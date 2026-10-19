"""原始响应费用分解必须闭合，失败成本不能丢失，阶段双来源不一致则拒绝。"""

import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_token_cost_audit import Receipts, aggregate, inspect_arm, price  # noqa: E402

PRICES = {"input_per_million_usd": "1.32", "output_per_million_usd": "3.96"}


def fixture(tmp_path):
    agent = tmp_path / "agent"
    agent.mkdir()
    events = []
    for number, recovery in ((1, False), (2, True)):
        events.extend([{"event": "agent.started", "recovery": recovery}, {"event": "model.request_started", "request_sequence": number}, {"event": "model.request_completed", "request_sequence": number, "recorded_tokens": 30}])
        (agent / f"request-{number}.json").write_text(json.dumps({"messages": [{"content": json.dumps({"handoff": {"handoff_id": "h"} if recovery else None})}]}))
        (agent / f"response-{number}.json").write_text(json.dumps([{"type": "ai", "usage_metadata": {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30}}]))
    (agent / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    row = {
        "project": "fixture",
        "repetition": 1,
        "arm": "plan",
        "strict_completed": False,
        "agent_usage": {
            "cost_and_usage_complete": True,
            "unknown_usage_requests": 0,
            "model_requests": 2,
            "input_tokens": 40,
            "output_tokens": 20,
            "recorded_tokens": 60,
            "estimated_cost_usd_completed_responses": str(price(40, 20, PRICES)),
        },
    }
    return row


def test_initial_and_recovery_costs_close_even_when_arm_failed(tmp_path):
    row = fixture(tmp_path)
    reader = Receipts()
    result = inspect_arm(tmp_path, row, PRICES, reader)
    assert [r["phase"] for r in result["requests"]] == ["initial", "recovery"]
    combined = aggregate([result], PRICES)
    assert combined["strict_completed"] == 0 and combined["requests"] == 2
    assert Decimal(combined["estimated_cost_usd"]) > 0
    assert sum(Decimal(v["estimated_cost_usd"]) for v in combined["phase_totals"].values()) == Decimal(combined["estimated_cost_usd"])
    assert len(reader.files) == 5


@pytest.mark.parametrize("damage", ["missing_usage", "phase_disagreement", "wrong_cost", "unknown_usage"])
def test_inconsistent_raw_accounting_is_rejected(tmp_path, damage):
    row = fixture(tmp_path)
    if damage == "missing_usage":
        (tmp_path / "agent/response-2.json").write_text(json.dumps([{"type": "ai"}]))
    elif damage == "phase_disagreement":
        (tmp_path / "agent/request-2.json").write_text(json.dumps({"messages": [{"content": json.dumps({"handoff": None})}]}))
    elif damage == "wrong_cost":
        row["agent_usage"]["estimated_cost_usd_completed_responses"] = "99"
    else:
        row["agent_usage"]["unknown_usage_requests"] = 1
    with pytest.raises(ValueError):
        inspect_arm(tmp_path, row, PRICES, Receipts())


def test_fewer_total_tokens_can_cost_more_with_output_heavy_response():
    assert 50 < 100
    assert price(0, 50, PRICES) > price(100, 0, PRICES)
