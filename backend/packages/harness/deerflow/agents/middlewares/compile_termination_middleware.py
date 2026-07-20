"""Terminate successful compile tool flows without another model call."""

import json
from collections.abc import Awaitable, Callable
from typing import NotRequired, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware, hook_config
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.types import Command


class CompileTerminationState(AgentState):
    compile_terminal: NotRequired[bool]


class CompileTerminationMiddleware(AgentMiddleware[CompileTerminationState]):
    """End compiler and lead graphs after their terminal compile tools succeed."""

    state_schema = CompileTerminationState

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
        else:
            if payload.get("status") not in {"completed", "failed", "cancelled", "timed_out"}:
                return result
            terminal_payload = payload

        return Command(
            update={
                "messages": [
                    result,
                    AIMessage(content=json.dumps(terminal_payload, ensure_ascii=False, indent=2)),
                ],
                "compile_terminal": True,
            }
        )

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
