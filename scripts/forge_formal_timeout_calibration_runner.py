#!/usr/bin/env python3
"""执行 formal 模型请求 300 秒超时校准。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_formal_timeout_calibration_protocol as protocol  # noqa: E402


def _load_parent_runner():
    module_name = f"{__name__}_parent"
    spec = importlib.util.spec_from_file_location(
        module_name,
        SCRIPT_ROOT / "forge_formal_collection_v4_authorized_runner.py",
    )
    if spec is None or spec.loader is None:
        raise ImportError("Unable to load the formal v4 authorized runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_runner = _load_parent_runner()
_runner.protocol = protocol
_runner._runner.protocol_formal_collection = protocol

RunnerError = _runner.RunnerError
REPO_ROOT = _runner.REPO_ROOT
DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST


def _authorized_slots(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return protocol.selected_slots(manifest)


def run_timeout_calibration_batch(
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    output_dir: Path,
    max_attempts: int,
    check_endpoint: bool = True,
) -> dict[str, Any]:
    if manifest.get("schema_version") != protocol.SCHEMA_VERSION:
        raise RunnerError("Timeout calibration requires its frozen protocol identity")
    if max_attempts < 1 or max_attempts > len(protocol.AUTHORIZED_SCHEDULE_ORDERS):
        raise RunnerError("Timeout calibration permits at most two attempts")
    result = _runner.run_formal_batch(
        manifest,
        manifest_path=manifest_path,
        output_dir=output_dir,
        max_attempts=max_attempts,
        check_endpoint=check_endpoint,
    )
    if result["next_authorized_index"] == len(protocol.AUTHORIZED_SCHEDULE_ORDERS):
        result["status"] = "timeout_calibration_complete"
    return result


_runner._authorized_slots = _authorized_slots
_runner._runner.run_formal_batch = run_timeout_calibration_batch


def _arguments_with_default_manifest(argv: list[str]) -> list[str]:
    if not argv or argv[0] == "runtime-preflight" or "--manifest" in argv:
        return argv
    return [argv[0], "--manifest", str(DEFAULT_MANIFEST), *argv[1:]]


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    return _runner._runner.main(_arguments_with_default_manifest(arguments))


def __getattr__(name: str):
    return getattr(_runner, name)


if __name__ == "__main__":
    raise SystemExit(main())
