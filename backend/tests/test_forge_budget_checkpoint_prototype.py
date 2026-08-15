from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOTYPE_PATH = REPO_ROOT / "scripts" / "forge_budget_checkpoint_prototype.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("forge_budget_checkpoint_prototype_test", PROTOTYPE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


prototype = _load_module()


def _manifest(*, post_build_started: bool = True):
    return prototype.build_manifest(
        checkpoint_id="fixture-budget-parent",
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
        post_build_started=post_build_started,
    )


def test_manifest_freezes_remaining_deadlines_parent_cost_and_hash() -> None:
    manifest = _manifest()

    assert manifest["remaining_at_capture"] == {
        "provider_requests": 3,
        "compiler_invocations": 2,
        "compiler_model_turns": 5,
        "graph_recursion_steps": 18,
        "attempt_wall_clock_seconds": 160,
        "compiler_wall_clock_seconds": 40,
        "post_build_commands": 2,
    }
    assert manifest["continuation_clock"] == {
        "clock_kind": "deterministic_monotonic_offset",
        "attempt_elapsed_before_capture_seconds": 40,
        "attempt_total_remaining_seconds": 160,
        "attempt_work_remaining_seconds": 140,
        "compiler_elapsed_before_capture_seconds": 60,
        "compiler_total_remaining_seconds": 40,
        "compiler_exploration_remaining_seconds": 20,
    }
    assert manifest["parent_cost"] == {
        "compiler_invocations": 1,
        "provider_requests": 5,
        "tokens": 12345,
    }
    assert manifest["manifest_sha256"] == "7a19ec82b058587656dd3c93d7f935e274f9560cb4e0beac863f6acd88043730"
    assert manifest["manifest_sha256"] == prototype.manifest_payload_sha256(manifest)


def test_same_parent_derives_equal_initial_budgets_and_independent_claims() -> None:
    manifest = _manifest()
    baseline = prototype.BudgetCheckpointRuntime(manifest, prototype.BASELINE_ARM, prototype.FakeClock(10))
    treatment = prototype.BudgetCheckpointRuntime(manifest, prototype.TREATMENT_ARM, prototype.FakeClock(80))

    assert prototype.canonical_initial_budget(baseline) == prototype.canonical_initial_budget(treatment)

    baseline.claim("provider_requests")
    baseline.claim("compiler_model_turns")
    assert baseline.snapshot()["remaining"]["provider_requests"] == 2
    assert baseline.snapshot()["remaining"]["compiler_model_turns"] == 4
    assert treatment.snapshot()["remaining"]["provider_requests"] == 3
    assert treatment.snapshot()["remaining"]["compiler_model_turns"] == 5


@pytest.mark.parametrize("resource", prototype.DISCRETE_RESOURCES)
def test_each_discrete_budget_exhausts_and_rejects_new_work(resource: str) -> None:
    runtime = prototype.BudgetCheckpointRuntime(_manifest(), prototype.BASELINE_ARM, prototype.FakeClock())
    initial = runtime.snapshot()["remaining"][resource]

    for _ in range(initial):
        runtime.claim(resource)

    with pytest.raises(prototype.BudgetCheckpointExceeded, match=f"{resource}_limit_reached"):
        runtime.claim(resource)


def test_compiler_exploration_and_total_deadlines_are_distinct() -> None:
    clock = prototype.FakeClock()
    runtime = prototype.BudgetCheckpointRuntime(_manifest(), prototype.TREATMENT_ARM, clock)

    clock.advance(20)
    with pytest.raises(prototype.BudgetCheckpointExceeded, match="compiler_exploration_deadline_reached"):
        runtime.claim("compiler_model_turns")
    runtime.claim("post_build_commands")

    clock.advance(20)
    with pytest.raises(prototype.BudgetCheckpointExceeded, match="compiler_total_deadline_reached"):
        runtime.claim("post_build_commands")


def test_attempt_work_deadline_rejects_new_work_but_not_finalize_or_cleanup() -> None:
    clock = prototype.FakeClock()
    runtime = prototype.BudgetCheckpointRuntime(_manifest(), prototype.BASELINE_ARM, clock)

    clock.advance(140)
    for resource in prototype.DISCRETE_RESOURCES:
        with pytest.raises(prototype.BudgetCheckpointExceeded, match="attempt_work_deadline_reached"):
            runtime.claim(resource)

    assert runtime.allow_terminal_action("finalize")["remaining"]["attempt_work_wall_clock_seconds"] == 0
    clock.advance(40)
    assert runtime.allow_terminal_action("cleanup")["remaining"]["attempt_total_wall_clock_seconds"] == 0


def test_post_build_must_start_before_command_claim() -> None:
    runtime = prototype.BudgetCheckpointRuntime(
        _manifest(post_build_started=False),
        prototype.BASELINE_ARM,
        prototype.FakeClock(),
    )

    with pytest.raises(prototype.BudgetCheckpointExceeded, match="post_build_not_started"):
        runtime.claim("post_build_commands")


def test_cost_report_preserves_parent_and_separates_arm_increment() -> None:
    baseline = prototype.BudgetCheckpointRuntime(_manifest(), prototype.BASELINE_ARM, prototype.FakeClock())
    treatment = prototype.BudgetCheckpointRuntime(_manifest(), prototype.TREATMENT_ARM, prototype.FakeClock())

    baseline.claim("provider_requests")
    baseline.record_tokens(500)
    treatment.claim("provider_requests")
    treatment.claim("provider_requests")
    treatment.claim("compiler_invocations")
    treatment.record_tokens(900)

    baseline_report = baseline.cost_report()
    treatment_report = treatment.cost_report()
    assert (
        baseline_report["parent_cost"]
        == treatment_report["parent_cost"]
        == {
            "compiler_invocations": 1,
            "provider_requests": 5,
            "tokens": 12345,
        }
    )
    assert baseline_report["continuation_cost"] == {
        "tokens": 500,
        "provider_requests": 1,
        "compiler_invocations": 0,
    }
    assert treatment_report["total_cost"] == {
        "compiler_invocations": 2,
        "provider_requests": 7,
        "tokens": 13245,
    }


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda manifest: manifest["remaining_at_capture"].__setitem__("provider_requests", 99),
            "remaining_at_capture",
        ),
        (
            lambda manifest: manifest["continuation_clock"].__setitem__("attempt_work_remaining_seconds", 999),
            "continuation_clock",
        ),
        (
            lambda manifest: manifest["parent_cost"].__setitem__("tokens", 0),
            "parent_cost",
        ),
        (
            lambda manifest: manifest["limits"].__setitem__("provider_requests", -1),
            "non-negative",
        ),
        (
            lambda manifest: manifest.__setitem__("unexpected", True),
            "fields",
        ),
    ],
)
def test_manifest_rejects_arithmetic_schema_and_cost_drift(mutate, message: str) -> None:
    manifest = copy.deepcopy(_manifest())
    mutate(manifest)
    manifest["manifest_sha256"] = prototype.manifest_payload_sha256(manifest)

    with pytest.raises(prototype.BudgetCheckpointError, match=message):
        prototype.validate_manifest(manifest)


def test_manifest_rejects_hash_tampering() -> None:
    manifest = copy.deepcopy(_manifest())
    manifest["manifest_sha256"] = "0" * 64

    with pytest.raises(prototype.BudgetCheckpointError, match="SHA-256"):
        prototype.validate_manifest(manifest)


def test_clock_cannot_move_backwards() -> None:
    clock = prototype.FakeClock(10)
    runtime = prototype.BudgetCheckpointRuntime(_manifest(), prototype.BASELINE_ARM, clock)
    clock.current = 9

    with pytest.raises(prototype.BudgetCheckpointError, match="backwards"):
        runtime.snapshot()


def test_prototype_has_no_provider_docker_or_formal_runner_imports() -> None:
    source = PROTOTYPE_PATH.read_text(encoding="utf-8")
    assert "deerflow.models" not in source
    assert "deerflow.compile.docker_runtime" not in source
    assert "forge_benchmark_runner" not in source
    assert "forge_verifier_repair_authorized_runner" not in source
