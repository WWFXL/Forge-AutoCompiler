from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from deerflow.compile.schemas import utc_now_iso

LEDGER_VERSION = "1.0.0"
LEDGER_CANONICALIZATION = "json-sort-keys-compact-utf8"

_EVENT_TYPE_RE = re.compile(r"^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_]*)+$")
_EVIDENCE_ID_RE = re.compile(r"^[a-z][a-z0-9_]*_[0-9a-f]{32}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BOUNDED_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_WINDOWS_PATH_RE = re.compile(r"(?i)(?:^|[^A-Za-z0-9_])(?:[A-Z]:[\\/]|\\\\)")
_WSL_PATH_RE = re.compile(r"(?i)(?:^|[^A-Za-z0-9_])/mnt/[a-z](?:/|$)")
_HOME_PATH_RE = re.compile(r"(?:^|[^A-Za-z0-9_])/(?:home|Users)/[^/\s]+/")
_SECRET_VALUE_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._-]{12,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
_FORBIDDEN_KEYS = {
    "api_key",
    "authorization",
    "command",
    "command_text",
    "content",
    "credential_value",
    "error_message",
    "log_content",
    "prompt",
    "request_body",
    "response",
    "response_body",
    "secret",
    "secret_hash",
    "stderr",
    "stdout",
}
_ALLOWED_MODEL_ROLES = {"lead", "compiler", "system"}
_ALLOWED_BUILD_SYSTEMS = {"cmake", "make", "autotools"}
_ALLOWED_TOOL_EXECUTION_MODES = {"sync", "async"}
_ALLOWED_COMMAND_ROLES = {
    "clone",
    "inspect",
    "dependency_setup",
    "configure",
    "build",
    "artifact_stage",
    "smoke",
    "replay_delay",
    "other",
}
_ALLOWED_SUBAGENT_TERMINAL_STATUSES = {
    "completed",
    "failed",
    "cancelled",
    "timed_out",
}
_ALLOWED_SUBAGENT_FAILURE_CLASSIFICATIONS = {
    "cancelled",
    "parent_cancelled",
    "polling_timeout",
    "recursion_limit",
    "subagent_failed",
    "subagent_timeout",
    "tracking_lost",
}


class EvidenceError(ValueError):
    pass


def new_evidence_id(prefix: str) -> str:
    normalized = prefix.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", normalized):
        raise EvidenceError(f"Invalid evidence ID prefix: {prefix!r}")
    return f"{normalized}_{uuid.uuid4().hex}"


def canonical_json_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"Evidence is not canonical JSON: {exc}") from exc
    return encoded.encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _validate_id(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _EVIDENCE_ID_RE.fullmatch(value):
        raise EvidenceError(f"{path} must be a stable evidence ID")
    return value


def _validate_sha256(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise EvidenceError(f"{path} must be a lowercase SHA-256 digest")
    return value


def _validate_safe_value(value: Any, path: str = "payload") -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EvidenceError(f"{path} must be finite")
        return
    if isinstance(value, str):
        if any(character in value for character in ("\0", "\r", "\n")):
            raise EvidenceError(f"{path} contains a control character")
        if ".compile-sessions" in value or _WINDOWS_PATH_RE.search(value) or _WSL_PATH_RE.search(value) or _HOME_PATH_RE.search(value):
            raise EvidenceError(f"{path} contains a host path")
        if any(pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS):
            raise EvidenceError(f"{path} contains a credential-like value")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_safe_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise EvidenceError(f"{path} contains an invalid key")
            if key.lower() in _FORBIDDEN_KEYS:
                raise EvidenceError(f"{path}.{key} is forbidden in experiment evidence")
            _validate_safe_value(item, f"{path}.{key}")
        return
    raise EvidenceError(f"{path} contains unsupported value type {type(value).__name__}")


def _validate_agent_event_payload(event: str, payload: dict[str, Any], path: str = "payload") -> None:
    if event == "build.identity_snapshot":
        required = {
            "session_id",
            "build_system_capabilities",
            "selected_build_system",
            "executed_build_system",
        }
        if set(payload) != required:
            raise EvidenceError(f"{path} has an invalid build.identity_snapshot schema")
        session_id = payload["session_id"]
        if session_id is not None and (not isinstance(session_id, str) or not re.fullmatch(r"[0-9a-f]{12}", session_id)):
            raise EvidenceError(f"{path}.session_id must be null or a compile-session ID")
        capabilities = payload["build_system_capabilities"]
        if not isinstance(capabilities, list) or len(capabilities) > len(_ALLOWED_BUILD_SYSTEMS) or len(set(capabilities)) != len(capabilities) or any(value not in _ALLOWED_BUILD_SYSTEMS for value in capabilities):
            raise EvidenceError(f"{path}.build_system_capabilities must be a unique supported build-system list")
        selected = payload["selected_build_system"]
        executed = payload["executed_build_system"]
        for key, value in (("selected_build_system", selected), ("executed_build_system", executed)):
            if value is not None and value not in _ALLOWED_BUILD_SYSTEMS:
                raise EvidenceError(f"{path}.{key} must be null or a supported build system")
        if selected is not None and selected not in capabilities:
            raise EvidenceError(f"{path}.selected_build_system must belong to build_system_capabilities")
        if session_id is None and (capabilities or selected is not None or executed is not None):
            raise EvidenceError(f"{path} cannot claim build identity without a session")
        return

    if event == "agent.subagent_terminated":
        required = {
            "task_id",
            "role",
            "status",
            "classification",
            "worker_stopped",
        }
        if set(payload) != required:
            raise EvidenceError(f"{path} has an invalid agent.subagent_terminated schema")
        if not isinstance(payload["task_id"], str) or not _BOUNDED_IDENTIFIER_RE.fullmatch(payload["task_id"]):
            raise EvidenceError(f"{path}.task_id must be a bounded identifier")
        if payload["role"] != "compiler":
            raise EvidenceError(f"{path}.role must be compiler")
        status = payload["status"]
        classification = payload["classification"]
        if status not in _ALLOWED_SUBAGENT_TERMINAL_STATUSES:
            raise EvidenceError(f"{path}.status is invalid")
        if status == "completed":
            if classification is not None:
                raise EvidenceError(f"{path}.classification must be null for completed tasks")
        elif classification not in _ALLOWED_SUBAGENT_FAILURE_CLASSIFICATIONS:
            raise EvidenceError(f"{path}.classification is invalid")
        if type(payload["worker_stopped"]) is not bool:
            raise EvidenceError(f"{path}.worker_stopped must be boolean")
        return

    if event == "agent.tool_failed":
        required = {
            "failure_id",
            "role",
            "tool_name",
            "tool_call_id",
            "exception_class",
            "execution_mode",
            "terminal",
        }
        if set(payload) != required:
            raise EvidenceError(f"{path} has an invalid agent.tool_failed schema")
        _validate_id(payload["failure_id"], f"{path}.failure_id")
        if payload["role"] not in _ALLOWED_MODEL_ROLES:
            raise EvidenceError(f"{path}.role is invalid")
        for key in ("tool_name", "tool_call_id", "exception_class"):
            if not isinstance(payload[key], str) or not _BOUNDED_IDENTIFIER_RE.fullmatch(payload[key]):
                raise EvidenceError(f"{path}.{key} must be a bounded identifier")
        if payload["execution_mode"] not in _ALLOWED_TOOL_EXECUTION_MODES:
            raise EvidenceError(f"{path}.execution_mode is invalid")
        if payload["terminal"] is not False:
            raise EvidenceError(f"{path}.terminal must be false for a recoverable tool error")
        return

    if event == "agent.clarification_auto_answered":
        required = {
            "repair_id",
            "role",
            "reason",
            "auto_answer_count",
            "max_auto_answers",
            "terminal",
        }
        if set(payload) != required:
            raise EvidenceError(f"{path} has an invalid agent.clarification_auto_answered schema")
        _validate_id(payload["repair_id"], f"{path}.repair_id")
        if payload["role"] != "lead":
            raise EvidenceError(f"{path}.role must be lead")
        if payload["reason"] != "non_interactive_frozen_policy":
            raise EvidenceError(f"{path}.reason is invalid")
        if payload["auto_answer_count"] != 1 or payload["max_auto_answers"] != 1:
            raise EvidenceError(f"{path} must describe the single allowed auto-answer")
        if payload["terminal"] is not False:
            raise EvidenceError(f"{path}.terminal must be false")
        return

    if event == "agent.no_compile_progress":
        required = {
            "failure_id",
            "classification",
            "completed_model_request_count",
            "tool_call_count",
            "compile_tool_call_count",
            "stream_completed",
            "terminal",
        }
        if set(payload) != required:
            raise EvidenceError(f"{path} has an invalid agent.no_compile_progress schema")
        _validate_id(payload["failure_id"], f"{path}.failure_id")
        if payload["classification"] != "no_compile_tool_call":
            raise EvidenceError(f"{path}.classification is invalid")
        for key in (
            "completed_model_request_count",
            "tool_call_count",
            "compile_tool_call_count",
        ):
            if type(payload[key]) is not int or payload[key] < 0:
                raise EvidenceError(f"{path}.{key} must be a non-negative integer")
        if payload["completed_model_request_count"] < 1:
            raise EvidenceError(f"{path}.completed_model_request_count must be positive")
        if payload["compile_tool_call_count"] != 0:
            raise EvidenceError(f"{path}.compile_tool_call_count must be zero")
        if payload["stream_completed"] is not True or payload["terminal"] is not True:
            raise EvidenceError(f"{path} must describe a completed terminal stream")


def _bounded_identifier(value: Any, fallback: str) -> str:
    candidate = str(value or "")
    if _BOUNDED_IDENTIFIER_RE.fullmatch(candidate):
        return candidate
    return fallback


def _validate_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise EvidenceError("The experiment endpoint must be a credential-free HTTPS URL")
    return value.rstrip("/")


@dataclass(frozen=True)
class ExperimentPolicy:
    benchmark_id: str
    manifest_sha256: str
    case_id: str
    condition: str
    repetition: int
    expected_repo_url: str
    expected_commit_sha: str
    expected_build_system: str
    compile_image: str
    image_id: str
    model_name: str
    endpoint: str
    credential_env: str
    request_timeout_seconds: int
    model_max_retries: int
    compiler_max_turns: int
    subagent_timeout_seconds: int
    memory_enabled: bool
    skills_enabled: bool
    required_system_packages: tuple[str, ...]
    cmake_arguments: tuple[str, ...]
    configure_arguments: tuple[str, ...]
    environment: tuple[tuple[str, str | None], ...]
    minimum_replay_delay_seconds: int

    def __post_init__(self) -> None:
        _validate_sha256(self.manifest_sha256, "manifest_sha256")
        if self.repetition < 1:
            raise EvidenceError("repetition must be positive")
        if self.request_timeout_seconds < 1 or self.model_max_retries < 0:
            raise EvidenceError("invalid model timeout/retry policy")
        if self.memory_enabled or self.skills_enabled:
            raise EvidenceError("The C/C++ baseline requires Memory and Skills to be disabled")
        if self.minimum_replay_delay_seconds < 0:
            raise EvidenceError("minimum replay delay cannot be negative")
        if self.expected_build_system not in _ALLOWED_BUILD_SYSTEMS:
            raise EvidenceError("expected_build_system must be cmake, make, or autotools")
        if self.expected_build_system != "cmake" and self.cmake_arguments:
            raise EvidenceError("cmake_arguments require expected_build_system=cmake")
        if self.expected_build_system != "autotools" and self.configure_arguments:
            raise EvidenceError("configure_arguments require expected_build_system=autotools")
        _validate_endpoint(self.endpoint)
        _validate_safe_value(self.to_payload())

    @property
    def process_environment(self) -> dict[str, str | None]:
        return dict(self.environment)

    @property
    def selected_build_system(self) -> str:
        return self.expected_build_system

    def to_payload(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "manifest_sha256": self.manifest_sha256,
            "case_id": self.case_id,
            "condition": self.condition,
            "repetition": self.repetition,
            "expected_repo_url": self.expected_repo_url,
            "expected_commit_sha": self.expected_commit_sha,
            "expected_build_system": self.expected_build_system,
            "compile_image": self.compile_image,
            "image_id": self.image_id,
            "model_name": self.model_name,
            "endpoint": self.endpoint,
            "credential_env": self.credential_env,
            "request_timeout_seconds": self.request_timeout_seconds,
            "model_max_retries": self.model_max_retries,
            "compiler_max_turns": self.compiler_max_turns,
            "subagent_timeout_seconds": self.subagent_timeout_seconds,
            "memory_enabled": self.memory_enabled,
            "skills_enabled": self.skills_enabled,
            "required_system_packages": list(self.required_system_packages),
            "cmake_arguments": list(self.cmake_arguments),
            "configure_arguments": list(self.configure_arguments),
            "environment": dict(self.environment),
            "minimum_replay_delay_seconds": self.minimum_replay_delay_seconds,
        }


@dataclass(frozen=True)
class ActiveExperiment:
    thread_id: str
    experiment_id: str
    physical_attempt_id: str
    ledger: ExperimentLedger
    policy: ExperimentPolicy


_PATH_LOCKS: dict[Path, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.Lock()
_ACTIVE_EXPERIMENTS: dict[str, ActiveExperiment] = {}
_ACTIVE_EXPERIMENTS_GUARD = threading.RLock()


def _path_lock(path: Path) -> threading.RLock:
    resolved = path.resolve()
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(resolved, threading.RLock())


@contextmanager
def _exclusive_sibling_lock(path: Path) -> Iterator[None]:
    lock_path = path.with_name(f".{path.name}.lock")
    descriptor: int | None = None
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    except FileExistsError as exc:
        raise EvidenceError(f"Experiment ledger lock already exists: {lock_path.name}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


class ExperimentLedger:
    def __init__(self, path: Path, experiment_id: str, physical_attempt_id: str):
        self.path = path
        self.experiment_id = _validate_id(experiment_id, "experiment_id")
        self.physical_attempt_id = _validate_id(physical_attempt_id, "physical_attempt_id")

    @classmethod
    def create(
        cls,
        path: Path,
        *,
        experiment_id: str,
        physical_attempt_id: str,
        context: dict[str, Any],
    ) -> ExperimentLedger:
        ledger = cls(path, experiment_id, physical_attempt_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with _path_lock(path):
            if path.exists():
                raise EvidenceError("A physical attempt ledger already exists and cannot be overwritten")
            ledger.append("experiment.started", context)
        return ledger

    @classmethod
    def open(cls, path: Path) -> ExperimentLedger:
        events = cls.verify_path(path)
        if not events:
            raise EvidenceError("Experiment ledger is empty")
        first = events[0]
        return cls(path, first["experiment_id"], first["physical_attempt_id"])

    @staticmethod
    def verify_path(path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            raise EvidenceError("Experiment ledger does not exist")
        events: list[dict[str, Any]] = []
        previous_digest: str | None = None
        for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw_line.strip():
                raise EvidenceError(f"Ledger line {line_number} is blank")
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise EvidenceError(f"Ledger line {line_number} is not valid JSON") from exc
            if not isinstance(event, dict):
                raise EvidenceError(f"Ledger line {line_number} is not an object")
            required = {
                "ledger_version",
                "canonicalization",
                "sequence",
                "occurred_at",
                "event",
                "experiment_id",
                "physical_attempt_id",
                "previous_event_sha256",
                "payload",
                "event_sha256",
            }
            if set(event) != required:
                raise EvidenceError(f"Ledger line {line_number} has unexpected fields")
            if event["ledger_version"] != LEDGER_VERSION or event["canonicalization"] != LEDGER_CANONICALIZATION:
                raise EvidenceError(f"Ledger line {line_number} has an unsupported protocol identity")
            if event["sequence"] != line_number:
                raise EvidenceError(f"Ledger line {line_number} has a non-contiguous sequence")
            if event["previous_event_sha256"] != previous_digest:
                raise EvidenceError(f"Ledger line {line_number} breaks the hash chain")
            _validate_id(event["experiment_id"], f"line {line_number}.experiment_id")
            _validate_id(event["physical_attempt_id"], f"line {line_number}.physical_attempt_id")
            if not isinstance(event["event"], str) or not _EVENT_TYPE_RE.fullmatch(event["event"]):
                raise EvidenceError(f"Ledger line {line_number} has an invalid event type")
            if not isinstance(event["payload"], dict):
                raise EvidenceError(f"Ledger line {line_number}.payload must be an object")
            _validate_safe_value(event["payload"], f"line {line_number}.payload")
            _validate_agent_event_payload(
                event["event"],
                event["payload"],
                f"line {line_number}.payload",
            )
            actual_digest = event["event_sha256"]
            _validate_sha256(actual_digest, f"line {line_number}.event_sha256")
            unsigned = {key: value for key, value in event.items() if key != "event_sha256"}
            if _sha256(unsigned) != actual_digest:
                raise EvidenceError(f"Ledger line {line_number} has an invalid event digest")
            previous_digest = actual_digest
            events.append(event)
        if events:
            experiment_ids = {event["experiment_id"] for event in events}
            attempt_ids = {event["physical_attempt_id"] for event in events}
            if len(experiment_ids) != 1 or len(attempt_ids) != 1:
                raise EvidenceError("One ledger may describe only one physical attempt")
            if events[0]["event"] != "experiment.started":
                raise EvidenceError("The first ledger event must be experiment.started")
        return events

    def read(self) -> list[dict[str, Any]]:
        return self.verify_path(self.path)

    def append(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not _EVENT_TYPE_RE.fullmatch(event):
            raise EvidenceError(f"Invalid evidence event type: {event!r}")
        if not isinstance(payload, dict):
            raise EvidenceError("Evidence payload must be an object")
        _validate_safe_value(payload)
        _validate_agent_event_payload(event, payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _path_lock(self.path), _exclusive_sibling_lock(self.path):
            existing = self.verify_path(self.path) if self.path.exists() else []
            if not existing and event != "experiment.started":
                raise EvidenceError("The first ledger event must be experiment.started")
            if existing:
                if existing[0]["experiment_id"] != self.experiment_id or existing[0]["physical_attempt_id"] != self.physical_attempt_id:
                    raise EvidenceError("Ledger identity does not match the active physical attempt")
                if any(item["event"] == "experiment.completed" for item in existing):
                    raise EvidenceError("A completed experiment ledger is immutable")
            unsigned = {
                "ledger_version": LEDGER_VERSION,
                "canonicalization": LEDGER_CANONICALIZATION,
                "sequence": len(existing) + 1,
                "occurred_at": utc_now_iso(),
                "event": event,
                "experiment_id": self.experiment_id,
                "physical_attempt_id": self.physical_attempt_id,
                "previous_event_sha256": existing[-1]["event_sha256"] if existing else None,
                "payload": payload,
            }
            record = {**unsigned, "event_sha256": _sha256(unsigned)}
            lines = [canonical_json_bytes(item).decode("utf-8") for item in existing]
            lines.append(canonical_json_bytes(record).decode("utf-8"))
            temporary_path: str | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.path.parent,
                    prefix=f".{self.path.name}.",
                    suffix=".tmp",
                    delete=False,
                    newline="\n",
                ) as fp:
                    temporary_path = fp.name
                    fp.write("\n".join(lines) + "\n")
                    fp.flush()
                    os.fsync(fp.fileno())
                os.replace(temporary_path, self.path)
                if os.name == "posix":
                    directory_fd = os.open(self.path.parent, os.O_RDONLY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
            finally:
                if temporary_path and os.path.exists(temporary_path):
                    os.unlink(temporary_path)
            return record


def activate_experiment(
    *,
    thread_id: str,
    experiment_id: str,
    physical_attempt_id: str,
    ledger: ExperimentLedger,
    policy: ExperimentPolicy,
) -> ActiveExperiment:
    if not thread_id or any(character in thread_id for character in ("\0", "\r", "\n")):
        raise EvidenceError("A safe thread_id is required to activate experiment evidence")
    active = ActiveExperiment(
        thread_id=thread_id,
        experiment_id=_validate_id(experiment_id, "experiment_id"),
        physical_attempt_id=_validate_id(physical_attempt_id, "physical_attempt_id"),
        ledger=ledger,
        policy=policy,
    )
    if ledger.experiment_id != active.experiment_id or ledger.physical_attempt_id != active.physical_attempt_id:
        raise EvidenceError("Active experiment identity does not match its ledger")
    with _ACTIVE_EXPERIMENTS_GUARD:
        if thread_id in _ACTIVE_EXPERIMENTS:
            raise EvidenceError("An experiment is already active for this thread")
        _ACTIVE_EXPERIMENTS[thread_id] = active
    return active


def deactivate_experiment(thread_id: str) -> ActiveExperiment | None:
    with _ACTIVE_EXPERIMENTS_GUARD:
        return _ACTIVE_EXPERIMENTS.pop(thread_id, None)


def get_active_experiment(thread_id: str | None) -> ActiveExperiment | None:
    if not thread_id:
        return None
    with _ACTIVE_EXPERIMENTS_GUARD:
        return _ACTIVE_EXPERIMENTS.get(thread_id)


def record_experiment_event(thread_id: str | None, event: str, **payload: Any) -> dict[str, Any] | None:
    active = get_active_experiment(thread_id)
    if active is None:
        return None
    return active.ledger.append(event, payload)


def request_thread_id(request: Any) -> str | None:
    runtime = getattr(request, "runtime", None)
    context = getattr(runtime, "context", None)
    if isinstance(context, dict) and isinstance(context.get("thread_id"), str):
        return context["thread_id"]
    config = getattr(runtime, "config", None)
    if isinstance(config, dict):
        configurable = config.get("configurable")
        if isinstance(configurable, dict) and isinstance(configurable.get("thread_id"), str):
            return configurable["thread_id"]
    return None


def request_model_role(request: Any) -> str:
    runtime = getattr(request, "runtime", None)
    context = getattr(runtime, "context", None)
    if isinstance(context, dict):
        role = context.get("agent_name")
        if role == "compiler":
            return "compiler"
        if isinstance(role, str) and role in _ALLOWED_MODEL_ROLES:
            return role
    return "lead"


def claim_experiment_clarification_auto_answer(
    request: Any,
) -> ExperimentPolicy | None:
    """Claim the one policy-backed clarification response allowed per experiment."""
    thread_id = request_thread_id(request)
    if request_model_role(request) != "lead":
        return None
    with _ACTIVE_EXPERIMENTS_GUARD:
        active = _ACTIVE_EXPERIMENTS.get(thread_id or "")
        if active is None:
            return None
        if any(event["event"] == "agent.clarification_auto_answered" for event in active.ledger.read()):
            return None
        active.ledger.append(
            "agent.clarification_auto_answered",
            {
                "repair_id": new_evidence_id("repair"),
                "role": "lead",
                "reason": "non_interactive_frozen_policy",
                "auto_answer_count": 1,
                "max_auto_answers": 1,
                "terminal": False,
            },
        )
        return active.policy


def record_agent_tool_failure(
    request: Any,
    exc: Exception,
    *,
    execution_mode: str,
) -> dict[str, Any] | None:
    if execution_mode not in _ALLOWED_TOOL_EXECUTION_MODES:
        raise EvidenceError("execution_mode must be sync or async")
    tool_call = getattr(request, "tool_call", None)
    if not isinstance(tool_call, dict):
        tool_call = {}
    return record_experiment_event(
        request_thread_id(request),
        "agent.tool_failed",
        failure_id=new_evidence_id("failure"),
        role=request_model_role(request),
        tool_name=_bounded_identifier(tool_call.get("name"), "unknown_tool"),
        tool_call_id=_bounded_identifier(
            tool_call.get("id"),
            "missing_tool_call_id",
        ),
        exception_class=_bounded_identifier(
            type(exc).__name__,
            "UnknownException",
        ),
        execution_mode=execution_mode,
        terminal=False,
    )


def request_model_name(request: Any, fallback: str) -> str:
    model = getattr(request, "model", None)
    for attribute in ("model_name", "model"):
        value = getattr(model, attribute, None)
        if isinstance(value, str) and value and len(value) <= 128:
            _validate_safe_value(value, "model_name")
            return value
    return fallback


def request_model_endpoint(request: Any) -> str | None:
    model = getattr(request, "model", None)
    candidates = [
        getattr(model, "openai_api_base", None),
        getattr(model, "base_url", None),
    ]
    for client_attribute in ("root_client", "client"):
        client = getattr(model, client_attribute, None)
        candidates.append(getattr(client, "base_url", None))
    for candidate in candidates:
        if candidate is None:
            continue
        value = str(candidate).rstrip("/")
        try:
            return _validate_endpoint(value)
        except EvidenceError:
            continue
    return None


def model_response_metadata(response: Any) -> tuple[str | None, dict[str, int | None]]:
    candidates: list[Any] = []
    if hasattr(response, "result"):
        result = getattr(response, "result")
        if isinstance(result, (list, tuple)):
            candidates.extend(result[:8])
        else:
            candidates.append(result)
    candidates.append(response)
    actual_model: str | None = None
    usage = {"input_tokens": None, "output_tokens": None, "total_tokens": None}
    for candidate in candidates:
        metadata = getattr(candidate, "response_metadata", None)
        if isinstance(metadata, dict):
            for key in ("model_name", "model"):
                value = metadata.get(key)
                if isinstance(value, str) and value and len(value) <= 128:
                    _validate_safe_value(value, "actual_model")
                    actual_model = value
                    break
        usage_metadata = getattr(candidate, "usage_metadata", None)
        if isinstance(usage_metadata, dict):
            for key in usage:
                value = usage_metadata.get(key)
                if isinstance(value, int) and value >= 0:
                    usage[key] = value
        if actual_model is not None and any(value is not None for value in usage.values()):
            break
    return actual_model, usage


def allowed_command_role(role: str | None) -> str:
    if role is None:
        return "other"
    if role not in _ALLOWED_COMMAND_ROLES:
        raise EvidenceError(f"Unsupported compile command role: {role!r}")
    return role
