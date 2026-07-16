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
            tool_calls=[{"name": self.tool_name, "args": {}, "id": "tool-call-graph", "type": "tool_call"}],
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
        commands=[BuildCommandRecord(stage="build", command="cmake --build build", workdir="/workspace/repo")],
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
    monkeypatch.setattr(bound_compile_tools, "submit_build_result_impl", lambda session: json.dumps(submit_payload))
    submit_tool = next(tool for tool in bound_compile_tools.get_bound_compile_tools(session) if tool.name == "submit_build_result")

    result = submit_tool.func()

    assert json.loads(result) == submit_payload


def test_successful_submit_ends_react_graph_after_one_model_call(monkeypatch):
    session = make_session()
    submit_payload = {
        "status": "passed",
        "message": "Build artifacts accepted from /artifacts.",
        "artifacts": [{"path": "thread-123/session-123/artifacts/hello"}],
    }
    monkeypatch.setattr(bound_compile_tools, "submit_build_result_impl", lambda session: json.dumps(submit_payload))
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
    monkeypatch.setattr(bound_compile_tools, "submit_build_result_impl", lambda session: json.dumps(submit_payload))
    submit_tool = next(tool for tool in bound_compile_tools.get_bound_compile_tools(session) if tool.name == "submit_build_result")
    model = SingleToolCallModel()
    agent = create_agent(model=model, tools=[submit_tool], middleware=[CompileTerminationMiddleware()])

    final_state = asyncio.run(agent.ainvoke({"messages": [HumanMessage(content="Submit the completed build.")]}))

    assert model.calls == 1
    assert json.loads(final_state["messages"][-1].content)["verification_status"] == "passed"


def test_failed_bound_submit_remains_repairable(monkeypatch):
    session = make_session()
    submit_payload = {"status": "failed", "message": "No compiled artifacts", "artifacts": []}
    monkeypatch.setattr(bound_compile_tools, "submit_build_result_impl", lambda session: json.dumps(submit_payload))
    submit_tool = next(tool for tool in bound_compile_tools.get_bound_compile_tools(session) if tool.name == "submit_build_result")

    result = submit_tool.func()

    assert isinstance(result, str)
    assert json.loads(result)["status"] == "failed"


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
    assert final_payload["commands"] == ["cmake --build build"]
    assert final_payload["verification"] == "passed"
    assert final_payload["container_stopped"] is True
    assert final_payload["container_removed"] is True
    assert final_payload["error"] is None

    request = SimpleNamespace(tool_call={"name": "finalize_session", "id": "tool-call-3", "args": {}})
    tool_message = ToolMessage(content=result, tool_call_id="tool-call-3", name="finalize_session")
    terminal = CompileTerminationMiddleware().wrap_tool_call(request, lambda _: tool_message)
    assert isinstance(terminal, Command)
    assert terminal.update["compile_terminal"] is True
    assert isinstance(terminal.update["messages"][-1], AIMessage)
    assert json.loads(terminal.update["messages"][-1].content) == final_payload

    jump = CompileTerminationMiddleware().before_model(
        {"messages": terminal.update["messages"], "compile_terminal": True},
        SimpleNamespace(),
    )
    assert jump == {"compile_terminal": False, "jump_to": "end"}


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
            "viewed_images": {},
        },
        config={"configurable": {"thread_id": session.thread_id}},
    )

    assert model.calls == 1
    assert events == ["cleanup", "finalize"]
    assert json.loads(final_state["messages"][-1].content)["container_removed"] is True


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
