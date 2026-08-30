"""Issue #233 confirmatory candidate v2 的 pre-result amendment 合同。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "forge_opaque_provenance_confirmatory_candidate_v2_protocol.py"


def _load_protocol():
    spec = importlib.util.spec_from_file_location(
        "forge_opaque_provenance_confirmatory_candidate_v2_test",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_protocol()


def test_v2_preserves_parent_and_allows_only_sql_parser_bootstrap_delta() -> None:
    manifest = protocol.generate_manifest(REPO_ROOT)
    delta = protocol.validate_allowed_delta(manifest, REPO_ROOT)
    assert delta == {
        "status": "passed",
        "parent_manifest_sha256": protocol.PARENT_MANIFEST_SHA256,
        "case_id": "sql-parser-shared",
        "bootstrap_before": [],
        "bootstrap_after": [protocol.SQL_PARSER_BOOTSTRAP],
        "schedule_identity_sha256": "3f35dd8c245cb7e9db6069f63cf133c98fbfdf6813a11e3fa2306a5eb34c2134",
        "schedule_modified": False,
        "artifact_oracle_modified": False,
        "verifier_relaxation": False,
    }


def test_manifest_schema_and_authorization_are_frozen() -> None:
    manifest = json.loads(protocol.DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    assert protocol.validate_manifest(manifest, REPO_ROOT) == manifest
    assert json.loads(protocol.DEFAULT_SCHEMA.read_text(encoding="utf-8")) == protocol.schema_document(manifest)
    assert manifest["authorization"] == protocol.parent.generate_manifest(REPO_ROOT)["authorization"]
    assert all(value is False for key, value in manifest["authorization"].items() if key.endswith("_authorized") and key != "model_tokens_authorized")
    assert manifest["authorization"]["model_tokens_authorized"] == 0


def test_unrelated_case_or_schedule_drift_fails_closed() -> None:
    for mutation in ("case", "schedule", "oracle"):
        drifted = protocol.generate_manifest(REPO_ROOT)
        if mutation == "case":
            drifted["cases"][0]["direct_target"] = "wrong"
        elif mutation == "schedule":
            drifted["schedule"]["pairs"][0]["arm_order"].reverse()
        else:
            drifted["cases"][-1]["artifact"]["artifact_type"] = "static_library"
        with pytest.raises(protocol.ConfirmatoryCandidateV2Error):
            protocol.validate_allowed_delta(drifted, REPO_ROOT)


def test_authorization_or_bootstrap_drift_fails_closed() -> None:
    manifest = protocol.generate_manifest(REPO_ROOT)
    authorized = copy.deepcopy(manifest)
    authorized["authorization"]["docker_execution_authorized"] = True
    with pytest.raises(protocol.ConfirmatoryCandidateV2Error):
        protocol.validate_manifest(authorized, REPO_ROOT)
    bootstrap_drift = copy.deepcopy(manifest)
    bootstrap_drift["cases"][-1]["bootstrap_commands"] = ["touch src/parser/bison_parser.y"]
    with pytest.raises(protocol.ConfirmatoryCandidateV2Error):
        protocol.validate_allowed_delta(bootstrap_drift, REPO_ROOT)


def test_static_gate_has_no_external_effects() -> None:
    report = protocol.validate_static_gate(REPO_ROOT)
    assert report["status"] == "passed"
    assert report["case_count"] == 6
    assert report["pair_count"] == 12
    assert report["provider_calls"] == report["formal_attempts"] == report["model_tokens"] == 0
    assert report["credential_read"] is False
    assert report["docker_executed"] is False
    assert report["checkpoint_created"] is False
    assert report["evidence_writes"] == 0


def test_new_sources_do_not_contain_provider_or_credential_entrypoints() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    for forbidden in ("openai_ak", "deepseek_api_key", "api_key=", "chatopenai(", "execute-pair", "reachability"):
        assert forbidden not in source
