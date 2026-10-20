"""新C++比较的实际接线、参考隔离、授权和固定顺序回归。"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_cxx_comparison as compare

from deerflow.compile.plan_workflow import PlanContractError


def test_six_permutations_and_each_method_position_are_balanced():
    rows = compare.schedule()
    assert len(rows) == 18
    blocks = [rows[i : i + 3] for i in range(0, 18, 3)]
    assert len({tuple(s["method"] for s in b) for b in blocks}) == 6
    assert all(sum(b[pos]["method"] == method for b in blocks) == 2 for method in compare.METHODS for pos in range(3))
    assert [(r["project"], r["method"]) for r in compare.gate_schedule()][-1] == ("snappy", compare.METHODS[2])


@pytest.mark.parametrize("method,arm,source", [(compare.METHODS[0], "plan", "tool"), (compare.METHODS[1], "plan", "model"), (compare.METHODS[2], "tool", "model")])
def test_real_dispatch_uses_prepared_executor_and_equivalent_observed_planner(tmp_path, monkeypatch, method, arm, source):
    seen = {}

    def factory(selected):
        seen["source"] = selected

        def planner(**kwargs):
            seen["planner"] = kwargs

        return planner

    monkeypatch.setattr(compare, "observed_planner", factory)

    def tool_agent(**kwargs):
        seen["tool"] = kwargs

    monkeypatch.setattr(compare, "run_tool_agent_automatic", tool_agent)

    def executor(**kwargs):
        seen.update(kwargs)
        kwargs["planner"](model="ignored")
        kwargs["tool_runner"](model="ignored")
        return {}

    compare.slot_runner(protocol={}, root=tmp_path, slot={"method": method}, item={}, model="real", executor=executor)
    assert seen["source"] == source and seen["arm"] == arm
    assert seen["reference"] is None
    assert seen["planner"]["model"] == seen["tool"]["model"] == "real"
    assert seen["meter_factory"] is compare.StrategyMeter
    assert seen["command_timeout_seconds"] == 600 and seen["replay_timeout_seconds"] == 900
    assert compare.run_arm.__module__ == "forge_build_prepared_arm"


@pytest.mark.parametrize("method,reference,qualify", [("bad", None, False), (compare.METHODS[0], {}, False), (compare.METHODS[2], None, True)])
def test_references_never_enter_real_agent(tmp_path, method, reference, qualify):
    with pytest.raises(PlanContractError):
        compare.slot_runner(protocol={}, root=tmp_path, slot={"method": method}, item={}, reference=reference, qualify=qualify)


def authorization():
    start = datetime.now(UTC) - timedelta(minutes=1)
    return dict(experiment_identity=compare.IDENTITY, candidate_sha256="a" * 64, user_authorized=True, max_new_provider_cost_usd=20, authorized_at_utc=start.isoformat(), deadline_utc=(start + timedelta(hours=4)).isoformat())


@pytest.mark.parametrize(
    "field,value",
    [
        ("experiment_identity", "old"),
        ("candidate_sha256", "wrong"),
        ("user_authorized", False),
        ("max_new_provider_cost_usd", 21),
        ("max_new_provider_cost_usd", 0),
        ("max_new_provider_cost_usd", "NaN"),
        ("deadline_utc", (datetime.now(UTC) + timedelta(hours=5)).isoformat()),
    ],
)
def test_authorization_cannot_reset_identity_budget_or_deadline(field, value):
    auth = authorization()
    auth[field] = value
    with pytest.raises(PlanContractError):
        compare.validate_authorization("a" * 64, auth)


def test_valid_authorization_and_missing_authorization_before_credentials(tmp_path, monkeypatch):
    compare.validate_authorization("a" * 64, authorization())
    candidate = tmp_path / "candidate.json"
    candidate.write_text(json.dumps({}))
    monkeypatch.setattr(compare, "validate", lambda c: None)
    monkeypatch.setattr(compare, "require_gate", lambda c: None)
    monkeypatch.setattr(sys, "argv", ["compare", "--candidate", str(candidate), "--output-root", str(tmp_path / "raw")])

    def forbidden(*args, **kwargs):
        pytest.fail("不能在授权前读取凭据")

    monkeypatch.setattr(compare, "os", SimpleNamespace(environ=SimpleNamespace(get=forbidden)))
    with pytest.raises(PlanContractError):
        compare.main()
    assert not (tmp_path / "raw").exists()
