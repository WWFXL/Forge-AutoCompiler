"""独立强基线候选：自动提交命令溯源，仍委托原有严格验收。"""

from __future__ import annotations

import json

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from deerflow.compile.plan_agent import PlanResponseCapture
from deerflow.compile.plan_agent_canary import TOOL_PROMPT, StopWhenVerified
from deerflow.compile.plan_agent_context import CONTEXT_PROMPT, safe_readonly_tools


def automatic_submission_arguments(session):
    """只从权威记录选择成功阶段；不推断命令、不修改测试凭证。"""
    successful = [row for row in session.commands if row.exit_code == 0 and not row.timed_out]
    builds = [row for row in successful if row.role == "build"]
    if not builds:
        return None
    return {
        "supporting_command_id": builds[-1].command_id,
        "recipe_command_ids": [row.command_id for row in successful if row.role in ("dependency", "configure", "build", "artifact_stage")],
    }


def automatic_tools(service):
    """仅替换手工ID入参；固定测试、freshness和clean replay仍由原服务判断。"""
    originals = service.tools()
    submit = next(item for item in originals if item.name == "submit_verified_build")

    @tool
    def submit_verified_build() -> str:
        """自动取得权威成功构建及有序配方ID，执行原有精确交付、固定测试和clean replay验收。"""
        current = service.current()
        arguments = automatic_submission_arguments(current)
        if arguments is None:
            return json.dumps({"accepted": False, "reason": "尚无成功构建记录"}, ensure_ascii=False)
        service.meter.ledger.append("submission.provenance_selected", observed_command_count=len(current.commands), **arguments)
        return submit.invoke(arguments)

    return [submit_verified_build if item.name == "submit_verified_build" else item for item in originals]


AUTOMATIC_PROMPT = TOOL_PROMPT.replace(
    "submit_verified_build提交成功构建ID及最小有序成功recipe，不能包含失败、diagnostic或smoke。",
    "submit_verified_build无需参数：系统自动选择权威记录中的最后成功构建及按原顺序的成功dependency/configure/build/artifact_stage命令，排除失败、超时、diagnostic和smoke；固定测试仍由run_fixed_tests执行并供严格验收。",
)


def run_tool_agent_automatic(*, model, service, source_root, session_root, meter):
    agent = create_agent(
        model=model,
        tools=[*safe_readonly_tools(source_root, session_root), *automatic_tools(service)],
        system_prompt=AUTOMATIC_PROMPT + CONTEXT_PROMPT,
        middleware=[StopWhenVerified(lambda: service.verified), meter],
    )
    return agent.invoke({"messages": [HumanMessage(content="根据当前状态完成构建任务。")]}, config={"max_concurrency": 1, "recursion_limit": 150, "callbacks": [PlanResponseCapture(meter)]})
