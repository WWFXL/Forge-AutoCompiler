"""Issue #147 controlled fault v1 的 opt-in Ubuntu 原生 Docker 门禁。"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from deerflow.compile import operations
from deerflow.compile.docker_runtime import CompileDockerRuntime
from deerflow.compile.evidence import ExperimentLedger, ExperimentPolicy, activate_experiment, deactivate_experiment, new_evidence_id
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.operations import CompileOperationsServices, submit_build_result_impl
from deerflow.compile.paths import get_host_artifacts_dir, get_host_logs_dir, get_host_repro_dir, get_host_workspace_dir
from deerflow.compile.schemas import BuildCommandRecord, utc_now_iso
from deerflow.config.paths import Paths

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
COMPILE_IMAGE = "autocompiler:gcc13"
CASE_ID = "cppitertools"
REPOSITORY_URL = "https://github.com/ryanhaining/cppitertools"
COMMIT_SHA = "531b3d753d2bbfe3b0ababe61c2e95e965c54a66"
DOCKER_INTEGRATION_ENABLED = os.getenv("FORGE_RUN_CONTROLLED_FAULT_DOCKER") == "1"

pytestmark = pytest.mark.skipif(
    not DOCKER_INTEGRATION_ENABLED,
    reason="set FORGE_RUN_CONTROLLED_FAULT_DOCKER=1 to run the controlled fault Docker gate",
)


def _load_module(name: str, filename: str):
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / filename)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


fault_module = _load_module("forge_controlled_fault_v1_gate_docker", "forge_controlled_fault_v1_gate.py")
lifecycle_module = _load_module("forge_real_lifecycle_checkpoint_gate_controlled", "forge_real_lifecycle_checkpoint_gate.py")


@pytest.fixture(scope="module", autouse=True)
def require_docker_and_compile_image():
    if not DOCKER_INTEGRATION_ENABLED:
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
        pytest.fail(f"Docker daemon is unavailable: {daemon.stderr.strip()}")
    image = subprocess.run(
        ["docker", "image", "inspect", COMPILE_IMAGE],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if image.returncode != 0:
        pytest.fail(f"Required image {COMPILE_IMAGE!r} is unavailable")
    yield


def _budget_manifest(capture_id: str, _message_sha256: str) -> dict:
    return lifecycle_module.budget_checkpoint.build_manifest(
        checkpoint_id=capture_id,
        limits={
            "provider_requests": 8,
            "compiler_invocations": 2,
            "compiler_model_turns": 8,
            "graph_recursion_steps": 24,
            "attempt_wall_clock_seconds": 720,
            "attempt_cleanup_reserve_seconds": 120,
            "compiler_wall_clock_seconds": 720,
            "compiler_post_build_reserve_seconds": 120,
            "post_build_commands": 2,
        },
        consumed_before_capture={
            "provider_requests": 0,
            "compiler_invocations": 1,
            "compiler_model_turns": 1,
            "graph_recursion_steps": 3,
            "attempt_wall_clock_seconds": 10,
            "compiler_wall_clock_seconds": 5,
            "post_build_commands": 0,
            "tokens": 0,
        },
        post_build_started=True,
    )


def _arm_plan(capture_id: str) -> dict:
    return {
        "baseline": {
            "thread_id": f"baseline-{capture_id}-thread",
            "session_id": f"baseline-{capture_id}-session",
            "environment_id": f"baseline-{capture_id}-environment",
        },
        "treatment": {
            "thread_id": f"treatment-{capture_id}-thread",
            "session_id": f"treatment-{capture_id}-session",
            "environment_id": f"treatment-{capture_id}-environment",
        },
    }


def _record_command(*, manager, runtime, session, command: str, role: str) -> BuildCommandRecord:
    started_at = utc_now_iso()
    started = time.monotonic()
    result = runtime.exec(session, command, workdir="/workspace/repo", timeout_seconds=300)
    record = BuildCommandRecord(
        stage="bash",
        command=command,
        workdir="/workspace/repo",
        role=role,
        exit_code=result.exit_code,
        started_at=started_at,
        completed_at=utc_now_iso(),
        timeout_seconds=300,
        duration_seconds=round(time.monotonic() - started, 6),
        timed_out=result.exit_code == 124,
        termination="timeout" if result.exit_code == 124 else ("failed" if result.exit_code != 0 else "completed"),
    )
    manager.record_command(session, record)
    manager.save_session(session)
    assert result.exit_code == 0, result.combined_output
    return record


def test_controlled_fault_capture_two_arm_restore_and_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    capture_id = f"faultv1-{uuid.uuid4().hex[:12]}"
    workspace = tmp_path / "workspace"
    paths = Paths(base_dir=tmp_path / ".deer-flow", workspace_root=workspace, host_workspace_root=str(workspace))
    manager = CompileSessionManager(paths=paths, default_image=COMPILE_IMAGE)
    runtime = CompileDockerRuntime(manager=manager)
    runner = lifecycle_module.environment_checkpoint.DockerCLI()
    session = manager.create_session(
        thread_id=f"parent-{uuid.uuid4().hex[:12]}",
        session_id=f"parent-{uuid.uuid4().hex[:12]}",
        run_id=f"run-{uuid.uuid4().hex[:12]}",
        repo_url=REPOSITORY_URL,
        image=COMPILE_IMAGE,
    )
    ledger = ExperimentLedger.create(
        tmp_path / "controlled-fault-ledger.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"scope": "issue-147-controlled-fault-docker-gate"},
    )
    active = False
    arm_sessions = []
    continuation_images: set[str] = set()
    snapshot = tmp_path / "snapshot"
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))
    try:
        Path(session.leadagent_repo_dir).mkdir(parents=True, exist_ok=True)
        runtime.create_container(session)
        manager.save_session(session)
        assert session.image_id is not None
        clone = runtime.exec(
            session,
            "git config --global --add safe.directory /workspace/repo && "
            "git init . && "
            "git remote add origin https://github.com/ryanhaining/cppitertools && "
            "git fetch --depth 1 origin 531b3d753d2bbfe3b0ababe61c2e95e965c54a66 && "
            "git checkout --detach FETCH_HEAD",
            workdir="/workspace/repo",
            timeout_seconds=180,
        )
        assert clone.exit_code == 0, clone.combined_output
        session.commit_sha = COMMIT_SHA
        session.build_system = "cmake"
        session.build_system_capabilities = ["cmake"]
        session.selected_build_system = "cmake"
        session.status = "inspected"
        manager.save_session(session)

        _record_command(
            manager=manager,
            runtime=runtime,
            session=session,
            command="cmake -S examples -B build -DCMAKE_BUILD_TYPE=Release",
            role="configure",
        )
        supporting = _record_command(
            manager=manager,
            runtime=runtime,
            session=session,
            command="cmake --build build --target accumulate_examples -j2",
            role="build",
        )
        _record_command(
            manager=manager,
            runtime=runtime,
            session=session,
            command="cp build/accumulate_examples /artifacts/accumulate_examples",
            role="artifact_stage",
        )

        policy = ExperimentPolicy(
            benchmark_id="forge-controlled-fault-v1-gate",
            manifest_sha256="7" * 64,
            case_id=CASE_ID,
            condition="controlled-fault-v1",
            repetition=1,
            expected_repo_url=REPOSITORY_URL,
            expected_commit_sha=COMMIT_SHA,
            expected_build_system="cmake",
            compile_image=COMPILE_IMAGE,
            image_id=session.image_id,
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
            cmake_arguments=("-DCMAKE_BUILD_TYPE=Release",),
            configure_arguments=(),
            environment=(),
            minimum_replay_delay_seconds=0,
        )
        activate_experiment(
            thread_id=session.thread_id,
            experiment_id=ledger.experiment_id,
            physical_attempt_id=ledger.physical_attempt_id,
            ledger=ledger,
            policy=policy,
        )
        active = True
        fault = fault_module.ControlledFaultV1(
            fault_module.ControlledFaultSpec(
                case_id=CASE_ID,
                build_output_relative_path="build/accumulate_examples",
                staged_relative_path="accumulate_examples",
                artifact_type="executable",
            )
        )
        fault_manifest = fault.inject(session=session, ledger=ledger, fault_id=new_evidence_id("fault"))
        assert fault_manifest["state"]["staged_artifact_present"] is False

        submit_results: list[str] = []

        def submit() -> str:
            result = submit_build_result_impl(session=session, supporting_command_id=supporting.command_id)
            submit_results.append(result)
            return result

        def evidence() -> dict:
            result = fault_module.validate_actionable_failure(ledger=ledger, session=session)
            result["session_sha256"] = lifecycle_module.sha256_file(Path(session.metadata_path))
            result["fault_state_sha256"] = fault_manifest["fault_state_sha256"]
            return result

        coordinator = lifecycle_module.CaptureCoordinator(tmp_path / "coordinator.sqlite")
        with SqliteSaver.from_conn_string(str(tmp_path / "messages.sqlite")) as saver:
            saver.setup()
            message_runtime = lifecycle_module.LifecycleMessageRuntime(
                saver,
                submit,
                repair_packet={
                    "schema_version": "forge-verifier-repair-packet-1.0.0",
                    "primary_classification": "candidate_verification_failed",
                },
            )
            environment = lifecycle_module.LifecycleEnvironmentAdapter(
                runner,
                local_snapshot_root=snapshot,
                host_snapshot_root=str(snapshot),
            )
            gate = lifecycle_module.RealLifecycleCheckpointGate(
                coordinator=coordinator,
                message_runtime=message_runtime,
                environment=environment,
                budget_capture=_budget_manifest,
                manager=manager,
                compile_runtime=runtime,
                owner="coordinator-controlled-fault",
            )
            manifest = gate.capture(
                capture_id=capture_id,
                session=session,
                instruction="freeze the controlled artifact staging failure before continuation",
                arm_plan=_arm_plan(capture_id),
                bind_sources={
                    "workspace": get_host_workspace_dir(session.session_id, session.thread_id, paths),
                    "artifacts": get_host_artifacts_dir(session.session_id, session.thread_id, paths),
                    "logs": get_host_logs_dir(session.session_id, session.thread_id, paths),
                    "repro": get_host_repro_dir(session.session_id, session.thread_id, paths),
                },
                evidence=evidence,
            )
            continuation_images.add(manifest["environment"]["continuation_image_id"])
            assert len(submit_results) == 1
            assert json.loads(submit_results[0])["candidate_status"] == "failed"
            assert session.replay_attempts == []

            baseline = gate.provision_arm(capture_id, "baseline", parent_session=session)
            treatment = gate.provision_arm(capture_id, "treatment", parent_session=session)
            arm_sessions.extend([baseline.session, treatment.session])
            assert gate.canonical_arm_environment("baseline") == gate.canonical_arm_environment("treatment")
            assert list(Path(baseline.session.leadagent_artifacts_dir).iterdir()) == []
            assert list(Path(treatment.session.leadagent_artifacts_dir).iterdir()) == []

            fault.restore_arm(session=baseline.session, runtime=runtime)
            assert list(Path(treatment.session.leadagent_artifacts_dir).iterdir()) == []
            fault.restore_arm(session=treatment.session, runtime=runtime)
            baseline_result = fault_module.validate_arm_submit_result(submit_build_result_impl(session=baseline.session, supporting_command_id=supporting.command_id))
            treatment_result = fault_module.validate_arm_submit_result(submit_build_result_impl(session=treatment.session, supporting_command_id=supporting.command_id))
            assert baseline_result["artifacts"][0]["sha256"] == treatment_result["artifacts"][0]["sha256"]
            assert len(baseline.session.replay_attempts) == 1
            assert len(treatment.session.replay_attempts) == 1

            cleaned = gate.cleanup(capture_id, parent_session=session)
            assert cleaned.phase == "cleaned"
            assert gate.external_counts() == {"provider_calls": 0, "formal_physical_attempts": 0, "model_tokens": 0}
    finally:
        if active:
            deactivate_experiment(session.thread_id)
        for arm_session in arm_sessions:
            runtime.stop_and_remove_container(arm_session)
        runtime.stop_and_remove_container(session)
        for container_id in runner.run(
            ["ps", "-aq", "--filter", f"label={lifecycle_module.CAPTURE_LABEL}={capture_id}"],
            check=False,
            timeout_seconds=30,
        ).stdout.split():
            runner.run(["rm", "-f", container_id], check=False, timeout_seconds=30)
        for image_id in continuation_images | set(
            runner.run(
                ["image", "ls", "-q", "--filter", f"label={lifecycle_module.CAPTURE_LABEL}={capture_id}"],
                check=False,
                timeout_seconds=30,
            ).stdout.split()
        ):
            runner.run(["image", "rm", "-f", image_id], check=False, timeout_seconds=60)

    assert (
        runner.run(
            ["ps", "-aq", "--filter", f"label={lifecycle_module.CAPTURE_LABEL}={capture_id}"],
            check=False,
            timeout_seconds=30,
        ).stdout.split()
        == []
    )
    assert (
        runner.run(
            ["image", "ls", "-q", "--filter", f"label={lifecycle_module.CAPTURE_LABEL}={capture_id}"],
            check=False,
            timeout_seconds=30,
        ).stdout.split()
        == []
    )
    assert not snapshot.exists()
