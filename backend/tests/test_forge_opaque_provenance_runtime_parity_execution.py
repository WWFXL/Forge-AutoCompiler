"""Issue #190 runtime-parity execution amendment 的零 provider 测试。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "scripts/forge_opaque_provenance_runtime_parity_execution_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts/forge_opaque_provenance_runtime_parity_execution_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-runtime-parity-execution.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-runtime-parity-execution.schema.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_module("forge_opaque_provenance_runtime_parity_execution_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_opaque_provenance_runtime_parity_execution_runner_test", RUNNER_PATH)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_generated_manifest_schema_parent_runtime_and_preregistration_are_frozen() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.schema_document(manifest)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    assert manifest["parent"]["canonical_sha256"] == protocol.PARENT_MANIFEST_SHA256
    assert manifest["parent"]["evidence_identity_sha256"] == protocol.PARENT_EVIDENCE_IDENTITY_SHA256
    assert manifest["runtime_adapter"]["file_sha256"] == protocol.file_sha256(RUNNER_PATH)


def test_execution_authorization_and_single_opportunity_are_exact() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    authorization = manifest["authorization"]
    assert authorization == {
        "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/190",
        "reachability_request_authorized": True,
        "provider_calls_authorized": True,
        "formal_attempts_authorized": True,
        "canary_collection_authorized": True,
        "credential_read_authorized": True,
        "model_tokens_authorized": 245_000,
    }
    assert manifest["opportunities"]["maximum_reachability_requests"] == 1
    assert manifest["opportunities"]["maximum_canary_pairs"] == 1
    assert manifest["opportunities"]["retry_replacement_backfill_forbidden"] is True
    assert manifest["opportunities"]["schedule_extension_forbidden"] is True


def test_runtime_parity_is_shared_and_parallel_tools_are_disabled() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    parity = manifest["runtime_parity"]
    assert parity["action_limits"] == {"inspection": 4, "repair_build": 2, "artifact_stage": 2, "submit": 2}
    assert parity["atomic_budget_claim"] is True
    assert parity["parallel_tool_calls"] is False
    assert parity["parent_submit_uses_bound_wrapper"] is True
    assert parity["fence_released_before_capture"] is True
    assert manifest["schedule"][0]["shared_measurement_policy"] == "runtime_parity_v1"
    assert manifest["schedule"][0]["treatment_exposure_only"] == "repair_packet"
    assert manifest["analysis"]["historical_pair_replacement"] is False


def test_execution_hooks_are_installed_and_restored_on_failure(tmp_path: Path) -> None:
    from deerflow.compile import operations

    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    originals = (runner.legacy.protocol, runner.legacy.collect_preflight, runner.primary.run_arm_continuation, operations.submit_build_result_impl)

    def operation() -> None:
        assert runner.legacy.protocol is runner.protocol
        assert runner.legacy.collect_preflight is runner.collect_preflight
        assert runner.primary.run_arm_continuation is not originals[2]
        assert operations.submit_build_result_impl is not originals[3]
        raise RuntimeError("expected")

    with pytest.raises(RuntimeError, match="expected"):
        runner._with_execution_hooks(manifest, tmp_path, operation)
    assert (runner.legacy.protocol, runner.legacy.collect_preflight, runner.primary.run_arm_continuation, operations.submit_build_result_impl) == originals


def test_report_hook_adds_runtime_parity_evidence_and_restores_writer(tmp_path: Path) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    report_path = tmp_path / manifest["evidence"]["canary_report"]
    original_writer = runner.legacy.v3_runner._write_once

    def operation() -> str:
        runner.legacy.v3_runner._write_once(
            report_path,
            {
                "schema_version": "old",
                "document_type": "old",
                "arms": [],
            },
        )
        return "ok"

    assert runner._with_execution_hooks(manifest, tmp_path, operation) == "ok"
    report = _load(report_path)
    assert report["schema_version"] == manifest["execution"]["report_schema_version"]
    assert report["document_type"] == manifest["execution"]["report_document_type"]
    assert report["runtime_parity"] == manifest["runtime_parity"]
    assert report["runtime_parity_action_budgets"] == {}
    assert report["historical_pair_replacement"] is False
    assert report["historical_canary_report_sha256"] == manifest["historical_evidence"]["canary_report_sha256"]
    assert runner.legacy.v3_runner._write_once is original_writer


def test_preflight_checks_new_directory_historical_hash_and_zero_provider(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    output = tmp_path / Path(manifest["evidence"]["directory"]).name
    historical = tmp_path / Path(manifest["historical_evidence"]["directory"]).name / manifest["historical_evidence"]["canary_report"]
    historical.parent.mkdir(parents=True)
    historical.write_bytes(b"frozen")
    monkeypatch.setattr(runner.protocol, "verify_frozen_components", lambda *_args: None)
    monkeypatch.setattr(runner, "_output_dir", lambda _manifest, value: value)
    monkeypatch.setattr(runner.legacy, "_release_identity", lambda *_args: {"revision": "a" * 40})
    monkeypatch.setattr(runner.legacy, "_network_medium", lambda _manifest: "wifi")
    monkeypatch.setattr(runner.primary, "require_compose_dood", lambda: None)
    monkeypatch.setattr(runner.legacy.v3_runner, "require_zero_managed_containers", lambda: None)
    monkeypatch.setattr(runner.legacy, "_provider_preflight", lambda _manifest: None)
    monkeypatch.setattr(runner.protocol, "file_sha256", lambda _path: manifest["historical_evidence"]["canary_report_sha256"])
    result = runner.collect_preflight(manifest, output_dir=output, repo_root=tmp_path, require_empty=True)
    assert result["ready"] is True
    assert result["network_access_medium"] == "wifi"
    assert result["evidence_files"] == []
    assert (result["provider_calls"], result["formal_attempts"], result["model_tokens"]) == (0, 0, 0)


def test_schema_and_semantics_reject_authorization_or_runtime_drift() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    for section, field, value in (
        ("authorization", "model_tokens_authorized", 245_001),
        ("runtime_parity", "parallel_tool_calls", True),
        ("runtime_parity", "atomic_budget_claim", False),
        ("historical_evidence", "reuse_forbidden", False),
    ):
        drifted = copy.deepcopy(manifest)
        drifted[section][field] = value
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(drifted)
        with pytest.raises(protocol.ProtocolError, match="manifest drifted"):
            protocol.validate_manifest(drifted, REPO_ROOT)


def test_runner_source_uses_bound_parent_submit_and_never_embeds_credentials() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "_submit_with_post_build_phase" in source
    assert "RuntimeParityToolAdapter" in source
    assert "SerialToolCallMiddleware" in source
    for forbidden in ("sk-", "api_key=", "OPENAI_AK", "os.environ["):
        assert forbidden not in source
