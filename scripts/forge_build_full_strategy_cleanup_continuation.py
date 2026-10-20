#!/usr/bin/env python3
"""新身份执行原未观察槽；源码拒绝与物理清理分别记录，旧证据不回写。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from decimal import Decimal
from pathlib import Path

import forge_build_full_strategy_comparison as parent
import forge_build_full_strategy_runtime as runtime
from forge_build_plan_agent_canary import run_arm
from forge_typed_evidence import audit, digest, seal, write_json

from deerflow.compile.plan_cross_system import SharedResearchBudget, before_deadline
from deerflow.compile.plan_workflow import PlanContractError

IDENTITY = "cpp-build-full-strategy-cleanup-continuation-v1"
PARENT_PATH = "benchmarks/manifests/cpp-build-full-strategy-comparison-v1.json"
PARENT_SHA = "c40e2279eac72b02d80c9c744d8233fe6d0359b6c4bd7f624e4626d91fe818b7"
PARTIAL_ROOT = Path("/home/yiwei/.codex/outputs/forge-full-strategy-real-v1")
PARTIAL_INVENTORY = "f216c3930624768d6def984681af377d0ccb1e2427dd52a30b21c5d595692b72"
ADDED = {
    "scripts/forge_build_full_strategy_cleanup_continuation.py",
    "backend/tests/test_build_full_strategy_cleanup_continuation.py",
    "benchmarks/preregistrations/cpp-build-full-strategy-cleanup-continuation-v1.md",
}


def inspect_absent(reference):
    result = subprocess.run(["docker", "inspect", "--type", "container", reference], capture_output=True, text=True, timeout=15)
    return result.returncode == 1 and ("No such container" in result.stderr or "No such object" in result.stderr)


def cleanup_receipt(folder, row, inspect=inspect_absent):
    """只有原始源码拒绝、权威清理成功与实际不存在同时成立才分别分类。"""
    if row.get("strict_completed") or row.get("cleanup_error_class") != "PlanContractError" or row.get("error_message") != "原始源码或测试被修改":
        return None
    sessions = list(folder.glob(".compile-sessions/*/*/session.json"))
    if len(sessions) != 1:
        return None
    session = json.loads(sessions[0].read_text())
    sources = json.loads((folder / "original-source-hashes.json").read_text())
    workspace = Path(session["leadagent_repo_dir"])
    changed = [name for name, sha in sources.items() if not (workspace / name).is_file() or digest(workspace / name) != sha]
    events = [json.loads(line) for line in (sessions[0].parent / "logs/workflow.log").read_text().splitlines()]
    removed = [e for e in events if e["event"] == "container.cleanup.removed" and e.get("exit_code") == 0 and e.get("session_id") == session["session_id"] and e.get("container_id") == session["container_id"]]
    finalized = any(e["event"] == "finalize.completed" and e.get("session_id") == session["session_id"] for e in events)
    references = {session["container_id"], session["container_name"]}
    for attempt in session.get("replay_attempts", []):
        references.update(str(v) for k, v in attempt.items() if k in ("container_id", "container_name") and v)
    if not changed or not removed or not finalized or not all(inspect(ref) for ref in sorted(references)):
        return None
    return {"physical_cleanup_succeeded": True, "source_contract_rejected": True, "changed_original_paths": changed, "removed_event": removed[-1], "absent_container_references": sorted(references), "strict_completed": False}


def classified_arm(**kwargs):
    row = run_arm(**kwargs)
    folder = kwargs["root"] / (kwargs["item"]["name"] + "-" + kwargs["arm"])
    receipt = cleanup_receipt(folder, row)
    if receipt:
        write_json(folder / "physical-cleanup-classification.json", receipt)
        row = {**row, "legacy_cleanup": row["cleanup"], "cleanup": {"succeeded": True}, "cleanup_classification": "source_rejected_physical_cleanup_verified", "strict_completed": False}
    return row


def validate(protocol):
    original_path = runtime.REPO_ROOT / PARENT_PATH
    if digest(original_path) != PARENT_SHA:
        raise PlanContractError("父比较协议变化")
    original = json.loads(original_path.read_text())
    parent.validate(original)
    mutable = {"identity", "schedule", "max_estimated_cost_usd", "components", "continuation"}
    if protocol["identity"] != IDENTITY or protocol["schedule"] != [{**s, "original_slot": i} for i, s in enumerate(original["schedule"]) if i >= 16] or protocol["max_estimated_cost_usd"] != 10:
        raise PlanContractError("续段身份、固定剩余顺序或阶段预算不符")
    if {k: v for k, v in protocol.items() if k not in mutable} != {k: v for k, v in original.items() if k not in mutable}:
        raise PlanContractError("不得改变模型、任务、资源、裁判或授权截止")
    if set(protocol["components"]) != set(original["components"]) | ADDED or any(protocol["components"][k] != v for k, v in original["components"].items()):
        raise PlanContractError("旧冻结执行组件变化")
    if audit(PARTIAL_ROOT)["inventory_canonical_sha256"] != PARTIAL_INVENTORY:
        raise PlanContractError("原部分证据变化")
    previous = json.loads((PARTIAL_ROOT / "result.json").read_text())
    if len(previous["arms"]) != 16 or [{k: v for k, v in s.items() if k not in ("status", "reason")} for s in previous["unobserved_schedule"]] != original["schedule"][16:]:
        raise PlanContractError("原未观察分母不符")
    for name, sha in protocol["components"].items():
        if digest(runtime.REPO_ROOT / name) != sha:
            raise PlanContractError(f"冻结组件变化：{name}")
    return {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--shared-budget-root", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    validate(protocol)
    parent.require_gate(runtime.REPO_ROOT / PARENT_PATH, parent.GATE_ROOT)
    shared = SharedResearchBudget(args.shared_budget_root)
    if (
        args.shared_budget_root.resolve() != Path(protocol["authorization"]["root"]).resolve()
        or digest(args.shared_budget_root / "authorization.json") != protocol["authorization"]["sha256"]
        or shared.authorization["deadline_utc"] != protocol["deadline_utc"]
        or shared.authorization["max_new_provider_cost_usd"] != 20
    ):
        raise PlanContractError("共享授权、费用或原截止不符")
    if args.validate_only:
        print(json.dumps({"valid": True, "provider_calls": 0}))
        return 0
    gate_path = args.shared_budget_root / "cleanup-negative-independent.json"
    if digest(gate_path) != protocol["continuation"]["negative_audit_sha256"]:
        raise PlanContractError("负例独立核验收据变化")
    gate = json.loads(gate_path.read_text())
    if audit(Path(gate["root"]))["inventory_canonical_sha256"] != protocol["continuation"]["negative_inventory_sha256"]:
        raise PlanContractError("负例冻结证据变化")
    if not gate["valid"] or gate["provider_calls"] != 0:
        raise PlanContractError("物理cleanup负例独立核验未通过")
    before_deadline(protocol["deadline_utc"], runtime.RESERVE)
    subprocess.run(["bash", str(runtime.REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    os.environ["COMPILE_DOCKER_CLEANUP_TIMEOUT_SECONDS"] = "120"
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    (root / "authorization.json").write_bytes((args.shared_budget_root / "authorization.json").read_bytes())
    write_json(root / "cleanup-negative-admission.json", gate)
    rows, unobserved, reason, complete = [], [], "initialization_not_completed", False
    shared.append({"event": "stage.started", "identity": IDENTITY, "reserved_cost_usd": "10", "protocol_sha256": digest(args.protocol), "evidence_root": str(root)})
    try:
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise PlanContractError("缺少已授权Provider凭据")
        model = runtime.PlanThinkingDeepSeek(model="deepseek-v4-pro", api_key=key, base_url="https://api.deepseek.com", max_tokens=32768, max_retries=0, timeout=240, reasoning_effort="low", extra_body={"thinking": {"type": "enabled"}})
        rows, unobserved, reason = runtime.execute(protocol, root, model, {}, qualify=False, executor=classified_arm, results=rows)
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
                "kind": "prospective_fixed_task_continuation",
                "arms": rows,
                "unobserved_schedule": unobserved,
                "stopping_reason": reason,
                "lifecycle_complete": complete,
                "known_estimated_cost_usd": str(known),
                "unknown_usage_reservation_usd": str(Decimal("0.40") * unknown),
            },
        )
        sealed = seal(root, protocol, runtime.REPO_ROOT, unknown)
        if complete:
            shared.append(
                {
                    "event": "stage.completed",
                    "identity": IDENTITY,
                    "charged_cost_usd": str(runtime.charged_cost(rows)),
                    "known_estimate_usd": str(known),
                    "unknown_reservation_usd": str(Decimal("0.40") * unknown),
                    "inventory_sha256": sealed["inventory_canonical_sha256"],
                }
            )
    return 0 if not unobserved else 1


if __name__ == "__main__":
    raise SystemExit(main())
