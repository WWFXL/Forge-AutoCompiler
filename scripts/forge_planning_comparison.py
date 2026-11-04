#!/usr/bin/env python3
"""改进规划下基础/经验Forge的16次比较；复用共同执行与计费，不续跑旧身份。"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from decimal import Decimal
from pathlib import Path

import forge_simple_comparison as shared
from forge_build_simple_task import save
from forge_typed_evidence import digest, seal

from deerflow.compile.plan_workflow import PlanContractError

ROOT = shared.ROOT
IDENTITY = "cpp-build-planning-context-experience-flash-v1"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PREREG = ROOT / "benchmarks/preregistrations" / (IDENTITY + ".md")
PROJECTS = ("jsoncpp", "libsrtp", "libite", "highwayhash")
METHODS = ("forge", "forge_experience")


def schedule():
    rows = []
    for repeat in range(2):
        for i, project in enumerate(PROJECTS):
            order = METHODS if (repeat + i) % 2 == 0 else METHODS[::-1]
            first = len(rows) + 1
            rows.extend(
                dict(
                    slot=first + j,
                    project=project,
                    repetition=repeat + 1,
                    method=method,
                )
                for j, method in enumerate(order)
            )
    return rows


def candidate():
    value = shared.candidate()
    by_name = {p["name"]: p for p in value["projects"]}
    value.update(
        identity=IDENTITY,
        issue=681,
        kind="paired_development_mechanism_comparison",
        projects=[by_name[n] for n in PROJECTS],
        methods=list(METHODS),
        schedule=schedule(),
        limits=value["limits"] | dict(proposed_hours=4),
        planning=dict(
            output="SimpleBuildActions",
            format_corrections_per_agent_task=1,
            context="complete_tool_conversations_until_capacity",
            message_capacity_bytes=49000,
            convergence_warning_stalled_rounds=2,
            finalize_only_stalled_rounds=3,
        ),
        validation=dict(
            author_tests="actual_top_level_CMake_CTest_or_original_reference",
            zero_tests="error",
            boundary="实际作者测试入口按所选构建系统适配；不声称两系统测试集逐项相同，不和旧E42完整率相减",
        ),
        boundary="四项目均因已见失败选入，是开发配对比较；只估计共同改进Harness下短动作经验的条件性增量，不隔离每项修复因果，不称holdout或普遍效果。",
    )
    value["experience"].update(
        selection="matched_action_advice_v1",
        top_k=2,
        maximum_bytes=4096,
        retrieval="once_per_agent_task",
        abstain_when_unmatched=True,
    )
    value.pop("baseline")
    value["components"].update({p.relative_to(ROOT).as_posix(): digest(p) for p in (Path(__file__).resolve(), PREREG)})
    return value


def validate(value):
    if value["identity"] != IDENTITY or value["schedule"] != schedule() or value["methods"] != list(METHODS):
        raise PlanContractError("新比较的固定身份、方法或16槽顺序变化")
    fixture = {p["name"]: p for p in shared.load(shared.FIXTURE)["projects"]}
    if value["projects"] != [fixture[n] for n in PROJECTS] or digest(shared.FIXTURE) != value["fixture_sha256"]:
        raise PlanContractError("共同任务/参考变化")
    # 复用已有任务、来源隔离、组件/依赖检查；旧实验身份与四方法顺序不参与新比较。
    for item in value["projects"]:
        if digest(Path(item["source_archive"])) != item["task"]["source_archive_sha256"] or item["family"] in value["experience"]["source_families"]:
            raise PlanContractError("源码变化或经验族重叠")
    if digest(Path(value["experience"]["path"])) != value["experience"]["sha256"]:
        raise PlanContractError("经验库变化")
    for name, sha in value["components"].items():
        if digest(ROOT / name) != sha:
            raise PlanContractError("运行组件变化：" + name)
    for name, version in value["package_versions"].items():
        if shared.importlib.metadata.version(name) != version:
            raise PlanContractError("运行依赖变化：" + name)


def analyze(root):
    result = shared.load(root / "result.json")
    summary, details = {}, []
    for row in result["rows"]:
        folder = root / f"slot-{row['slot']:02d}-{row['project']}-{row['method']}"
        path = folder / "agent/events.jsonl"
        events = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        seen, reads, duplicate = set(), 0, 0
        for event in events:
            if event["event"] == "tool.started" and event.get("name") == "read_source":
                args = event["args"]
                key = (
                    args.get("path", "").removeprefix("/workspace/repo/"),
                    args.get("start_line", 1),
                )
                reads += 1
                duplicate += key in seen
                seen.add(key)
        details.append(
            dict(
                **{k: row[k] for k in ("slot", "project", "repetition", "method")},
                initial_plan_delivered=any(e["event"] == "simple.proposal_accepted" and e.get("revision") == 1 for e in events),
                format_rejections=sum(e["event"] == "simple.proposal_rejected" for e in events),
                source_reads=reads,
                repeated_source_reads=duplicate,
                experience_retrievals=[e for e in events if e["event"] == "experience.retrieved"],
                convergence_forced=sum(e["event"] == "planning.context" and e.get("finalize_only", False) for e in events),
            )
        )
    for method in METHODS:
        rows = [r for r in result["rows"] if r["method"] == method]
        slots = [s for s in details if s["method"] == method]
        summary[method] = dict(
            planned=8,
            observed=len(rows),
            unobserved=8 - len(rows),
            initial_plans=sum(s["initial_plan_delivered"] for s in slots),
            primary_completed=sum(r.get("layers", {}).get("primary_build_completed") is True for r in rows),
            full_completed=sum(r.get("layers", {}).get("full_completed") is True for r in rows),
            requests=sum(shared.usage(r)["requests"] for r in rows),
            estimated_cost_usd=str(sum((shared.usage(r)["cost"] for r in rows), Decimal(0))),
            total_wall_seconds=sum(r.get("arm_total_wall_seconds", 0) for r in rows),
            source_reads=sum(s["source_reads"] for s in slots),
            repeated_source_reads=sum(s["repeated_source_reads"] for s in slots),
            author_tests=dict(Counter(r.get("layers", {}).get("author_tests", "unobserved") for r in rows)),
        )
    return dict(
        identity=IDENTITY,
        summary=summary,
        slots=details,
        boundary="全部16槽；未观察不补值；项目两重复不当独立项目；旧结果只作历史问题描述。经验采纳不从检索命中推定。",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--check-prepared", action="store_true")
    group.add_argument("--run", action="store_true")
    group.add_argument("--analyze", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.analyze:
        print(json.dumps(analyze(args.analyze), ensure_ascii=False, indent=2))
        return 0
    if args.prepare:
        if MANIFEST.exists():
            raise PlanContractError("不覆盖已准备身份")
        value = candidate()
        validate(value)
        save(MANIFEST, value)
    else:
        value = shared.load(MANIFEST)
        validate(value)
    if not args.run:
        print(
            json.dumps(
                dict(
                    valid=True,
                    identity=IDENTITY,
                    candidate_sha256=digest(MANIFEST),
                    slots=16,
                    provider_calls=0,
                    credentials_read=False,
                )
            )
        )
        return 0
    if args.authorization is None or args.output is None:
        raise PlanContractError("需要此身份的新授权文件及独立输出目录")
    auth = shared.load(args.authorization)
    shared.validate_authorization(auth, digest(MANIFEST), identity=IDENTITY, maximum_hours=4)
    subprocess.run(
        ["bash", str(ROOT / "scripts/require-docker-runtime.sh")],
        check=True,
        timeout=30,
    )
    executor = shared.paid_executor(value)
    try:
        shared.execute(value, args.output, auth, executor)
    finally:
        if (args.output / "result.json").exists():
            save(args.output / "analysis.json", analyze(args.output))
            result = shared.load(args.output / "result.json")
            seal(
                args.output,
                value,
                ROOT,
                unknown_usage_requests=sum(shared.usage(r)["unknown"] for r in result["rows"]) + bool(result.get("unclosed_slot")),
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
