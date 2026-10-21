#!/usr/bin/env python3
"""共享JSON值修复后的独立真实canary；共享原10美元与绝对截止。"""

from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import forge_build_rtorrent_canary_v2 as v2
from forge_build_rtorrent_shared_values import SharedValueMeter
from forge_typed_evidence import audit, digest

from deerflow.compile.plan_workflow import PlanContractError

previous = v2.previous
IDENTITY = "cpp-build-rtorrent-common-canary-v3"
RUNTIME = v2.RUNTIME
PROVIDER = v2.PROVIDER
STAGE_CAP = Decimal("4.50")
PARENT_CANDIDATE_SHA = "480057ef52ec06743f2515e7acd855ec6d52954c1287ab1c8d1d02ba1a73e636"
USER_AUTH_SHA = "f6b5e6855c912b8a7127cd9813138546ce89719d00041d96046f00cffaed1b7b"
PRIOR_INVENTORY = "271bcecbd2d17abae1c5358beffcf43b54d223a62d228e20a5ca330599b0d2be"


def validate(candidate):
    if candidate["identity"] != IDENTITY or candidate["parent_real_candidate_sha256"] != PARENT_CANDIDATE_SHA or candidate["proposed_stage_max_cost_usd"] != 4.5:
        raise PlanContractError("新独立canary或父候选身份变化")
    normalized = copy.deepcopy(candidate)
    normalized["identity"] = v2.IDENTITY
    v2.validate(normalized)
    gate = candidate["multiturn_gate"]
    root = Path(gate["root"])
    receipt = Path(gate["independent_audit_path"])
    independent = json.loads(receipt.read_text())
    result = json.loads((root / "result.json").read_text())
    protocol = json.loads((root / "protocol.json").read_text())
    if audit(root)["inventory_canonical_sha256"] != gate["inventory_sha256"] or digest(receipt) != gate["independent_audit_sha256"]:
        raise PlanContractError("多轮材料资格或审计来源变化")
    if not independent.get("valid") or independent["cases"] != 30 or independent["provider_calls"] != 0 or independent["inventory"]["inventory_canonical_sha256"] != gate["inventory_sha256"]:
        raise PlanContractError("独立多轮材料资格未闭合")
    if not result["qualified"] or len(result["rows"]) != 30 or result["unobserved"] or result["error"]:
        raise PlanContractError("多轮材料完整30例未通过")
    if any(candidate["components"].get(k) != v for k, v in protocol["components"].items()):
        raise PlanContractError("真实canary改变已资格多轮材料组件")


def validate_authorization(candidate_sha, authorization):
    if authorization.get("experiment_identity") != IDENTITY or authorization.get("candidate_sha256") != candidate_sha:
        raise PlanContractError("新授权须绑定独立v3候选")
    maximum = Decimal(str(authorization["max_new_provider_cost_usd"]))
    if not maximum.is_finite() or not Decimal(0) < maximum <= STAGE_CAP:
        raise PlanContractError("本独立阶段最多预留4.50美元")
    binding = authorization["shared_user_authorization"]
    path = Path(binding["path"])
    if digest(path) != binding["sha256"] or binding["sha256"] != USER_AUTH_SHA:
        raise PlanContractError("原用户授权变化")
    user = json.loads(path.read_text())
    keys = ("authorized_at_utc", "deadline_utc", "max_total_model_requests", "automatic_retry", "user_authorized")
    if any(authorization.get(k) != user.get(k) for k in keys) or user.get("max_new_provider_cost_usd") != 10 or user.get("automatic_retry") is not False:
        raise PlanContractError("不能续期、重试或扩大原用户授权")
    prior = authorization["prior_paid_stage"]
    if prior["inventory_sha256"] != PRIOR_INVENTORY:
        raise PlanContractError("旧付费阶段须为已观察的v2冻结证据")
    root, budget = Path(prior["root"]), Path(prior["budget_root"])
    events = [json.loads(line) for line in (budget / "budget-events.jsonl").read_text().splitlines()]
    if digest(budget / "budget-events.jsonl") != prior["budget_events_sha256"] or len(events) != 2 or events[0]["event"] != "stage.started" or events[1]["event"] != "stage.completed":
        raise PlanContractError("旧付费阶段未闭合或账本变化")
    sealed = audit(root)
    if sealed["inventory_canonical_sha256"] != prior["inventory_sha256"] or events[1]["inventory_sha256"] != prior["inventory_sha256"]:
        raise PlanContractError("旧费用来源变化")
    result = json.loads((root / "result.json").read_text())
    charged = Decimal(result["known_estimated_cost_usd"]) + Decimal(result["unknown_usage_reservation_usd"])
    if events[0]["identity"] != v2.IDENTITY or events[1]["identity"] != v2.IDENTITY or charged != Decimal(events[1]["charged_cost_usd"]) or charged != Decimal(prior["charged_cost_usd"]):
        raise PlanContractError("旧实际用量未完整计入")
    if maximum + charged > Decimal(10) or not result["lifecycle_complete"] or Decimal(result["unknown_usage_reservation_usd"]) != 0:
        raise PlanContractError("总预算不足或旧阶段仍有未知用量")
    normalized = {**authorization, "experiment_identity": v2.IDENTITY}
    v2.validate_authorization(candidate_sha, normalized)


def main():
    with (
        patch.object(previous, "IDENTITY", IDENTITY),
        patch.object(previous, "RUNTIME", RUNTIME),
        patch.object(previous, "validate", validate),
        patch.object(previous, "validate_authorization", validate_authorization),
        patch.object(previous, "CommonStrategyMeter", SharedValueMeter),
    ):
        return previous.main()


if __name__ == "__main__":
    raise SystemExit(main())
