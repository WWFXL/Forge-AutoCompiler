"""独立接线修复：thinking 模式使用 auto tool choice，并明确失败请求的未知用量。"""

from __future__ import annotations

from deerflow.compile.plan_agent import PlanAgentMeter
from deerflow.models.patched_deepseek import PatchedChatDeepSeek


class PlanThinkingDeepSeek(PatchedChatDeepSeek):
    """保留结构化方案解析；不向 thinking Provider 发送强制工具选择。"""

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return super().bind_tools(tools, tool_choice="auto" if tool_choice in ("any", "required") else tool_choice, **kwargs)


class PlanAgentMeterV2(PlanAgentMeter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.unknown_usage_requests: set[int] = set()
        self.known_usage_requests: set[int] = set()

    def capture_response(self, response, request_sequence):
        try:
            return super().capture_response(response, request_sequence)
        finally:
            try:
                self._response_usage(response)
            except Exception:
                self.unknown_usage_requests.add(request_sequence)
            else:
                self.known_usage_requests.add(request_sequence)

    def wrap_model_call(self, request, handler):
        before = self._request_sequence
        try:
            return super().wrap_model_call(request, handler)
        except Exception as exc:
            sequence = self._request_sequence
            if sequence > before and sequence not in self.known_usage_requests:
                self.unknown_usage_requests.add(sequence)
            body = getattr(exc, "body", None)
            error = body.get("error", body) if isinstance(body, dict) else {}
            if not isinstance(error, dict):
                error = {}
            # 只保存错误体的诊断字段，不保存请求头、凭据或客户端对象。
            self.ledger.append(
                "model.failure_detail",
                request_sequence=sequence,
                error_class=type(exc).__name__,
                status_code=getattr(exc, "status_code", None),
                error={key: error[key] for key in ("message", "type", "code", "param") if key in error},
            )
            raise

    def summary(self):
        result = super().summary()
        result.update(unknown_usage_requests=len(self.unknown_usage_requests), cost_and_usage_complete=not self.unknown_usage_requests, estimated_cost_usd_completed_responses=result["estimated_cost_usd"])
        if self.unknown_usage_requests:
            result["estimated_cost_usd"] = None
        return result
