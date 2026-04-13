"""Subagent execution engine."""

import asyncio
import logging
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from langchain.agents import create_agent
from langchain.tools import BaseTool
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from deerflow.agents.thread_state import SandboxState, ThreadDataState, ThreadState
from deerflow.models import create_chat_model
from deerflow.subagents.config import SubagentConfig

logger = logging.getLogger(__name__)

MAX_CONCURRENT_SUBAGENTS = 3


class SubagentStatus(Enum):
    """Status of a subagent execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass
class SubagentResult:
    """Result of a subagent execution."""

    task_id: str
    trace_id: str
    status: SubagentStatus
    result: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    ai_messages: list[dict[str, Any]] | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)

    def __post_init__(self):
        if self.ai_messages is None:
            self.ai_messages = []


_background_tasks: dict[str, SubagentResult] = {}
_background_tasks_lock = threading.Lock()
_scheduler_pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_SUBAGENTS, thread_name_prefix="subagent-scheduler-")
_execution_pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_SUBAGENTS, thread_name_prefix="subagent-exec-")
_isolated_loop_pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_SUBAGENTS, thread_name_prefix="subagent-isolated-")


def _extract_text_content(content: Any) -> str:
    """Extract readable text from model content payloads."""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts: list[str] = []
        pending_str_parts: list[str] = []

        for block in content:
            if isinstance(block, str):
                pending_str_parts.append(block)
                continue

            if pending_str_parts:
                text_parts.append("".join(pending_str_parts))
                pending_str_parts.clear()

            if isinstance(block, dict):
                text_val = block.get("text")
                if isinstance(text_val, str) and text_val:
                    text_parts.append(text_val)

        if pending_str_parts:
            text_parts.append("".join(pending_str_parts))

        return "\n".join(part for part in text_parts if part).strip() or "No text content in response"

    return str(content)


def _filter_tools(
    all_tools: list[BaseTool],
    allowed: list[str] | None,
    disallowed: list[str] | None,
) -> list[BaseTool]:
    filtered = all_tools
    if allowed is not None:
        allowed_set = set(allowed)
        filtered = [t for t in filtered if t.name in allowed_set]
    if disallowed is not None:
        disallowed_set = set(disallowed)
        filtered = [t for t in filtered if t.name not in disallowed_set]
    return filtered


def _get_model_name(config: SubagentConfig, parent_model: str | None) -> str | None:
    if config.model == "inherit":
        return parent_model
    return config.model


class SubagentExecutor:
    """Executor for running subagents."""

    def __init__(
        self,
        config: SubagentConfig,
        tools: list[BaseTool],
        parent_model: str | None = None,
        sandbox_state: SandboxState | None = None,
        thread_data: ThreadDataState | None = None,
        thread_id: str | None = None,
        trace_id: str | None = None,
    ):
        self.config = config
        self.parent_model = parent_model
        self.sandbox_state = sandbox_state
        self.thread_data = thread_data
        self.thread_id = thread_id
        self.trace_id = trace_id or str(uuid.uuid4())[:8]
        self.tools = _filter_tools(tools, config.tools, config.disallowed_tools)

        logger.info(
            "[trace=%s] SubagentExecutor initialized: %s with %s tools",
            self.trace_id,
            config.name,
            len(self.tools),
        )

    def _create_agent(self):
        model_name = _get_model_name(self.config, self.parent_model)
        model = create_chat_model(name=model_name, thinking_enabled=False)

        from deerflow.agents.middlewares.tool_error_handling_middleware import (
            build_subagent_runtime_middlewares,
        )

        middlewares = build_subagent_runtime_middlewares(lazy_init=True)

        return create_agent(
            model=model,
            tools=self.tools,
            middleware=middlewares,
            system_prompt=self.config.system_prompt,
            state_schema=ThreadState,
        )

    def _build_initial_state(self, task: str) -> dict[str, Any]:
        state: dict[str, Any] = {
            "messages": [HumanMessage(content=task)],
        }
        if self.sandbox_state is not None:
            state["sandbox"] = self.sandbox_state
        if self.thread_data is not None:
            state["thread_data"] = self.thread_data
        return state

    async def _aexecute(
        self,
        task: str,
        result_holder: SubagentResult | None = None,
    ) -> SubagentResult:
        if result_holder is not None:
            result = result_holder
        else:
            result = SubagentResult(
                task_id=str(uuid.uuid4())[:8],
                trace_id=self.trace_id,
                status=SubagentStatus.RUNNING,
                started_at=datetime.now(),
            )

        try:
            agent = self._create_agent()
            state = self._build_initial_state(task)

            run_config: RunnableConfig = {
                "recursion_limit": self.config.max_turns,
            }
            context: dict[str, Any] = {}
            if self.thread_id:
                run_config["configurable"] = {"thread_id": self.thread_id}
                context["thread_id"] = self.thread_id

            final_state = None

            if result.cancel_event.is_set():
                result.status = SubagentStatus.CANCELLED
                result.error = "Cancelled by user"
                result.completed_at = datetime.now()
                return result

            async for chunk in agent.astream(
                state,
                config=run_config,
                context=context,
                stream_mode="values",
            ):
                if result.cancel_event.is_set():
                    result.status = SubagentStatus.CANCELLED
                    result.error = "Cancelled by user"
                    result.completed_at = datetime.now()
                    return result

                final_state = chunk
                messages = chunk.get("messages", [])
                if messages:
                    last_message = messages[-1]
                    if isinstance(last_message, AIMessage):
                        message_dict = last_message.model_dump()
                        message_id = message_dict.get("id")
                        is_duplicate = False
                        if message_id:
                            is_duplicate = any(msg.get("id") == message_id for msg in result.ai_messages)
                        else:
                            is_duplicate = message_dict in result.ai_messages
                        if not is_duplicate:
                            result.ai_messages.append(message_dict)

            if final_state is None:
                result.result = "No response generated"
            else:
                messages = final_state.get("messages", [])
                last_ai_message = None
                for msg in reversed(messages):
                    if isinstance(msg, AIMessage):
                        last_ai_message = msg
                        break

                if last_ai_message is not None:
                    result.result = _extract_text_content(last_ai_message.content)
                elif messages:
                    last_message = messages[-1]
                    raw_content = last_message.content if hasattr(last_message, "content") else str(last_message)
                    result.result = _extract_text_content(raw_content)
                else:
                    result.result = "No response generated"

            result.status = SubagentStatus.COMPLETED
            result.completed_at = datetime.now()
        except Exception as e:
            logger.exception("[trace=%s] Subagent %s async execution failed", self.trace_id, self.config.name)
            result.status = SubagentStatus.FAILED
            result.error = str(e)
            result.completed_at = datetime.now()

        return result

    def _execute_in_isolated_loop(
        self,
        task: str,
        result_holder: SubagentResult | None = None,
    ) -> SubagentResult:
        try:
            previous_loop = asyncio.get_event_loop()
        except RuntimeError:
            previous_loop = None

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self._aexecute(task, result_holder))
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                if pending:
                    for task_obj in pending:
                        task_obj.cancel()
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.run_until_complete(loop.shutdown_default_executor())
            except Exception:
                logger.debug(
                    "[trace=%s] Failed cleaning isolated loop for subagent %s",
                    self.trace_id,
                    self.config.name,
                    exc_info=True,
                )
            finally:
                try:
                    loop.close()
                finally:
                    asyncio.set_event_loop(previous_loop)

    def execute(
        self,
        task: str,
        result_holder: SubagentResult | None = None,
    ) -> SubagentResult:
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                future = _isolated_loop_pool.submit(
                    self._execute_in_isolated_loop,
                    task,
                    result_holder,
                )
                return future.result()

            return asyncio.run(self._aexecute(task, result_holder))
        except Exception as e:
            logger.exception("[trace=%s] Subagent %s execution failed", self.trace_id, self.config.name)
            result = result_holder or SubagentResult(
                task_id=str(uuid.uuid4())[:8],
                trace_id=self.trace_id,
                status=SubagentStatus.FAILED,
            )
            result.status = SubagentStatus.FAILED
            result.error = str(e)
            result.completed_at = datetime.now()
            return result

    def execute_async(self, task: str, task_id: str | None = None) -> str:
        if task_id is None:
            task_id = str(uuid.uuid4())[:8]

        result = SubagentResult(
            task_id=task_id,
            trace_id=self.trace_id,
            status=SubagentStatus.PENDING,
        )

        with _background_tasks_lock:
            _background_tasks[task_id] = result

        def run_with_timeout() -> None:
            try:
                result.status = SubagentStatus.RUNNING
                result.started_at = datetime.now()
                future: Future = _execution_pool.submit(self.execute, task, result)
                try:
                    future.result(timeout=self.config.timeout_seconds)
                except FuturesTimeoutError:
                    result.status = SubagentStatus.TIMED_OUT
                    result.error = f"Task timed out after {self.config.timeout_seconds} seconds"
                    result.completed_at = datetime.now()
                except Exception as e:
                    logger.exception(
                        "[trace=%s] Subagent %s background execution failed",
                        self.trace_id,
                        self.config.name,
                    )
                    result.status = SubagentStatus.FAILED
                    result.error = str(e)
                    result.completed_at = datetime.now()
            except Exception as e:
                logger.exception(
                    "[trace=%s] Scheduler failed for subagent %s",
                    self.trace_id,
                    self.config.name,
                )
                result.status = SubagentStatus.FAILED
                result.error = str(e)
                result.completed_at = datetime.now()

        _scheduler_pool.submit(run_with_timeout)
        return task_id


def get_background_task_result(task_id: str) -> SubagentResult | None:
    with _background_tasks_lock:
        return _background_tasks.get(task_id)


def cleanup_background_task(task_id: str) -> None:
    with _background_tasks_lock:
        _background_tasks.pop(task_id, None)


def request_cancel_background_task(task_id: str) -> bool:
    with _background_tasks_lock:
        result = _background_tasks.get(task_id)
        if result is None:
            return False
        result.cancel_event.set()
        return True
