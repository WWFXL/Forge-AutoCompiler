"""Issue #379 mechanism v2 formal checkpoint failure 只读审计测试。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
AUDIT_SCRIPT = SCRIPTS / "forge_contract_driven_repair_mechanism_v2_formal_failure_audit.py"
JSON_REPORT = REPO_ROOT / "benchmarks/reports/cpp-contract-driven-repair-mechanism-v2-formal-failure-audit.json"
MARKDOWN_REPORT = REPO_ROOT / "benchmarks/reports/cpp-contract-driven-repair-mechanism-v2-formal-failure-audit.md"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-contract-driven-repair-mechanism-v2-formal-failure-audit.schema.json"


def _load_module(name: str, path: Path):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


audit = _load_module("forge_v2_formal_failure_audit_test", AUDIT_SCRIPT)


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_frozen_source_layout_covers_exactly_seventy_files() -> None:
    manifest = audit.protocol.load_manifest()
    files, directories = audit._expected_evidence_layout(manifest)

    assert len(files) == audit.EXPECTED_FILE_COUNT == 70
    assert len(directories) == 19
    assert audit.EXPECTED_TOTAL_SIZE_BYTES == 689_742
    assert audit.INVENTORY_SHA256 == "5c885b2a9d2bb2156f28913365c73b32d11a60ffcce7804d85d6cae718eb9d11"
    assert "attempts/12-clone-3071461291e81d129ad0fed6/result.json" in files
    assert all("attempts/13-" not in path for path in files)
    assert all("checkpoints/05-" not in path for path in files)


def test_checkpoint_ledger_verifier_detects_hash_drift(tmp_path: Path) -> None:
    path = tmp_path / "experiment.jsonl"
    event_types = [
        "candidate.submit_started",
        "artifact.observed",
        "artifact.observed",
        "candidate.prefreeze_verification_completed",
        "candidate.submit_rejected",
    ]
    events = []
    previous = "0" * 64
    for sequence, event_type in enumerate(event_types, 1):
        payload = {"rejection_codes": ["target_mapping_invalid"]} if event_type == "candidate.submit_rejected" else {}
        event = {
            "schema_version": "agent-workflow-node-v1",
            "event_id": f"event:{sequence:032x}",
            "sequence": sequence,
            "timestamp": "2026-09-30T00:00:00+00:00",
            "task_id": "fixture",
            "attempt_id": "parent-01",
            "run_id": "run",
            "session_id": "session",
            "event_type": event_type,
            "payload": payload,
            "previous_hash": previous,
        }
        event_hash = hashlib.sha256(json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        event["event_hash"] = event_hash
        previous = event_hash
        events.append(event)
    path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in events),
        encoding="utf-8",
    )

    summary = audit._verify_checkpoint_ledger(
        path,
        stratum="delivery_target",
        rejection_code="target_mapping_invalid",
    )
    assert summary["event_count"] == 5
    events[2]["payload"] = {"drifted": True}
    path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in events),
        encoding="utf-8",
    )
    with pytest.raises(audit.FormalFailureAuditError, match="hash chain"):
        audit._verify_checkpoint_ledger(
            path,
            stratum="delivery_target",
            rejection_code="target_mapping_invalid",
        )


def test_token_ledger_requires_closed_totals_and_model_identity() -> None:
    expected = audit.EXPECTED_ARM_OBSERVATIONS[1]
    request_count, input_tokens, output_tokens, total_tokens = expected[3:7]
    ledger = []
    for sequence in range(1, request_count + 1):
        ledger.append(
            {
                "request_sequence": sequence,
                "actual_model": "deepseek-flash",
                "model_identity_match": True,
                "response_received": True,
                "retry_eligible": False,
                "tool_side_effect_count": 0,
                "error_class": None,
                "input_tokens": input_tokens if sequence == 1 else 0,
                "output_tokens": output_tokens if sequence == 1 else 0,
                "total_tokens": total_tokens if sequence == 1 else 0,
            }
        )
    result = {
        "request_token_ledger": ledger,
        "provider_request_attempts": request_count,
        "recorded_input_tokens": input_tokens,
        "recorded_output_tokens": output_tokens,
        "recorded_total_tokens": total_tokens,
    }

    assert audit._verify_token_ledger(result, expected)["total_tokens"] == 46_972
    drifted = deepcopy(result)
    drifted["request_token_ledger"][1]["actual_model"] = "other"
    with pytest.raises(audit.FormalFailureAuditError, match="identity"):
        audit._verify_token_ledger(drifted, expected)


def test_incomplete_analysis_preserves_missingness_and_null_tests() -> None:
    manifest = audit.protocol.load_manifest()
    arms = []
    for checkpoint in manifest["schedule"]["checkpoints"][:4]:
        strict = checkpoint["stratum"] == "delivery_target"
        arms.extend(
            {
                "checkpoint_id": checkpoint["checkpoint_id"],
                "task_id": checkpoint["task_id"],
                "stratum": checkpoint["stratum"],
                "condition": arm["condition"],
                "strict_post_checkpoint_conversion": strict,
            }
            for arm in checkpoint["arms"]
        )

    result = audit._build_descriptive_analysis(arms, manifest)

    assert result["observed_complete_project_count"] == 2
    assert result["missing_checkpoint_count"] == 8
    assert result["primary_test"] is None
    assert result["secondary_test"] is None
    assert result["missing_arms_imputed_as_zero"] is False
    for comparison in result["comparisons"].values():
        assert comparison["observed_complete_estimate"] == "0"
        assert comparison["best_worst_identification_interval"] == {
            "lower": "-2/3",
            "upper": "2/3",
        }


def test_committed_report_schema_markdown_and_claim_boundaries() -> None:
    report = _load_json(JSON_REPORT)
    schema = _load_json(SCHEMA_PATH)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(report)

    assert schema == audit.generate_schema(report)
    assert audit.render_markdown(report) == MARKDOWN_REPORT.read_text(encoding="utf-8")
    assert report["failure"]["classification"] == "checkpoint_target_mapping_cardinality_failure"
    assert report["batch_terminal"]["completed_arm_count"] == 12
    assert report["batch_terminal"]["completed_checkpoint_count"] == 4
    assert report["batch_terminal"]["tokens"] == {
        "request_attempts": 75,
        "input_tokens": 907_258,
        "output_tokens": 161_276,
        "total_tokens": 1_068_534,
    }
    assert report["analysis"]["primary_test"] is None
    assert report["analysis"]["secondary_test"] is None
    assert report["analysis"]["treatment_effect_estimated"] is False
    assert report["execution_boundary"]["continuation_allowed"] is False


def test_committed_report_is_sanitized() -> None:
    report = _load_json(JSON_REPORT)
    serialized = json.dumps(report, ensure_ascii=False)

    audit._validate_report_sanitization(report)
    assert "/home/" not in serialized
    assert "/workspace/" not in serialized
    assert "api.deepseek.com" not in serialized
    assert len(report["source_integrity"]["files"]) == 70


def test_failure_contract_binds_frozen_engine_and_lz4_targets() -> None:
    failure = audit._verify_failure_contract(audit.protocol.load_manifest())

    assert failure["checkpoint_id"] == "lz4:delivery_target"
    assert failure["required_compiled_target_cardinality"] == 1
    assert failure["frozen_contract_compiled_targets"] == [
        "bin/lz4",
        "lib/liblz4.a",
    ]
    assert failure["sequence_13_attempt_created"] is False


@pytest.mark.skipif(
    not audit.DEFAULT_EVIDENCE_DIR.is_dir(),
    reason="冻结 mechanism v2 formal failure evidence 未挂载",
)
def test_local_frozen_evidence_rebuilds_report_without_mutation() -> None:
    manifest = audit.protocol.load_manifest()
    report = audit.build_report()
    after = audit.verify_source_inventory(audit.DEFAULT_EVIDENCE_DIR, manifest)

    assert report == _load_json(JSON_REPORT)
    assert after == report["source_integrity"]["files"]


def test_audit_source_has_no_provider_or_formal_execution_path() -> None:
    source = AUDIT_SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "create_chat_model",
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "execute_batch",
        "execute_arm",
        "_capture_checkpoint(",
        "_update_claimed_marker",
    ):
        assert forbidden not in source
    assert "ExperimentLedger.verify_path" in source
    assert audit.RUNNER_FILE_SHA256 == audit.file_sha256(audit.V2_RUNNER)
    assert audit.FROZEN_ENGINE_FILE_SHA256 == audit.file_sha256(audit.FROZEN_ENGINE)
