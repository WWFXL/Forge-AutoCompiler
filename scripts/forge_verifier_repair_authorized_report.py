#!/usr/bin/env python3
"""从主 ledger 与 repair sidecar 生成确定性配对 pilot 报告。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (SCRIPT_ROOT, HARNESS_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

import forge_verifier_repair_authorized_protocol as protocol  # noqa: E402
import forge_verifier_repair_pilot_analyzer as analyzer  # noqa: E402
import forge_verifier_repair_pilot_protocol as parent_protocol  # noqa: E402
import forge_verifier_repair_runtime as repair_runtime  # noqa: E402

from deerflow.compile.evidence import EvidenceError, ExperimentLedger  # noqa: E402

REPORT_VERSION = "verifier-driven-repair-pilot-authorized-report-1.0.0"
DEFAULT_EVIDENCE_DIR = Path(protocol.EVIDENCE_DIRECTORY)
DEFAULT_JSON_REPORT = DEFAULT_EVIDENCE_DIR / "verifier-repair-pilot-report.json"
DEFAULT_MARKDOWN_REPORT = DEFAULT_EVIDENCE_DIR / "verifier-repair-pilot-report.md"


class ReportError(ValueError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError(f"cannot read JSON document: {path}") from exc
    if not isinstance(value, dict):
        raise ReportError(f"JSON document must be an object: {path}")
    return value


def load_manifest(path: Path = protocol.DEFAULT_MANIFEST) -> dict[str, Any]:
    try:
        return protocol.validate_manifest(_load_json(path))
    except protocol.ProtocolError as exc:
        raise ReportError(str(exc)) from exc


def _event_payload(events: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.get("event") == name and isinstance(event.get("payload"), dict):
            return event["payload"]
    return None


def _slot_for_events(manifest: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not events:
        return None
    policy = events[0].get("payload", {}).get("policy")
    if not isinstance(policy, dict):
        return None
    if policy.get("benchmark_id") != manifest["benchmark"]["id"] or policy.get("manifest_sha256") != protocol.manifest_sha256(manifest):
        return None
    matches = [slot for slot in manifest["collection_plan"] if slot["case_id"] == policy.get("case_id") and slot["condition_id"] == policy.get("condition") and slot["repetition"] == policy.get("repetition")]
    if len(matches) != 1:
        raise ReportError("physical ledger does not map to one authorized slot")
    return matches[0]


def _sidecar_path(ledger_path: Path) -> Path:
    return ledger_path.with_name(ledger_path.stem + ".repair-sidecar.json")


def _read_completed_sidecar(path: Path, *, manifest: dict[str, Any], slot: dict[str, Any], events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        records = repair_runtime.RepairEvidenceLedger(path).read()
    except repair_runtime.RepairRuntimeError as exc:
        raise ReportError(f"invalid repair sidecar: {path}") from exc
    if not records or records[-1].get("event") != "repair.context_completed":
        raise ReportError("repair sidecar is not terminal")
    context = records[0]["payload"]
    expected = {
        "manifest_sha256": protocol.manifest_sha256(manifest),
        "thread_id": events[0]["payload"]["thread_id"],
        "physical_attempt_id": events[0]["physical_attempt_id"],
        "order": slot["order"],
        "pair_id": slot["pair_id"],
        "case_id": slot["case_id"],
        "provider_condition": slot["provider_condition"],
        "treatment": slot["treatment"],
        "repetition": slot["repetition"],
    }
    if context != expected:
        raise ReportError("repair sidecar identity drifted from the physical ledger")
    fidelity = repair_runtime.evaluate_treatment_fidelity(records)
    return records, fidelity


def _recorded_tokens(events: list[dict[str, Any]]) -> int:
    total = 0
    for event in events:
        if event.get("event") != "model.request_completed":
            continue
        usage = event.get("payload", {}).get("token_usage")
        value = usage.get("total_tokens") if isinstance(usage, dict) else None
        if type(value) is int and value >= 0:
            total += value
    return total


def _wall_clock_seconds(events: list[dict[str, Any]]) -> float:
    try:
        started = datetime.fromisoformat(events[0]["occurred_at"])
        completed = datetime.fromisoformat(events[-1]["occurred_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ReportError("physical ledger timestamps are invalid") from exc
    return round(max(0.0, (completed - started).total_seconds()), 6)


def _feedback_labels(records: list[dict[str, Any]]) -> list[str]:
    labels: list[str] = []
    for record in records:
        if record.get("event") != "repair.feedback_observed":
            continue
        payload = record["payload"]
        label = payload["primary_classification"] if payload["actionable"] else payload["status"]
        if isinstance(label, str):
            labels.append(label)
    return labels


def _failure_transitions(labels: list[str]) -> list[dict[str, str]]:
    return [{"from": previous, "to": current} for previous, current in zip(labels, labels[1:], strict=False) if previous != current]


def _repair_conversions(transitions: list[dict[str, str]]) -> int:
    return sum(transition["from"] in repair_runtime.REPAIR_GOALS and transition["to"] == "passed" for transition in transitions)


def summarize_attempt(
    manifest: dict[str, Any],
    slot: dict[str, Any],
    events: list[dict[str, Any]],
    sidecar_records: list[dict[str, Any]],
    fidelity: dict[str, Any],
) -> dict[str, Any]:
    completed = _event_payload(events, "experiment.completed")
    oracle = _event_payload(events, "oracle.completed")
    if completed is None or oracle is None or events[-1]["event"] != "experiment.completed":
        raise ReportError("attempt summary requires a terminal physical ledger")
    labels = _feedback_labels(sidecar_records)
    transitions = _failure_transitions(labels)
    return {
        "order": slot["order"],
        "pair_id": slot["pair_id"],
        "case_id": slot["case_id"],
        "provider_condition": slot["provider_condition"],
        "treatment": slot["treatment"],
        "repetition": slot["repetition"],
        "oracle_passed": oracle.get("passed") is True,
        "terminal_passed": completed.get("status") == "passed",
        "fidelity_status": fidelity["status"],
        "recorded_tokens": _recorded_tokens(events),
        "model_requests": sum(event.get("event") == "model.request_started" for event in events),
        "wall_clock_seconds": _wall_clock_seconds(events),
        "actionable_verifier_failures": sum(record.get("event") == "repair.feedback_observed" and record["payload"]["actionable"] is True for record in sidecar_records),
        "repair_conversions": _repair_conversions(transitions),
        "submit_attempts": sum(event.get("event") == "submit.started" for event in events),
        "clean_replay_attempts": sum(event.get("event") == "replay.started" for event in events),
        "failure_transitions": transitions,
    }


def _load_canary(evidence_dir: Path, manifest: dict[str, Any]) -> dict[str, Any] | None:
    canary_dir = evidence_dir / "provider-canaries"
    for path in sorted(canary_dir.glob("provider_canary_*.json"), reverse=True):
        value = _load_json(path)
        if value.get("document_type") == "formal_provider_canary" and value.get("manifest_sha256") == protocol.manifest_sha256(manifest):
            return value
    return None


def build_report(manifest: dict[str, Any], evidence_dir: Path) -> dict[str, Any]:
    protocol.validate_manifest(manifest)
    observed: list[tuple[dict[str, Any], Path, list[dict[str, Any]]]] = []
    for ledger_path in sorted(evidence_dir.rglob("*.jsonl")):
        try:
            events = ExperimentLedger.verify_path(ledger_path)
        except EvidenceError as exc:
            raise ReportError(f"invalid physical ledger: {ledger_path}") from exc
        slot = _slot_for_events(manifest, events)
        if slot is not None:
            observed.append((slot, ledger_path, events))
    observed.sort(key=lambda item: item[0]["order"])
    orders = [slot["order"] for slot, _path, _events in observed]
    if len(orders) != len(set(orders)) or orders != list(range(1, len(orders) + 1)):
        raise ReportError("observed physical ledgers are not the frozen schedule prefix")

    attempt_summaries: list[dict[str, Any]] = []
    attempt_evidence: list[dict[str, Any]] = []
    for slot, ledger_path, events in observed:
        sidecar_path = _sidecar_path(ledger_path)
        records, fidelity = _read_completed_sidecar(
            sidecar_path,
            manifest=manifest,
            slot=slot,
            events=events,
        )
        summary = summarize_attempt(manifest, slot, events, records, fidelity)
        attempt_summaries.append(summary)
        attempt_evidence.append(
            {
                "order": slot["order"],
                "physical_attempt_id": events[0]["physical_attempt_id"],
                "ledger": str(ledger_path),
                "repair_sidecar": str(sidecar_path),
                "fidelity": fidelity,
                "summary": summary,
            }
        )

    parent = parent_protocol.validate_manifest(parent_protocol._load_json(protocol.DEFAULT_PARENT_MANIFEST))
    paired = analyzer.build_report(parent, attempt_summaries)
    canary = _load_canary(evidence_dir, manifest)
    if attempt_summaries and (canary is None or canary.get("passed") is not True):
        raise ReportError("physical evidence requires a successful frozen provider canary")
    return {
        "report_version": REPORT_VERSION,
        "benchmark_id": manifest["benchmark"]["id"],
        "manifest_sha256": protocol.manifest_sha256(manifest),
        "parent_runtime_manifest_sha256": protocol.PARENT_CANONICAL_SHA256,
        "scope": {
            "descriptive_only": True,
            "p_value_computed": False,
            "model_ranking_performed": False,
        },
        "canary": canary,
        "collection": {
            "planned_slots": 12,
            "observed_slots": len(attempt_summaries),
            "complete_pairs": len(attempt_summaries) // 2,
            "recorded_tokens": sum(attempt["recorded_tokens"] for attempt in attempt_summaries),
            "recorded_token_limit": protocol.RECORDED_TOKEN_LIMIT,
            "model_requests": sum(attempt["model_requests"] for attempt in attempt_summaries),
            "wall_clock_seconds": round(
                sum(attempt["wall_clock_seconds"] for attempt in attempt_summaries),
                6,
            ),
        },
        "paired_analysis": paired,
        "attempts": attempt_evidence,
    }


def render_markdown(report: dict[str, Any]) -> str:
    collection = report["collection"]
    paired = report["paired_analysis"]
    lines = [
        "# Verifier-driven repair 配对 pilot 报告",
        "",
        f"- 协议：`{report['benchmark_id']}`",
        f"- 授权 manifest SHA-256：`{report['manifest_sha256']}`",
        f"- 已观察：{collection['observed_slots']}/12 slots，{collection['complete_pairs']}/6 complete pairs",
        f"- recorded tokens：{collection['recorded_tokens']}/{collection['recorded_token_limit']}",
        f"- 模型请求：{collection['model_requests']}",
        f"- physical-attempt 墙钟合计：{collection['wall_clock_seconds']:.3f} 秒",
        "",
        "## 配对结果",
        "",
        f"- paired primary eligible：`{str(paired['scope']['paired_primary_eligible']).lower()}`",
        f"- Oracle discordance：`{json.dumps(paired['oracle_discordance'], ensure_ascii=False, sort_keys=True)}`",
        f"- 不完整 pairs：`{json.dumps(paired['collection']['incomplete_pairs'], ensure_ascii=False)}`",
        "",
        "本报告只做配对描述，不计算 p-value，不按单个项目或不完整 block 排名模型。",
        "",
    ]
    return "\n".join(lines)


def write_reports(report: dict[str, Any], *, json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8", newline="\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=protocol.DEFAULT_MANIFEST)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN_REPORT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        report = build_report(manifest, args.evidence_dir)
        write_reports(report, json_path=args.json, markdown_path=args.markdown)
    except (OSError, ReportError, analyzer.AnalyzerError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "complete_pairs": report["collection"]["complete_pairs"],
                "json_report": str(args.json),
                "markdown_report": str(args.markdown),
                "observed_slots": report["collection"]["observed_slots"],
                "status": "written",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
