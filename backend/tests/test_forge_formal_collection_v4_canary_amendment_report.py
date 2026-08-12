from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "forge_formal_collection_v4_canary_amendment_report.py"
SPEC = importlib.util.spec_from_file_location(
    "forge_formal_collection_v4_canary_amendment_report_test",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
reporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reporter)


def _parent_report() -> dict:
    return {
        "report_version": "parent",
        "benchmark_id": "forge-cpp-formal-v4-canary-amendment",
        "manifest_sha256": "1" * 64,
        "scope": {"paired_primary_eligible": True},
        "authorization": {},
        "canary": {},
        "collection": {
            "analyzed_slots": 6,
            "authorized_slots": 6,
            "stop_reason": "authorized_complete_project_block_reached",
            "complete_project_block": True,
            "oracle_passed": 6,
            "orphan_count": 0,
            "ledger_hash_chain_valid": 6,
            "recorded_total_tokens": 100,
            "recorded_token_limit": 980_000,
        },
        "failure_event_counts": {},
        "conditions": [],
        "attempts": [],
        "interpretation": {},
        "limitations": [],
    }


def test_report_adds_diagnostics_and_preserved_legacy_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_protocol = reporter.parent_report.protocol
    original_runner = reporter.parent_report.runner
    monkeypatch.setattr(
        reporter.parent_report,
        "build_report",
        lambda *args, **kwargs: _parent_report(),
    )
    monkeypatch.setattr(
        reporter.runner,
        "_load_diagnostic_summary",
        lambda *args, **kwargs: {"passed": True, "conditions": []},
    )
    monkeypatch.setattr(
        reporter.runner,
        "_verify_legacy_terminal",
        lambda *args, **kwargs: {"status": "failed", "formal_ledger_count": 0},
    )

    report = reporter.build_report(
        {"benchmark": {"id": "forge-cpp-formal-v4-canary-amendment"}},
        tmp_path,
        diagnostic_dir=tmp_path / "diagnostics",
        legacy_evidence_dir=tmp_path / "legacy",
    )

    assert report["report_version"] == reporter.REPORT_VERSION
    assert report["diagnostics"]["passed"] is True
    assert report["superseded_canary_terminal"]["status"] == "failed"
    assert report["interpretation"]["diagnostics_excluded_from_formal_denominator"] is True
    assert reporter.parent_report.protocol is original_protocol
    assert reporter.parent_report.runner is original_runner


def test_parent_report_globals_are_restored_after_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_protocol = reporter.parent_report.protocol
    original_runner = reporter.parent_report.runner

    def fail(*args, **kwargs):
        raise reporter.ReportError("invalid evidence")

    monkeypatch.setattr(reporter.parent_report, "build_report", fail)

    with pytest.raises(reporter.ReportError, match="invalid evidence"):
        reporter.build_report({}, tmp_path)

    assert reporter.parent_report.protocol is original_protocol
    assert reporter.parent_report.runner is original_runner


def test_markdown_is_deterministic_and_documents_separation() -> None:
    report = _parent_report()
    report["diagnostics"] = {"passed": True}
    report["superseded_canary_terminal"] = {"status": "failed"}

    first = reporter.render_markdown(report)
    second = reporter.render_markdown(json.loads(json.dumps(report, sort_keys=True)))

    assert first == second
    assert "有限诊断与 formal evidence 分目录保存" in first
    assert "旧 canary 失败 marker" in first
    assert "forge_formal_collection_v4_canary_amendment_report.py" in first
