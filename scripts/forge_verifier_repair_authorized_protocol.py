#!/usr/bin/env python3
"""生成并校验 verifier-driven repair 配对 pilot 授权协议。"""

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
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_verifier_repair_pilot_protocol as parent_protocol  # noqa: E402

SCHEMA_VERSION = "verifier-driven-repair-pilot-authorized-1.0.0"
BASELINE_COMMIT = "fb24fa2b7acd0b39826d3440b8221a00a4d1a136"
PARENT_CANONICAL_SHA256 = "880af0175795e474d470fd483544296fc68cdb0e5e968cebd32d73ef183ab045"
REVISION_POLICY = "descendant-compatible"
CONTROL_PLANE_TOPOLOGY = "compose-dood"
DOCKER_DAEMON_PROVIDER = "ubuntu-native"
DOCKER_SOCKET_PATH = "/var/run/docker.sock"
EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-verifier-repair-authorized"
RECORDED_TOKEN_LIMIT = 2_400_000
EXPECTED_RECORDED_TOKENS = 800_000

DEFAULT_PARENT_MANIFEST = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-verifier-repair-pilot-runtime-candidate.json"
DEFAULT_MODEL_SOURCE = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-formal-timeout-calibration.json"
DEFAULT_MANIFEST = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-verifier-repair-pilot-authorized.json"
DEFAULT_SCHEMA = REPOSITORY_ROOT / "benchmarks" / "schemas" / "forge-verifier-repair-pilot-authorized-v1.schema.json"

PROTOCOL_ARTIFACT_PATHS = {
    "scripts/forge_verifier_repair_authorized_protocol.py",
    "scripts/forge_verifier_repair_authorized_runner.py",
    "scripts/forge_verifier_repair_authorized_report.py",
}

BASELINE_ARM = "baseline-current-verifier-output"
TREATMENT_ARM = "structured-verifier-repair-packet"
CONDITION_IDS = {
    ("richlab-gpt-5.5", BASELINE_ARM): "richlab-gpt-5.5-baseline",
    ("richlab-gpt-5.5", TREATMENT_ARM): "richlab-gpt-5.5-repair",
    ("deepseek-v4-flash", BASELINE_ARM): "deepseek-v4-flash-baseline",
    ("deepseek-v4-flash", TREATMENT_ARM): "deepseek-v4-flash-repair",
}


class ProtocolError(ValueError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"cannot read JSON document: {path}") from exc
    if not isinstance(value, dict):
        raise ProtocolError(f"JSON document must be an object: {path}")
    return value


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_paths(repo_root: Path, paths: set[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative_path in sorted(paths):
        path = repo_root / relative_path
        if not path.is_file():
            raise ProtocolError(f"protocol artifact is missing: {relative_path}")
        hashes[relative_path] = _file_sha256(path)
    return hashes


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _parent_manifest(document: dict[str, Any] | None = None) -> dict[str, Any]:
    parent = parent_protocol.validate_manifest(document or _load_json(DEFAULT_PARENT_MANIFEST))
    if parent_protocol.manifest_sha256(parent) != PARENT_CANONICAL_SHA256:
        raise ProtocolError("parent runtime manifest canonical SHA-256 drifted")
    return parent


def _model_source(document: dict[str, Any] | None = None) -> dict[str, Any]:
    if _file_sha256(DEFAULT_MODEL_SOURCE) != parent_protocol.MODEL_SOURCE_SHA256:
        raise ProtocolError("formal timeout model source SHA-256 drifted")
    source = document or _load_json(DEFAULT_MODEL_SOURCE)
    if source.get("schema_version") != "formal-collection-4.5.0-timeout-calibration":
        raise ProtocolError("formal timeout model source identity drifted")
    return source


def _formal_cases(parent: dict[str, Any], source: dict[str, Any]) -> list[dict[str, Any]]:
    source_by_id = {case["id"]: case for case in source.get("cases", [])}
    result: list[dict[str, Any]] = []
    for repair_case in parent["cases"]:
        case = source_by_id.get(repair_case["id"])
        if not isinstance(case, dict):
            raise ProtocolError(f"formal case is missing: {repair_case['id']}")
        artifact = case["oracle"]["required_artifacts"][0]
        expected_artifact = repair_case["artifact_oracle"]["required_artifacts"][0]
        if (
            case["repository_url"] != repair_case["repository_url"]
            or case["commit_sha"] != repair_case["commit"]
            or case["build_system"] != repair_case["build_system"]
            or artifact["relative_path"] != expected_artifact["staged_relative_path"]
            or artifact["artifact_type"] != expected_artifact["artifact_type"]
        ):
            raise ProtocolError(f"formal case drifted: {repair_case['id']}")
        result.append(copy.deepcopy(case))
    return result


def _conditions() -> list[dict[str, Any]]:
    return [
        {
            "id": condition_id,
            "model_profile": provider,
            "provider_condition": provider,
            "treatment": treatment,
            "memory_enabled": False,
            "skills_enabled": False,
            "repetitions": 1,
            "acceptance_gate": "clean_replay",
        }
        for (provider, treatment), condition_id in CONDITION_IDS.items()
    ]


def _collection_plan(parent: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            **copy.deepcopy(slot),
            "condition_id": CONDITION_IDS[(slot["provider_condition"], slot["treatment"])],
        }
        for slot in parent["pilot_schedule"]
    ]


def _authorization(parent: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "forge-verifier-driven-repair-pilot-authorized",
        "status": "authorized_six_complete_pairs",
        "authorized_by": "experiment_owner",
        "authorized_on": "2026-08-14",
        "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/127",
        "implementation_baseline_commit": BASELINE_COMMIT,
        "parent_runtime": {
            "id": parent["benchmark"]["id"],
            "path": "benchmarks/manifests/cpp-verifier-repair-pilot-runtime-candidate.json",
            "canonical_sha256": PARENT_CANONICAL_SHA256,
        },
        "network_observation": {
            "access_medium_reconfirmation_required_before_canary": True,
            "browser_ui_required": False,
        },
        "budget_confirmation": {
            "confirmed": True,
            "expected_recorded_tokens": EXPECTED_RECORDED_TOKENS,
            "maximum_recorded_tokens": RECORDED_TOKEN_LIMIT,
            "enforcement": "check_before_each_complete_pair",
            "complete_started_pair_before_next_boundary_check": True,
        },
        "collection_constraints": {
            "authorized_slot_count": 12,
            "authorized_complete_pairs": 6,
            "provider_canary_required_before_first_ledger": True,
            "provider_canary_max_attempts": 1,
            "provider_canary_requests_per_provider": 1,
            "empty_evidence_required_before_canary": True,
            "zero_residual_formal_containers_required_before_canary": True,
            "replacement_forbidden": True,
            "fallback_forbidden": True,
            "retry_forbidden": True,
            "backfill_forbidden": True,
            "p_value_forbidden": True,
            "model_ranking_forbidden": True,
            "evidence_directory": EVIDENCE_DIRECTORY,
        },
    }


def generate_manifest(
    repo_root: Path = REPOSITORY_ROOT,
    *,
    parent: dict[str, Any] | None = None,
    model_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parent = _parent_manifest(parent)
    source = _model_source(model_source)
    plan = _collection_plan(parent)
    forge = copy.deepcopy(source["forge"])
    forge["commit_sha"] = BASELINE_COMMIT
    forge["revision_policy"] = REVISION_POLICY
    budget = copy.deepcopy(parent["budget"])
    budget["authorized"] = True
    return {
        "$schema": "../schemas/forge-verifier-repair-pilot-authorized-v1.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": "forge_verifier_repair_pilot_authorization",
        "benchmark": {
            "id": "forge-verifier-driven-repair-pilot-authorized",
            "name": "Forge C/C++ verifier-driven repair paired pilot",
            "purpose": "execute six bounded baseline-versus-repair pairs",
        },
        "scope": {
            "languages": ["C", "C++"],
            "phase": "verifier_driven_repair_pilot",
            "formal_comparison_enabled": False,
            "collection_authorized": True,
            "instrumentation_blocker": False,
        },
        "authorization": _authorization(parent),
        "forge": forge,
        "protocol_artifact_sha256": _hash_paths(repo_root, PROTOCOL_ARTIFACT_PATHS),
        "prompt_sha256": copy.deepcopy(source["prompt_sha256"]),
        "model_profiles": copy.deepcopy(parent["model_profiles"]),
        "runtime": copy.deepcopy(source["runtime"]),
        "attempt_budget": copy.deepcopy(source["attempt_budget"]),
        "resource_preflight": copy.deepcopy(source["resource_preflight"]),
        "budget": budget,
        "conditions": _conditions(),
        "collection_plan": plan,
        "schedule_sha256": hashlib.sha256(canonical_json_bytes(plan)).hexdigest(),
        "cases": _formal_cases(parent, source),
        "pilot_schedule": copy.deepcopy(parent["pilot_schedule"]),
        "repair_packet": copy.deepcopy(parent["repair_packet"]),
        "fidelity_gate": copy.deepcopy(parent["fidelity_gate"]),
        "outcomes": copy.deepcopy(parent["outcomes"]),
        "analysis_plan": {
            "descriptive_only": True,
            "complete_pairs_required": 6,
            "repair_conversion_definition": "adjacent_actionable_classification_to_passed_feedback",
            "model_request_count_event": "model.request_started",
            "submit_attempt_count_event": "submit.started",
            "clean_replay_attempt_count_event": "replay.started",
            "wall_clock_definition": "experiment_started_to_experiment_completed_ledger_time",
            "p_value_computed": False,
            "model_ranking_performed": False,
        },
    }


def validate_manifest(
    document: Any,
    repo_root: Path = REPOSITORY_ROOT,
    *,
    parent: dict[str, Any] | None = None,
    model_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ProtocolError("authorized manifest must be an object")
    expected = generate_manifest(repo_root, parent=parent, model_source=model_source)
    if document != expected:
        raise ProtocolError("authorized manifest does not match the frozen protocol")
    plan = document["collection_plan"]
    if len(plan) != 12 or len({slot["pair_id"] for slot in plan}) != 6 or [slot["order"] for slot in plan] != list(range(1, 13)):
        raise ProtocolError("authorized schedule must contain 12 ordered slots and 6 pairs")
    for pair_id in {slot["pair_id"] for slot in plan}:
        arms = {slot["treatment"] for slot in plan if slot["pair_id"] == pair_id}
        if arms != {BASELINE_ARM, TREATMENT_ARM}:
            raise ProtocolError("each authorized pair must contain both arms")
    return document


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()


def schema_document() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-verifier-repair-pilot-authorized-v1.schema.json",
        "title": "Forge verifier-driven repair pilot authorization",
        "const": generate_manifest(),
    }


def verify_frozen_components(manifest: dict[str, Any], repo_root: Path = REPOSITORY_ROOT) -> None:
    validate_manifest(manifest, repo_root)
    parent_path = repo_root / manifest["authorization"]["parent_runtime"]["path"]
    parent = _parent_manifest(_load_json(parent_path))
    if parent_protocol.manifest_sha256(parent) != PARENT_CANONICAL_SHA256:
        raise ProtocolError("authorized parent runtime no longer matches")
    for relative_path, expected in manifest["forge"]["component_sha256"].items():
        if _file_sha256(repo_root / relative_path) != expected:
            raise ProtocolError(f"frozen Forge component drifted: {relative_path}")
    for relative_path, expected in manifest["protocol_artifact_sha256"].items():
        if _file_sha256(repo_root / relative_path) != expected:
            raise ProtocolError(f"protocol artifact drifted: {relative_path}")
    for relative_path, expected in manifest["prompt_sha256"].items():
        if _file_sha256(repo_root / relative_path) != expected:
            raise ProtocolError(f"frozen prompt drifted: {relative_path}")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    generate.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    validate = subparsers.add_parser("validate-manifest")
    validate.add_argument("manifest", type=Path, nargs="?", default=DEFAULT_MANIFEST)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "generate":
            manifest = generate_manifest()
            _write_json(args.manifest, manifest)
            _write_json(args.schema, schema_document())
        else:
            manifest = validate_manifest(_load_json(args.manifest))
            verify_frozen_components(manifest)
    except (OSError, ProtocolError, parent_protocol.ProtocolError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "authorized_complete_pairs": 6,
                "authorized_slots": 12,
                "collection_authorized": True,
                "manifest_sha256": manifest_sha256(manifest),
                "maximum_recorded_tokens": RECORDED_TOKEN_LIMIT,
                "status": "valid",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
