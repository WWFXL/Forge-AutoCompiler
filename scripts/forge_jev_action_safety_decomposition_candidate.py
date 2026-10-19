#!/usr/bin/env python3
"""Issue #465 Jev 逐动作安全判断问题分解零 Provider 候选。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import stat
from collections import Counter, defaultdict
from importlib.metadata import version
from pathlib import Path
from typing import Any

import httpx2
import jsonschema
from packaging.version import Version
from sklearn.linear_model import LogisticRegression
from typesafe_sdk import Noul, RetryPolicy, TypeSafeClient

import forge_jev_progress_budget_calibration_candidate as parent

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
IDENTITY = "cpp-jev-action-safety-decomposition-candidate-v1"
FORMAL_IDENTITY = "cpp-jev-action-safety-decomposition-v1"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/465"
SCHEMA_VERSION = "forge-jev-action-safety-decomposition-candidate-1.0.0"

SPEC_PATH = (
    REPO_ROOT / "docs/research/2026-10-17-jev-action-safety-decomposition-spec.md"
)
PLAN_PATH = (
    REPO_ROOT / "docs/research/2026-10-17-jev-action-safety-decomposition-plan.md"
)
PREREGISTRATION = (
    REPO_ROOT
    / "benchmarks/preregistrations/cpp-jev-action-safety-decomposition-candidate-v1.md"
)
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "benchmarks/manifests/cpp-jev-action-safety-decomposition-candidate-v1.json"
)
DEFAULT_SCHEMA = (
    REPO_ROOT
    / "benchmarks/schemas/forge-jev-action-safety-decomposition-candidate-v1.schema.json"
)

HISTORICAL_REPORT = (
    REPO_ROOT / "benchmarks/reports/cpp-jev-progress-budget-calibration-v1.json"
)
HISTORICAL_REPORT_FILE_SHA256 = (
    "fcda7993369100d51409c2595853c7f03439c6b5f31eb2d6020103e6e149c4d0"
)
HISTORICAL_EVIDENCE_ROOT = (
    REPO_ROOT
    / ".compile-sessions/benchmark-evidence-jev-progress-budget-calibration-v1"
)
HISTORICAL_INVENTORY = HISTORICAL_EVIDENCE_ROOT / "inventory.json"
HISTORICAL_INVENTORY_FILE_SHA256 = (
    "4bb6180a300733d2313d7e688fe611e6cbeb588be30ac57be57593562ed7c641"
)
HISTORICAL_INVENTORY_CANONICAL_SHA256 = (
    "83e6e5830ef551e4a2547666c98c4de8dcbeadd165c5f35cb876d25807482582"
)
HISTORICAL_COMPLETED = HISTORICAL_EVIDENCE_ROOT / "completed.json"
HISTORICAL_COMPLETED_FILE_SHA256 = (
    "ace66d9f5ac800065de397762e00beaec665ffabc5bfe2a6b42ef9f09eaa1648"
)

CREDENTIAL_FILE = REPO_ROOT / "jev-apikey.txt"
CONDITIONS = ("action_noul", "action_card_noul")
SPLITS = parent.SPLITS
BUILD_SYSTEMS = parent.BUILD_SYSTEMS
LOCAL_ACTIONS = parent.LOCAL_ACTIONS
PRIMARY_ACTION_ORDER = LOCAL_ACTIONS
SENSITIVITY_ACTION_ORDER = tuple(reversed(LOCAL_ACTIONS))
ACTION_COSTS = {"dependency": 3, "configure": 2, "build": 1}
PLATT_EPSILON = 1e-6
PLATT_RANDOM_STATE = 465


class CandidateError(RuntimeError):
    """候选合同、父证据或模拟 SDK 行为发生漂移。"""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
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


def _inventory_without_markers(root: Path) -> dict[str, Any]:
    excluded = {"inventory.json", "completed.json"}
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
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
        "identity": "cpp-jev-progress-budget-calibration-v1",
        "files": rows,
        "file_count": len(rows),
        "total_bytes": sum(row["size_bytes"] for row in rows),
        "canonical_sha256": canonical_sha256(rows),
    }


def audit_historical_evidence() -> dict[str, Any]:
    _assert_file_hash(HISTORICAL_REPORT, HISTORICAL_REPORT_FILE_SHA256, "历史 Jev 报告")
    _assert_file_hash(
        HISTORICAL_INVENTORY,
        HISTORICAL_INVENTORY_FILE_SHA256,
        "历史 Jev inventory",
    )
    _assert_file_hash(
        HISTORICAL_COMPLETED,
        HISTORICAL_COMPLETED_FILE_SHA256,
        "历史 Jev completed marker",
    )
    inventory = load_json(HISTORICAL_INVENTORY)
    observed = _inventory_without_markers(HISTORICAL_EVIDENCE_ROOT)
    if inventory != observed:
        raise CandidateError("历史 Jev evidence inventory 与只读文件不一致")
    if inventory["canonical_sha256"] != HISTORICAL_INVENTORY_CANONICAL_SHA256:
        raise CandidateError("历史 Jev inventory canonical SHA-256 漂移")
    report = load_json(HISTORICAL_REPORT)
    if (
        report.get("identity") != "cpp-jev-progress-budget-calibration-v1"
        or report.get("decision") != "stop_before_progress_budget_evaluation"
        or report.get("evaluation") is not None
    ):
        raise CandidateError("历史 Jev 停止决定漂移")
    return {
        "valid": True,
        "file_count": inventory["file_count"],
        "total_bytes": inventory["total_bytes"],
        "inventory_canonical_sha256": inventory["canonical_sha256"],
        "evaluation_provider_requests": 0,
    }


def _parent_contract() -> dict[str, Any]:
    contract = parent.load_contract()
    parent.audit_parent_raw_evidence()
    return contract


def split_rows(
    split: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if split not in SPLITS:
        raise CandidateError(f"未知 split: {split}")
    contract = _parent_contract()
    report = load_json(parent.PARENT_REPORT)
    state_ids = set(contract["data_contract"]["split"][split]["state_ids"])
    states = sorted(
        (
            copy.deepcopy(row)
            for row in report["states"]
            if row["state_id"] in state_ids
        ),
        key=lambda row: row["state_id"],
    )
    labels = sorted(
        (
            copy.deepcopy(row)
            for row in report["analysis"]["action_labels"]
            if row["state_id"] in state_ids
        ),
        key=lambda row: row["state_id"],
    )
    decisions = sorted(
        (
            copy.deepcopy(row)
            for row in report["analysis"]["budget_decisions"]
            if row["state_id"] in state_ids
        ),
        key=lambda row: row["decision_id"],
    )
    if len(states) != 15 or len(labels) != 15 or len(decisions) != 45:
        raise CandidateError(f"{split} 冻结数据规模漂移")
    return states, labels, decisions


def _action_row(state: dict[str, Any], action_family: str) -> dict[str, Any]:
    matches = [
        row
        for row in state["candidate_actions"]
        if row["action_family"] == action_family
    ]
    if len(matches) != 1:
        raise CandidateError(
            f"{state['state_id']} 缺少唯一 {action_family} CandidateAction"
        )
    return matches[0]


def action_card(state: dict[str, Any], action_family: str) -> dict[str, Any]:
    action = _action_row(state, action_family)
    commands = action["bound_commands"]
    if (
        not isinstance(commands, list)
        or not commands
        or not all(isinstance(command, str) and command for command in commands)
    ):
        raise CandidateError("CandidateAction bound_commands 非法")
    build_system = state["build_system"]
    if action_family == "dependency":
        if any(command.startswith("git checkout HEAD -- ") for command in commands):
            summary = "Restore one version-controlled build input from the fixed source revision."
            effect = "tracked_input_restore"
            transition = "A missing or corrupted tracked input becomes available to the existing build recipe."
            evidence = "The restored input is present and the frozen continuation can reach the strict endpoint."
        elif any("forge-cc" in command for command in commands):
            summary = "Create a deterministic compiler input marker and bind the existing build to a compiler wrapper that injects it."
            effect = "compiler_input_binding"
            transition = "The build recipe carries the required generated compiler input into clean replay."
            evidence = "The marker and compiler binding survive the frozen continuation and strict replay."
        elif any("forge_replay_marker.h" in command for command in commands):
            summary = "Create the deterministic generated compiler input required by the already-bound build configuration."
            effect = "generated_input_create"
            transition = "The generated compiler input referenced by the existing configuration becomes available."
            evidence = "The generated input survives the frozen continuation and strict replay."
        else:
            raise CandidateError("未知 dependency ActionCard 归纳模式")
    elif action_family == "configure":
        if build_system == "cmake":
            summary = "Regenerate the CMake build tree for the already-bound example or sample target."
            effect = "generated_build_state_reset"
            transition = "A fresh generated CMake build state replaces damaged or stale build metadata."
            evidence = "The configured build tree supports the frozen target build and strict replay."
        elif build_system == "make":
            summary = "Restore and verify the project Makefile used by the already-bound build target."
            effect = "makefile_restore"
            transition = "The normal Make build rules are available again without changing source inputs."
            evidence = "The restored Makefile supports the frozen build target and strict replay."
        elif build_system == "autotools":
            summary = "Regenerate Autotools inputs and configure the already-bound static-library build."
            effect = "generated_build_state_reset"
            transition = "Fresh configure output and Makefiles replace damaged or stale generated state."
            evidence = (
                "The configured tree supports the frozen build and strict replay."
            )
        else:
            raise CandidateError(f"未知构建系统: {build_system}")
    elif action_family == "build":
        if build_system == "cmake":
            summary = "Build the already-bound CMake example or sample target with bounded parallelism."
        elif build_system == "make":
            summary = "Run the already-bound Make build or test target with bounded parallelism where configured."
        elif build_system == "autotools":
            summary = "Run the generated Make build with bounded parallelism."
        else:
            raise CandidateError(f"未知构建系统: {build_system}")
        effect = "normal_build_execution"
        transition = "The existing configured state is compiled without restoring inputs or regenerating configuration."
        evidence = "The expected compiled artifact reaches the strict endpoint under the frozen continuation."
    else:
        raise CandidateError(f"未知局部动作: {action_family}")
    card = {
        "action_family": action_family,
        "operation_summary": summary,
        "bound_step_count": len(commands),
        "workspace_effect": effect,
        "expected_frontier_transition": transition,
        "expected_evidence": evidence,
    }
    serialized = json.dumps(card, ensure_ascii=False, sort_keys=True)
    for command in commands:
        if command in serialized:
            raise CandidateError("ActionCard 泄漏原始 Shell")
    return card


def provider_state(state: dict[str, Any], condition: str) -> dict[str, Any]:
    if condition not in CONDITIONS:
        raise CandidateError(f"未知 condition: {condition}")
    base = parent.provider_state(state)
    if condition == "action_card_noul":
        base["candidate_action_cards"] = {
            action: action_card(state, action) for action in LOCAL_ACTIONS
        }
    return base


def _noul_question(action: str) -> Noul:
    return Noul(
        instructions={
            "question": f"Is the already-bound {action} action safe to execute as the next local action?",
            "action_family": action,
            "safety_definition": (
                "Safe means that this bound action, followed by the frozen deterministic continuation, "
                "reaches the strict build endpoint in clean execution without an unbound repair."
            ),
            "evidence_rule": "Judge only from the supplied build state and candidate action semantics.",
        },
        criteria={
            "true": "The action is a safe next local action under the stated strict endpoint.",
            "false": "The action fails, stalls, damages state, or still requires an unbound repair.",
        },
    )


def provider_questions() -> dict[str, Noul]:
    questions: dict[str, Noul] = {}
    for action in PRIMARY_ACTION_ORDER:
        questions[f"primary_{action}"] = _noul_question(action)
    for action in SENSITIVITY_ACTION_ORDER:
        questions[f"order_sensitivity_{action}"] = _noul_question(action)
    return questions


def request_fingerprint(
    state: dict[str, Any], questions: dict[str, Noul], condition: str
) -> str:
    return canonical_sha256(
        {
            "condition": condition,
            "model": parent.MODEL_ID,
            "state": state,
            "questions": {
                key: question.model_dump(mode="json", exclude_none=True)
                for key, question in questions.items()
            },
        }
    )


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CandidateError(f"{label} 不是有限数值")
    number = float(value)
    if not math.isfinite(number):
        raise CandidateError(f"{label} 不是有限数值")
    return number


def normalize_response(response: Any, *, latency_ms: float) -> dict[str, Any]:
    if getattr(response, "model", None) != parent.MODEL_ID:
        raise CandidateError("响应模型漂移")
    request_id = getattr(response, "request_id", None)
    if not isinstance(request_id, str) or not request_id:
        raise CandidateError("响应缺少 request ID")
    answers = dict(getattr(response, "answers", {}))
    expected_ids = tuple(provider_questions())
    if tuple(answers) != expected_ids:
        raise CandidateError("Noul answer ID 或顺序漂移")
    normalized: dict[str, Any] = {}
    for question_id in expected_ids:
        answer = answers[question_id]
        if getattr(answer, "type", None) != "noul":
            raise CandidateError(f"{question_id} 不是 Noul answer")
        probability = _number(getattr(answer, "noul", None), f"{question_id}.noul")
        if probability < 0.0 or probability > 1.0:
            raise CandidateError(f"{question_id}.noul 越界")
        normalized[question_id] = probability
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    if (
        isinstance(input_tokens, bool)
        or not isinstance(input_tokens, int)
        or input_tokens < 0
        or isinstance(output_tokens, bool)
        or not isinstance(output_tokens, int)
        or output_tokens < 0
    ):
        raise CandidateError("响应 usage 漂移")
    pairs = {
        action: {
            "primary_probability": normalized[f"primary_{action}"],
            "order_sensitivity_probability": normalized[f"order_sensitivity_{action}"],
            "raw_action_score": min(
                normalized[f"primary_{action}"],
                normalized[f"order_sensitivity_{action}"],
            ),
            "absolute_order_difference": abs(
                normalized[f"primary_{action}"]
                - normalized[f"order_sensitivity_{action}"]
            ),
        }
        for action in LOCAL_ACTIONS
    }
    return {
        "model": response.model,
        "request_id": request_id,
        "answers": normalized,
        "action_pairs": pairs,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        "cost_usd": input_tokens
        * parent.INPUT_PRICE_USD_PER_MILLION_TOKENS
        / 1_000_000,
        "latency_ms": _number(latency_ms, "latency_ms"),
    }


def _logit(probability: float) -> float:
    clipped = min(max(probability, PLATT_EPSILON), 1.0 - PLATT_EPSILON)
    return math.log(clipped / (1.0 - clipped))


def fit_platt(rows: list[dict[str, Any]]) -> LogisticRegression:
    if len(rows) != 45:
        raise CandidateError("Platt calibration 必须恰好包含 45 个 action rows")
    probabilities = [
        _number(row.get("raw_action_score"), "raw_action_score") for row in rows
    ]
    labels = [row.get("safe") for row in rows]
    if any(probability < 0.0 or probability > 1.0 for probability in probabilities):
        raise CandidateError("raw_action_score 越界")
    if any(not isinstance(label, bool) for label in labels) or set(labels) != {
        False,
        True,
    }:
        raise CandidateError("Platt 标签必须同时包含正负类")
    estimator = LogisticRegression(
        C=1.0,
        solver="liblinear",
        random_state=PLATT_RANDOM_STATE,
        max_iter=1000,
    )
    estimator.fit([[_logit(value)] for value in probabilities], labels)
    return estimator


def calibrated_safe_probability(
    estimator: LogisticRegression, raw_action_score: float
) -> float:
    score = _number(raw_action_score, "raw_action_score")
    if score < 0.0 or score > 1.0:
        raise CandidateError("raw_action_score 越界")
    classes = list(estimator.classes_)
    if True not in classes:
        raise CandidateError("Platt estimator 缺少正类")
    return float(estimator.predict_proba([[_logit(score)]])[0][classes.index(True)])


def _select_for_threshold(
    rows: list[dict[str, Any]], *, probability_field: str, threshold: float
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["state_id"]].append(row)
    selected = []
    for state_id, state_rows in sorted(grouped.items()):
        eligible = [
            row
            for row in state_rows
            if _number(row.get(probability_field), probability_field) >= threshold
        ]
        if not eligible:
            continue
        choice = min(
            eligible,
            key=lambda row: (ACTION_COSTS[row["action"]], row["action"]),
        )
        selected.append({**choice, "selected_probability": choice[probability_field]})
    return selected


def select_zero_error_threshold(
    rows: list[dict[str, Any]], *, probability_field: str
) -> dict[str, Any]:
    if len(rows) != 45 or len({row["state_id"] for row in rows}) != 15:
        raise CandidateError("threshold rows 必须为 15 states x 3 actions")
    for row in rows:
        if (
            row.get("action") not in LOCAL_ACTIONS
            or row.get("build_system") not in BUILD_SYSTEMS
            or not isinstance(row.get("safe"), bool)
        ):
            raise CandidateError("threshold row 合同漂移")
    values = {_number(row.get(probability_field), probability_field) for row in rows}
    if any(value < 0.0 or value > 1.0 for value in values):
        raise CandidateError(f"{probability_field} 越界")
    candidates = sorted(values | {1.0}, reverse=True)
    best: tuple[int, float, list[dict[str, Any]]] | None = None
    for threshold in candidates:
        selected = _select_for_threshold(
            rows, probability_field=probability_field, threshold=threshold
        )
        if any(row["safe"] is False for row in selected):
            continue
        candidate = (len(selected), threshold, selected)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    if best is None:
        raise CandidateError("无法构造零 observed unsafe direct 阈值")
    coverage, threshold, selected = best
    per_system = Counter(row["build_system"] for row in selected)
    return {
        "threshold": threshold,
        "direct_state_count": coverage,
        "unsafe_direct_count": 0,
        "per_build_system_direct_state_count": {
            system: per_system[system] for system in BUILD_SYSTEMS
        },
        "selected": [
            {
                "state_id": row["state_id"],
                "action": row["action"],
                "probability": row["selected_probability"],
            }
            for row in selected
        ],
        "qualification_passed": coverage >= 5
        and all(per_system[system] >= 1 for system in BUILD_SYSTEMS),
    }


def select_action(
    rows: list[dict[str, Any]], *, probability_field: str, threshold: float
) -> str:
    if len(rows) != 3 or {row["action"] for row in rows} != set(LOCAL_ACTIONS):
        raise CandidateError("单状态必须包含三个局部动作")
    eligible = [
        row
        for row in rows
        if _number(row.get(probability_field), probability_field) >= threshold
    ]
    if not eligible:
        return "escalate_agent"
    return min(
        eligible,
        key=lambda row: (ACTION_COSTS[row["action"]], row["action"]),
    )["action"]


def _fits(charge: dict[str, int], remaining_budget: dict[str, int]) -> bool:
    if set(charge) != set(remaining_budget):
        raise CandidateError("budget 维度漂移")
    return all(charge[key] <= remaining_budget[key] for key in remaining_budget)


def budget_fit_route(
    *, selected_action: str, remaining_budget: dict[str, int], manifest: dict[str, Any]
) -> dict[str, Any]:
    if selected_action not in (*LOCAL_ACTIONS, "escalate_agent"):
        raise CandidateError("selected_action 漂移")
    contract = manifest["budget_fit_contract"]
    if selected_action in LOCAL_ACTIONS:
        charge = contract["direct_route_charges"][selected_action]
        if _fits(charge, remaining_budget):
            return {
                "route": "direct",
                "action": selected_action,
                "gate": "calibrated_action_safety",
            }
    if _fits(contract["agent_reservation"], remaining_budget):
        return {
            "route": "escalate_agent",
            "action": "escalate_agent",
            "gate": "agent_reservation",
        }
    return {"route": "stop", "action": None, "gate": "insufficient_budget"}


def _historical_reference() -> dict[str, Any]:
    report = load_json(HISTORICAL_REPORT)
    rows = report["calibration"]["action_analysis"]["rows"]
    local_rows = []
    for row in rows:
        local_choice = max(
            LOCAL_ACTIONS,
            key=lambda action: (row["probabilities"][action], -ACTION_COSTS[action]),
        )
        local_rows.append(
            {
                "state_id": row["state_id"],
                "local_choice": local_choice,
                "exact_optimal": local_choice == row["optimal_action"],
                "safe": local_choice in row["safe_actions"],
            }
        )
    return {
        "provider_requests": 0,
        "frozen_primary_choice_counts": dict(
            sorted(Counter(row["choice"] for row in rows).items())
        ),
        "frozen_exact_optimal_action_count": sum(row["exact_optimal"] for row in rows),
        "frozen_order_agreement_count": sum(row["order_agreement"] for row in rows),
        "posthoc_local_exact_optimal_action_count": sum(
            row["exact_optimal"] for row in local_rows
        ),
        "posthoc_local_safe_action_count": sum(row["safe"] for row in local_rows),
        "posthoc_local_rows": local_rows,
        "interpretation": "posthoc_design_diagnostic_only",
    }


def generate_manifest() -> dict[str, Any]:
    parent_contract = _parent_contract()
    split = copy.deepcopy(parent_contract["data_contract"]["split"])
    for split_name in SPLITS:
        states, labels, decisions = split_rows(split_name)
        split[split_name]["states_canonical_sha256"] = canonical_sha256(states)
        split[split_name]["action_labels_canonical_sha256"] = canonical_sha256(labels)
        split[split_name]["budget_decisions_canonical_sha256"] = canonical_sha256(
            decisions
        )
    historical = _historical_reference()
    return {
        "$schema": "../schemas/forge-jev-action-safety-decomposition-candidate-v1.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": "forge_jev_action_safety_decomposition_candidate",
        "identity": IDENTITY,
        "formal_identity": FORMAL_IDENTITY,
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
            "spec": {
                "path": _relative(SPEC_PATH),
                "file_sha256": file_sha256(SPEC_PATH),
            },
            "plan": {
                "path": _relative(PLAN_PATH),
                "file_sha256": file_sha256(PLAN_PATH),
            },
            "preregistration": {"path": _relative(PREREGISTRATION)},
        },
        "parent_contract": {
            "outcome_identity": parent.PARENT_IDENTITY,
            "outcome_report": {
                "path": _relative(parent.PARENT_REPORT),
                "file_sha256": parent.PARENT_REPORT_FILE_SHA256,
            },
            "outcome_inventory_canonical_sha256": parent.PARENT_INVENTORY_CANONICAL_SHA256,
            "historical_jev_identity": "cpp-jev-progress-budget-calibration-v1",
            "historical_jev_report": {
                "path": _relative(HISTORICAL_REPORT),
                "file_sha256": HISTORICAL_REPORT_FILE_SHA256,
            },
            "historical_jev_inventory_canonical_sha256": HISTORICAL_INVENTORY_CANONICAL_SHA256,
            "read_only": True,
        },
        "data_contract": {
            "project_family_overlap_allowed": False,
            "calibration_only_for_fit_and_threshold": True,
            "evaluation_single_analysis_only": True,
            "split": split,
            "base_model_input_fields": list(parent.PROVIDER_STATE_FIELDS),
            "action_card_fields": [
                "action_family",
                "operation_summary",
                "bound_step_count",
                "workspace_effect",
                "expected_frontier_transition",
                "expected_evidence",
            ],
            "excluded_model_input_fields": [
                "state_id",
                "project_id",
                "project_family",
                "commit",
                "fault_name",
                "bound_commands",
                "safe_actions",
                "optimal_action",
                "action_outcome",
                "action_cost",
                "budget_profile",
                "remaining_budget",
            ],
        },
        "conditions": {
            "four_way_choice_frozen_reference": historical,
            "action_noul": {"action_cards": False, "new_provider_requests": 30},
            "action_card_noul": {"action_cards": True, "new_provider_requests": 30},
        },
        "provider_contract": {
            **parent_contract["provider_contract"],
            "one_physical_request_per_condition_state": True,
        },
        "request_contract": {
            "question_type": "noul",
            "local_actions": list(LOCAL_ACTIONS),
            "primary_order": list(PRIMARY_ACTION_ORDER),
            "order_sensitivity_order": list(SENSITIVITY_ACTION_ORDER),
            "question_count_per_request": 6,
            "raw_action_score": "min(primary_noul, order_sensitivity_noul)",
            "same_request": True,
            "shell_generation_by_model": False,
        },
        "response_contract": {
            "answer_type": "noul",
            "probability_range": [0.0, 1.0],
            "store_request_id_usage_latency_model_and_all_noul_probabilities": True,
            "store_authorization_header": False,
            "store_raw_credential": False,
        },
        "calibration_contract": {
            "row_count_per_condition": 45,
            "input": "logit(clipped_min_of_two_noul_probabilities)",
            "label": "parent_safe_actions_contains_local_action",
            "clip_epsilon": PLATT_EPSILON,
            "estimator": "LogisticRegression",
            "parameters": {
                "C": 1.0,
                "solver": "liblinear",
                "random_state": PLATT_RANDOM_STATE,
                "max_iter": 1000,
            },
            "threshold_rule": "maximum_selector_state_coverage_with_zero_observed_unsafe_direct_tie_higher_threshold",
            "selector": "lowest_action_cost_then_action_name",
        },
        "budget_fit_contract": parent_contract["budget_fit_contract"],
        "future_provider_budget": {
            "requests_per_condition": 30,
            "maximum_physical_requests": 60,
            "maximum_input_tokens": 400000,
            "maximum_output_tokens": 100000,
            "maximum_model_cost_usd": 0.0168,
            "currently_authorized": False,
        },
        "qualification_thresholds": {
            "calibration": {
                "valid_responses": 15,
                "rows": 45,
                "maximum_unsafe_direct": 0,
                "minimum_direct_states": 5,
                "minimum_direct_states_per_build_system": 1,
            },
            "evaluation_core": {
                "valid_responses": 15,
                "minimum_direct_states": 5,
                "minimum_direct_states_per_build_system": 1,
                "maximum_wrong_direct_risk": 0.10,
                "minimum_exact_optimal_actions": 10,
                "minimum_joint_correct": 32,
                "minimum_joint_correct_per_build_system": 10,
            },
            "match_tfidf": {
                "minimum_exact_optimal_actions": 12,
                "minimum_joint_correct": 39,
                "maximum_wrong_direct": 0,
            },
            "incremental_over_tfidf": {
                "option_action_exact": 13,
                "option_joint_correct": 40,
                "option_coverage_joint_correct": 39,
                "option_coverage_direct_decisions_exclusive": 18,
            },
        },
        "decision_rule": {
            "action_noul_core_pass": "supports_problem_decomposition_without_action_cards",
            "only_action_card_core_pass": "supports_action_card_context_as_necessary",
            "both_core_fail": "stop_jev_action_safety_before_controller",
            "core_pass_but_tfidf_not_matched": "keep_jev_as_implementation_or_ablation_only",
            "tfidf_matched_without_increment": "no_increment_over_tfidf",
            "tfidf_increment": "supports_jev_action_safety_increment_candidate",
        },
        "stopping_rules": {
            "stop_on_credential_error": True,
            "stop_on_http_401_or_403": True,
            "stop_on_model_version_drift": True,
            "stop_on_response_contract_drift": True,
            "retry_failed_request": False,
            "replace_failed_state": False,
            "backfill_failed_state": False,
            "run_historical_four_way_evaluation": False,
            "adjust_after_evaluation": False,
        },
        "publication_gate": {
            "candidate_must_be_committed_and_pushed_before_credential_read": True,
            "requires_authorized_execution_manifest": True,
            "authorized_identity_must_bind_exact_git_revision": True,
        },
    }


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-jev-action-safety-decomposition-candidate-v1.schema.json",
        "title": "Forge Jev action safety decomposition candidate v1",
        "const": manifest,
    }


def generate_preregistration(manifest: dict[str, Any]) -> str:
    return f"""# Jev 逐动作安全判断问题分解候选预注册

## 身份

- Candidate identity：`{IDENTITY}`
- Planned formal identity：`{FORMAL_IDENTITY}`
- Tracking Issue：[#465]({ISSUE_URL})
- Manifest canonical SHA-256：`{canonical_sha256(manifest)}`

## 冻结设计

父 outcome 与 #463 Jev evidence 保持只读。四选一只作冻结 calibration 历史对照，
不运行其旧 evaluation。新实验比较 `action_noul` 与 `action_card_noul`；每个状态在
一个请求内按正序和逆序各询问三个 Noul，动作原始分数固定为两次真概率的最小值。

每个 condition 在 15 个 calibration 状态的 45 行上独立拟合一维 Platt scaling，
并选择使最低成本动作选择器零 observed unsafe direct、覆盖最大的阈值。该阈值只在
另 3 个项目族的 15 个 evaluation 状态上应用一次，随后复用父六维 BudgetFit。

## 当前权限

当前仅授权生成和验证候选合同、mock SDK、父 evidence 审计及 credential 文件元数据
检查。当前不授权读取 credential 内容、调用 Provider、创建 formal attempt/evidence
或实现 controller。

## 未来预算与停止规则

授权 identity 的硬上限计划为 60 requests、400,000 input tokens、100,000 output
tokens 和 `$0.0168`；固定 `jev-1.13.0`、30 秒 timeout、SDK retry 0。失败请求不
retry，不 replacement，不 backfill。结果后不得修改 prompt、split、calibrator、
threshold、label 或 decision rule。

资格门槛、TF-IDF 对照与解释边界以 spec 和 manifest 的 const 内容为准。候选通过只
允许创建绑定 exact implementation revision 的 authorized manifest，不构成 Jev 效果
证据。
"""


def generate_files() -> dict[str, Any]:
    if DEFAULT_MANIFEST.exists() or DEFAULT_SCHEMA.exists() or PREREGISTRATION.exists():
        raise CandidateError("candidate 文件已存在，禁止覆盖")
    manifest = generate_manifest()
    schema = generate_schema(manifest)
    jsonschema.Draft202012Validator.check_schema(schema)
    write_json(DEFAULT_MANIFEST, manifest)
    write_json(DEFAULT_SCHEMA, schema)
    PREREGISTRATION.parent.mkdir(parents=True, exist_ok=True)
    PREREGISTRATION.write_text(generate_preregistration(manifest), encoding="utf-8")
    return manifest


def load_contract() -> dict[str, Any]:
    manifest = load_json(DEFAULT_MANIFEST)
    expected = generate_manifest()
    if manifest != expected:
        raise CandidateError("candidate manifest 无法确定重建")
    schema = load_json(DEFAULT_SCHEMA)
    if schema != generate_schema(manifest):
        raise CandidateError("candidate const Schema 漂移")
    jsonschema.validate(manifest, schema)
    if PREREGISTRATION.read_text(encoding="utf-8") != generate_preregistration(
        manifest
    ):
        raise CandidateError("candidate preregistration 漂移")
    return manifest


def mock_sdk_roundtrip(condition: str = "action_card_noul") -> dict[str, Any]:
    state_row = split_rows("calibration")[0][0]
    state = provider_state(state_row, condition)
    questions = provider_questions()
    observed: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        observed["method"] = request.method
        observed["url"] = str(request.url)
        observed["authorized"] = (
            request.headers.get("authorization") == "Bearer mock-key"
        )
        observed["body"] = json.loads(request.content)
        answers = {
            question_id: {"type": "noul", "noul": 0.8} for question_id in questions
        }
        return httpx2.Response(
            200,
            headers={"x-typesafe-request-id": "req-action-safety-zero-provider-mock"},
            json={
                "model": parent.MODEL_ID,
                "answers": answers,
                "usage": {"input_tokens": 456, "output_tokens": 24},
            },
        )

    with TypeSafeClient(
        api_key="mock-key",
        model=parent.MODEL_ID,
        retry=RetryPolicy(max_retries=0, timeout=30.0),
        transport=httpx2.MockTransport(handler),
        base_url=parent.API_BASE_URL,
    ) as client:
        response = client.system_one(state=state, questions=questions)
    normalized = normalize_response(response, latency_ms=1.0)
    body = observed["body"]
    if (
        observed["method"] != "POST"
        or observed["url"] != f"{parent.API_BASE_URL}{parent.API_ENDPOINT}"
        or observed["authorized"] is not True
        or body["model"] != parent.MODEL_ID
        or tuple(body["questions"]) != tuple(questions)
        or any(question["type"] != "noul" for question in body["questions"].values())
    ):
        raise CandidateError("TypeSafe SDK Noul 模拟请求合同漂移")
    serialized = json.dumps(body, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        state_row["state_id"],
        state_row["project_family"],
        "remaining_budget",
        "safe_actions",
        "optimal_action",
        "bound_commands",
    ):
        if forbidden in serialized:
            raise CandidateError(f"模拟 Provider payload 泄漏禁止字段: {forbidden}")
    return {
        "provider_calls": 0,
        "credential_content_reads": 0,
        "transport": "httpx2.MockTransport",
        "condition": condition,
        "request_fingerprint": request_fingerprint(state, questions, condition),
        "normalized_response": normalized,
    }


def credential_metadata() -> dict[str, Any]:
    exists = CREDENTIAL_FILE.exists()
    metadata: dict[str, Any] = {
        "credential_env_present": parent.CREDENTIAL_ENV in os.environ,
        "credential_file_present": exists,
        "credential_file_is_symlink": CREDENTIAL_FILE.is_symlink(),
        "credential_file_mode": None,
        "credential_content_reads": 0,
    }
    if exists:
        metadata["credential_file_mode"] = format(
            stat.S_IMODE(CREDENTIAL_FILE.lstat().st_mode), "04o"
        )
    return metadata


def preflight() -> dict[str, Any]:
    manifest = load_contract()
    installed_sdk = version(parent.SDK_DISTRIBUTION)
    installed_sklearn = version(parent.SKLEARN_DISTRIBUTION)
    if installed_sdk != parent.SDK_VERSION:
        raise CandidateError("TypeSafe SDK 版本漂移")
    if not Version("1.7") <= Version(installed_sklearn) < Version("2"):
        raise CandidateError("scikit-learn 版本漂移")
    mocks = {condition: mock_sdk_roundtrip(condition) for condition in CONDITIONS}
    states = [state for split in SPLITS for state in split_rows(split)[0]]
    cards = [action_card(state, action) for state in states for action in LOCAL_ACTIONS]
    return {
        "ready": True,
        "identity": IDENTITY,
        "formal_identity": FORMAL_IDENTITY,
        "issue_url": ISSUE_URL,
        "manifest_canonical_sha256": canonical_sha256(manifest),
        "parent_raw_evidence": parent.audit_parent_raw_evidence(),
        "historical_jev_evidence": audit_historical_evidence(),
        "action_card_count": len(cards),
        "action_card_canonical_sha256": canonical_sha256(cards),
        "sdk_version": installed_sdk,
        "scikit_learn_version": installed_sklearn,
        "model": parent.MODEL_ID,
        "provider_calls": 0,
        "credential_content_reads": 0,
        "credential_metadata": credential_metadata(),
        "model_tokens": 0,
        "formal_attempts_created": 0,
        "formal_provider_evidence_writes": 0,
        "historical_evidence_writes": 0,
        "mock_request_fingerprints": {
            condition: mocks[condition]["request_fingerprint"]
            for condition in CONDITIONS
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("generate", "validate", "mock-check", "preflight"):
        subparsers.add_parser(command)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "generate":
        result = generate_files()
    elif args.command == "validate":
        result = load_contract()
    elif args.command == "mock-check":
        result = {condition: mock_sdk_roundtrip(condition) for condition in CONDITIONS}
    else:
        result = preflight()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
