#!/usr/bin/env python3
"""执行 Stage C v8 workspace remediation authorized canary。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
import uuid
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_stage_c_runner as stage_c  # noqa: E402
import forge_stage_c_v7_prefreeze_canary_authorized_runner as base_runner  # noqa: E402
import forge_stage_c_v8_workspace_remediation_authorized_protocol as protocol  # noqa: E402
import forge_stage_c_v8_workspace_remediation_runner as candidate_runner  # noqa: E402

from deerflow.compile.agent_workflow_runtime_v3 import run_agent_workflow_node_v3  # noqa: E402
from deerflow.compile.agent_workflow_schemas import AgentWorkflowExperimentIdentity  # noqa: E402
from deerflow.compile.evidence import (  # noqa: E402
    ExperimentLedger,
    ExperimentPolicy,
    activate_experiment,
    deactivate_experiment,
    new_evidence_id,
)
from deerflow.compile.external_evaluator_v4 import (  # noqa: E402
    ForgeCompileEvaluationBackend,
    run_external_evaluator_v4,
)
from deerflow.compile.manager import CompileSessionManager  # noqa: E402
from deerflow.compile.operations import (  # noqa: E402
    cleanup_and_finalize_compile_session_impl,
    clone_repository_impl,
    get_compile_services,
    inspect_build_system_impl,
    prepare_compile_session_impl,
)

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_OUTPUT_DIR = REPO_ROOT / protocol.EVIDENCE_DIRECTORY_RELATIVE


class StageCV8AuthorizedRunnerError(RuntimeError):
    """授权 release、workspace、evidence 或运行终态无效。"""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageCV8AuthorizedRunnerError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise StageCV8AuthorizedRunnerError(f"JSON 根节点必须是对象: {path}")
    return value


def _write_once(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise StageCV8AuthorizedRunnerError(f"不可覆盖已存在的 evidence: {path}") from exc


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _manifest_sha256(manifest: dict[str, Any]) -> str:
    return protocol.canonical_sha256(manifest)


def _task(manifest: dict[str, Any], task_id: str) -> dict[str, Any]:
    matches = [task for task in manifest["tasks"] if task["task_id"] == task_id]
    if len(matches) != 1:
        raise StageCV8AuthorizedRunnerError(f"未知或重复 task: {task_id}")
    return matches[0]


def _output_dir(manifest: dict[str, Any], output_dir: Path, repo_root: Path) -> Path:
    expected = repo_root.resolve(strict=True) / manifest["execution"]["evidence_directory_relative"]
    if output_dir.resolve(strict=False) != expected or expected.parent != repo_root.resolve(strict=True) / ".compile-sessions":
        raise StageCV8AuthorizedRunnerError("evidence 必须写入 release root 下冻结直属目录")
    return output_dir


def require_release_identity(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, str]:
    try:
        return base_runner.require_release_identity(manifest, repo_root)
    except base_runner.StageCV7AuthorizedRunnerError as exc:
        raise StageCV8AuthorizedRunnerError(str(exc)) from exc


def require_network_medium(manifest: dict[str, Any]) -> str:
    try:
        return base_runner.require_network_medium(manifest)
    except base_runner.StageCV7AuthorizedRunnerError as exc:
        raise StageCV8AuthorizedRunnerError(str(exc)) from exc


def require_docker_identity(manifest: dict[str, Any]) -> dict[str, str]:
    try:
        return base_runner.require_docker_identity(manifest)
    except base_runner.StageCV7AuthorizedRunnerError as exc:
        raise StageCV8AuthorizedRunnerError(str(exc)) from exc


def require_zero_managed_resources() -> None:
    try:
        base_runner.require_zero_managed_resources()
    except base_runner.StageCV7AuthorizedRunnerError as exc:
        raise StageCV8AuthorizedRunnerError(str(exc)) from exc


def _provider_config_preflight(manifest: dict[str, Any]) -> None:
    base_runner._provider_config_preflight(manifest)


def _create_provider_model(manifest: dict[str, Any], thread_id: str | None = None) -> Any:
    return base_runner._create_provider_model(manifest, thread_id)


def _attempt_paths(manifest: dict[str, Any], output_dir: Path, attempt: dict[str, Any]) -> tuple[Path, Path, Path]:
    values = {"sequence": attempt["sequence"], "task_id": attempt["task_id"]}
    execution = manifest["execution"]
    return (
        output_dir / execution["attempt_marker_template"].format(**values),
        output_dir / execution["attempt_result_template"].format(**values),
        output_dir / execution["attempt_ledger_template"].format(**values),
    )


def _evidence_files(output_dir: Path) -> list[str]:
    if not output_dir.exists():
        return []
    return sorted(path.relative_to(output_dir).as_posix() for path in output_dir.rglob("*") if path.is_file())


def require_workspace_identity(
    manifest: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    output_dir: Path | None = None,
) -> dict[str, str]:
    try:
        return candidate_runner.require_workspace_identity(manifest, repo_root=repo_root, output_dir=output_dir)
    except candidate_runner.StageCV8RunnerError as exc:
        raise StageCV8AuthorizedRunnerError(str(exc)) from exc


def _node_input(manifest: dict[str, Any], task: dict[str, Any], session: Any, attempt_id: str) -> Any:
    node_input = candidate_runner._node_input(manifest, task, session, attempt_id)
    frozen = manifest["frozen_authorized_components"]
    return replace(
        node_input,
        operation_policy_ref="stage-c-v8-workspace-remediation-authorized-operation-policy-v1",
        experiment_identity=AgentWorkflowExperimentIdentity(
            manifest_sha256=_manifest_sha256(manifest),
            protocol_sha256=frozen[protocol.PROTOCOL_PATH],
            runner_sha256=frozen[protocol.RUNNER_PATH],
        ),
    )


def _thread_id(attempt: dict[str, Any], manifest_sha256: str) -> str:
    identity = hashlib.sha256(attempt["attempt_id"].encode("utf-8")).hexdigest()
    return f"stage-c-v8-authorized-b-{identity[:32]}-{manifest_sha256[:16]}"


def _validate_all_node_inputs(manifest: dict[str, Any]) -> None:
    session = type(
        "StageCV8AuthorizedContractSession",
        (),
        {"session_id": "stage-c-v8-authorized-contract"},
    )()
    thread_ids: list[str] = []
    for attempt in manifest["schedule"]["attempts"]:
        task = _task(manifest, attempt["task_id"])
        _node_input(manifest, task, session, attempt["attempt_id"]).validate()
        stage_c._oracle_spec(task).validate()
        thread_id = _thread_id(attempt, _manifest_sha256(manifest))
        CompileSessionManager._validate_session_components(thread_id, "stage-c-v8-authorized-contract")
        thread_ids.append(thread_id)
    if len(thread_ids) != len(set(thread_ids)):
        raise StageCV8AuthorizedRunnerError("v8 authorized thread identity 不唯一")


def collect_preflight(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    require_empty: bool,
) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    _validate_all_node_inputs(manifest)
    workspace = require_workspace_identity(manifest, repo_root=repo_root, output_dir=output_dir)
    _output_dir(manifest, output_dir, repo_root)
    release = require_release_identity(manifest, repo_root)
    medium = require_network_medium(manifest)
    docker = require_docker_identity(manifest)
    require_zero_managed_resources()
    _provider_config_preflight(manifest)
    files = _evidence_files(output_dir)
    if require_empty and files:
        raise StageCV8AuthorizedRunnerError("reachability 前要求授权 evidence 目录为空")
    return {
        "ready": True,
        "manifest_sha256": _manifest_sha256(manifest),
        "parent_manifest_sha256": manifest["parent_candidate"]["canonical_sha256"],
        "release_revision": release["revision"],
        "workspace": workspace,
        "network_access_medium": medium,
        "docker": docker,
        "credential_check": "environment_variable_presence_only",
        "evidence_files": files,
        "zero_managed_resources": True,
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
    }


def _claim_marker(
    path: Path,
    *,
    document_type: str,
    manifest_sha256: str,
    revision: str,
    attempt: dict[str, Any] | None = None,
) -> None:
    _write_once(
        path,
        {
            "schema_version": "forge-stage-c-v8-authorized-marker-1.0.0",
            "document_type": document_type,
            "manifest_sha256": manifest_sha256,
            "release_revision": revision,
            "sequence": attempt["sequence"] if attempt else None,
            "task_id": attempt["task_id"] if attempt else None,
            "attempt_id": attempt["attempt_id"] if attempt else None,
            "status": "started",
            "error_class": None,
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )


def _finish_marker(path: Path, *, status: str, error_class: str | None = None) -> None:
    marker = _load_json(path)
    if marker.get("status") != "started":
        raise StageCV8AuthorizedRunnerError("create-once marker 不处于 started")
    marker["status"] = status
    marker["error_class"] = error_class
    marker["updated_at"] = datetime.now(UTC).isoformat()
    _atomic_write(path, marker)


def execute_reachability(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    model_factory: Callable[[dict[str, Any], str | None], Any] = _create_provider_model,
) -> dict[str, Any]:
    preflight = collect_preflight(manifest, output_dir=output_dir, repo_root=repo_root, require_empty=True)
    reachability = manifest["execution"]["reachability"]
    marker_path = output_dir / reachability["marker"]
    digest = _manifest_sha256(manifest)
    _claim_marker(
        marker_path,
        document_type="forge_stage_c_v8_authorized_reachability_attempt",
        manifest_sha256=digest,
        revision=preflight["release_revision"],
    )
    started = time.perf_counter()
    try:
        response = model_factory(manifest, None).invoke(reachability["prompt"])
        response_text = base_runner.stage_b._response_text(response).strip()
        actual_model, usage = base_runner.stage_b.model_response_metadata(response)
        input_tokens = usage.get("prompt_tokens", usage.get("input_tokens", 0))
        output_tokens = usage.get("completion_tokens", usage.get("output_tokens", 0))
        total_tokens = usage.get("total_tokens")
        passed = response_text == reachability["expected_response"] and actual_model == manifest["provider"]["actual_model"] and all(type(value) is int and value >= 0 for value in (input_tokens, output_tokens, total_tokens))
        report = {
            "schema_version": "forge-stage-c-v8-authorized-reachability-1.0.0",
            "document_type": "forge_stage_c_v8_authorized_reachability",
            "manifest_sha256": digest,
            "release_revision": preflight["release_revision"],
            "provider": manifest["provider"]["provider"],
            "model": manifest["provider"]["profile"],
            "actual_model": actual_model,
            "endpoint": manifest["provider"]["endpoint"],
            "request_count": 1,
            "token_ledger": [
                {
                    "request_sequence": 1,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                }
            ],
            "recorded_tokens": total_tokens,
            "passed": passed,
            "response_sha256": hashlib.sha256(response_text.encode("utf-8")).hexdigest(),
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "completed_at": datetime.now(UTC).isoformat(),
        }
        _write_once(output_dir / reachability["report"], report)
        if not passed:
            raise StageCV8AuthorizedRunnerError("唯一 reachability 响应或 identity 无效")
    except BaseException as exc:
        _finish_marker(marker_path, status="failed", error_class=type(exc).__name__)
        raise
    _finish_marker(marker_path, status="passed")
    return report


def require_passed_reachability(manifest: dict[str, Any], output_dir: Path, revision: str) -> dict[str, Any]:
    reachability = manifest["execution"]["reachability"]
    marker = _load_json(output_dir / reachability["marker"])
    report = _load_json(output_dir / reachability["report"])
    digest = _manifest_sha256(manifest)
    expected_hash = hashlib.sha256(reachability["expected_response"].encode("utf-8")).hexdigest()
    token_ledger = report.get("token_ledger")
    if (
        marker.get("status") != "passed"
        or marker.get("manifest_sha256") != digest
        or marker.get("release_revision") != revision
        or report.get("passed") is not True
        or report.get("manifest_sha256") != digest
        or report.get("release_revision") != revision
        or report.get("provider") != manifest["provider"]["provider"]
        or report.get("model") != manifest["provider"]["profile"]
        or report.get("actual_model") != manifest["provider"]["actual_model"]
        or report.get("endpoint") != manifest["provider"]["endpoint"]
        or report.get("request_count") != 1
        or report.get("response_sha256") != expected_hash
        or not isinstance(token_ledger, list)
        or len(token_ledger) != 1
        or token_ledger[0].get("total_tokens") != report.get("recorded_tokens")
    ):
        raise StageCV8AuthorizedRunnerError("唯一 reachability 未形成同 revision 通过终态")
    return report


def _experiment_policy(manifest: dict[str, Any], task: dict[str, Any], attempt: dict[str, Any]) -> ExperimentPolicy:
    policy = base_runner._experiment_policy(manifest, task, attempt)
    return replace(
        policy,
        benchmark_id="forge-stage-c-v8-workspace-remediation-canary-authorized-v1",
        manifest_sha256=_manifest_sha256(manifest),
    )


def _event_observations(events_path: Path) -> dict[str, Any]:
    try:
        return base_runner._event_observations(events_path)
    except base_runner.StageCV7AuthorizedRunnerError as exc:
        raise StageCV8AuthorizedRunnerError(str(exc)) from exc


@contextmanager
def _runtime_identity(manifest: dict[str, Any], repo_root: Path):
    services = get_compile_services()
    manager = services.manager
    runtime = services.runtime
    original = (
        manager.paths,
        manager.default_image,
        manager.parallel_jobs,
        runtime.config.image,
        runtime.config.parallel_jobs,
        runtime.config.replay_timeout_seconds,
    )
    try:
        manager.paths = candidate_runner._explicit_paths(repo_root)
        manager.default_image = manifest["environment"]["compile_image"]
        manager.parallel_jobs = manifest["environment"]["parallel_jobs"]
        runtime.config.image = manifest["environment"]["compile_image"]
        runtime.config.parallel_jobs = manifest["environment"]["parallel_jobs"]
        runtime.config.replay_timeout_seconds = manifest["budget"]["per_attempt"]["replay_timeout_seconds"]
        yield services
    finally:
        (
            manager.paths,
            manager.default_image,
            manager.parallel_jobs,
            runtime.config.image,
            runtime.config.parallel_jobs,
            runtime.config.replay_timeout_seconds,
        ) = original


def _bind_replay_source_archive(task: dict[str, Any], session: Any, manager: CompileSessionManager) -> None:
    try:
        candidate_runner._bind_replay_source_archive(task, session, manager)
    except candidate_runner.StageCV8RunnerError as exc:
        raise StageCV8AuthorizedRunnerError(str(exc)) from exc


async def execute_attempt(
    manifest: dict[str, Any],
    attempt: dict[str, Any],
    *,
    release_revision: str,
    output_dir: Path,
    repo_root: Path = REPO_ROOT,
    model_factory: Callable[[dict[str, Any], str | None], Any] = _create_provider_model,
) -> dict[str, Any]:
    require_workspace_identity(manifest, repo_root=repo_root, output_dir=output_dir)
    _output_dir(manifest, output_dir, repo_root)
    task = _task(manifest, attempt["task_id"])
    digest = _manifest_sha256(manifest)
    marker_path, result_path, ledger_path = _attempt_paths(manifest, output_dir, attempt)
    _claim_marker(
        marker_path,
        document_type="forge_stage_c_v8_authorized_canary_attempt",
        manifest_sha256=digest,
        revision=release_revision,
        attempt=attempt,
    )
    ledger = ExperimentLedger.create(
        ledger_path,
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={
            "manifest_sha256": digest,
            "release_revision": release_revision,
            "task_id": task["task_id"],
            "attempt_id": attempt["attempt_id"],
        },
    )
    thread_id = _thread_id(attempt, digest)
    session = finalized = cleanup = node_result = evaluation = None
    active = False
    error_class = error_message_sha256 = events_path = None
    started = time.perf_counter()
    try:
        activate_experiment(
            thread_id=thread_id,
            experiment_id=ledger.experiment_id,
            physical_attempt_id=ledger.physical_attempt_id,
            ledger=ledger,
            policy=_experiment_policy(manifest, task, attempt),
        )
        active = True
        with _runtime_identity(manifest, repo_root) as services:
            try:
                session = prepare_compile_session_impl(
                    thread_id=thread_id,
                    repo_url=task["repository_url"],
                    run_id=f"stage-c-v8-authorized-{task['task_id']}-{uuid.uuid4().hex}",
                    task_description=f"Stage C v8 workspace remediation canary: {task['task_id']}",
                )
                clone, _message = clone_repository_impl(
                    session=session,
                    repo_url=task["repository_url"],
                    commit_sha=task["commit_sha"],
                    depth=1,
                    max_retries=1,
                )
                if clone.exit_code != 0 or session.commit_sha != task["commit_sha"]:
                    raise StageCV8AuthorizedRunnerError(f"{task['task_id']} 无法检出冻结 commit")
                _bind_replay_source_archive(task, session, services.manager)
                primary, _detected, _suggested = inspect_build_system_impl(session=session)
                if primary not in task["build_system_capabilities"]:
                    raise StageCV8AuthorizedRunnerError(f"{task['task_id']} build-system identity 漂移")
                session.selected_build_system = task["selected_build_system"]
                services.manager.save_session(session)
                node_input = _node_input(manifest, task, session, attempt["attempt_id"])
                oracle_spec = stage_c._oracle_spec(task)
                with stage_c._offline_runtime(session) as offline_services:
                    node_result = await run_agent_workflow_node_v3(
                        node_input=node_input,
                        session=session,
                        manager=offline_services.manager,
                        model=model_factory(manifest, thread_id),
                        oracle_registry={oracle_spec.oracle_ref: oracle_spec},
                    )
                    workflow_dir = Path(session.metadata_path).parent / "agent-workflow" / attempt["attempt_id"]
                    events_path = workflow_dir / "events.jsonl"
                    if node_result.candidate_submitted:
                        evaluation = run_external_evaluator_v4(
                            node_input=node_input,
                            node_result=node_result,
                            session=session,
                            manager=offline_services.manager,
                            candidate_path=workflow_dir / "candidate.json",
                            evaluation_id=f"{attempt['canary_id']}-evaluation-v4",
                            backend=ForgeCompileEvaluationBackend(oracle_registry={oracle_spec.oracle_ref: oracle_spec}),
                        )
            finally:
                if session is not None:
                    finalized, cleanup = cleanup_and_finalize_compile_session_impl(session=session)
    except BaseException as exc:
        error_class = type(exc).__name__
        error_message_sha256 = hashlib.sha256(str(exc).encode("utf-8", errors="replace")).hexdigest()
    finally:
        if active:
            deactivate_experiment(thread_id)
        try:
            require_zero_managed_resources()
        except BaseException as resource_exc:
            _finish_marker(marker_path, status="failed", error_class=type(resource_exc).__name__)
            raise
    cleanup_succeeded = session is None or bool(cleanup and cleanup.succeeded and finalized and finalized.finalized_at is not None)
    if not cleanup_succeeded:
        _finish_marker(marker_path, status="failed", error_class="CleanupIncomplete")
        raise StageCV8AuthorizedRunnerError(f"{attempt['attempt_id']} cleanup 未闭合")
    observations = (
        _event_observations(events_path)
        if events_path is not None and events_path.is_file()
        else {
            "token_ledger": [],
            "submit_attempts": 0,
            "rejection_codes": [],
            "rejection_evidence_count": 0,
            "same_attempt_repair_observed": False,
        }
    )
    usage = node_result.usage if node_result is not None else None
    recorded_tokens = usage.recorded_tokens if usage else 0
    if sum(item["total_tokens"] for item in observations["token_ledger"]) != recorded_tokens:
        _finish_marker(marker_path, status="failed", error_class="TokenLedgerMismatch")
        raise StageCV8AuthorizedRunnerError("逐请求 token ledger 与 Runtime v3 usage 不一致")
    layers = [asdict(layer) for layer in evaluation.layers] if evaluation is not None else []
    strict_success = bool(evaluation and evaluation.strict_reproducible_build_success)
    result = {
        "schema_version": "forge-stage-c-v8-authorized-attempt-result-1.0.0",
        "document_type": "forge_stage_c_v8_authorized_attempt_result",
        "manifest_sha256": digest,
        "release_revision": release_revision,
        "sequence": attempt["sequence"],
        "task_id": task["task_id"],
        "attempt_id": attempt["attempt_id"],
        "canary_id": attempt["canary_id"],
        "method": "forge-agent-workflow-node-v3",
        "session_id": finalized.session_id if finalized is not None else None,
        "session_status": finalized.status if finalized is not None else None,
        "candidate_generated": bool(node_result and node_result.candidate_generated_observed),
        "candidate_submitted": bool(node_result and node_result.candidate_submitted),
        "candidate_record_sha256": (node_result.candidate_record_sha256 if node_result else None),
        "node_status": node_result.node_status if node_result else "failed",
        "model_requests": usage.model_requests if usage else 0,
        "recorded_tokens": recorded_tokens,
        "request_token_ledger": observations["token_ledger"],
        "agent_steps": usage.agent_steps if usage else 0,
        "tool_calls": usage.tool_calls if usage else 0,
        "commands": usage.commands if usage else 0,
        "submit_attempts": observations["submit_attempts"],
        "rejection_codes": observations["rejection_codes"],
        "rejection_evidence_count": observations["rejection_evidence_count"],
        "same_attempt_repair_observed": observations["same_attempt_repair_observed"],
        "s0_s5": layers,
        "strict_reproducible_build_success": strict_success,
        "bitwise_reproducible": (evaluation.bitwise_reproducible if evaluation is not None else None),
        "evaluation_sha256": (evaluation.canonical_sha256() if evaluation is not None else None),
        "cleanup_succeeded": True,
        "zero_managed_resources": True,
        "canary_passed": strict_success and error_class is None,
        "error_class": error_class,
        "error_message_sha256": error_message_sha256,
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "completed_at": datetime.now(UTC).isoformat(),
    }
    _write_once(result_path, result)
    ledger.append(
        "experiment.completed",
        {
            "status": "passed" if result["canary_passed"] else "failed",
            "result_sha256": protocol.file_sha256(result_path),
        },
    )
    _finish_marker(marker_path, status="completed")
    return result


def _completed_prefix(manifest: dict[str, Any], output_dir: Path, revision: str) -> tuple[list[dict[str, Any]], int]:
    digest = _manifest_sha256(manifest)
    completed: list[dict[str, Any]] = []
    gap_seen = False
    for index, attempt in enumerate(manifest["schedule"]["attempts"]):
        marker_path, result_path, _ledger_path = _attempt_paths(manifest, output_dir, attempt)
        if not marker_path.exists() and not result_path.exists():
            gap_seen = True
            continue
        if gap_seen or not marker_path.is_file() or not result_path.is_file():
            raise StageCV8AuthorizedRunnerError("attempt evidence 不是完整连续前缀")
        marker = _load_json(marker_path)
        result = _load_json(result_path)
        token_ledger = result.get("request_token_ledger")
        recorded_tokens = result.get("recorded_tokens")
        if (
            marker.get("status") != "completed"
            or marker.get("manifest_sha256") != digest
            or marker.get("release_revision") != revision
            or marker.get("attempt_id") != attempt["attempt_id"]
            or result.get("manifest_sha256") != digest
            or result.get("release_revision") != revision
            or result.get("sequence") != attempt["sequence"]
            or result.get("task_id") != attempt["task_id"]
            or result.get("attempt_id") != attempt["attempt_id"]
            or type(recorded_tokens) is not int
            or recorded_tokens < 0
            or not isinstance(token_ledger, list)
            or sum(item.get("total_tokens", -1) for item in token_ledger) != recorded_tokens
            or result.get("cleanup_succeeded") is not True
            or result.get("zero_managed_resources") is not True
            or type(result.get("canary_passed")) is not bool
        ):
            raise StageCV8AuthorizedRunnerError(f"attempt evidence 未闭合: {attempt['attempt_id']}")
        completed.append(result)
        if index != len(completed) - 1:
            raise StageCV8AuthorizedRunnerError("attempt 顺序发生漂移")
    return completed, len(completed)


def _summarize(
    manifest: dict[str, Any],
    revision: str,
    reachability: dict[str, Any],
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    stopped = next((item for item in outcomes if not item["canary_passed"]), None)
    layers = {name: sum(any(layer["layer"] == name and layer["status"] == "passed" for layer in item["s0_s5"]) for item in outcomes) for name in ("S0", "S1", "S2", "S3", "S4", "S5")}
    attempt_tokens = sum(item["recorded_tokens"] for item in outcomes)
    return {
        "schema_version": "forge-stage-c-v8-authorized-canary-report-1.0.0",
        "document_type": "forge_stage_c_v8_authorized_canary_report",
        "manifest_sha256": _manifest_sha256(manifest),
        "parent_manifest_sha256": manifest["parent_candidate"]["canonical_sha256"],
        "release_revision": revision,
        "status": "stopped_on_first_failure" if stopped else "completed",
        "scheduled_task_order": [item["task_id"] for item in manifest["schedule"]["attempts"]],
        "observed_task_order": [item["task_id"] for item in outcomes],
        "observed_attempt_count": len(outcomes),
        "stopped_after_task": stopped["task_id"] if stopped else None,
        "strict_success_count": sum(item["canary_passed"] for item in outcomes),
        "s0_s5_passed": layers,
        "reachability_recorded_tokens": reachability["recorded_tokens"],
        "attempt_recorded_tokens": attempt_tokens,
        "total_recorded_tokens": reachability["recorded_tokens"] + attempt_tokens,
        "token_ceiling": None,
        "token_total_is_termination_condition": False,
        "descriptive_canary_only": True,
        "treatment_effect_estimated": False,
        "p_value_computed": False,
        "model_ranking_performed": False,
        "historical_outcomes_pooled": False,
        "cleanup_succeeded": all(item["cleanup_succeeded"] for item in outcomes),
        "zero_managed_resources": True,
        "outcomes": outcomes,
        "completed_at": datetime.now(UTC).isoformat(),
    }


async def run_batch_async(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    attempt_executor: Callable[..., Any] = execute_attempt,
) -> dict[str, Any]:
    preflight = collect_preflight(manifest, output_dir=output_dir, repo_root=repo_root, require_empty=False)
    revision = preflight["release_revision"]
    reachability = require_passed_reachability(manifest, output_dir, revision)
    completed, next_index = _completed_prefix(manifest, output_dir, revision)
    digest = _manifest_sha256(manifest)
    marker_path = output_dir / manifest["execution"]["batch_marker"]
    if marker_path.exists():
        marker = _load_json(marker_path)
        if marker.get("status") != "started" or marker.get("manifest_sha256") != digest or marker.get("release_revision") != revision:
            raise StageCV8AuthorizedRunnerError("batch marker 无法恢复")
    else:
        if completed:
            raise StageCV8AuthorizedRunnerError("缺少 create-once batch marker，拒绝导入既有 attempt evidence")
        _claim_marker(
            marker_path,
            document_type="forge_stage_c_v8_authorized_canary_batch",
            manifest_sha256=digest,
            revision=revision,
        )
    try:
        if not completed or completed[-1]["canary_passed"]:
            for attempt in manifest["schedule"]["attempts"][next_index:]:
                outcome = attempt_executor(
                    manifest,
                    attempt,
                    release_revision=revision,
                    output_dir=output_dir,
                    repo_root=repo_root,
                )
                if hasattr(outcome, "__await__"):
                    outcome = await outcome
                completed.append(outcome)
                require_zero_managed_resources()
                if not outcome["canary_passed"]:
                    break
        report = _summarize(manifest, revision, reachability, completed)
        _write_once(output_dir / manifest["execution"]["batch_report"], report)
    except BaseException as exc:
        _finish_marker(marker_path, status="failed", error_class=type(exc).__name__)
        raise
    _finish_marker(
        marker_path,
        status="stopped" if report["status"] == "stopped_on_first_failure" else "passed",
    )
    return report


def run_batch(manifest: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return asyncio.run(run_batch_async(manifest, **kwargs))


def load_report(manifest: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    report = _load_json(output_dir / manifest["execution"]["batch_report"])
    if (
        report.get("manifest_sha256") != _manifest_sha256(manifest)
        or report.get("parent_manifest_sha256") != manifest["parent_candidate"]["canonical_sha256"]
        or report.get("scheduled_task_order") != [item["task_id"] for item in manifest["schedule"]["attempts"]]
        or report.get("token_ceiling") is not None
        or report.get("treatment_effect_estimated") is not False
    ):
        raise StageCV8AuthorizedRunnerError("Stage C v8 authorized canary report identity 发生漂移")
    return report


def validate_runtime(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    _validate_all_node_inputs(manifest)
    return {
        "status": "valid",
        "manifest_sha256": _manifest_sha256(manifest),
        "workspace_binding": "release_repository_root",
        "runtime": "agent-workflow-runtime-v3",
        "external_evaluator": "external-evaluator-v4",
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
        "credential_read": False,
        "evidence_written": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "preflight", "reachability", "run", "report"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest(args.manifest)
    if args.command == "validate":
        result: Mapping[str, Any] = validate_runtime(manifest)
    elif args.command == "preflight":
        result = collect_preflight(manifest, require_empty=True)
    elif args.command == "reachability":
        result = execute_reachability(manifest)
    elif args.command == "run":
        result = run_batch(manifest)
    else:
        result = load_report(manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
