"""真实图回放v2路径错误；零Provider验证错误恢复、读取边界和累计预算。"""

import hashlib
import importlib.util
import json
import os
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from langchain_core.messages import AIMessage
from test_plan_agent import ScriptedPlanModel, proposal, response
from test_plan_agent import task as original_task

from deerflow.compile.agent_workflow_node import AgentWorkflowBudgetExceeded
from deerflow.compile.plan_agent import PlanAgentLedger, trial_budget
from deerflow.compile.plan_agent_repair import propose_plan, repair_readonly_tools
from deerflow.compile.plan_agent_v2 import PlanAgentMeterV2, PlanThinkingDeepSeek
from deerflow.compile.plan_workflow import PlanContractError

REPO_ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("plan_agent_repair_trial", REPO_ROOT / "scripts/forge_build_plan_agent_repair.py")
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)


@pytest.fixture
def repair_task():
    return original_task.__wrapped__()


def test_actual_v2_calls_receive_errors_then_corrected_reads_and_plan(tmp_path, repair_task):
    task = repair_task
    (tmp_path / "README.md").write_text("真实图中的源码读取成功")
    calls = [
        {"name": "list_source", "args": {"directory": "/workspace/repo"}, "id": "one"},
        *[{"name": "read_source", "args": {"path": path}, "id": str(i)} for i, path in enumerate(("/workspace/repo/README.md", "/workspace/repo/CMakeLists.txt", "/workspace/repo/tests/CMakeLists.txt"))],
    ]
    model = ScriptedPlanModel(
        responses=[
            AIMessage(content="", tool_calls=calls, usage_metadata={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}, response_metadata={"model_name": "test-model"}),
            response("read_source", {"path": "README.md"}),
            response("PlanProposal", proposal(task).model_dump(mode="json")),
        ]
    )
    meter = PlanAgentMeterV2(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",))
    plan, _ = propose_plan(model=model, task=task, source_root=tmp_path, meter=meter, packet_mode=False)
    assert plan.steps == tuple(proposal(task).steps)
    events = [json.loads(line) for line in (tmp_path / "agent/events.jsonl").read_text().splitlines()]
    completed = [row for row in events if row["event"] == "tool.completed"]
    assert len(completed) == 5
    assert all(json.loads(row["result"]["content"])["ok"] is False for row in completed[:4])
    assert "源码读取成功" in completed[-1]["result"]["content"]
    assert meter.summary()["model_requests"] == 3 and meter.summary()["recorded_tokens"] == 15
    assert "correction" in (tmp_path / "agent/request-2.json").read_text()


@pytest.mark.parametrize("name", ["../private", "/etc/passwd", ".git/config", "escape", "missing"])
def test_error_feedback_preserves_read_boundary(tmp_path, name):
    outside = tmp_path.parent / "private"
    outside.write_text("DO_NOT_DISCLOSE")
    (tmp_path / "escape").symlink_to(outside)
    read = {t.name: t for t in repair_readonly_tools(tmp_path)}["read_source"]
    result = json.loads(read.invoke({"path": name}))
    assert result["ok"] is False and "correction" in result
    assert "DO_NOT_DISCLOSE" not in json.dumps(result)
    assert str(tmp_path) not in json.dumps(result)


def test_correctable_tool_error_does_not_bypass_request_budget(tmp_path, repair_task):
    task = repair_task
    meter = PlanAgentMeterV2(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), budget=replace(trial_budget(), max_model_requests=1))
    model = ScriptedPlanModel(responses=[response("read_source", {"path": "/workspace/repo/README.md"})])
    with pytest.raises(AgentWorkflowBudgetExceeded):
        propose_plan(model=model, task=task, source_root=tmp_path, meter=meter, packet_mode=False)
    assert meter.summary()["model_requests"] == 1
    assert len(list((tmp_path / "agent").glob("response-*.json"))) == 1


def test_source_packet_graph_proposes_in_one_request_without_source_tool_loop(tmp_path, repair_task):
    (tmp_path / "CMakeLists.txt").write_text("SOURCE_PACKET_MARKER\n" * 600)
    model = ScriptedPlanModel(responses=[response("PlanProposal", proposal(repair_task).model_dump(mode="json"))])
    meter = PlanAgentMeterV2(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",))
    plan, _ = propose_plan(model=model, task=repair_task, source_root=tmp_path, meter=meter)
    assert plan.artifact_paths == repair_task.artifact_paths
    packet = json.loads(next((tmp_path / "agent").glob("source-packet-*.json")).read_text())
    assert packet[0]["sha256"] == trial.sha(tmp_path / "CMakeLists.txt")
    assert packet[0]["truncated"] and len(json.dumps(packet, ensure_ascii=False).encode()) <= 36_000
    assert "SOURCE_PACKET_MARKER" in (tmp_path / "agent/request-1.json").read_text()
    assert meter.summary()["model_requests"] == 1 and meter.summary()["tool_calls"] == 0


def test_low_thinking_packet_mode_in_real_sdk_http_payload(tmp_path, repair_task):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "offline",
                "object": "chat.completion",
                "created": 1,
                "model": "deepseek-v4-pro",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": None, "tool_calls": [{"id": "proposal", "type": "function", "function": {"name": "PlanProposal", "arguments": proposal(repair_task).model_dump_json()}}]},
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
        )

    model = PlanThinkingDeepSeek(
        model="deepseek-v4-pro",
        api_key="synthetic-key",
        base_url="https://api.deepseek.com",
        max_tokens=8192,
        max_retries=0,
        reasoning_effort="low",
        extra_body={"thinking": {"type": "enabled"}},
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    meter = PlanAgentMeterV2(PlanAgentLedger(tmp_path / "agent"), accepted_models=("deepseek-v4-pro",))
    plan, _ = propose_plan(model=model, task=repair_task, source_root=tmp_path, meter=meter)
    assert plan.artifact_paths == repair_task.artifact_paths
    assert len(seen) == 1 and seen[0]["reasoning_effort"] == "low" and seen[0]["thinking"]["type"] == "enabled"
    assert seen[0]["tool_choice"] == "auto" and len(seen[0]["tools"]) == 1


def frozen_usage(root, *, requests=1, tokens=0, unknown=0):
    root.mkdir()
    usage = {"model_requests": requests, "recorded_tokens": tokens, "agent_steps": requests, "tool_calls": 0}
    (root / "result.json").write_text(json.dumps({"agent_usage": usage}))
    rows = [{"path": "result.json", "size": (root / "result.json").stat().st_size, "sha256": trial.sha(root / "result.json")}]
    (root / "inventory.json").write_text(json.dumps(rows))
    digest = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (root / "seal.json").write_text(json.dumps({"inventory_canonical_sha256": digest, "unknown_usage_requests": unknown}))
    return root


def test_prior_unknown_usage_and_completed_usage_reserve_cumulative_budget(tmp_path):
    one = frozen_usage(tmp_path / "v1", unknown=1)
    two = frozen_usage(tmp_path / "v2", tokens=1710)
    limits = trial.remaining_budget([one, two])
    assert limits.max_model_requests == 10 and limits.max_recorded_tokens == 98_290
    assert limits.max_recorded_tokens + 50_000 + 50_000 + 1710 == 200_000
    three = frozen_usage(tmp_path / "attempt-1", requests=3, tokens=20_000)
    limits = trial.remaining_budget([one, two, three])
    assert limits.max_model_requests == 7 and limits.max_recorded_tokens == 78_290
    limits = trial.remaining_budget([one, two, three], response_bound=25_000)
    assert limits.max_recorded_tokens == 103_290
    assert limits.max_recorded_tokens + limits.max_recorded_tokens_per_response + 50_000 + 21_710 == 200_000


def test_frozen_tampering_and_request_exhaustion_block_further_calls(tmp_path):
    full = frozen_usage(tmp_path / "full", requests=12)
    with pytest.raises(PlanContractError, match="预算"):
        trial.remaining_budget([full])
    (full / "result.json").write_text("changed")
    with pytest.raises(PlanContractError, match="冻结"):
        trial.audit_frozen(full)


@pytest.mark.skipif(os.getenv("FORGE_RUN_PLAN_AGENT_DOCKER") != "1", reason="显式启用新修复runner的真实Docker接线夹具")
def test_repair_runner_docker_normal_and_controlled_recovery(tmp_path, repair_task, monkeypatch):
    import test_plan_agent as original

    propose = trial.propose_plan
    monkeypatch.setattr(trial, "propose_plan", lambda **kwargs: propose(**kwargs, packet_mode=False))
    monkeypatch.setattr(original, "trial", trial)
    original.test_docker_agent_graph_normal_and_controlled_recovery(tmp_path, repair_task)
