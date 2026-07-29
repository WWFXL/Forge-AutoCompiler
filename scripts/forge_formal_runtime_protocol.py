#!/usr/bin/env python3
"""Generate and validate the pre-collection Forge C/C++ formal runtime protocol."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_benchmark as v1  # noqa: E402
import forge_benchmark_v8 as v8  # noqa: E402
import forge_formal_case_protocol as case_protocol  # noqa: E402
import forge_formal_preregistration as preregistration  # noqa: E402

SCHEMA_VERSION = "formal-1.0.0"
BASELINE_COMMIT = "09012ff6bf908094d8127bee441b99730cdcc0f4"
REVISION_POLICY = "baseline_ancestor_with_frozen_components"
CONTROL_PLANE_TOPOLOGY = "compose-dood"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-formal-v1.json"
DEFAULT_SCHEMA = REPOSITORY_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-v1.schema.json"
COMPONENT_PATHS = v8.COMPONENT_PATHS
PROMPT_PATHS = {
    "backend/packages/harness/deerflow/agents/lead_agent/prompt.py",
    "backend/packages/harness/deerflow/subagents/builtins/compiler_agent.py",
    "backend/packages/harness/deerflow/tools/builtins/task_tool.py",
}
PROTOCOL_ARTIFACT_PATHS = {
    "backend/Dockerfile",
    "scripts/forge_benchmark.py",
    "scripts/forge_benchmark_runner.py",
    "scripts/forge_formal_case_protocol.py",
    "scripts/forge_formal_preregistration.py",
    "scripts/forge_formal_runtime_protocol.py",
    "benchmarks/schemas/forge-cpp-formal-v1.schema.json",
}
SOURCE_PROTOCOL_PATHS = {
    "preregistration": "benchmarks/preregistrations/cpp-formal-v1.json",
    "case_protocol": "benchmarks/preregistrations/cpp-formal-v1-cases.json",
}
RUNTIME_BUDGETS = copy.deepcopy(v8.RUNTIME_BUDGETS)
MODEL_PROFILES = copy.deepcopy(v8.MODEL_PROFILES)

BenchmarkError = v1.BenchmarkError
load_json_document = v1.load_json_document


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise BenchmarkError("document cannot be represented as canonical JSON") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise BenchmarkError(f"frozen artifact is not an ordinary file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_paths(repo_root: Path, paths: set[str]) -> dict[str, str]:
    return {relative_path: _file_sha256(repo_root / relative_path) for relative_path in sorted(paths)}


def _source_protocols(
    prereg: dict[str, Any],
    cases: dict[str, Any],
) -> dict[str, dict[str, str]]:
    return {
        "preregistration": {
            "id": prereg["preregistration"]["id"],
            "path": SOURCE_PROTOCOL_PATHS["preregistration"],
            "sha256": preregistration.canonical_sha256(prereg),
        },
        "case_protocol": {
            "id": cases["protocolization"]["id"],
            "path": SOURCE_PROTOCOL_PATHS["case_protocol"],
            "sha256": case_protocol.canonical_sha256(cases),
        },
    }


def _runtime_case(
    selected: dict[str, Any],
    reviewed: dict[str, Any],
) -> dict[str, Any]:
    recipe = reviewed["recipe"]
    required_artifacts = [
        {
            "relative_path": artifact["staged_relative_path"],
            "build_output_path": artifact["build_output_path"],
            "artifact_type": artifact["artifact_type"],
            "producing_target": artifact["producing_target"],
        }
        for artifact in reviewed["artifact_oracle"]["required_artifacts"]
    ]
    build_system = selected["build_system"]
    return {
        "id": selected["id"],
        "repository_url": selected["repository_url"],
        "commit_sha": selected["commit"],
        "languages": [selected["language"]],
        "build_system": build_system,
        "license": selected["license_spdx"],
        "protocol": {
            "source_subdir": recipe["source_subdir"],
            "bootstrap_commands": copy.deepcopy(recipe["bootstrap_commands"]),
            "configure_arguments": copy.deepcopy(recipe["configure_arguments"]),
            "build_targets": copy.deepcopy(recipe["build_targets"]),
        },
        "oracle": {
            "expected_candidate_status": "pass",
            "expected_clean_replay_status": "pass",
            "required_artifacts": required_artifacts,
        },
        "constraints": {
            "required_system_packages": copy.deepcopy(recipe["required_system_packages"]),
            "build_arguments": {
                "cmake": (copy.deepcopy(recipe["configure_arguments"]) if build_system == "cmake" else []),
                "configure": (copy.deepcopy(recipe["configure_arguments"]) if build_system == "autotools" else []),
            },
            "environment": {},
            "minimum_replay_delay_seconds": 0,
        },
    }


def _runtime_cases(
    prereg: dict[str, Any],
    protocol: dict[str, Any],
) -> list[dict[str, Any]]:
    reviewed_by_id = {case["id"]: case for case in protocol["cases"]}
    return [_runtime_case(selected, reviewed_by_id[selected["id"]]) for selected in prereg["cases"]]


def _budget(prereg: dict[str, Any]) -> dict[str, Any]:
    projection = copy.deepcopy(prereg["resource_projection_from_v8"])
    policy = {
        "planned_attempts": projection["planned_attempts"],
        "linear_projected_tokens": projection["linear_projected_tokens"],
        "linear_projected_serial_hours": projection["linear_projected_serial_hours"],
        "planning_contingency_multiplier": projection["planning_contingency_multiplier"],
        "contingency_tokens": projection["contingency_tokens"],
        "contingency_serial_hours": projection["contingency_serial_hours"],
        "human_confirmation_required_before_collection": True,
    }
    return {"policy": policy, "budget_sha256": canonical_sha256(policy)}


def generate_manifest(
    repo_root: Path = REPOSITORY_ROOT,
    *,
    prereg: dict[str, Any] | None = None,
    case_document: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prereg = prereg or preregistration.load_preregistration()
    case_document = case_document or case_protocol.load_protocol()
    preregistration.validate_preregistration(prereg)
    case_protocol.validate_protocol(case_document, preregistration=prereg)
    schedule = preregistration.build_schedule(prereg)
    manifest = {
        "$schema": "../schemas/forge-cpp-formal-v1.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": "manifest",
        "manifest_canonicalization": "UTF-8 JSON, sorted object keys, compact separators, no NaN",
        "benchmark": {
            "id": "forge-cpp-formal-v1",
            "name": "Forge C/C++ dual-provider stratified formal experiment",
            "purpose": "pre-collection frozen runtime protocol",
            "dataset_provenance": "OSS-Fuzz metadata snapshot 08682bfc",
        },
        "scope": {
            "languages": ["C", "C++"],
            "phase": "formal_pre_collection",
            "formal_comparison_enabled": True,
            "collection_authorized": False,
            "instrumentation_blocker": False,
        },
        "source_protocols": _source_protocols(prereg, case_document),
        "forge": {
            "repository_url": "https://github.com/WWFXL/Forge-AutoCompiler",
            "commit_sha": BASELINE_COMMIT,
            "revision_policy": REVISION_POLICY,
            "component_sha256": _hash_paths(repo_root, COMPONENT_PATHS),
        },
        "protocol_artifact_sha256": _hash_paths(repo_root, PROTOCOL_ARTIFACT_PATHS),
        "prompt_sha256": _hash_paths(repo_root, PROMPT_PATHS),
        "model_profiles": MODEL_PROFILES,
        "runtime": {
            "compile_image": "autocompiler:gcc13",
            "image_id": "sha256:900d7ce4b902b79df5c64ffab88631b251538f1bde578c4dd2bf91558e9d1554",
            "control_plane_topology": CONTROL_PLANE_TOPOLOGY,
            "replay_timeout_seconds": 1200,
            "cleanup_timeout_seconds": 20,
            "docker_control_timeout_seconds": 30,
            **RUNTIME_BUDGETS,
            "max_parallel_runs": 1,
            "backend_processes": 1,
            "network_policy": {
                "network_name": "compile_network_wwf_v1",
                "egress": "enabled_for_clone_and_dependencies",
            },
            "host": {
                "wsl_distribution": "Ubuntu",
                "cpu_count": 32,
                "memory_kib": 7723024,
                "kernel": "6.6.114.1-microsoft-standard-WSL2",
                "architecture": "x86_64",
                "docker_server_version": "29.5.3",
            },
        },
        "budget": _budget(prereg),
        "conditions": [
            {
                "id": condition["id"],
                "model_profile": condition["id"],
                "memory_enabled": False,
                "skills_enabled": False,
                "repetitions": prereg["design"]["repetitions_per_project_condition"],
                "acceptance_gate": "clean_replay",
            }
            for condition in prereg["conditions"]
        ],
        "collection_plan": schedule,
        "schedule_sha256": prereg["design"]["schedule_sha256"],
        "cases": _runtime_cases(prereg, case_document),
    }
    return validate_manifest(
        manifest,
        prereg=prereg,
        case_document=case_document,
    )


def _validate_hash_map(
    value: Any,
    *,
    expected_paths: set[str],
    path: str,
) -> dict[str, str]:
    hashes = v1._as_object(value, path)
    if set(hashes) != expected_paths:
        v1._fail(path, "must contain exactly the required frozen paths")
    for relative_path, digest in hashes.items():
        pure_path = PurePosixPath(relative_path)
        if pure_path.is_absolute() or ".." in pure_path.parts or "\\" in relative_path:
            v1._fail(f"{path}.{relative_path}", "must stay inside the repository")
        v1._validate_sha256(digest, f"{path}.{relative_path}")
    return hashes


def validate_manifest(
    document: Any,
    *,
    prereg: dict[str, Any] | None = None,
    case_document: dict[str, Any] | None = None,
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
        }
        if set(manifest) != expected_root:
            v1._fail("manifest", "must contain exactly the formal protocol fields")
        if manifest["schema_version"] != SCHEMA_VERSION:
            v1._fail("manifest.schema_version", f"must be {SCHEMA_VERSION!r}")
        if manifest["document_type"] != "manifest":
            v1._fail("manifest.document_type", "must be 'manifest'")
        v1._scan_for_unsafe_values(manifest)
        prereg = prereg or preregistration.load_preregistration()
        case_document = case_document or case_protocol.load_protocol()
        preregistration.validate_preregistration(prereg)
        case_protocol.validate_protocol(case_document, preregistration=prereg)
        if manifest["source_protocols"] != _source_protocols(prereg, case_document):
            v1._fail(
                "manifest.source_protocols",
                "must bind the frozen preregistration and case protocol",
            )
        scope = manifest["scope"]
        if scope != {
            "languages": ["C", "C++"],
            "phase": "formal_pre_collection",
            "formal_comparison_enabled": True,
            "collection_authorized": False,
            "instrumentation_blocker": False,
        }:
            v1._fail(
                "manifest.scope",
                "must remain pre-collection and collection_authorized=false",
            )
        forge = v1._as_object(manifest["forge"], "manifest.forge")
        if forge.get("commit_sha") != BASELINE_COMMIT or forge.get("revision_policy") != REVISION_POLICY:
            v1._fail("manifest.forge", "must bind the reviewed Issue #78 baseline")
        _validate_hash_map(
            forge["component_sha256"],
            expected_paths=COMPONENT_PATHS,
            path="manifest.forge.component_sha256",
        )
        _validate_hash_map(
            manifest["protocol_artifact_sha256"],
            expected_paths=PROTOCOL_ARTIFACT_PATHS,
            path="manifest.protocol_artifact_sha256",
        )
        _validate_hash_map(
            manifest["prompt_sha256"],
            expected_paths=PROMPT_PATHS,
            path="manifest.prompt_sha256",
        )
        if manifest["model_profiles"] != MODEL_PROFILES:
            v1._fail(
                "manifest.model_profiles",
                "must freeze the preregistered provider profiles",
            )
        runtime = manifest["runtime"]
        if runtime.get("control_plane_topology") != CONTROL_PLANE_TOPOLOGY or runtime.get("max_parallel_runs") != 1 or runtime.get("backend_processes") != 1:
            v1._fail(
                "manifest.runtime",
                "must freeze serial Compose/DooD execution",
            )
        for key, expected in RUNTIME_BUDGETS.items():
            if runtime.get(key) != expected:
                v1._fail(f"manifest.runtime.{key}", f"must be {expected}")
        expected_budget = _budget(prereg)
        if manifest["budget"] != expected_budget:
            v1._fail(
                "manifest.budget",
                "must bind the preregistered projection and confirmation gate",
            )
        expected_conditions = [
            {
                "id": condition["id"],
                "model_profile": condition["id"],
                "memory_enabled": False,
                "skills_enabled": False,
                "repetitions": 3,
                "acceptance_gate": "clean_replay",
            }
            for condition in prereg["conditions"]
        ]
        if manifest["conditions"] != expected_conditions:
            v1._fail(
                "manifest.conditions",
                "must freeze both preregistered conditions with three repetitions",
            )
        schedule = preregistration.build_schedule(prereg)
        if manifest["collection_plan"] != schedule or len(schedule) != 180 or manifest["schedule_sha256"] != prereg["design"]["schedule_sha256"]:
            v1._fail(
                "manifest.collection_plan",
                "must equal the frozen 180-slot schedule",
            )
        expected_cases = _runtime_cases(prereg, case_document)
        if manifest["cases"] != expected_cases:
            v1._fail(
                "manifest.cases",
                "must be mechanically derived from both frozen source protocols",
            )
        return manifest
    except BenchmarkError:
        raise
    except (AttributeError, KeyError, OverflowError, TypeError, ValueError) as exc:
        raise BenchmarkError("manifest: contains a malformed value") from exc


def canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return canonical_json_bytes(validate_manifest(manifest))


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()


def verify_frozen_components(
    manifest: dict[str, Any],
    repo_root: Path = REPOSITORY_ROOT,
) -> None:
    validate_manifest(manifest)
    for path_prefix, hashes in (
        ("manifest.forge.component_sha256", manifest["forge"]["component_sha256"]),
        ("manifest.protocol_artifact_sha256", manifest["protocol_artifact_sha256"]),
        ("manifest.prompt_sha256", manifest["prompt_sha256"]),
    ):
        for relative_path, expected in hashes.items():
            actual = _file_sha256(repo_root / relative_path)
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
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-cpp-formal-v1.schema.json",
        "title": "Forge C/C++ formal runtime protocol",
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
        ],
        "properties": {
            "schema_version": {"const": SCHEMA_VERSION},
            "document_type": {"const": "manifest"},
            "scope": {
                "type": "object",
                "required": ["collection_authorized"],
                "properties": {"collection_authorized": {"const": False}},
            },
            "source_protocols": {"type": "object"},
            "forge": {
                "type": "object",
                "required": ["commit_sha", "component_sha256"],
                "properties": {
                    "commit_sha": {"pattern": "^[0-9a-f]{40}$"},
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
