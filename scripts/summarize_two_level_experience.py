#!/usr/bin/env python3
"""只读汇总两层经验的任务快照、分层验证和逐项目成本。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path


def summarize(value, root):
    groups, checks = {}, []
    for method in value["summary"]:
        rows = [r for r in value["slots"] if r["method"] == method]
        phases = {p: Counter() for p in ("initial", "recovery")}
        for row in rows:
            for phase, observations in row["exploration"]["phases"].items():
                phases[phase].update(observations)
            selections = row["exploration"]["selections"]
            uses = row["exploration"]["context_uses"]
            by_episode = {s["episode"]: s for s in selections}
            # 检查的是固定快照是否被复用，不把空检索或命中当效果。
            checks.append(
                dict(
                    slot=row["slot"],
                    one_selection_per_episode=len(by_episode) == len(selections),
                    fixed_context=all(
                        u["episode"] in by_episode
                        and u["context_sha256"]
                        == by_episode[u["episode"]]["context_sha256"]
                        for u in uses
                    ),
                    costs_match=row["response_cost_matches_ledger"],
                )
            )
        groups[method] = dict(
            phases={p: dict(c) for p, c in phases.items()},
            context_uses=sum(len(r["exploration"]["context_uses"]) for r in rows),
            nonempty_context_uses=sum(
                bool(u["bytes"]) for r in rows for u in r["exploration"]["context_uses"]
            ),
            context_bytes=sum(
                u["bytes"] for r in rows for u in r["exploration"]["context_uses"]
            ),
            selection_sources=[
                dict(
                    slot=r["slot"],
                    project=r["project"],
                    repetition=r["repetition"],
                    stage=s["stage"],
                    sources=s["source_ids"],
                    bytes=s["bytes"],
                )
                for r in rows
                for s in r["exploration"]["selections"]
            ],
            recipe_matches=dict(
                Counter(s["match"] for r in rows for s in r["recipe_selections"])
            ),
            cleanup=dict(Counter(r["cleanup"]["succeeded"] for r in rows)),
            online_plus_existing_library_cost_usd=str(
                Decimal(value["summary"][method]["cost_usd"])
                + (
                    Decimal("0.095129")
                    if method in ("source_retrieval", "state_target_retrieval")
                    else Decimal(0)
                )
            ),
            validation={
                k: dict(Counter(str(r[k]) for r in rows))
                for k in (
                    "original_tests_status",
                    "verification_status",
                    "replay_status",
                    "source_unchanged",
                    "source_links_unchanged",
                )
            },
        )
    partial_tests = []
    for row in value["slots"]:
        if row["project"] != "simdutf" or row["complete"]:
            continue
        folder = root / f"slot-{row['slot']}"
        for path in folder.glob(
            "*/.compile-sessions/*/*/workspace/repo/build/Testing/Temporary/LastTest.log.tmp"
        ):
            text = path.read_text(errors="replace")
            partial_tests.append(
                dict(
                    slot=row["slot"],
                    method=row["method"],
                    completed_passed_entries=text.count("Test Passed."),
                    completed_failed_entries=text.count("Test Failed."),
                    log=str(path),
                    semantics="部分日志中的完成条目；不是完整测试通过，不推断其余用例。",
                )
            )
    return dict(
        identity=value["identity"],
        groups=groups,
        checks=checks,
        all_snapshot_and_cost_checks=all(
            all(
                c[k]
                for k in ("one_selection_per_episode", "fixed_context", "costs_match")
            )
            for c in checks
        ),
        partial_test_observations=partial_tests,
        cost_semantics="只加既有跨项目库一次制库费；同项目源方案的历史构建获取费另见会话historical-recipe-source-costs.json，未在本字段计入。",
        note="本文件重复消费原运行；不增加分母，选择和固定快照不是方法效果。",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis", type=Path)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = summarize(json.loads(args.analysis.read_text()), args.root)
    with args.output.open("x") as handle:
        handle.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                identity=result["identity"],
                checks=result["all_snapshot_and_cost_checks"],
            )
        )
    )
