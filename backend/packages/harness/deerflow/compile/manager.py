from __future__ import annotations

import json
import os
import shutil
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
from deerflow.compile.schemas import BuildArtifact, BuildCommandRecord, CompileSession, utc_now_iso

DEFAULT_COMPILE_IMAGE = "autocompiler:gcc13"
WORKFLOW_LOG_NAME = "workflow.log"
TERMINAL_SESSION_STATUSES = {"completed", "failed", "cancelled", "timed_out"}


class CompileSessionManager:
    def __init__(self, paths=None, default_image: str = DEFAULT_COMPILE_IMAGE):
        self.paths = paths
        self.default_image = default_image
        self._session_locks: dict[tuple[str, str], threading.RLock] = {}
        self._session_locks_guard = threading.Lock()

    @contextmanager
    def session_lock(self, thread_id: str, session_id: str) -> Iterator[None]:
        key = (thread_id, session_id)
        with self._session_locks_guard:
            lock = self._session_locks.setdefault(key, threading.RLock())
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
                compile_sessions_root=str(session_dir.parent.parent),
                session_dir=str(session_dir),
                workspace_dir=str(workspace_dir),
                artifacts_dir=str(artifacts_dir),
                logs_dir=str(logs_dir),
                repro_dir=str(repro_dir),
                metadata_path=str(metadata_path),
            )
            return session

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
            return True

    def mark_session_status(self, session: CompileSession, status: str, error: str | None = None, summary: str | None = None) -> CompileSession:
        with self.session_lock(session.thread_id, session.session_id):
            authoritative = self._read_persisted_session(Path(session.metadata_path))
            termination_blocks_transition = authoritative is not None and authoritative.termination_requested_at is not None and status not in TERMINAL_SESSION_STATUSES
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
            if status in TERMINAL_SESSION_STATUSES:
                target.completed_at = target.completed_at if previous_status == status and target.completed_at is not None else utc_now_iso()
            else:
                target.completed_at = None
            target.error = error
            if summary is not None:
                target.summary = summary
            if not self.save_session(
                target,
                allow_lifecycle_fenced=(authoritative is not None and authoritative.termination_requested_at is not None and status in TERMINAL_SESSION_STATUSES),
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
