from __future__ import annotations

import asyncio
import json
import time
from dataclasses import replace
from types import SimpleNamespace

from langchain_core.messages import ToolMessage
from test_agent_workflow_runtime_v4 import (
    CapturingScriptedModel,
    FakeManager,
    PassingFunctionalRunner,
    RecordingLedger,
    _budget,
    _node_input,
    _session,
    _tool_call,
)

from deerflow.compile.agent_workflow_runtime import AgentWorkflowBudgetTracker
from deerflow.compile.agent_workflow_runtime_v5 import ReplayClosureStateStore
from deerflow.compile.agent_workflow_runtime_v6 import SubmitRejectionRecoveryHarnessMiddleware, run_agent_workflow_node_v6
from deerflow.compile.external_evaluator import FunctionalOracleSpec
from deerflow.compile.replay_closure_verifier import ReplayClosureVerificationResult
from deerflow.compile.schemas import BuildCommandRecord, utc_now_iso


def _request(name: str, call_id: str, *, role: str | None = None) -> SimpleNamespace:
    args = {} if role is None else {"command_role": role}
    return SimpleNamespace(tool_call={"name": name, "args": args, "id": call_id})


def _response(
    call_id: str,
    *,
    accepted: bool,
    terminal: bool,
    codes: list[str] | None = None,
) -> ToolMessage:
    return ToolMessage(
        content=json.dumps(
            {
                "accepted": accepted,
                "terminal_for_agent": terminal,
                "rejection_codes": codes or [],
            }
        ),
        tool_call_id=call_id,
        name="submit_candidate_v1",
        status="success" if accepted else "error",
    )


def _middleware(tmp_path):
    session = _session(tmp_path)
    ledger = RecordingLedger()
    middleware = SubmitRejectionRecoveryHarnessMiddleware(
        node_input=_node_input(session),
        session=session,
        manager=FakeManager(session),  # type: ignore[arg-type]
        tracker=AgentWorkflowBudgetTracker(_budget()),
        ledger=ledger,  # type: ignore[arg-type]
        started_monotonic=time.monotonic(),
        closure_store=ReplayClosureStateStore(),
    )
    return session, ledger, middleware


def _append_command(session, *, command_id: str, role: str, exit_code: int = 0) -> ToolMessage:
    session.commands.append(
        BuildCommandRecord(
            stage="bash",
            command="make -C test test" if role == "build" else "install -Dm755 test/unit_test /artifacts/bin/unit_test",
            workdir="/workspace/repo",
            command_id=command_id,
            role=role,
            completed_at=utc_now_iso(),
            exit_code=exit_code,
        )
    )
    return ToolMessage(content=f"exit_code={exit_code}", tool_call_id=command_id, name="run_container_bash")


def test_ready_frontier_still_requires_submit_before_shell(tmp_path) -> None:
    _session_value, _ledger, middleware = _middleware(tmp_path)

    result = middleware._wrap_tool_result(
        _request("run_container_bash", "build-before-submit", role="build"),
        lambda _request_value: raise_unexpected(),
    )

    assert isinstance(result, ToolMessage)
    assert json.loads(result.content)["reason"] == "candidate_ready_requires_submit"


def test_repairable_rejection_allows_one_build_and_one_stage_then_requires_submit(tmp_path) -> None:
    session, ledger, middleware = _middleware(tmp_path)
    pre_submit_count = len(session.commands)

    def reject_with_new_smoke(_request_value):
        _append_command(session, command_id="trusted-smoke", role="smoke")
        return _response(
            "submit-rejected",
            accepted=False,
            terminal=False,
            codes=["recipe_execution_failed"],
        )

    middleware._wrap_tool_result(
        _request("submit_candidate_v1", "submit-rejected"),
        reject_with_new_smoke,
    )
    snapshot = middleware.snapshot()
    assert snapshot.command_count == pre_submit_count + 1
    assert snapshot.submit_rejected_repairable is True
    assert snapshot.repair_build_available is True

    middleware._wrap_tool_result(
        _request("run_container_bash", "repair-build", role="build"),
        lambda _request_value: _append_command(session, command_id="repair-build", role="build"),
    )
    after_build = middleware.snapshot()
    assert after_build.repair_build_available is False
    assert after_build.repair_artifact_stage_available is True

    second_build = middleware._wrap_tool_result(
        _request("run_container_bash", "second-build", role="build"),
        lambda _request_value: raise_unexpected(),
    )
    assert isinstance(second_build, ToolMessage)
    assert json.loads(second_build.content)["reason"] == "submit_rejection_repair_window_violation"

    middleware._wrap_tool_result(
        _request("run_container_bash", "repair-stage", role="artifact_stage"),
        lambda _request_value: _append_command(session, command_id="repair-stage", role="artifact_stage"),
    )
    after_stage = middleware.snapshot()
    assert after_stage.repair_window_closed is True

    extra_stage = middleware._wrap_tool_result(
        _request("run_container_bash", "extra-stage", role="artifact_stage"),
        lambda _request_value: raise_unexpected(),
    )
    assert isinstance(extra_stage, ToolMessage)
    assert json.loads(extra_stage.content)["reason"] == "candidate_ready_requires_submit"

    events = [event for event, _payload in ledger.events]
    assert events.count("harness.repair_permission_consumed") == 2
    assert events.count("harness.repair_action_completed") == 2


def test_failed_build_consumes_and_closes_repair_window(tmp_path) -> None:
    session, _ledger, middleware = _middleware(tmp_path)
    middleware._wrap_tool_result(
        _request("submit_candidate_v1", "submit-rejected"),
        lambda _request_value: _response(
            "submit-rejected",
            accepted=False,
            terminal=False,
            codes=["recipe_execution_failed"],
        ),
    )
    middleware._wrap_tool_result(
        _request("run_container_bash", "failed-build", role="build"),
        lambda _request_value: _append_command(session, command_id="failed-build", role="build", exit_code=2),
    )

    snapshot = middleware.snapshot()
    assert snapshot.repair_window_closed is True
    assert snapshot.repair_artifact_stage_available is False


def test_nonrepairable_and_terminal_responses_do_not_open_window(tmp_path) -> None:
    for index, response in enumerate(
        (
            _response("invalid", accepted=False, terminal=False, codes=["invalid_contract"]),
            _response("terminal", accepted=False, terminal=True, codes=["recipe_execution_failed"]),
            ToolMessage(content="not-json", tool_call_id="malformed", name="submit_candidate_v1", status="error"),
        )
    ):
        _session_value, _ledger, middleware = _middleware(tmp_path / str(index))
        middleware._wrap_tool_result(
            _request("submit_candidate_v1", f"submit-{index}"),
            lambda _request_value, result=response: result,
        )
        blocked = middleware._wrap_tool_result(
            _request("run_container_bash", f"build-{index}", role="build"),
            lambda _request_value: raise_unexpected(),
        )
        assert isinstance(blocked, ToolMessage)
        assert json.loads(blocked.content)["reason"] == "candidate_ready_requires_submit"


def test_async_path_matches_sync_repair_window(tmp_path) -> None:
    session, _ledger, middleware = _middleware(tmp_path)

    async def scenario() -> None:
        async def rejected(_request_value):
            return _response(
                "async-submit",
                accepted=False,
                terminal=False,
                codes=["recipe_execution_failed"],
            )

        await middleware.awrap_tool_call(
            _request("submit_candidate_v1", "async-submit"),
            rejected,
        )

        async def built(_request_value):
            return _append_command(session, command_id="async-build", role="build")

        await middleware.awrap_tool_call(
            _request("run_container_bash", "async-build", role="build"),
            built,
        )

    asyncio.run(scenario())
    assert middleware.snapshot().repair_artifact_stage_available is True


def test_runtime_v6_budget_exhaustion_closes_without_executing_blocked_shell(tmp_path) -> None:
    session = _session(tmp_path)
    node_input = _node_input(session)
    node_input = replace(node_input, budget=replace(node_input.budget, max_model_requests=1))
    model = CapturingScriptedModel(
        responses=[
            _tool_call(
                "run_container_bash",
                {
                    "command": "make",
                    "command_role": "build",
                    "timeout_seconds": 30,
                    "workdir": "/workspace/repo",
                },
                "blocked-before-submit",
            )
        ]
    )

    class UnusedClosureVerifier:
        def verify(self, **_kwargs: object) -> ReplayClosureVerificationResult:
            raise AssertionError("预算终止案例不得执行 replay closure")

    result = asyncio.run(
        run_agent_workflow_node_v6(
            node_input=node_input,
            session=session,
            manager=FakeManager(session),  # type: ignore[arg-type]
            model=model,
            oracle_registry={
                "oracle-progress-v1": FunctionalOracleSpec(
                    oracle_ref="oracle-progress-v1",
                    argv=("/bin/true",),
                )
            },
            functional_runner=PassingFunctionalRunner(),
            closure_verifier=UnusedClosureVerifier(),  # type: ignore[arg-type]
        )
    )

    assert result.node_status == "no_submission"
    assert result.primary_failure == "budget_exhausted"
    assert result.budget_terminal_reason == "model_requests"
    assert result.usage.model_requests == 1
    assert result.usage.commands == 0
    assert len(session.commands) == 4


def raise_unexpected():
    raise AssertionError("被拒绝的工具不得执行 handler")
