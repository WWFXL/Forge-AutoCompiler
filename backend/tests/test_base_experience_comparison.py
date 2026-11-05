"""只验证新编排的处理隔离、共享预算与异常停止，不重复构建核心资格。"""

import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_base_experience_comparison as comparison  # noqa: E402


@pytest.mark.parametrize("mode", comparison.MODES)
def test_dispatch_isolates_advice_from_recipe_and_baseline(mode, monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "offline-placeholder")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(comparison, "PlanThinkingDeepSeek", lambda **k: object())
    bank, recipe = object(), object()
    monkeypatch.setattr(comparison, "experience_inputs", lambda *a: (bank, {}) if mode == "advice" else (None, {"jsoncpp": recipe}))
    captured = []
    monkeypatch.setattr(comparison.shared, "run_simple_system", lambda **k: captured.append(k))
    executor = comparison.paid_executor(dict(mode=mode))
    item = comparison.shared.load(comparison.shared.FIXTURE)["projects"][0]
    for method in comparison.parent.METHODS:
        executor(slot=dict(method=method), item=item, folder=tmp_path / method, available=Decimal("0.75"), deadline=(datetime.now(UTC) + timedelta(hours=1)).isoformat())
    assert captured[0]["bank"] is None and captured[0]["recipe"] is None
    assert captured[1]["bank"] is (bank if mode == "advice" else None)
    assert captured[1]["recipe"] is (recipe if mode == "reuse" else None)
    assert captured[0]["model"] is captured[1]["model"]
    assert {c["maximum_cost_usd"] for c in captured} == {"0.40"}


@pytest.mark.parametrize("unknown,expected_stages", [(False, 2), (True, 1)])
def test_shared_session_debits_prior_cost_and_stops_on_unknown(unknown, expected_stages, monkeypatch, tmp_path):
    shared = comparison.shared
    values = {m: dict(identity=comparison.IDENTITIES[m], mode=m, schedule=[dict(slot=1, project="p", repetition=1, method="forge")], projects=[dict(name="p")]) for m in comparison.MODES}
    monkeypatch.setattr(comparison, "manifest", lambda m: tmp_path / (m + ".json"))
    for mode in comparison.MODES:
        shared.save(comparison.manifest(mode), values[mode])
    limits = []

    def paid_executor(value):
        def run(**kwargs):
            limits.append(kwargs["available"])
            return dict(agent_usage=dict(model_requests=1, estimated_cost_usd_completed_responses="0.60", unknown_usage_requests=int(unknown)), cleanup=dict(succeeded=True), arm_total_wall_seconds=1)

        return run

    monkeypatch.setattr(comparison, "paid_executor", paid_executor)
    monkeypatch.setattr(comparison, "analyze", lambda p: {})
    monkeypatch.setattr(comparison, "seal", lambda *a, **k: None)
    now = datetime.now(UTC)
    auth = dict(authorized_at_utc=now.isoformat(), deadline_utc=(now + timedelta(hours=1)).isoformat(), maximum_cost_usd="1.50", automatic_retry=False, user_reply="开启比较")
    comparison.run_session(values, tmp_path / "session", auth)
    result = shared.load(tmp_path / "session/session-result.json")
    assert len(result["stages"]) == expected_stages
    assert limits == [Decimal("1.00"), Decimal("0.90")][:expected_stages]
    assert result["known_cost_usd"] == ("1.20" if not unknown else "0.60")
    if unknown:
        assert not (tmp_path / "session/reuse").exists()


def test_both_comparisons_have_independent_balanced_pairs_and_no_baseline_io(monkeypatch):
    rows = comparison.parent.schedule()
    assert len(rows) == 16 and set(Counter((r["project"], r["repetition"]) for r in rows).values()) == {2}
    assert all(rows[i]["method"] != rows[i + 8]["method"] for i in range(8))
    assert len(set(comparison.IDENTITIES.values())) == 2
    monkeypatch.setattr(comparison.SimpleStateTargetBank, "load", lambda *a: pytest.fail("基础组不应读库"))
    assert comparison.experience_inputs({}, "forge") == (None, {})
