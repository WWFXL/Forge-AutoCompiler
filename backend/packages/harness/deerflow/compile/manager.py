from __future__ import annotations

import json
import os
import re
import shutil
import stat
import tempfile
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from deerflow.compile.evidence import record_experiment_event
from deerflow.compile.paths import (
    get_artifacts_dir,
    get_logs_dir,
    get_metadata_path,
    get_repro_dir,
    get_session_dir,
    get_thread_compile_root,
    get_workspace_dir,
)
from deerflow.compile.schemas import DEFAULT_COMPILE_PARALLEL_JOBS, TERMINAL_COMPILE_SESSION_STATUSES, BuildArtifact, BuildCommandRecord, CompileSession, utc_now_iso

DEFAULT_COMPILE_IMAGE = "autocompiler:gcc13"
WORKFLOW_LOG_NAME = "workflow.log"
_MAX_HOST_ID = 2**32 - 2
_SESSION_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")


def _configured_host_identity() -> tuple[int, int] | None:
    uid_value = os.getenv("FORGE_HOST_UID") or None
    gid_value = os.getenv("FORGE_HOST_GID") or None
    if uid_value is None and gid_value is None:
        return None
    if uid_value is None or gid_value is None:
        raise ValueError("FORGE_HOST_UID and FORGE_HOST_GID must be configured together")
    try:
        uid = int(uid_value)
        gid = int(gid_value)
    except ValueError as exc:
        raise ValueError("FORGE_HOST_UID and FORGE_HOST_GID must be non-negative integers") from exc
    if not (0 <= uid <= _MAX_HOST_ID and 0 <= gid <= _MAX_HOST_ID):
        raise ValueError(f"FORGE_HOST_UID and FORGE_HOST_GID must be between 0 and {_MAX_HOST_ID}")
    return uid, gid


def _change_owner(path: Path, uid: int, gid: int, *, follow_symlinks: bool) -> None:
    if follow_symlinks:
        os.chown(path, uid, gid)
    elif hasattr(os, "lchown"):
        os.lchown(path, uid, gid)
    else:
        os.chown(path, uid, gid, follow_symlinks=False)


def _configured_parallel_jobs() -> int:
    try:
        value = int(os.getenv("COMPILE_MAX_PARALLEL_JOBS", str(DEFAULT_COMPILE_PARALLEL_JOBS)))
    except ValueError:
        return DEFAULT_COMPILE_PARALLEL_JOBS
    return value if value > 0 else DEFAULT_COMPILE_PARALLEL_JOBS


class CompileSessionManager:
    def __init__(self, paths=None, default_image: str = DEFAULT_COMPILE_IMAGE, parallel_jobs: int | None = None):
        self.paths = paths
        self.default_image = default_image
        self.parallel_jobs = parallel_jobs if parallel_jobs is not None and parallel_jobs > 0 else _configured_parallel_jobs()
        self.host_identity = _configured_host_identity()
        self._session_locks: dict[tuple[str, str], threading.RLock] = {}
        self._session_locks_guard = threading.Lock()
        self._run_locks: dict[tuple[str, str], threading.RLock] = {}
        self._run_locks_guard = threading.Lock()

    @contextmanager
    def session_lock(self, thread_id: str, session_id: str) -> Iterator[None]:
        key = (thread_id, session_id)
        with self._session_locks_guard:
            lock = self._session_locks.setdefault(key, threading.RLock())
        with lock:
            yield

    @contextmanager
    def run_lock(self, thread_id: str, run_id: str) -> Iterator[None]:
        key = (thread_id, run_id)
        with self._run_locks_guard:
            lock = self._run_locks.setdefault(key, threading.RLock())
        with lock:
            yield

    def create_session(
        self,
        thread_id: str | None,
        repo_url: str,
        branch: str | None = None,
        image: str | None = None,
        run_id: str | None = None,
        session_id: str | None = None,
    ) -> CompileSession:
        session_id = session_id or uuid.uuid4().hex[:12]
        resolved_thread_id = thread_id or "default"
        self._validate_session_components(resolved_thread_id, session_id)
        with self.session_lock(resolved_thread_id, session_id):
            session_dir = get_session_dir(session_id, resolved_thread_id, self.paths)
            workspace_dir = get_workspace_dir(session_id, resolved_thread_id, self.paths)
            artifacts_dir = get_artifacts_dir(session_id, resolved_thread_id, self.paths)
            logs_dir = get_logs_dir(session_id, resolved_thread_id, self.paths)
            repro_dir = get_repro_dir(session_id, resolved_thread_id, self.paths)
            metadata_path = get_metadata_path(session_id, resolved_thread_id, self.paths)

            for directory in (session_dir, workspace_dir, artifacts_dir, logs_dir, repro_dir):
                directory.mkdir(parents=True, exist_ok=True)

            session = CompileSession(
                session_id=session_id,
                thread_id=resolved_thread_id,
                run_id=run_id,
                repo_url=repo_url,
                branch=branch,
                image=image or self.default_image,
                status="created",
                parallel_jobs=self.parallel_jobs,
                metadata_path=str(metadata_path),
                leadagent_repo_dir=str(workspace_dir / "repo"),
                leadagent_artifacts_dir=str(artifacts_dir),
                leadagent_logs_dir=str(logs_dir),
                leadagent_repro_dir=str(repro_dir),
            )

            self.save_session(session)
            self.log_event(
                session,
                "session.created",
                run_id=run_id,
                repo_url=repo_url,
                branch=branch,
                image=session.image,
                parallel_jobs=session.parallel_jobs,
                compile_sessions_root=str(session_dir.parent.parent),
                session_dir=str(session_dir),
                workspace_dir=str(workspace_dir),
                artifacts_dir=str(artifacts_dir),
                logs_dir=str(logs_dir),
                repro_dir=str(repro_dir),
                metadata_path=str(metadata_path),
            )
            return session

    @staticmethod
    def _validate_session_components(thread_id: str, session_id: str) -> None:
        if not _SESSION_COMPONENT.fullmatch(thread_id) or not _SESSION_COMPONENT.fullmatch(session_id):
            raise ValueError("Compile thread and session identifiers must be safe path components")

    def _validated_session_dir(self, session: CompileSession) -> Path:
        self._validate_session_components(session.thread_id, session.session_id)
        root = get_thread_compile_root(session.thread_id, self.paths).parent
        expected = get_session_dir(session.session_id, session.thread_id, self.paths)
        metadata_directory = Path(session.metadata_path).parent
        if root.is_symlink() or (root / session.thread_id).is_symlink() or expected.is_symlink():
            raise ValueError("Compile session root must not contain symbolic-link boundaries")
        root_resolved = root.resolve(strict=True)
        expected_absolute = expected.absolute()
        if metadata_directory.absolute() != expected_absolute:
            raise ValueError("Compile session root does not match the session metadata path")
        try:
            relative = expected_absolute.relative_to(root.absolute())
        except ValueError as exc:
            raise ValueError("Compile session root is outside the configured compile sessions root") from exc
        if relative.parts != (session.thread_id, session.session_id):
            raise ValueError("Compile session root must have exactly <thread>/<session> components")
        resolved = expected.resolve(strict=True)
        if not resolved.is_relative_to(root_resolved) or resolved == root_resolved:
            raise ValueError("Compile session root is outside the configured compile sessions root")
        return resolved

    def _normalize_owned_path(self, path: Path) -> None:
        if self.host_identity is None:
            return
        uid, gid = self.host_identity
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            _change_owner(path, uid, gid, follow_symlinks=False)
            return
        _change_owner(path, uid, gid, follow_symlinks=True)
        current_mode = stat.S_IMODE(metadata.st_mode)
        if stat.S_ISDIR(metadata.st_mode):
            path.chmod((current_mode | 0o700) & ~0o007)
        elif stat.S_ISREG(metadata.st_mode):
            path.chmod((current_mode | 0o600) & ~0o007)

    def normalize_metadata(self, session: CompileSession) -> bool:
        if self.host_identity is None:
            return False
        session_dir = self._validated_session_dir(session)
        metadata_path = Path(session.metadata_path)
        if metadata_path.absolute() != (session_dir / "session.json").absolute():
            raise ValueError("Compile metadata path is outside the compile session root")
        self._normalize_owned_path(metadata_path)
        return True

    def normalize_event_log(self, session: CompileSession) -> bool:
        if self.host_identity is None:
            return False
        session_dir = self._validated_session_dir(session)
        log_path = self.workflow_log_path(session)
        if log_path.absolute() != (session_dir / "logs" / WORKFLOW_LOG_NAME).absolute():
            raise ValueError("Compile workflow log is outside the compile session root")
        self._normalize_owned_path(log_path)
        return True

    def normalize_session_tree(self, session: CompileSession) -> bool:
        if self.host_identity is None:
            return False
        session_dir = self._validated_session_dir(session)

        def normalize_directory(directory: Path) -> None:
            with os.scandir(directory) as entries:
                children = [Path(entry.path) for entry in entries]
            for child in children:
                metadata = child.lstat()
                if stat.S_ISLNK(metadata.st_mode):
                    self._normalize_owned_path(child)
                elif stat.S_ISDIR(metadata.st_mode):
                    normalize_directory(child)
                else:
                    self._normalize_owned_path(child)
            self._normalize_owned_path(directory)

        normalize_directory(session_dir)
        return True

    def load_session(self, session_id: str, thread_id: str | None = None) -> CompileSession:
        resolved_thread_id = thread_id or "default"
        with self.session_lock(resolved_thread_id, session_id):
            metadata_path = get_metadata_path(session_id, resolved_thread_id, self.paths)
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
            return CompileSession.from_dict(data)

    def list_sessions(self, thread_id: str) -> list[CompileSession]:
        thread_root = get_thread_compile_root(thread_id, self.paths)
        sessions: list[CompileSession] = []
        for metadata_path in sorted(thread_root.glob("*/session.json")):
            try:
                data = json.loads(metadata_path.read_text(encoding="utf-8"))
                sessions.append(CompileSession.from_dict(data))
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return sessions

    def list_active_run_sessions(self, thread_id: str, run_id: str) -> list[CompileSession]:
        return [session for session in self.list_sessions(thread_id) if session.run_id == run_id and session.status not in TERMINAL_COMPILE_SESSION_STATUSES and session.finalized_at is None]

    @staticmethod
    def _read_persisted_session(metadata_file: Path) -> CompileSession | None:
        if not metadata_file.is_file():
            return None
        try:
            return CompileSession.from_dict(json.loads(metadata_file.read_text(encoding="utf-8")))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _merge_finalized_replay_cleanup(
        authoritative: CompileSession,
        proposed: CompileSession,
    ) -> None:
        proposed_by_id = {attempt.attempt_id: attempt for attempt in proposed.replay_attempts}
        for attempt in authoritative.replay_attempts:
            update = proposed_by_id.get(attempt.attempt_id)
            if update is None:
                continue
            if attempt.status in {"pending", "running"} and update.status == "cancelled":
                attempt.status = "cancelled"
                attempt.failure_classification = attempt.failure_classification or "cancelled"
                attempt.completed_at = attempt.completed_at or update.completed_at
                attempt.duration_seconds = attempt.duration_seconds if attempt.duration_seconds is not None else update.duration_seconds
            if attempt.cleanup_succeeded is True or update.cleanup_succeeded is True:
                attempt.cleanup_succeeded = True
            elif update.cleanup_succeeded is False:
                attempt.cleanup_succeeded = False
            for note in update.notes:
                if note.startswith(("Parent replay cleanup raised an error:", "Replay was stopped by the parent compile-session cleanup path.")) and note not in attempt.notes:
                    attempt.notes.append(note)
            for check in update.checks:
                if check.name == "parent_container_cleanup" and check not in attempt.checks:
                    attempt.checks.append(check)

    def save_session(
        self,
        session: CompileSession,
        *,
        allow_lifecycle_fenced: bool = False,
        merge_finalized_replay_cleanup: bool = False,
    ) -> bool:
        with self.session_lock(session.thread_id, session.session_id):
            metadata_file = Path(session.metadata_path)
            metadata_file.parent.mkdir(parents=True, exist_ok=True)
            authoritative = self._read_persisted_session(metadata_file)
            termination_fenced = authoritative is not None and authoritative.termination_requested_at is not None and not allow_lifecycle_fenced
            if authoritative is not None and authoritative.finalized_at is not None and merge_finalized_replay_cleanup:
                self._merge_finalized_replay_cleanup(authoritative, session)
                session.__dict__.update(authoritative.__dict__)
            elif authoritative is not None and (authoritative.finalized_at is not None or termination_fenced):
                session.__dict__.update(authoritative.__dict__)
                return False
            payload = json.dumps(session.to_dict(), ensure_ascii=False, indent=2)
            temporary_path: str | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=metadata_file.parent,
                    prefix=f".{metadata_file.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as fp:
                    temporary_path = fp.name
                    fp.write(payload)
                    fp.flush()
                    os.fsync(fp.fileno())
                os.replace(temporary_path, metadata_file)
            finally:
                if temporary_path and os.path.exists(temporary_path):
                    os.unlink(temporary_path)
            self.normalize_metadata(session)
            return True

    def mark_session_status(self, session: CompileSession, status: str, error: str | None = None, summary: str | None = None) -> CompileSession:
        with self.session_lock(session.thread_id, session.session_id):
            authoritative = self._read_persisted_session(Path(session.metadata_path))
            termination_blocks_transition = authoritative is not None and authoritative.termination_requested_at is not None and status not in TERMINAL_COMPILE_SESSION_STATUSES
            if authoritative is not None and (authoritative.finalized_at is not None or termination_blocks_transition):
                session.__dict__.update(authoritative.__dict__)
                return session

            target = session
            if authoritative is not None and authoritative.termination_requested_at is not None:
                target = authoritative
                if session.termination_requested_at == authoritative.termination_requested_at and session.finalized_at is not None:
                    target.finalized_at = session.finalized_at

            previous_status = target.status
            target.status = status
            if status in TERMINAL_COMPILE_SESSION_STATUSES:
                target.completed_at = target.completed_at if previous_status == status and target.completed_at is not None else utc_now_iso()
            else:
                target.completed_at = None
            target.error = error
            if summary is not None:
                target.summary = summary
            if not self.save_session(
                target,
                allow_lifecycle_fenced=(authoritative is not None and authoritative.termination_requested_at is not None and status in TERMINAL_COMPILE_SESSION_STATUSES),
            ):
                session.__dict__.update(target.__dict__)
                return session
            self.log_event(
                target,
                "session.status_changed",
                previous_status=previous_status,
                status=status,
                error=error,
                summary=summary,
                completed_at=target.completed_at,
            )
            session.__dict__.update(target.__dict__)
            return session

    def record_command(self, session: CompileSession, command: BuildCommandRecord) -> CompileSession:
        session.commands.append(command)
        if self.save_session(session):
            self.log_event(
                session,
                "command.recorded",
                stage=command.stage,
                command=command.command,
                workdir=command.workdir,
                started_at=command.started_at,
                completed_at=command.completed_at,
                exit_code=command.exit_code,
                log_path=command.log_path,
                command_id=command.command_id,
                role=command.role,
                timeout_seconds=command.timeout_seconds,
                duration_seconds=command.duration_seconds,
                timed_out=command.timed_out,
                termination=command.termination,
            )
            record_experiment_event(
                session.thread_id,
                "command.completed",
                command_id=command.command_id,
                session_id=session.session_id,
                role=command.role,
                stage=command.stage,
                exit_code=command.exit_code,
                timeout_seconds=command.timeout_seconds,
                duration_seconds=command.duration_seconds,
                timed_out=command.timed_out,
                termination=command.termination,
            )
        return session

    def record_artifact(self, session: CompileSession, artifact: BuildArtifact) -> CompileSession:
        session.artifacts.append(artifact)
        if self.save_session(session):
            self.log_event(
                session,
                "artifact.recorded",
                path=artifact.path,
                artifact_type=artifact.artifact_type,
                size_bytes=artifact.size_bytes,
                source_path=artifact.source_path,
            )
        return session

    def local_logs_dir(self, session: CompileSession) -> Path:
        return Path(session.metadata_path).parent / "logs"

    def workflow_log_path(self, session: CompileSession) -> Path:
        return self.local_logs_dir(session) / WORKFLOW_LOG_NAME

    def log_event(self, session: CompileSession, event: str, **payload) -> None:
        with self.session_lock(session.thread_id, session.session_id):
            log_path = self.workflow_log_path(session)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "ts": utc_now_iso(),
                "event": event,
                "session_id": session.session_id,
                "thread_id": session.thread_id,
                "run_id": session.run_id,
                **payload,
            }
            with log_path.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self.normalize_event_log(session)

    def relative_path(self, session: CompileSession, path: str | Path) -> str:
        target = Path(path)
        session_dir = Path(session.metadata_path).parent
        try:
            relative = target.relative_to(session_dir.parent.parent)
        except ValueError:
            return str(target)
        return relative.as_posix()

    def copy_artifact_into_session(self, session: CompileSession, source_path: str | Path) -> str:
        src = Path(source_path)
        destination = Path(session.metadata_path).parent / "artifacts" / src.name
        copied = src.resolve() != destination.resolve()
        if copied:
            shutil.copy2(src, destination)
        self.log_event(
            session,
            "artifact.copied",
            source_path=str(src),
            destination_path=str(destination),
            copied=copied,
        )
        return str(destination)
