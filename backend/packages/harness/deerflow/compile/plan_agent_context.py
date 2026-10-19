"""独立开发修复：可恢复只读工具反馈与有界、带来源的证据工作集。"""

from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import asdict, replace
from pathlib import PurePosixPath

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from deerflow.compile.plan_agent import SYSTEM_PROMPT, PlanProposal, PlanResponseCapture, readonly_plan_tools
from deerflow.compile.plan_agent_canary import TOOL_PROMPT, CanaryMeter, StopWhenVerified
from deerflow.compile.plan_agent_repair import PATH_PROMPT
from deerflow.compile.plan_workflow import PlanContractError


def normalized_read_path(value: str, *, logs=False) -> str:
    """只为已授权的容器根提供别名；不扩展读取根或接受父目录穿越。"""
    path = PurePosixPath(value)
    if ".." in path.parts:
        raise PlanContractError("读取路径不能包含父目录跳转")
    if path.is_absolute():
        if logs:
            if path.parts[1:2] not in (("logs",), ("replay",)):
                raise PlanContractError("日志绝对路径仅允许/logs或/replay")
            value = path.as_posix().lstrip("/")
        else:
            try:
                value = path.relative_to("/workspace/repo").as_posix()
            except ValueError as exc:
                raise PlanContractError("源码绝对路径仅允许/workspace/repo内") from exc
    return value


def safe_readonly_tools(source_root, session_root):
    originals = {item.name: item for item in readonly_plan_tools(source_root, session_root)}

    def invoke(name, arguments):
        try:
            field = "directory" if name == "list_source" else "path"
            arguments[field] = normalized_read_path(arguments[field], logs=name == "read_failure_log")
            result = json.loads(originals[name].invoke(arguments))
            result["read_request"] = arguments
            return json.dumps(result, ensure_ascii=False)
        except (PlanContractError, OSError) as exc:
            # 拒绝无效操作但让Agent在下一次显式、计量的请求中纠正，不隐式重试工具。
            return json.dumps({"error": type(exc).__name__, "accepted": False, "reason": "路径越界、文件缺失或读取参数无效；先list_source核对规范路径", "read_request": arguments}, ensure_ascii=False)

    @tool
    def list_source(directory: str = ".") -> str:
        """列出源码目录的直接成员；支持相对路径或/workspace/repo内绝对路径；最多100项，错误返回反馈。"""
        return invoke("list_source", {"directory": directory})

    @tool
    def read_source(path: str, start_line: int = 1) -> str:
        """读取源码文本，支持相对路径或/workspace/repo内绝对路径；最多120行/8000字符，保留哈希与起始行。"""
        return invoke("read_source", {"path": path, "start_line": start_line})

    @tool
    def read_failure_log(path: str, start_line: int = 1) -> str:
        """读取Session内logs/或replay/日志；也接受/logs和/replay别名，不读取其他目录。"""
        return invoke("read_failure_log", {"path": path, "start_line": start_line})

    return [list_source, read_source, read_failure_log]


class EvidenceWorkingSet:
    """保存工具实际返回的片段，不调用模型总结；全文仍在独立原始日志。"""

    def __init__(self):
        self.entries = OrderedDict()
        self.index = []
        self.seeded = False

    def seed(self, rows):
        if self.seeded:
            return
        self.seeded = True
        for row in rows:
            self.entries[("read_source", row["path"], 1)] = row
        self.trim()

    def trim(self):
        while self.entries and len(json.dumps(list(self.entries.values()), ensure_ascii=False).encode()) > 24000:
            self.entries.popitem(last=False)
        while self.index and len(json.dumps(self.index, ensure_ascii=False).encode()) > 4000:
            self.index.pop(0)

    def observe(self, name, arguments, content):
        if name not in ("list_source", "read_source", "read_failure_log"):
            return
        row = json.loads(content)
        request = row.get("read_request", arguments)
        self.index.append({"tool": name, "request": request, "accepted": not bool(row.get("error")), "sha256": row.get("sha256")})
        if not row.get("error"):
            path = request.get("path", request.get("directory", "."))
            key = (name, path, request.get("start_line", 1))
            self.entries.pop(key, None)
            self.entries[key] = {"tool": name, **row}
        self.trim()


class ContextCanaryMeter(CanaryMeter):
    def __init__(self, *args, packet, **kwargs):
        self.working_set = EvidenceWorkingSet()

        def bounded_packet():
            current = packet()
            self.working_set.seed(current.get("source_packet", []))
            return {**current, "source_packet": list(self.working_set.entries.values()), "read_index": self.working_set.index}

        super().__init__(*args, packet=bounded_packet, **kwargs)
        self.tracker.limits = replace(self.tracker.limits, evaluator_timeout_seconds=300, replay_timeout_seconds=300)

    def wrap_model_call(self, request, handler):
        # 只淘汰可显式重读的证据片段，不截断任务、权威状态、方案或剩余预算。
        recent = [{"name": message.name, "content": str(message.content)[-3000:]} for message in request.messages if message.type == "tool"][-3:]
        while self.working_set.entries or not self.working_set.seeded:
            payload = {**self.packet(), "recent_tool_results": recent, "remaining_budget": asdict(self.tracker.remaining())}
            message = HumanMessage(content=json.dumps(payload, ensure_ascii=False))
            body = {"messages": [message.model_dump(mode="json")], "system_message": request.system_message.model_dump(mode="json") if request.system_message else None}
            if len(json.dumps(body, ensure_ascii=False).encode()) <= 49000 or not self.working_set.entries:
                break
            self.working_set.entries.popitem(last=False)
        return super().wrap_model_call(request, handler)

    def wrap_tool_call(self, request, handler):
        result = super().wrap_tool_call(request, handler)
        self.working_set.observe(request.tool_call["name"], request.tool_call["args"], result.content)
        return result


CONTEXT_PROMPT = (
    "\n源码读取使用相对路径或/workspace/repo内别名；Shell workdir仍为容器绝对路径。"
    "状态包source_packet保存有界的最近源码/日志/目录证据，read_index列出近期读取及哈希。"
    "先利用已给出的材料，不重复读取相同区间；被容量淘汰的材料可显式重读。"
    "工具拒绝会返回error，纠正调用而不是假定读取成功；不允许越界或改测试。准备完成后立即交付，避免不必要探索。"
)


def propose_with_context(*, model, task, source_root, session_root, meter, current_plan=None, handoff=None):
    revision = current_plan.revision + 1 if current_plan else 1
    meter.requires_structured_response = True
    meter.ledger.append("agent.started", revision=revision, recovery=current_plan is not None)
    agent = create_agent(model=model, tools=safe_readonly_tools(source_root, session_root), system_prompt=SYSTEM_PROMPT + PATH_PROMPT + CONTEXT_PROMPT, middleware=[meter], response_format=ToolStrategy(PlanProposal, handle_errors=False))
    result = agent.invoke({"messages": [HumanMessage(content="依据当前状态完成完整方案或修订，保留固定测试全部字段。")]}, config={"max_concurrency": 1, "recursion_limit": 100, "callbacks": [PlanResponseCapture(meter)]})
    proposal = result.get("structured_response")
    if not isinstance(proposal, PlanProposal):
        raise PlanContractError("未交付结构化方案")
    plan = task.materialize(proposal, revision=revision)
    meter.ledger.save(f"plan-{revision}.json", plan.model_dump(mode="json"))
    return plan, proposal.reason


def run_tool_agent_with_context(*, model, service, source_root, session_root, meter):
    agent = create_agent(model=model, tools=[*safe_readonly_tools(source_root, session_root), *service.tools()], system_prompt=TOOL_PROMPT + CONTEXT_PROMPT, middleware=[StopWhenVerified(lambda: service.verified), meter])
    return agent.invoke({"messages": [HumanMessage(content="根据当前状态完成构建任务。")]}, config={"max_concurrency": 1, "recursion_limit": 150, "callbacks": [PlanResponseCapture(meter)]})
