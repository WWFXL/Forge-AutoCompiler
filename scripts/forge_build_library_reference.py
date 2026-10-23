#!/usr/bin/env python3
"""新库任务的独立参考与完整重放；原作者文件保持不变。"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from forge_build_reference_expansion import run_reference
from forge_build_reference_repair_qualification import execute_schedule
from forge_build_source_expansion import require_time
from forge_typed_evidence import audit, digest, seal, write_json

from deerflow.compile.plan_agent import PlanTask
from deerflow.compile.plan_workflow import BuildPlan

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "cpp-build-library-reference-v1"


def validate(protocol):
    if protocol["identity"] != IDENTITY or protocol["provider_calls"] != 0:
        raise ValueError("参考身份或零模型边界变化")
    require_time(protocol["deadline_utc"])
    parent = Path(protocol["parent_raw"])
    if audit(parent)["inventory_canonical_sha256"] != protocol["parent_inventory_sha256"]:
        raise ValueError("完整输入父证据变化")
    originals = json.loads((parent / "result.json").read_text())["projects"]
    if [p["name"] for p in protocol["projects"]] != [p["name"] for p in originals]:
        raise ValueError("固定三项不能删除或替换")
    for item, original in zip(protocol["projects"], originals, strict=True):
        plan = BuildPlan.model_validate(item["plan"])
        task = PlanTask.model_validate(item["task"])
        if task.model_dump(exclude={"verification_steps"}) != plan.model_dump(exclude={"steps", "revision"}):
            raise ValueError("任务与参考构建身份不同")
        if tuple(s for s in plan.steps if s.role == "smoke") != task.verification_steps:
            raise ValueError("参考不得改变原作者测试裁判")
        if plan.commit_sha != original["commit_sha"] or plan.source_archive_sha256 != original["source_archive_sha256"]:
            raise ValueError("固定源码或依赖归档变化")
        if digest(Path(item["source_archive"])) != plan.source_archive_sha256 or digest(Path(item["source_file_hashes_path"])) != original["source_file_hashes_sha256"]:
            raise ValueError("原始源码文件变化")
    for name, expected in protocol["components"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("冻结组件变化：" + name)


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
    subprocess.run(["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    write_json(root / "release.json", {"revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()})
    rows, unseen, reason = [], [], "initialization_not_completed"
    try:
        rows, unseen, reason = execute_schedule(protocol, root, executor=run_reference)
    finally:
        write_json(root / "result.json", {"identity": IDENTITY, "provider_calls": 0, "projects": rows, "unobserved_schedule": unseen, "stop_reason": reason})
        print(json.dumps(seal(root, protocol, ROOT)), flush=True)
    return 0 if not unseen and len(rows) == 3 and all(r["qualified"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
