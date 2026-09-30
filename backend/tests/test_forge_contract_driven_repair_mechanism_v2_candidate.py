"""Issue #367 mechanism v2 独立 36-arm candidate 测试。"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import forge_contract_driven_repair_mechanism_v2_candidate_protocol as protocol  # noqa: E402
import forge_contract_driven_repair_mechanism_v2_candidate_runner as runner  # noqa: E402

MANIFEST_PATH = REPO_ROOT / protocol.MANIFEST_PATH
SCHEMA_PATH = REPO_ROOT / protocol.SCHEMA_PATH
PREREGISTRATION_PATH = REPO_ROOT / protocol.PREREGISTRATION_PATH


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@pytest.fixture
def manifest() -> dict[str, Any]:
    return protocol.load_manifest()


def test_manifest_schema_and_allowed_delta_are_deterministic(
    manifest: dict[str, Any],
) -> None:
    assert manifest == protocol.generate_manifest()
    schema = _load_json(SCHEMA_PATH)
    assert schema == protocol.generate_schema(manifest)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(manifest, schema)
    delta = protocol.validate_allowed_delta(manifest)
    assert delta == {
        "status": "passed",
        "arm_count": 36,
        "new_clone_id_count": 36,
        "new_evaluation_id_count": 36,
        "old_identity_overlap": 0,
        "historical_outcomes_imported": False,
        "formal_collection_execution_authorized": False,
        "provider_calls": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
    }


def test_scientific_contract_schedule_budget_and_stopping_are_unchanged(
    manifest: dict[str, Any],
) -> None:
    parent = protocol._parent_manifest(REPO_ROOT)
    for field in protocol.source.parent.parent.parent.SCIENTIFIC_CONTRACT_FIELDS:
        if field != "schedule":
            assert manifest[field] == parent[field]
    assert protocol._normalize_schedule_ids(manifest["schedule"]) == (protocol._normalize_schedule_ids(parent["schedule"]))
    assert manifest["budget_candidate"] == parent["budget_candidate"]
    assert manifest["transport_and_stopping"] == parent["transport_and_stopping"]
    assert manifest["formal_execution_tasks"] == parent["formal_execution_tasks"]


def test_all_opaque_ids_and_evidence_root_are_new(manifest: dict[str, Any]) -> None:
    parent = protocol._parent_manifest(REPO_ROOT)
    new_arms = [arm for checkpoint in manifest["schedule"]["checkpoints"] for arm in checkpoint["arms"]]
    old_arms = [arm for checkpoint in parent["schedule"]["checkpoints"] for arm in checkpoint["arms"]]
    new_clone_ids = {arm["opaque_clone_id"] for arm in new_arms}
    new_evaluation_ids = {arm["opaque_evaluation_id"] for arm in new_arms}
    old_clone_ids = {arm["opaque_clone_id"] for arm in old_arms}
    old_evaluation_ids = {arm["opaque_evaluation_id"] for arm in old_arms}
    assert len(new_clone_ids) == len(new_evaluation_ids) == 36
    assert not new_clone_ids & old_clone_ids
    assert not new_evaluation_ids & old_evaluation_ids
    assert manifest["candidate_evidence"]["directory"] == protocol.EVIDENCE_DIRECTORY
    assert manifest["candidate_evidence"]["directory"] != (protocol.OLD_EVIDENCE_DIRECTORY)
    assert not (REPO_ROOT / protocol.EVIDENCE_DIRECTORY).exists()


def test_old_observed_arm_is_explicitly_excluded(manifest: dict[str, Any]) -> None:
    failed = manifest["independent_identity"]["failed_identity"]
    independence = manifest["independent_identity"]["independence"]
    assert failed == {
        "evidence_directory": protocol.OLD_EVIDENCE_DIRECTORY,
        "inventory_sha256": protocol.FAILED_EVIDENCE_INVENTORY_SHA256,
        "file_count": 9,
        "total_size_bytes": 66_466,
        "failure_audit_json_path": protocol.FAILURE_AUDIT_JSON_PATH,
        "failure_audit_json_file_sha256": protocol.FAILURE_AUDIT_JSON_FILE_SHA256,
        "single_observed_arm_sequence": 1,
        "single_observed_arm_condition": "t2",
        "included_in_primary_or_secondary_analysis": False,
        "continuation_retry_replacement_backfill_allowed": False,
    }
    assert independence["historical_outcome_imported"] is False
    assert all(value is False for key, value in independence.items() if key.startswith("historical_"))


def test_candidate_authorization_and_commands_fail_closed(
    manifest: dict[str, Any],
) -> None:
    authorization = manifest["authorization"]
    assert authorization["identity_implementation_authorized"] is True
    assert authorization["execution_started"] is False
    assert all(value is False for key, value in authorization.items() if key not in {"identity_implementation_authorized", "execution_started"})
    availability = manifest["availability_execution"]
    for field in (
        "credential_read_authorized",
        "execution_authorized",
        "marker_write_authorized",
        "model_creation_authorized",
        "model_tokens_authorized",
        "provider_calls_authorized",
    ):
        assert availability[field] is False
    assert manifest["availability_execution_runtime"] == {
        "protocol_path": protocol.PROTOCOL_PATH,
        "runner_path": protocol.RUNNER_PATH,
        "commands": ["availability"],
        "availability_execution_authorized": False,
        "historical_availability_reused": False,
        "fail_closed_without_separate_authorization": True,
    }
    for command in runner.BLOCKED_COMMANDS:
        with pytest.raises(
            runner.IndependentCandidateRunnerError,
            match="execution authorization",
        ):
            runner._reject_execution(command)


def test_runtime_binding_installs_v2_protocol_and_repair_then_restores() -> None:
    original_protocol = runner.base.protocol
    original_update = runner.base._update_claimed_marker
    with runner._runtime_binding():
        assert runner.base.protocol is protocol
        assert runner.base._update_claimed_marker is runner.marker_repair.update_claimed_marker
        with pytest.raises(runner.IndependentCandidateRunnerError, match="只允许串行进入"):
            with runner._runtime_binding():
                pass
    assert runner.base.protocol is original_protocol
    assert runner.base._update_claimed_marker is original_update


def test_marker_repair_qualification_covers_all_terminal_paths(
    manifest: dict[str, Any],
) -> None:
    result = runner.qualify_marker_terminalization(manifest)
    assert result == {
        "status": "marker_terminalization_qualification_passed",
        "attempt_terminal_status": "complete",
        "batch_progress_last_sequence": 1,
        "batch_terminal_status": "completed",
        "batch_failure_status": "failed",
        "temporary_files_removed": True,
        "provider_calls": 0,
        "credential_reads": 0,
        "docker_sessions_created": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
        "model_tokens": 0,
    }


def test_preflight_is_zero_provider_and_reads_old_evidence_only(manifest: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / ".compile-sessions").mkdir(parents=True)
    before = {path: protocol.candidate.file_sha256(REPO_ROOT / protocol.OLD_EVIDENCE_DIRECTORY / path) for path in runner.failure_audit.EXPECTED_INPUT_SHA256}
    monkeypatch.setattr(
        runner,
        "_require_release",
        lambda _root: {
            "revision": "b" * 40,
            "branch": "main",
            "origin_main": "b" * 40,
        },
    )
    monkeypatch.setattr(
        runner,
        "_require_docker_identity",
        lambda _manifest, _root: manifest["environment_identity"]["image_id"],
    )
    monkeypatch.setattr(runner.base, "_require_zero_managed_resources", lambda: None)
    result = runner.collect_preflight(manifest, repo_root=REPO_ROOT, workspace_root=workspace)
    after = {path: protocol.candidate.file_sha256(REPO_ROOT / protocol.OLD_EVIDENCE_DIRECTORY / path) for path in runner.failure_audit.EXPECTED_INPUT_SHA256}
    assert before == after == runner.failure_audit.EXPECTED_INPUT_SHA256
    assert result["ready"] is True
    assert result["credential_check"] == "not_authorized_not_performed"
    assert result["old_evidence"]["imported"] is False
    assert result["new_evidence_directory_absent"] is True
    assert result["provider_calls"] == result["formal_evidence_writes"] == 0


def test_schedule_delta_rejects_scientific_or_identity_drift(
    manifest: dict[str, Any],
) -> None:
    parent = protocol._parent_manifest(REPO_ROOT)
    drifted = copy.deepcopy(manifest)
    drifted["schedule"]["checkpoints"][0]["arms"][0]["condition"] = "c0"
    with pytest.raises(protocol.IndependentCandidateProtocolError, match="schedule"):
        protocol.validate_schedule_delta(drifted, parent)
    drifted = copy.deepcopy(manifest)
    drifted["schedule"]["checkpoints"][0]["arms"][0]["opaque_clone_id"] = parent["schedule"]["checkpoints"][0]["arms"][0]["opaque_clone_id"]
    with pytest.raises(protocol.IndependentCandidateProtocolError, match="opaque"):
        protocol.validate_schedule_delta(drifted, parent)


def test_preregistration_and_runner_have_no_execution_escape_hatch() -> None:
    preregistration = PREREGISTRATION_PATH.read_text(encoding="utf-8")
    runner_source = (REPO_ROOT / protocol.RUNNER_PATH).read_text(encoding="utf-8")
    assert "sequence 1 T2 arm 永久排除" in preregistration
    assert "不构成真实执行授权" in preregistration
    assert "DEEPSEEK_API_KEY" not in runner_source
    assert "create_chat_model" not in runner_source
    assert "execute_batch(" not in runner_source
