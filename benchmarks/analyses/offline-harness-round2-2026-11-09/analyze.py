"""只读复算第二轮十二项目离线Harness比较，输出论文表和可追溯行为统计。"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import forge_offline_harness_round2 as run  # noqa: E402
from forge_typed_evidence import canonical  # noqa: E402

RAW = Path("/home/yiwei/.codex/outputs/forge-offline-harness-round2-flash-v1")


def main(output):
    output.mkdir(parents=True, exist_ok=False)
    load = run.shared.load
    summary = run.analyze(RAW)
    result = load(RAW / "comparison/result.json")
    inventory, seal = load(RAW / "inventory.json"), load(RAW / "seal.json")
    assert canonical(inventory) == seal["inventory_canonical_sha256"]
    hashes = {v["path"]: v["sha256"] for v in inventory if v["type"] == "file"}
    rows, receipts, behaviors = [], [], []
    for row in result["rows"]:
        folder = RAW / "comparison" / f"slot-{row['slot']:02d}-{row['project']}-{row['method']}"
        phase, usage, seen = "initial", {}, set()
        reads, lists, duplicates, recoveries, corrections = 0, 0, 0, 0, 0
        for event in map(json.loads, (folder / "agent/events.jsonl").read_text().splitlines()):
            if event["event"] == "agent.started":
                phase = "recovery" if event.get("recovery") else "initial"
                recoveries += bool(event.get("recovery"))
            part = usage.setdefault(phase, dict(requests=0, input_tokens=0, output_tokens=0, cost=Decimal(0)))
            if event["event"] == "model.request_completed":
                part["requests"] += 1
                part["input_tokens"] += event["input_tokens"]
                part["output_tokens"] += event["output_tokens"]
            elif event["event"] == "model.cost_estimated":
                part["cost"] += Decimal(event["cost_usd"])
            elif event["event"] == "tool.started" and event.get("name") in {"read_source", "list_source", "read_failure_log"}:
                key = (phase, event["name"], json.dumps(event.get("args", {}), sort_keys=True))
                duplicate = key in seen
                seen.add(key)
                reads += event["name"] == "read_source"
                lists += event["name"] == "list_source"
                duplicates += duplicate
                behaviors.append(dict(slot=row["slot"], project=row["project"], method=row["method"], phase=phase, tool=event["name"], arguments=event.get("args"), exact_repeat=duplicate))
            elif event["event"] == "simple.proposal_accepted":
                corrections += event["corrections"]
        counts, cost = Counter(dict(requests=0, input_tokens=0, output_tokens=0)), Decimal(0)
        for path in sorted((folder / "agent").glob("response-*.json"), key=lambda p: int(p.stem.split("-")[-1])):
            relative = path.relative_to(RAW).as_posix()
            assert hashlib.sha256(path.read_bytes()).hexdigest() == hashes[relative]
            messages = [m for m in load(path) if m["type"] == "ai"]
            assert len(messages) == 1
            m = messages[0]
            u, model = m["usage_metadata"], m["response_metadata"]["model_name"]
            assert model in run.shared.MODELS and u["total_tokens"] == u["input_tokens"] + u["output_tokens"]
            amount = (Decimal("0.30") * u["input_tokens"] + Decimal("1.20") * u["output_tokens"]) / 1_000_000
            counts.update(dict(requests=1, input_tokens=u["input_tokens"], output_tokens=u["output_tokens"]))
            cost += amount
            receipts.append(dict(slot=row["slot"], response=relative, sha256=hashes[relative], model=model, **u, estimated_cost_usd=str(amount)))
        recorded = run.shared.usage(row)
        assert recorded["unknown"] == 0
        assert all(counts[k] == recorded[k] for k in counts)
        assert abs(cost - recorded["cost"]) < Decimal("0.000000000001")
        assert cost == sum((p["cost"] for p in usage.values()), Decimal(0))
        layers = row.get("layers", {})
        session_path = next(folder.glob(".compile-sessions/*/*/session.json"))
        session = load(session_path)
        replay_attempts = session.get("replay_attempts", [])
        replay_observed = replay_attempts[-1]["status"] if replay_attempts else "not_started"
        verification = session.get("verification") or {}

        rows.append(
            dict(
                slot=row["slot"],
                project=row["project"],
                repetition=row["repetition"],
                method=row["method"],
                status=row["status"],
                error_type=row.get("error_type"),
                error=row.get("error"),
                main_task_completed=layers.get("main_build_task_completed"),
                primary_completed=layers.get("primary_build_completed"),
                delivery=layers.get("delivery", "unobserved"),
                clean_replay=layers.get("clean_replay", "unobserved"),
                author_tests=layers.get("author_tests", "unobserved"),
                final_verification_passed=session["status"] == "completed",
                observed_clean_replay=replay_observed,
                verification_error=session.get("error"),
                failed_verification_checks=[c for c in verification.get("checks", []) if c.get("passed") is not True],
                source_unchanged=row.get("source_unchanged"),
                cleanup=row.get("cleanup", {}).get("succeeded"),
                **counts,
                estimated_cost_usd=str(cost),
                wall_seconds=row["arm_total_wall_seconds"],
                source_reads=reads,
                directory_lists=lists,
                exact_repeat_information_calls=duplicates,
                recovery_tasks=recoveries,
                corrections=corrections,
                phase_usage={k: v | dict(cost=str(v["cost"])) for k, v in usage.items()},
                timings=row.get("timings"),
                router_usage=row.get("router_usage"),
            )
        )
    recovery_cases = []
    for row in rows:
        if not row["recovery_tasks"]:
            continue
        folder = RAW / "comparison" / f"slot-{row['slot']:02d}-{row['project']}-{row['method']}"
        session_path = next(folder.glob(".compile-sessions/*/*/session.json"))
        commands = load(session_path)["commands"]
        recovery_cases.append(
            dict(
                slot=row["slot"],
                project=row["project"],
                method=row["method"],
                session_path=session_path.relative_to(RAW).as_posix(),
                commands=[{k: c.get(k) for k in ("id", "role", "command", "workdir", "exit_code", "log_path")} for c in commands],
                proposals={p.name: load(p) for p in sorted((folder / "agent").glob("simple-actions-*.json"))},
                phase_usage=row["phase_usage"],
                timings=row["timings"],
                main_task_completed=row["main_task_completed"],
            )
        )
    run.save(output / "recovery-cases.json", recovery_cases)
    optimizer = load(RAW / "optimizer/response.json")
    u = optimizer["usage_metadata"]
    optimizer_cost = Decimal(u["input_tokens"] + u["output_tokens"]) / 1_000_000
    assert str(optimizer_cost) == summary["optimizer"]["estimated_cost_usd_completed_responses"]
    assert optimizer["response_metadata"]["model_name"] in {"gpt-5.6", "gpt-6-astra"}
    total = optimizer_cost + sum((Decimal(r["estimated_cost_usd"]) for r in rows), Decimal(0))
    assert abs(total - Decimal(summary["total_known_cost_usd"])) < Decimal("0.000000000001")
    by_project = {project: {method: run.summarize([r for r in result["rows"] if r["project"] == project and r["method"] == method], 1) for method in run.METHODS} for project in run.PROJECTS}
    pairs = []
    for project in run.PROJECTS:
        for repetition in (1,):
            both = {r["method"]: r for r in rows if r["project"] == project and r["repetition"] == repetition}
            pairs.append(dict(project=project, repetition=repetition, methods=both, all_three_observed=len(both) == 3))
    for method, arm in summary["arms"].items():
        chosen = [r for r in rows if r["method"] == method]
        for key in ("source_reads", "directory_lists", "exact_repeat_information_calls", "recovery_tasks", "corrections", "input_tokens", "output_tokens"):
            arm[key] = sum(r[key] for r in chosen)
        arm["phase_usage"] = {
            phase: dict(requests=sum(r["phase_usage"].get(phase, {}).get("requests", 0) for r in chosen), cost=str(sum((Decimal(r["phase_usage"].get(phase, {}).get("cost", "0")) for r in chosen), Decimal(0))))
            for phase in ("initial", "recovery")
        }
    for method, arm in summary["arms"].items():
        chosen = [r for r in rows if r["method"] == method]
        arm["median_wall_seconds"] = median(r["wall_seconds"] for r in chosen)
        arm["median_requests"] = median(r["requests"] for r in chosen)
        arm["median_cost_usd"] = str(median(Decimal(r["estimated_cost_usd"]) for r in chosen))
        arm["source_unchanged"] = dict(Counter(str(r["source_unchanged"]) for r in chosen))
        arm["cleanup"] = dict(Counter(str(r["cleanup"]) for r in chosen))
        arm["final_verification_passed"] = sum(r["final_verification_passed"] for r in chosen)
        arm["observed_clean_replay"] = dict(Counter(r["observed_clean_replay"] for r in chosen))
    protocol = load(RAW / "comparison/protocol.json")
    systems = {p["name"]: p["task"]["build_system"] for p in protocol["projects"]}
    summary["by_build_system"] = {system: {method: run.summarize([r for r in result["rows"] if r["method"] == method and systems[r["project"]] == system], 4) for method in run.METHODS} for system in ("cmake", "make", "autotools")}
    summary["paired_cost_time"] = {}
    for treatment, baseline in (("H1", "H0"), ("H2", "H0"), ("H2", "H1")):
        matched = []
        for project in run.PROJECTS:
            pair = {r["method"]: r for r in rows if r["project"] == project}
            if treatment not in pair or baseline not in pair:
                continue
            a, b = pair[treatment], pair[baseline]
            matched.append(
                dict(
                    project=project,
                    cost_delta_usd=str(Decimal(a["estimated_cost_usd"]) - Decimal(b["estimated_cost_usd"])),
                    wall_delta_seconds=a["wall_seconds"] - b["wall_seconds"],
                    request_delta=a["requests"] - b["requests"],
                    both_completed=a["main_task_completed"] and b["main_task_completed"],
                )
            )
        summary["paired_cost_time"][treatment + "_vs_" + baseline] = dict(
            paired_projects=len(matched), cheaper_projects=sum(Decimal(r["cost_delta_usd"]) < 0 for r in matched), faster_projects=sum(r["wall_delta_seconds"] < 0 for r in matched), differences=matched, descriptive_only=True
        )
    summary["evidence_inventory"] = seal["inventory_canonical_sha256"]
    summary["stop_reason"] = result["stop_reason"]
    summary["billing_complete"] = result["billing_complete"]
    summary["layer_interpretation"] = "原main_build_task_completed是主产物/源码/文件交付层；不包含完整submit验证和replay。原clean_replay=failed可能发生在smoke提交门禁，未有replay_attempt时另记not_started，保留原标签，不将未观察填失败。"
    summary["batch_wall_seconds"] = result["batch_wall_seconds"]
    for name, data in (
        ("summary.json", summary),
        ("slots.json", rows),
        ("by-project.json", by_project),
        ("pairs.json", pairs),
        ("failure-cases.json", [r for r in rows if not r["final_verification_passed"]]),
        ("optimizer-proposal.json", load(RAW / "optimizer/proposal.json")),
        ("frozen-harnesses.json", load(RAW / "frozen-harnesses.json")),
        ("information-calls.json", behaviors),
        ("response-verification.json", dict(responses=receipts, optimizer_tokens=u, optimizer_cost_usd=str(optimizer_cost), total_cost_usd=str(total), all_recorded_costs_match=True)),
    ):
        run.save(output / name, data)
    fields = [k for k in rows[0] if k not in {"phase_usage", "timings", "router_usage"}]
    with (output / "slots.csv").open("x") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(summary["arms"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
