#!/usr/bin/env python3
"""固定新库资格后的三策略比较；通用工具模板不注入参考配方。"""

from __future__ import annotations

import hashlib
import signal
import tarfile
from pathlib import Path
from unittest.mock import patch

import forge_build_strategy_replication as replication
from forge_typed_evidence import audit

base, bounded, indexed = replication.base, replication.bounded, replication.indexed
IDENTITY = "cpp-build-library-strategy-comparison-v1"
PROJECTS = ("rang", "ELFIO")


def schedule():
    return [dict(project=name, method=base.METHODS[i], repetition=r)
            for r in (1, 2) for p, name in enumerate(PROJECTS)
            for i in base.ORDERS[(p + 3 * (r - 1)) % 6]]


def common_obligation(item, dependencies):
    """只增原始文件和固定依赖资源清单，不携带参考指令。"""
    result = base.preparation_obligation(item)
    with tarfile.open(item["source_archive"]) as archive:
        for path in ("test/CMakeLists.txt", "tests/CMakeLists.txt", "cmake/Dependencies.cmake"):
            try:
                raw = archive.extractfile(path).read()
            except KeyError:
                continue
            result["author_build_declarations"].append(dict(path=path, sha256=hashlib.sha256(raw).hexdigest(), excerpt=raw.decode(errors="replace")[:6000], excerpt_is_partial=len(raw) > 6000))
    result["fixed_dependency_resources"] = dependencies
    result["dependency_resource_scope"] = "原作者依赖源码已固定于源码归档.forge-deps/目录；各策略相同，可自行读取构建说明。资源不是已安装包，不提供正确配置命令。"
    return result


def validate(candidate):
    if candidate["identity"] != IDENTITY or candidate["schedule"] != schedule():
        raise base.PlanContractError("新库身份或前瞻调度变化")
    if candidate["provider"] != base.PROVIDER or candidate["runtime"] != base.RUNTIME:
        raise base.PlanContractError("共同模型或资源变化")
    if candidate["dependency_runtime"] != bounded.previous.DEPENDENCY_RUNTIME or candidate["host_ownership_mode"] != "original_generic_unconfigured":
        raise base.PlanContractError("原依赖权限或宿主模式变化")
    if candidate["stage_max_cost_usd"] != "10.00" or candidate["holdout"] is not False:
        raise base.PlanContractError("共享阶段预算或暴露边界变化")
    if [p["name"] for p in candidate["projects"]] != list(PROJECTS):
        raise base.PlanContractError("资格项目不得替换")
    for record in candidate["qualification_evidence"]:
        root = Path(record["root"])
        if audit(root)["inventory_canonical_sha256"] != record["inventory_sha256"]:
            raise base.PlanContractError("参考原始证据变化")
        result = base.load(root / record["name"] / "result.json")
        if not result["qualified"]:
            raise base.PlanContractError("完整参考资格未通过")
        original = next(p for p in base.load(root / "protocol.json")["projects"] if p["name"] == record["name"])
        item = next(p for p in candidate["projects"] if p["name"] == record["name"])
        for key in ("task", "source_archive"):
            if original[key] != item[key]:
                raise base.PlanContractError("原任务或测试交付变化")
        if item["common_test_preparation"] != common_obligation(item, original["dependencies"]):
            raise base.PlanContractError("共同原始材料变化")
        contract = indexed.archive_index_contract(item["source_archive"])
        if candidate["source_index_contracts"][item["name"]] != contract:
            raise base.PlanContractError("完整源码索引变化")
        if base.digest(Path(item["source_archive"])) != item["task"]["source_archive_sha256"]:
            raise base.PlanContractError("固定输入归档变化")
        base.PlanTask.model_validate(item["task"])
    if any(k in candidate for k in ("reference", "recovery_actions")):
        raise base.PlanContractError("禁止注入正确方案")
    for name, expected in candidate["components"].items():
        if base.digest(base.ROOT / name) != expected:
            raise base.PlanContractError("冻结组件变化：" + name)


def main():
    signal.signal(signal.SIGINT, bounded.request_stop)
    with (patch.object(base, "validate", validate),
          patch.object(base, "execution_window", bounded.execution_window),
          patch.object(base, "PreparationMeter", bounded.previous.QualifiedPreparationMeter),
          patch.object(base, "execute", bounded.execute),
          patch.object(base, "run_slot", replication.run_slot)):
        return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
