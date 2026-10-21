"""真实新授权的请求策略、截止和零Provider门禁。"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_rtorrent_canary_v2 as canary  # noqa: E402

from deerflow.compile.agent_workflow_node import AgentWorkflowBudgetExceeded  # noqa: E402
from deerflow.compile.plan_agent import PlanAgentLedger  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402


def authorization():
    start = datetime.now(UTC) - timedelta(seconds=1)
    return dict(
        experiment_identity=canary.IDENTITY,
        candidate_sha256="candidate",
        user_authorized=True,
        max_new_provider_cost_usd=10,
        authorized_at_utc=start.isoformat(),
        deadline_utc=(start + timedelta(hours=4)).isoformat(),
        max_total_model_requests=None,
        automatic_retry=False,
    )


def test_exact_user_authorization_accepted():
    canary.validate_authorization("candidate", authorization())


@pytest.mark.parametrize(
    "field,value",
    [("max_new_provider_cost_usd", 10.01), ("automatic_retry", True), ("max_total_model_requests", 36), ("experiment_identity", "old"), ("candidate_sha256", "old"), ("user_authorized", False), ("deadline_utc", "2099-01-01T00:00:00+00:00")],
)
def test_other_or_extended_authorization_rejected(field, value):
    auth = authorization()
    auth[field] = value
    with pytest.raises(PlanContractError):
        canary.validate_authorization("candidate", auth)


def test_thirteenth_request_allowed_and_step_budget_still_binding(tmp_path):
    meter = canary.AuthorizedMeter(PlanAgentLedger(tmp_path / "meter"), accepted_models=("unused",), deadline="2099-01-01T00:00:00+00:00", packet=lambda: {})
    for _ in range(72):
        meter._before_request()
    assert meter.tracker.snapshot().model_requests == 72
    with pytest.raises(AgentWorkflowBudgetExceeded) as failure:
        meter._before_request()
    assert failure.value.reason == "agent_steps"
    assert meter.tracker.limits.max_recorded_tokens == 400000
    assert meter.tracker.limits.max_recorded_tokens_per_response == 100000
    assert meter.tracker.limits.max_tool_calls == 48
    assert meter.tracker.limits.max_commands == 32
    assert canary.REQUEST_POLICY["independent_request_cap"] is None


def test_old_canary_constants_restored_after_new_main(monkeypatch):
    old_id, old_runtime, old_meter = canary.previous.IDENTITY, canary.previous.RUNTIME, canary.previous.CommonStrategyMeter

    def main():
        assert canary.previous.IDENTITY == canary.IDENTITY
        assert canary.previous.CommonStrategyMeter is canary.AuthorizedMeter
        return 0

    monkeypatch.setattr(canary.previous, "main", main)
    assert canary.main() == 0
    assert (canary.previous.IDENTITY, canary.previous.RUNTIME, canary.previous.CommonStrategyMeter) == (old_id, old_runtime, old_meter)


def test_validate_only_never_reads_credentials(tmp_path, monkeypatch, capsys):
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps({}))
    monkeypatch.setattr(canary, "validate", lambda value: None)
    monkeypatch.setattr(sys, "argv", ["canary-v2", "--candidate", str(path), "--validate-only"])

    def forbidden(name):
        raise AssertionError("免费验证不得读取环境凭据")

    monkeypatch.setattr(canary.previous, "os", SimpleNamespace(environ=SimpleNamespace(get=forbidden)))
    assert canary.main() == 0
    assert json.loads(capsys.readouterr().out)["provider_calls"] == 0


def test_invalid_new_candidate_never_enters_parent_validation(monkeypatch):
    monkeypatch.setattr(canary, "OLD_VALIDATE", lambda value: pytest.fail("不应读取父证据"))
    with pytest.raises(PlanContractError):
        canary.validate(dict(identity=canary.IDENTITY, runtime=canary.RUNTIME, request_policy={**canary.REQUEST_POLICY, "automatic_retry": True}))
