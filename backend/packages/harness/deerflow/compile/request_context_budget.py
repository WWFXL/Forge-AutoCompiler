"""当前简洁构建入口的请求容量；本地估算不替代Provider实际usage。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from math import ceil

import tiktoken
from langchain.agents.structured_output import OutputToolBinding, ToolStrategy
from langchain_core.utils.function_calling import convert_to_openai_tool

from deerflow.compile.plan_workflow import PlanContractError


@lru_cache(maxsize=1)
def _encoding():
    return tiktoken.get_encoding("cl100k_base")


def request_schemas(request, *, finalize_only=False):
    tools = [] if finalize_only else list(request.tools or [])
    schemas = [convert_to_openai_tool(t) for t in tools]
    if isinstance(request.response_format, ToolStrategy):
        schemas.extend(convert_to_openai_tool(OutputToolBinding.from_schema_spec(s).tool) for s in request.response_format.schema_specs)
    return schemas


@dataclass(frozen=True)
class RequestContextBudget:
    """64K工作输入含估算余量；不宣称cl100k就是DeepSeek分词器。"""

    max_input_tokens: int = 64000
    max_output_tokens: int = 32768
    model_context_tokens: int = 1000000

    def measure(self, body, schemas):
        raw = json.dumps({**body, "tools": schemas}, ensure_ascii=False)
        estimated = len(_encoding().encode(raw, disallowed_special=()))
        return dict(
            version="build-request-context-v1",
            estimation="cl100k_base×1.25＋2048协议余量；非DeepSeek精确分词",
            serialized_bytes=len(raw.encode()),
            tokenizer_tokens=estimated,
            reserved_input_tokens=ceil(estimated * 1.25) + 2048,
            max_input_tokens=self.max_input_tokens,
            max_output_tokens=self.max_output_tokens,
            model_context_tokens=self.model_context_tokens,
        )

    def validate(self, meter):
        if min(self.max_input_tokens, self.max_output_tokens, self.model_context_tokens) <= 0:
            raise PlanContractError("上下文预算必须为正")
        ceiling = meter.tracker.limits.max_recorded_tokens_per_response
        total = self.max_input_tokens + self.max_output_tokens
        if total > self.model_context_tokens or (ceiling is not None and total > ceiling):
            raise PlanContractError("输入与输出预留超过模型上下文或单次用量上限")
