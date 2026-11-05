#!/usr/bin/env python3
"""简洁主构建九项目三方法比较；历史方案在新任务下实建确认后冻结，Jev不参与。"""

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

import forge_simple_comparison as shared
from forge_build_simple_task import save
from forge_typed_evidence import digest, seal

from deerflow.compile.build_state_routing import BuildStateRouter
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek
from deerflow.compile.plan_workflow import PlanContractError, _digest
from deerflow.compile.simple_build_experience import (
    SimpleProjectRecipe,
    SimpleStateTargetBank,
    select_simple_recipe,
)
from deerflow.compile.simple_build_task import BuildReference, PublicBuildTask

ROOT = shared.ROOT
IDENTITY = "cpp-build-main-system-comparison-flash-v1"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREG = ROOT / "benchmarks/preregistrations" / (IDENTITY + ".md")
FIXTURE = ROOT / "benchmarks/fixtures/main-system-comparison-v1/tasks.json"
PROJECTS = (
    "jsoncpp",
    "double-conversion",
    "miniz",
    "libite",
    "libogg",
    "libsrtp",
    "highwayhash",
    "xxhash",
    "pigz",
)
REUSE_PROJECTS = ("jsoncpp", "libite", "highwayhash")
METHODS = ("forge", "forge_experience", "strong_tool_agent")
# 六种排列各用两次；每个项目第二重复反转顺序，平衡位置与紧邻前序。
ORDERS = ((0, 1, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0), (0, 2, 1), (1, 0, 2))
CAP, HOURS = Decimal("10.00"), 8


def schedule():
    rows = []
    for repeat in range(2):
        for index, name in enumerate(PROJECTS):
            order = ORDERS[(index + repeat * 3) % 6]
            for method in order:
                rows.append(
                    dict(
                        slot=len(rows) + 1,
                        project=name,
                        repetition=repeat + 1,
                        method=METHODS[method],
                    )
                )
    return rows


def candidate():
    fixture = shared.load(FIXTURE)
    bank = shared.load(shared.BANK)
    projects = fixture["projects"]
    components = shared.runtime_files()
    components.update(
        {
            p.relative_to(ROOT).as_posix(): digest(p)
            for p in (
                Path(__file__).resolve(),
                ROOT / "scripts/forge_main_system_sources.py",
                PREREG,
                FIXTURE,
            )
        }
    )
    return dict(
        identity=IDENTITY,
        issue=695,
        launch_state="prepared_requires_current_identity_budget_and_time_authorization",
        kind="stratified_complete_system_comparison",
        holdout=False,
        projects=projects,
        methods=list(METHODS),
        schedule=schedule(),
        fixture_sha256=digest(FIXTURE),
        provider=dict(
            model="deepseek-flash",
            accepted_response_models=list(shared.MODELS),
            thinking="enabled",
            reasoning_effort="low",
            max_tokens=32768,
            max_retries=0,
            http_timeout_seconds=240,
        ),
        pricing=shared.PRICING,
        recipes=fixture["recipes"],
        validation_scope="main_build",
        state_routing="shared_bounded_rule_for_both_forge_arms; no_jev",
        experience=dict(
            path=str(shared.BANK),
            sha256=digest(shared.BANK),
            source_families=sorted({s["family"] for s in bank["sources"]}),
            historical_preparation_cost_usd=bank["preparation_cost_usd"],
            frozen=True,
            online_updates=False,
            retrieval="once_per_agent_task",
            selection="matched_action_advice_v1",
            top_k=2,
            maximum_bytes=4096,
        ),
        policy=dict(
            exact_match="all_public_task_fields_except_plan_id",
            hit="workflow_without_initial_agent",
            miss="one_advice_retrieval_then_planning",
            failure="same_flash_plan_recovery_with_one_retrieval_per_task",
            save="main_task_delivery_replay_verified_final_plan_to_slot_output_only",
        ),
        limits=dict(
            proposed_maximum_cost_usd=str(CAP),
            proposed_hours=HOURS,
            per_slot_cost_usd="0.40",
            per_slot_requests=96,
            per_slot_recorded_tokens=1_000_000,
        ),
        timing=dict(
            slot_seconds=shared.SLOT_SECONDS,
            author_test_seconds=shared.TEST_SECONDS,
            replay_seconds=shared.REPLAY_SECONDS,
            request_admission_seconds=600,
            cleanup_reserve_seconds=300,
            new_slot_admission_seconds=900,
        ),
        components=components,
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
        boundary="九个已开发暴露项目，三复用与六无方案任务分层，各两重复；三系统各三项目。同scope/Flash/镜像/资源/独立检查，无作者测试要求。总体仅对应该混合比例，不估纯状态增量、未见泛化或持续学习。旧结果不合分母。",
    )


def load_recipes(value):
    recipes = []
    for row in value["recipes"].values():
        path = Path(row["path"])
        if digest(path) != row["sha256"]:
            raise PlanContractError("历史成功方案变化")
        recipes.append(SimpleProjectRecipe.model_validate(shared.load(path)))
    return tuple(recipes)


def validate(value):
    if (
        value["identity"] != IDENTITY
        or value["methods"] != list(METHODS)
        or value["schedule"] != schedule()
    ):
        raise PlanContractError("比较身份、三方法或54次顺序变化")
    if (
        digest(FIXTURE) != value["fixture_sha256"]
        or value["projects"] != shared.load(FIXTURE)["projects"]
        or [p["name"] for p in value["projects"]] != list(PROJECTS)
    ):
        raise PlanContractError("共同任务集合变化")
    if (
        digest(Path(value["experience"]["path"])) != value["experience"]["sha256"]
        or value["experience"]["online_updates"] is not False
    ):
        raise PlanContractError("固定经验库变化")
    expected = shared.load(FIXTURE)["recipes"]
    if value["recipes"] != expected:
        raise PlanContractError("方案来源变化")
    recipes = load_recipes(value)
    for item in value["projects"]:
        task = PublicBuildTask.model_validate(item["task"])
        reference = BuildReference.model_validate(item["reference"])
        if digest(
            Path(item["source_archive"])
        ) != task.source_archive_sha256 or reference.task_sha256 != _digest(
            task.model_dump(mode="json")
        ):
            raise PlanContractError("源码或独立参考变化：" + item["name"])
        if (
            task.task_version != "main-build-v1"
            or value["validation_scope"] != "main_build"
        ):
            raise PlanContractError("共同主构建任务范围变化")
        if item["family"] in value["experience"]["source_families"]:
            raise PlanContractError("跨项目经验来源族泄漏")
        hit = select_simple_recipe(recipes=recipes, task=task) is not None
        if hit != (item["name"] in REUSE_PROJECTS) or item["stratum"] != (
            "exact_reuse" if hit else "no_recipe"
        ):
            raise PlanContractError("事前复用分层与实际公开任务匹配不一致")
    for name, expected_hash in value["components"].items():
        if digest(ROOT / name) != expected_hash:
            raise PlanContractError("运行组件变化：" + name)
    for name, version in value["package_versions"].items():
        if importlib.metadata.version(name) != version:
            raise PlanContractError("依赖版本变化：" + name)


def paid_executor(value):
    # main先检查此身份与有效费用/时窗；不更换账户、代理或Provider。
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise PlanContractError("现有DeepSeek凭据不可用")
    model = PlanThinkingDeepSeek(
        model="deepseek-flash",
        api_key=key,
        base_url="https://api.deepseek.com",
        max_tokens=32768,
        max_retries=0,
        timeout=240,
        reasoning_effort="low",
        extra_body={"thinking": {"type": "enabled"}},
    )
    bank, recipes = (
        SimpleStateTargetBank.load(Path(value["experience"]["path"])),
        load_recipes(value),
    )

    def run(*, slot, item, folder, available, deadline):
        task = PublicBuildTask.model_validate(item["task"])
        experience = slot["method"] == "forge_experience"
        recipe = (
            select_simple_recipe(recipes=recipes, task=task) if experience else None
        )
        end = min(
            datetime.fromisoformat(deadline),
            datetime.now(UTC) + timedelta(seconds=shared.SLOT_SECONDS),
        ).isoformat()

        def alarm(_signum, _frame):
            raise TimeoutError("单槽截止；保留失败，无自动重试")

        old = signal.signal(signal.SIGALRM, alarm)
        signal.alarm(
            max(
                1,
                int((datetime.fromisoformat(end) - datetime.now(UTC)).total_seconds())
                - 120,
            )
        )
        try:
            result = shared.run_simple_system(
                task=task,
                reference=BuildReference.model_validate(item["reference"]),
                source_archive=Path(item["source_archive"]),
                output_root=folder,
                method=slot["method"],
                model=model,
                accepted_models=shared.MODELS,
                family=item["family"],
                bank=bank if experience else None,
                recipe=recipe,
                deadline=end,
                maximum_cost_usd=str(min(Decimal("0.40"), available)),
                author_test_seconds=shared.TEST_SECONDS,
                replay_seconds=shared.REPLAY_SECONDS,
                validation_scope="main_build",
                state_router=BuildStateRouter(
                    method="rule", directory=folder / "state-routing"
                )
                if slot["method"] != "strong_tool_agent"
                else None,
            )
            dispatch = dict(
                stratum=item["stratum"],
                exact_recipe_selected=recipe is not None,
                recipe_source_id=recipe.source_id if recipe else None,
                advice_available=experience,
                online_library_updated=False,
            )
            save(folder / "experience-dispatch.json", dispatch)
            return result | dict(stratum=item["stratum"], experience_dispatch=dispatch)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

    return run


def summarize(rows, planned):
    return dict(
        planned=planned,
        observed=len(rows),
        unobserved=planned - len(rows),
        primary_completed=sum(
            r.get("layers", {}).get("primary_build_completed") is True for r in rows
        ),
        main_task_completed=sum(
            r.get("layers", {}).get("main_build_task_completed") is True for r in rows
        ),
        delivery=dict(
            Counter(r.get("layers", {}).get("delivery", "unobserved") for r in rows)
        ),
        clean_replay=dict(
            Counter(r.get("layers", {}).get("clean_replay", "unobserved") for r in rows)
        ),
        model_requests=sum(shared.usage(r)["requests"] for r in rows),
        estimated_cost_usd=str(
            sum((shared.usage(r)["cost"] for r in rows), Decimal(0))
        ),
        total_wall_seconds=sum(r.get("arm_total_wall_seconds", 0) for r in rows),
        initial_planning_seconds=sum(
            r.get("timings", {}).get("initial_planning_seconds", 0) for r in rows
        ),
        recovery_seconds=sum(
            r.get("timings", {}).get("recovery_agent_seconds", 0) for r in rows
        ),
        author_tests=dict(
            Counter(r.get("layers", {}).get("author_tests", "unobserved") for r in rows)
        ),
    )


def analyze(root):
    result, value = (
        shared.load(root / "result.json"),
        shared.load(root / "protocol.json"),
    )
    items = {p["name"]: p for p in value["projects"]}
    details = []
    for row in result["rows"]:
        folder = root / f"slot-{row['slot']:02d}-{row['project']}-{row['method']}"
        event_path = folder / "agent/events.jsonl"
        events = (
            [json.loads(line) for line in event_path.read_text().splitlines()]
            if event_path.exists()
            else []
        )
        phase = "tool_agent" if row["method"] == "strong_tool_agent" else "initial"
        phases = {
            p: dict(requests=0, cost=Decimal(0))
            for p in ("initial", "recovery", "tool_agent")
        }
        for event in events:
            if event["event"] == "agent.started":
                phase = (
                    "tool_agent"
                    if row["method"] == "strong_tool_agent"
                    else "recovery"
                    if event.get("recovery")
                    else "initial"
                )
            elif event["event"] == "model.cost_estimated":
                phases[phase]["requests"] += 1
                phases[phase]["cost"] += Decimal(event["cost_usd"])
        details.append(
            dict(
                slot=row["slot"],
                project=row["project"],
                method=row["method"],
                repetition=row["repetition"],
                stratum=items[row["project"]]["stratum"],
                primary_completed=row.get("layers", {}).get("primary_build_completed"),
                main_task_completed=row.get("layers", {}).get(
                    "main_build_task_completed"
                ),
                router_usage=row.get("router_usage"),
                wall_seconds=row.get("arm_total_wall_seconds"),
                layers=row.get("layers"),
                source_unchanged=row.get("source_unchanged"),
                phase_usage={
                    p: dict(requests=b["requests"], estimated_cost_usd=str(b["cost"]))
                    for p, b in phases.items()
                },
                recipe_selected=any(e["event"] == "recipe.selected" for e in events),
                retrievals=sum(e["event"] == "experience.retrieved" for e in events),
                source_reads=sum(
                    e["event"] == "tool.started" and e.get("name") == "read_source"
                    for e in events
                ),
                error_type=row.get("error_type"),
                error=row.get("error"),
                raw_folder=str(folder),
            )
        )
    summaries = {}
    for stratum in ("all", "exact_reuse", "no_recipe"):
        summaries[stratum] = {}
        for method in METHODS:
            planned = sum(
                s["method"] == method
                and (stratum == "all" or items[s["project"]]["stratum"] == stratum)
                for s in value["schedule"]
            )
            rows = [
                r
                for r in result["rows"]
                if r["method"] == method
                and (stratum == "all" or items[r["project"]]["stratum"] == stratum)
            ]
            summaries[stratum][method] = summarize(rows, planned)
    return dict(
        identity=IDENTITY,
        summary=summaries,
        slots=details,
        unobserved=result["unobserved"],
        historical_advice_preparation_cost_usd=value["experience"][
            "historical_preparation_cost_usd"
        ],
        historical_recipe_source_cost_usd=str(
            sum(
                (
                    Decimal(r["historical_source_cost_usd"])
                    for r in value["recipes"].values()
                ),
                Decimal(0),
            )
        ),
        boundary=value["boundary"],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--check-prepared", action="store_true")
    group.add_argument("--run", action="store_true")
    group.add_argument("--analyze", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.analyze:
        print(json.dumps(analyze(args.analyze), ensure_ascii=False, indent=2))
        return 0
    if args.prepare:
        if MANIFEST.exists():
            raise PlanContractError("不能覆盖已有比较身份")
        value = candidate()
        validate(value)
        save(MANIFEST, value)
    else:
        value = shared.load(MANIFEST)
        validate(value)
    if not args.run:
        print(
            json.dumps(
                dict(
                    valid=True,
                    identity=IDENTITY,
                    slots=54,
                    candidate_sha256=digest(MANIFEST),
                    provider_calls=0,
                    credentials_read=False,
                )
            )
        )
        return 0
    if args.authorization is None or args.output is None:
        raise PlanContractError("需要此身份的新授权文件与独立输出目录")
    auth = shared.load(args.authorization)
    shared.validate_authorization(
        auth, digest(MANIFEST), identity=IDENTITY, maximum_hours=HOURS
    )
    if Decimal(auth["maximum_cost_usd"]) > CAP:
        raise PlanContractError("此批共享上限10美元，不能自动扩大")
    from dotenv import load_dotenv

    load_dotenv(auth["credentials_env_file"], override=False)
    executor = paid_executor(value)
    try:
        shared.execute(value, args.output, auth, executor)
    finally:
        if (args.output / "result.json").exists():
            result = shared.load(args.output / "result.json")
            save(args.output / "analysis.json", analyze(args.output))
            seal(
                args.output,
                value,
                ROOT,
                unknown_usage_requests=sum(
                    shared.usage(r)["unknown"] for r in result["rows"]
                )
                + bool(result.get("unclosed_slot")),
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
