from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.compile.compile_tools import (
    FinalizeSessionInput,
    FinalizeSessionTool,
    IdentifyBuildSystemInput,
    IdentifyBuildSystemTool,
    PrepareWorkspaceInput,
    PrepareWorkspaceTool,
)
from deerflow.compile.operations import clone_repository_impl, get_bound_session, prepare_compile_session_impl

COMPILE_SESSION_STATE_KEY = "compile_session_id"
COMPILE_CONTAINER_STATE_KEY = "compile_container_id"
COMPILE_BUILD_SYSTEM_STATE_KEY = "compile_build_system"
COMPILE_CONTAINER_REPO_PATH = "/workspace/repo"


@dataclass
class CompileToolServices:
    manager: object
    runtime: object


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


@tool("prepare_workspace", parse_docstring=True)
def prepare_workspace(
    runtime: ToolRuntime[ContextT, ThreadState],
    repo_url: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    branch: str | None = None,
) -> Command:
    """Prepare a compile workspace for a remote repository.

    This legacy tool prepares a compile session, clones the repository, and binds
    the resulting state. Prefer the split flow of `prepare_compile_session()`,
    `clone_repository()`, then `identify_build_system()` for retry-friendly
    autonomous orchestration.

    Args:
        repo_url: Git repository URL to compile.
        branch: Optional branch to checkout.
    """
    result = PrepareWorkspaceTool().run(
        PrepareWorkspaceInput(
            thread_id=_get_thread_id(runtime),
            repo_url=repo_url,
            branch=branch,
        )
    )
    message = (
        "Workspace prepared and compile session bound. "
        "Prefer the split flow next time: prepare_compile_session(), clone_repository(), identify_build_system(). "
        f"container_repo_path={result.container_repo_path}"
    )
    update = _build_compile_state_update(
        session_id=result.session_id,
        container_id=result.container_id,
    )
    update["messages"] = [ToolMessage(message, tool_call_id=tool_call_id)]
    return Command(update=update)


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

    result = IdentifyBuildSystemTool().run(
        IdentifyBuildSystemInput(
            thread_id=_get_thread_id(runtime),
            session_id=effective_session_id,
            workspace_path=COMPILE_CONTAINER_REPO_PATH,
        )
    )
    message = (
        f"Build system identified: system={result.system}, root_file={result.root_file or 'none'}. "
        "Next call task(..., subagent_type=\"compiler\") directly."
    )
    update = _build_compile_state_update(
        session_id=effective_session_id,
        container_id=result.details.get("container_id"),
        build_system=result.system,
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

    result = FinalizeSessionTool().run(
        FinalizeSessionInput(
            thread_id=_get_thread_id(runtime),
            session_id=effective_session_id,
        )
    )
    return (
        f"Session finalized. session_id={result.session_id}, status={result.status}, action={result.action}, "
        f"lead_repro_bundle_path={result.lead_repro_bundle_path or 'none'}, "
        f"host_repro_bundle_path={result.host_repro_bundle_path or 'none'}, "
        f"artifact_count={len(result.artifact_paths)}"
    )
