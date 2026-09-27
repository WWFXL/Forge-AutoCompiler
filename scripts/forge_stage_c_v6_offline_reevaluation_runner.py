#!/usr/bin/env python3
"""执行 Stage C v6 的 22 条零 Provider 离线定向重评。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_stage_c_runner as stage_c  # noqa: E402
import forge_stage_c_task_qualification as qualification  # noqa: E402
import forge_stage_c_v6_offline_reevaluation_protocol as protocol  # noqa: E402

from deerflow.compile.agent_workflow_schemas import (  # noqa: E402
    AgentBuildNodeInput,
    AgentBuildNodeResult,
    AgentWorkflowBudget,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowTargetContract,
    AgentWorkflowUsage,
)
from deerflow.compile.external_evaluator_v4 import (  # noqa: E402
    ForgeCompileEvaluationBackend,
    run_external_evaluator_v4,
)
from deerflow.compile.operations import (  # noqa: E402
    cleanup_and_finalize_compile_session_impl,
)
from deerflow.compile.schemas import CompileSession  # noqa: E402

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_OUTPUT_DIR = Path(protocol.DEFAULT_EVIDENCE_DIRECTORY)
DEFAULT_COMPILE_SESSIONS_ROOT = Path("/workspace/.compile-sessions")


class StageCV6OfflineRunnerError(RuntimeError):
    """Stage C v6 离线重评来源、执行、恢复或清理合同无效。"""


def _load_json(path: Path) -> dict[str, Any]:
    return qualification.load_json(path)


def _write_once(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        if isinstance(value, str):
            stream.write(value)
        else:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _release_identity(manifest: dict[str, Any]) -> str:
    revision = protocol.release_revision()
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    origin_main = subprocess.run(
        ["git", "rev-parse", "origin/main"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if branch != manifest["execution"]["release_branch"] or revision != origin_main or status:
        raise StageCV6OfflineRunnerError("Stage C v6 正式重评只能从干净 main == origin/main 执行")
    return revision


def _receipt_by_evaluation(
    receipt: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return {entry["evaluation_id"]: entry for entry in receipt["entries"]}


def _validate_source_receipt(
    *,
    repo_root: Path = REPO_ROOT,
    compile_sessions_root: Path = DEFAULT_COMPILE_SESSIONS_ROOT,
) -> dict[str, Any]:
    expected = _load_json(repo_root / protocol.SOURCE_RECEIPT_PATH)
    observed = protocol.capture_source_receipt(repo_root=repo_root, compile_sessions_root=compile_sessions_root)
    if observed != expected:
        raise StageCV6OfflineRunnerError("Stage C v5 来源 evidence 与冻结收据不一致")
    return expected


def _load_node_input(path: Path) -> AgentBuildNodeInput:
    value = _load_json(path)
    value["build_system_candidates"] = tuple(value["build_system_candidates"])
    target = value.pop("target_contract")
    target["artifact_types"] = tuple(target["artifact_types"])
    target["artifact_path_patterns"] = tuple(target["artifact_path_patterns"])
    value["target_contract"] = AgentWorkflowTargetContract(**target)
    value["environment"] = AgentWorkflowEnvironmentIdentity(**value["environment"])
    value["budget"] = AgentWorkflowBudget(**value["budget"])
    value["experiment_identity"] = AgentWorkflowExperimentIdentity(**value["experiment_identity"])
    result = AgentBuildNodeInput(**value)
    result.validate()
    return result


def _synthetic_node_result(entry: dict[str, Any], session_status: str) -> AgentBuildNodeResult:
    usage = entry["source_usage"]
    result = AgentBuildNodeResult(
        node_status="submitted",
        candidate_generated_observed=True,
        candidate_submitted=True,
        usage=AgentWorkflowUsage(
            model_requests=usage["model_requests"],
            recorded_tokens=usage["recorded_tokens"],
            agent_steps=0,
            tool_calls=usage["tool_calls"],
            commands=usage["commands"],
        ),
        wall_clock_ms=0,
        evidence_head_sha256=entry["source_evidence_head_sha256"],
        session_terminal_status=session_status,
        submission_id=entry["submission_id"],
        candidate_record_sha256=entry["source_candidate_record_sha256"],
    )
    result.validate()
    return result


def _task(manifest: dict[str, Any], task_id: str) -> dict[str, Any]:
    matches = [task for task in manifest["tasks"] if task["task_id"] == task_id]
    if len(matches) != 1:
        raise StageCV6OfflineRunnerError(f"未知或重复 task: {task_id}")
    return matches[0]


def _validate_oracle_adapter(manifest: dict[str, Any]) -> dict[str, list[str]]:
    scheduled_kinds = sorted({task["oracle"]["kind"] for task in manifest["tasks"]})
    for task in manifest["tasks"]:
        stage_c._oracle_spec(task).validate()
    service_probe_gate = {
        "task_id": "stage-c-v6-service-probe-contract-gate",
        "oracle": {
            "kind": "service_probe",
            "start_argv": ["/artifacts/bin/server"],
            "workdir": "/workspace",
            "listen_host": "127.0.0.1",
            "listen_port": 18080,
            "startup_timeout_seconds": 2,
            "probe": {"scheme": "http", "path": "/", "expected_status": 200},
        },
    }
    stage_c._oracle_spec(service_probe_gate).validate()
    adapter_kinds = sorted({*scheduled_kinds, "service_probe"})
    expected = sorted(manifest["remediation_contract"]["oracle_kinds"])
    if adapter_kinds != expected:
        raise StageCV6OfflineRunnerError("三类 oracle adapter 合同覆盖漂移")
    return {
        "scheduled_oracle_kinds": scheduled_kinds,
        "adapter_oracle_kinds": adapter_kinds,
    }


def _reevaluation_thread_id(evaluation_id: str, manifest_sha256: str) -> str:
    digest = hashlib.sha256(evaluation_id.encode("utf-8")).hexdigest()
    return f"stage-c-v6-reeval-{digest}-{manifest_sha256[:16]}"


def _source_session_root(entry: dict[str, Any], compile_sessions_root: Path) -> Path:
    return compile_sessions_root / entry["source_session_relative_path"]


def _copy_candidate_and_source_session(
    *,
    manifest: dict[str, Any],
    task: dict[str, Any],
    evaluation: dict[str, Any],
    entry: dict[str, Any],
    source_identity: dict[str, Any],
    services: Any,
    compile_sessions_root: Path,
) -> tuple[Any, AgentBuildNodeInput, AgentBuildNodeResult, Path, dict[str, Any]]:
    manifest_sha256 = protocol.canonical_sha256(manifest)
    thread_id = _reevaluation_thread_id(evaluation["evaluation_id"], manifest_sha256)
    session_id = entry["source_session_id"]
    session_root = _source_session_root(entry, compile_sessions_root)
    source_session_path = session_root / "session.json"
    source_session_value = _load_json(source_session_path)
    source_session = CompileSession.from_dict(source_session_value)
    workflow_source = session_root / "agent-workflow" / evaluation["source_attempt_id"]
    source_input_path = workflow_source / "input.json"
    source_candidate_path = workflow_source / "candidate.json"
    node_input = _load_node_input(source_input_path)
    if (
        node_input.canonical_sha256() != entry["source_node_input_sha256"]
        or node_input.session_id != session_id
        or node_input.attempt_id != evaluation["source_attempt_id"]
        or node_input.source_snapshot_sha256 != task["source_snapshot_sha256"]
    ):
        raise StageCV6OfflineRunnerError(f"{evaluation['evaluation_id']} 原 node input 身份漂移")

    destination = compile_sessions_root / thread_id / session_id
    if destination.exists():
        raise StageCV6OfflineRunnerError(f"{evaluation['evaluation_id']} 新 Session 已存在，禁止 retry")
    session = services.manager.create_session(
        thread_id=thread_id,
        repo_url=task["repository_url"],
        run_id=f"{evaluation['evaluation_id']}-run",
        session_id=session_id,
    )
    shutil.copytree(source_identity["repository"], Path(session.leadagent_repo_dir), symlinks=True)
    shutil.copytree(
        session_root / "artifacts",
        Path(session.leadagent_artifacts_dir),
        symlinks=True,
        dirs_exist_ok=True,
    )
    candidate_path = Path(session.metadata_path).parent / "agent-workflow" / evaluation["source_attempt_id"] / "candidate.json"
    candidate_path.parent.mkdir(parents=True, exist_ok=False)
    shutil.copy2(source_candidate_path, candidate_path)

    source_archive = Path(session.leadagent_repro_dir) / "source.tar"
    stage_c._run(
        [
            "git",
            "-C",
            str(source_identity["repository"]),
            "archive",
            "--format=tar",
            "--output",
            str(source_archive),
            "HEAD",
        ]
    )
    archive_sha256 = qualification.file_sha256(source_archive)
    if archive_sha256 != task["source_snapshot_sha256"]:
        raise StageCV6OfflineRunnerError(f"{evaluation['evaluation_id']} source.tar identity 漂移")

    session.commit_sha = task["commit_sha"]
    session.image = manifest["environment"]["compile_image"]
    session.image_id = None
    session.status = "inspected"
    session.build_system = source_session.build_system
    session.build_system_capabilities = list(source_session.build_system_capabilities)
    session.selected_build_system = source_session.selected_build_system
    session.executed_build_system = source_session.executed_build_system
    session.parallel_jobs = manifest["environment"]["parallel_jobs"]
    session.commands = list(source_session.commands)
    session.artifacts = []
    session.verification = None
    session.replay_recipe = None
    session.replay_source_archive_sha256 = archive_sha256
    session.replay_attempts = []
    session.completed_at = None
    session.finalized_at = None
    session.termination_requested_at = None
    session.termination_status = None
    session.termination_error = None
    session.container_id = None
    session.container_name = None
    session.error = None
    session.summary = f"Stage C v6 offline reevaluation: {evaluation['evaluation_id']}"
    services.manager.save_session(session)
    services.manager.log_event(
        session,
        "offline_reevaluation.source_bound",
        evaluation_id=evaluation["evaluation_id"],
        source_pair_id=evaluation["source_pair_id"],
        source_attempt_id=evaluation["source_attempt_id"],
        source_session_file_sha256=entry["source_session_file_sha256"],
        source_candidate_record_sha256=entry["source_candidate_record_sha256"],
        source_snapshot_sha256=archive_sha256,
    )
    node_result = _synthetic_node_result(entry, session.status)
    provenance = {
        "schema_version": "forge-stage-c-v6-synthetic-node-result-provenance-1.0.0",
        "synthetic_node_result": True,
        "synthetic_node_result_sha256": node_result.canonical_sha256(),
        "unavailable_original_fields": ["agent_steps", "wall_clock_ms"],
        "synthetic_values": {"agent_steps": 0, "wall_clock_ms": 0},
        "source_node_input_sha256": entry["source_node_input_sha256"],
        "source_candidate_record_sha256": entry["source_candidate_record_sha256"],
        "source_evidence_head_sha256": entry["source_evidence_head_sha256"],
        "source_submission_id": entry["submission_id"],
        "source_usage": entry["source_usage"],
        "original_evaluator_node_result_sha256": (entry["original_evaluator"]["node_result_sha256"] if entry["original_evaluator"] is not None else None),
        "byte_identical_to_original_node_result_claimed": False,
    }
    return session, node_input, node_result, candidate_path, provenance


def _attempt_marker(
    manifest: dict[str, Any],
    evaluation: dict[str, Any],
    entry: dict[str, Any],
    release_revision: str,
) -> dict[str, Any]:
    return {
        "schema_version": "forge-stage-c-v6-offline-evaluation-attempt-1.0.0",
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "release_revision": release_revision,
        "evaluation_id": evaluation["evaluation_id"],
        "source_pair_id": evaluation["source_pair_id"],
        "source_attempt_id": evaluation["source_attempt_id"],
        "task_id": evaluation["task_id"],
        "replicate": evaluation["replicate"],
        "source_session_file_sha256": entry["source_session_file_sha256"],
        "source_candidate_record_sha256": entry["source_candidate_record_sha256"],
        "provider_requests": 0,
        "model_tokens": 0,
        "status": "started",
        "registered_at": datetime.now(UTC).isoformat(),
    }


def _token_ledger() -> dict[str, Any]:
    return {
        "mode": "meter_each_request_without_ceiling",
        "requests": [],
        "request_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "token_total_is_termination_condition": False,
    }


def execute_evaluation(
    manifest: dict[str, Any],
    evaluation: dict[str, Any],
    entry: dict[str, Any],
    *,
    release_revision: str,
    output_dir: Path,
    compile_sessions_root: Path = DEFAULT_COMPILE_SESSIONS_ROOT,
) -> dict[str, Any]:
    evaluation_dir = output_dir / "evaluations" / evaluation["evaluation_id"]
    if evaluation_dir.exists():
        raise StageCV6OfflineRunnerError(f"{evaluation['evaluation_id']} evidence 已存在，禁止 retry")
    task = _task(manifest, evaluation["task_id"])
    started = time.perf_counter()
    session = None
    evaluation_result = None
    cleanup_succeeded = False
    error: BaseException | None = None

    with tempfile.TemporaryDirectory(prefix=f"forge-stage-c-v6-{task['task_id']}-") as temporary:
        source_identity = stage_c._clone_export(task, Path(temporary) / "source")
        stage_c._validate_prepared_source(task, source_identity)
        evaluation_dir.mkdir(parents=True, exist_ok=False)
        _write_once(
            evaluation_dir / "attempt.json",
            _attempt_marker(manifest, evaluation, entry, release_revision),
        )
        _write_once(evaluation_dir / "token-ledger.json", _token_ledger())
        try:
            with stage_c._stage_c_runtime_identity(manifest) as services:
                (
                    session,
                    node_input,
                    node_result,
                    candidate_path,
                    provenance,
                ) = _copy_candidate_and_source_session(
                    manifest=manifest,
                    task=task,
                    evaluation=evaluation,
                    entry=entry,
                    source_identity=source_identity,
                    services=services,
                    compile_sessions_root=compile_sessions_root,
                )
                _write_once(evaluation_dir / "source-receipt.json", entry)
                _write_once(
                    evaluation_dir / "synthetic-node-result-provenance.json",
                    provenance,
                )
                services.runtime.create_container(session)
                if session.image_id != manifest["environment"]["image_id"]:
                    raise StageCV6OfflineRunnerError(f"{evaluation['evaluation_id']} image identity 漂移")
                services.manager.save_session(session)
                with stage_c._offline_runtime(session) as offline_services:
                    evaluation_result = run_external_evaluator_v4(
                        node_input=node_input,
                        node_result=node_result,
                        session=session,
                        manager=offline_services.manager,
                        candidate_path=candidate_path,
                        evaluation_id=evaluation["evaluation_id"],
                        backend=ForgeCompileEvaluationBackend(oracle_registry={node_input.target_contract.functional_oracle_ref: (stage_c._oracle_spec(task))}),
                    )
        except BaseException as exc:
            error = exc
        finally:
            if session is not None:
                try:
                    finalized, cleanup = cleanup_and_finalize_compile_session_impl(session=session)
                    cleanup_succeeded = cleanup.succeeded and finalized.finalized_at is not None
                except BaseException as cleanup_exc:
                    if error is None:
                        error = cleanup_exc
            stage_c.require_zero_managed_resources()

    layers = [asdict(layer) for layer in evaluation_result.layers] if evaluation_result is not None else []
    result = {
        "schema_version": "forge-stage-c-v6-offline-evaluation-result-1.0.0",
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "release_revision": release_revision,
        "evaluation_id": evaluation["evaluation_id"],
        "source_pair_id": evaluation["source_pair_id"],
        "source_attempt_id": evaluation["source_attempt_id"],
        "task_id": evaluation["task_id"],
        "replicate": evaluation["replicate"],
        "s0_s5": layers,
        "strict_reproducible_build_success": bool(evaluation_result and evaluation_result.strict_reproducible_build_success),
        "bitwise_reproducible": (evaluation_result.bitwise_reproducible if evaluation_result is not None else None),
        "primary_failure": (evaluation_result.primary_failure if evaluation_result is not None else None),
        "provider_requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cleanup_succeeded": cleanup_succeeded,
        "zero_managed_resources": True,
        "error_class": type(error).__name__ if error is not None else None,
        "error_message": str(error)[:4096] if error is not None else None,
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "completed_at": datetime.now(UTC).isoformat(),
    }
    _write_once(evaluation_dir / "result.json", result)
    if error is not None:
        raise StageCV6OfflineRunnerError(f"{evaluation['evaluation_id']} 离线重评异常: {type(error).__name__}: {error}") from error
    if not cleanup_succeeded:
        raise StageCV6OfflineRunnerError(f"{evaluation['evaluation_id']} cleanup 未闭合")
    return result


def _completed_prefix(manifest: dict[str, Any], output_dir: Path) -> list[dict[str, Any]]:
    results = []
    encountered_gap = False
    for evaluation in manifest["schedule"]["evaluations"]:
        result_path = output_dir / "evaluations" / evaluation["evaluation_id"] / "result.json"
        attempt_path = result_path.parent / "attempt.json"
        ledger_path = result_path.parent / "token-ledger.json"
        if result_path.is_file():
            if encountered_gap:
                raise StageCV6OfflineRunnerError("离线重评 evidence 不是连续前缀")
            value = _load_json(result_path)
            ledger = _load_json(ledger_path)
            if (
                not attempt_path.is_file()
                or value.get("manifest_sha256") != protocol.canonical_sha256(manifest)
                or value.get("evaluation_id") != evaluation["evaluation_id"]
                or value.get("provider_requests") != 0
                or value.get("total_tokens") != 0
                or value.get("cleanup_succeeded") is not True
                or value.get("zero_managed_resources") is not True
                or value.get("error_class") is not None
                or ledger != _token_ledger()
            ):
                raise StageCV6OfflineRunnerError(f"{evaluation['evaluation_id']} 已有 result 无效")
            results.append(value)
        else:
            encountered_gap = True
            if attempt_path.exists() or result_path.parent.exists():
                raise StageCV6OfflineRunnerError(f"{evaluation['evaluation_id']} 存在未闭合 attempt，禁止 retry")
    return results


def collect_preflight(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    compile_sessions_root: Path = DEFAULT_COMPILE_SESSIONS_ROOT,
    require_release: bool = True,
) -> dict[str, Any]:
    protocol.validate_manifest(manifest)
    release_revision = _release_identity(manifest) if require_release else None
    receipt = _validate_source_receipt(compile_sessions_root=compile_sessions_root)
    oracle_coverage = _validate_oracle_adapter(manifest)
    stage_c.require_zero_managed_resources()
    image_id = stage_c._run(
        [
            "docker",
            "image",
            "inspect",
            manifest["environment"]["compile_image"],
            "--format",
            "{{.Id}}",
        ]
    ).stdout.strip()
    if image_id != manifest["environment"]["image_id"]:
        raise StageCV6OfflineRunnerError("Stage C v6 compile image identity 漂移")
    completed = _completed_prefix(manifest, output_dir)
    if completed and not (output_dir / "markers" / "batch-started.json").is_file():
        raise StageCV6OfflineRunnerError("已有 evaluation 但缺少 batch started marker")
    return {
        "ready": True,
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "release_revision": release_revision,
        "source_receipt_file_sha256": qualification.file_sha256(REPO_ROOT / protocol.SOURCE_RECEIPT_PATH),
        "source_evaluation_count": receipt["evaluation_count"],
        "completed_evaluation_count": len(completed),
        "remaining_evaluation_count": 22 - len(completed),
        "provider_calls": 0,
        "model_tokens": 0,
        **oracle_coverage,
        "zero_managed_resources": True,
    }


def _batch_marker(manifest: dict[str, Any], release_revision: str, status: str) -> dict[str, Any]:
    return {
        "schema_version": "forge-stage-c-v6-offline-batch-marker-1.0.0",
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "release_revision": release_revision,
        "status": status,
        "evaluation_count": manifest["schedule"]["evaluation_count"],
        "provider_requests": 0,
        "model_tokens": 0,
        "recorded_at": datetime.now(UTC).isoformat(),
    }


def execute_batch(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    compile_sessions_root: Path = DEFAULT_COMPILE_SESSIONS_ROOT,
) -> dict[str, Any]:
    release_revision = _release_identity(manifest)
    preflight = collect_preflight(
        manifest,
        output_dir=output_dir,
        compile_sessions_root=compile_sessions_root,
    )
    receipt = _load_json(REPO_ROOT / protocol.SOURCE_RECEIPT_PATH)
    entries = _receipt_by_evaluation(receipt)
    started_marker = output_dir / "markers" / "batch-started.json"
    if not started_marker.exists():
        _write_once(started_marker, _batch_marker(manifest, release_revision, "started"))
    else:
        marker = _load_json(started_marker)
        if marker.get("manifest_sha256") != protocol.canonical_sha256(manifest) or marker.get("release_revision") != release_revision or marker.get("status") != "started":
            raise StageCV6OfflineRunnerError("batch started marker identity 漂移")

    completed_ids = {result["evaluation_id"] for result in _completed_prefix(manifest, output_dir)}
    for evaluation in manifest["schedule"]["evaluations"]:
        if evaluation["evaluation_id"] in completed_ids:
            continue
        execute_evaluation(
            manifest,
            evaluation,
            entries[evaluation["evaluation_id"]],
            release_revision=release_revision,
            output_dir=output_dir,
            compile_sessions_root=compile_sessions_root,
        )
    results = _completed_prefix(manifest, output_dir)
    if len(results) != 22:
        raise StageCV6OfflineRunnerError("Stage C v6 22 条重评未全部闭合")
    completed_marker = output_dir / "markers" / "batch-completed.json"
    if not completed_marker.exists():
        _write_once(completed_marker, _batch_marker(manifest, release_revision, "completed"))
    stage_c.require_zero_managed_resources()
    return {
        **preflight,
        "status": "completed",
        "completed_evaluation_count": 22,
        "remaining_evaluation_count": 0,
        "strict_success_count": sum(result["strict_reproducible_build_success"] for result in results),
    }


def _result_report(manifest: dict[str, Any], output_dir: Path, results: list[dict[str, Any]]) -> dict[str, Any]:
    layer_summary = {}
    for layer_name in ("S0", "S1", "S2", "S3", "S4", "S5"):
        statuses = [next(layer["status"] for layer in result["s0_s5"] if layer["layer"] == layer_name) for result in results]
        layer_summary[layer_name] = {status: statuses.count(status) for status in sorted(set(statuses))}
    projects: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        projects.setdefault(result["task_id"], []).append(result)
    project_summary = {
        task_id: {
            "evaluation_count": len(values),
            "strict_success_count": sum(value["strict_reproducible_build_success"] for value in values),
            "replicates": [
                {
                    "replicate": value["replicate"],
                    "evaluation_id": value["evaluation_id"],
                    "strict_reproducible_build_success": value["strict_reproducible_build_success"],
                    "primary_failure": value["primary_failure"],
                }
                for value in sorted(values, key=lambda item: item["replicate"])
            ],
        }
        for task_id, values in sorted(projects.items())
    }
    return {
        "schema_version": "forge-stage-c-v6-offline-reevaluation-report-1.0.0",
        "document_type": "forge_stage_c_v6_offline_reevaluation_report",
        "identity": {
            "manifest_sha256": protocol.canonical_sha256(manifest),
            "release_revision": results[0]["release_revision"],
            "parent_candidate_manifest_sha256": protocol.CANDIDATE_MANIFEST_SHA256,
            "source_v5_manifest_sha256": protocol.candidate.V5_MANIFEST_SHA256,
        },
        "analysis": {
            "kind": "post_hoc_measurement_remediation_sensitivity_analysis",
            "v5_original_result_replaced": False,
            "source_selection": "v5_b_arms_with_submitted_candidate",
            "excluded_no_candidate_pairs": manifest["schedule"]["excluded_no_candidate_pairs"],
            "independent_unit": "project",
        },
        "source_v5_frozen_result": {
            "arm_A_strict_success": "19/24",
            "arm_B_strict_success": "0/24",
        },
        "batch": {
            "evaluation_count": len(results),
            "strict_success_count": sum(result["strict_reproducible_build_success"] for result in results),
            "bitwise_reproducible_count": sum(result["bitwise_reproducible"] is True for result in results),
            "provider_requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cleanup_succeeded_count": sum(result["cleanup_succeeded"] is True for result in results),
            "zero_managed_resources": True,
        },
        "layer_summary": layer_summary,
        "project_summary": project_summary,
        "evaluations": results,
        "completed_at": datetime.now(UTC).isoformat(),
    }


def _markdown_report(report: dict[str, Any]) -> str:
    batch = report["batch"]
    rows = []
    for task_id, project in report["project_summary"].items():
        outcomes = ", ".join(f"r{item['replicate']}={'pass' if item['strict_reproducible_build_success'] else 'fail'}" for item in project["replicates"])
        rows.append(f"| `{task_id}` | {project['strict_success_count']}/{project['evaluation_count']} | {outcomes} |")
    return (
        "# Stage C v6 零 Provider 离线定向重评结果\n\n"
        "本报告是对 v5 中 22 个已提交 B 臂候选的事后测量修复敏感性分析。"
        "它不替代 v5 正式结果：A 臂仍为 `19/24`，B 臂仍为 `0/24`。\n\n"
        f"22 条重评中 strict success 为 `{batch['strict_success_count']}/22`，"
        f"bitwise reproducible 为 `{batch['bitwise_reproducible_count']}/22`。"
        "本阶段没有 Provider 请求，input/output/total token 均为 0；"
        "22 条 cleanup 全部闭合，结束时 0 managed resources。\n\n"
        "| Project | Strict success | Replicates |\n"
        "| --- | ---: | --- |\n" + "\n".join(rows) + "\n\n两次未生成候选的 CivetWeb attempt 不在重评分母中。"
        "22 个 attempt 也不能作为 22 个独立项目解释。\n"
    )


def _inventory(root: Path, excluded: set[Path]) -> dict[str, Any]:
    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path in excluded:
            continue
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": qualification.file_sha256(path),
            }
        )
    return {
        "schema_version": "forge-stage-c-v6-offline-inventory-1.0.0",
        "file_count": len(files),
        "total_size_bytes": sum(item["size_bytes"] for item in files),
        "files": files,
    }


def write_report(manifest: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    results = _completed_prefix(manifest, output_dir)
    if len(results) != 22 or not (output_dir / "markers" / "batch-completed.json").is_file():
        raise StageCV6OfflineRunnerError("Stage C v6 batch 尚未完整闭合")
    report_path = output_dir / manifest["execution"]["result_report"]
    markdown_path = output_dir / manifest["execution"]["result_report_markdown"]
    inventory_path = output_dir / manifest["execution"]["inventory_report"]
    if report_path.exists() or markdown_path.exists() or inventory_path.exists():
        if not (report_path.is_file() and markdown_path.is_file() and inventory_path.is_file()):
            raise StageCV6OfflineRunnerError("Stage C v6 报告只完成了部分写入")
        return _load_json(report_path)
    report = _result_report(manifest, output_dir, results)
    _write_once(report_path, report)
    _write_once(markdown_path, _markdown_report(report))
    inventory = _inventory(output_dir, {inventory_path})
    inventory["manifest_sha256"] = protocol.canonical_sha256(manifest)
    inventory["report_file_sha256"] = qualification.file_sha256(report_path)
    inventory["report_markdown_file_sha256"] = qualification.file_sha256(markdown_path)
    _write_once(inventory_path, inventory)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "preflight", "run", "report"))
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest()
    if args.command == "validate":
        result: Any = {
            "status": "valid_authorized",
            "manifest_sha256": protocol.canonical_sha256(manifest),
            "provider_calls": 0,
            "model_tokens": 0,
            "evaluation_count": manifest["schedule"]["evaluation_count"],
        }
    elif args.command == "preflight":
        result = collect_preflight(manifest)
    elif args.command == "run":
        result = execute_batch(manifest)
        write_report(manifest)
    else:
        result = write_report(manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
