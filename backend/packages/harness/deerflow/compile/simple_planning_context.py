"""简洁规划的有界对话、读取进展与显式收敛；不调用额外摘要模型。"""

from __future__ import annotations

import hashlib
import json
import time
from copy import deepcopy
from dataclasses import asdict

from langchain.agents.structured_output import OutputToolBinding, ToolStrategy
from langchain_core.messages import HumanMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from deerflow.compile.plan_agent_context import normalized_read_path
from deerflow.compile.plan_workflow import PlanContractError


def bounded_text(value, limit):
    """按实际UTF-8字节保留首尾；明确标记省略，不产生模型摘要。"""
    data = value.encode()
    if len(data) <= limit:
        return value
    half = max(1, (limit - 80) // 2)
    return data[:half].decode(errors="ignore") + "\n[容量压缩：中间省略，完整原件已保留]\n" + data[-half:].decode(errors="ignore")


class PlanningContext:
    def __init__(self, packet):
        self.packet = deepcopy(packet)
        self.seed_material = [dict(row) for row in packet.get("source_packet", [])]
        self.seed_compactions = 0
        self.reads = {}
        self.pending_reads = []
        self.stalled_rounds = 0
        self.pruned_groups = 0
        self.group_compactions = 0
        self.handoff_compactions = 0

    def compact_group(self, group, meter):
        """完整移出AI及配对Tool后另起证据消息，不发送悬空调用或截断推理字段。"""
        raw = [m.model_dump(mode="json") for m in group]
        self.group_compactions += 1
        path = f"context-group-{self.group_compactions}.json"
        meter.ledger.save(path, raw)
        evidence = []
        calls = []
        notes = []
        for message in group:
            if message.type == "ai":
                calls.extend(message.tool_calls)
                if message.content:
                    notes.append(bounded_text(str(message.content), 600))
            elif message.type == "tool":
                content = str(message.content)
                try:
                    row = json.loads(content)
                except ValueError:
                    row = {"preview": content}
                if isinstance(row, dict):
                    row = {k: bounded_text(v, 1600) if isinstance(v, str) else v for k, v in row.items()}
                if len(json.dumps(row, ensure_ascii=False).encode()) > 4000:
                    row = dict(preview=bounded_text(content, 2000), read_request=row.get("read_request") if isinstance(row, dict) else None)
                evidence.append(dict(tool=message.name, result=row, original_bytes=len(content.encode()), original_sha256=hashlib.sha256(content.encode()).hexdigest()))
        payload = dict(
            context_compaction=True,
            note="上一组AI及其工具结果已完整移出；以下为实际返回的有界片段，不是新工具执行或新的成功结论。必要时按read_request补读源码/日志。原推理与结果保存在独立原件中。",
            original_record=path,
            original_sha256=hashlib.sha256(json.dumps(raw, ensure_ascii=False).encode()).hexdigest(),
            calls=calls,
            assistant_notes=notes,
            evidence=evidence,
        )
        meter.ledger.append("planning.group_compacted", record=path, original_messages=len(group), original_sha256=payload["original_sha256"])
        return [HumanMessage(content=json.dumps(payload, ensure_ascii=False))]

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
            payload = {**self.packet, "source_packet": self.seed_material, "remaining_budget": asdict(meter.tracker.remaining())}
            payload["planning_progress"] = dict(
                recent_reads=list(self.reads.values())[-12:],
                consecutive_rounds_without_new_evidence=self.stalled_rounds,
                earlier_assistant_notes=removed_notes,
                initial_material_compactions=self.seed_compactions,
                completed_group_compactions=self.group_compactions,
                handoff_log_compactions=self.handoff_compactions,
                instruction="构建入口、必要依赖和配置/编译命令有依据即可交付；未解决的问题交由真实执行反馈定位。",
            )
            if self.stalled_rounds >= 2:
                payload["planning_progress"]["instruction"] = "连续重复读取没有新增证据。请利用现有材料交付方案；确实无法规划时明确说明阻塞，不能编造依据。"
            messages = [HumanMessage(content=json.dumps(payload, ensure_ascii=False)), *[m for g in groups for m in g]]
            body = dict(messages=[m.model_dump(mode="json") for m in messages], system_message=request.system_message.model_dump(mode="json") if request.system_message else None)
            if len(json.dumps(body, ensure_ascii=False).encode()) <= 49000:
                break
            # 初始片段可由原读取工具重新获得；优先保留最新完整交互，避免
            # 初始包与同一文件的新读取重复占用容量，挤掉唯一一次工具反馈。
            initial = [row for row in self.seed_material if row.get("content")]
            if initial:
                largest = max(initial, key=lambda row: len(row["content"].encode()))
                largest.update(content="", truncated=True, context_note="初始片段因容量移出；路径与哈希保留，必要时用read_source补读具体片段")
                self.seed_compactions += 1
                continue
            if not self.handoff_compactions and self.packet.get("handoff"):
                for row in self.packet["handoff"].get("recent_commands", []):
                    if row.get("output_tail"):
                        row["output_tail_original_bytes"] = len(row["output_tail"].encode())
                        row["output_tail"] = bounded_text(row["output_tail"], 1000)
                self.handoff_compactions += 1
                continue
            if not groups:
                raise PlanContractError("公开任务与必要规划材料超过上下文容量")
            # 按完整AI调用及其Tool结果淘汰，避免悬空tool_call_id；最新一组保留。
            if len(groups) == 1:
                if len(groups[0]) == 1 and groups[0][0].type == "human":
                    raise PlanContractError("公开任务与压缩后的必要证据超过规划上下文容量")
                groups[0] = self.compact_group(groups[0], meter)
                continue
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
        meter.ledger.append(
            "planning.context",
            history_messages=len(messages) - 1,
            pruned_groups=self.pruned_groups,
            initial_material_compactions=self.seed_compactions,
            completed_group_compactions=self.group_compactions,
            handoff_log_compactions=self.handoff_compactions,
            stalled_rounds=self.stalled_rounds,
            finalize_only=finalize_only,
        )
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
