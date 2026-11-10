#!/usr/bin/env python3
"""修复驱动参数后仅执行未启动槽；复用已完成共同规划，不续跑冻结原件。"""

from __future__ import annotations

import argparse
import json
import shutil
from decimal import Decimal
from pathlib import Path

import forge_recovery_harness_comparison as base
from forge_typed_evidence import audit, digest, seal

from deerflow.compile.operation_window import OperationWindow
from deerflow.compile.plan_workflow import PlanContractError

IDENTITY = "cpp-build-recovery-harness-comparison-flash-v2"
MANIFEST = base.ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREG = base.ROOT / "benchmarks/preregistrations" / (IDENTITY + ".md")
PARENT = Path("/home/yiwei/.codex/outputs/forge-recovery-harness-comparison-flash-v1")


def parent_scope(root=PARENT):
    """只接受已完成规划、首槽调用前失败的固定原件，不把未知请求擅自归零。"""
    sealed = audit(root)
    result = base.shared.load(root / "result.json")
    failure = base.shared.load(root / "runner-failure.json")
    initial = result["common_initial_plans"]
    if (
        result["identity"] != base.IDENTITY
        or result["completed_slots"] != 0
        or result["rows"]
        or len(initial) != 1
        or initial[0]["project"] != "cglm"
        or initial[0]["status"] != "planned"
        or base.shared.usage(initial[0])["unknown"]
        or result["unclosed_unit"]["kind"] != "comparison"
        or Path(result["unclosed_unit"]["folder"]).exists()
        or list(root.glob("slot-*"))
        or failure != dict(type="TypeError", message="BuildStateRouter.__init__() missing 2 required keyword-only arguments: 'method' and 'directory'")
    ):
        raise PlanContractError("原批次不符合仅执行未启动槽的固定边界")
    return dict(
        identity=base.IDENTITY,
        root=str(root),
        inventory_sha256=sealed["inventory_canonical_sha256"],
        result_sha256=digest(root / "result.json"),
        initial_result_sha256=digest(root / "initial/cglm/result.json"),
        imported_project="cglm",
        imported_plan_sha256=initial[0]["plan_sha256"],
        previously_paid_planning_cost_usd=str(base.shared.usage(initial[0])["cost"]),
        original_billing_complete=result["billing_complete"],
        original_seal_unknown_usage_requests=sealed["unknown_usage_requests"],
        boundary="原汇总因未闭合执行单元保守标未知；traceback在路由构造/执行器调用前，槽目录未创建，无槽模型请求或容器。原标签不改；复用两次已知响应及规划，不重试任何模型请求或已启动构建。",
    )


def candidate():
    value = base.candidate()
    value.update(identity=IDENTITY, issue=713, state="authorized_same_scope_unstarted_continuation", parent_scope=parent_scope())
    value["components"].update({p.relative_to(base.ROOT).as_posix(): digest(p) for p in (Path(__file__), PREREG, base.MANIFEST)})
    value["cost_attribution"] += "; imported_cglm_planning_is_prior_payment_counted_once_in_authorized_total_not_new_payment"
    value["user_review"] = "用户已确认原18项目/36槽、5美元/4小时；仅修复调用参数并执行尚未启动槽，复用已完成规划；沿原预算/截止，无自动重试、不改方法或验收。"
    return value


def reused_planner(planner, scope):
    def call(**kwargs):
        if kwargs["item"]["name"] != scope["imported_project"]:
            return planner(**kwargs)
        source = Path(scope["root"]) / "initial/cglm"
        if digest(source / "result.json") != scope["initial_result_sha256"]:
            raise PlanContractError("已完成规划原件变化")
        result = base.shared.load(source / "result.json")
        if result["plan"]["task"] != kwargs["item"]["task"]:
            raise PlanContractError("复用共同规划不属于原任务")
        shutil.copytree(source, kwargs["folder"])
        base.save(kwargs["folder"] / "import-origin.json", scope)
        return result | dict(origin_identity=scope["identity"], origin_path=str(source), new_model_payment=False)

    return call


def analyze(output, value):
    result = base.analyze(output)
    paid = Decimal(value["parent_scope"]["previously_paid_planning_cost_usd"])
    result.update(
        imported_planning=value["parent_scope"],
        authorized_scope_total_model_cost_usd=result["actual_batch_cost_usd"],
        current_stage_new_model_cost_usd=str(Decimal(result["actual_batch_cost_usd"]) - paid) if result["billing_complete"] else None,
        billing_boundary="总费用覆盖原授权v1+v2；cglm原两次规划请求/费用只计一次。v2新付款另列，不能将两份原始目录中的复制用量重复相加。",
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--check-prepared", action="store_true")
    group.add_argument("--run", action="store_true")
    group.add_argument("--analyze", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.prepare:
        if MANIFEST.exists():
            raise PlanContractError("不覆盖已冻结续段身份")
        base.save(MANIFEST, candidate())
    value = base.shared.load(MANIFEST)
    if args.analyze:
        print(json.dumps(analyze(args.analyze, value), ensure_ascii=False, indent=2))
        return
    base.validate(value, identity=IDENTITY)
    if parent_scope() != value["parent_scope"]:
        raise PlanContractError("冻结父批次或复用范围变化")
    if not args.run:
        print(json.dumps(dict(valid=True, identity=IDENTITY, candidate_sha256=digest(MANIFEST), execution_slots=36, new_planning_tasks=17, reused_planning_tasks=1, provider_calls=0)))
        return
    if not args.authorization or not args.output or args.output.exists():
        raise PlanContractError("需要新授权记录与不存在的续段输出目录")
    auth = base.shared.load(args.authorization)
    base.shared.validate_authorization(auth, digest(MANIFEST), identity=IDENTITY, maximum_hours=4)
    if Decimal(auth["maximum_cost_usd"]) > Decimal(value["maximum_cost_usd"]):
        raise PlanContractError("沿原5美元硬上限，包含先前规划支出")
    original = base.shared.load(PARENT / "authorization.json")
    if any(auth[k] != original[k] for k in ("authorized_at_utc", "deadline_utc", "maximum_cost_usd", "automatic_retry", "user_reply")):
        raise PlanContractError("不能重置原预算、授权起点、截止或用户答复")
    OperationWindow(auth["deadline_utc"]).admit("unstarted_continuation", 900)
    planner, executor = base.paid_callbacks(value, auth)
    try:
        base.execute(value, args.output, auth, reused_planner(planner, value["parent_scope"]), executor)
    finally:
        if (args.output / "result.json").exists():
            base.save(args.output / "analysis.json", analyze(args.output, value))
            result = base.shared.load(args.output / "result.json")
            unknown = sum(base.shared.usage(r)["unknown"] for r in result["rows"] + result["common_initial_plans"]) + int(result["unclosed_unit"] is not None)
            seal(args.output, value, base.ROOT, unknown_usage_requests=unknown)


if __name__ == "__main__":
    main()
