#!/usr/bin/env python3
"""修复后LH_v1对三个未完成项目的独立观察；默认不读取凭据。"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from forge_harness_update_remeasurement import runner
from forge_typed_evidence import digest, seal

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "cpp-build-failed-project-harness-observation-flash-v1"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREG = ROOT / "benchmarks/preregistrations" / (IDENTITY + ".md")
PROJECTS = ("dsvpn", "libass", "libtasn1")
METHOD = "LH_v1"


def runtime():
    module = runner()
    module.IDENTITY = IDENTITY
    module.PREREG = PREREG
    return module


def candidate():
    module = runtime()
    value = module.candidate()
    by_name = {p["name"]: p for p in value["projects"]}
    value.update(
        issue=823,
        projects=[by_name[name] for name in PROJECTS],
        methods=[METHOD],
        schedule=[dict(slot=i + 1, project=name, repetition=1, method=METHOD) for i, name in enumerate(PROJECTS)],
        maximum_cost_usd="2.00",
        maximum_hours=2,
        evaluation_type="post_repair_failed_project_observation_not_controlled_comparison",
        previous_experiment="cpp-build-harness-update-repaired-comparison-flash-v1",
        common_repair="pr822_tool_error_feedback_and_complete_structured_redelivery",
        reporting="all_three_projects_with_failures_and_unobserved_separate",
        reference_corrections=[],
        historical_exposure="三个已观察失败项目；libtasn1仅原基线失败，更新组曾成功；不可当未见样本或配对因果比较",
    )
    return value


def validate(value, *, check_sources=True):
    module = runtime()
    if value != candidate():
        raise module.PlanContractError("观察协议或运行组件变化，不得续用旧身份")
    for project in value["projects"]:
        task = module.PublicBuildTask.model_validate(project["task"])
        ref = module.BuildReference.model_validate(project["reference"])
        ref.require_main_build_verification()
        if task.image_id != module.IMAGE or ref.task_sha256 != module._digest(task.model_dump(mode="json")):
            raise module.PlanContractError("任务/镜像/独立参考变化")
        if check_sources and digest(Path(project["source_archive"])) != task.source_archive_sha256:
            raise module.PlanContractError("源码归档变化：" + project["name"])


def analyze(root):
    value = runtime().analyze(root)
    arm = value["arms"][METHOD]
    arm.update(planned=3, unobserved=3 - arm["observed"])
    value["arms"] = {METHOD: arm}
    value["boundary"] = "修复后已知失败项目的描述性观察；不回填E59，不作因果或总体成功率结论。"
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--check-prepared", action="store_true")
    group.add_argument("--run", action="store_true")
    group.add_argument("--analyze", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--authorization", type=Path)
    args = parser.parse_args()
    module = runtime()
    if args.analyze:
        print(json.dumps(analyze(args.analyze), ensure_ascii=False, indent=2))
        return
    if args.prepare:
        if MANIFEST.exists():
            raise module.PlanContractError("不覆盖已冻结观察协议")
        module.save(MANIFEST, candidate())
    value = module.shared.load(MANIFEST)
    validate(value)
    if not args.run:
        print(json.dumps(dict(identity=IDENTITY, manifest_sha256=digest(MANIFEST), projects=3, slots=3, provider_calls=0, credentials_read=False)))
        return
    if args.authorization is None or args.output is None or args.output.exists():
        raise module.PlanContractError("需要有效新授权和不存在的输出目录")
    auth = module.shared.load(args.authorization)
    module.shared.validate_authorization(auth, digest(MANIFEST), identity=IDENTITY, maximum_hours=2)
    if Decimal(str(auth["maximum_cost_usd"])) > Decimal("2.00"):
        raise module.PlanContractError("本轮费用硬上限2美元")
    module.shared.OperationWindow(auth["deadline_utc"]).admit("new_batch", 900)
    try:
        module.run_paid(value, args.output, auth)
    finally:
        if (args.output / "result.json").exists():
            result = module.shared.load(args.output / "result.json")
            module.save(args.output / "analysis.json", analyze(args.output))
            unknown = sum(module.shared.usage(r)["unknown"] for r in result["rows"]) + int(result["unclosed_slot"] is not None)
            seal(args.output, value, ROOT, unknown_usage_requests=unknown)


if __name__ == "__main__":
    main()
