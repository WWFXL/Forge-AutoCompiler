#!/usr/bin/env python3
"""simdutf源码元数据独立资格：准备Git索引以实际执行上游文件检查。"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "backend/packages/harness"), str(REPO_ROOT / "scripts")]

from forge_build_reference_expansion import run_reference  # noqa: E402
from forge_build_reference_repair_qualification import execute_schedule  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.plan_cross_system import before_deadline  # noqa: E402


def prepared_project(original):
    item = copy.deepcopy(next(row for row in original["projects"] if row["name"] == "simdutf"))
    step = next(step for step in item["plan"]["steps"] if step["role"] == "dependency")
    if "git init" in step["command"] or "git add" in step["command"]:
        raise ValueError("父方案已有Git索引准备，不得重复追加")
    step["command"] += " && git init -q && git add --force --all"
    return item


def validate(protocol):
    if protocol["identity"] != "cpp-build-cxx-reference-metadata-qualification-v1" or protocol["provider_calls"] != 0 or protocol["credentials_read"] is not False:
        raise ValueError("独立元数据资格或零费用边界不符")
    before_deadline(protocol["deadline_utc"], protocol["new_project_reserve_seconds"])
    parent = Path(protocol["parent_evidence"])
    if audit(parent)["inventory_canonical_sha256"] != protocol["parent_inventory_sha256"]:
        raise ValueError("父证据变化")
    original = json.loads((parent / "protocol.json").read_text())
    if protocol["projects"] != [prepared_project(original)]:
        raise ValueError("超出唯一Git索引准备：禁止改测试、来源、交付或其他动作")
    for key in ("deadline_utc", "new_project_reserve_seconds", "plan_budget", "replay_timeout_seconds"):
        if protocol[key] != original[key]:
            raise ValueError("截止或资源边界变化")
    for item in protocol["projects"]:
        if digest(Path(item["source_archive"])) != item["plan"]["source_archive_sha256"] or digest(Path(item["source_file_hashes_path"])) != item["source_file_hashes_sha256"]:
            raise ValueError("来源图变化")
    for name, expected in protocol["components"].items():
        if digest(REPO_ROOT / name) != expected:
            raise ValueError("冻结组件变化")


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
    subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    rows, unobserved, reason = [], [{"name": "simdutf", "status": "not_observed_or_unclosed"}], "initialization_not_completed"
    try:
        rows, unobserved, reason = execute_schedule(protocol, root, executor=run_reference)
    finally:
        write_json(root / "result.json", {"identity": protocol["identity"], "provider_calls": 0, "projects": rows, "unobserved_schedule": unobserved, "stopping_reason": reason})
        print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
    return 0 if len(rows) == 1 and rows[0]["qualified"] and not unobserved else 1


if __name__ == "__main__":
    raise SystemExit(main())
