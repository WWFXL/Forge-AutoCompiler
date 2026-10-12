from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_progress_aware_harness_comparison_v2.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("forge_progress_aware_harness_comparison_v2_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v2_manifest_binds_sealed_v1_and_keeps_schedule() -> None:
    module = _load_module()
    manifest = module.validate_manifest(module._manifest(), require_components=False)

    assert manifest["remediation_parent"]["decision"] == ("supersede_before_q2_due_to_canary_instrumentation_gap")
    assert len(manifest["formal_schedule"]) == 27
    assert manifest["qualification"]["formal_arms"] == 54


def test_v2_selects_only_main_agent_events() -> None:
    module = _load_module()
    root = REPO_ROOT / module._manifest()["remediation_parent"]["evidence_root"]
    h1_arms = [path.parent for path in sorted((root / "q1/arms").glob("*h1_runtime_v4/result.json"))]

    counts = [sum(event.get("event_type") == "harness.progress_snapshot" for event in module._events(path)) for path in h1_arms]

    assert counts == [5, 6, 7]


def test_v2_canary_gate_requires_treatment_separation() -> None:
    module = _load_module()
    common = {
        "terminal_classification": "strict_success",
        "budget": {"complete": True, "conserved": True},
        "post_action_observation": {"session_status": "completed"},
        "cleanup_succeeded": True,
        "error_class": None,
    }
    h0 = {
        **common,
        "treatment": "h0_runtime_v3",
        "token_accounting": {"requests_completed": 4},
        "harness_metrics": {
            "offline_source_bound": True,
            "progress_snapshots": 0,
            "context_compactions": 0,
        },
    }
    h1 = {
        **common,
        "treatment": "h1_runtime_v4",
        "token_accounting": {"requests_completed": 4},
        "harness_metrics": {
            "offline_source_bound": True,
            "progress_snapshots": 4,
            "context_compactions": 4,
        },
    }

    assert module._arm_complete(h0) is True
    assert module._arm_complete(h1) is True
    h1["harness_metrics"]["progress_snapshots"] = 0
    assert module._arm_complete(h1) is False
