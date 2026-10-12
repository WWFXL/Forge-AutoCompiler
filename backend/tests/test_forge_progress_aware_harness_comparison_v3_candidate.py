"""Issue #438 H0/H1 v3 未授权确认性复现 candidate 测试。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_progress_aware_harness_comparison_v3_candidate.py"


def _load_module() -> ModuleType:
    name = "forge_progress_aware_harness_comparison_v3_candidate_test"
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


def test_manifest_and_const_schema_are_deterministic() -> None:
    module = _load_module()
    manifest = _load(module.MANIFEST_PATH)
    schema = _load(module.SCHEMA_PATH)

    assert manifest == module.generate_manifest()
    assert schema == module.schema_document(manifest)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    assert module.validate_manifest(manifest) == manifest


def test_v3_uses_new_cross_depth_checkpoints_without_changing_tasks() -> None:
    module = _load_module()
    manifest = module.validate_manifest(_load(module.MANIFEST_PATH))
    parent = module._parent_manifest()
    observed = module._observed_v2_effect_checkpoints()

    formal = {task["checkpoint_state_id"] for task in manifest["tasks"]}
    canary = {item["checkpoint_state_id"] for item in manifest["canary_checkpoints"]}
    assert formal.isdisjoint(observed)
    assert canary.isdisjoint(observed)
    assert formal.isdisjoint(canary)
    assert manifest["replication"]["formal_effect_checkpoints_reused_from_v2"] == 0
    assert manifest["replication"]["project_families_reused"] == 9

    expected_depths = {1: 3, 2: 1, 3: 2}
    for task, parent_task in zip(manifest["tasks"], parent["tasks"], strict=True):
        assert task["task_id"] == parent_task["task_id"]
        assert module._state_depth(task["checkpoint_state_id"]) == expected_depths[module._state_depth(parent_task["checkpoint_state_id"])]
    for build_system in ("cmake", "make", "autotools"):
        depths = Counter(module._state_depth(task["checkpoint_state_id"]) for task in manifest["tasks"] if task["build_system"] == build_system)
        assert depths == Counter({1: 1, 2: 1, 3: 1})


def test_candidate_discloses_v2_and_imports_no_historical_effect() -> None:
    module = _load_module()
    manifest = module.validate_manifest(_load(module.MANIFEST_PATH))
    replication = manifest["replication"]

    assert manifest["observed_parent"]["result_observed_before_v3_design"] is True
    assert manifest["observed_parent"]["decision"] == "stop_progress_aware_harness_as_primary_mechanism"
    assert replication["classification"] == "post_observation_same_project_cross_state_confirmatory_replication"
    assert replication["historical_outcomes_imported"] is False
    assert replication["historical_effect_estimates_pooled"] is False
    assert replication["v2_observed_summary"]["h0_strict"] == 16
    assert replication["v2_observed_summary"]["h1_strict"] == 22
    assert replication["unseen_project_generalization"] is False


def test_candidate_freezes_bounded_token_contract_without_authorization() -> None:
    module = _load_module()
    manifest = module.validate_manifest(_load(module.MANIFEST_PATH))
    per_arm = manifest["budget"]["per_arm"]

    assert per_arm["max_recorded_tokens"] == 300_000
    assert per_arm["max_recorded_tokens_per_response"] == 100_000
    assert manifest["budget"]["provider_arms"] == 60
    assert manifest["budget"]["total_recorded_tokens_stop_threshold"] == 18_000_000
    assert manifest["budget"]["total_authorized_recorded_tokens"] == 24_000_000
    assert manifest["budget"]["total_provider_cost_usd_ceiling"] == 28.8
    assert manifest["authorization"]["model_tokens_authorized"] == 0
    assert all(value is False for key, value in manifest["authorization"].items() if key.endswith("_authorized") and key != "model_tokens_authorized")


def test_schema_and_protocol_reject_authorization_or_sample_drift() -> None:
    module = _load_module()
    manifest = _load(module.MANIFEST_PATH)
    schema = _load(module.SCHEMA_PATH)

    authorized = copy.deepcopy(manifest)
    authorized["authorization"]["provider_calls_authorized"] = True
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(authorized)
    with pytest.raises(module.CandidateError):
        module.validate_manifest(authorized)

    reused = copy.deepcopy(manifest)
    reused["tasks"][0]["checkpoint_state_id"] = "cmake-spdlog-state-1"
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(reused)
    with pytest.raises(module.CandidateError):
        module.validate_manifest(reused)


def test_candidate_has_no_provider_docker_or_credential_execution_path() -> None:
    module = _load_module()
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "create_chat_model",
        "docker.from_env",
        "subprocess.run",
        "requests.",
        "httpx.",
        "os.environ",
        "api_key=",
    ):
        assert forbidden not in source

    gate = module.validate_static_gate(verify_inventory_files=False)
    assert gate["status"] == "passed"
    assert gate["v2_effect_checkpoint_overlap"] == 0
    assert gate["depths_by_build_system"] == {
        "autotools": [1, 2, 3],
        "cmake": [1, 2, 3],
        "make": [1, 2, 3],
    }
    assert (
        gate["provider_calls"],
        gate["credential_read"],
        gate["docker_executed"],
        gate["formal_attempts"],
        gate["model_tokens"],
        gate["evidence_writes"],
    ) == (0, False, False, 0, 0, 0)
