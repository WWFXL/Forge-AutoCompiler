"""Issue #186 runtime-parity gate 的 opt-in Ubuntu 原生 Docker 测试。"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

from deerflow.compile import operations
from deerflow.compile.docker_runtime import CompileDockerRuntime
from deerflow.compile.evidence import (
    ExperimentLedger,
    ExperimentPolicy,
    activate_experiment,
    deactivate_experiment,
    new_evidence_id,
)
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.operations import CompileOperationsServices
from deerflow.compile.schemas import BuildCommandRecord, utc_now_iso
from deerflow.config.paths import Paths
from deerflow.tools import bound_compile_tools

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
DOCKER_ENABLED = os.getenv("FORGE_RUN_OPAQUE_RUNTIME_PARITY_DOCKER") == "1"

pytestmark = pytest.mark.skipif(
    not DOCKER_ENABLED,
    reason="set FORGE_RUN_OPAQUE_RUNTIME_PARITY_DOCKER=1 in WSL Ubuntu",
)


def _load_module(name: str, filename: str):
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / filename)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


gate = _load_module(
    "forge_opaque_provenance_runtime_parity_gate_docker_test",
    "forge_opaque_provenance_runtime_parity_gate.py",
)
opaque = gate.opaque
execution = _load_module(
    "forge_opaque_provenance_runtime_parity_execution_test",
    "forge_opaque_provenance_minimal_canary_execution_runner.py",
)


@pytest.fixture(scope="module", autouse=True)
def require_ubuntu_native_docker():
    if not DOCKER_ENABLED:
        yield
        return
    daemon = subprocess.run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if daemon.returncode != 0:
        pytest.fail(f"Ubuntu native Docker is unavailable: {daemon.stderr.strip()}")
    image = subprocess.run(
        ["docker", "image", "inspect", opaque.COMPILE_IMAGE],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if image.returncode != 0:
        pytest.fail(f"Required image {opaque.COMPILE_IMAGE!r} is unavailable")
    yield


def _record_controlled_parent(
    *,
    manager: CompileSessionManager,
    runtime: CompileDockerRuntime,
    session: Any,
) -> BuildCommandRecord:
    started_at = utc_now_iso()
    started = time.monotonic()
    result = runtime.exec(
        session,
        opaque.PARENT_COMMAND,
        workdir=opaque.WORKDIR,
        timeout_seconds=300,
    )
    record = BuildCommandRecord(
        stage="bash",
        command=opaque.PARENT_COMMAND,
        workdir=opaque.WORKDIR,
        command_id=new_evidence_id("command"),
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


def _policy(*, image_id: str) -> ExperimentPolicy:
    return ExperimentPolicy(
        benchmark_id="forge-opaque-provenance-runtime-parity-gate",
        manifest_sha256="6" * 64,
        case_id=opaque.CASE_ID,
        condition="opaque-runtime-parity-zero-provider",
        repetition=1,
        expected_repo_url=opaque.REPOSITORY_URL,
        expected_commit_sha=opaque.COMMIT_SHA,
        expected_build_system="cmake",
        compile_image=opaque.COMPILE_IMAGE,
        image_id=image_id,
        model_name="deterministic-no-provider",
        endpoint="https://example.invalid/v1",
        credential_env="UNUSED_PROVIDER_KEY",
        request_timeout_seconds=1,
        model_max_retries=0,
        compiler_max_turns=8,
        subagent_timeout_seconds=600,
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=(),
        cmake_arguments=(),
        configure_arguments=(),
        environment=(),
        minimum_replay_delay_seconds=0,
        source_subdir="examples",
        build_targets=(opaque.TARGET,),
        artifact_instructions=((opaque.STAGED_ARTIFACT, opaque.BUILD_OUTPUT, "executable"),),
    )


def _constraint_failures(session: Any) -> list[str]:
    assert session.verification is not None
    checks = [check for check in session.verification.checks if check.name == "benchmark_constraints"]
    return [] if not checks else list(checks[0].actual)


def test_failed_submit_releases_fence_and_bound_repair_reaches_clean_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate.validate_gate_contract()
    workspace = tmp_path / "workspace"
    paths = Paths(
        base_dir=tmp_path / ".deer-flow",
        workspace_root=workspace,
        host_workspace_root=str(workspace),
    )
    manager = CompileSessionManager(paths=paths, default_image=opaque.COMPILE_IMAGE)
    runtime = CompileDockerRuntime(manager=manager)
    session = manager.create_session(
        thread_id=f"runtime-parity-{uuid.uuid4().hex[:12]}",
        session_id=f"runtime-parity-{uuid.uuid4().hex[:12]}",
        run_id=f"run-{uuid.uuid4().hex[:12]}",
        repo_url=opaque.REPOSITORY_URL,
        image=opaque.COMPILE_IMAGE,
    )
    ledger = ExperimentLedger.create(
        tmp_path / "runtime-parity.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("mechanism_attempt"),
        context={"scope": "issue-186-runtime-parity-zero-provider"},
    )
    active = False
    container_id: str | None = None
    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=runtime),
    )
    try:
        Path(session.leadagent_repo_dir).mkdir(parents=True, exist_ok=True)
        runtime.create_container(session)
        manager.save_session(session)
        assert session.image_id is not None and session.container_id is not None
        container_id = session.container_id
        clone = runtime.exec(
            session,
            f"git config --global --add safe.directory /workspace/repo && git init . && git remote add origin {opaque.REPOSITORY_URL} && git fetch --depth 1 origin {opaque.COMMIT_SHA} && git checkout --detach FETCH_HEAD",
            workdir=opaque.WORKDIR,
            timeout_seconds=180,
        )
        assert clone.exit_code == 0, clone.combined_output
        session.commit_sha = opaque.COMMIT_SHA
        session.build_system = "cmake"
        session.build_system_capabilities = ["cmake"]
        session.selected_build_system = "cmake"
        session.status = "inspected"
        manager.save_session(session)

        supporting = _record_controlled_parent(
            manager=manager,
            runtime=runtime,
            session=session,
        )
        workspace_artifact = Path(session.leadagent_repo_dir) / opaque.BUILD_OUTPUT
        build_tree = Path(session.leadagent_repo_dir) / "build/build.ninja"
        frozen = execution.opaque.build_frozen_identity(
            image_id=session.image_id,
            physical_attempt_id=ledger.physical_attempt_id,
            build_tree_sha256=execution.primary.lifecycle.sha256_file(build_tree),
            artifact_size=workspace_artifact.stat().st_size,
            artifact_sha256=execution.primary.lifecycle.sha256_file(workspace_artifact),
        )
        parent_p2, _parent_history = execution.opaque.evaluate_parent(
            frozen,
            parent_command_id=supporting.command_id,
        )
        assert parent_p2.status == "unproven"
        assert parent_p2.reason == "opaque_wrapper"
        bound_compile_tools._set_post_build_phase(session, supporting.command_id)
        activate_experiment(
            thread_id=session.thread_id,
            experiment_id=ledger.experiment_id,
            physical_attempt_id=ledger.physical_attempt_id,
            ledger=ledger,
            policy=_policy(image_id=session.image_id),
        )
        active = True
        tools = bound_compile_tools.get_bound_compile_tools(session)
        run_tool = next(tool for tool in tools if tool.name == "run_container_bash")
        submit_tool = next(tool for tool in tools if tool.name == "submit_build_result")

        parent_payload = json.loads(submit_tool.invoke({"supporting_command_id": supporting.command_id}))
        assert parent_payload["status"] == "failed"
        assert parent_payload["replay_status"] == "not_run"
        assert _constraint_failures(session) == ["build_system_unproven"]

        after_failure = manager.load_session(session.session_id, session.thread_id)
        assert after_failure.post_build_supporting_command_id is None
        assert after_failure.post_build_started_at is None
        assert after_failure.post_build_commands_remaining is None

        adapter = gate.RuntimeParityToolAdapter(
            run_tool=run_tool,
            submit_tool=submit_tool,
            staged_artifacts_present=lambda: bound_compile_tools._has_staged_artifacts(session),
        )
        inspection = adapter.run(
            "test -f build/build.ninja",
            command_role="other",
        )
        assert "exit_code=0" in inspection
        repair_payload = json.loads(adapter.run(opaque.TREATMENT_BUILD_COMMAND, command_role="build"))
        assert repair_payload["command"]["command_role"] == "build"
        assert repair_payload["automatic_submit"]["status"] == "passed"
        assert repair_payload["automatic_submit"]["candidate_status"] == "passed"
        assert repair_payload["automatic_submit"]["replay_status"] == "passed"

        authoritative = manager.load_session(session.session_id, session.thread_id)
        assert authoritative.verification is not None
        assert authoritative.verification.status == "passed"
        assert authoritative.verification.failed_checks == 0
        assert len(authoritative.replay_attempts) == 1
        assert authoritative.replay_attempts[0].status == "passed"
        assert authoritative.replay_attempts[0].cleanup_succeeded is True
        treatment_p2, treatment_history = execution._evaluate_arm_p2(
            authoritative,
            frozen,
            supporting.command_id,
        )
        assert treatment_p2.status == "proven"
        assert treatment_p2.proof_mode == "direct_cmake"
        assert len(treatment_history) == 3
        consumed = adapter.budget.snapshot()["consumed"]
        assert consumed == {
            "inspection": 1,
            "repair_build": 1,
            "artifact_stage": 0,
            "submit": 1,
        }
        assert not any(event["event"] == "model.request_started" for event in ledger.read())
    finally:
        if active:
            deactivate_experiment(session.thread_id)
        runtime.stop_and_remove_container(session)

    if container_id is not None:
        inspected = subprocess.run(
            ["docker", "container", "inspect", container_id],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert inspected.returncode != 0
