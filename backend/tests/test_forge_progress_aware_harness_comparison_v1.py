from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_progress_aware_harness_comparison_v1.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("forge_progress_aware_harness_comparison_v1_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _outcomes(module: ModuleType, manifest: dict, *, h0_success: int, h1_success: int, h0_cost: int, h1_cost: int) -> list[dict]:
    rows = []
    per_treatment_seen = {treatment: 0 for treatment in module.TREATMENTS}
    for block in manifest["formal_schedule"]:
        task = next(item for item in manifest["tasks"] if item["task_id"] == block["task_id"])
        for treatment in module.TREATMENTS:
            per_treatment_seen[treatment] += 1
            limit = h0_success if treatment == module.TREATMENTS[0] else h1_success
            cost = h0_cost if treatment == module.TREATMENTS[0] else h1_cost
            success = per_treatment_seen[treatment] <= limit
            rows.append(
                {
                    "pair_sequence": block["sequence"],
                    "treatment": treatment,
                    "task_id": task["task_id"],
                    "build_system": task["build_system"],
                    "checkpoint_sha256": "a" * 64,
                    "terminal_classification": "strict_success" if success else "evaluated_failure",
                    "strict_success": success,
                    "budget": {"complete": True, "conserved": True, "delta": {"provider_cost_microusd": cost}},
                    "post_action_observation": {"session_status": "completed"},
                    "cleanup_succeeded": True,
                    "error_class": None,
                    "harness_metrics": {"offline_source_bound": True},
                }
            )
    return rows


def test_manifest_freezes_paired_cross_system_schedule_and_budget() -> None:
    module = _load_module()
    manifest = module.validate_manifest(module._manifest(), require_components=False)

    assert len(manifest["tasks"]) == 9
    assert len(manifest["canary_checkpoints"]) == 3
    assert len(manifest["formal_schedule"]) == 27
    assert module._treatment_order(1) == module.TREATMENTS
    assert module._treatment_order(2) == tuple(reversed(module.TREATMENTS))
    assert manifest["budget"]["provider_arms"] == 60
    assert manifest["budget"]["total_recorded_tokens"] == 18_000_000


def test_every_task_binds_an_exact_state_one_source_archive() -> None:
    module = _load_module()
    manifest = module.validate_manifest(module._manifest(), require_components=False)

    for task in manifest["tasks"]:
        source = manifest["source_archives"][task["task_id"]]
        assert source["checkpoint_state_id"].endswith("state-1")
        assert module.base._file_sha256(module._source_archive(manifest, task)) == source["sha256"]


def test_formal_primary_path_requires_noninferiority_cost_and_system_coverage() -> None:
    module = _load_module()
    manifest = module._manifest()
    positive = _outcomes(module, manifest, h0_success=18, h1_success=27, h0_cost=100, h1_cost=50)

    qualified = module._formal_qualification(manifest, positive)

    assert qualified["passed"] is True
    assert qualified["behavior_gates"]["primary_noninferiority_and_cost"] is True
    assert qualified["decision"] == "supports_progress_aware_harness_claim"

    expensive = _outcomes(module, manifest, h0_success=27, h1_success=27, h0_cost=100, h1_cost=100)
    rejected = module._formal_qualification(manifest, expensive)
    assert rejected["passed"] is False
    assert rejected["behavior_gates"]["primary_noninferiority_and_cost"] is False


def test_runtime_dispatch_keeps_h0_and_h1_separate(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    calls: list[str] = []

    async def h0(**_kwargs):
        calls.append("h0")
        return "h0"

    async def h1(**_kwargs):
        calls.append("h1")
        return "h1"

    monkeypatch.setattr(module, "_BASE_RUN_V3", h0)
    monkeypatch.setattr(module.runtime_v4, "run_agent_workflow_node_v4", h1)
    module._ACTIVE_TREATMENT = "h0_runtime_v3"
    assert asyncio.run(module._run_node(node_input=SimpleNamespace())) == "h0"
    module._ACTIVE_TREATMENT = "h1_runtime_v4"
    assert asyncio.run(module._run_node(node_input=SimpleNamespace())) == "h1"
    assert calls == ["h0", "h1"]


def test_q1_checks_q0_before_credential_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    manifest = module._manifest()
    credential_checked = False
    monkeypatch.setattr(module, "preflight", lambda _manifest, phase: {"manifest_sha256": "a" * 64, "release_revision": "b" * 40})

    def reject_q0(*_args, **_kwargs):
        raise module.QualificationError("q0 not passed")

    def credential_preflight(_manifest):
        nonlocal credential_checked
        credential_checked = True

    monkeypatch.setattr(module.base, "_require_phase_passed", reject_q0)
    monkeypatch.setattr(module.base, "_provider_preflight", credential_preflight)
    with pytest.raises(module.QualificationError, match="q0 not passed"):
        module.execute_q1(manifest)
    assert credential_checked is False
