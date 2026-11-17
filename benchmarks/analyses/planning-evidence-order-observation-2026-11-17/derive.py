"""只读复算已结束的P5三槽材料，不覆盖原始证据或补填结果。"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path


def load(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    args = parser.parse_args()
    raw = args.raw.resolve()
    result = load(raw / "result.json")
    sealed = load(raw / "seal.json")
    output = Path(__file__).resolve().parent
    rows = []
    for row in result["rows"]:
        slot = raw / f"slot-{row['slot']:02d}-{row['project']}-{row['method']}"
        requests = sorted((slot / "agent").glob("request-*.json"), key=lambda p: int(p.stem.split("-")[1]))
        responses = sorted((slot / "agent").glob("response-*.json"), key=lambda p: int(p.stem.split("-")[1]))
        events = [json.loads(s) for s in (slot / "agent/events.jsonl").read_text().splitlines()]
        phase = "initial"
        phases = {}
        for event in events:
            if event["event"] == "agent.started":
                phase = "recovery" if event["recovery"] else "initial"
            if event["event"] == "model.request_started":
                phases[event["request_sequence"]] = phase
        calls, feedback = [], {}
        for request in requests:
            for message in load(request)["messages"]:
                if message.get("type") == "tool":
                    content = message.get("content")
                    try:
                        value = json.loads(content)
                    except (TypeError, ValueError):
                        value = content
                    feedback[message["tool_call_id"]] = dict(name=message.get("name"), result=value)
        input_tokens = output_tokens = 0
        for response in responses:
            sequence = int(response.stem.split("-")[1])
            for message in load(response):
                usage = message.get("usage_metadata") or {}
                input_tokens += usage.get("input_tokens", 0)
                output_tokens += usage.get("output_tokens", 0)
                for call in message.get("tool_calls", []):
                    item = dict(request=sequence, phase=phases.get(sequence), name=call["name"], args=call.get("args"), feedback=feedback.get(call["id"]))
                    calls.append(item)
        u = row["agent_usage"]
        cost = Decimal(input_tokens) * Decimal("0.00000030") + Decimal(output_tokens) * Decimal("0.00000120")
        assert input_tokens == u["input_tokens"] and output_tokens == u["output_tokens"]
        assert cost == Decimal(str(u["estimated_cost_usd_completed_responses"]))
        assert len(responses) == u["model_requests"]
        first = load(requests[0])
        packet = json.loads(next(m["content"] for m in first["messages"] if m["type"] == "human"))
        reads = Counter(json.dumps(c["args"], sort_keys=True) for c in calls if c["name"] == "read_source")
        rows.append(
            dict(
                slot=row["slot"],
                project=row["project"],
                status=row["status"],
                layers=row.get("layers"),
                cleanup=row["cleanup"],
                source_unchanged=row.get("source_unchanged"),
                source_review=row.get("source_review"),
                requests=u["model_requests"],
                initial_requests=sum(p == "initial" for p in phases.values()),
                recovery_requests=sum(p == "recovery" for p in phases.values()),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=str(cost),
                total_seconds=row["arm_total_wall_seconds"],
                timings=row["timings"],
                initial_source_paths=[p["path"] for p in packet.get("source_packet", [])],
                repeated_identical_read_calls=sum(n - 1 for n in reads.values()),
                invalid_tool_queries=[c for c in calls if isinstance((c.get("feedback") or {}).get("result"), dict) and c["feedback"]["result"].get("status") == "invalid_query"],
                # 只保留工具动作和必要反馈摘要，不转写模型内部推理文本。
                trajectory=[{**c, "feedback": {"status": c["feedback"]["result"].get("status"), "reason": c["feedback"]["result"].get("reason")} if c.get("feedback") and isinstance(c["feedback"]["result"], dict) else None} for c in calls],
                harness_events=[e for e in events if e["event"] == "harness.selected"],
            )
        )
    summary = dict(
        identity=result["identity"],
        raw=str(raw),
        inventory_sha256=sealed["inventory_canonical_sha256"],
        manifest_sha256=hashlib.sha256((raw / "protocol.json").read_bytes()).hexdigest(),
        rows=rows,
        completed_slots=result["completed_slots"],
        expected_slots=result["expected_slots"],
        unobserved=result["unobserved"],
        stop_reason=result["stop_reason"],
        billing_complete=result["billing_complete"],
        total_cost_usd=str(sum((Decimal(r["cost_usd"]) for r in rows), Decimal(0))),
        total_requests=sum(r["requests"] for r in rows),
        batch_wall_seconds=result["batch_wall_seconds"],
    )
    assert Decimal(summary["total_cost_usd"]) == Decimal(result["closed_slot_cost_usd"])
    (output / "analysis.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, ensure_ascii=False, indent=2))
    for row in rows:
        print(row["project"], row["status"], row["requests"], row["cost_usd"], row["total_seconds"])


if __name__ == "__main__":
    main()
