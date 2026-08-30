"""Issue #232 六 case confirmatory lifecycle 的 opt-in Ubuntu 原生 Docker 门禁。"""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import subprocess
import sys
import time
import uuid
from dataclasses import asdict
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
from deerflow.compile.operations import (
    CompileOperationsServices,
    cleanup_and_finalize_compile_session_impl,
    submit_build_result_impl,
)
from deerflow.compile.schemas import BuildCommandRecord, utc_now_iso
from deerflow.config.paths import Paths

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "forge_opaque_provenance_confirmatory_lifecycle_gate.py"
DOCKER_ENABLED = os.getenv("FORGE_RUN_OPAQUE_PROVENANCE_CONFIRMATORY_LIFECYCLE_DOCKER") == "1"

pytestmark = pytest.mark.skipif(
    not DOCKER_ENABLED,
    reason="set FORGE_RUN_OPAQUE_PROVENANCE_CONFIRMATORY_LIFECYCLE_DOCKER=1 in WSL Ubuntu",
)


def _load_gate():
    scripts = str(REPO_ROOT / "scripts")
    sys.path.insert(0, scripts)
    try:
        spec = importlib.util.spec_from_file_location(
            "forge_opaque_provenance_confirmatory_lifecycle_docker_test",
            SCRIPT_PATH,
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(scripts)


gate = _load_gate()


@pytest.fixture(scope="module", autouse=True)
def require_ubuntu_native_docker():
    if not DOCKER_ENABLED:
        yield
        return
    native_gate = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "require-ubuntu-native-docker.sh")],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if native_gate.returncode != 0:
        pytest.fail(native_gate.stderr.strip() or native_gate.stdout.strip())
    image = subprocess.run(
        ["docker", "image", "inspect", gate.COMPILE_IMAGE],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if image.returncode != 0:
        pytest.fail(f"Required image {gate.COMPILE_IMAGE!r} is unavailable")
    yield


def _record_command(
    *,
    manager: CompileSessionManager,
    runtime: CompileDockerRuntime,
    session: Any,
    command: str,
    role: str,
) -> BuildCommandRecord:
    started_at = utc_now_iso()
    started = time.monotonic()
    result = runtime.exec(
        session,
        command,
        workdir=gate.WORKDIR,
        timeout_seconds=600,
    )
    record = BuildCommandRecord(
        stage="bash",
        command=command,
        workdir=gate.WORKDIR,
        role=role,
        exit_code=result.exit_code,
        started_at=started_at,
        completed_at=utc_now_iso(),
        timeout_seconds=600,
        duration_seconds=round(time.monotonic() - started, 6),
        timed_out=result.exit_code == 124,
        termination=("timeout" if result.exit_code == 124 else ("failed" if result.exit_code != 0 else "completed")),
    )
    manager.record_command(session, record)
    manager.save_session(session)
    assert result.exit_code == 0, result.combined_output
    return record


def _policy(adapter: Any, *, image_id: str) -> ExperimentPolicy:
    return ExperimentPolicy(
        benchmark_id="forge-opaque-provenance-confirmatory-lifecycle-gate",
        manifest_sha256=gate.CANDIDATE_MANIFEST_SHA256,
        case_id=adapter.case_id,
        condition="confirmatory-lifecycle-zero-provider",
        repetition=1,
        expected_repo_url=adapter.repository_url,
        expected_commit_sha=adapter.commit_sha,
        expected_build_system=adapter.build_system,
        compile_image=gate.COMPILE_IMAGE,
        image_id=image_id,
        model_name="deterministic-no-provider",
        endpoint="https://example.invalid/v1",
        credential_env="UNUSED_ZERO_PROVIDER_CREDENTIAL",
        request_timeout_seconds=300,
        model_max_retries=0,
        compiler_max_turns=8,
        subagent_timeout_seconds=600,
        memory_enabled=False,
        skills_enabled=False,
        # 依赖已由固定 Dockerfile 烘焙；本门禁不把镜像构建伪装成 agent dependency action。
        required_system_packages=(),
        cmake_arguments=(),
        configure_arguments=(),
        environment=(),
        minimum_replay_delay_seconds=0,
        source_subdir=".",
        bootstrap_commands=adapter.bootstrap_commands,
        build_targets=(adapter.target,),
        artifact_instructions=(
            (
                adapter.staged_artifact,
                adapter.build_output,
                adapter.artifact_type,
            ),
        ),
    )


def _failure_events(ledger: ExperimentLedger) -> list[dict[str, Any]]:
    return [event for event in ledger.read() if event["event"] == "failure.recorded"]


def _constraint_failures(session: Any) -> list[str]:
    assert session.verification is not None
    checks = [check for check in session.verification.checks if check.name == "benchmark_constraints"]
    return [] if not checks else list(checks[0].actual)


def _compile_container_names() -> set[str]:
    result = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return {name for name in result.stdout.splitlines() if name.startswith(("deerflow-compile-", "deerflow-replay-"))}


@pytest.mark.parametrize("case_id", gate.candidate.CASE_ORDER)
def test_confirmatory_case_parent_treatment_replay_and_cleanup(
    case_id: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate.validate_gate_contract(REPO_ROOT)
    adapter = gate.build_case_adapter(case_id, REPO_ROOT)
    names_before = _compile_container_names()
    workspace = tmp_path / "workspace"
    paths = Paths(
        base_dir=tmp_path / ".deer-flow",
        workspace_root=workspace,
        host_workspace_root=str(workspace),
    )
    manager = CompileSessionManager(paths=paths, default_image=gate.COMPILE_IMAGE)
    runtime = CompileDockerRuntime(manager=manager)
    session = manager.create_session(
        thread_id=f"issue232-{case_id}-{uuid.uuid4().hex[:10]}",
        session_id=f"session-{uuid.uuid4().hex[:12]}",
        run_id=f"run-{uuid.uuid4().hex[:12]}",
        repo_url=adapter.repository_url,
        image=gate.COMPILE_IMAGE,
    )
    ledger = ExperimentLedger.create(
        tmp_path / "ledger.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"scope": "issue-232-confirmatory-lifecycle", "case_id": case_id},
    )
    known_container_ids: set[str] = set()
    active = False
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
        known_container_ids.add(session.container_id)

        clone_command = (
            f"git config --global --add safe.directory /workspace/repo && git init . && git remote add origin {shlex.quote(adapter.repository_url)} && git fetch --depth 1 origin {adapter.commit_sha} && git checkout --detach FETCH_HEAD"
        )
        clone = runtime.exec(
            session,
            clone_command,
            workdir=gate.WORKDIR,
            timeout_seconds=180,
        )
        assert clone.exit_code == 0, clone.combined_output
        package_check = runtime.exec(
            session,
            shlex.join(("dpkg-query", "-W", *adapter.required_system_packages)),
            workdir=gate.WORKDIR,
            timeout_seconds=30,
        )
        assert package_check.exit_code == 0, package_check.combined_output
        session.commit_sha = adapter.commit_sha
        session.build_system = adapter.build_system
        session.build_system_capabilities = [adapter.build_system]
        session.selected_build_system = adapter.build_system
        session.status = "inspected"
        manager.save_session(session)

        activate_experiment(
            thread_id=session.thread_id,
            experiment_id=ledger.experiment_id,
            physical_attempt_id=ledger.physical_attempt_id,
            ledger=ledger,
            policy=_policy(adapter, image_id=session.image_id),
        )
        active = True
        parent_record = _record_command(
            manager=manager,
            runtime=runtime,
            session=session,
            command=adapter.parent_command,
            role="build",
        )
        workspace_artifact = Path(session.leadagent_repo_dir) / adapter.build_output
        assert workspace_artifact.is_file() and workspace_artifact.stat().st_size > 0
        build_tree_sha256 = None
        if adapter.build_tree_relative_path is not None:
            build_tree = Path(session.leadagent_repo_dir) / adapter.build_tree_relative_path
            assert build_tree.is_file()
            build_tree_sha256 = gate.file_sha256(build_tree)
        frozen = gate.build_frozen_identity(
            adapter,
            image_id=session.image_id,
            physical_attempt_id=f"issue232-{case_id}-lifecycle",
            build_tree_sha256=build_tree_sha256,
            artifact_size=workspace_artifact.stat().st_size,
            artifact_sha256=gate.file_sha256(workspace_artifact),
        )
        parent_p2, parent_history = gate.evaluate_parent(
            adapter,
            frozen,
            parent_command_id=parent_record.command_id,
        )
        assert (parent_p2.status, parent_p2.reason) == ("unproven", "opaque_wrapper")

        parent_payload = json.loads(
            submit_build_result_impl(
                session=session,
                supporting_command_id=parent_record.command_id,
            )
        )
        assert parent_payload["status"] == "failed"
        assert parent_payload["candidate_status"] == "failed"
        assert parent_payload["replay_status"] == "not_run"
        assert session.replay_attempts == []
        assert _constraint_failures(session) == ["build_system_unproven"]
        assert len(session.artifacts) == 1
        assert session.artifacts[0].artifact_type == adapter.artifact_type
        parent_failures = _failure_events(ledger)
        assert len(parent_failures) == 1
        assert parent_failures[0]["payload"]["classification"] == "build_system_unproven"

        treatment_build = _record_command(
            manager=manager,
            runtime=runtime,
            session=session,
            command=adapter.treatment_build_command,
            role="build",
        )
        treatment_stage = _record_command(
            manager=manager,
            runtime=runtime,
            session=session,
            command=adapter.treatment_stage_command,
            role="artifact_stage",
        )
        treatment_p2, treatment_history = gate.evaluate_treatment(
            adapter,
            frozen,
            parent_command_id=parent_record.command_id,
            treatment_build_command_id=treatment_build.command_id,
            treatment_stage_command_id=treatment_stage.command_id,
        )
        assert (treatment_p2.status, treatment_p2.proof_mode) == (
            "proven",
            adapter.expected_proof_mode,
        )
        assert treatment_history[: len(parent_history)] == parent_history

        treatment_payload = json.loads(
            submit_build_result_impl(
                session=session,
                supporting_command_id=treatment_build.command_id,
            )
        )
        if treatment_payload["status"] != "passed":
            pytest.fail(
                json.dumps(
                    {
                        "submit": treatment_payload,
                        "replay_attempts": [asdict(replay) for replay in session.replay_attempts],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        assert treatment_payload["candidate_status"] == "passed"
        assert treatment_payload["replay_status"] == "passed"
        assert len(treatment_payload["artifacts"]) == 1
        assert treatment_payload["artifacts"][0]["artifact_type"] == adapter.artifact_type
        assert len(session.replay_attempts) == 1
        replay = session.replay_attempts[0]
        assert replay.status == "passed" and replay.cleanup_succeeded is True
        if replay.container_id is not None:
            known_container_ids.add(replay.container_id)

        deactivate_experiment(session.thread_id)
        active = False
        finalized, cleanup = cleanup_and_finalize_compile_session_impl(session=session)
        assert cleanup.succeeded and cleanup.removed
        assert finalized.status == "completed"
        assert finalized.finalized_at is not None
        assert finalized.verification is not None
        finalization_checks = [check for check in finalized.verification.checks if check.name == "accepted_artifacts_unchanged_after_cleanup"]
        assert len(finalization_checks) == 1 and finalization_checks[0].passed
    finally:
        if active:
            deactivate_experiment(session.thread_id)
        runtime.stop_and_remove_container(session)

    for container_id in known_container_ids:
        inspect = subprocess.run(
            ["docker", "container", "inspect", container_id],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert inspect.returncode != 0
    assert _compile_container_names() == names_before
