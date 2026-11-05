#!/usr/bin/env python3
"""固定初始方案的主构建规则/Jev路由比较；工程实跑不连接Provider。"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import forge_simple_comparison as shared
from forge_build_simple_task import save
from forge_simple_system import ScriptedSimpleModel, run_simple_system
from forge_typed_evidence import digest, seal

from deerflow.compile.build_state_routing import (
    JEV_MODEL,
    BuildStateRouter,
    JevStateSelector,
)
from deerflow.compile.operation_window import OperationWindow
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek
from deerflow.compile.plan_workflow import PlanContractError, _digest
from deerflow.compile.simple_build_task import (
    BuildReference,
    PublicBuildTask,
    SimpleBuildPlan,
)

ROOT = shared.ROOT
IDENTITY = "cpp-build-main-state-routing-comparison-v1"
FIXTURE = ROOT / "benchmarks/fixtures/main-build-state-routing-v1/tasks.json"
PREREG = ROOT / "benchmarks/preregistrations" / (IDENTITY + ".md")
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
METHODS = ("rule", "jev")
CAP, HOURS = Decimal("2.00"), 4


def schedule(projects):
    slots = []
    for repeat in range(2):
        for index, p in enumerate(projects):
            order = METHODS if (index + repeat) % 2 == 0 else METHODS[::-1]
            for method in order:
                slots.append(
                    dict(
                        slot=len(slots) + 1,
                        project=p["name"],
                        repetition=repeat + 1,
                        method=method,
                    )
                )
    return slots


def candidate():
    projects = shared.load(FIXTURE)["projects"]
    components = shared.runtime_files()
    components.update(
        {
            p.relative_to(ROOT).as_posix(): digest(p)
            for p in (Path(__file__).resolve(), PREREG, FIXTURE)
        }
    )
    return dict(
        identity=IDENTITY,
        issue=693,
        kind="fixed_plan_component_comparison",
        holdout=False,
        projects=projects,
        methods=list(METHODS),
        schedule=schedule(projects),
        components=components,
        task_scope="main_program_or_library_build_and_valid_artifact; author_tests_not_required",
        shared_candidates="author_cmake_requirement_upgrade; existing_configuration_restore; incomplete_output_observation; otherwise_agent",
        source_planning="历史首重复基础Forge的初始方案，全六项目不按结果挑选；来源费用另列并等额加入描述性部署费用，非新增请求",
        experience="disabled_both_arms",
        normal_path_jev_requests=0,
        provider=dict(
            build_model="deepseek-flash",
            accepted_build_models=list(shared.MODELS),
            jev_model=JEV_MODEL,
            jev_input_per_million_usd="0.042",
            jev_output_per_million_usd="0",
            max_retries=0,
        ),
        limits=dict(
            maximum_cost_usd=str(CAP),
            hours=HOURS,
            per_slot_cost_usd="0.40",
            per_slot_seconds=1200,
            maximum_local_actions=2,
            unknown_usage="stop_batch",
            identity_mismatch="stop_batch",
            cleanup_failure="stop_batch",
        ),
        boundary="旧六开发项目/旧自然初始方案的路由组件比较；正常样本保留，异常少时如实报告触发分母，不估未见泛化，不与旧完整作者测试分母合并。",
    )


def validate(value):
    if (
        value["identity"] != IDENTITY
        or value["methods"] != list(METHODS)
        or value["schedule"] != schedule(value["projects"])
        or len(value["schedule"]) != 24
    ):
        raise PlanContractError("比较身份或24次配对顺序变化")
    if value["projects"] != shared.load(FIXTURE)["projects"]:
        raise PlanContractError("固定项目/初始方案变化")
    for name, expected in value["components"].items():
        if digest(ROOT / name) != expected:
            raise PlanContractError("运行组件变化：" + name)
    for item in value["projects"]:
        task = PublicBuildTask.model_validate(item["task"])
        plan = SimpleBuildPlan.model_validate(item["initial_plan"])
        if (
            task.task_version != "main-build-v1"
            or plan.task != task
            or item["reference"]["task_sha256"] != _digest(task.model_dump(mode="json"))
            or digest(Path(item["source_archive"])) != task.source_archive_sha256
        ):
            raise PlanContractError("主构建任务/方案/源码/参考不一致")
        if digest(Path(item["source_plan"]["path"])) != item["source_plan"]["sha256"]:
            raise PlanContractError("历史初始方案来源变化")


def usage(row):
    result = dict(
        requests=0, input_tokens=0, output_tokens=0, cost=Decimal(0), unknown=0
    )
    for key in ("agent_usage", "router_usage"):
        u = row.get(key)
        if not u or u.get("estimated_cost_usd_completed_responses") is None:
            raise PlanContractError("Provider费用未闭合，不能填零")
        result["requests"] += u.get("model_requests", 0)
        result["input_tokens"] += u.get("input_tokens", 0)
        result["output_tokens"] += u.get("output_tokens", 0)
        result["cost"] += Decimal(str(u["estimated_cost_usd_completed_responses"]))
        result["unknown"] += u.get("unknown_usage_requests", 0)
    return result


def stop_reason(row, folder):
    if usage(row)["unknown"]:
        return "unknown_usage"
    if row.get("router_usage", {}).get("identity_mismatch"):
        return "jev_identity_mismatch"
    return shared.global_stop(row, folder)


def execute(value, output, auth, executor):
    output.mkdir(parents=True, exist_ok=False)
    save(output / "protocol.json", value)
    save(output / "authorization.json", auth)
    rows, stop, inflight = [], None, None
    start = time.monotonic()
    try:
        for slot in value["schedule"]:
            spent = sum((usage(r)["cost"] for r in rows), Decimal(0))
            remaining = Decimal(auth["maximum_cost_usd"]) - spent
            if remaining < Decimal("0.10"):
                stop = "shared_budget"
                break
            try:
                OperationWindow(auth["deadline_utc"]).admit("new_slot", 600)
            except PlanContractError:
                stop = "deadline"
                break
            item = next(p for p in value["projects"] if p["name"] == slot["project"])
            folder = (
                output / f"slot-{slot['slot']:02d}-{slot['project']}-{slot['method']}"
            )
            save(output / "current-slot.json", slot)
            inflight = slot
            row = executor(
                slot,
                item,
                folder,
                min(remaining, Decimal("0.40")),
                auth["deadline_utc"],
            )
            rows.append(row | slot)
            inflight = None
            save(output / "progress.json", rows)
            stop = stop_reason(row, folder)
            if stop:
                break
    except BaseException as exc:
        stop = "runner_exception:" + type(exc).__name__
        save(output / "runner-failure.json", dict(error_type=type(exc).__name__))
        raise
    finally:
        result = dict(
            identity=IDENTITY,
            rows=rows,
            unobserved=value["schedule"][len(rows) :],
            unclosed_slot=inflight,
            stop_reason=stop,
            batch_wall_seconds=time.monotonic() - start,
            new_estimated_cost_usd=str(
                sum((usage(r)["cost"] for r in rows), Decimal(0))
            ),
        )
        save(output / "result.json", result)
    return result


def run_slot(
    slot, item, folder, available, deadline, *, model, accepted_models, jev_client=None
):
    end = min(
        datetime.fromisoformat(deadline), datetime.now(UTC) + timedelta(seconds=1200)
    ).isoformat()
    selector = (
        JevStateSelector(
            client=jev_client, directory=folder / "router/provider", deadline=end
        )
        if slot["method"] == "jev"
        else None
    )
    router = BuildStateRouter(
        method=slot["method"], directory=folder / "router", selector=selector
    )

    def alarm(_signum, _frame):
        raise TimeoutError("单槽截止，保留失败且不重试")

    old = signal.signal(signal.SIGALRM, alarm)
    signal.alarm(
        max(
            1,
            int((datetime.fromisoformat(end) - datetime.now(UTC)).total_seconds()) - 60,
        )
    )
    try:
        return run_simple_system(
            task=PublicBuildTask.model_validate(item["task"]),
            reference=BuildReference.model_validate(item["reference"]),
            source_archive=Path(item["source_archive"]),
            output_root=folder,
            method="forge",
            model=model,
            accepted_models=accepted_models,
            family=item["family"],
            initial_plan=SimpleBuildPlan.model_validate(item["initial_plan"]),
            state_router=router,
            validation_scope="main_build",
            maximum_cost_usd=str(available),
            deadline=end,
            replay_seconds=240,
        )
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def analyze(output):
    value, result = (
        shared.load(output / "protocol.json"),
        shared.load(output / "result.json"),
    )
    summaries = {}
    for method in METHODS:
        rows = [r for r in result["rows"] if r["method"] == method]
        summaries[method] = dict(
            planned=12,
            observed=len(rows),
            unobserved=12 - len(rows),
            primary_completed=sum(
                r.get("layers", {}).get("primary_build_completed") is True for r in rows
            ),
            task_completed=sum(
                r.get("layers", {}).get("main_build_task_completed") is True
                for r in rows
            ),
            clean_replay_passed=sum(
                r.get("layers", {}).get("clean_replay") == "passed" for r in rows
            ),
            requests=sum(usage(r)["requests"] for r in rows),
            jev_requests=sum(r["router_usage"]["model_requests"] for r in rows),
            agent_requests=sum(r["agent_usage"]["model_requests"] for r in rows),
            estimated_cost_usd=str(sum((usage(r)["cost"] for r in rows), Decimal(0))),
            wall_seconds=sum(r["arm_total_wall_seconds"] for r in rows),
            triggered_slots=sum(r["router_usage"]["decision_count"] > 0 for r in rows),
            local_actions=sum(r["router_usage"]["local_actions"] for r in rows),
            agent_routes=sum(r["router_usage"]["agent_routes"] for r in rows),
        )
    return dict(
        identity=IDENTITY,
        summary=summaries,
        source_initial_planning_cost_usd=str(
            sum(
                (
                    Decimal(p["source_plan"]["initial_cost_usd"])
                    for p in value["projects"]
                ),
                Decimal(0),
            )
        ),
        boundary=value["boundary"],
        stop_reason=result["stop_reason"],
        unobserved=result["unobserved"],
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--prepare", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--engineering", choices=("jsoncpp", "double-conversion"))
    g.add_argument("--run", action="store_true")
    g.add_argument("--analyze", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--authorization", type=Path)
    args = p.parse_args()
    if args.analyze:
        print(json.dumps(analyze(args.analyze), ensure_ascii=False, indent=2))
        return 0
    if args.prepare:
        if MANIFEST.exists():
            raise PlanContractError("不能覆盖已准备身份")
        value = candidate()
        validate(value)
        save(MANIFEST, value)
    else:
        value = shared.load(MANIFEST)
        validate(value)
    if args.engineering:
        if args.output is None:
            p.error("工程实跑需要独立输出目录")
        item = next(i for i in value["projects"] if i["name"] == args.engineering)
        # 工程样例额外覆盖变量形式命令；不改变正式固定初始方案。
        if args.engineering == "jsoncpp":
            item = json.loads(json.dumps(item))
            item["initial_plan"]["steps"][-1]["command"] = (
                'CM=cmake; "$CM" --build build --parallel 2'
            )
        result = run_slot(
            dict(method="rule"),
            item,
            args.output,
            Decimal("0.40"),
            (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            model=ScriptedSimpleModel(responses=[], calls=[]),
            accepted_models=("zero-provider-script",),
        )
        print(
            json.dumps(
                dict(
                    project=item["name"],
                    layers=result.get("layers"),
                    router=result["router_usage"],
                    error=result.get("error"),
                ),
                ensure_ascii=False,
            )
        )
        return (
            0
            if result.get("layers", {}).get("main_build_task_completed")
            and result["layers"]["clean_replay"] == "passed"
            else 1
        )
    if not args.run:
        print(
            json.dumps(
                dict(
                    identity=IDENTITY,
                    valid=True,
                    slots=24,
                    candidate_sha256=digest(MANIFEST),
                    provider_calls=0,
                )
            )
        )
        return 0
    if args.authorization is None or args.output is None:
        p.error("正式运行需要具体授权文件与独立输出目录")
    auth = shared.load(args.authorization)
    shared.validate_authorization(
        auth, digest(MANIFEST), identity=IDENTITY, maximum_hours=HOURS
    )
    if Decimal(auth["maximum_cost_usd"]) > CAP:
        raise PlanContractError("本批助手自限2美元，不自动扩批")
    # 身份、预算、时窗及当前用户执行指令已在上述检查绑定后，才读取现有凭据。
    from dotenv import load_dotenv
    from typesafe_sdk import RetryPolicy, TypeSafeClient

    import forge_jev_action_safety_decomposition_v1 as existing_jev

    logging.getLogger("typesafe_sdk").disabled = True
    load_dotenv(auth["provider_env_file"], override=False)
    key = os.environ.get("DEEPSEEK_API_KEY")
    jev_key = (
        os.environ.get("TYPESAFE_API_KEY")
        or Path(auth["jev_key_file"]).read_text().strip()
    )
    if not key or not jev_key:
        raise PlanContractError("现有模型凭据不可用")
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
    with (
        existing_jev._provider_http_client() as http_client,
        TypeSafeClient(
            api_key=jev_key,
            model=JEV_MODEL,
            retry=RetryPolicy(max_retries=0, timeout=30),
            http_client=http_client,
            base_url="https://api.typesafe.ai",
        ) as client,
    ):
        try:
            execute(
                value,
                args.output,
                auth,
                lambda s, i, f, a, d: run_slot(
                    s,
                    i,
                    f,
                    a,
                    d,
                    model=model,
                    accepted_models=shared.MODELS,
                    jev_client=client,
                ),
            )
        finally:
            if (args.output / "result.json").exists():
                save(args.output / "analysis.json", analyze(args.output))
                result = shared.load(args.output / "result.json")
                seal(
                    args.output,
                    value,
                    ROOT,
                    unknown_usage_requests=sum(
                        usage(r)["unknown"] for r in result["rows"]
                    )
                    + bool(result["unclosed_slot"]),
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
