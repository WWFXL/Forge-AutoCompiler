#!/usr/bin/env python3
"""封存 Stage C v4，并生成/校验 v5 Session identity 修复身份。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_stage_c_protocol as base  # noqa: E402
import forge_stage_c_task_qualification as qualification  # noqa: E402

SCHEMA_VERSION = "forge-stage-c-paired-calibration-v5-session-identity-authorized-1.0.0"
DOCUMENT_TYPE = "forge_stage_c_paired_calibration_v5_session_identity_authorized"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/327"
AUTHORIZATION_BASELINE_COMMIT = "9c271ea1d3b3b9dcec8e6aecbd16eab949b2a72b"
V4_MANIFEST_PATH = (
    "benchmarks/manifests/"
    "cpp-stage-c-paired-calibration-v4-build-entrypoint-authorized.json"
)
V4_PROTOCOL_PATH = "scripts/forge_stage_c_v4_protocol.py"
V4_FAILURE_AUDIT_PATH = (
    "benchmarks/reports/cpp-stage-c-paired-calibration-v4-failed.json"
)
V4_FAILURE_REPORT_PATH = (
    "benchmarks/reports/cpp-stage-c-paired-calibration-v4-failed.md"
)
PREREGISTRATION_PATH = (
    "benchmarks/preregistrations/cpp-stage-c-paired-calibration-v5-session-identity.md"
)
PROTOCOL_PATH = "scripts/forge_stage_c_v5_protocol.py"
RUNNER_PATH = "scripts/forge_stage_c_runner.py"
MANIFEST_RELATIVE_PATH = (
    "benchmarks/manifests/"
    "cpp-stage-c-paired-calibration-v5-session-identity-authorized.json"
)
SCHEMA_RELATIVE_PATH = (
    "benchmarks/schemas/"
    "forge-stage-c-paired-calibration-v5-session-identity-authorized.schema.json"
)
V4_EVIDENCE_DIRECTORY = (
    "/workspace/.compile-sessions/"
    "benchmark-evidence-stage-c-paired-calibration-v4-build-entrypoint"
)
DEFAULT_EVIDENCE_DIRECTORY = (
    "/workspace/.compile-sessions/"
    "benchmark-evidence-stage-c-paired-calibration-v5-session-identity"
)
DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_RELATIVE_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_RELATIVE_PATH

V4_MANIFEST_FILE_SHA256 = (
    "c0f2b3d0d77edda77f8951328590d225aae961508bc043aefcb29978d54251c6"
)
V4_MANIFEST_SHA256 = "46d1f2f95a14042f035fb908d3f5460672d560ae26eabcaa66f823a5594b8189"
V4_PROTOCOL_SHA256 = "8b203302239d2af409b525336fcd8cc56d6da1ff9bf000e96c94ce85bf661dca"
V4_RUNNER_SHA256 = "e47385c79dd0709823c66f7f982a4cc4bf9bab5b387eabbf369cb96ddb715d03"
V4_RELEASE_REVISION = "9c271ea1d3b3b9dcec8e6aecbd16eab949b2a72b"
V4_REACHABILITY_TOKENS = 73
V4_FORMAL_ATTEMPTS = 5
V4_FORMAL_REQUESTS = 30
V4_FORMAL_TOKENS = 213_301
V4_EVIDENCE_FILE_COUNT = 887
V4_EVIDENCE_TOTAL_SIZE_BYTES = 7_190_319
PRIOR_ACTUAL_RECORDED_TOKENS = 286_143
V5_TOTAL_MAX_RECORDED_TOKENS = 14_405_000

canonical_sha256 = base.canonical_sha256
file_sha256 = base.file_sha256


class StageCV5ProtocolError(RuntimeError):
    """Stage C v4 审计或 v5 授权身份无效。"""


def _load_v4_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    path = repo_root / V4_MANIFEST_PATH
    value = qualification.load_json(path)
    if (
        file_sha256(path) != V4_MANIFEST_FILE_SHA256
        or canonical_sha256(value) != V4_MANIFEST_SHA256
        or file_sha256(repo_root / V4_PROTOCOL_PATH) != V4_PROTOCOL_SHA256
    ):
        raise StageCV5ProtocolError("Stage C v4 identity 漂移")
    return value


def _file_inventory(root: Path) -> dict[str, Any]:
    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return {
        "file_count": len(files),
        "total_size_bytes": sum(item["size_bytes"] for item in files),
        "files": files,
    }


def _zero_managed_resources() -> bool:
    containers = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    images = subprocess.run(
        ["docker", "images", "-q", "--filter", "label=forge.stage-c.managed=true"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return not images and not any(
        name.startswith("forge-stage-c-") for name in containers
    )


def capture_v4_failure_audit(
    evidence_directory: Path = Path(V4_EVIDENCE_DIRECTORY),
    repo_root: Path = REPO_ROOT,
    output_root: Path | None = None,
) -> dict[str, Any]:
    _load_v4_manifest(repo_root)
    if not evidence_directory.is_dir():
        raise StageCV5ProtocolError("Stage C v4 evidence 目录不存在")

    reachability = qualification.load_json(
        evidence_directory / "reports/reachability.json"
    )
    batch_marker = qualification.load_json(evidence_directory / "markers/batch.json")
    completed_pair_paths = sorted(evidence_directory.glob("pairs/*/pair.json"))
    completed_pair_ids = [path.parent.name for path in completed_pair_paths]
    expected_completed = ["stage-c-v4-json-c-r1", "stage-c-v4-stockfish-11-r1"]
    incomplete_pair = "stage-c-v4-rnnoise-0.1.1-r1"
    if (
        completed_pair_ids != expected_completed
        or batch_marker.get("status") != "started"
        or batch_marker.get("manifest_sha256") != V4_MANIFEST_SHA256
        or reachability.get("passed") is not True
        or reachability.get("request_count") != 1
        or reachability.get("recorded_tokens") != V4_REACHABILITY_TOKENS
        or reachability.get("manifest_sha256") != V4_MANIFEST_SHA256
    ):
        raise StageCV5ProtocolError("Stage C v4 evidence 前缀无效")

    arm_paths = [
        "pairs/stage-c-v4-json-c-r1/A",
        "pairs/stage-c-v4-json-c-r1/B",
        "pairs/stage-c-v4-stockfish-11-r1/A",
        "pairs/stage-c-v4-stockfish-11-r1/B",
        f"pairs/{incomplete_pair}/A",
    ]
    arms = []
    for relative in arm_paths:
        arm_dir = evidence_directory / relative
        attempt_path = arm_dir / "attempt.json"
        result_path = arm_dir / "result.json"
        attempt = qualification.load_json(attempt_path)
        result = qualification.load_json(result_path)
        if (
            attempt.get("manifest_sha256") != V4_MANIFEST_SHA256
            or result.get("manifest_sha256") != V4_MANIFEST_SHA256
            or result.get("cleanup_succeeded") is not True
            or result.get("zero_managed_resources") is not True
        ):
            raise StageCV5ProtocolError(f"Stage C v4 arm evidence 无效: {relative}")
        arms.append(
            {
                "pair_id": result["pair_id"],
                "task_id": result["task_id"],
                "arm": result["arm"],
                "attempt_id": result["attempt_id"],
                "model_requests": result["model_requests"],
                "recorded_tokens": result["recorded_tokens"],
                "strict_reproducible_build_success": result[
                    "strict_reproducible_build_success"
                ],
                "error_class": result["error_class"],
                "attempt_sha256": file_sha256(attempt_path),
                "result_sha256": file_sha256(result_path),
            }
        )

    peer_dir = evidence_directory / f"pairs/{incomplete_pair}/B"
    if (peer_dir / "attempt.json").exists() or (peer_dir / "result.json").exists():
        raise StageCV5ProtocolError("Stage C v4 rnnoise B 不应存在正式 evidence")
    formal_requests = sum(arm["model_requests"] for arm in arms)
    formal_tokens = sum(arm["recorded_tokens"] for arm in arms)
    if (
        len(arms) != V4_FORMAL_ATTEMPTS
        or formal_requests != V4_FORMAL_REQUESTS
        or formal_tokens != V4_FORMAL_TOKENS
    ):
        raise StageCV5ProtocolError("Stage C v4 usage 复算不一致")

    inventory = _file_inventory(evidence_directory)
    if (
        inventory["file_count"] != V4_EVIDENCE_FILE_COUNT
        or inventory["total_size_bytes"] != V4_EVIDENCE_TOTAL_SIZE_BYTES
    ):
        raise StageCV5ProtocolError("Stage C v4 evidence inventory 漂移")
    audit = {
        "schema_version": "forge-stage-c-paired-calibration-v4-failed-audit-1.0.0",
        "document_type": "forge_stage_c_paired_calibration_v4_failed_audit",
        "classification": "unsafe_forge_thread_identity_after_first_arm_closed",
        "identity": {
            "manifest_file_sha256": V4_MANIFEST_FILE_SHA256,
            "manifest_sha256": V4_MANIFEST_SHA256,
            "protocol_sha256": V4_PROTOCOL_SHA256,
            "runner_sha256": V4_RUNNER_SHA256,
            "release_revision": V4_RELEASE_REVISION,
        },
        "evidence_directory": V4_EVIDENCE_DIRECTORY,
        "reachability": {
            "request_count": 1,
            "recorded_tokens": V4_REACHABILITY_TOKENS,
            "marker_sha256": file_sha256(
                evidence_directory / "markers/reachability.json"
            ),
            "report_sha256": file_sha256(
                evidence_directory / "reports/reachability.json"
            ),
        },
        "completed_prefix": {
            "pair_count": 2,
            "pair_ids": expected_completed,
            "pair_result_sha256": {
                path.parent.name: file_sha256(path) for path in completed_pair_paths
            },
        },
        "formal_arms": arms,
        "incomplete_pair": {
            "pair_id": incomplete_pair,
            "task_id": "rnnoise-0.1.1",
            "closed_arm": "A",
            "unregistered_arm": "B",
            "unregistered_arm_attempt_exists": False,
            "unregistered_arm_result_exists": False,
            "phase": "forge_session_creation_before_b_attempt_marker",
            "error_class": "ValueError",
            "error_message": (
                "Compile thread and session identifiers must be safe path components"
            ),
            "root_cause": "pair_id_dot_was_copied_into_compile_thread_id",
        },
        "usage": {
            "formal_arm_attempts": V4_FORMAL_ATTEMPTS,
            "formal_arm_model_requests": formal_requests,
            "formal_arm_recorded_tokens": formal_tokens,
            "provider_calls_including_reachability": formal_requests + 1,
            "recorded_tokens_including_reachability": (
                formal_tokens + V4_REACHABILITY_TOKENS
            ),
        },
        "batch": {
            "marker_sha256": file_sha256(evidence_directory / "markers/batch.json"),
            "status": "started",
            "complete_pair_count": 2,
            "incomplete_pair_count": 1,
            "must_not_resume": True,
        },
        "resource_audit": {"zero_managed_resources": _zero_managed_resources()},
        "evidence_inventory": inventory,
        "interpretation": {
            "stockfish_nested_build_entrypoint_fix_confirmed": True,
            "historical_outcomes_imported": False,
            "v4_identity_closed": True,
            "v5_requires_fresh_pair_attempt_and_session_identities": True,
        },
    }
    if audit["resource_audit"]["zero_managed_resources"] is not True:
        raise StageCV5ProtocolError("Stage C v4 存在 managed resource 残留")
    destination_root = output_root or repo_root
    path = destination_root / V4_FAILURE_AUDIT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path = destination_root / V4_FAILURE_REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "# Stage C v4 失败审计\n\n"
        f"v4 `{V4_MANIFEST_SHA256}` 在 `{V4_RELEASE_REVISION}` 上运行。"
        "唯一 reachability 通过，消耗 1 request / 73 recorded tokens。\n\n"
        "`json-c` 与 `stockfish-11` 的 replicate 1 pair 完整闭合；"
        "Stockfish 的 `src/Makefile` 已被正确识别。"
        "`rnnoise-0.1.1` A 臂闭合后，B 臂在 attempt 登记前创建 Compile Session 失败："
        "pair ID 中的点号被直接复制进 thread ID，不符合安全路径组件合同。\n\n"
        "v4 共形成 5 个正式 arm attempt、31 次 Provider 调用（含 reachability）和 "
        "213,374 recorded tokens。evidence 包含 887 个文件、7,190,319 bytes；"
        "停止后无 managed resource 残留。v4 必须永久停止，v5 不导入任何 v4 outcome。\n",
        encoding="utf-8",
    )
    return audit


def _validate_v4_failure_audit(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    path = repo_root / V4_FAILURE_AUDIT_PATH
    value = qualification.load_json(path)
    expected_usage = {
        "formal_arm_attempts": V4_FORMAL_ATTEMPTS,
        "formal_arm_model_requests": V4_FORMAL_REQUESTS,
        "formal_arm_recorded_tokens": V4_FORMAL_TOKENS,
        "provider_calls_including_reachability": 31,
        "recorded_tokens_including_reachability": 213_374,
    }
    if (
        value.get("schema_version")
        != "forge-stage-c-paired-calibration-v4-failed-audit-1.0.0"
        or value.get("classification")
        != "unsafe_forge_thread_identity_after_first_arm_closed"
        or value.get("identity", {}).get("manifest_sha256") != V4_MANIFEST_SHA256
        or value.get("identity", {}).get("release_revision") != V4_RELEASE_REVISION
        or value.get("usage") != expected_usage
        or value.get("batch", {}).get("must_not_resume") is not True
        or value.get("completed_prefix", {}).get("pair_count") != 2
        or value.get("incomplete_pair", {}).get("pair_id")
        != "stage-c-v4-rnnoise-0.1.1-r1"
        or value.get("incomplete_pair", {}).get("unregistered_arm_attempt_exists")
        is not False
        or value.get("resource_audit", {}).get("zero_managed_resources") is not True
        or value.get("interpretation", {}).get("historical_outcomes_imported")
        is not False
    ):
        raise StageCV5ProtocolError("Stage C v4 失败审计语义无效")
    inventory = value.get("evidence_inventory", {})
    files = inventory.get("files")
    if (
        not isinstance(files, list)
        or inventory.get("file_count") != V4_EVIDENCE_FILE_COUNT
        or len(files) != V4_EVIDENCE_FILE_COUNT
        or inventory.get("total_size_bytes") != V4_EVIDENCE_TOTAL_SIZE_BYTES
        or len({item.get("path") for item in files if isinstance(item, dict)})
        != V4_EVIDENCE_FILE_COUNT
    ):
        raise StageCV5ProtocolError("Stage C v4 evidence inventory 无效")
    return value


def _v5_schedule(schedule: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(schedule)
    value["pairs"] = []
    for pair in schedule["pairs"]:
        updated = copy.deepcopy(pair)
        pair_id = f"stage-c-v5-{pair['task_id']}-r{pair['replicate']}"
        updated["pair_id"] = pair_id
        updated["attempt_ids"] = {arm: f"{pair_id}-{arm.lower()}" for arm in ("A", "B")}
        value["pairs"].append(updated)
    value["forge_thread_identity"] = "sha256_full_pair_id_plus_manifest_prefix"
    value["session_identity_preflight_pair_count"] = 24
    value["v4_outcomes_imported"] = False
    return value


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    prior = _validate_v4_failure_audit(repo_root)
    manifest = copy.deepcopy(_load_v4_manifest(repo_root))
    preregistration = repo_root / PREREGISTRATION_PATH
    if not preregistration.is_file():
        raise StageCV5ProtocolError("Stage C v5 预注册不存在")

    manifest["$schema"] = (
        "../schemas/"
        "forge-stage-c-paired-calibration-v5-session-identity-authorized.schema.json"
    )
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["document_type"] = DOCUMENT_TYPE
    manifest["issue_url"] = ISSUE_URL
    manifest["purpose"] = "stage_c_controlled_paired_calibration_v5_session_identity"
    manifest["schedule"] = _v5_schedule(manifest["schedule"])
    manifest["analysis"]["v4_outcomes_imported"] = False
    manifest["authorization"]["prior_actual_recorded_tokens"] = (
        PRIOR_ACTUAL_RECORDED_TOKENS
    )
    manifest["authorization"]["cumulative_max_recorded_tokens"] = (
        PRIOR_ACTUAL_RECORDED_TOKENS + V5_TOTAL_MAX_RECORDED_TOKENS
    )
    manifest["execution"].update(
        {
            "authorization_baseline_commit": AUTHORIZATION_BASELINE_COMMIT,
            "evidence_directory": DEFAULT_EVIDENCE_DIRECTORY,
            "forge_thread_identity": "sha256_full_pair_id_plus_manifest_prefix",
            "session_identity_preflight_pair_count": 24,
            "v4_evidence_imported": False,
        }
    )
    manifest["preregistration"] = {
        "path": PREREGISTRATION_PATH,
        "file_sha256": file_sha256(preregistration),
    }
    manifest["prior_failed_identity"] = {
        "audit_path": V4_FAILURE_AUDIT_PATH,
        "audit_file_sha256": file_sha256(repo_root / V4_FAILURE_AUDIT_PATH),
        "audit_canonical_sha256": canonical_sha256(prior),
        "manifest_path": V4_MANIFEST_PATH,
        "manifest_file_sha256": V4_MANIFEST_FILE_SHA256,
        "manifest_sha256": V4_MANIFEST_SHA256,
        "release_revision": V4_RELEASE_REVISION,
        "evidence_directory": V4_EVIDENCE_DIRECTORY,
        "must_not_resume": True,
        "historical_outcomes_imported": False,
    }
    frozen = manifest["frozen_components"]
    frozen.pop(RUNNER_PATH, None)
    for relative in (
        V4_MANIFEST_PATH,
        V4_PROTOCOL_PATH,
        V4_FAILURE_AUDIT_PATH,
        V4_FAILURE_REPORT_PATH,
        PREREGISTRATION_PATH,
        PROTOCOL_PATH,
        RUNNER_PATH,
    ):
        frozen[relative] = file_sha256(repo_root / relative)
    return manifest


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": (
            "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/"
            "forge-stage-c-paired-calibration-v5-session-identity-authorized.schema.json"
        ),
        "title": "Forge Stage C paired calibration v5 session identity authorized",
        "const": manifest,
    }


def validate_manifest(
    value: dict[str, Any],
    repo_root: Path = REPO_ROOT,
    *,
    check_schema_file: bool = True,
) -> dict[str, Any]:
    expected = generate_manifest(repo_root)
    if value != expected:
        raise StageCV5ProtocolError("Stage C v5 manifest 与确定性生成结果不一致")
    schedule = value["schedule"]
    if (
        len(schedule["pairs"]) != 24
        or any(
            not pair["pair_id"].startswith("stage-c-v5-") for pair in schedule["pairs"]
        )
        or schedule.get("forge_thread_identity")
        != "sha256_full_pair_id_plus_manifest_prefix"
        or schedule.get("session_identity_preflight_pair_count") != 24
        or schedule.get("v4_outcomes_imported") is not False
        or schedule.get("retry") is not False
        or schedule.get("replacement") is not False
        or schedule.get("backfill") is not False
    ):
        raise StageCV5ProtocolError("Stage C v5 schedule 边界无效")
    schema = generate_schema(expected)
    jsonschema.Draft202012Validator.check_schema(schema)
    if check_schema_file:
        if (
            not DEFAULT_SCHEMA.is_file()
            or qualification.load_json(DEFAULT_SCHEMA) != schema
        ):
            raise StageCV5ProtocolError("Stage C v5 const Schema 缺失或漂移")
        jsonschema.validate(value, qualification.load_json(DEFAULT_SCHEMA))
    return value


def load_manifest(
    path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    return validate_manifest(qualification.load_json(path), repo_root)


def release_revision(repo_root: Path = REPO_ROOT) -> str:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    ancestor = subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            AUTHORIZATION_BASELINE_COMMIT,
            revision,
        ],
        cwd=repo_root,
        check=False,
    )
    if ancestor.returncode != 0:
        raise StageCV5ProtocolError(
            "当前 release 不是 Stage C v5 authorization baseline 的后代"
        )
    return revision


def write_generated(manifest: dict[str, Any]) -> None:
    DEFAULT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_SCHEMA.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    DEFAULT_SCHEMA.write_text(
        json.dumps(
            generate_schema(manifest), ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("capture-v4-audit", "generate", "validate", "show-schedule"),
    )
    parser.add_argument(
        "--evidence-directory",
        type=Path,
        default=Path(V4_EVIDENCE_DIRECTORY),
    )
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    if args.command == "capture-v4-audit":
        result: Any = capture_v4_failure_audit(
            args.evidence_directory, output_root=args.output_root
        )
    elif args.command == "generate":
        manifest = generate_manifest()
        write_generated(manifest)
        result = {
            "status": "generated",
            "manifest_sha256": canonical_sha256(manifest),
            "pair_count": 24,
            "physical_attempt_count": 48,
        }
    else:
        manifest = load_manifest()
        if args.command == "validate":
            result = {
                "status": "valid",
                "manifest_sha256": canonical_sha256(manifest),
                "release_revision": release_revision(),
                "provider_calls": 0,
                "formal_stage_c_attempts": 0,
                "model_tokens": 0,
            }
        else:
            result = manifest["schedule"]
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
