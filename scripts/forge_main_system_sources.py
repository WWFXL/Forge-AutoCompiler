#!/usr/bin/env python3
"""冻结九个已有源码任务，并实际确认三份历史动作在新主构建范围的可用性；零Provider。"""

from __future__ import annotations

import argparse
from pathlib import Path

import forge_base_experience_comparison as historical
import forge_main_system_comparison as comparison
import forge_simple_comparison as shared
from forge_build_simple_task import save
from forge_simple_system import ScriptedSimpleModel, run_simple_system
from forge_typed_evidence import digest, seal

from deerflow.compile.simple_build_experience import SimpleProjectRecipe
from deerflow.compile.simple_build_task import (
    BuildReference,
    PublicBuildTask,
    SimpleBuildPlan,
)
from deerflow.compile.plan_workflow import _digest


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    save(
        output / "scope.json",
        dict(
            identity="cpp-build-main-system-recipe-confirmation-v1",
            issue=695,
            kind="zero_provider_recipe_scope_confirmation",
            provider_calls=0,
            maximum_cost_usd="0",
            authorization="本轮自主实现；仅重建既有成功动作，非新增方法效果",
            retry=False,
        ),
    )
    old = {}
    for fixture in (
        shared.FIXTURE,
        shared.ROOT / "benchmarks/fixtures/two-level-system-comparison-v1/tasks.json",
    ):
        old.update({p["name"]: p for p in shared.load(fixture)["projects"]})
    sources = historical.recipe_sources([old[n] for n in comparison.REUSE_PROJECTS])
    projects, recipes = [], {}
    for name in comparison.PROJECTS:
        original = old[name]
        task = PublicBuildTask.model_validate(
            original["task"] | dict(task_version="main-build-v1")
        )
        reference = BuildReference.model_validate(
            original["reference"]
            | dict(task_sha256=_digest(task.model_dump(mode="json")))
        )
        item = dict(
            name=name,
            family=original["family"],
            task=task.model_dump(mode="json"),
            reference=reference.model_dump(mode="json"),
            source_archive=original["source_archive"],
            stratum="exact_reuse" if name in comparison.REUSE_PROJECTS else "no_recipe",
            exposure="此前已开发、参考或方法暴露；非holdout，来源经验族隔离",
        )
        if name in sources:
            source = sources[name]
            old_recipe = SimpleProjectRecipe.model_validate(shared.load(source["path"]))
            assert old_recipe.task.model_dump(
                exclude={"task_version"}
            ) == task.model_dump(exclude={"task_version"})
            # 明确仅重绑定任务版本。实际执行、独立产物、交付、重放及源码检查均重新观察。
            plan = SimpleBuildPlan(task=task, steps=old_recipe.steps)
            folder = output / name
            result = run_simple_system(
                task=task,
                reference=reference,
                source_archive=Path(item["source_archive"]),
                output_root=folder,
                method="forge",
                model=ScriptedSimpleModel(responses=[], calls=[]),
                accepted_models=("zero-provider-script",),
                family=item["family"],
                initial_plan=plan.model_dump(mode="json"),
                validation_scope="main_build",
                replay_seconds=600,
            )
            save(
                folder / "historical-source.json",
                source
                | dict(
                    source_task=old_recipe.task.model_dump(mode="json"),
                    change="only_task_version; original evidence unchanged",
                ),
            )
            print(name, result.get("layers"), flush=True)
            if (
                result.get("layers", {}).get("main_build_task_completed") is not True
                or result["agent_usage"]["model_requests"] != 0
            ):
                raise RuntimeError(
                    "方案确认未通过，保留来源与失败，不自动重试：" + name
                )
            path = folder / "verified-simple-recipe.json"
            SimpleProjectRecipe.model_validate(shared.load(path))
            recipes[name] = dict(
                path=str(path),
                sha256=digest(path),
                historical_source_cost_usd=source["historical_source_cost_usd"],
                original_source=source,
                confirmation_provider_cost_usd="0",
            )
        projects.append(item)
    fixture = dict(
        identity="cpp-build-main-system-fixture-v1",
        projects=projects,
        recipes=recipes,
        reference_evidence=str(output),
        boundary="旧成功动作按main-build-v1实建确认；不继承旧完整成功标签，不构造新测试要求",
    )
    comparison.FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    save(comparison.FIXTURE, fixture)
    save(output / "fixture.json", fixture)
    save(
        output / "summary.json",
        dict(provider_calls=0, new_cost_usd="0", recipe_confirmations=3, projects=9),
    )
    files = (
        Path(__file__).resolve(),
        shared.ROOT / "scripts/forge_simple_system.py",
        shared.ROOT
        / "backend/packages/harness/deerflow/compile/simple_build_experience.py",
    )
    seal(
        output,
        dict(
            identity="cpp-build-main-system-recipe-confirmation-v1",
            components={
                p.relative_to(shared.ROOT).as_posix(): digest(p) for p in files
            },
        ),
        shared.ROOT,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    prepare(parser.parse_args().output)
