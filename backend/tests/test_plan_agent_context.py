"""读取别名不扩大授权边界，工具拒绝可见，旧证据有界保留。"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from test_plan_agent import ScriptedPlanModel, proposal, response
from test_plan_agent import task as original_task

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_agent_context import ContextCanaryMeter, EvidenceWorkingSet, normalized_read_path, propose_with_context, safe_readonly_tools
from deerflow.compile.plan_workflow import PlanContractError


def test_absolute_alias_relative_path_missing_and_escape_feedback(tmp_path):
    (tmp_path / "README.md").write_text("source data")
    tools = {item.name: item for item in safe_readonly_tools(tmp_path, tmp_path)}
    assert json.loads(tools["read_source"].invoke({"path": "/workspace/repo/README.md"}))["content"] == "1: source data"
    assert json.loads(tools["read_source"].invoke({"path": "README.md"}))["sha256"]
    assert "README.md" in json.loads(tools["list_source"].invoke({"directory": "/workspace/repo"}))["entries"]
    for path in ("/etc/passwd", "../secret", "missing"):
        rejected = json.loads(tools["read_source"].invoke({"path": path}))
        assert rejected["accepted"] is False and rejected["error"]
    (tmp_path / "escape").symlink_to("/etc/passwd")
    assert not json.loads(tools["read_source"].invoke({"path": "escape"}))["accepted"]
    with pytest.raises(PlanContractError):
        normalized_read_path("/workspace/repo/../secret")


def test_log_alias_does_not_open_source_or_external_root(tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs/run.log").write_text("failed command detail")
    tools = {item.name: item for item in safe_readonly_tools(tmp_path, tmp_path)}
    assert "failed command detail" in json.loads(tools["read_failure_log"].invoke({"path": "/logs/run.log"}))["content"]
    for path in ("/etc/passwd", "/workspace/repo/test.log", "source.txt"):
        assert not json.loads(tools["read_failure_log"].invoke({"path": path}))["accepted"]


def test_real_graph_keeps_old_read_evidence_and_recovers_from_missing_file(tmp_path):
    task = original_task.__wrapped__()
    for i in range(4):
        (tmp_path / f"source-{i}.txt").write_text(f"VERIFIED-EVIDENCE-{i}")
    model = ScriptedPlanModel(
        responses=[
            response("read_source", {"path": "/workspace/repo/missing.txt"}),
            *[response("read_source", {"path": f"/workspace/repo/source-{i}.txt"}) for i in range(4)],
            response("PlanProposal", proposal(task).model_dump(mode="json")),
        ]
    )
    usage = ContextCanaryMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat(), packet=lambda: {"task": task.model_dump(mode="json"), "source_packet": []})
    plan, _ = propose_with_context(model=model, task=task, source_root=tmp_path, session_root=tmp_path, meter=usage)
    assert plan and usage.summary()["model_requests"] == 6 and usage.summary()["tool_calls"] == 5
    final = json.loads((tmp_path / "agent/request-6.json").read_text())
    payload = json.loads(final["messages"][0]["content"])
    # source-0已不在最近三个工具反馈，仍在带来源的工作集；缺失文件反馈没有变成成功证据。
    assert "VERIFIED-EVIDENCE-0" in json.dumps(payload["source_packet"])
    assert payload["read_index"][0]["accepted"] is False
    assert all(row.get("error") is None for row in payload["source_packet"])


def test_evidence_working_set_is_bounded_without_model_summary():
    working = EvidenceWorkingSet()
    working.seed([])
    for i in range(100):
        working.observe("read_source", {"path": f"source-{i}", "start_line": 1}, json.dumps({"path": f"source-{i}", "sha256": "a" * 64, "content": "source" * 1400}))
    assert len(json.dumps(list(working.entries.values()), ensure_ascii=False).encode()) <= 24000
    assert len(json.dumps(working.index, ensure_ascii=False).encode()) <= 4000
    assert ("read_source", "source-99", 1) in working.entries


def test_evidence_eviction_keeps_authoritative_state_under_message_limit(tmp_path):
    task = original_task.__wrapped__()
    authoritative = "authoritative" * 2300
    usage = ContextCanaryMeter(
        PlanAgentLedger(tmp_path / "agent"),
        accepted_models=("test-model",),
        deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat(),
        packet=lambda: {"task": task.model_dump(mode="json"), "state": authoritative, "source_packet": [{"path": "large.txt", "content": "evidence" * 2700}]},
    )
    model = ScriptedPlanModel(responses=[response("PlanProposal", proposal(task).model_dump(mode="json"))])
    propose_with_context(model=model, task=task, source_root=tmp_path, session_root=tmp_path, meter=usage)
    request = json.loads((tmp_path / "agent/request-1.json").read_text())
    payload = json.loads(request["messages"][0]["content"])
    assert payload["state"] == authoritative and not payload["source_packet"]
    assert usage.summary()["model_requests"] == 1
