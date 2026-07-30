#!/usr/bin/env python3
"""Unapproved formal-v3 adapter with a strict DooD evidence-path gate."""

from __future__ import annotations

import os
import posixpath
import sys
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_formal_collection_v2_runner as _runner  # noqa: E402
import forge_formal_collection_v3_protocol as protocol  # noqa: E402

_original_manifest_protocol = _runner._manifest_protocol
_original_build_policy = _runner.build_policy
_original_collect_runtime_launch_preflight = _runner.collect_runtime_launch_preflight

RunnerError = _runner.RunnerError
REPO_ROOT = _runner.REPO_ROOT
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


def _reject_unapproved_action(action: str) -> None:
    raise RunnerError(f"Formal collection v3 is not authorized; {action} is forbidden")


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


def main(argv: list[str] | None = None) -> int:
    return _runner.main(argv)


def __getattr__(name: str):
    return getattr(_runner, name)


if __name__ == "__main__":
    raise SystemExit(main())
