from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any

AGENT_WORKFLOW_NODE_SCHEMA_VERSION = "agent-workflow-node-v1"
AGENT_WORKFLOW_NODE_ORCHESTRATION_MODE = "agent_workflow_node_v1"

_BUILD_SYSTEMS = frozenset({"cmake", "make", "autotools"})
_COMPILED_ARTIFACT_TYPES = frozenset({"executable", "shared_library", "static_library", "object"})
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HEX_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


class AgentWorkflowContractError(ValueError):
    """节点输入或候选提交不满足冻结合同。"""


def _require_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER_PATTERN.fullmatch(value):
        raise AgentWorkflowContractError(f"{field_name} must be a stable non-empty identifier")


def _require_sha256(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not _HEX_DIGEST_PATTERN.fullmatch(value):
        raise AgentWorkflowContractError(f"{field_name} must be a lowercase SHA-256 digest")


def _require_positive(value: int, field_name: str) -> None:
    if type(value) is not int or value <= 0:
        raise AgentWorkflowContractError(f"{field_name} must be a positive integer")


def _require_unique_non_empty(values: tuple[str, ...], field_name: str) -> None:
    if not isinstance(values, tuple) or not values or any(not isinstance(value, str) or not value for value in values):
        raise AgentWorkflowContractError(f"{field_name} must contain non-empty values")
    if len(set(values)) != len(values):
        raise AgentWorkflowContractError(f"{field_name} must not contain duplicates")


def _require_relative_artifact_path(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise AgentWorkflowContractError(f"{field_name} must be a normalized relative POSIX path")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or value != path.as_posix() or any(part in {"", ".", ".."} for part in path.parts):
        raise AgentWorkflowContractError(f"{field_name} must be a normalized relative POSIX path")


def _canonical_payload(value: Any) -> str:
    try:
        return json.dumps(_json_data(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise AgentWorkflowContractError("contract payload must be canonical JSON data") from exc


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise AgentWorkflowContractError("contract JSON object keys must be strings")
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _json_data(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__") and not isinstance(value, type):
        return {field_name: _json_data(getattr(value, field_name)) for field_name in value.__dataclass_fields__}
    if isinstance(value, Mapping):
        return {key: _json_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_data(item) for item in value]
    return value


@dataclass(frozen=True)
class AgentWorkflowBudget:
    max_model_requests: int
    max_recorded_tokens: int
    max_agent_steps: int
    max_tool_calls: int
    max_commands: int
    node_timeout_seconds: int
    command_timeout_seconds: int
    evaluator_timeout_seconds: int
    replay_timeout_seconds: int
    cleanup_timeout_seconds: int

    def validate(self) -> None:
        for field_name, value in asdict(self).items():
            _require_positive(value, field_name)


@dataclass(frozen=True)
class AgentWorkflowEnvironmentIdentity:
    image_id: str
    parallel_jobs: int
    network_policy: str

    def validate(self) -> None:
        if not isinstance(self.image_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", self.image_id):
            raise AgentWorkflowContractError("environment.image_id must be a complete image digest")
        _require_positive(self.parallel_jobs, "environment.parallel_jobs")
        _require_identifier(self.network_policy, "environment.network_policy")


@dataclass(frozen=True)
class AgentWorkflowTargetContract:
    target_id: str
    artifact_types: tuple[str, ...]
    artifact_path_patterns: tuple[str, ...]
    functional_oracle_ref: str

    def validate(self) -> None:
        _require_identifier(self.target_id, "target_contract.target_id")
        _require_unique_non_empty(self.artifact_types, "target_contract.artifact_types")
        unsupported = set(self.artifact_types) - _COMPILED_ARTIFACT_TYPES
        if unsupported:
            raise AgentWorkflowContractError(f"target_contract.artifact_types contains unsupported values: {sorted(unsupported)}")
        _require_unique_non_empty(self.artifact_path_patterns, "target_contract.artifact_path_patterns")
        for pattern in self.artifact_path_patterns:
            _require_relative_artifact_path(pattern, "target_contract.artifact_path_patterns")
        _require_identifier(self.functional_oracle_ref, "target_contract.functional_oracle_ref")


@dataclass(frozen=True)
class AgentWorkflowExperimentIdentity:
    manifest_sha256: str
    protocol_sha256: str
    runner_sha256: str
    orchestration_mode: str = AGENT_WORKFLOW_NODE_ORCHESTRATION_MODE

    def validate(self) -> None:
        _require_sha256(self.manifest_sha256, "experiment_identity.manifest_sha256")
        _require_sha256(self.protocol_sha256, "experiment_identity.protocol_sha256")
        _require_sha256(self.runner_sha256, "experiment_identity.runner_sha256")
        if self.orchestration_mode != AGENT_WORKFLOW_NODE_ORCHESTRATION_MODE:
            raise AgentWorkflowContractError(f"experiment_identity.orchestration_mode must be {AGENT_WORKFLOW_NODE_ORCHESTRATION_MODE!r}")


@dataclass(frozen=True)
class AgentBuildNodeInput:
    task_id: str
    attempt_id: str
    session_id: str
    repository_url: str
    commit_sha: str
    build_system_candidates: tuple[str, ...]
    target_contract: AgentWorkflowTargetContract
    operation_policy_ref: str
    environment: AgentWorkflowEnvironmentIdentity
    budget: AgentWorkflowBudget
    experiment_identity: AgentWorkflowExperimentIdentity
    initial_observation: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    source_snapshot_sha256: str | None = None
    schema_version: str = AGENT_WORKFLOW_NODE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "initial_observation", _freeze_json(self.initial_observation))

    def validate(self) -> None:
        if self.schema_version != AGENT_WORKFLOW_NODE_SCHEMA_VERSION:
            raise AgentWorkflowContractError(f"schema_version must be {AGENT_WORKFLOW_NODE_SCHEMA_VERSION!r}")
        _require_identifier(self.task_id, "task_id")
        _require_identifier(self.attempt_id, "attempt_id")
        _require_identifier(self.session_id, "session_id")
        if not isinstance(self.repository_url, str) or not self.repository_url or any(character.isspace() for character in self.repository_url):
            raise AgentWorkflowContractError("repository_url must be non-empty and contain no whitespace")
        if not isinstance(self.commit_sha, str) or not _COMMIT_PATTERN.fullmatch(self.commit_sha):
            raise AgentWorkflowContractError("commit_sha must be a lowercase 40- or 64-character hexadecimal digest")
        if self.source_snapshot_sha256 is not None:
            _require_sha256(self.source_snapshot_sha256, "source_snapshot_sha256")
        _require_unique_non_empty(self.build_system_candidates, "build_system_candidates")
        unsupported = set(self.build_system_candidates) - _BUILD_SYSTEMS
        if unsupported:
            raise AgentWorkflowContractError(f"build_system_candidates contains unsupported values: {sorted(unsupported)}")
        _require_identifier(self.operation_policy_ref, "operation_policy_ref")
        self.target_contract.validate()
        self.environment.validate()
        self.budget.validate()
        self.experiment_identity.validate()
        _canonical_payload(self.initial_observation)

    def canonical_json(self) -> str:
        self.validate()
        return _canonical_payload(self)

    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SubmitCandidateRequest:
    candidate_id: str
    build_system: str
    supporting_command_ids: tuple[str, ...]
    artifact_paths: tuple[str, ...]
    target_mapping: Mapping[str, str]
    recipe_command_ids: tuple[str, ...]
    agent_summary: str | None = None
    known_limitations: tuple[str, ...] = ()
    schema_version: str = AGENT_WORKFLOW_NODE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_mapping", _freeze_json(self.target_mapping))

    def validate(self) -> None:
        if self.schema_version != AGENT_WORKFLOW_NODE_SCHEMA_VERSION:
            raise AgentWorkflowContractError(f"schema_version must be {AGENT_WORKFLOW_NODE_SCHEMA_VERSION!r}")
        _require_identifier(self.candidate_id, "candidate_id")
        if self.build_system not in _BUILD_SYSTEMS:
            raise AgentWorkflowContractError(f"build_system must be one of {sorted(_BUILD_SYSTEMS)}")
        _require_unique_non_empty(self.supporting_command_ids, "supporting_command_ids")
        _require_unique_non_empty(self.recipe_command_ids, "recipe_command_ids")
        if not set(self.supporting_command_ids).issubset(self.recipe_command_ids):
            raise AgentWorkflowContractError("supporting_command_ids must be included in recipe_command_ids")
        _require_unique_non_empty(self.artifact_paths, "artifact_paths")
        for path in self.artifact_paths:
            _require_relative_artifact_path(path, "artifact_paths")
        if not self.target_mapping:
            raise AgentWorkflowContractError("target_mapping must not be empty")
        unknown_paths = set(self.target_mapping.values()) - set(self.artifact_paths)
        if unknown_paths:
            raise AgentWorkflowContractError(f"target_mapping references undeclared artifact paths: {sorted(unknown_paths)}")
        for target_id, path in self.target_mapping.items():
            _require_identifier(target_id, "target_mapping key")
            _require_relative_artifact_path(path, "target_mapping value")
        if any(not isinstance(limitation, str) or not limitation.strip() for limitation in self.known_limitations):
            raise AgentWorkflowContractError("known_limitations must not contain empty values")
        if self.agent_summary is not None and not isinstance(self.agent_summary, str):
            raise AgentWorkflowContractError("agent_summary must be a string or null")

    def canonical_json(self) -> str:
        self.validate()
        return _canonical_payload(self)

    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AgentWorkflowRemainingBudget:
    model_requests: int
    recorded_tokens: int
    agent_steps: int
    tool_calls: int
    commands: int
    node_seconds: float

    def validate(self) -> None:
        for field_name in ("model_requests", "recorded_tokens", "agent_steps", "tool_calls", "commands"):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise AgentWorkflowContractError(f"remaining_budget.{field_name} must be a non-negative integer")
        if not isinstance(self.node_seconds, (int, float)) or isinstance(self.node_seconds, bool) or self.node_seconds < 0:
            raise AgentWorkflowContractError("remaining_budget.node_seconds must be a non-negative number")


@dataclass(frozen=True)
class AgentWorkflowUsage:
    model_requests: int
    recorded_tokens: int
    agent_steps: int
    tool_calls: int
    commands: int

    def validate(self) -> None:
        for field_name in ("model_requests", "recorded_tokens", "agent_steps", "tool_calls", "commands"):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise AgentWorkflowContractError(f"usage.{field_name} must be a non-negative integer")


@dataclass(frozen=True)
class SubmitCandidateResponse:
    accepted: bool
    remaining_budget: AgentWorkflowRemainingBudget
    submission_id: str | None = None
    rejection_codes: tuple[str, ...] = ()
    candidate_record_sha256: str | None = None
    terminal_for_agent: bool = False
    schema_version: str = AGENT_WORKFLOW_NODE_SCHEMA_VERSION

    def validate(self) -> None:
        if type(self.accepted) is not bool or type(self.terminal_for_agent) is not bool:
            raise AgentWorkflowContractError("submission response flags must be booleans")
        if self.schema_version != AGENT_WORKFLOW_NODE_SCHEMA_VERSION:
            raise AgentWorkflowContractError(f"schema_version must be {AGENT_WORKFLOW_NODE_SCHEMA_VERSION!r}")
        self.remaining_budget.validate()
        if self.accepted:
            if self.submission_id is None or self.candidate_record_sha256 is None:
                raise AgentWorkflowContractError("accepted submission must include submission identity")
            _require_identifier(self.submission_id, "submission_id")
            _require_sha256(self.candidate_record_sha256, "candidate_record_sha256")
            if self.rejection_codes or not self.terminal_for_agent:
                raise AgentWorkflowContractError("accepted submission must be terminal and contain no rejection codes")
            return
        if self.submission_id is not None or self.candidate_record_sha256 is not None:
            raise AgentWorkflowContractError("rejected submission must not include submission identity")
        _require_unique_non_empty(self.rejection_codes, "rejection_codes")
        for code in self.rejection_codes:
            _require_identifier(code, "rejection_codes")

    def canonical_json(self) -> str:
        self.validate()
        return _canonical_payload(self)

    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AgentBuildNodeResult:
    node_status: str
    candidate_generated_observed: bool
    candidate_submitted: bool
    usage: AgentWorkflowUsage
    wall_clock_ms: int
    evidence_head_sha256: str
    session_terminal_status: str
    submission_id: str | None = None
    candidate_record_sha256: str | None = None
    budget_terminal_reason: str | None = None
    primary_failure: str | None = None
    secondary_failures: tuple[str, ...] = ()
    schema_version: str = AGENT_WORKFLOW_NODE_SCHEMA_VERSION

    def validate(self) -> None:
        if self.schema_version != AGENT_WORKFLOW_NODE_SCHEMA_VERSION:
            raise AgentWorkflowContractError(f"schema_version must be {AGENT_WORKFLOW_NODE_SCHEMA_VERSION!r}")
        if self.node_status not in {"submitted", "no_submission", "failed", "cancelled"}:
            raise AgentWorkflowContractError("node_status is unsupported")
        if type(self.candidate_generated_observed) is not bool or type(self.candidate_submitted) is not bool:
            raise AgentWorkflowContractError("candidate result flags must be booleans")
        if self.node_status == "submitted" and not self.candidate_submitted:
            raise AgentWorkflowContractError("submitted node status requires a submitted candidate")
        if self.node_status != "submitted" and self.candidate_submitted:
            raise AgentWorkflowContractError("only submitted node status may contain a submitted candidate")
        if self.candidate_submitted and not self.candidate_generated_observed:
            raise AgentWorkflowContractError("submitted candidate must also be observed as generated")
        self.usage.validate()
        if type(self.wall_clock_ms) is not int or self.wall_clock_ms < 0:
            raise AgentWorkflowContractError("wall_clock_ms must be a non-negative integer")
        _require_sha256(self.evidence_head_sha256, "evidence_head_sha256")
        _require_identifier(self.session_terminal_status, "session_terminal_status")
        if self.candidate_submitted:
            if self.submission_id is None or self.candidate_record_sha256 is None:
                raise AgentWorkflowContractError("submitted result must include submission identity")
            _require_identifier(self.submission_id, "submission_id")
            _require_sha256(self.candidate_record_sha256, "candidate_record_sha256")
        elif self.submission_id is not None or self.candidate_record_sha256 is not None:
            raise AgentWorkflowContractError("unsubmitted result must not include submission identity")
        for field_name in ("budget_terminal_reason", "primary_failure"):
            value = getattr(self, field_name)
            if value is not None:
                _require_identifier(value, field_name)
        if len(set(self.secondary_failures)) != len(self.secondary_failures):
            raise AgentWorkflowContractError("secondary_failures must not contain duplicates")
        for failure in self.secondary_failures:
            _require_identifier(failure, "secondary_failures")

    def canonical_json(self) -> str:
        self.validate()
        return _canonical_payload(self)

    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
