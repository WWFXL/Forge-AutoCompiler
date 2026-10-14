#!/usr/bin/env python3
"""Issue #461 进展预算感知 Jev 校准实验的零 Provider candidate。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import stat
from collections import Counter
from collections.abc import Iterable
from importlib.metadata import version
from pathlib import Path
from typing import Any

import httpx2
import jsonschema
from packaging.version import Version
from sklearn.linear_model import LogisticRegression
from typesafe_sdk import Choice, RetryPolicy, TypeSafeClient

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
IDENTITY = "cpp-jev-progress-budget-calibration-candidate-v1"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/461"
SCHEMA_VERSION = "forge-jev-progress-budget-calibration-candidate-1.0.0"

PARENT_IDENTITY = "cpp-progress-budget-jev-identifiability-qualification-v1"
PARENT_REPORT = REPO_ROOT / "benchmarks/reports/cpp-progress-budget-jev-identifiability-qualification-v1.json"
PARENT_REPORT_FILE_SHA256 = "1ec00e9d9940ccabce5740a085da52b2f2dc82973b9c1554f026b3abeb4c1ccc"
PARENT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-progress-budget-jev-identifiability-qualification-v1.json"
PARENT_MANIFEST_FILE_SHA256 = "f8e1750bb63ee81138fbeff112831b64002dee68380d50d47eb22a2ade4fc179"
PARENT_MANIFEST_CANONICAL_SHA256 = "fed83243b439df16e10b9ef1940b0158ba269a4c03799e706dd1e2dcb290bc76"
PARENT_EVIDENCE_ROOT = REPO_ROOT / ".compile-sessions/benchmark-evidence-progress-budget-jev-identifiability-qualification-v1"
PARENT_INVENTORY = PARENT_EVIDENCE_ROOT / "inventory.json"
PARENT_INVENTORY_FILE_SHA256 = "4ec1fd32f372471e8bc768d717bf6661eeba8124ad6c9c62d8a212d4ed88e4c3"
PARENT_INVENTORY_CANONICAL_SHA256 = "2e4209fb52c07af949789ae7880db478f5a6d9326b4496de7fcff45ad64da9e9"
PARENT_COMPLETED = PARENT_EVIDENCE_ROOT / "completed.json"
PARENT_COMPLETED_FILE_SHA256 = "d38350f9480c64b218f835abea8d156c688c1c30410cb344e52d3b4ce50abd08"

SPEC_PATH = REPO_ROOT / "docs/research/2026-10-14-jev-progress-budget-calibration-spec.md"
SPEC_FILE_SHA256 = "f3d2d37fd119d872284d80102531cb98d146e310ec404f9ac37b9c1921c8e2e0"
PLAN_PATH = REPO_ROOT / "docs/research/2026-10-14-jev-progress-budget-calibration-plan.md"
API_AUDIT_PATH = REPO_ROOT / "docs/research/2026-10-09-jev-api-contract-audit.md"
API_AUDIT_FILE_SHA256 = "1f0057f76508df7d91daf7c10ee51c722cecb23197bb570b36397f6afed46680"
PREREGISTRATION = REPO_ROOT / "benchmarks/preregistrations/cpp-jev-progress-budget-calibration-candidate-v1.md"
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-jev-progress-budget-calibration-candidate-v1.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-jev-progress-budget-calibration-candidate-v1.schema.json"

SDK_DISTRIBUTION = "typesafe-sdk"
SDK_VERSION = "0.7.3"
SKLEARN_DISTRIBUTION = "scikit-learn"
MODEL_ID = "jev-1.13.0"
API_BASE_URL = "https://api.typesafe.ai"
API_ENDPOINT = "/v1/systemone"
CREDENTIAL_ENV = "TYPESAFE_API_KEY"
CREDENTIAL_FILE = REPO_ROOT / "jev-apikey.txt"
INPUT_PRICE_USD_PER_MILLION_TOKENS = 0.042

BUILD_SYSTEMS = ("cmake", "make", "autotools")
SPLITS = ("calibration", "evaluation")
ACTION_FAMILIES = ("dependency", "configure", "build", "escalate_agent")
LOCAL_ACTIONS = ACTION_FAMILIES[:3]
BUDGET_PROFILES = ("critical", "local_only", "agent_capable")
PRIMARY_ACTION_ORDER = ACTION_FAMILIES
SENSITIVITY_ACTION_ORDER = tuple(reversed(ACTION_FAMILIES))
QUESTION_IDS = ("next_action_primary", "next_action_order_sensitivity")
PROVIDER_STATE_FIELDS = (
    "build_system",
    "phase_facts",
    "progress_facts",
    "semantic_failure_log",
)

SPLIT_FAMILIES = {
    "calibration": {
        "cmake": "github.com/p-ranav/argparse",
        "make": "github.com/kgabis/parson",
        "autotools": "github.com/troglobit/libuev",
    },
    "evaluation": {
        "cmake": "github.com/neargye/magic_enum",
        "make": "github.com/antirez/sds",
        "autotools": "github.com/ivmai/libatomic_ops",
    },
}

ACTION_DESCRIPTIONS = {
    "dependency": "Execute the already-bound input or dependency recovery action, then continue the strict verification workflow.",
    "configure": "Regenerate the damaged or stale build-system state with the already-bound configure action, then continue strict verification.",
    "build": "Execute the already-bound normal build action without changing dependencies or generated configuration, then continue strict verification.",
    "escalate_agent": "Do not execute a direct local action. Escalate to the full compilation Agent because the observed state does not safely support one local action.",
}
ACTION_INSTRUCTIONS = (
    "Choose the single next action that is best supported by the observed build state and is "
    "most likely to reach the strict build endpoint at the lowest action cost. Use only the "
    "supplied state. Choose escalate_agent when the evidence is insufficient for one direct "
    "local action. Do not generate commands, parameters, or explanations."
)

PROBABILITY_SUM_TOLERANCE = 0.005
CONFIDENCE_FORMULA_TOLERANCE = 0.02
PLATT_EPSILON = 1e-6
CALIBRATION_RANDOM_STATE = 459


class CandidateError(RuntimeError):
    """Candidate 合同、父证据或模拟 SDK 行为发生漂移。"""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise CandidateError(f"JSON 顶层必须为对象: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _assert_file_hash(path: Path, expected: str, label: str) -> None:
    observed = file_sha256(path)
    if observed != expected:
        raise CandidateError(f"{label} 文件 SHA-256 漂移: {observed}")


def _current_parent_inventory() -> dict[str, Any]:
    excluded = {"inventory.json", "completed.json"}
    rows = []
    for path in sorted(item for item in PARENT_EVIDENCE_ROOT.rglob("*") if item.is_file()):
        relative = path.relative_to(PARENT_EVIDENCE_ROOT).as_posix()
        if relative in excluded:
            continue
        rows.append(
            {
                "path": relative,
                "size_bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    return {
        "files": rows,
        "file_count": len(rows),
        "total_bytes": sum(row["size_bytes"] for row in rows),
        "canonical_sha256": canonical_sha256(rows),
    }


def validate_parent_sources() -> tuple[dict[str, Any], dict[str, Any]]:
    _assert_file_hash(PARENT_REPORT, PARENT_REPORT_FILE_SHA256, "父报告")
    _assert_file_hash(PARENT_MANIFEST, PARENT_MANIFEST_FILE_SHA256, "父 manifest")
    _assert_file_hash(SPEC_PATH, SPEC_FILE_SHA256, "spec")
    _assert_file_hash(API_AUDIT_PATH, API_AUDIT_FILE_SHA256, "API 审计")

    report = load_json(PARENT_REPORT)
    manifest = load_json(PARENT_MANIFEST)

    if report.get("identity") != PARENT_IDENTITY or report.get("status") != "completed":
        raise CandidateError("父报告 identity/status 漂移")
    if report.get("analysis", {}).get("decision") != "proceed_to_jev_progress_budget_calibration_design" or report.get("analysis", {}).get("passed") is not True:
        raise CandidateError("父资格决定不允许进入 Jev 校准设计")
    if canonical_sha256(manifest) != PARENT_MANIFEST_CANONICAL_SHA256 or report.get("manifest_canonical_sha256") != PARENT_MANIFEST_CANONICAL_SHA256:
        raise CandidateError("父 manifest canonical SHA-256 漂移")
    if report.get("evidence", {}).get("inventory_canonical_sha256") != PARENT_INVENTORY_CANONICAL_SHA256:
        raise CandidateError("父报告未绑定冻结 inventory")
    return report, manifest


def audit_parent_raw_evidence() -> dict[str, Any]:
    if not PARENT_EVIDENCE_ROOT.is_dir():
        raise CandidateError(f"缺少父 raw evidence: {PARENT_EVIDENCE_ROOT}")
    _assert_file_hash(PARENT_INVENTORY, PARENT_INVENTORY_FILE_SHA256, "父 inventory")
    _assert_file_hash(PARENT_COMPLETED, PARENT_COMPLETED_FILE_SHA256, "父 completed marker")
    inventory = load_json(PARENT_INVENTORY)
    completed = load_json(PARENT_COMPLETED)
    observed_inventory = _current_parent_inventory()
    if inventory != observed_inventory:
        raise CandidateError("父 evidence inventory 与只读文件不一致")
    if inventory.get("canonical_sha256") != PARENT_INVENTORY_CANONICAL_SHA256:
        raise CandidateError("父 evidence inventory canonical SHA-256 漂移")
    if completed != {
        "completed_at": "2026-10-14T10:14:00.900547+00:00",
        "decision": "proceed_to_jev_progress_budget_calibration_design",
        "identity": PARENT_IDENTITY,
        "inventory_canonical_sha256": PARENT_INVENTORY_CANONICAL_SHA256,
        "status": "completed",
        "zero_managed_resources": True,
    }:
        raise CandidateError("父 completed marker 漂移")
    return {
        "valid": True,
        "file_count": inventory["file_count"],
        "total_bytes": inventory["total_bytes"],
        "inventory_canonical_sha256": inventory["canonical_sha256"],
        "zero_managed_resources": completed["zero_managed_resources"],
    }


def provider_state(state: dict[str, Any]) -> dict[str, Any]:
    model_input = state.get("model_input", state)
    expected = {
        "build_system",
        "candidate_action_families",
        "phase_facts",
        "progress_facts",
        "semantic_failure_log",
        "state_id",
    }
    if set(model_input) != expected:
        raise CandidateError("父 model_input 字段漂移")
    if tuple(model_input["candidate_action_families"]) != ACTION_FAMILIES:
        raise CandidateError("父候选动作目录漂移")
    if model_input["build_system"] not in BUILD_SYSTEMS:
        raise CandidateError("父 build_system 漂移")
    if not isinstance(model_input["phase_facts"], dict) or not isinstance(model_input["progress_facts"], dict):
        raise CandidateError("确定性进展事实不是对象")
    if not isinstance(model_input["semantic_failure_log"], str) or not model_input["semantic_failure_log"]:
        raise CandidateError("语义失败日志为空")
    return {
        "build_system": model_input["build_system"],
        "phase_facts": copy.deepcopy(model_input["phase_facts"]),
        "progress_facts": copy.deepcopy(model_input["progress_facts"]),
        "semantic_failure_log": model_input["semantic_failure_log"],
    }


def _choice_contract(order: tuple[str, ...]) -> dict[str, Any]:
    return {
        "type": "choice",
        "instructions": ACTION_INSTRUCTIONS,
        "criteria": {action: ACTION_DESCRIPTIONS[action] for action in order},
    }


def provider_questions() -> dict[str, Choice]:
    return {
        "next_action_primary": Choice(
            instructions=ACTION_INSTRUCTIONS,
            criteria={action: ACTION_DESCRIPTIONS[action] for action in PRIMARY_ACTION_ORDER},
        ),
        "next_action_order_sensitivity": Choice(
            instructions=ACTION_INSTRUCTIONS,
            criteria={action: ACTION_DESCRIPTIONS[action] for action in SENSITIVITY_ACTION_ORDER},
        ),
    }


def request_fingerprint(state: dict[str, Any], questions: dict[str, Choice]) -> str:
    payload = {
        "model": MODEL_ID,
        "state": state,
        "questions": {key: question.model_dump(mode="json", exclude_none=True) for key, question in questions.items()},
    }
    return canonical_sha256(payload)


def _selected_rows(rows: Iterable[dict[str, Any]], state_ids: set[str], key: str) -> list[dict[str, Any]]:
    selected = [copy.deepcopy(row) for row in rows if row["state_id"] in state_ids]
    return sorted(selected, key=lambda row: row[key])


def _baseline_summary(rows: list[dict[str, Any]], system_by_state: dict[str, str]) -> dict[str, Any]:
    direct_rows = [row for row in rows if row["predicted_route"] == "direct"]
    return {
        "decision_count": len(rows),
        "joint_correct": sum(row["correct"] for row in rows),
        "direct_count": len(direct_rows),
        "wrong_direct_count": sum(not row["correct"] for row in direct_rows),
        "per_build_system_joint_correct": {system: sum(row["correct"] for row in rows if system_by_state[row["state_id"]] == system) for system in BUILD_SYSTEMS},
    }


def derive_split_contract(report: dict[str, Any], split: str) -> dict[str, Any]:
    if split not in SPLITS:
        raise CandidateError(f"未知 split: {split}")
    families = SPLIT_FAMILIES[split]
    family_set = set(families.values())
    states = sorted(
        (copy.deepcopy(row) for row in report["states"] if row["project_family"] in family_set),
        key=lambda row: row["state_id"],
    )
    state_ids = {row["state_id"] for row in states}
    labels = _selected_rows(report["analysis"]["action_labels"], state_ids, "state_id")
    decisions = _selected_rows(report["analysis"]["budget_decisions"], state_ids, "decision_id")
    rule_rows = _selected_rows(report["analysis"]["rule_gate"]["rows"], state_ids, "decision_id")
    tfidf_rows = _selected_rows(report["analysis"]["tfidf_budgetfit"]["rows"], state_ids, "decision_id")
    tfidf_action_rows = _selected_rows(report["analysis"]["tfidf_budgetfit"]["action_rows"], state_ids, "state_id")
    provider_rows = [{"state_id": row["state_id"], "provider_state": provider_state(row)} for row in states]
    system_by_state = {row["state_id"]: row["build_system"] for row in states}
    return {
        "project_families": {system: families[system] for system in BUILD_SYSTEMS},
        "project_family_count": len(family_set),
        "state_count": len(states),
        "state_ids": sorted(state_ids),
        "budget_decision_count": len(decisions),
        "states_canonical_sha256": canonical_sha256(states),
        "provider_states_canonical_sha256": canonical_sha256(provider_rows),
        "action_labels_canonical_sha256": canonical_sha256(labels),
        "budget_decisions_canonical_sha256": canonical_sha256(decisions),
        "rule_gate_rows_canonical_sha256": canonical_sha256(rule_rows),
        "tfidf_budgetfit_rows_canonical_sha256": canonical_sha256(tfidf_rows),
        "tfidf_action_rows_canonical_sha256": canonical_sha256(tfidf_action_rows),
        "rule_gate": _baseline_summary(rule_rows, system_by_state),
        "tfidf_budgetfit": _baseline_summary(tfidf_rows, system_by_state),
        "oracle_routes": dict(sorted(Counter(row["optimal_route"] for row in decisions).items())),
    }


def _validate_split_contract(report: dict[str, Any], contract: dict[str, Any]) -> None:
    calibration = contract["calibration"]
    evaluation = contract["evaluation"]
    if set(calibration["state_ids"]) & set(evaluation["state_ids"]):
        raise CandidateError("calibration/evaluation state 重叠")
    if set(calibration["project_families"].values()) & set(evaluation["project_families"].values()):
        raise CandidateError("calibration/evaluation project family 重叠")
    for split in SPLITS:
        current = contract[split]
        if current["project_family_count"] != 3 or current["state_count"] != 15 or current["budget_decision_count"] != 45:
            raise CandidateError(f"{split} 规模漂移")
        selected = [row for row in report["states"] if row["state_id"] in current["state_ids"]]
        if Counter(row["build_system"] for row in selected) != {system: 5 for system in BUILD_SYSTEMS}:
            raise CandidateError(f"{split} 构建系统覆盖漂移")
    if evaluation["rule_gate"] != {
        "decision_count": 45,
        "joint_correct": 27,
        "direct_count": 30,
        "wrong_direct_count": 18,
        "per_build_system_joint_correct": {system: 9 for system in BUILD_SYSTEMS},
    }:
        raise CandidateError("evaluation RuleGate 冻结基线漂移")
    if evaluation["tfidf_budgetfit"] != {
        "decision_count": 45,
        "joint_correct": 39,
        "direct_count": 18,
        "wrong_direct_count": 0,
        "per_build_system_joint_correct": {system: 13 for system in BUILD_SYSTEMS},
    }:
        raise CandidateError("evaluation TF-IDF+BudgetFit 冻结基线漂移")
    if evaluation["oracle_routes"] != {"direct": 24, "escalate_agent": 3, "stop": 18}:
        raise CandidateError("evaluation oracle route 分布漂移")


def generate_manifest() -> dict[str, Any]:
    report, parent_manifest = validate_parent_sources()
    split_contract = {split: derive_split_contract(report, split) for split in SPLITS}
    _validate_split_contract(report, split_contract)
    parent_design = parent_manifest["design"]
    return {
        "$schema": "../schemas/forge-jev-progress-budget-calibration-candidate-v1.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": "forge_jev_progress_budget_calibration_candidate",
        "identity": IDENTITY,
        "issue_url": ISSUE_URL,
        "status": "candidate_zero_provider",
        "authorization": {
            "credential_content_read_authorized": False,
            "credential_presence_and_mode_check_authorized": True,
            "provider_calls_authorized": False,
            "jev_calls_authorized": False,
            "agent_calls_authorized": False,
            "model_tokens_authorized": 0,
            "formal_attempt_creation_authorized": False,
            "formal_provider_evidence_write_authorized": False,
            "controller_implementation_authorized": False,
            "historical_evidence_write_authorized": False,
        },
        "documents": {
            "spec": {"path": _relative(SPEC_PATH), "file_sha256": SPEC_FILE_SHA256},
            "plan": {"path": _relative(PLAN_PATH)},
            "api_audit": {"path": _relative(API_AUDIT_PATH), "file_sha256": API_AUDIT_FILE_SHA256},
            "preregistration": {"path": _relative(PREREGISTRATION)},
        },
        "parent_contract": {
            "identity": PARENT_IDENTITY,
            "report": {"path": _relative(PARENT_REPORT), "file_sha256": PARENT_REPORT_FILE_SHA256},
            "manifest": {
                "path": _relative(PARENT_MANIFEST),
                "file_sha256": PARENT_MANIFEST_FILE_SHA256,
                "canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
            },
            "evidence": {
                "root": _relative(PARENT_EVIDENCE_ROOT),
                "inventory_path": _relative(PARENT_INVENTORY),
                "inventory_file_sha256": PARENT_INVENTORY_FILE_SHA256,
                "inventory_canonical_sha256": PARENT_INVENTORY_CANONICAL_SHA256,
                "completed_path": _relative(PARENT_COMPLETED),
                "completed_file_sha256": PARENT_COMPLETED_FILE_SHA256,
                "read_only": True,
            },
        },
        "data_contract": {
            "split_rule": "first_parent_source_pool_family_per_build_system_for_calibration_second_for_evaluation",
            "project_family_overlap_allowed": False,
            "evaluation_single_analysis_only": True,
            "split": split_contract,
            "model_input_fields": list(PROVIDER_STATE_FIELDS),
            "excluded_model_input_fields": [
                "state_id",
                "project_id",
                "project_family",
                "commit",
                "fault_name",
                "fault_index",
                "candidate_action_families",
                "bound_commands",
                "safe_actions",
                "optimal_action",
                "action_outcome",
                "action_cost",
                "budget_profile",
                "remaining_budget",
                "baseline_prediction",
            ],
        },
        "provider_contract": {
            "provider": "TypeSafe AI",
            "api_base_url": API_BASE_URL,
            "endpoint": API_ENDPOINT,
            "credential_env": CREDENTIAL_ENV,
            "credential_file": CREDENTIAL_FILE.name,
            "sdk_distribution": SDK_DISTRIBUTION,
            "sdk_version": SDK_VERSION,
            "sdk_default_max_retries": 2,
            "model": MODEL_ID,
            "aliases_forbidden": ["jev-latest", "jev-preview"],
            "response_model_must_equal_request_model": True,
            "timeout_seconds": 30.0,
            "max_retries": 0,
            "one_physical_request_per_state": True,
            "input_price_usd_per_billion_tokens": 42.0,
            "output_tokens_free": True,
            "sdk_log_level": "off",
        },
        "request_contract": {
            "question_ids": list(QUESTION_IDS),
            "primary": _choice_contract(PRIMARY_ACTION_ORDER),
            "order_sensitivity": _choice_contract(SENSITIVITY_ACTION_ORDER),
            "same_request": True,
            "shell_generation_by_model": False,
        },
        "response_contract": {
            "probability_keys": list(ACTION_FAMILIES),
            "probability_sum_absolute_tolerance": PROBABILITY_SUM_TOLERANCE,
            "normalize_after_sum_validation": True,
            "choice_must_be_probability_argmax": True,
            "choice_confidence_formula": "(p_max - 1/n) / (1 - 1/n)",
            "confidence_formula_absolute_tolerance": CONFIDENCE_FORMULA_TOLERANCE,
            "store_request_id_usage_latency_model_and_full_probabilities": True,
            "store_authorization_header": False,
            "store_raw_credential": False,
        },
        "calibration_contract": {
            "actions": list(LOCAL_ACTIONS),
            "row_count": 45,
            "input": "logit(clipped_jev_probability_for_local_action)",
            "label": "parent_safe_actions_contains_local_action",
            "clip_epsilon": PLATT_EPSILON,
            "library": SKLEARN_DISTRIBUTION,
            "library_version": ">=1.7,<2",
            "estimator": "LogisticRegression",
            "parameters": {
                "C": 1.0,
                "solver": "liblinear",
                "random_state": CALIBRATION_RANDOM_STATE,
                "max_iter": 1000,
            },
            "threshold_rule": "maximum_coverage_with_zero_observed_unsafe_direct_tie_higher_threshold",
            "minimum_calibration_direct_state_count": 5,
            "minimum_per_build_system_direct_state_count": 1,
            "raw_probability_threshold_selected_separately": True,
            "order_disagreement_forces_rejection": True,
        },
        "budget_fit_contract": {
            "budget_not_sent_to_jev": True,
            "budget_profiles": parent_design["budget_profiles"],
            "direct_route_charges": parent_design["direct_route_charges"],
            "agent_reservation": parent_design["agent_reservation"],
            "route_order": ["accepted_local_direct_if_fit", "escalate_agent_if_fit", "stop"],
            "jev_request_cost_not_backfilled_into_parent_continuation_budget": True,
        },
        "future_provider_budget": {
            "calibration_requests": 15,
            "evaluation_requests": 15,
            "maximum_physical_requests": 30,
            "maximum_input_tokens": 200000,
            "maximum_output_tokens": 50000,
            "maximum_model_cost_usd": 0.0084,
            "currently_authorized": False,
        },
        "qualification_thresholds": {
            "calibration": {
                "complete_valid_responses": 15,
                "minimum_direct_state_count": 5,
                "minimum_per_build_system_direct_state_count": 1,
                "maximum_observed_unsafe_direct_count": 0,
            },
            "evaluation": {
                "complete_valid_responses": 15,
                "minimum_exact_optimal_action_count": 12,
                "minimum_exact_optimal_action_per_build_system": 4,
                "minimum_safe_action_count": 14,
                "minimum_order_agreement_count": 14,
                "minimum_direct_decision_count": 14,
                "maximum_wrong_direct_risk": 0.10,
                "minimum_joint_correct": 32,
            },
            "incremental_over_tfidf": {
                "minimum_joint_correct_per_build_system": 13,
                "option_a_minimum_joint_correct": 42,
                "option_b_minimum_direct_decision_count": 21,
                "option_b_minimum_joint_correct": 39,
                "option_b_maximum_wrong_direct_risk": 0.10,
            },
        },
        "decisions": {
            "calibration_failure": "stop_before_progress_budget_evaluation",
            "evaluation_core_failure": "stop_jev_progress_budget_routing_before_controller",
            "incremental_failure": "stop_jev_as_incremental_component_keep_semantic_budget_method",
            "all_pass": "proceed_to_frozen_response_progress_budget_controller_replay_design",
        },
        "stopping_rules": {
            "calibration_failure_stops_before_evaluation": True,
            "stop_on_credential_error": True,
            "stop_on_http_401_or_403": True,
            "stop_on_model_version_drift": True,
            "stop_on_response_contract_drift": True,
            "retry_failed_request": False,
            "replace_failed_state": False,
            "backfill_failed_state": False,
            "adjust_prompt_split_threshold_or_label_after_evaluation": False,
        },
        "publication_gate": {
            "candidate_must_be_committed_and_pushed_before_credential_read": True,
            "requires_separate_authorized_identity": True,
            "authorized_identity_must_bind_exact_git_revision": True,
        },
    }


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-jev-progress-budget-calibration-candidate-v1.schema.json",
        "title": "Forge Jev progress-budget calibration candidate v1",
        "const": manifest,
    }


def generate_contract_files() -> None:
    manifest = generate_manifest()
    schema = generate_schema(manifest)
    jsonschema.Draft202012Validator.check_schema(schema)
    write_json(DEFAULT_MANIFEST, manifest)
    write_json(DEFAULT_SCHEMA, schema)


def validate_manifest(manifest: dict[str, Any], *, check_schema: bool = True) -> dict[str, Any]:
    expected = generate_manifest()
    if manifest != expected:
        raise CandidateError("candidate manifest 无法从冻结父证据确定重建")
    authorization = manifest["authorization"]
    permitted_true = {"credential_presence_and_mode_check_authorized"}
    for key, value in authorization.items():
        if key in permitted_true:
            if value is not True:
                raise CandidateError(f"candidate metadata 权限漂移: {key}")
        elif key == "model_tokens_authorized":
            if value != 0:
                raise CandidateError("candidate model token 权限必须为 0")
        elif value is not False:
            raise CandidateError(f"candidate 意外授权真实执行: {key}")
    if check_schema:
        schema = load_json(DEFAULT_SCHEMA)
        if schema != generate_schema(manifest):
            raise CandidateError("const JSON Schema 漂移")
        jsonschema.validate(manifest, schema)
    return manifest


def load_contract() -> dict[str, Any]:
    return validate_manifest(load_json(DEFAULT_MANIFEST))


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CandidateError(f"{label} 不是有限数值")
    observed = float(value)
    if not math.isfinite(observed):
        raise CandidateError(f"{label} 不是有限数值")
    return observed


def _validate_choice_answer(answer: Any) -> dict[str, Any]:
    if getattr(answer, "type", None) != "choice":
        raise CandidateError("Jev answer type 不是 choice")
    probabilities = dict(answer.probabilities)
    if set(probabilities) != set(ACTION_FAMILIES):
        raise CandidateError("Jev probability key 漂移")
    raw = {action: _number(probabilities[action], f"{action} probability") for action in ACTION_FAMILIES}
    if any(value < 0.0 or value > 1.0 for value in raw.values()):
        raise CandidateError("Jev probability 越界")
    total = sum(raw.values())
    if abs(total - 1.0) > PROBABILITY_SUM_TOLERANCE or total <= 0.0:
        raise CandidateError("Jev probability 总和漂移")
    maximum = max(raw.values())
    if answer.choice not in ACTION_FAMILIES or not math.isclose(raw[answer.choice], maximum, abs_tol=1e-12):
        raise CandidateError("Jev choice 与最高概率不一致")
    confidence = _number(answer.confidence, "Jev confidence")
    expected_confidence = (maximum - 0.25) / 0.75
    if abs(confidence - expected_confidence) > CONFIDENCE_FORMULA_TOLERANCE:
        raise CandidateError("Jev confidence 与官方公式不一致")
    return {
        "choice": answer.choice,
        "raw_probabilities": raw,
        "raw_probability_sum": total,
        "normalized_probabilities": {action: raw[action] / total for action in ACTION_FAMILIES},
        "confidence": confidence,
        "recomputed_confidence": expected_confidence,
    }


def normalize_response(response: Any, *, latency_ms: float) -> dict[str, Any]:
    latency = _number(latency_ms, "latency_ms")
    if latency < 0.0:
        raise CandidateError("latency_ms 不能为负")
    if response.model != MODEL_ID:
        raise CandidateError(f"Jev 响应模型漂移: {response.model}")
    if set(response.answers) != set(QUESTION_IDS):
        raise CandidateError("Jev answer 集合漂移")
    if not response.request_id:
        raise CandidateError("Jev 响应缺少 request id")
    usage = response.usage
    for field in ("input_tokens", "output_tokens"):
        value = getattr(usage, field, None)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise CandidateError(f"Jev {field} usage 非法")
    answers = {question_id: _validate_choice_answer(response.answers[question_id]) for question_id in QUESTION_IDS}
    return {
        "model": response.model,
        "request_id": response.request_id,
        "answers": answers,
        "usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        },
        "cost_usd": usage.input_tokens * INPUT_PRICE_USD_PER_MILLION_TOKENS / 1_000_000,
        "latency_ms": latency,
        "order_agreement": (answers["next_action_primary"]["choice"] == answers["next_action_order_sensitivity"]["choice"]),
    }


def _logit(probability: float) -> float:
    clipped = min(max(probability, PLATT_EPSILON), 1.0 - PLATT_EPSILON)
    return math.log(clipped / (1.0 - clipped))


def fit_platt(rows: list[dict[str, Any]]) -> LogisticRegression:
    if len(rows) != 45:
        raise CandidateError("Platt calibration 必须恰好包含 45 个 local-action rows")
    probabilities = [_number(row.get("probability"), "calibration probability") for row in rows]
    labels = [row.get("safe") for row in rows]
    if any(probability < 0.0 or probability > 1.0 for probability in probabilities):
        raise CandidateError("calibration probability 越界")
    if any(not isinstance(label, bool) for label in labels) or set(labels) != {False, True}:
        raise CandidateError("Platt calibration 标签必须同时包含正负类")
    estimator = LogisticRegression(
        C=1.0,
        solver="liblinear",
        random_state=CALIBRATION_RANDOM_STATE,
        max_iter=1000,
    )
    estimator.fit([[_logit(probability)] for probability in probabilities], labels)
    return estimator


def calibrated_safe_probability(estimator: LogisticRegression, probability: float) -> float:
    observed = _number(probability, "Jev action probability")
    if observed < 0.0 or observed > 1.0:
        raise CandidateError("Jev action probability 越界")
    classes = list(estimator.classes_)
    if True not in classes:
        raise CandidateError("Platt estimator 缺少正类")
    return float(estimator.predict_proba([[_logit(observed)]])[0][classes.index(True)])


def select_zero_error_threshold(
    rows: list[dict[str, Any]],
    *,
    probability_field: str,
) -> dict[str, Any]:
    candidates = []
    for row in rows:
        action = row.get("selected_action")
        if row.get("order_agreement") is not True or action not in LOCAL_ACTIONS:
            continue
        probability = _number(row.get(probability_field), probability_field)
        if probability < 0.0 or probability > 1.0:
            raise CandidateError(f"{probability_field} 越界")
        if not isinstance(row.get("safe"), bool) or row.get("build_system") not in BUILD_SYSTEMS:
            raise CandidateError("threshold row 标签或构建系统非法")
        candidates.append({**row, "_probability": probability})
    if not candidates:
        raise CandidateError("没有可用于 threshold selection 的一致 local-action state")

    best: tuple[int, float, list[dict[str, Any]]] | None = None
    for threshold in sorted({row["_probability"] for row in candidates}, reverse=True):
        selected = [row for row in candidates if row["_probability"] >= threshold]
        if any(row["safe"] is False for row in selected):
            continue
        candidate = (len(selected), threshold, selected)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    if best is None:
        raise CandidateError("不存在零 observed unsafe direct threshold")
    coverage, threshold, selected = best
    per_system = Counter(row["build_system"] for row in selected)
    return {
        "threshold": threshold,
        "direct_state_count": coverage,
        "unsafe_direct_count": 0,
        "per_build_system_direct_state_count": {system: per_system[system] for system in BUILD_SYSTEMS},
        "selected_state_ids": sorted(row["state_id"] for row in selected),
        "qualification_passed": (coverage >= 5 and all(per_system[system] >= 1 for system in BUILD_SYSTEMS)),
    }


def _fits(charge: dict[str, int], remaining_budget: dict[str, int]) -> bool:
    if set(charge) != set(remaining_budget):
        raise CandidateError("budget 维度漂移")
    return all(charge[key] <= remaining_budget[key] for key in remaining_budget)


def budget_fit_route(
    *,
    selected_action: str,
    order_agreement: bool,
    calibrated_probability: float | None,
    threshold: float,
    remaining_budget: dict[str, int],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    if selected_action not in ACTION_FAMILIES:
        raise CandidateError("Jev selected_action 漂移")
    contract = manifest["budget_fit_contract"]
    accepted_local = False
    if selected_action in LOCAL_ACTIONS and order_agreement:
        if calibrated_probability is None:
            raise CandidateError("local action 缺少 calibrated probability")
        accepted_local = _number(calibrated_probability, "calibrated probability") >= threshold
    if accepted_local:
        charge = contract["direct_route_charges"][selected_action]
        if _fits(charge, remaining_budget):
            return {"route": "direct", "action": selected_action, "gate": "calibrated_local_action"}
    if _fits(contract["agent_reservation"], remaining_budget):
        return {"route": "escalate_agent", "action": "escalate_agent", "gate": "agent_reservation"}
    return {"route": "stop", "action": None, "gate": "insufficient_budget"}


def mock_sdk_roundtrip() -> dict[str, Any]:
    report = load_json(PARENT_REPORT)
    calibration_family = SPLIT_FAMILIES["calibration"]["cmake"]
    state_row = next(row for row in report["states"] if row["project_family"] == calibration_family)
    state = provider_state(state_row)
    questions = provider_questions()
    observed: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        observed["method"] = request.method
        observed["url"] = str(request.url)
        observed["authorized"] = request.headers.get("authorization") == "Bearer mock-key"
        observed["body"] = json.loads(request.content)
        answer = {
            "type": "choice",
            "choice": "configure",
            "confidence": 0.6,
            "probabilities": {
                "dependency": 0.1,
                "configure": 0.7,
                "build": 0.1,
                "escalate_agent": 0.1,
            },
        }
        return httpx2.Response(
            200,
            headers={"x-typesafe-request-id": "req-progress-budget-zero-provider-mock"},
            json={
                "model": MODEL_ID,
                "answers": {question_id: answer for question_id in QUESTION_IDS},
                "usage": {"input_tokens": 321, "output_tokens": 20},
            },
        )

    with TypeSafeClient(
        api_key="mock-key",
        model=MODEL_ID,
        retry=RetryPolicy(max_retries=0, timeout=30.0),
        transport=httpx2.MockTransport(handler),
        base_url=API_BASE_URL,
    ) as client:
        response = client.system_one(state=state, questions=questions)
    normalized = normalize_response(response, latency_ms=1.0)
    body = observed["body"]
    if (
        observed["method"] != "POST"
        or observed["url"] != f"{API_BASE_URL}{API_ENDPOINT}"
        or observed["authorized"] is not True
        or body["model"] != MODEL_ID
        or tuple(body["state"]) != PROVIDER_STATE_FIELDS
        or tuple(body["questions"]) != QUESTION_IDS
        or tuple(body["questions"]["next_action_primary"]["criteria"]) != PRIMARY_ACTION_ORDER
        or tuple(body["questions"]["next_action_order_sensitivity"]["criteria"]) != SENSITIVITY_ACTION_ORDER
    ):
        raise CandidateError("TypeSafe SDK 模拟请求合同漂移")
    serialized = json.dumps(body["state"], ensure_ascii=False, sort_keys=True)
    for forbidden in (
        state_row["state_id"],
        state_row["project_family"],
        "remaining_budget",
        "safe_actions",
        "optimal_action",
        "bound_commands",
    ):
        if forbidden in serialized:
            raise CandidateError(f"模拟 Provider state 泄漏禁止字段: {forbidden}")
    return {
        "provider_calls": 0,
        "credential_content_reads": 0,
        "transport": "httpx2.MockTransport",
        "request_fingerprint": request_fingerprint(state, questions),
        "normalized_response": normalized,
    }


def credential_metadata() -> dict[str, Any]:
    exists = CREDENTIAL_FILE.exists()
    metadata: dict[str, Any] = {
        "credential_env_present": CREDENTIAL_ENV in os.environ,
        "credential_file_present": exists,
        "credential_file_is_symlink": CREDENTIAL_FILE.is_symlink(),
        "credential_file_mode": None,
        "credential_content_reads": 0,
    }
    if exists:
        metadata["credential_file_mode"] = format(stat.S_IMODE(CREDENTIAL_FILE.lstat().st_mode), "04o")
    return metadata


def preflight() -> dict[str, Any]:
    manifest = load_contract()
    parent_audit = audit_parent_raw_evidence()
    installed_sdk = version(SDK_DISTRIBUTION)
    installed_sklearn = version(SKLEARN_DISTRIBUTION)
    if installed_sdk != SDK_VERSION:
        raise CandidateError(f"TypeSafe SDK 版本漂移: {installed_sdk} != {SDK_VERSION}")
    if not Version("1.7") <= Version(installed_sklearn) < Version("2"):
        raise CandidateError(f"scikit-learn 版本不在冻结范围: {installed_sklearn}")
    for path, label in (
        (PLAN_PATH, "candidate plan"),
        (PREREGISTRATION, "candidate preregistration"),
    ):
        if not path.is_file():
            raise CandidateError(f"缺少 {label}: {path}")
    mock = mock_sdk_roundtrip()
    return {
        "ready": True,
        "identity": IDENTITY,
        "issue_url": ISSUE_URL,
        "parent_identity": PARENT_IDENTITY,
        "calibration_state_count": manifest["data_contract"]["split"]["calibration"]["state_count"],
        "evaluation_state_count": manifest["data_contract"]["split"]["evaluation"]["state_count"],
        "sdk_version": installed_sdk,
        "scikit_learn_version": installed_sklearn,
        "model": MODEL_ID,
        "provider_calls": mock["provider_calls"],
        "credential_content_reads": mock["credential_content_reads"],
        "credential_metadata": credential_metadata(),
        "model_tokens": 0,
        "formal_attempts_created": 0,
        "formal_provider_evidence_writes": 0,
        "historical_evidence_writes": 0,
        "mock_request_fingerprint": mock["request_fingerprint"],
        "parent_inventory_canonical_sha256": PARENT_INVENTORY_CANONICAL_SHA256,
        "parent_raw_evidence_audit": parent_audit,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("generate", "validate", "show-plan", "mock-check", "preflight"):
        subparsers.add_parser(command)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "generate":
        generate_contract_files()
        print(canonical_sha256(load_json(DEFAULT_MANIFEST)))
        return 0
    if args.command == "validate":
        print(canonical_sha256(load_contract()))
        return 0
    if args.command == "show-plan":
        manifest = load_contract()
        print(
            json.dumps(
                {
                    "identity": manifest["identity"],
                    "status": manifest["status"],
                    "authorization": manifest["authorization"],
                    "split": manifest["data_contract"]["split"],
                    "future_provider_budget": manifest["future_provider_budget"],
                    "qualification_thresholds": manifest["qualification_thresholds"],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "mock-check":
        print(json.dumps(mock_sdk_roundtrip(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    print(json.dumps(preflight(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
