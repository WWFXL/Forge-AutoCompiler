#!/usr/bin/env python3
"""修复共同方案出口后比较Flash/RichLab规划；恢复统一Flash，保留正式失败。"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import tomllib
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import forge_planning_comparison as parent
import forge_simple_comparison as shared
from forge_build_simple_task import save
from forge_typed_evidence import digest, seal
from langchain_openai import ChatOpenAI

from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.simple_build_experience import SimpleStateTargetBank
from deerflow.compile.simple_build_task import BuildReference, PublicBuildTask

ROOT = shared.ROOT
IDENTITY = "cpp-build-planner-model-comparison-v1"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREG = ROOT / "benchmarks/preregistrations" / (IDENTITY + ".md")
PLANNERS = ("flash", "richlab")
RICH_MODELS = ("gpt-5.6", "gpt-6-astra")
PRICES = {**{m: ("0.30", "1.20") for m in shared.MODELS}, **{m: ("1.00", "1.00") for m in RICH_MODELS}}


class RichLabPlanner(ChatOpenAI):
    """Responses接入；与Flash同用auto工具选择，不增加强制提交优势。"""

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return super().bind_tools(tools, tool_choice="auto" if tool_choice in ("any", "required") else tool_choice, **kwargs)


def schedule():
    rows = []
    for repeat in range(2):
        for index, project in enumerate(parent.PROJECTS):
            order = PLANNERS if (index + repeat) % 2 == 0 else PLANNERS[::-1]
            for planner in order:
                rows.append(dict(slot=len(rows) + 1, project=project, repetition=repeat + 1, method="forge_experience", planner=planner))
    return rows


def candidate():
    value = parent.candidate()
    value.update(
        identity=IDENTITY, issue=685, launch_state="authorized_by_current_user_with_self_imposed_small_cap",
        kind="paired_development_planner_route_comparison", schedule=schedule(), methods=["forge_experience"], planners=list(PLANNERS),
        providers=dict(
            flash=value.pop("provider"),
            richlab=dict(requested_model="gpt-6-astra", accepted_response_models=list(RICH_MODELS), backend_identity_verified=False, api="responses", reasoning_effort="low", max_tokens=32768, max_retries=0, http_timeout_seconds=240),
        ),
        pricing_by_model=PRICES,
        recovery=dict(model="deepseek-flash", accepted_response_models=list(shared.MODELS), same_for_both=True),
        limits=value["limits"] | dict(proposed_maximum_cost_usd="2.00", proposed_hours=2, per_slot_cost_usd="0.40", request_reserve_usd="0.12"),
        boundary="四个已开发暴露项目×两重复，比较经验Forge中的规划路由；恢复固定Flash。API分别为DeepSeek Chat与RichLab Responses，模型/服务/接口差异共同构成处理，不作官方Astra或一般模型强弱排名，不估计经验/状态独立增量。",
    )
    value.pop("pricing")
    value["planning"].update(body="single_complete_JSON_with_identical_schema", correction_budget="one_shared_across_tool_schema_body_and_invalid_JSON", raw_response="retained_before_parsing")
    value["components"].update({p.relative_to(ROOT).as_posix(): digest(p) for p in (Path(__file__).resolve(), PREREG)})
    return value


def validate(value):
    if value["identity"] != IDENTITY or value["schedule"] != schedule() or value["pricing_by_model"] != {k: list(v) for k, v in PRICES.items()}:
        raise PlanContractError("规划模型比较的身份、顺序或单价变化")
    fixture = {p["name"]: p for p in shared.load(shared.FIXTURE)["projects"]}
    if value["projects"] != [fixture[n] for n in parent.PROJECTS]:
        raise PlanContractError("公开任务或独立参考变化")
    if digest(shared.FIXTURE) != value["fixture_sha256"] or digest(Path(value["experience"]["path"])) != value["experience"]["sha256"]:
        raise PlanContractError("固定材料变化")
    for item in value["projects"]:
        if digest(Path(item["source_archive"])) != item["task"]["source_archive_sha256"] or item["family"] in value["experience"]["source_families"]:
            raise PlanContractError("源码变化或来源族重叠")
    for path, expected in value["components"].items():
        if digest(ROOT / path) != expected:
            raise PlanContractError("运行组件变化：" + path)
    for name, version in value["package_versions"].items():
        if shared.importlib.metadata.version(name) != version:
            raise PlanContractError("依赖版本变化：" + name)


def paid_executor(value):
    # 仅在main核对本轮明确授权、身份、价格与时窗后读取已有凭据。
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise PlanContractError("现有DeepSeek凭据不可用")
    config = tomllib.loads(Path("/home/yiwei/.codex/config.toml").read_text())
    endpoint = config["model_providers"][config["model_provider"]]["base_url"]
    rich_key = shared.load(Path("/home/yiwei/.codex/auth.json"))["OPENAI_API_KEY"]
    flash = PlanThinkingDeepSeek(model="deepseek-flash", api_key=key, base_url="https://api.deepseek.com", max_tokens=32768, max_retries=0, timeout=240, reasoning_effort="low", extra_body={"thinking": {"type": "enabled"}})
    richlab = RichLabPlanner(model="gpt-6-astra", api_key=rich_key, base_url=endpoint, use_responses_api=True, max_tokens=32768, max_retries=0, timeout=240, reasoning_effort="low", store=False)
    bank = SimpleStateTargetBank.load(Path(value["experience"]["path"]))

    def run(*, slot, item, folder, available, deadline):
        end = min(datetime.fromisoformat(deadline), datetime.now(UTC) + timedelta(seconds=shared.SLOT_SECONDS)).isoformat()

        def alarm(_signum, _frame):
            raise TimeoutError("单槽截止；保留正式失败，不自动重试")

        old = signal.signal(signal.SIGALRM, alarm)
        signal.alarm(max(1, int((datetime.fromisoformat(end) - datetime.now(UTC)).total_seconds()) - 120))
        try:
            return shared.run_simple_system(
                task=PublicBuildTask.model_validate(item["task"]), reference=BuildReference.model_validate(item["reference"]), source_archive=Path(item["source_archive"]), output_root=folder,
                method="forge_experience", model=flash if slot["planner"] == "flash" else richlab, accepted_models=shared.MODELS if slot["planner"] == "flash" else RICH_MODELS,
                family=item["family"], bank=bank, recovery_model=flash, recovery_accepted_models=shared.MODELS, pricing_by_model=value["pricing_by_model"],
                deadline=end, maximum_cost_usd=str(min(Decimal("0.40"), available)), author_test_seconds=shared.TEST_SECONDS, replay_seconds=shared.REPLAY_SECONDS,
            )
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

    return run


def analyze(root):
    result = shared.load(root / "result.json")
    details = []
    for row in result["rows"]:
        folder = root / f"slot-{row['slot']:02d}-{row['project']}-{row['method']}"
        events_path = folder / "agent/events.jsonl"
        events = [json.loads(line) for line in events_path.read_text().splitlines()] if events_path.exists() else []
        stages, revision = Counter(), 0
        costs = dict(initial=Decimal(0), recovery=Decimal(0))
        for event in events:
            if event["event"] == "agent.started":
                revision = event["revision"]
            if event["event"] == "model.cost_estimated":
                stage = "initial" if revision == 1 else "recovery"
                stages[stage] += 1
                costs[stage] += Decimal(event["cost_usd"])
        details.append(dict(
            **{k: row[k] for k in ("slot", "project", "repetition", "planner")},
            initial_delivered=any(e["event"] == "simple.proposal_accepted" and e["revision"] == 1 for e in events),
            format_rejections=sum(e["event"] == "simple.proposal_rejected" for e in events),
            output_channels=dict(Counter(e["channel"] for e in events if e["event"] == "simple.output_received")),
            initial_requests=stages["initial"], recovery_requests=stages["recovery"], initial_cost_usd=str(costs["initial"]), recovery_cost_usd=str(costs["recovery"]),
            response_models=dict(Counter(e["response_model"] for e in events if e["event"] == "model.cost_estimated")),
            source_reads=sum(e["event"] == "tool.started" and e.get("name") == "read_source" for e in events),
        ))
    summary = {}
    for planner in PLANNERS:
        rows = [r for r in result["rows"] if r["planner"] == planner]
        slots = [d for d in details if d["planner"] == planner]
        summary[planner] = dict(
            planned=8, observed=len(rows), initial_plans=sum(s["initial_delivered"] for s in slots),
            primary_completed=sum(r.get("layers", {}).get("primary_build_completed") is True for r in rows),
            full_completed=sum(r.get("layers", {}).get("full_completed") is True for r in rows),
            requests=sum(shared.usage(r)["requests"] for r in rows), estimated_cost_usd=str(sum((shared.usage(r)["cost"] for r in rows), Decimal(0))),
            total_wall_seconds=sum(r["arm_total_wall_seconds"] for r in rows), initial_planning_seconds=sum(r.get("timings", {}).get("initial_planning_seconds", 0) for r in rows),
            format_rejections=sum(s["format_rejections"] for s in slots), source_reads=sum(s["source_reads"] for s in slots), recovery_requests=sum(s["recovery_requests"] for s in slots),
        )
    return dict(identity=IDENTITY, summary=summary, slots=details, unobserved=result["unobserved"], boundary="开发项目路由比较，不作官方模型排名；未观察不回填，所有费用含失败和纠正。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--check-prepared", action="store_true")
    group.add_argument("--run", action="store_true")
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.prepare:
        if MANIFEST.exists():
            raise PlanContractError("不覆盖固定身份")
        value = json.loads(json.dumps(candidate()))
        validate(value)
        save(MANIFEST, value)
    else:
        value = shared.load(MANIFEST)
        validate(value)
    if not args.run:
        print(json.dumps(dict(identity=IDENTITY, candidate_sha256=digest(MANIFEST), slots=16, provider_calls=0)))
        return 0
    if args.authorization is None or args.output is None:
        raise PlanContractError("正式运行需要本轮授权与新输出路径")
    auth = shared.load(args.authorization)
    shared.validate_authorization(auth, digest(MANIFEST), identity=IDENTITY, maximum_hours=2)
    if Decimal(auth["maximum_cost_usd"]) > Decimal("2"):
        raise PlanContractError("本轮自行限定2美元，不续用旧预算")
    subprocess.run(["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    executor = paid_executor(value)
    try:
        shared.execute(value, args.output, auth, executor)
    finally:
        if (args.output / "result.json").exists():
            save(args.output / "analysis.json", analyze(args.output))
            result = shared.load(args.output / "result.json")
            print(json.dumps(seal(args.output, value, ROOT, unknown_usage_requests=sum(shared.usage(r)["unknown"] for r in result["rows"]) + bool(result.get("unclosed_slot"))), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
