#!/usr/bin/env python3
"""生成并校验未授权的 formal v4 Ubuntu daemon 候选协议。"""

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
import forge_formal_collection_v4_runtime_protocol as parent_protocol  # noqa: E402
import forge_formal_runtime_protocol as _hasher  # noqa: E402

SCHEMA_VERSION = "formal-collection-4.2.0-ubuntu-candidate"
BASELINE_COMMIT = "65c2a739ba054375158cbddb27a885e8206a48aa"
REVISION_POLICY = parent_protocol.REVISION_POLICY
CONTROL_PLANE_TOPOLOGY = parent_protocol.CONTROL_PLANE_TOPOLOGY
DOCKER_DAEMON_PROVIDER = "ubuntu-native"
DOCKER_SOCKET_PATH = "/var/run/docker.sock"
DEFAULT_PARENT_MANIFEST = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-formal-v4-runtime-candidate.json"
DEFAULT_MANIFEST = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-formal-v4-ubuntu-candidate.json"
DEFAULT_SCHEMA = REPOSITORY_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-collection-v4-ubuntu-candidate.schema.json"
COMPONENT_PATHS = parent_protocol.COMPONENT_PATHS
PROTOCOL_ARTIFACT_PATHS = parent_protocol.PROTOCOL_ARTIFACT_PATHS | {
    "scripts/docker.sh",
    "scripts/require-ubuntu-native-docker.sh",
    "scripts/wsl-check.sh",
    "scripts/forge_formal_collection_v4_ubuntu_protocol.py",
    "scripts/forge_formal_collection_v4_ubuntu_runner.py",
    "benchmarks/preregistrations/cpp-formal-v4-ubuntu-gate-and-initial-block.md",
    "benchmarks/schemas/forge-cpp-formal-collection-v4-ubuntu-candidate.schema.json",
}
ATTEMPT_BUDGET = copy.deepcopy(parent_protocol.ATTEMPT_BUDGET)
RESOURCE_PREFLIGHT = {
    **copy.deepcopy(parent_protocol.RESOURCE_PREFLIGHT),
    "docker_daemon_provider": DOCKER_DAEMON_PROVIDER,
    "docker_socket_path": DOCKER_SOCKET_PATH,
}
RESOURCE_PREFLIGHT["required_checks"] = [
    *RESOURCE_PREFLIGHT["required_checks"],
    "docker_daemon_provider_matches",
    "docker_socket_source_matches_native_path",
]
ANALYSIS_PLAN = copy.deepcopy(parent_protocol.ANALYSIS_PLAN)
INITIAL_BATCH_DECISION = {
    "status": "pending_experiment_owner_confirmation",
    "selection_rule": "first_project_in_frozen_schedule",
    "project_ids": ["cppitertools"],
    "complete_project_blocks": 1,
    "conditions_per_project": 2,
    "repetitions_per_condition": 3,
    "planned_attempts": 6,
    "selected_schedule_orders": [1, 2, 73, 74, 153, 154],
    "maximum_recorded_tokens": 980_000,
    "token_budget_basis": "preregistered_full_budget_linear_share_times_1.25_rounded_up",
    "token_boundary_check": "after_attempt_terminalization_before_next_attempt",
    "maximum_attempt_wall_clock_seconds": 1_800,
    "maximum_batch_attempt_wall_clock_seconds": 10_800,
    "stop_conditions": [
        "six_selected_attempts_terminalized",
        "recorded_token_boundary_reached",
        "runtime_preflight_failed",
        "provider_canary_failed",
        "daemon_provider_drift",
        "ledger_or_cleanup_invariant_failed",
        "user_interrupted",
    ],
    "incomplete_block_handling": "descriptive_only_not_primary_paired_estimate",
    "retry_replacement_backfill_forbidden": True,
}
AUTHORIZATION = {
    "id": "forge-cpp-formal-v4-ubuntu-candidate-review",
    "status": "environment_gate_implemented_collection_pending",
    "implemented_on": "2026-08-12",
    "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/109",
    "implementation_baseline_commit": BASELINE_COMMIT,
    "collection_constraints": {
        "collection_authorized": False,
        "provider_canary_forbidden": True,
        "physical_attempt_creation_forbidden": True,
        "model_execution_forbidden": True,
        "batch_execution_forbidden": True,
        "experiment_owner_confirmation_required": True,
        "replacement_forbidden": True,
        "fallback_forbidden": True,
        "retry_forbidden": True,
        "backfill_forbidden": True,
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
            "path": "benchmarks/manifests/cpp-formal-v4-runtime-candidate.json",
            "canonical_sha256": parent_protocol.manifest_sha256(parent),
        },
    }


def _build_manifest(
    repo_root: Path,
    *,
    parent: dict[str, Any],
) -> dict[str, Any]:
    manifest = copy.deepcopy(parent)
    manifest["$schema"] = "../schemas/forge-cpp-formal-collection-v4-ubuntu-candidate.schema.json"
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["benchmark"] = {
        "id": "forge-cpp-formal-v4-ubuntu-candidate",
        "name": "Forge C/C++ formal v4 Ubuntu-daemon candidate",
        "purpose": "unapproved native-daemon gate and initial complete-block decision",
        "dataset_provenance": parent["benchmark"]["dataset_provenance"],
    }
    manifest["scope"] = {
        "languages": ["C", "C++"],
        "phase": "formal_collection_v4_ubuntu_candidate",
        "formal_comparison_enabled": False,
        "collection_authorized": False,
        "instrumentation_blocker": False,
    }
    manifest["forge"] = {
        **copy.deepcopy(parent["forge"]),
        "commit_sha": BASELINE_COMMIT,
        "component_sha256": _hasher._hash_paths(repo_root, COMPONENT_PATHS),
    }
    manifest["protocol_artifact_sha256"] = _hasher._hash_paths(
        repo_root,
        PROTOCOL_ARTIFACT_PATHS,
    )
    manifest["prompt_sha256"] = _hasher._hash_paths(
        repo_root,
        set(parent["prompt_sha256"]),
    )
    manifest["runtime"] = {
        **copy.deepcopy(parent["runtime"]),
        "docker_daemon_provider": DOCKER_DAEMON_PROVIDER,
        "docker_socket_path": DOCKER_SOCKET_PATH,
    }
    manifest["attempt_budget"] = copy.deepcopy(ATTEMPT_BUDGET)
    manifest["resource_preflight"] = copy.deepcopy(RESOURCE_PREFLIGHT)
    manifest["analysis_plan"] = copy.deepcopy(ANALYSIS_PLAN)
    manifest["initial_batch_decision"] = copy.deepcopy(INITIAL_BATCH_DECISION)
    manifest["authorization"] = _authorization(parent)
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
            v1._fail(
                "manifest",
                "must match the reviewed formal v4 Ubuntu candidate exactly",
            )
        selected = [slot for slot in manifest["collection_plan"] if slot["order"] in manifest["initial_batch_decision"]["selected_schedule_orders"]]
        if len(selected) != 6 or {slot["case_id"] for slot in selected} != {"cppitertools"}:
            v1._fail(
                "manifest.initial_batch_decision",
                "must select the complete cppitertools project block",
            )
        if {(slot["condition_id"], slot["repetition"]) for slot in selected} != {(condition["id"], repetition) for condition in manifest["conditions"] for repetition in range(1, 4)}:
            v1._fail(
                "manifest.initial_batch_decision",
                "must cover both conditions and all three repetitions",
            )
        return manifest
    except BenchmarkError:
        raise
    except (AttributeError, KeyError, OSError, TypeError, ValueError) as exc:
        raise BenchmarkError(f"manifest: invalid Ubuntu candidate: {exc}") from exc


def canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return canonical_json_bytes(manifest)


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()


def verify_frozen_components(
    manifest: dict[str, Any],
    repo_root: Path = REPOSITORY_ROOT,
) -> None:
    validate_manifest(manifest, repo_root=repo_root)
    for path_prefix, hashes in (
        ("manifest.forge.component_sha256", manifest["forge"]["component_sha256"]),
        (
            "manifest.protocol_artifact_sha256",
            manifest["protocol_artifact_sha256"],
        ),
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
        "properties": {
            relative_path: {
                "type": "string",
                "pattern": "^[0-9a-f]{64}$",
            }
            for relative_path in sorted(paths)
        },
    }


def schema_document() -> dict[str, Any]:
    schema = copy.deepcopy(parent_protocol.schema_document())
    parent = _parent_manifest()
    schema["$id"] = "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-cpp-formal-collection-v4-ubuntu-candidate.schema.json"
    schema["title"] = "Forge C/C++ unapproved formal v4 Ubuntu-daemon candidate"
    schema["required"] = [
        *schema["required"],
        "initial_batch_decision",
    ]
    properties = schema["properties"]
    properties["$schema"] = {"const": "../schemas/forge-cpp-formal-collection-v4-ubuntu-candidate.schema.json"}
    properties["schema_version"] = {"const": SCHEMA_VERSION}
    properties["benchmark"] = {
        "const": {
            "id": "forge-cpp-formal-v4-ubuntu-candidate",
            "name": "Forge C/C++ formal v4 Ubuntu-daemon candidate",
            "purpose": "unapproved native-daemon gate and initial complete-block decision",
            "dataset_provenance": parent["benchmark"]["dataset_provenance"],
        }
    }
    properties["scope"] = {
        "const": {
            "languages": ["C", "C++"],
            "phase": "formal_collection_v4_ubuntu_candidate",
            "formal_comparison_enabled": False,
            "collection_authorized": False,
            "instrumentation_blocker": False,
        }
    }
    properties["forge"]["properties"]["commit_sha"] = {"const": BASELINE_COMMIT}
    properties["forge"]["properties"]["component_sha256"] = _hash_map_schema(COMPONENT_PATHS)
    properties["protocol_artifact_sha256"] = _hash_map_schema(PROTOCOL_ARTIFACT_PATHS)
    properties["prompt_sha256"] = _hash_map_schema(set(parent["prompt_sha256"]))
    properties["runtime"]["required"] = [
        *properties["runtime"]["required"],
        "docker_daemon_provider",
        "docker_socket_path",
    ]
    properties["runtime"]["properties"]["docker_daemon_provider"] = {"const": DOCKER_DAEMON_PROVIDER}
    properties["runtime"]["properties"]["docker_socket_path"] = {"const": DOCKER_SOCKET_PATH}
    properties["attempt_budget"] = {"const": copy.deepcopy(ATTEMPT_BUDGET)}
    properties["resource_preflight"] = {"const": copy.deepcopy(RESOURCE_PREFLIGHT)}
    properties["analysis_plan"] = {"const": copy.deepcopy(ANALYSIS_PLAN)}
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
                    "benchmark_id": manifest["benchmark"]["id"],
                    "collection_authorized": manifest["scope"]["collection_authorized"],
                    "daemon_provider": manifest["runtime"]["docker_daemon_provider"],
                    "initial_batch_attempts": manifest["initial_batch_decision"]["planned_attempts"],
                    "manifest_sha256": manifest_sha256(manifest),
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
