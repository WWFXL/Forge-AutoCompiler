#!/usr/bin/env python3
"""固定两队列的回顾费用分解；逐响应核对输入/输出及规划/恢复阶段。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from forge_typed_evidence import audit, digest, seal, write_json

REPO_ROOT = Path(__file__).resolve().parents[1]


class Receipts:
    def __init__(self):
        self.files = {}

    def text(self, path):
        raw = path.read_bytes()
        import hashlib

        receipt = {"path": str(path.resolve()), "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        if str(path) in self.files and self.files[str(path)] != receipt:
            raise ValueError("读取期间证据发生变化")
        self.files[str(path)] = receipt
        return raw.decode()

    def json(self, path):
        return json.loads(self.text(path))


def price(inputs, outputs, prices):
    return (Decimal(inputs) * Decimal(prices["input_per_million_usd"]) + Decimal(outputs) * Decimal(prices["output_per_million_usd"])) / 1_000_000


def inspect_arm(folder, row, prices, reader):
    events = [json.loads(line) for line in reader.text(folder / "agent/events.jsonl").splitlines() if line.strip()]
    phase = "initial" if row["arm"] == "plan" else "tool"
    phases, completed = {}, {}
    for event in events:
        if event["event"] == "agent.started" and row["arm"] == "plan":
            phase = "recovery" if event["recovery"] else "initial"
        if event["event"] == "model.request_started":
            sequence = event["request_sequence"]
            if sequence in phases:
                raise ValueError("请求身份重复")
            phases[sequence] = phase
        if event["event"] == "model.request_completed":
            sequence = event["request_sequence"]
            if sequence in completed or sequence not in phases:
                raise ValueError("响应生命周期不闭合")
            completed[sequence] = event
    usage = row["agent_usage"]
    if not usage["cost_and_usage_complete"] or usage["unknown_usage_requests"] or set(phases) != set(completed) or len(phases) != usage["model_requests"]:
        raise ValueError("存在未闭合/未知用量，不作完整费用归因")
    requests = []
    for sequence in sorted(phases):
        response = reader.json(folder / f"agent/response-{sequence}.json")
        ai = [message for message in response if message["type"] == "ai"]
        if len(ai) != 1 or not ai[0].get("usage_metadata"):
            raise ValueError("原始AI响应usage不唯一或缺失")
        tokens = ai[0]["usage_metadata"]
        if tokens["total_tokens"] != tokens["input_tokens"] + tokens["output_tokens"] or tokens["total_tokens"] != completed[sequence]["recorded_tokens"]:
            raise ValueError("原始响应与事件Token不一致")
        request = reader.json(folder / f"agent/request-{sequence}.json")
        payload = json.loads(request["messages"][0]["content"])
        if row["arm"] == "plan" and bool(payload.get("handoff")) != (phases[sequence] == "recovery"):
            raise ValueError("事件阶段与真实请求接管材料不一致")
        requests.append(
            {"sequence": sequence, "phase": phases[sequence], "input_tokens": tokens["input_tokens"], "output_tokens": tokens["output_tokens"], "estimated_cost_usd": str(price(tokens["input_tokens"], tokens["output_tokens"], prices))}
        )
    inputs, outputs = (sum(item[key] for item in requests) for key in ("input_tokens", "output_tokens"))
    cost = price(inputs, outputs, prices)
    if inputs != usage["input_tokens"] or outputs != usage["output_tokens"] or inputs + outputs != usage["recorded_tokens"] or abs(cost - Decimal(str(usage["estimated_cost_usd_completed_responses"]))) > Decimal("0.00000001"):
        raise ValueError("逐响应与正式臂计量不一致")
    return {"project": row["project"], "repetition": row["repetition"], "arm": row["arm"], "strict_completed": row["strict_completed"], "input_tokens": inputs, "output_tokens": outputs, "estimated_cost_usd": str(cost), "requests": requests}


def aggregate(rows, prices):
    inputs = sum(row["input_tokens"] for row in rows)
    outputs = sum(row["output_tokens"] for row in rows)
    requests = [request for row in rows for request in row["requests"]]
    phases = {}
    for phase in sorted({request["phase"] for request in requests}):
        subset = [request for request in requests if request["phase"] == phase]
        phases[phase] = {
            "requests": len(subset),
            "input_tokens": sum(r["input_tokens"] for r in subset),
            "output_tokens": sum(r["output_tokens"] for r in subset),
            "estimated_cost_usd": str(sum((Decimal(r["estimated_cost_usd"]) for r in subset), Decimal(0))),
        }
    return {
        "arms": len(rows),
        "strict_completed": sum(row["strict_completed"] for row in rows),
        "requests": len(requests),
        "input_tokens": inputs,
        "output_tokens": outputs,
        "input_cost_usd": str(price(inputs, 0, prices)),
        "output_cost_usd": str(price(0, outputs, prices)),
        "estimated_cost_usd": str(price(inputs, outputs, prices)),
        "phase_totals": phases,
    }


def analyze(protocol, reader):
    cohorts = []
    for cohort in protocol["cohorts"]:
        root = Path(cohort["root"])
        before = audit(root)
        if before["inventory_canonical_sha256"] != cohort["inventory_sha256"]:
            raise ValueError("固定父队列封存身份不符")
        payload = reader.json(root / "result.json")
        original = reader.json(root / "protocol.json")
        expected = original["schedule"]
        if len(payload["arms"]) != cohort["arms"] or payload["unobserved_schedule"] or [{key: row[key] for key in ("project", "repetition", "arm")} for row in payload["arms"]] != expected:
            raise ValueError("原固定队列不完整或顺序不一致")
        rows = [inspect_arm(root / f"{row['name']}-{row['arm']}", row, protocol["prices"], reader) for row in payload["arms"]]
        totals = {arm: aggregate([row for row in rows if row["arm"] == arm], protocol["prices"]) for arm in ("plan", "tool")}
        delta = {key: str(Decimal(totals["plan"][key]) - Decimal(totals["tool"][key])) for key in ("input_cost_usd", "output_cost_usd", "estimated_cost_usd")}
        if Decimal(delta["input_cost_usd"]) + Decimal(delta["output_cost_usd"]) != Decimal(delta["estimated_cost_usd"]):
            raise ValueError("费用差分解不守恒")
        projects = {name: {arm: aggregate([row for row in rows if row["project"] == name and row["arm"] == arm], protocol["prices"]) for arm in ("plan", "tool")} for name in sorted({row["project"] for row in rows})}
        if audit(root) != before:
            raise ValueError("分析前后父证据变化")
        cohorts.append({"identity": cohort["identity"], "totals": totals, "plan_minus_tool_cost_components": delta, "projects": projects, "rows": rows})
    for receipt in reader.files.values():
        if digest(Path(receipt["path"])) != receipt["sha256"]:
            raise ValueError("分析后消费文件变化")
    return {
        "identity": protocol["identity"],
        "kind": "retrospective_cost_attribution",
        "provider_calls": 0,
        "cohorts": cohorts,
        "consumed_files": len(reader.files),
        "phase_request_counts": dict(Counter(request["phase"] for cohort in cohorts for row in cohort["rows"] for request in row["requests"])),
        "scope": "两个固定已见队列分别描述，不池化效果、不作跨批因果/自然恢复率/模型排名；估算不是账单",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    if protocol["identity"] != "cpp-build-token-cost-attribution-audit-v1" or protocol["provider_calls"] != 0:
        raise ValueError("回顾分析身份不符")
    if datetime.now(timezone.utc) >= datetime.fromisoformat(protocol["deadline_utc"].replace("Z", "+00:00")):
        raise ValueError("超过本轮结果分析执行窗口")
    for name, expected in protocol["components"].items():
        if digest(REPO_ROOT / name) != expected:
            raise ValueError("冻结分析组件变化")
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    reader = Receipts()
    result = analyze(protocol, reader)
    write_json(root / "result.json", result)
    write_json(root / "consumed-files.json", list(reader.files.values()))
    print(json.dumps(seal(root, protocol, REPO_ROOT)))
    print(json.dumps({"cohorts": [{"identity": c["identity"], "totals": c["totals"], "delta": c["plan_minus_tool_cost_components"]} for c in result["cohorts"]], "consumed_files": len(reader.files)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
