"""16次比较沿用真实分派/费用停止接口，开发测试不产生Provider支出。"""

import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_planning_comparison as planning  # noqa: E402
from forge_simple_comparison import execute, validate_authorization  # noqa: E402


def test_schedule_and_real_dispatch_keep_16_slots_balanced_without_retry(tmp_path):
    schedule = planning.schedule()
    assert [s["slot"] for s in schedule] == list(range(1, 17))
    assert set(Counter((s["project"], s["repetition"]) for s in schedule).values()) == {2}
    assert all(schedule[i]["method"] != schedule[i + 8]["method"] for i in range(8))
    calls = []

    def executor(**kwargs):
        calls.append(kwargs)
        return dict(agent_usage=dict(model_requests=1, estimated_cost_usd_completed_responses="0.01", unknown_usage_requests=0), cleanup=dict(succeeded=True), layers=dict(full_completed=len(calls) != 2))

    protocol = dict(identity=planning.IDENTITY, schedule=schedule, projects=[dict(name=n) for n in planning.PROJECTS])
    result = execute(protocol, tmp_path / "run", dict(deadline_utc="2099-01-01T00:00:00+00:00", maximum_cost_usd="10"), executor)
    assert len(calls) == 16 and result["expected_slots"] == 16 and result["identity"] == planning.IDENTITY
    assert result["closed_slot_cost_usd"] == "0.16" and not result["rows"][1]["layers"]["full_completed"]


def test_new_identity_and_four_hour_window_cannot_reuse_old_authorization():
    now = datetime.now(UTC)
    auth = dict(
        identity=planning.IDENTITY,
        candidate_sha256="a" * 64,
        user_reply="明确授权新16次",
        authorized_at_utc=(now - timedelta(seconds=1)).isoformat(),
        deadline_utc=(now + timedelta(hours=3)).isoformat(),
        maximum_cost_usd="10",
        automatic_retry=False,
    )
    validate_authorization(auth, "a" * 64, identity=planning.IDENTITY, maximum_hours=4)
    for bad in (auth | dict(identity="cpp-build-simple-system-comparison-flash-v1"), auth | dict(deadline_utc=(now + timedelta(hours=5)).isoformat())):
        with pytest.raises(planning.PlanContractError):
            validate_authorization(bad, "a" * 64, identity=planning.IDENTITY, maximum_hours=4)
