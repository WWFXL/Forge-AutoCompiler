"""构建方案的交接、修订、验收边界与证据保留测试。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from deerflow.compile import plan_workflow
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.plan_workflow import BuildPlan, PlanBudget, PlanContractError, PlanStep, PlanWorkflow
from deerflow.compile.schemas import BuildCommandRecord, CommandResult, utc_now_iso
from deerflow.config.paths import Paths

IMAGE_ID = "sha256:" + "1" * 64


def make_plan() -> BuildPlan:
    return BuildPlan(
        plan_id="sample",
        repository_url="https://example.com/sample.git",
        commit_sha="a" * 40,
        image_id=IMAGE_ID,
        build_system="cmake",
        artifact_paths=("libsample.a",),
        steps=(
            PlanStep(step_id="configure", role="configure", command="cmake -S . -B build", source="README:10", expected="生成构建文件"),
            PlanStep(step_id="build", role="build", command="cmake --build build", requires=("configure",), source="README:11", expected="编译成功"),
            PlanStep(
                step_id="check",
                role="smoke",
                command="ctest --test-dir build",
                requires=("build",),
                source="CI:12",
                expected="执行任务测试",
                required_output=("tests passed",),
                diagnostic_paths=("build/Testing/Temporary/LastTest.log",),
            ),
            PlanStep(step_id="stage", role="artifact_stage", command="cp build/libsample.a /artifacts/libsample.a", source="CMakeLists.txt:15", expected="整理库"),
        ),
    )


class ScriptedRuntime:
    def __init__(self, failures: dict | None = None):
        self.failures = failures or {}
        self.executed: list[str] = []
        self.diagnostics: list[str] = []

    def exec(self, session, command, *, workdir, timeout_seconds, log_path, strict_shell):
        assert strict_shell and timeout_seconds > 0
        if command.startswith("python3 -c "):
            self.diagnostics.append(command)
            output = '[{"status":"captured"}]'
            Path(log_path).write_text(output)
            return CommandResult(0, output, "", output, log_path)
        self.executed.append(command)
        outcome = self.failures.get(command, (0, "tests passed"))
        if isinstance(outcome, Exception):
            raise outcome
        code, output = outcome
        Path(log_path).write_text(output)
        if command.startswith("cp ") and code == 0:
            (Path(session.metadata_path).parent / "artifacts" / "libsample.a").write_bytes(b"!<arch>\n")
        return CommandResult(code, output, "", output, log_path)


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEER_FLOW_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("DEER_FLOW_HOST_WORKSPACE_ROOT", str(tmp_path))
    manager = CompileSessionManager(paths=Paths(base_dir=tmp_path / "data", workspace_root=tmp_path, host_workspace_root=str(tmp_path)))
    plan = make_plan()
    session = manager.create_session("plan-test", plan.repository_url)
    session.commit_sha = plan.commit_sha
    session.image_id = plan.image_id
    session.selected_build_system = "cmake"
    session.status = "inspected"
    manager.save_session(session)
    return manager, session, plan


def workflow(setup, runtime=None, **kwargs):
    manager, session, plan = setup
    return PlanWorkflow(plan=plan, session=session, manager=manager, runtime=runtime or ScriptedRuntime(), **kwargs)


def revised(plan, *, command="cmake -S . -B build -DREQUIRED=ON", role="configure"):
    steps = tuple(step.model_copy(update={"command": command}) if step.role == role else step for step in plan.steps)
    return BuildPlan.model_validate({**plan.model_dump(), "revision": plan.revision + 1, "steps": steps})


def test_normal_plan_produces_explicit_recipe_without_claiming_verified(setup):
    runner = workflow(setup)
    assert runner.run()["status"] == "ready_for_verification"
    recipe = runner.replay_recipe()
    assert [step.role for step in recipe.steps] == ["configure", "build", "artifact_stage"]
    assert [step.role for step in recipe.verification_steps] == ["smoke"]
    assert setup[0].load_session(setup[1].session_id, setup[1].thread_id).status == "inspected"


def test_failed_test_captures_diagnostics_before_handoff_and_does_not_repeat(setup):
    runtime = ScriptedRuntime({"ctest --test-dir build": (8, "1 failed")})
    runner = workflow(setup, runtime)
    first = runner.run()
    assert first["status"] == "needs_handoff"
    assert "check" not in runner.completed and "stage" not in runner.completed
    assert len(runtime.diagnostics) == 1
    assert "LastTest.log" in runtime.diagnostics[0]
    assert runner.run()["handoff"]["handoff_id"] == first["handoff"]["handoff_id"]
    assert runtime.executed.count("ctest --test-dir build") == 1
    assert first["handoff"]["recent_commands"][-1]["exit_code"] == 8
    assert first["handoff"]["recent_commands"][-1]["output_tail"] == "1 failed"
    assert len(first["handoff"]["recent_commands"][-1]["log_sha256"]) == 64


def test_revision_recovers_and_recipe_excludes_failed_command(setup):
    runtime = ScriptedRuntime({"cmake -S . -B build": (1, "missing configuration")})
    runner = workflow(setup, runtime)
    request = runner.run()["handoff"]
    runner.apply_revision(handoff_id=request["handoff_id"], plan=revised(runner.plan), reason="根据项目文档修正配置")
    assert runner.run()["status"] == "ready_for_verification"
    recipe = runner.replay_recipe()
    records = setup[0].load_session(setup[1].session_id, setup[1].thread_id).commands
    assert records[0].exit_code == 1
    assert records[0].command_id not in [row.command_id for row in recipe.steps]
    assert runner.handoffs_used == 1


def test_changed_configuration_invalidates_prior_successful_build(setup):
    runtime = ScriptedRuntime({"ctest --test-dir build": (8, "failed")})
    runner = workflow(setup, runtime)
    request = runner.run()["handoff"]
    old_build = runner.completed["build"]
    runner.apply_revision(handoff_id=request["handoff_id"], plan=revised(runner.plan), reason="配置变化必须重建")
    assert runner.completed == {}
    runtime.failures.clear()
    assert runner.run()["status"] == "ready_for_verification"
    assert runtime.executed.count("cmake --build build") == 2
    assert runner.completed["build"] != old_build
    assert old_build not in [row.command_id for row in runner.replay_recipe().steps]


def test_new_dependency_precedes_configuration_and_is_in_recipe(setup):
    runner = workflow(setup, ScriptedRuntime({"cmake -S . -B build": (1, "missing input")}))
    request = runner.run()["handoff"]
    install = PlanStep(step_id="install", role="dependency", command="apt-get install -y libexample-dev", source="CI:5", expected="安装依赖")
    plan = BuildPlan.model_validate({**runner.plan.model_dump(), "revision": 2, "steps": (install, *runner.plan.steps)})
    runner.apply_revision(handoff_id=request["handoff_id"], plan=plan, reason="CI给出缺失依赖")
    runner.runtime.failures.clear()
    assert runner.run()["status"] == "ready_for_verification"
    assert runner.replay_recipe().steps[0].role == "dependency"


@pytest.mark.parametrize("change", ["same", "metadata_only", "smoke", "artifact", "commit", "wrong_id"])
def test_rejects_noop_or_changed_acceptance_and_stale_handoff(setup, change):
    runner = workflow(setup, ScriptedRuntime({"ctest --test-dir build": (1, "failed")}))
    request = runner.run()["handoff"]
    plan = revised(runner.plan)
    payload = plan.model_dump()
    handoff_id = request["handoff_id"]
    if change == "same":
        payload["steps"] = runner.plan.steps
    elif change == "metadata_only":
        payload["steps"] = tuple(step.model_copy(update={"source": "仅改出处"}) if step.role == "configure" else step for step in runner.plan.steps)
    elif change == "smoke":
        payload["steps"] = tuple(step.model_copy(update={"command": "true"}) if step.role == "smoke" else step for step in plan.steps)
    elif change == "artifact":
        payload["artifact_paths"] = ("different.a",)
    elif change == "commit":
        payload["commit_sha"] = "b" * 40
    else:
        handoff_id = "outdated"
    with pytest.raises(PlanContractError):
        runner.apply_revision(handoff_id=handoff_id, plan=BuildPlan.model_validate(payload), reason="测试拒绝")
    assert runner.plan.revision == 1


def test_foreign_command_invalidates_handoff(setup):
    runner = workflow(setup, ScriptedRuntime({"cmake -S . -B build": (1, "failed")}))
    request = runner.run()["handoff"]
    manager, session, _ = setup
    current = manager.load_session(session.session_id, session.thread_id)
    manager.record_command(current, BuildCommandRecord(stage="foreign", command="true", workdir="/workspace/repo", exit_code=0, completed_at=utc_now_iso()))
    with pytest.raises(PlanContractError, match="命令记录变化"):
        runner.apply_revision(handoff_id=request["handoff_id"], plan=revised(runner.plan), reason="旧交接")


def test_empty_test_success_is_not_accepted(setup):
    runner = workflow(setup, ScriptedRuntime({"ctest --test-dir build": (0, "No tests were found")}))
    assert runner.run()["status"] == "needs_handoff"
    assert "check" not in runner.completed


@pytest.mark.parametrize("budget", [PlanBudget(max_commands=1), PlanBudget(max_handoffs=0)])
def test_command_or_handoff_budget_stops_execution(setup, budget):
    runner = workflow(setup, ScriptedRuntime({"cmake -S . -B build": (1, "failed")}), budget=budget)
    assert runner.run()["status"] == "budget_exhausted"
    assert runner.commands_used == 1


def test_wall_clock_expiry_prevents_execution(setup):
    now = [0.0]
    runner = workflow(setup, clock=lambda: now[0], budget=PlanBudget(wall_clock_seconds=5))
    now[0] = 5
    assert runner.run()["status"] == "budget_exhausted"
    assert runner.commands_used == 0


def test_timeout_preserves_audit_and_diagnostics(setup):
    runner = workflow(setup, ScriptedRuntime({"ctest --test-dir build": subprocess.TimeoutExpired("ctest", 1)}))
    assert runner.run()["status"] == "needs_handoff"
    record = runner.handoff["recent_commands"][-1]
    assert record["timed_out"] and record["exit_code"] == 124
    assert Path(record["log_path"]).is_file()
    assert runner.runtime.diagnostics


def test_acceptance_callback_cannot_self_report_verified_without_replay(setup, monkeypatch):
    runner = workflow(setup)
    runner.run()

    def false_success(**kwargs):
        session = kwargs["session"]
        session.status = "verified"
        runner.manager.save_session(session)
        return "成功"

    monkeypatch.setattr(plan_workflow, "submit_build_result_impl", false_success)
    monkeypatch.setattr(plan_workflow, "get_compile_services", lambda: SimpleNamespace(manager=runner.manager, runtime=runner.runtime))
    assert runner.verify()["status"] == "needs_handoff"
    assert runner.handoff["reason"] == "acceptance_failed"


def test_artifact_set_must_match_original_task(setup):
    runner = workflow(setup)
    runner.run()
    (Path(setup[1].metadata_path).parent / "artifacts" / "unexpected.a").write_bytes(b"extra")
    assert runner.verify()["handoff"]["reason"] == "artifact_set_mismatch"


@pytest.mark.parametrize("value", ["../escape", "/etc/passwd", "a/../../b", "."])
def test_diagnostic_paths_are_bounded(value):
    with pytest.raises(ValidationError):
        PlanStep(step_id="test", role="smoke", command="true", expected="检查", source="CI", required_output=("passed",), diagnostic_paths=(value,))


def test_verification_requires_output_evidence():
    with pytest.raises(ValidationError, match="非空输出依据"):
        PlanStep(step_id="check", role="smoke", command="ctest", expected="检查", source="CI")


@pytest.mark.parametrize("command", ["set +e; false", "cmake -S . -B build && cmake --build build"])
def test_disallowed_commands_are_rejected_before_execution(setup, command):
    manager, session, plan = setup
    payload = plan.model_dump()
    payload["steps"] = (plan.steps[0].model_copy(update={"command": command}), *plan.steps[1:])
    runner = PlanWorkflow(plan=BuildPlan.model_validate(payload), session=session, manager=manager, runtime=ScriptedRuntime())
    with pytest.raises(PlanContractError, match="严格 Shell"):
        runner.run()
    assert runner.commands_used == 0


def test_rejects_out_of_order_dependency_and_duplicate_steps():
    plan = make_plan()
    dependency = PlanStep(step_id="dep", role="dependency", command="true", source="CI", expected="依赖")
    for steps in [(plan.steps[0], dependency, *plan.steps[1:]), (*plan.steps, plan.steps[-1])]:
        with pytest.raises(ValidationError):
            BuildPlan.model_validate({**plan.model_dump(), "steps": steps})


def test_session_identity_and_json_roundtrip(setup):
    manager, session, plan = setup
    assert BuildPlan.model_validate_json(plan.model_dump_json()).fingerprint() == plan.fingerprint()
    session.commit_sha = "b" * 40
    manager.save_session(session)
    with pytest.raises(PlanContractError, match="身份"):
        workflow(setup)


def test_persists_plan_and_structured_state(setup):
    runner = workflow(setup)
    runner.run()
    state = json.loads((runner.directory / "state.json").read_text())
    assert state["status"] == "ready_for_verification"
    assert state["plan_sha256"] == runner.plan.fingerprint()
    assert (runner.directory / "plan-1.json").is_file()


def test_handoff_snapshot_is_not_mutable_internal_state(setup):
    runner = workflow(setup, ScriptedRuntime({"cmake -S . -B build": (1, "failed")}))
    snapshot = runner.run()
    original = runner.handoff["handoff_id"]
    snapshot["handoff"]["handoff_id"] = "changed"
    assert runner.handoff["handoff_id"] == original


def test_rejects_different_acceptance_service(setup):
    runner = workflow(setup)
    runner.run()
    with pytest.raises(PlanContractError, match="验收服务"):
        runner.verify()
