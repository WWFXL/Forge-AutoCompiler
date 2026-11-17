"""统一基座完整比较保留两组差异和原36槽，不连接Provider。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_harness_update_remeasurement as previous  # noqa: E402
import forge_unified_base_harness_comparison as current  # noqa: E402


def test_same_tasks_harnesses_and_schedule_on_new_identity():
    old, new = previous.runner(), current.runner()
    expected, value = old.candidate(), new.candidate()
    for key in ("projects", "schedule", "arm_options", "recovery_harnesses", "provider"):
        assert value[key] == expected[key]
    assert value["identity"] != expected["identity"]
    assert value["recipe_reuse"] is False and value["experience_bank"] is None
    assert value["known_solution_injection"] is False
    assert len(value["schedule"]) == 36
    assert len(value["projects"]) == 18
    new.validate(value, check_sources=False)


def test_no_authorization_stops_before_credentials(monkeypatch):
    module = current.runner()
    monkeypatch.setattr(module, "validate", lambda value: None)
    monkeypatch.setattr(sys, "argv", ["comparison", "--run"])
    with pytest.raises(ValueError, match="有效授权"):
        module.main()


def test_all_18_denominators_preserve_unobserved(tmp_path):
    module = current.runner()
    module.save(tmp_path / "result.json", dict(rows=[], unobserved=module.schedule(), unclosed_slot=None, billing_complete=True, closed_slot_cost_usd="0"))
    value = module.analyze(tmp_path)
    assert value["identity"] == current.IDENTITY
    assert len(value["unobserved"]) == 36
    assert all(a["planned"] == a["unobserved"] == 18 for a in value["arms"].values())
