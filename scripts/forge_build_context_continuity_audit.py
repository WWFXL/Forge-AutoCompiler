#!/usr/bin/env python3
"""只读审计已封存真实请求的会话连续性；不调用模型或执行构建。"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from forge_typed_evidence import audit, digest, seal, write_json

IDENTITY = "cpp-build-rtorrent-context-continuity-audit-v1"
REPO = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def size(value):
    return len(json.dumps(value, ensure_ascii=False).encode())


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def inspect_agent(agent, root):
    """仅以实际request_started为分母；工具轮次必须完整、唯一配对。"""
    rounds, sequence = {}, None
    for event in map(json.loads, (agent / "events.jsonl").read_text().splitlines()):
        if event["event"] == "model.request_started":
            sequence = event["request_sequence"]
            require(sequence not in rounds, "实际请求序号重复")
            rounds[sequence] = []
        elif event["event"] == "tool.completed":
            require(sequence is not None, "工具完成事件缺少前置请求")
            rounds[sequence].append(event["result"])
    require(sorted(rounds) == list(range(1, len(rounds) + 1)), "实际请求序号不连续")
    rows = []
    for sequence in rounds:
        path = agent / f"request-{sequence}.json"
        request = read(path)
        row = dict(
            path=path.relative_to(root).as_posix(),
            sha256=digest(path),
            sequence=sequence,
            message_types=[m["type"] for m in request["messages"]],
            messages_bytes=size({k: v for k, v in request.items() if k != "tools"}),
            transition=sequence > 1,
        )
        if sequence > 1:
            previous = agent / f"response-{sequence - 1}.json"
            ai = [m for m in read(previous) if m["type"] == "ai"]
            require(len(ai) == 1, "上一轮必须有唯一原始AI响应")
            calls = [c["id"] for c in ai[0].get("tool_calls", [])]
            tools = rounds[sequence - 1]
            ids = [t["tool_call_id"] for t in tools]
            require(
                bool(calls)
                and len(calls) == len(set(calls))
                and len(ids) == len(set(ids))
                and sorted(calls) == sorted(ids),
                "上一轮工具调用与返回不完整或不唯一",
            )
            by_id = {t["tool_call_id"]: t for t in tools}
            ordered = [by_id[identifier] for identifier in calls]
            prior = [ai[0], *ordered]
            candidate = dict(
                messages=[*request["messages"], *prior],
                system_message=request["system_message"],
            )
            row.update(
                previous_response_sha256=digest(previous),
                previous_tool_call_ids=calls,
                previous_round_pairing_complete=True,
                native_previous_ai_preserved=ai[0] in request["messages"],
                native_previous_tools_preserved=all(
                    t in request["messages"] for t in ordered
                ),
                previous_reasoning_present=bool(
                    ai[0].get("additional_kwargs", {}).get("reasoning_content")
                ),
                previous_round_bytes=size(prior),
                naive_append_bytes=size(candidate),
                naive_append_fits_original_50000=size(candidate) <= 50000,
            )
        rows.append(row)
    unstarted = [
        p.relative_to(root).as_posix()
        for p in sorted(agent.glob("request-*.json"))
        if int(p.stem.split("-")[-1]) not in rounds
    ]
    return rows, unstarted


def inspect_source(root):
    rows, unstarted = [], []
    agents = sorted(root.glob("slot-*/rtorrent-*/agent"))
    require(len(agents) == 3, "每个来源须有原三策略agent目录")
    for agent in agents:
        current, skipped = inspect_agent(agent, root)
        rows.extend(current)
        unstarted.extend(skipped)
    transitions = [r for r in rows if r["transition"]]
    return dict(
        root=str(root),
        actual_requests=len(rows),
        unstarted_saved_request_paths=unstarted,
        transitions=len(transitions),
        single_human_packets=sum(r["message_types"] == ["human"] for r in rows),
        previous_ai_preserved=sum(
            r["native_previous_ai_preserved"] for r in transitions
        ),
        previous_tools_preserved=sum(
            r["native_previous_tools_preserved"] for r in transitions
        ),
        naive_append_fits=sum(
            r["naive_append_fits_original_50000"] for r in transitions
        ),
        max_naive_append_bytes=max(
            (r["naive_append_bytes"] for r in transitions), default=None
        ),
        rows=rows,
    )


def execute(protocol, output):
    require(
        protocol["identity"] == IDENTITY
        and protocol["kind"] == "retrospective_complete_request_census",
        "审计身份或范围不符",
    )
    require(
        [r["identity"] for r in protocol["sources"]]
        == [f"cpp-build-rtorrent-common-canary-v{version}" for version in (2, 3, 4)],
        "不得改变来源分母",
    )
    require(
        protocol["deadline_utc"] == "2026-10-21T19:30:52+00:00"
        and datetime.now(timezone.utc)
        < datetime.fromisoformat(protocol["deadline_utc"]),
        "原运行时窗已结束",
    )
    for reference in protocol["reference_implementations"]:
        require(
            digest(Path(reference["path"])) == reference["sha256"], "既有实现来源变化"
        )
    for name, expected in protocol["components"].items():
        require(digest(REPO / name) == expected, "审计组件变化")
    sources = []
    for source in protocol["sources"]:
        root = Path(source["root"])
        sealed = audit(root)
        require(
            sealed["identity"] == source["identity"]
            and sealed["inventory_canonical_sha256"] == source["inventory_sha256"],
            "来源封存变化",
        )
        require(
            read(root / "result.json")["lifecycle_complete"]
            and sealed["unknown_usage_requests"] == 0,
            "来源未闭合",
        )
        receipt = source["independent_audit"]
        verified = read(Path(receipt["path"]))
        require(
            digest(Path(receipt["path"])) == receipt["sha256"]
            and verified["valid"]
            and verified["identity"] == source["identity"]
            and verified["inventory"]["inventory_canonical_sha256"]
            == source["inventory_sha256"]
            and verified["provider_requests"] == source["actual_requests"],
            "来源独立审计不匹配",
        )
        measured = inspect_source(root)
        require(
            measured["actual_requests"] == source["actual_requests"], "实际请求分母变化"
        )
        sources.append({**source, **measured})
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "protocol.json", protocol)
    write_json(
        output / "run.json",
        dict(
            release=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
            ).strip()
        ),
    )
    result = dict(
        identity=IDENTITY,
        kind=protocol["kind"],
        sources=sources,
        actual_requests=sum(r["actual_requests"] for r in sources),
        transitions=sum(r["transitions"] for r in sources),
        provider_calls=0,
        new_model_tokens=0,
        new_model_cost_usd="0",
        build_commands=0,
        claim_boundary="后验完整请求审计与原样追加材料测量；不证明失败原因、模型理解、修复有效或策略收益。追加方案不是实际发送或完整接口资格。",
    )
    write_json(output / "result.json", result)
    sealed = seal(output, protocol, REPO)
    return {k: v for k, v in result.items() if k != "sources"} | dict(inventory=sealed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(execute(read(args.protocol), args.output_root), ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
