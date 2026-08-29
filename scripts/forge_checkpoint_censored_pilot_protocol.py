#!/usr/bin/env python3
"""Issue #159 endpoint 删失容忍 checkpoint 六配对 pilot 协议。"""

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
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-checkpoint-censored-pilot-v1.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks" / "schemas" / "forge-checkpoint-censored-pilot-v1.schema.json"
DEFAULT_OUTPUT_DIR = Path("/workspace/.compile-sessions/benchmark-evidence-checkpoint-censored-pilot-v1")
PARENT_OUTPUT_DIR = Path("/workspace/.compile-sessions/benchmark-evidence-checkpoint-primary-canary-amendment")

SCHEMA_VERSION = "forge-checkpoint-censored-pilot-1.0.0"
DOCUMENT_TYPE = "forge_checkpoint_censored_pilot"
AUTHORIZATION_BASELINE = "fe9fb519eb831e0795ef31f93cec0fb971a80fdf"
PAIR_COUNT = 6
RECORDED_TOKENS_PER_ARM = 120_000
RECORDED_TOKEN_LIMIT = PAIR_COUNT * 2 * RECORDED_TOKENS_PER_ARM

PARENT_COMPONENTS = {
    "benchmarks/manifests/cpp-verifier-checkpoint-primary-canary-amendment-authorized.json": ("fb483a55542adf4be1d213a2130d87b11e783df9d6e5270ed7aa1573d88c7776"),
    "scripts/forge_checkpoint_primary_canary.py": ("031bac753459a060e134df765a27eaa1c8fca0ac784f239d46e243f89c8b3282"),
    "scripts/forge_checkpoint_primary_canary_amendment_authorized.py": ("89cce741bf56c234b9e31560a5662cd701cc6fab4f948858ca187ed64141f5ba"),
    "scripts/forge_checkpoint_windows_build_layout.py": ("df757d63ad493393957b1fb167dd5b01d5e9c1ae1d76796cca26d616b77355e5"),
}

PARENT_EVIDENCE = {
    "checkpoint/coordinator.sqlite": ("dc2b426ceff514683ccec719fb064158b7bc58b3f5f01d1fc620571d6fb13956"),
    "checkpoint/messages.sqlite": ("3091ebbe147af151ed9ad37aff3a5d14979bc187a0d69a685a72e8de3b6e14bb"),
    "checkpoint/messages.sqlite-shm": ("fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb"),
    "checkpoint/messages.sqlite-wal": ("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    "ledgers/baseline.jsonl": ("01137d096b55c447655946373afe517135f01306aaf54797aad700dfb69aece2"),
    "ledgers/parent.jsonl": ("683c68dc1f2626915c9a7a722db11701dbef667a8fac3d187acf22c269644891"),
    "markers/amendment-controlled-pair-attempt.json": ("0d7526bcd7c9af3d3d3349964d2df4cdf15c1503f53fd705c2fcbda16fe00cc0"),
    "markers/amendment-reachability-attempt.json": ("51212cbfc00b887f2540343bef156d0e3b1bd680f760a65debcf2eddeee5fa23"),
    "reports/reachability.json": ("ff664651aacea073cb8541594c1d443cd92654fe2c9d9767227788dd10adeb48"),
}

PROTOCOL_ARTIFACT_PATHS = {
    "scripts/forge_checkpoint_censored_pilot_protocol.py",
    "scripts/forge_checkpoint_censored_pilot_runner.py",
    "backend/tests/test_forge_checkpoint_censored_pilot.py",
    "benchmarks/preregistrations/cpp-verifier-checkpoint-censored-pilot-v1.md",
}


class ProtocolError(RuntimeError):
    """协议、冻结组件或历史 evidence 发生漂移。"""


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


def _hash_protocol_artifacts(repo_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative_path in sorted(PROTOCOL_ARTIFACT_PATHS):
        path = repo_root / relative_path
        if not path.is_file():
            raise ProtocolError(f"协议制品缺失: {relative_path}")
        result[relative_path] = file_sha256(path)
    return result


def _schedule() -> list[dict[str, Any]]:
    schedule: list[dict[str, Any]] = []
    for number in range(1, PAIR_COUNT + 1):
        arm_order = ["baseline", "treatment"] if number % 2 == 1 else ["treatment", "baseline"]
        schedule.append(
            {
                "pair_id": f"pair-{number:02d}",
                "order": number,
                "arm_order": arm_order,
            }
        )
    return schedule


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    schedule = _schedule()
    return {
        "$schema": "../schemas/forge-checkpoint-censored-pilot-v1.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "authorization": {
            "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/159",
            "authorized_by": "experiment_owner",
            "route": "B",
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
            "enforcement": "after_each_pair_before_next_pair",
        },
        "stopping": {
            "endpoint_timeout_censors_pair_and_continues": True,
            "cleanup_or_identity_failure_stops_batch": True,
            "non_endpoint_failure_stops_batch": True,
            "retry_forbidden": True,
            "replacement_forbidden": True,
            "backfill_forbidden": True,
            "schedule_extension_forbidden": True,
        },
        "analysis": {
            "itt_attrition_includes_all_scheduled_pairs": True,
            "conditional_mechanism_requires_complete_pair": True,
            "descriptive_only": True,
            "p_value_computed": False,
            "model_ranking_performed": False,
        },
        "execution": {
            "control_plane": "compose-dood-on-ubuntu-native-docker",
            "network_access_medium_env": "FORGE_NETWORK_ACCESS_MEDIUM",
            "network_access_medium": "wifi",
            "evidence_directory": str(DEFAULT_OUTPUT_DIR),
            "pair_directory_pattern": "pairs/pair-NN",
            "batch_marker": "markers/pilot-attempt.json",
            "pair_marker": "markers/pair-attempt.json",
            "release_branch": "main",
            "authorization_baseline_commit": AUTHORIZATION_BASELINE,
            "release_revision_policy": "descendant-compatible",
            "require_clean_worktree": True,
            "require_origin_main_identity": True,
            "require_zero_managed_containers_between_pairs": True,
        },
        "parent": {
            "authorized_manifest_canonical_sha256": ("f87dc3e0af2ec8c841191c70195808ac5e686656d15f00c479f6d030abebf356"),
            "components": dict(sorted(PARENT_COMPONENTS.items())),
            "terminal_evidence": {
                "directory": str(PARENT_OUTPUT_DIR),
                "expected_file_count": len(PARENT_EVIDENCE),
                "files": dict(sorted(PARENT_EVIDENCE.items())),
                "sqlite_sidecars_retained": True,
            },
        },
        "protocol_artifacts": _hash_protocol_artifacts(repo_root),
    }


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError("pilot manifest 必须是对象")
    expected = generate_manifest(repo_root)
    if value != expected:
        raise ProtocolError("pilot manifest 与冻结协议不一致")
    schedule = value["schedule"]
    if len(schedule) != PAIR_COUNT:
        raise ProtocolError("pilot schedule 必须包含 6 个 pair")
    if [item["order"] for item in schedule] != list(range(1, PAIR_COUNT + 1)):
        raise ProtocolError("pilot schedule order 不连续")
    first_arms = [item["arm_order"][0] for item in schedule]
    if first_arms != ["baseline", "treatment"] * 3:
        raise ProtocolError("pilot arm order 未交叉平衡")
    return value


def verify_frozen_components(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> None:
    validate_manifest(manifest, repo_root)
    for relative_path, expected in manifest["parent"]["components"].items():
        path = repo_root / relative_path
        if not path.is_file() or file_sha256(path) != expected:
            raise ProtocolError(f"冻结父组件发生漂移: {relative_path}")
    for relative_path, expected in manifest["protocol_artifacts"].items():
        path = repo_root / relative_path
        if not path.is_file() or file_sha256(path) != expected:
            raise ProtocolError(f"pilot 协议制品发生漂移: {relative_path}")


def verify_parent_evidence(manifest: dict[str, Any], output_dir: Path = PARENT_OUTPUT_DIR) -> dict[str, Any]:
    terminal = manifest["parent"]["terminal_evidence"]
    expected = terminal["files"]
    actual_paths = {path.relative_to(output_dir).as_posix() for path in output_dir.rglob("*") if path.is_file()}
    if actual_paths != set(expected):
        raise ProtocolError("Issue #155 冻结 evidence 文件集合发生漂移")
    for relative_path, digest in expected.items():
        if file_sha256(output_dir / relative_path) != digest:
            raise ProtocolError(f"Issue #155 冻结 evidence SHA-256 发生漂移: {relative_path}")
    return {
        "status": "valid",
        "file_count": len(actual_paths),
        "sqlite_sidecars_retained": terminal["sqlite_sidecars_retained"],
    }


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": ("https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-checkpoint-censored-pilot-v1.schema.json"),
        "title": "Forge endpoint-censored checkpoint pilot",
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate", "validate-evidence"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--parent-output-dir", type=Path, default=PARENT_OUTPUT_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
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
                verify_parent_evidence(manifest, args.parent_output_dir)
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
