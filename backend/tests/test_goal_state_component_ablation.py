"""共同修复及三个组件臂的接线；不创建正式尝试、不调用Provider。"""

import sys
from collections import Counter
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_goal_state_ablation as ablation  # noqa: E402

from deerflow.compile.goal_state import GoalStateWorkflow
from deerflow.compile.plan_candidate_reception import propose_received
from deerflow.compile.source_preparation import PreparedWorkflow


def test_schedule_separates_three_components_on_original_cmake_scope():
    rows = ablation.schedule()
    assert len(rows) == len({(r["project"], r["repetition"], r["method"]) for r in rows}) == 18
    for name in ablation.PROJECTS:
        for repetition in (1, 2):
            assert {r["method"] for r in rows if r["project"] == name and r["repetition"] == repetition} == set(ablation.METHODS)
    for position in range(3):
        assert Counter(rows[i]["method"] for i in range(position, 18, 3)) == dict.fromkeys(ablation.METHODS, 2)


@pytest.mark.parametrize("index,workflow", [(0, PreparedWorkflow), (1, PreparedWorkflow), (2, GoalStateWorkflow)])
def test_all_arms_use_common_candidate_reception_with_only_declared_component_difference(tmp_path, monkeypatch, index, workflow):
    captured = {}

    def execute(**kwargs):
        captured.update(kwargs)
        captured["workflow"] = ablation.base.prepared_module.PreparedWorkflow
        captured["planner"] = ablation.base.observed_module.observed_planner("model")
        captured["meter_factory"] = ablation.base.PreparationMeter
        return dict(strict_completed=False)

    original = ablation.base.observed_module.observed_planner
    factory = Mock(return_value=Mock(return_value="original-planner"))
    monkeypatch.setattr(ablation.paired.replication, "run_slot", execute)
    # 不替换运行中的observed_planner，只在其返回的闭包上检查新agent确已注入。
    import deerflow.compile.unified_plan_equivalent_observed as observed

    monkeypatch.setattr(observed, "unified_planner", factory)
    spec = ablation.base.load(ablation.ROOT / ablation.PARENT)
    result = ablation.run_slot(protocol=spec, slot=dict(project="simdutf", repetition=1, method=ablation.METHODS[index]), root=tmp_path, model="same-model")
    assert captured["workflow"] is workflow
    assert captured["slot"]["method"] == "model_plan_workflow"
    assert result["persistent_goals"] == (index > 0) and result["configuration_observation"] == (index == 2)
    assert factory.call_args.kwargs["agent"] is propose_received
    assert ablation.base.observed_module.observed_planner is original
