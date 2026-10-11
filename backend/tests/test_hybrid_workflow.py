from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace

import pytest

from deerflow.compile.hybrid_workflow import (
    HybridAgentHandoff,
    HybridStepOutcome,
    HybridWorkflowBudget,
    HybridWorkflowObservation,
    HybridWorkflowSnapshot,
    run_hybrid_workflow,
)
from deerflow.compile.jev_controller import CalibrationContract, CandidateAction, DecisionState, TypedDecision, VerifierCapabilities


def _budget(**overrides: int | float) -> HybridWorkflowBudget:
    values: dict[str, int | float] = {
        "max_cycles": 3,
        "max_direct_actions": 2,
        "max_agent_handoffs": 2,
        "wall_clock_seconds": 60.0,
    }
    values.update(overrides)
    return HybridWorkflowBudget(**values)  # type: ignore[arg-type]


def _calibration() -> CalibrationContract:
    return CalibrationContract(model="jev-1.13.0", coefficient=1.0, intercept=0.0, threshold=0.8)


def _capabilities(*, complete: bool = True) -> VerifierCapabilities:
    return VerifierCapabilities(complete, True, True, True)


def _candidates(state_id: str) -> tuple[CandidateAction, ...]:
    return (
        CandidateAction(f"{state_id}:dependency", "dependency", ("install-dependency",), True, True),
        CandidateAction(f"{state_id}:configure", "configure", ("configure",), True, True),
        CandidateAction(f"{state_id}:build", "build", ("build",), True, True),
        CandidateAction(f"{state_id}:escalate_agent", "escalate_agent", (), False, True),
    )


def _observation(
    observation_id: int,
    *,
    terminal_status: str = "pending",
    terminal_reason: str | None = None,
    complete_verifiers: bool = True,
    candidates: tuple[CandidateAction, ...] | None = None,
) -> HybridWorkflowObservation:
    state_id = f"state-{observation_id}"
    return HybridWorkflowObservation(
        observation_id=observation_id,
        decision_state=DecisionState(
            state_id=state_id,
            build_system="cmake",
            phase_facts={"configured": True, "build_succeeded": False},
            remaining_actions=999,
            remaining_wall_clock_seconds=999,
            expected_request_fingerprint=str(observation_id) * 64,
        ),
        candidates=_candidates(state_id) if candidates is None else candidates,
        verifier_capabilities=_capabilities(complete=complete_verifiers),
        terminal_status=terminal_status,  # type: ignore[arg-type]
        terminal_reason=terminal_reason,
    )


def _decision(observation: HybridWorkflowObservation, *, probability: float = 0.95, reverse_choice: str = "configure") -> TypedDecision:
    other_probability = (1.0 - probability) / 3.0
    probabilities = {
        "dependency": other_probability,
        "configure": probability,
        "build": other_probability,
        "escalate_agent": other_probability,
    }
    return TypedDecision(
        state_id=observation.decision_state.state_id,
        model="jev-1.13.0",
        request_fingerprint=observation.decision_state.expected_request_fingerprint,
        primary_choice="configure",
        reverse_choice=reverse_choice,
        probabilities=probabilities,
        reverse_probabilities=probabilities,
    )


def _scripted_observer(observations: list[HybridWorkflowObservation]) -> Callable[[HybridWorkflowSnapshot], HybridWorkflowObservation]:
    remaining = list(observations)

    def observe(_snapshot: HybridWorkflowSnapshot) -> HybridWorkflowObservation:
        return remaining.pop(0)

    return observe


def test_direct_action_returns_control_to_authoritative_observer() -> None:
    direct_actions: list[CandidateAction] = []
    agent_handoffs: list[HybridAgentHandoff] = []
    decision_states: list[DecisionState] = []

    async def decide(observation: HybridWorkflowObservation) -> TypedDecision:
        decision_states.append(observation.decision_state)
        return _decision(observation)

    async def execute(candidate: CandidateAction) -> HybridStepOutcome:
        direct_actions.append(candidate)
        return HybridStepOutcome(succeeded=True, reason="configure_completed", reported_terminal_success=True)

    async def run_agent(handoff: HybridAgentHandoff) -> HybridStepOutcome:
        agent_handoffs.append(handoff)
        return HybridStepOutcome(succeeded=True, reason="unused")

    result = asyncio.run(
        run_hybrid_workflow(
            budget=_budget(),
            calibration=_calibration(),
            observer=_scripted_observer(
                [
                    _observation(1),
                    _observation(2, terminal_status="strict_success", terminal_reason="strict_evaluator_passed"),
                ]
            ),
            decision_provider=decide,
            direct_executor=execute,
            agent_runner=run_agent,
        )
    )

    assert result.status == "strict_success"
    assert result.reason == "strict_evaluator_passed"
    assert result.direct_actions == 1
    assert result.agent_handoffs == 0
    assert direct_actions[0].action_family == "configure"
    assert agent_handoffs == []
    assert decision_states[0].remaining_actions == 2
    assert decision_states[0].remaining_wall_clock_seconds <= 60
    assert all(entry.event != "callback_terminal_success" for entry in result.trace)


@pytest.mark.parametrize("mode", ["missing", "low_confidence", "order_disagreement", "provider_exception"])
def test_unsafe_or_missing_jev_decision_escalates_once(mode: str) -> None:
    handoffs: list[HybridAgentHandoff] = []

    def decide(observation: HybridWorkflowObservation) -> TypedDecision | None:
        if mode == "missing":
            return None
        if mode == "provider_exception":
            raise RuntimeError("provider unavailable")
        if mode == "low_confidence":
            return _decision(observation, probability=0.4)
        return _decision(observation, reverse_choice="build")

    def run_agent(handoff: HybridAgentHandoff) -> HybridStepOutcome:
        handoffs.append(handoff)
        return HybridStepOutcome(succeeded=True, reason="agent_submitted_candidate", reported_terminal_success=True)

    result = asyncio.run(
        run_hybrid_workflow(
            budget=_budget(),
            calibration=_calibration(),
            observer=_scripted_observer(
                [
                    _observation(1),
                    _observation(2, terminal_status="strict_success", terminal_reason="strict_evaluator_passed"),
                ]
            ),
            decision_provider=decide,
            direct_executor=lambda _candidate: HybridStepOutcome(succeeded=True, reason="unexpected"),
            agent_runner=run_agent,
        )
    )

    assert result.status == "strict_success"
    assert result.direct_actions == 0
    assert result.agent_handoffs == 1
    assert result.fail_closed is True
    assert len(handoffs) == 1
    assert handoffs[0].trigger in {
        "response_missing",
        "below_calibrated_threshold",
        "choice_order_disagreement",
        "decision_provider_exception:RuntimeError",
    }


def test_direct_action_failure_escalates_without_second_jev_request() -> None:
    provider_calls = 0
    handoffs: list[HybridAgentHandoff] = []

    def decide(observation: HybridWorkflowObservation) -> TypedDecision:
        nonlocal provider_calls
        provider_calls += 1
        return _decision(observation)

    def run_agent(handoff: HybridAgentHandoff) -> HybridStepOutcome:
        handoffs.append(handoff)
        return HybridStepOutcome(succeeded=True, reason="agent_repaired")

    result = asyncio.run(
        run_hybrid_workflow(
            budget=_budget(),
            calibration=_calibration(),
            observer=_scripted_observer(
                [
                    _observation(1),
                    _observation(2, terminal_status="strict_success", terminal_reason="strict_evaluator_passed"),
                ]
            ),
            decision_provider=decide,
            direct_executor=lambda _candidate: HybridStepOutcome(succeeded=False, reason="configure_failed"),
            agent_runner=run_agent,
        )
    )

    assert result.status == "strict_success"
    assert provider_calls == 1
    assert result.direct_actions == 1
    assert result.agent_handoffs == 1
    assert handoffs[0].trigger == "direct_action_failed:configure_failed"
    assert handoffs[0].direct_outcome == HybridStepOutcome(succeeded=False, reason="configure_failed")


def test_executor_exception_escalates_to_agent() -> None:
    def execute(_candidate: CandidateAction) -> HybridStepOutcome:
        raise OSError("container disappeared")

    result = asyncio.run(
        run_hybrid_workflow(
            budget=_budget(),
            calibration=_calibration(),
            observer=_scripted_observer(
                [
                    _observation(1),
                    _observation(2, terminal_status="terminal_failure", terminal_reason="agent_could_not_repair"),
                ]
            ),
            decision_provider=lambda observation: _decision(observation),
            direct_executor=execute,
            agent_runner=lambda _handoff: HybridStepOutcome(succeeded=False, reason="agent_failed"),
        )
    )

    assert result.status == "terminal_failure"
    assert result.direct_actions == 1
    assert result.agent_handoffs == 1
    assert any(entry.reason == "direct_executor_exception:OSError" for entry in result.trace)


def test_agent_reported_success_cannot_replace_observer_verdict() -> None:
    result = asyncio.run(
        run_hybrid_workflow(
            budget=_budget(),
            calibration=_calibration(),
            observer=_scripted_observer(
                [
                    _observation(1),
                    _observation(2, terminal_status="terminal_failure", terminal_reason="clean_replay_failed"),
                ]
            ),
            decision_provider=lambda _observation: None,
            direct_executor=lambda _candidate: HybridStepOutcome(succeeded=True, reason="unused"),
            agent_runner=lambda _handoff: HybridStepOutcome(succeeded=True, reason="agent_claimed_success", reported_terminal_success=True),
        )
    )

    assert result.status == "terminal_failure"
    assert result.reason == "clean_replay_failed"
    assert result.agent_handoffs == 1


def test_stale_observation_after_agent_fails_closed() -> None:
    result = asyncio.run(
        run_hybrid_workflow(
            budget=_budget(),
            calibration=_calibration(),
            observer=_scripted_observer([_observation(1), _observation(1)]),
            decision_provider=lambda _observation: None,
            direct_executor=lambda _candidate: HybridStepOutcome(succeeded=True, reason="unused"),
            agent_runner=lambda _handoff: HybridStepOutcome(succeeded=True, reason="agent_claimed_success", reported_terminal_success=True),
        )
    )

    assert result.status == "terminal_failure"
    assert result.reason == "stale_observation_after_agent"
    assert result.fail_closed is True


def test_strict_success_requires_complete_verifier_capabilities() -> None:
    result = asyncio.run(
        run_hybrid_workflow(
            budget=_budget(),
            calibration=_calibration(),
            observer=_scripted_observer([_observation(1, terminal_status="strict_success", terminal_reason="claimed", complete_verifiers=False)]),
            decision_provider=lambda observation: _decision(observation),
            direct_executor=lambda _candidate: HybridStepOutcome(succeeded=True, reason="unused"),
            agent_runner=lambda _handoff: HybridStepOutcome(succeeded=True, reason="unused"),
        )
    )

    assert result.status == "terminal_failure"
    assert result.reason == "strict_success_without_complete_verifiers"
    assert result.fail_closed is True


def test_agent_budget_exhaustion_stops_before_agent_callback() -> None:
    agent_calls = 0

    def run_agent(_handoff: HybridAgentHandoff) -> HybridStepOutcome:
        nonlocal agent_calls
        agent_calls += 1
        return HybridStepOutcome(succeeded=True, reason="unexpected")

    result = asyncio.run(
        run_hybrid_workflow(
            budget=_budget(max_agent_handoffs=0),
            calibration=_calibration(),
            observer=_scripted_observer([_observation(1)]),
            decision_provider=lambda _observation: None,
            direct_executor=lambda _candidate: HybridStepOutcome(succeeded=True, reason="unused"),
            agent_runner=run_agent,
        )
    )

    assert result.status == "budget_exhausted"
    assert result.reason == "agent_handoff_budget_exhausted"
    assert agent_calls == 0


def test_cycle_budget_stops_after_reobservation() -> None:
    result = asyncio.run(
        run_hybrid_workflow(
            budget=_budget(max_cycles=1),
            calibration=_calibration(),
            observer=_scripted_observer([_observation(1), _observation(2)]),
            decision_provider=lambda observation: _decision(observation),
            direct_executor=lambda _candidate: HybridStepOutcome(succeeded=True, reason="build_advanced"),
            agent_runner=lambda _handoff: HybridStepOutcome(succeeded=True, reason="unused"),
        )
    )

    assert result.status == "budget_exhausted"
    assert result.reason == "cycle_budget_exhausted"
    assert result.cycles == 1
    assert result.observations == 2


def test_empty_candidate_set_skips_provider_and_escalates() -> None:
    provider_calls = 0

    def decide(_observation: HybridWorkflowObservation) -> None:
        nonlocal provider_calls
        provider_calls += 1
        return None

    result = asyncio.run(
        run_hybrid_workflow(
            budget=_budget(),
            calibration=_calibration(),
            observer=_scripted_observer(
                [
                    _observation(1, candidates=()),
                    _observation(2, terminal_status="terminal_failure", terminal_reason="no_safe_candidate"),
                ]
            ),
            decision_provider=decide,
            direct_executor=lambda _candidate: HybridStepOutcome(succeeded=True, reason="unused"),
            agent_runner=lambda handoff: HybridStepOutcome(succeeded=False, reason=handoff.trigger),
        )
    )

    assert result.status == "terminal_failure"
    assert provider_calls == 0
    assert result.agent_handoffs == 1
    assert any(entry.reason == "candidate_set_empty" for entry in result.trace)


def test_observer_exception_fails_closed_without_side_effect_callbacks() -> None:
    def observe(_snapshot: HybridWorkflowSnapshot) -> HybridWorkflowObservation:
        raise ValueError("ledger corrupt")

    result = asyncio.run(
        run_hybrid_workflow(
            budget=_budget(),
            calibration=_calibration(),
            observer=observe,
            decision_provider=lambda observation: _decision(observation),
            direct_executor=lambda _candidate: HybridStepOutcome(succeeded=True, reason="unused"),
            agent_runner=lambda _handoff: HybridStepOutcome(succeeded=True, reason="unused"),
        )
    )

    assert result.status == "terminal_failure"
    assert result.reason == "observer_exception:ValueError"
    assert result.decisions == 0
    assert result.direct_actions == 0
    assert result.agent_handoffs == 0


def test_trace_reconstructs_direct_action_agent_handoff_and_terminal_verdict() -> None:
    result = asyncio.run(
        run_hybrid_workflow(
            budget=_budget(),
            calibration=_calibration(),
            observer=_scripted_observer(
                [
                    _observation(1),
                    _observation(2, terminal_status="strict_success", terminal_reason="strict_evaluator_passed"),
                ]
            ),
            decision_provider=lambda observation: _decision(observation),
            direct_executor=lambda _candidate: HybridStepOutcome(succeeded=False, reason="action_failed"),
            agent_runner=lambda _handoff: HybridStepOutcome(succeeded=True, reason="candidate_submitted"),
        )
    )

    assert [entry.sequence for entry in result.trace] == list(range(1, len(result.trace) + 1))
    assert [entry.event for entry in result.trace] == [
        "observation",
        "route",
        "direct_action",
        "agent_handoff",
        "observation",
        "terminal",
    ]
    assert result.trace[-1].reason == "strict_evaluator_passed"
    assert sum(entry.event == "direct_action" for entry in result.trace) == result.direct_actions
    assert sum(entry.event == "agent_handoff" for entry in result.trace) == result.agent_handoffs


def test_observation_state_budget_is_replaced_from_coordinator_snapshot() -> None:
    seen: list[HybridWorkflowObservation] = []

    def decide(observation: HybridWorkflowObservation) -> TypedDecision:
        seen.append(observation)
        return _decision(observation)

    result = asyncio.run(
        run_hybrid_workflow(
            budget=_budget(max_direct_actions=1),
            calibration=_calibration(),
            observer=_scripted_observer(
                [
                    replace(_observation(1), decision_state=replace(_observation(1).decision_state, remaining_actions=500)),
                    _observation(2, terminal_status="strict_success", terminal_reason="strict_evaluator_passed"),
                ]
            ),
            decision_provider=decide,
            direct_executor=lambda _candidate: HybridStepOutcome(succeeded=True, reason="advanced"),
            agent_runner=lambda _handoff: HybridStepOutcome(succeeded=True, reason="unused"),
        )
    )

    assert result.status == "strict_success"
    assert seen[0].decision_state.remaining_actions == 1
