#!/usr/bin/env python3
"""Forge checkpoint tar 的安全恢复与稳定树哈希。"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import shutil
import stat
import tarfile
import tempfile
from pathlib import Path
from typing import Any


class CheckpointRestoreError(RuntimeError):
    """Checkpoint 无法安全、完整地恢复。"""


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checkpoint_tree_entries(
    root: Path,
    *,
    ignored_file_names: frozenset[str] = frozenset(),
    ignored_directory_names: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not root.exists():
        return entries
    for path in sorted(
        root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
    ):
        relative = path.relative_to(root).as_posix()
        if relative == ".git" or relative.startswith(".git/"):
            continue
        relative_parts = Path(relative).parts
        if Path(relative).name in ignored_file_names or any(
            part in ignored_directory_names for part in relative_parts
        ):
            continue
        mode = stat.S_IMODE(path.lstat().st_mode) & 0o111
        if path.is_symlink():
            entries.append(
                {
                    "path": relative,
                    "kind": "symlink",
                    "mode": mode,
                    "target": os.readlink(path),
                }
            )
        elif path.is_file():
            entries.append(
                {
                    "path": relative,
                    "kind": "file",
                    "mode": mode,
                    "size": path.stat().st_size,
                    "sha256": _sha256_file(path),
                }
            )
    return entries


def checkpoint_tree_sha256(
    root: Path,
    *,
    ignored_file_names: frozenset[str] = frozenset(),
    ignored_directory_names: frozenset[str] = frozenset(),
) -> str:
    return _canonical_sha256(
        checkpoint_tree_entries(
            root,
            ignored_file_names=ignored_file_names,
            ignored_directory_names=ignored_directory_names,
        )
    )


def _symlink_aware_data_filter(
    member: tarfile.TarInfo, destination: str
) -> tarfile.TarInfo | None:
    if not member.issym():
        return tarfile.data_filter(member, destination)

    original_linkname = member.linkname
    if posixpath.isabs(original_linkname) or os.path.isabs(original_linkname):
        raise tarfile.AbsoluteLinkError(member)

    # Tar symlink 目标相对于链接所在目录；Python 3.10 data_filter 错按
    # 解包根目录解析。先改成 archive-root 相对路径完成标准安全校验，
    # 再恢复原始 linkname，保证落盘后的链接语义不变。
    member_name = member.name.lstrip("/" + os.sep)
    validation_target = posixpath.normpath(
        posixpath.join(posixpath.dirname(member_name), original_linkname)
    )
    validation_member = member.replace(
        linkname=validation_target,
        deep=False,
    )
    filtered = tarfile.data_filter(validation_member, destination)
    if filtered is None:
        return None
    return filtered.replace(linkname=original_linkname, deep=False)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_extracted_tree(root: Path) -> None:
    resolved_root = root.resolve(strict=True)
    for path in root.rglob("*"):
        if not path.is_symlink():
            continue
        linkname = os.readlink(path)
        if posixpath.isabs(linkname) or os.path.isabs(linkname):
            raise CheckpointRestoreError(
                f"解包结果包含绝对符号链接：{path.relative_to(root)} -> {linkname}"
            )
        try:
            target = (path.parent / linkname).resolve(strict=False)
        except RuntimeError as exc:
            raise CheckpointRestoreError(
                f"解包结果包含循环符号链接：{path.relative_to(root)}"
            ) from exc
        if not _is_within(target, resolved_root):
            raise CheckpointRestoreError(
                f"解包结果包含越界符号链接：{path.relative_to(root)} -> {linkname}"
            )


def restore_checkpoint_archive(
    source: Path,
    destination: Path,
    *,
    expected_tree_sha256: str | None = None,
) -> str:
    """安全恢复 checkpoint，并在完整验证后原子发布 destination。"""

    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"恢复目标已经存在：{destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.restore-",
            dir=destination.parent,
        )
    )
    published = False
    try:
        with tarfile.open(source, "r:*") as archive:
            archive.extractall(staging, filter=_symlink_aware_data_filter)
        _validate_extracted_tree(staging)
        observed_tree_sha256 = checkpoint_tree_sha256(staging)
        if (
            expected_tree_sha256 is not None
            and observed_tree_sha256 != expected_tree_sha256
        ):
            raise CheckpointRestoreError(
                "checkpoint tree hash 不匹配："
                f"expected={expected_tree_sha256}, observed={observed_tree_sha256}"
            )
        os.replace(staging, destination)
        published = True
        return observed_tree_sha256
    except (tarfile.TarError, OSError) as exc:
        raise CheckpointRestoreError(f"checkpoint 恢复失败：{exc}") from exc
    finally:
        if not published:
            shutil.rmtree(staging, ignore_errors=True)
