"""Issue #143 的 opt-in Ubuntu 原生 Docker 生命周期门禁。"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
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
MODULE_PATH = SCRIPTS_DIR / "forge_real_lifecycle_checkpoint_gate.py"
COMPILE_IMAGE = "autocompiler:gcc13"
DOCKER_INTEGRATION_ENABLED = os.getenv("FORGE_RUN_DOCKER_INTEGRATION") == "1"

pytestmark = pytest.mark.skipif(
    not DOCKER_INTEGRATION_ENABLED,
    reason="set FORGE_RUN_DOCKER_INTEGRATION=1 to run the real lifecycle Docker gate",
)


def _load_module():
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location("forge_real_lifecycle_checkpoint_gate_docker", MODULE_PATH)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


gate_module = _load_module()


@pytest.fixture(scope="module", autouse=True)
def require_docker_and_compile_image():
    if not DOCKER_INTEGRATION_ENABLED:
        yield
        return
    if shutil.which("docker") is None:
        pytest.fail("FORGE_RUN_DOCKER_INTEGRATION=1 requires the docker CLI")
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
    return gate_module.budget_checkpoint.build_manifest(
        checkpoint_id=capture_id,
        limits={
            "provider_requests": 4,
            "compiler_invocations": 2,
            "compiler_model_turns": 8,
            "graph_recursion_steps": 32,
            "attempt_wall_clock_seconds": 600,
            "attempt_cleanup_reserve_seconds": 60,
            "compiler_wall_clock_seconds": 300,
            "compiler_post_build_reserve_seconds": 60,
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


def test_real_submit_capture_restore_and_cleanup_has_no_orphans(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    capture_id = f"lifecycle-{uuid.uuid4().hex[:12]}"
    workspace = tmp_path / "workspace"
    paths = Paths(
        base_dir=tmp_path / ".deer-flow",
        workspace_root=workspace,
        host_workspace_root=str(workspace),
    )
    manager = CompileSessionManager(paths=paths, default_image=COMPILE_IMAGE)
    runtime = CompileDockerRuntime(manager=manager)
    runner = gate_module.environment_checkpoint.DockerCLI()
    session = manager.create_session(
        thread_id=f"parent-{uuid.uuid4().hex[:12]}",
        session_id=f"parent-{uuid.uuid4().hex[:12]}",
        run_id=f"run-{uuid.uuid4().hex[:12]}",
        repo_url="https://example.invalid/synthetic.git",
        image=COMPILE_IMAGE,
    )
    ledger = ExperimentLedger.create(
        tmp_path / "synthetic-lifecycle-ledger.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"scope": "issue-143-non-provider-docker-gate"},
    )
    active = False
    continuation_images: set[str] = set()
    arm_sessions = []
    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=runtime),
    )
    try:
        runtime.create_container(session)
        manager.save_session(session)
        assert session.image_id is not None
        policy = ExperimentPolicy(
            benchmark_id="forge-real-lifecycle-checkpoint-gate",
            manifest_sha256="4" * 64,
            case_id="synthetic-no-artifact",
            condition="non-provider-integration",
            repetition=1,
            expected_repo_url=session.repo_url,
            expected_commit_sha="a" * 40,
            expected_build_system="make",
            compile_image=COMPILE_IMAGE,
            image_id=session.image_id,
            model_name="deterministic-no-provider",
            endpoint="https://example.invalid/v1",
            credential_env="UNUSED_PROVIDER_KEY",
            request_timeout_seconds=1,
            model_max_retries=0,
            compiler_max_turns=8,
            subagent_timeout_seconds=300,
            memory_enabled=False,
            skills_enabled=False,
            required_system_packages=(),
            cmake_arguments=(),
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

        session.commit_sha = "a" * 40
        session.build_system = "make"
        session.build_system_capabilities = ["make"]
        session.selected_build_system = "make"
        Path(session.leadagent_repo_dir).mkdir(parents=True, exist_ok=True)
        (Path(session.leadagent_repo_dir) / "source.c").write_text(
            "int main(void) { return 0; }\n",
            encoding="utf-8",
        )
        rootfs_seed = runtime.exec(
            session,
            "mkdir -p /opt/forge-checkpoint && printf 'parent-state\\n' > /opt/forge-checkpoint/state",
            workdir="/workspace",
            timeout_seconds=30,
        )
        assert rootfs_seed.exit_code == 0, rootfs_seed.combined_output
        supporting = BuildCommandRecord(
            stage="bash",
            command="make --version",
            workdir="/workspace/repo",
            role="build",
            exit_code=0,
            completed_at=utc_now_iso(),
        )
        manager.record_command(session, supporting)
        manager.save_session(session)

        submit_results: list[str] = []

        def submit() -> str:
            result = submit_build_result_impl(
                session=session,
                supporting_command_id=supporting.command_id,
            )
            submit_results.append(result)
            return result

        def evidence() -> dict:
            events = ledger.read()
            submit_event = next(item for item in reversed(events) if item["event"] == "submit.completed")
            failure_event = next(item for item in reversed(events) if item["event"] == "failure.recorded")
            metadata = Path(session.metadata_path)
            return {
                "submit_attempt_id": submit_event["payload"]["submit_attempt_id"],
                "failure_id": failure_event["payload"]["failure_id"],
                "session_sha256": gate_module.sha256_file(metadata),
                "ledger_sequence": events[-1]["sequence"],
                "ledger_head_sha256": events[-1]["event_sha256"],
            }

        snapshot = tmp_path / "snapshot"
        coordinator = gate_module.CaptureCoordinator(tmp_path / "coordinator.sqlite")
        with SqliteSaver.from_conn_string(str(tmp_path / "messages.sqlite")) as saver:
            saver.setup()
            message_runtime = gate_module.LifecycleMessageRuntime(
                saver,
                submit,
                repair_packet={
                    "schema_version": "forge-verifier-repair-packet-1.0.0",
                    "primary_classification": "candidate_verification_failed",
                },
            )
            environment = gate_module.LifecycleEnvironmentAdapter(
                runner,
                local_snapshot_root=snapshot,
                host_snapshot_root=str(snapshot),
            )
            gate = gate_module.RealLifecycleCheckpointGate(
                coordinator=coordinator,
                message_runtime=message_runtime,
                environment=environment,
                budget_capture=_budget_manifest,
                manager=manager,
                compile_runtime=runtime,
                owner="coordinator-docker",
            )
            manifest = gate.capture(
                capture_id=capture_id,
                session=session,
                instruction="freeze a synthetic actionable failure before continuation",
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
            assert json.loads(submit_results[0])["status"] == "failed"
            assert coordinator.get(capture_id).phase == "committed"
            assert message_runtime.continuation_calls == 0

            baseline = gate.provision_arm(capture_id, "baseline", parent_session=session)
            arm_sessions.append(baseline.session)
            treatment = gate.provision_arm(capture_id, "treatment", parent_session=session)
            arm_sessions.append(treatment.session)
            assert gate.canonical_arm_environment("baseline") == gate.canonical_arm_environment("treatment")

            treatment_rootfs = runtime.exec(
                treatment.session,
                "cat /opt/forge-checkpoint/state",
                workdir="/workspace",
                timeout_seconds=30,
            )
            assert treatment_rootfs.exit_code == 0
            assert treatment_rootfs.stdout.strip() == "parent-state"
            baseline_write = runtime.exec(
                baseline.session,
                "printf 'baseline-rootfs\\n' > /opt/forge-checkpoint/state && printf 'baseline-workspace\\n' > /workspace/repo/arm-only.txt",
                workdir="/workspace",
                timeout_seconds=30,
            )
            assert baseline_write.exit_code == 0
            treatment_isolated = runtime.exec(
                treatment.session,
                'test "$(cat /opt/forge-checkpoint/state)" = parent-state && test ! -e /workspace/repo/arm-only.txt',
                workdir="/workspace",
                timeout_seconds=30,
            )
            assert treatment_isolated.exit_code == 0, treatment_isolated.combined_output

            cleaned = gate.cleanup(capture_id, parent_session=session)
            assert cleaned.phase == "cleaned"
            assert cleaned.payload["cleanup"]["succeeded"] is True
            assert gate.external_counts() == {
                "provider_calls": 0,
                "formal_physical_attempts": 0,
                "model_tokens": 0,
            }
    finally:
        if active:
            deactivate_experiment(session.thread_id)
        for arm_session in arm_sessions:
            runtime.stop_and_remove_container(arm_session)
        runtime.stop_and_remove_container(session)
        capture_containers = runner.run(
            [
                "ps",
                "-aq",
                "--filter",
                f"label={gate_module.CAPTURE_LABEL}={capture_id}",
            ],
            check=False,
            timeout_seconds=30,
        ).stdout.split()
        for container_id in capture_containers:
            runner.run(["rm", "-f", container_id], check=False, timeout_seconds=30)
        for role in ("workspace", "artifacts", "logs", "repro"):
            runner.run(
                ["rm", "-f", f"forge-checkpoint-{capture_id}-{role}"],
                check=False,
                timeout_seconds=20,
            )
            for arm in ("baseline", "treatment"):
                runner.run(
                    ["rm", "-f", f"forge-checkpoint-{capture_id}-{arm}-{role}"],
                    check=False,
                    timeout_seconds=20,
                )
        for image_id in continuation_images | set(
            runner.run(
                ["image", "ls", "-q", "--filter", f"label={gate_module.CAPTURE_LABEL}={capture_id}"],
                check=False,
                timeout_seconds=30,
            ).stdout.split()
        ):
            runner.run(["image", "rm", "-f", image_id], check=False, timeout_seconds=60)

    residual_containers = runner.run(
        ["ps", "-aq", "--filter", f"label={gate_module.CAPTURE_LABEL}={capture_id}"],
        check=False,
        timeout_seconds=30,
    ).stdout.split()
    residual_images = runner.run(
        ["image", "ls", "-q", "--filter", f"label={gate_module.CAPTURE_LABEL}={capture_id}"],
        check=False,
        timeout_seconds=30,
    ).stdout.split()
    assert residual_containers == []
    assert residual_images == []
    assert not snapshot.exists()
