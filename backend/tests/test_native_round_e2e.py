"""免费真实构建入口的模型封闭性、绝对时窗及真实图原生交互。"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_native_round_e2e import NativeE2EMeter, NativeGateModel, scripted_model  # noqa: E402
from forge_build_rtorrent_fixed_contract import FixedVerifierRegistry  # noqa: E402
from forge_build_unified_plan import METHODS  # noqa: E402

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_workflow import PlanContractError


def meter(tmp_path, *, deadline=None, accepted=("scripted-gate",)):
    task = dict(verification_steps=[])
    return NativeE2EMeter(
        PlanAgentLedger(tmp_path / "agent"),
        accepted_models=accepted,
        registry=FixedVerifierRegistry(task),
        packet=lambda: dict(task=task, source_packet=[]),
        deadline=deadline or (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    )


def reply(content="脚本终结", tokens=0):
    return AIMessage(content=content, response_metadata=dict(model_name="scripted-gate"), usage_metadata=dict(input_tokens=tokens, output_tokens=0, total_tokens=tokens))


@pytest.mark.parametrize("failure", ["expired", "provider_identity", "prior_usage", "unknown_usage"])
def test_free_admission_stops_before_request(tmp_path, failure):
    value = meter(tmp_path, deadline="2020-01-01T00:00:00+00:00" if failure == "expired" else None, accepted=("provider",) if failure == "provider_identity" else ("scripted-gate",))
    if failure == "prior_usage":
        value.input_tokens = 1
    if failure == "unknown_usage":
        value.unknown_usage_requests.add(1)
    with pytest.raises(PlanContractError):
        value._before_request()
    assert value.summary()["model_requests"] == 0


def test_fake_responses_are_not_automatically_repeated():
    model = NativeGateModel(responses=[reply()])
    assert model.invoke("工程脚本").content == "脚本终结"
    with pytest.raises(PlanContractError, match="已用尽"):
        model.invoke("不应重试")
    assert model.served == 1


def test_other_model_rejected_before_handler_or_request(tmp_path):
    value = meter(tmp_path)
    model = FakeMessagesListChatModel(responses=[reply()])
    with pytest.raises(PlanContractError, match="非固定脚本模型"):
        create_agent(model=model, tools=[], middleware=[value]).invoke(dict(messages=[HumanMessage(content="开始")]))
    assert value.summary()["model_requests"] == 0 and model.i == 0


def test_nonzero_response_is_retained_and_stops_without_retry(tmp_path):
    value = meter(tmp_path)
    model = NativeGateModel(responses=[reply(tokens=1), reply()])
    with pytest.raises(PlanContractError, match="非零用量"):
        create_agent(model=model, tools=[], middleware=[value]).invoke(dict(messages=[HumanMessage(content="开始")]))
    assert model.served == 1
    assert value.summary()["recorded_tokens"] == 1 and value.summary()["unknown_usage_requests"] == 0
    assert json.loads((tmp_path / "agent/response-1.json").read_text())[0]["usage_metadata"]["total_tokens"] == 1


def test_actual_graph_preserves_native_round_under_free_meter(tmp_path):
    @tool
    def read_source(path: str, start_line: int = 1) -> str:
        """封闭只读源码夹具。"""
        assert path == "configure.ac" and start_line == 1
        return json.dumps(dict(path=path, start_line=start_line, content="AC_INIT(offline)", read_request=dict(path=path, start_line=start_line)))

    value = meter(tmp_path)
    model = NativeGateModel(
        responses=[
            AIMessage(
                content="",
                additional_kwargs=dict(reasoning_content="固定脚本前轮"),
                tool_calls=[dict(id="native", name="read_source", args=dict(path="configure.ac"))],
                response_metadata=dict(model_name="scripted-gate"),
                usage_metadata=dict(input_tokens=0, output_tokens=0, total_tokens=0),
            ),
            reply(),
        ]
    )
    result = create_agent(model=model, tools=[read_source], middleware=[value]).invoke(dict(messages=[HumanMessage(content="开始")]))
    assert result["messages"][-1].content == "脚本终结" and model.served == 2
    request = json.loads((tmp_path / "agent/request-2.json").read_text())
    assert [m["type"] for m in request["messages"]] == ["human", "ai", "tool"]
    assert request["messages"][1]["additional_kwargs"]["reasoning_content"] == "固定脚本前轮"
    assert json.loads(request["messages"][2]["content"])["content"] == "AC_INIT(offline)"
    assert value.summary()["model_requests"] == 2 and value.summary()["recorded_tokens"] == 0


@pytest.mark.parametrize("method", METHODS)
def test_each_strategy_has_native_read_round_before_original_fixture(method):
    root = Path(__file__).resolve().parents[2]
    spec = json.loads((root / "benchmarks/manifests/cpp-build-rtorrent-common-entry-gate-v2.json").read_text())
    model = scripted_model(spec, method)
    assert len(model.responses) == 2
    first, second = model.responses
    assert first.tool_calls[0]["name"] == "read_source" and first.additional_kwargs["reasoning_content"]
    if method == METHODS[2]:
        assert second.tool_calls[-1]["name"] == "submit_verified_build" and second.tool_calls[-1]["args"] == {}
        assert sum(c["name"] == "run_fixed_tests" for c in second.tool_calls) == 1
    else:
        assert second.tool_calls[0]["name"] == "ObservedBuildActions"
        assert all(s["role"] in ("dependency", "configure", "build") for s in second.tool_calls[0]["args"]["steps"])
