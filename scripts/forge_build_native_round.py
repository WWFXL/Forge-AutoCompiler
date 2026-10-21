"""独立共同接口：权威状态加最近完整原生工具轮次，原执行与验收保持。"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, replace
from decimal import Decimal

from forge_build_rtorrent_fixed_contract import (
    ContractMeter,
    run_strategy as contract_run_strategy,
)
from langchain.agents.structured_output import OutputToolBinding, ToolStrategy
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from deerflow.compile.plan_workflow import PlanContractError

MESSAGE_BYTES = 100000
NATIVE_PROMPT = (
    "\n当前Human状态包是权威状态；其后AI/Tool消息是紧邻的上一完整工具轮次，保留原分析与结果以继续工作。"
    "历史工具结果不能覆盖当前状态、预算或固定测试；不需要反复读取仍已可用的相同证据。"
)


def last_complete_round(messages):
    """按ID保留完整轮次；不截断思考、工具文本或配对。"""
    positions = [i for i, message in enumerate(messages) if message.type == "ai"]
    if not positions:
        if any(message.type == "tool" for message in messages):
            raise PlanContractError("原生工具返回缺少AI调用")
        return []
    result = list(messages[positions[-1] :])
    ai = result[0]
    identifiers = [call["id"] for call in ai.tool_calls]
    tools = [message for message in result[1:] if message.type == "tool"]
    returned = [message.tool_call_id for message in tools]
    if (
        not identifiers
        or len(identifiers) != len(set(identifiers))
        or len(returned) != len(set(returned))
        or sorted(identifiers) != sorted(returned)
        or any(message.type not in ("tool", "human") for message in result[1:])
    ):
        raise PlanContractError("原生上一轮工具配对不完整或含糊")
    return result


class NativeRoundMeter(ContractMeter):
    """新版本共同材料资源；不修改旧Meter或放宽构建裁判。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tracker.limits = replace(
            self.tracker.limits, max_recorded_tokens_per_response=200000
        )
        self.ledger.append(
            "native_context.policy",
            messages_bytes=MESSAGE_BYTES,
            schema_bytes=8000,
            complete_rounds=1,
            next_response_reservation_usd="0.80",
            original_task_and_evaluator_unchanged=True,
        )

    def _before_request(self):
        if Decimal(str(self.cost_usd)) + Decimal("0.80") > Decimal("1.50"):
            raise PlanContractError("单臂费用不足以覆盖新原生接口下一完整请求")
        # 原3900秒预留、全部Token/步骤、模型身份与单臂费用仍由祖先检查。
        return super()._before_request()

    def wrap_model_call(self, request, handler):
        self.tracker.observe_elapsed(time.monotonic() - self.started_monotonic)
        history = last_complete_round(request.messages)
        payload = {
            **self.packet(),
            "remaining_budget": asdict(self.tracker.remaining()),
        }
        messages = [
            HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
            *history,
        ]
        system = request.system_message
        if system is not None and not isinstance(system.content, str):
            raise PlanContractError("原生接口system必须为文本")
        system = SystemMessage(
            content=(system.content if system else "") + NATIVE_PROMPT
        )
        bounded = request.override(messages=messages, system_message=system)
        material = dict(
            messages=[m.model_dump(mode="json") for m in messages],
            system_message=system.model_dump(mode="json"),
        )
        if len(json.dumps(material, ensure_ascii=False).encode()) > MESSAGE_BYTES:
            raise PlanContractError(
                "原生状态及完整上一轮超过100000字节，不调用Provider"
            )
        tools = list(bounded.tools or [])
        if isinstance(bounded.response_format, ToolStrategy):
            tools.extend(
                OutputToolBinding.from_schema_spec(spec).tool
                for spec in bounded.response_format.schema_specs
            )
        schemas = [convert_to_openai_tool(item) for item in tools]
        if len(json.dumps(schemas, ensure_ascii=False, default=str).encode()) > 8000:
            raise PlanContractError("原生接口工具schema超过8000字节，不调用Provider")
        self.ledger.save(
            f"request-{self._request_sequence + 1}.json", {**material, "tools": schemas}
        )
        sequence = self._before_request()
        settings = dict(bounded.model_settings or {})
        settings.pop("parallel_tool_calls", None)
        try:
            response = handler(bounded.override(model_settings=settings))
            self._after_request(response, sequence)
            return response
        except Exception as exc:
            if sequence not in self.known_usage_requests:
                self.unknown_usage_requests.add(sequence)
            self.ledger.append(
                "model.request_failed",
                request_sequence=sequence,
                error_class=type(exc).__name__,
                status_code=getattr(exc, "status_code", None),
            )
            raise


def run_strategy(*, meter_factory=NativeRoundMeter, **kwargs):
    """三策略同一装配/执行/恢复入口，仅共同替换材料与响应资源。"""
    return contract_run_strategy(meter_factory=meter_factory, **kwargs)
