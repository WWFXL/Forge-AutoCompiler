"""共享装配和恢复边界；脚本模型只检验真实图接线，不代表模型效果。"""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from test_plan_agent import ScriptedPlanModel, response
from test_tool_plan import task

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_agent_context import ContextCanaryMeter
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.unified_plan import BuildActions, assemble_plan, propose_actions, tool_actions, unified_planner


def actions(command="make -j2"):
    return BuildActions(reason="源码依据", steps=[{"step_id": "build", "role": "build", "command": command, "source": "Makefile", "expected": "实际成功"}])


def test_both_sources_have_identical_system_tail(tmp_path):
    (tmp_path / "Makefile").write_text("all:\n\ttrue\n")
    tool, _ = tool_actions(task(), tmp_path)
    a = assemble_plan(task(), tool, revision=1)
    b = assemble_plan(task(), actions(), revision=1)
    assert a.steps[-2:] == b.steps[-2:]
    assert a.steps[-2] == task().verification_steps[0]
    assert a.artifact_paths == task().artifact_paths


@pytest.mark.parametrize("role", ["smoke", "artifact_stage"])
def test_model_schema_cannot_supply_tests_or_staging(role):
    value = actions().model_dump()
    value["steps"][0]["role"] = role
    with pytest.raises(ValidationError):
        BuildActions.model_validate(value)


@pytest.mark.parametrize("step_id", ["check", "stage", "other"])
def test_reserved_or_missing_final_build_rejected(step_id):
    value = actions().model_dump()
    value["steps"][0]["step_id"] = step_id
    with pytest.raises(PlanContractError):
        assemble_plan(task(), BuildActions.model_validate(value), revision=1)


def test_same_recovery_function_for_both_initial_sources(tmp_path):
    current = assemble_plan(task(), actions("false"), revision=1)
    handoff = {"handoff_id": "actual", "plan_sha256": current.fingerprint()}
    for source in ("tool", "model"):
        meter = Mock()
        revised = assemble_plan(task(), actions(), revision=2)
        agent = Mock(return_value=(revised, "修复"))
        unified_planner(source, agent=agent)(task=task(), source_root=tmp_path, meter=meter, current_plan=current, handoff=handoff)
        assert agent.call_args.kwargs["handoff"] is handoff
        assert agent.call_args.kwargs["current_plan"] is current


def test_initial_abstention_is_not_execution_handoff(tmp_path):
    meter = Mock()
    agent = Mock(return_value=(assemble_plan(task(), actions(), revision=1), "升级"))
    unified_planner("tool", agent=agent)(task=task(), source_root=tmp_path, meter=meter)
    assert agent.call_count == 1 and agent.call_args.kwargs.get("handoff") is None
    assert meter.ledger.save.call_args_list[0].args[0] == "tool-abstention.json"


def test_stale_recovery_rejected_before_agent(tmp_path):
    agent = Mock()
    with pytest.raises(PlanContractError, match="身份不一致"):
        unified_planner("tool", agent=agent)(task=task(), source_root=tmp_path, meter=Mock(), current_plan=assemble_plan(task(), actions(), revision=1), handoff={"handoff_id": "old", "plan_sha256": "old"})
    agent.assert_not_called()


def test_real_graph_only_emits_actions_and_system_inserts_tests(tmp_path):
    model = ScriptedPlanModel(responses=[response("BuildActions", actions().model_dump(mode="json"))])
    meter = ContextCanaryMeter(
        PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat(), packet=lambda: {"task": task().model_dump(mode="json"), "source_packet": []}
    )
    plan, _ = unified_planner("model")(model=model, task=task(), source_root=tmp_path, session_root=tmp_path, meter=meter)
    assert plan.steps[-2] == task().verification_steps[0]
    assert meter.summary()["model_requests"] == 1
    request = json.loads((tmp_path / "agent/request-1.json").read_text())
    assert "BuildActions" in request["system_message"]["content"]
    assert (tmp_path / "agent/actions-1.json").exists()


def test_recovery_argument_pair_required_before_model(tmp_path):
    with pytest.raises(PlanContractError, match="同时提供"):
        propose_actions(model=Mock(), task=task(), source_root=tmp_path, session_root=tmp_path, meter=Mock(), handoff={"x": 1})
