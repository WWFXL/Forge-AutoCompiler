#!/usr/bin/env python3
"""执行 Issue #291 授权的 Phase 5 reachability 与六项目校准。"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import shlex
import stat
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", SCRIPT_ROOT.parent)).resolve()
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_agent_workflow_stage_b_calibration_authorized_protocol as protocol  # noqa: E402

from deerflow.compile.agent_workflow_runtime import run_agent_workflow_node_v1  # noqa: E402
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
    model_response_metadata,
    new_evidence_id,
)
from deerflow.compile.external_evaluator import (  # noqa: E402
    ForgeCompileEvaluationBackend,
    FunctionalOracleSpec,
    run_external_evaluator_v1,
)
from deerflow.compile.operations import (  # noqa: E402
    cleanup_and_finalize_compile_session_impl,
    clone_repository_impl,
    get_compile_services,
    inspect_build_system_impl,
    prepare_compile_session_impl,
)

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_OUTPUT_DIR = Path(protocol.candidate.EVIDENCE_DIRECTORY)
MANAGED_CONTAINER_PREFIXES = ("deerflow-compile-", "deerflow-replay-")
AUTHORIZED_COMPOSE_PROJECT = "deer-flow-dev"
AUTHORIZED_COMPOSE_SERVICES = frozenset(("langgraph", "gateway"))
DOCKER_SOCKET = Path("/var/run/docker.sock")


class Phase5AuthorizedRunnerError(RuntimeError):
    """Phase 5 授权执行的 identity、evidence、预算或 cleanup 无效。"""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase5AuthorizedRunnerError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise Phase5AuthorizedRunnerError(f"JSON 根节点必须是对象: {path}")
    return value


def _write_once(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise Phase5AuthorizedRunnerError(f"不可覆盖已存在的 evidence: {path}") from exc


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def _git(repo_root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo_root}", *arguments],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise Phase5AuthorizedRunnerError("无法验证授权 release Git identity")
    return result.stdout.strip()


def _output_dir(manifest: dict[str, Any], output_dir: Path) -> Path:
    expected = Path(manifest["evidence_candidate"]["directory"]).resolve(strict=False)
    if output_dir.resolve(strict=False) != expected:
        raise Phase5AuthorizedRunnerError("evidence 必须写入 Phase 5 冻结授权目录")
    return output_dir


def require_release_identity(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, str]:
    branch = _git(repo_root, "branch", "--show-current")
    revision = _git(repo_root, "rev-parse", "HEAD")
    origin_main = _git(repo_root, "rev-parse", "origin/main")
    dirty = _git(repo_root, "status", "--porcelain", "--untracked-files=normal")
    execution = manifest["authorized_execution"]
    if branch != execution["release_branch"] or revision != origin_main:
        raise Phase5AuthorizedRunnerError("真实校准要求干净 main == origin/main")
    if dirty:
        raise Phase5AuthorizedRunnerError("真实校准要求干净工作树")
    baseline = execution["authorization_baseline_commit"]
    if _git(repo_root, "merge-base", baseline, revision) != baseline:
        raise Phase5AuthorizedRunnerError("当前 release 不是 Phase 5 授权基线的后代")
    return {"branch": branch, "revision": revision, "origin_main": origin_main}


def require_network_medium(manifest: dict[str, Any]) -> str:
    execution = manifest["authorized_execution"]
    name = execution["network_access_medium_env"]
    medium = os.environ.get(name)
    if medium != execution["network_access_medium"]:
        raise Phase5AuthorizedRunnerError(f"必须通过 {name}={execution['network_access_medium']} 记录当前网络介质")
    return medium


def _run_checked(command: Sequence[str], failure: str) -> str:
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise Phase5AuthorizedRunnerError(failure)
    return result.stdout.strip()


def _docker_socket_is_socket(path: Path = DOCKER_SOCKET) -> bool:
    try:
        return stat.S_ISSOCK(path.stat().st_mode)
    except OSError:
        return False


def require_docker_identity(manifest: dict[str, Any]) -> str:
    if not _docker_socket_is_socket():
        raise Phase5AuthorizedRunnerError("Docker socket 不存在或不是 socket")
    hostname = os.environ.get("HOSTNAME", "").strip()
    if not hostname:
        raise Phase5AuthorizedRunnerError("缺少当前执行容器 HOSTNAME")
    raw_container = _run_checked(["docker", "inspect", hostname], "无法核验当前 Compose/DooD 执行容器")
    try:
        inspected = json.loads(raw_container)
        container = inspected[0]
        labels = container["Config"]["Labels"]
        mounts = container["Mounts"]
    except (json.JSONDecodeError, IndexError, KeyError, TypeError) as exc:
        raise Phase5AuthorizedRunnerError("当前执行容器 Docker identity 无效") from exc
    if container.get("Id", "").startswith(hostname) is False or container["Config"].get("Hostname") != hostname:
        raise Phase5AuthorizedRunnerError("HOSTNAME 与当前 Docker 容器不一致")
    if labels.get("com.docker.compose.project") != AUTHORIZED_COMPOSE_PROJECT or labels.get("com.docker.compose.service") not in AUTHORIZED_COMPOSE_SERVICES:
        raise Phase5AuthorizedRunnerError("真实校准必须从授权 Compose/DooD control plane 执行")
    socket_mount = next((mount for mount in mounts if mount.get("Destination") == str(DOCKER_SOCKET)), None)
    if socket_mount is None or socket_mount.get("RW") is not True:
        raise Phase5AuthorizedRunnerError("Docker socket 必须以可写方式挂载")
    if not _run_checked(["docker", "version", "--format", "{{.Server.Version}}"], "Docker daemon 不可达"):
        raise Phase5AuthorizedRunnerError("Docker daemon server identity 为空")
    actual = _run_checked(
        ["docker", "image", "inspect", manifest["environment_candidate"]["compile_image"], "--format", "{{.Id}}"],
        "无法读取冻结编译镜像",
    )
    expected = manifest["environment_candidate"]["image_id"]
    if actual != expected:
        raise Phase5AuthorizedRunnerError("Docker image ID 与授权修订不一致")
    return actual


def managed_containers() -> list[str]:
    output = _run_checked(["docker", "ps", "-a", "--format", "{{.Names}}"], "无法核验受管容器")
    return sorted(name for name in output.splitlines() if name.startswith(MANAGED_CONTAINER_PREFIXES))


def require_zero_managed_resources() -> None:
    names = managed_containers()
    if names:
        raise Phase5AuthorizedRunnerError(f"存在 Compile Session/replay orphan: {','.join(names)}")
    paused = _run_checked(
        ["docker", "ps", "-q", "--filter", "status=paused", "--filter", "label=deerflow.compile.managed=true"],
        "无法核验 paused parent",
    )
    images = _run_checked(
        ["docker", "images", "-q", "--filter", "label=deerflow.compile.managed=true"],
        "无法核验受管镜像",
    )
    if paused or images:
        raise Phase5AuthorizedRunnerError("存在 paused parent 或受管镜像")


def _provider_config_preflight(manifest: dict[str, Any]) -> None:
    from deerflow.config import get_app_config

    provider = manifest["provider_candidate"]
    configured = get_app_config().get_model_config(provider["profile"])
    if configured is None or configured.model != provider["profile"]:
        raise Phase5AuthorizedRunnerError("config.yaml 缺少冻结 provider model")
    settings = configured.model_dump(exclude_none=True)
    endpoint = settings.get("base_url", settings.get("api_base", settings.get("openai_api_base")))
    if endpoint is None or str(endpoint).rstrip("/") != provider["endpoint"].rstrip("/"):
        raise Phase5AuthorizedRunnerError("config.yaml provider endpoint 发生漂移")
    if not os.environ.get(provider["credential_env_name"]):
        raise Phase5AuthorizedRunnerError("provider credential env 未注入")


def collect_preflight(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    require_empty: bool,
) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    _output_dir(manifest, output_dir)
    release = require_release_identity(manifest, repo_root)
    medium = require_network_medium(manifest)
    image_id = require_docker_identity(manifest)
    require_zero_managed_resources()
    _provider_config_preflight(manifest)
    files = sorted(str(path.relative_to(output_dir)).replace("\\", "/") for path in output_dir.rglob("*") if path.is_file()) if output_dir.exists() else []
    if require_empty and files:
        raise Phase5AuthorizedRunnerError("reachability 前要求授权 evidence 目录为空")
    return {
        "ready": True,
        "manifest_sha256": protocol.candidate.canonical_sha256(manifest),
        "release_revision": release["revision"],
        "network_access_medium": medium,
        "image_id": image_id,
        "credential_check": "environment_variable_presence_only",
        "evidence_files": files,
        "zero_managed_resources": True,
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
    }


def _response_text(response: Any) -> str:
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "".join(item if isinstance(item, str) else str(item.get("text", "")) for item in content if isinstance(item, (str, dict)))


def _create_provider_model(manifest: dict[str, Any], *, experiment_thread_id: str | None = None) -> Any:
    from deerflow.config import get_app_config
    from deerflow.models.factory import create_chat_model

    provider = manifest["provider_candidate"]
    configured = get_app_config().get_model_config(provider["profile"])
    if configured is None:
        raise Phase5AuthorizedRunnerError("config.yaml 缺少冻结 provider model")
    original_timeout = getattr(configured, "request_timeout", None)
    original_retries = getattr(configured, "max_retries", None)
    try:
        configured.request_timeout = float(provider["request_timeout_seconds"])
        configured.max_retries = provider["model_max_retries"]
        model = create_chat_model(
            name=provider["profile"],
            thinking_enabled=False,
            experiment_thread_id=experiment_thread_id,
            experiment_role="compiler" if experiment_thread_id else "system",
        )
    finally:
        configured.request_timeout = original_timeout
        configured.max_retries = original_retries
    if bool(getattr(model, "streaming", False)):
        raise Phase5AuthorizedRunnerError("冻结 provider 必须使用非 streaming 请求")
    return model


def _claim_marker(path: Path, *, document_type: str, digest: str, revision: str, task_id: str | None = None) -> None:
    payload = {
        "schema_version": "forge-agent-workflow-stage-b-calibration-attempt-1.0.0",
        "document_type": document_type,
        "manifest_sha256": digest,
        "release_revision": revision,
        "task_id": task_id,
        "status": "started",
        "error_class": None,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _write_once(path, payload)


def _finish_marker(path: Path, *, status: str, error_class: str | None = None) -> None:
    marker = _load_json(path)
    if marker.get("status") != "started":
        raise Phase5AuthorizedRunnerError("attempt marker 不处于 started")
    marker["status"] = status
    marker["error_class"] = error_class
    marker["updated_at"] = datetime.now(UTC).isoformat()
    _atomic_write(path, marker)


def execute_reachability(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    model_factory: Callable[[dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    preflight = collect_preflight(manifest, output_dir=output_dir, repo_root=repo_root, require_empty=True)
    digest = protocol.candidate.canonical_sha256(manifest)
    reachability = manifest["authorized_execution"]["reachability"]
    marker_path = output_dir / reachability["marker"]
    _claim_marker(marker_path, document_type="forge_agent_workflow_stage_b_reachability_attempt", digest=digest, revision=preflight["release_revision"])
    started = time.perf_counter()
    try:
        model = (model_factory or _create_provider_model)(manifest)
        response = model.invoke(reachability["prompt"])
        text = _response_text(response).strip()
        actual_model, usage = model_response_metadata(response)
        tokens = usage.get("total_tokens")
        passed = text == reachability["expected_response"] and actual_model == manifest["provider_candidate"]["profile"] and type(tokens) is int and 0 <= tokens <= reachability["maximum_recorded_tokens"]
        report = {
            "schema_version": "forge-agent-workflow-stage-b-reachability-1.0.0",
            "document_type": "forge_agent_workflow_stage_b_reachability",
            "manifest_sha256": digest,
            "release_revision": preflight["release_revision"],
            "provider": manifest["provider_candidate"]["provider"],
            "model": manifest["provider_candidate"]["profile"],
            "endpoint": manifest["provider_candidate"]["endpoint"],
            "network_access_medium": preflight["network_access_medium"],
            "request_count": 1,
            "recorded_tokens": tokens,
            "response_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "actual_model": actual_model,
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "passed": passed,
            "completed_at": datetime.now(UTC).isoformat(),
        }
        _write_once(output_dir / reachability["report"], report)
        if not passed:
            raise Phase5AuthorizedRunnerError("reachability 响应、模型 identity 或 token evidence 无效")
    except BaseException as exc:
        _finish_marker(marker_path, status="failed", error_class=type(exc).__name__)
        raise
    _finish_marker(marker_path, status="passed")
    return report


def require_passed_reachability(manifest: dict[str, Any], output_dir: Path, revision: str) -> dict[str, Any]:
    reachability = manifest["authorized_execution"]["reachability"]
    marker = _load_json(output_dir / reachability["marker"])
    report = _load_json(output_dir / reachability["report"])
    digest = protocol.candidate.canonical_sha256(manifest)
    if (
        marker.get("status") != "passed"
        or marker.get("manifest_sha256") != digest
        or marker.get("release_revision") != revision
        or report.get("passed") is not True
        or report.get("manifest_sha256") != digest
        or report.get("release_revision") != revision
        or type(report.get("recorded_tokens")) is not int
        or report["recorded_tokens"] > reachability["maximum_recorded_tokens"]
    ):
        raise Phase5AuthorizedRunnerError("唯一 reachability 未形成同 revision 通过终态")
    return report


def _task_by_id(manifest: dict[str, Any], task_id: str) -> dict[str, Any]:
    matches = [task for task in manifest["tasks"] if task["task_id"] == task_id]
    if len(matches) != 1:
        raise Phase5AuthorizedRunnerError(f"未知或重复 task: {task_id}")
    return matches[0]


def _experiment_policy(manifest: dict[str, Any], task: dict[str, Any]) -> ExperimentPolicy:
    provider = manifest["provider_candidate"]
    budget = manifest["budget_candidate"]["per_task"]
    return ExperimentPolicy(
        benchmark_id="forge-agent-workflow-stage-b-calibration-v1",
        manifest_sha256=protocol.candidate.canonical_sha256(manifest),
        case_id=task["task_id"],
        condition="agent-workflow-node-v1",
        repetition=1,
        expected_repo_url=task["repository_url"],
        expected_commit_sha=task["commit_sha"],
        expected_build_system=task["build_system"],
        compile_image=manifest["environment_candidate"]["compile_image"],
        image_id=manifest["environment_candidate"]["image_id"],
        model_name=provider["profile"],
        endpoint=provider["endpoint"],
        credential_env=provider["credential_env_name"],
        request_timeout_seconds=provider["request_timeout_seconds"],
        model_max_retries=provider["model_max_retries"],
        compiler_max_turns=budget["max_model_requests"],
        subagent_timeout_seconds=budget["node_timeout_seconds"],
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=(),
        cmake_arguments=(),
        configure_arguments=(),
        environment=(),
        minimum_replay_delay_seconds=0,
        compiler_model_turn_limit=budget["max_model_requests"],
        compiler_graph_recursion_limit=budget["max_agent_steps"],
        compiler_wall_clock_seconds=budget["node_timeout_seconds"],
        compiler_post_build_reserve_seconds=budget["cleanup_timeout_seconds"],
    )


def _node_input(manifest: dict[str, Any], task: dict[str, Any], session: Any, attempt_id: str) -> AgentBuildNodeInput:
    budget = manifest["budget_candidate"]["per_task"]
    target = task["target_contract"]
    frozen = manifest["frozen_authorized_components"]
    return AgentBuildNodeInput(
        task_id=task["task_id"],
        attempt_id=attempt_id,
        session_id=session.session_id,
        repository_url=task["repository_url"],
        commit_sha=task["commit_sha"],
        build_system_candidates=(task["build_system"],),
        target_contract=AgentWorkflowTargetContract(
            target_id=target["target_id"],
            artifact_types=tuple(target["artifact_types"]),
            artifact_path_patterns=tuple(target["artifact_path_patterns"]),
            functional_oracle_ref=target["functional_oracle_ref"],
        ),
        operation_policy_ref=manifest["operation_policy_ref"],
        environment=AgentWorkflowEnvironmentIdentity(
            image_id=manifest["environment_candidate"]["image_id"],
            parallel_jobs=manifest["environment_candidate"]["parallel_jobs"],
            network_policy=manifest["environment_candidate"]["network_policy"],
        ),
        budget=AgentWorkflowBudget(**budget),
        experiment_identity=AgentWorkflowExperimentIdentity(
            manifest_sha256=protocol.candidate.canonical_sha256(manifest),
            protocol_sha256=frozen[protocol.PROTOCOL_PATH],
            runner_sha256=frozen[protocol.RUNNER_PATH],
        ),
        initial_observation={
            "build_system": task["build_system"],
            "required_candidate_artifacts": task["required_candidate_artifacts"],
            "target_contract": task["target_contract"],
            "functional_oracle": task["oracle"],
        },
    )


def _oracle_spec(task: dict[str, Any]) -> FunctionalOracleSpec:
    oracle = task["oracle"]
    oracle_ref = task["target_contract"]["functional_oracle_ref"]
    if oracle["kind"] == "compile_and_run":
        suffix = ".c" if oracle["language"] == "c11" else ".cc"
        source_path = f"/workspace/forge-phase5-oracle-{task['task_id']}{suffix}"
        executable_path = f"/workspace/forge-phase5-oracle-{task['task_id']}"
        encoded = base64.b64encode(oracle["source"].encode("utf-8")).decode("ascii")
        compile_argv = [source_path if item == "{source}" else executable_path if item == "{executable}" else item for item in oracle["compile_argv"]]
        run_argv = [executable_path if item == "{executable}" else item for item in oracle["run_argv"]]
        script = f"printf %s {shlex.quote(encoded)} | base64 -d > {shlex.quote(source_path)} && {shlex.join(compile_argv)} && {shlex.join(run_argv)}"
        return FunctionalOracleSpec(oracle_ref=oracle_ref, argv=("sh", "-c", script), workdir="/workspace", timeout_seconds=120)
    if oracle["kind"] == "service_probe":
        start = shlex.join(oracle["start_argv"])
        url = f"{oracle['probe']['scheme']}://{oracle['listen_host']}:{oracle['listen_port']}{oracle['probe']['path']}"
        expected = str(oracle["probe"]["expected_status"])
        attempts = max(1, oracle["startup_timeout_seconds"] * 2)
        script = (
            f"{start} >/tmp/forge-phase5-uwebsockets.stdout 2>/tmp/forge-phase5-uwebsockets.stderr & pid=$!; "
            'cleanup() { if kill -0 "$pid" 2>/dev/null; then if kill "$pid" 2>/dev/null; then :; else :; fi; fi; '
            'if wait "$pid" 2>/dev/null; then :; else :; fi; }; trap cleanup EXIT; '
            f"i=0; while [ \"$i\" -lt {attempts} ]; do if status=$(curl -sS -o /dev/null -w '%{{http_code}}' {shlex.quote(url)}); then :; else status=; fi; "
            f'if [ "$status" = {shlex.quote(expected)} ]; then exit 0; fi; if kill -0 "$pid" 2>/dev/null; then :; else exit 1; fi; i=$((i+1)); sleep 0.5; done; exit 1'
        )
        return FunctionalOracleSpec(
            oracle_ref=oracle_ref,
            argv=("sh", "-c", script),
            workdir=oracle["workdir"],
            timeout_seconds=oracle["startup_timeout_seconds"] + 5,
        )
    raise Phase5AuthorizedRunnerError(f"不支持的 oracle kind: {oracle['kind']}")


def _candidate_path(session: Any, attempt_id: str) -> Path:
    return Path(session.metadata_path).parent / "agent-workflow" / attempt_id / "candidate.json"


def _safe_cleanup(session: Any) -> tuple[Any, Any]:
    finalized, cleanup = cleanup_and_finalize_compile_session_impl(session=session)
    require_zero_managed_resources()
    if not cleanup.succeeded or finalized.finalized_at is None:
        raise Phase5AuthorizedRunnerError("task cleanup 或 Session terminalization 未闭合")
    return finalized, cleanup


async def execute_task(
    manifest: dict[str, Any],
    task: dict[str, Any],
    *,
    release_revision: str,
    output_dir: Path,
    model_factory: Callable[[dict[str, Any], str], Any] | None = None,
) -> dict[str, Any]:
    digest = protocol.candidate.canonical_sha256(manifest)
    task_id = task["task_id"]
    attempt_id = f"phase5-{task_id}-attempt-1"
    thread_id = f"phase5-{task_id}-{digest[:12]}"
    task_dir = output_dir / "tasks" / task_id
    marker_path = task_dir / "attempt.json"
    result_path = task_dir / "result.json"
    _claim_marker(marker_path, document_type="forge_agent_workflow_stage_b_task_attempt", digest=digest, revision=release_revision, task_id=task_id)
    ledger = ExperimentLedger.create(
        task_dir / "experiment.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"manifest_sha256": digest, "release_revision": release_revision, "task_id": task_id},
    )
    services = get_compile_services()
    session = None
    active = False
    cleanup_succeeded = False
    started = time.perf_counter()
    try:
        activate_experiment(
            thread_id=thread_id,
            experiment_id=ledger.experiment_id,
            physical_attempt_id=ledger.physical_attempt_id,
            ledger=ledger,
            policy=_experiment_policy(manifest, task),
        )
        active = True
        session = prepare_compile_session_impl(
            thread_id=thread_id,
            repo_url=task["repository_url"],
            run_id=f"phase5-{task_id}-{uuid.uuid4().hex}",
            task_description=f"Phase 5 Stage B calibration: {task_id}",
        )
        clone, _message = clone_repository_impl(session=session, repo_url=task["repository_url"], depth=1, max_retries=1)
        if clone.exit_code != 0 or session.commit_sha != task["commit_sha"]:
            raise Phase5AuthorizedRunnerError(f"{task_id} 无法检出冻结 commit")
        primary, _detected, _suggested = inspect_build_system_impl(session=session)
        if primary != task["build_system"]:
            raise Phase5AuthorizedRunnerError(f"{task_id} build system identity 发生漂移")
        session.selected_build_system = primary
        services.manager.save_session(session)
        node_input = _node_input(manifest, task, session, attempt_id)
        model = model_factory(manifest, thread_id) if model_factory is not None else _create_provider_model(manifest, experiment_thread_id=thread_id)
        node_result = await run_agent_workflow_node_v1(node_input=node_input, session=session, manager=services.manager, model=model)
        evaluation = None
        if node_result.candidate_submitted:
            evaluation = run_external_evaluator_v1(
                node_input=node_input,
                node_result=node_result,
                session=session,
                manager=services.manager,
                candidate_path=_candidate_path(session, attempt_id),
                evaluation_id=f"phase5-{task_id}-evaluation-v1",
                backend=ForgeCompileEvaluationBackend(oracle_registry={task["target_contract"]["functional_oracle_ref"]: _oracle_spec(task)}),
            )
        finalized, cleanup = _safe_cleanup(session)
        cleanup_succeeded = True
        result = {
            "schema_version": "forge-agent-workflow-stage-b-task-result-1.0.0",
            "document_type": "forge_agent_workflow_stage_b_task_result",
            "manifest_sha256": digest,
            "release_revision": release_revision,
            "task_id": task_id,
            "attempt_id": attempt_id,
            "session_id": finalized.session_id,
            "session_status": finalized.status,
            "session_metadata_path": finalized.metadata_path,
            "candidate_generated_observed": node_result.candidate_generated_observed,
            "candidate_submitted": node_result.candidate_submitted,
            "node_status": node_result.node_status,
            "node_result": json.loads(node_result.canonical_json()),
            "s0_s5": [asdict(layer) for layer in evaluation.layers] if evaluation is not None else [],
            "strict_reproducible_build_success": evaluation.strict_reproducible_build_success if evaluation is not None else False,
            "bitwise_reproducible": evaluation.bitwise_reproducible if evaluation is not None else None,
            "evaluation_sha256": evaluation.canonical_sha256() if evaluation is not None else None,
            "recorded_tokens": node_result.usage.recorded_tokens,
            "cleanup_succeeded": cleanup.succeeded,
            "zero_managed_resources": True,
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "completed_at": datetime.now(UTC).isoformat(),
        }
        _write_once(result_path, result)
        ledger.append("experiment.completed", {"status": "passed", "task_result_sha256": protocol.candidate.file_sha256(result_path)})
    except BaseException as exc:
        if active:
            deactivate_experiment(thread_id)
            active = False
        if session is not None and not cleanup_succeeded:
            try:
                _safe_cleanup(session)
                cleanup_succeeded = True
            except Exception:
                cleanup_succeeded = False
        _finish_marker(marker_path, status="failed", error_class=type(exc).__name__)
        raise
    finally:
        if active:
            deactivate_experiment(thread_id)
    _finish_marker(marker_path, status="passed")
    return result


def _completed_prefix(manifest: dict[str, Any], output_dir: Path, revision: str) -> tuple[list[dict[str, Any]], int]:
    digest = protocol.candidate.canonical_sha256(manifest)
    completed: list[dict[str, Any]] = []
    gap_seen = False
    for index, task_id in enumerate(manifest["schedule"]["order"]):
        marker_path = output_dir / "tasks" / task_id / "attempt.json"
        result_path = output_dir / "tasks" / task_id / "result.json"
        if not marker_path.exists() and not result_path.exists():
            gap_seen = True
            continue
        if gap_seen or not marker_path.is_file() or not result_path.is_file():
            raise Phase5AuthorizedRunnerError("batch evidence 不是完整连续前缀")
        marker = _load_json(marker_path)
        result = _load_json(result_path)
        if (
            marker.get("status") != "passed"
            or marker.get("manifest_sha256") != digest
            or marker.get("release_revision") != revision
            or result.get("manifest_sha256") != digest
            or result.get("release_revision") != revision
            or result.get("task_id") != task_id
            or result.get("cleanup_succeeded") is not True
            or result.get("zero_managed_resources") is not True
        ):
            raise Phase5AuthorizedRunnerError(f"task evidence 未闭合: {task_id}")
        completed.append(result)
        if index != len(completed) - 1:
            raise Phase5AuthorizedRunnerError("batch task 顺序发生漂移")
    return completed, len(completed)


def _summarize(manifest: dict[str, Any], revision: str, reachability: dict[str, Any], outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    layers = {name: sum(any(layer["layer"] == name and layer["status"] == "passed" for layer in item["s0_s5"]) for item in outcomes) for name in ("S0", "S1", "S2", "S3", "S4", "S5")}
    return {
        "schema_version": "forge-agent-workflow-stage-b-calibration-report-1.0.0",
        "document_type": "forge_agent_workflow_stage_b_calibration_report",
        "manifest_sha256": protocol.candidate.canonical_sha256(manifest),
        "release_revision": revision,
        "purpose": manifest["purpose"],
        "unbiased_success_rate_claim_allowed": False,
        "task_order": manifest["schedule"]["order"],
        "task_count": len(outcomes),
        "candidate_generated": sum(item["candidate_generated_observed"] is True for item in outcomes),
        "candidate_submitted": sum(item["candidate_submitted"] is True for item in outcomes),
        "strict_success": sum(item["strict_reproducible_build_success"] is True for item in outcomes),
        "bitwise_reproducible": sum(item["bitwise_reproducible"] is True for item in outcomes),
        "s0_s5_passed": layers,
        "reachability_recorded_tokens": reachability["recorded_tokens"],
        "batch_recorded_tokens": sum(item["recorded_tokens"] for item in outcomes),
        "outcomes": outcomes,
        "historical_baseline": manifest["historical_baseline"]["audit"],
        "zero_managed_resources": True,
        "historical_evidence_mutated": False,
        "completed_at": datetime.now(UTC).isoformat(),
    }


async def run_batch_async(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    task_executor: Callable[..., Any] = execute_task,
) -> dict[str, Any]:
    preflight = collect_preflight(manifest, output_dir=output_dir, repo_root=repo_root, require_empty=False)
    revision = preflight["release_revision"]
    reachability = require_passed_reachability(manifest, output_dir, revision)
    completed, next_index = _completed_prefix(manifest, output_dir, revision)
    digest = protocol.candidate.canonical_sha256(manifest)
    marker_path = output_dir / manifest["authorized_execution"]["batch_marker"]
    if marker_path.exists():
        marker = _load_json(marker_path)
        if marker.get("status") != "started" or marker.get("manifest_sha256") != digest or marker.get("release_revision") != revision:
            raise Phase5AuthorizedRunnerError("batch marker 无法恢复")
    else:
        _claim_marker(marker_path, document_type="forge_agent_workflow_stage_b_batch_attempt", digest=digest, revision=revision)
    try:
        for task_id in manifest["schedule"]["order"][next_index:]:
            used = sum(item["recorded_tokens"] for item in completed)
            ceiling = manifest["budget_candidate"]["batch_max_recorded_tokens"]
            if used >= ceiling:
                raise Phase5AuthorizedRunnerError("batch token ceiling 已耗尽")
            task = _task_by_id(manifest, task_id)
            outcome = task_executor(manifest, task, release_revision=revision, output_dir=output_dir)
            if hasattr(outcome, "__await__"):
                outcome = await outcome
            completed.append(outcome)
            if sum(item["recorded_tokens"] for item in completed) > ceiling:
                raise Phase5AuthorizedRunnerError("batch recorded tokens 超过冻结上限")
            require_zero_managed_resources()
        report = _summarize(manifest, revision, reachability, completed)
        _write_once(output_dir / manifest["authorized_execution"]["batch_report"], report)
        decision = {
            "schema_version": "forge-agent-workflow-stage-c-decision-package-1.0.0",
            "document_type": "forge_agent_workflow_stage_c_decision_package",
            "manifest_sha256": digest,
            "release_revision": revision,
            "phase5_complete": len(completed) == len(manifest["tasks"]),
            "stage_c_authorized": False,
            "required_next_action": "review_phase5_results_before_stage_c_protocol",
            "report_sha256": protocol.candidate.file_sha256(output_dir / manifest["authorized_execution"]["batch_report"]),
            "completed_at": datetime.now(UTC).isoformat(),
        }
        _write_once(output_dir / manifest["authorized_execution"]["stage_c_decision_package"], decision)
    except BaseException as exc:
        _finish_marker(marker_path, status="failed", error_class=type(exc).__name__)
        raise
    _finish_marker(marker_path, status="passed")
    return report


def run_batch(manifest: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return asyncio.run(run_batch_async(manifest, **kwargs))


def load_report(manifest: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    report = _load_json(output_dir / manifest["authorized_execution"]["batch_report"])
    if report.get("manifest_sha256") != protocol.candidate.canonical_sha256(manifest):
        raise Phase5AuthorizedRunnerError("Phase 5 report identity 发生漂移")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "preflight", "reachability", "batch", "report"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest(args.manifest)
    if args.command == "validate":
        result: Any = protocol.validate_allowed_delta(manifest)
    elif args.command == "preflight":
        result = collect_preflight(manifest, output_dir=args.output_dir, require_empty=not args.output_dir.exists())
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
