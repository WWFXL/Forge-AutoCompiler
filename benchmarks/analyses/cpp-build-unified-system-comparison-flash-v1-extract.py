"""只读提取统一系统比较；输出到操作会话，不改正式原始证据。"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("raw_root", type=Path)
parser.add_argument("--output-dir", type=Path, required=True)
args = parser.parse_args()
RAW = args.raw_root.resolve()
SESSION = args.output_dir.resolve()
SESSION.mkdir(parents=True, exist_ok=True)
METHODS = ("forge_state_workflow", "strong_tool_agent", "cxxcrafter_community_reference")


def load(path):
    return json.loads(path.read_text())


def D(value):
    return Decimal(str(value))


def events(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def summarize(rows, planned):
    return dict(
        planned=planned,
        observed=len(rows),
        complete=sum(x["strict_completed"] for x in rows),
        not_complete=sum(not x["strict_completed"] for x in rows),
        unobserved=planned - len(rows),
        requests=sum(x["requests"] for x in rows),
        input_tokens=sum(x["input_tokens"] for x in rows),
        output_tokens=sum(x["output_tokens"] for x in rows),
        cost_usd=str(sum((D(x["cost_usd"]) for x in rows), D(0))),
        seconds=sum(x["seconds"] or 0 for x in rows),
        missing_timing=sum(x["seconds"] is None for x in rows),
        unknown_requests=sum(x["unknown_requests"] for x in rows),
    )


def main():
    result = load(RAW / "result.json")
    protocol = load(RAW / "protocol.json")
    projects = {x["name"]: x for x in protocol["projects"]}
    rows = []
    checks = []
    for index, original in enumerate(result["rows"], 1):
        slot = RAW / f"slot-{index}"
        usage = original["agent_usage"]
        method = original["method"]
        x = dict(
            slot=index,
            project=original["project"],
            repetition=original["repetition"],
            method=method,
            strict_completed=original["strict_completed"],
            requests=usage.get("model_requests", usage.get("provider_requests", 0)),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cost_usd=str(usage["estimated_cost_usd_completed_responses"]),
            seconds=original.get("arm_total_wall_seconds"),
            unknown_requests=usage["unknown_usage_requests"],
            build_system=projects[original["project"]]["task"]["build_system"],
            status=original.get("status"),
            error_class=original.get("error_class"),
            error_message=original.get("error_message"),
            provider_stop=original.get("provider_stop", False),
            cleanup=original["cleanup"]["succeeded"],
            source_unchanged=original.get("fixed_sources_unchanged"),
            source_links_unchanged=original.get("source_links_unchanged"),
        )
        phase = defaultdict(lambda: dict(requests=0, input_tokens=0, output_tokens=0, cost_usd=D(0)))
        agent_events = []
        for p in slot.glob("*/agent/events.jsonl"):
            agent_events.extend(events(p))
        if method != METHODS[2]:
            current = "interaction" if method == METHODS[1] else "initial_planning"
            for e in agent_events:
                if e["event"] == "agent.started" and method == METHODS[0]:
                    current = "recovery" if e.get("recovery") else "initial_planning"
                if e["event"] == "model.request_completed":
                    p = phase[current]
                    p["requests"] += 1
                    p["input_tokens"] += e["input_tokens"]
                    p["output_tokens"] += e["output_tokens"]
                    p["cost_usd"] += (D(e["input_tokens"]) * D("0.30") + D(e["output_tokens"]) * D("1.20")) / 1000000
            phase_req = sum(p["requests"] for p in phase.values())
            phase_cost = sum((p["cost_usd"] for p in phase.values()), D(0))
            checks.append(dict(slot=index, check="raw_event_usage_and_cost", passed=phase_req == x["requests"] - x["unknown_requests"] and abs(phase_cost - D(x["cost_usd"])) < D("0.000000000001")))
        else:
            responses = [load(p) for p in sorted((slot / "agent").glob("request-*.response.json"))]
            inp = sum(r["usage"]["prompt_tokens"] for r in responses if r.get("usage"))
            out = sum(r["usage"]["completion_tokens"] for r in responses if r.get("usage"))
            cost = (D(inp) * D("0.30") + D(out) * D("1.20")) / 1000000
            checks.append(dict(slot=index, check="raw_sdk_response_usage_and_cost", passed=inp == x["input_tokens"] and out == x["output_tokens"] and abs(cost - D(x["cost_usd"])) < D("0.000000000001")))
            phase["native_all"] = dict(requests=len(responses), input_tokens=inp, output_tokens=out, cost_usd=cost)
            x["reported_success"] = original.get("reported_success")
            x["dockerfile_versions"] = original.get("versions")
            x["evaluations"] = original.get("evaluations", [])
            ev = x["evaluations"]
            x["source_unchanged"] = all(e["source_unchanged"] for e in ev) if ev else None
        x["phases"] = {k: {**v, "cost_usd": str(v["cost_usd"])} for k, v in phase.items()}
        x["direct_actions"] = [e for e in agent_events if e["event"] == "goal_state.action" and e.get("action") == "direct_configuration_revision"]
        x["recovery_episodes"] = sum(e["event"] == "agent.started" and e.get("recovery", False) for e in agent_events)
        x["candidate_rejections"] = dict(Counter(e["event"] for e in agent_events if "reject" in e["event"]))
        x["handoffs"] = list({t["handoff"]["handoff_id"]: dict(reason=t["handoff"].get("reason"), step_id=t["handoff"].get("step_id")) for t in original.get("transitions", []) if t.get("handoff")}.values())
        sessions = list(slot.glob("*/.compile-sessions/*/*/session.json"))
        x["session_files"] = [str(p.relative_to(RAW)) for p in sessions]
        x["commands"] = []
        x["configuration_observations"] = []
        x["replay_attempts"] = []
        x["verification"] = None
        for p in sessions:
            s = load(p)
            x["verification"] = s.get("verification")
            x["replay_attempts"] = s.get("replay_attempts", [])
            x["commands"] = [{k: c.get(k) for k in ("command_id", "role", "command", "exit_code", "timed_out", "duration_seconds", "log_path", "output_tail")} for c in s.get("commands", [])]
            for e in events(p.parent / "logs/workflow.log"):
                if e["event"] == "goal_state.observed":
                    x["configuration_observations"].append(e)
        x["time_censored"] = any(t in str(original.get("error_message", "")) for t in ("operation_window", "截止", "时间不足"))
        rows.append(x)
    summary = {m: summarize([x for x in rows if x["method"] == m], 16) for m in METHODS}
    per_project = {name: {m: summarize([x for x in rows if x["project"] == name and x["method"] == m], 2) for m in METHODS} for name in projects}
    grouped = {
        system: {m: summarize([x for x in rows if x["build_system"] == system and x["method"] == m], sum(p["task"]["build_system"] == system for p in projects.values()) * 2) for m in METHODS}
        for system in sorted({x["build_system"] for x in rows})
    }
    matched = defaultdict(dict)
    for x in rows:
        matched[(x["project"], x["repetition"])][x["method"]] = x
    common = [(k, v) for k, v in matched.items() if len(v) == 3 and all(x["strict_completed"] for x in v.values())]
    paired = dict(
        n=len(common), keys=[dict(project=k[0], repetition=k[1]) for k, v in common], summary={m: summarize([v[m] for _, v in common], len(common)) for m in METHODS}, boundary="按三方共同完成结果条件化，仅辅助描述效率，不能替代48槽主表"
    )
    out = dict(
        identity=result["identity"],
        raw=str(RAW),
        release=load(RAW / "execution.json"),
        candidate_sha256=protocol["candidate_sha256"],
        inventory=load(RAW / "seal.json"),
        summary=summary,
        per_project=per_project,
        by_build_system=grouped,
        common_completed=paired,
        rows=rows,
        unobserved=result["unobserved_schedule"],
        stop_reason=result["stop_reason"],
        known_cost_usd=result["known_estimated_cost_usd"],
        unknown_cost_reservation_usd=result["unknown_usage_reservation_usd"],
        checks=checks,
        boundary=protocol["comparison_boundary"],
    )
    assert all(c["passed"] for c in checks), [c for c in checks if not c["passed"]]
    assert len(rows) + len(out["unobserved"]) == 48
    assert abs(sum((D(x["cost_usd"]) for x in rows), D(0)) - D(out["known_cost_usd"])) < D("0.000000000001")
    (SESSION / "detailed-analysis.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    fields = (
        "slot",
        "project",
        "repetition",
        "method",
        "strict_completed",
        "status",
        "requests",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "seconds",
        "unknown_requests",
        "cleanup",
        "source_unchanged",
        "source_links_unchanged",
        "time_censored",
        "error_class",
        "error_message",
    )
    with (SESSION / "slot-table.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for x in rows:
            writer.writerow({k: x.get(k) for k in fields})
    print(json.dumps(dict(summary=summary, common_completed=paired, checks_passed=len(checks), observed=len(rows), stop_reason=out["stop_reason"]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
