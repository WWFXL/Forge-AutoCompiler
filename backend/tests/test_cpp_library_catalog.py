"""固定来源分母及无源码patch元数据边界。"""

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
catalog = importlib.import_module("forge_build_cpp_library_catalog")


def test_fixed_denominator_and_exposure_name_boundaries():
    items = [dict(id=i, full_name=f"owner/lib-{i}", language="C++", archived=False, fork=False, stargazers_count=5000 - i, topics=["cpp-library"]) for i in range(20)]
    assert catalog.fixed_items(dict(items=items, incomplete_results=False)) == items
    with pytest.raises(ValueError):
        catalog.fixed_items(dict(items=items[:-1], incomplete_results=False))
    duplicate = items[:-1] + [items[0]]
    with pytest.raises(ValueError):
        catalog.fixed_items(dict(items=duplicate, incomplete_results=False))
    assert catalog.name_matches("owner/lib", "https://github.com/OWNER/lib.git")
    assert not catalog.name_matches("owner/lib", "https://github.com/owner/library")
    assert not catalog.name_matches("owner/lib", "xowner/lib")


def test_metadata_uses_git_objects_without_patch_or_blob(monkeypatch, tmp_path):
    calls = []
    commit = "a" * 40
    tree = "b" * 40

    def fake_api(arguments, output, protocol):
        calls.append(arguments[0])
        if "/git/ref/" in arguments[0]:
            return {"object": {"type": "commit", "sha": commit}}
        if "/git/commits/" in arguments[0]:
            return {"sha": commit, "tree": {"sha": tree}}
        return {"sha": tree, "truncated": False, "tree": [{"path": "CMakeLists.txt", "type": "blob", "mode": "100644", "sha": "c" * 40}]}

    monkeypatch.setattr(catalog, "api", fake_api)
    result = catalog.metadata({"full_name": "owner/lib", "default_branch": "main"}, tmp_path, {})
    assert calls == ["repos/owner/lib/git/ref/heads/main", f"repos/owner/lib/git/commits/{commit}", f"repos/owner/lib/git/trees/{tree}"]
    assert result["candidate_build_systems"] == ["cmake"]
    assert result["task_qualified"] is False
    assert result["build_result"] == "not_observed"
