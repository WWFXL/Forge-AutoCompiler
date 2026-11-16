"""实际查询与恢复接线；脚本模型仅验证工具行为，不构造Provider效果。"""

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from test_plan_agent import ScriptedPlanModel, response
from test_simple_build import actions, simple_actions, workflow

from deerflow.compile.offline_harness import PlanningHarness
from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_workflow import PlanContractError, _digest
from deerflow.compile.recovery_environment import RecoveryEnvironment, query_command
from deerflow.compile.recovery_harness import RecoveryHarness
from deerflow.compile.simple_build_agents import SimpleBuildMeter
from deerflow.compile.simple_build_task import SIMPLE_PROMPT, assemble_simple_plan, propose_simple

pytest_plugins = ["test_simple_build"]


def meter_at(root):
    return SimpleBuildMeter(PlanAgentLedger(root / "agent"), accepted_models=("test-model",), deadline="2099-01-01T00:00:00+00:00", packet=lambda: {})


def test_real_search_and_query_then_revision_preserve_original_failure(runner):
    w = workflow(runner, actions("make missing-target"))
    w.run()
    original = json.loads(json.dumps(w.handoff))
    completed = dict(w.completed)
    meter = meter_at(w.root)
    service = RecoveryEnvironment(w, meter)
    found = service.execute("search", "int sample", scope="project")
    assert found["status"] == "matches" and found["matches"][0]["line"] == 1
    assert found["matches"][0]["path"].endswith("sample.c")
    env = service.execute("environment", "cc", kind="command")
    assert env["status"] == "ok" and env["exit_code"] == 0
    assert w.status == "needs_handoff" and w.completed == completed
    assert w.handoff["handoff_id"] == original["handoff_id"]
    assert w.handoff["recent_commands"] == original["recent_commands"]
    assert w.handoff["command_frontier"] != original["command_frontier"]
    assert w.commands_used == 3 and meter.tracker.snapshot().commands == 2
    records = w.manager.load_session(w.session_id, w.thread_id).commands
    assert [r.role for r in records][-2:] == ["diagnostic", "diagnostic"]
    w.apply_revision(handoff_id=original["handoff_id"], plan=assemble_simple_plan(w.plan.task, actions(), revision=2), reason="工具查询后提交修正")
    with pytest.raises(PlanContractError, match="当前活动恢复"):
        service.execute("environment", "make", kind="command")
    assert w.run()["status"] == "primary_completed"
    assert not set([found["command_id"], env["command_id"]]) & set(w.completed.values())


def test_graph_returns_container_search_evidence_to_recovery_model(runner):
    w = workflow(runner, actions("make missing-target"))
    w.run()
    meter = meter_at(w.root)
    model = ScriptedPlanModel(responses=[response("search_build_files", dict(query="int sample", scope="project")), response("SimpleBuildActions", simple_actions().model_dump(mode="json"))])
    harness = PlanningHarness(name="P0", base_prompt_sha256=_digest(SIMPLE_PROMPT))
    root = Path(__file__).resolve().parents[2]
    recovery = RecoveryHarness.model_validate_json((root / "benchmarks/fixtures/recovery-harness-system-context-gpt61sol-v1/candidate.json").read_text()).model_copy(update={"base_prompt_sha256": _digest(SIMPLE_PROMPT)})
    revised, reason = propose_simple(
        model=model,
        task=w.plan.task,
        source_root=w.root,
        session_root=w.root,
        meter=meter,
        current_plan=w.plan,
        handoff=w.handoff,
        revision_validator=w.validate_revision,
        diagnostics=RecoveryEnvironment(w, meter),
        harness=harness,
        recovery_harness=recovery,
    )
    sent = json.loads((w.root / "agent/request-2.json").read_text())
    assert any(m["type"] == "tool" and "int sample(void)" in m["content"] for m in sent["messages"])
    assert "inspect_build_environment" in json.dumps(sent)
    assert "版本移除了功能" in json.dumps(sent, ensure_ascii=False)
    w.apply_revision(handoff_id=w.handoff["handoff_id"], plan=revised, reason=reason)
    assert w.run()["status"] == "primary_completed"


def test_recovery_tools_cannot_be_added_to_initial_planning(runner):
    w = workflow(runner, actions("make missing-target"))
    w.run()
    meter = meter_at(w.root)
    with pytest.raises(PlanContractError, match="仅绑定当前恢复"):
        propose_simple(model=None, task=w.plan.task, source_root=w.root, session_root=w.root, meter=meter, diagnostics=RecoveryEnvironment(w, meter))


def test_queries_respect_budget_and_reject_unbound_frontier(runner):
    w = workflow(runner, actions("make missing-target"))
    w.run()
    service = RecoveryEnvironment(w, meter_at(w.root))
    w.budget = w.budget.model_copy(update={"max_commands": w.commands_used})
    assert service.execute("environment", "cc", kind="command")["status"] == "budget_exhausted"
    assert service.calls == 0
    w._expected_frontier = "stale"
    with pytest.raises(PlanContractError, match="权威命令记录变化"):
        service.execute("environment", "cc", kind="command")


def test_meter_command_budget_also_applies(runner):
    w = workflow(runner, actions("make missing-target"))
    w.run()
    meter = meter_at(w.root)
    meter.tracker.limits = replace(meter.tracker.limits, max_commands=0)
    with pytest.raises(Exception, match="commands"):
        RecoveryEnvironment(w, meter).execute("environment", "cc", kind="command")
    assert w.commands_used == 1


def test_fixed_search_is_not_shell_or_regex_and_skips_symlink(runner, tmp_path):
    w = workflow(runner, actions("make missing-target"))
    # 直接运行固定查询程序，验证搜索不跟随越界链接。
    outside = tmp_path / "private.h"
    outside.write_text("TOP_SECRET")
    (w.root / "escape.h").symlink_to(outside)
    command = query_command("search", "TOP_SECRET", scope="project").replace("/workspace/repo", str(w.root))
    found = json.loads(subprocess.check_output(["bash", "-c", command], text=True))
    assert found["status"] == "no_match_in_scope"
    evil = "$(touch SHOULD_NOT_EXIST);.*"
    command = query_command("search", evil, scope="project").replace("/workspace/repo", str(w.root))
    assert json.loads(subprocess.check_output(["bash", "-c", command], cwd=w.root, text=True))["status"] == "no_match_in_scope"
    assert not (w.root / "SHOULD_NOT_EXIST").exists()


@pytest.mark.parametrize(
    "operation,query,kwargs",
    [
        ("environment", "--help", {"kind": "package"}),
        ("environment", "bash", {"kind": "command"}),
        ("environment", "lib*", {"kind": "package_files"}),
        ("environment", "/etc/shadow", {"kind": "owner"}),
        ("search", "x\ncommand", {"scope": "project"}),
        ("search", "x", {"scope": "/etc"}),
    ],
)
def test_invalid_queries_are_rejected_before_execution(operation, query, kwargs):
    with pytest.raises(ValueError):
        query_command(operation, query, **kwargs)


def test_missing_package_and_unavailable_index_have_explicit_status():
    missing = json.loads(subprocess.check_output(["bash", "-c", query_command("environment", "forge-no-such-package-760", kind="package")], text=True))
    assert missing["status"] == "query_failed" and missing["exit_code"] != 0
    # 模拟环境无apt-file；固定查询程序仍产生明确不可用状态。
    command = query_command("environment", "missing.m4", kind="package_file_search")
    command = command.replace("/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "/nonexistent")
    result = json.loads(subprocess.check_output(["bash", "-c", command], text=True))
    assert result["status"] == "unavailable" and "未安装" in result["reason"]


def test_search_limit_is_marked_incomplete(tmp_path):
    (tmp_path / "repeated.m4").write_text("TEST_MACRO\n" * 25)
    command = query_command("search", "TEST_MACRO", scope="project").replace("/workspace/repo", str(tmp_path))
    result = json.loads(subprocess.check_output(["bash", "-c", command], text=True))
    assert len(result["matches"]) == 20 and result["incomplete"] is True


def test_environment_evidence_updates_progress_but_new_log_id_is_not_novel():
    from deerflow.compile.simple_planning_context import PlanningContext

    context = PlanningContext({})
    row = dict(status="ok", output="version-1", command_id="one", log_path="logs/one")
    context.observe("inspect_build_environment", dict(kind="command", query="cc"), json.dumps(row))
    row.update(command_id="two", log_path="logs/two")
    context.observe("inspect_build_environment", dict(kind="command", query="cc"), json.dumps(row))
    row["output"] = "version-2"
    context.observe("inspect_build_environment", dict(kind="command", query="cc"), json.dumps(row))
    assert context.pending_reads == [True, False, True]
