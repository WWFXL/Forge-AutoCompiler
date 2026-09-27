from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = REPO_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_stage_c_runner as stage_c_runner  # noqa: E402
import forge_stage_c_v7_prefreeze_canary_protocol as protocol  # noqa: E402


def test_manifest_is_deterministic_and_fully_unauthorized() -> None:
    manifest = protocol.load_manifest()

    assert manifest == protocol.generate_manifest()
    assert manifest["authorization"] == {
        "candidate_identity_only": True,
        "credential_read_authorized": False,
        "provider_calls_authorized": False,
        "model_creation_authorized": False,
        "reachability_request_authorized": False,
        "docker_execution_authorized": False,
        "formal_stage_c_attempts_authorized": False,
        "evidence_write_authorized": False,
        "model_tokens_authorized": False,
        "stage_c_execution_started": False,
    }
    assert manifest["execution"]["commands"] == ["validate", "show-plan"]
    assert manifest["execution"]["execution_authorized"] is False
    assert manifest["execution"]["future_authorized_identity_required"] is True


def test_schedule_binds_all_four_audited_failure_shapes_once() -> None:
    manifest = protocol.load_manifest()
    schedule = manifest["schedule"]

    assert schedule["canary_attempt_count"] == 4
    assert [attempt["task_id"] for attempt in schedule["attempts"]] == list(protocol.CANARY_TASK_ORDER)
    assert [attempt["sequence"] for attempt in schedule["attempts"]] == [1, 2, 3, 4]
    assert len({attempt["attempt_id"] for attempt in schedule["attempts"]}) == 4
    assert all(attempt["arm"] == "B" and attempt["method"] == "forge-agent-workflow-node-v3" for attempt in schedule["attempts"])
    assert schedule["stop_on_first_failure"] is True
    assert schedule["retry"] is False
    assert schedule["replacement"] is False
    assert schedule["backfill"] is False
    assert schedule["historical_candidates_reused"] is False


def test_runtime_v3_and_external_evaluator_v4_are_frozen() -> None:
    manifest = protocol.load_manifest()

    assert manifest["methods"]["B"] == {
        "name": "forge-agent-workflow-node-v3",
        "runtime_version": "agent-workflow-runtime-v3",
        "runtime_path": protocol.RUNTIME_V3_PATH,
        "prefreeze_feedback_to_agent": True,
        "external_evaluator_feedback_to_agent": False,
        "zero_model_fast_path": False,
    }
    assert manifest["candidate_contract"]["max_rejection_evidence_items"] == 12
    assert manifest["candidate_contract"]["same_attempt_repair_and_resubmit"] is True
    assert manifest["external_evaluator"]["backend"] == "external-evaluator-v4"
    assert manifest["external_evaluator"]["layers"] == ["S0", "S1", "S2", "S3", "S4", "S5"]
    assert manifest["frozen_components"][protocol.RUNTIME_V3_PATH] == protocol.RUNTIME_V3_SHA256
    assert manifest["frozen_components"][protocol.CANDIDATE_VERIFIER_PATH] == protocol.CANDIDATE_VERIFIER_SHA256
    assert manifest["frozen_components"][protocol.EXTERNAL_EVALUATOR_V4_PATH] == protocol.EXTERNAL_EVALUATOR_V4_SHA256


def test_tokens_are_metered_per_request_without_a_ceiling() -> None:
    manifest = protocol.load_manifest()
    budget = manifest["budget"]

    assert budget["per_attempt"]["max_recorded_tokens"] is None
    assert budget["reachability_max_recorded_tokens"] is None
    assert budget["canary_attempts_max_recorded_tokens"] is None
    assert budget["total_max_recorded_tokens"] is None
    assert budget["token_accounting"] == {
        "mode": "meter_each_request_without_ceiling",
        "record_input_tokens": True,
        "record_output_tokens": True,
        "record_total_tokens": True,
        "token_total_is_termination_condition": False,
    }
    assert budget["per_attempt"]["max_model_requests"] == 24
    assert budget["per_attempt"]["forge_max_commands"] == 32


def test_each_canary_task_constructs_a_valid_runtime_v3_node_contract() -> None:
    manifest = protocol.load_manifest()
    compatible_manifest = {
        **manifest,
        "budget": {"per_arm": manifest["budget"]["per_attempt"]},
    }
    tasks = {task["task_id"]: task for task in manifest["tasks"]}

    for attempt in manifest["schedule"]["attempts"]:
        node_input = stage_c_runner._node_input(
            compatible_manifest,
            tasks[attempt["task_id"]],
            SimpleNamespace(session_id=f"session-{attempt['sequence']}"),
            attempt["attempt_id"],
        )
        node_input.validate()
        assert node_input.budget.max_recorded_tokens is None
        assert node_input.target_contract.target_id == tasks[attempt["task_id"]]["target_contract"]["target_id"]
        assert node_input.target_contract.functional_oracle_ref == f"stage-c-{attempt['task_id']}-oracle-v1"
        assert stage_c_runner._oracle_spec(tasks[attempt["task_id"]]).oracle_ref == node_input.target_contract.functional_oracle_ref


def test_historical_inputs_remain_read_only_and_match_frozen_hashes() -> None:
    manifest = protocol.load_manifest()

    assert manifest["historical_inputs"]["v5_manifest"] == {
        "path": protocol.V5_MANIFEST_PATH,
        "file_sha256": protocol.V5_MANIFEST_FILE_SHA256,
        "canonical_sha256": protocol.V5_MANIFEST_SHA256,
        "read_only": True,
    }
    assert manifest["historical_inputs"]["v6_manifest"]["canonical_sha256"] == protocol.V6_MANIFEST_SHA256
    assert all(item["read_only"] is True for item in manifest["historical_inputs"].values())
    assert protocol.file_sha256(REPO_ROOT / protocol.V6_RESULT_PATH) == protocol.V6_RESULT_FILE_SHA256
    assert protocol.file_sha256(REPO_ROOT / protocol.V6_FAILURE_AUDIT_PATH) == protocol.V6_FAILURE_AUDIT_FILE_SHA256


def test_const_schema_matches_the_generated_manifest() -> None:
    manifest = protocol.load_manifest()
    schema = json.loads((REPO_ROOT / protocol.SCHEMA_RELATIVE_PATH).read_text(encoding="utf-8"))

    assert schema == protocol.generate_schema(manifest)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(manifest, schema)
