#!/usr/bin/env python3
"""为未授权 formal v4 候选接入 Ubuntu 原生 daemon 门禁。"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_formal_collection_v4_ubuntu_protocol as protocol  # noqa: E402

# 协议模块先建立仓库导入根，再加载父 runner。
# isort: split
import forge_formal_collection_v4_runtime_runner as parent_runner  # noqa: E402

_runner = parent_runner._runner
_original_manifest_protocol = _runner._manifest_protocol
_original_collect_runtime_launch_preflight = parent_runner.collect_runtime_launch_preflight

_runner.protocol_formal_collection = protocol

RunnerError = _runner.RunnerError
REPO_ROOT = _runner.REPO_ROOT
DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST


def _manifest_protocol(manifest: dict[str, Any]):
    if manifest.get("schema_version") == protocol.SCHEMA_VERSION:
        return protocol
    return _original_manifest_protocol(manifest)


def _docker_socket_source_matches_native_path(
    mounts: list[dict[str, Any]] | None,
) -> bool:
    socket_mounts = [mount for mount in mounts or [] if mount.get("Type") == "bind" and mount.get("Source") == protocol.DOCKER_SOCKET_PATH and mount.get("Destination") == protocol.DOCKER_SOCKET_PATH and mount.get("RW") is True]
    return len(socket_mounts) == 1


def _docker_daemon_provider_probe(timeout_seconds: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{json .OperatingSystem}}"],
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {
            "provider": None,
            "responded": False,
            "latency_seconds": round(time.monotonic() - started, 6),
        }

    provider = None
    if result.returncode == 0:
        try:
            operating_system = json.loads(result.stdout)
        except json.JSONDecodeError:
            operating_system = None
        if isinstance(operating_system, str):
            provider = protocol.DOCKER_DAEMON_PROVIDER if operating_system.startswith("Ubuntu") else "other"
    return {
        "provider": provider,
        "responded": provider is not None,
        "latency_seconds": round(time.monotonic() - started, 6),
    }


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
    provider = _docker_daemon_provider_probe(protocol.RESOURCE_PREFLIGHT["docker_daemon_timeout_seconds"])
    checks = {
        **result["checks"],
        "docker_daemon_provider_matches": (provider["provider"] == protocol.DOCKER_DAEMON_PROVIDER),
        "docker_socket_source_matches_native_path": (_docker_socket_source_matches_native_path(mounts)),
    }
    return {
        **result,
        "ready": all(checks.values()),
        "checks": checks,
        "observations": {
            **result.get("observations", {}),
            "docker_daemon_provider": provider["provider"],
        },
    }


def _reject_unapproved_action(action: str) -> None:
    raise RunnerError(f"Formal v4 Ubuntu candidate is not authorized; {action} is forbidden")


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
