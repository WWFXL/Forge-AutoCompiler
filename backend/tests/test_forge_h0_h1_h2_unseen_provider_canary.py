"""Issue #447 未见项目族 H0/H1/H2 Provider canary 测试。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_h0_h1_h2_unseen_provider_canary.py"


def _load_module() -> ModuleType:
    name = "forge_h0_h1_h2_unseen_provider_canary_test"
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


def _outcome(task_id: str, treatment: str, *, closure_events: int = 0) -> dict:
    return {
        "task_id": task_id,
        "treatment": treatment,
        "terminal_classification": "strict_success",
        "strict_success": True,
        "candidate_submitted": True,
        "layers": [{"layer": index} for index in range(6)],
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
            "replay_closure_events": closure_events,
            "replay_closure_rejections": 0,
        },
        "duration_milliseconds": 1000,
    }


def _qualified_outcomes(module: ModuleType, manifest: dict) -> list[dict]:
    values = []
    for row in manifest["schedule"]:
        values.append(
            _outcome(
                row["task_id"],
                row["treatment"],
                closure_events=1 if row["treatment"] == "h2_runtime_v5" and not any(item["treatment"] == "h2_runtime_v5" for item in values) else 0,
            )
        )
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


def test_schedule_is_balanced_latin_rotation() -> None:
    module = _load_module()
    manifest = module.generate_manifest()

    assert [(row["task_id"], row["treatment"]) for row in manifest["schedule"]] == [
        ("cmake-tinyxml2", "h0_runtime_v3"),
        ("cmake-tinyxml2", "h1_runtime_v4"),
        ("cmake-tinyxml2", "h2_runtime_v5"),
        ("make-mjson", "h1_runtime_v4"),
        ("make-mjson", "h2_runtime_v5"),
        ("make-mjson", "h0_runtime_v3"),
        ("autotools-libcsv", "h2_runtime_v5"),
        ("autotools-libcsv", "h0_runtime_v3"),
        ("autotools-libcsv", "h1_runtime_v4"),
    ]
    assert {row["treatment"] for row in manifest["schedule"]} == set(module.TREATMENTS)


def test_budget_and_provider_authorization_are_bounded() -> None:
    module = _load_module()
    manifest = module.generate_manifest()
    budget = manifest["budget"]

    assert budget["per_arm"]["max_recorded_tokens"] == 600_000
    assert budget["per_arm"]["authorized_recorded_tokens_per_arm"] == 700_000
    assert budget["total_provider_requests"] == 324
    assert budget["total_recorded_tokens_stop_threshold"] == 5_400_000
    assert budget["total_authorized_recorded_tokens"] == 6_300_000
    assert budget["total_provider_cost_usd_ceiling"] == 7.56
    assert manifest["qualification"]["canary_enters_effect_estimate"] is False


def test_qualification_requires_usage_instrumentation_and_h2_closure() -> None:
    module = _load_module()
    manifest = module.generate_manifest()
    outcomes = _qualified_outcomes(module, manifest)

    qualified = module._qualification(manifest, outcomes)
    assert qualified["passed"] is True
    assert all(qualified["hard_gates"].values())
    assert qualified["decision"] == "proceed_to_unseen_three_arm_formal_comparison_design"

    no_closure = copy.deepcopy(outcomes)
    for item in no_closure:
        item["harness_metrics"]["replay_closure_events"] = 0
    assert module._qualification(manifest, no_closure)["hard_gates"]["h2_replay_closure_exercised"] is False

    bad_usage = copy.deepcopy(outcomes)
    bad_usage[0]["token_accounting"]["requests_usage_incomplete"] = 1
    assert module._qualification(manifest, bad_usage)["hard_gates"]["request_lifecycle_and_usage"] is False


def test_schema_and_validation_reject_schedule_or_budget_drift() -> None:
    module = _load_module()
    manifest = _load(module.MANIFEST_PATH)
    schema = _load(module.SCHEMA_PATH)

    schedule = copy.deepcopy(manifest)
    schedule["schedule"][0]["treatment"] = "h2_runtime_v5"
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(schedule)
    with pytest.raises(module.QualificationError):
        module.validate_manifest(schedule, require_components=False)

    budget = copy.deepcopy(manifest)
    budget["budget"]["total_provider_cost_usd_ceiling"] = 8.0
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(budget)
    with pytest.raises(module.QualificationError):
        module.validate_manifest(budget, require_components=False)


def test_plan_preserves_canary_claim_boundary() -> None:
    module = _load_module()
    planned = module.plan(module.generate_manifest())

    assert len(planned["schedule"]) == 9
    assert planned["provider"] == "deepseek-flash"
    assert planned["provider_recorded_token_ceiling"] == 6_300_000
    assert planned["canary_enters_effect_estimate"] is False
