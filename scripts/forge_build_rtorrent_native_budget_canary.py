#!/usr/bin/env python3
"""三策略共同资源预算敏感性；不改已资格任务、模型或验收。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/packages/harness"), str(ROOT / "scripts")]

from forge_build_native_round import NativeRoundMeter, run_strategy  # noqa: E402
from forge_build_rtorrent_canary import PROVIDER  # noqa: E402
from forge_build_rtorrent_canary_v2 import RUNTIME as OLD_RUNTIME  # noqa: E402
from forge_build_rtorrent_common_gate import schedule  # noqa: E402
from forge_typed_evidence import digest, seal, write_json  # noqa: E402

from deerflow.compile.agent_workflow_runtime import AgentWorkflowExecutionMiddleware  # noqa: E402
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek  # noqa: E402
from deerflow.compile.plan_cross_system import SharedResearchBudget, before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402

IDENTITY = "cpp-build-rtorrent-native-budget-canary-v1"
UNKNOWN_RESERVE = Decimal("0.80")
RUNTIME = {
    **OLD_RUNTIME,
    "max_model_requests": 145,
    "max_recorded_tokens": 1000000,
    "max_agent_steps": 144,
    "max_tool_calls": 96,
    "max_commands": 64,
    "planner_graph_recursion_limit": 100,
    "tool_graph_recursion_limit": 150,
    "workflow_command_limit": 32,
    "workflow_wall_clock_seconds": 1200,
    "per_arm_cost_cap_usd": "3.00",
    "message_limit_bytes": 100000,
    "max_recorded_tokens_per_response": 200000,
    "unknown_request_reserve_usd": str(UNKNOWN_RESERVE),
}


class PaidNativeMeter(NativeRoundMeter):
    """只扩大共同资源包；原生材料、用量捕获与执行验收复用。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tracker.limits = replace(
            self.tracker.limits,
            max_model_requests=145,
            max_recorded_tokens=1000000,
            max_agent_steps=144,
            max_tool_calls=96,
            max_commands=64,
        )

    def _before_request(self):
        before_deadline(self.deadline, 3900)
        if self.unknown_usage_requests or Decimal(
            str(self.cost_usd)
        ) + UNKNOWN_RESERVE > Decimal("3.00"):
            raise PlanContractError("资源敏感性单臂费用不足或存在未知请求")
        # 只替换历史多层固定费用准入；原始tracker、请求序号及计量事件保持。
        return AgentWorkflowExecutionMiddleware._before_request(self)


def charges(rows):
    known = sum(
        (
            Decimal(str(r["agent_usage"]["estimated_cost_usd_completed_responses"]))
            for r in rows
        ),
        Decimal(0),
    )
    unknown = sum(r["agent_usage"]["unknown_usage_requests"] for r in rows)
    return known, UNKNOWN_RESERVE * unknown


def validate(candidate):
    if (
        candidate["identity"] != IDENTITY
        or candidate["schedule"] != schedule()
        or candidate["provider"] != PROVIDER
        or candidate["runtime"] != RUNTIME
    ):
        raise PlanContractError("独立身份、策略、模型或共同资源变化")
    if (
        any(key in candidate for key in ("reference", "recovery_actions"))
        or candidate["holdout"] is not False
    ):
        raise PlanContractError("真实开发实验不接收正确参考或holdout主张")
    gate = candidate["qualified_native_e2e"]
    root, receipt = Path(gate["root"]), Path(gate["independent_audit_path"])
    # 前轮刚完成全量独立审计；此处核对封存标记/审计SHA，避免重复扫描数GB历史构建树。
    inventory = json.loads((root / "seal.json").read_text())
    checked = json.loads(receipt.read_text())
    parent = json.loads((root / "protocol.json").read_text())
    if (
        inventory["inventory_canonical_sha256"] != gate["inventory_sha256"]
        or digest(receipt) != gate["independent_audit_sha256"]
    ):
        raise PlanContractError("已资格来源指针变化")
    if (
        not checked["valid"]
        or checked["strict_completed"] != 3
        or checked["unobserved"]
        or checked["inventory"] != inventory
    ):
        raise PlanContractError("完整原生端到端资格未闭合")
    if candidate["project"] != parent["project"] or any(
        candidate["components"].get(k) != v for k, v in parent["components"].items()
    ):
        raise PlanContractError("已资格任务、测试或组件变化")
    if (
        digest(Path(candidate["project"]["source_archive"]))
        != candidate["project"]["task"]["source_archive_sha256"]
    ):
        raise PlanContractError("源码归档变化")
    for name, expected in candidate["components"].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or digest(path) != expected:
            raise PlanContractError("冻结组件变化：" + name)


def validate_authorization(candidate_sha, auth):
    if (
        auth.get("experiment_identity") != IDENTITY
        or auth.get("candidate_sha256") != candidate_sha
        or auth.get("user_authorized") is not True
    ):
        raise PlanContractError("新明确授权必须绑定本候选")
    if (
        auth.get("authorization_basis") != "current_user_direct_experiment_instruction"
        or auth.get("automatic_retry") is not False
    ):
        raise PlanContractError("不复用历史付费授权，不自动重试")
    if Decimal(str(auth["max_new_provider_cost_usd"])) != Decimal("12.00"):
        raise PlanContractError("本次执行器自设共享上限12美元，新阶段9美元")
    start, end = (
        datetime.fromisoformat(auth[k]) for k in ("authorized_at_utc", "deadline_utc")
    )
    if (
        start.tzinfo is None
        or end.tzinfo is None
        or start > datetime.now(UTC)
        or (end - start).total_seconds() != 14400
    ):
        raise PlanContractError("本次执行器自设四小时，准备计入")
    before_deadline(auth["deadline_utc"], 3900)
    prior = auth["prior_paid_stage"]
    ledger = Path(prior["budget_events_path"])
    events = [json.loads(line) for line in ledger.read_text().splitlines()]
    result = json.loads((Path(prior["root"]) / "result.json").read_text())
    seal_record = json.loads((Path(prior["root"]) / "seal.json").read_text())
    if (
        digest(ledger) != prior["budget_events_sha256"]
        or [e["event"] for e in events] != ["stage.started", "stage.completed"]
        or any(e["identity"] != "cpp-build-rtorrent-native-canary-v1" for e in events)
    ):
        raise PlanContractError("前一阶段账本未完整闭合")
    if (
        not result["lifecycle_complete"]
        or Decimal(result["unknown_usage_reservation_usd"]) != 0
        or seal_record["inventory_canonical_sha256"] != events[1]["inventory_sha256"]
    ):
        raise PlanContractError("前一阶段未知用量或证据未闭合")
    if Decimal(result["known_estimated_cost_usd"]) != Decimal(
        events[1]["charged_cost_usd"]
    ) or Decimal(events[1]["charged_cost_usd"]) + Decimal("9") > Decimal(
        str(auth["max_new_provider_cost_usd"])
    ):
        raise PlanContractError("未完整计入本次已有费用")


def execute(protocol, root, model, *, executor=run_strategy, results=None):
    rows = [] if results is None else results
    reason = None
    for index, slot in enumerate(protocol["schedule"], 1):
        try:
            before_deadline(protocol["deadline_utc"], 3900)
        except PlanContractError:
            reason = "deadline_reservation"
            break
        known, unknown = charges(rows)
        if known + unknown + Decimal("3.00") > Decimal(
            str(protocol["max_new_provider_cost_usd"])
        ):
            reason = "stage_cost_reservation"
            break
        folder = root / f"slot-{index}"
        folder.mkdir()
        started = time.monotonic()
        row = executor(
            method=slot["method"],
            item=protocol["project"],
            protocol=protocol,
            root=folder,
            model=model,
            meter_factory=PaidNativeMeter,
        )
        row = {**row, **slot, "arm_total_wall_seconds": time.monotonic() - started}
        rows.append(row)
        write_json(root / f"progress-{index}.json", row)
        print(
            json.dumps(
                dict(
                    slot=index,
                    method=slot["method"],
                    strict=row["strict_completed"],
                    error=row.get("error_message"),
                    usage=row["agent_usage"],
                ),
                ensure_ascii=False,
            ),
            flush=True,
        )
        usage = row["agent_usage"]
        if not row["cleanup"]["succeeded"] or usage["unknown_usage_requests"]:
            reason = "cleanup_or_unknown_usage"
            break
        events = [
            json.loads(line)
            for path in folder.glob("rtorrent-*/agent/events.jsonl")
            for line in path.read_text().splitlines()
        ]
        totals = [
            sum(
                (m.get("usage_metadata") or {}).get("total_tokens", 0)
                for m in json.loads(p.read_text())
                if m.get("type") == "ai"
            )
            for p in folder.glob("rtorrent-*/agent/response-*.json")
        ]
        if any(e.get("event") == "model.identity_mismatch" for e in events):
            reason = "provider_model_identity_mismatch"
            break
        if (
            Decimal(str(usage["estimated_cost_usd_completed_responses"]))
            > Decimal("3.00")
            or any(n > 200000 for n in totals)
            or usage["recorded_tokens"] > 1200000
        ):
            reason = "budget_contract_violation"
            break
        if row.get("error_class") not in (
            None,
            "PlanContractError",
            "ValueError",
            "AgentWorkflowBudgetExceeded",
            "ValidationError",
            "StructuredOutputValidationError",
            "GraphRecursionError",
        ):
            reason = "unexpected_runtime_error"
            break
    return rows, protocol["schedule"][len(rows) :], reason


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--authorization-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    candidate = json.loads(args.candidate.read_text())
    validate(candidate)
    budget = SharedResearchBudget(args.authorization_root)
    auth = budget.authorization
    validate_authorization(digest(args.candidate), auth)
    if (args.authorization_root / "budget-events.jsonl").read_bytes() != Path(
        auth["prior_paid_stage"]["budget_events_path"]
    ).read_bytes():
        raise PlanContractError("本轮共享账本必须先逐字计入前阶段，不能重复启动")
    if args.output_root.exists():
        raise PlanContractError("新实验目录已存在；不续跑或读取凭据")
    if args.validate_only:
        print(
            json.dumps(
                dict(
                    valid=True,
                    provider_calls=0,
                    unknown_reserve_usd=str(UNKNOWN_RESERVE),
                )
            )
        )
        return 0
    subprocess.run(
        ["bash", str(ROOT / "scripts/require-docker-runtime.sh")],
        check=True,
        timeout=30,
    )
    protocol = {
        **candidate,
        "deadline_utc": auth["deadline_utc"],
        "max_new_provider_cost_usd": "9.00",
        "candidate_sha256": digest(args.candidate),
    }
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    write_json(root / "authorization.json", auth)
    write_json(
        root / "execution.json",
        dict(
            release=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True
            ).strip()
        ),
    )
    budget.append(
        dict(
            event="stage.started",
            identity=IDENTITY,
            reserved_cost_usd="9.00",
            evidence_root=str(root),
            candidate_sha256=digest(args.candidate),
        )
    )
    rows, reason, complete = [], "initialization_not_completed", False
    try:
        # 新授权和身份核验后才读取凭据；只记录是否可用，不打印值。
        from dotenv import load_dotenv

        for path in (ROOT / ".env", ROOT / "backend/.env"):
            if not os.environ.get("DEEPSEEK_API_KEY") and path.is_file():
                load_dotenv(path, override=False)
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise PlanContractError("已授权Provider凭据不可用")
        model = PlanThinkingDeepSeek(
            model=PROVIDER["model"],
            api_key=key,
            base_url="https://api.deepseek.com",
            max_tokens=32768,
            max_retries=0,
            timeout=240,
            reasoning_effort="low",
            extra_body={"thinking": {"type": "enabled"}},
        )
        rows, _, reason = execute(protocol, root, model, results=rows)
        complete = True
    finally:
        known, unknown = charges(rows)
        write_json(
            root / "result.json",
            dict(
                identity=IDENTITY,
                kind="real_model_development_canary",
                rows=rows,
                unobserved_schedule=protocol["schedule"][len(rows) :],
                stop_reason=reason,
                lifecycle_complete=complete,
                known_estimated_cost_usd=str(known),
                unknown_usage_reservation_usd=str(unknown),
            ),
        )
        inventory = seal(
            root,
            protocol,
            ROOT,
            sum(r["agent_usage"]["unknown_usage_requests"] for r in rows),
        )
        if complete:
            budget.append(
                dict(
                    event="stage.completed",
                    identity=IDENTITY,
                    charged_cost_usd=str(known + unknown),
                    inventory_sha256=inventory["inventory_canonical_sha256"],
                )
            )
    return 0 if len(rows) == len(protocol["schedule"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
