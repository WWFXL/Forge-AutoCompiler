#!/usr/bin/env python3
"""同一H0初始方案、18新项目各一次的H0/R1恢复比较；准备与付费运行分开。"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import tarfile
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import forge_simple_comparison as shared
from forge_build_simple_task import save
from forge_recovery_harness_sources import FIXTURE, POOL
from forge_typed_evidence import digest, seal

from deerflow.compile.build_state_routing import BuildStateRouter
from deerflow.compile.operation_window import OperationWindow
from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_agent_canary import source_packet
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek
from deerflow.compile.plan_workflow import PlanContractError, _digest
from deerflow.compile.recovery_harness import RecoveryHarness
from deerflow.compile.simple_build_agents import SimpleBuildMeter
from deerflow.compile.simple_build_task import SIMPLE_PROMPT, BuildReference, PublicBuildTask, SimpleBuildPlan, propose_simple

ROOT = shared.ROOT
IDENTITY = "cpp-build-recovery-harness-comparison-flash-v1"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREG = ROOT / "benchmarks/preregistrations" / (IDENTITY + ".md")
REVIEWED = ROOT / "benchmarks/fixtures/recovery-harness-proposal-v1"
METHODS = ("H0", "R1")
CANDIDATE_SHA = "35280b6a11f01ef5da56d438659f0492c12ea8a82c18ac3d8a3b2e0e89d14ecf"
PROPOSAL_COST = "0.105856"


def projects():
    original = shared.load(POOL)["proposed_evaluation"]
    # 三系统交错，避免时窗中断仅观察某一系统；系统内保持公布顺序。
    groups = [[p["name"] for p in original if p["proposed_build_system"] == system] for system in ("cmake", "make", "autotools")]
    return [name for block in zip(*groups, strict=True) for name in block]


def schedule():
    rows = []
    for index, name in enumerate(projects()):
        for method in METHODS[:: 1 if index % 2 == 0 else -1]:
            rows.append(dict(slot=len(rows) + 1, project=name, repetition=1, method=method))
    return rows


def harnesses():
    h0 = RecoveryHarness.model_validate(shared.load(REVIEWED / "baseline.json"))
    r1 = RecoveryHarness.model_validate(shared.load(REVIEWED / "candidate.json"))
    if h0.recovery_guidance or r1.fingerprint() != CANDIDATE_SHA:
        raise PlanContractError("恢复策略不等于用户审核的原始提案")
    for value in (h0, r1):
        value.prompt(SIMPLE_PROMPT)
    return dict(H0=h0, R1=r1)


def candidate():
    hs = harnesses()
    paths = (Path(__file__), ROOT / "scripts/forge_recovery_harness_sources.py", PREREG, FIXTURE, POOL, REVIEWED / "baseline.json", REVIEWED / "candidate.json", REVIEWED / "corpus.json", REVIEWED / "usage.json")
    components = shared.runtime_files() | {p.relative_to(ROOT).as_posix(): digest(p) for p in paths}
    by_name = {p["name"]: p for p in shared.load(FIXTURE)["projects"]}
    return dict(
        identity=IDENTITY,
        issue=711,
        state="implemented_requires_current_run_budget_and_window",
        methods=list(METHODS),
        projects=[by_name[name] for name in projects()],
        schedule=schedule(),
        fixture_sha256=digest(FIXTURE),
        recovery_harnesses={key: value.model_dump(mode="json") for key, value in hs.items()},
        reviewed_candidate_sha256=CANDIDATE_SHA,
        user_review="用户：好的，我已审核开始做比较实现。；提案审核和比较实现已授权，费用/时窗另绑定",
        provider=dict(model="deepseek-flash", accepted_models=list(shared.MODELS), reasoning_effort="low", max_tokens=32768, max_retries=0, timeout_seconds=240),
        pricing=shared.PRICING,
        maximum_cost_usd="5.00",
        maximum_hours=4,
        per_unit_cost_usd="0.40",
        planning_seconds=1200,
        arm_seconds=1800,
        replay_seconds=600,
        validation_scope="main_build",
        state_routing="shared_rule_no_jev",
        experience=False,
        initial_plan="one_H0_model_plan_per_project_shared_byte_identically_by_both_clean_arms",
        cost_attribution="actual_batch_counts_common_planner_once; each_method_deployment_includes_full_common_planning; proposal_and_historical_sources_separate",
        proposal_cost_already_paid_usd=PROPOSAL_COST,
        holdout=False,
        automatic_retry=False,
        components=components,
        package_versions={n: importlib.metadata.version(n) for n in ("langchain", "langchain-core", "langgraph", "langchain-deepseek", "openai")},
        boundary="18个新开发项目、每法每项目一次；真实自然失败才恢复；无失败路径不证明恢复效果；无补槽/失败替换/论文自动更新。",
    )


def validate(value, *, identity=IDENTITY):
    if value["identity"] != identity or value["schedule"] != schedule() or value["methods"] != list(METHODS):
        raise PlanContractError("恢复比较身份或36槽排期变化")
    expected = {p["name"]: p for p in shared.load(FIXTURE)["projects"]}
    if value["projects"] != [expected[n] for n in projects()] or digest(FIXTURE) != value["fixture_sha256"]:
        raise PlanContractError("固定任务集合变化")
    if Counter(p["task"]["build_system"] for p in value["projects"]) != Counter(cmake=6, make=6, autotools=6):
        raise PlanContractError("18项目三系统覆盖变化")
    training = {e["repository_url"].lower().removesuffix(".git").rstrip("/") for e in shared.load(REVIEWED / "corpus.json")["episodes"]}
    if training & {p["task"]["repository_url"].lower().removesuffix(".git").rstrip("/") for p in value["projects"]}:
        raise PlanContractError("优化来源与评价项目重叠")
    if value["recovery_harnesses"] != {n: h.model_dump(mode="json") for n, h in harnesses().items()}:
        raise PlanContractError("已审核恢复指导发生变化")
    for p in value["projects"]:
        task, reference = PublicBuildTask.model_validate(p["task"]), BuildReference.model_validate(p["reference"])
        if task.task_version != "main-build-v1" or reference.task_sha256 != _digest(task.model_dump(mode="json")) or digest(Path(p["source_archive"])) != task.source_archive_sha256:
            raise PlanContractError("源码、任务或独立检查不匹配：" + p["name"])
    for path, expected_hash in value["components"].items():
        if digest(ROOT / path) != expected_hash:
            raise PlanContractError("固定组件变化：" + path)
    for name, version in value["package_versions"].items():
        if importlib.metadata.version(name) != version:
            raise PlanContractError("运行依赖变化：" + name)


def plan_once(*, item, folder, model, available, deadline, accepted_models=shared.MODELS):
    """共同规划只读源码，不创建容器或接触独立参考。失败仍保存全部模型用量。"""
    folder.mkdir(parents=True, exist_ok=False)
    task = PublicBuildTask.model_validate(item["task"])
    source = folder / "source"
    source.mkdir()
    with tarfile.open(item["source_archive"]) as archive:
        archive.extractall(source, filter="data")
    names = [p.name for p in sorted(source.iterdir()) if p.is_file() and (p.name.lower().startswith(("readme", "install")) or p.name in {"CMakeLists.txt", "Makefile", "configure.ac", "meson.build"})][:8]
    packet = dict(task=task.model_dump(mode="json"), source_packet=source_packet(source, names))
    save(folder / "common-public-task.json", packet["task"])
    meter = SimpleBuildMeter(PlanAgentLedger(folder / "agent"), accepted_models=accepted_models, deadline=deadline, packet=lambda: packet, maximum_cost_usd=str(available))
    started = time.monotonic()
    result = dict(status="started", cleanup=dict(succeeded=True, reason="只读宿主规划，无容器"))
    try:
        plan, reason = propose_simple(model=model, task=task, source_root=source, session_root=folder, meter=meter)
        save(folder / "initial-plan.json", plan.model_dump(mode="json"))
        result.update(status="planned", plan=plan.model_dump(mode="json"), plan_sha256=plan.fingerprint(), reason=reason)
    except Exception as exc:
        result.update(status="planning_failed", error_type=type(exc).__name__, error=str(exc))
    finally:
        result.update(agent_usage=meter.summary(), arm_total_wall_seconds=time.monotonic() - started)
        save(folder / "result.json", result)
    return result


def execute(value, output, auth, planner, executor):
    """按项目一次共同规划、两个干净处理；任何正式尝试均不重启或补槽。"""
    output.mkdir(parents=True, exist_ok=False)
    save(output / "protocol.json", value)
    save(output / "authorization.json", auth)
    rows, plans, blocked = [], [], {}
    stop, inflight = None, None
    cap = Decimal(auth["maximum_cost_usd"])
    started = time.monotonic()

    def spent():
        return sum((shared.usage(r)["cost"] for r in plans + rows), Decimal(0))

    def admit():
        if cap - spent() < Decimal("0.10"):
            raise PlanContractError("shared_budget")
        OperationWindow(auth["deadline_utc"]).admit("new_unit", 900)

    try:
        for item in value["projects"]:
            admit()
            folder = output / "initial" / item["name"]
            inflight = dict(kind="initial", project=item["name"], folder=str(folder))
            initial = planner(item=item, folder=folder, available=min(Decimal(value["per_unit_cost_usd"]), cap - spent()), deadline=auth["deadline_utc"])
            plans.append(initial | dict(project=item["name"]))
            inflight = None
            save(output / "initial-progress.json", plans)
            stop = shared.global_stop(initial, folder)
            if stop:
                break
            if initial["status"] != "planned":
                blocked[item["name"]] = "shared_initial_planning_failed; recovery_not_observed"
                continue
            initial_plan = SimpleBuildPlan.model_validate(initial["plan"])
            if initial_plan.task.model_dump(mode="json") != item["task"] or initial_plan.fingerprint() != initial["plan_sha256"]:
                raise PlanContractError("共同初始方案不属于当前任务或哈希改变")
            for slot in [s for s in value["schedule"] if s["project"] == item["name"]]:
                admit()
                folder = output / f"slot-{slot['slot']:02d}-{slot['project']}-{slot['method']}"
                inflight = dict(kind="comparison", **slot, folder=str(folder))
                row = executor(slot=slot, item=item, folder=folder, available=min(Decimal(value["per_unit_cost_usd"]), cap - spent()), deadline=auth["deadline_utc"], initial_plan=initial_plan.model_dump(mode="json"))
                rows.append(row | slot | dict(initial_plan_sha256=initial["plan_sha256"]))
                inflight = None
                save(output / "progress.json", rows)
                stop = shared.global_stop(row, folder)
                if stop or spent() > cap:
                    stop = stop or "shared_budget_exceeded"
                    break
            if stop:
                break
    except PlanContractError as exc:
        stop = str(exc)
        save(output / "runner-failure.json", dict(type=type(exc).__name__, message=str(exc)))
    except BaseException as exc:
        stop = "runner_exception:" + type(exc).__name__
        save(output / "runner-failure.json", dict(type=type(exc).__name__, message=str(exc)))
        raise
    finally:
        observed = {r["slot"] for r in rows}
        unseen = [s | dict(status="unobserved", reason=blocked.get(s["project"], stop)) for s in value["schedule"] if s["slot"] not in observed]
        result = dict(
            identity=value["identity"],
            rows=rows,
            common_initial_plans=plans,
            unobserved=unseen,
            stop_reason=stop,
            unclosed_unit=inflight,
            expected_slots=len(value["schedule"]),
            completed_slots=len(rows),
            known_actual_batch_cost_usd=str(spent()),
            billing_complete=inflight is None and not any(shared.usage(r)["unknown"] for r in plans + rows),
            batch_wall_seconds=time.monotonic() - started,
        )
        save(output / "result.json", result)
    return result


def paid_callbacks(value, auth):
    # main已核验新身份/候选/预算/时窗；不读取或请求RichLab/Jev。
    from dotenv import load_dotenv

    load_dotenv(auth["credentials_env_file"], override=False)
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise PlanContractError("既有DeepSeek凭据不可用")
    model = PlanThinkingDeepSeek(model="deepseek-flash", api_key=key, base_url="https://api.deepseek.com", max_tokens=32768, max_retries=0, timeout=240, reasoning_effort="low", extra_body={"thinking": {"type": "enabled"}})
    hs = {n: RecoveryHarness.model_validate(h) for n, h in value["recovery_harnesses"].items()}

    def end(deadline, seconds):
        return min(datetime.fromisoformat(deadline), datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()

    def planner(**kwargs):
        kwargs["deadline"] = end(kwargs["deadline"], value["planning_seconds"])
        return plan_once(model=model, **kwargs)

    def executor(*, slot, item, folder, available, deadline, initial_plan):
        return shared.run_simple_system(
            task=PublicBuildTask.model_validate(item["task"]),
            reference=BuildReference.model_validate(item["reference"]),
            source_archive=Path(item["source_archive"]),
            output_root=folder,
            method="forge",
            model=model,
            accepted_models=shared.MODELS,
            family=item["family"],
            deadline=end(deadline, value["arm_seconds"]),
            maximum_cost_usd=str(available),
            initial_plan=initial_plan,
            recovery_harness=hs[slot["method"]],
            state_router=BuildStateRouter(method="rule", directory=folder / "state-routing"),
            validation_scope="main_build",
            replay_seconds=value["replay_seconds"],
        )

    return planner, executor


def event_counts(folder):
    path = folder / "agent/events.jsonl"
    counts, seen = Counter(), set()
    for event in map(json.loads, path.read_text().splitlines()) if path.exists() else []:
        if event["event"] == "agent.started":
            counts["recovery_invocations"] += bool(event.get("recovery"))
        elif event["event"] == "tool.started" and event.get("name") in {"read_source", "list_source"}:
            key = (event["name"], _digest(event.get("args", {})))
            counts[event["name"]] += 1
            counts["exact_repeat_reads"] += key in seen
            seen.add(key)
        elif event["event"] == "simple.proposal_accepted":
            counts["corrections"] += event.get("corrections", 0)
    return dict(counts)


def analyze(output):
    result = shared.load(output / "result.json")
    plans = {r["project"]: r for r in result["common_initial_plans"]}
    arms = {}
    for method in METHODS:
        rows = [r for r in result["rows"] if r["method"] == method]
        eligible = {r["project"] for r in rows}
        initial_cost = sum((shared.usage(p)["cost"] for p in plans.values()), Decimal(0))
        recovery_cost = sum((shared.usage(r)["cost"] for r in rows), Decimal(0))
        arms[method] = dict(
            planned=18,
            observed=len(rows),
            unobserved=18 - len(rows),
            main_build_completed=sum(r.get("layers", {}).get("main_build_task_completed") is True for r in rows),
            reproducible_delivery_completed=sum(r.get("layers", {}).get("reproducible_delivery_completed") is True for r in rows),
            recovery_requests=sum(shared.usage(r)["requests"] for r in rows),
            recovery_online_cost_usd=str(recovery_cost),
            common_planning_all_attempted_projects_cost_usd=str(initial_cost),
            deployment_cost_usd=str(initial_cost + recovery_cost),
            deployment_with_proposal_usd=str(initial_cost + recovery_cost + (Decimal(PROPOSAL_COST) if method == "R1" else Decimal(0))),
            execution_wall_seconds=sum(r.get("arm_total_wall_seconds", 0) for r in rows),
            recovery_agent_seconds=sum(r.get("timings", {}).get("recovery_agent_seconds", 0) for r in rows),
            common_planning_wall_seconds=sum(p.get("arm_total_wall_seconds", 0) for p in plans.values()),
            common_planning_requests=sum(shared.usage(p)["requests"] for p in plans.values()),
            observed_projects=sorted(eligible),
        )
    details = []
    for r in result["rows"]:
        folder = output / f"slot-{r['slot']:02d}-{r['project']}-{r['method']}"
        details.append(
            dict(
                slot=r["slot"],
                project=r["project"],
                method=r["method"],
                status=r["status"],
                layers=r.get("layers"),
                timings=r.get("timings"),
                recovery_behavior=event_counts(folder),
                initial_plan_sha256=r["initial_plan_sha256"],
                error=r.get("error"),
            )
        )
    pairs = []
    for name in plans:
        matched = [r for r in result["rows"] if r["project"] == name]
        complete = len(matched) == 2
        pairs.append(dict(project=name, methods=[r["method"] for r in matched], complete_pair=complete, same_initial_plan=len({r["initial_plan_sha256"] for r in matched}) == 1 if complete else None))
    by_name = {p["name"]: p for p in shared.load(output / "protocol.json")["projects"]}
    stratified = {}
    for system in ("cmake", "make", "autotools"):
        stratified[system] = {}
        for method in METHODS:
            matched = [r for r in result["rows"] if r["method"] == method and by_name[r["project"]]["task"]["build_system"] == system]
            stratified[system][method] = dict(
                planned=6,
                observed=len(matched),
                main_build_completed=sum(r.get("layers", {}).get("main_build_task_completed") is True for r in matched),
                reproducible_delivery_completed=sum(r.get("layers", {}).get("reproducible_delivery_completed") is True for r in matched),
                recovery_requests=sum(shared.usage(r)["requests"] for r in matched),
                recovery_cost_usd=str(sum((shared.usage(r)["cost"] for r in matched), Decimal(0))),
            )
    return dict(
        identity=IDENTITY,
        arms=arms,
        details=details,
        pairs=pairs,
        common_initial_plans=[dict(project=n, status=r["status"], usage=r["agent_usage"]) for n, r in plans.items()],
        actual_batch_cost_usd=result["known_actual_batch_cost_usd"] if result["billing_complete"] else None,
        known_actual_batch_cost_usd=result["known_actual_batch_cost_usd"],
        billing_complete=result["billing_complete"],
        by_build_system=stratified,
        common_initial_failures=[name for name, record in plans.items() if record["status"] != "planned"],
        unobserved=result["unobserved"],
        historical_proposal_cost_usd=PROPOSAL_COST,
        historical_source_cost_usd=None,
        historical_source_cost_boundary="历史来源投入非本轮新增；未重新分摊，不声称已核清完整生命周期费用",
        boundary="共同规划实际只支付一次，各方法独立部署按全额计入；未启动不填失败；只在本轮自然失败上解释恢复效果；结果待用户审核，不自动写论文",
    )


def verify_runtime(output):
    """三系统各一条作者路径及一对受控恢复；不作模型效果比较。"""
    from forge_simple_system import ScriptedSimpleModel

    from deerflow.compile.simple_build_task import SimpleBuildActions, assemble_simple_plan

    output.mkdir(parents=True, exist_ok=False)
    save(
        output / "scope.json",
        dict(
            identity="cpp-build-recovery-harness-runtime-check-v1",
            kind="zero_provider_engineering",
            provider_calls=0,
            maximum_cost_usd="0",
            authorization="用户要求比较实现；必要零费用真实构建",
            automatic_retry=False,
            code_sha256=digest(Path(__file__)),
        ),
    )
    items = {p["name"]: p for p in shared.load(FIXTURE)["projects"]}
    hs, rows = harnesses(), []
    for name, method, controlled in (("cglm", "H0", False), ("massdns", "H0", False), ("libmodbus", "H0", False), ("massdns", "H0", True), ("massdns", "R1", True)):
        item = items[name]
        task = PublicBuildTask.model_validate(item["task"])
        actions = SimpleBuildActions.model_validate(item["reference_actions"])
        plan = assemble_simple_plan(task, actions)
        if controlled:
            plan = plan.model_copy(update=dict(steps=(plan.steps[-1].model_copy(update=dict(command="make forge_missing_target")),)))
        folder = output / (name + "-" + method + ("-controlled" if controlled else "-reference"))
        model = ScriptedSimpleModel(responses=[], calls=[dict(name="SimpleBuildActions", args=actions.model_dump(mode="json"))] if controlled else [])
        result = shared.run_simple_system(
            task=task,
            reference=BuildReference.model_validate(item["reference"]),
            source_archive=Path(item["source_archive"]),
            output_root=folder,
            method="forge",
            model=model,
            accepted_models=("zero-provider-script",),
            family=item["family"],
            initial_plan=plan.model_dump(mode="json"),
            recovery_harness=hs[method],
            validation_scope="main_build",
            replay_seconds=600,
        )
        row = result | dict(project=name, method=method, controlled=controlled, initial_plan_sha256=plan.fingerprint(), folder=str(folder))
        rows.append(row)
        print(name, method, controlled, result.get("layers"), flush=True)
        if not result.get("cleanup", {}).get("succeeded"):
            break
    summary = dict(identity="cpp-build-recovery-harness-runtime-check-v1", rows=rows, provider_calls=0, estimated_cost_usd="0", boundary="作者参考及受控脚本恢复只证明比较入口实现，不是自然恢复或R1效果")
    save(output / "result.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--check-prepared", action="store_true")
    group.add_argument("--run", action="store_true")
    group.add_argument("--analyze", type=Path)
    group.add_argument("--verify-runtime", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.analyze:
        print(json.dumps(analyze(args.analyze), ensure_ascii=False, indent=2))
        return
    if args.verify_runtime:
        verify_runtime(args.verify_runtime.resolve())
        return
    if args.prepare:
        if MANIFEST.exists():
            raise PlanContractError("不覆盖已冻结身份")
        save(MANIFEST, candidate())
    value = shared.load(MANIFEST)
    validate(value)
    if not args.run:
        print(json.dumps(dict(valid=True, identity=IDENTITY, candidate_sha256=digest(MANIFEST), projects=18, slots=36, common_planning_tasks=18, provider_calls=0, credentials_read=False)))
        return
    if not args.authorization or not args.output:
        parser.error("正式运行需要--authorization和独立--output")
    if args.output.exists():
        raise PlanContractError("输出目录已存在，不续跑或重新封存旧身份")
    auth = shared.load(args.authorization)
    shared.validate_authorization(auth, digest(MANIFEST), identity=IDENTITY, maximum_hours=4)
    if Decimal(auth["maximum_cost_usd"]) > Decimal(value["maximum_cost_usd"]):
        raise PlanContractError("比较总预算不能超过5美元")
    OperationWindow(auth["deadline_utc"]).admit("comparison", 900)
    callbacks = paid_callbacks(value, auth)
    try:
        execute(value, args.output, auth, *callbacks)
    finally:
        if (args.output / "result.json").exists():
            save(args.output / "analysis.json", analyze(args.output))
            result = shared.load(args.output / "result.json")
            unknown = sum(shared.usage(r)["unknown"] for r in result["rows"] + result["common_initial_plans"]) + int(result["unclosed_unit"] is not None)
            seal(args.output, value, ROOT, unknown_usage_requests=unknown)


if __name__ == "__main__":
    main()
