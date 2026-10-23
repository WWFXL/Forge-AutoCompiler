#!/usr/bin/env python3
"""沿已冻结目录获取三个库的完整归档；不调用模型或执行上游源码。"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from forge_build_source_expansion import collect_all, require_time
from forge_typed_evidence import digest, seal, write_json

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "cpp-build-library-full-sources-v1"
RANKS = (8, 16, 18)


def validate(protocol):
    if protocol["identity"] != IDENTITY or protocol["provider_calls"] != 0:
        raise ValueError("来源身份或零模型边界变化")
    require_time(protocol["deadline_utc"])
    for name, expected in protocol["components"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("来源组件变化")
    parent = Path(protocol["parent_raw"])
    for name, expected in protocol["parent_files"].items():
        if digest(parent / name) != expected:
            raise ValueError("父目录身份变化")
    rows = json.loads((parent / "result.json").read_text())["rows"]
    selected = [row for row in rows if row["rank"] in RANKS]
    if protocol["candidates"] != selected or tuple(row["rank"] for row in selected) != RANKS:
        raise ValueError("候选不等于父目录固定排名和版本")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    validate(protocol)
    if args.validate_only:
        print(json.dumps({"valid": True, "provider_calls": 0}))
        return 0
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    write_json(root / "release.json", {"revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()})
    rows = []
    try:
        for item in protocol["candidates"]:
            folder = root / item["repository"].replace("/", "--")
            folder.mkdir()
            write_json(folder / "head.json", {"status": "head_frozen", "commit_sha": item["commit_sha"], "root_tree_sha": item["root_tree_sha"], "authority": "parent_catalog_fixed_commit"})
        rows = collect_all(protocol, root)
    finally:
        write_json(root / "result.json", {"identity": IDENTITY, "provider_calls": 0, "build_commands": 0, "projects": rows, "unobserved": [row for row in protocol["candidates"] if row["repository"] not in {p["repository"] for p in rows}]})
        print(json.dumps(seal(root, protocol, ROOT)), flush=True)
    return 0 if len(rows) == 3 and all(row["status"] == "source_collected_pending_review" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
