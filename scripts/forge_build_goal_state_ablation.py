#!/usr/bin/env python3
"""共同Harness修复后的三臂配置消融；准备模式不读取凭据。"""

from __future__ import annotations

import argparse
import copy
import json
import signal
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import forge_build_goal_state_comparison as paired
from forge_build_common_harness import common_harness_interfaces

from deerflow.compile.goal_state import GoalStateWorkflow, configuration_goals, goal_state_planner
from deerflow.compile.plan_candidate_reception import CandidateReceptionMixin

base, bounded, flash = paired.base, paired.bounded, paired.flash
ROOT = base.ROOT
IDENTITY = "cpp-build-goal-state-component-ablation-flash-v1"
PARENT = "benchmarks/manifests/cpp-build-goal-state-paired-flash-v1.json"
PREREGISTRATION = "benchmarks/preregistrations/" + IDENTITY + ".md"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PROJECTS = ("simdutf", "snappy", "yaml-cpp")
METHODS = ("common_model_workflow", "goals_only_model_workflow", "goals_state_model_workflow")


def schedule():
    return [dict(project=name, repetition=repetition, method=METHODS[index]) for repetition in (1, 2) for position, name in enumerate(PROJECTS) for index in base.ORDERS[position + 3 * (repetition - 1)]]


def candidate_for():
    parent = base.load(ROOT / PARENT)
    candidate = copy.deepcopy(parent)
    candidate.update(
        identity=IDENTITY,
        issue=633,
        kind="goal_presentation_and_configuration_feedback_component_ablation",
        schedule=schedule(),
        projects=[item for item in parent["projects"] if item["name"] in PROJECTS],
        source_index_contracts={name: parent["source_index_contracts"][name] for name in PROJECTS},
        configuration_goals={name: parent["configuration_goals"][name] for name in PROJECTS},
        parent_manifest=dict(path=PARENT, sha256=base.digest(ROOT / PARENT)),
        stage_max_cost_usd="10.00",
        launch_state="prepared_requires_new_budget_and_time_authorization",
        treatment={
            METHODS[0]: dict(persistent_goals=False, configuration_observation=False, direct_configuration_revision=False),
            METHODS[1]: dict(persistent_goals=True, configuration_observation=False, direct_configuration_revision=False),
            METHODS[2]: dict(persistent_goals=True, configuration_observation=True, direct_configuration_revision=True),
        },
        common_harness=dict(candidate_reception="tool_or_complete_json_v1", literal_factor_markers="preserve_literal_text_and_hash", original_schema_assembly_evaluator=True),
        interpretation_boundary="三个已见CMake任务；目标呈现与观察/选择闭环分离。每臂独立模型规划，不是同一初始方案反事实；闭环未触发时不声称直接动作效果。",
    )
    for name in ("backend/packages/harness/deerflow/compile/plan_candidate_reception.py", "scripts/forge_build_common_harness.py", "scripts/forge_build_goal_state_ablation.py", PREREGISTRATION):
        candidate["components"][name] = base.digest(ROOT / name)
    return candidate


def validate(candidate):
    if candidate != candidate_for():
        raise base.PlanContractError("三臂配置消融的任务、共同接口或组件变化")
    for name, digest in candidate["components"].items():
        if base.digest(ROOT / name) != digest:
            raise base.PlanContractError("冻结组件变化：" + name)
    for item in candidate["projects"]:
        if base.digest(Path(item["source_archive"])) != item["task"]["source_archive_sha256"]:
            raise base.PlanContractError("原源码归档变化")
        if candidate["source_index_contracts"][item["name"]] != paired.replication.indexed.archive_index_contract(item["source_archive"]):
            raise base.PlanContractError("原源码及链接索引变化")


class CommonFlashMeter(CandidateReceptionMixin, flash.FlashMeter):
    """控制臂使用同一候选接收与原始响应计量。"""


class CommonGoalMeter(CandidateReceptionMixin, paired.GoalMeter):
    """两目标臂使用相同目标材料和共同候选接收。"""


def run_slot(*, protocol, slot, root, model):
    method = slot["method"]
    if method not in METHODS:
        raise base.PlanContractError("未知消融臂")
    item = next(p for p in protocol["projects"] if p["name"] == slot["project"])
    goals, state = method != METHODS[0], method == METHODS[2]

    def meter_factory(*args, **kwargs):
        if goals:
            return CommonGoalMeter(*args, goals=configuration_goals(base.PlanTask.model_validate(item["task"])), **kwargs)
        return CommonFlashMeter(*args, **kwargs)

    with common_harness_interfaces():
        original = base.observed_module.observed_planner

        def planner_factory(*args, **kwargs):
            planner = original(*args, **kwargs)
            return goal_state_planner(planner) if state else planner

        with (
            patch.object(base, "PreparationMeter", meter_factory),
            patch.object(base, "execution_window", bounded.execution_window),
            patch.object(base.prepared_module, "PreparedWorkflow", GoalStateWorkflow if state else base.prepared_module.PreparedWorkflow),
            patch.object(base.observed_module, "observed_planner", planner_factory),
        ):
            row = paired.replication.run_slot(protocol=protocol, slot={**slot, "method": "model_plan_workflow"}, root=root, model=model)
    return {**row, **slot, "persistent_goals": goals, "configuration_observation": state, "common_candidate_reception": True}


def execute(protocol, root, model, rows):
    with patch.object(paired, "run_slot", run_slot):
        return paired.execute(protocol, root, model, rows)


def analyze(root):
    result = base.load(root / "result.json")
    summary = {}
    for method in METHODS:
        rows = [row for row in result["rows"] if row["method"] == method]
        summary[method] = dict(
            observed=len(rows),
            strict_completed=sum(row["strict_completed"] for row in rows),
            requests=sum(row["agent_usage"]["model_requests"] for row in rows),
            known_cost_usd=str(sum((Decimal(str(row["agent_usage"]["estimated_cost_usd_completed_responses"])) for row in rows), Decimal(0))),
            slot_seconds=sum(row["arm_total_wall_seconds"] for row in rows),
        )
    events = [json.loads(line) for path in root.glob("slot-*/*/agent/events.jsonl") for line in path.read_text().splitlines()]
    return dict(
        identity=result["identity"],
        summary=summary,
        unobserved=len(result["unobserved_schedule"]),
        stop_reason=result["stop_reason"],
        candidate_presentations=dict(Counter(event["presentation"] for event in events if event["event"] == "candidate.accepted")),
        direct_configuration_actions=sum(event["event"] == "goal_state.action" and event.get("action") == "direct_configuration_revision" for event in events),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--check-prepared", action="store_true")
    parser.add_argument("--analyze", type=Path)
    args, remaining = parser.parse_known_args()
    if args.prepare:
        if MANIFEST.exists():
            raise base.PlanContractError("候选已存在，不覆盖冻结身份")
        candidate = candidate_for()
        validate(candidate)
        base.write_json(MANIFEST, candidate)
        print(json.dumps(dict(identity=IDENTITY, slots=len(candidate["schedule"]), provider_calls=0, credentials_read=False)))
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
