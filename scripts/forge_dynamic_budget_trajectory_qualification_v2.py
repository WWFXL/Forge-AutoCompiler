#!/usr/bin/env python3
"""Issue #423 动态预算轨迹 v2：忽略已冻结的构建工具诊断噪声。"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
V1_SCRIPT_PATH = SCRIPT_PATH.with_name(
    "forge_dynamic_budget_trajectory_qualification.py"
)
IDENTITY = "cpp-dynamic-budget-trajectory-benchmark-qualification-v2"
IGNORED_DIAGNOSTIC_NAMES = frozenset(
    {"CMakeConfigureLog.yaml", "CMakeOutput.log", "CMakeError.log", "config.log"}
)


def _load_v1() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "forge_dynamic_budget_trajectory_qualification_v1", V1_SCRIPT_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load v1 qualification runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def decision_relevant_entries(module: ModuleType, root: Path) -> list[dict[str, Any]]:
    ignored_directories = getattr(
        module, "IGNORED_DECISION_TREE_DIR_NAMES", frozenset()
    )
    return [
        entry
        for entry in module._tree_entries_unfiltered(root)
        if Path(entry["path"]).name not in IGNORED_DIAGNOSTIC_NAMES
        and not any(part in ignored_directories for part in Path(entry["path"]).parts)
    ]


def configure_module() -> ModuleType:
    module = _load_v1()
    module.IDENTITY = IDENTITY
    module.MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests" / f"{IDENTITY}.json"
    module.REPORT_JSON_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.json"
    module.REPORT_MD_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.md"
    module._tree_entries_unfiltered = module._tree_entries
    module._tree_entries = lambda root: decision_relevant_entries(module, root)
    return module


def main() -> int:
    return configure_module().main()


if __name__ == "__main__":
    raise SystemExit(main())
