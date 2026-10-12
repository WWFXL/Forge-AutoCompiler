from __future__ import annotations

import importlib.util
import io
import os
import tarfile
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts/forge_checkpoint_archive.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("forge_checkpoint_archive", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def module() -> ModuleType:
    return _load_module()


def _archive(path: Path, members: list[tarfile.TarInfo | tuple[tarfile.TarInfo, bytes]]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for item in members:
            if isinstance(item, tuple):
                member, content = item
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
            else:
                archive.addfile(item)


def _file(name: str, content: bytes = b"payload") -> tuple[tarfile.TarInfo, bytes]:
    member = tarfile.TarInfo(name)
    member.mode = 0o644
    return member, content


def _link(name: str, target: str, *, hardlink: bool = False) -> tarfile.TarInfo:
    member = tarfile.TarInfo(name)
    member.type = tarfile.LNKTYPE if hardlink else tarfile.SYMTYPE
    member.linkname = target
    return member


def test_restores_parent_relative_symlink_without_changing_target(module: ModuleType, tmp_path: Path) -> None:
    source = tmp_path / "source.tar.gz"
    _archive(source, [_file("src/libestr.la"), _link("src/.libs/libestr.la", "../libestr.la")])
    destination = tmp_path / "restored"

    observed = module.restore_checkpoint_archive(source, destination)

    link = destination / "src/.libs/libestr.la"
    assert link.is_symlink()
    assert os.readlink(link) == "../libestr.la"
    assert link.read_bytes() == b"payload"
    assert observed == module.checkpoint_tree_sha256(destination)


@pytest.mark.parametrize(
    ("name", "target"),
    [
        ("src/.libs/escape", "../../../outside"),
        ("src/escape", "/etc/passwd"),
    ],
)
def test_rejects_escaping_or_absolute_symlink_without_publishing(module: ModuleType, tmp_path: Path, name: str, target: str) -> None:
    source = tmp_path / "source.tar.gz"
    _archive(source, [_link(name, target)])
    destination = tmp_path / "restored"

    with pytest.raises(module.CheckpointRestoreError):
        module.restore_checkpoint_archive(source, destination)

    assert not destination.exists()


def test_rejects_escaping_hardlink_without_publishing(module: ModuleType, tmp_path: Path) -> None:
    source = tmp_path / "source.tar.gz"
    _archive(source, [_link("src/hardlink", "../outside", hardlink=True)])
    destination = tmp_path / "restored"

    with pytest.raises(module.CheckpointRestoreError):
        module.restore_checkpoint_archive(source, destination)

    assert not destination.exists()


@pytest.mark.parametrize("member_type", [tarfile.CHRTYPE, tarfile.FIFOTYPE])
def test_rejects_special_files_without_publishing(module: ModuleType, tmp_path: Path, member_type: bytes) -> None:
    source = tmp_path / "source.tar.gz"
    member = tarfile.TarInfo("special")
    member.type = member_type
    if member_type == tarfile.CHRTYPE:
        member.devmajor = 1
        member.devminor = 3
    _archive(source, [member])
    destination = tmp_path / "restored"

    with pytest.raises(module.CheckpointRestoreError):
        module.restore_checkpoint_archive(source, destination)

    assert not destination.exists()


def test_rejects_file_written_through_escaping_symlink(module: ModuleType, tmp_path: Path) -> None:
    source = tmp_path / "source.tar.gz"
    _archive(
        source,
        [
            _link("redirect", "../outside"),
            _file("redirect/value"),
        ],
    )
    destination = tmp_path / "restored"

    with pytest.raises(module.CheckpointRestoreError):
        module.restore_checkpoint_archive(source, destination)

    assert not destination.exists()
    assert not (tmp_path / "outside/value").exists()


def test_hash_mismatch_removes_staging_and_does_not_publish(module: ModuleType, tmp_path: Path) -> None:
    source = tmp_path / "source.tar.gz"
    _archive(source, [_file("value")])
    destination = tmp_path / "restored"

    with pytest.raises(module.CheckpointRestoreError, match="tree hash"):
        module.restore_checkpoint_archive(source, destination, expected_tree_sha256="0" * 64)

    assert not destination.exists()
    assert not list(tmp_path.glob(".restored.restore-*"))


def test_refuses_existing_destination(module: ModuleType, tmp_path: Path) -> None:
    source = tmp_path / "source.tar.gz"
    _archive(source, [_file("value")])
    destination = tmp_path / "restored"
    destination.mkdir()

    with pytest.raises(FileExistsError):
        module.restore_checkpoint_archive(source, destination)
