#!/usr/bin/env python3
"""Issue #180 opaque build provenance 最小 provider canary 候选协议。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-minimal-canary.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-minimal-canary.schema.json"

SCHEMA_VERSION = "forge-opaque-provenance-minimal-canary-1.0.0"
DOCUMENT_TYPE = "forge_opaque_provenance_minimal_canary_protocol"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/180"
PAIR_ID = "opaque-provenance-cppitertools-pair-01"
RECORDED_TOKENS_PER_ARM = 120_000
PAIR_RECORDED_TOKEN_LIMIT = RECORDED_TOKENS_PER_ARM * 2
REACHABILITY_RECORDED_TOKEN_LIMIT = 5_000
STAGE_RECORDED_TOKEN_LIMIT = PAIR_RECORDED_TOKEN_LIMIT + REACHABILITY_RECORDED_TOKEN_LIMIT

FROZEN_COMPONENT_PATHS = {
    "benchmarks/preregistrations/cpp-opaque-build-provenance-lifecycle-zero-provider-gate.md",
    "benchmarks/preregistrations/cpp-opaque-build-provenance-real-docker-zero-provider-gate.md",
    "benchmarks/preregistrations/cpp-opaque-build-provenance-zero-provider-gate.md",
    "scripts/forge_opaque_build_provenance_gate.py",
    "scripts/forge_opaque_build_provenance_lifecycle_gate.py",
    "scripts/forge_opaque_build_provenance_real_docker_gate.py",
}


class ProtocolError(RuntimeError):
    """候选协议、预算或冻结组件发生漂移。"""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_paths(repo_root: Path, paths: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative_path in sorted(paths):
        path = repo_root / relative_path
        if not path.is_file():
            raise ProtocolError(f"frozen component missing: {relative_path}")
        result[relative_path] = file_sha256(path)
    return result


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    schedule = [
        {
            "pair_id": PAIR_ID,
            "order": 1,
            "case_id": "cppitertools-opaque-provenance-real-docker",
            "arm_order": ["baseline", "treatment"],
            "treatment_exposure_only": "repair_packet",
        }
    ]
    return {
        "$schema": "../schemas/forge-opaque-provenance-minimal-canary.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "authorization": {
            "issue_url": ISSUE_URL,
            "protocol_freeze_authorized": True,
            "reachability_request_authorized": False,
            "provider_calls_authorized": False,
            "formal_attempts_authorized": False,
            "canary_collection_authorized": False,
            "model_tokens_authorized": 0,
        },
        "scope": {
            "languages": ["C++"],
            "mechanism": "provenance_compliance_repair",
            "fault_family": "opaque_build_provenance",
            "production_classification": "build_system_unproven",
            "reference_criterion": "P2",
            "behavioral_pilot_expansion_authorized": False,
        },
        "case": {
            "case_id": "cppitertools-opaque-provenance-real-docker",
            "repository_url": "https://github.com/ryanhaining/cppitertools",
            "commit_sha": "531b3d753d2bbfe3b0ababe61c2e95e965c54a66",
            "compile_image": "autocompiler:gcc13",
            "build_system": "cmake",
            "build_directory": "/workspace/repo/build",
            "target": "accumulate_examples",
            "staged_artifact": "accumulate_examples",
            "checkpoint_source": "issue-178-real-docker-lifecycle",
            "parent_proof_status": "opaque_wrapper",
            "parent_expected_failure": "build_system_unproven",
        },
        "reference_chain": [
            {"issue": 174, "purpose": "P2_reference_contract", "main_commit": "869686b3"},
            {"issue": 176, "purpose": "synthetic_lifecycle_contract", "main_commit": "5b5d867d"},
            {"issue": 178, "purpose": "real_docker_lifecycle", "main_commit": "aa1768dd"},
        ],
        "provider": {
            "status": "future_identity_only",
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
            "maximum_recorded_tokens_per_arm": RECORDED_TOKENS_PER_ARM,
        },
        "schedule": schedule,
        "schedule_sha256": canonical_sha256(schedule),
        "budget": {
            "maximum_reachability_requests": 1,
            "reachability_maximum_recorded_tokens": REACHABILITY_RECORDED_TOKEN_LIMIT,
            "recorded_tokens_per_arm": RECORDED_TOKENS_PER_ARM,
            "recorded_tokens_per_pair": PAIR_RECORDED_TOKEN_LIMIT,
            "stage_maximum_recorded_tokens": STAGE_RECORDED_TOKEN_LIMIT,
            "enforcement": "after_reachability_and_each_arm_before_continuation",
        },
        "stopping": {
            "reachability_failure_stops_before_pair": True,
            "identity_evidence_budget_cleanup_or_unclassified_failure_stops": True,
            "classified_arm_outcome_continues_other_arm": True,
            "endpoint_timeout_censors_arm_and_continues": True,
            "retry_forbidden": True,
            "replacement_forbidden": True,
            "backfill_forbidden": True,
            "schedule_extension_forbidden": True,
        },
        "analysis": {
            "purpose": "mechanism_wiring_canary_only",
            "unit_of_analysis": "single_failure_checkpoint_pair",
            "descriptive_only": True,
            "treatment_effect_estimated": False,
            "p_value_computed": False,
            "model_ranking_performed": False,
            "historical_pairs_pooled": False,
        },
        "execution": {
            "mode": "protocol_plan_only",
            "control_plane": "compose-dood-on-ubuntu-native-docker",
            "release_branch": "main",
            "require_clean_worktree": True,
            "require_origin_main_identity": True,
            "require_network_medium_record": True,
            "require_empty_evidence_directory": True,
            "require_zero_managed_orphans": True,
            "provider_model_creation_supported": False,
            "credential_read_supported": False,
            "execute_path_supported": False,
        },
        "frozen_components": _hash_paths(repo_root, FROZEN_COMPONENT_PATHS),
    }


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError("manifest must be an object")
    if value != generate_manifest(repo_root):
        raise ProtocolError("opaque provenance minimal canary manifest drifted")
    return value


def load_manifest(path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError("cannot read opaque provenance minimal canary manifest") from exc
    return validate_manifest(value, repo_root)


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    frozen = manifest or generate_manifest()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-opaque-provenance-minimal-canary.schema.json",
        "title": "Forge opaque provenance minimal canary protocol",
        "const": frozen,
    }


def show_plan(manifest: dict[str, Any]) -> dict[str, Any]:
    validate_manifest(manifest)
    return {
        "case_id": manifest["case"]["case_id"],
        "pair_id": manifest["schedule"][0]["pair_id"],
        "arm_order": manifest["schedule"][0]["arm_order"],
        "provider": manifest["provider"]["id"],
        "stage_maximum_recorded_tokens": manifest["budget"]["stage_maximum_recorded_tokens"],
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
        "execution_authorized": False,
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate", "show-plan"))
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
    result = (
        show_plan(manifest)
        if args.command == "show-plan"
        else {
            "manifest_sha256": canonical_sha256(manifest),
            "provider_calls": 0,
            "formal_attempts": 0,
            "model_tokens": 0,
        }
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
