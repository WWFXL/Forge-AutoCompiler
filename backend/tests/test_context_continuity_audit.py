"""审计须识别真正的会话保留、完整工具轮次与未发送请求。"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_context_continuity_audit import inspect_agent  # noqa: E402


def fixture(tmp_path, *, retained=False, large=False):
    ai = dict(type="ai", content="已确认依赖，准备配置。", additional_kwargs=dict(reasoning_content="原始思考"), tool_calls=[dict(id="a", name="read_source", args={}), dict(id="b", name="list_source", args={})])
    tools = [dict(type="tool", name="read_source", tool_call_id="a", content="源码"), dict(type="tool", name="list_source", tool_call_id="b", content="目录")]
    human = dict(type="human", content="状态" + ("x" * 51000 if large else ""))
    for seq in (1, 2):
        value = dict(messages=[human, ai, *tools] if retained and seq == 2 else [human], system_message=None, tools=[])
        (tmp_path / f"request-{seq}.json").write_text(json.dumps(value, ensure_ascii=False))
    (tmp_path / "response-1.json").write_text(json.dumps([ai], ensure_ascii=False))
    events = [dict(event="model.request_started", request_sequence=1), *[dict(event="tool.completed", result=t) for t in reversed(tools)], dict(event="model.request_started", request_sequence=2)]
    (tmp_path / "events.jsonl").write_text("\n".join(map(json.dumps, events)))
    return events


def test_detects_replaced_history_and_reconstructs_complete_round(tmp_path):
    fixture(tmp_path)
    rows, skipped = inspect_agent(tmp_path, tmp_path)
    assert len(rows) == 2 and not skipped
    assert not rows[1]["native_previous_ai_preserved"] and not rows[1]["native_previous_tools_preserved"]
    assert rows[1]["previous_tool_call_ids"] == ["a", "b"] and rows[1]["previous_round_pairing_complete"]
    assert rows[1]["previous_reasoning_present"] and rows[1]["naive_append_fits_original_50000"]


def test_recognizes_actual_native_history(tmp_path):
    fixture(tmp_path, retained=True)
    rows, _ = inspect_agent(tmp_path, tmp_path)
    assert rows[1]["native_previous_ai_preserved"] and rows[1]["native_previous_tools_preserved"]


def test_existing_deepseek_serializer_preserves_complete_native_round_without_network():
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek

    model = PlanThinkingDeepSeek(model="deepseek-v4-pro", api_key="zero-provider-placeholder", max_retries=0)
    messages = [
        HumanMessage(content="权威状态"),
        AIMessage(content="", additional_kwargs=dict(reasoning_content="离线占位思考"), tool_calls=[dict(id="a", name="read_source", args=dict(path="configure.ac"))]),
        ToolMessage(content="只读内容", tool_call_id="a"),
    ]
    payload = model._get_request_payload(messages)
    assert [m["role"] for m in payload["messages"]] == ["user", "assistant", "tool"]
    assert payload["messages"][1]["reasoning_content"] == "离线占位思考"
    assert payload["messages"][1]["tool_calls"][0]["id"] == payload["messages"][2]["tool_call_id"] == "a"


def test_does_not_count_unstarted_saved_request(tmp_path):
    fixture(tmp_path)
    (tmp_path / "request-3.json").write_text("{}")
    rows, skipped = inspect_agent(tmp_path, tmp_path)
    assert len(rows) == 2 and skipped == ["request-3.json"]


def test_reports_material_overflow_without_relaxing_limit(tmp_path):
    fixture(tmp_path, large=True)
    rows, _ = inspect_agent(tmp_path, tmp_path)
    assert rows[1]["naive_append_bytes"] > 50000 and not rows[1]["naive_append_fits_original_50000"]


@pytest.mark.parametrize("malformation", ["missing", "orphan", "duplicate", "request_duplicate", "request_gap"])
def test_rejects_incomplete_or_ambiguous_lifecycle(tmp_path, malformation):
    events = fixture(tmp_path)
    if malformation == "missing":
        events.pop(1)
    elif malformation == "orphan":
        events[1]["result"]["tool_call_id"] = "other"
    elif malformation == "duplicate":
        events.insert(1, events[1])
    elif malformation == "request_duplicate":
        events.append(events[-1])
    else:
        events[-1]["request_sequence"] = 3
    (tmp_path / "events.jsonl").write_text("\n".join(map(json.dumps, events)))
    with pytest.raises(ValueError):
        inspect_agent(tmp_path, tmp_path)
