#!/usr/bin/env python3
"""保留首批结果，在共享原预算/截止内独立确认初始材料压缩后的规划对照。"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

import forge_planner_model_comparison as first
from forge_build_simple_task import save
from forge_typed_evidence import digest, seal

ROOT = first.ROOT
IDENTITY = "cpp-build-planner-model-confirmation-v2"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREG = ROOT / "benchmarks/preregistrations" / (IDENTITY + ".md")
PARENT_RAW = Path("/home/yiwei/.codex/outputs/forge-planner-model-comparison-v1")


def validate(value):
    first.validate(value | dict(identity=first.IDENTITY))
    if value["identity"] != IDENTITY or digest(PARENT_RAW / "result.json") != value["observed_parent"]["result_sha256"] or digest(PARENT_RAW / "seal.json") != value["observed_parent"]["seal_sha256"]:
        raise first.PlanContractError("独立确认身份或首批封存指针变化")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--run", action="store_true")
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.prepare:
        if MANIFEST.exists():
            raise first.PlanContractError("不覆盖独立确认身份")
        parent = first.shared.load(PARENT_RAW / "result.json")
        if parent["completed_slots"] != 16 or not parent["billing_complete"]:
            raise first.PlanContractError("首批未完整闭合，不启动新比较")
        value = first.candidate()
        value.update(identity=IDENTITY, observed_parent=dict(identity=first.IDENTITY, result_sha256=digest(PARENT_RAW / "result.json"), seal_sha256=digest(PARENT_RAW / "seal.json"), known_cost_usd=parent["closed_slot_cost_usd"]))
        value["planning"]["initial_material_compaction"] = "retain_paths_hashes_and_latest_complete_tool_interaction"
        value["components"].update({p.relative_to(ROOT).as_posix(): digest(p) for p in (Path(__file__).resolve(), PREREG)})
        value = json.loads(json.dumps(value))
        validate(value)
        save(MANIFEST, value)
        print(json.dumps(dict(identity=IDENTITY, candidate_sha256=digest(MANIFEST), slots=16, provider_calls=0)))
        return 0
    value = first.shared.load(MANIFEST)
    validate(value)
    if args.authorization is None or args.output is None:
        raise first.PlanContractError("新比较必须绑定本轮授权")
    auth = first.shared.load(args.authorization)
    first.shared.validate_authorization(auth, digest(MANIFEST), identity=IDENTITY, maximum_hours=2)
    parent_auth = first.shared.load(PARENT_RAW / "authorization.json")
    if auth["deadline_utc"] != parent_auth["deadline_utc"] or Decimal(auth["maximum_cost_usd"]) + Decimal(value["observed_parent"]["known_cost_usd"]) > Decimal(parent_auth["maximum_cost_usd"]):
        raise first.PlanContractError("不得重置原时窗或增加共享总预算")
    executor = first.paid_executor(value)
    try:
        first.shared.execute(value, args.output, auth, executor)
    finally:
        if (args.output / "result.json").exists():
            analysis = first.analyze(args.output)
            analysis["identity"] = IDENTITY
            save(args.output / "analysis.json", analysis)
            result = first.shared.load(args.output / "result.json")
            print(json.dumps(seal(args.output, value, ROOT, unknown_usage_requests=sum(first.shared.usage(r)["unknown"] for r in result["rows"]) + bool(result.get("unclosed_slot"))), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
