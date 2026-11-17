"""E59工具错误与非法方案的真实Agent图回放；不连接Provider。"""

import json
from pathlib import Path

import pytest
from test_plan_agent import ScriptedPlanModel, response
from test_planning_environment import service
from test_simple_build import simple_actions
from test_simple_planning import body_response, request, run

from deerflow.compile.simple_build_task import PlanOutputError, propose_simple
from deerflow.compile.simple_planning_context import PlanningContext

pytest_plugins = ["test_simple_build"]
FIXTURE = Path(__file__).resolve().parents[2] / "benchmarks/fixtures/e59-output-errors.json"


@pytest.mark.parametrize("name", ["diagnose_dependency", "search_build_files", "inspect_build_environment", "read_source", "list_source", "read_failure_log"])
@pytest.mark.parametrize("content", ["Error invoking tool: invalid argument", "null", "[]", '{"error":"invalid_query"}'])
def test_tool_errors_never_become_successful_evidence(name, content):
    context = PlanningContext({})
    context.observe(name, {}, content)
    assert context.pending_reads == [False] and not context.reads


def test_invalid_environment_kind_returns_to_agent_then_corrected_query_and_plan(runner):
    task, _, _, root = runner
    env = service(runner)
    model = ScriptedPlanModel(
        responses=[
            response("inspect_build_environment", dict(kind="pkgconfig", query="freetype2")),
            response("inspect_build_environment", dict(kind="command", query="cc")),
            response("SimpleBuildActions", simple_actions().model_dump(mode="json")),
        ]
    )
    plan, _ = propose_simple(model=model, task=task, source_root=root, session_root=env.session_root, meter=env.meter, planning_environment=env)
    second = request(root, 2)
    tool = next(m for m in second["messages"] if m["type"] == "tool")
    assert tool["status"] == "error" and "Input should be" in tool["content"]
    assert not json.loads(second["messages"][0]["content"])["planning_progress"]["recent_reads"]
    assert env.calls == 1 and env.meter.summary()["model_requests"] == 3
    assert plan.steps[-1].role == "build"


@pytest.mark.parametrize("case", json.loads(FIXTURE.read_text())["invalid_outputs"])
def test_e59_original_invalid_output_receives_short_feedback_and_full_redelivery(tmp_path, case):
    original = case["message"]
    replies = [body_response(original["content"], invalid_tool_calls=original["invalid_tool_calls"]), response("SimpleBuildActions", simple_actions().model_dump(mode="json"))]
    plan, meter = run(tmp_path, replies)
    sent = request(tmp_path, 2)
    feedback = sent["messages"][-1]["content"]
    assert "JSON语法错误" in feedback and "重新提交一份完整JSON对象" in feedback
    assert len(feedback) < 1600
    assert not any(m.get("invalid_tool_calls") for m in sent["messages"])
    assert original["invalid_tool_calls"][0]["args"] not in str(sent)
    raw = json.loads((tmp_path / "agent/response-1.json").read_text())[0]
    assert raw["invalid_tool_calls"] == original["invalid_tool_calls"]
    assert plan.steps[-1].role == "build" and meter.summary()["model_requests"] == 2


def test_e59_repeated_invalid_output_stops_after_one_correction(tmp_path):
    original = json.loads(FIXTURE.read_text())["invalid_outputs"][0]["message"]
    bad = body_response(original["content"], invalid_tool_calls=original["invalid_tool_calls"])
    with pytest.raises(PlanOutputError):
        run(tmp_path, [bad, bad, response("SimpleBuildActions", simple_actions().model_dump(mode="json"))])
    assert not (tmp_path / "agent/request-3.json").exists()


def test_original_libass_text_error_is_preserved_without_observer_exception():
    original = json.loads(FIXTURE.read_text())["tool_error"]
    context = PlanningContext({})
    context.observe(original["name"], original["arguments"], original["content"], status="error")
    assert context.pending_reads == [False] and not context.reads
    assert "pkgconfig" in original["content"]


def test_schema_feedback_names_field_without_echoing_invalid_command(tmp_path):
    invalid = simple_actions().model_dump(mode="json")
    invalid["reason"] = ["INVALID_COMMAND_MUST_NOT_BE_ECHOED"]
    run(tmp_path, [response("SimpleBuildActions", invalid), response("SimpleBuildActions", simple_actions().model_dump(mode="json"))])
    feedback = next(m["content"] for m in request(tmp_path, 2)["messages"] if m["type"] == "tool")
    assert "reason" in feedback and "string_type" in feedback
    assert "INVALID_COMMAND_MUST_NOT_BE_ECHOED" not in feedback


def test_recovery_graph_corrects_original_libtasn1_output(tmp_path):
    from test_simple_build import task

    from deerflow.compile.plan_agent import PlanAgentLedger
    from deerflow.compile.simple_build_agents import SimpleBuildMeter
    from deerflow.compile.simple_build_task import assemble_simple_plan

    original = next(c["message"] for c in json.loads(FIXTURE.read_text())["invalid_outputs"] if "libtasn1" in c["path"])
    current = assemble_simple_plan(task(), simple_actions())
    meter = SimpleBuildMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline="2099-01-01T00:00:00+00:00", packet=lambda: {})
    corrected = simple_actions().model_dump(mode="json")
    corrected["steps"][-1]["command"] = "make -j2"
    model = ScriptedPlanModel(responses=[body_response(original["content"], invalid_tool_calls=original["invalid_tool_calls"]), response("SimpleBuildActions", corrected)])
    plan, _ = propose_simple(model=model, task=task(), source_root=tmp_path, session_root=tmp_path, meter=meter, current_plan=current, handoff=dict(handoff_id="replay", plan_sha256=current.fingerprint()))
    assert plan.revision == 2 and meter.summary()["model_requests"] == 2
