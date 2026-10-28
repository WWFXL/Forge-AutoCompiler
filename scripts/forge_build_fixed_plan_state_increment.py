#!/usr/bin/env python3
"""固定自然初始方案，分离提前核对与直接动作的贡献；准备不读取凭据。"""

from __future__ import annotations

import argparse
import copy
import json
import signal
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import forge_build_goal_state_ablation as component
from forge_build_common_harness import common_harness_interfaces
from forge_typed_evidence import canonical, seal

from deerflow.compile.goal_state import (
    GoalStateWorkflow,
    configuration_goals,
    goal_state_planner,
)
from deerflow.compile.plan_workflow import BuildPlan
from deerflow.compile.unified_plan_equivalent import BuildActions, assemble_plan

base, paired = component.base, component.paired
ROOT = base.ROOT
IDENTITY = "cpp-build-fixed-plan-state-increment-flash-v1"
PARENT = component.MANIFEST.relative_to(ROOT).as_posix()
PREREGISTRATION = "benchmarks/preregistrations/" + IDENTITY + ".md"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
FIXTURES = ROOT / "benchmarks/fixtures/fixed-plan-state-increment-v1"
SELECTION = FIXTURES / "selection.json"
SOURCE_ROOT = Path(
    "/home/yiwei/.codex/outputs/forge-goal-state-component-ablation-flash-v1"
)
SOURCE_INVENTORY = "8e1b481aa8a059e46e4ef325a2a8fadeb6db27b482d9d723d4cfe3d66273955d"
METHODS = ("late_agent", "early_agent", "early_direct_agent")


def prior_configuration_class(row):
    """只看原初始执行的配置证据，不按最终恢复成败选择案例。"""
    first = row["transitions"][0]
    handoff = first.get("handoff") or {}
    if handoff.get("reason") == "configuration_goal_violated":
        return "deviated"
    if handoff.get("step_id") == "check" and any(
        "AssertionError: 配置功能不符:" in c.get("output_tail", "")
        for c in handoff.get("recent_commands", [])
    ):
        return "deviated"
    if first["status"] == "ready_for_verification":
        return "satisfied"
    return "other_initial_failure"


def historical_planning(events, session):
    initial, inputs, outputs, requests = True, 0, 0, 0
    for event in events:
        if event["event"] == "agent.started" and event.get("recovery") is True:
            initial = False
        if initial and event["event"] == "model.request_completed":
            inputs += event["input_tokens"]
            outputs += event["output_tokens"]
            requests += 1
    commands = session["commands"]
    interval = (
        datetime.fromisoformat(commands[1]["started_at"])
        - datetime.fromisoformat(commands[0]["completed_at"])
    ).total_seconds()
    cost = (
        Decimal(inputs) * Decimal("0.30") + Decimal(outputs) * Decimal("1.20")
    ) / 1_000_000
    return dict(
        model_requests=requests,
        input_tokens=inputs,
        output_tokens=outputs,
        recorded_tokens=inputs + outputs,
        estimated_cost_usd=str(cost),
        historical_planning_boundary_seconds=interval,
    )


def select_cases():
    if SELECTION.exists():
        raise base.PlanContractError("选择已固定，不覆盖原案例")
    inventory = base.load(SOURCE_ROOT / "inventory.json")
    if (
        canonical(inventory) != SOURCE_INVENTORY
        or base.load(SOURCE_ROOT / "seal.json")["inventory_canonical_sha256"]
        != SOURCE_INVENTORY
    ):
        raise base.PlanContractError("原18槽证据指针变化")
    index = {r["path"]: r for r in inventory}

    def read_original(path):
        relative = path.relative_to(SOURCE_ROOT).as_posix()
        if base.digest(path) != index[relative]["sha256"]:
            raise base.PlanContractError("所用原证据变化：" + relative)
        return base.load(path)

    result = read_original(SOURCE_ROOT / "result.json")
    candidates, selected = [], []
    for number, row in enumerate(result["rows"], 1):
        candidates.append(
            dict(
                slot=number,
                project=row["project"],
                original_method=row["method"],
                configuration_class=prior_configuration_class(row),
            )
        )
    # 每项目/状态取最早槽；保留全部18份候选的选择登记，正常组也必须存在。
    for project in component.PROJECTS:
        for category in ("deviated", "satisfied"):
            matches = [
                r
                for r in candidates
                if r["project"] == project and r["configuration_class"] == category
            ]
            if not matches:
                continue
            record = matches[0]
            folder = SOURCE_ROOT / f"slot-{record['slot']}" / (project + "-plan")
            path = folder / "agent/plan-1.json"
            plan = read_original(path)
            events_path = folder / "agent/events.jsonl"
            if (
                base.digest(events_path)
                != index[events_path.relative_to(SOURCE_ROOT).as_posix()]["sha256"]
            ):
                raise base.PlanContractError("原模型事件变化")
            events = [json.loads(line) for line in events_path.read_text().splitlines()]
            session_path = next(folder.glob(".compile-sessions/*/*/session.json"))
            session = read_original(session_path)
            case_id = f"{project}-{category}"
            target = FIXTURES / (case_id + ".json")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as handle:
                handle.write(path.read_bytes())
            selected.append(
                dict(
                    **record,
                    case_id=case_id,
                    plan_path=target.relative_to(ROOT).as_posix(),
                    plan_sha256=base.digest(target),
                    original_plan_path=path.relative_to(SOURCE_ROOT).as_posix(),
                    original_events_path=events_path.relative_to(
                        SOURCE_ROOT
                    ).as_posix(),
                    original_events_sha256=base.digest(events_path),
                    original_session_path=session_path.relative_to(
                        SOURCE_ROOT
                    ).as_posix(),
                    original_session_sha256=base.digest(session_path),
                    historical_initial_planning=historical_planning(events, session),
                    plan_fingerprint=BuildPlan.model_validate(plan).fingerprint(),
                )
            )
    base.write_json(
        SELECTION,
        dict(
            source_identity=result["identity"],
            source_root=str(SOURCE_ROOT),
            source_inventory_sha256=SOURCE_INVENTORY,
            selection_rule="each_project_first_slot_per_prior_configuration_class",
            all_candidates=candidates,
            cases=selected,
            boundary="事后按已观察配置状态分层的机制案例；不是自然发生率、未见任务或总体效果样本",
        ),
    )


def schedule(cases):
    return [
        dict(
            project=case["project"],
            case_id=case["case_id"],
            repetition=repetition,
            method=METHODS[i],
        )
        for repetition in (1, 2)
        for position, case in enumerate(cases)
        for i in base.ORDERS[(position + 3 * (repetition - 1)) % 6]
    ]


def candidate_for():
    parent = base.load(ROOT / PARENT)
    selection = base.load(SELECTION)
    candidate = copy.deepcopy(parent)
    candidate.update(
        identity=IDENTITY,
        issue=637,
        kind="fixed_natural_plan_configuration_timing_and_action_ablation",
        schedule=schedule(selection["cases"]),
        parent_manifest=dict(path=PARENT, sha256=base.digest(ROOT / PARENT)),
        cases=selection["cases"],
        case_selection=dict(
            path=SELECTION.relative_to(ROOT).as_posix(),
            sha256=base.digest(SELECTION),
            source_inventory_sha256=SOURCE_INVENTORY,
        ),
        treatment={
            METHODS[0]: dict(
                persistent_goals=True, early_observation=False, direct_revision=False
            ),
            METHODS[1]: dict(
                persistent_goals=True, early_observation=True, direct_revision=False
            ),
            METHODS[2]: dict(
                persistent_goals=True, early_observation=True, direct_revision=True
            ),
        },
        cost_accounting="历史初始规划相同计入每个配对臂的分析总费；新增预算只扣本轮真实恢复请求，历史请求不重复收费。时间主指标为新鲜执行到完整验收及清理；历史规划边界间隔单列。",
        interpretation_boundary=selection["boundary"],
        launch_state="prepared_requires_new_budget_and_time_authorization",
    )
    for name in (
        "scripts/forge_build_fixed_plan_state_increment.py",
        PREREGISTRATION,
        SELECTION.relative_to(ROOT).as_posix(),
        *(c["plan_path"] for c in selection["cases"]),
    ):
        candidate["components"][name] = base.digest(ROOT / name)
    return candidate


def checked_plan(case, task):
    path = ROOT / case["plan_path"]
    if base.digest(path) != case["plan_sha256"]:
        raise base.PlanContractError("固定初始方案变化")
    plan = BuildPlan.model_validate(base.load(path))
    core = BuildActions(
        reason="固定原初始方案，不重采样",
        steps=[
            s.model_dump()
            for s in plan.steps
            if s.role in ("dependency", "configure", "build")
        ],
    )
    if (
        plan.revision != 1
        or assemble_plan(task, core, revision=1) != plan
        or plan.fingerprint() != case["plan_fingerprint"]
    ):
        raise base.PlanContractError("初始方案的任务、测试、交付或身份变化")
    return plan


def validate(candidate):
    if candidate != candidate_for():
        raise base.PlanContractError("固定方案比较的样本、组件或处理变化")
    for name, digest in candidate["components"].items():
        if base.digest(ROOT / name) != digest:
            raise base.PlanContractError("冻结组件变化：" + name)
    for item in candidate["projects"]:
        if (
            base.digest(Path(item["source_archive"]))
            != item["task"]["source_archive_sha256"]
        ):
            raise base.PlanContractError("固定源码变化")
        task = base.PlanTask.model_validate(item["task"])
        for case in candidate["cases"]:
            if case["project"] == item["name"]:
                checked_plan(case, task)


def fixed_planner(initial, original, *, direct, forbid_provider=False):
    def dispatch(**kwargs):
        if kwargs.get("current_plan") is None:
            kwargs["meter"].ledger.save("plan-1.json", initial.model_dump(mode="json"))
            kwargs["meter"].ledger.append(
                "fixed_plan.reused",
                plan_sha256=initial.fingerprint(),
                new_initial_provider_requests=0,
            )
            return initial, "复用固定自然初始方案；各臂命令及检查相同"
        if forbid_provider:
            kwargs["meter"].ledger.append(
                "development.provider_forbidden", reason=kwargs["handoff"]["reason"]
            )
            raise base.PlanContractError(
                "development_only_stop_before_provider：保存首次交接，不调用模型"
            )
        return original(**kwargs)

    return goal_state_planner(dispatch) if direct else dispatch


def run_slot(*, protocol, slot, root, model, forbid_provider=False):
    if slot["method"] not in METHODS or (forbid_provider and model is not None):
        raise base.PlanContractError("未知处理或零Provider检查传入了模型")
    case = next(c for c in protocol["cases"] if c["case_id"] == slot["case_id"])
    if slot["project"] != case["project"]:
        raise base.PlanContractError("槽与方案所属项目不一致")
    item = next(p for p in protocol["projects"] if p["name"] == slot["project"])
    task = base.PlanTask.model_validate(item["task"])
    initial = checked_plan(case, task)
    early, direct = slot["method"] != METHODS[0], slot["method"] == METHODS[2]
    with common_harness_interfaces():
        original = base.observed_module.observed_planner

        def planner_factory(*args, **kwargs):
            return fixed_planner(
                initial,
                original(*args, **kwargs),
                direct=direct,
                forbid_provider=forbid_provider,
            )

        def meter_factory(*args, **kwargs):
            return component.CommonGoalMeter(
                *args, goals=configuration_goals(task), **kwargs
            )

        with (
            patch.object(base, "PreparationMeter", meter_factory),
            patch.object(base, "execution_window", component.bounded.execution_window),
            patch.object(
                base.prepared_module,
                "PreparedWorkflow",
                GoalStateWorkflow if early else base.prepared_module.PreparedWorkflow,
            ),
            patch.object(base.observed_module, "observed_planner", planner_factory),
        ):
            row = paired.replication.run_slot(
                protocol=protocol,
                slot={**slot, "method": "model_plan_workflow"},
                root=root,
                model=model,
            )
    historical = case["historical_initial_planning"]
    return {
        **row,
        **slot,
        "kind": "zero_provider_engineering_dispatch_check"
        if forbid_provider
        else "real_model_fixed_plan_recovery_comparison",
        "initial_plan_sha256": initial.fingerprint(),
        "historical_initial_planning": historical,
        "comparable_total_estimated_cost_usd": str(
            Decimal(historical["estimated_cost_usd"])
            + Decimal(str(row["agent_usage"]["estimated_cost_usd_completed_responses"]))
        ),
        "historical_initial_cost_is_new_spending": False,
        "development_provider_disabled": forbid_provider,
    }


def execute(protocol, root, model, rows):
    with patch.object(paired, "run_slot", run_slot):
        return paired.execute(protocol, root, model, rows)


def analyze(root):
    result = base.load(root / "result.json")
    summary, details = {}, []
    for number, row in enumerate(result["rows"], 1):
        folder = root / f"slot-{number}"
        state = base.load(next(folder.glob("*/.compile-sessions/*/*/session.json")))
        events = [
            json.loads(line)
            for path in folder.glob("*/agent/events.jsonl")
            for line in path.read_text().splitlines()
        ]
        builds = [c for c in state["commands"] if c["role"] == "build"]
        first = next(iter(row.get("transitions", [])), {})
        first_handoff = first.get("handoff") or {}
        prior_builds = [
            c for c in first_handoff.get("recent_commands", []) if c["role"] == "build"
        ]
        # completed补足有界日志投影中可能省略的成功前缀；失败build仍从recent_commands恢复。
        prior_ids = set(first.get("completed", {}).values()) | {
            c["command_id"] for c in prior_builds
        }
        details.append(
            dict(
                case_id=row["case_id"],
                repetition=row["repetition"],
                method=row["method"],
                strict_completed=row["strict_completed"],
                initial_plan_sha256=row["initial_plan_sha256"],
                build_commands=len(builds),
                build_seconds=sum(c["duration_seconds"] for c in builds),
                build_seconds_before_first_handoff=sum(
                    c["duration_seconds"]
                    for c in builds
                    if c["command_id"] in prior_ids
                )
                if first_handoff
                else None,
                first_handoff_reason=first_handoff.get("reason"),
                first_handoff_step=first_handoff.get("step_id"),
                agent_recovery_episodes=sum(
                    e["event"] == "agent.started" and e.get("recovery") is True
                    for e in events
                ),
                direct_revisions=sum(
                    e["event"] == "goal_state.action"
                    and e.get("action") == "direct_configuration_revision"
                    for e in events
                ),
                error=row.get("error_message"),
                cleanup=row["cleanup"]["succeeded"],
            )
        )
    for method in METHODS:
        rows = [r for r in result["rows"] if r["method"] == method]
        summary[method] = dict(
            observed=len(rows),
            strict_completed=sum(r["strict_completed"] for r in rows),
            new_model_requests=sum(r["agent_usage"]["model_requests"] for r in rows),
            unknown_usage_requests=sum(
                r["agent_usage"]["unknown_usage_requests"] for r in rows
            ),
            new_estimated_cost_usd=str(
                sum(
                    (
                        Decimal(
                            str(
                                r["agent_usage"][
                                    "estimated_cost_usd_completed_responses"
                                ]
                            )
                        )
                        for r in rows
                    ),
                    Decimal(0),
                )
            ),
            comparable_total_estimated_cost_usd=str(
                sum(
                    (Decimal(r["comparable_total_estimated_cost_usd"]) for r in rows),
                    Decimal(0),
                )
            ),
            fresh_execution_seconds=sum(r["arm_total_wall_seconds"] for r in rows),
        )
    return dict(
        identity=result["identity"],
        summary=summary,
        details=details,
        unobserved=result["unobserved_schedule"],
        stop_reason=result["stop_reason"],
        interpretation="固定自然方案的条件性机制比较；按配置偏离/正常分层，不估自然错误发生率或总体泛化。两次重复不是独立项目。",
    )


def development_check(output):
    """只验证真实分派：两Agent组停在交接，直接组继续；不产生模型效果结论。"""
    candidate = candidate_for()
    validate(candidate)
    subprocess.run(
        ["bash", str(ROOT / "scripts/require-docker-runtime.sh")],
        check=True,
        timeout=30,
    )
    output.mkdir(parents=True, exist_ok=False)
    cases = [
        c
        for c in candidate["cases"]
        if c["case_id"] in ("snappy-deviated", "yaml-cpp-satisfied")
    ]
    slots = [
        dict(project=c["project"], case_id=c["case_id"], repetition=1, method=method)
        for c in cases
        for method in METHODS
    ]
    protocol = {
        **candidate,
        "identity": "cpp-build-fixed-plan-state-dispatch-check-v1",
        "kind": "zero_provider_engineering_dispatch_check",
        "schedule": slots,
        "stage_max_cost_usd": "0",
        "deadline_utc": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
    }
    base.write_json(output / "protocol.json", protocol)
    rows = []
    for number, slot in enumerate(slots, 1):
        folder = output / f"slot-{number}"
        folder.mkdir()
        row = run_slot(
            protocol=protocol, slot=slot, root=folder, model=None, forbid_provider=True
        )
        rows.append(row)
        print(
            json.dumps(
                dict(
                    slot=number,
                    case_id=slot["case_id"],
                    method=slot["method"],
                    strict=row["strict_completed"],
                    error=row.get("error_message"),
                ),
                ensure_ascii=False,
            ),
            flush=True,
        )
        if row["agent_usage"]["model_requests"] or not row["cleanup"]["succeeded"]:
            break
    result = dict(
        identity=protocol["identity"],
        kind=protocol["kind"],
        rows=rows,
        unobserved_schedule=slots[len(rows) :],
        stop_reason=None,
    )
    base.write_json(output / "result.json", result)
    analysis = analyze(output)
    base.write_json(output / "analysis.json", analysis)
    seal(output, protocol, ROOT)
    expected = [False, False, True, True, True, True]
    success = (
        len(rows) == 6
        and [r["strict_completed"] for r in rows] == expected
        and all(
            r["cleanup"]["succeeded"] and r["agent_usage"]["model_requests"] == 0
            for r in rows
        )
    )
    return 0 if success else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("--select-cases", action="store_true")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--check-prepared", action="store_true")
    parser.add_argument("--analyze", type=Path)
    parser.add_argument("--development-check", type=Path)
    args, remaining = parser.parse_known_args()
    if args.select_cases:
        select_cases()
        print(
            json.dumps(
                dict(
                    cases=len(base.load(SELECTION)["cases"]),
                    provider_calls=0,
                    credentials_read=False,
                )
            )
        )
        return 0
    if args.prepare:
        candidate = candidate_for()
        validate(candidate)
        base.write_json(MANIFEST, candidate)
        print(
            json.dumps(
                dict(
                    identity=IDENTITY,
                    slots=len(candidate["schedule"]),
                    provider_calls=0,
                    credentials_read=False,
                )
            )
        )
        return 0
    if args.check_prepared:
        validate(base.load(MANIFEST))
        print(json.dumps(dict(valid=True, provider_calls=0, credentials_read=False)))
        return 0
    if args.analyze:
        print(json.dumps(analyze(args.analyze), ensure_ascii=False, indent=2))
        return 0
    if args.development_check:
        return development_check(args.development_check.resolve())
    signal.signal(signal.SIGINT, component.bounded.request_stop)
    with (
        patch.object(sys, "argv", [sys.argv[0], *remaining]),
        patch.object(base, "PROVIDER", component.flash.PROVIDER),
        patch.object(base, "validate", validate),
        patch.object(base, "execute", execute),
    ):
        return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
