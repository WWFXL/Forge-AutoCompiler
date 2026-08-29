"""Issue #168 Make/Autotools 多 checkpoint 的 opt-in Compose/DooD 门禁。"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any

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

REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", Path(__file__).resolve().parents[2])).resolve()
SCRIPTS_DIR = REPO_ROOT / "scripts"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-verifier-multi-checkpoint-zero-provider-gate.json"
COMPILE_IMAGE = "autocompiler:gcc13"
DOCKER_ENABLED = os.getenv("FORGE_RUN_MULTI_CHECKPOINT_DOCKER") == "1"

pytestmark = pytest.mark.skipif(
    not DOCKER_ENABLED,
    reason="set FORGE_RUN_MULTI_CHECKPOINT_DOCKER=1 inside Forge Compose",
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


multi_gate = _load_module("forge_multi_checkpoint_zero_provider_docker", "forge_multi_checkpoint_zero_provider_gate.py")
fault_module = _load_module("forge_controlled_fault_v1_multi_checkpoint_docker", "forge_controlled_fault_v1_gate.py")
lifecycle = _load_module("forge_real_lifecycle_multi_checkpoint_docker", "forge_real_lifecycle_checkpoint_gate.py")
primary = _load_module("forge_checkpoint_primary_multi_checkpoint_docker", "forge_checkpoint_primary_canary.py")


def _load_manifest() -> dict[str, Any]:
    value = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return multi_gate.validate_manifest(value)


def _record_command(*, manager: CompileSessionManager, runtime: CompileDockerRuntime, session: Any, command: str, role: str) -> BuildCommandRecord:
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


def _policy(case: Any, *, image_id: str, manifest_sha256: str) -> ExperimentPolicy:
    return ExperimentPolicy(
        benchmark_id="forge-multi-checkpoint-zero-provider-gate",
        manifest_sha256=manifest_sha256,
        case_id=case.case_id,
        condition="controlled-fault-v1",
        repetition=1,
        expected_repo_url=case.repository_url,
        expected_commit_sha=case.commit_sha,
        expected_build_system=case.build_system,
        compile_image=COMPILE_IMAGE,
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
        required_system_packages=case.required_system_packages,
        cmake_arguments=case.cmake_arguments,
        configure_arguments=case.configure_arguments,
        environment=(),
        minimum_replay_delay_seconds=0,
        source_subdir=case.source_subdir,
        build_targets=case.build_targets,
        artifact_instructions=((case.staged_relative_path, case.build_output_relative_path, case.artifact_type),),
    )


def _remove_session_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
    try:
        path.parent.rmdir()
    except OSError:
        pass


@pytest.mark.parametrize("case_id", ["janet", "libcheck"])
def test_new_case_checkpoint_restore_verifier_replay_and_cleanup(case_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    primary.require_compose_dood()
    manifest = _load_manifest()
    multi_gate.verify_historical_components(manifest, REPO_ROOT)
    case = multi_gate.case_by_id(manifest, case_id)
    assert case.role == "new_gate"

    capture_id = f"issue168-{case_id}-{uuid.uuid4().hex[:8]}"
    paths = Paths()
    output_dir = paths.compile_sessions_dir / capture_id
    snapshot = output_dir / "snapshot"
    manager = CompileSessionManager(paths=paths, default_image=COMPILE_IMAGE)
    runtime = CompileDockerRuntime(manager=manager)
    docker = lifecycle.environment_checkpoint.DockerCLI()
    created_session_dirs: list[Path] = []
    original_create_session = manager.create_session

    def create_session(*args: Any, **kwargs: Any):
        session = original_create_session(*args, **kwargs)
        created_session_dirs.append(Path(session.metadata_path).parent)
        return session

    manager.create_session = create_session  # type: ignore[method-assign]
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))
    parent = manager.create_session(
        thread_id=f"parent-{uuid.uuid4().hex[:12]}",
        session_id=f"parent-{uuid.uuid4().hex[:12]}",
        run_id=f"run-{uuid.uuid4().hex[:12]}",
        repo_url=case.repository_url,
        image=COMPILE_IMAGE,
    )
    ledger = ExperimentLedger.create(
        output_dir / "parent.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"scope": "issue-168-multi-checkpoint-zero-provider", "case_id": case.case_id},
    )
    active = False
    gate = None
    arm_sessions: list[Any] = []
    continuation_images: set[str] = set()
    try:
        Path(parent.leadagent_repo_dir).mkdir(parents=True, exist_ok=True)
        runtime.create_container(parent)
        manager.save_session(parent)
        assert parent.image_id is not None
        clone = runtime.exec(
            parent,
            f"git config --global --add safe.directory /workspace/repo && git init . && git remote add origin {case.repository_url} && git fetch --depth 1 origin {case.commit_sha} && git checkout --detach FETCH_HEAD",
            workdir="/workspace/repo",
            timeout_seconds=180,
        )
        assert clone.exit_code == 0, clone.combined_output
        parent.commit_sha = case.commit_sha
        parent.build_system = case.build_system
        parent.build_system_capabilities = [case.build_system]
        parent.selected_build_system = case.build_system
        parent.status = "inspected"
        manager.save_session(parent)

        supporting = None
        for role, command in case.commands:
            record = _record_command(manager=manager, runtime=runtime, session=parent, command=command, role=role)
            if role == "build":
                supporting = record
        assert supporting is not None
        parent.post_build_supporting_command_id = supporting.command_id
        parent.post_build_started_at = utc_now_iso()
        parent.post_build_commands_remaining = 2
        manager.save_session(parent)

        activate_experiment(
            thread_id=parent.thread_id,
            experiment_id=ledger.experiment_id,
            physical_attempt_id=ledger.physical_attempt_id,
            ledger=ledger,
            policy=_policy(case, image_id=parent.image_id, manifest_sha256=multi_gate.canonical_sha256(manifest)),
        )
        active = True
        fault = fault_module.ControlledFaultV1(
            fault_module.ControlledFaultSpec(
                case_id=case.case_id,
                build_output_relative_path=case.build_output_relative_path,
                staged_relative_path=case.staged_relative_path,
                artifact_type=case.artifact_type,
            )
        )
        fault_manifest = fault.inject(session=parent, ledger=ledger, fault_id=new_evidence_id("fault"))
        assert fault_manifest["state"]["staged_artifact_present"] is False

        submit_results: list[str] = []

        def submit() -> str:
            result = submit_build_result_impl(session=parent, supporting_command_id=supporting.command_id)
            submit_results.append(result)
            return result

        def evidence() -> dict[str, Any]:
            result = fault_module.validate_actionable_failure(ledger=ledger, session=parent)
            result["session_sha256"] = lifecycle.sha256_file(Path(parent.metadata_path))
            result["fault_state_sha256"] = fault_manifest["fault_state_sha256"]
            return result

        coordinator = lifecycle.CaptureCoordinator(output_dir / "coordinator.sqlite")
        with SqliteSaver.from_conn_string(str(output_dir / "messages.sqlite")) as saver:
            saver.setup()
            message_runtime = lifecycle.LifecycleMessageRuntime(
                saver,
                submit,
                repair_packet={"schema_version": "forge-verifier-repair-packet-1.0.0", "primary_classification": "candidate_verification_failed"},
            )
            environment = lifecycle.LifecycleEnvironmentAdapter(
                docker,
                local_snapshot_root=snapshot,
                host_snapshot_root=primary.host_snapshot_root(snapshot),
            )
            gate = lifecycle.RealLifecycleCheckpointGate(
                coordinator=coordinator,
                message_runtime=message_runtime,
                environment=environment,
                budget_capture=primary._budget_manifest,
                manager=manager,
                compile_runtime=runtime,
                owner="issue-168-multi-checkpoint-gate",
            )
            capture = gate.capture(
                capture_id=capture_id,
                session=parent,
                instruction="freeze the controlled artifact staging failure before continuation",
                arm_plan=primary._arm_plan(capture_id),
                bind_sources={
                    "workspace": get_host_workspace_dir(parent.session_id, parent.thread_id, paths),
                    "artifacts": get_host_artifacts_dir(parent.session_id, parent.thread_id, paths),
                    "logs": get_host_logs_dir(parent.session_id, parent.thread_id, paths),
                    "repro": get_host_repro_dir(parent.session_id, parent.thread_id, paths),
                },
                evidence=evidence,
            )
            continuation_images.add(capture["environment"]["continuation_image_id"])
            assert len(submit_results) == 1
            assert json.loads(submit_results[0])["candidate_status"] == "failed"
            assert parent.replay_attempts == []
            deactivate_experiment(parent.thread_id)
            active = False
            ledger.append("experiment.completed", {"status": "passed"})

            baseline = gate.provision_arm(capture_id, "baseline", parent_session=parent)
            treatment = gate.provision_arm(capture_id, "treatment", parent_session=parent)
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

            cleaned = gate.cleanup(capture_id, parent_session=parent)
            assert cleaned.phase == "cleaned"
            assert gate.external_counts() == {"provider_calls": 0, "formal_physical_attempts": 0, "model_tokens": 0}
    finally:
        if active:
            deactivate_experiment(parent.thread_id)
        for session in arm_sessions:
            runtime.stop_and_remove_container(session)
        runtime.stop_and_remove_container(parent)
        for container_id in docker.run(["ps", "-aq", "--filter", f"label={lifecycle.CAPTURE_LABEL}={capture_id}"], check=False, timeout_seconds=30).stdout.split():
            docker.run(["rm", "-f", container_id], check=False, timeout_seconds=30)
        continuation_images.update(docker.run(["image", "ls", "-q", "--filter", f"label={lifecycle.CAPTURE_LABEL}={capture_id}"], check=False, timeout_seconds=30).stdout.split())
        for image_id in continuation_images:
            docker.run(["image", "rm", "-f", image_id], check=False, timeout_seconds=60)
        for session_dir in reversed(created_session_dirs):
            _remove_session_dir(session_dir)
        shutil.rmtree(output_dir, ignore_errors=True)

    assert docker.run(["ps", "-aq", "--filter", f"label={lifecycle.CAPTURE_LABEL}={capture_id}"], check=False, timeout_seconds=30).stdout.split() == []
    assert docker.run(["image", "ls", "-q", "--filter", f"label={lifecycle.CAPTURE_LABEL}={capture_id}"], check=False, timeout_seconds=30).stdout.split() == []
    assert not snapshot.exists()
