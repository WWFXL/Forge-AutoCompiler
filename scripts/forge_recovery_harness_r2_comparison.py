#!/usr/bin/env python3
"""已审核R2与H0的新项目恢复比较；复用共同规划、执行和计费实现。"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

import forge_recovery_harness_comparison as base
from forge_build_simple_task import save
from forge_typed_evidence import digest, seal

from deerflow.compile.operation_window import OperationWindow
from deerflow.compile.plan_workflow import PlanContractError, _digest
from deerflow.compile.recovery_harness import RecoveryHarness
from deerflow.compile.simple_build_task import SIMPLE_PROMPT, BuildReference, PublicBuildTask

ROOT = base.ROOT
IDENTITY = "cpp-build-recovery-harness-r2-comparison-flash-v1"
DIRECTORY = ROOT / "benchmarks/fixtures/recovery-harness-r2-comparison-v1"
SELECTION, DEFINITIONS, FIXTURE = (DIRECTORY / name for name in ("selection.json", "definitions-v2.json", "tasks-v2.json"))
REVIEWED = ROOT / "benchmarks/fixtures/recovery-harness-system-context-gpt61sol-v1"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREG = ROOT / "benchmarks/preregistrations" / (IDENTITY + ".md")
METHODS = ("H0", "R2_system_context")
CANDIDATE_SHA = "270becfd8fe2c0c89d0d7ab8c820893cdc6ae7cdd9d2c50e95ecb11f84263743"
IMAGE = "sha256:8123220a201ac4d00cda0dc985b9db7227cd909bb93ca6c25fd82cafce5cd887"
PROPOSAL_COST = "0.139614"


def project_order():
    rows = base.shared.load(SELECTION)["projects"]
    groups = [[p["name"] for p in rows if p["proposed_build_system"] == system] for system in ("cmake", "make", "autotools")]
    return [name for block in zip(*groups, strict=True) for name in block]


def schedule():
    rows = []
    for index, name in enumerate(project_order()):
        for method in METHODS[:: 1 if index % 2 == 0 else -1]:
            rows.append(dict(slot=len(rows) + 1, project=name, repetition=1, method=method))
    return rows


def harnesses():
    h0 = RecoveryHarness.model_validate(base.shared.load(base.REVIEWED / "baseline.json"))
    r2 = RecoveryHarness.model_validate(base.shared.load(REVIEWED / "candidate.json"))
    if h0.recovery_guidance or r2.fingerprint() != CANDIDATE_SHA:
        raise PlanContractError("恢复指导与用户审核的新候选不一致")
    for h in (h0, r2):
        h.prompt(SIMPLE_PROMPT)
    return dict(zip(METHODS, (h0, r2), strict=True))


def freeze_tasks(sources):
    """只从作者依据装配主任务；独立产物、验证与参考动作不送规划模型。"""
    if FIXTURE.exists():
        raise PlanContractError("不覆盖已固定的新项目任务")
    selected = base.shared.load(SELECTION)["projects"]
    collected = {r["name"]: r for r in base.shared.load(sources / "result.json")["projects"]}
    definitions = base.shared.load(DEFINITIONS)
    if set(definitions) != {p["name"] for p in selected}:
        raise PlanContractError("作者定义不能更换选定项目")
    projects = []
    for p in selected:
        row, definition = collected[p["name"]], definitions[p["name"]]
        if row["status"] != "collected" or digest(Path(row["source_archive"])) != row["source_archive_sha256"]:
            raise PlanContractError("源码归档未完整采集：" + p["name"])
        root = Path(row["source_root"])
        evidence = []
        for e in definition["source_evidence"]:
            path = root / e["path"]
            if not path.resolve().is_relative_to(root.resolve()) or e["quote"] not in path.read_text(errors="replace"):
                raise PlanContractError("作者引用不匹配：" + p["name"])
            evidence.append(e | dict(sha256=digest(path)))
        task = PublicBuildTask(
            task_version="main-build-v1",
            plan_id="r2-" + p["name"].lower(),
            repository_url=p["repository_url"],
            commit_sha=p["commit_sha"],
            image_id=IMAGE,
            source_archive_sha256=row["source_archive_sha256"],
            build_system=p["proposed_build_system"],
        )
        reference = BuildReference(
            task_sha256=_digest(task.model_dump(mode="json")),
            components=definition["components"],
            executable_smokes=definition.get("executable_smokes", []),
            tests_not_applicable_reason="主任务不要求完整作者测试；原生轻量验证与成功重建分层报告",
        )
        projects.append(
            dict(
                name=p["name"],
                family=p["repository_url"].lower(),
                task=task.model_dump(mode="json"),
                reference=reference.model_dump(mode="json"),
                source_archive=row["source_archive"],
                source_evidence=evidence,
                reference_actions=definition["reference_actions"],
                paper_sources=p["sources"],
                exposure="只读准备后的新开发评价集；未用于提案；非最终holdout",
            )
        )
    result = dict(identity="cpp-build-recovery-harness-r2-fixture-v1", selection_sha256=digest(SELECTION), definition_sha256=digest(DEFINITIONS), source_collection=str(sources), projects=projects)
    save(FIXTURE, result)
    return result


def candidate():
    paths = (
        Path(__file__),
        ROOT / "scripts/forge_recovery_harness_comparison.py",
        ROOT / "scripts/forge_recovery_harness_sources.py",
        PREREG,
        SELECTION,
        DEFINITIONS,
        FIXTURE,
        REVIEWED / "candidate.json",
        REVIEWED / "usage.json",
        base.REVIEWED / "baseline.json",
    )
    by_name = {p["name"]: p for p in base.shared.load(FIXTURE)["projects"]}
    return dict(
        identity=IDENTITY,
        issue=725,
        state="user_reviewed_candidate_prepared_requires_new_run_budget_and_window",
        methods=list(METHODS),
        projects=[by_name[name] for name in project_order()],
        schedule=schedule(),
        fixture_sha256=digest(FIXTURE),
        recovery_harnesses={n: h.model_dump(mode="json") for n, h in harnesses().items()},
        reviewed_candidate_sha256=CANDIDATE_SHA,
        user_review="用户：审核通过；新候选可进入比较准备，付费比较另绑定预算与时窗",
        provider=dict(model="deepseek-flash", accepted_models=list(base.shared.MODELS), reasoning_effort="low", max_tokens=32768, max_retries=0, timeout_seconds=240),
        pricing=base.shared.PRICING,
        maximum_cost_usd="5.00",
        maximum_hours=4,
        per_unit_cost_usd="0.40",
        planning_seconds=1200,
        arm_seconds=1800,
        replay_seconds=600,
        validation_scope="main_build",
        comparison_policy="successful-rebuild-v1",
        state_routing="shared_rule_no_jev",
        experience=False,
        initial_plan="one_H0_model_plan_per_project_shared_byte_identically_by_both_clean_arms",
        cost_attribution="actual_batch_common_planner_once; each_deployment_full_common_planning; proposal_and_historical_sources_separate",
        proposal_cost_already_paid_usd=PROPOSAL_COST,
        previous_r2_proposal_cost_already_paid_usd="0.106807",
        holdout=False,
        automatic_retry=False,
        components=base.shared.runtime_files() | {p.relative_to(ROOT).as_posix(): digest(p) for p in paths},
        package_versions={n: importlib.metadata.version(n) for n in ("langchain", "langchain-core", "langgraph", "langchain-deepseek", "openai")},
        boundary="18新项目，每法每项目一次；自然失败才恢复；无恢复不证明指导效果；不补槽、不替换失败、不自动写论文；不与E53跨版本相减归因。",
    )


def validate(value):
    if value["identity"] != IDENTITY or value["schedule"] != schedule() or value["methods"] != list(METHODS):
        raise PlanContractError("新比较身份或排期变化")
    if value["projects"] != [next(p for p in base.shared.load(FIXTURE)["projects"] if p["name"] == n) for n in project_order()] or value["fixture_sha256"] != digest(FIXTURE):
        raise PlanContractError("固定项目或参考变化")
    if Counter(p["task"]["build_system"] for p in value["projects"]) != Counter(cmake=6, make=6, autotools=6):
        raise PlanContractError("三系统各六项目覆盖变化")
    if value["recovery_harnesses"] != {n: h.model_dump(mode="json") for n, h in harnesses().items()} or value["reviewed_candidate_sha256"] != CANDIDATE_SHA:
        raise PlanContractError("已审核候选变化")
    for p in value["projects"]:
        task, ref = PublicBuildTask.model_validate(p["task"]), BuildReference.model_validate(p["reference"])
        if task.image_id != IMAGE or task.task_version != "main-build-v1" or ref.task_sha256 != _digest(task.model_dump(mode="json")) or digest(Path(p["source_archive"])) != task.source_archive_sha256:
            raise PlanContractError("源码、参考或镜像不匹配：" + p["name"])
    for path, expected in value["components"].items():
        if digest(ROOT / path) != expected:
            raise PlanContractError("固定组件变化：" + path)
    for name, version in value["package_versions"].items():
        if importlib.metadata.version(name) != version:
            raise PlanContractError("运行依赖变化：" + name)


def analyze(output):
    """按本次实际固定分母报告，不沿用旧R1标签、分母或提案费用。"""
    value, result = (base.shared.load(output / n) for n in ("protocol.json", "result.json"))
    plans, rows = result["common_initial_plans"], result["rows"]
    initial_cost = sum((base.shared.usage(p)["cost"] for p in plans), Decimal(0))
    initial_seconds = sum(p.get("arm_total_wall_seconds", 0) for p in plans)
    arms, details, pairs = {}, [], []
    for method in value["methods"]:
        matched = [r for r in rows if r["method"] == method]
        cost = sum((base.shared.usage(r)["cost"] for r in matched), Decimal(0))
        wall = sum(r.get("arm_total_wall_seconds", 0) for r in matched)
        arms[method] = dict(
            planned=sum(s["method"] == method for s in value["schedule"]),
            observed=len(matched),
            unobserved=sum(s["method"] == method for s in result["unobserved"]),
            main_build_completed=sum(r.get("layers", {}).get("main_build_task_completed") is True for r in matched),
            reproducible_delivery_completed=sum(r.get("layers", {}).get("reproducible_delivery_completed") is True for r in matched),
            recovery_requests=sum(base.shared.usage(r)["requests"] for r in matched),
            recovery_online_cost_usd=str(cost),
            common_planning_cost_usd=str(initial_cost),
            common_planning_requests=sum(base.shared.usage(p)["requests"] for p in plans),
            common_planning_wall_seconds=initial_seconds,
            deployment_cost_usd=str(initial_cost + cost),
            deployment_with_current_proposal_usd=str(initial_cost + cost + (Decimal(value["proposal_cost_already_paid_usd"]) if method != "H0" else Decimal(0))),
            execution_wall_seconds=wall,
            deployment_wall_seconds=initial_seconds + wall,
        )
    for r in rows:
        folder = output / f"slot-{r['slot']:02d}-{r['project']}-{r['method']}"
        details.append(
            dict(
                slot=r["slot"],
                project=r["project"],
                method=r["method"],
                status=r["status"],
                layers=r.get("layers"),
                timings=r.get("timings"),
                recovery_behavior=base.event_counts(folder),
                initial_plan_sha256=r["initial_plan_sha256"],
                error=r.get("error"),
            )
        )
    for item in value["projects"]:
        matched = [r for r in rows if r["project"] == item["name"]]
        complete = len(matched) == len(value["methods"])
        pairs.append(
            dict(
                project=item["name"],
                complete_pair=complete,
                same_initial_plan=len({r["initial_plan_sha256"] for r in matched}) == 1 if complete else None,
                main_build={r["method"]: r.get("layers", {}).get("main_build_task_completed") for r in matched},
                recovered_methods=[d["method"] for d in details if d["project"] == item["name"] and d["recovery_behavior"].get("recovery_invocations", 0)],
            )
        )
    by_system = {}
    for system in ("cmake", "make", "autotools"):
        names = {p["name"] for p in value["projects"] if p["task"]["build_system"] == system}
        by_system[system] = {
            m: dict(
                planned=sum(s["project"] in names and s["method"] == m for s in value["schedule"]),
                observed=sum(r["project"] in names and r["method"] == m for r in rows),
                main_build_completed=sum(r["project"] in names and r["method"] == m and r.get("layers", {}).get("main_build_task_completed") is True for r in rows),
            )
            for m in value["methods"]
        }
    return dict(
        identity=value["identity"],
        arms=arms,
        details=details,
        pairs=pairs,
        by_build_system=by_system,
        common_initial_failures=[p["project"] for p in plans if p["status"] != "planned"],
        unobserved=result["unobserved"],
        billing_complete=result["billing_complete"],
        known_actual_batch_cost_usd=result["known_actual_batch_cost_usd"],
        actual_batch_cost_usd=result["known_actual_batch_cost_usd"] if result["billing_complete"] else None,
        historical_current_proposal_cost_usd=value["proposal_cost_already_paid_usd"],
        historical_previous_r2_proposal_cost_usd=value["previous_r2_proposal_cost_already_paid_usd"],
        boundary=value["boundary"] + "共同规划实际付一次，各独立部署计全额；提案费另列，未核清全部历史生命周期费用；未观察不填失败。",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--freeze-sources", type=Path)
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--check-prepared", action="store_true")
    modes.add_argument("--analyze", type=Path)
    modes.add_argument("--run", action="store_true")
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.freeze_sources:
        freeze_tasks(args.freeze_sources.resolve())
        return
    if args.analyze:
        print(json.dumps(analyze(args.analyze), ensure_ascii=False, indent=2))
        return
    if args.prepare:
        if MANIFEST.exists():
            raise PlanContractError("不覆盖已固定身份")
        save(MANIFEST, candidate())
    value = base.shared.load(MANIFEST)
    validate(value)
    if not args.run:
        print(json.dumps(dict(valid=True, identity=IDENTITY, manifest_sha256=digest(MANIFEST), projects=len(value["projects"]), slots=len(value["schedule"]), provider_calls=0, credentials_read=False)))
        return
    if not args.authorization or not args.output:
        parser.error("正式比较需要新授权和独立输出目录")
    if args.output.exists():
        raise PlanContractError("旧身份不续跑、不覆盖")
    auth = base.shared.load(args.authorization)
    base.shared.validate_authorization(auth, digest(MANIFEST), identity=IDENTITY, maximum_hours=4)
    if Decimal(auth["maximum_cost_usd"]) > Decimal(value["maximum_cost_usd"]):
        raise PlanContractError("比较新增费用最多5美元")
    OperationWindow(auth["deadline_utc"]).admit("comparison", 900)
    callbacks = base.paid_callbacks(value, auth)
    try:
        base.execute(value, args.output, auth, *callbacks)
    finally:
        if (args.output / "result.json").exists():
            save(args.output / "analysis.json", analyze(args.output))
            result = base.shared.load(args.output / "result.json")
            unknown = sum(base.shared.usage(r)["unknown"] for r in result["rows"] + result["common_initial_plans"]) + int(result["unclosed_unit"] is not None)
            seal(args.output, value, ROOT, unknown_usage_requests=unknown)


if __name__ == "__main__":
    main()
