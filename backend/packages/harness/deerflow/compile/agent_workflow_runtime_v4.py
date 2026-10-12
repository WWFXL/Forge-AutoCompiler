"""Agent Workflow Runtime v4：进展感知的结构化 Harness。"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import threading
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, override

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from deerflow.compile import agent_workflow_runtime as v1
from deerflow.compile import agent_workflow_runtime_v2 as v2
from deerflow.compile import agent_workflow_runtime_v3 as v3
from deerflow.compile.agent_workflow_schemas import AgentBuildNodeInput, AgentBuildNodeResult
from deerflow.compile.candidate_verifier import CandidateVerifier, FunctionalCheckRunner
from deerflow.compile.external_evaluator import FunctionalOracleSpec
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.schemas import BuildCommandRecord, CompileSession

AGENT_WORKFLOW_RUNTIME_VERSION = "agent-workflow-runtime-v4"
PROGRESS_SNAPSHOT_VERSION = "agent-workflow-progress-v1"
_MAX_RECENT_COMMANDS = 6
_MAX_MODEL_INTERACTIONS = 2
_MAX_CONSECUTIVE_DIAGNOSTICS = 4
_COMMAND_PREVIEW_CHARS = 320
_REPLAY_ROLES = frozenset({"dependency", "dependency_setup", "configure", "build", "artifact_stage"})

_ORIGINAL_CREATE_AGENT = v2._ORIGINAL_CREATE_AGENT
_ORIGINAL_CANDIDATE_SERVICE = v2._ORIGINAL_CANDIDATE_SERVICE
_ORIGINAL_NODE_RUNNER = v2._ORIGINAL_NODE_RUNNER
_RUNTIME_BINDING_LOCK = v2._RUNTIME_BINDING_LOCK
_agent_factory = _ORIGINAL_CREATE_AGENT


class AgentWorkflowRuntimeV4Error(RuntimeError):
    """Runtime v4 进展 Harness 或串行绑定合同无效。"""


@dataclass(frozen=True)
class ProgressCommand:
    command_id: str
    role: str
    exit_code: int | None
    timed_out: bool
    workdir: str
    command_preview: str


@dataclass(frozen=True)
class AgentWorkflowProgressSnapshot:
    schema_version: str
    session_status: str
    build_system: str | None
    target_id: str
    command_count: int
    role_counts: Mapping[str, int]
    successful_build_command_ids: tuple[str, ...]
    successful_smoke_command_ids: tuple[str, ...]
    successful_artifact_stage_command_ids: tuple[str, ...]
    recommended_recipe_command_ids: tuple[str, ...]
    staged_artifact_paths: tuple[str, ...]
    recommended_target_mapping: Mapping[str, str]
    recent_commands: tuple[ProgressCommand, ...]
    consecutive_diagnostics: int
    candidate_ready: bool

    def canonical_payload(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _successful(command: BuildCommandRecord) -> bool:
    return command.exit_code == 0 and not command.timed_out and command.termination not in {"cancelled", "timed_out"}


def _command_preview(command: str) -> str:
    normalized = " ".join(command.split())
    if len(normalized) <= _COMMAND_PREVIEW_CHARS:
        return normalized
    return normalized[: _COMMAND_PREVIEW_CHARS - 3] + "..."


def _staged_artifacts(session: CompileSession) -> tuple[str, ...]:
    root = Path(session.leadagent_artifacts_dir)
    if not root.is_dir():
        return ()
    paths: list[str] = []
    for candidate in root.rglob("*"):
        if candidate.is_symlink() or not candidate.is_file():
            continue
        paths.append(candidate.relative_to(root).as_posix())
    return tuple(sorted(paths))


def _target_mapping(node_input: AgentBuildNodeInput, artifacts: Sequence[str]) -> dict[str, str]:
    matches = sorted(artifact for artifact in artifacts if any(fnmatch.fnmatchcase(artifact, pattern) for pattern in node_input.target_contract.artifact_path_patterns))
    if not matches:
        return {}
    return {node_input.target_contract.target_id: matches[0]}


def build_progress_snapshot(
    *,
    node_input: AgentBuildNodeInput,
    session: CompileSession,
) -> AgentWorkflowProgressSnapshot:
    commands = tuple(session.commands)
    role_counts = Counter(command.role for command in commands)
    successful_builds = tuple(command.command_id for command in commands if command.role == "build" and _successful(command))
    successful_smokes = tuple(command.command_id for command in commands if command.role == "smoke" and _successful(command))
    successful_stages = tuple(command.command_id for command in commands if command.role == "artifact_stage" and _successful(command))
    recipe = tuple(command.command_id for command in commands if command.role in _REPLAY_ROLES and _successful(command))
    artifacts = _staged_artifacts(session)
    target_mapping = _target_mapping(node_input, artifacts)

    consecutive_diagnostics = 0
    for command in reversed(commands):
        if command.role != "diagnostic":
            break
        consecutive_diagnostics += 1

    recent = tuple(
        ProgressCommand(
            command_id=command.command_id,
            role=command.role,
            exit_code=command.exit_code,
            timed_out=command.timed_out,
            workdir=command.workdir,
            command_preview=_command_preview(command.command),
        )
        for command in commands[-_MAX_RECENT_COMMANDS:]
    )
    candidate_ready = bool(successful_builds and successful_stages and target_mapping)
    return AgentWorkflowProgressSnapshot(
        schema_version=PROGRESS_SNAPSHOT_VERSION,
        session_status=session.status,
        build_system=session.executed_build_system or session.selected_build_system or session.build_system,
        target_id=node_input.target_contract.target_id,
        command_count=len(commands),
        role_counts=dict(sorted(role_counts.items())),
        successful_build_command_ids=successful_builds,
        successful_smoke_command_ids=successful_smokes,
        successful_artifact_stage_command_ids=successful_stages,
        recommended_recipe_command_ids=recipe,
        staged_artifact_paths=artifacts,
        recommended_target_mapping=target_mapping,
        recent_commands=recent,
        consecutive_diagnostics=consecutive_diagnostics,
        candidate_ready=candidate_ready,
    )


def compact_model_messages(
    messages: Sequence[BaseMessage],
    *,
    max_model_interactions: int = _MAX_MODEL_INTERACTIONS,
) -> list[BaseMessage]:
    if max_model_interactions < 1:
        raise ValueError("max_model_interactions 必须大于 0")
    copied = list(messages)
    if len(copied) <= 1:
        return copied
    ai_indexes = [index for index, message in enumerate(copied) if getattr(message, "type", None) == "ai"]
    if len(ai_indexes) <= max_model_interactions:
        return copied
    start = ai_indexes[-max_model_interactions]
    retained = [copied[0], *copied[start:]]
    if start == 0:
        return copied
    return retained


def _tool_args(request: ToolCallRequest) -> dict[str, Any]:
    raw = request.tool_call.get("args", {})
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


class ProgressAwareHarnessMiddleware(AgentMiddleware[v1.AgentWorkflowGraphState]):
    def __init__(
        self,
        *,
        node_input: AgentBuildNodeInput,
        session: CompileSession,
        manager: CompileSessionManager,
        tracker: v1.AgentWorkflowBudgetTracker,
        ledger: v1.AgentWorkflowEvidenceLedger,
        started_monotonic: float,
    ):
        self.node_input = node_input
        self.session = session
        self.manager = manager
        self.tracker = tracker
        self.ledger = ledger
        self.started_monotonic = started_monotonic
        self._attempted_submission_frontiers: set[str] = set()
        self._lock = threading.Lock()

    def snapshot(self) -> AgentWorkflowProgressSnapshot:
        current = self.manager.load_session(self.session.session_id, self.session.thread_id)
        return build_progress_snapshot(node_input=self.node_input, session=current)

    @staticmethod
    def _progress_message(snapshot: AgentWorkflowProgressSnapshot) -> HumanMessage:
        return HumanMessage(
            content=(
                "<authoritative_compile_progress>\n"
                + snapshot.canonical_json()
                + "\n</authoritative_compile_progress>\n"
                + "Use this deterministic snapshot as the source of truth. "
                + "If candidate_ready is true, call submit_candidate_v1 before any further shell command."
            )
        )

    def _prepare_model_request(self, request: ModelRequest) -> ModelRequest:
        snapshot = self.snapshot()
        compacted = compact_model_messages(request.messages)
        visible = [*compacted, self._progress_message(snapshot)]
        self.ledger.append(
            "harness.progress_snapshot",
            snapshot_sha256=snapshot.canonical_sha256(),
            command_count=snapshot.command_count,
            candidate_ready=snapshot.candidate_ready,
            consecutive_diagnostics=snapshot.consecutive_diagnostics,
        )
        self.ledger.append(
            "harness.context_compacted",
            original_message_count=len(request.messages),
            retained_message_count=len(compacted),
            provider_message_count=len(visible),
        )
        return request.override(messages=visible)

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        return handler(self._prepare_model_request(request))

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        return await handler(self._prepare_model_request(request))

    def _frontier(self, snapshot: AgentWorkflowProgressSnapshot) -> str:
        payload = {
            "command_count": snapshot.command_count,
            "recipe": snapshot.recommended_recipe_command_ids,
            "artifacts": snapshot.staged_artifact_paths,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _guard_reason(self, request: ToolCallRequest, snapshot: AgentWorkflowProgressSnapshot) -> str | None:
        if request.tool_call.get("name") != "run_container_bash":
            return None
        frontier = self._frontier(snapshot)
        with self._lock:
            submission_attempted = frontier in self._attempted_submission_frontiers
        if snapshot.candidate_ready and not submission_attempted:
            return "candidate_ready_requires_submit"
        args = _tool_args(request)
        if args.get("command_role") == "diagnostic" and snapshot.consecutive_diagnostics >= _MAX_CONSECUTIVE_DIAGNOSTICS:
            return "diagnostic_no_progress_limit"
        return None

    def _blocked_tool_result(
        self,
        request: ToolCallRequest,
        snapshot: AgentWorkflowProgressSnapshot,
        reason: str,
    ) -> ToolMessage:
        self.tracker.observe_elapsed(time.monotonic() - self.started_monotonic)
        self.tracker.consume(tool_calls=1, agent_steps=1)
        payload = {
            "accepted": False,
            "error": "progress_aware_harness_rejection",
            "reason": reason,
            "candidate_ready": snapshot.candidate_ready,
            "required_next_action": "submit_candidate_v1" if reason == "candidate_ready_requires_submit" else "choose_non_diagnostic_progress_action",
            "recommended_recipe_command_ids": list(snapshot.recommended_recipe_command_ids),
            "staged_artifact_paths": list(snapshot.staged_artifact_paths),
            "recommended_target_mapping": dict(snapshot.recommended_target_mapping),
        }
        self.ledger.append(
            "harness.tool_rejected",
            tool_name=request.tool_call.get("name"),
            reason=reason,
            snapshot_sha256=snapshot.canonical_sha256(),
        )
        return ToolMessage(
            content=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            tool_call_id=request.tool_call.get("id", "progress-aware-guard"),
            name=request.tool_call.get("name", "run_container_bash"),
            status="error",
        )

    def _record_submission_attempt(self, snapshot: AgentWorkflowProgressSnapshot) -> None:
        frontier = self._frontier(snapshot)
        with self._lock:
            self._attempted_submission_frontiers.add(frontier)
        self.ledger.append(
            "harness.submission_frontier_attempted",
            frontier_sha256=frontier,
            snapshot_sha256=snapshot.canonical_sha256(),
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
        result = handler(request)
        if request.tool_call.get("name") == "submit_candidate_v1":
            self._record_submission_attempt(snapshot)
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
        result = await handler(request)
        if request.tool_call.get("name") == "submit_candidate_v1":
            self._record_submission_attempt(snapshot)
        return result


class AgentWorkflowNodeRunner(v3.AgentWorkflowNodeRunner):
    def _build_middlewares(self) -> list[AgentMiddleware]:
        middleware = super()._build_middlewares()
        if self.ledger is None:
            raise AgentWorkflowRuntimeV4Error("Runtime v4 缺少 evidence ledger")
        progress = ProgressAwareHarnessMiddleware(
            node_input=self.node_input,
            session=self.session,
            manager=self.manager,
            tracker=self.tracker,
            ledger=self.ledger,
            started_monotonic=self.started_monotonic,
        )
        return [middleware[0], progress, *middleware[1:]]

    def _system_prompt(self) -> str:
        prompt = super()._system_prompt()
        suffix = "\n</agent_workflow_node_v1>"
        if not prompt.endswith(suffix):
            raise AgentWorkflowRuntimeV4Error("Runtime v3 system prompt 结构发生漂移")
        guidance = (
            "Before every model request, the Harness appends an authoritative_compile_progress JSON snapshot derived from the persisted Compile Session. "
            "Use its exact command IDs, staged artifact paths, target mapping, and recommended recipe. "
            "When candidate_ready is true, submit before issuing another shell command. "
            "A Harness rejection is not build failure; follow required_next_action or change to a non-diagnostic progress action."
        )
        return prompt[: -len(suffix)] + "\n" + guidance + suffix


def _create_agent_v4(*args: Any, **kwargs: Any) -> Any:
    middleware = kwargs.get("middleware")
    execution = next((item for item in middleware or () if isinstance(item, v1.AgentWorkflowExecutionMiddleware)), None)
    if execution is None:
        raise AgentWorkflowRuntimeV4Error("Runtime v4 缺少 execution middleware")
    return v2._RecursionGuardAgent(_agent_factory(*args, **kwargs), execution)


def _resolve_oracle_spec(
    node_input: AgentBuildNodeInput,
    oracle_registry: Mapping[str, FunctionalOracleSpec],
) -> FunctionalOracleSpec:
    oracle_ref = node_input.target_contract.functional_oracle_ref
    spec = oracle_registry.get(oracle_ref)
    if spec is None:
        raise AgentWorkflowRuntimeV4Error(f"未注册 pre-freeze functional oracle: {oracle_ref}")
    spec.validate()
    if spec.oracle_ref != oracle_ref:
        raise AgentWorkflowRuntimeV4Error("pre-freeze functional oracle identity 不匹配")
    return spec


async def run_agent_workflow_node_v4(
    *,
    node_input: AgentBuildNodeInput,
    session: CompileSession,
    manager: CompileSessionManager,
    model: BaseChatModel,
    oracle_registry: Mapping[str, FunctionalOracleSpec],
    functional_runner: FunctionalCheckRunner | None = None,
    finalizer: v1.Finalizer | None = None,
) -> AgentBuildNodeResult:
    """串行绑定 Runtime v4，并在所有终态恢复 v1/v3 模块。"""

    if not _RUNTIME_BINDING_LOCK.acquire(blocking=False):
        raise AgentWorkflowRuntimeV4Error("Runtime v4 只允许单进程串行执行")
    originals = (v1.create_agent, v1.AgentWorkflowCandidateService, v1.AgentWorkflowNodeRunner)
    try:
        expected = (_ORIGINAL_CREATE_AGENT, _ORIGINAL_CANDIDATE_SERVICE, _ORIGINAL_NODE_RUNNER)
        if originals != expected:
            raise AgentWorkflowRuntimeV4Error("Runtime v1 binding 已被其他执行修改")
        spec = _resolve_oracle_spec(node_input, oracle_registry)
        v3._active_verifier = CandidateVerifier(oracle_spec=spec, functional_runner=functional_runner)
        v1.create_agent = _create_agent_v4
        v1.AgentWorkflowCandidateService = v3.AgentWorkflowCandidateService
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
    finally:
        _RUNTIME_BINDING_LOCK.release()


__all__ = [
    "AGENT_WORKFLOW_RUNTIME_VERSION",
    "AgentWorkflowNodeRunner",
    "AgentWorkflowProgressSnapshot",
    "AgentWorkflowRuntimeV4Error",
    "ProgressAwareHarnessMiddleware",
    "build_progress_snapshot",
    "compact_model_messages",
    "run_agent_workflow_node_v4",
]
