#!/usr/bin/env python3
"""Issue #149 failure checkpoint primary canary 协议与执行器。"""

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
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", SCRIPT_ROOT.parent)).resolve()
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_budget_checkpoint_prototype as budget_checkpoint  # noqa: E402
import forge_controlled_fault_v1_gate as controlled_fault  # noqa: E402
import forge_real_lifecycle_checkpoint_gate as lifecycle  # noqa: E402
import forge_verifier_repair_runtime as repair_runtime  # noqa: E402

from deerflow.compile.evidence import (  # noqa: E402
    ExperimentAttemptBudget,
    ExperimentLedger,
    ExperimentPolicy,
    activate_experiment,
    deactivate_experiment,
    model_response_metadata,
    new_evidence_id,
    record_experiment_attempt_budget_completion,
)

SCHEMA_VERSION = "forge-checkpoint-primary-canary-authorized-1.0.0"
DOCUMENT_TYPE = "forge_checkpoint_primary_canary_authorized"
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "benchmarks"
    / "manifests"
    / "cpp-verifier-checkpoint-primary-canary-authorized.json"
)
DEFAULT_OUTPUT_DIR = Path(
    "/workspace/.compile-sessions/benchmark-evidence-checkpoint-primary-canary"
)
REACHABILITY_MARKER = "reachability-attempt.json"
PAIR_MARKER = "controlled-pair-attempt.json"
NETWORK_MEDIA = {"mobile_hotspot", "wifi", "ethernet", "other"}
ARMS = ("baseline", "treatment")
COMPILE_IMAGE = "autocompiler:gcc13"
CASE_ID = "cppitertools"
REPOSITORY_URL = "https://github.com/ryanhaining/cppitertools"
COMMIT_SHA = "531b3d753d2bbfe3b0ababe61c2e95e965c54a66"
BUILD_OUTPUT = "build/accumulate_examples"
STAGED_ARTIFACT = "accumulate_examples"
_MISSING = object()


class CanaryError(RuntimeError):
    """canary 协议、身份或执行门禁失败。"""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanaryError("无法读取 checkpoint primary canary manifest") from exc
    return validate_manifest(value)


def validate_manifest(value: Any) -> dict[str, Any]:
    required = {
        "schema_version",
        "document_type",
        "scope",
        "provider",
        "fault",
        "continuation",
        "budget",
        "stopping",
        "execution",
        "parent_candidate",
        "protocol_artifacts",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise CanaryError("授权 manifest 字段集合不匹配")
    if (
        value["schema_version"] != SCHEMA_VERSION
        or value["document_type"] != DOCUMENT_TYPE
    ):
        raise CanaryError("授权 manifest 协议身份不匹配")
    if value["scope"] != {
        "provider_canary_authorized": True,
        "mechanism_canary_authorized": True,
        "pilot_collection_authorized": False,
        "natural_collection_authorized": False,
        "secondary_provider_authorized": False,
    }:
        raise CanaryError("授权范围发生漂移")
    if value["provider"] != {
        "id": "deepseek-v4-flash",
        "endpoint": "https://api.deepseek.com",
        "credential_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-v4-flash",
        "request_timeout_seconds": 300,
        "max_retries": 0,
        "fallback": "forbidden",
    }:
        raise CanaryError("primary provider 身份或请求策略发生漂移")
    if value["fault"] != {
        "version": "controlled-fault-v1",
        "family": "artifact_staging_missing",
        "expected_classification": "candidate_verification_failed",
        "capture_point": "after-neutral-tool-message-before-continuation",
        "replay_attempts_required": 0,
    }:
        raise CanaryError("controlled fault 身份发生漂移")
    if value["continuation"] != {
        "checkpoint_pairs": 1,
        "arms_per_pair": 2,
        "arm_order": ["baseline", "treatment"],
        "maximum_requests_per_arm": 8,
        "maximum_model_turns_per_arm": 8,
        "maximum_graph_steps_per_arm": 24,
        "work_wall_clock_seconds_per_arm": 600,
        "cleanup_reserve_seconds_per_arm": 120,
        "maximum_recorded_tokens_per_arm": 120000,
    }:
        raise CanaryError("continuation 配对或预算发生漂移")
    if value["budget"] != {
        "reachability_requests": 1,
        "reachability_expected_tokens": 5000,
        "reachability_maximum_tokens": 5000,
        "mechanism_canary_expected_tokens": 120000,
        "mechanism_canary_maximum_tokens": 240000,
        "stage_expected_tokens": 125000,
        "stage_maximum_tokens": 245000,
    }:
        raise CanaryError("阶段 token 上限发生漂移")
    stopping = value["stopping"]
    if stopping != {
        "provider_timeout_stops_canary": True,
        "incomplete_pair_stops_canary": True,
        "cleanup_or_identity_failure_stops_canary": True,
        "retry_forbidden": True,
        "replacement_forbidden": True,
        "backfill_forbidden": True,
        "canary_pass_does_not_authorize_pilot": True,
    }:
        raise CanaryError("停止规则发生漂移")
    execution = value["execution"]
    if execution != {
        "control_plane": "compose-dood-on-ubuntu-native-docker",
        "network_access_medium_env": "FORGE_NETWORK_ACCESS_MEDIUM",
        "evidence_directory": str(DEFAULT_OUTPUT_DIR),
        "release_branch": "main",
        "require_clean_worktree": True,
        "require_origin_main_identity": True,
    }:
        raise CanaryError("执行拓扑或 release identity 规则发生漂移")
    parent = value["parent_candidate"]
    if (
        set(parent) != {"path", "sha256"}
        or parent["path"]
        != "benchmarks/manifests/cpp-verifier-checkpoint-primary-canary-candidate.json"
    ):
        raise CanaryError("未授权候选的父身份无效")
    artifacts = value["protocol_artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise CanaryError("协议制品列表为空")
    paths: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
            raise CanaryError("协议制品身份无效")
        path = artifact["path"]
        digest = artifact["sha256"]
        if (
            not isinstance(path, str)
            or not path
            or path.startswith(("/", "\\"))
            or ".." in Path(path).parts
        ):
            raise CanaryError("协议制品路径不安全")
        if path in paths or not isinstance(digest, str) or len(digest) != 64:
            raise CanaryError("协议制品路径重复或 hash 无效")
        paths.add(path)
    return value


def verify_frozen_artifacts(
    manifest: dict[str, Any], repo_root: Path = REPO_ROOT
) -> None:
    parent = manifest["parent_candidate"]
    parent_path = repo_root / parent["path"]
    if not parent_path.is_file() or file_sha256(parent_path) != parent["sha256"]:
        raise CanaryError("未授权候选 manifest 发生漂移")
    for artifact in manifest["protocol_artifacts"]:
        path = repo_root / artifact["path"]
        if not path.is_file() or file_sha256(path) != artifact["sha256"]:
            raise CanaryError(f"协议制品发生漂移: {artifact['path']}")


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
        raise CanaryError("无法验证 release Git identity")
    return result.stdout.strip()


def require_release_identity(
    manifest: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, str]:
    verify_frozen_artifacts(manifest, repo_root)
    branch = _git(repo_root, "branch", "--show-current")
    revision = _git(repo_root, "rev-parse", "HEAD")
    origin_main = _git(repo_root, "rev-parse", "origin/main")
    dirty = _git(repo_root, "status", "--porcelain", "--untracked-files=normal")
    if branch != manifest["execution"]["release_branch"]:
        raise CanaryError("真实 provider 只能在授权内容合并后的 main 分支运行")
    if revision != origin_main:
        raise CanaryError("HEAD 与 origin/main 不一致，禁止真实 provider")
    if dirty:
        raise CanaryError("工作树不干净，禁止真实 provider")
    return {"branch": branch, "revision": revision, "origin_main": origin_main}


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _claim_marker(
    path: Path, *, kind: str, manifest_sha256: str, revision: str
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {
        "schema_version": "forge-checkpoint-primary-canary-attempt-1.0.0",
        "document_type": kind,
        "manifest_sha256": manifest_sha256,
        "release_revision": revision,
        "status": "started",
        "error_class": None,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
    except FileExistsError as exc:
        raise CanaryError("该阶段唯一一次授权尝试已被消耗") from exc


def _finish_marker(path: Path, *, status: str, error_class: str | None = None) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    value.update(
        status=status,
        error_class=error_class,
        updated_at=datetime.now(UTC).isoformat(),
    )
    _atomic_write(path, value)


def _network_medium(manifest: dict[str, Any]) -> str:
    name = manifest["execution"]["network_access_medium_env"]
    medium = os.environ.get(name)
    if medium not in NETWORK_MEDIA:
        raise CanaryError(f"必须先通过 {name} 确认当前网络介质")
    return medium


def require_authorized_output_dir(manifest: dict[str, Any], output_dir: Path) -> None:
    expected = Path(manifest["execution"]["evidence_directory"]).resolve(strict=False)
    if output_dir.resolve(strict=False) != expected:
        raise CanaryError("canary evidence 必须写入冻结的授权目录")


def require_compose_dood() -> None:
    if not Path("/.dockerenv").is_file():
        raise CanaryError("canary 必须在 Forge Compose/DooD runtime 内运行")
    container_id = os.environ.get("HOSTNAME", "").strip()
    if not container_id:
        raise CanaryError("无法识别当前 Forge runtime container")
    result = subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            "{{json .Config.Labels}}|{{json .Mounts}}",
            container_id,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0 or "|" not in result.stdout:
        raise CanaryError("无法验证 Compose/DooD topology")
    labels_raw, mounts_raw = result.stdout.strip().split("|", 1)
    try:
        labels = json.loads(labels_raw)
        mounts = json.loads(mounts_raw)
    except json.JSONDecodeError as exc:
        raise CanaryError("Compose/DooD identity 不是有效 JSON") from exc
    socket_rw = any(
        isinstance(mount, dict)
        and mount.get("Destination") == "/var/run/docker.sock"
        and mount.get("RW") is True
        for mount in mounts
    )
    if (
        not isinstance(labels, dict)
        or labels.get("com.docker.compose.project") != "deer-flow-dev"
        or labels.get("com.docker.compose.service") not in {"langgraph", "gateway"}
        or not socket_rw
    ):
        raise CanaryError("当前进程不在冻结的 Compose/DooD control plane")


def host_snapshot_root(local_snapshot_root: Path) -> str:
    local_sessions = Path("/workspace/.compile-sessions")
    try:
        relative = local_snapshot_root.resolve(strict=False).relative_to(local_sessions)
    except ValueError as exc:
        raise CanaryError(
            "checkpoint snapshot 必须位于共享 compile-sessions mount"
        ) from exc
    project_root = os.environ.get("HOST_PROJECT_ROOT")
    if not project_root:
        raise CanaryError("HOST_PROJECT_ROOT 未注入，无法建立 DooD snapshot bind")
    return str(Path(project_root) / ".compile-sessions" / relative)


def _response_text(response: Any) -> str:
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "".join(
        item if isinstance(item, str) else str(item.get("text", ""))
        for item in content
        if isinstance(item, (str, dict))
    )


def _restore_config_value(configured: Any, name: str, value: Any) -> None:
    if value is _MISSING:
        try:
            delattr(configured, name)
        except AttributeError:
            pass
        return
    setattr(configured, name, value)


def _create_provider_model(
    provider: dict[str, Any], *, experiment_thread_id: str | None = None
):
    from deerflow.config import get_app_config
    from deerflow.models.factory import create_chat_model

    configured = get_app_config().get_model_config(provider["id"])
    if configured is None or configured.model != provider["model"]:
        raise CanaryError("config.yaml 中缺少冻结的 primary model 配置")
    settings = configured.model_dump(exclude_none=True)
    endpoint = settings.get("base_url", settings.get("openai_api_base"))
    if endpoint is None or str(endpoint).rstrip("/") != provider["endpoint"]:
        raise CanaryError("config.yaml 中的 primary endpoint 与授权不一致")
    if not os.environ.get(provider["credential_env"]):
        raise CanaryError("primary provider 凭据环境变量未注入")
    original_timeout = getattr(configured, "request_timeout", _MISSING)
    original_retries = getattr(configured, "max_retries", _MISSING)
    try:
        configured.request_timeout = float(provider["request_timeout_seconds"])
        configured.max_retries = provider["max_retries"]
        model = create_chat_model(
            name=provider["id"],
            thinking_enabled=False,
            experiment_thread_id=experiment_thread_id,
            experiment_role="compiler" if experiment_thread_id else "system",
        )
    finally:
        _restore_config_value(configured, "request_timeout", original_timeout)
        _restore_config_value(configured, "max_retries", original_retries)
    try:
        effective_timeout = float(model.request_timeout)
        effective_retries = int(model.max_retries)
    except (AttributeError, TypeError, ValueError) as exc:
        raise CanaryError("provider model 未暴露有效请求策略") from exc
    if (
        effective_timeout != provider["request_timeout_seconds"]
        or effective_retries != 0
    ):
        raise CanaryError("provider model 未应用 300 秒/0 retry 策略")
    return model


def run_reachability(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    model_factory: Callable[[dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    validate_manifest(manifest)
    require_authorized_output_dir(manifest, output_dir)
    release = require_release_identity(manifest, repo_root)
    medium = _network_medium(manifest)
    require_compose_dood()
    marker = output_dir / "markers" / REACHABILITY_MARKER
    manifest_digest = canonical_sha256(manifest)
    _claim_marker(
        marker,
        kind="forge_checkpoint_primary_reachability_attempt",
        manifest_sha256=manifest_digest,
        revision=release["revision"],
    )
    try:
        provider = manifest["provider"]
        model = (model_factory or _create_provider_model)(provider)
        started = time.perf_counter()
        response = model.invoke("Reply with exactly CANARY_OK and nothing else.")
        duration_ms = round((time.perf_counter() - started) * 1000)
        text = _response_text(response).strip()
        actual_model, token_usage = model_response_metadata(response)
        total_tokens = token_usage.get("total_tokens")
        passed = (
            text == "CANARY_OK"
            and actual_model == provider["model"]
            and type(total_tokens) is int
            and 0 <= total_tokens <= manifest["budget"]["reachability_maximum_tokens"]
        )
        report = {
            "schema_version": "forge-checkpoint-primary-reachability-1.0.0",
            "document_type": "forge_checkpoint_primary_reachability",
            "manifest_sha256": manifest_digest,
            "release_revision": release["revision"],
            "provider": provider["id"],
            "endpoint": provider["endpoint"],
            "credential_env": provider["credential_env"],
            "network_access_medium": medium,
            "request_count": 1,
            "request_timeout_seconds": provider["request_timeout_seconds"],
            "max_retries": provider["max_retries"],
            "duration_ms": duration_ms,
            "response_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "actual_model": actual_model,
            "recorded_tokens": total_tokens,
            "passed": passed,
            "completed_at": datetime.now(UTC).isoformat(),
        }
        report_path = output_dir / "reports" / "reachability.json"
        _atomic_write(report_path, report)
        if not passed:
            raise CanaryError("reachability 响应、actual model 或 token 门禁失败")
    except BaseException as exc:
        _finish_marker(marker, status="failed", error_class=type(exc).__name__)
        raise
    _finish_marker(marker, status="passed")
    return {**report, "report_path": str(report_path)}


def require_passed_reachability(
    manifest: dict[str, Any], output_dir: Path, revision: str
) -> dict[str, Any]:
    marker_path = output_dir / "markers" / REACHABILITY_MARKER
    report_path = output_dir / "reports" / "reachability.json"
    if not marker_path.is_file() or not report_path.is_file():
        raise CanaryError("controlled pair 前缺少通过的 reachability 证据")
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    expected = canonical_sha256(manifest)
    if marker.get("status") != "passed" or report.get("passed") is not True:
        raise CanaryError("reachability 未通过")
    if (
        marker.get("manifest_sha256") != expected
        or report.get("manifest_sha256") != expected
    ):
        raise CanaryError("reachability manifest identity 发生漂移")
    if (
        marker.get("release_revision") != revision
        or report.get("release_revision") != revision
    ):
        raise CanaryError("reachability 与 controlled pair 的 release revision 不一致")
    return report


def _budget_manifest(capture_id: str, _message_sha256: str) -> dict[str, Any]:
    return budget_checkpoint.build_manifest(
        checkpoint_id=capture_id,
        limits={
            "provider_requests": 8,
            "compiler_invocations": 1,
            "compiler_model_turns": 8,
            "graph_recursion_steps": 24,
            "attempt_wall_clock_seconds": 720,
            "attempt_cleanup_reserve_seconds": 120,
            "compiler_wall_clock_seconds": 600,
            "compiler_post_build_reserve_seconds": 120,
            "post_build_commands": 2,
        },
        consumed_before_capture={
            "provider_requests": 0,
            "compiler_invocations": 0,
            "compiler_model_turns": 0,
            "graph_recursion_steps": 0,
            "attempt_wall_clock_seconds": 0,
            "compiler_wall_clock_seconds": 0,
            "post_build_commands": 0,
            "tokens": 0,
        },
        post_build_started=True,
    )


def _arm_plan(capture_id: str) -> dict[str, dict[str, str]]:
    return {
        arm: {
            "thread_id": f"{arm}-{capture_id}-thread",
            "session_id": f"{arm}-{capture_id}-session",
            "environment_id": f"{arm}-{capture_id}-environment",
        }
        for arm in ARMS
    }


def _record_command(
    *, manager: Any, runtime: Any, session: Any, command: str, role: str
) -> Any:
    from deerflow.compile.schemas import BuildCommandRecord, utc_now_iso

    started_at = utc_now_iso()
    started = time.monotonic()
    result = runtime.exec(
        session,
        command,
        workdir="/workspace/repo",
        timeout_seconds=300,
    )
    record = BuildCommandRecord(
        stage="bash",
        command=command,
        workdir="/workspace/repo",
        role=role,
        exit_code=result.exit_code,
        started_at=started_at,
        completed_at=utc_now_iso(),
        timeout_seconds=300,
        duration_seconds=round(time.monotonic() - started, 6),
        timed_out=result.exit_code == 124,
        termination=(
            "timeout"
            if result.exit_code == 124
            else ("failed" if result.exit_code != 0 else "completed")
        ),
    )
    manager.record_command(session, record)
    manager.save_session(session)
    if result.exit_code != 0:
        raise CanaryError(f"controlled checkpoint 前置命令失败: {role}")
    return record


def _policy(
    manifest: dict[str, Any],
    *,
    arm: str,
    image_id: str,
) -> ExperimentPolicy:
    continuation = manifest["continuation"]
    provider = manifest["provider"]
    return ExperimentPolicy(
        benchmark_id="forge-checkpoint-primary-canary",
        manifest_sha256=canonical_sha256(manifest),
        case_id=CASE_ID,
        condition=arm,
        repetition=1,
        expected_repo_url=REPOSITORY_URL,
        expected_commit_sha=COMMIT_SHA,
        expected_build_system="cmake",
        compile_image=COMPILE_IMAGE,
        image_id=image_id,
        model_name=provider["model"],
        endpoint=provider["endpoint"],
        credential_env=provider["credential_env"],
        request_timeout_seconds=provider["request_timeout_seconds"],
        model_max_retries=provider["max_retries"],
        compiler_max_turns=continuation["maximum_model_turns_per_arm"],
        subagent_timeout_seconds=continuation["work_wall_clock_seconds_per_arm"],
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=(),
        cmake_arguments=("-DCMAKE_BUILD_TYPE=Release",),
        configure_arguments=(),
        environment=(),
        minimum_replay_delay_seconds=0,
        compiler_model_turn_limit=continuation["maximum_model_turns_per_arm"],
        compiler_graph_recursion_limit=continuation["maximum_graph_steps_per_arm"],
        compiler_wall_clock_seconds=continuation["work_wall_clock_seconds_per_arm"],
        compiler_post_build_reserve_seconds=continuation[
            "cleanup_reserve_seconds_per_arm"
        ],
        source_subdir="examples",
        build_targets=("accumulate_examples",),
        artifact_instructions=((STAGED_ARTIFACT, BUILD_OUTPUT, "executable"),),
    )


def _recorded_tokens(events: Sequence[dict[str, Any]]) -> int:
    total = 0
    for event in events:
        if event.get("event") != "model.request_completed":
            continue
        usage = event.get("payload", {}).get("token_usage")
        value = usage.get("total_tokens") if isinstance(usage, dict) else None
        if type(value) is not int or value < 0:
            raise CanaryError("model completion 缺少有效 token usage")
        total += value
    return total


def validate_arm_evidence(
    manifest: dict[str, Any],
    *,
    arm: str,
    ledger: ExperimentLedger,
    session: Any,
) -> dict[str, Any]:
    events = ledger.read()
    started = [event for event in events if event["event"] == "model.request_started"]
    completed = [
        event for event in events if event["event"] == "model.request_completed"
    ]
    failed = [
        event
        for event in events
        if event["event"] in {"model.request_failed", "model.request_cancelled"}
    ]
    maximum_requests = manifest["continuation"]["maximum_requests_per_arm"]
    if (
        not completed
        or len(started) != len(completed)
        or len(completed) > maximum_requests
        or failed
    ):
        raise CanaryError(f"{arm} arm 的模型请求证据不完整")
    provider = manifest["provider"]
    if any(
        event["payload"].get("configured_model") != provider["model"]
        or event["payload"].get("observed_endpoint") != provider["endpoint"]
        or event["payload"].get("request_timeout_seconds")
        != provider["request_timeout_seconds"]
        or event["payload"].get("provider_max_retries") != 0
        for event in started
    ):
        raise CanaryError(f"{arm} arm 的请求 policy identity 发生漂移")
    if any(
        event["payload"].get("actual_model") != provider["model"] for event in completed
    ):
        raise CanaryError(f"{arm} arm 的 actual model 缺失或漂移")
    tokens = _recorded_tokens(events)
    if tokens > manifest["continuation"]["maximum_recorded_tokens_per_arm"]:
        raise CanaryError(f"{arm} arm 超过 recorded-token 上限")
    if (
        session.status != "verified"
        or session.verification is None
        or session.verification.status != "passed"
    ):
        raise CanaryError(f"{arm} arm 未形成通过的 candidate + clean replay")
    return {
        "arm": arm,
        "status": "passed",
        "physical_attempt_id": ledger.physical_attempt_id,
        "model_requests": len(completed),
        "recorded_tokens": tokens,
        "actual_model": provider["model"],
        "session_status": session.status,
        "replay_attempts": len(session.replay_attempts),
        "ledger_head_sha256": events[-1]["event_sha256"],
    }


async def run_arm_continuation(
    manifest: dict[str, Any],
    *,
    arm: str,
    lifecycle_arm: Any,
    message_state: dict[str, Any],
    ledger: ExperimentLedger,
    model_factory: Callable[[dict[str, Any], str], Any] | None = None,
) -> dict[str, Any]:
    from langchain.agents import create_agent
    from langgraph.checkpoint.memory import InMemorySaver

    from deerflow.agents.middlewares.tool_error_handling_middleware import (
        build_subagent_runtime_middlewares,
    )
    from deerflow.agents.thread_state import ThreadState
    from deerflow.subagents.builtins.compiler_agent import COMPILER_AGENT_CONFIG
    from deerflow.tools.bound_compile_tools import get_bound_compile_tools

    if arm not in ARMS:
        raise CanaryError("unknown checkpoint arm")
    session = lifecycle_arm.session
    policy = _policy(manifest, arm=arm, image_id=session.image_id)
    budget = ExperimentAttemptBudget(
        total_wall_clock_seconds=720,
        cleanup_reserve_seconds=120,
        max_compiler_invocations=1,
        max_model_requests=manifest["continuation"]["maximum_requests_per_arm"],
    )
    activate_experiment(
        thread_id=session.thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=policy,
        attempt_budget=budget,
    )
    try:
        model = (
            model_factory(manifest["provider"], session.thread_id)
            if model_factory is not None
            else _create_provider_model(
                manifest["provider"], experiment_thread_id=session.thread_id
            )
        )
        tools = get_bound_compile_tools(session)
        run_tool = next(tool for tool in tools if tool.name == "run_container_bash")
        submit_tool = next(tool for tool in tools if tool.name == "submit_build_result")

        from langchain_core.tools import tool

        @tool("run_container_bash", parse_docstring=True)
        def bounded_run_container_bash(
            command: str,
            timeout_seconds: int = 300,
            workdir: str | None = None,
            command_role: str = "other",
        ) -> str:
            """在当前 arm 容器中执行有界构建命令。

            Args:
                command: 要执行的 bash 命令。
                timeout_seconds: 单条命令超时，最多 300 秒。
                workdir: 容器内工作目录。
                command_role: evidence 命令角色。
            """
            return run_tool.invoke(
                {
                    "command": command,
                    "timeout_seconds": min(300, max(1, timeout_seconds)),
                    "workdir": workdir,
                    "command_role": command_role,
                }
            )

        @tool("submit_build_result", parse_docstring=True)
        def bounded_submit_build_result(
            supporting_command_id: str | None = None,
        ) -> str:
            """提交当前 arm 的 staged artifacts。

            Args:
                supporting_command_id: 可选的成功构建命令 ID。
            """
            return submit_tool.invoke({"supporting_command_id": supporting_command_id})

        agent = create_agent(
            model=model,
            tools=[bounded_run_container_bash, bounded_submit_build_result],
            middleware=build_subagent_runtime_middlewares(lazy_init=True),
            system_prompt=COMPILER_AGENT_CONFIG.system_prompt,
            state_schema=ThreadState,
            checkpointer=InMemorySaver(),
        )
        messages = message_state["messages"]
        state = {
            "messages": messages,
            "artifacts": [],
            "viewed_images": {},
        }
        config = {
            "configurable": {"thread_id": session.thread_id},
            "recursion_limit": manifest["continuation"]["maximum_graph_steps_per_arm"],
        }
        await asyncio.wait_for(
            agent.ainvoke(
                state,
                config=config,
                context={"thread_id": session.thread_id, "agent_name": "compiler"},
            ),
            timeout=manifest["continuation"]["work_wall_clock_seconds_per_arm"],
        )
        record_experiment_attempt_budget_completion(session.thread_id)
    finally:
        deactivate_experiment(session.thread_id)
    from deerflow.compile.operations import get_compile_services

    authoritative = get_compile_services().manager.load_session(
        session.session_id, session.thread_id
    )
    result = validate_arm_evidence(
        manifest,
        arm=arm,
        ledger=ledger,
        session=authoritative,
    )
    ledger.append("experiment.completed", {"status": "passed"})
    return result


def _message_state(gate: Any, lifecycle_arm: Any) -> dict[str, Any]:
    snapshot = gate.message_runtime.graph.get_state(lifecycle_arm.message_config)
    if tuple(snapshot.next) != (lifecycle.CONTINUATION_NODE,):
        raise CanaryError("arm message checkpoint 不可 continuation")
    return snapshot.values


def run_controlled_pair(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    model_factory: Callable[[dict[str, Any], str], Any] | None = None,
) -> dict[str, Any]:
    from langgraph.checkpoint.sqlite import SqliteSaver

    from deerflow.compile import operations
    from deerflow.compile.paths import (
        get_host_artifacts_dir,
        get_host_logs_dir,
        get_host_repro_dir,
        get_host_workspace_dir,
    )

    validate_manifest(manifest)
    require_authorized_output_dir(manifest, output_dir)
    release = require_release_identity(manifest, repo_root)
    medium = _network_medium(manifest)
    require_compose_dood()
    reachability = require_passed_reachability(
        manifest, output_dir, release["revision"]
    )
    marker = output_dir / "markers" / PAIR_MARKER
    manifest_digest = canonical_sha256(manifest)
    _claim_marker(
        marker,
        kind="forge_checkpoint_primary_controlled_pair_attempt",
        manifest_sha256=manifest_digest,
        revision=release["revision"],
    )

    capture_id = f"primary-canary-{uuid.uuid4().hex[:12]}"
    services = operations.get_compile_services()
    manager = services.manager
    runtime = services.runtime
    docker = lifecycle.environment_checkpoint.DockerCLI()
    snapshot = output_dir / "checkpoint" / capture_id
    parent = manager.create_session(
        thread_id=f"parent-{uuid.uuid4().hex[:12]}",
        session_id=f"parent-{uuid.uuid4().hex[:12]}",
        run_id=f"run-{uuid.uuid4().hex[:12]}",
        repo_url=REPOSITORY_URL,
        image=COMPILE_IMAGE,
    )
    parent_ledger = ExperimentLedger.create(
        output_dir / "ledgers" / "parent.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("mechanism_attempt"),
        context={
            "scope": "checkpoint-primary-controlled-parent",
            "manifest_sha256": manifest_digest,
            "thread_id": parent.thread_id,
        },
    )
    gate = None
    parent_active = False
    repair_packet: dict[str, Any] | None = None
    arm_results: list[dict[str, Any]] = []
    cleanup_succeeded = False
    try:
        Path(parent.leadagent_repo_dir).mkdir(parents=True, exist_ok=True)
        runtime.create_container(parent)
        manager.save_session(parent)
        clone = runtime.exec(
            parent,
            "git config --global --add safe.directory /workspace/repo && "
            "git init . && "
            "git remote add origin https://github.com/ryanhaining/cppitertools && "
            f"git fetch --depth 1 origin {COMMIT_SHA} && "
            "git checkout --detach FETCH_HEAD",
            workdir="/workspace/repo",
            timeout_seconds=180,
        )
        if clone.exit_code != 0:
            raise CanaryError("controlled parent 无法检出冻结 commit")
        parent.commit_sha = COMMIT_SHA
        parent.build_system = "cmake"
        parent.build_system_capabilities = ["cmake"]
        parent.selected_build_system = "cmake"
        parent.status = "inspected"
        manager.save_session(parent)
        _record_command(
            manager=manager,
            runtime=runtime,
            session=parent,
            command="cmake -S examples -B build -DCMAKE_BUILD_TYPE=Release",
            role="configure",
        )
        supporting = _record_command(
            manager=manager,
            runtime=runtime,
            session=parent,
            command="cmake --build build --target accumulate_examples -j2",
            role="build",
        )
        from deerflow.compile.schemas import utc_now_iso

        parent.post_build_supporting_command_id = supporting.command_id
        parent.post_build_started_at = utc_now_iso()
        parent.post_build_commands_remaining = 2
        manager.save_session(parent)
        _record_command(
            manager=manager,
            runtime=runtime,
            session=parent,
            command="cp build/accumulate_examples /artifacts/accumulate_examples",
            role="artifact_stage",
        )
        parent_policy = ExperimentPolicy(
            benchmark_id="forge-checkpoint-primary-canary",
            manifest_sha256=manifest_digest,
            case_id=CASE_ID,
            condition="controlled-parent",
            repetition=1,
            expected_repo_url=REPOSITORY_URL,
            expected_commit_sha=COMMIT_SHA,
            expected_build_system="cmake",
            compile_image=COMPILE_IMAGE,
            image_id=parent.image_id,
            model_name="deterministic-no-provider",
            endpoint="https://example.invalid/v1",
            credential_env="UNUSED_PROVIDER_KEY",
            request_timeout_seconds=1,
            model_max_retries=0,
            compiler_max_turns=1,
            subagent_timeout_seconds=600,
            memory_enabled=False,
            skills_enabled=False,
            required_system_packages=(),
            cmake_arguments=("-DCMAKE_BUILD_TYPE=Release",),
            configure_arguments=(),
            environment=(),
            minimum_replay_delay_seconds=0,
        )
        activate_experiment(
            thread_id=parent.thread_id,
            experiment_id=parent_ledger.experiment_id,
            physical_attempt_id=parent_ledger.physical_attempt_id,
            ledger=parent_ledger,
            policy=parent_policy,
        )
        parent_active = True
        fault = controlled_fault.ControlledFaultV1(
            controlled_fault.ControlledFaultSpec(
                case_id=CASE_ID,
                build_output_relative_path=BUILD_OUTPUT,
                staged_relative_path=STAGED_ARTIFACT,
                artifact_type="executable",
            )
        )
        fault_manifest = fault.inject(
            session=parent,
            ledger=parent_ledger,
            fault_id=new_evidence_id("fault"),
        )
        submit_result: str | None = None

        def submit() -> str:
            nonlocal submit_result, repair_packet
            if submit_result is not None:
                raise CanaryError("neutral submit 不得重复执行")
            submit_result = operations.submit_build_result_impl(
                session=parent,
                supporting_command_id=supporting.command_id,
            )
            repair_packet = repair_runtime.build_repair_packet(
                json.loads(submit_result),
                parent_ledger.read(),
                expected_artifacts=((STAGED_ARTIFACT, "executable"),),
            )
            if repair_packet is None:
                raise CanaryError(
                    "controlled failure 未生成 schema-valid repair packet"
                )
            return submit_result

        def evidence() -> dict[str, Any]:
            result = controlled_fault.validate_actionable_failure(
                ledger=parent_ledger, session=parent
            )
            result["session_sha256"] = lifecycle.sha256_file(Path(parent.metadata_path))
            result["fault_state_sha256"] = fault_manifest["fault_state_sha256"]
            return result

        coordinator = lifecycle.CaptureCoordinator(
            output_dir / "checkpoint" / "coordinator.sqlite"
        )
        with SqliteSaver.from_conn_string(
            str(output_dir / "checkpoint" / "messages.sqlite")
        ) as saver:
            saver.setup()
            message_runtime = lifecycle.LifecycleMessageRuntime(saver, submit)
            environment = lifecycle.LifecycleEnvironmentAdapter(
                docker,
                local_snapshot_root=snapshot,
                host_snapshot_root=host_snapshot_root(snapshot),
            )
            gate = lifecycle.RealLifecycleCheckpointGate(
                coordinator=coordinator,
                message_runtime=message_runtime,
                environment=environment,
                budget_capture=_budget_manifest,
                manager=manager,
                compile_runtime=runtime,
                owner="checkpoint-primary-canary",
            )
            gate.capture(
                capture_id=capture_id,
                session=parent,
                instruction="Repair this controlled artifact staging failure and submit the build.",
                arm_plan=_arm_plan(capture_id),
                bind_sources={
                    "workspace": get_host_workspace_dir(
                        parent.session_id, parent.thread_id, manager.paths
                    ),
                    "artifacts": get_host_artifacts_dir(
                        parent.session_id, parent.thread_id, manager.paths
                    ),
                    "logs": get_host_logs_dir(
                        parent.session_id, parent.thread_id, manager.paths
                    ),
                    "repro": get_host_repro_dir(
                        parent.session_id, parent.thread_id, manager.paths
                    ),
                },
                evidence=evidence,
            )
            if repair_packet is None:
                raise CanaryError("repair packet 在 checkpoint capture 后缺失")
            message_runtime.repair_packet = repair_packet
            if parent_active:
                deactivate_experiment(parent.thread_id)
                parent_active = False
            parent_ledger.append("experiment.completed", {"status": "passed"})
            provisioned = {
                arm: gate.provision_arm(capture_id, arm, parent_session=parent)
                for arm in ARMS
            }
            if gate.canonical_arm_environment(
                "baseline"
            ) != gate.canonical_arm_environment("treatment"):
                raise CanaryError("baseline/treatment 初始环境不同源")
            for arm in manifest["continuation"]["arm_order"]:
                current = provisioned[arm]
                message_state = _message_state(gate, current)
                ledger = ExperimentLedger.create(
                    output_dir / "ledgers" / f"{arm}.jsonl",
                    experiment_id=new_evidence_id("experiment"),
                    physical_attempt_id=new_evidence_id("mechanism_attempt"),
                    context={
                        "scope": "checkpoint-primary-controlled-arm",
                        "manifest_sha256": manifest_digest,
                        "thread_id": current.session.thread_id,
                        "arm": arm,
                        "capture_id": capture_id,
                    },
                )
                result = asyncio.run(
                    run_arm_continuation(
                        manifest,
                        arm=arm,
                        lifecycle_arm=current,
                        message_state=message_state,
                        ledger=ledger,
                        model_factory=model_factory,
                    )
                )
                arm_results.append(result)
            cleaned = gate.cleanup(capture_id, parent_session=parent)
            cleanup_succeeded = cleaned.phase == "cleaned"
            if not cleanup_succeeded:
                raise CanaryError("controlled pair cleanup 未闭合")
        report = {
            "schema_version": "forge-checkpoint-primary-controlled-pair-1.0.0",
            "document_type": "forge_checkpoint_primary_controlled_pair",
            "manifest_sha256": manifest_digest,
            "release_revision": release["revision"],
            "capture_id": capture_id,
            "provider": manifest["provider"]["id"],
            "network_access_medium": medium,
            "reachability_recorded_tokens": reachability["recorded_tokens"],
            "arm_order": manifest["continuation"]["arm_order"],
            "arms": arm_results,
            "complete_pair": len(arm_results) == 2,
            "cleanup_succeeded": cleanup_succeeded,
            "pilot_denominator_contribution": 0,
            "passed": len(arm_results) == 2 and cleanup_succeeded,
            "completed_at": datetime.now(UTC).isoformat(),
        }
        total_tokens = reachability["recorded_tokens"] + sum(
            arm["recorded_tokens"] for arm in arm_results
        )
        report["stage_recorded_tokens"] = total_tokens
        if total_tokens > manifest["budget"]["stage_maximum_tokens"]:
            raise CanaryError("canary 阶段超过总 recorded-token 上限")
        report_path = output_dir / "reports" / "controlled-pair.json"
        _atomic_write(report_path, report)
    except BaseException as exc:
        if parent_active:
            deactivate_experiment(parent.thread_id)
        if gate is not None and not cleanup_succeeded:
            try:
                record = gate.coordinator.get(capture_id)
                if record.phase not in {
                    "committed",
                    "aborted",
                    "cleanup_pending",
                    "cleaned",
                }:
                    record = gate.reconcile(capture_id)
                if record.phase == "cleaned":
                    cleanup_succeeded = True
                else:
                    cleaned = gate.cleanup(capture_id, parent_session=parent)
                    cleanup_succeeded = cleaned.phase == "cleaned"
            except Exception:
                cleanup_succeeded = False
        else:
            runtime.stop_and_remove_container(parent)
        _finish_marker(marker, status="failed", error_class=type(exc).__name__)
        raise
    _finish_marker(marker, status="passed")
    return {**report, "report_path": str(report_path)}


def _json_print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("validate", "reachability", "controlled-pair")
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest = load_manifest(args.manifest)
    if args.command == "validate":
        verify_frozen_artifacts(manifest)
        _json_print(
            {
                "status": "valid",
                "manifest_sha256": canonical_sha256(manifest),
                "provider_calls": 0,
            }
        )
        return 0
    if args.command == "reachability":
        _json_print(run_reachability(manifest, output_dir=args.output_dir))
        return 0
    _json_print(run_controlled_pair(manifest, output_dir=args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
