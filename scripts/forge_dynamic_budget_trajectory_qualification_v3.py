#!/usr/bin/env python3
"""Issue #423 动态预算轨迹 v3：绑定确定性 continuation hostname。"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
V2_SCRIPT_PATH = SCRIPT_PATH.with_name(
    "forge_dynamic_budget_trajectory_qualification_v2.py"
)
IDENTITY = "cpp-dynamic-budget-trajectory-benchmark-qualification-v3"


def _load_v2() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "forge_dynamic_budget_trajectory_qualification_v2", V2_SCRIPT_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load v2 qualification runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configure_module() -> ModuleType:
    module = _load_v2().configure_module()
    module.IDENTITY = IDENTITY
    module.MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests" / f"{IDENTITY}.json"
    module.REPORT_JSON_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.json"
    module.REPORT_MD_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.md"
    module.DETERMINISTIC_HOSTNAME = True
    return module


def main() -> int:
    return configure_module().main()


if __name__ == "__main__":
    raise SystemExit(main())
