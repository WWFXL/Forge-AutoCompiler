from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_dynamic_budget_trajectory_qualification_v5.py"
V4_MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-dynamic-budget-trajectory-benchmark-qualification-v4.json"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("forge_dynamic_budget_trajectory_qualification_v5", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def configured() -> ModuleType:
    return _load_module().configure_module()


def test_v5_binds_new_identity_and_preserves_frozen_schedule(
    configured: ModuleType,
) -> None:
    manifest = configured.validate_manifest(configured._load_json(configured.MANIFEST_PATH))
    v4 = json.loads(V4_MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["identity"] == "cpp-dynamic-budget-trajectory-benchmark-qualification-v5"
    assert manifest["issue"] == 427
    assert manifest["implementation_revision"] == "30deeff6"
    assert manifest["evidence_root"].endswith("qualification-v5")
    for field in (
        "image",
        "authorization",
        "repetitions_per_state",
        "states_per_project",
        "shared_block_budget",
        "allocation",
        "projects",
        "qualification",
    ):
        assert manifest[field] == v4[field]


def test_v5_rejects_tracking_issue_drift(configured: ModuleType) -> None:
    manifest = configured._load_json(configured.MANIFEST_PATH)
    manifest["issue"] = 423

    with pytest.raises(configured.QualificationError, match="tracking issue"):
        configured.validate_manifest(manifest)


def test_v5_uses_symlink_safe_checkpoint_restore(configured: ModuleType, tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "src/.libs").mkdir(parents=True)
    (source / "src/libestr.la").write_text("payload", encoding="utf-8")
    (source / "src/.libs/libestr.la").symlink_to("../libestr.la")
    archive = tmp_path / "checkpoint.tar.gz"
    configured._create_snapshot(source, archive)

    destination = tmp_path / "restored"
    configured._restore_snapshot(archive, destination)

    link = destination / "src/.libs/libestr.la"
    assert link.is_symlink()
    assert os.readlink(link) == "../libestr.la"
    assert configured._tree_sha256(source) == configured._tree_sha256(destination)


def test_v5_keeps_final_zero_provider_gate(configured: ModuleType) -> None:
    manifest = configured.validate_manifest(configured._load_json(configured.MANIFEST_PATH))
    plan = configured._plan(manifest)

    assert plan["projects"] == 9
    assert plan["states"] == 27
    assert plan["continuations"] == 54
    assert plan["credential_read"] is False
    assert plan["provider_requests"] == 0
    assert plan["agent_continuation"] is False
    assert plan["controller_implementation"] is False
    assert configured.DETERMINISTIC_HOSTNAME is True
    assert configured.IGNORED_DECISION_TREE_DIR_NAMES == frozenset({"autom4te.cache"})
