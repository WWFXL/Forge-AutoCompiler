"""Issue #289 Phase 5 六项目校准候选的零 Provider 合同测试。"""

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
PROTOCOL_PATH = SCRIPTS / "forge_agent_workflow_stage_b_calibration_protocol.py"
RUNNER_PATH = SCRIPTS / "forge_agent_workflow_stage_b_calibration_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-agent-workflow-stage-b-calibration-candidate.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-agent-workflow-stage-b-calibration-candidate.schema.json"


def _load_module(name: str, path: Path):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_module("forge_agent_workflow_stage_b_calibration_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_agent_workflow_stage_b_calibration_runner_test", RUNNER_PATH)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_manifest_schema_and_frozen_components_are_deterministic() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)

    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.generate_schema(manifest)
    assert protocol.canonical_sha256(manifest) == "303b41c0ee95c4732eb9388a39176789064e131c19217632175fa19e1526434f"
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    assert manifest["frozen_components"][protocol.PROTOCOL_PATH] == protocol.file_sha256(PROTOCOL_PATH)
    assert manifest["frozen_components"][protocol.RUNNER_PATH] == protocol.file_sha256(RUNNER_PATH)


def test_six_task_identity_target_and_oracle_matrix_is_frozen() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    tasks = manifest["tasks"]

    assert [task["task_id"] for task in tasks] == ["yyjson", "cppitertools", "openh264", "uwebsockets", "c-ares", "libass"]
    assert [task["build_system"] for task in tasks] == ["cmake", "cmake", "make", "make", "autotools", "autotools"]
    assert len({task["commit_sha"] for task in tasks}) == 6
    assert all(len(task["commit_sha"]) == 40 for task in tasks)
    assert all(task["target_contract"]["functional_oracle_ref"] and task["oracle"]["kind"] in {"compile_and_run", "service_probe"} for task in tasks)
    uwebsockets = next(task for task in tasks if task["task_id"] == "uwebsockets")
    assert uwebsockets["oracle"]["start_argv"] == ["./HelloWorld"]


def test_historical_audit_keeps_generated_submitted_strict_and_bitwise_separate() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    assert manifest["historical_baseline"]["audit"] == {
        "task_count": 6,
        "candidate_generated": 6,
        "candidate_submitted": 4,
        "strict_success": 6,
        "bitwise_reproducible": 5,
        "candidate_to_submit_gap": ["cppitertools", "uwebsockets"],
        "evaluator_v3_overrides": ["uwebsockets"],
    }
    assert manifest["historical_baseline"]["outcomes_imported"] is False
    assert manifest["historical_baseline"]["historical_evidence_mutated"] is False


def test_historical_audit_rejects_identity_and_v3_scope_drift() -> None:
    fixture = protocol.load_historical_fixture(REPO_ROOT)
    wrong_source = copy.deepcopy(fixture)
    wrong_source["source"]["sha256"] = "0" * 64
    with pytest.raises(protocol.Phase5ProtocolError, match="来源"):
        protocol.audit_historical_fixture(wrong_source)

    wrong_selection_policy = copy.deepcopy(fixture)
    wrong_selection_policy["selection_policy"]["default_evaluation_run"] = "stage-b-external-v1"
    with pytest.raises(protocol.Phase5ProtocolError, match="选择策略"):
        protocol.audit_historical_fixture(wrong_selection_policy)

    wrong_commit = copy.deepcopy(fixture)
    wrong_commit["tasks"][0]["commit_sha"] = "0" * 40
    with pytest.raises(protocol.Phase5ProtocolError, match="identity"):
        protocol.audit_historical_fixture(wrong_commit)

    wrong_override = copy.deepcopy(fixture)
    wrong_override["tasks"][0]["selected_evaluation_run"] = "stage-b-external-uwebsockets-v3"
    with pytest.raises(protocol.Phase5ProtocolError, match="evaluator identity"):
        protocol.audit_historical_fixture(wrong_override)


def test_candidate_authorizes_no_provider_credentials_docker_or_evidence() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    authorization = manifest["authorization"]
    assert all(value is False for key, value in authorization.items() if key.endswith("_authorized") and key != "model_tokens_authorized")
    assert authorization["model_tokens_authorized"] == 0
    assert manifest["environment_candidate"]["image_id"] is None
    assert manifest["evidence_candidate"]["writes_authorized"] is False

    validation = runner.validate_runtime(manifest, REPO_ROOT)
    assert validation["task_count"] == 6
    assert (
        validation["provider_calls"],
        validation["credential_reads"],
        validation["docker_executions"],
        validation["formal_attempts"],
        validation["model_tokens"],
        validation["evidence_writes"],
    ) == (0, 0, 0, 0, 0, 0)

    with pytest.raises(runner.Phase5RunnerError, match="未授权"):
        runner.execute_reachability(manifest)
    with pytest.raises(runner.Phase5RunnerError, match="未授权"):
        runner.run_batch(manifest)


def test_schema_and_protocol_reject_authorization_or_task_drift() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    mutations = []

    authorized = copy.deepcopy(manifest)
    authorized["authorization"]["provider_calls_authorized"] = True
    mutations.append(authorized)

    reordered = copy.deepcopy(manifest)
    reordered["tasks"][0], reordered["tasks"][1] = reordered["tasks"][1], reordered["tasks"][0]
    mutations.append(reordered)

    imported = copy.deepcopy(manifest)
    imported["historical_baseline"]["outcomes_imported"] = True
    mutations.append(imported)

    for drifted in mutations:
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(drifted)
        with pytest.raises(protocol.Phase5ProtocolError):
            protocol.validate_manifest(drifted, REPO_ROOT)


def test_preflight_is_read_only_and_reports_frozen_matrix() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    result = protocol.collect_preflight(manifest, REPO_ROOT)

    assert result["status"] == "candidate_valid_not_authorized"
    assert result["task_count"] == 6
    assert result["build_system_counts"] == {"cmake": 2, "make": 2, "autotools": 2}
    assert result["historical_audit"] == manifest["historical_baseline"]["audit"]
    assert (
        result["provider_calls"],
        result["credential_reads"],
        result["docker_executions"],
        result["formal_attempts"],
        result["model_tokens"],
        result["evidence_writes"],
    ) == (0, 0, 0, 0, 0, 0)
