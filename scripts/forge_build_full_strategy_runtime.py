#!/usr/bin/env python3
"""三策略统一入口；工程门禁与真实模型结果分开封存，旧身份禁止续跑。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "backend/packages/harness"), str(REPO_ROOT / "scripts")]

from forge_build_auto_provenance_probe import automatic_gate_model  # noqa: E402
from forge_build_full_strategy_components import planner_with_rules  # noqa: E402
from forge_build_plan_agent_canary import run_arm  # noqa: E402
from forge_build_plan_paired_comparison import charged_cost, normalized_reference  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.plan_agent import PlanProposal, PlanTask  # noqa: E402
from deerflow.compile.plan_agent_context import propose_with_context  # noqa: E402
from deerflow.compile.plan_agent_provenance import run_tool_agent_automatic  # noqa: E402
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek  # noqa: E402
from deerflow.compile.plan_cross_system import SharedResearchBudget, before_deadline  # noqa: E402
from deerflow.compile.plan_handoff_context import HandoffContextMeter  # noqa: E402
from deerflow.compile.plan_workflow import BuildPlan, PlanContractError  # noqa: E402

IDENTITY = "cpp-build-full-strategy-runtime-v1"
DESIGN = "benchmarks/analyses/cpp-build-full-strategy-comparison-v1.json"
METHODS = ("strong_tool_agent", "plan_workflow_failure_agent", "plan_workflow_rules_failure_agent")
RESERVE = 3900


class StrategyMeter(HandoffContextMeter):
    """三方法共同资源；保留原消息、Token、费用和请求限制。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tracker.limits = replace(self.tracker.limits, command_timeout_seconds=600, evaluator_timeout_seconds=900, replay_timeout_seconds=900, cleanup_timeout_seconds=120)

    def _before_request(self):
        before_deadline(self.deadline, RESERVE)
        return super()._before_request()


def gate_schedule():
    rows = [{"project": name, "repetition": 1, "method": method, "case": "normal"} for name in ("buffer", "uncrustify", "libverto") for method in METHODS]
    rows.extend(
        [
            {"project": "buffer", "repetition": 1, "method": METHODS[1], "case": "agent_recovery"},
            {"project": "uncrustify", "repetition": 1, "method": METHODS[2], "case": "rule_recovery"},
            {"project": "buffer", "repetition": 1, "method": METHODS[2], "case": "uncovered_to_agent"},
            {"project": "uncrustify", "repetition": 1, "method": METHODS[2], "case": "rule_then_agent"},
        ]
    )
    return rows


def gate_plan_model(reference, case):
    """仅工程门禁使用人工方案；修订仍经过真实规划器、工具及预算接线。"""
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    class GateModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    bad = normalized_reference(reference)
    if case in ("agent_recovery", "uncovered_to_agent"):
        next(s for s in bad["steps"] if s["step_id"] == "build")["command"] = "false"
    elif case in ("rule_recovery", "rule_then_agent"):
        next(s for s in bad["steps"] if s["step_id"] == "build")["command"] += " --target forge_missing_target_qualification"
        if case == "rule_then_agent":
            next(s for s in bad["steps"] if s["step_id"] == "stage")["command"] = "false"
    plans = [bad] if case == "normal" else [bad, reference]
    return GateModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "PlanProposal", "args": {"reason": "零Provider工程门禁，非模型效果", "steps": p["steps"]}, "id": f"gate-plan-{i}"}],
                usage_metadata={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                response_metadata={"model_name": "scripted-gate"},
            )
            for i, p in enumerate(plans)
        ]
    )


def validate(protocol):
    design = json.loads((REPO_ROOT / DESIGN).read_text())
    if protocol["identity"] != IDENTITY or protocol["design_sha256"] != digest(REPO_ROOT / DESIGN):
        raise PlanContractError("执行身份或科学设计变化")
    if protocol["schedule"] != design["schedule"] or protocol["projects"] != design["projects"] or protocol["runtime"] != design["common_runtime"] or protocol["provider"] != design["model_candidate"]:
        raise PlanContractError("执行不能改变项目、顺序、模型或共同资源")
    if protocol["gate_schedule"] != gate_schedule() or protocol["max_estimated_cost_usd"] != 20 or protocol["deadline_utc"] != "2026-10-20T03:48:10Z":
        raise PlanContractError("门禁、预算或时窗不符")
    before_deadline(protocol["deadline_utc"], 120)
    roles = Path(design["role_evidence"]["root"])
    if audit(roles)["inventory_canonical_sha256"] != design["role_evidence"]["inventory_sha256"]:
        raise PlanContractError("角色证据变化")
    role_rows = json.loads((roles / "result.json").read_text())["projects"]
    by_name = {p["name"]: p for p in role_rows}
    expected_gate = [{k: by_name[name][k] for k in ("name", "task", "source_archive", "source_paths", "reference_root", "reference_inventory_sha256")} for name in ("buffer", "uncrustify", "libverto")]
    if protocol["gate_projects"] != expected_gate:
        raise PlanContractError("门禁只能使用预定开发角色")
    references, checked = {}, set()
    for item in [*protocol["projects"], *protocol["gate_projects"]]:
        parent = Path(item["reference_root"])
        if parent not in checked:
            if audit(parent)["inventory_canonical_sha256"] != item["reference_inventory_sha256"]:
                raise PlanContractError("参考证据变化")
            checked.add(parent)
        qualified = {p["name"] for p in json.loads((parent / "result.json").read_text())["projects"] if p.get("qualified")}
        ref = next(p for p in json.loads((parent / "protocol.json").read_text())["projects"] if p["name"] == item["name"])
        original = BuildPlan.model_validate(ref["plan"])
        task = PlanTask.model_validate(item["task"])
        if item["name"] not in qualified or task.materialize(PlanProposal(reason="验证任务同源及完整测试", steps=original.steps), revision=original.revision) != original:
            raise PlanContractError("任务不符合完整合格参考")
        if digest(Path(item["source_archive"])) != task.source_archive_sha256:
            raise PlanContractError("源码归档变化")
        references[item["name"]] = normalized_reference(ref["plan"])
    for name, expected in protocol["components"].items():
        if digest(REPO_ROOT / name) != expected:
            raise PlanContractError(f"冻结组件变化：{name}")
    return references


def gate_observation(root, item_name, arm, row, slot):
    folder = root / f"{item_name}-{arm}"
    event_path = folder / "agent/events.jsonl"
    events = [json.loads(line) for line in event_path.read_text().splitlines()] if event_path.exists() else []
    rules = [e for e in events if e["event"] == "strategy.rule_revision"]
    agents = [e for e in events if e["event"] == "strategy.agent_planner" and e["phase"] == "recovery"]
    handoffs = sum(s["status"] == "needs_handoff" for s in row["transitions"])
    case = slot["case"]
    expected_counts = {"normal": (0, 0, 0), "agent_recovery": (0, 0, 1), "rule_recovery": (1, 0, 1), "uncovered_to_agent": (0, 1, 1), "rule_then_agent": (1, 1, 2)}[case]
    actual = (len(rules), len(agents), handoffs)
    # 无规则臂直接调用同一planner，恢复通过真实handoff及修订事件核对。
    common = row["strict_completed"] and row.get("fixed_sources_unchanged") and row["agent_usage"]["recorded_tokens"] == 0 and row["agent_usage"]["unknown_usage_requests"] == 0
    return {"expected_observation": bool(common and actual == expected_counts), "rules": len(rules), "fallback_agent_calls": len(agents), "handoffs": handoffs}


def execute(protocol, root, model, references, *, qualify, executor=run_arm, results=None):
    rows = [] if results is None else results
    schedule = protocol["gate_schedule"] if qualify else protocol["schedule"]
    projects = {p["name"]: p for p in protocol["gate_projects"] if qualify} if qualify else {p["name"]: p for p in protocol["projects"]}
    reason = None
    for index, slot in enumerate(schedule):
        try:
            before_deadline(protocol["deadline_utc"], 120 if qualify else RESERVE)
        except PlanContractError:
            reason = "deadline_reservation"
            break
        if not qualify and charged_cost(rows) + Decimal("1.50") > Decimal(str(protocol["max_estimated_cost_usd"])):
            reason = "stage_cost_reservation"
            break
        method = slot["method"]
        arm = "tool" if method == METHODS[0] else "plan"
        name = f"{index:02d}-{slot['project']}-r{slot['repetition']}-{method}"
        reference = references[slot["project"]] if qualify else None
        active_model = gate_plan_model(reference, slot["case"]) if qualify and arm == "plan" else model

        def planner(**kwargs):
            if qualify:
                kwargs["model"] = active_model
            return propose_with_context(**kwargs)

        def tool_runner(**kwargs):
            if qualify:
                kwargs["model"] = automatic_gate_model(reference)
            return run_tool_agent_automatic(**kwargs)

        started = time.monotonic()
        row = executor(
            item={**projects[slot["project"]], "name": name},
            arm=arm,
            protocol=protocol,
            root=root,
            model=model,
            reference=reference,
            meter_factory=StrategyMeter,
            planner=planner_with_rules(planner) if method == METHODS[2] else planner,
            tool_runner=tool_runner,
            command_timeout_seconds=600,
            replay_timeout_seconds=900,
        )
        row = {**row, **slot, "arm_total_wall_seconds": time.monotonic() - started}
        if qualify:
            row["gate_observation"] = gate_observation(root, name, arm, row, slot)
        rows.append(row)
        print(json.dumps({k: row.get(k) for k in ("project", "method", "case", "strict_completed", "error_class", "error_message", "gate_observation", "agent_usage")}, ensure_ascii=False), flush=True)
        if not row["cleanup"]["succeeded"] or row["agent_usage"]["unknown_usage_requests"]:
            reason = "cleanup_or_unknown_usage"
            break
        if qualify and not row["gate_observation"]["expected_observation"]:
            reason = "engineering_gate_failed"
            break
    return rows, [{**s, "status": "not_observed", "reason": reason} for s in schedule[len(rows) :]], reason


def require_gate(protocol_path, gate_root):
    audit(gate_root)
    gate = json.loads((gate_root / "result.json").read_text())
    if (
        digest(gate_root / "protocol.json") != digest(protocol_path)
        or gate["kind"] != "scripted_engineering_gate"
        or len(gate["arms"]) != len(gate_schedule())
        or gate["unobserved_schedule"]
        or not all(r["gate_observation"]["expected_observation"] and r["agent_usage"]["recorded_tokens"] == 0 for r in gate["arms"])
    ):
        raise PlanContractError("同协议三策略端到端门禁未闭合")


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
    if args.shared_budget_root.resolve() != Path(protocol["authorization"]["root"]).resolve() or digest(args.shared_budget_root / "authorization.json") != protocol["authorization"]["sha256"]:
        raise PlanContractError("授权文件身份或哈希变化")
    if shared.authorization["deadline_utc"] != protocol["deadline_utc"] or shared.authorization["max_new_provider_cost_usd"] != 20:
        raise PlanContractError("本轮共享授权不符")
    if args.validate_only:
        print(json.dumps({"valid": True, "provider_calls": 0}))
        return 0
    if not args.qualify:
        if args.gate_root is None:
            raise PlanContractError("缺少门禁证据")
        require_gate(args.protocol, args.gate_root)
        before_deadline(protocol["deadline_utc"], RESERVE)
    subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    os.environ["COMPILE_DOCKER_CLEANUP_TIMEOUT_SECONDS"] = "120"
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    (root / "authorization.json").write_bytes((args.shared_budget_root / "authorization.json").read_bytes())
    rows, unobserved, reason, lifecycle_complete = [], [], "initialization_not_completed", False
    if not args.qualify:
        shared.append({"event": "stage.started", "identity": protocol["identity"], "reserved_cost_usd": "20", "protocol_sha256": digest(args.protocol), "evidence_root": str(root)})
    try:
        model = None
        if not args.qualify:
            key = os.environ.get("DEEPSEEK_API_KEY")
            if not key:
                raise PlanContractError("缺少已授权Provider凭据")
            model = PlanThinkingDeepSeek(model="deepseek-v4-pro", api_key=key, base_url="https://api.deepseek.com", max_tokens=32768, max_retries=0, timeout=240, reasoning_effort="low", extra_body={"thinking": {"type": "enabled"}})
        rows, unobserved, reason = execute(protocol, root, model, references, qualify=args.qualify, results=rows)
        lifecycle_complete = True
    finally:
        schedule = protocol["gate_schedule"] if args.qualify else protocol["schedule"]
        if len(rows) + len(unobserved) != len(schedule):
            unobserved = [{**s, "status": "not_observed_or_unclosed", "reason": reason} for s in schedule[len(rows) :]]
        known = sum((Decimal(str(r["agent_usage"]["estimated_cost_usd_completed_responses"])) for r in rows), Decimal(0))
        unknown = sum(r["agent_usage"]["unknown_usage_requests"] for r in rows)
        write_json(
            root / "result.json",
            {
                "identity": protocol["identity"],
                "kind": "scripted_engineering_gate" if args.qualify else "prospective_fixed_task_comparison",
                "arms": rows,
                "unobserved_schedule": unobserved,
                "stopping_reason": reason,
                "lifecycle_complete": lifecycle_complete,
                "known_estimated_cost_usd": str(known),
                "unknown_usage_reservation_usd": str(Decimal("0.40") * unknown),
            },
        )
        sealed = seal(root, protocol, REPO_ROOT, unknown)
        if not args.qualify and lifecycle_complete:
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
    return 0 if not unobserved and (not args.qualify or all(r["gate_observation"]["expected_observation"] for r in rows)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
