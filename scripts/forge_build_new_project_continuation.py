#!/usr/bin/env python3
"""独立执行原新项目比较从未启动的24槽，不续跑旧身份或重试中断。"""

from __future__ import annotations

import argparse
import copy
import json
import signal
import sys
from pathlib import Path
from unittest.mock import patch

import forge_build_new_project_comparison as parent

base, system, ROOT = parent.base, parent.system, parent.ROOT
IDENTITY = "cpp-build-new-project-system-continuation-flash-v1"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREGISTRATION = "benchmarks/preregistrations/" + IDENTITY + ".md"
INTERRUPTION = "benchmarks/analyses/cpp-build-new-project-system-comparison-flash-v1-interruption.json"


def candidate_for():
    """只取已登记的未启动后缀；所有任务和方法组件逐字继承。"""
    original = base.load(parent.MANIFEST)
    closure = base.load(ROOT / INTERRUPTION)
    schedule = original["schedule"][18:]
    if closure["identity"] != parent.IDENTITY or closure["unobserved_schedule"] != schedule or len(schedule) != 24:
        raise base.PlanContractError("续段必须仅包含原19–42未启动槽")
    candidate = copy.deepcopy(original)
    candidate.update(
        identity=IDENTITY,
        issue=650,
        kind="complete_system_comparison_unstarted_continuation",
        schedule=schedule,
        parent_manifests=[*original["parent_manifests"], dict(path=parent.MANIFEST.relative_to(ROOT).as_posix(), sha256=base.digest(parent.MANIFEST))],
        continuation=dict(
            parent_identity=parent.IDENTITY,
            parent_raw="/home/yiwei/.codex/outputs/forge-new-project-system-comparison-flash-v1",
            parent_inventory=closure["raw_inventory"],
            interruption_path=INTERRUPTION,
            interruption_sha256=base.digest(ROOT / INTERRUPTION),
            slot_mapping=[dict(slot=index, parent_slot=index + 18, **row) for index, row in enumerate(schedule, 1)],
            excluded_parent_slots=list(range(1, 19)),
            parent_results_visible=True,
            boundary="旧17终态与第18槽中断保留；本批只观察原24个未启动槽。跨身份仅描述性组合，不回填原42槽。",
        ),
    )
    for name in (PREREGISTRATION, INTERRUPTION, "scripts/forge_build_new_project_continuation.py"):
        candidate["components"][name] = base.digest(ROOT / name)
    return candidate


def validate(candidate):
    if candidate != candidate_for():
        raise base.PlanContractError("续段身份、原槽映射或比较条件变化")
    parent.validate(base.load(parent.MANIFEST))
    for name, expected in candidate["components"].items():
        if base.digest(ROOT / name) != expected:
            raise base.PlanContractError("冻结组件变化：" + name)


def analyze(root):
    """复用动态调度分母；旧结果不混进本批方法汇总。"""
    result = parent.analyze(root)
    result["boundary"] = "独立24槽、每方法8槽；保留失败与未观察。旧17终态和1中断不计入本批；跨身份仅描述性组合。"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--check-prepared", action="store_true")
    parser.add_argument("--analyze", type=Path)
    args, remaining = parser.parse_known_args()
    if args.prepare or args.check_prepared:
        candidate = candidate_for() if args.prepare else base.load(MANIFEST)
        validate(candidate)
        if args.prepare:
            if MANIFEST.exists():
                raise base.PlanContractError("不覆盖已固定续段候选")
            base.write_json(MANIFEST, candidate)
        print(json.dumps(dict(valid=True, slots=len(candidate["schedule"]), credentials_read=False, provider_calls=0)))
        return 0
    if args.analyze:
        print(json.dumps(analyze(args.analyze), ensure_ascii=False, indent=2))
        return 0
    signal.signal(signal.SIGINT, system.component.bounded.request_stop)
    with patch.object(sys, "argv", [sys.argv[0], *remaining]), patch.object(base, "PROVIDER", system.flash.PROVIDER), patch.object(base, "validate", validate), patch.object(base, "execute", system.execute):
        return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
