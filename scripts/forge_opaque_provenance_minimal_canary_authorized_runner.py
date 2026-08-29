#!/usr/bin/env python3
"""Issue #182 授权候选的零 provider runtime adapter。"""

from __future__ import annotations

import argparse
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
    """Runtime preflight 或未授权执行入口被拒绝。"""


def _load_protocol(repo_root: Path = REPO_ROOT):
    path = repo_root / "scripts/forge_opaque_provenance_minimal_canary_authorized_protocol.py"
    name = "forge_opaque_provenance_minimal_canary_authorized_runtime_protocol"
    existing = sys.modules.get(name)
    if existing is not None and Path(existing.__file__).resolve() == path.resolve():
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeGateError("cannot load authorized candidate protocol")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_protocol()
CommandRunner = Callable[[Sequence[str], Path], str]


def _run_command(command: Sequence[str], cwd: Path) -> str:
    try:
        result = subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeGateError(f"preflight command failed: {command[0]}") from exc
    return result.stdout.strip()


def build_plan(manifest: dict[str, Any]) -> dict[str, Any]:
    protocol.validate_manifest(manifest)
    return {
        "schema_version": manifest["schema_version"],
        "parent_manifest_sha256": manifest["parent"]["canonical_sha256"],
        "case_id": manifest["case"]["case_id"],
        "pair_id": manifest["schedule"][0]["pair_id"],
        "arm_order": manifest["schedule"][0]["arm_order"],
        "evidence_identity_sha256": manifest["evidence"]["identity_sha256"],
        "evidence_directory": manifest["evidence"]["directory"],
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
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
        "docker_provider",
        "docker_context",
        "docker_endpoint",
        "network_medium",
        "evidence_directory",
        "evidence_entries",
        "managed_orphans",
    }
    if set(snapshot) != expected_keys:
        raise RuntimeGateError("preflight snapshot fields drifted")
    if snapshot["schema_version"] != "forge-opaque-provenance-minimal-canary-preflight-1.0.0":
        raise RuntimeGateError("preflight schema identity drifted")
    if snapshot["branch"] != manifest["preflight"]["release_branch"]:
        raise RuntimeGateError("preflight release branch drifted")
    if not snapshot["head_commit"] or snapshot["head_commit"] != snapshot["origin_main_commit"]:
        raise RuntimeGateError("preflight main/origin identity drifted")
    if snapshot["worktree_clean"] is not True or snapshot["authorization_baseline_ancestor"] is not True:
        raise RuntimeGateError("preflight release identity is not clean or descendant-compatible")
    for key in ("docker_provider", "docker_context", "docker_endpoint"):
        if snapshot[key] != manifest["preflight"][key]:
            raise RuntimeGateError(f"preflight {key} drifted")
    if snapshot["network_medium"] not in manifest["preflight"]["allowed_network_media"]:
        raise RuntimeGateError("preflight network medium is missing or invalid")
    if snapshot["evidence_directory"] != manifest["evidence"]["directory"] or snapshot["evidence_entries"] != 0:
        raise RuntimeGateError("preflight evidence directory is not the frozen empty directory")
    if snapshot["managed_orphans"] != []:
        raise RuntimeGateError("preflight found managed Compile Session/replay orphans")
    return snapshot


def collect_preflight_snapshot(
    manifest: dict[str, Any],
    *,
    repo_root: Path,
    host_evidence_directory: Path,
    network_medium: str,
    command_runner: CommandRunner = _run_command,
) -> dict[str, Any]:
    protocol.validate_manifest(manifest, repo_root)
    expected_name = PurePosixPath(manifest["evidence"]["directory"]).name
    expected_host_directory = repo_root / ".compile-sessions" / expected_name
    if host_evidence_directory.resolve(strict=False) != expected_host_directory.resolve(strict=False):
        raise RuntimeGateError("host evidence directory is not bound to the frozen identity")
    if network_medium not in manifest["preflight"]["allowed_network_media"]:
        raise RuntimeGateError("network medium is missing or invalid")

    branch = command_runner(("git", "branch", "--show-current"), repo_root)
    head = command_runner(("git", "rev-parse", "HEAD"), repo_root)
    origin_main = command_runner(("git", "rev-parse", "origin/main"), repo_root)
    status = command_runner(("git", "status", "--porcelain"), repo_root)
    baseline_check = command_runner(
        ("git", "merge-base", "--is-ancestor", manifest["parent"]["authorization_baseline_commit"], "HEAD"),
        repo_root,
    )
    if baseline_check:
        raise RuntimeGateError("git ancestry check produced unexpected output")

    gate_output = command_runner(("bash", str(repo_root / "scripts/require-ubuntu-native-docker.sh")), repo_root)
    expected_gate = "OK: Forge Docker daemon provider=ubuntu-native; context=default; endpoint=/var/run/docker.sock"
    if gate_output != expected_gate:
        raise RuntimeGateError("Ubuntu-native Docker gate output drifted")
    names = command_runner(("docker", "ps", "-a", "--format", "{{.Names}}"), repo_root).splitlines()
    prefixes = tuple(manifest["preflight"]["managed_container_prefixes"])
    orphans = sorted(name for name in names if name.startswith(prefixes))
    entries = len(tuple(host_evidence_directory.iterdir())) if host_evidence_directory.exists() else 0

    snapshot = {
        "schema_version": "forge-opaque-provenance-minimal-canary-preflight-1.0.0",
        "branch": branch,
        "head_commit": head,
        "origin_main_commit": origin_main,
        "worktree_clean": status == "",
        "authorization_baseline_ancestor": True,
        "docker_provider": "ubuntu-native",
        "docker_context": "default",
        "docker_endpoint": "/var/run/docker.sock",
        "network_medium": network_medium,
        "evidence_directory": manifest["evidence"]["directory"],
        "evidence_entries": entries,
        "managed_orphans": orphans,
    }
    return validate_preflight_snapshot(manifest, snapshot)


def execute_reachability(_manifest: dict[str, Any]) -> None:
    raise RuntimeGateError("reachability request is not authorized by Issue #182")


def execute_canary(_manifest: dict[str, Any]) -> None:
    raise RuntimeGateError("provider canary is not authorized by Issue #182")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "plan", "preflight"))
    parser.add_argument("--manifest", type=Path, default=protocol.DEFAULT_MANIFEST)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--host-evidence-directory", type=Path)
    parser.add_argument("--network-medium", choices=("wired", "wifi", "mobile_hotspot"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest = protocol.load_manifest(args.manifest, args.repo_root)
    if args.command == "preflight":
        if args.host_evidence_directory is None or args.network_medium is None:
            raise RuntimeGateError("preflight requires host evidence directory and network medium")
        result = collect_preflight_snapshot(
            manifest,
            repo_root=args.repo_root,
            host_evidence_directory=args.host_evidence_directory,
            network_medium=args.network_medium,
        )
    else:
        result = (
            build_plan(manifest)
            if args.command == "plan"
            else {
                "manifest_sha256": protocol.canonical_sha256(manifest),
                "provider_calls": 0,
                "formal_attempts": 0,
                "model_tokens": 0,
                "evidence_writes": 0,
            }
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
