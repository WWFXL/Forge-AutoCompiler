#!/usr/bin/env python3
"""Issue #395 Jev 离线资格实验的授权执行器。"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import math
import re
import shlex
import subprocess
import tempfile
import time
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import forge_jev_offline_qualification_candidate as candidate
import forge_typed_action_benchmark_qualification as v1
import forge_typed_semantic_routing_pilot_v2 as pilot
import jsonschema
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from typesafe_sdk import Choice, RetryPolicy, TypeSafeClient

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
IDENTITY = "cpp-jev-offline-qualification-v1"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/395"
BRANCH = "yiwei/395-jev-offline-execution"
SCHEMA_VERSION = "forge-jev-offline-qualification-execution-1.0.0"
REPORT_SCHEMA_VERSION = "forge-jev-offline-qualification-report-1.0.0"

SOURCE_POOL = candidate.DEFAULT_SOURCE_POOL
CANDIDATE_MANIFEST = candidate.DEFAULT_MANIFEST
EVALUATION_REPORT = candidate.V2_REPORT
EVALUATION_STATES = REPO_ROOT / "benchmarks/fixtures/cpp-jev-offline-qualification-evaluation-states-v1.json"
EXECUTION_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-jev-offline-qualification-v1.json"
EXECUTION_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-jev-offline-qualification-v1.schema.json"
AMENDMENT = REPO_ROOT / "benchmarks/preregistrations/cpp-jev-offline-qualification-v1-execution-amendment.md"
EVIDENCE_ROOT = REPO_ROOT / ".compile-sessions/benchmark-evidence-jev-offline-qualification-v1"
JSON_REPORT = REPO_ROOT / "benchmarks/reports/cpp-jev-offline-qualification-v1.json"
MARKDOWN_REPORT = REPO_ROOT / "benchmarks/reports/cpp-jev-offline-qualification-v1.md"
CREDENTIAL_FILE = REPO_ROOT / "jev-apikey.txt"
PROMPT_AMENDMENT = REPO_ROOT / "benchmarks/preregistrations/cpp-jev-offline-qualification-v1-prompt-amendment.json"

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


def generate_execution_manifest(*, implementation_revision: str, runner_sha256: str) -> dict[str, Any]:
    parent = v1.load_json(CANDIDATE_MANIFEST)
    pool = v1.load_json(SOURCE_POOL)
    evaluation_states = validate_evaluation_states()
    return {
        "$schema": "../schemas/forge-jev-offline-qualification-v1.schema.json",
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
            "docker_outcome_collection_authorized": True,
            "new_identity_evidence_write_authorized": True,
            "controller_implementation_authorized": False,
            "historical_evidence_write_authorized": False,
        },
        "data_contract": {
            "source_pool_path": SOURCE_POOL.relative_to(REPO_ROOT).as_posix(),
            "source_pool_canonical_sha256": v1.canonical_sha256(pool),
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
        "environment": {
            "dockerfile_path": "docker/compile/Dockerfile.stage-c",
            "image_tag": "autocompiler:stage-c-v1",
            "expected_image_id": "sha256:adbef4a26de49e9cd2c361a50b5fe2a000073a343b072ed0e515cc67e6e758b1",
            "network_during_clone": True,
            "network_during_action": False,
            "parallel_jobs": 4,
            "per_action_timeout_seconds": 900,
            "replicates": 2,
        },
        "outcome_collection": {
            "project_count": 12,
            "faults_per_project": 3,
            "actions_per_state": 4,
            "state_count": 36,
            "state_action_pair_count": 144,
            "action_branch_count": 288,
            "reference_closure_count": 24,
            "minimum_replay_consistency": 0.95,
            "fault_types": list(candidate.FAULT_TYPES),
            "action_order": list(candidate.ACTION_FAMILIES),
            "action_costs": candidate.ACTION_COSTS,
            "invalid_build_state_path_field": "build_state_file",
            "label_rule": "strict_success_then_minimum_frozen_action_cost",
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
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-jev-offline-qualification-v1.schema.json",
        "title": "Forge Jev offline qualification execution v1",
        "const": manifest,
    }


def generate_execution_amendment(manifest: dict[str, Any]) -> str:
    authorization = manifest["authorization"]
    schedule = manifest["provider_schedule"]
    return f"""# Jev 离线资格实验 v1 授权执行补充

## 身份

- Formal identity：`{IDENTITY}`
- Tracking Issue：[#395]({ISSUE_URL})
- Parent candidate：`cpp-jev-offline-qualification-candidate-v1`
- Parent revision：`{manifest["parent_candidate"]["git_revision"]}`
- Implementation revision：`{manifest["implementation"]["git_revision"]}`
- Runner SHA-256：`{manifest["implementation"]["runner_sha256"]}`
- Manifest canonical SHA-256：`{v1.canonical_sha256(manifest)}`

## 授权与预算

本 identity 已获研究负责人授权读取仓库根 `jev-apikey.txt`、调用固定
`jev-1.13.0`、执行 Docker outcome collection，并写入本 identity 的
create-once evidence。credential 和 Authorization header 不得进入日志、
evidence 或 Git。

- 最大 Provider 请求：`{authorization["maximum_model_requests"]}`
- 最大 input tokens：`{authorization["maximum_input_tokens"]}`
- 最大模型费用：`${authorization["maximum_model_cost_usd"]}`
- Design：首轮 `{schedule["design_round_1_requests"]}` 请求；仅首轮失败时允许一次版本化 prompt amendment 和最多 `{schedule["design_round_2_maximum_requests"]}` 请求
- Calibration：`{schedule["calibration_requests"]}` 请求
- Evaluation：一次性 `{schedule["evaluation_requests"]}` 请求

## 执行和停止边界

先完成 12 个 design/calibration 项目族的零 Provider outcome qualification；
只有 reference closure、重复一致性、动作覆盖、候选有界终结和泄漏审计
全部通过才可读取 credential。Calibration 覆盖低于 `6/18` 时停止，不运行
evaluation。Evaluation 的 top-1、直接覆盖、错误直接动作、顺序一致性、
构建系统覆盖或预算任一门槛失败，决定均为
`stop_jev_controller_and_keep_offline_result`。

本 identity 不授权修改历史 evidence，不授权 retry、replacement、backfill
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


def preflight(*, require_clean: bool = True) -> dict[str, Any]:
    manifest = validate_execution_manifest()
    _assert_revision(manifest, require_clean=require_clean)
    if not AMENDMENT.is_file():
        raise ExecutionError("缺少 execution amendment")
    v1.require_zero_managed_resources()
    image = v1.current_image_id(manifest)
    credential_mode = CREDENTIAL_FILE.stat().st_mode & 0o777
    if credential_mode != 0o600:
        raise ExecutionError("credential 文件权限必须为 600")
    return {
        "ready": True,
        "identity": IDENTITY,
        "git_commit": _git("rev-parse", "HEAD"),
        "image_id": image,
        "credential_file_present": True,
        "credential_file_mode": "600",
        "credential_reads": 0,
        "provider_calls": 0,
        "model_tokens": 0,
        "evidence_exists": EVIDENCE_ROOT.exists(),
    }


def _formal_fault_trigger(task: dict[str, Any], fault_type: str) -> str:
    if fault_type == "missing_compile_input":
        return v1._commands_script([f"rm -f {shlex.quote(task['fault_file'])}", *task["build_commands"]])
    if fault_type == "invalid_build_state":
        return v1._commands_script(
            [
                f"printf '%s\\n' all > {shlex.quote(task['build_state_file'])}",
                *task["build_commands"],
            ]
        )
    if fault_type == "wrong_build_target":
        if task["selected_build_system"] == "cmake":
            return f"cmake --build build --target {pilot.OPAQUE_TARGET} --parallel 4"
        make_dir = Path(task["build_state_file"]).parent.as_posix()
        prefix = "make" if make_dir == "." else f"make -C {shlex.quote(make_dir)}"
        return f"{prefix} {pilot.OPAQUE_TARGET}"
    raise ExecutionError(f"未知 fault type: {fault_type}")


@contextlib.contextmanager
def _formal_pilot_context() -> Iterator[None]:
    original_identity = pilot.IDENTITY
    original_fault = pilot._fault_trigger_command
    pilot.IDENTITY = IDENTITY
    pilot._fault_trigger_command = _formal_fault_trigger
    try:
        yield
    finally:
        pilot.IDENTITY = original_identity
        pilot._fault_trigger_command = original_fault


def _qualify_outcomes(records: list[dict[str, Any]], pool: dict[str, Any]) -> dict[str, Any]:
    states_by_id: dict[str, dict[str, Any]] = {}
    outcomes: list[dict[str, Any]] = []
    closures: list[dict[str, Any]] = []
    hidden: dict[str, str] = {}
    for record in records:
        for state in record["states"]:
            states_by_id.setdefault(state["state_id"], state)
        outcomes.extend(record["outcomes"])
        closures.append(record["reference_closure"])
        hidden.update(record["hidden_fault_mapping"])
    states = sorted(states_by_id.values(), key=lambda row: row["state_id"])
    outcomes.sort(key=lambda row: (row["state_id"], row["action_family"], row["replicate"]))
    labels, replay = pilot._derive_labels(states, outcomes)
    split_by_family = {task["project_family"]: task["qualification_split"] for task in pool["tasks"]}
    for state in states:
        state["qualification_split"] = split_by_family[state["project_family"]]
    for label in labels:
        label["qualification_split"] = split_by_family[label["project_family"]]
    all_bounded = all(row["action_timed_out"] is False and row["action_exit_code"] is not None and row["replay_signature"]["continuation_exit_class"] != "timeout" and row["strict_timed_out"] is not True for row in outcomes)
    split_metrics: dict[str, Any] = {}
    for split in candidate.QUALIFICATION_SPLITS:
        split_states = [row for row in states if row["qualification_split"] == split]
        split_labels = [row for row in labels if row["qualification_split"] == split]
        split_metrics[split] = {
            "project_count": len({row["project_family"] for row in split_states}),
            "state_count": len(split_states),
            "states_by_build_system": dict(sorted(Counter(row["build_system"] for row in split_states).items())),
            "optimal_actions": dict(sorted(Counter(row["optimal_action"] for row in split_labels).items())),
        }
    forbidden = set(candidate.FAULT_TYPES)
    leakage = [state["state_id"] for state in states if any(token in json.dumps(state["model_input"], sort_keys=True).lower() for token in forbidden)]
    gates = {
        "expected_counts": len(states) == 36 and len(outcomes) == 288 and len(closures) == 24,
        "reference_closure": all(row["reference_passed"] and all(row["strict_checks"].values()) for row in closures),
        "replay_consistency": replay["replay_consistency"] >= 0.95,
        "split_balance": all(
            metrics["project_count"] == 6 and metrics["state_count"] == 18 and metrics["states_by_build_system"] == {"autotools": 6, "cmake": 6, "make": 6} and metrics["optimal_actions"] == {"build": 6, "configure": 6, "dependency": 6}
            for metrics in split_metrics.values()
        ),
        "all_candidates_bounded": all_bounded,
        "no_direct_label_leakage": not leakage,
    }
    return {
        "states": states,
        "outcomes": outcomes,
        "reference_closures": closures,
        "hidden_fault_mapping": dict(sorted(hidden.items())),
        "analysis": {
            "labels": labels,
            "replay": replay,
            "split_metrics": split_metrics,
            "leakage_violations": leakage,
            "gates": gates,
            "passed": all(gates.values()),
            "decision": "proceed_to_jev_provider_design" if all(gates.values()) else "stop_before_credential_read",
            "provider_calls": 0,
            "credential_reads": 0,
            "model_tokens": 0,
        },
    }


def collect_outcomes() -> dict[str, Any]:
    manifest = validate_execution_manifest()
    preflight()
    if EVIDENCE_ROOT.exists():
        raise ExecutionError("formal evidence root 已存在，禁止重跑或续跑")
    EVIDENCE_ROOT.mkdir(parents=True, mode=0o700)
    _write_once_json(
        EVIDENCE_ROOT / "identity.json",
        {
            "identity": IDENTITY,
            "status": "started",
            "created_at": _now(),
            "git_commit": _git("rev-parse", "HEAD"),
            "manifest_canonical_sha256": v1.canonical_sha256(manifest),
            "credential_reads": 0,
            "provider_calls": 0,
        },
    )
    pool = v1.load_json(SOURCE_POOL)
    records: list[dict[str, Any]] = []
    try:
        image = v1.current_image_id(manifest)
        with _formal_pilot_context():
            for task in pool["tasks"]:
                for replicate in range(1, 3):
                    with tempfile.TemporaryDirectory(prefix=f"forge-jev-{task['task_id']}-{replicate}-") as temporary:
                        root = Path(temporary)
                        states, outcomes, closure, mapping = pilot._run_project_replicate(
                            manifest=manifest,
                            image=image,
                            task=task,
                            replicate=replicate,
                            root=root,
                        )
                    record = {
                        "task_id": task["task_id"],
                        "project_family": task["project_family"],
                        "qualification_split": task["qualification_split"],
                        "replicate": replicate,
                        "states": states,
                        "outcomes": outcomes,
                        "reference_closure": closure,
                        "hidden_fault_mapping": mapping,
                    }
                    _write_once_json(
                        EVIDENCE_ROOT / "outcome-replicates" / f"{task['task_id']}-{replicate}.json",
                        record,
                    )
                    records.append(record)
                    v1.require_zero_managed_resources()
        report = _qualify_outcomes(records, pool)
        outcome_document = {
            "schema_version": "forge-jev-outcome-qualification-1.0.0",
            "identity": IDENTITY,
            "created_at": _now(),
            "git_commit": _git("rev-parse", "HEAD"),
            "manifest_canonical_sha256": v1.canonical_sha256(manifest),
            **report,
        }
        _write_once_json(EVIDENCE_ROOT / "outcomes.json", outcome_document)
        _write_once_json(
            EVIDENCE_ROOT / "outcome-terminal-completed.json",
            {
                "identity": IDENTITY,
                "status": "completed",
                "created_at": _now(),
                "passed": report["analysis"]["passed"],
                "decision": report["analysis"]["decision"],
                "credential_reads": 0,
                "provider_calls": 0,
            },
        )
        return outcome_document
    except Exception as exc:
        v1.require_zero_managed_resources()
        _write_once_json(
            EVIDENCE_ROOT / "outcome-terminal-failed.json",
            {
                "identity": IDENTITY,
                "status": "failed",
                "created_at": _now(),
                "error_type": type(exc).__name__,
                "error": str(exc)[-4000:],
                "credential_reads": 0,
                "provider_calls": 0,
            },
        )
        raise


def load_outcomes() -> dict[str, Any]:
    path = EVIDENCE_ROOT / "outcomes.json"
    if not path.is_file():
        raise ExecutionError("outcome qualification 尚未完成")
    value = v1.load_json(path)
    if value["identity"] != IDENTITY or value["analysis"]["passed"] is not True:
        raise ExecutionError("outcome qualification 未通过")
    if (EVIDENCE_ROOT / "outcome-terminal-failed.json").exists():
        raise ExecutionError("outcome identity 已失败，禁止 Provider")
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
    for path in _request_files():
        row = v1.load_json(path)
        completed_request_count += 1
        normalized = row["response"]
        input_tokens += normalized["usage"]["input_tokens"]
        output_tokens += normalized["usage"]["output_tokens"]
        cost += normalized["cost_usd"]
        request_id = normalized["request_id"]
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
        with TypeSafeClient(
            api_key=key,
            model=candidate.MODEL_ID,
            retry=RetryPolicy(max_retries=0, timeout=30.0),
            base_url=candidate.API_BASE_URL,
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
                normalized = candidate.normalize_response(response, latency_ms=latency_ms)
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


def build_report() -> dict[str, Any]:
    if JSON_REPORT.exists() or MARKDOWN_REPORT.exists():
        raise ExecutionError("正式报告已存在，禁止覆盖")
    manifest = validate_execution_manifest()
    outcome_path = EVIDENCE_ROOT / "outcomes.json"
    if not outcome_path.is_file():
        raise ExecutionError("outcome qualification 尚未完成")
    outcomes = v1.load_json(outcome_path)
    if outcomes["identity"] != IDENTITY:
        raise ExecutionError("outcome identity 漂移")
    if outcomes["analysis"]["passed"] is not True:
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "document_type": "forge_jev_offline_qualification_report",
            "identity": IDENTITY,
            "issue_url": ISSUE_URL,
            "created_at": _now(),
            "git_commit": _git("rev-parse", "HEAD"),
            "manifest_canonical_sha256": v1.canonical_sha256(manifest),
            "outcome_qualification": outcomes["analysis"],
            "terminal_stage": "outcome_qualification",
            "design": None,
            "calibration": None,
            "evaluation": None,
            "budget": _budget_usage(),
            "gates": {"outcome_qualification": False},
            "passed": False,
            "decision": "stop_jev_controller_and_keep_offline_result",
            "evidence_inventory": _evidence_inventory(),
            "interpretation": {
                "jev_offline_action_qualification_estimated": False,
                "controller_effect_estimated": False,
                "strict_success_noninferiority_estimated": False,
                "temporal_generalization_estimated": False,
                "natural_failure_population_estimated": False,
                "historical_evidence_modified": False,
            },
        }
        report["evidence_inventory_canonical_sha256"] = v1.canonical_sha256(report["evidence_inventory"])
        _write_once_json(JSON_REPORT, report)
        v1.write_once(MARKDOWN_REPORT, render_markdown(report))
        return report
    outcomes = load_outcomes()
    design_terminal_path = EVIDENCE_ROOT / "design-terminal.json"
    if design_terminal_path.is_file():
        design = v1.load_json(design_terminal_path)
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "document_type": "forge_jev_offline_qualification_report",
            "identity": IDENTITY,
            "issue_url": ISSUE_URL,
            "created_at": _now(),
            "git_commit": _git("rev-parse", "HEAD"),
            "manifest_canonical_sha256": v1.canonical_sha256(manifest),
            "outcome_qualification": outcomes["analysis"],
            "terminal_stage": "design",
            "design": design,
            "calibration": None,
            "evaluation": None,
            "budget": _budget_usage(),
            "gates": {"design_qualification": False},
            "passed": False,
            "decision": "stop_jev_controller_and_keep_offline_result",
            "evidence_inventory": _evidence_inventory(),
            "interpretation": {
                "jev_offline_action_qualification_estimated": False,
                "controller_effect_estimated": False,
                "strict_success_noninferiority_estimated": False,
                "temporal_generalization_estimated": False,
                "natural_failure_population_estimated": False,
                "historical_evidence_modified": False,
            },
        }
        report["evidence_inventory_canonical_sha256"] = v1.canonical_sha256(report["evidence_inventory"])
        _write_once_json(JSON_REPORT, report)
        v1.write_once(MARKDOWN_REPORT, render_markdown(report))
        return report
    calibration = v1.load_json(EVIDENCE_ROOT / "calibration.json")
    if calibration["passed"] is not True:
        freeze = v1.load_json(EVIDENCE_ROOT / "prompt-freeze.json")
        design = v1.load_json(_stage_directory("design", freeze["design_round"]) / "analysis.json")
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "document_type": "forge_jev_offline_qualification_report",
            "identity": IDENTITY,
            "issue_url": ISSUE_URL,
            "created_at": _now(),
            "git_commit": _git("rev-parse", "HEAD"),
            "manifest_canonical_sha256": v1.canonical_sha256(manifest),
            "outcome_qualification": outcomes["analysis"],
            "terminal_stage": "calibration",
            "design": design,
            "calibration": calibration,
            "evaluation": None,
            "budget": _budget_usage(),
            "gates": {"calibration_direct_coverage": False},
            "passed": False,
            "decision": "stop_jev_controller_and_keep_offline_result",
            "evidence_inventory": _evidence_inventory(),
            "interpretation": {
                "jev_offline_action_qualification_estimated": False,
                "controller_effect_estimated": False,
                "strict_success_noninferiority_estimated": False,
                "temporal_generalization_estimated": False,
                "natural_failure_population_estimated": False,
                "historical_evidence_modified": False,
            },
        }
        report["evidence_inventory_canonical_sha256"] = v1.canonical_sha256(report["evidence_inventory"])
        _write_once_json(JSON_REPORT, report)
        v1.write_once(MARKDOWN_REPORT, render_markdown(report))
        return report
    evaluation_responses = _responses("evaluation")
    evaluation = _analyse_predictions("evaluation", evaluation_responses)
    threshold = calibration["threshold"]["threshold"]
    direct_rows: list[dict[str, Any]] = []
    for row in evaluation["rows"]:
        raw = row["probabilities"][row["choice"]]
        calibrated = _calibrated_probability(calibration, raw)
        row["calibrated_safe_probability"] = calibrated
        row["direct_execute"] = bool(row["direct_choice"] and row["order_agreement"] and calibrated >= threshold)
        if row["direct_execute"]:
            direct_rows.append(row)
    wrong_direct = sum(not row["route_acceptable"] for row in direct_rows)
    correct_direct_systems = {row["build_system"] for row in direct_rows if row["top1_correct"] and row["route_acceptable"]}
    gates = {
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
    inventory = _evidence_inventory()
    freeze = v1.load_json(EVIDENCE_ROOT / "prompt-freeze.json")
    design_path = _stage_directory("design", freeze["design_round"]) / "analysis.json"
    risk_coverage = _risk_coverage_curve(evaluation["rows"], calibration)
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "document_type": "forge_jev_offline_qualification_report",
        "identity": IDENTITY,
        "issue_url": ISSUE_URL,
        "created_at": _now(),
        "git_commit": _git("rev-parse", "HEAD"),
        "manifest_canonical_sha256": v1.canonical_sha256(manifest),
        "outcome_qualification": outcomes["analysis"],
        "terminal_stage": "evaluation",
        "design": v1.load_json(design_path),
        "calibration": calibration,
        "evaluation": evaluation,
        "calibrated_gate": {
            "threshold": threshold,
            "direct_execution_count": len(direct_rows),
            "wrong_direct_action_count": wrong_direct,
            "correct_direct_build_systems": sorted(correct_direct_systems),
            "rejection_count": len(evaluation["rows"]) - len(direct_rows),
            "rejection_rate": 1 - len(direct_rows) / len(evaluation["rows"]),
            "risk_coverage_curve": risk_coverage,
            "rows": [row for row in evaluation["rows"] if row["direct_execute"]],
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
        "decision": "proceed_to_controller_replay_qualification" if passed else "stop_jev_controller_and_keep_offline_result",
        "evidence_inventory": inventory,
        "evidence_inventory_canonical_sha256": v1.canonical_sha256(inventory),
        "interpretation": {
            "jev_offline_action_qualification_estimated": True,
            "controller_effect_estimated": False,
            "strict_success_noninferiority_estimated": False,
            "temporal_generalization_estimated": False,
            "natural_failure_population_estimated": False,
            "historical_evidence_modified": False,
        },
    }
    _write_once_json(JSON_REPORT, report)
    v1.write_once(MARKDOWN_REPORT, render_markdown(report))
    return report


def render_markdown(report: dict[str, Any]) -> str:
    evaluation = report["evaluation"]
    if evaluation is None:
        if report["terminal_stage"] == "outcome_qualification":
            observed = "零 Provider outcome qualification 未通过，未读取 credential 或调用 Jev。"
        elif report["terminal_stage"] == "design":
            observed = f"Design round {report['design']['design_round']} 未达到 15/18 top-1 与 16/18 顺序一致门槛。"
        else:
            observed = f"Calibration 零观察错误直接执行覆盖为 {report['calibration']['threshold']['coverage']}/18，低于 6/18。"
        return f"""# Jev 离线资格实验 v1 结果

- identity：`{IDENTITY}`
- 决定：`{report["decision"]}`
- 停止阶段：`{report["terminal_stage"]}`
- Provider 请求：`{report["budget"]["model_requests"]}`
- Input tokens：`{report["budget"]["input_tokens"]}`
- Jev 模型费用：`${report["budget"]["model_cost_usd"]:.8f}`

## 结论

{observed} Jev 未通过预注册离线门槛，本方向停止在 controller 之前；保留 outcome benchmark 与负结果。

## 解释边界

该停止决定没有执行 evaluation，因此不能估计 evaluation holdout 表现、controller treatment effect、严格成功率非劣、端到端成本节省、跨时间泛化或自然失败总体表现。
"""
    gate = report["calibrated_gate"]
    tfidf = report["baselines"]["tfidf_logistic_regression"]
    metrics = report["supporting_metrics"]
    return f"""# Jev 离线资格实验 v1 结果

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
        "collect-outcomes",
        "outcome-audit",
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
    if args.command == "collect-outcomes":
        print(
            json.dumps(
                collect_outcomes()["analysis"],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "outcome-audit":
        print(
            json.dumps(
                load_outcomes()["analysis"],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
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
