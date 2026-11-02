#!/usr/bin/env python3
"""只读提取经验实验全分母、费用、请求阶段、检索和分层验收。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path


def load(path):
    return json.loads(path.read_text())


def analyze(root):
    result, protocol = load(root / "result.json"), load(root / "protocol.json")
    details = []
    for index, row in enumerate(result["rows"], 1):
        folder = root / f"slot-{index}"
        event_files = list(folder.glob("*/agent/events.jsonl"))
        events = [
            json.loads(line) for p in event_files for line in p.read_text().splitlines()
        ]
        phases, phase = {}, "initial"
        for event in events:
            if event["event"] == "agent.started":
                phase = "recovery" if event.get("recovery") else "initial"
            elif event["event"] == "model.request_started":
                phases[event["request_sequence"]] = phase
        counts = Counter(phases.values())
        costs = defaultdict(Decimal)
        tokens = Counter()
        models = Counter()
        for event_file in event_files:
            for path in event_file.parent.glob("response-*.json"):
                sequence = int(path.stem.split("-")[-1])
                for message in load(path):
                    if message.get("type") != "ai":
                        continue
                    usage = message.get("usage_metadata") or {}
                    inp, out = (
                        usage.get("input_tokens", 0),
                        usage.get("output_tokens", 0),
                    )
                    tokens["input"] += inp
                    tokens["output"] += out
                    costs[phases.get(sequence, "unclassified")] += (
                        Decimal(inp) * Decimal("0.30") + Decimal(out) * Decimal("1.20")
                    ) / 1_000_000
                    models[
                        message.get("response_metadata", {}).get(
                            "model_name", "unknown"
                        )
                    ] += 1
        sessions = list(folder.glob("*/.compile-sessions/*/*/session.json"))
        state = load(sessions[0]) if len(sessions) == 1 else {}
        commands = state.get("commands", [])
        smoke = [c for c in commands if c["role"] == "smoke"]
        task = next(
            p["task"] for p in protocol["projects"] if p["name"] == row["project"]
        )
        bank_used = load(folder / "experience-bank-used.json")
        updated_available = sorted(
            {
                e["source_id"]
                for e in bank_used["entries"]
                if e["source_id"].startswith("update-task-")
                and e["build_system"] == task["build_system"]
                and e["source_family"] != row["project"]
            }
        )
        test_observations = []
        for step in task["verification_steps"]:
            if step["step_id"] == "build-profile":
                continue
            matches = [c for c in smoke if c["command"] == step["command"]]
            last = matches[-1] if matches else None
            test_observations.append(
                dict(
                    step_id=step["step_id"],
                    attempts=len(matches),
                    status="unobserved"
                    if last is None
                    else "passed"
                    if last["exit_code"] == 0 and not last["timed_out"]
                    else "observed_failure",
                )
            )
        retrieval = [e for e in events if e["event"] == "experience.retrieved"]
        role_seconds = defaultdict(float)
        for command in commands:
            role_seconds[command["role"]] += command["duration_seconds"]
        replay_seconds = sum(
            attempt.get("duration_seconds") or 0
            for attempt in state.get("replay_attempts", [])
        )
        record = dict(
            slot=index,
            project=row["project"],
            method=row["method"],
            repetition=row["repetition"],
            complete=row["strict_completed"],
            status=row.get("status", "exception"),
            requests=row["agent_usage"]["model_requests"],
            cost_usd=str(row["agent_usage"]["estimated_cost_usd_completed_responses"]),
            wall_seconds=row["arm_total_wall_seconds"],
            recorded_command_seconds=sum(role_seconds.values()),
            role_seconds=dict(role_seconds),
            replay_total_seconds=replay_seconds,
            other_wall_seconds=row["arm_total_wall_seconds"]
            - sum(role_seconds.values())
            - replay_seconds,
            initial_requests=counts["initial"],
            recovery_requests=counts["recovery"],
            initial_cost_usd=str(costs["initial"]),
            recovery_cost_usd=str(costs["recovery"]),
            response_cost_matches_ledger=sum(costs.values(), Decimal(0))
            == Decimal(
                str(row["agent_usage"]["estimated_cost_usd_completed_responses"])
            ),
            response_tokens=dict(tokens),
            response_models=dict(models),
            recovery_episodes=sum(
                e["event"] == "agent.started" and e.get("recovery", False)
                for e in events
            ),
            direct_actions=sum(
                e["event"] == "goal_state.action"
                and e.get("action") == "direct_configuration_revision"
                for e in events
            ),
            retrieval_events=len(retrieval),
            retrieval_with_material=sum(bool(e["source_ids"]) for e in retrieval),
            retrieval_with_updated_material=sum(
                any(s.startswith("update-task-") for s in e["source_ids"])
                for e in retrieval
            ),
            retrieval_bytes=sum(e["bytes"] for e in retrieval),
            retrieved_source_ids=sorted(
                {n for e in retrieval for n in e["source_ids"]}
            ),
            available_updated_source_ids=updated_available,
            source_unchanged=row.get("fixed_sources_unchanged"),
            source_links_unchanged=row.get("source_links_unchanged"),
            original_test_observations=test_observations,
            smoke_command_observations=len(smoke),
            original_tests_status=(
                "unobserved"
                if any(t["status"] == "unobserved" for t in test_observations)
                else "passed"
                if all(t["status"] == "passed" for t in test_observations)
                else "observed_failure"
            ),
            verification_status=(state.get("verification") or {}).get(
                "status", "unobserved"
            ),
            replay_status=state["replay_attempts"][-1]["status"]
            if state.get("replay_attempts")
            else "unobserved",
            cleanup=row["cleanup"],
            error_class=row.get("error_class"),
            error=row.get("error_message"),
            proposal_rejections=[
                {k: e[k] for k in ("event", "detail", "reason") if k in e}
                for e in events
                if e["event"] in ("observed.proposal_rejected", "candidate.rejected")
            ],
            command_counts=dict(Counter(c["role"] for c in commands)),
            failed_commands=[
                dict(
                    role=c["role"],
                    command_id=c["command_id"],
                    exit_code=c["exit_code"],
                    timed_out=c["timed_out"],
                )
                for c in commands
                if c["exit_code"] != 0 or c["timed_out"]
            ],
        )
        details.append(record)
    summary = {}
    for method in dict.fromkeys(s["method"] for s in protocol["schedule"]):
        rows = [r for r in details if r["method"] == method]
        planned = sum(s["method"] == method for s in protocol["schedule"])
        summary[method] = dict(
            planned=planned,
            observed=len(rows),
            complete=sum(r["complete"] for r in rows),
            unobserved=planned - len(rows),
            requests=sum(r["requests"] for r in rows),
            cost_usd=str(sum((Decimal(r["cost_usd"]) for r in rows), Decimal(0))),
            wall_minutes=sum(r["wall_seconds"] for r in rows) / 60,
            recorded_command_minutes=sum(r["recorded_command_seconds"] for r in rows)
            / 60,
            replay_minutes=sum(r["replay_total_seconds"] for r in rows) / 60,
            other_wall_minutes=sum(r["other_wall_seconds"] for r in rows) / 60,
            initial_requests=sum(r["initial_requests"] for r in rows),
            recovery_requests=sum(r["recovery_requests"] for r in rows),
            recovery_episodes=sum(r["recovery_episodes"] for r in rows),
            direct_actions=sum(r["direct_actions"] for r in rows),
            retrieval_with_material=sum(r["retrieval_with_material"] for r in rows),
            retrieval_events=sum(r["retrieval_events"] for r in rows),
            retrieval_material_bytes=sum(r["retrieval_bytes"] for r in rows),
            slots_with_updated_material=sum(
                bool(r["retrieval_with_updated_material"]) for r in rows
            ),
            slots_with_available_updated_material=sum(
                bool(r["available_updated_source_ids"]) for r in rows
            ),
            original_tests=dict(Counter(r["original_tests_status"] for r in rows)),
            verification=dict(Counter(r["verification_status"] for r in rows)),
            replay=dict(Counter(r["replay_status"] for r in rows)),
            statuses=dict(Counter(r["status"] for r in rows)),
            recorded_tokens=sum(sum(r["response_tokens"].values()) for r in rows),
            input_tokens=sum(r["response_tokens"].get("input", 0) for r in rows),
            output_tokens=sum(r["response_tokens"].get("output", 0) for r in rows),
        )
    methods = list(summary)
    pairs = []
    for left_index, left in enumerate(methods):
        for right in methods[left_index + 1 :]:
            by_key = {(r["project"], r["repetition"], r["method"]): r for r in details}
            matched = [
                (r, by_key[(r["project"], r["repetition"], right)])
                for r in details
                if r["method"] == left
                and (r["project"], r["repetition"], right) in by_key
            ]
            common = [(a, b) for a, b in matched if a["complete"] and b["complete"]]
            pairs.append(
                dict(
                    left=left,
                    right=right,
                    matched=len(matched),
                    left_only_complete=sum(
                        a["complete"] and not b["complete"] for a, b in matched
                    ),
                    right_only_complete=sum(
                        b["complete"] and not a["complete"] for a, b in matched
                    ),
                    common_complete=len(common),
                    common_complete_left_cost_usd=str(
                        sum((Decimal(a["cost_usd"]) for a, _ in common), Decimal(0))
                    ),
                    common_complete_right_cost_usd=str(
                        sum((Decimal(b["cost_usd"]) for _, b in common), Decimal(0))
                    ),
                    common_complete_left_wall_seconds=sum(
                        a["wall_seconds"] for a, _ in common
                    ),
                    common_complete_right_wall_seconds=sum(
                        b["wall_seconds"] for _, b in common
                    ),
                )
            )
    update_receipts = [
        {"folder": p.parent.name, **load(p)}
        for p in sorted(root.glob("update-*/usage.json"))
    ]
    update_cost = sum((Decimal(r["cost_usd"]) for r in update_receipts), Decimal(0))
    update_unknown = sum(
        bool(load(p).get("unknown_usage")) for p in root.glob("update-*/failure.json")
    )
    return dict(
        identity=result["identity"],
        layer_semantics="原测试状态为固定原命令的最后实际观察；不替代后续状态变化后的有效性，完整完成按strict_completed",
        summary=summary,
        paired_descriptive=pairs,
        slots=details,
        updates=result.get("updates", []),
        update_cost_usd=str(update_cost),
        update_request_wall_seconds=sum(r["wall_seconds"] for r in update_receipts),
        update_cost_in_original_result_usd=result.get("update_cost_usd", "0"),
        update_receipts=update_receipts,
        update_unknown_usage=update_unknown,
        update_cost_matches_original=update_cost
        == Decimal(result.get("update_cost_usd", "0")),
        unobserved=result["unobserved_schedule"],
        stop_reason=result["stop_reason"],
        cost_recomputed=all(r["response_cost_matches_ledger"] for r in details),
        provenance={
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in ("result.json", "protocol.json", "execution.json")
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = analyze(args.root)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "analysis.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    )
    with (args.output / "slots.csv").open("w") as handle:
        columns = [
            k
            for k in value["slots"][0]
            if k
            not in ("cleanup", "response_models", "response_tokens", "command_counts")
        ]
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(value["slots"])
    print(json.dumps(value["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
