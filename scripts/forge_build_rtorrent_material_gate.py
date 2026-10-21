#!/usr/bin/env python3
"""冻结历史30材料案例的零Provider真实middleware重放；不是模型效果实验。"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from collections import OrderedDict
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/packages/harness"), str(ROOT / "scripts")]

from forge_build_rtorrent_shared_values import SharedValueMeter, restore_values  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402
from langchain.agents.middleware import ModelResponse  # noqa: E402
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage  # noqa: E402

from deerflow.compile.agent_workflow_schemas import AgentWorkflowRemainingBudget  # noqa: E402
from deerflow.compile.plan_agent import PlanAgentLedger  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402
from deerflow.compile.recovery_text_factors import restore_factor_packet  # noqa: E402

IDENTITY = "cpp-build-rtorrent-multiturn-material-gate-v1"


@dataclass
class ReplayRequest:
    messages: list
    system_message: object
    tools: list
    response_format: object = None
    model_settings: object = None

    def override(self, **kwargs):
        return replace(self, **kwargs)


def replay_case(case, old_root, out, deadline):
    source = json.loads((old_root / case["request"]).read_text())
    material = json.loads((old_root / case["material"]).read_text())
    projected = material["projected"]
    payload = json.loads(source["messages"][0]["content"])
    if case["kind"] == "actual_request":
        recent, remaining = payload["recent_tool_results"], payload["remaining_budget"]
        assert restore_factor_packet({k: v for k, v in payload.items() if k not in ("remaining_budget", "recent_tool_results")}) == projected
    else:
        events = [json.loads(line) for line in (old_root / case["events"]).read_text().splitlines()]
        recent = [{"name": event["name"], "content": str(event["result"]["content"])[-3000:]} for event in events if event["event"] == "tool.completed"][-3:]
        usage = json.loads((old_root / case["progress"]).read_text())["agent_usage"]
        remaining = dict(
            model_requests=73 - usage["model_requests"],
            recorded_tokens=400000 - usage["recorded_tokens"],
            agent_steps=72 - usage["agent_steps"],
            tool_calls=48 - usage["tool_calls"],
            commands=32 - usage["commands"],
            node_seconds=1200 - usage["elapsed_seconds"],
        )
    meter = SharedValueMeter(PlanAgentLedger(out / "agent"), accepted_models=("scripted-material-gate",), deadline=deadline, packet=lambda: copy.deepcopy(projected))
    # 显式注入该历史边界的工作集及预算，不重跑旧工具或伪称真实历史耗时。
    meter.working_set.seeded = True
    meter.working_set.entries = OrderedDict((i, copy.deepcopy(row)) for i, row in enumerate(projected.get("source_packet", [])))
    meter.working_set.index = copy.deepcopy(projected.get("read_index", []))
    meter.tracker.remaining = lambda: AgentWorkflowRemainingBudget(**remaining)
    request = ReplayRequest(
        messages=[ToolMessage(content=row["content"], name=row["name"], tool_call_id=f"historical-{i}") for i, row in enumerate(recent)],
        system_message=SystemMessage.model_validate(source["system_message"]) if source["system_message"] else None,
        tools=source["tools"],
    )
    received = []

    def handler(bounded):
        received.append(bounded)
        return ModelResponse(result=[AIMessage(content="零Provider材料门禁", response_metadata={"model_name": "scripted-material-gate"}, usage_metadata={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0})])

    meter.wrap_model_call(request, handler)
    actual = json.loads((out / "agent/request-1.json").read_text())
    plain_payload = json.loads(actual["messages"][0]["content"])
    restored = restore_values(restore_factor_packet({k: v for k, v in plain_payload.items() if k not in ("remaining_budget", "recent_tool_results")}))
    if restored != projected or plain_payload["recent_tool_results"] != recent or plain_payload["remaining_budget"] != remaining:
        raise PlanContractError("历史完整材料、反馈或预算变化")
    if actual["tools"] != source["tools"] or actual["system_message"] != source["system_message"]:
        raise PlanContractError("工具schema或系统提示变化")
    size = len(json.dumps({k: actual[k] for k in ("messages", "system_message")}, ensure_ascii=False).encode())
    schema = len(json.dumps(actual["tools"], ensure_ascii=False).encode())
    assert len(received) == 1 and size <= 50000 and schema <= 8000
    summary = meter.summary()
    assert summary["model_requests"] == 1 and summary["recorded_tokens"] == 0 and summary["unknown_usage_requests"] == 0
    return dict(
        case=case["id"],
        kind=case["kind"],
        qualified=True,
        exact_values_restored=True,
        source_working_set_unchanged=True,
        messages_bytes=size,
        schema_bytes=schema,
        scripted_responses=1,
        provider_calls=0,
        historical_budget_fixture=True,
        stopped_elapsed_seconds_reconstructed=case["kind"] == "stopped_material",
        actual_request_sha256=digest(out / "agent/request-1.json"),
    )


def validate(protocol):
    if protocol["identity"] != IDENTITY or len(protocol["cases"]) != 30 or protocol["provider_calls"] != 0:
        raise PlanContractError("资格身份或固定30分母变化")
    old = Path(protocol["source_root"])
    if audit(old)["inventory_canonical_sha256"] != protocol["source_inventory_sha256"]:
        raise PlanContractError("父冻结证据变化")
    for path, expected in protocol["source_files"].items():
        if digest(old / path) != expected:
            raise PlanContractError("历史材料来源变化")
    for path, expected in protocol["components"].items():
        if digest(ROOT / path) != expected:
            raise PlanContractError("资格组件变化")
    return old


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    old = validate(protocol)
    if args.validate_only:
        print(json.dumps(dict(valid=True, provider_calls=0)))
        return 0
    if datetime.now(UTC) >= datetime.fromisoformat(protocol["deadline_utc"]):
        raise PlanContractError("原共享窗口已结束")
    args.output_root.mkdir(parents=True, exist_ok=False)
    write_json(args.output_root / "protocol.json", protocol)
    release = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    write_json(args.output_root / "execution.json", dict(release=release, provider_calls=0))
    rows, error = [], None
    try:
        for case in protocol["cases"]:
            row = replay_case(case, old, args.output_root / case["id"], protocol["deadline_utc"])
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    except Exception as exc:
        error = dict(error_class=type(exc).__name__, message=str(exc))
        raise
    finally:
        result = dict(
            identity=IDENTITY,
            kind="zero_provider_historical_material_qualification",
            rows=rows,
            qualified=not error and len(rows) == 30,
            error=error,
            unobserved=[case["id"] for case in protocol["cases"][len(rows) :]],
            provider_calls=0,
            provider_cost_usd=0,
        )
        write_json(args.output_root / "result.json", result)
        seal(args.output_root, protocol, ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
