from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import struct
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from shlex import quote, shlex, split
from typing import BinaryIO
from urllib.parse import urlsplit

from deerflow.compile.docker_runtime import CONTAINER_REPO_DIR, CONTAINER_WORKSPACE_DIR, CompileDockerRuntime, ContainerCleanupResult, ReplayContainerHandle
from deerflow.compile.evidence import (
    EvidenceError,
    allowed_command_role,
    get_active_experiment,
    new_evidence_id,
    record_experiment_event,
)
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.paths import get_replay_artifacts_dir, get_replay_logs_dir, get_replay_recipe_dir, get_replay_workspace_dir
from deerflow.compile.schemas import (
    BuildArtifact,
    BuildCommandRecord,
    CommandResult,
    CompileSession,
    ReplayArtifactComparison,
    ReplayVerificationResult,
    VerificationCheck,
    VerificationResult,
    utc_now_iso,
)

_BUILD_SYSTEM_MARKERS = {
    "cmake": ("CMakeLists.txt",),
    "make": ("Makefile", "GNUmakefile", "makefile"),
    "autotools": ("configure", "configure.ac", "configure.in", "autogen.sh"),
}

_ARTIFACT_FILE_EXCLUDES = [
    "*/.*",
    "*/CMakeFiles/*",
]

_AR_MAGIC = b"!<arch>\n"
_ELF_MAGIC = b"\x7fELF"
_ELF_TYPE_OBJECT = 1
_ELF_TYPE_EXECUTABLE = 2
_ELF_TYPE_DYNAMIC = 3
_ELF_PROGRAM_TYPE_LOAD = 1
_ELF_PROGRAM_TYPE_DYNAMIC = 2
_ELF_PROGRAM_TYPE_INTERPRETER = 3
_ELF_SECTION_TYPE_NULL = 0
_ELF_SECTION_TYPE_STRTAB = 3
_ELF_SECTION_TYPE_NOBITS = 8
_ELF_VERSION_CURRENT = 1
_ELF32_HEADER_SIZE = 52
_ELF64_HEADER_SIZE = 64
_ELF32_PROGRAM_HEADER_SIZE = 32
_ELF64_PROGRAM_HEADER_SIZE = 56
_ELF32_SECTION_HEADER_SIZE = 40
_ELF64_SECTION_HEADER_SIZE = 64
_MAX_ELF_TABLE_ENTRIES = 4096
_AR_MEMBER_HEADER_SIZE = 60
_AR_MEMBER_TRAILER = b"`\n"
_AR_METADATA_MEMBERS = {"/", "//", "/SYM64/"}
_REPLAY_WORKDIR_ROOTS = (
    PurePosixPath(CONTAINER_WORKSPACE_DIR),
    PurePosixPath("/artifacts"),
)
_WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"(?i)(?<![A-Za-z0-9_])(?:[A-Z]:[\\/]|\\\\)")
_WSL_HOST_PATH_RE = re.compile(r"(?i)(?<![A-Za-z0-9_])/mnt/[A-Z](?:/|$)")
_REPLAY_SMOKE_TIMEOUT_SECONDS = 30
_REPLAY_CONTAINER_CREATE_TIMEOUT_SECONDS = 30
_MAX_PERSISTED_SMOKE_OUTPUT = 4000
_TERMINAL_SESSION_STATUSES = {"completed", "failed", "cancelled", "timed_out"}
_HOUSEKEEPING_BUILD_TARGETS = {
    "clean",
    "distclean",
    "help",
    "maintainer-clean",
    "mostlyclean",
}
_BUILD_TOOL_OPTIONS_WITH_VALUE = {
    "--directory",
    "--file",
    "--include-dir",
    "--jobs",
    "--load-average",
    "--output-sync",
    "-C",
    "-f",
    "-I",
    "-j",
    "-l",
    "-O",
}
_DEPENDENCY_SETUP_EXECUTABLES = {
    "apk",
    "apt",
    "apt-get",
    "dnf",
    "pacman",
    "yum",
    "zypper",
}
_SHELL_COMMAND_SEPARATORS = {"(", ")", ";", "&", "&&", "|", "||"}


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


def _load_authoritative_session(session: CompileSession) -> CompileSession:
    services = get_compile_services()
    try:
        return services.manager.load_session(session.session_id, session.thread_id)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return session


def _session_lifecycle_fenced(session: CompileSession) -> bool:
    return session.finalized_at is not None or session.termination_requested_at is not None or session.status in _TERMINAL_SESSION_STATUSES


def _abort_submit_for_lifecycle(
    session: CompileSession,
    *,
    stage: str,
    submit_attempt_id: str | None = None,
    supporting_command_id: str | None = None,
) -> str:
    services = get_compile_services()
    status = session.termination_status or session.status
    if status not in _TERMINAL_SESSION_STATUSES:
        status = "cancelled"
    message = f"Compile session is terminating or finalized with status {status}; submit was ignored."
    services.manager.log_event(
        session,
        "submit.aborted",
        stage=stage,
        status=status,
        finalized_at=session.finalized_at,
        termination_requested_at=session.termination_requested_at,
        submit_attempt_id=submit_attempt_id,
        supporting_command_id=supporting_command_id,
    )
    record_experiment_event(
        session.thread_id,
        "submit.aborted",
        submit_attempt_id=submit_attempt_id,
        supporting_command_id=supporting_command_id,
        session_id=session.session_id,
        stage=stage,
        status=status,
    )
    return json.dumps(
        {
            "exit_code": 1,
            "status": status,
            "candidate_status": "not_committed",
            "replay_status": "not_run",
            "replay_attempt_id": None,
            "submit_attempt_id": submit_attempt_id,
            "supporting_command_id": supporting_command_id,
            "image_id": session.image_id,
            "artifact_count": 0,
            "artifacts": [],
            "message": message,
        },
        ensure_ascii=False,
        indent=2,
    )


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
    *,
    role: str | None = None,
    timeout_seconds: int | None = None,
    duration_seconds: float | None = None,
    timed_out: bool = False,
    termination: str | None = None,
    command_id: str | None = None,
) -> BuildCommandRecord:
    record = BuildCommandRecord(
        stage=stage,
        command=command,
        workdir=workdir,
        command_id=command_id or new_evidence_id("command"),
        role=allowed_command_role(role or stage if stage in {"clone", "inspect"} else role),
        timeout_seconds=timeout_seconds,
        duration_seconds=duration_seconds,
        timed_out=timed_out,
        termination=termination,
        started_at=started_at,
        completed_at=completed_at,
        exit_code=exit_code,
        log_path=log_path,
    )
    get_compile_services().manager.record_command(session, record)
    return record


def _apply_experiment_dependencies(session: CompileSession) -> None:
    active = get_active_experiment(session.thread_id)
    if active is None or not active.policy.required_system_packages:
        return
    services = get_compile_services()
    packages = " ".join(shell_quote(package) for package in active.policy.required_system_packages)
    command = f"apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends {packages}"
    timeout_seconds = 1200
    started_at = utc_now_iso()
    started_monotonic = time.monotonic()
    result = services.runtime.exec(
        session,
        command,
        workdir=CONTAINER_WORKSPACE_DIR,
        timeout_seconds=timeout_seconds,
        log_path=local_log_path(session, "000_benchmark_dependency_setup.log"),
    )
    completed_at = utc_now_iso()
    append_command_record(
        session,
        "bash",
        command,
        CONTAINER_WORKSPACE_DIR,
        result.log_path or local_log_path(session, "000_benchmark_dependency_setup.log"),
        result.exit_code,
        started_at,
        completed_at,
        role="dependency_setup",
        timeout_seconds=timeout_seconds,
        duration_seconds=round(time.monotonic() - started_monotonic, 6),
        timed_out=result.exit_code == 124,
        termination="timeout" if result.exit_code == 124 else ("failed" if result.exit_code != 0 else "completed"),
    )
    if result.exit_code != 0:
        services.manager.mark_session_status(session, "failed", error="Benchmark dependency setup failed.")
        record_experiment_event(
            session.thread_id,
            "failure.recorded",
            failure_id=new_evidence_id("failure"),
            session_id=session.session_id,
            domain="build",
            classification="dependency_setup_failed",
            primary=True,
        )
        raise RuntimeError("Benchmark dependency setup failed before compilation")


def prepare_compile_session_impl(
    *,
    thread_id: str,
    repo_url: str,
    branch: str | None = None,
    task_description: str | None = None,
    owner_id: str | None = None,
    run_id: str | None = None,
) -> CompileSession:
    services = get_compile_services()
    active = get_active_experiment(thread_id)
    if active is not None:
        if repo_url.rstrip("/") != active.policy.expected_repo_url.rstrip("/"):
            raise EvidenceError("Compile repository does not match the active benchmark case")
    session_id = uuid.uuid4().hex[:12]
    with services.manager.session_lock(thread_id, session_id):
        session = services.manager.create_session(
            thread_id=thread_id,
            repo_url=repo_url,
            branch=branch,
            run_id=run_id,
            session_id=session_id,
        )
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
        if active is not None:
            if session.image != active.policy.compile_image or session.image_id != active.policy.image_id:
                services.runtime.stop_and_remove_container(session)
                raise EvidenceError("Compile container identity does not match the active benchmark policy")
            record_experiment_event(
                thread_id,
                "session.bound",
                session_id=session.session_id,
                repo_url=session.repo_url,
                image=session.image,
                image_id=session.image_id,
            )
            _apply_experiment_dependencies(session)
        services.manager.save_session(session)
        services.manager.mark_session_status(session, "ready")
        services.manager.log_event(
            session,
            "prepare.completed",
            container_id=session.container_id,
            container_name=session.container_name,
            image_id=session.image_id,
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
    effective_branch = branch if branch is not None else session.branch
    active = get_active_experiment(session.thread_id)
    expected_commit_sha = active.policy.expected_commit_sha if active is not None else None
    if active is not None and repo_url.rstrip("/") != active.policy.expected_repo_url.rstrip("/"):
        raise EvidenceError("Clone repository does not match the active benchmark case")
    session.repo_url = repo_url
    session.branch = effective_branch
    services.manager.save_session(session)

    if expected_commit_sha:
        object_format = "sha256" if len(expected_commit_sha) == 64 else "sha1"
        attempt_command = " && ".join(
            (
                f"rm -rf -- {shell_quote(CONTAINER_REPO_DIR)}",
                f"git init --object-format={object_format} {shell_quote(CONTAINER_REPO_DIR)}",
                f"git config --global --replace-all safe.directory {shell_quote(CONTAINER_REPO_DIR)}",
                f"git -C {shell_quote(CONTAINER_REPO_DIR)} remote add origin {shell_quote(repo_url)}",
                f"git -C {shell_quote(CONTAINER_REPO_DIR)} fetch --depth {max(1, depth)} origin {shell_quote(expected_commit_sha)}",
                f"git -C {shell_quote(CONTAINER_REPO_DIR)} checkout --detach FETCH_HEAD",
                f'test "$(git -C {shell_quote(CONTAINER_REPO_DIR)} rev-parse HEAD)" = {shell_quote(expected_commit_sha)}',
            )
        )
    else:
        clone_command_parts = ["git clone", f"--depth {depth}"]
        if effective_branch:
            clone_command_parts.append(f"--branch {shell_quote(effective_branch)}")
        clone_command_parts.append(f"{shell_quote(repo_url)} {shell_quote(CONTAINER_REPO_DIR)}")
        clone_command = " ".join(clone_command_parts)
        attempt_command = f"rm -rf -- {shell_quote(CONTAINER_REPO_DIR)} && {clone_command}"

    retries = max(1, max_retries)
    last_result: CommandResult | None = None

    for attempt in range(1, retries + 1):
        log_filename = f"001_clone_attempt_{attempt}.log" if retries > 1 else "001_clone.log"
        log_path = local_log_path(session, log_filename)
        services.manager.log_event(
            session,
            "clone.started",
            repo_url=repo_url,
            branch=effective_branch,
            depth=depth,
            attempt=attempt,
            max_retries=retries,
            log_path=log_path,
            target_dir=str(repo_dir),
        )
        started_at = utc_now_iso()
        started_monotonic = time.monotonic()

        result = services.runtime.exec(
            session,
            attempt_command,
            workdir=CONTAINER_WORKSPACE_DIR,
            log_path=log_path,
        )
        completed_at = utc_now_iso()
        append_command_record(
            session,
            "clone",
            attempt_command,
            CONTAINER_WORKSPACE_DIR,
            log_path,
            result.exit_code,
            started_at,
            completed_at,
            role="clone",
            timeout_seconds=600,
            duration_seconds=round(time.monotonic() - started_monotonic, 6),
            timed_out=result.exit_code == 124,
            termination="timeout" if result.exit_code == 124 else ("failed" if result.exit_code != 0 else "completed"),
        )
        last_result = result

        if result.exit_code == 0:
            sha = services.runtime.exec(
                session,
                f"git config --global --replace-all safe.directory {shell_quote(CONTAINER_REPO_DIR)} && git -C {shell_quote(CONTAINER_REPO_DIR)} rev-parse HEAD",
                workdir=CONTAINER_WORKSPACE_DIR,
            )
            if sha.exit_code == 0:
                session.commit_sha = (sha.stdout or "").strip()
                services.manager.save_session(session)
            if expected_commit_sha and session.commit_sha != expected_commit_sha:
                services.manager.mark_session_status(session, "failed", error="Cloned commit does not match the benchmark case.")
                raise EvidenceError("Cloned commit does not match the active benchmark policy")

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


def _build_system_marker_probe_command() -> str:
    statements = [f"test -d {shell_quote(CONTAINER_REPO_DIR)} || exit 66"]
    for build_system, markers in _BUILD_SYSTEM_MARKERS.items():
        branches = []
        for index, marker in enumerate(markers):
            keyword = "if" if index == 0 else "elif"
            marker_path = f"{CONTAINER_REPO_DIR}/{marker}"
            branches.append(f"{keyword} test -f {shell_quote(marker_path)}; then printf '%s\\t%s\\n' {shell_quote(build_system)} {shell_quote(marker)}")
        statements.append("; ".join(branches) + "; fi")
    return "\n".join(statements)


def _detected_build_system_markers(stdout: str) -> list[tuple[str, str]]:
    observed = [line for line in stdout.splitlines() if line]
    allowed = {f"{build_system}\t{marker}" for build_system, markers in _BUILD_SYSTEM_MARKERS.items() for marker in markers}
    if len(observed) != len(set(observed)) or any(line not in allowed for line in observed):
        raise RuntimeError("Compile container returned invalid build-system marker evidence")

    observed_set = set(observed)
    detected: list[tuple[str, str]] = []
    for build_system, markers in _BUILD_SYSTEM_MARKERS.items():
        marker = next((candidate for candidate in markers if f"{build_system}\t{candidate}" in observed_set), None)
        if marker is not None:
            detected.append((build_system, marker))
    return detected


def inspect_build_system_impl(*, session: CompileSession) -> tuple[str, list[tuple[str, str]], list[str]]:
    services = get_compile_services()

    repo_dir = Path(session.leadagent_repo_dir)
    services.manager.log_event(
        session,
        "inspect.started",
        lead_repo_dir=str(repo_dir),
        container_repo_dir=CONTAINER_REPO_DIR,
    )
    probe = services.runtime.exec(
        session,
        _build_system_marker_probe_command(),
        workdir=CONTAINER_WORKSPACE_DIR,
        timeout_seconds=30,
    )
    if probe.exit_code != 0:
        services.manager.log_event(
            session,
            "inspect.failed",
            container_repo_dir=CONTAINER_REPO_DIR,
            exit_code=probe.exit_code,
        )
        raise RuntimeError("Failed to inspect build-system markers inside the compile container")
    detected = _detected_build_system_markers(probe.stdout)

    session.build_system_capabilities = [build_system for build_system, _marker in detected]
    if detected:
        primary_system = detected[0][0]
        session.build_system = primary_system
    else:
        primary_system = "unknown"
        session.build_system = None
    services.manager.save_session(session)

    autotools_marker = next((marker for build_system, marker in detected if build_system == "autotools"), None)
    autotools_commands = {
        "configure": ["chmod +x ./configure && ./configure", "make -j"],
        "autogen.sh": ["chmod +x ./autogen.sh && ./autogen.sh", "make -j"],
        "configure.ac": ["autoreconf -fi && ./configure", "make -j"],
        "configure.in": ["autoreconf -fi && ./configure", "make -j"],
    }
    suggested_commands = {
        "cmake": ["mkdir -p build && cd build && cmake ..", "cmake --build build -j"],
        "make": ["make -j"],
        "autotools": autotools_commands.get(autotools_marker, ["autoreconf -fi && ./configure", "make -j"]),
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
            "build_system_capabilities": session.build_system_capabilities,
            "detected": detected,
            "suggested_commands": suggested_commands,
        },
        ensure_ascii=False,
        indent=2,
    )


def _check_replay_deadline(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise _ReplayVerificationFailure("timeout", "Clean replay exceeded its total timeout.")


def _list_artifact_files(base: Path, *, deadline: float | None = None) -> list[Path]:
    _check_replay_deadline(deadline)
    if not base.exists():
        return []
    try:
        resolved_base = base.resolve(strict=True)
    except OSError:
        return []
    files: list[Path] = []
    for p in base.rglob("*"):
        _check_replay_deadline(deadline)
        if p.is_symlink():
            continue
        try:
            resolved_path = p.resolve(strict=True)
        except OSError:
            continue
        if not resolved_path.is_relative_to(resolved_base) or not resolved_path.is_file():
            continue
        rel = p.relative_to(base)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if "CMakeFiles" in rel.parts:
            continue
        files.append(p)
    return files


def _list_leadagent_artifact_files(session: CompileSession) -> list[Path]:
    return _list_artifact_files(Path(session.leadagent_artifacts_dir))


def _sha256_file(path: Path, *, deadline: float | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            _check_replay_deadline(deadline)
            digest.update(chunk)
    _check_replay_deadline(deadline)
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _persisted_output(output: str) -> str:
    return output[:_MAX_PERSISTED_SMOKE_OUTPUT]


def _table_fits(*, offset: int, entry_size: int, entry_count: int, file_size: int, minimum_entry_size: int) -> bool:
    return offset > 0 and entry_size >= minimum_entry_size and 0 < entry_count <= _MAX_ELF_TABLE_ENTRIES and offset + entry_size * entry_count <= file_size


def _has_valid_object_sections(
    stream: BinaryIO,
    *,
    base_offset: int,
    file_size: int,
    elf_class: int,
    byte_prefix: str,
    section_header_offset: int,
    section_header_size: int,
    section_header_count: int,
    section_name_index: int,
    deadline: float | None = None,
) -> bool:
    if section_header_count < 2 or not 0 < section_name_index < section_header_count:
        return False

    meaningful_section_found = False
    valid_name_table = False
    for index in range(section_header_count):
        _check_replay_deadline(deadline)
        stream.seek(base_offset + section_header_offset + index * section_header_size)
        raw = stream.read(_ELF32_SECTION_HEADER_SIZE if elf_class == 1 else _ELF64_SECTION_HEADER_SIZE)
        try:
            if elf_class == 1:
                fields = struct.unpack(f"{byte_prefix}IIIIIIIIII", raw)
            else:
                fields = struct.unpack(f"{byte_prefix}IIQQQQIIQQ", raw)
        except struct.error:
            return False

        section_type = fields[1]
        section_offset = fields[4]
        section_size = fields[5]
        if index == 0:
            if section_type != _ELF_SECTION_TYPE_NULL:
                return False
            continue
        if section_type == _ELF_SECTION_TYPE_NULL:
            continue
        if section_type != _ELF_SECTION_TYPE_NOBITS and section_size > 0:
            if section_offset <= 0 or section_offset + section_size > file_size:
                return False
            meaningful_section_found = True
        elif section_type == _ELF_SECTION_TYPE_NOBITS and section_size > 0:
            meaningful_section_found = True
        if index == section_name_index:
            valid_name_table = section_type == _ELF_SECTION_TYPE_STRTAB and section_size > 0

    return meaningful_section_found and valid_name_table


def _classify_elf_stream(
    stream: BinaryIO,
    *,
    base_offset: int,
    file_size: int,
    deadline: float | None = None,
) -> str | None:
    _check_replay_deadline(deadline)
    if file_size < _ELF32_HEADER_SIZE:
        return None

    stream.seek(base_offset)
    header = stream.read(_ELF64_HEADER_SIZE)
    if not header.startswith(_ELF_MAGIC) or len(header) < _ELF32_HEADER_SIZE:
        return None

    elf_class = header[4]
    data_encoding = header[5]
    if data_encoding == 1:
        byte_prefix = "<"
    elif data_encoding == 2:
        byte_prefix = ">"
    else:
        return None
    if header[6] != _ELF_VERSION_CURRENT:
        return None

    try:
        if elf_class == 1:
            if len(header) < _ELF32_HEADER_SIZE:
                return None
            fields = struct.unpack_from(f"{byte_prefix}HHIIIIIHHHHHH", header, 16)
            expected_header_size = _ELF32_HEADER_SIZE
            expected_program_header_size = _ELF32_PROGRAM_HEADER_SIZE
            expected_section_header_size = _ELF32_SECTION_HEADER_SIZE
        elif elf_class == 2:
            if len(header) < _ELF64_HEADER_SIZE:
                return None
            fields = struct.unpack_from(f"{byte_prefix}HHIQQQIHHHHHH", header, 16)
            expected_header_size = _ELF64_HEADER_SIZE
            expected_program_header_size = _ELF64_PROGRAM_HEADER_SIZE
            expected_section_header_size = _ELF64_SECTION_HEADER_SIZE
        else:
            return None
    except struct.error:
        return None

    (
        elf_type,
        machine,
        elf_version,
        entry_point,
        program_header_offset,
        section_header_offset,
        _flags,
        header_size,
        program_header_size,
        program_header_count,
        section_header_size,
        section_header_count,
        section_name_index,
    ) = fields
    if machine == 0 or elf_version != _ELF_VERSION_CURRENT or header_size != expected_header_size:
        return None

    if elf_type == _ELF_TYPE_OBJECT:
        if not _table_fits(
            offset=section_header_offset,
            entry_size=section_header_size,
            entry_count=section_header_count,
            file_size=file_size,
            minimum_entry_size=expected_section_header_size,
        ):
            return None
        if not _has_valid_object_sections(
            stream,
            base_offset=base_offset,
            file_size=file_size,
            elf_class=elf_class,
            byte_prefix=byte_prefix,
            section_header_offset=section_header_offset,
            section_header_size=section_header_size,
            section_header_count=section_header_count,
            section_name_index=section_name_index,
            deadline=deadline,
        ):
            return None
        return "object"

    if elf_type not in {_ELF_TYPE_EXECUTABLE, _ELF_TYPE_DYNAMIC}:
        return None
    if not _table_fits(
        offset=program_header_offset,
        entry_size=program_header_size,
        entry_count=program_header_count,
        file_size=file_size,
        minimum_entry_size=expected_program_header_size,
    ):
        return None

    has_data_load_segment = False
    has_dynamic_segment = False
    has_interpreter = False
    for index in range(program_header_count):
        _check_replay_deadline(deadline)
        offset = base_offset + program_header_offset + index * program_header_size
        stream.seek(offset)
        raw = stream.read(expected_program_header_size)
        try:
            if elf_class == 1:
                program_fields = struct.unpack(f"{byte_prefix}IIIIIIII", raw)
                program_type, segment_offset, _vaddr, _paddr, file_segment_size, memory_segment_size, _segment_flags, _segment_align = program_fields
            else:
                program_fields = struct.unpack(f"{byte_prefix}IIQQQQQQ", raw)
                program_type, _segment_flags, segment_offset, _vaddr, _paddr, file_segment_size, memory_segment_size, _segment_align = program_fields
        except struct.error:
            return None
        if memory_segment_size < file_segment_size:
            return None
        if file_segment_size > 0 and (segment_offset < 0 or segment_offset + file_segment_size > file_size):
            return None
        if program_type == _ELF_PROGRAM_TYPE_LOAD and file_segment_size > 0:
            has_data_load_segment = True
        elif program_type == _ELF_PROGRAM_TYPE_DYNAMIC and file_segment_size > 0:
            has_dynamic_segment = True
        elif program_type == _ELF_PROGRAM_TYPE_INTERPRETER:
            if file_segment_size < 2 or segment_offset <= 0:
                return None
            stream.seek(base_offset + segment_offset)
            interpreter = stream.read(file_segment_size)
            if len(interpreter) != file_segment_size or not interpreter.endswith(b"\0"):
                return None
            has_interpreter = True

    if not has_data_load_segment:
        return None
    if elf_type == _ELF_TYPE_EXECUTABLE:
        return "executable" if entry_point != 0 else None
    if has_interpreter or entry_point != 0:
        return "executable"
    return "shared_library" if has_dynamic_segment else None


def _classify_archive_stream(
    stream: BinaryIO,
    *,
    file_size: int,
    deadline: float | None = None,
) -> str | None:
    if file_size < len(_AR_MAGIC) + _AR_MEMBER_HEADER_SIZE:
        return None

    offset = len(_AR_MAGIC)
    compiled_member_found = False
    while offset < file_size:
        _check_replay_deadline(deadline)
        if offset + _AR_MEMBER_HEADER_SIZE > file_size:
            return None
        stream.seek(offset)
        member_header = stream.read(_AR_MEMBER_HEADER_SIZE)
        if len(member_header) != _AR_MEMBER_HEADER_SIZE or member_header[58:60] != _AR_MEMBER_TRAILER:
            return None
        try:
            member_size = int(member_header[48:58].decode("ascii").strip())
            member_name = member_header[:16].decode("ascii").strip()
        except (UnicodeDecodeError, ValueError):
            return None
        if member_size < 0:
            return None

        payload_offset = offset + _AR_MEMBER_HEADER_SIZE
        payload_size = member_size
        payload_end = payload_offset + payload_size
        if payload_end > file_size:
            return None

        if member_name.startswith("#1/"):
            try:
                embedded_name_size = int(member_name[3:])
            except ValueError:
                return None
            if embedded_name_size < 0 or embedded_name_size > payload_size:
                return None
            payload_offset += embedded_name_size
            payload_size -= embedded_name_size

        if member_name not in _AR_METADATA_MEMBERS:
            member_type = _classify_elf_stream(
                stream,
                base_offset=payload_offset,
                file_size=payload_size,
                deadline=deadline,
            )
            compiled_member_found = compiled_member_found or member_type == "object"

        offset = payload_end + (member_size % 2)
        if offset > file_size:
            return None

    return "static_library" if compiled_member_found else None


def _classify_compiled_artifact(path: Path, *, deadline: float | None = None) -> str | None:
    """Classify supported Linux C/C++ outputs from file contents."""
    try:
        _check_replay_deadline(deadline)
        if path.is_symlink() or not path.is_file():
            return None
        file_size = path.stat().st_size
        with path.open("rb") as stream:
            magic = stream.read(len(_AR_MAGIC))
            if magic == _AR_MAGIC:
                return _classify_archive_stream(stream, file_size=file_size, deadline=deadline)
            return _classify_elf_stream(stream, base_offset=0, file_size=file_size, deadline=deadline)
    except OSError:
        return None


def _record_submit_check(
    *,
    checks: list[VerificationCheck],
    name: str,
    target: str,
    passed: bool,
    summary: str,
    expected=None,
    actual=None,
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
            expected=expected,
            actual=actual,
        )
    )


def _artifact_evidence_snapshot(artifacts: list[BuildArtifact]) -> list[dict]:
    snapshots: list[dict] = []
    for artifact in artifacts:
        try:
            relative_path = _artifact_relative_path(artifact)
        except ValueError:
            relative_path = None
        snapshots.append(
            {
                "path": relative_path,
                "artifact_type": artifact.artifact_type,
                "size_bytes": artifact.size_bytes,
                "sha256": artifact.sha256,
                "smoke_exit_code": artifact.smoke_exit_code,
                "smoke_output_sha256": artifact.smoke_output_sha256,
            }
        )
    return snapshots


def _check_evidence_snapshot(checks: list[VerificationCheck]) -> list[dict]:
    return [
        {
            "name": check.name,
            "passed": check.passed,
            "exit_code": check.exit_code,
        }
        for check in checks
    ]


def _replay_artifact_evidence_snapshot(
    artifacts: list[ReplayArtifactComparison],
) -> list[dict]:
    return [
        {
            "path": artifact.path,
            "expected_type": artifact.expected_type,
            "actual_type": artifact.actual_type,
            "expected_size_bytes": artifact.expected_size_bytes,
            "actual_size_bytes": artifact.actual_size_bytes,
            "expected_sha256": artifact.expected_sha256,
            "actual_sha256": artifact.actual_sha256,
            "expected_smoke_exit_code": artifact.expected_smoke_exit_code,
            "actual_smoke_exit_code": artifact.actual_smoke_exit_code,
            "expected_smoke_output_sha256": artifact.expected_smoke_output_sha256,
            "actual_smoke_output_sha256": artifact.actual_smoke_output_sha256,
            "passed": artifact.passed,
            "mismatches": list(artifact.mismatches),
        }
        for artifact in artifacts
    ]


def _record_replay_failure(
    attempt: ReplayVerificationResult,
    classification: str,
) -> None:
    if attempt.primary_failure_classification is None:
        attempt.primary_failure_classification = classification
    elif classification != attempt.primary_failure_classification and classification not in attempt.secondary_failure_classifications:
        attempt.secondary_failure_classifications.append(classification)
    attempt.failure_classification = attempt.primary_failure_classification


def _commit_submit_verification(
    *,
    session: CompileSession,
    artifacts: list[BuildArtifact],
    verification: VerificationResult,
    status: str,
    error: str | None,
) -> bool:
    services = get_compile_services()
    with services.manager.session_lock(session.thread_id, session.session_id):
        current = _load_authoritative_session(session)
        if _session_lifecycle_fenced(current):
            session.__dict__.update(current.__dict__)
            return False
        current.artifacts = list(artifacts)
        current.verification = verification
        services.manager.mark_session_status(current, status, error=error)
        session.__dict__.update(current.__dict__)
        return True


def _command_contains_arguments(command: str, expected: tuple[str, ...]) -> bool:
    if not expected:
        return True
    try:
        tokens = split(command, posix=True)
    except ValueError:
        return False
    token_iterator = iter(tokens)
    return all(any(token == argument for token in token_iterator) for argument in expected)


def _successful_configure_arguments_observed(
    commands: list[BuildCommandRecord],
    expected: tuple[str, ...],
) -> bool:
    return any(command.exit_code == 0 and not command.timed_out and "configure" in infer_command_roles(command.command) and _command_contains_arguments(command.command, expected) for command in commands)


def _command_invokes(command: str, executable: str) -> bool:
    try:
        lexer = shlex(command.replace("\n", ";"), posix=True, punctuation_chars="();&|")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return False
    expect_executable = True
    wrappers = {"command", "env", "sudo", "time"}
    separators = {"(", ")", ";", "&", "&&", "|", "||"}
    for token in tokens:
        if token in separators:
            expect_executable = True
            continue
        if not expect_executable:
            continue
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token) or token.startswith("-"):
            continue
        candidate = PurePosixPath(token).name
        if candidate in wrappers:
            continue
        if candidate == executable:
            return True
        expect_executable = False
    return False


def _shell_command_segments(command: str) -> list[list[str]]:
    try:
        lexer = shlex(command.replace("\n", ";"), posix=True, punctuation_chars="();&|")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return []

    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in _SHELL_COMMAND_SEPARATORS:
            if current:
                segments.append(current)
                current = []
            continue
        current.append(token)
    if current:
        segments.append(current)
    return segments


def _command_invocation(segment: list[str]) -> tuple[str, list[str]] | None:
    wrappers = {"command", "env", "sudo", "time"}
    for index, token in enumerate(segment):
        if token == "--" or token.startswith("-") or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token):
            continue
        executable = PurePosixPath(token).name
        if executable in wrappers:
            continue
        return executable, segment[index + 1 :]
    return None


def _build_tool_invokes_real_target(arguments: list[str]) -> bool:
    targets: list[str] = []
    skip_option_value = False
    for argument in arguments:
        if skip_option_value:
            skip_option_value = False
            continue
        if argument in _BUILD_TOOL_OPTIONS_WITH_VALUE:
            skip_option_value = True
            continue
        if argument.startswith("-") or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", argument):
            continue
        targets.append(argument)
    return not targets or any(target not in _HOUSEKEEPING_BUILD_TARGETS for target in targets)


def _cmake_invokes_real_build(arguments: list[str]) -> bool:
    if "--build" not in arguments:
        return False
    target_index = next((index for index, token in enumerate(arguments) if token in {"--target", "-t"}), None)
    if target_index is None:
        return True
    targets: list[str] = []
    for argument in arguments[target_index + 1 :]:
        if argument == "--" or argument.startswith("-"):
            break
        targets.append(argument)
    return not targets or any(target not in _HOUSEKEEPING_BUILD_TARGETS for target in targets)


def _command_mentions_container_path(command: str, path: str) -> bool:
    return re.search(rf"{re.escape(path)}(?:/|(?![A-Za-z0-9_.-]))", command) is not None


def _infer_command_roles(command: str, *, depth: int) -> set[str]:
    roles: set[str] = set()
    stages_artifacts = _command_mentions_container_path(command, "/artifacts")
    for segment in _shell_command_segments(command):
        invocation = _command_invocation(segment)
        if invocation is None:
            continue
        executable, arguments = invocation
        segment_text = " ".join(segment)

        if executable in _DEPENDENCY_SETUP_EXECUTABLES:
            roles.add("dependency_setup")
        if executable == "sleep":
            roles.add("replay_delay")

        if executable == "cmake":
            if "--build" in arguments:
                roles.add("build" if _cmake_invokes_real_build(arguments) else "housekeeping")
            elif "--install" not in arguments and "-E" not in arguments and "--open" not in arguments:
                roles.add("configure")
            if stages_artifacts and ("--install" in arguments or ("-E" in arguments and any(argument in {"copy", "copy_if_different"} for argument in arguments))):
                roles.add("artifact_stage")
            continue

        if executable in {"make", "gmake", "ninja"}:
            installs_artifacts = stages_artifacts and "install" in arguments
            if installs_artifacts:
                roles.add("artifact_stage")
            else:
                roles.add("build" if _build_tool_invokes_real_target(arguments) else "housekeeping")
            continue

        if executable in {"configure", "autogen.sh", "autoreconf"}:
            roles.add("configure")
            continue

        if stages_artifacts and executable in {"cp", "install"}:
            roles.add("artifact_stage")
            continue

        if executable in {"bash", "sh"}:
            if any(PurePosixPath(argument).name in {"configure", "autogen.sh"} for argument in arguments):
                roles.add("configure")
            inline_command = next(
                (arguments[index + 1] for index, argument in enumerate(arguments[:-1]) if argument.startswith("-") and "c" in argument[1:]),
                None,
            )
            if inline_command is not None and depth < 2:
                roles.update(_infer_command_roles(inline_command, depth=depth + 1))

        if stages_artifacts and re.search(r"(?:^|\s)(?:cp|install)\s", segment_text) is not None:
            roles.add("artifact_stage")

    return roles


def infer_command_roles(command: str) -> set[str]:
    """Infer every control-plane role present in a possibly compound shell command."""

    return _infer_command_roles(command, depth=0)


def infer_command_role(command: str) -> str | None:
    """Resolve the primary evidence role while retaining compound-role analysis."""

    roles = infer_command_roles(command)
    for role in ("build", "configure", "dependency_setup", "replay_delay", "artifact_stage"):
        if role in roles:
            return role
    return None


def resolve_command_role(command: str, declared_role: str | None) -> tuple[str, str | None]:
    """Resolve a model-declared role against deterministic command evidence."""

    declared = allowed_command_role(declared_role)
    inferred = infer_command_role(command)
    if inferred is not None:
        return inferred, inferred
    if declared in {"configure", "build", "artifact_stage"}:
        return "other", None
    return declared, None


def validate_experiment_build_arguments(
    session: CompileSession,
    command: str,
) -> tuple[bool, str | None, int]:
    """Validate frozen configure arguments before an experiment build executes."""

    active = get_active_experiment(session.thread_id)
    command_roles = infer_command_roles(command)
    if active is None or "build" not in command_roles:
        return True, None, 0

    expected_arguments: tuple[str, ...]
    failure: str
    if active.policy.selected_build_system == "cmake":
        expected_arguments = active.policy.cmake_arguments
        failure = "cmake_arguments_not_observed"
    elif active.policy.selected_build_system == "autotools":
        expected_arguments = active.policy.configure_arguments
        failure = "configure_arguments_not_observed"
    else:
        return True, None, 0

    if not expected_arguments:
        return True, None, 0

    observed = _successful_configure_arguments_observed(
        session.commands,
        expected_arguments,
    )
    if "configure" in command_roles:
        observed = observed or _command_contains_arguments(command, expected_arguments)
    return observed, None if observed else failure, len(expected_arguments)


def _configure_command_build_system(command: str) -> str | None:
    if infer_command_role(command) == "configure" and _command_invokes(command, "cmake"):
        return "cmake"
    if infer_command_role(command) == "configure" and any(_command_invokes(command, executable) for executable in ("configure", "autogen.sh", "autoreconf")):
        return "autotools"
    return None


def _infer_executed_build_system(
    commands: list[BuildCommandRecord],
    supporting_command_id: str | None,
) -> str | None:
    supporting_index = next(
        (index for index, command in enumerate(commands) if command.command_id == supporting_command_id),
        None,
    )
    if supporting_index is None:
        return None
    supporting = commands[supporting_index]
    if supporting.role != "build" or supporting.exit_code != 0 or supporting.timed_out:
        return None

    if _command_invokes(supporting.command, "cmake"):
        return "cmake"
    if _command_invokes(supporting.command, "configure"):
        return "autotools"

    successful_configures = [command for command in commands[:supporting_index] if command.role == "configure" and command.exit_code == 0 and not command.timed_out]
    for configure in reversed(successful_configures):
        configured_system = _configure_command_build_system(configure.command)
        if configured_system is not None:
            return configured_system

    if _command_invokes(supporting.command, "make") or _command_invokes(supporting.command, "gmake"):
        return "make"
    return None


def _persist_executed_build_system(session: CompileSession, executed_build_system: str | None) -> None:
    services = get_compile_services()
    with services.manager.session_lock(session.thread_id, session.session_id):
        current = _load_authoritative_session(session)
        current.executed_build_system = executed_build_system
        if executed_build_system is not None:
            current.build_system = executed_build_system
        services.manager.save_session(current)
        session.__dict__.update(current.__dict__)


def _experiment_submit_constraints(
    session: CompileSession,
    supporting_command_id: str | None,
) -> tuple[bool, list[str], str | None]:
    active = get_active_experiment(session.thread_id)
    if active is None:
        return True, [], None
    failures: list[str] = []
    selected_build_system = session.selected_build_system
    expected_build_system = active.policy.selected_build_system
    executed_build_system = _infer_executed_build_system(session.commands, supporting_command_id)
    selection_matches = selected_build_system == expected_build_system
    execution_matches = executed_build_system is not None and executed_build_system == selected_build_system
    record_experiment_event(
        session.thread_id,
        "build.execution_checked",
        session_id=session.session_id,
        expected_build_system=expected_build_system,
        selected_build_system=selected_build_system,
        observed_build_system=executed_build_system,
        detected_build_systems=list(session.build_system_capabilities),
        matches=selection_matches and execution_matches,
        submit_allowed=selection_matches and execution_matches,
    )
    identity_failure: str | None = None
    if not selection_matches:
        identity_failure = "build_system_selection_mismatch"
    elif executed_build_system is None:
        identity_failure = "build_system_unproven"
    elif not execution_matches:
        identity_failure = "build_system_mismatch"
    if identity_failure is not None:
        failures.append(identity_failure)
        record_experiment_event(
            session.thread_id,
            "protocol.deviation",
            phase="submit",
            classification=identity_failure,
            session_id=session.session_id,
            expected_build_system=expected_build_system,
            selected_build_system=selected_build_system,
            observed_build_system=executed_build_system,
            detected_build_systems=list(session.build_system_capabilities),
            submit_allowed=False,
        )
    supporting = next((command for command in session.commands if command.command_id == supporting_command_id), None)
    if supporting is None:
        failures.append("supporting_command_missing")
    elif supporting.role != "build":
        failures.append("supporting_command_role_invalid")
    elif supporting.exit_code != 0 or supporting.timed_out:
        failures.append("supporting_command_not_successful")

    successful_commands = [command for command in session.commands if command.exit_code == 0 and not command.timed_out]
    if active.policy.required_system_packages and not any(command.role == "dependency_setup" for command in successful_commands):
        failures.append("dependency_setup_not_observed")
    if active.policy.cmake_arguments and not _successful_configure_arguments_observed(
        successful_commands,
        active.policy.cmake_arguments,
    ):
        failures.append("cmake_arguments_not_observed")
    if active.policy.configure_arguments and not _successful_configure_arguments_observed(
        successful_commands,
        active.policy.configure_arguments,
    ):
        failures.append("configure_arguments_not_observed")
    return not failures, failures, executed_build_system


def _apply_experiment_replay_delay(session: CompileSession) -> None:
    active = get_active_experiment(session.thread_id)
    if active is None or active.policy.minimum_replay_delay_seconds <= 0:
        return
    services = get_compile_services()
    seconds = active.policy.minimum_replay_delay_seconds
    command = f"sleep {seconds}"
    timeout_seconds = seconds + 10
    started_at = utc_now_iso()
    started_monotonic = time.monotonic()
    result = services.runtime.exec(
        session,
        command,
        workdir=CONTAINER_WORKSPACE_DIR,
        timeout_seconds=timeout_seconds,
        log_path=local_log_path(session, f"{len(session.commands) + 1:03d}_benchmark_replay_delay.log"),
    )
    append_command_record(
        session,
        "bash",
        command,
        CONTAINER_WORKSPACE_DIR,
        result.log_path or local_log_path(session, f"{len(session.commands) + 1:03d}_benchmark_replay_delay.log"),
        result.exit_code,
        started_at,
        utc_now_iso(),
        role="replay_delay",
        timeout_seconds=timeout_seconds,
        duration_seconds=round(time.monotonic() - started_monotonic, 6),
        timed_out=result.exit_code == 124,
        termination="timeout" if result.exit_code == 124 else ("failed" if result.exit_code != 0 else "completed"),
    )
    if result.exit_code != 0:
        raise RuntimeError("Benchmark replay delay could not be established")


def submit_build_result_impl(
    *,
    session: CompileSession,
    supporting_command_id: str | None = None,
) -> str:
    services = get_compile_services()
    submit_attempt_id = new_evidence_id("submit")
    with services.manager.session_lock(session.thread_id, session.session_id):
        current = _load_authoritative_session(session)
        if _session_lifecycle_fenced(current):
            session.__dict__.update(current.__dict__)
            return _abort_submit_for_lifecycle(
                session,
                stage="entry",
                submit_attempt_id=submit_attempt_id,
                supporting_command_id=supporting_command_id,
            )
        session.__dict__.update(current.__dict__)
    constraints_passed, constraint_failures, executed_build_system = _experiment_submit_constraints(session, supporting_command_id)
    if get_active_experiment(session.thread_id) is not None:
        _persist_executed_build_system(session, executed_build_system)
    submit_index = len(session.commands) + 1
    summary_log_path = local_log_path(session, f"{submit_index:03d}_submit.log")
    while Path(summary_log_path).exists():
        submit_index += 1
        summary_log_path = local_log_path(session, f"{submit_index:03d}_submit.log")
    services.manager.log_event(
        session,
        "submit.started",
        leadagent_artifacts_dir=session.leadagent_artifacts_dir,
        container_artifacts_dir="/artifacts",
        log_path=summary_log_path,
        submit_attempt_id=submit_attempt_id,
        supporting_command_id=supporting_command_id,
    )
    record_experiment_event(
        session.thread_id,
        "submit.started",
        submit_attempt_id=submit_attempt_id,
        supporting_command_id=supporting_command_id,
        session_id=session.session_id,
        command_cutoff_before_delay=len(session.commands),
    )
    try:
        _apply_experiment_replay_delay(session)
    except RuntimeError:
        constraints_passed = False
        constraint_failures.append("minimum_replay_delay_not_observed")
    discovered_files = sorted(_list_leadagent_artifact_files(session), key=lambda p: p.as_posix())
    checks: list[VerificationCheck] = []
    artifacts: list[BuildArtifact] = []
    notes: list[str] = []

    if not constraints_passed:
        message = "Error: Verification failed. Benchmark launch constraints were not completely observed."
        notes.append(message)
        _record_submit_check(
            checks=checks,
            name="benchmark_constraints",
            target="experiment-policy",
            passed=False,
            summary=message,
            expected="applied",
            actual=list(constraint_failures),
        )

    if not discovered_files:
        notes.append("Error: Verification failed. No files were found in /artifacts. Copy your final build outputs into /artifacts and submit again.")
    else:
        base = Path(session.leadagent_artifacts_dir)
        for candidate_path in discovered_files:
            rel = candidate_path.relative_to(base)
            rel_posix = rel.as_posix()
            container_candidate = f"/artifacts/{rel_posix}" if rel_posix else "/artifacts"

            artifact_type = _classify_compiled_artifact(candidate_path)
            if artifact_type is None:
                notes.append(f"Ignored non-compiled file '{rel_posix}' in /artifacts.")
                continue

            exists = candidate_path.exists()
            _record_submit_check(
                checks=checks,
                name=f"{candidate_path.name}_exists",
                target=rel_posix,
                passed=exists,
                summary=("Artifact exists in artifacts directory." if exists else f"Error: Verification failed. File '{rel_posix}' does not exist. Copy the final output into /artifacts and submit again."),
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
                summary=(f"Artifact size is {size_bytes} bytes." if non_empty else f"Error: Verification failed. File '{rel_posix}' is empty. Rebuild or copy the correct output into /artifacts and submit again."),
            )
            if not non_empty:
                continue

            artifact_sha256 = _sha256_file(candidate_path)
            smoke_command_used: str | None = None
            smoke_result_used: CommandResult | None = None
            if artifact_type == "executable":
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
                        smoke_command_used = smoke_command
                        smoke_result_used = smoke_result
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
                    artifact_type=artifact_type,
                    size_bytes=size_bytes,
                    source_path=container_candidate,
                    sha256=artifact_sha256,
                    smoke_command=smoke_command_used,
                    smoke_exit_code=smoke_result_used.exit_code if smoke_result_used else None,
                    smoke_output=_persisted_output(smoke_result_used.combined_output) if smoke_result_used else None,
                    smoke_output_sha256=_sha256_text(smoke_result_used.combined_output) if smoke_result_used else None,
                )
            )

    if discovered_files and not artifacts:
        notes.append("Error: Verification failed. No recognized compiled artifacts were found in /artifacts.")

    candidate_status = "failed"
    replay_attempt: ReplayVerificationResult | None = None
    candidate_lifecycle_fenced = False
    if artifacts and all(check.passed for check in checks):
        with services.manager.session_lock(session.thread_id, session.session_id):
            current = _load_authoritative_session(session)
            if _session_lifecycle_fenced(current):
                session.__dict__.update(current.__dict__)
                candidate_lifecycle_fenced = True
            else:
                session.__dict__.update(current.__dict__)
                try:
                    _write_repro_bundle(session)
                except (OSError, ValueError) as exc:
                    message = f"Error: Verification failed. Could not generate a commit-pinned replay bundle: {exc}"
                    notes.append(message)
                    _record_submit_check(
                        checks=checks,
                        name="repro_bundle",
                        target="repro/build.sh",
                        passed=False,
                        summary=message,
                    )
                else:
                    candidate_status = "passed"
                    _record_submit_check(
                        checks=checks,
                        name="repro_bundle",
                        target="repro/build.sh",
                        passed=True,
                        summary="Generated a commit-pinned replay script from successful container commands.",
                    )
                    current.artifacts = list(artifacts)
                    current.verification = VerificationResult(
                        status="candidate_ready",
                        checks=list(checks),
                        artifact_count=len(artifacts),
                        failed_checks=0,
                        notes=list(notes),
                    )
                    services.manager.save_session(current)
                    session.__dict__.update(current.__dict__)

    if candidate_lifecycle_fenced:
        return _abort_submit_for_lifecycle(
            session,
            stage="candidate_checkpoint",
            submit_attempt_id=submit_attempt_id,
            supporting_command_id=supporting_command_id,
        )

    candidate_failed_checks = sum(1 for check in checks if not check.passed)
    if candidate_status == "passed" and artifacts and candidate_failed_checks == 0:
        if get_active_experiment(session.thread_id) is None:
            replay_attempt = verify_clean_replay_impl(session=session)
        else:
            replay_attempt = verify_clean_replay_impl(
                session=session,
                submit_attempt_id=submit_attempt_id,
            )
        replay_passed = replay_attempt.status == "passed" and replay_attempt.cleanup_succeeded is True
        replay_summary = (
            "Candidate recipe rebuilt matching artifacts in a clean container and cleanup succeeded."
            if replay_passed
            else f"Error: Verification failed. Clean replay did not pass ({replay_attempt.failure_classification or replay_attempt.status})."
        )
        _record_submit_check(
            checks=checks,
            name="clean_replay",
            target=f"replay/{replay_attempt.attempt_id}",
            passed=replay_passed,
            summary=replay_summary,
            expected="passed",
            actual=replay_attempt.status,
        )
        if not replay_passed:
            notes.append(replay_summary)

    failed_checks = sum(1 for check in checks if not check.passed)
    status = "passed" if artifacts and candidate_status == "passed" and replay_attempt is not None and replay_attempt.status == "passed" and replay_attempt.cleanup_succeeded is True and failed_checks == 0 else "failed"
    verification = VerificationResult(
        status=status,
        checks=checks,
        artifact_count=len(artifacts),
        failed_checks=failed_checks,
        notes=notes,
    )
    failure_message = next(
        (note for note in notes if note.startswith("Error:")),
        "Error: Verification failed. The submitted artifacts in /artifacts did not pass validation.",
    )
    target_status = "verified" if status == "passed" else "verification_failed"
    target_error = None if status == "passed" else failure_message
    if not _commit_submit_verification(
        session=session,
        artifacts=artifacts,
        verification=verification,
        status=target_status,
        error=target_error,
    ):
        return _abort_submit_for_lifecycle(
            session,
            stage="final_checkpoint",
            submit_attempt_id=submit_attempt_id,
            supporting_command_id=supporting_command_id,
        )

    payload = {
        "exit_code": 0 if status == "passed" else 1,
        "status": status,
        "candidate_status": candidate_status,
        "replay_status": replay_attempt.status if replay_attempt else "not_run",
        "replay_attempt_id": replay_attempt.attempt_id if replay_attempt else None,
        "submit_attempt_id": submit_attempt_id,
        "supporting_command_id": supporting_command_id,
        "image_id": session.image_id,
        "artifact_count": len(artifacts),
        "artifacts": [
            {
                "path": artifact.path,
                "source_path": artifact.source_path,
                "artifact_type": artifact.artifact_type,
                "size_bytes": artifact.size_bytes,
                "sha256": artifact.sha256,
            }
            for artifact in artifacts
        ],
        "message": "Build artifacts and clean replay accepted." if status == "passed" else failure_message,
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
        candidate_status=candidate_status,
        replay_status=replay_attempt.status if replay_attempt else "not_run",
        replay_attempt_id=replay_attempt.attempt_id if replay_attempt else None,
        submit_attempt_id=submit_attempt_id,
        supporting_command_id=supporting_command_id,
    )
    supporting_command = next(
        (command for command in session.commands if command.command_id == supporting_command_id),
        None,
    )
    supporting_command_passed = supporting_command is not None and supporting_command.role == "build" and supporting_command.exit_code == 0 and not supporting_command.timed_out
    replay_passed = replay_attempt is not None and replay_attempt.status == "passed" and replay_attempt.cleanup_succeeded is True
    record_experiment_event(
        session.thread_id,
        "submit.completed",
        submit_attempt_id=submit_attempt_id,
        supporting_command_id=supporting_command_id,
        session_id=session.session_id,
        status=status,
        candidate_status=candidate_status,
        command_cutoff=len(session.commands),
        command_ids=[command.command_id for command in session.commands],
        artifacts=_artifact_evidence_snapshot(artifacts),
        checks=_check_evidence_snapshot(checks),
        recipe_sha256=(replay_attempt.recipe_sha256 if replay_attempt else None),
        replay=(
            {
                "replay_attempt_id": replay_attempt.attempt_id,
                "status": replay_attempt.status,
                "primary_failure_classification": replay_attempt.primary_failure_classification,
                "secondary_failure_classifications": list(replay_attempt.secondary_failure_classifications),
                "cleanup_succeeded": replay_attempt.cleanup_succeeded,
            }
            if replay_attempt
            else None
        ),
        gates={
            "exit_code": supporting_command_passed,
            "candidate_only": candidate_status == "passed",
            "replay_ready": replay_attempt is not None and bool(replay_attempt.recipe_sha256),
            "clean_replay": replay_passed,
            "delivered": None,
        },
    )
    if status != "passed":
        primary_classification = replay_attempt.primary_failure_classification if replay_attempt is not None else (constraint_failures[0] if constraint_failures else "candidate_verification_failed")
        record_experiment_event(
            session.thread_id,
            "failure.recorded",
            failure_id=new_evidence_id("failure"),
            submit_attempt_id=submit_attempt_id,
            replay_attempt_id=(replay_attempt.attempt_id if replay_attempt else None),
            session_id=session.session_id,
            domain="verification",
            classification=primary_classification,
            primary=True,
            secondary_classifications=(list(replay_attempt.secondary_failure_classifications) if replay_attempt else []),
        )

    if status == "passed":
        services.manager.log_event(
            session,
            "verification.accepted",
            artifact_count=len(artifacts),
            replay_attempt_id=replay_attempt.attempt_id if replay_attempt else None,
        )

    return json.dumps(payload, ensure_ascii=False, indent=2)


def _validate_replay_workdir(workdir: str) -> str:
    if not workdir or any(character in workdir for character in ("\0", "\r", "\n")):
        raise ValueError("Invalid replay workdir.")

    path = PurePosixPath(workdir)
    if not path.is_absolute() or ".." in path.parts or ".compile-sessions" in path.parts:
        raise ValueError(f"Invalid replay workdir: {workdir!r}.")
    if not any(path == root or root in path.parents for root in _REPLAY_WORKDIR_ROOTS):
        raise ValueError(f"Unsupported replay workdir outside compile-container roots: {workdir!r}.")
    return path.as_posix()


def _validate_replay_command(session: CompileSession, command: str) -> None:
    if not command.strip() or "\0" in command or "\r" in command:
        raise ValueError("Invalid replay command.")

    forbidden_fragments = {
        ".compile-sessions",
        str(Path(session.metadata_path).parent),
        session.leadagent_repo_dir,
        session.leadagent_artifacts_dir,
        session.leadagent_logs_dir,
        session.leadagent_repro_dir,
    }
    if len(session.session_id) >= 8:
        forbidden_fragments.add(session.session_id)
    if len(session.thread_id) >= 8:
        forbidden_fragments.add(session.thread_id)

    if any(fragment and fragment in command for fragment in forbidden_fragments):
        raise ValueError("Invalid replay command containing a host or session path.")
    if _WINDOWS_ABSOLUTE_PATH_RE.search(command) or _WSL_HOST_PATH_RE.search(command):
        raise ValueError("Invalid replay command containing a host path.")


def _validate_replay_repo_url(repo_url: str) -> None:
    if not repo_url or repo_url != repo_url.strip() or any(character in repo_url for character in ("\0", "\r", "\n")):
        raise ValueError("A valid repo_url is required to generate a replay bundle.")
    if "?" in repo_url or "#" in repo_url:
        raise ValueError("Query parameters and fragments must not be embedded in repo_url for a persistent replay bundle.")
    if _WINDOWS_ABSOLUTE_PATH_RE.search(repo_url) or _WSL_HOST_PATH_RE.search(repo_url) or repo_url.startswith(("/", "./", "../", "~")):
        raise ValueError("A remote repo_url is required to generate a replay bundle.")

    parsed = urlsplit(repo_url)
    scheme = parsed.scheme.lower()
    if scheme:
        if scheme not in {"git", "git+ssh", "http", "https", "ssh"} or not parsed.hostname:
            raise ValueError("An HTTP(S), SSH, or Git repo_url is required to generate a replay bundle.")
        if parsed.password is not None or (scheme in {"http", "https"} and parsed.username is not None):
            raise ValueError("Credentials must not be embedded in repo_url for a persistent replay bundle.")
        return

    if not re.fullmatch(r"[^@\s/:]+@[^:\s/]+:.+", repo_url):
        raise ValueError("A remote repo_url is required to generate a replay bundle.")


def _write_repro_bundle(session: CompileSession) -> Path:
    repro_dir = Path(session.metadata_path).parent / "repro"
    build_path = repro_dir / "build.sh"
    build_path.unlink(missing_ok=True)

    commit_sha = (session.commit_sha or "").strip().lower()
    if not re.fullmatch(r"[0-9A-Fa-f]{40}|[0-9A-Fa-f]{64}", commit_sha):
        raise ValueError("A full commit_sha is required to generate a replay bundle.")
    _validate_replay_repo_url(session.repo_url)

    git_init_command = 'git init --quiet "$REPO_DIR"' if len(commit_sha) == 40 else 'git init --object-format=sha256 --quiet "$REPO_DIR"'
    build_lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        f"REPO_URL={shell_quote(session.repo_url)}",
        f"COMMIT_SHA={shell_quote(commit_sha)}",
        f"WORKSPACE_DIR={shell_quote(CONTAINER_WORKSPACE_DIR)}",
        f"REPO_DIR={shell_quote(CONTAINER_REPO_DIR)}",
        "ARTIFACTS_DIR=/artifacts",
        "",
        'mkdir -p -- "$WORKSPACE_DIR" "$ARTIFACTS_DIR"',
        'find "$WORKSPACE_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +',
        'find "$ARTIFACTS_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +',
        git_init_command,
        'git config --global --add safe.directory "$REPO_DIR"',
        "(",
        'cd -- "$REPO_DIR"',
        'git remote add origin "$REPO_URL"',
        'git fetch --depth 1 origin "$COMMIT_SHA"',
        'git checkout --detach "$COMMIT_SHA"',
        'test "$(git rev-parse HEAD)" = "$COMMIT_SHA"',
        ")",
        "",
    ]
    replay_index = 0
    for command in session.commands:
        if command.stage != "bash" or command.exit_code != 0:
            continue
        workdir = _validate_replay_workdir(command.workdir)
        _validate_replay_command(session, command.command)
        replay_index += 1
        build_lines.extend(
            [
                f"# Successful build command {replay_index}",
                "(",
                f"cd -- {shell_quote(workdir)}",
                f"bash -lc {shell_quote(command.command)}",
                ")",
                "",
            ]
        )
    if replay_index == 0:
        raise ValueError("At least one successful bash command is required to generate a replay bundle.")

    repro_dir.mkdir(parents=True, exist_ok=True)
    temporary_path = repro_dir / f".build.sh.{uuid.uuid4().hex}.tmp"
    try:
        temporary_path.write_text("\n".join(build_lines) + "\n", encoding="utf-8")
        temporary_path.replace(build_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return build_path


class _ReplayVerificationFailure(RuntimeError):
    def __init__(self, classification: str, message: str):
        super().__init__(message)
        self.classification = classification


def _record_replay_check(
    attempt: ReplayVerificationResult,
    *,
    name: str,
    target: str,
    passed: bool,
    summary: str,
    expected=None,
    actual=None,
    exit_code: int | None = None,
    log_path: str | None = None,
) -> None:
    attempt.checks.append(
        VerificationCheck(
            name=name,
            target=target,
            command="clean_replay",
            passed=passed,
            exit_code=exit_code if exit_code is not None else (0 if passed else 1),
            log_path=log_path,
            summary=summary,
            expected=expected,
            actual=actual,
        )
    )


def _remaining_replay_timeout(deadline: float) -> int:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _ReplayVerificationFailure("timeout", "Clean replay exceeded its total timeout.")
    return max(1, math.ceil(remaining))


def _artifact_relative_path(artifact: BuildArtifact) -> str:
    source_path = PurePosixPath(artifact.source_path or "")
    artifacts_root = PurePosixPath("/artifacts")
    if not source_path.is_absolute() or artifacts_root not in source_path.parents:
        raise ValueError(f"Artifact {artifact.path!r} does not have a valid /artifacts source path.")
    relative_path = source_path.relative_to(artifacts_root)
    if not relative_path.parts or ".." in relative_path.parts:
        raise ValueError(f"Artifact {artifact.path!r} does not have a safe relative path.")
    return relative_path.as_posix()


def _run_replay_smoke(
    *,
    session: CompileSession,
    handle: ReplayContainerHandle,
    relative_path: str,
    expected: BuildArtifact | None,
    deadline: float,
    log_path: Path,
) -> tuple[str | None, CommandResult | None]:
    services = get_compile_services()
    container_path = f"/artifacts/{relative_path}"
    expected_command = expected.smoke_command if expected else None
    smoke_commands = (
        (expected_command,)
        if expected_command
        else (
            f"{shell_quote(container_path)} -version",
            f"{shell_quote(container_path)} --version",
            f"{shell_quote(container_path)} --help",
        )
    )
    last_command: str | None = None
    last_result: CommandResult | None = None
    for smoke_command in smoke_commands:
        if smoke_command is None:
            continue
        timeout_seconds = min(_REPLAY_SMOKE_TIMEOUT_SECONDS, _remaining_replay_timeout(deadline))
        last_command = smoke_command
        last_result = services.runtime.exec_replay_container(
            session,
            handle,
            command=smoke_command,
            workdir=CONTAINER_WORKSPACE_DIR,
            timeout_seconds=timeout_seconds,
            log_path=str(log_path),
        )
        if last_result.exit_code == 0:
            break
        if last_result.exit_code == 124:
            raise _ReplayVerificationFailure("timeout", f"Smoke test for {relative_path!r} timed out.")
    return last_command, last_result


def _compare_replay_artifacts(
    *,
    session: CompileSession,
    attempt: ReplayVerificationResult,
    handle: ReplayContainerHandle,
    deadline: float,
) -> str | None:
    services = get_compile_services()
    replay_artifacts_dir = get_replay_artifacts_dir(
        session.session_id,
        session.thread_id,
        attempt.attempt_id,
        services.manager.paths,
    )
    replay_logs_dir = get_replay_logs_dir(
        session.session_id,
        session.thread_id,
        attempt.attempt_id,
        services.manager.paths,
    )
    expected_artifacts = {_artifact_relative_path(artifact): artifact for artifact in session.artifacts}
    actual_files: dict[str, Path] = {}
    actual_types: dict[str, str] = {}
    for path in _list_artifact_files(replay_artifacts_dir, deadline=deadline):
        artifact_type = _classify_compiled_artifact(path, deadline=deadline)
        if artifact_type is None:
            continue
        relative_path = path.relative_to(replay_artifacts_dir).as_posix()
        actual_files[relative_path] = path
        actual_types[relative_path] = artifact_type
    expected_paths = sorted(expected_artifacts)
    actual_paths = sorted(actual_files)
    artifact_set_matches = expected_paths == actual_paths
    _record_replay_check(
        attempt,
        name="artifact_set",
        target="/artifacts",
        passed=artifact_set_matches,
        summary=("Replay produced the same relative artifact paths." if artifact_set_matches else "Replay artifact paths differ from the accepted build."),
        expected=expected_paths,
        actual=actual_paths,
    )

    first_failure = None if artifact_set_matches else "artifact_set_mismatch"
    for artifact_index, relative_path in enumerate(sorted(set(expected_paths) | set(actual_paths)), start=1):
        expected = expected_artifacts.get(relative_path)
        actual_path = actual_files.get(relative_path)
        actual_type = actual_types.get(relative_path)
        _check_replay_deadline(deadline)
        actual_size = actual_path.stat().st_size if actual_path else None
        actual_sha256 = _sha256_file(actual_path, deadline=deadline) if actual_path else None
        actual_smoke_command: str | None = None
        actual_smoke_result: CommandResult | None = None
        if actual_path is not None and actual_type == "executable":
            smoke_log_path = replay_logs_dir / f"smoke_{artifact_index:03d}.log"
            actual_smoke_command, actual_smoke_result = _run_replay_smoke(
                session=session,
                handle=handle,
                relative_path=relative_path,
                expected=expected,
                deadline=deadline,
                log_path=smoke_log_path,
            )

        type_matches = expected is not None and actual_path is not None and expected.artifact_type == actual_type
        size_matches = expected is not None and actual_path is not None and expected.size_bytes == actual_size
        sha256_matches = expected is not None and actual_path is not None and expected.sha256 == actual_sha256
        expected_requires_smoke = expected is not None and expected.artifact_type == "executable"
        if expected_requires_smoke:
            actual_smoke_output = _persisted_output(actual_smoke_result.combined_output) if actual_smoke_result else None
            actual_smoke_output_sha256 = _sha256_text(actual_smoke_result.combined_output) if actual_smoke_result else None
            smoke_output_matches = expected.smoke_output_sha256 == actual_smoke_output_sha256 if expected.smoke_output_sha256 is not None else expected.smoke_output == actual_smoke_output
            smoke_matches = actual_smoke_result is not None and expected.smoke_command == actual_smoke_command and expected.smoke_exit_code == actual_smoke_result.exit_code and smoke_output_matches
        else:
            actual_smoke_output = _persisted_output(actual_smoke_result.combined_output) if actual_smoke_result else None
            actual_smoke_output_sha256 = _sha256_text(actual_smoke_result.combined_output) if actual_smoke_result else None
            smoke_matches = actual_smoke_result is None

        mismatches: list[str] = []
        if expected is None:
            mismatches.append("unexpected_artifact")
        if actual_path is None:
            mismatches.append("missing_artifact")
        if not type_matches:
            mismatches.append("type")
        if not size_matches:
            mismatches.append("size")
        if not sha256_matches:
            mismatches.append("sha256")
        if not smoke_matches:
            mismatches.append("smoke")
        comparison_passed = not mismatches
        comparison = ReplayArtifactComparison(
            path=relative_path,
            expected_type=expected.artifact_type if expected else None,
            actual_type=actual_type,
            expected_size_bytes=expected.size_bytes if expected else None,
            actual_size_bytes=actual_size,
            expected_sha256=expected.sha256 if expected else None,
            actual_sha256=actual_sha256,
            expected_smoke_command=expected.smoke_command if expected else None,
            actual_smoke_command=actual_smoke_command,
            expected_smoke_exit_code=expected.smoke_exit_code if expected else None,
            actual_smoke_exit_code=actual_smoke_result.exit_code if actual_smoke_result else None,
            expected_smoke_output=expected.smoke_output if expected else None,
            actual_smoke_output=actual_smoke_output,
            expected_smoke_output_sha256=expected.smoke_output_sha256 if expected else None,
            actual_smoke_output_sha256=actual_smoke_output_sha256,
            type_matches=type_matches,
            size_matches=size_matches,
            sha256_matches=sha256_matches,
            smoke_matches=smoke_matches,
            passed=comparison_passed,
            mismatches=mismatches,
        )
        attempt.artifacts.append(comparison)
        for check_name, expected_value, actual_value, passed in (
            ("type", comparison.expected_type, comparison.actual_type, type_matches),
            ("size", comparison.expected_size_bytes, comparison.actual_size_bytes, size_matches),
            ("sha256", comparison.expected_sha256, comparison.actual_sha256, sha256_matches),
            (
                "smoke",
                {
                    "command": comparison.expected_smoke_command,
                    "exit_code": comparison.expected_smoke_exit_code,
                    "output": comparison.expected_smoke_output,
                    "output_sha256": comparison.expected_smoke_output_sha256,
                },
                {
                    "command": comparison.actual_smoke_command,
                    "exit_code": comparison.actual_smoke_exit_code,
                    "output": comparison.actual_smoke_output,
                    "output_sha256": comparison.actual_smoke_output_sha256,
                },
                smoke_matches,
            ),
        ):
            _record_replay_check(
                attempt,
                name=f"artifact_{artifact_index}_{check_name}",
                target=relative_path,
                passed=passed,
                summary=f"Replay artifact {check_name} {'matches' if passed else 'does not match'} the accepted build.",
                expected=expected_value,
                actual=actual_value,
                exit_code=comparison.actual_smoke_exit_code if check_name == "smoke" else None,
            )

        if first_failure is None and not type_matches:
            first_failure = "type_mismatch"
        if first_failure is None and not size_matches:
            first_failure = "size_mismatch"
        if first_failure is None and not sha256_matches:
            first_failure = "sha256_mismatch"
        if first_failure is None and not smoke_matches:
            first_failure = "smoke_mismatch"
    return first_failure


def _merge_authoritative_replay_cancellation(
    attempt: ReplayVerificationResult,
    authoritative: ReplayVerificationResult,
) -> None:
    if authoritative.status != "cancelled":
        return
    attempt.container_id = attempt.container_id or authoritative.container_id
    attempt.container_name = attempt.container_name or authoritative.container_name
    attempt.completed_at = authoritative.completed_at or attempt.completed_at
    attempt.duration_seconds = attempt.duration_seconds if attempt.duration_seconds is not None else authoritative.duration_seconds
    if authoritative.cleanup_succeeded is True or attempt.cleanup_succeeded is True:
        attempt.cleanup_succeeded = True
    elif authoritative.cleanup_succeeded is False:
        attempt.cleanup_succeeded = False
    for check in authoritative.checks:
        if check not in attempt.checks:
            attempt.checks.append(check)
    for note in authoritative.notes:
        if note not in attempt.notes:
            attempt.notes.append(note)
    attempt.status = "cancelled"
    authoritative_primary = authoritative.primary_failure_classification or authoritative.failure_classification or "cancelled"
    _record_replay_failure(attempt, authoritative_primary)
    for classification in authoritative.secondary_failure_classifications:
        _record_replay_failure(attempt, classification)


def _persist_replay_attempt(
    *,
    session: CompileSession,
    attempt: ReplayVerificationResult,
) -> ReplayVerificationResult:
    services = get_compile_services()
    with services.manager.session_lock(session.thread_id, session.session_id):
        current = _load_authoritative_session(session)
        existing_attempt: ReplayVerificationResult | None = None
        for index, existing in enumerate(current.replay_attempts):
            if existing.attempt_id != attempt.attempt_id:
                continue
            existing_attempt = existing
            _merge_authoritative_replay_cancellation(attempt, existing)
            current.replay_attempts[index] = attempt
            break
        else:
            if _session_lifecycle_fenced(current):
                attempt.status = "cancelled"
                _record_replay_failure(attempt, "session_terminated")
                attempt.cleanup_succeeded = attempt.cleanup_succeeded if attempt.cleanup_succeeded is not None else True
                session.__dict__.update(current.__dict__)
                return attempt
            current.replay_attempts.append(attempt)
        if _session_lifecycle_fenced(current):
            if existing_attempt is not None and existing_attempt.status != "cancelled":
                attempt.status = "cancelled"
                _record_replay_failure(attempt, "session_terminated")
            if current.finalized_at is not None:
                session.__dict__.update(current.__dict__)
                return attempt
        services.manager.save_session(current, allow_lifecycle_fenced=True)
        session.__dict__.update(current.__dict__)
    return attempt


def verify_clean_replay_impl(
    *,
    session: CompileSession,
    submit_attempt_id: str | None = None,
    timeout_seconds: int | None = None,
) -> ReplayVerificationResult:
    services = get_compile_services()
    configured_timeout = getattr(getattr(services.runtime, "config", None), "replay_timeout_seconds", 1200)
    effective_timeout = max(1, timeout_seconds or configured_timeout)
    started_monotonic = time.monotonic()
    deadline = started_monotonic + effective_timeout
    attempt_id = new_evidence_id("replay")
    with services.manager.session_lock(session.thread_id, session.session_id):
        current = _load_authoritative_session(session)
        session.__dict__.update(current.__dict__)
        attempt = ReplayVerificationResult(
            attempt_id=attempt_id,
            status="pending",
            image=session.image,
            image_id=session.image_id or "",
            commit_sha=session.commit_sha or "",
            recipe_sha256="",
            submit_attempt_id=submit_attempt_id,
            timeout_seconds=effective_timeout,
        )
        if _session_lifecycle_fenced(session):
            attempt.status = "cancelled"
            _record_replay_failure(attempt, "session_terminated")
            attempt.cleanup_succeeded = True
            attempt.completed_at = utc_now_iso()
            attempt.duration_seconds = round(time.monotonic() - started_monotonic, 6)
            attempt.notes.append("Clean replay was not started because the compile session is terminating or finalized.")
            return attempt
        session.replay_attempts.append(attempt)
        services.manager.save_session(session)
    services.manager.log_event(
        session,
        "replay.started",
        attempt_id=attempt_id,
        image=session.image,
        image_id=session.image_id,
        commit_sha=session.commit_sha,
        timeout_seconds=effective_timeout,
        submit_attempt_id=submit_attempt_id,
    )
    record_experiment_event(
        session.thread_id,
        "replay.started",
        replay_attempt_id=attempt_id,
        submit_attempt_id=submit_attempt_id,
        session_id=session.session_id,
        image_id=session.image_id,
        commit_sha=session.commit_sha,
        timeout_seconds=effective_timeout,
    )

    handle: ReplayContainerHandle | None = None
    pending_base_exception: BaseException | None = None
    try:
        recipe_dir = get_replay_recipe_dir(
            session.session_id,
            session.thread_id,
            attempt_id,
            services.manager.paths,
        )
        workspace_dir = get_replay_workspace_dir(
            session.session_id,
            session.thread_id,
            attempt_id,
            services.manager.paths,
        )
        artifacts_dir = get_replay_artifacts_dir(
            session.session_id,
            session.thread_id,
            attempt_id,
            services.manager.paths,
        )
        logs_dir = get_replay_logs_dir(
            session.session_id,
            session.thread_id,
            attempt_id,
            services.manager.paths,
        )
        for directory in (recipe_dir, workspace_dir, artifacts_dir, logs_dir):
            directory.mkdir(parents=True, exist_ok=True)
        recipe_path = recipe_dir / "build.sh"
        source_recipe_path = Path(session.leadagent_repro_dir) / "build.sh"
        source_recipe_sha256 = _sha256_file(source_recipe_path, deadline=deadline)
        _check_replay_deadline(deadline)
        shutil.copy2(source_recipe_path, recipe_path)
        attempt.recipe_sha256 = _sha256_file(recipe_path, deadline=deadline)
        attempt.log_path = services.manager.relative_path(session, logs_dir / "build.log")
        recipe_snapshot_matches = source_recipe_sha256 == attempt.recipe_sha256
        _record_replay_check(
            attempt,
            name="recipe_snapshot",
            target="recipe/build.sh",
            passed=recipe_snapshot_matches,
            summary="Snapshotted the generated candidate recipe for this replay attempt.",
            expected=source_recipe_sha256,
            actual=attempt.recipe_sha256,
        )
        if not recipe_snapshot_matches:
            raise _ReplayVerificationFailure(
                "recipe_snapshot_mismatch",
                "Candidate recipe changed while the replay snapshot was being created.",
            )
        if not session.image_id:
            raise _ReplayVerificationFailure(
                "image_identity_unavailable",
                "The original compile container did not record an immutable image ID.",
            )
        _record_replay_check(
            attempt,
            name="image_identity",
            target=session.image,
            passed=True,
            summary="Replay will use the original container's immutable image ID.",
            expected=session.image_id,
            actual=session.image_id,
        )
        attempt.container_name = services.runtime.replay_container_name(session, attempt_id)
        attempt.status = "running"
        with services.manager.session_lock(session.thread_id, session.session_id):
            current = _load_authoritative_session(session)
            authoritative = next(
                (item for item in current.replay_attempts if item.attempt_id == attempt.attempt_id),
                None,
            )
            if _session_lifecycle_fenced(current) or (authoritative is not None and authoritative.status == "cancelled"):
                if authoritative is not None:
                    _merge_authoritative_replay_cancellation(attempt, authoritative)
                if attempt.status != "cancelled":
                    attempt.status = "cancelled"
                    _record_replay_failure(attempt, "session_terminated")
                current.replay_attempts = [attempt if item.attempt_id == attempt.attempt_id else item for item in current.replay_attempts]
                if current.finalized_at is None:
                    services.manager.save_session(current, allow_lifecycle_fenced=True)
                session.__dict__.update(current.__dict__)
                raise _ReplayVerificationFailure(
                    attempt.failure_classification or "cancelled",
                    "Clean replay was cancelled before its container could be created because the compile session is terminating.",
                )
            current.replay_attempts = [attempt if item.attempt_id == attempt.attempt_id else item for item in current.replay_attempts]
            services.manager.mark_session_status(current, "replay_verifying")
            session.__dict__.update(current.__dict__)
            handle = services.runtime.create_replay_container(
                session,
                attempt_id=attempt_id,
                timeout_seconds=min(
                    _REPLAY_CONTAINER_CREATE_TIMEOUT_SECONDS,
                    _remaining_replay_timeout(deadline),
                ),
            )
            attempt.container_id = handle.container_id
            attempt.container_name = handle.container_name
            current.replay_attempts = [attempt if item.attempt_id == attempt.attempt_id else item for item in current.replay_attempts]
            services.manager.save_session(current)
            session.__dict__.update(current.__dict__)
        build_log_path = logs_dir / "build.log"
        build_result = services.runtime.exec_replay_container(
            session,
            handle,
            timeout_seconds=_remaining_replay_timeout(deadline),
            log_path=str(build_log_path),
        )
        attempt.exit_code = build_result.exit_code
        execution_passed = build_result.exit_code == 0
        _record_replay_check(
            attempt,
            name="recipe_execution",
            target="recipe/build.sh",
            passed=execution_passed,
            summary=("Candidate recipe completed successfully in the clean replay container." if execution_passed else "Candidate recipe failed in the clean replay container."),
            expected=0,
            actual=build_result.exit_code,
            exit_code=build_result.exit_code,
            log_path=attempt.log_path,
        )
        if build_result.exit_code == 124:
            raise _ReplayVerificationFailure("timeout", "Clean replay recipe execution timed out.")
        if build_result.exit_code != 0:
            raise _ReplayVerificationFailure(
                "recipe_execution_failed",
                f"Clean replay recipe exited with code {build_result.exit_code}.",
            )
        failure_classification = _compare_replay_artifacts(
            session=session,
            attempt=attempt,
            handle=handle,
            deadline=deadline,
        )
        if failure_classification is not None:
            raise _ReplayVerificationFailure(
                failure_classification,
                "Replay artifacts did not match the accepted build.",
            )
    except _ReplayVerificationFailure as exc:
        _record_replay_failure(attempt, exc.classification)
        attempt.notes.append(str(exc))
    except subprocess.TimeoutExpired as exc:
        _record_replay_failure(attempt, "timeout")
        attempt.notes.append(f"Docker replay operation timed out: {exc}")
    except Exception as exc:
        _record_replay_failure(attempt, "internal_error")
        attempt.notes.append(f"Clean replay verification failed: {exc}")
    except BaseException as exc:
        _record_replay_failure(attempt, "cancelled")
        attempt.notes.append(f"Clean replay was cancelled by {type(exc).__name__}.")
        pending_base_exception = exc
    finally:
        if attempt.container_name:
            try:
                cleanup_result = services.runtime.stop_and_remove_replay_container(
                    session,
                    handle,
                    container_id=attempt.container_id,
                    container_name=attempt.container_name,
                )
            except Exception as exc:
                cleanup_result = ContainerCleanupResult(succeeded=False, stopped=False, removed=False)
                attempt.notes.append(f"Replay container cleanup raised an error: {exc}")
        else:
            cleanup_result = ContainerCleanupResult(succeeded=True, stopped=True, removed=True)
        attempt.cleanup_succeeded = cleanup_result.succeeded and cleanup_result.removed
        _record_replay_check(
            attempt,
            name="container_cleanup",
            target=attempt.container_name or "replay-container",
            passed=attempt.cleanup_succeeded,
            summary=("Replay container was removed." if attempt.cleanup_succeeded else "Replay container cleanup did not complete successfully."),
            expected={"stopped": True, "removed": True},
            actual={"stopped": cleanup_result.stopped, "removed": cleanup_result.removed},
        )
        if not attempt.cleanup_succeeded:
            _record_replay_failure(attempt, "cleanup_failed")
        if pending_base_exception is not None:
            attempt.status = "cancelled"
        elif attempt.primary_failure_classification == "timeout":
            attempt.status = "timed_out"
        elif attempt.primary_failure_classification == "cancelled":
            attempt.status = "cancelled"
        elif attempt.primary_failure_classification is None and attempt.cleanup_succeeded:
            attempt.status = "passed"
        else:
            attempt.status = "failed"
        attempt.completed_at = utc_now_iso()
        attempt.duration_seconds = round(time.monotonic() - started_monotonic, 6)
        _persist_replay_attempt(session=session, attempt=attempt)
        services.manager.log_event(
            session,
            "replay.completed",
            attempt_id=attempt.attempt_id,
            status=attempt.status,
            failure_classification=attempt.failure_classification,
            exit_code=attempt.exit_code,
            cleanup_succeeded=attempt.cleanup_succeeded,
            duration_seconds=attempt.duration_seconds,
            timeout_seconds=attempt.timeout_seconds,
            image_id=attempt.image_id,
            recipe_sha256=attempt.recipe_sha256,
            completed_by="replay_worker",
            submit_attempt_id=submit_attempt_id,
            primary_failure_classification=attempt.primary_failure_classification,
            secondary_failure_classifications=attempt.secondary_failure_classifications,
        )
        record_experiment_event(
            session.thread_id,
            "replay.completed",
            replay_attempt_id=attempt.attempt_id,
            submit_attempt_id=submit_attempt_id,
            session_id=session.session_id,
            status=attempt.status,
            exit_code=attempt.exit_code,
            cleanup_succeeded=attempt.cleanup_succeeded,
            duration_seconds=attempt.duration_seconds,
            timeout_seconds=attempt.timeout_seconds,
            image_id=attempt.image_id,
            commit_sha=attempt.commit_sha,
            recipe_sha256=attempt.recipe_sha256 or None,
            primary_failure_classification=attempt.primary_failure_classification,
            secondary_failure_classifications=list(attempt.secondary_failure_classifications),
            checks=_check_evidence_snapshot(attempt.checks),
            artifacts=_replay_artifact_evidence_snapshot(attempt.artifacts),
        )
    if pending_base_exception is not None:
        raise pending_base_exception
    return attempt


def _latest_replay_passed(session: CompileSession) -> bool:
    if not session.replay_attempts:
        return False
    latest = session.replay_attempts[-1]
    build_path = Path(session.leadagent_repro_dir) / "build.sh"
    try:
        recipe_sha256 = _sha256_file(build_path)
    except OSError:
        return False
    return latest.status == "passed" and latest.cleanup_succeeded is True and latest.image_id == session.image_id and latest.commit_sha == session.commit_sha and latest.recipe_sha256 == recipe_sha256


def _accepted_artifacts_still_match(session: CompileSession) -> tuple[bool, dict]:
    base = Path(session.leadagent_artifacts_dir)
    try:
        resolved_base = base.resolve(strict=True)
    except OSError as exc:
        return False, {"mismatches": [f"artifacts_root_unavailable: {exc}"]}

    expected: dict[str, BuildArtifact] = {}
    actual: dict[str, dict] = {}
    mismatches: list[str] = []
    for artifact in session.artifacts:
        try:
            relative_path = _artifact_relative_path(artifact)
        except ValueError as exc:
            mismatches.append(str(exc))
            continue
        if relative_path in expected:
            mismatches.append(f"duplicate_recorded_path:{relative_path}")
            continue
        expected[relative_path] = artifact
        candidate = base.joinpath(*PurePosixPath(relative_path).parts)
        current_component = base
        symlink_found = False
        for part in PurePosixPath(relative_path).parts:
            current_component /= part
            if current_component.is_symlink():
                symlink_found = True
                break
        if symlink_found:
            mismatches.append(f"symlink:{relative_path}")
            continue
        try:
            resolved_candidate = candidate.resolve(strict=True)
        except OSError:
            mismatches.append(f"missing:{relative_path}")
            continue
        if not resolved_candidate.is_relative_to(resolved_base) or not resolved_candidate.is_file():
            mismatches.append(f"path_escape_or_not_file:{relative_path}")
            continue
        artifact_type = _classify_compiled_artifact(resolved_candidate)
        size_bytes = resolved_candidate.stat().st_size
        sha256 = _sha256_file(resolved_candidate)
        actual[relative_path] = {
            "artifact_type": artifact_type,
            "size_bytes": size_bytes,
            "sha256": sha256,
        }
        if artifact_type != artifact.artifact_type:
            mismatches.append(f"type:{relative_path}")
        if size_bytes != artifact.size_bytes:
            mismatches.append(f"size:{relative_path}")
        if sha256 != artifact.sha256:
            mismatches.append(f"sha256:{relative_path}")

    actual_compiled_paths: set[str] = set()
    for candidate in _list_artifact_files(base):
        artifact_type = _classify_compiled_artifact(candidate)
        if artifact_type is not None:
            actual_compiled_paths.add(candidate.relative_to(base).as_posix())
    expected_paths = set(expected)
    if actual_compiled_paths != expected_paths:
        for missing_path in sorted(expected_paths - actual_compiled_paths):
            mismatch = f"missing_compiled_artifact:{missing_path}"
            if mismatch not in mismatches:
                mismatches.append(mismatch)
        for extra_path in sorted(actual_compiled_paths - expected_paths):
            mismatches.append(f"unexpected_compiled_artifact:{extra_path}")

    return not mismatches, {
        "expected_paths": sorted(expected_paths),
        "actual_paths": sorted(actual_compiled_paths),
        "actual": actual,
        "mismatches": mismatches,
    }


def finalize_compile_session_impl(
    *,
    session: CompileSession,
    summary: str | None = None,
    status: str = "completed",
    error: str | None = None,
    generate_repro_bundle: bool = True,
) -> CompileSession:
    services = get_compile_services()
    with services.manager.session_lock(session.thread_id, session.session_id):
        try:
            current = services.manager.load_session(session.session_id, session.thread_id)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            current = session

        if current.finalized_at is None:
            if current.termination_requested_at is not None:
                status = current.termination_status or status
                error = current.termination_error or error
                summary = current.termination_error or summary
            replay_verified = _latest_replay_passed(current)
            current.finalized_at = utc_now_iso()
            services.manager.mark_session_status(current, status, error=error, summary=summary)
            services.manager.log_event(
                current,
                "finalize.completed",
                status=status,
                summary=summary,
                finalized_at=current.finalized_at,
                generate_repro_bundle=False,
                generate_repro_bundle_requested=generate_repro_bundle,
                replay_verified=replay_verified,
            )
            latest_replay = current.replay_attempts[-1] if current.replay_attempts else None
            delivered = status == "completed" and replay_verified
            record_experiment_event(
                current.thread_id,
                "delivery.completed",
                session_id=current.session_id,
                submit_attempt_id=(latest_replay.submit_attempt_id if latest_replay else None),
                replay_attempt_id=(latest_replay.attempt_id if latest_replay else None),
                status=status,
                delivered=delivered,
                replay_verified=replay_verified,
                artifact_count=len(current.artifacts),
                artifacts=_artifact_evidence_snapshot(current.artifacts),
                primary_failure_classification=(latest_replay.primary_failure_classification if latest_replay else (None if delivered else "delivery_rejected")),
                secondary_failure_classifications=(list(latest_replay.secondary_failure_classifications) if latest_replay else []),
            )

        session.__dict__.update(current.__dict__)
        return session


def _cleanup_pending_replay_containers(session: CompileSession) -> ContainerCleanupResult:
    services = get_compile_services()
    pending_attempts = [attempt for attempt in session.replay_attempts if attempt.status in {"pending", "running"} or (attempt.cleanup_succeeded is not True and (attempt.container_id or attempt.container_name))]
    if not pending_attempts:
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    cleanup_results: list[ContainerCleanupResult] = []
    completed_attempts: list[tuple[ReplayVerificationResult, str]] = []
    for attempt in pending_attempts:
        was_active = attempt.status in {"pending", "running"}
        previous_cleanup_succeeded = attempt.cleanup_succeeded
        if attempt.container_id or attempt.container_name:
            try:
                cleanup_result = services.runtime.stop_and_remove_replay_container(
                    session,
                    container_id=attempt.container_id,
                    container_name=attempt.container_name,
                )
            except Exception as exc:
                cleanup_result = ContainerCleanupResult(succeeded=False, stopped=False, removed=False)
                attempt.notes.append(f"Parent replay cleanup raised an error: {exc}")
        else:
            cleanup_result = ContainerCleanupResult(succeeded=True, stopped=True, removed=True)
        attempt.cleanup_succeeded = cleanup_result.succeeded and cleanup_result.removed
        if was_active:
            attempt.status = "cancelled"
            _record_replay_failure(attempt, "cancelled")
            attempt.completed_at = attempt.completed_at or utc_now_iso()
            if attempt.duration_seconds is None:
                try:
                    elapsed = datetime.fromisoformat(attempt.completed_at) - datetime.fromisoformat(attempt.started_at)
                    attempt.duration_seconds = round(max(0.0, elapsed.total_seconds()), 6)
                except ValueError:
                    attempt.duration_seconds = None
            attempt.notes.append("Replay was stopped by the parent compile-session cleanup path.")
            completed_attempts.append((attempt, "parent_cleanup"))
        elif previous_cleanup_succeeded is not True and attempt.cleanup_succeeded:
            completed_attempts.append((attempt, "parent_cleanup_retry"))
        if not attempt.cleanup_succeeded:
            _record_replay_failure(attempt, "cleanup_failed")
        _record_replay_check(
            attempt,
            name="parent_container_cleanup",
            target=attempt.container_name or attempt.container_id or "replay-container",
            passed=attempt.cleanup_succeeded,
            summary=("Parent cleanup removed the replay container." if attempt.cleanup_succeeded else "Parent cleanup could not remove the replay container."),
            expected={"stopped": True, "removed": True},
            actual={"stopped": cleanup_result.stopped, "removed": cleanup_result.removed},
        )
        cleanup_results.append(cleanup_result)
    services.manager.save_session(
        session,
        allow_lifecycle_fenced=True,
        merge_finalized_replay_cleanup=True,
    )
    for attempt, completed_by in completed_attempts:
        services.manager.log_event(
            session,
            "replay.completed",
            attempt_id=attempt.attempt_id,
            status=attempt.status,
            failure_classification=attempt.failure_classification,
            exit_code=attempt.exit_code,
            cleanup_succeeded=attempt.cleanup_succeeded,
            duration_seconds=attempt.duration_seconds,
            timeout_seconds=attempt.timeout_seconds,
            image_id=attempt.image_id,
            recipe_sha256=attempt.recipe_sha256,
            completed_by=completed_by,
            submit_attempt_id=attempt.submit_attempt_id,
            primary_failure_classification=attempt.primary_failure_classification,
            secondary_failure_classifications=attempt.secondary_failure_classifications,
        )
        record_experiment_event(
            session.thread_id,
            "replay.reconciled",
            replay_attempt_id=attempt.attempt_id,
            submit_attempt_id=attempt.submit_attempt_id,
            session_id=session.session_id,
            status=attempt.status,
            cleanup_succeeded=attempt.cleanup_succeeded,
            completed_by=completed_by,
            primary_failure_classification=attempt.primary_failure_classification,
            secondary_failure_classifications=list(attempt.secondary_failure_classifications),
        )
    return ContainerCleanupResult(
        succeeded=all(result.succeeded for result in cleanup_results),
        stopped=all(result.stopped for result in cleanup_results),
        removed=all(result.removed for result in cleanup_results),
    )


def _combined_cleanup_result(
    replay_cleanup: ContainerCleanupResult,
    compile_cleanup: ContainerCleanupResult,
) -> ContainerCleanupResult:
    return ContainerCleanupResult(
        succeeded=replay_cleanup.succeeded and compile_cleanup.succeeded,
        stopped=replay_cleanup.stopped and compile_cleanup.stopped,
        removed=replay_cleanup.removed and compile_cleanup.removed,
    )


def _request_session_termination(
    session: CompileSession,
    *,
    status: str,
    error: str | None = None,
) -> None:
    services = get_compile_services()
    if session.termination_requested_at is not None:
        return
    session.termination_requested_at = utc_now_iso()
    session.termination_status = status
    session.termination_error = error
    services.manager.save_session(session)
    services.manager.log_event(
        session,
        "session.termination_requested",
        status=status,
        termination_requested_at=session.termination_requested_at,
    )


def cleanup_and_finalize_compile_session_impl(
    *,
    session: CompileSession,
    interrupted_status: str | None = None,
    error: str | None = None,
) -> tuple[CompileSession, ContainerCleanupResult]:
    """Clean a session container and persist a terminal result only after cleanup succeeds."""
    services = get_compile_services()
    with services.manager.session_lock(session.thread_id, session.session_id):
        try:
            current = services.manager.load_session(session.session_id, session.thread_id)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            current = session

        if current.finalized_at is not None:
            replay_cleanup_result = _cleanup_pending_replay_containers(current)
            compile_cleanup_result = services.runtime.stop_and_remove_container(current)
            session.__dict__.update(current.__dict__)
            return session, _combined_cleanup_result(replay_cleanup_result, compile_cleanup_result)
        if interrupted_status is not None:
            _request_session_termination(current, status=interrupted_status, error=error)

        replay_cleanup_result = _cleanup_pending_replay_containers(current)
        compile_cleanup_result = services.runtime.stop_and_remove_container(current)
        cleanup_result = _combined_cleanup_result(replay_cleanup_result, compile_cleanup_result)
        if not cleanup_result.succeeded:
            cleanup_error = error or "Compile container cleanup failed."
            if "cleanup failed" not in cleanup_error.lower():
                cleanup_error = f"{cleanup_error} Compile container cleanup failed."
            services.manager.mark_session_status(current, "failed", error=cleanup_error, summary=cleanup_error)
            services.manager.log_event(
                current,
                "finalize.deferred",
                reason="container_cleanup_failed",
                stopped=cleanup_result.stopped,
                removed=cleanup_result.removed,
            )
            session.__dict__.update(current.__dict__)
            return session, cleanup_result

        replay_and_verification_passed = current.status == "verified" and current.verification is not None and current.verification.status == "passed" and bool(current.artifacts) and _latest_replay_passed(current)
        artifact_integrity_error: str | None = None
        artifact_integrity_passed = False
        if interrupted_status is None and current.termination_requested_at is None and replay_and_verification_passed:
            artifact_integrity_passed, artifact_integrity_details = _accepted_artifacts_still_match(current)
            current.verification.checks.append(
                VerificationCheck(
                    name="accepted_artifacts_unchanged_after_cleanup",
                    target="/artifacts",
                    command="finalize",
                    passed=artifact_integrity_passed,
                    exit_code=0 if artifact_integrity_passed else 1,
                    summary=(
                        "Accepted artifacts still match their verified type, size, and SHA-256 after compile-container cleanup."
                        if artifact_integrity_passed
                        else "Accepted artifacts changed after clean replay verification and before finalization."
                    ),
                    expected={
                        artifact.source_path: {
                            "artifact_type": artifact.artifact_type,
                            "size_bytes": artifact.size_bytes,
                            "sha256": artifact.sha256,
                        }
                        for artifact in current.artifacts
                    },
                    actual=artifact_integrity_details,
                )
            )
            if not artifact_integrity_passed:
                artifact_integrity_error = "Accepted artifacts changed after clean replay verification; finalization was rejected."
                current.verification.status = "failed"
                current.verification.failed_checks += 1
                current.verification.notes.append(artifact_integrity_error)
            services.manager.save_session(current)
            services.manager.log_event(
                current,
                "artifact.finalization_recheck",
                passed=artifact_integrity_passed,
                details=artifact_integrity_details,
            )
        verification_passed = replay_and_verification_passed and artifact_integrity_passed
        if current.termination_requested_at is not None:
            final_status = current.termination_status or interrupted_status or "cancelled"
            final_error = current.termination_error or error or f"Parent run ended with status {final_status}."
        elif interrupted_status is not None:
            final_status = current.termination_status or interrupted_status
            final_error = current.termination_error or error or f"Parent run ended with status {final_status}."
        elif verification_passed:
            final_status = "completed"
            final_error = None
        elif current.status in {"failed", "cancelled", "timed_out"}:
            final_status = current.status
            final_error = current.error or f"Compile session ended with status {current.status}."
        else:
            final_status = "failed"
            final_error = artifact_integrity_error or current.error or "Compile session finalized before artifact verification passed."

        updated = finalize_compile_session_impl(
            session=current,
            status=final_status,
            summary=final_error,
            error=final_error,
        )
        session.__dict__.update(updated.__dict__)
        return session, cleanup_result


def cleanup_compile_session_container_impl(
    *,
    session: CompileSession,
    interrupted_status: str | None = None,
    error: str | None = None,
) -> tuple[CompileSession, ContainerCleanupResult]:
    """Reload and clean a session container under the session lifecycle lock."""
    services = get_compile_services()
    with services.manager.session_lock(session.thread_id, session.session_id):
        try:
            current = services.manager.load_session(session.session_id, session.thread_id)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            current = session
        if current.finalized_at is not None:
            replay_cleanup_result = _cleanup_pending_replay_containers(current)
            compile_cleanup_result = services.runtime.stop_and_remove_container(current)
            session.__dict__.update(current.__dict__)
            return session, _combined_cleanup_result(replay_cleanup_result, compile_cleanup_result)
        if interrupted_status is not None:
            _request_session_termination(current, status=interrupted_status, error=error)
        replay_cleanup_result = _cleanup_pending_replay_containers(current)
        compile_cleanup_result = services.runtime.stop_and_remove_container(current)
        cleanup_result = _combined_cleanup_result(replay_cleanup_result, compile_cleanup_result)
        session.__dict__.update(current.__dict__)
        return session, cleanup_result


def finalize_unfinished_thread_sessions_impl(
    *,
    thread_id: str,
    run_id: str | None = None,
    interrupted_status: str | None = None,
    error: str | None = None,
) -> list[CompileSession]:
    """Clean and finalize sessions left behind when a parent run exits."""
    services = get_compile_services()
    finalized: list[CompileSession] = []
    for discovered_session in services.manager.list_sessions(thread_id):
        if run_id is not None and discovered_session.run_id != run_id:
            continue
        with services.manager.session_lock(thread_id, discovered_session.session_id):
            try:
                session = services.manager.load_session(discovered_session.session_id, thread_id)
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                session = discovered_session
            if session.finalized_at is not None or (run_id is not None and session.run_id != run_id):
                continue
            updated, _cleanup_result = cleanup_and_finalize_compile_session_impl(
                session=session,
                interrupted_status=interrupted_status,
                error=error,
            )
            finalized.append(updated)
    return finalized


def finalize_compile_session_json(
    *,
    session: CompileSession,
    summary: str | None = None,
    status: str = "completed",
    error: str | None = None,
    generate_repro_bundle: bool = True,
) -> str:
    updated = finalize_compile_session_impl(
        session=session,
        summary=summary,
        status=status,
        error=error,
        generate_repro_bundle=generate_repro_bundle,
    )
    return json.dumps(updated.to_dict(), ensure_ascii=False, indent=2)
