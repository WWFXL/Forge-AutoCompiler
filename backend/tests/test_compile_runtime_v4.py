from __future__ import annotations

import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow.compile import evidence_ownership, operations
from deerflow.compile import manager as manager_module
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.operations import CompileOperationsServices
from deerflow.config.paths import Paths
from deerflow.subagents.builtins.compiler_agent import COMPILER_AGENT_CONFIG


def _paths(tmp_path: Path) -> Paths:
    return Paths(
        base_dir=tmp_path / ".deer-flow",
        workspace_root=tmp_path / "workspace",
        host_workspace_root=str(tmp_path / "workspace"),
    )


@pytest.fixture(autouse=True)
def clear_host_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FORGE_HOST_UID", raising=False)
    monkeypatch.delenv("FORGE_HOST_GID", raising=False)


@pytest.mark.parametrize(
    ("uid", "gid"),
    [
        ("1010", None),
        (None, "1010"),
        ("not-a-number", "1010"),
        ("-1", "1010"),
        ("1010", str(2**32)),
    ],
)
def test_host_identity_requires_a_valid_uid_gid_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    uid: str | None,
    gid: str | None,
) -> None:
    if uid is not None:
        monkeypatch.setenv("FORGE_HOST_UID", uid)
    if gid is not None:
        monkeypatch.setenv("FORGE_HOST_GID", gid)

    with pytest.raises(ValueError, match="FORGE_HOST_UID.*FORGE_HOST_GID"):
        CompileSessionManager(paths=_paths(tmp_path))


def test_metadata_and_workflow_writes_apply_configured_host_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FORGE_HOST_UID", "1010")
    monkeypatch.setenv("FORGE_HOST_GID", "1011")
    ownership: list[tuple[Path, int, int, bool]] = []
    monkeypatch.setattr(
        manager_module,
        "_change_owner",
        lambda path, uid, gid, *, follow_symlinks: ownership.append((Path(path), uid, gid, follow_symlinks)),
    )
    manager = CompileSessionManager(paths=_paths(tmp_path))

    session = manager.create_session(
        thread_id="thread-owner",
        session_id="session-owner",
        repo_url="https://example.com/repo.git",
    )

    assert (Path(session.metadata_path), 1010, 1011, True) in ownership
    assert (manager.workflow_log_path(session), 1010, 1011, True) in ownership


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode and symlink semantics")
def test_evidence_tree_normalization_does_not_follow_symlinks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FORGE_HOST_UID", "1010")
    monkeypatch.setenv("FORGE_HOST_GID", "1011")
    ownership: list[tuple[Path, int, int, bool]] = []
    monkeypatch.setattr(
        evidence_ownership,
        "_change_owner",
        lambda path, uid, gid, *, follow_symlinks: ownership.append((Path(path), uid, gid, follow_symlinks)),
    )
    evidence_root = tmp_path / "evidence"
    evidence_file = evidence_root / "tasks" / "task-a" / "experiment.jsonl"
    evidence_file.parent.mkdir(parents=True)
    evidence_file.write_text("{}\n", encoding="utf-8")
    evidence_file.chmod(0o600)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    outside.chmod(0o644)
    link = evidence_root / "outside-link"
    link.symlink_to(outside)

    assert evidence_ownership.normalize_evidence_tree(evidence_root) is True

    assert stat.S_IMODE(evidence_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(outside.stat().st_mode) == 0o644
    assert (link, 1010, 1011, False) in ownership
    assert all(path != outside for path, *_rest in ownership)


def test_evidence_tree_normalization_rejects_symlink_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORGE_HOST_UID", "1010")
    monkeypatch.setenv("FORGE_HOST_GID", "1011")
    monkeypatch.setattr(evidence_ownership, "_change_owner", lambda *_args, **_kwargs: None)
    outside = tmp_path / "outside"
    outside.mkdir()
    evidence_root = tmp_path / "evidence"
    evidence_root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symbolic-link"):
        evidence_ownership.normalize_evidence_tree(evidence_root)


def test_evidence_path_normalization_rejects_symlink_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORGE_HOST_UID", "1010")
    monkeypatch.setenv("FORGE_HOST_GID", "1011")
    monkeypatch.setattr(evidence_ownership, "_change_owner", lambda *_args, **_kwargs: None)
    outside = tmp_path / "outside"
    outside.mkdir()
    evidence_file = outside / "experiment.jsonl"
    evidence_file.write_text("{}\n", encoding="utf-8")
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symbolic-link"):
        evidence_ownership.normalize_evidence_path(linked_parent / "experiment.jsonl")


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode and symlink semantics")
def test_terminal_tree_normalization_preserves_executables_and_does_not_follow_symlinks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FORGE_HOST_UID", "1010")
    monkeypatch.setenv("FORGE_HOST_GID", "1011")
    ownership: list[tuple[Path, int, int, bool]] = []
    monkeypatch.setattr(
        manager_module,
        "_change_owner",
        lambda path, uid, gid, *, follow_symlinks: ownership.append((Path(path), uid, gid, follow_symlinks)),
    )
    manager = CompileSessionManager(paths=_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-tree",
        session_id="session-tree",
        repo_url="https://example.com/repo.git",
    )
    artifacts = Path(session.leadagent_artifacts_dir)
    executable = artifacts / "bin" / "hello"
    executable.parent.mkdir(parents=True)
    executable.write_text("hello", encoding="utf-8")
    executable.chmod(0o777)
    support = artifacts / "include" / "hello.h"
    support.parent.mkdir(parents=True)
    support.write_text("header", encoding="utf-8")
    support.chmod(0o666)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    outside.chmod(0o644)
    link = artifacts / "outside-link"
    link.symlink_to(outside)
    ownership.clear()

    manager.normalize_session_tree(session)

    assert stat.S_IMODE(executable.stat().st_mode) == 0o770
    assert stat.S_IMODE(support.stat().st_mode) == 0o660
    assert stat.S_IMODE(outside.stat().st_mode) == 0o644
    assert (link, 1010, 1011, False) in ownership
    assert all(path != outside for path, *_rest in ownership)


def test_tree_normalization_rejects_a_session_outside_the_compile_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FORGE_HOST_UID", "1010")
    monkeypatch.setenv("FORGE_HOST_GID", "1011")
    monkeypatch.setattr(manager_module, "_change_owner", lambda *_args, **_kwargs: None)
    manager = CompileSessionManager(paths=_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-boundary",
        session_id="session-boundary",
        repo_url="https://example.com/repo.git",
    )
    session.metadata_path = str(tmp_path / "outside" / "session.json")

    with pytest.raises(ValueError, match="(?i)compile session root"):
        manager.normalize_session_tree(session)


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlink semantics")
def test_tree_normalization_rejects_a_symlink_session_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FORGE_HOST_UID", "1010")
    monkeypatch.setenv("FORGE_HOST_GID", "1011")
    monkeypatch.setattr(manager_module, "_change_owner", lambda *_args, **_kwargs: None)
    manager = CompileSessionManager(paths=_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-symlink-root",
        session_id="session-symlink-root",
        repo_url="https://example.com/repo.git",
    )
    session_dir = Path(session.metadata_path).parent
    outside = tmp_path / "outside-session"
    session_dir.rename(outside)
    session_dir.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symbolic-link"):
        manager.normalize_session_tree(session)


def test_finalization_reports_host_identity_normalization_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FORGE_HOST_UID", "1010")
    monkeypatch.setenv("FORGE_HOST_GID", "1011")
    monkeypatch.setattr(manager_module, "_change_owner", lambda *_args, **_kwargs: None)
    manager = CompileSessionManager(paths=_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-finalize-owner",
        session_id="session-finalize-owner",
        repo_url="https://example.com/repo.git",
    )
    monkeypatch.setattr(
        manager,
        "normalize_session_tree",
        lambda _session: (_ for _ in ()).throw(PermissionError("ownership denied")),
    )
    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=SimpleNamespace()),
    )

    updated = operations.finalize_compile_session_impl(
        session=session,
        status="completed",
    )

    assert updated.status == "failed"
    assert updated.finalized_at is not None
    assert updated.error == "Host session ownership normalization failed: ownership denied"


def test_compiler_prompt_prefers_install_then_one_safe_discovery_and_submit() -> None:
    prompt = COMPILER_AGENT_CONFIG.system_prompt

    assert "cmake --install" in prompt
    assert "--prefix /artifacts" in prompt
    assert "at most one" in prompt
    assert "`find`" in prompt
    assert "glob" in prompt
    assert "`submit_build_result` immediately" in prompt
    assert "candidate" in prompt and "clean replay" in prompt
    assert "国内高等院校" in prompt
    assert "中文" in prompt
