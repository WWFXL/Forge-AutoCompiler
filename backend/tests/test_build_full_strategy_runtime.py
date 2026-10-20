"""三策略统一入口的冻结顺序、同资源、成本及门禁前Provider隔离。"""

import json
import sys
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_full_strategy_runtime as runtime  # noqa: E402

from deerflow.compile.plan_agent import PlanAgentLedger  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402


def test_gate_contains_every_design_method_and_both_fallback_routes():
    schedule = runtime.gate_schedule()
    normal = [s for s in schedule if s["case"] == "normal"]
    assert len(normal) == 9
    assert {(s["project"], s["method"]) for s in normal} == {(p, m) for p in ("buffer", "uncrustify", "libverto") for m in runtime.METHODS}
    assert {s["case"] for s in schedule} >= {"rule_recovery", "rule_then_agent", "uncovered_to_agent", "agent_recovery"}


def protocol():
    design = json.loads((runtime.REPO_ROOT / runtime.DESIGN).read_text())
    return {"schedule": design["schedule"], "projects": design["projects"], "gate_projects": [], "deadline_utc": "2026-10-20T03:48:10Z", "max_estimated_cost_usd": 20}


def fake_row():
    return {"cleanup": {"succeeded": True}, "strict_completed": True, "agent_usage": {"estimated_cost_usd_completed_responses": "0.1", "unknown_usage_requests": 0}}


def test_live_dispatch_preserves_all_slots_no_reference_and_unique_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "before_deadline", Mock())
    calls = []

    def executor(**kwargs):
        calls.append(kwargs)
        return fake_row()

    p = protocol()
    rows, missing, reason = runtime.execute(p, tmp_path, "model", {}, qualify=False, executor=executor)
    assert not missing and reason is None and len(rows) == 36
    assert [{k: r[k] for k in ("project", "repetition", "method")} for r in rows] == p["schedule"]
    assert all(c["reference"] is None and c["model"] == "model" and c["meter_factory"] is runtime.StrategyMeter for c in calls)
    assert len({c["item"]["name"] for c in calls}) == 36
    assert [c["arm"] for c in calls] == ["tool" if s["method"] == runtime.METHODS[0] else "plan" for s in p["schedule"]]


def test_budget_reserves_next_entire_arm_and_keeps_unobserved(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "before_deadline", Mock())
    p = protocol()
    p["max_estimated_cost_usd"] = 1.59
    rows, missing, reason = runtime.execute(p, tmp_path, None, {}, qualify=False, executor=lambda **kw: fake_row())
    assert len(rows) == 1 and len(missing) == 35 and reason == "stage_cost_reservation"
    assert all(s["status"] == "not_observed" for s in missing)


def test_unknown_usage_stops_without_replacement(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "before_deadline", Mock())
    row = fake_row()
    row["agent_usage"]["unknown_usage_requests"] = 1
    rows, missing, reason = runtime.execute(protocol(), tmp_path, None, {}, qualify=False, executor=lambda **kw: deepcopy(row))
    assert len(rows) == 1 and len(missing) == 35 and reason == "cleanup_or_unknown_usage"


def test_deadline_refusal_does_not_call_executor(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "before_deadline", Mock(side_effect=PlanContractError("时限")))
    executor = Mock()
    rows, missing, reason = runtime.execute(protocol(), tmp_path, None, {}, qualify=False, executor=executor)
    assert not rows and len(missing) == 36 and reason == "deadline_reservation"
    executor.assert_not_called()


def test_shared_meter_resource_and_reserve_without_model(tmp_path, monkeypatch):
    meter = runtime.StrategyMeter(PlanAgentLedger(tmp_path / "ledger"), accepted_models=("scripted-gate",), deadline="2026-10-20T03:48:10Z", packet=lambda: {})
    assert meter.tracker.limits.command_timeout_seconds == 600
    assert meter.tracker.limits.replay_timeout_seconds == 900
    guard = Mock(side_effect=PlanContractError("时限"))
    monkeypatch.setattr(runtime, "before_deadline", guard)
    with pytest.raises(PlanContractError):
        meter._before_request()
    guard.assert_called_once_with(meter.deadline, 3900)
    assert meter.summary()["model_requests"] == 0


def test_missing_gate_fails_before_credentials_or_provider(monkeypatch, tmp_path):
    p = tmp_path / "protocol.json"
    p.write_text(json.dumps({"deadline_utc": "deadline", "authorization": {"root": str(tmp_path), "sha256": "authorized"}}))
    monkeypatch.setattr(runtime, "validate", Mock(return_value={}))
    monkeypatch.setattr(runtime, "digest", Mock(return_value="authorized"))
    monkeypatch.setattr(runtime, "SharedResearchBudget", Mock(return_value=Mock(authorization={"deadline_utc": "deadline", "max_new_provider_cost_usd": 20})))
    key = Mock(side_effect=AssertionError("门禁前不得读取凭据"))
    monkeypatch.setattr(runtime, "os", Mock(environ=Mock(get=key)))
    model = Mock(side_effect=AssertionError("门禁前不得创建Provider"))
    monkeypatch.setattr(runtime, "PlanThinkingDeepSeek", model)
    monkeypatch.setattr(sys, "argv", ["runtime", "--protocol", str(p), "--output-root", str(tmp_path / "out"), "--shared-budget-root", str(tmp_path)])
    with pytest.raises(PlanContractError, match="缺少门禁"):
        runtime.main()
    model.assert_not_called()
    key.assert_not_called()
