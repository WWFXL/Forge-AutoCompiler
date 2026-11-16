#!/usr/bin/env python3
"""E58失败项目的零Provider工程构建与重建，不回填模型实验。"""

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

IDENTITY = "cpp-build-e58-failure-repair-v3"
HISTORY = Path(
    "/home/yiwei/.codex/outputs/forge-harness-update-comparison-flash-2026-11-17-v1"
)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project", choices=("smenu", "quickjs", "zstd", "libtasn1"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    fixture = ROOT / "benchmarks/fixtures/harness-update-comparison-v1/tasks.json"
    projects = {p["name"]: p for p in json.loads(fixture.read_text())["projects"]}
    cases = []
    for name, slot in (
        ("smenu", "06-smenu-LH_v1"),
        ("quickjs", "10-quickjs-LH_v1"),
        ("zstd", "22-zstd-LH_v1"),
        ("libtasn1", "30-libtasn1-LH_v1"),
    ):
        if args.project and name != args.project:
            continue
        reference = copy.deepcopy(projects[name]["reference"])
        if name in ("smenu", "quickjs", "zstd"):
            smoke = reference["executable_smokes"][0]["step"]
            if name == "smenu":
                smoke.update(
                    command="TERM=xterm script -qec '/artifacts/smenu -V' /dev/null",
                    required_output=["Version:"],
                    source="smenu.c:10457-10472先打开/dev/tty；8892-8906版本动作输出Version并退出0",
                    expected="提供原生PTY后，作者版本入口退出0并输出版本",
                )
            elif name == "quickjs":
                smoke.update(
                    required_output=["2"],
                    source="qjs.c表达式入口；原运算命令仅print(1+1)，真实输出2",
                    expected="算术表达式无异常，输出2并退出0",
                )
            else:
                smoke.update(
                    required_output=["Zstandard CLI"],
                    source="programs/zstdcli.c作者版本入口输出Zstandard CLI",
                    expected="交付程序原生版本入口退出0并输出版本",
                )
        actions = json.loads(
            (HISTORY / ("slot-" + slot) / "agent/simple-actions-1.json").read_text()
        )
        responses = []
        if name == "libtasn1":
            # 保留原首个真实失败，提交当时已生成但被共同基座阻断的补包方案。
            responses = [
                json.loads(
                    (
                        HISTORY / ("slot-" + slot) / "agent/simple-actions-2.json"
                    ).read_text()
                )
            ]
            # 首轮越过基座阻断后，fuzz/corpus2array.c未先包含config.h。
            # 使用正常编译选项，不改源码、不跳过默认构建目标。
            header_repair = copy.deepcopy(responses[0])
            header_repair["reason"] = (
                "工程诊断：gnulib包装头要求config.h优先；为默认make全部目标提供该头"
            )
            header_repair["steps"][-1]["command"] = (
                "make -j2 CPPFLAGS='-include /workspace/repo/config.h'"
            )
            responses.append(header_repair)
        cases.append(
            dict(
                project=name,
                initial=actions,
                responses=responses,
                task=projects[name]["task"],
                reference=reference,
                source_archive=projects[name]["source_archive"],
            )
        )
    sources = [
        Path(__file__),
        ROOT / "backend/packages/harness/deerflow/compile/simple_build_runtime.py",
        ROOT / "backend/packages/harness/deerflow/compile/generated_inputs.py",
        ROOT / "backend/packages/harness/deerflow/compile/operations.py",
        ROOT / "scripts/forge_simple_system.py",
        ROOT / "backend/packages/harness/deerflow/compile/simple_build_task.py",
    ]
    hashes = {}
    for path in sources:
        target = args.output / "source-snapshot" / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        hashes[str(path.relative_to(ROOT))] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    save(
        args.output / "scope.json",
        dict(
            identity=IDENTITY,
            kind="zero_provider_engineering",
            provider_calls=0,
            maximum_cost_usd=0,
            authorization="用户要求分析并修复本轮四个未完成项目，然后再系统比较",
            stop="各路径一次；非预期失败或清理失败停止，不自动重试",
            historical_evidence_readonly=str(HISTORY),
            source_sha256=hashes,
        ),
    )
    save(args.output / "cases.json", cases)
    rows = []
    for case in cases:
        print("START " + case["project"], flush=True)
        task = PublicBuildTask.model_validate(case["task"])
        model = ScriptedSimpleModel(
            responses=[],
            calls=[dict(name="SimpleBuildActions", args=r) for r in case["responses"]],
        )
        result = run_simple_system(
            task=task,
            reference=BuildReference.model_validate(case["reference"]),
            source_archive=Path(case["source_archive"]),
            output_root=args.output / case["project"],
            method="forge",
            model=model,
            accepted_models=("zero-provider-script",),
            family=case["project"],
            maximum_cost_usd="0",
            pricing_by_model={"zero-provider-script": ("0", "0")},
            initial_plan=assemble_simple_plan(
                task, SimpleBuildActions.model_validate(case["initial"])
            ),
            validation_scope="main_build",
            replay_seconds=600,
        )
        row = {
            k: result.get(k)
            for k in (
                "status",
                "layers",
                "source_unchanged",
                "cleanup",
                "error",
                "agent_usage",
                "arm_total_wall_seconds",
            )
        }
        row.update(project=case["project"], scripted_responses=model.position)
        session = json.loads(
            next(
                (args.output / case["project"]).glob(
                    ".compile-sessions/*/*/session.json"
                )
            ).read_text()
        )
        row["containers"] = [
            v
            for v in [
                session.get("container_id"),
                session.get("container_name"),
                *[a.get("container_id") for a in session["replay_attempts"]],
                *[a.get("container_name") for a in session["replay_attempts"]],
            ]
            if v
        ]
        rows.append(row)
        save(
            args.output / "summary.json",
            dict(identity=IDENTITY, provider_calls=0, rows=rows),
        )
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if not (
            result["cleanup"]["succeeded"]
            and result["layers"]["reproducible_delivery_completed"]
            and model.position == len(case["responses"])
        ):
            raise RuntimeError("本次工程路径未完成，保留证据，不自动重试")
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
