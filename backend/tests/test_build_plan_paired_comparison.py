"""跨重复配对、整阶段费用预留及部分观察持久化。"""

import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
spec = importlib.util.spec_from_file_location("paired_comparison", Path(__file__).resolve().parents[2] / "scripts/forge_build_plan_paired_comparison.py")
paired = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paired)


def protocol():
    names = [f"project-{index}" for index in range(6)]
    return {"projects": [{"name": name} for name in names], "schedule": paired.make_schedule(names), "deadline_utc": "2099-01-01T00:00:00Z", "max_estimated_cost_usd": 12}


def result(cost="0.1", unknown=0, strict=True):
    return {"arm": "plan", "strict_completed": strict, "cleanup": {"succeeded": True}, "agent_usage": {"estimated_cost_usd_completed_responses": cost, "unknown_usage_requests": unknown}}


def test_each_project_has_both_orders_and_two_complete_pairs():
    schedule = protocol()["schedule"]
    for index in range(6):
        rows = [row for row in schedule if row["project"] == f"project-{index}"]
        assert len(rows) == 4
        assert [row["arm"] for row in rows[:2]] == list(reversed([row["arm"] for row in rows[2:]]))


def test_whole_next_arm_is_reserved_and_remaining_slots_are_unobserved(tmp_path):
    observed, unobserved, reason = paired.execute_schedule(protocol(), tmp_path, None, {}, executor=lambda **kwargs: result("1.4"))
    assert len(observed) == 8 and len(unobserved) == 16
    assert reason == "stage_cost_reservation"
    assert all(row["status"] == "not_observed" for row in unobserved)
    assert paired.charged_cost(observed) == paired.Decimal("11.2")


def test_unknown_usage_holds_reservation_and_stops_whole_stage(tmp_path):
    observed, unobserved, reason = paired.execute_schedule(protocol(), tmp_path, None, {}, executor=lambda **kwargs: result("0.1", 1))
    assert len(observed) == 1 and len(unobserved) == 23
    assert paired.charged_cost(observed) == paired.Decimal("0.50")
    assert reason == "cleanup_or_unknown_usage"


def test_evaluated_failure_does_not_replace_or_stop_fixed_schedule(tmp_path):
    observed, unobserved, reason = paired.execute_schedule(protocol(), tmp_path, None, {}, executor=lambda **kwargs: result(strict=False))
    assert len(observed) == 24 and not unobserved and reason is None
    assert not any(row["strict_completed"] for row in observed)


def test_unexpected_executor_failure_preserves_already_observed_rows(tmp_path):
    observed = []

    def execute(**kwargs):
        if observed:
            raise RuntimeError("夹具注入异常")
        return result()

    with pytest.raises(RuntimeError, match="夹具"):
        paired.execute_schedule(protocol(), tmp_path, None, {}, executor=execute, results=observed)
    assert len(observed) == 1 and paired.charged_cost(observed) == paired.Decimal("0.1")


def test_failed_arms_are_included_in_cost_and_incomplete_schedule_blocks_contrast():
    specification = protocol()
    row = {**result("0.7", strict=False), "project": "project-0", "repetition": 1, "arm_total_wall_seconds": 20}
    row["agent_usage"].update(cost_and_usage_complete=True, model_requests=3, recorded_tokens=12000, commands=2)
    analysis = paired.analyze(specification, {"arms": [row], "unobserved_schedule": specification["schedule"][1:]})
    assert analysis["observed_totals"]["plan"]["cost_usd"] == 0.7
    assert analysis["observed_totals"]["plan"]["strict_completed"] == 0
    assert not analysis["paired_comparison_permitted"] and "plan_minus_tool" not in analysis
