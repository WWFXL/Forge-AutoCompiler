"""仅验证新增真实入口的费用保留和停止行为，不重复构建资格。"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_rtorrent_native_canary import IDENTITY, charges, execute, validate_authorization  # noqa: E402

from deerflow.compile.plan_workflow import PlanContractError


def auth():
    now = datetime.now(UTC) - timedelta(seconds=1)
    return dict(
        experiment_identity=IDENTITY,
        candidate_sha256="candidate",
        user_authorized=True,
        authorization_basis="current_user_direct_experiment_instruction",
        automatic_retry=False,
        max_new_provider_cost_usd="4.50",
        authorized_at_utc=now.isoformat(),
        deadline_utc=(now + timedelta(hours=4)).isoformat(),
    )


def test_new_current_authorization_and_old_identity_rejection():
    value = auth()
    validate_authorization("candidate", value)
    with pytest.raises(PlanContractError):
        validate_authorization("candidate", {**value, "experiment_identity": "old"})


def test_unknown_request_is_reserved_at_eighty_cents():
    assert tuple(str(v) for v in charges([dict(agent_usage=dict(estimated_cost_usd_completed_responses="0.12", unknown_usage_requests=1))])) == ("0.12", "0.80")


@pytest.mark.parametrize("unknown,expected_slots", [(0, 3), (1, 1)])
def test_method_failure_continues_but_unknown_usage_stops(tmp_path, unknown, expected_slots):
    calls = []

    def executor(**kwargs):
        assert "qualification_reference" not in kwargs
        calls.append(kwargs["method"])
        return dict(
            strict_completed=False,
            error_class="PlanContractError",
            error_message="方法失败保留",
            cleanup=dict(succeeded=True),
            agent_usage=dict(estimated_cost_usd_completed_responses="0.1", unknown_usage_requests=unknown, recorded_tokens=123),
        )

    p = dict(schedule=[dict(method=str(i)) for i in range(3)], project={}, deadline_utc=auth()["deadline_utc"], max_new_provider_cost_usd="4.50")
    rows, unseen, reason = execute(p, tmp_path, object(), executor=executor)
    assert len(rows) == len(calls) == expected_slots and len(unseen) == 3 - expected_slots
    assert reason == ("cleanup_or_unknown_usage" if unknown else None)
