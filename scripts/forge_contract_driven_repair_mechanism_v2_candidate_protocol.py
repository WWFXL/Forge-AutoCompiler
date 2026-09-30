#!/usr/bin/env python3
"""生成并校验契约驱动修复 mechanism v2 独立 36-arm 候选身份。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_contract_driven_repair_mechanism_v1_formal_protocol as source  # noqa: E402

# 保持 frozen v1 runner 访问 protocol.parent.parent.parent.candidate 的接口形状。
parent = source.parent
candidate = source.parent.parent.parent.candidate

SCHEMA_VERSION = "forge-contract-driven-repair-mechanism-v2-candidate-1.0.0"
DOCUMENT_TYPE = "forge_contract_driven_repair_mechanism_v2_candidate"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/367"
IDENTITY_BASELINE_REVISION = "b5acc18c13057e7ba1deee078c628ad907647679"
PARENT_MANIFEST_CANONICAL_SHA256 = (
    "3a843799109e1163b34f4ed046f0155c7eca91a48ebaecb904e5ad3ed015829f"
)
PARENT_MANIFEST_FILE_SHA256 = (
    "4fae67f177d692a0a0165326b9b3845fc79244b5d510abb88cd855eb159544a4"
)
FAILED_EVIDENCE_INVENTORY_SHA256 = (
    "24019a372a3b49fe6dc1b141da45f09f764639c253fc1ed16521341f3c6d2fb5"
)
FAILED_EVIDENCE_FILE_COUNT = 9
FAILED_EVIDENCE_TOTAL_SIZE_BYTES = 66_466
OLD_EVIDENCE_DIRECTORY = ".compile-sessions/benchmark-evidence-contract-driven-repair-mechanism-v1-authorized"
EVIDENCE_DIRECTORY = ".compile-sessions/benchmark-evidence-contract-driven-repair-mechanism-v2-independent"
OPAQUE_ID_SEED = "forge-contract-driven-repair-mechanism-v2-independent-2026-09-30"

PROTOCOL_PATH = (
    "scripts/forge_contract_driven_repair_mechanism_v2_candidate_protocol.py"
)
RUNNER_PATH = "scripts/forge_contract_driven_repair_mechanism_v2_candidate_runner.py"
MARKER_REPAIR_PATH = (
    "scripts/forge_contract_driven_repair_mechanism_v1_formal_marker_repair.py"
)
FAILURE_AUDIT_JSON_PATH = "benchmarks/reports/cpp-contract-driven-repair-mechanism-v1-formal-failure-audit.json"
FAILURE_AUDIT_MARKDOWN_PATH = (
    "benchmarks/reports/cpp-contract-driven-repair-mechanism-v1-formal-failure-audit.md"
)
FAILURE_AUDIT_SCHEMA_PATH = (
    "benchmarks/schemas/forge-contract-repair-formal-failure-audit.schema.json"
)
MANIFEST_PATH = (
    "benchmarks/manifests/cpp-contract-driven-repair-mechanism-v2-candidate.json"
)
SCHEMA_PATH = (
    "benchmarks/schemas/forge-contract-driven-repair-mechanism-v2-candidate.schema.json"
)
PREREGISTRATION_PATH = (
    "benchmarks/preregistrations/cpp-contract-driven-repair-mechanism-v2-candidate.md"
)

MARKER_REPAIR_FILE_SHA256 = (
    "07e781c220a3f315f823a127bb1a0f839dfa81ceca99d2266f6fa10be97c073c"
)
FROZEN_RUNNER_FILE_SHA256 = (
    "5bb1797d2a3a5a8c700ba8da5677b195d0c0db969498521df878f669c815e358"
)
FAILURE_AUDIT_JSON_FILE_SHA256 = (
    "1fe2892b362a05776b4748f1ffd6bd6f4aeb05d4d7f752ea70b5b2c93a299e7a"
)
FAILURE_AUDIT_MARKDOWN_FILE_SHA256 = (
    "45cdc745a4df725aaecc39e3320d3ac49bad944c2647c7103dfa3f205baf3be7"
)
FAILURE_AUDIT_SCHEMA_FILE_SHA256 = (
    "7b7c895a35057572abdc13688906af9e3c448c5ef182ef26d031152ce3d70846"
)

DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_PATH
AVAILABILITY_AUDIT_RELEASE_REVISION = IDENTITY_BASELINE_REVISION
AVAILABILITY_MARKER_FILE_SHA256 = "pending-independent-availability"

FROZEN_INDEPENDENT_COMPONENT_PATHS = (
    source.MANIFEST_PATH,
    source.PROTOCOL_PATH,
    source.RUNNER_PATH,
    MARKER_REPAIR_PATH,
    FAILURE_AUDIT_JSON_PATH,
    FAILURE_AUDIT_MARKDOWN_PATH,
    FAILURE_AUDIT_SCHEMA_PATH,
    "backend/tests/test_forge_contract_driven_repair_mechanism_v2_candidate.py",
    "backend/tests/test_forge_contract_driven_repair_mechanism_v2_candidate_docker.py",
    PREREGISTRATION_PATH,
    PROTOCOL_PATH,
    RUNNER_PATH,
)


class IndependentCandidateProtocolError(RuntimeError):
    """独立 36-arm 候选身份、父证据或允许差异发生漂移。"""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IndependentCandidateProtocolError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise IndependentCandidateProtocolError(f"JSON 顶层必须为对象: {path}")
    return value


def _parent_manifest(repo_root: Path) -> dict[str, Any]:
    path = repo_root / source.MANIFEST_PATH
    value = source.load_manifest(path, repo_root)
    if candidate.canonical_sha256(value) != PARENT_MANIFEST_CANONICAL_SHA256:
        raise IndependentCandidateProtocolError(
            "父 formal identity canonical SHA-256 漂移"
        )
    if candidate.file_sha256(path) != PARENT_MANIFEST_FILE_SHA256:
        raise IndependentCandidateProtocolError("父 formal manifest 文件 SHA-256 漂移")
    return value


def _verify_failure_audit(repo_root: Path) -> None:
    expected = {
        FAILURE_AUDIT_JSON_PATH: FAILURE_AUDIT_JSON_FILE_SHA256,
        FAILURE_AUDIT_MARKDOWN_PATH: FAILURE_AUDIT_MARKDOWN_FILE_SHA256,
        FAILURE_AUDIT_SCHEMA_PATH: FAILURE_AUDIT_SCHEMA_FILE_SHA256,
        MARKER_REPAIR_PATH: MARKER_REPAIR_FILE_SHA256,
        source.RUNNER_PATH: FROZEN_RUNNER_FILE_SHA256,
    }
    for relative_path, expected_sha256 in expected.items():
        if candidate.file_sha256(repo_root / relative_path) != expected_sha256:
            raise IndependentCandidateProtocolError(
                f"失败审计或 marker repair 组件漂移: {relative_path}"
            )
    report = _load_json(repo_root / FAILURE_AUDIT_JSON_PATH)
    integrity = report.get("source_integrity", {})
    if (
        integrity.get("inventory_sha256") != FAILED_EVIDENCE_INVENTORY_SHA256
        or integrity.get("file_count") != FAILED_EVIDENCE_FILE_COUNT
        or integrity.get("total_size_bytes") != FAILED_EVIDENCE_TOTAL_SIZE_BYTES
        or report.get("execution_boundary", {}).get("continuation_allowed") is not False
        or report.get("interpretation", {}).get("treatment_effect_estimated")
        is not False
    ):
        raise IndependentCandidateProtocolError("formal failure audit 语义发生漂移")


def _opaque_id(kind: str, checkpoint_id: str, sequence: int, condition: str) -> str:
    payload = "|".join(
        (OPAQUE_ID_SEED, kind, checkpoint_id, str(sequence), condition)
    ).encode()
    return f"{kind}-{hashlib.sha256(payload).hexdigest()[:24]}"


def _independent_schedule(parent_schedule: dict[str, Any]) -> dict[str, Any]:
    schedule = copy.deepcopy(parent_schedule)
    for checkpoint in schedule["checkpoints"]:
        for arm in checkpoint["arms"]:
            arm["opaque_clone_id"] = _opaque_id(
                "clone",
                checkpoint["checkpoint_id"],
                arm["sequence"],
                arm["condition"],
            )
            arm["opaque_evaluation_id"] = _opaque_id(
                "evaluation",
                checkpoint["checkpoint_id"],
                arm["sequence"],
                arm["condition"],
            )
    return schedule


def _frozen_independent_components(repo_root: Path) -> dict[str, str]:
    return {
        path: candidate.file_sha256(repo_root / path)
        for path in FROZEN_INDEPENDENT_COMPONENT_PATHS
    }


def _normalize_schedule_ids(schedule: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(schedule)
    for checkpoint in normalized["checkpoints"]:
        for arm in checkpoint["arms"]:
            arm["opaque_clone_id"] = "<opaque-clone-id>"
            arm["opaque_evaluation_id"] = "<opaque-evaluation-id>"
    return normalized


def validate_schedule_delta(
    value: dict[str, Any], parent_manifest: dict[str, Any]
) -> dict[str, Any]:
    if _normalize_schedule_ids(value["schedule"]) != _normalize_schedule_ids(
        parent_manifest["schedule"]
    ):
        raise IndependentCandidateProtocolError(
            "新 identity 改写了冻结 schedule 的非 opaque-ID 字段"
        )
    new_arms = [
        arm
        for checkpoint in value["schedule"]["checkpoints"]
        for arm in checkpoint["arms"]
    ]
    old_arms = [
        arm
        for checkpoint in parent_manifest["schedule"]["checkpoints"]
        for arm in checkpoint["arms"]
    ]
    new_clones = {arm["opaque_clone_id"] for arm in new_arms}
    new_evaluations = {arm["opaque_evaluation_id"] for arm in new_arms}
    old_clones = {arm["opaque_clone_id"] for arm in old_arms}
    old_evaluations = {arm["opaque_evaluation_id"] for arm in old_arms}
    if (
        len(new_arms) != 36
        or len(new_clones) != 36
        or len(new_evaluations) != 36
        or new_clones & old_clones
        or new_evaluations & old_evaluations
    ):
        raise IndependentCandidateProtocolError(
            "新 opaque identity 数量、唯一性或独立性无效"
        )
    return {
        "arm_count": len(new_arms),
        "new_clone_id_count": len(new_clones),
        "new_evaluation_id_count": len(new_evaluations),
        "old_identity_overlap": 0,
    }


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    parent_manifest = _parent_manifest(repo_root)
    _verify_failure_audit(repo_root)
    value = copy.deepcopy(parent_manifest)
    value.update(
        {
            "$schema": "../schemas/forge-contract-driven-repair-mechanism-v2-candidate.schema.json",
            "schema_version": SCHEMA_VERSION,
            "document_type": DOCUMENT_TYPE,
            "issue_url": ISSUE_URL,
            "status": "independent_formal_identity_candidate_not_execution_authorized",
        }
    )
    value["development_revision"] = {
        "identity_baseline_revision": IDENTITY_BASELINE_REVISION,
        "candidate_implementation_revision": None,
        "execution_revision_policy": (
            "future_authorized_release_must_be_clean_main_equal_origin_main_descendant_of_identity_baseline"
        ),
        "execution_requires_release_branch": "main",
    }
    value["authorization"] = {
        "identity_implementation_authorized": True,
        "availability_execution_completed": False,
        "credential_read_authorized": False,
        "provider_calls_authorized": False,
        "model_creation_authorized": False,
        "model_tokens_authorized": False,
        "docker_session_creation_authorized": False,
        "formal_collection_execution_authorized": False,
        "formal_attempts_authorized": False,
        "formal_evidence_write_authorized": False,
        "execution_started": False,
    }
    evidence = copy.deepcopy(parent_manifest["candidate_evidence"])
    evidence.update(
        {
            "directory": EVIDENCE_DIRECTORY,
            "batch_report": "reports/contract-driven-repair-mechanism-v2.json",
            "writes_authorized": False,
            "availability_marker_write_authorized": False,
            "formal_evidence_write_authorized": False,
            "historical_evidence_reused": False,
        }
    )
    evidence["authorized_write_paths"] = [
        evidence["batch_marker"],
        evidence["batch_report"],
        "checkpoints/{checkpoint_sequence:02d}-{checkpoint_slug}/checkpoint.json",
        "checkpoints/{checkpoint_sequence:02d}-{checkpoint_slug}/experiment.jsonl",
        evidence["attempt_template"],
        evidence["result_template"],
        "attempts/{sequence:02d}-{opaque_clone_id}/experiment.jsonl",
        "attempts/{sequence:02d}-{opaque_clone_id}/runtime-events.jsonl",
        "attempts/{sequence:02d}-{opaque_clone_id}/candidate.json",
    ]
    value["candidate_evidence"] = evidence
    value["schedule"] = _independent_schedule(parent_manifest["schedule"])
    value["availability_receipt"] = {
        "required_before_formal_execution": True,
        "status": "pending_independent_execution_authorization",
        "marker_path": evidence["availability_marker"],
        "marker_must_be_created_in_new_evidence_root": True,
        "historical_availability_reused": False,
        "provider_calls_authorized_in_candidate": False,
    }
    availability_execution = copy.deepcopy(parent_manifest["availability_execution"])
    availability_execution.update(
        {
            "status": "independent_execution_not_authorized",
            "credential_read_authorized": False,
            "execution_authorized": False,
            "marker_write_authorized": False,
            "model_creation_authorized": False,
            "model_tokens_authorized": False,
            "provider_calls_authorized": False,
            "historical_parent_availability_reused": False,
            "result_observed": False,
        }
    )
    value["availability_execution"] = availability_execution
    value["availability_execution_runtime"] = {
        "protocol_path": PROTOCOL_PATH,
        "runner_path": RUNNER_PATH,
        "commands": ["availability"],
        "availability_execution_authorized": False,
        "historical_availability_reused": False,
        "fail_closed_without_separate_authorization": True,
    }
    formal_execution = copy.deepcopy(parent_manifest["formal_execution"])
    formal_execution.update(
        {
            "protocol_path": PROTOCOL_PATH,
            "runner_path": RUNNER_PATH,
            "batch_report": evidence["batch_report"],
            "marker_repair_path": MARKER_REPAIR_PATH,
            "marker_repair_file_sha256": MARKER_REPAIR_FILE_SHA256,
            "frozen_runner_file_sha256": FROZEN_RUNNER_FILE_SHA256,
            "execution_authorized": False,
        }
    )
    formal_execution["preflight"] = {
        "before_credential_model_provider_marker_or_docker_session": True,
        "require_branch_after_release": "main",
        "require_head_equals_origin_main_after_release": True,
        "require_clean_descendant_revision": IDENTITY_BASELINE_REVISION,
        "verify_parent_failure_audit_and_component_hashes": True,
        "verify_compile_image_id": True,
        "verify_zero_managed_resources": True,
        "verify_old_evidence_inventory_read_only": True,
        "verify_new_evidence_directory_absent": True,
        "verify_provider_config_or_credential": False,
        "creates_evidence_or_marker": False,
    }
    value["formal_execution"] = formal_execution
    value["independent_identity"] = {
        "strategy": "new_36_arm_identity_from_zero",
        "opaque_id_seed": OPAQUE_ID_SEED,
        "parent_manifest_path": source.MANIFEST_PATH,
        "parent_manifest_canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "parent_manifest_file_sha256": PARENT_MANIFEST_FILE_SHA256,
        "failed_identity": {
            "evidence_directory": OLD_EVIDENCE_DIRECTORY,
            "inventory_sha256": FAILED_EVIDENCE_INVENTORY_SHA256,
            "file_count": FAILED_EVIDENCE_FILE_COUNT,
            "total_size_bytes": FAILED_EVIDENCE_TOTAL_SIZE_BYTES,
            "failure_audit_json_path": FAILURE_AUDIT_JSON_PATH,
            "failure_audit_json_file_sha256": FAILURE_AUDIT_JSON_FILE_SHA256,
            "single_observed_arm_sequence": 1,
            "single_observed_arm_condition": "t2",
            "included_in_primary_or_secondary_analysis": False,
            "continuation_retry_replacement_backfill_allowed": False,
        },
        "independence": {
            "historical_availability_reused": False,
            "historical_checkpoint_imported": False,
            "historical_arm_imported": False,
            "historical_marker_imported": False,
            "historical_ledger_imported": False,
            "historical_result_imported": False,
            "historical_tokens_imported": False,
            "historical_outcome_imported": False,
            "new_evidence_directory": True,
            "new_opaque_clone_ids": True,
            "new_opaque_evaluation_ids": True,
        },
        "marker_repair": {
            "path": MARKER_REPAIR_PATH,
            "file_sha256": MARKER_REPAIR_FILE_SHA256,
            "frozen_runner_path": source.RUNNER_PATH,
            "frozen_runner_file_sha256": FROZEN_RUNNER_FILE_SHA256,
            "frozen_runner_modified": False,
            "required_for_future_execution": True,
        },
        "execution_authorization_required": True,
        "qualification_is_not_treatment_evidence": True,
    }
    value["independent_runtime"] = {
        "commands_allowed_without_execution_authorization": [
            "validate",
            "plan",
            "qualify",
            "preflight",
        ],
        "commands_fail_closed_without_separate_authorization": [
            "availability",
            "batch",
            "report",
            "audit",
        ],
        "provider_calls": 0,
        "credential_reads": 0,
        "docker_sessions_created": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
    }
    frozen_independent = _frozen_independent_components(repo_root)
    value["frozen_independent_components"] = frozen_independent
    value["frozen_formal_execution_components"] = {
        **copy.deepcopy(parent_manifest["frozen_formal_execution_components"]),
        PROTOCOL_PATH: frozen_independent[PROTOCOL_PATH],
        RUNNER_PATH: frozen_independent[RUNNER_PATH],
    }
    return value


def validate_allowed_delta(
    value: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    parent_manifest = _parent_manifest(repo_root)
    for field in source.parent.parent.parent.SCIENTIFIC_CONTRACT_FIELDS:
        if field == "schedule":
            continue
        if value.get(field) != parent_manifest.get(field):
            raise IndependentCandidateProtocolError(
                f"新 identity 改写父科学合同: {field}"
            )
    if value["budget_candidate"] != parent_manifest["budget_candidate"]:
        raise IndependentCandidateProtocolError("新 identity 改写冻结预算")
    if value["transport_and_stopping"] != parent_manifest["transport_and_stopping"]:
        raise IndependentCandidateProtocolError("新 identity 改写冻结停止规则")
    if value["formal_execution_tasks"] != parent_manifest["formal_execution_tasks"]:
        raise IndependentCandidateProtocolError("新 identity 改写 formal task 输入")
    schedule = validate_schedule_delta(value, parent_manifest)
    if value != generate_manifest(repo_root):
        raise IndependentCandidateProtocolError("新 identity 包含未预注册差异")
    return {
        "status": "passed",
        **schedule,
        "historical_outcomes_imported": False,
        "formal_collection_execution_authorized": False,
        "provider_calls": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
    }


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-contract-driven-repair-mechanism-v2-candidate.schema.json",
        "title": "Forge contract-driven repair mechanism v2 independent candidate",
        "const": manifest,
    }


def validate_manifest(
    value: dict[str, Any],
    repo_root: Path = REPO_ROOT,
    *,
    check_schema_file: bool = True,
) -> dict[str, Any]:
    if value != generate_manifest(repo_root):
        raise IndependentCandidateProtocolError(
            "新 identity manifest 与确定性生成结果不一致"
        )
    validate_allowed_delta(value, repo_root)
    authorization = value["authorization"]
    if authorization.get("identity_implementation_authorized") is not True:
        raise IndependentCandidateProtocolError("identity 实现授权未冻结")
    forbidden = set(authorization) - {
        "identity_implementation_authorized",
        "execution_started",
    }
    if any(authorization[field] is not False for field in forbidden):
        raise IndependentCandidateProtocolError("候选 identity 包含真实执行授权")
    if authorization.get("execution_started") is not False:
        raise IndependentCandidateProtocolError("候选 identity 不得预写已开始")
    if value["candidate_evidence"]["directory"] == OLD_EVIDENCE_DIRECTORY:
        raise IndependentCandidateProtocolError("新 identity 复用了旧 evidence root")
    schema = generate_schema(value)
    jsonschema.Draft202012Validator.check_schema(schema)
    if check_schema_file:
        stored = _load_json(repo_root / SCHEMA_PATH)
        if stored != schema:
            raise IndependentCandidateProtocolError("候选 const Schema 发生漂移")
        jsonschema.validate(value, stored)
    return value


def load_manifest(
    path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    return validate_manifest(_load_json(path), repo_root)


def verify_frozen_components(
    manifest: dict[str, Any], repo_root: Path = REPO_ROOT
) -> None:
    validate_manifest(manifest, repo_root)
    if manifest["frozen_independent_components"] != (
        _frozen_independent_components(repo_root)
    ):
        raise IndependentCandidateProtocolError("新 identity 组件 SHA-256 漂移")


def plan_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    validated = validate_manifest(manifest)
    schedule = validate_schedule_delta(validated, _parent_manifest(REPO_ROOT))
    return {
        "status": "independent_formal_identity_candidate_not_execution_authorized",
        "manifest_sha256": candidate.canonical_sha256(validated),
        "project_count": len(validated["schedule"]["projects"]),
        "checkpoint_count": len(validated["schedule"]["checkpoints"]),
        **schedule,
        "max_provider_request_attempts": validated["formal_execution"][
            "formal_provider_request_attempt_limit"
        ],
        "max_recorded_tokens": validated["budget_candidate"][
            "total_max_recorded_tokens"
        ],
        "old_observed_arm_excluded": True,
        "execution_authorization_required": True,
        "provider_calls": 0,
        "credential_reads": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
        "model_tokens": 0,
    }


def write_artifacts(repo_root: Path = REPO_ROOT) -> None:
    manifest = generate_manifest(repo_root)
    schema = generate_schema(manifest)
    for relative_path, value in ((MANIFEST_PATH, manifest), (SCHEMA_PATH, schema)):
        path = repo_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate", "delta", "plan"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    if args.command == "generate":
        write_artifacts()
    manifest = load_manifest(args.manifest)
    if args.command == "delta":
        result: Any = validate_allowed_delta(manifest)
    elif args.command == "plan":
        result = plan_summary(manifest)
    else:
        result = {
            "status": "generated" if args.command == "generate" else "valid",
            "manifest_sha256": candidate.canonical_sha256(manifest),
            "provider_calls": 0,
            "credential_reads": 0,
            "formal_attempts": 0,
            "formal_evidence_writes": 0,
            "model_tokens": 0,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
