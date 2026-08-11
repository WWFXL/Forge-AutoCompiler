#!/usr/bin/env python3
"""Unapproved formal-v4 adapter with attempt-budget and resource gates."""

from __future__ import annotations

import importlib.util
import os
import posixpath
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_formal_collection_v4_protocol as protocol  # noqa: E402


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
    root = (
        host_workspace_root
        if host_workspace_root is not None
        else os.environ.get("DEER_FLOW_HOST_WORKSPACE_ROOT")
    )
    if not isinstance(root, str) or not root.strip():
        return False
    normalized_root = posixpath.normpath(root.strip())
    if not PurePosixPath(normalized_root).is_absolute() or normalized_root == "/":
        return False
    expected_source = posixpath.join(normalized_root, ".compile-sessions")
    evidence_mounts = [
        mount
        for mount in mounts or []
        if mount.get("Type") == "bind"
        and mount.get("Destination") == _EVIDENCE_MOUNT_ROOT.as_posix()
        and mount.get("RW") is True
    ]
    if len(evidence_mounts) != 1:
        return False
    source = evidence_mounts[0].get("Source")
    return (
        isinstance(source, str)
        and PurePosixPath(posixpath.normpath(source)).is_absolute()
        and posixpath.normpath(source) == expected_source
    )


def _available_memory_bytes(meminfo_path: Path = Path("/proc/meminfo")) -> int | None:
    try:
        for line in meminfo_path.read_text(encoding="ascii").splitlines():
            if not line.startswith("MemAvailable:"):
                continue
            fields = line.split()
            if len(fields) != 3 or fields[2] != "kB":
                return None
            return int(fields[1]) * 1024
    except (OSError, UnicodeError, ValueError):
        return None
    return None


def _docker_daemon_probe(timeout_seconds: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{json .ServerVersion}}"],
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {
            "responded": False,
            "latency_seconds": round(time.monotonic() - started, 6),
        }
    return {
        "responded": result.returncode == 0 and bool(result.stdout.strip()),
        "latency_seconds": round(time.monotonic() - started, 6),
    }


def collect_runtime_launch_preflight(
    output_dir: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    result = _original_collect_runtime_launch_preflight(output_dir, repo_root=repo_root)
    _labels, mounts = _runner._current_container_metadata(repo_root)
    source_matches = _evidence_mount_source_matches_host_workspace(mounts)
    available_memory = _available_memory_bytes()
    resource_policy = protocol.RESOURCE_PREFLIGHT
    daemon = _docker_daemon_probe(resource_policy["docker_daemon_timeout_seconds"])
    memory_ready = (
        available_memory is not None
        and available_memory >= resource_policy["minimum_available_memory_bytes"]
    )
    daemon_responded = daemon["responded"] is True
    daemon_latency_ready = (
        daemon_responded
        and daemon["latency_seconds"]
        <= resource_policy["maximum_docker_daemon_latency_seconds"]
    )
    checks = {
        **result["checks"],
        "evidence_mount_source_matches_host_workspace": source_matches,
        "host_available_memory_at_least_minimum": memory_ready,
        "docker_daemon_responded": daemon_responded,
        "docker_daemon_latency_within_limit": daemon_latency_ready,
    }
    observations = {
        **result.get("observations", {}),
        "available_memory_bytes": available_memory,
        "minimum_available_memory_bytes": resource_policy[
            "minimum_available_memory_bytes"
        ],
        "docker_daemon_latency_seconds": daemon["latency_seconds"],
        "maximum_docker_daemon_latency_seconds": resource_policy[
            "maximum_docker_daemon_latency_seconds"
        ],
    }
    return {
        **result,
        "ready": all(checks.values()),
        "checks": checks,
        "observations": observations,
    }


def attempt_budget_state(
    manifest: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    elapsed_seconds: float,
) -> dict[str, Any]:
    protocol.validate_manifest(manifest)
    if elapsed_seconds < 0:
        raise RunnerError("Attempt elapsed time cannot be negative")
    budget = manifest["attempt_budget"]
    compiler_invocations = sum(
        event.get("event") == "agent.subagent_terminated"
        and event.get("payload", {}).get("role") == "compiler"
        for event in events
    )
    model_requests = sum(
        event.get("event") == "model.request_started" for event in events
    )
    work_deadline = (
        budget["total_wall_clock_seconds"] - budget["cleanup_reserve_seconds"]
    )
    return {
        "elapsed_seconds": round(elapsed_seconds, 6),
        "work_deadline_seconds": work_deadline,
        "total_wall_clock_seconds": budget["total_wall_clock_seconds"],
        "compiler_invocations": compiler_invocations,
        "model_requests": model_requests,
        "allow_new_work": elapsed_seconds < work_deadline,
        "allow_new_compiler_invocation": (
            elapsed_seconds < work_deadline
            and compiler_invocations < budget["max_compiler_invocations"]
        ),
        "allow_new_model_request": (
            elapsed_seconds < work_deadline
            and model_requests < budget["max_model_requests"]
        ),
        "within_total_wall_clock": elapsed_seconds
        <= budget["total_wall_clock_seconds"],
        "cleanup_required": (
            elapsed_seconds >= work_deadline
            or compiler_invocations >= budget["max_compiler_invocations"]
            or model_requests >= budget["max_model_requests"]
        ),
    }


def require_attempt_budget_checkpoint(
    manifest: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    elapsed_seconds: float,
    checkpoint: str,
) -> dict[str, Any]:
    budget = manifest["attempt_budget"]
    if checkpoint not in budget["enforcement_checkpoints"]:
        raise RunnerError(f"Unknown attempt-budget checkpoint: {checkpoint}")
    state = attempt_budget_state(manifest, events, elapsed_seconds=elapsed_seconds)
    if checkpoint == "before_provider_request" and not state["allow_new_model_request"]:
        raise RunnerError("The physical-attempt model-request budget is exhausted")
    if (
        checkpoint == "before_compiler_invocation"
        and not state["allow_new_compiler_invocation"]
    ):
        raise RunnerError(
            "The physical-attempt Compiler invocation budget is exhausted"
        )
    if checkpoint == "before_submit_or_replay" and not state["allow_new_work"]:
        raise RunnerError("The physical-attempt work deadline is exhausted")
    return state


def _reject_unapproved_action(action: str) -> None:
    raise RunnerError(f"Formal collection v4 is not authorized; {action} is forbidden")


def collect_provider_canary(*args: Any, **kwargs: Any):
    _reject_unapproved_action("provider canary")


def create_attempt(*args: Any, **kwargs: Any):
    _reject_unapproved_action("physical-attempt ledger creation")


def run_attempt(*args: Any, **kwargs: Any):
    _reject_unapproved_action("model execution")


def run_formal_batch(*args: Any, **kwargs: Any):
    _reject_unapproved_action("batch execution")


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
