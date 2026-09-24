from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from deerflow.compile.agent_workflow_schemas import AgentBuildNodeInput, AgentBuildNodeResult, SubmitCandidateRequest
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.operations import _infer_executed_build_system, submit_build_result_impl
from deerflow.compile.schemas import TERMINAL_COMPILE_SESSION_STATUSES, BuildArtifact, CompileSession, ReplayVerificationResult, utc_now_iso
from deerflow.tools.bound_compile_tools import _run_container_bash_impl

EXTERNAL_EVALUATOR_SCHEMA_VERSION = "agent-workflow-external-evaluator-v1"
EXTERNAL_EVALUATOR_VERSION = "forge-external-evaluator-1.0.0"
EXTERNAL_EVALUATOR_LAYERS = ("S0", "S1", "S2", "S3", "S4", "S5")
EXTERNAL_EVALUATOR_STATUSES = frozenset({"passed", "failed", "not_run", "invalid"})
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REPLAY_ROLES = frozenset({"dependency", "dependency_setup", "configure", "build", "artifact_stage"})
_RULES = {
    "schema_version": EXTERNAL_EVALUATOR_SCHEMA_VERSION,
    "layers": list(EXTERNAL_EVALUATOR_LAYERS),
    "strict_success": "all_layers_passed",
    "bitwise_reproducibility": "auxiliary_unless_task_contract_requires",
    "agent_report_is_truth": False,
    "targeted_reevaluation": "append_only_new_run",
}
EXTERNAL_EVALUATOR_RULES_SHA256 = hashlib.sha256(json.dumps(_RULES, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ExternalEvaluatorError(RuntimeError):
    """外部 evaluator 无法产生可信判定。"""


class ExternalEvaluatorContractError(ExternalEvaluatorError):
    """外部 evaluator 的输入或输出不满足冻结合同。"""


class ExternalEvaluatorIdentityError(ExternalEvaluatorError):
    """evaluation run 的身份或 create-once 边界冲突。"""


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ExternalEvaluatorContractError(f"value is not canonical JSON: {exc}") from exc


def _require_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise ExternalEvaluatorContractError(f"{field_name} must be a bounded identifier")


def _require_sha256(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ExternalEvaluatorContractError(f"{field_name} must be a lowercase SHA-256 digest")


def _write_create_once(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ExternalEvaluatorIdentityError(f"evaluation output already exists: {path}") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


@dataclass(frozen=True)
class EvaluatorEvidenceReference:
    kind: str
    identifier: str
    relative_path: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    exit_code: int | None = None

    def validate(self) -> None:
        _require_identifier(self.kind, "evidence.kind")
        _require_identifier(self.identifier, "evidence.identifier")
        if self.relative_path is not None:
            path = PurePosixPath(self.relative_path)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ExternalEvaluatorContractError("evidence.relative_path must be a safe relative POSIX path")
        if self.sha256 is not None:
            _require_sha256(self.sha256, "evidence.sha256")
        if self.size_bytes is not None and (type(self.size_bytes) is not int or self.size_bytes < 0):
            raise ExternalEvaluatorContractError("evidence.size_bytes must be a non-negative integer")
        if self.exit_code is not None and type(self.exit_code) is not int:
            raise ExternalEvaluatorContractError("evidence.exit_code must be an integer")


@dataclass(frozen=True)
class ExternalEvaluatorLayerResult:
    layer: str
    status: str
    reason_codes: tuple[str, ...]
    evidence: tuple[EvaluatorEvidenceReference, ...] = ()

    def validate(self) -> None:
        if self.layer not in EXTERNAL_EVALUATOR_LAYERS:
            raise ExternalEvaluatorContractError(f"unsupported evaluator layer: {self.layer!r}")
        if self.status not in EXTERNAL_EVALUATOR_STATUSES:
            raise ExternalEvaluatorContractError(f"unsupported evaluator status: {self.status!r}")
        if not self.reason_codes or len(set(self.reason_codes)) != len(self.reason_codes):
            raise ExternalEvaluatorContractError("layer reason_codes must be unique and non-empty")
        for reason in self.reason_codes:
            _require_identifier(reason, "layer.reason_codes")
        for reference in self.evidence:
            reference.validate()


@dataclass(frozen=True)
class ExternalEvaluatorBackendResult:
    layers: tuple[ExternalEvaluatorLayerResult, ...]
    bitwise_reproducible: bool | None

    def validate(self) -> None:
        if tuple(layer.layer for layer in self.layers) != ("S2", "S3", "S4", "S5"):
            raise ExternalEvaluatorContractError("backend layers must be ordered S2 through S5")
        for layer in self.layers:
            layer.validate()
        if self.bitwise_reproducible is not None and type(self.bitwise_reproducible) is not bool:
            raise ExternalEvaluatorContractError("bitwise_reproducible must be boolean or null")


@dataclass(frozen=True)
class ExternalEvaluationResult:
    evaluation_id: str
    task_id: str
    attempt_id: str
    run_id: str | None
    session_id: str
    submission_id: str | None
    commit_sha: str
    build_system: str
    candidate_record_sha256: str
    node_input_sha256: str
    node_result_sha256: str
    evaluator_version: str
    evaluator_rules_sha256: str
    layers: tuple[ExternalEvaluatorLayerResult, ...]
    strict_reproducible_build_success: bool
    bitwise_reproducible: bool | None
    primary_failure: str | None
    started_at: str
    completed_at: str
    evidence_head_sha256: str
    schema_version: str = EXTERNAL_EVALUATOR_SCHEMA_VERSION

    def validate(self) -> None:
        if self.schema_version != EXTERNAL_EVALUATOR_SCHEMA_VERSION:
            raise ExternalEvaluatorContractError("unsupported evaluator schema version")
        for field_name in ("evaluation_id", "task_id", "attempt_id", "session_id", "build_system", "evaluator_version"):
            _require_identifier(getattr(self, field_name), field_name)
        for field_name in ("run_id", "submission_id"):
            value = getattr(self, field_name)
            if value is not None:
                _require_identifier(value, field_name)
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", self.commit_sha):
            raise ExternalEvaluatorContractError("commit_sha must be a full Git object ID")
        for field_name in ("candidate_record_sha256", "node_input_sha256", "node_result_sha256", "evaluator_rules_sha256", "evidence_head_sha256"):
            _require_sha256(getattr(self, field_name), field_name)
        if tuple(layer.layer for layer in self.layers) != EXTERNAL_EVALUATOR_LAYERS:
            raise ExternalEvaluatorContractError("evaluation layers must be ordered S0 through S5")
        for layer in self.layers:
            layer.validate()
        strict = all(layer.status == "passed" for layer in self.layers)
        if self.strict_reproducible_build_success is not strict:
            raise ExternalEvaluatorContractError("strict success must equal the conjunction of S0 through S5")
        if self.bitwise_reproducible is not None and type(self.bitwise_reproducible) is not bool:
            raise ExternalEvaluatorContractError("bitwise_reproducible must be boolean or null")
        expected_failure = next((layer.reason_codes[0] for layer in self.layers if layer.status != "passed"), None)
        if self.primary_failure != expected_failure:
            raise ExternalEvaluatorContractError("primary_failure must be the first non-passing layer reason")

    def canonical_json(self) -> str:
        self.validate()
        return _canonical_json(asdict(self))

    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


@dataclass(frozen=True)
class FunctionalOracleSpec:
    oracle_ref: str
    argv: tuple[str, ...]
    workdir: str = "/workspace/repo"
    timeout_seconds: int = 120
    acceptable_exit_codes: tuple[int, ...] = (0,)
    requires_explicit_relative_executable: bool = False

    def validate(self) -> None:
        _require_identifier(self.oracle_ref, "oracle_ref")
        if not self.argv or any(not isinstance(part, str) or not part or "\0" in part for part in self.argv):
            raise ExternalEvaluatorContractError("oracle argv must contain non-empty strings")
        executable = self.argv[0]
        if self.requires_explicit_relative_executable and not (executable.startswith("./") or executable.startswith("/") or "/" in executable):
            raise ExternalEvaluatorContractError("relative target executables must use an explicit './' path")
        workdir = PurePosixPath(self.workdir)
        if not workdir.is_absolute() or ".." in workdir.parts or not any(workdir == root or root in workdir.parents for root in (PurePosixPath("/workspace"), PurePosixPath("/artifacts"))):
            raise ExternalEvaluatorContractError("oracle workdir must remain inside compile-container roots")
        if type(self.timeout_seconds) is not int or self.timeout_seconds < 1:
            raise ExternalEvaluatorContractError("oracle timeout_seconds must be positive")
        if not self.acceptable_exit_codes or len(set(self.acceptable_exit_codes)) != len(self.acceptable_exit_codes) or any(type(code) is not int for code in self.acceptable_exit_codes):
            raise ExternalEvaluatorContractError("oracle acceptable_exit_codes must be unique integers")

    def shell_command(self) -> str:
        self.validate()
        return shlex.join(self.argv)

    def canonical_json(self) -> str:
        self.validate()
        return _canonical_json(asdict(self))

    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


@dataclass(frozen=True)
class FunctionalOracleExecution:
    layer: ExternalEvaluatorLayerResult
    verification_command_ids: tuple[str, ...]

    def validate(self) -> None:
        self.layer.validate()
        if self.layer.layer != "S3":
            raise ExternalEvaluatorContractError("functional oracle must produce S3")
        if len(set(self.verification_command_ids)) != len(self.verification_command_ids):
            raise ExternalEvaluatorContractError("verification_command_ids must be unique")


class ExternalEvaluatorBackend(Protocol):
    def evaluate(
        self,
        *,
        node_input: AgentBuildNodeInput,
        candidate: SubmitCandidateRequest,
        session: CompileSession,
        manager: CompileSessionManager,
        evaluation_dir: Path,
    ) -> ExternalEvaluatorBackendResult: ...


class FunctionalOracleRunner(Protocol):
    def run(
        self,
        *,
        spec: FunctionalOracleSpec,
        session: CompileSession,
        manager: CompileSessionManager,
        evaluation_dir: Path,
    ) -> FunctionalOracleExecution: ...


class ExternalEvaluatorEvidenceLedger:
    def __init__(self, path: Path, *, node_input: AgentBuildNodeInput, evaluation_id: str, run_id: str | None, previous_hash: str):
        _require_sha256(previous_hash, "previous_hash")
        self.path = path
        self.node_input = node_input
        self.evaluation_id = evaluation_id
        self.run_id = run_id
        self._head_sha256 = previous_hash
        self._sequence = 0
        self._lock = threading.Lock()
        _write_create_once(path, "")

    @property
    def head_sha256(self) -> str:
        return self._head_sha256

    def append(self, event_type: str, **payload: Any) -> str:
        with self._lock:
            self._sequence += 1
            entry = {
                "schema_version": EXTERNAL_EVALUATOR_SCHEMA_VERSION,
                "event_id": f"event:{uuid.uuid4().hex}",
                "sequence": self._sequence,
                "timestamp": utc_now_iso(),
                "task_id": self.node_input.task_id,
                "attempt_id": self.node_input.attempt_id,
                "run_id": self.run_id,
                "session_id": self.node_input.session_id,
                "evaluation_id": self.evaluation_id,
                "event_type": event_type,
                "payload": payload,
                "previous_hash": self._head_sha256,
            }
            canonical = _canonical_json(entry)
            event_hash = hashlib.sha256(canonical.encode()).hexdigest()
            entry["event_hash"] = event_hash
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(_canonical_json(entry) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            self._head_sha256 = event_hash
            return event_hash


def load_frozen_candidate(path: Path) -> SubmitCandidateRequest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("candidate payload must be an object")
        for field_name in ("supporting_command_ids", "artifact_paths", "recipe_command_ids", "known_limitations"):
            if field_name in payload:
                payload[field_name] = tuple(payload[field_name])
        candidate = SubmitCandidateRequest(**payload)
        candidate.validate()
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ExternalEvaluatorContractError(f"cannot load frozen candidate: {type(exc).__name__}") from exc
    return candidate


def _reference(kind: str, identifier: str, *, path: str | None = None, sha256: str | None = None, size_bytes: int | None = None, exit_code: int | None = None) -> EvaluatorEvidenceReference:
    return EvaluatorEvidenceReference(kind=kind, identifier=identifier, relative_path=path, sha256=sha256, size_bytes=size_bytes, exit_code=exit_code)


def _layer(layer: str, status: str, *reason_codes: str, evidence: Sequence[EvaluatorEvidenceReference] = ()) -> ExternalEvaluatorLayerResult:
    result = ExternalEvaluatorLayerResult(layer=layer, status=status, reason_codes=tuple(reason_codes), evidence=tuple(evidence))
    result.validate()
    return result


def _evaluate_s0(
    *,
    node_input: AgentBuildNodeInput,
    node_result: AgentBuildNodeResult,
    candidate: SubmitCandidateRequest,
    session: CompileSession,
) -> ExternalEvaluatorLayerResult:
    reasons: list[str] = []
    if node_result.node_status != "submitted" or not node_result.candidate_submitted or node_result.submission_id is None:
        reasons.append("node_not_submitted")
    if node_result.candidate_record_sha256 != candidate.canonical_sha256():
        reasons.append("candidate_identity_mismatch")
    if session.session_id != node_input.session_id or session.repo_url != node_input.repository_url or session.commit_sha != node_input.commit_sha:
        reasons.append("source_identity_mismatch")
    if session.image_id != node_input.environment.image_id or session.parallel_jobs != node_input.environment.parallel_jobs:
        reasons.append("environment_identity_mismatch")
    if session.run_id is None:
        reasons.append("run_identity_missing")
    if node_result.session_terminal_status != session.status:
        reasons.append("session_status_mismatch")
    if session.status in TERMINAL_COMPILE_SESSION_STATUSES or session.finalized_at is not None or session.termination_requested_at is not None:
        reasons.append("session_inactive")
    evidence = (
        _reference("node_input", node_input.attempt_id, sha256=node_input.canonical_sha256()),
        _reference("node_result", node_input.attempt_id, sha256=node_result.canonical_sha256()),
        _reference("candidate", candidate.candidate_id, sha256=candidate.canonical_sha256()),
        _reference("session", session.session_id),
    )
    return _layer("S0", "passed" if not reasons else "invalid", *(reasons or ["identity_valid"]), evidence=evidence)


def _evaluate_s1(candidate: SubmitCandidateRequest, session: CompileSession) -> ExternalEvaluatorLayerResult:
    positions: dict[str, list[int]] = {}
    for index, command in enumerate(session.commands):
        positions.setdefault(command.command_id, []).append(index)
    reasons: list[str] = []
    if len(candidate.supporting_command_ids) != 1:
        reasons.append("supporting_command_cardinality_invalid")
    previous = -1
    for command_id in candidate.recipe_command_ids:
        matches = positions.get(command_id, [])
        if not matches:
            reasons.append("command_missing")
            continue
        if len(matches) != 1:
            reasons.append("command_ambiguous")
            continue
        position = matches[0]
        command = session.commands[position]
        if position <= previous:
            reasons.append("command_order_invalid")
        previous = position
        if command.completed_at is None:
            reasons.append("command_not_completed")
        elif command.exit_code != 0 or command.timed_out:
            reasons.append("command_not_successful")
        if command.role not in _REPLAY_ROLES:
            reasons.append("command_role_invalid")
    for command_id in candidate.supporting_command_ids:
        matches = positions.get(command_id, [])
        if len(matches) != 1:
            reasons.append("supporting_command_invalid")
            continue
        command = session.commands[matches[0]]
        if command.role != "build" or command.exit_code != 0 or command.timed_out:
            reasons.append("supporting_command_invalid")
        if _infer_executed_build_system(session.commands, command_id) != candidate.build_system:
            reasons.append("build_system_mismatch")
    recipe_roles = {session.commands[matches[0]].role for command_id in candidate.recipe_command_ids if len(matches := positions.get(command_id, [])) == 1}
    if "artifact_stage" not in recipe_roles:
        reasons.append("artifact_stage_missing")
    evidence = tuple(_reference("command", command_id) for command_id in candidate.recipe_command_ids)
    return _layer("S1", "passed" if not reasons else "failed", *(tuple(dict.fromkeys(reasons)) or ("commands_valid",)), evidence=evidence)


class ExternalEvaluatorRunner:
    def __init__(
        self,
        *,
        node_input: AgentBuildNodeInput,
        node_result: AgentBuildNodeResult,
        session: CompileSession,
        manager: CompileSessionManager,
        candidate_path: Path,
        evaluation_id: str,
        backend: ExternalEvaluatorBackend,
        completed_clock: Callable[[], str] = utc_now_iso,
    ):
        self.node_input = node_input
        self.node_result = node_result
        self.session = session
        self.manager = manager
        self.candidate_path = candidate_path
        self.evaluation_id = evaluation_id
        self.backend = backend
        self.completed_clock = completed_clock
        self.evaluation_dir = candidate_path.parent / "evaluations" / evaluation_id

    def run(self) -> ExternalEvaluationResult:
        _require_identifier(self.evaluation_id, "evaluation_id")
        self.node_input.validate()
        self.node_result.validate()
        candidate = load_frozen_candidate(self.candidate_path)
        try:
            self.evaluation_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise ExternalEvaluatorIdentityError(f"evaluation already exists: {self.evaluation_id}") from exc
        started_at = self.completed_clock()
        ledger = ExternalEvaluatorEvidenceLedger(
            self.evaluation_dir / "events.jsonl",
            node_input=self.node_input,
            evaluation_id=self.evaluation_id,
            run_id=self.session.run_id,
            previous_hash=self.node_result.evidence_head_sha256,
        )
        ledger.append(
            "evaluator.started",
            evaluator_version=EXTERNAL_EVALUATOR_VERSION,
            evaluator_rules_sha256=EXTERNAL_EVALUATOR_RULES_SHA256,
            candidate_record_sha256=candidate.canonical_sha256(),
        )
        current = self.session
        layers: list[ExternalEvaluatorLayerResult] = []
        bitwise_reproducible: bool | None = None
        evaluator_failed = False
        try:
            current = self.manager.load_session(self.session.session_id, self.session.thread_id)
            self.session.__dict__.update(current.__dict__)
            layers.extend(
                (
                    _evaluate_s0(node_input=self.node_input, node_result=self.node_result, candidate=candidate, session=current),
                    _evaluate_s1(candidate, current),
                )
            )
            if all(layer.status == "passed" for layer in layers):
                backend_result = self.backend.evaluate(
                    node_input=self.node_input,
                    candidate=candidate,
                    session=current,
                    manager=self.manager,
                    evaluation_dir=self.evaluation_dir,
                )
                backend_result.validate()
                layers.extend(backend_result.layers)
                bitwise_reproducible = backend_result.bitwise_reproducible
            else:
                blocking_layer = next(layer.layer.lower() for layer in layers if layer.status != "passed")
                layers.extend(_layer(layer, "not_run", f"blocked_by_{blocking_layer}") for layer in EXTERNAL_EVALUATOR_LAYERS[2:])
        except Exception as exc:
            evaluator_failed = True
            failure = {
                "schema_version": EXTERNAL_EVALUATOR_SCHEMA_VERSION,
                "evaluation_id": self.evaluation_id,
                "task_id": self.node_input.task_id,
                "attempt_id": self.node_input.attempt_id,
                "error_class": type(exc).__name__,
                "classification": "evaluator_internal_error",
            }
            _write_create_once(self.evaluation_dir / "failure.json", _canonical_json(failure) + "\n")
            completed_layers = {layer.layer for layer in layers}
            first_missing = next(layer_name for layer_name in EXTERNAL_EVALUATOR_LAYERS if layer_name not in completed_layers)
            for layer_name in EXTERNAL_EVALUATOR_LAYERS:
                if layer_name in completed_layers:
                    continue
                status = "invalid" if layer_name == first_missing else "not_run"
                reason = "evaluator_internal_error" if status == "invalid" else "blocked_by_evaluator_error"
                layers.append(_layer(layer_name, status, reason))
            ledger.append("evaluator.failed", error_class=type(exc).__name__, classification="evaluator_internal_error")

        if not evaluator_failed:
            for layer in layers:
                ledger.append("evaluator.check_completed", layer=layer.layer, status=layer.status, reason_codes=list(layer.reason_codes))
        strict_success = all(layer.status == "passed" for layer in layers)
        primary_failure = next((layer.reason_codes[0] for layer in layers if layer.status != "passed"), None)
        ledger.append(
            "evaluator.terminal",
            status="passed" if strict_success else "failed",
            primary_failure=primary_failure,
            bitwise_reproducible=bitwise_reproducible,
        )
        result = ExternalEvaluationResult(
            evaluation_id=self.evaluation_id,
            task_id=self.node_input.task_id,
            attempt_id=self.node_input.attempt_id,
            run_id=current.run_id,
            session_id=current.session_id,
            submission_id=self.node_result.submission_id,
            commit_sha=self.node_input.commit_sha,
            build_system=candidate.build_system,
            candidate_record_sha256=candidate.canonical_sha256(),
            node_input_sha256=self.node_input.canonical_sha256(),
            node_result_sha256=self.node_result.canonical_sha256(),
            evaluator_version=EXTERNAL_EVALUATOR_VERSION,
            evaluator_rules_sha256=EXTERNAL_EVALUATOR_RULES_SHA256,
            layers=tuple(layers),
            strict_reproducible_build_success=strict_success,
            bitwise_reproducible=bitwise_reproducible,
            primary_failure=primary_failure,
            started_at=started_at,
            completed_at=self.completed_clock(),
            evidence_head_sha256=ledger.head_sha256,
        )
        result.validate()
        result_json = result.canonical_json()
        _write_create_once(self.evaluation_dir / "result.json", result_json + "\n")
        summary = {
            "schema_version": EXTERNAL_EVALUATOR_SCHEMA_VERSION,
            "evaluation_id": self.evaluation_id,
            "status": "passed" if strict_success else "failed",
            "strict_reproducible_build_success": strict_success,
            "bitwise_reproducible": bitwise_reproducible,
            "primary_failure": primary_failure,
            "result_sha256": hashlib.sha256(result_json.encode()).hexdigest(),
        }
        _write_create_once(self.evaluation_dir / "summary.json", _canonical_json(summary) + "\n")
        return result


class BoundCommandFunctionalOracleRunner:
    def run(
        self,
        *,
        spec: FunctionalOracleSpec,
        session: CompileSession,
        manager: CompileSessionManager,
        evaluation_dir: Path,
    ) -> FunctionalOracleExecution:
        spec.validate()
        command_result, _message, record = _run_container_bash_impl(
            session=session,
            command=spec.shell_command(),
            timeout_seconds=spec.timeout_seconds,
            workdir=spec.workdir,
            command_role="smoke",
        )
        streams_dir = evaluation_dir / "oracle"
        stdout_path = streams_dir / "stdout.log"
        stderr_path = streams_dir / "stderr.log"
        _write_create_once(stdout_path, command_result.stdout)
        _write_create_once(stderr_path, command_result.stderr)
        stdout_bytes = command_result.stdout.encode()
        stderr_bytes = command_result.stderr.encode()
        evidence = (
            _reference("command", record.command_id, exit_code=record.exit_code),
            _reference("oracle_stdout", f"{record.command_id}:stdout", path="oracle/stdout.log", sha256=hashlib.sha256(stdout_bytes).hexdigest(), size_bytes=len(stdout_bytes)),
            _reference("oracle_stderr", f"{record.command_id}:stderr", path="oracle/stderr.log", sha256=hashlib.sha256(stderr_bytes).hexdigest(), size_bytes=len(stderr_bytes)),
        )
        passed = record.completed_at is not None and not record.timed_out and record.exit_code in spec.acceptable_exit_codes
        layer = _layer("S3", "passed" if passed else "failed", "functional_oracle_passed" if passed else "functional_oracle_failed", evidence=evidence)
        current = manager.load_session(session.session_id, session.thread_id)
        session.__dict__.update(current.__dict__)
        return FunctionalOracleExecution(layer=layer, verification_command_ids=(record.command_id,) if passed else ())


Submitter = Callable[..., str]


class ForgeCompileEvaluationBackend:
    def __init__(
        self,
        *,
        oracle_registry: Mapping[str, FunctionalOracleSpec],
        oracle_runner: FunctionalOracleRunner | None = None,
        submitter: Submitter = submit_build_result_impl,
    ):
        self.oracle_registry = dict(oracle_registry)
        for oracle_ref, spec in self.oracle_registry.items():
            spec.validate()
            if oracle_ref != spec.oracle_ref:
                raise ExternalEvaluatorContractError("oracle registry key must match oracle_ref")
        self.oracle_runner = oracle_runner or BoundCommandFunctionalOracleRunner()
        self.submitter = submitter

    def evaluate(
        self,
        *,
        node_input: AgentBuildNodeInput,
        candidate: SubmitCandidateRequest,
        session: CompileSession,
        manager: CompileSessionManager,
        evaluation_dir: Path,
    ) -> ExternalEvaluatorBackendResult:
        spec = self.oracle_registry.get(node_input.target_contract.functional_oracle_ref)
        if spec is None:
            return ExternalEvaluatorBackendResult(
                layers=(
                    _layer("S2", "not_run", "functional_oracle_unavailable"),
                    _layer("S3", "invalid", "functional_oracle_unavailable"),
                    _layer("S4", "not_run", "functional_oracle_unavailable"),
                    _layer("S5", "not_run", "functional_oracle_unavailable"),
                ),
                bitwise_reproducible=None,
            )
        oracle = self.oracle_runner.run(spec=spec, session=session, manager=manager, evaluation_dir=evaluation_dir)
        oracle.validate()
        oracle_layer = replace(
            oracle.layer,
            evidence=(_reference("oracle_spec", spec.oracle_ref, sha256=spec.canonical_sha256()), *oracle.layer.evidence),
        )
        oracle_layer.validate()
        payload = json.loads(
            self.submitter(
                session=session,
                supporting_command_id=candidate.supporting_command_ids[0],
                recipe_command_ids=list(candidate.recipe_command_ids),
                verification_command_ids=list(oracle.verification_command_ids),
            )
        )
        current = manager.load_session(session.session_id, session.thread_id)
        session.__dict__.update(current.__dict__)
        s2 = self._evaluate_s2(candidate, node_input, current, payload)
        s4 = self._evaluate_s4(candidate, current, payload)
        s5, bitwise = self._evaluate_s5(current, payload, oracle_layer.status == "passed")
        return ExternalEvaluatorBackendResult(layers=(s2, oracle_layer, s4, s5), bitwise_reproducible=bitwise)

    @staticmethod
    def _session_artifacts(session: CompileSession) -> list[tuple[str, BuildArtifact]]:
        result: list[tuple[str, BuildArtifact]] = []
        for artifact in session.artifacts:
            source = PurePosixPath(artifact.source_path or "")
            try:
                relative = source.relative_to("/artifacts").as_posix()
            except ValueError:
                continue
            result.append((relative, artifact))
        return result

    @classmethod
    def _evaluate_s2(
        cls,
        candidate: SubmitCandidateRequest,
        node_input: AgentBuildNodeInput,
        session: CompileSession,
        payload: Mapping[str, Any],
    ) -> ExternalEvaluatorLayerResult:
        artifact_entries = cls._session_artifacts(session)
        artifacts_by_path = {path: artifact for path, artifact in artifact_entries}
        requested_paths = set(candidate.artifact_paths)
        target_paths = set(candidate.target_mapping.values())
        reasons: list[str] = []
        if payload.get("candidate_status") != "passed":
            reasons.append("candidate_verifier_failed")
        if len(artifact_entries) != len(artifacts_by_path) or set(artifacts_by_path) != requested_paths:
            reasons.append("candidate_artifact_set_mismatch")
        allowed_types = set(node_input.target_contract.artifact_types)
        if not artifact_entries or any(not artifact.size_bytes or not artifact.sha256 for _, artifact in artifact_entries):
            reasons.append("candidate_artifact_invalid")
        target_artifacts = [artifacts_by_path[path] for path in target_paths if path in artifacts_by_path]
        if set(candidate.target_mapping) != {node_input.target_contract.target_id} or len(target_artifacts) != len(target_paths) or any(artifact.artifact_type not in allowed_types for artifact in target_artifacts):
            reasons.append("target_mapping_invalid")
        patterns = node_input.target_contract.artifact_path_patterns
        if any(not any(PurePosixPath(path).match(pattern) for pattern in patterns) for path in target_paths):
            reasons.append("target_path_mismatch")
        evidence = tuple(_reference("artifact", PurePosixPath(path).name, path=path, sha256=artifact.sha256, size_bytes=artifact.size_bytes) for path, artifact in artifact_entries)
        return _layer("S2", "passed" if not reasons else "failed", *(reasons or ["candidate_artifacts_valid"]), evidence=evidence)

    @staticmethod
    def _evaluate_s4(candidate: SubmitCandidateRequest, session: CompileSession, payload: Mapping[str, Any]) -> ExternalEvaluatorLayerResult:
        reasons: list[str] = []
        if session.executed_build_system != candidate.build_system:
            reasons.append("build_system_provenance_mismatch")
        if session.replay_recipe is None:
            reasons.append("replay_recipe_missing")
        if payload.get("classification") not in (None, "sha256_mismatch"):
            reasons.append("provenance_policy_failed")
        evidence = (_reference("session", session.session_id),)
        if session.replay_recipe is not None:
            evidence += (_reference("replay_recipe", session.replay_recipe.fingerprint),)
        return _layer("S4", "passed" if not reasons else "failed", *(reasons or ["provenance_policy_valid"]), evidence=evidence)

    @staticmethod
    def _find_replay(session: CompileSession, payload: Mapping[str, Any]) -> ReplayVerificationResult | None:
        replay_id = payload.get("replay_attempt_id")
        return next((attempt for attempt in session.replay_attempts if attempt.attempt_id == replay_id), None)

    @classmethod
    def _evaluate_s5(
        cls,
        session: CompileSession,
        payload: Mapping[str, Any],
        oracle_passed: bool,
    ) -> tuple[ExternalEvaluatorLayerResult, bool | None]:
        attempt = cls._find_replay(session, payload)
        if attempt is None:
            return _layer("S5", "failed", "clean_replay_missing"), None
        checks = {check.name: check for check in attempt.checks}
        comparisons = attempt.artifacts
        recipe_passed = checks.get("recipe_execution") is not None and checks["recipe_execution"].passed
        verification_passed = checks.get("verification_execution") is not None and checks["verification_execution"].passed
        artifact_set_passed = checks.get("artifact_set") is not None and checks["artifact_set"].passed
        functional_artifacts_passed = bool(comparisons) and all(item.type_matches and item.smoke_matches and item.actual_size_bytes is not None and item.actual_size_bytes > 0 for item in comparisons)
        cleanup_passed = attempt.cleanup_succeeded is True
        functional_passed = recipe_passed and verification_passed and artifact_set_passed and functional_artifacts_passed and cleanup_passed and oracle_passed
        bitwise = artifact_set_passed and bool(comparisons) and all(item.sha256_matches for item in comparisons)
        reasons: list[str] = []
        if not recipe_passed:
            reasons.append("replay_recipe_failed")
        if not verification_passed or not oracle_passed:
            reasons.append("replay_functional_oracle_failed")
        if not artifact_set_passed or not functional_artifacts_passed:
            reasons.append("replay_artifact_invalid")
        if not cleanup_passed:
            reasons.append("replay_cleanup_failed")
        if functional_passed and not bitwise:
            reasons.append("functional_replay_passed_bitwise_mismatch")
        evidence = (_reference("replay", attempt.attempt_id),)
        return _layer("S5", "passed" if functional_passed else "failed", *(reasons or ["clean_replay_functional_success"]), evidence=evidence), bitwise


def run_external_evaluator_v1(
    *,
    node_input: AgentBuildNodeInput,
    node_result: AgentBuildNodeResult,
    session: CompileSession,
    manager: CompileSessionManager,
    candidate_path: Path,
    evaluation_id: str,
    backend: ExternalEvaluatorBackend,
) -> ExternalEvaluationResult:
    return ExternalEvaluatorRunner(
        node_input=node_input,
        node_result=node_result,
        session=session,
        manager=manager,
        candidate_path=candidate_path,
        evaluation_id=evaluation_id,
        backend=backend,
    ).run()


@dataclass(frozen=True)
class ExternalEvaluationAdjudication:
    adjudication_id: str
    task_order: tuple[str, ...]
    selected_evaluations: tuple[ExternalEvaluationResult, ...]
    source_result_sha256: tuple[str, ...]
    schema_version: str = EXTERNAL_EVALUATOR_SCHEMA_VERSION

    def validate(self) -> None:
        if self.schema_version != EXTERNAL_EVALUATOR_SCHEMA_VERSION:
            raise ExternalEvaluatorContractError("unsupported adjudication schema version")
        _require_identifier(self.adjudication_id, "adjudication_id")
        if not self.task_order or len(set(self.task_order)) != len(self.task_order):
            raise ExternalEvaluatorContractError("task_order must be unique and non-empty")
        if tuple(result.task_id for result in self.selected_evaluations) != self.task_order:
            raise ExternalEvaluatorContractError("selected evaluations must exactly match task_order")
        if tuple(result.canonical_sha256() for result in self.selected_evaluations) != self.source_result_sha256:
            raise ExternalEvaluatorContractError("source result digests do not match selected evaluations")
        for result in self.selected_evaluations:
            result.validate()

    def canonical_json(self) -> str:
        self.validate()
        return _canonical_json(asdict(self))


def adjudicate_external_evaluations_v1(
    *,
    adjudication_id: str,
    base_results: Sequence[ExternalEvaluationResult],
    replacement_results: Sequence[ExternalEvaluationResult],
    task_order: Sequence[str],
    output_path: Path,
) -> ExternalEvaluationAdjudication:
    base_by_task = {result.task_id: result for result in base_results}
    if len(base_by_task) != len(base_results) or tuple(base_by_task) != tuple(task_order):
        raise ExternalEvaluatorIdentityError("base results must be unique and follow the frozen task order")
    selected = dict(base_by_task)
    seen_replacements: set[str] = set()
    for replacement in replacement_results:
        if replacement.task_id in seen_replacements or replacement.task_id not in base_by_task:
            raise ExternalEvaluatorIdentityError("replacement task identity is unknown or duplicated")
        seen_replacements.add(replacement.task_id)
        base = base_by_task[replacement.task_id]
        replacement_identity = (
            replacement.attempt_id,
            replacement.run_id,
            replacement.session_id,
            replacement.submission_id,
            replacement.commit_sha,
            replacement.build_system,
            replacement.candidate_record_sha256,
            replacement.node_input_sha256,
            replacement.node_result_sha256,
        )
        base_identity = (
            base.attempt_id,
            base.run_id,
            base.session_id,
            base.submission_id,
            base.commit_sha,
            base.build_system,
            base.candidate_record_sha256,
            base.node_input_sha256,
            base.node_result_sha256,
        )
        if replacement_identity != base_identity:
            raise ExternalEvaluatorIdentityError("replacement identity drifted from the base evaluation")
        selected[replacement.task_id] = replacement
    ordered = tuple(selected[task_id] for task_id in task_order)
    adjudication = ExternalEvaluationAdjudication(
        adjudication_id=adjudication_id,
        task_order=tuple(task_order),
        selected_evaluations=ordered,
        source_result_sha256=tuple(result.canonical_sha256() for result in ordered),
    )
    _write_create_once(output_path, adjudication.canonical_json() + "\n")
    return adjudication
