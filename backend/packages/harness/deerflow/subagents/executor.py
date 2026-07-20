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
from typing import TYPE_CHECKING, Any

from langchain.agents import create_agent
from langchain.tools import BaseTool
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from deerflow.models import create_chat_model
from deerflow.subagents.config import SubagentConfig

if TYPE_CHECKING:
    from deerflow.agents.thread_state import SandboxState, ThreadDataState
else:
    SandboxState = ThreadDataState = Any

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
    worker_done_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _status_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _handle_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _loop: asyncio.AbstractEventLoop | None = field(default=None, repr=False)
    _asyncio_task: asyncio.Task[Any] | None = field(default=None, repr=False)

    def __post_init__(self):
        if self.ai_messages is None:
            self.ai_messages = []


_background_tasks: dict[str, SubagentResult] = {}
_background_tasks_lock = threading.Lock()
_scheduler_pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_SUBAGENTS, thread_name_prefix="subagent-scheduler-")
_execution_pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_SUBAGENTS, thread_name_prefix="subagent-exec-")
_isolated_loop_pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_SUBAGENTS, thread_name_prefix="subagent-isolated-")
_TERMINAL_STATUSES = {
    SubagentStatus.COMPLETED,
    SubagentStatus.FAILED,
    SubagentStatus.CANCELLED,
    SubagentStatus.TIMED_OUT,
}


def _mark_terminal(result: SubagentResult, status: SubagentStatus, error: str | None = None) -> bool:
    with result._status_lock:
        if result.status in _TERMINAL_STATUSES:
            return False
        result.status = status
        result.error = error
        result.completed_at = datetime.now()
        return True


def _mark_execution_complete(result: SubagentResult) -> None:
    with result._status_lock:
        if result.status in _TERMINAL_STATUSES:
            return
        if result.cancel_event.is_set():
            result.status = SubagentStatus.CANCELLED
            result.error = result.error or "Cancelled by user"
        else:
            result.status = SubagentStatus.COMPLETED
        result.completed_at = datetime.now()


def _cancel_running_coroutine(result: SubagentResult, *, force: bool = False) -> bool:
    with result._status_lock:
        if result.status in _TERMINAL_STATUSES and not force:
            return False
        result.cancel_event.set()
    with result._handle_lock:
        loop = result._loop
        task = result._asyncio_task
    if loop is None or task is None or task.done():
        return True
    try:
        loop.call_soon_threadsafe(task.cancel)
    except RuntimeError:
        # The isolated event loop may have completed between the snapshot and call.
        pass
    return True


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
        initial_state: dict[str, Any] | None = None,
    ):
        self.config = config
        self.parent_model = parent_model
        self.sandbox_state = sandbox_state
        self.thread_data = thread_data
        self.thread_id = thread_id
        self.trace_id = trace_id or str(uuid.uuid4())[:8]
        self.initial_state = initial_state or {}
        self.tools = _filter_tools(tools, config.tools, config.disallowed_tools)

        logger.info(
            "[trace=%s] SubagentExecutor initialized: %s with %s tools",
            self.trace_id,
            config.name,
            len(self.tools),
        )

    def _create_agent(self):
        from deerflow.agents.thread_state import ThreadState

        model_name = _get_model_name(self.config, self.parent_model)
        model = create_chat_model(name=model_name, thinking_enabled=False)

        from deerflow.agents.middlewares.tool_error_handling_middleware import build_subagent_runtime_middlewares

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
            **self.initial_state,
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
                _mark_terminal(result, SubagentStatus.CANCELLED, "Cancelled by user")
                return result

            async for chunk in agent.astream(
                state,
                config=run_config,
                context=context,
                stream_mode="values",
            ):
                if result.cancel_event.is_set():
                    _mark_terminal(result, SubagentStatus.CANCELLED, "Cancelled by user")
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

            _mark_execution_complete(result)
        except Exception as e:
            logger.exception("[trace=%s] Subagent %s async execution failed", self.trace_id, self.config.name)
            if result.cancel_event.is_set():
                _mark_terminal(result, SubagentStatus.CANCELLED, result.error or "Cancelled by user")
            else:
                _mark_terminal(result, SubagentStatus.FAILED, str(e))

        return result

    def _run_with_isolated_loop(self, task: str, result_holder: SubagentResult) -> SubagentResult:
        async def run_isolated() -> SubagentResult:
            loop = asyncio.get_running_loop()
            execution_task = asyncio.create_task(self._aexecute(task, result_holder))
            with result_holder._handle_lock:
                result_holder._loop = loop
                result_holder._asyncio_task = execution_task
            if result_holder.cancel_event.is_set():
                execution_task.cancel()
            try:
                return await execution_task
            except asyncio.CancelledError:
                _mark_terminal(result_holder, SubagentStatus.CANCELLED, result_holder.error or "Cancelled by user")
                return result_holder
            finally:
                with result_holder._handle_lock:
                    result_holder._asyncio_task = None
                    result_holder._loop = None
                result_holder.worker_done_event.set()

        return asyncio.run(run_isolated())

    def _execute_with_timeout(self, task: str, result_holder: SubagentResult) -> SubagentResult:
        future = _isolated_loop_pool.submit(self._run_with_isolated_loop, task, result_holder)
        try:
            return future.result(timeout=self.config.timeout_seconds)
        except FuturesTimeoutError:
            logger.warning("[trace=%s] Subagent %s timed out after %ss", self.trace_id, self.config.name, self.config.timeout_seconds)
            timeout_error = f"Subagent timed out after {self.config.timeout_seconds} seconds"
            with result_holder._status_lock:
                if result_holder.status in _TERMINAL_STATUSES:
                    return result_holder
                result_holder.cancel_event.set()
                result_holder.status = SubagentStatus.TIMED_OUT
                result_holder.error = timeout_error
                result_holder.completed_at = datetime.now()
            _cancel_running_coroutine(result_holder, force=True)
            future.cancel()
            return result_holder
        except Exception as exc:
            logger.exception("[trace=%s] Subagent %s execution wrapper failed", self.trace_id, self.config.name)
            _mark_terminal(result_holder, SubagentStatus.FAILED, str(exc))
            return result_holder

    def execute_async(self, task: str, task_id: str | None = None) -> str:
        task_id = task_id or str(uuid.uuid4())[:8]

        result_holder = SubagentResult(
            task_id=task_id,
            trace_id=self.trace_id,
            status=SubagentStatus.PENDING,
            started_at=datetime.now(),
        )

        with _background_tasks_lock:
            _background_tasks[task_id] = result_holder

        def submit_execution() -> SubagentResult:
            with result_holder._status_lock:
                if result_holder.status == SubagentStatus.PENDING:
                    result_holder.status = SubagentStatus.RUNNING
            return self._execute_with_timeout(task, result_holder)

        def on_done(future: Future[SubagentResult]) -> None:
            try:
                final_result = future.result()
            except Exception as exc:
                logger.exception("[trace=%s] Subagent execution future failed", self.trace_id)
                _mark_terminal(result_holder, SubagentStatus.FAILED, str(exc))
                return

            with _background_tasks_lock:
                if _background_tasks.get(task_id) is result_holder:
                    _background_tasks[task_id] = final_result

        scheduler_future = _scheduler_pool.submit(lambda: _execution_pool.submit(submit_execution).result())
        scheduler_future.add_done_callback(on_done)
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
    return _cancel_running_coroutine(result)


async def wait_for_background_task_shutdown(task_id: str, timeout_seconds: float) -> bool:
    result = get_background_task_result(task_id)
    if result is None:
        return True
    return await asyncio.to_thread(result.worker_done_event.wait, timeout_seconds)
