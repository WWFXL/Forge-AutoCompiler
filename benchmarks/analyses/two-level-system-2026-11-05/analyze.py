"""只读复算本轮原始响应，导出全分母与分层论文表，不修改运行证据。"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import forge_two_level_system_comparison as run  # noqa: E402
from forge_typed_evidence import canonical  # noqa: E402

RAW = Path("/home/yiwei/.codex/outputs/forge-two-level-system-comparison-flash-v1")


def main(output):
    output.mkdir(parents=True, exist_ok=False)
    result, protocol = (
        run.shared.load(RAW / "result.json"),
        run.shared.load(RAW / "protocol.json"),
    )
    seal, inventory = (
        run.shared.load(RAW / "seal.json"),
        run.shared.load(RAW / "inventory.json"),
    )
    assert canonical(inventory) == seal["inventory_canonical_sha256"]
    hashes = {r["path"]: r["sha256"] for r in inventory if r["type"] == "file"}
    analysis = run.analyze(RAW)
    rows, receipts, contexts = [], [], []
    counts = Counter()
    total_cost = Decimal(0)
    for row in result["rows"]:
        detail = next(r for r in analysis["slots"] if r["slot"] == row["slot"])
        folder = RAW / f"slot-{row['slot']:02d}-{row['project']}-{row['method']}"
        inputs = outputs = requests = 0
        cost = Decimal(0)
        for path in sorted(
            (folder / "agent").glob("response-*.json"),
            key=lambda p: int(p.stem.split("-")[-1]),
        ):
            relative = path.relative_to(RAW).as_posix()
            assert hashlib.sha256(path.read_bytes()).hexdigest() == hashes[relative]
            messages = [m for m in run.shared.load(path) if m["type"] == "ai"]
            assert len(messages) == 1
            message = messages[0]
            usage, model = (
                message["usage_metadata"],
                message["response_metadata"]["model_name"],
            )
            assert (
                model in run.shared.MODELS
                and usage["input_tokens"] + usage["output_tokens"]
                == usage["total_tokens"]
            )
            part = (
                Decimal("0.30") * usage["input_tokens"]
                + Decimal("1.20") * usage["output_tokens"]
            ) / 1_000_000
            inputs += usage["input_tokens"]
            outputs += usage["output_tokens"]
            requests += 1
            cost += part
            receipts.append(
                dict(
                    slot=row["slot"],
                    response=relative,
                    sha256=hashes[relative],
                    model=model,
                    input_tokens=usage["input_tokens"],
                    output_tokens=usage["output_tokens"],
                    estimated_cost_usd=str(part),
                )
            )
        recorded = run.shared.usage(row)
        assert (
            inputs == recorded["input_tokens"] and outputs == recorded["output_tokens"]
        )
        assert requests + recorded["unknown"] == recorded["requests"]
        assert abs(cost - recorded["cost"]) < Decimal("0.000000000001")
        assert cost == sum(
            (Decimal(v["estimated_cost_usd"]) for v in detail["phase_usage"].values()),
            Decimal(0),
        )
        counts.update(
            dict(requests=requests, input_tokens=inputs, output_tokens=outputs)
        )
        total_cost += cost
        layers, timings = row.get("layers", {}), row.get("timings", {})
        rows.append(
            dict(
                slot=row["slot"],
                project=row["project"],
                repetition=row["repetition"],
                method=row["method"],
                stratum=detail["stratum"],
                status=row["status"],
                primary_completed=layers.get("primary_build_completed"),
                full_completed=layers.get("full_completed"),
                author_tests=layers.get("author_tests", "unobserved"),
                delivery=layers.get("delivery", "unobserved"),
                clean_replay=layers.get("clean_replay", "unobserved"),
                source_unchanged=row.get("source_unchanged"),
                cleanup=row.get("cleanup", {}).get("succeeded"),
                requests=requests,
                input_tokens=inputs,
                output_tokens=outputs,
                estimated_cost_usd=str(cost),
                wall_seconds=row.get("arm_total_wall_seconds"),
                initial_planning_seconds=timings.get("initial_planning_seconds"),
                recovery_seconds=timings.get("recovery_agent_seconds"),
                phase_usage=detail["phase_usage"],
                recovery_tasks=sum(
                    event.get("event") == "agent.started"
                    and event.get("recovery") is True
                    for event in (
                        json.loads(line)
                        for line in (folder / "agent/events.jsonl")
                        .read_text()
                        .splitlines()
                    )
                ),
                recipe_selected=detail["recipe_selected"],
                verified_recipe_saved=(folder / "verified-simple-recipe.json").exists(),
                retrievals=detail["retrievals"],
                source_reads=detail["source_reads"],
                error_type=row.get("error_type"),
                error=row.get("error"),
            )
        )
        seen = set()
        for path in sorted((folder / "agent").glob("request-*.json")):
            packet = run.shared.load(path)
            for message in packet.get("messages", []):
                if message.get("type") != "human":
                    continue
                try:
                    data = json.loads(message["content"])
                except (ValueError, TypeError):
                    continue
                if "historical_build_experience" not in data:
                    continue
                context = data["historical_build_experience"]
                revision = (data.get("current_plan") or {}).get("revision", 0)
                key = (
                    revision,
                    json.dumps(context, sort_keys=True, ensure_ascii=False),
                )
                if key in seen:
                    continue
                seen.add(key)
                contexts.append(
                    dict(
                        slot=row["slot"],
                        project=row["project"],
                        revision=revision,
                        first_request=path.relative_to(RAW).as_posix(),
                        context=context,
                    )
                )
    for stratum, methods in analysis["summary"].items():
        for method, summary in methods.items():
            selected = [
                r
                for r in rows
                if r["method"] == method
                and (stratum == "all" or r["stratum"] == stratum)
            ]
            summary["phase_usage"] = {
                p: dict(
                    requests=sum(r["phase_usage"][p]["requests"] for r in selected),
                    estimated_cost_usd=str(
                        sum(
                            (
                                Decimal(r["phase_usage"][p]["estimated_cost_usd"])
                                for r in selected
                            ),
                            Decimal(0),
                        )
                    ),
                )
                for p in ("initial", "recovery", "tool_agent")
            }
            summary["recipe_hits"] = sum(r["recipe_selected"] for r in selected)
            summary["retrievals"] = sum(r["retrievals"] for r in selected)
            summary["source_reads"] = sum(r["source_reads"] for r in selected)
            summary["recovery_tasks"] = sum(r["recovery_tasks"] for r in selected)
            summary["verified_recipes_saved"] = sum(
                r["verified_recipe_saved"] for r in selected
            )
            summary["source_checks"] = dict(
                Counter(
                    "passed"
                    if r["source_unchanged"] is True
                    else "failed"
                    if r["source_unchanged"] is False
                    else "unobserved"
                    for r in selected
                )
            )
            summary["cleanup_checks"] = dict(
                Counter(str(r["cleanup"]) for r in selected)
            )
    pairs = [
        dict(
            project=name,
            repetition=repeat,
            methods={
                method: next(
                    (
                        r
                        for r in rows
                        if r["project"] == name
                        and r["repetition"] == repeat
                        and r["method"] == method
                    ),
                    None,
                )
                for method in run.METHODS
            },
        )
        for repeat in (1, 2)
        for name in run.PROJECTS
    ]
    conditional = {}
    for stratum in ("all", "exact_reuse", "no_recipe"):
        selected_pairs = [
            pair
            for pair in pairs
            if all(
                row is not None
                and row["full_completed"] is True
                and (stratum == "all" or row["stratum"] == stratum)
                for row in pair["methods"].values()
            )
        ]
        conditional[stratum] = {
            "pairs": len(selected_pairs),
            "interpretation": "按三方法共同完整结果条件化的辅助描述，不替代全分母",
            "methods": {
                method: {
                    "requests": sum(
                        pair["methods"][method]["requests"] for pair in selected_pairs
                    ),
                    "estimated_cost_usd": str(
                        sum(
                            (
                                Decimal(pair["methods"][method]["estimated_cost_usd"])
                                for pair in selected_pairs
                            ),
                            Decimal(0),
                        )
                    ),
                    "wall_seconds": sum(
                        pair["methods"][method]["wall_seconds"]
                        for pair in selected_pairs
                    ),
                }
                for method in run.METHODS
            },
        }
    with (output / "slots.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["slot"])
        writer.writeheader()
        writer.writerows(rows)
    run.save(output / "analysis.json", analysis)
    run.save(output / "pairs.json", pairs)
    run.save(output / "experience-contexts.json", contexts)
    verification = dict(
        valid=True,
        identity=protocol["identity"],
        inventory=seal["inventory_canonical_sha256"],
        **counts,
        total_tokens=counts["input_tokens"] + counts["output_tokens"],
        estimated_cost_usd=str(total_cost),
        unknown_usage_requests=sum(
            run.shared.usage(r)["unknown"] for r in result["rows"]
        ),
        billing_complete=result["billing_complete"],
        responses=receipts,
    )
    run.save(output / "response-verification.json", verification)
    summary = dict(
        identity=protocol["identity"],
        completed=result["completed_slots"],
        expected=result["expected_slots"],
        unobserved=len(result["unobserved"]),
        stop_reason=result["stop_reason"],
        estimated_cost_usd=str(total_cost),
        **counts,
        inventory=seal["inventory_canonical_sha256"],
        summary=analysis["summary"],
        common_full_three=conditional,
    )
    run.save(output / "summary.json", summary)
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k != "summary"},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
