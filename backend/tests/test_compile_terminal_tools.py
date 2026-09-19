import asyncio
import json
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

from langchain.agents import create_agent
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.types import Command

from deerflow.agents.middlewares.compile_termination_middleware import CompileTerminationMiddleware
from deerflow.agents.middlewares.memory_middleware import MemoryMiddleware
from deerflow.agents.thread_state import ThreadState
from deerflow.compile.docker_runtime import ContainerCleanupResult
from deerflow.compile.schemas import BuildArtifact, BuildCommandRecord, CompileSession, VerificationResult
from deerflow.tools import bound_compile_tools
from deerflow.tools.builtins import agent_compile_tools


class SingleToolCallModel(BaseChatModel):
    calls: int = 0
    tool_name: str = "submit_build_result"

    @property
    def _llm_type(self) -> str:
        return "single-tool-call"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable:
        del tools, tool_choice, kwargs
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        self.calls += 1
        if self.calls > 1:
            raise AssertionError("The model was called after a terminal compile tool")
        response = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": self.tool_name,
                    "args": {
                        "supporting_command_id": "command-build",
                        "recipe_command_ids": ["command-build", "command-stage"],
                        "verification_command_ids": [],
                    },
                    "id": "tool-call-graph",
                    "type": "tool_call",
                }
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=response)])


def make_session() -> CompileSession:
    return CompileSession(
        session_id="session-123",
        thread_id="thread-123",
        repo_url="https://example.com/repo.git",
        branch=None,
        image="autocompiler:gcc13",
        status="verified",
        commit_sha="abc123",
        container_id="container-123",
        build_system="cmake",
        metadata_path="/sessions/thread-123/session-123/session.json",
        leadagent_repo_dir="/sessions/thread-123/session-123/workspace/repo",
        leadagent_artifacts_dir="/sessions/thread-123/session-123/artifacts",
        leadagent_logs_dir="/sessions/thread-123/session-123/logs",
        leadagent_repro_dir="/sessions/thread-123/session-123/repro",
        commands=[
            BuildCommandRecord(stage="bash", command="cmake --build build", workdir="/workspace/repo", command_id="command-build", role="build", exit_code=0),
            BuildCommandRecord(stage="bash", command="cp build/hello /artifacts/hello", workdir="/workspace/repo", command_id="command-stage", role="artifact_stage", exit_code=0),
        ],
        artifacts=[BuildArtifact(path="thread-123/session-123/artifacts/hello", artifact_type="executable", size_bytes=16504)],
        verification=VerificationResult(status="passed", artifact_count=1),
    )


def test_successful_bound_submit_returns_machine_readable_result(monkeypatch):
    session = make_session()
    submit_payload = {
        "status": "passed",
        "message": "Build artifacts accepted from /artifacts.",
        "artifacts": [{"path": "thread-123/session-123/artifacts/hello"}],
    }
    monkeypatch.setattr(bound_compile_tools, "submit_build_result_impl", lambda **_kwargs: json.dumps(submit_payload))
    submit_tool = next(tool for tool in bound_compile_tools.get_bound_compile_tools(session) if tool.name == "submit_build_result")

    result = submit_tool.func(
        supporting_command_id="command-build",
        recipe_command_ids=["command-build", "command-stage"],
        verification_command_ids=[],
    )

    assert json.loads(result) == submit_payload


def test_successful_submit_ends_react_graph_after_one_model_call(monkeypatch):
    session = make_session()
    submit_payload = {
        "status": "passed",
        "message": "Build artifacts accepted from /artifacts.",
        "artifacts": [{"path": "thread-123/session-123/artifacts/hello"}],
    }
    monkeypatch.setattr(bound_compile_tools, "submit_build_result_impl", lambda **_kwargs: json.dumps(submit_payload))
    submit_tool = next(tool for tool in bound_compile_tools.get_bound_compile_tools(session) if tool.name == "submit_build_result")
    model = SingleToolCallModel()
    agent = create_agent(model=model, tools=[submit_tool], middleware=[CompileTerminationMiddleware()])

    final_state = agent.invoke({"messages": [HumanMessage(content="Submit the completed build.")]})

    assert model.calls == 1
    assert json.loads(final_state["messages"][-1].content)["verification_status"] == "passed"


def test_successful_submit_ends_async_react_graph_after_one_model_call(monkeypatch):
    session = make_session()
    submit_payload = {
        "status": "passed",
        "message": "Build artifacts accepted from /artifacts.",
        "artifacts": [{"path": "thread-123/session-123/artifacts/hello"}],
    }
    monkeypatch.setattr(bound_compile_tools, "submit_build_result_impl", lambda **_kwargs: json.dumps(submit_payload))
    submit_tool = next(tool for tool in bound_compile_tools.get_bound_compile_tools(session) if tool.name == "submit_build_result")
    model = SingleToolCallModel()
    agent = create_agent(model=model, tools=[submit_tool], middleware=[CompileTerminationMiddleware()])

    final_state = asyncio.run(agent.ainvoke({"messages": [HumanMessage(content="Submit the completed build.")]}))

    assert model.calls == 1
    assert json.loads(final_state["messages"][-1].content)["verification_status"] == "passed"


def test_failed_bound_submit_remains_repairable(monkeypatch):
    session = make_session()
    submit_payload = {"status": "failed", "message": "No compiled artifacts", "artifacts": []}
    monkeypatch.setattr(bound_compile_tools, "submit_build_result_impl", lambda **_kwargs: json.dumps(submit_payload))
    submit_tool = next(tool for tool in bound_compile_tools.get_bound_compile_tools(session) if tool.name == "submit_build_result")

    result = submit_tool.func(
        supporting_command_id="command-build",
        recipe_command_ids=["command-build", "command-stage"],
        verification_command_ids=[],
    )

    assert isinstance(result, str)
    assert json.loads(result)["status"] == "failed"


def test_staged_artifacts_require_an_explicit_submit_call(monkeypatch):
    session = make_session()
    session.status = "inspected"
    session.post_build_supporting_command_id = "command-build"
    record = BuildCommandRecord(
        stage="bash",
        command="cp build/hello /artifacts/hello",
        workdir="/workspace/repo",
        command_id="command-stage",
        role="artifact_stage",
        exit_code=0,
    )
    command_result = SimpleNamespace(exit_code=0)
    submitted: list[str | None] = []
    submit_payload = {
        "status": "passed",
        "message": "Build artifacts and clean replay accepted.",
        "artifacts": [{"path": "thread-123/session-123/artifacts/hello"}],
    }
    monkeypatch.setattr(
        bound_compile_tools,
        "_run_container_bash_impl",
        lambda **_kwargs: (command_result, "command completed", record),
    )

    def submit(*, supporting_command_id, **_kwargs):
        submitted.append(supporting_command_id)
        return json.dumps(submit_payload)

    monkeypatch.setattr(bound_compile_tools, "submit_build_result_impl", submit)
    run_tool = next(tool for tool in bound_compile_tools.get_bound_compile_tools(session) if tool.name == "run_container_bash")

    result = run_tool.func(command="cp build/hello /artifacts/hello", command_role="artifact_stage")

    assert submitted == []
    assert result == "command completed"


def test_invalid_submit_response_releases_post_build_fence(monkeypatch):
    session = make_session()
    session.post_build_supporting_command_id = "command-build"
    released: list[str] = []
    monkeypatch.setattr(bound_compile_tools, "_reload_session", lambda current: current)
    monkeypatch.setattr(bound_compile_tools, "_clear_post_build_phase", lambda _session, *, reason: released.append(reason))
    monkeypatch.setattr(bound_compile_tools, "submit_build_result_impl", lambda **_kwargs: "not-json")

    result = bound_compile_tools._submit_with_post_build_phase(
        session,
        supporting_command_id="command-build",
        recipe_command_ids=["command-build", "command-stage"],
        verification_command_ids=[],
    )

    assert result == "not-json"
    assert released == ["submit_invalid_response"]


def test_post_build_fence_blocks_reconfigure_rebuild_and_manual_replay(monkeypatch):
    session = make_session()
    session.post_build_supporting_command_id = "command-build"
    session.post_build_commands_remaining = 2
    monkeypatch.setattr(bound_compile_tools, "_reload_session", lambda current: current)

    assert "successful build" in bound_compile_tools._post_build_rejection(
        session,
        command="cmake -S . -B build-again",
        command_role="configure",
    )
    assert "successful build" in bound_compile_tools._post_build_rejection(
        session,
        command="make -j2",
        command_role="build",
    )
    assert "successful build" in bound_compile_tools._post_build_rejection(
        session,
        command="make -j2 && cp build/hello /artifacts/hello",
        command_role="artifact_stage",
    )
    assert "successful build" in bound_compile_tools._post_build_rejection(
        session,
        command="make clean && cp build/hello /artifacts/hello",
        command_role="artifact_stage",
    )
    assert "successful build" in bound_compile_tools._post_build_rejection(
        session,
        command="apt-get install -y texinfo",
        command_role="dependency",
    )
    assert "successful build" in bound_compile_tools._post_build_rejection(
        session,
        command="bash -lc 'apt-get install -y texinfo'",
        command_role="dependency",
    )
    assert (
        bound_compile_tools._post_build_rejection(
            session,
            command="make install DESTDIR=/artifacts",
            command_role="artifact_stage",
        )
        is None
    )
    assert "/repro" in bound_compile_tools._post_build_rejection(
        session,
        command="bash /repro/build.sh",
        command_role="diagnostic",
    )

    session.post_build_commands_remaining = 0
    assert "budget is exhausted" in bound_compile_tools._post_build_rejection(
        session,
        command="find build -type f",
        command_role="diagnostic",
    )
    assert (
        bound_compile_tools._post_build_rejection(
            session,
            command="cp build/hello /artifacts/hello",
            command_role="artifact_stage",
        )
        is None
    )


def test_run_container_bash_never_ends_the_compiler_graph():
    request = SimpleNamespace(tool_call={"name": "run_container_bash", "id": "tool-stage", "args": {}})
    tool_message = ToolMessage(
        content="command_id=command-stage\ncommand_role=artifact_stage\nexit_code=0",
        tool_call_id="tool-stage",
        name="run_container_bash",
    )

    terminal = CompileTerminationMiddleware().wrap_tool_call(request, lambda _request: tool_message)

    assert terminal is tool_message


def test_compile_session_skips_post_run_memory_model_work(monkeypatch):
    monkeypatch.setattr(
        "deerflow.agents.middlewares.memory_middleware.get_memory_queue",
        lambda: (_ for _ in ()).throw(AssertionError("compile runs must not enqueue memory updates")),
    )

    result = MemoryMiddleware().after_agent(
        {
            "messages": [HumanMessage(content="Build the repository")],
            "compile_session_id": "session-123",
        },
        SimpleNamespace(context={"thread_id": "thread-123"}),
    )

    assert result is None


def test_finalize_cleans_container_then_ends_lead_with_deterministic_summary(monkeypatch):
    session = make_session()
    session.artifacts = [
        BuildArtifact(
            path="thread-123/session-123/artifacts/lib/libfmt.a",
            source_path="/artifacts/lib/libfmt.a",
            artifact_type="static_library",
            size_bytes=253264,
            sha256="a" * 64,
        ),
        BuildArtifact(
            path="thread-123/session-123/artifacts/lib/libfmt-c.a",
            source_path="/artifacts/lib/libfmt-c.a",
            artifact_type="static_library",
            size_bytes=5642,
            sha256="b" * 64,
        ),
        *[
            BuildArtifact(
                path=f"thread-123/session-123/artifacts/include/fmt/header-{index}.h",
                source_path=f"/artifacts/include/fmt/header-{index}.h",
                artifact_type="support_file",
                size_bytes=index,
                sha256=f"{index:064x}",
            )
            for index in range(16)
        ],
        BuildArtifact(
            path="thread-123/session-123/artifacts/LICENSE",
            source_path="/artifacts/LICENSE",
            artifact_type="support_file",
            size_bytes=1100,
            sha256="c" * 64,
        ),
    ]
    events: list[str] = []

    def cleanup_and_finalize(*, session: CompileSession):
        assert session is session_arg
        events.append("cleanup")
        events.append("finalize")
        session.status = "completed"
        return session, ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    session_arg = session
    monkeypatch.setattr(agent_compile_tools, "get_bound_session", lambda session_id, thread_id: session)
    monkeypatch.setattr(agent_compile_tools, "cleanup_and_finalize_compile_session_impl", cleanup_and_finalize)
    runtime = SimpleNamespace(
        state={agent_compile_tools.COMPILE_SESSION_STATE_KEY: session.session_id},
        context={"thread_id": session.thread_id},
        config={"configurable": {}},
    )

    result = agent_compile_tools.finalize_session.func(runtime=runtime)

    assert events == ["cleanup", "finalize"]
    final_payload = json.loads(result)
    assert final_payload["status"] == "completed"
    assert final_payload["session_id"] == session.session_id
    assert final_payload["commands"] == ["cmake --build build", "cp build/hello /artifacts/hello"]
    assert final_payload["verification"] == "passed"
    assert final_payload["container_stopped"] is True
    assert final_payload["container_removed"] is True
    assert final_payload["error"] is None

    todos = [
        {"status": "completed", "content": "Clone repository"},
        {"status": "in_progress", "content": "Clean up the compile session and summarize results"},
        {"status": "pending", "content": "Optional follow-up"},
    ]
    request = SimpleNamespace(
        tool_call={"name": "finalize_session", "id": "tool-call-3", "args": {}},
        state={"todos": todos},
    )
    tool_message = ToolMessage(content=result, tool_call_id="tool-call-3", name="finalize_session")
    terminal = CompileTerminationMiddleware().wrap_tool_call(request, lambda _: tool_message)
    assert isinstance(terminal, Command)
    assert terminal.update["compile_terminal"] is True
    assert terminal.update["messages"][0] is tool_message
    assert json.loads(terminal.update["messages"][0].content) == final_payload
    assert isinstance(terminal.update["messages"][-1], AIMessage)
    summary = terminal.update["messages"][-1].content
    assert summary.startswith("## 编译会话已完成")
    assert "`session-123`" in summary
    assert "`abc123`" in summary
    assert "候选验证：通过" in summary
    assert "干净重放：未运行" in summary
    assert "编译产物：2" in summary
    assert "`lib/libfmt.a`" in summary
    assert "`lib/libfmt-c.a`" in summary
    assert "辅助文件：17" in summary
    assert "`include/fmt/`：16 个文件" in summary
    assert "`LICENSE`：1 个文件" in summary
    assert "thread-123/session-123" not in summary
    assert terminal.update["todos"] == [
        {"status": "completed", "content": "Clone repository"},
        {"status": "completed", "content": "Clean up the compile session and summarize results"},
        {"status": "pending", "content": "Optional follow-up"},
    ]
    assert terminal.update["todos"] is not todos

    jump = CompileTerminationMiddleware().before_model(
        {"messages": terminal.update["messages"], "compile_terminal": True},
        SimpleNamespace(),
    )
    assert jump == {"compile_terminal": False, "jump_to": "end"}


def test_build_system_mismatch_cleans_session_and_stops_before_compiler(monkeypatch):
    session = make_session()
    session.status = "source_ready"
    session.build_system = None
    session.finalized_at = None
    recorded_events: list[tuple[str, dict]] = []
    cleanup_calls: list[str] = []

    monkeypatch.setattr(agent_compile_tools, "get_bound_session", lambda session_id, thread_id: session)

    def inspect_build_system(*, session: CompileSession):
        session.build_system = "cmake"
        return "cmake", [("cmake", "CMakeLists.txt")], ["cmake -S . -B build"]

    def cleanup_and_finalize(*, session: CompileSession, interrupted_status: str, error: str):
        cleanup_calls.append(session.session_id)
        assert interrupted_status == "failed"
        assert "selected build system autotools" in error
        session.status = "failed"
        session.finalized_at = "2026-07-19T00:00:00+00:00"
        return session, ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    monkeypatch.setattr(agent_compile_tools, "inspect_build_system_impl", inspect_build_system)
    monkeypatch.setattr(agent_compile_tools, "cleanup_and_finalize_compile_session_impl", cleanup_and_finalize)
    monkeypatch.setattr(
        agent_compile_tools,
        "get_active_experiment",
        lambda _thread_id: SimpleNamespace(policy=SimpleNamespace(selected_build_system="autotools")),
    )
    monkeypatch.setattr(
        agent_compile_tools,
        "record_experiment_event",
        lambda _thread_id, event, **payload: recorded_events.append((event, payload)),
    )
    runtime = SimpleNamespace(
        state={agent_compile_tools.COMPILE_SESSION_STATE_KEY: session.session_id},
        context={"thread_id": session.thread_id},
        config={"configurable": {}},
    )

    result = agent_compile_tools.identify_build_system.func(
        runtime=runtime,
        tool_call_id="tool-build-system-mismatch",
    )

    assert cleanup_calls == [session.session_id]
    assert result.update["compile_terminal"] is True
    assert agent_compile_tools.COMPILE_BUILD_SYSTEM_STATE_KEY not in result.update
    assert "selected build system autotools" in result.update["messages"][0].content
    assert [event for event, _payload in recorded_events] == [
        "build.system_checked",
        "protocol.deviation",
    ]
    assert recorded_events[-1][1]["compiler_allowed"] is False
    assert recorded_events[-1][1]["session_finalized"] is True


def test_multi_entry_repository_selects_manifest_build_path(monkeypatch):
    session = make_session()
    session.status = "source_ready"
    session.build_system = None
    session.selected_build_system = None
    recorded_events: list[tuple[str, dict]] = []
    saved_sessions: list[CompileSession] = []

    monkeypatch.setattr(agent_compile_tools, "get_bound_session", lambda session_id, thread_id: session)

    def inspect_build_system(*, session: CompileSession):
        session.build_system = "cmake"
        session.build_system_capabilities = ["cmake", "make"]
        return "cmake", [("cmake", "CMakeLists.txt"), ("make", "Makefile")], ["cmake --build build"]

    monkeypatch.setattr(agent_compile_tools, "inspect_build_system_impl", inspect_build_system)
    monkeypatch.setattr(
        agent_compile_tools,
        "get_compile_services",
        lambda: SimpleNamespace(manager=SimpleNamespace(save_session=lambda current: saved_sessions.append(current))),
    )
    monkeypatch.setattr(
        agent_compile_tools,
        "get_active_experiment",
        lambda _thread_id: SimpleNamespace(policy=SimpleNamespace(selected_build_system="make")),
    )
    monkeypatch.setattr(
        agent_compile_tools,
        "record_experiment_event",
        lambda _thread_id, event, **payload: recorded_events.append((event, payload)),
    )
    runtime = SimpleNamespace(
        state={agent_compile_tools.COMPILE_SESSION_STATE_KEY: session.session_id},
        context={"thread_id": session.thread_id},
        config={"configurable": {}},
    )

    result = agent_compile_tools.identify_build_system.func(
        runtime=runtime,
        tool_call_id="tool-build-system-selection",
    )

    assert "compile_terminal" not in result.update
    assert result.update[agent_compile_tools.COMPILE_BUILD_SYSTEM_STATE_KEY] == "make"
    assert session.build_system == "cmake"
    assert session.build_system_capabilities == ["cmake", "make"]
    assert session.selected_build_system == "make"
    assert saved_sessions == [session]
    assert [event for event, _payload in recorded_events] == ["build.system_checked"]
    assert recorded_events[0][1]["observed_build_system"] == "cmake"
    assert recorded_events[0][1]["detected_build_systems"] == ["cmake", "make"]
    assert recorded_events[0][1]["selected_build_system"] == "make"
    assert recorded_events[0][1]["compiler_allowed"] is True


def test_finalize_ends_lead_graph_after_one_model_call(monkeypatch):
    session = make_session()
    events: list[str] = []

    def cleanup_and_finalize(*, session: CompileSession):
        events.append("cleanup")
        events.append("finalize")
        session.status = "completed"
        return session, ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    monkeypatch.setattr(agent_compile_tools, "get_bound_session", lambda session_id, thread_id: session)
    monkeypatch.setattr(agent_compile_tools, "cleanup_and_finalize_compile_session_impl", cleanup_and_finalize)
    model = SingleToolCallModel(tool_name="finalize_session")
    agent = create_agent(
        model=model,
        tools=[agent_compile_tools.finalize_session],
        middleware=[CompileTerminationMiddleware()],
        state_schema=ThreadState,
    )

    final_state = agent.invoke(
        {
            "messages": [HumanMessage(content="Finalize the verified compile session.")],
            "compile_session_id": session.session_id,
            "artifacts": [],
            "todos": [{"status": "in_progress", "content": "Finalize compile session"}],
            "viewed_images": {},
        },
        config={"configurable": {"thread_id": session.thread_id}},
    )

    assert model.calls == 1
    assert events == ["cleanup", "finalize"]
    assert final_state["messages"][-1].content.startswith("## 编译会话已完成")
    assert final_state["todos"] == [{"status": "completed", "content": "Finalize compile session"}]


def test_failed_finalize_summary_preserves_in_progress_todos():
    payload = {
        "status": "failed",
        "session_id": "session-failed",
        "commit_sha": "def456",
        "build_system": "cmake",
        "verification": "failed",
        "replay_verification": "not_run",
        "artifacts": [],
        "container_stopped": True,
        "container_removed": True,
        "error": "No recognized compiled artifacts were found.",
    }
    todos = [{"status": "in_progress", "content": "Repair failed verification"}]
    request = SimpleNamespace(
        tool_call={"name": "finalize_session", "id": "tool-call-failed", "args": {}},
        state={"todos": todos},
    )
    tool_message = ToolMessage(
        content=json.dumps(payload),
        tool_call_id="tool-call-failed",
        name="finalize_session",
    )

    terminal = CompileTerminationMiddleware().wrap_tool_call(request, lambda _: tool_message)

    assert isinstance(terminal, Command)
    assert terminal.update["messages"][0] is tool_message
    assert terminal.update["messages"][-1].content.startswith("## 编译会话失败")
    assert "No recognized compiled artifacts were found." in terminal.update["messages"][-1].content
    assert "todos" not in terminal.update
    assert todos == [{"status": "in_progress", "content": "Repair failed verification"}]


def test_finalize_cleans_container_but_fails_unverified_session(monkeypatch):
    session = make_session()
    session.status = "verification_failed"
    session.verification = VerificationResult(status="failed", artifact_count=0, failed_checks=1)
    session.artifacts = []
    session.error = "No recognized compiled artifacts were found."
    events: list[str] = []

    def cleanup_and_finalize(*, session: CompileSession):
        events.append("cleanup")
        events.append("finalize")
        session.status = "failed"
        return session, ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    monkeypatch.setattr(agent_compile_tools, "get_bound_session", lambda session_id, thread_id: session)
    monkeypatch.setattr(agent_compile_tools, "cleanup_and_finalize_compile_session_impl", cleanup_and_finalize)
    runtime = SimpleNamespace(
        state={agent_compile_tools.COMPILE_SESSION_STATE_KEY: session.session_id},
        context={"thread_id": session.thread_id},
        config={"configurable": {}},
    )

    result = json.loads(agent_compile_tools.finalize_session.func(runtime=runtime))

    assert events == ["cleanup", "finalize"]
    assert result["status"] == "failed"
    assert result["verification"] == "failed"
    assert result["artifacts"] == []
    assert result["container_removed"] is True
    assert result["error"] == "No recognized compiled artifacts were found."


def test_finalize_marks_verified_session_failed_when_container_cleanup_fails(monkeypatch):
    session = make_session()

    def cleanup_and_finalize(*, session: CompileSession):
        session.status = "failed"
        session.error = "Compile container cleanup failed."
        return session, ContainerCleanupResult(succeeded=False, stopped=False, removed=False)

    monkeypatch.setattr(agent_compile_tools, "get_bound_session", lambda session_id, thread_id: session)
    monkeypatch.setattr(agent_compile_tools, "cleanup_and_finalize_compile_session_impl", cleanup_and_finalize)
    runtime = SimpleNamespace(
        state={agent_compile_tools.COMPILE_SESSION_STATE_KEY: session.session_id},
        context={"thread_id": session.thread_id},
        config={"configurable": {}},
    )

    result = json.loads(agent_compile_tools.finalize_session.func(runtime=runtime))

    assert result["status"] == "failed"
    assert result["verification"] == "passed"
    assert result["container_stopped"] is False
    assert result["container_removed"] is False
    assert result["error"] == "Compile container cleanup failed."
    assert session.finalized_at is None
