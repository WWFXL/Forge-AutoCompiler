"""Issue #421 动态预算控制轨迹可辨识性审计测试。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_dynamic_budget_identifiability_audit.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-dynamic-budget-identifiability-audit-v1.json"
JSON_REPORT_PATH = REPO_ROOT / "benchmarks" / "reports" / "cpp-dynamic-budget-identifiability-audit-v1.json"
MARKDOWN_REPORT_PATH = REPO_ROOT / "benchmarks" / "reports" / "cpp-dynamic-budget-identifiability-audit-v1.md"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "forge_dynamic_budget_identifiability_audit_test",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


audit = _load_module()


def test_frozen_inputs_produce_stop_decision() -> None:
    report = audit.build_report(REPO_ROOT, MANIFEST_PATH)

    assert report["passed"] is False
    assert report["decision"] == "stop_before_dynamic_budget_controller_implementation"
    assert [gate["passed"] for gate in report["gates"]] == [
        True,
        True,
        False,
        False,
        False,
        False,
        False,
        False,
    ]


def test_formal_comparison_is_matched_but_not_sequential() -> None:
    report = audit.build_report(REPO_ROOT, MANIFEST_PATH)
    formal = report["source_audits"]["jev_formal_comparison_v6"]

    assert formal["arm_count"] == 72
    assert formal["state_count"] == 12
    assert formal["ledger_result_matches"] == 72
    assert formal["complete_terminal_cost_rows"] == 71
    assert formal["incomplete_terminal_cost_rows"] == [
        {
            "task_id": "redis",
            "repetition": 2,
            "policy": "jev_gate_agent",
            "terminal_classification": "evaluated_failure",
            "jev_error_class": "TypeSafeAPIConnectionError",
            "jev_model_requests": 1,
            "missing_usage_fields": ["input_tokens", "output_tokens", "cost_usd"],
        }
    ]
    assert formal["policy_coverage_passed"] is True
    assert formal["control_decisions_per_trajectory"] == {"minimum": 1, "maximum": 1}
    assert formal["checkpoint_bound_state_count"] == 0
    assert formal["explicit_decision_budget_snapshot_count"] == 0


def test_action_audit_excludes_composite_fallback_from_pure_direct() -> None:
    report = audit.build_report(REPO_ROOT, MANIFEST_PATH)
    formal = report["source_audits"]["jev_formal_comparison_v6"]

    assert formal["pure_action_counts"] == {
        "composite_direct_then_escalate": 16,
        "direct": 29,
        "escalate": 27,
    }
    assert formal["state_action_counts"]["cc65"] == {
        "direct": 0,
        "escalate": 4,
        "stop": 0,
        "composite_direct_then_escalate": 2,
    }
    assert all(counts["stop"] == 0 for counts in formal["state_action_counts"].values())
    assert formal["action_support_passed"] is False


def test_historical_checkpoints_only_establish_capture_capability() -> None:
    report = audit.build_report(REPO_ROOT, MANIFEST_PATH)
    checkpoints = report["source_audits"]["historical_checkpoint_capability"]

    assert checkpoints["checkpoint_count"] == 4
    assert checkpoints["all_environment_hash_bound"] is True
    assert checkpoints["all_remaining_budget_bound"] is True
    assert checkpoints["relevant_action_labels"] == []


def test_source_hash_drift_fails_closed(tmp_path: Path) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["sources"]["jev_formal_report"]["file_sha256"] = "0" * 64
    drifted = tmp_path / "manifest.json"
    drifted.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(audit.AuditError, match="SHA-256"):
        audit.build_report(REPO_ROOT, drifted)


def test_rendered_report_keeps_claim_boundary() -> None:
    report = audit.build_report(REPO_ROOT, MANIFEST_PATH)
    markdown = audit.render_markdown(report)

    assert "这不是动态预算方向的负效果结论" in markdown
    assert "不能支持" in markdown
    assert "动态预算 controller 的成功率、成本或时间效果" in markdown


def test_committed_reports_are_deterministically_rebuilt() -> None:
    report = audit.build_report(REPO_ROOT, MANIFEST_PATH)

    assert json.loads(JSON_REPORT_PATH.read_text(encoding="utf-8")) == report
    assert MARKDOWN_REPORT_PATH.read_text(encoding="utf-8") == audit.render_markdown(report)
