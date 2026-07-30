#!/usr/bin/env python3
"""Generate and validate the unapproved Forge formal-collection v3 protocol."""

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
import forge_formal_collection_v2_authorized_protocol as parent_protocol  # noqa: E402

SCHEMA_VERSION = "formal-collection-3.0.0"
BASELINE_COMMIT = "4578739983f5d23cb3e21ff619b1e33aba702859"
REVISION_POLICY = parent_protocol.REVISION_POLICY
CONTROL_PLANE_TOPOLOGY = parent_protocol.CONTROL_PLANE_TOPOLOGY
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PARENT_MANIFEST = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-formal-v2-authorized-collection.json"
DEFAULT_MANIFEST = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-formal-v3-collection.json"
DEFAULT_SCHEMA = REPOSITORY_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-collection-v3.schema.json"
COMPONENT_PATHS = parent_protocol.COMPONENT_PATHS
PROTOCOL_ARTIFACT_PATHS = parent_protocol.PROTOCOL_ARTIFACT_PATHS | {
    "scripts/forge_formal_collection_v3_runner.py",
    "scripts/forge_formal_collection_v3_protocol.py",
    "benchmarks/schemas/forge-cpp-formal-collection-v3.schema.json",
}

EXCLUDED_V2_LEDGER_SHA256 = {
    "slot-000": "7eba5023cf7f695f30cd81c491131e50a9955ce444982a737bdacbe91ef2340d",
    "slot-001": "e31cc7c73ed16df812b3b45a1388fab9acde7ca6efb0c46d2185f8a8f15d91db",
    "slot-002": "96bef8012ebebe8cdd29ed2488cd56c73a1bb52a0b90c2f87f9401b78d37f241",
    "slot-003": "64dc624bf30ea90ffba5248ebadca9a1b79028f8213358364410c0116027ddd4",
    "slot-004": "ec988f7e97276fe6851bc5989baf1df0739eb5213507f0535567468d6f01e0dd",
    "slot-005": "f1004b4a56e9575e243614a08e1b4c01c82bed5b2734fe496483ece9279c3164",
    "slot-006": "644adf29081250e59d76a43fc75ca6b8ac22f11f96579f91e2f867e962e39ec9",
    "slot-007": "f92512b1d2d714bace641fee748e32ce26e0d16ba61b4e89c33738edc54e7ee9",
    "slot-008": "6191d9cf555d17f07e10771013fd1eeef54bda171f343584f2ffcf604ab9a32c",
    "slot-009": "227b332f9d2f4119e2f96d4edbc4f9fb30b1521471faf6e99f518465305af35c",
}
AUTHORIZATION_REQUEST = {
    "id": "forge-cpp-formal-v3-collection-authorization-request",
    "status": "pending_experiment_owner_confirmation",
    "requested_on": "2026-07-30",
    "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/90",
    "budget_request": {
        "confirmed": False,
        "maximum_tokens": 29315818,
        "tokens_observed_in_excluded_v2": 143286,
        "remaining_tokens_ceiling": 29172532,
    },
    "collection_constraints": {
        "planned_attempts": 180,
        "initial_batch_size": 10,
        "provider_canary_required_before_first_ledger": True,
        "replacement_forbidden": True,
        "fallback_forbidden": True,
        "backfill_forbidden": True,
        "excluded_v2_launch_is_not_part_of_v3_analysis": True,
        "required_runtime_launch_checks": ["evidence_mount_source_matches_host_workspace"],
    },
    "excluded_v2_launch": {
        "benchmark_id": "forge-cpp-formal-v2-authorized-collection",
        "status": "excluded_infrastructure_launch",
        "exclusion_reason": "build_system_mismatch_from_evidence_bind_source_split",
        "canary_sha256": ("8ba42a5ed465f78196405b4673620bdeeb1af4d9f890c52eb645e2e5a3d4b16e"),
        "ledger_sha256": EXCLUDED_V2_LEDGER_SHA256,
        "attempts": 10,
        "model_requests_started": 32,
        "model_requests_completed": 32,
        "recorded_tokens": 143286,
        "ledger_elapsed_seconds": 697.972,
        "oracle_passes": 0,
        "build_system_mismatch_attempts": 10,
        "residual_containers": 0,
    },
}

BenchmarkError = v1.BenchmarkError
load_json_document = v1.load_json_document
canonical_json_bytes = parent_protocol.canonical_json_bytes


def _parent_manifest(document: dict[str, Any] | None = None) -> dict[str, Any]:
    parent = document or load_json_document(DEFAULT_PARENT_MANIFEST)
    return parent_protocol.validate_manifest(parent)


def _authorization_request(parent: dict[str, Any]) -> dict[str, Any]:
    return {
        **copy.deepcopy(AUTHORIZATION_REQUEST),
        "parent_manifest": {
            "id": parent["benchmark"]["id"],
            "path": ("benchmarks/manifests/cpp-formal-v2-authorized-collection.json"),
            "canonical_sha256": parent_protocol.manifest_sha256(parent),
        },
    }


def generate_manifest(
    repo_root: Path = REPOSITORY_ROOT,
    *,
    parent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parent = _parent_manifest(parent)
    manifest = copy.deepcopy(parent)
    manifest["$schema"] = "../schemas/forge-cpp-formal-collection-v3.schema.json"
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["benchmark"] = {
        "id": "forge-cpp-formal-v3-collection",
        "name": "Forge C/C++ repaired formal collection v3 candidate",
        "purpose": ("unapproved post-DooD-path-repair candidate; model execution remains disabled"),
        "dataset_provenance": parent["benchmark"]["dataset_provenance"],
    }
    manifest["scope"] = {
        "languages": ["C", "C++"],
        "phase": "formal_collection_v3_candidate",
        "formal_comparison_enabled": False,
        "collection_authorized": False,
        "instrumentation_blocker": False,
    }
    manifest["forge"] = {
        **copy.deepcopy(parent["forge"]),
        "commit_sha": BASELINE_COMMIT,
        "component_sha256": parent_protocol.candidate_protocol.parent_protocol._hash_paths(
            repo_root,
            COMPONENT_PATHS,
        ),
    }
    manifest["protocol_artifact_sha256"] = parent_protocol.candidate_protocol.parent_protocol._hash_paths(
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
                "must contain exactly the formal collection v3 fields",
            )
        if manifest["$schema"] != ("../schemas/forge-cpp-formal-collection-v3.schema.json"):
            v1._fail(
                "manifest.$schema",
                "must reference the formal collection v3 schema",
            )
        if manifest["schema_version"] != SCHEMA_VERSION:
            v1._fail("manifest.schema_version", f"must be {SCHEMA_VERSION!r}")
        if manifest["document_type"] != "manifest":
            v1._fail("manifest.document_type", "must be 'manifest'")
        v1._scan_for_unsafe_values(manifest)
        parent = _parent_manifest(parent)
        if manifest["benchmark"] != {
            "id": "forge-cpp-formal-v3-collection",
            "name": "Forge C/C++ repaired formal collection v3 candidate",
            "purpose": ("unapproved post-DooD-path-repair candidate; model execution remains disabled"),
            "dataset_provenance": parent["benchmark"]["dataset_provenance"],
        }:
            v1._fail("manifest.benchmark", "must identify the v3 candidate")
        if manifest["scope"] != {
            "languages": ["C", "C++"],
            "phase": "formal_collection_v3_candidate",
            "formal_comparison_enabled": False,
            "collection_authorized": False,
            "instrumentation_blocker": False,
        }:
            v1._fail(
                "manifest.scope",
                "must keep v3 model execution disabled",
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
                    "must remain identical to the authorized v2 protocol",
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
                "must bind the Issue #88 repair baseline",
            )
        parent_protocol.candidate_protocol.parent_protocol._validate_hash_map(
            forge["component_sha256"],
            expected_paths=COMPONENT_PATHS,
            path="manifest.forge.component_sha256",
        )
        parent_protocol.candidate_protocol.parent_protocol._validate_hash_map(
            manifest["protocol_artifact_sha256"],
            expected_paths=PROTOCOL_ARTIFACT_PATHS,
            path="manifest.protocol_artifact_sha256",
        )
        if manifest["authorization"] != _authorization_request(parent):
            v1._fail(
                "manifest.authorization",
                "must bind the pending Issue #90 authorization",
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
        raise BenchmarkError("manifest: contains a malformed formal collection v3 value") from exc


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
    if parent_protocol.manifest_sha256(parent) != (manifest["authorization"]["parent_manifest"]["canonical_sha256"]):
        v1._fail(
            "manifest.authorization.parent_manifest",
            "does not match the authorized v2 protocol",
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
            actual = parent_protocol.candidate_protocol.parent_protocol._file_sha256(repo_root / relative_path)
            if actual != expected:
                v1._fail(
                    f"{path_prefix}.{relative_path}",
                    "does not match the current repository file",
                )


def schema_document() -> dict[str, Any]:
    schema = copy.deepcopy(parent_protocol.schema_document())
    schema["$id"] = "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-cpp-formal-collection-v3.schema.json"
    schema["title"] = "Forge C/C++ unapproved formal collection v3"
    properties = schema["properties"]
    properties["schema_version"] = {"const": SCHEMA_VERSION}
    properties["scope"]["properties"] = {
        "collection_authorized": {"const": False},
        "formal_comparison_enabled": {"const": False},
    }
    properties["forge"]["properties"]["commit_sha"] = {"const": BASELINE_COMMIT}
    properties["authorization"] = {
        "type": "object",
        "required": [
            "id",
            "status",
            "requested_on",
            "issue_url",
            "budget_request",
            "collection_constraints",
            "excluded_v2_launch",
            "parent_manifest",
        ],
        "properties": {
            "status": {
                "const": "pending_experiment_owner_confirmation",
            },
            "budget_request": {
                "type": "object",
                "required": [
                    "confirmed",
                    "maximum_tokens",
                    "tokens_observed_in_excluded_v2",
                    "remaining_tokens_ceiling",
                ],
                "properties": {
                    "confirmed": {"const": False},
                    "maximum_tokens": {"const": 29315818},
                    "tokens_observed_in_excluded_v2": {"const": 143286},
                    "remaining_tokens_ceiling": {"const": 29172532},
                },
            },
            "excluded_v2_launch": {
                "type": "object",
                "required": [
                    "status",
                    "canary_sha256",
                    "ledger_sha256",
                    "attempts",
                    "model_requests_started",
                    "model_requests_completed",
                    "recorded_tokens",
                    "oracle_passes",
                    "build_system_mismatch_attempts",
                    "residual_containers",
                ],
                "properties": {
                    "status": {"const": "excluded_infrastructure_launch"},
                    "attempts": {"const": 10},
                    "model_requests_started": {"const": 32},
                    "model_requests_completed": {"const": 32},
                    "recorded_tokens": {"const": 143286},
                    "oracle_passes": {"const": 0},
                    "build_system_mismatch_attempts": {"const": 10},
                    "residual_containers": {"const": 0},
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
                    "benchmark_id": manifest["benchmark"]["id"],
                    "cases": len(manifest["cases"]),
                    "collection_authorized": manifest["scope"]["collection_authorized"],
                    "manifest_sha256": manifest_sha256(manifest),
                    "remaining_tokens_ceiling": manifest["authorization"]["budget_request"]["remaining_tokens_ceiling"],
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
