#!/usr/bin/env python3
"""只读分析探索步骤与任务快照；旧运行再分析不新增实验分母。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from forge_analyze_experience import analyze, load


def exploration(events):
    phase, episode, request = "initial", 0, 0
    result = {p: Counter() for p in ("initial", "recovery")}
    repeats = {p: Counter() for p in result}
    selections, uses, request_phases = [], [], {}
    for event in events:
        kind = event["event"]
        if kind == "agent.started":
            phase = "recovery" if event.get("recovery") else "initial"
            episode += 1
            result[phase]["tasks"] += 1
        elif kind == "model.request_started":
            request = event["request_sequence"]
            request_phases[request] = phase
            result[phase]["requests"] += 1
        elif kind == "tool.started":
            result[phase]["tool_calls"] += 1
            name = event["name"]
            result[phase][name] += 1
            # 相同任务内同工具/同参数的重复；不把跨恢复任务读取当作冗余。
            repeats[phase][
                (
                    episode,
                    name,
                    json.dumps(event.get("args"), sort_keys=True, ensure_ascii=False),
                )
            ] += 1
        elif kind == "experience.retrieved":
            result[phase]["old_per_request_retrievals"] += 1
            result[phase]["old_retrieval_bytes"] += event["bytes"]
        elif kind == "experience.task_selected":
            selections.append(event)
            # 选经验发生在agent.started之前，用任务事件的stage判断其归属。
            selected_phase = "initial" if event["stage"] == "initial" else "recovery"
            result[selected_phase]["selections"] += 1
            result[selected_phase]["material_selections"] += bool(event["source_ids"])
        elif kind == "experience.context_used":
            uses.append(event)
            result[phase]["context_uses"] += 1
            result[phase]["context_bytes"] += event["bytes"]
    for name in result:
        result[name]["exact_repeated_tools_within_task"] = sum(
            n - 1 for n in repeats[name].values()
        )
    return dict(
        phases={k: dict(v) for k, v in result.items()},
        selections=selections,
        context_uses=uses,
        request_phases=request_phases,
    )


def read_exploration(root):
    protocol = load(root / "protocol.json")
    rows = load(root / "result.json")["rows"]
    slots = []
    for index, row in enumerate(rows, 1):
        folder = root / f"slot-{index}"
        events = [
            json.loads(line)
            for p in folder.glob("*/agent/events.jsonl")
            for line in p.read_text().splitlines()
        ]
        detail = exploration(events)
        for p in folder.glob("*/agent/response-*.json"):
            phase = detail["request_phases"].get(int(p.stem.split("-")[-1]))
            if phase is None:
                continue
            values = detail["phases"][phase]
            for message in load(p):
                usage = message.get("usage_metadata") or {}
                for field in ("input_tokens", "output_tokens"):
                    values[field] = values.get(field, 0) + usage.get(field, 0)
        task = next(
            p["task"] for p in protocol["projects"] if p["name"] == row["project"]
        )
        slots.append(
            dict(
                slot=index,
                project=row["project"],
                repetition=row["repetition"],
                method=row["method"],
                build_system=task["build_system"],
                complete=row["strict_completed"],
                **detail,
            )
        )
    summary = {}
    for method in dict.fromkeys(r["method"] for r in slots):
        summary[method] = {}
        for phase in ("initial", "recovery"):
            total = Counter()
            for row in slots:
                if row["method"] == method:
                    total.update(row["phases"][phase])
            summary[method][phase] = dict(total)
    return dict(
        identity=protocol["identity"],
        observed=len(slots),
        slots=slots,
        summary=summary,
        semantics="工具事件计数不等于语义冗余；相同参数重复只在同一次Agent任务内统计。旧结果再分析与原分母完全重叠。",
    )


def analyze_new(root, session):
    result = analyze(root)
    steps = read_exploration(root)
    extraction = load(session / "distillation/result.json")
    protocol = load(root / "protocol.json")
    old_cost = load(Path(protocol["old_bank"]["path"]))["preparation_cost_usd"]
    for row, detail in zip(result["slots"], steps["slots"], strict=True):
        row["exploration"] = detail["phases"]
        row["experience_task_selections"] = len(detail["selections"])
        row["experience_context_uses"] = len(detail["context_uses"])
    for method, summary in result["summary"].items():
        summary["exploration"] = steps["summary"][method]
        cost = (
            extraction["cost_usd"]
            if method == "action_experience"
            else old_cost
            if method == "source_experience"
            else "0"
        )
        summary["seed_preparation_cost_usd"] = str(cost)
        summary["deployment_cost_usd"] = str(
            Decimal(summary["cost_usd"]) + Decimal(cost)
        )
        for phase in ("initial", "recovery"):
            summary[f"{phase}_cost_usd"] = str(
                sum(
                    (
                        Decimal(r[f"{phase}_cost_usd"])
                        for r in result["slots"]
                        if r["method"] == method
                    ),
                    Decimal(0),
                )
            )
        # 新事件明确区分一次选择与逐请求上下文使用，不沿用旧retrieval字段。
        for key in list(summary):
            if "retriev" in key:
                del summary[key]
    result["strata"] = {
        stratum: {
            method: dict(
                planned=sum(
                    protocol["strata"][s["project"]] == stratum
                    and s["method"] == method
                    for s in protocol["schedule"]
                ),
                observed=sum(
                    protocol["strata"][r["project"]] == stratum
                    and r["method"] == method
                    for r in result["slots"]
                ),
                complete=sum(
                    protocol["strata"][r["project"]] == stratum
                    and r["method"] == method
                    and r["complete"]
                    for r in result["slots"]
                ),
                cost_usd=str(
                    sum(
                        (
                            Decimal(r["cost_usd"])
                            for r in result["slots"]
                            if protocol["strata"][r["project"]] == stratum
                            and r["method"] == method
                        ),
                        Decimal(0),
                    )
                ),
            )
            for method in result["summary"]
        }
        for stratum in sorted(set(protocol["strata"].values()))
    }
    result["distillation"] = extraction
    result["exploration_details"] = steps
    result["interpretation"] = protocol["interpretation_boundary"]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--session", type=Path)
    args = parser.parse_args()
    value = (
        analyze_new(args.root, args.session)
        if args.session
        else read_exploration(args.root)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(
        json.dumps(
            dict(identity=value["identity"], output=str(args.output)),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
