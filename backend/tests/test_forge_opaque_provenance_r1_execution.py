"""Issue #200 R1 yyjson execution amendment 的零 provider 测试。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "scripts/forge_opaque_provenance_r1_execution_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts/forge_opaque_provenance_r1_execution_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-r1-execution.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-r1-execution.schema.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_module("forge_opaque_provenance_r1_execution_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_opaque_provenance_r1_execution_runner_test", RUNNER_PATH)


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


def test_authorization_provider_budget_and_single_opportunity_are_exact() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    assert manifest["authorization"] == {
        "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/200",
        "checkpoint_creation_authorized": True,
        "reachability_request_authorized": True,
        "provider_calls_authorized": True,
        "formal_attempts_authorized": True,
        "pair_collection_authorized": True,
        "credential_read_authorized": True,
        "model_creation_authorized": True,
        "docker_execution_authorized": True,
        "evidence_write_authorized": True,
        "model_tokens_authorized": 245_000,
    }
    assert manifest["provider"] == {
        "status": "active_authorized",
        "id": "deepseek-v4-flash",
        "endpoint": "https://api.deepseek.com",
        "credential_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-v4-flash",
        "request_timeout_seconds": 300,
        "max_retries": 0,
        "fallback": "forbidden",
        "streaming": False,
    }
    assert manifest["budget"] == {
        "maximum_reachability_requests": 1,
        "reachability_maximum_recorded_tokens": 5_000,
        "recorded_tokens_per_arm": 120_000,
        "recorded_tokens_per_pair": 240_000,
        "stage_maximum_recorded_tokens": 245_000,
        "enforcement": "after_reachability_and_each_arm_before_continuation",
    }
    assert manifest["opportunities"]["maximum_reachability_requests"] == 1
    assert manifest["opportunities"]["maximum_pairs"] == 1
    assert manifest["opportunities"]["marker_consumed_on_start"] is True
    assert manifest["opportunities"]["retry_replacement_backfill_forbidden"] is True


def test_r1_case_policy_and_r0_observability_are_bound() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    assert manifest["case"]["case_id"] == "yyjson-opaque-provenance-r1"
    assert manifest["case"]["target"] == "yyjson"
    assert manifest["case"]["artifact_type"] == "static_library"
    assert manifest["schedule"][0]["arm_order"] == ["baseline", "treatment"]
    assert manifest["schedule"][0]["treatment_exposure_only"] == "repair_packet"
    assert manifest["runtime_parity"]["observable_adapter"] == ("ObservableRuntimeParityToolAdapter")
    assert manifest["runtime_parity"]["rejection_registry"] == ("RejectionObservationRegistry")
    assert manifest["runtime_parity"]["parallel_tool_calls"] is False
    assert manifest["r0_observability"]["companion_required_for_classified_rejection"] is True
    policy = runner._policy(manifest, arm="treatment", image_id="sha256:" + "1" * 64)
    assert policy.source_subdir == "."
    assert policy.build_targets == ("yyjson",)
    assert policy.artifact_instructions == (("libyyjson.a", "build/libyyjson.a", "static_library"),)
    assert policy.required_system_packages == ()
    assert policy.cmake_arguments == ()


def test_execution_hooks_install_r1_lifecycle_and_restore_on_failure(
    tmp_path: Path,
) -> None:
    from deerflow.compile import operations

    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    originals = (
        runner.legacy.protocol,
        runner.legacy.collect_preflight,
        runner.legacy.opaque,
        runner.legacy._policy,
        runner.primary.run_arm_continuation,
        operations.submit_build_result_impl,
    )

    def operation() -> None:
        assert runner.legacy.protocol is runner.protocol
        assert runner.legacy.collect_preflight is runner.collect_preflight
        assert runner.legacy.opaque is runner.checkpoint_gate
        assert runner.legacy._policy is runner._policy
        assert runner.primary.run_arm_continuation is not originals[4]
        assert operations.submit_build_result_impl is not originals[5]
        raise RuntimeError("expected")

    with pytest.raises(RuntimeError, match="expected"):
        runner._with_execution_hooks(manifest, tmp_path, operation)
    assert (
        runner.legacy.protocol,
        runner.legacy.collect_preflight,
        runner.legacy.opaque,
        runner.legacy._policy,
        runner.primary.run_arm_continuation,
        operations.submit_build_result_impl,
    ) == originals


def test_r0_summary_requires_companion_for_each_classified_rejection() -> None:
    failure = {
        "event": "agent.tool_failed",
        "payload": {
            "failure_id": "failure_" + "1" * 32,
            "exception_class": "ObservableRuntimeParityGateError",
        },
    }
    observation = {
        "event": runner.observability.OBSERVATION_EVENT,
        "payload": {
            "failure_id": "failure_" + "1" * 32,
            "rejection_classification": "compound_shell_forbidden",
        },
    }
    summary = runner._r0_summary(SimpleNamespace(read=lambda: [failure, observation]))
    assert summary == {
        "classified_rejections": 1,
        "companion_events": 1,
        "companion_complete": True,
        "rejection_classifications": ["compound_shell_forbidden"],
        "raw_command_persisted": False,
    }
    with pytest.raises(runner.ExecutionGateError, match="缺少唯一 R0 companion"):
        runner._r0_summary(SimpleNamespace(read=lambda: [failure]))


def test_report_hook_adds_runtime_and_r0_evidence(tmp_path: Path) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    report_path = tmp_path / manifest["evidence"]["canary_report"]
    original_writer = runner.legacy.v3_runner._write_once

    def operation() -> str:
        runner.legacy.v3_runner._write_once(
            report_path,
            {"schema_version": "old", "document_type": "old", "arms": []},
        )
        return "ok"

    assert runner._with_execution_hooks(manifest, tmp_path, operation) == "ok"
    report = _load(report_path)
    assert report["schema_version"] == manifest["execution"]["report_schema_version"]
    assert report["document_type"] == manifest["execution"]["report_document_type"]
    assert report["runtime_parity"] == manifest["runtime_parity"]
    assert report["runtime_parity_action_budgets"] == {}
    assert report["r0_rejection_observability"] == {
        "baseline": {
            "classified_rejections": 0,
            "companion_events": 0,
            "companion_complete": True,
            "rejection_classifications": [],
            "raw_command_persisted": False,
        },
        "treatment": {
            "classified_rejections": 0,
            "companion_events": 0,
            "companion_complete": True,
            "rejection_classifications": [],
            "raw_command_persisted": False,
        },
    }
    assert runner.legacy.v3_runner._write_once is original_writer


def test_preflight_checks_empty_identity_and_zero_provider(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    output = tmp_path / Path(manifest["evidence"]["directory"]).name
    monkeypatch.setattr(runner.protocol, "verify_frozen_components", lambda *_: None)
    monkeypatch.setattr(runner, "_output_dir", lambda _manifest, value: value)
    monkeypatch.setattr(
        runner.legacy,
        "_release_identity",
        lambda *_args: {"revision": "a" * 40},
    )
    monkeypatch.setattr(runner.legacy, "_network_medium", lambda _manifest: "wifi")
    monkeypatch.setattr(runner.primary, "require_compose_dood", lambda: None)
    monkeypatch.setattr(runner.legacy.v3_runner, "require_zero_managed_containers", lambda: None)
    monkeypatch.setattr(runner.legacy, "_provider_preflight", lambda _manifest: None)
    result = runner.collect_preflight(
        manifest,
        output_dir=output,
        repo_root=tmp_path,
        require_empty=True,
    )
    assert result["ready"] is True
    assert result["network_access_medium"] == "wifi"
    assert result["evidence_files"] == []
    assert (result["provider_calls"], result["formal_attempts"], result["model_tokens"]) == (0, 0, 0)


def test_schema_and_semantics_reject_authorization_or_observability_drift() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    for section, field, value in (
        ("authorization", "model_tokens_authorized", 245_001),
        ("runtime_parity", "parallel_tool_calls", True),
        ("opportunities", "maximum_pairs", 2),
        ("r0_observability", "companion_required_for_classified_rejection", False),
    ):
        drifted = copy.deepcopy(manifest)
        drifted[section][field] = value
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(drifted)
        with pytest.raises(protocol.ProtocolError, match="manifest drifted"):
            protocol.validate_manifest(drifted, REPO_ROOT)


def test_runner_uses_r0_adapter_and_never_embeds_credentials() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "ObservableRuntimeParityToolAdapter" in source
    assert "RejectionObservationRegistry" in source
    assert "agent.tool_rejection_observed" not in source
    assert "RuntimeParityToolAdapter(" not in source.replace("ObservableRuntimeParityToolAdapter(", "")
    for forbidden in ("sk-", "api_key=", "OPENAI_AK", "os.environ["):
        assert forbidden not in source
