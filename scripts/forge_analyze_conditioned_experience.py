#!/usr/bin/env python3
"""只读派生四组经验比较，报告条件拒绝和重复工具调用，不认定因果采用。"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from forge_analyze_experience import analyze, load


def extend(root: Path, session: Path) -> dict:
    result = analyze(root)
    extraction = load(session / "distillation/result.json")
    receipts = [
        load(p) for p in sorted((session / "distillation").glob("source-*/usage.json"))
    ]
    old_bank = load(Path(load(root / "protocol.json")["old_bank"]["path"]))
    result["distillation"] = dict(
        **extraction,
        wall_seconds=sum(r["wall_seconds"] for r in receipts),
        response_models=dict(Counter(r["response_model"] for r in receipts)),
        accepted_entries=len(load(session / "seed-bank.json")["entries"]),
        rejected_sources=[
            load(p) for p in (session / "distillation").glob("source-*/rejected.json")
        ],
    )
    result["selection_details"] = []
    for row in result["slots"]:
        folder = root / f"slot-{row['slot']}"
        selection = [
            json.loads(line)
            for p in folder.glob("selection.jsonl")
            for line in p.read_text().splitlines()
        ]
        events = [
            json.loads(line)
            for p in folder.glob("*/agent/events.jsonl")
            for line in p.read_text().splitlines()
        ]
        tools = [e for e in events if e["event"] == "tool.started"]
        counts = Counter(
            (e["name"], json.dumps(e.get("args"), sort_keys=True, ensure_ascii=False))
            for e in tools
        )
        sessions = list(folder.glob("*/.compile-sessions/*/*/session.json"))
        commands = load(sessions[0])["commands"] if len(sessions) == 1 else []
        command_counts = Counter(
            (c["role"], c["workdir"], c["command"]) for c in commands
        )
        invalid_calls = [
            dict(
                response=p.name,
                name=call.get("name"),
                error=str(call.get("error", ""))[:250],
            )
            for p in folder.glob("*/agent/response-*.json")
            for message in load(p)
            for call in message.get("invalid_tool_calls", [])
        ]
        row["invalid_tool_call_count"] = len(invalid_calls)
        row["invalid_tool_calls"] = invalid_calls
        row["exact_repeated_tool_calls"] = sum(n - 1 for n in counts.values())
        row["exact_repeated_execution_commands"] = sum(
            n - 1 for n in command_counts.values()
        )
        row["selection_calls"] = len(selection)
        row["selection_abstentions"] = sum(not s["selected_ids"] for s in selection)
        row["selected_experience_ids"] = sorted(
            {i for s in selection for i in s["selected_ids"]}
        )
        row["excluded_reasons"] = dict(
            Counter(
                reason
                for s in selection
                for d in s["decisions"]
                for reason in d["excluded_reasons"]
            )
        )
        row["condition_checks"] = dict(
            Counter(
                c["status"]
                for s in selection
                for d in s["decisions"]
                for c in d["checks"]
            )
        )
        row["model_format_failures"] = sum(
            e["event"] == "model.request_failed"
            and e.get("error_class") == "StructuredOutputValidationError"
            for e in events
        )
        row["source_guard_rejected"] = row["error"] == "原始源码或测试被修改"
        result["selection_details"].extend(
            dict(
                slot=row["slot"],
                project=row["project"],
                repetition=row["repetition"],
                **s,
            )
            for s in selection
        )
    for method, summary in result["summary"].items():
        rows = [r for r in result["slots"] if r["method"] == method]
        if method in ("process_experience", "conditioned_experience"):
            cost, seconds = (
                Decimal(extraction["cost_usd"]),
                sum(r["wall_seconds"] for r in receipts),
            )
        elif method == "source_experience":
            cost = Decimal(old_bank["preparation_cost_usd"])
            seconds = sum(
                load(p)["wall_seconds"]
                for p in Path(
                    load(root / "protocol.json")["old_bank"]["path"]
                ).parent.glob("distillation/source-*/usage.json")
            )
        else:
            cost, seconds = Decimal(0), 0
        summary["seed_preparation_cost_usd"] = str(cost)
        summary["deployment_cost_usd"] = str(Decimal(summary["cost_usd"]) + cost)
        summary["seed_preparation_seconds"] = seconds
        summary["deployment_minutes"] = summary["wall_minutes"] + seconds / 60
        summary["exact_repeated_tool_calls"] = sum(
            r["exact_repeated_tool_calls"] for r in rows
        )
        summary["exact_repeated_execution_commands"] = sum(
            r["exact_repeated_execution_commands"] for r in rows
        )
        summary["selection_calls"] = sum(r["selection_calls"] for r in rows)
        summary["selection_abstentions"] = sum(r["selection_abstentions"] for r in rows)
        summary["selected_experience_ids"] = sorted(
            {i for r in rows for i in r["selected_experience_ids"]}
        )
        for phase in ("initial", "recovery"):
            summary[f"{phase}_cost_usd"] = str(
                sum((Decimal(r[f"{phase}_cost_usd"]) for r in rows), Decimal(0))
            )
        summary["source_unchanged"] = dict(
            Counter(str(r["source_unchanged"]) for r in rows)
        )
        summary["source_links_unchanged"] = dict(
            Counter(str(r["source_links_unchanged"]) for r in rows)
        )
        summary["model_format_failures"] = sum(r["model_format_failures"] for r in rows)
        summary["source_guard_rejections"] = sum(
            r["source_guard_rejected"] for r in rows
        )
        summary["excluded_reasons"] = dict(
            sum((Counter(r["excluded_reasons"]) for r in rows), Counter())
        )
        summary["condition_checks"] = dict(
            sum((Counter(r["condition_checks"]) for r in rows), Counter())
        )
    result["by_project"] = {}
    for project in dict.fromkeys(r["project"] for r in result["slots"]):
        result["by_project"][project] = {}
        for method in result["summary"]:
            rows = [
                r
                for r in result["slots"]
                if r["project"] == project and r["method"] == method
            ]
            result["by_project"][project][method] = dict(
                observed=len(rows),
                complete=sum(r["complete"] for r in rows),
                requests=sum(r["requests"] for r in rows),
                cost_usd=str(sum((Decimal(r["cost_usd"]) for r in rows), Decimal(0))),
                wall_minutes=sum(r["wall_seconds"] for r in rows) / 60,
                retrieval_with_material=sum(r["retrieval_with_material"] for r in rows),
                selection_calls=sum(r["selection_calls"] for r in rows),
                selection_abstentions=sum(r["selection_abstentions"] for r in rows),
                selected_experience_ids=sorted(
                    {i for r in rows for i in r["selected_experience_ids"]}
                ),
            )
    methods = list(result["summary"])
    keys = {(r["project"], r["repetition"]) for r in result["slots"]}
    common = [
        key
        for key in sorted(keys)
        if all(
            any(
                (r["project"], r["repetition"]) == key
                and r["method"] == m
                and r["complete"]
                for r in result["slots"]
            )
            for m in methods
        )
    ]
    result["four_way_common_complete"] = dict(
        keys=[list(key) for key in common],
        count=len(common),
        summary={
            m: dict(
                cost_usd=str(
                    sum(
                        (
                            Decimal(r["cost_usd"])
                            for r in result["slots"]
                            if r["method"] == m
                            and (r["project"], r["repetition"]) in common
                        ),
                        Decimal(0),
                    )
                ),
                wall_minutes=sum(
                    r["wall_seconds"]
                    for r in result["slots"]
                    if r["method"] == m and (r["project"], r["repetition"]) in common
                )
                / 60,
            )
            for m in methods
        },
        semantics="按四组实际完整结果条件化，仅作辅助；不替代固定48分母，不含库制作分摊。",
    )
    result["new_shared_cost_usd"] = str(
        sum((Decimal(s["cost_usd"]) for s in result["summary"].values()), Decimal(0))
        + Decimal(extraction["cost_usd"])
    )
    result["analysis_checks"] = dict(
        response_cost_matches_all_slot_ledgers=result["cost_recomputed"],
        request_phases_complete=all(
            r["initial_requests"] + r["recovery_requests"] == r["requests"]
            for r in result["slots"]
        ),
        phase_costs_complete=all(
            Decimal(r["initial_cost_usd"]) + Decimal(r["recovery_cost_usd"])
            == Decimal(r["cost_usd"])
            for r in result["slots"]
        ),
        distillation_receipts_match_result=sum(
            (Decimal(r["cost_usd"]) for r in receipts), Decimal(0)
        )
        == Decimal(extraction["cost_usd"]),
    )
    result["cost_semantics"] = (
        "每个C/D部署分别计一次相同提炼；本轮共享新增仅付一次。B旧库制作费单列，非本轮新增；旧轨迹收集成本不重复计入。"
    )
    result["selection_semantics"] = (
        "逐请求静态信号与当前handoff筛选，日志含重复查询；检索/选择不等于实际采用或因果贡献。完全相同工具调用重复仅是探索代理指标，不自动视为无效。"
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = extend(args.root, args.session)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    with (args.output / "slots.csv").open("w") as file:
        columns = [
            k for k, v in result["slots"][0].items() if not isinstance(v, (list, dict))
        ]
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(result["slots"])
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
