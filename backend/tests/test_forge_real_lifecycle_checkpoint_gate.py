from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from deerflow.compile.manager import CompileSessionManager
from deerflow.config.paths import Paths

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
MODULE_PATH = SCRIPTS_DIR / "forge_real_lifecycle_checkpoint_gate.py"
IMAGE_ID = "sha256:" + "1" * 64


def _load_module():
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location("forge_real_lifecycle_checkpoint_gate_test", MODULE_PATH)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


gate_module = _load_module()


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeDockerRunner:
    def __init__(self) -> None:
        self.paused: set[str] = set()
        self.images: set[str] = set()
        self.containers: set[str] = set()
        self.archives: dict[str, Path] = {}
        self.calls: list[list[str]] = []

    @staticmethod
    def _mounts(command: list[str]) -> dict[str, str]:
        mounts: dict[str, str] = {}
        for index, item in enumerate(command):
            if item != "--mount":
                continue
            values = dict(part.split("=", 1) for part in command[index + 1].split(",") if "=" in part)
            mounts[values["dst"]] = values["src"]
        return mounts

    def run(
        self,
        args: list[str],
        *,
        check: bool = True,
        timeout_seconds: int | float | None = None,
    ) -> SimpleNamespace:
        del timeout_seconds
        command = list(args)
        self.calls.append(command)
        if command[0] == "pause":
            self.paused.add(command[1])
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[0] == "unpause":
            self.paused.discard(command[1])
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[:3] == ["inspect", "--format", "{{.State.Paused}}"]:
            return SimpleNamespace(
                returncode=0,
                stdout="true\n" if command[3] in self.paused else "false\n",
                stderr="",
            )
        if command[0] == "commit":
            self.images.add(IMAGE_ID)
            return SimpleNamespace(returncode=0, stdout=IMAGE_ID + "\n", stderr="")
        if command[:3] == ["image", "ls", "-q"]:
            return SimpleNamespace(returncode=0, stdout="\n".join(sorted(self.images)), stderr="")
        if command[:3] == ["image", "rm", "-f"]:
            self.images.discard(command[3])
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[:2] == ["rm", "-f"]:
            self.containers.discard(command[2])
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[0] == "run":
            name = command[command.index("--name") + 1]
            mounts = self._mounts(command)
            script = command[-1]
            if " -cpf " in script:
                archive_name = script.split("/snapshot/", 1)[1].split(" ", 1)[0]
                role = Path(archive_name).stem
                source = Path(mounts["/source"])
                snapshot = Path(mounts["/snapshot"])
                snapshot.mkdir(parents=True, exist_ok=True)
                (snapshot / archive_name).write_bytes((role + "-archive").encode("ascii"))
                self.archives[archive_name] = source
            elif " -xpf " in script:
                archive_name = script.split("/snapshot/", 1)[1].split(" ", 1)[0]
                source = self.archives[archive_name]
                target = Path(mounts["/target"])
                shutil.copytree(source, target, dirs_exist_ok=True, symlinks=True)
            self.containers.discard(name)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if check:
            raise AssertionError(f"unexpected fake Docker command: {command}")
        return SimpleNamespace(returncode=1, stdout="", stderr="not found")


class FakeCompileRuntime:
    def __init__(self, runner: FakeDockerRunner) -> None:
        self.runner = runner
        self.created = 0

    def create_container(self, session) -> str:
        self.created += 1
        session.container_name = f"deerflow-compile-{session.thread_id[:8]}-{session.session_id[:8]}"
        session.container_id = session.container_name
        session.image_id = session.image
        self.runner.containers.add(session.container_name)
        return session.container_id


def _budget_manifest(capture_id: str, _message_sha256: str) -> dict:
    return gate_module.budget_checkpoint.build_manifest(
        checkpoint_id=capture_id,
        limits={
            "provider_requests": 8,
            "compiler_invocations": 3,
            "compiler_model_turns": 12,
            "graph_recursion_steps": 48,
            "attempt_wall_clock_seconds": 200,
            "attempt_cleanup_reserve_seconds": 20,
            "compiler_wall_clock_seconds": 100,
            "compiler_post_build_reserve_seconds": 20,
            "post_build_commands": 3,
        },
        consumed_before_capture={
            "provider_requests": 5,
            "compiler_invocations": 1,
            "compiler_model_turns": 7,
            "graph_recursion_steps": 30,
            "attempt_wall_clock_seconds": 40,
            "compiler_wall_clock_seconds": 60,
            "post_build_commands": 1,
            "tokens": 12345,
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


def test_arm_plan_rejects_compile_container_name_collision() -> None:
    capture_id = "capture-collision"
    plan = _arm_plan(capture_id)
    plan["baseline"]["thread_id"] = f"shared-prefix-baseline-{capture_id}"
    plan["baseline"]["session_id"] = f"shared-prefix-baseline-{capture_id}"
    plan["treatment"]["thread_id"] = f"shared-prefix-treatment-{capture_id}"
    plan["treatment"]["session_id"] = f"shared-prefix-treatment-{capture_id}"

    with pytest.raises(
        gate_module.LifecycleGateError,
        match="CompileDockerRuntime truncation",
    ):
        gate_module.validate_arm_plan(plan)


def _manager_and_parent(tmp_path: Path):
    workspace = tmp_path / "workspace"
    paths = Paths(
        base_dir=tmp_path / ".deer-flow",
        workspace_root=workspace,
        host_workspace_root=str(workspace),
    )
    manager = CompileSessionManager(paths=paths)
    session = manager.create_session(
        thread_id="parent-thread",
        session_id="parent-session",
        run_id="parent-run",
        repo_url="https://example.invalid/repo.git",
    )
    session.container_id = "parent-container"
    session.container_name = "parent-container"
    session.image_id = IMAGE_ID
    session.status = "verification_failed"
    session.commit_sha = "a" * 40
    session.build_system = "make"
    session.selected_build_system = "make"
    session.executed_build_system = "make"
    Path(session.leadagent_repo_dir).mkdir(parents=True, exist_ok=True)
    (Path(session.leadagent_repo_dir) / "source.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    (Path(session.leadagent_artifacts_dir) / "bad.txt").write_text("not compiled\n", encoding="utf-8")
    (Path(session.leadagent_logs_dir) / "submit.log").write_text("failed\n", encoding="utf-8")
    (Path(session.leadagent_repro_dir) / "build.sh").write_text("exit 1\n", encoding="utf-8")
    manager.save_session(session)
    return manager, session


def _bind_sources(session) -> dict[str, str]:
    return {
        "workspace": str(Path(session.leadagent_repo_dir).parent),
        "artifacts": session.leadagent_artifacts_dir,
        "logs": session.leadagent_logs_dir,
        "repro": session.leadagent_repro_dir,
    }


def _make_gate(tmp_path: Path, saver, manager, runner, submit_callback, *, clock=None):
    capture_id = "lifecycle-fixture"
    snapshot = tmp_path / "snapshot"
    coordinator = gate_module.CaptureCoordinator(
        tmp_path / "coordinator.sqlite",
        clock=clock or (lambda: 1000.0),
    )
    message = gate_module.LifecycleMessageRuntime(
        saver,
        submit_callback,
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
    compile_runtime = FakeCompileRuntime(runner)
    gate = gate_module.RealLifecycleCheckpointGate(
        coordinator=coordinator,
        message_runtime=message,
        environment=environment,
        budget_capture=_budget_manifest,
        manager=manager,
        compile_runtime=compile_runtime,
        owner="coordinator-main",
    )
    return capture_id, gate, coordinator, compile_runtime


def _evidence() -> dict[str, str | int]:
    return {
        "submit_attempt_id": "submit-123",
        "session_sha256": "2" * 64,
        "ledger_sequence": 7,
        "ledger_head_sha256": "3" * 64,
    }


def test_coordinator_enforces_lease_cas_and_transition_order(tmp_path: Path) -> None:
    clock = FakeClock()
    coordinator = gate_module.CaptureCoordinator(tmp_path / "state.sqlite", clock=clock)
    coordinator.create("capture-state", {"identity": "one"})
    coordinator.acquire("capture-state", "owner-one", ttl_seconds=10)

    with pytest.raises(gate_module.LifecycleGateError, match="owned by another"):
        coordinator.acquire("capture-state", "owner-two")
    with pytest.raises(gate_module.LifecycleGateError, match="illegal capture transition"):
        coordinator.update(
            "capture-state",
            "owner-one",
            expected_phase="preparing",
            target_phase="committed",
        )

    clock.advance(11)
    record = coordinator.acquire("capture-state", "owner-two")
    assert record.lease_owner == "owner-two"
    record = coordinator.update(
        "capture-state",
        "owner-two",
        expected_phase="preparing",
        target_phase="message_frozen",
    )
    assert record.phase == "message_frozen"


def test_full_gate_commits_and_provisions_equal_isolated_arms(tmp_path: Path) -> None:
    manager, parent = _manager_and_parent(tmp_path)
    runner = FakeDockerRunner()
    submit_count = 0

    def submit() -> str:
        nonlocal submit_count
        submit_count += 1
        return json.dumps(
            {
                "status": "failed",
                "submit_attempt_id": "submit-123",
                "message": "Error: Verification failed.",
            }
        )

    with SqliteSaver.from_conn_string(str(tmp_path / "messages.sqlite")) as saver:
        saver.setup()
        capture_id, gate, coordinator, compile_runtime = _make_gate(
            tmp_path,
            saver,
            manager,
            runner,
            submit,
        )
        manifest = gate.capture(
            capture_id=capture_id,
            session=parent,
            instruction="continue a deterministic failed build",
            arm_plan=_arm_plan(capture_id),
            bind_sources=_bind_sources(parent),
            evidence=_evidence(),
        )
        assert coordinator.get(capture_id).phase == "committed"
        assert manifest["manifest_sha256"] == gate_module.manifest_payload_sha256(manifest)
        assert submit_count == 1
        assert not runner.paused

        baseline = gate.provision_arm(capture_id, "baseline", parent_session=parent)
        treatment = gate.provision_arm(capture_id, "treatment", parent_session=parent)
        assert compile_runtime.created == 2
        assert baseline.session.session_id != treatment.session.session_id
        assert gate.canonical_arm_environment("baseline") == gate.canonical_arm_environment("treatment")

        baseline_file = Path(baseline.session.leadagent_repo_dir) / "baseline-only.txt"
        baseline_file.write_text("baseline\n", encoding="utf-8")
        assert not (Path(treatment.session.leadagent_repo_dir) / baseline_file.name).exists()
        baseline.budget.claim("provider_requests")
        assert treatment.budget.snapshot()["remaining"]["provider_requests"] == 3

        baseline_state = gate.message_runtime.graph.get_state(baseline.message_config).values
        treatment_state = gate.message_runtime.graph.get_state(treatment.message_config).values
        assert "repair_packet" not in json.loads(baseline_state["messages"][-1].content)
        assert "repair_packet" in json.loads(treatment_state["messages"][-1].content)
        assert gate.external_counts() == {
            "provider_calls": 0,
            "formal_physical_attempts": 0,
            "model_tokens": 0,
        }


@pytest.mark.parametrize(
    ("crash_after", "expected_phase"),
    [
        ("message_frozen", "cleaned"),
        ("pause", "cleaned"),
        ("commit", "cleaned"),
        ("workspace_archive", "cleaned"),
        ("environment_frozen", "committed"),
        ("budget_frozen", "committed"),
        ("combined_published", "committed"),
    ],
)
def test_crash_reconciliation_never_repeats_submit_or_leaves_parent_paused(
    tmp_path: Path,
    crash_after: str,
    expected_phase: str,
) -> None:
    manager, parent = _manager_and_parent(tmp_path)
    runner = FakeDockerRunner()
    submit_count = 0

    def submit() -> str:
        nonlocal submit_count
        submit_count += 1
        return json.dumps({"status": "failed", "submit_attempt_id": "submit-123"})

    with SqliteSaver.from_conn_string(str(tmp_path / "messages.sqlite")) as saver:
        saver.setup()
        capture_id, gate, coordinator, _runtime = _make_gate(
            tmp_path,
            saver,
            manager,
            runner,
            submit,
        )
        with pytest.raises(gate_module.SimulatedCrash):
            gate.capture(
                capture_id=capture_id,
                session=parent,
                instruction="capture before continuation",
                arm_plan=_arm_plan(capture_id),
                bind_sources=_bind_sources(parent),
                evidence=_evidence(),
                crash_after=crash_after,
            )
        recovered = gate.reconcile(capture_id)
        assert recovered.phase == expected_phase
        assert submit_count == 1
        assert not runner.paused
        if expected_phase == "cleaned":
            assert runner.images == set()
            assert not (tmp_path / "snapshot").exists()


@pytest.mark.parametrize("crash_after", ["arm_session", "arm_container"])
def test_partial_arm_is_cleaned_and_can_be_provisioned_again(tmp_path: Path, crash_after: str) -> None:
    manager, parent = _manager_and_parent(tmp_path)
    runner = FakeDockerRunner()
    with SqliteSaver.from_conn_string(str(tmp_path / "messages.sqlite")) as saver:
        saver.setup()
        capture_id, gate, coordinator, _runtime = _make_gate(
            tmp_path,
            saver,
            manager,
            runner,
            lambda: json.dumps({"status": "failed", "submit_attempt_id": "submit-123"}),
        )
        gate.capture(
            capture_id=capture_id,
            session=parent,
            instruction="capture before continuation",
            arm_plan=_arm_plan(capture_id),
            bind_sources=_bind_sources(parent),
            evidence=_evidence(),
        )
        with pytest.raises(gate_module.SimulatedCrash):
            gate.provision_arm(
                capture_id,
                "baseline",
                parent_session=parent,
                crash_after=crash_after,
            )

        record = gate.reconcile(capture_id)
        assert record.payload["arms"]["baseline"]["status"] == "planned"
        arm = gate.provision_arm(capture_id, "baseline", parent_session=parent)
        assert arm.session.container_id in runner.containers
        assert coordinator.get(capture_id).payload["arms"]["baseline"]["status"] == "ready"


def test_cold_restore_derives_arms_without_repeating_submit(tmp_path: Path) -> None:
    manager, parent = _manager_and_parent(tmp_path)
    runner = FakeDockerRunner()
    database = tmp_path / "messages.sqlite"
    with SqliteSaver.from_conn_string(str(database)) as saver:
        saver.setup()
        capture_id, gate, _coordinator, _runtime = _make_gate(
            tmp_path,
            saver,
            manager,
            runner,
            lambda: json.dumps({"status": "failed", "submit_attempt_id": "submit-123"}),
        )
        gate.capture(
            capture_id=capture_id,
            session=parent,
            instruction="capture before continuation",
            arm_plan=_arm_plan(capture_id),
            bind_sources=_bind_sources(parent),
            evidence=_evidence(),
        )

    with SqliteSaver.from_conn_string(str(database)) as saver:
        saver.setup()

        def forbidden_submit() -> str:
            pytest.fail("cold restore must not repeat the parent submit")

        capture_id, restored, _coordinator, _runtime = _make_gate(
            tmp_path,
            saver,
            manager,
            runner,
            forbidden_submit,
        )
        assert restored.reconcile(capture_id).phase == "committed"
        arms = restored.derive_message_arms(capture_id)
        assert set(arms) == {"baseline", "treatment"}
        assert restored.message_runtime.submit_calls == 0


def test_gate_source_does_not_import_provider_or_formal_runner() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "deerflow.models" not in source
    assert "forge_benchmark_runner" not in source
    assert "forge_verifier_repair_authorized_runner" not in source
