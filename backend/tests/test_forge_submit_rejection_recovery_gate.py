from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
SCRIPT_PATH = SCRIPTS_ROOT / "forge_submit_rejection_recovery_gate.py"


def _load_module() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS_ROOT))
    try:
        spec = importlib.util.spec_from_file_location("forge_submit_rejection_recovery_gate", SCRIPT_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS_ROOT))


def test_manifest_and_parent_inventory_are_valid() -> None:
    module = _load_module()

    manifest = module.validate_manifest(require_frozen=False)
    parent = module.audit_parent_evidence()

    assert manifest["identity"] == module.IDENTITY
    assert parent["valid"] is True
    assert parent["inventory_canonical_sha256"] == module.PARENT_INVENTORY_SHA256


def test_v5_deadlock_reproduction_observes_post_submit_frontier_drift() -> None:
    module = _load_module()

    result = module.reproduce_v5_deadlock()

    assert result["passed"] is True
    assert result["command_count_after"] == result["command_count_before"] + 1
    assert result["pre_submit_frontier_sha256"] != result["post_submit_frontier_sha256"]
    assert result["repair_guard_reason"] == "candidate_ready_requires_submit"
    assert result["provider_requests"] == result["credential_reads"] == 0


def test_report_preserves_engineering_claim_boundary() -> None:
    module = _load_module()
    source = Path(module.SCRIPT_PATH).read_text(encoding="utf-8")

    assert "zero-provider engineering recovery gate; no treatment effect" in source
    assert "不估计 H2 对严格成功率" in source
