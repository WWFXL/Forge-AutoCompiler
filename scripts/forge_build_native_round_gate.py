#!/usr/bin/env python3
"""全部v4请求的原生完整轮次材料资格；仅usage0脚本handler，无Provider。"""

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

from forge_build_native_round import MESSAGE_BYTES, NATIVE_PROMPT, NativeRoundMeter  # noqa: E402
from forge_build_rtorrent_fixed_contract import FixedVerifierRegistry  # noqa: E402
from forge_build_rtorrent_fixed_contract_material_gate import plain  # noqa: E402
from forge_build_rtorrent_material_gate import ReplayRequest  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402
from langchain.agents.middleware import ModelResponse  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage  # noqa: E402

from deerflow.compile.agent_workflow_schemas import AgentWorkflowRemainingBudget  # noqa: E402
from deerflow.compile.plan_agent import PlanAgentLedger  # noqa: E402
from deerflow.compile.plan_agent_v2 import PlanAgentMeterV2, PlanThinkingDeepSeek  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402

IDENTITY = "cpp-build-native-round-material-gate-v1"
MODEL = "scripted-native-material-gate"


class ScriptedNativeMeter(NativeRoundMeter):
    """仅免费historical fixture；明确不资格验证付费时窗/0.80预留。"""

    def _before_request(self):
        return PlanAgentMeterV2._before_request(self)


def historical_round(agent, sequence):
    if sequence == 1:
        return []
    response = json.loads((agent / f"response-{sequence - 1}.json").read_text())
    ai = [m for m in response if m["type"] == "ai"]
    if len(ai) != 1:
        raise PlanContractError("历史AI不唯一")
    events = [
        json.loads(line) for line in (agent / "events.jsonl").read_text().splitlines()
    ]
    active, tools = None, []
    for event in events:
        if event["event"] == "model.request_started":
            active = event["request_sequence"]
        elif event["event"] == "tool.completed" and active == sequence - 1:
            tools.append(event["result"])
    return [
        AIMessage.model_validate(ai[0]),
        *[ToolMessage.model_validate(m) for m in tools],
    ]


def replay_case(case, source, out, deadline):
    request_path = source / case["request"]
    if int(request_path.stem.split("-")[-1]) != case["sequence"]:
        raise PlanContractError("原生历史轮次必须紧邻当前实际请求")
    original = json.loads(request_path.read_text())
    projected = json.loads((source / case["material"]).read_text())["projected"]
    old_payload = json.loads(original["messages"][0]["content"])
    registry = FixedVerifierRegistry(projected["task"])
    if (
        registry.restore(
            plain(
                {
                    k: v
                    for k, v in old_payload.items()
                    if k not in ("recent_tool_results", "remaining_budget")
                }
            )
        )
        != projected
    ):
        raise PlanContractError("原请求与完整投影不匹配")
    history = historical_round(request_path.parent, case["sequence"])
    meter = ScriptedNativeMeter(
        PlanAgentLedger(out / "agent"),
        registry=registry,
        accepted_models=(MODEL,),
        deadline=deadline,
        packet=lambda: copy.deepcopy(projected),
    )
    meter.tracker.limits = replace(
        meter.tracker.limits, command_timeout_seconds=1200, replay_timeout_seconds=1200
    )
    meter.working_set.seeded = True
    meter.working_set.entries = OrderedDict(
        (i, copy.deepcopy(row)) for i, row in enumerate(projected["source_packet"])
    )
    meter.working_set.index = copy.deepcopy(projected["read_index"])
    meter.tracker.remaining = lambda: AgentWorkflowRemainingBudget(
        **old_payload["remaining_budget"]
    )
    meter.ledger.append(
        "qualification.fixture",
        paid_authorization_qualified=False,
        zero_provider_handler=True,
        historical_budget=True,
    )
    system = SystemMessage.model_validate(original["system_message"])
    request = ReplayRequest(
        messages=[HumanMessage(content="历史首轮提示由权威包替代"), *history],
        system_message=system,
        tools=copy.deepcopy(original["tools"]),
    )
    received = []

    def handler(actual):
        received.append(actual)
        return ModelResponse(
            result=[
                AIMessage(
                    content="零Provider原生材料资格",
                    response_metadata=dict(model_name=MODEL),
                    usage_metadata=dict(
                        input_tokens=0, output_tokens=0, total_tokens=0
                    ),
                )
            ]
        )

    meter.wrap_model_call(request, handler)
    actual = json.loads((out / "agent/request-1.json").read_text())
    payload = json.loads(actual["messages"][0]["content"])
    restored = registry.restore(
        plain({k: v for k, v in payload.items() if k != "remaining_budget"})
    )
    if (
        restored != projected
        or actual["messages"][1:] != [m.model_dump(mode="json") for m in history]
        or payload["remaining_budget"] != old_payload["remaining_budget"]
    ):
        raise PlanContractError(
            "原任务/脚本/权威状态/方案/源码工作集/预算fixture或完整原生轮次改变"
        )
    if (
        actual["tools"] != original["tools"]
        or actual["system_message"]["content"] != system.content + NATIVE_PROMPT
    ):
        raise PlanContractError("工具schema或共同system说明改变")
    body = {k: actual[k] for k in ("messages", "system_message")}
    message_bytes = len(json.dumps(body, ensure_ascii=False).encode())
    schema_bytes = len(json.dumps(actual["tools"], ensure_ascii=False).encode())
    assert (
        len(received) == 1 and message_bytes <= MESSAGE_BYTES and schema_bytes <= 8000
    )
    serialized = PlanThinkingDeepSeek(
        model="deepseek-v4-pro", api_key="zero-provider-placeholder", max_retries=0
    )._get_request_payload([received[0].system_message, *received[0].messages])
    if history:
        assert (
            serialized["messages"][2]["reasoning_content"]
            == history[0].additional_kwargs["reasoning_content"]
        )
        assert [m["tool_call_id"] for m in serialized["messages"][3:]] == [
            m.tool_call_id for m in history[1:]
        ]
    write_json(
        out / "serialized-messages.json",
        dict(kind="offline_serializer_only_not_sent", messages=serialized["messages"]),
    )
    usage = meter.summary()
    assert (
        usage["model_requests"] == 1
        and usage["recorded_tokens"] == usage["unknown_usage_requests"] == 0
    )
    return dict(
        case=case["id"],
        method=case["method"],
        qualified=True,
        original_packet_restored=True,
        complete_native_round_retained=bool(history),
        messages_bytes=message_bytes,
        schema_bytes=schema_bytes,
        scripted_responses=1,
        provider_calls=0,
        recorded_tokens=0,
        historical_budget_fixture=True,
        paid_authorization_qualified=False,
        actual_limits=asdict(meter.tracker.limits),
    )


def negative_case(kind, out, deadline):
    task = dict(verification_steps=[])
    meter = ScriptedNativeMeter(
        PlanAgentLedger(out / "agent"),
        registry=FixedVerifierRegistry(task),
        accepted_models=(MODEL,),
        deadline=deadline,
        packet=lambda: dict(task=task, source_packet=[]),
    )
    messages = (
        [ToolMessage(content="孤立返回", tool_call_id="missing")]
        if kind == "orphan"
        else [HumanMessage(content="资格负例")]
    )
    system = SystemMessage(content="x" * 100001 if kind == "material" else "负例")
    tools = (
        [
            dict(
                type="function",
                function=dict(
                    name="oversized",
                    description="x" * 8001,
                    parameters=dict(type="object", properties={}),
                ),
            )
        ]
        if kind == "schema"
        else []
    )
    try:
        meter.wrap_model_call(
            ReplayRequest(messages=messages, system_message=system, tools=tools),
            lambda _: (_ for _ in ()).throw(AssertionError("负例不得进入handler")),
        )
    except PlanContractError as exc:
        assert (
            meter.summary()["model_requests"]
            == meter.summary()["unknown_usage_requests"]
            == 0
        )
        return dict(
            case=kind,
            qualified=True,
            rejected_before_request=True,
            error=str(exc),
            scripted_responses=0,
            provider_calls=0,
        )
    raise PlanContractError("负例未拒绝")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.protocol.read_text())
    if (
        spec["identity"] != IDENTITY
        or spec["negative_cases"] != ["orphan", "material", "schema"]
        or datetime.now(UTC) >= datetime.fromisoformat(spec["deadline_utc"])
    ):
        raise PlanContractError("资格身份、负例或原时窗不符")
    source = Path(spec["source"]["root"])
    if (
        audit(source)["inventory_canonical_sha256"]
        != spec["source"]["inventory_sha256"]
        or len(spec["cases"]) != 55
    ):
        raise PlanContractError("v4全量来源变化")
    expected = set()
    for agent in source.glob("slot-*/rtorrent-*/agent"):
        for event in map(json.loads, (agent / "events.jsonl").read_text().splitlines()):
            if event["event"] == "model.request_started":
                expected.add(
                    (agent / f"request-{event['request_sequence']}.json")
                    .relative_to(source)
                    .as_posix()
                )
    if {case["request"] for case in spec["cases"]} != expected:
        raise PlanContractError("未覆盖全部实际请求")
    for name, sha in spec["source_files"].items():
        if digest(source / name) != sha:
            raise PlanContractError("历史输入文件变化")
    for name, sha in spec["components"].items():
        if digest(ROOT / name) != sha:
            raise PlanContractError("资格组件变化")
    args.output_root.mkdir(parents=True, exist_ok=False)
    write_json(args.output_root / "protocol.json", spec)
    write_json(
        args.output_root / "execution.json",
        dict(
            release=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            provider_calls=0,
        ),
    )
    rows, negatives, error = [], [], None
    try:
        for case in spec["cases"]:
            if datetime.now(UTC) >= datetime.fromisoformat(spec["deadline_utc"]):
                raise PlanContractError("原共享运行时窗已结束")
            row = replay_case(
                case, source, args.output_root / case["id"], spec["deadline_utc"]
            )
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        for kind in spec["negative_cases"]:
            if datetime.now(UTC) >= datetime.fromisoformat(spec["deadline_utc"]):
                raise PlanContractError("原共享运行时窗已结束")
            negatives.append(
                negative_case(
                    kind, args.output_root / ("negative-" + kind), spec["deadline_utc"]
                )
            )
    except Exception as exc:
        error = dict(error_class=type(exc).__name__, message=str(exc))
        raise
    finally:
        write_json(
            args.output_root / "result.json",
            dict(
                identity=IDENTITY,
                kind="zero_provider_native_material_gate",
                qualified=not error and len(rows) == 55 and len(negatives) == 3,
                rows=rows,
                negatives=negatives,
                error=error,
                unobserved=[c["id"] for c in spec["cases"][len(rows) :]],
                unobserved_negatives=spec["negative_cases"][len(negatives) :],
                provider_calls=0,
                recorded_tokens=0,
                estimated_cost_usd="0",
                paid_authorization_qualified=False,
            ),
        )
        seal(args.output_root, spec, ROOT)


if __name__ == "__main__":
    main()
