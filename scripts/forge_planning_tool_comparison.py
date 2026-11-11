#!/usr/bin/env python3
"""P0现有行为／P0工具约束／P4工具约束三组比较；默认不调用Provider。"""

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

import forge_planning_p3_comparison as previous
import forge_simple_comparison as shared
from forge_build_simple_task import save
from forge_typed_evidence import digest, seal

from deerflow.compile.build_state_routing import BuildStateRouter
from deerflow.compile.offline_harness import PlanningHarness
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek
from deerflow.compile.plan_workflow import PlanContractError, _digest
from deerflow.compile.recovery_harness import RecoveryHarness
from deerflow.compile.simple_build_task import SIMPLE_PROMPT, BuildReference, PublicBuildTask

ROOT = shared.ROOT
IDENTITY = "cpp-build-planning-tool-p4-comparison-flash-v1"
DIRECTORY = ROOT / "benchmarks/fixtures/planning-tool-p4-comparison-v1"
SELECTION, DEFINITIONS, FIXTURE = (DIRECTORY / n for n in ("selection.json", "definitions.json", "tasks.json"))
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREG = ROOT / "benchmarks/preregistrations" / (IDENTITY + ".md")
P4_FILE = ROOT / "benchmarks/analyses/codex-planning-harness-review-2026-11-11/candidate.json"
P4_SHA = "7686c24b8ab0a2a7434637e7c8002441901667e6c7c613b152b0299a11b1809d"
METHODS = ("A_P0_schema", "B_P0_enforced", "C_P4_enforced")
# 六种排列各两次，每个系统的四项目均有位置变化，不固定某组最后运行。
ORDERS = ((0, 1, 2), (2, 1, 0), (1, 2, 0), (0, 2, 1), (2, 0, 1), (1, 0, 2))


def harnesses():
    p4 = PlanningHarness.model_validate(shared.load(P4_FILE))
    r2 = RecoveryHarness.model_validate(shared.load(previous.R2_FILE))
    if p4.fingerprint() != P4_SHA or r2.fingerprint() != previous.R2_SHA:
        raise PlanContractError("已审核P4或R2指导变化")
    p0 = PlanningHarness(name="P0", base_prompt_sha256=_digest(SIMPLE_PROMPT))
    r2 = r2.model_copy(update=dict(base_prompt_sha256=_digest(SIMPLE_PROMPT)))
    for h in (p0, p4, r2):
        h.prompt(SIMPLE_PROMPT)
    return dict(zip(METHODS, (p0, p0, p4), strict=True)), r2


def project_order():
    projects = shared.load(SELECTION)["projects"]
    groups = [[p["name"] for p in projects if p["proposed_build_system"] == s] for s in ("cmake", "make", "autotools")]
    return [n for block in zip(*groups, strict=True) for n in block]


def schedule():
    return [dict(slot=i * 3 + j + 1, project=n, repetition=1, method=METHODS[m]) for i, n in enumerate(project_order()) for j, m in enumerate(ORDERS[i % 6])]


def freeze_tasks(sources):
    if FIXTURE.exists():
        raise PlanContractError("不覆盖已固定任务")
    definitions = shared.load(DEFINITIONS)
    selected = shared.load(SELECTION)["projects"]
    collected = {p["name"]: p for p in shared.load(sources / "source-index-final.json")["projects"]}
    if set(definitions) != {p["name"] for p in selected}:
        raise PlanContractError("不能增删预选项目")
    projects = []
    for p in selected:
        source, d = collected[p["name"]], definitions[p["name"]]
        root, archive = Path(source["source_root"]), Path(source["source_archive"])
        if source["status"] != "collected" or digest(archive) != source["source_archive_sha256"]:
            raise PlanContractError("源码不完整：" + p["name"])
        evidence = []
        for e in d["source_evidence"]:
            path = root / e["path"]
            if not path.resolve().is_relative_to(root.resolve()) or e["quote"] not in path.read_text(errors="replace"):
                raise PlanContractError("作者证据不匹配：" + p["name"])
            evidence.append(e | dict(sha256=digest(path)))
        task = PublicBuildTask(
            task_version="main-build-v1",
            plan_id="tool-p4-" + p["name"],
            repository_url=p["repository_url"],
            commit_sha=p["commit_sha"],
            image_id=previous.IMAGE,
            source_archive_sha256=source["source_archive_sha256"],
            build_system=p["proposed_build_system"],
        )
        reference = BuildReference(task_sha256=_digest(task.model_dump(mode="json")), components=d["components"], executable_smokes=d.get("executable_smokes", []), tests_not_applicable_reason="普通主构建及作者轻量运行；不要求完整作者测试")
        reference.require_main_build_verification()
        projects.append(
            dict(
                name=p["name"],
                family=p["repository_url"].lower(),
                task=task.model_dump(mode="json"),
                reference=reference.model_dump(mode="json"),
                source_archive=str(archive),
                source_evidence=evidence,
                reference_actions=d["reference_actions"],
                paper_sources=p["sources"],
                historical_exposure_pointers=p["historical_exposure_pointers"],
                exposure="近期Harness评价之外的新项目；旧目录接触如实登记；非最终holdout",
            )
        )
    save(FIXTURE, dict(projects=projects, sources=str(sources), selection_sha256=digest(SELECTION), definitions_sha256=digest(DEFINITIONS)))


def candidate():
    planning, recovery = harnesses()
    projects = {p["name"]: p for p in shared.load(FIXTURE)["projects"]}
    paths = (Path(__file__), SELECTION, DEFINITIONS, FIXTURE, P4_FILE, previous.R2_FILE, PREREG)
    return dict(
        identity=IDENTITY,
        issue=746,
        state="prepared_requires_new_budget_and_window",
        methods=list(METHODS),
        projects=[projects[n] for n in project_order()],
        schedule=schedule(),
        fixture_sha256=digest(FIXTURE),
        planning_harnesses={n: h.model_dump(mode="json") for n, h in planning.items()},
        recovery_harness=recovery.model_dump(mode="json"),
        enforce_planning_tools={n: n != METHODS[0] for n in METHODS},
        intervention_scope="initial_planning_only_recovery_unchanged",
        provider=dict(model="deepseek-flash", accepted_models=list(shared.MODELS), reasoning_effort="low", max_tokens=32768, max_retries=0, timeout_seconds=240),
        pricing=shared.PRICING,
        maximum_cost_usd="5.00",
        maximum_hours=8,
        per_unit_cost_usd="0.40",
        arm_seconds=1800,
        replay_seconds=600,
        validation_scope="main_build",
        comparison_policy="successful-rebuild-v1",
        state_routing="shared_rule_no_jev",
        experience=False,
        initial_plan="independent_in_all_arms",
        automatic_retry=False,
        holdout=False,
        historical_proposal_cost_not_recharged_usd="0",
        proposal_origin="Codex直接分析历史轨迹；无额外Provider提案费，不等于研究者时间成本为零",
        components=shared.runtime_files() | {p.relative_to(ROOT).as_posix(): digest(p) for p in paths},
        package_versions={n: importlib.metadata.version(n) for n in ("langchain", "langchain-core", "langgraph", "langchain-deepseek", "openai")},
    )


def validate(value):
    planning, recovery = harnesses()
    if value["identity"] != IDENTITY or value["schedule"] != schedule() or value["methods"] != list(METHODS):
        raise PlanContractError("身份或排期变化")
    fixed = {p["name"]: p for p in shared.load(FIXTURE)["projects"]}
    if value["projects"] != [fixed[n] for n in project_order()] or digest(FIXTURE) != value["fixture_sha256"]:
        raise PlanContractError("固定任务变化")
    if Counter(p["task"]["build_system"] for p in value["projects"]) != Counter(cmake=4, make=4, autotools=4):
        raise PlanContractError("三系统各四项目覆盖变化")
    if value["planning_harnesses"] != {n: h.model_dump(mode="json") for n, h in planning.items()} or value["recovery_harness"] != recovery.model_dump(mode="json"):
        raise PlanContractError("已审核提示变化")
    if value["enforce_planning_tools"] != {n: n != METHODS[0] for n in METHODS} or value["intervention_scope"] != "initial_planning_only_recovery_unchanged":
        raise PlanContractError("工具约束或恢复隔离变化")
    if value["initial_plan"] != "independent_in_all_arms" or value["experience"] is not False or value["automatic_retry"] is not False:
        raise PlanContractError("独立规划或停止规则变化")
    if (value["arm_seconds"], value["replay_seconds"], value["per_unit_cost_usd"], value["pricing"]) != (1800, 600, "0.40", shared.PRICING):
        raise PlanContractError("时限或计费变化")
    if value["provider"] != candidate_provider() or value["maximum_cost_usd"] != "5.00" or value["maximum_hours"] != 8:
        raise PlanContractError("模型/预算/时窗变化")
    for p in value["projects"]:
        task, ref = PublicBuildTask.model_validate(p["task"]), BuildReference.model_validate(p["reference"])
        ref.require_main_build_verification()
        if task.image_id != previous.IMAGE or ref.task_sha256 != _digest(task.model_dump(mode="json")) or digest(Path(p["source_archive"])) != task.source_archive_sha256:
            raise PlanContractError("源码/参考/镜像变化：" + p["name"])
    for name, expected in value["components"].items():
        if digest(ROOT / name) != expected:
            raise PlanContractError("固定组件变化：" + name)
    for name, expected in value["package_versions"].items():
        if importlib.metadata.version(name) != expected:
            raise PlanContractError("运行依赖变化：" + name)


def candidate_provider():
    return dict(model="deepseek-flash", accepted_models=list(shared.MODELS), reasoning_effort="low", max_tokens=32768, max_retries=0, timeout_seconds=240)


def executor(model):
    planning, recovery = harnesses()

    def run(*, slot, item, folder, available, deadline):
        end = min(datetime.fromisoformat(deadline), datetime.now(UTC) + timedelta(seconds=1800)).isoformat()

        def alarm(_signum, _frame):
            raise TimeoutError("单槽时限；失败保留，不自动重试")

        old = signal.signal(signal.SIGALRM, alarm)
        signal.alarm(max(1, int((datetime.fromisoformat(end) - datetime.now(UTC)).total_seconds()) - 120))
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
                state_router=BuildStateRouter(method="rule", directory=folder / "state-routing"),
                harness=planning[slot["method"]],
                recovery_harness=recovery,
                enforce_planning_tools=slot["method"] != METHODS[0],
            )
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

    return run


def tool_behavior(folder):
    path = folder / "agent/events.jsonl"
    events = [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []
    keys = ("finalize_only_requests", "rejected_tool_calls", "executed_read_calls", "attempted_read_calls")
    buckets = {phase: dict.fromkeys(keys, 0) for phase in ("initial", "recovery")}
    phase = "initial"
    for e in events:
        kind = e["event"]
        if kind == "agent.started":
            phase = "recovery" if e.get("recovery") else "initial"
        b = buckets[phase]
        b["finalize_only_requests"] += kind == "planning.context" and e.get("finalize_only") is True
        b["rejected_tool_calls"] += kind == "planning.tool_rejected"
        read = e.get("name") in {"read_source", "list_source", "read_failure_log"}
        b["executed_read_calls"] += kind == "tool.completed" and read and e.get("executed") is not False
        b["attempted_read_calls"] += kind == "tool.started" and read
    return buckets


def analyze(root):
    result = shared.load(root / "result.json")
    rows = []
    for r in result["rows"]:
        folder = root / f"slot-{r['slot']:02d}-{r['project']}-{r['method']}"
        rows.append(
            dict(
                slot=r["slot"],
                project=r["project"],
                method=r["method"],
                status=r["status"],
                layers=r.get("layers", {}),
                timings=r.get("timings", {}),
                wall_seconds=r.get("arm_total_wall_seconds", 0),
                phases=previous.phase_usage(folder),
                tool_behavior=tool_behavior(folder),
                usage={k: str(v) if isinstance(v, Decimal) else v for k, v in shared.usage(r).items()},
            )
        )
    arms = {}
    for m in METHODS:
        rs = [r for r in rows if r["method"] == m]
        arms[m] = dict(
            planned=12,
            observed=len(rs),
            unobserved=12 - len(rs),
            main_build_completed=sum(r["layers"].get("main_build_task_completed") is True for r in rs),
            reproducible_delivery_completed=sum(r["layers"].get("reproducible_delivery_completed") is True for r in rs),
            requests=sum(r["usage"]["requests"] for r in rs),
            estimated_cost_usd=str(sum((Decimal(r["usage"]["cost"]) for r in rs), Decimal(0))),
            wall_seconds=sum(r["wall_seconds"] for r in rs),
            tool_behavior={phase: {k: sum(r["tool_behavior"][phase][k] for r in rs) for k in ("finalize_only_requests", "rejected_tool_calls", "executed_read_calls", "attempted_read_calls")} for phase in ("initial", "recovery")},
        )
    return dict(
        identity=IDENTITY,
        arms=arms,
        slots=rows,
        unobserved=result["unobserved"],
        unclosed_slot=result["unclosed_slot"],
        billing_complete=result["billing_complete"],
        online_cost_usd=result["closed_slot_cost_usd"],
        boundary="A/B工具约束效果；B/C提示增量；A/C组合更新。不估计完整交互效应；无收敛触发时报告干预未激活。全分母保留失败与未观察，结果先审后入文。",
    )


def run_paid(value, output, auth):
    from dotenv import load_dotenv

    load_dotenv(auth["credentials_env_file"], override=False)
    model = PlanThinkingDeepSeek(
        model="deepseek-flash", api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com", max_tokens=32768, max_retries=0, timeout=240, reasoning_effort="low", extra_body={"thinking": {"type": "enabled"}}
    )
    shared.execute(value, output, auth, executor(model))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--freeze-tasks", type=Path)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--check-prepared", action="store_true")
    group.add_argument("--analyze", type=Path)
    group.add_argument("--run", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--authorization", type=Path)
    args = parser.parse_args()
    if args.freeze_tasks:
        freeze_tasks(args.freeze_tasks)
        return
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
        print(json.dumps(dict(valid=True, identity=IDENTITY, manifest_sha256=digest(MANIFEST), slots=36, provider_calls=0, credentials_read=False)))
        return
    if args.authorization is None or args.output is None or args.output.exists():
        raise PlanContractError("需要新输出目录和有效授权")
    auth = shared.load(args.authorization)
    shared.validate_authorization(auth, digest(MANIFEST), identity=IDENTITY, maximum_hours=8)
    if Decimal(auth["maximum_cost_usd"]) > Decimal(value["maximum_cost_usd"]):
        raise PlanContractError("授权金额超过协议硬上限")
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
