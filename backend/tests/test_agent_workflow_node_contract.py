from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import MappingProxyType

import pytest

from deerflow.compile.agent_workflow_node import (
    AgentWorkflowBudgetExceeded,
    AgentWorkflowBudgetTracker,
    AgentWorkflowCandidateStore,
    AgentWorkflowNodeStatus,
    AgentWorkflowStateMachine,
    AgentWorkflowTerminationReason,
    InvalidAgentWorkflowTransition,
)
from deerflow.compile.agent_workflow_schemas import (
    AGENT_WORKFLOW_NODE_ORCHESTRATION_MODE,
    AgentBuildNodeInput,
    AgentBuildNodeResult,
    AgentWorkflowBudget,
    AgentWorkflowContractError,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowRemainingBudget,
    AgentWorkflowTargetContract,
    AgentWorkflowUsage,
    SubmitCandidateRequest,
    SubmitCandidateResponse,
)

SHA256_A = "a" * 64
SHA256_B = "b" * 64
SHA256_C = "c" * 64
COMMIT_SHA = "d" * 40


def make_budget(**overrides: int) -> AgentWorkflowBudget:
    values = {
        "max_model_requests": 8,
        "max_recorded_tokens": 120_000,
        "max_agent_steps": 24,
        "max_tool_calls": 32,
        "max_commands": 24,
        "node_timeout_seconds": 600,
        "command_timeout_seconds": 300,
        "evaluator_timeout_seconds": 600,
        "replay_timeout_seconds": 1_200,
        "cleanup_timeout_seconds": 120,
    }
    values.update(overrides)
    return AgentWorkflowBudget(**values)


def make_node_input(**overrides) -> AgentBuildNodeInput:
    values = {
        "task_id": "task-fmt",
        "attempt_id": "attempt-001",
        "session_id": "session-001",
        "repository_url": "https://github.com/fmtlib/fmt.git",
        "commit_sha": COMMIT_SHA,
        "source_snapshot_sha256": SHA256_A,
        "build_system_candidates": ("cmake",),
        "target_contract": AgentWorkflowTargetContract(
            target_id="fmt-library",
            artifact_types=("static_library",),
            artifact_path_patterns=("lib/libfmt.a",),
            functional_oracle_ref="oracle-fmt-link-v1",
        ),
        "operation_policy_ref": "compile-policy-v1",
        "environment": AgentWorkflowEnvironmentIdentity(
            image_id=f"sha256:{SHA256_B}",
            parallel_jobs=4,
            network_policy="compile-network-v1",
        ),
        "budget": make_budget(),
        "experiment_identity": AgentWorkflowExperimentIdentity(
            manifest_sha256=SHA256_A,
            protocol_sha256=SHA256_B,
            runner_sha256=SHA256_C,
        ),
        "initial_observation": {"build_system": "cmake", "failure_codes": ["configure_failed"]},
    }
    values.update(overrides)
    return AgentBuildNodeInput(**values)


def make_submit_request(**overrides) -> SubmitCandidateRequest:
    values = {
        "candidate_id": "candidate-001",
        "build_system": "cmake",
        "supporting_command_ids": ("command-build",),
        "artifact_paths": ("lib/libfmt.a",),
        "target_mapping": {"fmt-library": "lib/libfmt.a"},
        "recipe_command_ids": ("command-configure", "command-build", "command-stage"),
        "agent_summary": "已生成候选。",
    }
    values.update(overrides)
    return SubmitCandidateRequest(**values)


def test_node_input_has_stable_canonical_identity() -> None:
    first = make_node_input(initial_observation={"failure_codes": ["configure_failed"], "build_system": "cmake"})
    second = make_node_input(initial_observation={"build_system": "cmake", "failure_codes": ["configure_failed"]})

    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_sha256() == second.canonical_sha256()
    assert len(first.canonical_sha256()) == 64


def test_node_input_deeply_freezes_json_observation() -> None:
    observation = {"failure_codes": ["configure_failed"], "details": {"attempt": 1}}
    node_input = make_node_input(initial_observation=observation)
    digest = node_input.canonical_sha256()

    observation["failure_codes"].append("build_failed")
    observation["details"]["attempt"] = 2

    assert node_input.canonical_sha256() == digest
    assert node_input.initial_observation["failure_codes"] == ("configure_failed",)
    assert isinstance(node_input.initial_observation["details"], MappingProxyType)
    with pytest.raises(TypeError):
        node_input.initial_observation["details"]["attempt"] = 3


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("commit_sha", "main", "commit_sha"),
        ("source_snapshot_sha256", "not-a-digest", "source_snapshot_sha256"),
        ("build_system_candidates", ("cmake", "cmake"), "duplicates"),
        ("build_system_candidates", ("bazel",), "unsupported"),
        ("repository_url", "https://example.com/repo with space", "repository_url"),
    ],
)
def test_node_input_rejects_invalid_identity(field_name: str, value, message: str) -> None:
    node_input = make_node_input(**{field_name: value})

    with pytest.raises(AgentWorkflowContractError, match=message):
        node_input.validate()


def test_node_input_rejects_wrong_orchestration_mode() -> None:
    identity = replace(make_node_input().experiment_identity, orchestration_mode="lead_compiler_v1")

    with pytest.raises(AgentWorkflowContractError, match="orchestration_mode"):
        make_node_input(experiment_identity=identity).validate()

    assert make_node_input().experiment_identity.orchestration_mode == AGENT_WORKFLOW_NODE_ORCHESTRATION_MODE


def test_budget_contract_rejects_non_positive_limits() -> None:
    with pytest.raises(AgentWorkflowContractError, match="max_model_requests"):
        make_budget(max_model_requests=0).validate()


def test_submit_candidate_has_stable_canonical_identity() -> None:
    first = make_submit_request(target_mapping={"fmt-library": "lib/libfmt.a", "fmt-archive": "lib/libfmt.a"})
    second = make_submit_request(target_mapping={"fmt-archive": "lib/libfmt.a", "fmt-library": "lib/libfmt.a"})

    assert first.canonical_sha256() == second.canonical_sha256()


def test_submit_candidate_freezes_target_mapping() -> None:
    target_mapping = {"fmt-library": "lib/libfmt.a"}
    request = make_submit_request(target_mapping=target_mapping)
    digest = request.canonical_sha256()

    target_mapping["fmt-library"] = "lib/other.a"

    assert request.target_mapping["fmt-library"] == "lib/libfmt.a"
    assert request.canonical_sha256() == digest
    with pytest.raises(TypeError):
        request.target_mapping["fmt-library"] = "lib/other.a"


def test_submit_response_and_node_result_require_consistent_submission_identity() -> None:
    remaining = AgentWorkflowRemainingBudget(8, 120_000, 24, 32, 24, 600.0)
    response = SubmitCandidateResponse(
        accepted=True,
        submission_id="submission:001",
        candidate_record_sha256=SHA256_A,
        remaining_budget=remaining,
        terminal_for_agent=True,
    )
    response.validate()
    assert len(response.canonical_sha256()) == 64

    result = AgentBuildNodeResult(
        node_status="submitted",
        candidate_generated_observed=True,
        candidate_submitted=True,
        submission_id="submission:001",
        candidate_record_sha256=SHA256_A,
        usage=AgentWorkflowUsage(1, 100, 2, 3, 2),
        wall_clock_ms=1200,
        evidence_head_sha256=SHA256_B,
        session_terminal_status="completed",
    )
    result.validate()
    assert len(result.canonical_sha256()) == 64

    with pytest.raises(AgentWorkflowContractError, match="submission identity"):
        replace(response, candidate_record_sha256=None).validate()
    with pytest.raises(AgentWorkflowContractError, match="submitted candidate"):
        replace(result, candidate_submitted=False).validate()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"artifact_paths": ("/artifacts/libfmt.a",)}, "relative POSIX"),
        ({"artifact_paths": ("../libfmt.a",)}, "relative POSIX"),
        ({"recipe_command_ids": ("command-configure",)}, "supporting_command_ids"),
        ({"target_mapping": {"fmt-library": "lib/other.a"}}, "undeclared"),
        ({"build_system": "bazel"}, "build_system"),
        ({"supporting_command_ids": ("command-build", "command-build")}, "duplicates"),
    ],
)
def test_submit_candidate_rejects_invalid_contract(overrides: dict, message: str) -> None:
    with pytest.raises(AgentWorkflowContractError, match=message):
        make_submit_request(**overrides).validate()


def test_contract_type_errors_use_domain_exception() -> None:
    with pytest.raises(AgentWorkflowContractError, match="repository_url"):
        make_node_input(repository_url=None).validate()
    with pytest.raises(AgentWorkflowContractError, match="commit_sha"):
        make_node_input(commit_sha=None).validate()
    with pytest.raises(AgentWorkflowContractError, match="agent_summary"):
        make_submit_request(agent_summary=42).validate()


def test_state_machine_accepts_complete_submission_path() -> None:
    machine = AgentWorkflowStateMachine()

    for target in (
        AgentWorkflowNodeStatus.READY,
        AgentWorkflowNodeStatus.RUNNING,
        AgentWorkflowNodeStatus.CANDIDATE_SUBMITTED,
        AgentWorkflowNodeStatus.EVALUATING,
        AgentWorkflowNodeStatus.EVALUATED,
    ):
        machine.transition(target)
    machine.begin_finalization(AgentWorkflowTerminationReason.EVALUATION_COMPLETED)
    machine.finish_finalization()

    assert machine.status is AgentWorkflowNodeStatus.COMPLETED
    assert machine.termination_reason is AgentWorkflowTerminationReason.EVALUATION_COMPLETED
    assert len(machine.transitions) == 7


def test_state_machine_accepts_no_submission_path() -> None:
    machine = AgentWorkflowStateMachine(status=AgentWorkflowNodeStatus.RUNNING)

    machine.transition(AgentWorkflowNodeStatus.NO_SUBMISSION)
    machine.begin_finalization(AgentWorkflowTerminationReason.NO_SUBMISSION)
    machine.finish_finalization()

    assert machine.status is AgentWorkflowNodeStatus.COMPLETED


def test_state_machine_rejects_every_unregistered_transition() -> None:
    for source in AgentWorkflowNodeStatus:
        for target in AgentWorkflowNodeStatus:
            termination_reason = None
            if source is AgentWorkflowNodeStatus.FINALIZING and target is AgentWorkflowNodeStatus.COMPLETED:
                termination_reason = AgentWorkflowTerminationReason.EVALUATION_COMPLETED
            elif source is AgentWorkflowNodeStatus.FINALIZING and target is AgentWorkflowNodeStatus.CANCELLED:
                termination_reason = AgentWorkflowTerminationReason.CANCELLED
            machine = AgentWorkflowStateMachine(status=source, termination_reason=termination_reason)
            allowed = target in {
                transition_target
                for transition_target in AgentWorkflowNodeStatus
                if (source, transition_target)
                in {
                    (AgentWorkflowNodeStatus.REGISTERED, AgentWorkflowNodeStatus.READY),
                    (AgentWorkflowNodeStatus.REGISTERED, AgentWorkflowNodeStatus.NODE_FAILED),
                    (AgentWorkflowNodeStatus.REGISTERED, AgentWorkflowNodeStatus.FINALIZING),
                    (AgentWorkflowNodeStatus.READY, AgentWorkflowNodeStatus.RUNNING),
                    (AgentWorkflowNodeStatus.READY, AgentWorkflowNodeStatus.NODE_FAILED),
                    (AgentWorkflowNodeStatus.READY, AgentWorkflowNodeStatus.FINALIZING),
                    (AgentWorkflowNodeStatus.RUNNING, AgentWorkflowNodeStatus.CANDIDATE_SUBMITTED),
                    (AgentWorkflowNodeStatus.RUNNING, AgentWorkflowNodeStatus.NO_SUBMISSION),
                    (AgentWorkflowNodeStatus.RUNNING, AgentWorkflowNodeStatus.NODE_FAILED),
                    (AgentWorkflowNodeStatus.RUNNING, AgentWorkflowNodeStatus.FINALIZING),
                    (AgentWorkflowNodeStatus.CANDIDATE_SUBMITTED, AgentWorkflowNodeStatus.EVALUATING),
                    (AgentWorkflowNodeStatus.CANDIDATE_SUBMITTED, AgentWorkflowNodeStatus.NODE_FAILED),
                    (AgentWorkflowNodeStatus.CANDIDATE_SUBMITTED, AgentWorkflowNodeStatus.FINALIZING),
                    (AgentWorkflowNodeStatus.NO_SUBMISSION, AgentWorkflowNodeStatus.FINALIZING),
                    (AgentWorkflowNodeStatus.NODE_FAILED, AgentWorkflowNodeStatus.FINALIZING),
                    (AgentWorkflowNodeStatus.EVALUATING, AgentWorkflowNodeStatus.EVALUATED),
                    (AgentWorkflowNodeStatus.EVALUATING, AgentWorkflowNodeStatus.NODE_FAILED),
                    (AgentWorkflowNodeStatus.EVALUATING, AgentWorkflowNodeStatus.FINALIZING),
                    (AgentWorkflowNodeStatus.EVALUATED, AgentWorkflowNodeStatus.FINALIZING),
                    (AgentWorkflowNodeStatus.FINALIZING, AgentWorkflowNodeStatus.COMPLETED),
                    (AgentWorkflowNodeStatus.FINALIZING, AgentWorkflowNodeStatus.CANCELLED),
                }
            }
            if allowed:
                machine.transition(target)
            else:
                with pytest.raises(InvalidAgentWorkflowTransition):
                    machine.transition(target)


def test_termination_reason_is_first_reason_wins() -> None:
    machine = AgentWorkflowStateMachine(status=AgentWorkflowNodeStatus.RUNNING)

    assert machine.request_termination(AgentWorkflowTerminationReason.BUDGET_EXHAUSTED) is True
    assert machine.request_termination(AgentWorkflowTerminationReason.NODE_FAILED) is False
    assert machine.termination_reason is AgentWorkflowTerminationReason.BUDGET_EXHAUSTED


def test_termination_reason_is_first_reason_wins_under_concurrency() -> None:
    machine = AgentWorkflowStateMachine(status=AgentWorkflowNodeStatus.RUNNING)
    reasons = list(AgentWorkflowTerminationReason)

    with ThreadPoolExecutor(max_workers=len(reasons)) as executor:
        results = list(executor.map(machine.request_termination, reasons))

    assert results.count(True) == 1
    assert results.count(False) == len(reasons) - 1
    assert machine.termination_reason in reasons


def test_cancelled_terminal_requires_finalization() -> None:
    machine = AgentWorkflowStateMachine(status=AgentWorkflowNodeStatus.RUNNING)

    with pytest.raises(InvalidAgentWorkflowTransition):
        machine.transition(AgentWorkflowNodeStatus.CANCELLED)

    machine.begin_finalization(AgentWorkflowTerminationReason.CANCELLED)
    machine.finish_finalization()
    assert machine.status is AgentWorkflowNodeStatus.CANCELLED


def test_terminal_state_rejects_late_writes() -> None:
    machine = AgentWorkflowStateMachine(status=AgentWorkflowNodeStatus.RUNNING)
    machine.begin_finalization(AgentWorkflowTerminationReason.NODE_FAILED)
    machine.finish_finalization()

    with pytest.raises(InvalidAgentWorkflowTransition, match="terminal"):
        machine.request_termination(AgentWorkflowTerminationReason.CANCELLED)
    with pytest.raises(InvalidAgentWorkflowTransition):
        machine.begin_finalization(AgentWorkflowTerminationReason.CANCELLED)

    assert machine.status is AgentWorkflowNodeStatus.COMPLETED
    assert machine.termination_reason is AgentWorkflowTerminationReason.NODE_FAILED


def test_terminal_transition_requires_matching_reason() -> None:
    machine = AgentWorkflowStateMachine(status=AgentWorkflowNodeStatus.FINALIZING)

    with pytest.raises(InvalidAgentWorkflowTransition, match="without a terminal reason"):
        machine.transition(AgentWorkflowNodeStatus.COMPLETED)

    machine.termination_reason = AgentWorkflowTerminationReason.CANCELLED
    with pytest.raises(InvalidAgentWorkflowTransition, match="does not match"):
        machine.transition(AgentWorkflowNodeStatus.COMPLETED)


def test_candidate_store_freezes_first_valid_submission() -> None:
    machine = AgentWorkflowStateMachine(status=AgentWorkflowNodeStatus.RUNNING)
    tracker = AgentWorkflowBudgetTracker(make_budget())
    store = AgentWorkflowCandidateStore(machine, tracker)
    request = make_submit_request()

    accepted = store.submit(request)
    duplicate = store.submit(make_submit_request(candidate_id="candidate-002"))

    accepted.validate()
    duplicate.validate()
    assert accepted.accepted is True
    assert accepted.terminal_for_agent is True
    assert accepted.candidate_record_sha256 == request.canonical_sha256()
    assert machine.status is AgentWorkflowNodeStatus.CANDIDATE_SUBMITTED
    assert store.candidate is not None
    assert store.candidate.request is request
    assert duplicate.accepted is False
    assert duplicate.rejection_codes == ("candidate_already_frozen",)


def test_candidate_store_accepts_only_one_concurrent_submission() -> None:
    machine = AgentWorkflowStateMachine(status=AgentWorkflowNodeStatus.RUNNING)
    store = AgentWorkflowCandidateStore(machine, AgentWorkflowBudgetTracker(make_budget()))
    requests = [make_submit_request(candidate_id=f"candidate-{index:03d}") for index in range(8)]

    with ThreadPoolExecutor(max_workers=len(requests)) as executor:
        responses = list(executor.map(store.submit, requests))

    assert sum(response.accepted for response in responses) == 1
    assert sum(response.rejection_codes == ("candidate_already_frozen",) for response in responses) == len(requests) - 1
    assert store.candidate is not None
    assert machine.status is AgentWorkflowNodeStatus.CANDIDATE_SUBMITTED


def test_candidate_store_allows_correction_after_contract_rejection() -> None:
    machine = AgentWorkflowStateMachine(status=AgentWorkflowNodeStatus.RUNNING)
    store = AgentWorkflowCandidateStore(machine, AgentWorkflowBudgetTracker(make_budget()))

    rejected = store.submit(make_submit_request(build_system="bazel"))
    accepted = store.submit(make_submit_request())

    assert rejected.rejection_codes == ("invalid_contract",)
    assert accepted.accepted is True
    assert machine.status is AgentWorkflowNodeStatus.CANDIDATE_SUBMITTED


@pytest.mark.parametrize("status", [AgentWorkflowNodeStatus.NO_SUBMISSION, AgentWorkflowNodeStatus.COMPLETED, AgentWorkflowNodeStatus.CANCELLED])
def test_candidate_store_rejects_late_submission(status: AgentWorkflowNodeStatus) -> None:
    machine = AgentWorkflowStateMachine(status=status)
    store = AgentWorkflowCandidateStore(machine, AgentWorkflowBudgetTracker(make_budget()))

    response = store.submit(make_submit_request())

    response.validate()
    assert response.accepted is False
    assert response.rejection_codes == ("node_not_running",)
    assert store.candidate is None
    assert machine.status is status


def test_budget_tracker_rejects_action_before_exceeding_limit() -> None:
    tracker = AgentWorkflowBudgetTracker(make_budget(max_model_requests=1))
    tracker.consume(model_requests=1, recorded_tokens=50)

    with pytest.raises(AgentWorkflowBudgetExceeded) as raised:
        tracker.consume(model_requests=1, recorded_tokens=25)

    assert raised.value.reason == "model_requests"
    assert tracker.snapshot().model_requests == 1
    assert tracker.snapshot().recorded_tokens == 50


def test_budget_tracker_requires_monotonic_elapsed_time() -> None:
    tracker = AgentWorkflowBudgetTracker(make_budget(node_timeout_seconds=10))
    tracker.observe_elapsed(5.0)

    with pytest.raises(ValueError, match="monotonic"):
        tracker.observe_elapsed(4.0)

    with pytest.raises(AgentWorkflowBudgetExceeded) as raised:
        tracker.observe_elapsed(10.1)

    assert raised.value.reason == "node_timeout_seconds"
    assert tracker.snapshot().elapsed_seconds == 5.0


def test_budget_tracker_reports_remaining_budget() -> None:
    tracker = AgentWorkflowBudgetTracker(make_budget(max_model_requests=2, max_recorded_tokens=100, node_timeout_seconds=10))
    tracker.consume(model_requests=1, recorded_tokens=40, agent_steps=2, tool_calls=3, commands=1)
    tracker.observe_elapsed(2.5)

    assert tracker.remaining() == AgentWorkflowRemainingBudget(
        model_requests=1,
        recorded_tokens=60,
        agent_steps=22,
        tool_calls=29,
        commands=23,
        node_seconds=7.5,
    )
