"""已审核P5接入、恢复隔离与真实Agent图提示送达；不连接Provider。"""

import json
import sys
from pathlib import Path

import pytest
from test_plan_agent import ScriptedPlanModel, response
from test_simple_build import simple_actions, task

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.simple_build_agents import SimpleBuildMeter
from deerflow.compile.simple_build_task import SIMPLE_PROMPT, propose_simple

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_planning_evidence_order_observation as observation  # noqa: E402


def test_current_harness_is_preserved_except_initial_planning(tmp_path, monkeypatch):
    module = observation.runtime()
    calls = []
    monkeypatch.setattr(module.shared, "run_simple_system", lambda **kw: calls.append(kw) or {})
    item = module.shared.load(module.FIXTURE)["projects"][0]
    model = object()
    for execute in (module.executor(model), __import__("forge_harness_update_comparison").executor(model)):
        execute(slot=dict(method="LH_v1"), item=item, folder=tmp_path, available=1, deadline="2099-01-01T00:00:00+00:00")
    new, old = calls
    assert new["harness"].fingerprint() == observation.P5_SHA
    assert old["harness"].name == "P0"
    for key in new.keys() - {"harness", "deadline", "state_router"}:
        assert new[key] == old[key], key
    assert new["harness"].prompt(SIMPLE_PROMPT, recovery=True) == SIMPLE_PROMPT
    assert new["recovery_harness"] == old["recovery_harness"]


def test_real_planning_graph_receives_reviewed_candidate(tmp_path):
    harness = observation.planning_harness()
    ledger = PlanAgentLedger(tmp_path / "agent")
    meter = SimpleBuildMeter(ledger, accepted_models=("test-model",), deadline="2099-01-01T00:00:00+00:00", packet=lambda: {})
    plan, _ = propose_simple(model=ScriptedPlanModel(responses=[response("SimpleBuildActions", simple_actions().model_dump(mode="json"))]), task=task(), source_root=tmp_path, session_root=tmp_path, meter=meter, harness=harness)
    request = json.loads((tmp_path / "agent/request-1.json").read_text())
    assert harness.planning_guidance in request["system_message"]["content"]
    assert plan.steps[-1].role == "build"
    assert meter.summary()["model_requests"] == 1


def test_candidate_is_reviewed_and_denominator_is_three():
    value = observation.candidate()
    observation.validate(value, check_sources=False)
    assert [p["task"]["build_system"] for p in value["projects"]] == ["cmake", "make", "autotools"]
    assert len(value["schedule"]) == 3
    assert value["recipe_reuse"] is False and value["experience_bank"] is None
    assert value["planning_harness"]["name"] == "P5_evidence_order"
    assert list(value["recovery_harnesses"]) == ["LH_v1"]


def test_changed_candidate_is_not_silently_accepted(tmp_path, monkeypatch):
    changed = observation.planning_harness().model_copy(update=dict(planning_guidance="different"))
    path = tmp_path / "candidate.json"
    path.write_text(changed.model_dump_json())
    monkeypatch.setattr(observation, "P5", path)
    with pytest.raises(PlanContractError, match="审核P5"):
        observation.planning_harness()


def test_missing_new_authorization_stops_before_provider(tmp_path, monkeypatch):
    module = observation.runtime()
    path = tmp_path / "manifest.json"
    module.save(path, observation.candidate())
    monkeypatch.setattr(observation, "MANIFEST", path)
    monkeypatch.setattr(observation, "validate", lambda value: None)
    monkeypatch.setattr(sys, "argv", ["observation", "--run"])
    with pytest.raises(PlanContractError, match="新授权"):
        observation.main()


def test_unstarted_slots_stay_unobserved(tmp_path):
    module = observation.runtime()
    module.save(tmp_path / "result.json", dict(rows=[], unobserved=observation.candidate()["schedule"], unclosed_slot=None, billing_complete=True, closed_slot_cost_usd="0"))
    value = observation.analyze(tmp_path)
    assert value["arms"]["LH_v1"]["planned"] == value["arms"]["LH_v1"]["unobserved"] == 3
    assert value["arms"]["LH_v1"]["main_build_completed"] == 0
