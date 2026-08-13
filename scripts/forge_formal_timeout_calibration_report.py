#!/usr/bin/env python3
"""为 formal 模型请求 300 秒超时校准生成审计报告。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", Path(__file__).resolve().parents[1])).resolve()
SCRIPT_ROOT = Path(__file__).resolve().parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for root in (str(SCRIPT_ROOT), str(HARNESS_ROOT)):
    if root not in sys.path:
        sys.path.insert(0, root)

import forge_formal_collection_v4_authorized_report as parent_report  # noqa: E402
import forge_formal_timeout_calibration_protocol as protocol  # noqa: E402
import forge_formal_timeout_calibration_runner as runner  # noqa: E402

from deerflow.compile.evidence import EvidenceError  # noqa: E402

REPORT_VERSION = "formal-timeout-calibration-report-1.0.0"
DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_EVIDENCE_DIR = Path(protocol.EVIDENCE_DIRECTORY)
DEFAULT_JSON_REPORT = REPO_ROOT / "benchmarks" / "reports" / "cpp-formal-timeout-calibration.json"
DEFAULT_MARKDOWN_REPORT = REPO_ROOT / "benchmarks" / "reports" / "cpp-formal-timeout-calibration.md"
ReportError = parent_report.ReportError


def _load_canary_attempt_marker(evidence_dir: Path, *, manifest_sha256: str) -> dict[str, Any]:
    marker_path = evidence_dir / "provider-canaries" / "formal-v4-provider-canary-attempt.json"
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError("缺少有效的 timeout calibration canary marker") from exc
    if marker.get("benchmark_id") != "forge-cpp-formal-timeout-calibration":
        raise ReportError("timeout calibration canary identity 不匹配")
    if marker.get("manifest_sha256") != manifest_sha256 or marker.get("status") != "passed":
        raise ReportError("timeout calibration canary 未成功")
    return {
        "status": marker["status"],
        "updated_at": marker.get("updated_at"),
        "error_class": marker.get("error_class"),
    }


def build_report(manifest: dict[str, Any], evidence_dir: Path, **kwargs: Any) -> dict[str, Any]:
    original_protocol = parent_report.protocol
    original_runner = parent_report.runner
    original_marker_loader = parent_report._load_canary_attempt_marker
    parent_report.protocol = protocol
    parent_report.runner = runner
    parent_report._load_canary_attempt_marker = _load_canary_attempt_marker
    try:
        report = parent_report.build_report(manifest, evidence_dir, **kwargs)
    finally:
        parent_report.protocol = original_protocol
        parent_report.runner = original_runner
        parent_report._load_canary_attempt_marker = original_marker_loader
    report["report_version"] = REPORT_VERSION
    report["scope"].update(
        {
            "formal_comparison_enabled": False,
            "paired_primary_eligible": False,
            "descriptive_only": True,
        }
    )
    report["collection"]["stop_reason"] = "timeout_calibration_complete"
    report["interpretation"].update(
        {
            "request_timeout_seconds": protocol.REQUEST_TIMEOUT_SECONDS,
            "provider_retries": 0,
            "formal_primary_pooling_forbidden": True,
        }
    )
    report["limitations"] = [
        "本校准只检验 300 秒客户端截止点下的请求闭合情况，不进入模型能力主比较。",
        "若没有请求超过 120 秒，不能据此证明延长截止点能够挽救历史超时。",
        "单一项目、每个 provider 一次 attempt 不能支持稳定性或模型优劣结论。",
    ]
    return report


def render_markdown(report: dict[str, Any]) -> str:
    rendered = parent_report.render_markdown(report)
    rendered = rendered.replace(
        "# Forge C/C++ formal v4 首批完整项目块审计报告",
        "# Forge C/C++ formal 模型请求 300 秒超时校准报告",
        1,
    )
    rendered = rendered.replace(
        "scripts/forge_formal_collection_v4_authorized_report.py",
        "scripts/forge_formal_timeout_calibration_report.py",
    )
    rendered = rendered.replace(
        "/workspace/.compile-sessions/benchmark-evidence-formal-v4-authorized-initial-block",
        protocol.EVIDENCE_DIRECTORY,
    )
    rendered = rendered.replace(
        "- 只包含 `cppitertools` 的两个 condition × 三次重复；原 schedule identity 未重编号。",
        "- 只包含 `cppitertools` 的两个 condition 各一次；沿用原 schedule order `1, 2`。",
    )
    rendered = rendered.replace(
        "- 单个完整 block 只能用于首批工程有效性和配对描述，不能推出总体模型优劣。",
        "- 本批只校准请求截止点，不进入模型能力比较，也不能推出总体模型优劣。",
    )
    boundary = "- 本批 evidence 不进入 formal 模型能力主比较。\n- 请求超时固定 300 秒，provider retry 固定为 0。\n"
    return rendered.replace("## 复算\n", f"{boundary}\n## 复算\n", 1)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError(f"无法读取 manifest: {path}") from exc
    return protocol.validate_manifest(document)


def write_reports(report: dict[str, Any], *, json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    markdown_path.write_text(render_markdown(report), encoding="utf-8", newline="\n")


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
        write_reports(report, json_path=args.json_output, markdown_path=args.markdown_output)
    except (EvidenceError, ReportError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report["collection"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
