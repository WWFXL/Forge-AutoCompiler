from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_dynamic_budget_trajectory_qualification_v2.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("forge_dynamic_budget_trajectory_qualification_v2", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def configured() -> ModuleType:
    return _load_module().configure_module()


def test_v2_has_independent_identity_and_evidence_root(configured: ModuleType) -> None:
    manifest = configured.validate_manifest(configured._load_json(configured.MANIFEST_PATH))

    assert manifest["identity"] == "cpp-dynamic-budget-trajectory-benchmark-qualification-v2"
    assert manifest["evidence_root"].endswith("qualification-v2")
    assert configured.REPORT_JSON_PATH.name.endswith("qualification-v2.json")


def test_v2_ignores_only_frozen_diagnostic_file_names(configured: ModuleType, tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    for root in (first, second):
        (root / "build/CMakeFiles").mkdir(parents=True)
        (root / "build/result.a").write_text("stable", encoding="utf-8")
    (first / "build/CMakeFiles/CMakeConfigureLog.yaml").write_text("TryCompile-AAAA", encoding="utf-8")
    (second / "build/CMakeFiles/CMakeConfigureLog.yaml").write_text("TryCompile-BBBB", encoding="utf-8")

    assert configured._tree_sha256(first) == configured._tree_sha256(second)

    (second / "build/result.a").write_text("changed", encoding="utf-8")
    assert configured._tree_sha256(first) != configured._tree_sha256(second)


def test_v2_does_not_ignore_similarly_named_files(configured: ModuleType, tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "config.log.saved").write_text("one", encoding="utf-8")
    (second / "config.log.saved").write_text("two", encoding="utf-8")

    assert configured._tree_sha256(first) != configured._tree_sha256(second)


def test_v2_still_freezes_zero_provider_schedule(configured: ModuleType) -> None:
    manifest = configured.validate_manifest(configured._load_json(configured.MANIFEST_PATH))
    plan = configured._plan(manifest)

    assert plan["projects"] == 9
    assert plan["states"] == 27
    assert plan["continuations"] == 54
    assert plan["provider_requests"] == 0
