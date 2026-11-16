"""恢复候选跨压缩保留及真实Agent图接线，不估计模型效果。"""

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from test_plan_agent import ScriptedPlanModel, response
from test_recovery_environment import meter_at
from test_simple_build import actions, simple_actions, workflow

from deerflow.compile.recovery_diagnostic_memory import MEMORY_PROMPT, RecoveryDiagnosticMemory
from deerflow.compile.recovery_environment import RecoveryEnvironment
from deerflow.compile.request_context_budget import RequestContextBudget
from deerflow.compile.simple_build_task import propose_simple
from deerflow.compile.simple_planning_context import PlanningContext

pytest_plugins = ["test_simple_build"]


def found(memory, *, handoff="h1", output="different-dev - headers for toolkit\n", status="ok", command="query1"):
    memory.observe("inspect_build_environment", dict(kind="package_search", query="toolkit"), dict(status=status, output=output, command_id=command, log_path="logs/" + command), handoff_id=handoff)


def test_candidates_are_observed_not_preloaded_and_checks_do_not_imply_success():
    memory = RecoveryDiagnosticMemory()
    assert memory.snapshot(dict(handoff_id="h1"))["candidates"] == []
    found(memory)
    memory.observe("inspect_build_environment", dict(kind="package", query="different-dev"), dict(status="query_failed", installed=False, command_id="q2"), handoff_id="h1")
    data = memory.snapshot(dict(handoff_id="h2"))
    candidate = data["candidates"][0]
    assert candidate["package"] == "different-dev"
    assert candidate["evidence_handoff_id"] == "h1"
    assert candidate["checks"]["package"]["installed"] is False
    assert data["current_handoff_id"] == "h2"
    assert candidate["checks"]["package"]["from_current_handoff"] is False
    assert "修复成功" in data["scope"] and "可能过期" in data["next_action"]
    assert "success" not in candidate and "installed" not in candidate


@pytest.mark.parametrize("status", ["budget_exhausted", "invalid_query", "query_failed", "unavailable"])
def test_errors_do_not_create_candidates(status):
    memory = RecoveryDiagnosticMemory()
    found(memory, status=status)
    assert not memory.snapshot(dict(handoff_id="h1"))["candidates"]


def test_memory_bounded_with_explicit_omissions_and_unexecuted_queries_ignored():
    memory = RecoveryDiagnosticMemory()
    found(memory, output="\n".join(f"package-{i}-dev - " + "长描述" * 300 for i in range(60)))
    memory.observe("inspect_build_environment", dict(kind="package_search", query="x"), dict(status="budget_exhausted"), handoff_id="h1")
    data = memory.snapshot(dict(handoff_id="h1"))
    assert 0 < len(data["candidates"]) <= 20 and data["omitted_candidates"] >= 40
    assert len(json.dumps(data, ensure_ascii=False).encode()) <= 10000
    found(memory)
    assert list(memory.observations.values())[-1]["repeat_count"] == 2
    assert not RecoveryDiagnosticMemory().snapshot(dict(handoff_id="other"))["candidates"]


def test_actual_capacity_pruning_keeps_candidate_and_tool_pairs(tmp_path):
    memory = RecoveryDiagnosticMemory()
    found(memory)
    context = PlanningContext(dict(handoff=dict(handoff_id="h1")), diagnostic_memory=memory)
    old = [AIMessage(content="", tool_calls=[dict(name="inspect_build_environment", args={}, id="old")]), ToolMessage(content="different-dev - headers", tool_call_id="old")]

    class Request:
        messages = [HumanMessage(content="task"), *old, AIMessage(content="", tool_calls=[dict(name="read_source", args={}, id="new")]), ToolMessage(content="x" * 48000, tool_call_id="new")]
        system_message = None
        model_settings = {}
        tools = []
        response_format = None

        def override(self, **kwargs):
            return SimpleNamespace(**kwargs, response_format=None)

    meter = meter_at(tmp_path)
    meter.context_budget = RequestContextBudget(max_input_tokens=5000)
    sent = []

    def handler(request):
        sent.extend(request.messages)
        return SimpleNamespace(result=[response("SimpleBuildActions", simple_actions().model_dump(mode="json"))])

    context.request(meter, Request(), handler)
    assert context.pruned_groups > 0
    packet = json.loads(sent[0].content)
    assert packet["recovery_diagnostic_memory"]["candidates"][0]["package"] == "different-dev"
    assert all(not (m.type == "tool" and m.tool_call_id == "old") for m in sent)
    assert (tmp_path / "agent/diagnostic-memory-request-1.json").is_file()


def test_actual_graph_queries_record_then_returns_to_real_build(runner):
    w = workflow(runner, actions("make missing-target"))
    assert w.run()["status"] == "needs_handoff"
    meter = meter_at(w.root)
    memory = RecoveryDiagnosticMemory()
    service = RecoveryEnvironment(w, meter, diagnostic_memory=memory)
    model = ScriptedPlanModel(responses=[response("search_build_files", dict(query="int sample", scope="project")), response("SimpleBuildActions", simple_actions().model_dump(mode="json"))])
    revised, reason = propose_simple(model=model, task=w.plan.task, source_root=w.root, session_root=w.root, meter=meter, current_plan=w.plan, handoff=w.handoff, revision_validator=w.validate_revision, diagnostics=service)
    sent = json.loads((w.root / "agent/request-2.json").read_text())
    data = json.loads(sent["messages"][0]["content"])["recovery_diagnostic_memory"]
    assert "int sample(void)" in data["observations"][0]["matches"][0]["text"]
    assert MEMORY_PROMPT in sent["system_message"]["content"]
    assert service.calls == 1
    w.apply_revision(handoff_id=w.handoff["handoff_id"], plan=revised, reason=reason)
    assert w.run()["status"] == "primary_completed"
    assert (w.root / "libsample.a").is_file()


def test_default_context_unchanged():
    context = PlanningContext({})
    assert context.diagnostic_memory is None


def test_old_single_run_authorization_does_not_authorize_memory_run():
    import sys
    from datetime import UTC, datetime, timedelta
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from forge_libffi_diagnostic_memory import validate_authorization

    with pytest.raises(ValueError, match="授权"):
        validate_authorization(dict(identity="cpp-build-libffi-diagnostic-order-flash-v1", maximum_cost_usd="1.00", user_authorized=True, deadline_utc=(datetime.now(UTC) + timedelta(minutes=30)).isoformat()))
