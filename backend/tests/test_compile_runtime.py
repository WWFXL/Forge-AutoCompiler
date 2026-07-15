from pathlib import Path

import pytest

from deerflow.compile.docker_runtime import DEFAULT_NETWORK, CompileDockerRuntime
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.paths import get_compile_sessions_root, get_host_session_dir, get_host_workspace_dir, get_metadata_path, get_session_dir
from deerflow.compile.schemas import BuildArtifact, BuildCommandRecord, CompileSession
from deerflow.config.paths import Paths


@pytest.fixture(autouse=True)
def isolate_compile_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace_root = tmp_path / "workspace"
    monkeypatch.setenv("DEER_FLOW_WORKSPACE_ROOT", str(workspace_root))
    monkeypatch.setenv("DEER_FLOW_HOST_WORKSPACE_ROOT", str(workspace_root))


def make_test_paths(tmp_path: Path, *, host_workspace_root: str | None = None) -> Paths:
    return Paths(
        base_dir=tmp_path / ".deer-flow",
        workspace_root=tmp_path / "service-workspace",
        host_workspace_root=host_workspace_root or str(tmp_path / "host-workspace"),
    )


def test_create_session_creates_expected_directory_layout(tmp_path: Path):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))

    session = manager.create_session(thread_id="thread-1", repo_url="https://example.com/repo.git", branch="main")

    session_dir = get_session_dir(session.session_id, session.thread_id, manager.paths)
    assert session_dir.exists()
    assert (session_dir / "workspace").exists()
    assert (session_dir / "artifacts").exists()
    assert (session_dir / "logs").exists()
    assert (session_dir / "repro").exists()
    assert get_metadata_path(session.session_id, session.thread_id, manager.paths).exists()


def test_create_session_under_compile_sessions_root(tmp_path: Path):
    paths = make_test_paths(tmp_path)
    manager = CompileSessionManager(paths=paths)

    session = manager.create_session(thread_id="abc", repo_url="https://example.com/repo.git")

    compile_root = get_compile_sessions_root(paths)
    session_dir = get_session_dir(session.session_id, session.thread_id, paths)
    assert session_dir == compile_root / "abc" / session.session_id
    assert Path(session.metadata_path).parent == session_dir
    assert get_host_session_dir(session.session_id, session.thread_id, paths).startswith(paths.host_workspace_root_str())


def test_save_and_load_session_roundtrip(tmp_path: Path):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-2", repo_url="https://example.com/repo.git")
    session.container_id = "container-123"
    session.container_name = "demo-container"
    session.build_system = "make"
    session.summary = "done"
    session.commands.append(BuildCommandRecord(stage="clone", command="git clone ...", workdir="/workspace"))
    session.artifacts.append(BuildArtifact(path="artifacts/app", artifact_type="binary", size_bytes=123))
    manager.save_session(session)

    loaded = manager.load_session(session.session_id, session.thread_id)

    assert isinstance(loaded, CompileSession)
    assert loaded.container_id == "container-123"
    assert loaded.build_system == "make"
    assert loaded.summary == "done"
    assert len(loaded.commands) == 1
    assert len(loaded.artifacts) == 1


def test_mark_status_sets_completed_at_for_terminal_state(tmp_path: Path):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-3", repo_url="https://example.com/repo.git")

    manager.mark_session_status(session, "completed", summary="ok")

    assert session.completed_at is not None
    assert session.summary == "ok"


def test_host_workspace_path_preserves_windows_style(tmp_path: Path):
    paths = make_test_paths(tmp_path, host_workspace_root=r"C:\Users\developer\Forge-AutoCompiler")
    manager = CompileSessionManager(paths=paths)
    session = manager.create_session(thread_id="windows-thread", repo_url="https://example.com/repo.git")

    assert get_host_workspace_dir(session.session_id, session.thread_id, paths) == (rf"C:\Users\developer\Forge-AutoCompiler\.compile-sessions\windows-thread\{session.session_id}\workspace")


def test_docker_runtime_uses_paths_host_workspace_root(tmp_path: Path, monkeypatch):
    host_root = tmp_path / "docker-host"
    paths = make_test_paths(tmp_path, host_workspace_root=str(host_root))
    manager = CompileSessionManager(paths=paths)
    session = manager.create_session(thread_id="thread-runtime", repo_url="https://example.com/repo.git")
    runtime = CompileDockerRuntime(manager=manager)
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        del kwargs
        commands.append(command)
        return type("Result", (), {"stdout": "container-id\n", "stderr": "", "returncode": 0})()

    monkeypatch.setattr("deerflow.compile.docker_runtime.subprocess.run", fake_run)

    runtime.create_container(session)

    docker_command = next(command for command in commands if command[:2] == ["docker", "run"])
    assert ["docker", "network", "inspect", DEFAULT_NETWORK] in commands
    assert f"{host_root / '.compile-sessions' / session.thread_id / session.session_id / 'workspace'}:/workspace" in docker_command
    assert "HOST_PROJECT_ROOT" not in docker_command


def test_docker_runtime_creates_missing_network(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-network", repo_url="https://example.com/repo.git")
    runtime = CompileDockerRuntime(manager=manager)
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        del kwargs
        commands.append(command)
        if command[:3] == ["docker", "network", "inspect"]:
            return type("Result", (), {"stdout": "", "stderr": "not found", "returncode": 1})()
        return type("Result", (), {"stdout": "container-id\n", "stderr": "", "returncode": 0})()

    monkeypatch.setattr("deerflow.compile.docker_runtime.subprocess.run", fake_run)

    runtime.create_container(session)

    assert ["docker", "network", "create", DEFAULT_NETWORK] in commands
