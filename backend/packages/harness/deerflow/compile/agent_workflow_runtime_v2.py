"""Agent Workflow Runtime v2：修复提交合同与 LangGraph recursion 边界。"""

from __future__ import annotations

import threading
from enum import StrEnum
from typing import Any

from langchain_core.language_models import BaseChatModel
from langgraph.errors import GraphRecursionError

from deerflow.compile import agent_workflow_runtime as v1
from deerflow.compile.agent_workflow_schemas import AgentBuildNodeInput, AgentBuildNodeResult, SubmitCandidateRequest
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.schemas import CompileSession

AGENT_WORKFLOW_RUNTIME_VERSION = "agent-workflow-runtime-v2"
_ORIGINAL_CREATE_AGENT = v1.create_agent
_ORIGINAL_CANDIDATE_SERVICE = v1.AgentWorkflowCandidateService
_ORIGINAL_NODE_RUNNER = v1.AgentWorkflowNodeRunner
_agent_factory = _ORIGINAL_CREATE_AGENT
_RUNTIME_BINDING_LOCK = threading.Lock()


class AgentWorkflowRuntimeV2Error(RuntimeError):
    """Runtime v2 绑定或版本化合同无效。"""


class _V2RejectionCode(StrEnum):
    REQUIRED_ARTIFACT_UNDECLARED = "required_artifact_undeclared"


def graph_recursion_limit(max_agent_steps: int) -> int:
    """为每轮 model/tool 图节点留出空间，由业务预算负责终止 Agent。"""

    return max_agent_steps * 2 + 4


def _required_candidate_artifacts(node_input: AgentBuildNodeInput) -> tuple[str, ...]:
    value = node_input.initial_observation.get("required_candidate_artifacts", ())
    if not isinstance(value, tuple) or any(not isinstance(path, str) or not path for path in value):
        return ()
    return value


class AgentWorkflowCandidateService(_ORIGINAL_CANDIDATE_SERVICE):
    def _validate_against_session(self, request: SubmitCandidateRequest) -> list[Any]:
        codes = super()._validate_against_session(request)
        required_paths = set(_required_candidate_artifacts(self.node_input))
        if not required_paths.issubset(request.artifact_paths):
            codes.append(_V2RejectionCode.REQUIRED_ARTIFACT_UNDECLARED)
        return list(dict.fromkeys(codes))


class AgentWorkflowNodeRunner(_ORIGINAL_NODE_RUNNER):
    def _system_prompt(self) -> str:
        prompt = super()._system_prompt()
        suffix = "\n</agent_workflow_node_v1>"
        if not prompt.endswith(suffix):
            raise AgentWorkflowRuntimeV2Error("Runtime v1 system prompt 结构发生漂移")
        guidance = (
            "After the first successful build enters the post-build phase, use only artifact_stage commands needed to copy final files. "
            "Do not run build, diagnostic, or smoke commands there; the external evaluator owns functional verification. "
            "artifact_paths must include every required_candidate_artifacts entry and must contain only regular files, never symlinks. "
            "Call submit_candidate_v1 immediately after the candidate artifacts and command evidence are ready, then stop."
        )
        return prompt[: -len(suffix)] + "\n" + guidance + suffix


class _RecursionGuardAgent:
    def __init__(self, agent: Any, middleware: v1.AgentWorkflowExecutionMiddleware):
        self._agent = agent
        self._middleware = middleware

    def __getattr__(self, name: str) -> Any:
        return getattr(self._agent, name)

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        config = dict(kwargs.get("config") or {})
        config["recursion_limit"] = graph_recursion_limit(self._middleware.tracker.limits.max_agent_steps)
        kwargs["config"] = config
        try:
            return await self._agent.ainvoke(*args, **kwargs)
        except GraphRecursionError as exc:
            self._middleware.ledger.append("budget.guard_reached", reason="agent_steps", error_class=type(exc).__name__)
            raise v1.AgentWorkflowBudgetExceeded("agent_steps", self._middleware.tracker.snapshot()) from exc


def _create_agent_v2(*args: Any, **kwargs: Any) -> Any:
    middleware = kwargs.get("middleware")
    execution = next((item for item in middleware or () if isinstance(item, v1.AgentWorkflowExecutionMiddleware)), None)
    if execution is None:
        raise AgentWorkflowRuntimeV2Error("Runtime v2 缺少 execution middleware")
    return _RecursionGuardAgent(_agent_factory(*args, **kwargs), execution)


async def run_agent_workflow_node_v2(
    *,
    node_input: AgentBuildNodeInput,
    session: CompileSession,
    manager: CompileSessionManager,
    model: BaseChatModel,
    finalizer: v1.Finalizer | None = None,
) -> AgentBuildNodeResult:
    """在串行绑定中执行 Runtime v2，并在所有终态恢复冻结的 v1 模块。"""

    if not _RUNTIME_BINDING_LOCK.acquire(blocking=False):
        raise AgentWorkflowRuntimeV2Error("Runtime v2 只允许单进程串行执行")
    originals = (v1.create_agent, v1.AgentWorkflowCandidateService, v1.AgentWorkflowNodeRunner)
    try:
        expected = (_ORIGINAL_CREATE_AGENT, _ORIGINAL_CANDIDATE_SERVICE, _ORIGINAL_NODE_RUNNER)
        if originals != expected:
            raise AgentWorkflowRuntimeV2Error("Runtime v1 binding 已被其他执行修改")
        v1.create_agent = _create_agent_v2
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
    finally:
        _RUNTIME_BINDING_LOCK.release()
