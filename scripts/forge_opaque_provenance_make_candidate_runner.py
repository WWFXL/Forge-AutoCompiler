#!/usr/bin/env python3
"""Issue #206 R2 Make 候选的零 provider、零 Docker runner。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent


class RuntimeGateError(RuntimeError):
    """候选快照或未授权执行入口被拒绝。"""


def _load_protocol(repo_root: Path = REPO_ROOT):
    path = repo_root / "scripts/forge_opaque_provenance_make_candidate_protocol.py"
    name = "forge_opaque_provenance_make_candidate_runtime_protocol"
    existing = sys.modules.get(name)
    if existing is not None and Path(existing.__file__).resolve() == path.resolve():
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeGateError("cannot load R2 Make candidate protocol")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_protocol()
CommandRunner = Callable[[Sequence[str], Path], str]


def _run_command(command: Sequence[str], cwd: Path) -> str:
    if not command or command[0] != "git":
        raise RuntimeGateError("candidate preflight only permits read-only git commands")
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeGateError("candidate preflight git command failed") from exc
    return result.stdout.strip()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_plan(manifest: dict[str, Any]) -> dict[str, Any]:
    protocol.validate_manifest(manifest)
    return {
        "schema_version": manifest["schema_version"],
        "case_id": manifest["case"]["case_id"],
        "build_system": manifest["case"]["build_system"],
        "target": manifest["case"]["target"],
        "pair_id": manifest["schedule"][0]["pair_id"],
        "arm_order": manifest["schedule"][0]["arm_order"],
        "provider": manifest["provider"]["model"],
        "phase_recorded_token_ceiling": manifest["budget"]["phase_recorded_token_ceiling"],
        "checkpoint_status": manifest["checkpoint"]["status"],
        "evidence_identity_sha256": manifest["evidence"]["identity_sha256"],
        "r0_companion_event": manifest["r0_observability"]["companion_event"],
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
        "credential_read": False,
        "docker_executed": False,
        "evidence_writes": 0,
        "execution_authorized": False,
    }


def validate_preflight_snapshot(manifest: dict[str, Any], snapshot: Any) -> dict[str, Any]:
    protocol.validate_manifest(manifest)
    if not isinstance(snapshot, dict):
        raise RuntimeGateError("preflight snapshot must be an object")
    expected_keys = {
        "schema_version",
        "branch",
        "head_commit",
        "origin_main_commit",
        "worktree_clean",
        "authorization_baseline_ancestor",
        "frozen_component_sha256",
        "candidate_evidence_directory",
        "candidate_evidence_entries",
        "checkpoint_status",
        "docker_executed",
    }
    if set(snapshot) != expected_keys:
        raise RuntimeGateError("preflight snapshot fields drifted")
    if snapshot["schema_version"] != "forge-opaque-provenance-r2-make-candidate-preflight-1.0.0":
        raise RuntimeGateError("preflight schema identity drifted")
    if snapshot["branch"] != manifest["preflight"]["release_branch"]:
        raise RuntimeGateError("preflight release branch drifted")
    if not snapshot["head_commit"] or snapshot["head_commit"] != snapshot["origin_main_commit"]:
        raise RuntimeGateError("preflight main/origin identity drifted")
    if snapshot["worktree_clean"] is not True or snapshot["authorization_baseline_ancestor"] is not True:
        raise RuntimeGateError("preflight release identity is not clean or descendant-compatible")
    if snapshot["frozen_component_sha256"] != manifest["frozen_components"]:
        raise RuntimeGateError("preflight frozen component identity drifted")
    if snapshot["candidate_evidence_directory"] != manifest["evidence"]["directory"] or snapshot["candidate_evidence_entries"] != 0:
        raise RuntimeGateError("candidate evidence directory is not the frozen empty directory")
    if snapshot["checkpoint_status"] != "not_created":
        raise RuntimeGateError("R2 Make checkpoint already exists")
    if snapshot["docker_executed"] is not False:
        raise RuntimeGateError("candidate preflight must not execute Docker")
    return snapshot


def collect_preflight_snapshot(
    manifest: dict[str, Any],
    *,
    repo_root: Path,
    host_candidate_evidence_directory: Path,
    command_runner: CommandRunner = _run_command,
) -> dict[str, Any]:
    protocol.validate_manifest(manifest, repo_root)
    candidate_name = PurePosixPath(manifest["evidence"]["directory"]).name
    expected_candidate = repo_root / ".compile-sessions" / candidate_name
    if host_candidate_evidence_directory.resolve(strict=False) != expected_candidate.resolve(strict=False):
        raise RuntimeGateError("candidate evidence directory is not bound to the frozen identity")
    branch = command_runner(("git", "branch", "--show-current"), repo_root)
    head = command_runner(("git", "rev-parse", "HEAD"), repo_root)
    origin_main = command_runner(("git", "rev-parse", "origin/main"), repo_root)
    status = command_runner(("git", "status", "--porcelain"), repo_root)
    ancestry = command_runner(
        (
            "git",
            "merge-base",
            "--is-ancestor",
            manifest["preflight"]["authorization_baseline_commit"],
            "HEAD",
        ),
        repo_root,
    )
    if ancestry:
        raise RuntimeGateError("git ancestry check produced unexpected output")
    candidate_entries = len(tuple(host_candidate_evidence_directory.iterdir())) if host_candidate_evidence_directory.exists() else 0
    snapshot = {
        "schema_version": "forge-opaque-provenance-r2-make-candidate-preflight-1.0.0",
        "branch": branch,
        "head_commit": head,
        "origin_main_commit": origin_main,
        "worktree_clean": status == "",
        "authorization_baseline_ancestor": True,
        "frozen_component_sha256": {path: _file_sha256(repo_root / path) for path in sorted(manifest["frozen_components"])},
        "candidate_evidence_directory": manifest["evidence"]["directory"],
        "candidate_evidence_entries": candidate_entries,
        "checkpoint_status": manifest["checkpoint"]["status"],
        "docker_executed": False,
    }
    return validate_preflight_snapshot(manifest, snapshot)


def execute_checkpoint(_manifest: dict[str, Any]) -> None:
    raise RuntimeGateError("checkpoint creation is not authorized by Issue #206")


def execute_reachability(_manifest: dict[str, Any]) -> None:
    raise RuntimeGateError("reachability request is not authorized by Issue #206")


def execute_pair(_manifest: dict[str, Any]) -> None:
    raise RuntimeGateError("provider pair is not authorized by Issue #206")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "plan", "preflight"))
    parser.add_argument("--manifest", type=Path, default=protocol.DEFAULT_MANIFEST)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--host-candidate-evidence-directory", type=Path)
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest(args.manifest, args.repo_root)
    if args.command == "preflight":
        if args.host_candidate_evidence_directory is None:
            raise RuntimeGateError("preflight requires the candidate evidence directory")
        result = collect_preflight_snapshot(
            manifest,
            repo_root=args.repo_root,
            host_candidate_evidence_directory=args.host_candidate_evidence_directory,
        )
    elif args.command == "plan":
        result = build_plan(manifest)
    else:
        result = {
            "manifest_sha256": protocol.canonical_sha256(manifest),
            "checkpoint_status": manifest["checkpoint"]["status"],
            "provider_calls": 0,
            "formal_attempts": 0,
            "model_tokens": 0,
            "credential_read": False,
            "docker_executed": False,
            "evidence_writes": 0,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
