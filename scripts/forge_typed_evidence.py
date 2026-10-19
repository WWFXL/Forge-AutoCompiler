"""新实验专用类型化封存：记录链接文本，绝不解引用外部或失效链接。"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def inventory(root):
    rows = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if relative in ("inventory.json", "seal.json"):
                continue
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                target = os.readlink(path)
                raw = os.fsencode(target)
                rows.append({"path": relative, "type": "symlink", "target": target, "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
            elif stat.S_ISREG(mode):
                rows.append({"path": relative, "type": "file", "size": path.stat().st_size, "sha256": digest(path)})
            elif not stat.S_ISDIR(mode):
                raise ValueError("证据包含不支持的特殊文件")
    return sorted(rows, key=lambda row: row["path"])


def canonical(rows):
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write_json(path, payload):
    with path.open("x") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def audit(root):
    rows = json.loads((root / "inventory.json").read_text())
    sealed = json.loads((root / "seal.json").read_text())
    if sealed["format"] != "forge-typed-evidence-v1" or canonical(rows) != sealed["inventory_canonical_sha256"] or inventory(root) != rows:
        raise ValueError("类型化证据封存不匹配")
    return sealed


def seal(root, protocol, repo_root, unknown_usage_requests=0):
    if (root / "inventory.json").exists() or (root / "seal.json").exists():
        raise ValueError("证据已封存，不可覆盖")
    for name, expected in protocol["components"].items():
        source = (repo_root / name).resolve()
        if not source.is_relative_to(repo_root.resolve()) or digest(source) != expected:
            raise ValueError("运行组件与冻结协议不符")
        target = root / "source-snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(source.read_bytes())
    rows = inventory(root)
    write_json(root / "inventory.json", rows)
    write_json(
        root / "seal.json",
        {
            "format": "forge-typed-evidence-v1",
            "identity": protocol["identity"],
            "entries": len(rows),
            "files": sum(row["type"] == "file" for row in rows),
            "symlinks": sum(row["type"] == "symlink" for row in rows),
            "bytes": sum(row["size"] for row in rows),
            "inventory_canonical_sha256": canonical(rows),
            "unknown_usage_requests": unknown_usage_requests,
        },
    )
    return audit(root)
