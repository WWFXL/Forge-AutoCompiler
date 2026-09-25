#!/usr/bin/env python3
"""Issue #303 Phase 5 v3 独立授权评测协议。"""

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

import forge_agent_workflow_stage_b_phase5_v2_authorized_protocol as parent  # noqa: E402

candidate = parent.candidate

SCHEMA_VERSION = "forge-agent-workflow-stage-b-phase5-v3-authorized-1.0.0"
DOCUMENT_TYPE = "forge_agent_workflow_stage_b_phase5_v3_authorized"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/303"
AUTHORIZATION_BASELINE_COMMIT = "9f8c8ad47753f61f92fb6c2effa484acbd6caf14"
PARENT_MANIFEST_CANONICAL_SHA256 = "aa1f9ec280cbbecf91b5e10a9724e9b2462aed8dccc44bfb906c5e3e1ef962ed"
PARENT_MANIFEST_FILE_SHA256 = "057ef202498a969190bf914b041ebe045a5684c5a214b9ecf1ec1d74110db662"
AUDIT_REPORT_PATH = "benchmarks/reports/cpp-agent-workflow-stage-b-phase5-v2-audit.json"
AUDIT_REPORT_FILE_SHA256 = "9d636d779ac43c5eee2095d219333fb30cc9082a09db8201a0bec10971337ef0"
EVALUATOR_PATH = "backend/packages/harness/deerflow/compile/external_evaluator_v3.py"
EVALUATOR_FILE_SHA256 = "cfb5e3baeff772e54051925e6b0504eea25b6ba9284d8a5c6ad7135355fde79c"
EVALUATOR_VERSION = "forge-external-evaluator-1.2.0"
EVALUATOR_RULES_SHA256 = "5c5579f426bf2b805599dbc8341c351a31802c1ad396e16ce0687ff02b14e8aa"
MANIFEST_RELATIVE_PATH = "benchmarks/manifests/cpp-agent-workflow-stage-b-phase5-v3-authorized.json"
SCHEMA_RELATIVE_PATH = "benchmarks/schemas/forge-agent-workflow-stage-b-phase5-v3-authorized.schema.json"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-agent-workflow-stage-b-phase5-v3-authorized.md"
PROTOCOL_PATH = "scripts/forge_agent_workflow_stage_b_phase5_v3_authorized_protocol.py"
RUNNER_PATH = "scripts/forge_agent_workflow_stage_b_phase5_v3_authorized_runner.py"
EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-agent-workflow-stage-b-phase5-v3-authorized"

DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_RELATIVE_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_RELATIVE_PATH


class Phase5V3AuthorizedProtocolError(RuntimeError):
    """Phase 5 v3 授权 identity 或允许差异发生漂移。"""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase5V3AuthorizedProtocolError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise Phase5V3AuthorizedProtocolError(f"JSON 根节点必须是对象: {path}")
    return value


def _parent_manifest(repo_root: Path) -> dict[str, Any]:
    path = repo_root / parent.MANIFEST_RELATIVE_PATH
    value = parent.load_manifest(path, repo_root)
    if candidate.canonical_sha256(value) != PARENT_MANIFEST_CANONICAL_SHA256:
        raise Phase5V3AuthorizedProtocolError("Phase 5 v2 authorized 父 identity 发生漂移")
    if candidate.file_sha256(path) != PARENT_MANIFEST_FILE_SHA256:
        raise Phase5V3AuthorizedProtocolError("Phase 5 v2 authorized manifest 文件发生漂移")
    return value


def _evaluator_identity() -> dict[str, Any]:
    return {
        "name": "external-evaluator-v3",
        "path": EVALUATOR_PATH,
        "file_sha256": EVALUATOR_FILE_SHA256,
        "version": EVALUATOR_VERSION,
        "rules_sha256": EVALUATOR_RULES_SHA256,
        "oracle_execution_authority": "system_owned_post_build_fence_isolated_v1",
    }


def _frozen_components(repo_root: Path) -> dict[str, str]:
    paths = (
        parent.MANIFEST_RELATIVE_PATH,
        parent.PROTOCOL_PATH,
        parent.RUNNER_PATH,
        AUDIT_REPORT_PATH,
        EVALUATOR_PATH,
        PREREGISTRATION_PATH,
        PROTOCOL_PATH,
        RUNNER_PATH,
    )
    return {path: candidate.file_sha256(repo_root / path) for path in paths}


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    source = _parent_manifest(repo_root)
    if candidate.file_sha256(repo_root / AUDIT_REPORT_PATH) != AUDIT_REPORT_FILE_SHA256:
        raise Phase5V3AuthorizedProtocolError("Phase 5 v2 审计报告发生漂移")
    if candidate.file_sha256(repo_root / EVALUATOR_PATH) != EVALUATOR_FILE_SHA256:
        raise Phase5V3AuthorizedProtocolError("external evaluator v3 文件发生漂移")

    value = copy.deepcopy(source)
    value.update(
        {
            "$schema": "../schemas/forge-agent-workflow-stage-b-phase5-v3-authorized.schema.json",
            "schema_version": SCHEMA_VERSION,
            "document_type": DOCUMENT_TYPE,
            "issue_url": ISSUE_URL,
            "status": "authorized_not_executed",
            "baseline_commit": AUTHORIZATION_BASELINE_COMMIT,
        }
    )
    value["runtime_candidate"].update(
        {
            "protocol_path": PROTOCOL_PATH,
            "runner_path": RUNNER_PATH,
            "external_evaluator": "external-evaluator-v3",
            "evaluator_identity": _evaluator_identity(),
            "parent_lifecycle_runner_reused_without_modification": True,
        }
    )
    value["evidence_candidate"].update(
        {
            "directory": EVIDENCE_DIRECTORY,
            "batch_report": "reports/stage-b-phase5-v3.json",
            "historical_evidence_reused": False,
            "writes_authorized": True,
        }
    )
    value["authorized_execution"] = {
        "authorization_baseline_commit": AUTHORIZATION_BASELINE_COMMIT,
        "release_branch": "main",
        "release_revision_policy": "descendant_of_authorization_baseline_and_record_each_attempt",
        "parent_manifest_path": parent.MANIFEST_RELATIVE_PATH,
        "parent_manifest_canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "parent_manifest_file_sha256": PARENT_MANIFEST_FILE_SHA256,
        "source_audit_report_path": AUDIT_REPORT_PATH,
        "source_audit_report_file_sha256": AUDIT_REPORT_FILE_SHA256,
        "qualification_result_sha256": candidate.QUALIFICATION_RESULT_SHA256,
        "network_access_medium_env": "FORGE_NETWORK_ACCESS_MEDIUM",
        "network_access_medium": "ethernet",
        "reachability": copy.deepcopy(source["authorized_execution"]["reachability"]),
        "attempt_id_template": "phase5-v3-{task_id}-attempt-1",
        "thread_id_prefix": "phase5-v3",
        "evaluation_id_template": "phase5-v3-{task_id}-evaluation-v3",
        "task_marker_path": "tasks/{task_id}/attempt.json",
        "task_result_path": "tasks/{task_id}/result.json",
        "batch_marker": "markers/batch.json",
        "batch_report": "reports/stage-b-phase5-v3.json",
        "stage_c_decision_package": "reports/stage-c-decision.json",
        "resume_policy": "completed_contiguous_prefix_only",
        "commands": ["validate", "preflight", "reachability", "batch", "report"],
        "evaluator": _evaluator_identity(),
        "independence": {
            "v2_reachability_reused": False,
            "v2_task_attempts_reused": False,
            "v2_outcomes_imported": False,
            "v2_evidence_imported": False,
            "new_compile_session_per_task": True,
            "historical_results_used_for_statistical_estimation": False,
        },
    }
    value["frozen_authorized_components"] = _frozen_components(repo_root)
    return value


def validate_allowed_delta(value: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    source = _parent_manifest(repo_root)
    normalized = copy.deepcopy(value)
    actual_runtime = normalized.pop("runtime_candidate", None)
    actual_evidence = normalized.pop("evidence_candidate", None)
    actual_execution = normalized.pop("authorized_execution", None)
    actual_frozen = normalized.pop("frozen_authorized_components", None)
    identity_keys = ("$schema", "schema_version", "document_type", "issue_url", "status", "baseline_commit")
    actual_identity = {key: normalized.get(key) for key in identity_keys}
    for key in identity_keys:
        normalized[key] = source[key]
    normalized["runtime_candidate"] = copy.deepcopy(source["runtime_candidate"])
    normalized["evidence_candidate"] = copy.deepcopy(source["evidence_candidate"])
    normalized["authorized_execution"] = copy.deepcopy(source["authorized_execution"])
    normalized["frozen_authorized_components"] = copy.deepcopy(source["frozen_authorized_components"])
    if normalized != source:
        raise Phase5V3AuthorizedProtocolError("Phase 5 v3 包含未预注册的父 identity 差异")

    expected = generate_manifest(repo_root)
    expected_identity = {key: expected[key] for key in identity_keys}
    if (
        actual_identity != expected_identity
        or actual_runtime != expected["runtime_candidate"]
        or actual_evidence != expected["evidence_candidate"]
        or actual_execution != expected["authorized_execution"]
        or actual_frozen != expected["frozen_authorized_components"]
    ):
        raise Phase5V3AuthorizedProtocolError("Phase 5 v3 evaluator 或独立执行 identity 发生漂移")
    return {
        "status": "passed",
        "parent_manifest_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "evaluator_version": EVALUATOR_VERSION,
        "evaluator_rules_sha256": EVALUATOR_RULES_SHA256,
        "task_count": len(source["tasks"]),
        "task_order": source["schedule"]["order"],
        "historical_evidence_reused": False,
        "historical_outcomes_imported": False,
        "unbiased_success_rate_claim_allowed": False,
        "stage_c_authorized": False,
    }


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-agent-workflow-stage-b-phase5-v3-authorized.schema.json",
        "title": "Forge Agent Workflow Stage B Phase 5 v3 independent authorized evaluation",
        "const": manifest,
    }


def validate_manifest(value: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    expected = generate_manifest(repo_root)
    if value != expected:
        raise Phase5V3AuthorizedProtocolError("Phase 5 v3 authorized manifest 与确定性生成结果不一致")
    validate_allowed_delta(value, repo_root)
    authorization = value["authorization"]
    required_authorizations = (
        "provider_calls_authorized",
        "credential_read_authorized",
        "model_creation_authorized",
        "reachability_request_authorized",
        "docker_execution_authorized",
        "evidence_write_authorized",
        "formal_attempts_authorized",
    )
    if not all(authorization[key] is True for key in required_authorizations):
        raise Phase5V3AuthorizedProtocolError("Phase 5 v3 真实执行授权未闭合")
    expected_tokens = value["budget_candidate"]["batch_max_recorded_tokens"] + value["authorized_execution"]["reachability"]["maximum_recorded_tokens"]
    if authorization["model_tokens_authorized"] != expected_tokens:
        raise Phase5V3AuthorizedProtocolError("Phase 5 v3 授权 token ceiling 发生漂移")
    independence = value["authorized_execution"]["independence"]
    false_fields = (
        "v2_reachability_reused",
        "v2_task_attempts_reused",
        "v2_outcomes_imported",
        "v2_evidence_imported",
        "historical_results_used_for_statistical_estimation",
    )
    true_fields = ("new_compile_session_per_task",)
    if any(independence[key] is not False for key in false_fields) or any(independence[key] is not True for key in true_fields):
        raise Phase5V3AuthorizedProtocolError("Phase 5 v3 独立性声明无效")
    schema = generate_schema(expected)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(value, schema)
    return value


def load_manifest(path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    return validate_manifest(_load_json(path), repo_root)


def verify_frozen_components(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> None:
    validate_manifest(manifest, repo_root)
    if manifest["frozen_authorized_components"] != _frozen_components(repo_root):
        raise Phase5V3AuthorizedProtocolError("Phase 5 v3 authorized 组件发生漂移")


def write_artifacts(repo_root: Path = REPO_ROOT) -> None:
    manifest = generate_manifest(repo_root)
    schema = generate_schema(manifest)
    for relative_path, value in ((MANIFEST_RELATIVE_PATH, manifest), (SCHEMA_RELATIVE_PATH, schema)):
        path = repo_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate", "delta"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    if args.command == "generate":
        write_artifacts()
        manifest = load_manifest(args.manifest)
        result: Any = {"status": "generated", "manifest": MANIFEST_RELATIVE_PATH, "schema": SCHEMA_RELATIVE_PATH}
    else:
        manifest = load_manifest(args.manifest)
        result = validate_allowed_delta(manifest) if args.command == "delta" else {"status": "valid"}
    result["manifest_sha256"] = candidate.canonical_sha256(manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
