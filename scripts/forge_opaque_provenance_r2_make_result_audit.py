#!/usr/bin/env python3
"""Issue #210 R2 Make 冻结 evidence 的只读结果审计与 sidecar。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from deerflow.compile.evidence import ExperimentLedger

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVIDENCE_ROOT = Path("/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-r2-hoextdown-v1")
DEFAULT_SIDECAR = "reports/audit-v1.json"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/210"
SCHEMA_VERSION = "forge-opaque-provenance-r2-make-result-audit-1.0.0"
EXPECTED_MANIFEST_SHA256 = "113192d509b3c15762f8055cb32fc9364a4a4be6bede1eeed838e540a025224e"
EXPECTED_EVIDENCE_IDENTITY_SHA256 = "c88f74282424de834be1523c9fd93fa18171c262a05b93f09aebca9359a424a4"
EXPECTED_INPUT_SHA256 = {
    "reports/canary.json": ("27a1bb39d693db535aa8a34e9d538dc8ee2b9def3b83262293110e0791543a1b"),
    "markers/pair.json": ("46bf6eff450e1e11a3091296c076730e2a509520b7cddf4b35ad37157d4a5ee9"),
    "checkpoints/opaque-provenance-r2-hoextdown-pair-01/parent/events.jsonl": ("077538789c0931edfc7aa276480ad9f841e81c9187348584c872b8da2453c4d2"),
    "pairs/opaque-provenance-r2-hoextdown-pair-01/arms/baseline.jsonl": ("3a218887cd741e535f75483abce5660ca17356b39393e338aa84437f9d948bb0"),
    "pairs/opaque-provenance-r2-hoextdown-pair-01/arms/treatment.jsonl": ("07a9ae876a8fd7ca7a6ccedb3b6050614045e065453f5977ac213f57fc3ceceb"),
}
ARM_LEDGER_PATHS = {
    "baseline": ("pairs/opaque-provenance-r2-hoextdown-pair-01/arms/baseline.jsonl"),
    "treatment": ("pairs/opaque-provenance-r2-hoextdown-pair-01/arms/treatment.jsonl"),
}
ACTION_LIMITS = {
    "inspection": 4,
    "repair_build": 2,
    "artifact_stage": 2,
    "submit": 2,
}
EXPECTED_ACTION_CONSUMED = {
    "baseline": {
        "inspection": 0,
        "repair_build": 0,
        "artifact_stage": 0,
        "submit": 0,
    },
    "treatment": {
        "inspection": 4,
        "repair_build": 0,
        "artifact_stage": 0,
        "submit": 0,
    },
}


class ResultAuditError(RuntimeError):
    """冻结结果、ledger 或可恢复汇总不完整。"""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResultAuditError(f"cannot read {label}") from exc
    if not isinstance(value, dict):
        raise ResultAuditError(f"{label} must be an object")
    return value


def summarize_r0(events: list[dict[str, Any]]) -> dict[str, Any]:
    failures = [event for event in events if event.get("event") == "agent.tool_failed" and event.get("payload", {}).get("exception_class") == "ObservableRuntimeParityGateError"]
    observations = [event for event in events if event.get("event") == "agent.tool_rejection_observed"]
    failure_ids = [event["payload"].get("failure_id") for event in failures]
    observation_ids = [event["payload"].get("failure_id") for event in observations]
    if (
        any(not isinstance(value, str) or not value for value in failure_ids)
        or any(not isinstance(value, str) or not value for value in observation_ids)
        or len(failure_ids) != len(set(failure_ids))
        or len(observation_ids) != len(set(observation_ids))
        or set(failure_ids) != set(observation_ids)
    ):
        raise ResultAuditError("classified rejection and R0 companion linkage is incomplete")
    return {
        "classified_rejections": len(failures),
        "companion_events": len(observations),
        "companion_complete": True,
        "rejection_classifications": sorted({event["payload"]["rejection_classification"] for event in observations}),
        "raw_command_persisted": False,
    }


def reconstruct_action_budget(
    arm: str,
    events: list[dict[str, Any]],
    *,
    submit_attempts: int,
) -> dict[str, Any]:
    if arm not in EXPECTED_ACTION_CONSUMED:
        raise ResultAuditError("unknown arm")
    role_by_command: dict[str, str] = {}
    for event in events:
        if event.get("event") != "command.role_resolved":
            continue
        payload = event.get("payload", {})
        command_id = payload.get("command_id")
        role = payload.get("effective_role")
        if not isinstance(command_id, str) or command_id in role_by_command or role not in {"other", "smoke", "build", "artifact_stage"}:
            raise ResultAuditError("command role evidence is ambiguous")
        role_by_command[command_id] = role

    completed_ids: list[str] = []
    for event in events:
        if event.get("event") != "command.completed":
            continue
        payload = event.get("payload", {})
        if payload.get("stage") == "bash" and payload.get("exit_code") == 0 and payload.get("termination") == "completed" and payload.get("timed_out") is False:
            command_id = payload.get("command_id")
            if not isinstance(command_id, str) or command_id in completed_ids:
                raise ResultAuditError("completed command evidence is ambiguous")
            completed_ids.append(command_id)
    if set(completed_ids) != set(role_by_command):
        raise ResultAuditError("command completion and role evidence differ")
    if type(submit_attempts) is not int or submit_attempts != 0:
        raise ResultAuditError("submit action budget is not recoverable for this result")

    consumed = {action: 0 for action in ACTION_LIMITS}
    for command_id in completed_ids:
        role = role_by_command[command_id]
        action = {
            "other": "inspection",
            "smoke": "inspection",
            "build": "repair_build",
            "artifact_stage": "artifact_stage",
        }[role]
        consumed[action] += 1
    consumed["submit"] = submit_attempts
    if consumed != EXPECTED_ACTION_CONSUMED[arm]:
        raise ResultAuditError("reconstructed action budget drifted")
    return {
        "limits": dict(ACTION_LIMITS),
        "consumed": consumed,
        "remaining": {action: ACTION_LIMITS[action] - consumed[action] for action in ACTION_LIMITS},
        "recovered_from_frozen_ledger": True,
    }


def build_audit_document(
    *,
    manifest: dict[str, Any],
    report: dict[str, Any],
    pair_marker: dict[str, Any],
    events_by_arm: dict[str, list[dict[str, Any]]],
    source_sha256: dict[str, str],
) -> dict[str, Any]:
    if canonical_sha256(manifest) != EXPECTED_MANIFEST_SHA256:
        raise ResultAuditError("manifest canonical identity drifted")
    if report.get("manifest_sha256") != EXPECTED_MANIFEST_SHA256:
        raise ResultAuditError("canary manifest identity drifted")
    if report.get("evidence_identity_sha256") != EXPECTED_EVIDENCE_IDENTITY_SHA256:
        raise ResultAuditError("canary evidence identity drifted")
    if (
        pair_marker.get("status") != "passed"
        or report.get("complete_pair") is not True
        or report.get("cleanup_succeeded") is not True
        or report.get("runtime_parity_action_budgets") != {"baseline": None, "treatment": None}
        or report.get("r0_rejection_observability") != {"baseline": None, "treatment": None}
    ):
        raise ResultAuditError("source report no longer matches the audit defect")
    arms = report.get("arms")
    if not isinstance(arms, list) or [item.get("arm") for item in arms] != [
        "baseline",
        "treatment",
    ]:
        raise ResultAuditError("source arm order drifted")

    audited_arms: dict[str, Any] = {}
    for arm_report in arms:
        arm = arm_report["arm"]
        events = events_by_arm.get(arm)
        if not isinstance(events, list):
            raise ResultAuditError("arm ledger is missing")
        metrics = arm_report.get("metrics", {})
        audited_arms[arm] = {
            "infrastructure_status": arm_report.get("infrastructure", {}).get("status"),
            "model_behavior_status": arm_report.get("model_behavior", {}).get("status"),
            "model_requests": arm_report.get("model_requests"),
            "recorded_tokens": arm_report.get("recorded_tokens"),
            "submit_attempts": metrics.get("submit_attempts"),
            "clean_replay_attempts": metrics.get("clean_replay_attempts"),
            "p2_status": arm_report.get("p2", {}).get("status"),
            "p2_reason": arm_report.get("p2", {}).get("reason"),
            "post_checkpoint_provenance_conversion": arm_report.get("post_checkpoint_provenance_conversion"),
            "r0_rejection_observability": summarize_r0(events),
            "runtime_parity_action_budget": reconstruct_action_budget(
                arm,
                events,
                submit_attempts=metrics.get("submit_attempts"),
            ),
        }
    baseline = audited_arms["baseline"]
    treatment = audited_arms["treatment"]
    if (
        baseline["infrastructure_status"] != "endpoint_censored"
        or baseline["p2_status"] != "unproven"
        or treatment["infrastructure_status"] != "valid"
        or treatment["p2_status"] != "unproven"
        or treatment["post_checkpoint_provenance_conversion"] is not False
    ):
        raise ResultAuditError("arm outcome drifted from the frozen result")
    return {
        "schema_version": SCHEMA_VERSION,
        "document_type": "forge_opaque_provenance_r2_make_result_audit",
        "issue_url": ISSUE_URL,
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "evidence_identity_sha256": EXPECTED_EVIDENCE_IDENTITY_SHA256,
        "source_sha256": source_sha256,
        "source_report_summary_fields_missing": [
            "runtime_parity_action_budgets",
            "r0_rejection_observability",
        ],
        "arms": audited_arms,
        "paired_primary_estimand": {
            "status": "not_estimable",
            "reason": "baseline_endpoint_censored",
        },
        "treatment_descriptive_outcome": {
            "status": "observed_no_conversion",
            "submit_attempts": treatment["submit_attempts"],
            "p2_status": treatment["p2_status"],
        },
        "complete_pair_is_structural_only": True,
        "historical_pairs_pooled": False,
        "treatment_effect_estimated": False,
        "p_value_computed": False,
        "model_ranking_performed": False,
        "provider_calls": 0,
        "docker_executed": False,
        "formal_attempts": 0,
        "model_tokens": 0,
        "source_evidence_modified": False,
    }


def audit_evidence(
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    manifest = _load_object(
        repo_root / "benchmarks/manifests/cpp-opaque-provenance-r2-make-execution.json",
        "manifest",
    )
    for relative_path, expected in EXPECTED_INPUT_SHA256.items():
        path = evidence_root / relative_path
        if not path.is_file() or file_sha256(path) != expected:
            raise ResultAuditError(f"frozen input drifted: {relative_path}")
    report = _load_object(evidence_root / "reports/canary.json", "canary report")
    pair_marker = _load_object(evidence_root / "markers/pair.json", "pair marker")
    parent_path = evidence_root / ("checkpoints/opaque-provenance-r2-hoextdown-pair-01/parent/events.jsonl")
    ExperimentLedger.open(parent_path).read()
    events_by_arm = {arm: ExperimentLedger.open(evidence_root / relative_path).read() for arm, relative_path in ARM_LEDGER_PATHS.items()}
    return build_audit_document(
        manifest=manifest,
        report=report,
        pair_marker=pair_marker,
        events_by_arm=events_by_arm,
        source_sha256=dict(EXPECTED_INPUT_SHA256),
    )


def write_sidecar_once(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    except FileExistsError as exc:
        raise ResultAuditError("audit sidecar already exists") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("audit", "write-sidecar"))
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    result = audit_evidence(args.evidence_root, repo_root=args.repo_root)
    if args.command == "write-sidecar":
        write_sidecar_once(args.evidence_root / DEFAULT_SIDECAR, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
