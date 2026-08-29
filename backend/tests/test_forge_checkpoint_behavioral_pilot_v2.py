from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = REPO_ROOT / "scripts"
PROTOCOL_PATH = SCRIPT_ROOT / "forge_checkpoint_behavioral_pilot_v2_protocol.py"
RUNNER_PATH = SCRIPT_ROOT / "forge_checkpoint_behavioral_pilot_v2_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-checkpoint-behavioral-pilot-v2.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-checkpoint-behavioral-pilot-v2.schema.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load("forge_checkpoint_behavioral_pilot_v2_protocol_test", PROTOCOL_PATH)
runner = _load("forge_checkpoint_behavioral_pilot_v2_runner_test", RUNNER_PATH)


class GraphRecursionError(RuntimeError):
    pass


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _ledger(tmp_path: Path, arm: str):
    return runner.primary.ExperimentLedger.create(
        tmp_path / f"{arm}.jsonl",
        experiment_id="experiment_1234567890abcdef1234567890abcdef",
        physical_attempt_id="mechanism_attempt_1234567890abcdef1234567890abcdef",
        context={"arm": arm},
    )


def _request(ledger, *, tokens: int = 10) -> None:
    suffix = len([event for event in ledger.read() if event["event"] == "model.request_started"]) + 1
    call_id = f"model_call_{suffix:02d}_1234567890abcdef1234567890"
    request_id = f"model_request_{suffix:02d}_1234567890abcdef123456"
    ledger.append(
        "model.request_started",
        {
            "attempt": 1,
            "configured_model": "deepseek-v4-flash",
            "max_attempts": 1,
            "model_call_id": call_id,
            "model_request_id": request_id,
            "observed_endpoint": "https://api.deepseek.com",
            "provider_max_retries": 0,
            "request_timeout_seconds": 300,
            "role": "compiler",
        },
    )
    ledger.append(
        "model.request_completed",
        {
            "actual_model": "deepseek-v4-flash",
            "attempt": 1,
            "latency_seconds": 1.0,
            "model_call_id": call_id,
            "model_request_id": request_id,
            "status_code": 200,
            "token_usage": {"input_tokens": tokens - 1, "output_tokens": 1, "total_tokens": tokens},
        },
    )


def _timeout_request(ledger) -> None:
    call_id = "model_call_timeout_1234567890abcdef123456"
    request_id = "model_request_timeout_1234567890abcdef1234"
    ledger.append(
        "model.request_started",
        {
            "attempt": 1,
            "configured_model": "deepseek-v4-flash",
            "max_attempts": 1,
            "model_call_id": call_id,
            "model_request_id": request_id,
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
            "model_call_id": call_id,
            "model_request_id": request_id,
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
            "failure_id": "failure_timeout_1234567890abcdef1234567890",
            "model_call_id": call_id,
            "model_request_id": request_id,
            "primary": True,
            "secondary_classifications": ["retry_exhausted"],
        },
    )


def _metrics(tokens: int = 10) -> dict:
    return {
        "model_requests": 1,
        "submit_attempts": 0,
        "clean_replay_attempts": 0,
        "recorded_tokens": tokens,
        "ledger_wall_clock_seconds": 1.0,
    }


def _arm(arm: str, *, infrastructure: str = "valid", behavior: str = "completed", verification: str = "passed", tokens: int = 10) -> dict:
    return {
        "arm": arm,
        "status": "observed",
        "infrastructure": {"status": infrastructure},
        "model_behavior": {"status": behavior, "terminal_error_class": None},
        "verification_outcome": {"status": verification, "submit_attempts": int(verification != "not_attempted"), "clean_replay_attempts": int(verification == "passed")},
        "recorded_tokens": tokens,
        "metrics": _metrics(tokens),
    }


def _outcome(manifest: dict, pair: dict, *, endpoint: bool = False, baseline_passed: bool = True) -> dict:
    arms = {
        "baseline": _arm("baseline", behavior="completed" if baseline_passed else "graph_step_limit", verification="passed" if baseline_passed else "not_attempted"),
        "treatment": _arm("treatment"),
    }
    if endpoint:
        arms["baseline"] = _arm("baseline", infrastructure="endpoint_censored", behavior="not_observed", verification="not_attempted", tokens=0)
    eligible = not endpoint
    success = {arm: value["verification_outcome"]["status"] == "passed" for arm, value in arms.items()}
    return {
        "schema_version": "forge-checkpoint-behavioral-pair-outcome-2.0.0",
        "document_type": "forge_checkpoint_behavioral_pair_outcome",
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "pair_manifest_sha256": "a" * 64,
        "pair_id": pair["pair_id"],
        "order": pair["order"],
        "arm_order": pair["arm_order"],
        "status": "observed" if eligible else "observed_with_endpoint_censoring",
        "arms": arms,
        "recorded_tokens": sum(value["recorded_tokens"] for value in arms.values()),
        "primary_mechanism_eligible": eligible,
        "repair_success": success,
        "paired_repair_conversion_delta": int(success["treatment"]) - int(success["baseline"]) if eligible else None,
    }


def test_manifest_freezes_fresh_v2_identity_and_excludes_old_pairs() -> None:
    manifest = _manifest()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert protocol.generate_manifest() == manifest
    assert protocol.validate_manifest(manifest) == manifest
    protocol.verify_frozen_components(manifest)
    assert schema == protocol.schema_document(manifest)
    assert manifest["authorization"]["selected_option"] == "A"
    assert manifest["historical_exclusion"]["pooled_into_v2"] is False
    assert manifest["historical_exclusion"]["recorded_tokens"] == 67_121
    assert [item["pair_id"] for item in manifest["schedule"]] == [f"v2-pair-{number:02d}" for number in range(1, 7)]
    assert manifest["budget"]["stage_maximum_recorded_tokens"] == 1_440_000


def test_graph_recursion_is_model_behavior_outcome_not_infrastructure_failure(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, "baseline")
    for _ in range(8):
        _request(ledger, tokens=10)

    result = runner.classify_arm_terminal(_manifest(), arm="baseline", ledger=ledger, error=GraphRecursionError("limit"))

    assert result["infrastructure"]["status"] == "valid"
    assert result["model_behavior"]["status"] == "graph_step_limit"
    assert result["verification_outcome"]["status"] == "not_attempted"
    assert result["recorded_tokens"] == 80
    assert ledger.read()[-1]["event"] == "experiment.completed"


def test_endpoint_timeout_is_censored_arm_and_not_model_behavior(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, "treatment")
    _timeout_request(ledger)

    result = runner.classify_arm_terminal(_manifest(), arm="treatment", ledger=ledger, error=TimeoutError("endpoint"))

    assert result["infrastructure"]["status"] == "endpoint_censored"
    assert result["model_behavior"]["status"] == "not_observed"
    assert result["verification_outcome"]["status"] == "not_attempted"


def test_parent_adapter_continues_second_arm_after_classified_behavior_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest()
    pair_manifest = runner._pair_manifest(manifest, manifest["schedule"][0])
    baseline = _ledger(tmp_path, "baseline")
    treatment = _ledger(tmp_path, "treatment")
    _request(baseline)
    _request(treatment)
    original = runner.primary.run_arm_continuation

    async def fake_continuation(*_args, **kwargs):
        if kwargs["arm"] == "baseline":
            raise GraphRecursionError("limit")
        kwargs["ledger"].append("experiment.completed", {"status": "passed"})
        return {
            "arm": "treatment",
            "status": "passed",
            "physical_attempt_id": kwargs["ledger"].physical_attempt_id,
            "model_requests": 1,
            "recorded_tokens": 10,
            "actual_model": "deepseek-v4-flash",
            "session_status": "verified",
            "replay_attempts": 1,
            "ledger_head_sha256": kwargs["ledger"].read()[-1]["event_sha256"],
        }

    monkeypatch.setattr(runner.primary, "run_arm_continuation", fake_continuation)
    with asyncio.Runner() as async_runner:
        with runner._adapt_parent_runner(manifest, pair_manifest, async_runner):
            first = async_runner.run(runner.primary.run_arm_continuation(arm="baseline", ledger=baseline))
            second = async_runner.run(runner.primary.run_arm_continuation(arm="treatment", ledger=treatment))

    assert first["model_behavior"]["status"] == "graph_step_limit"
    assert second["verification_outcome"]["status"] == "passed"
    assert runner.primary.run_arm_continuation is fake_continuation
    monkeypatch.setattr(runner.primary, "run_arm_continuation", original)


def test_unclassified_request_failure_fails_closed(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, "baseline")
    call_id = "model_call_connection_1234567890abcdef1234"
    request_id = "model_request_connection_1234567890abcdef12"
    ledger.append(
        "model.request_started",
        {
            "attempt": 1,
            "configured_model": "deepseek-v4-flash",
            "max_attempts": 1,
            "model_call_id": call_id,
            "model_request_id": request_id,
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
            "classification": "connection_error",
            "latency_seconds": 1.0,
            "max_attempts": 1,
            "model_call_id": call_id,
            "model_request_id": request_id,
            "retriable": False,
            "retry_exhausted": True,
            "status_code": None,
        },
    )

    with pytest.raises(runner.BehavioralPilotError, match="未分类"):
        runner.classify_arm_terminal(_manifest(), arm="baseline", ledger=ledger, error=RuntimeError("unknown"))


def _patch_preflight(monkeypatch: pytest.MonkeyPatch, manifest: dict, output_dir: Path) -> dict:
    candidate = copy.deepcopy(manifest)
    candidate["execution"]["evidence_directory"] = str(output_dir)
    monkeypatch.setattr(runner.protocol, "validate_manifest", lambda value, *_args: value)
    monkeypatch.setattr(runner.protocol, "verify_historical_evidence", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(runner, "require_release_identity", lambda *_args: {"branch": "main", "revision": "b" * 40, "origin_main": "b" * 40})
    monkeypatch.setattr(runner, "require_network_medium", lambda *_args: "wifi")
    monkeypatch.setattr(runner.primary, "require_compose_dood", lambda: None)
    monkeypatch.setattr(runner, "require_zero_managed_containers", lambda: None)
    return candidate


def test_batch_keeps_model_behavior_failures_in_estimand_and_continues_endpoint_pair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _patch_preflight(monkeypatch, _manifest(), tmp_path)
    calls: list[str] = []

    def execute(value: dict, pair: dict, _pair_dir: Path) -> dict:
        calls.append(pair["pair_id"])
        if pair["order"] == 2:
            return _outcome(value, pair, baseline_passed=False)
        if pair["order"] == 3:
            return _outcome(value, pair, endpoint=True)
        return _outcome(value, pair)

    report = runner.run_pilot(manifest, output_dir=tmp_path, pair_executor=execute)

    assert calls == [f"v2-pair-{number:02d}" for number in range(1, 7)]
    assert report["itt_attrition"]["observed_pairs"] == 6
    assert report["itt_attrition"]["attempted_arms"] == {"baseline": 6, "treatment": 6}
    assert report["itt_attrition"]["endpoint_censored_pairs"] == 1
    assert report["primary_mechanism"]["eligible_pairs"] == 5
    assert report["primary_mechanism"]["repair_success"] == {"baseline": 4, "treatment": 5}
    assert report["primary_mechanism"]["model_behavior_counts"]["baseline"] == {"completed": 4, "graph_step_limit": 1, "not_observed": 1}

    resumed = runner.run_pilot(manifest, output_dir=tmp_path, pair_executor=lambda *_args: pytest.fail("v2 终态不得重跑"))
    assert resumed == report


def test_manifest_rejects_old_pair_reuse_or_schedule_extension() -> None:
    manifest = _manifest()
    manifest["schedule"][0]["pair_id"] = "pair-01"
    with pytest.raises(protocol.ProtocolError, match="冻结协议"):
        protocol.validate_manifest(manifest)

    manifest = _manifest()
    manifest["schedule"].append(copy.deepcopy(manifest["schedule"][-1]))
    with pytest.raises(protocol.ProtocolError, match="冻结协议"):
        protocol.validate_manifest(manifest)
