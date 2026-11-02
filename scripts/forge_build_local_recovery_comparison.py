#!/usr/bin/env python3
"""相同自然初始方案下比较方案返回与工具辅助局部恢复；准备不读取凭据。"""

from __future__ import annotations

import argparse
import copy
import json
import signal
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import forge_build_fixed_plan_state_increment as fixed
from forge_build_common_harness import common_harness_interfaces

from deerflow.compile.goal_state import GoalStateWorkflow, configuration_goals
from deerflow.compile.local_recovery import LocalRecoveryWorkflow, run_local_agent

base, paired, component = fixed.base, fixed.paired, fixed.component
ROOT = base.ROOT
IDENTITY = "cpp-build-local-tool-recovery-comparison-flash-v1"
PARENT = fixed.MANIFEST.relative_to(ROOT).as_posix()
PREREGISTRATION = "benchmarks/preregistrations/" + IDENTITY + ".md"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
METHODS = ("plan_return", "local_tools")


def schedule(cases):
    return [
        dict(project=case["project"], case_id=case["case_id"], repetition=repetition, method=method)
        for repetition in (1, 2)
        for index, case in enumerate(cases)
        for method in (METHODS if (index + repetition) % 2 else tuple(reversed(METHODS)))
    ]


def candidate_for():
    parent = base.load(ROOT / PARENT)
    candidate = copy.deepcopy(parent)
    candidate.update(
        identity=IDENTITY,
        issue=655,
        kind="fixed_natural_plan_recovery_interface_comparison",
        parent_manifest=dict(path=PARENT, sha256=base.digest(ROOT / PARENT)),
        schedule=schedule(parent["cases"]),
        stage_max_cost_usd="10.00",
        proposed_runtime_hours=4,
        launch_state="prepared_requires_new_budget_and_time_authorization",
        treatment={
            "plan_return": dict(early_configuration_observation=True, direct_revision=False, repair="return_full_plan_then_workflow_executes"),
            "local_tools": dict(early_configuration_observation=True, direct_revision=False, repair="revise_plan_execute_to_local_goal_return_workflow"),
        },
        common_conditions="同初始方案/固定模型/源码镜像/任务材料/目标观测/全局命令Token时间预算/原测试/精确交付/干净重放/清理；无经验或联网。",
        cost_accounting="新增恢复的全部读取、输出、结构错误与失败请求均计费；相同历史初始规划费单列并加入比较总费，不重复计为新增支出。",
        interpretation_boundary="五份已见自然初始方案、三个CMake项目；沿用既有按配置状态分层的全部案例，不按本轮结果筛选。比较恢复工具与交互方式组合，不称纯控制器因果、自然错误率或新项目泛化。正常层也保留。",
    )
    for name in ("backend/packages/harness/deerflow/compile/local_recovery.py", "scripts/forge_build_local_recovery_comparison.py", PREREGISTRATION):
        candidate["components"][name] = base.digest(ROOT / name)
    return candidate


def validate(candidate):
    if candidate != candidate_for():
        raise base.PlanContractError("局部恢复比较的方案、任务、处理或组件变化")
    for name, expected in candidate["components"].items():
        if base.digest(ROOT / name) != expected:
            raise base.PlanContractError("冻结组件变化：" + name)
    for item in candidate["projects"]:
        if base.digest(Path(item["source_archive"])) != item["task"]["source_archive_sha256"]:
            raise base.PlanContractError("原源码变化")
        if candidate["source_index_contracts"][item["name"]] != paired.replication.indexed.archive_index_contract(item["source_archive"]):
            raise base.PlanContractError("原源码或链接索引变化")
        for case in candidate["cases"]:
            if case["project"] == item["name"]:
                fixed.checked_plan(case, base.PlanTask.model_validate(item["task"]))


def run_slot(*, protocol, slot, root, model, forbid_provider=False):
    if slot["method"] not in METHODS or (forbid_provider and model is not None):
        raise base.PlanContractError("未知恢复方式或零Provider检查传入模型")
    case = next(c for c in protocol["cases"] if c["case_id"] == slot["case_id"])
    if slot["project"] != case["project"]:
        raise base.PlanContractError("方案与项目不一致")
    item = next(p for p in protocol["projects"] if p["name"] == slot["project"])
    task = base.PlanTask.model_validate(item["task"])
    initial = fixed.checked_plan(case, task)

    def recover(workflow):
        if forbid_provider:
            workflow.meter.ledger.append("development.provider_forbidden", reason=workflow.handoff["reason"])
            raise base.PlanContractError("development_only_stop_before_provider：局部恢复已正确交接，不调用模型")
        run_local_agent(model=model, workflow=workflow, task=task, session_root=Path(workflow._session.metadata_path).parent)

    def workflow_factory(**kwargs):
        return LocalRecoveryWorkflow(recover=recover, **kwargs) if slot["method"] == "local_tools" else GoalStateWorkflow(**kwargs)

    with common_harness_interfaces():
        original = base.observed_module.observed_planner

        def planner_factory(*args, **kwargs):
            return fixed.fixed_planner(initial, original(*args, **kwargs), direct=False, forbid_provider=forbid_provider)

        def meter_factory(*args, **kwargs):
            return component.CommonGoalMeter(*args, goals=configuration_goals(task), **kwargs)

        with (
            patch.object(base, "PreparationMeter", meter_factory),
            patch.object(base, "execution_window", component.bounded.execution_window),
            patch.object(base.prepared_module, "PreparedWorkflow", workflow_factory),
            patch.object(base.observed_module, "observed_planner", planner_factory),
        ):
            row = paired.replication.run_slot(protocol=protocol, slot={**slot, "method": "model_plan_workflow"}, root=root, model=model)
    historical = case["historical_initial_planning"]
    return {
        **row,
        **slot,
        "kind": "zero_provider_engineering_dispatch_check" if forbid_provider else "real_model_fixed_plan_recovery_comparison",
        "initial_plan_sha256": initial.fingerprint(),
        "historical_initial_planning": historical,
        "comparable_total_estimated_cost_usd": str(Decimal(historical["estimated_cost_usd"]) + Decimal(str(row["agent_usage"]["estimated_cost_usd_completed_responses"]))),
        "historical_initial_cost_is_new_spending": False,
    }


def execute(protocol, root, model, rows):
    with patch.object(paired, "run_slot", run_slot):
        return paired.execute(protocol, root, model, rows)


def analyze(root):
    result = base.load(root / "result.json")
    details = []
    for index, row in enumerate(result["rows"], 1):
        folder = root / f"slot-{index}"
        events = [json.loads(line) for path in folder.glob("*/agent/events.jsonl") for line in path.read_text().splitlines()]
        state = base.load(next(folder.glob("*/.compile-sessions/*/*/session.json")))
        workflow_events = [json.loads(line) for path in folder.glob("*/.compile-sessions/*/*/logs/workflow.log") for line in path.read_text().splitlines()]
        command_rows = state["commands"]
        counts = {role: sum(c["role"] == role for c in command_rows) for role in ("dependency", "configure", "build", "smoke", "artifact_stage")}
        details.append(
            dict(
                **{k: row[k] for k in ("project", "case_id", "method", "repetition", "strict_completed", "arm_total_wall_seconds", "agent_usage", "comparable_total_estimated_cost_usd")},
                recovery_episodes=sum(e["event"] == "agent.started" and e.get("recovery") is True for e in events),
                local_returns=sum(e["event"] == "local_recovery.returned" for e in events),
                local_revisions=sum(e["event"] == "local_recovery.revised" for e in events),
                local_commands=sum(len(e.get("commands", [])) for e in events if e["event"] == "local_recovery.executed"),
                input_rejections=sum(e["event"] == "local_recovery.input_rejected" for e in events),
                command_counts=counts,
                repeated_build_executions=max(0, counts["build"] - 1),
                repeated_configure_executions=max(0, counts["configure"] - 1),
                source_unchanged=row.get("source_unchanged"),
                source_links_unchanged=row.get("source_links_unchanged"),
                replay_status=state["replay_attempts"][-1]["status"] if state.get("replay_attempts") else "unobserved",
                cleanup=row["cleanup"],
                error=row.get("error_message"),
                # 不把日志事件数当模型效果；仅留证据定位信息。
                workflow_log_events=len(workflow_events),
            )
        )
    summary = {}
    for method in METHODS:
        rows = [r for r in details if r["method"] == method]
        summary[method] = dict(
            observed=len(rows),
            strict_completed=sum(r["strict_completed"] for r in rows),
            requests=sum(r["agent_usage"]["model_requests"] for r in rows),
            new_cost_usd=str(sum((Decimal(str(r["agent_usage"]["estimated_cost_usd_completed_responses"])) for r in rows), Decimal(0))),
            total_with_historical_cost_usd=str(sum((Decimal(r["comparable_total_estimated_cost_usd"]) for r in rows), Decimal(0))),
            wall_seconds=sum(r["arm_total_wall_seconds"] for r in rows),
            recovery_episodes=sum(r["recovery_episodes"] for r in rows),
            local_returns=sum(r["local_returns"] for r in rows),
            build_executions=sum(r["command_counts"]["build"] for r in rows),
            repeated_build_executions=sum(r["repeated_build_executions"] for r in rows),
        )
    return dict(identity=result["identity"], summary=summary, slots=details, unobserved=result["unobserved_schedule"], stop_reason=result["stop_reason"])


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--check-prepared", action="store_true")
    parser.add_argument("--analyze", type=Path)
    args, remaining = parser.parse_known_args()
    if args.prepare:
        if MANIFEST.exists():
            raise base.PlanContractError("候选已存在，不能覆盖冻结身份")
        candidate = candidate_for()
        validate(candidate)
        base.write_json(MANIFEST, candidate)
        print(json.dumps(dict(identity=IDENTITY, slots=len(candidate["schedule"]), credentials_read=False, provider_calls=0)))
        return 0
    if args.check_prepared:
        validate(base.load(MANIFEST))
        print(json.dumps(dict(valid=True, credentials_read=False, provider_calls=0)))
        return 0
    if args.analyze:
        print(json.dumps(analyze(args.analyze.resolve()), ensure_ascii=False, indent=2))
        return 0
    signal.signal(signal.SIGINT, component.bounded.request_stop)
    with patch.object(sys, "argv", [sys.argv[0], *remaining]), patch.object(base, "PROVIDER", component.flash.PROVIDER), patch.object(base, "validate", validate), patch.object(base, "execute", execute):
        return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
