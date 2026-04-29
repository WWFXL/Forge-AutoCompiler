from __future__ import annotations

from typing import Annotated

from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.compile.operations import clone_repository_impl, finalize_compile_session_impl, get_bound_session, get_compile_services, inspect_build_system_impl, prepare_compile_session_impl

COMPILE_SESSION_STATE_KEY = "compile_session_id"
COMPILE_CONTAINER_STATE_KEY = "compile_container_id"
COMPILE_BUILD_SYSTEM_STATE_KEY = "compile_build_system"
COMPILE_CONTAINER_REPO_PATH = "/workspace/repo"


def _get_thread_id(runtime: ToolRuntime[ContextT, ThreadState]) -> str:
    thread_id = runtime.context.get("thread_id") if runtime.context else None
    if thread_id is None:
        thread_id = runtime.config.get("configurable", {}).get("thread_id")
    return thread_id or "default"


def _get_state_value(runtime: ToolRuntime[ContextT, ThreadState], key: str) -> str | None:
    state = runtime.state or {}
    context = runtime.context or {}
    return state.get(key) or context.get(key)


def _build_compile_state_update(
    *,
    session_id: str,
    container_id: str | None,
    build_system: str | None = None,
) -> dict[str, str]:
    update: dict[str, str] = {
        COMPILE_SESSION_STATE_KEY: session_id,
    }
    if container_id:
        update[COMPILE_CONTAINER_STATE_KEY] = container_id
    if build_system:
        update[COMPILE_BUILD_SYSTEM_STATE_KEY] = build_system
    return update


@tool("prepare_compile_session", parse_docstring=True)
def prepare_compile_session(
    runtime: ToolRuntime[ContextT, ThreadState],
    repo_url: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    branch: str | None = None,
) -> Command:
    """Prepare a compile session and container without cloning the repository.

    Use this as the first step in the retry-friendly compile flow. After this,
    call `clone_repository()` and retry only that step when network cloning fails.

    Args:
        repo_url: Git repository URL to compile.
        branch: Optional branch associated with the repository.
    """
    session = prepare_compile_session_impl(
        thread_id=_get_thread_id(runtime),
        repo_url=repo_url,
        branch=branch,
    )
    message = (
        "Compile session prepared. Next call clone_repository() using the bound session. "
        f"session_id={session.session_id}, container_id={session.container_id}, container_repo_path={COMPILE_CONTAINER_REPO_PATH}"
    )
    update = _build_compile_state_update(
        session_id=session.session_id,
        container_id=session.container_id,
    )
    update["messages"] = [ToolMessage(message, tool_call_id=tool_call_id)]
    return Command(update=update)


@tool("clone_repository", parse_docstring=True)
def clone_repository(
    runtime: ToolRuntime[ContextT, ThreadState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    repo_url: str | None = None,
    branch: str | None = None,
    depth: int = 1,
) -> Command:
    """Clone a git repository into the currently bound compile session.

    This is the retryable network step of the compile flow. The repository root
    inside the compile container is always `/workspace/repo`.

    Args:
        repo_url: Optional repository URL. Defaults to the bound session repository.
        branch: Optional branch to checkout.
        depth: Clone depth. Defaults to 1.
    """
    session_id = _get_state_value(runtime, COMPILE_SESSION_STATE_KEY)
    if not session_id:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        "No compile session is currently bound. Call prepare_compile_session() first.",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    thread_id = _get_thread_id(runtime)
    session = get_bound_session(session_id=session_id, thread_id=thread_id)
    effective_repo_url = repo_url or session.repo_url
    _, message = clone_repository_impl(
        session=session,
        repo_url=effective_repo_url,
        branch=branch,
        depth=depth,
    )

    state_update = _build_compile_state_update(
        session_id=session.session_id,
        container_id=session.container_id,
    )
    state_update["messages"] = [ToolMessage(message, tool_call_id=tool_call_id)]
    return Command(update=state_update)


@tool("identify_build_system", parse_docstring=True)
def identify_build_system(
    runtime: ToolRuntime[ContextT, ThreadState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    session_id: str | None = None,
    workspace_path: str | None = None,
) -> Command:
    """Identify the build system for the bound compile session.

    The repository root is always `/workspace/repo` inside the compile container.
    `workspace_path` is accepted only for backward compatibility and is ignored.

    Args:
        session_id: Optional compile session identifier. Usually omit this.
        workspace_path: Ignored. The tool always checks `/workspace/repo` in the container.
    """
    del workspace_path
    effective_session_id = session_id or _get_state_value(runtime, COMPILE_SESSION_STATE_KEY)

    if not effective_session_id:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        "No compile session is currently bound in state. Call prepare_compile_session() first, then clone_repository(), then identify_build_system().",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    session = get_bound_session(session_id=effective_session_id, thread_id=_get_thread_id(runtime))
    primary_system, detected, suggested_commands = inspect_build_system_impl(session=session)
    root_file = detected[0][1] if detected else None
    message = (
        f"Build system identified: system={primary_system}, root_file={root_file or 'none'}. "
        "Next call task(..., subagent_type=\"compiler\") directly."
    )
    update = _build_compile_state_update(
        session_id=effective_session_id,
        container_id=session.container_id,
        build_system=primary_system,
    )
    update["messages"] = [ToolMessage(message, tool_call_id=tool_call_id)]
    return Command(update=update)


@tool("finalize_session", parse_docstring=True)
def finalize_session(
    runtime: ToolRuntime[ContextT, ThreadState],
    session_id: str | None = None,
) -> str:
    """Finalize a compile session and destroy the compile container.

    Args:
        session_id: Optional compile session identifier. Uses the currently bound session when omitted.
    """
    effective_session_id = session_id or _get_state_value(runtime, COMPILE_SESSION_STATE_KEY)
    if not effective_session_id:
        return "No compile session is currently bound. Call prepare_compile_session() first."

    thread_id = _get_thread_id(runtime)
    session = get_bound_session(session_id=effective_session_id, thread_id=thread_id)
    updated = finalize_compile_session_impl(session=session)
    services = get_compile_services()
    services.runtime.stop_and_remove_container(session)

    return (
        f"Session finalized. session_id={updated.session_id}, status={updated.status}, action=destroy, "
        f"lead_repro_bundle_path=none, "
        f"host_repro_bundle_path=none, "
        f"artifact_count={len(updated.artifacts)}"
    )
