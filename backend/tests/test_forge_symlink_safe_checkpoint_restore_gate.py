from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
SCRIPT_PATH = SCRIPTS_ROOT / "forge_symlink_safe_checkpoint_restore_gate.py"


def _load_module() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS_ROOT))
    try:
        spec = importlib.util.spec_from_file_location("forge_symlink_safe_checkpoint_restore_gate", SCRIPT_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS_ROOT))


def test_gate_passes_synthetic_attacks_and_v4_read_only_round_trip() -> None:
    module = _load_module()

    report = module.run_gate()

    assert report["status"] == "passed"
    assert report["decision"] == "proceed_to_dynamic_budget_trajectory_qualification_v5_design"
    assert report["summary"] == {
        "passed": 8,
        "total": 8,
        "credential_read": False,
        "provider_requests": 0,
        "v4_evidence_mutated": False,
    }
    v4_case = next(item for item in report["cases"] if item["case"] == "v4_libestr_checkpoint_round_trip")
    assert v4_case["expected_decision_tree_sha256"] == "1e712e8e560e9b8bf3f7f2845df3aac66d7c6103b3bb4e2feb247d8abcd2488f"
    assert v4_case["observed_full_tree_sha256"] == v4_case["expected_full_tree_sha256"]
    assert v4_case["observed_decision_tree_sha256"] == v4_case["expected_decision_tree_sha256"]
    assert v4_case["link_target"] == "../libestr.la"
    assert v4_case["source_mutated"] is False


def test_markdown_keeps_engineering_claim_boundary() -> None:
    module = _load_module()
    report = module.run_gate()

    markdown = module._render_markdown(report)

    assert "工程修复验证" in markdown
    assert "不评价动态预算、Jev、Agent 或 controller 效果" in markdown
    assert "未续跑 v4" in markdown
