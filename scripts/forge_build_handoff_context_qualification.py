#!/usr/bin/env python3
"""只读冻结失败状态，比较修复前后的零Provider接管材料准入。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "backend/packages/harness"), str(REPO_ROOT / "scripts")]

from forge_build_plan_agent_canary import scripted_model, source_packet  # noqa: E402
from forge_build_plan_agent_repair import handoff_for_agent  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.plan_agent import PlanAgentLedger, PlanTask  # noqa: E402
from deerflow.compile.plan_agent_context import ContextCanaryMeter, propose_with_context  # noqa: E402
from deerflow.compile.plan_cross_system import diagnostic_packet  # noqa: E402
from deerflow.compile.plan_handoff_context import HandoffContextMeter, project_handoff_packet  # noqa: E402
from deerflow.compile.plan_workflow import BuildPlan, PlanContractError  # noqa: E402


def reconstructed_packet(parent):
    """按失败时执行器的确定性材料构造规则重建，剩余时间使用冻结观察值。"""
    protocol = json.loads((parent / "protocol.json").read_text())
    item = next(row for row in protocol["projects"] if row["name"] == "libverto")
    folder = parent / "libverto-r2-plan"
    observed = json.loads((folder / "result.json").read_text())
    if observed.get("error_message") != "当前状态材料超过50000字节，不调用Provider":
        raise PlanContractError("父失败身份不符")
    state = next(row for row in reversed(observed["transitions"]) if row["status"] == "needs_handoff")
    metadata = list(folder.glob(".compile-sessions/*/*/session.json"))
    if len(metadata) != 1:
        raise PlanContractError("父Session不唯一")
    session_root = metadata[0].parent
    handoff = handoff_for_agent(state["handoff"], session_root)
    handoff["recent_commands"] = handoff["recent_commands"][-3:]
    for row in handoff["recent_commands"]:
        row["output_tail"] = row.get("output_tail", "")[-2000:]
    handoff["diagnostic_logs"] = diagnostic_packet(session_root, handoff)
    plan = BuildPlan.model_validate_json((session_root / "build-plan/plan-1.json").read_text())
    source_root = session_root / "workspace/repo"
    packet = {"task": item["task"], "source_packet": source_packet(source_root, item["source_paths"]), "state": state, "current_plan": plan.model_dump(mode="json"), "handoff": handoff}
    return packet, plan, source_root, session_root


def run_gate(protocol, root):
    parent = Path(protocol["parent_evidence"])
    before = audit(parent)
    if before["inventory_canonical_sha256"] != protocol["parent_inventory_sha256"]:
        raise PlanContractError("父封存不符")
    for name, expected in protocol["components"].items():
        if digest(REPO_ROOT / name) != expected:
            raise PlanContractError("冻结组件变化")
    packet, plan, source_root, session_root = reconstructed_packet(parent)
    projected = project_handoff_packet(packet)
    write_json(root / "reconstructed-packet.json", packet)
    write_json(root / "projected-packet.json", projected)
    rows = []
    for name, factory in (("original", ContextCanaryMeter), ("projected", HandoffContextMeter)):
        meter = factory(PlanAgentLedger(root / name), accepted_models=("scripted-gate",), deadline=protocol["deadline_utc"], packet=lambda: packet)
        error = None
        returned_revision = None
        try:
            # 脚本响应仅复述原方案以检查真实middleware准入，不执行Workflow、不尝试修复功能错误。
            proposal, _ = propose_with_context(
                model=scripted_model(plan.model_dump(mode="json"), "plan"), task=PlanTask.model_validate(packet["task"]), source_root=source_root, session_root=session_root, meter=meter, current_plan=plan, handoff=packet["handoff"]
            )
            returned_revision = proposal.revision
        except PlanContractError as exc:
            error = str(exc)
        requests = sorted((root / name).glob("request-*.json"))
        sizes = []
        for path in requests:
            request = json.loads(path.read_text())
            sizes.append(len(json.dumps({key: request[key] for key in ("messages", "system_message")}, ensure_ascii=False).encode()))
        rows.append({"mode": name, "error": error, "returned_revision": returned_revision, "message_bytes": sizes, "usage": meter.summary()})
    expected = (
        rows[0]["error"] == "当前状态材料超过50000字节，不调用Provider"
        and rows[0]["usage"]["model_requests"] == 0
        and rows[1]["error"] is None
        and rows[1]["usage"]["model_requests"] == 1
        and rows[1]["returned_revision"] == 2
        and all(row["usage"]["recorded_tokens"] == 0 and row["usage"]["unknown_usage_requests"] == 0 for row in rows)
        and audit(parent) == before
    )
    return {
        "identity": protocol["identity"],
        "kind": "zero_provider_context_admission_qualification",
        "provider_calls": 0,
        "expected_observation": expected,
        "parent_unchanged": True,
        "rows": rows,
        "scope": "只证明冻结失败材料可经过原middleware准入；不执行构建、不证明真实模型恢复",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    if protocol["identity"] != "cpp-build-handoff-context-qualification-v1" or protocol["provider_calls"] != 0:
        raise PlanContractError("零Provider身份不符")
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    result = run_gate(protocol, root)
    write_json(root / "result.json", result)
    print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result["expected_observation"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
