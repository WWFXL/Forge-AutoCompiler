#!/usr/bin/env python3
"""固定验证合同引用的全部历史材料资格；零Provider、完整原脚本保持。"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from collections import OrderedDict
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/packages/harness"), str(ROOT / "scripts")]

from forge_build_rtorrent_fixed_contract import CONTRACT_PROMPT, ContractMeter, FixedVerifierRegistry  # noqa: E402
from forge_build_rtorrent_material_gate import ReplayRequest  # noqa: E402
from forge_build_rtorrent_shared_values import restore_values  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402
from langchain.agents.middleware import ModelResponse  # noqa: E402
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage  # noqa: E402
from langchain_core.utils.function_calling import convert_to_openai_tool  # noqa: E402

from deerflow.compile.agent_workflow_schemas import AgentWorkflowRemainingBudget  # noqa: E402
from deerflow.compile.plan_agent import PlanAgentLedger  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402
from deerflow.compile.recovery_text_factors import restore_factor_packet  # noqa: E402

IDENTITY = "cpp-build-rtorrent-fixed-contract-material-gate-v1"


def plain(packet):
    return restore_values(restore_factor_packet(packet))


def replay_case(case, source, out, deadline):
    source_request = json.loads((source / case["request"]).read_text())
    material = json.loads((source / case["material"]).read_text())
    projected = material["projected"]
    registry = FixedVerifierRegistry(projected["task"])
    old_payload = json.loads(source_request["messages"][0]["content"])
    if case["kind"] == "actual_request":
        recent, budget = (
            old_payload["recent_tool_results"],
            old_payload["remaining_budget"],
        )
        assert plain({k: v for k, v in old_payload.items() if k not in ("recent_tool_results", "remaining_budget")}) == projected
    else:
        events = [json.loads(line) for line in (source / case["events"]).read_text().splitlines()]
        recent = [{"name": e["name"], "content": str(e["result"]["content"])[-3000:]} for e in events if e["event"] == "tool.completed"][-3:]
        u = json.loads((source / case["progress"]).read_text())["agent_usage"]
        budget = dict(
            model_requests=73 - u["model_requests"],
            recorded_tokens=400000 - u["recorded_tokens"],
            agent_steps=72 - u["agent_steps"],
            tool_calls=48 - u["tool_calls"],
            commands=32 - u["commands"],
            node_seconds=1200 - u["elapsed_seconds"],
        )
    meter = ContractMeter(
        PlanAgentLedger(out / "agent"),
        registry=registry,
        accepted_models=("scripted-contract-material-gate",),
        deadline=deadline,
        packet=lambda: copy.deepcopy(projected),
    )
    meter.tracker.limits = replace(meter.tracker.limits, command_timeout_seconds=1200, replay_timeout_seconds=1200)
    meter.working_set.seeded = True
    meter.working_set.entries = OrderedDict((i, copy.deepcopy(row)) for i, row in enumerate(projected.get("source_packet", [])))
    meter.working_set.index = copy.deepcopy(projected.get("read_index", []))
    meter.tracker.remaining = lambda: AgentWorkflowRemainingBudget(**budget)
    tools = copy.deepcopy(source_request["tools"])
    if [t["function"]["name"] for t in tools[:3]] != [
        "list_source",
        "read_source",
        "read_failure_log",
    ]:
        raise PlanContractError("历史只读工具顺序变化")
    tools.insert(3, convert_to_openai_tool(registry.tool()))
    system = SystemMessage.model_validate(source_request["system_message"])
    if not isinstance(system.content, str):
        raise PlanContractError("历史system材料不是文本")
    system = system.model_copy(update={"content": system.content + CONTRACT_PROMPT})
    request = ReplayRequest(
        messages=[ToolMessage(content=row["content"], name=row["name"], tool_call_id=f"historical-{i}") for i, row in enumerate(recent)],
        system_message=system,
        tools=tools,
    )
    received = []

    def handler(value):
        received.append(value)
        return ModelResponse(
            result=[
                AIMessage(
                    content="零Provider固定验证合同资格",
                    response_metadata={"model_name": "scripted-contract-material-gate"},
                    usage_metadata=dict(input_tokens=0, output_tokens=0, total_tokens=0),
                )
            ]
        )

    meter.wrap_model_call(request, handler)
    actual = json.loads((out / "agent/request-1.json").read_text())
    payload = json.loads(actual["messages"][0]["content"])
    restored = registry.restore(plain({k: v for k, v in payload.items() if k not in ("recent_tool_results", "remaining_budget")}))
    if restored != projected or payload["recent_tool_results"] != recent or payload["remaining_budget"] != budget:
        raise PlanContractError("完整任务、原脚本、状态、源码工作集、反馈或预算改变")
    assert actual["tools"] == tools and actual["system_message"] == system.model_dump(mode="json")
    size = len(json.dumps({k: actual[k] for k in ("messages", "system_message")}, ensure_ascii=False).encode())
    schema = len(json.dumps(tools, ensure_ascii=False).encode())
    assert len(received) == 1 and size <= 50000 and schema <= 8000
    usage = meter.summary()
    assert usage["model_requests"] == 1 and usage["recorded_tokens"] == 0 and usage["unknown_usage_requests"] == 0
    # 所有原固定长脚本逐段只读取回并核验；不执行、改写或伪称模型主动读取。
    reads = []
    for key, expected in registry.commands.items():
        chunks, position = [], 0
        while True:
            row = json.loads(registry.tool().invoke(dict(command_sha256=key, start_char=position)))
            assert row["accepted"] and len(row["content"].encode()) <= 8000
            chunks.append(row["content"])
            reads.append(row)
            if row["next_char"] is None:
                break
            assert row["next_char"] > position
            position = row["next_char"]
        assert "".join(chunks) == expected
    write_json(
        out / "qualification-contract-readback.json",
        dict(kind="direct_readonly_tool_qualification_not_model_actions", rows=reads),
    )
    return dict(
        case=case["id"],
        source_id=case["source_id"],
        kind=case["kind"],
        qualified=True,
        exact_original_packet_restored=True,
        complete_original_fixed_scripts_readback=True,
        registry_sha256=registry.sha256,
        messages_bytes=size,
        schema_bytes=schema,
        scripted_responses=1,
        provider_calls=0,
        historical_budget_fixture=True,
        stopped_elapsed_seconds_reconstructed=case["kind"] == "stopped_material",
        actual_request_sha256=digest(out / "agent/request-1.json"),
        actual_limits=asdict(meter.tracker.limits),
    )


def validate(protocol):
    if protocol["identity"] != IDENTITY or protocol["provider_calls"] != 0 or not protocol["cases"] or set(protocol["sources"]) != {"v2", "v3"}:
        raise PlanContractError("固定验证合同资格身份或完整分母变化")
    roots = {}
    for key, source in protocol["sources"].items():
        root = Path(source["root"])
        if audit(root)["inventory_canonical_sha256"] != source["inventory_sha256"]:
            raise PlanContractError("历史冻结证据变化")
        for name, expected in protocol["source_files"][key].items():
            if digest(root / name) != expected:
                raise PlanContractError("历史输入来源变化")
        result = json.loads((root / "result.json").read_text())
        actual = sum(row["agent_usage"]["model_requests"] for row in result["rows"])
        stopped = sum(row.get("error_message") == "当前状态材料超过50000字节，不调用Provider" for row in result["rows"])
        cases = [c for c in protocol["cases"] if c["source_id"] == key]
        if sum(c["kind"] == "actual_request" for c in cases) != actual or sum(c["kind"] == "stopped_material" for c in cases) != stopped:
            raise PlanContractError("没有覆盖全部实际请求与全部材料停止案例")
        roots[key] = root
    for name, expected in protocol["components"].items():
        if digest(ROOT / name) != expected:
            raise PlanContractError("共同资格组件变化")
    return roots


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    roots = validate(protocol)
    if args.validate_only:
        print(json.dumps(dict(valid=True, provider_calls=0)))
        return 0
    if datetime.now(UTC) >= datetime.fromisoformat(protocol["deadline_utc"]):
        raise PlanContractError("原共享窗口已结束")
    args.output_root.mkdir(parents=True, exist_ok=False)
    write_json(args.output_root / "protocol.json", protocol)
    write_json(
        args.output_root / "execution.json",
        dict(
            release=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            provider_calls=0,
        ),
    )
    rows, error = [], None
    try:
        for case in protocol["cases"]:
            row = replay_case(
                case,
                roots[case["source_id"]],
                args.output_root / case["id"],
                protocol["deadline_utc"],
            )
            rows.append(row)
            print(
                json.dumps(
                    {
                        k: row[k]
                        for k in (
                            "case",
                            "kind",
                            "qualified",
                            "messages_bytes",
                            "schema_bytes",
                        )
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    except Exception as exc:
        error = dict(error_class=type(exc).__name__, message=str(exc))
        raise
    finally:
        write_json(
            args.output_root / "result.json",
            dict(
                identity=IDENTITY,
                kind="zero_provider_fixed_verifier_contract_qualification",
                rows=rows,
                qualified=not error and len(rows) == len(protocol["cases"]),
                error=error,
                unobserved=[c["id"] for c in protocol["cases"][len(rows) :]],
                provider_calls=0,
                provider_cost_usd=0,
            ),
        )
        seal(args.output_root, protocol, ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
