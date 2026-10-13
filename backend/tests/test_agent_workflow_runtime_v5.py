from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage
from test_agent_workflow_runtime_v4 import (
    CapturingScriptedModel,
    FakeManager,
    PassingFunctionalRunner,
    _events,
    _node_input,
    _session,
    _submit_args,
    _tool_call,
)

from deerflow.compile.agent_workflow_runtime_v5 import ReplayClosureStateStore, build_progress_snapshot, run_agent_workflow_node_v5
from deerflow.compile.external_evaluator import FunctionalOracleSpec
from deerflow.compile.replay_closure_verifier import ReplayClosureVerificationResult
from deerflow.compile.schemas import BuildCommandRecord, utc_now_iso


class ScriptedClosureVerifier:
    def __init__(self, result: ReplayClosureVerificationResult):
        self.result = result
        self.calls = 0

    def verify(self, **_kwargs: object) -> ReplayClosureVerificationResult:
        self.calls += 1
        return self.result


def _closure_result(*, passed: bool, classification: str) -> ReplayClosureVerificationResult:
    return ReplayClosureVerificationResult(
        passed=passed,
        classification=classification,
        frontier_sha256="f" * 64,
        recipe_fingerprint="e" * 64,
        exit_code=0 if passed else 2,
        cleanup_succeeded=True,
        expected_delivery=(),
        actual_delivery=(),
        output_excerpt="make: No rule to make target 'generated.c'" if not passed else "",
        duration_seconds=0.1,
    )


def _oracle_registry() -> dict[str, FunctionalOracleSpec]:
    return {
        "oracle-progress-v1": FunctionalOracleSpec(
            oracle_ref="oracle-progress-v1",
            argv=("/bin/true",),
        )
    }


def test_runtime_v5_accepts_candidate_only_after_replay_closure_passes(tmp_path) -> None:
    session = _session(tmp_path)
    closure = ScriptedClosureVerifier(_closure_result(passed=True, classification="passed"))
    model = CapturingScriptedModel(responses=[_tool_call("submit_candidate_v1", _submit_args(), "submit-with-closure")])

    result = asyncio.run(
        run_agent_workflow_node_v5(
            node_input=_node_input(session),
            session=session,
            manager=FakeManager(session),  # type: ignore[arg-type]
            model=model,
            oracle_registry=_oracle_registry(),
            functional_runner=PassingFunctionalRunner(),
            closure_verifier=closure,  # type: ignore[arg-type]
        )
    )

    assert result.node_status == "submitted"
    assert result.candidate_submitted is True
    assert closure.calls == 1
    assert any(event["event_type"] == "candidate.replay_closure_completed" and event["payload"]["passed"] is True for event in _events(session))


def test_runtime_v5_returns_replay_failure_and_keeps_agent_active(tmp_path) -> None:
    session = _session(tmp_path)
    closure = ScriptedClosureVerifier(_closure_result(passed=False, classification="missing_generated_input"))
    model = CapturingScriptedModel(
        responses=[
            _tool_call("submit_candidate_v1", _submit_args(), "submit-missing-input"),
            AIMessage(
                content="无法在本夹具中补充命令。",
                usage_metadata={"input_tokens": 4, "output_tokens": 4, "total_tokens": 8},
            ),
        ]
    )

    result = asyncio.run(
        run_agent_workflow_node_v5(
            node_input=_node_input(session),
            session=session,
            manager=FakeManager(session),  # type: ignore[arg-type]
            model=model,
            oracle_registry=_oracle_registry(),
            functional_runner=PassingFunctionalRunner(),
            closure_verifier=closure,  # type: ignore[arg-type]
        )
    )

    assert result.node_status == "no_submission"
    assert result.candidate_submitted is False
    assert session.status == "inspected"
    assert "missing_generated_input" in str(model.messages_seen[-1][-1].content)
    rejections = [event for event in _events(session) if event["event_type"] == "candidate.submit_rejected"]
    assert rejections[-1]["payload"]["rejection_codes"] == ["missing_generated_input"]


def test_replay_closure_state_is_invalidated_by_new_command(tmp_path) -> None:
    session = _session(tmp_path)
    store = ReplayClosureStateStore()
    store.record(
        command_count=len(session.commands),
        result=_closure_result(passed=True, classification="passed"),
    )

    ready = build_progress_snapshot(
        node_input=_node_input(session),
        session=session,
        closure_store=store,
    )
    assert ready.workspace_ready is True
    assert ready.replay_closure_ready is True

    session.commands.append(
        BuildCommandRecord(
            stage="bash",
            command="make generated.c",
            workdir="/workspace/repo",
            command_id="command-new-frontier",
            role="dependency",
            completed_at=utc_now_iso(),
            exit_code=0,
        )
    )
    stale = build_progress_snapshot(
        node_input=_node_input(session),
        session=session,
        closure_store=store,
    )
    assert stale.workspace_ready is True
    assert stale.replay_closure_ready is False
    assert stale.replay_closure_frontier_sha256 is None
