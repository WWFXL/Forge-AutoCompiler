#!/usr/bin/env python3
"""局部恢复材料去重后的独立恢复子集比较，复用原工具和裁判。"""

from __future__ import annotations

import copy
from pathlib import Path
from unittest.mock import patch

import forge_build_local_recovery_comparison as previous

base, ROOT = previous.base, previous.ROOT
IDENTITY = "cpp-build-local-recovery-material-repair-flash-v1"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREGISTRATION = "benchmarks/preregistrations/" + IDENTITY + ".md"
PARENT = previous.MANIFEST.relative_to(ROOT).as_posix()


def candidate_for():
    parent = base.load(ROOT / PARENT)
    candidate = copy.deepcopy(parent)
    cases = [c for c in parent["cases"] if c["case_id"].endswith("-deviated")]
    candidate.update(
        identity=IDENTITY,
        kind="recovery_interface_comparison_after_duplicate_material_repair",
        parent_manifest=dict(path=PARENT, sha256=base.digest(ROOT / PARENT)),
        cases=cases,
        schedule=previous.schedule(cases),
        stage_max_cost_usd="5.00",
        launch_state="prepared_requires_scope_extension_within_existing_budget_and_deadline",
        interpretation_boundary="沿用原五方案中全部两份偏离方案，不按修复后效果选样；八槽为新运行，与原20槽分开报告，不替换失败。正常路径复用原观察及工程检查，不宣称新版本全系统效果。新材料仅移除共同权威包已有的重复方案/状态，工具反馈改为收据，完整命令输出和原始响应保留。",
        authorization_boundary="原20槽用户授权不自动扩展；新增8槽需确认范围，仍共享2026-11-02 12:30UTC起4小时/总10美元，不重置时窗或余额。原阶段结算后才允许启动。",
    )
    for path in (
        "backend/packages/harness/deerflow/compile/local_recovery.py",
        "scripts/forge_build_local_recovery_material_repair.py",
        PREREGISTRATION,
    ):
        candidate["components"][path] = base.digest(ROOT / path)
    return candidate


def validate(candidate):
    if candidate != candidate_for():
        raise base.PlanContractError("修复后恢复子集范围或材料变化")
    for path, expected in candidate["components"].items():
        if base.digest(ROOT / path) != expected:
            raise base.PlanContractError("冻结组件变化：" + path)
    for item in candidate["projects"]:
        if (
            base.digest(Path(item["source_archive"]))
            != item["task"]["source_archive_sha256"]
        ):
            raise base.PlanContractError("源码归档变化")
        for case in candidate["cases"]:
            if case["project"] == item["name"]:
                previous.fixed.checked_plan(
                    case, base.PlanTask.model_validate(item["task"])
                )


def main():
    with (
        patch.object(previous, "IDENTITY", IDENTITY),
        patch.object(previous, "MANIFEST", MANIFEST),
        patch.object(previous, "candidate_for", candidate_for),
        patch.object(previous, "validate", validate),
    ):
        return previous.main()


if __name__ == "__main__":
    raise SystemExit(main())
