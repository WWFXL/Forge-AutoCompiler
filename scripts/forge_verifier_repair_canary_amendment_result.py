#!/usr/bin/env python3
"""从冻结的 verifier-driven repair amendment evidence 生成只读结果报告。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_verifier_repair_canary_amendment_protocol as protocol  # noqa: E402
import forge_verifier_repair_canary_amendment_report as frozen_report  # noqa: E402

RESULT_VERSION = "verifier-driven-repair-pilot-canary-amendment-result-1.0.0"
DEFAULT_EVIDENCE_DIR = Path(protocol.EVIDENCE_DIRECTORY)
DEFAULT_JSON_REPORT = DEFAULT_EVIDENCE_DIR / "verifier-repair-pilot-result.json"
DEFAULT_MARKDOWN_REPORT = DEFAULT_EVIDENCE_DIR / "verifier-repair-pilot-result.md"
ResultError = frozen_report._parent.ReportError


def build_report(manifest: dict[str, Any], evidence_dir: Path) -> dict[str, Any]:
    parent_report = frozen_report._parent
    original_load_json = parent_report.parent_protocol._load_json

    def load_runtime_parent(path: Path) -> dict[str, Any]:
        if path == protocol.DEFAULT_PARENT_MANIFEST:
            path = parent_report.parent_protocol.DEFAULT_MANIFEST
        return original_load_json(path)

    parent_report.parent_protocol._load_json = load_runtime_parent
    try:
        report = parent_report.build_report(manifest, evidence_dir)
    finally:
        parent_report.parent_protocol._load_json = original_load_json
    report["result_adapter_version"] = RESULT_VERSION
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=protocol.DEFAULT_MANIFEST)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_REPORT)
    args = parser.parse_args(argv)
    try:
        manifest = protocol.validate_manifest(protocol._load_json(args.manifest))
        report = build_report(manifest, args.evidence_dir)
        frozen_report._parent.write_reports(
            report,
            json_path=args.json_output,
            markdown_path=args.markdown_output,
        )
    except (
        OSError,
        ValueError,
        ResultError,
        frozen_report._parent.analyzer.AnalyzerError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "complete_pairs": report["collection"]["complete_pairs"],
                "json_report": str(args.json_output),
                "markdown_report": str(args.markdown_output),
                "observed_slots": report["collection"]["observed_slots"],
                "status": "written",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
