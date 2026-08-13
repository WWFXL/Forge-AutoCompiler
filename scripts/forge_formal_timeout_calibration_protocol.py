#!/usr/bin/env python3
"""生成并校验 formal 模型请求 300 秒超时校准协议。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", SCRIPT_ROOT.parent)).resolve()
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_benchmark as v1  # noqa: E402
import forge_formal_collection_v4_canary_amendment_protocol as parent_protocol  # noqa: E402
import forge_formal_runtime_protocol as _hasher  # noqa: E402

SCHEMA_VERSION = "formal-collection-4.5.0-timeout-calibration"
BASELINE_COMMIT = "762b53c6024f5fac45b82a9fc1194b4b86cf5fe0"
REQUEST_TIMEOUT_SECONDS = 300
AUTHORIZED_SCHEDULE_ORDERS = [1, 2]
RECORDED_TOKEN_LIMIT = 500_000
PARENT_CANONICAL_SHA256 = "e296138d6464adc6e7c12d4ee29d1f22c178d53a463b3467e2d2442e5fd66587"

REVISION_POLICY = parent_protocol.REVISION_POLICY
CONTROL_PLANE_TOPOLOGY = parent_protocol.CONTROL_PLANE_TOPOLOGY
DOCKER_DAEMON_PROVIDER = parent_protocol.DOCKER_DAEMON_PROVIDER
DOCKER_SOCKET_PATH = parent_protocol.DOCKER_SOCKET_PATH
COMPONENT_PATHS = parent_protocol.COMPONENT_PATHS
DEFAULT_PARENT_MANIFEST = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-formal-v4-canary-amendment.json"
DEFAULT_MANIFEST = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-formal-timeout-calibration.json"
DEFAULT_SCHEMA = REPOSITORY_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-timeout-calibration.schema.json"
EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-formal-timeout-calibration"
PROTOCOL_ARTIFACT_PATHS = parent_protocol.PROTOCOL_ARTIFACT_PATHS | {
    "scripts/forge_formal_timeout_calibration_protocol.py",
    "scripts/forge_formal_timeout_calibration_runner.py",
    "scripts/forge_formal_timeout_calibration_report.py",
    "benchmarks/preregistrations/cpp-formal-timeout-calibration.md",
    "benchmarks/schemas/forge-cpp-formal-timeout-calibration.schema.json",
}

AUTHORIZATION = {
    "id": "forge-cpp-formal-timeout-calibration",
    "status": "authorized_bounded_timeout_calibration",
    "authorized_by": "experiment_owner",
    "authorized_on": "2026-08-14",
    "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/117",
    "implementation_baseline_commit": BASELINE_COMMIT,
    "network_observation": {
        "access_medium": "mobile_hotspot",
        "browser_ui_required": False,
    },
    "calibration_hypothesis": {
        "observed_timeout_boundary_seconds": 120,
        "calibrated_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
        "success_criterion": "all_started_requests_close_with_append_only_evidence",
        "interpretation": "infrastructure_parameter_calibration_only",
    },
    "budget_confirmation": {
        "confirmed": True,
        "maximum_recorded_tokens": RECORDED_TOKEN_LIMIT,
        "enforcement": "stop_before_next_slot_when_recorded_total_reaches_limit",
        "terminalization_cleanup_precedes_token_boundary_check": True,
    },
    "collection_constraints": {
        "authorized_slot_count": 2,
        "authorized_schedule_orders": AUTHORIZED_SCHEDULE_ORDERS,
        "remaining_slots_require_additional_confirmation": True,
        "provider_canary_required_before_first_ledger": True,
        "provider_canary_max_attempts": 1,
        "empty_ledger_required_before_canary": True,
        "zero_residual_formal_containers_required_before_canary": True,
        "replacement_forbidden": True,
        "fallback_forbidden": True,
        "retry_forbidden": True,
        "backfill_forbidden": True,
        "formal_primary_pooling_forbidden": True,
        "required_runtime_launch_checks": copy.deepcopy(parent_protocol.AMENDMENT["collection_constraints"]["required_runtime_launch_checks"]),
        "evidence_directory": EVIDENCE_DIRECTORY,
    },
}

BenchmarkError = v1.BenchmarkError
load_json_document = v1.load_json_document
canonical_json_bytes = parent_protocol.canonical_json_bytes


def _parent_manifest(document: dict[str, Any] | None = None) -> dict[str, Any]:
    parent = parent_protocol.validate_manifest(document or load_json_document(DEFAULT_PARENT_MANIFEST))
    if parent_protocol.manifest_sha256(parent) != PARENT_CANONICAL_SHA256:
        v1._fail("manifest.authorization.parent_manifest", "does not match formal v4 canary amendment")
    return parent


def _authorization(parent: dict[str, Any]) -> dict[str, Any]:
    return {
        **copy.deepcopy(AUTHORIZATION),
        "parent_manifest": {
            "id": parent["benchmark"]["id"],
            "path": "benchmarks/manifests/cpp-formal-v4-canary-amendment.json",
            "canonical_sha256": parent_protocol.manifest_sha256(parent),
        },
    }


def _build_manifest(repo_root: Path, *, parent: dict[str, Any]) -> dict[str, Any]:
    manifest = copy.deepcopy(parent)
    manifest["$schema"] = "../schemas/forge-cpp-formal-timeout-calibration.schema.json"
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["benchmark"] = {
        "id": "forge-cpp-formal-timeout-calibration",
        "name": "Forge C/C++ formal model timeout calibration",
        "purpose": "calibrate a 300-second client request deadline without changing retry policy",
        "dataset_provenance": parent["benchmark"]["dataset_provenance"],
    }
    manifest["scope"] = {
        "languages": ["C", "C++"],
        "phase": "formal_timeout_calibration",
        "formal_comparison_enabled": False,
        "collection_authorized": True,
        "instrumentation_blocker": False,
    }
    manifest["forge"] = {
        **copy.deepcopy(parent["forge"]),
        "commit_sha": BASELINE_COMMIT,
        "component_sha256": _hasher._hash_paths(repo_root, COMPONENT_PATHS),
    }
    for profile in manifest["model_profiles"].values():
        profile["request_timeout_seconds"] = REQUEST_TIMEOUT_SECONDS
        profile["max_retries"] = 0
    manifest["protocol_artifact_sha256"] = _hasher._hash_paths(repo_root, PROTOCOL_ARTIFACT_PATHS)
    manifest["prompt_sha256"] = _hasher._hash_paths(repo_root, set(parent["prompt_sha256"]))
    manifest["authorization"] = _authorization(parent)
    return manifest


def generate_manifest(
    repo_root: Path = REPOSITORY_ROOT,
    *,
    parent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _build_manifest(repo_root, parent=_parent_manifest(parent))


def selected_slots(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    by_order = {slot["order"]: slot for slot in manifest["collection_plan"]}
    return [by_order[order] for order in AUTHORIZED_SCHEDULE_ORDERS]


def validate_manifest(
    document: Any,
    *,
    repo_root: Path = REPOSITORY_ROOT,
    parent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        manifest = v1._as_object(document, "manifest")
        expected = _build_manifest(repo_root, parent=_parent_manifest(parent))
        if manifest != expected:
            v1._fail("manifest", "must match the 300-second timeout calibration exactly")
        slots = selected_slots(manifest)
        if [(slot["condition_id"], slot["repetition"]) for slot in slots] != [
            ("richlab-gpt-5.5", 1),
            ("deepseek-v4-flash", 1),
        ]:
            v1._fail("manifest.authorization", "must contain one attempt per provider")
        return manifest
    except BenchmarkError:
        raise
    except (AttributeError, KeyError, OSError, TypeError, ValueError) as exc:
        raise BenchmarkError(f"manifest: invalid timeout calibration: {exc}") from exc


def canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return canonical_json_bytes(manifest)


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()


def verify_frozen_components(manifest: dict[str, Any], repo_root: Path = REPOSITORY_ROOT) -> None:
    validate_manifest(manifest, repo_root=repo_root)
    for path_prefix, hashes in (
        ("manifest.forge.component_sha256", manifest["forge"]["component_sha256"]),
        ("manifest.protocol_artifact_sha256", manifest["protocol_artifact_sha256"]),
        ("manifest.prompt_sha256", manifest["prompt_sha256"]),
    ):
        for relative_path, expected in hashes.items():
            if _hasher._file_sha256(repo_root / relative_path) != expected:
                v1._fail(f"{path_prefix}.{relative_path}", "does not match")


def _hash_map_schema(paths: set[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "required": sorted(paths),
        "additionalProperties": False,
        "properties": {relative_path: {"type": "string", "pattern": "^[0-9a-f]{64}$"} for relative_path in sorted(paths)},
    }


def schema_document() -> dict[str, Any]:
    schema = copy.deepcopy(parent_protocol.schema_document())
    parent = _parent_manifest()
    schema["$id"] = "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-cpp-formal-timeout-calibration.schema.json"
    schema["title"] = "Forge C/C++ formal model timeout calibration"
    properties = schema["properties"]
    properties["$schema"] = {"const": "../schemas/forge-cpp-formal-timeout-calibration.schema.json"}
    properties["schema_version"] = {"const": SCHEMA_VERSION}
    properties["benchmark"] = {"const": _build_manifest(REPOSITORY_ROOT, parent=parent)["benchmark"]}
    properties["scope"] = {"const": _build_manifest(REPOSITORY_ROOT, parent=parent)["scope"]}
    properties["forge"]["properties"]["commit_sha"] = {"const": BASELINE_COMMIT}
    properties["forge"]["properties"]["component_sha256"] = _hash_map_schema(COMPONENT_PATHS)
    properties["model_profiles"] = {"const": _build_manifest(REPOSITORY_ROOT, parent=parent)["model_profiles"]}
    properties["protocol_artifact_sha256"] = _hash_map_schema(PROTOCOL_ARTIFACT_PATHS)
    properties["prompt_sha256"] = _hash_map_schema(set(parent["prompt_sha256"]))
    properties["authorization"] = {"const": _authorization(parent)}
    return schema


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    generate.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    validate = subparsers.add_parser("validate-manifest")
    validate.add_argument("manifest", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "generate":
            _write_json(args.schema, schema_document())
            manifest = generate_manifest()
            _write_json(args.manifest, manifest)
        else:
            manifest = validate_manifest(load_json_document(args.manifest))
            verify_frozen_components(manifest)
        print(
            json.dumps(
                {
                    "authorized_schedule_orders": AUTHORIZED_SCHEDULE_ORDERS,
                    "benchmark_id": manifest["benchmark"]["id"],
                    "manifest_sha256": manifest_sha256(manifest),
                    "max_retries": 0,
                    "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
                    "status": "valid",
                },
                sort_keys=True,
            )
        )
        return 0
    except (BenchmarkError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
