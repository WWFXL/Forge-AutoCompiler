from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from deerflow.compile.paths import (
    get_artifacts_dir,
    get_host_artifacts_dir,
    get_host_logs_dir,
    get_host_repro_dir,
    get_host_session_dir,
    get_host_workspace_dir,
    get_logs_dir,
    get_metadata_path,
    get_repro_dir,
    get_session_dir,
    get_workspace_dir,
)
from deerflow.compile.schemas import BuildArtifact, BuildCommandRecord, CompileSession, utc_now_iso

DEFAULT_COMPILE_IMAGE = "autocompiler:gcc13"
WORKFLOW_LOG_NAME = "workflow.log"


class CompileSessionManager:
    def __init__(self, paths=None, default_image: str = DEFAULT_COMPILE_IMAGE):
        self.paths = paths
        self.default_image = default_image

    def create_session(
        self,
        thread_id: str | None,
        repo_url: str,
        branch: str | None = None,
        task_id: str | None = None,
        image: str | None = None,
    ) -> CompileSession:
        session_id = uuid.uuid4().hex[:12]
        resolved_thread_id = thread_id or "default"

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
            repo_url=repo_url,
            branch=branch,
            task_id=task_id,
            image=image or self.default_image,
            status="created",
            host_session_dir=get_host_session_dir(session_id, resolved_thread_id, self.paths),
            host_workspace_dir=get_host_workspace_dir(session_id, resolved_thread_id, self.paths),
            host_artifacts_dir=get_host_artifacts_dir(session_id, resolved_thread_id, self.paths),
            host_logs_dir=get_host_logs_dir(session_id, resolved_thread_id, self.paths),
            host_repro_dir=get_host_repro_dir(session_id, resolved_thread_id, self.paths),
            metadata_path=str(metadata_path),
        )
        self.save_session(session)
        self.log_event(
            session,
            "session.created",
            repo_url=repo_url,
            branch=branch,
            compile_sessions_root=str(Path(session.host_session_dir).parent.parent),
            host_session_dir=session.host_session_dir,
            host_workspace_dir=session.host_workspace_dir,
            host_artifacts_dir=session.host_artifacts_dir,
            host_logs_dir=session.host_logs_dir,
            host_repro_dir=session.host_repro_dir,
            container_workspace_dir=session.container_workspace_dir,
            container_repo_dir=session.container_repo_dir,
            container_artifacts_dir=session.container_artifacts_dir,
            container_logs_dir=session.container_logs_dir,
            container_repro_dir=session.container_repro_dir,
        )
        return session

    def load_session(self, session_id: str, thread_id: str | None = None) -> CompileSession:
        metadata_path = get_metadata_path(session_id, thread_id or "default", self.paths)
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        return CompileSession.from_dict(data)

    def save_session(self, session: CompileSession) -> None:
        metadata_file = Path(session.metadata_path)
        metadata_file.parent.mkdir(parents=True, exist_ok=True)
        metadata_file.write_text(json.dumps(session.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def mark_session_status(self, session: CompileSession, status: str, error: str | None = None, summary: str | None = None) -> CompileSession:
        previous_status = session.status
        session.status = status
        session.completed_at = utc_now_iso() if status in {"completed", "failed", "cancelled"} else session.completed_at
        if error is not None:
            session.error = error
        if summary is not None:
            session.summary = summary
        self.save_session(session)
        self.log_event(
            session,
            "session.status_changed",
            previous_status=previous_status,
            status=status,
            error=error,
            summary=summary,
            completed_at=session.completed_at,
        )
        return session

    def record_command(self, session: CompileSession, command: BuildCommandRecord) -> CompileSession:
        session.commands.append(command)
        self.save_session(session)
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
        )
        return session

    def record_artifact(self, session: CompileSession, artifact: BuildArtifact) -> CompileSession:
        session.artifacts.append(artifact)
        self.save_session(session)
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
        log_path = self.workflow_log_path(session)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": utc_now_iso(),
            "event": event,
            "session_id": session.session_id,
            "thread_id": session.thread_id,
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
