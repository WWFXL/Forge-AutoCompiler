#!/usr/bin/env python3
"""两个原未观察短任务的新独立参考，不续跑或回填六槽身份。"""

import argparse
import json
import os
import signal
import subprocess
from decimal import Decimal
from pathlib import Path

import forge_cxx_current_reference as ref
from forge_typed_evidence import audit, seal

IDENTITY = "cpp-build-current-cxx-short-reference-flash-v1"
OUTPUT = ref.OUTPUT.parent / "forge-cxx-short-reference-v1"
MANIFEST = ref.ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREG = "benchmarks/preregistrations/cpp-build-current-cxx-short-reference-flash-v1.md"
CAP = Decimal("3.50")


def prepare():
    if MANIFEST.exists() or OUTPUT.exists():
        raise RuntimeError("独立身份已存在")
    previous = json.loads((ref.OUTPUT / "result.json").read_text())
    previous_seal = audit(ref.OUTPUT)
    if previous["stop_reason"] != "remaining_time_or_budget" or any(
        r["agent_usage"]["unknown_usage_requests"] or not r["cleanup"]["succeeded"]
        for r in previous["rows"]
    ):
        raise RuntimeError("原批并非完整计量和清理的时间终结")
    parent = json.loads(ref.MANIFEST.read_text())
    expected = [s for s in parent["schedule"] if s["project"] in ("tinyxml2", "check")]
    if previous["unobserved_schedule"] != expected:
        raise RuntimeError("新前瞻任务必须恰为原未观察任务，不重跑失败")
    candidate = {
        **parent,
        "identity": IDENTITY,
        "schedule": expected,
        "projects": [
            p for p in parent["projects"] if p["name"] in ("tinyxml2", "check")
        ],
        "stage_max_cost_usd": str(CAP),
        "prior_cost_usd": previous["cumulative_known_cost_usd"],
        "new_slot_minimum_seconds": 900,
        "previous_identity_terminal": {
            "identity": ref.IDENTITY,
            "seal": previous_seal,
            "observed": len(previous["rows"]),
            "unobserved": len(previous["unobserved_schedule"]),
        },
        "interpretation": "新独立四槽探索性参考；原六槽仍2观察4未观察，不回填、合并分母或冒充预先完成六槽。",
    }
    for path in (str(Path(__file__).relative_to(ref.ROOT)), PREREG):
        candidate["components"][path] = ref.sha(ref.ROOT / path)
    ref.save(MANIFEST, candidate)
    print(json.dumps({"prepared": True, "slots": len(expected), "provider_calls": 0}))


def run():
    protocol = json.loads(MANIFEST.read_text())
    for name, expected in protocol["components"].items():
        if ref.sha(ref.ROOT / name) != expected:
            raise RuntimeError("运行组件变化：" + name)
    for name, expected in protocol["baseline"]["files"].items():
        if ref.sha(Path(protocol["baseline"]["path"]) / name) != expected:
            raise RuntimeError("基线快照变化")
    subprocess.run(
        ["bash", str(ref.ROOT / "scripts/require-docker-runtime.sh")], check=True
    )
    image = subprocess.check_output(
        ["docker", "image", "inspect", "autocompiler:gcc13", "--format", "{{.Id}}"],
        text=True,
    ).strip()
    for item in protocol["projects"]:
        if (
            ref.sha(item["source_archive"]) != item["task"]["source_archive_sha256"]
            or image != item["task"]["image_id"]
        ):
            raise RuntimeError("归档或镜像变化")
    if ref.remaining() < 900 or Decimal(protocol["prior_cost_usd"]) + CAP > 10:
        raise RuntimeError("原时窗或累计预算不足")
    OUTPUT.mkdir(exist_ok=False)
    ref.save(OUTPUT / "protocol.json", protocol)
    ref.save(
        OUTPUT / "execution.json",
        {
            "release": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True
            ).strip()
        },
    )
    from dotenv import load_dotenv

    for path in (ref.ROOT / ".env", ref.ROOT / "backend/.env"):
        if not os.environ.get("DEEPSEEK_API_KEY"):
            load_dotenv(path, override=False)
    model = ref.flash.base.PlanThinkingDeepSeek(
        model="deepseek-flash",
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
        max_tokens=32768,
        max_retries=0,
        timeout=240,
        reasoning_effort="low",
        extra_body={"thinking": {"type": "enabled"}},
    )
    rows, stop = [], None
    try:
        for index, slot in enumerate(protocol["schedule"], 1):
            known, unknown = ref.flash.base.charges(rows)
            reserve = (
                Decimal("1")
                if slot["method"] == "cxxcrafter_community_reference"
                else Decimal("3")
            )
            if ref.remaining() < 900 or known + unknown + reserve > CAP:
                stop = "remaining_time_or_budget"
                break
            folder = OUTPUT / f"slot-{index}"
            folder.mkdir()
            item = next(p for p in protocol["projects"] if p["name"] == slot["project"])
            try:
                if slot["method"] == "cxxcrafter_community_reference":
                    row = ref.run_cxx(protocol, item, folder, CAP - known)
                else:
                    with ref.execution_patch():
                        row = ref.replication.run_slot(
                            protocol=protocol, slot=slot, root=folder, model=model
                        )
            except Exception as exc:
                row = dict(
                    strict_completed=False,
                    error_class=type(exc).__name__,
                    error_message=str(exc)[:1500],
                    agent_usage=dict(
                        provider_requests=0,
                        total_tokens=0,
                        estimated_cost_usd_completed_responses="0",
                        unknown_usage_requests=0,
                    ),
                    cleanup=dict(succeeded=False),
                )
            rows.append({**row, **slot})
            ref.save(OUTPUT / f"progress-{index}.json", rows[-1])
            print(
                json.dumps(
                    {
                        k: rows[-1].get(k)
                        for k in (
                            "project",
                            "method",
                            "strict_completed",
                            "agent_usage",
                            "error_message",
                        )
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            if (
                row["agent_usage"]["unknown_usage_requests"]
                or not row["cleanup"]["succeeded"]
                or row.get("provider_stop")
            ):
                stop = "unknown_usage_cleanup_or_provider_identity"
                break
    finally:
        known, unknown = ref.flash.base.charges(rows)
        ref.save(
            OUTPUT / "result.json",
            dict(
                identity=IDENTITY,
                rows=rows,
                unobserved_schedule=protocol["schedule"][len(rows) :],
                stop_reason=stop,
                known_estimated_cost_usd=str(known),
                unknown_usage_reservation_usd=str(unknown),
                cumulative_known_cost_usd=str(
                    Decimal(protocol["prior_cost_usd"]) + known
                ),
            ),
        )
        seal(
            OUTPUT,
            protocol,
            ref.ROOT,
            sum(r["agent_usage"]["unknown_usage_requests"] for r in rows),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run"))
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare()
    else:

        def deadline(signum, frame):
            raise ref.StopPaid("原时窗截止，预留清理")

        signal.signal(signal.SIGALRM, deadline)
        signal.setitimer(signal.ITIMER_REAL, max(1, ref.remaining() - 180))
        run()
