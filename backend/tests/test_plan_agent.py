"""真实 LangChain 图上的零 Provider 契约、读取边界与计量回归。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import tarfile
from dataclasses import replace
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from deerflow.compile.agent_workflow_node import AgentWorkflowBudgetExceeded
from deerflow.compile.plan_agent import PlanAgentLedger, PlanAgentMeter, PlanContractError, PlanProposal, PlanTask, propose_plan, readonly_plan_tools, trial_budget
from deerflow.compile.plan_workflow import PlanStep

REPO_ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("plan_agent_trial", REPO_ROOT / "scripts/forge_build_plan_agent_trial.py")
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)


class ScriptedPlanModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def response(name, args, *, usage=True, model="test-model"):
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": name}],
        usage_metadata={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5} if usage else None,
        response_metadata={"model_name": model},
    )


@pytest.fixture
def task():
    return PlanTask(
        plan_id="unit-task",
        repository_url="https://example.com/unit.git",
        commit_sha="a" * 40,
        image_id="sha256:" + "1" * 64,
        source_archive_sha256="2" * 64,
        build_system="cmake",
        artifact_paths=("libunit.a",),
        verification_steps=(PlanStep(step_id="check", role="smoke", command="ctest --test-dir build", source="任务作者", expected="执行全部测试", required_output=("100% tests passed",)),),
    )


def proposal(task):
    return PlanProposal(
        reason="依据 README 构建并验证",
        steps=[
            PlanStep(step_id="configure", role="configure", command="cmake -S . -B build", source="README.md:1", expected="生成构建文件"),
            PlanStep(step_id="build", role="build", command="cmake --build build --parallel 2", source="README.md:2", expected="生成静态库"),
            *task.verification_steps,
            PlanStep(step_id="stage", role="artifact_stage", command="cp build/libunit.a /artifacts/", source="CMakeLists.txt", expected="精确暂存"),
        ],
    )


def meter(tmp_path, **kwargs):
    return PlanAgentMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), **kwargs)


def test_real_graph_reads_source_and_delivers_plan_with_actual_usage(tmp_path, task):
    (tmp_path / "README.md").write_text("build instructions\n")
    model = ScriptedPlanModel(responses=[response("read_source", {"path": "README.md"}), response("PlanProposal", proposal(task).model_dump(mode="json"))])
    usage = meter(tmp_path)
    plan, reason = propose_plan(model=model, task=task, source_root=tmp_path, meter=usage)
    assert reason and plan.revision == 1 and plan.artifact_paths == task.artifact_paths
    assert usage.summary()["model_requests"] == 2 and usage.summary()["recorded_tokens"] == 10
    assert usage.summary()["tool_calls"] == 1
    events = [json.loads(line) for line in (tmp_path / "agent/events.jsonl").read_text().splitlines()]
    assert len([e for e in events if e["event"] == "model.request_completed"]) == 2
    assert "build instructions" in next(e for e in events if e["event"] == "tool.completed")["result"]["content"]
    assert (tmp_path / "agent/response-2.json").is_file()


def test_recovery_returns_revision_without_executing_commands(tmp_path, task):
    current = task.materialize(proposal(task), revision=1)
    model = ScriptedPlanModel(responses=[response("PlanProposal", proposal(task).model_dump(mode="json"))])
    plan, _ = propose_plan(model=model, task=task, source_root=tmp_path, meter=meter(tmp_path), current_plan=current, handoff={"handoff_id": "one"})
    assert plan.revision == 2
    assert not (tmp_path / "build").exists()


def test_model_cannot_weaken_task_verification(task):
    changed = proposal(task)
    changed.steps = [s.model_copy(update={"command": "echo '100% tests passed'"}) if s.role == "smoke" else s for s in changed.steps]
    with pytest.raises(PlanContractError, match="验证"):
        task.materialize(changed, revision=1)


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", ".git/config", "README.md/../secret"])
def test_source_reader_rejects_host_and_noncanonical_paths(tmp_path, path):
    read = {t.name: t for t in readonly_plan_tools(tmp_path)}["read_source"]
    with pytest.raises(PlanContractError):
        read.invoke({"path": path})


def test_source_reader_rejects_symlink_escape_and_limits_content(tmp_path):
    (tmp_path / "outside").symlink_to("/etc/passwd")
    read = {t.name: t for t in readonly_plan_tools(tmp_path)}["read_source"]
    with pytest.raises(PlanContractError):
        read.invoke({"path": "outside"})
    (tmp_path / "README.md").write_text("x" * 9000)
    result = json.loads(read.invoke({"path": "README.md"}))
    assert result["truncated"] and len(result["content"]) == 8000


def test_recovery_can_read_only_whitelisted_failure_evidence(tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs/test.log").write_text("failed target\n")
    read = {t.name: t for t in readonly_plan_tools(tmp_path, tmp_path)}["read_failure_log"]
    assert "failed target" in read.invoke({"path": "logs/test.log"})
    with pytest.raises(PlanContractError):
        read.invoke({"path": "session.json"})
    (tmp_path / "session.json").write_text("private metadata")
    (tmp_path / "logs/link.log").symlink_to(tmp_path / "session.json")
    with pytest.raises(PlanContractError):
        read.invoke({"path": "logs/link.log"})


def test_missing_usage_stops_without_retry_and_preserves_raw_response(tmp_path, task):
    model = ScriptedPlanModel(responses=[response("PlanProposal", proposal(task).model_dump(mode="json"), usage=False)])
    usage = meter(tmp_path)
    with pytest.raises(Exception, match="missing_usage_metadata"):
        propose_plan(model=model, task=task, source_root=tmp_path, meter=usage)
    assert usage.tracker.snapshot().model_requests == 1
    assert "model.request_usage_incomplete" in (tmp_path / "agent/events.jsonl").read_text()
    assert (tmp_path / "agent/response-1.json").is_file()


def test_token_threshold_counts_full_response_before_stopping(tmp_path, task):
    usage = meter(tmp_path, budget=replace(trial_budget(), max_recorded_tokens=4))
    model = ScriptedPlanModel(responses=[response("PlanProposal", proposal(task).model_dump(mode="json"))])
    with pytest.raises(AgentWorkflowBudgetExceeded):
        propose_plan(model=model, task=task, source_root=tmp_path, meter=usage)
    assert usage.summary()["recorded_tokens"] == 5 and usage.summary()["input_tokens"] == 3
    assert usage.summary()["estimated_cost_usd"] > 0


def test_model_identity_mismatch_preserves_usage_and_stops(tmp_path, task):
    model = ScriptedPlanModel(responses=[response("PlanProposal", proposal(task).model_dump(mode="json"), model="other-model")])
    usage = meter(tmp_path)
    with pytest.raises(PlanContractError, match="模型标识"):
        propose_plan(model=model, task=task, source_root=tmp_path, meter=usage)
    assert usage.summary()["recorded_tokens"] == 5


def test_invalid_structured_proposal_still_records_actual_usage_once(tmp_path, task):
    model = ScriptedPlanModel(responses=[response("PlanProposal", {"reason": "wrong", "steps": []})])
    usage = meter(tmp_path)
    with pytest.raises(Exception):
        propose_plan(model=model, task=task, source_root=tmp_path, meter=usage)
    assert usage.summary()["recorded_tokens"] == 5
    events = [json.loads(line) for line in (tmp_path / "agent/events.jsonl").read_text().splitlines()]
    assert len([e for e in events if e["event"] == "model.request_completed"]) == 1
    assert usage.summary()["model_requests"] == 1


def test_request_limit_does_not_call_model_again(tmp_path, task):
    (tmp_path / "README.md").write_text("instructions")
    usage = meter(tmp_path, budget=replace(trial_budget(), max_model_requests=1))
    model = ScriptedPlanModel(responses=[response("read_source", {"path": "README.md"})])
    with pytest.raises(AgentWorkflowBudgetExceeded):
        propose_plan(model=model, task=task, source_root=tmp_path, meter=usage)
    assert usage.summary()["model_requests"] == 1
    assert len(list((tmp_path / "agent").glob("response-*.json"))) == 1


def test_handoff_paths_are_relative_without_mutating_original(tmp_path):
    handoff = {"recent_commands": [{"log_path": str(tmp_path / "logs/one.log"), "diagnostic_directory": str(tmp_path / "logs/diagnostics")}]}
    changed = trial.handoff_for_agent(handoff, tmp_path)
    assert changed["recent_commands"][0]["log_path"] == "logs/one.log"
    assert handoff["recent_commands"][0]["log_path"].startswith("/")


def test_controlled_injection_changes_only_build_command_and_source(task):
    plan = task.materialize(proposal(task), revision=1)
    faulted = trial.inject_controlled_target(plan)
    assert faulted.steps[2:] == plan.steps[2:]
    assert faulted.steps[1].command.endswith("forge_trial_missing_target")
    assert plan.steps[1].command != faulted.steps[1].command


@pytest.fixture
def trial_inputs(tmp_path):
    # 动态生成单测身份，不将正式候选的固定代码哈希当作未来代码的不变量。
    protocol = json.loads((REPO_ROOT / "benchmarks/manifests/cpp-build-plan-agent-trial-v1-candidate.json").read_text())
    protocol["components"] = {name: trial.sha(REPO_ROOT / name) for name in protocol["components"]}
    archive = tmp_path / "source.tar"
    archive.write_bytes(b"synthetic archive identity for input validation only")
    protocol["task"]["source_archive_sha256"] = trial.sha(archive)
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(protocol))
    return path, archive, protocol


def test_static_validation_needs_no_provider_and_authorization_must_match(trial_inputs, tmp_path):
    path, archive, protocol = trial_inputs
    assert trial.validate_inputs(path, archive)["identity"] == protocol["identity"]
    authorization = tmp_path / "authorization.json"
    authorization.write_text(json.dumps({"identity": protocol["identity"], "protocol_sha256": "0" * 64, "decision": "approve_trial", "max_estimated_cost_usd": 2}))
    with pytest.raises(PlanContractError, match="授权"):
        trial.validate_inputs(path, archive, authorization)


@pytest.mark.parametrize("change", ["code", "budget", "source"])
def test_drift_is_rejected_before_credentials(trial_inputs, change):
    path, archive, protocol = trial_inputs
    if change == "code":
        protocol["components"]["scripts/forge_build_plan_agent_trial.py"] = "0" * 64
    elif change == "budget":
        protocol["agent_budget"]["max_model_requests"] = 13
    else:
        protocol["task"]["source_archive_sha256"] = "0" * 64
    path.write_text(json.dumps(protocol))
    with pytest.raises(PlanContractError):
        trial.validate_inputs(path, archive)


@pytest.mark.skipif(os.getenv("FORGE_RUN_PLAN_AGENT_DOCKER") != "1", reason="显式启用零 Provider 的真实 Docker Agent 接线验证")
def test_docker_agent_graph_normal_and_controlled_recovery(tmp_path, task):
    source = tmp_path / "source"
    source.mkdir()
    (source / "CMakeLists.txt").write_text('cmake_minimum_required(VERSION 3.16)\nproject(unit C)\nadd_library(unit STATIC unit.c)\nenable_testing()\nadd_test(NAME unit_check COMMAND ${CMAKE_COMMAND} -E echo "functional check")\n')
    (source / "unit.c").write_text("int unit_add(int a,int b){return a+b;}\n")
    for args in (["init", "--quiet"], ["add", "."], ["-c", "user.name=Forge Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "Agent接线夹具"]):
        subprocess.run(["git", *args], cwd=source, check=True, capture_output=True, timeout=20)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    archive_path = tmp_path / "source.tar"
    with tarfile.open(archive_path, "w") as archive:
        for name in ("CMakeLists.txt", "unit.c"):
            archive.add(source / name, arcname=name)
    image = subprocess.check_output(["docker", "image", "inspect", "autocompiler:gcc13", "--format", "{{.Id}}"], text=True, timeout=20).strip()
    task = PlanTask.model_validate({**task.model_dump(), "commit_sha": commit, "image_id": image, "source_archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest()})
    selected = proposal(task)
    selected.steps[0] = selected.steps[0].model_copy(update={"source": "CMakeLists.txt:1"})
    model = ScriptedPlanModel(responses=[response("read_source", {"path": "CMakeLists.txt"}), response("PlanProposal", selected.model_dump(mode="json")), response("PlanProposal", selected.model_dump(mode="json"))])
    usage = meter(tmp_path)
    root = tmp_path / "run"
    root.mkdir()
    protocol = {"identity": "zero-provider-docker-fixture", "kind": "scripted_engineering_fixture", "task": task.model_dump(mode="json")}
    result = trial.execute_trial(protocol=protocol, archive_path=archive_path, root=root, model=model, meter=usage)
    assert result["status"] == "completed", result
    assert [case["session_status"] for case in result["cases"]] == ["completed", "completed"]
    recovery = result["cases"][1]
    assert recovery["transitions"][0]["status"] == "needs_handoff"
    assert len(recovery["agent_revisions"]) == 1
    assert usage.summary()["model_requests"] == 3  # 脚本化模型响应计数，不是真实 Provider 请求。
    assert all(case["cleanup"]["succeeded"] for case in result["cases"])
