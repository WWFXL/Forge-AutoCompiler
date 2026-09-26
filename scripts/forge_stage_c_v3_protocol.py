#!/usr/bin/env python3
"""生成并校验 Stage C v3 pair 源码与产物验证修复后的授权执行身份。"""

from __future__ import annotations

import argparse
import copy
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

SCHEMA_VERSION = "forge-stage-c-paired-calibration-v3-pair-source-authorized-1.0.0"
DOCUMENT_TYPE = "forge_stage_c_paired_calibration_v3_pair_source_authorized"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/323"
AUTHORIZATION_BASELINE_COMMIT = "b947846580be9db20cc8b5c3c41b89b1eb4212e6"
MANIFEST_RELATIVE_PATH = (
    "benchmarks/manifests/cpp-stage-c-paired-calibration-v3-pair-source-authorized.json"
)
SCHEMA_RELATIVE_PATH = "benchmarks/schemas/forge-stage-c-paired-calibration-v3-pair-source-authorized.schema.json"
PREREGISTRATION_PATH = (
    "benchmarks/preregistrations/cpp-stage-c-paired-calibration-v3-pair-source.md"
)
V2_PREREGISTRATION_PATH = (
    "benchmarks/preregistrations/cpp-stage-c-paired-calibration-v2-remediation.md"
)
V2_MANIFEST_PATH = (
    "benchmarks/manifests/cpp-stage-c-paired-calibration-v2-remediation-authorized.json"
)
V2_PROTOCOL_PATH = "scripts/forge_stage_c_remediation_protocol.py"
V2_FAILURE_AUDIT_PATH = (
    "benchmarks/reports/cpp-stage-c-paired-calibration-v2-failed.json"
)
V2_FAILURE_REPORT_PATH = (
    "benchmarks/reports/cpp-stage-c-paired-calibration-v2-failed.md"
)
PROTOCOL_PATH = "scripts/forge_stage_c_v3_protocol.py"
RUNNER_PATH = "scripts/forge_stage_c_runner.py"
DEFAULT_EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-stage-c-paired-calibration-v3-pair-source"
DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_RELATIVE_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_RELATIVE_PATH

canonical_bytes = base.canonical_bytes
canonical_sha256 = base.canonical_sha256
file_sha256 = base.file_sha256


class StageCV3ProtocolError(RuntimeError):
    """Stage C v3 manifest、v2 来源审计或授权边界无效。"""


def _validate_v2_failure_audit(repo_root: Path) -> dict[str, Any]:
    path = repo_root / V2_FAILURE_AUDIT_PATH
    value = qualification.load_json(path)
    expected_identity = {
        "manifest_file_sha256": "1b62360ef7fa2d5828d79924276b2c277026190ce926f870bdce62e530f9fd1e",
        "manifest_sha256": "5a479832a2a6f9bdc49407a35b3ccc997547365fa65273d19fda4d1b4516eee4",
        "release_revision": "b947846580be9db20cc8b5c3c41b89b1eb4212e6",
        "runner_sha256": "b1fea8f2d9bc5c1eacf39c6b18ce1a074c767026bed4ba4683c297c3ea1704ef",
    }
    if (
        value.get("schema_version")
        != "forge-stage-c-paired-calibration-v2-failed-audit-1.0.0"
        or value.get("document_type")
        != "forge_stage_c_paired_calibration_v2_failed_audit"
        or value.get("classification")
        != "closed_controlled_arm_then_peer_source_acquisition_interrupted_before_registration"
        or value.get("identity") != expected_identity
        or value.get("usage")
        != {
            "formal_arm_attempts": 1,
            "formal_arm_model_requests": 4,
            "formal_arm_recorded_tokens": 41861,
            "provider_calls_including_reachability": 5,
            "recorded_tokens_including_reachability": 41931,
        }
        or value.get("batch", {}).get("must_not_resume") is not True
        or value.get("resource_audit", {}).get("zero_managed_resources") is not True
        or value.get("interpretation", {}).get("historical_outcomes_imported")
        is not False
        or value.get("closed_arm", {}).get("error_class")
        != "method_error:FileNotFoundError"
        or value.get("closed_arm", {}).get("outcome_matches_result") is not True
        or value.get("unregistered_arm", {}).get("attempt_exists") is not False
        or value.get("unregistered_arm", {}).get("result_exists") is not False
    ):
        raise StageCV3ProtocolError("Stage C v2 失败审计语义无效")
    if (
        file_sha256(repo_root / V2_MANIFEST_PATH)
        != expected_identity["manifest_file_sha256"]
    ):
        raise StageCV3ProtocolError("Stage C v2 manifest 文件哈希漂移")
    inventory = value.get("evidence_inventory", {})
    files = inventory.get("files")
    if (
        not isinstance(files, list)
        or inventory.get("file_count") != 425
        or len(files) != 425
        or inventory.get("total_size_bytes") != 2_155_758
    ):
        raise StageCV3ProtocolError("Stage C v2 evidence inventory 不完整")
    paths = [item.get("path") for item in files if isinstance(item, dict)]
    if len(paths) != 425 or len(set(paths)) != 425:
        raise StageCV3ProtocolError("Stage C v2 evidence inventory 路径无效")
    required = {
        "markers/batch.json": value["batch"]["marker_sha256"],
        "markers/reachability.json": value["reachability"]["marker_sha256"],
        "reports/reachability.json": value["reachability"]["report_sha256"],
        "pairs/stage-c-v2-json-c-r1/A/attempt.json": value["closed_arm"][
            "attempt_sha256"
        ],
        "pairs/stage-c-v2-json-c-r1/A/result.json": value["closed_arm"][
            "result_sha256"
        ],
        "pairs/stage-c-v2-json-c-r1/A/method/outcome.json": value["closed_arm"][
            "method_outcome_sha256"
        ],
        "pairs/stage-c-v2-json-c-r1/A/method/events.jsonl": value["closed_arm"][
            "method_events_sha256"
        ],
    }
    file_hashes = {item["path"]: item["sha256"] for item in files}
    if any(file_hashes.get(path) != digest for path, digest in required.items()):
        raise StageCV3ProtocolError("Stage C v2 关键 evidence 哈希漂移")
    return value


def _remediation_schedule(schedule: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(schedule)
    pairs = []
    for pair in value["pairs"]:
        updated = copy.deepcopy(pair)
        pair_id = f"stage-c-v3-{pair['task_id']}-r{pair['replicate']}"
        updated["pair_id"] = pair_id
        updated["attempt_ids"] = {arm: f"{pair_id}-{arm.lower()}" for arm in ("A", "B")}
        pairs.append(updated)
    value["pairs"] = pairs
    value.pop("source_preparation_retry_before_attempt", None)
    value["pair_source_preparation_before_attempts"] = True
    value["pair_source_acquisition_count"] = 1
    value["v1_outcomes_imported"] = False
    value["v2_outcomes_imported"] = False
    return value


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    audit = _validate_v2_failure_audit(repo_root)
    manifest = qualification.load_json(repo_root / V2_MANIFEST_PATH)
    preregistration = repo_root / PREREGISTRATION_PATH
    if not preregistration.is_file():
        raise StageCV3ProtocolError("Stage C v3 预注册不存在")

    manifest["$schema"] = (
        "../schemas/forge-stage-c-paired-calibration-v3-pair-source-authorized.schema.json"
    )
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["document_type"] = DOCUMENT_TYPE
    manifest["issue_url"] = ISSUE_URL
    manifest["purpose"] = "stage_c_controlled_paired_calibration_v3_pair_source"
    manifest["schedule"] = _remediation_schedule(manifest["schedule"])
    manifest["analysis"]["v1_outcomes_imported"] = False
    manifest["analysis"]["v2_outcomes_imported"] = False
    manifest["authorization"].pop("prior_reachability_recorded_tokens", None)
    manifest["authorization"]["prior_actual_recorded_tokens"] = 42_001
    manifest["authorization"]["cumulative_max_recorded_tokens"] = 14_447_001
    manifest["execution"].update(
        {
            "authorization_baseline_commit": AUTHORIZATION_BASELINE_COMMIT,
            "evidence_directory": DEFAULT_EVIDENCE_DIRECTORY,
            "source_preparation_boundary": "before_first_pair_arm_attempt_marker",
            "pair_source_acquisition_count": 1,
            "v1_evidence_imported": False,
            "v2_evidence_imported": False,
        }
    )
    manifest["preregistration"] = {
        "path": PREREGISTRATION_PATH,
        "file_sha256": file_sha256(preregistration),
    }
    manifest["prior_failed_identity"] = {
        "audit_path": V2_FAILURE_AUDIT_PATH,
        "audit_file_sha256": file_sha256(repo_root / V2_FAILURE_AUDIT_PATH),
        "audit_canonical_sha256": canonical_sha256(audit),
        "manifest_path": V2_MANIFEST_PATH,
        "manifest_file_sha256": audit["identity"]["manifest_file_sha256"],
        "manifest_sha256": audit["identity"]["manifest_sha256"],
        "release_revision": audit["identity"]["release_revision"],
        "evidence_directory": audit["evidence_directory"],
        "must_not_resume": True,
        "historical_outcomes_imported": False,
    }
    frozen = manifest["frozen_components"]
    frozen.pop(V2_PREREGISTRATION_PATH, None)
    frozen.pop(V2_PROTOCOL_PATH, None)
    frozen.pop(RUNNER_PATH, None)
    for relative in (
        PREREGISTRATION_PATH,
        V2_PREREGISTRATION_PATH,
        V2_MANIFEST_PATH,
        V2_PROTOCOL_PATH,
        V2_FAILURE_AUDIT_PATH,
        V2_FAILURE_REPORT_PATH,
        PROTOCOL_PATH,
        RUNNER_PATH,
    ):
        frozen[relative] = file_sha256(repo_root / relative)
    return manifest


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": (
            "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-stage-c-paired-calibration-v3-pair-source-authorized.schema.json"
        ),
        "title": "Forge Stage C paired calibration v3 pair source authorized",
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
        raise StageCV3ProtocolError("Stage C v3 manifest 与确定性生成结果不一致")
    schedule = value["schedule"]
    if len(schedule["pairs"]) != 24 or any(
        not pair["pair_id"].startswith("stage-c-v3-") for pair in schedule["pairs"]
    ):
        raise StageCV3ProtocolError("Stage C v3 必须包含 24 个新 identity pairs")
    if (
        schedule.get("retry") is not False
        or schedule.get("replacement") is not False
        or schedule.get("backfill") is not False
        or schedule.get("pair_source_preparation_before_attempts") is not True
        or schedule.get("pair_source_acquisition_count") != 1
    ):
        raise StageCV3ProtocolError("Stage C v3 重试或源码准备边界无效")
    schema = generate_schema(expected)
    jsonschema.Draft202012Validator.check_schema(schema)
    if check_schema_file:
        if (
            not DEFAULT_SCHEMA.is_file()
            or qualification.load_json(DEFAULT_SCHEMA) != schema
        ):
            raise StageCV3ProtocolError("Stage C v3 const Schema 缺失或漂移")
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
        ["git", "merge-base", "--is-ancestor", AUTHORIZATION_BASELINE_COMMIT, revision],
        cwd=repo_root,
        check=False,
    )
    if ancestor.returncode != 0:
        raise StageCV3ProtocolError(
            "当前 release 不是 Stage C v3 authorization baseline 的后代"
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
    parser.add_argument("command", choices=("generate", "validate", "show-schedule"))
    args = parser.parse_args(argv)
    if args.command == "generate":
        manifest = generate_manifest()
        write_generated(manifest)
        result: Any = {
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
