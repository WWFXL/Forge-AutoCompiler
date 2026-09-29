from __future__ import annotations

import copy
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from langchain.agents.middleware.types import ModelResponse
from langchain_core.messages import AIMessage

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = REPO_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_contract_driven_repair_mechanism_v1_formal_protocol as protocol  # noqa: E402
import forge_contract_driven_repair_mechanism_v1_formal_runner as runner  # noqa: E402

from deerflow.compile.agent_workflow_node import (  # noqa: E402
    AgentWorkflowBudgetSnapshot,
    AgentWorkflowBudgetTracker,
)
from deerflow.compile.agent_workflow_schemas import (  # noqa: E402
    AgentWorkflowBudget,
    SubmitCandidateRequest,
)


@pytest.fixture
def manifest() -> dict[str, Any]:
    return protocol.load_manifest()


def _budget() -> AgentWorkflowBudget:
    return AgentWorkflowBudget(
        max_model_requests=8,
        max_recorded_tokens=None,
        max_agent_steps=24,
        max_tool_calls=24,
        max_commands=16,
        node_timeout_seconds=600,
        command_timeout_seconds=300,
        evaluator_timeout_seconds=900,
        replay_timeout_seconds=900,
        cleanup_timeout_seconds=120,
    )


class _Ledger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def append(self, event_type: str, **payload: Any) -> None:
        self.events.append((event_type, payload))


class _Request:
    model_settings: dict[str, Any] = {}

    def override(self, **kwargs: Any) -> _Request:
        self.model_settings = kwargs["model_settings"]
        return self


def _context() -> runner.ContinuationContext:
    return runner.ContinuationContext(
        checkpoint_id="project:delivery_target",
        parent_request={},
        parent_history=[],
        feedback={"accepted": False, "reason": "verification_failed"},
        parent_budget=AgentWorkflowBudgetSnapshot(tool_calls=1),
        expected_model="deepseek-flash",
        provenance_evaluator=None,
        request_attempts=[],
    )


def _response(model: str = "deepseek-flash") -> ModelResponse:
    return ModelResponse(
        result=[
            AIMessage(
                content="ok",
                response_metadata={"model_name": model},
                usage_metadata={
                    "input_tokens": 2,
                    "output_tokens": 1,
                    "total_tokens": 3,
                },
            )
        ]
    )


def _synthetic_results(
    manifest: dict[str, Any],
    outcomes: dict[str, bool],
) -> list[dict[str, Any]]:
    return [
        {
            "checkpoint_id": checkpoint["checkpoint_id"],
            "task_id": checkpoint["task_id"],
            "stratum": checkpoint["stratum"],
            "sequence": arm["sequence"],
            "condition": arm["condition"],
            "status": "complete",
            "strict_post_checkpoint_conversion": outcomes[arm["condition"]],
            "provider_request_attempts": 1,
            "recorded_input_tokens": 2,
            "recorded_output_tokens": 1,
            "recorded_total_tokens": 3,
        }
        for checkpoint in manifest["schedule"]["checkpoints"]
        for arm in checkpoint["arms"]
    ]


def _request(command_id: str) -> SubmitCandidateRequest:
    return SubmitCandidateRequest(
        candidate_id="candidate",
        build_system="cmake",
        supporting_command_ids=(command_id,),
        artifact_paths=("lib/libfixture.a",),
        target_mapping={"fixture": "lib/libfixture.a"},
        recipe_command_ids=(command_id,),
    )


def test_manifest_schema_and_parent_delta_are_deterministic(
    manifest: dict[str, Any],
) -> None:
    assert manifest == protocol.generate_manifest()
    assert json.loads(protocol.DEFAULT_SCHEMA.read_text(encoding="utf-8")) == (protocol.generate_schema(manifest))
    delta = protocol.validate_allowed_delta(manifest)
    assert delta["status"] == "passed"
    assert delta["formal_arm_count"] == 36
    assert delta["formal_provider_request_attempt_limit"] == 288


def test_availability_marker_is_hash_and_semantics_bound(
    manifest: dict[str, Any],
) -> None:
    marker = runner._verify_availability(manifest, runner.DEFAULT_OUTPUT_DIR)
    assert marker["status"] == "passed"
    assert marker["recorded_total_tokens"] == 58
    assert marker["attempts"][0]["actual_model"] == "deepseek-flash"


def test_feedback_is_the_only_arm_state_delta(manifest: dict[str, Any]) -> None:
    checkpoint = manifest["schedule"]["checkpoints"][0]
    projections = runner.qualification.build_projection_set(
        pair_id=checkpoint["checkpoint_id"],
        stratum=checkpoint["stratum"],
        finding={
            "code": "target_mapping_invalid",
            "paths": [],
            "expected": ["target"],
            "actual": ["invalid-target"],
        },
    )
    common = {
        "source": {},
        "parent_history_sha256": "a" * 64,
        "candidate_request_sha256": "b" * 64,
        "rejection_event_sha256": "c" * 64,
        "message_prefix_sha256": "d" * 64,
        "environment": {},
        "budget": {},
        "tool_policy": runner.qualification.TOOL_POLICY,
        "authorities": {},
    }
    states = runner.qualification.build_arm_states(common_state=common, projections=projections)
    assert runner.qualification.validate_state_matched(
        states,
        pair_id=checkpoint["checkpoint_id"],
        stratum=checkpoint["stratum"],
    )


@pytest.mark.parametrize(
    ("build_system", "direct_command"),
    (
        ("cmake", "cmake --build build --parallel 4"),
        ("make", "make -j4"),
        ("autotools", "make -j4"),
    ),
)
def test_generalized_p2_rejects_opaque_and_accepts_direct_tool_evidence(build_system: str, direct_command: str) -> None:
    opaque = SimpleNamespace(
        command_id="opaque",
        command="/tmp/opaque-build.sh",
        exit_code=0,
        timed_out=False,
    )
    direct = SimpleNamespace(
        command_id="direct",
        command=direct_command,
        exit_code=0,
        timed_out=False,
    )
    session = SimpleNamespace(commands=[opaque, direct])
    rejected = runner.evaluate_generalized_p2(
        session,
        _request("opaque"),
        selected_build_system=build_system,
    )
    accepted = runner.evaluate_generalized_p2(
        session,
        _request("direct"),
        selected_build_system=build_system,
    )
    assert (rejected["status"], rejected["reason"]) == (
        "unproven",
        "opaque_wrapper",
    )
    assert (accepted["status"], accepted["reason"]) == (
        "proven",
        "trusted_direct_compiler_tool_surface",
    )


def test_provenance_artifact_stage_fence_is_bounded_to_required_artifacts() -> None:
    command = runner._artifact_stage_fence_command(
        {
            "target_contract": {
                "required_artifacts": [
                    "include/fixture.h",
                    "lib/libfixture.a",
                ]
            }
        }
    )
    assert command == ("test -s /artifacts/include/fixture.h && test -s /artifacts/lib/libfixture.a")


def test_direct_make_install_is_bound_to_artifact_stage_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[str, str]] = []

    def run_tool(
        _session: Any,
        command: str,
        role: str,
        *,
        timeout_seconds: int,
    ) -> SimpleNamespace:
        assert timeout_seconds == 300
        observed.append((command, role))
        return SimpleNamespace(command_id=f"command-{len(observed)}", role=role)

    monkeypatch.setattr(runner, "_run_tool", run_tool)
    monkeypatch.setattr(
        runner,
        "scan_delivery",
        lambda _path: SimpleNamespace(invalid_paths=(), entries=()),
    )
    runner._run_direct_reference_recipe(
        {
            "reference_recipe": ["make -j4", "make install"],
            "target_contract": {"required_artifacts": ["lib/libfixture.a"]},
        },
        SimpleNamespace(leadagent_artifacts_dir="/unused"),
        timeout_seconds=300,
    )
    assert observed == [
        ("make -j4", "build"),
        ("test -d /artifacts && make install", "artifact_stage"),
    ]


def test_delivery_normalization_removes_only_contract_violations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner,
        "scan_delivery",
        lambda _path: SimpleNamespace(
            invalid_paths=("lib/libfixture.so",),
            entries=(
                SimpleNamespace(
                    relative_path="lib/libfixture.a",
                    artifact_type="static_library",
                    size_bytes=8,
                ),
                SimpleNamespace(
                    relative_path="lib/libextra.so.1",
                    artifact_type="shared_library",
                    size_bytes=8,
                ),
                SimpleNamespace(
                    relative_path="share/empty.txt",
                    artifact_type="support_file",
                    size_bytes=0,
                ),
                SimpleNamespace(
                    relative_path="include/fixture/detail.h",
                    artifact_type="support_file",
                    size_bytes=8,
                ),
            ),
        ),
    )
    command = runner._delivery_normalization_command(
        {"target_contract": {"required_artifacts": ["lib/libfixture.a"]}},
        SimpleNamespace(leadagent_artifacts_dir="/unused"),
    )
    assert command == ("rm -f -- /artifacts/lib/libextra.so.1 /artifacts/lib/libfixture.so /artifacts/share/empty.txt")


def test_transport_retry_counts_both_attempts_and_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    context = _context()
    monkeypatch.setattr(runner, "_active_continuation", context)
    tracker = AgentWorkflowBudgetTracker(_budget())
    middleware = runner.FormalExecutionMiddleware(tracker, _Ledger(), time.monotonic())
    calls = 0

    def handler(_request: Any) -> ModelResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError
        return _response()

    response = middleware.wrap_model_call(_Request(), handler)
    assert response == _response()
    assert tracker.snapshot().model_requests == 2
    assert tracker.snapshot().recorded_tokens == 3
    assert [item["retry_eligible"] for item in context.request_attempts] == [
        True,
        False,
    ]


def test_second_transport_failure_censors_arm(monkeypatch: pytest.MonkeyPatch) -> None:
    context = _context()
    monkeypatch.setattr(runner, "_active_continuation", context)
    tracker = AgentWorkflowBudgetTracker(_budget())
    middleware = runner.FormalExecutionMiddleware(tracker, _Ledger(), time.monotonic())

    with pytest.raises(runner.EndpointCensoredError):
        middleware.wrap_model_call(_Request(), lambda _request: (_ for _ in ()).throw(TimeoutError()))
    assert context.endpoint_censored is True
    assert tracker.snapshot().model_requests == 2
    assert len(context.request_attempts) == 2
    assert sum(item["total_tokens"] for item in context.request_attempts) == 0


def test_model_identity_drift_is_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    context = _context()
    monkeypatch.setattr(runner, "_active_continuation", context)
    middleware = runner.FormalExecutionMiddleware(AgentWorkflowBudgetTracker(_budget()), _Ledger(), time.monotonic())
    with pytest.raises(runner.ModelIdentityError):
        middleware.wrap_model_call(_Request(), lambda _request: _response("other"))
    assert context.fatal_error_class == "ModelIdentityError"


def test_complete_prefix_rejects_gaps_and_partial_recovery(manifest: dict[str, Any], tmp_path: Path) -> None:
    first_checkpoint = manifest["schedule"]["checkpoints"][0]
    checkpoint_marker, checkpoint_ledger = runner._checkpoint_paths(manifest, tmp_path, first_checkpoint)
    runner.qualification.persist_checkpoint(
        checkpoint_marker,
        {
            "status": "captured",
            "formal_manifest_sha256": runner._manifest_sha256(manifest),
            "checkpoint_id": first_checkpoint["checkpoint_id"],
        },
    )
    checkpoint_ledger.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_ledger.touch()

    first_arm = first_checkpoint["arms"][0]
    paths = runner._arm_paths(manifest, tmp_path, first_arm)
    result = {
        "manifest_sha256": runner._manifest_sha256(manifest),
        "checkpoint_id": first_checkpoint["checkpoint_id"],
        "sequence": first_arm["sequence"],
        "opaque_clone_id": first_arm["opaque_clone_id"],
        "status": "complete",
    }
    runner._write_once(paths["result"], result)
    runner._write_once(
        paths["marker"],
        {
            "sequence": first_arm["sequence"],
            "opaque_clone_id": first_arm["opaque_clone_id"],
            "status": "complete",
        },
    )
    for name in ("ledger", "runtime_events", "candidate"):
        paths[name].parent.mkdir(parents=True, exist_ok=True)
        paths[name].touch()
    assert len(runner.completed_prefix(manifest, tmp_path)) == 1
    with pytest.raises(runner.FormalRunnerError, match="完整 checkpoint"):
        runner.completed_prefix(manifest, tmp_path, require_checkpoint_boundary=True)

    second_checkpoint = manifest["schedule"]["checkpoints"][1]
    later_arm = second_checkpoint["arms"][0]
    later_paths = runner._arm_paths(manifest, tmp_path, later_arm)
    later_result = copy.deepcopy(result)
    later_result.update(
        checkpoint_id=second_checkpoint["checkpoint_id"],
        sequence=later_arm["sequence"],
        opaque_clone_id=later_arm["opaque_clone_id"],
    )
    runner._write_once(later_paths["result"], later_result)
    runner._write_once(
        later_paths["marker"],
        {
            "sequence": later_arm["sequence"],
            "opaque_clone_id": later_arm["opaque_clone_id"],
            "status": "complete",
        },
    )
    for name in ("ledger", "runtime_events", "candidate"):
        later_paths[name].parent.mkdir(parents=True, exist_ok=True)
        later_paths[name].touch()
    with pytest.raises(runner.FormalRunnerError, match="连续前缀"):
        runner.completed_prefix(manifest, tmp_path)


def test_fixed_sequence_analysis_and_two_censor_stop(manifest: dict[str, Any]) -> None:
    results = _synthetic_results(manifest, {"c0": False, "t1": True, "t2": True})
    report = runner.build_report(manifest, results)
    assert report["primary"]["exact_test"]["p_value"] == pytest.approx(2 / 64)
    assert report["primary_fixed_sequence_gate_passed"] is True
    assert report["secondary"]["exact_test"] is not None
    assert report["supportive"]["exact_test"] is None

    censored = copy.deepcopy(results[:2])
    for item in censored:
        item["status"] = "endpoint_censored"
    stopped = runner.build_report(manifest, censored)
    assert stopped["status"] == "stopped_after_second_endpoint_censor"
    assert stopped["primary"]["exact_test"] is None
    assert stopped["primary"]["identification_interval"] == [-1.0, 1.0]


def test_external_evaluator_input_identity_is_arm_blind(manifest: dict[str, Any]) -> None:
    checkpoint = manifest["schedule"]["checkpoints"][0]
    arm = checkpoint["arms"][0]
    task = runner._task(manifest, checkpoint["task_id"])
    session = SimpleNamespace(
        session_id="formalcontract",
        image_id=manifest["environment_identity"]["image_id"],
    )
    node_input = runner._node_input(
        manifest,
        task,
        session,
        checkpoint["checkpoint_id"],
        arm["opaque_clone_id"],
    )
    payload = json.loads(node_input.canonical_json())
    serialized = json.dumps(payload, sort_keys=True).lower()
    assert "condition" not in payload
    assert "feedback" not in serialized
    assert all(label not in serialized for label in ('"c0"', '"t1"', '"t2"'))


def test_managed_orphan_is_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner.stage_c, "require_zero_managed_resources", lambda: None)
    monkeypatch.setattr(
        runner,
        "_managed_resources",
        lambda: {"containers": ["forge-compile-orphan"], "images": []},
    )
    with pytest.raises(runner.FormalFatalError, match="orphan"):
        runner._require_zero_managed_resources()


def test_output_path_fails_closed(manifest: dict[str, Any], tmp_path: Path) -> None:
    with pytest.raises(runner.FormalRunnerError, match="create-once"):
        runner._output_dir(manifest, tmp_path, runner.REPO_ROOT)
