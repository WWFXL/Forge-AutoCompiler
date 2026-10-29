#!/usr/bin/env python3
"""在前瞻固定的新项目上复用已有三系统比较；免费准备不读取模型凭据。"""

from __future__ import annotations

import argparse
import copy
import json
import signal
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import forge_build_system_comparison as system

base, ROOT = system.base, system.ROOT
IDENTITY = "cpp-build-new-project-system-comparison-flash-v1"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
TASKS = ROOT / "benchmarks/fixtures/new-project-comparison-v1/tasks.json"
SELECTION = ROOT / "benchmarks/fixtures/new-project-comparison-v1/selection.json"
PREREGISTRATION = "benchmarks/preregistrations/" + IDENTITY + ".md"
PARENT = system.MANIFEST.relative_to(ROOT).as_posix()


def candidate_for():
    """只替换样本与实验身份；模型、方法、Harness、资源和裁判复用E30。"""
    candidate = copy.deepcopy(base.load(system.MANIFEST))
    tasks, selection = base.load(TASKS), base.load(SELECTION)
    names = [item["name"] for item in tasks["projects"]]
    scheduled_names = [row["name"] for row in selection["projects"] if row["role"] == "prospective_new_method_evaluation"]
    if len(names) != 7 or names != scheduled_names or len(set(names)) != 7:
        raise base.PlanContractError("本批必须保持七项主比较；原生条件跳过项目只作参考")
    candidate.update(
        identity=IDENTITY,
        issue=646,
        kind="complete_system_comparison_new_method_projects",
        projects=tasks["projects"],
        source_index_contracts=tasks["source_index_contracts"],
        exposure=selection,
        holdout=False,
        schedule=[dict(project=name, repetition=repetition, method=system.METHODS[index]) for repetition in (1, 2) for position, name in enumerate(names) for index in base.ORDERS[(position + 3 * (repetition - 1)) % 6]],
        parent_manifests=[dict(path=PARENT, sha256=base.digest(system.MANIFEST))],
        launch_state="prepared_requires_new_budget_and_time_authorization",
        comparison_boundary="新于当前方法调试的固定项目；源与任务准备已暴露，有限Git检索不证明全历史或训练未见；非纯状态因果。CXX社区版保留原生工具、反馈与CPU约束差异。",
    )
    # 旧样本的资格/暴露说明不继承为新样本的事实；旧组件仍全部冻结。
    for key in ("prior_qualification", "prior_development_exposure", "prior_development_exposure_v2", "prior_replication_exposure"):
        candidate.pop(key, None)
    for path in (TASKS.relative_to(ROOT).as_posix(), SELECTION.relative_to(ROOT).as_posix(), PREREGISTRATION, "scripts/forge_build_new_project_comparison.py"):
        candidate["components"][path] = base.digest(ROOT / path)
    return candidate


def validate(candidate):
    if candidate != candidate_for():
        raise base.PlanContractError("新项目、固定任务、顺序或比较条件变化")
    for path, expected in candidate["components"].items():
        if base.digest(ROOT / path) != expected:
            raise base.PlanContractError("冻结组件变化：" + path)
    for item in candidate["projects"]:
        if base.digest(Path(item["source_archive"])) != item["task"]["source_archive_sha256"]:
            raise base.PlanContractError("新项目源码归档变化：" + item["name"])
        if system.replication.indexed.archive_index_contract(item["source_archive"]) != candidate["source_index_contracts"][item["name"]]:
            raise base.PlanContractError("新项目原源码索引变化：" + item["name"])
        base.PlanTask.model_validate(item["task"])
    for name, expected in candidate["baseline"]["files"].items():
        if base.digest(Path(candidate["baseline"]["path"]) / name) != expected:
            raise base.PlanContractError("CXX社区快照变化")


def analyze(root):
    """沿原分析口径，分母按本批冻结调度计算，不继承E30的16槽。"""
    result = system.analyze(root)
    protocol = base.load(root / "protocol.json")
    planned = Counter(row["method"] for row in protocol["schedule"])
    for method, summary in result["summary"].items():
        summary["planned"] = planned[method]
        summary["unobserved"] = planned[method] - summary["observed"]
    result["boundary"] = "固定42槽；失败、截断和未观察分开，原生跳过的libxcrypt参考不进入效果分母；共同完成配对仅辅助，非纯状态因果。"
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
                raise base.PlanContractError("不覆盖已固定新项目候选")
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
