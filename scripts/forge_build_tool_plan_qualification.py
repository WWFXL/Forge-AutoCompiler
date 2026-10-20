#!/usr/bin/env python3
"""零Provider工具方案资格；不支持及失败停在交接，不调用恢复模型。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "backend/packages/harness"), str(REPO_ROOT / "scripts")]

from forge_build_full_strategy_cleanup_continuation import classified_arm  # noqa: E402
from forge_build_full_strategy_runtime import StrategyMeter  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.plan_agent import PlanTask  # noqa: E402
from deerflow.compile.plan_cross_system import before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402
from deerflow.compile.tool_plan import ToolPlanNeedsAgent, generate_tool_plan  # noqa: E402

IDENTITY = "cpp-build-tool-plan-qualification-v1"
PROJECTS = ("buffer", "uncrustify", "libverto")


class NoProviderMeter(StrategyMeter):
    """任何意外模型请求在请求开始及网络调用前立即拒绝。"""

    def wrap_model_call(self, request, handler):
        raise PlanContractError("零Provider资格禁止调用模型")

    def _before_request(self):
        raise PlanContractError("零Provider资格禁止登记模型请求")


def qualification_planner(*, task, source_root, meter, current_plan=None, handoff=None, **kwargs):
    if current_plan is not None:
        meter.ledger.save("qualification-needs-agent.json", {"current_plan_sha256": current_plan.fingerprint(), "handoff": handoff, "provider_calls": 0})
        raise ToolPlanNeedsAgent("工具初始方案实际失败；保留交接，零Provider身份不执行模型恢复")
    try:
        started = time.monotonic()
        plan, receipt = generate_tool_plan(task, source_root)
    except ToolPlanNeedsAgent as exc:
        meter.ledger.save("tool-plan-abstention.json", {"reason": str(exc), "provider_calls": 0})
        raise
    meter.ledger.save("plan-1.json", plan.model_dump(mode="json"))
    meter.ledger.save("tool-plan-receipt.json", {**receipt, "generation_seconds": time.monotonic() - started})
    return plan, "确定性工具初始方案"


def validate(protocol):
    if protocol["identity"] != IDENTITY or protocol["provider_calls"] != 0 or protocol["max_new_provider_cost_usd"] != 0:
        raise PlanContractError("资格身份或零费用边界错误")
    if tuple(p["name"] for p in protocol["projects"]) != PROJECTS:
        raise PlanContractError("开发项目固定，不允许替换或便利子集")
    for name, sha in protocol["components"].items():
        if digest(REPO_ROOT / name) != sha:
            raise PlanContractError("冻结组件变化：" + name)
    role = Path(protocol["role_evidence"]["root"])
    if audit(role)["inventory_canonical_sha256"] != protocol["role_evidence"]["inventory_sha256"]:
        raise PlanContractError("开发角色证据变化")
    roles = {r["name"]: r for r in json.loads((role / "result.json").read_text())["projects"]}
    for row in protocol["projects"]:
        if row != {k: roles[row["name"]][k] for k in ("name", "task", "source_archive", "source_paths")}:
            raise PlanContractError("任务、源码或开发暴露变化")
        if digest(Path(row["source_archive"])) != PlanTask.model_validate(row["task"]).source_archive_sha256:
            raise PlanContractError("源码归档变化")
    before_deadline(protocol["deadline_utc"], 120)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    validate(protocol)
    if args.validate_only:
        print(json.dumps({"valid": True, "provider_calls": 0}))
        return 0
    subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    os.environ["COMPILE_DOCKER_CLEANUP_TIMEOUT_SECONDS"] = "120"
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    rows, reason = [], None
    try:
        for item in protocol["projects"]:
            try:
                before_deadline(protocol["deadline_utc"], 2100)
            except PlanContractError:
                reason = "deadline_reservation"
                break
            started = time.monotonic()
            row = classified_arm(
                item=item,
                arm="plan",
                protocol={"deadline_utc": protocol["deadline_utc"], "provider": {"accepted_response_models": []}},
                root=root,
                model=None,
                reference=None,
                meter_factory=NoProviderMeter,
                planner=qualification_planner,
                command_timeout_seconds=600,
                replay_timeout_seconds=900,
            )
            row = {**row, "kind": "zero_provider_tool_plan_qualification", "arm_total_wall_seconds": time.monotonic() - started}
            rows.append(row)
            print(json.dumps({k: row.get(k) for k in ("name", "kind", "strict_completed", "status", "error_class", "error_message", "agent_usage")}, ensure_ascii=False), flush=True)
            if not row["cleanup"]["succeeded"] or row["agent_usage"]["model_requests"] or row["agent_usage"]["unknown_usage_requests"]:
                reason = "cleanup_or_zero_provider_contract"
                break
    finally:
        write_json(
            root / "result.json",
            {
                "identity": IDENTITY,
                "kind": "zero_provider_tool_plan_qualification",
                "arms": rows,
                "not_observed": [{"name": p["name"], "reason": reason or "interrupted"} for p in protocol["projects"][len(rows) :]],
                "stop_reason": reason,
                "provider_calls": sum(r["agent_usage"]["model_requests"] for r in rows),
                "research_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip(),
            },
        )
        sealed = seal(root, protocol, REPO_ROOT)
        print(json.dumps(sealed, ensure_ascii=False), flush=True)
    return 0 if len(rows) == len(PROJECTS) and not reason else 1


if __name__ == "__main__":
    raise SystemExit(main())
