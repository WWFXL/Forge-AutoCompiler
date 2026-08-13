#!/usr/bin/env python3
"""生成 300 秒超时校准 canary 修订审计报告。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_formal_timeout_calibration_canary_amendment_protocol as protocol  # noqa: E402
import forge_formal_timeout_calibration_canary_amendment_runner as runner  # noqa: E402


def _load_parent_report():
    name = f"{__name__}_parent"
    spec = importlib.util.spec_from_file_location(name, SCRIPT_ROOT / "forge_formal_timeout_calibration_report.py")
    if spec is None or spec.loader is None:
        raise ImportError("Unable to load the timeout calibration report")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


parent_report = _load_parent_report()
ReportError = parent_report.ReportError
DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_EVIDENCE_DIR = Path(protocol.EVIDENCE_DIRECTORY)
DEFAULT_JSON_REPORT = REPO_ROOT / "benchmarks" / "reports" / "cpp-formal-timeout-canary-amendment.json"
DEFAULT_MARKDOWN_REPORT = REPO_ROOT / "benchmarks" / "reports" / "cpp-formal-timeout-canary-amendment.md"


def _load_marker(evidence_dir: Path, *, manifest_sha256: str) -> dict[str, Any]:
    path = evidence_dir / "provider-canaries" / "formal-v4-provider-canary-attempt.json"
    try:
        marker = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError("缺少有效的 timeout canary amendment marker") from exc
    if marker.get("benchmark_id") != "forge-cpp-formal-timeout-canary-amendment":
        raise ReportError("timeout canary amendment identity 不匹配")
    if marker.get("manifest_sha256") != manifest_sha256 or marker.get("status") != "passed":
        raise ReportError("timeout canary amendment 未成功")
    return {"status": marker["status"], "updated_at": marker.get("updated_at"), "error_class": marker.get("error_class")}


def build_report(manifest: dict[str, Any], evidence_dir: Path, **kwargs: Any) -> dict[str, Any]:
    original_protocol = parent_report.protocol
    original_runner = parent_report.runner
    original_loader = parent_report._load_canary_attempt_marker
    parent_report.protocol = protocol
    parent_report.runner = runner
    parent_report._load_canary_attempt_marker = _load_marker
    try:
        report = parent_report.build_report(manifest, evidence_dir, **kwargs)
    finally:
        parent_report.protocol = original_protocol
        parent_report.runner = original_runner
        parent_report._load_canary_attempt_marker = original_loader
    report["report_version"] = "formal-timeout-canary-amendment-report-1.0.0"
    report["interpretation"]["anonymous_models_endpoint_preflight"] = "forbidden"
    report["limitations"].append("旧 canary 失败与本修订层分开保留，不能合并解释为一次成功重试。")
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_REPORT)
    args = parser.parse_args(argv)
    try:
        manifest = protocol.validate_manifest(protocol.load_json_document(args.manifest))
        report = build_report(manifest, args.evidence_dir)
        parent_report.write_reports(report, json_path=args.json_output, markdown_path=args.markdown_output)
    except (ReportError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report["collection"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
