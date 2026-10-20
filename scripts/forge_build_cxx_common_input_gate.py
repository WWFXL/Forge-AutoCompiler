#!/usr/bin/env python3
"""三策略共同源码准备资格；仅本地脚本模型，不提供Provider执行入口。"""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "backend/packages/harness"), str(REPO_ROOT / "scripts")]

# ruff: noqa: E402

from forge_build_auto_provenance_probe import automatic_gate_model
from forge_build_plan_predicate_gate import (
    fake_model,
    reference_actions,
    controlled_actions,
    proposal_values,
)
from forge_build_prepared_arm import run_arm
from forge_build_unified_plan import METHODS
from forge_typed_evidence import audit, digest, seal, write_json
from deerflow.compile.build_task_checks import (
    cmake_configuration_command,
    ctest_execution_command,
)
from deerflow.compile.plan_agent import PlanTask
from deerflow.compile.plan_agent_provenance import run_tool_agent_automatic
from deerflow.compile.plan_cross_system import before_deadline
from deerflow.compile.plan_workflow import BuildPlan, PlanContractError
from deerflow.compile.source_preparation import index_check_command, paths_fingerprint
from deerflow.compile.unified_plan_v2 import observed_planner, observed_tool_actions
from forge_build_full_strategy_runtime_v2 import QualificationAwareMeter

IDENTITY = "cpp-build-cxx-common-input-gate-v1"
PARENT_MANIFEST = (
    "benchmarks/manifests/cpp-build-cxx-reference-metadata-qualification-v2.json"
)
PROJECTS = ("yaml-cpp", "simdutf", "snappy")
REQUIREMENTS = {
    "yaml-cpp": {
        "YAML_CPP_BUILD_TESTS": True,
        "BUILD_TESTING": True,
        "YAML_CPP_BUILD_CONTRIB": True,
        "YAML_CPP_BUILD_TOOLS": True,
        "YAML_BUILD_SHARED_LIBS": False,
        "YAML_USE_SYSTEM_GTEST": False,
    },
    "simdutf": {
        "SIMDUTF_TESTS": True,
        "BUILD_TESTING": True,
        "SIMDUTF_FAST_TESTS": False,
        "SIMDUTF_TOOLS": True,
    },
    "snappy": {
        "SNAPPY_BUILD_TESTS": True,
        "SNAPPY_BUILD_BENCHMARKS": True,
        "HAVE_LIBZ": True,
        "HAVE_LIBLZO2": True,
        "HAVE_LIBLZ4": True,
    },
}
COUNTS = {"yaml-cpp": 3, "simdutf": 94, "snappy": 1}


def schedule():
    rows = [
        {"project": "buffer", "method": m, "case": "command_recovery"}
        for m in METHODS[:2]
    ]
    rows.extend(
        {"project": p, "method": m, "case": "normal"} for p in PROJECTS for m in METHODS
    )
    return rows


def task_and_reference(item):
    """在新结果前构造一致功能任务；保留原完整CTest及上游默认禁用项。"""
    reference = copy.deepcopy(item["plan"])
    for step in reference["steps"]:
        if step["role"] == "dependency":
            suffix = " && git init -q && git config --global --add safe.directory /workspace/repo && git add --force --all"
            if step["command"].endswith(suffix):
                step["command"] = step["command"][: -len(suffix)]
    expected = paths_fingerprint(
        json.loads(Path(item["source_file_hashes_path"]).read_text())
    )
    for step in reference["steps"]:
        if step["role"] != "smoke":
            continue
        check = index_check_command(expected)
        if item["name"] in PROJECTS:
            step["command"] = (
                cmake_configuration_command(REQUIREMENTS[item["name"]])
                + " && "
                + check
                + " && ctest --test-dir build --output-on-failure --no-tests=error --verbose --output-junit /workspace/forge-ctest.xml && "
                + ctest_execution_command(COUNTS[item["name"]])
                + " && "
                + check
            )
            step["required_output"] = [
                "FORGE_TASK_CONFIGURATION_OK",
                f"100% tests passed, 0 tests failed out of {COUNTS[item['name']]}",
                f"FORGE_CTEST_ACTUALLY_PASSED={COUNTS[item['name']]}",
                "FORGE_SOURCE_INDEX_VERIFIED=" + expected,
            ]
        else:
            step["command"] = "(\n" + step["command"] + "\n)\n" + check
            step["required_output"] = [
                *step["required_output"],
                "FORGE_SOURCE_INDEX_VERIFIED=" + expected,
            ]
        step["source"] = (
            "新身份共同任务：原作者完整测试/功能语义/实际执行与来源索引核验"
        )
    reference = BuildPlan.model_validate(reference).model_dump(mode="json")
    task = {k: v for k, v in reference.items() if k not in ("steps", "revision")}
    task["verification_steps"] = [s for s in reference["steps"] if s["role"] == "smoke"]
    PlanTask.model_validate(task)
    return {
        "name": item["name"],
        "task": task,
        "source_archive": item["source_archive"],
        "source_paths": item.get(
            "source_paths", ["README.md", "CMakeLists.txt", "Makefile"]
        ),
        "source_paths_sha256": expected,
    }, reference


def run_slot(protocol, root, slot, item, reference):
    method = slot["method"]
    arm = "tool" if method == METHODS[2] else "plan"
    source = "tool" if method == METHODS[0] else "model"
    case = slot["case"]
    good = reference_actions(reference)
    proposals = (
        proposal_values(good, case, source)
        if case == "command_recovery"
        else [good.model_dump(mode="json")]
    )
    active = fake_model(proposals)

    def generator(task, source_root):
        actions, receipt = observed_tool_actions(task, source_root)
        if case == "command_recovery":
            active.responses = fake_model(
                proposal_values(actions, case, source)
            ).responses
            return controlled_actions(actions, case, initial=True), receipt
        return actions, receipt

    base = observed_planner(source, generator=generator)

    def planner(**kwargs):
        return base(**{**kwargs, "model": active})

    def tool_runner(**kwargs):
        return run_tool_agent_automatic(
            **{**kwargs, "model": automatic_gate_model(reference)}
        )

    started = time.monotonic()
    row = run_arm(
        item=item,
        arm=arm,
        protocol=protocol,
        root=root,
        reference=reference,
        planner=planner,
        tool_runner=tool_runner,
        meter_factory=QualificationAwareMeter,
        command_timeout_seconds=600,
        replay_timeout_seconds=900,
    )
    events = [
        json.loads(s)
        for s in (root / (item["name"] + "-" + arm) / "agent/events.jsonl")
        .read_text()
        .splitlines()
    ]
    handoffs = sum(s["status"] == "needs_handoff" for s in row["transitions"])
    prep = [e for e in events if e["event"] == "source.preparation_completed"]
    phases = [e["phase"] for e in events if e["event"] == "unified.agent"]
    usage = row["agent_usage"]
    expected_phases = (
        (["recovery"] if source == "tool" else ["initial", "recovery"])
        if case == "command_recovery"
        else []
        if method == METHODS[2] or (source == "tool" and slot["project"] == "simdutf")
        else ["initial_abstention"]
        if source == "tool"
        else ["initial"]
    )
    row = {
        **row,
        **slot,
        "arm_total_wall_seconds": time.monotonic() - started,
        "gate_observation": {
            "agent_phases": phases,
            "preparation_count": len(prep),
            "handoffs": handoffs,
            "expected_observation": bool(
                row["strict_completed"]
                and len(prep) == 1
                and prep[0]["exit_code"] == 0
                and phases == expected_phases
                and handoffs == int(case == "command_recovery")
                and usage["model_requests"]
                == (1 if method == METHODS[2] else len(expected_phases))
                and not any(
                    usage[k]
                    for k in (
                        "recorded_tokens",
                        "unknown_usage_requests",
                        "estimated_cost_usd_completed_responses",
                    )
                )
            ),
        },
    }
    return row


def validate(protocol):
    if (
        protocol["identity"] != IDENTITY
        or protocol["schedule"] != schedule()
        or protocol["provider_calls"] != 0
        or protocol["credentials_read"] is not False
        or protocol["max_new_provider_cost_usd"] != 0
    ):
        raise PlanContractError("身份、11槽或零Provider边界不符")
    before_deadline(protocol["deadline_utc"], 2100)
    parent_path = REPO_ROOT / PARENT_MANIFEST
    parent_manifest = json.loads(parent_path.read_text())
    if protocol["parent_manifest_sha256"] != digest(parent_path) or any(
        protocol["components"].get(k) != v
        for k, v in parent_manifest["components"].items()
    ):
        raise PlanContractError("原141冻结组件或父manifest变化")
    references = {}
    projects = []
    for bound in protocol["reference_evidence"]:
        parent = Path(bound["root"])
        if audit(parent)["inventory_canonical_sha256"] != bound["inventory_sha256"]:
            raise PlanContractError("父证据变化")
        original = json.loads((parent / "protocol.json").read_text())
        for name in bound["projects"]:
            item = next(p for p in original["projects"] if p["name"] == name)
            # buffer来自既有角色对应的完整参考，C++项目资格由原终态显式核验。
            outcomes = json.loads((parent / "result.json").read_text())["projects"]
            if not next(p for p in outcomes if p["name"] == name)["qualified"]:
                raise PlanContractError("参考任务未合格")
            if (
                digest(Path(item["source_archive"]))
                != item["plan"]["source_archive_sha256"]
            ):
                raise PlanContractError("来源归档变化")
            if (
                digest(Path(item["source_file_hashes_path"]))
                != item["source_file_hashes_sha256"]
            ):
                raise PlanContractError("原来源文件索引变化")
            project, reference = task_and_reference(item)
            projects.append(project)
            references[name] = reference
    if protocol["projects"] != projects or set(references) != {"buffer", *PROJECTS}:
        raise PlanContractError("共同任务与前瞻登记不符")
    for name, h in protocol["components"].items():
        if digest(REPO_ROOT / name) != h:
            raise PlanContractError("冻结组件变化:" + name)
    return references


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    references = validate(protocol)
    if args.validate_only:
        print(json.dumps({"valid": True, "provider_calls": 0, "slots": 11}))
        return 0
    if args.output_root is None:
        raise PlanContractError("必须使用独立新证据目录")
    subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")],
        check=True,
        timeout=30,
    )
    os.environ["COMPILE_DOCKER_CLEANUP_TIMEOUT_SECONDS"] = "120"
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    rows = []
    reason = "initialization_not_completed"
    projects = {p["name"]: p for p in protocol["projects"]}
    try:
        for i, slot in enumerate(schedule()):
            before_deadline(protocol["deadline_utc"], 2100)
            item = {
                **projects[slot["project"]],
                "name": f"{i:02d}-{slot['project']}-{slot['method']}",
            }
            row = run_slot(protocol, root, slot, item, references[slot["project"]])
            rows.append(row)
            print(
                json.dumps(
                    {
                        k: row.get(k)
                        for k in (
                            "project",
                            "method",
                            "case",
                            "strict_completed",
                            "gate_observation",
                            "agent_usage",
                            "error_message",
                        )
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            if not row["gate_observation"]["expected_observation"]:
                reason = "gate_failed"
                break
        else:
            reason = None
    finally:
        write_json(
            root / "result.json",
            {
                "identity": IDENTITY,
                "kind": "scripted_common_input_qualification",
                "arms": rows,
                "not_observed": schedule()[len(rows) :],
                "stop_reason": reason,
            },
        )
        print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
    return 0 if reason is None and len(rows) == 11 else 1


if __name__ == "__main__":
    raise SystemExit(main())
