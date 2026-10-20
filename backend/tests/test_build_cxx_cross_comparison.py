"""跨系统共享接线、人工参考隔离与顺序平衡。"""

import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_cxx_cross_comparison as compare  # noqa: E402

from deerflow.compile.plan_workflow import PlanContractError


def test_each_project_has_three_methods_once_at_each_position():
    rows = compare.schedule()
    assert len(rows) == 18 and len(compare.gate_schedule()) == 6
    for project in compare.PROJECTS:
        blocks = [[r["method"] for r in rows if r["project"] == project and r["repetition"] == n] for n in (1, 2, 3)]
        for pos in range(3):
            assert Counter(b[pos] for b in blocks) == {m: 1 for m in compare.METHODS}


@pytest.mark.parametrize("method", compare.METHODS)
def test_real_methods_use_shared_meter_model_and_no_reference(tmp_path, monkeypatch, method):
    seen = {}

    def factory(source, *, generator):
        seen.update(source=source, generator=generator)
        return lambda **kw: seen.update(planner_model=kw["model"])

    monkeypatch.setattr(compare, "observed_planner", factory)
    monkeypatch.setattr(compare, "run_tool_agent_automatic", lambda **kw: seen.update(tool_model=kw["model"]))

    def execute(**kw):
        seen.update(kw)
        if kw["arm"] == "plan":
            kw["planner"](model="wrong")
        else:
            kw["tool_runner"](model="wrong")
        return {}

    compare.slot_runner(protocol={}, root=tmp_path, slot={"method": method}, item={}, model="shared", executor=execute)
    assert seen["reference"] is None and seen["model"] == "shared"
    assert seen["meter_factory"] is compare.ReferencedStrategyMeter
    assert seen.get("planner_model", seen.get("tool_model")) == "shared"
    assert seen["command_timeout_seconds"] == 600 and seen["replay_timeout_seconds"] == 900
    assert seen["generator"] is compare.selected_make_actions


@pytest.mark.parametrize("qualify,reference", [(False, {}), (True, None)])
def test_cannot_leak_reference_into_real_mode_or_skip_qualification_reference(tmp_path, qualify, reference):
    with pytest.raises(PlanContractError):
        compare.slot_runner(protocol={}, root=tmp_path, slot={"method": compare.METHODS[0]}, item={}, qualify=qualify, reference=reference)


def test_fixed_verification_is_copied_without_reference_commands():
    import json

    root = Path(__file__).resolve().parents[2]
    p = json.loads((root / "benchmarks/manifests/cpp-build-cxx-cross-system-reference-header-v1.json").read_text())["projects"][0]
    project, reference = compare.make_project(p)
    assert project["task"]["verification_steps"] == [s for s in p["plan"]["steps"] if s["role"] == "smoke"]
    assert not any(s["step_id"] == "forge-source-prepare" for s in reference["steps"])
    assert "steps" not in project["task"] and "reference" not in project
