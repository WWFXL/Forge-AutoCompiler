"""固定方案的真实分派差异与费用口径；不读取凭据、不调用Provider。"""

import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_fixed_plan_state_increment as fixed  # noqa: E402

from deerflow.compile.goal_state import GoalStateWorkflow  # noqa: E402
from deerflow.compile.plan_agent import PlanAgentLedger  # noqa: E402
from deerflow.compile.source_preparation import PreparedWorkflow  # noqa: E402


def test_selection_is_first_per_project_and_configuration_class_without_future_success():
    selection = fixed.base.load(fixed.SELECTION)
    assert len(selection["all_candidates"]) == 18
    assert [(c["project"], c["slot"]) for c in selection["cases"]] == [("simdutf", 1), ("simdutf", 2), ("snappy", 13), ("snappy", 4), ("yaml-cpp", 7)]
    for case in selection["cases"]:
        matches = [r for r in selection["all_candidates"] if (r["project"], r["configuration_class"]) == (case["project"], case["configuration_class"])]
        assert case["slot"] == min(r["slot"] for r in matches)
        original = fixed.SOURCE_ROOT / case["original_plan_path"]
        assert fixed.base.digest(fixed.ROOT / case["plan_path"]) == case["plan_sha256"]
        if original.exists():
            assert original.read_bytes() == (fixed.ROOT / case["plan_path"]).read_bytes()
    row = dict(strict_completed=False, transitions=[dict(status="needs_handoff", handoff=dict(step_id="check", recent_commands=[dict(output_tail="AssertionError: 配置功能不符:TESTS=OFF")]))])
    assert fixed.prior_configuration_class(row) == "deviated"
    row["strict_completed"] = True
    assert fixed.prior_configuration_class(row) == "deviated"


def test_schedule_keeps_identical_case_across_all_three_arms_and_repetitions():
    candidate = fixed.candidate_for()
    rows = candidate["schedule"]
    assert len(rows) == len({(r["case_id"], r["repetition"], r["method"]) for r in rows}) == 30
    assert Counter(r["method"] for r in rows) == dict.fromkeys(fixed.METHODS, 10)
    for case in candidate["cases"]:
        for repetition in (1, 2):
            assert {r["method"] for r in rows if r["case_id"] == case["case_id"] and r["repetition"] == repetition} == set(fixed.METHODS)


@pytest.mark.parametrize("index,workflow", [(0, PreparedWorkflow), (1, GoalStateWorkflow), (2, GoalStateWorkflow)])
def test_run_slot_bypasses_initial_model_and_uses_same_goal_material_and_harness(tmp_path, monkeypatch, index, workflow):
    candidate = fixed.candidate_for()
    case = candidate["cases"][0]
    task = fixed.base.PlanTask.model_validate(candidate["projects"][0]["task"])
    captured = {}

    def run(**kwargs):
        captured["workflow"] = fixed.base.prepared_module.PreparedWorkflow
        planner = fixed.base.observed_module.observed_planner("model")
        meter = SimpleNamespace(ledger=PlanAgentLedger(tmp_path / "ledger"))
        plan, _ = planner(task=task, meter=meter)
        captured["plan"] = plan
        return dict(strict_completed=False, agent_usage=dict(estimated_cost_usd_completed_responses="0.01"))

    monkeypatch.setattr(fixed.paired.replication, "run_slot", run)
    row = fixed.run_slot(protocol=candidate, slot=dict(project=case["project"], case_id=case["case_id"], repetition=1, method=fixed.METHODS[index]), root=tmp_path, model="unused-initial-model")
    assert captured["workflow"] is workflow
    assert captured["plan"].fingerprint() == case["plan_fingerprint"]
    assert not row["historical_initial_cost_is_new_spending"]
    assert fixed.Decimal(row["comparable_total_estimated_cost_usd"]) == fixed.Decimal(case["historical_initial_planning"]["estimated_cost_usd"]) + fixed.Decimal("0.01")


@pytest.mark.parametrize("direct", [False, True])
def test_direct_action_is_only_available_to_declared_arm(tmp_path, monkeypatch, direct):
    candidate = fixed.candidate_for()
    initial = fixed.checked_plan(candidate["cases"][0], fixed.base.PlanTask.model_validate(candidate["projects"][0]["task"]))
    revised = Mock(revision=2, model_dump=Mock(return_value=dict(revision=2)))
    current = Mock(fingerprint=Mock(return_value="same-plan"))
    original = Mock(return_value=(revised, "共同Agent恢复"))
    decision = Mock(return_value=(revised, "有界动作"))
    monkeypatch.setattr("deerflow.compile.goal_state.direct_configuration_revision", decision)
    meter = SimpleNamespace(ledger=PlanAgentLedger(tmp_path / "agent"))
    planner = fixed.fixed_planner(initial, original, direct=direct)
    assert planner(meter=meter, task="task", source_root=tmp_path)[0] is initial
    args = dict(meter=meter, task="task", source_root=tmp_path, current_plan=current, handoff=dict(plan_sha256="same-plan", configuration_state={}))
    assert planner(**args)[0] is revised
    assert decision.call_count == int(direct)
    assert original.call_count == int(not direct)


def test_free_check_stops_at_recovery_instead_of_silently_using_a_provider(tmp_path):
    meter = SimpleNamespace(ledger=PlanAgentLedger(tmp_path / "agent"))
    original = Mock()
    planner = fixed.fixed_planner(Mock(), original, direct=False, forbid_provider=True)
    with pytest.raises(fixed.base.PlanContractError, match="development_only_stop_before_provider"):
        planner(meter=meter, current_plan=Mock(), handoff=dict(reason="configuration_goal_violated"))
    original.assert_not_called()
    events = [json.loads(line) for line in (tmp_path / "agent/events.jsonl").read_text().splitlines()]
    assert events[-1]["event"] == "development.provider_forbidden"


def test_historical_usage_stops_at_first_recovery_and_is_not_zeroed():
    events = [
        dict(event="agent.started", recovery=False),
        dict(event="model.request_completed", input_tokens=100, output_tokens=20),
        dict(event="agent.started", recovery=True),
        dict(event="model.request_completed", input_tokens=9000, output_tokens=800),
    ]
    session = dict(commands=[dict(completed_at="2026-10-28T00:00:00+00:00"), dict(started_at="2026-10-28T00:00:03+00:00")])
    usage = fixed.historical_planning(events, session)
    assert usage["recorded_tokens"] == 120 and usage["model_requests"] == 1
    assert usage["estimated_cost_usd"] == "0.000054" and usage["historical_planning_boundary_seconds"] == 3


@pytest.mark.parametrize("has_handoff,empty_transitions", [(True, False), (False, False), (False, True)])
def test_analysis_uses_full_completed_prefix_and_does_not_invent_a_normal_handoff(tmp_path, has_handoff, empty_transitions):
    folder = tmp_path / "slot-1/sample-plan"
    session = folder / ".compile-sessions/thread/session/session.json"
    session.parent.mkdir(parents=True)
    commands = [dict(role="build", command_id=name, duration_seconds=seconds) for name, seconds in [("older-build", 9), ("failed-build", 2), ("later-build", 4)]]
    fixed.base.write_json(session, dict(commands=commands))
    (folder / "agent").mkdir()
    (folder / "agent/events.jsonl").write_text("")
    handoff = dict(reason="failure", step_id="build", recent_commands=[commands[1]]) if has_handoff else None
    row = dict(
        case_id="sample",
        repetition=1,
        method=fixed.METHODS[0],
        strict_completed=False,
        initial_plan_sha256="fixed-plan",
        cleanup=dict(succeeded=True),
        transitions=[] if empty_transitions else [dict(completed={"old": "older-build"}, handoff=handoff)],
        agent_usage=dict(model_requests=0, unknown_usage_requests=0, estimated_cost_usd_completed_responses="0"),
        comparable_total_estimated_cost_usd="0.01",
        arm_total_wall_seconds=20,
    )
    fixed.base.write_json(tmp_path / "result.json", dict(identity="test-analysis", rows=[row], unobserved_schedule=[], stop_reason=None))
    detail = fixed.analyze(tmp_path)["details"][0]
    assert detail["build_seconds"] == 15
    assert detail["build_seconds_before_first_handoff"] == (11 if has_handoff else None)
