"""Issue #440 H0/H1 v3 正式复现协议测试。"""

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
SCRIPT_PATH = REPO_ROOT / "scripts/forge_progress_aware_harness_comparison_v3.py"


def _load_module() -> ModuleType:
    name = "forge_progress_aware_harness_comparison_v3_test"
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


def test_authorized_manifest_and_const_schema_are_deterministic() -> None:
    module = _load_module()
    manifest = _load(module.MANIFEST_PATH)
    schema = _load(module.SCHEMA_PATH)

    assert manifest == module.generate_manifest()
    assert schema == module.schema_document(manifest)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    assert module.validate_manifest(manifest, require_components=False) == manifest


def test_authorized_identity_binds_candidate_and_preserves_design() -> None:
    module = _load_module()
    manifest = _load(module.MANIFEST_PATH)
    frozen_candidate = _load(module.CANDIDATE_MANIFEST_PATH)

    assert manifest["candidate_binding"]["revision"] == module.CANDIDATE_REVISION
    assert manifest["candidate_binding"]["manifest_canonical_sha256"] == module.CANDIDATE_MANIFEST_SHA256
    assert manifest["tasks"] == frozen_candidate["tasks"]
    assert manifest["canary_checkpoints"] == frozen_candidate["canary_checkpoints"]
    assert manifest["formal_schedule"] == frozen_candidate["formal_schedule"]
    assert manifest["treatments"] == frozen_candidate["treatments"]
    assert manifest["qualification"] == frozen_candidate["qualification"]


def test_authorized_budget_includes_bounded_post_response_usage() -> None:
    module = _load_module()
    manifest = _load(module.MANIFEST_PATH)
    per_arm = manifest["budget"]["per_arm"]

    assert per_arm["max_recorded_tokens"] == 300_000
    assert per_arm["max_recorded_tokens_per_response"] == 100_000
    assert manifest["budget"]["total_recorded_tokens_stop_threshold"] == 18_000_000
    assert manifest["budget"]["total_authorized_recorded_tokens"] == 24_000_000
    assert manifest["budget"]["total_provider_cost_usd_ceiling"] == 28.8
    assert manifest["authorization_record"]["maximum_provider_requests"] == 1_440


def test_token_observation_requires_one_terminal_per_started_request(tmp_path: Path) -> None:
    module = _load_module()
    events = tmp_path / "events.jsonl"
    rows = [
        {"event_type": "model.request_started", "payload": {"request_sequence": 1}},
        {
            "event_type": "model.request_completed",
            "payload": {
                "request_sequence": 1,
                "input_tokens": 7,
                "output_tokens": 3,
                "recorded_tokens": 10,
            },
        },
        {"event_type": "model.request_started", "payload": {"request_sequence": 2}},
        {
            "event_type": "model.request_failed",
            "payload": {"request_sequence": 2, "error_class": "ProviderError"},
        },
    ]
    events.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    observed = module._token_observation(events)
    assert observed["request_lifecycle_closed"] is True
    assert observed["complete"] is True
    assert observed["requests_started"] == 2
    assert observed["requests_completed"] == 1
    assert observed["requests_failed"] == 1
    assert observed["recorded_tokens"] == 10

    rows.append(
        {
            "event_type": "model.request_usage_incomplete",
            "payload": {"request_sequence": 2, "reason": "missing_usage_metadata"},
        }
    )
    events.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    invalid = module._token_observation(events)
    assert invalid["request_lifecycle_closed"] is False
    assert invalid["complete"] is False


def test_schema_and_protocol_reject_design_or_authorization_drift() -> None:
    module = _load_module()
    manifest = _load(module.MANIFEST_PATH)
    schema = _load(module.SCHEMA_PATH)

    drifted = copy.deepcopy(manifest)
    drifted["budget"]["per_arm"]["max_recorded_tokens_per_response"] = 200_000
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(drifted)
    with pytest.raises(module.QualificationError):
        module.validate_manifest(drifted, require_components=False)

    replaced = copy.deepcopy(manifest)
    replaced["authorization"]["replacement"] = True
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(replaced)
    with pytest.raises(module.QualificationError):
        module.validate_manifest(replaced, require_components=False)
