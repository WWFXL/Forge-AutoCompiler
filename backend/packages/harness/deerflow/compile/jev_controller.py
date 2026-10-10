from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

ACTION_FAMILIES = ("dependency", "configure", "build", "escalate_agent")
DIRECT_ACTION_FAMILIES = frozenset({"dependency", "configure", "build"})
REQUIRED_STRICT_VERIFIERS = (
    "candidate_verifier",
    "functional_oracle",
    "provenance",
    "clean_replay",
)


@dataclass(frozen=True)
class DecisionState:
    state_id: str
    build_system: str
    phase_facts: Mapping[str, bool]
    remaining_actions: int
    remaining_wall_clock_seconds: int
    expected_request_fingerprint: str


@dataclass(frozen=True)
class CandidateAction:
    action_id: str
    action_family: str
    bound_commands: tuple[str, ...]
    direct_execution: bool
    preconditions_satisfied: bool

    def __post_init__(self) -> None:
        if self.action_family not in ACTION_FAMILIES:
            raise ValueError(f"未知动作族: {self.action_family}")
        if self.direct_execution != (self.action_family in DIRECT_ACTION_FAMILIES):
            raise ValueError("动作族与 direct_execution 不一致")
        if self.direct_execution and not self.bound_commands:
            raise ValueError("直接动作必须绑定至少一条命令")


@dataclass(frozen=True)
class TypedDecision:
    state_id: str
    model: str
    request_fingerprint: str
    primary_choice: str
    reverse_choice: str
    probabilities: Mapping[str, float]
    reverse_probabilities: Mapping[str, float]


@dataclass(frozen=True)
class CalibrationContract:
    model: str
    coefficient: float
    intercept: float
    threshold: float

    def safe_probability(self, action_probability: float) -> float:
        clipped = min(0.999999, max(0.000001, action_probability))
        logit = math.log(clipped / (1.0 - clipped))
        value = self.coefficient * logit + self.intercept
        if value >= 0:
            return 1.0 / (1.0 + math.exp(-value))
        exp_value = math.exp(value)
        return exp_value / (1.0 + exp_value)


@dataclass(frozen=True)
class VerifierCapabilities:
    candidate_verifier: bool
    functional_oracle: bool
    provenance: bool
    clean_replay: bool

    @property
    def complete(self) -> bool:
        return all(getattr(self, name) for name in REQUIRED_STRICT_VERIFIERS)


@dataclass(frozen=True)
class RouteDecision:
    disposition: Literal["direct_execute", "escalate_agent"]
    selected_action_id: str | None
    selected_action_family: str
    calibrated_safe_probability: float | None
    reasons: tuple[str, ...]
    required_verifiers: tuple[str, ...] = REQUIRED_STRICT_VERIFIERS
    terminal_success: bool = False


@dataclass(frozen=True)
class DispatchReceipt:
    disposition: Literal["awaiting_strict_verification", "escalate_agent"]
    action_id: str | None
    action_family: str
    executor_invoked: bool
    required_verifiers: tuple[str, ...] = REQUIRED_STRICT_VERIFIERS
    terminal_success: bool = False


def _escalate(reason: str, *, calibrated_probability: float | None = None) -> RouteDecision:
    return RouteDecision(
        disposition="escalate_agent",
        selected_action_id=None,
        selected_action_family="escalate_agent",
        calibrated_safe_probability=calibrated_probability,
        reasons=(reason,),
    )


def _probability_contract_valid(probabilities: Mapping[str, float]) -> bool:
    if set(probabilities) != set(ACTION_FAMILIES):
        return False
    values = list(probabilities.values())
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0.0 or value > 1.0 for value in values):
        return False
    return abs(sum(values) - 1.0) <= 0.005


def route_next_action(
    *,
    state: DecisionState,
    candidates: Sequence[CandidateAction],
    decision: TypedDecision | None,
    calibration: CalibrationContract,
    verifier_capabilities: VerifierCapabilities,
) -> RouteDecision:
    if decision is None:
        return _escalate("response_missing")
    if decision.model != calibration.model:
        return _escalate("model_mismatch")
    if decision.state_id != state.state_id:
        return _escalate("state_mismatch")
    if decision.request_fingerprint != state.expected_request_fingerprint:
        return _escalate("request_fingerprint_mismatch")
    if decision.primary_choice not in ACTION_FAMILIES or decision.reverse_choice not in ACTION_FAMILIES:
        return _escalate("unknown_action_choice")
    if decision.primary_choice != decision.reverse_choice:
        return _escalate("choice_order_disagreement")
    if not _probability_contract_valid(decision.probabilities) or not _probability_contract_valid(decision.reverse_probabilities):
        return _escalate("probability_contract_invalid")
    selected_probability = float(decision.probabilities[decision.primary_choice])
    if selected_probability != max(decision.probabilities.values()):
        return _escalate("choice_probability_mismatch")
    if decision.primary_choice == "escalate_agent":
        return _escalate("model_requested_escalation")
    if state.remaining_actions <= 0 or state.remaining_wall_clock_seconds <= 0:
        return _escalate("budget_exhausted")
    if not verifier_capabilities.complete:
        return _escalate("strict_verifier_capability_missing")

    matching = [candidate for candidate in candidates if candidate.action_family == decision.primary_choice]
    if len(matching) != 1:
        return _escalate("selected_candidate_missing_or_ambiguous")
    selected = matching[0]
    if not selected.direct_execution:
        return _escalate("selected_candidate_not_direct")
    if not selected.preconditions_satisfied:
        return _escalate("selected_candidate_precondition_failed")

    calibrated_probability = calibration.safe_probability(selected_probability)
    if calibrated_probability < calibration.threshold:
        return _escalate("below_calibrated_threshold", calibrated_probability=calibrated_probability)
    return RouteDecision(
        disposition="direct_execute",
        selected_action_id=selected.action_id,
        selected_action_family=selected.action_family,
        calibrated_safe_probability=calibrated_probability,
        reasons=("calibrated_direct_action",),
    )


def dispatch_route(
    *,
    route: RouteDecision,
    candidates: Sequence[CandidateAction],
    executor: Callable[[CandidateAction], None],
) -> DispatchReceipt:
    if route.disposition == "escalate_agent":
        return DispatchReceipt(
            disposition="escalate_agent",
            action_id=None,
            action_family="escalate_agent",
            executor_invoked=False,
        )

    matching = [candidate for candidate in candidates if candidate.action_id == route.selected_action_id]
    if len(matching) != 1:
        raise ValueError("路由动作无法唯一映射到代码绑定候选")
    candidate = matching[0]
    if candidate.action_family != route.selected_action_family or not candidate.direct_execution or not candidate.preconditions_satisfied:
        raise ValueError("调度前候选动作合同已漂移")
    if route.required_verifiers != REQUIRED_STRICT_VERIFIERS or route.terminal_success:
        raise ValueError("路由不得绕过严格验证链或宣告终态成功")

    executor(candidate)
    return DispatchReceipt(
        disposition="awaiting_strict_verification",
        action_id=candidate.action_id,
        action_family=candidate.action_family,
        executor_invoked=True,
    )
