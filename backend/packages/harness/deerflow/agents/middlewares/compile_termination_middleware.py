"""Terminate successful compile tool flows without another model call."""

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from typing import NotRequired, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware, hook_config
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.types import Command


class CompileTerminationState(AgentState):
    compile_terminal: NotRequired[bool]
    todos: NotRequired[list | None]


_TERMINAL_STATUS_LABELS = {
    "completed": "已完成",
    "failed": "失败",
    "cancelled": "已取消",
    "timed_out": "超时",
}

_CHECK_STATUS_LABELS = {
    "passed": "通过",
    "failed": "失败",
    "not_run": "未运行",
}


def _inline_code(value: object) -> str:
    escaped = str(value).replace("`", "\\`")
    return f"`{escaped}`"


def _check_status(value: object) -> str:
    return _CHECK_STATUS_LABELS.get(str(value), str(value))


def _format_finalize_summary(payload: Mapping[str, object]) -> str:
    """Build a deterministic user-facing summary without another model call."""
    status = str(payload.get("status", "failed"))
    lines = [f"## 编译会话{_TERMINAL_STATUS_LABELS.get(status, status)}"]

    details = [
        ("会话", payload.get("session_id"), True),
        ("提交", payload.get("commit_sha"), True),
        ("镜像", payload.get("image"), True),
        (
            "构建系统",
            payload.get("executed_build_system") or payload.get("selected_build_system") or payload.get("build_system"),
            True,
        ),
        ("候选验证", _check_status(payload.get("verification", "not_run")), False),
        ("干净重放", _check_status(payload.get("replay_verification", "not_run")), False),
    ]
    lines.extend(f"- {label}：{_inline_code(value) if code else value}" for label, value, code in details if value not in {None, ""})

    stopped = payload.get("container_stopped") is True
    removed = payload.get("container_removed") is True
    if stopped or removed:
        cleanup_status = "已停止并删除" if stopped and removed else "已停止" if stopped else "已删除"
        lines.append(f"- 编译容器：{cleanup_status}")

    artifacts = payload.get("artifacts")
    if isinstance(artifacts, list) and artifacts:
        lines.extend(["", "### 构建产物"])
        for artifact in artifacts:
            if isinstance(artifact, Mapping):
                path = artifact.get("path")
                if not path:
                    continue
                metadata = [str(value) for key in ("artifact_type", "size_bytes") if (value := artifact.get(key))]
                suffix = f"（{', '.join(metadata)}）" if metadata else ""
                lines.append(f"- {_inline_code(path)}{suffix}")
            elif artifact:
                lines.append(f"- {_inline_code(artifact)}")

    error = payload.get("error")
    if error:
        lines.extend(["", "### 错误", *[f"> {line}" for line in str(error).splitlines()]])

    return "\n".join(lines)


def _completed_todos(request: ToolCallRequest, payload: Mapping[str, object]) -> list | None:
    if payload.get("status") != "completed":
        return None

    state = getattr(request, "state", None)
    if not isinstance(state, Mapping):
        return None
    todos = state.get("todos")
    if not isinstance(todos, list):
        return None

    changed = False
    updated: list = []
    for todo in todos:
        if isinstance(todo, Mapping):
            item = dict(todo)
            if item.get("status") == "in_progress":
                item["status"] = "completed"
                changed = True
            updated.append(item)
        else:
            updated.append(todo)
    return updated if changed else None


class CompileTerminationMiddleware(AgentMiddleware[CompileTerminationState]):
    """End compiler and lead graphs after their terminal compile tools succeed."""

    state_schema = CompileTerminationState

    def __init__(self, *, cleanup_run_on_end: bool = False):
        self.cleanup_run_on_end = cleanup_run_on_end

    @staticmethod
    def _run_identity(runtime: Runtime) -> tuple[str | None, str | None]:
        context = runtime.context or {}
        thread_id = context.get("thread_id")
        if thread_id is None:
            thread_id = runtime.config.get("configurable", {}).get("thread_id")
        run_id = context.get("run_id")
        if run_id is None:
            run_id = runtime.config.get("configurable", {}).get("run_id")
        if run_id is None:
            run_id = runtime.config.get("run_id")
        return thread_id, str(run_id) if run_id is not None else None

    @override
    def after_agent(self, state: CompileTerminationState, runtime: Runtime) -> dict | None:
        del state
        if not self.cleanup_run_on_end:
            return None
        thread_id, run_id = self._run_identity(runtime)
        if not thread_id or not run_id:
            return None
        from deerflow.compile.operations import finalize_unfinished_thread_sessions_impl

        finalize_unfinished_thread_sessions_impl(thread_id=thread_id, run_id=run_id)
        return None

    @override
    async def aafter_agent(self, state: CompileTerminationState, runtime: Runtime) -> dict | None:
        del state
        if not self.cleanup_run_on_end:
            return None
        thread_id, run_id = self._run_identity(runtime)
        if not thread_id or not run_id:
            return None
        from deerflow.compile.operations import finalize_unfinished_thread_sessions_impl

        await asyncio.to_thread(
            finalize_unfinished_thread_sessions_impl,
            thread_id=thread_id,
            run_id=run_id,
        )
        return None

    @hook_config(can_jump_to=["end"])
    @override
    def before_model(
        self,
        state: CompileTerminationState,
        runtime: Runtime,
    ) -> dict | None:
        del runtime
        if not state.get("compile_terminal"):
            return None
        return {"compile_terminal": False, "jump_to": "end"}

    @hook_config(can_jump_to=["end"])
    @override
    async def abefore_model(
        self,
        state: CompileTerminationState,
        runtime: Runtime,
    ) -> dict | None:
        return self.before_model(state, runtime)

    @staticmethod
    def _terminal_result(request: ToolCallRequest, result: ToolMessage | Command) -> ToolMessage | Command:
        if not isinstance(result, ToolMessage) or not isinstance(result.content, str):
            return result

        tool_name = request.tool_call.get("name")
        if tool_name not in {"submit_build_result", "finalize_session"}:
            return result

        try:
            payload = json.loads(result.content)
        except (TypeError, json.JSONDecodeError):
            return result

        if tool_name == "submit_build_result":
            if payload.get("status") != "passed":
                return result
            terminal_payload = {
                "build_status": "success",
                "proceed_to_verify": False,
                "verification_status": "passed",
                "summary": payload["message"],
                "artifacts": [artifact["path"] for artifact in payload.get("artifacts", [])],
            }
            terminal_content = json.dumps(terminal_payload, ensure_ascii=False, indent=2)
        else:
            if payload.get("status") not in {"completed", "failed", "cancelled", "timed_out"}:
                return result
            terminal_content = _format_finalize_summary(payload)

        update = {
            "messages": [result, AIMessage(content=terminal_content)],
            "compile_terminal": True,
        }
        if tool_name == "finalize_session" and (todos := _completed_todos(request, payload)) is not None:
            update["todos"] = todos
        return Command(update=update)

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        return self._terminal_result(request, handler(request))

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        return self._terminal_result(request, await handler(request))
