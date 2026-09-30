#!/usr/bin/env python3
"""执行并审计 mechanism v2 独立 36-arm formal collection。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_contract_driven_repair_mechanism_v1_formal_failure_audit as failure_audit  # noqa: E402
import forge_contract_driven_repair_mechanism_v1_formal_runner as base  # noqa: E402

_FROZEN_MARKER_UPDATE = base._update_claimed_marker

import forge_contract_driven_repair_mechanism_v1_formal_marker_repair as marker_repair  # noqa: E402
import forge_contract_driven_repair_mechanism_v2_formal_protocol as protocol  # noqa: E402

# marker repair 为旧入口保留 import-time 安装；v2 runner 只允许显式局部绑定。
base._update_claimed_marker = _FROZEN_MARKER_UPDATE

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_OUTPUT_DIR = REPO_ROOT / protocol.independent.EVIDENCE_DIRECTORY
COMMANDS = ("validate", "plan", "preflight", "batch", "report", "audit")

_ORIGINAL_PROTOCOL = base.protocol
_REPAIRED_MARKER_UPDATE = marker_repair.update_claimed_marker
_RUNTIME_BINDING_LOCK = threading.Lock()


class IndependentFormalRunnerError(RuntimeError):
    """v2 formal release、evidence、repair 或执行边界无效。"""


@contextmanager
def _runtime_binding() -> Iterator[None]:
    """串行绑定 v2 protocol 与已审阅 marker repair，退出后恢复 frozen runner。"""

    if not _RUNTIME_BINDING_LOCK.acquire(blocking=False):
        raise IndependentFormalRunnerError("v2 formal runtime binding 只允许串行进入")
    observed_protocol = base.protocol
    observed_update = base._update_claimed_marker
    try:
        if observed_protocol is not _ORIGINAL_PROTOCOL:
            raise IndependentFormalRunnerError(
                "frozen runner protocol binding 已被修改"
            )
        if observed_update is not _FROZEN_MARKER_UPDATE:
            raise IndependentFormalRunnerError("frozen runner marker helper 已被修改")
        base.protocol = protocol
        base._update_claimed_marker = _REPAIRED_MARKER_UPDATE
        yield
    finally:
        base.protocol = observed_protocol
        base._update_claimed_marker = observed_update
        _RUNTIME_BINDING_LOCK.release()


def _old_evidence_inventory(repo_root: Path) -> dict[str, Any]:
    evidence = repo_root / protocol.independent.OLD_EVIDENCE_DIRECTORY
    references = failure_audit.verify_source_inventory(evidence)
    inventory_sha256 = failure_audit._inventory_sha256(references)
    if (
        len(references) != protocol.independent.FAILED_EVIDENCE_FILE_COUNT
        or inventory_sha256 != protocol.independent.FAILED_EVIDENCE_INVENTORY_SHA256
    ):
        raise IndependentFormalRunnerError("v1 frozen evidence inventory 漂移")
    return {
        "directory": protocol.independent.OLD_EVIDENCE_DIRECTORY,
        "file_count": len(references),
        "inventory_sha256": inventory_sha256,
        "read_only": True,
        "imported": False,
    }


def _strict_evidence_inventory(
    manifest: dict[str, Any], output_dir: Path, *, require_formal_absent: bool
) -> list[str]:
    marker = manifest["candidate_evidence"]["availability_marker"]
    allowed = {marker, *base._formal_relative_files(manifest)}
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise IndependentFormalRunnerError("v2 evidence root 不存在或不是普通目录")
    observed: list[str] = []
    for path in output_dir.rglob("*"):
        if path.is_symlink():
            raise IndependentFormalRunnerError("v2 evidence root 含符号链接")
        if path.is_file():
            relative = path.relative_to(output_dir).as_posix()
            if relative.endswith(".tmp") or relative not in allowed:
                raise IndependentFormalRunnerError(
                    f"v2 evidence root 含未授权文件: {relative}"
                )
            observed.append(relative)
    observed.sort()
    if marker not in observed:
        raise IndependentFormalRunnerError("v2 availability marker 缺失")
    if require_formal_absent and observed != [marker]:
        raise IndependentFormalRunnerError(
            "formal 启动前 evidence 必须只有 availability marker"
        )
    return observed


def _validate_runtime_bound(
    manifest: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    marker_repair._verify_frozen_runner()
    if marker_repair._frozen_update_claimed_marker is not _FROZEN_MARKER_UPDATE:
        raise IndependentFormalRunnerError("marker repair 未绑定 frozen helper")
    result = base.validate_runtime(manifest, repo_root)
    execution = manifest["formal_execution"]
    if (
        execution.get("execution_authorized") is not True
        or execution.get("marker_repair_file_sha256")
        != protocol.independent.MARKER_REPAIR_FILE_SHA256
        or execution.get("frozen_runner_file_sha256")
        != protocol.independent.FROZEN_RUNNER_FILE_SHA256
    ):
        raise IndependentFormalRunnerError("v2 formal execution 或 repair 授权漂移")
    return {
        **result,
        "marker_repair_status": "installed_in_serial_runtime_binding",
        "historical_v1_arm_imported": False,
        "availability_repeated": False,
    }


def validate_runtime(
    manifest: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    with _runtime_binding():
        return _validate_runtime_bound(manifest, repo_root)


def _collect_preflight_bound(
    manifest: dict[str, Any],
    *,
    output_dir: Path,
    repo_root: Path,
    require_formal_absent: bool,
) -> dict[str, Any]:
    _validate_runtime_bound(manifest, repo_root)
    result = base.collect_preflight(
        manifest,
        output_dir=output_dir,
        repo_root=repo_root,
        require_formal_absent=require_formal_absent,
    )
    inventory = _strict_evidence_inventory(
        manifest, output_dir, require_formal_absent=require_formal_absent
    )
    return {
        **result,
        "status": "independent_formal_collection_preflight_passed_not_started",
        "old_evidence": _old_evidence_inventory(repo_root),
        "v2_evidence_inventory": inventory,
        "availability_repeated": False,
        "historical_v1_arm_imported": False,
    }


def collect_preflight(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    require_formal_absent: bool = True,
) -> dict[str, Any]:
    with _runtime_binding():
        return _collect_preflight_bound(
            manifest,
            output_dir=output_dir,
            repo_root=repo_root,
            require_formal_absent=require_formal_absent,
        )


async def execute_batch(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    with _runtime_binding():
        batch_marker = output_dir / manifest["formal_execution"]["batch_marker"]
        _collect_preflight_bound(
            manifest,
            output_dir=output_dir,
            repo_root=repo_root,
            require_formal_absent=not batch_marker.exists(),
        )
        report = await base.execute_batch(
            manifest, output_dir=output_dir, repo_root=repo_root
        )
        base._require_zero_managed_resources()
        return report


def audit_batch(
    manifest: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR
) -> dict[str, Any]:
    with _runtime_binding():
        inventory = _strict_evidence_inventory(
            manifest, output_dir, require_formal_absent=False
        )
        result = base.audit_batch(manifest, output_dir)
        base._require_zero_managed_resources()
        return {
            **result,
            "v2_evidence_file_count": len(inventory),
            "historical_v1_arm_imported": False,
            "availability_repeated": False,
            "zero_managed_resources": True,
        }


def show_plan(manifest: dict[str, Any]) -> dict[str, Any]:
    with _runtime_binding():
        return base.show_plan(manifest)


def build_live_report(
    manifest: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR
) -> dict[str, Any]:
    with _runtime_binding():
        results = base.completed_prefix(manifest, output_dir)
        return base.build_report(manifest, results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest(args.manifest)
    if args.command == "validate":
        result: Mapping[str, Any] = validate_runtime(manifest)
    elif args.command == "plan":
        result = show_plan(manifest)
    elif args.command == "preflight":
        result = collect_preflight(manifest, output_dir=args.output_dir)
    elif args.command == "batch":
        result = asyncio.run(execute_batch(manifest, output_dir=args.output_dir))
    elif args.command == "report":
        result = build_live_report(manifest, args.output_dir)
    else:
        result = audit_batch(manifest, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
