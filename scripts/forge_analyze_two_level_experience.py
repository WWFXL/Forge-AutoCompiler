#!/usr/bin/env python3
"""复用逐响应分析，补两层经验的匹配/目标变化及任务快照结果。"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from forge_analyze_action_experience import exploration
from forge_analyze_experience import analyze, load


def summarize(rows):
    return dict(
        observed=len(rows),
        complete=sum(r["complete"] for r in rows),
        requests=sum(r["requests"] for r in rows),
        cost_usd=str(sum((Decimal(r["cost_usd"]) for r in rows), Decimal(0))),
        wall_minutes=sum(r["wall_seconds"] for r in rows) / 60,
        initial_requests=sum(r["initial_requests"] for r in rows),
        recovery_requests=sum(r["recovery_requests"] for r in rows),
        initial_cost_usd=str(
            sum((Decimal(r["initial_cost_usd"]) for r in rows), Decimal(0))
        ),
        recovery_cost_usd=str(
            sum((Decimal(r["recovery_cost_usd"]) for r in rows), Decimal(0))
        ),
        skipped_planning=sum(bool(r["recipe_selections"]) for r in rows),
        verified_updates=sum(r["verified_update"] for r in rows),
        initial_reads=sum(
            r["exploration"]["phases"]["initial"].get("read_source", 0) for r in rows
        ),
        selections=sum(len(r["exploration"]["selections"]) for r in rows),
        material_selections=sum(
            bool(s["source_ids"]) for r in rows for s in r["exploration"]["selections"]
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = analyze(args.root)
    protocol = load(args.root / "protocol.json")
    for row in value["slots"]:
        folder = args.root / f"slot-{row['slot']}"
        events = [
            json.loads(line)
            for p in folder.glob("*/agent/events.jsonl")
            for line in p.read_text().splitlines()
        ]
        row["exploration"] = exploration(events)
        row["recipe_selections"] = [
            e for e in events if e["event"] == "recipe.selected"
        ]
        row["recipe_abstentions"] = [
            e for e in events if e["event"] == "recipe.abstained"
        ]
        row["verified_update"] = (folder / "verified-recipe-update.json").is_file()
        row["scenario"] = next(
            i["scenario"] for i in protocol["projects"] if i["name"] == row["project"]
        )
    value["two_level_summary"] = {
        m: summarize([r for r in value["slots"] if r["method"] == m])
        for m in value["summary"]
    }
    value["strata"] = {
        s: {
            m: summarize(
                [r for r in value["slots"] if r["method"] == m and r["scenario"] == s]
            )
            for m in value["summary"]
        }
        for s in dict.fromkeys(r["scenario"] for r in value["slots"])
    }
    value["by_project"] = {
        p: {
            m: summarize(
                [r for r in value["slots"] if r["method"] == m and r["project"] == p]
            )
            for m in value["summary"]
        }
        for p in dict.fromkeys(r["project"] for r in value["slots"])
    }
    value["validation_counts"] = {
        k: dict(Counter(r[k] for r in value["slots"]))
        for k in (
            "original_tests_status",
            "verification_status",
            "replay_status",
            "source_unchanged",
            "source_links_unchanged",
        )
    }
    value["total_tokens"] = sum(
        sum(r["response_tokens"].values()) for r in value["slots"]
    )
    value["new_distillation_cost_usd"] = "0"
    value["historical_library_distillation_cost_usd"] = "0.095129"
    value["limits"] = (
        "开发项目描述性比较；目标变化受控；无跨重复经验更新；旧制库/历史构建成本单列，不能由命中或追加推断泛化、自进化因果。"
    )
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "analysis.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    )
    columns = (
        "slot",
        "project",
        "scenario",
        "method",
        "repetition",
        "complete",
        "requests",
        "initial_requests",
        "recovery_requests",
        "cost_usd",
        "initial_cost_usd",
        "recovery_cost_usd",
        "wall_seconds",
        "verified_update",
        "original_tests_status",
        "verification_status",
        "replay_status",
        "error",
    )
    with (args.output / "slots.csv").open("w") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(value["slots"])
    print(
        json.dumps(
            dict(
                identity=value["identity"],
                summary=value["two_level_summary"],
                strata=value["strata"],
                stop_reason=value["stop_reason"],
                unobserved=len(value["unobserved"]),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
