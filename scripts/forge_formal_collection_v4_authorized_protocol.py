#!/usr/bin/env python3
"""生成并校验 formal v4 首批完整项目块授权协议。"""

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
REPOSITORY_SCRIPT_ROOT = REPOSITORY_ROOT / "scripts"
if str(REPOSITORY_SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_SCRIPT_ROOT))

import forge_benchmark as v1  # noqa: E402
import forge_formal_collection_v4_ubuntu_protocol as parent_protocol  # noqa: E402
import forge_formal_runtime_protocol as _hasher  # noqa: E402

SCHEMA_VERSION = "formal-collection-4.3.0-ubuntu-authorized"
BASELINE_COMMIT = "c079f31c1623111e3dd776952b151181cfa37a00"
REVISION_POLICY = parent_protocol.REVISION_POLICY
CONTROL_PLANE_TOPOLOGY = parent_protocol.CONTROL_PLANE_TOPOLOGY
DOCKER_DAEMON_PROVIDER = parent_protocol.DOCKER_DAEMON_PROVIDER
DOCKER_SOCKET_PATH = parent_protocol.DOCKER_SOCKET_PATH
DEFAULT_PARENT_MANIFEST = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-formal-v4-ubuntu-candidate.json"
DEFAULT_MANIFEST = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-formal-v4-authorized-initial-block.json"
DEFAULT_SCHEMA = REPOSITORY_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-collection-v4-authorized.schema.json"
COMPONENT_PATHS = parent_protocol.COMPONENT_PATHS
PROTOCOL_ARTIFACT_PATHS = parent_protocol.PROTOCOL_ARTIFACT_PATHS | {
    "scripts/forge_formal_collection_v4_authorized_protocol.py",
    "scripts/forge_formal_collection_v4_authorized_runner.py",
    "scripts/forge_formal_collection_v4_authorized_report.py",
    "benchmarks/preregistrations/cpp-formal-v4-authorized-initial-block.md",
    "benchmarks/schemas/forge-cpp-formal-collection-v4-authorized.schema.json",
}
AUTHORIZED_EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-formal-v4-authorized-initial-block"
AUTHORIZED_SCHEDULE_ORDERS = [1, 2, 73, 74, 153, 154]
BATCH_TOKEN_LIMIT = 980_000
INITIAL_BATCH_DECISION = {
    **copy.deepcopy(parent_protocol.INITIAL_BATCH_DECISION),
    "status": "authorized_by_experiment_owner",
}
AUTHORIZATION = {
    "id": "forge-cpp-formal-v4-authorized-initial-block",
    "status": "authorized_initial_complete_project_block",
    "authorized_by": "experiment_owner",
    "authorized_on": "2026-08-12",
    "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/111",
    "implementation_baseline_commit": BASELINE_COMMIT,
    "network_observation": {
        "access_medium": "mobile_hotspot",
        "browser_ui_required": False,
    },
    "budget_confirmation": {
        "confirmed": True,
        "maximum_recorded_tokens": BATCH_TOKEN_LIMIT,
        "enforcement": "stop_before_next_slot_when_recorded_total_reaches_limit",
        "terminalization_cleanup_precedes_token_boundary_check": True,
    },
    "collection_constraints": {
        "planned_attempts": 180,
        "authorized_slot_count": 6,
        "authorized_schedule_orders": AUTHORIZED_SCHEDULE_ORDERS,
        "remaining_slot_count": 174,
        "remaining_slots_require_additional_confirmation": True,
        "complete_project_blocks": 1,
        "provider_canary_required_before_first_ledger": True,
        "provider_canary_max_attempts": 1,
        "empty_ledger_required_before_canary": True,
        "zero_residual_formal_containers_required_before_canary": True,
        "replacement_forbidden": True,
        "fallback_forbidden": True,
        "retry_forbidden": True,
        "backfill_forbidden": True,
        "v3_slots_8_to_10_forbidden": True,
        "required_runtime_launch_checks": copy.deepcopy(parent_protocol.RESOURCE_PREFLIGHT["required_checks"]),
        "evidence_directory": AUTHORIZED_EVIDENCE_DIRECTORY,
    },
}

BenchmarkError = v1.BenchmarkError
load_json_document = v1.load_json_document
canonical_json_bytes = parent_protocol.canonical_json_bytes


def _parent_manifest(document: dict[str, Any] | None = None) -> dict[str, Any]:
    parent = document or load_json_document(DEFAULT_PARENT_MANIFEST)
    return parent_protocol.validate_manifest(parent)


def _authorization(parent: dict[str, Any]) -> dict[str, Any]:
    return {
        **copy.deepcopy(AUTHORIZATION),
        "parent_manifest": {
            "id": parent["benchmark"]["id"],
            "path": "benchmarks/manifests/cpp-formal-v4-ubuntu-candidate.json",
            "canonical_sha256": parent_protocol.manifest_sha256(parent),
        },
    }


def _build_manifest(
    repo_root: Path,
    *,
    parent: dict[str, Any],
) -> dict[str, Any]:
    manifest = copy.deepcopy(parent)
    manifest["$schema"] = "../schemas/forge-cpp-formal-collection-v4-authorized.schema.json"
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["benchmark"] = {
        "id": "forge-cpp-formal-v4-authorized-initial-block",
        "name": "Forge C/C++ formal v4 authorized initial project block",
        "purpose": "authorized append-only collection of one complete paired project block",
        "dataset_provenance": parent["benchmark"]["dataset_provenance"],
    }
    manifest["scope"] = {
        "languages": ["C", "C++"],
        "phase": "formal_collection_v4_authorized_initial_block",
        "formal_comparison_enabled": True,
        "collection_authorized": True,
        "instrumentation_blocker": False,
    }
    manifest["forge"] = {
        **copy.deepcopy(parent["forge"]),
        "commit_sha": BASELINE_COMMIT,
        "component_sha256": _hasher._hash_paths(repo_root, COMPONENT_PATHS),
    }
    manifest["protocol_artifact_sha256"] = _hasher._hash_paths(repo_root, PROTOCOL_ARTIFACT_PATHS)
    manifest["prompt_sha256"] = _hasher._hash_paths(repo_root, set(parent["prompt_sha256"]))
    manifest["initial_batch_decision"] = copy.deepcopy(INITIAL_BATCH_DECISION)
    manifest["authorization"] = _authorization(parent)
    return manifest


def generate_manifest(
    repo_root: Path = REPOSITORY_ROOT,
    *,
    parent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _build_manifest(repo_root, parent=_parent_manifest(parent))


def _selected_slots(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    by_order = {slot["order"]: slot for slot in manifest["collection_plan"]}
    return [by_order[order] for order in AUTHORIZED_SCHEDULE_ORDERS if order in by_order]


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
            v1._fail("manifest", "must match the authorized formal v4 initial block exactly")
        selected = _selected_slots(manifest)
        if len(selected) != 6 or {slot["case_id"] for slot in selected} != {"cppitertools"}:
            v1._fail("manifest.authorization", "must authorize the complete cppitertools project block")
        if {(slot["condition_id"], slot["repetition"]) for slot in selected} != {(condition["id"], repetition) for condition in manifest["conditions"] for repetition in range(1, 4)}:
            v1._fail("manifest.authorization", "must cover both conditions and all three repetitions")
        return manifest
    except BenchmarkError:
        raise
    except (AttributeError, KeyError, OSError, TypeError, ValueError) as exc:
        raise BenchmarkError(f"manifest: invalid formal v4 authorization: {exc}") from exc


def canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return canonical_json_bytes(manifest)


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()


def verify_frozen_components(
    manifest: dict[str, Any],
    repo_root: Path = REPOSITORY_ROOT,
) -> None:
    validate_manifest(manifest, repo_root=repo_root)
    parent_path = repo_root / manifest["authorization"]["parent_manifest"]["path"]
    parent = _parent_manifest(load_json_document(parent_path))
    if parent_protocol.manifest_sha256(parent) != manifest["authorization"]["parent_manifest"]["canonical_sha256"]:
        v1._fail("manifest.authorization.parent_manifest", "does not match the reviewed Ubuntu candidate")
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
    schema["$id"] = "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-cpp-formal-collection-v4-authorized.schema.json"
    schema["title"] = "Forge C/C++ authorized formal v4 initial project block"
    properties = schema["properties"]
    properties["$schema"] = {"const": "../schemas/forge-cpp-formal-collection-v4-authorized.schema.json"}
    properties["schema_version"] = {"const": SCHEMA_VERSION}
    properties["benchmark"] = {
        "const": {
            "id": "forge-cpp-formal-v4-authorized-initial-block",
            "name": "Forge C/C++ formal v4 authorized initial project block",
            "purpose": "authorized append-only collection of one complete paired project block",
            "dataset_provenance": parent["benchmark"]["dataset_provenance"],
        }
    }
    properties["scope"] = {
        "const": {
            "languages": ["C", "C++"],
            "phase": "formal_collection_v4_authorized_initial_block",
            "formal_comparison_enabled": True,
            "collection_authorized": True,
            "instrumentation_blocker": False,
        }
    }
    properties["forge"]["properties"]["commit_sha"] = {"const": BASELINE_COMMIT}
    properties["forge"]["properties"]["component_sha256"] = _hash_map_schema(COMPONENT_PATHS)
    properties["protocol_artifact_sha256"] = _hash_map_schema(PROTOCOL_ARTIFACT_PATHS)
    properties["prompt_sha256"] = _hash_map_schema(set(parent["prompt_sha256"]))
    properties["initial_batch_decision"] = {"const": copy.deepcopy(INITIAL_BATCH_DECISION)}
    properties["authorization"] = {"const": _authorization(parent)}
    return schema


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


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
                    "authorization_status": manifest["authorization"]["status"],
                    "authorized_schedule_orders": AUTHORIZED_SCHEDULE_ORDERS,
                    "benchmark_id": manifest["benchmark"]["id"],
                    "collection_authorized": manifest["scope"]["collection_authorized"],
                    "manifest_sha256": manifest_sha256(manifest),
                    "maximum_recorded_tokens": BATCH_TOKEN_LIMIT,
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
