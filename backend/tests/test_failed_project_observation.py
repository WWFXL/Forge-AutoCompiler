"""三个已知失败项目的观察范围与旧证据隔离；不连接Provider。"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_failed_project_observation as observation  # noqa: E402
import forge_harness_update_remeasurement as previous  # noqa: E402


def test_subset_keeps_original_tasks_and_updated_harness():
    current = observation.candidate()
    original = previous.runner().shared.load(previous.runner().FIXTURE)
    by_name = {p["name"]: p for p in original["projects"]}
    assert current["projects"] == [by_name[n] for n in observation.PROJECTS]
    assert [(r["project"], r["method"]) for r in current["schedule"]] == [(n, "LH_v1") for n in observation.PROJECTS]
    assert current["recipe_reuse"] is False and current["experience_bank"] is None
    assert current["known_solution_injection"] is False
    observation.validate(current, check_sources=False)
    assert previous.runner().IDENTITY != current["identity"]
    assert len(previous.runner().schedule()) == 36


def test_missing_authorization_stops_before_credentials(monkeypatch):
    monkeypatch.setattr(observation, "validate", lambda value: None)
    monkeypatch.setattr(sys, "argv", ["observation", "--run"])
    with pytest.raises(ValueError, match="新授权"):
        observation.main()


def test_three_project_denominator_keeps_unobserved(tmp_path):
    shared = observation.runtime().shared
    shared.save(tmp_path / "result.json", dict(rows=[], unobserved=observation.candidate()["schedule"], unclosed_slot=None, billing_complete=True, closed_slot_cost_usd="0"))
    value = observation.analyze(tmp_path)
    assert list(value["arms"]) == ["LH_v1"]
    assert value["arms"]["LH_v1"]["planned"] == value["arms"]["LH_v1"]["unobserved"] == 3
    assert value["arms"]["LH_v1"]["main_build_completed"] == 0
    assert len(value["unobserved"]) == 3
    assert json.dumps(value)
