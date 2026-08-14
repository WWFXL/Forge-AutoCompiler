#!/usr/bin/env python3
"""为 verifier-driven repair pilot 提供版本化反馈适配与证据门禁。"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any

BASELINE_ARM = "baseline-current-verifier-output"
TREATMENT_ARM = "structured-verifier-repair-packet"
ALLOWED_ARMS = frozenset({BASELINE_ARM, TREATMENT_ARM})
PACKET_SCHEMA_VERSION = "forge-verifier-repair-packet-1.0.0"
SIDECAR_SCHEMA_VERSION = "forge-verifier-repair-sidecar-1.0.0"
MAX_DIFF_ENTRIES = 64

REPAIR_GOALS = {
    "candidate_verification_failed": "Stage recognized compiled artifacts in /artifacts and submit the corrected candidate.",
    "build_system_selection_mismatch": "Use the frozen expected build system and rebuild before resubmitting.",
    "build_system_unproven": "Run a successful non-housekeeping build command with the frozen build system before resubmitting.",
    "build_system_mismatch": "Use the frozen expected build system and rebuild before resubmitting.",
    "recipe_execution_failed": "Make the recorded successful build and staging commands replayable from a clean workspace.",
    "artifact_set_mismatch": "Stage exactly the frozen artifact set and remove unexpected outputs before resubmitting.",
    "artifact_type_mismatch": "Stage artifacts with the frozen compiled artifact types before resubmitting.",
    "size_mismatch": "Rebuild and stage artifacts whose sizes reproduce in clean replay.",
    "sha256_mismatch": "Remove nondeterminism so staged artifacts reproduce with identical SHA-256 values.",
    "smoke_mismatch": "Repair runtime behavior so executable smoke output reproduces in clean replay.",
}

_REPLAY_CLASSIFICATION_MAP = {
    "artifact_set_mismatch": "artifact_set_mismatch",
    "type_mismatch": "artifact_type_mismatch",
    "size_mismatch": "size_mismatch",
    "sha256_mismatch": "sha256_mismatch",
    "smoke_mismatch": "smoke_mismatch",
    "recipe_execution_failed": "recipe_execution_failed",
}
_ARTIFACT_MISMATCH_KINDS = frozenset({"type", "size", "sha256", "smoke"})
_SIDECAR_RECORD_FIELDS = {
    "schema_version",
    "sequence",
    "timestamp",
    "event",
    "payload",
    "previous_sha256",
    "record_sha256",
}
_CONTEXT_STARTED_FIELDS = {
    "manifest_sha256",
    "thread_id",
    "physical_attempt_id",
    "order",
    "pair_id",
    "case_id",
    "provider_condition",
    "treatment",
    "repetition",
}
_FEEDBACK_OBSERVED_FIELDS = {
    "treatment",
    "status",
    "actionable",
    "evidence_complete",
    "primary_classification",
    "packet_attached",
    "packet",
    "original_sha256",
    "returned_sha256",
    "submit_attempt_id",
}


class RepairRuntimeError(ValueError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _sha256(value: bytes | str) -> str:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _safe_relative_path(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 512
        or any(character in value for character in ("\0", "\r", "\n", "\\"))
    ):
        raise RepairRuntimeError(f"{label} must be a bounded POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise RepairRuntimeError(f"{label} must be a safe relative path")
    return value


def _safe_id(value: Any, label: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 160
        or any(
            character
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
            for character in value
        )
    ):
        raise RepairRuntimeError(f"{label} must be a safe identifier")
    return value


def _is_safe_id(value: Any) -> bool:
    try:
        _safe_id(value, "identifier")
    except RepairRuntimeError:
        return False
    return True


def _safe_optional_id(value: Any) -> str | None:
    return value if value is not None and _is_safe_id(value) else None


def _safe_sha256(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RepairRuntimeError(f"{label} must be a lowercase SHA-256 digest")
    return value


def repair_packet_schema() -> dict[str, Any]:
    nullable_id = {"type": ["string", "null"], "pattern": "^[A-Za-z0-9_.-]{1,160}$"}
    relative_path = {
        "type": "string",
        "minLength": 1,
        "maxLength": 512,
        "pattern": "^(?!/)(?!.*(?:^|/)\\.\\.(?:/|$))(?!.*\\\\).+$",
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-verifier-repair-packet-v1.schema.json",
        "title": "Forge verifier-driven repair packet",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "failure_domain",
            "primary_classification",
            "failed_checks",
            "build_system_identity",
            "artifact_identity_diff",
            "replay_status",
            "repair_goal",
            "supporting_command_id",
            "submit_attempt_id",
            "replay_attempt_id",
        ],
        "properties": {
            "schema_version": {"const": PACKET_SCHEMA_VERSION},
            "failure_domain": {"const": "submit_replay"},
            "primary_classification": {"enum": sorted(REPAIR_GOALS)},
            "failed_checks": {
                "type": "array",
                "maxItems": MAX_DIFF_ENTRIES,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "exit_code"],
                    "properties": {
                        "name": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 160,
                            "pattern": "^[A-Za-z0-9_.-]+$",
                        },
                        "exit_code": {"type": ["integer", "null"]},
                    },
                },
            },
            "build_system_identity": {
                "type": ["object", "null"],
                "additionalProperties": False,
                "required": ["expected", "observed", "selected", "matches"],
                "properties": {
                    "expected": {
                        "type": ["string", "null"],
                        "enum": ["cmake", "make", "autotools", None],
                    },
                    "observed": {
                        "type": ["string", "null"],
                        "enum": ["cmake", "make", "autotools", None],
                    },
                    "selected": {
                        "type": ["string", "null"],
                        "enum": ["cmake", "make", "autotools", None],
                    },
                    "matches": {"type": ["boolean", "null"]},
                },
            },
            "artifact_identity_diff": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "expected_only",
                    "observed_only",
                    "mismatches",
                    "truncated",
                ],
                "properties": {
                    "expected_only": {
                        "type": "array",
                        "maxItems": MAX_DIFF_ENTRIES,
                        "items": relative_path,
                    },
                    "observed_only": {
                        "type": "array",
                        "maxItems": MAX_DIFF_ENTRIES,
                        "items": relative_path,
                    },
                    "mismatches": {
                        "type": "array",
                        "maxItems": MAX_DIFF_ENTRIES,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["path", "kinds"],
                            "properties": {
                                "path": relative_path,
                                "kinds": {
                                    "type": "array",
                                    "minItems": 1,
                                    "uniqueItems": True,
                                    "items": {"enum": sorted(_ARTIFACT_MISMATCH_KINDS)},
                                },
                            },
                        },
                    },
                    "truncated": {"type": "boolean"},
                },
            },
            "replay_status": {
                "type": "string",
                "minLength": 1,
                "maxLength": 64,
                "pattern": "^[a-z0-9_-]+$",
            },
            "repair_goal": {"enum": sorted(REPAIR_GOALS.values())},
            "supporting_command_id": nullable_id,
            "submit_attempt_id": nullable_id,
            "replay_attempt_id": nullable_id,
        },
    }


def validate_repair_packet(packet: Any) -> dict[str, Any]:
    if not isinstance(packet, dict) or set(packet) != set(
        repair_packet_schema()["required"]
    ):
        raise RepairRuntimeError("repair packet fields do not match the frozen schema")
    classification = packet.get("primary_classification")
    if (
        classification not in REPAIR_GOALS
        or packet.get("repair_goal") != REPAIR_GOALS[classification]
    ):
        raise RepairRuntimeError("repair packet classification and goal do not match")
    if (
        packet.get("schema_version") != PACKET_SCHEMA_VERSION
        or packet.get("failure_domain") != "submit_replay"
    ):
        raise RepairRuntimeError("repair packet identity is invalid")
    checks = packet.get("failed_checks")
    if not isinstance(checks, list) or len(checks) > MAX_DIFF_ENTRIES:
        raise RepairRuntimeError("repair packet failed_checks are invalid")
    for check in checks:
        if not isinstance(check, dict) or set(check) != {"name", "exit_code"}:
            raise RepairRuntimeError("repair packet check fields are invalid")
        _safe_id(check["name"], "failed check name")
        if check["exit_code"] is not None and type(check["exit_code"]) is not int:
            raise RepairRuntimeError("failed check exit_code is invalid")
    identity = packet.get("build_system_identity")
    if identity is not None:
        if not isinstance(identity, dict) or set(identity) != {
            "expected",
            "observed",
            "selected",
            "matches",
        }:
            raise RepairRuntimeError("build-system identity fields are invalid")
        for name in ("expected", "observed", "selected"):
            if identity[name] not in {None, "cmake", "make", "autotools"}:
                raise RepairRuntimeError("build-system identity value is invalid")
        if identity["matches"] is not None and not isinstance(
            identity["matches"], bool
        ):
            raise RepairRuntimeError("build-system match flag is invalid")
    diff = packet.get("artifact_identity_diff")
    if not isinstance(diff, dict) or set(diff) != {
        "expected_only",
        "observed_only",
        "mismatches",
        "truncated",
    }:
        raise RepairRuntimeError("artifact identity diff fields are invalid")
    for name in ("expected_only", "observed_only"):
        values = diff[name]
        if not isinstance(values, list) or len(values) > MAX_DIFF_ENTRIES:
            raise RepairRuntimeError("artifact identity path set is invalid")
        for value in values:
            _safe_relative_path(value, f"artifact_identity_diff.{name}")
    mismatches = diff["mismatches"]
    if not isinstance(mismatches, list) or len(mismatches) > MAX_DIFF_ENTRIES:
        raise RepairRuntimeError("artifact mismatch list is invalid")
    for mismatch in mismatches:
        if not isinstance(mismatch, dict) or set(mismatch) != {"path", "kinds"}:
            raise RepairRuntimeError("artifact mismatch fields are invalid")
        _safe_relative_path(mismatch["path"], "artifact mismatch path")
        kinds = mismatch["kinds"]
        if (
            not isinstance(kinds, list)
            or not kinds
            or len(kinds) != len(set(kinds))
            or any(kind not in _ARTIFACT_MISMATCH_KINDS for kind in kinds)
        ):
            raise RepairRuntimeError("artifact mismatch kinds are invalid")
    if not isinstance(diff["truncated"], bool):
        raise RepairRuntimeError("artifact diff truncated flag is invalid")
    replay_status = packet.get("replay_status")
    _safe_id(replay_status, "replay_status")
    for field in ("supporting_command_id", "submit_attempt_id", "replay_attempt_id"):
        _safe_id(packet.get(field), field, optional=True)
    return packet


def _latest_event(
    events: Sequence[Mapping[str, Any]],
    name: str,
    *,
    submit_attempt_id: str | None = None,
) -> Mapping[str, Any] | None:
    for event in reversed(events):
        if event.get("event") != name:
            continue
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            continue
        if (
            submit_attempt_id is None
            or payload.get("submit_attempt_id") == submit_attempt_id
        ):
            return payload
    return None


def _build_system_identity(
    events: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    payload = _latest_event(events, "build.system_checked")
    if payload is None:
        return None
    return {
        "expected": payload.get("expected_build_system")
        if payload.get("expected_build_system") in {"cmake", "make", "autotools"}
        else None,
        "observed": payload.get("observed_build_system")
        if payload.get("observed_build_system") in {"cmake", "make", "autotools"}
        else None,
        "selected": payload.get("selected_build_system")
        if payload.get("selected_build_system") in {"cmake", "make", "autotools"}
        else None,
        "matches": payload.get("matches")
        if isinstance(payload.get("matches"), bool)
        else None,
    }


def _artifact_diff(
    submit: Mapping[str, Any],
    replay: Mapping[str, Any] | None,
    expected_artifacts: tuple[tuple[str, str], ...],
) -> dict[str, Any]:
    expected = {path: artifact_type for path, artifact_type in expected_artifacts}
    observed = {
        artifact["path"]: artifact.get("artifact_type")
        for artifact in submit.get("artifacts", [])
        if isinstance(artifact, Mapping) and isinstance(artifact.get("path"), str)
    }
    expected_only = sorted(set(expected) - set(observed))
    observed_only = sorted(set(observed) - set(expected))
    mismatches: dict[str, set[str]] = {}
    for path in sorted(set(expected) & set(observed)):
        if expected[path] != observed[path]:
            mismatches.setdefault(path, set()).add("type")
    if replay is not None:
        for artifact in replay.get("artifacts", []):
            if not isinstance(artifact, Mapping) or not isinstance(
                artifact.get("path"), str
            ):
                continue
            kinds = {
                kind
                for kind in artifact.get("mismatches", [])
                if kind in _ARTIFACT_MISMATCH_KINDS
            }
            if kinds:
                mismatches.setdefault(artifact["path"], set()).update(kinds)
    raw_entries = [(path, sorted(kinds)) for path, kinds in sorted(mismatches.items())]
    total_entries = len(expected_only) + len(observed_only) + len(raw_entries)
    return {
        "expected_only": expected_only[:MAX_DIFF_ENTRIES],
        "observed_only": observed_only[:MAX_DIFF_ENTRIES],
        "mismatches": [
            {"path": path, "kinds": kinds}
            for path, kinds in raw_entries[:MAX_DIFF_ENTRIES]
        ],
        "truncated": total_entries > MAX_DIFF_ENTRIES,
    }


def _classification(
    submit: Mapping[str, Any],
    replay: Mapping[str, Any] | None,
    identity: Mapping[str, Any] | None,
) -> str | None:
    if replay is not None:
        normalized = _REPLAY_CLASSIFICATION_MAP.get(
            replay.get("primary_failure_classification")
        )
        if normalized is not None:
            return normalized
    if submit.get("candidate_status") != "failed":
        return None
    failed_names = {
        check.get("name")
        for check in submit.get("checks", [])
        if isinstance(check, Mapping) and check.get("passed") is False
    }
    if "benchmark_constraints" in failed_names:
        if identity is not None and identity.get("matches") is False:
            return "build_system_selection_mismatch"
        return "build_system_unproven"
    return "candidate_verification_failed"


def build_repair_packet(
    result_payload: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
    *,
    expected_artifacts: tuple[tuple[str, str], ...],
) -> dict[str, Any] | None:
    if result_payload.get("status") != "failed":
        return None
    submit_attempt_id = result_payload.get("submit_attempt_id")
    if not _is_safe_id(submit_attempt_id):
        return None
    submit = _latest_event(
        events, "submit.completed", submit_attempt_id=submit_attempt_id
    )
    if submit is None:
        return None
    replay = _latest_event(
        events, "replay.completed", submit_attempt_id=submit_attempt_id
    )
    identity = _build_system_identity(events)
    classification = _classification(submit, replay, identity)
    if classification not in REPAIR_GOALS:
        return None
    checks = [
        {
            "name": check["name"],
            "exit_code": check.get("exit_code")
            if type(check.get("exit_code")) is int
            else None,
        }
        for check in submit.get("checks", [])
        if isinstance(check, Mapping)
        and check.get("passed") is False
        and _is_safe_id(check.get("name"))
    ][:MAX_DIFF_ENTRIES]
    replay_snapshot = (
        submit.get("replay") if isinstance(submit.get("replay"), Mapping) else None
    )
    packet = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "failure_domain": "submit_replay",
        "primary_classification": classification,
        "failed_checks": checks,
        "build_system_identity": identity,
        "artifact_identity_diff": _artifact_diff(submit, replay, expected_artifacts),
        "replay_status": _safe_optional_id(
            result_payload.get("replay_status") or (replay_snapshot or {}).get("status")
        )
        or "not_run",
        "repair_goal": REPAIR_GOALS[classification],
        "supporting_command_id": _safe_optional_id(
            result_payload.get("supporting_command_id")
        ),
        "submit_attempt_id": submit_attempt_id,
        "replay_attempt_id": _safe_optional_id(
            result_payload.get("replay_attempt_id")
            or (replay_snapshot or {}).get("replay_attempt_id")
        ),
    }
    return validate_repair_packet(packet)


def _validate_sidecar_payload(event: str, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RepairRuntimeError("repair sidecar payload must be an object")
    if event == "repair.context_started":
        if set(payload) != _CONTEXT_STARTED_FIELDS:
            raise RepairRuntimeError(
                "repair context fields do not match the frozen sidecar contract"
            )
        _safe_sha256(payload["manifest_sha256"], "manifest_sha256")
        for field in (
            "thread_id",
            "physical_attempt_id",
            "pair_id",
            "case_id",
            "provider_condition",
        ):
            _safe_id(payload[field], field)
        if payload["treatment"] not in ALLOWED_ARMS:
            raise RepairRuntimeError("repair context treatment is invalid")
        for field in ("order", "repetition"):
            if type(payload[field]) is not int or payload[field] < 1:
                raise RepairRuntimeError(f"repair context {field} is invalid")
        return payload
    if event == "repair.feedback_observed":
        if set(payload) != _FEEDBACK_OBSERVED_FIELDS:
            raise RepairRuntimeError(
                "repair feedback fields do not match the frozen sidecar contract"
            )
        if payload["treatment"] not in ALLOWED_ARMS:
            raise RepairRuntimeError("repair feedback treatment is invalid")
        _safe_id(payload["status"], "feedback status")
        for field in ("actionable", "evidence_complete", "packet_attached"):
            if type(payload[field]) is not bool:
                raise RepairRuntimeError(f"repair feedback {field} is invalid")
        classification = payload["primary_classification"]
        if classification is not None and classification not in REPAIR_GOALS:
            raise RepairRuntimeError("repair feedback classification is invalid")
        if payload["actionable"] != (classification is not None):
            raise RepairRuntimeError("repair feedback actionable flag is inconsistent")
        packet = payload["packet"]
        if payload["packet_attached"] != (packet is not None):
            raise RepairRuntimeError("repair feedback packet flag is inconsistent")
        if packet is not None:
            validate_repair_packet(packet)
            if packet["primary_classification"] != classification:
                raise RepairRuntimeError(
                    "repair feedback packet classification drifted"
                )
        _safe_sha256(payload["original_sha256"], "original_sha256")
        _safe_sha256(payload["returned_sha256"], "returned_sha256")
        _safe_id(payload["submit_attempt_id"], "submit_attempt_id", optional=True)
        return payload
    if event == "repair.context_completed":
        if set(payload) != {"status"}:
            raise RepairRuntimeError(
                "repair completion fields do not match the frozen sidecar contract"
            )
        _safe_id(payload["status"], "completion status")
        return payload
    raise RepairRuntimeError("repair sidecar event is unsupported")


class RepairEvidenceLedger:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()

    @classmethod
    def create(cls, path: Path, context: Mapping[str, Any]) -> RepairEvidenceLedger:
        if path.exists():
            raise RepairRuntimeError("repair sidecar already exists")
        path.parent.mkdir(parents=True, exist_ok=True)
        ledger = cls(path)
        ledger.append("repair.context_started", dict(context))
        return ledger

    def read(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            raise RepairRuntimeError("repair sidecar does not exist")
        records = [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        previous = None
        for index, record in enumerate(records, start=1):
            if not isinstance(record, dict) or set(record) != _SIDECAR_RECORD_FIELDS:
                raise RepairRuntimeError("repair sidecar record fields are invalid")
            if (
                record.get("schema_version") != SIDECAR_SCHEMA_VERSION
                or record.get("sequence") != index
                or record.get("previous_sha256") != previous
            ):
                raise RepairRuntimeError("repair sidecar chain metadata is invalid")
            try:
                timestamp = datetime.fromisoformat(record["timestamp"])
            except (TypeError, ValueError) as exc:
                raise RepairRuntimeError("repair sidecar timestamp is invalid") from exc
            if timestamp.tzinfo is None:
                raise RepairRuntimeError(
                    "repair sidecar timestamp must include a timezone"
                )
            _validate_sidecar_payload(record.get("event"), record.get("payload"))
            expected_hash = _sha256(
                _canonical_bytes(
                    {
                        key: value
                        for key, value in record.items()
                        if key != "record_sha256"
                    }
                )
            )
            if record.get("record_sha256") != expected_hash:
                raise RepairRuntimeError("repair sidecar hash chain is invalid")
            previous = record["record_sha256"]
        return records

    def append(self, event: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        validated_payload = _validate_sidecar_payload(event, dict(payload))
        with self._lock:
            records = (
                self.read() if self.path.exists() and self.path.stat().st_size else []
            )
            record = {
                "schema_version": SIDECAR_SCHEMA_VERSION,
                "sequence": len(records) + 1,
                "timestamp": datetime.now(UTC).isoformat(),
                "event": event,
                "payload": validated_payload,
                "previous_sha256": records[-1]["record_sha256"] if records else None,
            }
            record["record_sha256"] = _sha256(_canonical_bytes(record))
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(
                    json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                )
                stream.flush()
                os.fsync(stream.fileno())
            return record


@dataclass(frozen=True)
class RepairFeedbackContext:
    thread_id: str
    pair_id: str
    case_id: str
    provider_condition: str
    treatment: str
    repetition: int
    expected_build_system: str
    expected_artifacts: tuple[tuple[str, str], ...]
    event_reader: Callable[[], Sequence[Mapping[str, Any]]]
    evidence: RepairEvidenceLedger

    def __post_init__(self) -> None:
        _safe_id(self.thread_id, "thread_id")
        _safe_id(self.pair_id, "pair_id")
        _safe_id(self.case_id, "case_id")
        _safe_id(self.provider_condition, "provider_condition")
        if (
            self.treatment not in ALLOWED_ARMS
            or self.repetition < 1
            or self.expected_build_system not in {"cmake", "make", "autotools"}
        ):
            raise RepairRuntimeError("repair feedback context identity is invalid")
        for path, artifact_type in self.expected_artifacts:
            _safe_relative_path(path, "expected artifact")
            if artifact_type not in {
                "executable",
                "shared_library",
                "static_library",
                "object",
            }:
                raise RepairRuntimeError("expected artifact type is invalid")


_CONTEXTS: dict[str, RepairFeedbackContext] = {}
_CONTEXT_LOCK = threading.RLock()


def _adapt_submit_result(context: RepairFeedbackContext, result: str) -> str:
    original_digest = _sha256(result if isinstance(result, str) else repr(result))
    try:
        payload = json.loads(result)
    except (TypeError, json.JSONDecodeError):
        context.evidence.append(
            "repair.feedback_observed",
            {
                "treatment": context.treatment,
                "status": "invalid_response",
                "actionable": False,
                "evidence_complete": False,
                "primary_classification": None,
                "packet_attached": False,
                "packet": None,
                "original_sha256": original_digest,
                "returned_sha256": original_digest,
                "submit_attempt_id": None,
            },
        )
        return result
    if not isinstance(payload, dict):
        context.evidence.append(
            "repair.feedback_observed",
            {
                "treatment": context.treatment,
                "status": "invalid_response",
                "actionable": False,
                "evidence_complete": False,
                "primary_classification": None,
                "packet_attached": False,
                "packet": None,
                "original_sha256": original_digest,
                "returned_sha256": original_digest,
                "submit_attempt_id": None,
            },
        )
        return result
    events = context.event_reader()
    status = payload.get("status") if _is_safe_id(payload.get("status")) else "unknown"
    submit_attempt_id = _safe_optional_id(payload.get("submit_attempt_id"))
    failed_submit_evidence = (
        submit_attempt_id is not None
        and _latest_event(
            events, "submit.completed", submit_attempt_id=submit_attempt_id
        )
        is not None
    )
    evidence_complete = status != "failed" or failed_submit_evidence
    packet = (
        build_repair_packet(
            payload, events, expected_artifacts=context.expected_artifacts
        )
        if evidence_complete
        else None
    )
    actionable = packet is not None
    returned = result
    attached_packet = None
    if context.treatment == TREATMENT_ARM and packet is not None:
        payload["repair_packet"] = packet
        attached_packet = packet
        returned = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    context.evidence.append(
        "repair.feedback_observed",
        {
            "treatment": context.treatment,
            "status": status,
            "actionable": actionable,
            "evidence_complete": evidence_complete,
            "primary_classification": packet.get("primary_classification")
            if packet
            else None,
            "packet_attached": attached_packet is not None,
            "packet": attached_packet,
            "original_sha256": original_digest,
            "returned_sha256": _sha256(returned),
            "submit_attempt_id": submit_attempt_id,
        },
    )
    return returned


@contextlib.contextmanager
def submit_feedback_scope(
    context: RepairFeedbackContext, bound_compile_tools: ModuleType
) -> Iterator[None]:
    with _CONTEXT_LOCK:
        if _CONTEXTS or context.thread_id in _CONTEXTS:
            raise RepairRuntimeError("repair feedback scopes must execute serially")
        original = bound_compile_tools._submit_with_post_build_phase
        _CONTEXTS[context.thread_id] = context

        def wrapped(session, *, supporting_command_id=None):
            result = original(session, supporting_command_id=supporting_command_id)
            active = _CONTEXTS.get(session.thread_id)
            return (
                _adapt_submit_result(active, result) if active is not None else result
            )

        bound_compile_tools._submit_with_post_build_phase = wrapped
    try:
        yield
    finally:
        with _CONTEXT_LOCK:
            bound_compile_tools._submit_with_post_build_phase = original
            _CONTEXTS.pop(context.thread_id, None)


def evaluate_treatment_fidelity(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not records or records[0].get("event") != "repair.context_started":
        return {
            "status": "failed",
            "evidence_complete": False,
            "exposures": 0,
            "actionable_exposures": 0,
            "failures": ["context_missing"],
        }
    context_payload = records[0].get("payload")
    treatment = (
        context_payload.get("treatment")
        if isinstance(context_payload, Mapping)
        else None
    )
    if treatment not in ALLOWED_ARMS:
        return {
            "status": "failed",
            "evidence_complete": False,
            "exposures": 0,
            "actionable_exposures": 0,
            "failures": ["arm_invalid"],
        }
    observed = [
        record.get("payload")
        for record in records
        if record.get("event") == "repair.feedback_observed"
        and isinstance(record.get("payload"), Mapping)
    ]
    failures: list[str] = []
    actionable_count = 0
    for payload in observed:
        if payload.get("treatment") != treatment:
            failures.append("arm_mismatch")
            continue
        if payload.get("evidence_complete") is not True:
            failures.append("evidence_missing")
        actionable = payload.get("actionable") is True
        attached = payload.get("packet_attached") is True
        actionable_count += int(actionable)
        if treatment == BASELINE_ARM and attached:
            failures.append("baseline_packet_attached")
        if treatment == BASELINE_ARM and payload.get("original_sha256") != payload.get(
            "returned_sha256"
        ):
            failures.append("baseline_response_modified")
        if treatment == TREATMENT_ARM and actionable != attached:
            failures.append("treatment_exposure_mismatch")
        if attached:
            try:
                validate_repair_packet(payload.get("packet"))
            except RepairRuntimeError:
                failures.append("packet_invalid")
    status = (
        "failed" if failures else ("not_exposed" if actionable_count == 0 else "passed")
    )
    return {
        "status": status,
        "evidence_complete": all(
            payload.get("evidence_complete") is True for payload in observed
        ),
        "exposures": len(observed),
        "actionable_exposures": actionable_count,
        "failures": sorted(set(failures)),
    }
