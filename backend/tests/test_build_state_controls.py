"""负控制必须有特定证据；异常或清理失败不能冒充正确拒绝。"""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("build_state_controls", Path(__file__).resolve().parents[2] / "scripts/forge_build_state_controls.py")
controls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controls)


@pytest.mark.parametrize("control", controls.CONTROL_NAMES)
def test_infrastructure_failure_never_counts_as_successful_negative_control(control):
    row = {"status": "stopped", "error_class": "TimeoutExpired", "cleanup": {"succeeded": True}, "fixed_source_files_unchanged": True}
    assert not controls.expected_observation({"control": control}, row)


def test_exit_zero_without_full_test_evidence_is_detected_only_at_fixed_test_step():
    row = {"status": "needs_handoff", "cleanup": {"succeeded": True}, "fixed_source_files_unchanged": True, "handoff_step": "check", "all_command_exit_zero": True, "test_expectation_satisfied": False}
    assert controls.expected_observation({"control": "empty_tests"}, row)
    row["handoff_step"] = "build"
    assert not controls.expected_observation({"control": "empty_tests"}, row)


@pytest.mark.parametrize("control", ("omit_bootstrap", "delivery_drift"))
def test_workspace_success_is_required_before_claiming_replay_detects_defect(control):
    row = {
        "status": "needs_handoff",
        "cleanup": {"succeeded": True},
        "fixed_source_files_unchanged": True,
        "handoff_reason": "acceptance_failed",
        "replay_status": "failed",
        "workspace_test_passed": True,
        "replay_attempts": [{"failure_classification": "recipe_execution_failed" if control == "omit_bootstrap" else "size_mismatch"}],
    }
    assert controls.expected_observation({"control": control}, row)
    row["workspace_test_passed"] = False
    assert not controls.expected_observation({"control": control}, row)


def test_cleanup_failure_invalidates_even_positive_control():
    row = {"status": "verified", "session_status": "completed", "cleanup": {"succeeded": False}, "fixed_source_files_unchanged": True}
    assert not controls.expected_observation({"control": "normal"}, row)


def test_empty_test_control_preserves_original_smoke_and_delivery_contract():
    import json

    original = json.loads((controls.REPO_ROOT / "benchmarks/manifests/cpp-build-plan-source-qualification-v2.json").read_text())["projects"][0]
    item = {**original, "control": "empty_tests"}
    changed = controls.prepare_plan(item)
    original_plan = controls.BuildPlan.model_validate(original["plan"])
    assert changed.artifact_paths == original_plan.artifact_paths
    assert [step for step in changed.steps if step.role == "smoke"] == [step for step in original_plan.steps if step.role == "smoke"]
    assert "-DBUILD_TESTS=OFF" in changed.steps[0].command
    assert "-DBUILD_TESTS=ON" in original_plan.steps[0].command
