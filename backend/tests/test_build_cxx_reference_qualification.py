"""新增C++资格的来源图、候选与零Provider边界。"""

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("cxx_reference", ROOT / "scripts/forge_build_cxx_reference_qualification.py")
cxx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cxx)


@pytest.fixture
def protocol(monkeypatch):
    monkeypatch.setattr(cxx, "require_time", lambda *args: None)
    monkeypatch.setattr(cxx, "audit", lambda *args: {"inventory_canonical_sha256": "parent"})
    return {
        "identity": "cpp-build-cxx-reference-inputs-v1",
        "provider_calls": 0,
        "credentials_read": False,
        "deadline_utc": "2099-01-01T00:00:00Z",
        "components": {},
        "parent_evidence": "unused",
        "parent_inventory_sha256": "parent",
        "candidates": [{"repository": name} for name in cxx.REPOSITORIES],
    }


@pytest.mark.parametrize("field,value", [("identity", "old-identity"), ("provider_calls", 1), ("credentials_read", True)])
def test_rejects_wrong_identity_or_provider_boundary(protocol, field, value):
    protocol[field] = value
    with pytest.raises(ValueError, match="边界"):
        cxx.validate(protocol, "prepare")


def test_rejects_changed_parent_inventory(protocol):
    protocol["parent_inventory_sha256"] = "changed"
    with pytest.raises(ValueError, match="父证据"):
        cxx.validate(protocol, "prepare")


def test_does_not_allow_dropping_or_replacing_candidate(protocol):
    parent = copy.deepcopy(protocol)
    protocol["candidates"].pop()
    with pytest.raises(ValueError, match="候选"):
        cxx.validate(protocol, "prepare")
    assert len(parent["candidates"]) == 3


def test_undeclared_gitlink_rejected_before_extract_or_download(protocol, monkeypatch, tmp_path):
    source = tmp_path / "sources" / "jbeder--yaml-cpp"
    source.mkdir(parents=True)
    (source / "head.json").write_text(json.dumps({"commit_sha": "a" * 40}))
    protocol["parent_evidence"] = str(source.parent)
    protocol["candidates"] = [{"name": "yaml-cpp", "repository": "jbeder/yaml-cpp", "dependencies": []}]

    class Response:
        stdout = json.dumps({"tree": [{"mode": "160000", "path": "third_party/missing", "sha": "b" * 40}]}).encode()

    monkeypatch.setattr(cxx.subprocess, "run", lambda *args, **kwargs: Response())
    monkeypatch.setattr(cxx, "normalized_source", lambda *args: pytest.fail("不应解包未闭合来源图"))
    output = tmp_path / "out"
    output.mkdir()
    rows = []
    with pytest.raises(ValueError, match="gitlink"):
        cxx.prepare(protocol, output, rows)
    assert rows == [] and not (output / "yaml-cpp" / "source.tar").exists()


def test_partial_preparation_keeps_completed_rows(protocol, monkeypatch, tmp_path):
    source = tmp_path / "sources" / "jbeder--yaml-cpp"
    source.mkdir(parents=True)
    (source / "head.json").write_text(json.dumps({"commit_sha": "a" * 40}))
    protocol["parent_evidence"] = str(source.parent)
    protocol["candidates"] = [{"name": "yaml-cpp", "repository": "jbeder/yaml-cpp", "dependencies": []}]
    monkeypatch.setattr(cxx.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError()))
    output = tmp_path / "out"
    output.mkdir()
    rows = [{"name": "already_observed"}]
    with pytest.raises(TimeoutError):
        cxx.prepare(protocol, output, rows)
    assert rows == [{"name": "already_observed"}]
