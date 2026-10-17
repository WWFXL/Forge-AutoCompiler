#!/usr/bin/env python3
"""Issue #465 Jev 逐动作安全判断问题分解正式资格实验。"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import statistics
import subprocess
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import httpx2
import jsonschema
from sklearn.metrics import brier_score_loss, roc_auc_score
from typesafe_sdk import RetryPolicy, TypeSafeClient

import forge_jev_action_safety_decomposition_candidate as candidate
import forge_jev_progress_budget_calibration_v1 as historical_execution

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
IDENTITY = "cpp-jev-action-safety-decomposition-v1"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/465"
BRANCH = "yiwei/465-jev-action-safety-decomposition"
SCHEMA_VERSION = "forge-jev-action-safety-decomposition-execution-1.0.0"
REPORT_SCHEMA_VERSION = "forge-jev-action-safety-decomposition-report-1.0.0"

EXECUTION_MANIFEST = (
    REPO_ROOT / "benchmarks/manifests/cpp-jev-action-safety-decomposition-v1.json"
)
EXECUTION_SCHEMA = (
    REPO_ROOT
    / "benchmarks/schemas/forge-jev-action-safety-decomposition-v1.schema.json"
)
AMENDMENT = (
    REPO_ROOT / "benchmarks/preregistrations/cpp-jev-action-safety-decomposition-v1.md"
)
EVIDENCE_ROOT = (
    REPO_ROOT
    / ".compile-sessions/benchmark-evidence-jev-action-safety-decomposition-v1"
)
JSON_REPORT = (
    REPO_ROOT / "benchmarks/reports/cpp-jev-action-safety-decomposition-v1.json"
)
MARKDOWN_REPORT = (
    REPO_ROOT / "benchmarks/reports/cpp-jev-action-safety-decomposition-v1.md"
)
AUDIT_REPORT = (
    REPO_ROOT / "benchmarks/reports/cpp-jev-action-safety-decomposition-v1-audit.md"
)
CREDENTIAL_FILE = REPO_ROOT / "jev-apikey.txt"


class ExecutionError(RuntimeError):
    """正式身份、执行环境或 evidence 生命周期违反冻结协议。"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _git(*argv: str) -> str:
    result = subprocess.run(
        ["git", *argv],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def _git_blob(revision: str, relative_path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative_path}"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        timeout=30,
    )
    return result.stdout


def _canonical_revision(revision: str) -> str:
    resolved = _git("rev-parse", "--verify", f"{revision}^{{commit}}")
    if len(resolved) != 40:
        raise ExecutionError("implementation revision 不是完整 commit")
    return resolved


def _bytes_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_once_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
    except FileExistsError as exc:
        raise ExecutionError(f"create-once 文件已存在: {path}") from exc


def _write_once_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(value)
    except FileExistsError as exc:
        raise ExecutionError(f"create-once 文件已存在: {path}") from exc


def generate_execution_manifest(
    *,
    implementation_revision: str,
    runner_sha256: str,
    candidate_manifest_file_sha256: str,
    candidate_manifest_canonical_sha256: str,
) -> dict[str, Any]:
    parent = candidate.load_contract()
    return {
        "$schema": "../schemas/forge-jev-action-safety-decomposition-v1.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": "forge_jev_action_safety_decomposition_execution",
        "identity": IDENTITY,
        "issue_url": ISSUE_URL,
        "status": "authorized_formal_execution",
        "parent_candidate": {
            "identity": parent["identity"],
            "git_revision": implementation_revision,
            "manifest_path": candidate.DEFAULT_MANIFEST.relative_to(
                REPO_ROOT
            ).as_posix(),
            "manifest_file_sha256": candidate_manifest_file_sha256,
            "manifest_canonical_sha256": candidate_manifest_canonical_sha256,
        },
        "implementation": {
            "git_revision": implementation_revision,
            "runner_path": SCRIPT_PATH.relative_to(REPO_ROOT).as_posix(),
            "runner_sha256": runner_sha256,
            "branch": BRANCH,
        },
        "authorization": {
            "credential_read_authorized": True,
            "provider_calls_authorized": True,
            "jev_calls_authorized": True,
            "agent_calls_authorized": False,
            "maximum_physical_requests": 60,
            "maximum_input_tokens": 400000,
            "maximum_output_tokens": 100000,
            "maximum_model_cost_usd": 0.0168,
            "new_identity_evidence_write_authorized": True,
            "controller_implementation_authorized": False,
            "historical_evidence_write_authorized": False,
        },
        "data_contract": parent["data_contract"],
        "conditions": parent["conditions"],
        "provider_contract": parent["provider_contract"],
        "request_contract": parent["request_contract"],
        "response_contract": {
            **parent["response_contract"],
            "response_observation_written_before_semantic_validation": True,
            "response_observation_contains_raw_provider_body": False,
            "budget_usage_source": "response_observations",
        },
        "calibration_contract": parent["calibration_contract"],
        "budget_fit_contract": parent["budget_fit_contract"],
        "qualification_thresholds": parent["qualification_thresholds"],
        "decision_rule": parent["decision_rule"],
        "stopping_rules": parent["stopping_rules"],
        "provider_schedule": [
            {"condition": "action_noul", "split": "calibration", "requests": 15},
            {
                "condition": "action_card_noul",
                "split": "calibration",
                "requests": 15,
            },
            {"operation": "freeze_calibrators_and_thresholds"},
            {"condition": "action_noul", "split": "evaluation", "requests": 15},
            {
                "condition": "action_card_noul",
                "split": "evaluation",
                "requests": 15,
            },
            {"operation": "single_evaluation_analysis"},
        ],
        "provider_route": {
            "proxy_url": historical_execution.EGRESS_PROXY_URL,
            "container_name": historical_execution.EGRESS_CONTAINER,
            "container_image_id": historical_execution.EGRESS_IMAGE_ID,
            "config_path": str(historical_execution.EGRESS_CONFIG),
            "config_sha256": historical_execution.EGRESS_CONFIG_SHA256,
            "trust_environment": False,
            "shared_github_egress_modified": False,
        },
        "evidence": {
            "root": EVIDENCE_ROOT.relative_to(REPO_ROOT).as_posix(),
            "create_once": True,
            "preserve_failures": True,
            "store_credential": False,
            "store_authorization_header": False,
            "store_raw_provider_body": False,
        },
        "preregistration": {
            "candidate": parent["documents"]["preregistration"]["path"],
            "execution_amendment": AMENDMENT.relative_to(REPO_ROOT).as_posix(),
        },
        "outputs": {
            "json_report": JSON_REPORT.relative_to(REPO_ROOT).as_posix(),
            "markdown_report": MARKDOWN_REPORT.relative_to(REPO_ROOT).as_posix(),
            "audit_report": AUDIT_REPORT.relative_to(REPO_ROOT).as_posix(),
        },
    }


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-jev-action-safety-decomposition-v1.schema.json",
        "title": "Forge Jev action safety decomposition execution v1",
        "const": manifest,
    }


def generate_execution_amendment(manifest: dict[str, Any]) -> str:
    authorization = manifest["authorization"]
    return f"""# Jev 逐动作安全判断问题分解 v1 执行协议

## 身份

- Formal identity：`{IDENTITY}`
- Tracking Issue：[#465]({ISSUE_URL})
- Candidate identity：`{manifest["parent_candidate"]["identity"]}`
- Implementation revision：`{manifest["implementation"]["git_revision"]}`
- Runner SHA-256：`{manifest["implementation"]["runner_sha256"]}`
- Manifest canonical SHA-256：`{candidate.canonical_sha256(manifest)}`

## 授权与预算

研究负责人已授权本 identity 读取仓库根 `jev-apikey.txt`、通过冻结 TypeSafe egress
调用 `jev-1.13.0`，并写入本 identity 的 create-once evidence。credential 和
Authorization header 不得进入日志、evidence、Issue、PR 或 Git。

- `action_noul`：15 calibration + 15 evaluation requests
- `action_card_noul`：15 calibration + 15 evaluation requests
- 最大物理请求：`{authorization["maximum_physical_requests"]}`
- 最大 input tokens：`{authorization["maximum_input_tokens"]}`
- 最大 output tokens：`{authorization["maximum_output_tokens"]}`
- 最大模型费用：`${authorization["maximum_model_cost_usd"]}`
- timeout 30 秒；SDK retry 0

## 固定执行

每个状态在请求前写 attempt，收到响应后先写不含 raw HTTP body 的 observation，再
校验固定模型、六个 Noul、概率、usage 和 request ID。任一失败都保留已写 evidence，
不 retry、replacement 或 backfill。

两个 condition 的 calibration 完成后分别拟合一维 Platt，并在最终最低成本动作
选择器上选择零 observed unsafe direct 且覆盖最大的阈值。随后按冻结顺序运行两个
evaluation split，一次性应用阈值和父 BudgetFit。即使 calibration 未达到最低覆盖，
evaluation 仍按预注册执行，以区分问题分解与 ActionCard 的诊断机制；该结果不能用于
放宽 controller 门禁。

本 identity 不运行历史四选一 evaluation，不修改历史 evidence，不实现 controller，
不支持端到端成功率、成本处理效应、自然失败、时间泛化或开放世界声明。
"""


def bind_execution(implementation_revision: str) -> dict[str, Any]:
    if EXECUTION_MANIFEST.exists() or EXECUTION_SCHEMA.exists() or AMENDMENT.exists():
        raise ExecutionError("execution identity 文件已存在，禁止覆盖")
    revision = _canonical_revision(implementation_revision)
    runner_relative = SCRIPT_PATH.relative_to(REPO_ROOT).as_posix()
    candidate_relative = candidate.DEFAULT_MANIFEST.relative_to(REPO_ROOT).as_posix()
    runner_sha = _bytes_sha256(_git_blob(revision, runner_relative))
    candidate_blob = _git_blob(revision, candidate_relative)
    candidate_file_sha = _bytes_sha256(candidate_blob)
    candidate_value = json.loads(candidate_blob)
    if runner_sha != candidate.file_sha256(SCRIPT_PATH):
        raise ExecutionError("当前 runner 与 implementation revision 不一致")
    if candidate_file_sha != candidate.file_sha256(candidate.DEFAULT_MANIFEST):
        raise ExecutionError(
            "当前 candidate manifest 与 implementation revision 不一致"
        )
    manifest = generate_execution_manifest(
        implementation_revision=revision,
        runner_sha256=runner_sha,
        candidate_manifest_file_sha256=candidate_file_sha,
        candidate_manifest_canonical_sha256=candidate.canonical_sha256(candidate_value),
    )
    schema = generate_schema(manifest)
    jsonschema.Draft202012Validator.check_schema(schema)
    candidate.write_json(EXECUTION_MANIFEST, manifest)
    candidate.write_json(EXECUTION_SCHEMA, schema)
    _write_once_text(AMENDMENT, generate_execution_amendment(manifest))
    return manifest


def validate_execution_manifest() -> dict[str, Any]:
    manifest = candidate.load_json(EXECUTION_MANIFEST)
    implementation = manifest["implementation"]
    revision = _canonical_revision(implementation["git_revision"])
    runner_relative = implementation["runner_path"]
    candidate_relative = manifest["parent_candidate"]["manifest_path"]
    runner_sha = _bytes_sha256(_git_blob(revision, runner_relative))
    candidate_blob = _git_blob(revision, candidate_relative)
    candidate_file_sha = _bytes_sha256(candidate_blob)
    expected = generate_execution_manifest(
        implementation_revision=revision,
        runner_sha256=runner_sha,
        candidate_manifest_file_sha256=candidate_file_sha,
        candidate_manifest_canonical_sha256=candidate.canonical_sha256(
            json.loads(candidate_blob)
        ),
    )
    if manifest != expected:
        raise ExecutionError("execution manifest 无法从冻结 implementation 重建")
    if candidate.file_sha256(SCRIPT_PATH) != runner_sha:
        raise ExecutionError("授权 runner hash 漂移")
    if candidate.file_sha256(candidate.DEFAULT_MANIFEST) != candidate_file_sha:
        raise ExecutionError("授权 candidate manifest hash 漂移")
    schema = candidate.load_json(EXECUTION_SCHEMA)
    if schema != generate_schema(manifest):
        raise ExecutionError("execution const Schema 漂移")
    jsonschema.validate(manifest, schema)
    if AMENDMENT.read_text(encoding="utf-8") != generate_execution_amendment(manifest):
        raise ExecutionError("execution amendment 漂移")
    if version(candidate.parent.SDK_DISTRIBUTION) != candidate.parent.SDK_VERSION:
        raise ExecutionError("TypeSafe SDK 版本漂移")
    candidate.audit_historical_evidence()
    candidate.parent.audit_parent_raw_evidence()
    return manifest


def _assert_revision(manifest: dict[str, Any], *, require_clean: bool) -> None:
    if _git("branch", "--show-current") != BRANCH:
        raise ExecutionError("正式执行分支漂移")
    revision = manifest["implementation"]["git_revision"]
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", revision, "HEAD"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise ExecutionError("HEAD 不包含授权 implementation revision")
    if require_clean:
        dirty = [
            line
            for line in _git("status", "--porcelain").splitlines()
            if "docs/research/2026-10-13-forge-research-progress-defense.html"
            not in line
        ]
        if dirty:
            raise ExecutionError("正式执行前除已知用户 HTML 外工作树必须干净")


def preflight(*, require_clean: bool = True) -> dict[str, Any]:
    manifest = validate_execution_manifest()
    _assert_revision(manifest, require_clean=require_clean)
    egress = historical_execution.validate_egress()
    if not CREDENTIAL_FILE.is_file() or CREDENTIAL_FILE.is_symlink():
        raise ExecutionError("credential 文件不存在或是符号链接")
    if CREDENTIAL_FILE.stat().st_mode & 0o777 != 0o600:
        raise ExecutionError("credential 文件权限必须为 600")
    return {
        "ready": True,
        "identity": IDENTITY,
        "git_commit": _git("rev-parse", "HEAD"),
        "implementation_revision": manifest["implementation"]["git_revision"],
        "manifest_canonical_sha256": candidate.canonical_sha256(manifest),
        "parent_raw_evidence": candidate.parent.audit_parent_raw_evidence(),
        "historical_jev_evidence": candidate.audit_historical_evidence(),
        "egress": egress,
        "credential_file_present": True,
        "credential_file_mode": "600",
        "credential_reads": 0,
        "provider_calls": 0,
        "model_tokens": 0,
        "evidence_exists": EVIDENCE_ROOT.exists(),
    }


def _read_credential() -> str:
    if CREDENTIAL_FILE.is_symlink() or CREDENTIAL_FILE.stat().st_mode & 0o777 != 0o600:
        raise ExecutionError("credential 文件类型或权限漂移")
    key = CREDENTIAL_FILE.read_text(encoding="utf-8").strip()
    if not key or "\n" in key or "\r" in key:
        raise ExecutionError("credential 文件必须只含一行非空 API key")
    return key


def _provider_http_client() -> httpx2.Client:
    return httpx2.Client(
        proxy=historical_execution.EGRESS_PROXY_URL,
        trust_env=False,
        timeout=30.0,
    )


def _stage_directory(condition: str, split: str) -> Path:
    if condition not in candidate.CONDITIONS or split not in candidate.SPLITS:
        raise ExecutionError("未知 Provider stage")
    return EVIDENCE_ROOT / "provider" / condition / split


def _observation_files() -> list[Path]:
    if not EVIDENCE_ROOT.exists():
        return []
    return sorted(EVIDENCE_ROOT.glob("provider/*/*/observations/*.json"))


def _request_files() -> list[Path]:
    if not EVIDENCE_ROOT.exists():
        return []
    return sorted(EVIDENCE_ROOT.glob("provider/*/*/requests/*.json"))


def _attempt_files() -> list[Path]:
    if not EVIDENCE_ROOT.exists():
        return []
    return sorted(EVIDENCE_ROOT.glob("provider/*/*/attempts/*.json"))


def _budget_usage() -> dict[str, Any]:
    input_tokens = 0
    output_tokens = 0
    cost = 0.0
    for path in _observation_files():
        observation = candidate.load_json(path)["response_observation"]
        input_tokens += observation["usage"]["input_tokens"]
        output_tokens += observation["usage"]["output_tokens"]
        cost += observation["cost_usd"]
    return {
        "physical_requests": len(_attempt_files()),
        "completed_response_observations": len(_observation_files()),
        "valid_normalized_responses": len(_request_files()),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "model_cost_usd": cost,
    }


def _enforce_budget(manifest: dict[str, Any], usage: dict[str, Any]) -> None:
    authorization = manifest["authorization"]
    if (
        usage["physical_requests"] > authorization["maximum_physical_requests"]
        or usage["input_tokens"] > authorization["maximum_input_tokens"]
        or usage["output_tokens"] > authorization["maximum_output_tokens"]
        or usage["model_cost_usd"] > authorization["maximum_model_cost_usd"] + 1e-12
    ):
        raise ExecutionError("Provider 硬预算越界")


def _response_observation(response: Any, *, latency_ms: float) -> dict[str, Any]:
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
        raise ExecutionError("Provider observation 缺少合法 usage")
    request_id = getattr(response, "request_id", None)
    if not isinstance(request_id, str) or not request_id:
        raise ExecutionError("Provider observation 缺少 request ID")
    answers = {
        str(name): {
            "type": getattr(answer, "type", None),
            "noul": getattr(answer, "noul", None),
        }
        for name, answer in dict(getattr(response, "answers", {})).items()
    }
    return {
        "model": getattr(response, "model", None),
        "request_id": request_id,
        "answers": answers,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        "cost_usd": input_tokens
        * candidate.parent.INPUT_PRICE_USD_PER_MILLION_TOKENS
        / 1_000_000,
        "latency_ms": float(latency_ms),
    }


def run_provider(condition: str, split: str) -> dict[str, Any]:
    manifest = validate_execution_manifest()
    _assert_revision(manifest, require_clean=True)
    historical_execution.validate_egress()
    if (EVIDENCE_ROOT / "completed.json").exists():
        raise ExecutionError("formal identity 已封存")
    directory = _stage_directory(condition, split)
    if directory.exists():
        raise ExecutionError(f"{condition}/{split} 已存在，禁止 retry/backfill")
    _enforce_budget(manifest, _budget_usage())
    states, _, _ = candidate.split_rows(split)
    directory.mkdir(parents=True, mode=0o700)
    if not (EVIDENCE_ROOT / "identity.json").exists():
        _write_once_json(
            EVIDENCE_ROOT / "identity.json",
            {
                "identity": IDENTITY,
                "issue_url": ISSUE_URL,
                "created_at": _now(),
                "git_commit": _git("rev-parse", "HEAD"),
                "manifest_canonical_sha256": candidate.canonical_sha256(manifest),
            },
        )
    _write_once_json(
        directory / "started.json",
        {
            "identity": IDENTITY,
            "condition": condition,
            "split": split,
            "status": "started",
            "created_at": _now(),
            "budget_before": _budget_usage(),
            "credential_reads": 0,
        },
    )
    credential_reads = 0
    key: str | None = None
    logging.getLogger("typesafe_sdk").disabled = True
    try:
        key = _read_credential()
        credential_reads = 1
        questions = candidate.provider_questions()
        with _provider_http_client() as http_client:
            with TypeSafeClient(
                api_key=key,
                model=candidate.parent.MODEL_ID,
                retry=RetryPolicy(max_retries=0, timeout=30.0),
                base_url=candidate.parent.API_BASE_URL,
                http_client=http_client,
            ) as client:
                for index, state_row in enumerate(states, start=1):
                    if (
                        _budget_usage()["physical_requests"]
                        >= manifest["authorization"]["maximum_physical_requests"]
                    ):
                        raise ExecutionError("Provider request 预算已耗尽")
                    state = candidate.provider_state(state_row, condition)
                    fingerprint = candidate.request_fingerprint(
                        state, questions, condition
                    )
                    stem = f"{index:02d}-{state_row['state_id']}"
                    _write_once_json(
                        directory / "attempts" / f"{stem}.json",
                        {
                            "identity": IDENTITY,
                            "condition": condition,
                            "split": split,
                            "sequence": index,
                            "state_id": state_row["state_id"],
                            "created_at": _now(),
                            "git_commit": _git("rev-parse", "HEAD"),
                            "model": candidate.parent.MODEL_ID,
                            "request_fingerprint": fingerprint,
                        },
                    )
                    started = time.perf_counter()
                    response = client.system_one(state=state, questions=questions)
                    latency_ms = (time.perf_counter() - started) * 1000
                    observation = _response_observation(response, latency_ms=latency_ms)
                    _write_once_json(
                        directory / "observations" / f"{stem}.json",
                        {
                            "identity": IDENTITY,
                            "condition": condition,
                            "split": split,
                            "sequence": index,
                            "state_id": state_row["state_id"],
                            "request_fingerprint": fingerprint,
                            "response_observation": observation,
                        },
                    )
                    normalized = candidate.normalize_response(
                        response, latency_ms=latency_ms
                    )
                    _write_once_json(
                        directory / "requests" / f"{stem}.json",
                        {
                            "identity": IDENTITY,
                            "condition": condition,
                            "split": split,
                            "sequence": index,
                            "state_id": state_row["state_id"],
                            "request_fingerprint": fingerprint,
                            "response": normalized,
                        },
                    )
                    _enforce_budget(manifest, _budget_usage())
        key = None
        rows = action_rows(condition, split, require_completed=False)
        raw = _raw_action_summary(rows)
        _write_once_json(directory / "analysis.json", raw)
        _write_once_json(
            directory / "completed.json",
            {
                "identity": IDENTITY,
                "condition": condition,
                "split": split,
                "status": "completed",
                "created_at": _now(),
                "credential_reads": credential_reads,
                "provider_calls": len(states),
                "budget_after": _budget_usage(),
            },
        )
        return raw
    except Exception as exc:
        key = None
        _write_once_json(
            directory / "failed.json",
            {
                "identity": IDENTITY,
                "condition": condition,
                "split": split,
                "status": "failed",
                "created_at": _now(),
                "error_type": type(exc).__name__,
                "request_id": getattr(exc, "request_id", None),
                "credential_reads": credential_reads,
                "budget_after": _budget_usage(),
            },
        )
        raise


def _responses(
    condition: str, split: str, *, require_completed: bool = True
) -> list[dict[str, Any]]:
    directory = _stage_directory(condition, split)
    if require_completed and not (directory / "completed.json").is_file():
        raise ExecutionError(f"{condition}/{split} Provider stage 未完整封存")
    rows = [
        candidate.load_json(path)
        for path in sorted((directory / "requests").glob("*.json"))
    ]
    if len(rows) != 15:
        raise ExecutionError(f"{condition}/{split} 有效响应不是 15/15")
    request_ids = [row["response"]["request_id"] for row in rows]
    if len(set(request_ids)) != 15:
        raise ExecutionError(f"{condition}/{split} request ID 不唯一")
    return rows


def action_rows(
    condition: str, split: str, *, require_completed: bool = True
) -> list[dict[str, Any]]:
    states, labels, _ = candidate.split_rows(split)
    states_by_id = {row["state_id"]: row for row in states}
    labels_by_id = {row["state_id"]: row for row in labels}
    rows = []
    for response_row in _responses(
        condition, split, require_completed=require_completed
    ):
        state_id = response_row["state_id"]
        state = states_by_id[state_id]
        label = labels_by_id[state_id]
        response = response_row["response"]
        for action in candidate.LOCAL_ACTIONS:
            pair = response["action_pairs"][action]
            rows.append(
                {
                    "condition": condition,
                    "split": split,
                    "state_id": state_id,
                    "project_family": state["project_family"],
                    "build_system": state["build_system"],
                    "action": action,
                    "safe": action in label["safe_actions"],
                    "optimal_action": label["optimal_action"],
                    "primary_probability": pair["primary_probability"],
                    "order_sensitivity_probability": pair[
                        "order_sensitivity_probability"
                    ],
                    "raw_action_score": pair["raw_action_score"],
                    "absolute_order_difference": pair["absolute_order_difference"],
                    "request_id": response["request_id"],
                    "usage": response["usage"],
                    "cost_usd": response["cost_usd"],
                    "latency_ms": response["latency_ms"],
                }
            )
    if len(rows) != 45:
        raise ExecutionError("action rows 不是 45")
    return sorted(rows, key=lambda row: (row["state_id"], row["action"]))


def _raw_action_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    labels = [row["safe"] for row in rows]
    scores = [row["raw_action_score"] for row in rows]
    differences = [row["absolute_order_difference"] for row in rows]
    return {
        "row_count": len(rows),
        "label_counts": dict(
            sorted(Counter(str(value).lower() for value in labels).items())
        ),
        "roc_auc": float(roc_auc_score(labels, scores)),
        "brier": float(brier_score_loss(labels, scores)),
        "mean_absolute_order_difference": statistics.fmean(differences),
        "maximum_absolute_order_difference": max(differences),
        "rows": rows,
    }


def _serialize_platt(estimator: Any) -> dict[str, float]:
    return {
        "coefficient": float(estimator.coef_[0][0]),
        "intercept": float(estimator.intercept_[0]),
    }


def _calibrated_probability(model: dict[str, float], raw: float) -> float:
    clipped = min(
        max(float(raw), candidate.PLATT_EPSILON), 1.0 - candidate.PLATT_EPSILON
    )
    logit = math.log(clipped / (1.0 - clipped))
    value = model["coefficient"] * logit + model["intercept"]
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def calibrate() -> dict[str, Any]:
    path = EVIDENCE_ROOT / "calibration.json"
    if path.exists():
        raise ExecutionError("calibration 已存在，禁止覆盖")
    manifest = validate_execution_manifest()
    results = {}
    for condition in candidate.CONDITIONS:
        rows = action_rows(condition, "calibration")
        estimator = candidate.fit_platt(rows)
        model = _serialize_platt(estimator)
        calibrated_rows = [
            {
                **row,
                "calibrated_probability": _calibrated_probability(
                    model, row["raw_action_score"]
                ),
            }
            for row in rows
        ]
        threshold = candidate.select_zero_error_threshold(
            calibrated_rows, probability_field="calibrated_probability"
        )
        raw_threshold = candidate.select_zero_error_threshold(
            calibrated_rows, probability_field="raw_action_score"
        )
        gates = {
            "complete_valid_responses": len(_responses(condition, "calibration")) == 15,
            "row_count": len(rows) == 45,
            "positive_and_negative_labels": {row["safe"] for row in rows}
            == {False, True},
            "zero_observed_unsafe_direct": threshold["unsafe_direct_count"] == 0,
            "minimum_direct_states": threshold["direct_state_count"]
            >= manifest["qualification_thresholds"]["calibration"][
                "minimum_direct_states"
            ],
            "all_build_systems_direct": all(
                threshold["per_build_system_direct_state_count"][system]
                >= manifest["qualification_thresholds"]["calibration"][
                    "minimum_direct_states_per_build_system"
                ]
                for system in candidate.BUILD_SYSTEMS
            ),
        }
        results[condition] = {
            "model": model,
            "calibrated_threshold": threshold,
            "raw_threshold": raw_threshold,
            "raw_action_summary": _raw_action_summary(rows),
            "gates": gates,
            "passed": all(gates.values()),
        }
    result = {
        "identity": IDENTITY,
        "created_at": _now(),
        "conditions": results,
        "historical_four_way_reference": manifest["conditions"][
            "four_way_choice_frozen_reference"
        ],
    }
    _write_once_json(path, result)
    return result


def _state_selection_rows(
    *, condition: str, split: str, calibration: dict[str, Any]
) -> list[dict[str, Any]]:
    rows = action_rows(condition, split)
    model = calibration["model"]
    threshold = calibration["calibrated_threshold"]["threshold"]
    labels = {row["state_id"]: row for row in candidate.split_rows(split)[1]}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        enriched = {
            **row,
            "calibrated_probability": _calibrated_probability(
                model, row["raw_action_score"]
            ),
        }
        grouped[row["state_id"]].append(enriched)
    selections = []
    for state_id, state_rows in sorted(grouped.items()):
        label = labels[state_id]
        selected = candidate.select_action(
            state_rows,
            probability_field="calibrated_probability",
            threshold=threshold,
        )
        selections.append(
            {
                "state_id": state_id,
                "project_family": state_rows[0]["project_family"],
                "build_system": state_rows[0]["build_system"],
                "selected_action": selected,
                "safe_actions": label["safe_actions"],
                "optimal_action": label["optimal_action"],
                "direct": selected in candidate.LOCAL_ACTIONS,
                "safe_selected": selected in label["safe_actions"],
                "exact_optimal": selected == label["optimal_action"],
                "selected_probability": next(
                    (
                        row["calibrated_probability"]
                        for row in state_rows
                        if row["action"] == selected
                    ),
                    None,
                ),
                "action_rows": state_rows,
            }
        )
    return selections


def _selection_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    direct = [row for row in rows if row["direct"]]
    wrong = [row for row in direct if not row["safe_selected"]]
    per_system = {}
    for system in candidate.BUILD_SYSTEMS:
        system_rows = [row for row in rows if row["build_system"] == system]
        system_direct = [row for row in system_rows if row["direct"]]
        per_system[system] = {
            "state_count": len(system_rows),
            "direct_state_count": len(system_direct),
            "wrong_direct_count": sum(
                not row["safe_selected"] for row in system_direct
            ),
            "exact_optimal_action_count": sum(
                row["exact_optimal"] for row in system_rows
            ),
        }
    return {
        "state_count": len(rows),
        "direct_state_count": len(direct),
        "wrong_direct_count": len(wrong),
        "wrong_direct_risk": len(wrong) / len(direct) if direct else None,
        "safe_selected_action_count": sum(row["safe_selected"] for row in rows),
        "exact_optimal_action_count": sum(row["exact_optimal"] for row in rows),
        "selected_action_counts": dict(
            sorted(Counter(row["selected_action"] for row in rows).items())
        ),
        "per_build_system": per_system,
        "rows": rows,
    }


def _route_summary(
    selections: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    by_state = {row["state_id"]: row for row in selections}
    rows = []
    for decision in decisions:
        selection = by_state[decision["state_id"]]
        route = candidate.budget_fit_route(
            selected_action=selection["selected_action"],
            remaining_budget=decision["remaining_budget"],
            manifest=manifest,
        )
        correct = route["route"] == decision["optimal_route"] and (
            route["route"] != "direct" or route["action"] == decision["optimal_action"]
        )
        rows.append(
            {
                "decision_id": decision["decision_id"],
                "state_id": decision["state_id"],
                "build_system": decision["build_system"],
                "budget_profile": decision["budget_profile"],
                "selected_action": selection["selected_action"],
                "predicted_route": route["route"],
                "predicted_action": route["action"],
                "route_gate": route["gate"],
                "optimal_route": decision["optimal_route"],
                "optimal_action": decision["optimal_action"],
                "correct": correct,
            }
        )
    direct = [row for row in rows if row["predicted_route"] == "direct"]
    return {
        "decision_count": len(rows),
        "joint_correct": sum(row["correct"] for row in rows),
        "route_accuracy": sum(
            row["predicted_route"] == row["optimal_route"] for row in rows
        )
        / len(rows),
        "direct_count": len(direct),
        "wrong_direct_count": sum(not row["correct"] for row in direct),
        "wrong_direct_risk": (
            sum(not row["correct"] for row in direct) / len(direct) if direct else None
        ),
        "per_build_system_joint_correct": {
            system: sum(row["correct"] for row in rows if row["build_system"] == system)
            for system in candidate.BUILD_SYSTEMS
        },
        "rows": rows,
    }


def evaluate() -> dict[str, Any]:
    path = EVIDENCE_ROOT / "evaluation.json"
    if path.exists():
        raise ExecutionError("evaluation 已存在，禁止覆盖")
    manifest = validate_execution_manifest()
    calibration = candidate.load_json(EVIDENCE_ROOT / "calibration.json")
    _, _, decisions = candidate.split_rows("evaluation")
    results = {}
    for condition in candidate.CONDITIONS:
        cal = calibration["conditions"][condition]
        selections = _state_selection_rows(
            condition=condition, split="evaluation", calibration=cal
        )
        selection = _selection_summary(selections)
        routes = _route_summary(selections, decisions, manifest)
        thresholds = manifest["qualification_thresholds"]
        core_gates = {
            "calibration_passed": cal["passed"],
            "complete_valid_responses": len(_responses(condition, "evaluation"))
            == thresholds["evaluation_core"]["valid_responses"],
            "minimum_direct_states": selection["direct_state_count"]
            >= thresholds["evaluation_core"]["minimum_direct_states"],
            "all_build_systems_direct": all(
                selection["per_build_system"][system]["direct_state_count"]
                >= thresholds["evaluation_core"][
                    "minimum_direct_states_per_build_system"
                ]
                for system in candidate.BUILD_SYSTEMS
            ),
            "maximum_wrong_direct_risk": selection["wrong_direct_risk"] is not None
            and selection["wrong_direct_risk"]
            <= thresholds["evaluation_core"]["maximum_wrong_direct_risk"],
            "minimum_exact_optimal_actions": selection["exact_optimal_action_count"]
            >= thresholds["evaluation_core"]["minimum_exact_optimal_actions"],
            "minimum_joint_correct": routes["joint_correct"]
            >= thresholds["evaluation_core"]["minimum_joint_correct"],
            "minimum_joint_correct_per_build_system": all(
                routes["per_build_system_joint_correct"][system]
                >= thresholds["evaluation_core"][
                    "minimum_joint_correct_per_build_system"
                ]
                for system in candidate.BUILD_SYSTEMS
            ),
        }
        match = {
            "minimum_exact_optimal_actions": selection["exact_optimal_action_count"]
            >= thresholds["match_tfidf"]["minimum_exact_optimal_actions"],
            "minimum_joint_correct": routes["joint_correct"]
            >= thresholds["match_tfidf"]["minimum_joint_correct"],
            "maximum_wrong_direct": routes["wrong_direct_count"]
            <= thresholds["match_tfidf"]["maximum_wrong_direct"],
        }
        incremental = {
            "action_exact": selection["exact_optimal_action_count"]
            >= thresholds["incremental_over_tfidf"]["option_action_exact"],
            "joint_correct": routes["joint_correct"]
            >= thresholds["incremental_over_tfidf"]["option_joint_correct"],
            "coverage_at_matched_joint": routes["joint_correct"]
            >= thresholds["incremental_over_tfidf"]["option_coverage_joint_correct"]
            and routes["direct_count"]
            > thresholds["incremental_over_tfidf"][
                "option_coverage_direct_decisions_exclusive"
            ],
        }
        results[condition] = {
            "raw_action_summary": _raw_action_summary(
                action_rows(condition, "evaluation")
            ),
            "selection": selection,
            "budgetfit": routes,
            "core_gates": core_gates,
            "core_passed": all(core_gates.values()),
            "tfidf_match_gates": match,
            "tfidf_matched": all(match.values()),
            "incremental_gates": incremental,
            "incremental_signal": all(match.values()) and any(incremental.values()),
        }
    plain = results["action_noul"]
    cards = results["action_card_noul"]
    if plain["core_passed"]:
        mechanism_decision = "supports_problem_decomposition_without_action_cards"
    elif cards["core_passed"]:
        mechanism_decision = "supports_action_card_context_as_necessary"
    else:
        mechanism_decision = "stop_jev_action_safety_before_controller"
    qualified = [row for row in results.values() if row["core_passed"]]
    if not qualified:
        decision = "stop_jev_action_safety_before_controller"
    elif not any(row["tfidf_matched"] for row in qualified):
        decision = "keep_jev_as_implementation_or_ablation_only"
    elif not any(row["incremental_signal"] for row in qualified):
        decision = "no_increment_over_tfidf"
    else:
        decision = "supports_jev_action_safety_increment_candidate"
    result = {
        "identity": IDENTITY,
        "created_at": _now(),
        "conditions": results,
        "baselines": {
            "tfidf_budgetfit": manifest["data_contract"]["split"]["evaluation"][
                "tfidf_budgetfit"
            ],
            "tfidf_action_top1_correct": 12,
            "rule_gate": manifest["data_contract"]["split"]["evaluation"]["rule_gate"],
        },
        "mechanism_decision": mechanism_decision,
        "decision": decision,
        "passed": decision == "supports_jev_action_safety_increment_candidate",
    }
    _write_once_json(path, result)
    return result


def _credential_scan() -> dict[str, Any]:
    key = _read_credential().encode()
    violations = []
    for path in sorted(EVIDENCE_ROOT.rglob("*")):
        if not path.is_file():
            continue
        payload = path.read_bytes()
        if key in payload or b"Authorization:" in payload or b"Bearer " in payload:
            violations.append(path.relative_to(EVIDENCE_ROOT).as_posix())
    if violations:
        raise ExecutionError(f"evidence credential/header 扫描失败: {violations}")
    return {
        "passed": True,
        "credential_exact_value_matches": 0,
        "authorization_header_matches": 0,
        "credential_content_reads_for_scan": 1,
    }


def _evidence_inventory() -> list[dict[str, Any]]:
    excluded = {"inventory.json", "completed.json"}
    return [
        {
            "path": path.relative_to(EVIDENCE_ROOT).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": candidate.file_sha256(path),
        }
        for path in sorted(EVIDENCE_ROOT.rglob("*"))
        if path.is_file() and path.relative_to(EVIDENCE_ROOT).as_posix() not in excluded
    ]


def _seal_evidence(result: dict[str, Any]) -> dict[str, Any]:
    if (EVIDENCE_ROOT / "completed.json").exists() or (
        EVIDENCE_ROOT / "inventory.json"
    ).exists():
        raise ExecutionError("formal evidence 已封存，禁止覆盖")
    candidate.audit_historical_evidence()
    candidate.parent.audit_parent_raw_evidence()
    _write_once_json(EVIDENCE_ROOT / "result.json", result)
    credential_scan = _credential_scan()
    rows = _evidence_inventory()
    inventory = {
        "identity": IDENTITY,
        "files": rows,
        "file_count": len(rows),
        "total_bytes": sum(row["size_bytes"] for row in rows),
        "canonical_sha256": candidate.canonical_sha256(rows),
    }
    _write_once_json(EVIDENCE_ROOT / "inventory.json", inventory)
    marker = {
        "identity": IDENTITY,
        "status": "completed",
        "completed_at": _now(),
        "decision": result["decision"],
        "mechanism_decision": result["mechanism_decision"],
        "inventory_canonical_sha256": inventory["canonical_sha256"],
        "credential_scan": credential_scan,
        "historical_evidence_modified": False,
        "zero_managed_resources": True,
    }
    _write_once_json(EVIDENCE_ROOT / "completed.json", marker)
    return {"inventory": inventory, "marker": marker}


def _markdown_report(report: dict[str, Any]) -> str:
    evaluation = report["evaluation"]
    calibration = report["calibration"]
    lines = [
        "# Jev 逐动作安全判断问题分解 v1 报告",
        "",
        "## 正式身份",
        "",
        f"- Identity：`{IDENTITY}`",
        f"- Tracking Issue：[#465]({ISSUE_URL})",
        f"- Implementation revision：`{report['implementation_revision']}`",
        f"- 决定：`{report['decision']}`",
        f"- 机制判断：`{report['mechanism_decision']}`",
        "",
        "## 结果",
        "",
        "| 条件 | Cal direct | Eval direct | Eval wrong | Exact | Joint | TF-IDF match | Increment |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for condition in candidate.CONDITIONS:
        cal = calibration["conditions"][condition]
        row = evaluation["conditions"][condition]
        lines.append(
            f"| `{condition}` | {cal['calibrated_threshold']['direct_state_count']}/15 | "
            f"{row['selection']['direct_state_count']}/15 | "
            f"{row['selection']['wrong_direct_count']} | "
            f"{row['selection']['exact_optimal_action_count']}/15 | "
            f"{row['budgetfit']['joint_correct']}/45 | "
            f"{row['tfidf_matched']} | {row['incremental_signal']} |"
        )
    lines.extend(
        [
            "",
            "## Provider 用量",
            "",
            f"- 物理请求：{report['budget']['physical_requests']}/60",
            f"- Input tokens：{report['budget']['input_tokens']}",
            f"- Output tokens：{report['budget']['output_tokens']}",
            f"- 费用：`${report['budget']['model_cost_usd']:.9f}`",
            "",
            "## 解释边界",
            "",
            "本实验比较冻结受控构建状态上的逐动作 Noul 与 ActionCard 增强，并复用父"
            " BudgetFit。它不估计 controller 的端到端成功率、成本处理效应、自然失败、"
            "时间泛化、开放世界或通用模型排名。四选一结果只来自 #463 冻结 calibration，"
            "本 identity 没有补齐其 evaluation。",
            "",
        ]
    )
    return "\n".join(lines)


def build_report() -> dict[str, Any]:
    if JSON_REPORT.exists() or MARKDOWN_REPORT.exists():
        raise ExecutionError("正式报告已存在，禁止覆盖")
    manifest = validate_execution_manifest()
    calibration = candidate.load_json(EVIDENCE_ROOT / "calibration.json")
    evaluation = candidate.load_json(EVIDENCE_ROOT / "evaluation.json")
    budget = _budget_usage()
    _enforce_budget(manifest, budget)
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "document_type": "forge_jev_action_safety_decomposition_report",
        "identity": IDENTITY,
        "issue_url": ISSUE_URL,
        "created_at": _now(),
        "git_commit": _git("rev-parse", "HEAD"),
        "implementation_revision": manifest["implementation"]["git_revision"],
        "manifest_canonical_sha256": candidate.canonical_sha256(manifest),
        "budget": budget,
        "calibration": calibration,
        "evaluation": evaluation,
        "mechanism_decision": evaluation["mechanism_decision"],
        "decision": evaluation["decision"],
        "passed": evaluation["passed"],
        "interpretation": {
            "supports": "frozen controlled state action-safety decomposition and project-family holdout",
            "does_not_support": [
                "controller treatment effect",
                "strict success noninferiority",
                "end-to-end cost reduction",
                "natural failure generalization",
                "time generalization",
                "open-world routing",
                "general model ranking",
            ],
            "historical_four_way_evaluation_requests": 0,
        },
    }
    sealed = _seal_evidence(report)
    report["evidence"] = {
        "root": manifest["evidence"]["root"],
        "file_count": sealed["inventory"]["file_count"],
        "total_bytes": sealed["inventory"]["total_bytes"],
        "inventory_canonical_sha256": sealed["inventory"]["canonical_sha256"],
        "marker_sha256": candidate.file_sha256(EVIDENCE_ROOT / "completed.json"),
        "credential_scan": sealed["marker"]["credential_scan"],
        "parent_outcome_inventory_unchanged": True,
        "historical_jev_inventory_unchanged": True,
        "zero_managed_resources": True,
    }
    _write_once_json(JSON_REPORT, report)
    _write_once_text(MARKDOWN_REPORT, _markdown_report(report))
    return report


def audit() -> dict[str, Any]:
    if AUDIT_REPORT.exists():
        raise ExecutionError("audit 报告已存在，禁止覆盖")
    report = candidate.load_json(JSON_REPORT)
    inventory = candidate.load_json(EVIDENCE_ROOT / "inventory.json")
    marker = candidate.load_json(EVIDENCE_ROOT / "completed.json")
    observed_rows = _evidence_inventory()
    valid = (
        inventory["files"] == observed_rows
        and inventory["canonical_sha256"] == candidate.canonical_sha256(observed_rows)
        and marker["inventory_canonical_sha256"] == inventory["canonical_sha256"]
        and report["evidence"]["inventory_canonical_sha256"]
        == inventory["canonical_sha256"]
        and report["budget"] == _budget_usage()
        and candidate.audit_historical_evidence()["valid"]
        and candidate.parent.audit_parent_raw_evidence()["valid"]
    )
    text = f"""# Jev 逐动作安全判断问题分解 v1 独立审计

- Identity：`{IDENTITY}`
- 决定：`{report["decision"]}`
- 机制判断：`{report["mechanism_decision"]}`
- Evidence：{inventory["file_count"]} files / {inventory["total_bytes"]} bytes
- Inventory canonical SHA-256：`{inventory["canonical_sha256"]}`
- Provider requests：{report["budget"]["physical_requests"]}/60
- Input/output tokens：{report["budget"]["input_tokens"]} / {report["budget"]["output_tokens"]}
- 费用：`${report["budget"]["model_cost_usd"]:.9f}`
- Credential/header 命中：0
- 历史 outcome 与 #463 Jev evidence：只读 hash 复核通过
- Audit valid：`{str(valid).lower()}`

审计重算 inventory、budget usage、marker/report 绑定和两个父 evidence hash。它不重发
Provider 请求，不修改 formal evidence，也不扩大报告的解释边界。
"""
    _write_once_text(AUDIT_REPORT, text)
    return {
        "valid": valid,
        "inventory_canonical_sha256": inventory["canonical_sha256"],
        "provider_requests": report["budget"]["physical_requests"],
        "decision": report["decision"],
        "mechanism_decision": report["mechanism_decision"],
    }


def run_all() -> dict[str, Any]:
    preflight(require_clean=True)
    for condition in candidate.CONDITIONS:
        run_provider(condition, "calibration")
    calibration = calibrate()
    for condition in candidate.CONDITIONS:
        run_provider(condition, "evaluation")
    evaluation = evaluate()
    report = build_report()
    audited = audit()
    return {
        "calibration": {
            condition: calibration["conditions"][condition]["passed"]
            for condition in candidate.CONDITIONS
        },
        "evaluation": {
            condition: evaluation["conditions"][condition]["core_passed"]
            for condition in candidate.CONDITIONS
        },
        "decision": report["decision"],
        "mechanism_decision": report["mechanism_decision"],
        "audit": audited,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    bind = subparsers.add_parser("bind-execution")
    bind.add_argument("--implementation-revision", required=True)
    subparsers.add_parser("validate")
    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--allow-dirty", action="store_true")
    provider = subparsers.add_parser("run-provider")
    provider.add_argument("--condition", choices=candidate.CONDITIONS, required=True)
    provider.add_argument("--split", choices=candidate.SPLITS, required=True)
    subparsers.add_parser("calibrate")
    subparsers.add_parser("evaluate")
    subparsers.add_parser("report")
    subparsers.add_parser("audit")
    subparsers.add_parser("run-all")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "bind-execution":
        result = bind_execution(args.implementation_revision)
    elif args.command == "validate":
        result = validate_execution_manifest()
    elif args.command == "preflight":
        result = preflight(require_clean=not args.allow_dirty)
    elif args.command == "run-provider":
        result = run_provider(args.condition, args.split)
    elif args.command == "calibrate":
        result = calibrate()
    elif args.command == "evaluate":
        result = evaluate()
    elif args.command == "report":
        result = build_report()
    elif args.command == "audit":
        result = audit()
    else:
        result = run_all()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
