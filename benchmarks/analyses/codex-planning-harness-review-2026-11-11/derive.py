"""只读提取已观察轨迹的工具名、参数和收敛状态，不提取模型隐藏推理。"""

import hashlib
import json
from pathlib import Path

RAW = Path("/home/yiwei/.codex/outputs/forge-planning-p3-fixed-r2-comparison-flash-v1")
OUT = Path(__file__).resolve().parent
rows = []
for name in ("slot-11-libgcrypt-P3_R2", "slot-30-snapraid-P3_R2", "slot-02-libarchive-P3_R2"):
    agent = RAW / name / "agent"
    evidence = []
    requests = sorted(agent.glob("request-*.json"), key=lambda p: int(p.stem.split("-")[-1]))
    for request in requests:
        number = int(request.stem.split("-")[-1])
        response = agent / f"response-{number}.json"
        sent = json.loads(request.read_text())
        allowed = [t["function"]["name"] for t in sent["tools"]]
        if allowed != ["SimpleBuildActions"]:
            continue
        calls = [t for m in json.loads(response.read_text()) for t in m.get("tool_calls", [])]
        unauthorized = [t for t in calls if t["name"] not in allowed]
        actual = []
        next_request = agent / f"request-{number + 1}.json"
        if next_request.exists():
            for message in json.loads(next_request.read_text())["messages"]:
                if message["type"] == "tool" and message.get("tool_call_id") in {t["id"] for t in unauthorized}:
                    value = json.loads(message["content"])
                    actual.append(dict(tool=message["name"], call_id=message["tool_call_id"], accepted=not bool(value.get("error")), source_sha256=value.get("sha256"), read_request=value.get("read_request")))
        evidence.append(
            dict(
                request=number,
                advertised=allowed,
                returned=[dict(name=t["name"], args=t["args"], id=t["id"]) for t in calls],
                executed_results=actual,
                request_sha256=hashlib.sha256(request.read_bytes()).hexdigest(),
                response_sha256=hashlib.sha256(response.read_bytes()).hexdigest(),
            )
        )
    rows.append(
        dict(
            slot=name,
            only_submission_advertised_requests=len(evidence),
            other_tool_calls=sum(sum(c["name"] != "SimpleBuildActions" for c in e["returned"]) for e in evidence),
            observed_successful_other_tool_results=sum(sum(r["accepted"] for r in e["executed_results"]) for e in evidence),
            evidence=evidence,
        )
    )
(OUT / "trace-summary.json").write_text(json.dumps(dict(kind="posthoc_diagnostic_cases", raw=str(RAW), scope="three selected observed negative-cost cases; not an independent evaluation", rows=rows), ensure_ascii=False, indent=2) + "\n")
for row in rows:
    print({k: v for k, v in row.items() if k != "evidence"})
