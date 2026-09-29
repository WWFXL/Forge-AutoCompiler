#!/usr/bin/env python3
"""检查 availability candidate；Provider 往返等待独立执行授权。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_contract_driven_repair_mechanism_v1_authorized_runner as parent_runner  # noqa: E402
import forge_contract_driven_repair_mechanism_v1_availability_candidate_protocol as protocol  # noqa: E402

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
READ_ONLY_COMMANDS = ("validate", "plan", "preflight")
BLOCKED_COMMANDS = ("availability", "batch")


class AvailabilityCandidateRunnerError(RuntimeError):
    """implementation release、preflight 或执行授权边界无效。"""


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
        raise AvailabilityCandidateRunnerError(
            f"非模型 preflight 命令失败: {' '.join(argv)}: {detail}"
        )
    return result.stdout.strip()


def validate_runtime(
    manifest: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    runtime = manifest["availability_candidate_runtime"]
    if runtime["commands_allowed_without_execution_authorization"] != list(
        READ_ONLY_COMMANDS
    ) or runtime["commands_fail_closed_without_separate_authorization"] != list(
        BLOCKED_COMMANDS
    ):
        raise AvailabilityCandidateRunnerError(
            "availability candidate 命令边界发生漂移"
        )
    return {
        "status": "availability_qualification_candidate_not_execution_authorized",
        "manifest_sha256": protocol.parent.candidate.canonical_sha256(manifest),
        "authorized_implementation_revision": protocol.IMPLEMENTATION_RELEASE_REVISION,
        "availability_execution_authorized": False,
        "formal_collection_execution_authorized": False,
        "provider_calls": 0,
        "credential_reads": 0,
        "docker_sessions_created": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
        "model_tokens": 0,
    }


def _require_release(repo_root: Path) -> str:
    revision = _run_checked(["git", "rev-parse", "HEAD"], cwd=repo_root)
    _run_checked(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            protocol.IMPLEMENTATION_RELEASE_REVISION,
            revision,
        ],
        cwd=repo_root,
    )
    dirty = _run_checked(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo_root
    )
    if dirty:
        raise AvailabilityCandidateRunnerError("非模型 preflight 要求干净工作树")
    return revision


def collect_preflight(
    manifest: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    validate_runtime(manifest, repo_root)
    revision = _require_release(repo_root)
    try:
        image_id = parent_runner._require_docker_identity(manifest, repo_root)
        parent_runner._require_zero_managed_resources(repo_root)
        evidence = parent_runner._require_evidence_absent(
            manifest, workspace_root or repo_root
        )
    except parent_runner.AuthorizedRunnerError as exc:
        raise AvailabilityCandidateRunnerError(str(exc)) from exc
    return {
        "ready": True,
        "status": "availability_candidate_preflight_passed_execution_not_authorized",
        "manifest_sha256": protocol.parent.candidate.canonical_sha256(manifest),
        "authorized_implementation_revision": protocol.IMPLEMENTATION_RELEASE_REVISION,
        "observed_clean_descendant_revision": revision,
        "compile_image_id": image_id,
        "evidence_directory": str(evidence),
        "zero_managed_resources": True,
        "evidence_directory_absent": True,
        "availability_execution_authorized": False,
        "formal_collection_execution_authorized": False,
        "provider_calls": 0,
        "credential_reads": 0,
        "docker_sessions_created": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
        "model_tokens": 0,
    }


def _reject_execution(command: str) -> None:
    if command not in BLOCKED_COMMANDS:
        raise AvailabilityCandidateRunnerError(f"未知执行命令: {command}")
    raise AvailabilityCandidateRunnerError(
        f"{command} 尚未获得独立执行授权；禁止读取 credential、调用 Provider 或创建 evidence"
    )


def execute_availability() -> None:
    _reject_execution("availability")


def run_batch() -> None:
    _reject_execution("batch")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=READ_ONLY_COMMANDS + BLOCKED_COMMANDS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    if args.command in BLOCKED_COMMANDS:
        _reject_execution(args.command)
    manifest = protocol.load_manifest(args.manifest)
    if args.command == "validate":
        result: Any = validate_runtime(manifest)
    elif args.command == "plan":
        result = protocol.plan_summary(manifest)
    else:
        result = collect_preflight(manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
