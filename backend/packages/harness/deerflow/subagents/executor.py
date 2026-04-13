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
    """Result of a subagent execution.

    Attributes:
        task_id: Unique identifier for this execution.
        trace_id: Trace ID for distributed tracing (links parent and subagent logs).
        status: Current status of the execution.
        result: The final result message (if completed).
        error: Error message (if failed).
        started_at: When execution started.
        completed_at: When execution completed.
        ai_messages: List of complete AI messages (as dicts) generated during execution.
    """

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
        """Initialize mutable defaults."""
        if self.ai_messages is None:
            self.ai_messages = []


# Global storage for background task results
_background_tasks: dict[str, SubagentResult] = {}
_background_tasks_lock = threading.Lock()

# Thread pool for background task scheduling and orchestration
_scheduler_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="subagent-scheduler-")

# Thread pool for actual subagent execution (with timeout support)
# Larger pool to avoid blocking when scheduler submits execution tasks
_execution_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="subagent-exec-")

# Dedicated pool for sync execute() calls made from an already-running event loop.
_isolated_loop_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="subagent-isolated-")


def _extract_text_content(content: Any) -> str:
    """Extract readable text from message content blocks.

    LangChain providers may return list content that mixes structured dict blocks
    with raw string chunks. For raw strings we must keep the whole string intact
    instead of joining every chunk with newlines, otherwise text may appear one
    character per line in the UI when a provider emits a string as an iterable of
    tiny chunks.
    """
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
                if isinstance(text_val, str):
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
    """Filter tools based on subagent configuration.

    Args:
        all_tools: List of all available tools.
        allowed: Optional allowlist of tool names. If provided, only these tools are included.
        disallowed: Optional denylist of tool names. These tools are always excluded.

    Returns:
        Filtered list of tools.
    """
    filtered = all_tools

    # Apply allowlist if specified
    if allowed is not None:
        allowed_set = set(allowed)
        filtered = [t for t in filtered if t.name in allowed_set]

    # Apply denylist
    if disallowed is not None:
        disallowed_set = set(disallowed)
        filtered = [t for t in filtered if t.name not in disallowed_set]

    return filtered


def _get_model_name(config: SubagentConfig, parent_model: str | None) -> str | None:
    """Resolve the model name for a subagent.

    Args:
        config: Subagent configuration.
        parent_model: The parent agent's model name.

    Returns:
        Model name to use, or None to use default.
    """
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
        """Initialize the executor.

        Args:
            config: Subagent configuration.
            tools: List of all available tools (will be filtered).
            parent_model: The parent agent's model name for inheritance.
            sandbox_state: Sandbox state from parent agent.
            thread_data: Thread data from parent agent.
            thread_id: Thread ID for sandbox operations.
            trace_id: Trace ID from parent for distributed tracing.
        """
        self.config = config
        self.parent_model = parent_model
        self.sandbox_state = sandbox_state
        self.thread_data = thread_data
        self.thread_id = thread_id
        # Generate trace_id if not provided (for top-level calls)
        self.trace_id = trace_id or str(uuid.uuid4())[:8]

        # Filter tools based on config
        self.tools = _filter_tools(
            tools,
            config.tools,
            config.disallowed_tools,
        )

        logger.info(f"[trace={self.trace_id}] SubagentExecutor initialized: {config.name} with {len(self.tools)} tools")

    def _create_agent(self):
        """Create the agent instance."""
        model_name = _get_model_name(self.config, self.parent_model)
        model = create_chat_model(name=model_name, thinking_enabled=False)

        from deerflow.agents.middlewares.tool_error_handling_middleware import build_subagent_runtime_middlewares

        # Reuse shared middleware composition with lead agent.
        middlewares = build_subagent_runtime_middlewares(lazy_init=True)

        return create_agent(
            model=model,
            tools=self.tools,
            middleware=middlewares,
            system_prompt=self.config.system_prompt,
            state_schema=ThreadState,
        )

    def _build_initial_state(self, task: str) -> dict[str, Any]:
        """Build the initial state for agent execution.

        Args:
            task: The task description.

        Returns:
            Initial state dictionary.
        """
        state: dict[str, Any] = {
            "messages": [HumanMessage(content=task)],
        }

        # Pass through sandbox and thread data from parent
        if self.sandbox_state is not None:
            state["sandbox"] = self.sandbox_state
        if self.thread_data is not None:
            state["thread_data"] = self.thread_data

        return state

    async def _aexecute(self, task: str, result_holder: SubagentResult | None = None) -> SubagentResult:
        """Execute a task asynchronously.

        Args:
            task: The task description for the subagent.
            result_holder: Optional pre-created result object to update during execution.

        Returns:
            SubagentResult with the execution result.
        """
        if result_holder is not None:
            # Use the provided result holder (for async execution with real-time updates)
            result = result_holder
        else:
            # Create a new result for synchronous execution
            task_id = str(uuid.uuid4())[:8]
            result = SubagentResult(
                task_id=task_id,
                trace_id=self.trace_id,
                status=SubagentStatus.RUNNING,
                started_at=datetime.now(),
            )

        try:
            agent = self._create_agent()
            state = self._build_initial_state(task)

            # Build config with thread_id for sandbox access and recursion limit
            run_config: RunnableConfig = {
                "recursion_limit": self.config.max_turns,
            }
            context = {}
            if self.thread_id:
                run_config["configurable"] = {"thread_id": self.thread_id}
                context["thread_id"] = self.thread_id

            logger.info(f"[trace={self.trace_id}] Subagent {self.config.name} starting async execution with max_turns={self.config.max_turns}")

            # Use stream instead of invoke to get real-time updates
            # This allows us to collect AI messages as they are generated
            final_state = None

            # Pre-check: bail out immediately if already cancelled before streaming starts
            if result.cancel_event.is_set():
                logger.info(f"[trace={self.trace_id}] Subagent {self.config.name} cancelled before streaming")
                with _background_tasks_lock:
                    if result.status == SubagentStatus.RUNNING:
                        result.status = SubagentStatus.CANCELLED
                        result.error = "Cancelled by user"
                        result.completed_at = datetime.now()
                return result

            async for chunk in agent.astream(state, config=run_config, context=context, stream_mode="values"):  # type: ignore[arg-type]
                # Cooperative cancellation: check if parent requested stop.
                # Note: cancellation is only detected at astream iteration boundaries,
                # so long-running tool calls within a single iteration will not be
                # interrupted until the next chunk is yielded.
                if result.cancel_event.is_set():
                    logger.info(f"[trace={self.trace_id}] Subagent {self.config.name} cancelled by parent")
                    with _background_tasks_lock:
                        if result.status == SubagentStatus.RUNNING:
                            result.status = SubagentStatus.CANCELLED
                            result.error = "Cancelled by user"
                            result.completed_at = datetime.now()
                    return result

                final_state = chunk

                # Extract AI messages from the current state
                messages = chunk.get("messages", [])
                if messages:
                    last_message = messages[-1]
                    # Check if this is a new AI message
                    if isinstance(last_message, AIMessage):
                        # Convert message to dict for serialization
                        message_dict = last_message.model_dump()
                        # Only add if it's not already in the list (avoid duplicates)
                        # Check by comparing message IDs if available, otherwise compare full dict
                        message_id = message_dict.get("id")
                        is_duplicate = False
                        if message_id:
                            is_duplicate = any(msg.get("id") == message_id for msg in result.ai_messages)
                        else:
                            is_duplicate = message_dict in result.ai_messages

                        if not is_duplicate:
                            result.ai_messages.append(message_dict)
                            logger.info(f"[trace={self.trace_id}] Subagent {self.config.name} captured AI message #{len(result.ai_messages)}")

            logger.info(f"[trace={self.trace_id}] Subagent {self.config.name} completed async execution")

            if final_state is None:
                logger.warning(f"[trace={self.trace_id}] Subagent {self.config.name} no final state")
                result.result = "No response generated"
            else:
                messages = final_state.get("messages", [])
                logger.info(f"[trace={self.trace_id}] Subagent {self.config.name} final messages count: {len(messages)}")

                last_ai_message = None
                for msg in reversed(messages):
                    if isinstance(msg, AIMessage):
                        last_ai_message = msg
                        break

                if last_ai_message is not None:
                    result.result = _extract_text_content(last_ai_message.content)
                elif messages:
                    last_message = messages[-1]
                    logger.warning(f"[trace={self.trace_id}] Subagent {self.config.name} no AIMessage found, using last message: {type(last_message)}")
                    raw_content = last_message.content if hasattr(last_message, "content") else str(last_message)
                    result.result = _extract_text_content(raw_content)
                else:
                    logger.warning(f"[trace={self.trace_id}] Subagent {self.config.name} no messages in final state")
                    result.result = "No response generated"

            result.status = SubagentStatus.COMPLETED
            result.completed_at = datetime.now()

        except Exception as e:
            logger.exception(f"[trace={self.trace_id}] Subagent {self.config.name} async execution failed")
            result.status = SubagentStatus.FAILED
            result.error = str(e)
            result.completed_at = datetime.now()

        return result

    def _execute_in_isolated_loop(self, task: str, result_holder: SubagentResult | None = None) -> SubagentResult:
        """Execute the subagent in a completely fresh event loop.

        This method is designed to run in a separate thread to ensure complete
        isolation from any parent event loop, preventing conflicts with asyncio
        primitives that may be bound to the parent loop (e.g., httpx clients).
        """
        try:
            previous_loop = asyncio.get_event_loop()
        except RuntimeError:
            previous_loop = None

        # Create and set a new event loop for this thread
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
                    f"[trace={self.trace_id}] Failed while cleaning up isolated event loop for subagent {self.config.name}",
                    exc_info=True,
                )
            finally:
                try:
                    loop.close()
                finally:
                    asyncio.set_event_loop(previous_loop)

    def execute(self, task: str, result_holder: SubagentResult | None = None) -> SubagentResult:
        """Execute a task synchronously (wrapper around async execution).

        This method runs the async execution in a new event loop, allowing
        asynchronous tools (like MCP tools) to be used within the thread pool.

        When called from within an already-running event loop (e.g., when the
        parent agent is async), this method isolates the subagent execution in
        a separate thread to avoid event loop conflicts with shared async
        primitives like httpx clients.

        Args:
            task: The task description for the subagent.
            result_holder: Optional pre-created result object to update during execution.

        Returns:
            SubagentResult with the execution result.
        """
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                logger.debug(f"[trace={self.trace_id}] Subagent {self.config.name} detected running event loop, using isolated thread")
                future = _isolated_loop_pool.submit(self._execute_in_isolated_loop, task, result_holder)
                return future.result()

            # Standard path: no running event loop, use asyncio.run
            return asyncio.run(self._aexecute(task, result_holder))
        except Exception as e:
            logger.exception(f"[trace={self.trace_id}] Subagent {self.config.name} execution failed")
            # Create a result with error if we don't have one
            if result_holder is not None:
                result = result_holder
            else:
                result = SubagentResult(
                    task_id=str(uuid.uuid4())[:8],
                    trace_id=self.trace_id,
                    status=SubagentStatus.FAILED,
                )
            result.status = SubagentStatus.FAILED
            result.error = str(e)
            result.completed_at = datetime.now()
            return result

    def execute_async(self, task: str, task_id: str | None = None) -> str:
        """Start a task execution in the background.

        Args:
            task: The task description for the subagent.
            task_id: Optional task ID to use. If not provided, a random UUID will be generated.

        Returns:
            Task ID that can be used to check status later.
        """
        # Use provided task_id or generate a new one
        if task_id is None:
            task_id = str(uuid.uuid4())[:8]

        # Create initial pending result
        result = SubagentResult(
            task_id=task_id,
            trace_id=self.trace_id,
            status=SubagentStatus.PENDING,
        )

        with _background_tasks_lock:
            _background_tasks[task_id] = result

        def run_with_timeout():
            """Run the task with timeout in a separate thread."""
            try:
                result.status = SubagentStatus.RUNNING
                result.started_at = datetime.now()

                # Submit actual execution to thread pool
                future: Future = _execution_pool.submit(self.execute, task, result)

                try:
                    # Wait with timeout
                    future.result(timeout=self.config.timeout_seconds)
                except FuturesTimeoutError:
                    logger.warning(f"[trace={self.trace_id}] Subagent {self.config.name} timed out after {self.config.timeout_seconds}s")
                    result.status = SubagentStatus.TIMED_OUT
                    result.error = f"Task timed out after {self.config.timeout_seconds} seconds"
                    result.completed_at = datetime.now()
                    # Note: cannot truly kill the thread, but mark as timed out
                except Exception as e:
                    logger.exception(f"[trace={self.trace_id}] Subagent {self.config.name} background execution failed")
                    result.status = SubagentStatus.FAILED
                    result.error = str(e)
                    result.completed_at = datetime.now()
            except Exception as e:
                logger.exception(f"[trace={self.trace_id}] Scheduler failed for subagent {self.config.name}")
                result.status = SubagentStatus.FAILED
                result.error = str(e)
                result.completed_at = datetime.now()

        # Submit scheduler task
        _scheduler_pool.submit(run_with_timeout)

        logger.info(f"[trace={self.trace_id}] Started async subagent {self.config.name} with task_id={task_id}")
        return task_id


def get_background_task_result(task_id: str) -> SubagentResult | None:
    """Get the result of a background task.

    Args:
        task_id: The task ID.

    Returns:
        SubagentResult if found, None otherwise.
    """
    with _background_tasks_lock:
        return _background_tasks.get(task_id)


def cleanup_background_task(task_id: str) -> None:
    """Remove a background task from storage.

    Args:
        task_id: The task ID to remove.
    """
    with _background_tasks_lock:
        _background_tasks.pop(task_id, None)


def request_cancel_background_task(task_id: str) -> bool:
    """Request cooperative cancellation of a background task.

    This sets a flag on the tracked task result that the executing subagent
    checks periodically between streamed chunks. It does not forcibly kill any
    running tool call, but allows the subagent to stop as soon as control
    returns to the agent loop.

    Args:
        task_id: The task ID to cancel.

    Returns:
        True if the task existed and the cancel flag was set, False otherwise.
    """
    with _background_tasks_lock:
        result = _background_tasks.get(task_id)
        if result is None:
            return False
        result.cancel_event.set()
        return True
