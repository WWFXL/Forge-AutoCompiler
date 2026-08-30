#!/usr/bin/env python3
"""Issue #228 OpenH264 冻结 evidence 的只读结果审计与 sidecar。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from deerflow.compile.evidence import ExperimentLedger

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVIDENCE_ROOT = Path("/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-openh264-execution-v1")
DEFAULT_SIDECAR = "reports/audit-v1.json"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/228"
SCHEMA_VERSION = "forge-opaque-provenance-openh264-result-audit-1.0.0"
EXPECTED_RELEASE_REVISION = "9873e7a8548a698e03fc4d9f3cf19123ffeb8070"
EXPECTED_MANIFEST_SHA256 = "536f6688f8c6289e2e4bd3a46ebd95fab7dc7dbdedf728e88d937cb171bb0cfc"
EXPECTED_EVIDENCE_IDENTITY_SHA256 = "035d45828ebd112e4f0bd44678e654a8cddcf2c69f92d4d18f358103c1142243"
EXPECTED_INPUT_SHA256 = {
    "checkpoint/coordinator.sqlite": "eeeeb0463d8440ccb41d0143a4343206c98a2ac35121cb93ee8cf4db6a85dafc",
    "checkpoint/messages.sqlite": "d8321738ecc9f1c6533cf1d7272adefb2206041953814fb4460f4e8ae4580d2f",
    "checkpoints/opaque-provenance-openh264-pair-01/parent/events.jsonl": "2725205cf361f6ecb5a46d2c21d37b928163c3dfa94a44f98264865b8c0f8543",
    "markers/dependency-fixture.json": "2a17495d2ebb218d63c0c25b7fb57932bfbedd580999bc66860ba0546affb34b",
    "markers/pair.json": "fbf3cb7108fa830ba6f478ae81cfb1c5adbe3a755a4c82a35fefd80c0e6fd7c0",
    "markers/reachability.json": "e47ad30b06ab04b62db231b27b562e52258754384090c26a3397ae8425928d0f",
    "pairs/opaque-provenance-openh264-pair-01/arms/baseline.jsonl": "f8e65cce0d780a4fbd7a8106b32899d19911b9d68b277c47ccb9d85dbef6aa2f",
    "pairs/opaque-provenance-openh264-pair-01/arms/treatment.jsonl": "6e2365e1e18b5205eb70068efa0af6b69bff07b17b3d759e42e1d8981d1991ca",
    "reports/canary.json": "bf5cd12f2d109e710ea8fbc95d8aa7ed86eedb93b245a956130d899bab7d137e",
    "reports/dependency-fixture-cleanup.json": "4f813e46469144b11381ce12e8105c09302d3943397a1375fec662401c083670",
    "reports/dependency-fixture.json": "ca907b43c5d82f7db4c80aafd3db0e88fdda8b0f2c8aec88b4c9bd1346bfdaf7",
    "reports/reachability.json": "84cc199fdb75af6a1e9487b9279ae0a75535506f02f77ffb2603e503f08f3ae6",
}
PARENT_LEDGER_PATH = "checkpoints/opaque-provenance-openh264-pair-01/parent/events.jsonl"
ARM_LEDGER_PATHS = {
    "baseline": "pairs/opaque-provenance-openh264-pair-01/arms/baseline.jsonl",
    "treatment": "pairs/opaque-provenance-openh264-pair-01/arms/treatment.jsonl",
}
EXPECTED_TERMINAL_HEADS = {
    "parent": "a40bfbd41a234a5c5c2fa510d3de270e937fc94fd7902537a4c032bf48952f40",
    "baseline": "ee71cece9216c6ce663c2287037c98a4be6e91fc11454f90017722b357eda7fa",
    "treatment": "d1e8fe7432be322684fe19fb127cd1c2c344b82c7894160b3d50e087a628785e",
}
EXPECTED_REPORT_TIME_HEADS = {
    "baseline": EXPECTED_TERMINAL_HEADS["baseline"],
    "treatment": "c5cca3895c0c67cbcbcabea726e7ff48d7208a4abe9b5a54e24ffec88a65b62f",
}
ACTION_LIMITS = {
    "inspection": 4,
    "repair_build": 2,
    "artifact_stage": 2,
    "submit": 2,
}
EXPECTED_ACTION_CONSUMED = {
    "baseline": {"inspection": 4, "repair_build": 0, "artifact_stage": 0, "submit": 0},
    "treatment": {"inspection": 4, "repair_build": 1, "artifact_stage": 0, "submit": 1},
}
EXPECTED_REQUESTS = {
    "baseline": {"model_requests": 8, "recorded_tokens": 37_271},
    "treatment": {"model_requests": 6, "recorded_tokens": 20_584},
}
EXPECTED_R0_COUNTS = {"baseline": 7, "treatment": 3}
EXPECTED_R0_CLASSIFICATIONS = [
    "compound_shell_forbidden",
    "inspection_budget_exhausted",
    "repair_build_arguments_invalid",
]


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


def verify_source_inputs(evidence_root: Path) -> dict[str, str]:
    actual_paths = {path.relative_to(evidence_root).as_posix() for path in evidence_root.rglob("*") if path.is_file()}
    allowed_paths = set(EXPECTED_INPUT_SHA256) | {DEFAULT_SIDECAR}
    if not set(EXPECTED_INPUT_SHA256).issubset(actual_paths):
        raise ResultAuditError("frozen source evidence is incomplete")
    if not actual_paths.issubset(allowed_paths):
        raise ResultAuditError("unexpected evidence file is present")
    actual = {relative_path: file_sha256(evidence_root / relative_path) for relative_path in sorted(EXPECTED_INPUT_SHA256)}
    if actual != EXPECTED_INPUT_SHA256:
        raise ResultAuditError("frozen source evidence hash drifted")
    return actual


def summarize_r0(arm: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    failures = [event for event in events if event.get("event") == "agent.tool_failed" and event.get("payload", {}).get("exception_class") == "ObservableRuntimeParityGateError"]
    observations = [event for event in events if event.get("event") == "agent.tool_rejection_observed"]
    failure_ids = [event.get("payload", {}).get("failure_id") for event in failures]
    observation_ids = [event.get("payload", {}).get("failure_id") for event in observations]
    if any(not isinstance(value, str) or not value for value in failure_ids + observation_ids) or len(failure_ids) != len(set(failure_ids)) or len(observation_ids) != len(set(observation_ids)) or set(failure_ids) != set(observation_ids):
        raise ResultAuditError("classified rejection and R0 companion linkage is incomplete")
    classifications = sorted({event.get("payload", {}).get("rejection_classification") for event in observations})
    if len(failures) != EXPECTED_R0_COUNTS.get(arm) or classifications != EXPECTED_R0_CLASSIFICATIONS:
        raise ResultAuditError("R0 rejection summary drifted")
    return {
        "classified_rejections": len(failures),
        "companion_events": len(observations),
        "companion_complete": True,
        "rejection_classifications": classifications,
        "raw_command_persisted": False,
        "recovered_from_frozen_ledger": True,
    }


def summarize_model_requests(arm: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    started = [event for event in events if event.get("event") == "model.request_started"]
    completed = [event for event in events if event.get("event") == "model.request_completed"]
    failed = [event for event in events if event.get("event") == "model.request_failed"]
    cancelled = [event for event in events if event.get("event") == "model.request_cancelled"]
    started_ids = [event.get("payload", {}).get("model_request_id") for event in started]
    completed_ids = [event.get("payload", {}).get("model_request_id") for event in completed]
    if (
        any(not isinstance(value, str) or not value for value in started_ids + completed_ids)
        or len(started_ids) != len(set(started_ids))
        or len(completed_ids) != len(set(completed_ids))
        or set(started_ids) != set(completed_ids)
        or failed
        or cancelled
    ):
        raise ResultAuditError("model request lifecycle is incomplete")
    try:
        recorded_tokens = sum(event["payload"]["token_usage"]["total_tokens"] for event in completed)
    except (KeyError, TypeError) as exc:
        raise ResultAuditError("model token evidence is incomplete") from exc
    summary = {
        "model_requests": len(completed),
        "recorded_tokens": recorded_tokens,
        "completed_requests": len(completed),
        "failed_requests": 0,
        "cancelled_requests": 0,
        "lifecycle_complete": True,
        "recovered_from_frozen_ledger": True,
    }
    if {key: summary[key] for key in ("model_requests", "recorded_tokens")} != EXPECTED_REQUESTS.get(arm):
        raise ResultAuditError("model request summary drifted")
    return summary


def reconstruct_action_budget(arm: str, events: list[dict[str, Any]]) -> dict[str, Any]:
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
        command_id = payload.get("command_id")
        if not isinstance(command_id, str) or command_id in completed_ids or payload.get("stage") != "bash" or payload.get("timed_out") is not False or payload.get("termination") not in {"completed", "failed"}:
            raise ResultAuditError("command completion evidence is ambiguous")
        completed_ids.append(command_id)
    if set(completed_ids) != set(role_by_command):
        raise ResultAuditError("command completion and role evidence differ")

    submit_started = [event.get("payload", {}).get("submit_attempt_id") for event in events if event.get("event") == "submit.started"]
    submit_completed = [event.get("payload", {}).get("submit_attempt_id") for event in events if event.get("event") == "submit.completed"]
    if (
        any(not isinstance(value, str) or not value for value in submit_started + submit_completed)
        or len(submit_started) != len(set(submit_started))
        or len(submit_completed) != len(set(submit_completed))
        or set(submit_started) != set(submit_completed)
    ):
        raise ResultAuditError("submit lifecycle evidence is incomplete")

    consumed = {action: 0 for action in ACTION_LIMITS}
    for command_id in completed_ids:
        action = {
            "other": "inspection",
            "smoke": "inspection",
            "build": "repair_build",
            "artifact_stage": "artifact_stage",
        }[role_by_command[command_id]]
        consumed[action] += 1
    consumed["submit"] = len(submit_started)
    if consumed != EXPECTED_ACTION_CONSUMED[arm]:
        raise ResultAuditError("reconstructed action budget drifted")
    return {
        "limits": dict(ACTION_LIMITS),
        "consumed": consumed,
        "remaining": {action: ACTION_LIMITS[action] - consumed[action] for action in ACTION_LIMITS},
        "recovered_from_frozen_ledger": True,
    }


def summarize_ledger_head(
    label: str,
    events: list[dict[str, Any]],
    *,
    report_time_head: str | None = None,
) -> dict[str, Any]:
    if not events or events[-1].get("event") != "experiment.completed":
        raise ResultAuditError("ledger terminal event is missing")
    terminal_head = events[-1].get("event_sha256")
    if terminal_head != EXPECTED_TERMINAL_HEADS[label]:
        raise ResultAuditError("ledger terminal head drifted")
    result = {
        "event_count": len(events),
        "terminal_event": "experiment.completed",
        "terminal_ledger_head_sha256": terminal_head,
    }
    if report_time_head is None:
        return result
    if report_time_head != EXPECTED_REPORT_TIME_HEADS[label]:
        raise ResultAuditError("report-time ledger head drifted")
    if report_time_head == terminal_head:
        semantics = "terminal_head"
    elif events[-1].get("previous_event_sha256") == report_time_head:
        semantics = "pre_terminal_head"
    else:
        raise ResultAuditError("report-time head is not linked to the terminal ledger")
    return {
        **result,
        "report_time_ledger_head_sha256": report_time_head,
        "report_time_head_semantics": semantics,
    }


def _validate_attempt_document(value: dict[str, Any], *, label: str) -> None:
    if value.get("status") != "passed" or value.get("error_class") is not None or value.get("manifest_sha256") != EXPECTED_MANIFEST_SHA256 or value.get("release_revision") != EXPECTED_RELEASE_REVISION:
        raise ResultAuditError(f"{label} drifted")


def build_audit_document(
    *,
    manifest: dict[str, Any],
    report: dict[str, Any],
    pair_marker: dict[str, Any],
    reachability_marker: dict[str, Any],
    reachability_report: dict[str, Any],
    fixture_marker: dict[str, Any],
    fixture_report: dict[str, Any],
    fixture_cleanup_report: dict[str, Any],
    parent_events: list[dict[str, Any]],
    events_by_arm: dict[str, list[dict[str, Any]]],
    source_sha256: dict[str, str],
) -> dict[str, Any]:
    if canonical_sha256(manifest) != EXPECTED_MANIFEST_SHA256:
        raise ResultAuditError("manifest canonical identity drifted")
    if (
        report.get("manifest_sha256") != EXPECTED_MANIFEST_SHA256
        or report.get("evidence_identity_sha256") != EXPECTED_EVIDENCE_IDENTITY_SHA256
        or report.get("release_revision") != EXPECTED_RELEASE_REVISION
        or report.get("complete_pair") is not True
        or report.get("cleanup_succeeded") is not True
        or report.get("recorded_tokens") != 57_872
        or report.get("reachability_recorded_tokens") != 17
        or report.get("historical_pairs_pooled") is not False
        or report.get("treatment_effect_estimated") is not False
        or report.get("p_value_computed") is not False
        or report.get("model_ranking_performed") is not False
    ):
        raise ResultAuditError("canary report identity or inference boundary drifted")
    _validate_attempt_document(pair_marker, label="pair marker")
    _validate_attempt_document(reachability_marker, label="reachability marker")
    _validate_attempt_document(fixture_marker, label="dependency fixture marker")
    if (
        reachability_report.get("passed") is not True
        or reachability_report.get("request_count") != 1
        or reachability_report.get("recorded_tokens") != 17
        or reachability_report.get("request_timeout_seconds") != 300
        or reachability_report.get("max_retries") != 0
        or reachability_report.get("fallback_used") is not False
        or reachability_report.get("manifest_sha256") != EXPECTED_MANIFEST_SHA256
        or reachability_report.get("release_revision") != EXPECTED_RELEASE_REVISION
    ):
        raise ResultAuditError("reachability report drifted")
    if (
        fixture_report.get("manifest_sha256") != EXPECTED_MANIFEST_SHA256
        or fixture_report.get("release_revision") != EXPECTED_RELEASE_REVISION
        or fixture_report.get("apt_index_downloaded") is not False
        or fixture_report.get("preparation_container_removed") is not True
        or fixture_cleanup_report.get("manifest_sha256") != EXPECTED_MANIFEST_SHA256
        or fixture_cleanup_report.get("cleanup_succeeded") is not True
        or fixture_cleanup_report.get("container_absent") is not True
        or fixture_cleanup_report.get("tag_absent") is not True
        or fixture_cleanup_report.get("image_id_absent") is not True
    ):
        raise ResultAuditError("dependency fixture evidence drifted")

    arms = report.get("arms")
    if not isinstance(arms, list) or [item.get("arm") for item in arms] != ["baseline", "treatment"]:
        raise ResultAuditError("source arm order drifted")
    if report.get("r0_rejection_observability", {}).get("baseline") is not None or report.get("runtime_parity_action_budgets", {}).get("baseline") is not None:
        raise ResultAuditError("source report no longer matches the audit gap")

    audited_arms: dict[str, Any] = {}
    for arm_report in arms:
        arm = arm_report["arm"]
        events = events_by_arm.get(arm)
        if not isinstance(events, list):
            raise ResultAuditError("arm ledger is missing")
        requests = summarize_model_requests(arm, events)
        budget = reconstruct_action_budget(arm, events)
        r0 = summarize_r0(arm, events)
        head = summarize_ledger_head(
            arm,
            events,
            report_time_head=arm_report.get("ledger_head_sha256"),
        )
        metrics = arm_report.get("metrics", {})
        if (
            arm_report.get("model_requests") != requests["model_requests"]
            or arm_report.get("recorded_tokens") != requests["recorded_tokens"]
            or metrics.get("model_requests") != requests["model_requests"]
            or metrics.get("recorded_tokens") != requests["recorded_tokens"]
            or metrics.get("submit_attempts") != budget["consumed"]["submit"]
        ):
            raise ResultAuditError("arm report and recovered ledger summary differ")
        audited_arms[arm] = {
            "infrastructure_status": arm_report.get("infrastructure", {}).get("status"),
            "model_behavior_status": arm_report.get("model_behavior", {}).get("status"),
            "terminal_error_class": arm_report.get("model_behavior", {}).get("terminal_error_class"),
            "verification_outcome": arm_report.get("verification_outcome"),
            "p2": arm_report.get("p2"),
            "post_checkpoint_provenance_conversion": arm_report.get("post_checkpoint_provenance_conversion"),
            "model_request_summary": requests,
            "r0_rejection_observability": r0,
            "runtime_parity_action_budget": budget,
            "ledger": head,
        }

    baseline = audited_arms["baseline"]
    treatment = audited_arms["treatment"]
    if (
        baseline["infrastructure_status"] != "valid"
        or baseline["model_behavior_status"] != "graph_step_limit"
        or baseline["terminal_error_class"] != "GraphRecursionError"
        or baseline["verification_outcome"] != {"clean_replay_attempts": 0, "status": "not_attempted", "submit_attempts": 0}
        or baseline["p2"].get("status") != "unproven"
        or baseline["p2"].get("reason") != "opaque_wrapper"
        or baseline["post_checkpoint_provenance_conversion"] is not False
        or treatment["infrastructure_status"] != "valid"
        or treatment["model_behavior_status"] != "completed"
        or treatment["verification_outcome"] != {"clean_replay_attempts": 1, "status": "passed", "submit_attempts": 1}
        or treatment["p2"].get("status") != "proven"
        or treatment["p2"].get("proof_mode") != "direct_make"
        or treatment["post_checkpoint_provenance_conversion"] is not True
    ):
        raise ResultAuditError("arm outcome drifted from the frozen result")

    return {
        "schema_version": SCHEMA_VERSION,
        "document_type": "forge_opaque_provenance_openh264_result_audit",
        "issue_url": ISSUE_URL,
        "release_revision": EXPECTED_RELEASE_REVISION,
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "evidence_identity_sha256": EXPECTED_EVIDENCE_IDENTITY_SHA256,
        "source_sha256": source_sha256,
        "source_evidence_file_count": len(EXPECTED_INPUT_SHA256),
        "evidence_file_count_after_sidecar": len(EXPECTED_INPUT_SHA256) + 1,
        "source_report_gaps": [
            "baseline_r0_rejection_observability_null",
            "baseline_runtime_parity_action_budget_null",
            "treatment_report_time_head_precedes_terminal_event",
        ],
        "parent_ledger": summarize_ledger_head("parent", parent_events),
        "arms": audited_arms,
        "reachability": {
            "actual_model": reachability_report.get("actual_model"),
            "request_count": 1,
            "recorded_tokens": 17,
            "duration_ms": reachability_report.get("duration_ms"),
            "request_timeout_seconds": 300,
            "max_retries": 0,
            "fallback_used": False,
            "passed": True,
        },
        "dependency_fixture": {
            "apt_index_downloaded": False,
            "preparation_container_removed": True,
            "cleanup_succeeded": True,
            "container_absent": True,
            "tag_absent": True,
            "image_id_absent": True,
        },
        "paired_descriptive_outcome": {
            "complete_pair": True,
            "baseline_p2_status": "unproven",
            "baseline_p2_reason": "opaque_wrapper",
            "treatment_p2_status": "proven",
            "treatment_p2_proof_mode": "direct_make",
            "treatment_submit_attempts": 1,
            "treatment_clean_replay_attempts": 1,
            "cleanup_succeeded": True,
        },
        "historical_pairs_pooled": False,
        "treatment_effect_estimated": False,
        "p_value_computed": False,
        "model_ranking_performed": False,
        "provider_calls": 0,
        "credential_read": False,
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
    source_sha256 = verify_source_inputs(evidence_root)
    manifest = _load_object(
        repo_root / "benchmarks/manifests/cpp-opaque-provenance-openh264-execution.json",
        "manifest",
    )
    parent_events = ExperimentLedger.open(evidence_root / PARENT_LEDGER_PATH).read()
    events_by_arm = {arm: ExperimentLedger.open(evidence_root / relative_path).read() for arm, relative_path in ARM_LEDGER_PATHS.items()}
    return build_audit_document(
        manifest=manifest,
        report=_load_object(evidence_root / "reports/canary.json", "canary report"),
        pair_marker=_load_object(evidence_root / "markers/pair.json", "pair marker"),
        reachability_marker=_load_object(evidence_root / "markers/reachability.json", "reachability marker"),
        reachability_report=_load_object(evidence_root / "reports/reachability.json", "reachability report"),
        fixture_marker=_load_object(evidence_root / "markers/dependency-fixture.json", "dependency fixture marker"),
        fixture_report=_load_object(evidence_root / "reports/dependency-fixture.json", "dependency fixture report"),
        fixture_cleanup_report=_load_object(evidence_root / "reports/dependency-fixture-cleanup.json", "dependency fixture cleanup report"),
        parent_events=parent_events,
        events_by_arm=events_by_arm,
        source_sha256=source_sha256,
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
        source_before = result["source_sha256"]
        write_sidecar_once(args.evidence_root / DEFAULT_SIDECAR, result)
        if verify_source_inputs(args.evidence_root) != source_before:
            raise ResultAuditError("source evidence changed while writing sidecar")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
