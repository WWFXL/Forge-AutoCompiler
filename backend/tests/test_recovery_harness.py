"""恢复指导实际进入Agent请求，初始规划和执行要求保持；无Provider。"""

import json
import sys
from pathlib import Path

import pytest
from test_plan_agent import ScriptedPlanModel, response
from test_simple_build import actions, runner, simple_actions, task, workflow  # noqa: F401

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_workflow import PlanContractError, _digest
from deerflow.compile.recovery_harness import RecoveryHarness, RecoveryHarnessProposal
from deerflow.compile.simple_build_agents import SimpleBuildMeter
from deerflow.compile.simple_build_task import SIMPLE_PROMPT, assemble_simple_plan, propose_simple

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_recovery_harness_proposal as offline  # noqa: E402


def candidate():
    return RecoveryHarness(name="H_R_test", base_prompt_sha256=_digest(SIMPLE_PROMPT), recovery_guidance="先使用当前失败交接，只补读影响修订的缺失信息。")


def test_candidate_requires_actual_evidence_and_supports_no_change():
    base = RecoveryHarness(name="H0_recovery", base_prompt_sha256=_digest(SIMPLE_PROMPT))
    proposal = RecoveryHarnessProposal(no_change=False, recovery_guidance=candidate().recovery_guidance, diagnoses=[dict(evidence_ids=["actual:1"], problem="重复读取", proposed_change="定点补读", expected_behavior="减少探索")])
    with pytest.raises(PlanContractError, match="不存在"):
        proposal.materialize(base, dict(episodes=[]))
    result = proposal.materialize(base, dict(episodes=[dict(evidence=[dict(evidence_id="actual:1")])]))
    assert result.training_corpus_sha256
    assert RecoveryHarnessProposal(no_change=True).materialize(base, dict(episodes=[])) == base
    with pytest.raises(PlanContractError, match="底座"):
        result.prompt("different base")


@pytest.mark.parametrize("recovery", [False, True])
def test_actual_agent_request_keeps_initial_prompt_unchanged(tmp_path, recovery):
    meter = SimpleBuildMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline="2099-01-01T00:00:00+00:00", packet=lambda: {})
    plan = assemble_simple_plan(task(), simple_actions("make missing")) if recovery else None
    handoff = dict(plan_sha256=plan.fingerprint(), handoff_id="actual-failure", reason="make: missing target") if plan else None
    propose_simple(
        model=ScriptedPlanModel(responses=[response("SimpleBuildActions", simple_actions().model_dump(mode="json"))]),
        task=task(),
        source_root=tmp_path,
        session_root=tmp_path,
        meter=meter,
        current_plan=plan,
        handoff=handoff,
        recovery_harness=candidate(),
    )
    actual = json.loads((tmp_path / "agent/request-1.json").read_text())
    system = actual["system_message"]["content"]
    assert (candidate().recovery_guidance in system) == recovery
    if not recovery:
        assert system == SIMPLE_PROMPT
    assert meter.summary()["model_requests"] == 1


def test_real_failed_build_returns_through_agent_and_workflow(runner, tmp_path):  # noqa: F811
    w = workflow(runner, actions("make missing-target"))
    assert w.run()["status"] == "needs_handoff"
    meter = SimpleBuildMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline="2099-01-01T00:00:00+00:00", packet=lambda: {})
    revised, reason = propose_simple(
        model=ScriptedPlanModel(responses=[response("SimpleBuildActions", simple_actions().model_dump(mode="json"))]),
        task=w.plan.task,
        source_root=w.root,
        session_root=tmp_path,
        meter=meter,
        current_plan=w.plan,
        handoff=w.handoff,
        recovery_harness=candidate(),
        revision_validator=w.validate_revision,
    )
    w.apply_revision(handoff_id=w.handoff["handoff_id"], plan=revised, reason=reason)
    assert w.run()["status"] == "primary_completed"
    assert w.layers["primary_build_completed"]
    assert (w.root / "libsample.a").is_file()


@pytest.mark.parametrize("known_usage", [True, False])
def test_invalid_paid_response_preserves_usage_and_never_retries(tmp_path, known_usage):
    from langchain_core.messages import AIMessage

    class Model:
        calls = 0

        def invoke(self, messages):
            self.calls += 1
            return AIMessage(content="not-json", usage_metadata=dict(input_tokens=100, output_tokens=2, total_tokens=102) if known_usage else None, response_metadata=dict(model_name="gpt-5.6"))

    request = tmp_path / "request.json"
    request.write_text(json.dumps(dict(system_prompt="test", packet={})))
    (tmp_path / "scope.json").write_text(
        json.dumps(dict(identity=offline.IDENTITY, request_sha256=offline.digest(request), deadline="2099-01-01T00:00:00+00:00", components={}, requested_model="gpt-6-astra", accepted_response_models=["gpt-5.6"], maximum_cost_usd="1.00"))
    )
    model = Model()
    with pytest.raises(ValueError):
        offline.generate(tmp_path, model)
    assert model.calls == 1 and (tmp_path / "response.json").exists()
    assert json.loads((tmp_path / "failure.json").read_text())["unknown_usage"] != known_usage
    assert (tmp_path / "usage.json").exists() == known_usage
    with pytest.raises(FileExistsError):
        offline.generate(tmp_path, model)
    assert model.calls == 1
