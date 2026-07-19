"""Tests for subagent executor async and isolated-loop execution paths.

Covers:
- SubagentExecutor._aexecute() asynchronous execution path
- Isolated event-loop execution and timeout handling
- Error handling in async and background paths
- Async tool support (MCP tools)
- Cooperative cancellation via cancel_event

Note: Due to circular import issues in the main codebase, conftest.py mocks
deerflow.subagents.executor. This test file uses delayed import via fixture to test
the real implementation in isolation.
"""

import asyncio
import sys
import threading
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

# Module names that need to be mocked to break circular imports
_MOCKED_MODULE_NAMES = [
    "deerflow.agents",
    "deerflow.agents.thread_state",
    "deerflow.agents.middlewares",
    "deerflow.agents.middlewares.thread_data_middleware",
    "deerflow.sandbox",
    "deerflow.sandbox.middleware",
    "deerflow.sandbox.security",
    "deerflow.models",
]


@pytest.fixture(scope="session", autouse=True)
def _setup_executor_classes():
    """Set up mocked modules and import real executor classes.

    This fixture runs once per session and yields the executor classes.
    It handles module cleanup to avoid affecting other test files.
    """
    # Save original modules
    original_modules = {name: sys.modules.get(name) for name in _MOCKED_MODULE_NAMES}
    original_executor = sys.modules.get("deerflow.subagents.executor")

    # Remove mocked executor if exists (from conftest.py)
    if "deerflow.subagents.executor" in sys.modules:
        del sys.modules["deerflow.subagents.executor"]

    # Set up mocks
    for name in _MOCKED_MODULE_NAMES:
        sys.modules[name] = MagicMock()

    # Import real classes inside fixture
    from langchain_core.messages import AIMessage, HumanMessage

    from deerflow.subagents.config import SubagentConfig
    from deerflow.subagents.executor import (
        SubagentExecutor,
        SubagentResult,
        SubagentStatus,
    )

    # Store classes in a dict to yield
    classes = {
        "AIMessage": AIMessage,
        "HumanMessage": HumanMessage,
        "SubagentConfig": SubagentConfig,
        "SubagentExecutor": SubagentExecutor,
        "SubagentResult": SubagentResult,
        "SubagentStatus": SubagentStatus,
    }

    yield classes

    # Cleanup: Restore original modules
    for name in _MOCKED_MODULE_NAMES:
        if original_modules[name] is not None:
            sys.modules[name] = original_modules[name]
        elif name in sys.modules:
            del sys.modules[name]

    # Restore executor module (conftest.py mock)
    if original_executor is not None:
        sys.modules["deerflow.subagents.executor"] = original_executor
    elif "deerflow.subagents.executor" in sys.modules:
        del sys.modules["deerflow.subagents.executor"]


# Helper classes that wrap real classes for testing
class MockHumanMessage:
    """Mock HumanMessage for testing - wraps real class from fixture."""

    def __init__(self, content, _classes=None):
        self._content = content
        self._classes = _classes

    def _get_real(self):
        return self._classes["HumanMessage"](content=self._content)


class MockAIMessage:
    """Mock AIMessage for testing - wraps real class from fixture."""

    def __init__(self, content, msg_id=None, _classes=None):
        self._content = content
        self._msg_id = msg_id
        self._classes = _classes

    def _get_real(self):
        msg = self._classes["AIMessage"](content=self._content)
        if self._msg_id:
            msg.id = self._msg_id
        return msg


async def async_iterator(items):
    """Helper to create an async iterator from a list."""
    for item in items:
        yield item


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def classes(_setup_executor_classes):
    """Provide access to executor classes."""
    return _setup_executor_classes


@pytest.fixture
def base_config(classes):
    """Return a basic subagent config for testing."""
    return classes["SubagentConfig"](
        name="test-agent",
        description="Test agent",
        system_prompt="You are a test agent.",
        max_turns=10,
        timeout_seconds=60,
    )


@pytest.fixture
def mock_agent():
    """Return a properly configured mock agent with async stream."""
    agent = MagicMock()
    agent.astream = MagicMock()
    return agent


# Helper to create real message objects
class _MsgHelper:
    """Helper to create real message objects from fixture classes."""

    def __init__(self, classes):
        self.classes = classes

    def human(self, content):
        return self.classes["HumanMessage"](content=content)

    def ai(self, content, msg_id=None):
        msg = self.classes["AIMessage"](content=content)
        if msg_id:
            msg.id = msg_id
        return msg


@pytest.fixture
def msg(classes):
    """Provide message factory."""
    return _MsgHelper(classes)


# -----------------------------------------------------------------------------
# Async Execution Path Tests
# -----------------------------------------------------------------------------


class TestAsyncExecutionPath:
    """Test _aexecute() async execution path."""

    @pytest.mark.anyio
    async def test_aexecute_success(self, classes, base_config, mock_agent, msg):
        """Test successful async execution returns completed result."""
        SubagentExecutor = classes["SubagentExecutor"]
        SubagentStatus = classes["SubagentStatus"]

        final_message = msg.ai("Task completed successfully", "msg-1")
        final_state = {
            "messages": [
                msg.human("Do something"),
                final_message,
            ]
        }
        mock_agent.astream = lambda *args, **kwargs: async_iterator([final_state])

        executor = SubagentExecutor(
            config=base_config,
            tools=[],
            thread_id="test-thread",
            trace_id="test-trace",
        )

        with patch.object(executor, "_create_agent", return_value=mock_agent):
            result = await executor._aexecute("Do something")

        assert result.status == SubagentStatus.COMPLETED
        assert result.result == "Task completed successfully"
        assert result.error is None
        assert result.started_at is not None
        assert result.completed_at is not None

    @pytest.mark.anyio
    async def test_aexecute_collects_ai_messages(self, classes, base_config, mock_agent, msg):
        """Test that AI messages are collected during streaming."""
        SubagentExecutor = classes["SubagentExecutor"]
        SubagentStatus = classes["SubagentStatus"]

        msg1 = msg.ai("First response", "msg-1")
        msg2 = msg.ai("Second response", "msg-2")

        chunk1 = {"messages": [msg.human("Task"), msg1]}
        chunk2 = {"messages": [msg.human("Task"), msg1, msg2]}

        mock_agent.astream = lambda *args, **kwargs: async_iterator([chunk1, chunk2])

        executor = SubagentExecutor(
            config=base_config,
            tools=[],
            thread_id="test-thread",
        )

        with patch.object(executor, "_create_agent", return_value=mock_agent):
            result = await executor._aexecute("Task")

        assert result.status == SubagentStatus.COMPLETED
        assert len(result.ai_messages) == 2
        assert result.ai_messages[0]["id"] == "msg-1"
        assert result.ai_messages[1]["id"] == "msg-2"

    @pytest.mark.anyio
    async def test_aexecute_handles_duplicate_messages(self, classes, base_config, mock_agent, msg):
        """Test that duplicate AI messages are not added."""
        SubagentExecutor = classes["SubagentExecutor"]

        msg1 = msg.ai("Response", "msg-1")

        # Same message appears in multiple chunks
        chunk1 = {"messages": [msg.human("Task"), msg1]}
        chunk2 = {"messages": [msg.human("Task"), msg1]}

        mock_agent.astream = lambda *args, **kwargs: async_iterator([chunk1, chunk2])

        executor = SubagentExecutor(
            config=base_config,
            tools=[],
            thread_id="test-thread",
        )

        with patch.object(executor, "_create_agent", return_value=mock_agent):
            result = await executor._aexecute("Task")

        assert len(result.ai_messages) == 1

    @pytest.mark.anyio
    async def test_aexecute_handles_list_content(self, classes, base_config, mock_agent, msg):
        """Test handling of list-type content in AIMessage."""
        SubagentExecutor = classes["SubagentExecutor"]
        SubagentStatus = classes["SubagentStatus"]

        final_message = msg.ai([{"text": "Part 1"}, {"text": "Part 2"}])
        final_state = {
            "messages": [
                msg.human("Task"),
                final_message,
            ]
        }
        mock_agent.astream = lambda *args, **kwargs: async_iterator([final_state])

        executor = SubagentExecutor(
            config=base_config,
            tools=[],
            thread_id="test-thread",
        )

        with patch.object(executor, "_create_agent", return_value=mock_agent):
            result = await executor._aexecute("Task")

        assert result.status == SubagentStatus.COMPLETED
        assert "Part 1" in result.result
        assert "Part 2" in result.result

    @pytest.mark.anyio
    async def test_aexecute_handles_agent_exception(self, classes, base_config, mock_agent):
        """Test that exceptions during execution are caught and returned as FAILED."""
        SubagentExecutor = classes["SubagentExecutor"]
        SubagentStatus = classes["SubagentStatus"]

        mock_agent.astream.side_effect = Exception("Agent error")

        executor = SubagentExecutor(
            config=base_config,
            tools=[],
            thread_id="test-thread",
        )

        with patch.object(executor, "_create_agent", return_value=mock_agent):
            result = await executor._aexecute("Task")

        assert result.status == SubagentStatus.FAILED
        assert "Agent error" in result.error
        assert result.completed_at is not None

    @pytest.mark.anyio
    async def test_aexecute_no_final_state(self, classes, base_config, mock_agent):
        """Test handling when no final state is returned."""
        SubagentExecutor = classes["SubagentExecutor"]
        SubagentStatus = classes["SubagentStatus"]

        mock_agent.astream = lambda *args, **kwargs: async_iterator([])

        executor = SubagentExecutor(
            config=base_config,
            tools=[],
            thread_id="test-thread",
        )

        with patch.object(executor, "_create_agent", return_value=mock_agent):
            result = await executor._aexecute("Task")

        assert result.status == SubagentStatus.COMPLETED
        assert result.result == "No response generated"

    @pytest.mark.anyio
    async def test_aexecute_no_ai_message_in_state(self, classes, base_config, mock_agent, msg):
        """Test fallback when no AIMessage found in final state."""
        SubagentExecutor = classes["SubagentExecutor"]
        SubagentStatus = classes["SubagentStatus"]

        final_state = {"messages": [msg.human("Task")]}
        mock_agent.astream = lambda *args, **kwargs: async_iterator([final_state])

        executor = SubagentExecutor(
            config=base_config,
            tools=[],
            thread_id="test-thread",
        )

        with patch.object(executor, "_create_agent", return_value=mock_agent):
            result = await executor._aexecute("Task")

        # Should fallback to string representation of last message
        assert result.status == SubagentStatus.COMPLETED
        assert "Task" in result.result


# -----------------------------------------------------------------------------
# Isolated Loop Execution Path Tests
# -----------------------------------------------------------------------------


class TestIsolatedLoopExecutionPath:
    """Test the isolated event-loop path used by background execution."""

    def test_run_with_isolated_loop_executes_async_agent(self, classes, base_config, mock_agent, msg):
        """The isolated-loop wrapper runs the async agent to completion."""
        SubagentExecutor = classes["SubagentExecutor"]
        SubagentResult = classes["SubagentResult"]
        SubagentStatus = classes["SubagentStatus"]

        final_message = msg.ai("Sync result", "msg-1")
        final_state = {
            "messages": [
                msg.human("Task"),
                final_message,
            ]
        }
        mock_agent.astream = lambda *args, **kwargs: async_iterator([final_state])

        executor = SubagentExecutor(
            config=base_config,
            tools=[],
            thread_id="test-thread",
        )
        result_holder = SubagentResult(
            task_id="isolated-loop",
            trace_id="test-trace",
            status=SubagentStatus.RUNNING,
            started_at=datetime.now(),
        )

        with patch.object(executor, "_create_agent", return_value=mock_agent):
            result = executor._run_with_isolated_loop("Task", result_holder)

        assert result.status == SubagentStatus.COMPLETED
        assert result.result == "Sync result"

    def test_isolated_loop_in_thread_pool_context(self, classes, base_config, msg):
        """The isolated-loop wrapper works when called from a thread pool.

        This simulates the scheduler and execution pools used by execute_async().
        """
        from concurrent.futures import ThreadPoolExecutor

        SubagentExecutor = classes["SubagentExecutor"]
        SubagentResult = classes["SubagentResult"]
        SubagentStatus = classes["SubagentStatus"]

        final_message = msg.ai("Thread pool result", "msg-1")
        final_state = {
            "messages": [
                msg.human("Task"),
                final_message,
            ]
        }

        def run_in_thread():
            mock_agent = MagicMock()
            mock_agent.astream = lambda *args, **kwargs: async_iterator([final_state])

            executor = SubagentExecutor(
                config=base_config,
                tools=[],
                thread_id="test-thread",
            )
            result_holder = SubagentResult(
                task_id="thread-pool",
                trace_id="test-trace",
                status=SubagentStatus.RUNNING,
                started_at=datetime.now(),
            )

            with patch.object(executor, "_create_agent", return_value=mock_agent):
                return executor._run_with_isolated_loop("Task", result_holder)

        # Execute in thread pool (simulating _execution_pool usage)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run_in_thread)
            result = future.result(timeout=5)

        assert result.status == SubagentStatus.COMPLETED
        assert result.result == "Thread pool result"

    @pytest.mark.anyio
    async def test_timeout_wrapper_uses_isolated_thread_from_running_loop(self, classes, base_config, mock_agent, msg):
        """The timeout wrapper never runs asyncio.run() on the caller's loop thread."""
        SubagentExecutor = classes["SubagentExecutor"]
        SubagentResult = classes["SubagentResult"]
        SubagentStatus = classes["SubagentStatus"]

        execution_threads = []
        final_state = {
            "messages": [
                msg.human("Task"),
                msg.ai("Async loop result", "msg-1"),
            ]
        }

        async def mock_astream(*args, **kwargs):
            execution_threads.append(threading.current_thread().name)
            yield final_state

        mock_agent.astream = mock_astream

        executor = SubagentExecutor(
            config=base_config,
            tools=[],
            thread_id="test-thread",
        )
        result_holder = SubagentResult(
            task_id="running-loop",
            trace_id="test-trace",
            status=SubagentStatus.RUNNING,
            started_at=datetime.now(),
        )

        with patch.object(executor, "_create_agent", return_value=mock_agent):
            result = executor._execute_with_timeout("Task", result_holder)

        assert execution_threads
        assert all(name.startswith("subagent-isolated-") for name in execution_threads)
        assert result.status == SubagentStatus.COMPLETED
        assert result.result == "Async loop result"

    def test_timeout_wrapper_handles_isolated_loop_failure(self, classes, base_config):
        """An isolated-loop failure becomes a failed result."""
        SubagentExecutor = classes["SubagentExecutor"]
        SubagentResult = classes["SubagentResult"]
        SubagentStatus = classes["SubagentStatus"]

        executor = SubagentExecutor(
            config=base_config,
            tools=[],
            thread_id="test-thread",
        )
        result_holder = SubagentResult(
            task_id="isolated-error",
            trace_id="test-trace",
            status=SubagentStatus.RUNNING,
            started_at=datetime.now(),
        )

        with patch.object(executor, "_run_with_isolated_loop", side_effect=Exception("Asyncio run error")):
            result = executor._execute_with_timeout("Task", result_holder)

        assert result.status == SubagentStatus.FAILED
        assert "Asyncio run error" in result.error
        assert result.completed_at is not None

    def test_isolated_loop_updates_result_holder(self, classes, base_config, mock_agent, msg):
        """The isolated-loop path updates the provided result holder in place."""
        SubagentExecutor = classes["SubagentExecutor"]
        SubagentResult = classes["SubagentResult"]
        SubagentStatus = classes["SubagentStatus"]

        msg1 = msg.ai("Step 1", "msg-1")
        chunk1 = {"messages": [msg.human("Task"), msg1]}

        mock_agent.astream = lambda *args, **kwargs: async_iterator([chunk1])

        # Pre-create result holder (as done in execute_async)
        result_holder = SubagentResult(
            task_id="predefined-id",
            trace_id="test-trace",
            status=SubagentStatus.RUNNING,
            started_at=datetime.now(),
        )

        executor = SubagentExecutor(
            config=base_config,
            tools=[],
            thread_id="test-thread",
        )

        with patch.object(executor, "_create_agent", return_value=mock_agent):
            result = executor._run_with_isolated_loop("Task", result_holder)

        # Should be the same object
        assert result is result_holder
        assert result.task_id == "predefined-id"
        assert result.status == SubagentStatus.COMPLETED


# -----------------------------------------------------------------------------
# Async Tool Support Tests (MCP Tools)
# -----------------------------------------------------------------------------


class TestAsyncToolSupport:
    """Test that async-only tools (like MCP tools) work correctly."""

    @pytest.mark.anyio
    async def test_async_tool_called_in_astream(self, classes, base_config, msg):
        """Test that async tools are properly awaited in astream.

        This verifies the fix for: async MCP tools not being executed properly
        because they were being called synchronously.
        """
        SubagentExecutor = classes["SubagentExecutor"]
        SubagentStatus = classes["SubagentStatus"]

        async_tool_calls = []

        async def mock_async_tool(*args, **kwargs):
            async_tool_calls.append("called")
            await asyncio.sleep(0.01)  # Simulate async work
            return {"result": "async tool result"}

        mock_agent = MagicMock()

        # Simulate agent that calls async tools during streaming
        async def mock_astream(*args, **kwargs):
            await mock_async_tool()
            yield {
                "messages": [
                    msg.human("Task"),
                    msg.ai("Done", "msg-1"),
                ]
            }

        mock_agent.astream = mock_astream

        executor = SubagentExecutor(
            config=base_config,
            tools=[],
            thread_id="test-thread",
        )

        with patch.object(executor, "_create_agent", return_value=mock_agent):
            result = await executor._aexecute("Task")

        assert len(async_tool_calls) == 1
        assert result.status == SubagentStatus.COMPLETED

    def test_isolated_loop_with_async_tools(self, classes, base_config, msg):
        """The isolated event loop awaits async-only tools."""
        SubagentExecutor = classes["SubagentExecutor"]
        SubagentResult = classes["SubagentResult"]
        SubagentStatus = classes["SubagentStatus"]

        async_tool_calls = []

        async def mock_async_tool():
            async_tool_calls.append("called")
            await asyncio.sleep(0.01)
            return {"result": "async result"}

        mock_agent = MagicMock()

        async def mock_astream(*args, **kwargs):
            await mock_async_tool()
            yield {
                "messages": [
                    msg.human("Task"),
                    msg.ai("Done", "msg-1"),
                ]
            }

        mock_agent.astream = mock_astream

        executor = SubagentExecutor(
            config=base_config,
            tools=[],
            thread_id="test-thread",
        )
        result_holder = SubagentResult(
            task_id="async-tools",
            trace_id="test-trace",
            status=SubagentStatus.RUNNING,
            started_at=datetime.now(),
        )

        with patch.object(executor, "_create_agent", return_value=mock_agent):
            result = executor._run_with_isolated_loop("Task", result_holder)

        assert len(async_tool_calls) == 1
        assert result.status == SubagentStatus.COMPLETED


# -----------------------------------------------------------------------------
# Thread Safety Tests
# -----------------------------------------------------------------------------


class TestThreadSafety:
    """Test thread safety of executor operations."""

    def test_multiple_executors_in_parallel(self, classes, base_config, msg):
        """Test multiple executors running in parallel via thread pool."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        SubagentExecutor = classes["SubagentExecutor"]
        SubagentResult = classes["SubagentResult"]
        SubagentStatus = classes["SubagentStatus"]

        results = []

        def execute_task(task_id: int):
            def make_astream(*args, **kwargs):
                return async_iterator(
                    [
                        {
                            "messages": [
                                msg.human(f"Task {task_id}"),
                                msg.ai(f"Result {task_id}", f"msg-{task_id}"),
                            ]
                        }
                    ]
                )

            mock_agent = MagicMock()
            mock_agent.astream = make_astream

            executor = SubagentExecutor(
                config=base_config,
                tools=[],
                thread_id=f"thread-{task_id}",
            )
            result_holder = SubagentResult(
                task_id=f"parallel-{task_id}",
                trace_id="test-trace",
                status=SubagentStatus.RUNNING,
                started_at=datetime.now(),
            )

            with patch.object(executor, "_create_agent", return_value=mock_agent):
                return executor._run_with_isolated_loop(f"Task {task_id}", result_holder)

        # Execute multiple tasks in parallel
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(execute_task, i) for i in range(5)]
            for future in as_completed(futures):
                results.append(future.result())

        assert len(results) == 5
        for result in results:
            assert result.status == SubagentStatus.COMPLETED
            assert "Result" in result.result


# -----------------------------------------------------------------------------
# Cleanup Background Task Tests
# -----------------------------------------------------------------------------


class TestCleanupBackgroundTask:
    """Test cleanup_background_task function for race condition prevention."""

    @pytest.fixture
    def executor_module(self, _setup_executor_classes):
        """Return the session's real executor module without changing class identity."""

        from deerflow.subagents import executor

        return executor

    def test_cleanup_removes_terminal_completed_task(self, executor_module, classes):
        """Test that cleanup removes a COMPLETED task."""
        SubagentResult = classes["SubagentResult"]
        SubagentStatus = classes["SubagentStatus"]

        # Add a completed task
        task_id = "test-completed-task"
        result = SubagentResult(
            task_id=task_id,
            trace_id="test-trace",
            status=SubagentStatus.COMPLETED,
            result="done",
            completed_at=datetime.now(),
        )
        executor_module._background_tasks[task_id] = result

        # Cleanup should remove it
        executor_module.cleanup_background_task(task_id)

        assert task_id not in executor_module._background_tasks

    def test_cleanup_removes_terminal_failed_task(self, executor_module, classes):
        """Test that cleanup removes a FAILED task."""
        SubagentResult = classes["SubagentResult"]
        SubagentStatus = classes["SubagentStatus"]

        task_id = "test-failed-task"
        result = SubagentResult(
            task_id=task_id,
            trace_id="test-trace",
            status=SubagentStatus.FAILED,
            error="error",
            completed_at=datetime.now(),
        )
        executor_module._background_tasks[task_id] = result

        executor_module.cleanup_background_task(task_id)

        assert task_id not in executor_module._background_tasks

    def test_cleanup_removes_terminal_timed_out_task(self, executor_module, classes):
        """Test that cleanup removes a TIMED_OUT task."""
        SubagentResult = classes["SubagentResult"]
        SubagentStatus = classes["SubagentStatus"]

        task_id = "test-timedout-task"
        result = SubagentResult(
            task_id=task_id,
            trace_id="test-trace",
            status=SubagentStatus.TIMED_OUT,
            error="timeout",
            completed_at=datetime.now(),
        )
        executor_module._background_tasks[task_id] = result

        executor_module.cleanup_background_task(task_id)

        assert task_id not in executor_module._background_tasks

    def test_cleanup_removes_running_task(self, executor_module, classes):
        """Explicit cleanup removes a RUNNING task from the result registry."""
        SubagentResult = classes["SubagentResult"]
        SubagentStatus = classes["SubagentStatus"]

        task_id = "test-running-task"
        result = SubagentResult(
            task_id=task_id,
            trace_id="test-trace",
            status=SubagentStatus.RUNNING,
            started_at=datetime.now(),
        )
        executor_module._background_tasks[task_id] = result

        executor_module.cleanup_background_task(task_id)

        assert task_id not in executor_module._background_tasks

    def test_cleanup_removes_pending_task(self, executor_module, classes):
        """Explicit cleanup removes a PENDING task from the result registry."""
        SubagentResult = classes["SubagentResult"]
        SubagentStatus = classes["SubagentStatus"]

        task_id = "test-pending-task"
        result = SubagentResult(
            task_id=task_id,
            trace_id="test-trace",
            status=SubagentStatus.PENDING,
        )
        executor_module._background_tasks[task_id] = result

        executor_module.cleanup_background_task(task_id)

        assert task_id not in executor_module._background_tasks

    def test_cleanup_handles_unknown_task_gracefully(self, executor_module):
        """Test that cleanup doesn't raise for unknown task IDs."""
        # Should not raise
        executor_module.cleanup_background_task("nonexistent-task")

    def test_cleanup_removes_task_with_completed_at_even_if_running(self, executor_module, classes):
        """Test that cleanup removes task if completed_at is set, even if status is RUNNING.

        This is a safety net: if completed_at is set, the task is considered done
        regardless of status.
        """
        SubagentResult = classes["SubagentResult"]
        SubagentStatus = classes["SubagentStatus"]

        task_id = "test-completed-at-task"
        result = SubagentResult(
            task_id=task_id,
            trace_id="test-trace",
            status=SubagentStatus.RUNNING,  # Status not terminal
            completed_at=datetime.now(),  # But completed_at is set
        )
        executor_module._background_tasks[task_id] = result

        executor_module.cleanup_background_task(task_id)

        # Should be removed because completed_at is set
        assert task_id not in executor_module._background_tasks


# -----------------------------------------------------------------------------
# Cooperative Cancellation Tests
# -----------------------------------------------------------------------------


class TestCooperativeCancellation:
    """Test cooperative cancellation via cancel_event."""

    @pytest.fixture
    def executor_module(self, _setup_executor_classes):
        """Return the session's real executor module without changing class identity."""

        from deerflow.subagents import executor

        return executor

    @pytest.mark.anyio
    async def test_aexecute_cancelled_before_streaming(self, classes, base_config, mock_agent, msg):
        """Test that _aexecute returns CANCELLED when cancel_event is set before streaming."""
        SubagentExecutor = classes["SubagentExecutor"]
        SubagentResult = classes["SubagentResult"]
        SubagentStatus = classes["SubagentStatus"]

        # The agent should never be called
        call_count = 0

        async def mock_astream(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            yield {"messages": [msg.human("Task"), msg.ai("Done", "msg-1")]}

        mock_agent.astream = mock_astream

        # Pre-create result holder with cancel_event already set
        result_holder = SubagentResult(
            task_id="cancel-before",
            trace_id="test-trace",
            status=SubagentStatus.RUNNING,
            started_at=datetime.now(),
        )
        result_holder.cancel_event.set()

        executor = SubagentExecutor(
            config=base_config,
            tools=[],
            thread_id="test-thread",
        )

        with patch.object(executor, "_create_agent", return_value=mock_agent):
            result = await executor._aexecute("Task", result_holder=result_holder)

        assert result.status == SubagentStatus.CANCELLED
        assert result.error == "Cancelled by user"
        assert result.completed_at is not None
        assert call_count == 0  # astream was never entered

    @pytest.mark.anyio
    async def test_aexecute_cancelled_mid_stream(self, classes, base_config, msg):
        """Test that _aexecute returns CANCELLED when cancel_event is set during streaming."""
        SubagentExecutor = classes["SubagentExecutor"]
        SubagentResult = classes["SubagentResult"]
        SubagentStatus = classes["SubagentStatus"]

        cancel_event = threading.Event()

        async def mock_astream(*args, **kwargs):
            yield {"messages": [msg.human("Task"), msg.ai("Partial", "msg-1")]}
            # Simulate cancellation during streaming
            cancel_event.set()
            yield {"messages": [msg.human("Task"), msg.ai("Should not appear", "msg-2")]}

        mock_agent = MagicMock()
        mock_agent.astream = mock_astream

        result_holder = SubagentResult(
            task_id="cancel-mid",
            trace_id="test-trace",
            status=SubagentStatus.RUNNING,
            started_at=datetime.now(),
        )
        result_holder.cancel_event = cancel_event

        executor = SubagentExecutor(
            config=base_config,
            tools=[],
            thread_id="test-thread",
        )

        with patch.object(executor, "_create_agent", return_value=mock_agent):
            result = await executor._aexecute("Task", result_holder=result_holder)

        assert result.status == SubagentStatus.CANCELLED
        assert result.error == "Cancelled by user"
        assert result.completed_at is not None

    def test_request_cancel_sets_event(self, executor_module, classes):
        """Test that request_cancel_background_task sets the cancel_event."""
        SubagentResult = classes["SubagentResult"]
        SubagentStatus = classes["SubagentStatus"]

        task_id = "test-cancel-event"
        result = SubagentResult(
            task_id=task_id,
            trace_id="test-trace",
            status=SubagentStatus.RUNNING,
            started_at=datetime.now(),
        )
        executor_module._background_tasks[task_id] = result

        assert not result.cancel_event.is_set()

        assert executor_module.request_cancel_background_task(task_id)

        assert result.cancel_event.is_set()

    def test_request_cancel_nonexistent_task_is_noop(self, executor_module):
        """Test that requesting cancellation on a nonexistent task does not raise."""
        assert not executor_module.request_cancel_background_task("nonexistent-task")

    def test_timeout_does_not_overwrite_cancelled(self, executor_module, classes):
        """Test that the real timeout handler does not overwrite CANCELLED status.

        This exercises execute_async -> _execute_with_timeout -> FuturesTimeoutError.
        The isolated worker is blocked so cancellation can win deterministically.
        """
        from concurrent.futures import ThreadPoolExecutor

        SubagentExecutor = executor_module.SubagentExecutor
        SubagentResult = executor_module.SubagentResult
        SubagentStatus = executor_module.SubagentStatus

        short_config = classes["SubagentConfig"](
            name="test-agent",
            description="Test agent",
            system_prompt="You are a test agent.",
            max_turns=10,
            timeout_seconds=0.05,  # 50ms – just enough for the future to time out
        )

        worker_entered = threading.Event()
        worker_release = threading.Event()

        def blocking_isolated_loop(task, result_holder):
            worker_entered.set()
            worker_release.wait(timeout=5)
            return result_holder

        executor = SubagentExecutor(
            config=short_config,
            tools=[],
            thread_id="test-thread",
            trace_id="test-trace",
        )
        result_holder = SubagentResult(
            task_id="cancel-wins",
            trace_id="test-trace",
            status=SubagentStatus.RUNNING,
            started_at=datetime.now(),
        )

        with patch.object(executor, "_run_with_isolated_loop", blocking_isolated_loop), ThreadPoolExecutor(max_workers=1) as pool:
            timeout_future = pool.submit(executor._execute_with_timeout, "Task", result_holder)
            assert worker_entered.wait(timeout=3), "isolated worker was never called"

            with result_holder._status_lock:
                result_holder.status = SubagentStatus.CANCELLED
                result_holder.error = "Cancelled by user"
                result_holder.completed_at = datetime.now()

            result = timeout_future.result(timeout=5)
            worker_release.set()

        assert result.status.value == SubagentStatus.CANCELLED.value
        assert result.error == "Cancelled by user"
        assert result.completed_at is not None

    def test_timeout_cancels_worker_and_preserves_timed_out_status(self, executor_module, classes):
        """A late worker completion cannot overwrite a timeout terminal state."""
        SubagentExecutor = executor_module.SubagentExecutor
        SubagentResult = executor_module.SubagentResult
        SubagentStatus = executor_module.SubagentStatus

        short_config = classes["SubagentConfig"](
            name="test-agent",
            description="Test agent",
            system_prompt="You are a test agent.",
            max_turns=10,
            timeout_seconds=0.05,
        )
        worker_entered = threading.Event()
        worker_release = threading.Event()
        worker_done = threading.Event()
        result_holder = SubagentResult(
            task_id="timeout-terminal",
            trace_id="test-trace",
            status=SubagentStatus.RUNNING,
            started_at=datetime.now(),
        )
        executor = SubagentExecutor(config=short_config, tools=[], trace_id="test-trace")

        def late_completion(task, result):
            worker_entered.set()
            worker_release.wait(timeout=5)
            executor_module._mark_execution_complete(result)
            worker_done.set()
            return result

        with patch.object(executor, "_run_with_isolated_loop", late_completion):
            result = executor._execute_with_timeout("Task", result_holder)

        assert worker_entered.is_set()
        assert result.status == SubagentStatus.TIMED_OUT
        assert result.cancel_event.is_set()

        worker_release.set()
        assert worker_done.wait(timeout=3)
        assert result.status == SubagentStatus.TIMED_OUT

    @pytest.mark.anyio
    async def test_execute_async_keeps_loop_bound_agent_on_caller_loop(
        self,
        executor_module,
        classes,
        base_config,
        msg,
    ):
        """Async background execution must not move model clients to another loop."""
        SubagentExecutor = classes["SubagentExecutor"]
        SubagentStatus = classes["SubagentStatus"]
        owner_loop = asyncio.get_running_loop()
        observed_loops = []

        class LoopBoundAgent:
            async def astream(self, *_args, **_kwargs):
                current_loop = asyncio.get_running_loop()
                if current_loop is not owner_loop:
                    raise RuntimeError("async model client is bound to a different event loop")
                observed_loops.append(current_loop)
                yield {
                    "messages": [
                        msg.human("Task"),
                        msg.ai("Same loop result", "msg-loop"),
                    ]
                }

        executor = SubagentExecutor(
            config=base_config,
            tools=[],
            thread_id="test-thread",
        )

        with patch.object(executor, "_create_agent", return_value=LoopBoundAgent()):
            task_id = executor.execute_async("Task", task_id="loop-bound-task")
            assert await executor_module.wait_for_background_task_shutdown(task_id, 3)

        result = executor_module.get_background_task_result(task_id)
        assert result is not None
        assert result.status.value == SubagentStatus.COMPLETED.value
        assert result.result == "Same loop result"
        assert observed_loops == [owner_loop]
        executor_module.cleanup_background_task(task_id)

    def test_cleanup_removes_cancelled_task(self, executor_module, classes):
        """Test that cleanup removes a CANCELLED task (terminal state)."""
        SubagentResult = classes["SubagentResult"]
        SubagentStatus = classes["SubagentStatus"]

        task_id = "test-cancelled-cleanup"
        result = SubagentResult(
            task_id=task_id,
            trace_id="test-trace",
            status=SubagentStatus.CANCELLED,
            error="Cancelled by user",
            completed_at=datetime.now(),
        )
        executor_module._background_tasks[task_id] = result

        executor_module.cleanup_background_task(task_id)

        assert task_id not in executor_module._background_tasks
