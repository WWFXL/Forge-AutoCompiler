from __future__ import annotations

import subprocess
from collections import deque
from typing import Any

from langchain.tools import tool

from deerflow.compile.operations import get_bound_session, get_compile_services, verify_build_artifacts_impl
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
) -> None:
    services = get_compile_services()
    services.manager.record_command(
        session,
        BuildCommandRecord(
            stage="bash",
            command=command,
            workdir=workdir,
            started_at=started_at,
            completed_at=completed_at,
            exit_code=exit_code,
            log_path=log_path,
        ),
    )


def _run_container_bash_impl(
    *,
    session: CompileSession,
    command: str,
    timeout_seconds: int = 1200,
    workdir: str | None = None,
) -> tuple[CommandResult, str]:
    services = get_compile_services()
    effective_workdir = workdir or session.container_repo_dir
    log_path = str(services.manager.local_logs_dir(session) / f"{len(session.commands) + 1:03d}_bash.log")

    services.manager.log_event(
        session,
        "container.bash.started",
        command=command,
        workdir=effective_workdir,
        timeout_seconds=timeout_seconds,
        log_path=log_path,
    )
    started_at = utc_now_iso()

    try:
        result = services.runtime.exec(
            session,
            command,
            workdir=effective_workdir,
            timeout_seconds=timeout_seconds,
            log_path=log_path,
        )
    except subprocess.TimeoutExpired:
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
        )
        services.manager.log_event(
            session,
            "container.bash.timed_out",
            command=command,
            workdir=effective_workdir,
            timeout_seconds=timeout_seconds,
            log_path=log_path,
        )
        raise RuntimeError(timeout_message) from None

    completed_at = utc_now_iso()
    _record_bash_command(
        session=session,
        command=command,
        workdir=effective_workdir,
        started_at=started_at,
        completed_at=completed_at,
        exit_code=result.exit_code,
        log_path=log_path,
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
    )
    message = (
        f"exit_code={result.exit_code}\n"
        f"workdir={effective_workdir}\n"
        f"log_path={log_path}\n"
        f"output_tail:\n{truncated_output}"
    )
    return result, message


@tool("run_container_bash", parse_docstring=True)
def run_container_bash(
    session_id: str,
    thread_id: str,
    command: str,
    timeout_seconds: int = 1200,
    workdir: str | None = None,
) -> str:
    """Run a bash command inside a compile session container.

    Args:
        session_id: Compile session identifier.
        thread_id: Parent workflow thread identifier.
        command: Bash command to execute inside the compile container.
        timeout_seconds: Command timeout in seconds.
        workdir: Optional absolute working directory inside the compile container.
    """
    session = get_bound_session(session_id=session_id, thread_id=thread_id)
    _, message = _run_container_bash_impl(
        session=session,
        command=command,
        timeout_seconds=timeout_seconds,
        workdir=workdir,
    )
    return message


def _format_verification_summary(payload: Any) -> str:
    if isinstance(payload, str):
        return payload

    if not isinstance(payload, dict):
        return str(payload)

    verification = payload.get("verification") or {}
    artifacts = payload.get("artifacts") or []
    lines = [
        f"status={verification.get('status', 'unknown')}",
        f"artifact_count={verification.get('artifact_count', len(artifacts))}",
        f"failed_checks={verification.get('failed_checks', 0)}",
    ]

    if artifacts:
        lines.append("artifacts:")
        for artifact in artifacts:
            path = artifact.get("path", "unknown") if isinstance(artifact, dict) else str(artifact)
            artifact_type = artifact.get("artifact_type") if isinstance(artifact, dict) else None
            lines.append(f"- {path}" + (f" ({artifact_type})" if artifact_type else ""))

    notes = verification.get("notes") or []
    if notes:
        lines.append("notes:")
        for note in notes:
            lines.append(f"- {note}")

    return "\n".join(lines)


def _run_verify_build_artifacts_impl(
    *,
    session: CompileSession,
    search_path: str | None = None,
    file_pattern: str | None = None,
    copy_to_artifacts: bool = True,
) -> str:
    _, payload, _ = verify_build_artifacts_impl(
        session=session,
        search_path=search_path,
        file_pattern=file_pattern,
        copy_to_artifacts=copy_to_artifacts,
    )
    return _format_verification_summary(payload)


@tool("verify_build_artifacts", parse_docstring=True)
def verify_build_artifacts(
    session_id: str,
    thread_id: str,
    search_path: str | None = None,
    file_pattern: str | None = None,
    copy_to_artifacts: bool = True,
) -> str:
    """Verify and collect build artifacts from a compile session container.

    Args:
        session_id: Compile session identifier.
        thread_id: Parent workflow thread identifier.
        search_path: Optional absolute search root. Defaults to `/workspace/repo`.
        file_pattern: Optional filename pattern such as `ffmpeg` or `*.so`.
        copy_to_artifacts: Whether to copy discovered files into the session artifacts directory.
    """
    session = get_bound_session(session_id=session_id, thread_id=thread_id)
    return _run_verify_build_artifacts_impl(
        session=session,
        search_path=search_path,
        file_pattern=file_pattern,
        copy_to_artifacts=copy_to_artifacts,
    )


def get_bound_compile_tools(session: CompileSession):
    @tool("run_container_bash", parse_docstring=True)
    def bound_run_container_bash(
        command: str,
        timeout_seconds: int = 1200,
        workdir: str | None = None,
    ) -> str:
        """Run a bash command inside the bound compile session container.

        Args:
            command: Bash command to execute inside the compile container.
            timeout_seconds: Command timeout in seconds.
            workdir: Optional absolute working directory inside the compile container.
        """
        _, message = _run_container_bash_impl(
            session=session,
            command=command,
            timeout_seconds=timeout_seconds,
            workdir=workdir,
        )
        return message

    @tool("verify_build_artifacts", parse_docstring=True)
    def bound_verify_build_artifacts(
        search_path: str | None = None,
        file_pattern: str | None = None,
        copy_to_artifacts: bool = True,
    ) -> str:
        """Verify and collect build artifacts from the bound compile session.

        Args:
            search_path: Optional absolute search root. Defaults to `/workspace/repo`.
            file_pattern: Optional filename pattern such as `ffmpeg` or `*.so`.
            copy_to_artifacts: Whether to copy discovered files into the session artifacts directory.
        """
        return _run_verify_build_artifacts_impl(
            session=session,
            search_path=search_path,
            file_pattern=file_pattern,
            copy_to_artifacts=copy_to_artifacts,
        )

    return [bound_run_container_bash, bound_verify_build_artifacts]
