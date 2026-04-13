from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.compile.docker_runtime import CompileDockerRuntime
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.schemas import BuildCommandRecord, utc_now_iso

COMPILE_SESSION_STATE_KEY = "compile_session_id"


@dataclass
class CompileToolServices:
    manager: CompileSessionManager
    runtime: CompileDockerRuntime


_services = CompileToolServices(
    manager=CompileSessionManager(),
    runtime=CompileDockerRuntime(),
)


def get_compile_services() -> CompileToolServices:
    return _services


def _get_thread_id(runtime: ToolRuntime[ContextT, ThreadState]) -> str:
    thread_id = runtime.context.get("thread_id") if runtime.context else None
    if thread_id is None:
        thread_id = runtime.config.get("configurable", {}).get("thread_id")
    return thread_id or "default"


def _get_bound_session_id(runtime: ToolRuntime[ContextT, ThreadState]) -> str | None:
    state = runtime.state or {}
    return state.get(COMPILE_SESSION_STATE_KEY)


def _load_bound_session(runtime: ToolRuntime[ContextT, ThreadState]):
    session_id = _get_bound_session_id(runtime)
    if not session_id:
        raise ValueError("No compile session is currently bound. Call prepare_compile_session first.")
    return get_compile_services().manager.load_session(session_id, _get_thread_id(runtime))


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
    services = get_compile_services()
    thread_id = _get_thread_id(runtime)
    session = services.manager.create_session(thread_id=thread_id, repo_url=repo_url, branch=branch)
    if task_description:
        session.summary = task_description
    services.runtime.create_container(session)
    services.manager.save_session(session)
    services.manager.mark_session_status(session, "ready")

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
    services = get_compile_services()
    session = _load_bound_session(runtime)

    clone_parts = [f"git clone --depth {depth}"]
    if branch:
        clone_parts.append(f"--branch {branch}")
    clone_parts.append(f"{repo_url} {session.container_repo_dir}")
    clone_command = " ".join(clone_parts)

    log_path = f"{session.host_logs_dir}/001_clone.log"
    started_at = utc_now_iso()
    result = services.runtime.exec(session, clone_command, workdir=session.container_workspace_dir, log_path=log_path)
    completed_at = utc_now_iso()

    record = BuildCommandRecord(
        stage="clone",
        command=clone_command,
        workdir=session.container_workspace_dir,
        started_at=started_at,
        completed_at=completed_at,
        exit_code=result.exit_code,
        log_path=log_path,
    )
    services.manager.record_command(session, record)

    if result.exit_code != 0:
        services.manager.mark_session_status(session, "failed", error=result.combined_output[:4000])
        return f"Clone failed with exit code {result.exit_code}. Output:\n{result.combined_output}"

    sha_result = services.runtime.exec(session, "git -C /workspace/repo rev-parse HEAD", workdir=session.container_workspace_dir)
    if sha_result.exit_code == 0:
        session.commit_sha = sha_result.stdout.strip()
        services.manager.save_session(session)

    services.manager.mark_session_status(session, "source_ready")
    return f"Repository cloned successfully to {session.container_repo_dir}. Commit: {session.commit_sha or 'unknown'}"


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
    services = get_compile_services()
    session = _load_bound_session(runtime)

    effective_stage = stage or "build"
    current_index = len(session.commands) + 1
    workdir_path = session.container_repo_dir if not workdir else f"{session.container_repo_dir}/{workdir.strip('/')}"
    log_path = f"{session.host_logs_dir}/{current_index:03d}_{effective_stage}.log"
    started_at = utc_now_iso()
    result = services.runtime.exec(session, command, workdir=workdir_path, timeout_seconds=timeout_seconds, log_path=log_path)
    completed_at = utc_now_iso()

    record = BuildCommandRecord(
        stage=effective_stage,
        command=command,
        workdir=workdir_path,
        started_at=started_at,
        completed_at=completed_at,
        exit_code=result.exit_code,
        log_path=log_path,
    )
    services.manager.record_command(session, record)

    if result.exit_code != 0:
        services.manager.mark_session_status(session, "failed", error=result.combined_output[:4000])
        return f"Command failed at stage '{effective_stage}' with exit code {result.exit_code}. Output:\n{result.combined_output}"

    services.manager.mark_session_status(session, "building")
    return f"Command succeeded at stage '{effective_stage}'. Log saved to {log_path}. Output:\n{result.combined_output}"
