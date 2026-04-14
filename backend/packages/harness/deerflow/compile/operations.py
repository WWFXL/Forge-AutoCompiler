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


_services = CompileOperationsServices(
    manager=CompileSessionManager(),
    runtime=CompileDockerRuntime(),
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
    services.runtime.create_container(session)
    services.manager.save_session(session)
    services.manager.mark_session_status(session, "ready")
    return session


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

    log_path = f"{session.host_logs_dir}/001_clone.log"
    started_at = utc_now_iso()
    result = services.runtime.exec(session, clone_command, workdir=session.container_workspace_dir, log_path=log_path)
    completed_at = utc_now_iso()
    append_command_record(session, "clone", clone_command, session.container_workspace_dir, log_path, result.exit_code, started_at, completed_at)

    if result.exit_code != 0:
        services.manager.mark_session_status(session, "failed", error=result.combined_output[:4000])
        return result, f"Clone failed with exit code {result.exit_code}. Output:\n{result.combined_output}"

    sha_result = services.runtime.exec(session, "git -C /workspace/repo rev-parse HEAD", workdir=session.container_workspace_dir)
    if sha_result.exit_code == 0:
        session.commit_sha = sha_result.stdout.strip()
        services.manager.save_session(session)

    services.manager.mark_session_status(session, "source_ready")
    return result, f"Repository cloned successfully to {session.container_repo_dir}. Commit: {session.commit_sha or 'unknown'}"


def inspect_build_system_impl(*, session: CompileSession) -> tuple[str, list[tuple[str, str]], list[str]]:
    services = get_compile_services()

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

    services.manager.mark_session_status(session, "inspected")
    return primary_system, detected, suggested_commands.get(primary_system, suggested_commands["unknown"])


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
    log_path = f"{session.host_logs_dir}/{current_index:03d}_{effective_stage}.log"
    started_at = utc_now_iso()
    result = services.runtime.exec(session, command, workdir=workdir_path, timeout_seconds=timeout_seconds, log_path=log_path)
    completed_at = utc_now_iso()

    append_command_record(session, effective_stage, command, workdir_path, log_path, result.exit_code, started_at, completed_at)
    record = session.commands[-1]

    if result.exit_code != 0:
        services.manager.mark_session_status(session, "failed", error=result.combined_output[:4000])
        return result, record, f"Command failed at stage '{effective_stage}' with exit code {result.exit_code}. Output:\n{result.combined_output}"

    services.manager.mark_session_status(session, "building")
    return result, record, (
        f"Command succeeded at stage '{effective_stage}'. "
        f"Log saved to {relative_or_original(session, log_path)}. Output:\n{result.combined_output}"
    )


def verify_build_artifacts_impl(
    *,
    session: CompileSession,
    search_path: str | None = None,
    file_pattern: str | None = None,
    copy_to_artifacts: bool = True,
) -> tuple[CommandResult, list[BuildArtifact], str]:
    services = get_compile_services()
    search_root = search_path or session.container_repo_dir
    pattern_clause = f" -name {shell_quote(file_pattern)}" if file_pattern else ""
    command = f"find {shell_quote(search_root)} -type f{pattern_clause} -exec file {{}} +"

    log_path = f"{session.host_logs_dir}/{len(session.commands) + 1:03d}_verify.log"
    started_at = utc_now_iso()
    result = services.runtime.exec(session, command, workdir=session.container_workspace_dir, log_path=log_path)
    completed_at = utc_now_iso()
    append_command_record(session, "verify", command, session.container_workspace_dir, log_path, result.exit_code, started_at, completed_at)

    if result.exit_code != 0:
        services.manager.mark_session_status(session, "failed", error=result.combined_output[:4000])
        return result, [], f"Artifact verification failed. Output:\n{result.combined_output}"

    artifacts: list[BuildArtifact] = []
    for line in result.combined_output.splitlines():
        if ":" not in line:
            continue
        source, description = line.split(":", 1)
        description_lower = description.lower()
        if not any(token in description_lower for token in ["elf", "executable", "shared object", "archive"]):
            continue
        source_path = source.strip()
        recorded_path = source_path
        if copy_to_artifacts:
            copied_path = services.manager.copy_artifact_into_session(session, source_path)
            recorded_path = copied_path
        artifact = BuildArtifact(
            path=services.manager.relative_path(session, recorded_path),
            artifact_type=description.strip(),
            size_bytes=Path(recorded_path).stat().st_size if Path(recorded_path).exists() else None,
            source_path=source_path,
        )
        services.manager.record_artifact(session, artifact)
        artifacts.append(artifact)

    services.manager.mark_session_status(session, "artifacts_verified")
    if not artifacts:
        return result, artifacts, "No matching build artifacts were found."
    lines = [f"- {artifact.path} ({artifact.artifact_type})" for artifact in artifacts]
    return result, artifacts, "Verified build artifacts:\n" + "\n".join(lines)


def finalize_compile_session_impl(
    *,
    session: CompileSession,
    summary: str | None = None,
    generate_repro_bundle: bool = True,
) -> dict[str, object]:
    services = get_compile_services()

    if generate_repro_bundle:
        repro_dir = Path(session.metadata_path).parent / "repro"
        repro_dir.mkdir(parents=True, exist_ok=True)
        build_script_path = repro_dir / "build.sh"
        command_lines = [record.command for record in session.commands if record.stage != "verify"]
        script_content = "#!/usr/bin/env bash\nset -euo pipefail\n\n" + "\n".join(command_lines) + "\n"
        build_script_path.write_text(script_content, encoding="utf-8")

        dockerfile_path = repro_dir / "Dockerfile"
        dockerfile_content = (
            f"FROM {session.image}\n"
            "WORKDIR /workspace/repo\n"
            "COPY . /workspace/repo\n"
            "COPY repro/build.sh /repro/build.sh\n"
            "RUN chmod +x /repro/build.sh\n"
            "CMD [\"bash\", \"/repro/build.sh\"]\n"
        )
        dockerfile_path.write_text(dockerfile_content, encoding="utf-8")

    final_status = "completed" if session.status != "failed" else "failed"
    services.runtime.stop_and_remove_container(session)
    services.manager.mark_session_status(session, final_status, summary=summary or session.summary)

    response = {
        "session_id": session.session_id,
        "status": final_status,
        "summary": session.summary,
        "artifacts": [artifact.path for artifact in session.artifacts],
        "logs": [services.manager.relative_path(session, record.log_path) for record in session.commands if record.log_path],
        "repro_files": [
            services.manager.relative_path(session, Path(session.metadata_path).parent / "repro" / "build.sh"),
            services.manager.relative_path(session, Path(session.metadata_path).parent / "repro" / "Dockerfile"),
        ]
        if generate_repro_bundle
        else [],
        "session_root": services.manager.relative_path(session, Path(session.metadata_path).parent),
    }
    return response


def finalize_compile_session_json(*, session: CompileSession, summary: str | None = None, generate_repro_bundle: bool = True) -> str:
    return json.dumps(
        finalize_compile_session_impl(session=session, summary=summary, generate_repro_bundle=generate_repro_bundle),
        ensure_ascii=False,
        indent=2,
    )
