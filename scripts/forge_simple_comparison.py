#!/usr/bin/env python3
"""简洁任务四方法48次比较；准备不读取凭据，付费运行必须绑定新授权。"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import signal
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from forge_build_simple_task import save
from forge_simple_cxx_reference import BASELINE, run_native_cxx
from forge_simple_system import METHODS, ROOT, BuildReference, PublicBuildTask, SimpleStateTargetBank, run_simple_system
from forge_typed_evidence import digest, seal

from deerflow.compile.operation_window import OperationWindow
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek
from deerflow.compile.plan_workflow import PlanContractError, _digest

IDENTITY = "cpp-build-simple-system-comparison-flash-v1"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
FIXTURE = ROOT / "benchmarks/fixtures/simple-system-comparison-v1/tasks.json"
BANK = Path("/home/yiwei/.codex/outputs/forge-experience-session-2026-11-02/richlab-route-v1/seed-bank.json")
PROJECTS = ("jsoncpp", "miniz", "pigz", "highwayhash", "libite", "libsrtp")
MODELS = ("DeepSeek-V4.1-Flash-1017", "deepseek-flash")
# 四个Williams顺序各用三次，位置和紧邻前序在12个项目/重复块中平衡。
ORDERS = ((0, 1, 3, 2), (1, 2, 0, 3), (2, 3, 1, 0), (3, 0, 2, 1))
SLOT_SECONDS, TEST_SECONDS, REPLAY_SECONDS = 2700, 180, 600
PREREG = "benchmarks/preregistrations/" + IDENTITY + ".md"
PRICING = dict(input_per_million_usd="0.30", output_per_million_usd="1.20", basis="沿用Flash全输入缓存未命中保守估费，不是账单", source="https://api-docs.deepseek.com/quick_start/pricing")


def load(path):
    return json.loads(Path(path).read_text())


def schedule():
    return [dict(slot=i * 4 + j + 1, project=PROJECTS[i % 6], repetition=i // 6 + 1, method=METHODS[m]) for i in range(12) for j, m in enumerate(ORDERS[i % 4])]


def runtime_files():
    paths = set()
    # 同时冻结当前已导入的本仓库依赖，以及运行时才动态加载的编译/模型模块。
    for module in list(sys.modules.values()):
        name = getattr(module, "__file__", None)
        if name and ".venv" not in Path(name).parts and Path(name).resolve().is_relative_to(ROOT) and name.endswith(".py"):
            paths.add(Path(name).resolve())
    for prefix in ("backend/packages/harness/deerflow/compile", "backend/packages/harness/deerflow/models"):
        paths.update((ROOT / prefix).glob("*.py"))
    paths.update(ROOT / p for p in (PREREG, "scripts/forge_simple_comparison.py", "scripts/forge_simple_cxx_reference.py", "scripts/forge_simple_system.py"))
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(paths)}


def candidate():
    fixture, bank = load(FIXTURE), load(BANK)
    return dict(
        identity=IDENTITY,
        issue=677,
        launch_state="prepared_requires_new_budget_and_time_authorization",
        kind="complete_system_comparison_development_projects",
        holdout=False,
        projects=fixture["projects"],
        schedule=schedule(),
        methods=list(METHODS),
        fixture_sha256=digest(FIXTURE),
        provider=dict(model="deepseek-flash", accepted_response_models=list(MODELS), reasoning_effort="low", thinking="enabled", max_tokens=32768, max_retries=0, http_timeout_seconds=240),
        pricing=PRICING,
        experience=dict(
            path=str(BANK),
            sha256=digest(BANK),
            source_families=sorted({s["family"] for s in bank["sources"]}),
            entries=len(bank["entries"]),
            historical_preparation_cost_usd=bank["preparation_cost_usd"],
            frozen=True,
            online_updates=False,
            exact_recipe_initially_available=False,
        ),
        timing=dict(
            slot_seconds=SLOT_SECONDS, main_agent_seconds=1200, command_seconds=180, author_test_seconds=TEST_SECONDS, replay_seconds=REPLAY_SECONDS, request_admission_seconds=600, cleanup_reserve_seconds=300, new_slot_admission_seconds=900
        ),
        limits=dict(proposed_maximum_cost_usd="10.00", proposed_hours=8, per_slot_cost_usd="1.00", per_slot_requests=96, per_slot_recorded_tokens=1_000_000),
        baseline=dict(path=str(BASELINE), files={p.relative_to(BASELINE).as_posix(): digest(p) for p in sorted((BASELINE / "src").rglob("*.py"))}),
        components=runtime_files(),
        package_versions={n: importlib.metadata.version(n) for n in ("langchain", "langchain-core", "langgraph", "langchain-deepseek", "openai")},
        boundary="六个已暴露项目，项目族与历史经验来源隔离；两重复不当12个独立项目。完整系统参考不是纯状态因果；无新提炼、无同项目命中，不在线更新库。",
    )


def validate(protocol):
    if protocol["identity"] != IDENTITY or protocol["schedule"] != schedule() or protocol["methods"] != list(METHODS):
        raise PlanContractError("正式身份或固定顺序变化")
    if digest(FIXTURE) != protocol["fixture_sha256"] or protocol["projects"] != load(FIXTURE)["projects"]:
        raise PlanContractError("固定任务变化")
    if digest(Path(protocol["experience"]["path"])) != protocol["experience"]["sha256"]:
        raise PlanContractError("经验种子变化")
    if [p["name"] for p in protocol["projects"]] != list(PROJECTS):
        raise PlanContractError("固定样本变化")
    for item in protocol["projects"]:
        task = PublicBuildTask.model_validate(item["task"])
        reference = BuildReference.model_validate(item["reference"])
        if reference.task_sha256 != _digest(task.model_dump(mode="json")) or digest(Path(item["source_archive"])) != task.source_archive_sha256:
            raise PlanContractError("任务/参考/原源码不一致：" + item["name"])
        if item["family"] in protocol["experience"]["source_families"]:
            raise PlanContractError("经验来源与评价项目族重叠")
    for name, expected in protocol["components"].items():
        if digest(ROOT / name) != expected:
            raise PlanContractError("固定组件变化：" + name)
    for name, expected in protocol["baseline"]["files"].items():
        if digest(Path(protocol["baseline"]["path"]) / name) != expected:
            raise PlanContractError("CXX社区源码变化：" + name)
    for name, version in protocol["package_versions"].items():
        if importlib.metadata.version(name) != version:
            raise PlanContractError("模型运行依赖版本变化：" + name)


def validate_authorization(auth, expected_sha, *, now=None):
    now = now or datetime.now(UTC)
    if auth.get("identity") != IDENTITY or auth.get("candidate_sha256") != expected_sha or not auth.get("user_reply"):
        raise PlanContractError("授权须绑定确切身份、候选SHA和本次用户答复")
    start, end = (datetime.fromisoformat(auth[k]) for k in ("authorized_at_utc", "deadline_utc"))
    if start.tzinfo is None or end.tzinfo is None or not start <= now < end or (end - start).total_seconds() > 8 * 3600:
        raise PlanContractError("新授权时窗无效或超出拟定8小时")
    cap = Decimal(str(auth["maximum_cost_usd"]))
    if not cap.is_finite() or not Decimal(0) < cap <= Decimal("10.00") or auth.get("automatic_retry") is not False:
        raise PlanContractError("需要不超过10美元硬上限、无自动重试")


def usage(row):
    u = row.get("agent_usage") or {}
    cost = u.get("estimated_cost_usd_completed_responses")
    if cost is None:
        raise PlanContractError("完成响应费用缺失，不允许记零")
    return dict(requests=u.get("model_requests", u.get("provider_requests", 0)), input_tokens=u.get("input_tokens", 0), output_tokens=u.get("output_tokens", 0), cost=Decimal(str(cost)), unknown=u.get("unknown_usage_requests", 0))


def global_stop(row, folder):
    if usage(row)["unknown"]:
        return "unknown_usage"
    if row.get("cleanup", {}).get("succeeded") is not True:
        return "cleanup_failure"
    events = folder / "agent/events.jsonl"
    if events.exists() and any(loads.get("event") == "model.identity_mismatch" for loads in (json.loads(line) for line in events.read_text().splitlines())):
        return "model_identity_mismatch"
    for response in (folder / "agent").glob("request-*.response.json"):
        if load(response).get("model") not in MODELS:
            return "model_identity_mismatch"
    return None


def execute(protocol, root, authorization, executor):
    """串行一次执行每个固定槽；失败保留，不补槽、不用本批成功方案喂后续重复。"""
    root.mkdir(parents=True, exist_ok=False)
    save(root / "protocol.json", protocol)
    save(root / "authorization.json", authorization)
    rows, stop, inflight = [], None, None
    cap = Decimal(authorization["maximum_cost_usd"])
    started = time.monotonic()
    try:
        for slot in protocol["schedule"]:
            total = sum((usage(row)["cost"] for row in rows), Decimal(0))
            if cap - total < Decimal("0.10"):
                stop = "shared_budget"
                break
            try:
                OperationWindow(authorization["deadline_utc"]).admit("new_slot", 900)
            except PlanContractError:
                stop = "deadline"
                break
            item = next(p for p in protocol["projects"] if p["name"] == slot["project"])
            folder = root / f"slot-{slot['slot']:02d}-{slot['project']}-{slot['method']}"
            save(root / "current-slot.json", slot)
            inflight = slot
            row = executor(slot=slot, item=item, folder=folder, available=min(Decimal("1.00"), cap - total), deadline=authorization["deadline_utc"])
            rows.append({**row, **slot})
            inflight = None
            save(root / "progress.json", rows)
            stop = global_stop(row, folder)
            if stop or sum((usage(r)["cost"] for r in rows), Decimal(0)) > cap:
                stop = stop or "shared_budget_exceeded"
                break
    except BaseException as exc:
        stop = f"runner_exception:{type(exc).__name__}"
        save(root / "runner-failure.json", dict(error_type=type(exc).__name__, error=str(exc)))
        raise
    finally:
        unseen = [{**s, "status": "unobserved_or_unclosed", "reason": stop} for s in protocol["schedule"][len(rows) :]]
        # 槽内部原始请求仍是异常/中断时的权威，不把未闭合槽的账单当零。
        known = sum((usage(r)["cost"] for r in rows), Decimal(0))
        save(
            root / "result.json",
            dict(
                identity=IDENTITY,
                rows=rows,
                unobserved=unseen,
                stop_reason=stop,
                completed_slots=len(rows),
                expected_slots=48,
                closed_slot_cost_usd=str(known),
                unclosed_slot=inflight,
                billing_complete=inflight is None and not any(usage(r)["unknown"] for r in rows),
                batch_wall_seconds=time.monotonic() - started,
            ),
        )
    return load(root / "result.json")


def paid_executor(protocol):
    # 仅由main在授权和冻结检查通过后创建；此处才允许读取现有Provider环境凭据。
    from forge_cxx_current_reference import SDKMeter, StopPaid
    from openai import OpenAI

    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise PlanContractError("缺少已授权DeepSeek环境凭据；不改现有接入")
    sdk = OpenAI(api_key=key, base_url="https://api.deepseek.com", max_retries=0, timeout=240)
    bank = SimpleStateTargetBank.load(Path(protocol["experience"]["path"]))

    class BoundedSDKMeter(SDKMeter):
        def request(self, call, kwargs):
            if self.requests >= 96 or self.input + self.output >= 1_000_000:
                raise StopPaid("单槽请求或Token停止阈值")
            return super().request(call, kwargs)

    def run(*, slot, item, folder, available, deadline):
        from datetime import timedelta

        end = min(datetime.fromisoformat(deadline), datetime.now(UTC) + timedelta(seconds=SLOT_SECONDS)).isoformat()
        common = dict(
            task=PublicBuildTask.model_validate(item["task"]),
            reference=BuildReference.model_validate(item["reference"]),
            source_archive=Path(item["source_archive"]),
            output_root=folder,
            maximum_cost_usd=str(available),
            deadline=end,
            author_test_seconds=TEST_SECONDS,
        )

        def alarm(_signum, _frame):
            raise TimeoutError("单槽运行时限；保留已发生请求与失败，不自动重试")

        old = signal.signal(signal.SIGALRM, alarm)
        signal.alarm(max(1, int((datetime.fromisoformat(end) - datetime.now(UTC)).total_seconds()) - 120))
        try:
            if slot["method"] == "cxxcrafter":
                with patch("forge_cxx_current_reference.SDKMeter", BoundedSDKMeter):
                    return run_native_cxx(**common, completion_call=sdk.chat.completions.create, baseline=Path(protocol["baseline"]["path"]))
            model = PlanThinkingDeepSeek(model="deepseek-flash", api_key=key, base_url="https://api.deepseek.com", max_tokens=32768, max_retries=0, timeout=240, reasoning_effort="low", extra_body={"thinking": {"type": "enabled"}})
            return run_simple_system(**common, method=slot["method"], model=model, accepted_models=MODELS, family=item["family"], bank=bank if slot["method"] == "forge_experience" else None, replay_seconds=REPLAY_SECONDS)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

    return run


def analyze(root):
    result, summaries = load(root / "result.json"), {}
    for method in METHODS:
        rows = [r for r in result["rows"] if r["method"] == method]
        summaries[method] = dict(
            planned=12,
            observed=len(rows),
            unobserved=12 - len(rows),
            primary_completed=sum(r.get("layers", {}).get("primary_build_completed") is True for r in rows),
            full_completed=sum(r.get("layers", {}).get("full_completed") is True for r in rows),
            requests=sum(usage(r)["requests"] for r in rows),
            estimated_cost_usd=str(sum((usage(r)["cost"] for r in rows), Decimal(0))),
            total_wall_seconds=sum(r.get("arm_total_wall_seconds", 0) for r in rows),
            author_tests=dict(Counter(r.get("layers", {}).get("author_tests", "unobserved") for r in rows)),
        )
    details = []
    for row in result["rows"]:
        folder = root / f"slot-{row['slot']:02d}-{row['project']}-{row['method']}"
        phase, phases, retrievals, reads = "initial", {}, 0, 0
        events = folder / "agent/events.jsonl"
        for event in (json.loads(line) for line in events.read_text().splitlines()) if events.exists() else []:
            if event["event"] == "agent.started":
                phase = "recovery" if event.get("recovery") else "tool_agent" if row["method"] == "strong_tool_agent" else "initial"
            elif event["event"] == "model.request_completed":
                bucket = phases.setdefault(phase, dict(requests=0, input_tokens=0, output_tokens=0))
                bucket["requests"] += 1
                bucket["input_tokens"] += event["input_tokens"]
                bucket["output_tokens"] += event["output_tokens"]
            elif event["event"] == "experience.retrieved":
                retrievals += 1
            elif event["event"] == "tool.started" and event.get("name") == "read_source":
                reads += 1
        for bucket in phases.values():
            bucket["estimated_cost_usd"] = str((Decimal(bucket["input_tokens"]) * Decimal("0.30") + Decimal(bucket["output_tokens"]) * Decimal("1.20")) / 1_000_000)
        details.append(
            dict(
                slot=row["slot"],
                project=row["project"],
                repetition=row["repetition"],
                method=row["method"],
                layers=row.get("layers"),
                timings=row.get("timings"),
                arm_total_wall_seconds=row.get("arm_total_wall_seconds"),
                agent_usage=row.get("agent_usage"),
                phase_usage=phases or None,
                source_reads=reads if events.exists() else None,
                experience_retrievals=retrievals if events.exists() else None,
            )
        )
    return dict(identity=IDENTITY, summary=summaries, slots=details, boundary="全部48计划槽分母保留；两重复按项目聚类。总体费用包含失败，成功配对耗时另作辅助，不在成功子集推断总体优势。经验历史制库费另列；CXX原生阶段未拆分则为null。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--check-prepared", action="store_true")
    group.add_argument("--run", action="store_true")
    group.add_argument("--analyze", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.analyze:
        print(json.dumps(analyze(args.analyze), ensure_ascii=False, indent=2))
        return 0
    if args.prepare:
        if MANIFEST.exists():
            raise PlanContractError("不覆盖已固定比较身份")
        value = candidate()
        validate(value)
        save(MANIFEST, value)
    else:
        value = load(MANIFEST)
        validate(value)
    if not args.run:
        print(json.dumps(dict(valid=True, identity=IDENTITY, candidate_sha256=digest(MANIFEST), slots=48, provider_calls=0, credentials_read=False)))
        return 0
    if args.authorization is None or args.output is None:
        raise PlanContractError("真实运行需要明确授权文件和独立新目录")
    auth = load(args.authorization)
    validate_authorization(auth, digest(MANIFEST))
    subprocess.run(["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    executor = paid_executor(value)
    try:
        execute(value, args.output, auth, executor)
    finally:
        if (args.output / "result.json").exists():
            save(args.output / "analysis.json", analyze(args.output))
            unknown = sum(usage(r)["unknown"] for r in load(args.output / "result.json")["rows"])
            seal(args.output, value, ROOT, unknown_usage_requests=unknown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
