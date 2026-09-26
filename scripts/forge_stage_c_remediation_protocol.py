#!/usr/bin/env python3
"""生成并校验 Stage C v2 源码准备修复后的授权执行身份。"""

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

import forge_stage_c_protocol as v1  # noqa: E402
import forge_stage_c_task_qualification as qualification  # noqa: E402

SCHEMA_VERSION = "forge-stage-c-paired-calibration-v2-remediation-authorized-1.0.0"
DOCUMENT_TYPE = "forge_stage_c_paired_calibration_v2_remediation_authorized"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/321"
AUTHORIZATION_BASELINE_COMMIT = "80ac16d01741012327841a140be4e8bec978f165"
MANIFEST_RELATIVE_PATH = (
    "benchmarks/manifests/cpp-stage-c-paired-calibration-v2-remediation-authorized.json"
)
SCHEMA_RELATIVE_PATH = "benchmarks/schemas/forge-stage-c-paired-calibration-v2-remediation-authorized.schema.json"
PREREGISTRATION_PATH = (
    "benchmarks/preregistrations/cpp-stage-c-paired-calibration-v2-remediation.md"
)
V1_MANIFEST_PATH = "benchmarks/manifests/cpp-stage-c-paired-calibration-authorized.json"
V1_FAILURE_AUDIT_PATH = (
    "benchmarks/reports/cpp-stage-c-paired-calibration-v1-failed.json"
)
V1_FAILURE_REPORT_PATH = (
    "benchmarks/reports/cpp-stage-c-paired-calibration-v1-failed.md"
)
PROTOCOL_PATH = "scripts/forge_stage_c_remediation_protocol.py"
RUNNER_PATH = "scripts/forge_stage_c_runner.py"
DEFAULT_EVIDENCE_DIRECTORY = (
    "/workspace/.compile-sessions/"
    "benchmark-evidence-stage-c-paired-calibration-v2-remediation"
)
DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_RELATIVE_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_RELATIVE_PATH

canonical_bytes = v1.canonical_bytes
canonical_sha256 = v1.canonical_sha256
file_sha256 = v1.file_sha256


class StageCRemediationProtocolError(RuntimeError):
    """Stage C v2 remediation manifest、来源审计或授权边界无效。"""


def _validate_v1_failure_audit(repo_root: Path) -> dict[str, Any]:
    path = repo_root / V1_FAILURE_AUDIT_PATH
    value = qualification.load_json(path)
    expected_identity = {
        "manifest_file_sha256": "c3037fc5fcebf6a4e077925b8fdda07caedf140bd4f4a0f73bb011fb3d1e2390",
        "manifest_sha256": "6ef6f6fe9986ad6eb53d57273d4901389e96bff5b6b69d884d09282d391ac641",
        "release_revision": "80ac16d01741012327841a140be4e8bec978f165",
        "runner_sha256": "113b46d627c46193789844c2fd31ce0b56181325f00575531b988d56d21553c3",
    }
    if (
        value.get("schema_version")
        != "forge-stage-c-paired-calibration-v1-failed-audit-1.0.0"
        or value.get("document_type")
        != "forge_stage_c_paired_calibration_v1_failed_audit"
        or value.get("classification")
        != "source_acquisition_interrupted_before_formal_arm_registration"
        or value.get("identity") != expected_identity
        or value.get("usage")
        != {
            "formal_arm_attempts": 0,
            "formal_arm_model_requests": 0,
            "formal_arm_recorded_tokens": 0,
        }
        or value.get("batch", {}).get("must_not_resume") is not True
        or value.get("resource_audit", {}).get("zero_managed_resources") is not True
        or value.get("interpretation", {}).get("historical_outcomes_imported")
        is not False
    ):
        raise StageCRemediationProtocolError("Stage C v1 失败审计语义无效")
    if (
        file_sha256(repo_root / V1_MANIFEST_PATH)
        != expected_identity["manifest_file_sha256"]
    ):
        raise StageCRemediationProtocolError("Stage C v1 manifest 文件哈希漂移")
    files = value.get("evidence_files")
    if not isinstance(files, list) or len(files) != 21:
        raise StageCRemediationProtocolError("Stage C v1 evidence inventory 不完整")
    paths = [item.get("path") for item in files if isinstance(item, dict)]
    if len(paths) != 21 or len(set(paths)) != 21:
        raise StageCRemediationProtocolError("Stage C v1 evidence inventory 路径无效")
    required = {
        "markers/batch.json": value["batch"]["marker_sha256"],
        "markers/reachability.json": value["reachability"]["marker_sha256"],
        "reports/reachability.json": value["reachability"]["report_sha256"],
        "pairs/stage-c-json-c-r1/A/source-acquisition/repository/.git/FETCH_HEAD": (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        ),
    }
    inventory = {item["path"]: item["sha256"] for item in files}
    if any(inventory.get(path) != digest for path, digest in required.items()):
        raise StageCRemediationProtocolError("Stage C v1 关键 evidence 哈希漂移")
    return value


def _remediation_schedule(schedule: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(schedule)
    pairs = []
    for pair in value["pairs"]:
        updated = copy.deepcopy(pair)
        pair_id = f"stage-c-v2-{pair['task_id']}-r{pair['replicate']}"
        updated["pair_id"] = pair_id
        updated["attempt_ids"] = {arm: f"{pair_id}-{arm.lower()}" for arm in ("A", "B")}
        pairs.append(updated)
    value["pairs"] = pairs
    value["source_preparation_retry_before_attempt"] = True
    value["v1_outcomes_imported"] = False
    return value


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    manifest = v1.generate_manifest(repo_root)
    audit = _validate_v1_failure_audit(repo_root)
    preregistration = repo_root / PREREGISTRATION_PATH
    if not preregistration.is_file():
        raise StageCRemediationProtocolError("Stage C v2 remediation 预注册不存在")

    manifest["$schema"] = (
        "../schemas/forge-stage-c-paired-calibration-v2-remediation-authorized.schema.json"
    )
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["document_type"] = DOCUMENT_TYPE
    manifest["issue_url"] = ISSUE_URL
    manifest["purpose"] = "stage_c_controlled_paired_calibration_v2_remediation"
    manifest["schedule"] = _remediation_schedule(manifest["schedule"])
    manifest["analysis"]["v1_outcomes_imported"] = False
    manifest["authorization"]["prior_reachability_recorded_tokens"] = 70
    manifest["authorization"]["cumulative_max_recorded_tokens"] = 14_405_070
    manifest["execution"].update(
        {
            "authorization_baseline_commit": AUTHORIZATION_BASELINE_COMMIT,
            "evidence_directory": DEFAULT_EVIDENCE_DIRECTORY,
            "source_preparation_boundary": "before_create_once_arm_attempt_marker",
            "v1_evidence_imported": False,
        }
    )
    manifest["preregistration"] = {
        "path": PREREGISTRATION_PATH,
        "file_sha256": file_sha256(preregistration),
    }
    manifest["prior_failed_identity"] = {
        "audit_path": V1_FAILURE_AUDIT_PATH,
        "audit_file_sha256": file_sha256(repo_root / V1_FAILURE_AUDIT_PATH),
        "audit_canonical_sha256": canonical_sha256(audit),
        "manifest_path": V1_MANIFEST_PATH,
        "manifest_file_sha256": audit["identity"]["manifest_file_sha256"],
        "manifest_sha256": audit["identity"]["manifest_sha256"],
        "release_revision": audit["identity"]["release_revision"],
        "evidence_directory": audit["evidence_directory"],
        "must_not_resume": True,
        "historical_outcomes_imported": False,
    }
    frozen = manifest["frozen_components"]
    frozen.pop(v1.PREREGISTRATION_PATH, None)
    for relative in (
        PREREGISTRATION_PATH,
        V1_MANIFEST_PATH,
        V1_FAILURE_AUDIT_PATH,
        V1_FAILURE_REPORT_PATH,
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
            "forge-stage-c-paired-calibration-v2-remediation-authorized.schema.json"
        ),
        "title": "Forge Stage C paired calibration v2 remediation authorized",
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
        raise StageCRemediationProtocolError(
            "Stage C v2 remediation manifest 与确定性生成结果不一致"
        )
    schedule = value["schedule"]
    if len(schedule["pairs"]) != 24 or any(
        not pair["pair_id"].startswith("stage-c-v2-") for pair in schedule["pairs"]
    ):
        raise StageCRemediationProtocolError(
            "Stage C v2 必须包含 24 个新 identity pairs"
        )
    if (
        schedule.get("retry") is not False
        or schedule.get("replacement") is not False
        or schedule.get("backfill") is not False
        or schedule.get("source_preparation_retry_before_attempt") is not True
    ):
        raise StageCRemediationProtocolError("Stage C v2 重试边界无效")
    schema = generate_schema(expected)
    jsonschema.Draft202012Validator.check_schema(schema)
    if check_schema_file:
        if (
            not DEFAULT_SCHEMA.is_file()
            or qualification.load_json(DEFAULT_SCHEMA) != schema
        ):
            raise StageCRemediationProtocolError("Stage C v2 const Schema 缺失或漂移")
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
        raise StageCRemediationProtocolError(
            "当前 release 不是 Stage C v2 authorization baseline 的后代"
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
