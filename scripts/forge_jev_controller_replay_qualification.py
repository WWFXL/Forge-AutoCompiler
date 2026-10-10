#!/usr/bin/env python3
"""Issue #403 Jev 控制器零 Provider 回放资格实验。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema

from deerflow.compile.jev_controller import (
    ACTION_FAMILIES,
    CalibrationContract,
    CandidateAction,
    DecisionState,
    TypedDecision,
    VerifierCapabilities,
    dispatch_route,
    route_next_action,
)

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
IDENTITY = "cpp-jev-controller-replay-qualification-v1"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/403"
BRANCH = "yiwei/403-jev-controller-replay"
SCHEMA_VERSION = "forge-jev-controller-replay-qualification-1.0.0"
REPORT_SCHEMA_VERSION = "forge-jev-controller-replay-report-1.0.0"

CONTROLLER_PATH = REPO_ROOT / "backend/packages/harness/deerflow/compile/jev_controller.py"
CONTROLLER_TEST_PATH = REPO_ROOT / "backend/tests/test_jev_controller.py"
RUNNER_TEST_PATH = REPO_ROOT / "backend/tests/test_forge_jev_controller_replay_qualification.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-jev-controller-replay-qualification-v1.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-jev-controller-replay-qualification-v1.schema.json"
PREREGISTRATION_PATH = REPO_ROOT / "benchmarks/preregistrations/cpp-jev-controller-replay-qualification-v1.md"
JSON_REPORT_PATH = REPO_ROOT / "benchmarks/reports/cpp-jev-controller-replay-qualification-v1.json"
MARKDOWN_REPORT_PATH = REPO_ROOT / "benchmarks/reports/cpp-jev-controller-replay-qualification-v1.md"
EVIDENCE_ROOT = REPO_ROOT / ".compile-sessions/benchmark-evidence-jev-controller-replay-qualification-v1"

V2_REPORT = REPO_ROOT / "benchmarks/reports/cpp-typed-semantic-routing-pilot-v2.json"
V2_REPORT_SHA256 = "ea2e126e81cfca374900436fa670015b28b3cc3f9d8c83e746ae2c92d2badfed"
V6_REPORT = REPO_ROOT / "benchmarks/reports/cpp-jev-offline-qualification-v6.json"
V6_REPORT_SHA256 = "7a9d440acd0dc1b51eea7470563fc263b518fffd428b2e4bd6c3967ab696b2c6"
V6_EVIDENCE_ROOT = REPO_ROOT / ".compile-sessions/benchmark-evidence-jev-offline-qualification-v6"
V6_EVIDENCE_INVENTORY_SHA256 = "296a365e9ebb7b0148fb9662d2aa2edf3cc5c2dfcf0da943f3a521e751877521"
V6_CALIBRATION = V6_EVIDENCE_ROOT / "calibration.json"
V6_CALIBRATION_SHA256 = "1c2d4a24eeb407821ad4e56f41b62e50bef247c71764398044d51d3a24c835cf"
V6_EVALUATION_ANALYSIS = V6_EVIDENCE_ROOT / "provider/evaluation/analysis.json"
V6_EVALUATION_ANALYSIS_SHA256 = "311f3f977677cb9d77a4d74b6fba4b5cf3de79c37b7e332178e35f4d13b2f33c"
V6_EVALUATION_ROOT = V6_EVIDENCE_ROOT / "provider/evaluation"

EXPECTED_MODEL = "jev-1.13.0"
EXPECTED_COEFFICIENT = 0.08805149266059632
EXPECTED_INTERCEPT = 0.618335523488825
EXPECTED_THRESHOLD = 0.6747568477098429
EXPECTED_EVALUATION_STATES = 18

FAULT_SCENARIOS = (
    "response_missing",
    "model_mismatch",
    "state_mismatch",
    "request_fingerprint_mismatch",
    "choice_order_disagreement",
    "probability_non_finite",
    "probability_sum_invalid",
    "choice_probability_mismatch",
    "below_calibrated_threshold",
    "selected_candidate_missing",
    "selected_candidate_precondition_failed",
    "budget_exhausted",
    "candidate_verifier_missing",
    "functional_oracle_missing",
    "provenance_missing",
    "clean_replay_missing",
    "model_requested_escalation",
    "unknown_action_choice",
)

EXPECTED_FAULT_REASON = {
    "response_missing": "response_missing",
    "model_mismatch": "model_mismatch",
    "state_mismatch": "state_mismatch",
    "request_fingerprint_mismatch": "request_fingerprint_mismatch",
    "choice_order_disagreement": "choice_order_disagreement",
    "probability_non_finite": "probability_contract_invalid",
    "probability_sum_invalid": "probability_contract_invalid",
    "choice_probability_mismatch": "choice_probability_mismatch",
    "below_calibrated_threshold": "below_calibrated_threshold",
    "selected_candidate_missing": "selected_candidate_missing_or_ambiguous",
    "selected_candidate_precondition_failed": "selected_candidate_precondition_failed",
    "budget_exhausted": "budget_exhausted",
    "candidate_verifier_missing": "strict_verifier_capability_missing",
    "functional_oracle_missing": "strict_verifier_capability_missing",
    "provenance_missing": "strict_verifier_capability_missing",
    "clean_replay_missing": "strict_verifier_capability_missing",
    "model_requested_escalation": "model_requested_escalation",
    "unknown_action_choice": "unknown_action_choice",
}


class ReplayError(RuntimeError):
    """身份、冻结输入或控制器回放违反协议。"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReplayError(f"JSON 根必须为对象: {path}")
    return value


def _write_once(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(content)
        path.chmod(0o600)
    except FileExistsError as exc:
        raise ReplayError(f"create-once 路径已存在: {path}") from exc


def _write_once_json(path: Path, value: Any) -> None:
    _write_once(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n")


def _git(*argv: str) -> str:
    result = subprocess.run(
        ["git", *argv],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise ReplayError(result.stderr.strip() or f"git {' '.join(argv)} 失败")
    return result.stdout.strip()


def _canonical_revision(revision: str) -> str:
    value = _git("rev-parse", "--verify", f"{revision}^{{commit}}")
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ReplayError("implementation revision 必须是完整 commit SHA")
    return value


def _git_blob(revision: str, relative_path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative_path}"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise ReplayError(f"无法读取 implementation revision 中的 {relative_path}")
    return result.stdout


def _component(revision: str, path: Path) -> dict[str, str]:
    relative = path.relative_to(REPO_ROOT).as_posix()
    return {
        "path": relative,
        "sha256": hashlib.sha256(_git_blob(revision, relative)).hexdigest(),
    }


def build_manifest(implementation_revision: str) -> dict[str, Any]:
    revision = _canonical_revision(implementation_revision)
    return {
        "$schema": "../schemas/forge-jev-controller-replay-qualification-v1.schema.json",
        "schema_version": SCHEMA_VERSION,
        "identity": IDENTITY,
        "issue_url": ISSUE_URL,
        "branch": BRANCH,
        "implementation_revision": revision,
        "components": {
            "controller": _component(revision, CONTROLLER_PATH),
            "controller_test": _component(revision, CONTROLLER_TEST_PATH),
            "runner": _component(revision, SCRIPT_PATH),
            "runner_test": _component(revision, RUNNER_TEST_PATH),
        },
        "frozen_inputs": {
            "v2_report": {
                "path": V2_REPORT.relative_to(REPO_ROOT).as_posix(),
                "sha256": V2_REPORT_SHA256,
            },
            "v6_report": {
                "path": V6_REPORT.relative_to(REPO_ROOT).as_posix(),
                "sha256": V6_REPORT_SHA256,
            },
            "v6_evidence_root": V6_EVIDENCE_ROOT.relative_to(REPO_ROOT).as_posix(),
            "v6_evidence_inventory_canonical_sha256": V6_EVIDENCE_INVENTORY_SHA256,
            "calibration_sha256": V6_CALIBRATION_SHA256,
            "evaluation_analysis_sha256": V6_EVALUATION_ANALYSIS_SHA256,
        },
        "controller_contract": {
            "action_families": list(ACTION_FAMILIES),
            "model": EXPECTED_MODEL,
            "calibration": {
                "coefficient": EXPECTED_COEFFICIENT,
                "intercept": EXPECTED_INTERCEPT,
                "threshold": EXPECTED_THRESHOLD,
            },
            "required_verifiers": ["candidate_verifier", "functional_oracle", "provenance", "clean_replay"],
            "direct_action_terminal_status": "awaiting_strict_verification",
            "model_generated_commands_allowed": False,
        },
        "schedule": {
            "normal_state_count": EXPECTED_EVALUATION_STATES,
            "fault_scenarios": list(FAULT_SCENARIOS),
            "fault_injection_per_state": True,
            "expected_fault_case_count": EXPECTED_EVALUATION_STATES * len(FAULT_SCENARIOS),
        },
        "authorization": {
            "credential_reads": 0,
            "provider_calls": 0,
            "model_tokens": 0,
            "model_cost_usd": 0,
            "formal_replay": True,
            "formal_evidence_write": True,
            "historical_evidence_write": False,
            "shell_action_execution": False,
        },
        "stopping_rule": {
            "stop_on_first_wrong_direct_action": True,
            "stop_on_parent_input_drift": True,
            "pass_decision": "proceed_to_end_to_end_canary",
            "fail_decision": "stop_before_end_to_end_canary",
        },
        "interpretation": {
            "controller_path_qualification": True,
            "controller_treatment_effect": False,
            "strict_success_noninferiority": False,
            "cost_savings": False,
            "natural_failure_generalization": False,
        },
    }


def build_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-jev-controller-replay-qualification-v1.schema.json",
        "title": "Forge Jev controller replay qualification v1",
        "const": manifest,
    }


def render_preregistration(manifest: dict[str, Any]) -> str:
    return f"""# Jev 控制器零 Provider 回放资格实验 v1

- Tracking Issue：[#403]({ISSUE_URL})
- Identity：`{IDENTITY}`
- Implementation revision：`{manifest["implementation_revision"]}`
- Manifest canonical SHA-256：`{canonical_sha256(manifest)}`

## 研究问题

固定 v6 响应进入最小控制器后，能否在 18 个 evaluation 状态上复现动作和校准门禁，并在输入、模型、候选、预算、前置条件或严格验证能力异常时全部升级 `escalate_agent`？

## 冻结输入

- v2 report SHA-256：`{V2_REPORT_SHA256}`
- v6 report SHA-256：`{V6_REPORT_SHA256}`
- v6 evidence inventory canonical SHA-256：`{V6_EVIDENCE_INVENTORY_SHA256}`
- calibration SHA-256：`{V6_CALIBRATION_SHA256}`
- evaluation analysis SHA-256：`{V6_EVALUATION_ANALYSIS_SHA256}`
- 模型：`{EXPECTED_MODEL}`
- 校准阈值：`{EXPECTED_THRESHOLD}`

## 回放与故障注入

正常路径按 state ID 重建 state、代码绑定候选、原始 Jev 决策和校准概率。
每个状态执行 {len(FAULT_SCENARIOS)} 个预先冻结的故障场景，共 {EXPECTED_EVALUATION_STATES * len(FAULT_SCENARIOS)} 个故障回放。
回放 executor 只记录被调度的代码绑定候选，不执行 Shell。

## 通过条件

- 18/18 正常路径与 v6 的动作、校准概率和 direct decision 一致；
- 18/18 调度回执均为 `awaiting_strict_verification`，不存在路由器终态成功；
- {EXPECTED_EVALUATION_STATES * len(FAULT_SCENARIOS)}/{EXPECTED_EVALUATION_STATES * len(FAULT_SCENARIOS)} 故障回放升级 Agent，
  错误直接动作和故障 executor 调用均为 0；
- CMake、Make、Autotools 各覆盖 6 个正常状态；
- v6 evidence inventory 前后哈希不变；
- credential、Provider、模型 token、费用和 Shell 动作执行均为 0。

任一输入漂移、错误直接执行、故障路径 executor 调用、验证链绕过或计数不完整均立即停止并决定 `stop_before_end_to_end_canary`。全部通过才决定 `proceed_to_end_to_end_canary`。

## 解释边界

本实验只评价冻结响应进入控制器后的确定性路由和 fail-closed 边界。它不执行真实构建动作，不估计端到端成功率、Agent 调用、token、费用、墙钟时间或 treatment effect。
"""


def bind_identity(implementation_revision: str) -> dict[str, Any]:
    manifest = build_manifest(implementation_revision)
    _write_once_json(MANIFEST_PATH, manifest)
    _write_once_json(SCHEMA_PATH, build_schema(manifest))
    _write_once(PREREGISTRATION_PATH, render_preregistration(manifest))
    return manifest


def validate_manifest() -> dict[str, Any]:
    manifest = load_json(MANIFEST_PATH)
    expected = build_manifest(manifest.get("implementation_revision", ""))
    if manifest != expected:
        raise ReplayError("manifest 与冻结生成结果不一致")
    schema = load_json(SCHEMA_PATH)
    if schema != build_schema(expected):
        raise ReplayError("const schema 漂移")
    jsonschema.validate(manifest, schema)
    if PREREGISTRATION_PATH.read_text(encoding="utf-8") != render_preregistration(expected):
        raise ReplayError("预注册文本漂移")
    return manifest


def _inventory(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "size": path.stat().st_size,
            "sha256": file_sha256(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def validate_parent_inputs() -> dict[str, Any]:
    if file_sha256(V2_REPORT) != V2_REPORT_SHA256 or file_sha256(V6_REPORT) != V6_REPORT_SHA256:
        raise ReplayError("父报告文件漂移")
    if file_sha256(V6_CALIBRATION) != V6_CALIBRATION_SHA256 or file_sha256(V6_EVALUATION_ANALYSIS) != V6_EVALUATION_ANALYSIS_SHA256:
        raise ReplayError("v6 calibration/evaluation 文件漂移")

    v2 = load_json(V2_REPORT)
    v6 = load_json(V6_REPORT)
    if v2.get("identity") != "cpp-typed-semantic-routing-pilot-v2" or v2.get("status") != "completed" or v2.get("analysis", {}).get("decision") != "proceed_to_jev_offline_qualification" or v2.get("analysis", {}).get("passed") is not True:
        raise ReplayError("v2 输入未通过资格")
    if v6.get("identity") != "cpp-jev-offline-qualification-v6" or v6.get("decision") != "proceed_to_controller_replay_qualification" or v6.get("passed") is not True:
        raise ReplayError("v6 输入未通过资格")

    inventory = _inventory(V6_EVIDENCE_ROOT)
    if inventory != v6.get("evidence_inventory") or canonical_sha256(inventory) != V6_EVIDENCE_INVENTORY_SHA256:
        raise ReplayError("v6 evidence inventory 漂移")
    calibration = load_json(V6_CALIBRATION)
    model = calibration.get("model", {})
    threshold = calibration.get("threshold", {}).get("threshold")
    if calibration.get("passed") is not True or model.get("coefficient") != EXPECTED_COEFFICIENT or model.get("intercept") != EXPECTED_INTERCEPT or threshold != EXPECTED_THRESHOLD:
        raise ReplayError("v6 calibration 合同漂移")

    counts: dict[str, int] = {}
    for directory in ("attempts", "observations", "requests"):
        paths = sorted((V6_EVALUATION_ROOT / directory).glob("*.json"))
        counts[directory] = len(paths)
        if len(paths) != EXPECTED_EVALUATION_STATES:
            raise ReplayError(f"evaluation {directory} 文件数不等于 18")
    return {
        "v2": v2,
        "v6": v6,
        "calibration": calibration,
        "evidence_inventory": inventory,
        "evidence_inventory_canonical_sha256": canonical_sha256(inventory),
        "evaluation_file_counts": counts,
    }


def preflight(*, require_clean: bool = True, require_absent_evidence: bool = True) -> dict[str, Any]:
    manifest = validate_manifest()
    parent = validate_parent_inputs()
    if _git("branch", "--show-current") != BRANCH:
        raise ReplayError("当前分支与身份不一致")
    if require_clean and _git("status", "--porcelain"):
        raise ReplayError("正式回放要求干净工作树")
    head = _git("rev-parse", "HEAD")
    implementation_revision = manifest["implementation_revision"]
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", implementation_revision, head],
        cwd=REPO_ROOT,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        raise ReplayError("HEAD 不是 implementation revision 的后代")
    for component in manifest["components"].values():
        current = REPO_ROOT / component["path"]
        if file_sha256(current) != component["sha256"]:
            raise ReplayError(f"实现组件漂移: {component['path']}")
    remote_contains = _git("branch", "-r", "--contains", head).splitlines()
    if f"origin/{BRANCH}" not in {row.strip() for row in remote_contains}:
        raise ReplayError("正式回放提交尚未推送")
    if require_absent_evidence and EVIDENCE_ROOT.exists():
        raise ReplayError("正式 evidence root 已存在")
    if JSON_REPORT_PATH.exists() or MARKDOWN_REPORT_PATH.exists():
        raise ReplayError("正式报告路径必须在回放前不存在")
    return {
        "ready": True,
        "head": head,
        "manifest_canonical_sha256": canonical_sha256(manifest),
        "parent_inventory_canonical_sha256": parent["evidence_inventory_canonical_sha256"],
        "credential_reads": 0,
        "provider_calls": 0,
    }


def _load_evaluation_records(parent: dict[str, Any]) -> list[dict[str, Any]]:
    states = {row["state_id"]: row for row in parent["v2"]["states"]}
    report_rows = {row["state_id"]: row for row in parent["v6"]["calibrated_gate"]["rows"]}
    analysis_rows = {row["state_id"]: row for row in load_json(V6_EVALUATION_ANALYSIS)["rows"]}
    records: list[dict[str, Any]] = []
    for request_path in sorted((V6_EVALUATION_ROOT / "requests").glob("*.json")):
        request = load_json(request_path)
        state_id = request["state_id"]
        attempt_paths = list((V6_EVALUATION_ROOT / "attempts").glob(f"*-{state_id}.json"))
        observation_paths = list((V6_EVALUATION_ROOT / "observations").glob(f"*-{state_id}.json"))
        if len(attempt_paths) != 1 or len(observation_paths) != 1 or state_id not in states or state_id not in report_rows or state_id not in analysis_rows:
            raise ReplayError(f"evaluation 状态输入不完整: {state_id}")
        attempt = load_json(attempt_paths[0])
        observation = load_json(observation_paths[0])
        fingerprint = request["request_fingerprint"]
        if (
            request.get("identity") != "cpp-jev-offline-qualification-v6"
            or request.get("split") != "evaluation"
            or attempt.get("request_fingerprint") != fingerprint
            or observation.get("request_fingerprint") != fingerprint
            or attempt.get("state_id") != state_id
            or observation.get("state_id") != state_id
        ):
            raise ReplayError(f"evaluation 请求身份漂移: {state_id}")
        records.append(
            {
                "state": states[state_id],
                "request": request,
                "attempt": attempt,
                "observation": observation,
                "report_row": report_rows[state_id],
                "analysis_row": analysis_rows[state_id],
            }
        )
    if len(records) != EXPECTED_EVALUATION_STATES:
        raise ReplayError("evaluation 状态数不等于 18")
    return records


def _controller_inputs(record: dict[str, Any], calibration_data: dict[str, Any]) -> tuple[DecisionState, tuple[CandidateAction, ...], TypedDecision, CalibrationContract, VerifierCapabilities]:
    source = record["state"]
    model_input = source["model_input"]
    state = DecisionState(
        state_id=source["state_id"],
        build_system=source["build_system"],
        phase_facts=dict(source["phase_facts"]),
        remaining_actions=int(model_input["remaining_budget"]["actions"]),
        remaining_wall_clock_seconds=int(model_input["remaining_budget"]["wall_clock_seconds"]),
        expected_request_fingerprint=record["attempt"]["request_fingerprint"],
    )
    candidates = tuple(
        CandidateAction(
            action_id=row["action_id"],
            action_family=row["action_family"],
            bound_commands=tuple(row["bound_commands"]),
            direct_execution=bool(row["direct_execution"]),
            preconditions_satisfied=bool(row["preconditions_checked_by_runner"]),
        )
        for row in source["candidate_actions"]
    )
    response = record["request"]["response"]
    primary = response["answers"]["next_action_primary"]
    reverse = response["answers"]["next_action_order_sensitivity"]
    decision = TypedDecision(
        state_id=source["state_id"],
        model=response["model"],
        request_fingerprint=record["request"]["request_fingerprint"],
        primary_choice=primary["choice"],
        reverse_choice=reverse["choice"],
        probabilities=dict(primary["probabilities"]),
        reverse_probabilities=dict(reverse["probabilities"]),
    )
    calibration = CalibrationContract(
        model=EXPECTED_MODEL,
        coefficient=float(calibration_data["model"]["coefficient"]),
        intercept=float(calibration_data["model"]["intercept"]),
        threshold=float(calibration_data["threshold"]["threshold"]),
    )
    return state, candidates, decision, calibration, VerifierCapabilities(True, True, True, True)


def _fault_case(
    scenario: str,
    state: DecisionState,
    candidates: tuple[CandidateAction, ...],
    decision: TypedDecision,
    capabilities: VerifierCapabilities,
) -> tuple[DecisionState, tuple[CandidateAction, ...], TypedDecision | None, VerifierCapabilities]:
    if scenario == "response_missing":
        return state, candidates, None, capabilities
    if scenario == "model_mismatch":
        return state, candidates, replace(decision, model="jev-preview"), capabilities
    if scenario == "state_mismatch":
        return state, candidates, replace(decision, state_id="s-mismatch"), capabilities
    if scenario == "request_fingerprint_mismatch":
        return state, candidates, replace(decision, request_fingerprint="0" * 64), capabilities
    if scenario == "choice_order_disagreement":
        alternate = next(action for action in ACTION_FAMILIES if action != decision.primary_choice)
        return state, candidates, replace(decision, reverse_choice=alternate), capabilities
    if scenario == "probability_non_finite":
        probabilities = dict(decision.probabilities)
        probabilities[decision.primary_choice] = float("nan")
        return state, candidates, replace(decision, probabilities=probabilities), capabilities
    if scenario == "probability_sum_invalid":
        probabilities = {action: 0.1 for action in ACTION_FAMILIES}
        probabilities[decision.primary_choice] = 0.5
        return state, candidates, replace(decision, probabilities=probabilities, reverse_probabilities=probabilities), capabilities
    if scenario == "choice_probability_mismatch":
        alternate = next(action for action in ACTION_FAMILIES if action != decision.primary_choice)
        probabilities = {action: 0.1 for action in ACTION_FAMILIES}
        probabilities[decision.primary_choice] = 0.2
        probabilities[alternate] = 0.5
        return state, candidates, replace(decision, probabilities=probabilities, reverse_probabilities=probabilities), capabilities
    if scenario == "below_calibrated_threshold":
        probabilities = {action: 0.2 for action in ACTION_FAMILIES}
        probabilities[decision.primary_choice] = 0.4
        return state, candidates, replace(decision, probabilities=probabilities, reverse_probabilities=probabilities), capabilities
    if scenario == "selected_candidate_missing":
        return state, tuple(row for row in candidates if row.action_family != decision.primary_choice), decision, capabilities
    if scenario == "selected_candidate_precondition_failed":
        changed = tuple(replace(row, preconditions_satisfied=False) if row.action_family == decision.primary_choice else row for row in candidates)
        return state, changed, decision, capabilities
    if scenario == "budget_exhausted":
        return replace(state, remaining_actions=0), candidates, decision, capabilities
    if scenario == "candidate_verifier_missing":
        return state, candidates, decision, replace(capabilities, candidate_verifier=False)
    if scenario == "functional_oracle_missing":
        return state, candidates, decision, replace(capabilities, functional_oracle=False)
    if scenario == "provenance_missing":
        return state, candidates, decision, replace(capabilities, provenance=False)
    if scenario == "clean_replay_missing":
        return state, candidates, decision, replace(capabilities, clean_replay=False)
    if scenario == "model_requested_escalation":
        probabilities = {action: 0.0 for action in ACTION_FAMILIES}
        probabilities["escalate_agent"] = 1.0
        changed = replace(
            decision,
            primary_choice="escalate_agent",
            reverse_choice="escalate_agent",
            probabilities=probabilities,
            reverse_probabilities=probabilities,
        )
        return state, candidates, changed, capabilities
    if scenario == "unknown_action_choice":
        return state, candidates, replace(decision, primary_choice="diagnostic", reverse_choice="diagnostic"), capabilities
    raise ReplayError(f"未知故障场景: {scenario}")


def compute_replay(parent: dict[str, Any]) -> dict[str, Any]:
    records = _load_evaluation_records(parent)
    normal_rows: list[dict[str, Any]] = []
    fault_rows: list[dict[str, Any]] = []
    dispatched: list[dict[str, Any]] = []
    build_system_counts: dict[str, int] = {}

    for record in records:
        state, candidates, decision, calibration, capabilities = _controller_inputs(record, parent["calibration"])
        route = route_next_action(
            state=state,
            candidates=candidates,
            decision=decision,
            calibration=calibration,
            verifier_capabilities=capabilities,
        )
        expected = record["report_row"]
        matched = (
            route.disposition == "direct_execute"
            and route.selected_action_family == expected["choice"]
            and expected["direct_execute"] is True
            and route.calibrated_safe_probability is not None
            and math.isclose(route.calibrated_safe_probability, expected["calibrated_safe_probability"], rel_tol=0.0, abs_tol=1e-12)
        )
        if not matched:
            raise ReplayError(f"正常路径未复现 v6 route: {state.state_id}")

        def record_dispatch(action: CandidateAction) -> None:
            dispatched.append(
                {
                    "state_id": state.state_id,
                    "action_id": action.action_id,
                    "action_family": action.action_family,
                    "bound_commands_sha256": canonical_sha256(list(action.bound_commands)),
                }
            )

        receipt = dispatch_route(route=route, candidates=candidates, executor=record_dispatch)
        if receipt.disposition != "awaiting_strict_verification" or receipt.terminal_success:
            raise ReplayError(f"正常路径绕过严格验证链: {state.state_id}")
        build_system_counts[state.build_system] = build_system_counts.get(state.build_system, 0) + 1
        normal_rows.append(
            {
                "state_id": state.state_id,
                "build_system": state.build_system,
                "selected_action": route.selected_action_family,
                "calibrated_safe_probability": route.calibrated_safe_probability,
                "dispatch_status": receipt.disposition,
                "terminal_success": receipt.terminal_success,
                "matches_v6": matched,
            }
        )

        for scenario in FAULT_SCENARIOS:
            fault_state, fault_candidates, fault_decision, fault_capabilities = _fault_case(scenario, state, candidates, decision, capabilities)
            fault_route = route_next_action(
                state=fault_state,
                candidates=fault_candidates,
                decision=fault_decision,
                calibration=calibration,
                verifier_capabilities=fault_capabilities,
            )
            fault_executor_calls = 0

            def reject_executor(_: CandidateAction) -> None:
                nonlocal fault_executor_calls
                fault_executor_calls += 1

            fault_receipt = dispatch_route(route=fault_route, candidates=fault_candidates, executor=reject_executor)
            expected_reason = EXPECTED_FAULT_REASON[scenario]
            if fault_route.disposition != "escalate_agent" or fault_route.reasons != (expected_reason,) or fault_receipt.disposition != "escalate_agent" or fault_executor_calls != 0:
                raise ReplayError(f"故障路径未 fail closed: {state.state_id}/{scenario}")
            fault_rows.append(
                {
                    "state_id": state.state_id,
                    "scenario": scenario,
                    "route": fault_route.disposition,
                    "reason": expected_reason,
                    "executor_calls": fault_executor_calls,
                    "terminal_success": fault_route.terminal_success,
                }
            )

    expected_fault_count = EXPECTED_EVALUATION_STATES * len(FAULT_SCENARIOS)
    gates = {
        "normal_routes_match_v6": len(normal_rows) == EXPECTED_EVALUATION_STATES and all(row["matches_v6"] for row in normal_rows),
        "normal_dispatch_waits_for_strict_verification": len(dispatched) == EXPECTED_EVALUATION_STATES and all(not row["terminal_success"] and row["dispatch_status"] == "awaiting_strict_verification" for row in normal_rows),
        "all_build_systems_covered": build_system_counts == {"autotools": 6, "cmake": 6, "make": 6},
        "all_faults_escalate": len(fault_rows) == expected_fault_count and all(row["route"] == "escalate_agent" for row in fault_rows),
        "zero_fault_executor_calls": sum(row["executor_calls"] for row in fault_rows) == 0,
        "zero_router_terminal_success": all(not row["terminal_success"] for row in normal_rows + fault_rows),
        "zero_provider": True,
        "zero_credential_read": True,
        "zero_shell_action_execution": True,
    }
    return {
        "identity": IDENTITY,
        "created_at": _now(),
        "normal_rows": normal_rows,
        "fault_rows": fault_rows,
        "dispatch_records": dispatched,
        "build_system_counts": build_system_counts,
        "normal_state_count": len(normal_rows),
        "fault_case_count": len(fault_rows),
        "fault_scenario_count": len(FAULT_SCENARIOS),
        "provider_calls": 0,
        "credential_reads": 0,
        "model_tokens": 0,
        "model_cost_usd": 0,
        "shell_action_executions": 0,
        "gates": gates,
        "passed": all(gates.values()),
        "decision": "proceed_to_end_to_end_canary" if all(gates.values()) else "stop_before_end_to_end_canary",
    }


def run_formal_replay() -> dict[str, Any]:
    gate = preflight(require_clean=True, require_absent_evidence=True)
    manifest = validate_manifest()
    parent_before = validate_parent_inputs()
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=False)
    EVIDENCE_ROOT.chmod(0o700)
    _write_once_json(
        EVIDENCE_ROOT / "identity.json",
        {
            "identity": IDENTITY,
            "created_at": _now(),
            "git_commit": gate["head"],
            "manifest_canonical_sha256": canonical_sha256(manifest),
            "implementation_revision": manifest["implementation_revision"],
            "parent_inventory_canonical_sha256": parent_before["evidence_inventory_canonical_sha256"],
            "authorization": manifest["authorization"],
        },
    )
    try:
        replay = compute_replay(parent_before)
        parent_after = validate_parent_inputs()
        replay["parent_inventory_before"] = parent_before["evidence_inventory_canonical_sha256"]
        replay["parent_inventory_after"] = parent_after["evidence_inventory_canonical_sha256"]
        replay["gates"]["historical_evidence_unchanged"] = replay["parent_inventory_before"] == replay["parent_inventory_after"] == V6_EVIDENCE_INVENTORY_SHA256
        replay["passed"] = all(replay["gates"].values())
        replay["decision"] = "proceed_to_end_to_end_canary" if replay["passed"] else "stop_before_end_to_end_canary"
        _write_once_json(EVIDENCE_ROOT / "replay.json", replay)
        _write_once_json(
            EVIDENCE_ROOT / "completed.json",
            {
                "identity": IDENTITY,
                "created_at": _now(),
                "status": "completed" if replay["passed"] else "failed",
                "decision": replay["decision"],
                "provider_calls": 0,
                "credential_reads": 0,
                "model_tokens": 0,
                "model_cost_usd": 0,
                "shell_action_executions": 0,
            },
        )
        return replay
    except Exception as exc:
        _write_once_json(
            EVIDENCE_ROOT / "failed.json",
            {
                "identity": IDENTITY,
                "created_at": _now(),
                "status": "failed",
                "decision": "stop_before_end_to_end_canary",
                "failure_type": type(exc).__name__,
                "failure_message": str(exc),
                "provider_calls": 0,
                "credential_reads": 0,
                "model_tokens": 0,
                "model_cost_usd": 0,
                "shell_action_executions": 0,
            },
        )
        raise


def build_report() -> dict[str, Any]:
    if JSON_REPORT_PATH.exists() or MARKDOWN_REPORT_PATH.exists():
        raise ReplayError("正式报告已存在，禁止覆盖")
    manifest = validate_manifest()
    replay = load_json(EVIDENCE_ROOT / "replay.json")
    completed = load_json(EVIDENCE_ROOT / "completed.json")
    inventory = _inventory(EVIDENCE_ROOT)
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "document_type": "forge_jev_controller_replay_qualification_report",
        "identity": IDENTITY,
        "issue_url": ISSUE_URL,
        "created_at": _now(),
        "git_commit": _git("rev-parse", "HEAD"),
        "manifest_canonical_sha256": canonical_sha256(manifest),
        "implementation_revision": manifest["implementation_revision"],
        "parent_inputs": manifest["frozen_inputs"],
        "normal_state_count": replay["normal_state_count"],
        "normal_direct_route_count": sum(row["matches_v6"] for row in replay["normal_rows"]),
        "normal_dispatch_waiting_verification_count": sum(row["dispatch_status"] == "awaiting_strict_verification" for row in replay["normal_rows"]),
        "build_system_counts": replay["build_system_counts"],
        "fault_scenario_count": replay["fault_scenario_count"],
        "fault_case_count": replay["fault_case_count"],
        "fault_escalation_count": sum(row["route"] == "escalate_agent" for row in replay["fault_rows"]),
        "wrong_direct_action_count": sum(row["route"] != "escalate_agent" for row in replay["fault_rows"]),
        "fault_executor_call_count": sum(row["executor_calls"] for row in replay["fault_rows"]),
        "provider_calls": replay["provider_calls"],
        "credential_reads": replay["credential_reads"],
        "model_tokens": replay["model_tokens"],
        "model_cost_usd": replay["model_cost_usd"],
        "shell_action_executions": replay["shell_action_executions"],
        "historical_evidence_unchanged": replay["parent_inventory_before"] == replay["parent_inventory_after"],
        "gates": replay["gates"],
        "passed": replay["passed"] and completed["status"] == "completed",
        "decision": replay["decision"],
        "evidence_inventory": inventory,
        "evidence_inventory_canonical_sha256": canonical_sha256(inventory),
        "interpretation": manifest["interpretation"],
    }
    _write_once_json(JSON_REPORT_PATH, report)
    _write_once(MARKDOWN_REPORT_PATH, render_report(report))
    return report


def render_report(report: dict[str, Any]) -> str:
    return f"""# Jev 控制器零 Provider 回放资格实验 v1 结果

- Identity：`{IDENTITY}`
- 决定：`{report["decision"]}`
- 正常路径复现：`{report["normal_direct_route_count"]}/{report["normal_state_count"]}`
- 等待严格验证的调度：`{report["normal_dispatch_waiting_verification_count"]}/{report["normal_state_count"]}`
- 故障回放升级：`{report["fault_escalation_count"]}/{report["fault_case_count"]}`
- 错误直接执行：`{report["wrong_direct_action_count"]}`
- 故障 executor 调用：`{report["fault_executor_call_count"]}`
- Provider / credential / model token / cost：`0 / 0 / 0 / $0`
- Shell 动作执行：`0`

## 结论

冻结 v6 响应通过最小控制器的确定性回放与 fail-closed 资格门槛。直接动作只能调度代码绑定候选，并停在 `awaiting_strict_verification`；输入、模型、概率、校准、候选、预算、前置条件或严格验证能力异常时均升级完整 Agent。

该结果允许进入独立的端到端 canary 设计。它不证明 JevGate 已降低成本、减少 Agent 调用或保持严格成功率非劣。

## 门槛

```json
{json.dumps(report["gates"], ensure_ascii=False, indent=2, sort_keys=True)}
```

## 解释边界

本实验使用冻结响应和零副作用记录 executor，没有执行真实 Shell 构建动作。它只证明控制路径、校准门禁、升级路径和严格验证边界在当前 18 个状态及冻结故障注入上可执行。
"""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    bind = subparsers.add_parser("bind-identity")
    bind.add_argument("--implementation-revision", required=True)
    for command in ("validate", "preflight", "run", "report"):
        subparsers.add_parser(command)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "bind-identity":
        print(canonical_sha256(bind_identity(args.implementation_revision)))
        return 0
    if args.command == "validate":
        print(canonical_sha256(validate_manifest()))
        return 0
    if args.command == "preflight":
        print(json.dumps(preflight(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "run":
        print(json.dumps(run_formal_replay(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
