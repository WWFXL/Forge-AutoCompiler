#!/usr/bin/env python3
"""固定Flash比较跨项目建议与同项目方案复用；两项独立16槽共享本轮上限。"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import forge_planning_comparison as parent
import forge_simple_comparison as shared
from forge_build_simple_task import save
from forge_typed_evidence import canonical, digest, seal

from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.simple_build_experience import (
    SimpleProjectRecipe,
    SimpleStateTargetBank,
)
from deerflow.compile.simple_build_task import BuildReference, PublicBuildTask

ROOT = shared.ROOT
MODES = ("advice", "reuse")
IDENTITIES = dict(
    advice="cpp-build-repaired-cross-project-experience-flash-v1",
    reuse="cpp-build-simple-project-reuse-flash-v1",
)
SESSION = "cpp-build-base-experience-session-flash-v1"
SOURCE = Path("/home/yiwei/.codex/outputs/forge-planner-model-confirmation-v2")
SOURCE_INVENTORY = "2ffaab2d1b7a9ed689c4ca089c7233f47c26797c8b28f2236c5ed53627326970"
CAP = Decimal("2.00")


def manifest(mode):
    return ROOT / "benchmarks/manifests" / (IDENTITIES[mode] + ".json")


def recipe_sources(projects):
    """按预定第一重复Flash取样，禁止按费用或后续比较结果挑选方案。"""
    inventory = shared.load(SOURCE / "inventory.json")
    if (
        canonical(inventory) != SOURCE_INVENTORY
        or shared.load(SOURCE / "seal.json")["inventory_canonical_sha256"]
        != SOURCE_INVENTORY
    ):
        raise PlanContractError("方案来源封存身份变化")
    hashes = {r["path"]: r["sha256"] for r in inventory if r["type"] == "file"}
    if digest(SOURCE / "result.json") != hashes["result.json"]:
        raise PlanContractError("来源结果变化")
    rows = shared.load(SOURCE / "result.json")["rows"]
    selected = {}
    for item in projects:
        (row,) = [
            r
            for r in rows
            if r["project"] == item["name"]
            and r["repetition"] == 1
            and r["planner"] == "flash"
        ]
        path = (
            SOURCE
            / f"slot-{row['slot']:02d}-{row['project']}-{row['method']}"
            / "verified-simple-recipe.json"
        )
        expected = hashes[path.relative_to(SOURCE).as_posix()]
        if digest(path) != expected or not SimpleProjectRecipe.model_validate(
            shared.load(path)
        ).match(PublicBuildTask.model_validate(item["task"])):
            raise PlanContractError("历史方案改动或不精确匹配当前任务")
        selected[item["name"]] = dict(
            path=str(path),
            sha256=expected,
            source_slot=row["slot"],
            source_inventory_sha256=SOURCE_INVENTORY,
            historical_source_cost_usd=str(shared.usage(row)["cost"]),
        )
    return selected


def candidate(mode):
    value = parent.candidate()
    value.update(
        identity=IDENTITIES[mode],
        issue=687,
        launch_state="authorized_by_current_user_with_self_imposed_small_cap",
        schedule=parent.schedule(),
        kind="paired_development_experience_comparison",
        mode=mode,
    )
    value["limits"].update(
        proposed_maximum_cost_usd=str(CAP),
        proposed_hours=2,
        per_slot_cost_usd="0.40",
        shared_session=SESSION,
    )
    value["experience"].update(
        enabled=mode == "advice",
        online_updates=False,
        exact_recipe_initially_available=mode == "reuse",
    )
    value["recipes"] = recipe_sources(value["projects"]) if mode == "reuse" else {}
    value["boundary"] = (
        "两项独立16槽、相同Flash与修复后Harness；advice只注入跨项目建议，reuse只精确复用成功方案；均不在线更新，全部项目已开发暴露。基础组始终重新规划，两项不合效果分母。"
    )
    prereg = ROOT / "benchmarks/preregistrations" / (value["identity"] + ".md")
    value["components"].update(
        {
            p.relative_to(ROOT).as_posix(): digest(p)
            for p in (Path(__file__).resolve(), prereg)
        }
    )
    return value


def validate(value):
    mode = value["mode"]
    if (
        mode not in MODES
        or value["identity"] != IDENTITIES[mode]
        or value["schedule"] != parent.schedule()
        or value["methods"] != list(parent.METHODS)
    ):
        raise PlanContractError("新比较身份/顺序/方法变化")
    fixture = {p["name"]: p for p in shared.load(shared.FIXTURE)["projects"]}
    if (
        value["projects"] != [fixture[n] for n in parent.PROJECTS]
        or digest(shared.FIXTURE) != value["fixture_sha256"]
    ):
        raise PlanContractError("共同任务/参考变化")
    for item in value["projects"]:
        task = PublicBuildTask.model_validate(item["task"])
        if (
            BuildReference.model_validate(item["reference"]).task_sha256
            != shared._digest(task.model_dump(mode="json"))
            or digest(Path(item["source_archive"])) != task.source_archive_sha256
            or item["family"] in value["experience"]["source_families"]
        ):
            raise PlanContractError("参考/源码变化或跨项目来源族重叠")
    if digest(Path(value["experience"]["path"])) != value["experience"]["sha256"]:
        raise PlanContractError("经验库变化")
    if value["experience"]["enabled"] != (mode == "advice") or value["recipes"] != (
        recipe_sources(value["projects"]) if mode == "reuse" else {}
    ):
        raise PlanContractError("经验处理或来源变化")
    for name, expected in value["components"].items():
        if digest(ROOT / name) != expected:
            raise PlanContractError("运行组件变化：" + name)
    for name, version in value["package_versions"].items():
        if shared.importlib.metadata.version(name) != version:
            raise PlanContractError("依赖版本变化：" + name)


def experience_inputs(value, method):
    """两种经验互斥；基础组完全不读取方案或经验对象。"""
    if method == "forge":
        return None, {}
    if value["mode"] == "advice":
        return SimpleStateTargetBank.load(Path(value["experience"]["path"])), {}
    return None, {
        name: SimpleProjectRecipe.model_validate(shared.load(Path(row["path"])))
        for name, row in value["recipes"].items()
    }


def paid_executor(value):
    # 只在main完成本轮授权/冻结核对后读取已有接入，不改变账户/代理/Provider。
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
    bank, recipes = experience_inputs(value, "forge_experience")

    def run(*, slot, item, folder, available, deadline):
        end = min(
            datetime.fromisoformat(deadline),
            datetime.now(UTC) + timedelta(seconds=shared.SLOT_SECONDS),
        ).isoformat()

        def alarm(_signum, _frame):
            raise TimeoutError("单槽截止；失败保留，不自动重试")

        old = signal.signal(signal.SIGALRM, alarm)
        signal.alarm(
            max(
                1,
                int((datetime.fromisoformat(end) - datetime.now(UTC)).total_seconds())
                - 120,
            )
        )
        try:
            experience = slot["method"] == "forge_experience"
            return shared.run_simple_system(
                task=PublicBuildTask.model_validate(item["task"]),
                reference=BuildReference.model_validate(item["reference"]),
                source_archive=Path(item["source_archive"]),
                output_root=folder,
                method=slot["method"],
                model=model,
                accepted_models=shared.MODELS,
                family=item["family"],
                bank=bank if experience else None,
                recipe=recipes.get(item["name"]) if experience else None,
                deadline=end,
                maximum_cost_usd=str(min(Decimal("0.40"), available)),
                author_test_seconds=shared.TEST_SECONDS,
                replay_seconds=shared.REPLAY_SECONDS,
            )
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

    return run


def analyze(root):
    value, result = (
        shared.load(root / "protocol.json"),
        shared.load(root / "result.json"),
    )
    output = parent.analyze(root)
    output.update(
        identity=value["identity"],
        mode=value["mode"],
        unobserved=result["unobserved"],
        boundary=value["boundary"],
    )
    for slot in output["slots"]:
        folder = root / f"slot-{slot['slot']:02d}-{slot['project']}-{slot['method']}"
        path = folder / "agent/events.jsonl"
        events = (
            [json.loads(line) for line in path.read_text().splitlines()]
            if path.exists()
            else []
        )
        phase, costs, requests = (
            "initial",
            dict(initial=Decimal(0), recovery=Decimal(0)),
            dict(initial=0, recovery=0),
        )
        for event in events:
            if event["event"] == "agent.started":
                phase = "recovery" if event.get("revision", 1) > 1 else "initial"
            if event["event"] == "model.cost_estimated":
                costs[phase] += Decimal(event["cost_usd"])
                requests[phase] += 1
        reused = any(e["event"] == "recipe.selected" for e in events)
        slot.update(
            recipe_selected=reused,
            phase_requests=requests,
            phase_cost_usd={k: str(v) for k, v in costs.items()},
        )
        slot["initial_plan_available"] = slot["initial_plan_delivered"] or reused
    for method, summary in output["summary"].items():
        rows = [r for r in result["rows"] if r["method"] == method]
        slots = [s for s in output["slots"] if s["method"] == method]
        summary.update(
            initial_plan_available=sum(s["initial_plan_available"] for s in slots),
            recipes_selected=sum(s["recipe_selected"] for s in slots),
            initial_planning_seconds=sum(
                r.get("timings", {}).get("initial_planning_seconds", 0) for r in rows
            ),
            recovery_requests=sum(s["phase_requests"]["recovery"] for s in slots),
        )
    return output


def run_session(values, root, authorization):
    root.mkdir(parents=True, exist_ok=False)
    save(root / "authorization.json", authorization)
    known, stages = Decimal(0), []
    for mode in MODES:
        value = values[mode]
        auth = authorization | dict(
            identity=value["identity"],
            candidate_sha256=digest(manifest(mode)),
            maximum_cost_usd=str(Decimal(authorization["maximum_cost_usd"]) - known),
        )
        shared.validate_authorization(
            auth, digest(manifest(mode)), identity=value["identity"], maximum_hours=2
        )
        folder = root / mode
        executor = paid_executor(value)
        try:
            shared.execute(value, folder, auth, executor)
        finally:
            if (folder / "result.json").exists():
                result = shared.load(folder / "result.json")
                save(folder / "analysis.json", analyze(folder))
                seal(
                    folder,
                    value,
                    ROOT,
                    unknown_usage_requests=sum(
                        shared.usage(r)["unknown"] for r in result["rows"]
                    )
                    + bool(result.get("unclosed_slot")),
                )
        known += Decimal(result["closed_slot_cost_usd"])
        stages.append(
            dict(
                mode=mode,
                identity=value["identity"],
                completed=result["completed_slots"],
                cost_usd=result["closed_slot_cost_usd"],
                stop_reason=result["stop_reason"],
            )
        )
        save(
            root / "session-result.json",
            dict(
                identity=SESSION,
                stages=stages,
                known_cost_usd=str(known),
                deadline_utc=authorization["deadline_utc"],
            ),
        )
        if (
            result["stop_reason"]
            or not result["billing_complete"]
            or Decimal(authorization["maximum_cost_usd"]) - known < Decimal("0.10")
        ):
            break


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--check-prepared", action="store_true")
    group.add_argument("--run", action="store_true")
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    values = {}
    for mode in MODES:
        if args.prepare:
            if manifest(mode).exists():
                raise PlanContractError("不覆盖新身份")
            save(manifest(mode), candidate(mode))
        values[mode] = shared.load(manifest(mode))
        validate(values[mode])
    if not args.run:
        print(
            json.dumps(
                dict(
                    provider_calls=0,
                    experiments={
                        mode: dict(
                            identity=v["identity"],
                            sha256=digest(manifest(mode)),
                            slots=16,
                        )
                        for mode, v in values.items()
                    },
                )
            )
        )
        return 0
    if args.authorization is None or args.output is None:
        raise PlanContractError("需要本轮会话授权与新目录")
    auth = shared.load(args.authorization)
    if (
        auth.get("identity") != SESSION
        or not Decimal(0) < Decimal(auth["maximum_cost_usd"]) <= CAP
        or auth.get("experiments") != {m: digest(manifest(m)) for m in MODES}
    ):
        raise PlanContractError("本轮身份/共享2美元/两项候选SHA不符")
    for mode, value in values.items():
        shared.validate_authorization(
            auth
            | dict(identity=value["identity"], candidate_sha256=digest(manifest(mode))),
            digest(manifest(mode)),
            identity=value["identity"],
            maximum_hours=2,
        )
    subprocess.run(
        ["bash", str(ROOT / "scripts/require-docker-runtime.sh")],
        check=True,
        timeout=30,
    )
    run_session(values, args.output, auth)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
