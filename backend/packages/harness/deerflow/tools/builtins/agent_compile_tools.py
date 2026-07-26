from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated, Any

from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langgraph.typing import ContextT

from deerflow.compile.evidence import get_active_experiment, record_experiment_event
from deerflow.compile.operations import cleanup_and_finalize_compile_session_impl, clone_repository_impl, get_bound_session, get_compile_services, inspect_build_system_impl, prepare_compile_session_impl
from deerflow.compile.schemas import CompileSession

if TYPE_CHECKING:
    from deerflow.agents.thread_state import ThreadState
else:
    ThreadState = Any

COMPILE_SESSION_STATE_KEY = "compile_session_id"
COMPILE_CONTAINER_STATE_KEY = "compile_container_id"
COMPILE_BUILD_SYSTEM_STATE_KEY = "compile_build_system"
COMPILE_CONTAINER_REPO_PATH = "/workspace/repo"


def _get_thread_id(runtime: ToolRuntime[ContextT, ThreadState]) -> str:
    thread_id = runtime.context.get("thread_id") if runtime.context else None
    if thread_id is None:
        thread_id = runtime.config.get("configurable", {}).get("thread_id")
    return thread_id or "default"


def _get_run_id(runtime: ToolRuntime[ContextT, ThreadState]) -> str | None:
    run_id = runtime.context.get("run_id") if runtime.context else None
    if run_id is None:
        run_id = runtime.config.get("configurable", {}).get("run_id")
    return run_id


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


def _enforce_experiment_build_system(
    *,
    session: CompileSession,
    observed_build_system: str,
    detected_build_systems: list[str],
) -> tuple[bool, str | None, str | None]:
    active = get_active_experiment(session.thread_id)
    if active is None:
        selected_build_system = observed_build_system if observed_build_system != "unknown" else None
        session.selected_build_system = selected_build_system
        get_compile_services().manager.save_session(session)
        return True, selected_build_system, None

    expected_build_system = active.policy.selected_build_system
    matches = expected_build_system in detected_build_systems
    record_experiment_event(
        session.thread_id,
        "build.system_checked",
        session_id=session.session_id,
        expected_build_system=expected_build_system,
        selected_build_system=expected_build_system if matches else None,
        observed_build_system=observed_build_system,
        detected_build_systems=detected_build_systems,
        matches=matches,
        compiler_allowed=matches,
    )
    if matches:
        session.selected_build_system = expected_build_system
        get_compile_services().manager.save_session(session)
        return True, expected_build_system, None

    detected_summary = ", ".join(detected_build_systems) or "none"
    error = f"Benchmark protocol deviation: selected build system {expected_build_system} is not supported by detected repository capabilities ({detected_summary})."
    updated, cleanup_result = cleanup_and_finalize_compile_session_impl(
        session=session,
        interrupted_status="failed",
        error=error,
    )
    record_experiment_event(
        session.thread_id,
        "protocol.deviation",
        phase="identify_build_system",
        classification="build_system_mismatch",
        session_id=session.session_id,
        expected_build_system=expected_build_system,
        selected_build_system=None,
        observed_build_system=observed_build_system,
        detected_build_systems=detected_build_systems,
        compiler_allowed=False,
        cleanup_succeeded=cleanup_result.succeeded and cleanup_result.removed,
        session_finalized=updated.finalized_at is not None,
    )
    return False, None, error


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
        run_id=_get_run_id(runtime),
    )
    message = f"Compile session prepared. Next call clone_repository() using the bound session. session_id={session.session_id}, container_id={session.container_id}, container_repo_path={COMPILE_CONTAINER_REPO_PATH}"
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
    detected_build_systems = [build_system for build_system, _marker in detected]
    build_system_matches, selected_build_system, deviation_error = _enforce_experiment_build_system(
        session=session,
        observed_build_system=primary_system,
        detected_build_systems=detected_build_systems,
    )
    selected_marker = next((marker for build_system, marker in detected if build_system == selected_build_system), None)
    message = f'Build systems identified: capabilities={detected_build_systems or ["unknown"]}, selected={selected_build_system or "none"}, root_file={selected_marker or "none"}. Next call task(..., subagent_type="compiler") directly.'
    update = _build_compile_state_update(
        session_id=effective_session_id,
        container_id=session.container_id,
        build_system=selected_build_system,
    )
    if not build_system_matches:
        update["compile_terminal"] = True
        update["messages"] = [ToolMessage(deviation_error or "Benchmark build-system identity mismatch.", tool_call_id=tool_call_id)]
        return Command(update=update)
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
        return json.dumps(
            {
                "status": "error",
                "message": "No compile session is currently bound. Call prepare_compile_session() first.",
            }
        )

    thread_id = _get_thread_id(runtime)
    session = get_bound_session(session_id=effective_session_id, thread_id=thread_id)
    updated, cleanup_result = cleanup_and_finalize_compile_session_impl(
        session=session,
    )

    final_payload = {
        "status": updated.status,
        "session_id": updated.session_id,
        "commit_sha": updated.commit_sha,
        "image": updated.image,
        "image_id": updated.image_id,
        "build_system": updated.build_system,
        "build_system_capabilities": updated.build_system_capabilities,
        "selected_build_system": updated.selected_build_system,
        "executed_build_system": updated.executed_build_system,
        "commands": [command.command for command in updated.commands],
        "verification": updated.verification.status if updated.verification else "not_run",
        "replay_verification": updated.replay_attempts[-1].status if updated.replay_attempts else "not_run",
        "replay_attempt_id": updated.replay_attempts[-1].attempt_id if updated.replay_attempts else None,
        "artifacts": [
            {
                "path": artifact.path,
                "artifact_type": artifact.artifact_type,
                "size_bytes": artifact.size_bytes,
                "sha256": artifact.sha256,
            }
            for artifact in updated.artifacts
        ],
        "repro_script": f"{updated.leadagent_repro_dir}/build.sh",
        "container_stopped": cleanup_result.stopped,
        "container_removed": cleanup_result.removed,
        "error": updated.error,
        "completed_at": updated.completed_at,
        "finalized_at": updated.finalized_at,
    }
    return json.dumps(final_payload, ensure_ascii=False, indent=2)
