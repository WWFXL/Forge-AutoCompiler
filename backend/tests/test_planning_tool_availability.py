"""真实Agent图验证请求Schema与执行约束；不连接Provider。"""

import json

import pytest
from langchain_core.messages import AIMessage
from test_plan_agent import ScriptedPlanModel, response
from test_simple_build import simple_actions, task

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.simple_build_agents import SimpleBuildMeter
from deerflow.compile.simple_build_task import assemble_simple_plan, propose_simple


@pytest.mark.parametrize("enforce", [False, True])
@pytest.mark.parametrize("batch", [False, True])
def test_graph_preserves_policy_feedback_and_cost(tmp_path, enforce, batch):
    (tmp_path / "README.md").write_text("make")
    (tmp_path / "new.txt").write_text("NEW-SOURCE-EVIDENCE")
    replies = [response("read_source", dict(path="README.md")) for _ in range(4)]
    calls = [dict(name="read_source", args=dict(path="new.txt"), id="new-read")]
    if batch:
        calls.append(dict(name="list_source", args=dict(directory="."), id="new-list"))
    replies += [
        AIMessage(content="", tool_calls=calls, usage_metadata=dict(input_tokens=3, output_tokens=2, total_tokens=5), response_metadata=dict(model_name="test-model")),
        response("SimpleBuildActions", simple_actions().model_dump(mode="json")),
    ]
    meter = SimpleBuildMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline="2099-01-01T00:00:00+00:00", packet=lambda: {})
    plan, _ = propose_simple(model=ScriptedPlanModel(responses=replies), task=task(), source_root=tmp_path, session_root=tmp_path, meter=meter, enforce_planning_tools=enforce)
    fifth, sixth = (json.loads((tmp_path / f"agent/request-{n}.json").read_text()) for n in (5, 6))
    assert [t["function"]["name"] for t in fifth["tools"]] == ["SimpleBuildActions"]
    assert plan.steps[-1].command == "make"
    assert meter.summary()["model_requests"] == 6
    assert meter.summary()["recorded_tokens"] == 30
    assert meter.summary()["tool_calls"] == 5 + batch
    events = [json.loads(s) for s in (tmp_path / "agent/events.jsonl").read_text().splitlines()]
    rejected = [e for e in events if e["event"] == "planning.tool_rejected"]
    if enforce:
        assert len(rejected) == 1 + batch
        assert "NEW-SOURCE-EVIDENCE" not in json.dumps(sixth)
        assert "tool_not_available" in json.dumps(sixth)
        assert [t["function"]["name"] for t in sixth["tools"]] == ["SimpleBuildActions"]
        packet = json.loads(sixth["messages"][0]["content"])
        assert packet["planning_progress"]["consecutive_rounds_without_new_evidence"] == 3
        assert all(r["path"] != "new.txt" for r in packet["planning_progress"]["recent_reads"])
    else:
        assert not rejected
        assert "NEW-SOURCE-EVIDENCE" in json.dumps(sixth)
        assert "read_source" in [t["function"]["name"] for t in sixth["tools"]]
    assert meter.planning_context is None


def test_recovery_keeps_original_policy(tmp_path):
    current = assemble_simple_plan(task(), simple_actions())
    revised = simple_actions().model_dump(mode="json")
    revised["steps"][-1]["command"] = "make V=1"
    meter = SimpleBuildMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline="2099-01-01T00:00:00+00:00", packet=lambda: {})
    propose_simple(
        model=ScriptedPlanModel(responses=[response("SimpleBuildActions", revised)]),
        task=task(),
        source_root=tmp_path,
        session_root=tmp_path,
        meter=meter,
        current_plan=current,
        handoff=dict(handoff_id="unit", plan_sha256=current.fingerprint()),
        enforce_planning_tools=True,
    )
    events = [json.loads(s) for s in (tmp_path / "agent/events.jsonl").read_text().splitlines()]
    policy = next(e for e in events if e["event"] == "planning.tool_policy")
    assert policy["recovery"] is True and policy["enforce_tool_availability"] is False
