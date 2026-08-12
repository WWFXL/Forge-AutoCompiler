from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from deerflow.compile.evidence import ExperimentLedger, new_evidence_id

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "forge_formal_collection_v4_authorized_report.py"
SPEC = importlib.util.spec_from_file_location(
    "forge_formal_collection_v4_authorized_report_test",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
reporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reporter)

ORDERS = [1, 2, 73, 74, 153, 154]
SLOTS = [
    ("richlab-gpt-5.5", 1),
    ("deepseek-v4-flash", 1),
    ("deepseek-v4-flash", 2),
    ("richlab-gpt-5.5", 2),
    ("deepseek-v4-flash", 3),
    ("richlab-gpt-5.5", 3),
]


def _manifest(*, token_limit: int = 1_000) -> dict:
    return {
        "benchmark": {"id": "forge-cpp-formal-v4-authorized-initial-block"},
        "scope": {
            "languages": ["C", "C++"],
            "phase": "formal_collection_v4_authorized_initial_block",
            "formal_comparison_enabled": True,
        },
        "conditions": [
            {"id": "richlab-gpt-5.5"},
            {"id": "deepseek-v4-flash"},
        ],
        "cases": [{"id": "cppitertools"}],
        "collection_plan": [
            {
                "order": order,
                "case_id": "cppitertools",
                "condition_id": condition,
                "repetition": repetition,
            }
            for order, (condition, repetition) in zip(ORDERS, SLOTS, strict=True)
        ],
        "authorization": {
            "network_observation": {"access_medium": "mobile_hotspot"},
            "budget_confirmation": {
                "maximum_recorded_tokens": token_limit,
                "enforcement": "stop_before_next_slot_when_recorded_total_reaches_limit",
            },
            "collection_constraints": {
                "authorized_schedule_orders": ORDERS,
                "remaining_slots_require_additional_confirmation": True,
            },
        },
    }


def _canary(root: Path, *, marker_status: str = "passed") -> None:
    directory = root / "provider-canaries"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "provider_canary_test.json").write_text(
        json.dumps(
            {
                "document_type": "formal_provider_canary",
                "manifest_sha256": "1" * 64,
                "canary_id": "provider_canary_" + "a" * 32,
                "completed_at": "2000-01-01T00:00:00+00:00",
                "passed": True,
                "conditions": [
                    {
                        "id": condition,
                        "model": model,
                        "duration_ms": 10,
                        "passed": True,
                    }
                    for condition, model in (
                        ("richlab-gpt-5.5", "gpt-5.5"),
                        ("deepseek-v4-flash", "deepseek-v4-flash"),
                    )
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (directory / "formal-v4-provider-canary-attempt.json").write_text(
        json.dumps(
            {
                "schema_version": "formal-provider-canary-attempt-1.0.0",
                "document_type": "formal_provider_canary_attempt",
                "benchmark_id": "forge-cpp-formal-v4-authorized-initial-block",
                "manifest_sha256": "1" * 64,
                "status": marker_status,
                "error_class": None,
                "updated_at": "2000-01-01T00:00:00+00:00",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _ledger(root: Path, *, slot_index: int, tokens: int = 100) -> Path:
    condition, repetition = SLOTS[slot_index]
    path = root / "cppitertools" / condition / f"rep-{repetition:03d}" / f"physical_attempt_{slot_index:032d}.jsonl"
    model = "gpt-5.5" if condition == "richlab-gpt-5.5" else "deepseek-v4-flash"
    ledger = ExperimentLedger.create(
        path,
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={
            "policy": {
                "case_id": "cppitertools",
                "condition": condition,
                "repetition": repetition,
                "manifest_sha256": "1" * 64,
                "model_name": model,
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
            "actual_model": model,
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
    monkeypatch.setattr(
        reporter.protocol,
        "manifest_sha256",
        lambda _manifest: "1" * 64,
    )


def test_complete_six_slot_block_is_paired_primary_eligible(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    _canary(tmp_path)
    for slot_index in range(6):
        _ledger(tmp_path, slot_index=slot_index)

    report = _build(tmp_path, manifest)

    assert report["collection"]["stop_reason"] == ("authorized_complete_project_block_reached")
    assert report["collection"]["complete_project_block"] is True
    assert report["scope"]["paired_primary_eligible"] is True
    assert report["collection"]["recorded_total_tokens"] == 600
    assert report["collection"]["gate_recomputation_valid"] == 6
    assert [attempt["schedule_order"] for attempt in report["attempts"]] == ORDERS


def test_short_prefix_at_token_boundary_is_descriptive_only(tmp_path: Path) -> None:
    manifest = _manifest(token_limit=100)
    _canary(tmp_path)
    _ledger(tmp_path, slot_index=0, tokens=100)

    report = _build(tmp_path, manifest)

    assert report["collection"]["stop_reason"] == ("recorded_token_boundary_reached")
    assert report["collection"]["complete_project_block"] is False
    assert report["scope"]["paired_primary_eligible"] is False
    assert report["scope"]["descriptive_only"] is True


def test_short_prefix_below_token_boundary_is_rejected(tmp_path: Path) -> None:
    manifest = _manifest(token_limit=101)
    _canary(tmp_path)
    _ledger(tmp_path, slot_index=0, tokens=100)

    with pytest.raises(reporter.ReportError, match="不完整 project block"):
        _build(tmp_path, manifest)


def test_non_authorized_prefix_is_rejected(tmp_path: Path) -> None:
    manifest = _manifest(token_limit=100)
    _canary(tmp_path)
    _ledger(tmp_path, slot_index=1, tokens=100)

    with pytest.raises(reporter.ReportError, match="严格前缀"):
        _build(tmp_path, manifest)


def test_failed_canary_attempt_marker_is_rejected(tmp_path: Path) -> None:
    manifest = _manifest(token_limit=100)
    _canary(tmp_path, marker_status="failed")
    _ledger(tmp_path, slot_index=0, tokens=100)

    with pytest.raises(reporter.ReportError, match="成功终态"):
        _build(tmp_path, manifest)


def test_markdown_is_deterministic(tmp_path: Path) -> None:
    manifest = _manifest(token_limit=100)
    _canary(tmp_path)
    _ledger(tmp_path, slot_index=0, tokens=100)
    report = _build(tmp_path, manifest)

    first = reporter.render_markdown(report)
    second = reporter.render_markdown(json.loads(json.dumps(report, sort_keys=True)))

    assert first == second
    assert "原 schedule order" in first
