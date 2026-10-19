#!/usr/bin/env python3
"""两项Make完整自测参考资格；复用固定执行/清理合同，不调用模型。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "backend/packages/harness"), str(REPO_ROOT / "scripts")]

from forge_build_reference_expansion import execute_schedule  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.plan_cross_system import before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import BuildPlan  # noqa: E402


def validate(protocol):
    if protocol["identity"] != "cpp-build-make-reference-v1" or protocol["provider_calls"] != 0:
        raise ValueError("Make参考身份或零Provider边界错误")
    projects = protocol["projects"]
    if [item["name"] for item in projects] != ["libhydrogen", "buffer"]:
        raise ValueError("不得替换Make固定槽位")
    before_deadline(protocol["deadline_utc"], 3000)
    parent = audit(Path(protocol["catalog_root"]))
    if parent["inventory_canonical_sha256"] != protocol["catalog_inventory_sha256"]:
        raise ValueError("Make父来源变化")
    for path, expected in protocol["components"].items():
        if digest(REPO_ROOT / path) != expected:
            raise ValueError("Make参考组件变化")
    for item in projects:
        plan = BuildPlan.model_validate(item["plan"])
        if plan.build_system != "make" or digest(Path(item["source_archive"])) != plan.source_archive_sha256:
            raise ValueError("Make源码身份变化")
        if digest(Path(item["source_file_hashes_path"])) != item["source_file_hashes_sha256"]:
            raise ValueError("Make源码索引变化")


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
    rows = []
    try:
        rows = execute_schedule(protocol, root)
    finally:
        write_json(root / "result.json", {"identity": protocol["identity"], "provider_calls": 0, "projects": rows})
        print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
    return 0 if len(rows) == 2 and all(row["qualified"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
