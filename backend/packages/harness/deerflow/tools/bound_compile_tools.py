from __future__ import annotations

import json
import re
import subprocess
import time
from collections import deque
from pathlib import Path
from typing import Literal

from langchain.tools import tool

from deerflow.compile.evidence import allowed_command_role, new_evidence_id, record_experiment_event
from deerflow.compile.operations import (
    get_bound_session,
    get_compile_services,
    infer_command_roles,
    submit_build_result_impl,
    validate_experiment_build_arguments,
)
from deerflow.compile.schemas import COMPILE_COMMAND_ROLES, BuildCommandRecord, CommandResult, CompileSession, utc_now_iso

CompileCommandRole = Literal["dependency", "configure", "build", "diagnostic", "smoke", "artifact_stage"]

_MAX_OUTPUT_LINES = 50
_MAX_POST_BUILD_NON_STAGING_COMMANDS = 2
_POLICY_REJECTED_EXIT_CODE = 126
_STRICT_SHELL_DISABLE_PATTERNS = (
    re.compile(r"(?:^|[;&|()\n]\s*)set\s+\+[a-zA-Z]*[eu][a-zA-Z]*(?=\s|[;&|()]|$)"),
    re.compile(r"(?:^|[;&|()\n]\s*)set\s+\+o\s+(?:errexit|nounset|pipefail)(?=\s|[;&|()]|$)"),
)
_POST_BUILD_FORBIDDEN_ROLES = {
    "clone",
    "inspect",
    "dependency_setup",
    "configure",
    "build",
    "housekeeping",
    "replay_delay",
}
_SYSTEM_ORACLE_AUTHORITY = object()


def _truncate_output_tail(output: str, max_lines: int = _MAX_OUTPUT_LINES) -> str:
    if not output:
        return ""
    tail = deque(output.splitlines(), maxlen=max_lines)
    return "\n".join(tail)


def _disables_strict_shell(command: str) -> bool:
    return any(pattern.search(command) is not None for pattern in _STRICT_SHELL_DISABLE_PATTERNS)


def _write_policy_rejection_log(log_path: str, rejection: str) -> None:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rejection.rstrip() + "\n", encoding="utf-8")


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
    termination: str | None = None,
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
        termination=termination or ("timeout" if timed_out else ("failed" if exit_code != 0 else "completed")),
        started_at=started_at,
        completed_at=completed_at,
        exit_code=exit_code,
        log_path=log_path,
    )
    services.manager.record_command(session, record)
    return record


def _reload_session(session: CompileSession) -> CompileSession:
    services = get_compile_services()
    try:
        current = services.manager.load_session(session.session_id, session.thread_id)
    except (OSError, TypeError, ValueError):
        return session
    session.__dict__.update(current.__dict__)
    return session


def _set_post_build_phase(session: CompileSession, supporting_command_id: str) -> None:
    services = get_compile_services()
    with services.manager.session_lock(session.thread_id, session.session_id):
        current = _reload_session(session)
        current.post_build_supporting_command_id = supporting_command_id
        current.post_build_started_at = utc_now_iso()
        current.post_build_commands_remaining = _MAX_POST_BUILD_NON_STAGING_COMMANDS
        services.manager.save_session(current)
        session.__dict__.update(current.__dict__)
    services.manager.log_event(
        session,
        "post_build.started",
        supporting_command_id=supporting_command_id,
        commands_remaining=_MAX_POST_BUILD_NON_STAGING_COMMANDS,
    )
    record_experiment_event(
        session.thread_id,
        "postbuild.started",
        session_id=session.session_id,
        supporting_command_id=supporting_command_id,
        commands_remaining=_MAX_POST_BUILD_NON_STAGING_COMMANDS,
    )


def _clear_post_build_phase(session: CompileSession, *, reason: str) -> None:
    services = get_compile_services()
    with services.manager.session_lock(session.thread_id, session.session_id):
        current = _reload_session(session)
        supporting_command_id = current.post_build_supporting_command_id
        current.post_build_supporting_command_id = None
        current.post_build_started_at = None
        current.post_build_commands_remaining = None
        services.manager.save_session(current)
        session.__dict__.update(current.__dict__)
    services.manager.log_event(
        session,
        "post_build.released",
        supporting_command_id=supporting_command_id,
        reason=reason,
    )


def _post_build_rejection(session: CompileSession, *, command: str, command_role: str) -> str | None:
    if "/repro" in command:
        return "Compiler commands may not read or write /repro; replay is controlled by the acceptance service."
    _reload_session(session)
    if session.post_build_supporting_command_id is None:
        return None
    command_roles = infer_command_roles(command) | {command_role}
    if command_roles & _POST_BUILD_FORBIDDEN_ROLES:
        return "A successful build already entered the post-build phase; configure, build, housekeeping, dependency, and replay commands are now blocked. Stage artifacts or submit the existing build."
    if command_role != "artifact_stage" and (session.post_build_commands_remaining or 0) <= 0:
        return "The bounded post-build inspection budget is exhausted. Stage final outputs into /artifacts or submit the existing build."
    return None


def _consume_post_build_budget(session: CompileSession, *, command_role: str) -> None:
    if command_role == "artifact_stage":
        return
    services = get_compile_services()
    with services.manager.session_lock(session.thread_id, session.session_id):
        current = _reload_session(session)
        if current.post_build_supporting_command_id is None or current.post_build_commands_remaining is None:
            return
        current.post_build_commands_remaining = max(0, current.post_build_commands_remaining - 1)
        services.manager.save_session(current)
        session.__dict__.update(current.__dict__)


def _submit_with_post_build_phase(
    session: CompileSession,
    *,
    supporting_command_id: str,
    recipe_command_ids: list[str],
    verification_command_ids: list[str],
) -> str:
    _reload_session(session)
    had_post_build_phase = session.post_build_supporting_command_id is not None
    try:
        result = submit_build_result_impl(
            session=session,
            supporting_command_id=supporting_command_id,
            recipe_command_ids=recipe_command_ids,
            verification_command_ids=verification_command_ids,
        )
    except Exception:
        if had_post_build_phase:
            _clear_post_build_phase(session, reason="submit_error")
        raise
    try:
        payload = json.loads(result)
    except (TypeError, json.JSONDecodeError):
        if had_post_build_phase:
            _clear_post_build_phase(session, reason="submit_invalid_response")
        return result
    if payload.get("status") != "passed" and session.post_build_supporting_command_id is not None:
        _clear_post_build_phase(session, reason="submit_failed")
    return result


def _run_container_bash_impl(
    *,
    session: CompileSession,
    command: str,
    timeout_seconds: int = 1200,
    workdir: str | None = None,
    command_role: CompileCommandRole,
    _execution_authority: object | None = None,
) -> tuple[CommandResult, str, BuildCommandRecord]:
    services = get_compile_services()
    effective_workdir = workdir or "/workspace/repo"
    if _execution_authority is not None and _execution_authority is not _SYSTEM_ORACLE_AUTHORITY:
        raise ValueError("Unsupported command execution authority")
    system_oracle = _execution_authority is _SYSTEM_ORACLE_AUTHORITY
    if command_role not in COMPILE_COMMAND_ROLES:
        raise ValueError(f"Unsupported compile command role: {command_role!r}")
    declared_role = allowed_command_role(command_role)
    inferred_roles = infer_command_roles(command)
    inferred_role = next(iter(sorted(inferred_roles)), None)
    effective_role = declared_role
    command_id = new_evidence_id("command")
    log_path = str(services.manager.local_logs_dir(session) / f"{command_id}.log")

    services.manager.log_event(
        session,
        "command.role_resolved",
        command_id=command_id,
        declared_role=declared_role,
        inferred_role=inferred_role,
        effective_role=effective_role,
        corrected=effective_role != declared_role,
    )

    if _disables_strict_shell(command):
        rejection = "Commands may not disable errexit, nounset, or pipefail. Keep the runtime strict-shell contract enabled."
        _write_policy_rejection_log(log_path, rejection)
        now = utc_now_iso()
        record = _record_bash_command(
            session=session,
            command=command,
            workdir=effective_workdir,
            started_at=now,
            completed_at=now,
            exit_code=_POLICY_REJECTED_EXIT_CODE,
            log_path=log_path,
            command_id=command_id,
            command_role=effective_role,
            timeout_seconds=timeout_seconds,
            duration_seconds=0.0,
            timed_out=False,
            termination="policy_rejected",
        )
        services.manager.log_event(
            session,
            "command.strict_shell_rejected",
            command_id=command_id,
            command_role=effective_role,
            classification="strict_shell_disabled",
        )
        result = CommandResult(
            exit_code=_POLICY_REJECTED_EXIT_CODE,
            stdout="",
            stderr=rejection,
            combined_output=rejection,
            log_path=log_path,
        )
        message = f"command_id={command_id}\ncommand_role={effective_role}\nexit_code={_POLICY_REJECTED_EXIT_CODE} (Policy rejected)\nworkdir={effective_workdir}\nclassification=strict_shell_disabled\nerror: {rejection}"
        return result, message, record
    record_experiment_event(
        session.thread_id,
        "command.role_resolved",
        command_id=command_id,
        session_id=session.session_id,
        declared_role=declared_role,
        inferred_role=inferred_role,
        effective_role=effective_role,
        corrected=effective_role != declared_role,
    )

    logical_roles = set(inferred_roles) & {"dependency_setup", "configure", "build", "artifact_stage", "smoke"}
    if len(logical_roles) > 1:
        rejection = "A run_container_bash call may execute only one logical stage. Split dependency, configure, build, smoke, and artifact staging into separate calls."
        _write_policy_rejection_log(log_path, rejection)
        now = utc_now_iso()
        record = _record_bash_command(
            session=session,
            command=command,
            workdir=effective_workdir,
            started_at=now,
            completed_at=now,
            exit_code=_POLICY_REJECTED_EXIT_CODE,
            log_path=log_path,
            command_id=command_id,
            command_role=effective_role,
            timeout_seconds=timeout_seconds,
            duration_seconds=0.0,
            timed_out=False,
            termination="policy_rejected",
        )
        services.manager.log_event(
            session,
            "command.stage_rejected",
            command_id=command_id,
            command_role=effective_role,
            classification="mixed_logical_stages",
            detected_roles=sorted(logical_roles),
        )
        result = CommandResult(
            exit_code=_POLICY_REJECTED_EXIT_CODE,
            stdout="",
            stderr=rejection,
            combined_output=rejection,
            log_path=log_path,
        )
        message = f"command_id={command_id}\ncommand_role={effective_role}\nexit_code={_POLICY_REJECTED_EXIT_CODE} (Policy rejected)\nworkdir={effective_workdir}\nclassification=mixed_logical_stages\nerror: {rejection}"
        return result, message, record

    if system_oracle:
        rejection = "Compiler commands may not read or write /repro; replay is controlled by the acceptance service." if "/repro" in command else None
    else:
        rejection = _post_build_rejection(
            session,
            command=command,
            command_role=effective_role,
        )
    if rejection is not None:
        _write_policy_rejection_log(log_path, rejection)
        now = utc_now_iso()
        record = _record_bash_command(
            session=session,
            command=command,
            workdir=effective_workdir,
            started_at=now,
            completed_at=now,
            exit_code=_POLICY_REJECTED_EXIT_CODE,
            log_path=log_path,
            command_id=command_id,
            command_role=effective_role,
            timeout_seconds=timeout_seconds,
            duration_seconds=0.0,
            timed_out=False,
            termination="policy_rejected",
        )
        services.manager.log_event(
            session,
            "post_build.command_rejected",
            command_id=command_id,
            command_role=effective_role,
            reason=rejection,
        )
        result = CommandResult(
            exit_code=_POLICY_REJECTED_EXIT_CODE,
            stdout="",
            stderr=rejection,
            combined_output=rejection,
            log_path=log_path,
        )
        return result, f"command_id={command_id}\ncommand_role={effective_role}\nexit_code={_POLICY_REJECTED_EXIT_CODE} (Policy rejected)\nworkdir={effective_workdir}\nerror: {rejection}", record

    arguments_match, argument_failure, required_argument_count = validate_experiment_build_arguments(
        session,
        command,
    )
    if required_argument_count:
        record_experiment_event(
            session.thread_id,
            "build.arguments_checked",
            phase="pre_build",
            session_id=session.session_id,
            command_id=command_id,
            build_system=session.selected_build_system,
            required_argument_count=required_argument_count,
            matches=arguments_match,
            command_executed=arguments_match,
        )
    if argument_failure is not None:
        rejection = "The build command was not executed because no successful configure command observed every frozen build argument in order. Correct the configure command with the experiment policy arguments, then retry the build."
        _write_policy_rejection_log(log_path, rejection)
        now = utc_now_iso()
        record = _record_bash_command(
            session=session,
            command=command,
            workdir=effective_workdir,
            started_at=now,
            completed_at=now,
            exit_code=_POLICY_REJECTED_EXIT_CODE,
            log_path=log_path,
            command_id=command_id,
            command_role=effective_role,
            timeout_seconds=timeout_seconds,
            duration_seconds=0.0,
            timed_out=False,
            termination="policy_rejected",
        )
        services.manager.log_event(
            session,
            "build.arguments_rejected",
            command_id=command_id,
            command_role=effective_role,
            classification=argument_failure,
        )
        record_experiment_event(
            session.thread_id,
            "protocol.deviation",
            phase="pre_build",
            classification=argument_failure,
            session_id=session.session_id,
            command_id=command_id,
            build_system=session.selected_build_system,
            required_argument_count=required_argument_count,
            submit_allowed=False,
            command_executed=False,
        )
        result = CommandResult(
            exit_code=_POLICY_REJECTED_EXIT_CODE,
            stdout="",
            stderr=rejection,
            combined_output=rejection,
            log_path=log_path,
        )
        message = f"command_id={command_id}\ncommand_role={effective_role}\nexit_code={_POLICY_REJECTED_EXIT_CODE} (Policy rejected)\nworkdir={effective_workdir}\nclassification={argument_failure}\nerror: {rejection}"
        return result, message, record

    if system_oracle:
        services.manager.log_event(
            session,
            "system_oracle.command_authorized",
            command_id=command_id,
            command_role=effective_role,
        )
    else:
        _consume_post_build_budget(session, command_role=effective_role)

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
            strict_shell=True,
        )
    except subprocess.TimeoutExpired as exc:
        completed_at = utc_now_iso()
        timeout_message = _build_timeout_message(command, timeout_seconds)
        record = _record_bash_command(
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
        return result, message, record

    completed_at = utc_now_iso()
    record = _record_bash_command(
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
    container_log_path = f"/logs/{command_id}.log"
    message = f"command_id={command_id}\ncommand_role={effective_role}\nexit_code={result.exit_code}\nworkdir={effective_workdir}\nlog_path={container_log_path}\noutput_tail:\n{truncated_output}"
    if result.exit_code == 0 and effective_role == "build":
        _set_post_build_phase(session, record.command_id)
    return result, message, record


def _run_system_oracle_bash_impl(
    *,
    session: CompileSession,
    command: str,
    timeout_seconds: int = 1200,
    workdir: str | None = None,
    command_role: CompileCommandRole,
) -> tuple[CommandResult, str, BuildCommandRecord]:
    """使用系统 evaluator 权限执行命令，不占用 Agent 的 post-build 次数。"""
    return _run_container_bash_impl(
        session=session,
        command=command,
        timeout_seconds=timeout_seconds,
        workdir=workdir,
        command_role=command_role,
        _execution_authority=_SYSTEM_ORACLE_AUTHORITY,
    )


@tool("run_container_bash", parse_docstring=True)
def run_container_bash(
    session_id: str,
    thread_id: str,
    command: str,
    command_role: CompileCommandRole,
    timeout_seconds: int = 1200,
    workdir: str | None = None,
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
        command_role: One logical stage: dependency, configure, build, diagnostic, smoke, or artifact_stage.
    """
    session = get_bound_session(session_id=session_id, thread_id=thread_id)
    _result, message, _record = _run_container_bash_impl(
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
    supporting_command_id: str,
    recipe_command_ids: list[str],
    verification_command_ids: list[str],
) -> str:
    """Submit final build artifacts from `/artifacts` for deterministic acceptance.

    Args:
        session_id: Compile session identifier.
        thread_id: Parent workflow thread identifier.
        supporting_command_id: Stable ID of the successful build command supporting this submission.
        recipe_command_ids: Ordered successful command IDs forming the minimal clean-replay recipe.
        verification_command_ids: Ordered successful smoke command IDs to rerun after the clean replay build, or an empty list when no project verification command ran.
    """
    session = get_bound_session(session_id=session_id, thread_id=thread_id)
    return _submit_with_post_build_phase(
        session=session,
        supporting_command_id=supporting_command_id,
        recipe_command_ids=recipe_command_ids,
        verification_command_ids=verification_command_ids,
    )


def get_bound_compile_tools(session: CompileSession):
    @tool("run_container_bash", parse_docstring=True)
    def bound_run_container_bash(
        command: str,
        command_role: CompileCommandRole,
        timeout_seconds: int = 1200,
        workdir: str | None = None,
    ) -> str:
        """Run a bash command inside the bound compile session container.

        Args:
            command: Bash command to execute inside the compile container.
            timeout_seconds: Command timeout in seconds.
            workdir: Optional absolute working directory inside the compile container.
            command_role: One logical stage: dependency, configure, build, diagnostic, smoke, or artifact_stage.
        """
        _result, message, _record = _run_container_bash_impl(
            session=session,
            command=command,
            timeout_seconds=timeout_seconds,
            workdir=workdir,
            command_role=command_role,
        )
        return message

    @tool("submit_build_result", parse_docstring=True)
    def bound_submit_build_result(
        supporting_command_id: str,
        recipe_command_ids: list[str],
        verification_command_ids: list[str],
    ) -> str:
        """Submit final build artifacts from `/artifacts` for deterministic acceptance.

        Args:
            supporting_command_id: Stable ID of the successful build command supporting this submission.
            recipe_command_ids: Ordered successful command IDs forming the minimal clean-replay recipe.
            verification_command_ids: Ordered successful smoke command IDs to rerun after the clean replay build, or an empty list when no project verification command ran.
        """
        return _submit_with_post_build_phase(
            session=session,
            supporting_command_id=supporting_command_id,
            recipe_command_ids=recipe_command_ids,
            verification_command_ids=verification_command_ids,
        )

    return [bound_run_container_bash, bound_submit_build_result]
