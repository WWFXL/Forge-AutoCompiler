from __future__ import annotations

from dataclasses import replace

import pytest

from deerflow.compile.jev_controller import (
    REQUIRED_STRICT_VERIFIERS,
    CalibrationContract,
    CandidateAction,
    DecisionState,
    TypedDecision,
    VerifierCapabilities,
    dispatch_route,
    route_next_action,
)


def _state() -> DecisionState:
    return DecisionState(
        state_id="state-1",
        build_system="cmake",
        phase_facts={"configured": True, "build_succeeded": False},
        remaining_actions=8,
        remaining_wall_clock_seconds=900,
        expected_request_fingerprint="f" * 64,
    )


def _candidates(*, preconditions_satisfied: bool = True) -> tuple[CandidateAction, ...]:
    return (
        CandidateAction("state-1:dependency", "dependency", ("restore-source",), True, preconditions_satisfied),
        CandidateAction("state-1:configure", "configure", ("configure",), True, preconditions_satisfied),
        CandidateAction("state-1:build", "build", ("build",), True, preconditions_satisfied),
        CandidateAction("state-1:escalate_agent", "escalate_agent", (), False, preconditions_satisfied),
    )


def _decision() -> TypedDecision:
    probabilities = {"dependency": 0.0, "configure": 0.99, "build": 0.01, "escalate_agent": 0.0}
    return TypedDecision(
        state_id="state-1",
        model="jev-1.13.0",
        request_fingerprint="f" * 64,
        primary_choice="configure",
        reverse_choice="configure",
        probabilities=probabilities,
        reverse_probabilities=probabilities,
    )


def _calibration() -> CalibrationContract:
    return CalibrationContract(
        model="jev-1.13.0",
        coefficient=0.08805149266059632,
        intercept=0.618335523488825,
        threshold=0.6747568477098429,
    )


def _capabilities() -> VerifierCapabilities:
    return VerifierCapabilities(True, True, True, True)


def test_calibration_reproduces_v6_probability() -> None:
    assert _calibration().safe_probability(0.99) == pytest.approx(0.735545402401868)


def test_valid_decision_dispatches_only_bound_candidate_and_never_completes() -> None:
    candidates = _candidates()
    route = route_next_action(
        state=_state(),
        candidates=candidates,
        decision=_decision(),
        calibration=_calibration(),
        verifier_capabilities=_capabilities(),
    )
    seen: list[CandidateAction] = []
    receipt = dispatch_route(route=route, candidates=candidates, executor=seen.append)

    assert route.disposition == "direct_execute"
    assert route.selected_action_id == "state-1:configure"
    assert route.required_verifiers == REQUIRED_STRICT_VERIFIERS
    assert route.terminal_success is False
    assert seen == [candidates[1]]
    assert receipt.disposition == "awaiting_strict_verification"
    assert receipt.executor_invoked is True
    assert receipt.terminal_success is False


@pytest.mark.parametrize(
    ("state", "decision", "candidates", "capabilities", "reason"),
    [
        (_state(), None, _candidates(), _capabilities(), "response_missing"),
        (_state(), replace(_decision(), model="jev-preview"), _candidates(), _capabilities(), "model_mismatch"),
        (_state(), replace(_decision(), state_id="wrong"), _candidates(), _capabilities(), "state_mismatch"),
        (_state(), replace(_decision(), request_fingerprint="0" * 64), _candidates(), _capabilities(), "request_fingerprint_mismatch"),
        (_state(), replace(_decision(), reverse_choice="build"), _candidates(), _capabilities(), "choice_order_disagreement"),
        (
            _state(),
            replace(
                _decision(),
                probabilities={"dependency": 0.0, "configure": float("nan"), "build": 0.0, "escalate_agent": 0.0},
                reverse_probabilities={"dependency": 0.0, "configure": float("nan"), "build": 0.0, "escalate_agent": 0.0},
            ),
            _candidates(),
            _capabilities(),
            "probability_contract_invalid",
        ),
        (
            _state(),
            replace(_decision(), probabilities={"dependency": 0.30, "configure": 0.25, "build": 0.25, "escalate_agent": 0.20}),
            _candidates(),
            _capabilities(),
            "choice_probability_mismatch",
        ),
        (
            _state(),
            replace(
                _decision(),
                primary_choice="escalate_agent",
                reverse_choice="escalate_agent",
                probabilities={"dependency": 0.0, "configure": 0.0, "build": 0.0, "escalate_agent": 1.0},
                reverse_probabilities={"dependency": 0.0, "configure": 0.0, "build": 0.0, "escalate_agent": 1.0},
            ),
            _candidates(),
            _capabilities(),
            "model_requested_escalation",
        ),
        (replace(_state(), remaining_actions=0), _decision(), _candidates(), _capabilities(), "budget_exhausted"),
        (_state(), _decision(), tuple(candidate for candidate in _candidates() if candidate.action_family != "configure"), _capabilities(), "selected_candidate_missing_or_ambiguous"),
        (_state(), _decision(), _candidates(preconditions_satisfied=False), _capabilities(), "selected_candidate_precondition_failed"),
        (_state(), _decision(), _candidates(), VerifierCapabilities(False, True, True, True), "strict_verifier_capability_missing"),
    ],
)
def test_invalid_or_unsafe_decisions_fail_closed(
    state: DecisionState,
    decision: TypedDecision | None,
    candidates: tuple[CandidateAction, ...],
    capabilities: VerifierCapabilities,
    reason: str,
) -> None:
    route = route_next_action(
        state=state,
        candidates=candidates,
        decision=decision,
        calibration=_calibration(),
        verifier_capabilities=capabilities,
    )
    invoked = False

    def executor(_: CandidateAction) -> None:
        nonlocal invoked
        invoked = True

    receipt = dispatch_route(route=route, candidates=candidates, executor=executor)
    assert route.disposition == "escalate_agent"
    assert route.reasons == (reason,)
    assert route.terminal_success is False
    assert receipt.disposition == "escalate_agent"
    assert invoked is False


def test_below_calibrated_threshold_escalates() -> None:
    decision = replace(
        _decision(),
        probabilities={"dependency": 0.20, "configure": 0.40, "build": 0.20, "escalate_agent": 0.20},
        reverse_probabilities={"dependency": 0.20, "configure": 0.40, "build": 0.20, "escalate_agent": 0.20},
    )
    route = route_next_action(
        state=_state(),
        candidates=_candidates(),
        decision=decision,
        calibration=_calibration(),
        verifier_capabilities=_capabilities(),
    )
    assert route.disposition == "escalate_agent"
    assert route.reasons == ("below_calibrated_threshold",)
    assert route.calibrated_safe_probability is not None
    assert route.calibrated_safe_probability < _calibration().threshold


def test_candidate_contract_rejects_model_generated_or_unknown_action_shape() -> None:
    with pytest.raises(ValueError, match="未知动作族"):
        CandidateAction("state-1:shell", "shell", ("rm -rf /",), True, True)
    with pytest.raises(ValueError, match="至少一条命令"):
        CandidateAction("state-1:build", "build", (), True, True)
    with pytest.raises(ValueError, match="不一致"):
        CandidateAction("state-1:escalate_agent", "escalate_agent", ("agent",), True, True)
