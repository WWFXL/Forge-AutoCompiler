from __future__ import annotations

from pathlib import Path

from deerflow.config.paths import Paths, join_host_path

COMPILE_SESSIONS_DIRNAME = ".compile-sessions"
DEFAULT_THREAD_ID = "default"


def _safe_thread_id(thread_id: str | None) -> str:
    if not thread_id:
        return DEFAULT_THREAD_ID
    return thread_id


def get_compile_sessions_root(paths: Paths | None = None) -> Path:
    resolved_paths = paths or Paths()
    root = resolved_paths.compile_sessions_dir
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_host_compile_sessions_root(paths: Paths | None = None) -> str:
    resolved_paths = paths or Paths()
    return resolved_paths.host_compile_sessions_dir_str()


def get_thread_compile_root(thread_id: str | None, paths: Paths | None = None) -> Path:
    return get_compile_sessions_root(paths) / _safe_thread_id(thread_id)


def get_host_thread_compile_root(thread_id: str | None, paths: Paths | None = None) -> str:
    return join_host_path(get_host_compile_sessions_root(paths), _safe_thread_id(thread_id))


def get_session_dir(session_id: str, thread_id: str | None, paths: Paths | None = None) -> Path:
    return get_thread_compile_root(thread_id, paths) / session_id


def get_host_session_dir(session_id: str, thread_id: str | None, paths: Paths | None = None) -> str:
    return join_host_path(get_host_thread_compile_root(thread_id, paths), session_id)


def get_workspace_dir(session_id: str, thread_id: str | None, paths: Paths | None = None) -> Path:
    return get_session_dir(session_id, thread_id, paths) / "workspace"


def get_host_workspace_dir(session_id: str, thread_id: str | None, paths: Paths | None = None) -> str:
    return join_host_path(get_host_session_dir(session_id, thread_id, paths), "workspace")


def get_artifacts_dir(session_id: str, thread_id: str | None, paths: Paths | None = None) -> Path:
    return get_session_dir(session_id, thread_id, paths) / "artifacts"


def get_host_artifacts_dir(session_id: str, thread_id: str | None, paths: Paths | None = None) -> str:
    return join_host_path(get_host_session_dir(session_id, thread_id, paths), "artifacts")


def get_logs_dir(session_id: str, thread_id: str | None, paths: Paths | None = None) -> Path:
    return get_session_dir(session_id, thread_id, paths) / "logs"


def get_host_logs_dir(session_id: str, thread_id: str | None, paths: Paths | None = None) -> str:
    return join_host_path(get_host_session_dir(session_id, thread_id, paths), "logs")


def get_repro_dir(session_id: str, thread_id: str | None, paths: Paths | None = None) -> Path:
    return get_session_dir(session_id, thread_id, paths) / "repro"


def get_host_repro_dir(session_id: str, thread_id: str | None, paths: Paths | None = None) -> str:
    return join_host_path(get_host_session_dir(session_id, thread_id, paths), "repro")


def get_metadata_path(session_id: str, thread_id: str | None, paths: Paths | None = None) -> Path:
    return get_session_dir(session_id, thread_id, paths) / "session.json"
