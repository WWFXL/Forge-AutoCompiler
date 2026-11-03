"""核对配方失配、固定测试保留与检索隔离，不模拟模型效果。"""

import copy
import json

import pytest

from deerflow.compile.plan_agent import PlanTask
from deerflow.compile.plan_workflow import PlanContractError, PlanStep
from deerflow.compile.project_experience import StateTargetBank, verified_recipe
from deerflow.compile.unified_plan_equivalent import BuildActions, assemble_plan


def task():
    return PlanTask(
        plan_id="recipe-test",
        repository_url="https://example.com/repo",
        commit_sha="a" * 40,
        image_id="sha256:" + "b" * 64,
        source_archive_sha256="c" * 64,
        build_system="cmake",
        artifact_paths=["libdemo.a"],
        verification_steps=[PlanStep(step_id="check", role="smoke", command="./test", requires=["build"], source="原测试", expected="完整通过", required_output=("PASS",))],
    )


def make_recipe():
    current = task()
    plan = assemble_plan(current, BuildActions(reason="已有成功", steps=[dict(step_id="build", role="build", command="cmake --build build", source="构建声明", expected="库生成")]), revision=2)
    validation = dict(full_completed=True, source_unchanged=True, cleanup=dict(succeeded=True), replay=[dict(status="passed")])
    return current, plan, validation, verified_recipe(source_id="seed", task=current, plan=plan, validation=validation)


def test_recipe_rejects_identity_change_and_keeps_current_tests():
    current, _, _, recipe = make_recipe()
    assert recipe.match(current) == "exact"
    changed = current.model_copy(update={"verification_steps": (current.verification_steps[0].model_copy(update={"command": "./new-test"}),)})
    assert recipe.match(changed) == "goal_changed_trial"
    assert recipe.materialize(changed).steps[-2].command == "./new-test"
    wrong = current.model_copy(update={"image_id": "sha256:" + "d" * 64})
    assert recipe.match(wrong) is None
    with pytest.raises(PlanContractError):
        recipe.materialize(wrong)


def test_failed_or_partial_trace_cannot_become_verified_recipe():
    current, plan, validation, _ = make_recipe()
    for key in ("full_completed", "source_unchanged"):
        with pytest.raises(PlanContractError):
            verified_recipe(source_id="failed", task=current, plan=plan, validation=validation | {key: False})


def test_retrieval_uses_current_failure_stage_and_excludes_same_family():
    sources = [dict(source_id="s1", family="other", build_system="cmake", observed_validation={}, retrieval_text="", commands=[])]
    entries = [dict(source_id="s1", stage="configure", conditions=["生成器不匹配"], state="build.ninja missing", action="检查CMAKE_GENERATOR", not_applicable=["真实编译失败"])]
    bank = StateTargetBank(sources, entries)
    args = dict(build_system="cmake", family="target", stage="configure", mode="structured", text=json.dumps(dict(task={}, handoff=dict(output="build.ninja missing"))))
    before = copy.deepcopy(entries)
    assert bank.retrieve(**args)["sources"] == ["s1"]
    assert not bank.retrieve(**(args | dict(stage="build")))["items"]
    assert not bank.retrieve(**(args | dict(family="other")))["items"]
    assert not bank.retrieve(**(args | dict(text='{"task":{},"handoff":{}}')))["items"]
    assert entries == before
