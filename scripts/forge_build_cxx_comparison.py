#!/usr/bin/env python3
"""共同准备的C++三策略比较；新四槽零Provider门禁先于真实运行。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from forge_build_cxx_common_input_gate_v3 import REPO_ROOT, task_and_reference
from forge_build_auto_provenance_probe import automatic_gate_model
from forge_build_full_strategy_cleanup_continuation import cleanup_receipt
from forge_build_full_strategy_runtime import StrategyMeter
from forge_build_full_strategy_runtime_v2 import QualificationAwareMeter
from forge_build_plan_predicate_gate import fake_model, reference_actions
from forge_build_prepared_arm import run_arm
from forge_build_unified_plan import METHODS
from forge_build_unified_plan_comparison import execute
from forge_typed_evidence import audit, digest, seal, write_json
from deerflow.compile.plan_agent import PlanTask
from deerflow.compile.plan_agent_provenance import run_tool_agent_automatic
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek
from deerflow.compile.plan_cross_system import SharedResearchBudget, before_deadline
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.unified_plan_equivalent_observed import observed_planner

IDENTITY = "cpp-build-cxx-comparison-v1"
GATE_IDENTITY = "cpp-build-cxx-comparison-dispatch-gate-v1"
PARENT = "benchmarks/manifests/cpp-build-cxx-common-input-gate-v3.json"
PROJECTS = ("yaml-cpp", "simdutf", "snappy")
ORDERS = (((0, 1, 2), (2, 1, 0)), ((1, 2, 0), (0, 2, 1)), ((2, 0, 1), (1, 0, 2)))


def schedule():
    return [
        dict(project=p, repetition=r + 1, method=METHODS[m], case="natural_unmodified")
        for p, orders in zip(PROJECTS, ORDERS, strict=True)
        for r, order in enumerate(orders)
        for m in order
    ]


def gate_schedule():
    return [
        dict(project="buffer", repetition=1, method=m, case="normal") for m in METHODS
    ] + [dict(project="snappy", repetition=1, method=METHODS[2], case="normal")]


def classified_prepared_arm(**kwargs):
    row = run_arm(**kwargs)
    folder = kwargs["root"] / (kwargs["item"]["name"] + "-" + kwargs["arm"])
    receipt = cleanup_receipt(folder, row)
    if receipt:
        write_json(folder / "physical-cleanup-classification.json", receipt)
        row = {
            **row,
            "legacy_cleanup": row["cleanup"],
            "cleanup": {"succeeded": True},
            "cleanup_classification": "source_rejected_physical_cleanup_verified",
            "strict_completed": False,
        }
    return row


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
    method = slot["method"]
    if (
        method not in METHODS
        or (qualify and reference is None)
        or (not qualify and reference is not None)
    ):
        raise PlanContractError("未知策略或人工参考隔离失败")
    arm = "tool" if method == METHODS[2] else "plan"
    active = (
        fake_model([reference_actions(reference).model_dump(mode="json")])
        if qualify and arm == "plan"
        else model
    )
    base = observed_planner("tool" if method == METHODS[0] else "model")

    def planner(**kwargs):
        return base(**{**kwargs, "model": active})

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
        model=active,
        reference=reference if qualify else None,
        meter_factory=QualificationAwareMeter if qualify else StrategyMeter,
        planner=planner,
        tool_runner=tool_runner,
        command_timeout_seconds=600,
        replay_timeout_seconds=900,
    )
    return {**row, **slot, "arm_total_wall_seconds": time.monotonic() - started}


def validate_common(protocol, *, qualify=False):
    parent = json.loads((REPO_ROOT / PARENT).read_text())
    if protocol["parent_manifest_sha256"] != digest(REPO_ROOT / PARENT) or any(
        protocol["components"].get(k) != v for k, v in parent["components"].items()
    ):
        raise PlanContractError("父manifest或157原冻结组件变化")
    for name, sha in protocol["components"].items():
        if digest(REPO_ROOT / name) != sha:
            raise PlanContractError("冻结组件变化：" + name)
    old = Path(protocol["common_input_evidence"]["root"])
    if (
        audit(old)["inventory_canonical_sha256"]
        != protocol["common_input_evidence"]["inventory_sha256"]
    ):
        raise PlanContractError("原部分资格证据变化")
    old_result = json.loads((old / "result.json").read_text())
    if (
        len(old_result["arms"]) != 10
        or not all(
            r["gate_observation"]["expected_observation"] for r in old_result["arms"]
        )
        or old_result["not_observed"] != [parent["schedule"][-1]]
    ):
        raise PlanContractError("父部分资格事实不符")
    expected = [
        p
        for p in parent["projects"]
        if p["name"] in (("buffer", "snappy") if qualify else PROJECTS)
    ]
    if protocol["projects"] != expected:
        raise PlanContractError("共同任务、完整测试或来源改变")
    original = json.loads(
        (
            REPO_ROOT
            / "benchmarks/manifests/cpp-build-observed-plan-comparison-v2.json"
        ).read_text()
    )
    if (
        protocol["provider"] != original["provider"]
        or protocol["runtime"] != original["runtime"]
    ):
        raise PlanContractError("原模型或共同资源改变")
    for item in protocol["projects"]:
        if (
            digest(Path(item["source_archive"]))
            != PlanTask.model_validate(item["task"]).source_archive_sha256
        ):
            raise PlanContractError("来源归档变化")


def validate(candidate):
    validate_common(candidate)
    if (
        candidate["identity"] != IDENTITY
        or candidate["schedule"] != schedule()
        or candidate["provider_authorization"] is not None
        or candidate["deadline_utc"] is not None
    ):
        raise PlanContractError("18槽身份、顺序或未授权候选不符")
    if candidate["exposure"] != {
        "holdout": False,
        "reference_seen_by_developer": True,
        "reference_injected_into_real_agent": False,
        "template_direct": ["simdutf"],
        "template_abstention": ["yaml-cpp", "snappy"],
        "shared_test_infrastructure": ["yaml-cpp", "snappy"],
        "all_cmake_cpp": True,
    }:
        raise PlanContractError("前瞻暴露与静态分层变化")


def require_gate(candidate):
    bound = candidate["dispatch_gate"]
    root = Path(bound["root"])
    if audit(root)["inventory_canonical_sha256"] != bound["inventory_sha256"]:
        raise PlanContractError("新门禁证据变化")
    receipt = Path(bound["independent_audit_path"])
    independent = json.loads(receipt.read_text())
    result = json.loads((root / "result.json").read_text())
    gate = json.loads((root / "protocol.json").read_text())
    if (
        digest(receipt) != bound["independent_audit_sha256"]
        or independent.get("valid") is not True
        or independent["inventory_sha256"] != bound["inventory_sha256"]
        or independent["strict_completed"] != 4
    ):
        raise PlanContractError("新门禁独立审计不完整")
    if (
        result["identity"] != GATE_IDENTITY
        or gate["schedule"] != gate_schedule()
        or len(result["arms"]) != 4
        or result["not_observed"]
        or result["stop_reason"] is not None
        or not all(
            r["gate_observation"]["expected_observation"] for r in result["arms"]
        )
    ):
        raise PlanContractError("三策略接线及snappy缺槽资格未闭合")
    if any(candidate["components"].get(k) != v for k, v in gate["components"].items()):
        raise PlanContractError("真实入口改变门禁组件")


def validate_authorization(candidate_sha, authorization):
    if (
        authorization.get("experiment_identity") != IDENTITY
        or authorization.get("candidate_sha256") != candidate_sha
        or authorization.get("user_authorized") is not True
    ):
        raise PlanContractError("缺少本身份和候选的有效授权")
    maximum = Decimal(str(authorization["max_new_provider_cost_usd"]))
    start, end = (
        datetime.fromisoformat(authorization[k])
        for k in ("authorized_at_utc", "deadline_utc")
    )
    if (
        not maximum.is_finite()
        or not 0 < maximum <= 20
        or start.tzinfo is None
        or end.tzinfo is None
        or start > datetime.now(UTC)
        or not 3900 <= (end - start).total_seconds() <= 14400
    ):
        raise PlanContractError("预算或四小时绝对时窗不符")
    before_deadline(authorization["deadline_utc"], 3900)


def run_gate(protocol, root):
    validate_common(protocol, qualify=True)
    if (
        protocol["identity"] != GATE_IDENTITY
        or protocol["schedule"] != gate_schedule()
        or protocol["provider_calls"] != 0
        or protocol["credentials_read"] is not False
        or protocol["max_new_provider_cost_usd"] != 0
    ):
        raise PlanContractError("新四槽门禁或零Provider边界变化")
    before_deadline(protocol["deadline_utc"], 2100)
    subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")],
        check=True,
        timeout=30,
    )
    os.environ["COMPILE_DOCKER_CLEANUP_TIMEOUT_SECONDS"] = "120"
    parent = json.loads((REPO_ROOT / PARENT).read_text())
    references = {}
    for bound in parent["reference_evidence"]:
        source = Path(bound["root"])
        if audit(source)["inventory_canonical_sha256"] != bound["inventory_sha256"]:
            raise PlanContractError("门禁人工参考证据变化")
        for original in json.loads((source / "protocol.json").read_text())["projects"]:
            if original["name"] in ("buffer", "snappy"):
                _, references[original["name"]] = task_and_reference(original)
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    rows, reason = [], "initialization_not_completed"
    projects = {p["name"]: p for p in protocol["projects"]}
    try:
        for i, slot in enumerate(gate_schedule()):
            before_deadline(protocol["deadline_utc"], 2100)
            item = {
                **projects[slot["project"]],
                "name": f"{i:02d}-{slot['project']}-{slot['method']}",
            }
            row = slot_runner(
                protocol=protocol,
                root=root,
                slot=slot,
                item=item,
                reference=references[slot["project"]],
                qualify=True,
            )
            u = row["agent_usage"]
            expected = (
                row["strict_completed"]
                and row["source_preparation"]["exit_code"] == 0
                and u["model_requests"] == int(slot["method"] != METHODS[0])
                and not any(
                    u[k]
                    for k in (
                        "recorded_tokens",
                        "unknown_usage_requests",
                        "estimated_cost_usd_completed_responses",
                    )
                )
            )
            rows.append(
                {**row, "gate_observation": {"expected_observation": bool(expected)}}
            )
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
            if not expected:
                reason = "dispatch_gate_failed"
                break
        else:
            reason = None
    finally:
        write_json(
            root / "result.json",
            {
                "identity": GATE_IDENTITY,
                "kind": "scripted_dispatch_and_missing_path_qualification",
                "arms": rows,
                "not_observed": gate_schedule()[len(rows) :],
                "stop_reason": reason,
            },
        )
        print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
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
            raise PlanContractError("门禁须新目录，不能混用真实preflight")
        return run_gate(candidate, args.output_root.resolve())
    validate(candidate)
    require_gate(candidate)
    if args.validate_only:
        print(
            json.dumps(
                {"valid": True, "provider_calls": 0, "slots": 18, "authorized": False}
            )
        )
        return 0
    if args.authorization_root is None or args.output_root is None:
        raise PlanContractError("真实执行须新授权与新证据目录")
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
        rows, unseen, reason = execute(
            protocol, root, model, executor=slot_runner, results=rows
        )
        complete = True
    finally:
        if len(rows) + len(unseen) != 18:
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
                "kind": "prospective_common_prepared_cpp_comparison",
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
