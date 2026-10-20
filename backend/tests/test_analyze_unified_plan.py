"""费用按原请求阶段重算；解析失败和未知响应不能丢失。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_analyze_unified_plan import request_accounting


def test_initial_recovery_and_known_parse_failure_costs_all_count():
    events = [
        {"event": "unified.agent", "phase": "initial"},
        {"event": "model.request_started", "request_sequence": 1},
        {"event": "model.request_completed", "request_sequence": 1, "input_tokens": 100, "output_tokens": 50, "recorded_tokens": 150},
        {"event": "model.request_failed", "request_sequence": 1},
        {"event": "unified.agent", "phase": "recovery"},
        {"event": "model.request_started", "request_sequence": 2},
        {"event": "model.request_failed", "request_sequence": 2},
    ]
    result = request_accounting(events)
    assert result["requests"] == 2 and result["unknown_requests"] == 1
    assert result["phases"]["initial"]["known_estimated_cost_usd"] == "0.00033"
    assert result["phases"]["recovery"]["unknown_requests"] == 1


def test_initial_upgrade_is_separate_from_runtime_recovery():
    result = request_accounting([{"event": "unified.agent", "phase": "initial_abstention"}, {"event": "model.request_started", "request_sequence": 1}])
    assert result["phases"]["initial_abstention"]["requests"] == 1
    assert "recovery" not in result["phases"]


@pytest.mark.parametrize("events", [[{"event": "model.request_started", "request_sequence": 1}] * 2, [{"event": "model.request_completed", "request_sequence": 1, "input_tokens": 1, "output_tokens": 1, "recorded_tokens": 2}]])
def test_duplicate_and_orphan_lifecycles_rejected(events):
    with pytest.raises(ValueError):
        request_accounting(events)
