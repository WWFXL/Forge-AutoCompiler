#!/usr/bin/env python3
"""精确生成执行与附加观察分别装配；单Workflow真实修复探针。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from langchain_core.messages import SystemMessage
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/packages/harness"), str(ROOT / "scripts")]

from forge_build_native_round import run_strategy as native_run_strategy  # noqa: E402
from forge_build_rtorrent_feedback_repair_probe import PaidNativeMeter as FeedbackMeter  # noqa: E402
from forge_build_rtorrent_canary import PROVIDER  # noqa: E402
from forge_build_rtorrent_canary_v2 import RUNTIME as OLD_RUNTIME  # noqa: E402
from forge_build_rtorrent_common_gate import schedule as three_strategy_schedule  # noqa: E402
from forge_typed_evidence import digest, seal, write_json  # noqa: E402

from deerflow.compile import unified_plan_equivalent_observed as observed_module  # noqa: E402
from deerflow.compile.generated_file_boundary import FileBoundary  # noqa: E402
from deerflow.compile.generation_observation_actions import assemble_generation_actions  # noqa: E402
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek  # noqa: E402
from deerflow.compile.plan_cross_system import SharedResearchBudget, before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402

IDENTITY = "cpp-build-rtorrent-generation-observation-probe-v1"
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
    "planning_exploration_round_limit": 8,
    "planning_bound_scope": "agent.started episode including internal correction",
    "preserve_agent_human_messages": True,
    "preserve_rejected_candidate": True,
    "clarify_main_project_roles": True,
    "separate_exact_generation_and_observation": True,
}


def schedule():
    return [
        slot
        for slot in three_strategy_schedule()
        if slot["method"] == "model_plan_workflow"
    ]


CONTRACT_CLARIFICATION = (
    "\n角色描述相对于本次主项目的宏观阶段：所有依赖子项目的引导、配置、编译和安装都属于dependency准备；"
    "configure和build指主项目的配置和编译。不要把依赖内部的局部阶段误标成主项目阶段。"
    "保持原返回顺序和requires约束，最后一个动作必须step_id=build且role=build；没有步骤自动重排。"
    "任务file_boundary.generations列出的生成动作是精确command与workdir契约，不用移动工作目录等价改写；"
    "系统保留精确生成原命令；files_exist/directories_exist由系统拆成后继显式观察，保留有效检查，不由Agent手工拼接Shell。"
    "其他必要文件检查与固定作者测试保持。reason/source/expected简短注明依据，避免重复整份论证。"
    "状态包rejected_candidate只包含本槽实际被拒的未执行建议及错误，请针对它局部修正并返回完整动作；"
    "它不是正确参考，不覆盖权威状态、源码边界或固定验收，不假定任何被拒动作已执行。"
)


class PaidNativeMeter(FeedbackMeter):
    """保留本槽被拒原tool_call来源，仍走原字节/费用/状态/验收边界。"""

    def wrap_model_call(self, request, handler):
        events = [
            json.loads(line)
            for line in (self.ledger.directory / "events.jsonl")
            .read_text()
            .splitlines()
        ]
        episode = max(
            (i for i, e in enumerate(events) if e["event"] == "agent.started"),
            default=-1,
        )
        rejected = [
            (i, e)
            for i, e in enumerate(events)
            if i > episode and e["event"] == "observed.proposal_rejected"
        ]
        candidate = None
        if rejected:
            index, event = rejected[-1]
            sequence = next(
                e["request_sequence"]
                for e in reversed(events[:index])
                if e["event"] == "model.request_started"
            )
            path = self.ledger.directory / f"response-{sequence}.json"
            calls = [
                call
                for message in json.loads(path.read_text())
                if message["type"] == "ai"
                for call in message.get("tool_calls", [])
                if call["name"] == "ObservedBuildActions"
            ]
            if len(calls) != 1:
                raise PlanContractError("被拒候选必须来自本槽唯一实际结构化tool_call")
            candidate = dict(
                status="not_executed",
                request_sequence=sequence,
                response_file=path.name,
                response_sha256=digest(path),
                tool_call=calls[0],
                error_category=event["category"],
                error_detail=event["detail"],
            )
        self.ledger.save(
            f"rejected-candidate-context-{self._request_sequence + 1}.json", candidate
        )
        original_packet = self.packet
        self.packet = lambda: {**original_packet(), "rejected_candidate": candidate}
        system = request.system_message
        if system is not None and not isinstance(system.content, str):
            raise PlanContractError("规划系统说明必须是文本")
        try:
            return super().wrap_model_call(
                request.override(
                    system_message=SystemMessage(
                        content=(system.content if system else "")
                        + CONTRACT_CLARIFICATION
                    )
                ),
                handler,
            )
        finally:
            self.packet = original_packet


def run_strategy(*, item, **kwargs):
    boundary = FileBoundary.model_validate(item["file_boundary"])

    def assemble(task, proposal, *, revision):
        return assemble_generation_actions(
            task, proposal, revision=revision, boundary=boundary
        )

    # 仅本独立身份使用新装配；原生成权限、执行/验证器和恢复检查保持。
    with patch.object(observed_module, "assemble_observed", assemble):
        return native_run_strategy(item=item, **kwargs)


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
        raise PlanContractError("当前明确授权必须绑定本候选")
    if (
        auth.get("authorization_basis") != "current_user_direct_experiment_instruction"
        or auth.get("automatic_retry") is not False
    ):
        raise PlanContractError("沿用当前直接指令，不复用过期授权或自动重试")
    if Decimal(str(auth["max_new_provider_cost_usd"])) != Decimal("12.00") or Decimal(
        str(auth["stage_max_new_provider_cost_usd"])
    ) != Decimal("3.00"):
        raise PlanContractError("本次共享12美元不重置；新探针预留3美元")
    start, end = (
        datetime.fromisoformat(auth[k]) for k in ("authorized_at_utc", "deadline_utc")
    )
    if (
        start.tzinfo is None
        or end.tzinfo is None
        or start > datetime.now(UTC)
        or (end - start).total_seconds() != 14400
    ):
        raise PlanContractError("保留原四小时时窗，准备计入")
    before_deadline(auth["deadline_utc"], 3900)
    prior = auth["prior_paid_stage"]
    ledger = Path(prior["budget_events_path"])
    events = [json.loads(line) for line in ledger.read_text().splitlines()]
    if (
        digest(ledger) != prior["budget_events_sha256"]
        or [e["event"] for e in events] != ["stage.started", "stage.completed"] * 5
    ):
        raise PlanContractError("前五stage账本未逐字完整闭合")
    if [e["identity"] for e in events[::2]] != [
        "cpp-build-rtorrent-native-canary-v1",
        "cpp-build-rtorrent-native-budget-canary-v1",
        "cpp-build-rtorrent-bounded-planning-canary-v1",
        "cpp-build-rtorrent-feedback-repair-probe-v1",
        "cpp-build-rtorrent-candidate-feedback-probe-v1",
    ]:
        raise PlanContractError("前阶段身份变化")
    total = Decimal(0)
    for begun, closed in zip(events[::2], events[1::2]):
        root = Path(begun["evidence_root"])
        result = json.loads((root / "result.json").read_text())
        marker = json.loads((root / "seal.json").read_text())
        if (
            closed["identity"] != begun["identity"]
            or not result["lifecycle_complete"]
            or Decimal(result["unknown_usage_reservation_usd"]) != 0
            or marker["inventory_canonical_sha256"] != closed["inventory_sha256"]
            or Decimal(result["known_estimated_cost_usd"])
            != Decimal(closed["charged_cost_usd"])
        ):
            raise PlanContractError("前阶段用量/生命周期/封存不完整")
        total += Decimal(closed["charged_cost_usd"])
    if Path(prior["root"]) != Path(events[-2]["evidence_root"]) or total + Decimal(
        "3.00"
    ) > Decimal("12.00"):
        raise PlanContractError("共享预算必须先计入前五阶段全部费用")


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
        "max_new_provider_cost_usd": "3.00",
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
            reserved_cost_usd="3.00",
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
