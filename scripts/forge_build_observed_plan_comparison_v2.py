#!/usr/bin/env python3
"""充值后独立重采；只增加身份与累计预算门禁，复用冻结策略执行。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from decimal import Decimal
from pathlib import Path

import forge_build_observed_plan_comparison as previous
from forge_build_observed_plan_comparison import (
    REPO_ROOT,
    PlanContractError,
    PlanThinkingDeepSeek,
    SharedResearchBudget,
    audit,
    digest,
    execute,
    require_gates,
    schedule,
    seal,
    write_json,
)

IDENTITY = "cpp-build-observed-plan-comparison-v2"
PARENT = "benchmarks/manifests/cpp-build-observed-plan-comparison-v1.json"
PARENT_SHA = "8a9310f8c89d657b29d9a1b7f56b967c17ba615a2717d2239fda139293bade2b"
PARENT_INVENTORY = "0a859d724b8e37e2c683e5531397cf0135fbd499a416ec12dbf7ce43e424e778"
DEADLINE = "2026-10-20T18:19:33Z"
PRIOR_RESERVED = Decimal("0.40")
MAXIMUM = Decimal("19.60")


def validate(candidate):
    parent_path = REPO_ROOT / PARENT
    if digest(parent_path) != PARENT_SHA:
        raise PlanContractError("原冻结候选变化")
    parent = json.loads(parent_path.read_text())
    if candidate["identity"] != IDENTITY or set(candidate) != set(parent) | {"restart"}:
        raise PlanContractError("必须独立v2身份及充值后暴露登记")
    for key, value in parent.items():
        if key not in ("identity", "components") and candidate.get(key) != value:
            raise PlanContractError("不得改变原实验方法、顺序、资源或裁判：" + key)
    if any(candidate["components"].get(k) != v for k, v in parent["components"].items()):
        raise PlanContractError("原120冻结组件变化")
    previous.validate({**candidate, "identity": previous.IDENTITY})
    restart = candidate["restart"]
    if (
        restart["parent_candidate_sha256"] != PARENT_SHA
        or restart["parent_inventory_sha256"] != PARENT_INVENTORY
        or restart["parent_unknown_reservation_usd"] != "0.40"
        or restart["aggregate_maximum_usd"] != "20.00"
        or restart["deadline_utc"] != DEADLINE
        or restart["user_continue_verified_utc"] != "2026-10-20T14:36:26Z"
    ):
        raise PlanContractError("旧未知用量、总预算或原截止不得重置")
    root = Path(restart["parent_evidence_root"])
    if audit(root)["inventory_canonical_sha256"] != PARENT_INVENTORY:
        raise PlanContractError("原402停止证据变化")
    result = json.loads((root / "result.json").read_text())
    if (
        result["identity"] != previous.IDENTITY
        or len(result["arms"]) != 1
        or len(result["not_observed"]) != 11
        or not result["lifecycle_complete"]
        or result["stop_reason"] != "cleanup_or_unknown_usage"
        or result["arms"][0]["agent_usage"]["unknown_usage_requests"] != 1
        or Decimal(result["known_estimated_cost_usd"]) != 0
        or Decimal(result["unknown_usage_reservation_usd"]) != PRIOR_RESERVED
    ):
        raise PlanContractError("原停止身份或预算占用不符")


def validate_authorization(candidate_sha, authorization):
    if (
        authorization.get("experiment_identity") != IDENTITY
        or authorization.get("deadline_utc") != DEADLINE
        or authorization.get("prior_reserved_cost_usd") != "0.40"
        or authorization.get("aggregate_maximum_usd") != "20.00"
        or authorization.get("user_continue_verified_utc") != "2026-10-20T14:36:26Z"
    ):
        raise PlanContractError("缺少充值后独立继续授权或原总预算时限")
    maximum = Decimal(str(authorization["max_new_provider_cost_usd"]))
    if not maximum.is_finite() or not Decimal(0) < maximum <= MAXIMUM:
        raise PlanContractError("保留旧0.40预留后本次最多19.60美元")
    previous.validate_authorization(candidate_sha, {**authorization, "experiment_identity": previous.IDENTITY})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--authorization-root", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    candidate = json.loads(args.candidate.read_text())
    validate(candidate)
    require_gates(candidate)
    if args.validate_only:
        print(json.dumps({"valid": True, "provider_calls": 0, "authorized": False, "slots": 12}))
        return 0
    if args.authorization_root is None or args.output_root is None:
        raise PlanContractError("真实运行需要新的明确授权和新目录")
    shared = SharedResearchBudget(args.authorization_root)
    authorization = shared.authorization
    validate_authorization(digest(args.candidate), authorization)
    protocol = {
        **candidate,
        "candidate_sha256": digest(args.candidate),
        "deadline_utc": authorization["deadline_utc"],
        "max_new_provider_cost_usd": authorization["max_new_provider_cost_usd"],
    }
    subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")],
        check=True,
        timeout=30,
    )
    os.environ["COMPILE_DOCKER_CLEANUP_TIMEOUT_SECONDS"] = "120"
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    write_json(root / "authorization.json", authorization)
    rows, unseen, reason, complete = [], [], "initialization_not_completed", False
    shared.append(
        {
            "event": "stage.started",
            "identity": IDENTITY,
            "reserved_cost_usd": str(protocol["max_new_provider_cost_usd"]),
            "candidate_sha256": digest(args.candidate),
            "evidence_root": str(root),
        }
    )
    try:
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise PlanContractError("缺少已授权Provider凭据")
        model = PlanThinkingDeepSeek(
            model="deepseek-v4-pro",
            api_key=key,
            base_url="https://api.deepseek.com",
            max_tokens=32768,
            max_retries=0,
            timeout=240,
            reasoning_effort="low",
            extra_body={"thinking": {"type": "enabled"}},
        )
        rows, unseen, reason = execute(protocol, root, model, results=rows)
        complete = True
    finally:
        if len(rows) + len(unseen) != 12:
            unseen = [{**s, "status": "not_observed_or_unclosed", "reason": reason} for s in schedule()[len(rows) :]]
        known = sum(
            (Decimal(str(r["agent_usage"]["estimated_cost_usd_completed_responses"])) for r in rows),
            Decimal(0),
        )
        unknown = sum(r["agent_usage"]["unknown_usage_requests"] for r in rows)
        write_json(
            root / "result.json",
            {
                "identity": IDENTITY,
                "kind": "prospective_observed_contract_comparison",
                "arms": rows,
                "not_observed": unseen,
                "stop_reason": reason,
                "lifecycle_complete": complete,
                "known_estimated_cost_usd": str(known),
                "unknown_usage_reservation_usd": str(Decimal("0.40") * unknown),
            },
        )
        sealed = seal(root, protocol, REPO_ROOT, unknown)
        if complete:
            shared.append(
                {
                    "event": "stage.completed",
                    "identity": IDENTITY,
                    "charged_cost_usd": str(known + Decimal("0.40") * unknown),
                    "inventory_sha256": sealed["inventory_canonical_sha256"],
                }
            )
    return 0 if not unseen else 1


if __name__ == "__main__":
    raise SystemExit(main())
