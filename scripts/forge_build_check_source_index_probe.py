#!/usr/bin/env python3
"""独立Autotools开发验证；原任务不改，完整计入原归档符号链接。"""

from __future__ import annotations

import signal
import time
from pathlib import Path
from unittest.mock import patch

import forge_build_test_preparation_comparison_v3 as bounded

from deerflow.compile.archive_source_index import archive_index_contract, complete_index_fingerprint, observe_original_links

base = bounded.base
IDENTITY = "cpp-build-check-source-index-probe-v1"
PARENT = Path("benchmarks/manifests/cpp-build-test-preparation-comparison-v3.json")
ORDER = ("strong_tool_agent", "tool_plan_workflow", "model_plan_workflow")
ORIGINAL_RUN_SLOT = base.run_slot


def validate(candidate):
    if candidate["identity"] != IDENTITY or candidate["schedule"] != [dict(project="check", method=m, repetition=1) for m in ORDER]:
        raise base.PlanContractError("独立开发身份或三槽顺序变化")
    if candidate["provider"] != base.PROVIDER or candidate["runtime"] != base.RUNTIME or candidate["dependency_runtime"] != bounded.previous.DEPENDENCY_RUNTIME or candidate["host_ownership_mode"] != "original_generic_unconfigured":
        raise base.PlanContractError("原模型/资源/依赖权限/宿主模式变化")
    for name, expected in candidate["components"].items():
        if base.digest(base.ROOT / name) != expected:
            raise base.PlanContractError("冻结组件变化：" + name)
    parent = next(p for p in base.load(base.ROOT / PARENT)["projects"] if p["name"] == "check")
    if candidate["projects"] != [parent]:
        raise base.PlanContractError("不得改变原check源码/任务/完整测试/交付")
    if base.digest(Path(parent["source_archive"])) != parent["task"]["source_archive_sha256"] or candidate["source_index_contract"] != archive_index_contract(parent["source_archive"]):
        raise base.PlanContractError("原源码归档或完整索引变化")
    base.PlanTask.model_validate(parent["task"])


def run_slot(*, protocol, slot, root, model):
    started = time.monotonic()
    contract = protocol["source_index_contract"]
    base.write_json(root / "source-index-contract.json", contract)
    with patch.object(base.prepared_module, "paths_fingerprint", lambda paths: complete_index_fingerprint(paths, contract)):
        row = ORIGINAL_RUN_SLOT(protocol=protocol, slot=slot, root=root, model=model)
    sessions = list(root.glob("*/.compile-sessions/*/*/session.json"))
    if len(sessions) != 1:
        raise base.PlanContractError("缺少唯一源码链接核验Session")
    state = base.load(sessions[0])
    observations = {"original": observe_original_links(state["leadagent_repo_dir"], contract)}
    for attempt in state.get("replay_attempts", []):
        workspace = sessions[0].parent / "replay" / attempt["attempt_id"] / "workspace/repo"
        observations[attempt["attempt_id"]] = observe_original_links(workspace, contract)
    unchanged = all(link["passed"] for tree in observations.values() for link in tree.values())
    base.write_json(root / "source-links-observation.json", observations)
    return {**row, "source_links_unchanged": unchanged, "strict_completed": row["strict_completed"] and unchanged, "arm_total_wall_seconds": time.monotonic() - started}


def main():
    signal.signal(signal.SIGINT, bounded.request_stop)
    with (
        patch.object(base, "validate", validate),
        patch.object(base, "execution_window", bounded.execution_window),
        patch.object(base, "PreparationMeter", bounded.previous.QualifiedPreparationMeter),
        patch.object(base, "execute", bounded.execute),
        patch.object(base, "run_slot", run_slot),
    ):
        return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
