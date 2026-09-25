#!/usr/bin/env python3
"""Issue #307 Phase 5 v5 修复重评授权协议。"""

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

import forge_agent_workflow_stage_b_phase5_v3_authorized_protocol as v3  # noqa: E402
import forge_agent_workflow_stage_b_phase5_v4_remediation_authorized_protocol as parent  # noqa: E402

candidate = v3.candidate

SCHEMA_VERSION = "forge-agent-workflow-stage-b-phase5-v5-remediation-authorized-1.0.0"
DOCUMENT_TYPE = "forge_agent_workflow_stage_b_phase5_v5_remediation_authorized"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/307"
AUTHORIZATION_BASELINE_COMMIT = "d6b841585c9af0b473924329763eb424c4bb9eb4"
V3_MANIFEST_CANONICAL_SHA256 = (
    "191062f15d83bee8e1a323e67763dafdee2b9cc9bee6ac399971872f36e48747"
)
V3_MANIFEST_FILE_SHA256 = (
    "a6975472306bf4b8cf53ef864ec702d38e6c9fc38f54544ff907f5c5de262ef4"
)
V3_EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-agent-workflow-stage-b-phase5-v3-authorized"
V3_REPORT_PATH = "reports/stage-b-phase5-v3.json"
V3_REPORT_FILE_SHA256 = (
    "4a4b5f4610fc9f31ee0dd06285b1f2ba3ab7371a1fb9c454ac8b80ab2bb3a4aa"
)
V3_DECISION_PATH = "reports/stage-c-decision.json"
V3_DECISION_FILE_SHA256 = (
    "b8762865a3ef03017697c84ac9546844333feb79a6da58ae2a4ee76f8efdb951"
)
V3_SUCCESS_RESULT_SHA256 = {
    "yyjson": "72abc8ca35f11f4637a8fb61aa4c884c5151c03d0acbd807d8715e0722d5768e",
    "cppitertools": "8eca2ef4a262b0ce9f3688eb89f9d75b2bf1524cdb0cd80d845fe4a02db09297",
    "openh264": "573abb644cdae8ed70364521153cbb2d81c4180616307ab001c164bbd8d17399",
}
PARENT_MANIFEST_CANONICAL_SHA256 = (
    "deb33c2aafacd5926df0f16d2437db4f9f37bb80e49b462b0ca62b0572bcb28a"
)
PARENT_MANIFEST_FILE_SHA256 = (
    "d69afcce6f8c266be3653f6287c9813a72b74f255ea8309cb03837e7f2f981ef"
)
PARENT_EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-agent-workflow-stage-b-phase5-v4-remediation-authorized"
PARENT_REPORT_PATH = "reports/stage-b-phase5-v4-remediation.json"
PARENT_REPORT_FILE_SHA256 = (
    "56b620ad98997ef76ad675396545c4a89d6c3267393282cc5622906c5749f448"
)
PARENT_BATCH_MARKER_PATH = "markers/batch.json"
PARENT_BATCH_MARKER_FILE_SHA256 = (
    "1034b1e8e98915d70f5288dafb8d449e9d381d4708b40f64639120d76775b372"
)
PARENT_SUCCESS_RESULT_SHA256 = {
    "c-ares": "1fbddbead6e050f4b815c0400a457f607f717da216e0766d5de1ac5d66677521",
    "libass": "5f5cecc9f71c9a7607c3d12db7052b09cc849d29f88f8f7524a2e7f610643af8",
}
FULL_TASK_ORDER = (
    "yyjson",
    "cppitertools",
    "openh264",
    "uwebsockets",
    "c-ares",
    "libass",
)
REMEDIATION_TASK_ORDER = ("uwebsockets",)
EVALUATOR_PATH = "backend/packages/harness/deerflow/compile/external_evaluator_v4.py"
EVALUATOR_FILE_SHA256 = (
    "9009c400b1b54d9ad05411f1a64124423cf50d8ba49bfa2d13071d9bedad4613"
)
EVALUATOR_VERSION = "forge-external-evaluator-1.3.0"
EVALUATOR_RULES_SHA256 = (
    "e5ad0acc6dd9f841258daccfd8d659f032e457139e8d09685388d04304b6e3d1"
)
RUNTIME_PATH = "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v2.py"
BASE_RUNTIME_PATH = (
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime.py"
)
NODE_PATH = "backend/packages/harness/deerflow/compile/agent_workflow_node.py"
MANIFEST_RELATIVE_PATH = "benchmarks/manifests/cpp-agent-workflow-stage-b-phase5-v5-remediation-authorized.json"
SCHEMA_RELATIVE_PATH = "benchmarks/schemas/forge-agent-workflow-stage-b-phase5-v5-remediation-authorized.schema.json"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-agent-workflow-stage-b-phase5-v5-remediation-authorized.md"
PROTOCOL_PATH = (
    "scripts/forge_agent_workflow_stage_b_phase5_v5_remediation_authorized_protocol.py"
)
RUNNER_PATH = (
    "scripts/forge_agent_workflow_stage_b_phase5_v5_remediation_authorized_runner.py"
)
EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-agent-workflow-stage-b-phase5-v5-remediation-authorized"

UWEBSOCKETS_EXECUTION_GUIDANCE = {
    "strategy_id": "uwebsockets-make-examples-v1",
    "dependency": {
        "command": "git submodule update --init uSockets",
        "command_role": "dependency",
        "workdir": "/workspace/repo",
    },
    "build": {
        "command": "make examples",
        "command_role": "build",
        "workdir": "/workspace/repo",
    },
    "artifact_stage": {
        "artifact_paths": ["HelloWorld", "uSockets/uSockets.a"],
        "source_paths": [
            "/workspace/repo/HelloWorld",
            "/workspace/repo/uSockets/uSockets.a",
        ],
    },
    "constraints": [
        "Use the tool timeout instead of shell timeout wrappers.",
        "Do not truncate command output with pipes, tail, or head.",
        "Do not run a manual smoke test; the external evaluator owns the service probe.",
        "After artifact staging, submit immediately with build_system make and the successful make examples command as supporting evidence.",
    ],
}

DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_RELATIVE_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_RELATIVE_PATH


class Phase5V5RemediationAuthorizedProtocolError(RuntimeError):
    """Phase 5 v5 修复重评 identity 或允许差异发生漂移。"""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase5V5RemediationAuthorizedProtocolError(
            f"无法读取 JSON: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise Phase5V5RemediationAuthorizedProtocolError(
            f"JSON 根节点必须是对象: {path}"
        )
    return value


def _parent_manifest(repo_root: Path) -> dict[str, Any]:
    path = repo_root / parent.MANIFEST_RELATIVE_PATH
    value = _load_json(path)
    if candidate.canonical_sha256(value) != PARENT_MANIFEST_CANONICAL_SHA256:
        raise Phase5V5RemediationAuthorizedProtocolError(
            "Phase 5 v4 remediation 父 identity 发生漂移"
        )
    if candidate.file_sha256(path) != PARENT_MANIFEST_FILE_SHA256:
        raise Phase5V5RemediationAuthorizedProtocolError(
            "Phase 5 v4 remediation manifest 文件发生漂移"
        )
    return value


def _v3_manifest(repo_root: Path) -> dict[str, Any]:
    path = repo_root / v3.MANIFEST_RELATIVE_PATH
    value = _load_json(path)
    if candidate.canonical_sha256(value) != V3_MANIFEST_CANONICAL_SHA256:
        raise Phase5V5RemediationAuthorizedProtocolError(
            "Phase 5 v3 authorized identity 发生漂移"
        )
    if candidate.file_sha256(path) != V3_MANIFEST_FILE_SHA256:
        raise Phase5V5RemediationAuthorizedProtocolError(
            "Phase 5 v3 authorized manifest 文件发生漂移"
        )
    return value


def _evaluator_identity() -> dict[str, Any]:
    return {
        "name": "external-evaluator-v4",
        "path": EVALUATOR_PATH,
        "file_sha256": EVALUATOR_FILE_SHA256,
        "version": EVALUATOR_VERSION,
        "rules_sha256": EVALUATOR_RULES_SHA256,
        "oracle_execution_authority": "system_owned_post_build_fence_isolated_v1",
    }


def _v3_historical_success_evidence() -> dict[str, Any]:
    return {
        "evidence_directory": V3_EVIDENCE_DIRECTORY,
        "manifest_canonical_sha256": V3_MANIFEST_CANONICAL_SHA256,
        "report_path": V3_REPORT_PATH,
        "report_file_sha256": V3_REPORT_FILE_SHA256,
        "decision_path": V3_DECISION_PATH,
        "decision_file_sha256": V3_DECISION_FILE_SHA256,
        "task_results": {
            task_id: {
                "path": f"tasks/{task_id}/result.json",
                "file_sha256": V3_SUCCESS_RESULT_SHA256[task_id],
            }
            for task_id in V3_SUCCESS_RESULT_SHA256
        },
        "embedded_outcome_identity_normalization": "phase5_v2_labels_to_phase5_v3_labels_only",
        "use": "cross_run_engineering_adjudication_only",
        "mutable": False,
    }


def _v4_historical_success_evidence() -> dict[str, Any]:
    return {
        "evidence_directory": PARENT_EVIDENCE_DIRECTORY,
        "manifest_canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "report_path": PARENT_REPORT_PATH,
        "report_file_sha256": PARENT_REPORT_FILE_SHA256,
        "batch_marker_path": PARENT_BATCH_MARKER_PATH,
        "batch_marker_file_sha256": PARENT_BATCH_MARKER_FILE_SHA256,
        "task_results": {
            task_id: {
                "path": f"tasks/{task_id}/result.json",
                "file_sha256": PARENT_SUCCESS_RESULT_SHA256[task_id],
            }
            for task_id in PARENT_SUCCESS_RESULT_SHA256
        },
        "use": "cross_run_engineering_adjudication_only",
        "mutable": False,
    }


def _historical_success_evidence() -> dict[str, Any]:
    return {
        "v3": _v3_historical_success_evidence(),
        "v4": _v4_historical_success_evidence(),
    }


def _frozen_components(repo_root: Path) -> dict[str, str]:
    paths = (
        v3.MANIFEST_RELATIVE_PATH,
        v3.PROTOCOL_PATH,
        v3.RUNNER_PATH,
        parent.MANIFEST_RELATIVE_PATH,
        parent.PROTOCOL_PATH,
        parent.RUNNER_PATH,
        BASE_RUNTIME_PATH,
        RUNTIME_PATH,
        NODE_PATH,
        EVALUATOR_PATH,
        PREREGISTRATION_PATH,
        PROTOCOL_PATH,
        RUNNER_PATH,
    )
    return {path: candidate.file_sha256(repo_root / path) for path in paths}


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    _parent_manifest(repo_root)
    source = _v3_manifest(repo_root)
    if candidate.file_sha256(repo_root / EVALUATOR_PATH) != EVALUATOR_FILE_SHA256:
        raise Phase5V5RemediationAuthorizedProtocolError(
            "external evaluator v4 文件发生漂移"
        )

    source_tasks = {task["task_id"]: task for task in source["tasks"]}
    if tuple(source["schedule"]["order"]) != FULL_TASK_ORDER or set(
        source_tasks
    ) != set(FULL_TASK_ORDER):
        raise Phase5V5RemediationAuthorizedProtocolError(
            "Phase 5 v3 六任务集合或顺序发生漂移"
        )

    value = copy.deepcopy(source)
    value.update(
        {
            "$schema": "../schemas/forge-agent-workflow-stage-b-phase5-v5-remediation-authorized.schema.json",
            "schema_version": SCHEMA_VERSION,
            "document_type": DOCUMENT_TYPE,
            "issue_url": ISSUE_URL,
            "status": "authorized_not_executed",
            "baseline_commit": AUTHORIZATION_BASELINE_COMMIT,
            "purpose": "engineering_remediation_and_cross_run_stage_c_adjudication_only",
        }
    )
    value["tasks"] = [
        copy.deepcopy(source_tasks[task_id]) for task_id in REMEDIATION_TASK_ORDER
    ]
    value["tasks"][0]["execution_guidance"] = copy.deepcopy(
        UWEBSOCKETS_EXECUTION_GUIDANCE
    )
    value["schedule"]["order"] = list(REMEDIATION_TASK_ORDER)
    value["budget_candidate"]["batch_max_recorded_tokens"] = 300000
    value["authorization"]["model_tokens_authorized"] = 305000
    value["runtime_candidate"].update(
        {
            "protocol_path": PROTOCOL_PATH,
            "runner_path": RUNNER_PATH,
            "external_evaluator": "external-evaluator-v4",
            "evaluator_identity": _evaluator_identity(),
            "parent_lifecycle_runner_reused_without_modification": True,
            "task_specific_execution_guidance": "uwebsockets-make-examples-v1",
        }
    )
    value["evidence_candidate"].update(
        {
            "directory": EVIDENCE_DIRECTORY,
            "batch_report": "reports/stage-b-phase5-v5-remediation.json",
            "historical_evidence_reused": False,
            "writes_authorized": True,
        }
    )
    value["reporting"].update(
        {
            "stage_c_authorized": False,
            "unbiased_success_rate_claim_allowed": False,
            "cross_run_adjudication_required": True,
        }
    )
    value["authorized_execution"] = {
        "authorization_baseline_commit": AUTHORIZATION_BASELINE_COMMIT,
        "release_branch": "main",
        "release_revision_policy": "descendant_of_authorization_baseline_and_record_each_attempt",
        "parent_manifest_path": parent.MANIFEST_RELATIVE_PATH,
        "parent_manifest_canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "parent_manifest_file_sha256": PARENT_MANIFEST_FILE_SHA256,
        "qualification_result_sha256": candidate.QUALIFICATION_RESULT_SHA256,
        "network_access_medium_env": "FORGE_NETWORK_ACCESS_MEDIUM",
        "network_access_medium": "ethernet",
        "reachability": copy.deepcopy(source["authorized_execution"]["reachability"]),
        "attempt_id_template": "phase5-v5-remediation-{task_id}-attempt-1",
        "thread_id_prefix": "phase5-v5-remediation",
        "evaluation_id_template": "phase5-v5-remediation-{task_id}-evaluation-v4",
        "task_marker_path": "tasks/{task_id}/attempt.json",
        "task_result_path": "tasks/{task_id}/result.json",
        "batch_marker": "markers/batch.json",
        "batch_report": "reports/stage-b-phase5-v5-remediation.json",
        "remediation_completion_package": "reports/remediation-completion.json",
        "stage_c_decision_package": "reports/remediation-completion.json",
        "cross_run_adjudication_report": "reports/stage-b-phase5-v3-v4-v5-cross-run-adjudication.json",
        "final_stage_c_decision_package": "reports/stage-c-decision.json",
        "resume_policy": "completed_contiguous_prefix_only",
        "commands": [
            "validate",
            "preflight",
            "reachability",
            "batch",
            "report",
            "adjudicate",
            "decision",
        ],
        "evaluator": _evaluator_identity(),
        "historical_success_evidence": _historical_success_evidence(),
        "cross_run_task_order": list(FULL_TASK_ORDER),
        "independence": {
            "v3_reachability_reused": False,
            "v4_reachability_reused": False,
            "v3_task_attempts_reused": False,
            "v4_task_attempts_reused_for_execution": False,
            "v3_failed_outcomes_imported": False,
            "v4_failed_outcomes_imported": False,
            "v3_evidence_mutated": False,
            "v4_evidence_mutated": False,
            "new_compile_session_per_task": True,
            "v3_success_outcomes_used_for_cross_run_adjudication": True,
            "v4_success_outcomes_used_for_cross_run_adjudication": True,
            "task_specific_guidance_pre_registered": True,
            "historical_results_used_for_statistical_estimation": False,
        },
    }
    value["frozen_authorized_components"] = _frozen_components(repo_root)
    return value


def validate_allowed_delta(
    value: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    source = _parent_manifest(repo_root)
    expected = generate_manifest(repo_root)
    if value != expected:
        raise Phase5V5RemediationAuthorizedProtocolError(
            "Phase 5 v5 包含未预注册的父 identity 差异"
        )
    inherited_keys = (
        "provider_candidate",
        "environment_candidate",
        "qualification",
        "operation_policy_ref",
    )
    if any(value[key] != source[key] for key in inherited_keys):
        raise Phase5V5RemediationAuthorizedProtocolError(
            "Phase 5 v5 冻结 Provider、环境或资格合同发生漂移"
        )
    if value["budget_candidate"]["per_task"] != source["budget_candidate"]["per_task"]:
        raise Phase5V5RemediationAuthorizedProtocolError(
            "Phase 5 v5 单任务预算发生漂移"
        )
    return {
        "status": "passed",
        "parent_manifest_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "evaluator_version": EVALUATOR_VERSION,
        "evaluator_rules_sha256": EVALUATOR_RULES_SHA256,
        "task_count": len(value["tasks"]),
        "task_order": value["schedule"]["order"],
        "historical_evidence_reused_for_execution": False,
        "historical_success_outcomes_used_for_cross_run_adjudication": True,
        "unbiased_success_rate_claim_allowed": False,
        "stage_c_authorized_before_execution": False,
    }


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-agent-workflow-stage-b-phase5-v5-remediation-authorized.schema.json",
        "title": "Forge Agent Workflow Stage B Phase 5 v5 remediation authorized evaluation",
        "const": manifest,
    }


def validate_manifest(
    value: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    expected = generate_manifest(repo_root)
    if value != expected:
        raise Phase5V5RemediationAuthorizedProtocolError(
            "Phase 5 v5 remediation authorized manifest 与确定性生成结果不一致"
        )
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
        raise Phase5V5RemediationAuthorizedProtocolError(
            "Phase 5 v5 真实执行授权未闭合"
        )
    expected_tokens = (
        value["budget_candidate"]["batch_max_recorded_tokens"]
        + value["authorized_execution"]["reachability"]["maximum_recorded_tokens"]
    )
    if authorization["model_tokens_authorized"] != expected_tokens:
        raise Phase5V5RemediationAuthorizedProtocolError(
            "Phase 5 v5 授权 token ceiling 发生漂移"
        )
    independence = value["authorized_execution"]["independence"]
    false_fields = (
        "v3_reachability_reused",
        "v4_reachability_reused",
        "v3_task_attempts_reused",
        "v4_task_attempts_reused_for_execution",
        "v3_failed_outcomes_imported",
        "v4_failed_outcomes_imported",
        "v3_evidence_mutated",
        "v4_evidence_mutated",
        "historical_results_used_for_statistical_estimation",
    )
    true_fields = (
        "new_compile_session_per_task",
        "v3_success_outcomes_used_for_cross_run_adjudication",
        "v4_success_outcomes_used_for_cross_run_adjudication",
        "task_specific_guidance_pre_registered",
    )
    if any(independence[key] is not False for key in false_fields) or any(
        independence[key] is not True for key in true_fields
    ):
        raise Phase5V5RemediationAuthorizedProtocolError("Phase 5 v5 独立性声明无效")
    schema = generate_schema(expected)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(value, schema)
    return value


def load_manifest(
    path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    return validate_manifest(_load_json(path), repo_root)


def verify_frozen_components(
    manifest: dict[str, Any], repo_root: Path = REPO_ROOT
) -> None:
    validate_manifest(manifest, repo_root)
    if manifest["frozen_authorized_components"] != _frozen_components(repo_root):
        raise Phase5V5RemediationAuthorizedProtocolError(
            "Phase 5 v5 authorized 组件发生漂移"
        )


def write_artifacts(repo_root: Path = REPO_ROOT) -> None:
    manifest = generate_manifest(repo_root)
    schema = generate_schema(manifest)
    for relative_path, value in (
        (MANIFEST_RELATIVE_PATH, manifest),
        (SCHEMA_RELATIVE_PATH, schema),
    ):
        path = repo_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate", "delta"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    if args.command == "generate":
        write_artifacts()
        manifest = load_manifest(args.manifest)
        result: Any = {
            "status": "generated",
            "manifest": MANIFEST_RELATIVE_PATH,
            "schema": SCHEMA_RELATIVE_PATH,
        }
    else:
        manifest = load_manifest(args.manifest)
        result = (
            validate_allowed_delta(manifest)
            if args.command == "delta"
            else {"status": "valid"}
        )
    result["manifest_sha256"] = candidate.canonical_sha256(manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
