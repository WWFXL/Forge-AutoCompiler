#!/usr/bin/env python3
"""Issue #463 进展预算感知 Jev 正式离线校准实验。"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import statistics
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import httpx2
import jsonschema
from typesafe_sdk import RetryPolicy, TypeSafeClient

import forge_jev_progress_budget_calibration_candidate as candidate

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
IDENTITY = "cpp-jev-progress-budget-calibration-v1"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/463"
BRANCH = "yiwei/463-jev-progress-budget-calibration-execution"
SCHEMA_VERSION = "forge-jev-progress-budget-calibration-execution-1.0.0"
REPORT_SCHEMA_VERSION = "forge-jev-progress-budget-calibration-report-1.0.0"

CANDIDATE_REVISION = "f5f76db338b9f87bf3916417301f363d50e88213"
CANDIDATE_MANIFEST = candidate.DEFAULT_MANIFEST
CANDIDATE_MANIFEST_FILE_SHA256 = (
    "4df74f308149887bcb0e8f38f53e7f55be3de8daf839313e3cafcaca74b66345"
)
CANDIDATE_MANIFEST_CANONICAL_SHA256 = (
    "39b1438270768f63de515827c65bed1ad15e7dd1f4a4175ee9670ba6205cb9c5"
)
EXECUTION_MANIFEST = (
    REPO_ROOT / "benchmarks/manifests/cpp-jev-progress-budget-calibration-v1.json"
)
EXECUTION_SCHEMA = (
    REPO_ROOT
    / "benchmarks/schemas/forge-jev-progress-budget-calibration-v1.schema.json"
)
AMENDMENT = (
    REPO_ROOT / "benchmarks/preregistrations/cpp-jev-progress-budget-calibration-v1.md"
)
EVIDENCE_ROOT = (
    REPO_ROOT
    / ".compile-sessions/benchmark-evidence-jev-progress-budget-calibration-v1"
)
JSON_REPORT = (
    REPO_ROOT / "benchmarks/reports/cpp-jev-progress-budget-calibration-v1.json"
)
MARKDOWN_REPORT = (
    REPO_ROOT / "benchmarks/reports/cpp-jev-progress-budget-calibration-v1.md"
)
CREDENTIAL_FILE = REPO_ROOT / "jev-apikey.txt"

EGRESS_CONTAINER = "forge-typesafe-egress"
EGRESS_PROXY_URL = "http://127.0.0.1:17891"
EGRESS_CONFIG = Path("/home/yiwei/services/forge-egress/config/typesafe-config.yaml")
EGRESS_CONFIG_SHA256 = (
    "61ed936fe28f5cc7631fbd20c3fe92a93230db16d2bd5dee07829119a05d37ea"
)
EGRESS_IMAGE_ID = (
    "sha256:30afbbe303155d74537b0e3061ffda5e5e64746a6b41ad32991dd63ab9984ce0"
)
EGRESS_HOST_PORT = "17891"
EGRESS_CONTAINER_PORT = "7890/tcp"


class ExecutionError(RuntimeError):
    """正式身份、执行环境或证据生命周期违反冻结协议。"""


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
) -> dict[str, Any]:
    parent = candidate.load_contract()
    if candidate.file_sha256(CANDIDATE_MANIFEST) != CANDIDATE_MANIFEST_FILE_SHA256:
        raise ExecutionError("candidate manifest 文件 SHA-256 漂移")
    if candidate.canonical_sha256(parent) != CANDIDATE_MANIFEST_CANONICAL_SHA256:
        raise ExecutionError("candidate manifest canonical SHA-256 漂移")
    return {
        "$schema": "../schemas/forge-jev-progress-budget-calibration-v1.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": "forge_jev_progress_budget_calibration_execution",
        "identity": IDENTITY,
        "issue_url": ISSUE_URL,
        "status": "authorized_formal_execution",
        "parent_candidate": {
            "identity": parent["identity"],
            "git_revision": CANDIDATE_REVISION,
            "manifest_path": CANDIDATE_MANIFEST.relative_to(REPO_ROOT).as_posix(),
            "manifest_file_sha256": CANDIDATE_MANIFEST_FILE_SHA256,
            "manifest_canonical_sha256": CANDIDATE_MANIFEST_CANONICAL_SHA256,
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
            "maximum_physical_requests": 30,
            "maximum_input_tokens": 200000,
            "maximum_output_tokens": 50000,
            "maximum_model_cost_usd": 0.0084,
            "new_identity_evidence_write_authorized": True,
            "controller_implementation_authorized": False,
            "historical_evidence_write_authorized": False,
        },
        "data_contract": parent["data_contract"],
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
        "decisions": parent["decisions"],
        "stopping_rules": parent["stopping_rules"],
        "provider_schedule": {
            "calibration_requests": 15,
            "evaluation_requests": 15,
            "evaluation_requires_passed_calibration": True,
            "evaluation_single_analysis_only": True,
        },
        "provider_route": {
            "proxy_url": EGRESS_PROXY_URL,
            "container_name": EGRESS_CONTAINER,
            "container_image_id": EGRESS_IMAGE_ID,
            "container_port": EGRESS_CONTAINER_PORT,
            "host_port": EGRESS_HOST_PORT,
            "config_path": str(EGRESS_CONFIG),
            "config_sha256": EGRESS_CONFIG_SHA256,
            "config_mode": "600",
            "route": "DOMAIN-SUFFIX,typesafe.ai,TypeSafeProxy",
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
            "parent": parent["documents"]["preregistration"]["path"],
            "execution_amendment": AMENDMENT.relative_to(REPO_ROOT).as_posix(),
        },
        "outputs": {
            "json_report": JSON_REPORT.relative_to(REPO_ROOT).as_posix(),
            "markdown_report": MARKDOWN_REPORT.relative_to(REPO_ROOT).as_posix(),
        },
    }


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-jev-progress-budget-calibration-v1.schema.json",
        "title": "Forge Jev progress-budget calibration execution v1",
        "const": manifest,
    }


def generate_execution_amendment(manifest: dict[str, Any]) -> str:
    authorization = manifest["authorization"]
    return f"""# 进展预算感知 Jev 正式离线校准 v1 执行协议

## 身份

- Formal identity：`{IDENTITY}`
- Tracking Issue：[#463]({ISSUE_URL})
- Parent candidate：`{manifest["parent_candidate"]["identity"]}`
- Parent revision：`{manifest["parent_candidate"]["git_revision"]}`
- Implementation revision：`{manifest["implementation"]["git_revision"]}`
- Runner SHA-256：`{manifest["implementation"]["runner_sha256"]}`
- Manifest canonical SHA-256：`{candidate.canonical_sha256(manifest)}`

## 授权与硬预算

研究负责人已授权本 identity 读取仓库根 `jev-apikey.txt`、通过冻结 TypeSafe
egress 调用固定 `jev-1.13.0`，并写入本 identity 的 create-once evidence。
credential 和 Authorization header 不得进入日志、evidence、Issue、PR 或 Git。

- Calibration：15 个状态，最多 15 个物理请求
- Evaluation：仅 calibration 门槛全部通过后执行 15 个状态，最多 15 个物理请求
- 总物理请求：`{authorization["maximum_physical_requests"]}`
- 最大 input tokens：`{authorization["maximum_input_tokens"]}`
- 最大 output tokens：`{authorization["maximum_output_tokens"]}`
- 最大模型费用：`${authorization["maximum_model_cost_usd"]}`
- timeout：30 秒；SDK retry：0

## 执行与停止边界

每个状态在请求前写 attempt，收到响应后先写不含 raw body 的 observation，再做
模型版本、Choice、概率、usage 和顺序语义校验。任何失败、部分响应和用量均保留。
禁止 retry、replacement 和 backfill。Calibration 必须 15/15 有效、45 行标签同时
含正负类，并在零 observed unsafe direct 下覆盖至少 5/15 且三个构建系统各至少
1 个状态；否则决定为 `stop_before_progress_budget_evaluation`，不得执行 evaluation。

Evaluation 只运行和分析一次。核心门槛失败时决定为
`stop_jev_progress_budget_routing_before_controller`；只超过 RuleGate 而未达到冻结
TF-IDF 增量门槛时决定为
`stop_jev_as_incremental_component_keep_semantic_budget_method`；全部通过时决定为
`proceed_to_frozen_response_progress_budget_controller_replay_design`。

本 identity 不授权修改任何历史 evidence，不授权 evaluation 后调整 prompt、split、
模型、阈值或标签，也不授权 controller 实现。结果只支持冻结受控状态上的离线动作
选择、校准和预算路由判断，不支持端到端成功率、成本处理效应、显著性、跨时间泛化
或自然失败总体声明。
"""


def bind_execution(implementation_revision: str) -> dict[str, Any]:
    if EXECUTION_MANIFEST.exists() or EXECUTION_SCHEMA.exists() or AMENDMENT.exists():
        raise ExecutionError("execution identity 文件已存在，禁止覆盖")
    implementation_revision = _canonical_revision(implementation_revision)
    relative = SCRIPT_PATH.relative_to(REPO_ROOT).as_posix()
    runner_sha = _bytes_sha256(_git_blob(implementation_revision, relative))
    if runner_sha != candidate.file_sha256(SCRIPT_PATH):
        raise ExecutionError("当前 runner 与 implementation revision 不一致")
    manifest = generate_execution_manifest(
        implementation_revision=implementation_revision,
        runner_sha256=runner_sha,
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
    expected = generate_execution_manifest(
        implementation_revision=implementation["git_revision"],
        runner_sha256=implementation["runner_sha256"],
    )
    if manifest != expected:
        raise ExecutionError("execution manifest 无法从冻结 candidate 确定重建")
    if candidate.file_sha256(SCRIPT_PATH) != implementation["runner_sha256"]:
        raise ExecutionError("授权 runner hash 漂移")
    schema = candidate.load_json(EXECUTION_SCHEMA)
    if schema != generate_schema(manifest):
        raise ExecutionError("execution const Schema 漂移")
    jsonschema.validate(manifest, schema)
    if AMENDMENT.read_text(encoding="utf-8") != generate_execution_amendment(manifest):
        raise ExecutionError("execution amendment 漂移")
    if version(candidate.SDK_DISTRIBUTION) != candidate.SDK_VERSION:
        raise ExecutionError("TypeSafe SDK 版本漂移")
    candidate.audit_parent_raw_evidence()
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


def validate_egress() -> dict[str, Any]:
    if not EGRESS_CONFIG.is_file() or EGRESS_CONFIG.stat().st_mode & 0o777 != 0o600:
        raise ExecutionError("TypeSafe egress 配置不存在或权限漂移")
    if candidate.file_sha256(EGRESS_CONFIG) != EGRESS_CONFIG_SHA256:
        raise ExecutionError("TypeSafe egress 配置 hash 漂移")
    result = subprocess.run(
        ["docker", "inspect", EGRESS_CONTAINER],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise ExecutionError("TypeSafe egress container 不可用")
    inspected = json.loads(result.stdout)
    if len(inspected) != 1:
        raise ExecutionError("TypeSafe egress inspect 结果漂移")
    container = inspected[0]
    host = container["HostConfig"]
    binding = host["PortBindings"].get(EGRESS_CONTAINER_PORT)
    if (
        container["State"]["Running"] is not True
        or container["Image"] != EGRESS_IMAGE_ID
        or binding != [{"HostIp": "127.0.0.1", "HostPort": EGRESS_HOST_PORT}]
        or host["ReadonlyRootfs"] is not True
        or set(host.get("CapDrop") or []) != {"ALL"}
        or "no-new-privileges:true" not in (host.get("SecurityOpt") or [])
        or host["Privileged"] is not False
    ):
        raise ExecutionError("TypeSafe egress runtime 合同漂移")
    return {
        "passed": True,
        "container": EGRESS_CONTAINER,
        "image_id": EGRESS_IMAGE_ID,
        "proxy_url": EGRESS_PROXY_URL,
        "config_sha256": EGRESS_CONFIG_SHA256,
        "config_mode": "600",
        "read_only_rootfs": True,
        "cap_drop_all": True,
        "no_new_privileges": True,
    }


def preflight(*, require_clean: bool = True) -> dict[str, Any]:
    manifest = validate_execution_manifest()
    _assert_revision(manifest, require_clean=require_clean)
    egress = validate_egress()
    if not CREDENTIAL_FILE.is_file() or CREDENTIAL_FILE.is_symlink():
        raise ExecutionError("credential 文件不存在或是符号链接")
    credential_mode = CREDENTIAL_FILE.stat().st_mode & 0o777
    if credential_mode != 0o600:
        raise ExecutionError("credential 文件权限必须为 600")
    return {
        "ready": True,
        "identity": IDENTITY,
        "git_commit": _git("rev-parse", "HEAD"),
        "candidate_manifest_canonical_sha256": CANDIDATE_MANIFEST_CANONICAL_SHA256,
        "parent_raw_evidence": candidate.audit_parent_raw_evidence(),
        "egress": egress,
        "credential_file_present": True,
        "credential_file_mode": "600",
        "credential_reads": 0,
        "provider_calls": 0,
        "model_tokens": 0,
        "evidence_exists": EVIDENCE_ROOT.exists(),
    }


def _split_rows(
    split: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if split not in candidate.SPLITS:
        raise ExecutionError(f"未知 split: {split}")
    report = candidate.load_json(candidate.PARENT_REPORT)
    state_ids = set(
        candidate.load_contract()["data_contract"]["split"][split]["state_ids"]
    )
    states = sorted(
        (row for row in report["states"] if row["state_id"] in state_ids),
        key=lambda row: row["state_id"],
    )
    labels = sorted(
        (
            row
            for row in report["analysis"]["action_labels"]
            if row["state_id"] in state_ids
        ),
        key=lambda row: row["state_id"],
    )
    decisions = sorted(
        (
            row
            for row in report["analysis"]["budget_decisions"]
            if row["state_id"] in state_ids
        ),
        key=lambda row: row["decision_id"],
    )
    if len(states) != 15 or len(labels) != 15 or len(decisions) != 45:
        raise ExecutionError(f"{split} 冻结数据规模漂移")
    return states, labels, decisions


def _request_files() -> list[Path]:
    return (
        sorted(EVIDENCE_ROOT.glob("provider/*/requests/*.json"))
        if EVIDENCE_ROOT.exists()
        else []
    )


def _observation_files() -> list[Path]:
    return (
        sorted(EVIDENCE_ROOT.glob("provider/*/observations/*.json"))
        if EVIDENCE_ROOT.exists()
        else []
    )


def _attempt_files() -> list[Path]:
    return (
        sorted(EVIDENCE_ROOT.glob("provider/*/attempts/*.json"))
        if EVIDENCE_ROOT.exists()
        else []
    )


def _budget_usage() -> dict[str, Any]:
    request_ids: set[str] = set()
    input_tokens = 0
    output_tokens = 0
    cost = 0.0
    for path in _observation_files():
        observation = candidate.load_json(path)["response_observation"]
        request_id = observation["request_id"]
        if request_id in request_ids:
            raise ExecutionError("Provider request ID 重复")
        request_ids.add(request_id)
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


def _read_credential() -> str:
    if CREDENTIAL_FILE.is_symlink() or CREDENTIAL_FILE.stat().st_mode & 0o777 != 0o600:
        raise ExecutionError("credential 文件类型或权限漂移")
    key = CREDENTIAL_FILE.read_text(encoding="utf-8").strip()
    if not key or "\n" in key or "\r" in key:
        raise ExecutionError("credential 文件必须只含一行非空 API key")
    return key


def _provider_http_client() -> httpx2.Client:
    return httpx2.Client(proxy=EGRESS_PROXY_URL, trust_env=False, timeout=30.0)


def _response_observation(response: Any, *, latency_ms: float) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    if (
        isinstance(input_tokens, bool)
        or not isinstance(input_tokens, int)
        or input_tokens < 0
    ):
        raise ExecutionError("Provider observation 缺少合法 input token usage")
    if (
        isinstance(output_tokens, bool)
        or not isinstance(output_tokens, int)
        or output_tokens < 0
    ):
        raise ExecutionError("Provider observation 缺少合法 output token usage")
    request_id = getattr(response, "request_id", None)
    if not isinstance(request_id, str) or not request_id:
        raise ExecutionError("Provider observation 缺少 request id")
    answers: dict[str, Any] = {}
    for question_id, answer in dict(getattr(response, "answers", {})).items():
        probabilities = getattr(answer, "probabilities", None)
        answers[str(question_id)] = {
            "type": getattr(answer, "type", None),
            "choice": getattr(answer, "choice", None),
            "confidence": getattr(answer, "confidence", None),
            "probabilities": dict(probabilities) if probabilities is not None else None,
        }
    return {
        "model": getattr(response, "model", None),
        "request_id": request_id,
        "answers": answers,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        "cost_usd": input_tokens
        * candidate.INPUT_PRICE_USD_PER_MILLION_TOKENS
        / 1_000_000,
        "latency_ms": float(latency_ms),
    }


def _stage_directory(split: str) -> Path:
    return EVIDENCE_ROOT / "provider" / split


def _validate_stage_request(split: str) -> None:
    if split not in candidate.SPLITS:
        raise ExecutionError(f"未知 split: {split}")
    if EVIDENCE_ROOT.joinpath("completed.json").exists():
        raise ExecutionError("formal identity 已封存")
    if split == "evaluation":
        calibration_path = EVIDENCE_ROOT / "calibration.json"
        if (
            not calibration_path.is_file()
            or candidate.load_json(calibration_path).get("passed") is not True
        ):
            raise ExecutionError("calibration 未通过，禁止 evaluation")


def run_provider(split: str) -> dict[str, Any]:
    manifest = validate_execution_manifest()
    _assert_revision(manifest, require_clean=True)
    validate_egress()
    _validate_stage_request(split)
    directory = _stage_directory(split)
    if directory.exists():
        raise ExecutionError(f"{split} Provider stage 已存在，禁止 retry/backfill")
    current = _budget_usage()
    _enforce_budget(manifest, current)
    states, _, _ = _split_rows(split)
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
            "split": split,
            "status": "started",
            "created_at": _now(),
            "budget_before": current,
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
                model=candidate.MODEL_ID,
                retry=RetryPolicy(max_retries=0, timeout=30.0),
                base_url=candidate.API_BASE_URL,
                http_client=http_client,
            ) as client:
                for index, state_row in enumerate(states, start=1):
                    before = _budget_usage()
                    if (
                        before["physical_requests"]
                        >= manifest["authorization"]["maximum_physical_requests"]
                    ):
                        raise ExecutionError("Provider request 预算已耗尽")
                    state = candidate.provider_state(state_row)
                    fingerprint = candidate.request_fingerprint(state, questions)
                    stem = f"{index:02d}-{state_row['state_id']}"
                    _write_once_json(
                        directory / "attempts" / f"{stem}.json",
                        {
                            "identity": IDENTITY,
                            "split": split,
                            "sequence": index,
                            "state_id": state_row["state_id"],
                            "created_at": _now(),
                            "git_commit": _git("rev-parse", "HEAD"),
                            "model": candidate.MODEL_ID,
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
                            "split": split,
                            "sequence": index,
                            "state_id": state_row["state_id"],
                            "request_fingerprint": fingerprint,
                            "response": normalized,
                        },
                    )
                    _enforce_budget(manifest, _budget_usage())
        key = None
        responses = _responses(split, require_completed=False)
        analysis = _analyse_actions(split, responses)
        _write_once_json(directory / "analysis.json", analysis)
        _write_once_json(
            directory / "completed.json",
            {
                "identity": IDENTITY,
                "split": split,
                "status": "completed",
                "created_at": _now(),
                "credential_reads": credential_reads,
                "provider_calls": len(states),
                "budget_after": _budget_usage(),
            },
        )
        return analysis
    except Exception as exc:
        key = None
        _write_once_json(
            directory / "failed.json",
            {
                "identity": IDENTITY,
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


def _responses(split: str, *, require_completed: bool = True) -> list[dict[str, Any]]:
    directory = _stage_directory(split)
    if require_completed and not (directory / "completed.json").is_file():
        raise ExecutionError(f"{split} Provider stage 未完整封存")
    rows = [
        candidate.load_json(path)
        for path in sorted((directory / "requests").glob("*.json"))
    ]
    if len(rows) != 15:
        raise ExecutionError(f"{split} 有效响应不是 15/15")
    request_ids = [row["response"]["request_id"] for row in rows]
    if len(set(request_ids)) != len(request_ids):
        raise ExecutionError(f"{split} request ID 不唯一")
    return rows


def _analyse_actions(split: str, responses: list[dict[str, Any]]) -> dict[str, Any]:
    states, labels, _ = _split_rows(split)
    states_by_id = {row["state_id"]: row for row in states}
    labels_by_id = {row["state_id"]: row for row in labels}
    rows: list[dict[str, Any]] = []
    for response_row in responses:
        state_id = response_row["state_id"]
        state = states_by_id[state_id]
        label = labels_by_id[state_id]
        response = response_row["response"]
        primary = response["answers"]["next_action_primary"]
        sensitivity = response["answers"]["next_action_order_sensitivity"]
        choice = primary["choice"]
        action_costs = {
            row["action_family"]: row["cost"] for row in state["candidate_actions"]
        }
        rows.append(
            {
                "state_id": state_id,
                "project_family": state["project_family"],
                "build_system": state["build_system"],
                "choice": choice,
                "order_sensitivity_choice": sensitivity["choice"],
                "order_agreement": response["order_agreement"],
                "probabilities": primary["normalized_probabilities"],
                "raw_probabilities": primary["raw_probabilities"],
                "raw_probability_sum": primary["raw_probability_sum"],
                "confidence": primary["confidence"],
                "optimal_action": label["optimal_action"],
                "safe_actions": label["safe_actions"],
                "exact_optimal": choice == label["optimal_action"],
                "safe_action": choice in label["safe_actions"],
                "selected_action_cost": action_costs[choice],
                "optimal_action_cost": label["optimal_cost"],
                "action_cost_regret": action_costs[choice] - label["optimal_cost"],
                "usage": response["usage"],
                "cost_usd": response["cost_usd"],
                "latency_ms": response["latency_ms"],
                "request_id": response["request_id"],
            }
        )
    if len(rows) != 15:
        raise ExecutionError(f"{split} action analysis 不是 15 个状态")
    return {
        "split": split,
        "state_count": len(rows),
        "exact_optimal_action_count": sum(row["exact_optimal"] for row in rows),
        "safe_action_count": sum(row["safe_action"] for row in rows),
        "order_agreement_count": sum(row["order_agreement"] for row in rows),
        "per_build_system": {
            system: {
                "state_count": sum(row["build_system"] == system for row in rows),
                "exact_optimal_action_count": sum(
                    row["exact_optimal"]
                    for row in rows
                    if row["build_system"] == system
                ),
                "safe_action_count": sum(
                    row["safe_action"] for row in rows if row["build_system"] == system
                ),
                "order_agreement_count": sum(
                    row["order_agreement"]
                    for row in rows
                    if row["build_system"] == system
                ),
            }
            for system in candidate.BUILD_SYSTEMS
        },
        "rows": sorted(rows, key=lambda row: row["state_id"]),
    }


def _serialized_probability(model: dict[str, float], probability: float) -> float:
    clipped = min(
        max(float(probability), candidate.PLATT_EPSILON), 1.0 - candidate.PLATT_EPSILON
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
        raise ExecutionError("calibration 已存在，禁止覆盖或重算")
    responses = _responses("calibration")
    analysis = _analyse_actions("calibration", responses)
    rows: list[dict[str, Any]] = []
    for state in analysis["rows"]:
        for action in candidate.LOCAL_ACTIONS:
            rows.append(
                {
                    "state_id": state["state_id"],
                    "build_system": state["build_system"],
                    "action": action,
                    "probability": state["probabilities"][action],
                    "safe": action in state["safe_actions"],
                }
            )
    labels = {row["safe"] for row in rows}
    if len(rows) != 45:
        raise ExecutionError("Platt calibration 行数不是 45")
    if labels != {False, True}:
        result = {
            "identity": IDENTITY,
            "created_at": _now(),
            "passed": False,
            "reason": "platt_labels_do_not_contain_both_classes",
            "row_count": len(rows),
            "label_counts": dict(
                sorted(Counter(str(row["safe"]).lower() for row in rows).items())
            ),
            "action_analysis": analysis,
            "decision": "stop_before_progress_budget_evaluation",
        }
        _write_once_json(path, result)
        return result
    estimator = candidate.fit_platt(rows)
    classes = list(estimator.classes_)
    if classes != [False, True] and classes != [0, 1]:
        raise ExecutionError(f"Platt class 顺序漂移: {classes}")
    model = {
        "coefficient": float(estimator.coef_[0][0]),
        "intercept": float(estimator.intercept_[0]),
    }
    threshold_rows: list[dict[str, Any]] = []
    for row in analysis["rows"]:
        choice = row["choice"]
        raw_probability = row["probabilities"][choice]
        threshold_rows.append(
            {
                "state_id": row["state_id"],
                "build_system": row["build_system"],
                "selected_action": choice,
                "order_agreement": row["order_agreement"],
                "safe": row["safe_action"],
                "raw_probability": raw_probability,
                "calibrated_probability": (
                    _serialized_probability(model, raw_probability)
                    if choice in candidate.LOCAL_ACTIONS
                    else None
                ),
            }
        )
    calibrated_threshold = candidate.select_zero_error_threshold(
        threshold_rows,
        probability_field="calibrated_probability",
    )
    raw_threshold = candidate.select_zero_error_threshold(
        threshold_rows,
        probability_field="raw_probability",
    )
    gates = {
        "complete_valid_responses": len(responses) == 15,
        "platt_rows": len(rows) == 45,
        "positive_and_negative_labels": labels == {False, True},
        "zero_observed_unsafe_direct": calibrated_threshold["unsafe_direct_count"] == 0,
        "minimum_direct_state_count": calibrated_threshold["direct_state_count"] >= 5,
        "all_build_systems_direct": all(
            calibrated_threshold["per_build_system_direct_state_count"][system] >= 1
            for system in candidate.BUILD_SYSTEMS
        ),
    }
    passed = all(gates.values())
    result = {
        "identity": IDENTITY,
        "created_at": _now(),
        "row_count": len(rows),
        "label_counts": dict(
            sorted(Counter(str(row["safe"]).lower() for row in rows).items())
        ),
        "model": model,
        "calibrated_threshold": calibrated_threshold,
        "raw_threshold": raw_threshold,
        "threshold_rows": threshold_rows,
        "action_analysis": analysis,
        "gates": gates,
        "passed": passed,
        "decision": (
            "proceed_to_progress_budget_evaluation"
            if passed
            else "stop_before_progress_budget_evaluation"
        ),
    }
    _write_once_json(path, result)
    return result


def _route_rows(
    *,
    decisions: list[dict[str, Any]],
    action_rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    probability_kind: str,
    model: dict[str, float] | None,
    threshold: float,
) -> list[dict[str, Any]]:
    actions_by_state = {row["state_id"]: row for row in action_rows}
    rows: list[dict[str, Any]] = []
    for decision in decisions:
        action = actions_by_state[decision["state_id"]]
        selected_action = action["choice"]
        probability: float | None = None
        if selected_action in candidate.LOCAL_ACTIONS:
            raw = action["probabilities"][selected_action]
            probability = (
                _serialized_probability(model, raw)
                if probability_kind == "calibrated" and model is not None
                else raw
            )
        route = candidate.budget_fit_route(
            selected_action=selected_action,
            order_agreement=action["order_agreement"],
            calibrated_probability=probability,
            threshold=threshold,
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
                "selected_action": selected_action,
                "order_agreement": action["order_agreement"],
                "safe_probability": probability,
                "threshold": threshold,
                "predicted_route": route["route"],
                "predicted_action": route["action"],
                "route_gate": route["gate"],
                "optimal_route": decision["optimal_route"],
                "optimal_action": decision["optimal_action"],
                "correct": correct,
            }
        )
    return sorted(rows, key=lambda row: row["decision_id"])


def _route_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    direct = [row for row in rows if row["predicted_route"] == "direct"]
    wrong_direct = [row for row in direct if not row["correct"]]
    confusion: dict[str, Counter[str]] = {}
    for route in ("direct", "escalate_agent", "stop"):
        confusion[route] = Counter(
            row["predicted_route"] for row in rows if row["optimal_route"] == route
        )
    return {
        "decision_count": len(rows),
        "joint_correct": sum(row["correct"] for row in rows),
        "direct_count": len(direct),
        "wrong_direct_count": len(wrong_direct),
        "wrong_direct_risk": len(wrong_direct) / len(direct) if direct else None,
        "per_build_system_joint_correct": {
            system: sum(row["correct"] for row in rows if row["build_system"] == system)
            for system in candidate.BUILD_SYSTEMS
        },
        "predicted_route_counts": dict(
            sorted(Counter(row["predicted_route"] for row in rows).items())
        ),
        "route_confusion": {
            actual: {
                predicted: confusion[actual][predicted]
                for predicted in ("direct", "escalate_agent", "stop")
            }
            for actual in ("direct", "escalate_agent", "stop")
        },
        "rows": rows,
    }


def _f1_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values: dict[str, float] = {}
    for action in candidate.ACTION_FAMILIES:
        true_positive = sum(
            row["choice"] == action and row["optimal_action"] == action for row in rows
        )
        false_positive = sum(
            row["choice"] == action and row["optimal_action"] != action for row in rows
        )
        false_negative = sum(
            row["choice"] != action and row["optimal_action"] == action for row in rows
        )
        denominator = 2 * true_positive + false_positive + false_negative
        values[action] = 0.0 if denominator == 0 else 2 * true_positive / denominator
    return {"macro_f1": sum(values.values()) / len(values), "f1_by_action": values}


def _ece(
    rows: list[dict[str, Any]], *, score_key: str, correct_key: str
) -> dict[str, Any]:
    bins: list[dict[str, Any]] = []
    value = 0.0
    for index in range(5):
        lower = index / 5
        upper = (index + 1) / 5
        selected = [
            row
            for row in rows
            if lower <= row[score_key]
            and (row[score_key] < upper or (index == 4 and row[score_key] <= upper))
        ]
        if not selected:
            bins.append(
                {
                    "lower": lower,
                    "upper": upper,
                    "count": 0,
                    "mean_score": None,
                    "observed_rate": None,
                }
            )
            continue
        mean_score = sum(row[score_key] for row in selected) / len(selected)
        observed = sum(row[correct_key] for row in selected) / len(selected)
        value += len(selected) / len(rows) * abs(observed - mean_score)
        bins.append(
            {
                "lower": lower,
                "upper": upper,
                "count": len(selected),
                "mean_score": mean_score,
                "observed_rate": observed,
            }
        )
    return {"ece": value, "bins": bins}


def _action_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    f1 = _f1_metrics(rows)
    brier = sum(
        sum(
            (row["probabilities"][action] - float(row["optimal_action"] == action)) ** 2
            for action in candidate.ACTION_FAMILIES
        )
        for row in rows
    ) / len(rows)
    confidence_rows = [
        {"score": max(row["probabilities"].values()), "correct": row["exact_optimal"]}
        for row in rows
    ]
    latencies = sorted(float(row["latency_ms"]) for row in rows)
    return {
        **f1,
        "multiclass_brier_score": brier,
        "multiclass_brier_definition": "mean sum of squared class-probability errors",
        "top1_ece_5_bins": _ece(
            confidence_rows, score_key="score", correct_key="correct"
        ),
        "action_cost_regret": {
            "total": sum(row["action_cost_regret"] for row in rows),
            "mean": sum(row["action_cost_regret"] for row in rows) / len(rows),
        },
        "latency_ms": {
            "mean": statistics.fmean(latencies),
            "median": statistics.median(latencies),
            "p95_nearest_rank": latencies[max(0, math.ceil(0.95 * len(latencies)) - 1)],
            "total": sum(latencies),
        },
        "usage": {
            "input_tokens": sum(row["usage"]["input_tokens"] for row in rows),
            "output_tokens": sum(row["usage"]["output_tokens"] for row in rows),
            "model_cost_usd": sum(row["cost_usd"] for row in rows),
        },
    }


def _binary_calibration_metrics(
    rows: list[dict[str, Any]],
    model: dict[str, float],
) -> dict[str, Any]:
    pairs: list[dict[str, Any]] = []
    for row in rows:
        for action in candidate.LOCAL_ACTIONS:
            raw = row["probabilities"][action]
            pairs.append(
                {
                    "raw_score": raw,
                    "calibrated_score": _serialized_probability(model, raw),
                    "safe": action in row["safe_actions"],
                }
            )
    return {
        "row_count": len(pairs),
        "raw_brier": sum((row["raw_score"] - float(row["safe"])) ** 2 for row in pairs)
        / len(pairs),
        "calibrated_brier": sum(
            (row["calibrated_score"] - float(row["safe"])) ** 2 for row in pairs
        )
        / len(pairs),
        "raw_ece_5_bins": _ece(pairs, score_key="raw_score", correct_key="safe"),
        "calibrated_ece_5_bins": _ece(
            pairs, score_key="calibrated_score", correct_key="safe"
        ),
    }


def _risk_coverage_curve(
    decisions: list[dict[str, Any]],
    action_rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    model: dict[str, float],
) -> list[dict[str, Any]]:
    scores = sorted(
        {
            _serialized_probability(model, row["probabilities"][row["choice"]])
            for row in action_rows
            if row["choice"] in candidate.LOCAL_ACTIONS and row["order_agreement"]
        },
        reverse=True,
    )
    curve: list[dict[str, Any]] = []
    for threshold in scores:
        rows = _route_rows(
            decisions=decisions,
            action_rows=action_rows,
            manifest=manifest,
            probability_kind="calibrated",
            model=model,
            threshold=threshold,
        )
        summary = _route_summary(rows)
        curve.append(
            {
                "threshold": threshold,
                "direct_count": summary["direct_count"],
                "coverage": summary["direct_count"] / len(rows),
                "wrong_direct_count": summary["wrong_direct_count"],
                "risk": summary["wrong_direct_risk"],
            }
        )
    return curve


def evaluate() -> dict[str, Any]:
    path = EVIDENCE_ROOT / "evaluation.json"
    if path.exists():
        raise ExecutionError("evaluation 已存在，禁止覆盖或重算")
    calibration = candidate.load_json(EVIDENCE_ROOT / "calibration.json")
    if calibration.get("passed") is not True:
        raise ExecutionError("calibration 未通过，禁止 evaluation 分析")
    responses = _responses("evaluation")
    manifest = validate_execution_manifest()
    _, _, decisions = _split_rows("evaluation")
    actions = _analyse_actions("evaluation", responses)
    model = calibration["model"]
    calibrated_rows = _route_rows(
        decisions=decisions,
        action_rows=actions["rows"],
        manifest=manifest,
        probability_kind="calibrated",
        model=model,
        threshold=calibration["calibrated_threshold"]["threshold"],
    )
    raw_rows = _route_rows(
        decisions=decisions,
        action_rows=actions["rows"],
        manifest=manifest,
        probability_kind="raw",
        model=None,
        threshold=calibration["raw_threshold"]["threshold"],
    )
    calibrated = _route_summary(calibrated_rows)
    raw = _route_summary(raw_rows)
    wrong_risk = calibrated["wrong_direct_risk"]
    core_gates = {
        "complete_valid_responses": len(responses) == 15,
        "minimum_exact_optimal_action_count": actions["exact_optimal_action_count"]
        >= 12,
        "minimum_exact_optimal_action_per_build_system": all(
            actions["per_build_system"][system]["exact_optimal_action_count"] >= 4
            for system in candidate.BUILD_SYSTEMS
        ),
        "minimum_safe_action_count": actions["safe_action_count"] >= 14,
        "minimum_order_agreement_count": actions["order_agreement_count"] >= 14,
        "minimum_direct_decision_count": calibrated["direct_count"] >= 14,
        "maximum_wrong_direct_risk": wrong_risk is not None and wrong_risk <= 0.10,
        "minimum_joint_correct": calibrated["joint_correct"] >= 32,
    }
    incremental_gates = {
        "minimum_joint_correct_per_build_system": all(
            calibrated["per_build_system_joint_correct"][system] >= 13
            for system in candidate.BUILD_SYSTEMS
        ),
        "option_a_joint_correct": calibrated["joint_correct"] >= 42,
        "option_b_coverage_risk_and_joint": (
            calibrated["direct_count"] >= 21
            and wrong_risk is not None
            and wrong_risk <= 0.10
            and calibrated["joint_correct"] >= 39
        ),
    }
    core_passed = all(core_gates.values())
    incremental_passed = incremental_gates[
        "minimum_joint_correct_per_build_system"
    ] and (
        incremental_gates["option_a_joint_correct"]
        or incremental_gates["option_b_coverage_risk_and_joint"]
    )
    if not core_passed:
        decision = "stop_jev_progress_budget_routing_before_controller"
    elif not incremental_passed:
        decision = "stop_jev_as_incremental_component_keep_semantic_budget_method"
    else:
        decision = "proceed_to_frozen_response_progress_budget_controller_replay_design"
    result = {
        "identity": IDENTITY,
        "created_at": _now(),
        "action_analysis": actions,
        "action_metrics": _action_metrics(actions["rows"]),
        "binary_safe_action_calibration": _binary_calibration_metrics(
            actions["rows"], model
        ),
        "jev_raw_budgetfit": raw,
        "jev_calibrated_budgetfit": calibrated,
        "risk_coverage_curve": _risk_coverage_curve(
            decisions, actions["rows"], manifest, model
        ),
        "baselines": {
            "rule_gate": manifest["data_contract"]["split"]["evaluation"]["rule_gate"],
            "tfidf_budgetfit": manifest["data_contract"]["split"]["evaluation"][
                "tfidf_budgetfit"
            ],
            "oracle_routes": manifest["data_contract"]["split"]["evaluation"][
                "oracle_routes"
            ],
        },
        "core_gates": core_gates,
        "incremental_gates": incremental_gates,
        "core_passed": core_passed,
        "incremental_passed": incremental_passed,
        "passed": core_passed and incremental_passed,
        "decision": decision,
    }
    _write_once_json(path, result)
    return result


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


def _credential_scan() -> dict[str, Any]:
    key = _read_credential().encode()
    violations: list[str] = []
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


def _terminal_payload() -> dict[str, Any]:
    calibration_failed = _stage_directory("calibration") / "failed.json"
    evaluation_failed = _stage_directory("evaluation") / "failed.json"
    calibration_path = EVIDENCE_ROOT / "calibration.json"
    evaluation_path = EVIDENCE_ROOT / "evaluation.json"
    if calibration_failed.is_file():
        return {
            "terminal_stage": "provider_calibration",
            "calibration": candidate.load_json(calibration_failed),
            "evaluation": None,
            "passed": False,
            "decision": "stop_before_progress_budget_evaluation",
        }
    if not calibration_path.is_file():
        raise ExecutionError("calibration 尚未完成，不能生成终态报告")
    calibration = candidate.load_json(calibration_path)
    if calibration.get("passed") is not True:
        return {
            "terminal_stage": "calibration",
            "calibration": calibration,
            "evaluation": None,
            "passed": False,
            "decision": "stop_before_progress_budget_evaluation",
        }
    if evaluation_failed.is_file():
        return {
            "terminal_stage": "provider_evaluation",
            "calibration": calibration,
            "evaluation": candidate.load_json(evaluation_failed),
            "passed": False,
            "decision": "stop_jev_progress_budget_routing_before_controller",
        }
    if not evaluation_path.is_file():
        raise ExecutionError("evaluation 尚未完成，不能生成终态报告")
    evaluation = candidate.load_json(evaluation_path)
    return {
        "terminal_stage": "evaluation",
        "calibration": calibration,
        "evaluation": evaluation,
        "passed": evaluation["passed"],
        "decision": evaluation["decision"],
    }


def _seal_evidence(result: dict[str, Any]) -> dict[str, Any]:
    if (EVIDENCE_ROOT / "completed.json").exists() or (
        EVIDENCE_ROOT / "inventory.json"
    ).exists():
        raise ExecutionError("formal evidence 已封存，禁止覆盖")
    candidate.audit_parent_raw_evidence()
    _write_once_json(EVIDENCE_ROOT / "result.json", result)
    credential_scan = _credential_scan()
    inventory_rows = _evidence_inventory()
    inventory = {
        "identity": IDENTITY,
        "files": inventory_rows,
        "file_count": len(inventory_rows),
        "total_bytes": sum(row["size_bytes"] for row in inventory_rows),
        "canonical_sha256": candidate.canonical_sha256(inventory_rows),
    }
    _write_once_json(EVIDENCE_ROOT / "inventory.json", inventory)
    marker = {
        "identity": IDENTITY,
        "status": "completed",
        "completed_at": _now(),
        "decision": result["decision"],
        "inventory_canonical_sha256": inventory["canonical_sha256"],
        "credential_scan": credential_scan,
        "historical_evidence_modified": False,
        "zero_managed_resources": True,
    }
    _write_once_json(EVIDENCE_ROOT / "completed.json", marker)
    return {"inventory": inventory, "marker": marker}


def build_report() -> dict[str, Any]:
    if JSON_REPORT.exists() or MARKDOWN_REPORT.exists():
        raise ExecutionError("正式报告已存在，禁止覆盖")
    manifest = validate_execution_manifest()
    terminal = _terminal_payload()
    budget = _budget_usage()
    _enforce_budget(manifest, budget)
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "document_type": "forge_jev_progress_budget_calibration_report",
        "identity": IDENTITY,
        "issue_url": ISSUE_URL,
        "created_at": _now(),
        "git_commit": _git("rev-parse", "HEAD"),
        "manifest_canonical_sha256": candidate.canonical_sha256(manifest),
        "candidate_manifest_canonical_sha256": CANDIDATE_MANIFEST_CANONICAL_SHA256,
        **terminal,
        "budget": budget,
        "parent_raw_evidence": candidate.audit_parent_raw_evidence(),
        "interpretation": {
            "offline_action_selection_estimated": terminal["terminal_stage"]
            == "evaluation",
            "offline_progress_budget_routing_estimated": terminal["terminal_stage"]
            == "evaluation",
            "controller_effect_estimated": False,
            "strict_success_noninferiority_estimated": False,
            "end_to_end_cost_effect_estimated": False,
            "statistical_significance_estimated": False,
            "temporal_generalization_estimated": False,
            "natural_failure_population_estimated": False,
            "historical_evidence_modified": False,
        },
    }
    sealed = _seal_evidence(report)
    report["evidence"] = {
        "root": EVIDENCE_ROOT.relative_to(REPO_ROOT).as_posix(),
        "inventory_file_count": sealed["inventory"]["file_count"],
        "inventory_total_bytes": sealed["inventory"]["total_bytes"],
        "inventory_canonical_sha256": sealed["inventory"]["canonical_sha256"],
        "marker": sealed["marker"],
    }
    _write_once_json(JSON_REPORT, report)
    _write_once_text(MARKDOWN_REPORT, render_markdown(report))
    return report


def render_markdown(report: dict[str, Any]) -> str:
    evaluation = report["evaluation"]
    if report["terminal_stage"] != "evaluation":
        return f"""# 进展预算感知 Jev 正式离线校准 v1 结果

- identity：`{IDENTITY}`
- 决定：`{report["decision"]}`
- 停止阶段：`{report["terminal_stage"]}`
- Provider 请求：`{report["budget"]["physical_requests"]}`
- 有效响应：`{report["budget"]["valid_normalized_responses"]}`
- Input tokens：`{report["budget"]["input_tokens"]}`
- Output tokens：`{report["budget"]["output_tokens"]}`
- Jev 模型费用：`${report["budget"]["model_cost_usd"]:.8f}`

## 结论

实验按预注册停止规则在 `{report["terminal_stage"]}` 阶段关闭，未执行或未形成完整 evaluation 分析。该结果不能估计 evaluation holdout 上的动作选择、预算路由或 Jev 相对轻量基线的增量。

## 解释边界

本 identity 不估计 controller treatment effect、严格成功率非劣、端到端成本下降、统计显著性、跨时间泛化或自然失败总体表现。
"""
    actions = evaluation["action_analysis"]
    calibrated = evaluation["jev_calibrated_budgetfit"]
    baselines = evaluation["baselines"]
    return f"""# 进展预算感知 Jev 正式离线校准 v1 结果

- identity：`{IDENTITY}`
- 决定：`{report["decision"]}`
- Evaluation exact optimal action：`{actions["exact_optimal_action_count"]}/15`
- Evaluation safe action：`{actions["safe_action_count"]}/15`
- 正反顺序一致：`{actions["order_agreement_count"]}/15`
- JevCalibrated+BudgetFit joint correct：`{calibrated["joint_correct"]}/45`
- JevCalibrated direct：`{calibrated["direct_count"]}/45`
- JevCalibrated wrong direct：`{calibrated["wrong_direct_count"]}`
- RuleGate joint correct：`{baselines["rule_gate"]["joint_correct"]}/45`
- TF-IDF+BudgetFit joint correct：`{baselines["tfidf_budgetfit"]["joint_correct"]}/45`
- Provider 请求：`{report["budget"]["physical_requests"]}`
- Input / output tokens：`{report["budget"]["input_tokens"]}` / `{report["budget"]["output_tokens"]}`
- Jev 模型费用：`${report["budget"]["model_cost_usd"]:.8f}`

## 门槛

```json
{json.dumps({"core": evaluation["core_gates"], "incremental": evaluation["incremental_gates"]}, ensure_ascii=False, indent=2, sort_keys=True)}
```

## 结论边界

该结果只估计当前 3 个 calibration 项目族与 3 个 evaluation 项目族、30 个受控状态上的离线动作选择、校准和预算路由。它不估计 controller treatment effect、严格成功率非劣、端到端成本下降、统计显著性、跨时间泛化或自然失败总体表现。
"""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    bind = subparsers.add_parser("bind-execution")
    bind.add_argument("--implementation-revision", required=True)
    for command in ("validate", "preflight", "calibrate", "evaluate", "report"):
        subparsers.add_parser(command)
    provider = subparsers.add_parser("run-provider")
    provider.add_argument("--split", choices=candidate.SPLITS, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "bind-execution":
        print(candidate.canonical_sha256(bind_execution(args.implementation_revision)))
        return 0
    if args.command == "validate":
        print(candidate.canonical_sha256(validate_execution_manifest()))
        return 0
    if args.command == "preflight":
        print(json.dumps(preflight(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "run-provider":
        print(
            json.dumps(
                run_provider(args.split), ensure_ascii=False, indent=2, sort_keys=True
            )
        )
        return 0
    if args.command == "calibrate":
        print(json.dumps(calibrate(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "evaluate":
        print(json.dumps(evaluate(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
