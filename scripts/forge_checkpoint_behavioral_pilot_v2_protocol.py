#!/usr/bin/env python3
"""Issue #165 checkpoint 行为终态 v2 六配对实验协议。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", SCRIPT_ROOT.parent)).resolve()
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-checkpoint-behavioral-pilot-v2.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks" / "schemas" / "forge-checkpoint-behavioral-pilot-v2.schema.json"
DEFAULT_OUTPUT_DIR = Path("/workspace/.compile-sessions/benchmark-evidence-checkpoint-behavioral-pilot-v2")
V1_OUTPUT_DIR = Path("/workspace/.compile-sessions/benchmark-evidence-checkpoint-censored-pilot-v1")
RECOVERY_OUTPUT_DIR = Path("/workspace/.compile-sessions/benchmark-evidence-checkpoint-censored-pilot-recovery-v1")

SCHEMA_VERSION = "forge-checkpoint-behavioral-pilot-2.0.0"
DOCUMENT_TYPE = "forge_checkpoint_behavioral_pilot"
AUTHORIZATION_BASELINE = "3bc211219e1d458ebdad2d02274c58c209e99113"
PAIR_COUNT = 6
RECORDED_TOKENS_PER_ARM = 120_000
RECORDED_TOKEN_LIMIT = PAIR_COUNT * 2 * RECORDED_TOKENS_PER_ARM

PARENT_COMPONENT_PATHS = {
    "benchmarks/manifests/cpp-verifier-checkpoint-primary-canary-amendment-authorized.json",
    "scripts/forge_checkpoint_primary_canary.py",
    "scripts/forge_checkpoint_primary_canary_amendment_authorized.py",
    "scripts/forge_checkpoint_windows_build_layout.py",
    "scripts/forge_checkpoint_censored_pilot_runner.py",
    "scripts/forge_checkpoint_censored_pilot_recovery_runner.py",
}

PROTOCOL_ARTIFACT_PATHS = {
    "scripts/forge_checkpoint_behavioral_pilot_v2_protocol.py",
    "scripts/forge_checkpoint_behavioral_pilot_v2_runner.py",
    "backend/tests/test_forge_checkpoint_behavioral_pilot_v2.py",
    "backend/tests/test_forge_checkpoint_behavioral_pilot_v2_docker.py",
    "benchmarks/preregistrations/cpp-verifier-checkpoint-behavioral-pilot-v2.md",
}

V1_EVIDENCE = {
    "markers/pilot-attempt.json": "90637cef19d2859c3067c6b1b982d8b91c180a94b20d999a5349948c68023575",
    "pairs/pair-01/checkpoint/coordinator.sqlite": "304288805942f5b210c82e06d421a6264edc344b7ff15066ddb6a91456c89a7c",
    "pairs/pair-01/checkpoint/messages.sqlite": "7a16adf27013d6e6f76a4c11c43f179ea63436f8dfec253359a4644feca633e9",
    "pairs/pair-01/ledgers/baseline.jsonl": "717755fa47d5f585282a76b4767454b8fe446c39f453375dc8f6bb6d38375aea",
    "pairs/pair-01/ledgers/parent.jsonl": "858097dfa4ce93815e304f14974a799e35d15d5286293470e22c8686bebf738d",
    "pairs/pair-01/ledgers/treatment.jsonl": "c504c61b3a492d00740d3abbf3cb19a457a6599a5212602b4d1f1f0c612ab840",
    "pairs/pair-01/markers/pair-attempt.json": "8178d32c61f4ed4425aa5dfa0ad155ba86fcf9626ef1b31bfe0eee1492f5de5d",
    "pairs/pair-01/reports/controlled-pair.json": "afad25b4c41ae3098b7feb4711d8f4f746f856a9e9773052c13b05a6054471f4",
}

RECOVERY_EVIDENCE = {
    "imports/pair-01.json": "4efffb5c899b716e5b1a066c8cc71a67befa4c4a1fa6696bc3d07df39202fef7",
    "markers/recovery-attempt.json": "f673ced8588a585aaa83f0bd4e180da63c96d873f7a48493f6dd9453f6c0a1a1",
    "pairs/pair-02/checkpoint/coordinator.sqlite": "01a72d5a13e33ee23a76b5943063e3cbd6f8b0fc4b2f0cbcc1dee688cf5eb380",
    "pairs/pair-02/checkpoint/messages.sqlite": "ac0f8c958c9839ed357508e26be4935d3e17188386e5db3d24aee6a23890297c",
    "pairs/pair-02/ledgers/baseline.jsonl": "9f4c713adb772576ac413bf65ea780fdaa31195d2066dea8755d27093935ddd5",
    "pairs/pair-02/ledgers/parent.jsonl": "dd5085ad7595e2eae19209a91b31b92845d304233fafb5f9a89507bd10183dd5",
    "pairs/pair-02/ledgers/treatment.jsonl": "27e7f71ebc13984e75238a9d072ed2db24c3e1cc6246d856b833104363087084",
    "pairs/pair-02/markers/pair-attempt.json": "ca74fa29c5a3a7e310ccc49a4bfe72b9c7a4d37033f74acca53ed5cca704144b",
}


class ProtocolError(RuntimeError):
    """协议、组件或历史 evidence 发生漂移。"""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_paths(repo_root: Path, paths: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative_path in sorted(paths):
        path = repo_root / relative_path
        if not path.is_file():
            raise ProtocolError(f"协议制品缺失: {relative_path}")
        result[relative_path] = file_sha256(path)
    return result


def _schedule() -> list[dict[str, Any]]:
    return [
        {
            "pair_id": f"v2-pair-{number:02d}",
            "order": number,
            "arm_order": ["baseline", "treatment"] if number % 2 == 1 else ["treatment", "baseline"],
        }
        for number in range(1, PAIR_COUNT + 1)
    ]


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    schedule = _schedule()
    return {
        "$schema": "../schemas/forge-checkpoint-behavioral-pilot-v2.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "authorization": {
            "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/165",
            "decision_issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/163",
            "selected_option": "A",
            "authorized_by": "experiment_owner",
            "pilot_collection_authorized": True,
            "authorized_pairs": PAIR_COUNT,
            "maximum_recorded_tokens": RECORDED_TOKEN_LIMIT,
        },
        "scope": {
            "languages": ["C", "C++"],
            "mechanism": "failure_checkpoint",
            "controlled_fault": "artifact_staging_missing",
            "natural_collection_authorized": False,
            "secondary_provider_authorized": False,
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
            "itt_attrition_includes_all_scheduled_pairs": True,
            "primary_mechanism_requires_both_arms_attempted_and_infrastructure_valid": True,
            "repair_conversion_outcome": "candidate_verification_and_clean_replay_passed",
            "efficiency_metrics_are_conditionally_descriptive": True,
            "descriptive_only": True,
            "p_value_computed": False,
            "model_ranking_performed": False,
            "historical_pairs_pooled": False,
        },
        "execution": {
            "control_plane": "compose-dood-on-ubuntu-native-docker",
            "network_access_medium_env": "FORGE_NETWORK_ACCESS_MEDIUM",
            "network_access_medium": "wifi",
            "evidence_directory": str(DEFAULT_OUTPUT_DIR),
            "pair_directory_pattern": "pairs/v2-pair-NN",
            "batch_marker": "markers/v2-pilot-attempt.json",
            "pair_marker": "markers/pair-attempt.json",
            "release_branch": "main",
            "authorization_baseline_commit": AUTHORIZATION_BASELINE,
            "release_revision_policy": "descendant-compatible",
            "require_clean_worktree": True,
            "require_origin_main_identity": True,
            "require_zero_managed_containers_between_pairs": True,
        },
        "historical_exclusion": {
            "v1_manifest_sha256": "d5edd9683def7c8842ad1eb0471cce877b47b52b2939f1b45d9c2a51f2362391",
            "recovery_manifest_sha256": "4e26976373bd02937a55703081794bcb45c4e9d07f6eec27931a368a32174d89",
            "recorded_tokens": 67_121,
            "pair_ids": ["v1:pair-01", "recovery:pair-02"],
            "role": "exploratory_feasibility_only",
            "pooled_into_v2": False,
            "v1_evidence": {
                "directory": str(V1_OUTPUT_DIR),
                "files": dict(sorted(V1_EVIDENCE.items())),
            },
            "recovery_evidence": {
                "directory": str(RECOVERY_OUTPUT_DIR),
                "files": dict(sorted(RECOVERY_EVIDENCE.items())),
            },
        },
        "parent_components": _hash_paths(repo_root, PARENT_COMPONENT_PATHS),
        "protocol_artifacts": _hash_paths(repo_root, PROTOCOL_ARTIFACT_PATHS),
    }


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if not isinstance(value, dict) or value != generate_manifest(repo_root):
        raise ProtocolError("v2 manifest 与冻结协议不一致")
    first_arms = [item["arm_order"][0] for item in value["schedule"]]
    if first_arms != ["baseline", "treatment"] * 3:
        raise ProtocolError("v2 arm order 未交叉平衡")
    return value


def verify_frozen_components(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> None:
    validate_manifest(manifest, repo_root)
    for group in ("parent_components", "protocol_artifacts"):
        for relative_path, expected in manifest[group].items():
            path = repo_root / relative_path
            if not path.is_file() or file_sha256(path) != expected:
                raise ProtocolError(f"v2 冻结组件发生漂移: {relative_path}")


def _verify_evidence_set(output_dir: Path, expected: dict[str, str], label: str) -> None:
    actual = {path.relative_to(output_dir).as_posix() for path in output_dir.rglob("*") if path.is_file()}
    if actual != set(expected):
        raise ProtocolError(f"{label} 历史 evidence 文件集合发生漂移")
    for relative_path, digest in expected.items():
        if file_sha256(output_dir / relative_path) != digest:
            raise ProtocolError(f"{label} 历史 evidence 哈希发生漂移: {relative_path}")


def verify_historical_evidence(
    manifest: dict[str, Any],
    v1_output_dir: Path = V1_OUTPUT_DIR,
    recovery_output_dir: Path = RECOVERY_OUTPUT_DIR,
) -> dict[str, Any]:
    validate_manifest(manifest)
    exclusion = manifest["historical_exclusion"]
    _verify_evidence_set(v1_output_dir, exclusion["v1_evidence"]["files"], "v1")
    _verify_evidence_set(recovery_output_dir, exclusion["recovery_evidence"]["files"], "recovery")
    return {
        "status": "valid",
        "excluded_pairs": 2,
        "recorded_tokens": exclusion["recorded_tokens"],
    }


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-checkpoint-behavioral-pilot-v2.schema.json",
        "title": "Forge checkpoint behavioral outcome pilot v2",
        "const": manifest or generate_manifest(),
    }


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ProtocolError(f"JSON 根节点必须是对象: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate", "validate-evidence"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            manifest = generate_manifest()
            _write_json(args.manifest, manifest)
            _write_json(args.schema, schema_document(manifest))
            status = "generated"
        else:
            manifest = validate_manifest(_load_json(args.manifest))
            verify_frozen_components(manifest)
            if args.command == "validate-evidence":
                verify_historical_evidence(manifest)
            status = "valid"
    except (OSError, ProtocolError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": status,
                "manifest_sha256": canonical_sha256(manifest),
                "authorized_pairs": PAIR_COUNT,
                "maximum_recorded_tokens": RECORDED_TOKEN_LIMIT,
                "provider_calls": 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
