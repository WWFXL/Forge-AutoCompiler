#!/usr/bin/env python3
"""执行 formal v4 已授权的首批完整项目块。"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import subprocess
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_formal_collection_v4_authorized_protocol as protocol  # noqa: E402

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
_original_collect_provider_canary = _runner.collect_provider_canary
_original_create_attempt = _runner.create_attempt
_original_run_attempt = _runner.run_attempt

_runner.protocol_formal_collection = protocol

RunnerError = _runner.RunnerError
REPO_ROOT = _runner.REPO_ROOT
DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
_CANARY_ATTEMPT_MARKER = "formal-v4-provider-canary-attempt.json"


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


def _authorized_output_dir(manifest: dict[str, Any]) -> Path:
    return Path(manifest["authorization"]["collection_constraints"]["evidence_directory"])


def _require_authorized_output_dir(
    manifest: dict[str, Any],
    output_dir: Path,
) -> None:
    if output_dir.resolve(strict=False) != _authorized_output_dir(manifest).resolve(strict=False):
        raise RunnerError("Formal v4 evidence must use the frozen authorized evidence directory")


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


def collect_provider_canary(
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    output_dir: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    if manifest.get("schema_version") != protocol.SCHEMA_VERSION:
        raise RunnerError("Provider canary is only valid for the authorized formal v4 collection")
    _require_authorized_output_dir(manifest, output_dir)
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
    try:
        with marker_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(
                {
                    "schema_version": "formal-provider-canary-attempt-1.0.0",
                    "document_type": "formal_provider_canary_attempt",
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
        raise RunnerError("The one authorized provider-canary attempt has already been consumed") from exc

    try:
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
            error_class=type(exc).__name__,
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
        _require_authorized_output_dir(manifest, output_dir)
        _ensure_token_budget_remaining(manifest, output_dir=output_dir)
        _enforce_authorized_order(
            manifest,
            case_id=case_id,
            condition_id=condition_id,
            repetition=repetition,
            output_dir=output_dir,
        )
        if kwargs.get("replacement_for") is not None:
            raise RunnerError("The formal v4 authorization forbids replacement attempts")
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
        expected = _authorized_output_dir(manifest).resolve(strict=False)
        try:
            ledger_path.resolve(strict=False).relative_to(expected)
        except ValueError as exc:
            raise RunnerError("Formal v4 ledger is outside the authorized evidence directory") from exc
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
    if manifest.get("schema_version") != protocol.SCHEMA_VERSION:
        raise RunnerError("Batch execution is only valid for the authorized formal v4 collection")
    _require_authorized_output_dir(manifest, output_dir)
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
                check_endpoint=check_endpoint,
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


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    return _runner.main(_arguments_with_default_manifest(arguments))


def __getattr__(name: str):
    return getattr(_runner, name)


if __name__ == "__main__":
    raise SystemExit(main())
