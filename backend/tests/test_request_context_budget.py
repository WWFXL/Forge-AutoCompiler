"""共享容量、计量前停止及冻结失败消息的零Provider回放。"""

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from test_recovery_environment import meter_at

from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.recovery_diagnostic_memory import RecoveryDiagnosticMemory
from deerflow.compile.request_context_budget import RequestContextBudget

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_request_capacity_replay import ReplayRequest, replay


def test_system_and_tools_share_input_budget_and_output_ceiling(tmp_path):
    meter = meter_at(tmp_path)
    meter.context_budget = RequestContextBudget(max_input_tokens=4000)
    request = ReplayRequest(messages=[HumanMessage(content="task")], system_message=SystemMessage(content="sys"), tools=[], model_settings={"max_tokens": 100000}, response_format=None, model=None)
    sent = []

    def handler(request):
        sent.append(request)
        return type("Response", (), {"result": [AIMessage(content="ok", usage_metadata=dict(input_tokens=3, output_tokens=2, total_tokens=5), response_metadata=dict(model_name="test-model"))]})()

    meter.wrap_model_call(request, handler)
    assert sent[0].model_settings["max_tokens"] == 32768
    assert meter.summary()["recorded_tokens"] == 5
    schema = dict(type="function", function=dict(name="large", description="schema " * 5000, parameters=dict(type="object", properties={})))
    for fields in [dict(system_message=SystemMessage(content="system " * 5000)), dict(tools=[schema])]:
        with pytest.raises(PlanContractError, match="上下文容量"):
            meter.wrap_model_call(request.override(**fields), handler)
    assert len(sent) == 1 and meter.summary()["unknown_usage_requests"] == 0


def test_inconsistent_capacity_or_insufficient_fee_stops_before_handler(tmp_path):
    meter = meter_at(tmp_path)
    meter.context_budget = RequestContextBudget(max_input_tokens=80000)
    with pytest.raises(PlanContractError, match="单次用量上限"):
        meter._before_request()
    meter.context_budget = RequestContextBudget(model_context_tokens=90000)
    with pytest.raises(PlanContractError, match="模型上下文"):
        meter._before_request()
    meter.context_budget = RequestContextBudget()
    meter.tracker.limits = replace(meter.tracker.limits, max_recorded_tokens_per_response=90000)
    with pytest.raises(PlanContractError, match="单次用量上限"):
        meter._before_request()
    meter.tracker.limits = replace(meter.tracker.limits, max_recorded_tokens_per_response=100000)
    meter.maximum_cost_usd = 0
    with pytest.raises(PlanContractError, match="费用不足"):
        meter._before_request()
    assert meter.summary()["model_requests"] == 0
    assert meter.summary()["unknown_usage_requests"] == 0


def test_strong_tool_uses_same_capacity_with_dynamic_state_and_recent_feedback(tmp_path):
    meter = meter_at(tmp_path)
    meter.packet = lambda: dict(state="important-state", detail="状态" * 18000)
    request = ReplayRequest(
        messages=[HumanMessage(content="task"), ToolMessage(content="latest-feedback", tool_call_id="q", name="diagnostic")], system_message=SystemMessage(content="tool-agent"), tools=[], model_settings={}, response_format=None, model=None
    )
    sent = []

    def handler(request):
        sent.append(request)
        return type("Response", (), {"result": [AIMessage(content="ok", usage_metadata=dict(input_tokens=3, output_tokens=2, total_tokens=5), response_metadata=dict(model_name="test-model"))]})()

    meter.wrap_model_call(request, handler)
    packet = json.loads(sent[0].messages[0].content)
    assert packet["state"] == "important-state"
    assert "planning_progress" not in packet
    assert packet["recent_tool_results"][0]["content"] == "latest-feedback"
    assert len(sent[0].messages[0].content.encode()) > 50000
    assert meter.summary()["model_requests"] == 1


def test_verified_candidate_survives_broad_search_without_mutating_memory():
    memory = RecoveryDiagnosticMemory()
    memory.observe("inspect_build_environment", dict(kind="package_search", query="broad"), dict(status="ok", command_id="q1", output="\n".join(f"package-{i}-dev - candidate" for i in range(20))), handoff_id="h")
    memory.observe("inspect_build_environment", dict(kind="package", query="package-19-dev"), dict(status="ok", command_id="q2", installed=False), handoff_id="h")
    original = json.dumps(memory.observations)
    data = memory.snapshot(dict(handoff_id="h"))
    assert data["candidates"][0]["package"] == "package-19-dev"
    assert data["candidates"][0]["checks"]["package"]["installed"] is False
    assert len(data["candidates"]) == 6 and data["omitted_candidates"] == 14
    assert json.dumps(memory.observations) == original
    assert len(memory.candidates) == 20


def test_frozen_failed_recovery_can_send_verified_candidate_and_full_tool_group(tmp_path):
    result = replay(tmp_path / "replay")
    assert result["provider_calls"] == 0 and result["cost_usd"] == 0
    assert result["current"]["latest_tool_group_unchanged"]
    assert result["current"]["verified_missing_candidate_preserved"]
    capacity = result["current"]["capacity"]
    assert capacity["reserved_input_tokens"] <= 64000
