"""独立重复调度完整性与逐项目索引路由。"""

import importlib
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
replication = importlib.import_module("forge_build_strategy_replication")


def test_replication_pairs_and_order_balance():
    slots = replication.schedule()
    assert len(slots) == 36
    assert Counter((s["project"], s["method"]) for s in slots) == {(p, m): 2 for p in replication.PROJECTS for m in replication.base.METHODS}
    orders = Counter(tuple(s["method"] for s in slots[i : i + 3]) for i in range(0, 36, 3))
    assert len(orders) == 6 and set(orders.values()) == {2}
    assert len({(s["project"], s["method"], s["repetition"]) for s in slots}) == 36


def test_source_index_is_selected_by_project(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(replication.indexed, "run_slot", lambda **kw: seen.append(kw) or {"strict_completed": True})
    protocol = {"source_index_contracts": {"a": {"symlinks": {}}, "b": {"symlinks": {"x": "missing"}}}}
    for name in ("b", "a"):
        replication.run_slot(protocol=protocol, slot={"project": name}, root=tmp_path, model=None)
    assert [x["protocol"]["source_index_contract"] for x in seen] == [protocol["source_index_contracts"]["b"], protocol["source_index_contracts"]["a"]]
    assert "source_index_contract" not in protocol
