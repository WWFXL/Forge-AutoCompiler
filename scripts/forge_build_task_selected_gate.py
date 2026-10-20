#!/usr/bin/env python3
"""任务指定CMake的三项目工程资格；只用脚本恢复，不提供Provider入口。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

from forge_build_cxx_comparison import REPO_ROOT, task_and_reference, validate_common
from forge_build_referenced_meter import (
    ReferencedQualificationMeter as QualificationAwareMeter,
)
from forge_build_plan_predicate_gate import fake_model, reference_actions
from forge_build_prepared_arm import run_arm
from forge_typed_evidence import audit, seal, write_json
from deerflow.compile.plan_cross_system import before_deadline
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.task_selected_tool_plan import selected_tool_actions
from deerflow.compile.unified_plan_equivalent_observed import observed_planner

IDENTITY = "cpp-build-task-selected-template-gate-v1"
PROJECTS = ("yaml-cpp", "simdutf", "snappy")


def validate(protocol):
    validate_common(protocol)
    if (
        protocol["identity"] != IDENTITY
        or protocol["schedule"] != list(PROJECTS)
        or protocol["provider_calls"] != 0
        or protocol["credentials_read"] is not False
        or protocol["max_new_provider_cost_usd"] != 0
    ):
        raise PlanContractError("固定三项目或零Provider边界不符")
    before_deadline(protocol["deadline_utc"], 2100)
    parent = Path(protocol["completed_comparison"]["root"])
    if (
        audit(parent)["inventory_canonical_sha256"]
        != protocol["completed_comparison"]["inventory_sha256"]
    ):
        raise PlanContractError("原比较尚未封存或证据变化，不能并行Docker")
    outcome = json.loads((parent / "result.json").read_text())
    if (
        not outcome["lifecycle_complete"]
        or outcome["not_observed"]
        or outcome["stop_reason"] is not None
    ):
        raise PlanContractError("原十八槽尚未完整结束")
    return json.loads(
        (
            REPO_ROOT / "benchmarks/manifests/cpp-build-cxx-common-input-gate-v3.json"
        ).read_text()
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    parent = validate(protocol)
    references = {}
    for bound in parent["reference_evidence"]:
        source = Path(bound["root"])
        if audit(source)["inventory_canonical_sha256"] != bound["inventory_sha256"]:
            raise PlanContractError("参考资格证据变化")
        for original in json.loads((source / "protocol.json").read_text())["projects"]:
            if original["name"] in PROJECTS:
                _, references[original["name"]] = task_and_reference(original)
    # 恢复可能新增依赖；必须丢弃初始缓存，避免沿用旧的依赖探测结果。
    for reference in references.values():
        for step in reference["steps"]:
            if step["role"] == "configure":
                step["command"] = "rm -rf build && " + step["command"]
    subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")],
        check=True,
        timeout=30,
    )
    os.environ["COMPILE_DOCKER_CLEANUP_TIMEOUT_SECONDS"] = "120"
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    projects = {p["name"]: p for p in protocol["projects"]}
    rows, reason = [], "initialization_not_completed"
    try:
        for i, name in enumerate(PROJECTS):
            before_deadline(protocol["deadline_utc"], 2100)
            # 仅失败恢复使用人工参考脚本响应；初始动作必须由源码模板独立生成。
            active = fake_model(
                [reference_actions(references[name]).model_dump(mode="json")]
            )
            base = observed_planner("tool", generator=selected_tool_actions)

            def planner(**kwargs):
                return base(**{**kwargs, "model": active})

            item = {**projects[name], "name": f"{i:02d}-{name}-task-selected"}
            started = time.monotonic()
            row = run_arm(
                item=item,
                arm="plan",
                protocol=protocol,
                root=root,
                reference=references[name],
                meter_factory=QualificationAwareMeter,
                planner=planner,
                command_timeout_seconds=600,
                replay_timeout_seconds=900,
            )
            row["arm_total_wall_seconds"] = time.monotonic() - started
            events = [
                json.loads(line)
                for line in (root / (item["name"] + "-plan") / "agent/events.jsonl")
                .read_text()
                .splitlines()
            ]
            phases = [e["phase"] for e in events if e["event"] == "unified.agent"]
            usage = row["agent_usage"]
            expected = (
                row["strict_completed"]
                and (
                    root / (item["name"] + "-plan") / "agent/tool-receipt.json"
                ).is_file()
                and all(p == "recovery" for p in phases)
                and usage["model_requests"] == len(phases)
                and not any(
                    usage[k]
                    for k in (
                        "recorded_tokens",
                        "unknown_usage_requests",
                        "estimated_cost_usd_completed_responses",
                    )
                )
            )
            rows.append(
                {
                    **row,
                    "project": name,
                    "method": "task_selected_tool_workflow",
                    "gate_observation": {
                        "expected_observation": bool(expected),
                        "scripted_recovery_phases": phases,
                    },
                }
            )
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
            if not expected:
                reason = "qualification_failed"
                break
        else:
            reason = None
    finally:
        write_json(
            root / "result.json",
            {
                "identity": IDENTITY,
                "kind": "scripted_task_selected_template_qualification",
                "arms": rows,
                "not_observed": list(PROJECTS[len(rows) :]),
                "stop_reason": reason,
            },
        )
        print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
    return 0 if reason is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
