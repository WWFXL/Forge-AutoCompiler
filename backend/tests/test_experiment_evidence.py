from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow.compile.evidence import (
    EvidenceError,
    ExperimentLedger,
    ExperimentPolicy,
    activate_experiment,
    deactivate_experiment,
    get_active_experiment,
    model_response_metadata,
    new_evidence_id,
    record_experiment_event,
)


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


@pytest.mark.parametrize("build_system", ["cmake", "make", "autotools"])
def test_experiment_policy_persists_supported_build_system_identity(build_system: str) -> None:
    policy = replace(
        make_policy(),
        expected_build_system=build_system,
        cmake_arguments=() if build_system != "cmake" else ("-DBUILD_TESTING=OFF",),
        configure_arguments=("--disable-subunit",) if build_system == "autotools" else (),
    )

    assert policy.to_payload()["expected_build_system"] == build_system


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
