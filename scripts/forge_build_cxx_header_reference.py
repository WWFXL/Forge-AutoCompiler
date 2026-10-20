#!/usr/bin/env python3
"""libconfig供应header模板的独立资格：只延续AUTOHEADER配置，不改原验收。"""

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

IDENTITY = "cpp-build-cxx-cross-system-reference-header-v1"


def repaired_project(original):
    """仅configure继承已有AUTOHEADER=true；测试/源/交付逐字段保持。"""
    row = copy.deepcopy(next(p for p in original if p["name"] == "libconfig"))
    step = next(s for s in row["plan"]["steps"] if s["step_id"] == "configure")
    step["command"] = "AUTOHEADER=true " + step["command"]
    return row


def validate(protocol):
    if (
        protocol["identity"] != IDENTITY
        or protocol["provider_calls"] != 0
        or protocol["credentials_read"] is not False
    ):
        raise ValueError("独立身份或零Provider边界变化")
    if (
        protocol["deadline_utc"] != "2026-10-20T22:07:35Z"
        or protocol["new_project_reserve_seconds"] != 3300
    ):
        raise ValueError("原绝对窗口或清理预留变化")
    before_deadline(protocol["deadline_utc"], 3300)
    parent = Path(protocol["parent_evidence"])
    if (
        audit(parent)["inventory_canonical_sha256"]
        != protocol["parent_inventory_sha256"]
    ):
        raise ValueError("原失败证据变化")
    old = json.loads((parent / "protocol.json").read_text())
    if protocol["projects"] != [repaired_project(old["projects"])]:
        raise ValueError("超出唯一configure环境修订或改变测试/源码/交付")
    if any(protocol[k] != old[k] for k in ("plan_budget", "replay_timeout_seconds")):
        raise ValueError("原执行预算变化")
    for path, expected in protocol["components"].items():
        if digest(REPO_ROOT / path) != expected:
            raise ValueError("冻结组件变化")
    for item in protocol["projects"]:
        if (
            digest(Path(item["source_archive"]))
            != item["plan"]["source_archive_sha256"]
            or digest(Path(item["source_file_hashes_path"]))
            != item["source_file_hashes_sha256"]
        ):
            raise ValueError("原来源身份变化")


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
    rows, unseen, reason = (
        [],
        [{"name": "libconfig", "status": "not_observed_or_unclosed"}],
        "initialization_not_completed",
    )
    try:
        rows, unseen, reason = execute_schedule(protocol, root, executor=run_reference)
    finally:
        write_json(
            root / "result.json",
            {
                "identity": IDENTITY,
                "kind": "zero_provider_reference_qualification",
                "provider_calls": 0,
                "projects": rows,
                "unobserved_schedule": unseen,
                "stopping_reason": reason,
            },
        )
        print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
    return 0 if len(rows) == 1 and not unseen and rows[0]["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
