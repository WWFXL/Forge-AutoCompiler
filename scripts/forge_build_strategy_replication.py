#!/usr/bin/env python3
"""已见六项目三策略的独立重复比较，统一核对原归档源码索引。"""

from __future__ import annotations

import signal
from pathlib import Path
from unittest.mock import patch

import forge_build_check_source_index_probe as indexed

bounded = indexed.bounded
base = indexed.base
IDENTITY = "cpp-build-strategy-replication-v1"
PARENT = Path("benchmarks/manifests/cpp-build-test-preparation-comparison-v3.json")
# 长任务先进入每轮，避免固定窗口只覆盖短项目。顺序在新结果前冻结。
PROJECTS = ("check", "simdutf", "snappy", "yaml-cpp", "libtommath", "tinyxml2")


def schedule():
    return [
        dict(project=name, method=base.METHODS[index], repetition=repetition)
        for repetition in (1, 2)
        for position, name in enumerate(PROJECTS)
        for index in base.ORDERS[(position + 3 * (repetition - 1)) % 6]
    ]


def validate(candidate):
    if candidate["identity"] != IDENTITY or candidate["schedule"] != schedule():
        raise base.PlanContractError("独立重复身份或前瞻调度变化")
    if candidate["provider"] != base.PROVIDER or candidate["runtime"] != base.RUNTIME:
        raise base.PlanContractError("原模型或共同资源变化")
    if (
        candidate["dependency_runtime"] != bounded.previous.DEPENDENCY_RUNTIME
        or candidate["host_ownership_mode"] != "original_generic_unconfigured"
    ):
        raise base.PlanContractError("原依赖权限或宿主模式变化")
    if candidate["stage_max_cost_usd"] != "18.00" or candidate["holdout"] is not False:
        raise base.PlanContractError("新阶段预算或已见角色变化")
    for name, expected in candidate["components"].items():
        if base.digest(base.ROOT / name) != expected:
            raise base.PlanContractError("冻结组件变化：" + name)
    parent = {p["name"]: p for p in base.load(base.ROOT / PARENT)["projects"]}
    if candidate["projects"] != [parent[name] for name in PROJECTS]:
        raise base.PlanContractError("不得改变原六项目任务/源码/测试/交付")
    if set(candidate["source_index_contracts"]) != set(PROJECTS):
        raise base.PlanContractError("缺少项目源码索引")
    for item in candidate["projects"]:
        if (
            base.digest(Path(item["source_archive"]))
            != item["task"]["source_archive_sha256"]
        ):
            raise base.PlanContractError("原源码归档变化")
        if candidate["source_index_contracts"][
            item["name"]
        ] != indexed.archive_index_contract(item["source_archive"]):
            raise base.PlanContractError("原文件或链接索引变化")
        if item["common_test_preparation"] != base.preparation_obligation(item):
            raise base.PlanContractError("共同原源码测试说明变化")
        base.PlanTask.model_validate(item["task"])
    if any(k in candidate for k in ("reference", "recovery_actions")):
        raise base.PlanContractError("真实比较不得注入人工正确方案")


def run_slot(*, protocol, slot, root, model):
    # 复用已通过真实check验证的适配；每个项目只使用自己的原归档索引。
    selected = {
        **protocol,
        "source_index_contract": protocol["source_index_contracts"][slot["project"]],
    }
    return indexed.run_slot(protocol=selected, slot=slot, root=root, model=model)


def main():
    signal.signal(signal.SIGINT, bounded.request_stop)
    with (
        patch.object(base, "validate", validate),
        patch.object(base, "execution_window", bounded.execution_window),
        patch.object(
            base, "PreparationMeter", bounded.previous.QualifiedPreparationMeter
        ),
        patch.object(base, "execute", bounded.execute),
        patch.object(base, "run_slot", run_slot),
    ):
        return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
