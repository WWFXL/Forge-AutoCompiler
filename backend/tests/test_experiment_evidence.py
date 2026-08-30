from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow.compile.evidence import (
    AttemptBudgetExceeded,
    EvidenceError,
    ExperimentAttemptBudget,
    ExperimentLedger,
    ExperimentPolicy,
    activate_experiment,
    canonical_json_bytes,
    claim_experiment_clarification_auto_answer,
    deactivate_experiment,
    enforce_experiment_attempt_budget,
    experiment_attempt_budget_snapshot,
    get_active_experiment,
    model_response_metadata,
    new_evidence_id,
    record_agent_tool_failure,
    record_experiment_attempt_budget_completion,
    record_experiment_event,
    record_model_tool_call_origins,
)
from deerflow.tools.builtins.task_tool import _record_subagent_terminal_evidence


def make_policy() -> ExperimentPolicy:
    return ExperimentPolicy(
        benchmark_id="forge-cpp-pilot-v1",
        manifest_sha256="1" * 64,
        case_id="fmt",
        condition="baseline",
        repetition=1,
        expected_repo_url="https://github.com/fmtlib/fmt.git",
        expected_commit_sha="2" * 40,
        expected_build_system="cmake",
        compile_image="autocompiler:gcc13",
        image_id=f"sha256:{'3' * 64}",
        model_name="gpt-5.6-sol",
        endpoint="https://example.invalid/v1",
        credential_env="OpenAI_AK",
        request_timeout_seconds=120,
        model_max_retries=0,
        compiler_max_turns=36,
        subagent_timeout_seconds=180,
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=("ninja-build",),
        cmake_arguments=("-DBUILD_TESTING=OFF",),
        configure_arguments=(),
        environment=(("CFLAGS", "-O2"),),
        minimum_replay_delay_seconds=0,
    )


def create_ledger(tmp_path: Path) -> ExperimentLedger:
    return ExperimentLedger.create(
        tmp_path / "attempt.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"thread_id": new_evidence_id("thread"), "policy": make_policy().to_payload()},
    )


def test_legacy_policy_payload_is_unchanged_and_future_budgets_are_explicit() -> None:
    legacy_payload = make_policy().to_payload()

    assert "compiler_model_turn_limit" not in legacy_payload
    assert "compiler_graph_recursion_limit" not in legacy_payload
    assert "compiler_wall_clock_seconds" not in legacy_payload
    assert "compiler_post_build_reserve_seconds" not in legacy_payload

    future_payload = replace(
        make_policy(),
        compiler_model_turn_limit=12,
        compiler_graph_recursion_limit=48,
        compiler_wall_clock_seconds=300,
        compiler_post_build_reserve_seconds=60,
    ).to_payload()
    assert future_payload["compiler_model_turn_limit"] == 12
    assert future_payload["compiler_graph_recursion_limit"] == 48
    assert future_payload["compiler_wall_clock_seconds"] == 300
    assert future_payload["compiler_post_build_reserve_seconds"] == 60


def test_future_budget_policy_rejects_reserve_without_execution_window() -> None:
    with pytest.raises(EvidenceError, match="must be smaller"):
        replace(
            make_policy(),
            compiler_wall_clock_seconds=60,
            compiler_post_build_reserve_seconds=60,
        )


def test_ledger_builds_contiguous_hash_chain_and_becomes_immutable(tmp_path: Path) -> None:
    ledger = create_ledger(tmp_path)
    ledger.append("preflight.completed", {"ready": True})
    ledger.append("experiment.completed", {"status": "passed"})

    events = ExperimentLedger.verify_path(ledger.path)

    assert [event["sequence"] for event in events] == [1, 2, 3]
    assert events[0]["previous_event_sha256"] is None
    assert events[1]["previous_event_sha256"] == events[0]["event_sha256"]
    assert events[2]["previous_event_sha256"] == events[1]["event_sha256"]
    with pytest.raises(EvidenceError, match="immutable"):
        ledger.append("oracle.completed", {"passed": True})


def test_ledger_detects_tampering(tmp_path: Path) -> None:
    ledger = create_ledger(tmp_path)
    ledger.append("preflight.completed", {"ready": False})
    records = [json.loads(line) for line in ledger.path.read_text(encoding="utf-8").splitlines()]
    records[1]["payload"]["ready"] = True
    ledger.path.write_text(
        "\n".join(json.dumps(record, sort_keys=True, separators=(",", ":")) for record in records) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(EvidenceError, match="invalid event digest"):
        ExperimentLedger.verify_path(ledger.path)


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"credential": "sk-example-secret-value-123456789"}, "credential-like"),
        ({"artifact_path": r"C:\\Users\\YiWei\\private\\artifact"}, "host path"),
        ({"command": "cmake --build build"}, "forbidden"),
    ],
)
def test_ledger_rejects_sensitive_or_raw_evidence(
    tmp_path: Path,
    payload: dict[str, str],
    message: str,
) -> None:
    ledger = create_ledger(tmp_path)

    with pytest.raises(EvidenceError, match=message):
        ledger.append("unsafe.observed", payload)


def test_active_experiment_registry_routes_events_to_one_thread(tmp_path: Path) -> None:
    ledger = create_ledger(tmp_path)
    policy = make_policy()
    thread_id = new_evidence_id("thread")
    active = activate_experiment(
        thread_id=thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=policy,
    )
    try:
        assert get_active_experiment(thread_id) is active
        assert record_experiment_event(thread_id, "model.request_started", attempt=1) is not None
        assert record_experiment_event("unrelated-thread", "model.request_started", attempt=1) is None
    finally:
        assert deactivate_experiment(thread_id) is active

    events = ledger.read()
    assert [event["event"] for event in events] == ["experiment.started", "model.request_started"]
    assert get_active_experiment(thread_id) is None


def test_attempt_budget_claims_are_atomic_and_hash_chained(tmp_path: Path) -> None:
    ledger = create_ledger(tmp_path)
    thread_id = ledger.read()[0]["payload"]["thread_id"]
    budget = ExperimentAttemptBudget(
        total_wall_clock_seconds=60,
        cleanup_reserve_seconds=10,
        max_compiler_invocations=2,
        max_model_requests=2,
    )
    active = activate_experiment(
        thread_id=thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=make_policy(),
        attempt_budget=budget,
    )

    def claim_provider() -> bool:
        try:
            enforce_experiment_attempt_budget(
                thread_id,
                "before_provider_request",
            )
        except AttemptBudgetExceeded:
            return False
        return True

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            allowed = list(pool.map(lambda _index: claim_provider(), range(8)))
        snapshot = experiment_attempt_budget_snapshot(thread_id)
        assert snapshot is not None
        assert sum(allowed) == 2
        assert snapshot["model_requests_claimed"] == 2
        assert snapshot["model_request_limit_reached"] is True
        completion = record_experiment_attempt_budget_completion(thread_id)
        assert completion is not None
        assert completion["model_requests_claimed"] == 2
    finally:
        assert deactivate_experiment(thread_id) is active

    events = ExperimentLedger.verify_path(ledger.path)
    checkpoints = [event for event in events if event["event"] == "attempt.budget_checkpoint"]
    assert len(checkpoints) == 8
    assert sum(event["payload"]["allowed"] for event in checkpoints) == 2
    assert events[-1]["event"] == "attempt.budget_completed"


def test_attempt_budget_rejects_third_compiler_claim_atomically(
    tmp_path: Path,
) -> None:
    ledger = create_ledger(tmp_path)
    thread_id = ledger.read()[0]["payload"]["thread_id"]
    active = activate_experiment(
        thread_id=thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=make_policy(),
        attempt_budget=ExperimentAttemptBudget(
            total_wall_clock_seconds=60,
            cleanup_reserve_seconds=10,
            max_compiler_invocations=2,
            max_model_requests=48,
        ),
    )

    def claim_compiler() -> bool:
        try:
            enforce_experiment_attempt_budget(
                thread_id,
                "before_compiler_invocation",
            )
        except AttemptBudgetExceeded:
            return False
        return True

    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            allowed = list(pool.map(lambda _index: claim_compiler(), range(6)))
        snapshot = experiment_attempt_budget_snapshot(thread_id)
        assert snapshot is not None
        assert sum(allowed) == 2
        assert snapshot["compiler_invocations_claimed"] == 2
        assert snapshot["compiler_invocations_completed"] == 0
    finally:
        assert deactivate_experiment(thread_id) is active


def test_attempt_budget_rejects_new_work_but_never_cleanup(tmp_path: Path) -> None:
    ledger = create_ledger(tmp_path)
    thread_id = ledger.read()[0]["payload"]["thread_id"]
    now = [100.0]
    active = activate_experiment(
        thread_id=thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=make_policy(),
        attempt_budget=ExperimentAttemptBudget(
            total_wall_clock_seconds=20,
            cleanup_reserve_seconds=5,
            max_compiler_invocations=2,
            max_model_requests=48,
        ),
        monotonic_clock=lambda: now[0],
    )
    try:
        now[0] = 115.0
        with pytest.raises(AttemptBudgetExceeded) as rejected:
            enforce_experiment_attempt_budget(
                thread_id,
                "before_submit_or_replay",
            )
        assert rejected.value.classification == "attempt_budget_exhausted"

        now[0] = 121.0
        finalize = enforce_experiment_attempt_budget(
            thread_id,
            "before_finalize",
        )
        cleanup = enforce_experiment_attempt_budget(
            thread_id,
            "before_cleanup",
        )
        assert finalize is not None
        assert cleanup is not None
        assert finalize["within_total_wall_clock"] is False
        assert cleanup["cleanup_required"] is True
    finally:
        assert deactivate_experiment(thread_id) is active


def test_experiment_without_attempt_budget_preserves_legacy_behavior(
    tmp_path: Path,
) -> None:
    ledger = create_ledger(tmp_path)
    thread_id = ledger.read()[0]["payload"]["thread_id"]
    active = activate_experiment(
        thread_id=thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=make_policy(),
    )
    try:
        assert (
            enforce_experiment_attempt_budget(
                thread_id,
                "before_provider_request",
            )
            is None
        )
        assert experiment_attempt_budget_snapshot(thread_id) is None
    finally:
        assert deactivate_experiment(thread_id) is active

    assert [event["event"] for event in ledger.read()] == ["experiment.started"]


@pytest.mark.parametrize(
    ("status", "classification"),
    [
        ("timed_out", "subagent_timeout"),
        ("failed", "recursion_limit"),
    ],
)
def test_subagent_termination_builds_valid_hash_chained_failure_evidence(
    tmp_path: Path,
    status: str,
    classification: str,
) -> None:
    ledger = create_ledger(tmp_path)
    thread_id = ledger.read()[0]["payload"]["thread_id"]
    active = activate_experiment(
        thread_id=thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=make_policy(),
    )
    try:
        _record_subagent_terminal_evidence(
            thread_id=thread_id,
            task_id="compiler-task-1",
            subagent_type="compiler",
            status=status,
            classification=classification,
            worker_stopped=True,
        )
    finally:
        assert deactivate_experiment(thread_id) is active

    events = ExperimentLedger.verify_path(ledger.path)
    assert [event["event"] for event in events] == [
        "experiment.started",
        "agent.subagent_terminated",
        "failure.recorded",
    ]
    assert events[1]["payload"]["classification"] == classification
    assert events[1]["payload"]["worker_stopped"] is True
    assert events[2]["payload"]["domain"] == "agent_tool"
    assert events[2]["payload"]["classification"] == classification


def test_subagent_termination_accepts_only_bounded_budget_snapshot(tmp_path: Path) -> None:
    ledger = create_ledger(tmp_path)
    snapshot = {
        "model_turn_limit": 12,
        "model_turn_count": 4,
        "graph_recursion_limit": 48,
        "wall_clock_limit_seconds": 300,
        "elapsed_seconds": 45.125,
        "post_build_reserve_seconds": 60,
        "post_build_started": False,
    }

    ledger.append(
        "agent.subagent_terminated",
        {
            "task_id": "compiler-task-1",
            "role": "compiler",
            "status": "failed",
            "classification": "model_turn_limit",
            "worker_stopped": True,
            "budget_snapshot": snapshot,
        },
    )

    assert ExperimentLedger.verify_path(ledger.path)[-1]["payload"]["budget_snapshot"] == snapshot

    with pytest.raises(EvidenceError, match="budget_snapshot has an invalid schema"):
        ledger.append(
            "agent.subagent_terminated",
            {
                "task_id": "compiler-task-2",
                "role": "compiler",
                "status": "failed",
                "classification": "model_turn_limit",
                "worker_stopped": True,
                "budget_snapshot": {**snapshot, "detail": "must not be recorded"},
            },
        )


def test_agent_tool_failure_records_only_bounded_identity_and_exception_class(
    tmp_path: Path,
) -> None:
    ledger = create_ledger(tmp_path)
    thread_id = new_evidence_id("thread")
    request = SimpleNamespace(
        tool_call={"name": "task", "id": "call-safe-123"},
        runtime=SimpleNamespace(
            context={"thread_id": thread_id, "agent_name": "compiler"},
            config={"configurable": {}},
        ),
    )
    exception_detail = "sk-this-must-not-enter-ledger C:\\Users\\YiWei\\private"
    activate_experiment(
        thread_id=thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=make_policy(),
    )
    try:
        record_agent_tool_failure(
            request,
            RuntimeError(exception_detail),
            execution_mode="async",
        )
    finally:
        deactivate_experiment(thread_id)

    payload = ledger.read()[-1]["payload"]
    assert payload == {
        "failure_id": payload["failure_id"],
        "role": "compiler",
        "tool_name": "task",
        "tool_call_id": "call-safe-123",
        "exception_class": "RuntimeError",
        "execution_mode": "async",
        "terminal": False,
    }
    assert exception_detail not in ledger.path.read_text(encoding="utf-8")


def test_classified_tool_failure_records_atomic_observability_without_raw_command(
    tmp_path: Path,
) -> None:
    ledger = create_ledger(tmp_path)
    thread_id = new_evidence_id("thread")
    model_request_id = new_evidence_id("model_request")
    command = "ls -la /workspace/repo && echo sensitive-value-must-not-enter-ledger"
    tool_call = {
        "name": "run_container_bash",
        "id": "call-observed-2",
        "args": {"command": command, "command_role": "other"},
    }
    request = SimpleNamespace(
        tool_call=tool_call,
        runtime=SimpleNamespace(
            context={"thread_id": thread_id, "agent_name": "compiler"},
            config={"configurable": {}},
        ),
    )
    activate_experiment(
        thread_id=thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=make_policy(),
    )
    try:
        response = SimpleNamespace(
            result=[
                SimpleNamespace(
                    tool_calls=[
                        {"name": "run_container_bash", "id": "call-observed-1", "args": {}},
                        tool_call,
                    ]
                )
            ]
        )
        assert record_model_tool_call_origins(thread_id, response, model_request_id=model_request_id) == 2
        record_agent_tool_failure(
            request,
            EvidenceError(
                "raw error must not enter ledger",
                rejection_classification="compound_shell_forbidden",
                action_kind="inspection",
            ),
            execution_mode="async",
        )
    finally:
        deactivate_experiment(thread_id)

    payload = ledger.read()[-1]["payload"]
    assert payload["rejection_classification"] == "compound_shell_forbidden"
    assert payload["action_kind"] == "inspection"
    assert payload["model_request_id"] == model_request_id
    assert payload["tool_ordinal"] == 2
    assert payload["command_sha256"] == hashlib.sha256(command.encode()).hexdigest()
    persisted = ledger.path.read_text(encoding="utf-8")
    assert command not in persisted
    assert "raw error must not enter ledger" not in persisted


def test_ambiguous_or_unknown_tool_call_origin_keeps_legacy_failure_schema(
    tmp_path: Path,
) -> None:
    ledger = create_ledger(tmp_path)
    thread_id = new_evidence_id("thread")
    model_request_id = new_evidence_id("model_request")
    duplicate = {"name": "run_container_bash", "id": "call-duplicate", "args": {"command": "pwd"}}
    request = SimpleNamespace(
        tool_call=duplicate,
        runtime=SimpleNamespace(context={"thread_id": thread_id, "agent_name": "compiler"}),
    )
    activate_experiment(
        thread_id=thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=make_policy(),
    )
    try:
        response = SimpleNamespace(result=[SimpleNamespace(tool_calls=[duplicate, duplicate])])
        assert record_model_tool_call_origins(thread_id, response, model_request_id=model_request_id) == 0
        record_agent_tool_failure(
            request,
            EvidenceError(
                "ambiguous",
                rejection_classification="inspection_budget_exhausted",
                action_kind="inspection",
            ),
            execution_mode="sync",
        )
    finally:
        deactivate_experiment(thread_id)

    payload = ledger.read()[-1]["payload"]
    assert set(payload) == {
        "failure_id",
        "role",
        "tool_name",
        "tool_call_id",
        "exception_class",
        "execution_mode",
        "terminal",
    }


def test_agent_event_schema_rejects_raw_or_inconsistent_payloads(
    tmp_path: Path,
) -> None:
    ledger = create_ledger(tmp_path)
    with pytest.raises(EvidenceError, match="agent.tool_failed schema"):
        ledger.append(
            "agent.tool_failed",
            {
                "failure_id": new_evidence_id("failure"),
                "role": "lead",
                "tool_name": "task",
                "tool_call_id": "call-1",
                "exception_class": "RuntimeError",
                "execution_mode": "async",
                "terminal": False,
                "detail": "raw exception detail is forbidden by schema",
            },
        )
    with pytest.raises(EvidenceError, match="compile_tool_call_count must be zero"):
        ledger.append(
            "agent.no_compile_progress",
            {
                "failure_id": new_evidence_id("failure"),
                "classification": "no_compile_tool_call",
                "completed_model_request_count": 1,
                "tool_call_count": 1,
                "compile_tool_call_count": 1,
                "stream_completed": True,
                "terminal": True,
            },
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("rejection_classification", "not_preregistered", "rejection_classification is invalid"),
        ("action_kind", "filesystem", "action_kind is invalid"),
        ("model_request_id", "request-1", "model_request_id must be a stable evidence ID"),
        ("tool_ordinal", 0, "tool_ordinal must be a positive integer"),
        ("command_sha256", "bad", "command_sha256 must be a lowercase SHA-256 digest"),
    ],
)
def test_agent_tool_failure_observability_schema_rejects_invalid_values(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    ledger = create_ledger(tmp_path)
    payload = {
        "failure_id": new_evidence_id("failure"),
        "role": "compiler",
        "tool_name": "run_container_bash",
        "tool_call_id": "call-1",
        "exception_class": "RuntimeParityGateError",
        "execution_mode": "async",
        "terminal": False,
        "rejection_classification": "compound_shell_forbidden",
        "action_kind": "inspection",
        "model_request_id": new_evidence_id("model_request"),
        "tool_ordinal": 1,
        "command_sha256": "a" * 64,
    }
    payload[field] = value
    with pytest.raises(EvidenceError, match=message):
        ledger.append("agent.tool_failed", payload)


def test_experiment_clarification_auto_answer_is_claimed_once(tmp_path: Path) -> None:
    ledger = create_ledger(tmp_path)
    thread_id = new_evidence_id("thread")
    request = SimpleNamespace(
        runtime=SimpleNamespace(
            context={"thread_id": thread_id},
            config={"configurable": {}},
        )
    )
    policy = make_policy()
    compiler_request = SimpleNamespace(
        runtime=SimpleNamespace(
            context={"thread_id": thread_id, "agent_name": "compiler"},
            config={"configurable": {}},
        )
    )
    activate_experiment(
        thread_id=thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=policy,
    )
    try:
        assert claim_experiment_clarification_auto_answer(compiler_request) is None
        assert claim_experiment_clarification_auto_answer(request) is policy
        assert claim_experiment_clarification_auto_answer(request) is None
    finally:
        deactivate_experiment(thread_id)

    repair_events = [event for event in ledger.read() if event["event"] == "agent.clarification_auto_answered"]
    assert len(repair_events) == 1
    assert repair_events[0]["payload"] == {
        "repair_id": repair_events[0]["payload"]["repair_id"],
        "role": "lead",
        "reason": "non_interactive_frozen_policy",
        "auto_answer_count": 1,
        "max_auto_answers": 1,
        "terminal": False,
    }


def test_agent_event_schema_rejects_digest_valid_tampering(tmp_path: Path) -> None:
    ledger = create_ledger(tmp_path)
    ledger.append(
        "agent.no_compile_progress",
        {
            "failure_id": new_evidence_id("failure"),
            "classification": "no_compile_tool_call",
            "completed_model_request_count": 1,
            "tool_call_count": 0,
            "compile_tool_call_count": 0,
            "stream_completed": True,
            "terminal": True,
        },
    )
    records = [json.loads(line) for line in ledger.path.read_text(encoding="utf-8").splitlines()]
    records[-1]["payload"]["completed_model_request_count"] = -1
    unsigned = {key: value for key, value in records[-1].items() if key != "event_sha256"}
    records[-1]["event_sha256"] = hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()
    ledger.path.write_text(
        "\n".join(json.dumps(record, sort_keys=True, separators=(",", ":")) for record in records) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        EvidenceError,
        match="completed_model_request_count must be a non-negative integer",
    ):
        ExperimentLedger.verify_path(ledger.path)


def test_completed_ledger_rejects_late_agent_evidence(tmp_path: Path) -> None:
    ledger = create_ledger(tmp_path)
    ledger.append("experiment.completed", {"status": "failed"})

    with pytest.raises(EvidenceError, match="immutable"):
        ledger.append(
            "agent.no_compile_progress",
            {
                "failure_id": new_evidence_id("failure"),
                "classification": "no_compile_tool_call",
                "completed_model_request_count": 1,
                "tool_call_count": 0,
                "compile_tool_call_count": 0,
                "stream_completed": True,
                "terminal": True,
            },
        )


@pytest.mark.parametrize("build_system", ["cmake", "make", "autotools"])
def test_experiment_policy_persists_supported_build_system_identity(build_system: str) -> None:
    policy = replace(
        make_policy(),
        expected_build_system=build_system,
        cmake_arguments=() if build_system != "cmake" else ("-DBUILD_TESTING=OFF",),
        configure_arguments=("--disable-subunit",) if build_system == "autotools" else (),
    )

    assert policy.to_payload()["expected_build_system"] == build_system
    assert policy.selected_build_system == build_system


def test_experiment_policy_rejects_build_system_argument_drift() -> None:
    with pytest.raises(EvidenceError, match="expected_build_system"):
        replace(make_policy(), expected_build_system="meson")
    with pytest.raises(EvidenceError, match="cmake_arguments"):
        replace(make_policy(), expected_build_system="make")


def test_model_response_metadata_reads_bounded_model_response_messages() -> None:
    response = SimpleNamespace(
        result=[
            SimpleNamespace(
                response_metadata={},
                usage_metadata={"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
            ),
            SimpleNamespace(
                response_metadata={"model_name": "provider-confirmed-model"},
                usage_metadata=None,
            ),
        ]
    )

    actual_model, usage = model_response_metadata(response)

    assert actual_model == "provider-confirmed-model"
    assert usage == {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}


def test_model_response_metadata_keeps_unobserved_model_null() -> None:
    response = SimpleNamespace(
        result=[
            SimpleNamespace(
                response_metadata={"finish_reason": "stop"},
                usage_metadata=None,
                content="must not be inspected",
            )
        ]
    )

    actual_model, usage = model_response_metadata(response)

    assert actual_model is None
    assert usage == {"input_tokens": None, "output_tokens": None, "total_tokens": None}


def test_model_response_metadata_rejects_unsafe_model_and_boolean_usage() -> None:
    response = SimpleNamespace(
        result=[
            SimpleNamespace(
                response_metadata={"model_name": "unsafe\nmodel"},
                usage_metadata={"input_tokens": True},
            )
        ]
    )

    actual_model, usage = model_response_metadata(response)

    assert actual_model is None
    assert usage == {"input_tokens": None, "output_tokens": None, "total_tokens": None}


def test_model_response_metadata_reads_at_most_eight_messages() -> None:
    messages = [SimpleNamespace(response_metadata={}, usage_metadata=None) for _ in range(8)]
    messages.append(
        SimpleNamespace(
            response_metadata={"model_name": "out-of-bounds-model"},
            usage_metadata={"total_tokens": 99},
        )
    )

    actual_model, usage = model_response_metadata(SimpleNamespace(result=messages))

    assert actual_model is None
    assert usage == {"input_tokens": None, "output_tokens": None, "total_tokens": None}
