"""Issue #230 六 case opaque provenance 确认性 pilot 的静态合同测试。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
PROTOCOL_PATH = SCRIPTS_DIR / "forge_opaque_provenance_confirmatory_candidate_protocol.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-confirmatory-candidate.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-confirmatory-candidate.schema.json"


def _load_protocol():
    name = "forge_opaque_provenance_confirmatory_candidate_protocol_test"
    spec = importlib.util.spec_from_file_location(name, PROTOCOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_protocol()


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_manifest_schema_and_frozen_sources_are_deterministic() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.schema_document(manifest)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    protocol.verify_frozen_sources(REPO_ROOT)
    assert manifest["selection"]["case_count"] == 6
    assert manifest["selection"]["build_system_counts"] == {"cmake": 3, "make": 3}


def test_candidate_has_no_external_execution_authority() -> None:
    manifest = protocol.validate_manifest(_load(MANIFEST_PATH), REPO_ROOT)
    assert all(value is False for key, value in manifest["authorization"].items() if key.endswith("_authorized") and key != "model_tokens_authorized")
    assert manifest["authorization"]["model_tokens_authorized"] == 0
    assert manifest["future_state"] == {
        "checkpoint_status": "not_created",
        "evidence_status": "not_created",
        "execution_runner_status": "not_implemented",
        "execution_requires_new_amendment": True,
    }


def test_case_identity_artifacts_and_result_blind_audit_are_frozen() -> None:
    manifest = _load(MANIFEST_PATH)
    cases = {case["case_id"]: case for case in manifest["cases"]}
    assert set(cases) == set(protocol.CASE_ORDER)
    assert all(case["historical_result_evidence_case_id_matches"] == 0 for case in cases.values())
    assert cases["args"]["source_audit"]["smoke"] == {"flag": "--help", "expected_exit_code": 0}
    assert cases["fio"]["source_audit"]["smoke"] == {"flag": "--help", "expected_exit_code": 0}
    assert cases["gpac"]["source_audit"]["submodules_on_target_dependency_path"] == []
    sql_parser = cases["sql-parser-shared"]
    assert sql_parser["artifact"] == {
        "build_output_path": "libsqlparser.so",
        "staged_relative_path": "libsqlparser.so",
        "artifact_type": "shared_library",
        "stage_source": "/workspace/repo/libsqlparser.so",
        "stage_destination": "/artifacts/libsqlparser.so",
    }
    assert sql_parser["oracle_correction"]["old_artifact"]["artifact_type"] == "static_library"
    assert sql_parser["oracle_correction"]["source_protocol_modified"] is False


def test_schedule_has_two_replicates_and_reverses_order_inside_every_project() -> None:
    result = protocol.validate_static_gate(REPO_ROOT)
    assert result["status"] == "passed"
    assert (result["case_count"], result["pair_count"], result["arm_count"]) == (6, 12, 24)
    assert (
        result["provider_calls"],
        result["credential_read"],
        result["docker_executed"],
        result["formal_attempts"],
        result["model_tokens"],
        result["evidence_writes"],
    ) == (0, False, False, 0, 0, 0)


def test_exclusions_and_inference_boundary_are_explicit() -> None:
    manifest = _load(MANIFEST_PATH)
    assert set(manifest["selection"]["exclusions"]) == {"mruby", "janet", "lodepng", "sql-parser-static"}
    assert manifest["analysis"]["independent_unit"] == "project_block"
    assert manifest["analysis"]["project_block_count"] == 6
    assert manifest["analysis"]["primary_test_requires_all_project_blocks_estimable"] is True
    assert manifest["analysis"]["historical_exploratory_pairs_pooled"] is False
    assert manifest["analysis"]["model_ranking_performed"] is False


def test_schema_and_semantic_validator_reject_drift() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    mutations = (
        ("authorization", "provider_calls_authorized", True),
        ("authorization", "model_tokens_authorized", 1),
        ("schedule", "pair_count", 11),
        ("runtime_contract", "request_retries", 1),
    )
    for section, field, value in mutations:
        drifted = copy.deepcopy(manifest)
        drifted[section][field] = value
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(drifted)
        with pytest.raises(protocol.ConfirmatoryCandidateError, match="manifest"):
            protocol.validate_manifest(drifted, REPO_ROOT)


def test_old_static_oracle_and_excluded_case_replacements_are_rejected() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)

    old_static = copy.deepcopy(manifest)
    sql_parser = old_static["cases"][-1]
    sql_parser["case_id"] = "sql-parser-static"
    sql_parser["artifact"]["artifact_type"] = "static_library"
    sql_parser["artifact"]["build_output_path"] = "libsqlparser.a"
    sql_parser["artifact"]["staged_relative_path"] = "libsqlparser.a"

    excluded = []
    for case_id in ("mruby", "janet", "lodepng"):
        drifted = copy.deepcopy(manifest)
        drifted["cases"][-1]["case_id"] = case_id
        excluded.append(drifted)

    for drifted in (old_static, *excluded):
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(drifted)
        with pytest.raises(protocol.ConfirmatoryCandidateError, match="manifest"):
            protocol.validate_manifest(drifted, REPO_ROOT)


def test_new_protocol_does_not_embed_credentials_or_provider_execution() -> None:
    combined = PROTOCOL_PATH.read_text(encoding="utf-8")
    for forbidden in ("sk-", "api_key=", "OPENAI_AK", "DEEPSEEK_API_KEY", "os.environ["):
        assert forbidden not in combined
    for forbidden in ("import docker", "from docker", "subprocess.run", "subprocess.Popen"):
        assert forbidden not in combined
