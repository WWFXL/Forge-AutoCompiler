#!/usr/bin/env python3
"""Make/Autotools C++共同接口资格与三策略比较；旧证据不变。"""

from __future__ import annotations
import argparse
import copy
import json
import os
import subprocess
import time
from decimal import Decimal
from pathlib import Path
from forge_build_cxx_comparison import REPO_ROOT, classified_prepared_arm
from forge_build_referenced_meter import (
    ReferencedStrategyMeter,
    ReferencedQualificationMeter,
)
from forge_build_task_selected_comparison import (
    validate_authorization as selected_authorization,
)
from forge_build_unified_plan_comparison import execute
from forge_build_unified_plan import METHODS
from forge_build_plan_predicate_gate import fake_model, reference_actions
from forge_build_auto_provenance_probe import automatic_gate_model
from forge_typed_evidence import audit, digest, seal, write_json
from deerflow.compile.plan_agent import PlanTask
from deerflow.compile.plan_agent_provenance import run_tool_agent_automatic
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek
from deerflow.compile.plan_cross_system import SharedResearchBudget, before_deadline
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.task_selected_make_plan import selected_make_actions
from deerflow.compile.unified_plan_equivalent_observed import observed_planner

IDENTITY = "cpp-build-cxx-cross-system-comparison-v1"
GATE_IDENTITY = "cpp-build-cxx-cross-system-common-gate-v1"
PROJECTS = ("tinyxml2", "libconfig")


def schedule():
    orders = (((0, 1, 2), (1, 2, 0), (2, 0, 1)), ((2, 1, 0), (1, 0, 2), (0, 2, 1)))
    return [
        dict(project=p, repetition=r + 1, method=METHODS[m], case="natural_unmodified")
        for p, blocks in zip(PROJECTS, orders, strict=True)
        for r, order in enumerate(blocks)
        for m in order
    ]


def gate_schedule():
    return [
        dict(project=p, repetition=1, method=m, case="normal")
        for p in PROJECTS
        for m in METHODS
    ]


def make_project(item):
    reference = copy.deepcopy(item["plan"])
    reference["steps"] = [
        s for s in reference["steps"] if s["step_id"] != "forge-source-prepare"
    ]
    task = {k: v for k, v in reference.items() if k not in ("steps", "revision")}
    task["verification_steps"] = [s for s in reference["steps"] if s["role"] == "smoke"]
    PlanTask.model_validate(task)
    paths = (
        ["README.md", "Makefile", "CMakeLists.txt"]
        if item["name"] == "tinyxml2"
        else ["README", "configure.ac", "Makefile.am", "ac_config.h.in"]
    )
    return dict(
        name=item["name"],
        task=task,
        source_archive=item["source_archive"],
        source_paths=paths,
    ), reference


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
        raise PlanContractError("策略或人工参考隔离失败")
    arm = "tool" if method == METHODS[2] else "plan"
    active = (
        fake_model([reference_actions(reference).model_dump(mode="json")])
        if qualify and arm == "plan"
        else model
    )
    base = observed_planner(
        "tool" if method == METHODS[0] else "model", generator=selected_make_actions
    )

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
        meter_factory=ReferencedQualificationMeter
        if qualify
        else ReferencedStrategyMeter,
        planner=planner,
        tool_runner=tool_runner,
        command_timeout_seconds=600,
        replay_timeout_seconds=900,
    )
    return {**row, **slot, "arm_total_wall_seconds": time.monotonic() - started}


def validate_sources(candidate):
    expected = []
    references = {}
    for bound in candidate["reference_evidence"]:
        root = Path(bound["root"])
        if audit(root)["inventory_canonical_sha256"] != bound["inventory_sha256"]:
            raise PlanContractError("参考封存变化")
        receipt = Path(bound["independent_audit_path"])
        checked = json.loads(receipt.read_text())
        if (
            digest(receipt) != bound["independent_audit_sha256"]
            or checked.get("valid") is not True
        ):
            raise PlanContractError("参考独立核验变化")
        rows = json.loads((root / "result.json").read_text())["projects"]
        original = json.loads((root / "protocol.json").read_text())["projects"]
        row = next(r for r in rows if r["name"] == bound["project"])
        if not row["qualified"] or not any(
            r["name"] == bound["project"] and r["qualified"] for r in checked["rows"]
        ):
            raise PlanContractError("参考任务未合格")
        item = next(r for r in original if r["name"] == bound["project"])
        project, reference = make_project(item)
        expected.append(project)
        references[item["name"]] = reference
        if (
            digest(Path(project["source_archive"]))
            != project["task"]["source_archive_sha256"]
        ):
            raise PlanContractError("归档变化")
    if (
        tuple(p["name"] for p in expected) != PROJECTS
        or candidate["projects"] != expected
    ):
        raise PlanContractError("任务/完整测试/来源或候选改变")
    return references


def validate(candidate):
    qualify = candidate["identity"] == GATE_IDENTITY
    if candidate["identity"] not in (GATE_IDENTITY, IDENTITY) or candidate[
        "schedule"
    ] != (gate_schedule() if qualify else schedule()):
        raise PlanContractError("固定身份或顺序变化")
    for p, h in candidate["components"].items():
        if digest(REPO_ROOT / p) != h:
            raise PlanContractError("冻结组件变化:" + p)
    parent = json.loads(
        (
            REPO_ROOT
            / "benchmarks/manifests/cpp-build-task-selected-comparison-v1.json"
        ).read_text()
    )
    if any(
        candidate["components"].get(k) != v for k, v in parent["components"].items()
    ) or any(candidate[k] != parent[k] for k in ("provider", "runtime")):
        raise PlanContractError("共同Harness/Provider/完整计量变化")
    references = validate_sources(candidate)
    if qualify:
        if (
            candidate["provider_calls"] != 0
            or candidate["credentials_read"] is not False
            or candidate["deadline_utc"] != "2026-10-20T22:07:35Z"
        ):
            raise PlanContractError("零Provider边界变化")
    else:
        if (
            candidate["deadline_utc"] is not None
            or candidate["provider_authorization"] is not None
        ):
            raise PlanContractError("候选不能自我授权")
        bound = candidate["gate"]
        root = Path(bound["root"])
        receipt = Path(bound["independent_audit_path"])
        checked = json.loads(receipt.read_text())
        if (
            audit(root)["inventory_canonical_sha256"] != bound["inventory_sha256"]
            or digest(receipt) != bound["independent_audit_sha256"]
            or checked.get("valid") is not True
            or checked["strict_completed"] != 6
        ):
            raise PlanContractError("六槽独立门禁未闭合")
        gate = json.loads((root / "protocol.json").read_text())
        result = json.loads((root / "result.json").read_text())
        if (
            gate["projects"] != candidate["projects"]
            or result["not_observed"]
            or len(result["arms"]) != 6
            or not all(r["strict_completed"] for r in result["arms"])
            or any(
                candidate["components"].get(k) != v
                for k, v in gate["components"].items()
            )
        ):
            raise PlanContractError("共同资格/组件变化")
    return references


def validate_authorization(candidate_sha, auth, shared, shared_root):
    if auth.get("experiment_identity") != IDENTITY:
        raise PlanContractError("不是本身份授权")
    return selected_authorization(
        candidate_sha,
        {**auth, "experiment_identity": "cpp-build-task-selected-comparison-v1"},
        shared,
        shared_root,
    )


def gate_main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    if protocol["identity"] != GATE_IDENTITY:
        raise PlanContractError("非零Provider身份")
    references = validate(protocol)
    before_deadline(protocol["deadline_utc"], 3300)
    if args.validate_only:
        print(json.dumps(dict(valid=True, provider_calls=0, slots=6)))
        return 0
    subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")],
        check=True,
        timeout=30,
    )
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    rows = []
    reason = None
    try:
        for i, slot in enumerate(protocol["schedule"]):
            try:
                before_deadline(protocol["deadline_utc"], 3300)
            except PlanContractError:
                reason = "deadline_reservation"
                break
            item = next(p for p in protocol["projects"] if p["name"] == slot["project"])
            item = {**item, "name": f"{i:02d}-{slot['project']}-{slot['method']}"}
            row = slot_runner(
                protocol=protocol,
                root=root,
                slot=slot,
                item=item,
                reference=references[slot["project"]],
                qualify=True,
            )
            rows.append(row)
            print(
                json.dumps(
                    {
                        k: row.get(k)
                        for k in (
                            "name",
                            "strict_completed",
                            "error_class",
                            "error_message",
                        )
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            if not row["cleanup"]["succeeded"]:
                reason = "cleanup_failure"
                break
    finally:
        unseen = [
            {**s, "status": "not_observed", "reason": reason}
            for s in protocol["schedule"][len(rows) :]
        ]
        write_json(
            root / "result.json",
            dict(
                identity=GATE_IDENTITY,
                kind="zero_provider_cross_system_common_gate",
                provider_calls=0,
                arms=rows,
                not_observed=unseen,
                stop_reason=reason,
            ),
        )
        print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
    return 0 if len(rows) == 6 and all(r["strict_completed"] for r in rows) else 1


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
        print(
            json.dumps(
                dict(
                    valid=True,
                    provider_calls=0,
                    slots=len(candidate["schedule"]),
                    authorized=False,
                )
            )
        )
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
        if len(rows) + len(unseen) != len(protocol["schedule"]):
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
                kind="prospective_cross_system_cpp_comparison",
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
    if len(os.sys.argv) > 1 and os.sys.argv[1] == "gate":
        os.sys.argv.pop(1)
        raise SystemExit(gate_main())
    raise SystemExit(main())
