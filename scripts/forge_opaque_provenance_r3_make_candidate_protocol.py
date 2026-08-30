#!/usr/bin/env python3
"""Issue #216 R3 Make 单配对未执行候选协议。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-r3-make-candidate.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-r3-make-candidate.schema.json"
PARENT_MANIFEST_PATH = "benchmarks/manifests/cpp-opaque-provenance-r2-make-execution.json"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-opaque-provenance-r3-make-candidate.md"
RUNTIME_ADAPTER_PATH = "scripts/forge_opaque_provenance_r3_make_candidate_runner.py"

SCHEMA_VERSION = "forge-opaque-provenance-r3-make-candidate-1.0.0"
DOCUMENT_TYPE = "forge_opaque_provenance_r3_make_candidate"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/216"
AUTHORIZATION_BASELINE_COMMIT = "e58ef0f0e7d5968667dc0c0ce586834251daeac1"
PARENT_MANIFEST_CANONICAL_SHA256 = "113192d509b3c15762f8055cb32fc9364a4a4be6bede1eeed838e540a025224e"

FROZEN_PARENT_COMPONENTS = {
    PARENT_MANIFEST_PATH: "c25a9eca30b58e686c21a03497a0c5a163dda45ab06eaf922442a83780d7b17d",
    "scripts/forge_opaque_provenance_r2_make_execution_protocol.py": "9cf49a76284c6f80feb439c4112e438336ca0f5276300cf0e403100d9569d4dd",
    "scripts/forge_opaque_provenance_r2_make_execution_runner.py": "0854a836f347d371974594eadb32f72d0cff4361bcb06bd5e1ad2a9effef78c0",
    "scripts/forge_opaque_provenance_r3_make_construct_alignment_gate.py": "152e945707d18682101d80d525416c079945d934336da373e994e4338bce19d6",
    "scripts/forge_opaque_provenance_r3_make_lifecycle_gate.py": "132fc6248af4690c9823060657b490626031e44f55a5232de09a79a3426b3b4e",
    "backend/tests/test_forge_opaque_provenance_r3_make_lifecycle_gate.py": "54d1c6f7c1137783b83c8208bbaa213e9cbf23b12fdda73de961b96e8f704347",
    "backend/tests/test_forge_opaque_provenance_r3_make_lifecycle_gate_docker.py": "af7219ab296804cb21a519a28d2aeec15e8d09f4076d88054ff4b9efdd668a77",
    "benchmarks/preregistrations/cpp-opaque-provenance-r3-make-construct-alignment-gate.md": "c88f4750ed75c9360dcae7220541fc597e7a5422e87ac384fa591374a309346b",
    "benchmarks/preregistrations/cpp-opaque-provenance-r3-make-lifecycle-zero-provider-gate.md": "2205f3f40b1dd71e3a86327dc3696826b793f3969507598fc5893f686509b1af",
}


class ProtocolError(RuntimeError):
    """R3 candidate 身份、授权或冻结组件无效。"""


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


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"cannot load {label}") from exc
    if not isinstance(value, dict):
        raise ProtocolError(f"{label} must be an object")
    return value


def verify_frozen_components(repo_root: Path = REPO_ROOT) -> None:
    for relative_path, expected_sha256 in FROZEN_PARENT_COMPONENTS.items():
        if file_sha256(repo_root / relative_path) != expected_sha256:
            raise ProtocolError(f"frozen parent component drifted: {relative_path}")


def _parent_manifest(repo_root: Path) -> dict[str, Any]:
    verify_frozen_components(repo_root)
    parent = _load_object(repo_root / PARENT_MANIFEST_PATH, "R2 Make execution manifest")
    if canonical_sha256(parent) != PARENT_MANIFEST_CANONICAL_SHA256:
        raise ProtocolError("R2 Make execution manifest canonical identity drifted")
    return parent


def _evidence_identity(case: dict[str, Any], schedule: list[dict[str, Any]], repair_packet: dict[str, Any]) -> str:
    return canonical_sha256(
        {
            "schema_version": "forge-opaque-provenance-r3-make-evidence-1.0.0",
            "case": case,
            "schedule": schedule,
            "repair_packet": repair_packet,
            "jobs_policy": {"omitted_allowed": True, "minimum": 1, "maximum": 2},
            "parent_manifest_canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        }
    )


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    parent = _parent_manifest(repo_root)
    runtime_path = repo_root / RUNTIME_ADAPTER_PATH
    preregistration_path = repo_root / PREREGISTRATION_PATH
    if not runtime_path.is_file() or not preregistration_path.is_file():
        raise ProtocolError("R3 candidate runtime or preregistration is missing")

    case = copy.deepcopy(parent["case"])
    case["case_id"] = "hoextdown-opaque-provenance-r3-make"
    schedule = [
        {
            "pair_id": "opaque-provenance-r3-hoextdown-pair-01",
            "order": 1,
            "case_id": case["case_id"],
            "arm_order": ["baseline", "treatment"],
            "state_matched": True,
            "treatment_exposure_only": "repair_packet",
            "shared_measurement_policy": "r3_bounded_jobs_with_r0_observability_v1",
        }
    ]
    repair_packet = copy.deepcopy(parent["repair_packet"])
    provider = copy.deepcopy(parent["provider"])
    provider["status"] = "candidate_not_authorized"
    action_surface = {
        "direct_executables": ["make", "gmake"],
        "build_directory": case["build_directory"],
        "target": case["target"],
        "jobs": {"omitted_allowed": True, "minimum": 1, "maximum": 2},
        "artifact_stage": {
            "source": f"{case['build_directory']}/{case['build_output']}",
            "destination": f"/artifacts/{case['staged_artifact']}",
            "separate_from_build": True,
        },
    }
    evidence_identity = _evidence_identity(case, schedule, repair_packet)
    return {
        "$schema": "../schemas/forge-opaque-provenance-r3-make-candidate.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "authorization": {
            "issue_url": ISSUE_URL,
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
        "parent": {
            "manifest_path": PARENT_MANIFEST_PATH,
            "schema_version": parent["schema_version"],
            "canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
            "file_sha256": FROZEN_PARENT_COMPONENTS[PARENT_MANIFEST_PATH],
            "historical_result_reused": False,
            "authorization_baseline_commit": AUTHORIZATION_BASELINE_COMMIT,
        },
        "case": case,
        "checkpoint": {
            "status": "not_created",
            "checkpoint_id": None,
            "source_gate": "issue-214-r3-make-lifecycle-zero-provider",
            "arm_state_matching": ["message", "environment", "budget"],
            "creation_requires_execution_amendment": True,
        },
        "provider": provider,
        "continuation": copy.deepcopy(parent["continuation"]),
        "schedule": schedule,
        "schedule_sha256": canonical_sha256(schedule),
        "repair_packet": repair_packet,
        "budget": copy.deepcopy(parent["budget"]),
        "runtime_parity": {
            "action_limits": copy.deepcopy(parent["runtime_parity"]["action_limits"]),
            "atomic_budget_claim": True,
            "parallel_tool_calls": False,
            "shared_tool_contract_identical": True,
            "treatment_exposure_only": "repair_packet",
            "action_surface": action_surface,
            "candidate_verification_required": True,
            "clean_replay_required": True,
            "cleanup_required": True,
            "forbidden_actions": copy.deepcopy(parent["runtime_parity"]["forbidden_actions"]),
        },
        "r0_observability": copy.deepcopy(parent["r0_observability"]),
        "evidence": {
            "schema_version": "forge-opaque-provenance-r3-make-evidence-1.0.0",
            "directory": "/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-r3-hoextdown-candidate-v1",
            "status": "not_created",
            "append_only": True,
            "zero_provider_preflight_writes_evidence": False,
            "identity_sha256": evidence_identity,
        },
        "stopping": copy.deepcopy(parent["stopping"]),
        "analysis": {
            **copy.deepcopy(parent["analysis"]),
            "purpose": "r3_make_action_surface_aligned_conversion_replication_candidate",
            "treatment_effect_estimated": False,
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
            "r0_companion_contract_supported": True,
        },
        "frozen_parent_components": copy.deepcopy(FROZEN_PARENT_COMPONENTS),
    }


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if not isinstance(value, dict) or value != generate_manifest(repo_root):
        raise ProtocolError("R3 Make candidate manifest drifted")
    if any(value["authorization"][key] for key in value["authorization"] if key.endswith("_authorized")):
        raise ProtocolError("R3 Make candidate unexpectedly authorizes execution")
    if value["authorization"]["model_tokens_authorized"] != 0:
        raise ProtocolError("R3 Make candidate token authorization drifted")
    if value["checkpoint"]["status"] != "not_created" or value["evidence"]["status"] != "not_created":
        raise ProtocolError("R3 Make candidate unexpectedly materialized state")
    return value


def load_manifest(path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    return validate_manifest(_load_object(path, "R3 Make candidate manifest"), repo_root)


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    frozen = manifest or generate_manifest()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-opaque-provenance-r3-make-candidate.schema.json",
        "title": "Forge opaque provenance R3 Make candidate",
        "const": frozen,
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


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
