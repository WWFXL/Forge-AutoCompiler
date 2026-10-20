#!/usr/bin/env python3
"""新观察接口的零Provider资格；仅本地脚本模型，不存在付费执行分支。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "backend/packages/harness"), str(REPO_ROOT / "scripts")]

from forge_build_full_strategy_cleanup_continuation import classified_arm  # noqa: E402
from forge_build_full_strategy_runtime_v2 import QualificationAwareMeter  # noqa: E402
from forge_build_unified_plan import validate as validate_parent  # noqa: E402
from forge_typed_evidence import digest, seal, write_json  # noqa: E402

from deerflow.compile.plan_cross_system import before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402
from deerflow.compile.unified_plan_v2 import ObservedBuildActions, observed_planner, observed_tool_actions  # noqa: E402

IDENTITY = "cpp-build-plan-predicate-qualification-v1"
PARENT = "benchmarks/manifests/cpp-build-unified-plan-gate-v2.json"
METHODS = ("tool_plan_workflow", "model_plan_workflow")


def schedule():
    rows = [{"project": p, "method": m, "case": "normal"} for p in ("buffer", "uncrustify", "libverto") for m in METHODS]
    rows += [{"project": "buffer", "method": m, "case": c} for c in ("command_recovery", "stdout_path_repair") for m in METHODS]
    rows += [{"project": "buffer", "method": METHODS[1], "case": c} for c in ("legacy_field_correction", "stage_order_correction", "no_change_correction")]
    rows += [{"project": "buffer", "method": METHODS[0], "case": "missing_path_rejected"}]
    return rows


def reference_actions(reference):
    steps = []
    for step in reference["steps"]:
        if step["role"] not in ("dependency", "configure", "build"):
            continue
        value = dict(step)
        value["stdout_contains"] = value.pop("required_output", [])
        steps.append(value)
    return ObservedBuildActions(reason="零Provider参考脚本，仅工程资格", steps=steps)


def qualify_paths(actions, build_system):
    """人工开发夹具的可观察路径，不能进入正式模型或工具规划器。"""
    value = actions.model_dump(mode="json")
    for step in value["steps"]:
        if build_system == "cmake" and step["role"] == "configure":
            step.update(files_exist=["build/CMakeCache.txt"], directories_exist=["build/"], diagnostic_paths=["build/"])
        if step["role"] == "build" and build_system in ("make", "autotools"):
            step.update(files_exist=["test"] if build_system == "make" else ["src/.libs/libverto.a"], directories_exist=[] if build_system == "make" else ["src/.libs/"])
    return ObservedBuildActions.model_validate(value)


def controlled_actions(actions, case, *, initial):
    value = actions.model_dump(mode="json")
    if case in ("command_recovery", "no_change_correction"):
        value["steps"].insert(0, {"step_id": "gate-configure", "role": "configure", "command": "true", "source": "受控前缀", "expected": "一次成功"})
        if initial:
            value["steps"][-1]["command"] = "false"
    if case == "stdout_path_repair":
        if initial:
            value["steps"][-1]["stdout_contains"] = ["/workspace/repo/test"]
        else:
            value["steps"][-1]["files_exist"] = ["test"]
    if case == "missing_path_rejected":
        value["steps"][-1]["files_exist"] = ["forge_controlled_missing.a"]
    return ObservedBuildActions.model_validate(value)


def fake_model(values):
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    class GateModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    return GateModel(
        responses=[
            AIMessage(
                content="", tool_calls=[{"name": "ObservedBuildActions", "args": v, "id": f"predicate-{i}"}], usage_metadata={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}, response_metadata={"model_name": "scripted-gate"}
            )
            for i, v in enumerate(values)
        ]
    )


def run_slot(protocol, root, slot, item, reference):
    source = "tool" if slot["method"] == METHODS[0] else "model"
    case = slot["case"]
    good = qualify_paths(reference_actions(reference), item["task"]["build_system"])
    first = controlled_actions(good, case, initial=True)
    recovered = controlled_actions(good, case, initial=False)
    proposals = [first.model_dump(mode="json")] if source == "model" else []
    if case in ("command_recovery", "stdout_path_repair"):
        proposals.append(recovered.model_dump(mode="json"))
    if case == "no_change_correction":
        proposals += [first.model_dump(mode="json"), recovered.model_dump(mode="json")]
    if case in ("legacy_field_correction", "stage_order_correction"):
        bad = first.model_dump(mode="json")
        if case == "legacy_field_correction":
            bad["steps"][-1]["required_output"] = ["build/CMakeCache.txt"]
        else:
            bad["steps"].append({"step_id": "late-configure", "role": "configure", "command": "true", "source": "受控错误", "expected": "顺序非法"})
        proposals = [bad, first.model_dump(mode="json")]
    if case == "missing_path_rejected":
        proposals = [first.model_dump(mode="json")] * 2
    active_model = fake_model(proposals)

    def generator(task, source_root):
        actions, receipt = observed_tool_actions(task, source_root)
        return controlled_actions(qualify_paths(actions, task.build_system), case, initial=True), receipt

    base = observed_planner(source, generator=generator)

    def planner(**kwargs):
        return base(**{**kwargs, "model": active_model})

    started = time.monotonic()
    row = classified_arm(item=item, arm="plan", protocol=protocol, root=root, reference=reference, planner=planner, meter_factory=QualificationAwareMeter, command_timeout_seconds=600, replay_timeout_seconds=900)
    folder = root / (item["name"] + "-plan")
    events = [json.loads(s) for s in (folder / "agent/events.jsonl").read_text().splitlines()]
    rejections = [e for e in events if e["event"] == "observed.proposal_rejected"]
    handoffs = sum(s["status"] == "needs_handoff" for s in row["transitions"])
    expected_handoffs = int(case in ("command_recovery", "stdout_path_repair", "no_change_correction", "missing_path_rejected"))
    expected_rejections = 2 if case == "missing_path_rejected" else int(case in ("legacy_field_correction", "stage_order_correction", "no_change_correction"))
    expected_strict = case != "missing_path_rejected"
    usage = row["agent_usage"]
    expected = (
        row["strict_completed"] == expected_strict
        and handoffs == expected_handoffs
        and len(rejections) == expected_rejections
        and usage["model_requests"] == len(proposals)
        and usage["recorded_tokens"] == usage["unknown_usage_requests"] == usage["estimated_cost_usd_completed_responses"] == 0
        and row["cleanup"]["succeeded"]
    )
    if not expected_strict:
        expected = expected and row.get("error_class") == "PlanContractError" and "no_execution_change" in row.get("error_message", "")
    return {**row, **slot, "arm_total_wall_seconds": time.monotonic() - started, "gate_observation": {"expected_observation": bool(expected), "handoffs": handoffs, "proposal_rejections": len(rejections), "expected_strict": expected_strict}}


def validate(protocol):
    parent = json.loads((REPO_ROOT / PARENT).read_text())
    references = validate_parent(parent)
    if protocol["identity"] != IDENTITY or protocol["provider_calls"] != 0 or protocol["max_new_provider_cost_usd"] != 0 or protocol["schedule"] != schedule() or protocol["projects"] != parent["projects"]:
        raise PlanContractError("身份、零Provider边界、固定开发任务或顺序不符")
    if protocol["parent_protocol_sha256"] != digest(REPO_ROOT / PARENT):
        raise PlanContractError("父协议变化")
    historical = json.loads((REPO_ROOT / "benchmarks/manifests/cpp-build-unified-plan-comparison-v1.json").read_text())["components"]
    if any(protocol["components"].get(name) != sha for name, sha in historical.items()):
        raise PlanContractError("107历史组件必须原样保留")
    for name, sha in protocol["components"].items():
        if digest(REPO_ROOT / name) != sha:
            raise PlanContractError("组件变化：" + name)
    return references


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    references = validate(protocol)
    if args.validate_only:
        print(json.dumps({"valid": True, "provider_calls": 0, "slots": len(schedule())}))
        return 0
    before_deadline(protocol["deadline_utc"], 2100)
    subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    os.environ["COMPILE_DOCKER_CLEANUP_TIMEOUT_SECONDS"] = "120"
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    rows, reason = [], None
    projects = {p["name"]: p for p in protocol["projects"]}
    try:
        for i, slot in enumerate(protocol["schedule"]):
            before_deadline(protocol["deadline_utc"], 2100)
            item = {**projects[slot["project"]], "name": f"{i:02d}-{slot['project']}-{slot['method']}-{slot['case']}"}
            row = run_slot(protocol, root, slot, item, references[slot["project"]])
            rows.append(row)
            print(json.dumps({k: row.get(k) for k in ("name", "strict_completed", "gate_observation", "agent_usage", "error_message")}, ensure_ascii=False), flush=True)
            if not row["gate_observation"]["expected_observation"]:
                reason = "gate_failed"
                break
    finally:
        write_json(
            root / "result.json",
            {
                "identity": IDENTITY,
                "kind": "zero_provider_observation_interface_qualification",
                "arms": rows,
                "not_observed": protocol["schedule"][len(rows) :],
                "stop_reason": reason,
                "research_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip(),
            },
        )
        print(json.dumps(seal(root, protocol, REPO_ROOT), ensure_ascii=False), flush=True)
    return 0 if len(rows) == len(schedule()) and reason is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
