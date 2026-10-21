#!/usr/bin/env python3
"""共同固定验证合同引用后的独立真实canary；完整扣除所有旧阶段。"""

from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import forge_build_rtorrent_canary_v3 as v3
from forge_build_rtorrent_fixed_contract import ContractMeter, run_strategy
from forge_typed_evidence import audit, digest

from deerflow.compile.plan_workflow import PlanContractError

previous = v3.previous
IDENTITY = "cpp-build-rtorrent-common-canary-v4"
RUNTIME, PROVIDER = v3.RUNTIME, v3.PROVIDER
PRIOR_IDENTITIES = (
    "cpp-build-rtorrent-common-canary-v2",
    "cpp-build-rtorrent-common-canary-v3",
)
PARENT_CANDIDATE_SHA = "04be79b1b0b59aadb1ed070a33b0788cd71ffebf3f9a009bb60df9c0fac54e0f"
original_execute = previous.execute


def validate(candidate):
    if candidate["identity"] != IDENTITY or candidate["parent_v3_candidate_sha256"] != PARENT_CANDIDATE_SHA:
        raise PlanContractError("固定合同真实canary身份或父候选变化")
    normalized = copy.deepcopy(candidate)
    normalized["identity"] = v3.IDENTITY
    v3.validate(normalized)
    gate = candidate["fixed_contract_gate"]
    root, receipt = Path(gate["root"]), Path(gate["independent_audit_path"])
    independent = json.loads(receipt.read_text())
    result, protocol = (json.loads((root / name).read_text()) for name in ("result.json", "protocol.json"))
    count = len(protocol["cases"])
    if audit(root)["inventory_canonical_sha256"] != gate["inventory_sha256"] or digest(receipt) != gate["independent_audit_sha256"]:
        raise PlanContractError("共同固定合同资格或审计来源变化")
    if not independent.get("valid") or independent["cases"] != count or independent["provider_calls"] != 0 or independent["inventory"]["inventory_canonical_sha256"] != gate["inventory_sha256"]:
        raise PlanContractError("独立合同资格未闭合")
    if protocol["identity"] != "cpp-build-rtorrent-fixed-contract-material-gate-v1" or not result["qualified"] or len(result["rows"]) != count or result["unobserved"] or result["error"]:
        raise PlanContractError("合同完整分母资格未通过")
    if any(candidate["components"].get(k) != v for k, v in protocol["components"].items()):
        raise PlanContractError("真实canary改变已资格合同组件")


def validate_authorization(candidate_sha, authorization):
    if authorization.get("experiment_identity") != IDENTITY or authorization.get("candidate_sha256") != candidate_sha:
        raise PlanContractError("新授权须绑定独立v4候选")
    # 先沿用原用户授权、v2原账本、SDK零重试与绝对截止检查。
    v3.validate_authorization(candidate_sha, {**authorization, "experiment_identity": v3.IDENTITY})
    stages = authorization.get("prior_paid_stages", [])
    if tuple(stage.get("identity") for stage in stages) != PRIOR_IDENTITIES:
        raise PlanContractError("必须完整计入v2和v3两个闭合阶段")
    charged_total = Decimal(0)
    for stage in stages:
        root, budget = Path(stage["root"]), Path(stage["budget_root"])
        ledger = budget / "budget-events.jsonl"
        events = [json.loads(line) for line in ledger.read_text().splitlines()]
        if digest(ledger) != stage["budget_events_sha256"] or len(events) != 2 or [e["event"] for e in events] != ["stage.started", "stage.completed"] or any(e["identity"] != stage["identity"] for e in events):
            raise PlanContractError("旧阶段身份、闭合或账本变化")
        sealed = audit(root)
        result = json.loads((root / "result.json").read_text())
        protocol = json.loads((root / "protocol.json").read_text())
        if sealed["inventory_canonical_sha256"] != stage["inventory_sha256"] or events[1]["inventory_sha256"] != stage["inventory_sha256"] or result["identity"] != stage["identity"]:
            raise PlanContractError("旧费用来源变化")
        if protocol["deadline_utc"] != authorization["deadline_utc"] or not result["lifecycle_complete"] or Decimal(result["unknown_usage_reservation_usd"]) != 0:
            raise PlanContractError("旧阶段时窗、生命周期或未知用量未闭合")
        charged = Decimal(result["known_estimated_cost_usd"])
        if charged != Decimal(events[1]["charged_cost_usd"]) or charged != Decimal(stage["charged_cost_usd"]):
            raise PlanContractError("旧阶段实际费用未完整计入")
        if stage["identity"] == PRIOR_IDENTITIES[0] and stage != {
            "identity": PRIOR_IDENTITIES[0],
            **authorization["prior_paid_stage"],
        }:
            raise PlanContractError("两处v2旧费绑定不一致")
        charged_total += charged
    if charged_total + Decimal(str(authorization["max_new_provider_cost_usd"])) > Decimal(10):
        raise PlanContractError("全部阶段累计超出原10美元")


def execute(protocol, root, model, *, results=None):
    return original_execute(protocol, root, model, executor=run_strategy, results=results)


def main():
    with (
        patch.object(previous, "IDENTITY", IDENTITY),
        patch.object(previous, "RUNTIME", RUNTIME),
        patch.object(previous, "validate", validate),
        patch.object(previous, "validate_authorization", validate_authorization),
        patch.object(previous, "CommonStrategyMeter", ContractMeter),
        patch.object(previous, "execute", execute),
    ):
        return previous.main()


if __name__ == "__main__":
    raise SystemExit(main())
