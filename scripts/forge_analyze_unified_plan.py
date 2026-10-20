#!/usr/bin/env python3
"""从封存账本描述共享契约比较；所有失败费用计入，未观察保持未观察。"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from forge_typed_evidence import audit, write_json


def request_accounting(events):
    phase = "agent_control"
    started, completed, phases = {}, {}, defaultdict(lambda: {"requests": 0, "input_tokens": 0, "output_tokens": 0})
    for event in events:
        kind = event["event"]
        if kind == "unified.agent":
            phase = event["phase"]
        elif kind == "model.request_started":
            sequence = event["request_sequence"]
            if sequence in started:
                raise ValueError("重复请求身份")
            started[sequence] = phase
            phases[phase]["requests"] += 1
        elif kind == "model.request_completed":
            sequence = event["request_sequence"]
            if sequence not in started or sequence in completed:
                raise ValueError("响应缺请求或重复计量")
            inp, out = event["input_tokens"], event["output_tokens"]
            if any(type(n) is not int or n < 0 for n in (inp, out)) or event["recorded_tokens"] != inp + out:
                raise ValueError("Token计量不闭合")
            completed[sequence] = event
            phases[started[sequence]]["input_tokens"] += inp
            phases[started[sequence]]["output_tokens"] += out
    for name, row in phases.items():
        row["known_estimated_cost_usd"] = str((Decimal(row["input_tokens"]) * Decimal("1.32") + Decimal(row["output_tokens"]) * Decimal("3.96")) / Decimal(1000000))
        row["unknown_requests"] = sum(s not in completed and p == name for s, p in started.items())
    return {"requests": len(started), "unknown_requests": len(set(started) - set(completed)), "phases": dict(phases)}


def analyze(root):
    sealed = audit(root)
    result = json.loads((root / "result.json").read_text())
    protocol = json.loads((root / "protocol.json").read_text())
    if result["identity"] != "cpp-build-unified-plan-comparison-v1":
        raise ValueError("不把工程门禁当效果")
    if len(result["arms"]) > len(protocol["schedule"]):
        raise ValueError("观察超出固定分母")
    rows = []
    groups = defaultdict(lambda: {"observed": 0, "strict": 0, "requests": 0, "unknown_requests": 0, "known_estimated_cost_usd": Decimal(0), "arm_total_wall_seconds": 0.0, "shell_commands": 0})
    for slot, row in zip(protocol["schedule"], result["arms"], strict=False):
        if any(row[k] != slot[k] for k in slot):
            raise ValueError("顺序或任务漂移")
        folder = root / (row["name"] + ("-tool" if row["method"] == "strong_tool_agent" else "-plan"))
        events = [json.loads(s) for s in (folder / "agent/events.jsonl").read_text().splitlines()]
        accounting = request_accounting(events)
        usage = row["agent_usage"]
        if accounting["requests"] != usage["model_requests"] or accounting["unknown_requests"] != usage["unknown_usage_requests"]:
            raise ValueError("原请求账本与汇总不一致")
        cost = sum((Decimal(p["known_estimated_cost_usd"]) for p in accounting["phases"].values()), Decimal(0))
        if abs(cost - Decimal(str(usage["estimated_cost_usd_completed_responses"]))) > Decimal("0.000000001"):
            raise ValueError("原Token重算费用不一致")
        sessions = list(folder.glob(".compile-sessions/*/*/session.json"))
        if len(sessions) != 1:
            raise ValueError("缺唯一Session")
        session = json.loads(sessions[0].read_text())
        shells = len(session["commands"])
        rows.append(
            {
                **slot,
                "strict_completed": row["strict_completed"],
                "accounting": accounting,
                "known_estimated_cost_usd": str(cost),
                "shell_commands": shells,
                "arm_total_wall_seconds": row["arm_total_wall_seconds"],
                "initial_abstention": (folder / "agent/tool-abstention.json").exists(),
                "error_class": row.get("error_class"),
            }
        )
        group = groups[row["method"]]
        group["observed"] += 1
        group["strict"] += bool(row["strict_completed"])
        group["requests"] += accounting["requests"]
        group["unknown_requests"] += accounting["unknown_requests"]
        group["known_estimated_cost_usd"] += cost
        group["shell_commands"] += shells
        group["arm_total_wall_seconds"] += row["arm_total_wall_seconds"]
    if len(rows) + len(result["not_observed"]) != len(protocol["schedule"]):
        raise ValueError("预定分母不闭合")
    expected_tail = protocol["schedule"][len(rows) :]
    actual_tail = [{k: row[k] for k in expected_tail[0]} for row in result["not_observed"]] if expected_tail else result["not_observed"]
    if actual_tail != expected_tail:
        raise ValueError("未观察身份或顺序不一致")
    for group in groups.values():
        total = group["known_estimated_cost_usd"] + Decimal("0.40") * group["unknown_requests"]
        group["all_cost_per_strict_delivery_usd"] = str(total / group["strict"]) if group["strict"] else None
        group["known_estimated_cost_usd"] = str(group["known_estimated_cost_usd"])
    return {
        "kind": "descriptive_fixed_task_shared_contract_comparison",
        "inventory_sha256": sealed["inventory_canonical_sha256"],
        "rows": rows,
        "methods": dict(groups),
        "not_observed": result["not_observed"],
        "warning": "已见项目描述性比较；libtom两项关联，未知费用非零不作完整费用主张；与强工具Agent不称纯规划来源因果",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.root)
    write_json(args.output, result)
    print(json.dumps(result["methods"], ensure_ascii=False))


if __name__ == "__main__":
    main()
