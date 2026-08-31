#!/usr/bin/env python3
"""Issue #247 independent replication authorized runner。"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_opaque_provenance_confirmatory_execution_authorized_runner as base  # noqa: E402
import forge_opaque_provenance_confirmatory_execution_repair_adapter as repair  # noqa: E402
import forge_opaque_provenance_confirmatory_replication_authorized_protocol as protocol  # noqa: E402

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_OUTPUT_DIR = Path(
    "/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-confirmatory-replication-v1"
)


class ReplicationExecutionError(RuntimeError):
    """Replication release、evidence 或 repair-adapter batch 无效。"""


@contextmanager
def _protocol_binding():
    original = base.protocol
    base.protocol = protocol
    try:
        yield
    finally:
        base.protocol = original


def validate_runtime(
    manifest: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    with _protocol_binding():
        repair_contract = repair.validate_contract(manifest, repo_root=repo_root)
    execution = manifest["authorized_execution"]
    return {
        "status": "valid",
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "evidence_identity_sha256": execution["evidence"]["identity_sha256"],
        "schedule_identity_sha256": manifest["schedule"]["identity_sha256"],
        "pair_executor_adapter": execution["execution"]["pair_executor_adapter"],
        "pair_count": repair_contract["pair_count"],
        "case_count": repair_contract["case_count"],
        "build_systems": repair_contract["build_systems"],
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
    }


def collect_preflight(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    require_empty: bool,
) -> dict[str, Any]:
    validate_runtime(manifest, repo_root)
    with _protocol_binding():
        return base.collect_preflight(
            manifest,
            output_dir=output_dir,
            repo_root=repo_root,
            require_empty=require_empty,
        )


def execute_reachability(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    validate_runtime(manifest, repo_root)
    with _protocol_binding():
        return base.execute_reachability(
            manifest,
            output_dir=output_dir,
            repo_root=repo_root,
        )


def run_batch(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    validate_runtime(manifest, repo_root)
    with _protocol_binding():
        return base.run_batch(
            manifest,
            output_dir=output_dir,
            repo_root=repo_root,
            pair_executor=repair.execute_real_pair,
        )


def load_report(
    manifest: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR
) -> dict[str, Any]:
    report_path = (
        output_dir / manifest["authorized_execution"]["evidence"]["batch_report"]
    )
    report = base._load_json(report_path)
    if report.get("manifest_sha256") != protocol.canonical_sha256(manifest):
        raise ReplicationExecutionError("replication batch report identity 发生漂移")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("validate", "preflight", "reachability", "batch", "report")
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest(args.manifest)
    if args.command == "validate":
        result: Any = validate_runtime(manifest)
    elif args.command == "preflight":
        result = collect_preflight(
            manifest, output_dir=args.output_dir, require_empty=True
        )
    elif args.command == "reachability":
        result = execute_reachability(manifest, output_dir=args.output_dir)
    elif args.command == "batch":
        result = run_batch(manifest, output_dir=args.output_dir)
    else:
        result = load_report(manifest, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
