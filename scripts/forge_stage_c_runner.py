#!/usr/bin/env python3
"""Stage C 配对校准 runner；validate/preflight 不启动正式实验。"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_agent_workflow_stage_b_phase5_v2_authorized_runner as stage_b  # noqa: E402
import forge_stage_c_controlled_baseline as controlled  # noqa: E402
import forge_stage_c_task_qualification as qualification  # noqa: E402
import forge_stage_c_v5_protocol as protocol  # noqa: E402

from deerflow.compile.agent_workflow_runtime_v2 import (  # noqa: E402
    run_agent_workflow_node_v2,
)
from deerflow.compile.agent_workflow_schemas import (  # noqa: E402
    AgentBuildNodeInput,
    AgentWorkflowBudget,
    AgentWorkflowContractError,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowTargetContract,
)
from deerflow.compile.evidence import (  # noqa: E402
    EvidenceError,
    ExperimentLedger,
    ExperimentPolicy,
    activate_experiment,
    deactivate_experiment,
    new_evidence_id,
    record_experiment_event,
)
from deerflow.compile.external_evaluator_v4 import (  # noqa: E402
    ExternalEvaluatorIdentityError,
    ForgeCompileEvaluationBackend,
    run_external_evaluator_v4,
)
from deerflow.compile.manager import CompileSessionManager  # noqa: E402
from deerflow.compile.operations import (  # noqa: E402
    cleanup_and_finalize_compile_session_impl,
    get_compile_services,
    inspect_build_system_impl,
)

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_OUTPUT_DIR = Path(protocol.DEFAULT_EVIDENCE_DIRECTORY)
MANAGED_A_PREFIX = "forge-stage-c-arm-a-"
_BUILD_SYSTEM_MARKERS = {
    "cmake": ("CMakeLists.txt",),
    "make": ("Makefile", "GNUmakefile", "makefile"),
    "autotools": ("configure", "configure.ac", "configure.in", "autogen.sh"),
}


class StageCRunnerError(RuntimeError):
    """Stage C release、evidence、隔离、预算或运行终态无效。"""


def _load_json(path: Path) -> dict[str, Any]:
    return qualification.load_json(path)


def _write_once(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _run(
    argv: list[str],
    *,
    cwd: Path = REPO_ROOT,
    timeout: int = 120,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-4000:]
        raise StageCRunnerError(
            f"命令失败 ({result.returncode}): {shlex.join(argv)}\n{detail}"
        )
    return result


def require_zero_managed_resources() -> None:
    stage_b.require_zero_managed_resources()
    output = _run(["docker", "ps", "-a", "--format", "{{.Names}}"])
    names = sorted(
        name
        for name in output.stdout.splitlines()
        if name.startswith(MANAGED_A_PREFIX)
        or name.startswith(qualification.MANAGED_PREFIX)
    )
    if names:
        raise StageCRunnerError(f"存在 Stage C managed orphan: {','.join(names)}")
    images = _run(
        [
            "docker",
            "images",
            "-q",
            "--filter",
            "label=forge.stage-c.managed=true",
        ]
    ).stdout.strip()
    if images:
        raise StageCRunnerError("存在 Stage C managed image")


def _compatibility_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    budget = manifest["budget"]["per_arm"]
    return {
        "provider_candidate": manifest["provider"],
        "environment_candidate": {
            "compile_image": manifest["environment"]["compile_image"],
            "image_id": manifest["environment"]["image_id"],
            "network_policy": "stage-c-frozen-image-clone-then-none-v1",
            "parallel_jobs": manifest["environment"]["parallel_jobs"],
        },
        "budget_candidate": {
            "per_task": {
                "max_recorded_tokens": budget["max_recorded_tokens"],
                "max_model_requests": budget["max_model_requests"],
                "node_timeout_seconds": budget["work_timeout_seconds"],
                "cleanup_timeout_seconds": budget["cleanup_reserve_seconds"],
                "command_timeout_seconds": budget["command_timeout_seconds"],
                "evaluator_timeout_seconds": budget["evaluator_timeout_seconds"],
                "replay_timeout_seconds": budget["replay_timeout_seconds"],
                "max_agent_steps": budget["forge_max_agent_steps"],
                "max_tool_calls": budget["forge_max_tool_calls"],
                "max_commands": budget["forge_max_commands"],
            }
        },
        "operation_policy_ref": "stage-c-shared-operation-policy-v1",
        "qualification": {
            "result_sha256": manifest["qualification"]["result_file_sha256"]
        },
        "frozen_authorized_components": manifest["frozen_components"],
    }


def _release_identity(manifest: dict[str, Any]) -> str:
    revision = protocol.release_revision()
    branch = _run(["git", "branch", "--show-current"]).stdout.strip()
    origin_main = _run(["git", "rev-parse", "origin/main"]).stdout.strip()
    status = _run(["git", "status", "--porcelain"], check=True).stdout.strip()
    if (
        branch != manifest["execution"]["release_branch"]
        or revision != origin_main
        or status
    ):
        raise StageCRunnerError("Stage C 只能从干净 main == origin/main 执行")
    return revision


def _provider_preflight(manifest: dict[str, Any]) -> None:
    stage_b._provider_config_preflight(_compatibility_manifest(manifest))


def _recorded_evidence_state(output_dir: Path) -> dict[str, Any]:
    pair_root = output_dir / "pairs"
    pair_dirs = (
        sorted(path for path in pair_root.iterdir() if path.is_dir())
        if pair_root.is_dir()
        else []
    )
    incomplete_pairs = [
        path.name for path in pair_dirs if not (path / "pair.json").is_file()
    ]
    attempt_markers = (
        sorted(pair_root.glob("*/*/attempt.json")) if pair_root.is_dir() else []
    )
    provider_calls = 0
    model_tokens = 0
    reachability = output_dir / "reports/reachability.json"
    if reachability.is_file():
        value = _load_json(reachability)
        requests = value.get("request_count")
        tokens = value.get("recorded_tokens")
        if (
            type(requests) is not int
            or requests < 0
            or type(tokens) is not int
            or tokens < 0
        ):
            raise StageCRunnerError("reachability usage evidence 无效")
        provider_calls += requests
        model_tokens += tokens
    for result_path in (
        sorted(pair_root.glob("*/*/result.json")) if pair_root.is_dir() else []
    ):
        value = _load_json(result_path)
        requests = value.get("model_requests")
        tokens = value.get("recorded_tokens")
        if (
            type(requests) is not int
            or requests < 0
            or type(tokens) is not int
            or tokens < 0
        ):
            raise StageCRunnerError(f"arm usage evidence 无效: {result_path}")
        provider_calls += requests
        model_tokens += tokens
    return {
        "formal_stage_c_attempts": len(attempt_markers),
        "incomplete_pairs": incomplete_pairs,
        "provider_calls": provider_calls,
        "model_tokens": model_tokens,
    }


def collect_preflight(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    require_empty: bool,
) -> dict[str, Any]:
    protocol.validate_manifest(manifest)
    _validate_all_node_inputs(manifest)
    revision = _release_identity(manifest)
    if output_dir != Path(manifest["execution"]["evidence_directory"]):
        raise StageCRunnerError("Stage C evidence directory 与 manifest 不一致")
    expected_medium = manifest["execution"]["network_access_medium"]
    medium_env = manifest["execution"]["network_access_medium_env"]
    if os.environ.get(medium_env) != expected_medium:
        raise StageCRunnerError("Stage C network access medium 未按 manifest 声明")
    actual_image_id = _run(
        [
            "docker",
            "image",
            "inspect",
            manifest["environment"]["compile_image"],
            "--format",
            "{{.Id}}",
        ]
    ).stdout.strip()
    if actual_image_id != manifest["environment"]["image_id"]:
        raise StageCRunnerError("Stage C image ID 发生漂移")
    require_zero_managed_resources()
    _provider_preflight(manifest)
    files = (
        sorted(
            path.relative_to(output_dir).as_posix()
            for path in output_dir.rglob("*")
            if path.is_file()
        )
        if output_dir.exists()
        else []
    )
    if require_empty and files:
        raise StageCRunnerError("reachability 前要求 Stage C evidence 目录为空")
    evidence_state = _recorded_evidence_state(output_dir)
    return {
        "ready": not evidence_state["incomplete_pairs"],
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "release_revision": revision,
        "image_id": actual_image_id,
        "network_access_medium": expected_medium,
        "credential_check": "environment_variable_presence_only",
        "evidence_files": files,
        "zero_managed_resources": True,
        **evidence_state,
    }


def _model(manifest: dict[str, Any], thread_id: str | None = None) -> Any:
    return stage_b._create_provider_model(
        _compatibility_manifest(manifest), experiment_thread_id=thread_id
    )


def execute_reachability(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    model_factory: Callable[[dict[str, Any], str | None], Any] = _model,
) -> dict[str, Any]:
    preflight = collect_preflight(manifest, output_dir=output_dir, require_empty=True)
    marker = output_dir / manifest["execution"]["reachability_marker"]
    report_path = output_dir / manifest["execution"]["reachability_report"]
    digest = protocol.canonical_sha256(manifest)
    _write_once(
        marker,
        {
            "schema_version": "forge-stage-c-reachability-marker-1.0.0",
            "manifest_sha256": digest,
            "release_revision": preflight["release_revision"],
            "status": "started",
        },
    )
    started = time.perf_counter()
    try:
        response = model_factory(manifest, None).invoke(
            "Reply with exactly STAGE_C_CANARY_OK and nothing else."
        )
        text = stage_b._response_text(response).strip()
        actual_model, usage = stage_b.model_response_metadata(response)
        tokens = usage.get("total_tokens")
        passed = (
            text == "STAGE_C_CANARY_OK"
            and actual_model == manifest["provider"]["actual_model"]
            and type(tokens) is int
            and 0 <= tokens <= manifest["budget"]["reachability_max_recorded_tokens"]
        )
        report = {
            "schema_version": "forge-stage-c-reachability-1.0.0",
            "document_type": "forge_stage_c_reachability",
            "manifest_sha256": digest,
            "release_revision": preflight["release_revision"],
            "provider": manifest["provider"]["provider"],
            "model": manifest["provider"]["profile"],
            "actual_model": actual_model,
            "endpoint": manifest["provider"]["endpoint"],
            "request_count": 1,
            "recorded_tokens": tokens,
            "passed": passed,
            "response_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "completed_at": datetime.now(UTC).isoformat(),
        }
        _write_once(report_path, report)
        if not passed:
            raise StageCRunnerError("Stage C 唯一 reachability 未通过")
        marker_value = _load_json(marker)
        marker_value["status"] = "passed"
        marker.write_text(
            json.dumps(marker_value, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        return report
    except BaseException:
        marker_value = _load_json(marker)
        marker_value["status"] = "failed"
        marker.write_text(
            json.dumps(marker_value, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        raise


def _require_reachability(
    manifest: dict[str, Any], output_dir: Path, revision: str
) -> dict[str, Any]:
    marker = _load_json(output_dir / manifest["execution"]["reachability_marker"])
    report = _load_json(output_dir / manifest["execution"]["reachability_report"])
    digest = protocol.canonical_sha256(manifest)
    if (
        marker.get("status") != "passed"
        or marker.get("manifest_sha256") != digest
        or marker.get("release_revision") != revision
        or report.get("passed") is not True
        or report.get("manifest_sha256") != digest
        or report.get("release_revision") != revision
        or report.get("request_count") != 1
    ):
        raise StageCRunnerError("Stage C reachability 未形成同 release 通过终态")
    return report


def _task(manifest: dict[str, Any], task_id: str) -> dict[str, Any]:
    matches = [task for task in manifest["tasks"] if task["task_id"] == task_id]
    if len(matches) != 1:
        raise StageCRunnerError(f"未知或重复 task: {task_id}")
    return matches[0]


def _oracle_spec(task: dict[str, Any]) -> Any:
    compatible = {
        **task,
        "required_candidate_artifacts": task["target_contract"]["required_artifacts"],
        "target_contract": {
            "target_id": task["target_contract"]["target_id"],
            "artifact_types": task["target_contract"]["artifact_types"],
            "artifact_path_patterns": task["target_contract"]["required_artifacts"],
            "functional_oracle_ref": f"stage-c-{task['task_id']}-oracle-v1",
        },
    }
    return stage_b._oracle_spec(compatible)


def _forge_policy(
    manifest: dict[str, Any], task: dict[str, Any], pair: dict[str, Any]
) -> ExperimentPolicy:
    budget = manifest["budget"]["per_arm"]
    provider = manifest["provider"]
    return ExperimentPolicy(
        benchmark_id="forge-stage-c-paired-calibration-v1",
        manifest_sha256=protocol.canonical_sha256(manifest),
        case_id=pair["pair_id"],
        condition="forge-agent-workflow-node-v2",
        repetition=pair["replicate"],
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


def _node_input(
    manifest: dict[str, Any],
    task: dict[str, Any],
    session: Any,
    attempt_id: str,
) -> AgentBuildNodeInput:
    budget = manifest["budget"]["per_arm"]
    target = task["target_contract"]
    compiled_types = tuple(
        artifact_type
        for artifact_type in target["artifact_types"]
        if artifact_type != "support_file"
    )
    if not compiled_types:
        raise StageCRunnerError(f"{task['task_id']} 缺少可编译 target 类型")
    frozen = manifest["frozen_components"]
    build_system_candidates = tuple(
        build_system
        for build_system in task["build_system_capabilities"]
        if build_system in _BUILD_SYSTEM_MARKERS
    )
    if task["selected_build_system"] not in build_system_candidates:
        raise StageCRunnerError(
            f"{task['task_id']} selected build system 不满足 Agent 合同"
        )
    return AgentBuildNodeInput(
        task_id=task["task_id"],
        attempt_id=attempt_id,
        session_id=session.session_id,
        repository_url=task["repository_url"],
        commit_sha=task["commit_sha"],
        build_system_candidates=build_system_candidates,
        target_contract=AgentWorkflowTargetContract(
            target_id=target["target_id"],
            artifact_types=compiled_types,
            artifact_path_patterns=tuple(target["required_artifacts"]),
            functional_oracle_ref=f"stage-c-{task['task_id']}-oracle-v1",
        ),
        operation_policy_ref="stage-c-shared-operation-policy-v1",
        environment=AgentWorkflowEnvironmentIdentity(
            image_id=manifest["environment"]["image_id"],
            network_policy="clone_then_network_none",
            parallel_jobs=manifest["environment"]["parallel_jobs"],
        ),
        budget=AgentWorkflowBudget(
            max_model_requests=budget["max_model_requests"],
            max_recorded_tokens=budget["max_recorded_tokens"],
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
            manifest_sha256=protocol.canonical_sha256(manifest),
            protocol_sha256=frozen[protocol.PROTOCOL_PATH],
            runner_sha256=frozen[protocol.RUNNER_PATH],
        ),
        source_snapshot_sha256=task["source_snapshot_sha256"],
        initial_observation={
            "required_candidate_artifacts": tuple(target["required_artifacts"]),
            "build_system_capabilities": tuple(task["build_system_capabilities"]),
            "selected_build_system": task["selected_build_system"],
            "qualification_receipt_sha256": task["qualification_receipt"][
                "receipt_sha256"
            ],
            "network_after_clone": "none",
        },
    )


def _validate_all_node_inputs(manifest: dict[str, Any]) -> None:
    session = type("StageCContractSession", (), {"session_id": "stage-c-contract"})()
    for task in manifest["tasks"]:
        try:
            _node_input(
                manifest,
                task,
                session,
                f"stage-c-contract-{task['task_id']}",
            ).validate()
        except AgentWorkflowContractError as exc:
            raise StageCRunnerError(
                f"{task['task_id']} Agent input contract 无效: {exc}"
            ) from exc

    digest = protocol.canonical_sha256(manifest)
    thread_ids = [
        _forge_thread_id(pair, digest) for pair in manifest["schedule"]["pairs"]
    ]
    if len(thread_ids) != len(set(thread_ids)):
        raise StageCRunnerError("Stage C Forge thread identity 不唯一")
    for pair, thread_id in zip(manifest["schedule"]["pairs"], thread_ids, strict=True):
        try:
            CompileSessionManager._validate_session_components(
                thread_id, "stage-c-contract"
            )
        except ValueError as exc:
            raise StageCRunnerError(
                f"{pair['pair_id']} Forge thread identity 无效: {exc}"
            ) from exc


def _forge_thread_id(pair: dict[str, Any], manifest_sha256: str) -> str:
    pair_digest = hashlib.sha256(pair["pair_id"].encode("utf-8")).hexdigest()
    return f"stage-c-b-{pair_digest}-{manifest_sha256[:16]}"


@contextmanager
def _offline_runtime(session: Any):
    services = get_compile_services()
    original_network = services.runtime.config.network
    try:
        if session.container_id:
            _run(
                [
                    "docker",
                    "network",
                    "disconnect",
                    original_network,
                    session.container_id,
                ]
            )
        services.runtime.config.network = "none"
        yield services
    finally:
        services.runtime.config.network = original_network


@contextmanager
def _stage_c_runtime_identity(manifest: dict[str, Any]):
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
        runtime.config.replay_timeout_seconds = manifest["budget"]["per_arm"][
            "replay_timeout_seconds"
        ]
        yield services
    finally:
        (
            manager.default_image,
            manager.parallel_jobs,
            runtime.config.image,
            runtime.config.parallel_jobs,
            runtime.config.replay_timeout_seconds,
        ) = original


def _register_arm_attempt(
    manifest: dict[str, Any],
    pair: dict[str, Any],
    arm: str,
    *,
    release_revision: str,
    arm_dir: Path,
    source_snapshot_sha256: str,
) -> dict[str, Any]:
    marker = {
        "schema_version": "forge-stage-c-arm-attempt-1.0.0",
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "release_revision": release_revision,
        "pair_id": pair["pair_id"],
        "task_id": pair["task_id"],
        "replicate": pair["replicate"],
        "arm": arm,
        "attempt_id": pair["attempt_ids"][arm],
        "source_snapshot_sha256": source_snapshot_sha256,
        "status": "started",
        "registered_at": datetime.now(UTC).isoformat(),
    }
    _write_once(arm_dir / "attempt.json", marker)
    return marker


def _validate_attempt_marker(
    manifest: dict[str, Any], pair: dict[str, Any], arm: str, arm_dir: Path
) -> None:
    value = _load_json(arm_dir / "attempt.json")
    task = _task(manifest, pair["task_id"])
    if (
        value.get("schema_version") != "forge-stage-c-arm-attempt-1.0.0"
        or value.get("manifest_sha256") != protocol.canonical_sha256(manifest)
        or value.get("pair_id") != pair["pair_id"]
        or value.get("task_id") != pair["task_id"]
        or value.get("replicate") != pair["replicate"]
        or value.get("arm") != arm
        or value.get("attempt_id") != pair["attempt_ids"][arm]
        or value.get("source_snapshot_sha256") != task["source_snapshot_sha256"]
        or value.get("status") != "started"
    ):
        raise StageCRunnerError(f"{pair['pair_id']} arm {arm} attempt marker 无效")


def _validate_prepared_source(
    task: dict[str, Any], source_identity: dict[str, Any]
) -> str:
    if source_identity["source_snapshot_sha256"] != task["source_snapshot_sha256"]:
        raise StageCRunnerError(f"{task['task_id']} source snapshot 漂移")
    source = source_identity["source"]
    detected: dict[str, str] = {}
    for build_system, markers in _BUILD_SYSTEM_MARKERS.items():
        marker = next(
            (candidate for candidate in markers if (source / candidate).is_file()),
            None,
        )
        if marker is not None:
            detected[build_system] = marker
    if not detected:
        for build_system, markers in _BUILD_SYSTEM_MARKERS.items():
            candidates = sorted(
                path.relative_to(source).as_posix()
                for child in source.iterdir()
                if child.is_dir()
                for marker in markers
                if (path := child / marker).is_file()
            )
            if candidates:
                detected[build_system] = candidates[0]
    selected = task["selected_build_system"]
    if selected not in detected:
        raise StageCRunnerError(f"{task['task_id']} build-system identity 漂移")
    source_identity["build_system_marker"] = detected[selected]
    return selected


def _prepare_forge_session(
    task: dict[str, Any],
    pair: dict[str, Any],
    thread_id: str,
    services: Any,
    source_identity: dict[str, Any],
) -> tuple[Any, str]:
    _validate_prepared_source(task, source_identity)
    session = services.manager.create_session(
        thread_id=thread_id,
        repo_url=task["repository_url"],
        run_id=f"stage-c-{pair['pair_id']}-b-{uuid.uuid4().hex}",
        session_id=uuid.uuid4().hex[:12],
    )
    try:
        shutil.copytree(source_identity["repository"], Path(session.leadagent_repo_dir))
        session.commit_sha = task["commit_sha"]
        session.summary = f"Stage C arm B: {pair['pair_id']}"
        services.manager.save_session(session)
        services.manager.log_event(
            session,
            "source.prepared",
            repo_url=task["repository_url"],
            commit_sha=task["commit_sha"],
            source_snapshot_sha256=source_identity["source_snapshot_sha256"],
            preparation_boundary="before_first_pair_arm_attempt",
        )
        services.manager.mark_session_status(session, "source_ready")
    except BaseException as exc:
        services.manager.mark_session_status(session, "failed", error=str(exc))
        raise
    return session, source_identity["source_snapshot_sha256"]


async def execute_forge_arm(
    manifest: dict[str, Any],
    task: dict[str, Any],
    pair: dict[str, Any],
    *,
    release_revision: str,
    arm_dir: Path,
    source_identity: dict[str, Any],
    model_factory: Callable[[dict[str, Any], str | None], Any] = _model,
) -> dict[str, Any]:
    attempt_id = pair["attempt_ids"]["B"]
    digest = protocol.canonical_sha256(manifest)
    thread_id = _forge_thread_id(pair, digest)
    ledger = None
    session = None
    active = False
    attempt_registered = False
    started = time.perf_counter()
    evaluation = None
    node_result = None
    cleanup_succeeded = False
    error_class = None
    try:
        with _stage_c_runtime_identity(manifest) as services:
            session, observed_source = _prepare_forge_session(
                task, pair, thread_id, services, source_identity
            )
            _register_arm_attempt(
                manifest,
                pair,
                "B",
                release_revision=release_revision,
                arm_dir=arm_dir,
                source_snapshot_sha256=observed_source,
            )
            attempt_registered = True
            ledger = ExperimentLedger.create(
                arm_dir / "experiment.jsonl",
                experiment_id=new_evidence_id("experiment"),
                physical_attempt_id=new_evidence_id("physical_attempt"),
                context={
                    "manifest_sha256": digest,
                    "release_revision": release_revision,
                    "pair_id": pair["pair_id"],
                    "arm": "B",
                    "source_snapshot_sha256": observed_source,
                },
            )
            activate_experiment(
                thread_id=thread_id,
                experiment_id=ledger.experiment_id,
                physical_attempt_id=ledger.physical_attempt_id,
                ledger=ledger,
                policy=_forge_policy(manifest, task, pair),
            )
            active = True
            services.runtime.create_container(session)
            if session.image_id != manifest["environment"]["image_id"]:
                raise StageCRunnerError(f"{pair['pair_id']} arm B image identity 漂移")
            services.manager.save_session(session)
            record_experiment_event(
                thread_id,
                "session.bound",
                session_id=session.session_id,
                repo_url=session.repo_url,
                image=session.image,
                image_id=session.image_id,
                source_snapshot_sha256=observed_source,
            )
            safe_directory = services.runtime.exec(
                session,
                "git config --global --replace-all safe.directory /workspace/repo",
                workdir="/workspace",
                timeout_seconds=30,
            )
            if safe_directory.exit_code != 0:
                raise StageCRunnerError(
                    f"{pair['pair_id']} arm B Git safe.directory 配置失败"
                )
            primary, _detected, _suggested = inspect_build_system_impl(session=session)
            if primary not in task["build_system_capabilities"]:
                raise StageCRunnerError(f"{task['task_id']} build-system identity 漂移")
            session.selected_build_system = task["selected_build_system"]
            services.manager.save_session(session)
            node_input = _node_input(manifest, task, session, attempt_id)
            with _offline_runtime(session) as offline_services:
                node_result = await run_agent_workflow_node_v2(
                    node_input=node_input,
                    session=session,
                    manager=offline_services.manager,
                    model=model_factory(manifest, thread_id),
                )
                if node_result.candidate_submitted:
                    evaluation = run_external_evaluator_v4(
                        node_input=node_input,
                        node_result=node_result,
                        session=session,
                        manager=offline_services.manager,
                        candidate_path=stage_b._candidate_path(session, attempt_id),
                        evaluation_id=f"{pair['pair_id']}-b-evaluation-v4",
                        backend=ForgeCompileEvaluationBackend(
                            oracle_registry={
                                f"stage-c-{task['task_id']}-oracle-v1": _oracle_spec(
                                    task
                                )
                            }
                        ),
                    )
    except (EvidenceError, ExternalEvaluatorIdentityError, StageCRunnerError):
        raise
    except Exception as exc:
        if not attempt_registered:
            raise
        error_class = type(exc).__name__
    finally:
        if active:
            deactivate_experiment(thread_id)
            active = False
        if session is not None:
            finalized, cleanup = cleanup_and_finalize_compile_session_impl(
                session=session
            )
            cleanup_succeeded = cleanup.succeeded and finalized.finalized_at is not None
        require_zero_managed_resources()
    if not cleanup_succeeded:
        raise StageCRunnerError(f"{pair['pair_id']} arm B cleanup 未闭合")
    layers = [asdict(layer) for layer in evaluation.layers] if evaluation else []
    usage = node_result.usage if node_result is not None else None
    result = {
        "schema_version": "forge-stage-c-arm-result-1.0.0",
        "manifest_sha256": digest,
        "release_revision": release_revision,
        "pair_id": pair["pair_id"],
        "task_id": task["task_id"],
        "replicate": pair["replicate"],
        "arm": "B",
        "method": "forge-agent-workflow-node-v2",
        "attempt_id": attempt_id,
        "candidate_generated": bool(
            node_result and node_result.candidate_generated_observed
        ),
        "candidate_submitted": bool(node_result and node_result.candidate_submitted),
        "s0_s5": layers,
        "strict_reproducible_build_success": bool(
            evaluation and evaluation.strict_reproducible_build_success
        ),
        "bitwise_reproducible": (
            evaluation.bitwise_reproducible if evaluation is not None else None
        ),
        "recorded_tokens": usage.recorded_tokens if usage else 0,
        "model_requests": usage.model_requests if usage else 0,
        "tool_calls": usage.tool_calls if usage else 0,
        "commands": usage.commands if usage else 0,
        "error_class": error_class,
        "cleanup_succeeded": True,
        "zero_managed_resources": True,
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "completed_at": datetime.now(UTC).isoformat(),
    }
    _write_once(arm_dir / "result.json", result)
    return result


def _export_repository(repository: Path, export: Path, task_id: str) -> None:
    archive = subprocess.Popen(
        ["git", "-C", str(repository), "archive", "--format=tar", "HEAD"],
        stdout=subprocess.PIPE,
    )
    export.mkdir()
    extract = subprocess.run(
        ["tar", "-xf", "-", "-C", str(export)],
        stdin=archive.stdout,
        check=False,
    )
    if archive.stdout is not None:
        archive.stdout.close()
    if extract.returncode != 0 or archive.wait() != 0:
        raise StageCRunnerError(f"{task_id} source export 失败")


def _source_git_environment() -> dict[str, str]:
    env = os.environ.copy()
    for source_name, target_name in (
        ("COMPILE_RUNTIME_HTTP_PROXY", "HTTP_PROXY"),
        ("COMPILE_RUNTIME_HTTPS_PROXY", "HTTPS_PROXY"),
        ("COMPILE_RUNTIME_NO_PROXY", "NO_PROXY"),
    ):
        value = os.environ.get(source_name)
        if value:
            env[target_name] = value
    return env


def _fetch_exact_commit(repository: Path, task: dict[str, Any]) -> None:
    argv = [
        "git",
        "-c",
        "http.version=HTTP/1.1",
        "-C",
        str(repository),
        "fetch",
        "--quiet",
        "--depth",
        "1",
        "origin",
        task["commit_sha"],
    ]
    failures: list[str] = []
    for attempt in range(1, 4):
        result = _run(
            argv,
            timeout=600,
            check=False,
            env=_source_git_environment(),
        )
        if result.returncode == 0:
            return
        failures.append((result.stderr or result.stdout).strip()[-2000:])
        if attempt < 3:
            time.sleep(attempt)
    raise StageCRunnerError(
        f"{task['task_id']} exact commit fetch 连续 3 次失败:\n{failures[-1]}"
    )


def _clone_export(task: dict[str, Any], destination: Path) -> dict[str, Any]:
    repository = destination / "repository"
    export = destination / "source"
    destination.mkdir(parents=True, exist_ok=False)
    _run(["git", "init", "--quiet", str(repository)])
    _run(
        [
            "git",
            "-C",
            str(repository),
            "remote",
            "add",
            "origin",
            task["repository_url"],
        ]
    )
    _fetch_exact_commit(repository, task)
    _run(
        ["git", "-C", str(repository), "checkout", "--quiet", "--detach", "FETCH_HEAD"]
    )
    checked_out = _run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"]
    ).stdout.strip()
    if checked_out != task["commit_sha"]:
        raise StageCRunnerError(f"{task['task_id']} exact commit 漂移")
    _export_repository(repository, export, task["task_id"])
    observed = qualification._archive_sha256(repository)
    if observed != task["source_snapshot_sha256"]:
        raise StageCRunnerError(f"{task['task_id']} source snapshot 漂移")
    return {
        "repository": repository,
        "source": export,
        "source_snapshot_sha256": observed,
    }


def _copy_prepared_source(
    task: dict[str, Any], source_identity: dict[str, Any], destination: Path
) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=False)
    repository = destination / "repository"
    source = destination / "source"
    shutil.copytree(source_identity["repository"], repository, symlinks=True)
    checked_out = _run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"]
    ).stdout.strip()
    observed = qualification._archive_sha256(repository)
    if checked_out != task["commit_sha"] or observed != task["source_snapshot_sha256"]:
        raise StageCRunnerError(f"{task['task_id']} pair source 副本身份漂移")
    _export_repository(repository, source, task["task_id"])
    copied = {
        "repository": repository,
        "source": source,
        "source_snapshot_sha256": observed,
    }
    _validate_prepared_source(task, copied)
    return copied


def _prepare_pair_sources(
    task: dict[str, Any], destination: Path
) -> dict[str, dict[str, Any]]:
    acquired = _clone_export(task, destination / "source-acquisition")
    _validate_prepared_source(task, acquired)
    prepared = {
        arm: _copy_prepared_source(task, acquired, destination / f"arm-{arm.lower()}")
        for arm in ("A", "B")
    }
    if prepared["A"]["repository"].samefile(prepared["B"]["repository"]):
        raise StageCRunnerError(f"{task['task_id']} pair source 未隔离")
    return prepared


def _source_observation(source: Path) -> dict[str, Any]:
    preferred = (
        "README",
        "README.md",
        "CMakeLists.txt",
        "Makefile",
        "makefile",
        "configure.ac",
        "configure",
    )
    documents: dict[str, str] = {}
    used = 0
    for relative in preferred:
        path = source / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")[:32_000]
        if used + len(text.encode()) > 128_000:
            break
        documents[relative] = text
        used += len(text.encode())
    return {
        "top_level_files": sorted(path.name for path in source.iterdir())[:200],
        "documents": documents,
    }


def _candidate_artifact_validation_script(task: dict[str, Any]) -> str:
    lines = ["set -euo pipefail"]
    for relative, expected_type in zip(
        task["target_contract"]["required_artifacts"],
        task["target_contract"]["artifact_types"],
        strict=True,
    ):
        path = shlex.quote(f"/artifacts/{relative}")
        lines.extend(
            (
                f"test -f {path}",
                f"test ! -L {path}",
                f"test -s {path}",
                f"kind=$(file -b -- {path})",
            )
        )
        if expected_type == "static_library":
            lines.append(f'test -n "$(ar t {path})"')
        elif expected_type == "executable":
            lines.append('case "$kind" in *[Ee]xecutable*) ;; *) exit 23 ;; esac')
        lines.append("printf '%s\\n' \"$kind\"")
    return "\n".join(lines)


def _artifact_evidence_from_candidate(
    task: dict[str, Any], artifacts: Path, file_types: list[str]
) -> list[dict[str, Any]]:
    required = task["target_contract"]["required_artifacts"]
    types = task["target_contract"]["artifact_types"]
    if len(file_types) != len(required):
        raise StageCRunnerError(f"{task['task_id']} candidate file 输出数量无效")
    result = []
    for relative, expected_type, file_type in zip(
        required, types, file_types, strict=True
    ):
        path = artifacts / relative
        if not path.is_file() or path.is_symlink() or path.stat().st_size <= 0:
            raise StageCRunnerError(
                f"{task['task_id']} 缺少有效 required artifact: {relative}"
            )
        if expected_type == "static_library" and path.read_bytes()[:8] != b"!<arch>\n":
            raise StageCRunnerError(f"{task['task_id']} 非静态库: {relative}")
        if expected_type == "executable" and "executable" not in file_type.lower():
            raise StageCRunnerError(f"{task['task_id']} 非 executable: {relative}")
        result.append(
            {
                "path": relative,
                "type": expected_type,
                "size_bytes": path.stat().st_size,
                "sha256": qualification.file_sha256(path),
                "file_type": file_type,
            }
        )
    return result


class DockerfileExecutor:
    def __init__(
        self,
        *,
        source: Path,
        task: dict[str, Any],
        arm_dir: Path,
        timeout_seconds: int,
    ):
        self.source = source
        self.task = task
        self.arm_dir = arm_dir
        self.timeout_seconds = timeout_seconds
        self.images: list[str] = []
        self.base_aliases: list[str] = []
        self.artifact_dirs: dict[int, Path] = {}
        self.results: dict[int, controlled.ControlledBuildResult] = {}

    def execute(
        self, dockerfile: str, *, revision: int
    ) -> controlled.ControlledBuildResult:
        first_line = dockerfile.splitlines()[0] if dockerfile.splitlines() else ""
        if not first_line.startswith("FROM "):
            raise StageCRunnerError("Stage C A candidate 缺少冻结 FROM")
        base_image_id = first_line.removeprefix("FROM ").strip()
        controlled.validate_dockerfile(dockerfile, base_image_id)
        base_alias = f"forge-stage-c-base:{uuid.uuid4().hex}"
        _run(["docker", "tag", base_image_id, base_alias])
        aliased_image_id = _run(
            ["docker", "image", "inspect", base_alias, "--format", "{{.Id}}"]
        ).stdout.strip()
        if aliased_image_id != base_image_id:
            _run(["docker", "image", "rm", base_alias], check=False)
            raise StageCRunnerError("Stage C A 本地 base alias identity 漂移")
        self.base_aliases.append(base_alias)
        execution_dockerfile = dockerfile.replace(
            f"FROM {base_image_id}", f"FROM {base_alias}", 1
        )
        revision_dir = self.arm_dir / "executor" / f"revision-{revision}"
        context = revision_dir / "context"
        artifacts = revision_dir / "artifacts"
        context.mkdir(parents=True, exist_ok=False)
        artifacts.mkdir()
        shutil.copytree(self.source, context / "source")
        (revision_dir / "Dockerfile.candidate").write_text(dockerfile, encoding="utf-8")
        (context / "Dockerfile").write_text(execution_dockerfile, encoding="utf-8")
        (revision_dir / "base-alias.json").write_text(
            json.dumps(
                {"base_image_id": base_image_id, "execution_alias": base_alias},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        tag = f"forge-stage-c-arm-a:{uuid.uuid4().hex}"
        name = f"{MANAGED_A_PREFIX}extract-{uuid.uuid4().hex[:8]}"
        started = time.perf_counter()
        build = _run(
            [
                "docker",
                "build",
                "--network",
                "none",
                "--label",
                "forge.stage-c.managed=true",
                "--tag",
                tag,
                "--file",
                str(context / "Dockerfile"),
                str(context),
            ],
            timeout=self.timeout_seconds,
            check=False,
        )
        output = (build.stdout + "\n" + build.stderr)[-64 * 1024 :]
        image_id = None
        artifact_paths: tuple[str, ...] = ()
        artifact_manifest_sha256 = None
        artifacts_valid = False
        if build.returncode == 0:
            image_id = _run(
                ["docker", "image", "inspect", tag, "--format", "{{.Id}}"]
            ).stdout.strip()
            self.images.append(tag)
            validation = None
            try:
                validation = _run(
                    [
                        "docker",
                        "run",
                        "--name",
                        name,
                        "--label",
                        "forge.stage-c.managed=true",
                        "--network",
                        "none",
                        "--read-only",
                        image_id,
                        "bash",
                        "-lc",
                        _candidate_artifact_validation_script(self.task),
                    ],
                    timeout=min(self.timeout_seconds, 300),
                    check=False,
                )
                if validation.returncode == 0:
                    _run(["docker", "cp", f"{name}:/artifacts/.", str(artifacts)])
            finally:
                _run(["docker", "rm", "-f", name], check=False)
            try:
                if validation is None or validation.returncode != 0:
                    detail = (
                        ""
                        if validation is None
                        else (validation.stderr or validation.stdout)
                    )
                    raise StageCRunnerError(
                        f"{self.task['task_id']} candidate image 产物验证失败: {detail.strip()[-2000:]}"
                    )
                items = _artifact_evidence_from_candidate(
                    self.task,
                    artifacts,
                    validation.stdout.splitlines(),
                )
                artifacts_valid = True
            except StageCRunnerError as exc:
                items = []
                output = (output + f"\nartifact validation failed: {exc}")[-64 * 1024 :]
            artifact_paths = tuple(item["path"] for item in items)
            artifact_manifest_sha256 = protocol.canonical_sha256(items)
            (revision_dir / "artifact-manifest.json").write_text(
                json.dumps(items, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        result = controlled.ControlledBuildResult(
            execution_id=f"execution:{uuid.uuid4().hex}",
            dockerfile_sha256=hashlib.sha256(dockerfile.encode()).hexdigest(),
            succeeded=(
                build.returncode == 0
                and artifacts_valid
                and set(artifact_paths)
                == set(self.task["target_contract"]["required_artifacts"])
            ),
            timed_out=False,
            exit_code=build.returncode,
            duration_seconds=round(time.perf_counter() - started, 6),
            output_tail=output,
            artifact_paths=artifact_paths,
            artifact_manifest_sha256=artifact_manifest_sha256,
            candidate_image_id=image_id,
        )
        result.validate()
        self.artifact_dirs[revision] = artifacts
        self.results[revision] = result
        return result

    def cleanup(self) -> None:
        for image in reversed(self.images):
            _run(["docker", "image", "rm", "--force", image], check=False)
        self.images.clear()
        for alias in reversed(self.base_aliases):
            _run(["docker", "image", "rm", alias], check=False)
        self.base_aliases.clear()


def _run_oracle(task: dict[str, Any], candidate_image_id: str, suffix: str) -> bool:
    name = f"{MANAGED_A_PREFIX}oracle-{uuid.uuid4().hex[:8]}"
    oracle = task["oracle"]
    if oracle["kind"] == "compile_and_run":
        extension = ".c" if oracle["language"] == "c11" else ".cc"
        source = f"/tmp/stage-c-{suffix}{extension}"
        executable = f"/tmp/stage-c-{suffix}"
        encoded = base64.b64encode(oracle["source"].encode()).decode()
        compile_argv = [
            source
            if item == "{source}"
            else executable
            if item == "{executable}"
            else item
            for item in oracle["compile_argv"]
        ]
        run_argv = [
            executable if item == "{executable}" else item
            for item in oracle["run_argv"]
        ]
        script = f"printf %s {shlex.quote(encoded)} | base64 -d > {source} && {shlex.join(compile_argv)} && {shlex.join(run_argv)}"
    else:
        script = shlex.join(oracle["argv"])
    try:
        result = _run(
            [
                "docker",
                "run",
                "--name",
                name,
                "--label",
                "forge.stage-c.managed=true",
                "--network",
                "none",
                "--read-only",
                "--tmpfs",
                "/tmp:rw,exec,nosuid,nodev,size=64m",
                candidate_image_id,
                "bash",
                "-lc",
                "set -euo pipefail\n" + script,
            ],
            timeout=300,
            check=False,
        )
        return result.returncode == 0
    finally:
        _run(["docker", "rm", "-f", name], check=False)


def _layer(name: str, passed: bool, reason: str) -> dict[str, Any]:
    return {"layer": name, "status": "passed" if passed else "failed", "reason": reason}


def _evaluate_a(
    manifest: dict[str, Any],
    task: dict[str, Any],
    outcome: controlled.ControlledBaselineOutcome,
    executor: DockerfileExecutor,
    dockerfile: str | None,
) -> tuple[list[dict[str, Any]], bool, bool | None]:
    submitted = outcome.candidate is not None and dockerfile is not None
    first = (
        executor.results.get(outcome.candidate.revision) if outcome.candidate else None
    )
    required = set(task["target_contract"]["required_artifacts"])
    s0 = submitted and outcome.evidence_head_sha256 != "0" * 64
    s1 = bool(first and first.succeeded)
    s2 = bool(first and set(first.artifact_paths) == required)
    artifacts = (
        executor.artifact_dirs.get(outcome.candidate.revision)
        if outcome.candidate
        else None
    )
    s3 = bool(
        artifacts
        and first
        and first.candidate_image_id
        and _run_oracle(task, first.candidate_image_id, f"{task['task_id']}-candidate")
    )
    try:
        s4 = bool(
            dockerfile
            and controlled.validate_dockerfile(
                dockerfile, manifest["environment"]["image_id"]
            )
        )
    except controlled.ControlledBaselineError:
        s4 = False
    s5 = False
    bitwise: bool | None = None
    if all((s0, s1, s2, s3, s4)) and dockerfile is not None and first is not None:
        replay = executor.execute(
            dockerfile, revision=outcome.candidate.revision + 1000
        )
        bitwise = replay.artifact_manifest_sha256 == first.artifact_manifest_sha256
        replay_oracle = bool(
            replay.succeeded
            and replay.candidate_image_id
            and _run_oracle(
                task,
                replay.candidate_image_id,
                f"{task['task_id']}-replay",
            )
        )
        s5 = (
            replay.succeeded
            and replay_oracle
            and (bitwise or not task["target_contract"]["bitwise_required"])
        )
    statuses = (s0, s1, s2, s3, s4, s5)
    layers = [
        _layer(f"S{index}", passed, "passed" if passed else f"stage_c_s{index}_failed")
        for index, passed in enumerate(statuses)
    ]
    return layers, all(statuses), bitwise


def execute_controlled_arm(
    manifest: dict[str, Any],
    task: dict[str, Any],
    pair: dict[str, Any],
    *,
    release_revision: str,
    arm_dir: Path,
    source_identity: dict[str, Any],
    model_factory: Callable[[dict[str, Any], str | None], Any] = _model,
) -> dict[str, Any]:
    started = time.perf_counter()
    digest = protocol.canonical_sha256(manifest)
    budget = manifest["budget"]["per_arm"]
    outcome = None
    layers: list[dict[str, Any]] = []
    strict = False
    bitwise = None
    _validate_prepared_source(task, source_identity)
    _register_arm_attempt(
        manifest,
        pair,
        "A",
        release_revision=release_revision,
        arm_dir=arm_dir,
        source_snapshot_sha256=source_identity["source_snapshot_sha256"],
    )
    executor = DockerfileExecutor(
        source=source_identity["source"],
        task=task,
        arm_dir=arm_dir,
        timeout_seconds=budget["command_timeout_seconds"],
    )
    try:
        public_contract = {
            "repository_url": task["repository_url"],
            "commit_sha": task["commit_sha"],
            "build_system_capabilities": task["build_system_capabilities"],
            "selected_build_system": task["selected_build_system"],
            "target_contract": task["target_contract"],
            "operation_policy": manifest["environment"]["network_policy"],
        }
        outcome = controlled.ControlledBaselineRunner(
            task_contract=public_contract,
            source_observation=_source_observation(source_identity["source"]),
            task_id=task["task_id"],
            attempt_id=pair["attempt_ids"]["A"],
            base_image_id=manifest["environment"]["image_id"],
            model=model_factory(manifest, f"stage-c-a-{pair['pair_id']}"),
            executor=executor,
            limits=controlled.ControlledBaselineLimits(
                max_model_requests=budget["max_model_requests"],
                max_recorded_tokens=budget["max_recorded_tokens"],
                work_timeout_seconds=budget["work_timeout_seconds"],
            ),
            output_dir=arm_dir / "method",
        ).run()
        dockerfile_path = arm_dir / "method/Dockerfile"
        dockerfile = (
            dockerfile_path.read_text(encoding="utf-8")
            if dockerfile_path.is_file()
            else None
        )
        layers, strict, bitwise = _evaluate_a(
            manifest, task, outcome, executor, dockerfile
        )
    finally:
        executor.cleanup()
        require_zero_managed_resources()
    assert outcome is not None
    result = {
        "schema_version": "forge-stage-c-arm-result-1.0.0",
        "manifest_sha256": digest,
        "release_revision": release_revision,
        "pair_id": pair["pair_id"],
        "task_id": task["task_id"],
        "replicate": pair["replicate"],
        "arm": "A",
        "method": "cxxcrafter-controlled",
        "attempt_id": pair["attempt_ids"]["A"],
        "candidate_generated": outcome.candidate_generated,
        "candidate_submitted": outcome.candidate_submitted,
        "s0_s5": layers,
        "strict_reproducible_build_success": strict,
        "bitwise_reproducible": bitwise,
        "recorded_tokens": outcome.recorded_tokens,
        "model_requests": outcome.model_requests,
        "tool_calls": None,
        "commands": outcome.executor_runs,
        "error_class": (
            outcome.termination_reason
            if outcome.termination_reason != "candidate_submitted"
            else None
        ),
        "cleanup_succeeded": True,
        "zero_managed_resources": True,
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "completed_at": datetime.now(UTC).isoformat(),
    }
    _write_once(arm_dir / "result.json", result)
    return result


def _validate_arm_result(
    manifest: dict[str, Any], pair: dict[str, Any], arm: str, value: dict[str, Any]
) -> None:
    if (
        value.get("manifest_sha256") != protocol.canonical_sha256(manifest)
        or value.get("pair_id") != pair["pair_id"]
        or value.get("task_id") != pair["task_id"]
        or value.get("replicate") != pair["replicate"]
        or value.get("arm") != arm
        or value.get("attempt_id") != pair["attempt_ids"][arm]
        or value.get("method")
        != ("cxxcrafter-controlled" if arm == "A" else "forge-agent-workflow-node-v2")
        or type(value.get("candidate_generated")) is not bool
        or type(value.get("candidate_submitted")) is not bool
        or (value["candidate_submitted"] and not value["candidate_generated"])
        or type(value.get("strict_reproducible_build_success")) is not bool
        or value.get("bitwise_reproducible") not in {None, True, False}
        or not isinstance(value.get("s0_s5"), list)
        or type(value.get("recorded_tokens")) is not int
        or not 0
        <= value["recorded_tokens"]
        <= manifest["budget"]["per_arm"]["max_recorded_tokens"]
        or value.get("cleanup_succeeded") is not True
        or value.get("zero_managed_resources") is not True
    ):
        raise StageCRunnerError(f"{pair['pair_id']} arm {arm} evidence 未闭合")


def _completed_pairs(
    manifest: dict[str, Any], output_dir: Path
) -> list[dict[str, Any]]:
    completed: list[dict[str, Any]] = []
    gap = False
    for pair in manifest["schedule"]["pairs"]:
        pair_dir = output_dir / "pairs" / pair["pair_id"]
        pair_result = pair_dir / "pair.json"
        if not pair_result.exists():
            if pair_dir.exists() and any(pair_dir.rglob("*")):
                raise StageCRunnerError("存在未闭合 pair，禁止静默续跑或补跑")
            gap = True
            continue
        if gap:
            raise StageCRunnerError("Stage C evidence 不是完整连续 pair 前缀")
        value = _load_json(pair_result)
        arm_values = []
        for arm in ("A", "B"):
            _validate_attempt_marker(manifest, pair, arm, pair_dir / arm)
            arm_value = _load_json(pair_dir / arm / "result.json")
            _validate_arm_result(manifest, pair, arm, arm_value)
            arm_values.append(arm_value)
        expected_delta = int(arm_values[1]["strict_reproducible_build_success"]) - int(
            arm_values[0]["strict_reproducible_build_success"]
        )
        if (
            value.get("schema_version") != "forge-stage-c-pair-result-1.0.0"
            or value.get("manifest_sha256") != protocol.canonical_sha256(manifest)
            or value.get("pair_id") != pair["pair_id"]
            or value.get("task_id") != pair["task_id"]
            or value.get("replicate") != pair["replicate"]
            or value.get("arm_order") != pair["arm_order"]
            or value.get("complete") is not True
            or value.get("paired_delta") != expected_delta
            or value.get("arms") != arm_values
        ):
            raise StageCRunnerError(f"{pair['pair_id']} pair result 无效")
        completed.append(value)
    return completed


def _summaries(
    manifest: dict[str, Any],
    release_revision: str,
    reachability: dict[str, Any],
    pairs: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    arms = [arm for pair in pairs for arm in pair["arms"]]
    project_scores = []
    for task_id in manifest["schedule"]["project_order"]:
        task_pairs = [pair for pair in pairs if pair["task_id"] == task_id]
        if len(task_pairs) != 2:
            continue
        deltas = [
            int(
                next(arm for arm in pair["arms"] if arm["arm"] == "B")[
                    "strict_reproducible_build_success"
                ]
            )
            - int(
                next(arm for arm in pair["arms"] if arm["arm"] == "A")[
                    "strict_reproducible_build_success"
                ]
            )
            for pair in task_pairs
        ]
        project_scores.append(
            {"task_id": task_id, "replicate_deltas": deltas, "score": sum(deltas) / 2}
        )
    deployment = {
        "schema_version": "forge-stage-c-deployment-report-1.0.0",
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "release_revision": release_revision,
        "pair_count": len(pairs),
        "arm_count": len(arms),
        "candidate_generated": sum(arm["candidate_generated"] for arm in arms),
        "candidate_submitted": sum(arm["candidate_submitted"] for arm in arms),
        "strict_success": {
            method: sum(
                arm["strict_reproducible_build_success"]
                for arm in arms
                if arm["arm"] == method
            )
            for method in ("A", "B")
        },
        "recorded_tokens": sum(arm["recorded_tokens"] for arm in arms),
        "reachability_recorded_tokens": reachability["recorded_tokens"],
        "pairs": pairs,
        "zero_managed_resources": True,
        "completed_at": datetime.now(UTC).isoformat(),
    }
    paired = {
        "schema_version": "forge-stage-c-paired-report-1.0.0",
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "independent_unit": "project",
        "complete_project_count": len(project_scores),
        "project_scores": project_scores,
        "mean_project_level_paired_delta": (
            sum(item["score"] for item in project_scores) / len(project_scores)
            if project_scores
            else None
        ),
        "inference_status": "calibration_descriptive_only",
    }
    return deployment, paired


async def run_batch_async(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    arm_executors: dict[str, Callable[..., Any]] | None = None,
) -> dict[str, Any]:
    preflight = collect_preflight(manifest, output_dir=output_dir, require_empty=False)
    if not preflight["ready"]:
        raise StageCRunnerError(
            "存在未闭合 pair，禁止静默续跑或补跑: "
            + ",".join(preflight["incomplete_pairs"])
        )
    revision = preflight["release_revision"]
    reachability = _require_reachability(manifest, output_dir, revision)
    completed = _completed_pairs(manifest, output_dir)
    marker = output_dir / manifest["execution"]["batch_marker"]
    if not marker.exists():
        if completed:
            raise StageCRunnerError("缺少 batch marker，拒绝导入既有 pair")
        _write_once(
            marker,
            {
                "schema_version": "forge-stage-c-batch-marker-1.0.0",
                "manifest_sha256": protocol.canonical_sha256(manifest),
                "release_revision": revision,
                "status": "started",
            },
        )
    executors = arm_executors or {
        "A": execute_controlled_arm,
        "B": execute_forge_arm,
    }
    for pair in manifest["schedule"]["pairs"][len(completed) :]:
        used = sum(arm["recorded_tokens"] for item in completed for arm in item["arms"])
        if (
            used + 2 * manifest["budget"]["per_arm"]["max_recorded_tokens"]
            > manifest["budget"]["formal_arms_max_recorded_tokens"]
        ):
            break
        pair_dir = output_dir / "pairs" / pair["pair_id"]
        task = _task(manifest, pair["task_id"])
        arms = []
        with tempfile.TemporaryDirectory(
            prefix=f"forge-stage-c-pair-source-{task['task_id']}-"
        ) as temporary:
            sources = _prepare_pair_sources(task, Path(temporary))
            require_zero_managed_resources()
            for arm in pair["arm_order"]:
                arm_dir = pair_dir / arm
                executor = executors[arm]
                value = executor(
                    manifest,
                    task,
                    pair,
                    release_revision=revision,
                    arm_dir=arm_dir,
                    source_identity=sources[arm],
                )
                if hasattr(value, "__await__"):
                    value = await value
                _validate_attempt_marker(manifest, pair, arm, arm_dir)
                _validate_arm_result(manifest, pair, arm, value)
                arms.append(value)
                require_zero_managed_resources()
        normalized_arms = [
            next(item for item in arms if item["arm"] == arm) for arm in ("A", "B")
        ]
        pair_value = {
            "schema_version": "forge-stage-c-pair-result-1.0.0",
            "manifest_sha256": protocol.canonical_sha256(manifest),
            "release_revision": revision,
            "pair_id": pair["pair_id"],
            "task_id": pair["task_id"],
            "replicate": pair["replicate"],
            "arm_order": pair["arm_order"],
            "complete": True,
            "paired_delta": int(normalized_arms[1]["strict_reproducible_build_success"])
            - int(normalized_arms[0]["strict_reproducible_build_success"]),
            "arms": normalized_arms,
        }
        _write_once(pair_dir / "pair.json", pair_value)
        completed.append(pair_value)
    deployment, paired = _summaries(manifest, revision, reachability, completed)
    _write_once(output_dir / manifest["execution"]["batch_report"], deployment)
    _write_once(output_dir / manifest["execution"]["paired_report"], paired)
    marker_value = _load_json(marker)
    marker_value["status"] = "passed" if len(completed) == 24 else "budget_stopped"
    marker.write_text(
        json.dumps(marker_value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return deployment


def run_batch(manifest: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return asyncio.run(run_batch_async(manifest, **kwargs))


def load_report(
    manifest: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR
) -> dict[str, Any]:
    report = _load_json(output_dir / manifest["execution"]["batch_report"])
    if report.get("manifest_sha256") != protocol.canonical_sha256(manifest):
        raise StageCRunnerError("Stage C report identity 漂移")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("validate", "preflight", "reachability", "batch", "report")
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest(args.manifest)
    if args.command == "validate":
        _validate_all_node_inputs(manifest)
        result: Any = {
            "status": "valid",
            "manifest_sha256": protocol.canonical_sha256(manifest),
            "pair_count": 24,
            "physical_attempt_count": 48,
            "provider_calls": 0,
            "formal_stage_c_attempts": 0,
            "model_tokens": 0,
        }
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
    else:
        result = load_report(manifest, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
