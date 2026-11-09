"""离线更新真实改变提示、保持恢复与裁判边界；不调用Provider。"""

import json
import sys
from pathlib import Path

import pytest
from test_plan_agent import ScriptedPlanModel, response
from test_simple_build import simple_actions, task

from deerflow.compile.offline_harness import HarnessProposal, PlanningHarness
from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_workflow import PlanContractError, _digest
from deerflow.compile.simple_build_agents import SimpleBuildMeter
from deerflow.compile.simple_build_task import SIMPLE_PROMPT, propose_simple

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_offline_harness as offline  # noqa: E402


def baseline():
    return PlanningHarness(name="H0", base_prompt_sha256=_digest(SIMPLE_PROMPT))


def proposal(**changes):
    return HarnessProposal.model_validate(
        dict(diagnoses=[dict(evidence_ids=["actual:1"], problem="重复读取已有证据", proposed_change="围绕当前疑问补读", expected_behavior="有依据时提交")], planning_guidance="先列出当前尚缺的具体信息，再定向补读。", no_change=False)
        | changes
    )


def test_update_binds_evidence_and_changes_only_initial_prompt():
    h0 = baseline()
    h1 = proposal().materialize(h0, dict(episodes=[dict(evidence=[dict(evidence_id="actual:1")])]))
    assert h1.parent_sha256 == h0.fingerprint()
    assert h0.prompt(SIMPLE_PROMPT) == SIMPLE_PROMPT
    assert h1.planning_guidance in h1.prompt(SIMPLE_PROMPT)
    assert h1.prompt(SIMPLE_PROMPT, recovery=True) == SIMPLE_PROMPT
    with pytest.raises(PlanContractError):
        h1.prompt("changed shared base")
    with pytest.raises(PlanContractError):
        proposal().materialize(h0, dict(episodes=[]))


def test_no_change_does_not_manufacture_a_candidate():
    h0 = baseline()
    no_change = HarnessProposal(no_change=True)
    assert no_change.materialize(h0, dict(episodes=[])) == h0
    with pytest.raises(PlanContractError):
        proposal(no_change=True).materialize(h0, dict(episodes=[dict(evidence=[dict(evidence_id="actual:1")])]))


def test_real_agent_graph_receives_fixed_guidance_without_corpus_leak(tmp_path):
    h1 = proposal().materialize(baseline(), dict(episodes=[dict(evidence=[dict(evidence_id="actual:1", private="NEVER_INJECT_CORPUS")])]))
    meter = SimpleBuildMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline="2099-01-01T00:00:00+00:00", packet=lambda: {})
    propose_simple(model=ScriptedPlanModel(responses=[response("SimpleBuildActions", simple_actions().model_dump(mode="json"))]), task=task(), source_root=tmp_path, session_root=tmp_path, meter=meter, harness=h1)
    actual = json.loads((tmp_path / "agent/request-1.json").read_text())
    assert h1.planning_guidance in actual["system_message"]["content"]
    assert "NEVER_INJECT_CORPUS" not in json.dumps(actual)
    assert meter.summary()["model_requests"] == 1


def test_schedule_has_isolated_projects_and_balanced_paired_order():
    slots = offline.schedule()
    assert len(slots) == 24 and not set(offline.TRAIN_PROJECTS) & set(offline.PROJECTS)
    for project in offline.PROJECTS:
        first = [s["method"] for s in slots if s["project"] == project and s["repetition"] == 1]
        second = [s["method"] for s in slots if s["project"] == project and s["repetition"] == 2]
        assert first == second[::-1] and set(first) == {"H0", "H1"}


def test_optimizer_invalid_response_is_preserved_and_not_retried(tmp_path, monkeypatch):
    from langchain_core.messages import AIMessage

    class Model:
        calls = 0

        def invoke(self, messages):
            self.calls += 1
            return AIMessage(content="invalid", usage_metadata=dict(input_tokens=100, output_tokens=2, total_tokens=102), response_metadata=dict(model_name="gpt-5.6"))

    corpus = tmp_path / "corpus.json"
    corpus.write_text(json.dumps(dict(episodes=[])))
    monkeypatch.setattr(offline, "CORPUS", corpus)
    model = Model()
    with pytest.raises(ValueError):
        offline.optimize(dict(baseline=baseline().model_dump(mode="json"), optimizer=dict(accepted_response_models=["gpt-5.6"])), tmp_path / "optimizer", model)
    assert model.calls == 1
    assert (tmp_path / "optimizer/response.json").exists()
    assert json.loads((tmp_path / "optimizer/usage.json").read_text())["estimated_cost_usd_completed_responses"] == "0.000102"
    assert not json.loads((tmp_path / "optimizer/failure.json").read_text())["unknown_usage"]


def test_prepared_corpus_retains_the_repeated_reading_observations():
    corpus = json.loads(offline.CORPUS.read_text())
    episode = next(e for e in corpus["episodes"] if e["trajectory_id"].endswith("comparison-flash-v1:27"))
    assert episode["evidence"][-1]["usage"]["model_requests"] == 50
    assert sum(episode["tool_feedback_counts"].values()) > 1
    assert max(row["count"] for row in episode["read_frequencies"]) > 1
    assert episode["omitted_tool_feedback"] > 0
