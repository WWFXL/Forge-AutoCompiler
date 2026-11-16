#!/usr/bin/env python3
"""修复共同基座后，libffi单次从零自主规划与构建；默认只检查材料。"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from forge_simple_system import ROOT, BuildReference, PublicBuildTask, run_simple_system

from deerflow.compile.build_state_routing import BuildStateRouter
from deerflow.compile.offline_harness import PlanningHarness
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek
from deerflow.compile.plan_workflow import _digest
from deerflow.compile.recovery_harness import RecoveryHarness
from deerflow.compile.simple_build_task import SIMPLE_PROMPT

IDENTITY = "cpp-build-libffi-autonomous-flash-v1"
MODELS = ("DeepSeek-V4.1-Flash-1017", "deepseek-flash")
R2 = (
    ROOT
    / "benchmarks/fixtures/recovery-harness-system-context-gpt61sol-v1/candidate.json"
)


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def material():
    fixture = ROOT / "benchmarks/fixtures/planning-tool-p4-comparison-v1/tasks.json"
    item = next(p for p in load(fixture)["projects"] if p["name"] == "libffi")
    task = PublicBuildTask.model_validate(item["task"])
    reference = BuildReference.model_validate(item["reference"])
    archive = Path(item["source_archive"])
    if hashlib.sha256(archive.read_bytes()).hexdigest() != task.source_archive_sha256:
        raise ValueError("原始源码归档不匹配")
    if reference.task_sha256 != _digest(task.model_dump(mode="json")):
        raise ValueError("独立参考不匹配")
    reference.require_main_build_verification()
    recovery = RecoveryHarness.model_validate(load(R2))
    if (
        recovery.fingerprint()
        != "270becfd8fe2c0c89d0d7ab8c820893cdc6ae7cdd9d2c50e95ecb11f84263743"
    ):
        raise ValueError("已审核R2指导变化")
    recovery = recovery.model_copy(
        update=dict(base_prompt_sha256=_digest(SIMPLE_PROMPT))
    )
    recovery.prompt(SIMPLE_PROMPT)
    return task, reference, archive, recovery


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    task, reference, archive, recovery = material()
    if args.authorization is None:
        print(
            json.dumps(
                dict(
                    identity=IDENTITY,
                    valid=True,
                    provider_calls=0,
                    credentials_read=False,
                    task=task.model_dump(mode="json"),
                ),
                ensure_ascii=False,
            )
        )
        return
    auth = load(args.authorization)
    end = datetime.fromisoformat(auth["deadline_utc"])
    if (
        auth["identity"] != IDENTITY
        or auth["maximum_cost_usd"] != "1.00"
        or not auth["user_authorized"]
        or datetime.now(UTC) >= end
    ):
        raise ValueError("本身份需要有效的一美元单路径授权")
    if args.output is None:
        raise ValueError("必须指定独立新输出目录")
    subprocess.run(
        ["bash", str(ROOT / "scripts/require-docker-runtime.sh")],
        check=True,
        timeout=30,
    )
    args.output.mkdir(parents=True, exist_ok=False)
    save(args.output / "authorization.json", auth)
    snapshot = args.output / "source-snapshot"
    snapshot.mkdir()
    names = ["scripts/forge_libffi_autonomous.py", "scripts/forge_simple_system.py"]
    names += [
        str(p.relative_to(ROOT))
        for p in (ROOT / "backend/packages/harness/deerflow/compile").glob("*.py")
    ]
    hashes = {}
    for name in names:
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    save(args.output / "source-sha256.json", hashes)
    save(
        args.output / "scope.json",
        dict(
            identity=IDENTITY,
            initial_plan=None,
            experience_bank=None,
            project_specific_hint=None,
            methods="P0＋初始工具执行约束＋规则路由＋原R2",
            attempts=1,
            automatic_retries=False,
            maximum_cost_usd="1.00",
            deadline_utc=auth["deadline_utc"],
            historical_exposure="已知libffi开发案例，非holdout，不回填E57",
        ),
    )
    from dotenv import load_dotenv

    load_dotenv(auth["credentials_env_file"], override=False)
    model = PlanThinkingDeepSeek(
        model="deepseek-flash",
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
        max_tokens=32768,
        max_retries=0,
        timeout=240,
        reasoning_effort="low",
        extra_body={"thinking": {"type": "enabled"}},
    )
    result = run_simple_system(
        task=task,
        reference=reference,
        source_archive=archive,
        output_root=args.output / "libffi",
        method="forge",
        model=model,
        accepted_models=MODELS,
        family=task.repository_url.lower(),
        deadline=auth["deadline_utc"],
        maximum_cost_usd="1.00",
        validation_scope="main_build",
        replay_seconds=900,
        state_router=BuildStateRouter(
            method="rule", directory=args.output / "state-routing"
        ),
        harness=PlanningHarness(name="P0", base_prompt_sha256=_digest(SIMPLE_PROMPT)),
        recovery_harness=recovery,
        enforce_planning_tools=True,
    )
    save(args.output / "summary.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
