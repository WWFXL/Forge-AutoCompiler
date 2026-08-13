from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "forge_formal_timeout_calibration_result.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


result = _load_module("forge_formal_timeout_calibration_result_test", SCRIPT_PATH)


def _completed(latency: float) -> dict:
    return {"event": "model.request_completed", "payload": {"latency_seconds": latency}}


def test_request_latency_metrics_counts_thresholds() -> None:
    metrics = result._request_latency_metrics([_completed(1.25), _completed(120.5), _completed(301)])

    assert metrics == {
        "completed_with_latency": 3,
        "maximum_seconds": 301.0,
        "over_120_seconds": 2,
        "over_300_seconds": 1,
    }


@pytest.mark.parametrize("latency", [None, True, -1])
def test_request_latency_metrics_rejects_invalid_values(latency) -> None:
    with pytest.raises(result.ResultError, match="latency_seconds"):
        result._request_latency_metrics([{"event": "model.request_completed", "payload": {"latency_seconds": latency}}])


def test_build_report_adds_latency_without_changing_frozen_result(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    frozen = {
        "report_version": "frozen",
        "attempts": [
            {
                "case_id": "cppitertools",
                "condition_id": "richlab-gpt-5.5",
                "repetition": 1,
                "model_requests": {"started": 2, "closed": 2},
                "oracle_passed": True,
                "token_usage": {"total_tokens": 10},
                "attempt_duration_seconds": 1.0,
            }
        ],
        "collection": {
            "analyzed_slots": 1,
            "authorized_slots": 1,
            "oracle_passed": 1,
            "recorded_total_tokens": 10,
            "recorded_token_limit": 100,
            "orphan_count": 0,
        },
        "interpretation": {},
        "limitations": [],
    }
    monkeypatch.setattr(result.frozen_report, "build_report", lambda *args, **kwargs: frozen)
    monkeypatch.setattr(
        result.runner._authorized_runner,
        "_observed_authorized_ledgers",
        lambda *args, **kwargs: [
            (
                {"case_id": "cppitertools", "condition_id": "richlab-gpt-5.5", "repetition": 1},
                [_completed(33.891), _completed(1.2)],
            )
        ],
    )

    report = result.build_report({}, tmp_path)

    assert report["report_version"] == "formal-timeout-calibration-result-1.0.0"
    assert report["collection"]["model_request_latency"] == {
        "completed_with_latency": 2,
        "maximum_seconds": 33.891,
        "over_120_seconds": 0,
        "over_300_seconds": 0,
    }
    assert report["interpretation"]["timeout_extension_rescue_observed"] is False
    markdown = result.render_markdown(report)
    assert "forge_formal_timeout_calibration_result.py" in markdown
    assert "benchmark-evidence-formal-timeout-canary-amendment" in markdown
