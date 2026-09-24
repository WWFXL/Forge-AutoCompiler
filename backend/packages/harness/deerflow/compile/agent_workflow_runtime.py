from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import threading
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, NotRequired, override

from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import AgentMiddleware, hook_config
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse
from langchain.tools import tool
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.types import Command

from deerflow.compile.agent_workflow_node import (
    AgentWorkflowBudgetExceeded,
    AgentWorkflowBudgetTracker,
    AgentWorkflowCandidateStore,
    AgentWorkflowNodeStatus,
    AgentWorkflowStateMachine,
    AgentWorkflowTerminationReason,
    SubmitCandidateRejectionCode,
)
from deerflow.compile.agent_workflow_schemas import (
    AGENT_WORKFLOW_NODE_SCHEMA_VERSION,
    AgentBuildNodeInput,
    AgentBuildNodeResult,
    AgentWorkflowContractError,
    AgentWorkflowUsage,
    SubmitCandidateRequest,
    SubmitCandidateResponse,
)
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.operations import _infer_executed_build_system
from deerflow.compile.schemas import TERMINAL_COMPILE_SESSION_STATUSES, CompileSession, utc_now_iso
from deerflow.subagents.builtins.compiler_agent import COMPILER_AGENT_CONFIG
from deerflow.tools.bound_compile_tools import get_bound_compile_tools

AGENT_WORKFLOW_RUNTIME_VERSION = "agent-workflow-runtime-v1"
_REPLAY_ROLES = frozenset({"dependency", "dependency_setup", "configure", "build", "artifact_stage"})


class AgentWorkflowRuntimeError(RuntimeError):
    """单 Agent Workflow Node 无法继续执行。"""


class AgentWorkflowIdentityError(AgentWorkflowRuntimeError):
    """节点输入与 Compile Session 的 authoritative identity 不一致。"""


class AgentWorkflowGraphState(AgentState):
    agent_workflow_terminal: NotRequired[bool]


class AgentWorkflowEvidenceLedger:
    def __init__(self, path: Path, *, node_input: AgentBuildNodeInput, run_id: str):
        self.path = path
        self.node_input = node_input
        self.run_id = run_id
        self._lock = threading.Lock()
        self._sequence = 0
        self._head_sha256 = "0" * 64
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.touch(exist_ok=False)
        except FileExistsError as exc:
            raise AgentWorkflowIdentityError(f"agent workflow evidence already exists: {path}") from exc

    @property
    def head_sha256(self) -> str:
        return self._head_sha256

    def append(self, event_type: str, **payload: Any) -> str:
        with self._lock:
            self._sequence += 1
            entry = {
                "schema_version": AGENT_WORKFLOW_NODE_SCHEMA_VERSION,
                "event_id": f"event:{uuid.uuid4().hex}",
                "sequence": self._sequence,
                "timestamp": utc_now_iso(),
                "task_id": self.node_input.task_id,
                "attempt_id": self.node_input.attempt_id,
                "run_id": self.run_id,
                "session_id": self.node_input.session_id,
                "event_type": event_type,
                "payload": payload,
                "previous_hash": self._head_sha256,
            }
            canonical = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            event_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            entry["event_hash"] = event_hash
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            self._head_sha256 = event_hash
            return event_hash


def _rejected_response(
    tracker: AgentWorkflowBudgetTracker,
    codes: list[SubmitCandidateRejectionCode],
    *,
    terminal: bool = False,
) -> SubmitCandidateResponse:
    return SubmitCandidateResponse(
        accepted=False,
        remaining_budget=tracker.remaining(),
        rejection_codes=tuple(code.value for code in codes),
        terminal_for_agent=terminal,
    )


class AgentWorkflowCandidateService:
    def __init__(
        self,
        *,
        node_input: AgentBuildNodeInput,
        session: CompileSession,
        manager: CompileSessionManager,
        store: AgentWorkflowCandidateStore,
        candidate_path: Path,
        ledger: AgentWorkflowEvidenceLedger,
    ):
        self.node_input = node_input
        self.session = session
        self.manager = manager
        self.store = store
        self.candidate_path = candidate_path
        self.ledger = ledger
        self._lock = threading.Lock()

    def submit(self, request: SubmitCandidateRequest) -> SubmitCandidateResponse:
        with self._lock:
            self.ledger.append("candidate.submit_started", candidate_id=request.candidate_id)
            if self.candidate_path.exists():
                response = _rejected_response(
                    self.store.budget_tracker,
                    [SubmitCandidateRejectionCode.CANDIDATE_ALREADY_FROZEN],
                    terminal=True,
                )
                self._record_rejection(request, response)
                return response

            try:
                request.validate()
            except AgentWorkflowContractError:
                response = _rejected_response(self.store.budget_tracker, [SubmitCandidateRejectionCode.INVALID_CONTRACT])
                self._record_rejection(request, response)
                return response

            self._record_artifact_observations(request.artifact_paths, phase="pre_submit")
            rejection_codes = self._validate_against_session(request)
            if rejection_codes:
                response = _rejected_response(self.store.budget_tracker, rejection_codes)
                self._record_rejection(request, response)
                return response

            response = self.store.submit(request)
            if not response.accepted:
                self._record_rejection(request, response)
                return response
            try:
                self._persist_candidate(request)
            except OSError as exc:
                self.store.state_machine.transition(AgentWorkflowNodeStatus.NODE_FAILED)
                self.ledger.append(
                    "candidate.submit_rejected",
                    candidate_id=request.candidate_id,
                    rejection_codes=[SubmitCandidateRejectionCode.CANDIDATE_PERSISTENCE_FAILED.value],
                    error_class=type(exc).__name__,
                )
                return _rejected_response(
                    self.store.budget_tracker,
                    [SubmitCandidateRejectionCode.CANDIDATE_PERSISTENCE_FAILED],
                    terminal=True,
                )

            self._record_artifact_observations(request.artifact_paths, phase="frozen")
            self.ledger.append(
                "candidate.submit_accepted",
                candidate_id=request.candidate_id,
                submission_id=response.submission_id,
                candidate_record_sha256=response.candidate_record_sha256,
            )
            return response

    def reject_invalid_contract(self, candidate_id: str | None) -> SubmitCandidateResponse:
        response = _rejected_response(self.store.budget_tracker, [SubmitCandidateRejectionCode.INVALID_CONTRACT])
        self.ledger.append(
            "candidate.submit_rejected",
            candidate_id=candidate_id if isinstance(candidate_id, str) else None,
            rejection_codes=list(response.rejection_codes),
        )
        return response

    def _record_rejection(self, request: SubmitCandidateRequest, response: SubmitCandidateResponse) -> None:
        self.ledger.append(
            "candidate.submit_rejected",
            candidate_id=request.candidate_id,
            rejection_codes=list(response.rejection_codes),
        )

    def _validate_against_session(self, request: SubmitCandidateRequest) -> list[SubmitCandidateRejectionCode]:
        current = self.manager.load_session(self.session.session_id, self.session.thread_id)
        if current.status in TERMINAL_COMPILE_SESSION_STATUSES or current.finalized_at is not None or current.termination_requested_at is not None:
            return [SubmitCandidateRejectionCode.SESSION_INACTIVE]

        positions: dict[str, list[int]] = {}
        for index, command in enumerate(current.commands):
            positions.setdefault(command.command_id, []).append(index)

        codes: list[SubmitCandidateRejectionCode] = []
        previous_position = -1
        for command_id in request.recipe_command_ids:
            matches = positions.get(command_id, [])
            if not matches:
                codes.append(SubmitCandidateRejectionCode.COMMAND_MISSING)
                continue
            if len(matches) != 1:
                codes.append(SubmitCandidateRejectionCode.COMMAND_AMBIGUOUS)
                continue
            position = matches[0]
            command = current.commands[position]
            if position <= previous_position:
                codes.append(SubmitCandidateRejectionCode.COMMAND_ORDER_INVALID)
            previous_position = position
            if command.completed_at is None:
                codes.append(SubmitCandidateRejectionCode.COMMAND_NOT_COMPLETED)
            elif command.exit_code != 0 or command.timed_out:
                codes.append(SubmitCandidateRejectionCode.COMMAND_NOT_SUCCESSFUL)
            if command.role not in _REPLAY_ROLES:
                codes.append(SubmitCandidateRejectionCode.COMMAND_ROLE_INVALID)

        for command_id in request.supporting_command_ids:
            matches = positions.get(command_id, [])
            if not matches:
                codes.append(SubmitCandidateRejectionCode.COMMAND_MISSING)
                continue
            if len(matches) != 1:
                codes.append(SubmitCandidateRejectionCode.COMMAND_AMBIGUOUS)
                continue
            command = current.commands[matches[0]]
            if command.role != "build":
                codes.append(SubmitCandidateRejectionCode.COMMAND_ROLE_INVALID)
                continue
            observed = _infer_executed_build_system(current.commands, command_id)
            if observed != request.build_system:
                codes.append(SubmitCandidateRejectionCode.BUILD_SYSTEM_MISMATCH)

        if "artifact_stage" not in {current.commands[indexes[0]].role for command_id in request.recipe_command_ids if len(indexes := positions.get(command_id, [])) == 1}:
            codes.append(SubmitCandidateRejectionCode.COMMAND_ROLE_INVALID)
        if current.selected_build_system != request.build_system:
            codes.append(SubmitCandidateRejectionCode.BUILD_SYSTEM_MISMATCH)

        for artifact_path in request.artifact_paths:
            code = self._validate_artifact_path(current, artifact_path)
            if code is not None:
                codes.append(code)

        return list(dict.fromkeys(codes))

    @staticmethod
    def _validate_artifact_path(session: CompileSession, relative_path: str) -> SubmitCandidateRejectionCode | None:
        base = Path(session.leadagent_artifacts_dir)
        candidate = base.joinpath(*relative_path.split("/"))
        if not candidate.exists():
            return SubmitCandidateRejectionCode.ARTIFACT_MISSING
        current = base
        for part in relative_path.split("/"):
            current /= part
            if current.is_symlink():
                return SubmitCandidateRejectionCode.ARTIFACT_SYMLINK
        if not candidate.is_file():
            return SubmitCandidateRejectionCode.ARTIFACT_NOT_REGULAR
        try:
            candidate.resolve(strict=True).relative_to(base.resolve(strict=True))
        except (FileNotFoundError, ValueError):
            return SubmitCandidateRejectionCode.ARTIFACT_SYMLINK
        return None

    def _record_artifact_observations(self, artifact_paths: tuple[str, ...], *, phase: str) -> None:
        base = Path(self.session.leadagent_artifacts_dir)
        for relative_path in artifact_paths:
            candidate = base.joinpath(*relative_path.split("/"))
            self.ledger.append(
                "artifact.observed",
                phase=phase,
                relative_path=relative_path,
                exists=candidate.exists(),
                is_file=candidate.is_file(),
                is_symlink=candidate.is_symlink(),
                size_bytes=candidate.stat().st_size if candidate.is_file() and not candidate.is_symlink() else None,
            )

    def _persist_candidate(self, request: SubmitCandidateRequest) -> None:
        self.candidate_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.candidate_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(request.canonical_json())
            stream.flush()
            os.fsync(stream.fileno())


class AgentWorkflowExecutionMiddleware(AgentMiddleware[AgentWorkflowGraphState]):
    def __init__(self, tracker: AgentWorkflowBudgetTracker, ledger: AgentWorkflowEvidenceLedger, started_monotonic: float):
        self.tracker = tracker
        self.ledger = ledger
        self.started_monotonic = started_monotonic
        self._request_sequence = 0

    def _before_request(self) -> int:
        self.tracker.observe_elapsed(time.monotonic() - self.started_monotonic)
        self.tracker.consume(model_requests=1, agent_steps=1)
        self._request_sequence += 1
        self.ledger.append("model.request_started", request_sequence=self._request_sequence)
        return self._request_sequence

    def _after_request(self, response: ModelResponse, request_sequence: int) -> None:
        tokens = sum(int(usage.get("total_tokens", 0)) for message in response.result if isinstance((usage := getattr(message, "usage_metadata", None)), Mapping))
        self.ledger.append("model.request_completed", request_sequence=request_sequence, recorded_tokens=tokens)
        self.tracker.consume(recorded_tokens=tokens)

    @override
    def wrap_model_call(self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]) -> ModelCallResult:
        sequence = self._before_request()
        serial_request = request.override(model_settings={**(request.model_settings or {}), "parallel_tool_calls": False})
        try:
            response = handler(serial_request)
        except Exception as exc:
            self.ledger.append("model.request_failed", request_sequence=sequence, error_class=type(exc).__name__)
            raise
        self._after_request(response, sequence)
        return response

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        sequence = self._before_request()
        serial_request = request.override(model_settings={**(request.model_settings or {}), "parallel_tool_calls": False})
        try:
            response = await handler(serial_request)
        except Exception as exc:
            self.ledger.append("model.request_failed", request_sequence=sequence, error_class=type(exc).__name__)
            raise
        self._after_request(response, sequence)
        return response


class AgentWorkflowTerminationMiddleware(AgentMiddleware[AgentWorkflowGraphState]):
    state_schema = AgentWorkflowGraphState

    @hook_config(can_jump_to=["end"])
    @override
    def before_model(self, state: AgentWorkflowGraphState, runtime: Runtime) -> dict | None:
        del runtime
        if not state.get("agent_workflow_terminal"):
            return None
        return {"agent_workflow_terminal": False, "jump_to": "end"}

    @hook_config(can_jump_to=["end"])
    @override
    async def abefore_model(self, state: AgentWorkflowGraphState, runtime: Runtime) -> dict | None:
        return self.before_model(state, runtime)

    @staticmethod
    def _terminal_result(request: ToolCallRequest, result: ToolMessage | Command) -> ToolMessage | Command:
        if request.tool_call.get("name") != "submit_candidate_v1" or not isinstance(result, ToolMessage) or not isinstance(result.content, str):
            return result
        try:
            payload = json.loads(result.content)
        except json.JSONDecodeError:
            return result
        if not payload.get("terminal_for_agent"):
            return result
        return Command(
            update={
                "messages": [result, AIMessage(content=result.content)],
                "agent_workflow_terminal": True,
            }
        )

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        return self._terminal_result(request, handler(request))

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        return self._terminal_result(request, await handler(request))


Finalizer = Callable[[CompileSession], None | Awaitable[None]]


class AgentWorkflowNodeRunner:
    def __init__(
        self,
        *,
        node_input: AgentBuildNodeInput,
        session: CompileSession,
        manager: CompileSessionManager,
        model: BaseChatModel,
        finalizer: Finalizer | None = None,
    ):
        self.node_input = node_input
        self.session = session
        self.manager = manager
        self.model = model
        self.finalizer = finalizer
        self.state_machine = AgentWorkflowStateMachine()
        self.tracker = AgentWorkflowBudgetTracker(node_input.budget)
        self.store = AgentWorkflowCandidateStore(self.state_machine, self.tracker)
        self.started_monotonic = time.monotonic()
        self.workflow_dir = Path(session.metadata_path).parent / "agent-workflow" / node_input.attempt_id
        self.ledger: AgentWorkflowEvidenceLedger | None = None

    async def run(self) -> AgentBuildNodeResult:
        primary_failure: str | None = None
        secondary_failures: list[str] = []
        budget_reason: str | None = None
        node_status = "failed"
        try:
            self.node_input.validate()
            self._validate_identity()
            self.ledger = AgentWorkflowEvidenceLedger(
                self.workflow_dir / "events.jsonl",
                node_input=self.node_input,
                run_id=self.session.run_id or "",
            )
            self.ledger.append("attempt.registered", input_sha256=self.node_input.canonical_sha256())
            self._persist_input()
            self.state_machine.transition(AgentWorkflowNodeStatus.READY)
            self.ledger.append("node.ready")
            self.state_machine.transition(AgentWorkflowNodeStatus.RUNNING)
            self.ledger.append("node.started")

            service = AgentWorkflowCandidateService(
                node_input=self.node_input,
                session=self.session,
                manager=self.manager,
                store=self.store,
                candidate_path=self.workflow_dir / "candidate.json",
                ledger=self.ledger,
            )
            tools = self._build_tools(service)
            middleware = [
                AgentWorkflowTerminationMiddleware(),
                AgentWorkflowExecutionMiddleware(self.tracker, self.ledger, self.started_monotonic),
            ]
            agent = create_agent(
                model=self.model,
                tools=tools,
                middleware=middleware,
                system_prompt=self._system_prompt(),
                state_schema=AgentWorkflowGraphState,
            )
            remaining_seconds = self.node_input.budget.node_timeout_seconds - (time.monotonic() - self.started_monotonic)
            if remaining_seconds <= 0:
                raise AgentWorkflowBudgetExceeded("node_timeout_seconds", self.tracker.snapshot())
            try:
                async with asyncio.timeout(remaining_seconds):
                    await agent.ainvoke(
                        {"messages": [{"role": "user", "content": self._task_prompt()}]},
                        config={"recursion_limit": self.node_input.budget.max_agent_steps + 2},
                        context={"thread_id": self.session.thread_id, "agent_name": "compiler"},
                    )
            except TimeoutError as exc:
                raise AgentWorkflowBudgetExceeded("node_timeout_seconds", self.tracker.snapshot()) from exc
            if self.state_machine.status is AgentWorkflowNodeStatus.NODE_FAILED:
                primary_failure = "candidate_persistence_failed"
                secondary_failures.extend(await self._finalize_safely(AgentWorkflowTerminationReason.NODE_FAILED))
                node_status = "failed"
            elif self.store.candidate is not None:
                node_status = "submitted"
            else:
                self.state_machine.transition(AgentWorkflowNodeStatus.NO_SUBMISSION)
                secondary_failures.extend(await self._finalize_safely(AgentWorkflowTerminationReason.NO_SUBMISSION))
                node_status = "no_submission"
        except AgentWorkflowBudgetExceeded as exc:
            budget_reason = exc.reason
            primary_failure = "budget_exhausted"
            self._append_if_available("budget.exhausted", reason=exc.reason)
            if self.state_machine.status is AgentWorkflowNodeStatus.RUNNING:
                self.state_machine.transition(AgentWorkflowNodeStatus.NO_SUBMISSION)
            elif self.state_machine.status is AgentWorkflowNodeStatus.CANDIDATE_SUBMITTED:
                self.state_machine.transition(AgentWorkflowNodeStatus.NODE_FAILED)
            secondary_failures.extend(await self._finalize_safely(AgentWorkflowTerminationReason.BUDGET_EXHAUSTED))
            node_status = "no_submission"
        except asyncio.CancelledError:
            primary_failure = "cancelled"
            self._append_if_available("node.cancelled")
            secondary_failures.extend(await asyncio.shield(self._finalize_safely(AgentWorkflowTerminationReason.CANCELLED)))
            node_status = "cancelled"
        except Exception as exc:
            primary_failure = "node_failed"
            self._append_if_available("node.failed", error_class=type(exc).__name__)
            if self.state_machine.status not in {AgentWorkflowNodeStatus.NODE_FAILED, AgentWorkflowNodeStatus.FINALIZING, AgentWorkflowNodeStatus.COMPLETED, AgentWorkflowNodeStatus.CANCELLED}:
                self.state_machine.transition(AgentWorkflowNodeStatus.NODE_FAILED)
            secondary_failures.extend(await self._finalize_safely(AgentWorkflowTerminationReason.NODE_FAILED))
            node_status = "failed"

        elapsed_seconds = time.monotonic() - self.started_monotonic
        self._append_if_available("node.terminal", node_status=node_status, primary_failure=primary_failure)
        snapshot = self.tracker.snapshot()
        candidate = self.store.candidate
        result = AgentBuildNodeResult(
            node_status=node_status,
            candidate_generated_observed=self._candidate_generated_observed(),
            candidate_submitted=candidate is not None and node_status == "submitted",
            submission_id=candidate.submission_id if candidate is not None and node_status == "submitted" else None,
            candidate_record_sha256=candidate.candidate_record_sha256 if candidate is not None and node_status == "submitted" else None,
            usage=AgentWorkflowUsage(
                model_requests=snapshot.model_requests,
                recorded_tokens=snapshot.recorded_tokens,
                agent_steps=snapshot.agent_steps,
                tool_calls=snapshot.tool_calls,
                commands=snapshot.commands,
            ),
            wall_clock_ms=round(elapsed_seconds * 1000),
            budget_terminal_reason=budget_reason,
            primary_failure=primary_failure,
            secondary_failures=tuple(dict.fromkeys(secondary_failures)),
            evidence_head_sha256=self.ledger.head_sha256 if self.ledger is not None else self.node_input.canonical_sha256(),
            session_terminal_status=self.session.status,
        )
        result.validate()
        return result

    def _validate_identity(self) -> None:
        current = self.manager.load_session(self.session.session_id, self.session.thread_id)
        mismatches = []
        if not current.run_id:
            mismatches.append("run_id")
        if current.session_id != self.node_input.session_id:
            mismatches.append("session_id")
        if current.repo_url != self.node_input.repository_url:
            mismatches.append("repository_url")
        if current.commit_sha != self.node_input.commit_sha:
            mismatches.append("commit_sha")
        if current.image_id != self.node_input.environment.image_id:
            mismatches.append("image_id")
        if current.parallel_jobs != self.node_input.environment.parallel_jobs:
            mismatches.append("parallel_jobs")
        if current.selected_build_system not in self.node_input.build_system_candidates:
            mismatches.append("build_system")
        if current.status in TERMINAL_COMPILE_SESSION_STATUSES or current.finalized_at is not None or current.termination_requested_at is not None:
            mismatches.append("session_status")
        if mismatches:
            raise AgentWorkflowIdentityError(f"agent workflow identity mismatch: {','.join(mismatches)}")
        self.session.__dict__.update(current.__dict__)

    def _persist_input(self) -> None:
        self.workflow_dir.mkdir(parents=True, exist_ok=True)
        input_path = self.workflow_dir / "input.json"
        descriptor = os.open(input_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(self.node_input.canonical_json())
            stream.flush()
            os.fsync(stream.fileno())

    def _build_tools(self, service: AgentWorkflowCandidateService):
        bound_tools = {bound_tool.name: bound_tool for bound_tool in get_bound_compile_tools(self.session)}
        run_tool = bound_tools["run_container_bash"]

        @tool("run_container_bash", parse_docstring=True)
        def workflow_run_container_bash(
            command: str,
            command_role: str,
            timeout_seconds: int = 1200,
            workdir: str | None = None,
        ) -> str:
            """在当前 Workflow Node 绑定的 Compile Session 中执行一个构建阶段。

            Args:
                command: 要执行的 Bash 命令。
                command_role: dependency、configure、build、diagnostic、smoke 或 artifact_stage。
                timeout_seconds: 单条命令超时秒数。
                workdir: 容器内绝对工作目录。
            """
            self._consume_tool_budget(command=True)
            before_command_ids = {command.command_id for command in self.manager.load_session(self.session.session_id, self.session.thread_id).commands}
            self.ledger.append("tool.call_started", tool_name="run_container_bash")
            try:
                result = run_tool.func(
                    command=command,
                    command_role=command_role,
                    timeout_seconds=min(timeout_seconds, self.node_input.budget.command_timeout_seconds),
                    workdir=workdir,
                )
            except Exception as exc:
                self._record_new_commands(before_command_ids, suppress_errors=True)
                self.ledger.append("tool.call_failed", tool_name="run_container_bash", error_class=type(exc).__name__)
                raise
            self._record_new_commands(before_command_ids)
            self.ledger.append("tool.call_completed", tool_name="run_container_bash")
            return result

        @tool("submit_candidate_v1", parse_docstring=True)
        def workflow_submit_candidate_v1(
            candidate_id: str,
            build_system: str,
            supporting_command_ids: list[str],
            artifact_paths: list[str],
            target_mapping: dict[str, str],
            recipe_command_ids: list[str],
            agent_summary: str | None = None,
            known_limitations: list[str] | None = None,
        ) -> str:
            """校验并冻结当前 attempt 的一个候选，不执行最终 S0-S5 判定。

            Args:
                candidate_id: 当前 attempt 内唯一的候选 ID。
                build_system: 实际执行的 cmake、make 或 autotools。
                supporting_command_ids: 支撑候选的成功 build command ID。
                artifact_paths: 相对 /artifacts 的候选文件路径。
                target_mapping: 冻结 target ID 到候选文件路径的映射。
                recipe_command_ids: 有序的 dependency/configure/build/artifact_stage command ID。
                agent_summary: 可选诊断摘要，不作为 evaluator 真值。
                known_limitations: 可选的已知限制。
            """
            self._consume_tool_budget(command=False)
            try:
                request = SubmitCandidateRequest(
                    candidate_id=candidate_id,
                    build_system=build_system,
                    supporting_command_ids=tuple(supporting_command_ids),
                    artifact_paths=tuple(artifact_paths),
                    target_mapping=target_mapping,
                    recipe_command_ids=tuple(recipe_command_ids),
                    agent_summary=agent_summary,
                    known_limitations=tuple(known_limitations or ()),
                )
            except AgentWorkflowContractError:
                return service.reject_invalid_contract(candidate_id).canonical_json()
            return service.submit(request).canonical_json()

        return [workflow_run_container_bash, workflow_submit_candidate_v1]

    def _consume_tool_budget(self, *, command: bool) -> None:
        self.tracker.observe_elapsed(time.monotonic() - self.started_monotonic)
        self.tracker.consume(tool_calls=1, commands=int(command), agent_steps=1)

    def _record_new_commands(self, before_command_ids: set[str], *, suppress_errors: bool = False) -> None:
        try:
            current = self.manager.load_session(self.session.session_id, self.session.thread_id)
            for command in current.commands:
                if command.command_id in before_command_ids:
                    continue
                self.ledger.append(
                    "command.completed",
                    command_id=command.command_id,
                    role=command.role,
                    exit_code=command.exit_code,
                    timed_out=command.timed_out,
                    termination=command.termination,
                    started_at=command.started_at,
                    completed_at=command.completed_at,
                    duration_seconds=command.duration_seconds,
                )
        except Exception as exc:
            self._append_if_available("command.observation_failed", error_class=type(exc).__name__)
            if not suppress_errors:
                raise

    async def _finalize(self, reason: AgentWorkflowTerminationReason) -> None:
        if self.state_machine.status not in {AgentWorkflowNodeStatus.FINALIZING, AgentWorkflowNodeStatus.COMPLETED, AgentWorkflowNodeStatus.CANCELLED}:
            self.state_machine.begin_finalization(reason)
            self._append_if_available("session.finalize_started", reason=reason.value)
        if self.finalizer is not None:
            result = self.finalizer(self.session)
            if inspect.isawaitable(result):
                await result
        if self.state_machine.status is AgentWorkflowNodeStatus.FINALIZING:
            self.state_machine.finish_finalization()
            self._append_if_available("session.finalized", node_status=self.state_machine.status.value)

    async def _finalize_safely(self, reason: AgentWorkflowTerminationReason) -> list[str]:
        failures: list[str] = []
        try:
            await self._finalize(reason)
        except Exception as exc:
            failures.append("finalizer_failed")
            try:
                self._append_if_available("session.finalize_failed", error_class=type(exc).__name__)
            except Exception:
                failures.append("finalizer_evidence_failed")
            if self.state_machine.status is AgentWorkflowNodeStatus.FINALIZING:
                try:
                    self.state_machine.finish_finalization()
                except Exception:
                    failures.append("finalizer_state_failed")
                else:
                    try:
                        self._append_if_available("session.finalized", node_status=self.state_machine.status.value, after_error=True)
                    except Exception:
                        failures.append("finalizer_evidence_failed")
        return failures

    def _append_if_available(self, event_type: str, **payload: Any) -> None:
        if self.ledger is not None:
            self.ledger.append(event_type, **payload)

    def _candidate_generated_observed(self) -> bool:
        base = Path(self.session.leadagent_artifacts_dir)
        return base.is_dir() and any(path.is_file() and not path.is_symlink() for path in base.rglob("*"))

    def _system_prompt(self) -> str:
        return (
            COMPILER_AGENT_CONFIG.system_prompt
            + "\n\n<agent_workflow_node_v1>\n"
            + "This version exposes submit_candidate_v1 instead of submit_build_result. "
            + "An accepted submission only freezes the candidate for an external evaluator; it does not prove build success. "
            + "Call submit_candidate_v1 once the candidate artifacts and command evidence are ready, then stop.\n"
            + "</agent_workflow_node_v1>"
        )

    def _task_prompt(self) -> str:
        return (
            f"执行 task {self.node_input.task_id} 的有界构建节点。"
            f"session_id={self.session.session_id}，commit={self.node_input.commit_sha}，"
            f"build_system_candidates={','.join(self.node_input.build_system_candidates)}。"
            "使用绑定工具构建或修复，并通过 submit_candidate_v1 冻结候选。"
        )


async def run_agent_workflow_node_v1(
    *,
    node_input: AgentBuildNodeInput,
    session: CompileSession,
    manager: CompileSessionManager,
    model: BaseChatModel,
    finalizer: Finalizer | None = None,
) -> AgentBuildNodeResult:
    runner = AgentWorkflowNodeRunner(
        node_input=node_input,
        session=session,
        manager=manager,
        model=model,
        finalizer=finalizer,
    )
    return await runner.run()
