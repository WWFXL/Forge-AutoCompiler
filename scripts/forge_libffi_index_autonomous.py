#!/usr/bin/env python3
"""查询索引修复后libffi单次从零自主观察；默认零费用检查。"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from forge_libffi_dependency_guidance import load, save
from forge_libffi_dependency_guidance import material as previous_material
from forge_simple_system import ROOT, run_simple_system

from deerflow.compile.build_state_routing import BuildStateRouter
from deerflow.compile.offline_harness import PlanningHarness
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek
from deerflow.compile.plan_workflow import _digest
from deerflow.compile.recovery_environment import DIAGNOSTIC_VERSION
from deerflow.compile.simple_build_task import SIMPLE_GOAL, SIMPLE_PROMPT

IDENTITY = "cpp-build-libffi-index-autonomous-flash-v1"
IMAGE_ID = "sha256:d483ffa7b71b9545cff9555f6c92b6281a3f826ce006e2d09134cbdca92f8aa1"
MODELS = ("DeepSeek-V4.1-Flash-1017", "deepseek-flash")


def material():
    task, reference, archive, recovery = previous_material()
    task = type(task).model_validate({**task.model_dump(mode="json"), "goal": SIMPLE_GOAL, "plan_id": IDENTITY, "image_id": IMAGE_ID})
    reference = reference.model_copy(update={"task_sha256": _digest(task.model_dump(mode="json"))})
    return task, reference, archive, recovery


def validate_authorization(auth, *, now=None):
    """新单次身份的预算与时窗须在读取凭据和创建正式输出前有效。"""
    now = now or datetime.now(UTC)
    end = datetime.fromisoformat(auth["deadline_utc"])
    if auth["identity"] != IDENTITY or auth["maximum_cost_usd"] != "1.00" or auth["user_authorized"] is not True or end.tzinfo is None or not now < end <= now + timedelta(hours=1):
        raise ValueError("本身份需要有效的一美元、一小时单路径授权")


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
    validate_authorization(auth)
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
    names = [
        "scripts/forge_libffi_index_autonomous.py",
        "scripts/forge_libffi_dependency_guidance.py",
        "docker/compile/Dockerfile.dependency-index",
        "benchmarks/preregistrations/cpp-build-libffi-index-autonomous-flash-v1.md",
        "benchmarks/fixtures/recovery-harness-system-context-gpt61sol-v1/candidate.json",
        "benchmarks/fixtures/planning-tool-p4-comparison-v1/tasks.json",
        "scripts/forge_simple_system.py",
        "benchmarks/fixtures/dependency-diagnosis-guidance-v1/guidance.md",
    ]
    names += [str(p.relative_to(ROOT)) for p in (ROOT / "backend/packages/harness/deerflow/compile").glob("*.py")]
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
            methods="P0＋初始工具执行约束＋规则路由＋R2通用依赖诊断＋恢复容器查询",
            recovery_environment_tools=DIAGNOSTIC_VERSION,
            source_change_policy="posthoc-review-v1",
            image_id=IMAGE_ID,
            environment_change="新增apt-file及两依赖和Packages/Contents索引；不预装项目缺包；不与旧镜像作单变量因果比较",
            revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            recovery_harness=recovery.model_dump(mode="json"),
            recovery_harness_sha256=recovery.fingerprint(),
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
        state_router=BuildStateRouter(method="rule", directory=args.output / "state-routing"),
        harness=PlanningHarness(name="P0", base_prompt_sha256=_digest(SIMPLE_PROMPT)),
        recovery_harness=recovery,
        enforce_planning_tools=True,
    )
    save(args.output / "summary.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
