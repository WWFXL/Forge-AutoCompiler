#!/usr/bin/env python3
"""生成并校验 Stage C v7 pre-freeze verifier canary 未授权候选身份。"""

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

SCHEMA_VERSION = "forge-stage-c-v7-prefreeze-verifier-canary-candidate-1.0.0"
DOCUMENT_TYPE = "forge_stage_c_v7_prefreeze_verifier_canary_candidate"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/341"
SOURCE_MAIN_REVISION = "cea24f53b503955e3be1c3e53c475fa9fd5dfa75"
V5_MANIFEST_PATH = "benchmarks/manifests/cpp-stage-c-paired-calibration-v5-session-identity-authorized.json"
V5_MANIFEST_FILE_SHA256 = "72e264046f9aca73b2c30e830b57db671ef6ca400b4e92dc106b3c1a2534f19e"
V5_MANIFEST_SHA256 = "11eefa99737b6e20fdf5d300802cf5a7cf0a9178a5f0a44de4028693721859a2"
V6_MANIFEST_PATH = "benchmarks/manifests/cpp-stage-c-v6-offline-reevaluation-authorized.json"
V6_MANIFEST_FILE_SHA256 = "b72011da6a921c8e790826c198038830b55bed5d7256df5a3653604250389638"
V6_MANIFEST_SHA256 = "00530ddc740ae98f0327a89e5a1860e9a983c9e47b9aaeabd27543f4c75f23dd"
V6_RESULT_PATH = "benchmarks/reports/cpp-stage-c-v6-offline-reevaluation-result.json"
V6_RESULT_FILE_SHA256 = "be0783c1f693d510291a853e1fa97223dfa716f539bf80c00fb1327502edf42f"
V6_RESULT_REPORT_PATH = "benchmarks/reports/cpp-stage-c-v6-offline-reevaluation-result.md"
V6_RESULT_REPORT_FILE_SHA256 = "318e3d76dfab6e979070b45685e5bf0b8ddc127c51371efca1d7571375e503d7"
V6_FAILURE_AUDIT_PATH = "benchmarks/reports/cpp-stage-c-v6-failure-audit.json"
V6_FAILURE_AUDIT_FILE_SHA256 = "e64c04a1714dc03c19209a9c95b519fb34a8f83e8a8d9580cb5dbb23cdddf688"
V6_FAILURE_AUDIT_REPORT_PATH = "benchmarks/reports/cpp-stage-c-v6-failure-audit.md"
V6_FAILURE_AUDIT_REPORT_FILE_SHA256 = "c4027a44b3177c431afdb9d37db2d18778bd96b4eee259f5a51479e147234ac8"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-stage-c-v7-prefreeze-verifier-canary-candidate.md"
PROTOCOL_PATH = "scripts/forge_stage_c_v7_prefreeze_canary_protocol.py"
MANIFEST_RELATIVE_PATH = "benchmarks/manifests/cpp-stage-c-v7-prefreeze-verifier-canary-candidate.json"
SCHEMA_RELATIVE_PATH = "benchmarks/schemas/forge-stage-c-v7-prefreeze-verifier-canary-candidate.schema.json"
DEFAULT_EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-stage-c-v7-prefreeze-verifier-canary"
DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_RELATIVE_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_RELATIVE_PATH

RUNTIME_V3_PATH = "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v3.py"
CANDIDATE_VERIFIER_PATH = "backend/packages/harness/deerflow/compile/candidate_verifier.py"
EXTERNAL_EVALUATOR_V4_PATH = "backend/packages/harness/deerflow/compile/external_evaluator_v4.py"
RUNTIME_V3_SHA256 = "2d71383d011e943f78e9259b9f7ceec2c8e1f080d7609e86413ce188a841f65e"
CANDIDATE_VERIFIER_SHA256 = "e358b06ce2721d2ec90d3f30e9d1cb05d210e9c6f802690fc88a554c058dff7a"
EXTERNAL_EVALUATOR_V4_SHA256 = "9009c400b1b54d9ad05411f1a64124423cf50d8ba49bfa2d13071d9bedad4613"

CANARY_TASK_ORDER = ("theora", "json-c", "libjpeg-turbo", "oatpp")
EXPECTED_FAILURES = {
    "theora": {
        "evaluation_id": "stage-c-v6-theora-r1-b-reevaluation",
        "source_attempt_id": "stage-c-v5-theora-r1-b",
        "primary_failure": "candidate_artifact_set_mismatch",
        "root_cause": "broad_install_left_undeclared_static_libraries_and_zero_byte_support_file",
    },
    "json-c": {
        "evaluation_id": "stage-c-v6-json-c-r2-b-reevaluation",
        "source_attempt_id": "stage-c-v5-json-c-r2-b",
        "primary_failure": "target_mapping_invalid",
        "root_cause": "extra_target_mapping_key_and_incomplete_public_header_delivery",
    },
    "libjpeg-turbo": {
        "evaluation_id": "stage-c-v6-libjpeg-turbo-r2-b-reevaluation",
        "source_attempt_id": "stage-c-v5-libjpeg-turbo-r2-b",
        "primary_failure": "candidate_verifier_failed",
        "root_cause": "broad_install_left_undeclared_library_and_tools_with_three_failed_default_smokes",
    },
    "oatpp": {
        "evaluation_id": "stage-c-v6-oatpp-r2-b-reevaluation",
        "source_attempt_id": "stage-c-v5-oatpp-r2-b",
        "primary_failure": "candidate_artifact_set_mismatch",
        "root_cause": "test_library_was_installed_but_not_declared",
    },
}

canonical_sha256 = base.canonical_sha256
file_sha256 = base.file_sha256


class StageCV7CandidateError(RuntimeError):
    """Stage C v7 candidate 的历史来源或未授权边界无效。"""


def _load_historical_inputs(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_files = {
        V5_MANIFEST_PATH: V5_MANIFEST_FILE_SHA256,
        V6_MANIFEST_PATH: V6_MANIFEST_FILE_SHA256,
        V6_RESULT_PATH: V6_RESULT_FILE_SHA256,
        V6_RESULT_REPORT_PATH: V6_RESULT_REPORT_FILE_SHA256,
        V6_FAILURE_AUDIT_PATH: V6_FAILURE_AUDIT_FILE_SHA256,
        V6_FAILURE_AUDIT_REPORT_PATH: V6_FAILURE_AUDIT_REPORT_FILE_SHA256,
        RUNTIME_V3_PATH: RUNTIME_V3_SHA256,
        CANDIDATE_VERIFIER_PATH: CANDIDATE_VERIFIER_SHA256,
        EXTERNAL_EVALUATOR_V4_PATH: EXTERNAL_EVALUATOR_V4_SHA256,
    }
    for relative, expected_sha256 in expected_files.items():
        if file_sha256(repo_root / relative) != expected_sha256:
            raise StageCV7CandidateError(f"冻结来源文件哈希漂移: {relative}")

    v5_manifest = qualification.load_json(repo_root / V5_MANIFEST_PATH)
    v6_manifest = qualification.load_json(repo_root / V6_MANIFEST_PATH)
    v6_result = qualification.load_json(repo_root / V6_RESULT_PATH)
    audit = qualification.load_json(repo_root / V6_FAILURE_AUDIT_PATH)
    if canonical_sha256(v5_manifest) != V5_MANIFEST_SHA256 or canonical_sha256(v6_manifest) != V6_MANIFEST_SHA256:
        raise StageCV7CandidateError("Stage C v5/v6 manifest identity 漂移")
    if (
        v6_result.get("identity", {}).get("manifest_sha256") != V6_MANIFEST_SHA256
        or v6_result.get("identity", {}).get("source_v5_manifest_sha256") != V5_MANIFEST_SHA256
        or audit.get("scope", {}).get("source_failure_count") != 4
        or audit.get("summary", {}).get("runtime_prefreeze_feedback_gap_count") != 4
        or audit.get("decision", {}).get("next_phase") != "zero_provider_prefreeze_candidate_verifier_gate"
        or audit.get("decision", {}).get("provider_execution_authorized") is not False
    ):
        raise StageCV7CandidateError("Stage C v6 结果或失败审计语义漂移")
    return v5_manifest, audit


def _selected_tasks(v5_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    tasks_by_id = {task["task_id"]: task for task in v5_manifest["tasks"]}
    if set(CANARY_TASK_ORDER) - set(tasks_by_id):
        raise StageCV7CandidateError("Stage C v5 缺少 v7 canary task")
    tasks = [copy.deepcopy(tasks_by_id[task_id]) for task_id in CANARY_TASK_ORDER]
    if any(task.get("oracle", {}).get("kind") != "compile_and_run" for task in tasks):
        raise StageCV7CandidateError("Stage C v7 canary 必须使用 compile_and_run oracle")
    return tasks


def _canary_schedule(audit: dict[str, Any]) -> dict[str, Any]:
    cases_by_task = {case["task_id"]: case for case in audit["cases"]}
    attempts = []
    for sequence, task_id in enumerate(CANARY_TASK_ORDER, 1):
        expected = EXPECTED_FAILURES[task_id]
        case = cases_by_task.get(task_id)
        if case is None or any(case.get(field) != value for field, value in expected.items()):
            raise StageCV7CandidateError(f"Stage C v6 失败来源漂移: {task_id}")
        attempts.append(
            {
                "sequence": sequence,
                "canary_id": f"stage-c-v7-{task_id}-prefreeze-canary",
                "attempt_id": f"stage-c-v7-{task_id}-b-canary",
                "task_id": task_id,
                "arm": "B",
                "method": "forge-agent-workflow-node-v3",
                "source_evaluation_id": expected["evaluation_id"],
                "source_attempt_id": expected["source_attempt_id"],
                "source_primary_failure": expected["primary_failure"],
                "source_root_cause": expected["root_cause"],
            }
        )
    return {
        "canary_attempt_count": len(attempts),
        "attempts": attempts,
        "stop_on_first_failure": True,
        "retry": False,
        "replacement": False,
        "backfill": False,
        "historical_candidates_reused": False,
    }


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    v5_manifest, audit = _load_historical_inputs(repo_root)
    preregistration = repo_root / PREREGISTRATION_PATH
    if preregistration.is_symlink() or not preregistration.is_file():
        raise StageCV7CandidateError("Stage C v7 candidate 预注册不存在")

    per_attempt = copy.deepcopy(v5_manifest["budget"]["per_arm"])
    per_attempt["max_recorded_tokens"] = None
    component_paths = (
        "backend/packages/harness/deerflow/compile/agent_workflow_runtime.py",
        "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v2.py",
        RUNTIME_V3_PATH,
        CANDIDATE_VERIFIER_PATH,
        "backend/packages/harness/deerflow/compile/agent_workflow_schemas.py",
        EXTERNAL_EVALUATOR_V4_PATH,
        "scripts/forge_stage_c_protocol.py",
        "scripts/forge_stage_c_v5_protocol.py",
        "scripts/forge_stage_c_runner.py",
        PROTOCOL_PATH,
        PREREGISTRATION_PATH,
        V5_MANIFEST_PATH,
        V6_MANIFEST_PATH,
        V6_RESULT_PATH,
        V6_RESULT_REPORT_PATH,
        V6_FAILURE_AUDIT_PATH,
        V6_FAILURE_AUDIT_REPORT_PATH,
    )
    return {
        "$schema": "../schemas/forge-stage-c-v7-prefreeze-verifier-canary-candidate.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "issue_url": ISSUE_URL,
        "purpose": "stage_c_v7_prefreeze_verifier_provider_canary_candidate",
        "status": "candidate_not_authorized",
        "authorization": {
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
        },
        "provider": copy.deepcopy(v5_manifest["provider"]),
        "environment": copy.deepcopy(v5_manifest["environment"]),
        "budget": {
            "per_attempt": per_attempt,
            "reachability_max_requests": 1,
            "reachability_max_recorded_tokens": None,
            "canary_attempts_max_recorded_tokens": None,
            "total_max_recorded_tokens": None,
            "token_accounting": {
                "mode": "meter_each_request_without_ceiling",
                "record_input_tokens": True,
                "record_output_tokens": True,
                "record_total_tokens": True,
                "token_total_is_termination_condition": False,
            },
        },
        "methods": {
            "B": {
                "name": "forge-agent-workflow-node-v3",
                "runtime_version": "agent-workflow-runtime-v3",
                "runtime_path": RUNTIME_V3_PATH,
                "prefreeze_feedback_to_agent": True,
                "external_evaluator_feedback_to_agent": False,
                "zero_model_fast_path": False,
            }
        },
        "candidate_contract": {
            "submission_schema_version": "agent-workflow-node-v1",
            "create_once": True,
            "complete_delivery_scan": True,
            "single_frozen_target_id": True,
            "system_owned_functional_oracle": True,
            "max_rejection_evidence_items": 12,
            "oracle_raw_output_exposed": False,
            "same_attempt_repair_and_resubmit": True,
        },
        "external_evaluator": {
            "backend": "external-evaluator-v4",
            "backend_path": EXTERNAL_EVALUATOR_V4_PATH,
            "layers": ["S0", "S1", "S2", "S3", "S4", "S5"],
            "strict_success": "all_layers_passed",
            "independent_after_candidate_freeze": True,
        },
        "tasks": _selected_tasks(v5_manifest),
        "schedule": _canary_schedule(audit),
        "execution": {
            "source_main_revision": SOURCE_MAIN_REVISION,
            "release_branch": "main",
            "authorization_baseline_commit": None,
            "evidence_directory": DEFAULT_EVIDENCE_DIRECTORY,
            "create_once": True,
            "commands": ["validate", "show-plan"],
            "execution_authorized": False,
            "future_authorized_identity_required": True,
            "fresh_thread_session_and_evidence_per_attempt": True,
        },
        "analysis": {
            "kind": "b_arm_engineering_canary",
            "independent_unit": "task",
            "a_arm_present": False,
            "treatment_effect_estimated": False,
            "generalization_claim_authorized": False,
            "v5_outcomes_replaced": False,
            "v6_outcomes_replaced": False,
        },
        "historical_inputs": {
            "v5_manifest": {
                "path": V5_MANIFEST_PATH,
                "file_sha256": V5_MANIFEST_FILE_SHA256,
                "canonical_sha256": V5_MANIFEST_SHA256,
                "read_only": True,
            },
            "v6_manifest": {
                "path": V6_MANIFEST_PATH,
                "file_sha256": V6_MANIFEST_FILE_SHA256,
                "canonical_sha256": V6_MANIFEST_SHA256,
                "read_only": True,
            },
            "v6_result": {"path": V6_RESULT_PATH, "file_sha256": V6_RESULT_FILE_SHA256, "read_only": True},
            "v6_failure_audit": {"path": V6_FAILURE_AUDIT_PATH, "file_sha256": V6_FAILURE_AUDIT_FILE_SHA256, "read_only": True},
        },
        "preregistration": {"path": PREREGISTRATION_PATH, "file_sha256": file_sha256(preregistration)},
        "frozen_components": {relative: file_sha256(repo_root / relative) for relative in component_paths},
    }


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-stage-c-v7-prefreeze-verifier-canary-candidate.schema.json",
        "title": "Forge Stage C v7 pre-freeze verifier canary candidate",
        "const": manifest,
    }


def validate_manifest(value: dict[str, Any], repo_root: Path = REPO_ROOT, *, check_schema_file: bool = True) -> dict[str, Any]:
    expected = generate_manifest(repo_root)
    if value != expected:
        raise StageCV7CandidateError("Stage C v7 candidate manifest 与确定性结果不一致")
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
        raise StageCV7CandidateError("Stage C v7 candidate 未授权边界漂移")
    budget = value["budget"]
    if (
        budget["per_attempt"].get("max_recorded_tokens") is not None
        or budget.get("reachability_max_recorded_tokens") is not None
        or budget.get("canary_attempts_max_recorded_tokens") is not None
        or budget.get("total_max_recorded_tokens") is not None
        or budget.get("token_accounting", {}).get("token_total_is_termination_condition") is not False
    ):
        raise StageCV7CandidateError("Stage C v7 token 只计量边界漂移")
    schedule = value["schedule"]
    if (
        schedule.get("canary_attempt_count") != 4
        or [attempt.get("task_id") for attempt in schedule.get("attempts", [])] != list(CANARY_TASK_ORDER)
        or schedule.get("stop_on_first_failure") is not True
        or any(schedule.get(field) is not False for field in ("retry", "replacement", "backfill", "historical_candidates_reused"))
    ):
        raise StageCV7CandidateError("Stage C v7 canary schedule 漂移")
    if value["frozen_components"].get(RUNTIME_V3_PATH) != RUNTIME_V3_SHA256 or value["frozen_components"].get(CANDIDATE_VERIFIER_PATH) != CANDIDATE_VERIFIER_SHA256:
        raise StageCV7CandidateError("Stage C v7 pre-freeze runtime identity 漂移")
    schema = generate_schema(expected)
    jsonschema.Draft202012Validator.check_schema(schema)
    if check_schema_file:
        if not DEFAULT_SCHEMA.is_file() or qualification.load_json(DEFAULT_SCHEMA) != schema:
            raise StageCV7CandidateError("Stage C v7 const Schema 缺失或漂移")
        jsonschema.validate(value, qualification.load_json(DEFAULT_SCHEMA))
    return value


def load_manifest(path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    return validate_manifest(qualification.load_json(path), repo_root)


def write_generated(manifest: dict[str, Any]) -> None:
    DEFAULT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_SCHEMA.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    DEFAULT_SCHEMA.write_text(json.dumps(generate_schema(manifest), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
            "canary_attempt_count": manifest["schedule"]["canary_attempt_count"],
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
