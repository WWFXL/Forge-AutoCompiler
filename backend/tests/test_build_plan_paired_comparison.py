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


def test_complete_analysis_keeps_failure_cost_and_clusters_related_repositories():
    specification = protocol()
    specification["family_groups"] = {"related": ["project-1", "project-2"], **{f"group-{index}": [f"project-{index}"] for index in (0, 3, 4, 5)}}
    rows = []
    for slot in specification["schedule"]:
        row = {**result("0.2" if slot["arm"] == "plan" else "0.1"), **slot, "arm_total_wall_seconds": 20}
        row["agent_usage"].update(cost_and_usage_complete=True, model_requests=3, recorded_tokens=12000, commands=2)
        row["strict_completed"] = not (slot["project"] == "project-0" and slot["arm"] == "plan")
        rows.append(row)
    analysis = paired.analyze(specification, {"arms": rows, "unobserved_schedule": []})
    assert analysis["paired_comparison_permitted"]
    assert analysis["pairs"]["tool_only_success"] == 2
    assert analysis["observed_totals"]["plan"]["cost_usd"] == pytest.approx(2.4)
    assert analysis["plan_minus_tool"]["strict_completed"]["mean_per_arm"] == pytest.approx(-1 / 6)
    assert analysis["plan_minus_tool"]["cost_usd"]["mean_per_arm"] == pytest.approx(0.1)


def test_reference_defaults_are_normalized_and_real_fixed_obligations_preserved():
    from test_plan_agent import proposal
    from test_plan_agent import task as task_fixture

    task = task_fixture.__wrapped__()
    full = {**task.model_dump(mode="json"), "steps": proposal(task).model_dump(mode="json")["steps"]}
    full.pop("verification_steps")
    minimal = paired.normalized_reference(full)
    for step in minimal["steps"]:
        step.pop("workdir", None)
        step.pop("diagnostic_paths", None)
    normalized = paired.normalized_reference(minimal)
    assert normalized["steps"] == paired.normalized_reference(full)["steps"]
    assert [row for row in normalized["steps"] if row["role"] == "smoke"] == task.model_dump(mode="json")["verification_steps"]


def test_both_execution_paths_receive_same_runtime_limits(tmp_path):
    received = []

    def execute(**kwargs):
        received.append((kwargs["arm"], kwargs["command_timeout_seconds"], kwargs["replay_timeout_seconds"], kwargs["meter_factory"]))
        return result()

    paired.execute_schedule(protocol(), tmp_path, None, {}, executor=execute)
    assert {row[0] for row in received} == {"plan", "tool"}
    assert all(row[1:] == (300, 600, paired.ComparisonMeter) for row in received)


def test_comparison_meter_uses_common_limits_and_stops_before_request(tmp_path, monkeypatch):
    from deerflow.compile.plan_agent import PlanAgentLedger

    meter = paired.ComparisonMeter(PlanAgentLedger(tmp_path / "meter"), accepted_models=("test-model",), deadline="2099-01-01T00:00:00Z", packet=lambda: {})
    assert (meter.tracker.limits.command_timeout_seconds, meter.tracker.limits.evaluator_timeout_seconds, meter.tracker.limits.replay_timeout_seconds) == (300, 600, 600)
    reservations = []

    def stop(deadline, seconds):
        reservations.append(seconds)
        raise paired.PlanContractError("截止保留")

    monkeypatch.setattr(paired, "before_deadline", stop)
    with pytest.raises(paired.PlanContractError, match="截止"):
        meter._before_request()
    assert reservations == [3600] and meter.summary()["model_requests"] == 0
