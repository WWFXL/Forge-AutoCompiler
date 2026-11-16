#!/usr/bin/env python3
"""只读旧查询回放及诊断记录真实构建接线；零Provider、预写修复。"""

import argparse
import hashlib
import json
from pathlib import Path

from forge_libffi_dependency_guidance import load, save
from forge_libffi_diagnostic_memory import material
from forge_simple_system import ScriptedSimpleModel, run_simple_system

from deerflow.compile.recovery_diagnostic_memory import RecoveryDiagnosticMemory
from deerflow.compile.simple_build_task import SimpleBuildActions, assemble_simple_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--engineering-case", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    save(
        args.output / "scope.json",
        dict(
            identity="cpp-build-diagnostic-memory-engineering-v1",
            provider_calls=0,
            cost_usd=0,
            authorization="用户批准实现与验证诊断记录",
            historical_replay="只读；不修改旧观测或推断模型将如何行动",
            scripted_repair=True,
        ),
    )
    memory = RecoveryDiagnosticMemory()
    events_file = args.history / "libffi/agent/events.jsonl"
    events = [json.loads(line) for line in events_file.read_text().splitlines()]
    queries = [e for e in events if e["event"] == "recovery.environment_query"]
    last_handoff = None
    for event in queries:
        last_handoff = event["handoff_id"]
        name = "search_build_files" if event["operation"] == "search" else "inspect_build_environment"
        arguments = {k: event[k] for k in ("query", "scope", "kind") if k in event}
        memory.observe(name, arguments, event["result"], handoff_id=last_handoff)
    snapshot = memory.snapshot(dict(handoff_id=last_handoff))
    assert any(c["package"] == "libltdl-dev" for c in snapshot["candidates"])
    old_present = {}
    for index in (32, 33, 40):
        old_present[str(index)] = "libltdl-dev" in (args.history / f"libffi/agent/request-{index}.json").read_text()
    save(
        args.output / "historical-replay.json",
        dict(
            input_events_sha256=hashlib.sha256(events_file.read_bytes()).hexdigest(),
            actual_queries=len(queries),
            original_candidate_visible=old_present,
            new_memory=snapshot,
            effect_claim=False,
        ),
    )
    # 复用既有工程动作验证新增记录贯通执行器，不重新发现依赖、不计模型效果。
    case = load(args.engineering_case)
    task, reference, archive, recovery = material()
    calls = case["calls"]
    model = ScriptedSimpleModel(responses=[], calls=calls)
    result = run_simple_system(
        task=task,
        reference=reference,
        source_archive=archive,
        output_root=args.output / "libffi",
        method="forge",
        model=model,
        accepted_models=("zero-provider-script",),
        family="libffi",
        maximum_cost_usd="0",
        pricing_by_model={"zero-provider-script": ("0", "0")},
        initial_plan=assemble_simple_plan(task, SimpleBuildActions.model_validate(case["initial"])),
        validation_scope="main_build",
        replay_seconds=900,
        recovery_harness=recovery,
        retain_recovery_diagnostics=True,
    )
    save(args.output / "summary.json", result)
    last = load(args.output / f"libffi/agent/diagnostic-memory-request-{model.position}.json")
    candidate = next(c for c in last["candidates"] if c["package"] == "libltdl-dev")
    assert "package_description" in candidate["checks"] and candidate["checks"]["package"]["installed"] is False
    assert result["cleanup"]["succeeded"] and result["layers"]["reproducible_delivery_completed"]
    save(
        args.output / "completed.json",
        dict(
            provider_calls=0,
            cost_usd=0,
            scripted_responses=model.position,
            historical_candidate_retained=True,
            candidate_checked_in_real_container=True,
            layers=result["layers"],
            cleanup=result["cleanup"],
        ),
    )
    print(json.dumps(load(args.output / "completed.json"), ensure_ascii=False))


if __name__ == "__main__":
    main()
