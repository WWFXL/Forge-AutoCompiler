#!/usr/bin/env python3
"""为 formal v4 canary amendment 生成确定性审计报告。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", Path(__file__).resolve().parents[1])).resolve()
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
SCRIPT_ROOT = Path(__file__).resolve().parent
for import_root in (str(HARNESS_ROOT), str(SCRIPT_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_formal_collection_v4_authorized_report as parent_report  # noqa: E402
import forge_formal_collection_v4_canary_amendment_protocol as protocol  # noqa: E402
import forge_formal_collection_v4_canary_amendment_runner as runner  # noqa: E402

from deerflow.compile.evidence import EvidenceError  # noqa: E402

REPORT_VERSION = "formal-v4-canary-amendment-report-1.0.0"
DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_EVIDENCE_DIR = Path(protocol.AUTHORIZED_EVIDENCE_DIRECTORY)
DEFAULT_DIAGNOSTIC_DIR = Path(protocol.DIAGNOSTIC_DIRECTORY)
DEFAULT_LEGACY_EVIDENCE_DIR = Path(protocol.LEGACY_EVIDENCE_DIRECTORY)
DEFAULT_JSON_REPORT = REPO_ROOT / "benchmarks" / "reports" / "cpp-formal-v4-canary-amendment.json"
DEFAULT_MARKDOWN_REPORT = REPO_ROOT / "benchmarks" / "reports" / "cpp-formal-v4-canary-amendment.md"

ReportError = parent_report.ReportError


def _load_canary_attempt_marker(
    evidence_dir: Path,
    *,
    manifest_sha256: str,
) -> dict[str, Any]:
    marker_path = evidence_dir / "provider-canaries" / "formal-v4-canary-amendment-provider-canary-attempt.json"
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError("缺少有效的 formal v4 amendment provider-canary attempt marker") from exc
    if marker.get("document_type") != "formal_provider_canary_attempt":
        raise ReportError("amendment provider-canary attempt marker 结构无效")
    if marker.get("benchmark_id") != "forge-cpp-formal-v4-canary-amendment":
        raise ReportError("amendment provider-canary attempt marker benchmark identity 不匹配")
    if marker.get("manifest_sha256") != manifest_sha256 or marker.get("status") != "passed":
        raise ReportError("amendment provider-canary attempt marker 未记录同协议的成功终态")
    return {
        "status": marker["status"],
        "updated_at": marker.get("updated_at"),
        "error_class": marker.get("error_class"),
    }


def build_report(
    manifest: dict[str, Any],
    evidence_dir: Path,
    *,
    diagnostic_dir: Path = DEFAULT_DIAGNOSTIC_DIR,
    legacy_evidence_dir: Path = DEFAULT_LEGACY_EVIDENCE_DIR,
    **kwargs: Any,
) -> dict[str, Any]:
    original_protocol = parent_report.protocol
    original_runner = parent_report.runner
    original_marker_loader = parent_report._load_canary_attempt_marker
    parent_report.protocol = protocol
    parent_report.runner = runner
    parent_report._load_canary_attempt_marker = _load_canary_attempt_marker
    try:
        report = parent_report.build_report(
            manifest,
            evidence_dir,
            **kwargs,
        )
        diagnostics = runner._load_diagnostic_summary(
            manifest,
            output_dir=diagnostic_dir,
            require_passed=True,
        )
        legacy_terminal = runner._verify_legacy_terminal(
            manifest,
            legacy_output_dir=legacy_evidence_dir,
        )
    except runner.RunnerError as exc:
        raise ReportError(str(exc)) from exc
    finally:
        parent_report.protocol = original_protocol
        parent_report.runner = original_runner
        parent_report._load_canary_attempt_marker = original_marker_loader
    report["report_version"] = REPORT_VERSION
    report["diagnostics"] = diagnostics
    report["superseded_canary_terminal"] = legacy_terminal
    report["interpretation"].update(
        {
            "diagnostics_excluded_from_formal_denominator": True,
            "superseded_canary_terminal_preserved": True,
            "anonymous_models_endpoint_preflight_used": False,
        }
    )
    return report


def render_markdown(report: dict[str, Any]) -> str:
    rendered = parent_report.render_markdown(report)
    rendered = rendered.replace(
        "# Forge C/C++ formal v4 首批完整项目块审计报告",
        "# Forge C/C++ formal v4 canary amendment 审计报告",
        1,
    )
    rendered = rendered.replace(
        "scripts/forge_formal_collection_v4_authorized_report.py",
        "scripts/forge_formal_collection_v4_canary_amendment_report.py",
    )
    rendered = rendered.replace(
        "/workspace/.compile-sessions/benchmark-evidence-formal-v4-authorized-initial-block",
        "/workspace/.compile-sessions/benchmark-evidence-formal-v4-canary-amendment",
    )
    boundary = "- 有限诊断与 formal evidence 分目录保存，不进入模型编译能力分母。\n- 旧 canary 失败 marker 保持原 SHA-256、失败终态、0 report 和 0 ledger。\n"
    return rendered.replace("## 复算\n", f"{boundary}\n## 复算\n", 1)


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
    parser.add_argument("--diagnostic-dir", type=Path, default=DEFAULT_DIAGNOSTIC_DIR)
    parser.add_argument("--legacy-evidence-dir", type=Path, default=DEFAULT_LEGACY_EVIDENCE_DIR)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_REPORT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = build_report(
            load_manifest(args.manifest),
            args.evidence_dir,
            diagnostic_dir=args.diagnostic_dir,
            legacy_evidence_dir=args.legacy_evidence_dir,
        )
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
