#!/usr/bin/env python3
"""新观察接口的三策略比较；独立门禁和有效新授权先于凭据。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from forge_build_auto_provenance_probe import automatic_gate_model
from forge_build_full_strategy_cleanup_continuation import classified_arm
from forge_build_full_strategy_runtime import StrategyMeter
from forge_build_full_strategy_runtime_v2 import QualificationAwareMeter
from forge_build_plan_predicate_gate import fake_model, reference_actions
from forge_build_unified_plan import METHODS, REPO_ROOT
from forge_build_unified_plan_comparison import execute as execute_schedule
from forge_typed_evidence import audit, digest, seal, write_json

from deerflow.compile.plan_agent import PlanTask
from deerflow.compile.plan_agent_provenance import run_tool_agent_automatic
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek
from deerflow.compile.plan_cross_system import SharedResearchBudget, before_deadline
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.unified_plan_v2 import observed_planner

IDENTITY = "cpp-build-observed-plan-comparison-v1"
GATE_IDENTITY = "cpp-build-observed-plan-dispatch-gate-v1"
PARENT = "benchmarks/manifests/cpp-build-unified-plan-comparison-v1.json"
PROJECTS = ("libpng", "check", "libtommath", "libsodium")
# 四块不能完全位置平衡：每方法每位置出现1或2次，提前披露。
ORDERS = ((0, 1, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0))


def schedule():
    return [
        {
            "project": p,
            "repetition": 1,
            "method": METHODS[m],
            "case": "natural_unmodified",
        }
        for p, order in zip(PROJECTS, ORDERS, strict=True)
        for m in order
    ]


def gate_schedule():
    return [
        {"project": "buffer", "repetition": 1, "method": m, "case": "normal"}
        for m in METHODS
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
    executor=classified_arm,
):
    method = slot["method"]
    if (
        method not in METHODS
        or (qualify and reference is None)
        or (not qualify and reference is not None)
    ):
        raise PlanContractError("未知策略或参考配方隔离失败")
    arm = "tool" if method == METHODS[2] else "plan"
    active_model = (
        fake_model([reference_actions(reference).model_dump(mode="json")])
        if qualify and arm == "plan"
        else model
    )
    base = observed_planner("tool" if method == METHODS[0] else "model")

    def planner(**kwargs):
        return base(**{**kwargs, "model": active_model})

    def tool_runner(**kwargs):
        return run_tool_agent_automatic(
            **{**kwargs, "model": automatic_gate_model(reference) if qualify else model}
        )

    started = time.monotonic()
    row = executor(
        item=item,
        arm=arm,
        protocol=protocol,
        root=root,
        model=active_model,
        reference=reference if qualify else None,
        meter_factory=QualificationAwareMeter if qualify else StrategyMeter,
        planner=planner,
        tool_runner=tool_runner,
        command_timeout_seconds=600,
        replay_timeout_seconds=900,
    )
    return {**row, **slot, "arm_total_wall_seconds": time.monotonic() - started}


def validate_common(protocol):
    parent = json.loads((REPO_ROOT / PARENT).read_text())
    if protocol["parent_candidate_sha256"] != digest(REPO_ROOT / PARENT) or any(
        protocol["components"].get(k) != v for k, v in parent["components"].items()
    ):
        raise PlanContractError("旧107组件或父协议变化")
    if (
        protocol["provider"] != parent["provider"]
        or protocol["runtime"] != parent["runtime"]
        or protocol["role_evidence"] != parent["role_evidence"]
    ):
        raise PlanContractError("共同模型、资源或原角色证据变化")
    for name, sha in protocol["components"].items():
        if digest(REPO_ROOT / name) != sha:
            raise PlanContractError("冻结组件变化：" + name)
    role_root = Path(protocol["role_evidence"]["root"])
    if (
        audit(role_root)["inventory_canonical_sha256"]
        != protocol["role_evidence"]["inventory_sha256"]
    ):
        raise PlanContractError("角色证据变化")
    registered = {
        p["name"]: p
        for p in json.loads((role_root / "result.json").read_text())["projects"]
    }
    for item in protocol["projects"]:
        if item != {
            k: registered[item["name"]][k]
            for k in ("name", "task", "source_archive", "source_paths")
        }:
            raise PlanContractError("原任务、完整测试或源码登记变化")
        if (
            digest(Path(item["source_archive"]))
            != PlanTask.model_validate(item["task"]).source_archive_sha256
        ):
            raise PlanContractError("原源码归档变化")


def validate(candidate):
    validate_common(candidate)
    if (
        candidate["identity"] != IDENTITY
        or candidate["schedule"] != schedule()
        or tuple(p["name"] for p in candidate["projects"]) != PROJECTS
    ):
        raise PlanContractError("新比较身份或固定12槽不符")
    if (
        candidate["provider_authorization"] is not None
        or candidate["deadline_utc"] is not None
    ):
        raise PlanContractError("候选不得嵌入旧授权或时窗")
    if (
        candidate["exposure"]["holdout"] is not False
        or candidate["exposure"]["template_direct"] != ["libsodium"]
        or candidate["exposure"]["template_abstention"] != list(PROJECTS[:3])
    ):
        raise PlanContractError("开发暴露或静态分层登记变化")


def require_bound_gate(bound, *, dispatch=False):
    root = Path(bound["root"])
    if audit(root)["inventory_canonical_sha256"] != bound["inventory_sha256"]:
        raise PlanContractError("门禁证据变化")
    receipt = Path(bound["independent_audit_path"])
    if digest(receipt) != bound["independent_audit_sha256"]:
        raise PlanContractError("门禁独立审计变化")
    independent = json.loads(receipt.read_text())
    result = json.loads((root / "result.json").read_text())
    identity = (
        GATE_IDENTITY if dispatch else "cpp-build-plan-predicate-qualification-v2"
    )
    count, strict = (3, 3) if dispatch else (14, 13)
    if (
        independent.get("valid") is not True
        or independent["inventory_sha256"] != bound["inventory_sha256"]
        or independent["strict_completed"] != strict
    ):
        raise PlanContractError("门禁独立审计未闭合")
    if (
        result["identity"] != identity
        or len(result["arms"]) != count
        or result["not_observed"]
        or result["stop_reason"] is not None
    ):
        raise PlanContractError("门禁分母未闭合")
    if sum(bool(r["strict_completed"]) for r in result["arms"]) != strict:
        raise PlanContractError("门禁严格结果不符")
    if not dispatch and not all(
        r["gate_observation"]["expected_observation"] for r in result["arms"]
    ):
        raise PlanContractError("14槽资格未通过")
    if any(
        r["agent_usage"]["recorded_tokens"]
        or r["agent_usage"]["unknown_usage_requests"]
        or r["agent_usage"]["estimated_cost_usd_completed_responses"]
        for r in result["arms"]
    ):
        raise PlanContractError("零Provider资格出现非零用量")
    return json.loads((root / "protocol.json").read_text())


def require_gates(candidate):
    for bound, dispatch in (
        (candidate["observation_gate"], False),
        (candidate["dispatch_gate"], True),
    ):
        gate = require_bound_gate(bound, dispatch=dispatch)
        if any(
            candidate["components"].get(k) != v for k, v in gate["components"].items()
        ):
            raise PlanContractError("比较改变已通过门禁的组件")
    paths = candidate["path_observations_audit"]
    path = Path(paths["path"])
    if (
        digest(path) != paths["sha256"]
        or json.loads(path.read_text()).get("valid") is not True
    ):
        raise PlanContractError("原/重放路径检查独立核验缺失")


def validate_authorization(candidate_sha, authorization):
    if (
        authorization.get("experiment_identity") != IDENTITY
        or authorization.get("candidate_sha256") != candidate_sha
        or authorization.get("user_authorized") is not True
    ):
        raise PlanContractError("缺少本候选的新明确授权")
    maximum = Decimal(str(authorization["max_new_provider_cost_usd"]))
    if not maximum.is_finite() or not Decimal(0) < maximum <= Decimal(20):
        raise PlanContractError("本候选最多20美元")
    start = datetime.fromisoformat(authorization["authorized_at_utc"])
    end = datetime.fromisoformat(authorization["deadline_utc"])
    if (
        start.tzinfo is None
        or end.tzinfo is None
        or start > datetime.now(UTC)
        or not 3900 <= (end - start).total_seconds() <= 14400
    ):
        raise PlanContractError("授权时窗尚未开始或超出四小时候选边界")
    before_deadline(authorization["deadline_utc"], 3900)
    if authorization.get("provider_service_recheck_authorized") is not True:
        raise PlanContractError(
            "HTTP402外部阻塞须允许在新窗口首次请求核验；不能假定已解决"
        )


def execute(protocol, root, model, *, executor=slot_runner, results=None):
    # 复用已资格的费用/时限/未知usage/cleanup停止调度，显式注入新接口，绝不monkeypatch旧模块。
    return execute_schedule(protocol, root, model, executor=executor, results=results)


def run_gate(protocol, root):
    from forge_build_plan_paired_comparison import normalized_reference

    validate_common(protocol)
    if (
        protocol["identity"] != GATE_IDENTITY
        or protocol["schedule"] != gate_schedule()
        or protocol["provider_calls"] != 0
        or protocol["max_new_provider_cost_usd"] != 0
    ):
        raise PlanContractError("调度门禁身份或零费用边界不符")
    before_deadline(protocol["deadline_utc"], 2100)
    subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")],
        check=True,
        timeout=30,
    )
    os.environ["COMPILE_DOCKER_CLEANUP_TIMEOUT_SECONDS"] = "120"
    role_root = Path(protocol["role_evidence"]["root"])
    role = next(
        p
        for p in json.loads((role_root / "result.json").read_text())["projects"]
        if p["name"] == "buffer"
    )
    parent = Path(role["reference_root"])
    if (
        audit(parent)["inventory_canonical_sha256"]
        != role["reference_inventory_sha256"]
    ):
        raise PlanContractError("开发参考资格变化")
    reference = normalized_reference(
        next(
            p["plan"]
            for p in json.loads((parent / "protocol.json").read_text())["projects"]
            if p["name"] == "buffer"
        )
    )
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    rows, reason = [], "initialization_not_completed"
    try:
        for i, slot in enumerate(gate_schedule()):
            item = {
                **protocol["projects"][0],
                "name": f"{i:02d}-buffer-{slot['method']}",
            }
            row = slot_runner(
                protocol=protocol,
                root=root,
                slot=slot,
                item=item,
                reference=reference,
                qualify=True,
            )
            rows.append(row)
            usage = row["agent_usage"]
            expected_requests = int(slot["method"] != METHODS[0])
            if (
                not row["strict_completed"]
                or not row["cleanup"]["succeeded"]
                or usage["model_requests"] != expected_requests
                or any(
                    usage[k]
                    for k in (
                        "recorded_tokens",
                        "unknown_usage_requests",
                        "estimated_cost_usd_completed_responses",
                    )
                )
            ):
                reason = "dispatch_gate_failed"
                break
        else:
            reason = None
    finally:
        write_json(
            root / "result.json",
            {
                "identity": GATE_IDENTITY,
                "kind": "scripted_dispatch_qualification",
                "arms": rows,
                "not_observed": gate_schedule()[len(rows) :],
                "stop_reason": reason,
            },
        )
        seal(root, protocol, REPO_ROOT)
    return 0 if reason is None else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--authorization-root", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--qualify", action="store_true")
    args = parser.parse_args()
    candidate = json.loads(args.candidate.read_text())
    if args.qualify:
        if args.output_root is None or args.validate_only:
            raise PlanContractError("门禁须独立新目录，不混效果preflight")
        return run_gate(candidate, args.output_root.resolve())
    validate(candidate)
    require_gates(candidate)
    if args.validate_only:
        print(
            json.dumps(
                {"valid": True, "provider_calls": 0, "authorized": False, "slots": 12}
            )
        )
        return 0
    if args.authorization_root is None or args.output_root is None:
        raise PlanContractError("真实运行需要新的明确授权和新目录")
    shared = SharedResearchBudget(args.authorization_root)
    authorization = shared.authorization
    validate_authorization(digest(args.candidate), authorization)
    protocol = {
        **candidate,
        "candidate_sha256": digest(args.candidate),
        "deadline_utc": authorization["deadline_utc"],
        "max_new_provider_cost_usd": authorization["max_new_provider_cost_usd"],
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
    write_json(root / "authorization.json", authorization)
    rows, unseen, reason, complete = [], [], "initialization_not_completed", False
    shared.append(
        {
            "event": "stage.started",
            "identity": IDENTITY,
            "reserved_cost_usd": str(protocol["max_new_provider_cost_usd"]),
            "candidate_sha256": digest(args.candidate),
            "evidence_root": str(root),
        }
    )
    try:
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise PlanContractError("缺少已授权Provider凭据")
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
        rows, unseen, reason = execute(protocol, root, model, results=rows)
        complete = True
    finally:
        if len(rows) + len(unseen) != 12:
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
            {
                "identity": IDENTITY,
                "kind": "prospective_observed_contract_comparison",
                "arms": rows,
                "not_observed": unseen,
                "stop_reason": reason,
                "lifecycle_complete": complete,
                "known_estimated_cost_usd": str(known),
                "unknown_usage_reservation_usd": str(Decimal("0.40") * unknown),
            },
        )
        sealed = seal(root, protocol, REPO_ROOT, unknown)
        if complete:
            shared.append(
                {
                    "event": "stage.completed",
                    "identity": IDENTITY,
                    "charged_cost_usd": str(known + Decimal("0.40") * unknown),
                    "inventory_sha256": sealed["inventory_canonical_sha256"],
                }
            )
    return 0 if not unseen else 1


if __name__ == "__main__":
    raise SystemExit(main())
