#!/usr/bin/env python3
"""Generate and validate the unapproved Forge formal-collection v2 candidate."""

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
import forge_formal_collection_protocol as previous_protocol  # noqa: E402
import forge_formal_runtime_protocol as parent_protocol  # noqa: E402

SCHEMA_VERSION = "formal-collection-2.0.0"
BASELINE_COMMIT = "4afd63a1d9c909fabee2f9055bf940a76ef40350"
REVISION_POLICY = parent_protocol.REVISION_POLICY
CONTROL_PLANE_TOPOLOGY = parent_protocol.CONTROL_PLANE_TOPOLOGY
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PARENT_MANIFEST = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-formal-v1-collection.json"
DEFAULT_MANIFEST = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-formal-v2-collection.json"
DEFAULT_SCHEMA = REPOSITORY_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-collection-v2.schema.json"
COMPONENT_PATHS = parent_protocol.COMPONENT_PATHS | {
    "backend/packages/harness/deerflow/agents/middlewares/memory_middleware.py",
}
PROTOCOL_ARTIFACT_PATHS = parent_protocol.PROTOCOL_ARTIFACT_PATHS | {
    "scripts/forge_formal_collection_v2_runner.py",
    "scripts/forge_formal_collection_v2_protocol.py",
    "benchmarks/schemas/forge-cpp-formal-collection-v2.schema.json",
}

SUPERSEDED_LEDGER_SHA256 = {
    "slot-000": "4ce139f362e1aefc3b7ee43872388d672c1ada68f2e88110567626248328fad5",
    "slot-001": "a136fe850d159098626372bb0a0c3d0872dcabc23200ad4a81951011794fff8f",
    "slot-002": "a638853d0ecc660c1d62a222e3f01814df615f8a8224ea49b7f654b0b38359ba",
    "slot-003": "3ff0e4a6ccc2e183076ff3f1bf4e5723120b38686f8997b92c68c90c83facdfa",
    "slot-004": "91870eb024ba3f7ddf002f58340844e62c4dd68e57858439438c6db5f4279d65",
    "slot-005": "59c036109ce390cdd5bcd9bf974c7b1f7c4fe0a8fee10ce124c5d54ed963c300",
    "slot-006": "637ecd31cbcb47f8f48a21354c1df457aa95d64a328cd660486e084495b29593",
    "slot-007": "c91365fc485e5ec212395ec1a9cfe3c99c93be3c71c57d6a874e5d5dc11a85d9",
    "slot-008": "efc4c76a471e9910d26992cd6955ea26c07bd317b3d47e7c8d898d1cb63567cd",
    "slot-009": "4597ac932cb2b81a6597ebb7129d9799c3a698b4da571584848f07a6576c5426",
}
AUTHORIZATION_REQUEST = {
    "id": "forge-cpp-formal-v2-collection-authorization-request",
    "status": "pending_experiment_owner_confirmation",
    "requested_on": "2026-07-30",
    "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/84",
    "budget_request": {
        "confirmed": False,
        "maximum_tokens": 29396970,
        "maximum_serial_hours": 31.301,
        "tokens_observed_in_superseded_launch": 81152,
        "remaining_tokens_ceiling": 29315818,
    },
    "collection_constraints": {
        "planned_attempts": 180,
        "initial_batch_size": 10,
        "provider_canary_required_before_first_ledger": True,
        "replacement_forbidden": True,
        "fallback_forbidden": True,
        "backfill_forbidden": True,
        "superseded_launch_is_not_part_of_v2_analysis": True,
    },
    "superseded_launch": {
        "benchmark_id": "forge-cpp-formal-v1-collection",
        "status": "excluded_infrastructure_launch",
        "canary_sha256": ("5b3a71bb3c56acc8f6071da19e3535980abd0adec296f11e49bc1061274c3cb0"),
        "ledger_sha256": SUPERSEDED_LEDGER_SHA256,
        "attempts": 10,
        "connection_error_attempts": 6,
        "build_system_mismatch_attempts": 4,
        "recorded_tokens": 81152,
    },
}

BenchmarkError = v1.BenchmarkError
load_json_document = v1.load_json_document
canonical_json_bytes = parent_protocol.canonical_json_bytes
canonical_sha256 = parent_protocol.canonical_sha256


def _parent_manifest(document: dict[str, Any] | None = None) -> dict[str, Any]:
    parent = document or load_json_document(DEFAULT_PARENT_MANIFEST)
    return previous_protocol.validate_manifest(parent)


def _authorization_request(parent: dict[str, Any]) -> dict[str, Any]:
    return {
        **copy.deepcopy(AUTHORIZATION_REQUEST),
        "parent_manifest": {
            "id": parent["benchmark"]["id"],
            "path": "benchmarks/manifests/cpp-formal-v1-collection.json",
            "canonical_sha256": previous_protocol.manifest_sha256(parent),
        },
    }


def generate_manifest(
    repo_root: Path = REPOSITORY_ROOT,
    *,
    parent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parent = _parent_manifest(parent)
    manifest = copy.deepcopy(parent)
    manifest["$schema"] = "../schemas/forge-cpp-formal-collection-v2.schema.json"
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["benchmark"] = {
        "id": "forge-cpp-formal-v2-collection",
        "name": "Forge C/C++ repaired formal collection candidate",
        "purpose": "unapproved candidate; model execution remains disabled",
        "dataset_provenance": parent["benchmark"]["dataset_provenance"],
    }
    manifest["scope"] = {
        "languages": ["C", "C++"],
        "phase": "formal_collection_v2_candidate",
        "formal_comparison_enabled": False,
        "collection_authorized": False,
        "instrumentation_blocker": False,
    }
    manifest["forge"] = {
        **copy.deepcopy(parent["forge"]),
        "commit_sha": BASELINE_COMMIT,
        "component_sha256": parent_protocol._hash_paths(
            repo_root,
            COMPONENT_PATHS,
        ),
    }
    manifest["protocol_artifact_sha256"] = parent_protocol._hash_paths(
        repo_root,
        PROTOCOL_ARTIFACT_PATHS,
    )
    manifest["authorization"] = _authorization_request(parent)
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
                "must contain exactly the formal collection v2 candidate fields",
            )
        if manifest["$schema"] != "../schemas/forge-cpp-formal-collection-v2.schema.json":
            v1._fail("manifest.$schema", "must reference the v2 candidate schema")
        if manifest["schema_version"] != SCHEMA_VERSION:
            v1._fail("manifest.schema_version", f"must be {SCHEMA_VERSION!r}")
        if manifest["document_type"] != "manifest":
            v1._fail("manifest.document_type", "must be 'manifest'")
        v1._scan_for_unsafe_values(manifest)
        parent = _parent_manifest(parent)
        if manifest["benchmark"] != {
            "id": "forge-cpp-formal-v2-collection",
            "name": "Forge C/C++ repaired formal collection candidate",
            "purpose": "unapproved candidate; model execution remains disabled",
            "dataset_provenance": parent["benchmark"]["dataset_provenance"],
        }:
            v1._fail("manifest.benchmark", "must identify the v2 candidate")
        if manifest["scope"] != {
            "languages": ["C", "C++"],
            "phase": "formal_collection_v2_candidate",
            "formal_comparison_enabled": False,
            "collection_authorized": False,
            "instrumentation_blocker": False,
        }:
            v1._fail(
                "manifest.scope",
                "must keep v2 model execution disabled pending owner confirmation",
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
                    "must remain identical to the reviewed v1 collection",
                )
        forge = v1._as_object(manifest["forge"], "manifest.forge")
        if set(forge) != set(parent["forge"]):
            v1._fail(
                "manifest.forge",
                "must contain exactly the inherited Forge identity fields",
            )
        if forge["repository_url"] != parent["forge"]["repository_url"]:
            v1._fail("manifest.forge.repository_url", "must preserve the repository")
        if forge["commit_sha"] != BASELINE_COMMIT or forge["revision_policy"] != REVISION_POLICY:
            v1._fail("manifest.forge", "must bind the Issue #84 repair baseline")
        parent_protocol._validate_hash_map(
            forge["component_sha256"],
            expected_paths=COMPONENT_PATHS,
            path="manifest.forge.component_sha256",
        )
        parent_protocol._validate_hash_map(
            manifest["protocol_artifact_sha256"],
            expected_paths=PROTOCOL_ARTIFACT_PATHS,
            path="manifest.protocol_artifact_sha256",
        )
        if manifest["authorization"] != _authorization_request(parent):
            v1._fail(
                "manifest.authorization",
                "must retain the unapproved Issue #84 request and launch audit",
            )
        if len(manifest["collection_plan"]) != 180:
            v1._fail("manifest.collection_plan", "must retain all 180 frozen slots")
        return manifest
    except BenchmarkError:
        raise
    except (AttributeError, KeyError, OverflowError, TypeError, ValueError) as exc:
        raise BenchmarkError("manifest: contains a malformed formal collection v2 candidate value") from exc


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
    if previous_protocol.manifest_sha256(parent) != manifest["authorization"]["parent_manifest"]["canonical_sha256"]:
        v1._fail(
            "manifest.authorization.parent_manifest",
            "does not match the reviewed v1 collection",
        )
    for path_prefix, hashes in (
        ("manifest.forge.component_sha256", manifest["forge"]["component_sha256"]),
        (
            "manifest.protocol_artifact_sha256",
            manifest["protocol_artifact_sha256"],
        ),
        ("manifest.prompt_sha256", manifest["prompt_sha256"]),
    ):
        for relative_path, expected in hashes.items():
            actual = parent_protocol._file_sha256(repo_root / relative_path)
            if actual != expected:
                v1._fail(
                    f"{path_prefix}.{relative_path}",
                    "does not match the current repository file",
                )


def schema_document() -> dict[str, Any]:
    hash_map = {
        "type": "object",
        "minProperties": 1,
        "additionalProperties": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": ("https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-cpp-formal-collection-v2.schema.json"),
        "title": "Forge C/C++ formal collection v2 candidate",
        "type": "object",
        "required": [
            "$schema",
            "schema_version",
            "document_type",
            "scope",
            "source_protocols",
            "forge",
            "protocol_artifact_sha256",
            "prompt_sha256",
            "runtime",
            "budget",
            "conditions",
            "collection_plan",
            "schedule_sha256",
            "cases",
            "authorization",
        ],
        "properties": {
            "schema_version": {"const": SCHEMA_VERSION},
            "document_type": {"const": "manifest"},
            "scope": {
                "type": "object",
                "required": [
                    "collection_authorized",
                    "formal_comparison_enabled",
                ],
                "properties": {
                    "collection_authorized": {"const": False},
                    "formal_comparison_enabled": {"const": False},
                },
            },
            "source_protocols": {"type": "object"},
            "forge": {
                "type": "object",
                "required": ["commit_sha", "component_sha256"],
                "properties": {
                    "commit_sha": {"const": BASELINE_COMMIT},
                    "component_sha256": hash_map,
                },
            },
            "protocol_artifact_sha256": hash_map,
            "prompt_sha256": hash_map,
            "runtime": {
                "type": "object",
                "required": [
                    "image_id",
                    "control_plane_topology",
                    "max_parallel_runs",
                ],
                "properties": {
                    "image_id": {"pattern": "^sha256:[0-9a-f]{64}$"},
                    "control_plane_topology": {"const": CONTROL_PLANE_TOPOLOGY},
                    "max_parallel_runs": {"const": 1},
                },
            },
            "budget": {"type": "object"},
            "conditions": {"type": "array", "minItems": 2, "maxItems": 2},
            "collection_plan": {
                "type": "array",
                "minItems": 180,
                "maxItems": 180,
            },
            "schedule_sha256": {
                "type": "string",
                "pattern": "^[0-9a-f]{64}$",
            },
            "cases": {"type": "array", "minItems": 30, "maxItems": 30},
            "authorization": {
                "type": "object",
                "required": [
                    "id",
                    "status",
                    "requested_on",
                    "issue_url",
                    "budget_request",
                    "collection_constraints",
                    "superseded_launch",
                    "parent_manifest",
                ],
                "properties": {
                    "status": {"const": "pending_experiment_owner_confirmation"},
                    "budget_request": {
                        "type": "object",
                        "required": ["confirmed"],
                        "properties": {"confirmed": {"const": False}},
                    },
                },
            },
        },
        "additionalProperties": True,
    }


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
