#!/usr/bin/env python3
"""Issue #196 opaque provenance R1 独立 checkpoint 未授权候选协议。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "benchmarks/manifests/cpp-opaque-provenance-r1-checkpoint-candidate.json"
)
DEFAULT_SCHEMA = (
    REPO_ROOT
    / "benchmarks/schemas/forge-opaque-provenance-r1-checkpoint-candidate.schema.json"
)
SOURCE_PROTOCOL_PATH = "benchmarks/preregistrations/cpp-formal-v1-cases.json"
RUNTIME_ADAPTER_PATH = "scripts/forge_opaque_provenance_r1_candidate_runner.py"
PREREGISTRATION_PATH = (
    "benchmarks/preregistrations/cpp-opaque-provenance-r1-checkpoint-candidate.md"
)

SCHEMA_VERSION = "forge-opaque-provenance-r1-checkpoint-candidate-1.0.0"
DOCUMENT_TYPE = "forge_opaque_provenance_r1_checkpoint_candidate"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/196"
AUTHORIZATION_BASELINE_COMMIT = "7fe33b2bde6cbed5d42110eb74434b029a754fa7"
SOURCE_PROTOCOL_FILE_SHA256 = (
    "55fc4ea1cc634376b5016fa3421736a66c284b293b9b8f10185e837e12db3fee"
)
SOURCE_CASES_SHA256 = "3adb51f7c4cee22219c6ef4035fa0bc1e1dc6764e6246ad0dc4f612a03bb31ca"
PAIR_ID = "opaque-provenance-r1-yyjson-pair-01"
EVIDENCE_DIRECTORY = (
    "/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-r1-yyjson-v1"
)
EVIDENCE_SCHEMA_VERSION = "forge-opaque-provenance-r1-evidence-1.0.0"

R0_COMPONENT_SHA256 = {
    "backend/tests/test_forge_opaque_provenance_rejection_observability_gate.py": "436099e045138ac05d8c53e81d2a8b2a821f1e44213bbcd540e39d1d6e531f2c",
    "benchmarks/preregistrations/cpp-opaque-provenance-rejection-observability-gate.md": "650670b29c2c7d4858e4403c544febb424b81eba18afafea0f851d362a2f689e",
    "scripts/forge_opaque_provenance_rejection_observability_gate.py": "695c6188acf92f4e34dcbaf4c6f049ca4b024e9bdd1eb91085c0c8d5d0ace158",
}
REPAIR_PACKET_ORIGIN = "scripts/forge_opaque_build_provenance_real_docker_gate.py"
REPAIR_PACKET_ORIGIN_SHA256 = (
    "cfaac00042a623083f351e5e1b82c7b0b497bb923aea6f02b35174a40cf949e4"
)
REPAIR_PACKET_FIELDS = [
    "schema_version",
    "primary_classification",
    "mechanism_classification",
    "expected_build_system",
    "selected_build_system",
    "build_directory",
    "target",
    "proof_status",
    "repair_goal",
]
R0_OBSERVATION_FIELDS = [
    "rejection_classification",
    "action_kind",
    "model_request_id",
    "tool_ordinal",
    "command_sha256",
]

YYJSON_SOURCE_CASE = {
    "id": "yyjson",
    "repository_url": "https://github.com/ibireme/yyjson",
    "commit": "9365ddc7061033df656578bf86040048b5b5531a",
    "build_system": "cmake",
    "review_state": "reviewed",
    "result_data_consulted": False,
    "recipe": {
        "source_subdir": ".",
        "bootstrap_commands": [],
        "configure_arguments": [
            "-DCMAKE_BUILD_TYPE=Release",
            "-DBUILD_SHARED_LIBS=OFF",
            "-DYYJSON_BUILD_TESTS=OFF",
            "-DYYJSON_BUILD_FUZZER=OFF",
        ],
        "build_targets": ["yyjson"],
        "required_system_packages": ["build-essential", "cmake"],
    },
    "artifact_oracle": {
        "required_artifacts": [
            {
                "staged_relative_path": "libyyjson.a",
                "build_output_path": "build/libyyjson.a",
                "artifact_type": "static_library",
                "producing_target": "yyjson",
            }
        ]
    },
    "evidence": [
        {
            "kind": "upstream_exact_commit",
            "path": "CMakeLists.txt",
            "url": "https://github.com/ibireme/yyjson/blob/9365ddc7061033df656578bf86040048b5b5531a/CMakeLists.txt",
            "supports": ["build_path", "artifact_identity"],
        },
        {
            "kind": "oss_fuzz_snapshot",
            "path": "yyjson/build.sh",
            "url": "https://github.com/google/oss-fuzz/blob/08682bfc14e31d12fcc94b52b4805d7994fb70fd/projects/yyjson/build.sh",
            "supports": ["build_path"],
        },
    ],
}


class ProtocolError(RuntimeError):
    """R1 候选、source case、R0 或授权边界发生漂移。"""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"cannot load {label}") from exc
    if not isinstance(value, dict):
        raise ProtocolError(f"{label} must be an object")
    return value


def _load_source_case(path: Path) -> dict[str, Any]:
    if file_sha256(path) != SOURCE_PROTOCOL_FILE_SHA256:
        raise ProtocolError("formal v1 source protocol file drifted")
    protocol = _load_object(path, "formal v1 source protocol")
    metadata = protocol.get("protocolization")
    if (
        not isinstance(metadata, dict)
        or metadata.get("case_protocol_sha256") != SOURCE_CASES_SHA256
    ):
        raise ProtocolError("formal v1 source case identity drifted")
    matches = [
        case
        for case in protocol.get("cases", [])
        if isinstance(case, dict) and case.get("id") == "yyjson"
    ]
    if matches != [YYJSON_SOURCE_CASE]:
        raise ProtocolError("yyjson source case fields drifted")
    return copy.deepcopy(matches[0])


def _verify_frozen_components(repo_root: Path) -> None:
    expected = {
        SOURCE_PROTOCOL_PATH: SOURCE_PROTOCOL_FILE_SHA256,
        REPAIR_PACKET_ORIGIN: REPAIR_PACKET_ORIGIN_SHA256,
        **R0_COMPONENT_SHA256,
    }
    for relative_path, expected_sha256 in expected.items():
        path = repo_root / relative_path
        if not path.is_file() or file_sha256(path) != expected_sha256:
            raise ProtocolError(f"frozen component drifted: {relative_path}")


def _case(source_case: dict[str, Any]) -> dict[str, Any]:
    artifact = source_case["artifact_oracle"]["required_artifacts"][0]
    return {
        "case_id": "yyjson-opaque-provenance-r1",
        "repository_url": source_case["repository_url"],
        "commit_sha": source_case["commit"],
        "compile_image": "autocompiler:gcc13",
        "build_system": source_case["build_system"],
        "source_subdir": source_case["recipe"]["source_subdir"],
        "build_directory": "/workspace/repo/build",
        "configure_arguments": copy.deepcopy(
            source_case["recipe"]["configure_arguments"]
        ),
        "target": artifact["producing_target"],
        "build_output": artifact["build_output_path"],
        "staged_artifact": artifact["staged_relative_path"],
        "artifact_type": artifact["artifact_type"],
        "required_system_packages": copy.deepcopy(
            source_case["recipe"]["required_system_packages"]
        ),
        "parent_proof_status": "opaque_wrapper",
        "parent_expected_failure": "build_system_unproven",
    }


def _evidence_identity() -> dict[str, Any]:
    identity = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "directory": EVIDENCE_DIRECTORY,
        "checkpoint_manifest": f"checkpoints/{PAIR_ID}/checkpoint.json",
        "parent_ledger": f"checkpoints/{PAIR_ID}/parent/events.jsonl",
        "pair_ledger": f"pairs/{PAIR_ID}/events.jsonl",
        "arm_ledger_directory": f"pairs/{PAIR_ID}/arms",
        "reachability_marker": "markers/reachability.json",
        "pair_marker": "markers/pair.json",
        "canary_report": "reports/canary.json",
        "append_only": True,
        "status": "not_created",
        "zero_provider_preflight_writes_evidence": False,
    }
    return {**identity, "identity_sha256": canonical_sha256(identity)}


def _repair_packet(case: dict[str, Any]) -> dict[str, Any]:
    template = {
        "schema_version": "forge-opaque-provenance-repair-packet-1.0.0",
        "primary_classification": "build_system_unproven",
        "mechanism_classification": "opaque_build_provenance",
        "expected_build_system": "cmake",
        "selected_build_system": "cmake",
        "build_directory": case["build_directory"],
        "target": case["target"],
        "proof_status": "opaque_wrapper",
        "repair_goal": "Execute and record a trusted build-system invocation bound to the frozen build directory and target, then submit again.",
    }
    if list(template) != REPAIR_PACKET_FIELDS:
        raise ProtocolError("repair packet schema fields drifted")
    return {
        "schema_version": template["schema_version"],
        "fields": REPAIR_PACKET_FIELDS,
        "template": template,
        "origin_path": REPAIR_PACKET_ORIGIN,
        "origin_file_sha256": REPAIR_PACKET_ORIGIN_SHA256,
        "forbidden_solution_fields": [
            "command",
            "argv",
            "command_line",
            "shell",
            "credential",
            "secret",
        ],
    }


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    _verify_frozen_components(repo_root)
    source_case = _load_source_case(repo_root / SOURCE_PROTOCOL_PATH)
    case = _case(source_case)
    runtime_path = repo_root / RUNTIME_ADAPTER_PATH
    preregistration_path = repo_root / PREREGISTRATION_PATH
    if not runtime_path.is_file() or not preregistration_path.is_file():
        raise ProtocolError("R1 runtime adapter or preregistration is missing")
    schedule = [
        {
            "pair_id": PAIR_ID,
            "order": 1,
            "case_id": case["case_id"],
            "arm_order": ["baseline", "treatment"],
            "state_matched": True,
            "treatment_exposure_only": "repair_packet",
            "shared_measurement_policy": "runtime_parity_with_r0_observability_v1",
        }
    ]
    return {
        "$schema": "../schemas/forge-opaque-provenance-r1-checkpoint-candidate.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "authorization": {
            "issue_url": ISSUE_URL,
            "candidate_generation_authorized": True,
            "zero_provider_preflight_authorized": True,
            "checkpoint_creation_authorized": False,
            "reachability_request_authorized": False,
            "provider_calls_authorized": False,
            "formal_attempts_authorized": False,
            "pair_collection_authorized": False,
            "credential_read_authorized": False,
            "model_creation_authorized": False,
            "docker_execution_authorized": False,
            "evidence_write_authorized": False,
            "model_tokens_authorized": 0,
        },
        "source_protocol": {
            "path": SOURCE_PROTOCOL_PATH,
            "file_sha256": SOURCE_PROTOCOL_FILE_SHA256,
            "case_protocol_sha256": SOURCE_CASES_SHA256,
            "audit_mode": "result-blind-static-document-review",
            "source_case": source_case,
        },
        "case": case,
        "independence": {
            "historical_pair": "opaque-provenance-cppitertools-runtime-parity-pair-01",
            "historical_repository_url": "https://github.com/ryanhaining/cppitertools",
            "historical_commit_sha": "531b3d753d2bbfe3b0ababe61c2e95e965c54a66",
            "historical_target": "accumulate_examples",
            "historical_staged_artifact": "accumulate_examples",
            "repository_commit_target_and_artifact_all_distinct": True,
            "historical_pair_pooled": False,
            "retry_replacement_backfill_or_extension": False,
        },
        "checkpoint": {
            "status": "not_created",
            "checkpoint_id": None,
            "parent_ledger_sha256": None,
            "message_state_sha256": None,
            "environment_identity_sha256": None,
            "budget_identity_sha256": None,
            "arm_state_matching": ["message", "environment", "budget"],
            "creation_requires_separate_authorization": True,
        },
        "provider": {
            "status": "candidate_not_authorized",
            "id": "deepseek-v4-flash",
            "endpoint": "https://api.deepseek.com",
            "credential_env": "DEEPSEEK_API_KEY",
            "model": "deepseek-v4-flash",
            "request_timeout_seconds": 300,
            "max_retries": 0,
            "fallback": "forbidden",
            "streaming": False,
        },
        "continuation": {
            "maximum_requests_per_arm": 8,
            "maximum_model_turns_per_arm": 8,
            "maximum_graph_steps_per_arm": 24,
            "work_wall_clock_seconds_per_arm": 600,
            "cleanup_reserve_seconds_per_arm": 120,
            "maximum_recorded_tokens_per_arm": 120000,
        },
        "schedule": schedule,
        "schedule_sha256": canonical_sha256(schedule),
        "repair_packet": _repair_packet(case),
        "runtime_parity": {
            "action_limits": {
                "inspection": 4,
                "repair_build": 2,
                "artifact_stage": 2,
                "submit": 2,
            },
            "atomic_budget_claim": True,
            "parallel_tool_calls": False,
            "repair_build_directory": case["build_directory"],
            "repair_build_target": case["target"],
            "build_output": case["build_output"],
            "staged_artifact": case["staged_artifact"],
            "forbidden_actions": [
                "clone",
                "configure",
                "dependency",
                "housekeeping",
                "manual_replay",
                "compound_build_stage",
            ],
            "candidate_verification_required": True,
            "clean_replay_required": True,
            "cleanup_required": True,
        },
        "r0_observability": {
            "schema_version": "forge-opaque-provenance-rejection-observability-gate-1.0.0",
            "legacy_failure_event": "agent.tool_failed",
            "legacy_failure_schema_preserved": True,
            "companion_event": "agent.tool_rejection_observed",
            "companion_required_for_classified_rejection": True,
            "failure_link_field": "failure_id",
            "atomic_fields": R0_OBSERVATION_FIELDS,
            "raw_command_error_model_text_and_credentials_forbidden": True,
            "unknown_or_ambiguous_tool_call_keeps_legacy_event_only": True,
            "frozen_components": copy.deepcopy(R0_COMPONENT_SHA256),
        },
        "evidence": _evidence_identity(),
        "stopping": {
            "checkpoint_creation_failure_stops": True,
            "reachability_failure_stops_before_pair": True,
            "identity_evidence_budget_cleanup_or_unclassified_failure_stops": True,
            "retry_forbidden": True,
            "replacement_forbidden": True,
            "backfill_forbidden": True,
            "schedule_extension_forbidden": True,
        },
        "analysis": {
            "purpose": "independent_checkpoint_intervention_delivery_and_p2_conversion_canary",
            "unit_of_analysis": "single_independent_state_matched_pair",
            "primary_outcome": "paired_post_checkpoint_p2_conversion_with_candidate_and_clean_replay",
            "descriptive_only": True,
            "treatment_effect_estimated": False,
            "p_value_computed": False,
            "model_ranking_performed": False,
            "historical_pairs_pooled": False,
        },
        "preflight": {
            "release_branch": "main",
            "require_clean_worktree": True,
            "require_head_equals_origin_main": True,
            "authorization_baseline_commit": AUTHORIZATION_BASELINE_COMMIT,
            "require_authorization_baseline_ancestor": True,
            "require_source_protocol_hash": True,
            "require_r0_component_hashes": True,
            "require_empty_candidate_evidence_directory": True,
            "require_checkpoint_not_created": True,
            "docker_check_forbidden": True,
        },
        "preregistration": {
            "path": PREREGISTRATION_PATH,
            "file_sha256": file_sha256(preregistration_path),
        },
        "runtime_adapter": {
            "path": RUNTIME_ADAPTER_PATH,
            "file_sha256": file_sha256(runtime_path),
            "commands": ["validate", "plan", "preflight"],
            "credential_read_supported": False,
            "provider_model_creation_supported": False,
            "checkpoint_execute_supported": False,
            "reachability_execute_supported": False,
            "pair_execute_supported": False,
            "docker_execute_supported": False,
            "evidence_write_supported": False,
        },
    }


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError("manifest must be an object")
    if value != generate_manifest(repo_root):
        raise ProtocolError("R1 checkpoint candidate manifest drifted")
    case = value["case"]
    independence = value["independence"]
    if not all(
        (
            case["repository_url"] != independence["historical_repository_url"],
            case["commit_sha"] != independence["historical_commit_sha"],
            case["target"] != independence["historical_target"],
            case["staged_artifact"] != independence["historical_staged_artifact"],
        )
    ):
        raise ProtocolError("R1 case is not independent from the exploratory pair")
    if (
        value["checkpoint"]["status"] != "not_created"
        or value["evidence"]["status"] != "not_created"
    ):
        raise ProtocolError("R1 candidate unexpectedly created checkpoint evidence")
    if value["runtime_parity"]["action_limits"] != {
        "inspection": 4,
        "repair_build": 2,
        "artifact_stage": 2,
        "submit": 2,
    }:
        raise ProtocolError("runtime-parity action limits drifted")
    return value


def load_manifest(
    path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    return validate_manifest(
        _load_object(path, "R1 checkpoint candidate manifest"), repo_root
    )


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    frozen = manifest or generate_manifest()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-opaque-provenance-r1-checkpoint-candidate.schema.json",
        "title": "Forge opaque provenance R1 independent checkpoint candidate",
        "const": frozen,
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "generate":
        manifest = generate_manifest()
        _write_json(args.manifest, manifest)
        _write_json(args.schema, schema_document(manifest))
    else:
        manifest = load_manifest(args.manifest)
    print(
        json.dumps(
            {
                "manifest_sha256": canonical_sha256(manifest),
                "checkpoint_status": manifest["checkpoint"]["status"],
                "provider_calls": 0,
                "formal_attempts": 0,
                "model_tokens": 0,
                "credential_read": False,
                "docker_executed": False,
                "evidence_writes": 0,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
