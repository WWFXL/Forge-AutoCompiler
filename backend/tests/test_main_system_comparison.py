"""新任务方案保存、处理隔离和主表分母的针对性验证。"""

import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from test_simple_build import actions, task

from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.simple_build_experience import verified_simple_recipe
from deerflow.compile.simple_build_task import assemble_simple_plan

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_main_system_comparison as comparison  # noqa: E402


def main_recipe():
    plan = assemble_simple_plan(task(task_version="main-build-v1"), actions())
    validation = dict(
        validation_scope="main_build", layers=dict(main_build_task_completed=True, full_completed=None, delivery="passed", clean_replay="passed", author_tests="not_required"), source_unchanged=True, cleanup=dict(succeeded=True)
    )
    return verified_simple_recipe(source_id="confirmed-main", plan=plan, validation=validation)


def test_main_recipe_requires_actual_main_scope_and_replay():
    recipe = main_recipe()
    assert recipe.match(recipe.task)
    assert not recipe.match(recipe.task.model_copy(update=dict(task_version="simple-build-v1")))
    for change in (
        dict(validation_scope="author_tests"),
        dict(source_unchanged=False),
        dict(layers=recipe.observed_validation["layers"] | dict(clean_replay="failed")),
        dict(layers=recipe.observed_validation["layers"] | dict(main_build_task_completed=False)),
    ):
        with pytest.raises(PlanContractError):
            verified_simple_recipe(source_id="bad", plan=recipe.materialize(recipe.task), validation=recipe.observed_validation | change)
    # 旧完整成功标签不能代替新任务实际观察。
    with pytest.raises(PlanContractError):
        verified_simple_recipe(source_id="old-label", plan=recipe.materialize(recipe.task), validation=dict(layers=dict(full_completed=True, clean_replay="passed"), source_unchanged=True, cleanup=dict(succeeded=True)))


def test_54_schedule_balances_method_order_and_preserves_pairs():
    rows = comparison.schedule()
    assert len(rows) == 54
    counts = Counter()
    for i in range(0, 54, 3):
        counts.update((r["method"], j) for j, r in enumerate(rows[i : i + 3]))
    assert set(counts.values()) == {6}
    for project in comparison.PROJECTS:
        orders = [[r["method"] for r in rows if r["project"] == project and r["repetition"] == rep] for rep in (1, 2)]
        assert orders[0] == orders[1][::-1]


def test_dispatch_scope_router_and_experience_are_separate(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "offline-placeholder")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    model, bank, recipe = object(), object(), main_recipe()
    monkeypatch.setattr(comparison, "PlanThinkingDeepSeek", lambda **kw: model)
    monkeypatch.setattr(comparison.SimpleStateTargetBank, "load", lambda _: bank)
    monkeypatch.setattr(comparison, "load_recipes", lambda _: (recipe,))
    calls = []

    def run(**kw):
        calls.append(kw)
        kw["output_root"].mkdir()
        return dict(status="completed")

    monkeypatch.setattr(comparison.shared, "run_simple_system", run)
    runner = comparison.paid_executor(dict(experience=dict(path="unused")))
    item = dict(
        task=recipe.task.model_dump(mode="json"),
        reference=dict(task_sha256="a" * 64, components=[dict(name="lib", artifact_names=["lib.a"], kinds=["static_library"], evidence="original")]),
        source_archive="unused",
        family="test",
        stratum="exact_reuse",
    )
    for i, method in enumerate(comparison.METHODS):
        runner(slot=dict(method=method), item=item, folder=tmp_path / str(i), available=Decimal("0.5"), deadline=(datetime.now(UTC) + timedelta(hours=1)).isoformat())
    assert all(c["validation_scope"] == "main_build" and c["model"] is model for c in calls)
    assert calls[0]["recipe"] is None and calls[0]["bank"] is None
    assert calls[1]["recipe"] is recipe and calls[1]["bank"] is bank
    assert calls[2]["recipe"] is None and calls[2]["bank"] is None
    assert calls[0]["state_router"].method == calls[1]["state_router"].method == "rule"
    assert calls[2]["state_router"] is None


def test_analysis_uses_new_task_and_keeps_unobserved_denominator(tmp_path):
    fixture = dict(
        projects=[dict(name=n, stratum="exact_reuse" if n in comparison.REUSE_PROJECTS else "no_recipe") for n in comparison.PROJECTS],
        schedule=comparison.schedule(),
        experience=dict(historical_preparation_cost_usd="0.1"),
        recipes={},
        boundary="开发比较",
    )
    comparison.save(tmp_path / "protocol.json", fixture)
    slot = fixture["schedule"][0]
    row = slot | dict(
        layers=dict(main_build_task_completed=True, primary_build_completed=True, full_completed=None, author_tests="not_required", delivery="passed", clean_replay="passed"),
        agent_usage=dict(model_requests=2, estimated_cost_usd_completed_responses="0.02", unknown_usage_requests=0),
        arm_total_wall_seconds=5,
    )
    comparison.save(tmp_path / "result.json", dict(rows=[row], unobserved=fixture["schedule"][1:]))
    result = comparison.analyze(tmp_path)
    assert result["summary"]["all"]["forge"]["planned"] == 18
    assert result["summary"]["all"]["forge"]["main_task_completed"] == 1
    assert result["summary"]["exact_reuse"]["forge"]["planned"] == 6
    assert result["summary"]["no_recipe"]["forge"]["planned"] == 12
    assert len(result["unobserved"]) == 53
    assert result["slots"][0]["main_task_completed"] is True
