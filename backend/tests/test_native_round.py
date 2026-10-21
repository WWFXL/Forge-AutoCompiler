"""共同原生材料接口：完整交互、准入前停止与零费用计量。"""

import json
import sys
from pathlib import Path

import pytest
from langchain.agents.middleware import ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_native_round import NativeRoundMeter, last_complete_round  # noqa: E402
from forge_build_rtorrent_fixed_contract import FixedVerifierRegistry  # noqa: E402
from forge_build_rtorrent_material_gate import ReplayRequest  # noqa: E402

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_agent_v2 import PlanAgentMeterV2, PlanThinkingDeepSeek
from deerflow.compile.plan_workflow import PlanContractError


def round_messages():
    return [
        AIMessage(content="", additional_kwargs=dict(reasoning_content="已检查依赖"), tool_calls=[dict(id="a", name="read_source", args=dict(path="configure.ac"))]),
        ToolMessage(content="AC_INIT(example)", tool_call_id="a", name="read_source"),
    ]


class FreeMeter(NativeRoundMeter):
    """仅测试/脚本handler，不能当作付费时窗准入。"""

    def _before_request(self):
        return PlanAgentMeterV2._before_request(self)


def meter(tmp_path, cls=FreeMeter):
    task = dict(verification_steps=[])
    return cls(
        PlanAgentLedger(tmp_path / "agent"), registry=FixedVerifierRegistry(task), accepted_models=("scripted-native",), deadline="2020-01-01T00:00:00+00:00", packet=lambda: dict(task=task, source_packet=[], state=dict(status="inspected"))
    )


def request(history=None, *, system="共同说明", tools=None):
    return ReplayRequest(messages=[HumanMessage(content="旧提示"), *(history or [])], system_message=SystemMessage(content=system), tools=tools or [])


def response(**metadata):
    return ModelResponse(result=[AIMessage(content="零费用脚本", response_metadata=dict(model_name="scripted-native", **metadata), usage_metadata=dict(input_tokens=0, output_tokens=0, total_tokens=0))])


@pytest.mark.parametrize("with_history", [False, True])
def test_exact_native_round_reaches_handler_ledger_and_deepseek_serializer(tmp_path, with_history):
    value = meter(tmp_path)
    history = round_messages() if with_history else []
    received = []

    def handler(actual):
        received.append(actual)
        return response()

    value.wrap_model_call(request(history), handler)
    saved = json.loads((tmp_path / "agent/request-1.json").read_text())
    assert saved["messages"] == [m.model_dump(mode="json") for m in received[0].messages]
    assert saved["messages"][1:] == [m.model_dump(mode="json") for m in history]
    assert "remaining_budget" in json.loads(saved["messages"][0]["content"])
    assert value.summary()["model_requests"] == 1 and value.summary()["recorded_tokens"] == value.summary()["unknown_usage_requests"] == 0
    serialized = PlanThinkingDeepSeek(model="deepseek-v4-pro", api_key="zero-provider-placeholder")._get_request_payload(received[0].messages)
    if with_history:
        assert serialized["messages"][1]["reasoning_content"] == "已检查依赖"
        assert serialized["messages"][1]["tool_calls"][0]["id"] == serialized["messages"][2]["tool_call_id"] == "a"
    limits = value.tracker.limits
    assert (limits.max_agent_steps, limits.max_tool_calls, limits.max_commands, limits.max_recorded_tokens, limits.max_recorded_tokens_per_response) == (72, 48, 32, 400000, 200000)


@pytest.mark.parametrize("kind", ["orphan", "missing", "duplicate", "no_calls", "material", "schema"])
def test_rejects_before_request_or_handler_without_unknown_usage(tmp_path, kind):
    value = meter(tmp_path)
    history = round_messages()
    system, tools = "共同说明", []
    if kind == "orphan":
        history = history[1:]
    elif kind == "missing":
        history = history[:1]
    elif kind == "duplicate":
        history.append(history[-1])
    elif kind == "no_calls":
        history = [AIMessage(content="非工具终态")]
    elif kind == "material":
        system = "x" * 100001
    else:
        tools = [dict(type="function", function=dict(name="oversized", description="x" * 8001, parameters=dict(type="object", properties={})))]
    with pytest.raises(PlanContractError):
        value.wrap_model_call(request(history, system=system, tools=tools), lambda _: pytest.fail("不应到达handler"))
    assert value.summary()["model_requests"] == value.summary()["unknown_usage_requests"] == 0


def test_paid_path_keeps_absolute_deadline_and_larger_fee_reservation(tmp_path):
    value = meter(tmp_path, NativeRoundMeter)
    with pytest.raises(PlanContractError):
        value.wrap_model_call(request(), lambda _: pytest.fail("授权时窗已过"))
    assert value.summary()["model_requests"] == 0
    value.cost_usd = 0.71
    with pytest.raises(PlanContractError, match="下一完整请求"):
        value._before_request()


def test_length_stop_keeps_known_usage_and_does_not_retry(tmp_path):
    value = meter(tmp_path)
    calls = []

    def handler(actual):
        calls.append(actual)
        return response(finish_reason="length")

    with pytest.raises(PlanContractError, match="响应截断"):
        value.wrap_model_call(request(), handler)
    assert len(calls) == 1 and value.summary()["model_requests"] == 1
    assert value.summary()["unknown_usage_requests"] == 0


def test_uses_only_latest_complete_round():
    first = round_messages()
    latest = [AIMessage(content="", tool_calls=[dict(id="b", name="read_source", args={})]), ToolMessage(content="第二片段", tool_call_id="b")]
    assert last_complete_round([HumanMessage(content="提示"), *first, *latest]) == latest


def test_actual_agent_graph_keeps_native_round_for_second_scripted_call(tmp_path):
    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.tools import tool

    class GateModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    @tool
    def read_proof() -> str:
        """返回离线只读证明，不访问网络或文件。"""
        return "已检查生成入口"

    common = dict(response_metadata=dict(model_name="scripted-native"), usage_metadata=dict(input_tokens=0, output_tokens=0, total_tokens=0))
    model = GateModel(responses=[AIMessage(content="", additional_kwargs=dict(reasoning_content="先检查入口"), tool_calls=[dict(id="graph-a", name="read_proof", args={})], **common), AIMessage(content="脚本完成", **common)])
    value = meter(tmp_path)
    result = create_agent(model=model, tools=[read_proof], system_prompt="共同资格", middleware=[value]).invoke(dict(messages=[HumanMessage(content="开始")]))
    assert result["messages"][-1].content == "脚本完成"
    second = json.loads((tmp_path / "agent/request-2.json").read_text())
    assert [m["type"] for m in second["messages"]] == ["human", "ai", "tool"]
    assert second["messages"][1]["additional_kwargs"]["reasoning_content"] == "先检查入口"
    assert second["messages"][2]["tool_call_id"] == "graph-a"
    assert value.summary()["model_requests"] == 2 and value.summary()["tool_calls"] == 1
    assert value.summary()["recorded_tokens"] == value.summary()["unknown_usage_requests"] == 0
