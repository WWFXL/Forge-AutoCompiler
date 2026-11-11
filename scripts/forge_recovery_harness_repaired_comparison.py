#!/usr/bin/env python3
"""共同修复后，同一18项目的H0/R2独立比较；不改变已审核恢复指导。"""

from __future__ import annotations

import argparse
import copy
import importlib.metadata
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

import forge_recovery_harness_r2_comparison as previous
from forge_build_simple_task import save
from forge_typed_evidence import digest, seal

from deerflow.compile.operation_window import OperationWindow
from deerflow.compile.plan_workflow import PlanContractError, _digest
from deerflow.compile.recovery_harness import RecoveryHarness
from deerflow.compile.simple_build_task import SIMPLE_PROMPT, BuildReference, PublicBuildTask

base = previous.base
ROOT = previous.ROOT
IDENTITY = "cpp-build-recovery-harness-r2-repaired-comparison-flash-v1"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREG = ROOT / "benchmarks/preregistrations" / (IDENTITY + ".md")
REPAIR_CASES = ROOT / "benchmarks/fixtures/common-system-repair-v1/cases.json"
METHODS = previous.METHODS


def harnesses():
    """仅重新绑定共同底座哈希；已审核指导及来源指纹原样保留。"""
    originals = {
        "H0": base.shared.load(base.REVIEWED / "baseline.json"),
        "R2_system_context": base.shared.load(previous.REVIEWED / "candidate.json"),
    }
    if RecoveryHarness.model_validate(originals["R2_system_context"]).fingerprint() != previous.CANDIDATE_SHA:
        raise PlanContractError("已审核原R2发生变化")
    if originals["H0"]["recovery_guidance"]:
        raise PlanContractError("H0必须为空指导")
    result = {name: RecoveryHarness.model_validate(data | dict(base_prompt_sha256=_digest(SIMPLE_PROMPT))) for name, data in originals.items()}
    for harness in result.values():
        harness.prompt(SIMPLE_PROMPT)
    return result


def projects():
    rows = copy.deepcopy(base.shared.load(previous.MANIFEST)["projects"])
    reference = next(row["reference"] for row in base.shared.load(REPAIR_CASES)["cases"] if row["name"] == "masscan")
    next(row for row in rows if row["name"] == "masscan")["reference"] = reference
    for row in rows:
        row["exposure"] = "E54及共同修复后已开发暴露；相同项目再评价，非新样本或holdout"
    return rows


def candidate():
    value = copy.deepcopy(base.shared.load(previous.MANIFEST))
    paths = (ROOT / "scripts/forge_recovery_harness_repaired_comparison.py", previous.MANIFEST, previous.REVIEWED / "candidate.json", base.REVIEWED / "baseline.json", REPAIR_CASES, PREREG)
    value.update(
        identity=IDENTITY,
        issue=731,
        state="repaired_basis_comparison_prepared_requires_new_budget_and_window",
        projects=projects(),
        recovery_harnesses={name: h.model_dump(mode="json") for name, h in harnesses().items()},
        rebound_harness_sha256={name: h.fingerprint() for name, h in harnesses().items()},
        original_reviewed_candidate_sha256=previous.CANDIDATE_SHA,
        common_prompt_sha256=_digest(SIMPLE_PROMPT),
        previous_experiment_identity=previous.IDENTITY,
        repair_merge_revision="8d9811424c54b0f2c2e91ce64adee31300fd60c7",
        user_review="用户要求在新基座重新比较R2与H0；R2指导原文保持，只重绑定共同提示哈希；预算/时窗另确认",
        boundary="同一18个已暴露项目、36槽，每法每项目一次；重新共同H0规划，配对两组方案一致；只比较修复后恢复指导增量，不由跨批差值归因基座修复，不回填E54、不自动写论文。",
        components=base.shared.runtime_files() | {p.relative_to(ROOT).as_posix(): digest(p) for p in paths},
    )
    return value


def validate(value):
    if value["identity"] != IDENTITY or value["methods"] != list(METHODS) or value["schedule"] != previous.schedule() or value["projects"] != projects():
        raise PlanContractError("新身份、项目、参考或36槽排期变化")
    if value["recovery_harnesses"] != {n: h.model_dump(mode="json") for n, h in harnesses().items()} or value["original_reviewed_candidate_sha256"] != previous.CANDIDATE_SHA:
        raise PlanContractError("恢复指导或共同底座绑定变化")
    if value["common_prompt_sha256"] != _digest(SIMPLE_PROMPT):
        raise PlanContractError("共同提示变化")
    if Counter(p["task"]["build_system"] for p in value["projects"]) != Counter(cmake=6, make=6, autotools=6):
        raise PlanContractError("三系统覆盖变化")
    for row in value["projects"]:
        task = PublicBuildTask.model_validate(row["task"])
        reference = BuildReference.model_validate(row["reference"])
        if task.image_id != previous.IMAGE or reference.task_sha256 != _digest(task.model_dump(mode="json")) or digest(Path(row["source_archive"])) != task.source_archive_sha256:
            raise PlanContractError("源码、任务或参考不匹配：" + row["name"])
    for path, expected in value["components"].items():
        if digest(ROOT / path) != expected:
            raise PlanContractError("固定组件变化：" + path)
    for name, version in value["package_versions"].items():
        if importlib.metadata.version(name) != version:
            raise PlanContractError("运行依赖变化：" + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--check-prepared", action="store_true")
    modes.add_argument("--analyze", type=Path)
    modes.add_argument("--run", action="store_true")
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.analyze:
        print(json.dumps(previous.analyze(args.analyze), ensure_ascii=False, indent=2))
        return
    if args.prepare:
        if MANIFEST.exists():
            raise PlanContractError("不覆盖已固定身份")
        save(MANIFEST, candidate())
    value = base.shared.load(MANIFEST)
    validate(value)
    if not args.run:
        print(json.dumps(dict(valid=True, identity=IDENTITY, manifest_sha256=digest(MANIFEST), projects=18, slots=36, provider_calls=0, credentials_read=False)))
        return
    if not args.authorization or not args.output:
        parser.error("正式比较需要新授权及独立输出目录")
    if args.output.exists():
        raise PlanContractError("旧身份不续跑、不覆盖")
    auth = base.shared.load(args.authorization)
    base.shared.validate_authorization(auth, digest(MANIFEST), identity=IDENTITY, maximum_hours=4)
    if Decimal(auth["maximum_cost_usd"]) > Decimal(value["maximum_cost_usd"]):
        raise PlanContractError("本轮费用硬上限5美元")
    OperationWindow(auth["deadline_utc"]).admit("comparison", 900)
    callbacks = base.paid_callbacks(value, auth)
    try:
        base.execute(value, args.output, auth, *callbacks)
    finally:
        if (args.output / "result.json").exists():
            save(args.output / "analysis.json", previous.analyze(args.output))
            result = base.shared.load(args.output / "result.json")
            unknown = sum(base.shared.usage(r)["unknown"] for r in result["rows"] + result["common_initial_plans"]) + int(result["unclosed_unit"] is not None)
            seal(args.output, value, ROOT, unknown_usage_requests=unknown)


if __name__ == "__main__":
    main()
