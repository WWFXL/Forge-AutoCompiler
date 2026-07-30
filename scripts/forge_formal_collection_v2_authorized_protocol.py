#!/usr/bin/env python3
"""Generate and validate the authorized Forge formal-collection v2 protocol."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_benchmark as v1  # noqa: E402
import forge_formal_collection_v2_protocol as candidate_protocol  # noqa: E402

SCHEMA_VERSION = "formal-collection-2.1.0"
BASELINE_COMMIT = "85ae003d3195107381ac354c53e8d2793513ff18"
REVISION_POLICY = candidate_protocol.REVISION_POLICY
CONTROL_PLANE_TOPOLOGY = candidate_protocol.CONTROL_PLANE_TOPOLOGY
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PARENT_MANIFEST = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-formal-v2-collection.json"
DEFAULT_MANIFEST = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-formal-v2-authorized-collection.json"
DEFAULT_SCHEMA = REPOSITORY_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-collection-v2-authorized.schema.json"
COMPONENT_PATHS = candidate_protocol.COMPONENT_PATHS
PROTOCOL_ARTIFACT_PATHS = candidate_protocol.PROTOCOL_ARTIFACT_PATHS | {
    "scripts/forge_formal_collection_v2_authorized_runner.py",
    "scripts/forge_formal_collection_v2_authorized_protocol.py",
    "benchmarks/schemas/forge-cpp-formal-collection-v2-authorized.schema.json",
}
AUTHORIZATION = {
    "id": "forge-cpp-formal-v2-authorized-collection",
    "status": "authorized_initial_batch",
    "authorized_by": "experiment_owner",
    "authorized_on": "2026-07-30",
    "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/86",
    "budget_confirmation": {
        "confirmed": True,
        "maximum_tokens": 29315818,
        "maximum_serial_hours": 31.301,
        "tokens_observed_before_v2": 81152,
    },
    "collection_constraints": {
        "planned_attempts": 180,
        "initial_batch_size": 10,
        "authorized_slot_count": 10,
        "remaining_slots_require_additional_confirmation": True,
        "provider_canary_required_before_first_ledger": True,
        "replacement_forbidden": True,
        "fallback_forbidden": True,
        "backfill_forbidden": True,
        "superseded_launch_is_not_part_of_v2_analysis": True,
    },
}

BenchmarkError = v1.BenchmarkError
load_json_document = v1.load_json_document
canonical_json_bytes = candidate_protocol.canonical_json_bytes


def _parent_manifest(document: dict[str, Any] | None = None) -> dict[str, Any]:
    parent = document or load_json_document(DEFAULT_PARENT_MANIFEST)
    return candidate_protocol.validate_manifest(parent)


def _authorization(parent: dict[str, Any]) -> dict[str, Any]:
    return {
        **copy.deepcopy(AUTHORIZATION),
        "superseded_launch": copy.deepcopy(parent["authorization"]["superseded_launch"]),
        "parent_manifest": {
            "id": parent["benchmark"]["id"],
            "path": "benchmarks/manifests/cpp-formal-v2-collection.json",
            "canonical_sha256": candidate_protocol.manifest_sha256(parent),
        },
    }


def generate_manifest(
    repo_root: Path = REPOSITORY_ROOT,
    *,
    parent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parent = _parent_manifest(parent)
    manifest = copy.deepcopy(parent)
    manifest["$schema"] = "../schemas/forge-cpp-formal-collection-v2-authorized.schema.json"
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["benchmark"] = {
        "id": "forge-cpp-formal-v2-authorized-collection",
        "name": "Forge C/C++ repaired formal collection v2",
        "purpose": "authorized append-only initial-batch evidence collection",
        "dataset_provenance": parent["benchmark"]["dataset_provenance"],
    }
    manifest["scope"] = {
        "languages": ["C", "C++"],
        "phase": "formal_collection_v2",
        "formal_comparison_enabled": True,
        "collection_authorized": True,
        "instrumentation_blocker": False,
    }
    manifest["forge"] = {
        **copy.deepcopy(parent["forge"]),
        "commit_sha": BASELINE_COMMIT,
        "component_sha256": candidate_protocol.parent_protocol._hash_paths(
            repo_root,
            COMPONENT_PATHS,
        ),
    }
    manifest["protocol_artifact_sha256"] = candidate_protocol.parent_protocol._hash_paths(
        repo_root,
        PROTOCOL_ARTIFACT_PATHS,
    )
    manifest["authorization"] = _authorization(parent)
    return validate_manifest(manifest, parent=parent)


def validate_manifest(
    document: Any,
    *,
    parent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        manifest = v1._as_object(document, "manifest")
        expected_root = {
            "$schema",
            "schema_version",
            "document_type",
            "manifest_canonicalization",
            "benchmark",
            "scope",
            "source_protocols",
            "forge",
            "protocol_artifact_sha256",
            "prompt_sha256",
            "model_profiles",
            "runtime",
            "budget",
            "conditions",
            "collection_plan",
            "schedule_sha256",
            "cases",
            "authorization",
        }
        if set(manifest) != expected_root:
            v1._fail(
                "manifest",
                "must contain exactly the authorized formal collection v2 fields",
            )
        if manifest["$schema"] != ("../schemas/forge-cpp-formal-collection-v2-authorized.schema.json"):
            v1._fail(
                "manifest.$schema",
                "must reference the authorized v2 collection schema",
            )
        if manifest["schema_version"] != SCHEMA_VERSION:
            v1._fail("manifest.schema_version", f"must be {SCHEMA_VERSION!r}")
        if manifest["document_type"] != "manifest":
            v1._fail("manifest.document_type", "must be 'manifest'")
        v1._scan_for_unsafe_values(manifest)
        parent = _parent_manifest(parent)
        if manifest["benchmark"] != {
            "id": "forge-cpp-formal-v2-authorized-collection",
            "name": "Forge C/C++ repaired formal collection v2",
            "purpose": "authorized append-only initial-batch evidence collection",
            "dataset_provenance": parent["benchmark"]["dataset_provenance"],
        }:
            v1._fail(
                "manifest.benchmark",
                "must identify the authorized formal collection v2",
            )
        if manifest["scope"] != {
            "languages": ["C", "C++"],
            "phase": "formal_collection_v2",
            "formal_comparison_enabled": True,
            "collection_authorized": True,
            "instrumentation_blocker": False,
        }:
            v1._fail(
                "manifest.scope",
                "must authorize only the frozen formal collection v2",
            )
        immutable_fields = (
            "source_protocols",
            "prompt_sha256",
            "model_profiles",
            "runtime",
            "budget",
            "conditions",
            "collection_plan",
            "schedule_sha256",
            "cases",
        )
        for field in immutable_fields:
            if manifest[field] != parent[field]:
                v1._fail(
                    f"manifest.{field}",
                    "must remain identical to the reviewed v2 candidate",
                )
        forge = v1._as_object(manifest["forge"], "manifest.forge")
        if set(forge) != set(parent["forge"]):
            v1._fail(
                "manifest.forge",
                "must contain exactly the inherited Forge identity fields",
            )
        if forge["repository_url"] != parent["forge"]["repository_url"]:
            v1._fail(
                "manifest.forge.repository_url",
                "must preserve the repository",
            )
        if forge["commit_sha"] != BASELINE_COMMIT or forge["revision_policy"] != REVISION_POLICY:
            v1._fail(
                "manifest.forge",
                "must bind the reviewed Issue #84 repair baseline",
            )
        candidate_protocol.parent_protocol._validate_hash_map(
            forge["component_sha256"],
            expected_paths=COMPONENT_PATHS,
            path="manifest.forge.component_sha256",
        )
        candidate_protocol.parent_protocol._validate_hash_map(
            manifest["protocol_artifact_sha256"],
            expected_paths=PROTOCOL_ARTIFACT_PATHS,
            path="manifest.protocol_artifact_sha256",
        )
        if manifest["authorization"] != _authorization(parent):
            v1._fail(
                "manifest.authorization",
                "must bind the Issue #86 initial-batch authorization",
            )
        if len(manifest["collection_plan"]) != 180:
            v1._fail(
                "manifest.collection_plan",
                "must retain all 180 frozen slots",
            )
        return manifest
    except BenchmarkError:
        raise
    except (
        AttributeError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise BenchmarkError("manifest: contains a malformed authorized collection v2 value") from exc


def canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return canonical_json_bytes(validate_manifest(manifest))


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()


def verify_frozen_components(
    manifest: dict[str, Any],
    repo_root: Path = REPOSITORY_ROOT,
) -> None:
    validate_manifest(manifest)
    parent_path = repo_root / manifest["authorization"]["parent_manifest"]["path"]
    parent = _parent_manifest(load_json_document(parent_path))
    if candidate_protocol.manifest_sha256(parent) != (manifest["authorization"]["parent_manifest"]["canonical_sha256"]):
        v1._fail(
            "manifest.authorization.parent_manifest",
            "does not match the reviewed v2 candidate",
        )
    for path_prefix, hashes in (
        (
            "manifest.forge.component_sha256",
            manifest["forge"]["component_sha256"],
        ),
        (
            "manifest.protocol_artifact_sha256",
            manifest["protocol_artifact_sha256"],
        ),
        ("manifest.prompt_sha256", manifest["prompt_sha256"]),
    ):
        for relative_path, expected in hashes.items():
            actual = candidate_protocol.parent_protocol._file_sha256(repo_root / relative_path)
            if actual != expected:
                v1._fail(
                    f"{path_prefix}.{relative_path}",
                    "does not match the current repository file",
                )


def schema_document() -> dict[str, Any]:
    schema = copy.deepcopy(candidate_protocol.schema_document())
    schema["$id"] = "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-cpp-formal-collection-v2-authorized.schema.json"
    schema["title"] = "Forge C/C++ authorized formal collection v2"
    properties = schema["properties"]
    properties["schema_version"] = {"const": SCHEMA_VERSION}
    properties["scope"]["properties"] = {
        "collection_authorized": {"const": True},
        "formal_comparison_enabled": {"const": True},
    }
    properties["forge"]["properties"]["commit_sha"] = {"const": BASELINE_COMMIT}
    properties["authorization"] = {
        "type": "object",
        "required": [
            "id",
            "status",
            "authorized_by",
            "authorized_on",
            "issue_url",
            "budget_confirmation",
            "collection_constraints",
            "superseded_launch",
            "parent_manifest",
        ],
        "properties": {
            "status": {"const": "authorized_initial_batch"},
            "budget_confirmation": {
                "type": "object",
                "required": ["confirmed", "maximum_tokens"],
                "properties": {
                    "confirmed": {"const": True},
                    "maximum_tokens": {"const": 29315818},
                },
            },
            "collection_constraints": {
                "type": "object",
                "required": [
                    "initial_batch_size",
                    "authorized_slot_count",
                    "remaining_slots_require_additional_confirmation",
                ],
                "properties": {
                    "initial_batch_size": {"const": 10},
                    "authorized_slot_count": {"const": 10},
                    "remaining_slots_require_additional_confirmation": {"const": True},
                },
            },
        },
    }
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
                    "authorized_slot_count": manifest["authorization"]["collection_constraints"]["authorized_slot_count"],
                    "benchmark_id": manifest["benchmark"]["id"],
                    "cases": len(manifest["cases"]),
                    "collection_authorized": manifest["scope"]["collection_authorized"],
                    "manifest_sha256": manifest_sha256(manifest),
                    "slots": len(manifest["collection_plan"]),
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
