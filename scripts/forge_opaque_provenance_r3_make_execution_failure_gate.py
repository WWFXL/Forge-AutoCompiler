#!/usr/bin/env python3
"""Issue #220 R3 Make 失败 evidence 审计与未来执行安全门禁。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import forge_opaque_provenance_make_rejection_observability_gate as make_observability
import forge_opaque_provenance_make_runtime_parity_gate as make_parity
import forge_opaque_provenance_r3_make_candidate_runner as r3_candidate

from deerflow.compile.evidence import ExperimentLedger, deactivate_experiment

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVIDENCE_ROOT = Path(
    "/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-r3-hoextdown-v1"
)
DEFAULT_SIDECAR = "reports/failure-audit-v1.json"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/220"
SCHEMA_VERSION = "forge-opaque-provenance-r3-make-execution-failure-audit-1.0.0"
EXPECTED_MANIFEST_SHA256 = (
    "e2335b9e180ff539752dbb6b9d049da561980b0af7a64a193b49ab423913e86f"
)
EXPECTED_EVIDENCE_IDENTITY_SHA256 = (
    "17bf1a758d953f4e0c579039c97c8a3e669caf92ca720f93b3edfe29116c9890"
)
CAPTURE_ID = "opaque-r3-make-33f2bf48e0d5"
PAIR_ID = "opaque-provenance-r3-hoextdown-pair-01"
EXPECTED_INPUT_SHA256 = {
    "reports/reachability.json": (
        "ab3faa1e3a7341f86858020d1a2d7446e2ae035156a211354a39776d22567313"
    ),
    "markers/reachability.json": (
        "9518d926646f97523e8aeb9b720cd834ffef851a58a2b595e36c0e0f71c38b9f"
    ),
    "markers/pair.json": (
        "8c9510134806e73bec2d847ba8402663340b889a6f5382c91104c47404744c5a"
    ),
    f"checkpoints/{PAIR_ID}/parent/events.jsonl": (
        "1c293e8070781742d5251d7992fd7c32a8a01b25b17995762372882db9ea3686"
    ),
    f"pairs/{PAIR_ID}/arms/baseline.jsonl": (
        "bfb99d21828b59537117f41dc1b01aa282d8ec315348fe73418a28bd79d344ff"
    ),
    f"pairs/{PAIR_ID}/arms/treatment.jsonl": (
        "b8ec8569fa09339700e2fbe70898da43692f5e2b623a7f4d666e1e05f53e1305"
    ),
    "checkpoint/coordinator.sqlite": (
        "4e4951f099dd6fe0c20bb3a2d7d9031a7360c9913e1ab873a8be1c2f0a75054b"
    ),
    "checkpoint/messages.sqlite": (
        "5c10a000bc68e7a09053396e298b8e8b52256c6084a51b3e8b9a71dedb970117"
    ),
}
EXPECTED_COMPONENT_SHA256 = {
    "scripts/forge_opaque_provenance_r3_make_execution_runner.py": (
        "5e955e79a15b00cd97726d1254d9716f5f8f18225c2149078f51a2adba420955"
    ),
    "scripts/forge_opaque_provenance_r3_make_candidate_runner.py": (
        "b8ec84f3835ecbbc462232b676c5ebf72e15a7f021be2a148d1b85d8138e9be0"
    ),
    "scripts/forge_opaque_provenance_r1_execution_runner.py": (
        "eb782230560a6e8ca20a973c7a8e89c0dc20e57cf22a5294d2fd8030a7fdcd49"
    ),
}
SESSION_INPUTS = {
    "baseline": (
        "baseline-opaque-r3-make-33f2bf48e0d5-thread/"
        "baseline-opaque-r3-make-33f2bf48e0d5-session/session.json",
        "f874ace0be0299a2699a8cf4a9042deb7ee1f64e14ef1ad501ec82429d430753",
    ),
    "treatment": (
        "treatment-opaque-r3-make-33f2bf48e0d5-thread/"
        "treatment-opaque-r3-make-33f2bf48e0d5-session/session.json",
        "9ce10cb9ad2def594bb0f6ab2c3719972f7c5b2e859447c116bcddff36f99e11",
    ),
}
MODEL_REQUEST_EVENTS = frozenset(
    {
        "model.request_started",
        "model.request_completed",
        "model.request_failed",
        "model.request_cancelled",
    }
)


class FailureGateError(RuntimeError):
    """冻结输入、失败分类或安全门禁不完整。"""


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


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
        raise FailureGateError(f"cannot read {label}") from exc
    if not isinstance(value, dict):
        raise FailureGateError(f"{label} must be an object")
    return value


def build_runtime_bindings() -> tuple[SimpleNamespace, SimpleNamespace]:
    """为下一版 runner 合并 R3 action adapter 与冻结 R0 companion。"""

    parity = SimpleNamespace(
        FrozenActionPolicy=r3_candidate.R3ActionPolicy,
        SerialToolCallMiddleware=make_parity.SerialToolCallMiddleware,
    )
    observability = SimpleNamespace(
        OBSERVATION_EVENT=make_observability.OBSERVATION_EVENT,
        RejectionObservationRegistry=make_observability.RejectionObservationRegistry,
        ObservableRuntimeParityToolAdapter=(
            r3_candidate.ObservableRuntimeParityToolAdapter
        ),
    )
    return parity, observability


def classify_pre_model_failure(
    *,
    arm: str,
    ledger: ExperimentLedger,
    error: Exception,
) -> dict[str, Any] | None:
    """零模型请求异常必须作为机制执行失败，而不是模型 no-submit。"""

    events = ledger.read()
    if any(event["event"] in MODEL_REQUEST_EVENTS for event in events):
        return None
    terminal_error_class = type(error).__name__
    ledger.append(
        "experiment.completed",
        {
            "status": "invalid_mechanism_attempt",
            "classification": "pre_model_execution_error",
            "terminal_error_class": terminal_error_class,
        },
    )
    return {
        "arm": arm,
        "status": "invalid",
        "valid_behavioral_observation": False,
        "infrastructure": {"status": "mechanism_invalid"},
        "model_behavior": {
            "status": "not_observed",
            "terminal_error_class": terminal_error_class,
        },
        "model_requests": 0,
        "recorded_tokens": 0,
        "verification_outcome": {
            "status": "not_attempted",
            "submit_attempts": 0,
            "clean_replay_attempts": 0,
        },
        "physical_attempt_id": ledger.physical_attempt_id,
        "ledger_head_sha256": ledger.read()[-1]["event_sha256"],
    }


def cleanup_after_deactivation(
    gate: Any,
    capture_id: str,
    *,
    parent_session: Any,
    experiment_thread_ids: list[str],
    deactivate: Callable[[str], Any] = deactivate_experiment,
) -> Any:
    """先解除所有 experiment context，再进入 production cleanup。"""

    safe_ids = tuple(dict.fromkeys(experiment_thread_ids))
    if not safe_ids or any(
        not isinstance(value, str) or not value for value in safe_ids
    ):
        raise FailureGateError("cleanup requires explicit experiment thread ids")
    for thread_id in safe_ids:
        deactivate(thread_id)
    return gate.cleanup(capture_id, parent_session=parent_session)


def _arm_summary(arm: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    event_names = [event["event"] for event in events]
    if event_names != ["experiment.started", "experiment.completed"]:
        raise FailureGateError(f"{arm} ledger no longer matches zero-request failure")
    terminal = events[-1]["payload"]
    if (
        terminal.get("status") != "model_behavior_outcome"
        or terminal.get("model_behavior") != "no_submit"
        or terminal.get("verification_outcome") != "not_attempted"
    ):
        raise FailureGateError(f"{arm} terminal taxonomy drifted")
    return {
        "ledger_events": len(events),
        "model_requests": 0,
        "recorded_tokens": 0,
        "submit_attempts": 0,
        "clean_replay_attempts": 0,
        "persisted_terminal_taxonomy": "no_submit",
        "valid_behavioral_observation": False,
        "corrected_failure_classification": "pre_model_execution_error",
        "original_terminal_error_class": "not_recoverable_from_frozen_evidence",
    }


def _coordinator_summary(path: Path) -> dict[str, Any]:
    uri = f"file:{path.as_posix()}?mode=ro&immutable=1"
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            row = connection.execute(
                "SELECT capture_id, phase, payload_json FROM checkpoint_capture"
            ).fetchone()
    except sqlite3.Error as exc:
        raise FailureGateError("cannot read coordinator evidence") from exc
    if row is None or row[0] != CAPTURE_ID or row[1] != "cleanup_pending":
        raise FailureGateError("coordinator failure phase drifted")
    payload = json.loads(row[2])
    arm_states = {
        arm: payload.get("arms", {}).get(arm, {}).get("status")
        for arm in ("baseline", "treatment")
    }
    if arm_states != {"baseline": "ready", "treatment": "ready"}:
        raise FailureGateError("coordinator arm states drifted")
    return {
        "capture_id": row[0],
        "phase": row[1],
        "arm_states": arm_states,
        "cleanup_recorded": payload.get("cleanup") is not None,
    }


def audit_evidence(
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    manifest = _load_object(
        repo_root / "benchmarks/manifests/cpp-opaque-provenance-r3-make-execution.json",
        "manifest",
    )
    if canonical_sha256(manifest) != EXPECTED_MANIFEST_SHA256:
        raise FailureGateError("manifest canonical identity drifted")
    for relative_path, expected in EXPECTED_COMPONENT_SHA256.items():
        if file_sha256(repo_root / relative_path) != expected:
            raise FailureGateError(f"frozen component drifted: {relative_path}")
    for relative_path, expected in EXPECTED_INPUT_SHA256.items():
        path = evidence_root / relative_path
        if not path.is_file() or file_sha256(path) != expected:
            raise FailureGateError(f"frozen input drifted: {relative_path}")

    reachability = _load_object(
        evidence_root / "reports/reachability.json", "reachability report"
    )
    reachability_marker = _load_object(
        evidence_root / "markers/reachability.json", "reachability marker"
    )
    pair_marker = _load_object(evidence_root / "markers/pair.json", "pair marker")
    if (
        reachability_marker.get("status") != "passed"
        or reachability.get("passed") is not True
        or reachability.get("request_count") != 1
        or reachability.get("recorded_tokens") != 17
        or pair_marker.get("status") != "failed"
        or pair_marker.get("error_class") != "EvidenceError"
        or (evidence_root / "reports/canary.json").exists()
    ):
        raise FailureGateError("execution terminal state drifted")

    parent_path = evidence_root / f"checkpoints/{PAIR_ID}/parent/events.jsonl"
    parent_events = ExperimentLedger.open(parent_path).read()
    if (
        len(parent_events) != 7
        or parent_events[-1]["event"] != "experiment.completed"
        or parent_events[-1]["payload"] != {"status": "passed"}
    ):
        raise FailureGateError("parent ledger drifted")
    arms = {
        arm: _arm_summary(
            arm,
            ExperimentLedger.open(
                evidence_root / f"pairs/{PAIR_ID}/arms/{arm}.jsonl"
            ).read(),
        )
        for arm in ("baseline", "treatment")
    }

    sessions: dict[str, Any] = {}
    for arm, (relative_path, expected_sha256) in SESSION_INPUTS.items():
        path = evidence_root.parent / relative_path
        if file_sha256(path) != expected_sha256:
            raise FailureGateError(f"{arm} session evidence drifted")
        session = _load_object(path, f"{arm} session")
        if (
            session.get("status") != "verification_failed"
            or len(session.get("commands", [])) != 1
            or session.get("replay_attempts") != []
            or session.get("finalized_at") is not None
        ):
            raise FailureGateError(f"{arm} session terminal state drifted")
        sessions[arm] = {
            "status": session["status"],
            "post_checkpoint_commands": 0,
            "replay_attempts": 0,
            "finalized": False,
        }

    parity, observability = build_runtime_bindings()
    if (
        hasattr(r3_candidate, "RejectionObservationRegistry")
        or hasattr(r3_candidate, "FrozenActionPolicy")
        or hasattr(r3_candidate, "SerialToolCallMiddleware")
        or parity.FrozenActionPolicy is not r3_candidate.R3ActionPolicy
        or observability.RejectionObservationRegistry
        is not make_observability.RejectionObservationRegistry
    ):
        raise FailureGateError("runtime binding root cause drifted")

    return {
        "schema_version": SCHEMA_VERSION,
        "document_type": "forge_opaque_provenance_r3_make_execution_failure_audit",
        "issue_url": ISSUE_URL,
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "evidence_identity_sha256": EXPECTED_EVIDENCE_IDENTITY_SHA256,
        "source_sha256": dict(EXPECTED_INPUT_SHA256),
        "reachability": {
            "status": "passed",
            "actual_model": reachability["actual_model"],
            "request_count": 1,
            "recorded_tokens": 17,
            "duration_ms": reachability["duration_ms"],
            "fallback_used": reachability["fallback_used"],
        },
        "pair": {
            "status": "failed",
            "marker_error_class": "EvidenceError",
            "complete_pair": False,
            "valid_behavioral_pair": False,
            "canary_report_created": False,
            "arms": arms,
            "sessions": sessions,
        },
        "coordinator": _coordinator_summary(
            evidence_root / "checkpoint/coordinator.sqlite"
        ),
        "root_cause": {
            "classification": "r3_runtime_binding_missing_symbols",
            "missing_candidate_symbols": [
                "RejectionObservationRegistry",
                "FrozenActionPolicy",
                "SerialToolCallMiddleware",
            ],
            "exception_before_guarded_finally": True,
            "active_experiment_leaked": True,
            "zero_request_misclassified_as_no_submit": True,
            "cleanup_blocked_by_completed_ledger": True,
        },
        "future_execution_guards": {
            "composed_runtime_bindings": True,
            "zero_request_failure_is_mechanism_invalid": True,
            "terminal_error_class_persisted": True,
            "deactivate_before_cleanup": True,
        },
        "paired_primary_estimand": {
            "status": "not_estimable",
            "reason": "invalid_mechanism_attempt_before_model_request",
        },
        "retry_performed": False,
        "replacement_performed": False,
        "backfill_performed": False,
        "historical_pairs_pooled": False,
        "model_ranking_performed": False,
        "provider_calls_during_audit": 0,
        "credential_read_during_audit": False,
        "docker_executed_during_audit": False,
        "model_tokens_during_audit": 0,
        "source_evidence_modified": False,
    }


def write_sidecar_once(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    except FileExistsError as exc:
        raise FailureGateError("failure audit sidecar already exists") from exc


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
