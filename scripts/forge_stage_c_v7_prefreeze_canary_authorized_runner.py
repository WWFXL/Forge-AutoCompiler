#!/usr/bin/env python3
"""执行 Stage C v7 pre-freeze verifier authorized canary。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_agent_workflow_stage_b_phase5_v2_authorized_runner as stage_b  # noqa: E402
import forge_stage_c_runner as stage_c  # noqa: E402
import forge_stage_c_v7_prefreeze_canary_authorized_protocol as protocol  # noqa: E402

from deerflow.compile.agent_workflow_runtime_v3 import run_agent_workflow_node_v3  # noqa: E402
from deerflow.compile.agent_workflow_schemas import (  # noqa: E402
    AgentBuildNodeInput,
    AgentWorkflowBudget,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowTargetContract,
)
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
DEFAULT_OUTPUT_DIR = Path(protocol.EVIDENCE_DIRECTORY)
DOCKER_SOCKET_ENDPOINT = "unix:///var/run/docker.sock"


class StageCV7AuthorizedRunnerError(RuntimeError):
    """授权 release、evidence、Provider 或运行终态无效。"""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageCV7AuthorizedRunnerError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise StageCV7AuthorizedRunnerError(f"JSON 根节点必须是对象: {path}")
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
        raise StageCV7AuthorizedRunnerError(f"不可覆盖已存在的 evidence: {path}") from exc


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def _run_checked(command: Sequence[str], failure: str, *, cwd: Path = REPO_ROOT) -> str:
    result = subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise StageCV7AuthorizedRunnerError(failure)
    return result.stdout.strip()


def _git(repo_root: Path, *arguments: str) -> str:
    return _run_checked(["git", "-c", f"safe.directory={repo_root}", *arguments], "无法验证授权 release Git identity", cwd=repo_root)


def _manifest_sha256(manifest: dict[str, Any]) -> str:
    return protocol.parent.canonical_sha256(manifest)


def _output_dir(manifest: dict[str, Any], output_dir: Path) -> Path:
    expected = Path(manifest["execution"]["evidence_directory"]).resolve(strict=False)
    if output_dir.resolve(strict=False) != expected:
        raise StageCV7AuthorizedRunnerError("evidence 必须写入冻结授权目录")
    return output_dir


def require_release_identity(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, str]:
    branch = _git(repo_root, "branch", "--show-current")
    revision = _git(repo_root, "rev-parse", "HEAD")
    origin_main = _git(repo_root, "rev-parse", "origin/main")
    dirty = _git(repo_root, "status", "--porcelain", "--untracked-files=normal")
    execution = manifest["execution"]
    if branch != execution["release_branch"] or revision != origin_main or dirty:
        raise StageCV7AuthorizedRunnerError("真实 canary 要求干净 main == origin/main")
    baseline = execution["authorization_baseline_commit"]
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", baseline, revision],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise StageCV7AuthorizedRunnerError("当前 release 不是授权基线的后代")
    return {"branch": branch, "revision": revision, "origin_main": origin_main}


def require_network_medium(manifest: dict[str, Any]) -> str:
    execution = manifest["execution"]
    name = execution["network_access_medium_env"]
    medium = os.environ.get(name)
    if medium != execution["network_access_medium"]:
        raise StageCV7AuthorizedRunnerError(f"必须通过 {name}={execution['network_access_medium']} 记录网络介质")
    return medium


def require_docker_identity(manifest: dict[str, Any]) -> dict[str, str]:
    _run_checked(["bash", str(REPO_ROOT / "scripts" / "require-docker-runtime.sh")], "Linux Docker runtime 不可用")
    expected = manifest["execution"]["docker"]
    context = _run_checked(["docker", "context", "show"], "无法读取 Docker context")
    endpoint = _run_checked(
        ["docker", "context", "inspect", context, "--format", "{{.Endpoints.docker.Host}}"],
        "无法读取 Docker endpoint",
    )
    if context != expected["context"] or endpoint != expected["endpoint"] or endpoint != DOCKER_SOCKET_ENDPOINT:
        raise StageCV7AuthorizedRunnerError("Docker context 或 endpoint 与授权 identity 不一致")
    image_id = _run_checked(
        ["docker", "image", "inspect", manifest["environment"]["compile_image"], "--format", "{{.Id}}"],
        "无法读取冻结编译镜像",
    )
    if image_id != manifest["environment"]["image_id"]:
        raise StageCV7AuthorizedRunnerError("Docker image ID 与授权 identity 不一致")
    return {"provider": expected["provider"], "context": context, "endpoint": endpoint, "image_id": image_id}


def require_zero_managed_resources() -> None:
    try:
        stage_c.require_zero_managed_resources()
    except (stage_c.StageCRunnerError, stage_b.Phase5V2AuthorizedRunnerError) as exc:
        raise StageCV7AuthorizedRunnerError(str(exc)) from exc


def _provider_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider_candidate": manifest["provider"],
        "environment_candidate": manifest["environment"],
        "budget_candidate": {"per_task": manifest["budget"]["per_attempt"]},
    }


def _provider_config_preflight(manifest: dict[str, Any]) -> None:
    stage_b._provider_config_preflight(_provider_manifest(manifest))


def _create_provider_model(manifest: dict[str, Any], thread_id: str | None = None) -> Any:
    return stage_b._create_provider_model(_provider_manifest(manifest), experiment_thread_id=thread_id)


def _task(manifest: dict[str, Any], task_id: str) -> dict[str, Any]:
    matches = [task for task in manifest["tasks"] if task["task_id"] == task_id]
    if len(matches) != 1:
        raise StageCV7AuthorizedRunnerError(f"未知或重复 task: {task_id}")
    return matches[0]


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


def _validate_all_node_inputs(manifest: dict[str, Any]) -> None:
    session = type("StageCV7ContractSession", (), {"session_id": "stage-c-v7-contract"})()
    for attempt in manifest["schedule"]["attempts"]:
        task = _task(manifest, attempt["task_id"])
        _node_input(manifest, task, session, attempt["attempt_id"]).validate()
        stage_c._oracle_spec(task).validate()
        thread_id = _thread_id(attempt, _manifest_sha256(manifest))
        CompileSessionManager._validate_session_components(thread_id, "stage-c-v7-contract")


def collect_preflight(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    require_empty: bool,
) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    _validate_all_node_inputs(manifest)
    _output_dir(manifest, output_dir)
    release = require_release_identity(manifest, repo_root)
    medium = require_network_medium(manifest)
    docker = require_docker_identity(manifest)
    require_zero_managed_resources()
    _provider_config_preflight(manifest)
    files = _evidence_files(output_dir)
    if require_empty and files:
        raise StageCV7AuthorizedRunnerError("reachability 前要求授权 evidence 目录为空")
    return {
        "ready": True,
        "manifest_sha256": _manifest_sha256(manifest),
        "parent_manifest_sha256": manifest["parent_candidate"]["canonical_sha256"],
        "release_revision": release["revision"],
        "network_access_medium": medium,
        "docker": docker,
        "credential_check": "environment_variable_presence_only",
        "evidence_files": files,
        "zero_managed_resources": True,
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
    }


def _claim_marker(path: Path, *, document_type: str, manifest_sha256: str, revision: str, attempt: dict[str, Any] | None = None) -> None:
    _write_once(
        path,
        {
            "schema_version": "forge-stage-c-v7-authorized-marker-1.0.0",
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
        raise StageCV7AuthorizedRunnerError("create-once marker 不处于 started")
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
    _claim_marker(marker_path, document_type="forge_stage_c_v7_reachability_attempt", manifest_sha256=digest, revision=preflight["release_revision"])
    started = time.perf_counter()
    try:
        response = model_factory(manifest, None).invoke(reachability["prompt"])
        response_text = stage_b._response_text(response).strip()
        actual_model, usage = stage_b.model_response_metadata(response)
        input_tokens = usage.get("prompt_tokens", usage.get("input_tokens", 0))
        output_tokens = usage.get("completion_tokens", usage.get("output_tokens", 0))
        total_tokens = usage.get("total_tokens")
        passed = response_text == reachability["expected_response"] and actual_model == manifest["provider"]["actual_model"] and all(type(value) is int and value >= 0 for value in (input_tokens, output_tokens, total_tokens))
        report = {
            "schema_version": "forge-stage-c-v7-authorized-reachability-1.0.0",
            "document_type": "forge_stage_c_v7_authorized_reachability",
            "manifest_sha256": digest,
            "release_revision": preflight["release_revision"],
            "provider": manifest["provider"]["provider"],
            "model": manifest["provider"]["profile"],
            "actual_model": actual_model,
            "endpoint": manifest["provider"]["endpoint"],
            "request_count": 1,
            "token_ledger": [{"request_sequence": 1, "input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total_tokens}],
            "recorded_tokens": total_tokens,
            "passed": passed,
            "response_sha256": hashlib.sha256(response_text.encode("utf-8")).hexdigest(),
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "completed_at": datetime.now(UTC).isoformat(),
        }
        _write_once(output_dir / reachability["report"], report)
        if not passed:
            raise StageCV7AuthorizedRunnerError("唯一 reachability 响应或 identity 无效")
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
        raise StageCV7AuthorizedRunnerError("唯一 reachability 未形成同 revision 通过终态")
    return report


def _thread_id(attempt: dict[str, Any], manifest_sha256: str) -> str:
    identity = hashlib.sha256(attempt["attempt_id"].encode("utf-8")).hexdigest()
    return f"stage-c-v7-b-{identity[:32]}-{manifest_sha256[:16]}"


def _bind_replay_source_archive(task: dict[str, Any], session: Any, manager: CompileSessionManager) -> None:
    repository = Path(session.leadagent_repo_dir)
    source_archive = Path(session.leadagent_repro_dir) / "source.tar"
    source_archive.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repository}", "-C", str(repository), "archive", "--format=tar", "--output", str(source_archive), "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise StageCV7AuthorizedRunnerError(f"{task['task_id']} 无法生成 replay source archive")
    observed = protocol.parent.file_sha256(source_archive)
    if observed != task["source_snapshot_sha256"]:
        raise StageCV7AuthorizedRunnerError(f"{task['task_id']} source snapshot identity 漂移")
    session.replay_source_archive_sha256 = observed
    manager.save_session(session)


def _experiment_policy(manifest: dict[str, Any], task: dict[str, Any], attempt: dict[str, Any]) -> ExperimentPolicy:
    budget = manifest["budget"]["per_attempt"]
    provider = manifest["provider"]
    return ExperimentPolicy(
        benchmark_id="forge-stage-c-v7-prefreeze-canary-authorized-v1",
        manifest_sha256=_manifest_sha256(manifest),
        case_id=attempt["canary_id"],
        condition="forge-agent-workflow-node-v3",
        repetition=1,
        expected_repo_url=task["repository_url"],
        expected_commit_sha=task["commit_sha"],
        expected_build_system=task["selected_build_system"],
        compile_image=manifest["environment"]["compile_image"],
        image_id=manifest["environment"]["image_id"],
        model_name=provider["profile"],
        endpoint=provider["endpoint"],
        credential_env=provider["credential_env_name"],
        request_timeout_seconds=provider["request_timeout_seconds"],
        model_max_retries=provider["model_max_retries"],
        compiler_max_turns=budget["max_model_requests"],
        subagent_timeout_seconds=budget["work_timeout_seconds"],
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=(),
        cmake_arguments=(),
        configure_arguments=(),
        environment=(),
        minimum_replay_delay_seconds=0,
        compiler_model_turn_limit=budget["max_model_requests"],
        compiler_graph_recursion_limit=budget["forge_max_agent_steps"],
        compiler_wall_clock_seconds=budget["work_timeout_seconds"],
        compiler_post_build_reserve_seconds=budget["cleanup_reserve_seconds"],
    )


@contextmanager
def _runtime_identity(manifest: dict[str, Any]):
    services = get_compile_services()
    manager = services.manager
    runtime = services.runtime
    original = (
        manager.default_image,
        manager.parallel_jobs,
        runtime.config.image,
        runtime.config.parallel_jobs,
        runtime.config.replay_timeout_seconds,
    )
    try:
        manager.default_image = manifest["environment"]["compile_image"]
        manager.parallel_jobs = manifest["environment"]["parallel_jobs"]
        runtime.config.image = manifest["environment"]["compile_image"]
        runtime.config.parallel_jobs = manifest["environment"]["parallel_jobs"]
        runtime.config.replay_timeout_seconds = manifest["budget"]["per_attempt"]["replay_timeout_seconds"]
        yield services
    finally:
        (
            manager.default_image,
            manager.parallel_jobs,
            runtime.config.image,
            runtime.config.parallel_jobs,
            runtime.config.replay_timeout_seconds,
        ) = original


def _node_input(manifest: dict[str, Any], task: dict[str, Any], session: Any, attempt_id: str) -> AgentBuildNodeInput:
    budget = manifest["budget"]["per_attempt"]
    target = task["target_contract"]
    compiled_types = tuple(item for item in target["artifact_types"] if item != "support_file")
    build_system_candidates = tuple(item for item in task["build_system_capabilities"] if item in {"cmake", "make", "autotools"})
    if not compiled_types:
        raise StageCV7AuthorizedRunnerError(f"{task['task_id']} 缺少可编译 target 类型")
    if task["selected_build_system"] not in build_system_candidates:
        raise StageCV7AuthorizedRunnerError(f"{task['task_id']} selected build system 不满足 Runtime v3 合同")
    return AgentBuildNodeInput(
        task_id=task["task_id"],
        attempt_id=attempt_id,
        session_id=session.session_id,
        repository_url=task["repository_url"],
        commit_sha=task["commit_sha"],
        source_snapshot_sha256=task["source_snapshot_sha256"],
        build_system_candidates=build_system_candidates,
        target_contract=AgentWorkflowTargetContract(
            target_id=target["target_id"],
            artifact_types=compiled_types,
            artifact_path_patterns=tuple(target["required_artifacts"]),
            functional_oracle_ref=f"stage-c-{task['task_id']}-oracle-v1",
        ),
        operation_policy_ref="stage-c-v7-prefreeze-shared-operation-policy-v1",
        environment=AgentWorkflowEnvironmentIdentity(
            image_id=manifest["environment"]["image_id"],
            parallel_jobs=manifest["environment"]["parallel_jobs"],
            network_policy="clone_then_network_none",
        ),
        budget=AgentWorkflowBudget(
            max_model_requests=budget["max_model_requests"],
            max_recorded_tokens=None,
            max_agent_steps=budget["forge_max_agent_steps"],
            max_tool_calls=budget["forge_max_tool_calls"],
            max_commands=budget["forge_max_commands"],
            node_timeout_seconds=budget["work_timeout_seconds"],
            command_timeout_seconds=budget["command_timeout_seconds"],
            evaluator_timeout_seconds=budget["evaluator_timeout_seconds"],
            replay_timeout_seconds=budget["replay_timeout_seconds"],
            cleanup_timeout_seconds=budget["cleanup_reserve_seconds"],
        ),
        experiment_identity=AgentWorkflowExperimentIdentity(
            manifest_sha256=_manifest_sha256(manifest),
            protocol_sha256=manifest["frozen_authorized_components"][protocol.PROTOCOL_PATH],
            runner_sha256=manifest["frozen_authorized_components"][protocol.RUNNER_PATH],
        ),
        initial_observation={
            "required_candidate_artifacts": tuple(target["required_artifacts"]),
            "build_system_capabilities": tuple(task["build_system_capabilities"]),
            "selected_build_system": task["selected_build_system"],
            "qualification_receipt_sha256": task["qualification_receipt"]["receipt_sha256"],
            "prefreeze_feedback_enabled": True,
            "network_after_clone": "none",
        },
    )


def _event_observations(events_path: Path) -> dict[str, Any]:
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    token_ledger = []
    rejected = []
    accepted_sequence: int | None = None
    for sequence, event in enumerate(events, 1):
        payload = event.get("payload", {})
        if event.get("event_type") == "model.request_completed":
            token_ledger.append(
                {
                    "request_sequence": payload.get("request_sequence"),
                    "input_tokens": payload.get("input_tokens"),
                    "output_tokens": payload.get("output_tokens"),
                    "total_tokens": payload.get("recorded_tokens"),
                }
            )
        elif event.get("event_type") == "candidate.submit_rejected":
            rejected.append(
                {
                    "event_sequence": sequence,
                    "codes": list(payload.get("rejection_codes", [])),
                    "evidence_count": len(payload.get("rejection_details", [])),
                }
            )
        elif event.get("event_type") == "candidate.submit_accepted":
            accepted_sequence = sequence
    if any(type(entry[field]) is not int or entry[field] < 0 for entry in token_ledger for field in ("request_sequence", "input_tokens", "output_tokens", "total_tokens")):
        raise StageCV7AuthorizedRunnerError("逐请求 token ledger 无效")
    submit_attempts = len(rejected) + int(accepted_sequence is not None)
    return {
        "token_ledger": token_ledger,
        "submit_attempts": submit_attempts,
        "rejection_codes": sorted({code for item in rejected for code in item["codes"]}),
        "rejection_evidence_count": sum(item["evidence_count"] for item in rejected),
        "same_attempt_repair_observed": bool(rejected and accepted_sequence is not None and rejected[-1]["event_sequence"] < accepted_sequence),
    }


async def execute_attempt(
    manifest: dict[str, Any],
    attempt: dict[str, Any],
    *,
    release_revision: str,
    output_dir: Path,
    model_factory: Callable[[dict[str, Any], str | None], Any] = _create_provider_model,
) -> dict[str, Any]:
    task = _task(manifest, attempt["task_id"])
    digest = _manifest_sha256(manifest)
    marker_path, result_path, ledger_path = _attempt_paths(manifest, output_dir, attempt)
    _claim_marker(marker_path, document_type="forge_stage_c_v7_canary_attempt", manifest_sha256=digest, revision=release_revision, attempt=attempt)
    ledger = ExperimentLedger.create(
        ledger_path,
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"manifest_sha256": digest, "release_revision": release_revision, "task_id": task["task_id"], "attempt_id": attempt["attempt_id"]},
    )
    thread_id = _thread_id(attempt, digest)
    session = None
    finalized = None
    cleanup = None
    active = False
    node_result = None
    evaluation = None
    error_class = None
    error_message_sha256 = None
    events_path = None
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
        with _runtime_identity(manifest) as services:
            session = prepare_compile_session_impl(
                thread_id=thread_id,
                repo_url=task["repository_url"],
                run_id=f"stage-c-v7-{task['task_id']}-{uuid.uuid4().hex}",
                task_description=f"Stage C v7 pre-freeze verifier canary: {task['task_id']}",
            )
            clone, _message = clone_repository_impl(
                session=session,
                repo_url=task["repository_url"],
                commit_sha=task["commit_sha"],
                depth=1,
                max_retries=1,
            )
            if clone.exit_code != 0 or session.commit_sha != task["commit_sha"]:
                raise StageCV7AuthorizedRunnerError(f"{task['task_id']} 无法检出冻结 commit")
            _bind_replay_source_archive(task, session, services.manager)
            primary, _detected, _suggested = inspect_build_system_impl(session=session)
            if primary not in task["build_system_capabilities"]:
                raise StageCV7AuthorizedRunnerError(f"{task['task_id']} build-system identity 漂移")
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
    except BaseException as exc:
        error_class = type(exc).__name__
        error_message_sha256 = hashlib.sha256(str(exc).encode("utf-8", errors="replace")).hexdigest()
    finally:
        if active:
            deactivate_experiment(thread_id)
            active = False
        if session is not None:
            try:
                finalized, cleanup = cleanup_and_finalize_compile_session_impl(session=session)
            except BaseException as cleanup_exc:
                _finish_marker(marker_path, status="failed", error_class=type(cleanup_exc).__name__)
                raise
        try:
            require_zero_managed_resources()
        except BaseException as resource_exc:
            _finish_marker(marker_path, status="failed", error_class=type(resource_exc).__name__)
            raise
    cleanup_succeeded = session is None or bool(cleanup and cleanup.succeeded and finalized and finalized.finalized_at is not None)
    if not cleanup_succeeded:
        _finish_marker(marker_path, status="failed", error_class="CleanupIncomplete")
        raise StageCV7AuthorizedRunnerError(f"{attempt['attempt_id']} cleanup 未闭合")
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
        raise StageCV7AuthorizedRunnerError("逐请求 token ledger 与 Runtime v3 usage 不一致")
    layers = [asdict(layer) for layer in evaluation.layers] if evaluation is not None else []
    strict_success = bool(evaluation and evaluation.strict_reproducible_build_success)
    result = {
        "schema_version": "forge-stage-c-v7-authorized-attempt-result-1.0.0",
        "document_type": "forge_stage_c_v7_authorized_attempt_result",
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
        "candidate_record_sha256": node_result.candidate_record_sha256 if node_result else None,
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
        "bitwise_reproducible": evaluation.bitwise_reproducible if evaluation is not None else None,
        "evaluation_sha256": evaluation.canonical_sha256() if evaluation is not None else None,
        "cleanup_succeeded": True,
        "zero_managed_resources": True,
        "canary_passed": strict_success and error_class is None,
        "error_class": error_class,
        "error_message_sha256": error_message_sha256,
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "completed_at": datetime.now(UTC).isoformat(),
    }
    _write_once(result_path, result)
    ledger.append("experiment.completed", {"status": "passed" if result["canary_passed"] else "failed", "result_sha256": protocol.parent.file_sha256(result_path)})
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
            raise StageCV7AuthorizedRunnerError("attempt evidence 不是完整连续前缀")
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
            raise StageCV7AuthorizedRunnerError(f"attempt evidence 未闭合: {attempt['attempt_id']}")
        completed.append(result)
        if index != len(completed) - 1:
            raise StageCV7AuthorizedRunnerError("attempt 顺序发生漂移")
    return completed, len(completed)


def _summarize(manifest: dict[str, Any], revision: str, reachability: dict[str, Any], outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    stopped = next((item for item in outcomes if not item["canary_passed"]), None)
    layers = {name: sum(any(layer["layer"] == name and layer["status"] == "passed" for layer in item["s0_s5"]) for item in outcomes) for name in ("S0", "S1", "S2", "S3", "S4", "S5")}
    return {
        "schema_version": "forge-stage-c-v7-authorized-canary-report-1.0.0",
        "document_type": "forge_stage_c_v7_authorized_canary_report",
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
        "attempt_recorded_tokens": sum(item["recorded_tokens"] for item in outcomes),
        "total_recorded_tokens": reachability["recorded_tokens"] + sum(item["recorded_tokens"] for item in outcomes),
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
            raise StageCV7AuthorizedRunnerError("batch marker 无法恢复")
    else:
        if completed:
            raise StageCV7AuthorizedRunnerError("缺少 create-once batch marker，拒绝导入既有 attempt evidence")
        _claim_marker(marker_path, document_type="forge_stage_c_v7_canary_batch", manifest_sha256=digest, revision=revision)
    try:
        if not completed or completed[-1]["canary_passed"]:
            for attempt in manifest["schedule"]["attempts"][next_index:]:
                outcome = attempt_executor(manifest, attempt, release_revision=revision, output_dir=output_dir)
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
    _finish_marker(marker_path, status="stopped" if report["status"] == "stopped_on_first_failure" else "passed")
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
        raise StageCV7AuthorizedRunnerError("Stage C v7 canary report identity 发生漂移")
    return report


def validate_runtime(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    _validate_all_node_inputs(manifest)
    return {
        "status": "valid",
        "manifest_sha256": _manifest_sha256(manifest),
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
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest(args.manifest)
    if args.command == "validate":
        result: Any = validate_runtime(manifest)
    elif args.command == "preflight":
        result = collect_preflight(manifest, output_dir=args.output_dir, require_empty=not args.output_dir.exists())
    elif args.command == "reachability":
        result = execute_reachability(manifest, output_dir=args.output_dir)
    elif args.command == "run":
        result = run_batch(manifest, output_dir=args.output_dir)
    else:
        result = load_report(manifest, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
