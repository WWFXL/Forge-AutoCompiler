#!/usr/bin/env python3
"""执行 Issue #307 授权的 Phase 5 v5 修复重评与 Stage C 准入判定。"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_agent_workflow_stage_b_phase5_v2_authorized_runner as base  # noqa: E402
import forge_agent_workflow_stage_b_phase5_v5_remediation_authorized_protocol as protocol  # noqa: E402

from deerflow.compile.evidence_ownership import normalize_evidence_tree  # noqa: E402
from deerflow.compile.agent_workflow_runtime_v2 import run_agent_workflow_node_v2  # noqa: E402
from deerflow.compile.external_evaluator_v4 import (  # noqa: E402
    EXTERNAL_EVALUATOR_RULES_SHA256,
    EXTERNAL_EVALUATOR_VERSION,
    ForgeCompileEvaluationBackend,
    run_external_evaluator_v4,
)

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_OUTPUT_DIR = Path(protocol.EVIDENCE_DIRECTORY)

_ORIGINAL_PROTOCOL = base.protocol
_ORIGINAL_EVALUATOR = base.run_external_evaluator_v2
_ORIGINAL_BACKEND = base.ForgeCompileEvaluationBackend
_ORIGINAL_WRITE_ONCE = base._write_once
_ORIGINAL_SUMMARIZE = base._summarize
_ORIGINAL_EXPERIMENT_POLICY = base._experiment_policy
_ORIGINAL_ORACLE_SPEC = base._oracle_spec
_ORIGINAL_PREPARE_SESSION = base.prepare_compile_session_impl
_ORIGINAL_NODE_EXECUTOR = base.run_agent_workflow_node_v1
_ORIGINAL_NODE_INPUT = base._node_input
_RUNTIME_BINDING_LOCK = threading.Lock()

_SCHEMA_RENAMES = {
    "forge-agent-workflow-stage-b-phase5-v2-attempt-1.0.0": "forge-agent-workflow-stage-b-phase5-v5-remediation-attempt-1.0.0",
    "forge-agent-workflow-stage-b-phase5-v2-reachability-1.0.0": "forge-agent-workflow-stage-b-phase5-v5-remediation-reachability-1.0.0",
    "forge-agent-workflow-stage-b-phase5-v2-task-result-1.0.0": "forge-agent-workflow-stage-b-phase5-v5-remediation-task-result-1.0.0",
    "forge-agent-workflow-stage-b-phase5-v2-report-1.0.0": "forge-agent-workflow-stage-b-phase5-v5-remediation-report-1.0.0",
}
_DOCUMENT_RENAMES = {
    "forge_agent_workflow_stage_b_phase5_v2_reachability": "forge_agent_workflow_stage_b_phase5_v5_remediation_reachability",
    "forge_agent_workflow_stage_b_phase5_v2_task_result": "forge_agent_workflow_stage_b_phase5_v5_remediation_task_result",
    "forge_agent_workflow_stage_b_phase5_v2_report": "forge_agent_workflow_stage_b_phase5_v5_remediation_report",
}


class Phase5V5RemediationAuthorizedRunnerError(RuntimeError):
    """Phase 5 v5 release、适配器、证据或 Stage C 判定无效。"""


def _adapt_document_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(dict(value))
    schema_version = payload.get("schema_version")
    document_type = payload.get("document_type")
    if schema_version in _SCHEMA_RENAMES:
        payload["schema_version"] = _SCHEMA_RENAMES[schema_version]
    if document_type in _DOCUMENT_RENAMES:
        payload["document_type"] = _DOCUMENT_RENAMES[document_type]
    return payload


def _write_once_v5(path: Path, value: dict[str, Any]) -> None:
    _ORIGINAL_WRITE_ONCE(path, _adapt_document_identity(value))


def _summarize_v5(
    manifest: dict[str, Any],
    revision: str,
    reachability: dict[str, Any],
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_outcomes = [_adapt_document_identity(outcome) for outcome in outcomes]
    report = _ORIGINAL_SUMMARIZE(manifest, revision, reachability, normalized_outcomes)
    report.update(
        {
            "schema_version": "forge-agent-workflow-stage-b-phase5-v5-remediation-report-1.0.0",
            "document_type": "forge_agent_workflow_stage_b_phase5_v5_remediation_report",
            "evaluator_identity": copy.deepcopy(
                manifest["authorized_execution"]["evaluator"]
            ),
            "independence": copy.deepcopy(
                manifest["authorized_execution"]["independence"]
            ),
            "cross_run_adjudication_required": True,
        }
    )
    return report


def _experiment_policy_v5(manifest: dict[str, Any], task: dict[str, Any]) -> Any:
    policy = _ORIGINAL_EXPERIMENT_POLICY(manifest, task)
    return replace(
        policy,
        benchmark_id="forge-agent-workflow-stage-b-phase5-v5-remediation-authorized-v1",
    )


def _oracle_spec_v5(task: dict[str, Any]) -> Any:
    spec = _ORIGINAL_ORACLE_SPEC(task)
    return replace(
        spec,
        argv=tuple(
            item.replace("phase5-v2", "phase5-v5-remediation") for item in spec.argv
        ),
    )


def _prepare_session_v5(**kwargs: Any) -> Any:
    adapted = dict(kwargs)
    run_id = adapted.get("run_id")
    description = adapted.get("task_description")
    if isinstance(run_id, str):
        adapted["run_id"] = run_id.replace("phase5-v2-", "phase5-v5-remediation-", 1)
    if isinstance(description, str):
        adapted["task_description"] = description.replace(
            "Phase 5 v2", "Phase 5 v5 remediation evaluation", 1
        )
    return _ORIGINAL_PREPARE_SESSION(**adapted)


def _node_input_v5(
    manifest: dict[str, Any], task: dict[str, Any], session: Any, attempt_id: str
) -> Any:
    node_input = _ORIGINAL_NODE_INPUT(manifest, task, session, attempt_id)
    observation = dict(node_input.initial_observation)
    observation["execution_guidance"] = copy.deepcopy(task["execution_guidance"])
    return replace(node_input, initial_observation=observation)


@contextmanager
def _runtime_binding() -> Iterator[None]:
    """在单进程串行执行期间绑定 v5 identity，并始终恢复父模块。"""

    if not _RUNTIME_BINDING_LOCK.acquire(blocking=False):
        raise Phase5V5RemediationAuthorizedRunnerError(
            "Phase 5 v5 runtime binding 只允许单进程串行执行"
        )
    originals = (
        base.protocol,
        base.run_external_evaluator_v2,
        base.ForgeCompileEvaluationBackend,
        base._write_once,
        base._summarize,
        base._experiment_policy,
        base._oracle_spec,
        base.prepare_compile_session_impl,
        base.run_agent_workflow_node_v1,
        base._node_input,
    )
    try:
        expected = (
            _ORIGINAL_PROTOCOL,
            _ORIGINAL_EVALUATOR,
            _ORIGINAL_BACKEND,
            _ORIGINAL_WRITE_ONCE,
            _ORIGINAL_SUMMARIZE,
            _ORIGINAL_EXPERIMENT_POLICY,
            _ORIGINAL_ORACLE_SPEC,
            _ORIGINAL_PREPARE_SESSION,
            _ORIGINAL_NODE_EXECUTOR,
            _ORIGINAL_NODE_INPUT,
        )
        if any(
            actual is not original
            for actual, original in zip(originals, expected, strict=True)
        ):
            raise Phase5V5RemediationAuthorizedRunnerError(
                "Phase 5 v2 父 runner binding 已被其他 identity 修改"
            )
        base.protocol = protocol
        base.run_external_evaluator_v2 = run_external_evaluator_v4
        base.ForgeCompileEvaluationBackend = ForgeCompileEvaluationBackend
        base._write_once = _write_once_v5
        base._summarize = _summarize_v5
        base._experiment_policy = _experiment_policy_v5
        base._oracle_spec = _oracle_spec_v5
        base.prepare_compile_session_impl = _prepare_session_v5
        base.run_agent_workflow_node_v1 = run_agent_workflow_node_v2
        base._node_input = _node_input_v5
        try:
            yield
        finally:
            (
                base.protocol,
                base.run_external_evaluator_v2,
                base.ForgeCompileEvaluationBackend,
                base._write_once,
                base._summarize,
                base._experiment_policy,
                base._oracle_spec,
                base.prepare_compile_session_impl,
                base.run_agent_workflow_node_v1,
                base._node_input,
            ) = originals
    finally:
        _RUNTIME_BINDING_LOCK.release()


def _normalize_output_tree(output_dir: Path) -> bool:
    return normalize_evidence_tree(output_dir) if output_dir.exists() else False


def _normalize_without_masking_active_error(output_dir: Path) -> None:
    active_error = sys.exception()
    try:
        _normalize_output_tree(output_dir)
    except Exception as exc:
        if active_error is None:
            raise
        active_error.add_note(
            f"Phase 5 v5 evidence ownership 规范化同时失败: {type(exc).__name__}: {exc}"
        )


def validate_runtime(
    manifest: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    evaluator = manifest["authorized_execution"]["evaluator"]
    if (
        evaluator["version"] != EXTERNAL_EVALUATOR_VERSION
        or evaluator["rules_sha256"] != EXTERNAL_EVALUATOR_RULES_SHA256
        or protocol.candidate.file_sha256(repo_root / evaluator["path"])
        != evaluator["file_sha256"]
    ):
        raise Phase5V5RemediationAuthorizedRunnerError(
            "external evaluator v4 runtime identity 发生漂移"
        )
    return {
        "status": "valid",
        "manifest_sha256": protocol.candidate.canonical_sha256(manifest),
        "parent_manifest_sha256": protocol.PARENT_MANIFEST_CANONICAL_SHA256,
        "evaluator_version": EXTERNAL_EVALUATOR_VERSION,
        "evaluator_rules_sha256": EXTERNAL_EVALUATOR_RULES_SHA256,
        "evidence_directory": manifest["evidence_candidate"]["directory"],
        "task_count": len(manifest["tasks"]),
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
    }


def collect_preflight(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    require_empty: bool,
) -> dict[str, Any]:
    validate_runtime(manifest, repo_root)
    with _runtime_binding():
        return base.collect_preflight(
            manifest,
            output_dir=output_dir,
            repo_root=repo_root,
            require_empty=require_empty,
        )


def execute_reachability(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    model_factory: Any | None = None,
) -> dict[str, Any]:
    validate_runtime(manifest, repo_root)
    try:
        with _runtime_binding():
            return base.execute_reachability(
                manifest,
                output_dir=output_dir,
                repo_root=repo_root,
                model_factory=model_factory,
            )
    finally:
        _normalize_without_masking_active_error(output_dir)


def load_report(
    manifest: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR
) -> dict[str, Any]:
    report = base._load_json(
        output_dir / manifest["authorized_execution"]["batch_report"]
    )
    outcomes = report.get("outcomes")
    expected_ids = manifest["schedule"]["order"]
    if (
        report.get("manifest_sha256") != protocol.candidate.canonical_sha256(manifest)
        or report.get("schema_version")
        != "forge-agent-workflow-stage-b-phase5-v5-remediation-report-1.0.0"
        or report.get("document_type")
        != "forge_agent_workflow_stage_b_phase5_v5_remediation_report"
        or report.get("evaluator_identity")
        != manifest["authorized_execution"]["evaluator"]
        or report.get("independence")
        != manifest["authorized_execution"]["independence"]
        or report.get("task_order") != expected_ids
        or not isinstance(outcomes, list)
        or [item.get("task_id") for item in outcomes if isinstance(item, dict)]
        != expected_ids
        or any(
            item.get("schema_version")
            != "forge-agent-workflow-stage-b-phase5-v5-remediation-task-result-1.0.0"
            or item.get("document_type")
            != "forge_agent_workflow_stage_b_phase5_v5_remediation_task_result"
            for item in outcomes
            if isinstance(item, dict)
        )
        or any(not isinstance(item, dict) for item in outcomes)
    ):
        raise Phase5V5RemediationAuthorizedRunnerError(
            "Phase 5 v5 report 或嵌套 outcome identity 发生漂移"
        )
    return report


def _all_layers_passed(outcome: Mapping[str, Any]) -> bool:
    layers = outcome.get("s0_s5")
    if not isinstance(layers, list):
        return False
    statuses = {
        item.get("layer"): item.get("status")
        for item in layers
        if isinstance(item, dict)
    }
    return len(layers) == 6 and statuses == {
        layer: "passed" for layer in ("S0", "S1", "S2", "S3", "S4", "S5")
    }


def _strict_success(outcome: Mapping[str, Any]) -> bool:
    return (
        outcome.get("candidate_generated_observed") is True
        and outcome.get("candidate_submitted") is True
        and outcome.get("strict_reproducible_build_success") is True
        and outcome.get("cleanup_succeeded") is True
        and outcome.get("zero_managed_resources") is True
        and _all_layers_passed(outcome)
    )


def _normalize_v3_embedded_outcome(value: Mapping[str, Any]) -> dict[str, Any]:
    outcome = copy.deepcopy(dict(value))
    if (
        outcome.get("schema_version")
        == "forge-agent-workflow-stage-b-phase5-v2-task-result-1.0.0"
        and outcome.get("document_type")
        == "forge_agent_workflow_stage_b_phase5_v2_task_result"
    ):
        outcome["schema_version"] = (
            "forge-agent-workflow-stage-b-phase5-v3-task-result-1.0.0"
        )
        outcome["document_type"] = "forge_agent_workflow_stage_b_phase5_v3_task_result"
    return outcome


def _load_v3_successes(
    evidence: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    root = Path(evidence["evidence_directory"])
    report_path = root / evidence["report_path"]
    decision_path = root / evidence["decision_path"]
    if protocol.candidate.file_sha256(report_path) != evidence["report_file_sha256"]:
        raise Phase5V5RemediationAuthorizedRunnerError(
            "Phase 5 v3 report 文件哈希发生漂移"
        )
    if (
        protocol.candidate.file_sha256(decision_path)
        != evidence["decision_file_sha256"]
    ):
        raise Phase5V5RemediationAuthorizedRunnerError(
            "Phase 5 v3 decision 文件哈希发生漂移"
        )
    report = base._load_json(report_path)
    decision = base._load_json(decision_path)
    if (
        report.get("schema_version")
        != "forge-agent-workflow-stage-b-phase5-v3-report-1.0.0"
        or report.get("document_type")
        != "forge_agent_workflow_stage_b_phase5_v3_report"
        or report.get("manifest_sha256") != protocol.V3_MANIFEST_CANONICAL_SHA256
        or report.get("task_order") != list(protocol.FULL_TASK_ORDER)
        or report.get("task_count") != len(protocol.FULL_TASK_ORDER)
        or report.get("strict_success") != len(protocol.V3_SUCCESS_RESULT_SHA256)
        or report.get("zero_managed_resources") is not True
        or decision.get("manifest_sha256") != protocol.V3_MANIFEST_CANONICAL_SHA256
        or decision.get("report_sha256") != evidence["report_file_sha256"]
        or decision.get("stage_c_authorized") is not False
    ):
        raise Phase5V5RemediationAuthorizedRunnerError(
            "Phase 5 v3 report 或 decision 语义发生漂移"
        )

    report_outcomes = report.get("outcomes")
    if not isinstance(report_outcomes, list):
        raise Phase5V5RemediationAuthorizedRunnerError(
            "Phase 5 v3 report 缺少 outcomes"
        )
    if [
        item.get("task_id") for item in report_outcomes if isinstance(item, dict)
    ] != list(protocol.FULL_TASK_ORDER) or any(
        not isinstance(item, dict) for item in report_outcomes
    ):
        raise Phase5V5RemediationAuthorizedRunnerError(
            "Phase 5 v3 report outcome 顺序或结构发生漂移"
        )
    outcomes_by_id = {
        item.get("task_id"): _normalize_v3_embedded_outcome(item)
        for item in report_outcomes
        if isinstance(item, dict)
    }
    results: dict[str, dict[str, Any]] = {}
    for task_id, identity in evidence["task_results"].items():
        path = root / identity["path"]
        if protocol.candidate.file_sha256(path) != identity["file_sha256"]:
            raise Phase5V5RemediationAuthorizedRunnerError(
                f"Phase 5 v3 task result 文件哈希发生漂移: {task_id}"
            )
        result = base._load_json(path)
        if (
            result.get("schema_version")
            != "forge-agent-workflow-stage-b-phase5-v3-task-result-1.0.0"
            or result.get("document_type")
            != "forge_agent_workflow_stage_b_phase5_v3_task_result"
            or result.get("manifest_sha256") != protocol.V3_MANIFEST_CANONICAL_SHA256
            or result.get("task_id") != task_id
            or outcomes_by_id.get(task_id) != result
            or not _strict_success(result)
        ):
            raise Phase5V5RemediationAuthorizedRunnerError(
                f"Phase 5 v3 严格成功证据无效: {task_id}"
            )
        results[task_id] = result
    return report, results


def _load_v4_successes(
    evidence: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    root = Path(evidence["evidence_directory"])
    report_path = root / evidence["report_path"]
    marker_path = root / evidence["batch_marker_path"]
    if protocol.candidate.file_sha256(report_path) != evidence["report_file_sha256"]:
        raise Phase5V5RemediationAuthorizedRunnerError(
            "Phase 5 v4 report 文件哈希发生漂移"
        )
    if (
        protocol.candidate.file_sha256(marker_path)
        != evidence["batch_marker_file_sha256"]
    ):
        raise Phase5V5RemediationAuthorizedRunnerError(
            "Phase 5 v4 batch marker 文件哈希发生漂移"
        )
    report = base._load_json(report_path)
    marker = base._load_json(marker_path)
    v4_order = ["uwebsockets", "c-ares", "libass"]
    if (
        report.get("schema_version")
        != "forge-agent-workflow-stage-b-phase5-v4-remediation-report-1.0.0"
        or report.get("document_type")
        != "forge_agent_workflow_stage_b_phase5_v4_remediation_report"
        or report.get("manifest_sha256") != protocol.PARENT_MANIFEST_CANONICAL_SHA256
        or report.get("task_order") != v4_order
        or report.get("task_count") != len(v4_order)
        or report.get("strict_success") != len(protocol.PARENT_SUCCESS_RESULT_SHA256)
        or report.get("zero_managed_resources") is not True
        or marker.get("manifest_sha256") != protocol.PARENT_MANIFEST_CANONICAL_SHA256
        or marker.get("status") != "passed"
        or marker.get("error_class") is not None
    ):
        raise Phase5V5RemediationAuthorizedRunnerError(
            "Phase 5 v4 report 或 batch marker 语义发生漂移"
        )
    report_outcomes = report.get("outcomes")
    if not isinstance(report_outcomes, list) or any(
        not isinstance(item, dict) for item in report_outcomes
    ):
        raise Phase5V5RemediationAuthorizedRunnerError(
            "Phase 5 v4 report 缺少 outcomes"
        )
    if [item.get("task_id") for item in report_outcomes] != v4_order:
        raise Phase5V5RemediationAuthorizedRunnerError(
            "Phase 5 v4 report outcome 顺序发生漂移"
        )
    outcomes_by_id = {item["task_id"]: item for item in report_outcomes}
    results: dict[str, dict[str, Any]] = {}
    for task_id, identity in evidence["task_results"].items():
        path = root / identity["path"]
        if protocol.candidate.file_sha256(path) != identity["file_sha256"]:
            raise Phase5V5RemediationAuthorizedRunnerError(
                f"Phase 5 v4 task result 文件哈希发生漂移: {task_id}"
            )
        result = base._load_json(path)
        if (
            result.get("schema_version")
            != "forge-agent-workflow-stage-b-phase5-v4-remediation-task-result-1.0.0"
            or result.get("document_type")
            != "forge_agent_workflow_stage_b_phase5_v4_remediation_task_result"
            or result.get("manifest_sha256")
            != protocol.PARENT_MANIFEST_CANONICAL_SHA256
            or result.get("task_id") != task_id
            or outcomes_by_id.get(task_id) != result
            or not _strict_success(result)
        ):
            raise Phase5V5RemediationAuthorizedRunnerError(
                f"Phase 5 v4 严格成功证据无效: {task_id}"
            )
        results[task_id] = result
    return report, results


def _load_historical_successes(
    manifest: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
    evidence = manifest["authorized_execution"]["historical_success_evidence"]
    v3_report, v3_results = _load_v3_successes(evidence["v3"])
    v4_report, v4_results = _load_v4_successes(evidence["v4"])
    overlap = set(v3_results) & set(v4_results)
    if overlap or set(v3_results) | set(v4_results) != set(protocol.FULL_TASK_ORDER) - {
        "uwebsockets"
    }:
        raise Phase5V5RemediationAuthorizedRunnerError(
            "历史严格成功任务集合不完整或发生重叠"
        )
    results = {**v3_results, **v4_results}
    sources = {
        **{task_id: "phase5_v3_frozen_success" for task_id in v3_results},
        **{task_id: "phase5_v4_frozen_success" for task_id in v4_results},
    }
    return {"v3": v3_report, "v4": v4_report}, results, sources


def _load_existing_adjudication(
    manifest: dict[str, Any], output_dir: Path, report_sha256: str
) -> dict[str, Any] | None:
    path = (
        output_dir / manifest["authorized_execution"]["cross_run_adjudication_report"]
    )
    if not path.exists():
        return None
    value = base._load_json(path)
    if (
        value.get("schema_version")
        != "forge-agent-workflow-stage-b-phase5-cross-run-adjudication-2.0.0"
        or value.get("document_type")
        != "forge_agent_workflow_stage_b_phase5_cross_run_adjudication"
        or value.get("remediation_manifest_sha256")
        != protocol.candidate.canonical_sha256(manifest)
        or value.get("remediation_report_sha256") != report_sha256
        or value.get("task_order") != list(protocol.FULL_TASK_ORDER)
        or value.get("stage_c_execution_started") is not False
    ):
        raise Phase5V5RemediationAuthorizedRunnerError(
            "既有 cross-run adjudication identity 发生漂移"
        )
    return value


def _ensure_stage_c_decision(
    manifest: dict[str, Any], output_dir: Path, adjudication: dict[str, Any]
) -> dict[str, Any]:
    path = (
        output_dir / manifest["authorized_execution"]["final_stage_c_decision_package"]
    )
    if path.exists():
        decision = load_decision(manifest, output_dir)
        if decision.get("stage_c_authorized") is not adjudication["stage_c_authorized"]:
            raise Phase5V5RemediationAuthorizedRunnerError(
                "Stage C decision 与 cross-run adjudication 不一致"
            )
        return decision
    adjudication_path = (
        output_dir / manifest["authorized_execution"]["cross_run_adjudication_report"]
    )
    decision = {
        "schema_version": "forge-agent-workflow-stage-c-decision-package-3.0.0",
        "document_type": "forge_agent_workflow_stage_c_decision_package",
        "manifest_sha256": protocol.candidate.canonical_sha256(manifest),
        "release_revision": adjudication["remediation_release_revision"],
        "phase5_complete": True,
        "cross_run_adjudication_sha256": protocol.candidate.file_sha256(
            adjudication_path
        ),
        "stage_c_authorized": adjudication["stage_c_authorized"],
        "stage_c_execution_started": False,
        "required_next_action": (
            "design_stage_c_protocol"
            if adjudication["stage_c_authorized"]
            else "create_new_remediation_identity_for_failed_tasks"
        ),
        "completed_at": adjudication["completed_at"],
    }
    _ORIGINAL_WRITE_ONCE(path, decision)
    return decision


def adjudicate_stage_c(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    validate_runtime(manifest, repo_root)
    base.require_zero_managed_resources()
    remediation_report = load_report(manifest, output_dir)
    remediation_report_path = (
        output_dir / manifest["authorized_execution"]["batch_report"]
    )
    remediation_report_sha256 = protocol.candidate.file_sha256(remediation_report_path)
    existing = _load_existing_adjudication(
        manifest, output_dir, remediation_report_sha256
    )
    if existing is not None:
        _ensure_stage_c_decision(manifest, output_dir, existing)
        return existing

    historical_reports, historical_results, historical_sources = (
        _load_historical_successes(manifest)
    )
    remediation_outcomes = {
        item["task_id"]: item for item in remediation_report["outcomes"]
    }
    task_sources: list[dict[str, Any]] = []
    for task_id in protocol.FULL_TASK_ORDER:
        if task_id in historical_results:
            result = historical_results[task_id]
            source_identity = historical_sources[task_id]
            result_sha256 = (
                protocol.V3_SUCCESS_RESULT_SHA256.get(task_id)
                or protocol.PARENT_SUCCESS_RESULT_SHA256[task_id]
            )
        else:
            result = remediation_outcomes.get(task_id)
            source_identity = "phase5_v5_remediation"
            result_path = output_dir / manifest["authorized_execution"][
                "task_result_path"
            ].format(task_id=task_id)
            result_sha256 = (
                protocol.candidate.file_sha256(result_path)
                if isinstance(result, dict)
                else None
            )
        task_sources.append(
            {
                "task_id": task_id,
                "source_identity": source_identity,
                "result_sha256": result_sha256,
                "candidate_submitted": result.get("candidate_submitted")
                if isinstance(result, dict)
                else False,
                "s0_s5_all_passed": _all_layers_passed(result)
                if isinstance(result, dict)
                else False,
                "strict_reproducible_build_success": result.get(
                    "strict_reproducible_build_success"
                )
                if isinstance(result, dict)
                else False,
                "cleanup_succeeded": result.get("cleanup_succeeded")
                if isinstance(result, dict)
                else False,
                "zero_managed_resources": result.get("zero_managed_resources")
                if isinstance(result, dict)
                else False,
                "strict_success": _strict_success(result)
                if isinstance(result, dict)
                else False,
            }
        )
    stage_c_authorized = all(item["strict_success"] is True for item in task_sources)
    adjudication = {
        "schema_version": "forge-agent-workflow-stage-b-phase5-cross-run-adjudication-2.0.0",
        "document_type": "forge_agent_workflow_stage_b_phase5_cross_run_adjudication",
        "purpose": "engineering_stage_c_entry_decision_only",
        "unbiased_success_rate_claim_allowed": False,
        "remediation_manifest_sha256": protocol.candidate.canonical_sha256(manifest),
        "remediation_release_revision": remediation_report["release_revision"],
        "remediation_report_sha256": remediation_report_sha256,
        "v3_manifest_sha256": protocol.V3_MANIFEST_CANONICAL_SHA256,
        "v3_release_revision": historical_reports["v3"]["release_revision"],
        "v3_report_sha256": protocol.V3_REPORT_FILE_SHA256,
        "v3_decision_sha256": protocol.V3_DECISION_FILE_SHA256,
        "v4_manifest_sha256": protocol.PARENT_MANIFEST_CANONICAL_SHA256,
        "v4_release_revision": historical_reports["v4"]["release_revision"],
        "v4_report_sha256": protocol.PARENT_REPORT_FILE_SHA256,
        "v4_batch_marker_sha256": protocol.PARENT_BATCH_MARKER_FILE_SHA256,
        "task_order": list(protocol.FULL_TASK_ORDER),
        "tasks": task_sources,
        "strict_success_count": sum(
            item["strict_success"] is True for item in task_sources
        ),
        "all_required_evidence_hashes_verified": True,
        "zero_managed_resources": True,
        "stage_c_authorized": stage_c_authorized,
        "stage_c_execution_started": False,
        "completed_at": datetime.now(UTC).isoformat(),
    }
    adjudication_path = (
        output_dir / manifest["authorized_execution"]["cross_run_adjudication_report"]
    )
    _ORIGINAL_WRITE_ONCE(adjudication_path, adjudication)
    _ensure_stage_c_decision(manifest, output_dir, adjudication)
    return adjudication


def load_decision(
    manifest: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR
) -> dict[str, Any]:
    path = (
        output_dir / manifest["authorized_execution"]["final_stage_c_decision_package"]
    )
    value = base._load_json(path)
    adjudication_path = (
        output_dir / manifest["authorized_execution"]["cross_run_adjudication_report"]
    )
    if (
        value.get("schema_version")
        != "forge-agent-workflow-stage-c-decision-package-3.0.0"
        or value.get("document_type") != "forge_agent_workflow_stage_c_decision_package"
        or value.get("manifest_sha256") != protocol.candidate.canonical_sha256(manifest)
        or value.get("cross_run_adjudication_sha256")
        != protocol.candidate.file_sha256(adjudication_path)
        or type(value.get("stage_c_authorized")) is not bool
        or value.get("stage_c_execution_started") is not False
    ):
        raise Phase5V5RemediationAuthorizedRunnerError(
            "Stage C decision identity 发生漂移"
        )
    return value


def run_batch(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    task_executor: Any | None = None,
) -> dict[str, Any]:
    validate_runtime(manifest, repo_root)
    kwargs: dict[str, Any] = {"output_dir": output_dir, "repo_root": repo_root}
    if task_executor is not None:
        kwargs["task_executor"] = task_executor
    try:
        with _runtime_binding():
            report = base.run_batch(manifest, **kwargs)
        adjudicate_stage_c(manifest, output_dir=output_dir, repo_root=repo_root)
        return report
    finally:
        _normalize_without_masking_active_error(output_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "validate",
            "preflight",
            "reachability",
            "batch",
            "report",
            "adjudicate",
            "decision",
        ),
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest(args.manifest)
    if args.command == "validate":
        result: Any = validate_runtime(manifest)
    elif args.command == "preflight":
        result = collect_preflight(
            manifest,
            output_dir=args.output_dir,
            require_empty=not args.output_dir.exists(),
        )
    elif args.command == "reachability":
        result = execute_reachability(manifest, output_dir=args.output_dir)
    elif args.command == "batch":
        result = run_batch(manifest, output_dir=args.output_dir)
    elif args.command == "report":
        result = load_report(manifest, args.output_dir)
    elif args.command == "adjudicate":
        try:
            result = adjudicate_stage_c(manifest, output_dir=args.output_dir)
        finally:
            _normalize_without_masking_active_error(args.output_dir)
    else:
        result = load_decision(manifest, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
