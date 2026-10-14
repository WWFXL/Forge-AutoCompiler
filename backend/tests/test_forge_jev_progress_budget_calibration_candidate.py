from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import httpx2
import pytest
from typesafe_sdk import RetryPolicy, TypeSafeAPIError, TypeSafeClient

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = REPO_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_jev_progress_budget_calibration_candidate as candidate  # noqa: E402


def _parent_report() -> dict[str, object]:
    return candidate.load_json(candidate.PARENT_REPORT)


def test_generated_contract_binds_parent_split_baselines_and_zero_provider() -> None:
    manifest = candidate.generate_manifest()

    assert manifest == candidate.load_json(candidate.DEFAULT_MANIFEST)
    assert candidate.generate_schema(manifest) == candidate.load_json(candidate.DEFAULT_SCHEMA)
    assert manifest["parent_contract"]["evidence"]["inventory_canonical_sha256"] == candidate.PARENT_INVENTORY_CANONICAL_SHA256
    assert manifest["authorization"] == {
        "credential_content_read_authorized": False,
        "credential_presence_and_mode_check_authorized": True,
        "provider_calls_authorized": False,
        "jev_calls_authorized": False,
        "agent_calls_authorized": False,
        "model_tokens_authorized": 0,
        "formal_attempt_creation_authorized": False,
        "formal_provider_evidence_write_authorized": False,
        "controller_implementation_authorized": False,
        "historical_evidence_write_authorized": False,
    }

    split = manifest["data_contract"]["split"]
    assert set(split["calibration"]["state_ids"]).isdisjoint(split["evaluation"]["state_ids"])
    assert set(split["calibration"]["project_families"].values()).isdisjoint(split["evaluation"]["project_families"].values())
    for name in candidate.SPLITS:
        assert split[name]["project_family_count"] == 3
        assert split[name]["state_count"] == 15
        assert split[name]["budget_decision_count"] == 45
    assert split["evaluation"]["rule_gate"]["joint_correct"] == 27
    assert split["evaluation"]["rule_gate"]["wrong_direct_count"] == 18
    assert split["evaluation"]["tfidf_budgetfit"]["joint_correct"] == 39
    assert split["evaluation"]["tfidf_budgetfit"]["wrong_direct_count"] == 0
    assert split["evaluation"]["oracle_routes"] == {
        "direct": 24,
        "escalate_agent": 3,
        "stop": 18,
    }


@pytest.mark.skipif(
    not candidate.PARENT_EVIDENCE_ROOT.is_dir(),
    reason="干净 CI checkout 不包含只读父 raw evidence",
)
def test_local_parent_raw_evidence_matches_frozen_inventory() -> None:
    audit = candidate.audit_parent_raw_evidence()

    assert audit == {
        "valid": True,
        "file_count": 702,
        "total_bytes": 2851071,
        "inventory_canonical_sha256": candidate.PARENT_INVENTORY_CANONICAL_SHA256,
        "zero_managed_resources": True,
    }


def test_split_is_mechanical_and_has_five_states_per_build_system() -> None:
    report = _parent_report()
    for split_name, families in candidate.SPLIT_FAMILIES.items():
        rows = [row for row in report["states"] if row["project_family"] in set(families.values())]
        assert Counter(row["build_system"] for row in rows) == {
            "cmake": 5,
            "make": 5,
            "autotools": 5,
        }
        contract = candidate.derive_split_contract(report, split_name)
        assert contract["state_ids"] == sorted(row["state_id"] for row in rows)


def test_provider_state_excludes_identity_labels_commands_costs_and_budget() -> None:
    report = _parent_report()
    state_row = report["states"][0]

    state = candidate.provider_state(state_row)

    assert tuple(state) == candidate.PROVIDER_STATE_FIELDS
    payload = json.dumps(state, ensure_ascii=False, sort_keys=True)
    assert state_row["state_id"] not in payload
    assert state_row["project_family"] not in payload
    for forbidden in (
        "candidate_action_families",
        "bound_commands",
        "safe_actions",
        "optimal_action",
        "remaining_budget",
        "budget_profile",
    ):
        assert forbidden not in payload


def test_choice_questions_have_identical_semantics_and_reversed_order() -> None:
    questions = candidate.provider_questions()
    primary = questions["next_action_primary"].model_dump(mode="json")
    sensitivity = questions["next_action_order_sensitivity"].model_dump(mode="json")

    assert primary["instructions"] == sensitivity["instructions"]
    assert tuple(primary["criteria"]) == candidate.PRIMARY_ACTION_ORDER
    assert tuple(sensitivity["criteria"]) == candidate.SENSITIVITY_ACTION_ORDER
    assert primary["criteria"] == dict(reversed(tuple(sensitivity["criteria"].items())))


def test_mock_sdk_roundtrip_validates_wire_contract_without_provider() -> None:
    result = candidate.mock_sdk_roundtrip()

    assert result["provider_calls"] == 0
    assert result["credential_content_reads"] == 0
    assert result["transport"] == "httpx2.MockTransport"
    response = result["normalized_response"]
    assert response["model"] == candidate.MODEL_ID
    assert response["request_id"] == "req-progress-budget-zero-provider-mock"
    assert response["usage"] == {"input_tokens": 321, "output_tokens": 20}
    assert response["cost_usd"] == pytest.approx(0.000013482)
    assert response["order_agreement"] is True


def test_sdk_retry_override_allows_only_one_physical_request() -> None:
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
        model=candidate.MODEL_ID,
        retry=RetryPolicy(max_retries=0, timeout=30.0),
        transport=httpx2.MockTransport(handler),
        base_url=candidate.API_BASE_URL,
    ) as client:
        with pytest.raises(TypeSafeAPIError):
            client.system_one(state={"state": "mock"}, questions=candidate.provider_questions())

    assert calls == 1


def test_response_normalizes_tolerated_probability_sum_and_fails_closed_on_drift() -> None:
    answer = SimpleNamespace(
        type="choice",
        choice="build",
        probabilities={
            "dependency": 0.1,
            "configure": 0.1,
            "build": 0.699,
            "escalate_agent": 0.1,
        },
        confidence=(0.699 - 0.25) / 0.75,
    )
    response = SimpleNamespace(
        model=candidate.MODEL_ID,
        request_id="req-tolerance",
        answers={question_id: answer for question_id in candidate.QUESTION_IDS},
        usage=SimpleNamespace(input_tokens=10, output_tokens=2),
    )

    normalized = candidate.normalize_response(response, latency_ms=2.0)
    probabilities = normalized["answers"]["next_action_primary"]["normalized_probabilities"]
    assert sum(probabilities.values()) == pytest.approx(1.0)
    assert normalized["answers"]["next_action_primary"]["raw_probability_sum"] == pytest.approx(0.999)

    response.model = "jev-latest"
    with pytest.raises(candidate.CandidateError, match="响应模型漂移"):
        candidate.normalize_response(response, latency_ms=2.0)
    response.model = candidate.MODEL_ID
    answer.probabilities = {"build": 1.0}
    with pytest.raises(candidate.CandidateError, match="probability key 漂移"):
        candidate.normalize_response(response, latency_ms=2.0)


def test_platt_configuration_and_zero_error_threshold_are_frozen() -> None:
    calibration_rows = [{"probability": 0.8 if index % 2 else 0.2, "safe": bool(index % 2)} for index in range(45)]
    estimator = candidate.fit_platt(calibration_rows)
    params = estimator.get_params()

    assert params["C"] == 1.0
    assert params["solver"] == "liblinear"
    assert params["random_state"] == 459
    assert params["max_iter"] == 1000
    assert candidate.calibrated_safe_probability(estimator, 0.8) > candidate.calibrated_safe_probability(estimator, 0.2)

    threshold_rows = [
        {"state_id": "c1", "build_system": "cmake", "selected_action": "build", "order_agreement": True, "safe": True, "score": 0.9},
        {"state_id": "c2", "build_system": "cmake", "selected_action": "configure", "order_agreement": True, "safe": True, "score": 0.8},
        {"state_id": "m1", "build_system": "make", "selected_action": "build", "order_agreement": True, "safe": True, "score": 0.7},
        {"state_id": "m2", "build_system": "make", "selected_action": "dependency", "order_agreement": True, "safe": True, "score": 0.6},
        {"state_id": "a1", "build_system": "autotools", "selected_action": "configure", "order_agreement": True, "safe": True, "score": 0.5},
        {"state_id": "a2", "build_system": "autotools", "selected_action": "build", "order_agreement": True, "safe": False, "score": 0.4},
        {"state_id": "ignored", "build_system": "autotools", "selected_action": "build", "order_agreement": False, "safe": False, "score": 0.95},
    ]
    selected = candidate.select_zero_error_threshold(threshold_rows, probability_field="score")

    assert selected["threshold"] == 0.5
    assert selected["direct_state_count"] == 5
    assert selected["unsafe_direct_count"] == 0
    assert selected["per_build_system_direct_state_count"] == {
        "cmake": 2,
        "make": 2,
        "autotools": 1,
    }
    assert selected["qualification_passed"] is True


def test_budget_fit_routes_direct_escalate_and_stop_without_sending_budget_to_jev() -> None:
    manifest = candidate.generate_manifest()
    profiles = manifest["budget_fit_contract"]["budget_profiles"]

    direct = candidate.budget_fit_route(
        selected_action="configure",
        order_agreement=True,
        calibrated_probability=0.9,
        threshold=0.8,
        remaining_budget=profiles["local_only"],
        manifest=manifest,
    )
    escalated = candidate.budget_fit_route(
        selected_action="configure",
        order_agreement=False,
        calibrated_probability=None,
        threshold=0.8,
        remaining_budget=profiles["agent_capable"],
        manifest=manifest,
    )
    stopped = candidate.budget_fit_route(
        selected_action="escalate_agent",
        order_agreement=True,
        calibrated_probability=None,
        threshold=0.8,
        remaining_budget=profiles["critical"],
        manifest=manifest,
    )

    assert direct == {"route": "direct", "action": "configure", "gate": "calibrated_local_action"}
    assert escalated == {"route": "escalate_agent", "action": "escalate_agent", "gate": "agent_reservation"}
    assert stopped == {"route": "stop", "action": None, "gate": "insufficient_budget"}
    assert "remaining_budget" not in manifest["data_contract"]["model_input_fields"]


def test_preflight_does_not_read_local_credential_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_path_open = Path.open
    original_read_text = Path.read_text

    def guarded_open(path: Path, *args: object, **kwargs: object):
        if path.name == "jev-apikey.txt":
            raise AssertionError("candidate preflight 不得打开 credential 文件")
        return original_path_open(path, *args, **kwargs)

    def guarded_read_text(path: Path, *args: object, **kwargs: object):
        if path.name == "jev-apikey.txt":
            raise AssertionError("candidate preflight 不得读取 credential 文件")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    monkeypatch.setattr(
        candidate,
        "audit_parent_raw_evidence",
        lambda: {
            "valid": True,
            "file_count": 702,
            "total_bytes": 2851071,
            "inventory_canonical_sha256": candidate.PARENT_INVENTORY_CANONICAL_SHA256,
            "zero_managed_resources": True,
        },
    )
    result = candidate.preflight()

    assert result["ready"] is True
    assert result["provider_calls"] == 0
    assert result["credential_content_reads"] == 0
    assert result["credential_metadata"]["credential_content_reads"] == 0
    assert result["model_tokens"] == 0
    assert result["formal_attempts_created"] == 0
    assert result["formal_provider_evidence_writes"] == 0
    assert result["historical_evidence_writes"] == 0
    assert result["parent_raw_evidence_audit"]["valid"] is True
