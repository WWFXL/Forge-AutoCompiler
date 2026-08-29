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
PROTOCOL_PATH = SCRIPT_ROOT / "forge_checkpoint_censored_pilot_recovery_protocol.py"
RUNNER_PATH = SCRIPT_ROOT / "forge_checkpoint_censored_pilot_recovery_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-checkpoint-censored-pilot-recovery-v1.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-checkpoint-censored-pilot-recovery-v1.schema.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load("forge_checkpoint_censored_pilot_recovery_protocol_test", PROTOCOL_PATH)
runner = _load("forge_checkpoint_censored_pilot_recovery_runner_test", RUNNER_PATH)


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _metrics() -> dict:
    return {
        "model_requests": 1,
        "submit_attempts": 1,
        "clean_replay_attempts": 1,
        "recorded_tokens": 10,
        "ledger_wall_clock_seconds": 2.0,
    }


def _outcome(manifest: dict, pair: dict, tokens: int = 20) -> dict:
    return {
        "schema_version": "forge-checkpoint-censored-pair-outcome-1.0.0",
        "document_type": "forge_checkpoint_censored_pair_outcome",
        "manifest_sha256": runner.protocol.canonical_sha256(manifest),
        "pair_id": pair["pair_id"],
        "order": pair["order"],
        "arm_order": pair["arm_order"],
        "status": "complete",
        "recorded_tokens": tokens,
        "metrics_by_arm": {"baseline": _metrics(), "treatment": _metrics()},
    }


def test_manifest_freezes_one_import_and_only_five_remaining_pairs() -> None:
    manifest = _manifest()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert protocol.generate_manifest() == manifest
    assert protocol.validate_manifest(manifest) == manifest
    protocol.verify_frozen_components(manifest)
    assert schema == protocol.schema_document(manifest)
    assert manifest["recovery"]["imported_pair"]["pair_id"] == "pair-01"
    assert manifest["recovery"]["imported_pair"]["rerun_forbidden"] is True
    assert manifest["execution"]["recovery_execution_pairs"] == [
        "pair-02",
        "pair-03",
        "pair-04",
        "pair-05",
        "pair-06",
    ]
    assert manifest["budget"]["imported_recorded_tokens"] == 23_811
    assert manifest["budget"]["additional_recorded_token_limit"] == 1_200_000
    assert manifest["budget"]["stage_maximum_recorded_tokens"] == 1_440_000


def test_copy_auditor_reads_latest_wal_without_mutating_source(
    tmp_path: Path,
) -> None:
    pair_dir = tmp_path / "pair-02"
    database = pair_dir / "checkpoint" / "coordinator.sqlite"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("CREATE TABLE checkpoint_capture (capture_id TEXT, phase TEXT, payload_json TEXT)")
        connection.execute(
            "INSERT INTO checkpoint_capture VALUES (?, ?, ?)",
            ("capture-1", "committed", json.dumps({"cleanup": {"succeeded": False}})),
        )
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.execute(
            "UPDATE checkpoint_capture SET phase = ?, payload_json = ?",
            ("cleaned", json.dumps({"cleanup": {"succeeded": True}})),
        )
        connection.commit()
        assert Path(f"{database}-wal").stat().st_size > 0
        before = runner._file_snapshot(database)

        result = runner.coordinator_terminal_from_copy(pair_dir)

        assert runner._file_snapshot(database) == before
        assert result["phase"] == "cleaned"
        assert result["cleanup_succeeded"] is True
        assert "coordinator.sqlite-wal" in result["source_files"]


def _patch_preflight(monkeypatch: pytest.MonkeyPatch, manifest: dict, output_dir: Path) -> dict:
    candidate = copy.deepcopy(manifest)
    candidate["execution"]["evidence_directory"] = str(output_dir)
    monkeypatch.setattr(runner.protocol, "validate_manifest", lambda value, *_args: value)
    monkeypatch.setattr(runner.protocol, "verify_frozen_components", lambda *_args: None)
    monkeypatch.setattr(runner.protocol, "verify_v1_evidence", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(runner.v1_protocol, "verify_parent_evidence", lambda *_args: {})
    monkeypatch.setattr(
        runner,
        "require_release_identity",
        lambda *_args: {
            "branch": "main",
            "revision": "a" * 40,
            "origin_main": "a" * 40,
        },
    )
    monkeypatch.setattr(runner.v1_runner, "require_network_medium", lambda *_args: "wifi")
    monkeypatch.setattr(runner.v1_runner.primary, "require_compose_dood", lambda: None)
    monkeypatch.setattr(runner.v1_runner, "require_zero_managed_containers", lambda: None)
    pair_one = _outcome(candidate, candidate["schedule"][0], 23_811)
    pair_one["source"] = {"kind": "frozen-v1-complete-pair", "rerun": False}
    monkeypatch.setattr(runner, "_import_pair_one", lambda *_args: pair_one)
    return candidate


def test_recovery_imports_pair_one_and_executes_only_pairs_two_through_six(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _patch_preflight(monkeypatch, _manifest(), tmp_path)
    calls: list[str] = []

    def execute(value: dict, pair: dict, _pair_dir: Path) -> dict:
        calls.append(pair["pair_id"])
        return _outcome(value, pair)

    report = runner.run_recovery(manifest, output_dir=tmp_path, pair_executor=execute)

    assert calls == [f"pair-{number:02d}" for number in range(2, 7)]
    assert report["itt_attrition"]["scheduled_pairs"] == 6
    assert report["itt_attrition"]["complete_pairs"] == 6
    assert report["recorded_tokens"] == 23_911
    assert report["recovery"] == {
        "imported_pair_ids": ["pair-01"],
        "executed_pair_ids": [f"pair-{number:02d}" for number in range(2, 7)],
        "replacement": False,
        "backfill": False,
        "coordinator_audit": "copy-main-wal-shm-then-read-copy",
    }
    assert not (tmp_path / "pairs" / "pair-01").exists()

    resumed = runner.run_recovery(
        manifest,
        output_dir=tmp_path,
        pair_executor=lambda *_args: pytest.fail("恢复终态不得重跑"),
    )
    assert resumed == report


def test_manifest_rejects_pair_one_rerun_or_extra_budget() -> None:
    manifest = _manifest()
    manifest["execution"]["recovery_execution_pairs"].insert(0, "pair-01")
    with pytest.raises(protocol.ProtocolError, match="冻结协议"):
        protocol.validate_manifest(manifest)

    manifest = _manifest()
    manifest["budget"]["additional_recorded_token_limit"] += 1
    with pytest.raises(protocol.ProtocolError, match="冻结协议"):
        protocol.validate_manifest(manifest)
