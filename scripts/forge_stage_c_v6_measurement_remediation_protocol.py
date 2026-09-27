#!/usr/bin/env python3
"""生成并校验 Stage C v6 测量链路修复的未授权候选身份。"""

from __future__ import annotations

import argparse
import copy
import json
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

SCHEMA_VERSION = "forge-stage-c-v6-measurement-remediation-candidate-1.0.0"
DOCUMENT_TYPE = "forge_stage_c_v6_measurement_remediation_candidate"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/331"
V5_MANIFEST_PATH = "benchmarks/manifests/cpp-stage-c-paired-calibration-v5-session-identity-authorized.json"
V5_RESULT_PATH = "benchmarks/reports/cpp-stage-c-paired-calibration-v5-result.json"
V5_RESULT_REPORT_PATH = "benchmarks/reports/cpp-stage-c-paired-calibration-v5-result.md"
V5_MANIFEST_FILE_SHA256 = "72e264046f9aca73b2c30e830b57db671ef6ca400b4e92dc106b3c1a2534f19e"
V5_MANIFEST_SHA256 = "11eefa99737b6e20fdf5d300802cf5a7cf0a9178a5f0a44de4028693721859a2"
V5_RESULT_FILE_SHA256 = "0fde19732f4310fd88d6b8db9a9bfca7fd5dabe3c7dd72d58b6d7b6ad9897efd"
V5_RESULT_REPORT_FILE_SHA256 = "80f337573f43bb23575460ad14471393f5d9580bece0ee06410231beac19d701"
V5_RELEASE_REVISION = "c37a145c3b0b30453cb2053a8fca3dd2d3599435"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-stage-c-paired-calibration-v6-measurement-remediation-candidate.md"
PROTOCOL_PATH = "scripts/forge_stage_c_v6_measurement_remediation_protocol.py"
MANIFEST_RELATIVE_PATH = "benchmarks/manifests/cpp-stage-c-paired-calibration-v6-measurement-remediation-candidate.json"
SCHEMA_RELATIVE_PATH = "benchmarks/schemas/forge-stage-c-v6-measurement-remediation-candidate.schema.json"
DEFAULT_EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-stage-c-v6-measurement-remediation"
DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_RELATIVE_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_RELATIVE_PATH

canonical_sha256 = base.canonical_sha256
file_sha256 = base.file_sha256


class StageCV6CandidateError(RuntimeError):
    """Stage C v6 candidate 的来源身份或未授权边界无效。"""


def _load_v5_inputs(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest_path = repo_root / V5_MANIFEST_PATH
    result_path = repo_root / V5_RESULT_PATH
    report_path = repo_root / V5_RESULT_REPORT_PATH
    if file_sha256(manifest_path) != V5_MANIFEST_FILE_SHA256 or file_sha256(result_path) != V5_RESULT_FILE_SHA256 or file_sha256(report_path) != V5_RESULT_REPORT_FILE_SHA256:
        raise StageCV6CandidateError("Stage C v5 冻结文件哈希漂移")
    manifest = qualification.load_json(manifest_path)
    result = qualification.load_json(result_path)
    if canonical_sha256(manifest) != V5_MANIFEST_SHA256:
        raise StageCV6CandidateError("Stage C v5 manifest identity 漂移")
    if (
        result.get("identity", {}).get("manifest_sha256") != V5_MANIFEST_SHA256
        or result.get("identity", {}).get("release_revision") != V5_RELEASE_REVISION
        or result.get("batch", {}).get("pair_count") != 24
        or result.get("batch", {}).get("arm_count") != 48
        or result.get("arm_summary", {}).get("B", {}).get("candidate_submitted") != 22
        or result.get("failure_structure", {}).get("arm_B_no_candidate_pairs") != ["stage-c-v5-civetweb-r1", "stage-c-v5-civetweb-r2"]
    ):
        raise StageCV6CandidateError("Stage C v5 结果审计语义漂移")
    return manifest, result


def _remediation_schedule(
    v5_manifest: dict[str, Any],
    v5_result: dict[str, Any],
) -> dict[str, Any]:
    excluded = set(v5_result["failure_structure"]["arm_B_no_candidate_pairs"])
    evaluations = []
    for pair in v5_manifest["schedule"]["pairs"]:
        if pair["pair_id"] in excluded:
            continue
        evaluations.append(
            {
                "evaluation_id": pair["pair_id"].replace("stage-c-v5-", "stage-c-v6-", 1) + "-b-reevaluation",
                "source_pair_id": pair["pair_id"],
                "source_attempt_id": pair["attempt_ids"]["B"],
                "task_id": pair["task_id"],
                "replicate": pair["replicate"],
                "source_arm": "B",
                "provider_requests": 0,
            }
        )
    return {
        "source_pair_count": 24,
        "evaluation_count": len(evaluations),
        "excluded_no_candidate_pairs": sorted(excluded),
        "evaluations": evaluations,
        "retry": False,
        "replacement": False,
        "backfill": False,
        "v5_candidate_and_outcome_inputs_read_only": True,
    }


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    v5_manifest, v5_result = _load_v5_inputs(repo_root)
    preregistration = repo_root / PREREGISTRATION_PATH
    if not preregistration.is_file():
        raise StageCV6CandidateError("Stage C v6 candidate 预注册不存在")
    manifest = copy.deepcopy(v5_manifest)
    manifest["$schema"] = "../schemas/forge-stage-c-v6-measurement-remediation-candidate.schema.json"
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["document_type"] = DOCUMENT_TYPE
    manifest["issue_url"] = ISSUE_URL
    manifest["purpose"] = "stage_c_v5_measurement_remediation_candidate"
    manifest["authorization"] = {
        "candidate_identity_only": True,
        "credential_read_authorized": False,
        "provider_calls_authorized": False,
        "model_creation_authorized": False,
        "reachability_request_authorized": False,
        "docker_execution_authorized": False,
        "formal_stage_c_attempts_authorized": False,
        "evidence_write_authorized": False,
        "model_tokens_authorized": False,
        "stage_c_execution_started": False,
    }
    historical_cost_audit = manifest["budget"].pop("cost_sensitivity_audit")
    manifest["budget"].pop("formal_arm_count")
    manifest["budget"]["future_full_paired_arm_count"] = 48
    manifest["budget"]["remediation_evaluation_count"] = 22
    manifest["budget"]["per_arm"]["max_recorded_tokens"] = None
    manifest["budget"]["reachability_max_recorded_tokens"] = None
    manifest["budget"]["formal_arms_max_recorded_tokens"] = None
    manifest["budget"]["total_max_recorded_tokens"] = None
    manifest["budget"]["historical_cost_sensitivity_audit"] = {
        **historical_cost_audit,
        "historical_only": True,
        "limits_apply_to_v6": False,
    }
    manifest["budget"]["token_accounting"] = {
        "mode": "meter_each_request_without_ceiling",
        "record_input_tokens": True,
        "record_output_tokens": True,
        "record_total_tokens": True,
        "token_total_is_termination_condition": False,
    }
    manifest["schedule"] = _remediation_schedule(v5_manifest, v5_result)
    manifest["analysis"] = {
        "kind": "post_hoc_measurement_remediation_sensitivity_analysis",
        "independent_unit": "project",
        "v5_original_result_replaced": False,
        "v5_a_arm_outcomes_read_only": True,
        "v5_b_candidates_read_only": True,
        "no_candidate_attempts_excluded_from_reevaluation": True,
        "fresh_full_paired_run_requires_separate_authorized_identity": True,
    }
    manifest["execution"] = {
        "authorization_baseline_commit": None,
        "release_branch": "main",
        "evidence_directory": DEFAULT_EVIDENCE_DIRECTORY,
        "create_once": True,
        "commands": ["validate", "show-plan"],
        "execution_authorized": False,
        "source_v5_evidence_read_only": True,
        "network_policy": "exact_source_acquisition_then_replay_network_none",
    }
    manifest["remediation_contract"] = {
        "replay_source": "verified_git_archive_mounted_read_only",
        "replay_source_archive_path": "/repro/source.tar",
        "replay_network": "none",
        "oracle_kinds": ["command", "compile_and_run", "service_probe"],
        "oracle_preflight_task_count": 12,
        "bounded_error_message_bytes": 4096,
        "error_message_sha256_required": True,
        "provider_requests_per_evaluation": 0,
    }
    manifest["prior_v5_identity"] = {
        "manifest_path": V5_MANIFEST_PATH,
        "manifest_file_sha256": V5_MANIFEST_FILE_SHA256,
        "manifest_sha256": V5_MANIFEST_SHA256,
        "result_path": V5_RESULT_PATH,
        "result_file_sha256": V5_RESULT_FILE_SHA256,
        "result_report_path": V5_RESULT_REPORT_PATH,
        "result_report_file_sha256": V5_RESULT_REPORT_FILE_SHA256,
        "release_revision": V5_RELEASE_REVISION,
        "must_not_modify_or_resume": True,
    }
    manifest["preregistration"] = {
        "path": PREREGISTRATION_PATH,
        "file_sha256": file_sha256(preregistration),
    }
    component_paths = (
        "backend/packages/harness/deerflow/compile/agent_workflow_node.py",
        "backend/packages/harness/deerflow/compile/agent_workflow_runtime.py",
        "backend/packages/harness/deerflow/compile/agent_workflow_schemas.py",
        "backend/packages/harness/deerflow/compile/operations.py",
        "backend/packages/harness/deerflow/compile/schemas.py",
        "backend/packages/harness/deerflow/compile/external_evaluator_v4.py",
        "scripts/forge_stage_c_controlled_baseline.py",
        "scripts/forge_stage_c_runner.py",
        PREREGISTRATION_PATH,
        PROTOCOL_PATH,
        V5_MANIFEST_PATH,
        V5_RESULT_PATH,
        V5_RESULT_REPORT_PATH,
    )
    manifest["frozen_components"] = {relative: file_sha256(repo_root / relative) for relative in component_paths}
    return manifest


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": ("https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-stage-c-v6-measurement-remediation-candidate.schema.json"),
        "title": "Forge Stage C v6 measurement remediation candidate",
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
        raise StageCV6CandidateError("Stage C v6 candidate manifest 与确定性结果不一致")
    authorization = value["authorization"]
    if (
        authorization.get("candidate_identity_only") is not True
        or authorization.get("stage_c_execution_started") is not False
        or any(
            authorization[field] is not False
            for field in (
                "credential_read_authorized",
                "provider_calls_authorized",
                "model_creation_authorized",
                "reachability_request_authorized",
                "docker_execution_authorized",
                "formal_stage_c_attempts_authorized",
                "evidence_write_authorized",
                "model_tokens_authorized",
            )
        )
    ):
        raise StageCV6CandidateError("Stage C v6 candidate 未授权边界漂移")
    budget = value["budget"]
    if (
        budget["per_arm"].get("max_recorded_tokens") is not None
        or budget.get("reachability_max_recorded_tokens") is not None
        or budget.get("formal_arms_max_recorded_tokens") is not None
        or budget.get("total_max_recorded_tokens") is not None
        or budget.get("token_accounting", {}).get("token_total_is_termination_condition") is not False
    ):
        raise StageCV6CandidateError("Stage C v6 token 只计量边界漂移")
    schedule = value["schedule"]
    if (
        schedule.get("evaluation_count") != 22
        or len(schedule.get("evaluations", [])) != 22
        or schedule.get("retry") is not False
        or schedule.get("replacement") is not False
        or schedule.get("backfill") is not False
        or len({item["evaluation_id"] for item in schedule.get("evaluations", [])}) != 22
    ):
        raise StageCV6CandidateError("Stage C v6 离线重评 schedule 漂移")
    schema = generate_schema(expected)
    jsonschema.Draft202012Validator.check_schema(schema)
    if check_schema_file:
        if not DEFAULT_SCHEMA.is_file() or qualification.load_json(DEFAULT_SCHEMA) != schema:
            raise StageCV6CandidateError("Stage C v6 const Schema 缺失或漂移")
        jsonschema.validate(value, qualification.load_json(DEFAULT_SCHEMA))
    return value


def load_manifest(
    path: Path = DEFAULT_MANIFEST,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    return validate_manifest(qualification.load_json(path), repo_root)


def write_generated(manifest: dict[str, Any]) -> None:
    DEFAULT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_SCHEMA.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    DEFAULT_SCHEMA.write_text(
        json.dumps(
            generate_schema(manifest),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate", "show-plan"))
    args = parser.parse_args(argv)
    if args.command == "generate":
        manifest = generate_manifest()
        write_generated(manifest)
        result: Any = {
            "status": "generated_candidate",
            "manifest_sha256": canonical_sha256(manifest),
            "evaluation_count": manifest["schedule"]["evaluation_count"],
            "execution_authorized": False,
        }
    else:
        manifest = load_manifest()
        if args.command == "validate":
            result = {
                "status": "valid_candidate",
                "manifest_sha256": canonical_sha256(manifest),
                "provider_calls": 0,
                "model_tokens": 0,
                "formal_attempts": 0,
                "execution_authorized": False,
            }
        else:
            result = manifest["schedule"]
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
