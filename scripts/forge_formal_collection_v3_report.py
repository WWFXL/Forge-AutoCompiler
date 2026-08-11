#!/usr/bin/env python3
"""Build a deterministic descriptive report for the authorized formal v3 prefix."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(
    os.environ.get("FORGE_REPO_ROOT", Path(__file__).resolve().parents[1])
).resolve()
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
SCRIPT_ROOT = Path(__file__).resolve().parent
for import_root in (str(HARNESS_ROOT), str(SCRIPT_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_benchmark_v8_report as common  # noqa: E402
import forge_formal_collection_v3_authorized_protocol as protocol  # noqa: E402
import forge_formal_collection_v3_authorized_runner as runner  # noqa: E402

from deerflow.compile.evidence import EvidenceError, ExperimentLedger  # noqa: E402

REPORT_VERSION = "formal-v3-initial-batch-report-1.0.0"
DEFAULT_MANIFEST = (
    REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-v3-authorized-collection.json"
)
DEFAULT_EVIDENCE_DIR = Path(
    "/workspace/.compile-sessions/benchmark-evidence-formal-v3-authorized"
)
DEFAULT_JSON_REPORT = (
    REPO_ROOT / "benchmarks" / "reports" / "cpp-formal-v3-initial-batch.json"
)
DEFAULT_MARKDOWN_REPORT = (
    REPO_ROOT / "benchmarks" / "reports" / "cpp-formal-v3-initial-batch.md"
)


class ReportError(ValueError):
    """Raised when evidence cannot support the formal v3 report."""


def _slot_key(item: dict[str, Any]) -> tuple[str, str, int]:
    return item["case_id"], item["condition_id"], item["repetition"]


def _ledger_slot(events: list[dict[str, Any]]) -> tuple[str, str, int]:
    started = [
        event["payload"] for event in events if event["event"] == "experiment.started"
    ]
    if len(started) != 1 or not isinstance(started[0].get("policy"), dict):
        raise ReportError("A formal ledger must contain one experiment.started policy")
    policy = started[0]["policy"]
    try:
        return policy["case_id"], policy["condition"], policy["repetition"]
    except KeyError as exc:
        raise ReportError(f"Formal ledger policy is missing {exc.args[0]}") from exc


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_canary_reports(
    evidence_dir: Path,
    *,
    manifest_sha256: str,
    condition_ids: set[str],
    first_ledger_time: str,
) -> dict[str, Any]:
    reports: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(
        (evidence_dir / "provider-canaries").glob("provider_canary_*.json")
    ):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReportError(f"Invalid provider canary report: {path.name}") from exc
        if document.get("document_type") != "formal_provider_canary":
            raise ReportError(
                f"Unexpected document in provider canary directory: {path.name}"
            )
        if document.get("manifest_sha256") != manifest_sha256:
            raise ReportError(
                "Provider canary manifest identity does not match formal v3"
            )
        reports.append((path, document))

    successful = [(path, item) for path, item in reports if item.get("passed") is True]
    if not successful:
        raise ReportError("A successful dual-provider canary is required")
    path, selected = successful[-1]
    conditions = selected.get("conditions")
    if (
        not isinstance(conditions, list)
        or {item.get("id") for item in conditions if isinstance(item, dict)}
        != condition_ids
    ):
        raise ReportError(
            "Successful canary does not cover the frozen provider conditions"
        )
    if any(item.get("passed") is not True for item in conditions):
        raise ReportError("Successful canary contains a failed provider condition")
    if common._parse_time(selected.get("completed_at")) >= common._parse_time(
        first_ledger_time
    ):
        raise ReportError(
            "Successful provider canary must precede the first formal ledger"
        )

    return {
        "reports_discovered": len(reports),
        "successful_reports": len(successful),
        "failed_reports": len(reports) - len(successful),
        "selected_canary_id": selected.get("canary_id"),
        "selected_report_sha256": _sha256(path),
        "selected_completed_at": selected.get("completed_at"),
        "conditions": [
            {
                "id": item.get("id"),
                "model": item.get("model"),
                "duration_ms": item.get("duration_ms"),
                "passed": item.get("passed"),
            }
            for item in conditions
        ],
    }


def _compiler_subagent_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    payloads = [
        event["payload"]
        for event in events
        if event["event"] == "agent.subagent_terminated"
        and event["payload"].get("role") == "compiler"
    ]
    statuses = Counter(payload.get("status", "unknown") for payload in payloads)
    classifications = Counter(
        payload["classification"]
        for payload in payloads
        if isinstance(payload.get("classification"), str)
    )
    elapsed = [
        payload["budget_snapshot"]["elapsed_seconds"]
        for payload in payloads
        if isinstance(payload.get("budget_snapshot"), dict)
        and isinstance(payload["budget_snapshot"].get("elapsed_seconds"), (int, float))
    ]
    limits = sorted(
        {
            payload["budget_snapshot"]["wall_clock_limit_seconds"]
            for payload in payloads
            if isinstance(payload.get("budget_snapshot"), dict)
            and isinstance(
                payload["budget_snapshot"].get("wall_clock_limit_seconds"),
                (int, float),
            )
        }
    )
    return {
        "invocations": len(payloads),
        "statuses": dict(sorted(statuses.items())),
        "failure_classifications": dict(sorted(classifications.items())),
        "worker_stopped": sum(
            payload.get("worker_stopped") is True for payload in payloads
        ),
        "elapsed_seconds": {
            "total": round(sum(elapsed), 3),
            "maximum": round(max(elapsed), 3) if elapsed else 0,
        },
        "wall_clock_limits_seconds": limits,
    }


def _discover_ledgers(
    evidence_dir: Path,
    *,
    ledger_verifier: Callable[[Path], list[dict[str, Any]]],
) -> dict[tuple[str, str, int], tuple[Path, list[dict[str, Any]]]]:
    discovered: dict[tuple[str, str, int], tuple[Path, list[dict[str, Any]]]] = {}
    for path in sorted(evidence_dir.glob("*/*/rep-*/physical_attempt_*.jsonl")):
        events = ledger_verifier(path)
        slot = _ledger_slot(events)
        if slot in discovered:
            raise ReportError(f"Formal slot {slot} has multiple ledgers")
        relative = path.relative_to(evidence_dir)
        try:
            path_slot = (
                relative.parts[0],
                relative.parts[1],
                int(relative.parts[2].removeprefix("rep-")),
            )
        except (IndexError, ValueError) as exc:
            raise ReportError(f"Invalid formal ledger path: {relative}") from exc
        if path_slot != slot:
            raise ReportError("Formal ledger path does not match its recorded policy")
        discovered[slot] = path, events
    return discovered


def build_report(
    manifest: dict[str, Any],
    evidence_dir: Path,
    *,
    ledger_verifier: Callable[
        [Path], list[dict[str, Any]]
    ] = ExperimentLedger.verify_path,
    gate_recomputer: Callable[
        [list[dict[str, Any]]], dict[str, Any]
    ] = runner.recompute_gates,
    oracle_runner: Callable[
        [dict[str, Any], list[dict[str, Any]]], dict[str, Any]
    ] = runner.run_oracle,
) -> dict[str, Any]:
    authorization = manifest["authorization"]
    constraints = authorization["collection_constraints"]
    budget = authorization["budget_confirmation"]
    authorized_count = int(constraints["authorized_slot_count"])
    authorized_plan = manifest["collection_plan"][:authorized_count]
    expected_slots = [_slot_key(slot) for slot in authorized_plan]
    if len(expected_slots) != len(set(expected_slots)):
        raise ReportError("Authorized formal v3 prefix contains duplicate slots")

    discovered = _discover_ledgers(
        evidence_dir,
        ledger_verifier=ledger_verifier,
    )
    if not discovered:
        raise ReportError("No formal v3 ledgers were discovered")
    if any(slot not in set(expected_slots) for slot in discovered):
        raise ReportError(
            "Evidence contains a slot outside the authorized formal prefix"
        )
    observed_count = len(discovered)
    if set(discovered) != set(expected_slots[:observed_count]):
        raise ReportError("Formal evidence is not a contiguous frozen schedule prefix")

    manifest_sha256 = protocol.manifest_sha256(manifest)
    attempts: list[dict[str, Any]] = []
    first_ledger_time: str | None = None
    for order, slot in enumerate(expected_slots[:observed_count], start=1):
        path, events = discovered[slot]
        if not events or events[-1]["event"] != "experiment.completed":
            raise ReportError("Every observed formal ledger must be terminal")
        first_ledger_time = first_ledger_time or events[0]["occurred_at"]
        metrics = common.extract_attempt_metrics(
            events,
            order=order,
            expected_slot=slot,
            expected_manifest_sha256=manifest_sha256,
            gates=gate_recomputer(events),
            oracle=oracle_runner(manifest, events),
        )
        cancelled_requests = sum(
            event["event"] == "model.request_cancelled" for event in events
        )
        metrics["model_requests"].update(
            {
                "cancelled": cancelled_requests,
                "closed": (
                    metrics["model_requests"]["completed"]
                    + metrics["model_requests"]["failed"]
                    + cancelled_requests
                ),
            }
        )
        metrics.update(
            {
                "physical_attempt_id": events[0]["physical_attempt_id"],
                "ledger_terminal_sha256": events[-1]["event_sha256"],
                "compiler_subagents": _compiler_subagent_metrics(events),
            }
        )
        attempts.append(metrics)

    recorded_tokens = sum(
        attempt["token_usage"]["total_tokens"] for attempt in attempts
    )
    token_limit = int(budget["maximum_recorded_tokens"])
    if recorded_tokens >= token_limit:
        stop_reason = "recorded_token_boundary_reached"
    elif observed_count == authorized_count:
        stop_reason = "authorized_batch_boundary_reached"
    else:
        raise ReportError(
            "A short authorized prefix must reach the recorded-token boundary"
        )

    canary = _load_canary_reports(
        evidence_dir,
        manifest_sha256=manifest_sha256,
        condition_ids={condition["id"] for condition in manifest["conditions"]},
        first_ledger_time=first_ledger_time,
    )
    condition_order = [condition["id"] for condition in manifest["conditions"]]
    conditions = [
        common._condition_summary(
            condition_id,
            [
                attempt
                for attempt in attempts
                if attempt["condition_id"] == condition_id
            ],
        )
        for condition_id in condition_order
        if any(attempt["condition_id"] == condition_id for attempt in attempts)
    ]
    for condition in conditions:
        condition_attempts = [
            attempt
            for attempt in attempts
            if attempt["condition_id"] == condition["condition_id"]
        ]
        condition["model_requests"].update(
            {
                "cancelled": sum(
                    attempt["model_requests"]["cancelled"]
                    for attempt in condition_attempts
                ),
                "closed": sum(
                    attempt["model_requests"]["closed"]
                    for attempt in condition_attempts
                ),
            }
        )
    failure_events: Counter[str] = Counter()
    for attempt in attempts:
        for domain, classifications in attempt["failure_domains"].items():
            for classification in classifications:
                failure_events[f"{domain}:{classification}"] += 1

    return {
        "report_version": REPORT_VERSION,
        "benchmark_id": manifest["benchmark"]["id"],
        "manifest_sha256": manifest_sha256,
        "scope": {
            "languages": manifest["scope"]["languages"],
            "phase": manifest["scope"]["phase"],
            "formal_comparison_enabled": manifest["scope"]["formal_comparison_enabled"],
            "descriptive_only": True,
        },
        "authorization": {
            "authorized_slots": authorized_count,
            "remaining_slots_require_confirmation": constraints[
                "remaining_slots_require_additional_confirmation"
            ],
            "maximum_recorded_tokens": token_limit,
            "budget_enforcement": budget["enforcement"],
            "access_medium": authorization["network_observation"]["access_medium"],
        },
        "canary": canary,
        "collection": {
            "authorized_slots": authorized_count,
            "analyzed_slots": observed_count,
            "next_slot_index": observed_count,
            "stop_reason": stop_reason,
            "recorded_total_tokens": recorded_tokens,
            "recorded_token_limit": token_limit,
            "recorded_tokens_over_boundary": max(0, recorded_tokens - token_limit),
            "ledger_hash_chain_valid": observed_count,
            "gate_recomputation_valid": observed_count,
            "actual_model_matches": sum(
                attempt["actual_model_match"] is True for attempt in attempts
            ),
            "terminal_completed": sum(
                attempt["terminal_status"] in {"passed", "failed"}
                for attempt in attempts
            ),
            "oracle_passed": sum(attempt["oracle_passed"] for attempt in attempts),
            "oracle_failed": sum(not attempt["oracle_passed"] for attempt in attempts),
            "session_finalization_succeeded": sum(
                attempt["session_finalization_succeeded"] is True
                for attempt in attempts
            ),
            "orphan_cleanup_succeeded": sum(
                attempt["orphan_cleanup_succeeded"] is True for attempt in attempts
            ),
            "orphan_count": sum(attempt["orphan_count"] or 0 for attempt in attempts),
            "model_requests": {
                key: sum(attempt["model_requests"][key] for attempt in attempts)
                for key in ("started", "completed", "failed", "cancelled", "closed")
            },
            "compiler_subagent_invocations": sum(
                attempt["compiler_subagents"]["invocations"] for attempt in attempts
            ),
            "attempt_duration_seconds": round(
                sum(attempt["attempt_duration_seconds"] for attempt in attempts), 3
            ),
        },
        "failure_event_counts": dict(sorted(failure_events.items())),
        "conditions": conditions,
        "attempts": attempts,
        "interpretation": {
            "valid_outcome_denominator": observed_count,
            "slots_8_to_10_not_created": observed_count < authorized_count,
            "provider_timeout_observed": any(
                attempt["model_requests"]["failed"] > 0 for attempt in attempts
            ),
            "attempt_level_wall_clock_budget_present": False,
            "compiler_wall_clock_budget_is_per_invocation": True,
            "historical_ledgers_modified": False,
            "retry_replacement_backfill_performed": False,
        },
        "limitations": [
            "The recorded-token boundary stopped collection after seven of ten authorized slots, so provider and case counts are unbalanced.",
            "Seven one-repetition slots cannot support a population-level model ranking or significance claim.",
            "The 900-second compiler wall-clock budget applies per compiler invocation, not to the whole physical attempt.",
            "The mobile-hotspot label records access medium but does not identify the cause of historical endpoint timeouts.",
        ],
    }


def _format_failures(attempt: dict[str, Any]) -> str:
    domains = [
        *common.FAILURE_DOMAIN_ORDER,
        *sorted(set(attempt["failure_domains"]) - set(common.FAILURE_DOMAIN_ORDER)),
    ]
    values = [
        f"{domain}:{classification}"
        for domain in domains
        for classification in attempt["failure_domains"].get(domain, [])
    ]
    return "<br>".join(values) if values else "-"


def render_markdown(report: dict[str, Any]) -> str:
    collection = report["collection"]
    lines = [
        "# Forge C/C++ formal v3 首批描述性审计报告",
        "",
        "> 状态：预算边界停止后的冻结描述性复核；不是模型总体排名。",
        "",
        "## 摘要",
        "",
        f"- 首批完成 {collection['analyzed_slots']}/{collection['authorized_slots']} 个授权 slot，"
        f"停止原因为 `{collection['stop_reason']}`；slot 8-10 未创建。",
        f"- Oracle 通过 {collection['oracle_passed']}/{collection['analyzed_slots']}；"
        f"ledger hash chain、离线 gate、Session finalization 与 cleanup 均为 "
        f"{collection['analyzed_slots']}/{collection['analyzed_slots']}，orphan={collection['orphan_count']}。",
        f"- 记录 {collection['recorded_total_tokens']:,} tokens；边界 "
        f"{collection['recorded_token_limit']:,}，完成中的 slot 使最终值越界 "
        f"{collection['recorded_tokens_over_boundary']:,}，随后未创建下一槽。",
        f"- 双 provider canary 选用 `{report['canary']['selected_canary_id']}`；"
        f"正式批次请求闭合 {collection['model_requests']['closed']}/"
        f"{collection['model_requests']['started']}，其中完成 "
        f"{collection['model_requests']['completed']}、失败 "
        f"{collection['model_requests']['failed']}、取消 "
        f"{collection['model_requests']['cancelled']}。",
        "",
        "## Condition 汇总",
        "",
        "| Condition | Oracle | Attempts | Requests closed/started/failed/cancelled | Tokens | Compiler calls | Wall time (s) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for condition in report["conditions"]:
        compiler_calls = sum(
            attempt["compiler_subagents"]["invocations"]
            for attempt in report["attempts"]
            if attempt["condition_id"] == condition["condition_id"]
        )
        requests = condition["model_requests"]
        lines.append(
            f"| `{condition['condition_id']}` | {condition['oracle_passed']}/{condition['attempts']} | "
            f"{condition['attempts']} | {requests['closed']}/{requests['started']}/"
            f"{requests['failed']}/{requests['cancelled']} | "
            f"{condition['token_usage']['total_tokens']:,} | "
            f"{compiler_calls} | {condition['attempt_duration_seconds']['total']:.3f} |"
        )

    lines.extend(
        [
            "",
            "## 每个 slot",
            "",
            "| # | Case | Condition | Oracle | Tokens | Wall time (s) | Compiler calls | Submit | Replay | Failures |",
            "|---:|---|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for attempt in report["attempts"]:
        lines.append(
            f"| {attempt['order']} | `{attempt['case_id']}` | `{attempt['condition_id']}` | "
            f"{'pass' if attempt['oracle_passed'] else 'fail'} | "
            f"{attempt['token_usage']['total_tokens']:,} | {attempt['attempt_duration_seconds']:.3f} | "
            f"{attempt['compiler_subagents']['invocations']} | {attempt['submits']['completed']} | "
            f"{attempt['clean_replays']['passed']}/{attempt['clean_replays']['completed']} | "
            f"{_format_failures(attempt)} |"
        )

    lines.extend(
        [
            "",
            "## 有效性与预算解释",
            "",
            "- 7 个 ledger 均为冻结 schedule 的连续前缀；没有 retry、replacement 或 backfill。",
            "- Token 边界在创建下一槽前检查，不会中途截断已经创建的 physical attempt。",
            "- 当前 900 秒 wall-clock 是每次 Compiler 调用的预算。同一 physical attempt 可由 Lead 多次调用 Compiler，因此 attempt 总时长可以超过 900 秒。",
            "- 下一协议应预注册独立的 physical-attempt 总时限；该建议不改变 v3 结果，也不授权补跑 slot 8-10。",
            "- 手机热点是已记录的接入分类，不足以把历史 endpoint timeout 归因于热点、WSL、路由或 provider 中任一层。",
            "",
            "## 研究边界",
            "",
            "- 当前有效分母为实际创建并终结的 7 个 slot，不是计划中的 10，也不是完整 180 槽。",
            "- Condition 样本不平衡且每个 case 仅一次，不能做显著性检验或总体模型排名。",
            "- 剩余 170 槽仍需实验所有者再次确认；slot 8-10 也不能在当前 token 授权下继续创建。",
            "",
            "## 复算",
            "",
            "```bash",
            "/app/backend/.venv/bin/python /repo/scripts/forge_formal_collection_v3_report.py \\",
            "  --evidence-dir /workspace/.compile-sessions/benchmark-evidence-formal-v3-authorized",
            "```",
            "",
            "JSON 是机器可读来源；Markdown 由同一分析器确定性生成。",
            "",
        ]
    )
    return "\n".join(lines)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError(f"Unable to load manifest: {path}") from exc
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
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")


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
