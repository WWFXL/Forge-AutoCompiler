"""用真实Shell和真实Agent图验证观察语义、纠错预算与固定裁判边界。"""

import json
import subprocess
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from test_plan_agent import ScriptedPlanModel, response
from test_tool_plan import task

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_agent_context import ContextCanaryMeter
from deerflow.compile.unified_plan_v2 import ObservedBuildActions, assemble_observed, compile_action, execution_changed, observed_planner, propose_observed, recovery_feedback


def actions(**changes):
    return ObservedBuildActions(reason="实际Makefile", steps=[{"step_id": "build", "role": "build", "command": "make -j2", "source": "Makefile", "expected": "执行构建", **changes}])


def shell(action, root):
    return subprocess.run(["bash", "-euo", "pipefail", "-c", compile_action(action).command], cwd=root, capture_output=True, text=True, timeout=10)


def meter(root):
    return ContextCanaryMeter(PlanAgentLedger(root / "agent"), accepted_models=("test-model",), deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat(), packet=lambda: {"task": task().model_dump(mode="json"), "source_packet": []})


def test_file_path_need_not_appear_in_output_and_is_in_replay_command(tmp_path):
    action = actions(command="mkdir -p build; touch build/CMakeCache.txt", files_exist=["build/CMakeCache.txt"], directories_exist=["build/"]).steps[0]
    compiled = compile_action(action)
    assert compiled.required_output == () and action.directories_exist == ("build",)
    assert shell(action, tmp_path).returncode == 0
    plan = assemble_observed(task(), ObservedBuildActions(reason="构建", steps=[action]), revision=1)
    assert "FORGE_PATH_OBSERVATIONS" in plan.steps[0].command
    assert plan.steps[-2] == task().verification_steps[0]


@pytest.mark.parametrize("field,path", [("files_exist", "missing.a"), ("directories_exist", "missing/")])
def test_missing_file_or_directory_fails_after_successful_command(tmp_path, field, path):
    result = shell(actions(command="true", **{field: [path]}).steps[0], tmp_path)
    assert result.returncode == 86 and '"passed": false' in result.stdout


def test_original_nonzero_is_preserved_and_checker_is_not_run(tmp_path):
    result = shell(actions(command="exit 17", directories_exist=["missing/"]).steps[0], tmp_path)
    assert result.returncode == 17 and "FORGE_PATH_OBSERVATIONS" not in result.stdout


@pytest.mark.parametrize("command", ["exit 0", "exec true"])
def test_exit_or_exec_cannot_skip_file_check(tmp_path, command):
    assert shell(actions(command=command, files_exist=["missing"]).steps[0], tmp_path).returncode == 86


def test_types_and_external_symlinks_do_not_pass(tmp_path):
    (tmp_path / "directory").mkdir()
    assert shell(actions(command="true", files_exist=["directory"]).steps[0], tmp_path).returncode == 86
    (tmp_path / "file").touch()
    assert shell(actions(command="true", directories_exist=["file"]).steps[0], tmp_path).returncode == 86
    (tmp_path / "outside").symlink_to(tmp_path.parent, target_is_directory=True)
    assert shell(actions(command="true", directories_exist=["outside"]).steps[0], tmp_path).returncode == 86


@pytest.mark.parametrize("value", ["../outside/", "/etc/", "./build/", "build//other/", "C:\\build\\", "", "/"])
def test_only_safe_trailing_directory_slash_is_normalized(value):
    with pytest.raises(ValidationError):
        actions(directories_exist=[value])


def test_old_field_rejected_and_schema_explains_types():
    with pytest.raises(ValidationError):
        actions(required_output=["build/CMakeCache.txt"])
    schema = str(ObservedBuildActions.model_json_schema())
    assert "不要填文件路径" in schema and "普通文件" in schema
    assert actions(diagnostic_paths=["logs/", "src/libsodium/.libs/"]).steps[0].diagnostic_paths == ("logs", "src/libsodium/.libs")


def test_order_is_rejected_not_silently_rearranged():
    value = actions().model_dump()
    value["steps"].append({**value["steps"][0], "step_id": "configure", "role": "configure"})
    with pytest.raises(ValidationError, match="按顺序"):
        ObservedBuildActions.model_validate(value)


def test_description_change_is_not_execution_change():
    before = assemble_observed(task(), actions(), revision=1)
    after = assemble_observed(task(), actions(expected="改了说明"), revision=2)
    assert not execution_changed(before, after)
    assert execution_changed(before, assemble_observed(task(), actions(command="make -j1"), revision=2))


def test_real_graph_corrects_legacy_field_once_and_keeps_original_response(tmp_path):
    invalid = actions().model_dump(mode="json")
    invalid["steps"][0]["required_output"] = ["build/CMakeCache.txt"]
    model = ScriptedPlanModel(responses=[response("ObservedBuildActions", invalid), response("ObservedBuildActions", actions().model_dump(mode="json"))])
    metering = meter(tmp_path)
    plan, _ = propose_observed(model=model, task=task(), source_root=tmp_path, session_root=tmp_path, meter=metering)
    assert plan.steps[-2] == task().verification_steps[0]
    assert metering.summary()["model_requests"] == 2
    assert (tmp_path / "agent/response-1.json").exists()
    assert "required_output" in (tmp_path / "agent/response-1.json").read_text()


def test_second_invalid_response_stops_instead_of_retrying_forever(tmp_path):
    invalid = actions().model_dump(mode="json")
    invalid["steps"][0]["required_output"] = ["file"]
    model = ScriptedPlanModel(responses=[response("ObservedBuildActions", invalid)] * 3)
    metering = meter(tmp_path)
    with pytest.raises(Exception, match="required_output"):
        propose_observed(model=model, task=task(), source_root=tmp_path, session_root=tmp_path, meter=metering)
    assert metering.summary()["model_requests"] == 2


def test_unchanged_recovery_gets_one_correction_and_changed_command(tmp_path):
    current = assemble_observed(task(), actions(command="false"), revision=1)
    model = ScriptedPlanModel(responses=[response("ObservedBuildActions", actions(command="false", expected="说明变化").model_dump(mode="json")), response("ObservedBuildActions", actions().model_dump(mode="json"))])
    metering = meter(tmp_path)
    plan, _ = propose_observed(model=model, task=task(), source_root=tmp_path, session_root=tmp_path, meter=metering, current_plan=current, handoff={"handoff_id": "real", "plan_sha256": current.fingerprint()})
    assert execution_changed(current, plan) and metering.summary()["model_requests"] == 2


@pytest.mark.parametrize("code,category", [(0, "output_expectation_missing"), (2, "command_failed")])
def test_recovery_feedback_distinguishes_exit_and_text(code, category):
    current = assemble_observed(task(), actions(stdout_contains=["expected literal"]), revision=1)
    step = current.steps[0]
    handoff = {"step_id": "build", "recent_commands": [{"command": step.command, "role": step.role, "workdir": step.workdir, "exit_code": code, "output_tail": "real output"}]}
    assert recovery_feedback(current, handoff)["category"] == category


def test_tool_and_model_assemble_same_tail(tmp_path):
    (tmp_path / "Makefile").write_text("all:\n\ttrue\n")
    metering = meter(tmp_path)
    tool, _ = observed_planner("tool")(task=task(), source_root=tmp_path, session_root=tmp_path, meter=metering)
    assert tool.steps[-2:] == assemble_observed(task(), actions(), revision=1).steps[-2:]
    assert metering.summary()["model_requests"] == 0
    assert json.loads((tmp_path / "agent/tool-receipt.json").read_text())["plan_sha256"] == tool.fingerprint()


def test_provider_exception_is_not_structural_correction(tmp_path):
    class FailingModel(ScriptedPlanModel):
        def _generate(self, *args, **kwargs):
            raise ConnectionError("受控Provider连接异常")

    metering = meter(tmp_path)
    with pytest.raises(ConnectionError):
        propose_observed(model=FailingModel(responses=[]), task=task(), source_root=tmp_path, session_root=tmp_path, meter=metering)
    assert metering.summary()["model_requests"] == 1
    assert "observed.proposal_rejected" not in (tmp_path / "agent/events.jsonl").read_text()
