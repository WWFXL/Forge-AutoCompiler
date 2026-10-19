#!/usr/bin/env python3
"""两项既有参考配方的独立修复资格；不回填旧实验，不调用模型。"""

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
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.plan_cross_system import before_deadline  # noqa: E402

NAMES = ["libpng", "libzip"]


def repaired_projects(original):
    """只改明确的配方命令；完整测试、源身份和精确交付全部沿用。"""
    by_name = {item["name"]: item for item in original}
    result = [copy.deepcopy(by_name[name]) for name in NAMES]
    for item in result:
        if item["name"] == "libpng":
            stage = next(step for step in item["plan"]["steps"] if step["role"] == "artifact_stage")
            stage["command"] = "cp build/libpng.a /artifacts/libpng.a"
        else:
            configure = next(step for step in item["plan"]["steps"] if step["role"] == "configure")
            configure["command"] += " -DBUILD_DOC=OFF"
    return result


def validate(protocol):
    if protocol["identity"] != "cpp-build-reference-repair-qualification-v1" or protocol["provider_calls"] != 0 or protocol["deadline_utc"] != "2026-10-19T22:45:00Z":
        raise ValueError("独立参考修复身份、零费用或截止错误")
    before_deadline(protocol["deadline_utc"], 1800)
    parent = Path(protocol["parent_evidence"])
    if audit(parent)["inventory_canonical_sha256"] != protocol["parent_inventory_sha256"]:
        raise ValueError("父参考证据变化")
    old = json.loads((parent / "protocol.json").read_text())
    if protocol["projects"] != repaired_projects(old["projects"]):
        raise ValueError("修复超出两项明确命令，或改变完整测试/交付/来源")
    expected_budget = {"max_commands": 32, "max_handoffs": 0, "wall_clock_seconds": 900, "command_timeout_seconds": 300}
    if protocol["plan_budget"] != expected_budget or protocol["replay_timeout_seconds"] != 600 or protocol["new_project_reserve_seconds"] != 1800:
        raise ValueError("执行与清理预留边界变化")
    for item in protocol["projects"]:
        if digest(Path(item["source_archive"])) != item["plan"]["source_archive_sha256"] or digest(Path(item["source_file_hashes_path"])) != item["source_file_hashes_sha256"]:
            raise ValueError("原源码归档或原始普通文件索引变化")
    for name, expected in protocol["components"].items():
        if digest(REPO_ROOT / name) != expected:
            raise ValueError("运行组件偏离冻结")


def execute_schedule(protocol, root, executor=run_reference):
    rows, reason = [], None
    for item in protocol["projects"]:
        try:
            before_deadline(protocol["deadline_utc"], protocol["new_project_reserve_seconds"])
        except ValueError:
            reason = "deadline_reservation"
            break
        try:
            row = executor(item, root / item["name"], protocol)
        except Exception as exc:
            row = {"name": item["name"], "status": "infrastructure_stopped", "error_class": type(exc).__name__, "qualified": False, "cleanup": {"succeeded": False}, "provider_calls": 0}
        rows.append(row)
        print(json.dumps({key: row.get(key) for key in ("name", "status", "qualified", "session_status")}), flush=True)
        if not row["cleanup"]["succeeded"]:
            reason = "cleanup_or_infrastructure_failure"
            break
    unobserved = [{"name": item["name"], "status": "not_observed", "reason": reason} for item in protocol["projects"][len(rows) :]]
    return rows, unobserved, reason


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
    rows, unobserved, reason = [], [{"name": name, "status": "not_observed_or_unclosed"} for name in NAMES], "initialization_not_completed"
    try:
        rows, unobserved, reason = execute_schedule(protocol, root)
    finally:
        write_json(root / "result.json", {"identity": protocol["identity"], "kind": "zero_provider_reference_qualification", "provider_calls": 0, "projects": rows, "unobserved_schedule": unobserved, "stopping_reason": reason})
        print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
    return 0 if len(rows) == 2 and not unobserved and all(row["qualified"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
