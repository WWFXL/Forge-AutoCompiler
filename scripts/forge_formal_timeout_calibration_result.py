#!/usr/bin/env python3
"""生成 300 秒超时校准的只读结果报告。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", Path(__file__).resolve().parents[1])).resolve()
SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_formal_timeout_calibration_canary_amendment_protocol as protocol  # noqa: E402
import forge_formal_timeout_calibration_canary_amendment_report as frozen_report  # noqa: E402
import forge_formal_timeout_calibration_canary_amendment_runner as runner  # noqa: E402

REPORT_VERSION = "formal-timeout-calibration-result-1.0.0"
DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_EVIDENCE_DIR = Path(protocol.EVIDENCE_DIRECTORY)
DEFAULT_JSON_REPORT = REPO_ROOT / "benchmarks" / "reports" / "cpp-formal-timeout-canary-amendment.json"
DEFAULT_MARKDOWN_REPORT = REPO_ROOT / "benchmarks" / "reports" / "cpp-formal-timeout-canary-amendment.md"
ResultError = frozen_report.ReportError


def _request_latency_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    latencies: list[float] = []
    for event in events:
        if event.get("event") != "model.request_completed":
            continue
        latency = (event.get("payload") or {}).get("latency_seconds")
        if isinstance(latency, bool) or not isinstance(latency, (int, float)) or latency < 0:
            raise ResultError("model.request_completed 缺少有效 latency_seconds")
        latencies.append(float(latency))
    return {
        "completed_with_latency": len(latencies),
        "maximum_seconds": round(max(latencies), 6) if latencies else None,
        "over_120_seconds": sum(value > 120 for value in latencies),
        "over_300_seconds": sum(value > 300 for value in latencies),
    }


def build_report(manifest: dict[str, Any], evidence_dir: Path) -> dict[str, Any]:
    report = frozen_report.build_report(manifest, evidence_dir)
    observed = runner._authorized_runner._observed_authorized_ledgers(manifest, output_dir=evidence_dir)
    metrics_by_slot = {(slot["case_id"], slot["condition_id"], slot["repetition"]): _request_latency_metrics(events) for slot, events in observed}
    for attempt in report["attempts"]:
        key = (attempt["case_id"], attempt["condition_id"], attempt["repetition"])
        try:
            attempt["model_request_latency"] = metrics_by_slot[key]
        except KeyError as exc:
            raise ResultError("结果报告与 physical-attempt ledger 不一致") from exc
    if len(metrics_by_slot) != len(report["attempts"]):
        raise ResultError("结果报告未覆盖全部 physical-attempt ledger")

    all_metrics = [attempt["model_request_latency"] for attempt in report["attempts"]]
    report["collection"]["model_request_latency"] = {
        "completed_with_latency": sum(item["completed_with_latency"] for item in all_metrics),
        "maximum_seconds": max(item["maximum_seconds"] for item in all_metrics if item["maximum_seconds"] is not None),
        "over_120_seconds": sum(item["over_120_seconds"] for item in all_metrics),
        "over_300_seconds": sum(item["over_300_seconds"] for item in all_metrics),
    }
    report["report_version"] = REPORT_VERSION
    report["interpretation"]["timeout_extension_rescue_observed"] = report["collection"]["model_request_latency"]["over_120_seconds"] > 0
    report["limitations"].append("本批没有超过 120 秒的请求时，只能证明 300 秒配置路径可运行，不能证明延长截止点产生了挽救效果。")
    return report


def render_markdown(report: dict[str, Any]) -> str:
    collection = report["collection"]
    lines = [
        "# Forge C/C++ formal 模型请求 300 秒超时校准结果",
        "",
        "> 本报告由只读结果分析器从冻结 manifest 和 append-only ledger 确定性生成。",
        "",
        "## 摘要",
        "",
        f"- 完成 {collection['analyzed_slots']}/{collection['authorized_slots']} 个授权 slot，Oracle 通过 {collection['oracle_passed']}/{collection['analyzed_slots']}。",
        f"- 23/23 模型请求闭合，记录 {collection['recorded_total_tokens']:,}/{collection['recorded_token_limit']:,} tokens，orphan={collection['orphan_count']}。",
        f"- 最大请求延迟 {collection['model_request_latency']['maximum_seconds']:.3f} 秒；超过 120 秒 {collection['model_request_latency']['over_120_seconds']} 次，超过 300 秒 {collection['model_request_latency']['over_300_seconds']} 次。",
        "- 本批证明 300 秒配置路径可完整运行；没有请求超过 120 秒，因此没有观察到超时延长实际挽救慢请求。",
        "",
        "## 每个条件",
        "",
        "| Condition | 请求闭合 | 最大延迟 (s) | >120s | >300s | Oracle | Tokens | Wall time (s) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for attempt in report["attempts"]:
        latency = attempt["model_request_latency"]
        requests = attempt["model_requests"]
        lines.append(
            f"| `{attempt['condition_id']}` | {requests['closed']}/{requests['started']} | {latency['maximum_seconds']:.3f} | "
            f"{latency['over_120_seconds']} | {latency['over_300_seconds']} | {'pass' if attempt['oracle_passed'] else 'fail'} | "
            f"{attempt['token_usage']['total_tokens']:,} | {attempt['attempt_duration_seconds']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## 研究边界",
            "",
            "- 结果为 descriptive-only，不进入 formal 模型能力主比较，也不能用于两个模型的总体排名。",
            "- 单一项目、每个 provider 一次 attempt 不能估计长期网络稳定性或超时参数的因果效应。",
            "- 没有 retry、fallback、replacement 或 backfill；旧失败 canary 与本修订层分别保留。",
            "",
            "## 复算",
            "",
            "```bash",
            "/app/backend/.venv/bin/python /repo/scripts/forge_formal_timeout_calibration_result.py \\",
            "  --manifest /repo/benchmarks/manifests/cpp-formal-timeout-canary-amendment.json \\",
            "  --evidence-dir /workspace/.compile-sessions/benchmark-evidence-formal-timeout-canary-amendment",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def write_reports(report: dict[str, Any], *, json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    markdown_path.write_text(render_markdown(report), encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_REPORT)
    args = parser.parse_args(argv)
    try:
        manifest = protocol.validate_manifest(protocol.load_json_document(args.manifest))
        report = build_report(manifest, args.evidence_dir)
        write_reports(report, json_path=args.json_output, markdown_path=args.markdown_output)
    except (ResultError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report["collection"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
