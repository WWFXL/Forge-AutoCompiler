from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "scripts" / "forge_verifier_repair_authorized_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts" / "forge_verifier_repair_authorized_runner.py"
REPORT_PATH = REPO_ROOT / "scripts" / "forge_verifier_repair_authorized_report.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-repair-pilot-authorized.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_module("forge_verifier_repair_authorized_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_verifier_repair_authorized_runner_test", RUNNER_PATH)
report = _load_module("forge_verifier_repair_authorized_report_test", REPORT_PATH)


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_authorized_protocol_is_deterministic_and_binds_parent() -> None:
    manifest = _manifest()
    assert protocol.validate_manifest(manifest) == manifest
    assert protocol.generate_manifest() == manifest
    assert manifest["scope"]["collection_authorized"] is True
    assert manifest["authorization"]["parent_runtime"]["canonical_sha256"] == protocol.PARENT_CANONICAL_SHA256
    assert manifest["authorization"]["budget_confirmation"]["maximum_recorded_tokens"] == 2_400_000
    assert len(manifest["collection_plan"]) == 12
    assert len({slot["pair_id"] for slot in manifest["collection_plan"]}) == 6
    assert len({condition["id"] for condition in manifest["conditions"]}) == 4
    assert {condition["provider_condition"] for condition in manifest["conditions"]} == {
        "richlab-gpt-5.5",
        "deepseek-v4-flash",
    }
    assert manifest["analysis_plan"]["repair_conversion_definition"] == "adjacent_actionable_classification_to_passed_feedback"


def test_authorized_protocol_rejects_budget_or_schedule_drift() -> None:
    manifest = _manifest()
    manifest["budget"]["maximum_recorded_tokens"] += 1
    with pytest.raises(protocol.ProtocolError):
        protocol.validate_manifest(manifest)


def test_canary_invokes_each_provider_once_and_projects_four_conditions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest()
    calls: list[str] = []

    monkeypatch.setattr(runner, "_require_authorized_output_dir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runner, "_formal_container_ids", lambda: [])
    monkeypatch.setattr(runner._runner, "_running_inside_compose_dood", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(runner._runner, "collect_preflight", lambda *_args, **_kwargs: {"ready": True})
    monkeypatch.setenv("FORGE_NETWORK_ACCESS_MEDIUM", "mobile_hotspot")

    def fake_canary(profile: dict) -> dict:
        calls.append(profile["roles"]["lead"])
        return {
            "model": profile["roles"]["lead"],
            "endpoint": profile["endpoint"],
            "credential_env": profile["credential_env"],
            "duration_ms": 1,
            "response_nonempty": True,
            "response_sha256": "0" * 64,
            "error_class": None,
            "passed": True,
        }

    monkeypatch.setattr(runner, "_invoke_provider_canary", fake_canary)
    result = runner.collect_provider_canary(
        manifest,
        manifest_path=MANIFEST_PATH,
        output_dir=tmp_path,
        repo_root=REPO_ROOT,
    )
    assert sorted(calls) == ["deepseek-v4-flash", "gpt-5.5"]
    assert result["provider_request_count"] == 2
    assert len(result["providers"]) == 2
    assert len(result["conditions"]) == 4
    assert result["network_access_medium"] == "mobile_hotspot"
    assert result["passed"] is True


def test_canary_rejects_unconfirmed_network_before_consuming_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest()
    monkeypatch.setattr(runner, "_require_authorized_output_dir", lambda *_args, **_kwargs: None)
    monkeypatch.delenv("FORGE_NETWORK_ACCESS_MEDIUM", raising=False)
    with pytest.raises(runner.RunnerError):
        runner.collect_provider_canary(
            manifest,
            manifest_path=MANIFEST_PATH,
            output_dir=tmp_path,
            repo_root=REPO_ROOT,
        )
    assert not runner._canary_marker_path(tmp_path).exists()


def test_run_attempt_creates_terminal_sidecar_without_model_work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest()
    slot = manifest["collection_plan"][0]
    policy = runner._runner.build_policy(
        manifest,
        case_id=slot["case_id"],
        condition_id=slot["condition_id"],
        repetition=slot["repetition"],
    )
    ledger_path = tmp_path / "attempt.jsonl"
    ledger = runner._runner.ExperimentLedger.create(
        ledger_path,
        experiment_id=runner._runner.new_evidence_id("experiment"),
        physical_attempt_id=runner._runner.new_evidence_id("physical_attempt"),
        context={
            "thread_id": "thread_test",
            "policy": policy.to_payload(),
        },
    )
    monkeypatch.setattr(runner, "_authorized_output_dir", lambda _manifest: tmp_path)
    monkeypatch.setattr(
        runner,
        "_original_run_attempt",
        lambda *_args, **_kwargs: {"status": "failed"},
    )

    result = runner.run_attempt(manifest, ledger.path)
    sidecar = runner.repair_sidecar_path(ledger.path)
    records = runner.repair_runtime.RepairEvidenceLedger(sidecar).read()
    assert result["status"] == "failed"
    assert result["repair_fidelity"]["status"] == "not_exposed"
    assert records[0]["payload"]["order"] == 1
    assert records[-1]["event"] == "repair.context_completed"
    assert records[-1]["payload"] == {"status": "failed"}


def test_pair_budget_only_blocks_start_of_new_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    events = [
        {
            "event": "model.request_completed",
            "payload": {"token_usage": {"total_tokens": 2_400_000}},
        }
    ]
    monkeypatch.setattr(
        runner,
        "_observed_ledgers",
        lambda *_args, **_kwargs: [({}, events)],
    )
    with pytest.raises(runner.RunnerError):
        runner._ensure_pair_budget_remaining(manifest, output_dir=Path("unused"), observed_count=2)
    assert runner._ensure_pair_budget_remaining(manifest, output_dir=Path("unused"), observed_count=1) == 2_400_000


def test_batch_request_must_end_on_complete_pair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest()
    monkeypatch.setattr(runner, "_require_authorized_output_dir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runner, "_observed_ledgers", lambda *_args, **_kwargs: [])
    with pytest.raises(runner.RunnerError):
        runner.run_repair_batch(
            manifest,
            manifest_path=MANIFEST_PATH,
            output_dir=tmp_path,
            max_attempts=1,
            check_endpoint=False,
        )


def test_attempt_summary_derives_repair_conversion_and_costs() -> None:
    manifest = _manifest()
    slot = manifest["collection_plan"][1]
    events = [
        {
            "occurred_at": "2026-08-14T00:00:00+00:00",
            "event": "experiment.started",
            "payload": {},
        },
        {
            "occurred_at": "2026-08-14T00:00:01+00:00",
            "event": "model.request_started",
            "payload": {},
        },
        {
            "occurred_at": "2026-08-14T00:00:02+00:00",
            "event": "model.request_completed",
            "payload": {"token_usage": {"total_tokens": 123}},
        },
        {
            "occurred_at": "2026-08-14T00:00:03+00:00",
            "event": "submit.started",
            "payload": {},
        },
        {
            "occurred_at": "2026-08-14T00:00:04+00:00",
            "event": "replay.started",
            "payload": {},
        },
        {
            "occurred_at": "2026-08-14T00:00:05+00:00",
            "event": "oracle.completed",
            "payload": {"passed": True},
        },
        {
            "occurred_at": "2026-08-14T00:00:06+00:00",
            "event": "experiment.completed",
            "payload": {"status": "passed"},
        },
    ]
    records = [
        {
            "event": "repair.feedback_observed",
            "payload": {
                "actionable": True,
                "primary_classification": "recipe_execution_failed",
                "status": "failed",
            },
        },
        {
            "event": "repair.feedback_observed",
            "payload": {
                "actionable": False,
                "primary_classification": None,
                "status": "passed",
            },
        },
    ]
    summary = report.summarize_attempt(
        manifest,
        slot,
        events,
        records,
        {"status": "passed"},
    )
    assert summary["repair_conversions"] == 1
    assert summary["actionable_verifier_failures"] == 1
    assert summary["recorded_tokens"] == 123
    assert summary["model_requests"] == 1
    assert summary["submit_attempts"] == 1
    assert summary["clean_replay_attempts"] == 1
    assert summary["wall_clock_seconds"] == 6.0


def test_report_orders_ledgers_by_frozen_schedule_not_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest()
    first_path = tmp_path / "z-case" / "first.jsonl"
    second_path = tmp_path / "a-case" / "second.jsonl"
    first_path.parent.mkdir(parents=True)
    second_path.parent.mkdir(parents=True)
    first_path.touch()
    second_path.touch()

    def fake_events(slot: dict, physical_attempt_id: str) -> list[dict]:
        return [
            {
                "physical_attempt_id": physical_attempt_id,
                "event": "experiment.started",
                "payload": {
                    "thread_id": f"thread_{slot['order']}",
                    "policy": {
                        "benchmark_id": manifest["benchmark"]["id"],
                        "manifest_sha256": protocol.manifest_sha256(manifest),
                        "case_id": slot["case_id"],
                        "condition": slot["condition_id"],
                        "repetition": slot["repetition"],
                    },
                },
            }
        ]

    by_path = {
        first_path: fake_events(manifest["collection_plan"][0], "physical_attempt_first"),
        second_path: fake_events(manifest["collection_plan"][1], "physical_attempt_second"),
    }
    monkeypatch.setattr(
        report.ExperimentLedger,
        "verify_path",
        staticmethod(lambda path: by_path[path]),
    )
    monkeypatch.setattr(
        report,
        "_read_completed_sidecar",
        lambda *_args, **_kwargs: ([], {"status": "not_exposed"}),
    )

    def fake_summary(_manifest: dict, slot: dict, *_args, **_kwargs) -> dict:
        return {
            "order": slot["order"],
            "pair_id": slot["pair_id"],
            "case_id": slot["case_id"],
            "provider_condition": slot["provider_condition"],
            "treatment": slot["treatment"],
            "repetition": slot["repetition"],
            "oracle_passed": False,
            "terminal_passed": False,
            "fidelity_status": "not_exposed",
            "recorded_tokens": 0,
            "model_requests": 0,
            "wall_clock_seconds": 0.0,
            "actionable_verifier_failures": 0,
            "repair_conversions": 0,
            "submit_attempts": 0,
            "clean_replay_attempts": 0,
            "failure_transitions": [],
        }

    monkeypatch.setattr(report, "summarize_attempt", fake_summary)
    monkeypatch.setattr(report, "_load_canary", lambda *_args, **_kwargs: {"passed": True})
    result = report.build_report(manifest, tmp_path)
    assert result["collection"]["observed_slots"] == 2
    assert result["paired_analysis"]["collection"]["complete_pairs"] == 1
    assert [attempt["order"] for attempt in result["attempts"]] == [1, 2]
