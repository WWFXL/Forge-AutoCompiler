#!/usr/bin/env python3
"""执行 formal v4 有限端点诊断、新 canary 与原六槽。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_formal_collection_v4_canary_amendment_protocol as protocol  # noqa: E402

# 协议模块先建立仓库导入根，再加载 Ubuntu 门禁实现。
# isort: split
import forge_formal_collection_v4_ubuntu_runner as ubuntu_runner  # noqa: E402


def _load_private_base_runner():
    module_name = f"{__name__}_base"
    spec = importlib.util.spec_from_file_location(
        module_name,
        SCRIPT_ROOT / "forge_formal_collection_v2_runner.py",
    )
    if spec is None or spec.loader is None:
        raise ImportError("Unable to load the formal collection base runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_runner = _load_private_base_runner()
_original_manifest_protocol = _runner._manifest_protocol
_original_build_policy = _runner.build_policy
_original_collect_preflight = _runner.collect_preflight
_original_collect_provider_canary = _runner.collect_provider_canary
_original_create_attempt = _runner.create_attempt
_original_run_attempt = _runner.run_attempt

_runner.protocol_formal_collection = protocol

RunnerError = _runner.RunnerError
REPO_ROOT = _runner.REPO_ROOT
DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
_CANARY_ATTEMPT_MARKER = "formal-v4-canary-amendment-provider-canary-attempt.json"
_DIAGNOSTIC_SUMMARY = "endpoint-diagnostic-summary.json"
_DIAGNOSTIC_ATTEMPT_KEYS = {
    "schema_version",
    "document_type",
    "benchmark_id",
    "manifest_sha256",
    "condition_id",
    "provider",
    "model",
    "attempt",
    "status",
    "started_at",
    "completed_at",
    "duration_ms",
    "response_nonempty",
    "error_class",
    "passed",
}
_SAFE_ERROR_CLASS = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def _manifest_protocol(manifest: dict[str, Any]):
    if manifest.get("schema_version") == protocol.SCHEMA_VERSION:
        return protocol
    return _original_manifest_protocol(manifest)


def build_policy(
    manifest: dict[str, Any],
    *,
    case_id: str,
    condition_id: str,
    repetition: int,
):
    return _original_build_policy(
        manifest,
        case_id=case_id,
        condition_id=condition_id,
        repetition=repetition,
    )


def collect_runtime_launch_preflight(
    output_dir: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    return ubuntu_runner.collect_runtime_launch_preflight(
        output_dir,
        repo_root=repo_root,
    )


def _formal_output_dir(manifest: dict[str, Any]) -> Path:
    return Path(manifest["authorization"]["collection_constraints"]["evidence_directory"])


def _diagnostic_output_dir(manifest: dict[str, Any]) -> Path:
    return Path(manifest["authorization"]["diagnostics"]["directory"])


def _legacy_output_dir(manifest: dict[str, Any]) -> Path:
    return Path(manifest["authorization"]["superseded_canary_terminal"]["evidence_directory"])


def _require_exact_output_dir(actual: Path, expected: Path, *, purpose: str) -> None:
    if actual.resolve(strict=False) != expected.resolve(strict=False):
        raise RunnerError(f"Formal v4 {purpose} must use its frozen directory")


def _authorized_slots(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    orders = manifest["authorization"]["collection_constraints"]["authorized_schedule_orders"]
    by_order = {slot["order"]: slot for slot in manifest["collection_plan"]}
    try:
        return [by_order[order] for order in orders]
    except KeyError as exc:
        raise RunnerError("An authorized schedule order is missing from the frozen collection") from exc


def _slot_identity(slot: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": slot["case_id"],
        "condition_id": slot["condition_id"],
        "repetition": slot["repetition"],
    }


def _recorded_total_tokens(
    observed: list[tuple[dict[str, Any], list[dict[str, Any]]]],
) -> int:
    total = 0
    for _slot, events in observed:
        for event in events:
            if event.get("event") != "model.request_completed":
                continue
            payload = event.get("payload")
            usage = payload.get("token_usage") if isinstance(payload, dict) else None
            value = usage.get("total_tokens") if isinstance(usage, dict) else None
            if type(value) is int and value >= 0:
                total += value
    return total


def _token_limit(manifest: dict[str, Any]) -> int:
    return int(manifest["authorization"]["budget_confirmation"]["maximum_recorded_tokens"])


def _observed_authorized_ledgers(
    manifest: dict[str, Any],
    *,
    output_dir: Path,
) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    return _runner._observed_collection_ledgers(manifest, output_dir=output_dir)


def _ensure_token_budget_remaining(
    manifest: dict[str, Any],
    *,
    output_dir: Path,
) -> int:
    recorded = _recorded_total_tokens(_observed_authorized_ledgers(manifest, output_dir=output_dir))
    if recorded >= _token_limit(manifest):
        raise RunnerError("The authorized recorded-token boundary has already been reached")
    return recorded


def _enforce_authorized_order(
    manifest: dict[str, Any],
    *,
    case_id: str,
    condition_id: str,
    repetition: int,
    output_dir: Path,
) -> int:
    plan = [_slot_identity(slot) for slot in _authorized_slots(manifest)]
    observed = _observed_authorized_ledgers(manifest, output_dir=output_dir)
    observed_slots = [slot for slot, _events in observed]
    if observed_slots != plan[: len(observed_slots)]:
        raise RunnerError("Existing physical evidence does not match the authorized slot order")
    if observed and observed[-1][1][-1]["event"] != "experiment.completed":
        raise RunnerError("The previous authorized slot must complete before the next slot is created")
    if len(observed_slots) >= len(plan):
        raise RunnerError("All six authorized slots already have physical evidence")
    requested = {
        "case_id": case_id,
        "condition_id": condition_id,
        "repetition": repetition,
    }
    if requested != plan[len(observed_slots)]:
        raise RunnerError("The requested slot is not next in the authorized slot order")
    return len(observed_slots)


@contextmanager
def _base_order_gate_already_checked():
    original = _runner._enforce_frozen_collection_order
    _runner._enforce_frozen_collection_order = lambda *args, **kwargs: 0
    try:
        yield
    finally:
        _runner._enforce_frozen_collection_order = original


@contextmanager
def _anonymous_endpoint_preflight_disabled():
    original = _runner.collect_preflight

    def collect_without_endpoint(*args: Any, **kwargs: Any):
        kwargs["check_endpoint"] = False
        return _original_collect_preflight(*args, **kwargs)

    _runner.collect_preflight = collect_without_endpoint
    try:
        yield
    finally:
        _runner.collect_preflight = original


def _formal_container_ids() -> list[str] | None:
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                "label=deerflow.compile.physical_attempt_id",
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return [line for line in result.stdout.splitlines() if line.strip()]


def _verify_legacy_terminal(
    manifest: dict[str, Any],
    *,
    legacy_output_dir: Path | None = None,
) -> dict[str, Any]:
    frozen = manifest["authorization"]["superseded_canary_terminal"]
    directory = legacy_output_dir or _legacy_output_dir(manifest)
    marker_path = directory / frozen["marker_relative_path"]
    try:
        raw = marker_path.read_bytes()
        marker = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise RunnerError("The consumed formal v4 canary marker is missing or invalid") from exc
    if hashlib.sha256(raw).hexdigest() != frozen["marker_sha256"]:
        raise RunnerError("The consumed formal v4 canary marker changed")
    expected = {
        "benchmark_id": frozen["benchmark_id"],
        "manifest_sha256": frozen["manifest_sha256"],
        "status": frozen["status"],
        "error_class": frozen["error_class"],
    }
    if any(marker.get(key) != value for key, value in expected.items()):
        raise RunnerError("The consumed formal v4 canary terminal identity changed")
    reports = [path for path in (directory / "provider-canaries").glob("*.json") if path != marker_path]
    ledgers = list(directory.rglob("*.jsonl"))
    if len(reports) != frozen["provider_report_count"] or len(ledgers) != frozen["formal_ledger_count"]:
        raise RunnerError("The consumed formal v4 evidence layer is no longer empty")
    return {
        "marker_sha256": frozen["marker_sha256"],
        "status": marker["status"],
        "error_class": marker["error_class"],
        "provider_report_count": len(reports),
        "formal_ledger_count": len(ledgers),
    }


def _bounded_error_class(exc: BaseException) -> str:
    name = type(exc).__name__
    return name if _SAFE_ERROR_CLASS.fullmatch(name) else "DiagnosticFailure"


def _model_response_text(response: Any) -> str:
    return _runner._model_response_text(response)


def _issue_diagnostic_request(model_name: str, prompt: str, max_output_tokens: int) -> bool:
    from deerflow.models.factory import create_chat_model

    model = create_chat_model(name=model_name, thinking_enabled=False)
    response = model.invoke(prompt, max_tokens=max_output_tokens)
    return bool(_model_response_text(response).strip())


def _diagnostic_model_config_matches(
    manifest: dict[str, Any],
    provider: dict[str, Any],
) -> bool:
    try:
        from deerflow.config import get_app_config

        profile = manifest["model_profiles"][provider["condition_id"]]
        configured = get_app_config().get_model_config(provider["model"])
        if configured is None:
            return False
        settings = configured.model_dump(exclude_none=True)
        endpoint = settings.get("base_url", settings.get("openai_api_base"))
        timeout = settings.get("request_timeout")
        return (
            configured.model == provider["model"]
            and endpoint is not None
            and str(endpoint).rstrip("/") == profile["endpoint"].rstrip("/")
            and float(timeout) == float(manifest["authorization"]["diagnostics"]["request_timeout_seconds"])
            and settings.get("max_retries") == 0
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def _diagnostic_attempt_path(
    output_dir: Path,
    *,
    condition_id: str,
    attempt: int,
) -> Path:
    return output_dir / "attempts" / f"{condition_id}-{attempt}-started.json"


def _diagnostic_terminal_path(
    output_dir: Path,
    *,
    condition_id: str,
    attempt: int,
) -> Path:
    return output_dir / "attempts" / f"{condition_id}-{attempt}-terminal.json"


def _write_json_exclusive(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def _read_diagnostic_document(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunnerError("A diagnostic attempt record is invalid") from exc
    if set(record) != _DIAGNOSTIC_ATTEMPT_KEYS:
        raise RunnerError("A diagnostic attempt record contains non-whitelisted fields")
    if record.get("document_type") != "formal_endpoint_diagnostic_attempt":
        raise RunnerError("A diagnostic attempt record has the wrong document type")
    if record.get("benchmark_id") != manifest["benchmark"]["id"]:
        raise RunnerError("A diagnostic attempt record has the wrong benchmark identity")
    if record.get("manifest_sha256") != protocol.manifest_sha256(manifest):
        raise RunnerError("A diagnostic attempt record has the wrong manifest identity")
    if type(record.get("attempt")) is not int or record["attempt"] not in {1, 2}:
        raise RunnerError("A diagnostic attempt number is outside the frozen limit")
    if record.get("status") not in {"started", "passed", "failed"}:
        raise RunnerError("A diagnostic attempt status is invalid")
    if record["status"] == "started":
        if any(
            (
                record.get("completed_at") is not None,
                record.get("duration_ms") is not None,
                record.get("response_nonempty") is not False,
                record.get("error_class") is not None,
                record.get("passed") is not False,
            )
        ):
            raise RunnerError("A started diagnostic attempt contains terminal evidence")
        return record
    if type(record.get("duration_ms")) is not int or record["duration_ms"] < 0:
        raise RunnerError("A diagnostic attempt duration is invalid")
    if type(record.get("response_nonempty")) is not bool or type(record.get("passed")) is not bool:
        raise RunnerError("A diagnostic attempt boolean is invalid")
    error_class = record.get("error_class")
    if error_class is not None and (not isinstance(error_class, str) or not _SAFE_ERROR_CLASS.fullmatch(error_class)):
        raise RunnerError("A diagnostic attempt error class is invalid")
    if record["passed"] is not (record["response_nonempty"] and error_class is None):
        raise RunnerError("A diagnostic attempt result is internally inconsistent")
    if record["status"] != ("passed" if record["passed"] else "failed"):
        raise RunnerError("A diagnostic attempt terminal status is inconsistent")
    return record


def _read_diagnostic_attempt(
    output_dir: Path,
    manifest: dict[str, Any],
    *,
    provider: dict[str, Any],
    attempt: int,
) -> dict[str, Any] | None:
    started_path = _diagnostic_attempt_path(
        output_dir,
        condition_id=provider["condition_id"],
        attempt=attempt,
    )
    terminal_path = _diagnostic_terminal_path(
        output_dir,
        condition_id=provider["condition_id"],
        attempt=attempt,
    )
    if terminal_path.exists() and not started_path.exists():
        raise RunnerError("A diagnostic terminal record is missing its reservation")
    if not started_path.exists():
        return None
    started = _read_diagnostic_document(started_path, manifest)
    if started["status"] != "started":
        raise RunnerError("A diagnostic reservation has a terminal status")
    if not terminal_path.exists():
        return started
    terminal = _read_diagnostic_document(terminal_path, manifest)
    immutable_keys = {
        "schema_version",
        "document_type",
        "benchmark_id",
        "manifest_sha256",
        "condition_id",
        "provider",
        "model",
        "attempt",
        "started_at",
    }
    if any(terminal.get(key) != started.get(key) for key in immutable_keys):
        raise RunnerError("A diagnostic terminal record changed its reservation identity")
    if terminal["status"] == "started":
        raise RunnerError("A diagnostic terminal record is not terminal")
    return terminal


def _existing_diagnostic_attempts(
    manifest: dict[str, Any],
    *,
    output_dir: Path,
    provider: dict[str, Any],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for attempt in (1, 2):
        record = _read_diagnostic_attempt(
            output_dir,
            manifest,
            provider=provider,
            attempt=attempt,
        )
        if record is None:
            continue
        expected_identity = {
            "condition_id": provider["condition_id"],
            "provider": provider["provider"],
            "model": provider["model"],
            "attempt": attempt,
        }
        if any(record.get(key) != value for key, value in expected_identity.items()):
            raise RunnerError("A diagnostic attempt identity changed")
        records.append(record)
    if [record["attempt"] for record in records] != list(range(1, len(records) + 1)):
        raise RunnerError("Diagnostic attempts must form a strict prefix")
    if any(record["passed"] for record in records[:-1]):
        raise RunnerError("A diagnostic provider was retried after its first success")
    return records


def _diagnostic_summary_path(output_dir: Path) -> Path:
    return output_dir / _DIAGNOSTIC_SUMMARY


def _require_diagnostic_layout(manifest: dict[str, Any], *, output_dir: Path) -> None:
    allowed = {_diagnostic_summary_path(output_dir)}
    for provider in manifest["authorization"]["diagnostics"]["providers"]:
        for attempt in (1, 2):
            allowed.add(
                _diagnostic_attempt_path(
                    output_dir,
                    condition_id=provider["condition_id"],
                    attempt=attempt,
                )
            )
            allowed.add(
                _diagnostic_terminal_path(
                    output_dir,
                    condition_id=provider["condition_id"],
                    attempt=attempt,
                )
            )
    unexpected = [path for path in output_dir.rglob("*") if path.is_file() and path not in allowed]
    if unexpected:
        raise RunnerError("The endpoint diagnostic directory contains an unexpected file")


def _build_diagnostic_summary(
    manifest: dict[str, Any],
    *,
    output_dir: Path,
) -> dict[str, Any]:
    conditions = []
    for provider in manifest["authorization"]["diagnostics"]["providers"]:
        records = _existing_diagnostic_attempts(
            manifest,
            output_dir=output_dir,
            provider=provider,
        )
        conditions.append(
            {
                "condition_id": provider["condition_id"],
                "provider": provider["provider"],
                "model": provider["model"],
                "attempt_count": len(records),
                "passed": bool(records and records[-1]["status"] == "passed"),
            }
        )
    return {
        "schema_version": "formal-endpoint-diagnostic-summary-1.0.0",
        "document_type": "formal_endpoint_diagnostic_summary",
        "benchmark_id": manifest["benchmark"]["id"],
        "manifest_sha256": protocol.manifest_sha256(manifest),
        "completed_at": datetime.now(UTC).isoformat(),
        "conditions": conditions,
        "passed": all(condition["passed"] for condition in conditions),
    }


def _load_diagnostic_summary(
    manifest: dict[str, Any],
    *,
    output_dir: Path | None = None,
    require_passed: bool,
) -> dict[str, Any]:
    directory = output_dir or _diagnostic_output_dir(manifest)
    try:
        summary = json.loads(_diagnostic_summary_path(directory).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunnerError("The endpoint diagnostic summary is missing or invalid") from exc
    expected_keys = {
        "schema_version",
        "document_type",
        "benchmark_id",
        "manifest_sha256",
        "completed_at",
        "conditions",
        "passed",
    }
    if set(summary) != expected_keys:
        raise RunnerError("The endpoint diagnostic summary contains non-whitelisted fields")
    if summary.get("document_type") != "formal_endpoint_diagnostic_summary":
        raise RunnerError("The endpoint diagnostic summary has the wrong document type")
    if summary.get("benchmark_id") != manifest["benchmark"]["id"] or summary.get("manifest_sha256") != protocol.manifest_sha256(manifest):
        raise RunnerError("The endpoint diagnostic summary has the wrong identity")
    _require_diagnostic_layout(manifest, output_dir=directory)
    rebuilt = _build_diagnostic_summary(manifest, output_dir=directory)
    if summary.get("conditions") != rebuilt["conditions"] or summary.get("passed") is not rebuilt["passed"]:
        raise RunnerError("The endpoint diagnostic summary does not match its attempt records")
    if require_passed and summary["passed"] is not True:
        raise RunnerError("Both bounded endpoint diagnostics must pass before the new canary")
    return summary


def collect_endpoint_diagnostics(
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    output_dir: Path,
    request_issuer: Callable[[str, str, int], bool] = _issue_diagnostic_request,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    if manifest.get("schema_version") != protocol.SCHEMA_VERSION:
        raise RunnerError("Endpoint diagnostics are only valid for the formal v4 canary amendment")
    _require_exact_output_dir(
        output_dir,
        _diagnostic_output_dir(manifest),
        purpose="diagnostics",
    )
    if any(output_dir.rglob("*.jsonl")):
        raise RunnerError("Endpoint diagnostics must never create a formal ledger")
    _require_diagnostic_layout(manifest, output_dir=output_dir)
    _verify_legacy_terminal(manifest)
    container_ids = _formal_container_ids()
    if container_ids is None:
        raise RunnerError("Formal container reconciliation failed before endpoint diagnostics")
    if container_ids:
        raise RunnerError("Residual formal containers block endpoint diagnostics")
    if _diagnostic_summary_path(output_dir).exists():
        return _load_diagnostic_summary(
            manifest,
            output_dir=output_dir,
            require_passed=False,
        )
    if not _runner._running_inside_compose_dood(repo_root):
        raise RunnerError("Endpoint diagnostics must run inside the frozen Compose/DooD control plane")
    preflight = _original_collect_preflight(
        manifest,
        repo_root=repo_root,
        manifest_path=manifest_path,
        output_dir=output_dir,
        check_endpoint=False,
    )
    if preflight["ready"] is not True:
        raise RunnerError("The non-model diagnostic preflight is not ready")

    diagnostic = manifest["authorization"]["diagnostics"]
    for provider in diagnostic["providers"]:
        if not _diagnostic_model_config_matches(manifest, provider):
            raise RunnerError("The configured diagnostic model does not match the frozen policy")
        records = _existing_diagnostic_attempts(
            manifest,
            output_dir=output_dir,
            provider=provider,
        )
        if records and records[-1]["passed"]:
            continue
        while len(records) < diagnostic["maximum_attempts_per_provider"]:
            attempt = len(records) + 1
            started_at = datetime.now(UTC).isoformat()
            attempt_path = _diagnostic_attempt_path(
                output_dir,
                condition_id=provider["condition_id"],
                attempt=attempt,
            )
            record = {
                "schema_version": "formal-endpoint-diagnostic-attempt-1.0.0",
                "document_type": "formal_endpoint_diagnostic_attempt",
                "benchmark_id": manifest["benchmark"]["id"],
                "manifest_sha256": protocol.manifest_sha256(manifest),
                "condition_id": provider["condition_id"],
                "provider": provider["provider"],
                "model": provider["model"],
                "attempt": attempt,
                "status": "started",
                "started_at": started_at,
                "completed_at": None,
                "duration_ms": None,
                "response_nonempty": False,
                "error_class": None,
                "passed": False,
            }
            _write_json_exclusive(attempt_path, record)
            started = time.perf_counter()
            response_nonempty = False
            error_class: str | None = None
            try:
                response_nonempty = request_issuer(
                    provider["model"],
                    diagnostic["prompt"],
                    diagnostic["max_output_tokens"],
                )
            except Exception as exc:
                error_class = _bounded_error_class(exc)
            completed_at = datetime.now(UTC).isoformat()
            record.update(
                {
                    "status": ("passed" if error_class is None and response_nonempty else "failed"),
                    "completed_at": completed_at,
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                    "response_nonempty": response_nonempty,
                    "error_class": error_class,
                    "passed": error_class is None and response_nonempty,
                }
            )
            _write_json_exclusive(
                _diagnostic_terminal_path(
                    output_dir,
                    condition_id=provider["condition_id"],
                    attempt=attempt,
                ),
                record,
            )
            records.append(record)
            if record["passed"]:
                break

    summary = _build_diagnostic_summary(manifest, output_dir=output_dir)
    _write_json_exclusive(_diagnostic_summary_path(output_dir), summary)
    return summary


def _canary_marker_path(output_dir: Path) -> Path:
    return output_dir / "provider-canaries" / _CANARY_ATTEMPT_MARKER


def _write_canary_marker(
    path: Path,
    *,
    manifest: dict[str, Any],
    status: str,
    error_class: str | None = None,
) -> None:
    marker = {
        "schema_version": "formal-provider-canary-attempt-1.0.0",
        "document_type": "formal_provider_canary_attempt",
        "benchmark_id": manifest["benchmark"]["id"],
        "manifest_sha256": protocol.manifest_sha256(manifest),
        "status": status,
        "error_class": error_class,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(marker, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _require_successful_canary(manifest: dict[str, Any], *, output_dir: Path) -> None:
    try:
        marker = json.loads(_canary_marker_path(output_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunnerError("The formal v4 amendment canary marker is missing or invalid") from exc
    if marker.get("benchmark_id") != manifest["benchmark"]["id"] or marker.get("manifest_sha256") != protocol.manifest_sha256(manifest) or marker.get("status") != "passed":
        raise RunnerError("A successful formal v4 amendment canary is required")
    if _runner._successful_provider_canary(manifest, output_dir=output_dir) is None:
        raise RunnerError("A successful dual-provider canary report is required")


def collect_provider_canary(
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    output_dir: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    if manifest.get("schema_version") != protocol.SCHEMA_VERSION:
        raise RunnerError("Provider canary is only valid for the formal v4 canary amendment")
    _require_exact_output_dir(output_dir, _formal_output_dir(manifest), purpose="evidence")
    _verify_legacy_terminal(manifest)
    _load_diagnostic_summary(manifest, require_passed=True)
    if any(output_dir.rglob("*.jsonl")):
        raise RunnerError("Provider canary requires an empty formal ledger directory")
    if _observed_authorized_ledgers(manifest, output_dir=output_dir):
        raise RunnerError("Provider canary must complete before the first formal ledger is created")
    container_ids = _formal_container_ids()
    if container_ids is None:
        raise RunnerError("Formal container reconciliation failed before provider canary")
    if container_ids:
        raise RunnerError("Residual formal containers block provider canary")

    marker_path = _canary_marker_path(output_dir)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    if not marker_path.exists() and any(marker_path.parent.glob("*.json")):
        raise RunnerError("An orphan provider-canary report blocks the amended canary")
    try:
        _write_json_exclusive(
            marker_path,
            {
                "schema_version": "formal-provider-canary-attempt-1.0.0",
                "document_type": "formal_provider_canary_attempt",
                "benchmark_id": manifest["benchmark"]["id"],
                "manifest_sha256": protocol.manifest_sha256(manifest),
                "status": "started",
                "error_class": None,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )
    except FileExistsError as exc:
        raise RunnerError("The one amended provider-canary attempt has already been consumed") from exc

    try:
        with _anonymous_endpoint_preflight_disabled():
            report = _original_collect_provider_canary(
                manifest,
                manifest_path=manifest_path,
                output_dir=output_dir,
                repo_root=repo_root,
            )
    except BaseException as exc:
        _write_canary_marker(
            marker_path,
            manifest=manifest,
            status="failed",
            error_class=_bounded_error_class(exc),
        )
        raise
    _write_canary_marker(
        marker_path,
        manifest=manifest,
        status="passed" if report["passed"] else "failed",
    )
    return report


def create_attempt(
    manifest: dict[str, Any],
    *,
    case_id: str,
    condition_id: str,
    repetition: int,
    output_dir: Path,
    **kwargs: Any,
):
    if manifest.get("schema_version") == protocol.SCHEMA_VERSION:
        _require_exact_output_dir(output_dir, _formal_output_dir(manifest), purpose="evidence")
        _verify_legacy_terminal(manifest)
        _load_diagnostic_summary(manifest, require_passed=True)
        _require_successful_canary(manifest, output_dir=output_dir)
        _ensure_token_budget_remaining(manifest, output_dir=output_dir)
        _enforce_authorized_order(
            manifest,
            case_id=case_id,
            condition_id=condition_id,
            repetition=repetition,
            output_dir=output_dir,
        )
        if kwargs.get("replacement_for") is not None:
            raise RunnerError("The formal v4 amendment forbids replacement attempts")
        kwargs["check_endpoint"] = False
        with _base_order_gate_already_checked():
            return _original_create_attempt(
                manifest,
                case_id=case_id,
                condition_id=condition_id,
                repetition=repetition,
                output_dir=output_dir,
                **kwargs,
            )
    return _original_create_attempt(
        manifest,
        case_id=case_id,
        condition_id=condition_id,
        repetition=repetition,
        output_dir=output_dir,
        **kwargs,
    )


def run_attempt(
    manifest: dict[str, Any],
    ledger_path: Path,
    **kwargs: Any,
) -> dict[str, Any]:
    if manifest.get("schema_version") == protocol.SCHEMA_VERSION:
        expected = _formal_output_dir(manifest).resolve(strict=False)
        try:
            ledger_path.resolve(strict=False).relative_to(expected)
        except ValueError as exc:
            raise RunnerError("Formal v4 amendment ledger is outside the authorized evidence directory") from exc
        _verify_legacy_terminal(manifest)
        _load_diagnostic_summary(manifest, require_passed=True)
        _require_successful_canary(manifest, output_dir=expected)
        _ensure_token_budget_remaining(manifest, output_dir=expected)
        kwargs["attempt_budget"] = _runner.ExperimentAttemptBudget.from_mapping(manifest["attempt_budget"])
    return _original_run_attempt(manifest, ledger_path, **kwargs)


def run_formal_batch(
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    output_dir: Path,
    max_attempts: int,
    check_endpoint: bool = True,
) -> dict[str, Any]:
    del check_endpoint
    if manifest.get("schema_version") != protocol.SCHEMA_VERSION:
        raise RunnerError("Batch execution is only valid for the formal v4 canary amendment")
    _require_exact_output_dir(output_dir, _formal_output_dir(manifest), purpose="evidence")
    _verify_legacy_terminal(manifest)
    _load_diagnostic_summary(manifest, require_passed=True)
    _require_successful_canary(manifest, output_dir=output_dir)
    authorized_slots = _authorized_slots(manifest)
    if max_attempts < 1 or max_attempts > len(authorized_slots):
        raise RunnerError(f"Batch execution must request between 1 and {len(authorized_slots)} attempts")
    observed = _observed_authorized_ledgers(manifest, output_dir=output_dir)
    observed_slots = [slot for slot, _events in observed]
    planned_slots = [_slot_identity(slot) for slot in authorized_slots]
    if observed_slots != planned_slots[: len(observed_slots)]:
        raise RunnerError("Existing physical evidence does not match the authorized slot order")
    if observed and observed[-1][1][-1]["event"] != "experiment.completed":
        raise RunnerError("The previous authorized slot must complete before batch execution resumes")
    start_index = len(observed_slots)
    if start_index >= len(authorized_slots):
        raise RunnerError("The authorized six-slot boundary has already been reached")
    if max_attempts > len(authorized_slots) - start_index:
        raise RunnerError("The requested batch would cross the authorized six-slot boundary")

    results: list[dict[str, Any]] = []
    stop_reason = "authorized_complete_project_block_reached"
    with asyncio.Runner() as async_runner:
        for authorized_index in range(start_index, start_index + max_attempts):
            recorded_before = _ensure_token_budget_remaining(
                manifest,
                output_dir=output_dir,
            )
            slot = authorized_slots[authorized_index]
            ledger, _preflight = create_attempt(
                manifest,
                case_id=slot["case_id"],
                condition_id=slot["condition_id"],
                repetition=slot["repetition"],
                output_dir=output_dir,
                manifest_path=manifest_path,
                check_endpoint=False,
            )
            result = run_attempt(
                manifest,
                ledger.path,
                async_runner=async_runner,
            )
            recorded_after = _recorded_total_tokens(_observed_authorized_ledgers(manifest, output_dir=output_dir))
            results.append(
                {
                    "authorized_index": authorized_index,
                    "schedule_order": slot["order"],
                    "case_id": slot["case_id"],
                    "condition_id": slot["condition_id"],
                    "repetition": slot["repetition"],
                    "physical_attempt_id": ledger.physical_attempt_id,
                    "ledger": str(ledger.path),
                    "status": result["status"],
                    "recorded_tokens_before": recorded_before,
                    "recorded_tokens_after": recorded_after,
                }
            )
            if recorded_after >= _token_limit(manifest):
                stop_reason = "recorded_token_boundary_reached"
                break
    return {
        "status": stop_reason,
        "benchmark_id": manifest["benchmark"]["id"],
        "manifest_sha256": protocol.manifest_sha256(manifest),
        "start_authorized_index": start_index,
        "next_authorized_index": start_index + len(results),
        "authorized_slot_count": len(authorized_slots),
        "attempts_completed": len(results),
        "recorded_total_tokens": (results[-1]["recorded_tokens_after"] if results else _recorded_total_tokens(observed)),
        "recorded_token_limit": _token_limit(manifest),
        "results": results,
    }


_runner.collect_runtime_launch_preflight = collect_runtime_launch_preflight
_runner._manifest_protocol = _manifest_protocol
_runner.build_policy = build_policy
_runner.collect_provider_canary = collect_provider_canary
_runner.create_attempt = create_attempt
_runner.run_attempt = run_attempt
_runner.run_formal_batch = run_formal_batch


def _arguments_with_default_manifest(argv: list[str]) -> list[str]:
    if not argv or argv[0] == "runtime-preflight" or "--manifest" in argv:
        return argv
    return [argv[0], "--manifest", str(DEFAULT_MANIFEST), *argv[1:]]


def _diagnostic_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="执行 formal v4 有限端点诊断")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "endpoint-diagnostics":
        args = _diagnostic_parser().parse_args(arguments[1:])
        try:
            manifest = _runner._load_manifest(args.manifest)
            result = collect_endpoint_diagnostics(
                manifest,
                manifest_path=args.manifest,
                output_dir=args.output_dir,
            )
            _runner._json_print(result)
            return 0 if result["passed"] else 2
        except (_runner.EvidenceError, RunnerError, OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    return _runner.main(_arguments_with_default_manifest(arguments))


def __getattr__(name: str):
    return getattr(_runner, name)


if __name__ == "__main__":
    raise SystemExit(main())
