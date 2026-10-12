from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_dynamic_budget_trajectory_qualification_v4.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("forge_dynamic_budget_trajectory_qualification_v4", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def configured() -> ModuleType:
    return _load_module().configure_module()


def test_v4_has_independent_identity_and_frozen_cache_exclusion(configured: ModuleType) -> None:
    manifest = configured.validate_manifest(configured._load_json(configured.MANIFEST_PATH))

    assert manifest["identity"] == "cpp-dynamic-budget-trajectory-benchmark-qualification-v4"
    assert manifest["evidence_root"].endswith("qualification-v4")
    assert configured.IGNORED_DECISION_TREE_DIR_NAMES == frozenset({"autom4te.cache"})


def test_v4_ignores_autom4te_cache_but_not_other_generated_files(configured: ModuleType, tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    for root in (first, second):
        (root / "autom4te.cache").mkdir(parents=True)
        (root / "config.status").write_text("stable", encoding="utf-8")
    (first / "autom4te.cache/requests").write_text("one", encoding="utf-8")
    (second / "autom4te.cache/requests").write_text("two", encoding="utf-8")

    assert configured._tree_sha256(first) == configured._tree_sha256(second)

    (second / "config.status").write_text("changed", encoding="utf-8")
    assert configured._tree_sha256(first) != configured._tree_sha256(second)


def test_v4_is_final_zero_provider_schedule(configured: ModuleType) -> None:
    manifest = configured.validate_manifest(configured._load_json(configured.MANIFEST_PATH))
    plan = configured._plan(manifest)

    assert plan["projects"] == 9
    assert plan["states"] == 27
    assert plan["continuations"] == 54
    assert plan["provider_requests"] == 0
    assert configured.DETERMINISTIC_HOSTNAME is True
