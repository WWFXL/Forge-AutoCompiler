"""真实只读查询与初始规划接线，不把脚本回复当模型效果。"""

import json
from dataclasses import replace

import pytest
from test_plan_agent import ScriptedPlanModel, response
from test_recovery_environment import meter_at
from test_simple_build import LocalRuntime, reference, simple_actions

from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.planning_environment import PlanningEnvironment
from deerflow.compile.simple_build_runtime import SimpleBuildWorkflow
from deerflow.compile.simple_build_task import assemble_simple_plan, propose_simple

pytest_plugins = ["test_simple_build"]


def service(runner):
    _, session, manager, root = runner
    return PlanningEnvironment(session=session, manager=manager, runtime=LocalRuntime(), meter=meter_at(root))


def test_planner_observes_real_environment_before_any_build(runner):
    task, session, manager, root = runner
    env = service(runner)
    model = ScriptedPlanModel(responses=[response("inspect_build_environment", dict(kind="command", query="cc")), response("SimpleBuildActions", simple_actions().model_dump(mode="json"))])
    plan, _ = propose_simple(model=model, task=task, source_root=root, session_root=env.session_root, meter=env.meter, planning_environment=env, enforce_planning_tools=True)
    sent = json.loads((root / "agent/request-2.json").read_text())
    assert "规划前可用" in sent["system_message"]["content"]
    assert any(m["type"] == "tool" and '"status": "ok"' in m["content"] for m in sent["messages"])
    records = manager.load_session(session.session_id, session.thread_id).commands
    assert len(records) == env.calls == env.meter.tracker.snapshot().commands == 1
    assert records[0].role == "diagnostic" and records[0].stage == "planning_dependency"
    assert manager.load_session(session.session_id, session.thread_id).status == "inspected"
    env.close()
    w = SimpleBuildWorkflow(plan=plan, session=session, manager=manager, runtime=LocalRuntime(), reference=reference(task))
    w.commands_used += env.calls
    assert w.run()["status"] == "primary_completed"
    assert records[0].command_id not in w.completed.values()
    with pytest.raises(PlanContractError, match="初始方案"):
        env.execute("environment", "cc", kind="command")


def test_planning_budget_and_invalid_queries(runner):
    env = service(runner)
    assert env.execute("environment", "$(bad)", kind="command")["status"] == "invalid_query"
    assert env.calls == 0
    env.calls = 12
    assert env.execute("environment", "cc", kind="command")["status"] == "budget_exhausted"
    env.calls = 0
    env.meter.tracker.limits = replace(env.meter.tracker.limits, max_commands=0)
    with pytest.raises(Exception, match="commands"):
        env.execute("environment", "cc", kind="command")
    assert env.calls == 0


def test_planning_service_cannot_target_other_source_or_recovery(runner, tmp_path):
    task, _, _, root = runner
    env = service(runner)
    with pytest.raises(PlanContractError, match="绑定当前初始"):
        propose_simple(model=None, task=task, source_root=tmp_path, session_root=env.session_root, meter=env.meter, planning_environment=env)
    plan = assemble_simple_plan(task, simple_actions())
    with pytest.raises(PlanContractError, match="绑定当前初始"):
        propose_simple(model=None, task=task, source_root=root, session_root=env.session_root, meter=env.meter, planning_environment=env, current_plan=plan, handoff={"handoff_id": "test", "plan_sha256": plan.fingerprint()})
