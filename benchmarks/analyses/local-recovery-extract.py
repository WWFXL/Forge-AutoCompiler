"""只读提取两批局部恢复比较；运行后核对计量与终态，不改冻结证据。"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend/packages/harness")]
runner = importlib.import_module("forge_build_local_recovery_comparison")


def summarize(rows):
    return {
        "observed": len(rows),
        "complete": sum(d["strict_completed"] for d in rows),
        "requests": sum(d["agent_usage"]["model_requests"] for d in rows),
        "tokens": sum(d["agent_usage"]["recorded_tokens"] for d in rows),
        "new_cost_usd": str(
            sum(
                (
                    Decimal(
                        str(d["agent_usage"]["estimated_cost_usd_completed_responses"])
                    )
                    for d in rows
                ),
                Decimal(0),
            )
        ),
        "total_with_historical_cost_usd": str(
            sum(
                (Decimal(d["comparable_total_estimated_cost_usd"]) for d in rows),
                Decimal(0),
            )
        ),
        "wall_seconds": sum(d["arm_total_wall_seconds"] for d in rows),
        "recovery_episodes": sum(d["recovery_episodes"] for d in rows),
        "local_returns": sum(d["local_returns"] for d in rows),
        "local_commands": sum(d["local_commands"] for d in rows),
        "build_executions": sum(d["command_counts"]["build"] for d in rows),
        "repeated_build_executions": sum(d["repeated_build_executions"] for d in rows),
        "configure_executions": sum(d["command_counts"]["configure"] for d in rows),
        "repeated_configure_executions": sum(
            d["repeated_configure_executions"] for d in rows
        ),
    }


def extract(raw, expected):
    result = runner.base.load(raw / "result.json")
    protocol = runner.base.load(raw / "protocol.json")
    assert result["lifecycle_complete"]
    assert len(protocol["schedule"]) == expected
    assert len(result["rows"]) + len(result["unobserved_schedule"]) == expected
    assert result["unobserved_schedule"] == protocol["schedule"][len(result["rows"]) :]
    analysis = runner.analyze(raw)
    analysis.update(
        raw_root=str(raw),
        release=runner.base.load(raw / "execution.json")["release"],
        inventory=runner.base.load(raw / "seal.json"),
        interpretation_boundary=protocol["interpretation_boundary"],
    )
    for number, (row, detail) in enumerate(
        zip(result["rows"], analysis["slots"], strict=True), 1
    ):
        assert all(
            row[k] == protocol["schedule"][number - 1][k]
            for k in ("project", "case_id", "repetition", "method")
        )
        folder = raw / f"slot-{number}"
        state = runner.base.load(
            next(folder.glob("*/.compile-sessions/*/*/session.json"))
        )
        events = [
            json.loads(line)
            for path in folder.glob("*/agent/events.jsonl")
            for line in path.read_text().splitlines()
        ]
        requests = [e for e in events if e["event"] == "model.request_completed"]
        assert len(requests) == row["agent_usage"]["model_requests"]
        assert row["agent_usage"]["unknown_usage_requests"] == 0
        assert (
            sum(e["input_tokens"] + e["output_tokens"] for e in requests)
            == row["agent_usage"]["recorded_tokens"]
        )
        detail.update(
            slot=number,
            source_unchanged=row.get("fixed_sources_unchanged"),
            configuration_class="deviated"
            if row["case_id"].endswith("-deviated")
            else "satisfied",
            command_seconds_by_role={
                role: sum(
                    c.get("duration_seconds") or 0
                    for c in state["commands"]
                    if c["role"] == role
                )
                for role in detail["command_counts"]
            },
            replay_seconds=sum(
                a.get("duration_seconds") or 0 for a in state.get("replay_attempts", [])
            ),
            local_target_roles=[
                e["target_role"]
                for e in events
                if e["event"] == "local_recovery.returned"
            ],
            failure_category="completed"
            if row["strict_completed"]
            else "context_material_limit"
            if "100000" in (row.get("error_message") or "")
            else "see_error_and_report",
        )
        assert (
            row["cleanup"]["succeeded"]
            and detail["source_unchanged"]
            and detail["source_links_unchanged"]
        )
        if row["strict_completed"]:
            assert (
                state["status"] == "completed" and detail["replay_status"] == "passed"
            )
    analysis["summary"] = {
        method: summarize([d for d in analysis["slots"] if d["method"] == method])
        for method in runner.METHODS
    }
    for method, summary in analysis["summary"].items():
        summary["planned"] = sum(d["method"] == method for d in protocol["schedule"])
        summary["unobserved"] = sum(
            d["method"] == method for d in result["unobserved_schedule"]
        )
    analysis["strata"] = {
        category: {
            method: summarize(
                [
                    d
                    for d in analysis["slots"]
                    if d["method"] == method and d["configuration_class"] == category
                ]
            )
            for method in runner.METHODS
        }
        for category in ("deviated", "satisfied")
    }
    analysis["pairs"] = []
    for case in protocol["cases"]:
        for repetition in (1, 2):
            rows = {
                d["method"]: d
                for d in analysis["slots"]
                if d["case_id"] == case["case_id"] and d["repetition"] == repetition
            }
            if len(rows) == 2 and all(d["strict_completed"] for d in rows.values()):
                analysis["pairs"].append(
                    {
                        "case_id": case["case_id"],
                        "repetition": repetition,
                        **{
                            method: {
                                "wall_seconds": d["arm_total_wall_seconds"],
                                "new_cost_usd": d["agent_usage"][
                                    "estimated_cost_usd_completed_responses"
                                ],
                                "total_with_historical_cost_usd": d[
                                    "comparable_total_estimated_cost_usd"
                                ],
                            }
                            for method, d in rows.items()
                        },
                    }
                )
    assert sum(
        Decimal(d["new_cost_usd"]) for d in analysis["summary"].values()
    ) == Decimal(result["known_estimated_cost_usd"])
    return analysis


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--expected", type=int, choices=(8, 20), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    analysis = extract(args.raw.resolve(), args.expected)
    args.output.mkdir(parents=True, exist_ok=False)
    runner.base.write_json(args.output / "analysis.json", analysis)
    columns = [
        "slot",
        "project",
        "case_id",
        "repetition",
        "method",
        "strict_completed",
        "requests",
        "tokens",
        "new_cost_usd",
        "total_with_historical_cost_usd",
        "wall_seconds",
        "recovery_episodes",
        "local_returns",
        "local_revisions",
        "local_commands",
        "build_executions",
        "repeated_build_executions",
        "configure_executions",
        "repeated_configure_executions",
        "source_unchanged",
        "source_links_unchanged",
        "replay_status",
        "cleanup",
        "failure_category",
        "error",
    ]
    with (args.output / "slots.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for d in analysis["slots"]:
            row = {key: d[key] for key in columns if key in d}
            row.update(
                requests=d["agent_usage"]["model_requests"],
                tokens=d["agent_usage"]["recorded_tokens"],
                new_cost_usd=d["agent_usage"]["estimated_cost_usd_completed_responses"],
                total_with_historical_cost_usd=d["comparable_total_estimated_cost_usd"],
                wall_seconds=d["arm_total_wall_seconds"],
                build_executions=d["command_counts"]["build"],
                configure_executions=d["command_counts"]["configure"],
                cleanup=d["cleanup"]["succeeded"],
            )
            writer.writerow(row)
    print(
        json.dumps(
            {
                "identity": analysis["identity"],
                "summary": analysis["summary"],
                "strata": analysis["strata"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
