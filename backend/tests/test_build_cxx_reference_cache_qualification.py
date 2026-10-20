"""类型修复身份不能借机改变作者测试或其他动作。"""

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("cxx_cache", ROOT / "scripts/forge_build_cxx_reference_cache_qualification.py")
cache = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cache)


@pytest.fixture
def protocol(monkeypatch, tmp_path):
    original = json.loads((ROOT / "benchmarks/manifests/cpp-build-cxx-reference-qualification-v1.json").read_text())
    (tmp_path / "protocol.json").write_text(json.dumps(original))
    settings = copy.deepcopy(original)
    settings.update(identity="cpp-build-cxx-reference-cache-qualification-v1", parent_evidence=str(tmp_path), parent_inventory_sha256="parent", components={}, projects=[cache.revised_project(original)])
    item = settings["projects"][0]
    hashes = {item["source_archive"]: item["plan"]["source_archive_sha256"], item["source_file_hashes_path"]: item["source_file_hashes_sha256"]}
    monkeypatch.setattr(cache, "digest", lambda path: hashes[str(path)])
    monkeypatch.setattr(cache, "audit", lambda *args: {"inventory_canonical_sha256": "parent"})
    monkeypatch.setattr(cache, "before_deadline", lambda *args: None)
    return settings


def test_valid_type_only_revision_keeps_parent_and_tests(protocol):
    cache.validate(protocol)
    parent = json.loads((Path(protocol["parent_evidence"]) / "protocol.json").read_text())
    old = next(p for p in parent["projects"] if p["name"] == "simdutf")
    assert old["plan"]["steps"][1]["command"].count("-DBUILD_SHARED_LIBS=OFF") == 1
    assert protocol["projects"][0]["plan"]["steps"][3] == old["plan"]["steps"][3]


@pytest.mark.parametrize("role", ["dependency", "build", "smoke", "artifact_stage"])
def test_rejects_any_other_command_change(protocol, role):
    next(s for s in protocol["projects"][0]["plan"]["steps"] if s["role"] == role)["command"] = "true"
    with pytest.raises(ValueError, match="唯一缓存"):
        cache.validate(protocol)


def test_cannot_extend_deadline(protocol):
    protocol["deadline_utc"] = "2099-01-01T00:00:00Z"
    with pytest.raises(ValueError, match="截止"):
        cache.validate(protocol)
