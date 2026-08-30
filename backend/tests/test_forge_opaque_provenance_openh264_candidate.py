"""Issue #224 OpenH264 独立 Make checkpoint 的零 provider 门禁。"""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
GATE_PATH = SCRIPTS_DIR / "forge_opaque_provenance_openh264_candidate_gate.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-openh264-candidate.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-openh264-candidate.schema.json"


def _load_gate():
    name = "forge_opaque_provenance_openh264_candidate_gate_test"
    spec = importlib.util.spec_from_file_location(name, GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        sys.modules[name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))
    return module


gate = _load_gate()


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_manifest_schema_and_result_blind_selection_are_frozen() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    assert manifest == gate.generate_manifest(REPO_ROOT)
    assert schema == gate.schema_document(manifest)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    gate.verify_frozen_components(REPO_ROOT)
    assert manifest["selection"]["source_case"]["id"] == "openh264"
    assert manifest["selection"]["historical_physical_evidence_matches"] == 0
    assert manifest["selection"]["published_report_matches"] == 0
    assert manifest["reference_sources"]["submodules_at_exact_commit"] == []


def test_authorization_and_future_evidence_are_closed() -> None:
    manifest = gate.load_manifest(MANIFEST_PATH, REPO_ROOT)
    assert all(value is False for key, value in manifest["authorization"].items() if key.endswith("_authorized") and key != "model_tokens_authorized")
    assert manifest["authorization"]["model_tokens_authorized"] == 0
    assert manifest["checkpoint"]["status"] == "not_created"
    assert manifest["evidence"]["status"] == "not_created"
    assert manifest["runtime_parity"]["treatment_exposure_only"] == "repair_packet"


def test_static_p2_lifecycle_and_action_surface_close() -> None:
    result = gate.validate_static_gate(REPO_ROOT)
    assert result["parent"]["status"] == "unproven"
    assert result["parent"]["reason"] == "opaque_wrapper"
    assert result["treatment"]["status"] == "proven"
    assert result["treatment"]["proof_mode"] == "direct_make"
    assert result["parent_history_prefix_preserved"] is True
    assert set(result["accepted"].values()) == {"repair_build"}
    assert result["rejected"] == {
        "make -j libopenh264.a": "repair_build_jobs_unbounded",
        "make -j0 libopenh264.a": "repair_build_jobs_out_of_bounds",
        "make -j3 libopenh264.a": "repair_build_jobs_out_of_bounds",
        "make libhoedown.a": "repair_build_target_drift",
    }
    assert (
        result["provider_calls"],
        result["credential_read"],
        result["docker_executed"],
        result["formal_evidence_writes"],
        result["model_tokens"],
    ) == (0, False, False, 0, 0)


def test_candidate_policy_reaches_full_agent_construction_gate() -> None:
    result = asyncio.run(gate.validate_agent_construction())
    assert result["status"] == "passed"
    assert result["candidate_policy"]["target"] == "libopenh264.a"
    assert result["success_probe"]["request_evidence"] == {
        "model.request_started": 1,
        "model.request_completed": 1,
        "model.request_failed": 0,
        "model.request_cancelled": 0,
    }
    assert result["failure_probe"]["classification"] == "pre_model_execution_error"
    assert result["cleanup_probe"]["status"] == "passed"
    assert (
        result["provider_calls"],
        result["credential_read"],
        result["docker_executed"],
        result["formal_evidence_writes"],
        result["model_tokens"],
    ) == (0, False, False, 0, 0)


def test_schema_and_protocol_reject_identity_or_authorization_drift() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    mutations = (
        ("authorization", "provider_calls_authorized", True),
        ("authorization", "model_tokens_authorized", 1),
        ("case", "target", "all"),
        ("runtime_parity", "parallel_tool_calls", True),
    )
    for section, field, value in mutations:
        drifted = copy.deepcopy(manifest)
        drifted[section][field] = value
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(drifted)
        with pytest.raises(gate.OpenH264CandidateGateError, match="manifest"):
            gate.validate_manifest(drifted, REPO_ROOT)


def test_new_sources_do_not_embed_credentials_or_provider_execution() -> None:
    combined = GATE_PATH.read_text(encoding="utf-8")
    for forbidden in ("sk-", "api_key=", "OPENAI_AK", "DEEPSEEK_API_KEY", "os.environ["):
        assert forbidden not in combined
    assert 'provider_calls_authorized": False' in combined
    assert gate.validate_repair_packet(gate.build_repair_packet()) == gate.build_repair_packet()
