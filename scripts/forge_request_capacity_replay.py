#!/usr/bin/env python3
"""只读冻结消息的容量回放；不初始化模型、读取凭据或执行容器命令。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from deerflow.compile.dependency_diagnosis import DependencyDiagnosis
from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.recovery_diagnostic_memory import RecoveryDiagnosticMemory
from deerflow.compile.simple_build_agents import SimpleBuildMeter
from deerflow.compile.simple_planning_context import PlanningContext

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "benchmarks/fixtures/recovery-context-capacity-v1"


class ReplayRequest:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def override(self, **kwargs):
        return ReplayRequest(**{**self.__dict__, **kwargs})


def legacy_class(source, filename, name):
    path = source / filename
    spec = importlib.util.spec_from_file_location("frozen_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, name)


def replay(output, *, fixture=FIXTURE, legacy_source=None):
    output.mkdir(parents=True, exist_ok=False)
    provenance = json.loads((fixture / "provenance.json").read_text())
    for name, digest in provenance["files"].items():
        assert hashlib.sha256((fixture / name).read_bytes()).hexdigest() == digest
    original = json.loads((fixture / "request-8.json").read_text())
    group = json.loads((fixture / "latest-group.json").read_text())
    packet = json.loads(original["messages"][0]["content"])
    for key in ("remaining_budget", "planning_progress", "recovery_diagnostic_memory", "dependency_diagnosis"):
        packet.pop(key, None)
    queries = json.loads((fixture / "queries.json").read_text())
    messages = [HumanMessage(content="回放公开任务"), *[{"ai": AIMessage, "tool": ToolMessage}[m["type"]](**m) for m in group]]
    request = ReplayRequest(messages=messages, system_message=SystemMessage(**original["system_message"]), model_settings={}, model=None, tools=original["tools"], response_format=None)
    diagnosis = DependencyDiagnosis(SimpleNamespace(workflow=SimpleNamespace(handoff=packet["handoff"])))

    def make_memory(cls):
        memory = cls()
        for row in queries:
            name = "search_build_files" if row["operation"] == "search" else "inspect_build_environment"
            args = {k: row[k] for k in ("query", "scope", "kind") if k in row}
            memory.observe(name, args, row["result"], handoff_id=row["handoff_id"])
        return memory

    for row in queries:
        diagnosis.observe("search_build_files" if row["operation"] == "search" else "inspect_build_environment", {k: row[k] for k in ("query", "scope", "kind") if k in row}, row["result"])
    legacy_result = None
    if legacy_source:
        old_context = legacy_class(legacy_source, "simple_planning_context.py", "PlanningContext")
        old_memory = legacy_class(legacy_source, "recovery_diagnostic_memory.py", "RecoveryDiagnosticMemory")
        old_meter = SimpleBuildMeter(PlanAgentLedger(output / "legacy"), packet=lambda: {}, accepted_models=("zero-provider-script",), deadline="2099-01-01T00:00:00+00:00")
        context = old_context(packet, diagnostic_memory=make_memory(old_memory), dependency_diagnosis=diagnosis)
        try:
            context.request(old_meter, request, lambda _: (_ for _ in ()).throw(AssertionError("旧容量应在请求前停止")))
        except PlanContractError as exc:
            legacy_result = dict(error=str(exc), model_requests=old_meter.summary()["model_requests"])
        assert legacy_result and "上下文容量" in legacy_result["error"]
    meter = SimpleBuildMeter(PlanAgentLedger(output / "current"), packet=lambda: {}, accepted_models=("zero-provider-script",), deadline="2099-01-01T00:00:00+00:00")
    context = PlanningContext(packet, diagnostic_memory=make_memory(RecoveryDiagnosticMemory), dependency_diagnosis=diagnosis)
    sent = []

    def handler(bounded):
        sent.append(bounded)
        return SimpleNamespace(result=[AIMessage(content="仅工程送达回执，不是构建方案", usage_metadata=dict(input_tokens=0, output_tokens=0, total_tokens=0), response_metadata=dict(model_name="zero-provider-script"))])

    context.request(meter, request, handler)
    forwarded = json.loads(sent[0].messages[0].content)
    candidate = next(c for c in forwarded["recovery_diagnostic_memory"]["candidates"] if c["package"] == "libltdl-dev")
    assert candidate["checks"]["package"]["installed"] is False
    assert forwarded["current_plan"] == packet["current_plan"]
    assert forwarded["handoff"]["recent_commands"][-1]["command"] == packet["handoff"]["recent_commands"][-1]["command"]
    assert [m.model_dump(mode="json") for m in sent[0].messages[1:]] == group
    events = [json.loads(line) for line in (output / "current/events.jsonl").read_text().splitlines()]
    capacity = next(e for e in events if e["event"] == "model.context_budget")
    result = dict(
        scope=provenance["scope"],
        provider_calls=0,
        cost_usd=0,
        legacy=legacy_result,
        current=dict(capacity=capacity, max_tokens=sent[0].model_settings["max_tokens"], verified_missing_candidate_preserved=True, latest_tool_group_unchanged=True, current_plan_preserved=True),
        summary=meter.summary(),
    )
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--legacy-source", type=Path)
    args = parser.parse_args()
    print(json.dumps(replay(args.output, legacy_source=args.legacy_source), ensure_ascii=False, indent=2))
