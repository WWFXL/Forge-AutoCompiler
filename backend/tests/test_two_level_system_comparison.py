"""只检查新装配的精确身份、处理隔离、分层分母与费用归因。"""

import json
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from test_simple_build import actions, task

from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.simple_build_experience import select_simple_recipe, verified_simple_recipe
from deerflow.compile.simple_build_task import assemble_simple_plan

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_two_level_system_comparison as comparison  # noqa: E402


def recipe():
    t = task()
    return verified_simple_recipe(source_id="verified-source", plan=assemble_simple_plan(t, actions()), validation=dict(layers=dict(full_completed=True, clean_replay="passed"), source_unchanged=True, cleanup=dict(succeeded=True)))


def test_exact_lookup_uses_public_identity_and_rejects_ambiguous_sources():
    r = recipe()
    assert select_simple_recipe(recipes=[r], task=r.task.model_copy(update={"plan_id": "different-label"})) is r
    assert select_simple_recipe(recipes=[r], task=task(parallel_jobs=1)) is None
    assert select_simple_recipe(recipes=[], task=task()) is None
    with pytest.raises(PlanContractError, match="多个相同任务身份"):
        select_simple_recipe(recipes=[r, r.model_copy(update=dict(source_id="second"))], task=task())


def test_schedule_balances_positions_predecessors_and_reverses_each_pair():
    slots = comparison.schedule()
    positions, predecessors = Counter(), Counter()
    assert len(slots) == 36
    assert set(Counter((s["project"], s["repetition"]) for s in slots).values()) == {3}
    for i in range(0, len(slots), 3):
        group = slots[i : i + 3]
        positions.update((s["method"], j) for j, s in enumerate(group))
        predecessors.update((a["method"], b["method"]) for a, b in zip(group, group[1:]))
    assert set(positions.values()) == {4}
    assert len(predecessors) == 6 and set(predecessors.values()) == {4}
    for name in comparison.PROJECTS:
        first = [s["method"] for s in slots if s["project"] == name and s["repetition"] == 1]
        second = [s["method"] for s in slots if s["project"] == name and s["repetition"] == 2]
        assert first == second[::-1]


def test_joint_dispatch_passes_both_layers_only_to_experience_and_miss_keeps_bank(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "offline-placeholder")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    model, bank, r = object(), object(), recipe()
    monkeypatch.setattr(comparison, "PlanThinkingDeepSeek", lambda **kw: model)
    monkeypatch.setattr(comparison.SimpleStateTargetBank, "load", lambda _: bank)
    monkeypatch.setattr(comparison, "load_recipes", lambda _: (r,))
    calls = []

    def execute(**kw):
        calls.append(kw)
        kw["output_root"].mkdir()
        return dict(status="completed")

    monkeypatch.setattr(comparison.shared, "run_simple_system", execute)
    item = comparison.shared.load(comparison.shared.FIXTURE)["projects"][0]
    item = item | dict(task=task().model_dump(mode="json"), stratum="exact_reuse")
    runner = comparison.paid_executor(dict(experience=dict(path="unused")))
    for i, method in enumerate((*comparison.METHODS, "forge_experience")):
        current = item if i < 3 else item | dict(task=task(parallel_jobs=1).model_dump(mode="json"), stratum="no_recipe")
        runner(slot=dict(method=method), item=current, folder=tmp_path / str(i), available=Decimal("0.75"), deadline=(datetime.now(UTC) + timedelta(hours=1)).isoformat())
    assert all(c["model"] is model and c["maximum_cost_usd"] == "0.40" for c in calls)
    assert calls[0]["bank"] is None and calls[0]["recipe"] is None
    assert calls[1]["bank"] is bank and calls[1]["recipe"] is r
    assert calls[2]["bank"] is None and calls[2]["recipe"] is None
    assert calls[3]["bank"] is bank and calls[3]["recipe"] is None


def test_analysis_keeps_unobserved_denominator_and_actual_recovery_cost(tmp_path):
    projects = comparison.PROJECTS
    protocol = dict(
        projects=[dict(name=n, stratum="exact_reuse" if n in comparison.REUSE_PROJECTS else "no_recipe") for n in projects],
        schedule=comparison.schedule(),
        experience=dict(historical_preparation_cost_usd="0.1"),
        recipes={},
        boundary="本样本分层",
    )
    comparison.save(tmp_path / "protocol.json", protocol)
    first = protocol["schedule"][0]
    row = first | dict(
        agent_usage=dict(model_requests=2, estimated_cost_usd_completed_responses="0.02", unknown_usage_requests=0),
        layers=dict(primary_build_completed=False, full_completed=False),
        timings=dict(recovery_agent_seconds=2),
        arm_total_wall_seconds=4,
    )
    comparison.save(tmp_path / "result.json", dict(rows=[row], unobserved=protocol["schedule"][1:]))
    agent = tmp_path / f"slot-01-{first['project']}-{first['method']}" / "agent"
    agent.mkdir(parents=True)
    events = [dict(event="agent.started", recovery=False), dict(event="model.cost_estimated", cost_usd="0.01"), dict(event="agent.started", recovery=True), dict(event="model.cost_estimated", cost_usd="0.01")]
    (agent / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    result = comparison.analyze(tmp_path)
    assert result["summary"]["all"]["forge"]["planned"] == 12
    assert result["summary"]["all"]["forge"]["observed"] == 1
    assert result["summary"]["all"]["forge"]["estimated_cost_usd"] == "0.02"
    assert result["summary"]["exact_reuse"]["forge"]["planned"] == 6
    assert result["summary"]["no_recipe"]["forge"]["observed"] == 0
    assert result["slots"][0]["phase_usage"]["recovery"] == dict(requests=1, estimated_cost_usd="0.01")
    assert len(result["unobserved"]) == 35
