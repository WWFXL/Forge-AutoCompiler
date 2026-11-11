#!/usr/bin/env python3
"""共同准备/交付修复的四条零Provider真实构建，不回填旧实验。"""

import argparse
import copy
import hashlib
import json
import shutil
from pathlib import Path

from forge_simple_system import ROOT, ScriptedSimpleModel, run_simple_system

from deerflow.compile.simple_build_task import BuildReference, PublicBuildTask, SimpleBuildActions, assemble_simple_plan

IDENTITY = "cpp-build-common-preparation-delivery-repair-v3"
HISTORY = Path("/home/yiwei/.codex/outputs/forge-planning-p3-fixed-r2-comparison-flash-v1")


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project", choices=("jansson", "toybox", "linenoise", "snapraid"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    fixture = ROOT / "benchmarks/fixtures/planning-p3-fixed-r2-comparison-v1/tasks.json"
    projects = {p["name"]: p for p in json.loads(fixture.read_text())["projects"]}
    cases = []
    for name, slot in (("jansson", "17-jansson-P0_R2"), ("toybox", "03-toybox-P3_R2"), ("linenoise", "27-linenoise-P3_R2"), ("snapraid", "29-snapraid-P0_R2")):
        if args.project and name != args.project:
            continue
        reference = copy.deepcopy(projects[name]["reference"])
        if name == "snapraid":
            reference["executable_smokes"] = [
                dict(
                    artifact_name="snapraid",
                    step=dict(
                        step_id="snapraid-version",
                        role="smoke",
                        command="/artifacts/snapraid --version",
                        workdir="/artifacts",
                        source="cmdline/snapraid.c:303,874-876；version选项明确exit(EXIT_SUCCESS)",
                        expected="实际作者版本入口成功",
                        required_output=["snapraid"],
                    ),
                )
            ]
        actions = json.loads((HISTORY / ("slot-" + slot) / "agent/simple-actions-1.json").read_text())
        responses = []
        if name == "jansson":
            # 使用真实作者bootstrap，角色为dependency；配置变化必须先清理、再生成configure。
            actions["steps"][0]["role"] = "dependency"
            repaired = copy.deepcopy(actions)
            repaired["steps"][1]["command"] = "./configure --disable-dependency-tracking"
            repaired["reason"] = "工程受控恢复：先清理，再重做作者bootstrap及配置，默认主目标不变"
            actions["steps"][-1]["command"] = "make forge_controlled_missing_target"
            responses = [repaired]
        cases.append(dict(project=name, initial=actions, responses=responses, task=projects[name]["task"], reference=reference, source_archive=projects[name]["source_archive"]))
    sources = [Path(__file__), ROOT / "backend/packages/harness/deerflow/compile/simple_build_runtime.py", ROOT / "scripts/forge_simple_system.py", ROOT / "backend/packages/harness/deerflow/compile/simple_build_task.py"]
    hashes = {}
    for path in sources:
        target = args.output / "source-snapshot" / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    save(
        args.output / "scope.json",
        dict(
            identity=IDENTITY,
            kind="zero_provider_engineering",
            provider_calls=0,
            maximum_cost_usd=0,
            authorization="用户要求按顺序修复共同机制并少量真实构建",
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
        model = ScriptedSimpleModel(responses=[], calls=[dict(name="SimpleBuildActions", args=r) for r in case["responses"]])
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
            initial_plan=assemble_simple_plan(task, SimpleBuildActions.model_validate(case["initial"])),
            validation_scope="main_build",
            replay_seconds=600,
        )
        row = {k: result.get(k) for k in ("status", "layers", "source_unchanged", "cleanup", "error", "agent_usage", "arm_total_wall_seconds")}
        row.update(project=case["project"], scripted_responses=model.position)
        session = json.loads(next((args.output / case["project"]).glob(".compile-sessions/*/*/session.json")).read_text())
        row["containers"] = [v for v in [session.get("container_id"), session.get("container_name"), *[a.get("container_id") for a in session["replay_attempts"]], *[a.get("container_name") for a in session["replay_attempts"]]] if v]
        rows.append(row)
        save(args.output / "summary.json", dict(identity=IDENTITY, provider_calls=0, rows=rows))
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if not (result["cleanup"]["succeeded"] and result["source_unchanged"] and result["layers"]["reproducible_delivery_completed"] and model.position == len(case["responses"])):
            raise RuntimeError("本次工程路径未完成，保留证据，不自动重试")
    save(args.output / "completed.json", dict(engineering_paths_passed=len(rows), provider_calls=0, scientific_effect_observations=0))


if __name__ == "__main__":
    main()
