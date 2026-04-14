import os
import re
import shutil
from functools import lru_cache
from pathlib import Path, PureWindowsPath

# Virtual path prefix seen by agents inside the sandbox
VIRTUAL_PATH_PREFIX = "/mnt/user-data"
DEFAULT_WORKSPACE_ROOT = Path("/workspace")
DEFAULT_HOST_WORKSPACE_ROOT = "/mnt/usr/jyh_wwf/LLM-AutoCompiler-v2"

_SAFE_THREAD_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


@lru_cache(maxsize=1)
def get_paths() -> "Paths":
    """Return the process-wide cached Paths instance."""
    return Paths()


def _default_local_base_dir() -> Path:
    """Return the repo-local DeerFlow state directory without relying on cwd."""
    backend_dir = Path(__file__).resolve().parents[4]
    return backend_dir / ".deer-flow"


def _default_workspace_root() -> Path:
    """Return the mounted workspace root inside the current container."""
    return DEFAULT_WORKSPACE_ROOT


def _default_host_workspace_root_str() -> str:
    """Return the host-visible workspace root corresponding to `/workspace`."""
    if env := os.getenv("DEER_FLOW_HOST_WORKSPACE_ROOT"):
        return env
    return DEFAULT_HOST_WORKSPACE_ROOT


def _validate_thread_id(thread_id: str) -> str:
    """Validate a thread ID before using it in filesystem paths."""
    if not _SAFE_THREAD_ID_RE.match(thread_id):
        raise ValueError(f"Invalid thread_id {thread_id!r}: only alphanumeric characters, hyphens, and underscores are allowed.")
    return thread_id


def _join_host_path(base: str, *parts: str) -> str:
    """Join host filesystem path segments while preserving native style."""
    if not parts:
        return base

    if re.match(r"^[A-Za-z]:[\\/]", base) or base.startswith("\\\\") or "\\" in base:
        result = PureWindowsPath(base)
        for part in parts:
            result /= part
        return str(result)

    result = Path(base)
    for part in parts:
        result /= part
    return str(result)


def join_host_path(base: str, *parts: str) -> str:
    """Join host filesystem path segments while preserving native style."""
    return _join_host_path(base, *parts)


def resolve_path(path: str | Path, *, base_dir: str | Path | None = None) -> Path:
    """Resolve a DeerFlow data path to an absolute filesystem path."""
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()

    base = Path(base_dir).expanduser().resolve() if base_dir is not None else get_paths().base_dir
    return (base / candidate).resolve()


class Paths:
    def __init__(self, base_dir: str | Path | None = None) -> None:
        self._base_dir = Path(base_dir).resolve() if base_dir is not None else None

    @property
    def host_base_dir(self) -> Path:
        if env := os.getenv("DEER_FLOW_HOST_BASE_DIR"):
            return Path(env)
        return self.base_dir

    def _host_base_dir_str(self) -> str:
        if env := os.getenv("DEER_FLOW_HOST_BASE_DIR"):
            return env
        return str(self.base_dir)

    def _workspace_root(self) -> Path:
        if env_workspace := os.getenv("DEER_FLOW_WORKSPACE_ROOT"):
            return Path(env_workspace).resolve()
        return _default_workspace_root()

    def _host_workspace_root_str(self) -> str:
        return _default_host_workspace_root_str()

    @property
    def compile_sessions_dir(self) -> Path:
        return self._workspace_root() / ".compile-sessions"

    @property
    def host_compile_sessions_dir(self) -> Path:
        return Path(self._host_workspace_root_str()) / ".compile-sessions"

    def host_compile_sessions_dir_str(self) -> str:
        return _join_host_path(self._host_workspace_root_str(), ".compile-sessions")

    @property
    def base_dir(self) -> Path:
        if self._base_dir is not None:
            return self._base_dir
        if env_home := os.getenv("DEER_FLOW_HOME"):
            return Path(env_home).resolve()
        return _default_local_base_dir()

    @property
    def memory_file(self) -> Path:
        return self.base_dir / "memory.json"

    @property
    def user_md_file(self) -> Path:
        return self.base_dir / "USER.md"

    @property
    def agents_dir(self) -> Path:
        return self.base_dir / "agents"

    def agent_dir(self, name: str) -> Path:
        return self.agents_dir / name.lower()

    def agent_memory_file(self, name: str) -> Path:
        return self.agent_dir(name) / "memory.json"

    def thread_dir(self, thread_id: str) -> Path:
        return self.base_dir / "threads" / _validate_thread_id(thread_id)

    def sandbox_work_dir(self, thread_id: str) -> Path:
        return self.thread_dir(thread_id) / "user-data" / "workspace"

    def sandbox_uploads_dir(self, thread_id: str) -> Path:
        return self.thread_dir(thread_id) / "user-data" / "uploads"

    def sandbox_outputs_dir(self, thread_id: str) -> Path:
        return self.thread_dir(thread_id) / "user-data" / "outputs"

    def acp_workspace_dir(self, thread_id: str) -> Path:
        return self.thread_dir(thread_id) / "acp-workspace"

    def sandbox_user_data_dir(self, thread_id: str) -> Path:
        return self.thread_dir(thread_id) / "user-data"

    def host_thread_dir(self, thread_id: str) -> str:
        return _join_host_path(self._host_base_dir_str(), "threads", _validate_thread_id(thread_id))

    def host_sandbox_user_data_dir(self, thread_id: str) -> str:
        return _join_host_path(self.host_thread_dir(thread_id), "user-data")

    def host_sandbox_work_dir(self, thread_id: str) -> str:
        return _join_host_path(self.host_sandbox_user_data_dir(thread_id), "workspace")

    def host_sandbox_uploads_dir(self, thread_id: str) -> str:
        return _join_host_path(self.host_sandbox_user_data_dir(thread_id), "uploads")

    def host_sandbox_outputs_dir(self, thread_id: str) -> str:
        return _join_host_path(self.host_sandbox_user_data_dir(thread_id), "outputs")

    def host_acp_workspace_dir(self, thread_id: str) -> str:
        return _join_host_path(self.host_thread_dir(thread_id), "acp-workspace")

    def ensure_thread_dirs(self, thread_id: str) -> None:
        for d in [
            self.sandbox_work_dir(thread_id),
            self.sandbox_uploads_dir(thread_id),
            self.sandbox_outputs_dir(thread_id),
            self.acp_workspace_dir(thread_id),
        ]:
            d.mkdir(parents=True, exist_ok=True)
            d.chmod(0o777)

    def delete_thread_dir(self, thread_id: str) -> None:
        thread_dir = self.thread_dir(thread_id)
        if thread_dir.exists():
            shutil.rmtree(thread_dir)

    def resolve_virtual_path(self, thread_id: str, virtual_path: str) -> Path:
        vp = virtual_path.lstrip("/")
        prefix = VIRTUAL_PATH_PREFIX.lstrip("/")

        if not vp.startswith(prefix):
            raise ValueError(f"Unsupported virtual path: {virtual_path}")

        suffix = vp[len(prefix) :].lstrip("/")
        parts = Path(suffix).parts
        if not parts:
            return self.sandbox_user_data_dir(thread_id)

        root, *rest = parts
        if root == "workspace":
            return self.sandbox_work_dir(thread_id).joinpath(*rest)
        if root == "uploads":
            return self.sandbox_uploads_dir(thread_id).joinpath(*rest)
        if root == "outputs":
            return self.sandbox_outputs_dir(thread_id).joinpath(*rest)

        raise ValueError(f"Unsupported virtual path root: {virtual_path}")
