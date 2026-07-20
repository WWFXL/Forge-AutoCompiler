import asyncio
import importlib
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from deerflow.compile import operations
from deerflow.compile.docker_runtime import ContainerCleanupResult
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.operations import CompileOperationsServices
from deerflow.compile.schemas import CompileSession, ReplayVerificationResult
from deerflow.config.paths import Paths
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


def test_compiler_task_termination_stops_worker_before_finalizing_session(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(
        paths=Paths(
            base_dir=tmp_path / ".deer-flow",
            workspace_root=tmp_path / "service-workspace",
            host_workspace_root=str(tmp_path / "host-workspace"),
        )
    )
    session = manager.create_session(
        session_id="session-123",
        thread_id="thread-123",
        repo_url="https://example.com/repo.git",
    )
    session.status = "inspected"
    session.container_id = "container-123"
    session.container_name = "compile-container-123"
    session.image_id = f"sha256:{'1' * 64}"
    session.replay_attempts.append(
        ReplayVerificationResult(
            attempt_id="replay-attempt",
            status="running",
            image=session.image,
            image_id=session.image_id,
            commit_sha="a" * 40,
            recipe_sha256="b" * 64,
            timeout_seconds=30,
            container_id="replay-container-123",
            container_name="replay-name-123",
        )
    )
    manager.save_session(session)
    events: list[str] = []

    async def load_session(*, session_id: str, thread_id: str):
        assert session_id == session.session_id
        assert thread_id == session.thread_id
        events.append("load")
        return manager.load_session(session_id, thread_id)

    def stop_container(session_arg: CompileSession):
        assert session_arg.container_id == session.container_id
        events.append("stop")
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    def stop_replay_container(
        session_arg: CompileSession,
        handle=None,
        *,
        container_id: str | None = None,
        container_name: str | None = None,
    ):
        assert handle is None
        assert session_arg.session_id == session.session_id
        assert container_id == "replay-container-123"
        assert container_name == "replay-name-123"
        events.append("stop_replay")
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

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
    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(
            manager=manager,
            runtime=SimpleNamespace(
                stop_and_remove_container=stop_container,
                stop_and_remove_replay_container=stop_replay_container,
            ),
        ),
    )
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
    assert events == [
        "cancel",
        "load",
        "stop_replay",
        "stop",
        "wait",
        "load",
        "stop",
        "finalize",
        "registry_cleanup",
    ]
    replay_attempt = manager.load_session(session.session_id, session.thread_id).replay_attempts[-1]
    assert replay_attempt.status == "cancelled"
    assert replay_attempt.failure_classification == "cancelled"
    assert replay_attempt.cleanup_succeeded is True
    assert replay_attempt.timeout_seconds == 30
    assert replay_attempt.duration_seconds is not None
    assert any(check.name == "parent_container_cleanup" and check.passed for check in replay_attempt.checks)
    workflow_log = manager.workflow_log_path(manager.load_session(session.session_id, session.thread_id)).read_text(encoding="utf-8")
    assert '"event": "replay.completed"' in workflow_log
    assert '"completed_by": "parent_cleanup"' in workflow_log


def test_compiler_cancellation_rejects_late_worker_metadata_without_repeating_successful_replay_cleanup(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(
        paths=Paths(
            base_dir=tmp_path / ".deer-flow",
            workspace_root=tmp_path / "service-workspace",
            host_workspace_root=str(tmp_path / "host-workspace"),
        )
    )
    session = manager.create_session(
        session_id="session-race",
        thread_id="thread-race",
        repo_url="https://example.com/repo.git",
    )
    session.container_id = "compile-container-race"
    session.container_name = "compile-name-race"
    session.replay_attempts.append(
        ReplayVerificationResult(
            attempt_id="attempt-race",
            status="running",
            image=session.image,
            image_id=f"sha256:{'1' * 64}",
            commit_sha="a" * 40,
            recipe_sha256="b" * 64,
            container_name="replay-name-race",
        )
    )
    manager.save_session(session)
    replay_cleanup_ids: list[str | None] = []
    events: list[str] = []

    async def load_session(*, session_id: str, thread_id: str):
        events.append("load")
        return manager.load_session(session_id, thread_id)

    def stop_compile(_session: CompileSession):
        events.append("stop_compile")
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    def stop_replay(
        _session: CompileSession,
        handle=None,
        *,
        container_id: str | None = None,
        container_name: str | None = None,
    ):
        assert handle is None
        assert container_name == "replay-name-race"
        replay_cleanup_ids.append(container_id)
        events.append("stop_replay")
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    async def wait_for_shutdown(_task_id: str, _timeout_seconds: float):
        events.append("wait")
        stale_worker_state = manager.load_session(session.session_id, session.thread_id)
        attempt = stale_worker_state.replay_attempts[-1]
        attempt.status = "running"
        attempt.failure_classification = None
        attempt.cleanup_succeeded = None
        attempt.container_id = "container-created-after-first-cleanup"
        manager.save_session(stale_worker_state)
        return True

    def finalize(*, session: CompileSession, **_kwargs):
        events.append("finalize")
        return session

    monkeypatch.setattr(
        "deerflow.agents.middlewares.tool_error_handling_middleware.load_bound_session_async",
        load_session,
    )
    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(
            manager=manager,
            runtime=SimpleNamespace(
                stop_and_remove_container=stop_compile,
                stop_and_remove_replay_container=stop_replay,
            ),
        ),
    )
    monkeypatch.setattr("deerflow.compile.operations.finalize_compile_session_impl", finalize)
    monkeypatch.setattr(task_tool_module, "request_cancel_background_task", lambda _task_id: True)
    monkeypatch.setattr(task_tool_module, "wait_for_background_task_shutdown", wait_for_shutdown)
    monkeypatch.setattr(task_tool_module, "cleanup_background_task", lambda _task_id: events.append("registry_cleanup"))

    stopped = asyncio.run(
        task_tool_module._cancel_and_reap_task(
            task_id="task-race",
            subagent_type="compiler",
            compile_state={task_tool_module.COMPILE_SESSION_STATE_KEY: session.session_id},
            thread_id=session.thread_id,
            terminal_status="cancelled",
            error="parent cancelled",
            shutdown_timeout_seconds=30,
        )
    )

    assert stopped is True
    assert replay_cleanup_ids == [None]
    assert events == [
        "load",
        "stop_replay",
        "stop_compile",
        "wait",
        "load",
        "stop_compile",
        "finalize",
        "registry_cleanup",
    ]
    replay_attempt = manager.load_session(session.session_id, session.thread_id).replay_attempts[-1]
    assert replay_attempt.status == "cancelled"
    assert replay_attempt.failure_classification == "cancelled"
    assert replay_attempt.cleanup_succeeded is True


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
