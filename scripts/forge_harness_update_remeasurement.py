#!/usr/bin/env python3
"""共同修复后原18项目重新测量；复用既有调度且不改旧实验身份。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from forge_typed_evidence import digest

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "cpp-build-harness-update-repaired-comparison-flash-v1"
DIRECTORY = ROOT / "benchmarks/fixtures/harness-update-repaired-comparison-v1"


def runner():
    # 独立加载入口命名空间，避免改写旧模块的全局变量或冻结manifest。
    source = ROOT / "scripts/forge_harness_update_comparison.py"
    spec = importlib.util.spec_from_file_location(
        "_forge_harness_remeasurement", source
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.IDENTITY = IDENTITY
    module.DIRECTORY = DIRECTORY
    module.FIXTURE = DIRECTORY / "tasks.json"
    module.MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
    module.PREREG = ROOT / "benchmarks/preregistrations" / (IDENTITY + ".md")
    previous_candidate = module.candidate

    def candidate():
        value = previous_candidate()
        value.update(
            issue=817,
            previous_experiment="cpp-build-harness-update-comparison-flash-v1",
            evaluation_type="same_18_projects_remeasurement_after_common_repair",
            common_repair="source_inventory_execution_side_sha_checked_reset_and_repro_path_boundary",
            reference_corrections=["smenu", "quickjs", "zstd"],
            known_solution_injection=False,
        )
        path = (
            ROOT
            / "benchmarks/analyses/e58-failure-repair-2026-11-17/corrected-references.json"
        )
        value["components"][path.relative_to(ROOT).as_posix()] = digest(path)
        return value

    module.candidate = candidate
    return module


if __name__ == "__main__":
    runner().main()
