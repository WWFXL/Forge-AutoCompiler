"""Issue #365 formal marker failure 只读审计与 repair 测试。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
AUDIT_SCRIPT = SCRIPTS / "forge_contract_driven_repair_mechanism_v1_formal_failure_audit.py"
REPAIR_SCRIPT = SCRIPTS / "forge_contract_driven_repair_mechanism_v1_formal_marker_repair.py"
JSON_REPORT = REPO_ROOT / "benchmarks/reports/cpp-contract-driven-repair-mechanism-v1-formal-failure-audit.json"
MARKDOWN_REPORT = REPO_ROOT / "benchmarks/reports/cpp-contract-driven-repair-mechanism-v1-formal-failure-audit.md"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-contract-repair-formal-failure-audit.schema.json"


def _load_module(name: str, path: Path):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


audit = _load_module("forge_formal_failure_audit_test", AUDIT_SCRIPT)
repair = _load_module("forge_formal_marker_repair_test", REPAIR_SCRIPT)


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_frozen_source_identity_covers_exactly_nine_files() -> None:
    assert len(audit.EXPECTED_INPUT_SHA256) == 9
    assert set(audit.EXPECTED_INPUT_SHA256) == {
        "attempts/01-clone-4d90a79086b9d5007c7ccbf5/attempt.json",
        "attempts/01-clone-4d90a79086b9d5007c7ccbf5/candidate.json",
        "attempts/01-clone-4d90a79086b9d5007c7ccbf5/experiment.jsonl",
        "attempts/01-clone-4d90a79086b9d5007c7ccbf5/result.json",
        "attempts/01-clone-4d90a79086b9d5007c7ccbf5/runtime-events.jsonl",
        "checkpoints/01-rnnoise-0.1.1-delivery-target/checkpoint.json",
        "checkpoints/01-rnnoise-0.1.1-delivery-target/experiment.jsonl",
        "markers/availability.json",
        "markers/batch.json",
    }
    assert audit.EXPECTED_FILE_COUNT == 9
    assert audit.EXPECTED_TOTAL_SIZE_BYTES == 66_466
    assert audit.INVENTORY_SHA256 == "24019a372a3b49fe6dc1b141da45f09f764639c253fc1ed16521341f3c6d2fb5"


def test_inventory_rejects_unexpected_and_drifted_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "markers/batch.json"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"frozen\n")
    reference = audit._reference(source, tmp_path)
    monkeypatch.setattr(audit, "EXPECTED_INPUT_SHA256", {"markers/batch.json": reference["sha256"]})
    monkeypatch.setattr(audit, "EXPECTED_FILE_COUNT", 1)
    monkeypatch.setattr(audit, "EXPECTED_TOTAL_SIZE_BYTES", source.stat().st_size)
    monkeypatch.setattr(audit, "INVENTORY_SHA256", audit._inventory_sha256([reference]))
    assert audit.verify_source_inventory(tmp_path) == [reference]

    unexpected = tmp_path / "attempts/unexpected.json"
    unexpected.parent.mkdir()
    unexpected.write_text("{}\n", encoding="utf-8")
    with pytest.raises(audit.FormalFailureAuditError, match="文件集合漂移"):
        audit.verify_source_inventory(tmp_path)
    unexpected.unlink()
    source.write_bytes(b"drifted\n")
    with pytest.raises(audit.FormalFailureAuditError, match="文件 SHA-256 漂移"):
        audit.verify_source_inventory(tmp_path)


def test_checkpoint_ledger_verifier_detects_hash_drift(tmp_path: Path) -> None:
    path = tmp_path / "experiment.jsonl"
    events = []
    previous = "0" * 64
    event_types = [
        "candidate.submit_started",
        "artifact.observed",
        "artifact.observed",
        "candidate.prefreeze_verification_completed",
        "candidate.submit_rejected",
    ]
    for sequence, event_type in enumerate(event_types, 1):
        payload = {"rejection_codes": ["target_mapping_invalid"]} if event_type == "candidate.submit_rejected" else {}
        event = {
            "schema_version": "agent-workflow-node-v1",
            "event_id": f"event:{sequence:032x}",
            "sequence": sequence,
            "timestamp": "2026-09-29T00:00:00+00:00",
            "task_id": "fixture",
            "attempt_id": "parent-01",
            "run_id": "run",
            "session_id": "session",
            "event_type": event_type,
            "payload": payload,
            "previous_hash": previous,
        }
        event_hash = hashlib.sha256(
            json.dumps(
                event,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
        event["event_hash"] = event_hash
        previous = event_hash
        events.append(event)
    path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in events),
        encoding="utf-8",
    )
    assert audit.verify_checkpoint_ledger(path)["event_count"] == 5
    events[2]["payload"] = {"drifted": True}
    path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in events),
        encoding="utf-8",
    )
    with pytest.raises(audit.FormalFailureAuditError, match="hash chain"):
        audit.verify_checkpoint_ledger(path)


def test_token_ledger_requires_model_identity_and_closed_totals() -> None:
    ledger = []
    for sequence in range(1, 6):
        ledger.append(
            {
                "request_sequence": sequence,
                "actual_model": "deepseek-flash",
                "model_identity_match": True,
                "response_received": True,
                "retry_eligible": False,
                "error_class": None,
                "input_tokens": 1,
                "output_tokens": 1,
                "total_tokens": 2,
            }
        )
    result = {
        "request_token_ledger": ledger,
        "recorded_input_tokens": 5,
        "recorded_output_tokens": 5,
        "recorded_total_tokens": 10,
    }
    monkeypatch_values = {
        "input_tokens": 44_561,
        "output_tokens": 8_423,
        "total_tokens": 52_984,
    }
    ledger[0].update(monkeypatch_values)
    for item in ledger[1:]:
        item.update(input_tokens=0, output_tokens=0, total_tokens=0)
    result.update(
        recorded_input_tokens=44_561,
        recorded_output_tokens=8_423,
        recorded_total_tokens=52_984,
    )
    assert audit.summarize_token_ledger(result)["request_attempts"] == 5
    ledger[1]["actual_model"] = "other"
    with pytest.raises(audit.FormalFailureAuditError, match="identity"):
        audit.summarize_token_ledger(result)


@pytest.mark.parametrize(
    "updates",
    (
        {"status": "complete", "error_class": None, "completed_at": "terminal"},
        {"completed_arm_count": 1, "provider_request_attempt_count": 5},
        {"status": "completed", "report_sha256": "a" * 64},
        {"status": "failed", "error_class": "FormalFatalError"},
    ),
)
def test_marker_repair_adapts_keyword_updates_atomically(tmp_path: Path, updates: dict) -> None:
    marker = tmp_path / "marker.json"
    marker.write_text('{"status":"started","updated_at":"initial"}\n')

    updated = repair.update_claimed_marker(marker, **updates)

    assert json.loads(marker.read_text()) == updated
    assert all(updated[key] == value for key, value in updates.items())
    assert updated["updated_at"] != "initial"
    assert repair.validate()["formal_attempts"] == 0


def test_committed_report_schema_markdown_and_claim_boundaries() -> None:
    report = _load_json(JSON_REPORT)
    schema = _load_json(SCHEMA_PATH)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(report)

    assert schema == audit.generate_schema(report)
    assert audit.render_markdown(report) == MARKDOWN_REPORT.read_text(encoding="utf-8")
    assert report["failure"]["classification"] == "formal_marker_terminalization_failed"
    assert report["observed_arm"]["strict_post_checkpoint_conversion"] is True
    assert report["execution_boundary"]["completed_arm_results"] == 1
    assert report["execution_boundary"]["continuation_allowed"] is False
    assert report["interpretation"]["treatment_effect_estimated"] is False


def test_committed_report_is_sanitized() -> None:
    report = _load_json(JSON_REPORT)
    serialized = json.dumps(report, ensure_ascii=False)
    audit._validate_report_sanitization(report)
    assert "/home/" not in serialized
    assert "/workspace/" not in serialized
    assert "api.deepseek.com" not in serialized
    assert len(report["source_integrity"]["files"]) == 9


@pytest.mark.skipif(not audit.DEFAULT_EVIDENCE_DIR.is_dir(), reason="冻结 formal failure evidence 未挂载")
def test_local_frozen_evidence_rebuilds_report_without_mutation() -> None:
    before = {path: audit.file_sha256(audit.DEFAULT_EVIDENCE_DIR / path) for path in audit.EXPECTED_INPUT_SHA256}
    report = audit.build_report()
    after = {path: audit.file_sha256(audit.DEFAULT_EVIDENCE_DIR / path) for path in audit.EXPECTED_INPUT_SHA256}
    assert report == _load_json(JSON_REPORT)
    assert before == after == audit.EXPECTED_INPUT_SHA256


def test_audit_source_has_no_provider_or_evidence_write_path() -> None:
    source = AUDIT_SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "create_chat_model",
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "execute_batch",
        "execute_arm",
        "_update_claimed_marker",
    ):
        assert forbidden not in source
    assert "ExperimentLedger.verify_path" in source
    assert repair.FROZEN_RUNNER_SHA256 == audit.RUNNER_FILE_SHA256
