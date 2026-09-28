#!/usr/bin/env python3
"""验证 Stage C v8 workspace remediation 未授权候选。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_stage_c_runner as stage_c  # noqa: E402
import forge_stage_c_v7_prefreeze_canary_authorized_runner as parent_runner  # noqa: E402
import forge_stage_c_v8_workspace_remediation_protocol as protocol  # noqa: E402

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
from deerflow.config.paths import Paths  # noqa: E402

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST


class StageCV8RunnerError(RuntimeError):
    """v8 candidate 路径、资源或未授权边界无效。"""


def _canonical_sha256(manifest: dict[str, Any]) -> str:
    return protocol.parent.parent.canonical_sha256(manifest)


def _task(manifest: dict[str, Any], task_id: str) -> dict[str, Any]:
    matches = [task for task in manifest["tasks"] if task["task_id"] == task_id]
    if len(matches) != 1:
        raise StageCV8RunnerError(f"未知或重复 task: {task_id}")
    return matches[0]


def _thread_id(attempt: dict[str, Any], manifest_sha256: str) -> str:
    identity = hashlib.sha256(attempt["attempt_id"].encode("utf-8")).hexdigest()
    return f"stage-c-v8-b-{identity[:32]}-{manifest_sha256[:16]}"


def _explicit_paths(repo_root: Path) -> Paths:
    resolved = repo_root.resolve(strict=True)
    return Paths(workspace_root=resolved, host_workspace_root=str(resolved))


def _has_symlink_boundary(path: Path, stop: Path) -> bool:
    current = path.absolute()
    boundary = stop.absolute()
    while True:
        if current.exists() and current.is_symlink():
            return True
        if current == boundary:
            return False
        if boundary not in current.parents:
            return True
        current = current.parent


def _require_directory_access(path: Path, *, label: str) -> None:
    if path.is_symlink() or not path.is_dir():
        raise StageCV8RunnerError(f"{label} 必须是非符号链接目录")
    if not os.access(path, os.W_OK | os.X_OK):
        raise StageCV8RunnerError(f"{label} 对当前用户不可写或不可进入")


def require_workspace_identity(
    manifest: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    output_dir: Path | None = None,
) -> dict[str, str]:
    execution = manifest["execution"]
    contract = execution["workspace"]
    if contract != {
        "binding": "release_repository_root",
        "process_workspace_root": ".",
        "host_workspace_root": ".",
        "compile_sessions_relative_path": ".compile-sessions",
        "process_host_roots_must_match": True,
        "repository_root_must_not_be_symlink": True,
        "compile_sessions_root_must_not_be_symlink": True,
        "compile_sessions_root_must_be_writable": True,
        "preflight_before_credential_model_provider_or_marker": True,
    }:
        raise StageCV8RunnerError("v8 workspace 合同漂移")
    repo_absolute = repo_root.absolute()
    repo_resolved = repo_root.resolve(strict=True)
    if repo_absolute != repo_resolved or repo_root.is_symlink():
        raise StageCV8RunnerError("release repository root 不得经过符号链接")
    paths = _explicit_paths(repo_root)
    process_root = paths.compile_sessions_dir
    host_root = paths.host_compile_sessions_dir
    expected_root = repo_resolved / ".compile-sessions"
    if process_root != expected_root or host_root != expected_root:
        raise StageCV8RunnerError("Compile Session process/host root 未绑定到 release repository")
    if _has_symlink_boundary(expected_root, repo_resolved):
        raise StageCV8RunnerError("Compile Session root 路径包含符号链接边界")
    _require_directory_access(expected_root, label="Compile Session root")

    expected_output = repo_resolved / execution["evidence_directory_relative"]
    observed_output = (output_dir or expected_output).resolve(strict=False)
    if observed_output != expected_output or expected_output.parent != expected_root:
        raise StageCV8RunnerError("candidate evidence 路径未绑定到独立 Compile Session 子目录")
    if expected_output.exists():
        if _has_symlink_boundary(expected_output, repo_resolved):
            raise StageCV8RunnerError("candidate evidence 路径包含符号链接边界")
        _require_directory_access(expected_output, label="candidate evidence directory")
    else:
        _require_directory_access(expected_output.parent, label="candidate evidence parent")
    return {
        "binding": "release_repository_root",
        "repository_root": str(repo_resolved),
        "process_compile_sessions_root": str(process_root),
        "host_compile_sessions_root": str(host_root),
        "evidence_directory": str(expected_output),
    }


def _evidence_files(output_dir: Path) -> list[str]:
    if not output_dir.exists():
        return []
    return sorted(path.relative_to(output_dir).as_posix() for path in output_dir.rglob("*") if path.is_file())


def _node_input(manifest: dict[str, Any], task: dict[str, Any], session: Any, attempt_id: str) -> AgentBuildNodeInput:
    budget = manifest["budget"]["per_attempt"]
    target = task["target_contract"]
    compiled_types = tuple(item for item in target["artifact_types"] if item != "support_file")
    build_system_candidates = tuple(item for item in task["build_system_capabilities"] if item in {"cmake", "make", "autotools"})
    if not compiled_types or task["selected_build_system"] not in build_system_candidates:
        raise StageCV8RunnerError(f"{task['task_id']} target 或 build-system 合同无效")
    frozen = manifest["frozen_candidate_components"]
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
        operation_policy_ref="stage-c-v8-workspace-remediation-operation-policy-v1",
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
            manifest_sha256=_canonical_sha256(manifest),
            protocol_sha256=frozen[protocol.PROTOCOL_PATH],
            runner_sha256=frozen[protocol.RUNNER_PATH],
        ),
        initial_observation={
            "required_candidate_artifacts": tuple(target["required_artifacts"]),
            "build_system_capabilities": tuple(task["build_system_capabilities"]),
            "selected_build_system": task["selected_build_system"],
            "qualification_receipt_sha256": task["qualification_receipt"]["receipt_sha256"],
            "prefreeze_feedback_enabled": True,
            "network_after_clone": "none",
            "workspace_binding": "release_repository_root",
        },
    )


def _validate_all_node_inputs(manifest: dict[str, Any]) -> None:
    session = type("StageCV8ContractSession", (), {"session_id": "stage-c-v8-contract"})()
    thread_ids: list[str] = []
    for attempt in manifest["schedule"]["attempts"]:
        task = _task(manifest, attempt["task_id"])
        _node_input(manifest, task, session, attempt["attempt_id"]).validate()
        stage_c._oracle_spec(task).validate()
        thread_id = _thread_id(attempt, _canonical_sha256(manifest))
        CompileSessionManager._validate_session_components(thread_id, "stage-c-v8-contract")
        thread_ids.append(thread_id)
    if len(thread_ids) != len(set(thread_ids)):
        raise StageCV8RunnerError("v8 thread identity 不唯一")


def collect_preflight(
    manifest: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    output_dir: Path | None = None,
    require_empty: bool = True,
) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    _validate_all_node_inputs(manifest)
    workspace = require_workspace_identity(manifest, repo_root=repo_root, output_dir=output_dir)
    parent_runner.require_docker_identity(manifest)
    parent_runner.require_zero_managed_resources()
    evidence_root = Path(workspace["evidence_directory"])
    files = _evidence_files(evidence_root)
    if require_empty and files:
        raise StageCV8RunnerError("v8 candidate evidence 目录必须为空")
    return {
        "ready": True,
        "manifest_sha256": _canonical_sha256(manifest),
        "parent_manifest_sha256": protocol.PARENT_MANIFEST_CANONICAL_SHA256,
        "workspace": workspace,
        "evidence_files": files,
        "zero_managed_resources": True,
        "credential_read": False,
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
        "authorized": False,
    }


def _experiment_policy(manifest: dict[str, Any], task: dict[str, Any], attempt: dict[str, Any]) -> ExperimentPolicy:
    budget = manifest["budget"]["per_attempt"]
    provider = manifest["provider"]
    return ExperimentPolicy(
        benchmark_id="forge-stage-c-v8-workspace-remediation-zero-provider-gate",
        manifest_sha256=_canonical_sha256(manifest),
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
        manager.paths = _explicit_paths(repo_root)
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
        raise StageCV8RunnerError(f"{task['task_id']} 无法生成 replay source archive")
    observed = protocol.parent.parent.file_sha256(source_archive)
    if observed != task["source_snapshot_sha256"]:
        raise StageCV8RunnerError(f"{task['task_id']} source snapshot identity 漂移")
    session.replay_source_archive_sha256 = observed
    manager.save_session(session)


async def execute_zero_provider_gate_attempt(
    manifest: dict[str, Any],
    attempt: dict[str, Any],
    *,
    repo_root: Path,
    ledger_path: Path,
    model: Any,
) -> dict[str, Any]:
    """只供确定性本地模型 Docker gate 使用，不是正式 candidate 入口。"""
    if manifest["authorization"]["provider_calls_authorized"] is not False:
        raise StageCV8RunnerError("zero-provider gate 只接受未授权 candidate")
    require_workspace_identity(manifest, repo_root=repo_root)
    task = _task(manifest, attempt["task_id"])
    digest = _canonical_sha256(manifest)
    ledger = ExperimentLedger.create(
        ledger_path,
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"manifest_sha256": digest, "task_id": task["task_id"], "gate": "zero_provider"},
    )
    thread_id = _thread_id(attempt, digest)
    session = None
    cleanup = None
    finalized = None
    node_result = None
    evaluation = None
    active = False
    events_path = None
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
                    run_id=f"stage-c-v8-gate-{uuid.uuid4().hex}",
                    task_description=f"Stage C v8 zero-provider gate: {task['task_id']}",
                )
                clone, _message = clone_repository_impl(
                    session=session,
                    repo_url=task["repository_url"],
                    commit_sha=task["commit_sha"],
                    depth=1,
                    max_retries=1,
                )
                if clone.exit_code != 0 or session.commit_sha != task["commit_sha"]:
                    raise StageCV8RunnerError("zero-provider gate 无法检出冻结 commit")
                _bind_replay_source_archive(task, session, services.manager)
                primary, _detected, _suggested = inspect_build_system_impl(session=session)
                if primary not in task["build_system_capabilities"]:
                    raise StageCV8RunnerError("zero-provider gate build-system identity 漂移")
                session.selected_build_system = task["selected_build_system"]
                services.manager.save_session(session)
                node_input = _node_input(manifest, task, session, attempt["attempt_id"])
                oracle_spec = stage_c._oracle_spec(task)
                with stage_c._offline_runtime(session) as offline_services:
                    node_result = await run_agent_workflow_node_v3(
                        node_input=node_input,
                        session=session,
                        manager=offline_services.manager,
                        model=model,
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
    finally:
        if active:
            deactivate_experiment(thread_id)
        parent_runner.require_zero_managed_resources()
    if session is None or finalized is None or cleanup is None or not cleanup.succeeded:
        raise StageCV8RunnerError("zero-provider gate cleanup 未闭合")
    observations = parent_runner._event_observations(events_path) if events_path and events_path.is_file() else {"token_ledger": []}
    usage = node_result.usage if node_result else None
    recorded_tokens = usage.recorded_tokens if usage else 0
    if sum(item["total_tokens"] for item in observations["token_ledger"]) != recorded_tokens:
        raise StageCV8RunnerError("zero-provider gate token ledger 不闭合")
    return {
        "session_id": finalized.session_id,
        "session_status": finalized.status,
        "session_directory": str(Path(finalized.metadata_path).parent),
        "candidate_submitted": bool(node_result and node_result.candidate_submitted),
        "strict_reproducible_build_success": bool(evaluation and evaluation.strict_reproducible_build_success),
        "bitwise_reproducible": evaluation.bitwise_reproducible if evaluation else None,
        "recorded_tokens": recorded_tokens,
        "request_token_ledger": observations["token_ledger"],
        "cleanup_succeeded": True,
        "zero_managed_resources": True,
    }


def validate_runtime(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    _validate_all_node_inputs(manifest)
    return {
        "status": "valid",
        "manifest_sha256": _canonical_sha256(manifest),
        "workspace_binding": "release_repository_root",
        "runtime": "agent-workflow-runtime-v3",
        "external_evaluator": "external-evaluator-v4",
        "credential_read": False,
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
        "evidence_written": False,
        "authorized": False,
    }


def show_plan(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "manifest_sha256": _canonical_sha256(manifest),
        "attempt_order": [item["task_id"] for item in manifest["schedule"]["attempts"]],
        "workspace_binding": manifest["execution"]["workspace"]["binding"],
        "evidence_directory_relative": manifest["execution"]["evidence_directory_relative"],
        "token_ceiling": None,
        "authorized": False,
    }


def _forbid_real_execution(command: str) -> None:
    raise StageCV8RunnerError(f"v8 candidate 未授权 {command}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "preflight", "show-plan", "reachability", "run"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest(args.manifest)
    if args.command == "validate":
        result: Mapping[str, Any] = validate_runtime(manifest)
    elif args.command == "preflight":
        result = collect_preflight(manifest)
    elif args.command == "show-plan":
        result = show_plan(manifest)
    else:
        _forbid_real_execution(args.command)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
