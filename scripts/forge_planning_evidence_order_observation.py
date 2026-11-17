#!/usr/bin/env python3
"""已审核P5的三构建系统观察；复用LH_v1执行入口，准备不读取模型凭据。"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from forge_harness_update_remeasurement import runner
from forge_typed_evidence import digest, seal

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "cpp-build-planning-evidence-order-observation-flash-v1"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREG = ROOT / "benchmarks/preregistrations" / (IDENTITY + ".md")
P5 = ROOT / "benchmarks/fixtures/planning-evidence-order-v1/candidate.json"
P5_SHA = "568429c41480d2208cc9bbfb14b0a1a173331d0e9874629fc550793a017f98b4"
PROJECTS = ("libuv", "quickjs", "libunwind")
METHOD = "LH_v1"


def planning_harness():
    module = runner()
    value = module.PlanningHarness.model_validate(module.shared.load(P5))
    if value.fingerprint() != P5_SHA:
        raise module.PlanContractError("用户已审核P5发生变化")
    value.prompt(module.SIMPLE_PROMPT)
    return value


def runtime():
    module = runner()
    module.IDENTITY, module.PREREG = IDENTITY, PREREG
    original_executor = module.executor
    module.executor = lambda model: original_executor(model, planning_harness=planning_harness())
    return module


def candidate():
    module = runtime()
    value = module.candidate()
    by_name = {p["name"]: p for p in value["projects"]}
    value.update(
        issue=830,
        projects=[by_name[name] for name in PROJECTS],
        methods=[METHOD],
        schedule=[dict(slot=i + 1, project=name, repetition=1, method=METHOD) for i, name in enumerate(PROJECTS)],
        maximum_cost_usd="2.00",
        maximum_hours=2,
        planning_harness=planning_harness().model_dump(mode="json"),
        arm_options={METHOD: module.policy(METHOD)},
        recovery_harnesses={METHOD: module.harnesses()[METHOD].model_dump(mode="json")},
        evaluation_type="known_project_planning_process_observation_not_effect_comparison",
        previous_experiment="cpp-build-unified-base-harness-comparison-flash-v1",
        intervention_scope="仅P0改为用户审核的P5；其余保持当前LH_v1",
        reporting="all_three_projects_and_initial_planning_trajectories",
        historical_exposure="三个项目均已观察；仅作读取顺序、依赖查询、收敛和方案执行的描述性观察，不增独立样本",
        reference_corrections=[],
    )
    for path in (P5, Path(__file__)):
        value["components"][path.relative_to(ROOT).as_posix()] = digest(path)
    return value


def validate(value, *, check_sources=True):
    module = runtime()
    if value != candidate():
        raise module.PlanContractError("P5观察协议或组件发生变化，不得续用旧身份")
    for project in value["projects"]:
        task = module.PublicBuildTask.model_validate(project["task"])
        ref = module.BuildReference.model_validate(project["reference"])
        ref.require_main_build_verification()
        if task.image_id != module.IMAGE or ref.task_sha256 != module._digest(task.model_dump(mode="json")):
            raise module.PlanContractError("任务/镜像/参考变化")
        if check_sources and digest(Path(project["source_archive"])) != task.source_archive_sha256:
            raise module.PlanContractError("源码归档变化：" + project["name"])


def analyze(root):
    value = runtime().analyze(root)
    arm = value["arms"][METHOD]
    arm.update(planned=len(PROJECTS), unobserved=len(PROJECTS) - arm["observed"])
    value["arms"] = {METHOD: arm}
    value["planning_harness"] = planning_harness().name
    value["boundary"] = "三个已知项目的P5流程观察，不证明P5优于P0；真实规划行为需结合完整请求/工具轨迹分析。"
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
            raise module.PlanContractError("不覆盖既有观察协议")
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
