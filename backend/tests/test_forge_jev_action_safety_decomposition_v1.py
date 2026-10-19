from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import forge_jev_action_safety_decomposition_candidate as candidate  # noqa: E402
import forge_jev_action_safety_decomposition_v1 as execution  # noqa: E402


def test_execution_manifest_freezes_authorization_and_schedule() -> None:
    manifest = execution.generate_execution_manifest(
        implementation_revision="a" * 40,
        runner_sha256="b" * 64,
        candidate_manifest_file_sha256="c" * 64,
        candidate_manifest_canonical_sha256="d" * 64,
    )

    assert manifest["identity"] == "cpp-jev-action-safety-decomposition-v1"
    assert manifest["authorization"]["maximum_physical_requests"] == 60
    assert manifest["authorization"]["maximum_model_cost_usd"] == 0.0168
    assert manifest["provider_schedule"] == [
        {"condition": "action_noul", "split": "calibration", "requests": 15},
        {
            "condition": "action_card_noul",
            "split": "calibration",
            "requests": 15,
        },
        {"operation": "freeze_calibrators_and_thresholds"},
        {"condition": "action_noul", "split": "evaluation", "requests": 15},
        {
            "condition": "action_card_noul",
            "split": "evaluation",
            "requests": 15,
        },
        {"operation": "single_evaluation_analysis"},
    ]
    assert manifest["stopping_rules"]["run_historical_four_way_evaluation"] is False


def test_response_observation_records_noul_without_raw_http_body() -> None:
    response = SimpleNamespace(
        model=candidate.parent.MODEL_ID,
        request_id="req-observation",
        answers={question_id: SimpleNamespace(type="noul", noul=0.75) for question_id in candidate.provider_questions()},
        usage=SimpleNamespace(input_tokens=100, output_tokens=20),
    )

    observed = execution._response_observation(response, latency_ms=12.5)

    assert observed["request_id"] == "req-observation"
    assert observed["usage"] == {"input_tokens": 100, "output_tokens": 20}
    assert observed["cost_usd"] == pytest.approx(0.0000042)
    assert set(observed["answers"]) == set(candidate.provider_questions())
    assert all(answer == {"type": "noul", "noul": 0.75} for answer in observed["answers"].values())
    assert "raw_http_body" not in observed


def test_perfect_oracle_selections_close_all_budget_decisions() -> None:
    manifest = candidate.load_contract()
    _, labels, decisions = candidate.split_rows("evaluation")
    selections = [
        {
            "state_id": row["state_id"],
            "build_system": row["build_system"],
            "selected_action": row["optimal_action"],
        }
        for row in labels
    ]

    summary = execution._route_summary(selections, decisions, manifest)

    assert summary["joint_correct"] == 45
    assert summary["wrong_direct_count"] == 0
    assert summary["per_build_system_joint_correct"] == {
        "cmake": 15,
        "make": 15,
        "autotools": 15,
    }


def test_selection_summary_counts_wrong_direct_and_escalation_separately() -> None:
    rows = [
        {
            "build_system": "cmake",
            "selected_action": "build",
            "direct": True,
            "safe_selected": False,
            "exact_optimal": False,
        },
        {
            "build_system": "make",
            "selected_action": "dependency",
            "direct": True,
            "safe_selected": True,
            "exact_optimal": True,
        },
        {
            "build_system": "autotools",
            "selected_action": "escalate_agent",
            "direct": False,
            "safe_selected": True,
            "exact_optimal": True,
        },
    ]

    summary = execution._selection_summary(rows)

    assert summary["direct_state_count"] == 2
    assert summary["wrong_direct_count"] == 1
    assert summary["wrong_direct_risk"] == 0.5
    assert summary["exact_optimal_action_count"] == 2
