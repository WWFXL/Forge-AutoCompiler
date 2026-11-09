"""执行契约的行为回归：合法方案可推进，观察未知不代替最终成功判定。"""

import json
import shutil
import subprocess

import pytest
from test_plan_agent import ScriptedPlanModel, response
from test_simple_build import LocalRuntime, reference, simple_actions

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_workflow import PlanContractError, PlanStep
from deerflow.compile.simple_build_agents import SimpleBuildMeter
from deerflow.compile.simple_build_runtime import SimpleBuildWorkflow, configuration_entry, generated_reset_step
from deerflow.compile.simple_build_task import SimpleBuildActions, assemble_simple_plan, propose_simple

pytest_plugins = ("test_simple_build",)


def build_workflow(runner, system, steps, *, with_reset=False, **context):
    t, session, manager, _ = runner
    t = t.model_copy(update={"build_system": system})
    session.build_system = session.selected_build_system = system
    manager.save_session(session)
    proposal = SimpleBuildActions(reason="真实工具工程夹具", steps=steps, **context)
    plan = assemble_simple_plan(t, proposal)
    if with_reset:
        from deerflow.compile.simple_build_runtime import source_inventory

        plan = plan.model_copy(update={"steps": (generated_reset_step(source_inventory(runner[3])), *plan.steps)})
    return SimpleBuildWorkflow(plan=plan, session=session, manager=manager, runtime=LocalRuntime(), reference=reference(t))


def step(name, role, command):
    return dict(step_id=name, role=role, command=command, source="夹具作者构建文件", expected="由实际执行确认")


@pytest.mark.skipif(not shutil.which("cmake"), reason="需要原生CMake")
def test_redirected_preset_and_build_preset_complete_with_unknown_observation(runner):
    root = runner[3]
    (root / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.21)\nproject(sample C)\nadd_library(sample STATIC sample.c)\n")
    (root / "CMakePresets.json").write_text(json.dumps(dict(version=3, configurePresets=[dict(name="gcc", generator="Unix Makefiles", binaryDir="${sourceDir}/build")], buildPresets=[dict(name="gcc", configurePreset="gcc")])))
    w = build_workflow(runner, "cmake", [step("configure", "configure", "cmake --preset gcc > configure.log 2>&1"), step("build", "build", "cmake --build --preset gcc")])
    assert w.run()["status"] == "primary_completed"
    assert w.configuration["status"] == "unknown" and w.configuration["directory"] is None
    assert w.handoffs_used == 0 and len(w._session.commands) == 2
    assert w.primary["artifacts"][0]["path"] == "build/libsample.a"


@pytest.mark.skipif(not shutil.which("autoconf"), reason="需要原生Autoconf")
@pytest.mark.parametrize("filename", ["GNUmakefile", "project.mk"])
def test_autoconf_native_and_custom_makefile_both_build(runner, filename):
    root = runner[3]
    (root / "Makefile").unlink()
    (root / "configure.ac").write_text(f"AC_INIT([sample],[1.0])\nAC_CONFIG_SRCDIR([sample.c])\nAC_PROG_CC\nAC_CONFIG_FILES([{filename}])\nAC_OUTPUT\n")
    (root / (filename + ".in")).write_text("CC=@CC@\nlibsample.a: sample.c\n\t$(CC) -c sample.c -o sample.o\n\tar rcs libsample.a sample.o\n")
    subprocess.run(["autoconf"], cwd=root, check=True, capture_output=True, timeout=30)
    w = build_workflow(runner, "autotools", [step("configure", "configure", "./configure"), step("build", "build", f"make -f {filename}")])
    assert w.run()["status"] == "primary_completed"
    assert w.configuration["status"] == ("passed" if filename == "GNUmakefile" else "unknown")
    assert w.handoffs_used == 0 and w.layers["primary_build_completed"] is True


def test_unknown_and_zero_exit_without_product_do_not_complete(runner):
    w = build_workflow(runner, "cmake", [step("configure", "configure", "true"), step("build", "build", "true")])
    result = w.run()
    assert len(w._session.commands) == 2
    assert result["handoff"]["reason"] == "primary_components_missing_or_unobserved"
    assert w.configuration["status"] == "unknown" and w.layers["primary_build_completed"] is False


def test_real_intermediate_failure_stops_before_remaining_actions(runner):
    w = build_workflow(runner, "autotools", [step("prepare", "configure", "exit 37"), step("configure", "configure", "true"), step("build", "build", "make")])
    assert w.run()["status"] == "needs_handoff"
    assert len(w._session.commands) == 1 and w._session.commands[0].exit_code == 37
    assert w.handoff["reason"] == "step_failed_or_expectation_missing"


def test_bound_configuration_conflict_stops_before_build(runner):
    root = runner[3]
    (root / "CMakeLists.txt").write_text("project(sample C)\n")
    (root / "CMakeCache.txt").write_text("CMAKE_GENERATOR:INTERNAL=Unix Makefiles\nCMAKE_HOME_DIRECTORY:INTERNAL=/workspace/repo/other\nCMAKE_CACHEFILE_DIR:INTERNAL=/workspace/repo\n")
    w = build_workflow(runner, "cmake", [step("configure", "configure", "true"), step("build", "build", "make")], build_directory="/workspace/repo")
    assert w.run()["status"] == "needs_handoff"
    assert len(w._session.commands) == 1 and w._session.commands[0].exit_code == 0
    assert w.handoff["reason"] == "configuration_inconsistent"


def test_explicit_context_is_verified_and_survives_recovery(runner):
    root = runner[3]
    (root / "CMakeLists.txt").write_text("project(sample C)\n")
    (root / "CMakeCache.txt").write_text("CMAKE_GENERATOR:INTERNAL=Unix Makefiles\nCMAKE_HOME_DIRECTORY:INTERNAL=/workspace/repo\nCMAKE_CACHEFILE_DIR:INTERNAL=/workspace/repo\n")
    w = build_workflow(runner, "cmake", [step("build", "build", "make missing-target")], build_directory="/workspace/repo")
    w.run()
    proposal = SimpleBuildActions(reason="修复错误目标", steps=[step("build", "build", "make")], build_directory="/workspace/repo")
    w.apply_revision(handoff_id=w.handoff["handoff_id"], plan=assemble_simple_plan(w.plan.task, proposal, revision=2), reason=proposal.reason)
    assert w.plan.build_directory == "/workspace/repo"
    assert w.run()["status"] == "primary_completed" and w.configuration["status"] == "passed"


@pytest.mark.parametrize("with_reset", [False, True])
def test_wrong_observation_context_is_repaired_without_reexecuting_success(runner, tmp_path, with_reset):
    root = runner[3]
    (root / "CMakeLists.txt").write_text("project(sample C)\n")
    cache = "CMAKE_GENERATOR:INTERNAL=Unix Makefiles\nCMAKE_HOME_DIRECTORY:INTERNAL=/workspace/repo\nCMAKE_CACHEFILE_DIR:INTERNAL=/workspace/repo\n"
    (root / "CMakeCache.txt").write_text(cache)
    (root / "copied").mkdir()
    (root / "copied/CMakeCache.txt").write_text(cache)
    (root / "copied/Makefile").write_text("all:\n")
    steps = [step("configure", "configure", "true"), step("build", "build", "make")]
    w = build_workflow(runner, "cmake", steps, build_directory="/workspace/repo/copied", with_reset=with_reset)
    w.run()
    assert w.handoff["reason"] == "configuration_inconsistent"
    success_id = w._session.commands[-1].command_id
    invalid = SimpleBuildActions(reason="没有证据的观察提示", steps=steps, build_directory="/workspace/repo/missing")
    with pytest.raises(PlanContractError, match="新观察目录没有通过"):
        w.validate_revision(assemble_simple_plan(w.plan.task, invalid, revision=2))
    proposal = SimpleBuildActions(reason="依据实际Cache纠正观察绑定", steps=steps, build_directory="/workspace/repo")
    meter = SimpleBuildMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline="2099-01-01T00:00:00+00:00", packet=lambda: {})
    model = ScriptedPlanModel(responses=[response("SimpleBuildActions", proposal.model_dump(mode="json"))])
    revised, reason = propose_simple(model=model, task=w.plan.task, source_root=root, session_root=tmp_path, meter=meter, current_plan=w.plan, handoff=w.handoff, revision_validator=w.validate_revision)
    w.apply_revision(handoff_id=w.handoff["handoff_id"], plan=revised, reason=reason)
    assert w.completed["configure"] == success_id and len(w._session.commands) == 1 + with_reset
    assert w.run()["status"] == "primary_completed" and len(w._session.commands) == 2 + with_reset
    assert ("forge-generated-reset" in w.completed) == with_reset
    assert meter.summary()["model_requests"] == 1


@pytest.mark.parametrize("directory", ["build", "/artifacts", "/workspace/repo/../escape", "/workspace/repo/build/"])
def test_invalid_observation_context_is_rejected(directory):
    with pytest.raises(ValueError):
        SimpleBuildActions(reason="非法目录", steps=simple_actions().steps, build_directory=directory)


def test_preset_argument_is_never_interpreted_as_directory(tmp_path):
    s = PlanStep(**step("build", "build", "cmake --build --preset gcc"))
    assert configuration_entry(tmp_path, s, dict(build_system="cmake", directory="build")) == ("cmake", "build")
    assert configuration_entry(tmp_path, s, dict(build_system="cmake")) == ("cmake", None)


def test_observation_does_not_substitute_a_stale_cache(runner):
    root = runner[3]
    (root / "old").mkdir()
    (root / "old/CMakeCache.txt").write_text("CMAKE_GENERATOR:INTERNAL=Unix Makefiles\n")
    w = build_workflow(runner, "cmake", [step("configure", "configure", "true"), step("build", "build", "make")])
    assert w.run()["status"] == "primary_completed"
    assert w.configuration["status"] == "unknown" and w.configuration["directory"] is None


@pytest.mark.parametrize("still_invalid", [False, True])
def test_recovery_receives_one_execution_feedback_and_preserves_failure(runner, tmp_path, still_invalid):
    w = build_workflow(runner, "make", [step("build", "build", "make missing-target")])
    w.run()
    failed_id = w._session.commands[-1].command_id
    invalid = SimpleBuildActions(reason="只修改说明", steps=[step("build", "build", "make missing-target")])
    valid = simple_actions()
    model = ScriptedPlanModel(responses=[response("SimpleBuildActions", p.model_dump(mode="json")) for p in [invalid, invalid if still_invalid else valid]])
    meter = SimpleBuildMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline="2099-01-01T00:00:00+00:00", packet=lambda: {})
    if still_invalid:
        with pytest.raises(PlanContractError, match="没有改变实际执行动作"):
            propose_simple(model=model, task=w.plan.task, source_root=w.root, session_root=tmp_path, meter=meter, current_plan=w.plan, handoff=w.handoff)
        assert not (tmp_path / "agent/request-3.json").exists()
    else:
        revised, reason = propose_simple(model=model, task=w.plan.task, source_root=w.root, session_root=tmp_path, meter=meter, current_plan=w.plan, handoff=w.handoff)
        w.apply_revision(handoff_id=w.handoff["handoff_id"], plan=revised, reason=reason)
        assert w.run()["status"] == "primary_completed"
        assert w.completed["build"] != failed_id
    sent = json.loads((tmp_path / "agent/request-2.json").read_text())
    assert "没有改变实际执行动作" in json.dumps(sent, ensure_ascii=False)
    assert (tmp_path / "agent/response-1.json").exists()
    assert meter.summary()["model_requests"] == 2
    assert len([r for r in w._session.commands if r.command == "make missing-target"]) == 1


def test_renaming_steps_cannot_trigger_unchanged_failed_command(runner):
    w = build_workflow(runner, "make", [step("prepare", "dependency", "command -v cc"), step("build", "build", "make missing-target")])
    w.run()
    proposal = SimpleBuildActions(reason="只改步骤别名", steps=[step("renamed", "dependency", "command -v cc"), step("build", "build", "make missing-target")])
    with pytest.raises(PlanContractError, match="没有改变实际执行动作"):
        w.apply_revision(handoff_id=w.handoff["handoff_id"], plan=assemble_simple_plan(w.plan.task, proposal, revision=2), reason=proposal.reason)
    assert len(w._session.commands) == 2
