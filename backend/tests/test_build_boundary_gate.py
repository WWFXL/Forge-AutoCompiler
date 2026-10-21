"""共同策略入口与固定边界传递；端到端另由真实Docker资格验证。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_boundary_gate as gate  # noqa: E402


def test_schedule_keeps_all_three_methods_and_two_recoveries():
    rows = gate.schedule()
    assert [r["method"] for r in rows[:3]] == list(gate.METHODS)
    assert [r["method"] for r in rows[3:]] == list(gate.METHODS[:2])


@pytest.mark.parametrize("method", gate.METHODS)
def test_normal_slot_passes_same_boundary_and_keeps_reference_qualification_only(tmp_path, monkeypatch, method):
    item, ref, seen = {"file_boundary": {"fixed": True}}, {}, {}
    monkeypatch.setattr(gate, "normal_slot", lambda **kw: seen.update(kw) or {"ok": True})
    runner = object()
    result = gate.run_slot({"project": item, "reference": ref}, tmp_path, {"method": method, "case": "normal"}, executor=runner)
    assert result == {"ok": True}
    assert seen["item"] is item and seen["reference"] is ref and seen["executor"] is runner
    assert seen["qualify"] is True
