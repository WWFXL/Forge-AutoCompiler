"""只读提取新项目统一系统比较；输出到操作会话，不改正式原始证据。"""

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("raw_root", type=Path)
parser.add_argument("--output-dir", type=Path, required=True)
parser.add_argument("--derived-result", type=Path)
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
        not_complete=sum(not x["strict_completed"] and not x["interrupted"] for x in rows),
        interrupted=sum(x["interrupted"] for x in rows),
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
    result_path = args.derived_result or RAW / "result.json"
    result = load(result_path)
    assert not args.derived_result or result.get("derived") is True
    if args.derived_result:
        assert len(result["rows"]) == 18 and len(result["unobserved_schedule"]) == 24
        assert not (RAW / "result.json").exists() and not (RAW / "progress-18.json").exists()
        for index, row in enumerate(result["rows"][:17], 1):
            assert row == load(RAW / f"progress-{index}.json")
        assert result["rows"][17]["agent_usage"] == load(RAW / "slot-18/agent/usage.json")
        assert result["raw_inventory"] == load(RAW / "seal.json")["inventory_canonical_sha256"]
    protocol = load(RAW / "protocol.json")
    projects = {x["name"]: x for x in protocol["projects"]}
    languages = {x["name"]: x["language"] for x in protocol["exposure"]["projects"]}
    rows = []
    initial_plans = []
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
            interrupted=original.get("interrupted", False),
            cleanup_observed_during_attempt=original["cleanup"].get("original_cleanup_observed", True),
            requests=usage.get("model_requests", usage.get("provider_requests", 0)),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cost_usd=str(usage["estimated_cost_usd_completed_responses"]),
            seconds=original.get("arm_total_wall_seconds"),
            unknown_requests=usage["unknown_usage_requests"],
            build_system=projects[original["project"]]["task"]["build_system"],
            language=languages[original["project"]],
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
        x["time_censored"] = original.get("time_censored", False) or any(t in str(original.get("error_message", "")) for t in ("operation_window", "截止", "时间不足"))
        if method == METHODS[0]:
            paths = sorted(slot.glob("*/agent/plan-1.json"))
            assert len(paths) <= 1
            p = paths[0] if paths else None
            initial_plans.append(dict(
                slot=index, project=x["project"], repetition=x["repetition"],
                accepted_plan_path=str(p.relative_to(RAW)) if p else None,
                accepted_plan_sha256=hashlib.sha256(p.read_bytes()).hexdigest() if p else None,
                initial_configuration_status=x["configuration_observations"][0]["status"] if x["configuration_observations"] else "unobserved",
                first_configuration_observation=x["configuration_observations"][0] if x["configuration_observations"] else None,
                initial_planning_usage=x["phases"].get("initial_planning"),
                build_system=x["build_system"], strict_completed=x["strict_completed"],
            ))
        rows.append(x)
    planned = Counter(x["method"] for x in protocol["schedule"])
    summary = {m: summarize([x for x in rows if x["method"] == m], planned[m]) for m in METHODS}
    per_project = {name: {m: summarize([x for x in rows if x["project"] == name and x["method"] == m], 2) for m in METHODS} for name in projects}
    grouped = {
        system: {m: summarize([x for x in rows if x["build_system"] == system and x["method"] == m], sum(p["task"]["build_system"] == system for p in projects.values()) * 2) for m in METHODS}
        for system in sorted({x["build_system"] for x in rows})
    }
    language_summary = {language: {m: summarize([x for x in rows if x["language"] == language and x["method"] == m], sum(languages[p] == language for p in projects) * 2) for m in METHODS} for language in sorted({languages[p] for p in projects})}
    matched = defaultdict(dict)
    for x in rows:
        matched[(x["project"], x["repetition"])][x["method"]] = x
    common = [(k, v) for k, v in matched.items() if len(v) == 3 and all(x["strict_completed"] for x in v.values())]
    paired = dict(
        n=len(common), keys=[dict(project=k[0], repetition=k[1]) for k, v in common], summary={m: summarize([v[m] for _, v in common], len(common)) for m in METHODS}, boundary="按三方共同完成结果条件化，仅辅助描述效率，不能替代固定42槽主表"
    )
    # 本批已核对的事后分层注释；不填充中断或未运行的验收。
    assert len(rows) == 18 and sum(x["strict_completed"] for x in rows) == 16
    assert rows[14]["verification"]["status"] == "failed" and rows[17]["interrupted"]
    layer_counts = {
        name: dict(passed=17, rejected=0, unobserved=25)
        for name in ("final_build", "fixed_task_check", "full_original_tests", "exact_delivery", "original_sources_and_links", "cleanup_during_attempt")
    }
    layer_counts["full_clean_replay"] = dict(passed=16, rejected=1, unobserved=25)
    out = dict(
        layered_validation_final=layer_counts,
        validation_annotation_boundary="固定42分母的事后原轨迹分层；slot15原32测试及交付通过但replay失败；slot18验收均未观察、清理仅恢复时确认。不能估自然误接受率。",
        identity=result["identity"],
        result_source=dict(path=str(result_path), sha256=hashlib.sha256(result_path.read_bytes()).hexdigest(), derived=result.get("derived", False)),
        raw=str(RAW),
        release=load(RAW / "execution.json"),
        candidate_sha256=protocol["candidate_sha256"],
        inventory=load(RAW / "seal.json"),
        summary=summary,
        per_project=per_project,
        by_build_system=grouped,
        by_language=language_summary,
        common_completed=paired,
        rows=rows,
        unobserved=result["unobserved_schedule"],
        stop_reason=result["stop_reason"],
        known_cost_usd=result["known_estimated_cost_usd"],
        unknown_cost_reservation_usd=result["unknown_usage_reservation_usd"],
        natural_initial_plan_registry=dict(planned=planned[METHODS[0]], observed=len(initial_plans), rows=initial_plans, boundary="登记全部观察到的Forge初始方案，不按偏离或能否修复筛选；未观察与非CMake分开解释。本表不创建新的付费组件实验。"),
        checks=checks,
        boundary=protocol["comparison_boundary"],
    )
    assert all(c["passed"] for c in checks), [c for c in checks if not c["passed"]]
    assert len(rows) + len(out["unobserved"]) == len(protocol["schedule"])
    assert abs(sum((D(x["cost_usd"]) for x in rows), D(0)) - D(out["known_cost_usd"])) < D("0.000000000001")
    (SESSION / "detailed-analysis.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    fields = (
        "slot",
        "project",
        "repetition",
        "method",
        "strict_completed",
        "interrupted",
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
