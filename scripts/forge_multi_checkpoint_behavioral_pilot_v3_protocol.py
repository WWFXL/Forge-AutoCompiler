#!/usr/bin/env python3
"""Issue #170 多 checkpoint behavioral pilot v3 的未授权冻结协议。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-verifier-multi-checkpoint-behavioral-pilot-v3.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-multi-checkpoint-behavioral-pilot-v3.schema.json"
CASE_MANIFEST_PATH = "benchmarks/manifests/cpp-verifier-multi-checkpoint-zero-provider-gate.json"

SCHEMA_VERSION = "forge-multi-checkpoint-behavioral-pilot-3.0.0"
DOCUMENT_TYPE = "forge_multi_checkpoint_behavioral_pilot"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/170"
AUTHORIZATION_BASELINE = "24a79228e3b6e5b49d7101666d16a3479c6b9e52"
CASE_IDS = ("cppitertools", "janet", "libcheck")
RECORDED_TOKENS_PER_ARM = 120_000
PAIR_COUNT = len(CASE_IDS) * 2
RECORDED_TOKEN_LIMIT = PAIR_COUNT * 2 * RECORDED_TOKENS_PER_ARM

FROZEN_COMPONENT_PATHS = {
    "benchmarks/manifests/cpp-verifier-checkpoint-behavioral-pilot-v2.json",
    "benchmarks/manifests/cpp-verifier-multi-checkpoint-zero-provider-gate.json",
    "benchmarks/schemas/forge-checkpoint-behavioral-pilot-v2.schema.json",
    "benchmarks/schemas/forge-multi-checkpoint-zero-provider-gate.schema.json",
    "scripts/forge_checkpoint_behavioral_pilot_v2_protocol.py",
    "scripts/forge_checkpoint_behavioral_pilot_v2_runner.py",
    "scripts/forge_multi_checkpoint_zero_provider_gate.py",
}


class ProtocolError(RuntimeError):
    """v3 协议、case identity 或授权边界无效。"""


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


def _load_case_gate(repo_root: Path = REPO_ROOT):
    path = repo_root / "scripts/forge_multi_checkpoint_zero_provider_gate.py"
    name = "forge_multi_checkpoint_zero_provider_gate_v3_dependency"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ProtocolError("cannot load zero-provider case gate")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _case_manifest(repo_root: Path = REPO_ROOT) -> tuple[dict[str, Any], Any]:
    gate = _load_case_gate(repo_root)
    manifest = gate.load_manifest(repo_root / CASE_MANIFEST_PATH)
    gate.verify_historical_components(manifest, repo_root)
    if tuple(case.case_id for case in gate.cases(manifest)) != CASE_IDS:
        raise ProtocolError("zero-provider case set drifted")
    return manifest, gate


def _schedule() -> list[dict[str, Any]]:
    schedule: list[dict[str, Any]] = []
    order = 1
    for case_id in CASE_IDS:
        for case_pair_index, arm_order in enumerate((("baseline", "treatment"), ("treatment", "baseline")), start=1):
            schedule.append(
                {
                    "pair_id": f"v3-{case_id}-pair-{case_pair_index:02d}",
                    "order": order,
                    "case_id": case_id,
                    "case_pair_index": case_pair_index,
                    "arm_order": list(arm_order),
                }
            )
            order += 1
    return schedule


def _hash_paths(repo_root: Path, paths: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative_path in sorted(paths):
        path = repo_root / relative_path
        if not path.is_file():
            raise ProtocolError(f"frozen component missing: {relative_path}")
        result[relative_path] = file_sha256(path)
    return result


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    case_manifest, _gate = _case_manifest(repo_root)
    schedule = _schedule()
    return {
        "$schema": "../schemas/forge-multi-checkpoint-behavioral-pilot-v3.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "authorization": {
            "issue_url": ISSUE_URL,
            "protocol_freeze_authorized": True,
            "provider_calls_authorized": False,
            "formal_attempts_authorized": False,
            "model_tokens_authorized": 0,
            "pilot_collection_authorized": False,
        },
        "scope": {
            "languages": ["C", "C++"],
            "mechanism": "failure_checkpoint",
            "controlled_fault": "artifact_staging_missing",
            "build_systems": ["cmake", "make", "autotools"],
            "natural_collection_authorized": False,
            "secondary_provider_authorized": False,
        },
        "case_source": {
            "manifest_path": CASE_MANIFEST_PATH,
            "schema_version": case_manifest["schema_version"],
            "canonical_sha256": canonical_sha256(case_manifest),
            "file_sha256": file_sha256(repo_root / CASE_MANIFEST_PATH),
            "case_ids": list(CASE_IDS),
        },
        "provider": {
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
            "recorded_tokens_per_arm": RECORDED_TOKENS_PER_ARM,
            "recorded_tokens_per_pair": RECORDED_TOKENS_PER_ARM * 2,
            "stage_maximum_recorded_tokens": RECORDED_TOKEN_LIMIT,
            "expected_recorded_tokens_planning_only": 231_944,
            "reachability_requests": 0,
            "enforcement": "after_each_arm_and_pair_before_next_pair",
        },
        "terminal_taxonomy": {
            "infrastructure": ["valid", "endpoint_censored", "invalid"],
            "model_behavior": [
                "completed",
                "graph_step_limit",
                "work_wall_clock_limit",
                "no_submit",
                "verification_failed",
                "not_observed",
            ],
            "verification_outcome": ["passed", "failed", "not_attempted"],
        },
        "stopping": {
            "classified_arm_outcome_continues_other_arm": True,
            "endpoint_timeout_censors_arm_and_continues": True,
            "model_behavior_failure_is_outcome": True,
            "identity_evidence_budget_cleanup_or_unclassified_failure_stops_batch": True,
            "retry_forbidden": True,
            "replacement_forbidden": True,
            "backfill_forbidden": True,
            "schedule_extension_forbidden": True,
        },
        "analysis": {
            "descriptive_only": True,
            "unit_of_analysis": "failure_checkpoint_case",
            "per_case_outputs": ["paired_four_cell", "requests", "recorded_tokens", "failure_transitions"],
            "cross_case_summary": "equal_weight_macro_average",
            "case_weights": {case_id: "1/3" for case_id in CASE_IDS},
            "pairs_pooled_as_independent_contexts": False,
            "providers_pooled": False,
            "p_value_computed": False,
            "model_ranking_performed": False,
            "historical_pairs_pooled": False,
        },
        "execution": {
            "mode": "protocol_plan_only",
            "control_plane": "compose-dood-on-ubuntu-native-docker",
            "evidence_directory": "/workspace/.compile-sessions/benchmark-evidence-multi-checkpoint-behavioral-pilot-v3",
            "pair_directory_pattern": "pairs/v3-CASE-pair-NN",
            "release_branch": "main",
            "authorization_baseline_commit": AUTHORIZATION_BASELINE,
            "release_revision_policy": "descendant-compatible",
            "require_clean_worktree": True,
            "require_origin_main_identity": True,
            "require_zero_managed_containers_between_pairs": True,
        },
        "frozen_components": _hash_paths(repo_root, FROZEN_COMPONENT_PATHS),
    }


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError("manifest must be an object")
    expected = generate_manifest(repo_root)
    if value != expected:
        raise ProtocolError("multi-checkpoint behavioral v3 manifest drifted")
    return value


def verify_frozen_components(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> None:
    validate_manifest(manifest, repo_root)
    if manifest["frozen_components"] != _hash_paths(repo_root, FROZEN_COMPONENT_PATHS):
        raise ProtocolError("frozen component identity drifted")


def load_manifest(path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError("cannot read multi-checkpoint behavioral v3 manifest") from exc
    return validate_manifest(value, repo_root)


def case_definitions(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    validate_manifest(manifest, repo_root)
    case_manifest, gate = _case_manifest(repo_root)
    return {case.case_id: case for case in gate.cases(case_manifest)}


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    frozen = manifest or generate_manifest()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-multi-checkpoint-behavioral-pilot-v3.schema.json",
        "title": "Forge multi-checkpoint behavioral pilot v3 protocol",
        "const": frozen,
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate", "show-schedule"))
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
        verify_frozen_components(manifest)
    result: Any = (
        manifest["schedule"]
        if args.command == "show-schedule"
        else {
            "manifest_sha256": canonical_sha256(manifest),
            "pairs": len(manifest["schedule"]),
            "provider_calls": 0,
            "formal_attempts": 0,
            "model_tokens": 0,
        }
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
