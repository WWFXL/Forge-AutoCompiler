from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from shlex import quote

from deerflow.compile.docker_runtime import CompileDockerRuntime
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.schemas import BuildArtifact, BuildCommandRecord, CommandResult, CompileSession, VerificationCheck, VerificationResult, utc_now_iso

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

    repo_dir = Path(session.leadagent_repo_dir)
    workspace_dir = repo_dir.parent

    clone_command_parts = ["git", "clone", "--depth", str(depth)]
    if branch:
        clone_command_parts.extend(["--branch", branch])
    clone_command_parts.extend([repo_url, str(repo_dir)])

    clone_parts_for_record = [f"git clone --depth {depth}"]
    if branch:
        clone_parts_for_record.append(f"--branch {shell_quote(branch)}")
    clone_parts_for_record.append(f"{shell_quote(repo_url)} {shell_quote(str(repo_dir))}")
    clone_command_for_record = " ".join(clone_parts_for_record)

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
            target_dir=str(repo_dir),
        )
        started_at = utc_now_iso()

        if repo_dir.exists():
            shutil.rmtree(repo_dir)

        run_result = subprocess.run(
            clone_command_parts,
            cwd=str(workspace_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        completed_at = utc_now_iso()
        stdout = run_result.stdout or ""
        stderr = run_result.stderr or ""
        combined_output = stdout + stderr
        Path(log_path).write_text(combined_output, encoding="utf-8")

        result = CommandResult(
            exit_code=run_result.returncode,
            stdout=stdout,
            stderr=stderr,
            combined_output=combined_output,
            log_path=log_path,
        )
        append_command_record(
            session,
            "clone",
            clone_command_for_record,
            str(workspace_dir),
            log_path,
            result.exit_code,
            started_at,
            completed_at,
        )
        last_result = result

        if result.exit_code == 0:
            sha = subprocess.run(
                ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            )
            if sha.returncode == 0:
                session.commit_sha = (sha.stdout or "").strip()
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
            return result, f"Repository cloned successfully to {repo_dir}. Commit: {session.commit_sha or 'unknown'}"

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

    repo_dir = Path(session.leadagent_repo_dir)
    services.manager.log_event(session, "inspect.started", lead_repo_dir=str(repo_dir))
    detected: list[tuple[str, str]] = []
    for build_system, marker in _BUILD_SYSTEM_MARKERS.items():
        if (repo_dir / marker).is_file():
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
        lead_repo_dir=str(repo_dir),
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


def _list_leadagent_artifact_files(session: CompileSession) -> list[Path]:
    base = Path(session.leadagent_artifacts_dir)
    if not base.exists():
        return []
    files: list[Path] = []
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(base)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if "CMakeFiles" in rel.parts:
            continue
        files.append(p)
    return files


def _record_submit_check(
    *,
    checks: list[VerificationCheck],
    name: str,
    target: str,
    passed: bool,
    summary: str,
) -> None:
    checks.append(
        VerificationCheck(
            name=name,
            target=target,
            command="submit_build_result",
            passed=passed,
            exit_code=0 if passed else 1,
            log_path=None,
            summary=summary,
        )
    )


def submit_build_result_impl(*, session: CompileSession) -> str:
    services = get_compile_services()
    submit_index = len(session.commands) + 1
    summary_log_path = local_log_path(session, f"{submit_index:03d}_submit.log")
    services.manager.log_event(
        session,
        "submit.started",
        leadagent_artifacts_dir=session.leadagent_artifacts_dir,
        container_artifacts_dir="/artifacts",
        log_path=summary_log_path,
    )
    started_at = utc_now_iso()

    discovered_files = sorted(_list_leadagent_artifact_files(session), key=lambda p: p.as_posix())
    checks: list[VerificationCheck] = []
    artifacts: list[BuildArtifact] = []
    notes: list[str] = []

    if not discovered_files:
        notes.append("Error: Verification failed. No files were found in /artifacts. Copy your final build outputs into /artifacts and submit again.")
    else:
        base = Path(session.leadagent_artifacts_dir)
        for candidate_path in discovered_files:
            rel = candidate_path.relative_to(base)
            rel_posix = rel.as_posix()
            container_candidate = f"/artifacts/{rel_posix}" if rel_posix else "/artifacts"

            exists = candidate_path.exists()
            _record_submit_check(
                checks=checks,
                name=f"{candidate_path.name}_exists",
                target=rel_posix,
                passed=exists,
                summary=(
                    "Artifact exists in artifacts directory."
                    if exists
                    else f"Error: Verification failed. File '{rel_posix}' does not exist. Copy the final output into /artifacts and submit again."
                ),
            )
            if not exists:
                continue

            size_bytes = candidate_path.stat().st_size
            non_empty = size_bytes > 0
            _record_submit_check(
                checks=checks,
                name=f"{candidate_path.name}_non_empty",
                target=rel_posix,
                passed=non_empty,
                summary=(
                    f"Artifact size is {size_bytes} bytes."
                    if non_empty
                    else f"Error: Verification failed. File '{rel_posix}' is empty. Rebuild or copy the correct output into /artifacts and submit again."
                ),
            )
            if not non_empty:
                continue

            executable = candidate_path.is_file() and bool(candidate_path.stat().st_mode & 0o111)
            if executable:
                smoke_passed = False
                for smoke_command in (
                    f"{shell_quote(container_candidate)} -version",
                    f"{shell_quote(container_candidate)} --version",
                    f"{shell_quote(container_candidate)} --help",
                ):
                    smoke_result = services.runtime.exec(
                        session,
                        smoke_command,
                        workdir="/workspace",
                    )
                    if smoke_result.exit_code == 0:
                        smoke_passed = True
                        break
                _record_submit_check(
                    checks=checks,
                    name=f"{candidate_path.name}_smoke_test",
                    target=rel_posix,
                    passed=smoke_passed,
                    summary=(
                        "Executable artifact completed a smoke test successfully."
                        if smoke_passed
                        else f"Error: Verification failed. File '{rel_posix}' exists but could not be executed successfully. Check missing libraries or submit the correct binary."
                    ),
                )
                if not smoke_passed:
                    continue

            artifacts.append(
                BuildArtifact(
                    path=services.manager.relative_path(session, candidate_path),
                    artifact_type="executable" if executable else "build_output",
                    size_bytes=size_bytes,
                    source_path=container_candidate,
                )
            )

    failed_checks = sum(1 for check in checks if not check.passed)
    status = "passed" if artifacts and failed_checks == 0 else "failed"
    verification = VerificationResult(
        status=status,
        checks=checks,
        artifact_count=len(artifacts),
        failed_checks=failed_checks,
        notes=notes,
    )
    session.artifacts = artifacts
    session.verification = verification
    services.manager.save_session(session)

    completed_at = utc_now_iso()
    append_command_record(
        session,
        "submit",
        "submit build result from /artifacts",
        str(Path(session.metadata_path).parent),
        summary_log_path,
        0 if status == "passed" else 1,
        started_at,
        completed_at,
    )

    payload = {
        "exit_code": 0 if status == "passed" else 1,
        "status": status,
        "artifact_count": len(artifacts),
        "artifacts": [
            {
                "path": artifact.path,
                "source_path": artifact.source_path,
                "artifact_type": artifact.artifact_type,
                "size_bytes": artifact.size_bytes,
            }
            for artifact in artifacts
        ],
        "message": (
            "Build artifacts accepted from /artifacts."
            if status == "passed"
            else (notes[0] if notes else "Error: Verification failed. The submitted artifacts in /artifacts did not pass validation.")
        ),
    }
    Path(summary_log_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    services.manager.log_event(
        session,
        "submit.completed",
        log_path=summary_log_path,
        status=status,
        artifact_count=len(artifacts),
        artifacts=[artifact.path for artifact in artifacts],
        failed_checks=failed_checks,
    )

    if status == "passed":
        finalize_compile_session_impl(session=session, status="completed", generate_repro_bundle=True)
    else:
        services.manager.mark_session_status(session, "verification_failed", error=payload["message"])

    return json.dumps(payload, ensure_ascii=False, indent=2)


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
