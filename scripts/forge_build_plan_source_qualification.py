#!/usr/bin/env python3
"""只执行预冻结参考方案的零Provider来源资格；不修复、不替换失败项目。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tarfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "backend/packages/harness"), str(REPO_ROOT / "scripts")]

from forge_build_plan_agent_repair import audit_frozen, seal_attempt  # noqa: E402

from deerflow.compile.plan_cross_system import before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import BuildPlan, PlanContractError  # noqa: E402


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(protocol):
    if protocol["identity"] != "cpp-build-plan-source-qualification-v2" or protocol["provider_calls"] != 0:
        raise PlanContractError("来源资格身份或零Provider边界不匹配")
    before_deadline(protocol["deadline_utc"], 1800)
    seal = audit_frozen(Path(protocol["catalog_root"]))
    if seal["inventory_canonical_sha256"] != protocol["catalog_inventory_sha256"]:
        raise PlanContractError("来源目录封存身份变化")
    for name, digest in protocol["components"].items():
        path = (REPO_ROOT / name).resolve()
        if not path.is_relative_to(REPO_ROOT) or sha(path) != digest:
            raise PlanContractError("资格运行组件变化")
    for item in protocol["projects"]:
        plan = BuildPlan.model_validate(item["plan"])
        if sha(Path(item["source_archive"])) != plan.source_archive_sha256:
            raise PlanContractError("资格源码归档变化")


def original_files(archive_path):
    """原始普通文件逐项哈希，符号链接身份另以原tar哈希约束。"""
    with tarfile.open(archive_path) as archive:
        return {item.name: hashlib.sha256(archive.extractfile(item).read()).hexdigest() for item in archive.getmembers() if item.isfile()}


def inspect_result(folder, frozen):
    result = json.loads((folder / "result.json").read_text())
    sessions = list(folder.glob(".compile-sessions/*/*/session.json"))
    if len(sessions) != 1:
        raise PlanContractError("资格必须恰好一个Session")
    session = json.loads(sessions[0].read_text())
    source = sessions[0].parent / "workspace/repo"
    unchanged = all((source / name).is_file() and sha(source / name) == digest for name, digest in frozen.items())
    qualified = result["status"] == "verified" and result["session_status"] == "completed" and result["cleanup"]["succeeded"] and unchanged
    return {
        "qualified": qualified,
        "status": result["status"],
        "session_status": result["session_status"],
        "cleanup": result["cleanup"],
        "fixed_source_files_unchanged": unchanged,
        "provider_calls": result["provider_calls"],
        "runtime_agent_calls": result["runtime_agent_calls"],
        "session_id": session["session_id"],
        "commands": [{key: row.get(key) for key in ("command_id", "command", "role", "exit_code", "timed_out", "duration_seconds", "log_path")} for row in session["commands"]],
        "replay_attempts": session.get("replay_attempts", []),
    }


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
    results = []
    try:
        for item in protocol["projects"]:
            before_deadline(protocol["deadline_utc"], 1800)
            plan_path = root / (item["name"] + "-plan.json")
            plan_path.write_text(json.dumps(item["plan"], ensure_ascii=False, indent=2) + "\n")
            frozen = original_files(item["source_archive"])
            (root / (item["name"] + "-source-hashes.json")).write_text(json.dumps(frozen, indent=2) + "\n")
            with (root / (item["name"] + "-console.log")).open("x") as log:
                completed = subprocess.run(
                    [sys.executable, str(REPO_ROOT / "scripts/forge_build_plan_prototype.py"), "--plan", str(plan_path), "--source-archive", item["source_archive"], "--output-root", str(root / item["name"]), "--verify"],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=1500,
                    check=False,
                )
            result = {"name": item["name"], "process_exit_code": completed.returncode, **inspect_result(root / item["name"], frozen)}
            results.append(result)
            print(json.dumps({key: result[key] for key in ("name", "qualified", "status", "session_status", "fixed_source_files_unchanged")}), flush=True)
            if not result["cleanup"]["succeeded"]:
                break
    finally:
        (root / "result.json").write_text(json.dumps({"identity": protocol["identity"], "kind": "zero_provider_reference_qualification", "provider_calls": 0, "projects": results}, ensure_ascii=False, indent=2) + "\n")

        class NoUsage:
            def summary(self):
                return {"unknown_usage_requests": 0}

        seal_attempt(root, protocol, NoUsage())
    return 0 if len(results) == len(protocol["projects"]) and all(result["qualified"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
