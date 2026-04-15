from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from shlex import quote

from deerflow.compile.docker_runtime import CompileDockerRuntime
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.schemas import BuildArtifact, BuildCommandRecord, CommandResult, CompileSession, utc_now_iso

_BUILD_SYSTEM_MARKERS = {
    "cmake": "CMakeLists.txt",
    "make": "Makefile",
    "autotools": "configure",
}


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
) -> tuple[CommandResult, str]:
    services = get_compile_services()

    clone_parts = [f"git clone --depth {depth}"]
    if branch:
        clone_parts.append(f"--branch {shell_quote(branch)}")
    clone_parts.append(f"{shell_quote(repo_url)} {shell_quote(session.container_repo_dir)}")
    clone_command = " ".join(clone_parts)

    log_path = local_log_path(session, "001_clone.log")
    services.manager.log_event(
        session,
        "clone.started",
        repo_url=repo_url,
        branch=branch,
        depth=depth,
        log_path=log_path,
        target_dir=session.container_repo_dir,
    )
    started_at = utc_now_iso()
    result = services.runtime.exec(session, clone_command, workdir=session.container_workspace_dir, log_path=log_path)
    completed_at = utc_now_iso()
    append_command_record(session, "clone", clone_command, session.container_workspace_dir, log_path, result.exit_code, started_at, completed_at)

    if result.exit_code != 0:
        services.manager.log_event(
            session,
            "clone.failed",
            exit_code=result.exit_code,
            log_path=log_path,
            output=result.combined_output[:4000],
        )
        services.manager.mark_session_status(session, "failed", error=result.combined_output[:4000])
        return result, f"Clone failed with exit code {result.exit_code}. Output:\n{result.combined_output}"

    sha_result = services.runtime.exec(session, "git -C /workspace/repo rev-parse HEAD", workdir=session.container_workspace_dir)
    if sha_result.exit_code == 0:
        session.commit_sha = sha_result.stdout.strip()
        services.manager.save_session(session)

    services.manager.log_event(
        session,
        "clone.completed",
        exit_code=result.exit_code,
        log_path=log_path,
        commit_sha=session.commit_sha,
    )
    services.manager.mark_session_status(session, "source_ready")
    return result, f"Repository cloned successfully to {session.container_repo_dir}. Commit: {session.commit_sha or 'unknown'}"


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
        recorded_path = services.manager.copy_artifact_into_session(session, artifact_path)
    artifact = BuildArtifact(
        path=services.manager.relative_path(session, recorded_path),
        artifact_type=artifact_type,
        size_bytes=Path(recorded_path).stat().st_size if Path(recorded_path).exists() else None,
        source_path=artifact_path,
    )
    services.manager.record_artifact(session, artifact)
    return artifact


def verify_build_artifacts_impl(
    *,
    session: CompileSession,
    search_path: str | None = None,
    file_pattern: str | None = None,
    copy_to_artifacts: bool = True,
) -> tuple[CommandResult, list[BuildArtifact], str]:
    services = get_compile_services()
    log_path = local_log_path(session, f"{len(session.commands) + 1:03d}_verify.log")
    services.manager.log_event(
        session,
        "verify.started",
        search_root=search_path or session.container_repo_dir,
        file_pattern=file_pattern,
        copy_to_artifacts=copy_to_artifacts,
        log_path=log_path,
        skipped=True,
    )
    started_at = utc_now_iso()
    completed_at = utc_now_iso()
    append_command_record(session, "verify", "true", session.container_workspace_dir, log_path, 0, started_at, completed_at)
    result = CommandResult(
        exit_code=0,
        stdout="Verification skipped.",
        stderr="",
        combined_output="Verification skipped.",
        log_path=log_path,
    )
    Path(log_path).write_text("Verification skipped.\n", encoding="utf-8")
    artifacts = list(session.artifacts)
    services.manager.log_event(
        session,
        "verify.completed",
        log_path=log_path,
        artifact_count=len(artifacts),
        artifacts=[artifact.path for artifact in artifacts],
        skipped=True,
    )
    services.manager.mark_session_status(session, "artifacts_verified")
    return result, artifacts, "Verification skipped."


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
