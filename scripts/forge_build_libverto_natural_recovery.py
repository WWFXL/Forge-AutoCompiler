"""真实已见失败的后验单例零模型恢复资格，不估自然恢复率。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "backend/packages/harness"), str(REPO_ROOT / "scripts")]
from forge_build_plan_agent_canary import run_arm  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.plan_agent_context import ContextCanaryMeter  # noqa: E402
from deerflow.compile.plan_cross_system import before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import BuildPlan, PlanContractError  # noqa: E402


class NoProviderMeter(ContextCanaryMeter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tracker.limits = replace(self.tracker.limits, node_timeout_seconds=180, command_timeout_seconds=60, evaluator_timeout_seconds=120, replay_timeout_seconds=120, cleanup_timeout_seconds=60)

    def _before_request(self):
        raise PlanContractError("自然恢复零模型资格禁止模型请求")


def revise(plan, handoff, suite_log, config_log):
    if plan.revision != 1 or handoff.get("plan_sha256") != plan.fingerprint():
        raise PlanContractError("只允许当前初始方案的一次修订")
    step = next(s for s in plan.steps if s.step_id == "configure")
    recent = handoff.get("recent_commands", [])
    if handoff.get("reason") != "step_failed_or_expectation_missing" or handoff.get("step_id") != "check" or not recent:
        raise PlanContractError("未观察预定实际测试失败")
    record = recent[-1]
    if record["command"] != "make check" or record["exit_code"] != 2 or record.get("timed_out"):
        raise PlanContractError("实际失败类型不吻合")
    if step.command != "./configure --disable-shared --enable-static" or "BUILTIN_MODULE=''" not in config_log:
        raise PlanContractError("配置前提不吻合")
    assertion = "Assertion `(ctx = verto_default(MODULES[i], VERTO_EV_TYPE_NONE))' failed."
    if not all(s in suite_log for s in ("# TOTAL: 6", "# PASS:  0", "# FAIL:  6")) or suite_log.count(assertion) != 6:
        raise PlanContractError("六项共享上下文断言未复现")
    payload = plan.model_dump(mode="json")
    payload["revision"] = 2
    changed = next(s for s in payload["steps"] if s["step_id"] == "configure")
    changed.update(command="./configure --enable-shared --enable-static", source="已见自然失败后验诊断：保留静态交付并恢复默认动态后端构建")
    return BuildPlan.model_validate(payload)


def planner_for(initial):
    def planner(**kwargs):
        if kwargs.get("current_plan") is None:
            return BuildPlan.model_validate(initial), "重放已封存真实初始方案，不重新规划"
        source = kwargs["source_root"]
        plan = revise(kwargs["current_plan"], kwargs["handoff"], (source / "tests/test-suite.log").read_text(), (source / "config.log").read_text())
        kwargs["meter"].ledger.append("qualification.natural_revision", plan_sha256=plan.fingerprint(), rule="enable_shared_preserving_static_after_six_context_assertions")
        return plan, "固定单项配置修订，其余任务和完整测试不变"

    return planner


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    if protocol["identity"] != "cpp-build-libverto-natural-recovery-v1" or protocol["provider_calls"] != 0:
        raise PlanContractError("身份或零模型边界不符")
    before_deadline(protocol["deadline_utc"], 600)
    parent = Path(protocol["parent_root"])
    if audit(parent)["inventory_canonical_sha256"] != protocol["parent_inventory_sha256"]:
        raise PlanContractError("父封存变化")
    prior = json.loads((parent / "protocol.json").read_text())
    if protocol["projects"] != [p for p in prior["projects"] if p["name"] == "libverto"]:
        raise PlanContractError("固定源/任务改变")
    if digest(parent / protocol["initial_plan_path"]) != protocol["initial_plan_sha256"]:
        raise PlanContractError("原始真实方案变化")
    initial = json.loads((parent / protocol["initial_plan_path"]).read_text())
    if initial != protocol["initial_plan"]:
        raise PlanContractError("初始方案不是原真实方案")
    for name, expected in protocol["components"].items():
        if digest(REPO_ROOT / name) != expected:
            raise PlanContractError("组件变化")
    subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    before_deadline(protocol["deadline_utc"], 600)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    rows = []
    try:
        row = run_arm(item=protocol["projects"][0], arm="plan", protocol=protocol, root=root, reference=initial, meter_factory=NoProviderMeter, planner=planner_for(initial), command_timeout_seconds=60, replay_timeout_seconds=120)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    finally:
        write_json(root / "result.json", {"identity": protocol["identity"], "kind": "posthoc_natural_failure_qualification", "provider_calls": 0, "arms": rows, "known_estimated_cost_usd": "0"})
        print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
    return 0 if len(rows) == 1 and rows[0]["strict_completed"] and rows[0]["agent_usage"]["model_requests"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
