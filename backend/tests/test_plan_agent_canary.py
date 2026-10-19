"""开发canary的共同预算、固定oracle和新上下文边界。"""

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage
from test_plan_agent import ScriptedPlanModel, proposal, response
from test_plan_agent import task as original_task

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_agent_canary import CanaryMeter, ToolBuildService, propose, run_tool_agent, source_packet
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.schemas import CommandResult


def meter(tmp_path, packet=None):
    return CanaryMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat(), packet=packet or (lambda: {"task": "unit"}))


def test_full_plan_graph_includes_tools_and_current_authoritative_packet(tmp_path):
    task = original_task.__wrapped__()
    model = ScriptedPlanModel(responses=[response("PlanProposal", proposal(task).model_dump(mode="json"))])
    usage = meter(tmp_path, packet=lambda: {"task": task.model_dump(mode="json"), "state": {"marker": "AUTHORITATIVE"}})
    plan, _ = propose(model=model, task=task, source_root=tmp_path, session_root=tmp_path, meter=usage)
    assert plan.artifact_paths == task.artifact_paths and usage.summary()["model_requests"] == 1
    request = json.loads((tmp_path / "agent/request-1.json").read_text())
    assert "AUTHORITATIVE" in request["messages"][0]["content"]
    assert {tool["function"]["name"] for tool in request["tools"]} == {"list_source", "read_source", "read_failure_log", "PlanProposal"}


def test_large_state_is_rejected_before_provider_request(tmp_path):
    usage = meter(tmp_path, packet=lambda: {"state": "x" * 50001})
    task = original_task.__wrapped__()
    model = ScriptedPlanModel(responses=[response("PlanProposal", proposal(task).model_dump(mode="json"))])
    with pytest.raises(PlanContractError, match="50000"):
        propose(model=model, task=task, source_root=tmp_path, session_root=tmp_path, meter=usage)
    assert usage.summary()["model_requests"] == 0


def test_response_can_exceed_old_50000_bound_and_truncation_keeps_known_usage(tmp_path):
    task = original_task.__wrapped__()
    truncated = AIMessage(content="", response_metadata={"model_name": "test-model", "finish_reason": "length"}, usage_metadata={"input_tokens": 18239, "output_tokens": 32768, "total_tokens": 51007})
    model = ScriptedPlanModel(responses=[truncated])
    usage = meter(tmp_path)
    with pytest.raises(PlanContractError, match="截断"):
        propose(model=model, task=task, source_root=tmp_path, session_root=tmp_path, meter=usage)
    assert usage.summary()["model_requests"] == 1 and usage.summary()["recorded_tokens"] == 51007
    assert usage.summary()["unknown_usage_requests"] == 0


def test_fixed_oracle_cannot_pass_only_from_zero_exit_or_fake_empty_ctest(tmp_path, monkeypatch):
    service = ToolBuildService(task=original_task.__wrapped__(), session=None, manager=None, source_root=tmp_path, frozen={}, meter=meter(tmp_path))
    monkeypatch.setattr(service, "execute", lambda *args: ({"command_id": "check-one"}, CommandResult(0, "No tests were found!", "", "No tests were found!", "unused")))
    tools = {tool.name: tool for tool in service.tools()}
    result = json.loads(tools["run_fixed_tests"].invoke({}))
    assert not result[0]["fixed_expectations_passed"] and not service.verifications
    submitted = json.loads(tools["submit_verified_build"].invoke({"supporting_command_id": "build-one", "recipe_command_ids": ["build-one"]}))
    assert not submitted["accepted"] and "测试" in submitted["reason"]


def test_submission_requires_exact_artifact_set_after_fixed_tests(tmp_path, monkeypatch):
    task = original_task.__wrapped__()
    service = ToolBuildService(task=task, session=None, manager=None, source_root=tmp_path, frozen={}, meter=meter(tmp_path))
    service.verifications = {task.verification_steps[0].step_id: "passed-check"}
    monkeypatch.setattr(service, "current", lambda: SimpleNamespace(metadata_path=str(tmp_path / "session.json")))
    (tmp_path / "artifacts").mkdir()
    tools = {tool.name: tool for tool in service.tools()}
    result = json.loads(tools["submit_verified_build"].invoke({"supporting_command_id": "build-one", "recipe_command_ids": ["build-one"]}))
    assert not result["accepted"] and "交付集合" in result["reason"]


def test_packet_does_not_follow_source_escape_and_remains_bounded(tmp_path):
    (tmp_path / "README.md").write_text("源码" * 30000)
    rows = source_packet(tmp_path, ["README.md"])
    assert len(json.dumps(rows, ensure_ascii=False).encode()) <= 24000 and rows[0]["truncated"]
    (tmp_path / "secret").symlink_to(tmp_path.parent / "private-config")
    with pytest.raises(PlanContractError, match="逃出"):
        source_packet(tmp_path, ["secret"])


def test_tool_graph_executes_batch_in_order_and_stops_without_extra_request(tmp_path):
    from langchain_core.tools import tool

    events = []
    state = SimpleNamespace(verified=False)

    @tool
    def ordered_action(number: int) -> str:
        """记录脚本化执行顺序。"""
        assert events == list(range(number))
        events.append(number)
        state.verified = number == 2
        return "executed"

    batch = AIMessage(
        content="",
        tool_calls=[{"name": "ordered_action", "args": {"number": i}, "id": f"call-{i}"} for i in range(3)],
        usage_metadata={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
        response_metadata={"model_name": "test-model"},
    )
    model = ScriptedPlanModel(responses=[batch])
    usage = meter(tmp_path)

    # 同一可观察状态供终止中间件读取。
    class Service:
        def tools(self):
            return [ordered_action]

        @property
        def verified(self):
            return state.verified

    run_tool_agent(model=model, service=Service(), source_root=tmp_path, session_root=tmp_path, meter=usage)
    assert events == [0, 1, 2] and usage.summary()["model_requests"] == 1 and usage.summary()["tool_calls"] == 3


def test_typed_seal_preserves_broken_external_links_and_detects_tampering(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("typed_evidence", Path(__file__).resolve().parents[2] / "scripts/forge_typed_evidence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "evidence"
    root.mkdir()
    (root / "ordinary").write_text("fixed")
    (root / "outside").symlink_to("/private/never-read")
    (root / "directory").symlink_to(tmp_path.parent, target_is_directory=True)
    sealed = module.seal(root, {"identity": "unit", "components": {}}, tmp_path)
    assert sealed["files"] == 1 and sealed["symlinks"] == 2
    assert module.audit(root) == sealed
    (root / "outside").unlink()
    (root / "outside").symlink_to("/another-target")
    with pytest.raises(ValueError, match="封存"):
        module.audit(root)
    (root / "outside").unlink()
    (root / "outside").symlink_to("/private/never-read")
    (root / "ordinary").write_text("changed")
    with pytest.raises(ValueError, match="封存"):
        module.audit(root)


@pytest.mark.parametrize("limit", [180, 300])
def test_tool_execution_honors_shared_command_limit(tmp_path, monkeypatch, limit):
    from dataclasses import replace

    from deerflow.compile import plan_agent_canary

    usage = meter(tmp_path)
    usage.tracker.limits = replace(usage.tracker.limits, command_timeout_seconds=limit)
    service = ToolBuildService(task=original_task.__wrapped__(), session=None, manager=None, source_root=tmp_path, frozen={}, meter=usage)
    monkeypatch.setattr(service, "current", lambda: SimpleNamespace())
    observed = []

    def execute(**kwargs):
        observed.append(kwargs["timeout_seconds"])
        return CommandResult(0, "ok", "", "ok", "unused"), None, SimpleNamespace(command_id="build-one")

    monkeypatch.setattr(plan_agent_canary, "_run_system_oracle_bash_impl", execute)
    service.execute("make", "build", "/workspace/repo")
    assert observed == [limit]
