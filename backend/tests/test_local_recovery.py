"""局部恢复保留真实进展、失效变化后缀，并守住原测试与执行边界。"""

import hashlib
import json
from types import SimpleNamespace

import pytest
from test_goal_state import cache, core_plan, task
from test_plan_workflow import ScriptedRuntime

from deerflow.compile.local_recovery import LocalRecovery, LocalRecoveryInputError, LocalRecoveryWorkflow
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_workflow import PlanBudget, PlanContractError
from deerflow.compile.schemas import BuildCommandRecord
from deerflow.compile.source_preparation import paths_fingerprint, with_preparation
from deerflow.compile.unified_plan_equivalent_observed import ObservedBuildActions
from deerflow.config.paths import Paths


def actions(*, configure="cmake -S . -B build -DBUILD_TESTS=ON", dependency=False):
    steps = []
    if dependency:
        steps.append(dict(step_id="dependency", role="dependency", command="echo prepare-dependency", source="受控依赖", expected="准备成功"))
    steps.extend(
        [
            dict(step_id="configure", role="configure", command=configure, requires=("dependency",) if dependency else (), source="原任务", expected="配置成功"),
            dict(step_id="build", role="build", command="cmake --build build", requires=("configure",), source="原任务", expected="编译成功"),
        ]
    )
    return ObservedBuildActions(reason="从真实反馈修复当前阶段", steps=steps)


@pytest.fixture
def local_setup(tmp_path, monkeypatch):
    value, source = task(), tmp_path / "source"
    source.mkdir()
    (source / "CMakeLists.txt").write_text('option(BUILD_TESTS "original tests" ON)\n')
    cache(source)
    frozen = {"CMakeLists.txt": hashlib.sha256((source / "CMakeLists.txt").read_bytes()).hexdigest()}
    plan = with_preparation(core_plan(value), paths_fingerprint(frozen))
    manager = CompileSessionManager(paths=Paths(base_dir=tmp_path / "data", workspace_root=tmp_path, host_workspace_root=str(tmp_path)))
    session = manager.create_session("local-test", value.repository_url)
    session.commit_sha, session.image_id = value.commit_sha, value.image_id
    session.replay_source_archive_sha256 = value.source_archive_sha256
    session.selected_build_system, session.status = "cmake", "inspected"
    manager.save_session(session)
    step = plan.steps[0]
    record = BuildCommandRecord(command=step.command, workdir=step.workdir, role=step.role, stage="plan", exit_code=0, timed_out=False)
    manager.record_command(session, record)
    tracker = SimpleNamespace(observe_elapsed=lambda value: None, consume=lambda **kwargs: None)
    meter = SimpleNamespace(started_monotonic=0, tracker=tracker, ledger=PlanAgentLedger(tmp_path / "agent"))
    runtime = ScriptedRuntime()
    monkeypatch.setattr("deerflow.compile.plan_agent_canary.time.monotonic", lambda: 0)
    kwargs = dict(plan=plan, session=session, manager=manager, runtime=runtime, preparation_command_id=record.command_id, meter=meter, source_root=source, frozen=frozen, budget=PlanBudget(wall_clock_seconds=1200), clock=lambda: 0)
    return value, source, runtime, kwargs


def test_local_configure_then_workflow_runs_build_and_original_tests_once(local_setup):
    value, source, runtime, kwargs = local_setup
    episodes = []

    def recover(wf):
        recovery = LocalRecovery(wf, value)
        episodes.append(recovery)
        assert recovery.target == "configure" and "build" not in wf.completed
        recovery.revise(actions(dependency=True))
        assert recovery.execute("dependency")["passed"]
        cache(source, tests="ON")
        assert recovery.execute("configure")["passed"]
        recovery.finish()
        assert "build" not in wf.completed

    wf = LocalRecoveryWorkflow(recover=recover, **kwargs)
    assert wf.run()["status"] == "ready_for_verification"
    assert len(episodes) == wf.handoffs_used == 1
    assert runtime.executed.count("cmake --build build") == 1
    assert len([s for s in wf.plan.steps if s.role == "smoke" and s.step_id in wf.completed]) == 1
    assert episodes[0].executed == [wf.completed["dependency"], wf.completed["configure"]]
    assert [s.role for s in wf.replay_recipe().steps] == ["dependency", "dependency", "configure", "build", "artifact_stage"]


def test_normal_workflow_does_not_call_recovery(local_setup):
    _, source, _, kwargs = local_setup
    cache(source, tests="ON")
    wf = LocalRecoveryWorkflow(recover=lambda wf: pytest.fail("正常路径不调用Agent"), **kwargs)
    assert wf.run()["status"] == "ready_for_verification" and wf.handoffs_used == 0


def test_unmet_goals_or_test_execution_cannot_be_returned_as_success(local_setup):
    value, _, _, kwargs = local_setup
    wf = LocalRecoveryWorkflow(recover=lambda wf: None, **kwargs)
    super(LocalRecoveryWorkflow, wf).run()
    recovery = LocalRecovery(wf, value)
    with pytest.raises(LocalRecoveryInputError, match="不能交还"):
        recovery.finish()
    recovery.revise(actions())
    with pytest.raises(LocalRecoveryInputError, match="原测试"):
        recovery.execute("check")
    assert not recovery.execute("configure")["passed"]
    with pytest.raises(LocalRecoveryInputError, match="配置目标"):
        recovery.finish()


def test_revision_invalidates_old_build_and_smoke_results(local_setup):
    value, source, _, kwargs = local_setup
    cache(source, tests="ON")
    wf = LocalRecoveryWorkflow(recover=lambda wf: None, **kwargs)
    assert super(LocalRecoveryWorkflow, wf).run()["status"] == "ready_for_verification"
    old_build = wf.completed["build"]
    wf._request_handoff("acceptance_failed")
    recovery = LocalRecovery(wf, value)
    assert recovery.target == "build"
    recovery.revise(actions())
    assert "build" not in wf.completed and "check" not in wf.completed
    recovery.execute("configure")
    recovery.execute("build")
    recovery.finish()
    assert wf.completed["build"] != old_build and "check" not in wf.completed
    assert wf.run()["status"] == "ready_for_verification"


def test_failed_command_requires_changed_actions_or_actual_predecessor(local_setup):
    value, _, runtime, kwargs = local_setup
    wf = LocalRecoveryWorkflow(recover=lambda wf: None, **kwargs)
    super(LocalRecoveryWorkflow, wf).run()
    recovery = LocalRecovery(wf, value)
    proposal = actions(configure="cmake -S . -B build -DNEW=ON")
    runtime.failures[proposal.steps[0].command] = (1, "missing dependency")
    recovery.revise(proposal)
    assert not recovery.execute("configure")["passed"]
    with pytest.raises(LocalRecoveryInputError, match="相同动作"):
        recovery.execute("configure")
    with pytest.raises(LocalRecoveryInputError, match="无执行变化"):
        recovery.revise(proposal)
    assert runtime.executed.count(proposal.steps[0].command) == 1


@pytest.mark.parametrize("violation", ["source", "frontier", "budget"])
def test_runtime_integrity_and_budget_errors_propagate(local_setup, violation):
    value, source, _, kwargs = local_setup
    wf = LocalRecoveryWorkflow(recover=lambda wf: None, **kwargs)
    super(LocalRecoveryWorkflow, wf).run()
    recovery = LocalRecovery(wf, value)
    recovery.revise(actions())
    if violation == "source":
        (source / "CMakeLists.txt").write_text("changed source")
    elif violation == "frontier":
        wf.manager.record_command(wf._session, BuildCommandRecord(command="echo foreign", workdir="/workspace/repo", role="diagnostic", stage="tool"))
    else:
        wf.commands_used = wf.budget.max_commands
    with pytest.raises(PlanContractError) as error:
        recovery.execute("configure")
    assert not isinstance(error.value, LocalRecoveryInputError)
    events = [json.loads(line) for line in (wf.meter.ledger.root / "events.jsonl").read_text().splitlines()] if hasattr(wf.meter.ledger, "root") else []
    assert not any(e["event"] == "local_recovery.returned" for e in events)


def test_actual_agent_tools_and_meter_return_without_extra_model_request(local_setup, tmp_path):
    from langchain_core.messages import AIMessage
    from test_plan_candidate_reception import COMMON, GateModel, common_harness_interfaces, meter

    from deerflow.compile.local_recovery import run_local_agent

    value, source, _, kwargs = local_setup
    wf = LocalRecoveryWorkflow(recover=lambda wf: None, **kwargs)
    super(LocalRecoveryWorkflow, wf).run()
    accounting, _ = meter(tmp_path / "model", value)
    accounting.packet = lambda: dict(task=value.model_dump(mode="json"), source_packet=[], state=wf.snapshot(), current_plan=wf.plan.model_dump(mode="json"))
    wf.meter = accounting
    cache(source, tests="ON")
    calls = [
        ("return_to_workflow", {}),  # 没有执行不能自报恢复；明确反馈后再修复。
        ("revise_recovery_plan", dict(actions_json=actions().model_dump_json())),
        ("execute_recovery_step", dict(step_id="configure")),
        ("return_to_workflow", {}),
    ]
    model = GateModel(responses=[AIMessage(content="", tool_calls=[dict(name=name, args=args, id=str(i))], **COMMON) for i, (name, args) in enumerate(calls)])
    with common_harness_interfaces():
        run_local_agent(model=model, workflow=wf, task=value, session_root=wf.directory.parent)
    assert wf.status == "pending" and "configure" in wf.completed and "build" not in wf.completed
    assert accounting.summary()["model_requests"] == 4 and accounting.summary()["unknown_usage_requests"] == 0
    events = [json.loads(line) for line in (accounting.ledger.directory / "events.jsonl").read_text().splitlines()]
    assert sum(e["event"] == "local_recovery.input_rejected" for e in events) == 1
    request = json.loads((accounting.ledger.directory / "request-3.json").read_text())
    assert "local_recovery" in request["messages"][0]["content"]
    assert str(wf.directory.parent) not in json.dumps(request)
