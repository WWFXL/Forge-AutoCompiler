#!/usr/bin/env python3
"""生成 verifier-driven repair canary 修订的确定性配对报告。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_verifier_repair_canary_amendment_protocol as protocol  # noqa: E402


def _load_parent_report():
    module_name = f"{__name__}_parent"
    spec = importlib.util.spec_from_file_location(
        module_name,
        SCRIPT_ROOT / "forge_verifier_repair_authorized_report.py",
    )
    if spec is None or spec.loader is None:
        raise ImportError("Unable to load the authorized verifier-repair report")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_parent = _load_parent_report()
_parent.protocol = protocol
_parent.REPORT_VERSION = "verifier-driven-repair-pilot-canary-amendment-report-1.0.0"
_parent.DEFAULT_EVIDENCE_DIR = Path(protocol.EVIDENCE_DIRECTORY)
_parent.DEFAULT_JSON_REPORT = _parent.DEFAULT_EVIDENCE_DIR / "verifier-repair-pilot-report.json"
_parent.DEFAULT_MARKDOWN_REPORT = _parent.DEFAULT_EVIDENCE_DIR / "verifier-repair-pilot-report.md"


def main(argv: list[str] | None = None) -> int:
    return _parent.main(argv)


def __getattr__(name: str):
    return getattr(_parent, name)


if __name__ == "__main__":
    raise SystemExit(main())
