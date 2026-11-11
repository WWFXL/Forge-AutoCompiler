#!/usr/bin/env python3
"""E54问题项目的零Provider工程实建，不构成Harness比较或补跑。"""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from forge_simple_system import ROOT, ScriptedSimpleModel, run_simple_system

from deerflow.compile.simple_build_task import (
    BuildReference,
    PublicBuildTask,
    SimpleBuildActions,
    assemble_simple_plan,
)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    save(
        args.output / "scope.json",
        dict(
            identity=fixture["identity"],
            kind="zero_provider_engineering",
            maximum_cost_usd=0,
            authorization="用户要求修复共同问题并做少量针对性真实构建",
            provider_calls=0,
            old_evidence_readonly=True,
            stop="各路径一次；非预期失败停止，不自动重试或追加比较",
        ),
    )
    shutil.copy2(args.fixture, args.output / "cases.json")
    files = [
        "scripts/forge_common_system_repair.py",
        "scripts/forge_simple_system.py",
        *[
            f"backend/packages/harness/deerflow/compile/{n}.py"
            for n in (
                "simple_build_task",
                "simple_build_runtime",
                "simple_planning_context",
                "plan_workflow",
            )
        ],
    ]
    hashes = {}
    for name in files:
        target = args.output / "source-snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    save(
        args.output / "source.json",
        dict(
            revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            sha256=hashes,
        ),
    )
    rows = []
    for case in fixture["cases"]:
        task = PublicBuildTask.model_validate(case["task"])
        reference = BuildReference.model_validate(case["reference"])
        model = ScriptedSimpleModel(responses=[], calls=[])
        print("START " + case["name"], flush=True)
        result = run_simple_system(
            task=task,
            reference=reference,
            source_archive=Path(case["source_archive"]),
            output_root=args.output / case["name"],
            method="forge",
            model=model,
            accepted_models=("zero-provider-script",),
            family=case["name"],
            maximum_cost_usd="0",
            pricing_by_model={"zero-provider-script": ("0", "0")},
            initial_plan=assemble_simple_plan(task, SimpleBuildActions.model_validate(case["actions"])),
            validation_scope="main_build",
            replay_seconds=900,
        )
        row = dict(
            name=case["name"],
            status=result["status"],
            layers=result.get("layers"),
            source_unchanged=result.get("source_unchanged"),
            source_protection=result.get("source_protection"),
            cleanup=result.get("cleanup"),
            error=result.get("error"),
            usage=result.get("agent_usage"),
            wall_seconds=result["arm_total_wall_seconds"],
        )
        rows.append(row)
        save(
            args.output / "summary.json",
            dict(identity=fixture["identity"], provider_calls=0, rows=rows),
        )
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if not (result["cleanup"]["succeeded"] and result["layers"].get("reproducible_delivery_completed") and result["agent_usage"]["model_requests"] == 0):
            raise RuntimeError("工程路径未完成，保留本次结果，不自动重试")
    save(
        args.output / "completed.json",
        dict(
            engineering_paths_passed=len(rows),
            provider_calls=0,
            scientific_effect_observations=0,
        ),
    )


if __name__ == "__main__":
    main()
