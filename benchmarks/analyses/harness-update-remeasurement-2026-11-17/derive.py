"""从封存原件重建派生表与核对收据；不调用Provider、不修改原件。"""

import difflib
import sys
import csv
import hashlib
import json
import subprocess
import tarfile
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = Path(
    "/home/yiwei/.codex/outputs/forge-harness-update-repaired-comparison-flash-2026-11-17-v1"
)
OUT = ROOT / "benchmarks/analyses/harness-update-remeasurement-2026-11-17"
OUT.mkdir(exist_ok=True, parents=True)
a = json.loads((RAW / "analysis.json").read_text())
r = json.loads((RAW / "result.json").read_text())
assert r["completed_slots"] == r["expected_slots"] == 36
assert r["stop_reason"] is None and r["unclosed_slot"] is None and r["billing_complete"]
responses = Counter()
total_in = total_out = 0
refs = set()
source_changes = []
for row in r["rows"]:
    folder = RAW / f"slot-{row['slot']:02d}-{row['project']}-{row['method']}"
    ins = outs = requests = 0
    for f in (folder / "agent").glob("response-*.json"):
        data = json.loads(f.read_text())
        for m in data:
            meta = m["response_metadata"]
            responses[meta["model_name"]] += 1
            usage = meta["token_usage"]
            ins += usage["prompt_tokens"]
            outs += usage["completion_tokens"]
            requests += 1
    u = row["agent_usage"]
    assert (ins, outs, requests) == (
        u["input_tokens"],
        u["output_tokens"],
        u["model_requests"],
    )
    cost = (
        Decimal(ins) * Decimal("0.30") / 1000000
        + Decimal(outs) * Decimal("1.20") / 1000000
    )
    assert cost == Decimal(str(u["estimated_cost_usd_completed_responses"]))
    total_in += ins
    total_out += outs
    assert u["unknown_usage_requests"] == 0 and row["cleanup"]["succeeded"]
    for f in folder.glob(".compile-sessions/simple-system/*/session.json"):
        s = json.loads(f.read_text())
        refs.update(s[k] for k in ("container_id", "container_name") if s.get(k))
        for replay in s.get("replay_attempts", []):
            refs.update(
                replay[k] for k in ("container_id", "container_name") if replay.get(k)
            )
    changes = row.get("source_protection", {}).get("changes", [])
    original = [x["path"] for x in changes if x.get("before") is not None]
    source_changes.append(
        dict(
            slot=row["slot"],
            project=row["project"],
            method=row["method"],
            original_input_changes=original,
            added=sum(x["kind"] == "added" for x in changes),
            source_review=row.get("source_review"),
        )
    )
assert responses == {
    "deepseek-flash": sum(x["agent_usage"]["model_requests"] for x in r["rows"])
}
present = []
for ref in sorted(refs):
    c = subprocess.run(
        ["docker", "container", "inspect", ref],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if c.returncode == 0:
        present.append(ref)
    else:
        assert "No such container" in c.stderr or "No such object" in c.stderr, c.stderr
assert not present
seal = json.loads((RAW / "seal.json").read_text())
verification = dict(
    identity=a["identity"],
    closed_slots=36,
    request_responses=dict(responses),
    input_tokens=total_in,
    output_tokens=total_out,
    total_tokens=total_in + total_out,
    estimated_cost_usd=str(
        Decimal(total_in) * Decimal(".30") / 1000000
        + Decimal(total_out) * Decimal("1.20") / 1000000
    ),
    unknown_usage_requests=0,
    billing_recomputed=True,
    cleanup_passed=36,
    container_references_checked=len(refs),
    container_references_present=present,
    source_changes=source_changes,
    raw_inventory_canonical_sha256=seal["inventory_canonical_sha256"],
    raw_result_sha256=hashlib.sha256((RAW / "result.json").read_bytes()).hexdigest(),
    raw_analysis_sha256=hashlib.sha256(
        (RAW / "analysis.json").read_bytes()
    ).hexdigest(),
)
# 原输入差异后审：不修改封存结果中的pending_review字段。

fixture = json.loads(
    (
        ROOT / "benchmarks/fixtures/harness-update-repaired-comparison-v1/tasks.json"
    ).read_text()
)
reviews = []
for change in source_changes:
    if not change["original_input_changes"]:
        continue
    folder = next(RAW.glob(f"slot-{change['slot']:02d}-*"))
    workspace = next(folder.glob(".compile-sessions/simple-system/*/workspace/repo"))
    item = next(x for x in fixture["projects"] if x["name"] == change["project"])
    with tarfile.open(item["source_archive"]) as archive:
        for path in change["original_input_changes"]:
            original = archive.extractfile(path).read().decode()
            current = (workspace / path).read_text()
            if change["project"] == "libconfuse":

                def normalize(text):
                    return "\n".join(
                        line
                        for line in text.splitlines()
                        if not line.startswith("#") and "POT-Creation-Date:" not in line
                    )

                assert normalize(original) == normalize(current)
                assessment = "作者gettext更新日期/位置注释，翻译内容未变"
            elif change["project"] == "libtasn1":
                assert current.replace("#include <config.h>\n", "", 1) == original
                assessment = "辅助程序仅增加config.h包含，默认目标未跳过，属构建适配"
            elif change["project"] == "libffi":
                replacement = "m4_ifdef([LT_SYS_SYMBOL_USCORE], [LT_SYS_SYMBOL_USCORE], [sys_symbol_underscore=${lt_cv_sys_symbol_underscore:-no}])"
                assert current == original.replace(
                    "LT_SYS_SYMBOL_USCORE\n", replacement + "\n", 1
                )
                assessment = (
                    "宏兼容回退；当前固定Linux平台通过，不能据此证明其他平台检测等价"
                )
            else:
                raise AssertionError("未审查的原输入变化")
            reviews.append(
                dict(
                    slot=change["slot"],
                    path=path,
                    assessment=assessment,
                    diff="".join(
                        difflib.unified_diff(
                            original.splitlines(True),
                            current.splitlines(True),
                            fromfile="original/" + path,
                            tofile="current/" + path,
                        )
                    ),
                )
            )
(OUT / "source-review.json").write_text(
    json.dumps(reviews, ensure_ascii=False, indent=2) + "\n"
)
# 仅重放真实文本错误消息在观察器中的处理，不连接Provider或执行构建。

sys.path.insert(0, str(ROOT / "backend/packages/harness"))
from deerflow.compile.simple_planning_context import PlanningContext  # noqa: E402

folder = next(RAW.glob("slot-23-*"))
events = [
    json.loads(line)
    for line in (folder / "agent/events.jsonl").read_text().splitlines()
]
message = next(
    e["result"]["content"]
    for e in reversed(events)
    if e.get("event") == "tool.completed"
    and e.get("name") == "inspect_build_environment"
)
try:
    PlanningContext({}).observe(
        "inspect_build_environment",
        {"kind": "pkgconfig", "query": "freetype2"},
        message,
    )
except json.JSONDecodeError as error:
    replay = dict(
        provider_calls=0,
        original_slot=23,
        reproduced=True,
        error_type=type(error).__name__,
        error=str(error),
        location="simple_planning_context.py:110",
        input_sha256=hashlib.sha256(message.encode()).hexdigest(),
    )
else:
    raise AssertionError("原失败未重现")
(OUT / "tool-error-replay.json").write_text(
    json.dumps(replay, ensure_ascii=False, indent=2) + "\n"
)
verification["source_review_file"] = "source-review.json"
verification["tool_error_replay_file"] = "tool-error-replay.json"
(OUT / "analysis.json").write_bytes((RAW / "analysis.json").read_bytes())
(OUT / "verification.json").write_text(
    json.dumps(verification, ensure_ascii=False, indent=2) + "\n"
)
fields = [
    "slot",
    "project",
    "method",
    "main_build_completed",
    "reproducible_delivery_completed",
    "initial_requests",
    "recovery_requests",
    "requests",
    "input_tokens",
    "output_tokens",
    "estimated_cost_usd",
    "wall_seconds",
]
with (OUT / "slots.csv").open("w") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for x in a["slots"]:
        w.writerow(
            dict(
                slot=x["slot"],
                project=x["project"],
                method=x["method"],
                main_build_completed=x["layers"].get(
                    "main_build_task_completed", False
                ),
                reproducible_delivery_completed=x["layers"].get(
                    "reproducible_delivery_completed", False
                ),
                initial_requests=x["phases"]["initial"]["requests"],
                recovery_requests=x["phases"]["recovery"]["requests"],
                requests=x["usage"]["requests"],
                input_tokens=x["usage"]["input_tokens"],
                output_tokens=x["usage"]["output_tokens"],
                estimated_cost_usd=x["usage"]["cost"],
                wall_seconds=f"{x['wall_seconds']:.6f}",
            )
        )
table = [
    "| 项目 | 主构建 原/新 | 可复现交付 原/新 | 请求 原/新 | 费用美元 原/新 | 含重建耗时秒 原/新 |",
    "|---|---|---|---|---|---|",
]
for project in dict.fromkeys(x["project"] for x in a["slots"]):
    old, new = sorted(
        [x for x in a["slots"] if x["project"] == project], key=lambda x: x["method"]
    )

    def pair(fn):
        return f"{fn(old)}/{fn(new)}"

    def mark(v):
        return "通过" if v else "未完成"

    table.append(
        "| "
        + project
        + " | "
        + pair(lambda x: mark(x["layers"].get("main_build_task_completed", False)))
        + " | "
        + pair(
            lambda x: mark(x["layers"].get("reproducible_delivery_completed", False))
        )
        + " | "
        + pair(lambda x: x["usage"]["requests"])
        + " | "
        + pair(lambda x: f"{Decimal(x['usage']['cost']):.6f}")
        + " | "
        + pair(lambda x: f"{x['wall_seconds']:.2f}")
        + " |"
    )
(OUT / "project-table.md").write_text("\n".join(table) + "\n")
print(
    json.dumps(
        {k: v for k, v in verification.items() if k != "source_changes"},
        ensure_ascii=False,
        indent=2,
    )
)
