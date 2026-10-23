"""新库任务不能通过修改比较侧测试义务获得准入。"""

import copy
import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
comparison = importlib.import_module("forge_build_library_comparison")


def test_comparison_rejects_test_obligation_drift(monkeypatch):
    candidate = comparison.base.load(ROOT / "benchmarks/manifests/cpp-build-library-strategy-comparison-v1.json")
    candidate = copy.deepcopy(candidate)
    record = candidate["qualification_evidence"][0]
    original_task = copy.deepcopy(candidate["projects"][0]["task"])
    candidate["projects"][0]["task"]["verification_steps"] = []
    monkeypatch.setattr(comparison, "audit", lambda root: {"inventory_canonical_sha256": record["inventory_sha256"]})
    original_load = comparison.base.load

    def load(path):
        if path.name == "result.json":
            return {"qualified": True}
        if path.name == "protocol.json":
            return {"projects": [{"name": record["name"], "task": original_task, "source_archive": candidate["projects"][0]["source_archive"]}]}
        return original_load(path)

    monkeypatch.setattr(comparison.base, "load", load)
    with pytest.raises(comparison.base.PlanContractError, match="原任务或测试交付变化"):
        comparison.validate(candidate)
