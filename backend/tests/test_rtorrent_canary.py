"""新 canary 的授权、费用、失败保留与不重试调度。"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_rtorrent_canary as canary  # noqa: E402
from forge_build_plan_agent_canary import PlanAgentLedger  # noqa: E402

from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402


def authorization():
    start = datetime.now(UTC) - timedelta(seconds=5)
    return dict(experiment_identity=canary.IDENTITY, candidate_sha256="candidate", user_authorized=True, max_new_provider_cost_usd=5, authorized_at_utc=start.isoformat(), deadline_utc=(start + timedelta(hours=3)).isoformat())


@pytest.mark.parametrize("field,value", [("user_authorized", False), ("experiment_identity", "old"), ("candidate_sha256", "old"), ("max_new_provider_cost_usd", 6), ("deadline_utc", "2099-01-01T00:00:00+00:00")])
def test_old_missing_over_budget_or_extended_authorization_rejected(field, value):
    auth = authorization()
    auth[field] = value
    with pytest.raises(PlanContractError):
        canary.validate_authorization("candidate", auth)


def test_exact_bounded_authorization_accepted():
    canary.validate_authorization("candidate", authorization())


def test_candidate_limits_match_inherited_runtime_instead_of_early_trial_defaults(tmp_path):
    meter = canary.CommonStrategyMeter(PlanAgentLedger(tmp_path / "meter"), accepted_models=("unused",), deadline="2099-01-01T00:00:00+00:00", packet=lambda: {})
    for key in ("max_model_requests", "max_recorded_tokens", "max_recorded_tokens_per_response", "max_agent_steps", "max_tool_calls", "max_commands", "node_timeout_seconds", "evaluator_timeout_seconds", "cleanup_timeout_seconds"):
        assert getattr(meter.tracker.limits, key) == canary.RUNTIME[key]


def protocol(maximum=5):
    return dict(schedule=canary.schedule(), deadline_utc="2099-01-01T00:00:00+00:00", max_new_provider_cost_usd=maximum, project={"name": "rtorrent"})


def response(*, success=True, unknown=0, cleanup=True, cost="0.10"):
    return dict(strict_completed=success, error_class=None if success else "PlanContractError", cleanup={"succeeded": cleanup}, agent_usage=dict(estimated_cost_usd_completed_responses=cost, unknown_usage_requests=unknown))


@pytest.mark.parametrize("error", ["PlanContractError", "AgentWorkflowBudgetExceeded", "ValidationError"])
def test_method_failure_kept_and_other_fixed_slots_continue(tmp_path, error):
    calls = []

    def executor(**kwargs):
        calls.append(kwargs)
        assert "qualification_reference" not in kwargs
        value = response(success=len(calls) != 1)
        if len(calls) == 1:
            value["error_class"] = error
        return value

    rows, unseen, reason = canary.execute(protocol(), tmp_path, "model", executor=executor)
    assert len(rows) == len(calls) == 3 and not unseen and reason is None
    assert not rows[0]["strict_completed"] and all(r["strict_completed"] for r in rows[1:])
    assert [c["method"] for c in calls] == list(canary.METHODS)


@pytest.mark.parametrize("problem", ["unknown", "cleanup", "model_identity"])
def test_unknown_cleanup_and_model_mismatch_stop_batch_without_replacement(tmp_path, problem):
    def executor(**kwargs):
        if problem == "model_identity":
            p = kwargs["root"] / "rtorrent-plan/agent"
            p.mkdir(parents=True)
            (p / "events.jsonl").write_text(json.dumps({"event": "model.identity_mismatch"}) + "\n")
        return response(unknown=int(problem == "unknown"), cleanup=problem != "cleanup")

    rows, unseen, reason = canary.execute(protocol(), tmp_path, None, executor=executor)
    assert len(rows) == 1 and unseen == canary.schedule()[1:] and reason is not None


def test_shared_budget_requires_whole_next_arm_reservation(tmp_path):
    rows, unseen, reason = canary.execute(protocol(1.55), tmp_path, None, executor=lambda **kw: response())
    assert len(rows) == 1 and len(unseen) == 2 and reason == "stage_cost_reservation"


def test_out_of_contract_actual_response_usage_is_preserved_and_stops_batch(tmp_path):
    def executor(**kwargs):
        p = kwargs["root"] / "rtorrent-plan/agent"
        p.mkdir(parents=True)
        (p / "events.jsonl").write_text(json.dumps(dict(event="model.request_completed", recorded_tokens=100001)) + "\n")
        value = response(success=False)
        value["agent_usage"]["recorded_tokens"] = 100001
        return value

    rows, unseen, reason = canary.execute(protocol(), tmp_path, None, executor=executor)
    assert len(rows) == 1 and rows[0]["agent_usage"]["recorded_tokens"] == 100001
    assert len(unseen) == 2 and reason == "budget_contract_violation"


def test_single_response_excess_detected_even_without_completed_event(tmp_path):
    def executor(**kwargs):
        p = kwargs["root"] / "rtorrent-plan/agent"
        p.mkdir(parents=True)
        (p / "response-1.json").write_text(json.dumps([dict(type="ai", usage_metadata=dict(input_tokens=100000, output_tokens=1, total_tokens=100001))]))
        value = response(success=False)
        value["error_class"] = "AgentWorkflowBudgetExceeded"
        return value

    rows, unseen, reason = canary.execute(protocol(), tmp_path, None, executor=executor)
    assert len(rows) == 1 and len(unseen) == 2 and reason == "budget_contract_violation"


def test_no_authorization_stops_before_key_read_or_provider_construction(tmp_path, monkeypatch):
    path = tmp_path / "candidate.json"
    path.write_text("{}")
    monkeypatch.setattr(canary, "validate", lambda candidate: None)
    monkeypatch.setattr(sys, "argv", ["canary", "--candidate", str(path)])
    monkeypatch.setattr(canary, "os", SimpleNamespace(environ=SimpleNamespace(get=lambda *a: pytest.fail("未授权不得读凭据"))))
    monkeypatch.setattr(canary, "PlanThinkingDeepSeek", lambda **kw: pytest.fail("未授权不得构造Provider"))
    with pytest.raises(PlanContractError, match="新明确授权"):
        canary.main()


def test_dry_validation_cannot_enter_provider_branch(tmp_path, monkeypatch):
    path = tmp_path / "candidate.json"
    path.write_text("{}")
    monkeypatch.setattr(canary, "validate", lambda candidate: None)
    monkeypatch.setattr(sys, "argv", ["canary", "--candidate", str(path), "--validate-only"])
    monkeypatch.setattr(canary, "os", SimpleNamespace(environ=SimpleNamespace(get=lambda *a: pytest.fail("免费验证不得读凭据"))))
    assert canary.main() == 0
