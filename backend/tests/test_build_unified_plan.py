"""新入口的脚本模型与调度、拒绝边界。"""

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_unified_plan as runner

from deerflow.compile.plan_workflow import PlanContractError


def test_gate_schedule_preserves_two_sources_three_systems_and_recovery():
    rows = runner.gate_schedule()
    assert len(rows) == 9
    assert {(s["project"], s["method"]) for s in rows if s["case"] == "normal"} == {(p, m) for p in ("buffer", "uncrustify", "libverto") for m in runner.METHODS[:2]}
    assert sum(s["case"] == "controlled_build_recovery" for s in rows) == 2


def test_slot_dispatches_same_meter_and_no_reference_to_real_planners(tmp_path):
    for method in runner.METHODS[:2]:
        executor = Mock(return_value={"strict_completed": False})
        runner.slot_runner(protocol={}, root=tmp_path, slot={"method": method}, item={}, model="authorized-model", reference={"must_not_leak": True}, executor=executor)
        args = executor.call_args.kwargs
        assert args["reference"] is None and args["meter_factory"] is runner.StrategyMeter
        assert args["model"] == "authorized-model" and args["arm"] == "plan"
        assert args["command_timeout_seconds"] == 600 and args["replay_timeout_seconds"] == 900


def test_controlled_failure_preserves_prefix_and_restores_build_only():
    actions = runner.core({"steps": [{"step_id": "build", "role": "build", "command": "make -j2", "source": "Makefile", "expected": "成功"}]})
    bad, good = runner.bad_actions(actions), runner.recovered_actions(actions)
    assert bad.steps[0] == good.steps[0]
    assert bad.steps[-1].command == "false" and good.steps[-1].command == "make -j2"


def test_invalid_new_authorization_rejected_without_credentials():
    with pytest.raises(PlanContractError, match="新明确授权"):
        runner.validate_authorization({"candidate_sha256": "new"}, {"experiment_identity": "old", "user_authorized": True})


def test_gate_model_is_local_and_explicitly_zero_usage():
    model = runner.gate_model([runner.core({"steps": [{"step_id": "build", "role": "build", "command": "make", "source": "Makefile", "expected": "成功"}]})])
    response = model.invoke("gate")
    assert response.response_metadata["model_name"] == "scripted-gate"
    assert response.usage_metadata["total_tokens"] == 0
