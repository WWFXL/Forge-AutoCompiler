"""Issue #178 opaque build provenance 的 opt-in Ubuntu 原生 Docker 门禁。"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

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
from deerflow.compile.operations import CompileOperationsServices, submit_build_result_impl
from deerflow.compile.paths import (
    get_host_artifacts_dir,
    get_host_logs_dir,
    get_host_repro_dir,
    get_host_workspace_dir,
)
from deerflow.compile.schemas import BuildCommandRecord, utc_now_iso
from deerflow.config.paths import Paths

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
DOCKER_ENABLED = os.getenv("FORGE_RUN_OPAQUE_PROVENANCE_DOCKER") == "1"

pytestmark = pytest.mark.skipif(
    not DOCKER_ENABLED,
    reason="set FORGE_RUN_OPAQUE_PROVENANCE_DOCKER=1 in WSL Ubuntu",
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


adapter = _load_module(
    "forge_opaque_build_provenance_real_docker_adapter",
    "forge_opaque_build_provenance_real_docker_gate.py",
)
lifecycle = _load_module(
    "forge_opaque_build_provenance_real_docker_lifecycle",
    "forge_real_lifecycle_checkpoint_gate.py",
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
        ["docker", "image", "inspect", adapter.COMPILE_IMAGE],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if image.returncode != 0:
        pytest.fail(f"Required image {adapter.COMPILE_IMAGE!r} is unavailable")
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
        workdir=adapter.WORKDIR,
        timeout_seconds=300,
    )
    record = BuildCommandRecord(
        stage="bash",
        command=command,
        workdir=adapter.WORKDIR,
        role=role,
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
        benchmark_id="forge-opaque-provenance-real-docker-gate",
        manifest_sha256="8" * 64,
        case_id=adapter.CASE_ID,
        condition="opaque-build-provenance-zero-provider",
        repetition=1,
        expected_repo_url=adapter.REPOSITORY_URL,
        expected_commit_sha=adapter.COMMIT_SHA,
        expected_build_system="cmake",
        compile_image=adapter.COMPILE_IMAGE,
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
        build_targets=(adapter.TARGET,),
        artifact_instructions=((adapter.STAGED_ARTIFACT, adapter.BUILD_OUTPUT, "executable"),),
    )


def _budget_manifest(capture_id: str, _message_sha256: str) -> dict[str, Any]:
    return lifecycle.budget_checkpoint.build_manifest(
        checkpoint_id=capture_id,
        limits={
            "provider_requests": 1,
            "compiler_invocations": 2,
            "compiler_model_turns": 0,
            "graph_recursion_steps": 8,
            "attempt_wall_clock_seconds": 900,
            "attempt_cleanup_reserve_seconds": 120,
            "compiler_wall_clock_seconds": 720,
            "compiler_post_build_reserve_seconds": 120,
            "post_build_commands": 2,
        },
        consumed_before_capture={
            "provider_requests": 0,
            "compiler_invocations": 1,
            "compiler_model_turns": 0,
            "graph_recursion_steps": 3,
            "attempt_wall_clock_seconds": 10,
            "compiler_wall_clock_seconds": 5,
            "post_build_commands": 0,
            "tokens": 0,
        },
        post_build_started=True,
    )


def _arm_plan(capture_id: str) -> dict[str, dict[str, str]]:
    return {
        arm: {
            "thread_id": f"{arm}-{capture_id}-thread",
            "session_id": f"{arm}-{capture_id}-session",
            "environment_id": f"{arm}-{capture_id}-environment",
        }
        for arm in ("baseline", "treatment")
    }


def _failure_event(ledger: ExperimentLedger) -> dict[str, Any]:
    failures = [event for event in ledger.read() if event["event"] == "failure.recorded"]
    assert len(failures) == 1
    return failures[0]


def _constraint_failures(session: Any) -> list[str]:
    assert session.verification is not None
    benchmark = [check for check in session.verification.checks if check.name == "benchmark_constraints"]
    return [] if not benchmark else list(benchmark[0].actual)


def _feedback(message_runtime: Any, config: dict[str, Any]) -> dict[str, Any]:
    messages = message_runtime.graph.get_state(config).values["messages"]
    return json.loads(messages[-1].content)


def test_real_parent_checkpoint_treatment_replay_and_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter.validate_gate_contract()
    capture_id = f"issue178-{uuid.uuid4().hex[:10]}"
    workspace = tmp_path / "workspace"
    paths = Paths(
        base_dir=tmp_path / ".deer-flow",
        workspace_root=workspace,
        host_workspace_root=str(workspace),
    )
    manager = CompileSessionManager(paths=paths, default_image=adapter.COMPILE_IMAGE)
    runtime = CompileDockerRuntime(manager=manager)
    docker = lifecycle.environment_checkpoint.DockerCLI()
    parent = manager.create_session(
        thread_id=f"parent-{uuid.uuid4().hex[:12]}",
        session_id=f"parent-{uuid.uuid4().hex[:12]}",
        run_id=f"run-{uuid.uuid4().hex[:12]}",
        repo_url=adapter.REPOSITORY_URL,
        image=adapter.COMPILE_IMAGE,
    )
    parent_ledger = ExperimentLedger.create(
        tmp_path / "parent-ledger.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"scope": "issue-178-opaque-provenance-real-docker-gate"},
    )
    active_threads: set[str] = set()
    arm_sessions: list[Any] = []
    continuation_images: set[str] = set()
    known_container_ids: set[str] = set()
    known_replay_container_ids: set[str] = set()
    gate = None
    cleaned = False
    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=runtime),
    )
    try:
        Path(parent.leadagent_repo_dir).mkdir(parents=True, exist_ok=True)
        runtime.create_container(parent)
        manager.save_session(parent)
        assert parent.image_id is not None and parent.container_id is not None
        known_container_ids.add(parent.container_id)
        clone = runtime.exec(
            parent,
            f"git config --global --add safe.directory /workspace/repo && git init . && git remote add origin {adapter.REPOSITORY_URL} && git fetch --depth 1 origin {adapter.COMMIT_SHA} && git checkout --detach FETCH_HEAD",
            workdir=adapter.WORKDIR,
            timeout_seconds=180,
        )
        assert clone.exit_code == 0, clone.combined_output
        parent.commit_sha = adapter.COMMIT_SHA
        parent.build_system = "cmake"
        parent.build_system_capabilities = ["cmake"]
        parent.selected_build_system = "cmake"
        parent.status = "inspected"
        manager.save_session(parent)

        supporting = _record_command(
            manager=manager,
            runtime=runtime,
            session=parent,
            command=adapter.PARENT_COMMAND,
            role="build",
        )
        parent.post_build_supporting_command_id = supporting.command_id
        parent.post_build_started_at = utc_now_iso()
        parent.post_build_commands_remaining = 2
        manager.save_session(parent)

        workspace_artifact = Path(parent.leadagent_repo_dir) / adapter.BUILD_OUTPUT
        build_tree = Path(parent.leadagent_repo_dir) / "build" / "build.ninja"
        assert workspace_artifact.is_file() and build_tree.is_file()
        parent_frozen = adapter.build_frozen_identity(
            image_id=parent.image_id,
            physical_attempt_id=f"{capture_id}-parent",
            build_tree_sha256=lifecycle.sha256_file(build_tree),
            artifact_size=workspace_artifact.stat().st_size,
            artifact_sha256=lifecycle.sha256_file(workspace_artifact),
        )
        parent_p2, _ = adapter.evaluate_parent(
            parent_frozen,
            parent_command_id=supporting.command_id,
        )
        assert parent_p2.reason == "opaque_wrapper"

        activate_experiment(
            thread_id=parent.thread_id,
            experiment_id=parent_ledger.experiment_id,
            physical_attempt_id=parent_ledger.physical_attempt_id,
            ledger=parent_ledger,
            policy=_policy(image_id=parent.image_id),
        )
        active_threads.add(parent.thread_id)
        submit_results: list[str] = []

        def submit_parent() -> str:
            result = submit_build_result_impl(
                session=parent,
                supporting_command_id=supporting.command_id,
            )
            submit_results.append(result)
            return result

        def capture_evidence() -> dict[str, Any]:
            failure = _failure_event(parent_ledger)
            return {
                "classification": failure["payload"]["classification"],
                "failure_id": failure["payload"]["failure_id"],
                "submit_attempt_id": failure["payload"]["submit_attempt_id"],
                "session_sha256": lifecycle.sha256_file(Path(parent.metadata_path)),
                "parent_p2": asdict(parent_p2),
                "parent_command_history_sha256": adapter.provenance.command_history_sha256(
                    adapter.evaluate_parent(
                        parent_frozen,
                        parent_command_id=supporting.command_id,
                    )[1]
                ),
            }

        snapshot = tmp_path / "snapshot"
        coordinator = lifecycle.CaptureCoordinator(tmp_path / "coordinator.sqlite")
        with SqliteSaver.from_conn_string(str(tmp_path / "messages.sqlite")) as saver:
            saver.setup()
            message_runtime = lifecycle.LifecycleMessageRuntime(
                saver,
                submit_parent,
                repair_packet=adapter.build_repair_packet(),
            )
            environment = lifecycle.LifecycleEnvironmentAdapter(
                docker,
                local_snapshot_root=snapshot,
                host_snapshot_root=str(snapshot),
            )
            gate = lifecycle.RealLifecycleCheckpointGate(
                coordinator=coordinator,
                message_runtime=message_runtime,
                environment=environment,
                budget_capture=_budget_manifest,
                manager=manager,
                compile_runtime=runtime,
                owner="issue-178-real-docker-gate",
            )
            capture = gate.capture(
                capture_id=capture_id,
                session=parent,
                instruction="freeze the opaque build provenance failure before continuation",
                arm_plan=_arm_plan(capture_id),
                bind_sources={
                    "workspace": get_host_workspace_dir(
                        parent.session_id,
                        parent.thread_id,
                        paths,
                    ),
                    "artifacts": get_host_artifacts_dir(
                        parent.session_id,
                        parent.thread_id,
                        paths,
                    ),
                    "logs": get_host_logs_dir(
                        parent.session_id,
                        parent.thread_id,
                        paths,
                    ),
                    "repro": get_host_repro_dir(
                        parent.session_id,
                        parent.thread_id,
                        paths,
                    ),
                },
                evidence=capture_evidence,
            )
            continuation_images.add(capture["environment"]["continuation_image_id"])
            parent_payload = json.loads(submit_results[0])
            parent_failure = _failure_event(parent_ledger)["payload"]
            assert parent_payload["status"] == "failed"
            assert parent_payload["candidate_status"] == "failed"
            assert parent_payload["replay_status"] == "not_run"
            assert parent.replay_attempts == []
            assert parent_failure["classification"] == "build_system_unproven"
            assert parent_failure["secondary_classifications"] == []
            assert _constraint_failures(parent) == ["build_system_unproven"]
            deactivate_experiment(parent.thread_id)
            active_threads.remove(parent.thread_id)

            baseline = gate.provision_arm(capture_id, "baseline", parent_session=parent)
            treatment = gate.provision_arm(capture_id, "treatment", parent_session=parent)
            arm_sessions.extend([baseline.session, treatment.session])
            known_container_ids.update(session.container_id for session in arm_sessions if session.container_id is not None)
            assert gate.canonical_arm_environment("baseline") == gate.canonical_arm_environment("treatment")
            assert _feedback(message_runtime, baseline.message_config).get("repair_packet") is None
            treatment_feedback = _feedback(message_runtime, treatment.message_config)
            assert adapter.validate_repair_packet(treatment_feedback["repair_packet"]) == adapter.build_repair_packet()
            assert {key: value for key, value in treatment_feedback.items() if key != "repair_packet"} == _feedback(message_runtime, baseline.message_config)

            assert baseline.session.image_id == treatment.session.image_id
            branch_artifact = Path(treatment.session.leadagent_repo_dir) / adapter.BUILD_OUTPUT
            branch_tree = Path(treatment.session.leadagent_repo_dir) / "build" / "build.ninja"
            branch_frozen = adapter.build_frozen_identity(
                image_id=treatment.session.image_id,
                physical_attempt_id=f"{capture_id}-branches",
                build_tree_sha256=lifecycle.sha256_file(branch_tree),
                artifact_size=branch_artifact.stat().st_size,
                artifact_sha256=lifecycle.sha256_file(branch_artifact),
            )
            baseline_p2, baseline_history = adapter.evaluate_parent(
                branch_frozen,
                parent_command_id=supporting.command_id,
            )
            assert baseline_p2.status == "unproven"

            arm_ledgers: dict[str, ExperimentLedger] = {}
            for arm in (baseline, treatment):
                ledger = ExperimentLedger.create(
                    tmp_path / f"{arm.arm}-ledger.jsonl",
                    experiment_id=new_evidence_id("experiment"),
                    physical_attempt_id=new_evidence_id("physical_attempt"),
                    context={"scope": "issue-178-arm", "arm": arm.arm},
                )
                arm_ledgers[arm.arm] = ledger
                activate_experiment(
                    thread_id=arm.session.thread_id,
                    experiment_id=ledger.experiment_id,
                    physical_attempt_id=ledger.physical_attempt_id,
                    ledger=ledger,
                    policy=_policy(image_id=arm.session.image_id),
                )
                active_threads.add(arm.session.thread_id)

            baseline_payload = json.loads(
                submit_build_result_impl(
                    session=baseline.session,
                    supporting_command_id=supporting.command_id,
                )
            )
            assert baseline_payload["status"] == "failed"
            assert baseline_payload["replay_status"] == "not_run"
            assert baseline.session.replay_attempts == []
            assert _failure_event(arm_ledgers["baseline"])["payload"]["classification"] == "build_system_unproven"
            assert _constraint_failures(baseline.session) == ["build_system_unproven"]

            treatment_build = _record_command(
                manager=manager,
                runtime=runtime,
                session=treatment.session,
                command=adapter.TREATMENT_BUILD_COMMAND,
                role="build",
            )
            treatment_stage = _record_command(
                manager=manager,
                runtime=runtime,
                session=treatment.session,
                command=adapter.TREATMENT_STAGE_COMMAND,
                role="artifact_stage",
            )
            assert branch_artifact.stat().st_size == branch_frozen.artifact_size
            assert lifecycle.sha256_file(branch_artifact) == branch_frozen.artifact_sha256
            treatment_p2, treatment_history = adapter.evaluate_treatment(
                branch_frozen,
                parent_command_id=supporting.command_id,
                treatment_build_command_id=treatment_build.command_id,
                treatment_stage_command_id=treatment_stage.command_id,
            )
            assert treatment_p2.status == "proven"
            assert treatment_history[: len(baseline_history)] == baseline_history

            treatment_payload = json.loads(
                submit_build_result_impl(
                    session=treatment.session,
                    supporting_command_id=treatment_build.command_id,
                )
            )
            assert treatment_payload["status"] == "passed", treatment_payload
            assert treatment_payload["candidate_status"] == "passed"
            assert treatment_payload["replay_status"] == "passed"
            assert len(treatment.session.replay_attempts) == 1
            replay = treatment.session.replay_attempts[0]
            assert replay.status == "passed" and replay.cleanup_succeeded is True
            if replay.container_id is not None:
                known_replay_container_ids.add(replay.container_id)

            for thread_id in tuple(active_threads):
                deactivate_experiment(thread_id)
                active_threads.remove(thread_id)
            record = gate.cleanup(capture_id, parent_session=parent)
            cleaned = True
            assert record.phase == "cleaned"
            assert record.payload["cleanup"]["succeeded"] is True
            assert gate.external_counts() == {
                "provider_calls": 0,
                "formal_physical_attempts": 0,
                "model_tokens": 0,
            }
    finally:
        for thread_id in tuple(active_threads):
            deactivate_experiment(thread_id)
        if gate is not None and not cleaned:
            try:
                gate.cleanup(capture_id, parent_session=parent)
            except Exception:
                pass
        for session in arm_sessions:
            runtime.stop_and_remove_container(session)
        runtime.stop_and_remove_container(parent)
        for container_id in docker.run(
            ["ps", "-aq", "--filter", f"label={lifecycle.CAPTURE_LABEL}={capture_id}"],
            check=False,
            timeout_seconds=30,
        ).stdout.split():
            docker.run(["rm", "-f", container_id], check=False, timeout_seconds=30)
        continuation_images.update(
            docker.run(
                [
                    "image",
                    "ls",
                    "-q",
                    "--filter",
                    f"label={lifecycle.CAPTURE_LABEL}={capture_id}",
                ],
                check=False,
                timeout_seconds=30,
            ).stdout.split()
        )
        for image_id in continuation_images:
            docker.run(["image", "rm", "-f", image_id], check=False, timeout_seconds=60)

    for container_id in known_container_ids | known_replay_container_ids:
        assert (
            docker.run(
                ["container", "inspect", container_id],
                check=False,
                timeout_seconds=20,
            ).returncode
            != 0
        )
    assert (
        docker.run(
            ["ps", "-aq", "--filter", f"label={lifecycle.CAPTURE_LABEL}={capture_id}"],
            check=False,
            timeout_seconds=30,
        ).stdout.split()
        == []
    )
    assert (
        docker.run(
            [
                "image",
                "ls",
                "-q",
                "--filter",
                f"label={lifecycle.CAPTURE_LABEL}={capture_id}",
            ],
            check=False,
            timeout_seconds=30,
        ).stdout.split()
        == []
    )
