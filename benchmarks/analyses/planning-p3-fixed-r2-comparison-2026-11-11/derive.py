import json
import csv
from pathlib import Path
from decimal import Decimal
from collections import Counter

raw = Path("/home/yiwei/.codex/outputs/forge-planning-p3-fixed-r2-comparison-flash-v1")
out = raw.parent / "forge-planning-p3-comparison-session-20261111"
result = json.loads((raw / "result.json").read_text())
analysis = json.loads((raw / "analysis.json").read_text())
protocol = json.loads((raw / "protocol.json").read_text())
rows = []
models = Counter()
inputs = outputs = requests = 0
for row, detail in zip(result["rows"], analysis["slots"], strict=True):
    assert row["slot"] == detail["slot"]
    folder = raw / f"slot-{row['slot']:02d}-{row['project']}-{row['method']}"
    responses = sorted((folder / "agent").glob("response-*.json"))
    ii = oo = 0
    for f in responses:
        messages = json.loads(f.read_text())
        ai = [m for m in messages if m.get("type") == "ai" and m.get("usage_metadata")]
        assert len(ai) == 1, (f, len(ai))
        m = ai[0]
        ii += m["usage_metadata"]["input_tokens"]
        oo += m["usage_metadata"]["output_tokens"]
        models[m["response_metadata"].get("model_name")] += 1
    u = row["agent_usage"]
    cost = (Decimal(ii) * Decimal("0.30") + Decimal(oo) * Decimal("1.20")) / 1000000
    assert (
        ii == u["input_tokens"]
        and oo == u["output_tokens"]
        and len(responses) == u["model_requests"]
    )
    assert cost == Decimal(str(u["estimated_cost_usd_completed_responses"]))
    inputs += ii
    outputs += oo
    requests += len(responses)
    p = detail["phases"]
    layers = row.get("layers", {})
    issue = (row.get("verification_issue") or {}).get("kind") or row.get("error", "")
    rows.append(
        dict(
            slot=row["slot"],
            project=row["project"],
            method=row["method"],
            status=row["status"],
            main=layers.get("main_build_task_completed"),
            delivery=layers.get("reproducible_delivery_completed"),
            cost=str(cost),
            requests=len(responses),
            wall_seconds=row["arm_total_wall_seconds"],
            initial_requests=p["initial"]["requests"],
            initial_cost=p["initial"]["estimated_cost_usd"],
            recovery_invocations=p["recovery"]["invocations"],
            recovery_requests=p["recovery"]["requests"],
            recovery_cost=p["recovery"]["estimated_cost_usd"],
            initial_reads=p["initial"]["reads"],
            initial_repeat_reads=p["initial"]["exact_repeat_reads"],
            initial_seconds=row.get("timings", {}).get("initial_planning_seconds"),
            recovery_seconds=row.get("timings", {}).get("recovery_agent_seconds"),
            issue=issue,
        )
    )
usage = dict(
    valid=True,
    requests=requests,
    input_tokens=inputs,
    output_tokens=outputs,
    total_tokens=inputs + outputs,
    cost_usd=str(
        (Decimal(inputs) * Decimal("0.30") + Decimal(outputs) * Decimal("1.20"))
        / 1000000
    ),
    models=dict(models),
    unknown_usage_requests=sum(
        r["agent_usage"].get("unknown_usage_requests", 0) for r in result["rows"]
    ),
)
assert Decimal(usage["cost_usd"]) == Decimal(result["closed_slot_cost_usd"])
assert usage["unknown_usage_requests"] == 0
(out / "usage-verification.json").write_text(
    json.dumps(usage, ensure_ascii=False, indent=2) + "\n"
)
with (out / "slots.csv").open("w") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader()
    w.writerows(rows)
pairs = []
for project in protocol["projects"]:
    rr = {r["method"]: r for r in rows if r["project"] == project["name"]}
    if len(rr) != 2:
        continue
    a, b = rr["P0_R2"], rr["P3_R2"]
    pairs.append(
        dict(
            project=project["name"],
            system=project["task"]["build_system"],
            P0=a,
            P3=b,
            cost_delta=str(Decimal(b["cost"]) - Decimal(a["cost"])),
            wall_delta=b["wall_seconds"] - a["wall_seconds"],
        )
    )
systems = {
    system: {
        method: {
            "observed": sum(p["system"] == system for p in pairs),
            "main": sum(
                p[method]["main"] is True for p in pairs if p["system"] == system
            ),
            "delivery": sum(
                p[method]["delivery"] is True for p in pairs if p["system"] == system
            ),
        }
        for method in ["P0", "P3"]
    }
    for system in ["cmake", "make", "autotools"]
}
summary = dict(
    analysis=analysis,
    usage=usage,
    by_system=systems,
    pairs=pairs,
    paired_main=dict(
        P0_only=sum(
            p["P0"]["main"] is True and p["P3"]["main"] is not True for p in pairs
        ),
        P3_only=sum(
            p["P3"]["main"] is True and p["P0"]["main"] is not True for p in pairs
        ),
        both=sum(p["P0"]["main"] is True and p["P3"]["main"] is True for p in pairs),
    ),
    raw_summary={k: v for k, v in result.items() if k not in ("rows", "unobserved")},
)
(out / "derived.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
)
print(
    json.dumps(
        {k: v for k, v in summary.items() if k not in ("analysis", "pairs")},
        ensure_ascii=False,
        indent=2,
    )
)
