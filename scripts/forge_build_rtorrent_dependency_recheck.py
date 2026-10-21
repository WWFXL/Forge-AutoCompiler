#!/usr/bin/env python3
"""离线复核已封存依赖；正确识别Autoconf单层/双层引用，不重写v1。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path

from forge_build_task_contract_sources import LIMITS, verify_archive, verify_recursive_tree
from forge_typed_evidence import audit, digest, seal, write_json

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "cpp-build-rtorrent-dependency-recheck-v2"


def require_version(text, required):
    # 仅识别真实行首AC_INIT及平衡的M4引用；注释、其他项目和近似版本均拒绝。
    atom = r"(?:\[\[([^\[\]\n,]+)\]\]|\[([^\[\]\n,]+)\]|([^\[\]\s,()]+))"
    match = re.search(r"(?m)^[ \t]*AC_INIT[ \t]*\([ \t]*" + atom + r"[ \t]*,[ \t]*" + atom + r"[ \t]*(?:,|\))", text)
    if not match:
        raise ValueError("没有可核验的AC_INIT声明")
    project = next(value for value in match.groups()[:3] if value is not None).strip()
    version = next(value for value in match.groups()[3:] if value is not None).strip()
    if project != "libtorrent" or version != required:
        raise ValueError("不是所需精确项目及版本")
    return version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    if protocol["identity"] != IDENTITY or protocol["required_version"] != "0.16.25" or protocol["network_calls"] != 0:
        raise ValueError("复核身份不符")
    if datetime.now(UTC) >= datetime.fromisoformat(protocol["deadline_utc"]):
        raise ValueError("已过原免费截止")
    for path, expected in protocol["components"].items():
        if digest(ROOT / path) != expected:
            raise ValueError("冻结组件变化")
    parent = Path(protocol["parent_raw"])
    if audit(parent)["inventory_canonical_sha256"] != protocol["parent_inventory_sha256"]:
        raise ValueError("父证据变化")
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    write_json(root / "execution.json", {"release": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "network_calls": 0, "provider_calls": 0, "build_commands": 0})
    result = {"identity": IDENTITY, "source_qualified": False, "task_qualified": False, "build_result": "not_observed", "retry_parent": False, "network_calls": 0, "provider_calls": 0}
    try:
        identity = json.loads((parent / "frozen-identity.json").read_text())
        tree = json.loads((parent / "git-tree.json").read_text())
        verify_recursive_tree(tree, identity["root_tree_sha"])
        inspection, proof = verify_archive(parent / "source.tar.gz", tree, LIMITS)
        with tarfile.open(parent / "source.tar.gz") as archive:
            member = archive.getmember(inspection["archive_root"] + "/configure.ac")
            text = archive.extractfile(member).read().decode()
        version = require_version(text, protocol["required_version"])
        write_json(root / "file-index.json", proof.pop("file_index"))
        write_json(root / "archive-inspection.json", inspection)
        result.update(**identity, **proof, version=version, source_archive_sha256=digest(parent / "source.tar.gz"), source_qualified=not proof["gitlinks"], note="仅同版本依赖根来源资格；系统依赖、完整任务与真实构建未资格")
    except Exception as exc:
        result.update(error_class=type(exc).__name__, error=str(exc)[:500])
    finally:
        write_json(root / "result.json", result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        print(json.dumps(seal(root, protocol, ROOT)), flush=True)
    return 0 if result["source_qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
