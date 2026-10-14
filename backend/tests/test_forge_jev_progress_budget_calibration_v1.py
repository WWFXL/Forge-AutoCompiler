from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = REPO_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_jev_progress_budget_calibration_v1 as formal  # noqa: E402


def _manifest() -> dict[str, object]:
    return formal.generate_execution_manifest(
        implementation_revision="a" * 40,
        runner_sha256="b" * 64,
    )


def _write_provider_fixture(root: Path, split: str) -> None:
    states, labels, _ = formal._split_rows(split)
    labels_by_id = {row["state_id"]: row for row in labels}
    directory = root / "provider" / split
    directory.mkdir(parents=True)
    for index, state in enumerate(states, start=1):
        choice = labels_by_id[state["state_id"]]["optimal_action"]
        probabilities = {action: 0.025 for action in formal.candidate.ACTION_FAMILIES}
        probabilities[choice] = 0.925
        response = {
            "model": formal.candidate.MODEL_ID,
            "request_id": f"req-{split}-{index:02d}",
            "answers": {
                question_id: {
                    "choice": choice,
                    "raw_probabilities": probabilities,
                    "raw_probability_sum": 1.0,
                    "normalized_probabilities": probabilities,
                    "confidence": 0.9,
                    "recomputed_confidence": 0.9,
                }
                for question_id in formal.candidate.QUESTION_IDS
            },
            "usage": {"input_tokens": 100, "output_tokens": 10},
            "cost_usd": 0.0000042,
            "latency_ms": float(index),
            "order_agreement": True,
        }
        formal._write_once_json(
            directory / "requests" / f"{index:02d}-{state['state_id']}.json",
            {
                "identity": formal.IDENTITY,
                "split": split,
                "sequence": index,
                "state_id": state["state_id"],
                "request_fingerprint": "f" * 64,
                "response": response,
            },
        )
    formal._write_once_json(directory / "completed.json", {"status": "completed"})


def test_execution_manifest_authorizes_only_frozen_offline_provider_run() -> None:
    manifest = _manifest()

    assert manifest["parent_candidate"] == {
        "identity": "cpp-jev-progress-budget-calibration-candidate-v1",
        "git_revision": formal.CANDIDATE_REVISION,
        "manifest_path": "benchmarks/manifests/cpp-jev-progress-budget-calibration-candidate-v1.json",
        "manifest_file_sha256": formal.CANDIDATE_MANIFEST_FILE_SHA256,
        "manifest_canonical_sha256": formal.CANDIDATE_MANIFEST_CANONICAL_SHA256,
    }
    assert manifest["authorization"] == {
        "credential_read_authorized": True,
        "provider_calls_authorized": True,
        "jev_calls_authorized": True,
        "agent_calls_authorized": False,
        "maximum_physical_requests": 30,
        "maximum_input_tokens": 200000,
        "maximum_output_tokens": 50000,
        "maximum_model_cost_usd": 0.0084,
        "new_identity_evidence_write_authorized": True,
        "controller_implementation_authorized": False,
        "historical_evidence_write_authorized": False,
    }
    assert manifest["provider_schedule"] == {
        "calibration_requests": 15,
        "evaluation_requests": 15,
        "evaluation_requires_passed_calibration": True,
        "evaluation_single_analysis_only": True,
    }
    assert manifest["stopping_rules"]["retry_failed_request"] is False
    assert manifest["stopping_rules"]["replace_failed_state"] is False
    assert manifest["stopping_rules"]["backfill_failed_state"] is False


def test_response_observation_precedes_and_survives_semantic_rejection() -> None:
    answer = SimpleNamespace(
        type="choice",
        choice="build",
        probabilities={"build": 1.0},
        confidence=1.0,
    )
    response = SimpleNamespace(
        model=formal.candidate.MODEL_ID,
        request_id="req-invalid-schema",
        answers={question_id: answer for question_id in formal.candidate.QUESTION_IDS},
        usage=SimpleNamespace(input_tokens=123, output_tokens=7),
    )

    observation = formal._response_observation(response, latency_ms=12.5)

    assert observation["request_id"] == "req-invalid-schema"
    assert observation["usage"] == {"input_tokens": 123, "output_tokens": 7}
    assert observation["cost_usd"] == pytest.approx(0.000005166)
    assert observation["answers"]["next_action_primary"]["probabilities"] == {"build": 1.0}
    with pytest.raises(formal.candidate.CandidateError, match="probability key 漂移"):
        formal.candidate.normalize_response(response, latency_ms=12.5)


def test_provider_failure_is_create_once_and_not_retried(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    evidence = tmp_path / "evidence"
    credential = tmp_path / "jev-apikey.txt"
    credential.write_text("test-key\n", encoding="utf-8")
    credential.chmod(0o600)
    calls = 0

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def system_one(self, **kwargs: object) -> object:
            nonlocal calls
            calls += 1
            raise RuntimeError("transport failed")

    class FakeHTTP:
        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(formal, "EVIDENCE_ROOT", evidence)
    monkeypatch.setattr(formal, "CREDENTIAL_FILE", credential)
    monkeypatch.setattr(formal, "validate_execution_manifest", lambda: manifest)
    monkeypatch.setattr(formal, "_assert_revision", lambda manifest, require_clean: None)
    monkeypatch.setattr(formal, "validate_egress", lambda: {"passed": True})
    monkeypatch.setattr(formal, "_provider_http_client", FakeHTTP)
    monkeypatch.setattr(formal, "TypeSafeClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(formal, "_git", lambda *args: "a" * 40)

    with pytest.raises(RuntimeError, match="transport failed"):
        formal.run_provider("calibration")

    assert calls == 1
    assert len(list((evidence / "provider/calibration/attempts").glob("*.json"))) == 1
    assert not (evidence / "provider/calibration/observations").exists()
    assert (evidence / "provider/calibration/failed.json").is_file()
    with pytest.raises(formal.ExecutionError, match="已存在"):
        formal.run_provider("calibration")
    assert calls == 1


def test_calibration_and_evaluation_use_frozen_holdout_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    evidence = tmp_path / "evidence"
    monkeypatch.setattr(formal, "EVIDENCE_ROOT", evidence)
    monkeypatch.setattr(formal, "validate_execution_manifest", lambda: manifest)
    _write_provider_fixture(evidence, "calibration")

    calibration = formal.calibrate()

    assert calibration["passed"] is True
    assert calibration["row_count"] == 45
    assert calibration["calibrated_threshold"]["direct_state_count"] == 12
    assert calibration["calibrated_threshold"]["unsafe_direct_count"] == 0
    assert all(calibration["calibrated_threshold"]["per_build_system_direct_state_count"][system] == 4 for system in formal.candidate.BUILD_SYSTEMS)
    with pytest.raises(formal.ExecutionError, match="已存在"):
        formal.calibrate()

    _write_provider_fixture(evidence, "evaluation")
    evaluation = formal.evaluate()

    assert evaluation["action_analysis"]["exact_optimal_action_count"] == 15
    assert evaluation["action_analysis"]["safe_action_count"] == 15
    assert evaluation["jev_calibrated_budgetfit"]["joint_correct"] == 45
    assert evaluation["jev_calibrated_budgetfit"]["direct_count"] == 24
    assert evaluation["jev_calibrated_budgetfit"]["wrong_direct_count"] == 0
    assert evaluation["core_passed"] is True
    assert evaluation["incremental_passed"] is True
    assert evaluation["decision"] == "proceed_to_frozen_response_progress_budget_controller_replay_design"
    with pytest.raises(formal.ExecutionError, match="已存在"):
        formal.evaluate()


def test_preflight_never_reads_credential_content(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    credential = tmp_path / "jev-apikey.txt"
    credential.write_text("must-not-be-read\n", encoding="utf-8")
    credential.chmod(0o600)
    monkeypatch.setattr(formal, "CREDENTIAL_FILE", credential)
    monkeypatch.setattr(formal, "validate_execution_manifest", _manifest)
    monkeypatch.setattr(formal, "_assert_revision", lambda manifest, require_clean: None)
    monkeypatch.setattr(formal, "validate_egress", lambda: {"passed": True})
    monkeypatch.setattr(formal, "_git", lambda *args: "a" * 40)
    monkeypatch.setattr(formal.candidate, "audit_parent_raw_evidence", lambda: {"valid": True})
    original_read_text = Path.read_text

    def guarded_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path == credential:
            raise AssertionError("preflight 读取了 credential")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    result = formal.preflight()

    assert result["ready"] is True
    assert result["credential_reads"] == 0
    assert result["provider_calls"] == 0
    assert result["model_tokens"] == 0


def test_hard_budget_includes_output_tokens() -> None:
    usage = {
        "physical_requests": 1,
        "completed_response_observations": 1,
        "valid_normalized_responses": 1,
        "input_tokens": 1,
        "output_tokens": 50001,
        "model_cost_usd": 0.0,
    }

    with pytest.raises(formal.ExecutionError, match="硬预算越界"):
        formal._enforce_budget(_manifest(), usage)


def test_evidence_inventory_excludes_self_and_terminal_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "result.json").write_text(json.dumps({"result": True}), encoding="utf-8")
    (evidence / "inventory.json").write_text("{}", encoding="utf-8")
    (evidence / "completed.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(formal, "EVIDENCE_ROOT", evidence)

    rows = formal._evidence_inventory()

    assert [row["path"] for row in rows] == ["result.json"]


def test_frozen_report_stops_before_evaluation_without_backfill() -> None:
    report = formal.candidate.load_json(formal.JSON_REPORT)

    assert report["identity"] == formal.IDENTITY
    assert report["terminal_stage"] == "calibration"
    assert report["decision"] == "stop_before_progress_budget_evaluation"
    assert report["evaluation"] is None
    assert report["budget"] == {
        "physical_requests": 15,
        "completed_response_observations": 15,
        "valid_normalized_responses": 15,
        "input_tokens": 14552,
        "output_tokens": 1557,
        "model_cost_usd": 0.000611184,
    }
    calibration = report["calibration"]
    assert calibration["action_analysis"]["exact_optimal_action_count"] == 4
    assert calibration["action_analysis"]["safe_action_count"] == 14
    assert calibration["action_analysis"]["order_agreement_count"] == 7
    assert calibration["calibrated_threshold"]["direct_state_count"] == 2
    assert calibration["calibrated_threshold"]["per_build_system_direct_state_count"] == {
        "cmake": 2,
        "make": 0,
        "autotools": 0,
    }
    assert calibration["gates"]["minimum_direct_state_count"] is False
    assert calibration["gates"]["all_build_systems_direct"] is False
