#!/usr/bin/env python3
"""单独验证规则后再失败转Agent；不替代完整矩阵，不准入付费比较。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from forge_build_full_strategy_runtime import REPO_ROOT, execute, gate_schedule, validate
from forge_typed_evidence import digest, seal, write_json

IDENTITY = "cpp-build-full-strategy-fallback-gate-v1"


def qualify_protocol(parent, parent_path):
    """保留全部共同资源和组件，仅将工程资格限定为预定开发案例。"""
    extra = [
        "scripts/forge_build_full_strategy_fallback_gate.py",
        "backend/tests/test_build_full_strategy_fallback_gate.py",
        "benchmarks/preregistrations/cpp-build-full-strategy-fallback-gate-v1.md",
        str(parent_path.relative_to(REPO_ROOT)),
    ]
    return {
        **parent,
        "identity": IDENTITY,
        "parent_protocol_sha256": digest(parent_path),
        "provider_calls": 0,
        "full_comparison_admission_permitted": False,
        "gate_schedule": [gate_schedule()[-1]],
        "components": {**parent["components"], **{name: digest(REPO_ROOT / name) for name in extra}},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    parent_path = args.parent_protocol.resolve()
    parent = json.loads(parent_path.read_text())
    references = validate(parent)
    authorization = Path(parent["authorization"]["root"]) / "authorization.json"
    if digest(authorization) != parent["authorization"]["sha256"]:
        raise ValueError("独立资格授权哈希变化")
    subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    os.environ["COMPILE_DOCKER_CLEANUP_TIMEOUT_SECONDS"] = "120"
    protocol = qualify_protocol(parent, parent_path)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    (root / "authorization.json").write_bytes((Path(parent["authorization"]["root"]) / "authorization.json").read_bytes())
    rows, missing, reason = [], [], "initialization_not_completed"
    try:
        rows, missing, reason = execute(protocol, root, None, references, qualify=True, results=rows)
    finally:
        if not rows:
            missing = [{**protocol["gate_schedule"][0], "status": "not_observed_or_unclosed", "reason": reason}]
        write_json(
            root / "result.json",
            {
                "identity": IDENTITY,
                "kind": "scripted_engineering_gate",
                "full_comparison_admission_permitted": False,
                "arms": rows,
                "unobserved_schedule": missing,
                "stopping_reason": reason,
                "known_estimated_cost_usd": "0",
                "unknown_usage_reservation_usd": "0",
            },
        )
        seal(root, protocol, REPO_ROOT)
    return 0 if len(rows) == 1 and rows[0]["gate_observation"]["expected_observation"] and not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
