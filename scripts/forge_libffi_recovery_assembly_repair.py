#!/usr/bin/env python3
"""E57 libffi的零Provider工程复现：原失败→结构化恢复→真实干净重建。"""

import argparse
import copy
import hashlib
import json
import shutil
from pathlib import Path

from forge_simple_system import ROOT, ScriptedSimpleModel, run_simple_system

from deerflow.compile.simple_build_task import (
    BuildReference,
    PublicBuildTask,
    SimpleBuildActions,
    assemble_simple_plan,
)

IDENTITY = "cpp-build-libffi-recovery-assembly-repair-v1"
HISTORY = Path(
    "/home/yiwei/.codex/outputs/forge-planning-tool-p4-comparison-flash-v1/slot-16-libffi-B_P0_enforced"
)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
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
    # 原始响应和修订后的规范标识分别保存；不改命令、工作目录或作者目标。
    repaired["steps"] = [
        dict(
            step_id="install-ltdl.1",
            role="dependency",
            command="DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends libltdl-dev && dpkg-query -W libtool libltdl-dev && dpkg-query -S /usr/share/aclocal/ltdl.m4 && grep -n 'AC_DEFUN.*LT_SYS_SYMBOL_USCORE' /usr/share/aclocal/ltdl.m4",
            workdir="/workspace/repo",
            requires=["install-autotools"],
            source="configure.ac:219；Libtool发行包m4/ltdl.m4的LT_SYS_SYMBOL_USCORE定义及Debian/Ubuntu libltdl-dev包",
            expected="补齐作者所需的真实ltdl宏，不改原源码或制造空宏",
        ),
        *repaired["steps"][1:],
    ]
    repaired["steps"][1]["requires"] = ["install-ltdl.1"]
    repaired["reason"] = (
        "原autogen因LT_SYS_SYMBOL_USCORE未展开失败；补齐libltdl-dev宏文件，保留已成功工具安装，再生成配置和构建默认主库"
    )
    save(
        args.output / "scope.json",
        dict(
            identity=IDENTITY,
            kind="zero_provider_engineering",
            provider_calls=0,
            maximum_cost_usd=0,
            authorization="用户2026-11-16要求执行共同装配修复及libffi针对性真实构建",
            stop="单工程路径；非预期失败保留并结束本身份，不自动重试",
            historical_evidence_readonly=str(HISTORY),
            scientific_effect_observations=0,
        ),
    )
    save(
        args.output / "case.json",
        dict(
            task=item["task"],
            reference=item["reference"],
            source_archive=item["source_archive"],
            initial=initial,
            repaired=repaired,
        ),
    )
    hashes = {}
    for name in [
        "scripts/forge_libffi_recovery_assembly_repair.py",
        "scripts/forge_simple_system.py",
        "backend/packages/harness/deerflow/compile/simple_build_task.py",
        "backend/packages/harness/deerflow/compile/simple_build_runtime.py",
    ]:
        target = args.output / "source-snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    save(args.output / "source-sha256.json", hashes)
    model = ScriptedSimpleModel(
        responses=[], calls=[dict(name="SimpleBuildActions", args=repaired)]
    )
    task = PublicBuildTask.model_validate(item["task"])
    result = run_simple_system(
        task=task,
        reference=BuildReference.model_validate(item["reference"]),
        source_archive=Path(item["source_archive"]),
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
    )
    row = {
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
    row.update(
        identity=IDENTITY,
        provider_calls=0,
        scripted_responses=model.position,
        scientific_effect_observations=0,
    )
    save(args.output / "summary.json", row)
    print(json.dumps(row, ensure_ascii=False), flush=True)
    if not (
        result.get("cleanup", {}).get("succeeded")
        and result.get("source_unchanged")
        and result.get("layers", {}).get("reproducible_delivery_completed")
        and model.position == 1
    ):
        raise RuntimeError("工程路径未完成，保留结果，不自动重试")
    save(
        args.output / "completed.json",
        dict(
            engineering_paths_passed=1,
            provider_calls=0,
            scientific_effect_observations=0,
        ),
    )


if __name__ == "__main__":
    main()
