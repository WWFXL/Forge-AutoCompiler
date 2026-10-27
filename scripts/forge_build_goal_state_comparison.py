#!/usr/bin/env python3
"""同任务、同模型、同验收的配置状态增强配对比较；准备不读取凭据。"""

from __future__ import annotations

import argparse
import copy
import json
import signal
import sys
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import forge_build_flash_paper_experiments as flash
import forge_build_strategy_replication as replication
from langchain_core.messages import SystemMessage

from deerflow.compile.goal_state import GoalStateWorkflow, configuration_goals, goal_state_planner

base, bounded = replication.base, replication.bounded
ROOT = base.ROOT
IDENTITY = "cpp-build-goal-state-paired-flash-v1"
PARENT = "benchmarks/manifests/cpp-build-strategy-replication-v1.json"
PREREGISTRATION = "benchmarks/preregistrations/" + IDENTITY + ".md"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
METHODS = ("current_model_workflow", "goal_state_model_workflow")


@dataclass(frozen=True)
class TimingPolicy:
    node_seconds: int = 1200
    replay_seconds: int = 1200
    cleanup_reserve_seconds: int = 300
    request_reserve_seconds: int = 600

    @property
    def new_slot_reserve_seconds(self):
        return self.node_seconds + self.replay_seconds + self.cleanup_reserve_seconds


TIMING = TimingPolicy()


def schedule():
    return [dict(project=name, repetition=repetition, method=method) for repetition in (1, 2) for index, name in enumerate(replication.PROJECTS) for method in (METHODS if (index + repetition) % 2 else tuple(reversed(METHODS)))]


def candidate_for():
    parent = base.load(ROOT / PARENT)
    candidate = copy.deepcopy(parent)
    candidate.update(
        identity=IDENTITY,
        issue=631,
        kind="paired_explicit_configuration_state_ablation",
        provider=flash.PROVIDER,
        pricing=flash.PRICING,
        schedule=schedule(),
        stage_max_cost_usd="10.00",
        parent_manifest=dict(path=PARENT, sha256=base.digest(ROOT / PARENT)),
        timing_policy={**asdict(TIMING), "new_slot_reserve_seconds": TIMING.new_slot_reserve_seconds},
        launch_state="prepared_requires_new_budget_and_time_authorization",
        treatment=dict(persistent_goals=True, after_configure_observation=True, before_build_observation=True, max_direct_configuration_revisions=1, unknown_or_dependency_probe="original_agent", final_acceptance_unchanged=True),
        interpretation_boundary="六个已见开发任务的组件增量；CMake显式配置为可观测作用范围，Make/Autotools保留原流程，不主张新项目泛化或纯单组件因果。",
    )
    candidate["runtime"] = {**parent["runtime"], "new_slot_reserve_seconds": TIMING.new_slot_reserve_seconds}
    candidate["configuration_goals"] = {item["name"]: [asdict(g) for g in configuration_goals(base.PlanTask.model_validate(item["task"]))] for item in candidate["projects"]}
    for name in ("backend/packages/harness/deerflow/compile/goal_state.py", "scripts/forge_build_goal_state_comparison.py", "scripts/forge_build_flash_paper_experiments.py", PREREGISTRATION):
        candidate["components"][name] = base.digest(ROOT / name)
    return candidate


def validate(candidate):
    if candidate != candidate_for():
        raise base.PlanContractError("候选、原任务或配对设计变化")
    for name, digest in candidate["components"].items():
        if base.digest(ROOT / name) != digest:
            raise base.PlanContractError("运行组件变化：" + name)
    for item in candidate["projects"]:
        if base.digest(Path(item["source_archive"])) != item["task"]["source_archive_sha256"]:
            raise base.PlanContractError("原源码归档变化")
        if candidate["source_index_contracts"][item["name"]] != replication.indexed.archive_index_contract(item["source_archive"]):
            raise base.PlanContractError("原文件或符号链接索引变化")


class GoalMeter(flash.FlashMeter):
    def __init__(self, *args, goals, **kwargs):
        packet = kwargs.pop("packet")
        super().__init__(*args, packet=lambda: {**packet(), "persistent_configuration_goals": [asdict(g) for g in goals]}, **kwargs)
        self.ledger.save("persistent-configuration-goals.json", [asdict(g) for g in goals])

    def wrap_model_call(self, request, handler):
        system = request.system_message
        prompt = (
            "\npersistent_configuration_goals来自原公开任务的显式约束，所有规划和恢复必须保持。"
            "configuration_state是实际执行后缓存观测，unknown不代表失败或满足。"
            "禁止通过强设HAVE_*等依赖探测变量伪造依赖就绪；应安装真实依赖并清缓存重配。继续使用原完整固定测试及精确交付。"
        )
        return super().wrap_model_call(request.override(system_message=SystemMessage(content=(system.content if system else "") + prompt)), handler)


def run_slot(*, protocol, slot, root, model):
    item = next(p for p in protocol["projects"] if p["name"] == slot["project"])
    enhanced = slot["method"] == METHODS[1]
    if slot["method"] not in METHODS:
        raise base.PlanContractError("未知配对方法")
    original_planner = base.observed_module.observed_planner

    def planner_factory(*args, **kwargs):
        return goal_state_planner(original_planner(*args, **kwargs))

    def meter_factory(*args, **kwargs):
        if enhanced:
            return GoalMeter(*args, goals=configuration_goals(base.PlanTask.model_validate(item["task"])), **kwargs)
        return flash.FlashMeter(*args, **kwargs)

    # 所有修改仅在本槽有效，旧实现和冻结组件保持原字节。
    with (
        patch.object(base, "PreparationMeter", meter_factory),
        patch.object(base, "execution_window", bounded.execution_window),
        patch.object(base.prepared_module, "PreparedWorkflow", GoalStateWorkflow if enhanced else base.prepared_module.PreparedWorkflow),
        patch.object(base.observed_module, "observed_planner", planner_factory if enhanced else original_planner),
    ):
        row = replication.run_slot(protocol=protocol, slot={**slot, "method": "model_plan_workflow"}, root=root, model=model)
    return {**row, **slot, "configuration_scope": "explicit_cmake_configuration_only"}


def execute(protocol, root, model, rows):
    for index, slot in enumerate(protocol["schedule"], 1):
        if bounded.STOP_REQUESTED:
            return "operator_or_deadline_stop"
        try:
            base.OperationWindow(protocol["deadline_utc"]).admit("new_slot", TIMING.new_slot_reserve_seconds)
        except base.PlanContractError:
            return "new_slot_time_reservation"
        if sum(base.charges(rows)) + Decimal("3.00") > Decimal(protocol["stage_max_cost_usd"]):
            return "stage_cost_reservation"
        folder = root / f"slot-{index}"
        folder.mkdir()
        row = run_slot(protocol=protocol, slot=slot, root=folder, model=model)
        rows.append(row)
        base.write_json(root / f"progress-{index}.json", row)
        print(json.dumps(dict(slot=index, project=slot["project"], method=slot["method"], strict=row["strict_completed"], error=row.get("error_message"), usage=row["agent_usage"]), ensure_ascii=False), flush=True)
        if not row["cleanup"]["succeeded"] or row["agent_usage"]["unknown_usage_requests"]:
            return "cleanup_or_unknown_usage"
        if Decimal(str(row["agent_usage"]["estimated_cost_usd_completed_responses"])) > Decimal("3.00"):
            return "cost_contract_violation"
        if any(json.loads(line)["event"] == "model.identity_mismatch" for path in folder.glob("*/agent/events.jsonl") for line in path.read_text().splitlines()):
            return "provider_identity_mismatch"
        if row.get("error_class") not in (None, "PlanContractError", "ValueError", "AgentWorkflowBudgetExceeded", "ValidationError", "StructuredOutputValidationError", "GraphRecursionError"):
            return "unexpected_runtime_error"
    return None


def analyze(root: Path):
    result = base.load(root / "result.json")
    methods = {}
    for method in METHODS:
        rows = [r for r in result["rows"] if r["method"] == method]
        methods[method] = dict(
            observed=len(rows),
            strict_completed=sum(r["strict_completed"] for r in rows),
            model_requests=sum(r["agent_usage"]["model_requests"] for r in rows),
            estimated_cost_usd=str(sum((Decimal(str(r["agent_usage"]["estimated_cost_usd_completed_responses"])) for r in rows), Decimal(0))),
            wall_seconds=sum(r["arm_total_wall_seconds"] for r in rows),
        )
    details = []
    for index, row in enumerate(result["rows"], 1):
        folder = root / f"slot-{index}"
        sessions = list(folder.glob("*/.compile-sessions/*/*/session.json"))
        state = base.load(sessions[0]) if len(sessions) == 1 else {}
        events = [json.loads(line) for path in folder.glob("*/agent/events.jsonl") for line in path.read_text().splitlines()]
        actions = [event for event in events if event["event"] == "goal_state.action"]
        error = row.get("error_message") or ""
        category = "completed" if row["strict_completed"] else "time_censored" if any(term in error for term in ("operation_window", "时限", "deadline_stop")) else "requires_failure_review"
        details.append(
            dict(
                project=row["project"],
                repetition=row["repetition"],
                method=row["method"],
                status=row["status"],
                terminal_category=category,
                original_build_commands=sum(c["role"] == "build" for c in state.get("commands", [])),
                direct_configuration_revisions=sum(a["action"] == "direct_configuration_revision" for a in actions),
                agent_recovery_episodes=sum(e["event"] == "agent.started" and e.get("recovery") is True for e in events),
                error=error,
            )
        )
    pairs = []
    for repetition in (1, 2):
        for project in replication.PROJECTS:
            rows = {r["method"]: r for r in result["rows"] if r["project"] == project and r["repetition"] == repetition}
            pairs.append(dict(project=project, repetition=repetition, fully_observed=len(rows) == 2, outcomes={k: v["strict_completed"] for k, v in rows.items()}))
    # 报告原始false而不把它直接解释为方法失败；时间截断需查逐槽停止原因。
    return dict(
        identity=IDENTITY,
        methods=methods,
        details=details,
        pairs=pairs,
        unobserved_schedule=result["unobserved_schedule"],
        stop_reason=result["stop_reason"],
        interpretation="已见任务的组件比较，false须结合失败/删失记录分类；不作总体排名或显著性主张",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--check-prepared", action="store_true")
    parser.add_argument("--analyze", type=Path)
    args, remaining = parser.parse_known_args()
    if args.prepare:
        if MANIFEST.exists():
            raise base.PlanContractError("候选已存在；不得覆盖冻结身份")
        candidate = candidate_for()
        validate(candidate)
        base.write_json(MANIFEST, candidate)
        print(json.dumps(dict(candidate=str(MANIFEST), slots=len(candidate["schedule"]), provider_calls=0, credentials_read=False)))
        return 0
    if args.check_prepared:
        validate(base.load(MANIFEST))
        print(json.dumps(dict(valid=True, provider_calls=0, credentials_read=False)))
        return 0
    if args.analyze:
        print(json.dumps(analyze(args.analyze), ensure_ascii=False, indent=2))
        return 0
    signal.signal(signal.SIGINT, bounded.request_stop)
    with patch.object(sys, "argv", [sys.argv[0], *remaining]), patch.object(base, "PROVIDER", flash.PROVIDER), patch.object(base, "validate", validate), patch.object(base, "execute", execute):
        return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
