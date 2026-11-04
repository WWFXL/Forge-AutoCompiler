"""复现E42的交付错误、遗忘/重复读取及测试入口错配；全部不连接Provider。"""

import json
import subprocess
from pathlib import Path

import pytest
from langchain.agents.structured_output import StructuredOutputValidationError
from langchain_core.messages import AIMessage
from pydantic import ValidationError
from test_plan_agent import ScriptedPlanModel, response
from test_simple_build import reference, simple_actions, task

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.simple_author_tests import resolve_author_tests
from deerflow.compile.simple_build_agents import SimpleBuildMeter
from deerflow.compile.simple_build_experience import SimpleStateTargetBank
from deerflow.compile.simple_build_task import SimpleBuildActions, propose_simple


def run(root, replies):
    meter = SimpleBuildMeter(PlanAgentLedger(root / "agent"), accepted_models=("test-model",), deadline="2099-01-01T00:00:00+00:00", packet=lambda: dict(source_packet=[], private_reference="NEVER_SEND"))
    model = ScriptedPlanModel(responses=replies)
    plan, _ = propose_simple(model=model, task=task(), source_root=root, session_root=root, meter=meter)
    return plan, meter


def request(root, sequence):
    return json.loads((root / f"agent/request-{sequence}.json").read_text())


@pytest.mark.parametrize("invalid", [{}, {"reason": simple_actions().model_dump(mode="json")["steps"]}])
def test_real_graph_corrects_empty_or_misplaced_steps_with_feedback_and_cost(tmp_path, invalid):
    plan, meter = run(tmp_path, [response("SimpleBuildActions", invalid), response("SimpleBuildActions", simple_actions().model_dump(mode="json"))])
    assert plan.steps[-1].command == "make"
    assert meter.summary()["model_requests"] == 2 and meter.summary()["unknown_usage_requests"] == 0
    sent = request(tmp_path, 2)
    assert any(m["type"] == "tool" and "仅允许这一次结构纠正" in m["content"] for m in sent["messages"])
    assert "NEVER_SEND" not in json.dumps(sent)
    assert json.loads((tmp_path / "agent/response-1.json").read_text())[0]["tool_calls"][0]["args"] == invalid


def test_two_invalid_candidates_stop_without_an_unbounded_retry(tmp_path):
    with pytest.raises(StructuredOutputValidationError):
        run(tmp_path, [response("SimpleBuildActions", {})] * 3)
    assert (tmp_path / "agent/response-2.json").exists()
    assert not (tmp_path / "agent/request-3.json").exists()


def body_response(text, **kwargs):
    return AIMessage(content=text, usage_metadata=dict(input_tokens=3, output_tokens=2, total_tokens=5), response_metadata=dict(model_name="test-model"), **kwargs)


def test_valid_body_is_strictly_validated_and_original_response_remains(tmp_path):
    original = json.dumps(simple_actions().model_dump(mode="json"))
    plan, meter = run(tmp_path, [body_response(original)])
    assert plan.steps[-1].command == "make" and meter.summary()["model_requests"] == 1
    raw = json.loads((tmp_path / "agent/response-1.json").read_text())[0]
    assert raw["content"] == original and not raw["tool_calls"]
    assert '"channel": "json_body"' in (tmp_path / "agent/events.jsonl").read_text()


def test_invalid_json_tool_gets_one_feedback_without_dangling_tool_call(tmp_path):
    invalid = body_response("", invalid_tool_calls=[dict(name="SimpleBuildActions", args='{"reason":"x"}}', id="malformed", error="Extra data")])
    _, meter = run(tmp_path, [invalid, response("SimpleBuildActions", simple_actions().model_dump(mode="json"))])
    assert meter.summary()["model_requests"] == 2 and meter.summary()["recorded_tokens"] == 10
    sent = request(tmp_path, 2)
    assert "工具参数不是合法JSON" in sent["messages"][-1]["content"]
    assert "仅允许这一次结构纠正" in sent["messages"][-1]["content"]
    assert all(not m.get("invalid_tool_calls") for m in sent["messages"])
    raw = json.loads((tmp_path / "agent/response-1.json").read_text())[0]
    assert raw["invalid_tool_calls"][0]["args"] == '{"reason":"x"}}'


@pytest.mark.parametrize("first_tool", [True, False])
def test_tool_and_body_errors_share_exactly_one_correction(tmp_path, first_tool):
    invalid = [response("SimpleBuildActions", {}), body_response('{"reason":"x"}')]
    if not first_tool:
        invalid.reverse()
    with pytest.raises((StructuredOutputValidationError, ValueError)):
        run(tmp_path, [*invalid, response("SimpleBuildActions", simple_actions().model_dump(mode="json"))])
    assert (tmp_path / "agent/response-2.json").exists()
    assert not (tmp_path / "agent/request-3.json").exists()


@pytest.mark.parametrize("text", ["方案完成", '{"reason":"x"}}', '说明：{"reason":"x","steps":[]}', '{"reason":"x","steps":[],"tests":"skip"}'])
def test_invalid_body_receives_specific_feedback_then_valid_candidate(tmp_path, text):
    plan, meter = run(tmp_path, [body_response(text), response("SimpleBuildActions", simple_actions().model_dump(mode="json"))])
    assert plan.steps[-1].command == "make" and meter.summary()["model_requests"] == 2
    assert "仅允许这一次结构纠正" in request(tmp_path, 2)["messages"][-1]["content"]


@pytest.mark.parametrize("index", range(7))
def test_e43_original_responses_reach_validation_or_explicit_feedback(tmp_path, index):
    root = Path(__file__).resolve().parents[2]
    original = json.loads((root / "benchmarks/analyses/cpp-build-planning-context-experience-flash-v1/failure-analysis.json").read_text())["failures"][index]
    replay = body_response(original["content"], invalid_tool_calls=original["invalid_tool_calls"])
    plan, meter = run(tmp_path, [replay, response("SimpleBuildActions", simple_actions().model_dump(mode="json"))])
    expected_requests = 2 if original["invalid_tool_calls"] else 1
    assert meter.summary()["model_requests"] == expected_requests
    assert plan.steps[-1].role == "build"
    raw = json.loads((tmp_path / "agent/response-1.json").read_text())[0]
    assert raw["content"] == original["content"] and raw["invalid_tool_calls"] == original["invalid_tool_calls"]


def test_mixed_provider_prices_are_counted_once_per_actual_response(tmp_path):
    (tmp_path / "README.md").write_text("make")
    meter = SimpleBuildMeter(
        PlanAgentLedger(tmp_path / "agent"),
        accepted_models=("flash-test", "richlab-test"),
        deadline="2099-01-01T00:00:00+00:00",
        packet=lambda: {},
        pricing_by_model={"flash-test": ("0.30", "1.20"), "richlab-test": ("1.00", "1.00")},
    )
    model = ScriptedPlanModel(responses=[response("read_source", dict(path="README.md"), model="flash-test"), response("SimpleBuildActions", simple_actions().model_dump(mode="json"), model="richlab-test")])
    propose_simple(model=model, task=task(), source_root=tmp_path, session_root=tmp_path, meter=meter)
    assert meter.summary()["estimated_cost_usd"] == pytest.approx(0.0000083)
    events = [json.loads(line) for line in (tmp_path / "agent/events.jsonl").read_text().splitlines()]
    assert len([e for e in events if e["event"] == "model.cost_estimated"]) == 2


def test_provider_error_is_not_a_format_correction(tmp_path):
    class OfflineFailure(ScriptedPlanModel):
        def _generate(self, *args, **kwargs):
            raise ConnectionError("受控服务异常")

    meter = SimpleBuildMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline="2099-01-01T00:00:00+00:00", packet=lambda: {})
    with pytest.raises(ConnectionError):
        propose_simple(model=OfflineFailure(responses=[]), task=task(), source_root=tmp_path, session_root=tmp_path, meter=meter)
    assert meter.summary()["model_requests"] == 1 and meter.summary()["unknown_usage_requests"] == 1
    assert "simple.proposal_rejected" not in (tmp_path / "agent/events.jsonl").read_text()


def test_five_read_interactions_keep_earliest_evidence_and_assistant_message(tmp_path):
    replies = []
    for i in range(5):
        (tmp_path / f"part-{i}.txt").write_text(f"SOURCE-EVIDENCE-{i}")
        reply = response("read_source", dict(path=f"part-{i}.txt"))
        reply.content = f"已确认构建事实{i}"
        replies.append(reply)
    replies.append(response("SimpleBuildActions", simple_actions().model_dump(mode="json")))
    run(tmp_path, replies)
    sent = request(tmp_path, 6)
    assert "SOURCE-EVIDENCE-0" in json.dumps(sent) and "已确认构建事实0" in json.dumps(sent, ensure_ascii=False)
    assert len([m for m in sent["messages"] if m["type"] == "tool"]) == 5


def test_repeated_reads_receive_convergence_feedback_then_only_output_tool(tmp_path):
    (tmp_path / "README.md").write_text("Run make for the main library")
    run(tmp_path, [response("read_source", dict(path="README.md")) for _ in range(4)] + [response("SimpleBuildActions", simple_actions().model_dump(mode="json"))])
    fourth, fifth = request(tmp_path, 4), request(tmp_path, 5)
    assert "连续重复读取没有新增证据" in fourth["messages"][0]["content"]
    assert [t["function"]["name"] for t in fifth["tools"]] == ["SimpleBuildActions"]


def test_context_compacts_whole_interactions_and_keeps_latest_evidence(tmp_path):
    replies = []
    for i in range(8):
        (tmp_path / f"large-{i}.txt").write_text(f"LATEST-{i}\n" + "payload" * 1100)
        replies.append(response("read_source", dict(path=f"large-{i}.txt")))
    replies.append(response("SimpleBuildActions", simple_actions().model_dump(mode="json")))
    run(tmp_path, replies)
    sent = request(tmp_path, 9)
    assert "LATEST-7" in json.dumps(sent) and "LATEST-0" not in json.dumps(sent)
    assert len(json.dumps({k: v for k, v in sent.items() if k != "tools"}, ensure_ascii=False).encode()) <= 49000
    assert sent["messages"][1]["type"] == "ai"


def test_large_initial_packet_does_not_displace_latest_multi_tool_results(tmp_path):
    for i in range(3):
        (tmp_path / f"part-{i}.txt").write_text(f"LATEST-{i}\n" + "data" * 1800)
    initial = dict(path="README.md", sha256="a" * 64, content="SEED " * 4400)
    meter = SimpleBuildMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline="2099-01-01T00:00:00+00:00", packet=lambda: dict(source_packet=[initial]))
    batch = body_response("", tool_calls=[dict(name="read_source", args=dict(path=f"part-{i}.txt"), id=f"read-{i}") for i in range(3)])
    model = ScriptedPlanModel(responses=[batch, response("SimpleBuildActions", simple_actions().model_dump(mode="json"))])
    propose_simple(model=model, task=task(), source_root=tmp_path, session_root=tmp_path, meter=meter)
    sent = request(tmp_path, 2)
    assert all(f"LATEST-{i}" in json.dumps(sent) for i in range(3))
    packet = json.loads(sent["messages"][0]["content"])
    assert packet["source_packet"][0]["sha256"] == "a" * 64 and packet["source_packet"][0]["content"] == ""
    assert packet["planning_progress"]["initial_material_compactions"] == 1
    assert initial["content"] == "SEED " * 4400
    assert len(json.dumps({k: v for k, v in sent.items() if k != "tools"}, ensure_ascii=False).encode()) <= 49000


def test_rejected_read_remains_feedback_instead_of_aborting_planning(tmp_path):
    (tmp_path / "README.md").write_text("make")
    plan, _ = run(tmp_path, [response("read_source", dict(path="../outside")), response("read_source", dict(path="README.md")), response("SimpleBuildActions", simple_actions().model_dump(mode="json"))])
    assert plan.steps[-1].command == "make"
    assert any(m["type"] == "tool" and "accepted" in m["content"] for m in request(tmp_path, 3)["messages"])


def test_schema_omits_obsolete_observations_and_rejects_unknown_fields():
    assert "files_exist" not in str(SimpleBuildActions.model_json_schema())
    invalid = simple_actions().model_dump()
    invalid["steps"][0]["files_exist"] = ["guessed.a"]
    with pytest.raises(ValidationError):
        SimpleBuildActions.model_validate(invalid)


def test_compact_experience_matches_conditions_not_action_or_other_stage():
    sources = [dict(source_id="other", family="other", build_system="cmake")]
    base = dict(source_id="other", stage="configure", conditions=["CMAKE_GENERATOR"], state="actual cache", action="CHECK_GENERATOR", not_applicable=["no cache"])
    bank = SimpleStateTargetBank(sources, [base, base | dict(stage="verification", action="DO_NOT_SEND_TEST_RULE"), base | dict(conditions=["unrelated"], state="unrelated", action="CMAKE_GENERATOR SHOULD_NOT_MATCH")])
    kwargs = dict(build_system="cmake", family="current", stage="initial", mode="structured", text=json.dumps(dict(source_packet=[dict(content="CMAKE_GENERATOR")], private_reference="unrelated")))
    result = bank.retrieve(**kwargs)
    assert len(result["items"]) == 1 and result["items"][0]["advice"]["action"] == "CHECK_GENERATOR"
    assert "source_validation" not in json.dumps(result) and result["bytes"] <= 4096
    assert not bank.retrieve(**(kwargs | dict(family="other")))["items"]
    assert bank.retrieve(**(kwargs | dict(limit_bytes=10)))["abstained"]


@pytest.mark.parametrize("registered", [True, False])
def test_actual_cmake_suite_replaces_autotools_entry_but_zero_tests_fail(tmp_path, registered):
    (tmp_path / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.16)\nproject(sample C)\nenable_testing()\n" + ('add_test(NAME author COMMAND "${CMAKE_COMMAND}" -E true)\n' if registered else ""))
    subprocess.run(["cmake", "-S", str(tmp_path), "-B", str(tmp_path / "actual-output")], check=True, capture_output=True)
    ref = reference(task()).model_copy(update={"author_tests": (simple_author_step(),)})
    steps, selection = resolve_author_tests(tmp_path, ref)
    assert selection["route"] == "actual_cmake_ctest"
    command = steps[0].command.replace("/workspace/repo", str(tmp_path))
    result = subprocess.run(["bash", "-euo", "pipefail", "-c", command], cwd=tmp_path, capture_output=True, text=True)
    assert (result.returncode == 0) == registered
    if registered:
        assert "100% tests passed" in result.stdout


def simple_author_step():
    from deerflow.compile.plan_workflow import PlanStep

    return PlanStep(step_id="test", role="smoke", command="make runtest", source="作者Makefile", expected="完整作者测试", required_output=("tests passed",))
