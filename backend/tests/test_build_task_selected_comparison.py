"""两模板真实接线与跨阶段共享预算/绝对窗口边界。"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_task_selected_comparison as compare

from deerflow.compile.plan_workflow import PlanContractError


@pytest.mark.parametrize("method,generator", [(compare.METHODS[0], compare.observed_tool_actions), (compare.METHODS[1], compare.selected_tool_actions)])
def test_only_initial_generator_changes_and_same_recovery_model_remains(tmp_path, monkeypatch, method, generator):
    seen = {}

    def factory(source, *, generator):
        seen.update(source=source, generator=generator)

        def planner(**kwargs):
            seen["planner_model"] = kwargs["model"]

        return planner

    monkeypatch.setattr(compare, "observed_planner", factory)

    def executor(**kwargs):
        seen.update(kwargs)
        kwargs["planner"](model="wrong")
        return {}

    compare.slot_runner(protocol={}, root=tmp_path, slot={"method": method}, item={}, model="same", executor=executor)
    assert seen["source"] == "tool" and seen["generator"] is generator
    assert seen["arm"] == "plan" and seen["model"] == seen["planner_model"] == "same"
    assert seen["reference"] is None and seen["meter_factory"] is compare.StrategyMeter
    assert seen["command_timeout_seconds"] == 600 and seen["replay_timeout_seconds"] == 900


def test_fixed_six_slots_include_simd_negative_control_and_disclose_position_imbalance():
    rows = compare.schedule()
    assert len(rows) == 6
    assert {r["project"] for r in rows} == {"yaml-cpp", "simdutf", "snappy"}
    for project in {"yaml-cpp", "simdutf", "snappy"}:
        assert {r["method"] for r in rows if r["project"] == project} == set(compare.METHODS)
    assert [rows[i]["method"] for i in (0, 2, 4)].count(compare.METHODS[0]) == 2


@pytest.mark.parametrize("reference,qualify", [({}, False), (None, True)])
def test_no_reference_or_scripted_mode_in_real_comparison(tmp_path, reference, qualify):
    with pytest.raises(PlanContractError):
        compare.slot_runner(protocol={}, root=tmp_path, slot={"method": compare.METHODS[0]}, item={}, reference=reference, qualify=qualify)


def auth(tmp_path):
    start = datetime.now(UTC) - timedelta(minutes=1)
    original = dict(user_authorized=True, authorized_at_utc=start.isoformat(), deadline_utc=(start + timedelta(hours=4)).isoformat(), max_new_provider_cost_usd=20)
    (tmp_path / "authorization.json").write_text(json.dumps(original))
    stage = dict(original, experiment_identity=compare.IDENTITY, candidate_sha256="a" * 64, max_new_provider_cost_usd=9, shared_budget_root=str(tmp_path), shared_authorization_sha256=compare.digest(tmp_path / "authorization.json"))
    return stage, SimpleNamespace(authorization=original)


def test_stage_inherits_global_window_and_bounded_reservation(tmp_path):
    stage, shared = auth(tmp_path)
    compare.validate_authorization("a" * 64, stage, shared, tmp_path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("experiment_identity", "old"),
        ("shared_authorization_sha256", "bad"),
        ("max_new_provider_cost_usd", 10),
        ("max_new_provider_cost_usd", 0),
        ("max_new_provider_cost_usd", "NaN"),
        ("candidate_sha256", "bad"),
        ("user_authorized", False),
        ("authorized_at_utc", "2026-10-20T20:00:00Z"),
        ("deadline_utc", "2026-10-22T00:00:00Z"),
    ],
)
def test_new_stage_cannot_reset_time_budget_or_identity(tmp_path, field, value):
    stage, shared = auth(tmp_path)
    stage[field] = value
    with pytest.raises(PlanContractError):
        compare.validate_authorization("a" * 64, stage, shared, tmp_path)
