"""Agent Workflow Runtime v6：在 submit 拒绝后提供有界恢复窗口。"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, fields
from typing import Any, override

from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from deerflow.compile import agent_workflow_runtime as v1
from deerflow.compile import agent_workflow_runtime_v2 as v2
from deerflow.compile import agent_workflow_runtime_v3 as v3
from deerflow.compile import agent_workflow_runtime_v4 as v4
from deerflow.compile import agent_workflow_runtime_v5 as v5
from deerflow.compile.agent_workflow_schemas import AgentBuildNodeInput, AgentBuildNodeResult, SubmitCandidateRequest
from deerflow.compile.candidate_verifier import CandidateVerifier, FunctionalCheckRunner, PrefreezeSubmitCandidateResponse
from deerflow.compile.external_evaluator import FunctionalOracleSpec
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.replay_closure_verifier import ReplayClosureVerifier
from deerflow.compile.schemas import CompileSession

AGENT_WORKFLOW_RUNTIME_VERSION = "agent-workflow-runtime-v6"
PROGRESS_SNAPSHOT_VERSION = "agent-workflow-progress-v3"
_REPAIRABLE_REJECTION_CODES = frozenset({"recipe_execution_failed"})
_MAX_REPAIR_WINDOWS = 1

_ORIGINAL_CREATE_AGENT = v2._ORIGINAL_CREATE_AGENT
_ORIGINAL_CANDIDATE_SERVICE = v2._ORIGINAL_CANDIDATE_SERVICE
_ORIGINAL_NODE_RUNNER = v2._ORIGINAL_NODE_RUNNER
_RUNTIME_BINDING_LOCK = v2._RUNTIME_BINDING_LOCK
_agent_factory = _ORIGINAL_CREATE_AGENT


class AgentWorkflowRuntimeV6Error(RuntimeError):
    """Runtime v6 submit-rejection recovery 合同或串行绑定无效。"""


@dataclass(frozen=True)
class SubmitRecoveryProgressSnapshot(v5.ReplayClosureProgressSnapshot):
    submit_attempted: bool
    submit_rejected_repairable: bool
    repair_build_available: bool
    repair_artifact_stage_available: bool
    repair_window_closed: bool


@dataclass
class _RepairWindow:
    origin_frontier_sha256: str
    current_frontier_sha256: str
    build_consumed: bool = False
    build_succeeded: bool = False
    artifact_stage_consumed: bool = False
    closed: bool = False


def _response_payload(result: ToolMessage | Command) -> dict[str, Any] | None:
    if not isinstance(result, ToolMessage) or not isinstance(result.content, str):
        return None
    try:
        payload = json.loads(result.content)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


class AgentWorkflowCandidateService(v5.AgentWorkflowCandidateService):
    def submit(self, request: SubmitCandidateRequest) -> PrefreezeSubmitCandidateResponse:
        response = super().submit(request)
        if not response.accepted and not response.terminal_for_agent and _REPAIRABLE_REJECTION_CODES.intersection(response.rejection_codes):
            self._release_post_build_phase()
        return response

    def _release_post_build_phase(self) -> None:
        with self.manager.session_lock(self.session.thread_id, self.session.session_id):
            current = self.manager.load_session(self.session.session_id, self.session.thread_id)
            supporting_command_id = current.post_build_supporting_command_id
            if supporting_command_id is None:
                self.session.__dict__.update(current.__dict__)
                return
            current.post_build_supporting_command_id = None
            current.post_build_started_at = None
            current.post_build_commands_remaining = None
            self.manager.save_session(current)
            self.session.__dict__.update(current.__dict__)
        self.manager.log_event(
            self.session,
            "post_build.released",
            supporting_command_id=supporting_command_id,
            reason="workflow_candidate_rejected_repairable",
        )
        self.ledger.append(
            "harness.post_build_released",
            supporting_command_id=supporting_command_id,
            reason="workflow_candidate_rejected_repairable",
        )


class SubmitRejectionRecoveryHarnessMiddleware(v5.ReplayClosureHarnessMiddleware):
    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._repair_window: _RepairWindow | None = None
        self._repair_windows_opened = 0

    def snapshot(self) -> SubmitRecoveryProgressSnapshot:
        base = super().snapshot()
        frontier = self._frontier(base)
        with self._lock:
            attempted = frontier in self._attempted_submission_frontiers
            window = self._repair_window
            active = window is not None and window.current_frontier_sha256 == frontier
            build_available = bool(active and not window.closed and not window.build_consumed)
            stage_available = bool(active and not window.closed and window.build_succeeded and not window.artifact_stage_consumed)
            closed = bool(active and window.closed)
            rejected = bool(active)
        base_payload = {field.name: getattr(base, field.name) for field in fields(v5.ReplayClosureProgressSnapshot)}
        base_payload["schema_version"] = PROGRESS_SNAPSHOT_VERSION
        return SubmitRecoveryProgressSnapshot(
            **base_payload,
            submit_attempted=attempted,
            submit_rejected_repairable=rejected,
            repair_build_available=build_available,
            repair_artifact_stage_available=stage_available,
            repair_window_closed=closed,
        )

    def _active_window(self, snapshot: v4.AgentWorkflowProgressSnapshot) -> _RepairWindow | None:
        frontier = self._frontier(snapshot)
        window = self._repair_window
        if window is None or window.current_frontier_sha256 != frontier:
            return None
        return window

    def _guard_reason(self, request: ToolCallRequest, snapshot: v4.AgentWorkflowProgressSnapshot) -> str | None:
        if request.tool_call.get("name") != "run_container_bash":
            return None
        args = v4._tool_args(request)
        role = args.get("command_role")
        with self._lock:
            window = self._active_window(snapshot)
            if snapshot.candidate_ready and window is not None:
                if window.closed:
                    return "candidate_ready_requires_submit"
                if role == "build" and not window.build_consumed:
                    return None
                if role == "artifact_stage" and window.build_succeeded and not window.artifact_stage_consumed:
                    return None
                return "submit_rejection_repair_window_violation"
            if snapshot.candidate_ready and self._frontier(snapshot) in self._attempted_submission_frontiers:
                return "candidate_ready_requires_submit"
        return super()._guard_reason(request, snapshot)

    def _consume_repair_permission(self, request: ToolCallRequest, snapshot: v4.AgentWorkflowProgressSnapshot) -> tuple[_RepairWindow, str] | None:
        if request.tool_call.get("name") != "run_container_bash":
            return None
        role = v4._tool_args(request).get("command_role")
        with self._lock:
            window = self._active_window(snapshot)
            if window is None or window.closed:
                return None
            if role == "build" and not window.build_consumed:
                window.build_consumed = True
            elif role == "artifact_stage" and window.build_succeeded and not window.artifact_stage_consumed:
                window.artifact_stage_consumed = True
            else:
                return None
            origin = window.origin_frontier_sha256
        self.ledger.append(
            "harness.repair_permission_consumed",
            origin_frontier_sha256=origin,
            snapshot_sha256=snapshot.canonical_sha256(),
            command_role=role,
        )
        return window, role

    @staticmethod
    def _command_succeeded(
        *,
        before: v4.AgentWorkflowProgressSnapshot,
        after: v4.AgentWorkflowProgressSnapshot,
        role: str,
    ) -> bool:
        if after.command_count <= before.command_count:
            return False
        if role == "build":
            return len(after.successful_build_command_ids) > len(before.successful_build_command_ids)
        if role == "artifact_stage":
            return len(after.successful_artifact_stage_command_ids) > len(before.successful_artifact_stage_command_ids)
        return False

    def _finish_repair_action(
        self,
        *,
        before: v4.AgentWorkflowProgressSnapshot,
        window: _RepairWindow,
        role: str,
    ) -> None:
        after = super().snapshot()
        succeeded = self._command_succeeded(before=before, after=after, role=role)
        frontier = self._frontier(after)
        with self._lock:
            window.current_frontier_sha256 = frontier
            if role == "build":
                window.build_succeeded = succeeded
                if not succeeded:
                    window.closed = True
            else:
                window.closed = True
                if not succeeded:
                    window.build_succeeded = False
        self.ledger.append(
            "harness.repair_action_completed",
            origin_frontier_sha256=window.origin_frontier_sha256,
            current_frontier_sha256=frontier,
            command_role=role,
            succeeded=succeeded,
            repair_window_closed=window.closed,
        )

    def _record_submission_result(
        self,
        *,
        before: v4.AgentWorkflowProgressSnapshot,
        result: ToolMessage | Command,
    ) -> None:
        after = super().snapshot()
        frontier = self._frontier(after)
        payload = _response_payload(result)
        accepted = payload.get("accepted") if payload is not None else None
        terminal = payload.get("terminal_for_agent") if payload is not None else None
        raw_codes = payload.get("rejection_codes", []) if payload is not None else []
        rejection_codes = tuple(code for code in raw_codes if isinstance(code, str)) if isinstance(raw_codes, list) else ()
        repairable = accepted is False and terminal is False and bool(_REPAIRABLE_REJECTION_CODES.intersection(rejection_codes))
        with self._lock:
            self._attempted_submission_frontiers.add(frontier)
            opened = False
            if repairable and self._repair_windows_opened < _MAX_REPAIR_WINDOWS:
                if self._repair_window is None or self._repair_window.origin_frontier_sha256 != frontier:
                    self._repair_window = _RepairWindow(
                        origin_frontier_sha256=frontier,
                        current_frontier_sha256=frontier,
                    )
                    self._repair_windows_opened += 1
                    opened = True
        self.ledger.append(
            "harness.submission_frontier_observed",
            pre_submit_frontier_sha256=self._frontier(before),
            post_submit_frontier_sha256=frontier,
            pre_submit_snapshot_sha256=before.canonical_sha256(),
            post_submit_snapshot_sha256=after.canonical_sha256(),
            accepted=accepted,
            terminal_for_agent=terminal,
            rejection_codes=list(rejection_codes),
            repair_window_opened=opened,
        )

    def _wrap_tool_result(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        snapshot = self.snapshot()
        reason = self._guard_reason(request, snapshot)
        if reason is not None:
            return self._blocked_tool_result(request, snapshot, reason)
        repair = self._consume_repair_permission(request, snapshot)
        result = handler(request)
        if repair is not None:
            self._finish_repair_action(before=snapshot, window=repair[0], role=repair[1])
        if request.tool_call.get("name") == "submit_candidate_v1":
            self._record_submission_result(before=snapshot, result=result)
        return result

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        return self._wrap_tool_result(request, handler)

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        snapshot = self.snapshot()
        reason = self._guard_reason(request, snapshot)
        if reason is not None:
            return self._blocked_tool_result(request, snapshot, reason)
        repair = self._consume_repair_permission(request, snapshot)
        result = await handler(request)
        if repair is not None:
            self._finish_repair_action(before=snapshot, window=repair[0], role=repair[1])
        if request.tool_call.get("name") == "submit_candidate_v1":
            self._record_submission_result(before=snapshot, result=result)
        return result


class AgentWorkflowNodeRunner(v5.AgentWorkflowNodeRunner):
    def _build_middlewares(self) -> list[AgentMiddleware]:
        middleware = super()._build_middlewares()
        if self.ledger is None or v5._active_closure_store is None:
            raise AgentWorkflowRuntimeV6Error("Runtime v6 缺少 evidence ledger 或 closure state store")
        recovery = SubmitRejectionRecoveryHarnessMiddleware(
            node_input=self.node_input,
            session=self.session,
            manager=self.manager,
            tracker=self.tracker,
            ledger=self.ledger,
            started_monotonic=self.started_monotonic,
            closure_store=v5._active_closure_store,
        )
        return [recovery if isinstance(item, v5.ReplayClosureHarnessMiddleware) else item for item in middleware]

    def _system_prompt(self) -> str:
        prompt = super()._system_prompt()
        suffix = "\n</agent_workflow_node_v1>"
        if not prompt.endswith(suffix):
            raise AgentWorkflowRuntimeV6Error("Runtime v5 system prompt 结构发生漂移")
        guidance = (
            "After a repairable recipe_execution_failed rejection, the Harness opens one bounded repair window. "
            "Use exactly one corrective build command, then restage the repaired artifact once, and resubmit immediately. "
            "The window is consumed even when a command fails and never bypasses candidate verification or replay closure."
        )
        return prompt[: -len(suffix)] + "\n" + guidance + suffix


def _create_agent_v6(*args: Any, **kwargs: Any) -> Any:
    middleware = kwargs.get("middleware")
    execution = next((item for item in middleware or () if isinstance(item, v1.AgentWorkflowExecutionMiddleware)), None)
    if execution is None:
        raise AgentWorkflowRuntimeV6Error("Runtime v6 缺少 execution middleware")
    return v2._RecursionGuardAgent(_agent_factory(*args, **kwargs), execution)


async def run_agent_workflow_node_v6(
    *,
    node_input: AgentBuildNodeInput,
    session: CompileSession,
    manager: CompileSessionManager,
    model: BaseChatModel,
    oracle_registry: dict[str, FunctionalOracleSpec],
    functional_runner: FunctionalCheckRunner | None = None,
    closure_verifier: ReplayClosureVerifier | None = None,
    finalizer: v1.Finalizer | None = None,
) -> AgentBuildNodeResult:
    """串行绑定 Runtime v6，并在所有终态恢复 v1/v3/v5 模块。"""

    if not _RUNTIME_BINDING_LOCK.acquire(blocking=False):
        raise AgentWorkflowRuntimeV6Error("Runtime v6 只允许单进程串行执行")
    originals = (v1.create_agent, v1.AgentWorkflowCandidateService, v1.AgentWorkflowNodeRunner)
    try:
        expected = (_ORIGINAL_CREATE_AGENT, _ORIGINAL_CANDIDATE_SERVICE, _ORIGINAL_NODE_RUNNER)
        if originals != expected:
            raise AgentWorkflowRuntimeV6Error("Runtime v1 binding 已被其他执行修改")
        spec = v3._resolve_oracle_spec(node_input, oracle_registry)
        v3._active_verifier = CandidateVerifier(oracle_spec=spec, functional_runner=functional_runner)
        v5._active_closure_verifier = closure_verifier or ReplayClosureVerifier(
            timeout_seconds=node_input.budget.replay_timeout_seconds,
        )
        v5._active_closure_store = v5.ReplayClosureStateStore()
        v1.create_agent = _create_agent_v6
        v1.AgentWorkflowCandidateService = AgentWorkflowCandidateService
        v1.AgentWorkflowNodeRunner = AgentWorkflowNodeRunner
        try:
            return await v1.run_agent_workflow_node_v1(
                node_input=node_input,
                session=session,
                manager=manager,
                model=model,
                finalizer=finalizer,
            )
        finally:
            v1.create_agent, v1.AgentWorkflowCandidateService, v1.AgentWorkflowNodeRunner = originals
            v3._active_verifier = None
            v5._active_closure_verifier = None
            v5._active_closure_store = None
    finally:
        _RUNTIME_BINDING_LOCK.release()


__all__ = [
    "AGENT_WORKFLOW_RUNTIME_VERSION",
    "AgentWorkflowCandidateService",
    "AgentWorkflowNodeRunner",
    "AgentWorkflowRuntimeV6Error",
    "PROGRESS_SNAPSHOT_VERSION",
    "SubmitRecoveryProgressSnapshot",
    "SubmitRejectionRecoveryHarnessMiddleware",
    "run_agent_workflow_node_v6",
]
