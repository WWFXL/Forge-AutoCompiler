import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow.compile import operations
from deerflow.compile.docker_runtime import DEFAULT_NETWORK, CompileDockerRuntime, ContainerCleanupResult, RuntimeConfig
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.operations import CompileOperationsServices, _classify_compiled_artifact, _write_repro_bundle, clone_repository_impl, submit_build_result_impl
from deerflow.compile.paths import get_compile_sessions_root, get_host_session_dir, get_host_workspace_dir, get_metadata_path, get_session_dir
from deerflow.compile.schemas import BuildArtifact, BuildCommandRecord, CommandResult, CompileSession, VerificationResult
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


def add_replayable_build_command(session: CompileSession, command: str = "cmake --build build") -> None:
    session.commands.append(
        BuildCommandRecord(
            stage="bash",
            command=command,
            workdir="/workspace/repo",
            exit_code=0,
        )
    )


def write_elf(path: Path, elf_type: int, *, has_interpreter: bool = False, has_entry_point: bool | None = None) -> None:
    header = bytearray(64)
    header[:4] = b"\x7fELF"
    header[4] = 2  # ELF64
    header[5] = 1  # little-endian
    header[6] = 1  # ELF version
    header[16:18] = elf_type.to_bytes(2, byteorder="little")
    header[18:20] = (62).to_bytes(2, byteorder="little")  # x86-64
    header[20:24] = (1).to_bytes(4, byteorder="little")
    header[52:54] = (64).to_bytes(2, byteorder="little")
    if elf_type == 1:
        header[40:48] = (64).to_bytes(8, byteorder="little")
        header[58:60] = (64).to_bytes(2, byteorder="little")
        header[60:62] = (3).to_bytes(2, byteorder="little")
        header[62:64] = (2).to_bytes(2, byteorder="little")
        null_section = bytearray(64)
        text_section = bytearray(64)
        text_section[4:8] = (1).to_bytes(4, byteorder="little")
        text_section[24:32] = (256).to_bytes(8, byteorder="little")
        text_section[32:40] = (1).to_bytes(8, byteorder="little")
        names = b"\0.text\0.shstrtab\0"
        name_section = bytearray(64)
        name_section[4:8] = (3).to_bytes(4, byteorder="little")
        name_section[24:32] = (257).to_bytes(8, byteorder="little")
        name_section[32:40] = len(names).to_bytes(8, byteorder="little")
        header.extend(null_section + text_section + name_section + b"\x90" + names)
    else:
        if has_entry_point is None:
            has_entry_point = elf_type == 2 or has_interpreter
        if has_entry_point:
            header[24:32] = (0x1000).to_bytes(8, byteorder="little")
        dynamic_payload = b"\0" * 16 if elf_type == 3 and not has_interpreter and not has_entry_point else b""
        interpreter_payload = b"/lib64/ld-linux-x86-64.so.2\0" if has_interpreter else b""
        program_count = 1 + int(bool(dynamic_payload or interpreter_payload))
        file_size = 64 + program_count * 56 + len(dynamic_payload) + len(interpreter_payload)
        header[32:40] = (64).to_bytes(8, byteorder="little")
        header[54:56] = (56).to_bytes(2, byteorder="little")
        header[56:58] = program_count.to_bytes(2, byteorder="little")
        load_header = bytearray(56)
        load_header[:4] = (1).to_bytes(4, byteorder="little")
        load_header[32:40] = file_size.to_bytes(8, byteorder="little")
        load_header[40:48] = file_size.to_bytes(8, byteorder="little")
        header.extend(load_header)
        if has_interpreter:
            interpreter_header = bytearray(56)
            interpreter_header[:4] = (3).to_bytes(4, byteorder="little")
            interpreter_header[8:16] = (64 + program_count * 56).to_bytes(8, byteorder="little")
            interpreter_header[32:40] = len(interpreter_payload).to_bytes(8, byteorder="little")
            interpreter_header[40:48] = len(interpreter_payload).to_bytes(8, byteorder="little")
            header.extend(interpreter_header)
        elif dynamic_payload:
            dynamic_header = bytearray(56)
            dynamic_header[:4] = (2).to_bytes(4, byteorder="little")
            dynamic_header[8:16] = (64 + program_count * 56).to_bytes(8, byteorder="little")
            dynamic_header[32:40] = len(dynamic_payload).to_bytes(8, byteorder="little")
            dynamic_header[40:48] = len(dynamic_payload).to_bytes(8, byteorder="little")
            header.extend(dynamic_header)
        header.extend(dynamic_payload + interpreter_payload)
    path.write_bytes(header)


def write_empty_elf(path: Path, elf_type: int) -> None:
    header = bytearray(64)
    header[:4] = b"\x7fELF"
    header[4:7] = bytes((2, 1, 1))
    header[16:18] = elf_type.to_bytes(2, byteorder="little")
    header[18:20] = (62).to_bytes(2, byteorder="little")
    header[20:24] = (1).to_bytes(4, byteorder="little")
    header[52:54] = (64).to_bytes(2, byteorder="little")
    if elf_type == 1:
        header[40:48] = (64).to_bytes(8, byteorder="little")
        header[58:60] = (64).to_bytes(2, byteorder="little")
        header[60:62] = (1).to_bytes(2, byteorder="little")
        header.extend(bytearray(64))
    else:
        header[24:32] = (0x1000).to_bytes(8, byteorder="little")
        header[32:40] = (64).to_bytes(8, byteorder="little")
        header[54:56] = (56).to_bytes(2, byteorder="little")
        header[56:58] = (1).to_bytes(2, byteorder="little")
        load_header = bytearray(56)
        load_header[:4] = (1).to_bytes(4, byteorder="little")
        header.extend(load_header)
    path.write_bytes(header)


def write_static_archive(path: Path) -> None:
    object_path = path.with_suffix(".member.o")
    write_elf(object_path, 1)
    payload = object_path.read_bytes()
    object_path.unlink()
    member_header = b"".join(
        [
            b"member.o/".ljust(16),
            b"0".ljust(12),
            b"0".ljust(6),
            b"0".ljust(6),
            b"100644".ljust(8),
            str(len(payload)).encode("ascii").ljust(10),
            b"`\n",
        ]
    )
    path.write_bytes(b"!<arch>\n" + member_header + payload + (b"\n" if len(payload) % 2 else b""))


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


def test_mark_status_clears_stale_error_and_preserves_completion_time(tmp_path: Path):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-status", repo_url="https://example.com/repo.git")
    manager.mark_session_status(session, "verification_failed", error="old failure")

    manager.mark_session_status(session, "verified")
    assert session.error is None
    assert session.completed_at is None

    manager.mark_session_status(session, "completed")
    completed_at = session.completed_at
    manager.mark_session_status(session, "completed")
    assert session.completed_at == completed_at


def test_finalize_is_idempotent_and_preserves_first_terminal_result(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-finalize", repo_url="https://example.com/repo.git")
    session.status = "verified"
    session.commit_sha = "a" * 40
    session.artifacts = [BuildArtifact(path="artifacts/hello", artifact_type="executable", size_bytes=128)]
    session.verification = VerificationResult(status="passed", artifact_count=1)
    add_replayable_build_command(session)
    manager.save_session(session)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=SimpleNamespace()))

    operations.finalize_compile_session_impl(session=session, status="completed")
    completed_at = session.completed_at
    finalized_at = session.finalized_at
    reloaded = manager.load_session(session.session_id, session.thread_id)
    operations.finalize_compile_session_impl(
        session=reloaded,
        status="failed",
        error="must not replace the first result",
    )

    assert reloaded.status == "completed"
    assert reloaded.error is None
    assert reloaded.completed_at == completed_at
    assert reloaded.finalized_at == finalized_at
    workflow_log = Path(session.leadagent_logs_dir) / "workflow.log"
    events = [json.loads(line) for line in workflow_log.read_text(encoding="utf-8").splitlines()]
    assert sum(event["event"] == "finalize.completed" for event in events) == 1
    assert sum(event["event"] == "session.status_changed" and event["status"] == "completed" for event in events) == 1


def test_finalize_failed_session_does_not_generate_repro_bundle(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-failed-finalize", repo_url="https://example.com/repo.git")
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=SimpleNamespace()))

    operations.finalize_compile_session_impl(session=session, status="failed", error="clone failed")

    assert session.status == "failed"
    assert not (Path(session.metadata_path).parent / "repro" / "build.sh").exists()


def test_concurrent_finalize_with_stale_copies_commits_one_terminal_result(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-concurrent-finalize", repo_url="https://example.com/repo.git")
    manager.save_session(session)
    first = manager.load_session(session.session_id, session.thread_id)
    second = manager.load_session(session.session_id, session.thread_id)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=SimpleNamespace()))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(operations.finalize_compile_session_impl, session=first, status="completed"),
            pool.submit(
                operations.finalize_compile_session_impl,
                session=second,
                status="failed",
                error="competing terminal result",
            ),
        ]
        results = [future.result() for future in futures]

    authoritative = manager.load_session(session.session_id, session.thread_id)
    assert {result.status for result in results} == {authoritative.status}
    workflow_log = Path(session.leadagent_logs_dir) / "workflow.log"
    events = [json.loads(line) for line in workflow_log.read_text(encoding="utf-8").splitlines()]
    assert sum(event["event"] == "finalize.completed" for event in events) == 1


def test_parent_run_cleanup_finalizes_unfinished_session_once(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-cancelled", repo_url="https://example.com/repo.git")
    session.status = "inspected"
    session.container_id = "container-123"
    manager.save_session(session)
    cleanup_calls: list[str] = []

    def cleanup(session_arg):
        cleanup_calls.append(session_arg.session_id)
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(
            manager=manager,
            runtime=SimpleNamespace(stop_and_remove_container=cleanup),
        ),
    )

    finalized = operations.finalize_unfinished_thread_sessions_impl(
        thread_id=session.thread_id,
        interrupted_status="cancelled",
        error="Parent run was cancelled.",
    )
    repeated = operations.finalize_unfinished_thread_sessions_impl(
        thread_id=session.thread_id,
        interrupted_status="cancelled",
        error="Parent run was cancelled.",
    )

    assert len(finalized) == 1
    assert repeated == []
    loaded = manager.load_session(session.session_id, session.thread_id)
    assert loaded.status == "cancelled"
    assert loaded.error == "Parent run was cancelled."
    assert loaded.completed_at is not None
    assert loaded.finalized_at is not None
    assert cleanup_calls == [session.session_id]
    workflow_log = Path(loaded.leadagent_logs_dir) / "workflow.log"
    events = [json.loads(line) for line in workflow_log.read_text(encoding="utf-8").splitlines()]
    assert sum(event["event"] == "finalize.completed" for event in events) == 1


def test_parent_run_cleanup_only_touches_sessions_owned_by_that_run(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    old_session = manager.create_session(
        thread_id="thread-overlap",
        run_id="run-old",
        repo_url="https://example.com/old.git",
    )
    new_session = manager.create_session(
        thread_id="thread-overlap",
        run_id="run-new",
        repo_url="https://example.com/new.git",
    )
    cleanup_calls: list[str] = []

    def cleanup(session_arg):
        cleanup_calls.append(session_arg.session_id)
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=SimpleNamespace(stop_and_remove_container=cleanup)),
    )

    finalized = operations.finalize_unfinished_thread_sessions_impl(
        thread_id=old_session.thread_id,
        run_id="run-old",
        interrupted_status="cancelled",
        error="Old run was replaced.",
    )

    assert [item.session_id for item in finalized] == [old_session.session_id]
    assert cleanup_calls == [old_session.session_id]
    assert manager.load_session(old_session.session_id, old_session.thread_id).finalized_at is not None
    loaded_new = manager.load_session(new_session.session_id, new_session.thread_id)
    assert loaded_new.status == "created"
    assert loaded_new.finalized_at is None


def test_cleanup_failure_remains_retryable_until_container_is_removed(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-cleanup-retry",
        run_id="run-cleanup-retry",
        repo_url="https://example.com/repo.git",
    )
    results = iter(
        [
            ContainerCleanupResult(succeeded=False, stopped=False, removed=False),
            ContainerCleanupResult(succeeded=True, stopped=True, removed=True),
        ]
    )
    cleanup_calls = 0

    def cleanup(_session):
        nonlocal cleanup_calls
        cleanup_calls += 1
        return next(results)

    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=SimpleNamespace(stop_and_remove_container=cleanup)),
    )

    operations.finalize_unfinished_thread_sessions_impl(
        thread_id=session.thread_id,
        run_id=session.run_id,
        interrupted_status="cancelled",
        error="Parent run was cancelled.",
    )
    after_failure = manager.load_session(session.session_id, session.thread_id)
    assert after_failure.status == "failed"
    assert after_failure.finalized_at is None

    operations.finalize_unfinished_thread_sessions_impl(
        thread_id=session.thread_id,
        run_id=session.run_id,
        interrupted_status="cancelled",
        error="Parent run was cancelled.",
    )
    after_retry = manager.load_session(session.session_id, session.thread_id)
    assert after_retry.status == "cancelled"
    assert after_retry.finalized_at is not None
    assert cleanup_calls == 2


def test_parent_cleanup_reloads_session_before_stopping_container(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-stale-cleanup",
        run_id="run-stale-cleanup",
        repo_url="https://example.com/repo.git",
    )
    stale_snapshot = manager.load_session(session.session_id, session.thread_id)
    session.container_id = "container-created-after-snapshot"
    manager.save_session(session)
    cleanup_container_ids: list[str | None] = []

    def cleanup(session_arg):
        cleanup_container_ids.append(session_arg.container_id)
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    monkeypatch.setattr(manager, "list_sessions", lambda _thread_id: [stale_snapshot])
    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=SimpleNamespace(stop_and_remove_container=cleanup)),
    )

    operations.finalize_unfinished_thread_sessions_impl(
        thread_id=session.thread_id,
        run_id=session.run_id,
        interrupted_status="cancelled",
        error="Parent run was cancelled.",
    )

    assert cleanup_container_ids == ["container-created-after-snapshot"]


def test_host_workspace_path_preserves_windows_style(tmp_path: Path):
    paths = make_test_paths(tmp_path, host_workspace_root=r"C:\Users\developer\Forge-AutoCompiler")
    manager = CompileSessionManager(paths=paths)
    session = manager.create_session(thread_id="windows-thread", repo_url="https://example.com/repo.git")

    assert get_host_workspace_dir(session.session_id, session.thread_id, paths) == (rf"C:\Users\developer\Forge-AutoCompiler\.compile-sessions\windows-thread\{session.session_id}\workspace")


def test_cleanup_reports_stopped_container_without_claiming_removal(monkeypatch):
    runtime = CompileDockerRuntime(config=RuntimeConfig(remove_on_cleanup=False))
    session = CompileSession(
        session_id="session-cleanup",
        thread_id="thread-cleanup",
        repo_url="https://example.com/repo.git",
        branch=None,
        image="autocompiler:gcc13",
        status="verified",
        container_id="container-123",
    )

    def fake_run(command, **kwargs):
        del kwargs
        assert command == ["docker", "stop", "container-123"]
        return SimpleNamespace(returncode=0, stdout="container-123\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runtime.stop_and_remove_container(session)

    assert result.succeeded is True
    assert result.stopped is True
    assert result.removed is False


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


def test_clone_repository_persists_effective_source_for_replay(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-clone-override",
        repo_url="https://example.com/old.git",
        branch="prepared-branch",
    )
    session.container_id = "container-123"
    actual_repo_url = "https://example.com/actual.git"
    commit_sha = "0123456789abcdef0123456789abcdef01234567"
    calls: list[str] = []

    def fake_exec(session_arg, command, **kwargs):
        del kwargs
        assert session_arg is session
        calls.append(command)
        if "git clone" in command:
            return CommandResult(exit_code=0, stdout="", stderr="", combined_output="")
        return CommandResult(exit_code=0, stdout=f"{commit_sha}\n", stderr="", combined_output=f"{commit_sha}\n")

    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=SimpleNamespace(exec=fake_exec)))

    result, _ = clone_repository_impl(session=session, repo_url=actual_repo_url)

    assert result.exit_code == 0
    assert calls[0] == "rm -rf -- /workspace/repo && git clone --depth 1 --branch prepared-branch https://example.com/actual.git /workspace/repo"
    assert session.repo_url == actual_repo_url
    assert session.branch == "prepared-branch"
    assert session.commit_sha == commit_sha
    reloaded = manager.load_session(session.session_id, session.thread_id)
    assert reloaded.repo_url == actual_repo_url
    assert reloaded.branch == "prepared-branch"


def test_compiled_artifact_classifier_uses_file_format_not_mode(tmp_path: Path):
    executable = tmp_path / "app"
    pie_executable = tmp_path / "pie-app"
    shared_library = tmp_path / "libapp.so"
    static_pie = tmp_path / "static-pie"
    object_file = tmp_path / "app.o"
    static_library = tmp_path / "libapp.a"
    text_log = tmp_path / "commands.log"

    write_elf(executable, 2)
    write_elf(pie_executable, 3, has_interpreter=True)
    write_elf(shared_library, 3)
    write_elf(static_pie, 3, has_entry_point=True)
    write_elf(object_file, 1)
    write_static_archive(static_library)
    text_log.write_text("echo this must never run\n", encoding="utf-8")
    text_log.chmod(0o777)

    assert _classify_compiled_artifact(executable) == "executable"
    assert _classify_compiled_artifact(pie_executable) == "executable"
    assert _classify_compiled_artifact(shared_library) == "shared_library"
    assert _classify_compiled_artifact(static_pie) == "executable"
    assert _classify_compiled_artifact(object_file) == "object"
    assert _classify_compiled_artifact(static_library) == "static_library"
    assert _classify_compiled_artifact(text_log) is None


def test_compiled_artifact_classifier_rejects_truncated_headers(tmp_path: Path):
    truncated_elf = tmp_path / "truncated.o"
    empty_archive = tmp_path / "empty.a"
    truncated_archive = tmp_path / "truncated.a"
    truncated_elf.write_bytes(b"\x7fELF" + bytes(60))
    empty_archive.write_bytes(b"!<arch>\n")
    truncated_archive.write_bytes(b"!<arch>\nmember.o/")

    assert _classify_compiled_artifact(truncated_elf) is None
    assert _classify_compiled_artifact(empty_archive) is None
    assert _classify_compiled_artifact(truncated_archive) is None


def test_compiled_artifact_classifier_rejects_empty_structural_shells(tmp_path: Path):
    executable = tmp_path / "empty-app"
    object_file = tmp_path / "empty.o"
    archive = tmp_path / "empty.a"
    write_empty_elf(executable, 2)
    write_empty_elf(object_file, 1)
    payload = object_file.read_bytes()
    member_header = b"".join(
        [
            b"empty.o/".ljust(16),
            b"0".ljust(12),
            b"0".ljust(6),
            b"0".ljust(6),
            b"100644".ljust(8),
            str(len(payload)).encode("ascii").ljust(10),
            b"`\n",
        ]
    )
    archive.write_bytes(b"!<arch>\n" + member_header + payload + (b"\n" if len(payload) % 2 else b""))

    assert _classify_compiled_artifact(executable) is None
    assert _classify_compiled_artifact(object_file) is None
    assert _classify_compiled_artifact(archive) is None


@pytest.mark.skipif(shutil.which("gcc") is None or shutil.which("ar") is None, reason="requires a C toolchain")
def test_compiled_artifact_classifier_accepts_real_gcc_and_ar_outputs(tmp_path: Path):
    source = tmp_path / "artifact.c"
    executable = tmp_path / "artifact"
    shared_library = tmp_path / "libartifact.so"
    object_file = tmp_path / "artifact.o"
    static_library = tmp_path / "libartifact.a"
    source.write_text("int value(void) { return 7; }\nint main(void) { return value(); }\n", encoding="utf-8")

    subprocess.run(["gcc", str(source), "-o", str(executable)], check=True, capture_output=True)
    subprocess.run(["gcc", "-shared", "-fPIC", str(source), "-o", str(shared_library)], check=True, capture_output=True)
    subprocess.run(["gcc", "-c", str(source), "-o", str(object_file)], check=True, capture_output=True)
    subprocess.run(["ar", "rcs", str(static_library), str(object_file)], check=True, capture_output=True)

    assert _classify_compiled_artifact(executable) == "executable"
    assert _classify_compiled_artifact(shared_library) == "shared_library"
    assert _classify_compiled_artifact(object_file) == "object"
    assert _classify_compiled_artifact(static_library) == "static_library"


@pytest.mark.skipif(shutil.which("gcc") is None, reason="requires gcc")
def test_compiled_artifact_classifier_recognizes_real_static_pie(tmp_path: Path):
    source = tmp_path / "static-pie.c"
    executable = tmp_path / "static-pie"
    source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
    result = subprocess.run(["gcc", "-static-pie", str(source), "-o", str(executable)], check=False, capture_output=True)
    if result.returncode != 0:
        pytest.skip("toolchain does not support static PIE")

    assert _classify_compiled_artifact(executable) == "executable"


def test_repro_bundle_pins_commit_and_renders_only_successful_bash_commands(tmp_path: Path):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-repro-contract",
        repo_url="https://example.com/O'Reilly/repo.git",
    )
    session.commit_sha = "0123456789abcdef0123456789abcdef01234567"
    session.commands = [
        BuildCommandRecord(
            stage="clone",
            command="rm -rf /workspace/repo && git clone https://moving.example/repo.git /workspace/repo",
            workdir="/workspace",
            exit_code=0,
        ),
        BuildCommandRecord(
            stage="bash",
            command="cmake -S . -B 'build dir'",
            workdir="/workspace/repo",
            exit_code=0,
        ),
        BuildCommandRecord(
            stage="bash",
            command="cmake --build broken",
            workdir="/workspace/repo",
            exit_code=1,
        ),
        BuildCommandRecord(
            stage="bash",
            command="cmake --build timed-out",
            workdir="/workspace/repo",
            exit_code=124,
        ),
        BuildCommandRecord(
            stage="bash",
            command="cmake --build unfinished",
            workdir="/workspace/repo",
            exit_code=None,
        ),
        BuildCommandRecord(
            stage="inspect",
            command="echo inspect-only",
            workdir="/workspace/repo",
            exit_code=0,
        ),
        BuildCommandRecord(
            stage="bash",
            command="cmake --build . && cp hello /artifacts/hello",
            workdir="/workspace/repo/build dir",
            exit_code=0,
        ),
        BuildCommandRecord(
            stage="bash",
            command="test -f hello",
            workdir="/artifacts",
            exit_code=0,
        ),
        BuildCommandRecord(
            stage="submit",
            command="submit build result from /artifacts",
            workdir=str(Path(session.metadata_path).parent),
            exit_code=0,
        ),
    ]

    build_path = _write_repro_bundle(session)
    script = build_path.read_text(encoding="utf-8")

    assert f"REPO_URL={operations.shell_quote(session.repo_url)}" in script
    assert f"COMMIT_SHA={session.commit_sha}" in script
    assert 'git fetch --depth 1 origin "$COMMIT_SHA"' in script
    assert 'test "$(git rev-parse HEAD)" = "$COMMIT_SHA"' in script
    assert 'find "$WORKSPACE_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +' in script
    assert 'find "$ARTIFACTS_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +' in script
    assert 'git init --quiet "$REPO_DIR"' in script
    assert 'git config --global --add safe.directory "$REPO_DIR"' in script
    assert f"bash -lc {operations.shell_quote("cmake -S . -B 'build dir'")}" in script
    assert "cd -- '/workspace/repo/build dir'" in script
    assert f"bash -lc {operations.shell_quote('cmake --build . && cp hello /artifacts/hello')}" in script
    assert "cd -- /artifacts" in script
    assert "bash -lc 'test -f hello'" in script
    assert "cmake --build broken" not in script
    assert "cmake --build timed-out" not in script
    assert "cmake --build unfinished" not in script
    assert "inspect-only" not in script
    assert "submit build result" not in script
    assert "moving.example" not in script
    assert session.session_id not in script
    assert ".compile-sessions" not in script
    subprocess.run(["bash", "-n", str(build_path)], check=True, capture_output=True)


@pytest.mark.parametrize(
    "workdir",
    [
        "relative/repo",
        "/workspace/../etc",
        "/workspace/.compile-sessions/thread/session/workspace/repo",
        r"C:\Users\YiWei\Forge\repo",
    ],
)
def test_repro_bundle_rejects_non_container_workdir(tmp_path: Path, workdir: str):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-repro-workdir", repo_url="https://example.com/repo.git")
    session.commit_sha = "a" * 40
    session.commands = [
        BuildCommandRecord(
            stage="bash",
            command="cmake --build .",
            workdir=workdir,
            exit_code=0,
        )
    ]

    with pytest.raises(ValueError, match="replay workdir"):
        _write_repro_bundle(session)


@pytest.mark.parametrize(
    "command",
    [
        "cp /workspace/.compile-sessions/thread/session/artifacts/hello /artifacts/hello",
        r"cp C:\Users\YiWei\Forge\hello /artifacts/hello",
        "printf x >/mnt/c/Users/YiWei/out",
        r"printf x >C:\Users\YiWei\out",
        "PATH=/tmp:/mnt/c/Windows cmake --build .",
    ],
)
def test_repro_bundle_rejects_host_path_in_command(tmp_path: Path, command: str):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-repro-command", repo_url="https://example.com/repo.git")
    session.commit_sha = "a" * 40
    session.commands = [
        BuildCommandRecord(
            stage="bash",
            command=command,
            workdir="/workspace/repo",
            exit_code=0,
        )
    ]

    with pytest.raises(ValueError, match="replay command"):
        _write_repro_bundle(session)


def test_repro_bundle_requires_commit_sha(tmp_path: Path):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-repro-commit", repo_url="https://example.com/repo.git")

    with pytest.raises(ValueError, match="commit_sha"):
        _write_repro_bundle(session)


def test_repro_bundle_rejects_empty_successful_recipe_and_removes_stale_script(tmp_path: Path):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-empty-repro", repo_url="https://example.com/repo.git")
    session.commit_sha = "a" * 40
    build_path = Path(session.metadata_path).parent / "repro" / "build.sh"
    build_path.parent.mkdir(parents=True, exist_ok=True)
    build_path.write_text("stale unsafe replay\n", encoding="utf-8")

    with pytest.raises(ValueError, match="successful bash command"):
        _write_repro_bundle(session)

    assert not build_path.exists()


@pytest.mark.parametrize(
    ("commit_sha", "expected_init"),
    [
        ("A" * 40, 'git init --quiet "$REPO_DIR"'),
        ("B" * 64, 'git init --object-format=sha256 --quiet "$REPO_DIR"'),
    ],
)
def test_repro_bundle_normalizes_commit_sha_and_selects_git_object_format(tmp_path: Path, commit_sha: str, expected_init: str):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-repro-object-format", repo_url="https://example.com/repo.git")
    session.commit_sha = commit_sha
    add_replayable_build_command(session)

    script = _write_repro_bundle(session).read_text(encoding="utf-8")

    assert f"COMMIT_SHA={commit_sha.lower()}" in script
    assert expected_init in script


@pytest.mark.parametrize(
    "commit_sha",
    [
        "main",
        "a" * 39,
        "a" * 40 + "; touch /tmp/pwned",
    ],
)
def test_repro_bundle_rejects_invalid_commit_sha(tmp_path: Path, commit_sha: str):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-invalid-commit", repo_url="https://example.com/repo.git")
    session.commit_sha = commit_sha

    with pytest.raises(ValueError, match="commit_sha"):
        _write_repro_bundle(session)


@pytest.mark.parametrize(
    "repo_url",
    [
        "https://token@example.com/private/repo.git",
        "https://example.com/private/repo.git?token=secret",
        "ssh://git@example.com/private/repo.git?token=secret",
        "git@example.com:private/repo.git?token=secret",
        "git@example.com:private/repo.git#main",
        "file:///tmp/repo",
        "/mnt/c/Users/YiWei/repo",
        r"C:\Users\YiWei\repo",
    ],
)
def test_repro_bundle_rejects_credentialed_or_local_repo_url(tmp_path: Path, repo_url: str):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-invalid-repo-url", repo_url=repo_url)
    session.commit_sha = "a" * 40

    with pytest.raises(ValueError, match="repo_url"):
        _write_repro_bundle(session)


def test_submit_rejects_artifact_when_repro_bundle_is_not_commit_pinned(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-unpinned-repro", repo_url="https://example.com/repo.git")
    write_elf(Path(session.leadagent_artifacts_dir) / "hello", 2)

    def fake_exec(*args, **kwargs):
        return CommandResult(exit_code=0, stdout="Hello Matt!\n", stderr="", combined_output="Hello Matt!\n")

    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=SimpleNamespace(exec=fake_exec)))

    payload = json.loads(submit_build_result_impl(session=session))

    assert payload["status"] == "failed"
    assert "replay bundle" in payload["message"].lower()
    assert session.status == "verification_failed"
    assert session.verification is not None
    assert session.verification.failed_checks == 1
    assert any(check.name == "repro_bundle" and not check.passed for check in session.verification.checks)
    assert not (Path(session.metadata_path).parent / "repro" / "build.sh").exists()


def test_submit_rejects_executable_mode_text_without_running_it(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-text-artifact", repo_url="https://example.com/repo.git")
    text_log = Path(session.leadagent_artifacts_dir) / "commands.log"
    text_log.write_text("echo this must never run\n", encoding="utf-8")
    text_log.chmod(0o777)

    def fail_exec(*args, **kwargs):
        raise AssertionError("Text artifacts must not be executed")

    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=SimpleNamespace(exec=fail_exec)))

    payload = json.loads(submit_build_result_impl(session=session))

    assert payload["status"] == "failed"
    assert payload["artifact_count"] == 0
    assert "No recognized compiled artifacts" in payload["message"]
    assert session.status == "verification_failed"


def test_submit_rejects_symlinked_system_executable_without_running_it(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-symlink-artifact", repo_url="https://example.com/repo.git")
    symlink = Path(session.leadagent_artifacts_dir) / "fake-app"
    symlink.symlink_to("/bin/true")

    def fail_exec(*args, **kwargs):
        raise AssertionError("Symlinked artifacts must not be executed")

    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=SimpleNamespace(exec=fail_exec)))

    payload = json.loads(submit_build_result_impl(session=session))

    assert payload["status"] == "failed"
    assert payload["artifact_count"] == 0
    assert session.status == "verification_failed"


def test_submit_smokes_only_elf_executable_and_ignores_text(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-mixed-artifacts", repo_url="https://example.com/repo.git")
    session.commit_sha = "a" * 40
    add_replayable_build_command(session, "cmake --build build && cp build/hello /artifacts/hello")
    session.error = "stale verification failure"
    artifacts_dir = Path(session.leadagent_artifacts_dir)
    write_elf(artifacts_dir / "hello", 2)
    text_log = artifacts_dir / "verification.log"
    text_log.write_text("", encoding="utf-8")
    text_log.chmod(0o777)
    calls: list[str] = []

    def fake_exec(session_arg, command, **kwargs):
        assert session_arg is session
        calls.append(command)
        return CommandResult(exit_code=0, stdout="Hello Matt!\n", stderr="", combined_output="Hello Matt!\n")

    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=SimpleNamespace(exec=fake_exec)))

    payload = json.loads(submit_build_result_impl(session=session))

    assert payload["status"] == "passed"
    assert payload["artifact_count"] == 1
    assert payload["artifacts"][0]["artifact_type"] == "executable"
    assert calls == ["/artifacts/hello -version"]
    assert session.status == "verified"
    assert session.error is None
    assert session.completed_at is None
    assert all(command.stage != "submit" for command in session.commands)
    assert (Path(session.metadata_path).parent / "repro" / "build.sh").exists()


@pytest.mark.parametrize(
    ("filename", "file_type", "expected_type"),
    [
        ("libapp.so", "shared", "shared_library"),
        ("app.o", "object", "object"),
        ("libapp.a", "archive", "static_library"),
    ],
)
def test_submit_accepts_non_executable_compiled_outputs_without_smoke(tmp_path: Path, monkeypatch, filename: str, file_type: str, expected_type: str):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id=f"thread-{file_type}", repo_url="https://example.com/repo.git")
    session.commit_sha = "a" * 40
    add_replayable_build_command(session, f"cmake --build build && cp build/{filename} /artifacts/{filename}")
    artifact = Path(session.leadagent_artifacts_dir) / filename
    if file_type == "shared":
        write_elf(artifact, 3)
    elif file_type == "object":
        write_elf(artifact, 1)
    else:
        write_static_archive(artifact)

    def fail_exec(*args, **kwargs):
        raise AssertionError("Non-executable compiled artifacts must not be smoke-tested")

    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=SimpleNamespace(exec=fail_exec)))

    payload = json.loads(submit_build_result_impl(session=session))

    assert payload["status"] == "passed"
    assert payload["artifacts"][0]["artifact_type"] == expected_type
    assert session.status == "verified"
