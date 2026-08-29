"""Issue #172 多 checkpoint behavioral pilot v3 授权协议与 runner 门禁。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError
from langchain_core.messages import AIMessage

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
PROTOCOL_PATH = SCRIPTS / "forge_multi_checkpoint_behavioral_pilot_v3_authorized_protocol.py"
RUNNER_PATH = SCRIPTS / "forge_multi_checkpoint_behavioral_pilot_v3_authorized_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-verifier-multi-checkpoint-behavioral-pilot-v3-authorized.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-multi-checkpoint-behavioral-pilot-v3-authorized.schema.json"


def _load_module(name: str, path: Path):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_module("forge_multi_checkpoint_behavioral_pilot_v3_authorized_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_multi_checkpoint_behavioral_pilot_v3_authorized_runner_test", RUNNER_PATH)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _arm(arm: str, *, passed: bool, tokens: int = 100) -> dict[str, Any]:
    return {
        "arm": arm,
        "status": "observed",
        "infrastructure": {"status": "valid"},
        "model_behavior": {"status": "completed", "terminal_error_class": None},
        "verification_outcome": {
            "status": "passed" if passed else "failed",
            "submit_attempts": 1,
            "clean_replay_attempts": 1 if passed else 0,
        },
        "physical_attempt_id": f"attempt-{arm}",
        "model_requests": 1,
        "recorded_tokens": tokens,
        "actual_model": "deepseek-v4-flash",
        "metrics": {
            "model_requests": 1,
            "submit_attempts": 1,
            "clean_replay_attempts": 1 if passed else 0,
            "recorded_tokens": tokens,
            "ledger_wall_clock_seconds": 1.0,
        },
        "ledger_head_sha256": "a" * 64,
    }


def _outcome(pair: dict[str, Any]) -> dict[str, Any]:
    treatment_passed = pair["case_pair_index"] == 2 or pair["case_id"] != "janet"
    baseline_passed = pair["case_id"] == "cppitertools"
    arms = {
        "baseline": _arm("baseline", passed=baseline_passed),
        "treatment": _arm("treatment", passed=treatment_passed),
    }
    return {
        "schema_version": "forge-multi-checkpoint-behavioral-pair-outcome-3.1.0",
        "document_type": "forge_multi_checkpoint_behavioral_pair_outcome",
        "manifest_sha256": "b" * 64,
        "pair_manifest_sha256": "c" * 64,
        "pair_id": pair["pair_id"],
        "order": pair["order"],
        "case_id": pair["case_id"],
        "build_system": {"cppitertools": "cmake", "janet": "make", "libcheck": "autotools"}[pair["case_id"]],
        "case_pair_index": pair["case_pair_index"],
        "arm_order": pair["arm_order"],
        "status": "observed",
        "arms": arms,
        "recorded_tokens": 200,
        "primary_mechanism_eligible": True,
        "repair_success": {"baseline": baseline_passed, "treatment": treatment_passed},
        "paired_repair_conversion_delta": int(treatment_passed) - int(baseline_passed),
        "itt_attrition_contribution": 1,
        "coordinator": {"phase": "cleaned"},
        "completed_at": "2026-08-29T00:00:00+00:00",
    }


class CanaryModel:
    def invoke(self, _prompt: str) -> AIMessage:
        return AIMessage(
            content="CANARY_OK",
            response_metadata={"model_name": "deepseek-v4-flash"},
            usage_metadata={"input_tokens": 8, "output_tokens": 2, "total_tokens": 10},
        )


def test_generated_manifest_schema_and_parent_protocol_are_current() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.schema_document(manifest)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    protocol.verify_frozen_components(manifest, REPO_ROOT)
    assert manifest["parent_protocol"]["canonical_sha256"] == "7efa555cb95ace497833c5fb9e9106778d5f856214f9d07a3511bd04298cae5b"


def test_authorization_canary_schedule_and_budget_are_exact() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    assert manifest["authorization"] == {
        "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/172",
        "authorized_by": "experiment_owner",
        "provider_calls_authorized": True,
        "formal_attempts_authorized": True,
        "model_tokens_authorized": 1_440_000,
        "pilot_collection_authorized": True,
        "authorized_provider_canaries": 1,
        "authorized_pairs": 6,
    }
    assert manifest["canary"]["maximum_requests"] == 1
    assert manifest["canary"]["retry_forbidden"] is True
    assert len(manifest["schedule"]) == 6
    assert manifest["budget"]["stage_maximum_recorded_tokens"] == 1_440_000
    assert manifest["execution"]["network_access_medium"] == "wifi"


def test_schema_and_protocol_reject_authorization_drift() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    drifted = copy.deepcopy(manifest)
    drifted["authorization"]["authorized_provider_canaries"] = 2
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(drifted)
    with pytest.raises(protocol.ProtocolError, match="manifest drifted"):
        protocol.validate_manifest(drifted, REPO_ROOT)


def test_pair_runtime_maps_all_case_policy_fields() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    cases = protocol.case_definitions(manifest, REPO_ROOT)
    for pair in manifest["schedule"]:
        case = cases[pair["case_id"]]
        pair_manifest = runner._pair_manifest(manifest, pair, case, Path("/tmp") / pair["pair_id"])
        policy = runner._case_policy(manifest, case, arm="baseline", image_id="sha256:" + "a" * 64)
        assert pair_manifest["pilot"]["case_id"] == case.case_id
        assert pair_manifest["pilot"]["build_system"] == case.build_system
        assert policy.case_id == case.case_id
        assert policy.expected_repo_url == case.repository_url
        assert policy.expected_build_system == case.build_system
        assert policy.required_system_packages == case.required_system_packages
        assert policy.artifact_instructions == ((case.staged_relative_path, case.build_output_relative_path, case.artifact_type),)


def test_preflight_is_zero_request_and_checks_frozen_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    monkeypatch.setattr(runner.protocol, "verify_frozen_components", lambda *_args: None)
    monkeypatch.setattr(runner, "_require_output_dir", lambda *_args: None)
    monkeypatch.setattr(runner, "require_release_identity", lambda *_args: {"branch": "main", "revision": "a" * 40, "origin_main": "a" * 40})
    monkeypatch.setattr(runner, "require_network_medium", lambda *_args: "wifi")
    monkeypatch.setattr(runner.primary, "require_compose_dood", lambda: None)
    monkeypatch.setattr(runner, "require_zero_managed_containers", lambda: None)
    monkeypatch.setattr(runner, "_provider_config_preflight", lambda *_args: None)
    result = runner.collect_preflight(manifest, output_dir=tmp_path)
    assert result["ready"] is True
    assert (result["provider_calls"], result["formal_attempts"], result["model_tokens"]) == (0, 0, 0)


def test_canary_is_single_use_and_records_no_response_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    release = {"ready": True, "release_revision": "a" * 40, "network_access_medium": "wifi"}
    monkeypatch.setattr(runner, "collect_preflight", lambda *_args, **_kwargs: release)
    report = runner.collect_provider_canary(manifest, output_dir=tmp_path, model_factory=lambda _provider: CanaryModel())
    assert report["passed"] is True
    assert report["request_count"] == 1
    assert report["recorded_tokens"] == 10
    assert "CANARY_OK" not in json.dumps(report)
    marker = _load(tmp_path / manifest["execution"]["canary_marker"])
    assert marker["status"] == "passed"
    with pytest.raises(runner.AuthorizedPilotError, match="不可覆盖"):
        runner.collect_provider_canary(manifest, output_dir=tmp_path, model_factory=lambda _provider: CanaryModel())


def test_batch_reports_per_case_macro_and_counts_canary_tokens(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    revision = "a" * 40
    digest = protocol.canonical_sha256(manifest)
    canary = {
        "manifest_sha256": digest,
        "release_revision": revision,
        "recorded_tokens": 10,
        "passed": True,
    }
    runner._write_once(
        tmp_path / manifest["execution"]["canary_marker"],
        {"manifest_sha256": digest, "release_revision": revision, "status": "passed"},
    )
    runner._write_once(tmp_path / "reports/provider-canary.json", canary)
    monkeypatch.setattr(runner.protocol, "verify_frozen_components", lambda *_args: None)
    monkeypatch.setattr(runner, "_require_output_dir", lambda *_args: None)
    monkeypatch.setattr(runner, "require_release_identity", lambda *_args: {"branch": "main", "revision": revision, "origin_main": revision})
    monkeypatch.setattr(runner, "require_network_medium", lambda *_args: "wifi")
    monkeypatch.setattr(runner.primary, "require_compose_dood", lambda: None)
    monkeypatch.setattr(runner, "require_zero_managed_containers", lambda: None)

    report = runner.run_pilot(
        manifest,
        output_dir=tmp_path,
        pair_executor=lambda _manifest, pair, _pair_dir: _outcome(pair),
    )
    assert report["observed_pairs"] == 6
    assert set(report["per_case"]) == {"cppitertools", "janet", "libcheck"}
    assert all(item["scheduled_pairs"] == 2 for item in report["per_case"].values())
    assert report["equal_weight_macro_average"]["case_weights"] == {
        "cppitertools": "1/3",
        "janet": "1/3",
        "libcheck": "1/3",
    }
    assert report["recorded_tokens"] == 1_210
    assert report["p_value_computed"] is False
    assert report["providers_pooled"] is False
    assert _load(tmp_path / manifest["execution"]["batch_marker"])["status"] == "passed"


def test_new_files_do_not_contain_secret_values() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "sk-" not in source
    assert "OpenAI_AK" not in source
