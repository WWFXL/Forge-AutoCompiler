"""接管材料投影不得改任务/方案/权威状态身份，错配时拒绝。"""

from copy import deepcopy
from hashlib import sha256

import pytest

from deerflow.compile.plan_handoff_context import project_handoff_packet
from deerflow.compile.plan_workflow import PlanContractError


def packet():
    handoff = {"handoff_id": "h1", "reason": "step_failed", "step_id": "check", "plan_sha256": "a" * 64, "command_frontier": "b" * 64, "return_contract": "不降低固定测试"}
    records = [{"command_id": str(i), "command": "make check", "exit_code": 2, "log_path": f"logs/{i}.log", "log_sha256": "c" * 64, "output_tail": "失败日志\n" * 3000} for i in range(6)]
    return {
        "task": {"verification_steps": ["all tests"]},
        "current_plan": {"steps": ["fixed plan"]},
        "state": {"completed": {"build": "4"}, "commands_used": 6, "handoff": {**handoff, "recent_commands": records}},
        "handoff": {**handoff, "recent_commands": deepcopy(records[-3:])},
    }


def test_projection_keeps_full_core_and_all_log_receipts_without_mutating_input():
    source = packet()
    original = deepcopy(source)
    result = project_handoff_packet(source)
    assert source == original
    assert result["task"] == source["task"] and result["current_plan"] == source["current_plan"]
    assert result["handoff"] == source["handoff"]
    assert result["state"]["completed"] == source["state"]["completed"]
    for before, after in zip(source["state"]["handoff"]["recent_commands"], result["state"]["handoff"]["recent_commands"]):
        assert {k: v for k, v in before.items() if k != "output_tail"} == {k: v for k, v in after.items() if k != "omitted_output_tail"}
        raw = before["output_tail"].encode()
        assert after["omitted_output_tail"]["sha256"] == sha256(raw).hexdigest()
        assert after["omitted_output_tail"]["utf8_bytes"] == len(raw)
    assert project_handoff_packet(result) == result


@pytest.mark.parametrize("key", ["handoff_id", "reason", "step_id", "plan_sha256", "command_frontier", "return_contract"])
def test_projection_rejects_stale_or_different_handoff(key):
    source = packet()
    source["handoff"][key] = "different"
    with pytest.raises(PlanContractError, match="身份不一致"):
        project_handoff_packet(source)


def test_initial_plan_without_handoff_is_preserved():
    source = {"task": {"fixed": True}, "state": {"handoff": None}, "handoff": None}
    assert project_handoff_packet(source) == source


def test_oversized_core_still_stops_before_any_model_request(tmp_path):
    from datetime import UTC, datetime, timedelta

    from test_plan_agent import ScriptedPlanModel, proposal, response
    from test_plan_agent import task as task_fixture

    from deerflow.compile.plan_agent import PlanAgentLedger
    from deerflow.compile.plan_agent_context import propose_with_context
    from deerflow.compile.plan_handoff_context import HandoffContextMeter

    task = task_fixture.__wrapped__()
    materials = {"task": task.model_dump(mode="json"), "state": {"completed": {}, "core": "核心状态" * 20000}, "source_packet": []}
    meter = HandoffContextMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat(), packet=lambda: materials)
    model = ScriptedPlanModel(responses=[response("PlanProposal", proposal(task).model_dump(mode="json"))])
    with pytest.raises(PlanContractError, match="超过50000字节"):
        propose_with_context(model=model, task=task, source_root=tmp_path, session_root=tmp_path, meter=meter)
    assert meter.summary()["model_requests"] == 0
    assert not list((tmp_path / "agent").glob("request-*.json"))
