#!/usr/bin/env python3
"""Issue #206 R2 Make 单配对未执行候选协议。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-r2-make-candidate.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-r2-make-candidate.schema.json"
SOURCE_PROTOCOL_PATH = "benchmarks/preregistrations/cpp-formal-v1-cases.json"
RUNTIME_ADAPTER_PATH = "scripts/forge_opaque_provenance_make_candidate_runner.py"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-opaque-provenance-r2-make-candidate.md"

SCHEMA_VERSION = "forge-opaque-provenance-r2-make-candidate-1.0.0"
DOCUMENT_TYPE = "forge_opaque_provenance_r2_make_candidate"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/206"
AUTHORIZATION_BASELINE_COMMIT = "b8092e6f58830690359b137b32031d3cc96361dc"
SOURCE_PROTOCOL_FILE_SHA256 = "55fc4ea1cc634376b5016fa3421736a66c284b293b9b8f10185e837e12db3fee"
SOURCE_CASES_SHA256 = "3adb51f7c4cee22219c6ef4035fa0bc1e1dc6764e6246ad0dc4f612a03bb31ca"
PAIR_ID = "opaque-provenance-r2-hoextdown-pair-01"
EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-r2-hoextdown-v1"

FROZEN_COMPONENT_SHA256 = {
    "scripts/forge_opaque_provenance_make_reference_gate.py": "5df722d6115aa879a9dbe43fb5f98278ff72df6958ae99f22fe4cb2f6d16c14a",
    "scripts/forge_opaque_provenance_make_lifecycle_gate.py": "bb9fc467df0476cc1e7fdcca06bf64d020cb39f0efd48502289d814b3152230b",
    "benchmarks/preregistrations/cpp-opaque-provenance-make-lifecycle-zero-provider-gate.md": "c7d52ab58cca98e0438574f77909044ab6ed4d4556c859a5eda1b16560543fbd",
    "scripts/forge_opaque_provenance_rejection_observability_gate.py": "695c6188acf92f4e34dcbaf4c6f049ca4b024e9bdd1eb91085c0c8d5d0ace158",
    "backend/tests/test_forge_opaque_provenance_rejection_observability_gate.py": "436099e045138ac05d8c53e81d2a8b2a821f1e44213bbcd540e39d1d6e531f2c",
    "benchmarks/preregistrations/cpp-opaque-provenance-rejection-observability-gate.md": "650670b29c2c7d4858e4403c544febb424b81eba18afafea0f851d362a2f689e",
}
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


class ProtocolError(RuntimeError):
    """Make candidate 的 source、组件、manifest 或授权边界发生漂移。"""


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


def _load_source_case(repo_root: Path) -> dict[str, Any]:
    path = repo_root / SOURCE_PROTOCOL_PATH
    if file_sha256(path) != SOURCE_PROTOCOL_FILE_SHA256:
        raise ProtocolError("formal v1 source protocol file drifted")
    protocol = _load_object(path, "formal v1 source protocol")
    metadata = protocol.get("protocolization")
    if not isinstance(metadata, dict) or metadata.get("case_protocol_sha256") != SOURCE_CASES_SHA256:
        raise ProtocolError("formal v1 case protocol identity drifted")
    matches = [case for case in protocol.get("cases", []) if isinstance(case, dict) and case.get("id") == "hoextdown"]
    if len(matches) != 1 or matches[0].get("result_data_consulted") is not False:
        raise ProtocolError("result-blind hoextdown case is absent or ambiguous")
    return copy.deepcopy(matches[0])


def _verify_frozen_components(repo_root: Path) -> None:
    for relative_path, expected_sha256 in FROZEN_COMPONENT_SHA256.items():
        path = repo_root / relative_path
        if not path.is_file() or file_sha256(path) != expected_sha256:
            raise ProtocolError(f"frozen component drifted: {relative_path}")


def _case(source_case: dict[str, Any]) -> dict[str, Any]:
    recipe = source_case["recipe"]
    artifacts = source_case["artifact_oracle"]["required_artifacts"]
    if len(artifacts) != 1:
        raise ProtocolError("hoextdown must have one frozen artifact")
    artifact = artifacts[0]
    expected = {
        "repository_url": "https://github.com/kjdev/hoextdown",
        "commit_sha": "1ef9a71957570c2a65b7daa1b2f693ad87daf385",
        "build_system": "make",
        "source_subdir": ".",
        "target": "libhoedown.a",
        "build_output": "libhoedown.a",
        "staged_artifact": "libhoedown.a",
        "artifact_type": "static_library",
    }
    actual = {
        "repository_url": source_case["repository_url"],
        "commit_sha": source_case["commit"],
        "build_system": source_case["build_system"],
        "source_subdir": recipe["source_subdir"],
        "target": artifact["producing_target"],
        "build_output": artifact["build_output_path"],
        "staged_artifact": artifact["staged_relative_path"],
        "artifact_type": artifact["artifact_type"],
    }
    if actual != expected:
        raise ProtocolError("hoextdown candidate identity drifted")
    return {
        "case_id": "hoextdown-opaque-provenance-r2-make",
        **actual,
        "compile_image": "autocompiler:gcc13",
        "build_directory": "/workspace/repo",
        "required_system_packages": copy.deepcopy(recipe["required_system_packages"]),
        "parent_proof_status": "opaque_wrapper",
        "parent_expected_failure": "build_system_unproven",
    }


def _repair_packet(case: dict[str, Any]) -> dict[str, Any]:
    template = {
        "schema_version": "forge-opaque-provenance-repair-packet-1.0.0",
        "primary_classification": "build_system_unproven",
        "mechanism_classification": "opaque_build_provenance",
        "expected_build_system": "make",
        "selected_build_system": "make",
        "build_directory": case["build_directory"],
        "target": case["target"],
        "proof_status": "opaque_wrapper",
        "repair_goal": "Execute and record a trusted build-system invocation bound to the frozen directory and target, then submit again.",
    }
    if list(template) != REPAIR_PACKET_FIELDS:
        raise ProtocolError("repair packet fields drifted")
    return {
        "schema_version": template["schema_version"],
        "fields": REPAIR_PACKET_FIELDS,
        "template": template,
        "origin_path": "scripts/forge_opaque_provenance_make_lifecycle_gate.py",
        "origin_file_sha256": FROZEN_COMPONENT_SHA256["scripts/forge_opaque_provenance_make_lifecycle_gate.py"],
        "forbidden_solution_fields": [
            "command",
            "argv",
            "command_line",
            "shell",
            "credential",
            "secret",
        ],
    }


def _evidence_identity() -> dict[str, Any]:
    identity = {
        "schema_version": "forge-opaque-provenance-r2-make-evidence-1.0.0",
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


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    _verify_frozen_components(repo_root)
    source_case = _load_source_case(repo_root)
    case = _case(source_case)
    runtime_path = repo_root / RUNTIME_ADAPTER_PATH
    preregistration_path = repo_root / PREREGISTRATION_PATH
    if not runtime_path.is_file() or not preregistration_path.is_file():
        raise ProtocolError("runtime adapter or preregistration is missing")
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
    r0_components = {path: sha256 for path, sha256 in FROZEN_COMPONENT_SHA256.items() if "rejection_observability" in path}
    return {
        "$schema": "../schemas/forge-opaque-provenance-r2-make-candidate.schema.json",
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
        "frozen_components": copy.deepcopy(FROZEN_COMPONENT_SHA256),
        "source_protocol": {
            "path": SOURCE_PROTOCOL_PATH,
            "file_sha256": SOURCE_PROTOCOL_FILE_SHA256,
            "case_protocol_sha256": SOURCE_CASES_SHA256,
            "audit_mode": "result-blind-static-document-review",
            "source_case": source_case,
        },
        "case": case,
        "checkpoint": {
            "status": "not_created",
            "checkpoint_id": None,
            "arm_state_matching": ["message", "environment", "budget"],
            "creation_requires_execution_amendment": True,
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
        "budget": {
            "reachability_recorded_tokens": 5000,
            "maximum_requests_per_arm": 8,
            "maximum_model_turns_per_arm": 8,
            "maximum_graph_steps_per_arm": 24,
            "work_wall_clock_seconds_per_arm": 600,
            "cleanup_reserve_seconds_per_arm": 120,
            "maximum_recorded_tokens_per_arm": 120000,
            "pair_recorded_tokens": 240000,
            "phase_recorded_token_ceiling": 245000,
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
            "frozen_components": r0_components,
        },
        "evidence": _evidence_identity(),
        "stopping": {
            "reachability_failure_stops_before_pair": True,
            "identity_evidence_budget_cleanup_or_unclassified_failure_stops": True,
            "retry_replacement_backfill_or_extension_forbidden": True,
        },
        "analysis": {
            "purpose": "cross_build_system_p2_conversion_replication_canary",
            "unit_of_analysis": "single_state_matched_make_pair",
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
            "require_frozen_component_hashes": True,
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
    if not isinstance(value, dict) or value != generate_manifest(repo_root):
        raise ProtocolError("R2 Make candidate manifest drifted")
    budget = value["budget"]
    if budget["phase_recorded_token_ceiling"] != budget["reachability_recorded_tokens"] + budget["pair_recorded_tokens"]:
        raise ProtocolError("R2 Make candidate token ceiling drifted")
    if value["checkpoint"]["status"] != "not_created" or value["evidence"]["status"] != "not_created":
        raise ProtocolError("R2 Make candidate unexpectedly created checkpoint evidence")
    return value


def load_manifest(path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    return validate_manifest(_load_object(path, "R2 Make candidate manifest"), repo_root)


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    frozen = manifest or generate_manifest()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-opaque-provenance-r2-make-candidate.schema.json",
        "title": "Forge opaque provenance R2 Make candidate",
        "const": frozen,
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args(argv)
    if args.command == "generate":
        manifest = generate_manifest()
        _write_json(args.manifest, manifest)
        _write_json(args.schema, schema_document(manifest))
    else:
        manifest = load_manifest(args.manifest)
    print(json.dumps({"manifest_sha256": canonical_sha256(manifest), "authorization": manifest["authorization"]}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
