"""共同接收链的实际Agent调用与原错误反馈；脚本模型，零Provider。"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from test_goal_state import task

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_common_harness import common_harness_interfaces, literal_safe_factor_packet  # noqa: E402
from forge_build_goal_state_ablation import CommonFlashMeter  # noqa: E402
from forge_build_rtorrent_fixed_contract import FixedVerifierRegistry  # noqa: E402
from forge_build_rtorrent_shared_values import restore_values  # noqa: E402

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_candidate_reception import propose_received, text_candidate
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.recovery_text_factors import FACTOR_TABLE, restore_factor_packet
from deerflow.compile.unified_plan_equivalent_observed import ObservedBuildActions, assemble_observed

COMMON = dict(response_metadata=dict(model_name="scripted-common"), usage_metadata=dict(input_tokens=0, output_tokens=0, total_tokens=0))


class GateModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def candidate(command="make -j2"):
    return dict(reason="共同接收的受控候选", steps=[dict(step_id="build", role="build", command=command, source="原始源码", expected="实际编译")])


def meter(tmp_path, value):
    registry = FixedVerifierRegistry(value.model_dump(mode="json"))
    return CommonFlashMeter(
        PlanAgentLedger(tmp_path / "agent"),
        registry=registry,
        obligation={},
        accepted_models=("scripted-common",),
        deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat(),
        packet=lambda: dict(task=value.model_dump(mode="json"), source_packet=[], current_plan=None, handoff=None),
    ), registry


@pytest.mark.parametrize("presentation", ["tool_call", "json_text", "json_fence"])
def test_same_schema_and_assembly_preserve_raw_response(tmp_path, presentation):
    value, data = task(), candidate()
    tool = presentation == "tool_call"
    content = "" if tool else json.dumps(data, ensure_ascii=False)
    if presentation == "json_fence":
        content = "ObservedBuildActions:\n```json\n" + content + "\n```"
    response = AIMessage(content=content, tool_calls=[dict(name="ObservedBuildActions", args=data, id="candidate")] if tool else [], **COMMON)
    accounting, _ = meter(tmp_path, value)
    with common_harness_interfaces():
        plan, _ = propose_received(model=GateModel(responses=[response]), task=value, source_root=tmp_path, session_root=tmp_path, meter=accounting)
    assert plan == assemble_observed(value, ObservedBuildActions.model_validate(data), revision=1)
    raw = json.loads((tmp_path / "agent/response-1.json").read_text())[0]
    assert raw["content"] == content and bool(raw["tool_calls"]) == tool
    events = [json.loads(line) for line in (tmp_path / "agent/events.jsonl").read_text().splitlines()]
    assert [event["presentation"] for event in events if event["event"] == "candidate.accepted"] == [presentation]
    assert accounting.summary()["model_requests"] == 1 and accounting.summary()["recorded_tokens"] == accounting.summary()["unknown_usage_requests"] == 0


@pytest.mark.parametrize("content", ['{"reason":"a","reason":"b","steps":[]}', '{"reason":NaN,"steps":[]}', "说明一下构建方法", "{}\n{}", "```json\n{}\n```\n```json\n{}\n```", "执行这个方案：\n```json\n{}\n```"])
def test_ambiguous_or_non_json_output_is_not_guessed(content):
    with pytest.raises(PlanContractError):
        text_candidate(content)


def test_text_schema_failure_receives_same_single_correction(tmp_path):
    value = task()
    invalid = candidate()
    invalid["steps"][0]["required_output"] = ["旧字段不能绕过校验"]
    responses = [AIMessage(content=json.dumps(data, ensure_ascii=False), **COMMON) for data in (invalid, candidate())]
    accounting, _ = meter(tmp_path, value)
    with common_harness_interfaces():
        propose_received(model=GateModel(responses=responses), task=value, source_root=tmp_path, session_root=tmp_path, meter=accounting)
    request = json.loads((tmp_path / "agent/request-2.json").read_text())
    assert "上次建议结构/装配不合法" in request["messages"][0]["content"]
    assert "required_output" in request["messages"][0]["content"]
    assert accounting.summary()["model_requests"] == 2


def test_literal_bad_path_feedback_survives_next_request_and_agent_can_correct(tmp_path):
    value = task()
    (tmp_path / "README.md").write_text("原作者的构建说明\n")
    responses = [
        AIMessage(content="", tool_calls=[dict(name="read_source", args=dict(path="~6~.mk", start_line=120), id="invalid-path")], **COMMON),
        AIMessage(content="", tool_calls=[dict(name="read_source", args=dict(path="README.md"), id="corrected-path")], **COMMON),
        AIMessage(content=json.dumps(candidate()), **COMMON),
    ]
    accounting, registry = meter(tmp_path, value)
    with common_harness_interfaces():
        propose_received(model=GateModel(responses=responses), task=value, source_root=tmp_path, session_root=tmp_path, meter=accounting)
    request = json.loads((tmp_path / "agent/request-2.json").read_text())
    packet = json.loads(request["messages"][0]["content"])
    packet.pop("remaining_budget")
    restored = registry.restore(restore_values(restore_factor_packet(packet)))
    assert restored["read_index"][-1]["request"]["path"] == "~6~.mk"
    assert restored["read_index"][-1]["accepted"] is False
    assert "~6~.mk" in request["messages"][-1]["content"]
    assert accounting.summary()["model_requests"] == 3
    assert (tmp_path / "agent/response-1.json").is_file()


def test_literal_packet_remains_reversible_and_reserved_fields_still_rejected():
    packet = dict(read_request=dict(path="~6~.mk"), error="literal ~7~ and repeated original text " * 50)
    encoded = literal_safe_factor_packet(packet)
    assert restore_factor_packet(encoded) == packet
    assert FACTOR_TABLE not in encoded
    with pytest.raises(PlanContractError, match="保留因子字段"):
        literal_safe_factor_packet({FACTOR_TABLE: [], "path": "~6~.mk"})


def test_plain_explanation_stops_without_extra_request(tmp_path):
    value = task()
    accounting, _ = meter(tmp_path, value)
    with common_harness_interfaces(), pytest.raises(PlanContractError, match="完整JSON"):
        propose_received(model=GateModel(responses=[AIMessage(content="没有可行方案", **COMMON)]), task=value, source_root=tmp_path, session_root=tmp_path, meter=accounting)
    assert accounting.summary()["model_requests"] == 1
    assert accounting.summary()["unknown_usage_requests"] == 0


def test_recovery_text_cannot_claim_success_without_execution_change(tmp_path):
    value, data = task(), candidate()
    current = assemble_observed(value, ObservedBuildActions.model_validate(data), revision=1)
    handoff = dict(handoff_id="actual-recovery", plan_sha256=current.fingerprint(), step_id="build", recent_commands=[])
    accounting, _ = meter(tmp_path, value)
    responses = [AIMessage(content=json.dumps(data), **COMMON)] * 2
    with common_harness_interfaces(), pytest.raises(PlanContractError, match="no_execution_change"):
        propose_received(model=GateModel(responses=responses), task=value, source_root=tmp_path, session_root=tmp_path, meter=accounting, current_plan=current, handoff=handoff)
    assert accounting.summary()["model_requests"] == 2


@pytest.mark.parametrize("metadata,reason", [(dict(model_name="scripted-common", finish_reason="length"), "响应截断"), (dict(model_name="unexpected-provider"), "模型标识")])
def test_original_truncation_and_provider_identity_stop_before_candidate_acceptance(tmp_path, metadata, reason):
    value = task()
    accounting, _ = meter(tmp_path, value)
    response = AIMessage(content=json.dumps(candidate()), response_metadata=metadata, usage_metadata=COMMON["usage_metadata"])
    with common_harness_interfaces(), pytest.raises(PlanContractError, match=reason):
        propose_received(model=GateModel(responses=[response]), task=value, source_root=tmp_path, session_root=tmp_path, meter=accounting)
    assert (tmp_path / "agent/response-1.json").is_file()
    assert not (tmp_path / "agent/observed-actions-1-0.json").exists()


def test_text_output_is_charged_from_same_original_usage(tmp_path):
    value = task()
    accounting, _ = meter(tmp_path, value)
    response = AIMessage(content=json.dumps(candidate()), response_metadata=COMMON["response_metadata"], usage_metadata=dict(input_tokens=11, output_tokens=7, total_tokens=18))
    with common_harness_interfaces():
        propose_received(model=GateModel(responses=[response]), task=value, source_root=tmp_path, session_root=tmp_path, meter=accounting)
    usage = accounting.summary()
    assert usage["input_tokens"] == 11 and usage["output_tokens"] == 7 and usage["recorded_tokens"] == 18
    assert usage["estimated_cost_usd_completed_responses"] == pytest.approx((11 * 0.30 + 7 * 1.20) / 1_000_000)
