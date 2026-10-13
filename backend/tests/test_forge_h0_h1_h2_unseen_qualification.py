"""Issue #445 未见项目族 H0/H1/H2 零 Provider 资格测试。"""

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
SCRIPT_PATH = REPO_ROOT / "scripts/forge_h0_h1_h2_unseen_qualification.py"


def _load_module() -> ModuleType:
    name = "forge_h0_h1_h2_unseen_qualification_test"
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


def test_unseen_sample_covers_three_build_systems_without_old_families() -> None:
    module = _load_module()
    manifest = module.generate_manifest()
    old_families = {
        "github.com/gabime/spdlog",
        "github.com/cliutils/cli11",
        "github.com/jarro2783/cxxopts",
        "github.com/libtom/libtommath",
        "github.com/kokke/tiny-aes-c",
        "github.com/antirez/kilo",
        "github.com/rsyslog/libestr",
        "github.com/rsyslog/libfastjson",
        "github.com/enki/libev",
    }
    tasks = manifest["tasks"]

    assert {task["build_system"] for task in tasks} == {"cmake", "make", "autotools"}
    assert {task["project_family"] for task in tasks}.isdisjoint(old_families)
    assert len({task["project_family"] for task in tasks}) == 3
    assert all(len(task["commit_sha"]) == 40 for task in tasks)
    assert all(len(task["source_archive"]["sha256"]) == 64 for task in tasks)


def test_budget_is_common_bounded_and_above_observed_h0_tail() -> None:
    module = _load_module()
    manifest = module.generate_manifest()
    budget = manifest["future_common_budget"]
    observed = manifest["observed_basis"]

    assert budget["max_recorded_tokens"] == 600_000
    assert budget["max_recorded_tokens"] > observed["h0_max_recorded_tokens"]
    assert budget["max_recorded_tokens_per_response"] == 100_000
    assert budget["authorized_recorded_tokens_per_arm"] == 700_000
    assert manifest["future_effect_boundary"]["provider_canary_arms"] == 9
    assert manifest["future_effect_boundary"]["planned_formal_arms"] == 18


def test_treatment_dispatch_is_exactly_runtime_v3_v4_v5() -> None:
    module = _load_module()
    manifest = module.generate_manifest()

    assert manifest["treatments"] == {
        "h0": {"id": "h0_runtime_v3", "runtime": "agent-workflow-runtime-v3"},
        "h1": {"id": "h1_runtime_v4", "runtime": "agent-workflow-runtime-v4"},
        "h2": {
            "id": "h2_runtime_v5",
            "runtime": "agent-workflow-runtime-v5",
            "increment_over_h1": "pre_freeze_replay_closure_only",
        },
    }
    assert module.runtime_v3.run_agent_workflow_node_v3.__name__ == "run_agent_workflow_node_v3"
    assert module.runtime_v4.run_agent_workflow_node_v4.__name__ == "run_agent_workflow_node_v4"
    assert module.runtime_v5.run_agent_workflow_node_v5.__name__ == "run_agent_workflow_node_v5"


def test_schema_rejects_provider_or_sample_drift() -> None:
    module = _load_module()
    manifest = _load(module.MANIFEST_PATH)
    schema = _load(module.SCHEMA_PATH)

    provider = copy.deepcopy(manifest)
    provider["authorization"]["provider_calls"] = True
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(provider)
    with pytest.raises(module.QualificationError):
        module.validate_manifest(provider, verify_components=False)

    sample = copy.deepcopy(manifest)
    sample["tasks"][0]["commit_sha"] = "0" * 40
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(sample)
    with pytest.raises(module.QualificationError):
        module.validate_manifest(sample, verify_components=False)


def test_plan_preserves_zero_provider_claim_boundary() -> None:
    module = _load_module()
    plan = module.plan(module.generate_manifest())

    assert plan["mode"] == "zero_provider_unseen_project_qualification"
    assert plan["authorization"]["credential_read"] is False
    assert plan["authorization"]["provider_calls"] is False
    assert plan["authorization"]["model_tokens"] == 0
    assert plan["decision_on_pass"] == "proceed_to_unseen_three_arm_provider_canary_design"
