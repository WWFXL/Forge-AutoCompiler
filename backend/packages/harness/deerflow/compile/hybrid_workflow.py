from __future__ import annotations

import inspect
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Literal

from deerflow.compile.jev_controller import (
    CalibrationContract,
    CandidateAction,
    DecisionState,
    RouteDecision,
    TypedDecision,
    VerifierCapabilities,
    dispatch_route,
    route_next_action,
)

HybridTerminalStatus = Literal["pending", "strict_success", "terminal_failure"]
HybridResultStatus = Literal["strict_success", "terminal_failure", "budget_exhausted"]
HybridTraceEvent = Literal["observation", "route", "direct_action", "agent_handoff", "terminal"]


@dataclass(frozen=True)
class HybridWorkflowBudget:
    max_cycles: int
    max_direct_actions: int
    max_agent_handoffs: int
    wall_clock_seconds: float

    def __post_init__(self) -> None:
        if self.max_cycles < 0 or self.max_direct_actions < 0 or self.max_agent_handoffs < 0:
            raise ValueError("混合工作流计数预算不得为负数")
        if not math.isfinite(self.wall_clock_seconds) or self.wall_clock_seconds <= 0:
            raise ValueError("混合工作流墙钟预算必须为正数")


@dataclass(frozen=True)
class HybridWorkflowSnapshot:
    cycles: int
    decisions: int
    direct_actions: int
    agent_handoffs: int
    observations: int
    elapsed_seconds: float
    remaining_cycles: int
    remaining_direct_actions: int
    remaining_agent_handoffs: int
    remaining_wall_clock_seconds: int


@dataclass(frozen=True)
class HybridWorkflowObservation:
    observation_id: int
    decision_state: DecisionState
    candidates: tuple[CandidateAction, ...]
    verifier_capabilities: VerifierCapabilities
    terminal_status: HybridTerminalStatus = "pending"
    terminal_reason: str | None = None

    def __post_init__(self) -> None:
        if self.observation_id < 0:
            raise ValueError("observation_id 不得为负数")
        if self.terminal_status not in {"pending", "strict_success", "terminal_failure"}:
            raise ValueError(f"未知权威终态: {self.terminal_status}")
        if self.terminal_status != "pending" and not self.terminal_reason:
            raise ValueError("权威终态必须提供原因")


@dataclass(frozen=True)
class HybridStepOutcome:
    succeeded: bool
    reason: str
    reported_terminal_success: bool = False

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError("步骤结果必须提供原因")


@dataclass(frozen=True)
class HybridAgentHandoff:
    observation: HybridWorkflowObservation
    snapshot: HybridWorkflowSnapshot
    trigger: str
    route: RouteDecision | None
    direct_action: CandidateAction | None = None
    direct_outcome: HybridStepOutcome | None = None


@dataclass(frozen=True)
class HybridTraceEntry:
    sequence: int
    event: HybridTraceEvent
    observation_id: int | None
    state_id: str | None
    action_id: str | None
    action_family: str | None
    disposition: str | None
    succeeded: bool | None
    reason: str
    reported_terminal_success: bool = False


@dataclass(frozen=True)
class HybridWorkflowResult:
    status: HybridResultStatus
    reason: str
    cycles: int
    decisions: int
    direct_actions: int
    agent_handoffs: int
    observations: int
    final_observation_id: int | None
    fail_closed: bool
    trace: tuple[HybridTraceEntry, ...]


type MaybeAwaitable[T] = T | Awaitable[T]
Observer = Callable[[HybridWorkflowSnapshot], MaybeAwaitable[HybridWorkflowObservation]]
DecisionProvider = Callable[[HybridWorkflowObservation], MaybeAwaitable[TypedDecision | None]]
DirectExecutor = Callable[[CandidateAction], MaybeAwaitable[HybridStepOutcome]]
AgentRunner = Callable[[HybridAgentHandoff], MaybeAwaitable[HybridStepOutcome]]


async def _resolve[T](value: MaybeAwaitable[T]) -> T:
    if inspect.isawaitable(value):
        return await value
    return value


async def run_hybrid_workflow(
    *,
    budget: HybridWorkflowBudget,
    calibration: CalibrationContract,
    observer: Observer,
    decision_provider: DecisionProvider,
    direct_executor: DirectExecutor,
    agent_runner: AgentRunner,
    clock: Callable[[], float] = time.monotonic,
) -> HybridWorkflowResult:
    """运行一次由权威 observer 收口的 Jev/Agent 混合恢复循环。"""

    started_at = clock()
    cycles = 0
    decisions = 0
    direct_actions = 0
    agent_handoffs = 0
    observations = 0
    trace: list[HybridTraceEntry] = []
    last_observation: HybridWorkflowObservation | None = None
    progress_required_after: Literal["direct_action", "agent"] | None = None
    fail_closed = False

    def elapsed_seconds() -> float:
        return max(0.0, clock() - started_at)

    def snapshot() -> HybridWorkflowSnapshot:
        elapsed = elapsed_seconds()
        remaining_wall_clock = max(0, math.ceil(budget.wall_clock_seconds - elapsed))
        return HybridWorkflowSnapshot(
            cycles=cycles,
            decisions=decisions,
            direct_actions=direct_actions,
            agent_handoffs=agent_handoffs,
            observations=observations,
            elapsed_seconds=elapsed,
            remaining_cycles=max(0, budget.max_cycles - cycles),
            remaining_direct_actions=max(0, budget.max_direct_actions - direct_actions),
            remaining_agent_handoffs=max(0, budget.max_agent_handoffs - agent_handoffs),
            remaining_wall_clock_seconds=remaining_wall_clock,
        )

    def record(
        event: HybridTraceEvent,
        *,
        observation: HybridWorkflowObservation | None,
        reason: str,
        action: CandidateAction | None = None,
        disposition: str | None = None,
        succeeded: bool | None = None,
        reported_terminal_success: bool = False,
    ) -> None:
        trace.append(
            HybridTraceEntry(
                sequence=len(trace) + 1,
                event=event,
                observation_id=observation.observation_id if observation else None,
                state_id=observation.decision_state.state_id if observation else None,
                action_id=action.action_id if action else None,
                action_family=action.action_family if action else None,
                disposition=disposition,
                succeeded=succeeded,
                reason=reason,
                reported_terminal_success=reported_terminal_success,
            )
        )

    def finish(status: HybridResultStatus, reason: str, *, closed: bool = False) -> HybridWorkflowResult:
        nonlocal fail_closed
        fail_closed = fail_closed or closed
        record("terminal", observation=last_observation, reason=reason, disposition=status, succeeded=status == "strict_success")
        return HybridWorkflowResult(
            status=status,
            reason=reason,
            cycles=cycles,
            decisions=decisions,
            direct_actions=direct_actions,
            agent_handoffs=agent_handoffs,
            observations=observations,
            final_observation_id=last_observation.observation_id if last_observation else None,
            fail_closed=fail_closed,
            trace=tuple(trace),
        )

    def wall_clock_exhausted() -> bool:
        return elapsed_seconds() >= budget.wall_clock_seconds

    while True:
        if wall_clock_exhausted():
            return finish("budget_exhausted", "wall_clock_budget_exhausted")

        try:
            observed = await _resolve(observer(snapshot()))
        except Exception as exc:
            return finish("terminal_failure", f"observer_exception:{type(exc).__name__}", closed=True)
        if not isinstance(observed, HybridWorkflowObservation):
            return finish("terminal_failure", "observer_contract_invalid", closed=True)

        observations += 1
        remaining_wall_clock = snapshot().remaining_wall_clock_seconds
        observed = replace(
            observed,
            decision_state=replace(
                observed.decision_state,
                remaining_actions=max(0, budget.max_direct_actions - direct_actions),
                remaining_wall_clock_seconds=remaining_wall_clock,
            ),
        )
        record("observation", observation=observed, reason=observed.terminal_status, disposition=observed.terminal_status)

        if last_observation is not None and observed.observation_id <= last_observation.observation_id:
            source = progress_required_after or "callback"
            last_observation = observed
            return finish("terminal_failure", f"stale_observation_after_{source}", closed=True)
        last_observation = observed
        progress_required_after = None

        if observed.terminal_status == "strict_success":
            if not observed.verifier_capabilities.complete:
                return finish("terminal_failure", "strict_success_without_complete_verifiers", closed=True)
            return finish("strict_success", observed.terminal_reason or "strict_evaluator_passed")
        if observed.terminal_status == "terminal_failure":
            return finish("terminal_failure", observed.terminal_reason or "authoritative_terminal_failure")
        if wall_clock_exhausted():
            return finish("budget_exhausted", "wall_clock_budget_exhausted")
        if cycles >= budget.max_cycles:
            return finish("budget_exhausted", "cycle_budget_exhausted")

        cycles += 1
        route: RouteDecision | None = None
        trigger: str | None = None
        selected_action: CandidateAction | None = None
        direct_outcome: HybridStepOutcome | None = None

        if not observed.candidates:
            trigger = "candidate_set_empty"
            fail_closed = True
            record("route", observation=observed, reason=trigger, disposition="escalate_agent")
        elif direct_actions >= budget.max_direct_actions:
            trigger = "direct_action_budget_exhausted"
            fail_closed = True
            record("route", observation=observed, reason=trigger, disposition="escalate_agent")
        else:
            if wall_clock_exhausted():
                return finish("budget_exhausted", "wall_clock_budget_exhausted")
            decisions += 1
            provider_error: str | None = None
            try:
                decision = await _resolve(decision_provider(observed))
            except Exception as exc:
                decision = None
                provider_error = f"decision_provider_exception:{type(exc).__name__}"
            try:
                route = route_next_action(
                    state=observed.decision_state,
                    candidates=observed.candidates,
                    decision=decision,
                    calibration=calibration,
                    verifier_capabilities=observed.verifier_capabilities,
                )
            except Exception as exc:
                provider_error = f"decision_contract_exception:{type(exc).__name__}"
                route = route_next_action(
                    state=observed.decision_state,
                    candidates=observed.candidates,
                    decision=None,
                    calibration=calibration,
                    verifier_capabilities=observed.verifier_capabilities,
                )
            if provider_error is not None:
                route = replace(route, reasons=(provider_error,))

            record(
                "route",
                observation=observed,
                reason=route.reasons[0],
                disposition=route.disposition,
            )
            if route.disposition == "escalate_agent":
                trigger = route.reasons[0]
                fail_closed = True
            else:
                captured: list[CandidateAction] = []
                try:
                    dispatch_route(route=route, candidates=observed.candidates, executor=captured.append)
                except Exception as exc:
                    return finish("terminal_failure", f"dispatch_contract_exception:{type(exc).__name__}", closed=True)
                if len(captured) != 1:
                    return finish("terminal_failure", "dispatch_contract_invalid", closed=True)
                selected_action = captured[0]
                if wall_clock_exhausted():
                    return finish("budget_exhausted", "wall_clock_budget_exhausted")

                direct_actions += 1
                try:
                    direct_outcome = await _resolve(direct_executor(selected_action))
                except Exception as exc:
                    direct_outcome = HybridStepOutcome(succeeded=False, reason=f"direct_executor_exception:{type(exc).__name__}")
                    fail_closed = True
                if not isinstance(direct_outcome, HybridStepOutcome):
                    direct_outcome = HybridStepOutcome(succeeded=False, reason="direct_executor_contract_invalid")
                    fail_closed = True
                record(
                    "direct_action",
                    observation=observed,
                    action=selected_action,
                    reason=direct_outcome.reason,
                    disposition="awaiting_authoritative_observation",
                    succeeded=direct_outcome.succeeded,
                    reported_terminal_success=direct_outcome.reported_terminal_success,
                )
                if direct_outcome.succeeded:
                    progress_required_after = "direct_action"
                    continue
                trigger = f"direct_action_failed:{direct_outcome.reason}"
                fail_closed = True

        if trigger is None:
            return finish("terminal_failure", "hybrid_route_invariant_failed", closed=True)
        if agent_handoffs >= budget.max_agent_handoffs:
            return finish("budget_exhausted", "agent_handoff_budget_exhausted")
        if wall_clock_exhausted():
            return finish("budget_exhausted", "wall_clock_budget_exhausted")

        handoff = HybridAgentHandoff(
            observation=observed,
            snapshot=snapshot(),
            trigger=trigger,
            route=route,
            direct_action=selected_action,
            direct_outcome=direct_outcome,
        )
        agent_handoffs += 1
        try:
            agent_outcome = await _resolve(agent_runner(handoff))
        except Exception as exc:
            agent_outcome = HybridStepOutcome(succeeded=False, reason=f"agent_runner_exception:{type(exc).__name__}")
            fail_closed = True
        if not isinstance(agent_outcome, HybridStepOutcome):
            agent_outcome = HybridStepOutcome(succeeded=False, reason="agent_runner_contract_invalid")
            fail_closed = True
        record(
            "agent_handoff",
            observation=observed,
            action=selected_action,
            reason=agent_outcome.reason,
            disposition="awaiting_authoritative_observation",
            succeeded=agent_outcome.succeeded,
            reported_terminal_success=agent_outcome.reported_terminal_success,
        )
        progress_required_after = "agent"
