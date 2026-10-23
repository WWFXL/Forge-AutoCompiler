"""关闭恢复必须在Provider调用前终止，并保留同一初始规划路径。"""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
ablation = importlib.import_module("forge_build_recovery_ablation")


def test_recovery_toggle_preserves_initial_route_and_blocks_disabled_agent(monkeypatch):
    calls, events = [], []

    def factory(source, **kwargs):
        def planner(**values):
            calls.append(values.get("current_plan"))
            return "same-initial-plan" if values.get("current_plan") is None else "repaired-plan"
        return planner

    monkeypatch.setattr(ablation, "ORIGINAL_FACTORY", factory)
    meter = SimpleNamespace(ledger=SimpleNamespace(append=lambda *a, **k: events.append((a, k))))
    disabled = ablation.planner_factory(False)("tool")
    enabled = ablation.planner_factory(True)("tool")
    assert disabled(meter=meter) == enabled(meter=meter) == "same-initial-plan"
    plan = SimpleNamespace(fingerprint=lambda: "frozen-initial-fingerprint")
    with pytest.raises(ablation.base.PlanContractError, match="ablation_stop_on_first_failure"):
        disabled(meter=meter, current_plan=plan, handoff={"step_id": "build"})
    assert len(calls) == 2 and events[0][0] == ("ablation.recovery_disabled",)
    assert enabled(meter=meter, current_plan=plan, handoff={"step_id": "build"}) == "repaired-plan"
