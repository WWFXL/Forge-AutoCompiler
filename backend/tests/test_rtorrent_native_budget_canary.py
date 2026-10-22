"""只检查资源变化与旧费用夹紧不会截断新预算，不重做构建资格。"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_rtorrent_fixed_contract import FixedVerifierRegistry  # noqa: E402
from forge_build_rtorrent_native_budget_canary import PaidNativeMeter  # noqa: E402

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_workflow import PlanContractError


@pytest.mark.parametrize("cost,allowed", [(1.30, True), (2.21, False)])
def test_expanded_reservation_replaces_old_clamps(tmp_path, cost, allowed):
    value = PaidNativeMeter(
        PlanAgentLedger(tmp_path / "agent"), accepted_models=("deepseek-v4-pro",), registry=FixedVerifierRegistry(dict(verification_steps=[])), packet=lambda: {}, deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat()
    )
    value.cost_usd = cost
    assert value.tracker.limits.max_recorded_tokens == 1000000
    assert value.tracker.limits.max_agent_steps == 144
    assert value.tracker.limits.max_tool_calls == 96
    assert value.tracker.limits.max_commands == 64
    if allowed:
        assert value._before_request() == 1
    else:
        with pytest.raises(PlanContractError):
            value._before_request()
        assert value.summary()["model_requests"] == 0
