#!/usr/bin/env python3
"""同一装配恢复契约的前瞻比较；新明确授权及完整独立门禁先于凭据。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from decimal import Decimal
from pathlib import Path

from forge_build_unified_plan import METHODS, REPO_ROOT, slot_runner, validate_authorization
from forge_typed_evidence import audit, digest, seal, write_json

from deerflow.compile.plan_agent import PlanTask
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek
from deerflow.compile.plan_cross_system import SharedResearchBudget, before_deadline
from deerflow.compile.plan_workflow import PlanContractError

IDENTITY = "cpp-build-unified-plan-comparison-v1"
PROJECTS = ("libpng", "libzip", "libtomcrypt", "libtommath", "libsodium", "check")


def schedule():
    """六个project/repetition块覆盖三方法全部六种顺序，下一重复反序。"""
    permutations = ((0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0))
    return [{"project": p, "repetition": r, "method": METHODS[m], "case": "natural_unmodified"} for r in (1, 2) for i, p in enumerate(PROJECTS) for m in (permutations[i] if r == 1 else tuple(reversed(permutations[i])))]


def validate(candidate):
    if candidate["identity"] != IDENTITY or candidate["schedule"] != schedule() or candidate["provider_authorization"] is not None or candidate["deadline_utc"] is not None:
        raise PlanContractError("候选身份、完整顺序或未授权状态不符")
    if tuple(p["name"] for p in candidate["projects"]) != PROJECTS:
        raise PlanContractError("固定评估分母不符")
    for name, sha in candidate["components"].items():
        if digest(REPO_ROOT / name) != sha:
            raise PlanContractError("候选组件变化：" + name)
    roles = Path(candidate["role_evidence"]["root"])
    if audit(roles)["inventory_canonical_sha256"] != candidate["role_evidence"]["inventory_sha256"]:
        raise PlanContractError("项目角色证据变化")
    registered = {p["name"]: p for p in json.loads((roles / "result.json").read_text())["projects"]}
    for row in candidate["projects"]:
        if row != {k: registered[row["name"]][k] for k in ("name", "task", "source_archive", "source_paths")}:
            raise PlanContractError("原任务/测试/源码登记变化")
        if digest(Path(row["source_archive"])) != PlanTask.model_validate(row["task"]).source_archive_sha256:
            raise PlanContractError("归档变化")


def require_gate(candidate):
    bound = candidate["gate"]
    root = Path(bound["root"])
    if audit(root)["inventory_canonical_sha256"] != bound["inventory_sha256"]:
        raise PlanContractError("共享契约门禁证据变化")
    result = json.loads((root / "result.json").read_text())
    receipt = Path(bound["independent_audit_path"])
    if digest(receipt) != bound["independent_audit_sha256"]:
        raise PlanContractError("门禁独立审计收据变化")
    independent = json.loads(receipt.read_text())
    if not independent["valid"] or independent["inventory_sha256"] != bound["inventory_sha256"] or independent["strict_completed"] != 9:
        raise PlanContractError("独立审计未闭合")
    if len(result["arms"]) != 9 or result["not_observed"] or not all(r["gate_observation"]["expected_observation"] for r in result["arms"]):
        raise PlanContractError("共享契约九槽门禁未完整通过")
    strong = candidate["strong_dispatch_gate"]
    strong_root = Path(strong["root"])
    if audit(strong_root)["inventory_canonical_sha256"] != strong["inventory_sha256"]:
        raise PlanContractError("强工具新入口资格证据变化")
    strong_result = json.loads((strong_root / "result.json").read_text())
    if len(strong_result["arms"]) != 1 or strong_result["not_observed"] or not strong_result["arms"][0]["gate_observation"]["expected_observation"]:
        raise PlanContractError("强工具新入口资格未闭合")
    strong_receipt = Path(strong["independent_audit_path"])
    if digest(strong_receipt) != strong["independent_audit_sha256"]:
        raise PlanContractError("强工具入口独立审计收据变化")
    strong_audit = json.loads(strong_receipt.read_text())
    if not strong_audit["valid"] or strong_audit["inventory_sha256"] != strong["inventory_sha256"] or strong_audit["strict_completed"] != 1:
        raise PlanContractError("强工具入口独立审计缺失")
    gate = json.loads((root / "protocol.json").read_text())
    if any(candidate["components"].get(k) != v for k, v in gate["components"].items()):
        raise PlanContractError("比较改变已通过门禁的组件")


def execute(protocol, root, model, *, executor=slot_runner, results=None):
    rows = [] if results is None else results
    projects = {p["name"]: p for p in protocol["projects"]}
    reason = None
    for i, slot in enumerate(protocol["schedule"]):
        try:
            before_deadline(protocol["deadline_utc"], 3900)
        except PlanContractError:
            reason = "deadline_reservation"
            break
        charged = sum((Decimal(str(r["agent_usage"]["estimated_cost_usd_completed_responses"])) + Decimal("0.40") * r["agent_usage"]["unknown_usage_requests"] for r in rows), Decimal(0))
        if charged + Decimal("1.50") > Decimal(str(protocol["max_new_provider_cost_usd"])):
            reason = "stage_cost_reservation"
            break
        item = {**projects[slot["project"]], "name": f"{i:02d}-{slot['project']}-r{slot['repetition']}-{slot['method']}"}
        # 正式入口不加载任何参考配方；source_paths仅原源码材料。
        row = executor(protocol=protocol, root=root, slot=slot, item=item, model=model, reference=None, qualify=False)
        rows.append(row)
        print(json.dumps({k: row.get(k) for k in ("name", "method", "strict_completed", "error_class", "error_message", "agent_usage")}, ensure_ascii=False), flush=True)
        if row.get("error_message") == "Provider 返回的模型标识不符合运行协议":
            reason = "provider_identity_mismatch"
            break
        if not row["cleanup"]["succeeded"] or row["agent_usage"]["unknown_usage_requests"]:
            reason = "cleanup_or_unknown_usage"
            break
    return rows, [{**s, "status": "not_observed", "reason": reason} for s in protocol["schedule"][len(rows) :]], reason


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--authorization-root", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    candidate = json.loads(args.candidate.read_text())
    validate(candidate)
    require_gate(candidate)
    if args.validate_only:
        print(json.dumps({"valid": True, "provider_calls": 0, "authorized": False, "slots": 36}))
        return 0
    if args.authorization_root is None or args.output_root is None:
        raise PlanContractError("正式运行必须提供新明确授权和新输出目录")
    shared = SharedResearchBudget(args.authorization_root)
    authorization = shared.authorization
    validate_authorization({"candidate_sha256": digest(args.candidate)}, authorization)
    protocol = {**candidate, "candidate_sha256": digest(args.candidate), "deadline_utc": authorization["deadline_utc"], "max_new_provider_cost_usd": authorization["max_new_provider_cost_usd"]}
    subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    os.environ["COMPILE_DOCKER_CLEANUP_TIMEOUT_SECONDS"] = "120"
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    write_json(root / "authorization.json", authorization)
    rows, unobserved, reason, complete = [], [], "initialization_not_completed", False
    shared.append({"event": "stage.started", "identity": IDENTITY, "reserved_cost_usd": str(protocol["max_new_provider_cost_usd"]), "candidate_sha256": digest(args.candidate), "evidence_root": str(root)})
    try:
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise PlanContractError("缺少已授权Provider凭据")
        model = PlanThinkingDeepSeek(model="deepseek-v4-pro", api_key=key, base_url="https://api.deepseek.com", max_tokens=32768, max_retries=0, timeout=240, reasoning_effort="low", extra_body={"thinking": {"type": "enabled"}})
        rows, unobserved, reason = execute(protocol, root, model, results=rows)
        complete = True
    finally:
        if len(rows) + len(unobserved) != len(protocol["schedule"]):
            unobserved = [{**s, "status": "not_observed_or_unclosed", "reason": reason} for s in protocol["schedule"][len(rows) :]]
        known = sum((Decimal(str(r["agent_usage"]["estimated_cost_usd_completed_responses"])) for r in rows), Decimal(0))
        unknown = sum(r["agent_usage"]["unknown_usage_requests"] for r in rows)
        write_json(
            root / "result.json",
            {
                "identity": IDENTITY,
                "kind": "prospective_shared_contract_comparison",
                "arms": rows,
                "not_observed": unobserved,
                "stop_reason": reason,
                "lifecycle_complete": complete,
                "known_estimated_cost_usd": str(known),
                "unknown_usage_reservation_usd": str(Decimal("0.40") * unknown),
            },
        )
        sealed = seal(root, protocol, REPO_ROOT, unknown)
        if complete:
            shared.append({"event": "stage.completed", "identity": IDENTITY, "charged_cost_usd": str(known + Decimal("0.40") * unknown), "inventory_sha256": sealed["inventory_canonical_sha256"]})
    return 0 if not unobserved else 1


if __name__ == "__main__":
    raise SystemExit(main())
