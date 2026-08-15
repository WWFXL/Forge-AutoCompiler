from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
PROTOTYPE_PATH = SCRIPTS_DIR / "forge_combined_checkpoint_prototype.py"
FIXTURE_PATH = REPO_ROOT / "benchmarks" / "fixtures" / "failure-checkpoints" / "slot-007-openthread.json"


def _load_module():
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location("forge_combined_checkpoint_prototype_test", PROTOTYPE_PATH)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


prototype = _load_module()


def _fixture():
    return prototype.message_checkpoint.load_fixture(FIXTURE_PATH)


def _arm_plan(capture_id: str):
    return {
        "baseline": {
            "thread_id": f"{capture_id}-baseline-thread",
            "session_id": f"{capture_id}-baseline-session",
            "environment_id": f"{capture_id}-baseline-environment",
        },
        "treatment": {
            "thread_id": f"{capture_id}-treatment-thread",
            "session_id": f"{capture_id}-treatment-session",
            "environment_id": f"{capture_id}-treatment-environment",
        },
    }


def _environment_manifest(capture_id: str):
    image_id = "sha256:" + "1" * 64
    plan = _arm_plan(capture_id)
    manifest = {
        "schema_version": prototype.environment_checkpoint.SCHEMA_VERSION,
        "manifest_sha256": "",
        "run_id": capture_id,
        "capture_method": "explicit-pause+docker-commit+bind-tar",
        "base_image_id": image_id,
        "continuation_image_id": image_id,
        "rootfs": {
            "sentinel_path": prototype.environment_checkpoint.ROOTFS_SENTINEL,
            "content_sha256": "2" * 64,
        },
        "bind_mounts": {
            "workspace": {"archive_sha256": "3" * 64, "entries": []},
            "artifacts": {"archive_sha256": "4" * 64, "entries": []},
        },
        "identities": {
            "parent": f"{capture_id}-parent-environment",
            "baseline": plan["baseline"]["environment_id"],
            "treatment": plan["treatment"]["environment_id"],
        },
        "budget": {"reconstructed": False, "scope": "deferred-separate-gate"},
    }
    manifest["manifest_sha256"] = prototype.environment_checkpoint.checkpoint_payload_sha256(manifest)
    return prototype.environment_checkpoint.validate_checkpoint_manifest(manifest)


def _budget_manifest(capture_id: str):
    return prototype.budget_checkpoint.build_manifest(
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


def _callbacks(capture_id: str, events: list[tuple]):
    def capture_environment(observed_capture_id: str, message_sha256: str):
        events.append(("environment", observed_capture_id, message_sha256))
        return _environment_manifest(capture_id)

    def capture_budget(observed_capture_id: str, message_sha256: str):
        events.append(("budget", observed_capture_id, message_sha256))
        return _budget_manifest(capture_id)

    return capture_environment, capture_budget


def test_atomic_capture_binds_three_components_after_message_pause(tmp_path: Path) -> None:
    capture_id = "combined-fixture"
    events: list[tuple] = []
    counters = prototype.message_checkpoint.PrototypeCounters()
    environment_capture, budget_capture = _callbacks(capture_id, events)

    with SqliteSaver.from_conn_string(str(tmp_path / "combined.sqlite")) as saver:
        saver.setup()
        runtime = prototype.CombinedCheckpointPrototype(
            _fixture(),
            saver,
            environment_capture=environment_capture,
            budget_capture=budget_capture,
            counters=counters,
        )
        manifest = runtime.capture(capture_id, _arm_plan(capture_id))

        assert [event[0] for event in events] == ["environment", "budget"]
        assert {event[1] for event in events} == {capture_id}
        assert len({event[2] for event in events}) == 1
        assert counters.submit_calls == 1
        assert counters.fake_model_calls == 0
        assert manifest["components"]["message"]["canonical_state_sha256"] == events[0][2]
        assert manifest["manifest_sha256"] == "bb1f6f4da5868e2e33ef1caf8c34a4645fc06641b5577669edf94f75f8449738"
        assert manifest["manifest_sha256"] == prototype.manifest_payload_sha256(manifest)


@pytest.mark.parametrize("failing_component", ["environment", "budget"])
def test_capture_failure_does_not_publish_parent_or_derive_arm(tmp_path: Path, failing_component: str) -> None:
    capture_id = f"combined-fail-{failing_component}"
    events: list[tuple] = []

    def fail(_capture_id: str, _message_sha256: str):
        raise prototype.CombinedCheckpointError(f"synthetic {failing_component} failure")

    environment_capture, budget_capture = _callbacks(capture_id, events)
    if failing_component == "environment":
        environment_capture = fail
    else:
        budget_capture = fail

    with SqliteSaver.from_conn_string(str(tmp_path / f"{failing_component}.sqlite")) as saver:
        saver.setup()
        runtime = prototype.CombinedCheckpointPrototype(
            _fixture(),
            saver,
            environment_capture=environment_capture,
            budget_capture=budget_capture,
        )
        with pytest.raises(prototype.CombinedCheckpointError, match=f"synthetic {failing_component}"):
            runtime.capture(capture_id, _arm_plan(capture_id))

        assert runtime.combined_manifest is None
        assert runtime.arms == {}
        assert runtime.counters.submit_calls == 1
        assert runtime.counters.fake_model_calls == 0
        assert runtime.external_counts() == {
            "provider_calls": 0,
            "docker_calls": 0,
            "formal_physical_attempts": 0,
            "model_tokens": 0,
        }


def test_cold_restore_derives_equal_isolated_arms_and_resumes_once(tmp_path: Path) -> None:
    capture_id = "combined-cold-restore"
    database = tmp_path / "combined.sqlite"
    events: list[tuple] = []
    counters = prototype.message_checkpoint.PrototypeCounters()
    environment_capture, budget_capture = _callbacks(capture_id, events)

    with SqliteSaver.from_conn_string(str(database)) as saver:
        saver.setup()
        runtime = prototype.CombinedCheckpointPrototype(
            _fixture(),
            saver,
            environment_capture=environment_capture,
            budget_capture=budget_capture,
            counters=counters,
        )
        manifest = runtime.capture(capture_id, _arm_plan(capture_id))
        environment_manifest = copy.deepcopy(runtime.environment_manifest)
        budget_manifest = copy.deepcopy(runtime.budget_manifest)

    assert environment_manifest is not None
    assert budget_manifest is not None
    with SqliteSaver.from_conn_string(str(database)) as saver:
        saver.setup()
        restored = prototype.CombinedCheckpointPrototype(
            _fixture(),
            saver,
            environment_capture=lambda *_args: pytest.fail("cold restore must not recapture environment"),
            budget_capture=lambda *_args: pytest.fail("cold restore must not recapture budget"),
            counters=counters,
        )
        restored.restore_parent(
            combined_manifest=manifest,
            environment_manifest=environment_manifest,
            budget_manifest=budget_manifest,
        )
        baseline = restored.derive_arm("baseline")
        treatment = restored.derive_arm("treatment")

        assert restored.canonical_initial_state("baseline") == restored.canonical_initial_state("treatment")
        assert baseline.session_id != treatment.session_id
        assert baseline.environment.identity != treatment.environment.identity

        parent_environment_before = copy.deepcopy(restored.environment_manifest)
        baseline.environment.write("workspace", "repo/generated.txt", "baseline")
        baseline.budget.claim("provider_requests")
        assert treatment.environment.workspace_overlay == {}
        assert treatment.budget.snapshot()["remaining"]["provider_requests"] == 3
        assert restored.environment_manifest == parent_environment_before

        restored.resume_arm("baseline")
        restored.resume_arm("treatment")
        with pytest.raises(prototype.CombinedCheckpointError, match="already resumed"):
            restored.resume_arm("baseline")

        assert counters.submit_calls == 1
        assert counters.fake_model_calls == 2
        assert baseline.budget.snapshot()["remaining"]["compiler_model_turns"] == 4
        assert treatment.budget.snapshot()["remaining"]["compiler_model_turns"] == 4
        assert restored.external_counts() == {
            "provider_calls": 0,
            "docker_calls": 0,
            "formal_physical_attempts": 0,
            "model_tokens": 0,
        }


@pytest.mark.parametrize("drift", ["combined", "message", "environment", "budget"])
def test_component_drift_before_resume_rejects_without_budget_claim(tmp_path: Path, drift: str) -> None:
    capture_id = f"combined-drift-{drift}"
    events: list[tuple] = []
    environment_capture, budget_capture = _callbacks(capture_id, events)

    with SqliteSaver.from_conn_string(str(tmp_path / f"{drift}.sqlite")) as saver:
        saver.setup()
        runtime = prototype.CombinedCheckpointPrototype(
            _fixture(),
            saver,
            environment_capture=environment_capture,
            budget_capture=budget_capture,
        )
        runtime.capture(capture_id, _arm_plan(capture_id))
        arm = runtime.derive_arm("baseline")
        before = copy.deepcopy(arm.budget.snapshot())

        if drift == "combined":
            runtime.combined_manifest["arm_plan"]["baseline"]["session_id"] = "drifted-session"
            runtime.combined_manifest["manifest_sha256"] = prototype.manifest_payload_sha256(runtime.combined_manifest)
        elif drift == "message":
            runtime.message_runtime.fixture["fixture_sha256"] = "0" * 64
        elif drift == "environment":
            runtime.environment_manifest["run_id"] = "drifted-capture"
        else:
            runtime.budget_manifest["parent_cost"]["tokens"] += 1

        expected_errors = (
            prototype.CombinedCheckpointError,
            prototype.message_checkpoint.FailureCheckpointPrototypeError,
            prototype.environment_checkpoint.EnvironmentCheckpointError,
            prototype.budget_checkpoint.BudgetCheckpointError,
        )
        with pytest.raises(expected_errors):
            runtime.resume_arm("baseline")
        assert arm.budget.snapshot() == before
        assert runtime.counters.fake_model_calls == 0


def test_capture_rejects_environment_arm_identity_drift(tmp_path: Path) -> None:
    capture_id = "combined-identity-drift"

    def environment_capture(_capture_id: str, _message_sha256: str):
        manifest = copy.deepcopy(_environment_manifest(capture_id))
        manifest["identities"]["baseline"] = "wrong-environment"
        manifest["manifest_sha256"] = prototype.environment_checkpoint.checkpoint_payload_sha256(manifest)
        return manifest

    with SqliteSaver.from_conn_string(str(tmp_path / "identity.sqlite")) as saver:
        saver.setup()
        runtime = prototype.CombinedCheckpointPrototype(
            _fixture(),
            saver,
            environment_capture=environment_capture,
            budget_capture=lambda *_args: _budget_manifest(capture_id),
        )
        with pytest.raises(prototype.CombinedCheckpointError, match="environment identity drifted"):
            runtime.capture(capture_id, _arm_plan(capture_id))
        assert runtime.combined_manifest is None


def test_combined_prototype_does_not_invoke_external_runtimes() -> None:
    source = PROTOTYPE_PATH.read_text(encoding="utf-8")
    assert "DockerCLI(" not in source
    assert "deerflow.models" not in source
    assert "forge_benchmark_runner" not in source
    assert "forge_verifier_repair_authorized_runner" not in source
