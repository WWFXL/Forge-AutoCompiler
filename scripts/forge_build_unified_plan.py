#!/usr/bin/env python3
"""共享方案契约零Provider门禁及公平比较入口；付费必须另绑定有效授权。"""

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

from forge_build_auto_provenance_probe import automatic_gate_model  # noqa: E402
from forge_build_full_strategy_cleanup_continuation import classified_arm  # noqa: E402
from forge_build_full_strategy_runtime import StrategyMeter  # noqa: E402
from forge_build_full_strategy_runtime_v2 import QualificationAwareMeter  # noqa: E402
from forge_build_plan_paired_comparison import normalized_reference  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.plan_agent import PlanTask  # noqa: E402
from deerflow.compile.plan_agent_provenance import run_tool_agent_automatic  # noqa: E402
from deerflow.compile.plan_cross_system import before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402
from deerflow.compile.tool_plan import ToolPlanNeedsAgent  # noqa: E402
from deerflow.compile.unified_plan import BuildActions, tool_actions, unified_planner  # noqa: E402

IDENTITY = "cpp-build-unified-plan-gate-v2"
METHODS = ("tool_plan_workflow", "model_plan_workflow", "strong_tool_agent")


def gate_schedule():
    rows = [{"project": p, "method": m, "case": "normal", "repetition": 1} for p in ("buffer", "uncrustify", "libverto") for m in METHODS[:2]]
    rows += [{"project": "buffer", "method": m, "case": "controlled_build_recovery", "repetition": 1} for m in METHODS[:2]]
    rows += [{"project": "buffer", "method": METHODS[0], "case": "controlled_initial_abstention", "repetition": 1}]
    return rows


def core(reference):
    return BuildActions(reason="零Provider脚本资格，非真实模型效果", steps=[s for s in reference["steps"] if s["role"] in ("dependency", "configure", "build")])


def bad_actions(actions):
    # 保留一个实际完成的configure前缀，再让build真实失败；恢复须保留此前缀。
    value = actions.model_dump(mode="json")
    value["steps"].insert(0, {"step_id": "gate-configure", "role": "configure", "command": "true", "source": "受控接线门禁", "expected": "前缀成功"})
    value["steps"][-1]["command"] = "false"
    return BuildActions.model_validate(value)


def recovered_actions(actions):
    value = bad_actions(actions).model_dump(mode="json")
    value["steps"][-1]["command"] = actions.steps[-1].command
    return BuildActions.model_validate(value)


def gate_model(actions):
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    class GateModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    return GateModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "BuildActions", "args": a.model_dump(mode="json"), "id": f"gate-{i}"}],
                usage_metadata={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                response_metadata={"model_name": "scripted-gate"},
            )
            for i, a in enumerate(actions)
        ]
    )


def slot_runner(*, protocol, root, slot, item, model=None, reference=None, qualify=False, executor=classified_arm):
    method = slot["method"]
    arm = "tool" if method == METHODS[2] else "plan"
    planner = unified_planner("tool" if method == METHODS[0] else "model")
    active_model = model
    if qualify and arm == "plan":
        original = core(reference)
        case = slot["case"]
        proposals = [original]
        if case == "controlled_build_recovery":
            proposals = ([bad_actions(original)] if method == METHODS[1] else []) + [recovered_actions(original)]
        active_model = gate_model(proposals)

        def generator(task, source_root):
            actions, receipt = tool_actions(task, source_root)
            if case == "controlled_initial_abstention":
                raise ToolPlanNeedsAgent("受控初始拒绝门禁，非自然模板覆盖结论")
            if case == "controlled_build_recovery":
                actions = bad_actions(actions)
            return actions, {**receipt, "gate_control": case}

        base = unified_planner("tool" if method == METHODS[0] else "model", generator=generator)

        def planner(**kwargs):
            return base(**{**kwargs, "model": active_model})

    def tool_runner(**kwargs):
        return run_tool_agent_automatic(**{**kwargs, "model": automatic_gate_model(reference) if qualify else model})

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
    row = {**row, **slot, "kind": "scripted_unified_contract_gate" if qualify else "prospective_shared_contract_comparison", "arm_total_wall_seconds": time.monotonic() - started}
    if qualify:
        events = [json.loads(s) for s in (root / f"{item['name']}-{arm}" / "agent/events.jsonl").read_text().splitlines()]
        agents = [e["phase"] for e in events if e["event"] == "unified.agent"]
        expected = (
            ["recovery"]
            if slot["case"] == "controlled_build_recovery" and method == METHODS[0]
            else ["initial", "recovery"]
            if slot["case"] == "controlled_build_recovery"
            else ["initial_abstention"]
            if slot["case"] == "controlled_initial_abstention"
            else ["initial"]
            if method == METHODS[1]
            else []
        )
        handoffs = sum(s["status"] == "needs_handoff" for s in row["transitions"])
        row["gate_observation"] = {
            "agent_phases": agents,
            "handoffs": handoffs,
            "expected_observation": bool(
                row["strict_completed"] and agents == expected and handoffs == (1 if slot["case"] == "controlled_build_recovery" else 0) and row["agent_usage"]["recorded_tokens"] == 0 and row["agent_usage"]["unknown_usage_requests"] == 0
            ),
        }
    return row


def validate(protocol):
    if protocol["identity"] != IDENTITY or protocol["provider_calls"] != 0 or protocol["max_new_provider_cost_usd"] != 0 or protocol["schedule"] != gate_schedule():
        raise PlanContractError("门禁身份、顺序或零费用边界不符")
    for name, sha in protocol["components"].items():
        if digest(REPO_ROOT / name) != sha:
            raise PlanContractError("冻结组件变化：" + name)
    role_root = Path(protocol["role_evidence"]["root"])
    if audit(role_root)["inventory_canonical_sha256"] != protocol["role_evidence"]["inventory_sha256"]:
        raise PlanContractError("角色证据变化")
    role_rows = {p["name"]: p for p in json.loads((role_root / "result.json").read_text())["projects"]}
    references = {}
    for item in protocol["projects"]:
        role = role_rows[item["name"]]
        if item != {k: role[k] for k in ("name", "task", "source_archive", "source_paths")} or digest(Path(item["source_archive"])) != PlanTask.model_validate(item["task"]).source_archive_sha256:
            raise PlanContractError("任务、来源或完整测试变化")
        parent = Path(role["reference_root"])
        if audit(parent)["inventory_canonical_sha256"] != role["reference_inventory_sha256"]:
            raise PlanContractError("参考资格变化")
        references[item["name"]] = normalized_reference(next(p["plan"] for p in json.loads((parent / "protocol.json").read_text())["projects"] if p["name"] == item["name"]))
    return references


def validate_authorization(candidate, authorization):
    """新授权必须点名候选hash和新身份；历史窗口余额不构成准入。"""
    if authorization.get("experiment_identity") != "cpp-build-unified-plan-comparison-v1" or authorization.get("candidate_sha256") != candidate["candidate_sha256"] or authorization.get("user_authorized") is not True:
        raise PlanContractError("缺少本比较的新明确授权")
    maximum = Decimal(str(authorization["max_new_provider_cost_usd"]))
    if not Decimal(0) < maximum <= Decimal(20):
        raise PlanContractError("候选协议只支持最多20美元，变更须重新冻结")
    before_deadline(authorization["deadline_utc"], 3900)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    references = validate(protocol)
    if args.validate_only:
        print(json.dumps({"valid": True, "provider_calls": 0}))
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
            item = {**projects[slot["project"]], "name": f"{i:02d}-{slot['project']}-{slot['method']}"}
            row = slot_runner(protocol=protocol, root=root, slot=slot, item=item, reference=references[slot["project"]], qualify=True)
            rows.append(row)
            print(json.dumps({k: row.get(k) for k in ("name", "case", "strict_completed", "gate_observation", "agent_usage", "error_message")}, ensure_ascii=False), flush=True)
            if not row["gate_observation"]["expected_observation"]:
                reason = "gate_failed"
                break
    finally:
        write_json(
            root / "result.json",
            {
                "identity": IDENTITY,
                "kind": "zero_provider_shared_contract_gate",
                "arms": rows,
                "not_observed": [{**s, "reason": reason or "interrupted"} for s in protocol["schedule"][len(rows) :]],
                "stop_reason": reason,
                "research_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip(),
            },
        )
        print(json.dumps(seal(root, protocol, REPO_ROOT), ensure_ascii=False), flush=True)
    return 0 if len(rows) == len(protocol["schedule"]) and reason is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
