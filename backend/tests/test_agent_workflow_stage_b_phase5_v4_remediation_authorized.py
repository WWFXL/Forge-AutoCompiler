"""Issue #305 Phase 5 v4 修复重评 identity 与 Stage C 判定门禁。"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import forge_agent_workflow_stage_b_phase5_v3_authorized_protocol as parent_protocol  # noqa: E402
import forge_agent_workflow_stage_b_phase5_v4_remediation_authorized_protocol as protocol  # noqa: E402
import forge_agent_workflow_stage_b_phase5_v4_remediation_authorized_runner as runner  # noqa: E402

MANIFEST_PATH = REPO_ROOT / protocol.MANIFEST_RELATIVE_PATH
SCHEMA_PATH = REPO_ROOT / protocol.SCHEMA_RELATIVE_PATH


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _strict_outcome(task_id: str, *, identity: str, manifest_sha256: str, strict: bool = True) -> dict[str, Any]:
    if identity == "v3":
        schema = "forge-agent-workflow-stage-b-phase5-v3-task-result-1.0.0"
        document = "forge_agent_workflow_stage_b_phase5_v3_task_result"
        attempt = f"phase5-v3-{task_id}-attempt-1"
    else:
        schema = "forge-agent-workflow-stage-b-phase5-v4-remediation-task-result-1.0.0"
        document = "forge_agent_workflow_stage_b_phase5_v4_remediation_task_result"
        attempt = f"phase5-v4-remediation-{task_id}-attempt-1"
    return {
        "schema_version": schema,
        "document_type": document,
        "manifest_sha256": manifest_sha256,
        "release_revision": "a" * 40,
        "task_id": task_id,
        "attempt_id": attempt,
        "candidate_generated_observed": True,
        "candidate_submitted": strict,
        "strict_reproducible_build_success": strict,
        "bitwise_reproducible": strict,
        "s0_s5": [{"layer": layer, "status": "passed" if strict else "failed"} for layer in ("S0", "S1", "S2", "S3", "S4", "S5")],
        "recorded_tokens": 10,
        "cleanup_succeeded": True,
        "zero_managed_resources": True,
    }


def test_manifest_and_const_schema_are_deterministic() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)

    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.generate_schema(manifest)
    assert protocol.validate_allowed_delta(manifest, REPO_ROOT)["status"] == "passed"


def test_allowed_delta_is_exactly_three_task_remediation() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    parent = _load(REPO_ROOT / parent_protocol.MANIFEST_RELATIVE_PATH)

    assert manifest["schedule"]["order"] == ["uwebsockets", "c-ares", "libass"]
    assert [task["task_id"] for task in manifest["tasks"]] == manifest["schedule"]["order"]
    assert manifest["budget_candidate"]["per_task"] == parent["budget_candidate"]["per_task"]
    assert manifest["budget_candidate"]["batch_max_recorded_tokens"] == 900000
    assert manifest["authorization"]["model_tokens_authorized"] == 905000
    for key in ("provider_candidate", "environment_candidate", "qualification", "operation_policy_ref", "parent_phase5"):
        assert manifest[key] == parent[key]

    for mutation in (
        lambda value: value["tasks"].append(copy.deepcopy(parent["tasks"][0])),
        lambda value: value["schedule"]["order"].reverse(),
        lambda value: value["budget_candidate"]["per_task"].__setitem__("max_agent_steps", 65),
        lambda value: value["authorization"].__setitem__("model_tokens_authorized", 1),
    ):
        drifted = copy.deepcopy(manifest)
        mutation(drifted)
        with pytest.raises(protocol.Phase5V4RemediationAuthorizedProtocolError):
            protocol.validate_allowed_delta(drifted, REPO_ROOT)


def test_identity_freezes_evaluator_and_cross_run_sources() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    execution = manifest["authorized_execution"]
    evaluator = execution["evaluator"]
    historical = execution["historical_success_evidence"]

    assert manifest["runtime_candidate"]["external_evaluator"] == "external-evaluator-v4"
    assert evaluator["version"] == "forge-external-evaluator-1.3.0"
    assert evaluator["rules_sha256"] == protocol.EVALUATOR_RULES_SHA256
    assert evaluator["file_sha256"] == protocol.EVALUATOR_FILE_SHA256
    assert execution["attempt_id_template"] == "phase5-v4-remediation-{task_id}-attempt-1"
    assert execution["evaluation_id_template"] == "phase5-v4-remediation-{task_id}-evaluation-v4"
    assert "phase5-v4-remediation-authorized" in manifest["evidence_candidate"]["directory"]
    assert historical["report_file_sha256"] == protocol.PARENT_REPORT_FILE_SHA256
    assert historical["decision_file_sha256"] == protocol.PARENT_DECISION_FILE_SHA256
    assert set(historical["task_results"]) == {"yyjson", "cppitertools", "openh264"}
    assert execution["cross_run_task_order"] == list(protocol.FULL_TASK_ORDER)
    assert manifest["reporting"]["stage_c_authorized"] is False
    assert manifest["reporting"]["unbiased_success_rate_claim_allowed"] is False


def test_runtime_validation_is_zero_provider_and_checks_v4_identity() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)

    result = runner.validate_runtime(manifest, REPO_ROOT)

    assert result["status"] == "valid"
    assert result["evaluator_version"] == protocol.EVALUATOR_VERSION
    assert result["evaluator_rules_sha256"] == protocol.EVALUATOR_RULES_SHA256
    assert result["task_count"] == 3
    assert result["provider_calls"] == 0
    assert result["formal_attempts"] == 0
    assert result["model_tokens"] == 0


def test_runtime_binding_uses_v4_and_restores_parent_on_success_and_error() -> None:
    original_protocol = runner.base.protocol
    original_evaluator = runner.base.run_external_evaluator_v2
    original_backend = runner.base.ForgeCompileEvaluationBackend
    original_node_executor = runner.base.run_agent_workflow_node_v1

    with runner._runtime_binding():
        assert runner.base.protocol is protocol
        assert runner.base.run_external_evaluator_v2 is runner.run_external_evaluator_v4
        assert runner.base.ForgeCompileEvaluationBackend is runner.ForgeCompileEvaluationBackend
        assert runner.base.run_agent_workflow_node_v1 is runner.run_agent_workflow_node_v2
        with pytest.raises(runner.Phase5V4RemediationAuthorizedRunnerError, match="串行"):
            with runner._runtime_binding():
                pass

    assert runner.base.protocol is original_protocol
    assert runner.base.run_external_evaluator_v2 is original_evaluator
    assert runner.base.ForgeCompileEvaluationBackend is original_backend
    assert runner.base.run_agent_workflow_node_v1 is original_node_executor

    with pytest.raises(RuntimeError, match="injected"):
        with runner._runtime_binding():
            raise RuntimeError("injected")

    assert runner.base.protocol is original_protocol
    assert runner.base.run_external_evaluator_v2 is original_evaluator
    assert runner.base.ForgeCompileEvaluationBackend is original_backend
    assert runner.base.run_agent_workflow_node_v1 is original_node_executor


def test_v4_summary_normalizes_nested_outcome_identity() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    outcome = _strict_outcome("uwebsockets", identity="v3", manifest_sha256=protocol.candidate.canonical_sha256(manifest))
    outcome["schema_version"] = "forge-agent-workflow-stage-b-phase5-v2-task-result-1.0.0"
    outcome["document_type"] = "forge_agent_workflow_stage_b_phase5_v2_task_result"

    report = runner._summarize_v4(manifest, "a" * 40, {"recorded_tokens": 2}, [outcome])

    assert report["schema_version"] == "forge-agent-workflow-stage-b-phase5-v4-remediation-report-1.0.0"
    assert report["document_type"] == "forge_agent_workflow_stage_b_phase5_v4_remediation_report"
    assert report["outcomes"][0]["schema_version"] == "forge-agent-workflow-stage-b-phase5-v4-remediation-task-result-1.0.0"
    assert report["outcomes"][0]["document_type"] == "forge_agent_workflow_stage_b_phase5_v4_remediation_task_result"


def _prepare_adjudication_fixture(tmp_path: Path, *, all_remediation_strict: bool) -> tuple[dict[str, Any], Path]:
    manifest = protocol.generate_manifest(REPO_ROOT)
    historical_root = tmp_path / "historical"
    historical = manifest["authorized_execution"]["historical_success_evidence"]
    historical["evidence_directory"] = str(historical_root)

    historical_outcomes: list[dict[str, Any]] = []
    for task_id in protocol.FULL_TASK_ORDER:
        strict = task_id in protocol.PARENT_SUCCESS_RESULT_SHA256
        historical_outcomes.append(_strict_outcome(task_id, identity="v3", manifest_sha256=protocol.PARENT_MANIFEST_CANONICAL_SHA256, strict=strict))
    for task_id in protocol.PARENT_SUCCESS_RESULT_SHA256:
        result = next(item for item in historical_outcomes if item["task_id"] == task_id)
        path = historical_root / f"tasks/{task_id}/result.json"
        _write(path, result)
        historical["task_results"][task_id]["file_sha256"] = protocol.candidate.file_sha256(path)

    parent_report = {
        "schema_version": "forge-agent-workflow-stage-b-phase5-v3-report-1.0.0",
        "document_type": "forge_agent_workflow_stage_b_phase5_v3_report",
        "manifest_sha256": protocol.PARENT_MANIFEST_CANONICAL_SHA256,
        "release_revision": "b" * 40,
        "task_order": list(protocol.FULL_TASK_ORDER),
        "task_count": 6,
        "strict_success": 3,
        "zero_managed_resources": True,
        "outcomes": historical_outcomes,
    }
    parent_report_path = historical_root / historical["report_path"]
    _write(parent_report_path, parent_report)
    historical["report_file_sha256"] = protocol.candidate.file_sha256(parent_report_path)
    parent_decision = {
        "manifest_sha256": protocol.PARENT_MANIFEST_CANONICAL_SHA256,
        "report_sha256": historical["report_file_sha256"],
        "stage_c_authorized": False,
    }
    parent_decision_path = historical_root / historical["decision_path"]
    _write(parent_decision_path, parent_decision)
    historical["decision_file_sha256"] = protocol.candidate.file_sha256(parent_decision_path)

    output_dir = tmp_path / "remediation"
    digest = protocol.candidate.canonical_sha256(manifest)
    remediation_outcomes = [
        _strict_outcome(
            task_id,
            identity="v4",
            manifest_sha256=digest,
            strict=all_remediation_strict or task_id != "libass",
        )
        for task_id in protocol.REMEDIATION_TASK_ORDER
    ]
    remediation_report = {
        "schema_version": "forge-agent-workflow-stage-b-phase5-v4-remediation-report-1.0.0",
        "document_type": "forge_agent_workflow_stage_b_phase5_v4_remediation_report",
        "manifest_sha256": digest,
        "release_revision": "c" * 40,
        "task_order": list(protocol.REMEDIATION_TASK_ORDER),
        "outcomes": remediation_outcomes,
        "evaluator_identity": manifest["authorized_execution"]["evaluator"],
        "independence": manifest["authorized_execution"]["independence"],
    }
    _write(output_dir / manifest["authorized_execution"]["batch_report"], remediation_report)
    for outcome in remediation_outcomes:
        _write(output_dir / f"tasks/{outcome['task_id']}/result.json", outcome)
    return manifest, output_dir


@pytest.mark.parametrize(("all_remediation_strict", "expected_authorized"), [(True, True), (False, False)])
def test_cross_run_adjudication_controls_stage_c_without_starting_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    all_remediation_strict: bool,
    expected_authorized: bool,
) -> None:
    manifest, output_dir = _prepare_adjudication_fixture(tmp_path, all_remediation_strict=all_remediation_strict)
    monkeypatch.setattr(runner, "validate_runtime", lambda *args, **kwargs: {})
    monkeypatch.setattr(runner.base, "require_zero_managed_resources", lambda: None)

    adjudication = runner.adjudicate_stage_c(manifest, output_dir=output_dir, repo_root=REPO_ROOT)
    decision = runner.load_decision(manifest, output_dir)

    assert adjudication["strict_success_count"] == (6 if expected_authorized else 5)
    assert adjudication["stage_c_authorized"] is expected_authorized
    assert adjudication["stage_c_execution_started"] is False
    assert decision["stage_c_authorized"] is expected_authorized
    assert decision["stage_c_execution_started"] is False
    assert runner.adjudicate_stage_c(manifest, output_dir=output_dir, repo_root=REPO_ROOT) == adjudication
    decision_path = output_dir / manifest["authorized_execution"]["final_stage_c_decision_package"]
    decision_path.unlink()
    assert runner.adjudicate_stage_c(manifest, output_dir=output_dir, repo_root=REPO_ROOT) == adjudication
    assert runner.load_decision(manifest, output_dir) == decision


def test_cross_run_adjudication_rejects_historical_hash_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest, output_dir = _prepare_adjudication_fixture(tmp_path, all_remediation_strict=True)
    monkeypatch.setattr(runner, "validate_runtime", lambda *args, **kwargs: {})
    monkeypatch.setattr(runner.base, "require_zero_managed_resources", lambda: None)
    historical = manifest["authorized_execution"]["historical_success_evidence"]
    report_path = Path(historical["evidence_directory"]) / historical["report_path"]
    report_path.write_text(report_path.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(runner.Phase5V4RemediationAuthorizedRunnerError, match="report 文件哈希"):
        runner.adjudicate_stage_c(manifest, output_dir=output_dir, repo_root=REPO_ROOT)
