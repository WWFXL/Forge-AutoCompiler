#!/usr/bin/env python3
"""查询就绪镜像上的真实恢复工程路径；零Provider、预写修复、不评价模型。"""

import argparse
import copy
import hashlib
import json
import shutil
from pathlib import Path

from forge_recovery_environment_repair import HISTORY, save
from forge_simple_system import ROOT, ScriptedSimpleModel, run_simple_system

from deerflow.compile.offline_harness import PlanningHarness
from deerflow.compile.plan_workflow import _digest
from deerflow.compile.recovery_harness import RecoveryHarness
from deerflow.compile.simple_build_task import SIMPLE_PROMPT, BuildReference, PublicBuildTask, SimpleBuildActions, assemble_simple_plan

IDENTITY = "cpp-build-dependency-provider-repair-v2"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image-id", required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    item = next(p for p in json.loads((ROOT / "benchmarks/fixtures/planning-tool-p4-comparison-v1/tasks.json").read_text())["projects"] if p["name"] == "libffi")
    task = PublicBuildTask.model_validate(dict(item["task"], image_id=args.image_id))
    reference = BuildReference.model_validate(dict(item["reference"], task_sha256=_digest(task.model_dump(mode="json"))))
    archive = Path(item["source_archive"])
    if hashlib.sha256(archive.read_bytes()).hexdigest() != task.source_archive_sha256:
        raise ValueError("原源码摘要不匹配")
    initial = json.loads((HISTORY / "agent/simple-actions-1.json").read_text())
    repaired = copy.deepcopy(initial)
    repaired["steps"].insert(
        1,
        dict(
            step_id="install-missing-development-files",
            role="dependency",
            command="DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends libltdl-dev",
            requires=["install-autotools"],
            source="开发者预写工程验真，不是Agent发现",
            expected="安装真实宏文件",
        ),
    )
    repaired["steps"][2]["requires"] = ["install-missing-development-files"]
    repaired["reason"] = "工程验证真实系统包修复，保持作者源码与主库范围"
    calls = [dict(name="search_build_files", args=dict(query="LT_SYS_SYMBOL_USCORE", scope="project"))]
    for kind, query in [("package_index", "apt"), ("package_search", "libtool"), ("package_description", "libltdl-dev"), ("package_file_search", "ltdl.m4"), ("package", "libltdl-dev")]:
        calls.append(dict(name="inspect_build_environment", args=dict(kind=kind, query=query)))
    calls.append(dict(name="SimpleBuildActions", args=repaired))
    save(args.output / "scope.json", dict(identity=IDENTITY, provider_calls=0, maximum_cost_usd=0, scientific_effect_observations=0, scripted_repair=True, stop="一次工程路径，无自动重试", authorization="用户批准通用依赖查询修复"))
    save(args.output / "case.json", dict(task=task.model_dump(mode="json"), reference=reference.model_dump(mode="json"), initial=initial, calls=calls, source_archive=str(archive)))
    for name in ["scripts/forge_dependency_provider_repair.py", "scripts/forge_simple_system.py", "backend/packages/harness/deerflow/compile/recovery_environment.py"]:
        target = args.output / "source-snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    recovery = RecoveryHarness.model_validate_json((ROOT / "benchmarks/fixtures/recovery-harness-system-context-gpt61sol-v1/candidate.json").read_text()).model_copy(update={"base_prompt_sha256": _digest(SIMPLE_PROMPT)})
    model = ScriptedSimpleModel(responses=[], calls=calls)
    result = run_simple_system(
        task=task,
        reference=reference,
        source_archive=archive,
        output_root=args.output / "libffi",
        method="forge",
        model=model,
        accepted_models=("zero-provider-script",),
        family="libffi",
        maximum_cost_usd="0",
        pricing_by_model={"zero-provider-script": ("0", "0")},
        initial_plan=assemble_simple_plan(task, SimpleBuildActions.model_validate(initial)),
        validation_scope="main_build",
        replay_seconds=900,
        harness=PlanningHarness(name="P0", base_prompt_sha256=_digest(SIMPLE_PROMPT)),
        recovery_harness=recovery,
    )
    events = [json.loads(line) for line in (args.output / "libffi/agent/events.jsonl").read_text().splitlines()]
    queries = [e for e in events if e["event"] == "recovery.environment_query"]
    summary = {k: result.get(k) for k in ("status", "layers", "source_unchanged", "source_protection", "cleanup", "error", "agent_usage", "arm_total_wall_seconds")}
    summary.update(identity=IDENTITY, provider_calls=0, scientific_effect_observations=0, scripted_responses=model.position, queries=queries)
    save(args.output / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if not (result.get("cleanup", {}).get("succeeded") and result.get("layers", {}).get("reproducible_delivery_completed") and len(queries) == 6 and model.position == 7):
        raise RuntimeError("工程路径未完成，保留原件、不自动重试")
    if not (
        queries[1]["result"]["index_state"]["contents"] == "present"
        and "libltdl-dev" in queries[2]["result"].get("output", "")
        and "libltdl-dev: /usr/share/aclocal/ltdl.m4" in queries[4]["result"].get("output", "")
        and queries[5]["result"].get("installed") is False
    ):
        raise RuntimeError("提供者证据或缺包初态不符合预期")
    session = json.loads(next((args.output / "libffi/.compile-sessions").glob("*/*/session.json")).read_text())
    if {q["result"]["command_id"] for q in queries} & {s["command_id"] for s in (session.get("replay_recipe") or {}).get("steps", [])}:
        raise RuntimeError("诊断错误进入重放配方")
    save(args.output / "completed.json", dict(engineering_paths_passed=1, provider_calls=0, scientific_effect_observations=0, diagnostic_commands_excluded_from_recipe=True))


if __name__ == "__main__":
    main()
