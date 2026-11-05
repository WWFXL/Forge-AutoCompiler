"""只验证实际构建误拦、新任务测试边界及语义路由的执行约束。"""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx2
import pytest
from test_simple_build import LocalRuntime, actions, workflow
from typesafe_sdk import RetryPolicy, TypeSafeClient

from deerflow.compile.build_state_routing import BuildStateRouter, JevStateSelector, StateAction, candidate_actions, observe_state, rule_choice
from deerflow.compile.plan_workflow import PlanContractError, PlanStep

pytest_plugins = ("test_simple_build",)


def test_variable_invocation_is_confirmed_by_execution_and_actual_library(runner):
    w = workflow(runner, actions('MK=make; "$MK"'))
    assert w.run()["status"] == "primary_completed"
    assert w.layers["primary_build_completed"] is True
    assert w.primary["artifacts"][0]["kind"] == "static_library"


def test_declared_build_and_zero_exit_without_artifact_are_insufficient(runner):
    w = workflow(runner, actions("true"))
    assert w.run()["status"] == "needs_handoff"
    assert w.layers["primary_build_completed"] is False


def test_tool_agent_submission_uses_same_variable_build_evidence(runner):
    from deerflow.compile.simple_build_agents import SimpleToolBuildService

    w = workflow(runner, actions('MK=make; "$MK"'))
    w.run()
    command_id = w.completed["build"]
    assert SimpleToolBuildService(w, None).submit(command_id, [command_id])["accepted"] is True


def test_new_main_task_does_not_run_optional_author_suite(runner):
    class MappedRuntime(LocalRuntime):
        def exec(self, session, command, **kw):
            return super().exec(session, command.replace("/artifacts", session.leadagent_artifacts_dir), **kw)

    w = workflow(runner, actions())
    w.runtime = MappedRuntime()
    w.reference = w.reference.model_copy(update={"author_tests": (PlanStep(step_id="optional", role="smoke", command="exit 37", source="作者可选完整测试", expected="不应执行", required_output=("unused",)),)})
    w.run()
    result = w.postchecks(validation_scope="main_build", replay=False)
    assert result["layers"]["author_tests"] == "not_required"
    assert result["layers"]["delivery"] == "passed"
    assert result["author_test_records"] == []


def test_unknown_failure_with_no_bound_action_goes_to_agent_without_model(runner, tmp_path):
    w = workflow(runner, actions("make no-such-target"))
    w.run()
    router = BuildStateRouter(method="rule", directory=tmp_path / "routing")
    assert router.handle(w, None) is False
    assert router.summary()["model_requests"] == 0
    assert router.summary()["agent_routes"] == 1


def test_cmake_action_comes_from_author_requirement_not_project_name(runner):
    w = workflow(runner, actions("false"))
    (w.root / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.29)\nproject(arbitrary)\n")
    state = dict(phase="configure", exit_code=1, output_tail="CMake 3.29 or higher is required. You are running version 3.28.3")
    candidates = candidate_actions(w, state, set())
    assert len(candidates) == 1 and "cmake>=3.29,<4" in candidates[0].plan.steps[0].command
    assert rule_choice(state, candidates) == "upgrade_cmake"
    assert rule_choice(state | dict(output_tail="Compiler is unable to compile a simple test program"), candidates) == "agent"
    assert candidate_actions(w, state, {"upgrade_cmake"}) == ()


def test_real_failed_command_is_not_changed_to_success_by_semantic_label(runner, tmp_path):
    class Selector:
        cost = Decimal(0)

        def choose(self, *a):
            return "agent", "phase_completed"

    w = workflow(runner, actions("false"))
    w.run()
    assert observe_state(w)["exit_code"] == 1
    router = BuildStateRouter(method="jev", directory=tmp_path, selector=Selector())
    assert router.handle(w, None) is False  # 无候选也不请求selector。
    assert w.status == "needs_handoff" and w.layers["primary_build_completed"] is None


def test_sdk_request_preserves_choices_and_counts_real_response_usage(tmp_path):
    captured = []

    def respond(request):
        body = json.loads(request.content)
        captured.append(body)
        answers = {}
        for key, q in body["questions"].items():
            choice = "execution_failed" if key == "state" else "agent"
            n = len(q["criteria"])
            answers[key] = dict(type="choice", choice=choice, probabilities={k: 0.9 if k == choice else 0.1 / (n - 1) for k in q["criteria"]}, confidence=0.8)
        return httpx2.Response(200, headers={"x-typesafe-request-id": "offline"}, json=dict(model="jev-1.13.0", answers=answers, usage=dict(input_tokens=100, output_tokens=20)))

    with TypeSafeClient(api_key="offline", model="jev-1.13.0", retry=RetryPolicy(max_retries=0), transport=httpx2.MockTransport(respond)) as client:
        selector = JevStateSelector(client=client, directory=tmp_path, deadline=(datetime.now(UTC) + timedelta(minutes=5)).isoformat())
        assert selector.choose(dict(exit_code=1), (StateAction("restore_configuration", "恢复配置", "实际配置缺失"),), Decimal("1"))[0] == "agent"
    assert len(captured) == 1
    assert selector.summary()["estimated_cost_usd_completed_responses"] == "0.0000042"
    assert selector.summary()["unknown_usage_requests"] == 0
    assert "offline" not in (tmp_path / "request-1.json").read_text()


def test_provider_error_is_once_and_unknown_usage_stops(tmp_path):
    calls = []

    def fail(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("service unavailable")

    selector = JevStateSelector(client=SimpleNamespace(system_one=fail), directory=tmp_path, deadline=(datetime.now(UTC) + timedelta(minutes=5)).isoformat())
    with pytest.raises(PlanContractError, match="停止付费"):
        selector.choose({}, (StateAction("observe_outputs", "观察", "证据不足"),), Decimal("1"))
    assert len(calls) == 1 and selector.summary()["unknown_usage_requests"] == 1


def test_comparison_counts_both_providers_and_stops_on_unknown_usage(tmp_path):
    import forge_main_build_state_comparison as comparison

    u = dict(model_requests=1, input_tokens=100, output_tokens=10, estimated_cost_usd_completed_responses="0.01", unknown_usage_requests=0)
    row = dict(agent_usage=u, router_usage=u | dict(unknown_usage_requests=1), cleanup=dict(succeeded=True))
    assert comparison.usage(row)["cost"] == Decimal("0.02")
    assert comparison.usage(row)["requests"] == 2
    assert comparison.stop_reason(row, tmp_path) == "unknown_usage"


def test_pair_schedule_reverses_order_without_changing_initial_plan():
    import forge_main_build_state_comparison as comparison

    projects = [dict(name=str(i)) for i in range(6)]
    slots = comparison.schedule(projects)
    assert len(slots) == 24
    for p in projects:
        a = [s["method"] for s in slots if s["project"] == p["name"] and s["repetition"] == 1]
        b = [s["method"] for s in slots if s["project"] == p["name"] and s["repetition"] == 2]
        assert a == b[::-1]
