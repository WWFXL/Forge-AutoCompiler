#!/usr/bin/env python3
"""Audit frozen benchmark revisions across reviewed squash merges."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import forge_benchmark_v2 as protocol_v2

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class HistoryAuditError(ValueError):
    """Raised when frozen history cannot be tied to an audited successor."""


@dataclass(frozen=True)
class AuditedSquashLineage:
    baseline_commit: str
    baseline_tree_sha: str
    source_head: str
    successor_commit: str
    successor_tree_sha: str


V2_LINEAGE = AuditedSquashLineage(
    baseline_commit="d845b735576be706f79fcf0666f66c14929a52cc",
    baseline_tree_sha="67c604af71df09376f17a881828a465cdebe879a",
    source_head="561b38cee9f027b0dfb01ff765b44a28dbf2de8f",
    successor_commit="9e002f4568a77de07fdce65b49373afb7e5cc74e",
    successor_tree_sha="29aa07d5bb4bb5e9482b1f0e5146237757adf695",
)


def _git(repo_root: Path, arguments: list[str]) -> bytes:
    git = shutil.which("git")
    if git is None:
        raise HistoryAuditError("git is required to audit frozen benchmark history")
    result = subprocess.run(
        [git, *arguments],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise HistoryAuditError(f"git {' '.join(arguments)} failed")
    return result.stdout


def _git_text(repo_root: Path, arguments: list[str]) -> str:
    return _git(repo_root, arguments).decode("ascii").strip()


def _is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    git = shutil.which("git")
    if git is None:
        raise HistoryAuditError("git is required to audit frozen benchmark history")
    result = subprocess.run(
        [git, "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if result.returncode not in {0, 1}:
        raise HistoryAuditError("git merge-base failed while auditing benchmark history")
    return result.returncode == 0


def _safe_repository_file(repo_root: Path, relative_path: str) -> Path:
    resolved_root = repo_root.resolve(strict=True)
    candidate = resolved_root
    for part in PurePosixPath(relative_path).parts:
        candidate /= part
        if candidate.is_symlink():
            raise HistoryAuditError(f"{relative_path} must not be a symlink")
    if not candidate.is_file():
        raise HistoryAuditError(f"{relative_path} is not an ordinary file")
    resolved_candidate = candidate.resolve(strict=True)
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise HistoryAuditError(f"{relative_path} escapes the repository") from exc
    return resolved_candidate


def audit_v2_history(
    manifest: dict[str, Any],
    repo_root: Path = REPOSITORY_ROOT,
    *,
    head_revision: str = "HEAD",
) -> dict[str, Any]:
    """Verify v2 blobs and prove that HEAD follows an audited history lineage."""
    protocol_v2.validate_manifest(manifest)
    baseline = manifest["forge"]["commit_sha"]
    if baseline != V2_LINEAGE.baseline_commit:
        raise HistoryAuditError("the v2 baseline is not covered by the audited lineage")

    baseline_tree = _git_text(repo_root, ["rev-parse", f"{baseline}^{{tree}}"])
    if baseline_tree != V2_LINEAGE.baseline_tree_sha:
        raise HistoryAuditError("the v2 baseline has an unexpected tree")
    for revision in (V2_LINEAGE.source_head, V2_LINEAGE.successor_commit):
        tree = _git_text(repo_root, ["rev-parse", f"{revision}^{{tree}}"])
        if tree != V2_LINEAGE.successor_tree_sha:
            raise HistoryAuditError(f"audited revision {revision} has an unexpected tree")

    resolved_head = _git_text(repo_root, ["rev-parse", head_revision])
    if resolved_head == baseline or _is_ancestor(repo_root, baseline, resolved_head):
        lineage_mode = "native_baseline_ancestor"
    elif _is_ancestor(repo_root, V2_LINEAGE.successor_commit, resolved_head):
        lineage_mode = "audited_squash_successor"
    else:
        raise HistoryAuditError("HEAD does not descend from the baseline or its audited successor")

    for relative_path, expected_digest in manifest["forge"]["component_sha256"].items():
        blob = _git(repo_root, ["show", f"{baseline}:{relative_path}"])
        if hashlib.sha256(blob).hexdigest() != expected_digest:
            raise HistoryAuditError(f"frozen baseline blob mismatch: {relative_path}")

    for relative_path, expected_digest in manifest["protocol_artifact_sha256"].items():
        artifact = _safe_repository_file(repo_root, relative_path)
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != expected_digest:
            raise HistoryAuditError(f"frozen protocol artifact mismatch: {relative_path}")

    return {
        "baseline_commit": baseline,
        "head_revision": resolved_head,
        "lineage_mode": lineage_mode,
        "source_head": V2_LINEAGE.source_head,
        "successor_commit": V2_LINEAGE.successor_commit,
        "baseline_tree_sha": V2_LINEAGE.baseline_tree_sha,
        "successor_tree_sha": V2_LINEAGE.successor_tree_sha,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest",
        nargs="?",
        type=Path,
        default=REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v2.json",
    )
    parser.add_argument("--head", default="HEAD", help="revision to audit as the current head")
    args = parser.parse_args(argv)
    try:
        manifest = protocol_v2.load_json_document(args.manifest)
        result = audit_v2_history(manifest, head_revision=args.head)
    except (HistoryAuditError, protocol_v2.BenchmarkError, OSError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": "valid", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
