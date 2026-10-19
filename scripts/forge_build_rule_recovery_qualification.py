#!/usr/bin/env python3
"""已见受控错误的零模型强规则恢复资格；不作公平效果估计。"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "backend/packages/harness"), str(REPO_ROOT / "scripts")]
from forge_build_plan_agent_canary import run_arm  # noqa: E402
from forge_build_plan_agent_repair import audit_frozen  # noqa: E402
from forge_build_plan_recovery_qualification import NAMES, controlled_plan, inspect_recovery  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.plan_agent_context import ContextCanaryMeter  # noqa: E402
from deerflow.compile.plan_cross_system import before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import BuildPlan, PlanContractError  # noqa: E402


def rule_revision(plan, handoff, source_names):
    """只消费当前坏方案、实际失败记录与源码文件名，不接收正确参考。"""
    if handoff.get("plan_sha256") != plan.fingerprint():
        raise PlanContractError("规则接管方案已过期")
    if handoff.get("reason") != "step_failed_or_expectation_missing":
        return None
    step = next((s for s in plan.steps if s.step_id == handoff.get("step_id")), None)
    records = handoff.get("recent_commands", [])
    if not step or not records:
        return None
    record = records[-1]
    if record["command"] != step.command or record["exit_code"] == 0 or record.get("timed_out"):
        return None
    words = shlex.split(step.command)
    if any(word in ("&&", ";", "|", "||", ">", "<") for word in words):
        return None
    log = record.get("output_tail", "")
    changed_id, command, rule = step.step_id, None, None
    target = re.search(r"No rule to make target '([^']+)'", log)
    if plan.build_system == "cmake" and step.role == "build" and words[:2] == ["cmake", "--build"] and words.count("--target") == 1 and target:
        index = words.index("--target")
        if index + 1 < len(words) and words[index + 1] == target.group(1):
            command, rule = shlex.join(words[:index] + words[index + 2 :]), "remove_missing_explicit_target"
    if plan.build_system == "make" and step.role == "build" and words and words[0] == "make":
        overrides = [word for word in words[1:] if word.startswith("CC=")]
        if len(overrides) == 1 and f"make: {overrides[0][3:]}: No such file or directory" in log:
            command, rule = shlex.join([word for word in words if word != overrides[0]]), "use_image_default_compiler"
    if plan.build_system == "autotools" and step.role == "configure" and words == ["./configure"] and "./configure: No such file or directory" in log and {"configure.ac", "Makefile.am", "autogen.sh"} <= set(source_names):
        preceding = plan.steps[: list(plan.steps).index(step)]
        noops = [candidate for candidate in preceding if candidate.role == "configure" and candidate.command == "true"]
        if len(noops) == 1:
            changed_id, command, rule = noops[0].step_id, "./autogen.sh", "execute_project_bootstrap_instead_of_noop"
    if command is None:
        return None
    payload = plan.model_dump(mode="json")
    payload["revision"] += 1
    changed = next(s for s in payload["steps"] if s["step_id"] == changed_id)
    changed.update(command=command, source=f"已见开发资格的有界规则：{rule}")
    return BuildPlan.model_validate(payload), rule


class NoProviderMeter(ContextCanaryMeter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tracker.limits = replace(self.tracker.limits, node_timeout_seconds=300, command_timeout_seconds=120, evaluator_timeout_seconds=180, replay_timeout_seconds=180, cleanup_timeout_seconds=120)

    def _before_request(self):
        raise PlanContractError("零模型规则资格禁止任何模型请求")


def planner_for(initial_reference, name):
    def planner(**kwargs):
        if kwargs.get("current_plan") is None:
            plan = controlled_plan(initial_reference, name)
            kwargs["meter"].ledger.append("qualification.initial_plan", source="与父相同的人工方案与受控注入", plan_sha256=plan.fingerprint())
            kwargs["meter"].ledger.save("initial-controlled-plan.json", plan.model_dump(mode="json"))
            return plan, "与父资格相同的人工初始方案及注入"
        # 正确参考只构造人工初始方案；规则接口不接收它，不读父模型修订。
        source = kwargs["source_root"]
        names = {n for n in ("configure.ac", "Makefile.am", "autogen.sh") if (source / n).is_file()}
        result = rule_revision(kwargs["current_plan"], kwargs["handoff"], names)
        if result is None:
            raise PlanContractError("规则未覆盖，资格停止而不调用模型")
        plan, rule = result
        kwargs["meter"].ledger.append("qualification.rule_revision", rule=rule, plan_sha256=plan.fingerprint())
        return plan, rule

    return planner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    if protocol["identity"] != "cpp-build-rule-recovery-qualification-v1" or protocol["provider_calls"] != 0 or protocol["deadline_utc"] != "2026-10-19T22:45:00Z":
        raise PlanContractError("规则资格身份或时窗错误")
    before_deadline(protocol["deadline_utc"], 1200)
    parent = Path(protocol["parent_evidence"])
    if audit(parent)["inventory_canonical_sha256"] != protocol["parent_inventory_sha256"]:
        raise PlanContractError("父恢复资格证据变化")
    prior = json.loads((parent / "protocol.json").read_text())
    if protocol["projects"] != prior["projects"]:
        raise PlanContractError("固定任务义务改变")
    references_root = Path(prior["source_qualification_evidence"])
    if audit_frozen(references_root)["inventory_canonical_sha256"] != prior["source_inventory_sha256"]:
        raise PlanContractError("人工初始方案来源变化")
    references = {r["name"]: r["plan"] for r in json.loads((references_root / "protocol.json").read_text())["projects"]}
    for name, expected in protocol["components"].items():
        if digest(REPO_ROOT / name) != expected:
            raise PlanContractError("冻结组件变化")
    subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    rows, reason = [], None
    try:
        for item in protocol["projects"]:
            try:
                before_deadline(protocol["deadline_utc"], 1200)
            except PlanContractError:
                reason = "deadline_reservation"
                break
            name = item["name"]
            row = run_arm(
                item={**item, "name": f"{name}-repair"},
                arm="plan",
                protocol=protocol,
                root=root,
                reference=references[name],
                model=None,
                meter_factory=NoProviderMeter,
                planner=planner_for(references[name], name),
                command_timeout_seconds=120,
                replay_timeout_seconds=180,
            )
            observation = inspect_recovery(root / f"{name}-repair-plan", row, name, "repair")
            row.update(project=name, mode="repair", recovery_observation=observation)
            rows.append(row)
            print(json.dumps({"name": name, "strict_completed": row["strict_completed"], "observation": observation, "usage": row["agent_usage"]}), flush=True)
            if not row["cleanup"]["succeeded"] or row["agent_usage"]["model_requests"]:
                reason = "cleanup_or_forbidden_model_request"
                break
    finally:
        unobserved = [{"project": item["name"], "mode": "repair", "arm": "plan", "status": "not_observed", "reason": reason} for item in protocol["projects"][len(rows) :]]
        write_json(
            root / "result.json",
            {"identity": protocol["identity"], "kind": "zero_provider_rule_qualification", "provider_calls": 0, "arms": rows, "unobserved_schedule": unobserved, "known_estimated_cost_usd": "0", "stopping_reason": reason},
        )
        print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
    return 0 if len(rows) == len(NAMES) and not unobserved and all(r["recovery_observation"]["expected_observation"] and r["agent_usage"]["model_requests"] == 0 for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
