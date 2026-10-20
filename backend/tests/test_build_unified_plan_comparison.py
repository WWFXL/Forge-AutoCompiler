"""完整配对调度、资源停止和参考隔离，不发Provider。"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_unified_plan_comparison as compare

from deerflow.compile.plan_workflow import PlanContractError


def protocol():
    return {"schedule": compare.schedule(), "projects": [{"name": p} for p in compare.PROJECTS], "deadline_utc": (datetime.now(UTC) + timedelta(hours=4)).isoformat(), "max_new_provider_cost_usd": 20}


def result(unknown=0, cleanup=True):
    return {"agent_usage": {"estimated_cost_usd_completed_responses": 0.1, "unknown_usage_requests": unknown}, "cleanup": {"succeeded": cleanup}}


def test_balanced_complete_schedule_and_reverse_repetition():
    rows = compare.schedule()
    assert len(rows) == 36 and len({(s["project"], s["repetition"], s["method"]) for s in rows}) == 36
    for p in compare.PROJECTS:
        a = [s["method"] for s in rows if s["project"] == p and s["repetition"] == 1]
        b = [s["method"] for s in rows if s["project"] == p and s["repetition"] == 2]
        assert a == list(reversed(b))
    for m in compare.METHODS:
        assert [sum(rows[i]["method"] == m for i in range(position, 18, 3)) for position in range(3)] == [2, 2, 2]


def test_full_execute_includes_failures_and_never_passes_reference(tmp_path):
    executor = Mock(side_effect=lambda **kw: result())
    rows, unseen, reason = compare.execute(protocol(), tmp_path, "model", executor=executor)
    assert len(rows) == 36 and not unseen and reason is None
    assert all(c.kwargs["reference"] is None and c.kwargs["qualify"] is False for c in executor.call_args_list)


@pytest.mark.parametrize("unknown,cleanup", [(1, True), (0, False)])
def test_unknown_usage_or_cleanup_stops_remaining_as_unobserved(tmp_path, unknown, cleanup):
    rows, unseen, reason = compare.execute(protocol(), tmp_path, "model", executor=Mock(return_value=result(unknown, cleanup)))
    assert len(rows) == 1 and len(unseen) == 35 and reason == "cleanup_or_unknown_usage"


def test_stage_reservation_counts_failed_arms_and_stops_before_provider(tmp_path):
    p = protocol()
    p["max_new_provider_cost_usd"] = 1.55
    rows, unseen, reason = compare.execute(p, tmp_path, "model", executor=Mock(return_value=result()))
    assert len(rows) == 1 and len(unseen) == 35 and reason == "stage_cost_reservation"


def test_expired_window_never_calls_executor(tmp_path):
    p = protocol()
    p["deadline_utc"] = (datetime.now(UTC) + timedelta(minutes=30)).isoformat()
    executor = Mock()
    rows, unseen, reason = compare.execute(p, tmp_path, None, executor=executor)
    assert not rows and len(unseen) == 36 and reason == "deadline_reservation"
    executor.assert_not_called()


def test_old_authorization_identity_cannot_be_reused():
    with pytest.raises(PlanContractError):
        compare.validate_authorization({"candidate_sha256": "new"}, {"experiment_identity": "cpp-build-full-strategy-comparison-v1", "candidate_sha256": "new", "user_authorized": True})


def test_recovery_rejects_modified_fixed_tail_before_agent(tmp_path):
    from test_tool_plan import task

    from deerflow.compile.unified_plan import BuildActions, assemble_plan, unified_planner

    actions = BuildActions(reason="测试", steps=[{"step_id": "build", "role": "build", "command": "make", "source": "Makefile", "expected": "成功"}])
    plan = assemble_plan(task(), actions, revision=1)
    value = plan.model_dump()
    value["steps"][-1]["command"] = "true"
    modified = type(plan).model_validate(value)
    agent = Mock()
    with pytest.raises(PlanContractError, match="固定装配"):
        unified_planner("model", agent=agent)(task=task(), source_root=tmp_path, meter=Mock(), current_plan=modified, handoff={"handoff_id": "actual", "plan_sha256": modified.fingerprint()})
    agent.assert_not_called()


def test_wrong_provider_model_stops_entire_comparison(tmp_path):
    value = {**result(), "error_message": "Provider 返回的模型标识不符合运行协议"}
    rows, unseen, reason = compare.execute(protocol(), tmp_path, "model", executor=Mock(return_value=value))
    assert len(rows) == 1 and len(unseen) == 35 and reason == "provider_identity_mismatch"


def test_strong_baseline_uses_tool_control_and_shared_meter(tmp_path):
    import forge_build_unified_plan as dispatch

    executor = Mock(return_value={"strict_completed": False})
    dispatch.slot_runner(protocol={}, root=tmp_path, slot={"method": "strong_tool_agent"}, item={}, model="same-model", executor=executor)
    args = executor.call_args.kwargs
    assert args["arm"] == "tool" and args["meter_factory"] is dispatch.StrategyMeter
    assert args["reference"] is None and args["model"] == "same-model"
