from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from shlex import quote

from deerflow.compile.docker_runtime import CompileDockerRuntime
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.schemas import (
    BuildArtifact,
    BuildCommandRecord,
    CommandResult,
    CompileSession,
    VerificationCheck,
    VerificationResult,
    utc_now_iso,
)

_BUILD_SYSTEM_MARKERS = {
    "cmake": "CMakeLists.txt",
    "make": "Makefile",
    "autotools": "configure",
}

_ARTIFACT_FILE_EXCLUDES = [
    "*/.*",
    "*/CMakeFiles/*",
]


@dataclass
class CompileOperationsServices:
    manager: CompileSessionManager
    runtime: CompileDockerRuntime


_manager = CompileSessionManager()
_services = CompileOperationsServices(
    manager=_manager,
    runtime=CompileDockerRuntime(manager=_manager),
)


def get_compile_services() -> CompileOperationsServices:
    return _services


def get_bound_session(session_id: str | None, thread_id: str, owner_id: str | None = None) -> CompileSession:
    if not session_id:
        raise ValueError("No compile session is currently bound. Call prepare_compile_session first.")

    session = get_compile_services().manager.load_session(session_id, thread_id)
    if session.owner_subagent_id and owner_id and session.owner_subagent_id != owner_id:
        raise ValueError("The bound compile session belongs to another subagent execution.")
    return session


def relative_or_original(session: CompileSession, path: str | Path) -> str:
    return get_compile_services().manager.relative_path(session, path)


def local_log_path(session: CompileSession, filename: str) -> str:
    return str(get_compile_services().manager.local_logs_dir(session) / filename)


def shell_quote(value: str) -> str:
    return quote(value)


def container_repo_path(session: CompileSession, relative_path: str | None) -> str:
    if not relative_path:
        return session.container_repo_dir
    normalized = relative_path.strip("/")
    return f"{session.container_repo_dir}/{normalized}" if normalized else session.container_repo_dir


def append_command_record(
    session: CompileSession,
    stage: str,
    command: str,
    workdir: str,
    log_path: str,
    exit_code: int,
    started_at: str,
    completed_at: str,
) -> BuildCommandRecord:
    record = BuildCommandRecord(
        stage=stage,
        command=command,
        workdir=workdir,
        started_at=started_at,
        completed_at=completed_at,
        exit_code=exit_code,
        log_path=log_path,
    )
    get_compile_services().manager.record_command(session, record)
    return record


def prepare_compile_session_impl(
    *,
    thread_id: str,
    repo_url: str,
    branch: str | None = None,
    task_description: str | None = None,
    owner_id: str | None = None,
) -> CompileSession:
    services = get_compile_services()
    session = services.manager.create_session(thread_id=thread_id, repo_url=repo_url, branch=branch)
    session.owner_subagent_id = owner_id
    if task_description:
        session.summary = task_description
    services.manager.save_session(session)
    services.manager.log_event(
        session,
        "prepare.started",
        owner_id=owner_id,
        task_description=task_description,
    )
    services.runtime.create_container(session)
    services.manager.save_session(session)
    services.manager.mark_session_status(session, "ready")
    services.manager.log_event(
        session,
        "prepare.completed",
        container_id=session.container_id,
        container_name=session.container_name,
    )
    return session


def prepare_compile_session_json(
    *,
    thread_id: str,
    repo_url: str,
    branch: str | None = None,
    task_description: str | None = None,
    owner_id: str | None = None,
) -> str:
    session = prepare_compile_session_impl(
        thread_id=thread_id,
        repo_url=repo_url,
        branch=branch,
        task_description=task_description,
        owner_id=owner_id,
    )
    return json.dumps(session.to_dict(), ensure_ascii=False, indent=2)


def clone_repository_impl(
    *,
    session: CompileSession,
    repo_url: str,
    branch: str | None = None,
    depth: int = 1,
    max_retries: int = 2,
) -> tuple[CommandResult, str]:
    services = get_compile_services()

    clone_parts = [f"git clone --depth {depth}"]
    if branch:
        clone_parts.append(f"--branch {shell_quote(branch)}")
    clone_parts.append(f"{shell_quote(repo_url)} {shell_quote(session.container_repo_dir)}")
    clone_command = " ".join(clone_parts)

    retries = max(1, max_retries)
    last_result: CommandResult | None = None

    for attempt in range(1, retries + 1):
        log_filename = f"001_clone_attempt_{attempt}.log" if retries > 1 else "001_clone.log"
        log_path = local_log_path(session, log_filename)
        services.manager.log_event(
            session,
            "clone.started",
            repo_url=repo_url,
            branch=branch,
            depth=depth,
            attempt=attempt,
            max_retries=retries,
            log_path=log_path,
            target_dir=session.container_repo_dir,
        )
        started_at = utc_now_iso()
        cleanup_command = f"rm -rf {shell_quote(session.container_repo_dir)}"
        services.runtime.exec(session, cleanup_command, workdir=session.container_workspace_dir)
        result = services.runtime.exec(session, clone_command, workdir=session.container_workspace_dir, log_path=log_path)
        completed_at = utc_now_iso()
        append_command_record(session, "clone", clone_command, session.container_workspace_dir, log_path, result.exit_code, started_at, completed_at)
        last_result = result

        if result.exit_code == 0:
            sha_result = services.runtime.exec(session, "git -C /workspace/repo rev-parse HEAD", workdir=session.container_workspace_dir)
            if sha_result.exit_code == 0:
                session.commit_sha = sha_result.stdout.strip()
                services.manager.save_session(session)

            services.manager.log_event(
                session,
                "clone.completed",
                attempt=attempt,
                max_retries=retries,
                exit_code=result.exit_code,
                log_path=log_path,
                commit_sha=session.commit_sha,
            )
            services.manager.mark_session_status(session, "source_ready")
            return result, f"Repository cloned successfully to {session.container_repo_dir}. Commit: {session.commit_sha or 'unknown'}"

        services.manager.log_event(
            session,
            "clone.failed_attempt",
            attempt=attempt,
            max_retries=retries,
            exit_code=result.exit_code,
            log_path=log_path,
            output=result.combined_output[:4000],
        )

    assert last_result is not None
    services.manager.log_event(
        session,
        "clone.failed",
        attempts=retries,
        exit_code=last_result.exit_code,
        log_path=last_result.log_path,
        output=last_result.combined_output[:4000],
    )
    services.manager.mark_session_status(session, "failed", error=last_result.combined_output[:4000])
    return last_result, f"Clone failed with exit code {last_result.exit_code} after {retries} attempt(s). Output:\n{last_result.combined_output}"


def clone_repository_json(
    *,
    session: CompileSession,
    repo_url: str,
    branch: str | None = None,
    depth: int = 1,
) -> str:
    result, message = clone_repository_impl(session=session, repo_url=repo_url, branch=branch, depth=depth)
    return json.dumps({"exit_code": result.exit_code, "message": message, "log_path": result.log_path}, ensure_ascii=False, indent=2)


def inspect_build_system_impl(*, session: CompileSession) -> tuple[str, list[tuple[str, str]], list[str]]:
    services = get_compile_services()

    services.manager.log_event(session, "inspect.started")
    detected: list[tuple[str, str]] = []
    for build_system, marker in _BUILD_SYSTEM_MARKERS.items():
        check_command = f"test -f {shell_quote(container_repo_path(session, marker))}"
        result = services.runtime.exec(session, check_command, workdir=session.container_workspace_dir)
        if result.exit_code == 0:
            detected.append((build_system, marker))

    if detected:
        primary_system = detected[0][0]
        session.build_system = primary_system
        services.manager.save_session(session)
    else:
        primary_system = "unknown"

    suggested_commands = {
        "cmake": ["mkdir -p build && cd build && cmake ..", "cmake --build build -j"],
        "make": ["make -j"],
        "autotools": ["chmod +x ./configure && ./configure", "make -j"],
        "unknown": ["Inspect repository manually and run the appropriate C/C++ build command"],
    }

    services.manager.log_event(
        session,
        "inspect.completed",
        primary_system=primary_system,
        detected=detected,
        suggested_commands=suggested_commands.get(primary_system, suggested_commands["unknown"]),
    )
    services.manager.mark_session_status(session, "inspected")
    return primary_system, detected, suggested_commands.get(primary_system, suggested_commands["unknown"])


def inspect_build_system_json(*, session: CompileSession) -> str:
    primary_system, detected, suggested_commands = inspect_build_system_impl(session=session)
    return json.dumps(
        {
            "build_system": primary_system,
            "detected": detected,
            "suggested_commands": suggested_commands,
        },
        ensure_ascii=False,
        indent=2,
    )


def run_compile_command_impl(
    *,
    session: CompileSession,
    command: str,
    workdir: str | None = None,
    timeout_seconds: int = 1200,
    stage: str | None = None,
) -> tuple[CommandResult, BuildCommandRecord, str]:
    services = get_compile_services()

    effective_stage = stage or "build"
    current_index = len(session.commands) + 1
    workdir_path = container_repo_path(session, workdir)
    log_path = local_log_path(session, f"{current_index:03d}_{effective_stage}.log")
    services.manager.log_event(
        session,
        "build.command.started",
        stage=effective_stage,
        command=command,
        workdir=workdir_path,
        timeout_seconds=timeout_seconds,
        log_path=log_path,
    )
    started_at = utc_now_iso()
    result = services.runtime.exec(session, command, workdir=workdir_path, timeout_seconds=timeout_seconds, log_path=log_path)
    completed_at = utc_now_iso()

    append_command_record(session, effective_stage, command, workdir_path, log_path, result.exit_code, started_at, completed_at)
    record = session.commands[-1]

    if result.exit_code != 0:
        services.manager.log_event(
            session,
            "build.command.failed",
            stage=effective_stage,
            command=command,
            workdir=workdir_path,
            timeout_seconds=timeout_seconds,
            log_path=log_path,
            exit_code=result.exit_code,
            output=result.combined_output[:4000],
        )
        services.manager.mark_session_status(session, "build_failed", error=result.combined_output[:4000])
        return result, record, f"Command failed at stage '{effective_stage}' with exit code {result.exit_code}. Output:\n{result.combined_output}"

    services.manager.log_event(
        session,
        "build.command.completed",
        stage=effective_stage,
        command=command,
        workdir=workdir_path,
        timeout_seconds=timeout_seconds,
        log_path=log_path,
        exit_code=result.exit_code,
    )
    services.manager.mark_session_status(session, "building")
    return result, record, (
        f"Command succeeded at stage '{effective_stage}'. "
        f"Log saved to {relative_or_original(session, log_path)}. Output:\n{result.combined_output}"
    )


def run_compile_command_json(
    *,
    session: CompileSession,
    command: str,
    workdir: str | None = None,
    timeout_seconds: int = 1200,
    stage: str | None = None,
) -> str:
    result, record, message = run_compile_command_impl(
        session=session,
        command=command,
        workdir=workdir,
        timeout_seconds=timeout_seconds,
        stage=stage,
    )
    return json.dumps(
        {
            "exit_code": result.exit_code,
            "stage": record.stage,
            "log_path": record.log_path,
            "message": message,
        },
        ensure_ascii=False,
        indent=2,
    )


def record_build_artifact_impl(
    *,
    session: CompileSession,
    artifact_path: str,
    artifact_type: str = "build_output",
    copy_to_artifacts: bool = True,
) -> BuildArtifact:
    services = get_compile_services()
    recorded_path = artifact_path
    if copy_to_artifacts:
        destination_name = Path(artifact_path).name
        recorded_path = services.runtime.copy_artifact_to_session(session, artifact_path, destination_name)
    host_recorded_path = Path(session.host_artifacts_dir) / Path(recorded_path).name if copy_to_artifacts else Path(recorded_path)
    artifact = BuildArtifact(
        path=services.manager.relative_path(session, host_recorded_path),
        artifact_type=artifact_type,
        size_bytes=host_recorded_path.stat().st_size if host_recorded_path.exists() else None,
        source_path=artifact_path,
    )
    services.manager.record_artifact(session, artifact)
    return artifact


def _detect_artifact_type(file_output: str) -> str | None:
    normalized = file_output.lower()
    if "elf" in normalized and "executable" in normalized:
        return "executable"
    if "shared object" in normalized:
        return "shared_object"
    if "current ar archive" in normalized:
        return "static_library"
    return None


def _safe_check_name(target: str, suffix: str) -> str:
    safe_target = Path(target).name.replace(" ", "_")
    return f"{safe_target}_{suffix}"


def _run_verification_check(
    *,
    session: CompileSession,
    name: str,
    target: str,
    command: str,
    workdir: str,
    log_filename: str,
    summary_on_success: str,
) -> VerificationCheck:
    services = get_compile_services()
    log_path = local_log_path(session, log_filename)
    result = services.runtime.exec(session, command, workdir=workdir, log_path=log_path)
    passed = result.exit_code == 0
    summary = summary_on_success if passed else (result.combined_output.strip()[:500] or f"Command failed with exit code {result.exit_code}")
    services.manager.log_event(
        session,
        "verify.check.completed",
        name=name,
        target=target,
        command=command,
        log_path=log_path,
        exit_code=result.exit_code,
        passed=passed,
        summary=summary,
    )
    return VerificationCheck(
        name=name,
        target=target,
        command=command,
        passed=passed,
        exit_code=result.exit_code,
        log_path=relative_or_original(session, log_path),
        summary=summary,
    )


def _list_staged_artifact_paths(session: CompileSession) -> list[str]:
    artifact_dir = shell_quote(session.container_artifacts_dir)
    exclude_parts = " ".join(f"-not -path {shell_quote(pattern)}" for pattern in _ARTIFACT_FILE_EXCLUDES)
    find_command = f"find {artifact_dir} -type f {exclude_parts}".strip()
    result = get_compile_services().runtime.exec(
        session,
        find_command,
        workdir=session.container_workspace_dir,
    )
    if result.exit_code != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def verify_build_artifacts_impl(
    *,
    session: CompileSession,
    search_path: str | None = None,
    file_pattern: str | None = None,
    copy_to_artifacts: bool = True,
) -> tuple[CommandResult, list[BuildArtifact], str]:
    services = get_compile_services()
    requested_search_root = search_path or session.container_artifacts_dir
    verify_index = len(session.commands) + 1
    summary_log_path = local_log_path(session, f"{verify_index:03d}_verify.log")
    services.manager.log_event(
        session,
        "verify.started",
        requested_search_root=requested_search_root,
        effective_search_root=session.container_artifacts_dir,
        file_pattern=file_pattern,
        copy_to_artifacts=copy_to_artifacts,
        log_path=summary_log_path,
        skipped=False,
    )
    started_at = utc_now_iso()

    discovered_paths = _list_staged_artifact_paths(session)
    notes: list[str] = []
    if requested_search_root != session.container_artifacts_dir:
        notes.append(
            f"Verification only inspects staged artifacts under {session.container_artifacts_dir}; requested search_path={requested_search_root!r} was ignored."
        )
    if file_pattern:
        discovered_paths = [path for path in discovered_paths if Path(path).match(file_pattern) or Path(path).name == file_pattern]

    checks: list[VerificationCheck] = []
    artifacts: list[BuildArtifact] = []

    for candidate in discovered_paths:
        file_check = _run_verification_check(
            session=session,
            name=_safe_check_name(candidate, "file"),
            target=candidate,
            command=f"file {shell_quote(candidate)}",
            workdir=session.container_workspace_dir,
            log_filename=f"{verify_index:03d}_{Path(candidate).name}_file.log",
            summary_on_success="Artifact type identified successfully.",
        )
        checks.append(file_check)
        if not file_check.passed:
            continue

        file_log_path = Path(session.metadata_path).parent / file_check.log_path
        file_output = file_log_path.read_text(encoding="utf-8") if file_log_path.exists() else ""
        artifact_type = _detect_artifact_type(file_output)
        if artifact_type is None:
            continue

        host_artifact_path = Path(session.host_artifacts_dir) / Path(candidate).name
        artifact = BuildArtifact(
            path=services.manager.relative_path(session, host_artifact_path),
            artifact_type=artifact_type,
            size_bytes=host_artifact_path.stat().st_size if host_artifact_path.exists() else None,
            source_path=candidate,
        )
        artifacts.append(artifact)

        if artifact_type == "executable":
            version_check = _run_verification_check(
                session=session,
                name=_safe_check_name(candidate, "version"),
                target=candidate,
                command=f"{shell_quote(candidate)} -version",
                workdir=session.container_workspace_dir,
                log_filename=f"{verify_index:03d}_{Path(candidate).name}_version.log",
                summary_on_success="Executable produced version output successfully.",
            )
            checks.append(version_check)
            if not version_check.passed:
                fallback_check = _run_verification_check(
                    session=session,
                    name=_safe_check_name(candidate, "version_fallback"),
                    target=candidate,
                    command=f"{shell_quote(candidate)} --version",
                    workdir=session.container_workspace_dir,
                    log_filename=f"{verify_index:03d}_{Path(candidate).name}_version_fallback.log",
                    summary_on_success="Executable produced --version output successfully.",
                )
                checks.append(fallback_check)

    session.artifacts = artifacts
    services.manager.save_session(session)

    completed_at = utc_now_iso()
    result_exit_code = 0 if discovered_paths else 1
    append_command_record(session, "verify", f"verify staged artifacts in {session.container_artifacts_dir}", session.container_workspace_dir, summary_log_path, result_exit_code, started_at, completed_at)

    if not discovered_paths:
        notes.append(f"No staged files were found under {session.container_artifacts_dir}.")
    elif not artifacts:
        notes.append("No executable, shared library, or static archive artifacts were detected among the staged files in /artifacts.")

    failed_checks = sum(1 for check in checks if not check.passed)
    status = "passed" if artifacts and failed_checks == 0 else "failed"
    verification = VerificationResult(
        status=status,
        checks=checks,
        artifact_count=len(artifacts),
        failed_checks=failed_checks,
        notes=notes,
    )
    session.verification = verification
    services.manager.save_session(session)

    summary_lines = [
        "Verification completed.",
        f"status={status}",
        f"artifact_count={len(artifacts)}",
        f"failed_checks={failed_checks}",
    ]
    if artifacts:
        summary_lines.append("artifacts:")
        summary_lines.extend(f"- {artifact.path}" for artifact in artifacts)
    if checks:
        summary_lines.append("checks:")
        summary_lines.extend(
            f"- {check.name}: {'passed' if check.passed else 'failed'}"
            for check in checks
        )
    if notes:
        summary_lines.append("notes:")
        summary_lines.extend(f"- {note}" for note in notes)
    Path(summary_log_path).write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    result = CommandResult(
        exit_code=0 if status == "passed" else 1,
        stdout="\n".join(summary_lines),
        stderr="",
        combined_output="\n".join(summary_lines),
        log_path=summary_log_path,
    )
    services.manager.log_event(
        session,
        "verify.completed",
        log_path=summary_log_path,
        artifact_count=len(artifacts),
        artifacts=[artifact.path for artifact in artifacts],
        failed_checks=failed_checks,
        status=status,
        staged_files=discovered_paths,
    )
    services.manager.mark_session_status(session, "artifacts_verified" if status == "passed" else "verification_failed")
    return result, artifacts, result.combined_output


def verify_build_artifacts_json(
    *,
    session: CompileSession,
    search_path: str | None = None,
    file_pattern: str | None = None,
    copy_to_artifacts: bool = True,
) -> str:
    result, artifacts, message = verify_build_artifacts_impl(
        session=session,
        search_path=search_path,
        file_pattern=file_pattern,
        copy_to_artifacts=copy_to_artifacts,
    )
    return json.dumps(
        {
            "exit_code": result.exit_code,
            "artifact_count": len(artifacts),
            "artifacts": [artifact.__dict__ for artifact in artifacts],
            "verification": session.verification.__dict__ if session.verification else None,
            "message": message,
        },
        ensure_ascii=False,
        indent=2,
    )


def finalize_compile_session_impl(
    *,
    session: CompileSession,
    summary: str | None = None,
    status: str = "completed",
    generate_repro_bundle: bool = True,
) -> CompileSession:
    services = get_compile_services()
    if generate_repro_bundle:
        repro_dir = Path(session.metadata_path).parent / "repro"
        repro_dir.mkdir(parents=True, exist_ok=True)
        build_lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
        for command in session.commands:
            build_lines.append(command.command)
        (repro_dir / "build.sh").write_text("\n".join(build_lines) + "\n", encoding="utf-8")
    services.manager.mark_session_status(session, status, summary=summary)
    services.manager.log_event(
        session,
        "finalize.completed",
        status=status,
        summary=summary,
        generate_repro_bundle=generate_repro_bundle,
    )
    return session


def finalize_compile_session_json(
    *,
    session: CompileSession,
    summary: str | None = None,
    status: str = "completed",
    generate_repro_bundle: bool = True,
) -> str:
    updated = finalize_compile_session_impl(
        session=session,
        summary=summary,
        status=status,
        generate_repro_bundle=generate_repro_bundle,
    )
    return json.dumps(updated.to_dict(), ensure_ascii=False, indent=2)
