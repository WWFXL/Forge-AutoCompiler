#!/usr/bin/env python3
"""只读审计 Stage C v8 workspace remediation canary 并冻结脱敏结果。"""

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

import forge_stage_c_v8_workspace_remediation_authorized_protocol as protocol
from deerflow.compile.evidence import ExperimentLedger

SCHEMA_VERSION = "forge-stage-c-v8-workspace-remediation-result-audit-1.0.0"
DOCUMENT_TYPE = "forge_stage_c_v8_workspace_remediation_result_audit"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/351"
MANIFEST_SHA256 = "df3a8c7ac1e13567b99ec5b7c77d341b6df20f35236cf767e76c06af46835a61"
MANIFEST_FILE_SHA256 = (
    "eb7cb461c17720f4ed6526a76d01e5112d59db19c857afbf1d08d81e1b2200d5"
)
PARENT_MANIFEST_SHA256 = (
    "4ed33a827d2c801ed1b0f56c717ee332f0a65141ed8d07d05326ff373dd07f6d"
)
RELEASE_REVISION = "6682d86cb30cc4e8d7b240bca8922606077a4808"
INVENTORY_SHA256 = "afe607e075509eee1999a65f4c485b0995959a1f026bf22f3f6ff7673d6b14a7"
EXPECTED_FILE_COUNT = 16
EXPECTED_TOTAL_SIZE_BYTES = 631_570
EXPECTED_INPUT_SHA256 = {
    "attempts/01-theora/attempt.json": "38fa19cdd8ace9168c801b845449fffbaab75e2ba916c770849b50842fd972bd",
    "attempts/01-theora/experiment.jsonl": "55e035f09e0ac3ed5c81005eceb44384c515d3241ddf9c38d876b16a8cf34f72",
    "attempts/01-theora/result.json": "2febe4afbb42c434042a9a2f8ecd7defd6eac4d398e0ce7cd89c3b5b2cdc550e",
    "attempts/02-json-c/attempt.json": "c5851b6e9b2338c25ba4b165ff72d9b19d7e00332c74256a703399958de2dc4b",
    "attempts/02-json-c/experiment.jsonl": "082789a7aece2200563836ae233a2e76cd46ffd17b9696d25eb55f5ed6f217ff",
    "attempts/02-json-c/result.json": "4f747006363bae0d0a46c8badc599380548c45844892316c9347c2e54ba9ff4a",
    "attempts/03-libjpeg-turbo/attempt.json": "7d82bcef01a583e6ff200ba1066c2d3495fe73db51ea84d09796291b3d28c559",
    "attempts/03-libjpeg-turbo/experiment.jsonl": "026bffcebccc98dfd8a1abbfe447b1e15813afa5043e6a669574d5803f097ef8",
    "attempts/03-libjpeg-turbo/result.json": "6a07340df527020e4af71abe64188463ab937793ffd12ee5a2a3a95e07ed35d2",
    "attempts/04-oatpp/attempt.json": "6d809d061de03b3d9c2791d17585f4ff049e5b653e0b8f56d832ff0f95d05049",
    "attempts/04-oatpp/experiment.jsonl": "3adc60b98d7e935de45136def9d8893c68cdcff381b9bd907daf99b4a52b5dee",
    "attempts/04-oatpp/result.json": "10aec2ac7ee37080c562a4aebce234e12aa2b037797d2ba9ed026d0f8b5595a5",
    "markers/batch.json": "363642d7b2cf57b740cb6d1e6650d40f6a2737029e612d46812d07a4a87d447f",
    "markers/reachability.json": "2d827b8cc80ffb4f34ca0b7f1a54324112f2c5471c610070b60b1b06fcb6dafd",
    "reports/canary.json": "d6e6f440bacaacb43ca31b1d6899180b272038a7cea151d641a1e00771efca70",
    "reports/reachability.json": "c418a6de746c021192bc521116a2f85a5e26b7ad45f1ead6e9e949a41aa8d078",
}
EXPECTED_REPAIRS = {
    "theora": (1, [], 0, False),
    "json-c": (1, [], 0, False),
    "libjpeg-turbo": (2, ["target_mapping_invalid"], 1, True),
    "oatpp": (1, [], 0, False),
}
LAYER_NAMES = ("S0", "S1", "S2", "S3", "S4", "S5")
FORBIDDEN_REPORT_KEYS = frozenset(
    {
        "api_key",
        "content",
        "credential",
        "error_message",
        "messages",
        "prompt",
        "response",
        "response_text",
        "session_id",
        "stderr",
        "stdout",
    }
)

DEFAULT_EVIDENCE_DIR = (
    REPO_ROOT
    / ".compile-sessions"
    / "benchmark-evidence-stage-c-v8-workspace-remediation-canary-authorized-v1"
)
DEFAULT_JSON_REPORT = (
    REPO_ROOT
    / "benchmarks"
    / "reports"
    / "cpp-stage-c-v8-workspace-remediation-result-audit.json"
)
DEFAULT_MARKDOWN_REPORT = (
    REPO_ROOT
    / "benchmarks"
    / "reports"
    / "cpp-stage-c-v8-workspace-remediation-result-audit.md"
)
DEFAULT_SCHEMA = (
    REPO_ROOT
    / "benchmarks"
    / "schemas"
    / "forge-stage-c-v8-workspace-remediation-result-audit.schema.json"
)


class StageCV8ResultAuditError(RuntimeError):
    """Stage C v8 冻结 evidence 或派生报告不满足审计不变量。"""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageCV8ResultAuditError(f"无法读取 {label}") from exc
    if not isinstance(value, dict):
        raise StageCV8ResultAuditError(f"{label} 根节点必须是对象")
    return value


def _reference(path: Path, root: Path) -> dict[str, Any]:
    try:
        relative_path = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise StageCV8ResultAuditError(f"evidence 路径越出冻结根: {path}") from exc
    return {
        "path": relative_path,
        "sha256": file_sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _inventory_sha256(references: list[dict[str, Any]]) -> str:
    payload = "".join(f"{item['sha256']}  ./{item['path']}\n" for item in references)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_source_inventory(evidence_dir: Path) -> list[dict[str, Any]]:
    if evidence_dir.is_symlink() or not evidence_dir.is_dir():
        raise StageCV8ResultAuditError("冻结 evidence 根必须是非符号链接目录")
    entries = sorted(evidence_dir.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise StageCV8ResultAuditError("冻结 evidence 不得包含符号链接")
    files = [path for path in entries if path.is_file()]
    references = [_reference(path, evidence_dir) for path in files]
    actual_sha256 = {item["path"]: item["sha256"] for item in references}
    if actual_sha256 != EXPECTED_INPUT_SHA256:
        missing = sorted(set(EXPECTED_INPUT_SHA256) - set(actual_sha256))
        unexpected = sorted(set(actual_sha256) - set(EXPECTED_INPUT_SHA256))
        if missing or unexpected:
            raise StageCV8ResultAuditError(
                f"冻结 evidence 文件集合漂移: missing={missing}, unexpected={unexpected}"
            )
        raise StageCV8ResultAuditError("冻结 evidence 文件 SHA-256 漂移")
    if (
        len(references) != EXPECTED_FILE_COUNT
        or sum(item["size_bytes"] for item in references) != EXPECTED_TOTAL_SIZE_BYTES
    ):
        raise StageCV8ResultAuditError("冻结 evidence 文件数量或总大小漂移")
    if _inventory_sha256(references) != INVENTORY_SHA256:
        raise StageCV8ResultAuditError("冻结 evidence inventory SHA-256 漂移")
    return references


def _require_identity(
    value: dict[str, Any], *, label: str, task: dict[str, Any] | None = None
) -> None:
    if (
        value.get("manifest_sha256") != MANIFEST_SHA256
        or value.get("release_revision") != RELEASE_REVISION
    ):
        raise StageCV8ResultAuditError(f"{label} identity 漂移")
    if task is not None and (
        value.get("sequence") != task["sequence"]
        or value.get("task_id") != task["task_id"]
        or value.get("attempt_id") != task["attempt_id"]
    ):
        raise StageCV8ResultAuditError(f"{label} attempt identity 漂移")


def summarize_token_ledger(
    ledger: Any, *, expected_requests: int, expected_total: int, label: str
) -> dict[str, int]:
    if not isinstance(ledger, list) or len(ledger) != expected_requests:
        raise StageCV8ResultAuditError(f"{label} request 数量不闭合")
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    for sequence, item in enumerate(ledger, start=1):
        if not isinstance(item, dict) or set(item) != {
            "input_tokens",
            "output_tokens",
            "request_sequence",
            "total_tokens",
        }:
            raise StageCV8ResultAuditError(f"{label} token ledger 字段无效")
        values = (item["input_tokens"], item["output_tokens"], item["total_tokens"])
        if item["request_sequence"] != sequence or any(
            type(value) is not int or value < 0 for value in values
        ):
            raise StageCV8ResultAuditError(f"{label} token ledger 顺序或数值无效")
        if item["input_tokens"] + item["output_tokens"] != item["total_tokens"]:
            raise StageCV8ResultAuditError(f"{label} 单请求 token 不闭合")
        input_tokens += item["input_tokens"]
        output_tokens += item["output_tokens"]
        total_tokens += item["total_tokens"]
    if total_tokens != expected_total:
        raise StageCV8ResultAuditError(f"{label} token 总量不闭合")
    return {
        "requests": expected_requests,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def audit_ledger(ledger_path: Path, result_path: Path) -> dict[str, Any]:
    try:
        events = ExperimentLedger.verify_path(ledger_path)
    except Exception as exc:
        raise StageCV8ResultAuditError(f"ledger 验证失败: {ledger_path.name}") from exc
    completions = [
        event for event in events if event["event"] == "experiment.completed"
    ]
    result_sha256 = file_sha256(result_path)
    if (
        len(completions) != 1
        or not events
        or events[-1] is not completions[0]
        or completions[0]["payload"]
        != {"result_sha256": result_sha256, "status": "passed"}
    ):
        raise StageCV8ResultAuditError(
            "ledger 缺少唯一、末尾且绑定 result 的 completed 终态"
        )
    return {
        "path": ledger_path.name,
        "sha256": file_sha256(ledger_path),
        "event_count": len(events),
        "terminal_event": "experiment.completed",
        "terminal_event_sha256": events[-1]["event_sha256"],
        "completion_result_sha256": result_sha256,
        "immutable_after_completion": True,
    }


def _summarize_layers(result: dict[str, Any]) -> list[dict[str, Any]]:
    layers = result.get("s0_s5")
    if not isinstance(layers, list) or [
        item.get("layer") for item in layers if isinstance(item, dict)
    ] != list(LAYER_NAMES):
        raise StageCV8ResultAuditError(f"{result.get('task_id')} S0-S5 顺序或集合漂移")
    summarized = []
    for item in layers:
        reason_codes = item.get("reason_codes")
        if (
            item.get("status") != "passed"
            or not isinstance(reason_codes, list)
            or not all(isinstance(code, str) for code in reason_codes)
        ):
            raise StageCV8ResultAuditError(
                f"{result.get('task_id')} {item.get('layer')} 未通过"
            )
        summarized.append(
            {"layer": item["layer"], "status": "passed", "reason_codes": reason_codes}
        )
    return summarized


def _summarize_task(
    manifest: dict[str, Any],
    evidence_dir: Path,
    scheduled: dict[str, Any],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    values = {"sequence": scheduled["sequence"], "task_id": scheduled["task_id"]}
    execution = manifest["execution"]
    marker_path = evidence_dir / execution["attempt_marker_template"].format(**values)
    result_path = evidence_dir / execution["attempt_result_template"].format(**values)
    ledger_path = evidence_dir / execution["attempt_ledger_template"].format(**values)
    marker = _load_json(marker_path, f"{scheduled['task_id']} marker")
    result = _load_json(result_path, f"{scheduled['task_id']} result")
    _require_identity(marker, label=f"{scheduled['task_id']} marker", task=scheduled)
    _require_identity(result, label=f"{scheduled['task_id']} result", task=scheduled)
    if marker.get("status") != "completed" or marker.get("error_class") is not None:
        raise StageCV8ResultAuditError(f"{scheduled['task_id']} marker 未完成")
    if result != outcome:
        raise StageCV8ResultAuditError(
            f"{scheduled['task_id']} result 与 canary report 不一致"
        )
    if (
        file_sha256(result_path)
        != EXPECTED_INPUT_SHA256[result_path.relative_to(evidence_dir).as_posix()]
    ):
        raise StageCV8ResultAuditError(f"{scheduled['task_id']} result SHA-256 漂移")
    required_true = (
        "canary_passed",
        "candidate_generated",
        "candidate_submitted",
        "strict_reproducible_build_success",
        "bitwise_reproducible",
        "cleanup_succeeded",
        "zero_managed_resources",
    )
    if (
        any(result.get(field) is not True for field in required_true)
        or result.get("method") != "forge-agent-workflow-node-v3"
        or result.get("node_status") != "submitted"
        or result.get("session_status") != "completed"
        or result.get("error_class") is not None
        or result.get("error_message_sha256") is not None
    ):
        raise StageCV8ResultAuditError(f"{scheduled['task_id']} 成功或清理终态漂移")
    expected_repair = EXPECTED_REPAIRS[scheduled["task_id"]]
    observed_repair = (
        result.get("submit_attempts"),
        result.get("rejection_codes"),
        result.get("rejection_evidence_count"),
        result.get("same_attempt_repair_observed"),
    )
    if observed_repair != expected_repair:
        raise StageCV8ResultAuditError(f"{scheduled['task_id']} submit repair 轨迹漂移")
    token_summary = summarize_token_ledger(
        result.get("request_token_ledger"),
        expected_requests=result.get("model_requests"),
        expected_total=result.get("recorded_tokens"),
        label=scheduled["task_id"],
    )
    ledger_summary = audit_ledger(ledger_path, result_path)
    ledger_summary["path"] = ledger_path.relative_to(evidence_dir).as_posix()
    return {
        "sequence": scheduled["sequence"],
        "task_id": scheduled["task_id"],
        "attempt_id": scheduled["attempt_id"],
        "method": result["method"],
        "candidate_generated": True,
        "candidate_submitted": True,
        "agent_steps": result["agent_steps"],
        "tool_calls": result["tool_calls"],
        "commands": result["commands"],
        "tokens": token_summary,
        "submit": {
            "attempts": result["submit_attempts"],
            "rejection_codes": result["rejection_codes"],
            "rejection_evidence_count": result["rejection_evidence_count"],
            "same_attempt_repair_observed": result["same_attempt_repair_observed"],
        },
        "layers": _summarize_layers(result),
        "strict_reproducible_build_success": True,
        "bitwise_reproducible": True,
        "cleanup_succeeded": True,
        "zero_managed_resources": True,
        "marker": _reference(marker_path, evidence_dir),
        "result": _reference(result_path, evidence_dir),
        "ledger": ledger_summary,
    }


def _validate_report_sanitization(value: Any, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_REPORT_KEYS:
                raise StageCV8ResultAuditError(
                    f"派生报告包含禁止字段: {'.'.join((*path, key))}"
                )
            _validate_report_sanitization(item, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_report_sanitization(item, (*path, str(index)))
    elif isinstance(value, str) and (
        value.startswith(("/home/", "/workspace/")) or "-----BEGIN" in value
    ):
        raise StageCV8ResultAuditError(
            f"派生报告包含敏感绝对路径或密钥材料: {'.'.join(path)}"
        )


def build_report(
    *,
    evidence_dir: Path = DEFAULT_EVIDENCE_DIR,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    manifest_path = repo_root / protocol.MANIFEST_RELATIVE_PATH
    manifest = protocol.load_manifest(manifest_path, repo_root)
    protocol.verify_frozen_components(manifest, repo_root)
    if (
        protocol.canonical_sha256(manifest) != MANIFEST_SHA256
        or file_sha256(manifest_path) != MANIFEST_FILE_SHA256
    ):
        raise StageCV8ResultAuditError("authorized manifest identity 漂移")
    references = verify_source_inventory(evidence_dir)

    batch_marker_path = evidence_dir / manifest["execution"]["batch_marker"]
    reachability_marker_path = (
        evidence_dir / manifest["execution"]["reachability"]["marker"]
    )
    canary_report_path = evidence_dir / manifest["execution"]["batch_report"]
    reachability_report_path = (
        evidence_dir / manifest["execution"]["reachability"]["report"]
    )
    batch_marker = _load_json(batch_marker_path, "batch marker")
    reachability_marker = _load_json(reachability_marker_path, "reachability marker")
    canary = _load_json(canary_report_path, "canary report")
    reachability = _load_json(reachability_report_path, "reachability report")
    for label, value in (
        ("batch marker", batch_marker),
        ("reachability marker", reachability_marker),
        ("canary report", canary),
        ("reachability report", reachability),
    ):
        _require_identity(value, label=label)
    if (
        batch_marker.get("status") != "passed"
        or batch_marker.get("error_class") is not None
        or reachability_marker.get("status") != "passed"
        or reachability_marker.get("error_class") is not None
        or reachability.get("passed") is not True
        or reachability.get("request_count") != 1
        or reachability.get("actual_model") != manifest["provider"]["actual_model"]
    ):
        raise StageCV8ResultAuditError("reachability 或 batch marker 未形成通过终态")
    reachability_tokens = summarize_token_ledger(
        reachability.get("token_ledger"),
        expected_requests=1,
        expected_total=reachability.get("recorded_tokens"),
        label="reachability",
    )

    scheduled = manifest["schedule"]["attempts"]
    outcomes = canary.get("outcomes")
    if not isinstance(outcomes, list) or len(outcomes) != len(scheduled):
        raise StageCV8ResultAuditError("canary report task 数量漂移")
    tasks = [
        _summarize_task(manifest, evidence_dir, attempt, outcomes[index])
        for index, attempt in enumerate(scheduled)
    ]
    task_order = [item["task_id"] for item in scheduled]
    task_tokens = {
        "requests": sum(item["tokens"]["requests"] for item in tasks),
        "input_tokens": sum(item["tokens"]["input_tokens"] for item in tasks),
        "output_tokens": sum(item["tokens"]["output_tokens"] for item in tasks),
        "total_tokens": sum(item["tokens"]["total_tokens"] for item in tasks),
    }
    total_tokens = {
        key: reachability_tokens[key] + task_tokens[key] for key in task_tokens
    }
    if (
        canary.get("status") != "completed"
        or canary.get("parent_manifest_sha256") != PARENT_MANIFEST_SHA256
        or canary.get("scheduled_task_order") != task_order
        or canary.get("observed_task_order") != task_order
        or canary.get("observed_attempt_count") != 4
        or canary.get("strict_success_count") != 4
        or canary.get("s0_s5_passed") != {name: 4 for name in LAYER_NAMES}
        or canary.get("attempt_recorded_tokens") != task_tokens["total_tokens"]
        or canary.get("reachability_recorded_tokens")
        != reachability_tokens["total_tokens"]
        or canary.get("total_recorded_tokens") != total_tokens["total_tokens"]
        or canary.get("cleanup_succeeded") is not True
        or canary.get("zero_managed_resources") is not True
        or canary.get("token_ceiling") is not None
        or canary.get("token_total_is_termination_condition") is not False
        or canary.get("descriptive_canary_only") is not True
        or canary.get("treatment_effect_estimated") is not False
        or canary.get("p_value_computed") is not False
        or canary.get("model_ranking_performed") is not False
        or canary.get("historical_outcomes_pooled") is not False
    ):
        raise StageCV8ResultAuditError("canary report 汇总或科学边界漂移")

    report = {
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "issue_url": ISSUE_URL,
        "identity": {
            "manifest_path": protocol.MANIFEST_RELATIVE_PATH,
            "manifest_file_sha256": MANIFEST_FILE_SHA256,
            "manifest_canonical_sha256": MANIFEST_SHA256,
            "parent_manifest_canonical_sha256": PARENT_MANIFEST_SHA256,
            "release_revision": RELEASE_REVISION,
            "runtime": "agent-workflow-runtime-v3",
            "external_evaluator": "external-evaluator-v4",
            "source_evidence_root": manifest["execution"][
                "evidence_directory_relative"
            ],
        },
        "source_integrity": {
            "file_count": len(references),
            "total_size_bytes": sum(item["size_bytes"] for item in references),
            "inventory_algorithm": "sha256(sha256sum_lines_sorted_by_dot_slash_relative_path)",
            "inventory_sha256": _inventory_sha256(references),
            "files": references,
            "historical_evidence_mutated": False,
        },
        "reachability": {
            "marker_status": "passed",
            "passed": True,
            "actual_model": reachability["actual_model"],
            "tokens": reachability_tokens,
        },
        "batch": {
            "marker_status": "passed",
            "report_status": "completed",
            "task_order": task_order,
            "attempt_count": len(tasks),
            "strict_success_count": 4,
            "bitwise_reproducible_count": 4,
            "cleanup_succeeded_count": 4,
            "s0_s5_passed": {name: 4 for name in LAYER_NAMES},
            "task_tokens": task_tokens,
            "total_tokens_with_reachability": total_tokens,
            "zero_managed_resources": True,
        },
        "tasks": tasks,
        "interpretation": {
            "analysis_kind": "descriptive_b_arm_engineering_canary_result_freeze",
            "supported_claims": [
                "workspace_remediation_closed_end_to_end_for_four_fixed_canary_tasks",
                "prefreeze_rejection_and_same_attempt_repair_observed_for_libjpeg_turbo",
                "all_four_candidates_passed_external_evaluator_v4_s0_s5_bitwise_replay_and_cleanup",
            ],
            "unsupported_claims": [
                "stage_c_v5_result_replacement",
                "treatment_effect_or_statistical_significance",
                "population_success_rate",
                "provider_or_model_ranking",
                "generalization_beyond_observed_tasks_environment_or_identity",
            ],
            "v5_outcomes_replaced": False,
            "v6_outcomes_replaced": False,
            "v7_terminal_state_rewritten": False,
            "treatment_effect_estimated": False,
            "p_value_computed": False,
            "model_ranking_performed": False,
        },
        "execution_boundary": {
            "provider_calls": 0,
            "credential_read": False,
            "docker_executed": False,
            "model_tokens": 0,
            "formal_attempts": 0,
            "experiment_evidence_written": False,
            "source_evidence_modified": False,
            "rerun_allowed": False,
            "retry_replacement_backfill_allowed": False,
            "next_action": "review_result_freeze_then_decide_confirmatory_sample_independent_replication_or_stop",
        },
        "source_completed_at": canary["completed_at"],
    }
    _validate_report_sanitization(report)
    return report


def generate_schema(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-stage-c-v8-workspace-remediation-result-audit.schema.json",
        "title": "Forge Stage C v8 workspace remediation result audit",
        "const": report,
    }


def render_markdown(report: dict[str, Any]) -> str:
    batch = report["batch"]
    rows = []
    for task in report["tasks"]:
        rejection = (
            ", ".join(f"`{code}`" for code in task["submit"]["rejection_codes"]) or "-"
        )
        rows.append(
            f"| `{task['task_id']}` | {task['tokens']['requests']} | {task['tokens']['total_tokens']:,} | {task['submit']['attempts']} | {rejection} | 是 | 是 | 是 |"
        )
    return "\n".join(
        [
            "# Stage C v8 workspace remediation 结果冻结与只读审计",
            "",
            "> 本报告由确定性只读审计器从冻结 evidence 生成；原始 evidence 未修改。",
            "",
            "## 身份与完整性",
            "",
            f"- Release：`{report['identity']['release_revision']}`。",
            f"- Authorized manifest canonical SHA-256：`{report['identity']['manifest_canonical_sha256']}`。",
            f"- Evidence：{report['source_integrity']['file_count']} files / {report['source_integrity']['total_size_bytes']:,} bytes。",
            f"- Inventory SHA-256：`{report['source_integrity']['inventory_sha256']}`。",
            "- 四条 ledger 均通过 `ExperimentLedger.verify_path()`，并由唯一末尾 `experiment.completed` 封口；completion 中的 result SHA-256 与实际文件一致。",
            "",
            "## 结果",
            "",
            f"唯一 reachability 通过；四任务按 `{' -> '.join(batch['task_order'])}` 执行，strict success、S0-S5、bitwise reproducible 与 cleanup 均为 4/4。",
            (
                f"完整账本为 {batch['total_tokens_with_reachability']['requests']} requests / {batch['total_tokens_with_reachability']['input_tokens']:,} input / "
                f"{batch['total_tokens_with_reachability']['output_tokens']:,} output / {batch['total_tokens_with_reachability']['total_tokens']:,} total tokens。"
            ),
            "",
            "| Task | Requests | Tokens | Submit | Rejection | Strict | Bitwise | Cleanup |",
            "|---|---:|---:|---:|---|---:|---:|---:|",
            *rows,
            "",
            "`libjpeg-turbo` 首次提交被 pre-freeze verifier 以 `target_mapping_invalid` 拒绝，并在同一 physical attempt 内修复后第二次提交成功；其余任务均一次提交成功。",
            "",
            "## 解释边界",
            "",
            "本结果支持：v8 workspace remediation 在这四个固定 canary task 上完成端到端工程闭合；四个候选均通过 external evaluator v4、bitwise replay 与 cleanup；`libjpeg-turbo` 存在一次可观察的同 attempt 修复轨迹。",
            "",
            "本结果不替换 Stage C v5 预注册结果，不估计 treatment effect、p 值或总体成功率，不进行 Provider/模型排名，也不外推到未观测项目、环境或实验 identity。一次修复轨迹不能单独证明 verifier 的总体因果效果。",
            "",
            "## 决策边界",
            "",
            "该 create-once identity 已消费完毕，不允许重跑、retry、replacement、backfill 或续跑。审阅本冻结报告后，再决定扩大确认性样本、设计独立 replication，或停止当前机制路线；任何新实验都需要新的 identity、预算、停止规则和明确授权。",
            "",
        ]
    )


def _write_text(path: Path, content: str, *, evidence_dir: Path) -> None:
    if path.resolve(strict=False).is_relative_to(evidence_dir.resolve(strict=True)):
        raise StageCV8ResultAuditError("派生报告不得写入冻结 evidence 根")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def compact_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "audited",
        "manifest_sha256": report["identity"]["manifest_canonical_sha256"],
        "inventory_sha256": report["source_integrity"]["inventory_sha256"],
        "task_count": report["batch"]["attempt_count"],
        "strict_success_count": report["batch"]["strict_success_count"],
        "total_recorded_tokens": report["batch"]["total_tokens_with_reachability"][
            "total_tokens"
        ],
        "source_evidence_modified": report["execution_boundary"][
            "source_evidence_modified"
        ],
        "rerun_allowed": report["execution_boundary"]["rerun_allowed"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate"))
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_REPORT)
    parser.add_argument("--schema-output", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args(argv)
    report = build_report(evidence_dir=args.evidence_dir)
    schema = generate_schema(report)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(report)
    markdown = render_markdown(report)
    if args.command == "generate":
        _write_text(
            args.json_output,
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            evidence_dir=args.evidence_dir,
        )
        _write_text(args.markdown_output, markdown, evidence_dir=args.evidence_dir)
        _write_text(
            args.schema_output,
            json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            evidence_dir=args.evidence_dir,
        )
    else:
        committed_report = _load_json(args.json_output, "已提交 JSON 报告")
        committed_schema = _load_json(args.schema_output, "已提交 Schema")
        if (
            committed_report != report
            or committed_schema != schema
            or args.markdown_output.read_text(encoding="utf-8") != markdown
        ):
            raise StageCV8ResultAuditError("已提交结果冻结材料与当前只读复算不一致")
    print(json.dumps(compact_summary(report), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
