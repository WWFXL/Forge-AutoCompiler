#!/usr/bin/env python3
"""冻结六项目双重复配对比较；不把未观察槽位填成失败。"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "backend/packages/harness"), str(REPO_ROOT / "scripts")]

from forge_build_plan_agent_canary import run_arm  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.plan_agent import PlanTask  # noqa: E402
from deerflow.compile.plan_agent_context import ContextCanaryMeter, propose_with_context, run_tool_agent_with_context  # noqa: E402
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek  # noqa: E402
from deerflow.compile.plan_cross_system import SharedResearchBudget, before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402


def make_schedule(names, repeats=2):
    rows = []
    for repetition in range(1, repeats + 1):
        for index, name in enumerate(names):
            arms = ("plan", "tool") if (index + repetition) % 2 else ("tool", "plan")
            rows.extend({"project": name, "repetition": repetition, "arm": arm} for arm in arms)
    return rows


def charged_cost(rows):
    return sum((Decimal(str(row["agent_usage"]["estimated_cost_usd_completed_responses"])) + Decimal("0.40") * row["agent_usage"]["unknown_usage_requests"] for row in rows), Decimal(0))


def arm_admissible(rows, stage_cap=Decimal("12")):
    # 既有meter在每个请求前预留0.40、单臂上限1.50；整阶段再预留下一整臂。
    return charged_cost(rows) + Decimal("1.50") <= stage_cap


def validate(protocol):
    if protocol["identity"] != "cpp-build-plan-agent-paired-comparison-v1" or protocol["max_estimated_cost_usd"] != 12 or protocol["deadline_utc"] != "2026-10-19T23:00:00Z":
        raise PlanContractError("配对比较身份、预算或截止错误")
    before_deadline(protocol["deadline_utc"], 1800)
    projects = protocol["projects"]
    names = [item["name"] for item in projects]
    if len(set(names)) != 6 or Counter(item["task"]["build_system"] for item in projects) != Counter(cmake=2, make=2, autotools=2):
        raise PlanContractError("六项目三系统边界不符")
    groups = list(protocol["family_groups"].values())
    if len(groups) != 5 or Counter(name for group in groups for name in group) != Counter(names):
        raise PlanContractError("维护者关联项目必须在同一重采样组，不能把重复当独立项目")
    if protocol["schedule"] != make_schedule(names) or protocol["gate_schedule"] != make_schedule(names, 1):
        raise PlanContractError("配对、重复或顺序被更改")
    control_root = Path(protocol["control_evidence"])
    if audit(control_root)["inventory_canonical_sha256"] != protocol["control_inventory_sha256"]:
        raise PlanContractError("状态控制父证据变化")
    controls = json.loads((control_root / "result.json").read_text())["cases"]
    if len(controls) != 7 or not all(row["expected_observation"] for row in controls):
        raise PlanContractError("状态/验证控制尚未闭合")
    references = {}
    for parent in protocol["reference_evidence"]:
        root = Path(parent["path"])
        if audit(root)["inventory_canonical_sha256"] != parent["inventory_sha256"]:
            raise PlanContractError("参考父证据变化")
        qualified = {row["name"] for row in json.loads((root / "result.json").read_text())["projects"] if row.get("qualified")}
        for item in json.loads((root / "protocol.json").read_text())["projects"]:
            if item["name"] in qualified:
                references[item["name"]] = item
    for item in projects:
        if item["name"] not in references:
            raise PlanContractError("比较项目未通过固定完整参考资格")
        reference = references[item["name"]]
        task = PlanTask.model_validate(item["task"])
        original = reference["plan"]
        for key in ("plan_id", "repository_url", "commit_sha", "image_id", "source_archive_sha256", "build_system", "artifact_paths"):
            if task.model_dump(mode="json")[key] != original[key]:
                raise PlanContractError("比较任务偏离参考身份或交付")
        if task.model_dump(mode="json")["verification_steps"] != [step for step in original["steps"] if step["role"] == "smoke"]:
            raise PlanContractError("比较不能改完整验证义务")
        if digest(Path(item["source_archive"])) != task.source_archive_sha256:
            raise PlanContractError("比较源码归档变化")
    for name, expected in protocol["components"].items():
        if digest(REPO_ROOT / name) != expected:
            raise PlanContractError("比较运行组件变化")
    return references


def execute_schedule(protocol, root, model, references, *, qualify=False, executor=run_arm, results=None):
    rows = [] if results is None else results
    schedule = protocol["gate_schedule"] if qualify else protocol["schedule"]
    projects = {item["name"]: item for item in protocol["projects"]}
    stopping_reason = None
    for slot in schedule:
        try:
            before_deadline(protocol["deadline_utc"], 1800)
        except PlanContractError:
            stopping_reason = "deadline_reservation"
            break
        if not qualify and not arm_admissible(rows):
            stopping_reason = "stage_cost_reservation"
            break
        item = {**projects[slot["project"]], "name": f"{slot['project']}-r{slot['repetition']}"}
        started = time.monotonic()
        row = executor(
            item=item,
            arm=slot["arm"],
            protocol=protocol,
            root=root,
            model=model,
            reference=references[slot["project"]]["plan"] if qualify else None,
            meter_factory=ContextCanaryMeter,
            planner=propose_with_context,
            tool_runner=run_tool_agent_with_context,
            probe_reads=qualify,
        )
        # 原始单臂记录保留复用runner的kind；阶段role由冻结协议和此schedule定义。
        rows.append({**row, "project": slot["project"], "repetition": slot["repetition"], "arm_total_wall_seconds": time.monotonic() - started})
        print(json.dumps({key: rows[-1].get(key) for key in ("project", "repetition", "arm", "strict_completed", "agent_usage")}), flush=True)
        if not row["cleanup"]["succeeded"] or row["agent_usage"]["unknown_usage_requests"]:
            stopping_reason = "cleanup_or_unknown_usage"
            break
        if charged_cost(rows) > Decimal(str(protocol["max_estimated_cost_usd"])):
            raise PlanContractError("阶段计量超出冻结上界，停止且保留全部证据")
    return rows, [{**slot, "status": "not_observed", "reason": stopping_reason} for slot in schedule[len(rows) :]], stopping_reason


def analyze(protocol, payload):
    """固定任务集的配对描述；缺槽时不比较便利子集，不做非劣或总体推断。"""
    arms = payload["arms"]
    actual = [(row["project"], row["repetition"], row["arm"]) for row in arms]
    expected = [(row["project"], row["repetition"], row["arm"]) for row in protocol["schedule"]]
    if actual != expected[: len(actual)]:
        raise PlanContractError("观察顺序、重复或配对身份异常")
    fully_observed = len(actual) == 24 and not payload["unobserved_schedule"]
    usage_complete = all(row["agent_usage"].get("cost_and_usage_complete", False) for row in arms)
    result = {"fully_observed": fully_observed, "usage_complete": usage_complete, "observed_arms": len(arms), "paired_comparison_permitted": fully_observed and usage_complete}
    metrics = {
        "strict_completed": lambda row: int(row["strict_completed"]),
        "cost_usd": lambda row: float(row["agent_usage"]["estimated_cost_usd_completed_responses"]),
        "requests": lambda row: row["agent_usage"]["model_requests"],
        "tokens": lambda row: row["agent_usage"]["recorded_tokens"],
        "commands": lambda row: row["agent_usage"].get("commands", 0),
        "wall_seconds": lambda row: row["arm_total_wall_seconds"],
    }
    result["observed_totals"] = {arm: {name: sum(value(row) for row in arms if row["arm"] == arm) for name, value in metrics.items()} for arm in ("plan", "tool")}
    if not result["paired_comparison_permitted"]:
        return result
    projects = [item["name"] for item in protocol["projects"]]
    pairs = {}
    for row in arms:
        pairs.setdefault((row["project"], row["repetition"]), {})[row["arm"]] = row
    counts = Counter((int(pair["plan"]["strict_completed"]), int(pair["tool"]["strict_completed"])) for pair in pairs.values())
    result["pairs"] = {"both_success": counts[(1, 1)], "both_failure": counts[(0, 0)], "plan_only_success": counts[(1, 0)], "tool_only_success": counts[(0, 1)]}
    result["project_means"] = {project: {arm: {name: sum(value(row) for row in arms if row["project"] == project and row["arm"] == arm) / 2 for name, value in metrics.items()} for arm in ("plan", "tool")} for project in projects}
    result["plan_minus_tool"] = {}
    for name in metrics:
        differences = {project: result["project_means"][project]["plan"][name] - result["project_means"][project]["tool"][name] for project in projects}
        groups = list(protocol["family_groups"].values())
        rng = random.Random(20261020)
        samples = []
        for _ in range(20000):
            selected = [project for group in (rng.choice(groups) for _ in groups) for project in group]
            samples.append(sum(differences[project] for project in selected) / len(selected))
        samples.sort()
        result["plan_minus_tool"][name] = {"mean_per_arm": sum(differences.values()) / 6, "family_resampling_percentile_95": [samples[499], samples[19499]]}
    result["resampling_scope"] = "仅固定六仓库/五维护者关联组的配对重采样描述；非OSS总体置信区间，不作显著性、非劣或机制增量判断"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--shared-budget-root", type=Path, required=True)
    parser.add_argument("--qualify", action="store_true")
    parser.add_argument("--gate-root", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    references = validate(protocol)
    shared = SharedResearchBudget(args.shared_budget_root)
    if shared.authorization["deadline_utc"] != protocol["deadline_utc"] or shared.authorization["max_new_provider_cost_usd"] != 20:
        raise PlanContractError("共享用户授权不匹配")
    if args.validate_only:
        print(json.dumps({"valid": True, "provider_calls": 0}))
        return 0
    if not args.qualify:
        if args.gate_root is None:
            raise PlanContractError("缺少同协议零Provider十二臂门禁")
        audit(args.gate_root)
        gate = json.loads((args.gate_root / "result.json").read_text())
        if (
            digest(args.gate_root / "protocol.json") != digest(args.protocol)
            or gate["kind"] != "scripted_engineering_gate"
            or gate["unobserved_schedule"]
            or len(gate["arms"]) != 12
            or not all(row["strict_completed"] and row["agent_usage"]["recorded_tokens"] == 0 for row in gate["arms"])
        ):
            raise PlanContractError("同协议零Provider门禁未闭合")
    subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    (root / "authorization.json").write_bytes((args.shared_budget_root / "authorization.json").read_bytes())
    if not args.qualify:
        shared.append({"event": "stage.started", "identity": protocol["identity"], "reserved_cost_usd": "12", "protocol_sha256": digest(args.protocol), "evidence_root": str(root)})
    rows, unobserved, reason = [], [], "initialization_not_completed"
    lifecycle_complete = False
    try:
        model = None
        if not args.qualify:
            key = os.environ.get("DEEPSEEK_API_KEY")
            if not key:
                raise PlanContractError("缺少已授权Provider凭据")
            model = PlanThinkingDeepSeek(model="deepseek-v4-pro", api_key=key, base_url="https://api.deepseek.com", max_tokens=32768, max_retries=0, timeout=240, reasoning_effort="low", extra_body={"thinking": {"type": "enabled"}})
        rows, unobserved, reason = execute_schedule(protocol, root, model, references, qualify=args.qualify, results=rows)
        lifecycle_complete = True
    finally:
        if not lifecycle_complete:
            unobserved = [{**slot, "status": "not_observed_or_unclosed", "reason": reason} for slot in (protocol["gate_schedule"] if args.qualify else protocol["schedule"])[len(rows) :]]
        known = sum((Decimal(str(row["agent_usage"]["estimated_cost_usd_completed_responses"])) for row in rows), Decimal(0))
        unknown = sum(row["agent_usage"]["unknown_usage_requests"] for row in rows)
        write_json(
            root / "result.json",
            {
                "identity": protocol["identity"],
                "kind": "scripted_engineering_gate" if args.qualify else "prospective_paired_comparison",
                "arms": rows,
                "unobserved_schedule": unobserved,
                "stopping_reason": reason,
                "known_estimated_cost_usd": str(known),
                "unknown_usage_reservation_usd": str(Decimal("0.40") * unknown),
            },
        )
        sealed = seal(root, protocol, REPO_ROOT, unknown)
        if not args.qualify and lifecycle_complete:
            shared.append(
                {
                    "event": "stage.completed",
                    "identity": protocol["identity"],
                    "charged_cost_usd": str(charged_cost(rows)),
                    "known_estimate_usd": str(known),
                    "unknown_reservation_usd": str(Decimal("0.40") * unknown),
                    "inventory_sha256": sealed["inventory_canonical_sha256"],
                }
            )
    return 0 if len(rows) == (12 if args.qualify else 24) and not unobserved and (not args.qualify or all(row["strict_completed"] for row in rows)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
