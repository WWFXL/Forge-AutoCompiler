"""简洁规划的有界对话、读取进展与显式收敛；不调用额外摘要模型。"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict

from langchain.agents.structured_output import OutputToolBinding, ToolStrategy
from langchain_core.messages import HumanMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from deerflow.compile.plan_agent_context import normalized_read_path
from deerflow.compile.plan_workflow import PlanContractError


class PlanningContext:
    def __init__(self, packet):
        self.packet = packet
        self.reads = {}
        self.pending_reads = []
        self.stalled_rounds = 0
        self.pruned_groups = 0

    def observe(self, name, arguments, content):
        if name not in {"read_source", "list_source", "read_failure_log"}:
            return
        row = json.loads(content)
        args = row.get("read_request", arguments)
        path = args.get("path", args.get("directory", "."))
        try:
            canonical_path = normalized_read_path(path, logs=name == "read_failure_log")
        except PlanContractError:
            canonical_path = path  # 读取工具已拒绝；错误仍应反馈Agent，而不是打断纠正。
        key = (name, canonical_path, args.get("start_line", 1))
        evidence = {k: v for k, v in row.items() if k != "read_request"}
        digest = hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        novel = self.reads.get(key, {}).get("result_sha256") != digest
        self.reads[key] = dict(tool=name, path=key[1], start_line=key[2], accepted=not bool(row.get("error")), result_sha256=digest)
        self.pending_reads.append(novel)

    def request(self, meter, request, handler):
        if self.pending_reads:
            self.stalled_rounds = 0 if any(self.pending_reads) else self.stalled_rounds + 1
            self.pending_reads.clear()
        # 首条消息是公开任务；之后保留真实AI/Tool对话，包含结构纠错反馈。
        history = list(request.messages[1:])
        groups = []
        for message in history:
            if message.type != "tool" or not groups:
                groups.append([])
            groups[-1].append(message)
        removed_notes = []
        self.pruned_groups = 0
        while True:
            payload = {**self.packet, "remaining_budget": asdict(meter.tracker.remaining())}
            payload["planning_progress"] = dict(
                recent_reads=list(self.reads.values())[-12:],
                consecutive_rounds_without_new_evidence=self.stalled_rounds,
                earlier_assistant_notes=removed_notes,
                instruction="构建入口、必要依赖和配置/编译命令有依据即可交付；未解决的问题交由真实执行反馈定位。",
            )
            if self.stalled_rounds >= 2:
                payload["planning_progress"]["instruction"] = "连续重复读取没有新增证据。请利用现有材料交付方案；确实无法规划时明确说明阻塞，不能编造依据。"
            messages = [HumanMessage(content=json.dumps(payload, ensure_ascii=False)), *[m for g in groups for m in g]]
            body = dict(messages=[m.model_dump(mode="json") for m in messages], system_message=request.system_message.model_dump(mode="json") if request.system_message else None)
            if len(json.dumps(body, ensure_ascii=False).encode()) <= 49000:
                break
            if not groups:
                raise PlanContractError("公开任务与必要规划材料超过上下文容量")
            # 按完整AI调用及其Tool结果淘汰，避免悬空tool_call_id；最新一组保留。
            if len(groups) == 1:
                raise PlanContractError("最近完整工具交互超过规划上下文容量")
            removed = groups.pop(0)
            removed_notes.extend(str(m.content)[:500] for m in removed if m.type == "ai" and m.content)
            removed_notes = removed_notes[-3:]
            self.pruned_groups += 1
        finalize_only = self.stalled_rounds >= 3
        settings = dict(request.model_settings or {})
        settings.pop("parallel_tool_calls", None)
        bounded = request.override(messages=messages, tools=[] if finalize_only else request.tools, model_settings=settings)
        schemas = [convert_to_openai_tool(t) for t in bounded.tools or []]
        if isinstance(bounded.response_format, ToolStrategy):
            schemas.extend(convert_to_openai_tool(OutputToolBinding.from_schema_spec(s).tool) for s in bounded.response_format.schema_specs)
        if len(json.dumps(schemas, ensure_ascii=False).encode()) > 8000:
            raise PlanContractError("规划工具schema超过容量")
        meter.ledger.save(f"request-{meter._request_sequence + 1}.json", {**body, "tools": schemas})
        meter.ledger.append("planning.context", history_messages=len(messages) - 1, pruned_groups=self.pruned_groups, stalled_rounds=self.stalled_rounds, finalize_only=finalize_only)
        meter.tracker.observe_elapsed(time.monotonic() - meter.started_monotonic)
        sequence = meter._before_request()
        try:
            response = handler(bounded)
            meter._after_request(response, sequence)
            return response
        except Exception as exc:
            if sequence not in meter.known_usage_requests:
                meter.unknown_usage_requests.add(sequence)
            meter.ledger.append("model.request_failed", request_sequence=sequence, error_class=type(exc).__name__, status_code=getattr(exc, "status_code", None))
            raise
