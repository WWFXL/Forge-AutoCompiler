"""新入口必须真正使用新诊断门禁，并给依赖/重放足够资源。"""

import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_libverto_natural_recovery_v2 import ADMISSION_RESERVE_SECONDS, RUNTIME_LIMITS, NoProviderMeter, planner_for  # noqa: E402

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_workflow import BuildPlan, PlanContractError


def test_new_entry_rejects_dependency_failure_before_reading_logs():
    protocol = json.loads((Path(__file__).resolve().parents[2] / "benchmarks/analyses/cpp-build-libverto-natural-recovery-v1.json").read_text())
    plan = BuildPlan.model_validate(protocol["initial_plan"])
    source = Mock()
    handoff = {"plan_sha256": plan.fingerprint(), "reason": "step_failed_or_expectation_missing", "step_id": "dep"}
    with pytest.raises(PlanContractError, match="非固定测试"):
        planner_for(protocol["initial_plan"])(current_plan=plan, handoff=handoff, source_root=source)
    assert source.mock_calls == []


def test_meter_uses_frozen_resources_and_forbids_model_calls(tmp_path):
    meter = NoProviderMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("scripted-gate",), deadline="2026-10-20T03:30:00Z", packet=lambda: {})
    for key, value in RUNTIME_LIMITS.items():
        assert getattr(meter.tracker.limits, key) == value
    assert meter.tracker.limits.command_timeout_seconds > 60
    assert ADMISSION_RESERVE_SECONDS >= sum(RUNTIME_LIMITS.values())
    with pytest.raises(PlanContractError, match="禁止模型"):
        meter._before_request()
    assert meter.summary()["model_requests"] == 0
