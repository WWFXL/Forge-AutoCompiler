#!/usr/bin/env python3
"""未授权 verifier-driven repair pilot runner 门禁与反馈 context 构造器。"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_verifier_repair_pilot_protocol as protocol  # noqa: E402
import forge_verifier_repair_runtime as repair_runtime  # noqa: E402


class RunnerError(ValueError):
    pass


def load_manifest(path: Path = protocol.DEFAULT_MANIFEST) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunnerError(f"cannot read runtime candidate manifest: {path}") from exc
    try:
        return protocol.validate_manifest(document)
    except protocol.ProtocolError as exc:
        raise RunnerError(str(exc)) from exc


def slot_by_order(manifest: dict[str, Any], order: int) -> dict[str, Any]:
    protocol.validate_manifest(manifest)
    matches = [slot for slot in manifest["pilot_schedule"] if slot["order"] == order]
    if len(matches) != 1:
        raise RunnerError("pilot schedule order is invalid")
    return matches[0]


def build_feedback_context(
    manifest: dict[str, Any],
    *,
    order: int,
    thread_id: str,
    event_reader: Callable[[], Sequence[Mapping[str, Any]]],
    evidence: repair_runtime.RepairEvidenceLedger,
) -> repair_runtime.RepairFeedbackContext:
    slot = slot_by_order(manifest, order)
    case = next(
        (item for item in manifest["cases"] if item["id"] == slot["case_id"]), None
    )
    if case is None:
        raise RunnerError("pilot case is missing")
    expected_artifacts = tuple(
        (artifact["staged_relative_path"], artifact["artifact_type"])
        for artifact in case["artifact_oracle"]["required_artifacts"]
    )
    return repair_runtime.RepairFeedbackContext(
        thread_id=thread_id,
        pair_id=slot["pair_id"],
        case_id=slot["case_id"],
        provider_condition=slot["provider_condition"],
        treatment=slot["treatment"],
        repetition=slot["repetition"],
        expected_build_system=case["build_system"],
        expected_artifacts=expected_artifacts,
        event_reader=event_reader,
        evidence=evidence,
    )


def sidecar_context_payload(
    manifest: dict[str, Any], *, order: int, thread_id: str, physical_attempt_id: str
) -> dict[str, Any]:
    slot = slot_by_order(manifest, order)
    return {
        "manifest_sha256": protocol.manifest_sha256(manifest),
        "thread_id": thread_id,
        "physical_attempt_id": physical_attempt_id,
        "order": slot["order"],
        "pair_id": slot["pair_id"],
        "case_id": slot["case_id"],
        "provider_condition": slot["provider_condition"],
        "treatment": slot["treatment"],
        "repetition": slot["repetition"],
    }


def _reject_collection() -> None:
    raise RunnerError(
        "Verifier-driven repair collection is not authorized; model execution and evidence creation are forbidden"
    )


def provider_canary(*_args: Any, **_kwargs: Any) -> None:
    _reject_collection()


def run_attempt(*_args: Any, **_kwargs: Any) -> None:
    _reject_collection()


def run_batch(*_args: Any, **_kwargs: Any) -> None:
    _reject_collection()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("validate-manifest", "provider-canary", "run-attempt", "run-batch"),
    )
    parser.add_argument("--manifest", type=Path, default=protocol.DEFAULT_MANIFEST)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        if args.command != "validate-manifest":
            _reject_collection()
    except (RunnerError, protocol.ProtocolError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "collection_authorized": False,
                "manifest_sha256": protocol.manifest_sha256(manifest),
                "status": "valid",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
