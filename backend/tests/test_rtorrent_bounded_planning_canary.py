"""只验证新增提交状态跨真实Agent图生效与新恢复重置，不做构建资格。"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.middleware import ModelResponse
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_rtorrent_bounded_planning_canary import PaidNativeMeter  # noqa: E402
from forge_build_rtorrent_fixed_contract import FixedVerifierRegistry  # noqa: E402
from forge_build_rtorrent_material_gate import ReplayRequest  # noqa: E402

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.unified_plan import BuildActions

COMMON = dict(response_metadata=dict(model_name="scripted-bounded"), usage_metadata=dict(input_tokens=0, output_tokens=0, total_tokens=0))


def meter(tmp_path):
    return PaidNativeMeter(
        PlanAgentLedger(tmp_path / "agent"),
        registry=FixedVerifierRegistry(dict(verification_steps=[])),
        accepted_models=("scripted-bounded",),
        deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat(),
        packet=lambda: dict(task=dict(verification_steps=[]), source_packet=[]),
    )


def test_actual_graph_submits_after_eight_rounds_and_new_recovery_resets(tmp_path):
    bound = []

    class GateModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            bound.append([t.name if hasattr(t, "name") else t.get("function", t)["name"] for t in tools])
            return self

    @tool
    def read_proof() -> str:
        """返回零Provider只读片段。"""
        return "Autotools入口"

    proposal = dict(reason="先执行已有构建动作，错误由实际Workflow反馈", steps=[dict(step_id="build", role="build", command="make", workdir="/workspace/repo", requires=[], source="只读入口", expected="编译通过")])

    def responses(count, prefix):
        return [AIMessage(content="", tool_calls=[dict(id=f"{prefix}-{i}", name="read_proof", args={})], **COMMON) for i in range(count)] + [
            AIMessage(content="", tool_calls=[dict(id=f"{prefix}-submit", name="BuildActions", args=proposal)], **COMMON)
        ]

    value = meter(tmp_path)
    value.requires_structured_response = True
    for count, prefix in ((8, "initial"), (2, "recovery")):
        model = GateModel(responses=responses(count, prefix))
        result = create_agent(model=model, tools=[read_proof], system_prompt="共同说明", middleware=[value], response_format=ToolStrategy(BuildActions, handle_errors=False)).invoke(dict(messages=[HumanMessage(content="当前规划")]))
        assert result["structured_response"] == BuildActions.model_validate(proposal)
    assert "read_proof" in bound[0]
    assert bound[8] == ["BuildActions"]
    assert "read_proof" in bound[9]  # 新规划图重新允许读取，不沿用累计请求数。
    saved = json.loads((tmp_path / "agent/request-9.json").read_text())
    assert [s["function"]["name"] for s in saved["tools"]] == ["BuildActions"]
    assert "动作提交状态" in saved["system_message"]["content"]
    assert value.summary()["model_requests"] == 12
    assert value.summary()["recorded_tokens"] == value.summary()["unknown_usage_requests"] == 0


def test_strong_tool_agent_keeps_readonly_tools_after_eight_rounds(tmp_path):
    value = meter(tmp_path)
    history = []
    for i in range(8):
        history.extend([AIMessage(content="", tool_calls=[dict(id=str(i), name="read_source", args=dict(path="configure.ac"))]), ToolMessage(content="AC_INIT(example)", tool_call_id=str(i))])
    tools = [dict(type="function", function=dict(name="read_source", description="只读入口", parameters=dict(type="object", properties={})))]
    received = []

    def handler(actual):
        received.append(actual)
        return ModelResponse(result=[AIMessage(content="脚本结束", **COMMON)])

    value.wrap_model_call(ReplayRequest(messages=[HumanMessage(content="当前状态"), *history], system_message=SystemMessage(content="强工具"), tools=tools), handler)
    assert received[0].tools == tools
    assert "动作提交状态" not in received[0].system_message.content
    assert value.summary()["model_requests"] == 1 and value.summary()["unknown_usage_requests"] == 0


def test_hidden_read_tool_cannot_execute_after_submit_state(tmp_path):
    executed = []

    class GateModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    @tool
    def read_source(path: str) -> str:
        """只读测试入口。"""
        executed.append(path)
        return json.dumps(dict(path=path, content="AC_INIT(example)", sha256="fixture"))

    proposal = dict(reason="读取结束", steps=[dict(step_id="build", role="build", command="make", workdir="/workspace/repo", requires=[], source="只读入口", expected="编译通过")])
    responses = [AIMessage(content="", tool_calls=[dict(id=f"read-{i}", name="read_source", args=dict(path="configure.ac"))], **COMMON) for i in range(9)]
    responses.append(AIMessage(content="", tool_calls=[dict(id="submit", name="BuildActions", args=proposal)], **COMMON))
    value = meter(tmp_path)
    value.requires_structured_response = True
    result = create_agent(model=GateModel(responses=responses), tools=[read_source], system_prompt="共同说明", middleware=[value], response_format=ToolStrategy(BuildActions, handle_errors=False)).invoke(
        dict(messages=[HumanMessage(content="规划")])
    )
    assert result["structured_response"] == BuildActions.model_validate(proposal)
    assert len(executed) == 8
    feedback = [m for m in result["messages"] if m.type == "tool" and m.tool_call_id == "read-8"]
    assert len(feedback) == 1 and json.loads(feedback[0].content)["error"] == "planning_submit_required"
    assert value.summary()["model_requests"] == 10 and value.summary()["tool_calls"] == 9
    assert value.summary()["recorded_tokens"] == value.summary()["unknown_usage_requests"] == 0
