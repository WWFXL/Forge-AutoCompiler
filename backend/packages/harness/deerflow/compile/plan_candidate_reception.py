"""新实验共同接收机器候选；原始响应、结构、装配和验收保持。"""

from __future__ import annotations

import json
import re

from langchain.agents import create_agent
from langchain.agents.structured_output import StructuredOutputValidationError, ToolStrategy
from langchain_core.messages import HumanMessage
from pydantic import ValidationError

from deerflow.compile import unified_plan_equivalent_observed as observed
from deerflow.compile.plan_agent import PlanResponseCapture
from deerflow.compile.plan_workflow import PlanContractError


def text_candidate(content):
    """只接受完整JSON对象，或仅带可选schema标题的单个JSON围栏。"""
    if not isinstance(content, str):
        raise PlanContractError("候选必须是完整JSON文本或结构化工具调用")
    text, method = content.strip(), "json_text"
    if not text.startswith("{"):
        match = re.fullmatch(r"(?:ObservedBuildActions\s*:\s*)?```json[ \t]*\r?\n([\s\S]*?)\r?\n```", text)
        if not match:
            raise PlanContractError("未交付唯一完整JSON候选；不从自由说明中猜测方案")
        text, method = match[1], "json_fence"

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("候选JSON包含重复字段")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("候选JSON含非标准常量：" + value)

    try:
        value = json.loads(text, object_pairs_hook=unique, parse_constant=invalid_constant)
    except ValueError as exc:
        raise PlanContractError("候选不是唯一完整的标准JSON对象") from exc
    if not isinstance(value, dict):
        raise PlanContractError("候选必须是JSON对象")
    return value, method


class CandidateReceptionMixin:
    """先由原计量链保存响应及用量，再允许可解析文本进入同一schema。"""

    def capture_response(self, response, request_sequence):
        required = self.requires_structured_response
        # 只在新propose入口放开呈现方式；探索额度仍由原structured标志控制。
        accepts_text = getattr(self, "accepts_text_candidates", False)
        if required and accepts_text:
            self.requires_structured_response = False
        try:
            super().capture_response(response, request_sequence)
        finally:
            self.requires_structured_response = required
        if required and accepts_text:
            for message in response.result:
                if message.type == "ai" and not message.tool_calls:
                    text_candidate(message.content)


def propose_received(*, model, task, source_root, session_root, meter, current_plan=None, handoff=None):
    """工具或文本候选共用原校验、一次结构纠错、恢复约束及完整装配。"""
    observed.validate_recovery(task, current_plan, handoff)
    revision = current_plan.revision + 1 if current_plan else 1
    meter.requires_structured_response = True
    meter.accepts_text_candidates = True
    meter.ledger.append("agent.started", revision=revision, recovery=current_plan is not None, contract="ObservedBuildActions", reception="tool_or_complete_json_v1")
    feedback = observed.recovery_feedback(current_plan, handoff)
    messages = [HumanMessage(content="请返回完整构建动作。额外权威恢复说明：" + json.dumps(feedback, ensure_ascii=False))]
    agent = create_agent(
        model=model, tools=observed.safe_readonly_tools(source_root, session_root), system_prompt=observed.OBSERVED_PROMPT, middleware=[meter], response_format=ToolStrategy(observed.ObservedBuildActions, handle_errors=False)
    )
    for correction in range(2):
        proposal = None
        try:
            result = agent.invoke({"messages": messages}, config={"max_concurrency": 1, "recursion_limit": 100, "callbacks": [PlanResponseCapture(meter)]})
            proposal, method = result.get("structured_response"), "tool_call"
            if proposal is None:
                last = result["messages"][-1]
                if last.type != "ai" or last.tool_calls:
                    raise PlanContractError("未交付ObservedBuildActions候选")
                value, method = text_candidate(last.content)
                proposal = observed.ObservedBuildActions.model_validate(value)
            if not isinstance(proposal, observed.ObservedBuildActions):
                raise PlanContractError("候选类型不符合ObservedBuildActions")
            meter.ledger.save(f"observed-actions-{revision}-{correction}.json", proposal.model_dump(mode="json"))
            plan = observed.assemble_observed(task, proposal, revision=revision)
            if current_plan is not None and not observed.execution_changed(current_plan, plan):
                raise PlanContractError("no_execution_change：仅修改说明不能修复；必须根据真实失败改变动作或检查")
        except (ValidationError, StructuredOutputValidationError, PlanContractError) as exc:
            if isinstance(exc, PlanContractError) and proposal is None:
                raise
            detail = str(exc)[:6000]
            meter.ledger.append("observed.proposal_rejected", revision=revision, correction=correction, category=type(exc).__name__, detail=detail)
            if correction:
                raise
            messages.append(HumanMessage(content="上次建议结构/装配不合法，尚未执行。仅允许一次纠错，保持原任务和验收。错误：" + detail))
            continue
        meter.ledger.append("candidate.accepted", revision=revision, correction=correction, presentation=method, plan_sha256=plan.fingerprint())
        return plan, proposal.reason
    raise PlanContractError("有界纠错结束")
