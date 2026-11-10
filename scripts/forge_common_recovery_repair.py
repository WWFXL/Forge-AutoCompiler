#!/usr/bin/env python3
"""历史问题项目的独立工程实建；零Provider，不补跑H0/R1比较。"""

from __future__ import annotations

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
    SimpleBuildPlan,
)

IDENTITY = "cpp-build-common-recovery-repair-2026-11-10-v1"
FIXTURE = ROOT / "benchmarks/fixtures/common-recovery-repair-v1/cases.json"


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    fixture_path = args.fixture.resolve()
    fixture = json.loads(fixture_path.read_text())
    identity = fixture["identity"]
    files = [
        "scripts/forge_common_recovery_repair.py",
        "scripts/forge_simple_system.py",
        fixture_path.relative_to(ROOT).as_posix(),
        *[
            "backend/packages/harness/deerflow/compile/" + name + ".py"
            for name in (
                "operations",
                "schemas",
                "docker_runtime",
                "simple_build_runtime",
                "simple_build_task",
                "simple_build_agents",
                "simple_planning_context",
            )
        ],
    ]
    hashes = {}
    for name in files:
        path = ROOT / name
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        target = args.output / "source-snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    save(
        args.output / "scope.json",
        dict(
            identity=identity,
            kind="zero_provider_engineering",
            authorization=fixture.get(
                "authorization", "用户要求集中解决E53共同问题；仅必要修复与少量真实构建"
            ),
            provider_calls=0,
            maximum_model_cost_usd=0,
            cases=[c["name"] for c in fixture["cases"]],
            stopping_rule="声明路径各一次；异常或清理失败立即停止，不自动重试，不追加比较",
            comparison_policy=fixture.get("comparison_policy"),
            revision=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            fixture_sha256=hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
            executed_source_sha256=hashes,
            historical_evidence="forge-recovery-harness-comparison-flash-v2，只读；原终态不变",
        ),
    )
    save(args.output / "cases.json", fixture)
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
            initial_plan=SimpleBuildPlan.model_validate(case["initial_plan"]),
            validation_scope="main_build",
            author_test_seconds=60,
            replay_seconds=600,
        )
        sessions = list(
            (args.output / case["name"]).glob(
                ".compile-sessions/simple-system/*/session.json"
            )
        )
        session = json.loads(sessions[0].read_text())
        row = dict(
            name=case["name"],
            status=result["status"],
            layers=result.get("layers"),
            source_unchanged=result.get("source_unchanged"),
            cleanup=result.get("cleanup"),
            error=result.get("error"),
            usage=result.get("agent_usage"),
            wall_seconds=result["arm_total_wall_seconds"],
            replay_attempts=[
                dict(
                    attempt_id=a["attempt_id"],
                    status=a["status"],
                    comparison_policy=a.get("comparison_policy"),
                    failure_classification=a.get("failure_classification"),
                    duration_seconds=a["duration_seconds"],
                    artifact_diagnostics=[
                        dict(
                            path=c["path"],
                            passed=c["passed"],
                            differences=c.get("diagnostic_differences", []),
                        )
                        for c in a.get("artifacts", [])
                    ],
                )
                for a in session.get("replay_attempts", [])
            ],
            native_smokes=[
                dict(
                    command=r["command"],
                    exit_code=r["exit_code"],
                    timeout_seconds=r["timeout_seconds"],
                    duration_seconds=r["duration_seconds"],
                )
                for r in session["commands"]
                if r["role"] == "smoke"
            ],
        )
        rows.append(row)
        save(
            args.output / "summary.json",
            dict(identity=identity, provider_calls=0, rows=rows),
        )
        print(json.dumps(row, ensure_ascii=False), flush=True)
        assert result["cleanup"]["succeeded"] and result["source_unchanged"] is True, (
            row
        )
        assert (
            result["layers"]["main_build_task_completed"]
            and result["layers"]["reproducible_delivery_completed"]
        ), row
        assert result["agent_usage"]["model_requests"] == 0 and not model.position, row
    save(
        args.output / "completed.json",
        dict(
            identity=identity,
            engineering_paths_passed=len(rows),
            provider_calls=0,
            model_cost_usd=0,
            scientific_effect_observations=0,
        ),
    )


if __name__ == "__main__":
    main()
