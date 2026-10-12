from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_dynamic_budget_trajectory_qualification_v3.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("forge_dynamic_budget_trajectory_qualification_v3", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def configured() -> ModuleType:
    return _load_module().configure_module()


def test_v3_has_independent_identity_and_deterministic_hostname(configured: ModuleType) -> None:
    manifest = configured.validate_manifest(configured._load_json(configured.MANIFEST_PATH))

    assert manifest["identity"] == "cpp-dynamic-budget-trajectory-benchmark-qualification-v3"
    assert manifest["evidence_root"].endswith("qualification-v3")
    assert configured.DETERMINISTIC_HOSTNAME is True


def test_v3_inherits_v2_semantic_tree_rule(configured: ModuleType, tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    for root in (first, second):
        (root / "build/CMakeFiles").mkdir(parents=True)
        (root / "stable").write_text("same", encoding="utf-8")
    (first / "build/CMakeFiles/CMakeConfigureLog.yaml").write_text("one", encoding="utf-8")
    (second / "build/CMakeFiles/CMakeConfigureLog.yaml").write_text("two", encoding="utf-8")

    assert configured._tree_sha256(first) == configured._tree_sha256(second)


def test_v3_schedule_and_provider_boundary_are_unchanged(configured: ModuleType) -> None:
    manifest = configured.validate_manifest(configured._load_json(configured.MANIFEST_PATH))
    plan = configured._plan(manifest)

    assert plan["states"] == 27
    assert plan["continuations"] == 54
    assert plan["provider_requests"] == 0
