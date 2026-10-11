#!/usr/bin/env python3
"""执行修复 Autotools 功能 oracle 后的混合链路零 Provider 资格 v3。"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_jev_hybrid_workflow_qualification_v2 as v2  # noqa: E402

IDENTITY = "cpp-jev-hybrid-workflow-qualification-v3"
v2.v1.IDENTITY = IDENTITY
v2.v1.MANIFEST_PATH = v2.v1.REPO_ROOT / "benchmarks" / "manifests" / f"{IDENTITY}.json"
v2.v1.REPORT_JSON_PATH = v2.v1.REPO_ROOT / "benchmarks" / "reports" / f"{IDENTITY}.json"
v2.v1.REPORT_MARKDOWN_PATH = v2.v1.REPO_ROOT / "benchmarks" / "reports" / f"{IDENTITY}.md"
v2.v1.FAILURE_JSON_PATH = v2.v1.REPO_ROOT / "benchmarks" / "reports" / f"{IDENTITY}-failure.json"
v2.v1.FAILURE_MARKDOWN_PATH = v2.v1.REPO_ROOT / "benchmarks" / "reports" / f"{IDENTITY}-failure.md"


if __name__ == "__main__":
    raise SystemExit(v2.v1.main())
