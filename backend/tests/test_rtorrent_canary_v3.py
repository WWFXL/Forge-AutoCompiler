"""后续独立阶段的原授权、旧费和原截止约束。"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_rtorrent_canary_v3 as canary  # noqa: E402

from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402


def binding(tmp_path, monkeypatch):
    start = datetime.now(UTC) - timedelta(seconds=1)
    user = dict(user_authorized=True, authorized_at_utc=start.isoformat(), deadline_utc=(start + timedelta(hours=4)).isoformat(), max_new_provider_cost_usd=10, max_total_model_requests=None, automatic_retry=False)
    up = tmp_path / "user.json"
    up.write_text(json.dumps(user))
    monkeypatch.setattr(canary, "USER_AUTH_SHA", canary.digest(up))
    old = tmp_path / "old"
    old.mkdir()
    result = dict(known_estimated_cost_usd="0.82323780", unknown_usage_reservation_usd="0", lifecycle_complete=True)
    (old / "result.json").write_text(json.dumps(result))
    budget = tmp_path / "old-budget"
    budget.mkdir()
    events = [dict(event="stage.started", identity=canary.v2.IDENTITY), dict(event="stage.completed", identity=canary.v2.IDENTITY, charged_cost_usd="0.82323780", inventory_sha256=canary.PRIOR_INVENTORY)]
    ep = budget / "budget-events.jsonl"
    ep.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    monkeypatch.setattr(canary, "audit", lambda path: dict(inventory_canonical_sha256=canary.PRIOR_INVENTORY))
    return dict(
        **{k: v for k, v in user.items() if k != "max_new_provider_cost_usd"},
        experiment_identity=canary.IDENTITY,
        candidate_sha256="candidate",
        max_new_provider_cost_usd=4.5,
        shared_user_authorization=dict(path=str(up), sha256=canary.digest(up)),
        prior_paid_stage=dict(root=str(old), budget_root=str(budget), budget_events_sha256=canary.digest(ep), charged_cost_usd="0.82323780", inventory_sha256=canary.PRIOR_INVENTORY),
    )


def test_closed_prior_stage_and_original_window_allow_bounded_new_stage(tmp_path, monkeypatch):
    auth = binding(tmp_path, monkeypatch)
    canary.validate_authorization("candidate", auth)


@pytest.mark.parametrize(
    "field,value",
    [("automatic_retry", True), ("max_new_provider_cost_usd", 4.51), ("max_total_model_requests", 99), ("deadline_utc", "2099-01-01T00:00:00+00:00"), ("experiment_identity", "old"), ("candidate_sha256", "old"), ("user_authorized", False)],
)
def test_cannot_extend_retry_change_identity_or_reservation(tmp_path, monkeypatch, field, value):
    auth = binding(tmp_path, monkeypatch)
    auth[field] = value
    with pytest.raises(PlanContractError):
        canary.validate_authorization("candidate", auth)


@pytest.mark.parametrize("failure", ["unknown_usage", "open_stage", "charge_mismatch", "incomplete", "modified_user", "modified_ledger", "shared_exhausted"])
def test_prior_unknown_unclosed_or_inconsistent_cost_prevents_new_stage(tmp_path, monkeypatch, failure):
    auth = binding(tmp_path, monkeypatch)
    prior = auth["prior_paid_stage"]
    rp = Path(prior["root"]) / "result.json"
    result = json.loads(rp.read_text())
    ep = Path(prior["budget_root"]) / "budget-events.jsonl"
    events = [json.loads(line) for line in ep.read_text().splitlines()]
    if failure == "unknown_usage":
        result["unknown_usage_reservation_usd"] = "0.40"
    elif failure == "open_stage":
        events.pop()
    elif failure == "charge_mismatch":
        prior["charged_cost_usd"] = "0"
    elif failure == "incomplete":
        result["lifecycle_complete"] = False
    elif failure == "modified_user":
        Path(auth["shared_user_authorization"]["path"]).write_text("{}")
    elif failure == "modified_ledger":
        ep.write_text("{}\n")
    else:
        result["known_estimated_cost_usd"] = "9"
        events[1]["charged_cost_usd"] = "9"
        prior["charged_cost_usd"] = "9"
    rp.write_text(json.dumps(result))
    if failure != "modified_ledger":
        ep.write_text("\n".join(json.dumps(e) for e in events) + "\n")
        prior["budget_events_sha256"] = canary.digest(ep)
    with pytest.raises(PlanContractError):
        canary.validate_authorization("candidate", auth)


def test_main_restores_old_frozen_module_bindings(monkeypatch):
    old = canary.previous.IDENTITY, canary.previous.CommonStrategyMeter, canary.previous.validate

    def main():
        assert canary.previous.IDENTITY == canary.IDENTITY
        assert canary.previous.CommonStrategyMeter is canary.SharedValueMeter
        return 0

    monkeypatch.setattr(canary.previous, "main", main)
    assert canary.main() == 0
    assert (canary.previous.IDENTITY, canary.previous.CommonStrategyMeter, canary.previous.validate) == old


def test_invalid_candidate_rejected_before_old_gate_reads(monkeypatch):
    monkeypatch.setattr(canary.v2, "validate", lambda value: pytest.fail("不应读取父证据"))
    with pytest.raises(PlanContractError):
        canary.validate(dict(identity="old", parent_real_candidate_sha256=canary.PARENT_CANDIDATE_SHA))
