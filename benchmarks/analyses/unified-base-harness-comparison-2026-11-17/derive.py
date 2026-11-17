"""只读本轮封存原件，复算计费、完整表及原输入diff，不调用Provider。"""

import csv
import difflib
import hashlib
import json
import subprocess
import tarfile
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = Path("/home/yiwei/.codex/outputs/forge-unified-base-harness-comparison-flash-2026-11-17-v1")
OUT = Path(__file__).resolve().parent
result = json.loads((RAW / "result.json").read_text())
analysis = json.loads((RAW / "analysis.json").read_text())
protocol = json.loads((RAW / "protocol.json").read_text())
refs, models, slots, reviews = set(), Counter(), [], []
for row in result["rows"]:
    folder = RAW / f"slot-{row['slot']:02d}-{row['project']}-{row['method']}"
    ins = outs = requests = 0
    for response in sorted((folder / "agent").glob("response-*.json")):
        for message in json.loads(response.read_text()):
            meta = message["response_metadata"]
            models[meta["model_name"]] += 1
            ins += meta["token_usage"]["prompt_tokens"]
            outs += meta["token_usage"]["completion_tokens"]
            requests += 1
    usage = row["agent_usage"]
    assert (ins, outs, requests) == (usage["input_tokens"], usage["output_tokens"], usage["model_requests"])
    cost = (Decimal(ins) * Decimal(".30") + Decimal(outs) * Decimal("1.20")) / 1_000_000
    assert cost == Decimal(str(usage["estimated_cost_usd_completed_responses"]))
    assert usage["unknown_usage_requests"] == 0 and row["cleanup"]["succeeded"]
    events = [json.loads(line) for line in (folder / "agent/events.jsonl").read_text().splitlines()]
    layers = row.get("layers", {})
    slots.append(
        dict(
            slot=row["slot"],
            project=row["project"],
            method=row["method"],
            status=row["status"],
            main=layers.get("main_build_task_completed"),
            delivery=layers.get("reproducible_delivery_completed"),
            requests=requests,
            input_tokens=ins,
            output_tokens=outs,
            cost_usd=str(cost),
            wall_seconds=row.get("arm_total_wall_seconds", 0),
            error=row.get("error"),
            rejection_count=sum(e["event"] == "simple.proposal_rejected" for e in events),
        )
    )
    for session_file in folder.glob(".compile-sessions/simple-system/*/session.json"):
        session = json.loads(session_file.read_text())
        for container in [session, *session.get("replay_attempts", [])]:
            refs.update(container[k] for k in ("container_id", "container_name") if container.get(k))
    originals = [c for c in row.get("source_protection", {}).get("changes", []) if c.get("before") is not None]
    if not originals:
        continue
    project = next(p for p in protocol["projects"] if p["name"] == row["project"])
    workspace = next(folder.glob(".compile-sessions/simple-system/*/workspace/repo"))
    with tarfile.open(project["source_archive"]) as archive:
        members = {m.name.removeprefix("./").removeprefix("repo/"): m for m in archive.getmembers()}
        for change in originals:
            path = change["path"]
            member = members.get(path)
            old = archive.extractfile(member).read() if member and member.isfile() else b""
            current = workspace / path
            new = current.read_bytes() if current.is_file() and not current.is_symlink() else b""
            reviews.append(
                dict(
                    slot=row["slot"],
                    project=row["project"],
                    method=row["method"],
                    path=path,
                    kind=change["kind"],
                    original_sha256=hashlib.sha256(old).hexdigest(),
                    observed_sha256=hashlib.sha256(new).hexdigest(),
                    diff="".join(difflib.unified_diff(old.decode(errors="replace").splitlines(True), new.decode(errors="replace").splitlines(True), fromfile="original/" + path, tofile="observed/" + path)),
                )
            )
assert set(models) <= {"deepseek-flash"}
for ref in sorted(refs):
    c = subprocess.run(["docker", "container", "inspect", ref], capture_output=True, text=True)
    assert c.returncode != 0 and ("No such container" in c.stderr or "No such object" in c.stderr)
seal = json.loads((RAW / "seal.json").read_text())
verification = dict(
    identity=protocol["identity"],
    closed_slots=len(slots),
    planned_slots=len(protocol["schedule"]),
    models=dict(models),
    input_tokens=sum(s["input_tokens"] for s in slots),
    output_tokens=sum(s["output_tokens"] for s in slots),
    requests=sum(s["requests"] for s in slots),
    cost_usd=str(sum((Decimal(s["cost_usd"]) for s in slots), Decimal(0))),
    unknown_usage_requests=0,
    cleanup_passed=len(slots),
    absent_container_references=len(refs),
    inventory_sha256=seal["inventory_canonical_sha256"],
    original_input_changes=len(reviews),
    unclosed_slot=result["unclosed_slot"],
    billing_complete=result["billing_complete"],
    batch_wall_seconds=result["batch_wall_seconds"],
)
for name, data in [("analysis.json", analysis), ("verification.json", verification), ("slots.json", slots), ("source-diffs.json", reviews)]:
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
with (OUT / "slots.csv").open("w") as f:
    writer = csv.DictWriter(f, fieldnames=list(slots[0]))
    writer.writeheader()
    writer.writerows(slots)
lines = ["| 项目 | 原组完成 | 新组完成 | 原/新请求 | 原/新费用美元 | 原/新秒 |", "| --- | --- | --- | ---: | ---: | ---: |"]
for p in protocol["projects"]:
    pair = {s["method"]: s for s in slots if s["project"] == p["name"]}
    old, new = (pair.get(m) for m in protocol["methods"])

    def outcome(s):
        return "未观察" if s is None else "通过" if s["delivery"] else "未完成"

    def metric(k, fmt):
        return "/".join(fmt(s[k]) if s else "—" for s in (old, new))

    lines.append(f"| {p['name']} | {outcome(old)} | {outcome(new)} | {metric('requests', str)} | {metric('cost_usd', str)} | {metric('wall_seconds', lambda v: format(v, '.2f'))} |")
(OUT / "project-table.md").write_text("\n".join(lines) + "\n")
print(json.dumps(verification, ensure_ascii=False))
