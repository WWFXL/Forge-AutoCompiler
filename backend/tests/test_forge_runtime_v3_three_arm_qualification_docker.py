"""Issue #352 Runtime v3 三臂 qualification 的 opt-in 真实 Docker 门禁。"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from deerflow.compile import operations
from deerflow.compile.agent_workflow_node import AgentWorkflowBudgetSnapshot
from deerflow.compile.agent_workflow_runtime import AgentWorkflowEvidenceLedger
from deerflow.compile.agent_workflow_schemas import (
    AgentBuildNodeInput,
    AgentBuildNodeResult,
    AgentWorkflowBudget,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowTargetContract,
    AgentWorkflowUsage,
    SubmitCandidateRequest,
)
from deerflow.compile.candidate_verifier import CandidateVerifier
from deerflow.compile.docker_runtime import CompileDockerRuntime
from deerflow.compile.external_evaluator import FunctionalOracleSpec
from deerflow.compile.external_evaluator_v3 import (
    ForgeCompileEvaluationBackend,
    run_external_evaluator_v3,
)
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.operations import (
    CompileOperationsServices,
    cleanup_and_finalize_compile_session_impl,
    clone_repository_impl,
    inspect_build_system_impl,
    prepare_compile_session_impl,
)
from deerflow.compile.schemas import BuildCommandRecord, CompileSession, utc_now_iso
from deerflow.config.paths import Paths
from deerflow.models import factory as model_factory
from deerflow.tools.bound_compile_tools import _run_container_bash_impl

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_runtime_v3_three_arm_qualification.py"
DOCKER_ENABLED = os.getenv("FORGE_RUN_RUNTIME_V3_QUALIFICATION_DOCKER") == "1"
COMPILE_IMAGE = "autocompiler:gcc13"
WORKDIR = "/workspace/repo"
BUILD_DIRECTORY = "/workspace/repo/build"
BUILD_OUTPUT = "build/forge_fixture"
STAGED_ARTIFACT = "bin/forge-fixture"
BUILD_TARGET = "forge_fixture"
TARGET_ID = "forge-fixture"
ORACLE_REF = "oracle-runtime-v3-qualification"
CAPTURE_LABEL = "forge.runtime-v3-qualification.capture"

CONFIGURE_COMMAND = "cmake -S /workspace/repo -B /workspace/repo/build -G Ninja"
BUILD_COMMAND = "cmake --build /workspace/repo/build --target forge_fixture -j2"
STAGE_COMMAND = "mkdir -p /artifacts/bin && cp /workspace/repo/build/forge_fixture /artifacts/bin/forge-fixture"
OPAQUE_INNER_COMMAND = f"rm -rf /workspace/repo/build && {CONFIGURE_COMMAND} && {BUILD_COMMAND} && mkdir -p /artifacts/bin && cp /workspace/repo/build/forge_fixture /artifacts/bin/forge-fixture"
OPAQUE_COMMAND = f"sh -c {json.dumps(OPAQUE_INNER_COMMAND)}"

pytestmark = pytest.mark.skipif(
    not DOCKER_ENABLED,
    reason=("set FORGE_RUN_RUNTIME_V3_QUALIFICATION_DOCKER=1 to run the Runtime v3 qualification"),
)

FIXTURE_FILES = {
    "CMakeLists.txt": ("cmake_minimum_required(VERSION 3.16)\nproject(forge_runtime_v3_qualification C)\nadd_executable(forge_fixture main.c)\n"),
    "main.c": "int main(void) { return 0; }\n",
}


def _load_adapter():
    spec = importlib.util.spec_from_file_location(
        "forge_runtime_v3_three_arm_qualification_docker_test",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


qualification = _load_adapter()
p2 = qualification.load_p2_reference()


def _git(*args: str, cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout.strip()


@pytest.fixture(scope="module")
def fixture_repository(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[str, str]]:
    root = tmp_path_factory.mktemp("runtime-v3-qualification-repository")
    source = root / "source"
    bare = root / "fixture.git"
    source.mkdir()
    for relative_path, content in FIXTURE_FILES.items():
        path = source / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git("init", "--quiet", cwd=source)
    _git("config", "user.name", "Forge Qualification", cwd=source)
    _git("config", "user.email", "qualification@example.invalid", cwd=source)
    _git("add", ".", cwd=source)
    _git("commit", "--quiet", "-m", "runtime v3 qualification fixture", cwd=source)
    commit_sha = _git("rev-parse", "HEAD", cwd=source)
    _git("clone", "--quiet", "--bare", str(source), str(bare), cwd=root)
    _git("update-server-info", cwd=bare)

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    daemon = subprocess.Popen(
        [
            "git",
            "daemon",
            "--reuseaddr",
            "--export-all",
            f"--base-path={root}",
            "--listen=0.0.0.0",
            f"--port={port}",
            str(root),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 5
    while True:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            if daemon.poll() is not None or time.monotonic() >= deadline:
                daemon.terminate()
                raise RuntimeError("qualification fixture git daemon failed to start")
            time.sleep(0.05)
    try:
        yield f"git://host.docker.internal:{port}/fixture.git", commit_sha
    finally:
        daemon.terminate()
        try:
            daemon.wait(timeout=5)
        except subprocess.TimeoutExpired:
            daemon.kill()
            daemon.wait(timeout=5)


def _managed_resources() -> dict[str, list[str]]:
    commands = {
        "containers": [
            "docker",
            "ps",
            "-aq",
            "--filter",
            "label=deerflow.compile.managed=true",
        ],
        "paused": [
            "docker",
            "ps",
            "-q",
            "--filter",
            "status=paused",
            "--filter",
            "label=deerflow.compile.managed=true",
        ],
        "images": [
            "docker",
            "images",
            "-q",
            "--filter",
            "label=deerflow.compile.managed=true",
        ],
    }
    resources: dict[str, list[str]] = {}
    for name, command in commands.items():
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        resources[name] = sorted(set(result.stdout.split()))
    return resources


@pytest.fixture(scope="module", autouse=True)
def require_docker_gate() -> Iterator[None]:
    if not DOCKER_ENABLED:
        yield
        return
    required = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if required.returncode != 0:
        pytest.fail(required.stderr.strip() or required.stdout.strip())
    image = subprocess.run(
        ["docker", "image", "inspect", COMPILE_IMAGE],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if image.returncode != 0:
        pytest.fail(f"Required image {COMPILE_IMAGE!r} is unavailable")
    assert _managed_resources() == {"containers": [], "paused": [], "images": []}
    yield
    assert _managed_resources() == {"containers": [], "paused": [], "images": []}


@pytest.fixture(autouse=True)
def forbid_provider_and_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise AssertionError("qualification must not construct a provider-backed model")

    monkeypatch.setattr(model_factory, "create_chat_model", forbidden)
    for variable in (
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(variable, raising=False)


def _oracle_spec() -> FunctionalOracleSpec:
    return FunctionalOracleSpec(
        oracle_ref=ORACLE_REF,
        argv=("/artifacts/bin/forge-fixture",),
        workdir=WORKDIR,
        timeout_seconds=60,
    )


def _budget() -> AgentWorkflowBudget:
    return AgentWorkflowBudget(
        max_model_requests=4,
        max_recorded_tokens=20_000,
        max_agent_steps=12,
        max_tool_calls=8,
        max_commands=4,
        node_timeout_seconds=600,
        command_timeout_seconds=300,
        evaluator_timeout_seconds=600,
        replay_timeout_seconds=600,
        cleanup_timeout_seconds=120,
    )


def _node_input(session: CompileSession, commit_sha: str) -> AgentBuildNodeInput:
    return AgentBuildNodeInput(
        task_id="runtime-v3-qualification",
        attempt_id="runtime-v3-qualification-attempt",
        session_id=session.session_id,
        repository_url=session.repo_url,
        commit_sha=commit_sha,
        source_snapshot_sha256=hashlib.sha256(commit_sha.encode()).hexdigest(),
        build_system_candidates=("cmake",),
        target_contract=AgentWorkflowTargetContract(
            target_id=TARGET_ID,
            artifact_types=("executable",),
            artifact_path_patterns=(STAGED_ARTIFACT,),
            functional_oracle_ref=ORACLE_REF,
        ),
        operation_policy_ref="runtime-v3-qualification-zero-provider",
        environment=AgentWorkflowEnvironmentIdentity(
            image_id=session.image_id or "",
            parallel_jobs=session.parallel_jobs,
            network_policy="compile-network-v1",
        ),
        budget=_budget(),
        experiment_identity=AgentWorkflowExperimentIdentity(
            manifest_sha256="a" * 64,
            protocol_sha256="b" * 64,
            runner_sha256="c" * 64,
        ),
        initial_observation={
            "required_candidate_artifacts": (STAGED_ARTIFACT,),
            "zero_provider": True,
            "qualification_only": True,
        },
    )


def _candidate(
    *,
    supporting_command_id: str,
    recipe_command_ids: tuple[str, ...],
    correct_mapping: bool,
) -> SubmitCandidateRequest:
    target_id = TARGET_ID if correct_mapping else "wrong-target"
    return SubmitCandidateRequest(
        candidate_id="runtime-v3-qualification-candidate",
        build_system="cmake",
        supporting_command_ids=(supporting_command_id,),
        artifact_paths=(STAGED_ARTIFACT,),
        target_mapping={target_id: STAGED_ARTIFACT},
        recipe_command_ids=recipe_command_ids,
        agent_summary="Deterministic zero-provider qualification candidate.",
    )


def _run_tool(
    session: CompileSession,
    command: str,
    role: str,
) -> BuildCommandRecord:
    result, _message, record = _run_container_bash_impl(
        session=session,
        command=command,
        command_role=role,
        timeout_seconds=300,
        workdir=WORKDIR,
    )
    assert result.exit_code == 0, result.combined_output
    return record


def _record_opaque_parent(
    *,
    manager: CompileSessionManager,
    runtime: CompileDockerRuntime,
    session: CompileSession,
) -> BuildCommandRecord:
    started_at = utc_now_iso()
    started = time.monotonic()
    result = runtime.exec(
        session,
        OPAQUE_COMMAND,
        workdir=WORKDIR,
        timeout_seconds=300,
        strict_shell=True,
    )
    record = BuildCommandRecord(
        stage="bash",
        command=OPAQUE_COMMAND,
        workdir=WORKDIR,
        command_id=f"command_{uuid.uuid4().hex}",
        role="build",
        exit_code=result.exit_code,
        started_at=started_at,
        completed_at=utc_now_iso(),
        timeout_seconds=300,
        duration_seconds=round(time.monotonic() - started, 6),
        timed_out=result.exit_code == 124,
        termination=("timeout" if result.exit_code == 124 else ("failed" if result.exit_code != 0 else "completed")),
    )
    manager.record_command(session, record)
    manager.save_session(session)
    assert result.exit_code == 0, result.combined_output
    return record


def _tree_manifest(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(
        root.rglob("*"),
        key=lambda item: item.relative_to(root).as_posix(),
    ):
        relative = path.relative_to(root).as_posix()
        stat = path.lstat()
        entry: dict[str, Any] = {"path": relative, "mode": stat.st_mode & 0o7777}
        if path.is_symlink():
            entry.update(type="symlink", target=os.readlink(path))
        elif path.is_dir():
            entry["type"] = "directory"
        elif path.is_file():
            entry.update(
                type="file",
                size=stat.st_size,
                sha256=qualification.sha256_file(path),
            )
        else:
            entry["type"] = "other"
        entries.append(entry)
    return entries


def _environment_identity(session: CompileSession) -> dict[str, Any]:
    return {
        "image_id": session.image_id,
        "workspace_sha256": qualification.canonical_sha256(_tree_manifest(Path(session.leadagent_repo_dir).parent)),
        "artifacts_sha256": qualification.canonical_sha256(_tree_manifest(Path(session.leadagent_artifacts_dir))),
    }


def _copy_tree(source: Path, target: Path) -> None:
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(source, target, symlinks=True)


def _capture_environment(
    parent: CompileSession,
    *,
    capture_id: str,
    snapshot_root: Path,
) -> dict[str, Any]:
    assert parent.container_id is not None
    snapshot_root.mkdir(parents=True, exist_ok=False)
    paused = subprocess.run(
        ["docker", "pause", parent.container_id],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert paused.returncode == 0, paused.stderr
    try:
        committed = subprocess.run(
            [
                "docker",
                "commit",
                "--no-pause",
                "--change",
                f"LABEL {CAPTURE_LABEL}={capture_id}",
                parent.container_id,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert committed.returncode == 0, committed.stderr
        continuation_image_id = committed.stdout.strip()
        assert continuation_image_id.startswith("sha256:")
        _copy_tree(
            Path(parent.leadagent_repo_dir).parent,
            snapshot_root / "workspace",
        )
        _copy_tree(
            Path(parent.leadagent_artifacts_dir),
            snapshot_root / "artifacts",
        )
    finally:
        unpaused = subprocess.run(
            ["docker", "unpause", parent.container_id],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert unpaused.returncode == 0, unpaused.stderr
    return {
        "continuation_image_id": continuation_image_id,
        "workspace": str(snapshot_root / "workspace"),
        "artifacts": str(snapshot_root / "artifacts"),
        "identity": {
            "image_id": continuation_image_id,
            "workspace_sha256": qualification.canonical_sha256(_tree_manifest(snapshot_root / "workspace")),
            "artifacts_sha256": qualification.canonical_sha256(_tree_manifest(snapshot_root / "artifacts")),
        },
    }


def _copy_parent_state(parent: CompileSession, arm: CompileSession) -> None:
    for field_name in (
        "commit_sha",
        "build_system",
        "build_system_capabilities",
        "selected_build_system",
        "executed_build_system",
        "post_build_supporting_command_id",
        "post_build_started_at",
        "post_build_commands_remaining",
        "commands",
        "artifacts",
        "verification",
        "summary",
        "error",
    ):
        setattr(arm, field_name, copy.deepcopy(getattr(parent, field_name)))
    arm.status = parent.status
    arm.replay_attempts = []


def _provision_arm(
    *,
    manager: CompileSessionManager,
    runtime: CompileDockerRuntime,
    parent: CompileSession,
    captured: dict[str, Any],
) -> CompileSession:
    opaque = uuid.uuid4().hex
    arm = manager.create_session(
        thread_id=f"q{opaque[:15]}",
        session_id=f"s{opaque[15:30]}",
        run_id=f"r{uuid.uuid4().hex[:20]}",
        repo_url=parent.repo_url,
        branch=parent.branch,
        image=captured["continuation_image_id"],
    )
    _copy_parent_state(parent, arm)
    _copy_tree(
        Path(captured["workspace"]),
        Path(arm.leadagent_repo_dir).parent,
    )
    _copy_tree(
        Path(captured["artifacts"]),
        Path(arm.leadagent_artifacts_dir),
    )
    manager.save_session(arm)
    runtime.create_container(arm)
    manager.save_session(arm)
    return arm


def _p2_evaluator(
    session: CompileSession,
    *,
    wrapper_command_id: str,
) -> Any:
    def evaluate(request: SubmitCandidateRequest) -> dict[str, Any]:
        build_tree = Path(session.leadagent_repo_dir) / "build" / "build.ninja"
        artifact_path = Path(session.leadagent_repo_dir) / BUILD_OUTPUT
        frozen = p2.FrozenIdentity(
            schema_version=p2.SCHEMA_VERSION,
            case_id="runtime-v3-qualification-provenance",
            repository_url=session.repo_url,
            commit_sha=session.commit_sha,
            image_id=session.image_id,
            physical_attempt_id="runtime-v3-qualification-p2",
            workdir=WORKDIR,
            build_directory=BUILD_DIRECTORY,
            generator="Ninja",
            build_tree_sha256=qualification.sha256_file(build_tree),
            target=BUILD_TARGET,
            artifact_relative_path=BUILD_OUTPUT,
            artifact_type="executable",
            artifact_size=artifact_path.stat().st_size,
            artifact_sha256=qualification.sha256_file(artifact_path),
        ).validate()
        wrapper = p2.record_invocation(
            command_id=wrapper_command_id,
            physical_attempt_id=frozen.physical_attempt_id,
            sequence=1,
            repository_url=frozen.repository_url,
            commit_sha=frozen.commit_sha,
            image_id=frozen.image_id,
            executable="sh",
            argv=("-c", OPAQUE_INNER_COMMAND),
            workdir=WORKDIR,
            previous_hash=p2.ZERO_HASH,
            output_paths=(BUILD_OUTPUT,),
            model_declared_role="build",
        )
        producer = wrapper
        invocations = (wrapper,)
        if request.supporting_command_ids[0] != wrapper_command_id:
            command_id = request.supporting_command_ids[0]
            command = next(item for item in session.commands if item.command_id == command_id)
            assert command.command == BUILD_COMMAND
            producer = p2.record_invocation(
                command_id=command_id,
                physical_attempt_id=frozen.physical_attempt_id,
                sequence=2,
                repository_url=frozen.repository_url,
                commit_sha=frozen.commit_sha,
                image_id=frozen.image_id,
                executable="cmake",
                argv=("--build", BUILD_DIRECTORY, "--target", BUILD_TARGET, "-j2"),
                workdir=WORKDIR,
                previous_hash=wrapper.ledger_hash,
                output_paths=(BUILD_OUTPUT,),
                model_declared_role="build",
            )
            invocations = (wrapper, producer)
        artifact = p2.ArtifactIdentity(
            schema_version=p2.SCHEMA_VERSION,
            physical_attempt_id=frozen.physical_attempt_id,
            producer_command_id=producer.command_id,
            repository_url=frozen.repository_url,
            commit_sha=frozen.commit_sha,
            image_id=frozen.image_id,
            relative_path=BUILD_OUTPUT,
            artifact_type="executable",
            size=frozen.artifact_size,
            sha256=frozen.artifact_sha256,
            observed_after_sequence=len(invocations) + 1,
        )
        decision = p2.evaluate_p2(frozen, invocations, artifact)
        return {
            **asdict(decision),
            "paths": [BUILD_OUTPUT],
            "expected": ["cmake"],
            "actual": [decision.proof_mode or decision.reason],
        }

    return evaluate


def _create_service(
    *,
    session: CompileSession,
    manager: CompileSessionManager,
    node_input: AgentBuildNodeInput,
    tracker: Any,
    store: Any,
    provenance_evaluator: Any = None,
) -> tuple[Any, AgentWorkflowEvidenceLedger, Path]:
    workflow_dir = Path(session.metadata_path).parent / "qualification" / node_input.attempt_id
    ledger = AgentWorkflowEvidenceLedger(
        workflow_dir / "events.jsonl",
        node_input=node_input,
        run_id=session.run_id or "",
    )
    candidate_path = workflow_dir / "candidate.json"
    service = qualification.create_candidate_service(
        verifier=CandidateVerifier(oracle_spec=_oracle_spec()),
        provenance_evaluator=provenance_evaluator,
        node_input=node_input,
        session=session,
        manager=manager,
        store=store,
        candidate_path=candidate_path,
        ledger=ledger,
    )
    return service, ledger, candidate_path


def _restore_budget(
    tracker: Any,
    snapshot: AgentWorkflowBudgetSnapshot,
) -> None:
    tracker.consume(
        model_requests=snapshot.model_requests,
        recorded_tokens=snapshot.recorded_tokens,
        agent_steps=snapshot.agent_steps,
        tool_calls=snapshot.tool_calls,
        commands=snapshot.commands,
    )


def _normalize_session_tree(session: CompileSession) -> None:
    session_dir = Path(session.metadata_path).parent
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{session_dir}:/target",
            COMPILE_IMAGE,
            "sh",
            "-c",
            f"chown -R {os.getuid()}:{os.getgid()} /target && chmod -R u+rwX /target",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def _remove_capture_image(image_id: str | None) -> None:
    if not image_id:
        return
    subprocess.run(
        ["docker", "image", "rm", "-f", image_id],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize("stratum", qualification.STRATA)
def test_runtime_v3_three_arm_state_matched_stratum(
    stratum: str,
    fixture_repository: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_url, commit_sha = fixture_repository
    workspace = tmp_path / "workspace"
    paths = Paths(
        base_dir=tmp_path / ".deer-flow",
        workspace_root=workspace,
        host_workspace_root=str(workspace),
    )
    manager = CompileSessionManager(paths=paths, default_image=COMPILE_IMAGE)
    runtime = CompileDockerRuntime(manager=manager)
    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=runtime),
    )
    monkeypatch.setenv(
        "COMPILE_RUNTIME_NO_PROXY",
        "host.docker.internal,127.0.0.1,localhost",
    )
    parent = prepare_compile_session_impl(
        thread_id=f"qparent{uuid.uuid4().hex[:12]}",
        repo_url=repository_url,
        run_id=f"rparent{uuid.uuid4().hex[:12]}",
        task_description="Runtime v3 three-arm zero-provider qualification parent",
    )
    arms: dict[str, CompileSession] = {}
    continuation_image_id: str | None = None
    cleaned_sessions: set[str] = set()
    capture_id = f"q{uuid.uuid4().hex[:20]}"
    try:
        clone, _message = clone_repository_impl(
            session=parent,
            repo_url=repository_url,
            max_retries=1,
        )
        assert clone.exit_code == 0, clone.combined_output
        assert parent.commit_sha == commit_sha
        primary, _detected, _suggested = inspect_build_system_impl(session=parent)
        assert primary == "cmake"
        parent.selected_build_system = "cmake"
        manager.save_session(parent)

        if stratum == "delivery_target":
            configure = _run_tool(parent, CONFIGURE_COMMAND, "configure")
            build = _run_tool(parent, BUILD_COMMAND, "build")
            stage = _run_tool(parent, STAGE_COMMAND, "artifact_stage")
            parent_request = _candidate(
                supporting_command_id=build.command_id,
                recipe_command_ids=(
                    configure.command_id,
                    build.command_id,
                    stage.command_id,
                ),
                correct_mapping=False,
            )
            parent_p2 = None
            parent_wrapper_id = None
        else:
            wrapper = _record_opaque_parent(
                manager=manager,
                runtime=runtime,
                session=parent,
            )
            stage = _run_tool(parent, STAGE_COMMAND, "artifact_stage")
            parent_request = _candidate(
                supporting_command_id=wrapper.command_id,
                recipe_command_ids=(wrapper.command_id, stage.command_id),
                correct_mapping=True,
            )
            parent_p2 = _p2_evaluator(
                parent,
                wrapper_command_id=wrapper.command_id,
            )
            parent_wrapper_id = wrapper.command_id

        parent_input = _node_input(parent, commit_sha)
        _parent_state, parent_tracker, parent_store = qualification.create_store(parent_input.budget)
        parent_tracker.consume(tool_calls=1)
        parent_service, _parent_ledger, _parent_candidate_path = _create_service(
            session=parent,
            manager=manager,
            node_input=parent_input,
            tracker=parent_tracker,
            store=parent_store,
            provenance_evaluator=parent_p2,
        )
        rejection = parent_service.submit(parent_request)
        assert rejection.accepted is False
        assert rejection.terminal_for_agent is False
        if stratum == "delivery_target":
            assert rejection.rejection_codes == ("target_mapping_invalid",)
            finding = rejection.rejection_details[0].as_payload()
        else:
            assert rejection.rejection_codes == ("build_system_unproven",)
            finding = parent_service.last_provenance_finding
        assert finding is not None

        captured = _capture_environment(
            parent,
            capture_id=capture_id,
            snapshot_root=tmp_path / "checkpoint-snapshot",
        )
        continuation_image_id = captured["continuation_image_id"]
        parent_history_sha256 = qualification.canonical_sha256([asdict(command) for command in parent.commands])
        rejection_event = {
            "response": json.loads(rejection.canonical_json()),
            "finding": qualification.normalize_finding(finding),
        }
        parent_budget = parent_tracker.snapshot()
        common_state = {
            "source": {
                "repository_url": repository_url,
                "commit_sha": commit_sha,
            },
            "parent_history_sha256": parent_history_sha256,
            "candidate_request_sha256": parent_request.canonical_sha256(),
            "rejection_event_sha256": qualification.canonical_sha256(rejection_event),
            "message_prefix_sha256": qualification.canonical_sha256(
                {
                    "instruction": "submit candidate",
                    "tool": "submit_candidate_v1",
                    "request": parent_request.canonical_sha256(),
                    "next": "continuation",
                }
            ),
            "environment": captured["identity"],
            "budget": asdict(parent_budget),
            "tool_policy": qualification.TOOL_POLICY,
            "authorities": qualification.component_hashes(),
        }
        checkpoint = qualification.persist_checkpoint(
            tmp_path / "qualification-checkpoint.json",
            {
                "schema_version": qualification.SCHEMA_VERSION,
                "capture_id": capture_id,
                "pair_id": f"pair-{capture_id}",
                "stratum": stratum,
                "common_state": common_state,
                "provider_calls": 0,
                "formal_attempts": 0,
                "experiment_evidence_writes": 0,
            },
        )
        assert qualification.validate_checkpoint(tmp_path / "qualification-checkpoint.json") == checkpoint

        projections = qualification.build_projection_set(
            pair_id=f"pair-{capture_id}",
            stratum=stratum,
            finding=finding,
        )
        for arm_name in qualification.ARMS:
            arms[arm_name] = _provision_arm(
                manager=manager,
                runtime=runtime,
                parent=parent,
                captured=captured,
            )
        arm_states: dict[str, dict[str, Any]] = {}
        for arm_name, arm in arms.items():
            assert _environment_identity(arm) == captured["identity"]
            assert qualification.canonical_sha256([asdict(command) for command in arm.commands]) == parent_history_sha256
            arm_input = _node_input(arm, commit_sha)
            _state, tracker, _store = qualification.create_store(arm_input.budget)
            _restore_budget(tracker, parent_budget)
            assert tracker.snapshot() == parent_budget
            arm_states[arm_name] = {
                "common_state": {
                    **copy.deepcopy(common_state),
                    "environment": _environment_identity(arm),
                    "budget": asdict(tracker.snapshot()),
                },
                "feedback": projections[arm_name].payload,
            }
        qualification.validate_state_matched(
            arm_states,
            pair_id=f"pair-{capture_id}",
            stratum=stratum,
        )

        outcomes: dict[str, Any] = {}
        for arm_name, arm in arms.items():
            arm_input = _node_input(arm, commit_sha)
            _state, tracker, store = qualification.create_store(arm_input.budget)
            _restore_budget(tracker, parent_budget)
            exposure = projections[arm_name].payload
            assert exposure == arm_states[arm_name]["feedback"]
            if stratum == "provenance":
                assert parent_wrapper_id is not None
                tracker.consume(tool_calls=1, commands=1)
                continuation_build = _run_tool(arm, BUILD_COMMAND, "build")
                tracker.consume(tool_calls=1, commands=1)
                continuation_stage = _run_tool(
                    arm,
                    STAGE_COMMAND,
                    "artifact_stage",
                )
                candidate = _candidate(
                    supporting_command_id=continuation_build.command_id,
                    recipe_command_ids=(
                        parent_wrapper_id,
                        stage.command_id,
                        continuation_build.command_id,
                        continuation_stage.command_id,
                    ),
                    correct_mapping=True,
                )
                provenance_evaluator = _p2_evaluator(
                    arm,
                    wrapper_command_id=parent_wrapper_id,
                )
            else:
                candidate = _candidate(
                    supporting_command_id=build.command_id,
                    recipe_command_ids=(
                        configure.command_id,
                        build.command_id,
                        stage.command_id,
                    ),
                    correct_mapping=True,
                )
                provenance_evaluator = None
            tracker.consume(tool_calls=1)
            service, ledger, candidate_path = _create_service(
                session=arm,
                manager=manager,
                node_input=arm_input,
                tracker=tracker,
                store=store,
                provenance_evaluator=provenance_evaluator,
            )
            accepted = service.submit(candidate)
            assert accepted.accepted is True
            assert accepted.terminal_for_agent is True
            snapshot = tracker.snapshot()
            node_result = AgentBuildNodeResult(
                node_status="submitted",
                candidate_generated_observed=True,
                candidate_submitted=True,
                submission_id=accepted.submission_id,
                candidate_record_sha256=accepted.candidate_record_sha256,
                usage=AgentWorkflowUsage(
                    model_requests=snapshot.model_requests,
                    recorded_tokens=snapshot.recorded_tokens,
                    agent_steps=snapshot.agent_steps,
                    tool_calls=snapshot.tool_calls,
                    commands=snapshot.commands,
                ),
                wall_clock_ms=0,
                evidence_head_sha256=ledger.head_sha256,
                session_terminal_status=arm.status,
            )
            evaluation_id = f"evaluation-{uuid.uuid4().hex[:20]}"
            evaluator_identity = {
                "task_id": arm_input.task_id,
                "attempt_id": arm_input.attempt_id,
                "evaluation_id": evaluation_id,
                "evaluator_version": "forge-external-evaluator-1.2.0",
            }
            evaluation = run_external_evaluator_v3(
                node_input=arm_input,
                node_result=node_result,
                session=arm,
                manager=manager,
                candidate_path=candidate_path,
                evaluation_id=evaluation_id,
                backend=ForgeCompileEvaluationBackend(oracle_registry={ORACLE_REF: _oracle_spec()}),
            )
            assert evaluation.strict_reproducible_build_success is True
            current = manager.load_session(arm.session_id, arm.thread_id)
            arm.__dict__.update(current.__dict__)
            assert arm.status == "verified"
            assert arm.replay_attempts[-1].status == "passed"
            assert arm.replay_attempts[-1].cleanup_succeeded is True
            if stratum == "provenance":
                provenance = provenance_evaluator(candidate)
                provenance_passed = provenance["status"] == "proven"
            else:
                provenance_passed = (
                    operations._infer_executed_build_system(
                        arm.commands,
                        candidate.supporting_command_ids[0],
                    )
                    == "cmake"
                )
            finalized, cleanup = cleanup_and_finalize_compile_session_impl(session=arm)
            cleaned_sessions.add(arm.session_id)
            assert finalized.status == "completed"
            qualification.validate_strict_outcome(
                qualification.StrictOutcome(
                    candidate=True,
                    functional_oracle=next(layer for layer in evaluation.layers if layer.layer == "S3").status == "passed",
                    provenance=provenance_passed,
                    external_evaluator=True,
                    clean_replay=True,
                    cleanup=cleanup.succeeded,
                    managed_orphans=(),
                    evaluator_input=evaluator_identity,
                )
            )
            outcomes[arm_name] = {
                "candidate": "passed",
                "functional_oracle": "passed",
                "provenance": "passed",
                "external_evaluator": "passed",
                "clean_replay": "passed",
                "cleanup": "passed",
                "provider_calls": 0,
                "formal_attempts": 0,
                "experiment_evidence_writes": 0,
                "model_requests": snapshot.model_requests,
                "recorded_tokens": snapshot.recorded_tokens,
            }

        assert set(outcomes) == set(qualification.ARMS)
        assert {(outcome["provider_calls"], outcome["formal_attempts"], outcome["experiment_evidence_writes"]) for outcome in outcomes.values()} == {(0, 0, 0)}
        assert {(outcome["model_requests"], outcome["recorded_tokens"]) for outcome in outcomes.values()} == {(0, 0)}

        parent_finalized, parent_cleanup = cleanup_and_finalize_compile_session_impl(
            session=parent,
            interrupted_status="cancelled",
            error="Runtime v3 qualification parent checkpoint completed.",
        )
        cleaned_sessions.add(parent.session_id)
        assert parent_finalized.status == "cancelled"
        assert parent_cleanup.succeeded is True
        _remove_capture_image(continuation_image_id)
        continuation_image_id = None
        assert _managed_resources() == {
            "containers": [],
            "paused": [],
            "images": [],
        }
    finally:
        for session in reversed([*arms.values(), parent]):
            if session.session_id not in cleaned_sessions:
                runtime.stop_and_remove_container(session)
            _normalize_session_tree(session)
        _remove_capture_image(continuation_image_id)
