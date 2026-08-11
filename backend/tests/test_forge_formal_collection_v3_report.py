from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from deerflow.compile.evidence import ExperimentLedger, new_evidence_id

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "forge_formal_collection_v3_report.py"
SPEC = importlib.util.spec_from_file_location("forge_formal_collection_v3_report", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
reporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reporter)


def _manifest(*, slots: int = 1, token_limit: int = 1000) -> dict:
    plan = [
        {
            "case_id": f"case-{index}",
            "condition_id": "richlab-gpt-5.5",
            "repetition": 1,
        }
        for index in range(slots)
    ]
    return {
        "benchmark": {"id": "formal-test"},
        "scope": {
            "languages": ["C", "C++"],
            "phase": "formal",
            "formal_comparison_enabled": False,
        },
        "conditions": [{"id": "richlab-gpt-5.5"}],
        "cases": [{"id": f"case-{index}"} for index in range(slots)],
        "collection_plan": plan,
        "authorization": {
            "network_observation": {"access_medium": "mobile_hotspot"},
            "budget_confirmation": {
                "maximum_recorded_tokens": token_limit,
                "enforcement": "stop_before_next_slot_when_recorded_total_reaches_limit",
            },
            "collection_constraints": {
                "authorized_slot_count": slots,
                "remaining_slots_require_additional_confirmation": True,
            },
        },
    }


def _canary(root: Path, *, passed: bool = True) -> None:
    path = root / "provider-canaries" / "provider_canary_test.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "document_type": "formal_provider_canary",
                "manifest_sha256": "1" * 64,
                "canary_id": "provider_canary_" + "a" * 32,
                "completed_at": "2000-01-01T00:00:00+00:00",
                "passed": passed,
                "conditions": [
                    {
                        "id": "richlab-gpt-5.5",
                        "model": "gpt-5.5",
                        "duration_ms": 10,
                        "passed": passed,
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _ledger(root: Path, *, index: int = 0, tokens: int = 100) -> Path:
    case_id = f"case-{index}"
    path = root / case_id / "richlab-gpt-5.5" / "rep-001" / f"physical_attempt_{index:032d}.jsonl"
    ledger = ExperimentLedger.create(
        path,
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={
            "policy": {
                "case_id": case_id,
                "condition": "richlab-gpt-5.5",
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
    ledger.append(
        "model.request_completed",
        {
            "actual_model": "gpt-5.5",
            "token_usage": {
                "input_tokens": tokens - 1,
                "output_tokens": 1,
                "total_tokens": tokens,
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
            "gate_recomputation_valid": True,
            "oracle_passed": True,
            "orphan_cleanup_succeeded": True,
            "session_finalization_succeeded": True,
            "status": "passed",
        },
    )
    return path


def _build(root: Path, manifest: dict) -> dict:
    return reporter.build_report(
        manifest,
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
    monkeypatch.setattr(reporter.protocol, "manifest_sha256", lambda _manifest: "1" * 64)


def test_complete_authorized_prefix_builds_report(tmp_path: Path) -> None:
    manifest = _manifest()
    _canary(tmp_path)
    _ledger(tmp_path)

    report = _build(tmp_path, manifest)

    assert report["collection"]["stop_reason"] == "authorized_batch_boundary_reached"
    assert report["collection"]["analyzed_slots"] == 1
    assert report["collection"]["recorded_total_tokens"] == 100
    assert report["canary"]["successful_reports"] == 1


def test_short_prefix_requires_recorded_token_boundary(tmp_path: Path) -> None:
    manifest = _manifest(slots=2, token_limit=101)
    _canary(tmp_path)
    _ledger(tmp_path, tokens=100)

    with pytest.raises(reporter.ReportError, match="short authorized prefix"):
        _build(tmp_path, manifest)


def test_short_prefix_at_token_boundary_is_valid(tmp_path: Path) -> None:
    manifest = _manifest(slots=2, token_limit=100)
    _canary(tmp_path)
    _ledger(tmp_path, tokens=100)

    report = _build(tmp_path, manifest)

    assert report["collection"]["stop_reason"] == "recorded_token_boundary_reached"
    assert report["interpretation"]["slots_8_to_10_not_created"] is True


def test_non_contiguous_prefix_is_rejected(tmp_path: Path) -> None:
    manifest = _manifest(slots=2, token_limit=100)
    _canary(tmp_path)
    _ledger(tmp_path, index=1, tokens=100)

    with pytest.raises(reporter.ReportError, match="contiguous frozen schedule prefix"):
        _build(tmp_path, manifest)


def test_successful_canary_is_required(tmp_path: Path) -> None:
    manifest = _manifest()
    _canary(tmp_path, passed=False)
    _ledger(tmp_path)

    with pytest.raises(reporter.ReportError, match="successful dual-provider canary"):
        _build(tmp_path, manifest)


def test_committed_markdown_matches_machine_report() -> None:
    json_path = REPO_ROOT / "benchmarks" / "reports" / "cpp-formal-v3-initial-batch.json"
    markdown_path = REPO_ROOT / "benchmarks" / "reports" / "cpp-formal-v3-initial-batch.md"
    report = json.loads(json_path.read_text(encoding="utf-8"))

    assert report["collection"]["analyzed_slots"] == 7
    assert report["collection"]["oracle_passed"] == 4
    assert report["collection"]["recorded_total_tokens"] == 1_700_577
    assert report["collection"]["stop_reason"] == "recorded_token_boundary_reached"
    assert markdown_path.read_text(encoding="utf-8") == reporter.render_markdown(report)
