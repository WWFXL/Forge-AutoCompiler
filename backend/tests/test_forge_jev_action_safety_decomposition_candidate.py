from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx2
import pytest
from typesafe_sdk import RetryPolicy, TypeSafeAPIError, TypeSafeClient

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import forge_jev_action_safety_decomposition_candidate as candidate  # noqa: E402


def test_contract_is_deterministic_and_preserves_frozen_parents() -> None:
    manifest = candidate.load_contract()

    assert manifest == candidate.generate_manifest()
    assert manifest["formal_identity"] == "cpp-jev-action-safety-decomposition-v1"
    assert manifest["future_provider_budget"] == {
        "requests_per_condition": 30,
        "maximum_physical_requests": 60,
        "maximum_input_tokens": 400000,
        "maximum_output_tokens": 100000,
        "maximum_model_cost_usd": 0.0168,
        "currently_authorized": False,
    }
    assert candidate.audit_historical_evidence()["evaluation_provider_requests"] == 0
    assert candidate.parent.audit_parent_raw_evidence()["valid"] is True


def test_action_cards_cover_all_states_without_shell_or_labels() -> None:
    cards = []
    for split in candidate.SPLITS:
        states, _, _ = candidate.split_rows(split)
        for state in states:
            command_text = {command for action in state["candidate_actions"] if action["action_family"] in candidate.LOCAL_ACTIONS for command in action["bound_commands"]}
            for action in candidate.LOCAL_ACTIONS:
                card = candidate.action_card(state, action)
                cards.append(card)
                assert tuple(card) == (
                    "action_family",
                    "operation_summary",
                    "bound_step_count",
                    "workspace_effect",
                    "expected_frontier_transition",
                    "expected_evidence",
                )
                payload = json.dumps(card, ensure_ascii=False, sort_keys=True)
                assert not any(command in payload for command in command_text)
                for forbidden in (
                    state["state_id"],
                    state["project_family"],
                    "safe_actions",
                    "optimal_action",
                    "fault_name",
                ):
                    assert forbidden not in payload
    assert len(cards) == 90


def test_provider_conditions_differ_only_by_action_cards() -> None:
    state = candidate.split_rows("calibration")[0][0]
    plain = candidate.provider_state(state, "action_noul")
    enhanced = candidate.provider_state(state, "action_card_noul")

    assert tuple(plain) == candidate.parent.PROVIDER_STATE_FIELDS
    assert {**enhanced, "candidate_action_cards": None} != plain
    assert {key: value for key, value in enhanced.items() if key != "candidate_action_cards"} == plain
    assert tuple(enhanced["candidate_action_cards"]) == candidate.LOCAL_ACTIONS


def test_noul_questions_repeat_identical_semantics_in_reverse_order() -> None:
    questions = candidate.provider_questions()

    assert tuple(questions) == (
        "primary_dependency",
        "primary_configure",
        "primary_build",
        "order_sensitivity_build",
        "order_sensitivity_configure",
        "order_sensitivity_dependency",
    )
    for action in candidate.LOCAL_ACTIONS:
        primary = questions[f"primary_{action}"].model_dump(mode="json")
        sensitivity = questions[f"order_sensitivity_{action}"].model_dump(mode="json")
        assert primary == sensitivity
        assert primary["type"] == "noul"


def test_mock_sdk_roundtrip_uses_real_noul_wire_shape() -> None:
    for condition in candidate.CONDITIONS:
        result = candidate.mock_sdk_roundtrip(condition)
        response = result["normalized_response"]
        assert result["provider_calls"] == 0
        assert result["credential_content_reads"] == 0
        assert result["transport"] == "httpx2.MockTransport"
        assert response["model"] == candidate.parent.MODEL_ID
        assert response["request_id"] == "req-action-safety-zero-provider-mock"
        assert response["usage"] == {"input_tokens": 456, "output_tokens": 24}
        assert all(row["raw_action_score"] == pytest.approx(0.8) for row in response["action_pairs"].values())


def test_retry_override_allows_one_physical_request() -> None:
    calls = 0

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(
            529,
            headers={"x-typesafe-request-id": "req-no-retry"},
            json={"error": {"message": "overloaded"}},
        )

    with TypeSafeClient(
        api_key="mock-key",
        model=candidate.parent.MODEL_ID,
        retry=RetryPolicy(max_retries=0, timeout=30.0),
        transport=httpx2.MockTransport(handler),
        base_url=candidate.parent.API_BASE_URL,
    ) as client:
        with pytest.raises(TypeSafeAPIError):
            client.system_one(
                state={"build_system": "cmake"},
                questions=candidate.provider_questions(),
            )
    assert calls == 1


def test_response_uses_conservative_minimum_and_fails_closed() -> None:
    probabilities = {
        "primary_dependency": 0.9,
        "primary_configure": 0.8,
        "primary_build": 0.7,
        "order_sensitivity_build": 0.6,
        "order_sensitivity_configure": 0.5,
        "order_sensitivity_dependency": 0.4,
    }
    answers = {key: SimpleNamespace(type="noul", noul=value) for key, value in probabilities.items()}
    response = SimpleNamespace(
        model=candidate.parent.MODEL_ID,
        request_id="req-test",
        answers=answers,
        usage=SimpleNamespace(input_tokens=10, output_tokens=2),
    )

    normalized = candidate.normalize_response(response, latency_ms=2.0)

    assert normalized["action_pairs"]["dependency"]["raw_action_score"] == 0.4
    assert normalized["action_pairs"]["configure"]["raw_action_score"] == 0.5
    assert normalized["action_pairs"]["build"]["raw_action_score"] == 0.6
    response.model = "jev-latest"
    with pytest.raises(candidate.CandidateError, match="响应模型漂移"):
        candidate.normalize_response(response, latency_ms=2.0)


def test_selector_threshold_is_zero_error_at_final_action_level() -> None:
    rows = []
    systems = ("cmake", "make", "autotools")
    for index in range(15):
        safe_action = candidate.LOCAL_ACTIONS[index % 3]
        for action in candidate.LOCAL_ACTIONS:
            rows.append(
                {
                    "state_id": f"s-{index:02d}",
                    "build_system": systems[index % 3],
                    "action": action,
                    "safe": action == safe_action,
                    "raw_action_score": 0.9 if action == safe_action else 0.1,
                }
            )
    estimator = candidate.fit_platt(rows)
    for row in rows:
        row["calibrated_probability"] = candidate.calibrated_safe_probability(estimator, row["raw_action_score"])
    threshold = candidate.select_zero_error_threshold(rows, probability_field="calibrated_probability")

    assert threshold["direct_state_count"] == 15
    assert threshold["unsafe_direct_count"] == 0
    assert threshold["qualification_passed"] is True
    assert {row["action"] for row in threshold["selected"]} == set(candidate.LOCAL_ACTIONS)


def test_budget_fit_keeps_budget_out_of_jev_and_routes_deterministically() -> None:
    manifest = candidate.load_contract()
    profiles = manifest["budget_fit_contract"]["budget_profiles"]

    assert candidate.budget_fit_route(
        selected_action="configure",
        remaining_budget=profiles["local_only"],
        manifest=manifest,
    ) == {
        "route": "direct",
        "action": "configure",
        "gate": "calibrated_action_safety",
    }
    assert (
        candidate.budget_fit_route(
            selected_action="escalate_agent",
            remaining_budget=profiles["agent_capable"],
            manifest=manifest,
        )["route"]
        == "escalate_agent"
    )
    assert (
        candidate.budget_fit_route(
            selected_action="escalate_agent",
            remaining_budget=profiles["critical"],
            manifest=manifest,
        )["route"]
        == "stop"
    )
    assert "remaining_budget" not in manifest["data_contract"]["base_model_input_fields"]
