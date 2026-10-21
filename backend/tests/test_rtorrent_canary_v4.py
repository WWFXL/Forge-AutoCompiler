"""新独立真实身份不得漏计任一旧阶段或续期重试。"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_rtorrent_canary_v4 as canary  # noqa: E402

from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402


def binding(tmp_path, monkeypatch):
    # 原授权/v2检查已有独立回归；本夹具聚焦新增两个阶段的闭合与完整费用。
    monkeypatch.setattr(canary.v3, "validate_authorization", lambda sha, authorization: None)
    stages = []
    inventories = {}
    for i, identity in enumerate(canary.PRIOR_IDENTITIES):
        root = tmp_path / f"stage-{i}"
        budget = tmp_path / f"budget-{i}"
        root.mkdir()
        budget.mkdir()
        inventory = str(i) * 64
        cost = ("0.82323780", "0.7")[i]
        (root / "result.json").write_text(json.dumps(dict(identity=identity, lifecycle_complete=True, known_estimated_cost_usd=cost, unknown_usage_reservation_usd="0")))
        (root / "protocol.json").write_text(json.dumps(dict(deadline_utc="original-deadline")))
        events = [dict(event="stage.started", identity=identity), dict(event="stage.completed", identity=identity, inventory_sha256=inventory, charged_cost_usd=cost)]
        ledger = budget / "budget-events.jsonl"
        ledger.write_text("\n".join(json.dumps(e) for e in events) + "\n")
        stages.append(dict(identity=identity, root=str(root), budget_root=str(budget), inventory_sha256=inventory, charged_cost_usd=cost, budget_events_sha256=canary.digest(ledger)))
        inventories[root] = inventory
    monkeypatch.setattr(canary, "audit", lambda p: dict(inventory_canonical_sha256=inventories[p]))
    return dict(
        experiment_identity=canary.IDENTITY, candidate_sha256="candidate", deadline_utc="original-deadline", max_new_provider_cost_usd=4.5, prior_paid_stages=stages, prior_paid_stage={k: v for k, v in stages[0].items() if k != "identity"}
    )


def test_both_closed_known_stages_are_counted(tmp_path, monkeypatch):
    canary.validate_authorization("candidate", binding(tmp_path, monkeypatch))


@pytest.mark.parametrize("fault", ["omitted", "duplicate", "reordered", "unknown", "open", "incomplete", "cost", "ledger", "inventory", "deadline", "identity", "v2_disagreement", "exhausted"])
def test_missing_changed_unknown_or_exhausted_stage_prevents_provider(tmp_path, monkeypatch, fault):
    auth = binding(tmp_path, monkeypatch)
    prior = auth["prior_paid_stages"][1]
    result_path = Path(prior["root"]) / "result.json"
    result = json.loads(result_path.read_text())
    ledger = Path(prior["budget_root"]) / "budget-events.jsonl"
    events = [json.loads(x) for x in ledger.read_text().splitlines()]
    if fault == "omitted":
        auth["prior_paid_stages"].pop()
    elif fault == "duplicate":
        auth["prior_paid_stages"][1] = auth["prior_paid_stages"][0]
    elif fault == "reordered":
        auth["prior_paid_stages"].reverse()
    elif fault == "unknown":
        result["unknown_usage_reservation_usd"] = "0.40"
    elif fault == "open":
        events.pop()
    elif fault == "incomplete":
        result["lifecycle_complete"] = False
    elif fault == "cost":
        prior["charged_cost_usd"] = "0"
    elif fault == "ledger":
        events[1]["charged_cost_usd"] = "0"
    elif fault == "inventory":
        prior["inventory_sha256"] = "f" * 64
    elif fault == "deadline":
        (Path(prior["root"]) / "protocol.json").write_text(json.dumps(dict(deadline_utc="extended")))
    elif fault == "identity":
        result["identity"] = canary.PRIOR_IDENTITIES[0]
    elif fault == "v2_disagreement":
        auth["prior_paid_stage"]["charged_cost_usd"] = "0"
    else:
        result["known_estimated_cost_usd"] = "6"
        prior["charged_cost_usd"] = events[1]["charged_cost_usd"] = "6"
    result_path.write_text(json.dumps(result))
    ledger.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    prior["budget_events_sha256"] = canary.digest(ledger)
    with pytest.raises(PlanContractError):
        canary.validate_authorization("candidate", auth)


def test_main_restores_all_old_runtime_bindings(monkeypatch):
    previous = canary.previous
    old = previous.IDENTITY, previous.CommonStrategyMeter, previous.execute

    def main():
        assert previous.IDENTITY == canary.IDENTITY and previous.CommonStrategyMeter is canary.ContractMeter and previous.execute is canary.execute
        return 0

    monkeypatch.setattr(previous, "main", main)
    assert canary.main() == 0
    assert (previous.IDENTITY, previous.CommonStrategyMeter, previous.execute) == old
