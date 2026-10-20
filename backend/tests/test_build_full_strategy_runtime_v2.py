"""零Provider工程请求不占付费余量，真实请求仍受3900秒保护。"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_full_strategy_runtime import StrategyMeter  # noqa: E402
from forge_build_full_strategy_runtime_v2 import QualificationAwareMeter  # noqa: E402

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_workflow import PlanContractError


def meter(cls, path, models=("scripted-gate",)):
    return cls(PlanAgentLedger(path), accepted_models=models, deadline=(datetime.now(UTC) + timedelta(seconds=1800)).isoformat(), packet=lambda: {})


def test_reproduce_original_gate_refusal_and_allow_only_zero_provider(tmp_path):
    old = meter(StrategyMeter, tmp_path / "old")
    with pytest.raises(PlanContractError, match="时限"):
        old._before_request()
    new = meter(QualificationAwareMeter, tmp_path / "new")
    assert new._before_request() == 1
    assert new.tracker.limits == old.tracker.limits


def test_paid_model_still_uses_original_3900_second_admission(tmp_path):
    paid = meter(QualificationAwareMeter, tmp_path / "paid", ("deepseek-v4-pro",))
    with pytest.raises(PlanContractError, match="时限"):
        paid._before_request()
    assert paid.summary()["model_requests"] == 0


def test_scripted_route_refuses_nonzero_usage(tmp_path):
    gate = meter(QualificationAwareMeter, tmp_path / "gate")
    gate.input_tokens = 1
    with pytest.raises(PlanContractError, match="非零用量"):
        gate._before_request()
    assert gate.summary()["model_requests"] == 0
