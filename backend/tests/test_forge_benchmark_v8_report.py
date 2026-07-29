from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from deerflow.compile.evidence import EvidenceError, ExperimentLedger, new_evidence_id

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_SCRIPT = REPO_ROOT / "scripts" / "forge_benchmark_v8_report.py"

SPEC = importlib.util.spec_from_file_location("forge_benchmark_v8_report", REPORT_SCRIPT)
assert SPEC is not None and SPEC.loader is not None
forge_benchmark_v8_report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(forge_benchmark_v8_report)


def _manifest() -> dict:
    return {
        "benchmark": {"id": "forge-cpp-clean-replay-pilot-v8"},
        "scope": {
            "languages": ["C", "C++"],
            "phase": "pilot",
            "formal_comparison_enabled": False,
        },
        "conditions": [{"id": "richlab-gpt-5.5"}],
        "collection_plan": [
            {
                "case_id": "fmt",
                "condition_id": "richlab-gpt-5.5",
                "repetition": 1,
            }
        ],
        "cases": [{"id": "fmt"}],
    }


def _create_terminal_ledger(
    root: Path,
    *,
    condition: str = "richlab-gpt-5.5",
    name: str = "physical_attempt_a",
    recorded_gate_valid: bool = True,
) -> Path:
    path = root / "fmt" / condition / "rep-001" / f"{name}.jsonl"
    ledger = ExperimentLedger.create(
        path,
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={
            "policy": {
                "case_id": "fmt",
                "condition": condition,
                "repetition": 1,
                "manifest_sha256": "1" * 64,
                "model_name": "gpt-5.5",
            },
            "preflight_checks": {
                "network_present": True,
                "endpoint_reachable": True,
            },
        },
    )
    ledger.append("oracle.completed", {"passed": True, "classification": None})
    ledger.append(
        "orphan.reconciled",
        {
            "cleanup_succeeded": True,
            "orphan_count": 0,
            "removed_count": 0,
            "scan_succeeded": True,
        },
    )
    ledger.append(
        "experiment.completed",
        {
            "gate_recomputation_valid": recorded_gate_valid,
            "oracle_passed": True,
            "orphan_cleanup_succeeded": True,
            "session_finalization_succeeded": True,
            "status": "passed",
        },
    )
    return path


def _build_report(root: Path, manifest: dict | None = None) -> dict:
    return forge_benchmark_v8_report.build_report(
        manifest or _manifest(),
        root,
        gate_recomputer=lambda _events: {
            "valid": True,
            "failure_domains": {
                "model_endpoint": None,
                "agent_tool": None,
                "build": None,
                "submit_replay": None,
                "completion": None,
            },
        },
        oracle_runner=lambda _manifest, _events: {
            "passed": True,
            "classification": None,
        },
    )


@pytest.fixture(autouse=True)
def _stable_manifest_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        forge_benchmark_v8_report.protocol_v8,
        "manifest_sha256",
        lambda _manifest: "1" * 64,
    )


def test_build_report_requires_every_collection_slot(tmp_path: Path) -> None:
    with pytest.raises(forge_benchmark_v8_report.ReportError, match="Missing collection ledger"):
        _build_report(tmp_path)


def test_build_report_rejects_duplicate_collection_ledgers(tmp_path: Path) -> None:
    first = _create_terminal_ledger(tmp_path)
    shutil.copy2(first, first.with_name("physical_attempt_b.jsonl"))

    with pytest.raises(forge_benchmark_v8_report.ReportError, match="multiple ledgers"):
        _build_report(tmp_path)


def test_build_report_rejects_non_collection_condition(tmp_path: Path) -> None:
    _create_terminal_ledger(tmp_path)
    _create_terminal_ledger(tmp_path, condition="unexpected-model", name="physical_attempt_b")

    with pytest.raises(forge_benchmark_v8_report.ReportError, match="non-collection condition"):
        _build_report(tmp_path)


def test_build_report_rejects_corrupted_hash_chain(tmp_path: Path) -> None:
    path = _create_terminal_ledger(tmp_path)
    path.write_text(
        path.read_text(encoding="utf-8").replace('"status":"passed"', '"status":"failed"'),
        encoding="utf-8",
    )

    with pytest.raises(EvidenceError, match="invalid event digest"):
        _build_report(tmp_path)


def test_build_report_rejects_unterminated_ledger(tmp_path: Path) -> None:
    path = _create_terminal_ledger(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")

    with pytest.raises(forge_benchmark_v8_report.ReportError, match="must end with experiment.completed"):
        _build_report(tmp_path)


def test_build_report_keeps_historical_baseline_out_of_v8_denominator(tmp_path: Path) -> None:
    _create_terminal_ledger(tmp_path)
    _create_terminal_ledger(tmp_path, condition="baseline", name="physical_attempt_b")

    report = _build_report(tmp_path)

    assert report["collection"]["planned_slots"] == 1
    assert report["collection"]["oracle_passed"] == 1
    assert report["historical_baseline_ledgers"] == {
        "discovered": 1,
        "hash_chain_valid": 1,
        "terminal_completed": 1,
        "orphan_cleanup_succeeded": 1,
        "included_in_v8_outcome_denominator": False,
    }
    assert report["network_interpretation"]["access_medium_recorded"] is False
    assert "手机热点" in forge_benchmark_v8_report.render_markdown(report)


def test_build_report_preserves_historical_terminal_gate_result(tmp_path: Path) -> None:
    _create_terminal_ledger(tmp_path, recorded_gate_valid=False)

    report = _build_report(tmp_path)

    assert report["collection"]["gate_recomputation_valid"] == 1
    assert report["collection"]["recorded_terminal_gate_recomputation_valid"] == 0


def test_committed_markdown_matches_machine_report() -> None:
    report_path = REPO_ROOT / "benchmarks" / "reports" / "cpp-pilot-v8-descriptive.json"
    markdown_path = REPO_ROOT / "benchmarks" / "reports" / "cpp-pilot-v8-descriptive.md"
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["collection"]["planned_slots"] == 10
    assert report["collection"]["oracle_passed"] == 6
    assert report["collection"]["recorded_terminal_gate_recomputation_valid"] == 9
    assert report["collection"]["actual_model_matches"] == 10
    assert markdown_path.read_text(encoding="utf-8") == forge_benchmark_v8_report.render_markdown(report)
