#!/usr/bin/env python3
"""生成并校验 formal v4 有限诊断与新 canary 修正协议。"""

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
import forge_formal_collection_v4_authorized_protocol as parent_protocol  # noqa: E402
import forge_formal_runtime_protocol as _hasher  # noqa: E402

SCHEMA_VERSION = "formal-collection-4.4.0-canary-amendment"
BASELINE_COMMIT = "efc640fedbc4da2e00d553fd37adaa693e8abaa2"
REVISION_POLICY = parent_protocol.REVISION_POLICY
CONTROL_PLANE_TOPOLOGY = parent_protocol.CONTROL_PLANE_TOPOLOGY
DOCKER_DAEMON_PROVIDER = parent_protocol.DOCKER_DAEMON_PROVIDER
DOCKER_SOCKET_PATH = parent_protocol.DOCKER_SOCKET_PATH
DEFAULT_PARENT_MANIFEST = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-formal-v4-authorized-initial-block.json"
DEFAULT_MANIFEST = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-formal-v4-canary-amendment.json"
DEFAULT_SCHEMA = REPOSITORY_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-collection-v4-canary-amendment.schema.json"
COMPONENT_PATHS = parent_protocol.COMPONENT_PATHS
PROTOCOL_ARTIFACT_PATHS = parent_protocol.PROTOCOL_ARTIFACT_PATHS | {
    "scripts/forge_formal_collection_v4_canary_amendment_protocol.py",
    "scripts/forge_formal_collection_v4_canary_amendment_runner.py",
    "scripts/forge_formal_collection_v4_canary_amendment_report.py",
    "benchmarks/preregistrations/cpp-formal-v4-canary-amendment.md",
    "benchmarks/schemas/forge-cpp-formal-collection-v4-canary-amendment.schema.json",
}

AUTHORIZED_EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-formal-v4-canary-amendment"
DIAGNOSTIC_DIRECTORY = "/workspace/.compile-sessions/benchmark-diagnostics-formal-v4-canary-amendment"
LEGACY_EVIDENCE_DIRECTORY = parent_protocol.AUTHORIZED_EVIDENCE_DIRECTORY
AUTHORIZED_SCHEDULE_ORDERS = copy.deepcopy(parent_protocol.AUTHORIZED_SCHEDULE_ORDERS)
BATCH_TOKEN_LIMIT = parent_protocol.BATCH_TOKEN_LIMIT
LEGACY_MANIFEST_CANONICAL_SHA256 = "8f05820d97054d16cc0cf1ee5646089ccf8f5c9c56108f2781ec45a70c7ccf03"
LEGACY_CANARY_MARKER_SHA256 = "9ab297d091967c15fae4f90caf18657b25214903b849fa3a695cd749fc19f724"
DIAGNOSTIC_PROVIDER_ORDER = ["richlab-gpt-5.5", "deepseek-v4-flash"]
DIAGNOSTIC_PROVIDERS = [
    {
        "condition_id": "richlab-gpt-5.5",
        "provider": "richlab",
        "model": "gpt-5.5",
    },
    {
        "condition_id": "deepseek-v4-flash",
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
    },
]

AMENDMENT = {
    "id": "forge-cpp-formal-v4-canary-amendment",
    "status": "authorized_limited_diagnostics_and_single_canary",
    "authorized_by": "experiment_owner",
    "authorized_on": "2026-08-13",
    "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/115",
    "implementation_baseline_commit": BASELINE_COMMIT,
    "network_observation": {
        "access_medium": "mobile_hotspot",
        "browser_ui_required": False,
    },
    "budget_confirmation": copy.deepcopy(parent_protocol.AUTHORIZATION["budget_confirmation"]),
    "collection_constraints": {
        **copy.deepcopy(parent_protocol.AUTHORIZATION["collection_constraints"]),
        "evidence_directory": AUTHORIZED_EVIDENCE_DIRECTORY,
        "endpoint_readiness_source": "bounded_authenticated_diagnostics_then_single_provider_canary",
    },
    "diagnostics": {
        "directory": DIAGNOSTIC_DIRECTORY,
        "provider_order": DIAGNOSTIC_PROVIDER_ORDER,
        "providers": DIAGNOSTIC_PROVIDERS,
        "maximum_attempts_per_provider": 2,
        "request_timeout_seconds": 120,
        "max_output_tokens": 32,
        "prompt": "Reply with exactly DIAGNOSTIC_OK and nothing else.",
        "success_criterion": "request_completed_and_response_nonempty",
        "stop_after_first_success_per_provider": True,
        "all_providers_must_pass_before_canary": True,
        "stop_conditions": [
            "first_success_for_current_provider",
            "two_attempts_consumed_for_current_provider",
            "all_providers_terminal",
            "user_interrupted",
        ],
        "interruption_policy": "started_attempt_remains_consumed_and_only_unconsumed_attempts_may_run",
        "formal_evidence_separation_required": True,
        "response_body_storage_forbidden": True,
        "request_headers_storage_forbidden": True,
        "credential_material_storage_forbidden": True,
        "network_identifier_storage_forbidden": True,
    },
    "superseded_canary_terminal": {
        "evidence_directory": LEGACY_EVIDENCE_DIRECTORY,
        "marker_relative_path": "provider-canaries/formal-v4-provider-canary-attempt.json",
        "marker_sha256": LEGACY_CANARY_MARKER_SHA256,
        "benchmark_id": "forge-cpp-formal-v4-authorized-initial-block",
        "manifest_sha256": LEGACY_MANIFEST_CANONICAL_SHA256,
        "status": "failed",
        "error_class": "RunnerError",
        "provider_report_count": 0,
        "formal_ledger_count": 0,
        "immutable": True,
    },
    "new_canary": {
        "maximum_attempts": 1,
        "attempt_marker": "formal-v4-canary-amendment-provider-canary-attempt.json",
        "anonymous_models_endpoint_preflight": "forbidden",
        "successful_diagnostics_required": True,
        "success_required_before_formal_ledger": True,
    },
}

BenchmarkError = v1.BenchmarkError
load_json_document = v1.load_json_document
canonical_json_bytes = parent_protocol.canonical_json_bytes


def _parent_manifest(document: dict[str, Any] | None = None) -> dict[str, Any]:
    parent = document or load_json_document(DEFAULT_PARENT_MANIFEST)
    validated = parent_protocol.validate_manifest(parent)
    if parent_protocol.manifest_sha256(validated) != LEGACY_MANIFEST_CANONICAL_SHA256:
        v1._fail("manifest.amendment.parent_manifest", "does not match the consumed authorized v4 identity")
    return validated


def _amendment(parent: dict[str, Any]) -> dict[str, Any]:
    return {
        **copy.deepcopy(AMENDMENT),
        "parent_manifest": {
            "id": parent["benchmark"]["id"],
            "path": "benchmarks/manifests/cpp-formal-v4-authorized-initial-block.json",
            "canonical_sha256": parent_protocol.manifest_sha256(parent),
        },
    }


def _build_manifest(repo_root: Path, *, parent: dict[str, Any]) -> dict[str, Any]:
    manifest = copy.deepcopy(parent)
    manifest["$schema"] = "../schemas/forge-cpp-formal-collection-v4-canary-amendment.schema.json"
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["benchmark"] = {
        "id": "forge-cpp-formal-v4-canary-amendment",
        "name": "Forge C/C++ formal v4 bounded diagnostics and canary amendment",
        "purpose": "preserve the consumed canary while authorizing bounded endpoint diagnosis and one new canary",
        "dataset_provenance": parent["benchmark"]["dataset_provenance"],
    }
    manifest["scope"] = {
        "languages": ["C", "C++"],
        "phase": "formal_collection_v4_canary_amendment",
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
    manifest["authorization"] = _amendment(parent)
    return manifest


def generate_manifest(
    repo_root: Path = REPOSITORY_ROOT,
    *,
    parent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _build_manifest(repo_root, parent=_parent_manifest(parent))


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
            v1._fail("manifest", "must match the formal v4 canary amendment exactly")
        selected = parent_protocol._selected_slots(manifest)
        if [slot["order"] for slot in selected] != AUTHORIZED_SCHEDULE_ORDERS:
            v1._fail("manifest.authorization", "must preserve the original six-slot schedule")
        if [provider["condition_id"] for provider in manifest["authorization"]["diagnostics"]["providers"]] != DIAGNOSTIC_PROVIDER_ORDER:
            v1._fail("manifest.authorization.diagnostics", "must preserve the reviewed provider order")
        return manifest
    except BenchmarkError:
        raise
    except (AttributeError, KeyError, OSError, TypeError, ValueError) as exc:
        raise BenchmarkError(f"manifest: invalid formal v4 canary amendment: {exc}") from exc


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
        v1._fail("manifest.authorization.parent_manifest", "does not match the consumed authorized v4 manifest")
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
    schema["$id"] = "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-cpp-formal-collection-v4-canary-amendment.schema.json"
    schema["title"] = "Forge C/C++ formal v4 bounded diagnostics and canary amendment"
    properties = schema["properties"]
    properties["$schema"] = {"const": "../schemas/forge-cpp-formal-collection-v4-canary-amendment.schema.json"}
    properties["schema_version"] = {"const": SCHEMA_VERSION}
    properties["benchmark"] = {
        "const": {
            "id": "forge-cpp-formal-v4-canary-amendment",
            "name": "Forge C/C++ formal v4 bounded diagnostics and canary amendment",
            "purpose": "preserve the consumed canary while authorizing bounded endpoint diagnosis and one new canary",
            "dataset_provenance": parent["benchmark"]["dataset_provenance"],
        }
    }
    properties["scope"] = {
        "const": {
            "languages": ["C", "C++"],
            "phase": "formal_collection_v4_canary_amendment",
            "formal_comparison_enabled": True,
            "collection_authorized": True,
            "instrumentation_blocker": False,
        }
    }
    properties["forge"]["properties"]["commit_sha"] = {"const": BASELINE_COMMIT}
    properties["forge"]["properties"]["component_sha256"] = _hash_map_schema(COMPONENT_PATHS)
    properties["protocol_artifact_sha256"] = _hash_map_schema(PROTOCOL_ARTIFACT_PATHS)
    properties["prompt_sha256"] = _hash_map_schema(set(parent["prompt_sha256"]))
    properties["authorization"] = {"const": _amendment(parent)}
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
                    "diagnostic_max_attempts_per_provider": 2,
                    "manifest_sha256": manifest_sha256(manifest),
                    "maximum_recorded_tokens": BATCH_TOKEN_LIMIT,
                    "new_canary_max_attempts": 1,
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
