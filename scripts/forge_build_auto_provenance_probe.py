#!/usr/bin/env python3
"""后验接口归因探针：新鲜plan与自动配方溯源工具Agent，不修改父比较。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "backend/packages/harness"), str(REPO_ROOT / "scripts")]

from forge_build_plan_agent_canary import run_arm  # noqa: E402
from forge_build_plan_paired_comparison import ComparisonMeter, charged_cost, make_schedule, normalized_reference  # noqa: E402
from forge_build_plan_paired_comparison import validate as validate_parent  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.plan_agent_context import propose_with_context  # noqa: E402
from deerflow.compile.plan_agent_provenance import run_tool_agent_automatic  # noqa: E402
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek  # noqa: E402
from deerflow.compile.plan_cross_system import SharedResearchBudget, before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402


def automatic_gate_model(reference):
    """零Provider工具接线，末次提交为真正的无参数接口。"""
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    class GateModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    def reply(calls):
        return AIMessage(
            content="",
            tool_calls=[{"name": name, "args": arguments, "id": f"gate-{index}"} for index, (name, arguments) in enumerate(calls)],
            usage_metadata={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            response_metadata={"model_name": "scripted-gate"},
        )

    calls = [("run_fixed_tests", {}) if step["role"] == "smoke" else ("run_build_command", {"command": step["command"], "command_role": step["role"], "workdir": step["workdir"]}) for step in reference["steps"]]
    return GateModel(responses=[reply([*calls, ("submit_verified_build", {})])])


def validate(protocol):
    if protocol["identity"] != "cpp-build-auto-provenance-probe-v1" or protocol["max_estimated_cost_usd"] != 6 or protocol["deadline_utc"] != "2026-10-19T23:00:00Z":
        raise PlanContractError("接口探针身份、共享预算或截止错误")
    before_deadline(protocol["deadline_utc"], 3600)
    parent_root = Path(protocol["parent_evidence"])
    if audit(parent_root)["inventory_canonical_sha256"] != protocol["parent_inventory_sha256"]:
        raise PlanContractError("父比较封存身份不符")
    parent = json.loads((parent_root / "protocol.json").read_text())
    outcome = json.loads((parent_root / "result.json").read_text())
    if len(outcome["arms"]) != 24 or outcome["unobserved_schedule"] or any(not row["agent_usage"]["cost_and_usage_complete"] for row in outcome["arms"]):
        raise PlanContractError("父比较尚未完整闭合")
    references = validate_parent(parent)
    names = ["libsndfile", "buffer", "libverto"]
    selection_path = Path(protocol["selection_record"]["path"])
    if digest(selection_path) != protocol["selection_record"]["sha256"]:
        raise PlanContractError("候选选样记录变化")
    selection = json.loads(selection_path.read_text())
    if (
        selection["selected_projects"] != names
        or any(selection["selected_parent_r2_results_exist"].values())
        or selection["candidate_preregistration_sha256"] != protocol["components"].get("benchmarks/preregistrations/cpp-build-auto-provenance-probe-v1.md")
    ):
        raise PlanContractError("候选选样记录与冻结协议不符")
    by_name = {item["name"]: item for item in parent["projects"]}
    if protocol["projects"] != [by_name[name] for name in names] or protocol["provider"] != parent["provider"] or protocol["runtime"] != parent["runtime"]:
        raise PlanContractError("探针不能改变父任务、测试、模型或共同资源")
    if protocol["schedule"] != make_schedule(names) or protocol["gate_schedule"] != make_schedule(names, 1):
        raise PlanContractError("固定三系统双重复配对被改变")
    if any(protocol["components"].get(name) != value for name, value in parent["components"].items()):
        raise PlanContractError("父比较的共同执行组件发生变化")
    for name, expected in protocol["components"].items():
        if digest(REPO_ROOT / name) != expected:
            raise PlanContractError("探针运行组件偏离冻结")
    return references


def execute_schedule(protocol, root, model, references, *, qualify=False, executor=run_arm, results=None):
    rows = [] if results is None else results
    schedule = protocol["gate_schedule"] if qualify else protocol["schedule"]
    projects = {item["name"]: item for item in protocol["projects"]}
    reason = None
    for slot in schedule:
        try:
            before_deadline(protocol["deadline_utc"], 3600)
        except PlanContractError:
            reason = "deadline_reservation"
            break
        if not qualify and charged_cost(rows) + Decimal("1.50") > Decimal("6"):
            reason = "stage_cost_reservation"
            break
        reference = normalized_reference(references[slot["project"]]["plan"]) if qualify else None

        def tool_runner(**kwargs):
            # 旧runner创建的人工GateModel不运行；工具门禁替换为无参数提交的独立Fake。
            if qualify:
                kwargs["model"] = automatic_gate_model(reference)
            return run_tool_agent_automatic(**kwargs)

        started = time.monotonic()
        row = executor(
            item={**projects[slot["project"]], "name": f"{slot['project']}-r{slot['repetition']}"},
            arm=slot["arm"],
            protocol=protocol,
            root=root,
            model=model,
            reference=reference,
            meter_factory=ComparisonMeter,
            planner=propose_with_context,
            tool_runner=tool_runner,
            command_timeout_seconds=300,
            replay_timeout_seconds=600,
        )
        rows.append({**row, "project": slot["project"], "repetition": slot["repetition"], "arm_total_wall_seconds": time.monotonic() - started})
        print(json.dumps({key: rows[-1].get(key) for key in ("project", "repetition", "arm", "strict_completed", "agent_usage")}), flush=True)
        if not row["cleanup"]["succeeded"] or row["agent_usage"]["unknown_usage_requests"]:
            reason = "cleanup_or_unknown_usage"
            break
    return rows, [{**slot, "status": "not_observed", "reason": reason} for slot in schedule[len(rows) :]], reason


def analyze(protocol, payload):
    rows = payload["arms"]
    expected = protocol["schedule"]
    if [{key: row[key] for key in ("project", "repetition", "arm")} for row in rows] != expected[: len(rows)]:
        raise PlanContractError("探针观察顺序不符")
    permitted = len(rows) == 12 and not payload["unobserved_schedule"] and all(row["agent_usage"]["cost_and_usage_complete"] for row in rows)
    result = {"paired_description_permitted": permitted, "observed_arms": len(rows), "scope": "后验选择三固定任务/三系统/双重复；不估计一般因果、非劣、总体CI或成熟Agent排名"}
    metrics = {
        "strict_completed": lambda row: int(row["strict_completed"]),
        "requests": lambda row: row["agent_usage"]["model_requests"],
        "tokens": lambda row: row["agent_usage"]["recorded_tokens"],
        "cost_usd": lambda row: float(row["agent_usage"]["estimated_cost_usd_completed_responses"]),
        "commands": lambda row: row["agent_usage"]["commands"],
        "wall_seconds": lambda row: row["arm_total_wall_seconds"],
    }
    result["observed_totals"] = {arm: {name: sum(value(row) for row in rows if row["arm"] == arm) for name, value in metrics.items()} for arm in ("plan", "tool")}
    if permitted:
        result["project_means"] = {
            item["name"]: {arm: {name: sum(value(row) for row in rows if row["project"] == item["name"] and row["arm"] == arm) / 2 for name, value in metrics.items()} for arm in ("plan", "tool")} for item in protocol["projects"]
        }
    return result


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
        raise PlanContractError("共享授权不匹配")
    if args.validate_only:
        print(json.dumps({"valid": True, "provider_calls": 0}))
        return 0
    if not args.qualify:
        if args.gate_root is None:
            raise PlanContractError("缺少同协议六臂零Provider门禁")
        audit(args.gate_root)
        gate = json.loads((args.gate_root / "result.json").read_text())
        if (
            digest(args.gate_root / "protocol.json") != digest(args.protocol)
            or gate["kind"] != "scripted_engineering_gate"
            or gate["unobserved_schedule"]
            or len(gate["arms"]) != 6
            or any(not row["strict_completed"] or row["agent_usage"]["recorded_tokens"] for row in gate["arms"])
        ):
            raise PlanContractError("同协议门禁未闭合")
    subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    (root / "authorization.json").write_bytes((args.shared_budget_root / "authorization.json").read_bytes())
    (root / "selection-record.json").write_bytes(Path(protocol["selection_record"]["path"]).read_bytes())
    if not args.qualify:
        shared.append({"event": "stage.started", "identity": protocol["identity"], "reserved_cost_usd": "6", "protocol_sha256": digest(args.protocol), "evidence_root": str(root)})
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
                "kind": "scripted_engineering_gate" if args.qualify else "posthoc_interface_probe",
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
    return 0 if len(rows) == len(schedule) and not unobserved and (not args.qualify or all(row["strict_completed"] for row in rows)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
