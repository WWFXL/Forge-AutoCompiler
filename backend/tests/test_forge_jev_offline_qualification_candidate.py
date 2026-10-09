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

import forge_jev_offline_qualification_candidate as candidate  # noqa: E402


def test_generated_contract_is_frozen_split_isolated_and_zero_provider() -> None:
    pool = candidate.generate_source_pool()
    manifest = candidate.generate_manifest(pool)

    assert pool == candidate.v1.load_json(candidate.DEFAULT_SOURCE_POOL)
    assert manifest == candidate.v1.load_json(candidate.DEFAULT_MANIFEST)
    assert candidate.generate_schema(manifest) == candidate.v1.load_json(candidate.DEFAULT_SCHEMA)
    assert Counter(task["qualification_split"] for task in pool["tasks"]) == {
        "design": 6,
        "calibration": 6,
    }
    for split in candidate.QUALIFICATION_SPLITS:
        assert Counter(task["selected_build_system"] for task in pool["tasks"] if task["qualification_split"] == split) == {"cmake": 2, "make": 2, "autotools": 2}

    development_families = {task["project_family"] for task in pool["tasks"]}
    evaluation = manifest["data_contract"]["evaluation"]
    assert not development_families.intersection(evaluation["project_families"])
    assert evaluation["file_sha256"] == candidate._file_sha256(candidate.V2_REPORT)
    assert evaluation["read_only"] is True
    assert evaluation["single_analysis_only"] is True
    assert manifest["data_contract"]["global_commit_time_isolation"] is False
    assert manifest["data_contract"]["temporal_generalization_claim_allowed"] is False
    assert manifest["authorization"] == {
        "credential_read_authorized": False,
        "provider_calls_authorized": False,
        "model_calls_authorized": False,
        "model_tokens_authorized": 0,
        "provider_evidence_write_authorized": False,
        "docker_outcome_collection_authorized": False,
        "controller_implementation_authorized": False,
        "historical_evidence_write_authorized": False,
    }


def test_provider_state_excludes_identity_commands_and_fault_name() -> None:
    report = candidate.v1.load_json(candidate.V2_REPORT)
    model_input = report["states"][0]["model_input"]

    state = candidate.provider_state(model_input)

    assert set(state) == {
        "build_system",
        "phase_facts",
        "remaining_budget",
        "semantic_failure_log",
        "candidate_action_costs",
    }
    payload = json.dumps(state, ensure_ascii=False, sort_keys=True)
    assert model_input["state_id"] not in payload
    assert report["states"][0]["project_family"] not in payload
    assert all(fault not in payload for fault in candidate.FAULT_TYPES)


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
    assert result["credential_reads"] == 0
    assert result["transport"] == "httpx2.MockTransport"
    assert result["normalized_response"]["model"] == candidate.MODEL_ID
    assert result["normalized_response"]["request_id"] == "req-zero-provider-mock"
    assert result["normalized_response"]["usage"] == {
        "input_tokens": 123,
        "output_tokens": 18,
    }
    assert result["normalized_response"]["cost_usd"] == pytest.approx(0.000005166)
    assert result["normalized_response"]["order_agreement"] is True


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


def test_response_validation_fails_closed_on_model_and_probability_drift() -> None:
    answer = SimpleNamespace(
        type="choice",
        choice="build",
        probabilities={
            "dependency": 0.1,
            "configure": 0.1,
            "build": 0.7,
            "escalate_agent": 0.1,
        },
        confidence=0.6,
    )
    response = SimpleNamespace(
        model="jev-latest",
        request_id="req-version-drift",
        answers={question_id: answer for question_id in candidate.QUESTION_IDS},
        usage=SimpleNamespace(input_tokens=10, output_tokens=2),
    )
    with pytest.raises(candidate.CandidateError, match="响应模型漂移"):
        candidate.normalize_response(response, latency_ms=1.0)

    response.model = candidate.MODEL_ID
    answer.probabilities = {"build": 1.0}
    with pytest.raises(candidate.CandidateError, match="probability key 漂移"):
        candidate.normalize_response(response, latency_ms=1.0)


def test_preflight_does_not_read_local_credential_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_path_open = Path.open

    def guarded_open(path: Path, *args: object, **kwargs: object):
        if path.name == "jev-apikey.txt":
            raise AssertionError("candidate preflight 不得读取 credential 文件")
        return original_path_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    result = candidate.preflight()

    assert result["ready"] is True
    assert result["provider_calls"] == 0
    assert result["credential_reads"] == 0
    assert result["model_tokens"] == 0
    assert result["provider_evidence_writes"] == 0
