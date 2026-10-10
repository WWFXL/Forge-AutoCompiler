from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_jev_end_to_end_canary_v1.py"
SCRIPTS_ROOT = str(REPO_ROOT / "scripts")
if SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, SCRIPTS_ROOT)


def _load_module():
    spec = importlib.util.spec_from_file_location("forge_jev_end_to_end_canary_v1", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def canary():
    return _load_module()


def test_three_build_system_cases_and_balanced_arms(canary) -> None:
    assert {canary._task(case["task_id"])["selected_build_system"] for case in canary.CASE_SPECS} == {"cmake", "make", "autotools"}
    assert {case["expected_action"] for case in canary.CASE_SPECS} == {"dependency", "configure", "build"}
    assert len(canary.SCHEDULE) == 9
    assert all(sum(row[1] == arm for row in canary.SCHEDULE) == 3 for arm in canary.ARMS)
    assert all(sum(row[0] == case["task_id"] for row in canary.SCHEDULE) == 3 for case in canary.CASE_SPECS)


def test_rule_gate_is_frozen_build(canary) -> None:
    assert canary.rule_route({}) == "build"


def test_direct_commands_are_code_bound(canary) -> None:
    for case in canary.CASE_SPECS:
        task = canary._task(case["task_id"])
        commands = canary._commands(task, case["fault_type"], case["expected_action"])
        assert commands
        assert commands == next(row["bound_commands"] for row in canary.semantic_v2._state_record(task, case["fault_type"], "failure")["candidate_actions"] if row["action_family"] == case["expected_action"])


def test_budget_is_bounded(canary) -> None:
    assert canary.AGENT_BUDGET["max_model_requests"] == 24
    assert canary.AGENT_BUDGET["max_recorded_tokens"] == 300_000
    assert canary.TOTAL_AGENT_REQUEST_CEILING == 9 * 24
    assert canary.TOTAL_AGENT_TOKEN_CEILING == 9 * 300_000
    assert canary.TOTAL_JEV_REQUEST_CEILING == 3


def test_jev_route_uses_calibration_and_never_declares_success(canary) -> None:
    task = canary._task("args")
    state = canary.semantic_v2._state_record(task, "invalid_build_state", "Makefile:1: missing separator")
    fingerprint = "f" * 64
    decision = canary.TypedDecision(
        state_id=state["state_id"],
        model=canary.CALIBRATION.model,
        request_fingerprint=fingerprint,
        primary_choice="configure",
        reverse_choice="configure",
        probabilities={"dependency": 0.01, "configure": 0.97, "build": 0.01, "escalate_agent": 0.01},
        reverse_probabilities={"dependency": 0.01, "configure": 0.97, "build": 0.01, "escalate_agent": 0.01},
    )
    action, route = canary.choose_jev_route(state, decision)
    assert action == "configure"
    assert route["disposition"] == "direct_execute"
    assert route["dispatch_disposition"] == "awaiting_strict_verification"


def test_manifest_authorization_and_claim_boundaries(canary, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(canary, "_git", lambda *args: "a" * 40)
    monkeypatch.setattr(canary, "_git_blob_sha256", lambda revision, path: "b" * 64)
    monkeypatch.setattr(canary, "file_sha256", lambda path: "c" * 64)
    manifest = canary.build_manifest("a" * 40)
    assert manifest["authorization"]["formal_attempts"] == 9
    assert manifest["authorization"]["replacement"] is False
    assert manifest["interpretation"] == {
        "canary_only": True,
        "treatment_effect": False,
        "strict_success_noninferiority": False,
        "cost_savings_claim": False,
        "dynamic_budget_claim": False,
    }


def test_target_contracts_and_oracles_are_constructible(canary) -> None:
    for case in canary.CASE_SPECS:
        task = canary._task(case["task_id"])
        target_path, target_type = canary._compiled_target(task)
        assert target_path in task["target"]["required_artifacts"]
        assert target_type in {"executable", "shared_library", "static_library", "object"}
        oracle = canary._oracle_spec(task)
        oracle.validate()
        assert oracle.oracle_ref == canary._oracle_ref(task)


def test_batch_budget_aggregation_fails_closed(canary) -> None:
    row = {
        "agent_usage": {"model_requests": 1, "recorded_tokens": 2},
        "jev_usage": {"model_requests": 1, "input_tokens": 3, "cost_usd": 0.0001},
    }
    totals = canary._batch_totals([row, row])
    assert totals == {
        "agent_requests": 2,
        "agent_recorded_tokens": 4,
        "jev_requests": 2,
        "jev_input_tokens": 6,
        "jev_cost_usd": 0.0002,
    }
    assert canary._within_budget(totals) is True
    totals["jev_requests"] = canary.TOTAL_JEV_REQUEST_CEILING + 1
    assert canary._within_budget(totals) is False
