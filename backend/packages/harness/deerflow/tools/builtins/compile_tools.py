from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.compile.docker_runtime import CompileDockerRuntime
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.schemas import BuildArtifact, BuildCommandRecord, utc_now_iso

COMPILE_SESSION_STATE_KEY = "compile_session_id"
_BUILD_SYSTEM_MARKERS = {
    "cmake": "CMakeLists.txt",
    "make": "Makefile",
    "cargo": "Cargo.toml",
    "npm": "package.json",
    "go": "go.mod",
    "python": "pyproject.toml",
    "python-legacy": "setup.py",
}


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
    session_id = _get_bound_session_id(runtime)
    if not session_id:
        raise ValueError("No compile session is currently bound. Call prepare_compile_session first.")

    session = get_compile_services().manager.load_session(session_id, _get_thread_id(runtime))
    owner_id = _get_subagent_owner_id(runtime)
    if session.owner_subagent_id and owner_id and session.owner_subagent_id != owner_id:
        raise ValueError("The bound compile session belongs to another subagent execution.")
    return session


def _relative_or_original(session, path: str) -> str:
    return get_compile_services().manager.relative_path(session, path)


def _append_command_record(session, stage: str, command: str, workdir: str, log_path: str, exit_code: int, started_at: str, completed_at: str) -> None:
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
    owner_id = _get_subagent_owner_id(runtime)
    session = services.manager.create_session(thread_id=thread_id, repo_url=repo_url, branch=branch)
    session.owner_subagent_id = owner_id
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
    _append_command_record(session, "clone", clone_command, session.container_workspace_dir, log_path, result.exit_code, started_at, completed_at)

    if result.exit_code != 0:
        services.manager.mark_session_status(session, "failed", error=result.combined_output[:4000])
        return f"Clone failed with exit code {result.exit_code}. Output:\n{result.combined_output}"

    sha_result = services.runtime.exec(session, "git -C /workspace/repo rev-parse HEAD", workdir=session.container_workspace_dir)
    if sha_result.exit_code == 0:
        session.commit_sha = sha_result.stdout.strip()
        services.manager.save_session(session)

    services.manager.mark_session_status(session, "source_ready")
    return f"Repository cloned successfully to {session.container_repo_dir}. Commit: {session.commit_sha or 'unknown'}"


@tool("inspect_build_system", parse_docstring=True)
def inspect_build_system(runtime: ToolRuntime[ContextT, ThreadState]) -> str:
    """Detect the likely build system for the bound repository.

    Returns a concise summary of detected marker files and suggested commands.
    """
    services = get_compile_services()
    session = _load_bound_session(runtime)

    detected: list[tuple[str, str]] = []
    for build_system, marker in _BUILD_SYSTEM_MARKERS.items():
        check_command = f"test -f {session.container_repo_dir}/{marker}"
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
        "cargo": ["cargo build --release"],
        "npm": ["npm install", "npm run build"],
        "go": ["go build ./..."],
        "python": ["python -m build"],
        "python-legacy": ["python setup.py build"],
        "unknown": ["Inspect repository manually and run the appropriate build command"],
    }

    marker_summary = ", ".join(f"{name} ({marker})" for name, marker in detected) if detected else "none"
    command_summary = "; ".join(suggested_commands.get(primary_system, suggested_commands["unknown"]))
    services.manager.mark_session_status(session, "inspected")
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
    services = get_compile_services()
    session = _load_bound_session(runtime)

    effective_stage = stage or "build"
    current_index = len(session.commands) + 1
    workdir_path = session.container_repo_dir if not workdir else f"{session.container_repo_dir}/{workdir.strip('/')}"
    log_path = f"{session.host_logs_dir}/{current_index:03d}_{effective_stage}.log"
    started_at = utc_now_iso()
    result = services.runtime.exec(session, command, workdir=workdir_path, timeout_seconds=timeout_seconds, log_path=log_path)
    completed_at = utc_now_iso()

    _append_command_record(session, effective_stage, command, workdir_path, log_path, result.exit_code, started_at, completed_at)

    if result.exit_code != 0:
        services.manager.mark_session_status(session, "failed", error=result.combined_output[:4000])
        return f"Command failed at stage '{effective_stage}' with exit code {result.exit_code}. Output:\n{result.combined_output}"

    services.manager.mark_session_status(session, "building")
    return f"Command succeeded at stage '{effective_stage}'. Log saved to {_relative_or_original(session, log_path)}. Output:\n{result.combined_output}"


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
    services = get_compile_services()
    session = _load_bound_session(runtime)
    search_root = search_path or session.container_repo_dir
    pattern_clause = f" -name '{file_pattern}'" if file_pattern else ""
    command = f"find {search_root} -type f{pattern_clause} | xargs -r file"

    log_path = f"{session.host_logs_dir}/{len(session.commands) + 1:03d}_verify.log"
    started_at = utc_now_iso()
    result = services.runtime.exec(session, command, workdir=session.container_workspace_dir, log_path=log_path)
    completed_at = utc_now_iso()
    _append_command_record(session, "verify", command, session.container_workspace_dir, log_path, result.exit_code, started_at, completed_at)

    if result.exit_code != 0:
        services.manager.mark_session_status(session, "failed", error=result.combined_output[:4000])
        return f"Artifact verification failed. Output:\n{result.combined_output}"

    artifacts: list[str] = []
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
        artifacts.append(f"- {artifact.path} ({artifact.artifact_type})")

    services.manager.mark_session_status(session, "artifacts_verified")
    if not artifacts:
        return "No matching build artifacts were found."
    return "Verified build artifacts:\n" + "\n".join(artifacts)


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
    services = get_compile_services()
    session = _load_bound_session(runtime)

    if generate_repro_bundle:
        repro_dir = Path(session.host_repro_dir)
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
            "RUN chmod +x /repro/build.sh || true\n"
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
            services.manager.relative_path(session, Path(session.host_repro_dir) / "build.sh"),
            services.manager.relative_path(session, Path(session.host_repro_dir) / "Dockerfile"),
        ]
        if generate_repro_bundle
        else [],
        "session_root": services.manager.relative_path(session, session.host_session_dir),
    }
    return json.dumps(response, ensure_ascii=False, indent=2)
