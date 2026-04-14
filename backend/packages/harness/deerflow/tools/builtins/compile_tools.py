from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.compile.operations import (
    clone_repository_impl,
    finalize_compile_session_json,
    get_bound_session,
    get_compile_services,
    inspect_build_system_impl,
    prepare_compile_session_impl,
    run_compile_command_impl,
    verify_build_artifacts_impl,
)

COMPILE_SESSION_STATE_KEY = "compile_session_id"


@dataclass
class CompileToolServices:
    manager: object
    runtime: object



def _get_thread_id(runtime: ToolRuntime[ContextT, ThreadState]) -> str:
    thread_id = runtime.context.get("thread_id") if runtime.context else None
    if thread_id is None:
        thread_id = runtime.config.get("configurable", {}).get("thread_id")
    return thread_id or "default"



def _get_subagent_owner_id(runtime: ToolRuntime[ContextT, ThreadState]) -> str | None:
    metadata = runtime.config.get("metadata", {}) if runtime and runtime.config else {}
    trace_id = metadata.get("trace_id")
    agent_name = metadata.get("agent_name")
    if agent_name == "compiler" and trace_id:
        return f"compiler:{trace_id}"
    return trace_id or agent_name



def _get_bound_session_id(runtime: ToolRuntime[ContextT, ThreadState]) -> str | None:
    state = runtime.state or {}
    return state.get(COMPILE_SESSION_STATE_KEY)



def _load_bound_session(runtime: ToolRuntime[ContextT, ThreadState]):
    return get_bound_session(
        session_id=_get_bound_session_id(runtime),
        thread_id=_get_thread_id(runtime),
        owner_id=_get_subagent_owner_id(runtime),
    )



def get_compile_tool_services() -> CompileToolServices:
    services = get_compile_services()
    return CompileToolServices(manager=services.manager, runtime=services.runtime)


@tool("prepare_compile_session", parse_docstring=True)
def prepare_compile_session(
    runtime: ToolRuntime[ContextT, ThreadState],
    repo_url: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    branch: str | None = None,
    task_description: str | None = None,
) -> Command:
    """Create and bind a compile session for the current task.

    Args:
        repo_url: Git repository URL to compile.
        branch: Optional branch to clone.
        task_description: Optional short task summary for session metadata.
    """
    session = prepare_compile_session_impl(
        thread_id=_get_thread_id(runtime),
        repo_url=repo_url,
        branch=branch,
        task_description=task_description,
        owner_id=_get_subagent_owner_id(runtime),
    )

    message = (
        f"Compile session prepared. session_id={session.session_id}, "
        f"container_id={session.container_id}, repo_url={repo_url}, repo_dir={session.container_repo_dir}"
    )
    return Command(
        update={
            COMPILE_SESSION_STATE_KEY: session.session_id,
            "messages": [ToolMessage(message, tool_call_id=tool_call_id)],
        }
    )


@tool("clone_repository", parse_docstring=True)
def clone_repository(
    runtime: ToolRuntime[ContextT, ThreadState],
    repo_url: str,
    branch: str | None = None,
    depth: int = 1,
) -> str:
    """Clone a git repository into the current compile session.

    Args:
        repo_url: Git repository URL to clone.
        branch: Optional branch to checkout.
        depth: Clone depth. Defaults to 1.
    """
    _, message = clone_repository_impl(
        session=_load_bound_session(runtime),
        repo_url=repo_url,
        branch=branch,
        depth=depth,
    )
    return message


@tool("inspect_build_system", parse_docstring=True)
def inspect_build_system(runtime: ToolRuntime[ContextT, ThreadState]) -> str:
    """Detect the likely build system for the bound repository.

    Returns a concise summary of detected marker files and suggested commands.
    """
    primary_system, detected, suggested_commands = inspect_build_system_impl(session=_load_bound_session(runtime))
    marker_summary = ", ".join(f"{name} ({marker})" for name, marker in detected) if detected else "none"
    command_summary = "; ".join(suggested_commands)
    return f"Detected build system: {primary_system}. Marker files: {marker_summary}. Suggested commands: {command_summary}"


@tool("run_compile_command", parse_docstring=True)
def run_compile_command(
    runtime: ToolRuntime[ContextT, ThreadState],
    command: str,
    workdir: str | None = None,
    timeout_seconds: int = 1200,
    stage: str | None = None,
) -> str:
    """Run a build command inside the current compile session container.

    Args:
        command: Shell command to run.
        workdir: Optional subdirectory under `/workspace/repo`.
        timeout_seconds: Command timeout in seconds.
        stage: Optional logical stage label (e.g. configure/build/test).
    """
    _, _, message = run_compile_command_impl(
        session=_load_bound_session(runtime),
        command=command,
        workdir=workdir,
        timeout_seconds=timeout_seconds,
        stage=stage,
    )
    return message


@tool("verify_build_artifacts", parse_docstring=True)
def verify_build_artifacts(
    runtime: ToolRuntime[ContextT, ThreadState],
    search_path: str | None = None,
    file_pattern: str | None = None,
    copy_to_artifacts: bool = True,
) -> str:
    """Verify and collect build artifacts from the current repository.

    Args:
        search_path: Optional absolute search root. Defaults to `/workspace/repo`.
        file_pattern: Optional filename pattern such as `ffmpeg` or `*.so`.
        copy_to_artifacts: Whether to copy discovered files into the session artifacts directory.
    """
    _, _, message = verify_build_artifacts_impl(
        session=_load_bound_session(runtime),
        search_path=search_path,
        file_pattern=file_pattern,
        copy_to_artifacts=copy_to_artifacts,
    )
    return message


@tool("finalize_compile_session", parse_docstring=True)
def finalize_compile_session(
    runtime: ToolRuntime[ContextT, ThreadState],
    summary: str | None = None,
    generate_repro_bundle: bool = True,
) -> str:
    """Finalize the bound compile session and clean up the compile container.

    Args:
        summary: Optional final summary to persist into session metadata.
        generate_repro_bundle: Whether to generate a simple reproducible build script.
    """
    return finalize_compile_session_json(
        session=_load_bound_session(runtime),
        summary=summary,
        generate_repro_bundle=generate_repro_bundle,
    )
