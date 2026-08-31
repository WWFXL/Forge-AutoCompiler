#!/usr/bin/env python3
"""Issue #239 confirmatory v1 机制故障的版本化 pair runtime 修复。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_opaque_provenance_confirmatory_execution_authorized_runner as v1  # noqa: E402
import forge_opaque_provenance_confirmatory_lifecycle_gate as lifecycle  # noqa: E402

DEFAULT_MANIFEST = v1.DEFAULT_MANIFEST


class ConfirmatoryRepairError(RuntimeError):
    """修复后的 pair runtime identity 或静态合同无效。"""


def _pair_manifest(
    manifest: dict[str, Any],
    pair: dict[str, Any],
    pair_dir: Path,
) -> dict[str, Any]:
    runtime_manifest = v1._pair_manifest(manifest, pair, pair_dir)
    case = v1._case(manifest, pair["case_id"])
    reference_case_id = case.get("source_case_id")
    if not isinstance(reference_case_id, str) or not reference_case_id:
        raise ConfirmatoryRepairError(f"{pair['case_id']} 缺少冻结 source case identity")
    runtime_manifest["case"]["reference_case_id"] = reference_case_id
    return runtime_manifest


def validate_contract(
    manifest: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    v1.protocol.verify_frozen_components(manifest, repo_root)
    pairs = manifest["schedule"]["pairs"]
    build_systems: set[str] = set()
    reference_case_ids: dict[str, str] = {}
    for pair in pairs:
        case = v1._case(manifest, pair["case_id"])
        adapter = lifecycle.build_case_adapter(pair["case_id"], repo_root)
        pair_manifest = _pair_manifest(manifest, pair, Path("/tmp") / pair["pair_id"])
        expected = case["source_case_id"]
        if pair_manifest["case"].get("reference_case_id") != expected:
            raise ConfirmatoryRepairError(f"{pair['pair_id']} reference identity 漂移")
        if pair_manifest["case"]["build_system"] != adapter.build_system:
            raise ConfirmatoryRepairError(f"{pair['pair_id']} build system identity 漂移")
        if adapter.build_system == "make" and not callable(getattr(lifecycle.make_reference.provenance, "command_history_sha256", None)):
            raise ConfirmatoryRepairError("Make pair 缺少通用 provenance history evaluator")
        build_systems.add(adapter.build_system)
        reference_case_ids[pair["case_id"]] = expected
    if build_systems != {"cmake", "make"}:
        raise ConfirmatoryRepairError("repair gate 未覆盖 CMake 与 Make")
    return {
        "status": "passed",
        "pair_count": len(pairs),
        "case_count": len(reference_case_ids),
        "build_systems": sorted(build_systems),
        "reference_case_ids": reference_case_ids,
        "provider_calls": 0,
        "credential_read": False,
        "formal_attempts": 0,
        "model_tokens": 0,
        "evidence_writes": 0,
    }


def execute_real_pair(
    manifest: dict[str, Any],
    pair: dict[str, Any],
    pair_dir: Path,
    async_runner: asyncio.Runner,
    reachability: dict[str, Any],
    release: dict[str, str],
    model_factory: Callable[[dict[str, Any], str], Any] | None = None,
) -> dict[str, Any]:
    adapter = lifecycle.build_case_adapter(pair["case_id"], REPO_ROOT)
    pair_manifest = _pair_manifest(manifest, pair, pair_dir)
    with v1._pair_bindings(
        manifest,
        pair_manifest,
        adapter,
        pair_dir,
        release,
        reachability,
        async_runner,
    ) as base:
        if adapter.build_system == "make":
            base.make_lifecycle.provenance = lifecycle.make_reference.provenance
        report = base._run_pair(
            pair_manifest,
            output_dir=pair_dir,
            repo_root=REPO_ROOT,
            model_factory=model_factory,
        )
    return v1._pair_outcome(manifest, pair, pair_manifest, report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate",))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    try:
        manifest = v1.protocol.load_manifest(args.manifest)
        result = validate_contract(manifest)
    except (OSError, ConfirmatoryRepairError, v1.protocol.ProtocolError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
