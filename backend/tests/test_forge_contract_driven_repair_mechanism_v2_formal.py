"""Issue #377 mechanism v2 独立 formal collection identity 测试。"""

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

import forge_contract_driven_repair_mechanism_v2_formal_protocol as protocol  # noqa: E402
import forge_contract_driven_repair_mechanism_v2_formal_runner as runner  # noqa: E402

SCHEMA_PATH = REPO_ROOT / protocol.SCHEMA_PATH
PREREGISTRATION_PATH = REPO_ROOT / protocol.PREREGISTRATION_PATH


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@pytest.fixture(scope="session")
def manifest() -> dict[str, Any]:
    return protocol.load_manifest()


def _synthetic_results(manifest: dict[str, Any], outcomes: dict[str, bool]) -> list[dict[str, Any]]:
    return [
        {
            "checkpoint_id": checkpoint["checkpoint_id"],
            "task_id": checkpoint["task_id"],
            "stratum": checkpoint["stratum"],
            "sequence": arm["sequence"],
            "condition": arm["condition"],
            "status": "complete",
            "strict_post_checkpoint_conversion": outcomes[arm["condition"]],
            "provider_request_attempts": 1,
            "recorded_input_tokens": 2,
            "recorded_output_tokens": 1,
            "recorded_total_tokens": 3,
        }
        for checkpoint in manifest["schedule"]["checkpoints"]
        for arm in checkpoint["arms"]
    ]


def test_manifest_schema_parent_and_allowed_delta_are_deterministic(
    manifest: dict[str, Any],
) -> None:
    assert manifest == protocol.generate_manifest(REPO_ROOT)
    schema = _load_json(SCHEMA_PATH)
    assert schema == protocol.generate_schema(manifest)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(manifest, schema)
    delta = protocol.validate_allowed_delta(manifest)
    assert delta["status"] == "passed"
    assert delta["availability_marker_sha256"] == (protocol.AVAILABILITY_MARKER_FILE_SHA256)
    assert delta["formal_arm_count"] == 36
    assert delta["formal_provider_request_attempt_limit"] == 288


def test_scientific_contract_schedule_budget_and_ids_are_unchanged(
    manifest: dict[str, Any],
) -> None:
    parent = protocol._parent_manifest(REPO_ROOT)
    for field in protocol.independent.source.parent.parent.parent.SCIENTIFIC_CONTRACT_FIELDS:
        assert manifest[field] == parent[field]
    assert manifest["schedule"] == parent["schedule"]
    assert manifest["budget_candidate"] == parent["budget_candidate"]
    assert manifest["transport_and_stopping"] == parent["transport_and_stopping"]
    assert manifest["formal_execution_tasks"] == parent["formal_execution_tasks"]
    assert manifest["independent_identity"] == parent["independent_identity"]
    assert manifest["candidate_evidence"]["directory"] == (parent["candidate_evidence"]["directory"])


def test_formal_authorization_excludes_availability_replay(
    manifest: dict[str, Any],
) -> None:
    authorization = manifest["authorization"]
    for field in (
        "identity_implementation_authorized",
        "availability_execution_completed",
        "credential_read_authorized",
        "provider_calls_authorized",
        "model_creation_authorized",
        "model_tokens_authorized",
        "docker_session_creation_authorized",
        "formal_collection_execution_authorized",
        "formal_attempts_authorized",
        "formal_evidence_write_authorized",
    ):
        assert authorization[field] is True
    assert authorization["execution_started"] is False
    assert authorization["availability_execution_authorized"] is False
    assert authorization["availability_marker_write_authorized"] is False
    availability = manifest["availability_execution"]
    assert availability["status"] == "passed_consumed_read_only"
    assert availability["result_observed"] is True
    for field in (
        "credential_read_authorized",
        "execution_authorized",
        "marker_write_authorized",
        "model_creation_authorized",
        "model_tokens_authorized",
        "provider_calls_authorized",
        "formal_batch_creation_authorized",
    ):
        assert availability[field] is False
    assert manifest["candidate_evidence"]["availability_marker_write_authorized"] is False
    assert manifest["formal_execution"]["availability_is_not_repeated"] is True
    assert manifest["formal_execution"]["execution_authorized"] is True
    assert manifest["availability_receipt"] == {
        "manifest_path": protocol.availability.MANIFEST_PATH,
        "manifest_canonical_sha256": protocol.AVAILABILITY_MANIFEST_CANONICAL_SHA256,
        "manifest_file_sha256": protocol.AVAILABILITY_MANIFEST_FILE_SHA256,
        "execution_revision": protocol.AVAILABILITY_EXECUTION_REVISION,
        "marker_path": "markers/availability.json",
        "marker_file_sha256": protocol.AVAILABILITY_MARKER_FILE_SHA256,
        "required_status": "passed",
        "required_passed": True,
        "request_attempt_count": 1,
        "recorded_total_tokens": 158,
        "formal_batch_creation_authorized_in_parent": False,
        "read_only": True,
        "audit_json_path": protocol.AVAILABILITY_AUDIT_JSON_PATH,
        "audit_json_file_sha256": protocol.AVAILABILITY_AUDIT_JSON_FILE_SHA256,
        "audit_markdown_path": protocol.AVAILABILITY_AUDIT_MD_PATH,
        "audit_markdown_file_sha256": protocol.AVAILABILITY_AUDIT_MD_FILE_SHA256,
    }


def test_runtime_binding_installs_protocol_and_repair_then_restores() -> None:
    original_protocol = runner.base.protocol
    original_update = runner.base._update_claimed_marker
    with runner._runtime_binding():
        assert runner.base.protocol is protocol
        assert runner.base._update_claimed_marker is (runner.marker_repair.update_claimed_marker)
        with pytest.raises(runner.IndependentFormalRunnerError, match="只允许串行进入"):
            with runner._runtime_binding():
                pass
    assert runner.base.protocol is original_protocol
    assert runner.base._update_claimed_marker is original_update


def test_marker_repair_closes_attempt_progress_terminal_and_failure(
    tmp_path: Path,
) -> None:
    attempt = tmp_path / "attempt.json"
    batch = tmp_path / "batch.json"
    failed = tmp_path / "failed.json"
    runner.base._write_once(attempt, {"status": "started"})
    runner.base._write_once(batch, {"status": "running"})
    runner.base._write_once(failed, {"status": "running"})
    with runner._runtime_binding():
        attempt_result = runner.base._update_claimed_marker(attempt, status="complete", completed_at="terminal")
        progress = runner.base._update_claimed_marker(batch, completed_arm_count=1, last_completed_sequence=1)
        terminal = runner.base._update_claimed_marker(batch, status="complete", completed_arm_count=36)
        failure = runner.base._update_claimed_marker(failed, status="failed", error_class="FormalFatalError")
    assert attempt_result["status"] == "complete"
    assert progress["last_completed_sequence"] == 1
    assert terminal["completed_arm_count"] == 36
    assert failure["error_class"] == "FormalFatalError"
    assert _load_json(attempt) == attempt_result
    assert _load_json(batch) == terminal
    assert _load_json(failed) == failure


def test_passed_availability_marker_is_hash_and_semantics_bound(
    manifest: dict[str, Any],
) -> None:
    with runner._runtime_binding():
        marker = runner.base._verify_availability(manifest, runner.DEFAULT_OUTPUT_DIR)
    assert marker["status"] == "passed"
    assert marker["recorded_total_tokens"] == 158
    assert marker["attempts"][0]["actual_model"] == "deepseek-flash"


def test_strict_evidence_inventory_allows_only_marker_before_batch(manifest: dict[str, Any], tmp_path: Path) -> None:
    output = tmp_path / "evidence"
    marker = output / manifest["candidate_evidence"]["availability_marker"]
    marker.parent.mkdir(parents=True)
    marker.write_text("{}\n", encoding="utf-8")
    with runner._runtime_binding():
        observed = runner._strict_evidence_inventory(manifest, output, require_formal_absent=True)
    assert observed == ["markers/availability.json"]
    unexpected = output / "unexpected.json"
    unexpected.write_text("{}\n", encoding="utf-8")
    with runner._runtime_binding():
        with pytest.raises(runner.IndependentFormalRunnerError, match="未授权文件"):
            runner._strict_evidence_inventory(manifest, output, require_formal_absent=True)


def test_fixed_sequence_analysis_and_two_censor_stop(
    manifest: dict[str, Any],
) -> None:
    results = _synthetic_results(manifest, {"c0": False, "t1": True, "t2": True})
    with runner._runtime_binding():
        report = runner.base.build_report(manifest, results)
    assert report["primary"]["exact_test"]["p_value"] == pytest.approx(2 / 64)
    assert report["primary_fixed_sequence_gate_passed"] is True
    assert report["secondary"]["exact_test"] is not None
    assert report["supportive"]["exact_test"] is None

    censored = copy.deepcopy(results[:2])
    for item in censored:
        item["status"] = "endpoint_censored"
    with runner._runtime_binding():
        stopped = runner.base.build_report(manifest, censored)
    assert stopped["status"] == "stopped_after_second_endpoint_censor"
    assert stopped["primary"]["exact_test"] is None


def test_preregistration_freezes_boundaries() -> None:
    preregistration = PREREGISTRATION_PATH.read_text(encoding="utf-8")
    assert "v1 sequence 1 T2 observation 永久排除" in preregistration
    assert "最多 288 个 formal physical request attempts" in preregistration
    assert "第二个出现后完成当前 checkpoint cleanup 并停止 identity" in preregistration
    assert "逐响应记录 input/output/total tokens" in preregistration
    assert "不能解释为 treatment effect" in preregistration
