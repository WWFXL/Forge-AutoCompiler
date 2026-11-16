#!/usr/bin/env python3
"""零Provider工程验证：libffi辅助文件更新后继续构建，并从原归档重建。"""

import argparse
import hashlib
import json
from pathlib import Path

from forge_simple_system import ROOT, ScriptedSimpleModel, run_simple_system

from deerflow.compile.plan_workflow import _digest
from deerflow.compile.simple_build_task import (
    SIMPLE_GOAL,
    BuildReference,
    PublicBuildTask,
    SimpleBuildActions,
    assemble_simple_plan,
)

IDENTITY = "cpp-build-source-posthoc-review-repair-v1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    scope = dict(
        identity=IDENTITY,
        kind="zero_provider_engineering",
        provider_calls=0,
        maximum_cost_usd=0,
        authorization="用户批准文件保护改为后验审查及必要验证",
        stop="一条预写工程路径，失败保留，无自动重试",
        scientific_effect_observations=0,
    )
    (args.output / "scope.json").write_text(json.dumps(scope, ensure_ascii=False, indent=2) + "\n")
    projects = json.loads((ROOT / "benchmarks/fixtures/planning-tool-p4-comparison-v1/tasks.json").read_text())["projects"]
    item = next(p for p in projects if p["name"] == "libffi")
    task = PublicBuildTask.model_validate(item["task"]).model_copy(update={"goal": SIMPLE_GOAL, "plan_id": IDENTITY})
    reference = BuildReference.model_validate(item["reference"]).model_copy(update={"task_sha256": _digest(task.model_dump(mode="json"))})
    commands = [
        (
            "dependencies",
            "dependency",
            "apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends autoconf automake libtool libltdl-dev texinfo",
        ),
        ("bootstrap", "configure", "autoreconf -fiv"),
        ("configure", "configure", "./configure"),
        ("build", "build", "make -j2"),
    ]
    actions = SimpleBuildActions.model_validate(
        dict(
            reason="预写工程路径，真实重生成辅助文件；不是Agent自主发现",
            steps=[
                dict(
                    step_id=name,
                    role=role,
                    command=command,
                    source="开发者针对性工程验证",
                    expected="实际命令成功",
                    requires=[] if i == 0 else [commands[i - 1][0]],
                )
                for i, (name, role, command) in enumerate(commands)
            ],
        )
    )
    result = run_simple_system(
        task=task,
        reference=reference,
        source_archive=Path(item["source_archive"]),
        output_root=args.output / "libffi",
        method="forge",
        model=ScriptedSimpleModel(responses=[], calls=[]),
        accepted_models=("zero-provider-script",),
        family="libffi",
        maximum_cost_usd="0",
        pricing_by_model={"zero-provider-script": ("0", "0")},
        initial_plan=assemble_simple_plan(task, actions),
        validation_scope="main_build",
        replay_seconds=900,
    )
    summary = {
        key: result.get(key)
        for key in (
            "status",
            "layers",
            "source_unchanged",
            "source_review",
            "source_protection",
            "cleanup",
            "error",
            "agent_usage",
            "arm_total_wall_seconds",
        )
    }
    summary.update(scope)
    summary["runtime_sha256"] = hashlib.sha256((ROOT / "backend/packages/harness/deerflow/compile/simple_build_runtime.py").read_bytes()).hexdigest()
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k != "source_protection"},
            ensure_ascii=False,
        ),
        flush=True,
    )
    changes = result.get("source_protection", {}).get("changes", [])
    if not (
        result.get("layers", {}).get("reproducible_delivery_completed")
        and result.get("cleanup", {}).get("succeeded")
        and result.get("source_review") == "pending_review"
        and any(row["kind"] == "modified" and row["path"] in {"config.guess", "config.sub"} for row in changes)
    ):
        raise RuntimeError("工程路径未满足完成条件；保留结果，不自动重试")
    if (args.output / "libffi/verified-simple-recipe.json").exists():
        raise RuntimeError("未经审查的改动不得自动入成功经验库")


if __name__ == "__main__":
    main()
