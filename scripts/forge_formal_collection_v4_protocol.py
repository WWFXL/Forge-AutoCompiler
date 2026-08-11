#!/usr/bin/env python3
"""Generate and validate the unapproved Forge formal-collection v4 protocol."""

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
import forge_formal_collection_v3_authorized_protocol as parent_protocol  # noqa: E402

SCHEMA_VERSION = "formal-collection-4.0.0"
BASELINE_COMMIT = "7d5ad0d294e1cc28a29f92a71264e79df1121ef2"
REVISION_POLICY = parent_protocol.REVISION_POLICY
CONTROL_PLANE_TOPOLOGY = parent_protocol.CONTROL_PLANE_TOPOLOGY
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PARENT_MANIFEST = (
    REPOSITORY_ROOT
    / "benchmarks"
    / "manifests"
    / "cpp-formal-v3-authorized-collection.json"
)
DEFAULT_MANIFEST = (
    REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-formal-v4-collection.json"
)
DEFAULT_SCHEMA = (
    REPOSITORY_ROOT
    / "benchmarks"
    / "schemas"
    / "forge-cpp-formal-collection-v4.schema.json"
)
COMPONENT_PATHS = parent_protocol.COMPONENT_PATHS
PROTOCOL_ARTIFACT_PATHS = parent_protocol.PROTOCOL_ARTIFACT_PATHS | {
    "scripts/forge_formal_collection_v4_runner.py",
    "scripts/forge_formal_collection_v4_protocol.py",
    "benchmarks/preregistrations/cpp-formal-v4-amendment.md",
    "benchmarks/schemas/forge-cpp-formal-collection-v4.schema.json",
}

V3_REPORT_PATH = "benchmarks/reports/cpp-formal-v3-initial-batch.json"
V3_REPORT_SHA256 = "1140637ae8ba519aedc9185099e27ddb652f2ee0a31ab2586705d505c312381f"
ATTEMPT_BUDGET = {
    "total_wall_clock_seconds": 1800,
    "cleanup_reserve_seconds": 120,
    "max_compiler_invocations": 2,
    "max_model_requests": 48,
    "enforcement_checkpoints": [
        "before_provider_request",
        "before_compiler_invocation",
        "before_submit_or_replay",
        "before_finalize",
        "before_cleanup",
    ],
    "new_work_forbidden_after_limit": True,
    "cleanup_mandatory_after_limit": True,
    "terminal_classification": "attempt_budget_exhausted",
}
RESOURCE_PREFLIGHT = {
    "minimum_available_memory_bytes": 2_147_483_648,
    "docker_daemon_timeout_seconds": 10,
    "maximum_docker_daemon_latency_seconds": 5,
    "required_checks": [
        "host_available_memory_at_least_minimum",
        "docker_daemon_responded",
        "docker_daemon_latency_within_limit",
    ],
    "sensitive_host_identifiers_forbidden": True,
}
ANALYSIS_PLAN = {
    "protocol_version_pooling": "forbidden",
    "v3_initial_batch_role": "separate_descriptive_protocol_stratum",
    "v4_primary_estimand": "complete_project_blocks_collected_under_v4_only",
    "incomplete_block_primary_handling": "exclude_from_paired_primary_estimate",
    "incomplete_block_secondary_handling": "retain_in_end_to_end_descriptive_denominator",
    "provider_and_case_imbalance_must_be_reported": True,
    "retry_replacement_backfill_forbidden": True,
}
AUTHORIZATION_REQUEST = {
    "id": "forge-cpp-formal-v4-collection-authorization-request",
    "status": "pending_experiment_owner_confirmation",
    "requested_on": "2026-08-11",
    "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/103",
    "collection_constraints": {
        "planned_attempts": 180,
        "collection_authorized": False,
        "provider_canary_forbidden": True,
        "physical_attempt_creation_forbidden": True,
        "model_execution_forbidden": True,
        "replacement_forbidden": True,
        "fallback_forbidden": True,
        "retry_forbidden": True,
        "backfill_forbidden": True,
        "new_collection_budget_requires_confirmation": True,
        "required_runtime_launch_checks": [
            "evidence_mount_source_matches_host_workspace",
            *RESOURCE_PREFLIGHT["required_checks"],
        ],
    },
    "v3_initial_batch": {
        "report_path": V3_REPORT_PATH,
        "report_sha256": V3_REPORT_SHA256,
        "analyzed_slots": 7,
        "authorized_slots": 10,
        "recorded_usage_units": 1_700_577,
        "recorded_budget_units": 1_633_165,
        "recorded_overage_units": 67_412,
        "oracle_passed": 4,
        "stop_reason": "recorded_token_boundary_reached",
        "slots_8_to_10_not_created": True,
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
        **copy.deepcopy(AUTHORIZATION_REQUEST),
        "parent_manifest": {
            "id": parent["benchmark"]["id"],
            "path": "benchmarks/manifests/cpp-formal-v3-authorized-collection.json",
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
    manifest["$schema"] = "../schemas/forge-cpp-formal-collection-v4.schema.json"
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["benchmark"] = {
        "id": "forge-cpp-formal-v4-collection",
        "name": "Forge C/C++ attempt-bounded formal collection v4 candidate",
        "purpose": "unapproved protocol amendment with attempt-level and host-resource gates",
        "dataset_provenance": parent["benchmark"]["dataset_provenance"],
    }
    manifest["scope"] = {
        "languages": ["C", "C++"],
        "phase": "formal_collection_v4_candidate",
        "formal_comparison_enabled": False,
        "collection_authorized": False,
        "instrumentation_blocker": False,
    }
    hasher = parent_protocol.parent_protocol.parent_protocol.candidate_protocol.parent_protocol
    manifest["forge"] = {
        **copy.deepcopy(parent["forge"]),
        "commit_sha": BASELINE_COMMIT,
        "component_sha256": hasher._hash_paths(repo_root, COMPONENT_PATHS),
    }
    manifest["protocol_artifact_sha256"] = hasher._hash_paths(
        repo_root, PROTOCOL_ARTIFACT_PATHS
    )
    manifest["attempt_budget"] = copy.deepcopy(ATTEMPT_BUDGET)
    manifest["resource_preflight"] = copy.deepcopy(RESOURCE_PREFLIGHT)
    manifest["analysis_plan"] = copy.deepcopy(ANALYSIS_PLAN)
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
            "attempt_budget",
            "resource_preflight",
            "analysis_plan",
            "authorization",
        }
        if set(manifest) != expected_root:
            v1._fail("manifest", "must contain exactly the formal collection v4 fields")
        if (
            manifest["$schema"]
            != "../schemas/forge-cpp-formal-collection-v4.schema.json"
        ):
            v1._fail(
                "manifest.$schema", "must reference the formal collection v4 schema"
            )
        if manifest["schema_version"] != SCHEMA_VERSION:
            v1._fail("manifest.schema_version", f"must be {SCHEMA_VERSION!r}")
        if manifest["document_type"] != "manifest":
            v1._fail("manifest.document_type", "must be 'manifest'")
        v1._scan_for_unsafe_values(manifest)
        parent = _parent_manifest(parent)
        expected_benchmark = {
            "id": "forge-cpp-formal-v4-collection",
            "name": "Forge C/C++ attempt-bounded formal collection v4 candidate",
            "purpose": "unapproved protocol amendment with attempt-level and host-resource gates",
            "dataset_provenance": parent["benchmark"]["dataset_provenance"],
        }
        if manifest["benchmark"] != expected_benchmark:
            v1._fail("manifest.benchmark", "must identify the v4 candidate")
        if manifest["scope"] != {
            "languages": ["C", "C++"],
            "phase": "formal_collection_v4_candidate",
            "formal_comparison_enabled": False,
            "collection_authorized": False,
            "instrumentation_blocker": False,
        }:
            v1._fail("manifest.scope", "must keep v4 model execution disabled")
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
                    f"manifest.{field}", "must remain identical to formal collection v3"
                )
        if manifest["attempt_budget"] != ATTEMPT_BUDGET:
            v1._fail(
                "manifest.attempt_budget",
                "must preserve the reviewed attempt-level limits",
            )
        if manifest["resource_preflight"] != RESOURCE_PREFLIGHT:
            v1._fail(
                "manifest.resource_preflight",
                "must preserve the reviewed host-resource gates",
            )
        if manifest["analysis_plan"] != ANALYSIS_PLAN:
            v1._fail(
                "manifest.analysis_plan",
                "must preserve the preregistered imbalance handling",
            )
        if (
            ATTEMPT_BUDGET["cleanup_reserve_seconds"]
            >= ATTEMPT_BUDGET["total_wall_clock_seconds"]
        ):
            v1._fail(
                "manifest.attempt_budget.cleanup_reserve_seconds",
                "must be smaller than the total wall clock",
            )
        forge = v1._as_object(manifest["forge"], "manifest.forge")
        if set(forge) != set(parent["forge"]):
            v1._fail(
                "manifest.forge",
                "must contain exactly the inherited Forge identity fields",
            )
        if forge["repository_url"] != parent["forge"]["repository_url"]:
            v1._fail("manifest.forge.repository_url", "must preserve the repository")
        if (
            forge["commit_sha"] != BASELINE_COMMIT
            or forge["revision_policy"] != REVISION_POLICY
        ):
            v1._fail("manifest.forge", "must bind the Issue #101 snapshot baseline")
        hasher = parent_protocol.parent_protocol.parent_protocol.candidate_protocol.parent_protocol
        hasher._validate_hash_map(
            forge["component_sha256"],
            expected_paths=COMPONENT_PATHS,
            path="manifest.forge.component_sha256",
        )
        hasher._validate_hash_map(
            manifest["protocol_artifact_sha256"],
            expected_paths=PROTOCOL_ARTIFACT_PATHS,
            path="manifest.protocol_artifact_sha256",
        )
        if manifest["authorization"] != _authorization(parent):
            v1._fail(
                "manifest.authorization",
                "must bind the pending Issue #103 authorization",
            )
        if len(manifest["collection_plan"]) != 180:
            v1._fail("manifest.collection_plan", "must retain all 180 frozen slots")
        return manifest
    except BenchmarkError:
        raise
    except (AttributeError, KeyError, OverflowError, TypeError, ValueError) as exc:
        raise BenchmarkError(
            "manifest: contains a malformed formal collection v4 value"
        ) from exc


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
    if (
        parent_protocol.manifest_sha256(parent)
        != manifest["authorization"]["parent_manifest"]["canonical_sha256"]
    ):
        v1._fail(
            "manifest.authorization.parent_manifest",
            "does not match formal collection v3",
        )
    report_path = (
        repo_root / manifest["authorization"]["v3_initial_batch"]["report_path"]
    )
    if hashlib.sha256(report_path.read_bytes()).hexdigest() != V3_REPORT_SHA256:
        v1._fail(
            "manifest.authorization.v3_initial_batch.report_sha256",
            "does not match the audited v3 report",
        )
    hasher = parent_protocol.parent_protocol.parent_protocol.candidate_protocol.parent_protocol
    for path_prefix, hashes in (
        ("manifest.forge.component_sha256", manifest["forge"]["component_sha256"]),
        ("manifest.protocol_artifact_sha256", manifest["protocol_artifact_sha256"]),
        ("manifest.prompt_sha256", manifest["prompt_sha256"]),
    ):
        for relative_path, expected in hashes.items():
            actual = hasher._file_sha256(repo_root / relative_path)
            if actual != expected:
                v1._fail(
                    f"{path_prefix}.{relative_path}",
                    "does not match the current repository file",
                )


def schema_document() -> dict[str, Any]:
    schema = copy.deepcopy(parent_protocol.schema_document())
    parent = _parent_manifest()
    schema["$id"] = (
        "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-cpp-formal-collection-v4.schema.json"
    )
    schema["title"] = "Forge C/C++ unapproved formal collection v4"
    schema["additionalProperties"] = False
    schema["required"] = [
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
        "attempt_budget",
        "resource_preflight",
        "analysis_plan",
        "authorization",
    ]
    properties = schema["properties"]
    properties["$schema"] = {
        "const": "../schemas/forge-cpp-formal-collection-v4.schema.json"
    }
    properties["schema_version"] = {"const": SCHEMA_VERSION}
    properties["manifest_canonicalization"] = {
        "const": parent["manifest_canonicalization"]
    }
    properties["benchmark"] = {
        "const": {
            "id": "forge-cpp-formal-v4-collection",
            "name": "Forge C/C++ attempt-bounded formal collection v4 candidate",
            "purpose": "unapproved protocol amendment with attempt-level and host-resource gates",
            "dataset_provenance": parent["benchmark"]["dataset_provenance"],
        }
    }
    properties["scope"]["properties"] = {
        "collection_authorized": {"const": False},
        "formal_comparison_enabled": {"const": False},
    }
    properties["forge"]["properties"]["commit_sha"] = {"const": BASELINE_COMMIT}
    properties["model_profiles"] = {"const": parent["model_profiles"]}
    properties["attempt_budget"] = {"const": copy.deepcopy(ATTEMPT_BUDGET)}
    properties["resource_preflight"] = {"const": copy.deepcopy(RESOURCE_PREFLIGHT)}
    properties["analysis_plan"] = {"const": copy.deepcopy(ANALYSIS_PLAN)}
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
                    "benchmark_id": manifest["benchmark"]["id"],
                    "collection_authorized": manifest["scope"]["collection_authorized"],
                    "manifest_sha256": manifest_sha256(manifest),
                    "maximum_compiler_invocations": manifest["attempt_budget"][
                        "max_compiler_invocations"
                    ],
                    "maximum_model_requests": manifest["attempt_budget"][
                        "max_model_requests"
                    ],
                    "physical_attempt_wall_clock_seconds": manifest["attempt_budget"][
                        "total_wall_clock_seconds"
                    ],
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
