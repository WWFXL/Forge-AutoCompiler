#!/usr/bin/env python3
"""规划依赖查询→安装方案→真实构建的零Provider接线验证，不代表模型效果。"""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from forge_libffi_macro_experience import material
from forge_simple_system import ROOT, ScriptedSimpleModel, run_simple_system

from deerflow.compile.plan_workflow import _digest

IDENTITY = "cpp-build-planning-dependency-engineering-v1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    task, reference, archive, recovery = material()
    task = task.model_copy(update={"plan_id": IDENTITY})
    reference = reference.model_copy(update={"task_sha256": _digest(task.model_dump(mode="json"))})
    args.output.mkdir(parents=True, exist_ok=False)
    scope = dict(
        identity=IDENTITY,
        provider_calls=0,
        cost_usd=0,
        authorization="用户执行下一步：实现规划依赖检查与必要真实验证",
        scripted_model=True,
        known_package_in_script=True,
        effect_claim=False,
        revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    )
    (args.output / "scope.json").write_text(json.dumps(scope, ensure_ascii=False, indent=2))
    snapshot = args.output / "source-snapshot"
    names = ["scripts/forge_planning_dependency_check.py", "scripts/forge_simple_system.py"]
    names += [str(p.relative_to(ROOT)) for p in (ROOT / "backend/packages/harness/deerflow/compile").glob("*.py")]
    hashes = {}
    for name in names:
        p = snapshot / name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, p)
        hashes[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    (args.output / "source-sha256.json").write_text(json.dumps(hashes, indent=2))
    steps = [
        dict(step_id="dependencies", role="dependency", command="apt-get install -y --no-install-recommends libltdl-dev", source="工程脚本：真实安装状态和ltdl.m4提供者查询", expected="补齐开发宏"),
        dict(step_id="autogen", role="configure", command="./autogen.sh", source="作者构建入口", expected="生成配置"),
        dict(step_id="configure", role="configure", command="./configure --disable-docs", source="作者主库配置", expected="配置主库"),
        dict(step_id="build", role="build", command="make -j2", source="作者构建入口", expected="构建主库"),
    ]
    calls = [
        dict(name="search_build_files", args=dict(query="LT_SYS_SYMBOL_USCORE", scope="project")),
        dict(name="inspect_build_environment", args=dict(kind="package", query="libltdl-dev")),
        dict(name="inspect_build_environment", args=dict(kind="package_file_search", query="ltdl.m4")),
        dict(name="SimpleBuildActions", args=dict(reason="工程脚本在初始规划核实缺包后生成安装与原构建步骤，不调用恢复", steps=steps)),
    ]
    result = run_simple_system(
        task=task,
        reference=reference,
        source_archive=archive,
        output_root=args.output / "libffi",
        method="forge",
        model=ScriptedSimpleModel(responses=[], calls=calls),
        accepted_models=("zero-provider-script",),
        family="libffi",
        maximum_cost_usd="0",
        pricing_by_model={"zero-provider-script": ("0", "0")},
        recovery_harness=recovery,
        enforce_planning_tools=True,
        inspect_planning_dependencies=True,
        validation_scope="main_build",
        replay_seconds=900,
    )
    (args.output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    events = [json.loads(line) for line in (args.output / "libffi/agent/events.jsonl").read_text().splitlines()]
    queries = [e for e in events if e["event"] == "planning.environment_query"]
    assert len(queries) == 3 and queries[1]["result"]["installed"] is False
    assert "libltdl-dev: /usr/share/aclocal/ltdl.m4" in queries[2]["result"]["output"]
    assert not any(e["event"] == "agent.started" and e["recovery"] for e in events)
    assert result["layers"]["reproducible_delivery_completed"] and result["cleanup"]["succeeded"]
    print(json.dumps(dict(provider_calls=0, scripted_responses=4, queries=len(queries), layers=result["layers"], cleanup=result["cleanup"], seconds=result["arm_total_wall_seconds"]), ensure_ascii=False))


if __name__ == "__main__":
    main()
