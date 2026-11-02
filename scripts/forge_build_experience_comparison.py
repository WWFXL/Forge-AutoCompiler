#!/usr/bin/env python3
"""经验提炼、三组复用与独立持续更新比较；复用现有真实构建底座。"""

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

import forge_build_system_comparison as system
from forge_build_common_harness import common_harness_interfaces
from langchain_core.messages import SystemMessage

from deerflow.compile.build_experience import (
    EXPERIENCE_PROMPT,
    ExperienceBank,
    Extraction,
    fingerprint,
    query_state,
    validate_extraction,
)
from deerflow.compile.goal_state import (
    GoalStateWorkflow,
    goal_state_planner,
)

base, ROOT = system.base, system.ROOT
SESSION = Path("/home/yiwei/.codex/outputs/forge-experience-session-2026-11-02")
MAIN_ID = "cpp-build-state-experience-comparison-flash-v1"
UPDATE_ID = "cpp-build-experience-update-comparison-flash-v1"
EXTRACT_ID = "cpp-build-state-experience-distillation-astra-v1"
TARGETS = ("jsoncpp", "pegtl", "inja", "highwayhash", "libsigcplusplus", "libsrtp")
METHODS = ("no_experience", "raw_trajectory", "structured_experience")
OUTPUTS = {
    MAIN_ID: SESSION.parent / "forge-state-experience-comparison-flash-v1",
    UPDATE_ID: SESSION.parent / "forge-experience-update-comparison-flash-v1",
}
PREREG = "benchmarks/preregistrations/cpp-build-state-experience-comparison-flash-v1.md"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


def trace_from(folder, row, source_id, task):
    paths = list(folder.glob("*/.compile-sessions/*/*/session.json"))
    if len(paths) != 1:
        raise ValueError("轨迹必须含唯一Session")
    session = base.load(paths[0])
    commands = []
    for command in session["commands"]:
        log = Path(command["log_path"]) if command.get("log_path") else None
        output = log.read_text(errors="replace") if log and log.is_file() else ""
        commands.append(
            {
                **{
                    k: command.get(k)
                    for k in (
                        "command_id",
                        "role",
                        "command",
                        "workdir",
                        "exit_code",
                        "timed_out",
                    )
                },
                "output_head": output[:250],
                "output_tail": output[-1200:],
                "full_log_sha256": base.digest(log) if log and log.is_file() else None,
            }
        )
    validation = dict(
        full_completed=row["strict_completed"],
        source_unchanged=row.get("source_unchanged"),
        source_links_unchanged=row.get("source_links_unchanged"),
        tests=[
            dict(
                command_id=c["command_id"],
                exit_code=c["exit_code"],
                timed_out=c["timed_out"],
            )
            for c in commands
            if c["role"] == "smoke"
        ],
        replay=[dict(status=r["status"]) for r in session.get("replay_attempts", [])],
        cleanup=row.get("cleanup"),
        error=row.get("error_message"),
    )
    trace = dict(
        source_id=source_id,
        family=row["project"],
        build_system=task["build_system"],
        source_folder=str(folder),
        session_sha256=base.digest(paths[0]),
        task=task,
        commands=commands,
        observed_validation=validation,
    )
    # 固定的原轨迹片段预算；失败与配置优先，保留完整原始证据指针。
    raw_commands = []
    order = sorted(
        commands,
        key=lambda c: (
            c["exit_code"] == 0,
            c["role"] not in ("configure", "dependency"),
        ),
    )
    for command in order:
        candidate = {
            k: command[k] for k in ("command_id", "role", "exit_code", "timed_out")
        }
        candidate.update(
            command=command["command"][:550],
            output_tail=command["output_tail"][-300:],
            excerpt=True,
        )
        if (
            len(json.dumps(raw_commands + [candidate], ensure_ascii=False).encode())
            <= 2800
        ):
            raw_commands.append(candidate)
    trace["raw_context"] = dict(
        commands=raw_commands,
        scope="deterministic_historical_trace_excerpts",
        omitted_commands=len(commands) - len(raw_commands),
    )
    trace["retrieval_text"] = " ".join(
        c["command"] + " " + c["output_tail"] for c in commands
    )
    return trace


def seed_sources():
    root = SESSION.parent / "forge-unified-system-comparison-flash-v1"
    result, protocol = (
        base.load(root / "result.json"),
        base.load(root / "protocol.json"),
    )
    sources = []
    for i, row in enumerate(result["rows"], 1):
        if row["method"] == "forge_state_workflow" and row["repetition"] == 1:
            task = next(
                p["task"] for p in protocol["projects"] if p["name"] == row["project"]
            )
            sources.append(trace_from(root / f"slot-{i}", row, f"E30-slot-{i}", task))
    root = SESSION.parent / "forge-tool-recovery-ablation-flash-v1"
    result, protocol = (
        base.load(root / "result.json"),
        base.load(root / "protocol.json"),
    )
    # 全部四条原失败，不按新实验收益选择经验来源。
    for i, row in enumerate(result["rows"], 1):
        if not row["strict_completed"]:
            task = next(
                p["task"] for p in protocol["projects"] if p["name"] == row["project"]
            )
            sources.append(trace_from(root / f"slot-{i}", row, f"E04-slot-{i}", task))
    if len(sources) != 12 or set(s["family"] for s in sources) & set(TARGETS):
        raise ValueError("种子数量或项目族隔离错误")
    return sources


def schedule(update=False):
    if update:
        return [
            dict(project=name, repetition=1, method=method)
            for i, name in enumerate(TARGETS)
            for method in (
                ("fixed_bank", "updating_bank")
                if i % 2
                else ("updating_bank", "fixed_bank")
            )
        ]
    return [
        dict(project=name, repetition=r, method=METHODS[j])
        for r in (1, 2)
        for i, name in enumerate(TARGETS)
        for j in base.ORDERS[(i + 3 * (r - 1)) % 6]
    ]


def prepare():
    SESSION.mkdir(exist_ok=False)
    auth = dict(
        user_authorized=True,
        authorized_at_utc="2026-11-02T15:42:54+00:00",
        deadline_utc="2026-11-02T23:42:54+00:00",
        target_cost_usd="20",
        authorized_overrun_to_finish_fixed_scope=True,
        maximum_comparisons=48,
        automatic_retry=False,
        identities=[EXTRACT_ID, MAIN_ID, UPDATE_ID],
        pricing={
            "astra_input_per_million_usd": "1",
            "astra_output_per_million_usd": "1",
            "basis": "用户2026-11-02明确提供每百万Token1美元，输入输出均按该费率估计，非服务商账单",
        },
        stop_rules=[
            "unknown_usage",
            "model_identity_mismatch",
            "cleanup_failure",
            "deadline",
        ],
        richlab_model="gpt-6-astra",
        build_model="deepseek-flash",
    )
    save(SESSION / "authorization.json", auth)
    sources = seed_sources()
    save(SESSION / "sources.json", sources)
    tasks = base.load(ROOT / "benchmarks/fixtures/new-project-comparison-v1/tasks.json")
    parent = base.load(system.MANIFEST)
    for identity in (MAIN_ID, UPDATE_ID):
        candidate = copy.deepcopy(parent)
        candidate.update(
            identity=identity,
            issue=658,
            kind="state_associated_experience_comparison"
            if identity == MAIN_ID
            else "fixed_vs_updating_experience_comparison",
            projects=[p for p in tasks["projects"] if p["name"] in TARGETS],
            source_index_contracts={
                n: tasks["source_index_contracts"][n] for n in TARGETS
            },
            schedule=schedule(identity == UPDATE_ID),
            seed_sources=dict(
                path=str(SESSION / "sources.json"),
                sha256=base.digest(SESSION / "sources.json"),
                families=sorted({s["family"] for s in sources}),
            ),
            holdout=False,
            stage_max_cost_usd="144",
            experience=dict(
                top_k=3,
                context_limit_bytes=12000,
                retrieval="shared_source_index_system_stage_lexical_overlap",
                online_model="deepseek-flash",
                extraction_model="gpt-6-astra",
            ),
            comparison_boundary="来源/评价项目族隔离；评价项目已开发暴露；原轨迹/结构化比较同来源和检索器，未单独隔离状态匹配因果。更新组从种子开始，不消费36槽结果，任务后仅用于后续不同项目。",
            selection_reason="复用现有七项目中的六项；FSE已知默认smoke和跨午夜产物边界，本轮不改变裁判亦不纳入。CMake3/Make1/Autotools2。",
            parent_manifest=dict(
                path=str(system.MANIFEST.relative_to(ROOT)),
                sha256=base.digest(system.MANIFEST),
            ),
        )
        candidate["components"].update(
            {
                p: base.digest(ROOT / p)
                for p in (
                    "scripts/forge_build_experience_comparison.py",
                    "backend/packages/harness/deerflow/compile/build_experience.py",
                    PREREG,
                )
            }
        )
        save(ROOT / "benchmarks/manifests" / (identity + ".json"), candidate)


EXTRACT_PROMPT = """你是构建轨迹的离线经验提炼Agent。只能读取所给真实轨迹，提炼最多两条可迁移到其他项目的经验。关注依赖、测试准备、配置状态与动作选择；不复制项目完整配方，不声称每个成功命令都有因果作用。
成功只说明实际观察范围；未执行测试/交付/replay为未观察，失败中的局部成功仍可描述。每条经验必须引用实际command_id，并说明前提和不适用条件。不要把特定项目开关当所有项目通用开关；未知原因写hypothesis，不得虚构证据。
只返回满足下列schema的JSON对象，不输出Markdown。文字字段尽量简洁，每条约500中文字以内。schema："""


def extract_one(source, folder):
    """一次真实Responses请求，无SDK重试；保存原响应后才解析经验。"""
    import tomllib
    from openai import OpenAI

    folder.mkdir()
    auth = base.load(SESSION / "authorization.json")
    system.OperationWindow(auth["deadline_utc"]).request()
    config = tomllib.loads(Path("/home/yiwei/.codex/config.toml").read_text())
    endpoint = config["model_providers"][config["model_provider"]]["base_url"]
    key = base.load(Path("/home/yiwei/.codex/auth.json"))["OPENAI_API_KEY"]
    payload = {
        k: v for k, v in source.items() if k not in ("raw_context", "retrieval_text")
    }
    kwargs = dict(
        model="gpt-6-astra",
        instructions=EXTRACT_PROMPT
        + json.dumps(Extraction.model_json_schema(), ensure_ascii=False),
        input=json.dumps(payload, ensure_ascii=False),
        max_output_tokens=8192,
        reasoning={"effort": "high"},
        store=False,
    )
    save(folder / "request.json", kwargs)
    started = time.monotonic()
    client = OpenAI(base_url=endpoint, api_key=key, timeout=240, max_retries=0)
    try:
        response = client.responses.create(**kwargs)
    except Exception as exc:
        save(
            folder / "failure.json",
            dict(
                error_class=type(exc).__name__,
                http_status=getattr(exc, "status_code", None),
                unknown_usage=True,
            ),
        )
        raise RuntimeError("经验提炼Provider异常，保留未知用量且不重试") from None
    finally:
        client.close()
    save(folder / "response.json", response.model_dump(mode="json"))
    usage = response.usage
    if not usage:
        raise RuntimeError("经验提炼返回未知用量")
    receipt = dict(
        model=response.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        cost_usd=str(Decimal(usage.total_tokens) / 1_000_000),
        wall_seconds=time.monotonic() - started,
        price_basis=auth["pricing"],
    )
    save(folder / "usage.json", receipt)
    if response.model != "gpt-6-astra":
        raise RuntimeError("经验提炼模型身份异常")
    try:
        entries = validate_extraction(json.loads(response.output_text), source)
    except (ValueError, TypeError) as exc:
        # 已知用量的内容错误不重试，不把此来源编造为成功经验。
        save(
            folder / "rejected.json",
            dict(error=str(exc), source_id=source["source_id"]),
        )
        entries = []
    save(folder / "entries.json", entries)
    return entries, receipt


def extract():
    root = SESSION / "distillation"
    root.mkdir()
    sources, entries, receipts = base.load(SESSION / "sources.json"), [], []
    try:
        for i, source in enumerate(sources, 1):
            new, receipt = extract_one(source, root / f"source-{i}")
            entries.extend(new)
            receipts.append(receipt)
            print(
                json.dumps(
                    dict(source=source["source_id"], entries=len(new), usage=receipt)
                ),
                flush=True,
            )
    finally:
        save(
            root / "result.json",
            dict(
                identity=EXTRACT_ID,
                observed=len(receipts),
                planned=len(sources),
                entries=len(entries),
                cost_usd=str(
                    sum((Decimal(r["cost_usd"]) for r in receipts), Decimal(0))
                ),
            ),
        )
    save(
        SESSION / "seed-bank.json",
        dict(
            sources=sources,
            entries=entries,
            preparation_cost_usd=str(
                sum((Decimal(r["cost_usd"]) for r in receipts), Decimal(0))
            ),
            creation="Astra from twelve fixed historical trajectories",
        ),
    )


def run_slot(protocol, slot, root, model, bank):
    item = next(i for i in protocol["projects"] if i["name"] == slot["project"])
    task = base.PlanTask.model_validate(item["task"])
    mode = {"no_experience": "none", "raw_trajectory": "raw"}.get(
        slot["method"], "structured"
    )

    class ExperienceMeter(system.CommonTaskMeter):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, item=item, **kwargs)
            original = self.packet

            def packet():
                current = original()
                state = query_state(task, current)
                context = bank.retrieve(
                    build_system=task.build_system,
                    family=item["name"],
                    stage=state["stage"],
                    text=state["text"],
                    mode=mode,
                )
                self.ledger.append(
                    "experience.retrieved",
                    stage=state["stage"],
                    mode=mode,
                    source_ids=context["sources"],
                    bytes=context["bytes"],
                    bank_sha256=fingerprint(
                        dict(sources=list(bank.sources), entries=bank.entries)
                    ),
                )
                return {**current, "historical_build_experience": context}

            self.packet = packet

        def wrap_model_call(self, request, handler):
            s = request.system_message
            return super().wrap_model_call(
                request.override(
                    system_message=SystemMessage(
                        content=(s.content if s else "") + EXPERIENCE_PROMPT
                    )
                ),
                handler,
            )

    with common_harness_interfaces():
        original = base.observed_module.observed_planner
        with (
            patch.object(base, "PreparationMeter", ExperienceMeter),
            patch.object(
                base, "execution_window", system.component.bounded.execution_window
            ),
            patch.object(base.prepared_module, "PreparedWorkflow", GoalStateWorkflow),
            patch.object(
                base.observed_module,
                "observed_planner",
                lambda *a, **kw: goal_state_planner(original(*a, **kw)),
            ),
        ):
            row = system.replication.run_slot(
                protocol=protocol,
                slot={**slot, "method": "model_plan_workflow"},
                root=root,
                model=model,
            )
    return {**row, **slot, "experience_mode": mode}


def run(identity):
    from dotenv import load_dotenv

    candidate = ROOT / "benchmarks/manifests" / (identity + ".json")
    protocol = base.load(candidate)
    auth = base.load(SESSION / "authorization.json")
    for name, digest in protocol["components"].items():
        if base.digest(ROOT / name) != digest:
            raise ValueError("冻结组件变化：" + name)
    for item in protocol["projects"]:
        if (
            base.digest(Path(item["source_archive"]))
            != item["task"]["source_archive_sha256"]
        ):
            raise ValueError("源码归档变化")
    subprocess.run(
        ["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True
    )
    root = OUTPUTS[identity]
    root.mkdir()
    protocol.update(deadline_utc=auth["deadline_utc"])
    save(root / "protocol.json", protocol)
    save(root / "authorization.json", auth)
    save(
        root / "execution.json",
        dict(
            release=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True
            ).strip(),
            candidate_sha256=base.digest(candidate),
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
    original_bank = base.load(SESSION / "seed-bank.json")
    evolving = copy.deepcopy(original_bank)
    rows = []
    updates = []
    reason = None
    try:
        for index, slot in enumerate(protocol["schedule"], 1):
            if (
                system.OperationWindow(auth["deadline_utc"]).remaining()
                < system.SLOT_SECONDS
            ):
                reason = "deadline_reservation"
                break
            folder = root / f"slot-{index}"
            folder.mkdir()
            bank_data = evolving if slot["method"] == "updating_bank" else original_bank
            save(
                folder / "experience-bank-used.json",
                dict(
                    source_ids=[s["source_id"] for s in bank_data["sources"]],
                    entries=bank_data["entries"],
                ),
            )
            started = time.monotonic()
            try:
                selected = {
                    **protocol,
                    "deadline_utc": min(
                        datetime.fromisoformat(auth["deadline_utc"]),
                        datetime.now(UTC)
                        + system.timedelta(seconds=system.SLOT_SECONDS),
                    ).isoformat(),
                }
                row = run_slot(
                    selected,
                    slot,
                    folder,
                    model,
                    ExperienceBank(bank_data["sources"], bank_data["entries"]),
                )
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
            save(root / f"progress-{index}.json", row)
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
                                "error_message",
                                "arm_total_wall_seconds",
                                "agent_usage",
                            ]
                        },
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
            if slot["method"] == "updating_bank":
                # 前36槽输出永不写入此库；本槽完成后才形成下一任务可读的更新。
                item = next(
                    i for i in protocol["projects"] if i["name"] == slot["project"]
                )
                trace = trace_from(folder, row, f"update-task-{index}", item["task"])
                new, receipt = extract_one(trace, root / f"update-{index}")
                evolving["sources"].append(trace)
                evolving["entries"].extend(new)
                updates.append(dict(after_slot=index, entries=len(new), usage=receipt))
                save(root / f"bank-after-{index}.json", evolving)
    finally:
        save(
            root / "result.json",
            dict(
                identity=identity,
                rows=rows,
                updates=updates,
                unobserved_schedule=protocol["schedule"][len(rows) :],
                stop_reason=reason,
                known_estimated_cost_usd=str(
                    sum(
                        (
                            Decimal(
                                str(
                                    r["agent_usage"][
                                        "estimated_cost_usd_completed_responses"
                                    ]
                                )
                            )
                            for r in rows
                        ),
                        Decimal(0),
                    )
                ),
                update_cost_usd=str(
                    sum((Decimal(r["usage"]["cost_usd"]) for r in updates), Decimal(0))
                ),
            ),
        )
        base.seal(
            root,
            protocol,
            ROOT,
            sum(r["agent_usage"]["unknown_usage_requests"] for r in rows),
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "extract", "main", "update"])
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "extract":
        extract()
    else:
        run(MAIN_ID if args.action == "main" else UPDATE_ID)


if __name__ == "__main__":
    main()
