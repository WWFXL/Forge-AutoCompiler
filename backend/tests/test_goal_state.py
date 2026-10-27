"""配置状态的真实观测、有界动作及执行前拦截；不调用Provider。"""

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_plan_workflow import ScriptedRuntime, make_plan

from deerflow.compile.build_task_checks import cmake_configuration_command
from deerflow.compile.goal_state import GoalStateWorkflow, configuration_goals, direct_configuration_revision, goal_state_planner, observe_configuration
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.plan_agent import PlanAgentLedger, PlanTask
from deerflow.compile.plan_workflow import PlanBudget, PlanContractError
from deerflow.compile.schemas import BuildCommandRecord
from deerflow.compile.source_preparation import PREPARATION_ID, paths_fingerprint, with_preparation
from deerflow.config.paths import Paths


def task():
    plan = make_plan()
    check = plan.steps[2].model_copy(update={"command": cmake_configuration_command({"BUILD_TESTS": True}), "required_output": ("captured",), "diagnostic_paths": ()})
    return PlanTask(**plan.model_dump(exclude={"steps", "revision", "source_archive_sha256"}), verification_steps=(check,), source_archive_sha256="a" * 64)


def cache(root, *, tests="OFF", dependency=None):
    (root / "build").mkdir(exist_ok=True)
    text = f"BUILD_TESTS:BOOL={tests}\nCMAKE_HOME_DIRECTORY:INTERNAL=/workspace/repo\n"
    if dependency is not None:
        text += f"HAVE_LIBLZO2:INTERNAL={dependency}\n"
    (root / "build/CMakeCache.txt").write_text(text)


def core_plan(value):
    from deerflow.compile.unified_plan_equivalent import BuildActions, assemble_plan

    return assemble_plan(value, BuildActions(reason="受控配置偏离", steps=[s.model_dump() for s in make_plan().steps[:2]]), revision=1)


def test_task_goals_keep_provenance_defaults_and_missing_evidence(tmp_path):
    goals = configuration_goals(task())
    assert [(g.key, g.expected) for g in goals] == [("BUILD_TESTS", True), ("BUILD_SHARED_LIBS", False)]
    assert all(g.verifier_sha256 == hashlib.sha256(task().verification_steps[0].command.encode()).hexdigest() for g in goals)
    missing = observe_configuration(tmp_path, goals)
    assert missing["status"] == "unknown" and all(r["actual"] is None for r in missing["goals"])
    cache(tmp_path)
    observed = observe_configuration(tmp_path, goals)
    assert [r["status"] for r in observed["goals"]] == ["violated", "satisfied"]
    assert all(len(r["evidence_sha256"]) == 64 for r in observed["goals"])
    cache(tmp_path, tests="yes")
    assert observe_configuration(tmp_path, goals)["status"] == "satisfied"


def test_direct_revision_requires_real_option_and_current_evidence(tmp_path):
    value = task()
    plan = core_plan(value)
    cache(tmp_path)
    observation = observe_configuration(tmp_path, configuration_goals(value))
    assert direct_configuration_revision(value, plan, observation, tmp_path) is None
    (tmp_path / "CMakeLists.txt").write_text('option(BUILD_TESTS "original tests" ON)\n')
    revised, _ = direct_configuration_revision(value, plan, observation, tmp_path)
    correction = revised.steps[1]
    assert correction.role == "configure" and "-DBUILD_TESTS:BOOL=ON" in correction.command
    assert revised.steps[0] == plan.steps[0]
    assert revised.steps[-2:] == plan.steps[-2:]
    assert correction.step_id in revised.steps[2].requires
    cache(tmp_path, tests="ON")
    assert direct_configuration_revision(value, plan, observation, tmp_path) is None


def test_dependency_probe_is_never_forced_true(tmp_path):
    value = task()
    step = value.verification_steps[0].model_copy(update={"command": cmake_configuration_command({"HAVE_LIBLZO2": True})})
    value = value.model_copy(update={"verification_steps": (step,)})
    cache(tmp_path, tests="ON", dependency="")
    (tmp_path / "CMakeLists.txt").write_text('check_library_exists(lzo2 some_symbol "" HAVE_LIBLZO2)\n')
    assert direct_configuration_revision(value, core_plan(value), observe_configuration(tmp_path, configuration_goals(value)), tmp_path) is None

    # 即使上游把探测值错误声明为BOOL，也不能通过置ON冒充真实依赖。
    path = tmp_path / "build/CMakeCache.txt"
    path.write_text(path.read_text().replace("HAVE_LIBLZO2:INTERNAL=", "HAVE_LIBLZO2:BOOL="))
    (tmp_path / "CMakeLists.txt").write_text('option(HAVE_LIBLZO2 "probe must not be forced" OFF)\n')
    assert direct_configuration_revision(value, core_plan(value), observe_configuration(tmp_path, configuration_goals(value)), tmp_path) is None


def test_unsupported_or_absent_goals_remain_unknown(tmp_path):
    original = task()
    check = original.verification_steps[0].model_copy(update={"command": "make check"})
    unsupported = original.model_copy(update={"verification_steps": (check,)})
    assert configuration_goals(unsupported) == ()
    assert observe_configuration(tmp_path, configuration_goals(unsupported))["status"] == "unknown"


def test_cache_link_cannot_escape_source_root(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "build").symlink_to(tmp_path)
    with pytest.raises(PlanContractError, match="越出"):
        observe_configuration(root, configuration_goals(task()))


def test_state_stops_before_build_and_persists_through_revision(tmp_path, monkeypatch):
    value, source = task(), tmp_path / "source"
    source.mkdir()
    (source / "CMakeLists.txt").write_text('option(BUILD_TESTS "original tests" ON)\n')
    cache(source)
    frozen = {"CMakeLists.txt": hashlib.sha256((source / "CMakeLists.txt").read_bytes()).hexdigest()}
    expected = paths_fingerprint(frozen)
    plan = with_preparation(core_plan(value), expected)
    manager = CompileSessionManager(paths=Paths(base_dir=tmp_path / "data", workspace_root=tmp_path, host_workspace_root=str(tmp_path)))
    session = manager.create_session("goal-test", value.repository_url)
    session.commit_sha, session.image_id = value.commit_sha, value.image_id
    session.replay_source_archive_sha256 = value.source_archive_sha256
    session.selected_build_system, session.status = "cmake", "inspected"
    manager.save_session(session)
    prepare = plan.steps[0]
    record = BuildCommandRecord(command=prepare.command, workdir=prepare.workdir, role=prepare.role, stage="plan", exit_code=0, timed_out=False)
    manager.record_command(session, record)
    meter = SimpleNamespace(started_monotonic=0, tracker=SimpleNamespace(observe_elapsed=lambda value: None, consume=lambda **kwargs: None), ledger=PlanAgentLedger(tmp_path / "agent"))
    runtime = ScriptedRuntime()
    monkeypatch.setattr("deerflow.compile.plan_agent_canary.time.monotonic", lambda: 0)
    workflow = GoalStateWorkflow(
        plan=plan, session=session, manager=manager, runtime=runtime, preparation_command_id=record.command_id, meter=meter, source_root=source, frozen=frozen, budget=PlanBudget(wall_clock_seconds=1200), clock=lambda: 0
    )
    first = workflow.run()
    assert first["status"] == "needs_handoff"
    assert first["handoff"]["reason"] == "configuration_goal_violated"
    assert runtime.executed == ["cmake -S . -B build"]
    assert "build" not in workflow.completed
    assert first["handoff"]["persistent_configuration_goals"]

    called = []

    def agent(**kwargs):
        called.append(kwargs)
        return "original-agent"

    planner = goal_state_planner(agent)
    args = dict(task=value, current_plan=workflow.plan, handoff=first["handoff"], source_root=source, meter=meter)
    revised, reason = planner(**args)
    assert called == [] and all(s.step_id != PREPARATION_ID for s in revised.steps)
    workflow.apply_revision(handoff_id=first["handoff"]["handoff_id"], plan=with_preparation(revised, expected), reason=reason)
    assert workflow.goal_state["status"] == "unknown" and not workflow.goal_blocked
    # 模拟新configure真正生成了正确缓存，原目标仍在Workflow中。
    cache(source, tests="ON")
    assert workflow.run()["status"] == "ready_for_verification"
    assert workflow.goal_state["status"] == "satisfied"
    assert runtime.executed.count("cmake --build build") == 1
    assert len([s for s in workflow.replay_recipe().steps if s.role == "configure"]) == 2
    assert planner(**args) == "original-agent" and len(called) == 1
    events = [json.loads(line) for line in (tmp_path / "agent/events.jsonl").read_text().splitlines()]
    assert events[0]["action"] == "direct_configuration_revision"


def test_schedule_covers_all_pairs_and_time_contract():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import forge_build_goal_state_comparison as runner

    rows = runner.schedule()
    assert len(rows) == 24
    for project in runner.replication.PROJECTS:
        for repetition in (1, 2):
            assert {r["method"] for r in rows if r["project"] == project and r["repetition"] == repetition} == set(runner.METHODS)
    assert runner.TIMING.new_slot_reserve_seconds == runner.TIMING.node_seconds + runner.TIMING.replay_seconds + runner.TIMING.cleanup_reserve_seconds
