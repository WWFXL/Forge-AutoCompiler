#!/usr/bin/env python3
"""Build a deterministic descriptive report from frozen Forge v8 ledgers."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(
    os.environ.get("FORGE_REPO_ROOT", Path(__file__).resolve().parents[1])
).resolve()
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
SCRIPT_ROOT = Path(__file__).resolve().parent
for import_root in (str(HARNESS_ROOT), str(SCRIPT_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_benchmark_runner as runner  # noqa: E402
import forge_benchmark_v8 as protocol_v8  # noqa: E402

from deerflow.compile.evidence import EvidenceError, ExperimentLedger  # noqa: E402

REPORT_VERSION = "1.0.0"
FAILURE_DOMAIN_ORDER = (
    "model_endpoint",
    "agent_tool",
    "build",
    "submit_replay",
    "completion",
)
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v8.json"
DEFAULT_JSON_REPORT = (
    REPO_ROOT / "benchmarks" / "reports" / "cpp-pilot-v8-descriptive.json"
)
DEFAULT_MARKDOWN_REPORT = (
    REPO_ROOT / "benchmarks" / "reports" / "cpp-pilot-v8-descriptive.md"
)


class ReportError(ValueError):
    """Raised when frozen evidence cannot support the requested report."""


def _parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ReportError(f"Invalid ledger timestamp: {value!r}") from exc


def _round(value: float) -> float:
    return round(value, 3)


def _event_payloads(
    events: list[dict[str, Any]], event_name: str
) -> list[dict[str, Any]]:
    return [event["payload"] for event in events if event["event"] == event_name]


def _require_single_payload(
    events: list[dict[str, Any]], event_name: str
) -> dict[str, Any]:
    payloads = _event_payloads(events, event_name)
    if len(payloads) != 1:
        raise ReportError(
            f"A collection ledger must contain exactly one {event_name} event"
        )
    return payloads[0]


def _slot_key(item: dict[str, Any]) -> tuple[str, str, int]:
    return item["case_id"], item["condition_id"], item["repetition"]


def _ledger_slot(events: list[dict[str, Any]]) -> tuple[str, str, int]:
    started = _require_single_payload(events, "experiment.started")
    policy = started.get("policy")
    if not isinstance(policy, dict):
        raise ReportError("experiment.started must contain a policy object")
    try:
        return policy["case_id"], policy["condition"], policy["repetition"]
    except KeyError as exc:
        raise ReportError(
            f"experiment.started policy is missing {exc.args[0]}"
        ) from exc


def _token_usage(events: list[dict[str, Any]]) -> dict[str, int]:
    total = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for payload in _event_payloads(events, "model.request_completed"):
        usage = payload.get("token_usage") or {}
        for key in total:
            value = usage.get(key)
            if type(value) is int and value >= 0:
                total[key] += value
    return total


def _failure_domains(gates: dict[str, Any]) -> dict[str, list[str]]:
    return {
        domain: [item["classification"] for item in (items or [])]
        for domain, items in gates["failure_domains"].items()
    }


def extract_attempt_metrics(
    events: list[dict[str, Any]],
    *,
    order: int,
    expected_slot: tuple[str, str, int],
    expected_manifest_sha256: str,
    gates: dict[str, Any],
    oracle: dict[str, Any],
) -> dict[str, Any]:
    if not events or events[-1]["event"] != "experiment.completed":
        raise ReportError("A collection ledger must end with experiment.completed")
    if _ledger_slot(events) != expected_slot:
        raise ReportError("Ledger policy does not match its collection-plan slot")

    started = _require_single_payload(events, "experiment.started")
    policy = started["policy"]
    if policy.get("manifest_sha256") != expected_manifest_sha256:
        raise ReportError(
            "Ledger manifest identity does not match the frozen v8 manifest"
        )
    if gates.get("valid") is not True:
        raise ReportError("Offline gate recomputation is not valid")

    recorded_oracle = _require_single_payload(events, "oracle.completed")
    if recorded_oracle != oracle:
        raise ReportError(
            "Recorded oracle payload does not match offline recomputation"
        )

    terminal = events[-1]["payload"]
    if terminal.get("oracle_passed") != oracle.get("passed"):
        raise ReportError("Terminal oracle result does not match offline recomputation")

    model_completed = _event_payloads(events, "model.request_completed")
    model_failed = _event_payloads(events, "model.request_failed")
    failure_classifications = Counter(
        payload.get("classification", "unknown") for payload in model_failed
    )
    actual_models = sorted(
        {
            payload["actual_model"]
            for payload in model_completed
            if isinstance(payload.get("actual_model"), str)
        }
    )
    model_latency = sum(
        payload.get("latency_seconds", 0)
        for payload in [*model_completed, *model_failed]
        if isinstance(payload.get("latency_seconds"), (int, float))
    )

    commands = _event_payloads(events, "command.completed")
    submits = _event_payloads(events, "submit.completed")
    replays = _event_payloads(events, "replay.completed")
    orphan = _require_single_payload(events, "orphan.reconciled")
    network_checks = started.get("preflight_checks") or {}
    duration_seconds = (
        _parse_time(events[-1]["occurred_at"]) - _parse_time(events[0]["occurred_at"])
    ).total_seconds()
    if duration_seconds < 0:
        raise ReportError("Ledger timestamps are not monotonic at the attempt boundary")

    artifact_diff = oracle.get("artifact_identity_diff") or {}
    replay_diff = oracle.get("replay_artifact_diff") or {}
    configured_model = policy.get("model_name")
    case_id, condition_id, repetition = expected_slot
    return {
        "order": order,
        "case_id": case_id,
        "condition_id": condition_id,
        "repetition": repetition,
        "configured_model": configured_model,
        "actual_models": actual_models,
        "actual_model_match": bool(actual_models)
        and all(model == configured_model for model in actual_models),
        "oracle_passed": oracle.get("passed") is True,
        "oracle_classification": oracle.get("classification"),
        "terminal_status": terminal.get("status"),
        "attempt_duration_seconds": _round(duration_seconds),
        "model_requests": {
            "started": len(_event_payloads(events, "model.request_started")),
            "completed": len(model_completed),
            "failed": len(model_failed),
            "failure_classifications": dict(sorted(failure_classifications.items())),
            "latency_seconds": _round(model_latency),
        },
        "token_usage": _token_usage(events),
        "commands": {
            "completed": len(commands),
            "successful": sum(
                payload.get("exit_code") == 0 and payload.get("timed_out") is False
                for payload in commands
            ),
            "timed_out": sum(payload.get("timed_out") is True for payload in commands),
        },
        "submits": {
            "started": len(_event_payloads(events, "submit.started")),
            "completed": len(submits),
            "aborted": len(_event_payloads(events, "submit.aborted")),
        },
        "clean_replays": {
            "started": len(_event_payloads(events, "replay.started")),
            "completed": len(replays),
            "passed": sum(
                payload.get("status") == "passed"
                and payload.get("cleanup_succeeded") is True
                for payload in replays
            ),
            "failed": sum(payload.get("status") != "passed" for payload in replays),
            "reconciled": len(_event_payloads(events, "replay.reconciled")),
        },
        "deliveries_succeeded": sum(
            payload.get("delivered") is True
            for payload in _event_payloads(events, "delivery.completed")
        ),
        "failure_domains": _failure_domains(gates),
        "artifact_identity_diff": {
            "expected_only_count": artifact_diff.get("expected_only_count", 0),
            "observed_only_count": artifact_diff.get("observed_only_count", 0),
            "type_mismatch_count": artifact_diff.get("type_mismatch_count", 0),
        },
        "replay_artifact_diff": {
            "available": replay_diff.get("available", False),
            "mismatch_count": replay_diff.get("mismatch_count", 0),
        },
        "network_preflight": {
            "network_present": network_checks.get("network_present"),
            "endpoint_reachable": network_checks.get("endpoint_reachable"),
            "access_medium_recorded": "network_access_medium" in started,
        },
        "recorded_gate_recomputation_valid": terminal.get("gate_recomputation_valid"),
        "offline_gate_recomputation_valid": gates.get("valid"),
        "session_finalization_succeeded": terminal.get(
            "session_finalization_succeeded"
        ),
        "orphan_cleanup_succeeded": terminal.get("orphan_cleanup_succeeded"),
        "orphan_count": orphan.get("orphan_count"),
    }


def _sum_nested(attempts: list[dict[str, Any]], section: str, key: str) -> int | float:
    return sum(attempt[section][key] for attempt in attempts)


def _condition_summary(
    condition_id: str, attempts: list[dict[str, Any]]
) -> dict[str, Any]:
    durations = [attempt["attempt_duration_seconds"] for attempt in attempts]
    failure_event_counts: Counter[str] = Counter()
    for attempt in attempts:
        for domain, classifications in attempt["failure_domains"].items():
            for classification in classifications:
                failure_event_counts[f"{domain}:{classification}"] += 1
    return {
        "condition_id": condition_id,
        "configured_model": attempts[0]["configured_model"],
        "attempts": len(attempts),
        "oracle_passed": sum(attempt["oracle_passed"] for attempt in attempts),
        "oracle_failed": sum(not attempt["oracle_passed"] for attempt in attempts),
        "model_requests": {
            key: _sum_nested(attempts, "model_requests", key)
            for key in ("started", "completed", "failed")
        },
        "token_usage": {
            key: _sum_nested(attempts, "token_usage", key)
            for key in ("input_tokens", "output_tokens", "total_tokens")
        },
        "commands_completed": _sum_nested(attempts, "commands", "completed"),
        "submits_completed": _sum_nested(attempts, "submits", "completed"),
        "clean_replays": {
            key: _sum_nested(attempts, "clean_replays", key)
            for key in ("completed", "passed", "failed")
        },
        "attempt_duration_seconds": {
            "total": _round(sum(durations)),
            "median": _round(statistics.median(durations)),
            "minimum": _round(min(durations)),
            "maximum": _round(max(durations)),
        },
        "failure_event_counts": dict(sorted(failure_event_counts.items())),
    }


def _scan_ledgers(
    evidence_dir: Path,
    expected_slots: set[tuple[str, str, int]],
    known_cases: set[str],
) -> tuple[dict[tuple[str, str, int], list[Path]], list[Path]]:
    collection: dict[tuple[str, str, int], list[Path]] = {}
    historical_baseline: list[Path] = []
    for path in sorted(evidence_dir.glob("*/*/rep-*/physical_attempt_*.jsonl")):
        relative = path.relative_to(evidence_dir)
        case_id, condition_id, repetition_dir, _name = relative.parts
        if case_id not in known_cases:
            raise ReportError(f"Evidence contains an unknown case: {case_id}")
        try:
            repetition = int(repetition_dir.removeprefix("rep-"))
        except ValueError as exc:
            raise ReportError(
                f"Evidence contains an invalid repetition path: {relative}"
            ) from exc
        key = case_id, condition_id, repetition
        if condition_id == "baseline":
            historical_baseline.append(path)
        elif key in expected_slots:
            collection.setdefault(key, []).append(path)
        else:
            raise ReportError(
                f"Evidence contains a non-collection condition or slot: {relative}"
            )
    return collection, historical_baseline


def build_report(
    manifest: dict[str, Any],
    evidence_dir: Path,
    *,
    ledger_verifier: Callable[
        [Path], list[dict[str, Any]]
    ] = ExperimentLedger.verify_path,
    gate_recomputer: Callable[
        [list[dict[str, Any]]], dict[str, Any]
    ] = runner.recompute_gates,
    oracle_runner: Callable[
        [dict[str, Any], list[dict[str, Any]]], dict[str, Any]
    ] = runner.run_oracle,
) -> dict[str, Any]:
    plan = manifest["collection_plan"]
    expected_slots = [_slot_key(item) for item in plan]
    if len(expected_slots) != len(set(expected_slots)):
        raise ReportError("The v8 collection plan contains duplicate slots")
    expected_slot_set = set(expected_slots)
    collection, baseline_paths = _scan_ledgers(
        evidence_dir, expected_slot_set, {case["id"] for case in manifest["cases"]}
    )

    attempts: list[dict[str, Any]] = []
    manifest_sha256 = protocol_v8.manifest_sha256(manifest)
    for order, slot in enumerate(expected_slots, start=1):
        paths = collection.get(slot, [])
        if not paths:
            raise ReportError(f"Missing collection ledger for slot {slot}")
        if len(paths) != 1:
            raise ReportError(f"Collection slot {slot} has multiple ledgers")
        events = ledger_verifier(paths[0])
        attempts.append(
            extract_attempt_metrics(
                events,
                order=order,
                expected_slot=slot,
                expected_manifest_sha256=manifest_sha256,
                gates=gate_recomputer(events),
                oracle=oracle_runner(manifest, events),
            )
        )

    baseline_terminal = 0
    baseline_cleanup = 0
    for path in baseline_paths:
        events = ledger_verifier(path)
        if events and events[-1]["event"] == "experiment.completed":
            baseline_terminal += 1
            if events[-1]["payload"].get("orphan_cleanup_succeeded") is True:
                baseline_cleanup += 1

    condition_order = [condition["id"] for condition in manifest["conditions"]]
    conditions = [
        _condition_summary(
            condition_id,
            [
                attempt
                for attempt in attempts
                if attempt["condition_id"] == condition_id
            ],
        )
        for condition_id in condition_order
    ]
    return {
        "report_version": REPORT_VERSION,
        "benchmark_id": manifest["benchmark"]["id"],
        "manifest_sha256": manifest_sha256,
        "scope": {
            "languages": manifest["scope"]["languages"],
            "phase": manifest["scope"]["phase"],
            "formal_comparison_enabled": manifest["scope"]["formal_comparison_enabled"],
            "descriptive_only": True,
        },
        "collection": {
            "planned_slots": len(expected_slots),
            "analyzed_slots": len(attempts),
            "ledger_hash_chain_valid": len(attempts),
            "gate_recomputation_valid": len(attempts),
            "recorded_terminal_gate_recomputation_valid": sum(
                attempt["recorded_gate_recomputation_valid"] is True
                for attempt in attempts
            ),
            "actual_model_matches": sum(
                attempt["actual_model_match"] is True for attempt in attempts
            ),
            "terminal_completed": sum(
                attempt["terminal_status"] in {"passed", "failed"}
                for attempt in attempts
            ),
            "oracle_passed": sum(attempt["oracle_passed"] for attempt in attempts),
            "oracle_failed": sum(not attempt["oracle_passed"] for attempt in attempts),
            "session_finalization_succeeded": sum(
                attempt["session_finalization_succeeded"] is True
                for attempt in attempts
            ),
            "orphan_cleanup_succeeded": sum(
                attempt["orphan_cleanup_succeeded"] is True for attempt in attempts
            ),
            "orphan_count": sum(attempt["orphan_count"] or 0 for attempt in attempts),
        },
        "historical_baseline_ledgers": {
            "discovered": len(baseline_paths),
            "hash_chain_valid": len(baseline_paths),
            "terminal_completed": baseline_terminal,
            "orphan_cleanup_succeeded": baseline_cleanup,
            "included_in_v8_outcome_denominator": False,
        },
        "conditions": conditions,
        "attempts": attempts,
        "network_interpretation": {
            "network_present_preflight": sum(
                attempt["network_preflight"]["network_present"] is True
                for attempt in attempts
            ),
            "endpoint_reachable_preflight": sum(
                attempt["network_preflight"]["endpoint_reachable"] is True
                for attempt in attempts
            ),
            "access_medium_recorded": any(
                attempt["network_preflight"]["access_medium_recorded"]
                for attempt in attempts
            ),
            "endpoint_timeout_attempts": sum(
                attempt["model_requests"]["failure_classifications"].get("timeout", 0)
                > 0
                for attempt in attempts
            ),
            "attribution": "indeterminate",
            "potential_layers": [
                "local_access_medium",
                "windows_network_stack",
                "wsl_docker_forwarding",
                "restricted_proxy_relay",
                "internet_route",
                "provider_endpoint",
            ],
        },
        "limitations": [
            "Five purposively selected cases with one repetition per condition cannot estimate a population-level model effect.",
            "formal_comparison_enabled is false; no significance test or model-ranking claim is supported.",
            "Historical ledgers did not record Wi-Fi, mobile-hotspot, wired, or other local access-medium identity.",
            "A provider timeout is an observed endpoint-path failure, not proof of a model-capability failure.",
        ],
    }


def _format_failure_domains(attempt: dict[str, Any]) -> str:
    values = [
        f"{domain}:{classification}"
        for domain in FAILURE_DOMAIN_ORDER
        for classification in attempt["failure_domains"].get(domain, [])
    ]
    return "<br>".join(values) if values else "—"


def render_markdown(report: dict[str, Any]) -> str:
    collection = report["collection"]
    baseline = report["historical_baseline_ledgers"]
    lines = [
        "# Forge C/C++ pilot v8 描述性分析报告",
        "",
        "> 状态：冻结 calibration 的描述性复核；不是正式模型比较。",
        "",
        "## 摘要",
        "",
        f"- v8 collection：{collection['oracle_passed']}/{collection['planned_slots']} oracle passed；"
        f"{collection['ledger_hash_chain_valid']}/{collection['planned_slots']} ledger hash chain、"
        f"{collection['gate_recomputation_valid']}/{collection['planned_slots']} 当前离线 gate、"
        f"{collection['orphan_cleanup_succeeded']}/{collection['planned_slots']} cleanup 有效，"
        f"orphan={collection['orphan_count']}。",
        f"- 冻结终态原始记录中的 `gate_recomputation_valid` 为 "
        f"{collection['recorded_terminal_gate_recomputation_valid']}/{collection['planned_slots']}；"
        "Issue #69 修复后当前只读重算为 10/10。二者差异保留历史来源，不回填 ledger。",
        f"- 实际模型身份与各 condition 配置匹配 "
        f"{collection['actual_model_matches']}/{collection['planned_slots']}。",
        f"- 同目录另有 {baseline['discovered']} 条历史 baseline ledger；"
        f"{baseline['hash_chain_valid']}/{baseline['discovered']} hash chain 有效，不进入 v8 的成功率分母。",
        "- 本报告只描述五个自选 case、每 condition 一次的 calibration；manifest 明确 "
        "`formal_comparison_enabled=false`，不得据此宣称模型总体优劣或统计显著性。",
        "",
        "## Condition 汇总",
        "",
        "| Condition | 模型 | Oracle | 请求 started/completed/failed | Tokens | 命令 | Submit | Clean replay passed/completed | 总墙钟（秒） | 中位墙钟（秒） |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for condition in report["conditions"]:
        requests = condition["model_requests"]
        replays = condition["clean_replays"]
        durations = condition["attempt_duration_seconds"]
        lines.append(
            f"| `{condition['condition_id']}` | `{condition['configured_model']}` | "
            f"{condition['oracle_passed']}/{condition['attempts']} | "
            f"{requests['started']}/{requests['completed']}/{requests['failed']} | "
            f"{condition['token_usage']['total_tokens']:,} | {condition['commands_completed']} | "
            f"{condition['submits_completed']} | {replays['passed']}/{replays['completed']} | "
            f"{durations['total']:.3f} | {durations['median']:.3f} |"
        )

    lines.extend(
        [
            "",
            "## 每个 slot",
            "",
            "| # | Case | Condition | Oracle | 分类 | 请求 | Tokens | 墙钟（秒） | 命令 | Submit | Replay passed/completed | 观测失败事件 |",
            "|---:|---|---|---:|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for attempt in report["attempts"]:
        requests = attempt["model_requests"]
        replays = attempt["clean_replays"]
        lines.append(
            f"| {attempt['order']} | `{attempt['case_id']}` | `{attempt['condition_id']}` | "
            f"{'pass' if attempt['oracle_passed'] else 'fail'} | `{attempt['oracle_classification'] or 'passed'}` | "
            f"{requests['started']}/{requests['completed']}/{requests['failed']} | "
            f"{attempt['token_usage']['total_tokens']:,} | {attempt['attempt_duration_seconds']:.3f} | "
            f"{attempt['commands']['completed']} | {attempt['submits']['completed']} | "
            f"{replays['passed']}/{replays['completed']} | {_format_failure_domains(attempt)} |"
        )

    network = report["network_interpretation"]
    lines.extend(
        [
            "",
            "## 网络与 endpoint 解释边界",
            "",
            f"- 10 个 slot 的 `network_present` 与 `endpoint_reachable` 启动前检查分别通过 "
            f"{network['network_present_preflight']}/10 和 {network['endpoint_reachable_preflight']}/10。",
            f"- 共观察到 {network['endpoint_timeout_attempts']} 个带 timeout 的 physical attempt；"
            "这只能说明当时从 Forge 到兼容 endpoint 的完整请求路径未在冻结时限内闭合。",
            "- 历史 v8 ledger 没有记录本机使用 Wi‑Fi、手机热点、有线网络或其他接入介质，"
            "也不能把 Windows 网络栈、WSL/Docker 转发、受限 relay、互联网路由与 provider endpoint 分离。",
            "- 因此 timeout 的归因是 `indeterminate`：不得把它直接算作模型能力失败，也不得事后根据当前网络环境回填历史证据。",
            "",
            "正式实验应在 attempt 前记录不含 SSID、IP、运营商账户或凭据的分类元数据："
            "`access_medium ∈ {wired,wifi,mobile_hotspot,unknown}`、relay 是否启用、"
            "endpoint canary 延迟与 Docker/WSL 网络拓扑；这些只能进入新协议，不能回写 v8。",
            "",
            "## 描述性观察",
            "",
            "- RichLab condition 在本 calibration 中为 2/5，DeepSeek condition 为 4/5；"
            "该差值同时混合了项目差异、单次随机性、Agent 搜索轨迹、endpoint 路径和预算消耗，不能视为模型总体效应。",
            "- `hiredis / RichLab` 的最终 oracle 失败来自 artifact identity 路径不匹配；"
            "`libcheck / RichLab` 同时出现候选验证失败、build-system mismatch 与 post-build reserve 耗尽；"
            "`sysstat / DeepSeek` 在 submit 前出现 endpoint timeout。",
            "- `sysstat / RichLab` 的中间 SHA-256 mismatch 后续变为 clean replay 可通过，"
            "没有满足冻结的非确定性负向预期；Issue #69 只修复了离线 gate 解释，没有改变该 oracle 结论。",
            "",
            "## 对下一阶段的约束",
            "",
            "1. 保持 v1-v8 manifest、Schema、validator 和 ledger 冻结，不 retry、replacement 或 backfill。",
            "2. 正式比较前预注册约 30 个分层 C/C++ 项目，每 condition 至少 3 次；"
            "primary metric、删失规则、失败层级和统计方法必须先写定。",
            "3. endpoint timeout 作为可靠性/删失结果单列；是否重试必须由新协议预先固定，不能运行后决定。",
            "4. verifier-driven repair、阶段 Skill、验证后 Memory 与控制面 A/B 分开设计，一次只改变一个 treatment。",
            "",
            "## 复算",
            "",
            "```bash",
            "PYTHONPATH=backend/packages/harness python scripts/forge_benchmark_v8_report.py \\",
            "  --evidence-dir /workspace/.compile-sessions/benchmark-evidence",
            "```",
            "",
            "JSON 报告是表格数字的机器可读来源；Markdown 由同一分析器确定性生成。",
            "",
        ]
    )
    return "\n".join(lines)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReportError(f"Manifest is not valid JSON: {exc}") from exc
    return protocol_v8.validate_manifest(document)


def write_reports(
    report: dict[str, Any], json_output: Path, markdown_output: Path
) -> None:
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(
            report, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    markdown_output.write_text(render_markdown(report), encoding="utf-8", newline="\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the frozen Forge v8 descriptive report"
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_REPORT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = build_report(load_manifest(args.manifest), args.evidence_dir)
        write_reports(report, args.json_output, args.markdown_output)
        print(
            json.dumps(
                {
                    "generated": True,
                    "json_output": str(args.json_output),
                    "markdown_output": str(args.markdown_output),
                    "analyzed_slots": report["collection"]["analyzed_slots"],
                    "oracle_passed": report["collection"]["oracle_passed"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (EvidenceError, OSError, ReportError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
