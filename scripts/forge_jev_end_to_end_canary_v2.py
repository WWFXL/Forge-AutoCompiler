#!/usr/bin/env python3
"""Issue #406 Jev 三臂端到端 canary v2。"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"
for import_root in (str(SCRIPT_PATH.parent), str(BACKEND_ROOT / "packages/harness")):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_agent_workflow_stage_b_phase5_v2_authorized_runner as agent_runner  # noqa: E402
import forge_jev_offline_qualification_candidate as jev_candidate  # noqa: E402
import forge_jev_offline_qualification_v6 as jev_v6  # noqa: E402
import forge_typed_action_benchmark_qualification as typed_v1  # noqa: E402
import forge_typed_semantic_routing_pilot_v2 as semantic_v2  # noqa: E402
from deerflow.compile.agent_workflow_node import (  # noqa: E402
    AgentWorkflowBudgetTracker,
    AgentWorkflowCandidateStore,
    AgentWorkflowNodeStatus,
    AgentWorkflowStateMachine,
)
from deerflow.compile.agent_workflow_runtime import (  # noqa: E402
    AgentWorkflowCandidateService,
    AgentWorkflowEvidenceLedger,
    run_agent_workflow_node_v1,
)
from deerflow.compile.agent_workflow_schemas import (  # noqa: E402
    AgentBuildNodeInput,
    AgentBuildNodeResult,
    AgentWorkflowBudget,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowTargetContract,
    AgentWorkflowUsage,
    SubmitCandidateRequest,
)
from deerflow.compile.evidence import (  # noqa: E402
    ExperimentLedger,
    ExperimentPolicy,
    activate_experiment,
    deactivate_experiment,
    new_evidence_id,
)
from deerflow.compile.external_evaluator_v2 import (  # noqa: E402
    ForgeCompileEvaluationBackend,
    FunctionalOracleSpec,
    run_external_evaluator_v2,
)
from deerflow.compile.jev_controller import (  # noqa: E402
    CalibrationContract,
    CandidateAction,
    DecisionState,
    TypedDecision,
    VerifierCapabilities,
    dispatch_route,
    route_next_action,
)
from deerflow.compile.operations import (  # noqa: E402
    cleanup_and_finalize_compile_session_impl,
    clone_repository_impl,
    get_compile_services,
    inspect_build_system_impl,
    prepare_compile_session_impl,
)
from deerflow.tools.bound_compile_tools import _run_container_bash_impl  # noqa: E402
from typesafe_sdk import RetryPolicy, TypeSafeClient  # noqa: E402

IDENTITY = "cpp-jev-end-to-end-canary-v2"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/406"
BRANCH = "yiwei/406-jev-end-to-end-canary"
SCHEMA_VERSION = "forge-jev-end-to-end-canary-2.0.0"
REPORT_SCHEMA_VERSION = "forge-jev-end-to-end-canary-report-2.0.0"

MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-jev-end-to-end-canary-v2.json"
SCHEMA_PATH = (
    REPO_ROOT / "benchmarks/schemas/forge-jev-end-to-end-canary-v2.schema.json"
)
PREREGISTRATION_PATH = (
    REPO_ROOT / "benchmarks/preregistrations/cpp-jev-end-to-end-canary-v2.md"
)
QUALIFICATION_JSON_PATH = (
    REPO_ROOT / "benchmarks/reports/cpp-jev-end-to-end-canary-v2-qualification.json"
)
QUALIFICATION_MARKDOWN_PATH = (
    REPO_ROOT / "benchmarks/reports/cpp-jev-end-to-end-canary-v2-qualification.md"
)
JSON_REPORT_PATH = REPO_ROOT / "benchmarks/reports/cpp-jev-end-to-end-canary-v2.json"
MARKDOWN_REPORT_PATH = REPO_ROOT / "benchmarks/reports/cpp-jev-end-to-end-canary-v2.md"
EVIDENCE_ROOT = (
    REPO_ROOT / ".compile-sessions/benchmark-evidence-jev-end-to-end-canary-v2"
)
CREDENTIAL_FILE = REPO_ROOT / "jev-apikey.txt"

V1_MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-jev-end-to-end-canary-v1.json"
V1_FAILURE_PATH = (
    REPO_ROOT
    / "benchmarks/reports/cpp-jev-end-to-end-canary-v1-qualification-failure.json"
)

V2_REPORT_PATH = (
    REPO_ROOT / "benchmarks/reports/cpp-typed-semantic-routing-pilot-v2.json"
)
V6_REPORT_PATH = REPO_ROOT / "benchmarks/reports/cpp-jev-offline-qualification-v6.json"
CONTROLLER_REPORT_PATH = (
    REPO_ROOT / "benchmarks/reports/cpp-jev-controller-replay-qualification-v2.json"
)
PARENT_PATHS = (
    V2_REPORT_PATH,
    V6_REPORT_PATH,
    CONTROLLER_REPORT_PATH,
    V1_MANIFEST_PATH,
    V1_FAILURE_PATH,
)

COMPILE_IMAGE = "autocompiler:gcc13"
EXPECTED_IMAGE_ID = (
    "sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a"
)
AGENT_PROFILE = "deepseek-flash"
AGENT_ENDPOINT = "https://api.deepseek.com"
AGENT_CREDENTIAL_ENV = "DEEPSEEK_API_KEY"
AGENT_REQUEST_TIMEOUT_SECONDS = 300
AGENT_MAX_RETRIES = 0

ARMS = ("always_agent", "rule_gate_agent", "jev_gate_agent")
CASE_SPECS = (
    {
        "task_id": "args",
        "fault_type": "invalid_build_state",
        "expected_action": "configure",
    },
    {
        "task_id": "hoextdown",
        "fault_type": "wrong_build_target",
        "expected_action": "build",
    },
    {
        "task_id": "c-ares",
        "fault_type": "missing_compile_input",
        "expected_action": "dependency",
    },
)
SCHEDULE = (
    ("args", "always_agent"),
    ("args", "rule_gate_agent"),
    ("args", "jev_gate_agent"),
    ("hoextdown", "rule_gate_agent"),
    ("hoextdown", "jev_gate_agent"),
    ("hoextdown", "always_agent"),
    ("c-ares", "jev_gate_agent"),
    ("c-ares", "always_agent"),
    ("c-ares", "rule_gate_agent"),
)
AGENT_BUDGET = {
    "max_model_requests": 24,
    "max_recorded_tokens": 300_000,
    "max_agent_steps": 64,
    "max_tool_calls": 48,
    "max_commands": 32,
    "node_timeout_seconds": 1_800,
    "command_timeout_seconds": 900,
    "evaluator_timeout_seconds": 1_800,
    "replay_timeout_seconds": 1_800,
    "cleanup_timeout_seconds": 120,
}
TOTAL_AGENT_REQUEST_CEILING = 216
TOTAL_AGENT_TOKEN_CEILING = 2_700_000
TOTAL_JEV_REQUEST_CEILING = 3
TOTAL_JEV_INPUT_TOKEN_CEILING = 60_000
TOTAL_JEV_COST_CEILING_USD = 0.00252

CALIBRATION = CalibrationContract(
    model="jev-1.13.0",
    coefficient=0.08805149266059632,
    intercept=0.618335523488825,
    threshold=0.6747568477098429,
)
VERIFIER_CAPABILITIES = VerifierCapabilities(True, True, True, True)


class CanaryError(RuntimeError):
    """Canary 身份、预算、evidence 或运行合同无效。"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CanaryError(f"JSON 根必须为对象: {path}")
    return value


def _write_once(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        path.chmod(0o600)
    except FileExistsError as exc:
        raise CanaryError(f"create-once 路径已存在: {path}") from exc


def _write_once_json(path: Path, value: Any) -> None:
    _write_once(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
    )


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)
    path.chmod(0o600)


def _git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise CanaryError(result.stderr.strip() or f"git {' '.join(arguments)} 失败")
    return result.stdout.strip()


def _git_blob_sha256(revision: str, path: Path) -> str:
    relative = path.relative_to(REPO_ROOT).as_posix()
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative}"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise CanaryError(f"无法读取 {revision}:{relative}")
    return hashlib.sha256(result.stdout).hexdigest()


def _task(task_id: str) -> dict[str, Any]:
    matches = [task for task in semantic_v2.TASKS if task["task_id"] == task_id]
    if len(matches) != 1:
        raise CanaryError(f"未知 task: {task_id}")
    return matches[0]


def _case(task_id: str) -> dict[str, str]:
    matches = [case for case in CASE_SPECS if case["task_id"] == task_id]
    if len(matches) != 1:
        raise CanaryError(f"未知 case: {task_id}")
    return matches[0]


def _source_contract(task: dict[str, Any]) -> dict[str, Any]:
    return {
        key: task[key]
        for key in (
            "task_id",
            "project_family",
            "repository_url",
            "commit_sha",
            "source_snapshot_sha256",
            "selected_build_system",
            "fault_file",
            "configure_commands",
            "configure_repair_commands",
            "build_commands",
            "artifact_stage_commands",
            "target",
            "oracle",
        )
    }


def build_manifest(implementation_revision: str) -> dict[str, Any]:
    revision = _git("rev-parse", "--verify", f"{implementation_revision}^{{commit}}")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise CanaryError("implementation revision 必须为完整 commit")
    components = {
        SCRIPT_PATH.relative_to(REPO_ROOT).as_posix(): _git_blob_sha256(
            revision, SCRIPT_PATH
        ),
        "backend/packages/harness/deerflow/compile/jev_controller.py": _git_blob_sha256(
            revision,
            REPO_ROOT / "backend/packages/harness/deerflow/compile/jev_controller.py",
        ),
        "backend/packages/harness/deerflow/compile/agent_workflow_runtime.py": _git_blob_sha256(
            revision,
            REPO_ROOT
            / "backend/packages/harness/deerflow/compile/agent_workflow_runtime.py",
        ),
        "backend/packages/harness/deerflow/compile/external_evaluator_v2.py": _git_blob_sha256(
            revision,
            REPO_ROOT
            / "backend/packages/harness/deerflow/compile/external_evaluator_v2.py",
        ),
    }
    return {
        "$schema": "../schemas/forge-jev-end-to-end-canary-v2.schema.json",
        "schema_version": SCHEMA_VERSION,
        "identity": IDENTITY,
        "issue_url": ISSUE_URL,
        "branch": BRANCH,
        "implementation_revision": revision,
        "components": components,
        "parents": {
            path.relative_to(REPO_ROOT).as_posix(): file_sha256(path)
            for path in PARENT_PATHS
        },
        "cases": [
            {
                **_case(case["task_id"]),
                "source": _source_contract(_task(case["task_id"])),
            }
            for case in CASE_SPECS
        ],
        "arms": list(ARMS),
        "schedule": [
            {"sequence": index, "task_id": task_id, "arm": arm}
            for index, (task_id, arm) in enumerate(SCHEDULE, start=1)
        ],
        "routing": {
            "rule_gate_action": "build",
            "jev_model": CALIBRATION.model,
            "jev_calibration": asdict(CALIBRATION),
            "candidate_actions": ["dependency", "configure", "build", "escalate_agent"],
            "direct_action_terminal_success_allowed": False,
            "agent_escalation_on_direct_action_failure": True,
        },
        "agent_provider": {
            "profile": AGENT_PROFILE,
            "endpoint": AGENT_ENDPOINT,
            "credential_env": AGENT_CREDENTIAL_ENV,
            "request_timeout_seconds": AGENT_REQUEST_TIMEOUT_SECONDS,
            "max_retries": AGENT_MAX_RETRIES,
        },
        "jev_provider": {
            "model": jev_candidate.MODEL_ID,
            "endpoint": jev_candidate.API_BASE_URL,
            "credential_file": CREDENTIAL_FILE.name,
            "max_retries": 0,
            "request_timeout_seconds": 30,
            "input_price_usd_per_million_tokens": jev_candidate.INPUT_PRICE_USD_PER_MILLION_TOKENS,
        },
        "environment": {
            "compile_image": COMPILE_IMAGE,
            "image_id": EXPECTED_IMAGE_ID,
            "parallel_jobs": 4,
            "network_policy": "compile-network-v1",
        },
        "budget": {
            "per_arm_agent": AGENT_BUDGET,
            "total_agent_request_ceiling": TOTAL_AGENT_REQUEST_CEILING,
            "total_agent_token_ceiling": TOTAL_AGENT_TOKEN_CEILING,
            "total_jev_request_ceiling": TOTAL_JEV_REQUEST_CEILING,
            "total_jev_input_token_ceiling": TOTAL_JEV_INPUT_TOKEN_CEILING,
            "total_jev_cost_ceiling_usd": TOTAL_JEV_COST_CEILING_USD,
        },
        "authorization": {
            "credential_reads": True,
            "provider_calls": True,
            "docker_execution": True,
            "formal_attempts": 9,
            "formal_evidence_write": True,
            "historical_evidence_write": False,
            "replacement": False,
            "backfill": False,
        },
        "stopping_rules": {
            "stop_batch_on_identity_or_evidence_corruption": True,
            "stop_batch_on_budget_overrun": True,
            "stop_batch_on_cleanup_or_orphan_failure": True,
            "provider_or_model_failure_is_arm_outcome": True,
            "continue_after_behavioral_failure": True,
        },
        "evidence": {
            "root": EVIDENCE_ROOT.relative_to(REPO_ROOT).as_posix(),
            "create_once": True,
            "preserve_failures": True,
            "store_credentials": False,
        },
        "interpretation": {
            "canary_only": True,
            "treatment_effect": False,
            "strict_success_noninferiority": False,
            "cost_savings_claim": False,
            "dynamic_budget_claim": False,
        },
    }


def build_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-jev-end-to-end-canary-v2.schema.json",
        "title": "Forge Jev end-to-end canary v2",
        "const": manifest,
    }


def render_preregistration(manifest: dict[str, Any]) -> str:
    schedule = "\n".join(
        f"{row['sequence']}. `{row['task_id']}` / `{row['arm']}`"
        for row in manifest["schedule"]
    )
    return f"""# Jev 三臂端到端 canary v2

- Tracking Issue：[#406]({ISSUE_URL})
- Identity：`{IDENTITY}`
- Implementation revision：`{manifest["implementation_revision"]}`
- Manifest canonical SHA-256：`{canonical_sha256(manifest)}`

## 研究问题

在三个受控、已知可恢复的 CMake/Make/Autotools 失败状态上，`AlwaysAgent`、`RuleGate+Agent` 和 `JevGate+Agent` 能否在相同完整 Agent 预算与同一严格 evaluator 下形成闭合终态，并完整记录 Agent 调用、Jev 调用、token、墙钟、升级与严格成功？

本阶段是 canary，只评价运行闭合、指标可采集性和预算可接受性，不估计 treatment effect。

v1 在零 Provider qualification 启动时因父 manifest 常量名错误而在 Docker 动作前失败，
未读取 credential、未调用 Provider、未创建 formal attempt 或 formal evidence。v2 只修正
该接口名并使用全新 manifest、报告和 evidence root；不导入、续跑或改写 v1。

## 样本与顺序

- `args` / CMake / `invalid_build_state` / 预期 `configure`
- `hoextdown` / Make / `wrong_build_target` / 预期 `build`
- `c-ares` / Autotools / `missing_compile_input` / 预期 `dependency`

固定顺序：

{schedule}

三个项目和故障已进入先前 Jev 资格数据，因此本 canary 不支持未见项目泛化；复用只服务于确认端到端接线。

## 三臂

- `always_agent`：故障状态直接升级完整 Agent。
- `rule_gate_agent`：固定选择 `build`；动作失败时升级完整 Agent，动作成功时由确定性 continuation 和同一 evaluator 收口。
- `jev_gate_agent`：Jev 以正序/逆序 Choice 判断动作，经冻结 Platt 门禁后直接执行或升级 Agent；动作失败时升级完整 Agent。

直接动作只执行代码绑定命令，不能生成 Shell，也不能宣告成功。所有候选必须经过 CandidateVerifier、functional oracle、provenance 和 clean replay。

## 固定预算

- 每 arm Agent：最多 {AGENT_BUDGET["max_model_requests"]} 请求、{AGENT_BUDGET["max_recorded_tokens"]} tokens、{AGENT_BUDGET["node_timeout_seconds"]} 秒；
- 全阶段 Agent：最多 {TOTAL_AGENT_REQUEST_CEILING} 请求、{TOTAL_AGENT_TOKEN_CEILING} tokens；
- Jev：3 请求、最多 {TOTAL_JEV_INPUT_TOKEN_CEILING} input tokens、`${TOTAL_JEV_COST_CEILING_USD}`；
- Provider retry 均为 0；不存在 replacement 或 backfill。

## 停止规则与结论

identity/evidence 损坏、预算越界、cleanup/orphan 失败立即停止整个 batch。Provider、模型行为、无候选或严格验证失败保留为 arm outcome，并在资源闭合时继续后续 arm。

9 个 arm 均产生可分类终态、指标完整、无预算越界、无历史 evidence 修改且无受管资源残留时，决定 `proceed_to_formal_end_to_end_comparison_design`。否则决定 `stop_and_repair_canary_infrastructure` 或 `stop_before_formal_comparison`。

## 解释边界

Canary 结果不能支持成功率非劣、成本下降、显著性、模型排名、自然失败泛化或动态预算优越性。正式比较必须使用新的未见项目族和独立 identity。
"""


def bind_identity(implementation_revision: str) -> dict[str, Any]:
    manifest = build_manifest(implementation_revision)
    _write_once_json(MANIFEST_PATH, manifest)
    _write_once_json(SCHEMA_PATH, build_schema(manifest))
    _write_once(PREREGISTRATION_PATH, render_preregistration(manifest))
    return manifest


def validate_manifest() -> dict[str, Any]:
    manifest = _load_json(MANIFEST_PATH)
    expected = build_manifest(manifest.get("implementation_revision", ""))
    if manifest != expected:
        raise CanaryError("manifest 与冻结生成结果不一致")
    schema = _load_json(SCHEMA_PATH)
    if schema != build_schema(expected):
        raise CanaryError("const Schema 漂移")
    jsonschema.validate(manifest, schema)
    if PREREGISTRATION_PATH.read_text(encoding="utf-8") != render_preregistration(
        expected
    ):
        raise CanaryError("预注册文本漂移")
    return manifest


def validate_parents() -> None:
    manifest = validate_manifest()
    for relative, digest in manifest["parents"].items():
        if file_sha256(REPO_ROOT / relative) != digest:
            raise CanaryError(f"父报告漂移: {relative}")
    v2 = _load_json(V2_REPORT_PATH)
    v6 = _load_json(V6_REPORT_PATH)
    controller = _load_json(CONTROLLER_REPORT_PATH)
    v1_failure = _load_json(V1_FAILURE_PATH)
    if v2.get("analysis", {}).get("decision") != "proceed_to_jev_offline_qualification":
        raise CanaryError("v2 未通过")
    if v6.get("decision") != "proceed_to_controller_replay_qualification":
        raise CanaryError("v6 未通过")
    if controller.get("decision") != "proceed_to_end_to_end_canary":
        raise CanaryError("controller replay 未通过")
    if v1_failure.get("decision") != "supersede_with_fresh_v2_identity":
        raise CanaryError("v1 qualification failure record 无效")


def _image_id() -> str:
    result = subprocess.run(
        ["docker", "image", "inspect", COMPILE_IMAGE, "--format", "{{.Id}}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise CanaryError("无法读取编译镜像")
    return result.stdout.strip()


def preflight(
    *, require_clean: bool = True, require_absent_evidence: bool = True
) -> dict[str, Any]:
    manifest = validate_manifest()
    validate_parents()
    _qualification_report()
    if _git("branch", "--show-current") != BRANCH:
        raise CanaryError("当前分支与实验身份不一致")
    if require_clean and _git("status", "--porcelain"):
        raise CanaryError("正式运行要求干净工作树")
    head = _git("rev-parse", "HEAD")
    if (
        subprocess.run(
            [
                "git",
                "merge-base",
                "--is-ancestor",
                manifest["implementation_revision"],
                head,
            ],
            cwd=REPO_ROOT,
            check=False,
        ).returncode
        != 0
    ):
        raise CanaryError("HEAD 不是 implementation revision 后代")
    if f"origin/{BRANCH}" not in {
        row.strip() for row in _git("branch", "-r", "--contains", head).splitlines()
    }:
        raise CanaryError("正式运行 revision 尚未推送")
    for relative, digest in manifest["components"].items():
        if file_sha256(REPO_ROOT / relative) != digest:
            raise CanaryError(f"实现组件漂移: {relative}")
    if _image_id() != manifest["environment"]["image_id"]:
        raise CanaryError("编译镜像漂移")
    if not CREDENTIAL_FILE.is_file() or CREDENTIAL_FILE.stat().st_mode & 0o777 != 0o600:
        raise CanaryError("Jev credential 文件必须存在且权限为 600")
    if not os.environ.get(AGENT_CREDENTIAL_ENV):
        raise CanaryError("完整 Agent credential 环境变量未注入")
    if require_absent_evidence and EVIDENCE_ROOT.exists():
        raise CanaryError("正式 evidence root 已存在")
    if require_absent_evidence and (
        JSON_REPORT_PATH.exists() or MARKDOWN_REPORT_PATH.exists()
    ):
        raise CanaryError("正式报告路径必须不存在")
    agent_runner.require_zero_managed_resources()
    jev_v6.validate_egress()
    return {
        "ready": True,
        "identity": IDENTITY,
        "git_commit": head,
        "manifest_sha256": canonical_sha256(manifest),
        "image_id": _image_id(),
        "credential_reads": 0,
        "provider_calls": 0,
        "formal_attempts": 0,
        "evidence_exists": EVIDENCE_ROOT.exists(),
        "zero_managed_resources": True,
    }


def _commands(task: dict[str, Any], fault_type: str, action_family: str) -> list[str]:
    if action_family == "dependency":
        return [f"git checkout HEAD -- {shlex.quote(task['fault_file'])}"]
    if action_family == "configure":
        return list(task["configure_repair_commands"])
    if action_family == "build":
        return list(task["build_commands"])
    raise CanaryError(f"不可直接执行动作: {action_family}")


def _candidate_actions(state: dict[str, Any]) -> tuple[CandidateAction, ...]:
    return tuple(
        CandidateAction(
            action_id=row["action_id"],
            action_family=row["action_family"],
            bound_commands=tuple(row["bound_commands"]),
            direct_execution=row["direct_execution"],
            preconditions_satisfied=row["preconditions_checked_by_runner"],
        )
        for row in state["candidate_actions"]
    )


def _decision_state(state: dict[str, Any], fingerprint: str) -> DecisionState:
    return DecisionState(
        state_id=state["state_id"],
        build_system=state["build_system"],
        phase_facts=state["phase_facts"],
        remaining_actions=8,
        remaining_wall_clock_seconds=900,
        expected_request_fingerprint=fingerprint,
    )


def rule_route(state: dict[str, Any]) -> str:
    del state
    return "build"


def _read_jev_credential() -> str:
    if CREDENTIAL_FILE.stat().st_mode & 0o777 != 0o600:
        raise CanaryError("Jev credential 权限漂移")
    value = CREDENTIAL_FILE.read_text(encoding="utf-8").strip()
    if not value or "\n" in value or "\r" in value:
        raise CanaryError("Jev credential 必须只有一行")
    return value


def request_jev(state: dict[str, Any]) -> tuple[TypedDecision, dict[str, Any]]:
    prompt = jev_v6._prompt_contract(2)
    provider_state = jev_candidate.provider_state(state["model_input"])
    questions = jev_v6._provider_questions(prompt)
    fingerprint = jev_candidate.request_fingerprint(provider_state, questions)
    logging.getLogger("typesafe_sdk").disabled = True
    key = _read_jev_credential()
    started = time.perf_counter()
    with jev_v6._provider_http_client() as http_client:
        with TypeSafeClient(
            api_key=key,
            model=jev_candidate.MODEL_ID,
            retry=RetryPolicy(max_retries=0, timeout=30.0),
            base_url=jev_candidate.API_BASE_URL,
            http_client=http_client,
        ) as client:
            response = client.system_one(state=provider_state, questions=questions)
    key = ""
    normalized = jev_v6.normalize_response(
        response, latency_ms=(time.perf_counter() - started) * 1000
    )
    primary = normalized["answers"]["next_action_primary"]
    reverse = normalized["answers"]["next_action_order_sensitivity"]
    decision = TypedDecision(
        state_id=state["state_id"],
        model=normalized["model"],
        request_fingerprint=fingerprint,
        primary_choice=primary["choice"],
        reverse_choice=reverse["choice"],
        probabilities=primary["probabilities"],
        reverse_probabilities=reverse["probabilities"],
    )
    return decision, {"request_fingerprint": fingerprint, "response": normalized}


def choose_jev_route(
    state: dict[str, Any], decision: TypedDecision
) -> tuple[str, dict[str, Any]]:
    route = route_next_action(
        state=_decision_state(state, decision.request_fingerprint),
        candidates=_candidate_actions(state),
        decision=decision,
        calibration=CALIBRATION,
        verifier_capabilities=VERIFIER_CAPABILITIES,
    )
    receipt = dispatch_route(
        route=route, candidates=_candidate_actions(state), executor=lambda _: None
    )
    return route.selected_action_family, {
        "disposition": route.disposition,
        "selected_action_id": route.selected_action_id,
        "selected_action_family": route.selected_action_family,
        "calibrated_safe_probability": route.calibrated_safe_probability,
        "reasons": list(route.reasons),
        "dispatch_disposition": receipt.disposition,
    }


def zero_provider_qualification() -> dict[str, Any]:
    manifest = validate_manifest()
    parent_manifest = _load_json(semantic_v2.DEFAULT_MANIFEST)
    image = manifest["environment"]["image_id"]
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(
        prefix="forge-jev-e2e-qualification-"
    ) as temporary:
        base = Path(temporary)
        for case in CASE_SPECS:
            task = _task(case["task_id"])
            root = base / task["task_id"]
            source = root / "source"
            configured = root / "configured"
            configured_artifacts = root / "configured-artifacts"
            root.mkdir(parents=True)
            typed_v1._clone_exact(task, source)
            semantic_v2._copy_tree(source, configured)
            configured_artifacts.mkdir()
            configure = typed_v1._run_container(
                manifest=parent_manifest,
                image=image,
                workspace=configured,
                artifacts=configured_artifacts,
                script=typed_v1._commands_script(task["configure_commands"]),
                log_path=root / "configure.log",
            )
            if configure["exit_code"] != 0 or configure["timed_out"]:
                raise CanaryError(f"{task['task_id']} qualification configure 失败")
            fault_root = root / "fault"
            fault_workspace = fault_root / "workspace"
            fault_artifacts = fault_root / "artifacts"
            fault_root.mkdir()
            semantic_v2._copy_tree(configured, fault_workspace)
            fault_artifacts.mkdir()
            fault = semantic_v2._inject_fault(
                manifest=parent_manifest,
                image=image,
                task=task,
                fault_type=case["fault_type"],
                workspace=fault_workspace,
                artifacts=fault_artifacts,
                log_path=fault_root / "fault.log",
            )
            state = semantic_v2._state_record(
                task, case["fault_type"], fault["log_tail"]
            )
            action = next(
                row
                for row in state["candidate_actions"]
                if row["action_family"] == case["expected_action"]
            )
            action_root = root / "action"
            action_root.mkdir()
            outcome = semantic_v2._execute_action_branch(
                manifest=parent_manifest,
                image=image,
                task=task,
                state=state,
                action=action,
                fault_workspace=fault_workspace,
                replicate=1,
                root=action_root,
            )
            rows.append(
                {
                    "task_id": task["task_id"],
                    "build_system": task["selected_build_system"],
                    "fault_type": case["fault_type"],
                    "expected_action": case["expected_action"],
                    "state_id": state["state_id"],
                    "fault_exit_code": fault["exit_code"],
                    "action_exit_code": outcome["action_exit_code"],
                    "strict_checks": outcome["strict_checks"],
                    "strict_success": outcome["strict_success"],
                }
            )
    gates = {
        "all_build_systems": {row["build_system"] for row in rows}
        == {"cmake", "make", "autotools"},
        "all_faults_triggered": all(
            row["fault_exit_code"] not in (None, 0) for row in rows
        ),
        "all_actions_succeeded": all(row["action_exit_code"] == 0 for row in rows),
        "all_strict_checks_passed": all(
            row["strict_success"] and set(row["strict_checks"].values()) == {True}
            for row in rows
        ),
        "zero_provider": True,
        "zero_credential_read": True,
    }
    report = {
        "schema_version": "forge-jev-end-to-end-canary-qualification-1.0.0",
        "identity": IDENTITY,
        "manifest_sha256": canonical_sha256(manifest),
        "created_at": _now(),
        "rows": rows,
        "gates": gates,
        "passed": all(gates.values()),
        "decision": "proceed_to_formal_canary"
        if all(gates.values())
        else "stop_before_formal_canary",
        "provider_calls": 0,
        "credential_reads": 0,
        "formal_attempts": 0,
    }
    if QUALIFICATION_JSON_PATH.exists() or QUALIFICATION_MARKDOWN_PATH.exists():
        raise CanaryError("qualification 报告已存在")
    _write_once_json(QUALIFICATION_JSON_PATH, report)
    _write_once(
        QUALIFICATION_MARKDOWN_PATH,
        "# Jev 三臂端到端 canary v2 零 Provider 资格报告\n\n"
        f"- 决定：`{report['decision']}`\n"
        f"- 三个构建系统严格成功：`{sum(row['strict_success'] for row in rows)}/3`\n"
        "- Provider / credential / formal attempt：`0 / 0 / 0`\n\n"
        "该门禁只证明三个冻结失败状态、代码绑定最优动作和严格验证链可执行；不证明三臂效果。\n",
    )
    return report


def _qualification_report() -> dict[str, Any]:
    if (
        not QUALIFICATION_JSON_PATH.is_file()
        or not QUALIFICATION_MARKDOWN_PATH.is_file()
    ):
        raise CanaryError("缺少已提交的零 Provider 资格报告")
    report = _load_json(QUALIFICATION_JSON_PATH)
    manifest = validate_manifest()
    if report.get("identity") != IDENTITY or report.get(
        "manifest_sha256"
    ) != canonical_sha256(manifest):
        raise CanaryError("qualification 报告 identity 漂移")
    if (
        report.get("passed") is not True
        or report.get("decision") != "proceed_to_formal_canary"
    ):
        raise CanaryError("零 Provider 资格门禁未通过")
    return report


def _experiment_policy(
    manifest: dict[str, Any], task: dict[str, Any], arm: str, sequence: int
) -> ExperimentPolicy:
    return ExperimentPolicy(
        benchmark_id=IDENTITY,
        manifest_sha256=canonical_sha256(manifest),
        case_id=f"{sequence:02d}-{task['task_id']}",
        condition=arm,
        repetition=1,
        expected_repo_url=task["repository_url"],
        expected_commit_sha=task["commit_sha"],
        expected_build_system=task["selected_build_system"],
        compile_image=manifest["environment"]["compile_image"],
        image_id=manifest["environment"]["image_id"],
        model_name=AGENT_PROFILE,
        endpoint=AGENT_ENDPOINT,
        credential_env=AGENT_CREDENTIAL_ENV,
        request_timeout_seconds=AGENT_REQUEST_TIMEOUT_SECONDS,
        model_max_retries=AGENT_MAX_RETRIES,
        compiler_max_turns=AGENT_BUDGET["max_model_requests"],
        subagent_timeout_seconds=AGENT_BUDGET["node_timeout_seconds"],
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=(),
        cmake_arguments=(),
        configure_arguments=(),
        environment=(),
        minimum_replay_delay_seconds=0,
        compiler_model_turn_limit=AGENT_BUDGET["max_model_requests"],
        compiler_graph_recursion_limit=AGENT_BUDGET["max_agent_steps"],
        compiler_wall_clock_seconds=AGENT_BUDGET["node_timeout_seconds"],
        compiler_post_build_reserve_seconds=AGENT_BUDGET["cleanup_timeout_seconds"],
    )


def _oracle_ref(task: dict[str, Any]) -> str:
    return f"{task['task_id']}-functional-oracle-v1"


def _compiled_target(task: dict[str, Any]) -> tuple[str, str]:
    compiled_types = {"executable", "shared_library", "static_library", "object"}
    matches = [
        (path, artifact_type)
        for path, artifact_type in zip(
            task["target"]["required_artifacts"],
            task["target"]["artifact_types"],
            strict=True,
        )
        if artifact_type in compiled_types
    ]
    if len(matches) != 1:
        raise CanaryError(f"{task['task_id']} 必须只有一个编译目标产物")
    return matches[0]


def _node_input(
    manifest: dict[str, Any],
    task: dict[str, Any],
    session: Any,
    attempt_id: str,
    state: dict[str, Any],
    route_observation: dict[str, Any],
) -> AgentBuildNodeInput:
    _target_path, target_type = _compiled_target(task)
    return AgentBuildNodeInput(
        task_id=task["task_id"],
        attempt_id=attempt_id,
        session_id=session.session_id,
        repository_url=task["repository_url"],
        commit_sha=task["commit_sha"],
        source_snapshot_sha256=task["source_snapshot_sha256"],
        build_system_candidates=(task["selected_build_system"],),
        target_contract=AgentWorkflowTargetContract(
            target_id=f"{task['task_id']}-target",
            artifact_types=(target_type,),
            artifact_path_patterns=tuple(task["target"]["required_artifacts"]),
            functional_oracle_ref=_oracle_ref(task),
        ),
        operation_policy_ref="compile-operation-policy-v1",
        environment=AgentWorkflowEnvironmentIdentity(
            image_id=manifest["environment"]["image_id"],
            parallel_jobs=manifest["environment"]["parallel_jobs"],
            network_policy=manifest["environment"]["network_policy"],
        ),
        budget=AgentWorkflowBudget(**AGENT_BUDGET),
        experiment_identity=AgentWorkflowExperimentIdentity(
            manifest_sha256=canonical_sha256(manifest),
            protocol_sha256=file_sha256(PREREGISTRATION_PATH),
            runner_sha256=manifest["components"][
                SCRIPT_PATH.relative_to(REPO_ROOT).as_posix()
            ],
        ),
        initial_observation={
            "fault_type": _case(task["task_id"])["fault_type"],
            "semantic_failure_log": state["semantic_failure_log"],
            "candidate_action_families": tuple(
                row["action_family"] for row in state["candidate_actions"]
            ),
            "required_candidate_artifacts": tuple(task["target"]["required_artifacts"]),
            "functional_oracle": task["oracle"],
            "selected_build_system": task["selected_build_system"],
            "route_observation": route_observation,
        },
    )


def _oracle_spec(task: dict[str, Any]) -> FunctionalOracleSpec:
    oracle = task["oracle"]
    oracle_ref = _oracle_ref(task)
    if oracle["kind"] == "command":
        return FunctionalOracleSpec(
            oracle_ref=oracle_ref,
            argv=tuple(oracle["argv"]),
            workdir="/workspace/repo",
            timeout_seconds=120,
            requires_explicit_relative_executable=True,
        )
    if oracle["kind"] == "compile_and_run":
        suffix = ".c" if oracle["language"] == "c11" else ".cc"
        source_path = f"/workspace/forge-jev-canary-{task['task_id']}{suffix}"
        executable_path = f"/workspace/forge-jev-canary-{task['task_id']}"
        encoded = base64.b64encode(oracle["source"].encode("utf-8")).decode("ascii")
        compile_argv = [
            source_path
            if item == "{source}"
            else executable_path
            if item == "{executable}"
            else item
            for item in oracle["compile_argv"]
        ]
        run_argv = [
            executable_path if item == "{executable}" else item
            for item in oracle["run_argv"]
        ]
        command = (
            f"printf %s {shlex.quote(encoded)} | base64 -d > {shlex.quote(source_path)}"
            f" && {shlex.join(compile_argv)} && {shlex.join(run_argv)}"
        )
        return FunctionalOracleSpec(
            oracle_ref=oracle_ref,
            argv=("sh", "-c", command),
            workdir="/workspace",
            timeout_seconds=120,
        )
    raise CanaryError(f"不支持的 oracle kind: {oracle['kind']}")


def _run_bound_commands(
    session: Any,
    commands: list[str],
    role: str,
    *,
    require_success: bool,
) -> tuple[bool, list[Any], str]:
    records: list[Any] = []
    last_message = ""
    for command in commands:
        result, message, record = _run_container_bash_impl(
            session=session,
            command=command,
            command_role=role,
            timeout_seconds=AGENT_BUDGET["command_timeout_seconds"],
            workdir="/workspace/repo",
        )
        records.append(record)
        last_message = message
        succeeded = result.exit_code == 0 and not record.timed_out
        if not succeeded:
            if require_success:
                raise CanaryError(f"{role} 冻结命令执行失败")
            return False, records, last_message
    return True, records, last_message


def _inject_fault(
    session: Any, task: dict[str, Any], fault_type: str, ledger: ExperimentLedger
) -> tuple[dict[str, Any], Any]:
    workspace = Path(session.leadagent_repo_dir)
    fault_path = workspace / task["fault_file"]
    if fault_type == "invalid_build_state":
        invalid_path = workspace / (
            "build/Makefile" if task["selected_build_system"] == "cmake" else "Makefile"
        )
        invalid_path.write_text("all\n", encoding="utf-8")
        mutation = "replace_build_state"
        failure_commands = list(task["build_commands"])
    elif fault_type == "missing_compile_input":
        fault_path.unlink()
        mutation = "remove_compile_input"
        failure_commands = list(task["build_commands"])
    elif fault_type == "wrong_build_target":
        mutation = "none"
        failure_commands = [semantic_v2._fault_trigger_command(task, fault_type)]
    else:
        raise CanaryError(f"未知 fault type: {fault_type}")
    ledger.append(
        "canary.fault_injected",
        {
            "fault_type": fault_type,
            "mutation": mutation,
            "fault_file": task["fault_file"],
        },
    )
    succeeded, records, message = _run_bound_commands(
        session,
        failure_commands,
        "build",
        require_success=False,
    )
    if succeeded or not records or records[-1].timed_out:
        raise CanaryError(f"{task['task_id']} 未形成有界构建失败")
    state = semantic_v2._state_record(task, fault_type, message[-8_000:])
    ledger.append(
        "canary.fault_observed",
        {
            "state_id": state["state_id"],
            "command_id": records[-1].command_id,
            "exit_code": records[-1].exit_code,
        },
    )
    return state, records[-1]


def _direct_candidate(
    *,
    node_input: AgentBuildNodeInput,
    session: Any,
    manager: Any,
    sequence: int,
    arm: str,
    recipe_records: list[Any],
    supporting_record: Any,
) -> tuple[AgentBuildNodeResult, Path]:
    workflow_dir = (
        Path(session.metadata_path).parent / "agent-workflow" / node_input.attempt_id
    )
    _write_once(workflow_dir / "input.json", node_input.canonical_json())
    ledger = AgentWorkflowEvidenceLedger(
        workflow_dir / "events.jsonl",
        node_input=node_input,
        run_id=session.run_id,
    )
    ledger.append("attempt.registered", input_sha256=node_input.canonical_sha256())
    ledger.append("node.ready")
    ledger.append("node.started", controller="typed_direct_execution")
    state_machine = AgentWorkflowStateMachine()
    state_machine.transition(AgentWorkflowNodeStatus.READY)
    state_machine.transition(AgentWorkflowNodeStatus.RUNNING)
    tracker = AgentWorkflowBudgetTracker(node_input.budget)
    store = AgentWorkflowCandidateStore(state_machine, tracker)
    candidate_path = workflow_dir / "candidate.json"
    service = AgentWorkflowCandidateService(
        node_input=node_input,
        session=session,
        manager=manager,
        store=store,
        candidate_path=candidate_path,
        ledger=ledger,
    )
    target_path, _target_type = _compiled_target(_task(node_input.task_id))
    request = SubmitCandidateRequest(
        candidate_id=f"canary-{sequence:02d}-{arm}-direct",
        build_system=_task(node_input.task_id)["selected_build_system"],
        supporting_command_ids=(supporting_record.command_id,),
        artifact_paths=tuple(_task(node_input.task_id)["target"]["required_artifacts"]),
        target_mapping={node_input.target_contract.target_id: target_path},
        recipe_command_ids=tuple(record.command_id for record in recipe_records),
        agent_summary="Typed route completed through code-bound commands.",
    )
    response = service.submit(request)
    if not response.accepted:
        raise CanaryError(
            f"direct candidate 被拒绝: {','.join(response.rejection_codes)}"
        )
    current = manager.load_session(session.session_id, session.thread_id)
    session.__dict__.update(current.__dict__)
    ledger.append("node.terminal", node_status="submitted", primary_failure=None)
    result = AgentBuildNodeResult(
        node_status="submitted",
        candidate_generated_observed=True,
        candidate_submitted=True,
        submission_id=response.submission_id,
        candidate_record_sha256=response.candidate_record_sha256,
        usage=AgentWorkflowUsage(0, 0, 0, 0, 0),
        wall_clock_ms=0,
        evidence_head_sha256=ledger.head_sha256,
        session_terminal_status=session.status,
    )
    result.validate()
    return result, candidate_path


def _evaluate(
    *,
    node_input: AgentBuildNodeInput,
    node_result: AgentBuildNodeResult,
    session: Any,
    candidate_path: Path,
    evaluation_id: str,
) -> Any:
    services = get_compile_services()
    task = _task(node_input.task_id)
    return run_external_evaluator_v2(
        node_input=node_input,
        node_result=node_result,
        session=session,
        manager=services.manager,
        candidate_path=candidate_path,
        evaluation_id=evaluation_id,
        backend=ForgeCompileEvaluationBackend(
            oracle_registry={_oracle_ref(task): _oracle_spec(task)}
        ),
    )


def _agent_model(thread_id: str) -> Any:
    return agent_runner._create_provider_model(
        {
            "provider_candidate": {
                "profile": AGENT_PROFILE,
                "endpoint": AGENT_ENDPOINT,
                "request_timeout_seconds": AGENT_REQUEST_TIMEOUT_SECONDS,
                "model_max_retries": AGENT_MAX_RETRIES,
            }
        },
        experiment_thread_id=thread_id,
    )


def _arm_directory(sequence: int, task_id: str, arm: str) -> Path:
    return EVIDENCE_ROOT / "arms" / f"{sequence:02d}-{task_id}-{arm}"


def _claim_marker(
    path: Path,
    *,
    manifest_sha256: str,
    release_revision: str,
    sequence: int,
    task_id: str,
    arm: str,
) -> None:
    _write_once_json(
        path,
        {
            "schema_version": "forge-jev-end-to-end-canary-attempt-1.0.0",
            "identity": IDENTITY,
            "manifest_sha256": manifest_sha256,
            "release_revision": release_revision,
            "sequence": sequence,
            "task_id": task_id,
            "arm": arm,
            "status": "started",
            "error_class": None,
            "updated_at": _now(),
        },
    )


def _finish_marker(path: Path, *, status: str, error_class: str | None = None) -> None:
    marker = _load_json(path)
    if marker.get("status") != "started":
        raise CanaryError("attempt marker 不处于 started")
    marker["status"] = status
    marker["error_class"] = error_class
    marker["updated_at"] = _now()
    _atomic_json(path, marker)


def _safe_cleanup(session: Any) -> tuple[Any, Any]:
    finalized, cleanup = cleanup_and_finalize_compile_session_impl(session=session)
    agent_runner.require_zero_managed_resources()
    if not cleanup.succeeded or finalized.finalized_at is None:
        raise CanaryError("Compile Session cleanup 或 terminalization 未闭合")
    return finalized, cleanup


async def execute_arm(
    manifest: dict[str, Any],
    *,
    sequence: int,
    task_id: str,
    arm: str,
    release_revision: str,
) -> dict[str, Any]:
    task = _task(task_id)
    case = _case(task_id)
    digest = canonical_sha256(manifest)
    arm_dir = _arm_directory(sequence, task_id, arm)
    marker_path = arm_dir / "attempt.json"
    result_path = arm_dir / "result.json"
    _claim_marker(
        marker_path,
        manifest_sha256=digest,
        release_revision=release_revision,
        sequence=sequence,
        task_id=task_id,
        arm=arm,
    )
    ledger = ExperimentLedger.create(
        arm_dir / "experiment.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={
            "manifest_sha256": digest,
            "release_revision": release_revision,
            "sequence": sequence,
            "task_id": task_id,
            "arm": arm,
        },
    )
    thread_id = f"jev-canary-{sequence:02d}-{task_id}-{arm}-{digest[:10]}"
    services = get_compile_services()
    session = None
    active = False
    cleanup_succeeded = False
    started = time.perf_counter()
    route_action = "escalate_agent"
    route_observation: dict[str, Any] = {"controller": arm}
    direct_attempted = False
    direct_action_succeeded = False
    escalated = arm == "always_agent"
    jev_requests = 0
    jev_response: dict[str, Any] | None = None
    jev_error_class: str | None = None
    node_result: AgentBuildNodeResult | None = None
    evaluation = None
    error_class: str | None = None
    finalized = None
    cleanup = None
    initial_command_count = 0
    try:
        activate_experiment(
            thread_id=thread_id,
            experiment_id=ledger.experiment_id,
            physical_attempt_id=ledger.physical_attempt_id,
            ledger=ledger,
            policy=_experiment_policy(manifest, task, arm, sequence),
        )
        active = True
        session = prepare_compile_session_impl(
            thread_id=thread_id,
            repo_url=task["repository_url"],
            run_id=f"jev-canary-{sequence:02d}-{uuid.uuid4().hex}",
            task_description=f"Jev end-to-end canary {sequence:02d}: {task_id}/{arm}",
        )
        clone, _message = clone_repository_impl(
            session=session,
            repo_url=task["repository_url"],
            commit_sha=task["commit_sha"],
            depth=1,
            max_retries=1,
        )
        if clone.exit_code != 0 or session.commit_sha != task["commit_sha"]:
            raise CanaryError(f"{task_id} 无法检出冻结 commit")
        primary, _detected, _suggested = inspect_build_system_impl(session=session)
        if primary != task["selected_build_system"]:
            raise CanaryError(f"{task_id} build system 漂移")
        services.manager.save_session(session)
        _configured, baseline_records, _configure_message = _run_bound_commands(
            session,
            list(task["configure_commands"]),
            "configure",
            require_success=True,
        )
        initial_command_count = len(
            services.manager.load_session(
                session.session_id, session.thread_id
            ).commands
        )
        state, failure_record = _inject_fault(session, task, case["fault_type"], ledger)
        route_observation["failure_command_id"] = failure_record.command_id
        route_observation["state_id"] = state["state_id"]

        if arm == "rule_gate_agent":
            route_action = rule_route(state)
            route_observation.update(
                {
                    "selected_action_family": route_action,
                    "disposition": "direct_execute",
                }
            )
        elif arm == "jev_gate_agent":
            jev_requests = 1
            try:
                decision, jev_response = request_jev(state)
                route_action, decision_route = choose_jev_route(state, decision)
                route_observation.update(decision_route)
                route_observation["request_fingerprint"] = decision.request_fingerprint
            except Exception as exc:
                jev_error_class = type(exc).__name__
                route_action = "escalate_agent"
                route_observation.update(
                    {
                        "selected_action_family": route_action,
                        "disposition": "escalate_agent",
                        "reasons": ["jev_provider_or_contract_failure"],
                    }
                )
        elif arm != "always_agent":
            raise CanaryError(f"未知 arm: {arm}")

        if route_action != "escalate_agent":
            direct_attempted = True
            action_succeeded, action_records, _action_message = _run_bound_commands(
                session,
                _commands(task, case["fault_type"], route_action),
                route_action,
                require_success=False,
            )
            direct_action_succeeded = action_succeeded
            if action_succeeded:
                build_records = action_records if route_action == "build" else []
                if route_action != "build":
                    build_succeeded, build_records, _build_message = (
                        _run_bound_commands(
                            session,
                            list(task["build_commands"]),
                            "build",
                            require_success=False,
                        )
                    )
                    action_succeeded = build_succeeded
                stage_records: list[Any] = []
                if action_succeeded:
                    stage_succeeded, stage_records, _stage_message = (
                        _run_bound_commands(
                            session,
                            list(task["artifact_stage_commands"]),
                            "artifact_stage",
                            require_success=False,
                        )
                    )
                    action_succeeded = stage_succeeded
                if action_succeeded:
                    direct_attempt_id = f"canary-{sequence:02d}-{arm}-direct"
                    direct_input = _node_input(
                        manifest,
                        task,
                        session,
                        direct_attempt_id,
                        state,
                        route_observation,
                    )
                    recipe_records = [*baseline_records, *action_records]
                    if route_action != "build":
                        recipe_records.extend(build_records)
                    recipe_records.extend(stage_records)
                    node_result, candidate_path = _direct_candidate(
                        node_input=direct_input,
                        session=session,
                        manager=services.manager,
                        sequence=sequence,
                        arm=arm,
                        recipe_records=recipe_records,
                        supporting_record=build_records[-1],
                    )
                    evaluation = _evaluate(
                        node_input=direct_input,
                        node_result=node_result,
                        session=session,
                        candidate_path=candidate_path,
                        evaluation_id=f"canary-eval-{sequence:02d}-{arm}-direct",
                    )
                else:
                    escalated = True
            else:
                escalated = True

        if route_action == "escalate_agent" or escalated:
            escalated = True
            agent_attempt_id = f"canary-{sequence:02d}-{arm}-agent"
            agent_input = _node_input(
                manifest, task, session, agent_attempt_id, state, route_observation
            )
            model = _agent_model(thread_id)
            node_result = await run_agent_workflow_node_v1(
                node_input=agent_input,
                session=session,
                manager=services.manager,
                model=model,
            )
            if node_result.candidate_submitted:
                candidate_path = (
                    Path(session.metadata_path).parent
                    / "agent-workflow"
                    / agent_attempt_id
                    / "candidate.json"
                )
                evaluation = _evaluate(
                    node_input=agent_input,
                    node_result=node_result,
                    session=session,
                    candidate_path=candidate_path,
                    evaluation_id=f"canary-eval-{sequence:02d}-{arm}-agent",
                )
        finalized, cleanup = _safe_cleanup(session)
        cleanup_succeeded = True
    except BaseException as exc:
        error_class = type(exc).__name__
        if session is not None and not cleanup_succeeded:
            try:
                finalized, cleanup = _safe_cleanup(session)
                cleanup_succeeded = True
            except Exception as cleanup_exc:
                error_class = f"{error_class}+{type(cleanup_exc).__name__}"
                cleanup_succeeded = False
    finally:
        if active:
            deactivate_experiment(thread_id)

    strict_success = bool(
        evaluation is not None and evaluation.strict_reproducible_build_success
    )
    terminal_classification = (
        "arm_error"
        if error_class is not None
        else "strict_success"
        if strict_success
        else "evaluated_failure"
        if evaluation is not None
        else "no_candidate"
    )
    usage = (
        node_result.usage
        if node_result is not None
        else AgentWorkflowUsage(0, 0, 0, 0, 0)
    )
    jev_usage = (
        jev_response["response"]["usage"]
        if jev_response is not None
        else {"input_tokens": None, "output_tokens": None}
    )
    jev_cost = (
        jev_response["response"]["cost_usd"] if jev_response is not None else None
    )
    final_command_count = (
        len(finalized.commands) if finalized is not None else initial_command_count
    )
    result = {
        "schema_version": "forge-jev-end-to-end-canary-arm-result-1.0.0",
        "identity": IDENTITY,
        "manifest_sha256": digest,
        "release_revision": release_revision,
        "sequence": sequence,
        "task_id": task_id,
        "build_system": task["selected_build_system"],
        "fault_type": case["fault_type"],
        "arm": arm,
        "route": route_observation,
        "route_action": route_action,
        "direct_attempted": direct_attempted,
        "direct_action_succeeded": direct_action_succeeded,
        "escalated_agent": escalated,
        "agent_usage": json.loads(json.dumps(asdict(usage))),
        "jev_usage": {
            "model_requests": jev_requests,
            "input_tokens": jev_usage["input_tokens"],
            "output_tokens": jev_usage["output_tokens"],
            "cost_usd": jev_cost,
            "error_class": jev_error_class,
            "response_observed": jev_response is not None,
        },
        "node_status": node_result.node_status if node_result is not None else None,
        "candidate_submitted": node_result.candidate_submitted
        if node_result is not None
        else False,
        "s0_s5": [asdict(layer) for layer in evaluation.layers]
        if evaluation is not None
        else [],
        "strict_reproducible_build_success": strict_success,
        "bitwise_reproducible": evaluation.bitwise_reproducible
        if evaluation is not None
        else None,
        "evaluation_sha256": evaluation.canonical_sha256()
        if evaluation is not None
        else None,
        "session_id": finalized.session_id
        if finalized is not None
        else getattr(session, "session_id", None),
        "session_status": finalized.status
        if finalized is not None
        else getattr(session, "status", None),
        "command_count": final_command_count,
        "cleanup_succeeded": cleanup_succeeded
        and cleanup is not None
        and cleanup.succeeded,
        "zero_managed_resources": cleanup_succeeded,
        "terminal_classification": terminal_classification,
        "error_class": error_class,
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "completed_at": _now(),
    }
    _write_once_json(result_path, result)
    ledger.append(
        "experiment.completed",
        {
            "terminal_classification": terminal_classification,
            "strict_success": strict_success,
            "result_sha256": file_sha256(result_path),
        },
    )
    if not cleanup_succeeded:
        _finish_marker(marker_path, status="failed", error_class=error_class)
        raise CanaryError(f"sequence {sequence} cleanup 未闭合")
    _finish_marker(marker_path, status="completed", error_class=error_class)
    return result


def _batch_totals(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "agent_requests": sum(row["agent_usage"]["model_requests"] for row in results),
        "agent_recorded_tokens": sum(
            row["agent_usage"]["recorded_tokens"] for row in results
        ),
        "jev_requests": sum(row["jev_usage"]["model_requests"] for row in results),
        "jev_input_tokens": sum(
            row["jev_usage"]["input_tokens"] or 0 for row in results
        ),
        "jev_cost_usd": sum(row["jev_usage"]["cost_usd"] or 0.0 for row in results),
    }


def _within_budget(totals: dict[str, Any]) -> bool:
    return (
        totals["agent_requests"] <= TOTAL_AGENT_REQUEST_CEILING
        and totals["agent_recorded_tokens"] <= TOTAL_AGENT_TOKEN_CEILING
        and totals["jev_requests"] <= TOTAL_JEV_REQUEST_CEILING
        and totals["jev_input_tokens"] <= TOTAL_JEV_INPUT_TOKEN_CEILING
        and totals["jev_cost_usd"] <= TOTAL_JEV_COST_CEILING_USD + 1e-12
    )


async def execute_batch() -> dict[str, Any]:
    ready = preflight()
    _qualification_report()
    digest = ready["manifest_sha256"]
    release_revision = ready["git_commit"]
    batch_path = EVIDENCE_ROOT / "batch.json"
    _write_once_json(
        batch_path,
        {
            "schema_version": "forge-jev-end-to-end-canary-batch-1.0.0",
            "identity": IDENTITY,
            "manifest_sha256": digest,
            "release_revision": release_revision,
            "status": "running",
            "completed_arms": 0,
            "error_class": None,
            "updated_at": _now(),
        },
    )
    results: list[dict[str, Any]] = []
    try:
        for sequence, (task_id, arm) in enumerate(SCHEDULE, start=1):
            result = await execute_arm(
                validate_manifest(),
                sequence=sequence,
                task_id=task_id,
                arm=arm,
                release_revision=release_revision,
            )
            results.append(result)
            totals = _batch_totals(results)
            if not _within_budget(totals):
                raise CanaryError("formal canary 总预算越界")
            batch = _load_json(batch_path)
            batch["completed_arms"] = len(results)
            batch["totals"] = totals
            batch["updated_at"] = _now()
            _atomic_json(batch_path, batch)
        batch = _load_json(batch_path)
        batch["status"] = "completed"
        batch["updated_at"] = _now()
        _atomic_json(batch_path, batch)
        return batch
    except BaseException as exc:
        batch = _load_json(batch_path)
        batch["status"] = "failed"
        batch["completed_arms"] = len(results)
        batch["totals"] = _batch_totals(results)
        batch["error_class"] = type(exc).__name__
        batch["updated_at"] = _now()
        _atomic_json(batch_path, batch)
        raise


def _evidence_inventory() -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(EVIDENCE_ROOT).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
        for path in sorted(EVIDENCE_ROOT.rglob("*"))
        if path.is_file()
    ]


def generate_report() -> dict[str, Any]:
    manifest = validate_manifest()
    validate_parents()
    _qualification_report()
    batch = _load_json(EVIDENCE_ROOT / "batch.json")
    rows: list[dict[str, Any]] = []
    for sequence, (task_id, arm) in enumerate(SCHEDULE, start=1):
        arm_dir = _arm_directory(sequence, task_id, arm)
        marker_path = arm_dir / "attempt.json"
        result_path = arm_dir / "result.json"
        ledger_path = arm_dir / "experiment.jsonl"
        if (
            not marker_path.is_file()
            or not result_path.is_file()
            or not ledger_path.is_file()
        ):
            continue
        marker = _load_json(marker_path)
        result = _load_json(result_path)
        ExperimentLedger.verify_path(ledger_path)
        if (
            marker.get("sequence") != sequence
            or marker.get("task_id") != task_id
            or marker.get("arm") != arm
        ):
            raise CanaryError("attempt marker schedule 漂移")
        if (
            result.get("sequence") != sequence
            or result.get("task_id") != task_id
            or result.get("arm") != arm
        ):
            raise CanaryError("arm result schedule 漂移")
        rows.append(result)
    totals = _batch_totals(rows)
    agent_runner.require_zero_managed_resources()
    metrics_complete = all(
        isinstance(row.get("agent_usage", {}).get("model_requests"), int)
        and isinstance(row.get("agent_usage", {}).get("recorded_tokens"), int)
        and isinstance(row.get("jev_usage", {}).get("model_requests"), int)
        and isinstance(row.get("duration_ms"), int)
        and isinstance(row.get("escalated_agent"), bool)
        and isinstance(row.get("strict_reproducible_build_success"), bool)
        for row in rows
    )
    jev_usage_complete = all(
        row["arm"] != "jev_gate_agent"
        or (
            row["jev_usage"]["response_observed"] is True
            and isinstance(row["jev_usage"]["input_tokens"], int)
            and isinstance(row["jev_usage"]["cost_usd"], (int, float))
        )
        for row in rows
    )
    gates = {
        "batch_completed": batch.get("status") == "completed",
        "nine_classified_arms": len(rows) == 9
        and all(row.get("terminal_classification") for row in rows),
        "metrics_complete": metrics_complete and jev_usage_complete,
        "all_cleanup_succeeded": len(rows) == 9
        and all(row.get("cleanup_succeeded") is True for row in rows),
        "within_frozen_budget": _within_budget(totals),
        "zero_managed_resources": True,
        "parent_evidence_unchanged": True,
    }
    passed = all(gates.values())
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "identity": IDENTITY,
        "manifest_sha256": canonical_sha256(manifest),
        "release_revision": batch.get("release_revision"),
        "created_at": _now(),
        "arm_count": len(rows),
        "rows": rows,
        "totals": totals,
        "strict_success_by_arm": {
            arm: {
                "successes": sum(
                    row["strict_reproducible_build_success"]
                    for row in rows
                    if row["arm"] == arm
                ),
                "arms": sum(row["arm"] == arm for row in rows),
            }
            for arm in ARMS
        },
        "routing": {
            "direct_attempts": sum(row["direct_attempted"] for row in rows),
            "direct_action_failures": sum(
                row["direct_attempted"] and not row["direct_action_succeeded"]
                for row in rows
            ),
            "agent_escalations": sum(row["escalated_agent"] for row in rows),
        },
        "gates": gates,
        "passed": passed,
        "decision": "proceed_to_formal_end_to_end_comparison_design"
        if passed
        else "stop_before_formal_comparison",
        "interpretation": manifest["interpretation"],
        "evidence_inventory": _evidence_inventory(),
    }
    if JSON_REPORT_PATH.exists() or MARKDOWN_REPORT_PATH.exists():
        raise CanaryError("formal report 已存在")
    _write_once_json(JSON_REPORT_PATH, report)
    strict_lines = "\n".join(
        f"- `{arm}`：{values['successes']}/{values['arms']} strict success"
        for arm, values in report["strict_success_by_arm"].items()
    )
    _write_once(
        MARKDOWN_REPORT_PATH,
        "# Jev 三臂端到端 canary v2\n\n"
        f"- 决定：`{report['decision']}`\n"
        f"- 完整 arm：`{report['arm_count']}/9`\n"
        f"- Agent 请求 / tokens：`{totals['agent_requests']} / {totals['agent_recorded_tokens']}`\n"
        f"- Jev 请求 / input tokens / 费用：`{totals['jev_requests']} / {totals['jev_input_tokens']} / ${totals['jev_cost_usd']:.8f}`\n"
        f"- 直接动作 / 直接动作失败 / Agent 升级：`{report['routing']['direct_attempts']} / {report['routing']['direct_action_failures']} / {report['routing']['agent_escalations']}`\n\n"
        "## 严格终点\n\n"
        f"{strict_lines}\n\n"
        "## 解释边界\n\n"
        "本结果只判断三臂接线、指标采集、预算与清理是否闭合。三个项目已参与先前资格数据，"
        "因此不能据此主张成功率非劣、成本下降、显著性、模型排名、未见项目泛化或动态预算优越性。\n",
    )
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    bind = sub.add_parser("bind")
    bind.add_argument("--implementation-revision", required=True)
    sub.add_parser("validate")
    sub.add_parser("preflight")
    sub.add_parser("qualify")
    sub.add_parser("run")
    sub.add_parser("report")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "bind":
        print(
            json.dumps(
                bind_identity(args.implementation_revision),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    elif args.command == "validate":
        print(
            json.dumps(
                validate_manifest(), ensure_ascii=False, indent=2, sort_keys=True
            )
        )
    elif args.command == "preflight":
        print(json.dumps(preflight(), ensure_ascii=False, indent=2, sort_keys=True))
    elif args.command == "qualify":
        print(
            json.dumps(
                zero_provider_qualification(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    elif args.command == "run":
        print(
            json.dumps(
                asyncio.run(execute_batch()),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    elif args.command == "report":
        print(
            json.dumps(generate_report(), ensure_ascii=False, indent=2, sort_keys=True)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
