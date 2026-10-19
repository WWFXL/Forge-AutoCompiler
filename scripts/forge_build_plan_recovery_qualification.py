#!/usr/bin/env python3
"""三系统既有人工方案的受控失效与模型恢复资格，非自然失败效果比较。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "backend/packages/harness"), str(REPO_ROOT / "scripts")]

from forge_build_plan_agent_canary import audit_frozen, run_arm  # noqa: E402
from forge_build_plan_paired_comparison import ComparisonMeter, charged_cost, normalized_reference  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.plan_agent import PlanProposal, PlanTask  # noqa: E402
from deerflow.compile.plan_agent_context import propose_with_context  # noqa: E402
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek  # noqa: E402
from deerflow.compile.plan_cross_system import SharedResearchBudget, before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import BuildPlan, PlanContractError  # noqa: E402

STATIC_STOP = "静态控制在首次交接停止，不调用模型"
NAMES = ["miniz", "pigz", "libite"]
FAULTS = {
    "miniz": {"changed_step": "build", "command": "cmake --build build --parallel 2 --target forge_missing_target_qualification", "failed_step": "build", "exit_code": 2},
    "pigz": {"changed_step": "build", "command": "make -j2 CC=forge_missing_compiler_qualification", "failed_step": "build", "exit_code": 2},
    "libite": {"changed_step": "bootstrap", "command": "true", "failed_step": "configure", "exit_code": 127},
}


def controlled_plan(reference, name):
    plan = normalized_reference(reference)
    fault = FAULTS[name]
    step = next(row for row in plan["steps"] if row["step_id"] == fault["changed_step"])
    step.update(command=fault["command"], source="受控资格：既有方案中的操作失效，需依据执行日志恢复", expected="执行既有任务，失败时移交真实日志")
    return BuildPlan.model_validate(plan)


def make_schedule(qualify):
    return [{"project": name, "mode": mode, "arm": "plan"} for name in NAMES for mode in (("normal", "static", "repair") if qualify else ("repair",))]


def qualification_planner(reference, name, mode):
    def planner(**kwargs):
        if kwargs.get("current_plan") is None:
            plan = BuildPlan.model_validate(normalized_reference(reference)) if mode == "normal" else controlled_plan(reference, name)
            kwargs["meter"].ledger.append("qualification.initial_plan", mode=mode, source="人工合格参考及预定受控注入，非模型初始规划", plan_sha256=plan.fingerprint())
            kwargs["meter"].ledger.save("initial-controlled-plan.json", plan.model_dump(mode="json"))
            return plan, "人工既有方案；费用只记录后续模型恢复，不进入RQ1全策略比较"
        if mode == "static":
            kwargs["meter"].ledger.append("qualification.static_stop", handoff=kwargs.get("handoff"))
            raise PlanContractError(STATIC_STOP)
        # 只传run_arm给出的当前坏方案、真实handoff与源码；不把正确人工参考传给真实模型。
        return propose_with_context(**kwargs)

    return planner


def inspect_recovery(folder, row, name, mode):
    metadata = list(folder.glob(".compile-sessions/*/*/session.json"))
    if len(metadata) != 1:
        return {"expected_observation": False, "reason": "session_metadata_missing"}
    session = json.loads(metadata[0].read_text())
    events = [json.loads(line) for line in (metadata[0].parent / "logs/workflow.log").read_text().splitlines() if line.strip()]
    steps = [event for event in events if event["event"] == "plan.step"]
    revisions = [event for event in events if event["event"] == "plan.revised"]
    handoffs = [state for state in row["transitions"] if state["status"] == "needs_handoff"]
    expected_failures = [event for event in steps if event["step_id"] == FAULTS[name]["failed_step"] and not event["expected_satisfied"]]
    records = {record["command_id"]: record for record in session["commands"]}
    expected_command = "./configure" if name == "libite" else FAULTS[name]["command"]
    failed = records[expected_failures[0]["command_id"]] if expected_failures else None
    initial_failure = bool(failed and failed["exit_code"] == FAULTS[name]["exit_code"] and failed["command"] == expected_command and not failed.get("timed_out"))
    common = row["cleanup"]["succeeded"] and row.get("fixed_sources_unchanged", False) and row["agent_usage"].get("cost_and_usage_complete", False)
    if mode == "normal":
        expected = row["strict_completed"] and not handoffs and not revisions
    elif mode == "static":
        expected = not row["strict_completed"] and row.get("error_message") == STATIC_STOP and initial_failure and len(handoffs) == 1 and not revisions and row["agent_usage"]["model_requests"] == 0
    else:
        expected = row["strict_completed"] and initial_failure and bool(handoffs) and bool(revisions)
    return {
        "expected_observation": bool(common and expected),
        "initial_expected_failure": initial_failure,
        "handoffs": len(handoffs),
        "revisions": [{"revision": event["revision"], "retained_steps": event["retained_steps"]} for event in revisions],
    }


def validate(protocol):
    if protocol["identity"] != "cpp-build-plan-recovery-qualification-v1" or protocol["max_estimated_cost_usd"] != 3 or protocol["deadline_utc"] != "2026-10-19T23:00:00Z":
        raise PlanContractError("恢复资格身份、费用或截止不符")
    before_deadline(protocol["deadline_utc"], 3600)
    probe_root = Path(protocol["completed_probe_evidence"])
    if audit(probe_root)["inventory_canonical_sha256"] != protocol["completed_probe_inventory_sha256"]:
        raise PlanContractError("上一阶段尚未封存")
    probe = json.loads((probe_root / "result.json").read_text())
    if len(probe["arms"]) != 12 or probe["unobserved_schedule"] or any(not row["agent_usage"]["cost_and_usage_complete"] for row in probe["arms"]):
        raise PlanContractError("上一阶段未完整结束，不并行影响配对耗时")
    source_root = Path(protocol["source_qualification_evidence"])
    if audit_frozen(source_root)["inventory_canonical_sha256"] != protocol["source_inventory_sha256"]:
        raise PlanContractError("参考资格证据变化")
    qualified = {row["name"] for row in json.loads((source_root / "result.json").read_text())["projects"] if row["qualified"]}
    references = {row["name"]: row for row in json.loads((source_root / "protocol.json").read_text())["projects"]}
    if [row["name"] for row in protocol["projects"]] != NAMES or protocol["faults"] != FAULTS or protocol["schedule"] != make_schedule(False) or protocol["gate_schedule"] != make_schedule(True):
        raise PlanContractError("固定三项目、注入或顺序改变")
    for item in protocol["projects"]:
        task = PlanTask.model_validate(item["task"])
        original = normalized_reference(references[item["name"]]["plan"])
        if item["name"] not in qualified or task.materialize(PlanProposal(reason="核对人工参考身份及完整测试", steps=BuildPlan.model_validate(original).steps), revision=1).model_dump(mode="json") != original:
            raise PlanContractError("任务偏离原始合格参考或完整测试")
        if digest(Path(item["source_archive"])) != task.source_archive_sha256:
            raise PlanContractError("源归档变化")
    for name, expected in protocol["components"].items():
        if digest(REPO_ROOT / name) != expected:
            raise PlanContractError("冻结组件变化")
    return references


def execute_schedule(protocol, root, model, references, *, qualify=False, results=None):
    rows = [] if results is None else results
    schedule = protocol["gate_schedule"] if qualify else protocol["schedule"]
    projects = {row["name"]: row for row in protocol["projects"]}
    reason = None
    for slot in schedule:
        try:
            before_deadline(protocol["deadline_utc"], 3600)
        except PlanContractError:
            reason = "deadline_reservation"
            break
        if not qualify and charged_cost(rows) + Decimal("1.50") > Decimal("3"):
            reason = "stage_cost_reservation"
            break
        name, mode = slot["project"], slot["mode"]
        item = {**projects[name], "name": f"{name}-{mode}"}
        reference = normalized_reference(references[name]["plan"])
        row = run_arm(
            item=item,
            arm="plan",
            protocol=protocol,
            root=root,
            model=model,
            reference=reference if qualify else None,
            meter_factory=ComparisonMeter,
            planner=qualification_planner(reference, name, mode),
            command_timeout_seconds=300,
            replay_timeout_seconds=600,
        )
        observation = inspect_recovery(root / f"{item['name']}-plan", row, name, mode)
        rows.append({**row, **slot, "recovery_observation": observation})
        print(json.dumps({key: rows[-1].get(key) for key in ("project", "mode", "strict_completed", "recovery_observation", "agent_usage")}), flush=True)
        if not row["cleanup"]["succeeded"] or row["agent_usage"]["unknown_usage_requests"]:
            reason = "cleanup_or_unknown_usage"
            break
    return rows, [{**slot, "status": "not_observed", "reason": reason} for slot in schedule[len(rows) :]], reason


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--shared-budget-root", type=Path, required=True)
    parser.add_argument("--qualify", action="store_true")
    parser.add_argument("--gate-root", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    references = validate(protocol)
    shared = SharedResearchBudget(args.shared_budget_root)
    if shared.authorization["deadline_utc"] != protocol["deadline_utc"] or shared.authorization["max_new_provider_cost_usd"] != 20:
        raise PlanContractError("共享授权不符")
    if args.validate_only:
        print(json.dumps({"valid": True, "provider_calls": 0}))
        return 0
    if not args.qualify:
        if args.gate_root is None:
            raise PlanContractError("缺少九槽恢复门禁")
        audit(args.gate_root)
        gate = json.loads((args.gate_root / "result.json").read_text())
        if (
            digest(args.gate_root / "protocol.json") != digest(args.protocol)
            or gate["kind"] != "scripted_engineering_gate"
            or len(gate["arms"]) != 9
            or gate["unobserved_schedule"]
            or any(not row["recovery_observation"]["expected_observation"] or row["agent_usage"]["recorded_tokens"] for row in gate["arms"])
        ):
            raise PlanContractError("九槽门禁未闭合")
    subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    (root / "authorization.json").write_bytes((args.shared_budget_root / "authorization.json").read_bytes())
    if not args.qualify:
        shared.append({"event": "stage.started", "identity": protocol["identity"], "reserved_cost_usd": "3", "protocol_sha256": digest(args.protocol), "evidence_root": str(root)})
    rows, unobserved, reason, complete = [], [], "initialization_not_completed", False
    try:
        model = None
        if not args.qualify:
            key = os.environ.get("DEEPSEEK_API_KEY")
            if not key:
                raise PlanContractError("缺少已授权Provider凭据")
            model = PlanThinkingDeepSeek(model="deepseek-v4-pro", api_key=key, base_url="https://api.deepseek.com", max_tokens=32768, max_retries=0, timeout=240, reasoning_effort="low", extra_body={"thinking": {"type": "enabled"}})
        rows, unobserved, reason = execute_schedule(protocol, root, model, references, qualify=args.qualify, results=rows)
        complete = True
    finally:
        schedule = protocol["gate_schedule"] if args.qualify else protocol["schedule"]
        if not complete:
            unobserved = [{**slot, "status": "not_observed_or_unclosed", "reason": reason} for slot in schedule[len(rows) :]]
        known = sum((Decimal(str(row["agent_usage"]["estimated_cost_usd_completed_responses"])) for row in rows), Decimal(0))
        unknown = sum(row["agent_usage"]["unknown_usage_requests"] for row in rows)
        write_json(
            root / "result.json",
            {
                "identity": protocol["identity"],
                "kind": "scripted_engineering_gate" if args.qualify else "controlled_recovery_qualification",
                "arms": rows,
                "unobserved_schedule": unobserved,
                "stopping_reason": reason,
                "known_estimated_cost_usd": str(known),
                "unknown_usage_reservation_usd": str(Decimal("0.40") * unknown),
            },
        )
        sealed = seal(root, protocol, REPO_ROOT, unknown)
        if not args.qualify and complete:
            shared.append(
                {
                    "event": "stage.completed",
                    "identity": protocol["identity"],
                    "charged_cost_usd": str(charged_cost(rows)),
                    "known_estimate_usd": str(known),
                    "unknown_reservation_usd": str(Decimal("0.40") * unknown),
                    "inventory_sha256": sealed["inventory_canonical_sha256"],
                }
            )
    return 0 if len(rows) == len(schedule) and not unobserved and all(row["recovery_observation"]["expected_observation"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
