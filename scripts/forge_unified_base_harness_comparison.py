#!/usr/bin/env python3
"""统一修复基座上的18项目Harness比较；复用执行器，不续用旧身份。"""

from __future__ import annotations

from forge_harness_update_remeasurement import runner as previous_runner

IDENTITY = "cpp-build-unified-base-harness-comparison-flash-v1"


def runner():
    module = previous_runner()
    module.IDENTITY = IDENTITY
    module.MANIFEST = module.ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
    module.PREREG = module.ROOT / "benchmarks/preregistrations" / (IDENTITY + ".md")
    previous_candidate = module.candidate

    def candidate():
        value = previous_candidate()
        value.update(
            issue=826,
            previous_experiment="cpp-build-harness-update-repaired-comparison-flash-v1",
            evaluation_type="same_18_projects_complete_comparison_on_unified_repaired_base",
            common_repair="pr816_source_inventory_and_pr822_tool_error_feedback_structured_redelivery",
            reference_corrections=["smenu", "quickjs", "zstd"],
            historical_exposure="沿用E58/E59的18项目，部分已用于失败诊断及三项目观察；不计新增独立样本或未见评价",
        )
        return value

    module.candidate = candidate
    return module


if __name__ == "__main__":
    runner().main()
