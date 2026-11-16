"""简洁规划的有界对话、读取进展与显式收敛；不调用额外摘要模型。"""

from __future__ import annotations

import hashlib
import json
import time
from copy import deepcopy
from dataclasses import asdict

from langchain_core.messages import HumanMessage

from deerflow.compile.plan_agent_context import normalized_read_path
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.request_context_budget import request_schemas


def bounded_text(value, limit):
    """按实际UTF-8字节保留首尾；明确标记省略，不产生模型摘要。"""
    data = value.encode()
    if len(data) <= limit:
        return value
    half = max(1, (limit - 80) // 2)
    return data[:half].decode(errors="ignore") + "\n[容量压缩：中间省略，完整原件已保留]\n" + data[-half:].decode(errors="ignore")


class PlanningContext:
    def __init__(self, packet, *, enforce_tool_availability=False, diagnostic_memory=None, dependency_diagnosis=None, include_planning_progress=True):
        self.packet = deepcopy(packet)
        self.diagnostic_memory = diagnostic_memory
        self.dependency_diagnosis = dependency_diagnosis
        self.enforce_tool_availability = enforce_tool_availability
        self.include_planning_progress = include_planning_progress
        self.available_tools = None
        self.seed_material = [dict(row) for row in packet.get("source_packet", [])]
        self.seed_compactions = 0
        self.reads = {}
        self.pending_reads = []
        self.stalled_rounds = 0
        self.pruned_groups = 0
        self.group_compactions = 0
        self.handoff_compactions = 0
        self.packet_compactions = 0

    def compact_group(self, group, meter):
        """完整移出AI及配对Tool后另起证据消息，不发送悬空调用或截断推理字段。"""
        raw = [m.model_dump(mode="json") for m in group]
        self.group_compactions += 1
        # 初始规划与各次恢复共用账本；请求序号避免新任务重置组号后撞名。
        path = f"context-request-{meter._request_sequence + 1}-group-{self.group_compactions}.json"
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

    def compact_packet(self, meter):
        """保存完整交接，仅缩短旧记录；当前失败命令、方案和任务保持完整。"""
        original = deepcopy(self.packet)
        path = f"context-request-{meter._request_sequence + 1}-packet.json"
        meter.ledger.save(path, original)
        handoff = self.packet.get("handoff") or {}
        records = handoff.get("recent_commands", [])
        for index, row in enumerate(records):
            last = index == len(records) - 1
            keys = {"command_id", "command", "workdir", "role", "exit_code", "timed_out", "termination", "log_path", "log_sha256", "output_tail"}
            trimmed = {k: v for k, v in row.items() if k in keys}
            for key in ("command", "output_tail"):
                if key in trimmed and not (last and key == "command"):
                    trimmed[key] = bounded_text(trimmed[key], 1800 if last else 500)
            records[index] = trimmed
        handoff["full_handoff_record"] = path
        handoff["context_note"] = "旧记录已压缩；当前方案和最后失败命令未截断。缺少诊断时使用read_failure_log按行补读原日志。"
        self.packet_compactions += 1

    def observe(self, name, arguments, content):
        if name == "diagnose_dependency":
            # 子查询已逐条写入诊断记录；这里只计算真实内容进展，不重复记账。
            row = json.loads(content)
            for evidence in row.get("evidence", []):
                self._observe_query(evidence["tool"], evidence["arguments"], evidence["result"])
            return
        if name in {"search_build_files", "inspect_build_environment"}:
            row = json.loads(content)
            if self.diagnostic_memory is not None:
                self.diagnostic_memory.observe(name, arguments, row, handoff_id=self.packet["handoff"]["handoff_id"])
            if self.dependency_diagnosis is not None:
                self.dependency_diagnosis.observe(name, arguments, row)
            self._observe_query(name, arguments, row)
            return
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

    def _observe_query(self, name, arguments, row):
        # 新命令ID/日志路径不是新知识，避免重复查询被误计为诊断进展。
        ignored = {"command_id", "log_path"}
        if self.dependency_diagnosis is not None:
            ignored |= {"files_scanned", "bytes_scanned"}
        evidence = {k: v for k, v in row.items() if k not in ignored}
        key = (name, json.dumps(arguments, sort_keys=True, ensure_ascii=False))
        digest = hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        self.pending_reads.append(self.reads.get(key, {}).get("result_sha256") != digest)
        self.reads[key] = dict(tool=name, query=arguments, result_sha256=digest)

    def request(self, meter, request, handler):
        budget = meter.context_budget
        budget.validate(meter)
        if self.pending_reads:
            self.stalled_rounds = 0 if any(self.pending_reads) else self.stalled_rounds + 1
            self.pending_reads.clear()
        finalize_only = self.stalled_rounds >= 3 and self.dependency_diagnosis is None
        schemas = request_schemas(request, finalize_only=finalize_only)
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
            if self.diagnostic_memory is not None:
                payload["recovery_diagnostic_memory"] = self.diagnostic_memory.snapshot(self.packet["handoff"])
            if self.dependency_diagnosis is not None:
                payload["dependency_diagnosis"] = self.dependency_diagnosis.snapshot()
            payload["planning_progress"] = dict(
                recent_reads=list(self.reads.values())[-12:],
                consecutive_rounds_without_new_evidence=self.stalled_rounds,
                earlier_assistant_notes=removed_notes,
                initial_material_compactions=self.seed_compactions,
                completed_group_compactions=self.group_compactions,
                handoff_log_compactions=self.handoff_compactions,
                handoff_packet_compactions=self.packet_compactions,
                instruction="构建入口、必要依赖和配置/编译命令有依据即可交付；未解决的问题交由真实执行反馈定位。",
            )
            if self.stalled_rounds >= 2:
                payload["planning_progress"]["instruction"] = "连续重复读取没有新增证据。请利用现有材料交付方案；确实无法规划时明确说明阻塞，不能编造依据。"
                if self.dependency_diagnosis is not None:
                    payload["planning_progress"]["instruction"] = "连续重复读取没有新增证据；请核实已有候选或转向尚未查询的组件包索引/路径。继续同范围须有新问题；证据足够即提交修订。"
            if not self.include_planning_progress:
                payload.pop("planning_progress")
            messages = [HumanMessage(content=json.dumps(payload, ensure_ascii=False)), *[m for g in groups for m in g]]
            body = dict(messages=[m.model_dump(mode="json") for m in messages], system_message=request.system_message.model_dump(mode="json") if request.system_message else None)
            context_usage = budget.measure(body, schemas)
            if context_usage["reserved_input_tokens"] <= budget.max_input_tokens:
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
            if not self.packet_compactions and self.packet.get("handoff"):
                self.compact_packet(meter)
                continue
            if not groups:
                raise PlanContractError("公开任务与必要规划材料超过上下文容量")
            # 按完整AI调用及其Tool结果淘汰，避免悬空tool_call_id；最新一组保留。
            if len(groups) == 1:
                if len(groups[0]) == 1 and groups[0][0].type == "human":
                    content = str(groups[0][0].content)
                    if len(content.encode()) <= 6500:
                        raise PlanContractError("公开任务与压缩后的必要证据超过规划上下文容量")
                    path = f"context-request-{meter._request_sequence + 1}-evidence.json"
                    meter.ledger.save(path, groups[0][0].model_dump(mode="json"))
                    groups[0] = [
                        HumanMessage(
                            content=json.dumps(
                                dict(context_compaction=True, original_record=path, note="先前证据片段已再次有界压缩；不是新的工具结果，缺失部分须按路径补读，不能据此推断成功。", preview=bounded_text(content, 5000)), ensure_ascii=False
                            )
                        )
                    ]
                    self.group_compactions += 1
                    continue
                groups[0] = self.compact_group(groups[0], meter)
                continue
            removed = groups.pop(0)
            removed_notes.extend(str(m.content)[:500] for m in removed if m.type == "ai" and m.content)
            removed_notes = removed_notes[-3:]
            self.pruned_groups += 1
        settings = dict(request.model_settings or {})
        settings.pop("parallel_tool_calls", None)
        output_limit = settings.get("max_tokens") or getattr(getattr(request, "model", None), "max_tokens", None) or budget.max_output_tokens
        settings["max_tokens"] = min(output_limit, budget.max_output_tokens)
        bounded = request.override(messages=messages, tools=[] if finalize_only else request.tools, model_settings=settings)
        # 与本次真实请求绑定；结构化输出也保留在集合内。恢复默认不启用此干预。
        self.available_tools = frozenset(s["function"]["name"] for s in schemas)
        meter.ledger.save(f"request-{meter._request_sequence + 1}.json", {**body, "tools": schemas})
        if self.diagnostic_memory is not None:
            meter.ledger.save(f"diagnostic-memory-request-{meter._request_sequence + 1}.json", payload["recovery_diagnostic_memory"])
        if self.dependency_diagnosis is not None:
            meter.ledger.save(f"dependency-diagnosis-request-{meter._request_sequence + 1}.json", payload["dependency_diagnosis"])
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
        meter.ledger.append("model.context_budget", **context_usage)
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
