from pathlib import Path

from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.paths import get_compile_sessions_root, get_metadata_path, get_session_dir
from deerflow.compile.schemas import BuildArtifact, BuildCommandRecord, CompileSession
from deerflow.config.paths import Paths


def test_create_session_creates_expected_directory_layout(tmp_path: Path):
    manager = CompileSessionManager(paths=Paths(base_dir=tmp_path / ".deer-flow"))

    session = manager.create_session(thread_id="thread-1", repo_url="https://example.com/repo.git", branch="main")

    session_dir = get_session_dir(session.session_id, session.thread_id, manager.paths)
    assert session_dir.exists()
    assert (session_dir / "workspace").exists()
    assert (session_dir / "artifacts").exists()
    assert (session_dir / "logs").exists()
    assert (session_dir / "repro").exists()
    assert get_metadata_path(session.session_id, session.thread_id, manager.paths).exists()


def test_create_session_under_compile_sessions_root(tmp_path: Path):
    paths = Paths(base_dir=tmp_path / ".deer-flow")
    manager = CompileSessionManager(paths=paths)

    session = manager.create_session(thread_id="abc", repo_url="https://example.com/repo.git")

    compile_root = get_compile_sessions_root(paths)
    assert str(session.host_session_dir).startswith(str(compile_root))


def test_save_and_load_session_roundtrip(tmp_path: Path):
    manager = CompileSessionManager(paths=Paths(base_dir=tmp_path / ".deer-flow"))
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
    manager = CompileSessionManager(paths=Paths(base_dir=tmp_path / ".deer-flow"))
    session = manager.create_session(thread_id="thread-3", repo_url="https://example.com/repo.git")

    manager.mark_session_status(session, "completed", summary="ok")

    assert session.completed_at is not None
    assert session.summary == "ok"

