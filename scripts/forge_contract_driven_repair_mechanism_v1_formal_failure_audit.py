#!/usr/bin/env python3
"""只读审计 mechanism v1 formal marker 封口失败并冻结脱敏报告。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_contract_driven_repair_mechanism_v1_formal_protocol as protocol  # noqa: E402
from deerflow.compile.evidence import ExperimentLedger  # noqa: E402

SCHEMA_VERSION = "forge-contract-repair-formal-failure-audit-1.0.0"
DOCUMENT_TYPE = "forge_contract_repair_formal_failure_audit"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/365"
PR_URL = "https://github.com/WWFXL/Forge-AutoCompiler/pull/364"
MANIFEST_CANONICAL_SHA256 = (
    "3a843799109e1163b34f4ed046f0155c7eca91a48ebaecb904e5ad3ed015829f"
)
MANIFEST_FILE_SHA256 = (
    "4fae67f177d692a0a0165326b9b3845fc79244b5d510abb88cd855eb159544a4"
)
RUNNER_FILE_SHA256 = "5bb1797d2a3a5a8c700ba8da5677b195d0c0db969498521df878f669c815e358"
RELEASE_REVISION = "e5acf5d79209fea8894fc31aad1cbb3ce815b205"
INVENTORY_SHA256 = "24019a372a3b49fe6dc1b141da45f09f764639c253fc1ed16521341f3c6d2fb5"
EXPECTED_FILE_COUNT = 9
EXPECTED_TOTAL_SIZE_BYTES = 66_466
EXPECTED_TERMINAL_LEDGER_HEAD = (
    "87835c97ad556b49e6bb9d5665a00ffe2cbb510d5f19cf0ef8dc249134830c63"
)
FAILURE_MESSAGE_SHA256 = (
    "f10abf03c41c79e8e386a76469c36eca73c9e4595a0058714363772002e23c26"
)
EXPECTED_INPUT_SHA256 = {
    "attempts/01-clone-4d90a79086b9d5007c7ccbf5/attempt.json": "0301d258c6c39ead59f9a97e19a23c83ed0dbc251403e56c41803645b5a3504c",
    "attempts/01-clone-4d90a79086b9d5007c7ccbf5/candidate.json": "fc5d17baa377c08ee9f5ec1de3e905ea7fc90e991e3ee9f9f0db6df83e7cf5ad",
    "attempts/01-clone-4d90a79086b9d5007c7ccbf5/experiment.jsonl": "b53015db1706e54b4771dab12912b2e987ba2fc63611feddcfac60c5f0a2b531",
    "attempts/01-clone-4d90a79086b9d5007c7ccbf5/result.json": "db258e1a6caa11bc26f23795bd15b63a1636a2b260295e1ed6b54be361fb9aaf",
    "attempts/01-clone-4d90a79086b9d5007c7ccbf5/runtime-events.jsonl": "34ba2be9533f9fa03240b00a74394b2d9fb376581d24eaee0e8da3755c475d38",
    "checkpoints/01-rnnoise-0.1.1-delivery-target/checkpoint.json": "4185bbaa50b256f17d1fe08cb9a182e4c67604d3d9f8a8e560ed923c2150d6f0",
    "checkpoints/01-rnnoise-0.1.1-delivery-target/experiment.jsonl": "ca1f5f72594e970a5fed4e37b5b47bdad29058c290a68e54656366d9e62af153",
    "markers/availability.json": "8527d64acc50a88ea0d5f8b64fc25971d68294fb142b043f1e889586ad088bee",
    "markers/batch.json": "11bfe119281988765b803123c0030eb74788915413c69e1125cd35c6a5d17b64",
}
ARM_PREFIX = "attempts/01-clone-4d90a79086b9d5007c7ccbf5"
CHECKPOINT_PREFIX = "checkpoints/01-rnnoise-0.1.1-delivery-target"
FORBIDDEN_REPORT_KEYS = frozenset(
    {
        "api_key",
        "capture",
        "command",
        "credential",
        "messages",
        "parent_command_history",
        "prompt",
        "response",
        "session_id",
        "stderr",
        "stdout",
    }
)

DEFAULT_EVIDENCE_DIR = (
    REPO_ROOT
    / ".compile-sessions"
    / "benchmark-evidence-contract-driven-repair-mechanism-v1-authorized"
)
DEFAULT_JSON_REPORT = (
    REPO_ROOT
    / "benchmarks"
    / "reports"
    / "cpp-contract-driven-repair-mechanism-v1-formal-failure-audit.json"
)
DEFAULT_MARKDOWN_REPORT = (
    REPO_ROOT
    / "benchmarks"
    / "reports"
    / "cpp-contract-driven-repair-mechanism-v1-formal-failure-audit.md"
)
DEFAULT_SCHEMA = (
    REPO_ROOT
    / "benchmarks"
    / "schemas"
    / "forge-contract-repair-formal-failure-audit.schema.json"
)


class FormalFailureAuditError(RuntimeError):
    """冻结 formal failure evidence 不满足审计不变量。"""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FormalFailureAuditError(f"无法读取 {label}") from exc
    if not isinstance(value, dict):
        raise FormalFailureAuditError(f"{label} 顶层必须为对象")
    return value


def _reference(path: Path, root: Path) -> dict[str, Any]:
    relative = path.relative_to(root).as_posix()
    return {
        "path": relative,
        "sha256": file_sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _inventory_sha256(references: list[dict[str, Any]]) -> str:
    payload = "".join(f"{item['sha256']}  ./{item['path']}\n" for item in references)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_source_inventory(evidence_dir: Path) -> list[dict[str, Any]]:
    if evidence_dir.is_symlink() or not evidence_dir.is_dir():
        raise FormalFailureAuditError("冻结 evidence 根不存在或不是普通目录")
    entries = sorted(evidence_dir.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise FormalFailureAuditError("冻结 evidence 不得包含符号链接")
    references = [_reference(path, evidence_dir) for path in entries if path.is_file()]
    observed = {item["path"]: item["sha256"] for item in references}
    if observed != EXPECTED_INPUT_SHA256:
        missing = sorted(set(EXPECTED_INPUT_SHA256) - set(observed))
        unexpected = sorted(set(observed) - set(EXPECTED_INPUT_SHA256))
        if missing or unexpected:
            raise FormalFailureAuditError(
                f"冻结 evidence 文件集合漂移: missing={missing}, unexpected={unexpected}"
            )
        raise FormalFailureAuditError("冻结 evidence 文件 SHA-256 漂移")
    if (
        len(references) != EXPECTED_FILE_COUNT
        or sum(item["size_bytes"] for item in references) != EXPECTED_TOTAL_SIZE_BYTES
    ):
        raise FormalFailureAuditError("冻结 evidence 文件数量或总大小漂移")
    if _inventory_sha256(references) != INVENTORY_SHA256:
        raise FormalFailureAuditError("冻结 evidence inventory SHA-256 漂移")
    return references


def verify_checkpoint_ledger(path: Path) -> dict[str, Any]:
    previous_hash = "0" * 64
    events: list[dict[str, Any]] = []
    for sequence, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FormalFailureAuditError("checkpoint ledger JSON 无效") from exc
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            raise FormalFailureAuditError("checkpoint ledger sequence 不连续")
        event_hash = event.get("event_hash")
        body = dict(event)
        body.pop("event_hash", None)
        calculated = hashlib.sha256(
            json.dumps(
                body,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        if event.get("previous_hash") != previous_hash or event_hash != calculated:
            raise FormalFailureAuditError("checkpoint ledger hash chain 断裂")
        previous_hash = event_hash
        events.append(event)
    if [event["event_type"] for event in events] != [
        "candidate.submit_started",
        "artifact.observed",
        "artifact.observed",
        "candidate.prefreeze_verification_completed",
        "candidate.submit_rejected",
    ]:
        raise FormalFailureAuditError("checkpoint ledger 事件序列漂移")
    rejection = events[-1]["payload"]
    if rejection.get("rejection_codes") != ["target_mapping_invalid"]:
        raise FormalFailureAuditError("checkpoint authoritative rejection 漂移")
    return {
        "event_count": len(events),
        "terminal_event": events[-1]["event_type"],
        "terminal_head_sha256": previous_hash,
    }


def summarize_token_ledger(result: dict[str, Any]) -> dict[str, int]:
    ledger = result.get("request_token_ledger")
    if not isinstance(ledger, list) or len(ledger) != 5:
        raise FormalFailureAuditError("Provider request ledger 数量漂移")
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for sequence, item in enumerate(ledger, 1):
        if (
            not isinstance(item, dict)
            or item.get("request_sequence") != sequence
            or item.get("actual_model") != "deepseek-flash"
            or item.get("model_identity_match") is not True
            or item.get("response_received") is not True
            or item.get("retry_eligible") is not False
            or item.get("error_class") is not None
        ):
            raise FormalFailureAuditError("Provider request identity 或顺序漂移")
        values = tuple(item.get(key) for key in totals)
        if any(type(value) is not int or value < 0 for value in values):
            raise FormalFailureAuditError("Provider token 值无效")
        if values[0] + values[1] != values[2]:
            raise FormalFailureAuditError("单请求 token 不闭合")
        for key in totals:
            totals[key] += item[key]
    expected = {
        "input_tokens": result.get("recorded_input_tokens"),
        "output_tokens": result.get("recorded_output_tokens"),
        "total_tokens": result.get("recorded_total_tokens"),
    }
    if totals != expected or totals != {
        "input_tokens": 44_561,
        "output_tokens": 8_423,
        "total_tokens": 52_984,
    }:
        raise FormalFailureAuditError("Provider token 汇总不闭合")
    return {"request_attempts": len(ledger), **totals}


def verify_arm_ledger(path: Path, result_path: Path) -> dict[str, Any]:
    try:
        events = ExperimentLedger.verify_path(path)
    except Exception as exc:
        raise FormalFailureAuditError("arm ledger hash chain 无效") from exc
    result_hash = file_sha256(result_path)
    completions = [
        event for event in events if event["event"] == "experiment.completed"
    ]
    if (
        len(completions) != 1
        or completions[0] is not events[-1]
        or completions[0]["payload"]
        != {"result_sha256": result_hash, "status": "complete"}
        or events[-1]["event_sha256"] != EXPECTED_TERMINAL_LEDGER_HEAD
    ):
        raise FormalFailureAuditError("arm ledger 终态与 result 未闭合")
    return {
        "event_count": len(events),
        "terminal_event": "experiment.completed",
        "terminal_head_sha256": events[-1]["event_sha256"],
        "result_sha256": result_hash,
    }


def _require_identity(value: dict[str, Any], label: str) -> None:
    if (
        value.get("manifest_sha256") != MANIFEST_CANONICAL_SHA256
        or value.get("release_revision") != RELEASE_REVISION
    ):
        raise FormalFailureAuditError(f"{label} identity 漂移")


def _validate_report_sanitization(report: dict[str, Any]) -> None:
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            forbidden = FORBIDDEN_REPORT_KEYS & set(value)
            if forbidden:
                raise FormalFailureAuditError(f"报告包含禁止字段: {sorted(forbidden)}")
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(report)
    serialized = json.dumps(report, ensure_ascii=False)
    if any(
        value in serialized for value in ("/home/", "/workspace/", "api.deepseek.com")
    ):
        raise FormalFailureAuditError("报告包含宿主、容器或 endpoint 细节")


def build_report(evidence_dir: Path = DEFAULT_EVIDENCE_DIR) -> dict[str, Any]:
    references = verify_source_inventory(evidence_dir)
    manifest = protocol.load_manifest()
    if canonical_sha256(manifest) != MANIFEST_CANONICAL_SHA256:
        raise FormalFailureAuditError("formal manifest canonical SHA-256 漂移")
    if file_sha256(protocol.DEFAULT_MANIFEST) != MANIFEST_FILE_SHA256:
        raise FormalFailureAuditError("formal manifest 文件 SHA-256 漂移")

    availability = _load_json(
        evidence_dir / "markers/availability.json", "availability marker"
    )
    batch = _load_json(evidence_dir / "markers/batch.json", "batch marker")
    checkpoint = _load_json(
        evidence_dir / f"{CHECKPOINT_PREFIX}/checkpoint.json", "checkpoint marker"
    )
    attempt = _load_json(evidence_dir / f"{ARM_PREFIX}/attempt.json", "attempt marker")
    result_path = evidence_dir / f"{ARM_PREFIX}/result.json"
    result = _load_json(result_path, "arm result")
    for value, label in (
        (batch, "batch marker"),
        (attempt, "attempt marker"),
        (result, "arm result"),
    ):
        _require_identity(value, label)

    if (
        availability.get("status") != "passed"
        or availability.get("recorded_total_tokens") != 58
    ):
        raise FormalFailureAuditError("availability marker 漂移")
    if (
        batch.get("status") != "running"
        or batch.get("completed_arm_count") != 0
        or batch.get("completed_checkpoint_count") != 0
        or batch.get("provider_request_attempt_count") != 0
        or batch.get("endpoint_censored_arm_count") != 0
    ):
        raise FormalFailureAuditError("batch marker 未保留封口失败状态")
    if (
        checkpoint.get("status") != "captured"
        or checkpoint.get("checkpoint_id") != "rnnoise-0.1.1:delivery_target"
        or checkpoint.get("authoritative_rejection", {})
        .get("response", {})
        .get("rejection_codes")
        != ["target_mapping_invalid"]
    ):
        raise FormalFailureAuditError("checkpoint marker 漂移")
    if (
        attempt.get("status") != "started"
        or attempt.get("sequence") != 1
        or attempt.get("opaque_clone_id") != "clone-4d90a79086b9d5007c7ccbf5"
        or attempt.get("error_class") is not None
    ):
        raise FormalFailureAuditError("attempt marker 未保留封口失败状态")

    required_true = (
        "candidate_accepted",
        "functional_oracle_passed",
        "provenance_passed",
        "external_evaluator_v3_passed",
        "clean_replay_passed",
        "cleanup_closed",
        "zero_managed_orphans",
        "strict_post_checkpoint_conversion",
    )
    if (
        result.get("status") != "complete"
        or result.get("condition") != "t2"
        or result.get("sequence") != 1
        or any(result.get(field) is not True for field in required_true)
        or result.get("error_class") is not None
        or [item.get("layer") for item in result.get("s0_s5", [])]
        != ["S0", "S1", "S2", "S3", "S4", "S5"]
        or any(item.get("status") != "passed" for item in result.get("s0_s5", []))
    ):
        raise FormalFailureAuditError("arm result 严格终点漂移")

    token_summary = summarize_token_ledger(result)
    arm_ledger = verify_arm_ledger(
        evidence_dir / f"{ARM_PREFIX}/experiment.jsonl", result_path
    )
    checkpoint_ledger = verify_checkpoint_ledger(
        evidence_dir / f"{CHECKPOINT_PREFIX}/experiment.jsonl"
    )
    runtime_event_count = len(
        (evidence_dir / f"{ARM_PREFIX}/runtime-events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    if runtime_event_count != 34:
        raise FormalFailureAuditError("runtime event 数量漂移")

    report = {
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "issue_url": ISSUE_URL,
        "identity": {
            "release_revision": RELEASE_REVISION,
            "implementation_pr_url": PR_URL,
            "manifest_path": protocol.DEFAULT_MANIFEST.relative_to(
                REPO_ROOT
            ).as_posix(),
            "manifest_canonical_sha256": MANIFEST_CANONICAL_SHA256,
            "manifest_file_sha256": MANIFEST_FILE_SHA256,
            "runner_file_sha256": RUNNER_FILE_SHA256,
            "source_evidence_root": ".compile-sessions/benchmark-evidence-contract-driven-repair-mechanism-v1-authorized",
        },
        "source_integrity": {
            "file_count": len(references),
            "total_size_bytes": sum(item["size_bytes"] for item in references),
            "inventory_sha256": _inventory_sha256(references),
            "files": references,
            "source_evidence_modified": False,
        },
        "observed_arm": {
            "sequence": 1,
            "checkpoint_id": "rnnoise-0.1.1:delivery_target",
            "condition": "t2",
            "status": "complete",
            "strict_post_checkpoint_conversion": True,
            "candidate_accepted": True,
            "functional_oracle_passed": True,
            "provenance_passed": True,
            "external_evaluator_v3_passed": True,
            "clean_replay_passed": True,
            "cleanup_closed": True,
            "s0_s5_passed": 6,
            "tokens": token_summary,
            "result_sha256": file_sha256(result_path),
            "ledger": arm_ledger,
            "runtime_event_count": runtime_event_count,
            "completed_at": result["completed_at"],
        },
        "checkpoint": {
            "status": "captured",
            "authoritative_rejection_code": "target_mapping_invalid",
            "provider_calls_before_capture": 0,
            "formal_attempts_before_capture": 0,
            "ledger": checkpoint_ledger,
        },
        "failure": {
            "classification": "formal_marker_terminalization_failed",
            "exception_class": "TypeError",
            "exception_message_sha256": FAILURE_MESSAGE_SHA256,
            "phase": "after_result_and_experiment_completion_before_attempt_marker_terminalization",
            "attempt_marker_status": "started",
            "batch_marker_status": "running",
            "batch_marker_completed_arm_count": 0,
            "batch_marker_provider_request_attempt_count": 0,
            "root_cause": "marker_helper_requires_updates_mapping_but_all_runtime_call_sites_pass_keyword_updates",
            "secondary_failure": "batch_exception_terminalization_called_the_same_incompatible_helper_contract",
        },
        "execution_boundary": {
            "identity_terminal_failed": True,
            "schedule_stopped_before_sequence": 2,
            "completed_arm_results": 1,
            "formal_provider_request_attempts": 5,
            "formal_total_tokens": 52_984,
            "endpoint_censored_arms": 0,
            "zero_managed_resources_observed_after_failure": True,
            "rerun_allowed": False,
            "replacement_allowed": False,
            "backfill_allowed": False,
            "marker_repair_allowed": False,
            "continuation_allowed": False,
        },
        "interpretation": {
            "analysis_kind": "formal_infrastructure_failure_audit",
            "supported_claims": [
                "the_first_t2_arm_reached_the_preregistered_strict_endpoint_before_marker_terminalization_failed",
                "the_runner_stopped_before_sequence_2_and_cleanup_left_zero_managed_resources",
                "the_failure_was_caused_by_the_marker_update_call_contract",
            ],
            "unsupported_claims": [
                "c0_t1_or_t1_t2_treatment_effect",
                "statistical_significance_or_project_level_estimate",
                "population_success_rate_or_model_ranking",
                "permission_to_reuse_rerun_replace_or_backfill_the_observed_arm",
            ],
            "treatment_effect_estimated": False,
            "p_value_computed": False,
            "model_ranking_performed": False,
        },
        "next_decision": "choose_between_a_new_full_identity_an_explicit_evidence_import_amendment_or_stopping_collection_after_repair_review",
    }
    _validate_report_sanitization(report)
    return report


def generate_schema(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://forge-autocompiler.local/schemas/forge-contract-repair-formal-failure-audit.schema.json",
        "title": "Forge Contract Repair Formal Failure Audit",
        "const": report,
    }


def render_markdown(report: dict[str, Any]) -> str:
    arm = report["observed_arm"]
    tokens = arm["tokens"]
    failure = report["failure"]
    return f"""# 契约驱动修复 mechanism v1 formal marker 封口失败审计

> 本报告从 9 个 create-once 文件做只读冻结；原始 evidence 未修改。首 arm 是未完成 batch 中的单个观测，不能解释为 treatment effect。

## 身份与完整性

- 执行 release：`{report["identity"]["release_revision"]}`。
- Manifest canonical SHA-256：`{report["identity"]["manifest_canonical_sha256"]}`。
- Evidence：{report["source_integrity"]["file_count"]} files / {report["source_integrity"]["total_size_bytes"]:,} bytes；inventory SHA-256 `{report["source_integrity"]["inventory_sha256"]}`。
- Arm ledger：{arm["ledger"]["event_count"]} events，末尾 `experiment.completed`，head `{arm["ledger"]["terminal_head_sha256"]}`。
- 失败后人工只读资源审计：0 managed containers / 0 capture images。

## 已观察执行

| Sequence | Checkpoint | Arm | Requests | Input | Output | Total | Strict endpoint |
|---:|---|---|---:|---:|---:|---:|---|
| {arm["sequence"]} | `{arm["checkpoint_id"]}` | {arm["condition"].upper()} | {tokens["request_attempts"]} | {tokens["input_tokens"]:,} | {tokens["output_tokens"]:,} | {tokens["total_tokens"]:,} | 是 |

该 arm 的 candidate、functional oracle、provenance、external evaluator v3、clean replay、S0-S5 与 cleanup 均通过，result 与 ledger 已在 marker 缺陷触发前落盘并互相绑定。

## 失败与终态

Runner 在 `{failure["phase"]}` 调用 marker helper。Helper 接受单个 `updates` mapping，运行路径却传入 `status=...` 等关键字参数，因此抛出 `{failure["exception_class"]}`；batch 异常封口再次调用同一不兼容接口。

- Attempt marker 保持 `started`；
- Batch marker 保持 `running`，completed arm 与 Provider attempt 计数均为 0；
- schedule 在 sequence 2 前停止；
- 当前 identity 视为失败，不允许续跑、重跑、replacement、backfill 或手工修补 marker。

## 解释边界与下一决策

本审计支持首个 T2 arm 在 marker 封口失败前到达预注册严格终点，也支持失败根因位于 runner marker API。它不提供 C0 vs T1、T1 vs T2 或 C0 vs T2 比较，不计算 p 值、项目级估计、总体成功率或模型排名。

修复通过独立 PR 审阅后，需要在“全新 36-arm identity”“显式导入该 arm 的 amendment”与“停止 collection”之间作科研决策；任何选项都不得修改本 evidence。
"""


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def generate() -> dict[str, Any]:
    report = build_report()
    schema = generate_schema(report)
    _write_json(DEFAULT_JSON_REPORT, report)
    _write_json(DEFAULT_SCHEMA, schema)
    DEFAULT_MARKDOWN_REPORT.write_text(
        render_markdown(report), encoding="utf-8", newline="\n"
    )
    return report


def validate() -> dict[str, Any]:
    expected = build_report()
    report = _load_json(DEFAULT_JSON_REPORT, "committed audit report")
    schema = _load_json(DEFAULT_SCHEMA, "committed audit schema")
    if report != expected:
        raise FormalFailureAuditError("committed audit report 与冻结 evidence 不一致")
    if schema != generate_schema(report):
        raise FormalFailureAuditError("committed audit schema 不是确定性 const Schema")
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(report)
    if DEFAULT_MARKDOWN_REPORT.read_text(encoding="utf-8") != render_markdown(report):
        raise FormalFailureAuditError("committed Markdown report 漂移")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate", "audit"))
    args = parser.parse_args(argv)
    report = generate() if args.command == "generate" else validate()
    print(
        json.dumps(
            {
                "status": "passed",
                "classification": report["failure"]["classification"],
                "file_count": report["source_integrity"]["file_count"],
                "inventory_sha256": report["source_integrity"]["inventory_sha256"],
                "completed_arm_results": report["execution_boundary"][
                    "completed_arm_results"
                ],
                "formal_provider_request_attempts": report["execution_boundary"][
                    "formal_provider_request_attempts"
                ],
                "formal_total_tokens": report["execution_boundary"][
                    "formal_total_tokens"
                ],
                "treatment_effect_estimated": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
