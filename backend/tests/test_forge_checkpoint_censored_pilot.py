from __future__ import annotations

import copy
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = REPO_ROOT / "scripts"
PROTOCOL_PATH = SCRIPT_ROOT / "forge_checkpoint_censored_pilot_protocol.py"
RUNNER_PATH = SCRIPT_ROOT / "forge_checkpoint_censored_pilot_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-checkpoint-censored-pilot-v1.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-checkpoint-censored-pilot-v1.schema.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load("forge_checkpoint_censored_pilot_protocol_test", PROTOCOL_PATH)
runner = _load("forge_checkpoint_censored_pilot_runner_test", RUNNER_PATH)


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_is_deterministic_balanced_and_bounded() -> None:
    manifest = _manifest()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert protocol.generate_manifest() == manifest
    assert protocol.validate_manifest(manifest) == manifest
    protocol.verify_frozen_components(manifest)
    assert schema == protocol.schema_document(manifest)
    assert len(manifest["schedule"]) == 6
    assert [item["arm_order"][0] for item in manifest["schedule"]] == [
        "baseline",
        "treatment",
    ] * 3
    assert manifest["provider"]["request_timeout_seconds"] == 300
    assert manifest["provider"]["max_retries"] == 0
    assert manifest["budget"]["stage_maximum_recorded_tokens"] == 1_440_000
    assert manifest["stopping"] == {
        "endpoint_timeout_censors_pair_and_continues": True,
        "cleanup_or_identity_failure_stops_batch": True,
        "non_endpoint_failure_stops_batch": True,
        "retry_forbidden": True,
        "replacement_forbidden": True,
        "backfill_forbidden": True,
        "schedule_extension_forbidden": True,
    }


def test_manifest_rejects_schedule_budget_and_transport_drift() -> None:
    manifest = _manifest()
    manifest["schedule"].reverse()
    with pytest.raises(protocol.ProtocolError, match="冻结协议"):
        protocol.validate_manifest(manifest)

    manifest = _manifest()
    manifest["budget"]["stage_maximum_recorded_tokens"] += 1
    with pytest.raises(protocol.ProtocolError, match="冻结协议"):
        protocol.validate_manifest(manifest)

    manifest = _manifest()
    manifest["provider"]["request_timeout_seconds"] = 600
    with pytest.raises(protocol.ProtocolError, match="冻结协议"):
        protocol.validate_manifest(manifest)


def _patch_preflight(monkeypatch: pytest.MonkeyPatch, manifest: dict, output_dir: Path) -> dict:
    candidate = copy.deepcopy(manifest)
    candidate["execution"]["evidence_directory"] = str(output_dir)
    monkeypatch.setattr(runner.protocol, "validate_manifest", lambda value, *_args: value)
    monkeypatch.setattr(runner.protocol, "verify_frozen_components", lambda *_args: None)
    monkeypatch.setattr(runner.protocol, "verify_parent_evidence", lambda *_args: {})
    monkeypatch.setattr(
        runner,
        "require_release_identity",
        lambda *_args: {
            "branch": "main",
            "revision": "a" * 40,
            "origin_main": "a" * 40,
        },
    )
    monkeypatch.setattr(runner, "require_network_medium", lambda *_args: "wifi")
    monkeypatch.setattr(runner.primary, "require_compose_dood", lambda: None)
    monkeypatch.setattr(runner, "require_zero_managed_containers", lambda: None)
    return candidate


def _fake_outcome(manifest: dict, pair: dict, *, censored: bool) -> dict:
    metrics = {
        "model_requests": 1,
        "submit_attempts": 1,
        "clean_replay_attempts": 1,
        "recorded_tokens": 10,
        "ledger_wall_clock_seconds": 2.0,
    }
    return {
        "schema_version": "forge-checkpoint-censored-pair-outcome-1.0.0",
        "document_type": "forge_checkpoint_censored_pair_outcome",
        "manifest_sha256": runner.protocol.canonical_sha256(manifest),
        "pair_id": pair["pair_id"],
        "order": pair["order"],
        "arm_order": pair["arm_order"],
        "status": "endpoint_censored" if censored else "complete",
        "endpoint_timeout_arm": pair["arm_order"][0] if censored else None,
        "recorded_tokens": 10 if censored else 20,
        "metrics_by_arm": ({pair["arm_order"][0]: metrics} if censored else {"baseline": metrics, "treatment": metrics}),
    }


def test_schedule_continues_after_endpoint_censoring_without_replacement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _patch_preflight(monkeypatch, _manifest(), tmp_path)
    calls: list[str] = []

    def execute(value: dict, pair: dict, _pair_dir: Path) -> dict:
        calls.append(pair["pair_id"])
        return _fake_outcome(value, pair, censored=pair["order"] in {2, 5})

    report = runner.run_pilot(manifest, output_dir=tmp_path, pair_executor=execute)

    assert calls == [f"pair-{number:02d}" for number in range(1, 7)]
    assert report["status"] == "completed_with_censoring"
    assert report["itt_attrition"] == {
        "scheduled_pairs": 6,
        "observed_pairs": 6,
        "complete_pairs": 4,
        "endpoint_censored_pairs": 2,
        "endpoint_censored_pair_ids": ["pair-02", "pair-05"],
        "endpoint_timeout_arms": {"baseline": 1, "treatment": 1},
        "observed_arm_attempts": {"baseline": 5, "treatment": 5},
    }
    assert report["conditional_mechanism"]["eligible_complete_pairs"] == 4
    assert report["conditional_mechanism"]["mean_paired_deltas"]["recorded_tokens"] == 0
    assert len(list((tmp_path / "pairs").glob("*/reports/pair-outcome.json"))) == 6

    resumed = runner.run_pilot(
        manifest,
        output_dir=tmp_path,
        pair_executor=lambda *_args: pytest.fail("终态 pair 不得重跑"),
    )
    assert resumed == report


def test_non_endpoint_outcome_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _patch_preflight(monkeypatch, _manifest(), tmp_path)

    with pytest.raises(runner.PilotError, match="非 endpoint"):
        runner.run_pilot(
            manifest,
            output_dir=tmp_path,
            pair_executor=lambda *_args: {"status": "runtime_failed"},
        )
    marker = json.loads((tmp_path / runner.BATCH_MARKER).read_text(encoding="utf-8"))
    assert marker["status"] == "failed"
    assert marker["error_class"] == "PilotError"


def test_timeout_classifier_requires_hashed_endpoint_failure_and_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest()
    pair = manifest["schedule"][0]
    pair_manifest = runner._pair_manifest(manifest, pair)
    pair_dir = tmp_path / pair["pair_id"]
    pair_manifest["execution"]["evidence_directory"] = str(pair_dir)
    marker = {
        "status": "failed",
        "manifest_sha256": protocol.canonical_sha256(pair_manifest),
    }
    runner._write_once(pair_dir / "markers" / runner.PAIR_MARKER, marker)

    database = pair_dir / "checkpoint" / "coordinator.sqlite"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE checkpoint_capture (capture_id TEXT, phase TEXT, payload_json TEXT)")
        connection.execute(
            "INSERT INTO checkpoint_capture VALUES (?, ?, ?)",
            ("capture-1", "cleaned", json.dumps({"cleanup": {"succeeded": True}})),
        )

    ledger = runner.primary.ExperimentLedger.create(
        pair_dir / "ledgers" / "baseline.jsonl",
        experiment_id="experiment_1234567890abcdef1234567890abcdef",
        physical_attempt_id="mechanism_attempt_1234567890abcdef1234567890abcdef",
        context={"scope": "test"},
    )
    ledger.append(
        "model.request_started",
        {
            "attempt": 1,
            "configured_model": "deepseek-v4-flash",
            "max_attempts": 1,
            "model_call_id": "model_call_1234567890abcdef1234567890abcdef",
            "model_request_id": "model_request_1234567890abcdef1234567890abcdef",
            "observed_endpoint": "https://api.deepseek.com",
            "provider_max_retries": 0,
            "request_timeout_seconds": 300,
            "role": "compiler",
        },
    )
    ledger.append(
        "model.request_failed",
        {
            "attempt": 1,
            "classification": "timeout",
            "latency_seconds": 300.1,
            "max_attempts": 1,
            "model_call_id": "model_call_1234567890abcdef1234567890abcdef",
            "model_request_id": "model_request_1234567890abcdef1234567890abcdef",
            "retriable": True,
            "retry_exhausted": True,
            "status_code": None,
        },
    )
    ledger.append(
        "failure.recorded",
        {
            "classification": "timeout",
            "domain": "model_endpoint",
            "failure_id": "failure_1234567890abcdef1234567890abcdef",
            "model_call_id": "model_call_1234567890abcdef1234567890abcdef",
            "model_request_id": "model_request_1234567890abcdef1234567890abcdef",
            "primary": True,
            "secondary_classifications": ["retry_exhausted"],
        },
    )
    monkeypatch.setattr(runner, "require_zero_managed_containers", lambda: None)

    outcome = runner._endpoint_timeout_outcome(
        manifest,
        pair,
        pair_manifest,
        pair_dir,
        runner.primary.CanaryError("timeout"),
    )
    assert outcome["status"] == "endpoint_censored"
    assert outcome["endpoint_timeout_arm"] == "baseline"
    assert outcome["recorded_tokens"] == 0
    assert outcome["metrics_by_arm"]["baseline"]["model_requests"] == 1

    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE checkpoint_capture SET phase = 'cleanup_pending'")
    with pytest.raises(runner.PilotError, match="cleanup 未闭合"):
        runner._endpoint_timeout_outcome(
            manifest,
            pair,
            pair_manifest,
            pair_dir,
            runner.primary.CanaryError("timeout"),
        )


def test_runtime_pair_manifest_binds_pair_identity_and_no_reachability() -> None:
    manifest = _manifest()
    first = runner._pair_manifest(manifest, manifest["schedule"][0])
    second = runner._pair_manifest(manifest, manifest["schedule"][1])

    assert first["pilot"]["pair_id"] == "pair-01"
    assert second["pilot"]["pair_id"] == "pair-02"
    assert first["continuation"]["arm_order"] == ["baseline", "treatment"]
    assert second["continuation"]["arm_order"] == ["treatment", "baseline"]
    assert first["budget"]["reachability_requests"] == 0
    assert protocol.canonical_sha256(first) != protocol.canonical_sha256(second)
