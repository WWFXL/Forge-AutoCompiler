#!/usr/bin/env python3
"""rtorrent 三策略开发 canary；先完整免费验证，再绑定独立新授权。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/packages/harness"), str(ROOT / "scripts")]
from forge_build_rtorrent_common_v2 import CommonStrategyMeterV2 as CommonStrategyMeter  # noqa: E402
from forge_build_rtorrent_common_v2 import run_strategy  # noqa: E402
from forge_build_unified_plan import METHODS  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek  # noqa: E402
from deerflow.compile.plan_cross_system import SharedResearchBudget, before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402

IDENTITY = "cpp-build-rtorrent-common-canary-v1"
PROVIDER = dict(model="deepseek-v4-pro", thinking=True, reasoning_effort="low", max_output_tokens=32768, max_retries=0, accepted_response_models=["DeepSeek-V4-Pro-0813", "deepseek-v4-pro"])
RUNTIME = dict(
    parallel_jobs=2,
    node_timeout_seconds=1200,
    command_timeout_seconds=1200,
    evaluator_timeout_seconds=900,
    replay_timeout_seconds=1200,
    cleanup_timeout_seconds=120,
    max_model_requests=12,
    max_recorded_tokens=400000,
    max_recorded_tokens_per_response=100000,
    max_agent_steps=72,
    max_tool_calls=48,
    max_commands=32,
    max_handoffs=2,
    message_limit_bytes=50000,
    tool_schema_limit_bytes=8000,
    new_request_reserve_seconds=3900,
    per_arm_cost_cap_usd="1.50",
    unknown_request_reserve_usd="0.40",
)


def schedule():
    return [dict(project="rtorrent", method=m, repetition=1) for m in METHODS]


def validate(candidate):
    if candidate["identity"] != IDENTITY or candidate["schedule"] != schedule() or candidate["provider"] != PROVIDER or candidate["runtime"] != RUNTIME:
        raise PlanContractError("候选身份/顺序/模型/共同资源变化")
    if candidate["provider_authorization"] is not None or candidate["deadline_utc"] is not None or candidate["proposed_max_new_provider_cost_usd"] != 5 or candidate["proposed_runtime_hours"] != 3:
        raise PlanContractError("候选不得嵌入旧授权或改变待审预算")
    if candidate["holdout"] is not False or candidate["family_group"] != ["rtorrent", "rakshasa-libtorrent"]:
        raise PlanContractError("单一已见development项目族边界变化")
    gate = candidate["common_gate"]
    root = Path(gate["root"])
    sealed = audit(root)
    receipt = Path(gate["independent_audit_path"])
    independent = json.loads(receipt.read_text())
    result = json.loads((root / "result.json").read_text())
    original = json.loads((root / "protocol.json").read_text())
    if sealed["inventory_canonical_sha256"] != gate["inventory_sha256"] or digest(receipt) != gate["independent_audit_sha256"]:
        raise PlanContractError("共同门禁或独立审计变化")
    if independent.get("valid") is not True or independent["strict_completed"] != 3 or independent["inventory"]["inventory_canonical_sha256"] != gate["inventory_sha256"]:
        raise PlanContractError("独立共同资格未通过")
    if result["identity"] != "cpp-build-rtorrent-common-entry-gate-v2" or len(result["rows"]) != 3 or result["unobserved_schedule"] or result["stop_reason"] is not None:
        raise PlanContractError("共同门禁分母未闭合")
    for row in result["rows"]:
        if not row["strict_completed"] or any(row["agent_usage"][k] for k in ("recorded_tokens", "unknown_usage_requests", "estimated_cost_usd_completed_responses")):
            raise PlanContractError("共同门禁出现失败或非零用量")
    if candidate["project"] != original["project"] or any(candidate["components"].get(k) != v for k, v in original["components"].items()):
        raise PlanContractError("比较改变已资格任务/测试/生成权限或共同代码")
    if any(k in candidate for k in ("reference", "recovery_actions")):
        raise PlanContractError("真实候选不得携带人工脚本参考")
    if digest(Path(candidate["project"]["source_archive"])) != candidate["project"]["task"]["source_archive_sha256"]:
        raise PlanContractError("源码归档变化")
    for name, expected in candidate["components"].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or digest(path) != expected:
            raise PlanContractError("候选运行组件变化：" + name)


def validate_authorization(candidate_sha, authorization):
    if authorization.get("experiment_identity") != IDENTITY or authorization.get("candidate_sha256") != candidate_sha or authorization.get("user_authorized") is not True:
        raise PlanContractError("需要用户对本候选的新明确授权")
    maximum = Decimal(str(authorization["max_new_provider_cost_usd"]))
    start, end = (datetime.fromisoformat(authorization[key]) for key in ("authorized_at_utc", "deadline_utc"))
    if not maximum.is_finite() or not Decimal(0) < maximum <= Decimal(5):
        raise PlanContractError("本候选新增模型估费最多5美元")
    if start.tzinfo is None or end.tzinfo is None or start > datetime.now(UTC) or not 3900 <= (end - start).total_seconds() <= 10800:
        raise PlanContractError("候选授权须已开始且最多三小时")
    before_deadline(authorization["deadline_utc"], 3900)


def execute(protocol, root, model, *, executor=run_strategy, results=None):
    rows = [] if results is None else results
    reason = None
    for i, slot in enumerate(protocol["schedule"], 1):
        try:
            before_deadline(protocol["deadline_utc"], 3900)
        except PlanContractError:
            reason = "deadline_reservation"
            break
        charged = sum((Decimal(str(r["agent_usage"]["estimated_cost_usd_completed_responses"])) for r in rows), Decimal(0))
        if charged + Decimal("1.50") > Decimal(str(protocol["max_new_provider_cost_usd"])):
            reason = "stage_cost_reservation"
            break
        folder = root / f"slot-{i}"
        folder.mkdir()
        started = time.monotonic()
        row = executor(method=slot["method"], item=protocol["project"], protocol=protocol, root=folder, model=model, meter_factory=CommonStrategyMeter)
        row = {**row, **slot, "arm_total_wall_seconds": time.monotonic() - started}
        rows.append(row)
        write_json(root / f"progress-{i}.json", row)
        print(json.dumps(dict(slot=i, method=slot["method"], strict=row["strict_completed"], usage=row["agent_usage"]), ensure_ascii=False), flush=True)
        if not row["cleanup"]["succeeded"] or row["agent_usage"]["unknown_usage_requests"]:
            reason = "cleanup_or_unknown_usage"
            break
        event_paths = list(folder.glob("rtorrent-*/agent/events.jsonl"))
        events = [json.loads(line) for path in event_paths for line in path.read_text().splitlines()]
        if any(e.get("event") == "model.identity_mismatch" for e in events):
            reason = "provider_model_identity_mismatch"
            break
        usage = row["agent_usage"]
        # 单响应超限可能在request_completed事件追加之前抛出；原响应先保存，不能只看完成事件。
        raw_response_totals = [sum((m.get("usage_metadata") or {}).get("total_tokens", 0) for m in json.loads(path.read_text()) if m.get("type") == "ai") for path in folder.glob("rtorrent-*/agent/response-*.json")]
        if (
            Decimal(str(usage["estimated_cost_usd_completed_responses"])) > Decimal("1.50")
            or usage.get("recorded_tokens", 0) > 500000
            or any(total > 100000 for total in raw_response_totals)
            or any(e.get("event") == "model.request_completed" and e["recorded_tokens"] > 100000 for e in events)
        ):
            reason = "budget_contract_violation"
            break
        if row.get("error_class") not in (None, "PlanContractError", "ValueError", "AgentWorkflowBudgetExceeded", "ValidationError", "StructuredOutputValidationError"):
            reason = "unexpected_runtime_error"
            break
        # 方法失败是有效观察；不要求各臂成功才继续下一个固定槽。
    return rows, protocol["schedule"][len(rows) :], reason


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--authorization-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    candidate = json.loads(args.candidate.read_text())
    validate(candidate)
    if args.validate_only:
        print(json.dumps(dict(valid=True, authorized=False, provider_calls=0, slots=3)))
        return 0
    if args.authorization_root is None or args.output_root is None:
        raise PlanContractError("付费执行须先绑定新明确授权及新目录")
    shared = SharedResearchBudget(args.authorization_root)
    authorization = shared.authorization
    validate_authorization(digest(args.candidate), authorization)
    protocol = {**candidate, "candidate_sha256": digest(args.candidate), "deadline_utc": authorization["deadline_utc"], "max_new_provider_cost_usd": authorization["max_new_provider_cost_usd"]}
    subprocess.run(["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    write_json(root / "authorization.json", authorization)
    write_json(root / "execution.json", dict(release=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()))
    shared.append(dict(event="stage.started", identity=IDENTITY, reserved_cost_usd=str(protocol["max_new_provider_cost_usd"]), evidence_root=str(root), candidate_sha256=digest(args.candidate)))
    rows, unseen, reason, complete = [], [], "initialization_not_completed", False
    try:
        # 仅在具体身份、共同门禁、预算、时窗和共享账本均通过之后读取凭据。
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise PlanContractError("缺少已授权Provider凭据")
        model = PlanThinkingDeepSeek(model="deepseek-v4-pro", api_key=key, base_url="https://api.deepseek.com", max_tokens=32768, max_retries=0, timeout=240, reasoning_effort="low", extra_body={"thinking": {"type": "enabled"}})
        rows, unseen, reason = execute(protocol, root, model, results=rows)
        complete = True
    finally:
        unseen = protocol["schedule"][len(rows) :]
        known = sum((Decimal(str(r["agent_usage"]["estimated_cost_usd_completed_responses"])) for r in rows), Decimal(0))
        unknown = sum(r["agent_usage"]["unknown_usage_requests"] for r in rows)
        write_json(
            root / "result.json",
            dict(
                identity=IDENTITY,
                kind="real_model_development_canary",
                rows=rows,
                unobserved_schedule=unseen,
                stop_reason=reason,
                lifecycle_complete=complete,
                known_estimated_cost_usd=str(known),
                unknown_usage_reservation_usd=str(Decimal("0.40") * unknown),
            ),
        )
        sealed = seal(root, protocol, ROOT, unknown)
        if complete:
            shared.append(dict(event="stage.completed", identity=IDENTITY, charged_cost_usd=str(known + Decimal("0.40") * unknown), inventory_sha256=sealed["inventory_canonical_sha256"]))
    return 0 if not unseen else 1


if __name__ == "__main__":
    raise SystemExit(main())
