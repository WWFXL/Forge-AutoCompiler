#!/usr/bin/env python3
"""历史轨迹→一次离线提案→固定H0/H1比较；准备与分析不读取凭据。"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import signal
import time
import tomllib
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import forge_simple_comparison as shared
from forge_build_simple_task import save
from forge_main_system_comparison import summarize
from forge_planner_model_comparison import RICH_MODELS, RichLabPlanner
from forge_typed_evidence import digest, seal
from langchain_core.messages import HumanMessage, SystemMessage

from deerflow.compile.build_state_routing import BuildStateRouter
from deerflow.compile.offline_harness import OPTIMIZER_PROMPT, HarnessProposal, PlanningHarness
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek
from deerflow.compile.plan_workflow import PlanContractError, _digest
from deerflow.compile.simple_build_task import SIMPLE_PROMPT, BuildReference, PublicBuildTask

ROOT = shared.ROOT
IDENTITY = "cpp-build-offline-harness-round1-flash-v1"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREG = ROOT / "benchmarks/preregistrations" / (IDENTITY + ".md")
CORPUS = ROOT / "benchmarks/fixtures/offline-harness-round1/corpus.json"
TASKS = ROOT / "benchmarks/fixtures/main-system-comparison-v1/tasks.json"
PROJECTS = ("double-conversion", "miniz", "libogg", "libsrtp", "xxhash", "pigz")
TRAIN_PROJECTS = ("jsoncpp", "highwayhash", "libite")
SOURCE_ROOT = Path("/home/yiwei/.codex/outputs")
SOURCES = (
    ("forge-simple-system-comparison-flash-v1", (1, 2, 27, 14, 37, 17)),
    ("forge-main-system-comparison-flash-v1", (1, 12, 19)),
)


def excerpt(value, limit=1200):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return dict(text=text[:limit], truncated=len(text) > limit)


def build_corpus():
    """只读选择九条代表轨迹；不复制私有裁判、凭据或模型隐藏推理。"""
    episodes = []
    for batch, slots in SOURCES:
        root = SOURCE_ROOT / batch
        rows = shared.load(root / "result.json")["rows"]
        for slot in slots:
            row = next(r for r in rows if r["slot"] == slot)
            if row["project"] not in TRAIN_PROJECTS:
                raise PlanContractError("来源项目角色变化")
            folder = root / f"slot-{slot:02d}-{row['project']}-{row['method']}"
            evidence, counts, frequencies, arguments = [], Counter(), Counter(), {}
            # 旧版本请求包可能只含重建后的Human上下文；工具事件才是跨版本共同来源。
            path = folder / "agent/events.jsonl"
            source_hash = digest(path)
            for index, event in enumerate(map(json.loads, path.read_text().splitlines()), 1):
                name = event.get("name")
                if name not in {"read_source", "list_source", "read_failure_log"}:
                    continue
                if event["event"] == "tool.started":
                    arguments[name] = event.get("args", {})
                    counts[name] += 1
                    frequencies[json.dumps(dict(tool=name, args=arguments[name]), ensure_ascii=False, sort_keys=True)] += 1
                elif event["event"] == "tool.completed":
                    content = event.get("result", {}).get("content", "")
                    actual_args = json.loads(content).get("read_request", arguments.get(name, {}))
                    evidence.append(
                        dict(
                            evidence_id=f"{batch}:{slot}:event:{index}",
                            kind="tool_feedback",
                            tool=name,
                            arguments=actual_args,
                            content=excerpt(content),
                            source_path=str(path),
                            source_sha256=source_hash,
                        )
                    )
            # 保留工具行动首尾与重复次数，显式标记中间片段省略。
            selected = evidence if len(evidence) <= 8 else evidence[:4] + evidence[-4:]
            responses = sorted((folder / "agent").glob("response-*.json"), key=lambda p: int(p.stem.split("-")[-1]))
            for path in responses[:2] + (responses[-1:] if len(responses) > 2 else []):
                messages = shared.load(path)
                visible = [dict(content=excerpt(m.get("content", ""), 600), tool_calls=m.get("tool_calls", []), invalid_tool_calls=m.get("invalid_tool_calls", [])) for m in messages if m.get("type") == "ai"]
                selected.append(dict(evidence_id=f"{batch}:{slot}:{path.stem}", kind="visible_response", content=excerpt(visible, 1800), source_path=str(path), source_sha256=digest(path)))
            result = folder / "result.json"
            selected.append(dict(evidence_id=f"{batch}:{slot}:outcome", kind="outcome", status=row.get("status"), layers=row.get("layers"), usage=row.get("agent_usage"), source_path=str(result), source_sha256=digest(result)))
            episodes.append(
                dict(
                    trajectory_id=f"{batch}:{slot}",
                    project=row["project"],
                    family=row["project"],
                    method=row["method"],
                    role="optimizer_development",
                    task=shared.load(folder / "common-public-task.json"),
                    tool_feedback_counts=dict(counts),
                    read_frequencies=[dict(**json.loads(key), count=count) for key, count in frequencies.most_common()],
                    omitted_tool_feedback=len(evidence) - min(8, len(evidence)),
                    evidence=selected,
                )
            )
    return dict(
        format="offline-harness-corpus-v1",
        role="development_only",
        training_projects=list(TRAIN_PROJECTS),
        evaluation_projects=list(PROJECTS),
        historical_source_cost_usd=str(sum((Decimal(e["evidence"][-1]["usage"]["estimated_cost_usd_completed_responses"]) for e in episodes), Decimal(0))),
        historical_source_cost_is_new_charge=False,
        known_exposure="所有项目已在历史开发实验出现；仅本轮优化输入按项目隔离，不称最终holdout",
        historical_repairs="H0已修复输出格式、容量和共同底座；不能以旧格式失败作H1的修复收益",
        episodes=episodes,
    )


def schedule():
    rows = []
    for repetition in (1, 2):
        for index, project in enumerate(PROJECTS):
            order = ("H0", "H1") if (index + repetition) % 2 else ("H1", "H0")
            for method in order:
                rows.append(dict(slot=len(rows) + 1, project=project, repetition=repetition, method=method))
    return rows


def candidate():
    projects = [p for p in shared.load(TASKS)["projects"] if p["name"] in PROJECTS]
    components = shared.runtime_files()
    for path in (Path(__file__).resolve(), ROOT / "scripts/forge_main_system_comparison.py", ROOT / "scripts/forge_planner_model_comparison.py", PREREG, CORPUS, TASKS):
        components[path.relative_to(ROOT).as_posix()] = digest(path)
    return dict(
        identity=IDENTITY,
        issue=697,
        state="prepared_no_paid_authorization",
        projects=projects,
        schedule=schedule(),
        methods=["H0", "H1"],
        validation_scope="main_build",
        holdout=False,
        baseline=PlanningHarness(name="H0", base_prompt_sha256=_digest(SIMPLE_PROMPT)).model_dump(mode="json"),
        corpus_sha256=digest(CORPUS),
        components=components,
        package_versions={name: importlib.metadata.version(name) for name in ("langchain", "langchain-core", "langgraph", "openai")},
        optimizer=dict(requested_model="gpt-6-astra", accepted_response_models=list(RICH_MODELS), identity_disclosed=True, price_per_million_input_and_output_usd="1.00", requests=1, max_tokens=8192),
        online=dict(model="deepseek-flash", accepted_response_models=list(shared.MODELS), thinking="enabled", reasoning_effort="low", max_retries=0, prices=shared.PRICING),
        maximum_cost_usd="10.00",
        maximum_hours=4,
        automatic_retry=False,
        maximum_comparison_slots=24,
        boundary="首轮只更新初始规划策略，恢复/工具/模型/状态路由/裁判共享；无经验库或精确方案跳过规划。提案在任何新评价结果前固定，所有比较轨迹在本轮结束前不反馈。",
    )


def validate(value):
    if value["identity"] != IDENTITY or value["schedule"] != schedule():
        raise PlanContractError("首轮身份或排期变化")
    if {p["name"] for p in value["projects"]} != set(PROJECTS):
        raise PlanContractError("评价项目变化")
    if set(TRAIN_PROJECTS) & set(PROJECTS):
        raise PlanContractError("优化与评价项目重叠")
    for path, expected in value["components"].items():
        if digest(ROOT / path) != expected:
            raise PlanContractError("准备后组件变化：" + path)
    for item in value["projects"]:
        task = PublicBuildTask.model_validate(item["task"])
        if digest(Path(item["source_archive"])) != task.source_archive_sha256 or BuildReference.model_validate(item["reference"]).task_sha256 != _digest(task.model_dump(mode="json")):
            raise PlanContractError("评价来源变化")
    for name, expected in value["package_versions"].items():
        if importlib.metadata.version(name) != expected:
            raise PlanContractError("运行依赖变化")
    PlanningHarness.model_validate(value["baseline"]).prompt(SIMPLE_PROMPT)


def optimize(value, output, model):
    """恰好一次请求；无响应/未知用量/不明模型/无效提案不自动重试。"""
    output.mkdir(parents=True, exist_ok=False)
    packet = dict(baseline=value["baseline"], base_prompt=SIMPLE_PROMPT, corpus=shared.load(CORPUS))
    if len((OPTIMIZER_PROMPT + json.dumps(packet, ensure_ascii=False)).encode()) > 180000:
        raise PlanContractError("离线提案材料超过本轮保守预留，不调用Provider")
    save(output / "request.json", dict(system_prompt=OPTIMIZER_PROMPT, packet=packet))
    started = time.monotonic()
    try:
        response = model.invoke([SystemMessage(content=OPTIMIZER_PROMPT), HumanMessage(content=json.dumps(packet, ensure_ascii=False))])
        save(output / "response.json", response.model_dump(mode="json"))
        usage = response.usage_metadata
        actual = response.response_metadata.get("model_name") or response.response_metadata.get("model")
        if not usage or any(not isinstance(usage.get(k), int) or usage[k] < 0 for k in ("input_tokens", "output_tokens")):
            raise PlanContractError("离线提案用量未知，停止付费")
        if usage.get("total_tokens") != usage["input_tokens"] + usage["output_tokens"]:
            raise PlanContractError("离线提案用量不一致，停止付费")
        accounting = dict(
            model_requests=1,
            actual_response_model=actual,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            estimated_cost_usd_completed_responses=str(Decimal(usage["input_tokens"] + usage["output_tokens"]) / 1_000_000),
            unknown_usage_requests=0,
        )
        save(output / "usage.json", accounting)
        if actual not in value["optimizer"]["accepted_response_models"]:
            raise PlanContractError("离线响应模型异常，停止付费")
        proposal = HarnessProposal.model_validate(json.loads(response.text))
        harness = proposal.materialize(PlanningHarness.model_validate(value["baseline"]), packet["corpus"])
        save(output / "proposal.json", proposal.model_dump(mode="json"))
        save(output / "harness.json", harness.model_dump(mode="json"))
        return harness, accounting
    except BaseException as error:
        save(output / "failure.json", dict(type=type(error).__name__, message="离线提案未完成；原响应与用量文件保留，不自动重试", unknown_usage=not (output / "usage.json").exists()))
        raise
    finally:
        save(output / "timing.json", dict(wall_seconds=time.monotonic() - started))


def executor(harnesses, model):
    def run(*, slot, item, folder, available, deadline):
        end = min(datetime.fromisoformat(deadline), datetime.now(UTC) + timedelta(seconds=1200)).isoformat()

        def alarm(_signum, _frame):
            raise TimeoutError("首轮单槽截止；保留原失败")

        previous = signal.signal(signal.SIGALRM, alarm)
        signal.alarm(max(1, int((datetime.fromisoformat(end) - datetime.now(UTC)).total_seconds()) - 90))
        try:
            return shared.run_simple_system(
                task=PublicBuildTask.model_validate(item["task"]),
                reference=BuildReference.model_validate(item["reference"]),
                source_archive=Path(item["source_archive"]),
                output_root=folder,
                method="forge",
                model=model,
                accepted_models=shared.MODELS,
                family=item["family"],
                deadline=end,
                maximum_cost_usd=str(min(Decimal("0.40"), available)),
                validation_scope="main_build",
                replay_seconds=600,
                state_router=BuildStateRouter(method="rule", directory=folder / "state-routing"),
                harness=harnesses[slot["method"]],
            )
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)

    return run


def analyze(root):
    usage_path = root / "optimizer/usage.json"
    usage = shared.load(usage_path) if usage_path.exists() else None
    if not (root / "comparison/result.json").exists():
        return dict(
            identity=IDENTITY, status="no_change" if (root / "no-change.json").exists() else "optimizer_not_completed", optimizer=usage, planned_comparisons=24, observed_comparisons=0, unobserved_comparisons=24, treatment_effect=None
        )
    result = shared.load(root / "comparison/result.json")
    arms = {method: summarize([r for r in result["rows"] if r["method"] == method], 12) for method in ("H0", "H1")}
    optimizer_cost = Decimal(usage["estimated_cost_usd_completed_responses"])
    source_cost = Decimal(shared.load(CORPUS)["historical_source_cost_usd"])
    details = []
    for row in result["rows"]:
        folder = root / "comparison" / f"slot-{row['slot']:02d}-{row['project']}-{row['method']}"
        events = folder / "agent/events.jsonl"
        phase, phases, seen = "initial", {}, set()
        for event in map(json.loads, events.read_text().splitlines()) if events.exists() else []:
            if event["event"] == "agent.started":
                phase = "recovery" if event.get("recovery") else "initial"
            bucket = phases.setdefault(phase, dict(requests=0, source_reads=0, exact_repeat_reads=0, accepted_proposals=0, corrections=0))
            if event["event"] == "model.request_completed":
                bucket["requests"] += 1
            elif event["event"] == "simple.proposal_accepted":
                bucket["accepted_proposals"] += 1
                bucket["corrections"] += event["corrections"]
            elif event["event"] == "tool.started" and event.get("name") == "read_source":
                key = (phase, _digest(event.get("args", {})))
                bucket["source_reads"] += 1
                bucket["exact_repeat_reads"] += key in seen
                seen.add(key)
        details.append(dict(slot=row["slot"], project=row["project"], repetition=row["repetition"], method=row["method"], status=row["status"], layers=row.get("layers"), phases=phases, timings=row.get("timings")))
    return dict(
        identity=IDENTITY,
        arms=arms,
        slots=details,
        optimizer=usage,
        historical_source_cost_usd=str(source_cost),
        h1_deployment_cost_usd=str(optimizer_cost + Decimal(arms["H1"]["estimated_cost_usd"])),
        h1_with_all_historical_source_cost_usd=str(source_cost + optimizer_cost + Decimal(arms["H1"]["estimated_cost_usd"])),
        optimizer_wall_seconds=shared.load(root / "optimizer/timing.json")["wall_seconds"],
        total_known_cost_usd=str(Decimal(usage["estimated_cost_usd_completed_responses"]) + sum((shared.usage(r)["cost"] for r in result["rows"]), Decimal(0))),
        unobserved=result["unobserved"],
        boundary="开发项目上的首轮候选比较，不证明最终泛化或持续改进。旧结果不替换；小收益、混合和退化均报告；第二轮需另固定版本。重复读取仅描述相同读取参数，不自动称无用。",
    )


def run_paid(value, output, auth):
    # 调用者已先验证确切身份、当前授权及组件；到此才读取既有凭据。
    from dotenv import load_dotenv

    load_dotenv(auth["credentials_env_file"], override=False)
    config = tomllib.loads(Path("/home/yiwei/.codex/config.toml").read_text())
    endpoint = config["model_providers"][config["model_provider"]]["base_url"]
    rich_key = shared.load(Path("/home/yiwei/.codex/auth.json"))["OPENAI_API_KEY"]
    rich = RichLabPlanner(model="gpt-6-astra", api_key=rich_key, base_url=endpoint, use_responses_api=True, max_tokens=8192, max_retries=0, timeout=240, reasoning_effort="low", store=False)
    save(output / "authorization.json", auth)
    h1, usage = optimize(value, output / "optimizer", rich)
    h0 = PlanningHarness.model_validate(value["baseline"])
    if h1.fingerprint() == h0.fingerprint():
        save(output / "no-change.json", dict(reason="优化Agent未提出有依据的变化，不启动重复比较"))
        return
    remaining = Decimal(auth["maximum_cost_usd"]) - Decimal(usage["estimated_cost_usd_completed_responses"])
    if remaining < Decimal("0.10") or datetime.now(UTC) >= datetime.fromisoformat(auth["deadline_utc"]):
        raise PlanContractError("提案后剩余预算或时窗不足")
    save(output / "frozen-harnesses.json", {"H0": h0.model_dump(mode="json"), "H1": h1.model_dump(mode="json"), "frozen_before_first_evaluation": True})
    flash = PlanThinkingDeepSeek(
        model="deepseek-flash", api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com", max_tokens=32768, max_retries=0, timeout=240, reasoning_effort="low", extra_body={"thinking": {"type": "enabled"}}
    )
    effective = auth | dict(maximum_cost_usd=str(remaining), optimizer_cost_already_charged_usd=usage["estimated_cost_usd_completed_responses"])
    try:
        shared.execute(value, output / "comparison", effective, executor({"H0": h0, "H1": h1}, flash))
    finally:
        if (output / "comparison/result.json").exists():
            save(output / "analysis.json", analyze(output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--check-prepared", action="store_true")
    group.add_argument("--run", action="store_true")
    group.add_argument("--analyze", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--authorization", type=Path)
    args = parser.parse_args()
    if args.analyze:
        print(json.dumps(analyze(args.analyze), ensure_ascii=False, indent=2))
        return
    if args.prepare:
        if MANIFEST.exists() or CORPUS.exists():
            raise PlanContractError("已有准备材料不覆盖；新轮次另建身份")
        CORPUS.parent.mkdir(parents=True, exist_ok=True)
        save(CORPUS, build_corpus())
        save(MANIFEST, candidate())
    value = shared.load(MANIFEST)
    validate(value)
    if not args.run:
        print(json.dumps(dict(valid=True, identity=IDENTITY, candidate_sha256=digest(MANIFEST), trajectories=9, comparison_slots=24, provider_calls=0, credentials_read=False)))
        return
    if args.authorization is None or args.output is None:
        raise PlanContractError("需要本轮有效授权和独立输出目录")
    auth = shared.load(args.authorization)
    shared.validate_authorization(auth, digest(MANIFEST), identity=IDENTITY, maximum_hours=4)
    if Decimal(auth["maximum_cost_usd"]) < Decimal("0.20"):
        raise PlanContractError("不足一次离线提案的保守预留")
    shared.OperationWindow(auth["deadline_utc"]).admit("offline_optimizer", 300)
    # 在try外原子占用新目录；拒绝重用时不能触碰已有结果或封存。
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        run_paid(value, args.output, auth)
    finally:
        if args.output.exists():
            comparison = shared.load(args.output / "comparison/result.json") if (args.output / "comparison/result.json").exists() else None
            unknown = sum(shared.usage(r)["unknown"] for r in comparison["rows"]) + int(comparison.get("unclosed_slot") is not None) if comparison else 0
            if (args.output / "optimizer/request.json").exists() and not (args.output / "optimizer/usage.json").exists():
                unknown += 1
            if not (args.output / "analysis.json").exists():
                save(args.output / "analysis.json", analyze(args.output))
            save(args.output / "pipeline-status.json", dict(identity=IDENTITY, comparison_started=comparison is not None, unknown_usage_requests=unknown, no_automatic_retry=True))
            seal(args.output, value, ROOT, unknown_usage_requests=unknown)


if __name__ == "__main__":
    main()
