#!/usr/bin/env python3
"""Authorized initial-batch adapter for the Forge formal-collection v2 runner."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_formal_collection_v2_authorized_protocol as authorized_protocol  # noqa: E402
import forge_formal_collection_v2_runner as _runner  # noqa: E402

_runner.protocol_formal_collection = authorized_protocol
_original_create_attempt = _runner.create_attempt
_original_run_formal_batch = _runner.run_formal_batch

RunnerError = _runner.RunnerError
REPO_ROOT = _runner.REPO_ROOT


def _authorized_slot_count(manifest: dict[str, Any]) -> int:
    return int(manifest["authorization"]["collection_constraints"]["authorized_slot_count"])


def _slot_index(
    manifest: dict[str, Any],
    *,
    case_id: str,
    condition_id: str,
    repetition: int,
) -> int:
    target = {
        "case_id": case_id,
        "condition_id": condition_id,
        "repetition": repetition,
    }
    for index, slot in enumerate(manifest["collection_plan"]):
        if {
            "case_id": slot["case_id"],
            "condition_id": slot["condition_id"],
            "repetition": slot["repetition"],
        } == target:
            return index
    raise RunnerError("The requested slot is not part of the frozen collection")


def create_attempt(
    manifest: dict[str, Any],
    *,
    case_id: str,
    condition_id: str,
    repetition: int,
    **kwargs: Any,
):
    if manifest.get("schema_version") == authorized_protocol.SCHEMA_VERSION:
        index = _slot_index(
            manifest,
            case_id=case_id,
            condition_id=condition_id,
            repetition=repetition,
        )
        if index >= _authorized_slot_count(manifest):
            raise RunnerError("The initial authorization stops before this frozen slot")
    return _original_create_attempt(
        manifest,
        case_id=case_id,
        condition_id=condition_id,
        repetition=repetition,
        **kwargs,
    )


def run_formal_batch(
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    output_dir: Path,
    max_attempts: int,
    check_endpoint: bool = True,
) -> dict[str, Any]:
    if manifest.get("schema_version") == authorized_protocol.SCHEMA_VERSION:
        observed = _runner._observed_collection_ledgers(
            manifest,
            output_dir=output_dir,
        )
        remaining = _authorized_slot_count(manifest) - len(observed)
        if remaining <= 0:
            raise RunnerError("The authorized ten-slot boundary has already been reached")
        if max_attempts > remaining:
            raise RunnerError("The requested batch would cross the authorized ten-slot boundary")
    return _original_run_formal_batch(
        manifest,
        manifest_path=manifest_path,
        output_dir=output_dir,
        max_attempts=max_attempts,
        check_endpoint=check_endpoint,
    )


_runner.create_attempt = create_attempt
_runner.run_formal_batch = run_formal_batch


def main(argv: list[str] | None = None) -> int:
    return _runner.main(argv)


def __getattr__(name: str):
    return getattr(_runner, name)


if __name__ == "__main__":
    raise SystemExit(main())
