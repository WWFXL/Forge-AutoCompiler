#!/usr/bin/env python3
"""验证 mechanism v2 release-bound identity；真实执行等待单独授权。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_contract_driven_repair_mechanism_v2_authorized_protocol as protocol  # noqa: E402
import forge_contract_driven_repair_mechanism_v2_candidate_runner as candidate_runner  # noqa: E402

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
READ_ONLY_COMMANDS = ("validate", "plan", "preflight")
BLOCKED_COMMANDS = ("availability", "batch", "report", "audit")


class AuthorizedRunnerError(RuntimeError):
    """release-bound identity、evidence 或权限边界无效。"""


def _run_checked(argv: list[str], *, cwd: Path) -> str:
    result = subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-3000:]
        raise AuthorizedRunnerError(
            f"非模型 preflight 命令失败: {' '.join(argv)}: {detail}"
        )
    return result.stdout.strip()


def validate_runtime(
    manifest: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    runtime = manifest["independent_runtime"]
    if runtime["commands_allowed_without_execution_authorization"] != list(
        READ_ONLY_COMMANDS
    ) or runtime["commands_fail_closed_without_separate_authorization"] != list(
        BLOCKED_COMMANDS
    ):
        raise AuthorizedRunnerError("release-bound runner 命令边界漂移")
    return {
        "status": "release_bound_identity_not_execution_authorized",
        "manifest_sha256": protocol.candidate.candidate.canonical_sha256(manifest),
        "scientific_contract_release_revision": (
            protocol.SCIENTIFIC_CONTRACT_RELEASE_REVISION
        ),
        "availability_execution_authorized": False,
        "formal_collection_execution_authorized": False,
        "provider_calls": 0,
        "credential_reads": 0,
        "docker_sessions_created": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
        "model_tokens": 0,
    }


def _require_release(repo_root: Path) -> dict[str, str]:
    revision = _run_checked(["git", "rev-parse", "HEAD"], cwd=repo_root)
    branch = _run_checked(["git", "branch", "--show-current"], cwd=repo_root)
    origin_main = _run_checked(
        ["git", "rev-parse", "refs/remotes/origin/main"], cwd=repo_root
    )
    _run_checked(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            protocol.SCIENTIFIC_CONTRACT_RELEASE_REVISION,
            revision,
        ],
        cwd=repo_root,
    )
    dirty = _run_checked(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo_root
    )
    if branch != "main" or revision != origin_main or dirty:
        raise AuthorizedRunnerError(
            "release-bound preflight 要求 clean main == origin/main"
        )
    return {"revision": revision, "branch": branch, "origin_main": origin_main}


def collect_preflight(
    manifest: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    validate_runtime(manifest, repo_root)
    release = _require_release(repo_root)
    image_id = candidate_runner._require_docker_identity(manifest, repo_root)
    candidate_runner.base._require_zero_managed_resources()
    old_evidence = candidate_runner._require_old_evidence_read_only(repo_root)
    new_evidence = candidate_runner._require_new_evidence_absent(
        manifest, workspace_root or repo_root
    )
    return {
        "ready": True,
        "status": "release_bound_preflight_passed_execution_not_authorized",
        "manifest_sha256": protocol.candidate.candidate.canonical_sha256(manifest),
        "scientific_contract_release_revision": (
            protocol.SCIENTIFIC_CONTRACT_RELEASE_REVISION
        ),
        "observed_clean_release_revision": release["revision"],
        "branch": release["branch"],
        "origin_main": release["origin_main"],
        "compile_image_id": image_id,
        "old_evidence": old_evidence,
        "new_evidence_directory": str(new_evidence),
        "new_evidence_directory_absent": True,
        "zero_managed_resources": True,
        "credential_check": "not_authorized_not_performed",
        "provider_calls": 0,
        "credential_reads": 0,
        "docker_sessions_created": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
        "model_tokens": 0,
    }


def _reject_execution(command: str) -> None:
    raise AuthorizedRunnerError(
        f"{command} 需要新的 execution authorization；release-bound identity 保持 fail-closed"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=READ_ONLY_COMMANDS + BLOCKED_COMMANDS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest(args.manifest)
    if args.command in BLOCKED_COMMANDS:
        _reject_execution(args.command)
    if args.command == "plan":
        result = protocol.plan_summary(manifest)
    elif args.command == "preflight":
        result = collect_preflight(manifest)
    else:
        result = validate_runtime(manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
