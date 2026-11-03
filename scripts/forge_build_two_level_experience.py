#!/usr/bin/env python3
"""两层经验的两个独立比较；复用现有完整构建、恢复、计量和验收入口。"""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import forge_build_action_experience as action
from forge_build_experience_comparison import save

from deerflow.compile.build_experience import ExperienceBank
from deerflow.compile.goal_state import GoalStateWorkflow, goal_state_planner
from deerflow.compile.plan_workflow import BuildPlan
from deerflow.compile.project_experience import (
    ProjectRecipe,
    StateTargetBank,
    recipe_planner,
    verified_recipe,
)

base, system, ROOT = action.base, action.system, action.ROOT
SESSION = Path("/home/yiwei/.codex/outputs/forge-two-level-experience-session-v1")
IDENTITIES = dict(
    recipe="cpp-build-project-recipe-reuse-flash-v1",
    retrieval="cpp-build-state-target-retrieval-flash-v1",
)
OLD_BANK = Path(
    "/home/yiwei/.codex/outputs/forge-experience-session-2026-11-02/richlab-route-v1/seed-bank.json"
)
SOURCES = Path(
    "/home/yiwei/.codex/outputs/forge-task-action-experience-session-v1/sources.json"
)
RECIPE_PROJECTS = ("simdutf", "snappy", "yaml-cpp", "tinyxml2", "rang", "ELFIO")
CHANGED = {"simdutf", "rang", "ELFIO"}
CROSS_PROJECTS = (
    "jsoncpp",
    "pegtl",
    "inja",
    "highwayhash",
    "libsigcplusplus",
    "libsrtp",
)
METHODS = dict(
    recipe=("replan", "recipe_reuse"),
    retrieval=("no_experience", "source_retrieval", "state_target_retrieval"),
)
PREREG = "benchmarks/preregistrations/cpp-build-two-level-experience-v1.md"
NEW_FILES = (
    "scripts/forge_build_two_level_experience.py",
    "backend/packages/harness/deerflow/compile/project_experience.py",
    "backend/tests/test_project_experience.py",
    PREREG,
)


def manifest(kind):
    return ROOT / "benchmarks/manifests" / (IDENTITIES[kind] + ".json")


def output(kind):
    return SESSION.parent / ("forge-" + IDENTITIES[kind].removeprefix("cpp-build-"))


def changed_profile(value):
    if isinstance(value, str):
        return value.replace("Release", "Debug")
    if isinstance(value, list):
        return [changed_profile(v) for v in value]
    if isinstance(value, dict):
        return {k: changed_profile(v) for k, v in value.items()}
    return value


def current_public_task(item):
    result = ORIGINAL_COMMON_TASK(item)
    if item.get("scenario") == "profile_changed":
        result["build_profile"] = (
            "本任务预先指定CMake build目录和Debug；必须满足当前verification_steps，其余原测试/交付不变。"
        )
        result["common_test_preparation"] = item["common_test_preparation"]
    return result


ORIGINAL_COMMON_TASK = system.common_task


def prepare():
    """用户已授权本阶段全部费用；内部保守设20美元/12小时，不读取凭据。"""
    SESSION.mkdir(exist_ok=False)
    now = datetime.now(UTC)
    auth = dict(
        user_reply="好的开始执行这个阶段，批准一切预算。",
        authorized_scope="已讨论四步、24次同项目+36次跨项目；不自动扩样本",
        authorized_at_utc=now.isoformat(),
        deadline_utc=(now + timedelta(hours=12)).isoformat(),
        maximum_cost_usd="20",
        budget_basis="用户批准本阶段全部预算，执行者自设共享20美元保守上限",
        automatic_retry=False,
        identities=list(IDENTITIES.values()),
        stop_rules=[
            "unknown_usage",
            "model_identity_mismatch",
            "cleanup_failure",
            "deadline",
            "internal_budget",
        ],
    )
    save(SESSION / "authorization.json", auth)
    bank = base.load(OLD_BANK)
    save(SESSION / "seed-bank.json", bank)
    recipes = {}
    sources = base.load(SOURCES)
    for name in RECIPE_PROJECTS:
        trace = next(
            s
            for s in sources
            if s["family"] == name and s["source_id"].startswith("E30")
        )
        plans = [
            o["plan"]
            for o in trace["process_observations"]
            if o["kind"] == "submitted_plan"
        ]
        final = BuildPlan.model_validate(max(plans, key=lambda p: p["revision"]))
        recipe = verified_recipe(
            source_id=trace["source_id"],
            task=base.PlanTask.model_validate(trace["task"]),
            plan=final,
            validation=trace["observed_validation"],
        )
        recipes[name] = recipe.model_dump(mode="json")
    save(SESSION / "project-recipes.json", recipes)
    for kind in IDENTITIES:
        parent = base.load(
            ROOT
            / (
                "benchmarks/manifests/cpp-build-unified-system-comparison-flash-v1.json"
                if kind == "recipe"
                else "benchmarks/manifests/cpp-build-transfer-action-experience-flash-v1.json"
            )
        )
        candidate = copy.deepcopy(parent)
        names = RECIPE_PROJECTS if kind == "recipe" else CROSS_PROJECTS
        candidate["projects"] = [
            copy.deepcopy(next(p for p in parent["projects"] if p["name"] == name))
            for name in names
        ]
        for item in candidate["projects"]:
            item["scenario"] = (
                "profile_changed"
                if kind == "recipe" and item["name"] in CHANGED
                else "unchanged"
                if kind == "recipe"
                else "cross_project"
            )
            if item["scenario"] == "profile_changed":
                item["task"]["verification_steps"] = changed_profile(
                    item["task"]["verification_steps"]
                )
                item["common_test_preparation"] = changed_profile(
                    item["common_test_preparation"]
                )
            base.PlanTask.model_validate(item["task"])
        methods = METHODS[kind]
        schedule = []
        for repeat in (1, 2):
            for position, name in enumerate(names):
                order = (
                    range(2)
                    if kind == "recipe" and (position + repeat) % 2
                    else reversed(range(2))
                    if kind == "recipe"
                    else base.ORDERS[(position + 3 * (repeat - 1)) % 6]
                )
                schedule.extend(
                    dict(project=name, repetition=repeat, method=methods[j])
                    for j in order
                )
        candidate.update(
            identity=IDENTITIES[kind],
            issue=668,
            kind="verified_project_recipe_reuse"
            if kind == "recipe"
            else "same_bank_state_target_retrieval",
            schedule=schedule,
            methods=methods,
            authorization_sha256=base.digest(SESSION / "authorization.json"),
            stage_max_cost_usd="20",
            holdout=False,
            new_paid_distillation=False,
            seed_preparation="existing_verified_sources_no_model_rewrite",
            comparison_boundary="开发暴露项目；同项目固定源码/镜像，三项预先指定Release→Debug目标变化，非版本/环境泛化。跨项目同24条库、相同上下文12000字节/top3来源，仅选择方式改变。无自动重试，无跨重复更新。",
            material_hashes={
                str(p): base.digest(p)
                for p in (
                    OLD_BANK,
                    SOURCES,
                    SESSION / "seed-bank.json",
                    SESSION / "project-recipes.json",
                )
            },
        )
        candidate["source_index_contracts"] = {
            n: parent["source_index_contracts"][n] for n in names
        }
        candidate["components"] = {
            p: base.digest(ROOT / p)
            for p in sorted(set(parent["components"]) | set(NEW_FILES))
        }
        save(manifest(kind), candidate)
    save(
        SESSION / "preparation.json",
        dict(
            recipe_slots=24,
            retrieval_slots=36,
            new_provider_requests=0,
            old_seed_distillation_usd="0.095129",
            recipe_generation_model_cost_usd="0",
            recipe_sources={n: r["source_id"] for n, r in recipes.items()},
        ),
    )


def check_prepared():
    auth = base.load(SESSION / "authorization.json")
    if auth["user_reply"] != "好的开始执行这个阶段，批准一切预算。" or auth[
        "identities"
    ] != list(IDENTITIES.values()):
        raise ValueError("缺少当前范围授权")
    for kind, identity in IDENTITIES.items():
        protocol = base.load(manifest(kind))
        if protocol["identity"] != identity or len(protocol["schedule"]) != (
            24 if kind == "recipe" else 36
        ):
            raise ValueError("独立身份/分母变化")
        if (
            base.digest(SESSION / "authorization.json")
            != protocol["authorization_sha256"]
        ):
            raise ValueError("本轮授权变化")
        for name, digest in {
            **protocol["components"],
            **protocol["material_hashes"],
        }.items():
            if (
                base.digest(Path(name) if Path(name).is_absolute() else ROOT / name)
                != digest
            ):
                raise ValueError("固定实现/材料变化：" + name)
        for item in protocol["projects"]:
            if (
                base.digest(Path(item["source_archive"]))
                != item["task"]["source_archive_sha256"]
            ):
                raise ValueError("源码归档变化")
    return auth


def run_slot(protocol, slot, folder, model, *, recipe=None):
    item = next(p for p in protocol["projects"] if p["name"] == slot["project"])
    task = base.PlanTask.model_validate(item["task"])
    data = base.load(SESSION / "seed-bank.json")
    bank_type = (
        StateTargetBank
        if slot["method"] == "state_target_retrieval"
        else ExperienceBank
    )
    bank = bank_type(data["sources"], data["entries"])
    mode = (
        "none"
        if slot["method"] in ("replan", "recipe_reuse", "no_experience")
        else "structured"
    )
    save(
        folder / "experience-bank-used.json",
        dict(
            source_ids=[s["source_id"] for s in data["sources"]],
            entries=data["entries"],
        ),
    )
    with action.task_interfaces():
        original = base.observed_module.observed_planner

        def planner_factory(*args, **kwargs):
            planner = goal_state_planner(original(*args, **kwargs))
            return (
                recipe_planner(planner, recipe, allow_goal_trial=True)
                if recipe is not None
                else planner
            )

        with (
            patch.object(
                base, "PreparationMeter", action.meter_class(item, task, bank, mode)
            ),
            patch.object(
                base, "execution_window", system.component.bounded.execution_window
            ),
            patch.object(base.prepared_module, "PreparedWorkflow", GoalStateWorkflow),
            patch.object(base.observed_module, "observed_planner", planner_factory),
            patch.object(system, "common_task", current_public_task),
        ):
            row = system.replication.run_slot(
                protocol=protocol,
                slot={**slot, "method": "model_plan_workflow"},
                root=folder,
                model=model,
            )
    return {**row, **slot, "scenario": item["scenario"], "experience_mode": mode}


def completed_recipe(protocol, row, folder):
    """任务后生成新版；保存在本槽，不让其泄漏到后续比较或覆盖种子。"""
    if not row["strict_completed"]:
        return None
    sessions = list(folder.glob("*/.compile-sessions/*/*/session.json"))
    session = base.load(sessions[0])
    plans = [base.load(p) for p in folder.glob("*/agent/*plan-*.json")]
    if not plans:
        return None
    final = BuildPlan.model_validate(max(plans, key=lambda p: p["revision"]))
    task = base.PlanTask.model_validate(
        next(p["task"] for p in protocol["projects"] if p["name"] == row["project"])
    )
    validation = dict(
        full_completed=True,
        source_unchanged=row.get("fixed_sources_unchanged"),
        replay=session.get("replay_attempts", []),
        cleanup=row["cleanup"],
    )
    value = verified_recipe(
        source_id="new-task:" + folder.name,
        task=task,
        plan=final,
        validation=validation,
    ).model_dump(mode="json")
    save(folder / "verified-recipe-update.json", value)
    return value


def run():
    from dotenv import load_dotenv

    auth = check_prepared()
    subprocess.run(
        ["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True
    )
    # 身份、授权、成本和停止规则均已固定，至此才读取Provider配置。
    load_dotenv(ROOT / ".env", override=False)
    model = base.PlanThinkingDeepSeek(
        model="deepseek-flash",
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
        max_tokens=32768,
        max_retries=0,
        timeout=240,
        reasoning_effort="low",
        extra_body={"thinking": {"type": "enabled"}},
    )
    recipes = {
        k: ProjectRecipe.model_validate(v)
        for k, v in base.load(SESSION / "project-recipes.json").items()
    }
    paid, stop_all = Decimal(0), None
    before_original = system.CommonTaskMeter._before_request

    def before(meter):
        if paid + Decimal(str(meter.cost_usd)) + Decimal("0.80") > Decimal(
            auth["maximum_cost_usd"]
        ):
            raise base.PlanContractError("本阶段内部共享预算不足下一完整响应")
        return before_original(meter)

    with patch.object(system.CommonTaskMeter, "_before_request", before):
        for kind, identity in IDENTITIES.items():
            if stop_all:
                break
            protocol = base.load(manifest(kind))
            protocol["deadline_utc"] = auth["deadline_utc"]
            root = output(kind)
            root.mkdir(exist_ok=False)
            save(root / "protocol.json", protocol)
            save(root / "authorization.json", auth)
            save(
                root / "execution.json",
                dict(
                    release=subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], text=True
                    ).strip(),
                    candidate_sha256=base.digest(manifest(kind)),
                ),
            )
            rows, updates, reason, initial_paid = [], [], None, paid
            try:
                for index, slot in enumerate(protocol["schedule"], 1):
                    if system.OperationWindow(
                        auth["deadline_utc"]
                    ).remaining() < system.SLOT_SECONDS or paid + Decimal(
                        "0.80"
                    ) > Decimal(auth["maximum_cost_usd"]):
                        reason = stop_all = "deadline_or_internal_budget"
                        break
                    folder = root / f"slot-{index}"
                    folder.mkdir()
                    selected = {
                        **protocol,
                        "deadline_utc": min(
                            datetime.fromisoformat(auth["deadline_utc"]),
                            datetime.now(UTC) + timedelta(seconds=system.SLOT_SECONDS),
                        ).isoformat(),
                    }
                    started = time.monotonic()
                    try:
                        row = run_slot(
                            selected,
                            slot,
                            folder,
                            model,
                            recipe=recipes[slot["project"]]
                            if slot["method"] == "recipe_reuse"
                            else None,
                        )
                    except Exception as exc:
                        usage_files = list(folder.glob("*/agent/usage.json"))
                        usage = (
                            base.load(usage_files[0])
                            if len(usage_files) == 1
                            else dict(
                                model_requests=0,
                                estimated_cost_usd_completed_responses="0",
                                unknown_usage_requests=1,
                            )
                        )
                        row = {
                            **slot,
                            "strict_completed": False,
                            "agent_usage": usage,
                            "cleanup": dict(succeeded=False),
                            "error_class": type(exc).__name__,
                            "error_message": str(exc)[:1500],
                        }
                    row["arm_total_wall_seconds"] = time.monotonic() - started
                    rows.append(row)
                    paid += Decimal(
                        str(
                            row["agent_usage"]["estimated_cost_usd_completed_responses"]
                        )
                    )
                    save(root / f"progress-{index}.json", row)
                    if kind == "recipe":
                        update = completed_recipe(protocol, row, folder)
                        if update:
                            updates.append(dict(slot=index, recipe=update))
                    print(
                        json.dumps(
                            dict(
                                identity=identity,
                                slot=index,
                                project=row["project"],
                                method=row["method"],
                                complete=row["strict_completed"],
                                seconds=row["arm_total_wall_seconds"],
                                usage=row["agent_usage"],
                                error=row.get("error_message"),
                                shared_cost_usd=str(paid),
                            ),
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                    events = [
                        json.loads(line)
                        for p in folder.glob("*/agent/events.jsonl")
                        for line in p.read_text().splitlines()
                    ]
                    if (
                        row["agent_usage"]["unknown_usage_requests"]
                        or not row["cleanup"]["succeeded"]
                        or any(e["event"] == "model.identity_mismatch" for e in events)
                    ):
                        reason = stop_all = "unknown_usage_identity_or_cleanup"
                        break
            except BaseException as exc:
                reason = stop_all = type(exc).__name__ + ": " + str(exc)[:500]
                raise
            finally:
                save(
                    root / "result.json",
                    dict(
                        identity=identity,
                        rows=rows,
                        updates=updates,
                        unobserved_schedule=protocol["schedule"][len(rows) :],
                        stop_reason=reason,
                        known_estimated_cost_usd=str(paid - initial_paid),
                        distillation_cost_usd="0",
                        shared_cost_usd=str(paid),
                    ),
                )
                base.seal(
                    root,
                    protocol,
                    ROOT,
                    sum(r["agent_usage"]["unknown_usage_requests"] for r in rows),
                )
    save(
        SESSION / "final-session-summary.json",
        dict(
            shared_cost_usd=str(paid),
            stop_reason=stop_all,
            outputs={k: str(output(k)) for k in IDENTITIES},
            new_distillation_requests=0,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "check-prepared", "run"))
    args = parser.parse_args()
    {"prepare": prepare, "check-prepared": check_prepared, "run": run}[args.action]()


if __name__ == "__main__":
    main()
