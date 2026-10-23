#!/usr/bin/env python3
"""仅纠正ELFIO注释内测试误计；以新身份完成独立参考与重放。"""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
from pathlib import Path

from forge_build_library_reference import ROOT
from forge_build_reference_expansion import run_reference
from forge_build_reference_repair_qualification import execute_schedule
from forge_typed_evidence import audit, digest, seal, write_json

from deerflow.compile.plan_cross_system import before_deadline

IDENTITY = "cpp-build-library-elfio-qualification-v1"


def corrected_item(old):
    """原源码、全部测试、构建及交付不变，只移除块注释误计的九个叶。"""
    item = copy.deepcopy(next(p for p in old["projects"] if p["name"] == "ELFIO"))
    for step in [*item["task"]["verification_steps"], *item["plan"]["steps"]]:
        if step["role"] == "smoke":
            step["command"] = re.sub(r"\b82\b", "73", step["command"])
            step["command"] = re.sub(r"\b83\b", "74", step["command"])
            step["command"] = step["command"].replace("82leaves 83ctest", "73leaves 74ctest")
            step["required_output"] = [s.replace("82leaves 83ctest", "73leaves 74ctest") for s in step["required_output"]]
    item["task_scope"] = item["task_scope"].replace("82叶/83CTest", "73叶/74CTest")
    return item


def validate(protocol):
    if protocol["identity"] != IDENTITY or protocol["provider_calls"] != 0:
        raise ValueError("独立修正身份或零模型边界变化")
    before_deadline(protocol["deadline_utc"], 3900)
    parent = Path(protocol["parent_raw"])
    if audit(parent)["inventory_canonical_sha256"] != protocol["parent_inventory_sha256"]:
        raise ValueError("旧失败证据变化")
    old = json.loads((parent / "protocol.json").read_text())
    if protocol["projects"] != [corrected_item(old)]:
        raise ValueError("超出注释误计修正范围")
    for key in ("plan_budget", "replay_timeout_seconds", "new_project_reserve_seconds", "deadline_utc"):
        if protocol[key] != old[key]:
            raise ValueError("原时间或资源变化")
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
        print(json.dumps(dict(valid=True, provider_calls=0)))
        return 0
    subprocess.run(["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    write_json(root / "release.json", dict(revision=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()))
    rows, unseen, reason = [], [], "initialization_not_completed"
    try:
        rows, unseen, reason = execute_schedule(protocol, root, executor=run_reference)
    finally:
        write_json(root / "result.json", dict(identity=IDENTITY, provider_calls=0, projects=rows, unobserved_schedule=unseen, stop_reason=reason))
        print(json.dumps(seal(root, protocol, ROOT)), flush=True)
    return 0 if len(rows) == 1 and rows[0]["qualified"] and not unseen else 1


if __name__ == "__main__":
    raise SystemExit(main())
