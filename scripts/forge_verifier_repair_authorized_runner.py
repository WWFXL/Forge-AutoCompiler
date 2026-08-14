#!/usr/bin/env python3
"""执行已授权的 verifier-driven repair 配对 pilot。"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_verifier_repair_authorized_protocol as protocol  # noqa: E402
import forge_verifier_repair_runtime as repair_runtime  # noqa: E402

# 协议模块先建立仓库导入根，再加载 Ubuntu daemon 门禁。
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
_original_collect_provider_canary = _runner.collect_provider_canary
_original_create_attempt = _runner.create_attempt
_original_run_attempt = _runner.run_attempt

_runner.protocol_formal_collection = protocol

RunnerError = _runner.RunnerError
REPO_ROOT = _runner.REPO_ROOT
DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
_CANARY_ATTEMPT_MARKER = "verifier-repair-provider-canary-attempt.json"
_SIDECAR_SUFFIX = ".repair-sidecar.json"
_NETWORK_ACCESS_MEDIA = {"mobile_hotspot", "wifi", "ethernet", "other"}
_MISSING = object()


def _manifest_protocol(manifest: dict[str, Any]):
    if manifest.get("schema_version") == protocol.SCHEMA_VERSION:
        return protocol
    return _original_manifest_protocol(manifest)


def collect_runtime_launch_preflight(
    output_dir: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    return ubuntu_runner.collect_runtime_launch_preflight(
        output_dir,
        repo_root=repo_root,
    )


def _authorized_output_dir(manifest: dict[str, Any]) -> Path:
    return Path(manifest["authorization"]["collection_constraints"]["evidence_directory"])


def _require_authorized_output_dir(manifest: dict[str, Any], output_dir: Path) -> None:
    expected = _authorized_output_dir(manifest).resolve(strict=False)
    if output_dir.resolve(strict=False) != expected:
        raise RunnerError("Verifier-repair evidence must use the frozen authorized directory")


def _authorized_slots(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(manifest["collection_plan"], key=lambda slot: slot["order"])


def _slot_identity(slot: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": slot["case_id"],
        "condition_id": slot["condition_id"],
        "repetition": slot["repetition"],
    }


def _observed_ledgers(manifest: dict[str, Any], *, output_dir: Path) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    return _runner._observed_collection_ledgers(manifest, output_dir=output_dir)


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


def _ensure_pair_budget_remaining(manifest: dict[str, Any], *, output_dir: Path, observed_count: int) -> int:
    recorded = _recorded_total_tokens(_observed_ledgers(manifest, output_dir=output_dir))
    # 已开始 pair 的第二个 arm 必须先闭合；新 pair 只能在边界以下开始。
    if observed_count % 2 == 0 and recorded >= _token_limit(manifest):
        raise RunnerError("The authorized recorded-token boundary blocks a new complete pair")
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
    observed = _observed_ledgers(manifest, output_dir=output_dir)
    observed_slots = [slot for slot, _events in observed]
    if observed_slots != plan[: len(observed_slots)]:
        raise RunnerError("Existing physical evidence does not match the authorized schedule")
    if observed and observed[-1][1][-1]["event"] != "experiment.completed":
        raise RunnerError("The previous authorized slot must complete before the next slot")
    if len(observed_slots) >= len(plan):
        raise RunnerError("All 12 authorized slots already have physical evidence")
    requested = {
        "case_id": case_id,
        "condition_id": condition_id,
        "repetition": repetition,
    }
    if requested != plan[len(observed_slots)]:
        raise RunnerError("The requested slot is not next in the authorized schedule")
    _ensure_pair_budget_remaining(manifest, output_dir=output_dir, observed_count=len(observed_slots))
    return len(observed_slots)


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


def _canary_marker_path(output_dir: Path) -> Path:
    return output_dir / "provider-canaries" / _CANARY_ATTEMPT_MARKER


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _write_canary_marker(
    path: Path,
    *,
    manifest: dict[str, Any],
    status: str,
    error_class: str | None = None,
) -> None:
    _write_json_atomic(
        path,
        {
            "schema_version": "verifier-repair-canary-attempt-1.0.0",
            "document_type": "verifier_repair_provider_canary_attempt",
            "benchmark_id": manifest["benchmark"]["id"],
            "manifest_sha256": protocol.manifest_sha256(manifest),
            "status": status,
            "error_class": error_class,
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )


def _model_response_text(response: Any) -> str:
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "".join(item if isinstance(item, str) else item.get("text", "") for item in content if isinstance(item, (str, dict)))


def _restore_model_config_value(configured: Any, name: str, value: Any) -> None:
    if value is _MISSING:
        try:
            delattr(configured, name)
        except AttributeError:
            pass
        return
    setattr(configured, name, value)


def _create_provider_canary_model(profile: dict[str, Any]):
    from deerflow.config import get_app_config
    from deerflow.models.factory import create_chat_model

    model_name = profile["roles"]["lead"]
    configured = get_app_config().get_model_config(model_name)
    if configured is None or configured.model != model_name:
        raise RunnerError(
            "Provider canary model configuration does not match the frozen profile"
        )
    settings = configured.model_dump(exclude_none=True)
    endpoint = settings.get("base_url", settings.get("openai_api_base"))
    if endpoint is None or str(endpoint).rstrip("/") != profile["endpoint"].rstrip("/"):
        raise RunnerError("Provider canary endpoint does not match the frozen profile")

    expected_timeout = float(profile["request_timeout_seconds"])
    original_timeout = getattr(configured, "request_timeout", _MISSING)
    original_retries = getattr(configured, "max_retries", _MISSING)
    try:
        configured.request_timeout = expected_timeout
        configured.max_retries = 0
        model = create_chat_model(name=model_name, thinking_enabled=False)
    finally:
        _restore_model_config_value(configured, "request_timeout", original_timeout)
        _restore_model_config_value(configured, "max_retries", original_retries)

    try:
        effective_timeout = float(model.request_timeout)
        effective_retries = int(model.max_retries)
    except (AttributeError, TypeError, ValueError) as exc:
        raise RunnerError(
            "Provider canary model does not expose its effective request policy"
        ) from exc
    if effective_timeout != expected_timeout or effective_retries != 0:
        raise RunnerError(
            "Provider canary model did not apply the frozen request policy"
        )
    return model


def _invoke_provider_canary(profile: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    error_class: str | None = None
    response_text = ""
    try:
        model = _create_provider_canary_model(profile)
        response = model.invoke("Reply with exactly CANARY_OK and nothing else.")
        response_text = _model_response_text(response)
    except Exception as exc:
        error_class = type(exc).__name__
    return {
        "model": profile["roles"]["lead"],
        "endpoint": profile["endpoint"].rstrip("/"),
        "credential_env": profile["credential_env"],
        "request_timeout_seconds": profile["request_timeout_seconds"],
        "max_retries": 0,
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "response_nonempty": bool(response_text.strip()),
        "response_sha256": (hashlib.sha256(response_text.encode("utf-8")).hexdigest() if response_text else None),
        "error_class": error_class,
        "passed": error_class is None and bool(response_text.strip()),
    }


def collect_provider_canary(
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    output_dir: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    if manifest.get("schema_version") != protocol.SCHEMA_VERSION:
        raise RunnerError("Provider canary requires the authorized repair protocol")
    _require_authorized_output_dir(manifest, output_dir)
    access_medium = os.environ.get("FORGE_NETWORK_ACCESS_MEDIUM")
    if access_medium not in _NETWORK_ACCESS_MEDIA:
        raise RunnerError("Provider canary requires a confirmed FORGE_NETWORK_ACCESS_MEDIUM")
    if any(output_dir.rglob("*.jsonl")) or any(output_dir.rglob(f"*{_SIDECAR_SUFFIX}")):
        raise RunnerError("Provider canary requires an empty evidence directory")
    if _observed_ledgers(manifest, output_dir=output_dir):
        raise RunnerError("Provider canary must precede the first pilot ledger")
    container_ids = _formal_container_ids()
    if container_ids is None:
        raise RunnerError("Formal container reconciliation failed before canary")
    if container_ids:
        raise RunnerError("Residual formal containers block provider canary")
    if not _runner._running_inside_compose_dood(repo_root):
        raise RunnerError("Provider canary must run inside the Compose/DooD control plane")

    marker_path = _canary_marker_path(output_dir)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with marker_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(
                {
                    "schema_version": "verifier-repair-canary-attempt-1.0.0",
                    "document_type": "verifier_repair_provider_canary_attempt",
                    "benchmark_id": manifest["benchmark"]["id"],
                    "manifest_sha256": protocol.manifest_sha256(manifest),
                    "status": "started",
                    "error_class": None,
                    "updated_at": datetime.now(UTC).isoformat(),
                },
                stream,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            stream.write("\n")
    except FileExistsError as exc:
        raise RunnerError("The one authorized provider-canary attempt is consumed") from exc

    try:
        preflight = _runner.collect_preflight(
            manifest,
            repo_root=repo_root,
            manifest_path=manifest_path,
            output_dir=output_dir,
            check_endpoint=False,
        )
        if preflight["ready"] is not True:
            raise RunnerError("Provider canary preflight is not ready")
        provider_results = {provider: {"id": provider, **_invoke_provider_canary(profile)} for provider, profile in manifest["model_profiles"].items()}
        condition_results = [
            {
                "id": condition["id"],
                "provider_condition": condition["provider_condition"],
                "treatment": condition["treatment"],
                **{key: value for key, value in provider_results[condition["provider_condition"]].items() if key != "id"},
            }
            for condition in manifest["conditions"]
        ]
        report = {
            "schema_version": "formal-provider-canary-1.0.0",
            "document_type": "formal_provider_canary",
            "canary_id": _runner.new_evidence_id("provider_canary"),
            "benchmark_id": manifest["benchmark"]["id"],
            "manifest_sha256": protocol.manifest_sha256(manifest),
            "manifest_file_sha256": _runner._sha256_file(manifest_path),
            "completed_at": datetime.now(UTC).isoformat(),
            "control_plane_topology": protocol.CONTROL_PLANE_TOPOLOGY,
            "preflight_ready": True,
            "network_access_medium": access_medium,
            "provider_request_count": len(provider_results),
            "providers": list(provider_results.values()),
            "conditions": condition_results,
            "passed": all(result["passed"] for result in provider_results.values()),
        }
        report_path = output_dir / "provider-canaries" / f"{report['canary_id']}.json"
        with report_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
    except BaseException as exc:
        _write_canary_marker(
            marker_path,
            manifest=manifest,
            status="failed",
            error_class=type(exc).__name__,
        )
        raise
    _write_canary_marker(
        marker_path,
        manifest=manifest,
        status="passed" if report["passed"] else "failed",
    )
    return {**report, "report_path": str(report_path)}


def create_attempt(
    manifest: dict[str, Any],
    *,
    case_id: str,
    condition_id: str,
    repetition: int,
    output_dir: Path,
    **kwargs: Any,
):
    if manifest.get("schema_version") != protocol.SCHEMA_VERSION:
        return _original_create_attempt(
            manifest,
            case_id=case_id,
            condition_id=condition_id,
            repetition=repetition,
            output_dir=output_dir,
            **kwargs,
        )
    _require_authorized_output_dir(manifest, output_dir)
    if kwargs.get("replacement_for") is not None:
        raise RunnerError("Verifier-repair authorization forbids replacement")
    _enforce_authorized_order(
        manifest,
        case_id=case_id,
        condition_id=condition_id,
        repetition=repetition,
        output_dir=output_dir,
    )
    return _original_create_attempt(
        manifest,
        case_id=case_id,
        condition_id=condition_id,
        repetition=repetition,
        output_dir=output_dir,
        **kwargs,
    )


def _slot_for_policy(manifest: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    matches = [slot for slot in manifest["collection_plan"] if slot["case_id"] == policy.get("case_id") and slot["condition_id"] == policy.get("condition") and slot["repetition"] == policy.get("repetition")]
    if len(matches) != 1:
        raise RunnerError("The physical-attempt policy has no unique repair slot")
    return matches[0]


def repair_sidecar_path(ledger_path: Path) -> Path:
    return ledger_path.with_name(ledger_path.stem + _SIDECAR_SUFFIX)


def _feedback_context(
    manifest: dict[str, Any],
    ledger: Any,
    slot: dict[str, Any],
    evidence: repair_runtime.RepairEvidenceLedger,
) -> repair_runtime.RepairFeedbackContext:
    case = next(item for item in manifest["cases"] if item["id"] == slot["case_id"])
    expected_artifacts = tuple((artifact["relative_path"], artifact["artifact_type"]) for artifact in case["oracle"]["required_artifacts"])
    thread_id = ledger.read()[0]["payload"]["thread_id"]
    return repair_runtime.RepairFeedbackContext(
        thread_id=thread_id,
        pair_id=slot["pair_id"],
        case_id=slot["case_id"],
        provider_condition=slot["provider_condition"],
        treatment=slot["treatment"],
        repetition=slot["repetition"],
        expected_build_system=case["build_system"],
        expected_artifacts=expected_artifacts,
        event_reader=ledger.read,
        evidence=evidence,
    )


def run_attempt(manifest: dict[str, Any], ledger_path: Path, **kwargs: Any) -> dict[str, Any]:
    if manifest.get("schema_version") != protocol.SCHEMA_VERSION:
        return _original_run_attempt(manifest, ledger_path, **kwargs)
    expected = _authorized_output_dir(manifest).resolve(strict=False)
    try:
        ledger_path.resolve(strict=False).relative_to(expected)
    except ValueError as exc:
        raise RunnerError("Repair pilot ledger is outside the authorized directory") from exc
    ledger = _runner.ExperimentLedger.open(ledger_path)
    events = ledger.read()
    if any(event["event"].startswith("model.") for event in events):
        raise RunnerError("A physical attempt cannot issue model calls twice")
    slot = _slot_for_policy(manifest, events[0]["payload"]["policy"])
    sidecar_path = repair_sidecar_path(ledger_path)
    evidence = repair_runtime.RepairEvidenceLedger.create(
        sidecar_path,
        {
            "manifest_sha256": protocol.manifest_sha256(manifest),
            "thread_id": events[0]["payload"]["thread_id"],
            "physical_attempt_id": ledger.physical_attempt_id,
            "order": slot["order"],
            "pair_id": slot["pair_id"],
            "case_id": slot["case_id"],
            "provider_condition": slot["provider_condition"],
            "treatment": slot["treatment"],
            "repetition": slot["repetition"],
        },
    )
    context = _feedback_context(manifest, ledger, slot, evidence)
    kwargs["attempt_budget"] = _runner.ExperimentAttemptBudget.from_mapping(manifest["attempt_budget"])
    from deerflow.tools import bound_compile_tools

    try:
        with repair_runtime.submit_feedback_scope(context, bound_compile_tools):
            result = _original_run_attempt(manifest, ledger_path, **kwargs)
    except BaseException:
        evidence.append("repair.context_completed", {"status": "interrupted"})
        raise
    evidence.append("repair.context_completed", {"status": str(result["status"])})
    result["repair_sidecar"] = str(sidecar_path)
    result["repair_fidelity"] = repair_runtime.evaluate_treatment_fidelity(evidence.read())
    return result


def run_repair_batch(
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    output_dir: Path,
    max_attempts: int,
    check_endpoint: bool = True,
) -> dict[str, Any]:
    if manifest.get("schema_version") != protocol.SCHEMA_VERSION:
        raise RunnerError("Repair batch requires the authorized protocol identity")
    _require_authorized_output_dir(manifest, output_dir)
    slots = _authorized_slots(manifest)
    observed = _observed_ledgers(manifest, output_dir=output_dir)
    observed_slots = [slot for slot, _events in observed]
    planned = [_slot_identity(slot) for slot in slots]
    if observed_slots != planned[: len(observed_slots)]:
        raise RunnerError("Existing evidence does not match the authorized schedule")
    if observed and observed[-1][1][-1]["event"] != "experiment.completed":
        raise RunnerError("The previous slot must complete before batch resume")
    start_index = len(observed_slots)
    if start_index >= len(slots):
        raise RunnerError("The authorized 12-slot boundary has been reached")
    if max_attempts < 1 or max_attempts > len(slots) - start_index:
        raise RunnerError("Requested batch crosses the authorized 12-slot boundary")
    if (start_index + max_attempts) % 2 != 0:
        raise RunnerError("Requested batch must stop on a complete-pair boundary")

    results: list[dict[str, Any]] = []
    stop_reason = "requested_attempt_boundary_reached"
    with asyncio.Runner() as async_runner:
        for slot_index in range(start_index, start_index + max_attempts):
            recorded_before = _ensure_pair_budget_remaining(
                manifest,
                output_dir=output_dir,
                observed_count=slot_index,
            )
            slot = slots[slot_index]
            ledger, _preflight = create_attempt(
                manifest,
                case_id=slot["case_id"],
                condition_id=slot["condition_id"],
                repetition=slot["repetition"],
                output_dir=output_dir,
                manifest_path=manifest_path,
                check_endpoint=check_endpoint,
            )
            result = run_attempt(
                manifest,
                ledger.path,
                async_runner=async_runner,
            )
            recorded_after = _recorded_total_tokens(_observed_ledgers(manifest, output_dir=output_dir))
            results.append(
                {
                    "schedule_order": slot["order"],
                    "pair_id": slot["pair_id"],
                    "case_id": slot["case_id"],
                    "provider_condition": slot["provider_condition"],
                    "treatment": slot["treatment"],
                    "condition_id": slot["condition_id"],
                    "physical_attempt_id": ledger.physical_attempt_id,
                    "ledger": str(ledger.path),
                    "repair_sidecar": result["repair_sidecar"],
                    "status": result["status"],
                    "fidelity_status": result["repair_fidelity"]["status"],
                    "recorded_tokens_before": recorded_before,
                    "recorded_tokens_after": recorded_after,
                }
            )
            next_index = slot_index + 1
            if next_index == len(slots):
                stop_reason = "authorized_six_complete_pairs_reached"
                break
            if next_index % 2 == 0 and recorded_after >= _token_limit(manifest):
                stop_reason = "recorded_token_pair_boundary_reached"
                break
    return {
        "status": stop_reason,
        "benchmark_id": manifest["benchmark"]["id"],
        "manifest_sha256": protocol.manifest_sha256(manifest),
        "start_slot_index": start_index,
        "next_slot_index": start_index + len(results),
        "authorized_slot_count": len(slots),
        "attempts_completed": len(results),
        "complete_pairs_observed": (start_index + len(results)) // 2,
        "recorded_total_tokens": (results[-1]["recorded_tokens_after"] if results else _recorded_total_tokens(observed)),
        "recorded_token_limit": _token_limit(manifest),
        "results": results,
    }


_runner.collect_runtime_launch_preflight = collect_runtime_launch_preflight
_runner._manifest_protocol = _manifest_protocol
_runner.collect_provider_canary = collect_provider_canary
_runner.create_attempt = create_attempt
_runner.run_attempt = run_attempt
_runner.run_formal_batch = run_repair_batch


def _arguments_with_default_manifest(argv: list[str]) -> list[str]:
    if not argv or argv[0] == "runtime-preflight" or "--manifest" in argv:
        return argv
    return [argv[0], "--manifest", str(DEFAULT_MANIFEST), *argv[1:]]


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    return _runner.main(_arguments_with_default_manifest(arguments))


def __getattr__(name: str):
    return getattr(_runner, name)


if __name__ == "__main__":
    raise SystemExit(main())
