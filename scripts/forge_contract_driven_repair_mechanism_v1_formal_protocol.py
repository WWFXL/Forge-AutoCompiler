#!/usr/bin/env python3
"""生成并校验契约驱动修复 mechanism v1 formal collection 执行身份。"""

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

import forge_contract_driven_repair_mechanism_v1_availability_execution_protocol as parent  # noqa: E402

SCHEMA_VERSION = "forge-contract-driven-repair-mechanism-v1-formal-execution-1.0.0"
DOCUMENT_TYPE = "forge_contract_driven_repair_mechanism_v1_formal_execution"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/363"
AVAILABILITY_AUDIT_RELEASE_REVISION = "c04507aa31d0352bd3bc05b97448a4809e149d2e"
AVAILABILITY_EXECUTION_REVISION = "09d7ff36ca081f5bfa39f8e1d6f3b3daa53c93a0"
AVAILABILITY_MANIFEST_CANONICAL_SHA256 = (
    "cf21d2c228e46b39a3287d3c9ab7139c9f24d8ba36990e4b8e94475c9b0d7839"
)
AVAILABILITY_MANIFEST_FILE_SHA256 = (
    "83d78d1a0512472ef45a801f8d37537effc4f43fbe4244dc936cd14b6cf44e08"
)
AVAILABILITY_MARKER_FILE_SHA256 = (
    "8527d64acc50a88ea0d5f8b64fc25971d68294fb142b043f1e889586ad088bee"
)
AVAILABILITY_AUDIT_JSON_FILE_SHA256 = (
    "2837f4c2f5e003641d889476edad7be7378af8bb6094bec2b0668ca94fe572c1"
)
AVAILABILITY_AUDIT_MD_FILE_SHA256 = (
    "8631bd31374232a9b18dd87e29e91fadf6ef9105bb7e2c75014d7658b52cedb5"
)

PROTOCOL_PATH = "scripts/forge_contract_driven_repair_mechanism_v1_formal_protocol.py"
RUNNER_PATH = "scripts/forge_contract_driven_repair_mechanism_v1_formal_runner.py"
MANIFEST_PATH = (
    "benchmarks/manifests/cpp-contract-driven-repair-mechanism-v1-formal-execution.json"
)
SCHEMA_PATH = "benchmarks/schemas/forge-contract-driven-repair-mechanism-v1-formal-execution.schema.json"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-contract-driven-repair-mechanism-v1-formal-execution.md"
TASK_PLAN_PATH = "benchmarks/manifests/cpp-stage-c-task-qualification.json"
AVAILABILITY_AUDIT_JSON_PATH = (
    "benchmarks/reports/cpp-contract-driven-repair-mechanism-v1-availability-audit.json"
)
AVAILABILITY_AUDIT_MD_PATH = (
    "benchmarks/reports/cpp-contract-driven-repair-mechanism-v1-availability-audit.md"
)

DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_PATH

FROZEN_FORMAL_COMPONENT_PATHS = (
    parent.MANIFEST_PATH,
    parent.SCHEMA_PATH,
    parent.PREREGISTRATION_PATH,
    parent.PROTOCOL_PATH,
    parent.RUNNER_PATH,
    AVAILABILITY_AUDIT_JSON_PATH,
    AVAILABILITY_AUDIT_MD_PATH,
    TASK_PLAN_PATH,
    "scripts/forge_stage_c_runner.py",
    "scripts/forge_stage_c_v8_workspace_remediation_runner.py",
    "scripts/forge_runtime_v3_three_arm_qualification.py",
    "scripts/forge_opaque_build_provenance_gate.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v2.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v3.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_schemas.py",
    "backend/packages/harness/deerflow/compile/candidate_verifier.py",
    "backend/packages/harness/deerflow/compile/external_evaluator_v3.py",
    "backend/packages/harness/deerflow/compile/operations.py",
    "backend/packages/harness/deerflow/compile/evidence.py",
    "backend/packages/harness/deerflow/tools/bound_compile_tools.py",
    "backend/packages/harness/deerflow/models/factory.py",
    "config.yaml",
    PREREGISTRATION_PATH,
    PROTOCOL_PATH,
    RUNNER_PATH,
)


class FormalProtocolError(RuntimeError):
    """formal identity、父 availability、执行输入或授权边界发生漂移。"""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FormalProtocolError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise FormalProtocolError(f"JSON 顶层必须为对象: {path}")
    return value


def _parent_manifest(repo_root: Path) -> dict[str, Any]:
    path = repo_root / parent.MANIFEST_PATH
    value = parent.load_manifest(path, repo_root)
    if parent.parent.parent.candidate.canonical_sha256(value) != (
        AVAILABILITY_MANIFEST_CANONICAL_SHA256
    ):
        raise FormalProtocolError(
            "父 availability execution canonical identity 发生漂移"
        )
    if parent.parent.parent.candidate.file_sha256(path) != (
        AVAILABILITY_MANIFEST_FILE_SHA256
    ):
        raise FormalProtocolError("父 availability execution manifest 文件发生漂移")
    return value


def _frozen_formal_components(repo_root: Path) -> dict[str, str]:
    return {
        path: parent.parent.parent.candidate.file_sha256(repo_root / path)
        for path in FROZEN_FORMAL_COMPONENT_PATHS
    }


def _execution_tasks(
    candidate_tasks: list[dict[str, Any]], repo_root: Path
) -> list[dict[str, Any]]:
    plan = _load_json(repo_root / TASK_PLAN_PATH)
    result: list[dict[str, Any]] = []
    for candidate_task in candidate_tasks:
        task_id = candidate_task["task_id"]
        matches = [
            item for item in plan.get("tasks", []) if item.get("task_id") == task_id
        ]
        if len(matches) != 1:
            raise FormalProtocolError(
                f"formal task runtime input 缺失或重复: {task_id}"
            )
        planned = matches[0]
        if planned.get("target") != candidate_task["contract"]["target"]:
            raise FormalProtocolError(f"formal task target contract 漂移: {task_id}")
        oracle = planned.get("oracle")
        if (
            not isinstance(oracle, dict)
            or parent.parent.parent.candidate.canonical_sha256(oracle)
            != candidate_task["contract"]["functional_oracle"][
                "definition_canonical_sha256"
            ]
        ):
            raise FormalProtocolError(f"formal task oracle contract 漂移: {task_id}")
        recipe = planned.get("reference_recipe")
        if (
            not isinstance(recipe, list)
            or not recipe
            or any(not isinstance(command, str) or not command for command in recipe)
        ):
            raise FormalProtocolError(f"formal task reference recipe 无效: {task_id}")
        source = candidate_task["source"]
        result.append(
            {
                "task_id": task_id,
                "repository_url": source["repository_url"],
                "commit_sha": source["commit_sha"],
                "source_snapshot_sha256": source["source_snapshot_sha256"],
                "submodule_commits": copy.deepcopy(source["submodule_commits"]),
                "build_system_capabilities": copy.deepcopy(
                    source["build_system_capabilities"]
                ),
                "selected_build_system": source["selected_build_system"],
                "target_contract": copy.deepcopy(candidate_task["contract"]["target"]),
                "reference_recipe": copy.deepcopy(recipe),
                "reference_recipe_canonical_sha256": (
                    parent.parent.parent.candidate.canonical_sha256(recipe)
                ),
                "oracle": copy.deepcopy(oracle),
                "oracle_canonical_sha256": (
                    parent.parent.parent.candidate.canonical_sha256(oracle)
                ),
                "historical_model_outcomes_imported": False,
            }
        )
    return result


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    parent_manifest = _parent_manifest(repo_root)
    value = copy.deepcopy(parent_manifest)
    value.update(
        {
            "$schema": "../schemas/forge-contract-driven-repair-mechanism-v1-formal-execution.schema.json",
            "schema_version": SCHEMA_VERSION,
            "document_type": DOCUMENT_TYPE,
            "issue_url": ISSUE_URL,
            "status": "formal_collection_authorized_not_started",
        }
    )
    value["development_revision"] = {
        **copy.deepcopy(parent_manifest["development_revision"]),
        "availability_audit_release_revision": AVAILABILITY_AUDIT_RELEASE_REVISION,
        "formal_execution_implementation_revision": None,
        "execution_revision_policy": "clean_main_equal_origin_main_descendant_of_availability_audit_release",
        "formal_execution_requires_release_branch": "main",
    }
    value["authorization"] = {
        "identity_implementation_authorized": True,
        "availability_execution_completed": True,
        "credential_read_authorized": True,
        "provider_calls_authorized": True,
        "model_creation_authorized": True,
        "model_tokens_authorized": True,
        "docker_session_creation_authorized": True,
        "formal_collection_execution_authorized": True,
        "formal_attempts_authorized": True,
        "formal_evidence_write_authorized": True,
        "execution_started": False,
    }
    evidence = copy.deepcopy(parent_manifest["candidate_evidence"])
    evidence.update(
        {
            "writes_authorized": True,
            "availability_marker_write_authorized": False,
            "formal_evidence_write_authorized": True,
            "authorized_write_paths": [
                evidence["batch_marker"],
                evidence["batch_report"],
                "checkpoints/{checkpoint_sequence:02d}-{checkpoint_slug}/checkpoint.json",
                "checkpoints/{checkpoint_sequence:02d}-{checkpoint_slug}/experiment.jsonl",
                evidence["attempt_template"],
                evidence["result_template"],
                "attempts/{sequence:02d}-{opaque_clone_id}/experiment.jsonl",
                "attempts/{sequence:02d}-{opaque_clone_id}/runtime-events.jsonl",
                "attempts/{sequence:02d}-{opaque_clone_id}/candidate.json",
            ],
        }
    )
    value["candidate_evidence"] = evidence
    value["availability_receipt"] = {
        "manifest_path": parent.MANIFEST_PATH,
        "manifest_canonical_sha256": AVAILABILITY_MANIFEST_CANONICAL_SHA256,
        "manifest_file_sha256": AVAILABILITY_MANIFEST_FILE_SHA256,
        "execution_revision": AVAILABILITY_EXECUTION_REVISION,
        "marker_path": evidence["availability_marker"],
        "marker_file_sha256": AVAILABILITY_MARKER_FILE_SHA256,
        "required_status": "passed",
        "required_passed": True,
        "request_attempt_count": 1,
        "recorded_total_tokens": 58,
        "formal_batch_creation_authorized_in_parent": False,
        "read_only": True,
        "audit_json_path": AVAILABILITY_AUDIT_JSON_PATH,
        "audit_json_file_sha256": AVAILABILITY_AUDIT_JSON_FILE_SHA256,
        "audit_markdown_path": AVAILABILITY_AUDIT_MD_PATH,
        "audit_markdown_file_sha256": AVAILABILITY_AUDIT_MD_FILE_SHA256,
    }
    value["formal_execution_tasks"] = _execution_tasks(value["tasks"], repo_root)
    value["formal_execution"] = {
        "protocol_path": PROTOCOL_PATH,
        "runner_path": RUNNER_PATH,
        "commands": ["validate", "plan", "preflight", "batch", "report", "audit"],
        "strictly_serial": True,
        "availability_is_not_repeated": True,
        "batch_marker": evidence["batch_marker"],
        "batch_report": evidence["batch_report"],
        "checkpoint_marker_template": "checkpoints/{checkpoint_sequence:02d}-{checkpoint_slug}/checkpoint.json",
        "checkpoint_ledger_template": "checkpoints/{checkpoint_sequence:02d}-{checkpoint_slug}/experiment.jsonl",
        "arm_marker_template": evidence["attempt_template"],
        "arm_result_template": evidence["result_template"],
        "arm_ledger_template": "attempts/{sequence:02d}-{opaque_clone_id}/experiment.jsonl",
        "arm_runtime_events_template": "attempts/{sequence:02d}-{opaque_clone_id}/runtime-events.jsonl",
        "arm_candidate_template": "attempts/{sequence:02d}-{opaque_clone_id}/candidate.json",
        "marker_create_once": True,
        "checkpoint_capture_timing": parent_manifest["checkpoint_contract"][
            "capture_timing"
        ],
        "checkpoint_parent_model_requests": 0,
        "formal_arm_count": 36,
        "formal_checkpoint_count": 12,
        "formal_provider_request_attempt_limit": 288,
        "endpoint_censored_arm_stop_count": 2,
        "generalized_p2": {
            "required_parent_reason": "opaque_wrapper",
            "accepted_proof_mode": "trusted_direct_compiler_tool_surface",
            "supported_build_systems": ["cmake", "make", "autotools"],
            "direct_command_record_write_forbidden": True,
        },
        "preflight": {
            "before_model_provider_batch_marker_or_docker_session": True,
            "require_branch": "main",
            "require_head_equals_origin_main": True,
            "require_clean_descendant_revision": AVAILABILITY_AUDIT_RELEASE_REVISION,
            "verify_parent_and_component_hashes": True,
            "verify_passed_availability_marker_hash_and_semantics": True,
            "verify_compile_image_id": True,
            "verify_zero_managed_resources": True,
            "verify_formal_evidence_absent": True,
            "verify_provider_config_and_credential_presence": True,
            "creates_evidence_or_marker": False,
        },
    }
    value["frozen_formal_execution_components"] = _frozen_formal_components(repo_root)
    return value


def validate_allowed_delta(
    value: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    parent_manifest = _parent_manifest(repo_root)
    for field in parent.parent.parent.SCIENTIFIC_CONTRACT_FIELDS:
        if value.get(field) != parent_manifest.get(field):
            raise FormalProtocolError(f"formal execution 改写父科学合同: {field}")
    if value["schedule"] != parent_manifest["schedule"]:
        raise FormalProtocolError("formal execution 改写冻结 schedule")
    if value["budget_candidate"] != parent_manifest["budget_candidate"]:
        raise FormalProtocolError("formal execution 改写冻结预算")
    if value["transport_and_stopping"] != parent_manifest["transport_and_stopping"]:
        raise FormalProtocolError("formal execution 改写冻结停止规则")
    if value != generate_manifest(repo_root):
        raise FormalProtocolError("formal execution 包含未预注册差异")
    return {
        "status": "passed",
        "availability_marker_sha256": AVAILABILITY_MARKER_FILE_SHA256,
        "formal_checkpoint_count": 12,
        "formal_arm_count": 36,
        "formal_provider_request_attempt_limit": 288,
        "formal_collection_execution_authorized": True,
        "provider_calls": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
    }


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-contract-driven-repair-mechanism-v1-formal-execution.schema.json",
        "title": "Forge contract-driven repair mechanism v1 formal execution",
        "const": manifest,
    }


def validate_manifest(
    value: dict[str, Any],
    repo_root: Path = REPO_ROOT,
    *,
    check_schema_file: bool = True,
) -> dict[str, Any]:
    if value != generate_manifest(repo_root):
        raise FormalProtocolError("formal execution manifest 与确定性生成结果不一致")
    validate_allowed_delta(value, repo_root)
    authorization = value["authorization"]
    for field in (
        "identity_implementation_authorized",
        "availability_execution_completed",
        "credential_read_authorized",
        "provider_calls_authorized",
        "model_creation_authorized",
        "model_tokens_authorized",
        "docker_session_creation_authorized",
        "formal_collection_execution_authorized",
        "formal_attempts_authorized",
        "formal_evidence_write_authorized",
    ):
        if authorization.get(field) is not True:
            raise FormalProtocolError(f"formal 授权不完整: {field}")
    if authorization.get("execution_started") is not False:
        raise FormalProtocolError("formal identity 在 manifest 中不得预写已开始")
    execution = value["formal_execution"]
    if (
        execution["formal_arm_count"] != 36
        or execution["formal_checkpoint_count"] != 12
        or execution["formal_provider_request_attempt_limit"] != 288
        or execution["endpoint_censored_arm_stop_count"] != 2
        or execution["strictly_serial"] is not True
        or execution["availability_is_not_repeated"] is not True
    ):
        raise FormalProtocolError("formal execution 规模、顺序或停止边界发生漂移")
    if len(value["formal_execution_tasks"]) != 6:
        raise FormalProtocolError("formal runtime task 输入必须恰好为六项")
    schema = generate_schema(value)
    jsonschema.Draft202012Validator.check_schema(schema)
    if check_schema_file:
        stored = _load_json(repo_root / SCHEMA_PATH)
        if stored != schema:
            raise FormalProtocolError("formal execution const Schema 发生漂移")
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
    if manifest["frozen_formal_execution_components"] != (
        _frozen_formal_components(repo_root)
    ):
        raise FormalProtocolError("formal execution component SHA-256 发生漂移")


def plan_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    validated = validate_manifest(manifest)
    return {
        "status": "formal_collection_authorized_not_started",
        "manifest_sha256": parent.parent.parent.candidate.canonical_sha256(validated),
        "availability_marker_sha256": AVAILABILITY_MARKER_FILE_SHA256,
        "project_count": len(validated["schedule"]["projects"]),
        "checkpoint_count": len(validated["schedule"]["checkpoints"]),
        "arm_count": sum(
            len(checkpoint["arms"])
            for checkpoint in validated["schedule"]["checkpoints"]
        ),
        "formal_provider_request_attempt_limit": validated["formal_execution"][
            "formal_provider_request_attempt_limit"
        ],
        "max_recorded_tokens": validated["budget_candidate"][
            "total_max_recorded_tokens"
        ],
        "endpoint_censored_arm_stop_count": validated["formal_execution"][
            "endpoint_censored_arm_stop_count"
        ],
        "formal_collection_execution_authorized": True,
        "provider_calls": 0,
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
            "manifest_sha256": parent.parent.parent.candidate.canonical_sha256(
                manifest
            ),
            "provider_calls": 0,
            "formal_attempts": 0,
            "formal_evidence_writes": 0,
            "model_tokens": 0,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
