"""Issue #303 Phase 5 v3 独立授权 identity 与 runner 适配门禁。"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import forge_agent_workflow_stage_b_phase5_v2_authorized_protocol as parent_protocol  # noqa: E402
import forge_agent_workflow_stage_b_phase5_v3_authorized_protocol as protocol  # noqa: E402
import forge_agent_workflow_stage_b_phase5_v3_authorized_runner as runner  # noqa: E402

MANIFEST_PATH = REPO_ROOT / protocol.MANIFEST_RELATIVE_PATH
SCHEMA_PATH = REPO_ROOT / protocol.SCHEMA_RELATIVE_PATH


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_manifest_and_const_schema_are_deterministic() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)

    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.generate_schema(manifest)
    assert protocol.validate_allowed_delta(manifest, REPO_ROOT)["status"] == "passed"
    assert protocol.candidate.canonical_sha256(manifest) == "191062f15d83bee8e1a323e67763dafdee2b9cc9bee6ac399971872f36e48747"


def test_allowed_delta_preserves_parent_tasks_provider_environment_budget_and_schedule() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    parent = parent_protocol.load_manifest(repo_root=REPO_ROOT)

    for key in (
        "tasks",
        "provider_candidate",
        "environment_candidate",
        "budget_candidate",
        "schedule",
        "qualification",
        "operation_policy_ref",
        "authorization",
    ):
        assert manifest[key] == parent[key]

    for key, mutation in (
        ("tasks", lambda value: value[0].__setitem__("commit_sha", "0" * 40)),
        ("provider_candidate", lambda value: value.__setitem__("model_max_retries", 1)),
        ("budget_candidate", lambda value: value.__setitem__("batch_max_recorded_tokens", 1)),
        ("schedule", lambda value: value["order"].reverse()),
    ):
        drifted = copy.deepcopy(manifest)
        mutation(drifted[key])
        with pytest.raises(protocol.Phase5V3AuthorizedProtocolError):
            protocol.validate_allowed_delta(drifted, REPO_ROOT)


def test_identity_is_independent_and_freezes_evaluator_v3() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    execution = manifest["authorized_execution"]
    evaluator = execution["evaluator"]
    independence = execution["independence"]

    assert manifest["runtime_candidate"]["external_evaluator"] == "external-evaluator-v3"
    assert evaluator["version"] == "forge-external-evaluator-1.2.0"
    assert evaluator["rules_sha256"] == protocol.EVALUATOR_RULES_SHA256
    assert evaluator["file_sha256"] == protocol.EVALUATOR_FILE_SHA256
    assert execution["attempt_id_template"] == "phase5-v3-{task_id}-attempt-1"
    assert execution["evaluation_id_template"] == "phase5-v3-{task_id}-evaluation-v3"
    assert execution["thread_id_prefix"] == "phase5-v3"
    assert "phase5-v3-authorized" in manifest["evidence_candidate"]["directory"]
    assert all(independence[key] is False for key in independence if key != "new_compile_session_per_task")
    assert independence["new_compile_session_per_task"] is True
    assert manifest["reporting"]["stage_c_authorized"] is False
    assert manifest["reporting"]["unbiased_success_rate_claim_allowed"] is False

    drifted = copy.deepcopy(manifest)
    drifted["schema_version"] = "forge-agent-workflow-stage-b-phase5-v4-authorized-1.0.0"
    with pytest.raises(protocol.Phase5V3AuthorizedProtocolError):
        protocol.validate_allowed_delta(drifted, REPO_ROOT)

    drifted = copy.deepcopy(manifest)
    drifted["authorized_execution"]["independence"]["v2_outcomes_imported"] = True
    with pytest.raises(protocol.Phase5V3AuthorizedProtocolError):
        protocol.validate_allowed_delta(drifted, REPO_ROOT)

    drifted = copy.deepcopy(manifest)
    drifted["authorized_execution"]["evaluator"]["rules_sha256"] = "0" * 64
    with pytest.raises(protocol.Phase5V3AuthorizedProtocolError):
        protocol.validate_allowed_delta(drifted, REPO_ROOT)


def test_runtime_validation_is_zero_provider_and_checks_evaluator_identity() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)

    result = runner.validate_runtime(manifest, REPO_ROOT)

    assert result["status"] == "valid"
    assert result["evaluator_version"] == protocol.EVALUATOR_VERSION
    assert result["evaluator_rules_sha256"] == protocol.EVALUATOR_RULES_SHA256
    assert result["provider_calls"] == 0
    assert result["formal_attempts"] == 0
    assert result["model_tokens"] == 0


def test_runtime_binding_uses_v3_and_restores_parent_on_success_and_error() -> None:
    original_protocol = runner.base.protocol
    original_evaluator = runner.base.run_external_evaluator_v2
    original_backend = runner.base.ForgeCompileEvaluationBackend

    with runner._runtime_binding():
        assert runner.base.protocol is protocol
        assert runner.base.run_external_evaluator_v2 is runner.run_external_evaluator_v3
        assert runner.base.ForgeCompileEvaluationBackend is runner.ForgeCompileEvaluationBackend
        with pytest.raises(runner.Phase5V3AuthorizedRunnerError, match="串行"):
            with runner._runtime_binding():
                pass

    assert runner.base.protocol is original_protocol
    assert runner.base.run_external_evaluator_v2 is original_evaluator
    assert runner.base.ForgeCompileEvaluationBackend is original_backend

    runner.base.protocol = object()
    try:
        with pytest.raises(runner.Phase5V3AuthorizedRunnerError, match="其他 identity"):
            with runner._runtime_binding():
                pass
    finally:
        runner.base.protocol = original_protocol

    with pytest.raises(RuntimeError, match="injected"):
        with runner._runtime_binding():
            raise RuntimeError("injected")

    assert runner.base.protocol is original_protocol
    assert runner.base.run_external_evaluator_v2 is original_evaluator
    assert runner.base.ForgeCompileEvaluationBackend is original_backend


def test_ownership_normalization_does_not_mask_active_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    output_dir = tmp_path / "evidence"
    output_dir.mkdir()

    def fail_reachability(*args, **kwargs):
        raise RuntimeError("provider failure")

    def fail_normalization(path: Path) -> bool:
        raise OSError("ownership failure")

    monkeypatch.setattr(runner.base, "execute_reachability", fail_reachability)
    monkeypatch.setattr(runner, "normalize_evidence_tree", fail_normalization)

    with pytest.raises(RuntimeError, match="provider failure") as raised:
        runner.execute_reachability(manifest, output_dir=output_dir, repo_root=REPO_ROOT)

    assert any("ownership failure" in note for note in raised.value.__notes__)


def test_ownership_normalization_failure_is_fatal_after_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output_dir = tmp_path / "evidence"
    output_dir.mkdir()

    def fail_normalization(path: Path) -> bool:
        raise OSError("ownership failure")

    monkeypatch.setattr(runner, "normalize_evidence_tree", fail_normalization)

    with pytest.raises(OSError, match="ownership failure"):
        runner._normalize_without_masking_active_error(output_dir)


def test_adapter_writes_v3_document_identity(tmp_path: Path) -> None:
    output = tmp_path / "result.json"

    runner._write_once_v3(
        output,
        {
            "schema_version": "forge-agent-workflow-stage-b-phase5-v2-task-result-1.0.0",
            "document_type": "forge_agent_workflow_stage_b_phase5_v2_task_result",
        },
    )

    assert _load(output) == {
        "schema_version": "forge-agent-workflow-stage-b-phase5-v3-task-result-1.0.0",
        "document_type": "forge_agent_workflow_stage_b_phase5_v3_task_result",
    }


def test_v3_summary_records_evaluator_and_independence() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    outcome = {
        "candidate_generated_observed": True,
        "candidate_submitted": True,
        "strict_reproducible_build_success": True,
        "bitwise_reproducible": True,
        "recorded_tokens": 10,
        "s0_s5": [{"layer": layer, "status": "passed"} for layer in ("S0", "S1", "S2", "S3", "S4", "S5")],
    }

    with runner._runtime_binding():
        report = runner._summarize_v3(manifest, "a" * 40, {"recorded_tokens": 2}, [outcome])

    assert report["schema_version"] == "forge-agent-workflow-stage-b-phase5-v3-report-1.0.0"
    assert report["document_type"] == "forge_agent_workflow_stage_b_phase5_v3_report"
    assert report["evaluator_identity"] == manifest["authorized_execution"]["evaluator"]
    assert report["independence"] == manifest["authorized_execution"]["independence"]
    assert report["strict_success"] == 1


def test_load_report_rejects_cross_identity_evidence(tmp_path: Path) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    report_path = tmp_path / manifest["authorized_execution"]["batch_report"]
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps(
            {
                "schema_version": "forge-agent-workflow-stage-b-phase5-v3-report-1.0.0",
                "document_type": "forge_agent_workflow_stage_b_phase5_v3_report",
                "manifest_sha256": "0" * 64,
                "evaluator_identity": manifest["authorized_execution"]["evaluator"],
                "independence": manifest["authorized_execution"]["independence"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(runner.Phase5V3AuthorizedRunnerError, match="identity"):
        runner.load_report(manifest, tmp_path)
