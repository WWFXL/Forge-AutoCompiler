"""Issue #351 Stage C v8 结果冻结与只读审计测试。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest

from deerflow.compile.evidence import ExperimentLedger

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
SCRIPT_PATH = SCRIPTS / "forge_stage_c_v8_workspace_remediation_result_audit.py"
JSON_REPORT = REPO_ROOT / "benchmarks/reports/cpp-stage-c-v8-workspace-remediation-result-audit.json"
MARKDOWN_REPORT = REPO_ROOT / "benchmarks/reports/cpp-stage-c-v8-workspace-remediation-result-audit.md"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-stage-c-v8-workspace-remediation-result-audit.schema.json"


def _load_module():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("forge_stage_c_v8_workspace_remediation_result_audit_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


audit = _load_module()


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_frozen_source_identity_covers_exactly_sixteen_files() -> None:
    assert len(audit.EXPECTED_INPUT_SHA256) == 16
    assert set(audit.EXPECTED_INPUT_SHA256) == {
        "attempts/01-theora/attempt.json",
        "attempts/01-theora/experiment.jsonl",
        "attempts/01-theora/result.json",
        "attempts/02-json-c/attempt.json",
        "attempts/02-json-c/experiment.jsonl",
        "attempts/02-json-c/result.json",
        "attempts/03-libjpeg-turbo/attempt.json",
        "attempts/03-libjpeg-turbo/experiment.jsonl",
        "attempts/03-libjpeg-turbo/result.json",
        "attempts/04-oatpp/attempt.json",
        "attempts/04-oatpp/experiment.jsonl",
        "attempts/04-oatpp/result.json",
        "markers/batch.json",
        "markers/reachability.json",
        "reports/canary.json",
        "reports/reachability.json",
    }
    assert audit.EXPECTED_FILE_COUNT == 16
    assert audit.EXPECTED_TOTAL_SIZE_BYTES == 631_570
    assert audit.INVENTORY_SHA256 == "afe607e075509eee1999a65f4c485b0995959a1f026bf22f3f6ff7673d6b14a7"


def test_inventory_digest_matches_sha256sum_line_contract(tmp_path: Path) -> None:
    first = tmp_path / "a.json"
    second = tmp_path / "nested/b.jsonl"
    second.parent.mkdir()
    first.write_bytes(b"a\n")
    second.write_bytes(b"b\n")
    references = [audit._reference(first, tmp_path), audit._reference(second, tmp_path)]
    expected_payload = (f"{hashlib.sha256(first.read_bytes()).hexdigest()}  ./a.json\n{hashlib.sha256(second.read_bytes()).hexdigest()}  ./nested/b.jsonl\n").encode()
    assert audit._inventory_sha256(references) == hashlib.sha256(expected_payload).hexdigest()


def test_source_inventory_rejects_unexpected_or_drifted_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "reports/canary.json"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"frozen\n")
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    references = [audit._reference(source, tmp_path)]
    monkeypatch.setattr(audit, "EXPECTED_INPUT_SHA256", {"reports/canary.json": source_sha256})
    monkeypatch.setattr(audit, "EXPECTED_FILE_COUNT", 1)
    monkeypatch.setattr(audit, "EXPECTED_TOTAL_SIZE_BYTES", source.stat().st_size)
    monkeypatch.setattr(audit, "INVENTORY_SHA256", audit._inventory_sha256(references))

    assert audit.verify_source_inventory(tmp_path) == references
    unexpected = tmp_path / "reports/unexpected.json"
    unexpected.write_text("{}\n", encoding="utf-8")
    with pytest.raises(audit.StageCV8ResultAuditError, match="文件集合漂移"):
        audit.verify_source_inventory(tmp_path)
    unexpected.unlink()
    source.write_bytes(b"drifted\n")
    with pytest.raises(audit.StageCV8ResultAuditError, match="文件 SHA-256 漂移"):
        audit.verify_source_inventory(tmp_path)


def test_token_ledger_requires_contiguous_requests_and_closed_totals() -> None:
    ledger = [
        {"request_sequence": 1, "input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        {"request_sequence": 2, "input_tokens": 20, "output_tokens": 3, "total_tokens": 23},
    ]
    assert audit.summarize_token_ledger(ledger, expected_requests=2, expected_total=35, label="fixture") == {
        "requests": 2,
        "input_tokens": 30,
        "output_tokens": 5,
        "total_tokens": 35,
    }
    drifted = [dict(item) for item in ledger]
    drifted[1]["total_tokens"] = 24
    with pytest.raises(audit.StageCV8ResultAuditError, match="单请求 token 不闭合"):
        audit.summarize_token_ledger(drifted, expected_requests=2, expected_total=36, label="fixture")


def test_ledger_audit_requires_unique_terminal_result_binding(tmp_path: Path) -> None:
    result_path = tmp_path / "result.json"
    result_path.write_text('{"status":"passed"}\n', encoding="utf-8")
    result_sha256 = audit.file_sha256(result_path)
    ledger_path = tmp_path / "experiment.jsonl"
    ledger = ExperimentLedger.create(
        ledger_path,
        experiment_id=f"fixture_{'a' * 32}",
        physical_attempt_id=f"fixture_{'b' * 32}",
        context={},
    )
    ledger.append("experiment.completed", {"result_sha256": result_sha256, "status": "passed"})

    summary = audit.audit_ledger(ledger_path, result_path)

    assert summary["event_count"] == 2
    assert summary["terminal_event"] == "experiment.completed"
    assert summary["completion_result_sha256"] == result_sha256
    result_path.write_text('{"status":"drifted"}\n', encoding="utf-8")
    with pytest.raises(audit.StageCV8ResultAuditError, match="completed 终态"):
        audit.audit_ledger(ledger_path, result_path)


def test_committed_report_schema_markdown_and_claim_boundaries() -> None:
    report = _load_json(JSON_REPORT)
    schema = _load_json(SCHEMA_PATH)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(report)

    assert schema == audit.generate_schema(report)
    assert audit.render_markdown(report) == MARKDOWN_REPORT.read_text(encoding="utf-8")
    assert report["identity"]["manifest_canonical_sha256"] == audit.MANIFEST_SHA256
    assert report["source_integrity"]["inventory_sha256"] == audit.INVENTORY_SHA256
    assert report["batch"]["strict_success_count"] == 4
    assert report["batch"]["s0_s5_passed"] == {name: 4 for name in audit.LAYER_NAMES}
    assert report["batch"]["total_tokens_with_reachability"] == {
        "requests": 37,
        "input_tokens": 260_873,
        "output_tokens": 19_115,
        "total_tokens": 279_988,
    }
    assert report["interpretation"]["treatment_effect_estimated"] is False
    assert report["execution_boundary"]["rerun_allowed"] is False


def test_committed_report_records_only_bounded_whitelist() -> None:
    report = _load_json(JSON_REPORT)
    serialized = json.dumps(report, ensure_ascii=False)
    audit._validate_report_sanitization(report)

    assert not any(key in serialized for key in ('"prompt"', '"messages"', '"response"', '"stdout"', '"stderr"', '"session_id"'))
    assert "/home/" not in serialized
    assert "/workspace/" not in serialized
    assert "api.deepseek.com" not in serialized
    assert len(report["source_integrity"]["files"]) == 16
    assert report["tasks"][2]["submit"] == {
        "attempts": 2,
        "rejection_codes": ["target_mapping_invalid"],
        "rejection_evidence_count": 1,
        "same_attempt_repair_observed": True,
    }


@pytest.mark.skipif(not audit.DEFAULT_EVIDENCE_DIR.is_dir(), reason="冻结 Stage C v8 evidence 未挂载")
def test_local_frozen_evidence_rebuilds_committed_reports_without_mutation() -> None:
    before = {path: audit.file_sha256(audit.DEFAULT_EVIDENCE_DIR / path) for path in audit.EXPECTED_INPUT_SHA256}

    report = audit.build_report()

    after = {path: audit.file_sha256(audit.DEFAULT_EVIDENCE_DIR / path) for path in audit.EXPECTED_INPUT_SHA256}
    assert report == _load_json(JSON_REPORT)
    assert before == after == audit.EXPECTED_INPUT_SHA256


def test_source_has_no_provider_docker_or_formal_execution_path() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "ExperimentLedger.verify_path" in source
    for forbidden in (
        "create_chat_model",
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "os.environ",
        "docker.from_env",
        "subprocess",
        "execute_reachability",
        "run_batch",
        "execute_attempt",
    ):
        assert forbidden not in source
