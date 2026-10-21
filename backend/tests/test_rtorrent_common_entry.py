"""共同运行资源、初始材料、真实失败接管与材料完整性回归。"""

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_rtorrent_arm as arm  # noqa: E402
import forge_build_rtorrent_common as common  # noqa: E402
import forge_build_rtorrent_common_gate as gate  # noqa: E402
from forge_build_plan_agent_canary import PlanAgentLedger  # noqa: E402

from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402
from deerflow.compile.recovery_text_factors import restore_factor_packet  # noqa: E402
from deerflow.compile.staged_verification import StagedVerificationTask  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def fixture():
    return json.loads((ROOT / "benchmarks/manifests/cpp-build-rtorrent-actual-template-reset-gate-v2.json").read_text())


def test_same_task_material_boundary_and_runtime_for_all_methods(tmp_path):
    spec = fixture()
    captured = []
    original = arm.CompileDockerRuntime

    def executor(**kwargs):
        assert arm.CompileDockerRuntime is common.HostIdentityRuntime
        captured.append(kwargs)
        return {"strict_completed": True}

    for method in common.METHODS:
        common.run_strategy(method=method, item=spec["project"], protocol=spec, root=tmp_path, model="explicit-model", meter_factory=common.CommonQualificationMeter, executor=executor)
        assert arm.CompileDockerRuntime is original
    assert [row["arm"] for row in captured] == ["plan", "plan", "tool"]
    for row in captured:
        assert row["item"] == spec["project"] and row["model"] == "explicit-model"
        assert row["reference"] is None
        assert row["command_timeout_seconds"] == row["replay_timeout_seconds"] == 1200
        assert row["tool_runner"] is common.run_tool_agent_automatic


def test_actual_tool_starts_without_script_and_both_workflows_share_recovery(tmp_path, monkeypatch):
    spec = fixture()
    (tmp_path / "configure.ac").write_text("AC_INIT([sample],[1])")
    planners = []

    def executor(**kwargs):
        planners.append(kwargs["planner"])

    for method in common.METHODS[:2]:
        common.run_strategy(method=method, item=spec["project"], protocol=spec, root=tmp_path, model=None, meter_factory=common.CommonQualificationMeter, executor=executor)
    task = StagedVerificationTask.model_validate(spec["project"]["task"])
    meter = SimpleNamespace(ledger=PlanAgentLedger(tmp_path / "ledger"))
    plan, _ = planners[0](task=task, source_root=tmp_path, meter=meter, model=None)
    assert [s.command for s in plan.steps[:3]] == ["autoreconf -fi", "sh ./configure", "make -j2"]
    assert tuple(s for s in plan.steps if s.role == "smoke") == task.verification_steps
    # 两个闭包绑定的是同一个只读Agent，不把脚本参考偷偷带入初始工具规划。
    import deerflow.compile.unified_plan_equivalent_observed as observed

    assert observed.propose_observed in [cell.cell_contents for cell in planners[0].__closure__]
    assert observed.propose_observed in [cell.cell_contents for cell in planners[1].__closure__]


def test_runtime_is_restored_even_if_executor_fails(tmp_path):
    spec = fixture()
    original = arm.CompileDockerRuntime

    def executor(**kwargs):
        raise RuntimeError("受控错误")

    with pytest.raises(RuntimeError):
        common.run_strategy(method=common.METHODS[2], item=spec["project"], protocol=spec, root=tmp_path, model=None, meter_factory=common.CommonQualificationMeter, executor=executor)
    assert arm.CompileDockerRuntime is original
    with pytest.raises(PlanContractError):
        common.run_strategy(method="unknown", item=spec["project"], protocol=spec, root=tmp_path, model=None, meter_factory=common.CommonQualificationMeter, executor=executor)


def test_material_receipt_records_full_pre_encoding_packet_and_rejects_tampering(tmp_path):
    ledger = PlanAgentLedger(tmp_path / "agent")
    text = "完整测试、动作和状态保持不变。" * 80
    packet = {"task": {"tests": text}, "current_plan": {"tests": text}, "state": {"status": "inspected"}}
    meter = common.CommonQualificationMeter(ledger, accepted_models=("scripted-gate",), deadline="2099-01-01T00:00:00+00:00", packet=lambda: copy.deepcopy(packet))
    encoded = meter.packet()
    receipt = json.loads((ledger.directory / "material-1.json").read_text())
    assert restore_factor_packet(encoded) == receipt["projected"]
    assert receipt["projected"]["task"] == packet["task"]
    assert receipt["projected"]["current_plan"] == packet["current_plan"]
    changed = copy.deepcopy(encoded)
    changed["forge_shared_texts"][next(iter(changed["forge_shared_texts"]))] += "改动"
    with pytest.raises(PlanContractError):
        restore_factor_packet(changed)


@pytest.mark.parametrize("field,value", [("provider_calls", 1), ("max_model_cost_usd", 1), ("credentials_read", True), ("reserve_seconds", 1)])
def test_gate_rejects_paid_or_relaxed_protocol_before_evidence_read(field, value):
    spec = fixture()
    spec.update(identity=gate.IDENTITY, schedule=gate.schedule(), started_window_utc="2026-10-21T13:40:00+00:00", deadline_utc="2026-10-21T16:40:00+00:00")
    spec[field] = value
    with pytest.raises(PlanContractError):
        gate.validate(spec)
