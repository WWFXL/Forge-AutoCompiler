from __future__ import annotations

import subprocess
import time
from collections import deque

from langchain.tools import tool

from deerflow.compile.evidence import allowed_command_role, new_evidence_id
from deerflow.compile.operations import get_bound_session, get_compile_services, submit_build_result_impl
from deerflow.compile.schemas import BuildCommandRecord, CommandResult, CompileSession, utc_now_iso

_MAX_OUTPUT_LINES = 50


def _truncate_output_tail(output: str, max_lines: int = _MAX_OUTPUT_LINES) -> str:
    if not output:
        return ""
    tail = deque(output.splitlines(), maxlen=max_lines)
    return "\n".join(tail)


def _build_timeout_message(command: str, timeout_seconds: int) -> str:
    return f"Command timed out after {timeout_seconds}s: {command}"


def _record_bash_command(
    *,
    session: CompileSession,
    command: str,
    workdir: str,
    started_at: str,
    completed_at: str,
    exit_code: int,
    log_path: str,
    command_id: str,
    command_role: str,
    timeout_seconds: int,
    duration_seconds: float,
    timed_out: bool,
) -> BuildCommandRecord:
    services = get_compile_services()
    record = BuildCommandRecord(
        stage="bash",
        command=command,
        workdir=workdir,
        command_id=command_id,
        role=command_role,
        timeout_seconds=timeout_seconds,
        duration_seconds=duration_seconds,
        timed_out=timed_out,
        termination="timeout" if timed_out else ("failed" if exit_code != 0 else "completed"),
        started_at=started_at,
        completed_at=completed_at,
        exit_code=exit_code,
        log_path=log_path,
    )
    services.manager.record_command(session, record)
    return record


def _run_container_bash_impl(
    *,
    session: CompileSession,
    command: str,
    timeout_seconds: int = 1200,
    workdir: str | None = None,
    command_role: str = "other",
) -> tuple[CommandResult, str]:
    services = get_compile_services()
    effective_workdir = workdir or "/workspace/repo"
    effective_role = allowed_command_role(command_role)
    command_id = new_evidence_id("command")
    log_path = str(services.manager.local_logs_dir(session) / f"{len(session.commands) + 1:03d}_bash.log")

    services.manager.log_event(
        session,
        "container.bash.started",
        command=command,
        workdir=effective_workdir,
        timeout_seconds=timeout_seconds,
        log_path=log_path,
        command_id=command_id,
        command_role=effective_role,
    )
    started_at = utc_now_iso()
    started_monotonic = time.monotonic()

    try:
        result = services.runtime.exec(
            session,
            command,
            workdir=effective_workdir,
            timeout_seconds=timeout_seconds,
            log_path=log_path,
        )
    except subprocess.TimeoutExpired as exc:
        completed_at = utc_now_iso()
        timeout_message = _build_timeout_message(command, timeout_seconds)
        _record_bash_command(
            session=session,
            command=command,
            workdir=effective_workdir,
            started_at=started_at,
            completed_at=completed_at,
            exit_code=124,
            log_path=log_path,
            command_id=command_id,
            command_role=effective_role,
            timeout_seconds=timeout_seconds,
            duration_seconds=round(time.monotonic() - started_monotonic, 6),
            timed_out=True,
        )
        services.manager.log_event(
            session,
            "container.bash.timed_out",
            command=command,
            workdir=effective_workdir,
            timeout_seconds=timeout_seconds,
            log_path=log_path,
            command_id=command_id,
            command_role=effective_role,
        )
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        combined_output = stdout + stderr
        # Return a structured timeout to the agent instead of raising.
        message = f"command_id={command_id}\ncommand_role={effective_role}\nexit_code=124 (Timeout)\nworkdir={effective_workdir}\nerror: {timeout_message}\noutput_tail:\n{_truncate_output_tail(combined_output)}"
        result = CommandResult(
            exit_code=124,
            stdout=stdout,
            stderr=stderr or timeout_message,
            combined_output=combined_output or timeout_message,
            log_path=log_path,
        )
        return result, message

    completed_at = utc_now_iso()
    _record_bash_command(
        session=session,
        command=command,
        workdir=effective_workdir,
        started_at=started_at,
        completed_at=completed_at,
        exit_code=result.exit_code,
        log_path=log_path,
        command_id=command_id,
        command_role=effective_role,
        timeout_seconds=timeout_seconds,
        duration_seconds=round(time.monotonic() - started_monotonic, 6),
        timed_out=False,
    )
    truncated_output = _truncate_output_tail(result.combined_output)
    services.manager.log_event(
        session,
        "container.bash.completed",
        command=command,
        workdir=effective_workdir,
        timeout_seconds=timeout_seconds,
        log_path=log_path,
        exit_code=result.exit_code,
        truncated_output=truncated_output,
        command_id=command_id,
        command_role=effective_role,
    )
    message = f"command_id={command_id}\ncommand_role={effective_role}\nexit_code={result.exit_code}\nworkdir={effective_workdir}\nlog_path={log_path}\noutput_tail:\n{truncated_output}"
    return result, message


@tool("run_container_bash", parse_docstring=True)
def run_container_bash(
    session_id: str,
    thread_id: str,
    command: str,
    timeout_seconds: int = 1200,
    workdir: str | None = None,
    command_role: str = "other",
) -> str:
    """Run a bash command inside a compile session container.

    CRITICAL NOTE FOR AGENT: Each call to this tool runs in a completely isolated, new shell session.
    State changes like `cd` or `export` will NOT persist across multiple calls.
    You must use the `workdir` parameter to set the directory, or chain commands using `&&`.

    Args:
        session_id: Compile session identifier.
        thread_id: Parent workflow thread identifier.
        command: Bash command to execute inside the compile container.
        timeout_seconds: Command timeout in seconds.
        workdir: Optional absolute working directory inside the compile container.
        command_role: Evidence role: configure, build, artifact_stage, smoke, or other.
    """
    session = get_bound_session(session_id=session_id, thread_id=thread_id)
    _, message = _run_container_bash_impl(
        session=session,
        command=command,
        timeout_seconds=timeout_seconds,
        workdir=workdir,
        command_role=command_role,
    )
    return message


@tool("submit_build_result", parse_docstring=True)
def submit_build_result(
    session_id: str,
    thread_id: str,
    supporting_command_id: str | None = None,
) -> str:
    """Submit final build artifacts from `/artifacts` for deterministic acceptance.

    Args:
        session_id: Compile session identifier.
        thread_id: Parent workflow thread identifier.
        supporting_command_id: Stable ID of the successful build command supporting this submission.
    """
    session = get_bound_session(session_id=session_id, thread_id=thread_id)
    if supporting_command_id is None:
        return submit_build_result_impl(session=session)
    return submit_build_result_impl(
        session=session,
        supporting_command_id=supporting_command_id,
    )


def get_bound_compile_tools(session: CompileSession):
    @tool("run_container_bash", parse_docstring=True)
    def bound_run_container_bash(
        command: str,
        timeout_seconds: int = 1200,
        workdir: str | None = None,
        command_role: str = "other",
    ) -> str:
        """Run a bash command inside the bound compile session container.

        Args:
            command: Bash command to execute inside the compile container.
            timeout_seconds: Command timeout in seconds.
            workdir: Optional absolute working directory inside the compile container.
            command_role: Evidence role: configure, build, artifact_stage, smoke, or other.
        """
        _, message = _run_container_bash_impl(
            session=session,
            command=command,
            timeout_seconds=timeout_seconds,
            workdir=workdir,
            command_role=command_role,
        )
        return message

    @tool("submit_build_result", parse_docstring=True)
    def bound_submit_build_result(supporting_command_id: str | None = None) -> str:
        """Submit final build artifacts from `/artifacts` for deterministic acceptance.

        Args:
            supporting_command_id: Stable ID of the successful build command supporting this submission.
        """
        if supporting_command_id is None:
            return submit_build_result_impl(session=session)
        return submit_build_result_impl(
            session=session,
            supporting_command_id=supporting_command_id,
        )

    return [bound_run_container_bash, bound_submit_build_result]
