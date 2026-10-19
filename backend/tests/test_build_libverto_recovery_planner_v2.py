"""早期交接不得访问不存在的测试诊断，也不能遮盖真实失败阶段。"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_libverto_recovery_planner_v2 import planner_for  # noqa: E402

from deerflow.compile.plan_workflow import BuildPlan, PlanContractError  # noqa: E402


def setup_case():
    protocol = json.loads((Path(__file__).resolve().parents[2] / "benchmarks/analyses/cpp-build-libverto-natural-recovery-v1.json").read_text())
    plan = BuildPlan.model_validate(protocol["initial_plan"])
    handoff = {"plan_sha256": plan.fingerprint(), "reason": "step_failed_or_expectation_missing", "step_id": "check", "recent_commands": [{"command": "make check", "exit_code": 2, "timed_out": False}]}
    return plan, handoff, planner_for(protocol["initial_plan"])


def test_dependency_handoff_rejected_before_any_source_access():
    plan, h, planner = setup_case()
    h["step_id"] = "dep"
    source = Mock()
    with pytest.raises(PlanContractError, match="非固定测试"):
        planner(current_plan=plan, handoff=h, source_root=source)
    assert source.mock_calls == []


def test_missing_test_diagnostic_has_contract_error(tmp_path):
    plan, h, planner = setup_case()
    with pytest.raises(PlanContractError, match="缺少必需诊断"):
        planner(current_plan=plan, handoff=h, source_root=tmp_path)


def test_stale_handoff_rejected_before_source_access():
    plan, h, planner = setup_case()
    h["plan_sha256"] = "old"
    source = Mock()
    with pytest.raises(PlanContractError, match="当前初始"):
        planner(current_plan=plan, handoff=h, source_root=source)
    assert source.mock_calls == []


def test_valid_full_diagnostic_still_revises_only_configure(tmp_path):
    plan, h, planner = setup_case()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test-suite.log").write_text("# TOTAL: 6\n# PASS:  0\n# FAIL:  6\n" + "Assertion `(ctx = verto_default(MODULES[i], VERTO_EV_TYPE_NONE))' failed.\n" * 6)
    (tmp_path / "config.log").write_text("BUILTIN_MODULE=''")
    ledger = Mock()
    revised, _ = planner(current_plan=plan, handoff=h, source_root=tmp_path, meter=SimpleNamespace(ledger=ledger))
    assert revised.revision == 2
    assert [s.model_dump() for s in revised.steps if s.role == "smoke"] == [s.model_dump() for s in plan.steps if s.role == "smoke"]
    assert [s.command for s in revised.steps if s.step_id == "configure"] == ["./configure --enable-shared --enable-static"]
    ledger.append.assert_called_once()
