"""共同暂存器必须同时进入初始装配与权威恢复合同。"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from test_plan_agent import ScriptedPlanModel, response
from test_tool_plan import task

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_agent_context import ContextCanaryMeter
from deerflow.compile.plan_delivery_equivalent import equivalent_delivery_command
from deerflow.compile.plan_workflow import BuildPlan, PlanContractError
from deerflow.compile.source_preparation import with_preparation
from deerflow.compile.unified_plan import BuildActions as OldActions
from deerflow.compile.unified_plan import assemble_plan as old_assemble
from deerflow.compile.unified_plan_equivalent import BuildActions, assemble_plan, validate_recovery
from deerflow.compile.unified_plan_equivalent_observed import ObservedBuildActions, observed_planner


def actions():
    return BuildActions(reason="受控源码依据", steps=[{"step_id": "build", "role": "build", "command": "false", "source": "Makefile", "expected": "执行"}])


@pytest.mark.parametrize("source", ["tool", "model"])
def test_prepared_plan_recovery_real_graph_uses_identical_staging(tmp_path, source):
    t = task()
    current = with_preparation(assemble_plan(t, actions(), revision=1), "1" * 64)
    handoff = {"handoff_id": "actual", "plan_sha256": current.fingerprint()}
    validate_recovery(t, current, handoff)
    good = ObservedBuildActions(reason="恢复真实失败", steps=[{"step_id": "build", "role": "build", "command": "make -j2", "source": "Makefile", "expected": "编译"}])
    model = ScriptedPlanModel(responses=[response("ObservedBuildActions", good.model_dump(mode="json"))])
    meter = ContextCanaryMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat(), packet=lambda: {"task": t.model_dump(mode="json"), "source_packet": []})
    plan, _ = observed_planner(source)(model=model, task=t, source_root=tmp_path, session_root=tmp_path, meter=meter, current_plan=current, handoff=handoff)
    revised = with_preparation(plan, "1" * 64)
    assert revised.revision == 2 and revised.steps[0] == current.steps[0]
    assert revised.steps[-1] == current.steps[-1]
    assert revised.steps[-1].command == equivalent_delivery_command(t.artifact_paths)
    assert [s for s in revised.steps if s.role == "smoke"] == list(t.verification_steps)
    assert meter.summary()["model_requests"] == 1
    assert json.loads((tmp_path / "agent/plan-2.json").read_text())["steps"][-1]["command"] == revised.steps[-1].command


def test_old_or_modified_staging_cannot_enter_new_recovery():
    t = task()
    old = old_assemble(t, OldActions.model_validate(actions().model_dump()), revision=1)
    with pytest.raises(PlanContractError, match="固定装配"):
        validate_recovery(t, old, {"handoff_id": "old", "plan_sha256": old.fingerprint()})
    current = assemble_plan(t, actions(), revision=1)
    value = current.model_dump()
    value["steps"][-1]["command"] = "true"
    bad = BuildPlan.model_validate(value)
    with pytest.raises(PlanContractError, match="固定装配"):
        validate_recovery(t, bad, {"handoff_id": "tampered", "plan_sha256": bad.fingerprint()})


def test_gate_v3_uses_one_new_assembly_without_posthoc_stage_replacement():
    import forge_build_cxx_common_input_gate_v3 as gate

    assert gate.IDENTITY == "cpp-build-cxx-common-input-gate-v3"
    assert len(gate.schedule()) == 11
    assert gate.observed_planner is observed_planner
