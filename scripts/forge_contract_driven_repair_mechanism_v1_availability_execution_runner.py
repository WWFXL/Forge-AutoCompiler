#!/usr/bin/env python3
"""执行并审计契约驱动修复 mechanism v1 唯一 availability qualification。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_contract_driven_repair_mechanism_v1_availability_candidate_runner as candidate_runner  # noqa: E402
import forge_contract_driven_repair_mechanism_v1_availability_execution_protocol as protocol  # noqa: E402

from deerflow.compile.evidence import model_response_metadata  # noqa: E402

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_OUTPUT_DIR = REPO_ROOT / protocol.parent.parent.EVIDENCE_DIRECTORY
READ_ONLY_COMMANDS = ("validate", "plan", "preflight", "audit")
EXECUTION_COMMANDS = ("availability",)
BLOCKED_COMMANDS = ("batch",)


class AvailabilityExecutionRunnerError(RuntimeError):
    """availability 执行的 release、evidence、Provider 或终态无效。"""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AvailabilityExecutionRunnerError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise AvailabilityExecutionRunnerError(f"JSON 顶层必须为对象: {path}")
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
        raise AvailabilityExecutionRunnerError(
            f"不可覆盖已存在的 availability evidence: {path}"
        ) from exc


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    if path.is_symlink() or not path.is_file():
        raise AvailabilityExecutionRunnerError(
            "availability marker 不存在或不是普通文件"
        )
    temporary = path.with_suffix(path.suffix + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise AvailabilityExecutionRunnerError("availability marker 临时路径已存在")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _run_checked(argv: list[str], *, cwd: Path) -> str:
    result = subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise AvailabilityExecutionRunnerError(
            f"availability preflight 命令失败: {' '.join(argv)}: {detail}"
        )
    return result.stdout.strip()


def _manifest_sha256(manifest: dict[str, Any]) -> str:
    return protocol.parent.parent.candidate.canonical_sha256(manifest)


def _output_dir(manifest: dict[str, Any], output_dir: Path, repo_root: Path) -> Path:
    root = repo_root.resolve(strict=True)
    expected = root / manifest["candidate_evidence"]["directory"]
    if (
        output_dir.resolve(strict=False) != expected
        or expected.parent != root / ".compile-sessions"
        or output_dir.is_symlink()
    ):
        raise AvailabilityExecutionRunnerError(
            "availability evidence 未绑定到冻结的 create-once 路径"
        )
    return expected


def validate_runtime(
    manifest: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    runtime = manifest["availability_execution_runtime"]
    if (
        runtime["commands"]
        != [
            "validate",
            "plan",
            "preflight",
            "availability",
            "audit",
            "batch",
        ]
        or runtime["batch_fails_closed"] is not True
    ):
        raise AvailabilityExecutionRunnerError(
            "availability execution 命令边界发生漂移"
        )
    return {
        "status": "availability_execution_authorized_not_started",
        "manifest_sha256": _manifest_sha256(manifest),
        "availability_candidate_release_revision": protocol.AVAILABILITY_CANDIDATE_RELEASE_REVISION,
        "availability_execution_authorized": True,
        "formal_collection_execution_authorized": False,
        "provider_calls": 0,
        "credential_reads": 0,
        "docker_sessions_created": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
        "model_tokens": 0,
    }


def _require_execution_release(repo_root: Path) -> dict[str, str]:
    revision = _run_checked(["git", "rev-parse", "HEAD"], cwd=repo_root)
    origin_main = _run_checked(["git", "rev-parse", "origin/main"], cwd=repo_root)
    branch = _run_checked(["git", "branch", "--show-current"], cwd=repo_root)
    _run_checked(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            protocol.AVAILABILITY_CANDIDATE_RELEASE_REVISION,
            revision,
        ],
        cwd=repo_root,
    )
    dirty = _run_checked(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo_root
    )
    if branch != "main" or revision != origin_main or dirty:
        raise AvailabilityExecutionRunnerError(
            "availability 执行要求干净 main 且 HEAD == origin/main"
        )
    return {"revision": revision, "branch": branch, "origin_main": origin_main}


def _provider_config_preflight(manifest: dict[str, Any]) -> None:
    from deerflow.config import get_app_config

    provider = manifest["provider_candidate"]
    configured = get_app_config().get_model_config(provider["profile"])
    if configured is None:
        raise AvailabilityExecutionRunnerError("config.yaml 缺少冻结 Provider model")
    settings = configured.model_dump(exclude_none=True)
    if settings.get("model") != provider["actual_model"]:
        raise AvailabilityExecutionRunnerError("Provider actual model 配置发生漂移")
    endpoint = settings.get(
        "base_url", settings.get("api_base", settings.get("openai_api_base"))
    )
    if endpoint is None or str(endpoint).rstrip("/") != provider["endpoint"].rstrip(
        "/"
    ):
        raise AvailabilityExecutionRunnerError("Provider endpoint 配置发生漂移")
    if not os.environ.get(provider["credential_env_name"], "").strip():
        raise AvailabilityExecutionRunnerError("Provider credential env 未注入")


def collect_preflight(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    validate_runtime(manifest, repo_root)
    evidence = _output_dir(manifest, output_dir, repo_root)
    release = _require_execution_release(repo_root)
    parent_runner = candidate_runner.parent_runner
    try:
        image_id = parent_runner._require_docker_identity(manifest, repo_root)
        parent_runner._require_zero_managed_resources(repo_root)
        observed_evidence = parent_runner._require_evidence_absent(manifest, repo_root)
    except parent_runner.AuthorizedRunnerError as exc:
        raise AvailabilityExecutionRunnerError(str(exc)) from exc
    if observed_evidence != evidence:
        raise AvailabilityExecutionRunnerError(
            "父 preflight 返回了不同 evidence identity"
        )
    _provider_config_preflight(manifest)
    return {
        "ready": True,
        "status": "availability_execution_preflight_passed_not_started",
        "manifest_sha256": _manifest_sha256(manifest),
        "availability_candidate_release_revision": protocol.AVAILABILITY_CANDIDATE_RELEASE_REVISION,
        "observed_execution_revision": release["revision"],
        "branch": release["branch"],
        "origin_main": release["origin_main"],
        "compile_image_id": image_id,
        "evidence_directory": str(evidence),
        "evidence_directory_absent": True,
        "zero_managed_resources": True,
        "provider_config_valid": True,
        "credential_check": "environment_variable_presence_only",
        "provider_calls": 0,
        "docker_sessions_created": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
        "model_tokens": 0,
    }


def _create_provider_model(manifest: dict[str, Any]) -> Any:
    from deerflow.config import get_app_config
    from deerflow.models.factory import create_chat_model

    provider = manifest["provider_candidate"]
    configured = get_app_config().get_model_config(provider["profile"])
    if configured is None:
        raise AvailabilityExecutionRunnerError("config.yaml 缺少冻结 Provider model")
    original_timeout = getattr(configured, "request_timeout", None)
    original_retries = getattr(configured, "max_retries", None)
    try:
        configured.request_timeout = float(provider["request_timeout_seconds"])
        configured.max_retries = 0
        model = create_chat_model(
            name=provider["profile"],
            thinking_enabled=False,
            experiment_role="availability",
        )
    finally:
        configured.request_timeout = original_timeout
        configured.max_retries = original_retries
    if bool(getattr(model, "streaming", False)):
        raise AvailabilityExecutionRunnerError(
            "availability Provider 必须关闭 streaming"
        )
    return model


def _response_text(response: Any) -> str:
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "".join(parts)


def _bounded_error_class(exc: BaseException) -> str:
    name = type(exc).__name__
    return (
        name if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name) else "ProviderError"
    )


def _claim_marker(
    path: Path, *, manifest_sha256: str, revision: str, execution: dict[str, Any]
) -> None:
    _write_once(
        path,
        {
            "schema_version": execution["marker_schema_version"],
            "document_type": "forge_contract_repair_availability_marker",
            "manifest_sha256": manifest_sha256,
            "execution_revision": revision,
            "provider": execution["provider"],
            "model": execution["provider_profile"],
            "actual_model_required": execution["actual_model"],
            "endpoint": execution["endpoint"],
            "logical_request_count": 1,
            "maximum_request_attempts": execution["contract"][
                "max_request_attempts_including_transport_retry"
            ],
            "max_recorded_tokens": execution["max_recorded_tokens"],
            "formal_batch_creation_authorized": False,
            "status": "started",
            "passed": False,
            "attempts": [],
            "request_attempt_count": 0,
            "recorded_input_tokens": 0,
            "recorded_output_tokens": 0,
            "recorded_total_tokens": 0,
            "error_class": None,
            "started_at": datetime.now(UTC).isoformat(),
            "completed_at": None,
        },
    )


def _append_attempt(path: Path, attempt: dict[str, Any]) -> dict[str, Any]:
    marker = _load_json(path)
    if marker.get("status") != "started":
        raise AvailabilityExecutionRunnerError("availability marker 不处于 started")
    attempts = marker.get("attempts")
    if (
        not isinstance(attempts, list)
        or attempt["request_sequence"] != len(attempts) + 1
    ):
        raise AvailabilityExecutionRunnerError("availability attempt 顺序发生漂移")
    attempts.append(attempt)
    marker["request_attempt_count"] = len(attempts)
    marker["recorded_input_tokens"] += attempt["input_tokens"]
    marker["recorded_output_tokens"] += attempt["output_tokens"]
    marker["recorded_total_tokens"] += attempt["total_tokens"]
    _atomic_write(path, marker)
    return marker


def _finish_marker(
    path: Path, *, passed: bool, error_class: str | None
) -> dict[str, Any]:
    marker = _load_json(path)
    if marker.get("status") != "started":
        raise AvailabilityExecutionRunnerError("availability marker 不处于 started")
    marker["status"] = "passed" if passed else "failed"
    marker["passed"] = passed
    marker["error_class"] = error_class
    marker["completed_at"] = datetime.now(UTC).isoformat()
    _atomic_write(path, marker)
    return marker


def _attempt_from_response(
    response: Any,
    *,
    sequence: int,
    expected_response: str,
    expected_model: str,
    duration_ms: int,
) -> tuple[dict[str, Any], bool]:
    text = _response_text(response).strip()
    actual_model, usage = model_response_metadata(response)
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    total_tokens = usage.get("total_tokens")
    tokens_valid = all(
        type(value) is int and value >= 0
        for value in (input_tokens, output_tokens, total_tokens)
    )
    normalized = (
        (input_tokens, output_tokens, total_tokens) if tokens_valid else (0, 0, 0)
    )
    passed = (
        text == expected_response and actual_model == expected_model and tokens_valid
    )
    retry_eligible = sequence == 1 and text == "" and normalized == (0, 0, 0)
    return (
        {
            "request_sequence": sequence,
            "response_received": text != "",
            "response_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()
            if text
            else None,
            "response_length": len(text),
            "expected_response_match": text == expected_response,
            "actual_model": actual_model,
            "model_identity_match": actual_model == expected_model,
            "usage_metadata_observed": tokens_valid,
            "input_tokens": normalized[0],
            "output_tokens": normalized[1],
            "total_tokens": normalized[2],
            "tool_side_effect_count": 0,
            "error_class": None,
            "retry_eligible": retry_eligible,
            "duration_ms": duration_ms,
        },
        passed,
    )


def execute_availability(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    model_factory: Callable[[dict[str, Any]], Any] = _create_provider_model,
) -> dict[str, Any]:
    preflight = collect_preflight(manifest, output_dir=output_dir, repo_root=repo_root)
    execution = manifest["availability_execution"]
    marker_path = output_dir / execution["marker"]
    digest = _manifest_sha256(manifest)
    _claim_marker(
        marker_path,
        manifest_sha256=digest,
        revision=preflight["observed_execution_revision"],
        execution=execution,
    )
    terminal_error: str | None = None
    passed = False
    try:
        model = model_factory(manifest)
        maximum = execution["contract"][
            "max_request_attempts_including_transport_retry"
        ]
        for sequence in range(1, maximum + 1):
            started = time.perf_counter()
            try:
                response = model.invoke(execution["contract"]["request"])
                duration_ms = round((time.perf_counter() - started) * 1000)
                attempt, passed = _attempt_from_response(
                    response,
                    sequence=sequence,
                    expected_response=execution["contract"]["expected_response"],
                    expected_model=execution["actual_model"],
                    duration_ms=duration_ms,
                )
            except BaseException as exc:
                duration_ms = round((time.perf_counter() - started) * 1000)
                attempt = {
                    "request_sequence": sequence,
                    "response_received": False,
                    "response_sha256": None,
                    "response_length": 0,
                    "expected_response_match": False,
                    "actual_model": None,
                    "model_identity_match": False,
                    "usage_metadata_observed": False,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "tool_side_effect_count": 0,
                    "error_class": _bounded_error_class(exc),
                    "retry_eligible": sequence == 1,
                    "duration_ms": duration_ms,
                }
            _append_attempt(marker_path, attempt)
            if passed:
                break
            if not attempt["retry_eligible"]:
                terminal_error = attempt["error_class"] or "AvailabilityResponseInvalid"
                break
        if not passed and terminal_error is None:
            terminal_error = "AvailabilityTransportRetryExhausted"
    except BaseException as exc:
        terminal_error = _bounded_error_class(exc)
        _finish_marker(marker_path, passed=False, error_class=terminal_error)
        raise
    marker = _finish_marker(
        marker_path, passed=passed, error_class=None if passed else terminal_error
    )
    try:
        candidate_runner.parent_runner._require_zero_managed_resources(repo_root)
    except candidate_runner.parent_runner.AuthorizedRunnerError as exc:
        raise AvailabilityExecutionRunnerError(str(exc)) from exc
    if not passed:
        raise AvailabilityExecutionRunnerError(
            "唯一 availability qualification 未通过；formal batch 保持关闭"
        )
    return marker


def audit_availability(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    validate_runtime(manifest, repo_root)
    _output_dir(manifest, output_dir, repo_root)
    marker_path = output_dir / manifest["availability_execution"]["marker"]
    marker = _load_json(marker_path)
    expected_hash = hashlib.sha256(b"FORGE_READY").hexdigest()
    attempts = marker.get("attempts")
    if (
        marker.get("schema_version")
        != manifest["availability_execution"]["marker_schema_version"]
        or marker.get("manifest_sha256") != _manifest_sha256(manifest)
        or marker.get("formal_batch_creation_authorized") is not False
        or marker.get("status") not in {"passed", "failed"}
        or not isinstance(attempts, list)
        or not 0 <= len(attempts) <= 2
        or marker.get("request_attempt_count") != len(attempts)
        or [item.get("request_sequence") for item in attempts]
        != list(range(1, len(attempts) + 1))
    ):
        raise AvailabilityExecutionRunnerError(
            "availability marker identity 或顺序无效"
        )
    for index, attempt in enumerate(attempts):
        if (
            attempt.get("tool_side_effect_count") != 0
            or type(attempt.get("input_tokens")) is not int
            or type(attempt.get("output_tokens")) is not int
            or type(attempt.get("total_tokens")) is not int
        ):
            raise AvailabilityExecutionRunnerError("availability attempt evidence 无效")
        if index == 1 and attempts[0].get("retry_eligible") is not True:
            raise AvailabilityExecutionRunnerError(
                "第二次 attempt 不满足冻结 retry 条件"
            )
    if marker["status"] == "passed":
        if not attempts:
            raise AvailabilityExecutionRunnerError("availability 通过终态缺少 attempt")
        final = attempts[-1]
        if (
            marker.get("passed") is not True
            or final.get("expected_response_match") is not True
            or final.get("response_sha256") != expected_hash
            or final.get("actual_model")
            != manifest["availability_execution"]["actual_model"]
            or final.get("usage_metadata_observed") is not True
            or marker.get("error_class") is not None
        ):
            raise AvailabilityExecutionRunnerError("availability 通过终态证据无效")
    elif marker.get("passed") is not False or not marker.get("error_class"):
        raise AvailabilityExecutionRunnerError("availability 失败终态证据无效")
    candidate_runner.parent_runner._require_zero_managed_resources(repo_root)
    return {
        "status": "availability_evidence_audited",
        "manifest_sha256": marker["manifest_sha256"],
        "execution_revision": marker["execution_revision"],
        "availability_status": marker["status"],
        "passed": marker["passed"],
        "request_attempt_count": marker["request_attempt_count"],
        "recorded_input_tokens": marker["recorded_input_tokens"],
        "recorded_output_tokens": marker["recorded_output_tokens"],
        "recorded_total_tokens": marker["recorded_total_tokens"],
        "zero_tool_side_effects": True,
        "zero_managed_resources": True,
        "formal_batch_creation_authorized": False,
    }


def run_batch() -> None:
    raise AvailabilityExecutionRunnerError(
        "batch 不属于 availability identity；formal collection 必须使用独立身份"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=READ_ONLY_COMMANDS + EXECUTION_COMMANDS + BLOCKED_COMMANDS
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    if args.command in BLOCKED_COMMANDS:
        run_batch()
    manifest = protocol.load_manifest(args.manifest)
    if args.command == "validate":
        result: Any = validate_runtime(manifest)
    elif args.command == "plan":
        result = protocol.plan_summary(manifest)
    elif args.command == "preflight":
        result = collect_preflight(manifest, output_dir=args.output_dir)
    elif args.command == "audit":
        result = audit_availability(manifest, output_dir=args.output_dir)
    else:
        result = execute_availability(manifest, output_dir=args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
