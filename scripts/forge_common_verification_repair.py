"""四条零Provider真实构建路径；只验证共同机制，不重跑或回填E52。"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from forge_simple_system import ROOT, ScriptedSimpleModel, run_simple_system

from deerflow.compile.simple_build_task import BuildReference, PublicBuildTask, SimpleBuildActions, assemble_simple_plan

IDENTITY = "cpp-build-common-verification-recipe-repair-v2"


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--historical-root", type=Path, default=Path("/home/yiwei/.codex/outputs/forge-offline-harness-round2-flash-v1"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    projects = {p["name"]: p for p in json.loads((ROOT / "benchmarks/fixtures/offline-harness-round2/tasks.json").read_text())["projects"]}
    history = args.historical_root / "comparison"
    fse_actions = json.loads((history / "slot-24-fse-H0/agent/simple-actions-1.json").read_text())
    initial = json.loads((history / "slot-36-libsigcplusplus-H2/agent/simple-actions-2.json").read_text())
    repaired = json.loads((history / "slot-36-libsigcplusplus-H2/agent/simple-actions-3.json").read_text())
    # 独立参考的作者依据：programs/commandline.c:73、165，-V返回欢迎/版本信息。
    smoke = dict(
        artifact_name="fse",
        step=dict(
            step_id="native-version",
            role="smoke",
            command="/artifacts/fse -V",
            workdir="/workspace/repo",
            source="programs/commandline.c:73,165；作者case V返回欢迎/版本信息",
            expected="实际运行交付的主程序",
            required_output=["FSE : Finite State Entropy"],
        ),
    )
    bad_smoke = json.loads(json.dumps(smoke))
    bad_smoke["step"].update(command="/artifacts/fse --version", source="受控负例：作者未支持的参数，必须拒绝")
    discard = {**repaired, "discard_dependencies": {"install-mm-common": "受控负例：显式删除仍必需的安装步骤，必须由干净重放拒绝"}}
    cases = [
        dict(name="fse-native-smoke", project="fse", initial=fse_actions, smokes=[smoke], responses=[], expected_replay="passed", expected_final=True),
        dict(name="fse-invalid-smoke", project="fse", initial=fse_actions, smokes=[bad_smoke], responses=[], expected_replay="not_started", expected_final=False),
        dict(name="libsig-retained-dependency", project="libsigcplusplus", initial=initial, smokes=[], responses=[repaired], expected_replay="passed", expected_final=True),
        dict(name="libsig-explicit-discard-negative", project="libsigcplusplus", initial=initial, smokes=[], responses=[discard], expected_replay="failed", expected_final=False),
    ]
    save(args.output / "cases.json", cases)
    files = [
        "scripts/forge_common_verification_repair.py",
        "scripts/forge_simple_system.py",
        *["backend/packages/harness/deerflow/compile/" + n + ".py" for n in ("simple_build_task", "simple_build_runtime")],
        "backend/tests/test_common_verification_recipe.py",
    ]
    hashes = {}
    for name in files:
        target = args.output / "source-snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    save(
        args.output / "scope.json",
        dict(
            identity=IDENTITY,
            kind="zero_provider_engineering",
            authorization="用户要求完成两项共同机制修复、修正标签并少量针对性真实构建后结束",
            maximum_provider_cost_usd=0,
            provider_calls=0,
            cases=4,
            stop="四个独立路径各执行一次；非预期失败或cleanup失败即停，不自动重试",
            base_revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            source_sha256=hashes,
            historical_evidence_readonly=str(args.historical_root),
        ),
    )
    rows = []
    for case in cases:
        item = projects[case["project"]]
        task = PublicBuildTask.model_validate(item["task"])
        ref = BuildReference.model_validate({**item["reference"], "executable_smokes": case["smokes"]})
        model = ScriptedSimpleModel(responses=[], calls=[dict(name="SimpleBuildActions", args=r) for r in case["responses"]])
        print("START " + case["name"], flush=True)
        result = run_simple_system(
            task=task,
            reference=ref,
            source_archive=Path(item["source_archive"]),
            output_root=args.output / case["name"],
            method="forge",
            model=model,
            accepted_models=("zero-provider-script",),
            family=case["project"],
            maximum_cost_usd="0.00",
            pricing_by_model={"zero-provider-script": ("0", "0")},
            initial_plan=assemble_simple_plan(task, SimpleBuildActions.model_validate(case["initial"])),
            validation_scope="main_build",
            replay_seconds=300,
        )
        sessions = list((args.output / case["name"]).glob(".compile-sessions/simple-system/*/session.json"))
        session = json.loads(sessions[0].read_text())
        recipe = session.get("replay_recipe") or {}
        dependency_records = [r for r in session["commands"] if r["role"] == "dependency"]
        row = dict(
            name=case["name"],
            status=result["status"],
            layers=result.get("layers"),
            source_unchanged=result.get("source_unchanged"),
            cleanup=result.get("cleanup"),
            scripted_responses=model.position,
            usage=result.get("agent_usage"),
            replay_attempts=session.get("replay_attempts"),
            dependency_records=dependency_records,
            recipe=recipe,
            wall_seconds=result["arm_total_wall_seconds"],
            error=result.get("error"),
        )
        rows.append(row)
        save(args.output / "summary.json", dict(identity=IDENTITY, provider_calls=0, rows=rows))
        print(json.dumps({k: v for k, v in row.items() if k not in {"recipe", "dependency_records", "replay_attempts"}}, ensure_ascii=False), flush=True)
        assert result["source_unchanged"] is True and result["cleanup"]["succeeded"], row
        assert result["layers"]["primary_build_completed"] is True and result["layers"]["delivery"] == "passed", row
        assert result["layers"]["clean_replay"] == case["expected_replay"] and result["layers"]["final_verification_passed"] is case["expected_final"], row
        assert result["layers"]["reproducible_delivery_completed"] is case["expected_final"] and model.position == len(case["responses"]), row
        if case["project"] == "libsigcplusplus":
            assert len(dependency_records) == 1 and dependency_records[0]["exit_code"] == 0, row
            # 配方用实际成功ID取舍，不含失败探索；正例保留安装，负例显式删除。
            selected = {s["command_id"] for s in recipe["steps"]}
            assert (dependency_records[0]["command_id"] in selected) is case["expected_final"], row
            assert all(r["exit_code"] == 0 and not r["timed_out"] for r in session["commands"] if r["command_id"] in selected), row
    save(args.output / "completed.json", dict(identity=IDENTITY, engineering_cases_as_expected=len(rows), provider_calls=0, cost_usd=0, scientific_effect_observations=0, old_evidence_modified=False))


if __name__ == "__main__":
    main()
