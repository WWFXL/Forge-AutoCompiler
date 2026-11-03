#!/usr/bin/env python3
"""四组经验增量比较：固定来源、共享预算、真实失败保留。"""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import forge_build_experience_comparison as original
import forge_build_experience_route_comparison as route
from deerflow.compile.build_experience import ExperienceBank
from deerflow.compile.conditioned_experience import (
    ConditionedBank,
    ProcessExtraction,
    archive_facts,
    validate_process_extraction,
)

base, system, ROOT = original.base, original.system, original.ROOT
SESSION = Path(
    "/home/yiwei/.codex/outputs/forge-experience-improvement-session-2026-11-03"
)
OLD_BANK = route.SESSION / "seed-bank.json"
IDENTITY = "cpp-build-evidence-conditioned-experience-flash-v1"
EXTRACT_ID = "cpp-build-evidence-conditioned-distillation-richlab-v1"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREG = "benchmarks/preregistrations/" + IDENTITY + ".md"
OUTPUT = SESSION.parent / "forge-evidence-conditioned-experience-flash-v1"
METHODS = (
    "no_experience",
    "source_experience",
    "process_experience",
    "conditioned_experience",
)
PROMPT = """你是构建轨迹的离线经验提炼Agent。仅根据所给原始命令、失败反馈、方案与实际修订提炼最多两条经验。
优先解释具体失败过程：失败前状态→实际失败动作或被拒方案→反馈→实际修订→修订后观察；没有修订则observed_revision=null，不能虚构修复成功。
区分effective局部成功、ineffective实际无效、hypothesis未执行猜测；command_ids只能引用实际命令，evidence_ids可引用命令或过程观察。
不要重复Harness固定要求（全部测试、源码保护、精确交付、replay），除非有具体工具或依赖机制。不要把某个项目的选项、路径或target建议直接推广为通用配方。
给出可程序核对的少量必要适用信号applicability：required_files为通用构建输入的精确basename，如CMakeLists.txt/Makefile.am；declaration_terms为当前作者构建声明必须实际出现的字面词，如enable_testing、pkg_check_modules。不要把来源项目的专属选项作为所有项目的必要前提；没有必要信号可空。
error_markers仅用于确实需要当前失败反馈才适用的经验，列出错误中的短字面片段；无失败时不应使用的修复必须给出这个条件。所有条件列表取AND，error_markers内部取OR。
文字简洁，每条不超过约400中文字，不输出Markdown。只返回符合schema的JSON："""


def save(path, value):
    original.save(path, value)


def enrich_sources():
    sources = copy.deepcopy(base.load(route.SESSION / "sources.json"))
    for source in sources:
        folder = Path(source["source_folder"])
        observations = []
        for path in sorted(folder.glob("*/agent/plan-*.json")):
            plan = base.load(path)
            observations.append(
                dict(
                    evidence_id="plan:" + path.name,
                    kind="submitted_plan",
                    sha256=base.digest(path),
                    plan=plan,
                )
            )
        for path in sorted(
            folder.glob("*/.compile-sessions/*/*/build-plan/handoff-*.json")
        ):
            handoff = base.load(path)
            observations.append(
                dict(
                    evidence_id="handoff:" + path.name,
                    kind="execution_failure",
                    sha256=base.digest(path),
                    feedback={
                        k: v
                        for k, v in handoff.items()
                        if k not in ("recent_commands", "current_plan")
                    },
                    recent_commands=[
                        {
                            k: c.get(k)
                            for k in (
                                "command_id",
                                "role",
                                "exit_code",
                                "timed_out",
                                "output_tail",
                            )
                        }
                        for c in handoff.get("recent_commands", [])[-4:]
                    ],
                )
            )
        for path in sorted(folder.glob("*/agent/events.jsonl")):
            for index, line in enumerate(path.read_text().splitlines()):
                event = json.loads(line)
                if any(
                    t in event["event"]
                    for t in (
                        "candidate.rejected",
                        "recovery_disabled",
                        "model.contract",
                        "plan.rejected",
                    )
                ):
                    observations.append(
                        dict(
                            evidence_id=f"event:{index}",
                            kind="guard_or_recovery_observation",
                            event=event,
                        )
                    )
        row_index = int(source["source_id"].split("-")[-1])
        row = base.load(folder.parent / "result.json")["rows"][row_index - 1]
        source["observed_validation"]["source_unchanged"] = row.get(
            "fixed_sources_unchanged"
        )
        source["process_observations"] = observations
        source["terminal_failure"] = {
            k: row.get(k) for k in ("error_class", "error_message", "strict_completed")
        }
    return sources


def prepare():
    auth = base.load(SESSION / "authorization.json")
    if (
        auth["identities"] != [EXTRACT_ID, IDENTITY]
        or Decimal(auth["maximum_cost_usd"]) != 10
    ):
        raise ValueError("授权范围不符")
    sources = enrich_sources()
    save(SESSION / "sources.json", sources)
    tasks = base.load(ROOT / "benchmarks/fixtures/new-project-comparison-v1/tasks.json")
    projects = [p for p in tasks["projects"] if p["name"] in original.TARGETS]
    save(
        SESSION / "archive-facts.json",
        {p["name"]: archive_facts(p["source_archive"]) for p in projects},
    )
    candidate = copy.deepcopy(
        base.load(ROOT / "benchmarks/manifests" / (route.MAIN_ID + ".json"))
    )
    candidate.update(
        identity=IDENTITY,
        issue=660,
        kind="process_extraction_and_item_applicability_ablation",
        stage_max_cost_usd="10.00",
        projects=projects,
        schedule=[
            dict(project=name, repetition=r, method=METHODS[(j + i + 2 * (r - 1)) % 4])
            for r in (1, 2)
            for i, name in enumerate(original.TARGETS)
            for j in range(4)
        ],
        authorization_sha256=base.digest(SESSION / "authorization.json"),
        source_material_sha256=base.digest(SESSION / "sources.json"),
        old_bank=dict(path=str(OLD_BANK), sha256=base.digest(OLD_BANK)),
        facts_sha256=base.digest(SESSION / "archive-facts.json"),
        extraction_identity=EXTRACT_ID,
        holdout=False,
        treatment={
            METHODS[0]: "无经验",
            METHODS[1]: "原24条经验＋原来源级检索",
            METHODS[2]: "失败过程重提炼＋同一来源级检索",
            METHODS[3]: "与C同库＋逐条当前状态/静态信号检查",
        },
        interpretation_boundary="固定库，来源/评价项目族隔离；评价已有开发暴露。B-C为材料和表示组合，C-D为逐条检索/适用性组合，非等Token纯因果。四组共享command-v修复，不与旧版做修复因果比较。",
    )
    candidate["experience"] = dict(
        top_k=3,
        context_limit_bytes=12000,
        per_item_conditions="file/declaration/current_error; AND; unconfirmed permits abstention",
        bank_update=False,
    )
    paths = [
        *candidate["components"],
        "scripts/forge_build_conditioned_experience.py",
        "backend/packages/harness/deerflow/compile/conditioned_experience.py",
        PREREG,
    ]
    candidate["components"] = {p: base.digest(ROOT / p) for p in paths}
    save(MANIFEST, candidate)
    print(
        json.dumps(
            dict(prepared=True, slots=48, sources=len(sources), provider_calls=0)
        )
    )


def check_prepared():
    protocol = base.load(MANIFEST)
    for path, sha in protocol["components"].items():
        if base.digest(ROOT / path) != sha:
            raise ValueError("冻结组件变化：" + path)
    for name, field in [
        ("authorization.json", "authorization_sha256"),
        ("sources.json", "source_material_sha256"),
        ("archive-facts.json", "facts_sha256"),
    ]:
        if base.digest(SESSION / name) != protocol[field]:
            raise ValueError("冻结材料变化：" + name)
    if base.digest(OLD_BANK) != protocol["old_bank"]["sha256"]:
        raise ValueError("旧经验库变化")
    for item in protocol["projects"]:
        if (
            base.digest(Path(item["source_archive"]))
            != item["task"]["source_archive_sha256"]
        ):
            raise ValueError("源码归档变化")
    return protocol


def extract():
    check_prepared()
    # 复用已披露路由的单请求/用量保存，无SDK重试。
    original_prompt, original_schema, original_validator = (
        original.EXTRACT_PROMPT,
        original.Extraction,
        original.validate_extraction,
    )
    old_session = route.SESSION
    route.SESSION = SESSION
    original.EXTRACT_PROMPT, original.Extraction, original.validate_extraction = (
        PROMPT,
        ProcessExtraction,
        validate_process_extraction,
    )
    root = SESSION / "distillation"
    root.mkdir()
    entries, error = [], None
    try:
        for index, source in enumerate(base.load(SESSION / "sources.json"), 1):
            receipts = [base.load(p) for p in root.glob("source-*/usage.json")]
            if sum((Decimal(r["cost_usd"]) for r in receipts), Decimal(0)) + Decimal(
                "0.25"
            ) > Decimal("10"):
                raise ValueError("共享预算不足下一提炼请求")
            # 单输入200KB、输出8192Token，总计预留0.25美元。
            if len(json.dumps(source, ensure_ascii=False).encode()) > 200000:
                raise ValueError("提炼材料超出已保留的单响应费用范围")
            new, receipt = route.extract_one(source, root / f"source-{index}")
            entries.extend(new)
            print(
                json.dumps(
                    dict(source=source["source_id"], entries=len(new), usage=receipt),
                    ensure_ascii=False,
                ),
                flush=True,
            )
    except BaseException as exc:
        error = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        original.EXTRACT_PROMPT, original.Extraction, original.validate_extraction = (
            original_prompt,
            original_schema,
            original_validator,
        )
        route.SESSION = old_session
        receipts = [base.load(p) for p in root.glob("source-*/usage.json")]
        save(
            root / "result.json",
            dict(
                identity=EXTRACT_ID,
                observed=len(receipts),
                planned=12,
                entries=len(entries),
                error=error,
                cost_usd=str(
                    sum((Decimal(r["cost_usd"]) for r in receipts), Decimal(0))
                ),
                unknown_usage=sum(
                    base.load(p).get("unknown_usage", False)
                    for p in root.glob("source-*/failure.json")
                ),
            ),
        )
    save(
        SESSION / "seed-bank.json",
        dict(
            sources=base.load(SESSION / "sources.json"),
            entries=entries,
            preparation_cost_usd=base.load(root / "result.json")["cost_usd"],
            requested_model="gpt-6-astra",
            response_models=sorted({r["response_model"] for r in receipts}),
            backend_identity_verified=False,
        ),
    )


def run():
    from dotenv import load_dotenv

    protocol = check_prepared()
    auth = base.load(SESSION / "authorization.json")
    extraction = base.load(SESSION / "distillation/result.json")
    if (
        extraction["unknown_usage"]
        or extraction["error"]
        or extraction["observed"] != 12
    ):
        raise ValueError("提炼未完整结束，不能开启比较")
    subprocess.run(
        ["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True
    )
    OUTPUT.mkdir()
    protocol["deadline_utc"] = auth["deadline_utc"]
    save(OUTPUT / "protocol.json", protocol)
    save(OUTPUT / "authorization.json", auth)
    save(
        OUTPUT / "execution.json",
        dict(
            release=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True
            ).strip(),
            candidate_sha256=base.digest(MANIFEST),
            seed_bank_sha256=base.digest(SESSION / "seed-bank.json"),
        ),
    )
    load_dotenv(ROOT / ".env", override=False)
    model = base.PlanThinkingDeepSeek(
        model="deepseek-flash",
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
        max_tokens=32768,
        max_retries=0,
        timeout=240,
        reasoning_effort="low",
        extra_body={"thinking": {"type": "enabled"}},
    )
    old, new, facts = (
        base.load(OLD_BANK),
        base.load(SESSION / "seed-bank.json"),
        base.load(SESSION / "archive-facts.json"),
    )
    rows, reason = [], None
    paid = Decimal(extraction["cost_usd"])
    old_before = system.CommonTaskMeter._before_request

    def before(meter):
        if paid + Decimal(str(meter.cost_usd)) + Decimal("0.80") > Decimal("10"):
            raise base.PlanContractError("共享10美元预算不足下一完整响应")
        return old_before(meter)

    try:
        with patch.object(system.CommonTaskMeter, "_before_request", before):
            for index, slot in enumerate(protocol["schedule"], 1):
                if (
                    system.OperationWindow(auth["deadline_utc"]).remaining()
                    < system.SLOT_SECONDS
                ):
                    reason = "deadline_reservation"
                    break
                if paid + Decimal("0.80") > Decimal("10"):
                    reason = "budget_reservation"
                    break
                folder = OUTPUT / f"slot-{index}"
                folder.mkdir()
                data = old if slot["method"] in METHODS[:2] else new
                save(
                    folder / "experience-bank-used.json",
                    dict(
                        source_ids=[s["source_id"] for s in data["sources"]],
                        entries=data["entries"],
                    ),
                )
                bank = (
                    ConditionedBank(
                        data["sources"],
                        data["entries"],
                        facts,
                        folder / "selection.jsonl",
                    )
                    if slot["method"] == "conditioned_experience"
                    else ExperienceBank(data["sources"], data["entries"])
                )
                selected = {
                    **protocol,
                    "deadline_utc": min(
                        datetime.fromisoformat(auth["deadline_utc"]),
                        datetime.now(UTC)
                        + system.timedelta(seconds=system.SLOT_SECONDS),
                    ).isoformat(),
                }
                started = time.monotonic()
                try:
                    row = original.run_slot(selected, slot, folder, model, bank)
                except Exception as exc:
                    paths = list(folder.glob("*/agent/usage.json"))
                    usage = (
                        base.load(paths[0])
                        if len(paths) == 1
                        else dict(
                            model_requests=0,
                            estimated_cost_usd_completed_responses="0",
                            unknown_usage_requests=1,
                        )
                    )
                    row = {
                        **slot,
                        "strict_completed": False,
                        "agent_usage": usage,
                        "cleanup": dict(succeeded=False),
                        "error_class": type(exc).__name__,
                        "error_message": str(exc)[:1500],
                    }
                row["arm_total_wall_seconds"] = time.monotonic() - started
                rows.append(row)
                paid += Decimal(
                    str(row["agent_usage"]["estimated_cost_usd_completed_responses"])
                )
                save(OUTPUT / f"progress-{index}.json", row)
                print(
                    json.dumps(
                        dict(
                            slot=index,
                            **{
                                k: row.get(k)
                                for k in [
                                    "project",
                                    "method",
                                    "repetition",
                                    "strict_completed",
                                    "arm_total_wall_seconds",
                                    "error_message",
                                    "agent_usage",
                                ]
                            },
                            shared_cost_usd=str(paid),
                        ),
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                events = [
                    json.loads(line)
                    for p in folder.glob("*/agent/events.jsonl")
                    for line in p.read_text().splitlines()
                ]
                if (
                    row["agent_usage"]["unknown_usage_requests"]
                    or not row["cleanup"]["succeeded"]
                    or any(e["event"] == "model.identity_mismatch" for e in events)
                ):
                    reason = "unknown_usage_identity_or_cleanup"
                    break
    finally:
        save(
            OUTPUT / "result.json",
            dict(
                identity=IDENTITY,
                rows=rows,
                updates=[],
                unobserved_schedule=protocol["schedule"][len(rows) :],
                stop_reason=reason,
                known_estimated_cost_usd=str(paid - Decimal(extraction["cost_usd"])),
                distillation_cost_usd=extraction["cost_usd"],
                shared_cost_usd=str(paid),
            ),
        )
        base.seal(
            OUTPUT,
            protocol,
            ROOT,
            sum(r["agent_usage"]["unknown_usage_requests"] for r in rows),
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["prepare", "check-prepared", "extract", "run"]
    )
    args = parser.parse_args()
    {
        "prepare": prepare,
        "check-prepared": check_prepared,
        "extract": extract,
        "run": run,
    }[args.action]()


if __name__ == "__main__":
    main()
