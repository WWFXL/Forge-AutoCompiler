from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from threading import Lock, RLock

from deerflow.compile.agent_workflow_schemas import (
    AgentWorkflowBudget,
    AgentWorkflowContractError,
    AgentWorkflowRemainingBudget,
    SubmitCandidateRequest,
    SubmitCandidateResponse,
)


class AgentWorkflowNodeStatus(StrEnum):
    REGISTERED = "registered"
    READY = "ready"
    RUNNING = "running"
    CANDIDATE_SUBMITTED = "candidate_submitted"
    NO_SUBMISSION = "no_submission"
    NODE_FAILED = "node_failed"
    EVALUATING = "evaluating"
    EVALUATED = "evaluated"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AgentWorkflowTerminationReason(StrEnum):
    EVALUATION_COMPLETED = "evaluation_completed"
    NO_SUBMISSION = "no_submission"
    NODE_FAILED = "node_failed"
    CANCELLED = "cancelled"
    BUDGET_EXHAUSTED = "budget_exhausted"


class InvalidAgentWorkflowTransition(RuntimeError):
    """状态转换不属于冻结的节点状态机。"""


class AgentWorkflowBudgetExceeded(RuntimeError):
    def __init__(self, reason: str, snapshot: AgentWorkflowBudgetSnapshot):
        self.reason = reason
        self.snapshot = snapshot
        super().__init__(f"Agent workflow budget exhausted: {reason}")


class SubmitCandidateRejectionCode(StrEnum):
    INVALID_CONTRACT = "invalid_contract"
    NODE_NOT_RUNNING = "node_not_running"
    CANDIDATE_ALREADY_FROZEN = "candidate_already_frozen"
    SESSION_INACTIVE = "session_inactive"
    COMMAND_MISSING = "command_missing"
    COMMAND_AMBIGUOUS = "command_ambiguous"
    COMMAND_NOT_COMPLETED = "command_not_completed"
    COMMAND_NOT_SUCCESSFUL = "command_not_successful"
    COMMAND_ROLE_INVALID = "command_role_invalid"
    COMMAND_ORDER_INVALID = "command_order_invalid"
    BUILD_SYSTEM_MISMATCH = "build_system_mismatch"
    ARTIFACT_MISSING = "artifact_missing"
    ARTIFACT_NOT_REGULAR = "artifact_not_regular"
    ARTIFACT_SYMLINK = "artifact_symlink"
    CANDIDATE_PERSISTENCE_FAILED = "candidate_persistence_failed"


@dataclass(frozen=True)
class AgentWorkflowTransition:
    previous: AgentWorkflowNodeStatus
    current: AgentWorkflowNodeStatus


_ALLOWED_TRANSITIONS: dict[AgentWorkflowNodeStatus, frozenset[AgentWorkflowNodeStatus]] = {
    AgentWorkflowNodeStatus.REGISTERED: frozenset({AgentWorkflowNodeStatus.READY, AgentWorkflowNodeStatus.NODE_FAILED, AgentWorkflowNodeStatus.FINALIZING}),
    AgentWorkflowNodeStatus.READY: frozenset({AgentWorkflowNodeStatus.RUNNING, AgentWorkflowNodeStatus.NODE_FAILED, AgentWorkflowNodeStatus.FINALIZING}),
    AgentWorkflowNodeStatus.RUNNING: frozenset(
        {
            AgentWorkflowNodeStatus.CANDIDATE_SUBMITTED,
            AgentWorkflowNodeStatus.NO_SUBMISSION,
            AgentWorkflowNodeStatus.NODE_FAILED,
            AgentWorkflowNodeStatus.FINALIZING,
        }
    ),
    AgentWorkflowNodeStatus.CANDIDATE_SUBMITTED: frozenset({AgentWorkflowNodeStatus.EVALUATING, AgentWorkflowNodeStatus.NODE_FAILED, AgentWorkflowNodeStatus.FINALIZING}),
    AgentWorkflowNodeStatus.NO_SUBMISSION: frozenset({AgentWorkflowNodeStatus.FINALIZING}),
    AgentWorkflowNodeStatus.NODE_FAILED: frozenset({AgentWorkflowNodeStatus.FINALIZING}),
    AgentWorkflowNodeStatus.EVALUATING: frozenset({AgentWorkflowNodeStatus.EVALUATED, AgentWorkflowNodeStatus.NODE_FAILED, AgentWorkflowNodeStatus.FINALIZING}),
    AgentWorkflowNodeStatus.EVALUATED: frozenset({AgentWorkflowNodeStatus.FINALIZING}),
    AgentWorkflowNodeStatus.FINALIZING: frozenset({AgentWorkflowNodeStatus.COMPLETED, AgentWorkflowNodeStatus.CANCELLED}),
    AgentWorkflowNodeStatus.COMPLETED: frozenset(),
    AgentWorkflowNodeStatus.CANCELLED: frozenset(),
}


@dataclass
class AgentWorkflowStateMachine:
    status: AgentWorkflowNodeStatus = AgentWorkflowNodeStatus.REGISTERED
    termination_reason: AgentWorkflowTerminationReason | None = None
    transitions: list[AgentWorkflowTransition] = field(default_factory=list)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False, compare=False)

    def transition(self, target: AgentWorkflowNodeStatus) -> AgentWorkflowTransition:
        with self._lock:
            allowed = _ALLOWED_TRANSITIONS[self.status]
            if target not in allowed:
                raise InvalidAgentWorkflowTransition(f"Cannot transition agent workflow node from {self.status.value!r} to {target.value!r}")
            if target in {AgentWorkflowNodeStatus.COMPLETED, AgentWorkflowNodeStatus.CANCELLED}:
                if self.termination_reason is None:
                    raise InvalidAgentWorkflowTransition("Cannot enter a terminal state without a terminal reason")
                cancelled = self.termination_reason is AgentWorkflowTerminationReason.CANCELLED
                if (target is AgentWorkflowNodeStatus.CANCELLED) is not cancelled:
                    raise InvalidAgentWorkflowTransition("Terminal state does not match the first termination reason")
            transition = AgentWorkflowTransition(previous=self.status, current=target)
            self.status = target
            self.transitions.append(transition)
            return transition

    def request_termination(self, reason: AgentWorkflowTerminationReason) -> bool:
        with self._lock:
            if self.status in {AgentWorkflowNodeStatus.COMPLETED, AgentWorkflowNodeStatus.CANCELLED}:
                raise InvalidAgentWorkflowTransition("Cannot write a termination reason after the node is terminal")
            if self.termination_reason is not None:
                return False
            self.termination_reason = reason
            return True

    def begin_finalization(self, reason: AgentWorkflowTerminationReason) -> AgentWorkflowTransition:
        with self._lock:
            if AgentWorkflowNodeStatus.FINALIZING not in _ALLOWED_TRANSITIONS[self.status]:
                raise InvalidAgentWorkflowTransition(f"Cannot transition agent workflow node from {self.status.value!r} to 'finalizing'")
            self.request_termination(reason)
            return self.transition(AgentWorkflowNodeStatus.FINALIZING)

    def finish_finalization(self) -> AgentWorkflowTransition:
        with self._lock:
            if self.termination_reason is None:
                raise InvalidAgentWorkflowTransition("Cannot finish finalization without a terminal reason")
            target = AgentWorkflowNodeStatus.CANCELLED if self.termination_reason is AgentWorkflowTerminationReason.CANCELLED else AgentWorkflowNodeStatus.COMPLETED
            return self.transition(target)


@dataclass(frozen=True)
class AgentWorkflowBudgetSnapshot:
    model_requests: int = 0
    recorded_tokens: int = 0
    agent_steps: int = 0
    tool_calls: int = 0
    commands: int = 0
    elapsed_seconds: float = 0.0


@dataclass
class AgentWorkflowBudgetTracker:
    limits: AgentWorkflowBudget
    _snapshot: AgentWorkflowBudgetSnapshot = field(default_factory=AgentWorkflowBudgetSnapshot)

    def __post_init__(self) -> None:
        self.limits.validate()

    def snapshot(self) -> AgentWorkflowBudgetSnapshot:
        return self._snapshot

    def remaining(self) -> AgentWorkflowRemainingBudget:
        return AgentWorkflowRemainingBudget(
            model_requests=self.limits.max_model_requests - self._snapshot.model_requests,
            recorded_tokens=self.limits.max_recorded_tokens - self._snapshot.recorded_tokens,
            agent_steps=self.limits.max_agent_steps - self._snapshot.agent_steps,
            tool_calls=self.limits.max_tool_calls - self._snapshot.tool_calls,
            commands=self.limits.max_commands - self._snapshot.commands,
            node_seconds=max(0.0, self.limits.node_timeout_seconds - self._snapshot.elapsed_seconds),
        )

    def consume(
        self,
        *,
        model_requests: int = 0,
        recorded_tokens: int = 0,
        agent_steps: int = 0,
        tool_calls: int = 0,
        commands: int = 0,
    ) -> AgentWorkflowBudgetSnapshot:
        increments = {
            "model_requests": model_requests,
            "recorded_tokens": recorded_tokens,
            "agent_steps": agent_steps,
            "tool_calls": tool_calls,
            "commands": commands,
        }
        if any(type(value) is not int or value < 0 for value in increments.values()):
            raise ValueError("Budget increments must be non-negative integers")
        candidate = AgentWorkflowBudgetSnapshot(
            model_requests=self._snapshot.model_requests + model_requests,
            recorded_tokens=self._snapshot.recorded_tokens + recorded_tokens,
            agent_steps=self._snapshot.agent_steps + agent_steps,
            tool_calls=self._snapshot.tool_calls + tool_calls,
            commands=self._snapshot.commands + commands,
            elapsed_seconds=self._snapshot.elapsed_seconds,
        )
        ceilings = {
            "model_requests": self.limits.max_model_requests,
            "recorded_tokens": self.limits.max_recorded_tokens,
            "agent_steps": self.limits.max_agent_steps,
            "tool_calls": self.limits.max_tool_calls,
            "commands": self.limits.max_commands,
        }
        for field_name, ceiling in ceilings.items():
            if getattr(candidate, field_name) > ceiling:
                raise AgentWorkflowBudgetExceeded(field_name, self._snapshot)
        self._snapshot = candidate
        return candidate

    def observe_elapsed(self, elapsed_seconds: float) -> AgentWorkflowBudgetSnapshot:
        if not isinstance(elapsed_seconds, (int, float)) or isinstance(elapsed_seconds, bool) or elapsed_seconds < 0:
            raise ValueError("elapsed_seconds must be a non-negative number")
        if elapsed_seconds > self.limits.node_timeout_seconds:
            raise AgentWorkflowBudgetExceeded("node_timeout_seconds", self._snapshot)
        if elapsed_seconds < self._snapshot.elapsed_seconds:
            raise ValueError("elapsed_seconds must be monotonic")
        self._snapshot = AgentWorkflowBudgetSnapshot(
            model_requests=self._snapshot.model_requests,
            recorded_tokens=self._snapshot.recorded_tokens,
            agent_steps=self._snapshot.agent_steps,
            tool_calls=self._snapshot.tool_calls,
            commands=self._snapshot.commands,
            elapsed_seconds=float(elapsed_seconds),
        )
        return self._snapshot


@dataclass(frozen=True)
class FrozenAgentWorkflowCandidate:
    submission_id: str
    candidate_record_sha256: str
    request: SubmitCandidateRequest


@dataclass
class AgentWorkflowCandidateStore:
    state_machine: AgentWorkflowStateMachine
    budget_tracker: AgentWorkflowBudgetTracker
    _candidate: FrozenAgentWorkflowCandidate | None = field(default=None, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False, compare=False)

    @property
    def candidate(self) -> FrozenAgentWorkflowCandidate | None:
        return self._candidate

    def submit(self, request: SubmitCandidateRequest) -> SubmitCandidateResponse:
        with self._lock, self.state_machine._lock:
            if self._candidate is not None:
                return self._rejected(SubmitCandidateRejectionCode.CANDIDATE_ALREADY_FROZEN)
            if self.state_machine.status is not AgentWorkflowNodeStatus.RUNNING:
                return self._rejected(SubmitCandidateRejectionCode.NODE_NOT_RUNNING)
            try:
                candidate_record_sha256 = request.canonical_sha256()
            except AgentWorkflowContractError:
                return self._rejected(SubmitCandidateRejectionCode.INVALID_CONTRACT)

            submission_id = f"submission:{candidate_record_sha256}"
            candidate = FrozenAgentWorkflowCandidate(
                submission_id=submission_id,
                candidate_record_sha256=candidate_record_sha256,
                request=request,
            )
            self.state_machine.transition(AgentWorkflowNodeStatus.CANDIDATE_SUBMITTED)
            self._candidate = candidate
            return SubmitCandidateResponse(
                accepted=True,
                submission_id=submission_id,
                candidate_record_sha256=candidate_record_sha256,
                remaining_budget=self.budget_tracker.remaining(),
                terminal_for_agent=True,
            )

    def _rejected(self, code: SubmitCandidateRejectionCode) -> SubmitCandidateResponse:
        return SubmitCandidateResponse(
            accepted=False,
            rejection_codes=(code.value,),
            remaining_budget=self.budget_tracker.remaining(),
            terminal_for_agent=code is not SubmitCandidateRejectionCode.INVALID_CONTRACT,
        )
