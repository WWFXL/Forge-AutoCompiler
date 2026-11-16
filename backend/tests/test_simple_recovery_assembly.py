"""恢复方案先装配成功依赖，后执行严格校验；脚本模型不调用Provider。"""

import copy
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from test_common_verification_recipe import dependency_failure, step
from test_plan_agent import ScriptedPlanModel, response
from test_simple_build import runner  # noqa: F401

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.simple_build_agents import SimpleBuildMeter
from deerflow.compile.simple_build_task import SimpleBuildActions, propose_simple, simple_action_schema


def proposal():
    return dict(reason="工程恢复", steps=[dict(**step("check-tool.1", "dependency", "command -v make"), requires=["install"]), dict(**step("build", "build", "make"), requires=["check-tool.1"])])


def test_dotted_ids_and_references_normalized_without_command_changes():
    data = proposal()
    data["steps"][0]["requires"] = []
    data["steps"][0]["command"] = "printf '%s' tool.1"
    result = SimpleBuildActions.model_validate(data)
    assert result.steps[0].step_id == "check-tool_1"
    assert result.steps[1].requires == ("check-tool_1",)
    assert result.steps[0].command == "printf '%s' tool.1"
    assert data["steps"][0]["step_id"] == "check-tool.1"
    data["steps"].insert(1, step("check-tool_1", "dependency", "true"))
    with pytest.raises(ValidationError, match="规范化后冲突"):
        SimpleBuildActions.model_validate(data)


def test_real_graph_assembles_omitted_dependencies_and_executes_once(runner, tmp_path):  # noqa: F811
    w = dependency_failure(runner)
    completed = dict(w.completed)
    meter = SimpleBuildMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline=(datetime.now(UTC) + timedelta(hours=1)).isoformat(), packet=lambda: {})
    model = ScriptedPlanModel(responses=[response("SimpleBuildActions", proposal())])
    plan, reason = propose_simple(model=model, task=w.plan.task, source_root=w.root, session_root=tmp_path, meter=meter, current_plan=w.plan, handoff=w.handoff, revision_validator=w.validate_revision)
    assert [s.step_id for s in plan.steps] == ["install", "other", "check-tool_1", "build"]
    w.apply_revision(handoff_id=w.handoff["handoff_id"], plan=plan, reason=reason)
    assert w.run()["status"] == "primary_completed"
    assert all(w.completed[k] == v for k, v in completed.items())
    assert meter.summary()["model_requests"] == 1


def test_unknown_forward_duplicate_discard_and_forged_history_stay_rejected(runner):  # noqa: F811
    w = dependency_failure(runner)
    schema = simple_action_schema(w.plan, w.handoff)
    for reference in ["unknown", "build", "check-tool.1"]:
        data = proposal()
        data["steps"][0]["requires"] = [reference]
        with pytest.raises(ValidationError):
            schema.model_validate(data)
    data = proposal()
    data["discard_dependencies"] = {"install": "明确弃用"}
    with pytest.raises(ValidationError):
        schema.model_validate(data)
    data = proposal()
    data["steps"].insert(0, step("install", "dependency", "true"))
    data["steps"].insert(0, step("install", "dependency", "true"))
    with pytest.raises(ValidationError):
        schema.model_validate(data)
    fake = copy.deepcopy(w.handoff)
    fake["successful_dependencies"][0]["command"] = "false"
    with pytest.raises(PlanContractError, match="不匹配"):
        simple_action_schema(w.plan, fake)
    with pytest.raises(ValidationError):
        SimpleBuildActions.model_validate(proposal())
