#!/usr/bin/env python3
"""独立v2工程修复canary；读取拒绝可恢复，证据工作集有界保留。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "backend/packages/harness"), str(REPO_ROOT / "scripts")]

from forge_build_plan_agent_canary import run_arm  # noqa: E402
from forge_build_plan_agent_repair import audit_frozen  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.plan_agent import PlanTask  # noqa: E402
from deerflow.compile.plan_agent_context import ContextCanaryMeter, propose_with_context, run_tool_agent_with_context  # noqa: E402
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek  # noqa: E402
from deerflow.compile.plan_cross_system import SharedResearchBudget, before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402


def validate(protocol):
    if protocol["identity"] != "cpp-build-plan-agent-canary-v2" or protocol["max_estimated_cost_usd"] != 12 or protocol["deadline_utc"] != "2026-10-19T23:00:00Z":
        raise PlanContractError("阶段身份、预算或截止时间不符")
    before_deadline(protocol["deadline_utc"], 1800)
    parent = audit_frozen(Path(protocol["source_qualification_root"]))
    if parent["inventory_canonical_sha256"] != protocol["source_qualification_inventory_sha256"]:
        raise PlanContractError("参考任务资格身份变化")
    prior_root = Path(protocol["prior_canary_root"])
    if audit(prior_root)["inventory_canonical_sha256"] != protocol["prior_canary_inventory_sha256"]:
        raise PlanContractError("前序失败证据变化")
    prior = json.loads((prior_root / "protocol.json").read_text())
    if [item["task"] for item in protocol["projects"]] != [item["task"] for item in prior["projects"]] or protocol["schedule"] != prior["schedule"] or protocol["provider"] != prior["provider"]:
        raise PlanContractError("工程修复不得改变模型、固定任务或样本顺序")
    for name, expected in protocol["components"].items():
        path = (REPO_ROOT / name).resolve()
        if not path.is_relative_to(REPO_ROOT) or digest(path) != expected:
            raise PlanContractError("运行组件与协议不符")
    if len(protocol["schedule"]) != 8 or {(row["project"], row["arm"]) for row in protocol["schedule"]} != {(item["name"], arm) for item in protocol["projects"] for arm in ("plan", "tool")}:
        raise PlanContractError("固定双臂顺序不完整")
    for item in protocol["projects"]:
        task = PlanTask.model_validate(item["task"])
        if digest(Path(item["source_archive"])) != task.source_archive_sha256:
            raise PlanContractError("源码归档变化")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--shared-budget-root", type=Path, required=True)
    parser.add_argument("--qualify", action="store_true")
    parser.add_argument("--gate-root", type=Path, help="真实调用前必须核验同协议零Provider双臂Docker门禁")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    validate(protocol)
    shared = SharedResearchBudget(args.shared_budget_root)
    if shared.authorization["deadline_utc"] != protocol["deadline_utc"] or shared.authorization["max_new_provider_cost_usd"] != 20:
        raise PlanContractError("共享用户授权不匹配")
    if args.validate_only:
        print(json.dumps({"valid": True, "provider_calls": 0}))
        return 0
    if not args.qualify:
        if args.gate_root is None:
            raise PlanContractError("缺少已封存的零Provider门禁")
        audit(args.gate_root)
        gate = json.loads((args.gate_root / "result.json").read_text())
        if (
            digest(args.gate_root / "protocol.json") != digest(args.protocol)
            or gate["kind"] != "scripted_engineering_gate"
            or len(gate["arms"]) != 8
            or not all(r["strict_completed"] and r["agent_usage"]["recorded_tokens"] == 0 for r in gate["arms"])
        ):
            raise PlanContractError("双臂Docker门禁未通过或与当前协议不符")
    subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    (root / "authorization.json").write_bytes((args.shared_budget_root / "authorization.json").read_bytes())
    if not args.qualify:
        shared.append({"event": "stage.started", "identity": protocol["identity"], "reserved_cost_usd": "12", "protocol_sha256": digest(args.protocol), "evidence_root": str(root)})
    results = []
    try:
        model = None
        references = {}
        if args.qualify:
            references = {item["name"]: item["plan"] for item in json.loads((Path(protocol["source_qualification_root"]) / "protocol.json").read_text())["projects"]}
        else:
            key = os.environ.get("DEEPSEEK_API_KEY")
            if not key:
                raise PlanContractError("缺少已授权Provider凭据")
            model = PlanThinkingDeepSeek(model="deepseek-v4-pro", api_key=key, base_url="https://api.deepseek.com", max_tokens=32768, max_retries=0, timeout=240, reasoning_effort="low", extra_body={"thinking": {"type": "enabled"}})
        projects = {item["name"]: item for item in protocol["projects"]}
        for row in protocol["schedule"]:
            before_deadline(protocol["deadline_utc"], 1800)
            result = run_arm(
                item=projects[row["project"]],
                arm=row["arm"],
                protocol=protocol,
                root=root,
                model=model,
                reference=references.get(row["project"]),
                meter_factory=ContextCanaryMeter,
                planner=propose_with_context,
                tool_runner=run_tool_agent_with_context,
                probe_reads=args.qualify,
            )
            results.append(result)
            print(json.dumps({k: result.get(k) for k in ("name", "arm", "status", "strict_completed", "agent_usage")}, ensure_ascii=False), flush=True)
            if not result["cleanup"]["succeeded"] or result["agent_usage"]["unknown_usage_requests"]:
                break
    finally:
        known = sum((Decimal(str(r["agent_usage"]["estimated_cost_usd_completed_responses"])) for r in results), Decimal(0))
        unknown = sum(r["agent_usage"]["unknown_usage_requests"] for r in results)
        write_json(
            root / "result.json",
            {
                "identity": protocol["identity"],
                "kind": "scripted_engineering_gate" if args.qualify else "real_model_development_canary",
                "arms": results,
                "known_estimated_cost_usd": str(known),
                "unknown_usage_reservation_usd": str(Decimal("0.40") * unknown),
            },
        )
        sealed = seal(root, protocol, REPO_ROOT, unknown)
        if not args.qualify:
            shared.append(
                {
                    "event": "stage.completed",
                    "identity": protocol["identity"],
                    "charged_cost_usd": str(known + Decimal("0.40") * unknown),
                    "known_estimate_usd": str(known),
                    "unknown_reservation_usd": str(Decimal("0.40") * unknown),
                    "inventory_sha256": sealed["inventory_canonical_sha256"],
                }
            )
    return 0 if len(results) == 8 and all(r["strict_completed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
