#!/usr/bin/env python3
"""固定Make/Autotools C++来源的完整参考资格；不调用Provider。"""

from __future__ import annotations

import argparse
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
from deerflow.compile.plan_workflow import BuildPlan  # noqa: E402

IDENTITY = "cpp-build-cxx-cross-system-reference-v1"
NAMES = ("tinyxml2", "libconfig")


def validate(protocol):
    if (
        protocol["identity"] != IDENTITY
        or protocol["provider_calls"] != 0
        or protocol["credentials_read"] is not False
    ):
        raise ValueError("参考身份或零Provider边界变化")
    if (
        protocol["deadline_utc"] != "2026-10-20T22:07:35Z"
        or protocol["new_project_reserve_seconds"] != 3300
    ):
        raise ValueError("绝对截止或清理预留变化")
    before_deadline(protocol["deadline_utc"], protocol["new_project_reserve_seconds"])
    if (
        protocol["plan_budget"]
        != {
            "max_commands": 32,
            "max_handoffs": 0,
            "wall_clock_seconds": 1800,
            "command_timeout_seconds": 900,
        }
        or protocol["replay_timeout_seconds"] != 1200
    ):
        raise ValueError("参考执行预算变化")
    parent = Path(protocol["parent_evidence"])
    if (
        audit(parent)["inventory_canonical_sha256"]
        != protocol["parent_inventory_sha256"]
    ):
        raise ValueError("父来源证据变化")
    original = json.loads((parent / "result.json").read_text())["projects"]
    if (
        tuple(row["name"] for row in protocol["projects"]) != NAMES
        or tuple(row["name"] for row in original) != NAMES
    ):
        raise ValueError("固定候选不可删除、重排或替换")
    for item, source in zip(protocol["projects"], original, strict=True):
        plan = BuildPlan.model_validate(item["plan"])
        if not source["qualified"] or (
            plan.repository_url,
            plan.commit_sha,
            plan.build_system,
        ) != (
            "https://github.com/" + source["repository"],
            source["commit"],
            source["requested_build_system"],
        ):
            raise ValueError("参考来源与固定Git身份不符")
        if (
            item["source_archive"] != source["source_archive"]
            or plan.source_archive_sha256 != source["source_archive_sha256"]
            or digest(Path(item["source_archive"])) != plan.source_archive_sha256
        ):
            raise ValueError("参考归档变化")
        if (
            item["source_file_hashes_path"] != source["source_file_hashes_path"]
            or item["source_file_hashes_sha256"] != source["source_file_hashes_sha256"]
            or digest(Path(item["source_file_hashes_path"]))
            != item["source_file_hashes_sha256"]
        ):
            raise ValueError("原源码索引变化")
    for path, expected in protocol["components"].items():
        if digest(REPO_ROOT / path) != expected:
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
    subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")],
        check=True,
        timeout=30,
    )
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    rows, unobserved, reason = (
        [],
        [{"name": name, "status": "not_observed_or_unclosed"} for name in NAMES],
        "initialization_not_completed",
    )
    try:
        rows, unobserved, reason = execute_schedule(
            protocol, root, executor=run_reference
        )
    finally:
        write_json(
            root / "result.json",
            {
                "identity": IDENTITY,
                "kind": "zero_provider_reference_qualification",
                "provider_calls": 0,
                "projects": rows,
                "unobserved_schedule": unobserved,
                "stopping_reason": reason,
            },
        )
        print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
    return (
        0
        if len(rows) == 2 and not unobserved and all(row["qualified"] for row in rows)
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
