#!/usr/bin/env python3
"""Authorized initial-batch adapter for the Forge formal-collection v3 runner."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import posixpath
import sys
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_formal_collection_v3_authorized_protocol as protocol  # noqa: E402


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
_original_collect_runtime_launch_preflight = _runner.collect_runtime_launch_preflight
_original_collect_provider_canary = _runner.collect_provider_canary
_original_create_attempt = _runner.create_attempt
_original_run_attempt = _runner.run_attempt

_runner.protocol_formal_collection = protocol

RunnerError = _runner.RunnerError
REPO_ROOT = _runner.REPO_ROOT
DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
_EVIDENCE_MOUNT_ROOT = Path("/workspace/.compile-sessions")


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
    policy = _original_build_policy(
        manifest,
        case_id=case_id,
        condition_id=condition_id,
        repetition=repetition,
    )
    if manifest.get("schema_version") != protocol.SCHEMA_VERSION:
        return policy
    case = _runner._manifest_case(manifest, case_id)
    artifacts = tuple(
        (
            artifact["relative_path"],
            artifact.get("build_output_path", artifact["relative_path"]),
            artifact["artifact_type"],
        )
        for artifact in case["oracle"]["required_artifacts"]
    )
    return replace(policy, artifact_instructions=artifacts)


def _evidence_mount_source_matches_host_workspace(
    mounts: list[dict[str, Any]] | None,
    *,
    host_workspace_root: str | None = None,
) -> bool:
    root = host_workspace_root if host_workspace_root is not None else os.environ.get("DEER_FLOW_HOST_WORKSPACE_ROOT")
    if not isinstance(root, str) or not root.strip():
        return False
    normalized_root = posixpath.normpath(root.strip())
    if not PurePosixPath(normalized_root).is_absolute() or normalized_root == "/":
        return False
    expected_source = posixpath.join(normalized_root, ".compile-sessions")
    evidence_mounts = [mount for mount in mounts or [] if mount.get("Type") == "bind" and mount.get("Destination") == _EVIDENCE_MOUNT_ROOT.as_posix() and mount.get("RW") is True]
    if len(evidence_mounts) != 1:
        return False
    source = evidence_mounts[0].get("Source")
    return isinstance(source, str) and PurePosixPath(posixpath.normpath(source)).is_absolute() and posixpath.normpath(source) == expected_source


def collect_runtime_launch_preflight(
    output_dir: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    result = _original_collect_runtime_launch_preflight(
        output_dir,
        repo_root=repo_root,
    )
    _labels, mounts = _runner._current_container_metadata(repo_root)
    source_matches = _evidence_mount_source_matches_host_workspace(mounts)
    checks = {
        **result["checks"],
        "evidence_mount_source_matches_host_workspace": source_matches,
    }
    return {
        **result,
        "ready": result["ready"] is True and source_matches,
        "checks": checks,
    }


def _authorized_slot_count(manifest: dict[str, Any]) -> int:
    return int(manifest["authorization"]["collection_constraints"]["authorized_slot_count"])


def _authorized_output_dir(manifest: dict[str, Any]) -> Path:
    return Path(manifest["authorization"]["collection_constraints"]["evidence_directory"])


def _require_authorized_output_dir(
    manifest: dict[str, Any],
    output_dir: Path,
) -> None:
    expected = _authorized_output_dir(manifest)
    if output_dir.resolve(strict=False) != expected.resolve(strict=False):
        raise RunnerError("Formal v3 evidence must use the frozen authorized evidence directory")


def _slot_index(
    manifest: dict[str, Any],
    *,
    case_id: str,
    condition_id: str,
    repetition: int,
) -> int:
    target = {
        "case_id": case_id,
        "condition_id": condition_id,
        "repetition": repetition,
    }
    for index, slot in enumerate(manifest["collection_plan"]):
        if {
            "case_id": slot["case_id"],
            "condition_id": slot["condition_id"],
            "repetition": slot["repetition"],
        } == target:
            return index
    raise RunnerError("The requested slot is not part of the frozen collection")


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
    return _runner._observed_collection_ledgers(
        manifest,
        output_dir=output_dir,
    )


def _ensure_token_budget_remaining(
    manifest: dict[str, Any],
    *,
    output_dir: Path,
) -> int:
    observed = _observed_authorized_ledgers(manifest, output_dir=output_dir)
    recorded = _recorded_total_tokens(observed)
    if recorded >= _token_limit(manifest):
        raise RunnerError("The authorized recorded-token boundary has already been reached")
    return recorded


def collect_provider_canary(
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    output_dir: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    if manifest.get("schema_version") == protocol.SCHEMA_VERSION:
        _require_authorized_output_dir(manifest, output_dir)
    return _original_collect_provider_canary(
        manifest,
        manifest_path=manifest_path,
        output_dir=output_dir,
        repo_root=repo_root,
    )


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
        index = _slot_index(
            manifest,
            case_id=case_id,
            condition_id=condition_id,
            repetition=repetition,
        )
        if index >= _authorized_slot_count(manifest):
            raise RunnerError("The initial authorization stops before this frozen slot")
        _require_authorized_output_dir(manifest, output_dir)
        _ensure_token_budget_remaining(manifest, output_dir=output_dir)
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
            raise RunnerError("Formal v3 ledger is outside the authorized evidence directory") from exc
        _ensure_token_budget_remaining(manifest, output_dir=expected)
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
        raise RunnerError("Batch execution is only valid for the authorized formal v3 collection")
    _require_authorized_output_dir(manifest, output_dir)
    authorized_slots = _authorized_slot_count(manifest)
    if max_attempts < 1 or max_attempts > authorized_slots:
        raise RunnerError(f"Batch execution must request between 1 and {authorized_slots} attempts")
    observed = _observed_authorized_ledgers(manifest, output_dir=output_dir)
    observed_slots = [slot for slot, _events in observed]
    planned_slots = [
        {
            "case_id": slot["case_id"],
            "condition_id": slot["condition_id"],
            "repetition": slot["repetition"],
        }
        for slot in manifest["collection_plan"]
    ]
    if observed_slots != planned_slots[: len(observed_slots)]:
        raise RunnerError("Existing physical evidence does not match the frozen collection prefix")
    if observed and observed[-1][1][-1]["event"] != "experiment.completed":
        raise RunnerError("The previous frozen slot must complete before batch execution resumes")
    start_index = len(observed_slots)
    if start_index >= authorized_slots:
        raise RunnerError("The authorized ten-slot boundary has already been reached")
    if max_attempts > authorized_slots - start_index:
        raise RunnerError("The requested batch would cross the authorized ten-slot boundary")

    results: list[dict[str, Any]] = []
    stop_reason = "authorized_batch_boundary_reached"
    with asyncio.Runner() as async_runner:
        for slot_index in range(start_index, start_index + max_attempts):
            recorded_before = _ensure_token_budget_remaining(
                manifest,
                output_dir=output_dir,
            )
            slot = manifest["collection_plan"][slot_index]
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
            observed_after = _observed_authorized_ledgers(
                manifest,
                output_dir=output_dir,
            )
            recorded_after = _recorded_total_tokens(observed_after)
            results.append(
                {
                    "slot_index": slot_index,
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
        "start_slot_index": start_index,
        "next_slot_index": start_index + len(results),
        "authorized_end_slot_index": authorized_slots,
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
