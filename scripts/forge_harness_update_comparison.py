#!/usr/bin/env python3
"""18项目本轮Harness更新比较；默认只核对材料，不读取凭据。"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import signal
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import forge_planning_p3_comparison as phases
import forge_simple_comparison as shared
from forge_build_simple_task import save
from forge_planning_tool_comparison import tool_behavior
from forge_typed_evidence import digest, seal

from deerflow.compile.build_state_routing import BuildStateRouter
from deerflow.compile.offline_harness import PlanningHarness
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek
from deerflow.compile.plan_workflow import PlanContractError, _digest
from deerflow.compile.recovery_harness import RecoveryHarness
from deerflow.compile.simple_build_task import (
    SIMPLE_GOAL,
    SIMPLE_PROMPT,
    BuildReference,
    PublicBuildTask,
)

ROOT = shared.ROOT
IDENTITY = "cpp-build-harness-update-comparison-flash-v1"
DIRECTORY = ROOT / "benchmarks/fixtures/harness-update-comparison-v1"
FIXTURE = DIRECTORY / "tasks.json"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREG = ROOT / "benchmarks/preregistrations" / (IDENTITY + ".md")
IMAGE = "sha256:d483ffa7b71b9545cff9555f6c92b6281a3f826ce006e2d09134cbdca92f8aa1"
METHODS = ("LH_v0_common", "LH_v1")
BASELINE = ROOT / "benchmarks/fixtures/recovery-harness-system-context-gpt61sol-v1/candidate.json"
UPDATED = ROOT / "benchmarks/fixtures/verified-macro-recovery-experience-v1/candidate.json"
CANDIDATE_SHA = "9de184d72f39866fd832a985f720293d6432ccd7c8a033e94f81f2376d4836d8"


def harnesses():
    old = RecoveryHarness.model_validate(shared.load(BASELINE))
    if old.fingerprint() != "270becfd8fe2c0c89d0d7ab8c820893cdc6ae7cdd9d2c50e95ecb11f84263743":
        raise PlanContractError("原R2候选变化")
    old = old.model_copy(update=dict(base_prompt_sha256=_digest(SIMPLE_PROMPT)))
    new = RecoveryHarness.model_validate(shared.load(UPDATED))
    if new.fingerprint() != CANDIDATE_SHA:
        raise PlanContractError("已审核经验候选变化")
    for value in (old, new):
        value.prompt(SIMPLE_PROMPT)
    return dict(zip(METHODS, (old, new), strict=True))


def policy(method):
    if method not in METHODS:
        raise PlanContractError("未知比较组")
    enabled = method == METHODS[1]
    return dict(
        enforce_planning_tools=True,
        recovery_environment_tools=enabled,
        retain_recovery_diagnostics=enabled,
        diagnose_dependencies=enabled,
        inspect_planning_dependencies=enabled,
    )


def project_order():
    return [p["name"] for p in shared.load(FIXTURE)["projects"]]


def schedule():
    return [dict(slot=i * 2 + j + 1, project=name, repetition=1, method=method) for i, name in enumerate(project_order()) for j, method in enumerate(METHODS[:: 1 if i % 2 == 0 else -1])]


def candidate():
    paths = (
        Path(__file__),
        DIRECTORY / "selection.json",
        FIXTURE,
        BASELINE,
        UPDATED,
        PREREG,
        ROOT / "scripts/forge_harness_update_sources.py",
    )
    # 确定性文件集合，避免pytest的其他已导入测试改变协议指纹。
    runtime = list((ROOT / "backend/packages/harness/deerflow").rglob("*.py")) + list((ROOT / "scripts").glob("*.py"))
    return dict(
        identity=IDENTITY,
        issue=809,
        methods=list(METHODS),
        projects=shared.load(FIXTURE)["projects"],
        schedule=schedule(),
        fixture_sha256=digest(FIXTURE),
        provider=dict(
            model="deepseek-flash",
            accepted_models=list(shared.MODELS),
            reasoning_effort="low",
            max_tokens=32768,
            max_retries=0,
            timeout_seconds=240,
        ),
        pricing=shared.PRICING,
        maximum_cost_usd="10.00",
        maximum_hours=8,
        per_unit_cost_usd="0.60",
        arm_seconds=1800,
        replay_seconds=600,
        validation_scope="main_build",
        comparison_policy="successful-rebuild-v1",
        file_policy="posthoc-review-v1",
        context_policy="shared_64000_input_32768_output_current_repair",
        normalized_baseline="LH-v0的P0/R2及源码读取能力，在共同修复后执行器/文件政策/Token容量上运行；不恢复旧49KB缺陷，不声称原历史快照整体差值",
        intervention_scope="规划依赖查询与通用指导、恢复环境工具/组合诊断/证据记忆、R2追加的通用诊断和宏经验",
        arm_options={m: policy(m) for m in METHODS},
        recovery_harnesses={m: h.model_dump(mode="json") for m, h in harnesses().items()},
        initial_plan="independent_in_both_arms",
        recipe_reuse=False,
        experience_bank=None,
        error_experience_delivery="updated_recovery_only_fixed_reviewed_guidance_no_dynamic_retrieval",
        reporting="all_18_projects_only_no_17_project_subgroup_summary",
        historical_exposure="libffi用于本轮开发；其他项目历史目录/旧实验暴露见各项目指针；不称全历史未见或holdout",
        holdout=False,
        automatic_retry=False,
        components={p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(set(runtime) | set(paths))},
        package_versions={
            n: importlib.metadata.version(n)
            for n in (
                "langchain",
                "langchain-core",
                "langgraph",
                "langchain-deepseek",
                "openai",
            )
        },
    )


def validate(value, *, check_sources=True):
    expected = candidate()
    if value != expected:
        raise PlanContractError("比较协议、配置、提示或固定组件变化；不得续用旧身份")
    names = project_order()
    if len(names) != 18 or len(set(names)) != 18 or names.count("libffi") != 1:
        raise PlanContractError("必须保留18项目及libffi")
    if Counter(r["method"] for r in value["schedule"]) != Counter(dict.fromkeys(METHODS, 18)):
        raise PlanContractError("两组各18次且不得增加重复")
    for p in value["projects"]:
        task, ref = (
            PublicBuildTask.model_validate(p["task"]),
            BuildReference.model_validate(p["reference"]),
        )
        ref.require_main_build_verification()
        if task.image_id != IMAGE or task.goal != SIMPLE_GOAL or ref.task_sha256 != _digest(task.model_dump(mode="json")):
            raise PlanContractError("共同任务/镜像/参考变化：" + p["name"])
        if check_sources and digest(Path(p["source_archive"])) != task.source_archive_sha256:
            raise PlanContractError("源码归档变化：" + p["name"])


def executor(model):
    recovery = harnesses()
    planning = PlanningHarness(name="P0", base_prompt_sha256=_digest(SIMPLE_PROMPT))

    def run(*, slot, item, folder, available, deadline):
        end = min(
            datetime.fromisoformat(deadline),
            datetime.now(UTC) + timedelta(seconds=1800),
        ).isoformat()

        def alarm(_signum, _frame):
            raise TimeoutError("单槽超时，失败保留，无自动重试")

        old = signal.signal(signal.SIGALRM, alarm)
        signal.alarm(
            max(
                1,
                int((datetime.fromisoformat(end) - datetime.now(UTC)).total_seconds()) - 120,
            )
        )
        try:
            return shared.run_simple_system(
                task=PublicBuildTask.model_validate(item["task"]),
                reference=BuildReference.model_validate(item["reference"]),
                source_archive=Path(item["source_archive"]),
                output_root=folder,
                method="forge",
                model=model,
                accepted_models=shared.MODELS,
                family=item["family"],
                deadline=end,
                maximum_cost_usd=str(min(Decimal("0.60"), Decimal(str(available)))),
                validation_scope="main_build",
                replay_seconds=600,
                state_router=BuildStateRouter(method="rule", directory=folder / "state-routing"),
                harness=planning,
                recovery_harness=recovery[slot["method"]],
                **policy(slot["method"]),
            )
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

    return run


def analyze(root):
    result = shared.load(root / "result.json")
    details = []
    for row in result["rows"]:
        folder = root / f"slot-{row['slot']:02d}-{row['project']}-{row['method']}"
        details.append(
            dict(
                slot=row["slot"],
                project=row["project"],
                method=row["method"],
                status=row["status"],
                layers=row.get("layers", {}),
                wall_seconds=row.get("arm_total_wall_seconds", 0),
                phases=phases.phase_usage(folder),
                tool_behavior=tool_behavior(folder),
                usage={k: str(v) if isinstance(v, Decimal) else v for k, v in shared.usage(row).items()},
            )
        )
    arms = {}
    for method in METHODS:
        rs = [r for r in details if r["method"] == method]
        arms[method] = dict(
            planned=18,
            observed=len(rs),
            unobserved=18 - len(rs),
            main_build_completed=sum(r["layers"].get("main_build_task_completed") is True for r in rs),
            reproducible_delivery_completed=sum(r["layers"].get("reproducible_delivery_completed") is True for r in rs),
            requests=sum(r["usage"]["requests"] for r in rs),
            input_tokens=sum(r["usage"]["input_tokens"] for r in rs),
            output_tokens=sum(r["usage"]["output_tokens"] for r in rs),
            estimated_cost_usd=str(sum((Decimal(r["usage"]["cost"]) for r in rs), Decimal(0))),
            wall_seconds=sum(r["wall_seconds"] for r in rs),
            phases={p: dict(requests=sum(r["phases"][p]["requests"] for r in rs), estimated_cost_usd=str(sum((Decimal(r["phases"][p]["estimated_cost_usd"]) for r in rs), Decimal(0)))) for p in ("initial", "recovery")},
        )
    return dict(
        identity=IDENTITY,
        arms=arms,
        slots=details,
        unobserved=result["unobserved"],
        unclosed_slot=result["unclosed_slot"],
        billing_complete=result["billing_complete"],
        online_cost_usd=result["closed_slot_cost_usd"],
        boundary="只汇总全部18项目；libffi开发暴露注明。包含多项Harness更新，不将差值归因单一经验或上下文；不作跨项目总体显著性声明。",
    )


def run_paid(value, output, auth):
    from dotenv import load_dotenv

    load_dotenv(auth["credentials_env_file"], override=False)
    model = PlanThinkingDeepSeek(
        model="deepseek-flash",
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
        max_tokens=32768,
        max_retries=0,
        timeout=240,
        reasoning_effort="low",
        extra_body={"thinking": {"type": "enabled"}},
    )
    shared.execute(value, output, auth, executor(model))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--check-prepared", action="store_true")
    group.add_argument("--analyze", type=Path)
    group.add_argument("--run", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--authorization", type=Path)
    args = parser.parse_args()
    if args.analyze:
        print(json.dumps(analyze(args.analyze), ensure_ascii=False, indent=2))
        return
    if args.prepare:
        if MANIFEST.exists():
            raise PlanContractError("不覆盖已冻结协议")
        save(MANIFEST, candidate())
    value = shared.load(MANIFEST)
    validate(value)
    if not args.run:
        print(
            json.dumps(
                dict(
                    identity=IDENTITY,
                    valid=True,
                    manifest_sha256=digest(MANIFEST),
                    projects=18,
                    slots=36,
                    provider_calls=0,
                    credentials_read=False,
                )
            )
        )
        return
    if args.authorization is None or args.output is None or args.output.exists():
        raise PlanContractError("需要新输出目录和有效授权")
    auth = shared.load(args.authorization)
    shared.validate_authorization(auth, digest(MANIFEST), identity=IDENTITY, maximum_hours=8)
    shared.OperationWindow(auth["deadline_utc"]).admit("new_batch", 900)
    try:
        run_paid(value, args.output, auth)
    finally:
        if (args.output / "result.json").exists():
            result = shared.load(args.output / "result.json")
            save(args.output / "analysis.json", analyze(args.output))
            unknown = sum(shared.usage(r)["unknown"] for r in result["rows"]) + int(result["unclosed_slot"] is not None)
            seal(args.output, value, ROOT, unknown_usage_requests=unknown)


if __name__ == "__main__":
    main()
