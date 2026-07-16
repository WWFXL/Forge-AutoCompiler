from __future__ import annotations

import json
import struct
import uuid
from dataclasses import dataclass
from pathlib import Path
from shlex import quote
from typing import BinaryIO

from deerflow.compile.docker_runtime import CONTAINER_REPO_DIR, CONTAINER_WORKSPACE_DIR, CompileDockerRuntime, ContainerCleanupResult
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
    run_id: str | None = None,
) -> CompileSession:
    services = get_compile_services()
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

    clone_command_parts = ["git clone", f"--depth {depth}"]
    if branch:
        clone_command_parts.append(f"--branch {shell_quote(branch)}")
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
            branch=branch,
            depth=depth,
            attempt=attempt,
            max_retries=retries,
            log_path=log_path,
            target_dir=str(repo_dir),
        )
        started_at = utc_now_iso()

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
    try:
        resolved_base = base.resolve(strict=True)
    except OSError:
        return []
    files: list[Path] = []
    for p in base.rglob("*"):
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
) -> bool:
    if section_header_count < 2 or not 0 < section_name_index < section_header_count:
        return False

    meaningful_section_found = False
    valid_name_table = False
    for index in range(section_header_count):
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


def _classify_elf_stream(stream: BinaryIO, *, base_offset: int, file_size: int) -> str | None:
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


def _classify_archive_stream(stream: BinaryIO, *, file_size: int) -> str | None:
    if file_size < len(_AR_MAGIC) + _AR_MEMBER_HEADER_SIZE:
        return None

    offset = len(_AR_MAGIC)
    compiled_member_found = False
    while offset < file_size:
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
            )
            compiled_member_found = compiled_member_found or member_type == "object"

        offset = payload_end + (member_size % 2)
        if offset > file_size:
            return None

    return "static_library" if compiled_member_found else None


def _classify_compiled_artifact(path: Path) -> str | None:
    """Classify supported Linux C/C++ outputs from file contents."""
    try:
        if path.is_symlink() or not path.is_file():
            return None
        file_size = path.stat().st_size
        with path.open("rb") as stream:
            magic = stream.read(len(_AR_MAGIC))
            if magic == _AR_MAGIC:
                return _classify_archive_stream(stream, file_size=file_size)
            return _classify_elf_stream(stream, base_offset=0, file_size=file_size)
    except OSError:
        return None


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
                )
            )

    if discovered_files and not artifacts:
        notes.append("Error: Verification failed. No recognized compiled artifacts were found in /artifacts.")

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

    failure_message = next(
        (note for note in notes if note.startswith("Error:")),
        "Error: Verification failed. The submitted artifacts in /artifacts did not pass validation.",
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
        "message": "Build artifacts accepted from /artifacts." if status == "passed" else failure_message,
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
        _write_repro_bundle(session)
        services.manager.mark_session_status(session, "verified")
        services.manager.log_event(session, "verification.accepted", artifact_count=len(artifacts))
    else:
        services.manager.mark_session_status(session, "verification_failed", error=payload["message"])

    return json.dumps(payload, ensure_ascii=False, indent=2)


def _write_repro_bundle(session: CompileSession) -> Path:
    repro_dir = Path(session.metadata_path).parent / "repro"
    repro_dir.mkdir(parents=True, exist_ok=True)
    build_lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
    for command in session.commands:
        build_lines.append(command.command)
    build_path = repro_dir / "build.sh"
    build_path.write_text("\n".join(build_lines) + "\n", encoding="utf-8")
    return build_path


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
            if generate_repro_bundle:
                _write_repro_bundle(current)
            current.finalized_at = utc_now_iso()
            services.manager.mark_session_status(current, status, error=error, summary=summary)
            services.manager.log_event(
                current,
                "finalize.completed",
                status=status,
                summary=summary,
                finalized_at=current.finalized_at,
                generate_repro_bundle=generate_repro_bundle,
            )

        session.__dict__.update(current.__dict__)
        return session


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
            session.__dict__.update(current.__dict__)
            return session, ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

        cleanup_result = services.runtime.stop_and_remove_container(current)
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

        verification_passed = current.status == "verified" and current.verification is not None and current.verification.status == "passed" and bool(current.artifacts)
        if interrupted_status is not None:
            final_status = interrupted_status
            final_error = error or f"Parent run ended with status {interrupted_status}."
        elif verification_passed:
            final_status = "completed"
            final_error = None
        elif current.status in {"failed", "cancelled", "timed_out"}:
            final_status = current.status
            final_error = current.error or f"Compile session ended with status {current.status}."
        else:
            final_status = "failed"
            final_error = current.error or "Compile session finalized before artifact verification passed."

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
) -> tuple[CompileSession, ContainerCleanupResult]:
    """Reload and clean a session container under the session lifecycle lock."""
    services = get_compile_services()
    with services.manager.session_lock(session.thread_id, session.session_id):
        try:
            current = services.manager.load_session(session.session_id, session.thread_id)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            current = session
        if current.finalized_at is not None:
            session.__dict__.update(current.__dict__)
            return session, ContainerCleanupResult(succeeded=True, stopped=True, removed=True)
        cleanup_result = services.runtime.stop_and_remove_container(current)
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
