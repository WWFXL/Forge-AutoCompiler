#!/usr/bin/env python3
"""生成并校验 failure checkpoint primary canary amendment 候选。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", SCRIPT_ROOT.parent)).resolve()
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-checkpoint-primary-canary-amendment-candidate.json"
PARENT_MANIFEST = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-checkpoint-primary-canary-authorized.json"

SCHEMA_VERSION = "forge-checkpoint-primary-canary-amendment-candidate-1.0.0"
DOCUMENT_TYPE = "forge_checkpoint_primary_canary_amendment_candidate"
PARENT_MANIFEST_SHA256 = "2771e72eee45ca6eac7bc1e7d5040cf5633bb3bf7e24a186a44071d9a98ce579"
PARENT_RELEASE_REVISION = "1ae32b501db4f4e1c35cec84b93e02267239b051"
IMPLEMENTATION_BASELINE = "c7217e201bb1cb35217482e184fb1d51ec5d8d18"
SUPERSEDED_EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-checkpoint-primary-canary"
AMENDMENT_EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-checkpoint-primary-canary-amendment"
REACHABILITY_MARKER = "amendment-reachability-attempt.json"
PAIR_MARKER = "amendment-controlled-pair-attempt.json"

SUPERSEDED_FILES = {
    "ledgers/parent.jsonl": "1f6378867058261d6849436fe8077fdbb33ce74b82bd960f4045aa945b79dcf4",
    "markers/controlled-pair-attempt.json": "93160bddd375dfc6574bf8294876a75f0052a6bf96a22b38d5b174a607bcccf8",
    "markers/reachability-attempt.json": "d9aa041027140bae3473977ae66a570dc743e207d184cf20e6914846108890ac",
    "reports/reachability.json": "5eac49ff35e868fc3d307d9cf4ea5accc5cfa365858fdcc771aa1bd4df33ab14",
}
PROTOCOL_ARTIFACT_PATHS = (
    "scripts/forge_checkpoint_windows_build_layout.py",
    "benchmarks/preregistrations/cpp-verifier-checkpoint-primary-canary-amendment.md",
)


class AmendmentError(RuntimeError):
    """候选协议、父协议或旧 evidence 发生漂移。"""


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AmendmentError(f"无法加载协议模块: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AmendmentError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise AmendmentError(f"JSON 根节点必须是对象: {path}")
    return value


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _protocol_artifacts(repo_root: Path) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for relative_path in PROTOCOL_ARTIFACT_PATHS:
        path = repo_root / relative_path
        if not path.is_file():
            raise AmendmentError(f"候选协议文件缺失: {relative_path}")
        artifacts.append({"path": relative_path, "sha256": file_sha256(path)})
    return artifacts


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "scope": {
            "provider_canary_authorized": False,
            "mechanism_canary_authorized": False,
            "pilot_collection_authorized": False,
            "natural_collection_authorized": False,
            "secondary_provider_authorized": False,
            "provider_calls": 0,
            "formal_physical_attempts": 0,
            "model_tokens": 0,
        },
        "parent": {
            "manifest_path": "benchmarks/manifests/cpp-verifier-checkpoint-primary-canary-authorized.json",
            "manifest_sha256": PARENT_MANIFEST_SHA256,
            "release_revision": PARENT_RELEASE_REVISION,
            "terminal_evidence": {
                "directory": SUPERSEDED_EVIDENCE_DIRECTORY,
                "expected_file_count": len(SUPERSEDED_FILES),
                "files": [{"path": path, "sha256": digest} for path, digest in SUPERSEDED_FILES.items()],
                "reachability": {
                    "status": "passed",
                    "actual_model": "deepseek-v4-flash",
                    "request_count": 1,
                    "recorded_tokens": 17,
                },
                "controlled_pair": {
                    "status": "failed",
                    "error_class": "CanaryError",
                    "arm_ledger_count": 0,
                    "pair_report_count": 0,
                    "pair_provider_calls": 0,
                    "pair_model_tokens": 0,
                },
                "reuse_policy": "forbidden_new_manifest_and_revision_required",
            },
        },
        "amendment": {
            "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/153",
            "implementation_baseline_commit": IMPLEMENTATION_BASELINE,
            "reachability_policy": "new_request_required_after_separate_authorization",
            "build_layout": {
                "adapter_path": "scripts/forge_checkpoint_windows_build_layout.py",
                "cmake_binary_dir": ".forge-cmake-build",
                "build_output": ".forge-cmake-build/accumulate_examples",
            },
            "provider": {
                "id": "deepseek-v4-flash",
                "endpoint": "https://api.deepseek.com",
                "credential_env": "DEEPSEEK_API_KEY",
                "model": "deepseek-v4-flash",
                "request_timeout_seconds": 300,
                "max_retries": 0,
                "fallback": "forbidden",
            },
            "fault": {
                "version": "controlled-fault-v1",
                "family": "artifact_staging_missing",
                "expected_classification": "candidate_verification_failed",
                "capture_point": "after-neutral-tool-message-before-continuation",
                "replay_attempts_required": 0,
            },
            "continuation": {
                "checkpoint_pairs": 1,
                "arms_per_pair": 2,
                "arm_order": ["baseline", "treatment"],
                "maximum_requests_per_arm": 8,
                "maximum_model_turns_per_arm": 8,
                "maximum_graph_steps_per_arm": 24,
                "work_wall_clock_seconds_per_arm": 600,
                "cleanup_reserve_seconds_per_arm": 120,
                "maximum_recorded_tokens_per_arm": 120000,
            },
            "budget": {
                "reachability_requests": 1,
                "reachability_expected_tokens": 5000,
                "reachability_maximum_tokens": 5000,
                "mechanism_canary_expected_tokens": 120000,
                "mechanism_canary_maximum_tokens": 240000,
                "stage_expected_tokens": 125000,
                "stage_maximum_tokens": 245000,
            },
            "stopping": {
                "provider_timeout_stops_canary": True,
                "incomplete_pair_stops_canary": True,
                "cleanup_or_identity_failure_stops_canary": True,
                "retry_forbidden": True,
                "replacement_forbidden": True,
                "backfill_forbidden": True,
                "canary_pass_does_not_authorize_pilot": True,
            },
            "execution": {
                "control_plane": "compose-dood-on-ubuntu-native-docker",
                "network_access_medium_env": "FORGE_NETWORK_ACCESS_MEDIUM",
                "evidence_directory": AMENDMENT_EVIDENCE_DIRECTORY,
                "reachability_marker": REACHABILITY_MARKER,
                "controlled_pair_marker": PAIR_MARKER,
                "release_branch": "main",
                "require_clean_worktree": True,
                "require_origin_main_identity": True,
            },
        },
        "protocol_artifacts": _protocol_artifacts(repo_root),
    }


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AmendmentError("amendment candidate manifest 必须是对象")
    expected = generate_manifest(repo_root)
    if value != expected:
        raise AmendmentError("amendment candidate manifest 与冻结候选协议不一致")
    return value


def _parent_modules() -> tuple[ModuleType, ModuleType]:
    primary = _load_module("forge_checkpoint_primary_canary_amendment_parent", SCRIPT_ROOT / "forge_checkpoint_primary_canary.py")
    layout = _load_module("forge_checkpoint_primary_canary_amendment_layout", SCRIPT_ROOT / "forge_checkpoint_windows_build_layout.py")
    return primary, layout


def verify_frozen_components(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> None:
    validate_manifest(manifest, repo_root)
    primary, layout = _parent_modules()
    parent = primary.load_manifest(repo_root / manifest["parent"]["manifest_path"])
    if primary.canonical_sha256(parent) != PARENT_MANIFEST_SHA256:
        raise AmendmentError("父授权 manifest identity 发生漂移")
    primary.verify_frozen_artifacts(parent, repo_root)
    build_layout = manifest["amendment"]["build_layout"]
    if layout.CMAKE_BINARY_DIR != build_layout["cmake_binary_dir"] or layout.BUILD_OUTPUT_RELATIVE_PATH != build_layout["build_output"]:
        raise AmendmentError("Windows bind build-layout adapter 发生漂移")


def _assert_fields(value: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    if any(value.get(key) != expected_value for key, expected_value in expected.items()):
        raise AmendmentError(f"旧 {label} 语义发生漂移")


def verify_superseded_evidence(manifest: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    validate_manifest(manifest)
    terminal = manifest["parent"]["terminal_evidence"]
    files = {path.relative_to(output_dir).as_posix(): path for path in output_dir.rglob("*") if path.is_file()}
    expected_files = {item["path"]: item["sha256"] for item in terminal["files"]}
    if set(files) != set(expected_files) or len(files) != terminal["expected_file_count"]:
        raise AmendmentError("旧 evidence 文件集合发生漂移")
    for relative_path, expected_digest in expected_files.items():
        if file_sha256(files[relative_path]) != expected_digest:
            raise AmendmentError(f"旧 evidence SHA-256 发生漂移: {relative_path}")

    reachability_marker = _load_json(output_dir / "markers" / "reachability-attempt.json")
    pair_marker = _load_json(output_dir / "markers" / "controlled-pair-attempt.json")
    reachability_report = _load_json(output_dir / "reports" / "reachability.json")
    marker_identity = {"manifest_sha256": PARENT_MANIFEST_SHA256, "release_revision": PARENT_RELEASE_REVISION}
    _assert_fields(reachability_marker, {**marker_identity, "status": "passed", "error_class": None}, "reachability marker")
    _assert_fields(pair_marker, {**marker_identity, "status": "failed", "error_class": "CanaryError"}, "controlled pair marker")
    _assert_fields(
        reachability_report,
        {
            **marker_identity,
            "passed": True,
            "actual_model": terminal["reachability"]["actual_model"],
            "request_count": terminal["reachability"]["request_count"],
            "recorded_tokens": terminal["reachability"]["recorded_tokens"],
        },
        "reachability report",
    )
    return {"status": "valid", "file_count": len(files), "manifest_sha256": PARENT_MANIFEST_SHA256}


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    evidence = subparsers.add_parser("validate-evidence")
    evidence.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    evidence.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "generate":
            manifest = generate_manifest()
            _write_json(args.manifest, manifest)
            result = {"status": "generated", "manifest_sha256": canonical_sha256(manifest)}
        else:
            manifest = validate_manifest(_load_json(args.manifest))
            verify_frozen_components(manifest)
            result = {
                "status": "valid",
                "provider_canary_authorized": False,
                "mechanism_canary_authorized": False,
                "stage_maximum_tokens": manifest["amendment"]["budget"]["stage_maximum_tokens"],
                "manifest_sha256": canonical_sha256(manifest),
            }
            if args.command == "validate-evidence":
                result["superseded_evidence"] = verify_superseded_evidence(manifest, args.output_dir)
    except (AmendmentError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
