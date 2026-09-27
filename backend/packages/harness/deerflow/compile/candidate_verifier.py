"""Candidate 冻结前的完整交付验证。"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Protocol

from deerflow.compile.agent_workflow_schemas import (
    AgentBuildNodeInput,
    AgentWorkflowContractError,
    AgentWorkflowRemainingBudget,
    SubmitCandidateRequest,
    SubmitCandidateResponse,
)
from deerflow.compile.external_evaluator import FunctionalOracleSpec
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.operations import _classify_artifact
from deerflow.compile.schemas import CompileSession
from deerflow.tools.bound_compile_tools import _run_system_oracle_bash_impl

PREFREEZE_RESPONSE_SCHEMA_VERSION = "agent-workflow-prefreeze-response-v1"
MAX_REJECTION_PATHS = 12
_COMPILED_ARTIFACT_TYPES = frozenset({"executable", "shared_library", "static_library", "object"})


class CandidateVerificationCode(StrEnum):
    DELIVERY_UNAVAILABLE = "delivery_unavailable"
    DELIVERY_INVALID = "delivery_invalid"
    DELIVERY_ZERO_BYTE = "delivery_zero_byte"
    UNDECLARED_COMPILED_ARTIFACT = "undeclared_compiled_artifact"
    TARGET_MAPPING_INVALID = "target_mapping_invalid"
    TARGET_PATH_MISMATCH = "target_path_mismatch"
    FUNCTIONAL_ORACLE_FAILED = "functional_oracle_failed"


@dataclass(frozen=True)
class DeliveryEntry:
    relative_path: str
    artifact_type: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class DeliverySnapshot:
    entries: tuple[DeliveryEntry, ...]
    invalid_paths: tuple[str, ...] = ()

    @property
    def files_by_path(self) -> dict[str, DeliveryEntry]:
        return {entry.relative_path: entry for entry in self.entries}


@dataclass(frozen=True)
class FunctionalCheckEvidence:
    oracle_ref: str
    passed: bool
    command_id: str
    exit_code: int | None
    timed_out: bool
    stdout_sha256: str
    stderr_sha256: str


class FunctionalCheckRunner(Protocol):
    def run(
        self,
        *,
        spec: FunctionalOracleSpec,
        session: CompileSession,
        manager: CompileSessionManager,
    ) -> FunctionalCheckEvidence: ...


class SystemOwnedFunctionalCheckRunner:
    """使用与 external evaluator 相同的系统权限执行受信 oracle。"""

    def run(
        self,
        *,
        spec: FunctionalOracleSpec,
        session: CompileSession,
        manager: CompileSessionManager,
    ) -> FunctionalCheckEvidence:
        spec.validate()
        result, _message, record = _run_system_oracle_bash_impl(
            session=session,
            command=spec.shell_command(),
            timeout_seconds=spec.timeout_seconds,
            workdir=spec.workdir,
            command_role="smoke",
        )
        current = manager.load_session(session.session_id, session.thread_id)
        session.__dict__.update(current.__dict__)
        return FunctionalCheckEvidence(
            oracle_ref=spec.oracle_ref,
            passed=record.completed_at is not None and not record.timed_out and record.exit_code in spec.acceptable_exit_codes,
            command_id=record.command_id,
            exit_code=record.exit_code,
            timed_out=record.timed_out,
            stdout_sha256=hashlib.sha256(result.stdout.encode()).hexdigest(),
            stderr_sha256=hashlib.sha256(result.stderr.encode()).hexdigest(),
        )


@dataclass(frozen=True)
class CandidateVerificationFinding:
    code: str
    paths: tuple[str, ...] = ()
    total_count: int = 0
    expected: tuple[str, ...] = ()
    actual: tuple[str, ...] = ()
    oracle: FunctionalCheckEvidence | None = None

    def validate(self) -> None:
        if not self.code or self.total_count < 0:
            raise AgentWorkflowContractError("candidate verification finding is invalid")
        if any(len(values) > MAX_REJECTION_PATHS for values in (self.paths, self.expected, self.actual)):
            raise AgentWorkflowContractError("candidate verification finding is not bounded")
        if self.total_count < len(self.paths):
            raise AgentWorkflowContractError("candidate verification total_count is smaller than paths")
        for values in (self.paths, self.expected, self.actual):
            if tuple(sorted(set(values))) != values:
                raise AgentWorkflowContractError("candidate verification values must be sorted and unique")

    def as_payload(self) -> dict[str, object]:
        self.validate()
        payload: dict[str, object] = {
            "code": self.code,
            "paths": list(self.paths),
            "total_count": self.total_count,
            "truncated": self.total_count > len(self.paths),
        }
        if self.expected:
            payload["expected"] = list(self.expected)
        if self.actual:
            payload["actual"] = list(self.actual)
        if self.oracle is not None:
            payload["oracle"] = asdict(self.oracle)
        return payload


@dataclass(frozen=True)
class CandidateVerificationResult:
    delivery: DeliverySnapshot
    findings: tuple[CandidateVerificationFinding, ...]

    @property
    def passed(self) -> bool:
        return not self.findings

    def evidence_payload(self) -> dict[str, object]:
        compiled_count = sum(entry.artifact_type in _COMPILED_ARTIFACT_TYPES for entry in self.delivery.entries)
        return {
            "passed": self.passed,
            "delivery_file_count": len(self.delivery.entries),
            "compiled_artifact_count": compiled_count,
            "invalid_path_count": len(self.delivery.invalid_paths),
            "findings": [finding.as_payload() for finding in self.findings],
        }


@dataclass(frozen=True)
class PrefreezeSubmitCandidateResponse:
    accepted: bool
    remaining_budget: AgentWorkflowRemainingBudget
    submission_id: str | None = None
    rejection_codes: tuple[str, ...] = ()
    rejection_details: tuple[CandidateVerificationFinding, ...] = ()
    candidate_record_sha256: str | None = None
    terminal_for_agent: bool = False
    schema_version: str = PREFREEZE_RESPONSE_SCHEMA_VERSION

    @classmethod
    def from_base(
        cls,
        response: SubmitCandidateResponse,
        findings: tuple[CandidateVerificationFinding, ...] = (),
    ) -> PrefreezeSubmitCandidateResponse:
        return cls(
            accepted=response.accepted,
            remaining_budget=response.remaining_budget,
            submission_id=response.submission_id,
            rejection_codes=response.rejection_codes,
            rejection_details=findings,
            candidate_record_sha256=response.candidate_record_sha256,
            terminal_for_agent=response.terminal_for_agent,
        )

    def canonical_json(self) -> str:
        if self.schema_version != PREFREEZE_RESPONSE_SCHEMA_VERSION:
            raise AgentWorkflowContractError("pre-freeze response schema version is invalid")
        self.remaining_budget.validate()
        for finding in self.rejection_details:
            finding.validate()
        if self.accepted:
            if self.submission_id is None or self.candidate_record_sha256 is None or self.rejection_codes or self.rejection_details or not self.terminal_for_agent:
                raise AgentWorkflowContractError("accepted pre-freeze response is inconsistent")
        elif self.submission_id is not None or self.candidate_record_sha256 is not None or not self.rejection_codes:
            raise AgentWorkflowContractError("rejected pre-freeze response is inconsistent")
        payload = {
            "accepted": self.accepted,
            "candidate_record_sha256": self.candidate_record_sha256,
            "rejection_codes": list(self.rejection_codes),
            "rejection_details": [finding.as_payload() for finding in self.rejection_details],
            "remaining_budget": asdict(self.remaining_budget),
            "schema_version": self.schema_version,
            "submission_id": self.submission_id,
            "terminal_for_agent": self.terminal_for_agent,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _bounded_paths(paths: set[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(paths)))[:MAX_REJECTION_PATHS]


def _bounded_values(values: set[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))[:MAX_REJECTION_PATHS]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def scan_delivery(
    artifacts_dir: Path,
    *,
    classifier: Callable[[Path], str | None] = _classify_artifact,
) -> DeliverySnapshot:
    """扫描完整 delivery；目录仅用于遍历，符号链接和特殊文件均拒绝。"""

    try:
        if artifacts_dir.is_symlink() or not artifacts_dir.is_dir():
            return DeliverySnapshot(entries=(), invalid_paths=(".",))
    except OSError:
        return DeliverySnapshot(entries=(), invalid_paths=(".",))

    entries: list[DeliveryEntry] = []
    invalid_paths: set[str] = set()
    pending = [artifacts_dir]
    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as scanner:
                children = sorted(scanner, key=lambda entry: entry.name)
        except OSError:
            invalid_paths.add(current.relative_to(artifacts_dir).as_posix() or ".")
            continue
        for child in children:
            path = Path(child.path)
            relative_path = path.relative_to(artifacts_dir).as_posix()
            try:
                if child.is_symlink():
                    invalid_paths.add(relative_path)
                elif child.is_dir(follow_symlinks=False):
                    pending.append(path)
                elif child.is_file(follow_symlinks=False):
                    size_bytes = child.stat(follow_symlinks=False).st_size
                    artifact_type = classifier(path)
                    if artifact_type is None:
                        invalid_paths.add(relative_path)
                        continue
                    entries.append(
                        DeliveryEntry(
                            relative_path=relative_path,
                            artifact_type=artifact_type,
                            size_bytes=size_bytes,
                            sha256=_sha256_file(path),
                        )
                    )
                else:
                    invalid_paths.add(relative_path)
            except OSError:
                invalid_paths.add(relative_path)
    return DeliverySnapshot(
        entries=tuple(sorted(entries, key=lambda entry: entry.relative_path)),
        invalid_paths=tuple(sorted(invalid_paths)),
    )


class CandidateVerifier:
    def __init__(
        self,
        *,
        oracle_spec: FunctionalOracleSpec,
        functional_runner: FunctionalCheckRunner | None = None,
        classifier: Callable[[Path], str | None] = _classify_artifact,
    ):
        oracle_spec.validate()
        self.oracle_spec = oracle_spec
        self.functional_runner = functional_runner or SystemOwnedFunctionalCheckRunner()
        self.classifier = classifier

    def verify(
        self,
        *,
        request: SubmitCandidateRequest,
        node_input: AgentBuildNodeInput,
        session: CompileSession,
        manager: CompileSessionManager,
    ) -> CandidateVerificationResult:
        delivery = scan_delivery(Path(session.leadagent_artifacts_dir), classifier=self.classifier)
        files_by_path = delivery.files_by_path
        findings: list[CandidateVerificationFinding] = []

        if delivery.invalid_paths == (".",):
            findings.append(CandidateVerificationFinding(code=CandidateVerificationCode.DELIVERY_UNAVAILABLE.value, paths=(".",), total_count=1))
        elif delivery.invalid_paths:
            findings.append(
                CandidateVerificationFinding(
                    code=CandidateVerificationCode.DELIVERY_INVALID.value,
                    paths=_bounded_paths(delivery.invalid_paths),
                    total_count=len(delivery.invalid_paths),
                )
            )

        zero_byte_paths = {entry.relative_path for entry in delivery.entries if entry.size_bytes == 0}
        if zero_byte_paths:
            findings.append(
                CandidateVerificationFinding(
                    code=CandidateVerificationCode.DELIVERY_ZERO_BYTE.value,
                    paths=_bounded_paths(zero_byte_paths),
                    total_count=len(zero_byte_paths),
                )
            )

        declared_paths = set(request.artifact_paths)
        undeclared_compiled = {entry.relative_path for entry in delivery.entries if entry.artifact_type in _COMPILED_ARTIFACT_TYPES and entry.relative_path not in declared_paths}
        if undeclared_compiled:
            findings.append(
                CandidateVerificationFinding(
                    code=CandidateVerificationCode.UNDECLARED_COMPILED_ARTIFACT.value,
                    paths=_bounded_paths(undeclared_compiled),
                    total_count=len(undeclared_compiled),
                )
            )

        expected_target_ids = (node_input.target_contract.target_id,)
        actual_target_ids = tuple(sorted(request.target_mapping))
        if actual_target_ids != expected_target_ids:
            findings.append(
                CandidateVerificationFinding(
                    code=CandidateVerificationCode.TARGET_MAPPING_INVALID.value,
                    expected=expected_target_ids,
                    actual=_bounded_values(actual_target_ids),
                )
            )
        else:
            target_path = request.target_mapping[node_input.target_contract.target_id]
            target_entry = files_by_path.get(target_path)
            if target_entry is None or target_path not in declared_paths or target_entry.artifact_type not in node_input.target_contract.artifact_types:
                findings.append(
                    CandidateVerificationFinding(
                        code=CandidateVerificationCode.TARGET_MAPPING_INVALID.value,
                        paths=(target_path,),
                        total_count=1,
                        expected=_bounded_values(node_input.target_contract.artifact_types),
                        actual=(() if target_entry is None else (target_entry.artifact_type,)),
                    )
                )
            elif not any(PurePosixPath(target_path).match(pattern) for pattern in node_input.target_contract.artifact_path_patterns):
                findings.append(
                    CandidateVerificationFinding(
                        code=CandidateVerificationCode.TARGET_PATH_MISMATCH.value,
                        paths=(target_path,),
                        total_count=1,
                        expected=_bounded_values(node_input.target_contract.artifact_path_patterns),
                    )
                )

        if not findings:
            oracle = self.functional_runner.run(
                spec=self.oracle_spec,
                session=session,
                manager=manager,
            )
            if not oracle.passed:
                findings.append(
                    CandidateVerificationFinding(
                        code=CandidateVerificationCode.FUNCTIONAL_ORACLE_FAILED.value,
                        oracle=oracle,
                    )
                )

        return CandidateVerificationResult(delivery=delivery, findings=tuple(findings))
