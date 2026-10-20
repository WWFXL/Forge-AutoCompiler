#!/usr/bin/env python3
"""原模板与任务指定模板的有界比较；共享本轮预算和绝对截止。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from decimal import Decimal
from pathlib import Path

from forge_build_cxx_comparison import (
    REPO_ROOT,
    classified_prepared_arm,
    validate_common,
    validate_authorization as validate_window,
)
from forge_build_referenced_meter import ReferencedStrategyMeter as StrategyMeter
from forge_build_unified_plan_comparison import execute
from forge_typed_evidence import audit, digest, seal, write_json
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek
from deerflow.compile.plan_cross_system import SharedResearchBudget
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.task_selected_tool_plan import selected_tool_actions
from deerflow.compile.unified_plan_equivalent_observed import (
    observed_planner,
    observed_tool_actions,
)

IDENTITY = "cpp-build-task-selected-comparison-v1"
METHODS = ("original_tool_workflow", "task_selected_tool_workflow")


def schedule():
    return [
        dict(project=p, repetition=1, method=METHODS[m], case="natural_unmodified")
        for p, order in (("yaml-cpp", (0, 1)), ("simdutf", (1, 0)), ("snappy", (0, 1)))
        for m in order
    ]


def slot_runner(
    *,
    protocol,
    root,
    slot,
    item,
    model=None,
    reference=None,
    qualify=False,
    executor=classified_prepared_arm,
):
    if slot["method"] not in METHODS or reference is not None or qualify:
        raise PlanContractError("真实两模板比较禁止人工参考/脚本模型或未知方法")
    generator = (
        selected_tool_actions if slot["method"] == METHODS[1] else observed_tool_actions
    )
    base = observed_planner("tool", generator=generator)

    def planner(**kwargs):
        return base(**{**kwargs, "model": model})

    started = time.monotonic()
    row = executor(
        item=item,
        arm="plan",
        protocol=protocol,
        root=root,
        model=model,
        reference=None,
        meter_factory=StrategyMeter,
        planner=planner,
        command_timeout_seconds=600,
        replay_timeout_seconds=900,
    )
    return {**row, **slot, "arm_total_wall_seconds": time.monotonic() - started}


def validate(candidate):
    validate_common(candidate)
    if (
        candidate["identity"] != IDENTITY
        or candidate["schedule"] != schedule()
        or candidate["deadline_utc"] is not None
        or candidate["provider_authorization"] is not None
    ):
        raise PlanContractError("新六槽候选身份或前瞻顺序不符")
    bound = candidate["selected_gate"]
    root = Path(bound["root"])
    if audit(root)["inventory_canonical_sha256"] != bound["inventory_sha256"]:
        raise PlanContractError("新模板资格封存变化")
    receipt = Path(bound["independent_audit_path"])
    checked = json.loads(receipt.read_text())
    result = json.loads((root / "result.json").read_text())
    gate = json.loads((root / "protocol.json").read_text())
    if (
        digest(receipt) != bound["independent_audit_sha256"]
        or checked.get("valid") is not True
        or checked["strict_completed"] != 3
        or checked["inventory_sha256"] != bound["inventory_sha256"]
    ):
        raise PlanContractError("独立三项目模板资格不完整")
    if (
        result["identity"] != "cpp-build-task-selected-template-gate-v1"
        or result["not_observed"]
        or result["stop_reason"] is not None
        or len(result["arms"]) != 3
        or not all(
            r["gate_observation"]["expected_observation"] for r in result["arms"]
        )
    ):
        raise PlanContractError("三项目初始模板/恢复工程门禁未通过")
    if any(candidate["components"].get(k) != v for k, v in gate["components"].items()):
        raise PlanContractError("真实比较改变已通过资格的组件")


def validate_authorization(candidate_sha, auth, shared, shared_root):
    # 复用同一窗口检查，身份只对本新候选转换；不修改原授权或模块全局。
    if (
        auth.get("experiment_identity") != IDENTITY
        or auth.get("shared_authorization_sha256")
        != digest(shared_root / "authorization.json")
        or Path(auth["shared_budget_root"]).resolve() != shared_root.resolve()
    ):
        raise PlanContractError("新身份未绑定本轮共享授权")
    global_auth = shared.authorization
    if any(
        auth[k] != global_auth[k]
        for k in ("authorized_at_utc", "deadline_utc", "user_authorized")
    ):
        raise PlanContractError("阶段不能重置四小时绝对窗口")
    cap = Decimal(str(auth["max_new_provider_cost_usd"]))
    if (
        not cap.is_finite()
        or not 0 < cap <= 9
        or cap > Decimal(str(global_auth["max_new_provider_cost_usd"]))
    ):
        raise PlanContractError("本阶段最多预留九美元且不超过共享上限")
    validate_window(
        candidate_sha, {**auth, "experiment_identity": "cpp-build-cxx-comparison-v1"}
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--authorization-root", type=Path)
    parser.add_argument("--shared-budget-root", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    candidate = json.loads(args.candidate.read_text())
    validate(candidate)
    if args.validate_only:
        print(json.dumps(dict(valid=True, provider_calls=0, slots=6, authorized=False)))
        return 0
    if (
        args.output_root is None
        or args.authorization_root is None
        or args.shared_budget_root is None
    ):
        raise PlanContractError("真实运行必须绑定独立阶段授权及本轮共享账本")
    shared = SharedResearchBudget(args.shared_budget_root)
    auth = json.loads((args.authorization_root / "authorization.json").read_text())
    validate_authorization(
        digest(args.candidate), auth, shared, args.shared_budget_root
    )
    protocol = {
        **candidate,
        "candidate_sha256": digest(args.candidate),
        "deadline_utc": auth["deadline_utc"],
        "max_new_provider_cost_usd": auth["max_new_provider_cost_usd"],
    }
    subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")],
        check=True,
        timeout=30,
    )
    os.environ["COMPILE_DOCKER_CLEANUP_TIMEOUT_SECONDS"] = "120"
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    write_json(root / "authorization.json", auth)
    rows, unseen, reason, complete = [], [], "initialization_not_completed", False
    shared.append(
        dict(
            event="stage.started",
            identity=IDENTITY,
            reserved_cost_usd=str(auth["max_new_provider_cost_usd"]),
            candidate_sha256=digest(args.candidate),
            evidence_root=str(root),
        )
    )
    try:
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise PlanContractError("缺少已授权凭据")
        model = PlanThinkingDeepSeek(
            model="deepseek-v4-pro",
            api_key=key,
            base_url="https://api.deepseek.com",
            max_tokens=32768,
            max_retries=0,
            timeout=240,
            reasoning_effort="low",
            extra_body={"thinking": {"type": "enabled"}},
        )
        rows, unseen, reason = execute(
            protocol, root, model, executor=slot_runner, results=rows
        )
        complete = True
    finally:
        if len(rows) + len(unseen) != 6:
            unseen = [
                {**s, "status": "not_observed_or_unclosed", "reason": reason}
                for s in schedule()[len(rows) :]
            ]
        known = sum(
            (
                Decimal(str(r["agent_usage"]["estimated_cost_usd_completed_responses"]))
                for r in rows
            ),
            Decimal(0),
        )
        unknown = sum(r["agent_usage"]["unknown_usage_requests"] for r in rows)
        write_json(
            root / "result.json",
            dict(
                identity=IDENTITY,
                kind="prospective_task_selected_template_ablation",
                arms=rows,
                not_observed=unseen,
                stop_reason=reason,
                lifecycle_complete=complete,
                known_estimated_cost_usd=str(known),
                unknown_usage_reservation_usd=str(Decimal("0.40") * unknown),
            ),
        )
        sealed = seal(root, protocol, REPO_ROOT, unknown)
        if complete:
            shared.append(
                dict(
                    event="stage.completed",
                    identity=IDENTITY,
                    charged_cost_usd=str(known + Decimal("0.40") * unknown),
                    inventory_sha256=sealed["inventory_canonical_sha256"],
                )
            )
    return 0 if not unseen else 1


if __name__ == "__main__":
    raise SystemExit(main())
