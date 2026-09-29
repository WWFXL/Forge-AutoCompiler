#!/usr/bin/env python3
"""生成并校验契约驱动修复 mechanism v1 未授权候选 identity。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
from collections import Counter
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_VERSION = "forge-contract-driven-repair-mechanism-v1-candidate-1.0.0"
DOCUMENT_TYPE = "forge_contract_driven_repair_mechanism_v1_candidate"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/353"
DEVELOPMENT_BASELINE_REVISION = "47b34eb1eb13eb845b3af0f466e4457f74f01e2a"
SELECTION_SEED = "forge-contract-driven-repair-mechanism-v1-2026-09-29"
ARMS = ("c0", "t1", "t2")
STRATA = ("delivery_target", "provenance")
EXCLUDED_STAGE_C_V8_TASKS = frozenset({"theora", "json-c", "libjpeg-turbo", "oatpp"})
EXPECTED_TASK_IDS = (
    "leveldb",
    "libsoundio",
    "8cc",
    "lz4",
    "rnnoise-0.1.1",
    "libsndfile",
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = (
    "scripts/forge_contract_driven_repair_mechanism_v1_candidate_protocol.py"
)
RUNNER_PATH = "scripts/forge_contract_driven_repair_mechanism_v1_candidate_runner.py"
MANIFEST_PATH = (
    "benchmarks/manifests/cpp-contract-driven-repair-mechanism-v1-candidate.json"
)
SCHEMA_PATH = (
    "benchmarks/schemas/forge-contract-driven-repair-mechanism-v1-candidate.schema.json"
)
PREREGISTRATION_PATH = (
    "benchmarks/preregistrations/cpp-contract-driven-repair-mechanism-v1-candidate.md"
)
SOURCE_POOL_PATH = "benchmarks/fixtures/stage-c-source-pool.json"
TASK_QUALIFICATION_PLAN_PATH = (
    "benchmarks/manifests/cpp-stage-c-task-qualification.json"
)
TASK_QUALIFICATION_RESULT_PATH = (
    "benchmarks/fixtures/stage-c-task-qualification-result.json"
)

DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_PATH

FROZEN_COMPONENT_PATHS = (
    SOURCE_POOL_PATH,
    TASK_QUALIFICATION_PLAN_PATH,
    TASK_QUALIFICATION_RESULT_PATH,
    "benchmarks/schemas/forge-stage-c-task-qualification.schema.json",
    "scripts/forge_runtime_v3_three_arm_qualification.py",
    "backend/tests/test_forge_runtime_v3_three_arm_qualification_docker.py",
    "benchmarks/preregistrations/cpp-runtime-v3-three-arm-zero-provider-qualification.md",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v3.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_schemas.py",
    "backend/packages/harness/deerflow/compile/candidate_verifier.py",
    "scripts/forge_opaque_build_provenance_gate.py",
    "backend/packages/harness/deerflow/compile/external_evaluator_v3.py",
    "backend/packages/harness/deerflow/compile/operations.py",
    "backend/packages/harness/deerflow/tools/bound_compile_tools.py",
    "scripts/forge_contract_repair_design_sensitivity.py",
    "docs/research/2026-09-29-contract-driven-repair-design-audit.md",
    "docs/research/2026-09-29-contract-driven-repair-preregistration-decision.md",
    PREREGISTRATION_PATH,
    PROTOCOL_PATH,
    RUNNER_PATH,
)


class CandidateProtocolError(RuntimeError):
    """候选 identity、输入权威或确定性计划发生漂移。"""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise CandidateProtocolError(f"候选权威文件不存在或为符号链接: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateProtocolError(f"无法读取候选 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise CandidateProtocolError(f"候选 JSON 顶层必须为对象: {path}")
    return value


def _digest_parts(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _project_selection_key(task: dict[str, Any]) -> str:
    return _digest_parts(SELECTION_SEED, task["repository_url"], task["commit_sha"])


def _select_source_tasks(source_pool: dict[str, Any]) -> list[dict[str, Any]]:
    desired = {
        ("cmake", "small"),
        ("cmake", "medium"),
        ("make", "small"),
        ("make", "medium"),
        ("autotools", "small"),
        ("autotools", "medium"),
    }
    selected: list[dict[str, Any]] = []
    observed: set[tuple[str, str]] = set()
    for task in source_pool.get("tasks", []):
        key = (task.get("build_system_stratum"), task.get("size_stratum"))
        if (
            task.get("task_id") in EXCLUDED_STAGE_C_V8_TASKS
            or key not in desired
            or key in observed
        ):
            continue
        selected.append(copy.deepcopy(task))
        observed.add(key)
    ids = tuple(task["task_id"] for task in selected)
    if observed != desired or ids != EXPECTED_TASK_IDS:
        raise CandidateProtocolError(
            f"结果盲 source-pool 选择规则发生漂移: observed={ids!r}"
        )
    return selected


def _qualified_task(
    result: dict[str, Any], task_id: str, source_task: dict[str, Any]
) -> dict[str, Any]:
    matches = [
        task for task in result.get("tasks", []) if task.get("task_id") == task_id
    ]
    if len(matches) != 1:
        raise CandidateProtocolError(f"task qualification 缺失或重复: {task_id}")
    task = matches[0]
    replicates = task.get("replicates", [])
    if (
        task.get("passed") is not True
        or task.get("bitwise_reproducible") is not True
        or len(replicates) != 2
    ):
        raise CandidateProtocolError(f"task qualification 未通过双重复门禁: {task_id}")
    expected_source = {
        "commit_sha": source_task["commit_sha"],
        "license_sha256": source_task["license_sha256"],
        "source_snapshot_sha256": source_task["source_snapshot_sha256"],
        "submodule_commits": source_task["submodule_commits"],
    }
    if any(
        replicate.get("source_identity") != expected_source for replicate in replicates
    ):
        raise CandidateProtocolError(
            f"task qualification source identity 漂移: {task_id}"
        )
    artifact_sets = [replicate.get("artifacts") for replicate in replicates]
    if artifact_sets[0] != artifact_sets[1] or any(
        replicate.get("oracle_passed") is not True for replicate in replicates
    ):
        raise CandidateProtocolError(
            f"task qualification artifact/oracle 漂移: {task_id}"
        )
    return {
        "passed": True,
        "bitwise_reproducible": True,
        "replicate_count": 2,
        "task_result_canonical_sha256": canonical_sha256(task),
        "artifact_set_canonical_sha256": canonical_sha256(artifact_sets[0]),
    }


def _task_contract(plan: dict[str, Any], task_id: str) -> dict[str, Any]:
    matches = [task for task in plan.get("tasks", []) if task.get("task_id") == task_id]
    if len(matches) != 1:
        raise CandidateProtocolError(f"task contract 缺失或重复: {task_id}")
    task = matches[0]
    target = task.get("target")
    oracle = task.get("oracle")
    if not isinstance(target, dict) or not isinstance(oracle, dict):
        raise CandidateProtocolError(f"task contract target/oracle 无效: {task_id}")
    return {
        "target": copy.deepcopy(target),
        "functional_oracle": {
            "authority_path": TASK_QUALIFICATION_PLAN_PATH,
            "definition_canonical_sha256": canonical_sha256(oracle),
            "evaluator_only": True,
            "exposed_to_model": False,
        },
    }


def _tasks(repo_root: Path) -> list[dict[str, Any]]:
    source_pool = _load_json(repo_root / SOURCE_POOL_PATH)
    plan = _load_json(repo_root / TASK_QUALIFICATION_PLAN_PATH)
    result = _load_json(repo_root / TASK_QUALIFICATION_RESULT_PATH)
    if (
        plan.get("source_pool_path") != SOURCE_POOL_PATH
        or plan.get("result_path") != TASK_QUALIFICATION_RESULT_PATH
        or result.get("source_pool_canonical_sha256") != canonical_sha256(source_pool)
        or result.get("plan_canonical_sha256") != canonical_sha256(plan)
        or result.get("task_count") != len(source_pool.get("tasks", []))
        or result.get("status") != "passed"
        or result.get("provider_request_count") != 0
        or result.get("model_created") is not False
        or result.get("formal_stage_c_attempt_created") is not False
        or result.get("formal_stage_c_evidence_written") is not False
    ):
        raise CandidateProtocolError(
            "Stage C task qualification 零 Provider 边界发生漂移"
        )
    selected = _select_source_tasks(source_pool)
    tasks: list[dict[str, Any]] = []
    for source_task in selected:
        task_id = source_task["task_id"]
        tasks.append(
            {
                "task_id": task_id,
                "source": source_task,
                "contract": _task_contract(plan, task_id),
                "qualification": _qualified_task(result, task_id, source_task),
                "historical_model_outcomes_imported": False,
            }
        )
    return tasks


def _frozen_components(repo_root: Path) -> dict[str, str]:
    return {
        relative_path: file_sha256(repo_root / relative_path)
        for relative_path in FROZEN_COMPONENT_PATHS
    }


def _opaque_identity(kind: str, checkpoint_id: str, arm: str) -> str:
    digest = _digest_parts(SELECTION_SEED, kind, checkpoint_id, arm)
    return f"{kind}-{digest[:24]}"


def _schedule(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    project_order = sorted(
        tasks, key=lambda task: _project_selection_key(task["source"])
    )
    permutations = list(itertools.permutations(ARMS))
    arm_orders: dict[str, dict[str, tuple[str, ...]]] = {}
    for stratum in STRATA:
        ranked = sorted(
            permutations,
            key=lambda order: _digest_parts(SELECTION_SEED, stratum, *order),
        )
        arm_orders[stratum] = {
            task["task_id"]: ranked[index] for index, task in enumerate(project_order)
        }

    projects: list[dict[str, Any]] = []
    checkpoints: list[dict[str, Any]] = []
    arm_sequence = 0
    for project_index, task in enumerate(project_order):
        first_stratum = STRATA[project_index % 2]
        stratum_order = (
            first_stratum,
            next(item for item in STRATA if item != first_stratum),
        )
        projects.append(
            {
                "project_sequence": project_index + 1,
                "task_id": task["task_id"],
                "selection_key_sha256": _project_selection_key(task["source"]),
                "stratum_order": list(stratum_order),
            }
        )
        for stratum in stratum_order:
            checkpoint_id = f"{task['task_id']}:{stratum}"
            arms: list[dict[str, Any]] = []
            for position, arm in enumerate(
                arm_orders[stratum][task["task_id"]], start=1
            ):
                arm_sequence += 1
                clone_id = _opaque_identity("clone", checkpoint_id, arm)
                arms.append(
                    {
                        "sequence": arm_sequence,
                        "position_within_checkpoint": position,
                        "condition": arm,
                        "feedback_projection": f"forge-contract-feedback-projection-1.0.0#{arm}",
                        "opaque_clone_id": clone_id,
                        "opaque_evaluation_id": _opaque_identity(
                            "evaluation", checkpoint_id, arm
                        ),
                    }
                )
            checkpoints.append(
                {
                    "checkpoint_sequence": len(checkpoints) + 1,
                    "checkpoint_id": checkpoint_id,
                    "task_id": task["task_id"],
                    "stratum": stratum,
                    "arm_order": list(arm_orders[stratum][task["task_id"]]),
                    "arms": arms,
                }
            )
    return {
        "seed": SELECTION_SEED,
        "project_order_key": "sha256(seed || NUL || repository_url || NUL || commit_sha)",
        "arm_order_method": "stratum-specific SHA-256 ranking of all six C0/T1/T2 permutations",
        "execution": "strictly_serial",
        "outcome_adaptive_reordering": False,
        "replacement": False,
        "backfill": False,
        "failed_arm_rerun": False,
        "post_outcome_extension": False,
        "projects": projects,
        "checkpoints": checkpoints,
    }


def _validate_schedule(schedule: dict[str, Any]) -> None:
    projects = schedule.get("projects", [])
    checkpoints = schedule.get("checkpoints", [])
    if len(projects) != 6 or len(checkpoints) != 12:
        raise CandidateProtocolError("schedule 必须包含 6 projects / 12 checkpoints")
    first_counts = Counter(project["stratum_order"][0] for project in projects)
    if first_counts != Counter({"delivery_target": 3, "provenance": 3}):
        raise CandidateProtocolError("首个 stratum 分配不平衡")
    expected_permutations = Counter(itertools.permutations(ARMS))
    all_clone_ids: list[str] = []
    all_evaluation_ids: list[str] = []
    sequences: list[int] = []
    for stratum in STRATA:
        observed = Counter(
            tuple(checkpoint["arm_order"])
            for checkpoint in checkpoints
            if checkpoint["stratum"] == stratum
        )
        if observed != expected_permutations:
            raise CandidateProtocolError(f"{stratum} 未恰好使用六种 arm 排列各一次")
    for checkpoint in checkpoints:
        arms = checkpoint.get("arms", [])
        if len(arms) != 3 or {arm["condition"] for arm in arms} != set(ARMS):
            raise CandidateProtocolError("checkpoint 必须包含唯一 C0/T1/T2")
        if [arm["condition"] for arm in arms] != checkpoint["arm_order"]:
            raise CandidateProtocolError("checkpoint arm 顺序与执行项不一致")
        all_clone_ids.extend(arm["opaque_clone_id"] for arm in arms)
        all_evaluation_ids.extend(arm["opaque_evaluation_id"] for arm in arms)
        sequences.extend(arm["sequence"] for arm in arms)
    if sequences != list(range(1, 37)):
        raise CandidateProtocolError("36-arm 全局顺序不连续")
    if len(set(all_clone_ids)) != 36 or len(set(all_evaluation_ids)) != 36:
        raise CandidateProtocolError("opaque clone/evaluation identity 不唯一")


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    tasks = _tasks(repo_root)
    manifest: dict[str, Any] = {
        "$schema": "../schemas/forge-contract-driven-repair-mechanism-v1-candidate.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "issue_url": ISSUE_URL,
        "status": "candidate_not_authorized",
        "development_revision": {
            "baseline_commit": DEVELOPMENT_BASELINE_REVISION,
            "release_revision": None,
            "release_revision_frozen": False,
            "merge_required_before_authorization": True,
        },
        "authorization": {
            "candidate_identity_only": True,
            "credential_read_authorized": False,
            "provider_calls_authorized": False,
            "model_creation_authorized": False,
            "reachability_request_authorized": False,
            "docker_execution_authorized": False,
            "formal_attempts_authorized": False,
            "formal_evidence_write_authorized": False,
            "model_tokens_authorized": False,
            "execution_started": False,
        },
        "provider_candidate": {
            "provider": "deepseek",
            "profile": "deepseek-flash",
            "actual_model": "deepseek-flash",
            "endpoint": "https://api.deepseek.com",
            "credential_env_name": "DEEPSEEK_API_KEY",
            "streaming": False,
            "fallback_enabled": False,
            "parallel_tool_calls": False,
            "request_timeout_seconds": 300,
            "model_max_retries": 0,
        },
        "budget_candidate": {
            "per_arm": {
                "max_model_request_attempts": 8,
                "max_turns": 8,
                "max_graph_steps": 24,
                "max_recorded_tokens": None,
                "max_tool_calls": 24,
                "max_commands": 16,
                "continuation_timeout_seconds": 600,
                "command_timeout_seconds": 300,
                "evaluator_timeout_seconds": 900,
                "clean_replay_timeout_seconds": 900,
                "cleanup_reserve_seconds": 120,
            },
            "formal_arm_count": 36,
            "formal_arms_total_max_model_request_attempts": 288,
            "total_provider_request_attempts_including_availability_max": 290,
            "total_max_recorded_tokens": None,
            "token_accounting": {
                "mode": "meter_each_request_without_ceiling",
                "record_input_tokens": True,
                "record_output_tokens": True,
                "record_total_tokens": True,
                "token_total_is_termination_condition": False,
            },
            "monetary_stop_rule": None,
            "runtime_budget_mapping": {
                "max_model_request_attempts": "AgentWorkflowBudget.max_model_requests",
                "max_graph_steps": "AgentWorkflowBudget.max_agent_steps",
                "continuation_timeout_seconds": "AgentWorkflowBudget.node_timeout_seconds",
                "clean_replay_timeout_seconds": "AgentWorkflowBudget.replay_timeout_seconds",
            },
        },
        "transport_and_stopping": {
            "availability_qualification": {
                "before_formal_marker": True,
                "logical_request_count": 1,
                "max_request_attempts_including_transport_retry": 2,
                "request": "Reply exactly with FORGE_READY.",
                "expected_response": "FORGE_READY",
                "experiment_content_included": False,
                "transport_retry_policy_applies": True,
                "failure_creates_batch": False,
                "request_attempts_count_toward_formal_arm_budget": False,
            },
            "transport_retry_max_per_logical_request": 1,
            "transport_retry_conditions": [
                "zero_response",
                "zero_recorded_tokens",
                "zero_tool_side_effects",
            ],
            "transport_retry_counts_toward_request_attempt_limit": True,
            "model_behavior_retry_allowed": False,
            "stop_after_endpoint_censored_arm_count": 2,
            "cleanup_current_checkpoint_before_stop": True,
            "identity_or_checkpoint_failure_stops_identity": True,
            "ledger_or_budget_failure_stops_identity": True,
            "evaluator_or_cleanup_or_orphan_failure_stops_identity": True,
        },
        "feedback_contract": {
            "schema_version": "forge-contract-feedback-projection-1.0.0",
            "conditions": {
                "c0": "generic verification_failed payload only",
                "t1": "C0 plus classification and code/paths/expected/actual finding",
                "t2": "T1 plus bounded abstract repair_goal without commands, patches, or answers",
            },
            "allowed_cross_arm_delta": "feedback projection only",
            "forbidden_content": [
                "argv",
                "shell",
                "complete_command",
                "patch",
                "answer",
                "credential",
                "external_evaluator_information",
            ],
        },
        "checkpoint_contract": {
            "capture_timing": "after authoritative rejection and before any continuation model request",
            "independent_parent_per_task_and_stratum": True,
            "state_matched_fields": [
                "source",
                "commit",
                "rootfs",
                "workspace",
                "artifacts",
                "parent_command_history",
                "candidate_request",
                "authoritative_rejection",
                "message_prefix",
                "remaining_budget",
                "tool_policy",
                "authority_hashes",
            ],
            "strata": {
                "delivery_target": {
                    "authority": "production CandidateVerifier",
                    "unique_finding_code": "target_mapping_invalid",
                    "preconditions": [
                        "target_artifacts_exist",
                        "functional_oracle_passed",
                        "single_expected_finding",
                    ],
                },
                "provenance": {
                    "authority": "production CandidateVerifier followed by P2 reference criterion",
                    "unique_finding_code": "build_system_unproven",
                    "required_actual": "opaque_wrapper",
                    "preconditions": [
                        "target_artifacts_exist",
                        "functional_oracle_passed",
                        "single_expected_finding",
                    ],
                    "repair_must_use_real_compiler_tool_surface": True,
                    "direct_command_record_write_forbidden": True,
                },
            },
        },
        "strict_endpoint": {
            "name": "strict_post_checkpoint_conversion",
            "all_required": [
                "candidate_accepted",
                "functional_oracle_passed",
                "provenance_passed",
                "external_evaluator_v3_passed",
                "clean_replay_passed",
                "cleanup_closed",
                "zero_managed_orphans",
            ],
            "model_behavior_failures_are_zero": [
                "request_or_step_or_time_budget_exhausted",
                "no_submit",
                "candidate_rejected_again",
            ],
            "endpoint_censoring_is_not_zero": True,
        },
        "analysis": {
            "population": "six frozen small/medium C/C++ projects only",
            "project_weighting": "equal",
            "primary": {
                "comparison": "c0_vs_t1",
                "estimand": "mean of six project scores over twelve matched checkpoints",
                "minimum_meaningful_effect": "1/3",
                "minimum_net_conversions": 4,
                "test": "two-sided exact project-level sign-flip",
                "alpha": 0.05,
                "requires_all_relevant_arms_eligible": True,
            },
            "secondary": {
                "comparison": "t1_vs_t2",
                "minimum_meaningful_effect": "1/6",
                "minimum_net_conversions": 2,
                "test": "two-sided exact project-level sign-flip",
                "alpha": 0.05,
                "gate": "primary statistical and practical criteria both pass",
                "requires_all_relevant_arms_eligible": True,
            },
            "supportive": {
                "comparison": "c0_vs_t2",
                "confirmatory_p_value": False,
                "report": "effect size and stratum descriptions only",
            },
            "incomplete_data": {
                "missing_arms_imputed_as_zero": False,
                "observed_complete_estimate_reported": True,
                "best_and_worst_case_identification_interval_reported": True,
            },
            "power_claim": "fixed-sample mechanism study; not powered confirmation",
        },
        "tasks": tasks,
        "schedule": _schedule(tasks),
        "runtime_candidate": {
            "orchestration": "agent_workflow_runtime_v3",
            "external_evaluator": "external_evaluator_v3",
            "clean_replay_required": True,
            "cleanup_required": True,
            "tool_policy": {
                "tools": ["run_container_bash", "submit_candidate_v1"],
                "parallel_tool_calls": False,
                "action_policy": "runtime-v3-compiler-tool-surface",
            },
            "external_evaluator_input_contract": {
                "allowed_identity_fields": [
                    "opaque_evaluation_id",
                    "checkpoint_id",
                    "task_id",
                ],
                "forbidden_fields": [
                    "condition",
                    "arm",
                    "feedback_projection",
                    "opaque_clone_id",
                ],
            },
            "commands_allowed_by_candidate_runner": [
                "validate",
                "plan",
                "show-checkpoint",
            ],
            "commands_fail_closed": ["reachability", "run", "batch"],
        },
        "runtime_v3_qualification": {
            "status": "passed",
            "fault_strata": list(STRATA),
            "arms": list(ARMS),
            "static_tests_passed": 14,
            "adjacent_regression_tests_passed": 77,
            "docker_tests_passed": 2,
            "provider_requests": 0,
            "formal_attempts": 0,
            "formal_evidence_writes": 0,
            "interpretation": "infrastructure qualification only; no treatment effect",
        },
        "candidate_evidence": {
            "formal_directory": None,
            "writes_authorized": False,
            "historical_evidence_reused": False,
        },
        "frozen_components": _frozen_components(repo_root),
        "interpretation_boundary": [
            "candidate identity is not execution authorization",
            "qualification evidence is not a treatment effect",
            "results cannot establish a general provider or model ranking",
            "inference is limited to the six frozen projects and conditions",
        ],
    }
    _validate_schedule(manifest["schedule"])
    return manifest


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-contract-driven-repair-mechanism-v1-candidate.schema.json",
        "title": "Forge contract-driven repair mechanism v1 candidate",
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
        raise CandidateProtocolError("candidate manifest 与确定性生成结果不一致")
    authorization = value["authorization"]
    if authorization.get("candidate_identity_only") is not True or any(
        authorization.get(field) is not False
        for field in (
            "credential_read_authorized",
            "provider_calls_authorized",
            "model_creation_authorized",
            "reachability_request_authorized",
            "docker_execution_authorized",
            "formal_attempts_authorized",
            "formal_evidence_write_authorized",
            "model_tokens_authorized",
            "execution_started",
        )
    ):
        raise CandidateProtocolError("candidate 未授权边界未闭合")
    budget = value["budget_candidate"]
    if (
        budget["per_arm"]["max_recorded_tokens"] is not None
        or budget["total_max_recorded_tokens"] is not None
        or budget["token_accounting"]["token_total_is_termination_condition"]
        is not False
    ):
        raise CandidateProtocolError("无 token ceiling 合同发生漂移")
    if value["development_revision"]["release_revision"] is not None:
        raise CandidateProtocolError("candidate 不得自行冻结 release revision")
    _validate_schedule(value["schedule"])
    schema = generate_schema(value)
    jsonschema.Draft202012Validator.check_schema(schema)
    if check_schema_file:
        stored_schema = _load_json(repo_root / SCHEMA_PATH)
        if stored_schema != schema:
            raise CandidateProtocolError("candidate const Schema 发生漂移")
        jsonschema.validate(value, stored_schema)
    return value


def load_manifest(
    path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    return validate_manifest(_load_json(path), repo_root)


def plan_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    validated = validate_manifest(manifest)
    return {
        "status": "candidate_valid_not_authorized",
        "manifest_sha256": canonical_sha256(validated),
        "project_count": len(validated["schedule"]["projects"]),
        "checkpoint_count": len(validated["schedule"]["checkpoints"]),
        "arm_count": sum(
            len(checkpoint["arms"])
            for checkpoint in validated["schedule"]["checkpoints"]
        ),
        "project_order": [
            project["task_id"] for project in validated["schedule"]["projects"]
        ],
        "release_revision": None,
        "provider_calls": 0,
        "credential_reads": 0,
        "docker_executions": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
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
    parser.add_argument("command", choices=("generate", "validate", "plan"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    if args.command == "generate":
        write_artifacts()
    manifest = load_manifest(args.manifest)
    result = (
        plan_summary(manifest)
        if args.command == "plan"
        else {
            "status": "generated" if args.command == "generate" else "valid",
            "manifest_sha256": canonical_sha256(manifest),
            "provider_calls": 0,
            "credential_reads": 0,
            "formal_attempts": 0,
            "formal_evidence_writes": 0,
        }
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
