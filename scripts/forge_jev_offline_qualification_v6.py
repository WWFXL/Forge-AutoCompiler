#!/usr/bin/env python3
"""Issue #401 Jev 离线资格实验 v6 的授权执行器。"""

from __future__ import annotations

import argparse
import json
import logging
import math
import re
import subprocess
import time
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import forge_jev_offline_qualification_candidate as candidate
import forge_typed_action_benchmark_qualification as v1
import httpx2
import jsonschema
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from typesafe_sdk import Choice, RetryPolicy, TypeSafeClient

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
IDENTITY = "cpp-jev-offline-qualification-v6"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/401"
BRANCH = "yiwei/401-jev-offline-v6"
SCHEMA_VERSION = "forge-jev-offline-qualification-execution-6.0.0"
REPORT_SCHEMA_VERSION = "forge-jev-offline-qualification-report-6.0.0"

SOURCE_POOL = REPO_ROOT / "benchmarks/fixtures/cpp-jev-offline-qualification-source-pool-v2.json"
CANDIDATE_MANIFEST = candidate.DEFAULT_MANIFEST
EVALUATION_REPORT = candidate.V2_REPORT
EVALUATION_STATES = REPO_ROOT / "benchmarks/fixtures/cpp-jev-offline-qualification-evaluation-states-v1.json"
EXECUTION_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-jev-offline-qualification-v6.json"
EXECUTION_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-jev-offline-qualification-v6.schema.json"
AMENDMENT = REPO_ROOT / "benchmarks/preregistrations/cpp-jev-offline-qualification-v6.md"
EVIDENCE_ROOT = REPO_ROOT / ".compile-sessions/benchmark-evidence-jev-offline-qualification-v6"
JSON_REPORT = REPO_ROOT / "benchmarks/reports/cpp-jev-offline-qualification-v6.json"
MARKDOWN_REPORT = REPO_ROOT / "benchmarks/reports/cpp-jev-offline-qualification-v6.md"
CREDENTIAL_FILE = REPO_ROOT / "jev-apikey.txt"
PROMPT_AMENDMENT = REPO_ROOT / "benchmarks/preregistrations/cpp-jev-offline-qualification-v6-prompt-amendment.json"
PARENT_FAILURE_REPORT = REPO_ROOT / "benchmarks/reports/cpp-jev-offline-qualification-v3.json"
PARENT_FAILURE_REPORT_SHA256 = "ea2257cac6eff19196d2363b600e8302a5c40e454aea8699c66eeba8cc494168"
PARENT_CATALOG_REPORT = REPO_ROOT / "benchmarks/reports/cpp-jev-offline-qualification-v4.json"
PARENT_CATALOG_REPORT_SHA256 = "85e62c6fa8b6f4c1d9dc1eabd2808b12ec5cc2d30e5ceb6d16ec9604b6a82909"
PARENT_NUMERIC_REPORT = REPO_ROOT / "benchmarks/reports/cpp-jev-offline-qualification-v5.json"
PARENT_NUMERIC_REPORT_SHA256 = "42512a051c99cbf46279ceb395adc947f9eb27c029e770a7355cd713f8d41327"
PARENT_OUTCOMES = REPO_ROOT / ".compile-sessions/benchmark-evidence-jev-offline-qualification-v3/outcomes.json"
PARENT_OUTCOMES_SHA256 = "8fd490d8cc9e2517c1ff8e182a8e0930e103a6b6c9b2ff426904deede9d2cf93"
PARENT_OUTCOME_IDENTITY = "cpp-jev-offline-qualification-v3"

EGRESS_CONTAINER = "forge-typesafe-egress"
EGRESS_PROXY_URL = "http://127.0.0.1:17891"
EGRESS_CONFIG = Path("/home/yiwei/services/forge-egress/config/typesafe-config.yaml")
EGRESS_CONFIG_SHA256 = "61ed936fe28f5cc7631fbd20c3fe92a93230db16d2bd5dee07829119a05d37ea"
EGRESS_IMAGE_ID = "sha256:30afbbe303155d74537b0e3061ffda5e5e64746a6b41ad32991dd63ab9984ce0"
EGRESS_HOST_PORT = "17891"
EGRESS_CONTAINER_PORT = "7890/tcp"

DIRECT_ACTIONS = ("dependency", "configure", "build")
PROVIDER_SPLITS = ("design", "calibration", "evaluation")


class ExecutionError(RuntimeError):
    """授权身份、evidence 或执行合同发生漂移。"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _git(*argv: str) -> str:
    return v1._run_checked(["git", *argv])


def _git_blob(revision: str, relative_path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative_path}"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise ExecutionError(f"无法读取 implementation revision 中的 {relative_path}")
    return result.stdout


def _canonical_revision(revision: str) -> str:
    canonical = _git("rev-parse", "--verify", f"{revision}^{{commit}}")
    if not re.fullmatch(r"[0-9a-f]{40}", canonical):
        raise ExecutionError("implementation revision 不是完整 commit SHA")
    return canonical


def _bytes_sha256(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()


def _write_once_json(path: Path, value: Any) -> None:
    v1.write_once(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def generate_evaluation_states() -> dict[str, Any]:
    report = v1.load_json(EVALUATION_REPORT)
    states = [{"state_id": row["state_id"], "model_input": row["model_input"]} for row in report["states"]]
    return {
        "schema_version": "forge-jev-evaluation-states-1.0.0",
        "source_identity": report["identity"],
        "source_report_path": EVALUATION_REPORT.relative_to(REPO_ROOT).as_posix(),
        "source_report_file_sha256": candidate.V2_REPORT_SHA256,
        "contains_labels": False,
        "states": sorted(states, key=lambda row: row["state_id"]),
    }


def write_evaluation_states() -> dict[str, Any]:
    expected = generate_evaluation_states()
    if EVALUATION_STATES.exists():
        if v1.load_json(EVALUATION_STATES) != expected:
            raise ExecutionError("label-free evaluation fixture 漂移")
    else:
        v1.write_json(EVALUATION_STATES, expected)
    return expected


def validate_evaluation_states() -> dict[str, Any]:
    fixture = v1.load_json(EVALUATION_STATES)
    if fixture != generate_evaluation_states():
        raise ExecutionError("label-free evaluation fixture 无法确定重建")
    forbidden = {"optimal_action", "successful_actions", "fault_type", "project_family"}
    payload = json.dumps(fixture, ensure_ascii=False, sort_keys=True).lower()
    if any(field in payload for field in forbidden):
        raise ExecutionError("label-free evaluation fixture 含标签或项目身份")
    if len(fixture["states"]) != 18:
        raise ExecutionError("label-free evaluation fixture 状态数漂移")
    return fixture


def generate_execution_manifest(
    *,
    implementation_revision: str,
    runner_sha256: str,
) -> dict[str, Any]:
    parent = v1.load_json(CANDIDATE_MANIFEST)
    pool = v1.load_json(SOURCE_POOL)
    evaluation_states = validate_evaluation_states()
    return {
        "$schema": "../schemas/forge-jev-offline-qualification-v6.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": "forge_jev_offline_qualification_execution",
        "identity": IDENTITY,
        "issue_url": ISSUE_URL,
        "status": "authorized_formal_execution",
        "parent_candidate": {
            "identity": parent["identity"],
            "git_revision": "72a0003bae19ff5c6a881853ad822725ee9b5447",
            "manifest_path": CANDIDATE_MANIFEST.relative_to(REPO_ROOT).as_posix(),
            "manifest_canonical_sha256": candidate.v1.canonical_sha256(parent),
        },
        "parent_executions": {
            "v3": {
                "identity": "cpp-jev-offline-qualification-v3",
                "report_path": PARENT_FAILURE_REPORT.relative_to(REPO_ROOT).as_posix(),
                "report_file_sha256": PARENT_FAILURE_REPORT_SHA256,
                "provider_evidence_reuse_allowed": False,
                "failure_classification": "provider_region_unavailable",
            },
            "v4": {
                "identity": "cpp-jev-offline-qualification-v4",
                "report_path": PARENT_CATALOG_REPORT.relative_to(REPO_ROOT).as_posix(),
                "report_file_sha256": PARENT_CATALOG_REPORT_SHA256,
                "provider_evidence_reuse_allowed": False,
                "failure_classification": "exact_model_absent_from_catalog",
            },
            "v5": {
                "identity": "cpp-jev-offline-qualification-v5",
                "report_path": PARENT_NUMERIC_REPORT.relative_to(REPO_ROOT).as_posix(),
                "report_file_sha256": PARENT_NUMERIC_REPORT_SHA256,
                "provider_evidence_reuse_allowed": False,
                "failure_classification": "probability_sum_tolerance_exceeded",
            },
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
            "model_calls_authorized": True,
            "maximum_model_requests": 72,
            "maximum_input_tokens": 1_000_000,
            "maximum_model_cost_usd": 0.042,
            "docker_outcome_collection_authorized": False,
            "new_identity_evidence_write_authorized": True,
            "controller_implementation_authorized": False,
            "historical_evidence_write_authorized": False,
        },
        "data_contract": {
            "source_pool_path": SOURCE_POOL.relative_to(REPO_ROOT).as_posix(),
            "source_pool_canonical_sha256": v1.canonical_sha256(pool),
            "parent_outcomes_path": PARENT_OUTCOMES.relative_to(REPO_ROOT).as_posix(),
            "parent_outcomes_file_sha256": PARENT_OUTCOMES_SHA256,
            "parent_outcome_identity": PARENT_OUTCOME_IDENTITY,
            "parent_provider_evidence_reused": False,
            "parent_outcome_qualification_required": True,
            "evaluation_report_path": EVALUATION_REPORT.relative_to(REPO_ROOT).as_posix(),
            "evaluation_report_file_sha256": candidate.V2_REPORT_SHA256,
            "evaluation_states_path": EVALUATION_STATES.relative_to(REPO_ROOT).as_posix(),
            "evaluation_states_file_sha256": v1.file_sha256(EVALUATION_STATES),
            "evaluation_states_canonical_sha256": v1.canonical_sha256(evaluation_states),
            "evaluation_states_contain_labels": False,
            "design_projects": 6,
            "calibration_projects": 6,
            "evaluation_projects": 6,
            "states_per_split": 18,
            "project_family_overlap_allowed": False,
            "global_commit_time_isolation": False,
            "temporal_generalization_claim_allowed": False,
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
        "model_resolution": {
            "catalog_observation_report": PARENT_CATALOG_REPORT.relative_to(REPO_ROOT).as_posix(),
            "catalog_aliases": ["jev-latest", "jev-preview"],
            "catalog_exact_version_required": False,
            "request_model": candidate.MODEL_ID,
            "response_model_must_equal_request_model": True,
            "first_design_request_establishes_callable_version": True,
            "alias_fallback_allowed": False,
            "extra_probe_request_allowed": False,
        },
        "response_contract": {
            "raw_probability_sum_tolerance": 0.005,
            "normalization": "probability_divided_by_raw_sum",
            "raw_probabilities_preserved": True,
            "response_observation_written_before_semantic_validation": True,
            "response_observation_contains_raw_body": False,
            "budget_usage_source": "response_observations",
        },
        "provider_contract": parent["provider_contract"],
        "request_contract": parent["request_contract"],
        "calibration": {
            "input_actions": list(DIRECT_ACTIONS),
            "probability_clip": [0.000001, 0.999999],
            "feature": "logit_of_action_probability",
            "label": "route_acceptable_from_repeated_strict_outcome",
            "model": "sklearn.linear_model.LogisticRegression",
            "c": 1.0,
            "solver": "liblinear",
            "random_state": 393,
            "max_iter": 1000,
            "threshold_rule": "maximum_coverage_with_zero_observed_wrong_direct_action_then_highest_threshold",
        },
        "provider_schedule": {
            "design_round_1_requests": 18,
            "design_round_2_maximum_requests": 18,
            "calibration_requests": 18,
            "evaluation_requests": 18,
            "evaluation_single_analysis_only": True,
            "prompt_amendment_path": PROMPT_AMENDMENT.relative_to(REPO_ROOT).as_posix(),
            "prompt_amendment_allowed_only_after_failed_design_round_1": True,
        },
        "thresholds": parent["candidate_thresholds"],
        "stopping_rules": parent["stopping_rules"],
        "evidence": {
            "root": EVIDENCE_ROOT.relative_to(REPO_ROOT).as_posix(),
            "create_once": True,
            "preserve_failures": True,
            "store_credential": False,
            "store_authorization_header": False,
            "store_raw_provider_body": False,
        },
        "preregistration": {
            "parent": parent["preregistration"]["path"],
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
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-jev-offline-qualification-v6.schema.json",
        "title": "Forge Jev offline qualification execution v6",
        "const": manifest,
    }


def generate_execution_amendment(manifest: dict[str, Any]) -> str:
    authorization = manifest["authorization"]
    schedule = manifest["provider_schedule"]
    return f"""# Jev 离线资格实验 v6 预注册与授权执行协议

## 身份

- Formal identity：`{IDENTITY}`
- Tracking Issue：[#401]({ISSUE_URL})
- Parent candidate：`cpp-jev-offline-qualification-candidate-v1`
- Parent failed identity：`cpp-jev-offline-qualification-v3`
- Parent revision：`{manifest["parent_candidate"]["git_revision"]}`
- Implementation revision：`{manifest["implementation"]["git_revision"]}`
- Runner SHA-256：`{manifest["implementation"]["runner_sha256"]}`
- Manifest canonical SHA-256：`{v1.canonical_sha256(manifest)}`

## 授权与预算

本 identity 已获研究负责人授权读取仓库根 `jev-apikey.txt`、调用固定
`jev-1.13.0`、通过冻结 TypeSafe egress 调用 Provider，并写入本 identity 的
create-once evidence。credential 和 Authorization header 不得进入日志、
evidence 或 Git。

- 最大 Provider 请求：`{authorization["maximum_model_requests"]}`
- 最大 input tokens：`{authorization["maximum_input_tokens"]}`
- 最大模型费用：`${authorization["maximum_model_cost_usd"]}`
- Design：首轮 `{schedule["design_round_1_requests"]}` 请求；仅首轮失败时允许一次版本化 prompt amendment 和最多 `{schedule["design_round_2_maximum_requests"]}` 请求
- Calibration：`{schedule["calibration_requests"]}` 请求
- Evaluation：一次性 `{schedule["evaluation_requests"]}` 请求

## 执行和停止边界

只读绑定 Issue #398 已通过资格门禁的完整 outcome matrix；不得导入其失败的
Provider attempt。Issue #399 已证明固定版本未被模型目录枚举，Issue #400 已证明
固定 `jev-1.13.0` 可直接调用，但在第 13 个 design 响应因原始概率和的 `1e-6`
容差过严而失败关闭。本 identity 不导入其部分预测，把原始概率和容差冻结为
`abs(sum - 1) <= 0.005`，保存原始概率与原始和，并将每个概率除以原始和后再用于
校准和指标。响应观察必须在语义校验前 create-once 封存，以准确计入 token 和费用。
模型版本、Choice schema、概率范围和最大项一致性仍严格校验，不使用 alias 回退。
Calibration 覆盖低于 `6/18` 时停止，不运行
evaluation。Evaluation 的 top-1、直接覆盖、错误直接动作、顺序一致性、
构建系统覆盖或预算任一门槛失败，决定均为
`stop_jev_controller_and_keep_offline_result`。

Issue #398、#399 和 #400 的 Provider attempt 不得导入本实验。本 identity 不授权修改历史
evidence，不授权 retry、replacement、backfill
或 evaluation 后调参，也不授权 controller 实现。结果不支持跨时间泛化、
自然失败总体、端到端严格成功非劣或成本下降声明。
"""


def bind_execution(implementation_revision: str) -> dict[str, Any]:
    if EXECUTION_MANIFEST.exists() or EXECUTION_SCHEMA.exists() or AMENDMENT.exists():
        raise ExecutionError("execution identity 文件已存在，禁止覆盖")
    implementation_revision = _canonical_revision(implementation_revision)
    relative = SCRIPT_PATH.relative_to(REPO_ROOT).as_posix()
    runner_sha = _bytes_sha256(_git_blob(implementation_revision, relative))
    if runner_sha != v1.file_sha256(SCRIPT_PATH):
        raise ExecutionError("当前 runner 与 implementation revision 不一致")
    manifest = generate_execution_manifest(
        implementation_revision=implementation_revision,
        runner_sha256=runner_sha,
    )
    schema = generate_schema(manifest)
    jsonschema.Draft202012Validator.check_schema(schema)
    v1.write_json(EXECUTION_MANIFEST, manifest)
    v1.write_json(EXECUTION_SCHEMA, schema)
    v1.write_once(AMENDMENT, generate_execution_amendment(manifest))
    return manifest


def validate_parent_catalog() -> dict[str, Any]:
    if v1.file_sha256(PARENT_CATALOG_REPORT) != PARENT_CATALOG_REPORT_SHA256:
        raise ExecutionError("Issue #399 冻结模型目录报告漂移")
    report = v1.load_json(PARENT_CATALOG_REPORT)
    availability = report.get("availability", {})
    names = sorted(row["name"] for row in availability.get("models", []))
    if (
        report.get("identity") != "cpp-jev-offline-qualification-v4"
        or report.get("terminal_stage") != "availability"
        or report.get("passed") is not False
        or availability.get("model_inference_performed") is not False
        or names != ["jev-latest", "jev-preview"]
        or report.get("budget", {}).get("model_requests") != 0
    ):
        raise ExecutionError("Issue #399 模型目录观察合同漂移")
    return {
        "identity": report["identity"],
        "report_file_sha256": PARENT_CATALOG_REPORT_SHA256,
        "observed_models": availability["models"],
        "model_inference_performed": False,
        "interpretation": "catalog_aliases_do_not_establish_exact_version_callability",
    }


def validate_parent_numeric_failure() -> dict[str, Any]:
    if v1.file_sha256(PARENT_NUMERIC_REPORT) != PARENT_NUMERIC_REPORT_SHA256:
        raise ExecutionError("Issue #400 冻结概率合同失败报告漂移")
    report = v1.load_json(PARENT_NUMERIC_REPORT)
    budget = report.get("budget", {})
    design = report.get("design", {})
    if (
        report.get("identity") != "cpp-jev-offline-qualification-v5"
        or report.get("terminal_stage") != "provider_design"
        or report.get("passed") is not False
        or design.get("error_type") != "CandidateError"
        or budget.get("model_requests") != 13
        or budget.get("completed_model_responses") != 12
    ):
        raise ExecutionError("Issue #400 概率合同失败观察漂移")
    return {
        "identity": report["identity"],
        "report_file_sha256": PARENT_NUMERIC_REPORT_SHA256,
        "model_requests": budget["model_requests"],
        "persisted_model_responses": budget["completed_model_responses"],
        "failure_type": design["error_type"],
        "provider_evidence_reused": False,
    }


def validate_execution_manifest() -> dict[str, Any]:
    validate_evaluation_states()
    manifest = v1.load_json(EXECUTION_MANIFEST)
    implementation = manifest["implementation"]
    expected = generate_execution_manifest(
        implementation_revision=implementation["git_revision"],
        runner_sha256=implementation["runner_sha256"],
    )
    if manifest != expected:
        raise ExecutionError("execution manifest 无法确定重建")
    if v1.file_sha256(SCRIPT_PATH) != implementation["runner_sha256"]:
        raise ExecutionError("授权 runner hash 漂移")
    schema = v1.load_json(EXECUTION_SCHEMA)
    if schema != generate_schema(manifest):
        raise ExecutionError("execution const Schema 漂移")
    jsonschema.validate(manifest, schema)
    if AMENDMENT.read_text(encoding="utf-8") != generate_execution_amendment(manifest):
        raise ExecutionError("execution amendment 漂移")
    if v1.file_sha256(EVALUATION_REPORT) != candidate.V2_REPORT_SHA256:
        raise ExecutionError("冻结 evaluation 报告漂移")
    if v1.file_sha256(PARENT_FAILURE_REPORT) != PARENT_FAILURE_REPORT_SHA256:
        raise ExecutionError("Issue #398 冻结失败报告漂移")
    validate_parent_catalog()
    validate_parent_numeric_failure()
    load_outcomes()
    if version(candidate.SDK_DISTRIBUTION) != candidate.SDK_VERSION:
        raise ExecutionError("TypeSafe SDK 版本漂移")
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
    if require_clean and _git("status", "--porcelain"):
        raise ExecutionError("正式执行前工作树必须干净")


def validate_egress() -> dict[str, Any]:
    if not EGRESS_CONFIG.is_file():
        raise ExecutionError("TypeSafe egress 配置不存在")
    if EGRESS_CONFIG.stat().st_mode & 0o777 != 0o600:
        raise ExecutionError("TypeSafe egress 配置权限漂移")
    if v1.file_sha256(EGRESS_CONFIG) != EGRESS_CONFIG_SHA256:
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
    ports = host["PortBindings"]
    binding = ports.get(EGRESS_CONTAINER_PORT)
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
    credential_mode = CREDENTIAL_FILE.stat().st_mode & 0o777
    if credential_mode != 0o600:
        raise ExecutionError("credential 文件权限必须为 600")
    return {
        "ready": True,
        "identity": IDENTITY,
        "git_commit": _git("rev-parse", "HEAD"),
        "parent_outcomes": {
            "identity": PARENT_OUTCOME_IDENTITY,
            "file_sha256": PARENT_OUTCOMES_SHA256,
            "passed": True,
        },
        "parent_model_catalog": validate_parent_catalog(),
        "parent_numeric_failure": validate_parent_numeric_failure(),
        "egress": egress,
        "credential_file_present": True,
        "credential_file_mode": "600",
        "credential_reads": 0,
        "provider_calls": 0,
        "model_tokens": 0,
        "evidence_exists": EVIDENCE_ROOT.exists(),
    }


def load_outcomes() -> dict[str, Any]:
    if v1.file_sha256(PARENT_OUTCOMES) != PARENT_OUTCOMES_SHA256:
        raise ExecutionError("v3 冻结 outcome 文件漂移")
    value = v1.load_json(PARENT_OUTCOMES)
    analysis = value.get("analysis", {})
    replay = analysis.get("replay", {})
    gates = analysis.get("gates", {})
    if (
        value.get("identity") != PARENT_OUTCOME_IDENTITY
        or analysis.get("passed") is not True
        or len(value.get("states", [])) != 36
        or len(value.get("outcomes", [])) != 288
        or len(value.get("reference_closures", [])) != 24
        or replay.get("state_action_pair_count") != 144
        or replay.get("consistent_state_action_pair_count") != 144
        or replay.get("replay_consistency") != 1.0
        or set(gates.values()) != {True}
    ):
        raise ExecutionError("v3 冻结 outcome 资格合同未通过")
    return value


def _split_data(split: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return _split_states(split), _split_labels(split)


def _split_states(split: str) -> list[dict[str, Any]]:
    if split not in PROVIDER_SPLITS:
        raise ExecutionError(f"未知 split: {split}")
    if split == "evaluation":
        return validate_evaluation_states()["states"]
    outcomes = load_outcomes()
    return [row for row in outcomes["states"] if row["qualification_split"] == split]


def _split_labels(split: str) -> list[dict[str, Any]]:
    if split not in PROVIDER_SPLITS:
        raise ExecutionError(f"未知 split: {split}")
    if split == "evaluation":
        report = v1.load_json(EVALUATION_REPORT)
        return report["analysis"]["labels"]
    outcomes = load_outcomes()
    return [row for row in outcomes["analysis"]["labels"] if row["qualification_split"] == split]


def _request_files() -> list[Path]:
    provider_root = EVIDENCE_ROOT / "provider"
    if not provider_root.exists():
        return []
    return sorted(provider_root.glob("**/requests/*.json"))


def _observation_files() -> list[Path]:
    provider_root = EVIDENCE_ROOT / "provider"
    if not provider_root.exists():
        return []
    return sorted(provider_root.glob("**/observations/*.json"))


def _attempt_files() -> list[Path]:
    provider_root = EVIDENCE_ROOT / "provider"
    if not provider_root.exists():
        return []
    return sorted(provider_root.glob("**/attempts/*.json"))


def _budget_usage() -> dict[str, Any]:
    request_count = len(_attempt_files())
    completed_request_count = 0
    input_tokens = 0
    output_tokens = 0
    cost = 0.0
    request_ids: set[str] = set()
    for path in _observation_files():
        row = v1.load_json(path)
        completed_request_count += 1
        observation = row["response_observation"]
        input_tokens += observation["usage"]["input_tokens"]
        output_tokens += observation["usage"]["output_tokens"]
        cost += observation["cost_usd"]
        request_id = observation["request_id"]
        if request_id in request_ids:
            raise ExecutionError("Provider request ID 重复")
        request_ids.add(request_id)
    return {
        "model_requests": request_count,
        "completed_model_responses": completed_request_count,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "model_cost_usd": cost,
    }


def _enforce_budget(manifest: dict[str, Any], usage: dict[str, Any]) -> None:
    authorization = manifest["authorization"]
    if usage["model_requests"] > authorization["maximum_model_requests"] or usage["input_tokens"] > authorization["maximum_input_tokens"] or usage["model_cost_usd"] > authorization["maximum_model_cost_usd"] + 1e-12:
        raise ExecutionError("Provider 硬预算越界")


def _read_credential() -> str:
    mode = CREDENTIAL_FILE.stat().st_mode & 0o777
    if mode != 0o600:
        raise ExecutionError("credential 文件权限漂移")
    key = CREDENTIAL_FILE.read_text(encoding="utf-8").strip()
    if not key or "\n" in key or "\r" in key:
        raise ExecutionError("credential 文件必须只含一行非空 API key")
    return key


def _provider_http_client() -> httpx2.Client:
    return httpx2.Client(
        proxy=EGRESS_PROXY_URL,
        trust_env=False,
        timeout=30.0,
    )


def _stage_directory(split: str, round_number: int) -> Path:
    name = f"{split}-round-{round_number}" if split == "design" else split
    return EVIDENCE_ROOT / "provider" / name


def _base_prompt_contract() -> dict[str, Any]:
    return {
        "instructions": candidate.ACTION_INSTRUCTIONS,
        "action_descriptions": dict(candidate.ACTION_DESCRIPTIONS),
    }


def _prompt_contract(round_number: int) -> dict[str, Any]:
    if round_number == 1:
        return _base_prompt_contract()
    if round_number != 2:
        raise ExecutionError("design round 只允许 1 或 2")
    amendment = v1.load_json(PROMPT_AMENDMENT)
    expected_keys = {
        "schema_version",
        "identity",
        "based_on_design_round",
        "design_analysis_canonical_sha256",
        "rationale",
        "instructions",
        "action_descriptions",
    }
    if set(amendment) != expected_keys:
        raise ExecutionError("prompt amendment 字段漂移")
    if (
        amendment["schema_version"] != "forge-jev-prompt-amendment-1.0.0"
        or amendment["identity"] != IDENTITY
        or amendment["based_on_design_round"] != 1
        or not amendment["rationale"].strip()
        or not amendment["instructions"].strip()
        or set(amendment["action_descriptions"]) != set(candidate.ACTION_FAMILIES)
        or not all(value.strip() for value in amendment["action_descriptions"].values())
    ):
        raise ExecutionError("prompt amendment 合同无效")
    round_one = v1.load_json(_stage_directory("design", 1) / "analysis.json")
    if amendment["design_analysis_canonical_sha256"] != v1.canonical_sha256(round_one):
        raise ExecutionError("prompt amendment 未绑定 design round 1 分析")
    return {
        "instructions": amendment["instructions"],
        "action_descriptions": amendment["action_descriptions"],
    }


def _provider_questions(prompt: dict[str, Any]) -> dict[str, Choice]:
    return {
        "next_action_primary": Choice(
            instructions=prompt["instructions"],
            criteria={family: prompt["action_descriptions"][family] for family in candidate.PRIMARY_ACTION_ORDER},
        ),
        "next_action_order_sensitivity": Choice(
            instructions=prompt["instructions"],
            criteria={family: prompt["action_descriptions"][family] for family in candidate.SENSITIVITY_ACTION_ORDER},
        ),
    }


def _validate_choice_answer(answer: Any) -> dict[str, Any]:
    if getattr(answer, "type", None) != "choice":
        raise ExecutionError("Jev answer type 不是 choice")
    raw_probabilities = {key: float(value) for key, value in dict(answer.probabilities).items()}
    if set(raw_probabilities) != set(candidate.ACTION_FAMILIES):
        raise ExecutionError("Jev probability key 漂移")
    if any(not 0.0 <= value <= 1.0 for value in raw_probabilities.values()):
        raise ExecutionError("Jev probability 越界")
    raw_sum = sum(raw_probabilities.values())
    if raw_sum <= 0.0 or abs(raw_sum - 1.0) > 0.005:
        raise ExecutionError("Jev probability 总和超出冻结舍入容差")
    probabilities = {key: value / raw_sum for key, value in raw_probabilities.items()}
    maximum = max(probabilities.values())
    if answer.choice not in candidate.ACTION_FAMILIES or abs(probabilities[answer.choice] - maximum) > 0.000001:
        raise ExecutionError("Jev choice 与最高概率不一致")
    expected_confidence = (maximum - 0.25) / 0.75
    if abs(float(answer.confidence) - expected_confidence) > 0.02:
        raise ExecutionError("Jev confidence 与官方公式不一致")
    return {
        "choice": answer.choice,
        "raw_probabilities": raw_probabilities,
        "raw_probability_sum": raw_sum,
        "probabilities": probabilities,
        "confidence": float(answer.confidence),
        "recomputed_confidence": expected_confidence,
    }


def _response_observation(response: Any, *, latency_ms: float) -> dict[str, Any]:
    usage = response.usage
    answers: dict[str, Any] = {}
    for key, answer in response.answers.items():
        probabilities = {name: float(value) for name, value in dict(answer.probabilities).items()}
        answers[key] = {
            "type": getattr(answer, "type", None),
            "choice": getattr(answer, "choice", None),
            "probabilities": probabilities,
            "raw_probability_sum": sum(probabilities.values()),
            "confidence": getattr(answer, "confidence", None),
        }
    return {
        "model": response.model,
        "request_id": response.request_id,
        "answers": answers,
        "usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        },
        "cost_usd": usage.input_tokens * candidate.INPUT_PRICE_USD_PER_MILLION_TOKENS / 1_000_000,
        "latency_ms": latency_ms,
    }


def normalize_response(response: Any, *, latency_ms: float) -> dict[str, Any]:
    if response.model != candidate.MODEL_ID:
        raise ExecutionError(f"Jev 响应模型漂移: {response.model}")
    if set(response.answers) != set(candidate.QUESTION_IDS):
        raise ExecutionError("Jev answer 集合漂移")
    if not response.request_id:
        raise ExecutionError("Jev 响应缺少 request id")
    usage = response.usage
    if usage.input_tokens is None or usage.output_tokens is None:
        raise ExecutionError("Jev 响应缺少 token usage")
    if usage.input_tokens < 0 or usage.output_tokens < 0:
        raise ExecutionError("Jev token usage 非法")
    return {
        "model": response.model,
        "request_id": response.request_id,
        "answers": {key: _validate_choice_answer(response.answers[key]) for key in candidate.QUESTION_IDS},
        "usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        },
        "cost_usd": usage.input_tokens * candidate.INPUT_PRICE_USD_PER_MILLION_TOKENS / 1_000_000,
        "latency_ms": latency_ms,
        "order_agreement": (response.answers["next_action_primary"].choice == response.answers["next_action_order_sensitivity"].choice),
    }


def _responses(split: str, round_number: int = 1, *, require_completed: bool = True) -> list[dict[str, Any]]:
    stage = _stage_directory(split, round_number)
    if (stage / "failed.json").exists():
        raise ExecutionError(f"{split} Provider stage 已失败")
    if require_completed and not (stage / "completed.json").is_file():
        raise ExecutionError(f"{split} Provider stage 尚未完整封存")
    directory = stage / "requests"
    if not directory.is_dir():
        raise ExecutionError(f"{split} Provider 响应不存在")
    rows = [v1.load_json(path) for path in sorted(directory.glob("*.json"))]
    if len(rows) != 18:
        raise ExecutionError(f"{split} Provider 响应不完整")
    return rows


def _analyse_predictions(split: str, responses: list[dict[str, Any]]) -> dict[str, Any]:
    states, labels = _split_data(split)
    labels_by_state = {row["state_id"]: row for row in labels}
    states_by_id = {row["state_id"]: row for row in states}
    rows: list[dict[str, Any]] = []
    for response in responses:
        state_id = response["state_id"]
        label = labels_by_state[state_id]
        primary = response["response"]["answers"]["next_action_primary"]
        sensitivity = response["response"]["answers"]["next_action_order_sensitivity"]
        choice = primary["choice"]
        rows.append(
            {
                "state_id": state_id,
                "project_family": label["project_family"],
                "build_system": label["build_system"],
                "choice": choice,
                "optimal_action": label["optimal_action"],
                "successful_actions": label["successful_actions"],
                "top1_correct": choice == label["optimal_action"],
                "route_acceptable": choice in label["successful_actions"],
                "direct_choice": choice in DIRECT_ACTIONS,
                "order_agreement": choice == sensitivity["choice"],
                "probabilities": primary["probabilities"],
                "confidence": primary["confidence"],
                "latency_ms": response["response"]["latency_ms"],
                "usage": response["response"]["usage"],
                "cost_usd": response["response"]["cost_usd"],
                "semantic_failure_log_sha256": _bytes_sha256(
                    states_by_id[state_id]
                    .get(
                        "semantic_failure_log",
                        states_by_id[state_id]["model_input"]["semantic_failure_log"],
                    )
                    .encode()
                ),
            }
        )
    rows.sort(key=lambda row: row["state_id"])
    return {
        "split": split,
        "state_count": len(rows),
        "top1_correct": sum(row["top1_correct"] for row in rows),
        "route_acceptable_count": sum(row["route_acceptable"] for row in rows),
        "direct_choice_count": sum(row["direct_choice"] for row in rows),
        "order_agreement_count": sum(row["order_agreement"] for row in rows),
        "rows": rows,
    }


def _validate_provider_stage_request(split: str, round_number: int) -> None:
    if split == "design":
        if round_number not in (1, 2):
            raise ExecutionError("design round 只允许 1 或 2")
        if (EVIDENCE_ROOT / "prompt-freeze.json").exists() or (EVIDENCE_ROOT / "design-terminal.json").exists():
            raise ExecutionError("design 已进入终态")
        if round_number == 2:
            review_path = EVIDENCE_ROOT / "design-round-1-review.json"
            if not review_path.is_file():
                raise ExecutionError("design round 2 缺少 round 1 失败审计")
            review = v1.load_json(review_path)
            if review.get("decision") != "amend_prompt_and_run_round_2":
                raise ExecutionError("design round 1 未授权 prompt amendment")
            if not (_stage_directory("design", 1) / "completed.json").is_file():
                raise ExecutionError("design round 1 未完整封存")
            _prompt_contract(2)
        return
    if round_number != 1:
        raise ExecutionError(f"{split} 只允许 round 1")
    freeze_path = EVIDENCE_ROOT / "prompt-freeze.json"
    if not freeze_path.is_file() or v1.load_json(freeze_path).get("passed") is not True:
        raise ExecutionError("进入 calibration/evaluation 前必须冻结通过的 prompt")
    if split == "evaluation":
        calibration_path = EVIDENCE_ROOT / "calibration.json"
        if not calibration_path.is_file():
            raise ExecutionError("evaluation 前缺少 calibration")
        calibration = v1.load_json(calibration_path)
        if calibration["passed"] is not True:
            raise ExecutionError("calibration 未通过，禁止 evaluation")


def run_provider(split: str, round_number: int) -> dict[str, Any]:
    manifest = validate_execution_manifest()
    _assert_revision(manifest, require_clean=True)
    load_outcomes()
    validate_parent_catalog()
    validate_egress()
    _validate_provider_stage_request(split, round_number)
    directory = _stage_directory(split, round_number)
    if directory.exists():
        raise ExecutionError(f"{split} Provider stage 已存在，禁止 retry/backfill")
    current = _budget_usage()
    _enforce_budget(manifest, current)
    states = _split_states(split)
    if len(states) != 18:
        raise ExecutionError(f"{split} 状态数漂移")
    directory.mkdir(parents=True, mode=0o700)
    _write_once_json(
        directory / "started.json",
        {
            "identity": IDENTITY,
            "split": split,
            "round": round_number,
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
        if split == "design":
            prompt_round = round_number
        else:
            prompt_round = int(v1.load_json(EVIDENCE_ROOT / "prompt-freeze.json")["design_round"])
        prompt = _prompt_contract(prompt_round)
        prompt_sha256 = v1.canonical_sha256(prompt)
        with _provider_http_client() as http_client:
            with TypeSafeClient(
                api_key=key,
                model=candidate.MODEL_ID,
                retry=RetryPolicy(max_retries=0, timeout=30.0),
                base_url=candidate.API_BASE_URL,
                http_client=http_client,
            ) as client:
                for index, state in enumerate(sorted(states, key=lambda row: row["state_id"]), start=1):
                    before = _budget_usage()
                    if before["model_requests"] >= manifest["authorization"]["maximum_model_requests"]:
                        raise ExecutionError("Provider request 预算已耗尽")
                    provider_state = candidate.provider_state(state["model_input"])
                    questions = _provider_questions(prompt)
                    _write_once_json(
                        directory / "attempts" / f"{index:02d}-{state['state_id']}.json",
                        {
                            "identity": IDENTITY,
                            "split": split,
                            "round": round_number,
                            "sequence": index,
                            "state_id": state["state_id"],
                            "created_at": _now(),
                            "git_commit": _git("rev-parse", "HEAD"),
                            "model": candidate.MODEL_ID,
                            "prompt_contract_canonical_sha256": prompt_sha256,
                            "request_fingerprint": candidate.request_fingerprint(provider_state, questions),
                        },
                    )
                    started = time.perf_counter()
                    response = client.system_one(state=provider_state, questions=questions)
                    latency_ms = (time.perf_counter() - started) * 1000
                    observation = _response_observation(response, latency_ms=latency_ms)
                    _write_once_json(
                        directory / "observations" / f"{index:02d}-{state['state_id']}.json",
                        {
                            "identity": IDENTITY,
                            "split": split,
                            "round": round_number,
                            "sequence": index,
                            "state_id": state["state_id"],
                            "request_fingerprint": candidate.request_fingerprint(provider_state, questions),
                            "response_observation": observation,
                        },
                    )
                    normalized = normalize_response(response, latency_ms=latency_ms)
                    row = {
                        "identity": IDENTITY,
                        "split": split,
                        "round": round_number,
                        "sequence": index,
                        "state_id": state["state_id"],
                        "request_fingerprint": candidate.request_fingerprint(provider_state, questions),
                        "prompt_contract_canonical_sha256": prompt_sha256,
                        "response": normalized,
                    }
                    _write_once_json(
                        directory / "requests" / f"{index:02d}-{state['state_id']}.json",
                        row,
                    )
                    _enforce_budget(manifest, _budget_usage())
        key = None
        responses = _responses(split, round_number, require_completed=False)
        analysis = _analyse_predictions(split, responses)
        _write_once_json(directory / "analysis.json", analysis)
        _write_once_json(
            directory / "completed.json",
            {
                "identity": IDENTITY,
                "split": split,
                "round": round_number,
                "status": "completed",
                "created_at": _now(),
                "credential_reads": credential_reads,
                "provider_calls": 18,
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
                "round": round_number,
                "status": "failed",
                "created_at": _now(),
                "error_type": type(exc).__name__,
                "request_id": getattr(exc, "request_id", None),
                "credential_reads": credential_reads,
                "budget_after": _budget_usage(),
            },
        )
        raise


def freeze_prompt(round_number: int) -> dict[str, Any]:
    if round_number not in (1, 2):
        raise ExecutionError("design round 只允许 1 或 2")
    if (EVIDENCE_ROOT / "prompt-freeze.json").exists() or (EVIDENCE_ROOT / "design-terminal.json").exists():
        raise ExecutionError("design 已进入终态")
    if not (_stage_directory("design", round_number) / "completed.json").is_file():
        raise ExecutionError("design Provider stage 尚未完整封存")
    analysis = _analyse_predictions("design", _responses("design", round_number))
    passed = analysis["top1_correct"] >= 15 and analysis["order_agreement_count"] >= 16
    result = {
        "identity": IDENTITY,
        "created_at": _now(),
        "design_round": round_number,
        "question_contract_sha256": v1.canonical_sha256(_prompt_contract(round_number)),
        "design_analysis": analysis,
        "passed": passed,
        "prompt_adjusted_after_design": round_number == 2,
    }
    if passed:
        result["decision"] = "freeze_prompt_and_proceed_to_calibration"
        _write_once_json(EVIDENCE_ROOT / "prompt-freeze.json", result)
    elif round_number == 1:
        result["decision"] = "amend_prompt_and_run_round_2"
        _write_once_json(EVIDENCE_ROOT / "design-round-1-review.json", result)
    else:
        result["decision"] = "stop_jev_controller_after_design"
        _write_once_json(EVIDENCE_ROOT / "design-terminal.json", result)
    return result


def _logit(probability: float) -> float:
    clipped = min(0.999999, max(0.000001, probability))
    return math.log(clipped / (1.0 - clipped))


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def _select_zero_error_threshold(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    thresholds = sorted({row["calibrated_safe_probability"] for row in candidates}, reverse=True)
    feasible: list[dict[str, Any]] = []
    for threshold in thresholds:
        selected = [row for row in candidates if row["calibrated_safe_probability"] >= threshold]
        errors = sum(not row["route_acceptable"] for row in selected)
        if errors == 0:
            feasible.append({"threshold": threshold, "coverage": len(selected), "errors": errors})
    if not feasible:
        raise ExecutionError("calibration 无零错误门槛")
    return max(feasible, key=lambda row: (row["coverage"], row["threshold"]))


def calibrate() -> dict[str, Any]:
    path = EVIDENCE_ROOT / "calibration.json"
    if path.exists():
        raise ExecutionError("calibration 已存在，禁止重算")
    responses = _responses("calibration")
    states, labels = _split_data("calibration")
    _ = states
    labels_by_state = {row["state_id"]: row for row in labels}
    x: list[list[float]] = []
    y: list[int] = []
    for response in responses:
        state_id = response["state_id"]
        probabilities = response["response"]["answers"]["next_action_primary"]["probabilities"]
        for action in DIRECT_ACTIONS:
            x.append([_logit(probabilities[action])])
            y.append(int(action in labels_by_state[state_id]["successful_actions"]))
    if set(y) != {0, 1}:
        raise ExecutionError("calibration 缺少正负标签")
    model = LogisticRegression(
        C=1.0,
        solver="liblinear",
        random_state=393,
        max_iter=1000,
    )
    model.fit(x, y)
    coefficient = float(model.coef_[0][0])
    intercept = float(model.intercept_[0])
    analysis = _analyse_predictions("calibration", responses)
    candidates: list[dict[str, Any]] = []
    for row in analysis["rows"]:
        probability = row["probabilities"][row["choice"]]
        calibrated = _sigmoid(coefficient * _logit(probability) + intercept)
        row["calibrated_safe_probability"] = calibrated
        if row["direct_choice"] and row["order_agreement"]:
            candidates.append(row)
    selected_threshold = _select_zero_error_threshold(candidates)
    result = {
        "identity": IDENTITY,
        "created_at": _now(),
        "model": {
            "coefficient": coefficient,
            "intercept": intercept,
            "c": 1.0,
            "solver": "liblinear",
            "random_state": 393,
            "max_iter": 1000,
            "training_pair_count": len(y),
            "positive_count": sum(y),
            "negative_count": len(y) - sum(y),
        },
        "threshold": selected_threshold,
        "analysis": analysis,
        "passed": selected_threshold["coverage"] >= 6,
        "decision": "proceed_to_single_evaluation" if selected_threshold["coverage"] >= 6 else "stop_before_evaluation",
    }
    _write_once_json(path, result)
    return result


def _tfidf_evaluation() -> dict[str, Any]:
    train_states: list[dict[str, Any]] = []
    train_labels: list[dict[str, Any]] = []
    for split in ("design", "calibration"):
        states, labels = _split_data(split)
        train_states.extend(states)
        train_labels.extend(labels)
    evaluation_states, evaluation_labels = _split_data("evaluation")
    labels_by_state = {row["state_id"]: row["optimal_action"] for row in train_labels}
    evaluation_by_state = {row["state_id"]: row["optimal_action"] for row in evaluation_labels}
    vectorizer = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 2),
        sublinear_tf=True,
        max_features=5000,
    )
    x_train = vectorizer.fit_transform(row.get("semantic_failure_log", row["model_input"]["semantic_failure_log"]) for row in train_states)
    x_test = vectorizer.transform(row.get("semantic_failure_log", row["model_input"]["semantic_failure_log"]) for row in evaluation_states)
    classifier = OneVsRestClassifier(
        LogisticRegression(
            C=1.0,
            solver="liblinear",
            random_state=391,
            max_iter=1000,
        )
    )
    classifier.fit(x_train, [labels_by_state[row["state_id"]] for row in train_states])
    predictions = classifier.predict(x_test)
    rows = [
        {
            "state_id": state["state_id"],
            "prediction": str(prediction),
            "optimal_action": evaluation_by_state[state["state_id"]],
            "correct": str(prediction) == evaluation_by_state[state["state_id"]],
        }
        for state, prediction in zip(evaluation_states, predictions, strict=True)
    ]
    return {
        "training_state_count": len(train_states),
        "evaluation_state_count": len(rows),
        "top1_correct": sum(row["correct"] for row in rows),
        "rows": sorted(rows, key=lambda row: row["state_id"]),
    }


def _calibrated_probability(calibration: dict[str, Any], probability: float) -> float:
    model = calibration["model"]
    return _sigmoid(model["coefficient"] * _logit(probability) + model["intercept"])


def _prediction_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    classes = sorted({row["choice"] for row in rows} | {row["optimal_action"] for row in rows})
    f1_by_class: dict[str, float] = {}
    for action in classes:
        true_positive = sum(row["choice"] == action and row["optimal_action"] == action for row in rows)
        false_positive = sum(row["choice"] == action and row["optimal_action"] != action for row in rows)
        false_negative = sum(row["choice"] != action and row["optimal_action"] == action for row in rows)
        denominator = 2 * true_positive + false_positive + false_negative
        f1_by_class[action] = 0.0 if denominator == 0 else 2 * true_positive / denominator
    probability_classes = list(candidate.ACTION_FAMILIES)
    multiclass_brier = sum(sum((row["probabilities"][action] - float(row["optimal_action"] == action)) ** 2 for action in probability_classes) for row in rows) / len(rows)
    bins: list[dict[str, Any]] = []
    ece = 0.0
    for index in range(5):
        lower = index / 5
        upper = (index + 1) / 5
        selected = [row for row in rows if lower <= max(row["probabilities"].values()) and (max(row["probabilities"].values()) < upper or (index == 4 and max(row["probabilities"].values()) <= upper))]
        if not selected:
            bins.append(
                {
                    "lower": lower,
                    "upper": upper,
                    "count": 0,
                    "mean_confidence": None,
                    "accuracy": None,
                }
            )
            continue
        mean_confidence = sum(max(row["probabilities"].values()) for row in selected) / len(selected)
        accuracy = sum(row["top1_correct"] for row in selected) / len(selected)
        ece += len(selected) / len(rows) * abs(accuracy - mean_confidence)
        bins.append(
            {
                "lower": lower,
                "upper": upper,
                "count": len(selected),
                "mean_confidence": mean_confidence,
                "accuracy": accuracy,
            }
        )
    latencies = sorted(float(row["latency_ms"]) for row in rows)
    p95_index = max(0, math.ceil(0.95 * len(latencies)) - 1)
    by_system: dict[str, Any] = {}
    for build_system in candidate.BUILD_SYSTEMS:
        system_rows = [row for row in rows if row["build_system"] == build_system]
        by_system[build_system] = {
            "state_count": len(system_rows),
            "top1_correct": sum(row["top1_correct"] for row in system_rows),
            "route_acceptable_count": sum(row["route_acceptable"] for row in system_rows),
            "order_agreement_count": sum(row["order_agreement"] for row in system_rows),
        }
    return {
        "macro_f1": sum(f1_by_class.values()) / len(f1_by_class),
        "macro_f1_classes": classes,
        "f1_by_class": f1_by_class,
        "multiclass_brier_score": multiclass_brier,
        "brier_definition": "mean sum of squared class-probability errors",
        "ece_5_equal_width_bins": ece,
        "ece_bins": bins,
        "latency_ms": {
            "mean": sum(latencies) / len(latencies),
            "median": (latencies[(len(latencies) - 1) // 2] + latencies[len(latencies) // 2]) / 2,
            "p95_nearest_rank": latencies[p95_index],
            "total": sum(latencies),
        },
        "usage": {
            "input_tokens": sum(row["usage"]["input_tokens"] for row in rows),
            "output_tokens": sum(row["usage"]["output_tokens"] for row in rows),
            "model_cost_usd": sum(row["cost_usd"] for row in rows),
        },
        "by_build_system": by_system,
    }


def _risk_coverage_curve(rows: list[dict[str, Any]], calibration: dict[str, Any]) -> list[dict[str, Any]]:
    eligible: list[dict[str, Any]] = []
    for row in rows:
        if not row["direct_choice"] or not row["order_agreement"]:
            continue
        probability = _calibrated_probability(calibration, row["probabilities"][row["choice"]])
        eligible.append({**row, "calibrated_safe_probability": probability})
    curve: list[dict[str, Any]] = []
    for threshold in sorted({row["calibrated_safe_probability"] for row in eligible}, reverse=True):
        selected = [row for row in eligible if row["calibrated_safe_probability"] >= threshold]
        errors = sum(not row["route_acceptable"] for row in selected)
        curve.append(
            {
                "threshold": threshold,
                "selected_count": len(selected),
                "coverage": len(selected) / len(rows),
                "error_count": errors,
                "risk": errors / len(selected),
            }
        )
    return curve


def _evidence_inventory() -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(EVIDENCE_ROOT).as_posix(),
            "size": path.stat().st_size,
            "sha256": v1.file_sha256(path),
        }
        for path in sorted(EVIDENCE_ROOT.rglob("*"))
        if path.is_file()
    ]


def _parent_outcome_summary() -> dict[str, Any]:
    outcomes = load_outcomes()
    analysis = outcomes["analysis"]
    return {
        "identity": outcomes["identity"],
        "file_sha256": PARENT_OUTCOMES_SHA256,
        "passed": analysis["passed"],
        "state_count": len(outcomes["states"]),
        "action_outcome_count": len(outcomes["outcomes"]),
        "reference_closure_count": len(outcomes["reference_closures"]),
        "replay": analysis["replay"],
        "split_metrics": analysis["split_metrics"],
        "gates": analysis["gates"],
    }


def _write_report(report: dict[str, Any]) -> dict[str, Any]:
    report["evidence_inventory"] = _evidence_inventory()
    report["evidence_inventory_canonical_sha256"] = v1.canonical_sha256(report["evidence_inventory"])
    _write_once_json(JSON_REPORT, report)
    v1.write_once(MARKDOWN_REPORT, render_markdown(report))
    return report


def build_report() -> dict[str, Any]:
    if JSON_REPORT.exists() or MARKDOWN_REPORT.exists():
        raise ExecutionError("正式报告已存在，禁止覆盖")
    manifest = validate_execution_manifest()
    parent_outcome = _parent_outcome_summary()
    common = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "document_type": "forge_jev_offline_qualification_report",
        "identity": IDENTITY,
        "issue_url": ISSUE_URL,
        "created_at": _now(),
        "git_commit": _git("rev-parse", "HEAD"),
        "manifest_canonical_sha256": v1.canonical_sha256(manifest),
        "parent_outcome_qualification": parent_outcome,
        "parent_model_catalog": validate_parent_catalog(),
        "parent_numeric_failure": validate_parent_numeric_failure(),
        "budget": _budget_usage(),
        "interpretation": {
            "jev_offline_action_qualification_estimated": False,
            "controller_effect_estimated": False,
            "strict_success_noninferiority_estimated": False,
            "temporal_generalization_estimated": False,
            "natural_failure_population_estimated": False,
            "historical_evidence_modified": False,
        },
    }
    provider_failure_path = _stage_directory("design", 1) / "failed.json"
    if provider_failure_path.is_file():
        return _write_report(
            {
                **common,
                "terminal_stage": "provider_design",
                "design": v1.load_json(provider_failure_path),
                "calibration": None,
                "evaluation": None,
                "gates": {"fixed_model_provider_execution": False},
                "passed": False,
                "decision": "stop_jev_controller_and_keep_offline_result",
            }
        )
    design_terminal_path = EVIDENCE_ROOT / "design-terminal.json"
    if design_terminal_path.is_file():
        return _write_report(
            {
                **common,
                "terminal_stage": "design",
                "design": v1.load_json(design_terminal_path),
                "calibration": None,
                "evaluation": None,
                "gates": {"fixed_model_provider_execution": True, "design_qualification": False},
                "passed": False,
                "decision": "stop_jev_controller_and_keep_offline_result",
            }
        )
    calibration_path = EVIDENCE_ROOT / "calibration.json"
    if not calibration_path.is_file():
        raise ExecutionError("calibration 尚未完成，不能生成终态报告")
    calibration = v1.load_json(calibration_path)
    freeze = v1.load_json(EVIDENCE_ROOT / "prompt-freeze.json")
    design = v1.load_json(_stage_directory("design", freeze["design_round"]) / "analysis.json")
    if calibration["passed"] is not True:
        return _write_report(
            {
                **common,
                "terminal_stage": "calibration",
                "design": design,
                "calibration": calibration,
                "evaluation": None,
                "gates": {
                    "fixed_model_provider_execution": True,
                    "design_qualification": True,
                    "calibration_direct_coverage": False,
                },
                "passed": False,
                "decision": "stop_jev_controller_and_keep_offline_result",
            }
        )
    evaluation_responses = _responses("evaluation")
    evaluation = _analyse_predictions("evaluation", evaluation_responses)
    threshold = calibration["threshold"]["threshold"]
    direct_rows: list[dict[str, Any]] = []
    for row in evaluation["rows"]:
        raw_probability = row["probabilities"][row["choice"]]
        calibrated_probability = _calibrated_probability(calibration, raw_probability)
        row["calibrated_safe_probability"] = calibrated_probability
        row["direct_execute"] = bool(row["direct_choice"] and row["order_agreement"] and calibrated_probability >= threshold)
        if row["direct_execute"]:
            direct_rows.append(row)
    wrong_direct = sum(not row["route_acceptable"] for row in direct_rows)
    correct_direct_systems = {row["build_system"] for row in direct_rows if row["top1_correct"] and row["route_acceptable"]}
    gates = {
        "fixed_model_provider_execution": True,
        "design_qualification": True,
        "calibration_direct_coverage": True,
        "evaluation_top1": evaluation["top1_correct"] >= 15,
        "direct_coverage": len(direct_rows) >= 6,
        "zero_wrong_direct_actions": wrong_direct == 0,
        "order_agreement": evaluation["order_agreement_count"] >= 16,
        "all_build_systems_correct_direct": correct_direct_systems == set(candidate.BUILD_SYSTEMS),
    }
    budget = _budget_usage()
    _enforce_budget(manifest, budget)
    gates["budget"] = True
    passed = all(gates.values())
    report = {
        **common,
        "terminal_stage": "evaluation",
        "design": design,
        "calibration": calibration,
        "evaluation": evaluation,
        "calibrated_gate": {
            "threshold": threshold,
            "direct_execution_count": len(direct_rows),
            "wrong_direct_action_count": wrong_direct,
            "correct_direct_build_systems": sorted(correct_direct_systems),
            "rejection_count": len(evaluation["rows"]) - len(direct_rows),
            "rejection_rate": 1 - len(direct_rows) / len(evaluation["rows"]),
            "risk_coverage_curve": _risk_coverage_curve(evaluation["rows"], calibration),
            "rows": direct_rows,
        },
        "baselines": {
            "rule_gate": {
                "fixed_choice": "build",
                "top1_correct": sum(row["optimal_action"] == "build" for row in evaluation["rows"]),
                "route_acceptable_count": sum("build" in row["successful_actions"] for row in evaluation["rows"]),
            },
            "tfidf_logistic_regression": _tfidf_evaluation(),
        },
        "budget": budget,
        "supporting_metrics": _prediction_metrics(evaluation["rows"]),
        "gates": gates,
        "passed": passed,
        "decision": ("proceed_to_controller_replay_qualification" if passed else "stop_jev_controller_and_keep_offline_result"),
        "interpretation": {
            **common["interpretation"],
            "jev_offline_action_qualification_estimated": True,
        },
    }
    return _write_report(report)


def render_markdown(report: dict[str, Any]) -> str:
    evaluation = report["evaluation"]
    if evaluation is None:
        if report["terminal_stage"] == "provider_design":
            observed = "固定 `jev-1.13.0` 的首轮 design Provider stage 失败关闭。"
            conclusion = "该结果不估计 Jev 的动作选择能力。"
        elif report["terminal_stage"] == "design":
            observed = f"Design round {report['design']['design_round']} 未达到 15/18 top-1 与 16/18 顺序一致门槛。"
            conclusion = "Jev 未通过预注册离线门槛，本方向停止在 controller 之前；保留 outcome benchmark 与负结果。"
        else:
            observed = f"Calibration 零观察错误直接执行覆盖为 {report['calibration']['threshold']['coverage']}/18，低于 6/18。"
            conclusion = "Jev 未通过预注册离线门槛，本方向停止在 controller 之前；保留 outcome benchmark 与负结果。"
        return f"""# Jev 离线资格实验 v6 结果

- identity：`{IDENTITY}`
- 决定：`{report["decision"]}`
- 停止阶段：`{report["terminal_stage"]}`
- Provider 请求：`{report["budget"]["model_requests"]}`
- Input tokens：`{report["budget"]["input_tokens"]}`
- Jev 模型费用：`${report["budget"]["model_cost_usd"]:.8f}`

## 结论

{observed} {conclusion}

## 解释边界

该停止决定没有执行 evaluation，因此不能估计 evaluation holdout 表现、controller treatment effect、严格成功率非劣、端到端成本节省、跨时间泛化或自然失败总体表现。
"""
    gate = report["calibrated_gate"]
    tfidf = report["baselines"]["tfidf_logistic_regression"]
    metrics = report["supporting_metrics"]
    return f"""# Jev 离线资格实验 v6 结果

- identity：`{IDENTITY}`
- 决定：`{report["decision"]}`
- Evaluation top-1：`{evaluation["top1_correct"]}/18`
- 正反顺序一致：`{evaluation["order_agreement_count"]}/18`
- 校准门禁直接执行覆盖：`{gate["direct_execution_count"]}/18`
- 错误直接动作：`{gate["wrong_direct_action_count"]}`
- TF-IDF/逻辑回归：`{tfidf["top1_correct"]}/18`
- Macro-F1：`{metrics["macro_f1"]:.6f}`
- Multiclass Brier：`{metrics["multiclass_brier_score"]:.6f}`
- ECE（5 个等宽区间）：`{metrics["ece_5_equal_width_bins"]:.6f}`
- Provider 请求：`{report["budget"]["model_requests"]}`
- Input tokens：`{report["budget"]["input_tokens"]}`
- Jev 模型费用：`${report["budget"]["model_cost_usd"]:.8f}`

## 结论

{"Jev 通过离线动作与校准门槛，可以进入冻结响应的零 Provider controller 回放资格；这还不是端到端收益证据。" if report["passed"] else "Jev 未通过预注册离线门槛，本方向停止在 controller 之前；保留 outcome benchmark 与负结果。"}

## 门槛

```json
{json.dumps(report["gates"], ensure_ascii=False, indent=2, sort_keys=True)}
```

## 解释边界

本实验只估计固定受控故障 holdout 上的动作选择、顺序稳定性和校准门禁。它不估计 controller treatment effect、严格成功率非劣、端到端成本节省、跨时间泛化或自然失败总体表现。
"""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    bind = subparsers.add_parser("bind-execution")
    bind.add_argument("--implementation-revision", required=True)
    for command in (
        "generate-evaluation-states",
        "validate",
        "preflight",
        "calibrate",
        "report",
    ):
        subparsers.add_parser(command)
    provider = subparsers.add_parser("run-provider")
    provider.add_argument("--split", choices=PROVIDER_SPLITS, required=True)
    provider.add_argument("--round", type=int, default=1)
    freeze = subparsers.add_parser("freeze-prompt")
    freeze.add_argument("--round", type=int, default=1)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "bind-execution":
        manifest = bind_execution(args.implementation_revision)
        print(v1.canonical_sha256(manifest))
        return 0
    if args.command == "generate-evaluation-states":
        print(v1.canonical_sha256(write_evaluation_states()))
        return 0
    if args.command == "validate":
        print(v1.canonical_sha256(validate_execution_manifest()))
        return 0
    if args.command == "preflight":
        print(json.dumps(preflight(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "run-provider":
        print(
            json.dumps(
                run_provider(args.split, args.round),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "freeze-prompt":
        print(json.dumps(freeze_prompt(args.round), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "calibrate":
        print(json.dumps(calibrate(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
