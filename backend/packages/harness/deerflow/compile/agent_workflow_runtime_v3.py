"""Agent Workflow Runtime v3：在 candidate 冻结前执行完整交付验证。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langchain_core.language_models import BaseChatModel

from deerflow.compile import agent_workflow_runtime as v1
from deerflow.compile import agent_workflow_runtime_v2 as v2
from deerflow.compile.agent_workflow_schemas import AgentBuildNodeInput, AgentBuildNodeResult, SubmitCandidateRequest
from deerflow.compile.candidate_verifier import (
    CandidateVerificationCode,
    CandidateVerificationFinding,
    CandidateVerifier,
    FunctionalCheckRunner,
    PrefreezeSubmitCandidateResponse,
)
from deerflow.compile.external_evaluator import FunctionalOracleSpec
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.schemas import CompileSession

AGENT_WORKFLOW_RUNTIME_VERSION = "agent-workflow-runtime-v3"
_ORIGINAL_CREATE_AGENT = v2._ORIGINAL_CREATE_AGENT
_ORIGINAL_CANDIDATE_SERVICE = v2._ORIGINAL_CANDIDATE_SERVICE
_ORIGINAL_NODE_RUNNER = v2._ORIGINAL_NODE_RUNNER
_RUNTIME_BINDING_LOCK = v2._RUNTIME_BINDING_LOCK
_agent_factory = _ORIGINAL_CREATE_AGENT
_active_verifier: CandidateVerifier | None = None


class AgentWorkflowRuntimeV3Error(RuntimeError):
    """Runtime v3 绑定或 pre-freeze verifier 合同无效。"""


class AgentWorkflowCandidateService(v2.AgentWorkflowCandidateService):
    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        if _active_verifier is None:
            raise AgentWorkflowRuntimeV3Error("Runtime v3 缺少活动 candidate verifier")
        self.verifier = _active_verifier
        self._verification_findings: tuple[CandidateVerificationFinding, ...] = ()

    def submit(self, request: SubmitCandidateRequest) -> PrefreezeSubmitCandidateResponse:
        self._verification_findings = ()
        response = super().submit(request)
        return PrefreezeSubmitCandidateResponse.from_base(response, self._verification_findings)

    def reject_invalid_contract(self, candidate_id: str | None) -> PrefreezeSubmitCandidateResponse:
        response = super().reject_invalid_contract(candidate_id)
        return PrefreezeSubmitCandidateResponse.from_base(response)

    def _validate_against_session(self, request: SubmitCandidateRequest) -> list[Any]:
        codes = super()._validate_against_session(request)
        if codes:
            return codes
        result = self.verifier.verify(
            request=request,
            node_input=self.node_input,
            session=self.session,
            manager=self.manager,
        )
        self._verification_findings = result.findings
        self.ledger.append("candidate.prefreeze_verification_completed", **result.evidence_payload())
        codes.extend(CandidateVerificationCode(finding.code) for finding in result.findings)
        return list(dict.fromkeys(codes))

    def _record_rejection(self, request: SubmitCandidateRequest, response: Any) -> None:
        self.ledger.append(
            "candidate.submit_rejected",
            candidate_id=request.candidate_id,
            rejection_codes=list(response.rejection_codes),
            rejection_details=[finding.as_payload() for finding in self._verification_findings],
        )


class AgentWorkflowNodeRunner(v2.AgentWorkflowNodeRunner):
    def _system_prompt(self) -> str:
        prompt = super()._system_prompt()
        suffix = "\n</agent_workflow_node_v1>"
        if not prompt.endswith(suffix):
            raise AgentWorkflowRuntimeV3Error("Runtime v2 system prompt 结构发生漂移")
        guidance = (
            "submit_candidate_v1 now runs a trusted pre-freeze verifier over the complete /artifacts delivery. "
            "When it returns rejection_details, repair only the reported delivery paths, target mapping, or functional oracle failure, then resubmit within the same attempt. "
            "A pre-freeze pass still does not replace the independent external evaluator."
        )
        return prompt[: -len(suffix)] + "\n" + guidance + suffix


def _create_agent_v3(*args: Any, **kwargs: Any) -> Any:
    middleware = kwargs.get("middleware")
    execution = next((item for item in middleware or () if isinstance(item, v1.AgentWorkflowExecutionMiddleware)), None)
    if execution is None:
        raise AgentWorkflowRuntimeV3Error("Runtime v3 缺少 execution middleware")
    return v2._RecursionGuardAgent(_agent_factory(*args, **kwargs), execution)


def _resolve_oracle_spec(
    node_input: AgentBuildNodeInput,
    oracle_registry: Mapping[str, FunctionalOracleSpec],
) -> FunctionalOracleSpec:
    oracle_ref = node_input.target_contract.functional_oracle_ref
    spec = oracle_registry.get(oracle_ref)
    if spec is None:
        raise AgentWorkflowRuntimeV3Error(f"未注册 pre-freeze functional oracle: {oracle_ref}")
    spec.validate()
    if spec.oracle_ref != oracle_ref:
        raise AgentWorkflowRuntimeV3Error("pre-freeze functional oracle identity 不匹配")
    return spec


async def run_agent_workflow_node_v3(
    *,
    node_input: AgentBuildNodeInput,
    session: CompileSession,
    manager: CompileSessionManager,
    model: BaseChatModel,
    oracle_registry: Mapping[str, FunctionalOracleSpec],
    functional_runner: FunctionalCheckRunner | None = None,
    finalizer: v1.Finalizer | None = None,
) -> AgentBuildNodeResult:
    """串行绑定 Runtime v3，并在所有终态恢复 v1 模块。"""

    global _active_verifier
    if not _RUNTIME_BINDING_LOCK.acquire(blocking=False):
        raise AgentWorkflowRuntimeV3Error("Runtime v3 只允许单进程串行执行")
    originals = (v1.create_agent, v1.AgentWorkflowCandidateService, v1.AgentWorkflowNodeRunner)
    try:
        expected = (_ORIGINAL_CREATE_AGENT, _ORIGINAL_CANDIDATE_SERVICE, _ORIGINAL_NODE_RUNNER)
        if originals != expected:
            raise AgentWorkflowRuntimeV3Error("Runtime v1 binding 已被其他执行修改")
        spec = _resolve_oracle_spec(node_input, oracle_registry)
        _active_verifier = CandidateVerifier(oracle_spec=spec, functional_runner=functional_runner)
        v1.create_agent = _create_agent_v3
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
            _active_verifier = None
    finally:
        _RUNTIME_BINDING_LOCK.release()


__all__ = [
    "AGENT_WORKFLOW_RUNTIME_VERSION",
    "AgentWorkflowCandidateService",
    "AgentWorkflowNodeRunner",
    "AgentWorkflowRuntimeV3Error",
    "run_agent_workflow_node_v3",
]
