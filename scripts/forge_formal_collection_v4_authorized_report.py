#!/usr/bin/env python3
"""为 formal v4 首批授权项目块生成确定性审计报告。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", Path(__file__).resolve().parents[1])).resolve()
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
SCRIPT_ROOT = Path(__file__).resolve().parent
for import_root in (str(HARNESS_ROOT), str(SCRIPT_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_benchmark_v8_report as common  # noqa: E402
import forge_formal_collection_v3_report as report_common  # noqa: E402
import forge_formal_collection_v4_authorized_protocol as protocol  # noqa: E402
import forge_formal_collection_v4_authorized_runner as runner  # noqa: E402

from deerflow.compile.evidence import EvidenceError, ExperimentLedger  # noqa: E402

REPORT_VERSION = "formal-v4-authorized-initial-block-report-1.0.0"
DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_EVIDENCE_DIR = Path(protocol.AUTHORIZED_EVIDENCE_DIRECTORY)
DEFAULT_JSON_REPORT = REPO_ROOT / "benchmarks" / "reports" / "cpp-formal-v4-authorized-initial-block.json"
DEFAULT_MARKDOWN_REPORT = REPO_ROOT / "benchmarks" / "reports" / "cpp-formal-v4-authorized-initial-block.md"


class ReportError(ValueError):
    """证据不足以形成 formal v4 首批报告。"""


def _slot_key(item: dict[str, Any]) -> tuple[str, str, int]:
    return item["case_id"], item["condition_id"], item["repetition"]


def _authorized_plan(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    orders = manifest["authorization"]["collection_constraints"]["authorized_schedule_orders"]
    by_order = {slot["order"]: slot for slot in manifest["collection_plan"]}
    try:
        return [by_order[order] for order in orders]
    except KeyError as exc:
        raise ReportError("授权 order 不存在于冻结 collection plan") from exc


def _load_canary_attempt_marker(
    evidence_dir: Path,
    *,
    manifest_sha256: str,
) -> dict[str, Any]:
    marker_path = evidence_dir / "provider-canaries" / "formal-v4-provider-canary-attempt.json"
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError("缺少有效的 formal v4 provider-canary attempt marker") from exc
    if marker.get("document_type") != "formal_provider_canary_attempt":
        raise ReportError("provider-canary attempt marker 结构无效")
    if marker.get("benchmark_id") != "forge-cpp-formal-v4-authorized-initial-block":
        raise ReportError("provider-canary attempt marker benchmark identity 不匹配")
    if marker.get("manifest_sha256") != manifest_sha256 or marker.get("status") != "passed":
        raise ReportError("provider-canary attempt marker 未记录同协议的成功终态")
    return {
        "status": marker["status"],
        "updated_at": marker.get("updated_at"),
        "error_class": marker.get("error_class"),
    }


def build_report(
    manifest: dict[str, Any],
    evidence_dir: Path,
    *,
    ledger_verifier: Callable[[Path], list[dict[str, Any]]] = ExperimentLedger.verify_path,
    gate_recomputer: Callable[[list[dict[str, Any]]], dict[str, Any]] = runner.recompute_gates,
    oracle_runner: Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]] = runner.run_oracle,
) -> dict[str, Any]:
    authorization = manifest["authorization"]
    constraints = authorization["collection_constraints"]
    budget = authorization["budget_confirmation"]
    authorized_plan = _authorized_plan(manifest)
    expected_slots = [_slot_key(slot) for slot in authorized_plan]
    if len(expected_slots) != len(set(expected_slots)):
        raise ReportError("授权 formal v4 project block 含重复 slot")

    try:
        discovered = report_common._discover_ledgers(
            evidence_dir,
            ledger_verifier=ledger_verifier,
        )
    except report_common.ReportError as exc:
        raise ReportError(str(exc)) from exc
    if not discovered:
        raise ReportError("未发现 formal v4 ledger")
    if any(slot not in set(expected_slots) for slot in discovered):
        raise ReportError("证据包含授权 project block 之外的 slot")
    observed_count = len(discovered)
    if set(discovered) != set(expected_slots[:observed_count]):
        raise ReportError("formal v4 evidence 不是授权顺序的严格前缀")

    manifest_sha256 = protocol.manifest_sha256(manifest)
    attempts: list[dict[str, Any]] = []
    first_ledger_time: str | None = None
    for authorized_index, slot in enumerate(
        expected_slots[:observed_count],
        start=1,
    ):
        path, events = discovered[slot]
        if not events or events[-1]["event"] != "experiment.completed":
            raise ReportError("每个已观察 formal v4 ledger 必须进入 experiment.completed")
        first_ledger_time = first_ledger_time or events[0]["occurred_at"]
        metrics = common.extract_attempt_metrics(
            events,
            order=authorized_index,
            expected_slot=slot,
            expected_manifest_sha256=manifest_sha256,
            gates=gate_recomputer(events),
            oracle=oracle_runner(manifest, events),
        )
        cancelled = sum(event["event"] == "model.request_cancelled" for event in events)
        metrics["model_requests"].update(
            {
                "cancelled": cancelled,
                "closed": (metrics["model_requests"]["completed"] + metrics["model_requests"]["failed"] + cancelled),
            }
        )
        metrics.update(
            {
                "authorized_index": authorized_index - 1,
                "schedule_order": authorized_plan[authorized_index - 1]["order"],
                "physical_attempt_id": events[0]["physical_attempt_id"],
                "ledger_terminal_sha256": events[-1]["event_sha256"],
                "compiler_subagents": report_common._compiler_subagent_metrics(events),
            }
        )
        attempts.append(metrics)

    recorded_tokens = sum(attempt["token_usage"]["total_tokens"] for attempt in attempts)
    token_limit = int(budget["maximum_recorded_tokens"])
    if observed_count == len(expected_slots):
        stop_reason = "authorized_complete_project_block_reached"
    elif recorded_tokens >= token_limit:
        stop_reason = "recorded_token_boundary_reached"
    else:
        raise ReportError("不完整 project block 必须已达到 recorded-token boundary")

    assert first_ledger_time is not None
    try:
        canary = report_common._load_canary_reports(
            evidence_dir,
            manifest_sha256=manifest_sha256,
            condition_ids={condition["id"] for condition in manifest["conditions"]},
            first_ledger_time=first_ledger_time,
        )
    except report_common.ReportError as exc:
        raise ReportError(str(exc)) from exc
    canary["attempt_marker"] = _load_canary_attempt_marker(
        evidence_dir,
        manifest_sha256=manifest_sha256,
    )

    conditions = [
        common._condition_summary(
            condition["id"],
            [attempt for attempt in attempts if attempt["condition_id"] == condition["id"]],
        )
        for condition in manifest["conditions"]
        if any(attempt["condition_id"] == condition["id"] for attempt in attempts)
    ]
    for condition in conditions:
        condition_attempts = [attempt for attempt in attempts if attempt["condition_id"] == condition["condition_id"]]
        condition["model_requests"].update(
            {
                "cancelled": sum(attempt["model_requests"]["cancelled"] for attempt in condition_attempts),
                "closed": sum(attempt["model_requests"]["closed"] for attempt in condition_attempts),
            }
        )
    failure_events: Counter[str] = Counter()
    for attempt in attempts:
        for domain, classifications in attempt["failure_domains"].items():
            for classification in classifications:
                failure_events[f"{domain}:{classification}"] += 1

    complete_block = observed_count == len(expected_slots)
    return {
        "report_version": REPORT_VERSION,
        "benchmark_id": manifest["benchmark"]["id"],
        "manifest_sha256": manifest_sha256,
        "scope": {
            "languages": manifest["scope"]["languages"],
            "phase": manifest["scope"]["phase"],
            "formal_comparison_enabled": manifest["scope"]["formal_comparison_enabled"],
            "paired_primary_eligible": complete_block,
            "descriptive_only": not complete_block,
        },
        "authorization": {
            "authorized_schedule_orders": constraints["authorized_schedule_orders"],
            "remaining_slots_require_confirmation": constraints["remaining_slots_require_additional_confirmation"],
            "maximum_recorded_tokens": token_limit,
            "budget_enforcement": budget["enforcement"],
            "access_medium": authorization["network_observation"]["access_medium"],
        },
        "canary": canary,
        "collection": {
            "authorized_slots": len(expected_slots),
            "analyzed_slots": observed_count,
            "next_authorized_index": observed_count,
            "stop_reason": stop_reason,
            "complete_project_block": complete_block,
            "recorded_total_tokens": recorded_tokens,
            "recorded_token_limit": token_limit,
            "recorded_tokens_over_boundary": max(0, recorded_tokens - token_limit),
            "ledger_hash_chain_valid": observed_count,
            "gate_recomputation_valid": sum(attempt["offline_gate_recomputation_valid"] is True for attempt in attempts),
            "actual_model_matches": sum(attempt["actual_model_match"] is True for attempt in attempts),
            "terminal_completed": sum(attempt["terminal_status"] in {"passed", "failed"} for attempt in attempts),
            "oracle_passed": sum(attempt["oracle_passed"] for attempt in attempts),
            "oracle_failed": sum(not attempt["oracle_passed"] for attempt in attempts),
            "session_finalization_succeeded": sum(attempt["session_finalization_succeeded"] is True for attempt in attempts),
            "orphan_cleanup_succeeded": sum(attempt["orphan_cleanup_succeeded"] is True for attempt in attempts),
            "orphan_count": sum(attempt["orphan_count"] or 0 for attempt in attempts),
            "model_requests": {
                key: sum(attempt["model_requests"][key] for attempt in attempts)
                for key in (
                    "started",
                    "completed",
                    "failed",
                    "cancelled",
                    "closed",
                )
            },
            "compiler_subagent_invocations": sum(attempt["compiler_subagents"]["invocations"] for attempt in attempts),
            "attempt_duration_seconds": round(
                sum(attempt["attempt_duration_seconds"] for attempt in attempts),
                3,
            ),
        },
        "failure_event_counts": dict(sorted(failure_events.items())),
        "conditions": conditions,
        "attempts": attempts,
        "interpretation": {
            "complete_block_required_for_paired_primary": True,
            "v3_slots_8_to_10_created": False,
            "historical_ledgers_modified": False,
            "retry_replacement_backfill_performed": False,
            "ubuntu_native_daemon_required": True,
        },
        "limitations": [
            "一个完整 project block 仍不足以支持总体模型排名或显著性结论。",
            "recorded-token boundary 若提前停止，已有 attempt 只进入描述性分母。",
            "网络接入分类不能识别 endpoint failure 的具体因果层。",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    collection = report["collection"]
    lines = [
        "# Forge C/C++ formal v4 首批完整项目块审计报告",
        "",
        "> 本报告由冻结分析器确定性生成。",
        "",
        "## 摘要",
        "",
        f"- 完成 {collection['analyzed_slots']}/{collection['authorized_slots']} 个授权 slot；停止原因为 `{collection['stop_reason']}`。",
        f"- complete project block={str(collection['complete_project_block']).lower()}，paired-primary eligible={str(report['scope']['paired_primary_eligible']).lower()}。",
        f"- Oracle 通过 {collection['oracle_passed']}/{collection['analyzed_slots']}；ledger hash chain 有效 {collection['ledger_hash_chain_valid']}/{collection['analyzed_slots']}，orphan={collection['orphan_count']}。",
        f"- 记录 {collection['recorded_total_tokens']:,}/{collection['recorded_token_limit']:,} tokens。",
        "",
        "## 每个 slot",
        "",
        "| 授权序号 | 原 schedule order | Condition | Repetition | Oracle | Tokens | Wall time (s) |",
        "|---:|---:|---|---:|---:|---:|---:|",
    ]
    for attempt in report["attempts"]:
        lines.append(
            f"| {attempt['authorized_index'] + 1} | {attempt['schedule_order']} | `{attempt['condition_id']}` | "
            f"{attempt['repetition']} | {'pass' if attempt['oracle_passed'] else 'fail'} | "
            f"{attempt['token_usage']['total_tokens']:,} | {attempt['attempt_duration_seconds']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## 边界",
            "",
            "- 只包含 `cppitertools` 的两个 condition × 三次重复；原 schedule identity 未重编号。",
            "- 没有 retry、fallback、replacement、backfill，也没有创建 v3 slot 8-10。",
            "- 单个完整 block 只能用于首批工程有效性和配对描述，不能推出总体模型优劣。",
            "",
            "## 复算",
            "",
            "```bash",
            "/app/backend/.venv/bin/python /repo/scripts/forge_formal_collection_v4_authorized_report.py \\",
            "  --evidence-dir /workspace/.compile-sessions/benchmark-evidence-formal-v4-authorized-initial-block",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError(f"无法读取 manifest: {path}") from exc
    protocol.validate_manifest(document)
    return document


def write_reports(
    report: dict[str, Any],
    *,
    json_path: Path,
    markdown_path: Path,
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    markdown_path.write_text(
        render_markdown(report),
        encoding="utf-8",
        newline="\n",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_REPORT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = build_report(load_manifest(args.manifest), args.evidence_dir)
        write_reports(
            report,
            json_path=args.json_output,
            markdown_path=args.markdown_output,
        )
    except (EvidenceError, ReportError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report["collection"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
