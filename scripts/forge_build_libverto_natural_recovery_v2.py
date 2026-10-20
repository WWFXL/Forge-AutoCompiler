"""新时窗同源恢复资格：显式使用诊断门禁 v2 与充足依赖资源。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "backend/packages/harness"), str(REPO_ROOT / "scripts")]
from forge_build_libverto_recovery_planner_v2 import planner_for  # noqa: E402
from forge_build_plan_agent_canary import run_arm  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.plan_agent_context import ContextCanaryMeter  # noqa: E402
from deerflow.compile.plan_cross_system import before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402

RUNTIME_LIMITS = {"node_timeout_seconds": 1200, "command_timeout_seconds": 600, "evaluator_timeout_seconds": 900, "replay_timeout_seconds": 900, "cleanup_timeout_seconds": 120}
ADMISSION_RESERVE_SECONDS = 3900


class NoProviderMeter(ContextCanaryMeter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tracker.limits = replace(self.tracker.limits, **RUNTIME_LIMITS)

    def _before_request(self):
        raise PlanContractError("自然恢复零模型资格禁止模型请求")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    if protocol["identity"] != "cpp-build-libverto-natural-recovery-v2" or protocol["provider_calls"] != 0:
        raise PlanContractError("身份或零模型边界不符")
    before_deadline(protocol["deadline_utc"], ADMISSION_RESERVE_SECONDS)
    if protocol["runtime"] != RUNTIME_LIMITS:
        raise PlanContractError("运行资源与冻结协议不符")
    parent = Path(protocol["parent_root"])
    if audit(parent)["inventory_canonical_sha256"] != protocol["parent_inventory_sha256"]:
        raise PlanContractError("父封存变化")
    prior = json.loads((parent / "protocol.json").read_text())
    if protocol["projects"] != [p for p in prior["projects"] if p["name"] == "libverto"]:
        raise PlanContractError("固定源/任务改变")
    if digest(parent / protocol["initial_plan_path"]) != protocol["initial_plan_sha256"]:
        raise PlanContractError("原始真实方案变化")
    initial = json.loads((parent / protocol["initial_plan_path"]).read_text())
    if initial != protocol["initial_plan"]:
        raise PlanContractError("初始方案不是原真实方案")
    for name, expected in protocol["components"].items():
        if digest(REPO_ROOT / name) != expected:
            raise PlanContractError("组件变化")
    subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    before_deadline(protocol["deadline_utc"], ADMISSION_RESERVE_SECONDS)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    rows = []
    try:
        row = run_arm(
            item=protocol["projects"][0],
            arm="plan",
            protocol=protocol,
            root=root,
            reference=initial,
            meter_factory=NoProviderMeter,
            planner=planner_for(initial),
            command_timeout_seconds=RUNTIME_LIMITS["command_timeout_seconds"],
            replay_timeout_seconds=RUNTIME_LIMITS["replay_timeout_seconds"],
        )
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    finally:
        write_json(root / "result.json", {"identity": protocol["identity"], "kind": "posthoc_natural_failure_qualification", "provider_calls": 0, "arms": rows, "known_estimated_cost_usd": "0"})
        print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
    return 0 if len(rows) == 1 and rows[0]["strict_completed"] and rows[0]["agent_usage"]["model_requests"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
