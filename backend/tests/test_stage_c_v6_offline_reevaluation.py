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

import forge_stage_c_runner as stage_c  # noqa: E402
import forge_stage_c_v6_offline_reevaluation_protocol as protocol  # noqa: E402
import forge_stage_c_v6_offline_reevaluation_runner as runner  # noqa: E402


def test_authorized_manifest_is_deterministic_and_zero_provider() -> None:
    manifest = protocol.load_manifest()

    assert manifest == protocol.generate_manifest()
    assert manifest["authorization"] == {
        "offline_reevaluation_authorized": True,
        "credential_read_authorized": False,
        "provider_calls_authorized": False,
        "model_creation_authorized": False,
        "reachability_request_authorized": False,
        "docker_execution_authorized": True,
        "evidence_write_authorized": True,
        "formal_stage_c_attempts_authorized": True,
        "model_tokens_authorized": 0,
        "stage_c_execution_started": False,
    }
    assert manifest["budget"]["per_arm"]["max_recorded_tokens"] is None
    assert manifest["budget"]["token_accounting"] == {
        "mode": "meter_each_request_without_ceiling",
        "record_input_tokens": True,
        "record_output_tokens": True,
        "record_total_tokens": True,
        "token_total_is_termination_condition": False,
    }
    assert manifest["schedule"]["evaluation_count"] == 22
    assert manifest["schedule"]["retry"] is False
    assert manifest["schedule"]["replacement"] is False
    assert manifest["schedule"]["backfill"] is False


def test_source_receipt_covers_submitted_candidates_and_prior_evaluator_gap() -> None:
    receipt = json.loads((REPO_ROOT / protocol.SOURCE_RECEIPT_PATH).read_text())

    assert receipt["evaluation_count"] == 22
    assert receipt["excluded_no_candidate_pairs"] == [
        "stage-c-v5-civetweb-r1",
        "stage-c-v5-civetweb-r2",
    ]
    assert len({entry["source_pair_id"] for entry in receipt["entries"]}) == 22
    assert sum(entry["original_evaluator"] is not None for entry in receipt["entries"]) == 16
    assert sum(entry["original_evaluator"] is None for entry in receipt["entries"]) == 6
    assert {entry["task_id"] for entry in receipt["entries"] if entry["original_evaluator"] is None} == {"stockfish-11", "lz4", "8cc"}
    assert all(entry["submission_id"].removeprefix("submission:") == entry["source_candidate_record_sha256"] for entry in receipt["entries"])


def test_original_node_input_round_trips_without_identity_change(tmp_path: Path) -> None:
    manifest = json.loads((REPO_ROOT / "benchmarks/manifests/cpp-stage-c-paired-calibration-v5-session-identity-authorized.json").read_text())
    pair = manifest["schedule"]["pairs"][0]
    task = next(task for task in manifest["tasks"] if task["task_id"] == pair["task_id"])
    source = stage_c._node_input(
        manifest,
        task,
        SimpleNamespace(session_id="source-session"),
        pair["attempt_ids"]["B"],
    )
    path = tmp_path / "input.json"
    path.write_text(source.canonical_json(), encoding="utf-8")

    loaded = runner._load_node_input(path)

    assert loaded == source
    assert loaded.canonical_sha256() == source.canonical_sha256()


def test_synthetic_node_result_binds_source_and_marks_unavailable_values() -> None:
    receipt = json.loads((REPO_ROOT / protocol.SOURCE_RECEIPT_PATH).read_text())
    entry = receipt["entries"][0]

    result = runner._synthetic_node_result(entry, "inspected")

    assert result.node_status == "submitted"
    assert result.submission_id == entry["submission_id"]
    assert result.candidate_record_sha256 == entry["source_candidate_record_sha256"]
    assert result.evidence_head_sha256 == entry["source_evidence_head_sha256"]
    assert result.usage.model_requests == entry["source_usage"]["model_requests"]
    assert result.usage.recorded_tokens == entry["source_usage"]["recorded_tokens"]
    assert result.usage.agent_steps == 0
    assert result.wall_clock_ms == 0
    result.validate()


def _closed_result(manifest: dict[str, object], evaluation_id: str) -> dict[str, object]:
    return {
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "evaluation_id": evaluation_id,
        "provider_requests": 0,
        "total_tokens": 0,
        "cleanup_succeeded": True,
        "zero_managed_resources": True,
        "error_class": None,
    }


def _write_closed_evaluation(root: Path, manifest: dict[str, object], evaluation_id: str) -> None:
    evaluation_dir = root / "evaluations" / evaluation_id
    evaluation_dir.mkdir(parents=True)
    (evaluation_dir / "attempt.json").write_text("{}\n", encoding="utf-8")
    (evaluation_dir / "token-ledger.json").write_text(json.dumps(runner._token_ledger()), encoding="utf-8")
    (evaluation_dir / "result.json").write_text(json.dumps(_closed_result(manifest, evaluation_id)), encoding="utf-8")


def test_recovery_accepts_only_a_contiguous_completed_prefix(tmp_path: Path) -> None:
    manifest = protocol.load_manifest()
    evaluations = manifest["schedule"]["evaluations"]
    first = evaluations[0]["evaluation_id"]
    third = evaluations[2]["evaluation_id"]
    _write_closed_evaluation(tmp_path, manifest, first)

    completed = runner._completed_prefix(manifest, tmp_path)

    assert [result["evaluation_id"] for result in completed] == [first]
    _write_closed_evaluation(tmp_path, manifest, third)
    with pytest.raises(runner.StageCV6OfflineRunnerError, match="不是连续前缀"):
        runner._completed_prefix(manifest, tmp_path)


def test_token_ledger_records_zero_requests_without_a_ceiling() -> None:
    assert runner._token_ledger() == {
        "mode": "meter_each_request_without_ceiling",
        "requests": [],
        "request_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "token_total_is_termination_condition": False,
    }


def test_oracle_adapter_gate_covers_all_three_contract_kinds() -> None:
    manifest = protocol.load_manifest()

    assert runner._validate_oracle_adapter(manifest) == {
        "scheduled_oracle_kinds": ["command", "compile_and_run"],
        "adapter_oracle_kinds": ["command", "compile_and_run", "service_probe"],
    }
