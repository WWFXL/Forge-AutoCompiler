"""Issue #307 Phase 5 v5 定向重评 identity 与 Stage C 判定门禁。"""

from __future__ import annotations

import copy
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import forge_agent_workflow_stage_b_phase5_v4_remediation_authorized_protocol as parent_protocol  # noqa: E402
import forge_agent_workflow_stage_b_phase5_v5_remediation_authorized_protocol as protocol  # noqa: E402
import forge_agent_workflow_stage_b_phase5_v5_remediation_authorized_runner as runner  # noqa: E402

MANIFEST_PATH = REPO_ROOT / protocol.MANIFEST_RELATIVE_PATH
SCHEMA_PATH = REPO_ROOT / protocol.SCHEMA_RELATIVE_PATH


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _strict_outcome(
    task_id: str,
    *,
    identity: str,
    manifest_sha256: str,
    strict: bool = True,
) -> dict[str, Any]:
    labels = {
        "v2": (
            "forge-agent-workflow-stage-b-phase5-v2-task-result-1.0.0",
            "forge_agent_workflow_stage_b_phase5_v2_task_result",
            f"phase5-v3-{task_id}-attempt-1",
        ),
        "v3": (
            "forge-agent-workflow-stage-b-phase5-v3-task-result-1.0.0",
            "forge_agent_workflow_stage_b_phase5_v3_task_result",
            f"phase5-v3-{task_id}-attempt-1",
        ),
        "v4": (
            "forge-agent-workflow-stage-b-phase5-v4-remediation-task-result-1.0.0",
            "forge_agent_workflow_stage_b_phase5_v4_remediation_task_result",
            f"phase5-v4-remediation-{task_id}-attempt-1",
        ),
        "v5": (
            "forge-agent-workflow-stage-b-phase5-v5-remediation-task-result-1.0.0",
            "forge_agent_workflow_stage_b_phase5_v5_remediation_task_result",
            f"phase5-v5-remediation-{task_id}-attempt-1",
        ),
    }
    schema, document, attempt = labels[identity]
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


def test_allowed_delta_is_exactly_one_guided_task() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    parent = _load(REPO_ROOT / parent_protocol.MANIFEST_RELATIVE_PATH)

    assert manifest["schedule"]["order"] == ["uwebsockets"]
    assert [task["task_id"] for task in manifest["tasks"]] == ["uwebsockets"]
    assert manifest["tasks"][0]["execution_guidance"] == (protocol.UWEBSOCKETS_EXECUTION_GUIDANCE)
    assert manifest["budget_candidate"]["per_task"] == parent["budget_candidate"]["per_task"]
    assert manifest["budget_candidate"]["batch_max_recorded_tokens"] == 300000
    assert manifest["authorization"]["model_tokens_authorized"] == 305000
    for key in (
        "provider_candidate",
        "environment_candidate",
        "qualification",
        "operation_policy_ref",
    ):
        assert manifest[key] == parent[key]

    for mutation in (
        lambda value: value["tasks"].append(copy.deepcopy(parent["tasks"][1])),
        lambda value: value["tasks"][0]["execution_guidance"].__setitem__("strategy_id", "drifted"),
        lambda value: value["budget_candidate"]["per_task"].__setitem__("max_agent_steps", 65),
        lambda value: value["authorization"].__setitem__("model_tokens_authorized", 1),
    ):
        drifted = copy.deepcopy(manifest)
        mutation(drifted)
        with pytest.raises(protocol.Phase5V5RemediationAuthorizedProtocolError):
            protocol.validate_allowed_delta(drifted, REPO_ROOT)


def test_identity_freezes_evaluator_and_both_historical_sources() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    execution = manifest["authorized_execution"]
    historical = execution["historical_success_evidence"]

    assert manifest["runtime_candidate"]["external_evaluator"] == ("external-evaluator-v4")
    assert execution["evaluator"]["version"] == "forge-external-evaluator-1.3.0"
    assert execution["attempt_id_template"] == ("phase5-v5-remediation-{task_id}-attempt-1")
    assert set(historical) == {"v3", "v4"}
    assert set(historical["v3"]["task_results"]) == {
        "yyjson",
        "cppitertools",
        "openh264",
    }
    assert set(historical["v4"]["task_results"]) == {"c-ares", "libass"}
    assert historical["v4"]["report_file_sha256"] == (protocol.PARENT_REPORT_FILE_SHA256)
    assert execution["cross_run_task_order"] == list(protocol.FULL_TASK_ORDER)
    assert manifest["reporting"]["stage_c_authorized"] is False
    assert manifest["reporting"]["unbiased_success_rate_claim_allowed"] is False


def test_runtime_validation_is_zero_provider() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)

    result = runner.validate_runtime(manifest, REPO_ROOT)

    assert result["status"] == "valid"
    assert result["task_count"] == 1
    assert result["provider_calls"] == 0
    assert result["formal_attempts"] == 0
    assert result["model_tokens"] == 0


def test_runtime_binding_uses_v5_and_restores_parent() -> None:
    originals = (
        runner.base.protocol,
        runner.base.run_external_evaluator_v2,
        runner.base.run_agent_workflow_node_v1,
        runner.base._node_input,
    )

    with runner._runtime_binding():
        assert runner.base.protocol is protocol
        assert runner.base.run_external_evaluator_v2 is runner.run_external_evaluator_v4
        assert runner.base.run_agent_workflow_node_v1 is runner.run_agent_workflow_node_v2
        assert runner.base._node_input is runner._node_input_v5
        with pytest.raises(runner.Phase5V5RemediationAuthorizedRunnerError, match="串行"):
            with runner._runtime_binding():
                pass

    assert (
        runner.base.protocol,
        runner.base.run_external_evaluator_v2,
        runner.base.run_agent_workflow_node_v1,
        runner.base._node_input,
    ) == originals


@dataclass(frozen=True)
class _DummyNodeInput:
    initial_observation: dict[str, Any]


def test_node_input_injects_frozen_execution_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner,
        "_ORIGINAL_NODE_INPUT",
        lambda *_args: _DummyNodeInput(initial_observation={"existing": True}),
    )
    task = {"execution_guidance": protocol.UWEBSOCKETS_EXECUTION_GUIDANCE}

    result = runner._node_input_v5({}, task, object(), "attempt")

    assert result.initial_observation == {
        "existing": True,
        "execution_guidance": protocol.UWEBSOCKETS_EXECUTION_GUIDANCE,
    }


def test_v5_summary_normalizes_nested_outcome_identity() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    outcome = _strict_outcome(
        "uwebsockets",
        identity="v2",
        manifest_sha256=protocol.candidate.canonical_sha256(manifest),
    )

    report = runner._summarize_v5(manifest, "a" * 40, {"recorded_tokens": 2}, [outcome])

    assert report["schema_version"] == ("forge-agent-workflow-stage-b-phase5-v5-remediation-report-1.0.0")
    assert report["outcomes"][0]["schema_version"] == ("forge-agent-workflow-stage-b-phase5-v5-remediation-task-result-1.0.0")


def _prepare_adjudication_fixture(tmp_path: Path, *, remediation_strict: bool) -> tuple[dict[str, Any], Path]:
    manifest = protocol.generate_manifest(REPO_ROOT)
    historical = manifest["authorized_execution"]["historical_success_evidence"]

    v3_root = tmp_path / "v3"
    historical["v3"]["evidence_directory"] = str(v3_root)
    v3_outcomes: list[dict[str, Any]] = []
    for task_id in protocol.FULL_TASK_ORDER:
        strict = task_id in protocol.V3_SUCCESS_RESULT_SHA256
        result = _strict_outcome(
            task_id,
            identity="v3",
            manifest_sha256=protocol.V3_MANIFEST_CANONICAL_SHA256,
            strict=strict,
        )
        embedded = copy.deepcopy(result)
        embedded["schema_version"] = "forge-agent-workflow-stage-b-phase5-v2-task-result-1.0.0"
        embedded["document_type"] = "forge_agent_workflow_stage_b_phase5_v2_task_result"
        v3_outcomes.append(embedded)
        if strict:
            path = v3_root / f"tasks/{task_id}/result.json"
            _write(path, result)
            historical["v3"]["task_results"][task_id]["file_sha256"] = protocol.candidate.file_sha256(path)
    v3_report = {
        "schema_version": "forge-agent-workflow-stage-b-phase5-v3-report-1.0.0",
        "document_type": "forge_agent_workflow_stage_b_phase5_v3_report",
        "manifest_sha256": protocol.V3_MANIFEST_CANONICAL_SHA256,
        "release_revision": "b" * 40,
        "task_order": list(protocol.FULL_TASK_ORDER),
        "task_count": 6,
        "strict_success": 3,
        "zero_managed_resources": True,
        "outcomes": v3_outcomes,
    }
    v3_report_path = v3_root / historical["v3"]["report_path"]
    _write(v3_report_path, v3_report)
    historical["v3"]["report_file_sha256"] = protocol.candidate.file_sha256(v3_report_path)
    v3_decision = {
        "manifest_sha256": protocol.V3_MANIFEST_CANONICAL_SHA256,
        "report_sha256": historical["v3"]["report_file_sha256"],
        "stage_c_authorized": False,
    }
    v3_decision_path = v3_root / historical["v3"]["decision_path"]
    _write(v3_decision_path, v3_decision)
    historical["v3"]["decision_file_sha256"] = protocol.candidate.file_sha256(v3_decision_path)

    v4_root = tmp_path / "v4"
    historical["v4"]["evidence_directory"] = str(v4_root)
    v4_outcomes = [
        _strict_outcome(
            task_id,
            identity="v4",
            manifest_sha256=protocol.PARENT_MANIFEST_CANONICAL_SHA256,
            strict=task_id in protocol.PARENT_SUCCESS_RESULT_SHA256,
        )
        for task_id in ("uwebsockets", "c-ares", "libass")
    ]
    for result in v4_outcomes:
        if result["task_id"] in protocol.PARENT_SUCCESS_RESULT_SHA256:
            path = v4_root / f"tasks/{result['task_id']}/result.json"
            _write(path, result)
            historical["v4"]["task_results"][result["task_id"]]["file_sha256"] = protocol.candidate.file_sha256(path)
    v4_report = {
        "schema_version": ("forge-agent-workflow-stage-b-phase5-v4-remediation-report-1.0.0"),
        "document_type": ("forge_agent_workflow_stage_b_phase5_v4_remediation_report"),
        "manifest_sha256": protocol.PARENT_MANIFEST_CANONICAL_SHA256,
        "release_revision": "c" * 40,
        "task_order": ["uwebsockets", "c-ares", "libass"],
        "task_count": 3,
        "strict_success": 2,
        "zero_managed_resources": True,
        "outcomes": v4_outcomes,
    }
    v4_report_path = v4_root / historical["v4"]["report_path"]
    _write(v4_report_path, v4_report)
    historical["v4"]["report_file_sha256"] = protocol.candidate.file_sha256(v4_report_path)
    v4_marker = {
        "manifest_sha256": protocol.PARENT_MANIFEST_CANONICAL_SHA256,
        "status": "passed",
        "error_class": None,
    }
    v4_marker_path = v4_root / historical["v4"]["batch_marker_path"]
    _write(v4_marker_path, v4_marker)
    historical["v4"]["batch_marker_file_sha256"] = protocol.candidate.file_sha256(v4_marker_path)

    output_dir = tmp_path / "v5"
    digest = protocol.candidate.canonical_sha256(manifest)
    remediation = _strict_outcome(
        "uwebsockets",
        identity="v5",
        manifest_sha256=digest,
        strict=remediation_strict,
    )
    remediation_report = {
        "schema_version": ("forge-agent-workflow-stage-b-phase5-v5-remediation-report-1.0.0"),
        "document_type": ("forge_agent_workflow_stage_b_phase5_v5_remediation_report"),
        "manifest_sha256": digest,
        "release_revision": "d" * 40,
        "task_order": ["uwebsockets"],
        "outcomes": [remediation],
        "evaluator_identity": manifest["authorized_execution"]["evaluator"],
        "independence": manifest["authorized_execution"]["independence"],
    }
    _write(
        output_dir / manifest["authorized_execution"]["batch_report"],
        remediation_report,
    )
    _write(output_dir / "tasks/uwebsockets/result.json", remediation)
    return manifest, output_dir


@pytest.mark.parametrize(
    ("remediation_strict", "expected_authorized"),
    [(True, True), (False, False)],
)
def test_cross_run_adjudication_controls_stage_c_without_starting_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    remediation_strict: bool,
    expected_authorized: bool,
) -> None:
    manifest, output_dir = _prepare_adjudication_fixture(tmp_path, remediation_strict=remediation_strict)
    monkeypatch.setattr(runner, "validate_runtime", lambda *args, **kwargs: {})
    monkeypatch.setattr(runner.base, "require_zero_managed_resources", lambda: None)

    adjudication = runner.adjudicate_stage_c(manifest, output_dir=output_dir, repo_root=REPO_ROOT)
    decision = runner.load_decision(manifest, output_dir)

    assert adjudication["strict_success_count"] == (6 if expected_authorized else 5)
    assert adjudication["stage_c_authorized"] is expected_authorized
    assert adjudication["stage_c_execution_started"] is False
    assert [item["source_identity"] for item in adjudication["tasks"]] == [
        "phase5_v3_frozen_success",
        "phase5_v3_frozen_success",
        "phase5_v3_frozen_success",
        "phase5_v5_remediation",
        "phase5_v4_frozen_success",
        "phase5_v4_frozen_success",
    ]
    assert decision["stage_c_authorized"] is expected_authorized
    assert decision["stage_c_execution_started"] is False
    assert runner.adjudicate_stage_c(manifest, output_dir=output_dir, repo_root=REPO_ROOT) == adjudication


def test_cross_run_adjudication_rejects_v4_hash_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest, output_dir = _prepare_adjudication_fixture(tmp_path, remediation_strict=True)
    monkeypatch.setattr(runner, "validate_runtime", lambda *args, **kwargs: {})
    monkeypatch.setattr(runner.base, "require_zero_managed_resources", lambda: None)
    evidence = manifest["authorized_execution"]["historical_success_evidence"]["v4"]
    report_path = Path(evidence["evidence_directory"]) / evidence["report_path"]
    report_path.write_text(report_path.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(
        runner.Phase5V5RemediationAuthorizedRunnerError,
        match="Phase 5 v4 report 文件哈希",
    ):
        runner.adjudicate_stage_c(manifest, output_dir=output_dir, repo_root=REPO_ROOT)
