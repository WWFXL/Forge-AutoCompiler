"""Issue #455 Runtime v6 H0/H1/H2 Provider 正式比较测试。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_h0_h1_h2_runtime_v6_formal_comparison_v2.py"


def _load_module() -> ModuleType:
    name = "forge_h0_h1_h2_runtime_v6_formal_comparison_v2_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _outcome(task_id: str, treatment: str) -> dict:
    return {
        "task_id": task_id,
        "treatment": treatment,
        "terminal_classification": "strict_success",
        "strict_success": True,
        "candidate_submitted": True,
        "layers": [{"layer": f"S{index}", "status": "passed"} for index in range(6)],
        "error_class": None,
        "cleanup_succeeded": True,
        "post_action_observation": {"session_status": "completed"},
        "token_accounting": {
            "complete": True,
            "request_lifecycle_closed": True,
            "requests_started": 1,
            "requests_completed": 1,
            "requests_usage_incomplete": 0,
            "budget_contract_violations": 0,
            "input_tokens": 100,
            "output_tokens": 10,
            "recorded_tokens": 110,
        },
        "node_result": {
            "primary_failure": None,
            "usage": {"model_requests": 1, "recorded_tokens": 110},
        },
        "budget": {
            "complete": True,
            "conserved": True,
            "delta": {
                "provider_requests": 1,
                "input_tokens": 100,
                "output_tokens": 10,
                "provider_cost_microusd": 42,
            },
        },
        "harness_metrics": {
            "offline_source_bound": True,
            "progress_snapshots": 0 if treatment == "h0_runtime_v3" else 1,
            "context_compactions": 0 if treatment == "h0_runtime_v3" else 1,
            "replay_closure_events": 1 if treatment == "h2_runtime_v6" else 0,
            "replay_closure_rejections": 0,
            "repair_windows_opened": 0,
            "repair_permissions_consumed": 0,
            "repair_actions_completed": 0,
            "diagnostic_commands": 0,
        },
        "storage_before": {
            "free_bytes": 40 * 1024**3,
            "minimum_free_bytes": 20 * 1024**3,
            "passed": True,
        },
        "duration_milliseconds": 1000,
    }


def _qualified_outcomes(module: ModuleType, manifest: dict) -> list[dict]:
    values = []
    for row in manifest["schedule"]:
        values.append(_outcome(row["task_id"], row["treatment"]))
    return values


def test_manifest_and_const_schema_are_deterministic() -> None:
    module = _load_module()
    manifest = _load(module.MANIFEST_PATH)
    schema = _load(module.SCHEMA_PATH)

    assert manifest == module.generate_manifest()
    assert schema == module.schema_document(manifest)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    assert module.validate_manifest(manifest) == manifest


def test_schedule_is_balanced_across_two_repetitions() -> None:
    module = _load_module()
    manifest = module.generate_manifest()

    assert [(row["task_id"], row["treatment"], row["repetition"]) for row in manifest["schedule"]] == [
        ("cmake-cmark", "h0_runtime_v3", 1),
        ("cmake-cmark", "h1_runtime_v4", 1),
        ("cmake-cmark", "h2_runtime_v6", 1),
        ("make-mpc", "h1_runtime_v4", 1),
        ("make-mpc", "h2_runtime_v6", 1),
        ("make-mpc", "h0_runtime_v3", 1),
        ("autotools-expat", "h2_runtime_v6", 1),
        ("autotools-expat", "h0_runtime_v3", 1),
        ("autotools-expat", "h1_runtime_v4", 1),
        ("cmake-cmark", "h2_runtime_v6", 2),
        ("cmake-cmark", "h1_runtime_v4", 2),
        ("cmake-cmark", "h0_runtime_v3", 2),
        ("make-mpc", "h0_runtime_v3", 2),
        ("make-mpc", "h2_runtime_v6", 2),
        ("make-mpc", "h1_runtime_v4", 2),
        ("autotools-expat", "h1_runtime_v4", 2),
        ("autotools-expat", "h0_runtime_v3", 2),
        ("autotools-expat", "h2_runtime_v6", 2),
    ]
    assert {row["treatment"] for row in manifest["schedule"]} == set(module.TREATMENTS)


def test_budget_and_provider_authorization_are_bounded() -> None:
    module = _load_module()
    manifest = module.generate_manifest()
    budget = manifest["budget"]

    assert budget["per_arm"]["max_recorded_tokens"] == 600_000
    assert budget["per_arm"]["authorized_recorded_tokens_per_arm"] == 700_000
    assert budget["total_provider_requests"] == 648
    assert budget["total_recorded_tokens_stop_threshold"] == 10_800_000
    assert budget["total_authorized_recorded_tokens"] == 12_600_000
    assert budget["total_provider_cost_usd_ceiling"] == 15.12
    assert manifest["analysis"]["noninferiority_margin"] == -0.10
    assert manifest["storage_gate"]["minimum_free_bytes_before_each_arm"] == 20 * 1024**3
    assert manifest["predecessor_failure"]["enters_v2_effect_analysis"] is False


def test_storage_gate_fails_closed_before_arm_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    manifest = module.generate_manifest()
    monkeypatch.setattr(
        module.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(
            total=100 * 1024**3,
            used=85 * 1024**3,
            free=15 * 1024**3,
        ),
    )

    observation = module._storage_observation(manifest, checkpoint="q1-arm-01")
    assert observation["passed"] is False
    with pytest.raises(module.QualificationError, match="宿主存储余量不足"):
        module._require_storage(manifest, checkpoint="q1-arm-01")


def test_formal_analysis_separates_noninferiority_from_mechanism_activation() -> None:
    module = _load_module()
    manifest = module.generate_manifest()
    outcomes = _qualified_outcomes(module, manifest)

    analysis = module._qualification(manifest, outcomes)
    assert analysis["passed"] is True
    assert all(analysis["hard_gates"].values())
    assert analysis["primary_analysis"]["noninferiority_passed"] is True
    assert analysis["mechanism_activation"]["activated"] is False
    assert analysis["decision"] == "runtime_v6_noninferior_but_mechanism_not_activated"

    activated = copy.deepcopy(outcomes)
    h1 = next(item for item in activated if item["treatment"] == "h1_runtime_v4")
    h1["strict_success"] = False
    h1["terminal_classification"] = "evaluated_failure"
    h1["layers"][-1]["status"] = "failed"
    h2 = next(item for item in activated if item["treatment"] == "h2_runtime_v6")
    h2["harness_metrics"].update(
        {
            "replay_closure_rejections": 1,
            "repair_windows_opened": 1,
            "repair_permissions_consumed": 2,
            "repair_actions_completed": 2,
        }
    )
    activated_analysis = module._qualification(manifest, activated)
    assert activated_analysis["mechanism_activation"]["activated"] is True
    assert activated_analysis["decision"] == "supports_runtime_v6_reliability_claim"

    bad_usage = copy.deepcopy(outcomes)
    bad_usage[0]["token_accounting"]["requests_usage_incomplete"] = 1
    assert module._qualification(manifest, bad_usage)["hard_gates"]["request_lifecycle_and_usage"] is False


def test_formal_analysis_rejects_noninferiority_failure() -> None:
    module = _load_module()
    manifest = module.generate_manifest()
    outcomes = _qualified_outcomes(module, manifest)
    for item in outcomes:
        if item["treatment"] == "h2_runtime_v6":
            item["strict_success"] = False
            item["terminal_classification"] = "evaluated_failure"
            item["layers"][-1]["status"] = "failed"

    analysis = module._qualification(manifest, outcomes)
    assert analysis["formal_valid"] is True
    assert analysis["primary_analysis"]["noninferiority_passed"] is False
    assert analysis["decision"] == "reject_runtime_v6_due_to_success_noninferiority"


def test_schema_and_validation_reject_schedule_or_budget_drift() -> None:
    module = _load_module()
    manifest = _load(module.MANIFEST_PATH)
    schema = _load(module.SCHEMA_PATH)

    schedule = copy.deepcopy(manifest)
    schedule["schedule"][0]["treatment"] = "h2_runtime_v6"
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(schedule)
    with pytest.raises(module.QualificationError):
        module.validate_manifest(schedule, require_components=False)

    budget = copy.deepcopy(manifest)
    budget["budget"]["total_provider_cost_usd_ceiling"] = 16.0
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(budget)
    with pytest.raises(module.QualificationError):
        module.validate_manifest(budget, require_components=False)


def test_plan_exposes_formal_estimand_and_ceiling() -> None:
    module = _load_module()
    planned = module.plan(module.generate_manifest())

    assert len(planned["schedule"]) == 18
    assert planned["provider"] == "deepseek-flash"
    assert planned["provider_recorded_token_ceiling"] == 12_600_000
    assert planned["primary_estimand"] == "strict_success_risk_difference_h2_minus_h1"
    assert planned["noninferiority_margin"] == -0.10
    assert planned["minimum_free_storage_bytes"] == 20 * 1024**3
