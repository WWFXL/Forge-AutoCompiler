#!/usr/bin/env python3
"""补验新调度入口到原强工具Agent的真实零Provider接线，不计效果样本。"""

import argparse
import json
import os
import subprocess
from pathlib import Path

from forge_build_unified_plan import REPO_ROOT, slot_runner, validate
from forge_typed_evidence import audit, digest, seal, write_json

from deerflow.compile.plan_workflow import PlanContractError

IDENTITY = "cpp-build-unified-strong-dispatch-gate-v1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-protocol", type=Path, required=True)
    parser.add_argument("--parent-gate-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    parent = json.loads(args.parent_protocol.read_text())
    references = validate(parent)
    parent_seal = audit(args.parent_gate_root)
    previous = json.loads((args.parent_gate_root / "result.json").read_text())
    if digest(args.parent_protocol) != digest(args.parent_gate_root / "protocol.json") or len(previous["arms"]) != 9 or previous["not_observed"] or not all(r["gate_observation"]["expected_observation"] for r in previous["arms"]):
        raise PlanContractError("共享契约完整门禁必须先通过")
    slot = {"project": "buffer", "method": "strong_tool_agent", "case": "normal", "repetition": 1}
    components = {**parent["components"], "scripts/forge_build_unified_strong_gate.py": digest(Path(__file__))}
    protocol = {**parent, "identity": IDENTITY, "schedule": [slot], "components": components, "parent_gate_inventory": parent_seal["inventory_canonical_sha256"]}
    subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    os.environ["COMPILE_DOCKER_CLEANUP_TIMEOUT_SECONDS"] = "120"
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    item = {**next(p for p in parent["projects"] if p["name"] == "buffer"), "name": "buffer-strong-dispatch"}
    rows = []
    try:
        row = slot_runner(protocol=protocol, root=root, slot=slot, item=item, reference=references["buffer"], qualify=True)
        rows.append(row)
    finally:
        write_json(root / "result.json", {"identity": IDENTITY, "kind": "scripted_strong_dispatch_qualification", "arms": rows, "not_observed": [] if rows else [slot]})
        print(json.dumps(seal(root, protocol, REPO_ROOT), ensure_ascii=False))
    return 0 if rows[0]["gate_observation"]["expected_observation"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
