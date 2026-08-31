"""Issue #243 confirmatory independent replication candidate 的零 provider 测试。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
PROTOCOL_PATH = SCRIPTS / "forge_opaque_provenance_confirmatory_replication_candidate_protocol.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-confirmatory-replication-candidate.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-confirmatory-replication-candidate.schema.json"


def _load_protocol():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "forge_confirmatory_replication_candidate_protocol_test",
        PROTOCOL_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_protocol()


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_manifest_schema_and_decision_components_are_frozen() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.schema_document(manifest)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    protocol.verify_frozen_components(manifest, REPO_ROOT)
    assert protocol.canonical_sha256(manifest) == "7b1817becba4ec57eb9726be0e1faaa5427af309dca7552634e3f6a3a1b5d938"


def test_candidate_is_independent_closed_and_keeps_full_schedule() -> None:
    manifest = protocol.validate_manifest(_load(MANIFEST_PATH), REPO_ROOT)
    candidate = manifest["replication_candidate"]
    relationship = candidate["relationship_to_v1"]
    assert len(manifest["cases"]) == 6
    assert len(manifest["schedule"]["pairs"]) == 12
    assert [pair["pair_id"] for pair in manifest["schedule"]["pairs"]] == [
        "pupnp-rep-01",
        "ada-url-rep-01",
        "args-rep-01",
        "gpac-rep-01",
        "fio-rep-01",
        "sql-parser-shared-rep-01",
        "sql-parser-shared-rep-02",
        "fio-rep-02",
        "gpac-rep-02",
        "args-rep-02",
        "ada-url-rep-02",
        "pupnp-rep-02",
    ]
    arm_orders = {case["case_id"]: [pair["arm_order"] for pair in manifest["schedule"]["pairs"] if pair["case_id"] == case["case_id"]] for case in manifest["cases"]}
    expected_orders = {("baseline", "treatment"), ("treatment", "baseline")}
    assert all({tuple(order) for order in orders} == expected_orders for orders in arm_orders.values())
    assert relationship["historical_outcomes_imported"] is False
    assert relationship["v1_attempt_extended"] is False
    assert relationship["gpac_provider_opportunity_consumed"] is False
    assert relationship["gpac_v1_attempt_resumed"] is False
    assert candidate["evidence_candidate"]["directory"].endswith("confirmatory-replication-v1")
    assert candidate["evidence_candidate"]["directory"] != "/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-confirmatory-v1"
    assert candidate["runtime_candidate"]["pair_executor_adapter"] == protocol.RUNTIME_PATH


def test_candidate_authorizes_no_external_work_or_tokens() -> None:
    manifest = protocol.validate_manifest(_load(MANIFEST_PATH), REPO_ROOT)
    authorization = manifest["authorization"]
    assert all(value is False for key, value in authorization.items() if key.endswith("_authorized") and key != "model_tokens_authorized")
    assert authorization["model_tokens_authorized"] == 0
    gate = protocol.validate_static_gate(REPO_ROOT)
    assert gate["pair_count"] == 12
    assert (
        gate["provider_calls"],
        gate["credential_read"],
        gate["docker_executed"],
        gate["checkpoint_created"],
        gate["formal_attempts"],
        gate["model_tokens"],
        gate["evidence_writes"],
    ) == (0, False, False, False, 0, 0, 0)


def test_schema_and_protocol_reject_import_or_authorization_drift() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    mutations = (
        ("authorization", "provider_calls_authorized", True),
        ("authorization", "model_tokens_authorized", 1),
    )
    for section, field, value in mutations:
        drifted = copy.deepcopy(manifest)
        drifted[section][field] = value
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(drifted)
        with pytest.raises(protocol.ReplicationCandidateError):
            protocol.validate_manifest(drifted, REPO_ROOT)

    drifted = copy.deepcopy(manifest)
    drifted["replication_candidate"]["relationship_to_v1"]["historical_outcomes_imported"] = True
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(drifted)
    with pytest.raises(protocol.ReplicationCandidateError):
        protocol.validate_manifest(drifted, REPO_ROOT)


def test_protocol_has_no_provider_docker_or_credential_execution() -> None:
    source = PROTOCOL_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "create_chat_model",
        "docker.from_env",
        "subprocess.run",
        "requests.",
        "httpx.",
        "os.environ",
        "sk-",
        "api_key=",
        "OPENAI_AK",
    ):
        assert forbidden not in source
