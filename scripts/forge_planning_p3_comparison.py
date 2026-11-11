#!/usr/bin/env python3
"""P0/P3独立规划、共同R2恢复的配对比较；准备不读取Provider凭据。"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import signal
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import forge_simple_comparison as shared
from forge_build_simple_task import save
from forge_recovery_harness_sources import collect_one
from forge_typed_evidence import digest, seal

from deerflow.compile.build_state_routing import BuildStateRouter
from deerflow.compile.offline_harness import PlanningHarness
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek
from deerflow.compile.plan_workflow import PlanContractError, _digest
from deerflow.compile.recovery_harness import RecoveryHarness
from deerflow.compile.simple_build_task import (
    SIMPLE_PROMPT,
    BuildReference,
    PublicBuildTask,
)

ROOT = shared.ROOT
IDENTITY = "cpp-build-planning-p3-fixed-r2-comparison-flash-v1"
DIRECTORY = ROOT / "benchmarks/fixtures/planning-p3-fixed-r2-comparison-v1"
SELECTION, DEFINITIONS, FIXTURE = (
    DIRECTORY / n for n in ("selection.json", "definitions.json", "tasks.json")
)
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREG = ROOT / "benchmarks/preregistrations" / (IDENTITY + ".md")
P3_FILE = (
    ROOT
    / "benchmarks/analyses/planning-harness-system-context-2026-11-11/candidate.json"
)
R2_FILE = (
    ROOT
    / "benchmarks/fixtures/recovery-harness-system-context-gpt61sol-v1/candidate.json"
)
P3_SHA = "126d5ac439f5fe374a4ad8348fca6a8933cd302d3e3a86f2a26afcefabde0f58"
R2_SHA = "270becfd8fe2c0c89d0d7ab8c820893cdc6ae7cdd9d2c50e95ecb11f84263743"
IMAGE = "sha256:8123220a201ac4d00cda0dc985b9db7227cd909bb93ca6c25fd82cafce5cd887"
METHODS = ("P0_R2", "P3_R2")


def harnesses():
    p3 = PlanningHarness.model_validate(shared.load(P3_FILE))
    r2 = RecoveryHarness.model_validate(shared.load(R2_FILE))
    if p3.fingerprint() != P3_SHA or r2.fingerprint() != R2_SHA:
        raise PlanContractError("用户已审核指导发生变化")
    p0 = PlanningHarness(name="P0", base_prompt_sha256=_digest(SIMPLE_PROMPT))
    # 只重绑定共同底座，不编辑已审核恢复指导。
    r2 = r2.model_copy(update=dict(base_prompt_sha256=_digest(SIMPLE_PROMPT)))
    for h in (p0, p3, r2):
        h.prompt(SIMPLE_PROMPT)
    return {"P0_R2": p0, "P3_R2": p3}, r2


def project_order():
    rows = shared.load(SELECTION)["projects"]
    groups = [
        [p["name"] for p in rows if p["proposed_build_system"] == s]
        for s in ("cmake", "make", "autotools")
    ]
    return [name for block in zip(*groups, strict=True) for name in block]


def schedule():
    return [
        dict(slot=i * 2 + j + 1, project=name, repetition=1, method=method)
        for i, name in enumerate(project_order())
        for j, method in enumerate(METHODS[:: 1 if i % 2 == 0 else -1])
    ]


def collect(output):
    output.mkdir(parents=True, exist_ok=False)
    selection = shared.load(SELECTION)
    save(
        output / "scope.json",
        dict(
            kind="zero_provider_preparation",
            selection=selection,
            provider_calls=0,
            cost_usd="0",
            automatic_retry=False,
        ),
    )
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(lambda p: collect_one(p, output), selection["projects"]))
    save(
        output / "result.json",
        dict(projects=rows, provider_calls=0, automatic_retry=False),
    )


def freeze_tasks(sources):
    if FIXTURE.exists():
        raise PlanContractError("不覆盖已固定任务")
    selected, definitions = shared.load(SELECTION)["projects"], shared.load(DEFINITIONS)
    collected = {p["name"]: p for p in shared.load(sources / "result.json")["projects"]}
    if set(definitions) != {p["name"] for p in selected}:
        raise PlanContractError("作者定义不能更换选定项目")
    rows = []
    for p in selected:
        source, definition = collected[p["name"]], definitions[p["name"]]
        archive, root = Path(source["source_archive"]), Path(source["source_root"])
        if (
            source["status"] != "collected"
            or digest(archive) != source["source_archive_sha256"]
        ):
            raise PlanContractError("源码采集不完整：" + p["name"])
        evidence = []
        for e in definition["source_evidence"]:
            path = root / e["path"]
            if not path.resolve().is_relative_to(root.resolve()) or e[
                "quote"
            ] not in path.read_text(errors="replace"):
                raise PlanContractError("作者依据不匹配：" + p["name"])
            evidence.append(e | dict(sha256=digest(path)))
        task = PublicBuildTask(
            task_version="main-build-v1",
            plan_id="p3-" + p["name"].lower(),
            repository_url=p["repository_url"],
            commit_sha=p["commit_sha"],
            image_id=IMAGE,
            source_archive_sha256=source["source_archive_sha256"],
            build_system=p["proposed_build_system"],
        )
        reference = BuildReference(
            task_sha256=_digest(task.model_dump(mode="json")),
            components=definition["components"],
            executable_smokes=definition.get("executable_smokes", []),
            tests_not_applicable_reason="普通主构建；不要求完整作者测试，轻量验证与成功重建分层报告",
        )
        rows.append(
            dict(
                name=p["name"],
                family=p["repository_url"].lower(),
                task=task.model_dump(mode="json"),
                reference=reference.model_dump(mode="json"),
                source_archive=str(archive),
                source_evidence=evidence,
                reference_actions=definition["reference_actions"],
                paper_sources=p["sources"],
                historical_exposure_pointers=p["historical_exposure_pointers"],
                exposure="P3提案与旧H1/H2开发评价之外；已登记目录接触；非最终holdout",
            )
        )
    save(
        FIXTURE,
        dict(
            projects=rows,
            selection_sha256=digest(SELECTION),
            definitions_sha256=digest(DEFINITIONS),
            sources=str(sources),
        ),
    )


def candidate():
    planning, recovery = harnesses()
    by_name = {p["name"]: p for p in shared.load(FIXTURE)["projects"]}
    paths = (Path(__file__), SELECTION, DEFINITIONS, FIXTURE, P3_FILE, R2_FILE, PREREG)
    return dict(
        identity=IDENTITY,
        issue=739,
        state="prepared_requires_new_budget_and_window",
        methods=list(METHODS),
        projects=[by_name[n] for n in project_order()],
        schedule=schedule(),
        fixture_sha256=digest(FIXTURE),
        planning_harnesses={n: h.model_dump(mode="json") for n, h in planning.items()},
        recovery_harness=recovery.model_dump(mode="json"),
        original_reviewed_p3_sha256=P3_SHA,
        original_reviewed_r2_sha256=R2_SHA,
        common_prompt_sha256=_digest(SIMPLE_PROMPT),
        provider=dict(
            model="deepseek-flash",
            accepted_models=list(shared.MODELS),
            reasoning_effort="low",
            max_tokens=32768,
            max_retries=0,
            timeout_seconds=240,
        ),
        pricing=shared.PRICING,
        maximum_cost_usd="5.00",
        maximum_hours=4,
        per_unit_cost_usd="0.40",
        arm_seconds=1800,
        replay_seconds=600,
        validation_scope="main_build",
        comparison_policy="successful-rebuild-v1",
        state_routing="shared_rule_no_jev",
        experience=False,
        initial_plan="independent_model_planning_in_each_arm_no_shared_plan",
        proposal_cost_already_paid_usd="0.317073",
        recovery_proposal_cost_already_paid_usd="0.139614",
        automatic_retry=False,
        holdout=False,
        components=shared.runtime_files()
        | {p.relative_to(ROOT).as_posix(): digest(p) for p in paths},
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


def validate(value):
    planning, recovery = harnesses()
    if (
        value["identity"] != IDENTITY
        or value["schedule"] != schedule()
        or value["methods"] != list(METHODS)
    ):
        raise PlanContractError("身份或排期变化")
    fixed = {p["name"]: p for p in shared.load(FIXTURE)["projects"]}
    if (
        value["projects"] != [fixed[n] for n in project_order()]
        or digest(FIXTURE) != value["fixture_sha256"]
    ):
        raise PlanContractError("固定任务变化")
    if Counter(p["task"]["build_system"] for p in value["projects"]) != Counter(
        cmake=6, make=6, autotools=6
    ):
        raise PlanContractError("三系统各六项目覆盖变化")
    if value["planning_harnesses"] != {
        n: h.model_dump(mode="json") for n, h in planning.items()
    } or value["recovery_harness"] != recovery.model_dump(mode="json"):
        raise PlanContractError("已审核指导变化")
    if (
        value["initial_plan"] != "independent_model_planning_in_each_arm_no_shared_plan"
        or value["experience"] is not False
    ):
        raise PlanContractError("独立规划或无经验边界变化")
    for p in value["projects"]:
        task, ref = (
            PublicBuildTask.model_validate(p["task"]),
            BuildReference.model_validate(p["reference"]),
        )
        if (
            task.image_id != IMAGE
            or task.task_version != "main-build-v1"
            or ref.task_sha256 != _digest(task.model_dump(mode="json"))
            or digest(Path(p["source_archive"])) != task.source_archive_sha256
        ):
            raise PlanContractError("源码/参考/镜像变化：" + p["name"])
    for path, expected in value["components"].items():
        if digest(ROOT / path) != expected:
            raise PlanContractError("固定组件变化：" + path)
    for name, expected in value["package_versions"].items():
        if importlib.metadata.version(name) != expected:
            raise PlanContractError("运行依赖变化：" + name)


def executor(model):
    planning, recovery = harnesses()

    def run(*, slot, item, folder, available, deadline):
        end = min(
            datetime.fromisoformat(deadline),
            datetime.now(UTC) + timedelta(seconds=1800),
        ).isoformat()

        def alarm(_signum, _frame):
            raise TimeoutError("单槽时限；保留失败，不自动重试")

        old = signal.signal(signal.SIGALRM, alarm)
        signal.alarm(
            max(
                1,
                int((datetime.fromisoformat(end) - datetime.now(UTC)).total_seconds())
                - 120,
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
                maximum_cost_usd=str(min(Decimal("0.40"), Decimal(str(available)))),
                validation_scope="main_build",
                replay_seconds=600,
                state_router=BuildStateRouter(
                    method="rule", directory=folder / "state-routing"
                ),
                harness=planning[slot["method"]],
                recovery_harness=recovery,
            )
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

    return run


def phase_usage(folder):
    phase, seen = "initial", set()
    buckets = {
        p: dict(
            requests=0,
            input_tokens=0,
            output_tokens=0,
            cost=Decimal(0),
            reads=0,
            exact_repeat_reads=0,
            invocations=0,
        )
        for p in ("initial", "recovery")
    }
    path = folder / "agent/events.jsonl"
    for event in (
        (json.loads(line) for line in path.read_text().splitlines())
        if path.exists()
        else []
    ):
        kind = event["event"]
        if kind == "agent.started":
            phase = "recovery" if event.get("recovery") else "initial"
            buckets[phase]["invocations"] += 1
        b = buckets[phase]
        if kind == "model.request_completed":
            b["requests"] += 1
            for key in ("input_tokens", "output_tokens"):
                b[key] += event[key]
        elif kind == "model.cost_estimated":
            b["cost"] += Decimal(event["cost_usd"])
        elif kind == "tool.started" and event.get("name") == "read_source":
            key = (phase, _digest(event.get("args", {})))
            b["reads"] += 1
            b["exact_repeat_reads"] += key in seen
            seen.add(key)
    return {
        p: {
            **{k: v for k, v in b.items() if k != "cost"},
            "estimated_cost_usd": str(b["cost"]),
        }
        for p, b in buckets.items()
    }


def analyze(root):
    result, protocol = (shared.load(root / n) for n in ("result.json", "protocol.json"))
    details, arms = [], {}
    for row in result["rows"]:
        phases = phase_usage(
            root / f"slot-{row['slot']:02d}-{row['project']}-{row['method']}"
        )
        details.append(
            dict(
                slot=row["slot"],
                project=row["project"],
                method=row["method"],
                status=row["status"],
                layers=row.get("layers", {}),
                phases=phases,
                usage={
                    k: str(v) if isinstance(v, Decimal) else v
                    for k, v in shared.usage(row).items()
                },
                wall_seconds=row.get("arm_total_wall_seconds", 0),
                timings=row.get("timings", {}),
            )
        )
    for method in METHODS:
        rows = [r for r in details if r["method"] == method]
        arms[method] = dict(
            planned=18,
            observed=len(rows),
            unobserved=18 - len(rows),
            main_build_completed=sum(
                r["layers"].get("main_build_task_completed") is True for r in rows
            ),
            reproducible_delivery_completed=sum(
                r["layers"].get("reproducible_delivery_completed") is True for r in rows
            ),
            completed_without_recovery=sum(
                r["layers"].get("reproducible_delivery_completed") is True
                and not r["phases"]["recovery"]["invocations"]
                for r in rows
            ),
            requests=sum(r["usage"]["requests"] for r in rows),
            estimated_cost_usd=str(
                sum((Decimal(r["usage"]["cost"]) for r in rows), Decimal(0))
            ),
            wall_seconds=sum(r["wall_seconds"] for r in rows),
            phases={
                p: {
                    k: str(
                        sum((Decimal(str(r["phases"][p][k])) for r in rows), Decimal(0))
                    )
                    if k == "estimated_cost_usd"
                    else sum(r["phases"][p][k] for r in rows)
                    for k in rows[0]["phases"][p]
                }
                for p in ("initial", "recovery")
            }
            if rows
            else {},
        )
    return dict(
        identity=IDENTITY,
        arms=arms,
        slots=details,
        unobserved=result["unobserved"],
        unclosed_slot=result["unclosed_slot"],
        billing_complete=result["billing_complete"],
        online_cost_usd=result["closed_slot_cost_usd"],
        planning_proposal_cost_separate_usd=protocol["proposal_cost_already_paid_usd"],
        boundary="18配对开发项目的描述比较；两组各自规划，R2相同；未观察不记失败，全部初始/失败/恢复费用计入；结果先审后入文",
    )


def run_paid(value, output, auth):
    # 只在main完成身份、授权和时窗校验后读取既有接入凭据。
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
    # execute原子占用新目录，重复运行不会改已有证据。
    shared.execute(value, output, auth, executor(model))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--collect", action="store_true")
    group.add_argument("--freeze-tasks", type=Path)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--check-prepared", action="store_true")
    group.add_argument("--analyze", type=Path)
    group.add_argument("--run", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--authorization", type=Path)
    args = parser.parse_args()
    if args.collect:
        collect(args.output)
        return
    if args.freeze_tasks:
        freeze_tasks(args.freeze_tasks)
        return
    if args.analyze:
        print(json.dumps(analyze(args.analyze), ensure_ascii=False, indent=2))
        return
    if args.prepare:
        if MANIFEST.exists():
            raise PlanContractError("不覆盖已固定协议")
        save(MANIFEST, candidate())
    value = shared.load(MANIFEST)
    validate(value)
    if not args.run:
        print(
            json.dumps(
                dict(
                    valid=True,
                    identity=IDENTITY,
                    manifest_sha256=digest(MANIFEST),
                    slots=36,
                    provider_calls=0,
                    credentials_read=False,
                )
            )
        )
        return
    if args.authorization is None or args.output is None or args.output.exists():
        raise PlanContractError("需要新输出目录和本轮有效授权")
    auth = shared.load(args.authorization)
    shared.validate_authorization(
        auth, digest(MANIFEST), identity=IDENTITY, maximum_hours=4
    )
    if Decimal(auth["maximum_cost_usd"]) > Decimal(value["maximum_cost_usd"]):
        raise PlanContractError("授权金额超过本协议硬上限")
    shared.OperationWindow(auth["deadline_utc"]).admit("new_batch", 900)
    try:
        run_paid(value, args.output, auth)
    finally:
        if (args.output / "result.json").exists():
            result = shared.load(args.output / "result.json")
            save(args.output / "analysis.json", analyze(args.output))
            unknown = sum(shared.usage(r)["unknown"] for r in result["rows"]) + int(
                result["unclosed_slot"] is not None
            )
            seal(args.output, value, ROOT, unknown_usage_requests=unknown)


if __name__ == "__main__":
    main()
