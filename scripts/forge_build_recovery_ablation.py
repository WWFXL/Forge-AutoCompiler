#!/usr/bin/env python3
"""相同工具初始方案，比较首次失败停止与状态触发Agent恢复。"""

from __future__ import annotations

import signal
from pathlib import Path
from unittest.mock import patch

import forge_build_strategy_replication as replication

base, bounded = replication.base, replication.bounded
IDENTITY = "cpp-build-tool-recovery-ablation-v1"
PROJECTS = ("snappy", "simdutf", "yaml-cpp", "libtommath", "tinyxml2")
ARMS = ("no_recovery", "failure_agent_recovery")
ORIGINAL_FACTORY = base.observed_module.observed_planner


def schedule():
    return [dict(project=name, method=arm, repetition=1)
            for i, name in enumerate(PROJECTS)
            for arm in (ARMS if i % 2 == 0 else ARMS[::-1])]


def planner_factory(recovery_enabled):
    def factory(source, **kwargs):
        if source != "tool":
            raise base.PlanContractError("消融必须使用同一工具初始方案")

        def forbidden_agent(**agent_kwargs):
            agent_kwargs["meter"].ledger.append("ablation.agent_forbidden", phase="initial_abstention")
            raise base.PlanContractError("消融工具初始拒答；不得改成初始Agent规划")

        def recovery_only_agent(**agent_kwargs):
            if agent_kwargs.get("current_plan") is None:
                return forbidden_agent(**agent_kwargs)
            return base.observed_module.propose_observed(**agent_kwargs)

        kwargs["agent"] = recovery_only_agent if recovery_enabled else forbidden_agent
        original = ORIGINAL_FACTORY(source, **kwargs)

        def planner(**planner_kwargs):
            if not recovery_enabled and planner_kwargs.get("current_plan") is not None:
                planner_kwargs["meter"].ledger.append("ablation.recovery_disabled", failed_step=planner_kwargs.get("handoff", {}).get("step_id"), current_plan_sha256=planner_kwargs["current_plan"].fingerprint())
                raise base.PlanContractError("ablation_stop_on_first_failure：不调用Agent，保留首次失败和未观察后缀")
            return original(**planner_kwargs)

        return planner

    return factory


def run_slot(*, protocol, slot, root, model):
    enabled = slot["method"] == ARMS[1]
    internal_slot = {**slot, "method": base.METHODS[0]}
    with patch.object(base.observed_module, "observed_planner", planner_factory(enabled)):
        row = replication.run_slot(protocol=protocol, slot=internal_slot, root=root, model=model)
    return {**row, **slot, "ablation_recovery_enabled": enabled}


def validate(candidate):
    if candidate["identity"] != IDENTITY or candidate["schedule"] != schedule():
        raise base.PlanContractError("恢复消融身份或前瞻调度变化")
    if candidate["provider"] != base.PROVIDER or candidate["runtime"] != base.RUNTIME:
        raise base.PlanContractError("共同模型或资源变化")
    if candidate["dependency_runtime"] != bounded.previous.DEPENDENCY_RUNTIME or candidate["host_ownership_mode"] != "original_generic_unconfigured":
        raise base.PlanContractError("原依赖权限或宿主模式变化")
    if candidate["stage_max_cost_usd"] != "5.00" or candidate["holdout"] is not False:
        raise base.PlanContractError("消融阶段预算或已见角色变化")
    parent_path = base.ROOT / "benchmarks/manifests/cpp-build-strategy-replication-v1.json"
    if base.digest(parent_path) != candidate["parent_manifest_sha256"]:
        raise base.PlanContractError("原任务清单变化")
    parent = {p["name"]: p for p in base.load(parent_path)["projects"]}
    if candidate["projects"] != [parent[name] for name in PROJECTS]:
        raise base.PlanContractError("原任务/全部测试/交付改变")
    for item in candidate["projects"]:
        if base.digest(Path(item["source_archive"])) != item["task"]["source_archive_sha256"]:
            raise base.PlanContractError("原源码变化")
        if candidate["source_index_contracts"][item["name"]] != replication.indexed.archive_index_contract(item["source_archive"]):
            raise base.PlanContractError("完整源码索引变化")
    for name, expected in candidate["components"].items():
        if base.digest(base.ROOT / name) != expected:
            raise base.PlanContractError("冻结组件变化：" + name)


def main():
    signal.signal(signal.SIGINT, bounded.request_stop)
    with (patch.object(base, "validate", validate),
          patch.object(base, "execution_window", bounded.execution_window),
          patch.object(base, "PreparationMeter", bounded.previous.QualifiedPreparationMeter),
          patch.object(base, "execute", bounded.execute),
          patch.object(base, "run_slot", run_slot)):
        return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
