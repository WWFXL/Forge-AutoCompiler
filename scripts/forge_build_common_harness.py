"""新实验共同的候选接收与字面引用反馈；不改旧冻结接口。"""

from __future__ import annotations

import json
from contextlib import contextmanager
from hashlib import sha256
from unittest.mock import patch

import forge_build_rtorrent_generation_observation_probe as generation
import forge_build_rtorrent_shared_values as shared
from forge_build_rtorrent_common_v2 import factor_common_packet
from langchain_core.messages import SystemMessage

from deerflow.compile import unified_plan_equivalent_observed as observed
from deerflow.compile.plan_candidate_reception import propose_received, text_candidate
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.recovery_text_factors import FACTOR_META, FACTOR_TABLE, MARKER, map_strings
from deerflow.compile.shared_text_packet import referenced_packet, restore_packet


def literal_safe_factor_packet(packet):
    """原材料含字面~数字~时保留完整文本，只做原有整串共享去重。"""
    literals = []

    def validate(value):
        if isinstance(value, dict):
            if any(key in value for key in (FACTOR_META, FACTOR_TABLE)):
                raise PlanContractError("共同材料含保留因子字段")
            for child in value.values():
                validate(child)
        elif isinstance(value, list):
            for child in value:
                validate(child)

    validate(packet)
    map_strings(packet, lambda text: literals.append(text) if MARKER.search(text) else None)
    if not literals:
        return factor_common_packet(packet)
    # 不把错误参数当引用展开，也不删掉参数。没有因子元数据时~数字~为字面原文。
    result = referenced_packet(packet)
    if restore_packet(result) != packet:
        raise PlanContractError("字面引用反馈不能完整还原")
    return result


def candidate_feedback(self, request, handler):
    """被拒候选仍绑定本槽原响应；工具和文本呈现使用同一错误反馈。"""
    events = [json.loads(line) for line in (self.ledger.directory / "events.jsonl").read_text().splitlines()]
    episode = max((index for index, event in enumerate(events) if event["event"] == "agent.started"), default=-1)
    rejected = [(index, event) for index, event in enumerate(events) if index > episode and event["event"] == "observed.proposal_rejected"]
    candidate = None
    if rejected:
        index, event = rejected[-1]
        sequence = next(event["request_sequence"] for event in reversed(events[:index]) if event["event"] == "model.request_started")
        path = self.ledger.directory / f"response-{sequence}.json"
        raw = path.read_bytes()
        messages = [message for message in json.loads(raw) if message["type"] == "ai"]
        if len(messages) != 1:
            raise PlanContractError("被拒候选必须来自本槽唯一实际AI响应")
        calls = messages[0].get("tool_calls", [])
        if len(calls) == 1 and calls[0]["name"] == "ObservedBuildActions":
            arguments, presentation = calls[0]["args"], "tool_call"
        elif not calls:
            arguments, presentation = text_candidate(messages[0]["content"])
        else:
            raise PlanContractError("被拒候选来源不唯一或不是构建动作")
        candidate = dict(
            status="not_executed", request_sequence=sequence, response_file=path.name, response_sha256=sha256(raw).hexdigest(), presentation=presentation, arguments=arguments, error_category=event["category"], error_detail=event["detail"]
        )
    self.ledger.save(f"rejected-candidate-context-{self._request_sequence + 1}.json", candidate)
    original = self.packet
    self.packet = lambda: {**original(), "rejected_candidate": candidate}
    system = request.system_message
    if system is not None and not isinstance(system.content, str):
        raise PlanContractError("规划系统说明必须是文本")
    try:
        return generation.FeedbackMeter.wrap_model_call(self, request.override(system_message=SystemMessage(content=(system.content if system else "") + generation.CONTRACT_CLARIFICATION)), handler)
    finally:
        self.packet = original


@contextmanager
def common_harness_interfaces():
    original = observed.observed_planner

    def planner(source, **kwargs):
        return original(source, agent=propose_received, **kwargs)

    with (
        patch.object(shared, "factor_common_packet", literal_safe_factor_packet),
        patch.object(observed, "observed_planner", planner),
        patch.object(generation.PaidNativeMeter, "wrap_model_call", candidate_feedback),
    ):
        yield
