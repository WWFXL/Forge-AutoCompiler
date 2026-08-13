#!/usr/bin/env python3
"""执行 300 秒超时校准 canary 接线修订。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_formal_timeout_calibration_canary_amendment_protocol as protocol  # noqa: E402


def _load_parent_runner():
    module_name = f"{__name__}_parent"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_ROOT / "forge_formal_timeout_calibration_runner.py")
    if spec is None or spec.loader is None:
        raise ImportError("Unable to load the timeout calibration runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_parent = _load_parent_runner()
_authorized_runner = _parent._runner
_base_runner = _authorized_runner._runner
_original_collect_preflight = _base_runner.collect_preflight
_original_collect_provider_canary = _authorized_runner.collect_provider_canary
_original_create_attempt = _authorized_runner.create_attempt
_original_run_timeout_calibration_batch = _parent.run_timeout_calibration_batch

_parent.protocol = protocol
_authorized_runner.protocol = protocol
_base_runner.protocol_formal_collection = protocol

RunnerError = _parent.RunnerError
REPO_ROOT = _parent.REPO_ROOT
DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST


def _superseded_output_dir(manifest: dict[str, Any]) -> Path:
    return Path(manifest["authorization"]["superseded_canary_terminal"]["evidence_directory"])


def _verify_superseded_canary_terminal(manifest: dict[str, Any], *, output_dir: Path | None = None) -> dict[str, Any]:
    frozen = manifest["authorization"]["superseded_canary_terminal"]
    directory = output_dir or _superseded_output_dir(manifest)
    marker_path = directory / frozen["marker_relative_path"]
    try:
        raw = marker_path.read_bytes()
        marker = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise RunnerError("The superseded timeout calibration canary marker is missing or invalid") from exc
    if hashlib.sha256(raw).hexdigest() != frozen["marker_sha256"]:
        raise RunnerError("The superseded timeout calibration canary marker changed")
    expected = {
        "benchmark_id": frozen["benchmark_id"],
        "manifest_sha256": frozen["manifest_sha256"],
        "status": frozen["status"],
        "error_class": frozen["error_class"],
    }
    if any(marker.get(key) != value for key, value in expected.items()):
        raise RunnerError("The superseded timeout calibration canary identity changed")
    reports = [path for path in (directory / "provider-canaries").glob("*.json") if path != marker_path]
    ledgers = list(directory.rglob("*.jsonl"))
    if len(reports) != frozen["provider_report_count"] or len(ledgers) != frozen["formal_ledger_count"]:
        raise RunnerError("The superseded timeout calibration evidence layer changed")
    return {"status": marker["status"], "provider_report_count": len(reports), "formal_ledger_count": len(ledgers)}


@contextmanager
def _anonymous_endpoint_preflight_disabled():
    original = _base_runner.collect_preflight

    def collect_without_endpoint(*args: Any, **kwargs: Any):
        kwargs["check_endpoint"] = False
        return _original_collect_preflight(*args, **kwargs)

    _base_runner.collect_preflight = collect_without_endpoint
    try:
        yield
    finally:
        _base_runner.collect_preflight = original


def collect_provider_canary(manifest: dict[str, Any], *, manifest_path: Path, output_dir: Path, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if manifest.get("schema_version") != protocol.SCHEMA_VERSION:
        raise RunnerError("Provider canary is only valid for the timeout canary amendment")
    _verify_superseded_canary_terminal(manifest)
    with _anonymous_endpoint_preflight_disabled():
        return _original_collect_provider_canary(manifest, manifest_path=manifest_path, output_dir=output_dir, repo_root=repo_root)


def create_attempt(manifest: dict[str, Any], **kwargs: Any):
    if manifest.get("schema_version") == protocol.SCHEMA_VERSION:
        _verify_superseded_canary_terminal(manifest)
        kwargs["check_endpoint"] = False
    return _original_create_attempt(manifest, **kwargs)


def run_timeout_canary_amendment_batch(manifest: dict[str, Any], *, manifest_path: Path, output_dir: Path, max_attempts: int, check_endpoint: bool = True) -> dict[str, Any]:
    del check_endpoint
    if manifest.get("schema_version") != protocol.SCHEMA_VERSION:
        raise RunnerError("Timeout canary amendment requires its frozen protocol identity")
    _verify_superseded_canary_terminal(manifest)
    return _original_run_timeout_calibration_batch(
        manifest,
        manifest_path=manifest_path,
        output_dir=output_dir,
        max_attempts=max_attempts,
        check_endpoint=False,
    )


_authorized_runner.collect_provider_canary = collect_provider_canary
_authorized_runner.create_attempt = create_attempt
_base_runner.collect_provider_canary = collect_provider_canary
_base_runner.create_attempt = create_attempt
_base_runner.run_formal_batch = run_timeout_canary_amendment_batch


def _arguments_with_default_manifest(argv: list[str]) -> list[str]:
    if not argv or argv[0] == "runtime-preflight" or "--manifest" in argv:
        return argv
    return [argv[0], "--manifest", str(DEFAULT_MANIFEST), *argv[1:]]


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    return _base_runner.main(_arguments_with_default_manifest(arguments))


def __getattr__(name: str):
    return getattr(_parent, name)


if __name__ == "__main__":
    raise SystemExit(main())
