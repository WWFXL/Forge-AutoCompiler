#!/usr/bin/env python3
"""Issue #421 动态预算控制轨迹可辨识性的只读审计。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks" / "manifests" / "cpp-dynamic-budget-identifiability-audit-v1.json"
DEFAULT_JSON_REPORT = REPO_ROOT / "benchmarks" / "reports" / "cpp-dynamic-budget-identifiability-audit-v1.json"
DEFAULT_MARKDOWN_REPORT = REPO_ROOT / "benchmarks" / "reports" / "cpp-dynamic-budget-identifiability-audit-v1.md"

REPORT_SCHEMA = "forge-dynamic-budget-identifiability-audit-report-1.0.0"
BUDGET_FIELDS = (
    "wall_clock",
    "model_requests",
    "input_tokens",
    "output_tokens",
    "provider_cost",
    "build_executions",
)


class AuditError(RuntimeError):
    """审计输入或只读不变量不满足。"""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError(f"无法读取 {label}: {path}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"{label} 顶层必须是对象: {path}")
    return value


def load_ledger(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise AuditError(f"无法读取 ledger: {path}") from exc
    events: list[dict[str, Any]] = []
    previous: str | None = None
    for index, line in enumerate(lines, start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AuditError(f"ledger 第 {index} 行不是 JSON: {path}") from exc
        if not isinstance(event, dict):
            raise AuditError(f"ledger 第 {index} 行顶层不是对象: {path}")
        if event.get("sequence") != index:
            raise AuditError(f"ledger sequence 不连续: {path}")
        if event.get("previous_event_sha256") != previous:
            raise AuditError(f"ledger previous hash 不闭合: {path}")
        stored = event.get("event_sha256")
        hashed = dict(event)
        hashed.pop("event_sha256", None)
        if stored != canonical_sha256(hashed):
            raise AuditError(f"ledger event hash 不匹配: {path}#{index}")
        previous = stored
        events.append(event)
    return events


def _source_path(repo_root: Path, source: dict[str, Any]) -> Path:
    path = repo_root / str(source["path"])
    if file_sha256(path) != source["file_sha256"]:
        raise AuditError(f"绑定输入 SHA-256 不匹配: {path}")
    return path


def _usage_complete(result: dict[str, Any], key: str) -> bool:
    usage = result.get(key)
    if not isinstance(usage, dict):
        return False
    required = {"model_requests", "input_tokens", "output_tokens", "cost_usd"}
    if key == "agent_usage":
        required = {"model_requests", "input_tokens", "output_tokens", "estimated_cost_usd"}
    if not required.issubset(usage):
        return False
    requests = usage.get("model_requests")
    if not isinstance(requests, int) or requests < 0:
        return False
    for field in required - {"model_requests"}:
        value = usage.get(field)
        if requests == 0 and value is None:
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            return False
    return True


def audit_progress_report(report: dict[str, Any]) -> dict[str, Any]:
    observed = report.get("observed_input", {})
    development = observed.get("development", {})
    evaluation = observed.get("evaluation", {})
    return {
        "observed_action_decision_points": int(development.get("row_count", 0)) + int(evaluation.get("row_count", 0)),
        "sessions": int(development.get("sessions", 0)) + int(evaluation.get("sessions", 0)),
        "project_families": int(development.get("project_family_count", 0)) + int(evaluation.get("project_family_count", 0)),
        "alternative_action_outcomes": 0,
        "interpretation": ("轨迹包含连续 observed-action 状态，但报告按设计不读取未选择动作，不能提供动作反事实。"),
    }


def audit_checkpoints(
    repo_root: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    sources = manifest["sources"]
    root = repo_root
    for part in Path(sources["checkpoint_glob"]).parts:
        if "*" in part:
            break
        root /= part
    expected_hashes = sources["checkpoint_sha256"]
    observed: list[dict[str, Any]] = []
    for relative, expected_hash in sorted(expected_hashes.items()):
        path = root / relative
        if file_sha256(path) != expected_hash:
            raise AuditError(f"checkpoint SHA-256 不匹配: {path}")
        checkpoint = load_json(path, "checkpoint")
        capture_identity = checkpoint.get("capture", {}).get("identity", {})
        remaining = checkpoint.get("authoritative_rejection", {}).get("response", {}).get("remaining_budget", {})
        observed.append(
            {
                "checkpoint_id": checkpoint.get("checkpoint_id"),
                "environment_hash_bound": {
                    "workspace_sha256",
                    "artifacts_sha256",
                    "repro_sha256",
                    "image_id",
                }.issubset(capture_identity),
                "remaining_budget_bound": {
                    "agent_steps",
                    "commands",
                    "model_requests",
                    "node_seconds",
                    "tool_calls",
                }.issubset(remaining),
            }
        )
    return {
        "checkpoint_count": len(observed),
        "all_environment_hash_bound": all(row["environment_hash_bound"] for row in observed),
        "all_remaining_budget_bound": all(row["remaining_budget_bound"] for row in observed),
        "checkpoints": observed,
        "relevant_action_labels": [],
        "interpretation": ("历史资产证明 Forge 能冻结环境与剩余安全预算；这些 checkpoint 的干预是反馈暴露，不是 direct/escalate/stop，不能充当本问题的动作标签。"),
    }


def audit_formal_comparison(
    repo_root: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    expected = manifest["expected"]
    evidence_root = repo_root / manifest["sources"]["jev_formal_evidence_root"]
    arm_dirs = sorted(path for path in (evidence_root / "arms").iterdir() if path.is_dir())
    if len(arm_dirs) != expected["arm_count"]:
        raise AuditError("Jev v6 arm 数量与审计 manifest 不一致")

    rows: list[dict[str, Any]] = []
    event_counts: Counter[str] = Counter()
    ledger_result_matches = 0
    complete_cost_rows = 0
    build_execution_total = 0
    command_seconds_total = 0.0
    checkpoint_bound_states: set[str] = set()
    explicit_budget_snapshots = 0
    incomplete_terminal_cost_rows: list[dict[str, Any]] = []

    for arm_dir in arm_dirs:
        result_path = arm_dir / "result.json"
        ledger_path = arm_dir / "experiment.jsonl"
        result = load_json(result_path, "arm result")
        events = load_ledger(ledger_path)
        event_counts.update(str(event.get("event")) for event in events)
        completed = [event for event in events if event.get("event") == "experiment.completed"]
        if len(completed) != 1:
            raise AuditError(f"arm 缺少唯一 experiment.completed: {arm_dir}")
        payload = completed[0].get("payload", {})
        result_hash = file_sha256(result_path)
        if payload.get("result_sha256") == result_hash:
            ledger_result_matches += 1
        else:
            raise AuditError(f"ledger/result SHA-256 不匹配: {arm_dir}")

        command_events = [event for event in events if event.get("event") == "command.completed" and isinstance(event.get("payload"), dict)]
        build_executions = sum(event["payload"].get("role") == "build" for event in command_events)
        command_seconds = sum(float(event["payload"].get("duration_seconds", 0.0)) for event in command_events)
        build_execution_total += build_executions
        command_seconds_total += command_seconds

        route = result.get("route")
        if not isinstance(route, dict) or not route.get("state_id"):
            raise AuditError(f"arm 缺少 route state: {arm_dir}")
        state_id = str(route["state_id"])
        if list(arm_dir.rglob("checkpoint.json")):
            checkpoint_bound_states.add(state_id)

        budget_keys = {key for event in events for key in event.get("payload", {}) if key in {"budget", "remaining_budget", "budget_used", "budget_delta"}}
        if {"budget", "remaining_budget", "budget_delta"}.issubset(budget_keys):
            explicit_budget_snapshots += 1

        complete = (
            isinstance(result.get("strict_reproducible_build_success"), bool)
            and isinstance(result.get("duration_ms"), int)
            and result["duration_ms"] >= 0
            and isinstance(result.get("command_count"), int)
            and result["command_count"] >= 0
            and _usage_complete(result, "agent_usage")
            and _usage_complete(result, "jev_usage")
            and build_executions >= 0
        )
        complete_cost_rows += int(complete)
        if not complete:
            incomplete_terminal_cost_rows.append(
                {
                    "task_id": result.get("task_id"),
                    "repetition": result.get("repetition"),
                    "policy": result.get("arm"),
                    "terminal_classification": result.get("terminal_classification"),
                    "jev_error_class": result.get("jev_usage", {}).get("error_class"),
                    "jev_model_requests": result.get("jev_usage", {}).get("model_requests"),
                    "missing_usage_fields": [field for field in ("input_tokens", "output_tokens", "cost_usd") if result.get("jev_usage", {}).get(field) is None],
                }
            )

        if result.get("route_action") == "escalate_agent":
            pure_action = "escalate"
        elif result.get("direct_attempted") and not result.get("escalated_agent"):
            pure_action = "direct"
        else:
            pure_action = "composite_direct_then_escalate"

        rows.append(
            {
                "task_id": result.get("task_id"),
                "repetition": result.get("repetition"),
                "policy": result.get("arm"),
                "build_system": result.get("build_system"),
                "fault_type": result.get("fault_type"),
                "state_id": state_id,
                "route_action": result.get("route_action"),
                "pure_action": pure_action,
                "strict_success": result.get("strict_reproducible_build_success"),
                "direct_attempted": result.get("direct_attempted"),
                "direct_action_succeeded": result.get("direct_action_succeeded"),
                "escalated_agent": result.get("escalated_agent"),
                "duration_ms": result.get("duration_ms"),
                "build_executions": build_executions,
            }
        )

    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_task[str(row["task_id"])].append(row)

    policy_coverage_passed = True
    state_action_counts: dict[str, dict[str, int]] = {}
    state_ids: set[str] = set()
    for task_id, task_rows in sorted(by_task.items()):
        task_states = {row["state_id"] for row in task_rows}
        state_ids.update(task_states)
        if len(task_states) != 1:
            policy_coverage_passed = False
        for policy in expected["policies"]:
            repetitions = {row["repetition"] for row in task_rows if row["policy"] == policy}
            if repetitions != set(range(1, expected["repetitions_per_policy"] + 1)):
                policy_coverage_passed = False
        counts = Counter(row["pure_action"] for row in task_rows)
        counts["stop"] = 0
        state_action_counts[task_id] = {
            "direct": counts["direct"],
            "escalate": counts["escalate"],
            "stop": counts["stop"],
            "composite_direct_then_escalate": counts["composite_direct_then_escalate"],
        }

    action_support_passed = all(counts[action] >= expected["minimum_continuations_per_state_action"] for counts in state_action_counts.values() for action in expected["required_actions"])
    action_support_summary = {
        "states": len(state_action_counts),
        "states_meeting_all_actions": sum(all(counts[action] >= expected["minimum_continuations_per_state_action"] for action in expected["required_actions"]) for counts in state_action_counts.values()),
        "states_without_pure_direct": sorted(task_id for task_id, counts in state_action_counts.items() if counts["direct"] < expected["minimum_continuations_per_state_action"]),
        "stop_continuations": sum(counts["stop"] for counts in state_action_counts.values()),
        "composite_direct_then_escalate_arms": sum(counts["composite_direct_then_escalate"] for counts in state_action_counts.values()),
    }
    route_action_counts = Counter(str(row["route_action"]) for row in rows)
    pure_action_counts = Counter(str(row["pure_action"]) for row in rows)
    strict_counts = Counter(bool(row["strict_success"]) for row in rows)
    build_system_counts = Counter(str(row["build_system"]) for row in rows)

    return {
        "arm_count": len(rows),
        "state_count": len(state_ids),
        "task_count": len(by_task),
        "ledger_result_matches": ledger_result_matches,
        "event_counts": dict(sorted(event_counts.items())),
        "build_system_counts": dict(sorted(build_system_counts.items())),
        "route_action_counts": dict(sorted(route_action_counts.items())),
        "pure_action_counts": dict(sorted(pure_action_counts.items())),
        "strict_successes": strict_counts[True],
        "strict_failures": strict_counts[False],
        "complete_terminal_cost_rows": complete_cost_rows,
        "incomplete_terminal_cost_rows": incomplete_terminal_cost_rows,
        "build_execution_total": build_execution_total,
        "command_seconds_total": round(command_seconds_total, 6),
        "policy_coverage_passed": policy_coverage_passed,
        "state_action_counts": state_action_counts,
        "action_support_summary": action_support_summary,
        "action_support_passed": action_support_passed,
        "control_decisions_per_trajectory": {"minimum": 1, "maximum": 1},
        "checkpoint_bound_state_count": len(checkpoint_bound_states),
        "explicit_decision_budget_snapshot_count": explicit_budget_snapshots,
        "split_roles": ["evaluation"],
        "outcomes_already_exposed": True,
    }


def make_gate(name: str, observed: Any, threshold: Any, passed: bool) -> dict[str, Any]:
    return {
        "name": name,
        "observed": observed,
        "threshold": threshold,
        "passed": passed,
    }


def build_report(repo_root: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = load_json(manifest_path, "audit manifest")
    sources = manifest["sources"]
    progress_path = _source_path(repo_root, sources["progress_state_report"])
    formal_manifest_path = _source_path(repo_root, sources["jev_formal_manifest"])
    formal_report_path = _source_path(repo_root, sources["jev_formal_report"])
    progress = audit_progress_report(load_json(progress_path, "progress report"))
    formal_manifest = load_json(formal_manifest_path, "Jev formal manifest")
    formal_report = load_json(formal_report_path, "Jev formal report")
    v6 = audit_formal_comparison(repo_root, manifest)
    checkpoints = audit_checkpoints(repo_root, manifest)
    expected = manifest["expected"]

    input_integrity = (
        v6["arm_count"] == expected["arm_count"]
        and v6["ledger_result_matches"] == expected["arm_count"]
        and formal_report.get("arm_count") == expected["arm_count"]
        and formal_report.get("manifest_sha256") == canonical_sha256(formal_manifest)
        and checkpoints["checkpoint_count"] == expected["checkpoint_count"]
    )
    build_system_coverage = set(v6["build_system_counts"]) == set(expected["build_systems"])
    matched_policy = v6["state_count"] == expected["state_count"] and v6["policy_coverage_passed"] and build_system_coverage
    terminal_cost = v6["complete_terminal_cost_rows"] == expected["arm_count"]
    sequential = v6["control_decisions_per_trajectory"]["minimum"] >= expected["minimum_control_decisions_per_trajectory"]
    checkpoint_coverage = v6["checkpoint_bound_state_count"] == expected["state_count"]
    budget_snapshots = v6["explicit_decision_budget_snapshot_count"] == expected["arm_count"]
    isolation = (
        set(v6["split_roles"])
        == {
            "design",
            "calibration",
            "evaluation",
        }
        and not v6["outcomes_already_exposed"]
    )

    gates = [
        make_gate(
            "input_integrity",
            {
                "arms": v6["arm_count"],
                "ledger_result_matches": v6["ledger_result_matches"],
                "checkpoint_files": checkpoints["checkpoint_count"],
            },
            {
                "arms": expected["arm_count"],
                "ledger_result_matches": expected["arm_count"],
                "checkpoint_files": expected["checkpoint_count"],
            },
            input_integrity,
        ),
        make_gate(
            "matched_policy_coverage",
            {
                "states": v6["state_count"],
                "build_systems": sorted(v6["build_system_counts"]),
                "three_policies_two_repetitions": v6["policy_coverage_passed"],
            },
            {
                "states": expected["state_count"],
                "build_systems": expected["build_systems"],
                "repetitions_per_policy": expected["repetitions_per_policy"],
            },
            matched_policy,
        ),
        make_gate(
            "strict_terminal_and_total_cost",
            v6["complete_terminal_cost_rows"],
            expected["arm_count"],
            terminal_cost,
        ),
        make_gate(
            "action_continuation_support",
            {
                "required_actions": expected["required_actions"],
                **v6["action_support_summary"],
            },
            {"minimum_per_state_action": expected["minimum_continuations_per_state_action"]},
            v6["action_support_passed"],
        ),
        make_gate(
            "sequential_control_decisions",
            v6["control_decisions_per_trajectory"],
            {
                "minimum": expected["minimum_control_decisions_per_trajectory"],
                "action_post_state_required": True,
            },
            sequential,
        ),
        make_gate(
            "resumable_checkpoint_coverage",
            v6["checkpoint_bound_state_count"],
            expected["state_count"],
            checkpoint_coverage,
        ),
        make_gate(
            "per_decision_budget_state",
            {
                "complete_snapshots": v6["explicit_decision_budget_snapshot_count"],
                "required_fields": list(BUDGET_FIELDS),
            },
            expected["arm_count"],
            budget_snapshots,
        ),
        make_gate(
            "unexposed_project_family_splits",
            {
                "split_roles": v6["split_roles"],
                "outcomes_already_exposed": v6["outcomes_already_exposed"],
            },
            {
                "split_roles": ["design", "calibration", "evaluation"],
                "outcomes_already_exposed": False,
            },
            isolation,
        ),
    ]
    passed = all(gate["passed"] for gate in gates)
    decision = manifest["decision_rule"]["pass" if passed else "fail"]

    return {
        "schema_version": REPORT_SCHEMA,
        "identity": manifest["identity"],
        "issue_url": manifest["issue_url"],
        "analysis_date": manifest["analysis_date"],
        "work_type": manifest["work_type"],
        "authorization_observed": manifest["authorization"],
        "manifest_file_sha256": file_sha256(manifest_path),
        "manifest_canonical_sha256": canonical_sha256(manifest),
        "source_audits": {
            "progress_state_v1": progress,
            "jev_formal_comparison_v6": v6,
            "historical_checkpoint_capability": checkpoints,
        },
        "gates": gates,
        "passed": passed,
        "decision": decision,
        "interpretation": ("现有证据足以比较单个受控故障状态上的策略终点和大部分总成本，但缺少 stop 的共享预算机会成本、序列动作后状态、逐决策剩余预算、评测状态 checkpoint 和未暴露项目族，因此不能识别动态预算控制器。"),
        "minimum_next_collection": {
            "phase": "dynamic_budget_trajectory_benchmark_qualification_v1",
            "provider_calls": 0,
            "project_families": 9,
            "project_families_per_build_system": 3,
            "minimum_states_per_project": 3,
            "clean_checkpoint_replays_per_state": 2,
            "required_properties": [
                "每个状态绑定 source/image/workspace/artifacts/message/budget 哈希",
                "direct 后始终重新观察并生成下一状态，禁止自动拼接 Agent",
                "预算账本记录动作前、动作增量和动作后六维向量",
                "项目 block 共享预算，使 stop 的资源可转移",
                "结果盲冻结 design/calibration/evaluation 项目族与时间边界",
                "先用确定性 continuation 资格化，再单独授权 Agent 重复 continuation",
            ],
            "go_condition": ("9/9 项目、27/27 状态均完成两次 checkpoint clean replay，预算向量守恒且三种构建系统无缺口。"),
            "stop_condition": ("任一构建系统无法形成至少三个多步状态，或 checkpoint/预算重放一致率低于 95%，则停止动态 controller 路线。"),
        },
        "claim_boundary": {
            "supported": [
                "现有 v6 受控故障数据的 matched policy、严格终点与 71/72 总成本覆盖边界",
                "历史 checkpoint 资产能够冻结环境和剩余安全预算",
                "是否达到实现动态预算 controller 前的数据可辨识性门槛",
            ],
            "unsupported": [
                "动态预算 controller 的成功率、成本或时间效果",
                "任何未观察动作的反事实收益",
                "自然失败、开放世界或跨时间泛化",
                "Jev、Agent 或其他模型的通用排名",
            ],
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    v6 = report["source_audits"]["jev_formal_comparison_v6"]
    checkpoints = report["source_audits"]["historical_checkpoint_capability"]
    gate_rows = []
    for gate in report["gates"]:
        gate_rows.append(f"| `{gate['name']}` | `{json.dumps(gate['observed'], ensure_ascii=False, sort_keys=True)}` | {'是' if gate['passed'] else '否'} |")
    action_rows = []
    for task_id, counts in sorted(v6["state_action_counts"].items()):
        action_rows.append(f"| `{task_id}` | {counts['direct']} | {counts['escalate']} | {counts['stop']} | {counts['composite_direct_then_escalate']} |")
    next_collection = report["minimum_next_collection"]
    return "\n".join(
        [
            "# 动态预算控制轨迹可辨识性审计结果",
            "",
            f"> 日期：{report['analysis_date']}  ",
            f"> Tracking Issue：[{report['issue_url'].rsplit('/', 1)[-1]}]({report['issue_url']})  ",
            f"> Identity：`{report['identity']}`  ",
            "> 类型：结果分析；0 Provider、0 credential read、0 formal attempt",
            "",
            "## 1. 关键结论",
            "",
            f"**决定：`{report['decision']}`。**",
            "",
            report["interpretation"],
            "",
            "这不是动态预算方向的负效果结论。它只说明当前数据不能支持 controller 的离线训练、选择或效果评价。",
            "",
            "## 2. 已有证据能回答什么",
            "",
            f"- Jev v6：{v6['state_count']} 个同源状态、{v6['arm_count']} 个 arm，严格成功 {v6['strict_successes']}、失败 {v6['strict_failures']}；{v6['ledger_result_matches']}/{v6['arm_count']} ledger/result 哈希闭合。",
            f"- 总成本：{v6['complete_terminal_cost_rows']}/{v6['arm_count']} arm 同时具备严格终点、墙钟、请求、token、费用、命令和 build execution；共观察 {v6['build_execution_total']} 次 build execution。",
            f"- 缺失成本：`{v6['incomplete_terminal_cost_rows'][0]['task_id']}` repetition "
            f"{v6['incomplete_terminal_cost_rows'][0]['repetition']} 的 Jev 请求因 "
            f"`{v6['incomplete_terminal_cost_rows'][0]['jev_error_class']}` 结束，1 次请求的 token 与费用未知，未做估算回填。",
            f"- 旧轨迹：进展状态 v1 有 {report['source_audits']['progress_state_v1']['observed_action_decision_points']} 个连续 observed-action 决策点，但没有未选择动作结果。",
            f"- Checkpoint：现存 {checkpoints['checkpoint_count']} 个历史 checkpoint 均绑定环境哈希和剩余安全预算，但其干预不是本轮三动作。",
            "",
            "## 3. 动作覆盖",
            "",
            "纯动作要求该 arm 没有把直接动作失败与 Agent 自动回退合并。",
            "",
            "| 状态/项目 | pure direct | pure escalate | stop | direct 后自动 escalate |",
            "| --- | ---: | ---: | ---: | ---: |",
            *action_rows,
            "",
            "`stop` 的任务内终点虽可确定为失败，但当前实验没有共享 batch 预算，因此无法观察把节省资源转移给其他任务后的机会收益。",
            "",
            "## 4. 资格门槛",
            "",
            "| 门槛 | 观测 | 通过 |",
            "| --- | --- | --- |",
            *gate_rows,
            "",
            "通过的两项说明旧证据具备完整账本和 matched 三策略结构。失败的六项包含完整成本、动作支持、序列状态、checkpoint、逐决策预算和隔离语料，不能用更多后验特征或阈值补齐。",
            "",
            "## 5. 为什么现在不能实现 controller",
            "",
            "1. 一个 Jev 失败请求缺少 token 与费用，完整成本向量只有 71/72。",
            "2. 每个 v6 arm 只有一个控制决策；Agent 内部命令不是控制器可替换的独立决策点。",
            "3. 16 个直接动作失败 arm 自动拼接 Agent，终点标签混合了两个动作，不能当作 pure direct 结果。",
            "4. 72 个路由状态没有可恢复 checkpoint，也没有动作前/后六维剩余预算快照。",
            "5. v6 的 12 个项目全部是结果已公开的 evaluation 数据，没有预算机制自己的 design/calibration holdout。",
            "6. 每任务预算相互独立，停止一个任务不能把资源转移给另一个任务，因此无法评价预算分配。",
            "",
            "## 6. 下一阶段最小采集",
            "",
            f"下一 identity 候选为 `{next_collection['phase']}`，先做 0 Provider 轨迹 benchmark 资格："
            f"CMake、Make、Autotools 各 {next_collection['project_families_per_build_system']} 个新项目族，"
            f"每项至少 {next_collection['minimum_states_per_project']} 个多步状态，每状态 "
            f"{next_collection['clean_checkpoint_replays_per_state']} 次 clean checkpoint replay。",
            "",
            "资格通过前仍不实现 controller，也不调用 Jev/Agent。通过后再单独冻结 Agent continuation 的请求、token、费用、重复次数和停止规则。",
            "",
            "## 7. 解释边界",
            "",
            "能够支持：",
            "",
            *[f"- {item}；" for item in report["claim_boundary"]["supported"]],
            "",
            "不能支持：",
            "",
            *[f"- {item}；" for item in report["claim_boundary"]["unsupported"]],
            "",
            "所有历史 identity 和 evidence 在本审计中保持只读。",
            "",
        ]
    )


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--markdown-report", type=Path, default=DEFAULT_MARKDOWN_REPORT)
    parser.add_argument("--check-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        report = build_report(REPO_ROOT, args.manifest.resolve())
        if not args.check_only:
            write_json(args.json_report, report)
            args.markdown_report.parent.mkdir(parents=True, exist_ok=True)
            args.markdown_report.write_text(render_markdown(report), encoding="utf-8")
    except (AuditError, KeyError, TypeError, ValueError) as exc:
        print(f"审计失败: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "decision": report["decision"],
                "passed": report["passed"],
                "gates_passed": sum(gate["passed"] for gate in report["gates"]),
                "gates_total": len(report["gates"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
