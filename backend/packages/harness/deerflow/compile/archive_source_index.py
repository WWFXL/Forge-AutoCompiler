"""归档原文件与符号链接共同组成Git索引，不追随悬空链接。"""

from __future__ import annotations

import os
import posixpath
import tarfile
from pathlib import Path, PurePosixPath

from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.source_preparation import paths_fingerprint


def archive_index_contract(path):
    regular, links, seen = [], {}, set()
    with tarfile.open(path) as archive:
        for member in archive:
            if member.isdir():
                continue
            name = member.name.removeprefix("./")
            parts = PurePosixPath(name)
            if not name or parts.is_absolute() or ".." in parts.parts or name in seen:
                raise PlanContractError("归档源码索引含不安全路径或重复条目")
            seen.add(name)
            if member.isfile():
                regular.append(name)
            elif member.issym():
                target = member.linkname
                resolved = posixpath.normpath(posixpath.join(str(parts.parent), target))
                if target.startswith("/") or resolved == ".." or resolved.startswith("../"):
                    raise PlanContractError("原符号链接越出源码树")
                links[name] = target
            else:
                raise PlanContractError("源码索引不支持该归档条目类型")
    return dict(regular_paths=sorted(regular), symlinks=dict(sorted(links.items())), complete_index_sha256=paths_fingerprint(seen))


def complete_index_fingerprint(observed_hash_paths, contract):
    observed = set(observed_hash_paths)
    regular = set(contract["regular_paths"])
    complete = regular | set(contract["symlinks"])
    if not regular <= observed <= complete:
        raise PlanContractError("普通原文件集合与冻结归档不同")
    actual = paths_fingerprint(complete)
    if actual != contract["complete_index_sha256"]:
        raise PlanContractError("归档完整索引指纹变化")
    return actual


def observe_original_links(workspace, contract):
    observations = {}
    for name, expected in contract["symlinks"].items():
        path = Path(workspace) / name
        actual = os.readlink(path) if path.is_symlink() else None
        observations[name] = dict(expected_target=expected, actual_target=actual, passed=actual == expected)
    return observations
