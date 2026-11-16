#!/usr/bin/env python3
"""libffi真实缺宏→容器诊断→预写系统包修复→干净重建；零Provider工程观察。"""

import argparse
import copy
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from forge_simple_system import ROOT, ScriptedSimpleModel, run_simple_system

from deerflow.compile.offline_harness import PlanningHarness
from deerflow.compile.plan_workflow import _digest
from deerflow.compile.recovery_harness import RecoveryHarness
from deerflow.compile.simple_build_task import (
    SIMPLE_PROMPT,
    BuildReference,
    PublicBuildTask,
    SimpleBuildActions,
    assemble_simple_plan,
)

IDENTITY = "cpp-build-recovery-environment-r2-repair-v1"
HISTORY = Path(
    "/home/yiwei/.codex/outputs/forge-planning-tool-p4-comparison-flash-v1/slot-16-libffi-B_P0_enforced"
)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    subprocess.run(
        ["bash", str(ROOT / "scripts/require-docker-runtime.sh")],
        check=True,
        timeout=30,
    )
    args.output.mkdir(parents=True, exist_ok=False)
    item = next(
        p
        for p in json.loads(
            (
                ROOT / "benchmarks/fixtures/planning-tool-p4-comparison-v1/tasks.json"
            ).read_text()
        )["projects"]
        if p["name"] == "libffi"
    )
    initial = json.loads((HISTORY / "agent/simple-actions-1.json").read_text())
    repaired = copy.deepcopy(initial)
    repaired["steps"].insert(
        1,
        dict(
            step_id="install-missing-development-files",
            role="dependency",
            command="DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends libltdl-dev",
            requires=["install-autotools"],
            source="开发者预写修复；不是模型自主发现",
            expected="安装真实宏文件",
        ),
    )
    repaired["steps"][2]["requires"] = ["install-missing-development-files"]
    repaired["reason"] = (
        "工程验证预写真实开发包修复，不修改作者宏和源码，继续默认主库构建"
    )
    calls = [
        dict(
            name="search_build_files",
            args=dict(query="LT_SYS_SYMBOL_USCORE", scope="project"),
        ),
        dict(
            name="search_build_files",
            args=dict(query="LT_SYS_SYMBOL_USCORE", scope="macros"),
        ),
        dict(
            name="inspect_build_environment", args=dict(kind="command", query="aclocal")
        ),
        dict(
            name="inspect_build_environment",
            args=dict(kind="package", query="libltdl-dev"),
        ),
        dict(
            name="inspect_build_environment",
            args=dict(kind="package_search", query="ltdl"),
        ),
        dict(
            name="inspect_build_environment",
            args=dict(kind="package_file_search", query="ltdl.m4"),
        ),
        dict(
            name="inspect_build_environment",
            args=dict(kind="search_paths", query="aclocal"),
        ),
        dict(name="SimpleBuildActions", args=repaired),
    ]
    save(
        args.output / "scope.json",
        dict(
            identity=IDENTITY,
            kind="zero_provider_engineering",
            provider_calls=0,
            maximum_cost_usd=0,
            scientific_effect_observations=0,
            authorization="用户批准修复及针对性零Provider验证",
            stop="一条工程路径，无自动重试；失败保留，不替换旧实验",
            scripted_repair=True,
        ),
    )
    save(
        args.output / "case.json",
        dict(
            task=item["task"],
            reference=item["reference"],
            source_archive=item["source_archive"],
            initial=initial,
            calls=calls,
        ),
    )
    hashes = {}
    for name in [
        "scripts/forge_recovery_environment_repair.py",
        "scripts/forge_simple_system.py",
        "backend/packages/harness/deerflow/compile/recovery_environment.py",
        "backend/packages/harness/deerflow/compile/simple_build_task.py",
        "backend/packages/harness/deerflow/compile/simple_planning_context.py",
    ]:
        target = args.output / "source-snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    save(args.output / "source-sha256.json", hashes)
    task = PublicBuildTask.model_validate(item["task"])
    archive = Path(item["source_archive"])
    if hashlib.sha256(archive.read_bytes()).hexdigest() != task.source_archive_sha256:
        raise ValueError("源码归档与原任务不匹配")
    model = ScriptedSimpleModel(responses=[], calls=calls)
    harness = PlanningHarness(name="P0", base_prompt_sha256=_digest(SIMPLE_PROMPT))
    recovery = RecoveryHarness.model_validate_json(
        (
            ROOT
            / "benchmarks/fixtures/recovery-harness-system-context-gpt61sol-v1/candidate.json"
        ).read_text()
    ).model_copy(update={"base_prompt_sha256": _digest(SIMPLE_PROMPT)})
    result = run_simple_system(
        task=task,
        reference=BuildReference.model_validate(item["reference"]),
        source_archive=archive,
        output_root=args.output / "libffi",
        method="forge",
        model=model,
        accepted_models=("zero-provider-script",),
        family="libffi",
        maximum_cost_usd="0",
        pricing_by_model={"zero-provider-script": ("0", "0")},
        initial_plan=assemble_simple_plan(
            task, SimpleBuildActions.model_validate(initial)
        ),
        validation_scope="main_build",
        replay_seconds=900,
        harness=harness,
        recovery_harness=recovery,
    )
    summary = {
        k: result.get(k)
        for k in (
            "status",
            "layers",
            "source_unchanged",
            "source_protection",
            "cleanup",
            "error",
            "agent_usage",
            "arm_total_wall_seconds",
        )
    }
    events = [
        json.loads(line)
        for line in (args.output / "libffi/agent/events.jsonl").read_text().splitlines()
    ]
    queries = [e for e in events if e["event"] == "recovery.environment_query"]
    summary.update(
        identity=IDENTITY,
        provider_calls=0,
        scientific_effect_observations=0,
        scripted_responses=model.position,
        queries=queries,
    )
    save(args.output / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if not (
        result.get("cleanup", {}).get("succeeded")
        and result.get("source_unchanged")
        and result.get("layers", {}).get("reproducible_delivery_completed")
        and len(queries) == 7
        and model.position == 8
    ):
        raise RuntimeError("工程路径未完成，结果保留，不自动重试")
    if not (
        queries[0]["result"]["status"] == "matches"
        and queries[1]["result"]["status"] == "no_match_in_scope"
        and "libltdl-dev" in queries[4]["result"].get("output", "")
    ):
        raise RuntimeError("关键容器诊断证据与预期不符；不宣告成功")
    if queries[3]["result"].get("installed") is not False:
        raise RuntimeError("缺包应返回明确未安装状态")
    session = json.loads(
        next(
            (args.output / "libffi/.compile-sessions").glob("*/*/session.json")
        ).read_text()
    )
    recipe = session.get("replay_recipe") or {}
    diagnostic_ids = {q["result"]["command_id"] for q in queries}
    if diagnostic_ids & {step["command_id"] for step in recipe.get("steps", [])}:
        raise RuntimeError("诊断错误地进入重放配方")
    save(
        args.output / "completed.json",
        dict(
            engineering_paths_passed=1,
            provider_calls=0,
            scientific_effect_observations=0,
            diagnostic_commands_excluded_from_recipe=True,
        ),
    )


if __name__ == "__main__":
    main()
