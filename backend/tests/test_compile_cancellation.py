import asyncio
import importlib
import sys
import threading
from unittest.mock import MagicMock

import pytest

from deerflow.compile.docker_runtime import ContainerCleanupResult
from deerflow.compile.schemas import CompileSession
from deerflow.subagents.config import SubagentConfig

task_tool_module = importlib.import_module("deerflow.tools.builtins.task_tool")

_EXECUTOR_IMPORT_MOCKS = [
    "deerflow.agents",
    "deerflow.agents.thread_state",
    "deerflow.agents.middlewares",
    "deerflow.agents.middlewares.thread_data_middleware",
    "deerflow.models",
]


@pytest.fixture
def real_executor_module():
    original_executor = sys.modules.get("deerflow.subagents.executor")
    original_modules = {name: sys.modules.get(name) for name in _EXECUTOR_IMPORT_MOCKS}
    sys.modules.pop("deerflow.subagents.executor", None)
    for name in _EXECUTOR_IMPORT_MOCKS:
        sys.modules[name] = MagicMock()
    module = importlib.import_module("deerflow.subagents.executor")
    try:
        yield module
    finally:
        sys.modules.pop("deerflow.subagents.executor", None)
        if original_executor is not None:
            sys.modules["deerflow.subagents.executor"] = original_executor
        for name, original in original_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


class BlockingAgent:
    def __init__(self, started: threading.Event, stopped: threading.Event):
        self.started = started
        self.stopped = stopped

    async def astream(self, *args, **kwargs):
        del args, kwargs
        self.started.set()
        try:
            await asyncio.Event().wait()
            yield {}
        finally:
            self.stopped.set()


def make_executor(executor_module, *, timeout_seconds: int, started: threading.Event, stopped: threading.Event):
    executor = executor_module.SubagentExecutor(
        config=SubagentConfig(
            name="compiler",
            description="test compiler",
            system_prompt="test",
            max_turns=10,
            timeout_seconds=timeout_seconds,
        ),
        tools=[],
    )
    executor._create_agent = lambda: BlockingAgent(started, stopped)
    return executor


def test_background_subagent_cancel_stops_isolated_worker_and_does_not_reinsert_registry_entry(real_executor_module):
    async def scenario() -> None:
        started = threading.Event()
        stopped = threading.Event()
        executor = make_executor(real_executor_module, timeout_seconds=30, started=started, stopped=stopped)
        task_id = executor.execute_async("block", task_id="cancel-task")

        started_in_time = await asyncio.to_thread(started.wait, 3)
        initial_result = real_executor_module.get_background_task_result(task_id)
        assert started_in_time, (initial_result.status if initial_result else None, initial_result.error if initial_result else None)
        assert real_executor_module.request_cancel_background_task(task_id) is True
        assert await real_executor_module.wait_for_background_task_shutdown(task_id, 3)
        result = real_executor_module.get_background_task_result(task_id)
        assert result is not None
        assert result.status == real_executor_module.SubagentStatus.CANCELLED
        assert stopped.is_set()

        real_executor_module.cleanup_background_task(task_id)
        await asyncio.sleep(0.05)
        assert real_executor_module.get_background_task_result(task_id) is None

    asyncio.run(scenario())


def test_background_subagent_timeout_cannot_be_overwritten_by_late_completion(real_executor_module):
    async def scenario() -> None:
        started = threading.Event()
        stopped = threading.Event()
        executor = make_executor(real_executor_module, timeout_seconds=1, started=started, stopped=stopped)
        task_id = executor.execute_async("block", task_id="timeout-task")

        started_in_time = await asyncio.to_thread(started.wait, 3)
        initial_result = real_executor_module.get_background_task_result(task_id)
        assert started_in_time, (initial_result.status if initial_result else None, initial_result.error if initial_result else None)
        deadline = asyncio.get_running_loop().time() + 4
        result = real_executor_module.get_background_task_result(task_id)
        while result is not None and result.status != real_executor_module.SubagentStatus.TIMED_OUT:
            assert asyncio.get_running_loop().time() < deadline
            await asyncio.sleep(0.05)
            result = real_executor_module.get_background_task_result(task_id)

        assert result is not None
        assert result.status == real_executor_module.SubagentStatus.TIMED_OUT
        assert await real_executor_module.wait_for_background_task_shutdown(task_id, 3)
        await asyncio.sleep(0.05)
        assert result.status == real_executor_module.SubagentStatus.TIMED_OUT
        assert stopped.is_set()
        real_executor_module.cleanup_background_task(task_id)

    asyncio.run(scenario())


def test_timeout_terminal_transition_blocks_boundary_completion(real_executor_module):
    result = real_executor_module.SubagentResult(
        task_id="boundary-task",
        trace_id="boundary-trace",
        status=real_executor_module.SubagentStatus.RUNNING,
    )

    assert real_executor_module._mark_terminal(
        result,
        real_executor_module.SubagentStatus.TIMED_OUT,
        "deadline reached",
    )
    real_executor_module._mark_execution_complete(result)

    assert result.status == real_executor_module.SubagentStatus.TIMED_OUT
    assert result.error == "deadline reached"


def test_compiler_task_termination_stops_worker_before_finalizing_session(monkeypatch):
    session = CompileSession(
        session_id="session-123",
        thread_id="thread-123",
        repo_url="https://example.com/repo.git",
        branch=None,
        image="autocompiler:gcc13",
        status="inspected",
        container_id="container-123",
    )
    events: list[str] = []

    async def load_session(*, session_id: str, thread_id: str):
        assert session_id == session.session_id
        assert thread_id == session.thread_id
        events.append("load")
        return session

    def stop_container(session_arg):
        assert session_arg is session
        events.append("stop")
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    def cleanup_container(*, session: CompileSession):
        return session, stop_container(session)

    async def wait_for_shutdown(task_id: str, timeout_seconds: float):
        assert task_id == "task-123"
        assert timeout_seconds == 30
        events.append("wait")
        return True

    def finalize(*, session: CompileSession, status: str, summary: str, error: str):
        events.append("finalize")
        assert status == "timed_out"
        assert summary == "compiler timeout"
        assert error == "compiler timeout"
        session.status = status
        return session

    monkeypatch.setattr(
        "deerflow.agents.middlewares.tool_error_handling_middleware.load_bound_session_async",
        load_session,
    )
    monkeypatch.setattr("deerflow.compile.operations.cleanup_compile_session_container_impl", cleanup_container)
    monkeypatch.setattr("deerflow.compile.operations.finalize_compile_session_impl", finalize)
    monkeypatch.setattr(task_tool_module, "request_cancel_background_task", lambda task_id: events.append("cancel") or True)
    monkeypatch.setattr(task_tool_module, "wait_for_background_task_shutdown", wait_for_shutdown)
    monkeypatch.setattr(task_tool_module, "cleanup_background_task", lambda task_id: events.append("registry_cleanup"))

    stopped = asyncio.run(
        task_tool_module._cancel_and_reap_task(
            task_id="task-123",
            subagent_type="compiler",
            compile_state={task_tool_module.COMPILE_SESSION_STATE_KEY: session.session_id},
            thread_id=session.thread_id,
            terminal_status="timed_out",
            error="compiler timeout",
            shutdown_timeout_seconds=30,
        )
    )

    assert stopped is True
    assert events == ["cancel", "load", "stop", "wait", "load", "finalize", "registry_cleanup"]


def test_compiler_model_cannot_lower_server_owned_turn_limit():
    config = SubagentConfig(
        name="compiler",
        description="compiler",
        system_prompt="test",
        max_turns=36,
    )

    compiler = task_tool_module._apply_max_turns_override(
        config,
        subagent_type="compiler",
        requested_max_turns=10,
    )
    general = task_tool_module._apply_max_turns_override(
        config,
        subagent_type="general-purpose",
        requested_max_turns=10,
    )

    assert compiler.max_turns == 36
    assert general.max_turns == 10
