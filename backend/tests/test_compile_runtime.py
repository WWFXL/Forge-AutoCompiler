import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow.compile import operations
from deerflow.compile.docker_runtime import DEFAULT_NETWORK, CompileDockerRuntime, RuntimeConfig
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.operations import CompileOperationsServices, clone_repository_impl
from deerflow.compile.paths import get_compile_sessions_root, get_host_session_dir, get_host_workspace_dir, get_metadata_path, get_session_dir
from deerflow.compile.schemas import BuildArtifact, BuildCommandRecord, CommandResult, CompileSession
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
    runtime = CompileDockerRuntime(config=RuntimeConfig(network=DEFAULT_NETWORK), manager=manager)
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
    runtime = CompileDockerRuntime(config=RuntimeConfig(network=DEFAULT_NETWORK), manager=manager)
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


def test_docker_runtime_passes_runtime_proxy_values_out_of_band(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-proxy", repo_url="https://example.com/repo.git")
    proxy_url = "http://127.0.0.1:7897"
    monkeypatch.setenv("COMPILE_RUNTIME_NETWORK", "host")
    monkeypatch.setenv("COMPILE_RUNTIME_HTTP_PROXY", proxy_url)
    monkeypatch.setenv("COMPILE_RUNTIME_HTTPS_PROXY", proxy_url)
    monkeypatch.setenv("COMPILE_RUNTIME_NO_PROXY", "localhost,127.0.0.1")
    calls: list[tuple[list[str], dict]] = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return type("Result", (), {"stdout": "container-id\n", "stderr": "", "returncode": 0})()

    monkeypatch.setattr("deerflow.compile.docker_runtime.subprocess.run", fake_run)

    CompileDockerRuntime(manager=manager).create_container(session)

    commands = [command for command, _ in calls]
    assert ["docker", "network", "inspect", "host"] in commands
    docker_command, docker_kwargs = next((command, kwargs) for command, kwargs in calls if command[:2] == ["docker", "run"])
    assert ["--network", "host"] == docker_command[docker_command.index("--network") : docker_command.index("--network") + 2]
    assert ["--add-host", "host.docker.internal:host-gateway"] == docker_command[docker_command.index("--add-host") : docker_command.index("--add-host") + 2]
    assert docker_command.count("-e") == 6
    assert "HTTP_PROXY" in docker_command
    assert "http_proxy" in docker_command
    assert "HTTPS_PROXY" in docker_command
    assert "https_proxy" in docker_command
    assert "NO_PROXY" in docker_command
    assert "no_proxy" in docker_command
    assert proxy_url not in docker_command
    assert docker_kwargs["env"]["HTTP_PROXY"] == proxy_url
    assert docker_kwargs["env"]["https_proxy"] == proxy_url
    assert docker_kwargs["env"]["NO_PROXY"] == "localhost,127.0.0.1"


def test_docker_runtime_exec_enforces_timeout_inside_container(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-exec-timeout", repo_url="https://example.com/repo.git")
    session.container_id = "container-123"
    calls: list[tuple[list[str], dict]] = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout="ok\n", stderr="", returncode=0)

    monkeypatch.setattr("deerflow.compile.docker_runtime.subprocess.run", fake_run)

    result = CompileDockerRuntime(manager=manager).exec(session, "echo ok", timeout_seconds=7)

    docker_command, docker_kwargs = calls[0]
    assert docker_command[-7:] == ["timeout", "--signal=TERM", "--kill-after=5s", "7s", "bash", "-lc", "echo ok"]
    assert docker_kwargs["timeout"] == 17
    assert result.exit_code == 0


def test_docker_runtime_exec_records_docker_client_timeout(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-client-timeout", repo_url="https://example.com/repo.git")
    session.container_id = "container-123"
    log_path = tmp_path / "timeout.log"

    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output="partial output\n", stderr="stalled\n")

    monkeypatch.setattr("deerflow.compile.docker_runtime.subprocess.run", fake_run)

    result = CompileDockerRuntime(manager=manager).exec(session, "long-command", timeout_seconds=3, log_path=str(log_path))

    assert result.exit_code == 124
    assert result.stdout == "partial output\n"
    assert result.stderr == "stalled\n"
    assert "3-second container timeout" in result.combined_output
    assert log_path.read_text(encoding="utf-8") == result.combined_output


def test_clone_repository_runs_git_inside_compile_container(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-clone", repo_url="https://example.com/repo.git")
    session.container_id = "container-123"
    calls: list[tuple[str, str | None, str | None]] = []

    def fake_exec(session_arg, command, workdir=None, timeout_seconds=600, log_path=None):
        del timeout_seconds
        assert session_arg is session
        calls.append((command, workdir, log_path))
        if "git clone" in command:
            Path(session.leadagent_repo_dir).mkdir(parents=True)
            return CommandResult(exit_code=0, stdout="", stderr="", combined_output="", log_path=log_path)
        return CommandResult(exit_code=0, stdout="abc123\n", stderr="", combined_output="abc123\n")

    services = CompileOperationsServices(manager=manager, runtime=SimpleNamespace(exec=fake_exec))
    monkeypatch.setattr(operations, "_services", services)

    result, message = clone_repository_impl(
        session=session,
        repo_url=session.repo_url,
        branch="release branch",
        depth=1,
    )

    assert result.exit_code == 0
    assert calls[0][0] == "rm -rf -- /workspace/repo && git clone --depth 1 --branch 'release branch' https://example.com/repo.git /workspace/repo"
    assert calls[0][1] == "/workspace"
    assert calls[0][2].endswith("001_clone_attempt_1.log")
    assert calls[1][:2] == (
        "git config --global --replace-all safe.directory /workspace/repo && git -C /workspace/repo rev-parse HEAD",
        "/workspace",
    )
    assert session.commit_sha == "abc123"
    assert session.status == "source_ready"
    assert "Repository cloned successfully" in message


def test_clone_repository_retries_with_container_side_cleanup(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-clone-retry", repo_url="https://example.com/repo.git")
    session.container_id = "container-123"
    calls: list[tuple[str, str | None, str | None]] = []
    clone_results = iter(
        [
            CommandResult(exit_code=124, stdout="", stderr="timed out", combined_output="timed out"),
            CommandResult(exit_code=0, stdout="", stderr="", combined_output=""),
        ]
    )

    def fake_exec(session_arg, command, workdir=None, timeout_seconds=600, log_path=None):
        del timeout_seconds
        assert session_arg is session
        calls.append((command, workdir, log_path))
        if "git clone" in command:
            return next(clone_results)
        return CommandResult(exit_code=0, stdout="def456\n", stderr="", combined_output="def456\n")

    services = CompileOperationsServices(manager=manager, runtime=SimpleNamespace(exec=fake_exec))
    monkeypatch.setattr(operations, "_services", services)

    result, message = clone_repository_impl(session=session, repo_url=session.repo_url, max_retries=2)

    clone_calls = [call for call in calls if "git clone" in call[0]]
    assert result.exit_code == 0
    assert len(clone_calls) == 2
    assert all(call[0].startswith("rm -rf -- /workspace/repo && git clone") for call in clone_calls)
    assert clone_calls[0][2].endswith("001_clone_attempt_1.log")
    assert clone_calls[1][2].endswith("001_clone_attempt_2.log")
    assert session.commit_sha == "def456"
    assert session.status == "source_ready"
    assert "Repository cloned successfully" in message
