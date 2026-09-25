"""独立实验 evidence 的宿主 ownership 规范化。"""

from __future__ import annotations

import os
import stat
from pathlib import Path

_MAX_HOST_ID = 2**32 - 2


def configured_host_identity() -> tuple[int, int] | None:
    uid_value = os.getenv("FORGE_HOST_UID") or None
    gid_value = os.getenv("FORGE_HOST_GID") or None
    if uid_value is None and gid_value is None:
        return None
    if uid_value is None or gid_value is None:
        raise ValueError("FORGE_HOST_UID and FORGE_HOST_GID must be configured together")
    try:
        uid = int(uid_value)
        gid = int(gid_value)
    except ValueError as exc:
        raise ValueError("FORGE_HOST_UID and FORGE_HOST_GID must be non-negative integers") from exc
    if not (0 <= uid <= _MAX_HOST_ID and 0 <= gid <= _MAX_HOST_ID):
        raise ValueError(f"FORGE_HOST_UID and FORGE_HOST_GID must be between 0 and {_MAX_HOST_ID}")
    return uid, gid


def _change_owner(path: Path, uid: int, gid: int, *, follow_symlinks: bool) -> None:
    if follow_symlinks:
        os.chown(path, uid, gid)
    elif hasattr(os, "lchown"):
        os.lchown(path, uid, gid)
    else:
        os.chown(path, uid, gid, follow_symlinks=False)


def _normalize_path(path: Path, identity: tuple[int, int]) -> None:
    uid, gid = identity
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        _change_owner(path, uid, gid, follow_symlinks=False)
        return
    _change_owner(path, uid, gid, follow_symlinks=True)
    current_mode = stat.S_IMODE(metadata.st_mode)
    if stat.S_ISDIR(metadata.st_mode):
        path.chmod((current_mode | 0o700) & ~0o007)
    elif stat.S_ISREG(metadata.st_mode):
        path.chmod((current_mode | 0o600) & ~0o007)


def normalize_evidence_path(path: Path) -> bool:
    identity = configured_host_identity()
    if identity is None:
        return False
    if path.is_symlink() or path.absolute() != path.resolve(strict=True):
        raise ValueError("Evidence path must not contain a symbolic-link boundary")
    _normalize_path(path, identity)
    return True


def normalize_evidence_tree(root: Path) -> bool:
    identity = configured_host_identity()
    if identity is None:
        return False
    if root.is_symlink() or root.absolute() != root.resolve(strict=True):
        raise ValueError("Evidence root must not contain a symbolic-link boundary")
    metadata = root.lstat()
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("Evidence root must be a directory")

    def normalize_directory(directory: Path) -> None:
        with os.scandir(directory) as entries:
            children = [Path(entry.path) for entry in entries]
        for child in children:
            child_metadata = child.lstat()
            if stat.S_ISLNK(child_metadata.st_mode):
                _normalize_path(child, identity)
            elif stat.S_ISDIR(child_metadata.st_mode):
                normalize_directory(child)
            else:
                _normalize_path(child, identity)
        _normalize_path(directory, identity)

    normalize_directory(root)
    return True
