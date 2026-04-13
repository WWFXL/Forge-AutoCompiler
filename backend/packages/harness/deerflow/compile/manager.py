from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from deerflow.compile.paths import get_artifacts_dir, get_logs_dir, get_metadata_path, get_repro_dir, get_session_dir, get_workspace_dir
from deerflow.compile.schemas import BuildArtifact, BuildCommandRecord, CompileSession, utc_now_iso

DEFAULT_COMPILE_IMAGE = "autocompiler:gcc13"


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
            host_session_dir=str(session_dir),
            host_workspace_dir=str(workspace_dir),
            host_artifacts_dir=str(artifacts_dir),
            host_logs_dir=str(logs_dir),
            host_repro_dir=str(repro_dir),
            metadata_path=str(metadata_path),
        )
        self.save_session(session)
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
        session.status = status
        session.completed_at = utc_now_iso() if status in {"completed", "failed", "cancelled"} else session.completed_at
        if error is not None:
            session.error = error
        if summary is not None:
            session.summary = summary
        self.save_session(session)
        return session

    def record_command(self, session: CompileSession, command: BuildCommandRecord) -> CompileSession:
        session.commands.append(command)
        self.save_session(session)
        return session

    def record_artifact(self, session: CompileSession, artifact: BuildArtifact) -> CompileSession:
        session.artifacts.append(artifact)
        self.save_session(session)
        return session

    def relative_path(self, session: CompileSession, path: str | Path) -> str:
        target = Path(path)
        session_dir = Path(session.host_session_dir)
        try:
            relative = target.relative_to(session_dir.parent.parent)
        except ValueError:
            return str(target)
        return relative.as_posix()

    def copy_artifact_into_session(self, session: CompileSession, source_path: str | Path) -> str:
        src = Path(source_path)
        destination = Path(session.host_artifacts_dir) / src.name
        if src.resolve() != destination.resolve():
            shutil.copy2(src, destination)
        return str(destination)
