"""新接口调度、参考隔离、全成本停止及授权边界；不访问Provider。"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_observed_plan_comparison as compare

from deerflow.compile.plan_workflow import PlanContractError


def protocol():
    return {"schedule": compare.schedule(), "projects": [{"name": p} for p in compare.PROJECTS], "deadline_utc": (datetime.now(UTC) + timedelta(hours=4)).isoformat(), "max_new_provider_cost_usd": 20}


def result(unknown=0, cleanup=True):
    return {"agent_usage": {"estimated_cost_usd_completed_responses": 0.1, "unknown_usage_requests": unknown}, "cleanup": {"succeeded": cleanup}}


def test_fixed_complete_denominator_and_disclosed_position_imbalance():
    rows = compare.schedule()
    assert len(rows) == len({(r["project"], r["method"]) for r in rows}) == 12
    for method in compare.METHODS:
        assert sorted(sum(rows[i]["method"] == method for i in range(pos, 12, 3)) for pos in range(3)) == [1, 1, 2]


def test_execute_includes_failures_without_loading_reference(tmp_path):
    executor = Mock(side_effect=lambda **kw: result())
    rows, unseen, reason = compare.execute(protocol(), tmp_path, "model", executor=executor)
    assert len(rows) == 12 and not unseen and reason is None
    assert all(c.kwargs["reference"] is None and c.kwargs["qualify"] is False for c in executor.call_args_list)


@pytest.mark.parametrize("unknown,cleanup", [(1, True), (0, False)])
def test_unknown_or_cleanup_stops_global_queue(tmp_path, unknown, cleanup):
    rows, unseen, reason = compare.execute(protocol(), tmp_path, None, executor=Mock(return_value=result(unknown, cleanup)))
    assert len(rows) == 1 and len(unseen) == 11 and reason == "cleanup_or_unknown_usage"


def test_provider_identity_stops_global_queue(tmp_path):
    row = {**result(), "error_message": "Provider 返回的模型标识不符合运行协议"}
    assert compare.execute(protocol(), tmp_path, None, executor=Mock(return_value=row))[2] == "provider_identity_mismatch"


def test_cost_of_failed_slots_counts_before_next_admission(tmp_path):
    p = {**protocol(), "max_new_provider_cost_usd": 1.55}
    rows, unseen, reason = compare.execute(p, tmp_path, None, executor=Mock(return_value=result()))
    assert len(rows) == 1 and len(unseen) == 11 and reason == "stage_cost_reservation"


def test_deadline_blocks_executor(tmp_path):
    executor = Mock()
    p = {**protocol(), "deadline_utc": (datetime.now(UTC) + timedelta(minutes=60)).isoformat()}
    assert compare.execute(p, tmp_path, None, executor=executor)[2] == "deadline_reservation"
    executor.assert_not_called()


@pytest.mark.parametrize("method,source,arm", [("tool_plan_workflow", "tool", "plan"), ("model_plan_workflow", "model", "plan"), ("strong_tool_agent", "model", "tool")])
def test_new_dispatch_explicitly_injects_observed_interface(tmp_path, monkeypatch, method, source, arm):
    factory = Mock(return_value=Mock(return_value="new-plan"))
    monkeypatch.setattr(compare, "observed_planner", factory)
    executor = Mock(return_value={"strict_completed": False})
    compare.slot_runner(protocol={}, root=tmp_path, slot={"method": method}, item={}, model="same-model", executor=executor)
    factory.assert_called_once_with(source)
    kw = executor.call_args.kwargs
    assert kw["arm"] == arm and kw["reference"] is None and kw["meter_factory"] is compare.StrategyMeter
    assert kw["command_timeout_seconds"] == 600 and kw["replay_timeout_seconds"] == 900
    assert kw["planner"](task="task") == "new-plan"
    factory.return_value.assert_called_once_with(task="task", model="same-model")


@pytest.mark.parametrize("method,reference", [("unknown", None), ("model_plan_workflow", {})])
def test_real_dispatch_rejects_unknown_method_or_reference_leak(tmp_path, method, reference):
    with pytest.raises(PlanContractError):
        compare.slot_runner(protocol={}, root=tmp_path, slot={"method": method}, item={}, reference=reference)


def authorization():
    now = datetime.now(UTC)
    return {
        "experiment_identity": compare.IDENTITY,
        "candidate_sha256": "new-hash",
        "user_authorized": True,
        "authorized_at_utc": now.isoformat(),
        "deadline_utc": (now + timedelta(hours=4)).isoformat(),
        "max_new_provider_cost_usd": 20,
        "provider_service_recheck_authorized": True,
    }


def test_new_authorization_accepts_only_current_candidate_and_identity():
    compare.validate_authorization("new-hash", authorization())
    for key, value in [("experiment_identity", "cpp-build-unified-plan-comparison-v1"), ("candidate_sha256", "old"), ("user_authorized", False), ("max_new_provider_cost_usd", 21), ("provider_service_recheck_authorized", False)]:
        with pytest.raises(PlanContractError):
            compare.validate_authorization("new-hash", {**authorization(), key: value})


def test_expired_future_or_overlong_window_rejected():
    now = datetime.now(UTC)
    for start, end in [(now - timedelta(hours=5), now - timedelta(hours=1)), (now + timedelta(minutes=1), now + timedelta(hours=4)), (now, now + timedelta(hours=5))]:
        with pytest.raises(PlanContractError):
            compare.validate_authorization("new-hash", {**authorization(), "authorized_at_utc": start.isoformat(), "deadline_utc": end.isoformat()})


def test_cli_rejects_missing_authorization_before_environment_or_output(tmp_path, monkeypatch):
    candidate = tmp_path / "candidate.json"
    candidate.write_text("{}")
    monkeypatch.setattr(compare, "validate", Mock())
    monkeypatch.setattr(compare, "require_gates", Mock())
    monkeypatch.setattr(sys, "argv", ["compare", "--candidate", str(candidate), "--output-root", str(tmp_path / "raw")])
    monkeypatch.setattr(compare, "os", SimpleNamespace(environ=None))
    with pytest.raises(PlanContractError, match="新的明确授权"):
        compare.main()
    assert not (tmp_path / "raw").exists()
