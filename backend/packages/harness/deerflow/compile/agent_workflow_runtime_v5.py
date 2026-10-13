"""Agent Workflow Runtime v5：在候选冻结前验证 replay closure。"""

from __future__ import annotations

import threading
from dataclasses import dataclass, fields
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel

from deerflow.compile import agent_workflow_runtime as v1
from deerflow.compile import agent_workflow_runtime_v2 as v2
from deerflow.compile import agent_workflow_runtime_v3 as v3
from deerflow.compile import agent_workflow_runtime_v4 as v4
from deerflow.compile.agent_workflow_schemas import AgentBuildNodeInput, AgentBuildNodeResult, SubmitCandidateRequest
from deerflow.compile.candidate_verifier import CandidateVerificationCode, CandidateVerificationFinding, CandidateVerifier, FunctionalCheckRunner
from deerflow.compile.external_evaluator import FunctionalOracleSpec
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.replay_closure_verifier import ReplayClosureVerificationResult, ReplayClosureVerifier
from deerflow.compile.schemas import CompileSession

AGENT_WORKFLOW_RUNTIME_VERSION = "agent-workflow-runtime-v5"
PROGRESS_SNAPSHOT_VERSION = "agent-workflow-progress-v2"

_ORIGINAL_CREATE_AGENT = v2._ORIGINAL_CREATE_AGENT
_ORIGINAL_CANDIDATE_SERVICE = v2._ORIGINAL_CANDIDATE_SERVICE
_ORIGINAL_NODE_RUNNER = v2._ORIGINAL_NODE_RUNNER
_RUNTIME_BINDING_LOCK = v2._RUNTIME_BINDING_LOCK
_agent_factory = _ORIGINAL_CREATE_AGENT
_active_closure_verifier: ReplayClosureVerifier | None = None
_active_closure_store: ReplayClosureStateStore | None = None


class AgentWorkflowRuntimeV5Error(RuntimeError):
    """Runtime v5 replay closure 合同或串行绑定无效。"""


@dataclass(frozen=True)
class ReplayClosureProgressSnapshot(v4.AgentWorkflowProgressSnapshot):
    workspace_ready: bool
    replay_closure_ready: bool
    replay_closure_frontier_sha256: str | None
    replay_closure_failure: str | None


class ReplayClosureStateStore:
    def __init__(self) -> None:
        self._latest: tuple[int, ReplayClosureVerificationResult] | None = None
        self._lock = threading.Lock()

    def record(self, *, command_count: int, result: ReplayClosureVerificationResult) -> None:
        with self._lock:
            self._latest = (command_count, result)

    def latest_for(self, *, command_count: int) -> ReplayClosureVerificationResult | None:
        with self._lock:
            if self._latest is None or self._latest[0] != command_count:
                return None
            return self._latest[1]


def build_progress_snapshot(
    *,
    node_input: AgentBuildNodeInput,
    session: CompileSession,
    closure_store: ReplayClosureStateStore,
) -> ReplayClosureProgressSnapshot:
    base = v4.build_progress_snapshot(node_input=node_input, session=session)
    latest = closure_store.latest_for(command_count=base.command_count)
    base_payload = {field.name: getattr(base, field.name) for field in fields(v4.AgentWorkflowProgressSnapshot)}
    base_payload["schema_version"] = PROGRESS_SNAPSHOT_VERSION
    return ReplayClosureProgressSnapshot(
        **base_payload,
        workspace_ready=base.candidate_ready,
        replay_closure_ready=bool(latest and latest.passed),
        replay_closure_frontier_sha256=latest.frontier_sha256 if latest else None,
        replay_closure_failure=(latest.classification if latest and not latest.passed else None),
    )


_CLOSURE_CODE_MAP = {
    "missing_bootstrap_step": CandidateVerificationCode.MISSING_BOOTSTRAP_STEP,
    "missing_generated_input": CandidateVerificationCode.MISSING_GENERATED_INPUT,
    "recipe_execution_failed": CandidateVerificationCode.RECIPE_EXECUTION_FAILED,
    "artifact_set_mismatch": CandidateVerificationCode.REPLAY_ARTIFACT_SET_MISMATCH,
    "artifact_content_mismatch": CandidateVerificationCode.REPLAY_ARTIFACT_CONTENT_MISMATCH,
    "timeout": CandidateVerificationCode.REPLAY_CLOSURE_TIMEOUT,
    "cleanup_failed": CandidateVerificationCode.REPLAY_CLOSURE_CLEANUP_FAILED,
    "replay_verification_failed": CandidateVerificationCode.REPLAY_VERIFICATION_FAILED,
    "internal_error": CandidateVerificationCode.REPLAY_CLOSURE_INTERNAL_ERROR,
}


class AgentWorkflowCandidateService(v3.AgentWorkflowCandidateService):
    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        if _active_closure_verifier is None or _active_closure_store is None:
            raise AgentWorkflowRuntimeV5Error("Runtime v5 缺少活动 replay closure verifier")
        self.closure_verifier = _active_closure_verifier
        self.closure_store = _active_closure_store

    def _validate_against_session(self, request: SubmitCandidateRequest) -> list[Any]:
        codes = super()._validate_against_session(request)
        if codes:
            return codes
        result = self.closure_verifier.verify(request=request, session=self.session)
        current = self.manager.load_session(self.session.session_id, self.session.thread_id)
        self.session.__dict__.update(current.__dict__)
        self.closure_store.record(command_count=len(current.commands), result=result)
        self.ledger.append("candidate.replay_closure_completed", **result.canonical_payload())
        if result.passed:
            return []
        code = _CLOSURE_CODE_MAP.get(result.classification, CandidateVerificationCode.REPLAY_CLOSURE_INTERNAL_ERROR)
        finding = CandidateVerificationFinding(
            code=code.value,
            message=result.output_excerpt or result.classification,
        )
        self._verification_findings = (*self._verification_findings, finding)
        return [code]


class ReplayClosureHarnessMiddleware(v4.ProgressAwareHarnessMiddleware):
    def __init__(self, *, closure_store: ReplayClosureStateStore, **kwargs: Any):
        super().__init__(**kwargs)
        self.closure_store = closure_store

    def snapshot(self) -> ReplayClosureProgressSnapshot:
        current = self.manager.load_session(self.session.session_id, self.session.thread_id)
        return build_progress_snapshot(
            node_input=self.node_input,
            session=current,
            closure_store=self.closure_store,
        )


class AgentWorkflowNodeRunner(v4.AgentWorkflowNodeRunner):
    def _build_middlewares(self) -> list[AgentMiddleware]:
        middleware = super()._build_middlewares()
        if self.ledger is None or _active_closure_store is None:
            raise AgentWorkflowRuntimeV5Error("Runtime v5 缺少 evidence ledger 或 closure state store")
        progress = ReplayClosureHarnessMiddleware(
            node_input=self.node_input,
            session=self.session,
            manager=self.manager,
            tracker=self.tracker,
            ledger=self.ledger,
            started_monotonic=self.started_monotonic,
            closure_store=_active_closure_store,
        )
        return [progress if isinstance(item, v4.ProgressAwareHarnessMiddleware) else item for item in middleware]

    def _system_prompt(self) -> str:
        prompt = super()._system_prompt()
        suffix = "\n</agent_workflow_node_v1>"
        if not prompt.endswith(suffix):
            raise AgentWorkflowRuntimeV5Error("Runtime v4 system prompt 结构发生漂移")
        guidance = (
            "candidate_ready/workspace_ready only means the current workspace can be submitted. "
            "submit_candidate_v1 also performs an isolated replay-closure preflight before freezing the candidate. "
            "If replay_closure_failure or rejection_details reports a missing bootstrap/generated input, add the general prerequisite command to the recipe and retry. "
            "Replay closure preflight never replaces the independent external evaluator."
        )
        return prompt[: -len(suffix)] + "\n" + guidance + suffix


def _create_agent_v5(*args: Any, **kwargs: Any) -> Any:
    middleware = kwargs.get("middleware")
    execution = next((item for item in middleware or () if isinstance(item, v1.AgentWorkflowExecutionMiddleware)), None)
    if execution is None:
        raise AgentWorkflowRuntimeV5Error("Runtime v5 缺少 execution middleware")
    return v2._RecursionGuardAgent(_agent_factory(*args, **kwargs), execution)


async def run_agent_workflow_node_v5(
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
    """串行绑定 Runtime v5，并在所有终态恢复 v1/v3 模块。"""

    global _active_closure_store, _active_closure_verifier
    if not _RUNTIME_BINDING_LOCK.acquire(blocking=False):
        raise AgentWorkflowRuntimeV5Error("Runtime v5 只允许单进程串行执行")
    originals = (v1.create_agent, v1.AgentWorkflowCandidateService, v1.AgentWorkflowNodeRunner)
    try:
        expected = (_ORIGINAL_CREATE_AGENT, _ORIGINAL_CANDIDATE_SERVICE, _ORIGINAL_NODE_RUNNER)
        if originals != expected:
            raise AgentWorkflowRuntimeV5Error("Runtime v1 binding 已被其他执行修改")
        spec = v4._resolve_oracle_spec(node_input, oracle_registry)
        v3._active_verifier = CandidateVerifier(oracle_spec=spec, functional_runner=functional_runner)
        _active_closure_verifier = closure_verifier or ReplayClosureVerifier(
            timeout_seconds=node_input.budget.replay_timeout_seconds,
        )
        _active_closure_store = ReplayClosureStateStore()
        v1.create_agent = _create_agent_v5
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
            _active_closure_verifier = None
            _active_closure_store = None
    finally:
        _RUNTIME_BINDING_LOCK.release()


__all__ = [
    "AGENT_WORKFLOW_RUNTIME_VERSION",
    "AgentWorkflowCandidateService",
    "AgentWorkflowNodeRunner",
    "AgentWorkflowRuntimeV5Error",
    "PROGRESS_SNAPSHOT_VERSION",
    "ReplayClosureHarnessMiddleware",
    "ReplayClosureProgressSnapshot",
    "ReplayClosureStateStore",
    "build_progress_snapshot",
    "run_agent_workflow_node_v5",
]
