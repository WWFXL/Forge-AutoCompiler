from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/forge_jev_controller_replay_qualification.py"
SPEC = importlib.util.spec_from_file_location("forge_jev_controller_replay_qualification", SCRIPT)
assert SPEC and SPEC.loader
replay = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = replay
SPEC.loader.exec_module(replay)


def test_cli_exposes_only_zero_provider_replay_commands() -> None:
    choices = replay._parser()._subparsers._group_actions[0].choices
    assert set(choices) == {"bind-identity", "validate", "preflight", "run", "report"}
    assert "run-provider" not in choices


def test_fault_schedule_and_reasons_are_frozen() -> None:
    assert len(replay.FAULT_SCENARIOS) == 18
    assert set(replay.FAULT_SCENARIOS) == set(replay.EXPECTED_FAULT_REASON)
    assert replay.EXPECTED_EVALUATION_STATES * len(replay.FAULT_SCENARIOS) == 324


def test_parent_inputs_match_frozen_reports_and_evidence() -> None:
    parent = replay.validate_parent_inputs()
    assert parent["v6"]["decision"] == "proceed_to_controller_replay_qualification"
    assert parent["evaluation_file_counts"] == {"attempts": 18, "observations": 18, "requests": 18}
    assert parent["evidence_inventory_canonical_sha256"] == replay.V6_EVIDENCE_INVENTORY_SHA256


def test_manifest_generation_binds_implementation_components(monkeypatch: pytest.MonkeyPatch) -> None:
    revision = "a" * 40
    monkeypatch.setattr(replay, "_canonical_revision", lambda value: revision)
    monkeypatch.setattr(replay, "_git_blob", lambda _revision, path: path.encode())
    manifest = replay.build_manifest(revision)
    assert manifest["implementation_revision"] == revision
    assert manifest["authorization"] == {
        "credential_reads": 0,
        "provider_calls": 0,
        "model_tokens": 0,
        "model_cost_usd": 0,
        "formal_replay": True,
        "formal_evidence_write": True,
        "historical_evidence_write": False,
        "shell_action_execution": False,
    }
    assert manifest["schedule"]["expected_fault_case_count"] == 324
    assert replay.build_schema(manifest)["const"] == manifest


def test_write_once_rejects_existing_path(tmp_path: Path) -> None:
    target = tmp_path / "evidence.json"
    replay._write_once_json(target, {"first": True})
    assert json.loads(target.read_text(encoding="utf-8")) == {"first": True}
    with pytest.raises(replay.ReplayError, match="create-once"):
        replay._write_once_json(target, {"second": True})


def test_fault_case_does_not_mutate_frozen_controller_inputs() -> None:
    record = replay._load_evaluation_records(replay.validate_parent_inputs())[0]
    state, candidates, decision, _, capabilities = replay._controller_inputs(record, replay.load_json(replay.V6_CALIBRATION))
    original_probabilities = dict(decision.probabilities)
    _, _, changed, _ = replay._fault_case("probability_non_finite", state, candidates, decision, capabilities)
    assert changed is not None
    assert dict(decision.probabilities) == original_probabilities
    assert changed.probabilities is not decision.probabilities


def test_preregistration_freezes_claim_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    revision = "b" * 40
    monkeypatch.setattr(replay, "_canonical_revision", lambda value: revision)
    monkeypatch.setattr(replay, "_git_blob", lambda _revision, path: path.encode())
    text = replay.render_preregistration(replay.build_manifest(revision))
    assert "不执行真实构建动作" in text
    assert "不估计端到端成功率" in text
    assert "proceed_to_end_to_end_canary" in text
