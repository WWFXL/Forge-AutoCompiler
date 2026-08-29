"""Issue #180 opaque provenance 最小 canary 的零 provider 协议测试。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "scripts/forge_opaque_provenance_minimal_canary_protocol.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-minimal-canary.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-minimal-canary.schema.json"


def _load_module():
    name = "forge_opaque_provenance_minimal_canary_protocol_test"
    spec = importlib.util.spec_from_file_location(name, PROTOCOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_module()


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_generated_manifest_schema_and_components_are_frozen() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.schema_document(manifest)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    assert set(manifest["frozen_components"]) == protocol.FROZEN_COMPONENT_PATHS


def test_single_cppitertools_pair_and_unique_exposure_are_fixed() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    assert manifest["case"]["case_id"] == "cppitertools-opaque-provenance-real-docker"
    assert manifest["case"]["commit_sha"] == "531b3d753d2bbfe3b0ababe61c2e95e965c54a66"
    assert manifest["schedule"] == [
        {
            "pair_id": protocol.PAIR_ID,
            "order": 1,
            "case_id": "cppitertools-opaque-provenance-real-docker",
            "arm_order": ["baseline", "treatment"],
            "treatment_exposure_only": "repair_packet",
        }
    ]
    assert manifest["schedule_sha256"] == protocol.canonical_sha256(manifest["schedule"])


def test_provider_budget_and_analysis_boundaries_are_fixed() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    assert manifest["provider"] == {
        "status": "future_identity_only",
        "id": "deepseek-v4-flash",
        "endpoint": "https://api.deepseek.com",
        "credential_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-v4-flash",
        "request_timeout_seconds": 300,
        "max_retries": 0,
        "fallback": "forbidden",
        "streaming": False,
    }
    assert manifest["budget"]["stage_maximum_recorded_tokens"] == 245_000
    assert manifest["continuation"]["maximum_requests_per_arm"] == 8
    assert manifest["analysis"]["treatment_effect_estimated"] is False
    assert manifest["analysis"]["p_value_computed"] is False
    assert manifest["analysis"]["model_ranking_performed"] is False


def test_all_execution_authorization_and_paths_are_closed() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    authorization = manifest["authorization"]
    assert authorization["reachability_request_authorized"] is False
    assert authorization["provider_calls_authorized"] is False
    assert authorization["formal_attempts_authorized"] is False
    assert authorization["canary_collection_authorized"] is False
    assert authorization["model_tokens_authorized"] == 0
    assert manifest["execution"]["provider_model_creation_supported"] is False
    assert manifest["execution"]["credential_read_supported"] is False
    assert manifest["execution"]["execute_path_supported"] is False


def test_schema_and_semantics_reject_authorization_or_schedule_drift() -> None:
    schema = _load(SCHEMA_PATH)
    manifest = _load(MANIFEST_PATH)
    authorized = copy.deepcopy(manifest)
    authorized["authorization"]["provider_calls_authorized"] = True
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(authorized)
    with pytest.raises(protocol.ProtocolError, match="manifest drifted"):
        protocol.validate_manifest(authorized, REPO_ROOT)

    reordered = copy.deepcopy(manifest)
    reordered["schedule"][0]["arm_order"].reverse()
    with pytest.raises(protocol.ProtocolError, match="manifest drifted"):
        protocol.validate_manifest(reordered, REPO_ROOT)


def test_protocol_source_has_no_provider_or_credential_execution_path() -> None:
    source = PROTOCOL_PATH.read_text(encoding="utf-8")
    for forbidden in ("os.environ", "create_chat_model", "ChatOpenAI", "execute_collection", "api_key="):
        assert forbidden not in source
    plan = protocol.show_plan(protocol.load_manifest(MANIFEST_PATH, REPO_ROOT))
    assert plan["provider_calls"] == 0
    assert plan["formal_attempts"] == 0
    assert plan["model_tokens"] == 0
    assert plan["execution_authorized"] is False
