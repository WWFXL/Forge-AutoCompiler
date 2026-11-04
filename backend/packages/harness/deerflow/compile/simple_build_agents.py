"""简洁任务的共享模型计量和强工具Agent；不把Workflow状态策略注入基线。"""

from __future__ import annotations

import json
import time
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Literal

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from deerflow.compile import operations
from deerflow.compile.agent_workflow_runtime import AgentWorkflowExecutionMiddleware
from deerflow.compile.operation_window import OperationWindow
from deerflow.compile.plan_agent import PlanResponseCapture
from deerflow.compile.plan_agent_canary import StopWhenVerified
from deerflow.compile.plan_agent_context import CONTEXT_PROMPT, ContextCanaryMeter, safe_readonly_tools
from deerflow.compile.plan_workflow import PlanContractError, PlanStep
from deerflow.compile.simple_build_runtime import generated_reset_step, primary_artifacts, source_unchanged, validate_phase_command


class SimpleBuildMeter(ContextCanaryMeter):
    """沿用原始请求/响应/Token记录；新入口使用Flash价格与显式时窗。"""

    def __init__(self, *args, maximum_cost_usd="1.00", **kwargs):
        super().__init__(*args, **kwargs)
        self.maximum_cost_usd = Decimal(maximum_cost_usd)
        self.tracker.limits = replace(self.tracker.limits, max_model_requests=96, max_recorded_tokens=1_000_000, max_agent_steps=192, max_tool_calls=128, max_commands=64, node_timeout_seconds=1200)

    def _before_request(self):
        OperationWindow(self.deadline).request()
        if Decimal(str(self.cost_usd)) + Decimal("0.10") > self.maximum_cost_usd:
            raise PlanContractError("当前槽费用不足下一请求保守预留")
        return AgentWorkflowExecutionMiddleware._before_request(self)

    def capture_response(self, response, request_sequence):
        try:
            return super().capture_response(response, request_sequence)
        finally:
            self.cost_usd = float((Decimal(self.input_tokens) * Decimal("0.30") + Decimal(self.output_tokens) * Decimal("1.20")) / 1_000_000)

    def wrap_model_call(self, request, handler):
        context = getattr(self, "planning_context", None)
        if context is not None:
            return context.request(self, request, handler)
        return super().wrap_model_call(request, handler)

    def wrap_tool_call(self, request, handler):
        result = super().wrap_tool_call(request, handler)
        context = getattr(self, "planning_context", None)
        if context is not None:
            context.observe(request.tool_call["name"], request.tool_call["args"], result.content)
        return result


SIMPLE_TOOL_PROMPT = (
    """你是C/C++工具型构建Agent。读取公开任务与作者源码，在隔离容器构建主要程序或库。
采用作者推荐或默认的普通Linux构建，不人为增加Debug、静态、示例或benchmark要求，不缩小主要组件。
可以读取源码、日志、安装依赖、配置、编译和诊断。run_build_command执行一个逻辑阶段，Shell严格且各次独立。
原源码/测试不准改；允许新增正常生成文件，清理使用作者clean目标，不执行任意rm，不访问/repro或宿主。
需要重置配置/生成物时可显式调用reset_generated_outputs，保留原输入并删除本次新增文件；其命令也要进入成功recipe。
由你决定下一动作；系统不提供Workflow阶段动作建议。完成后用submit_primary_build提交成功build ID和最小有序成功构建recipe。
不要自行测试或暂存。外部系统独立定位主产物、交付、运行作者测试并干净重放；文字宣告不算完成。
提交反馈指出主组件未覆盖时可以继续修复；主构建接受后立即停止，外部测试失败不会覆盖已通过的主要构建。
"""
    + CONTEXT_PROMPT
)


class SimpleToolBuildService:
    """只复用执行记录与外部裁判；下一指令完全由工具Agent选择。"""

    def __init__(self, workflow, meter):
        self.workflow, self.meter = workflow, meter
        self.accepted = False

    def observe(self):
        current = self.workflow.manager.load_session(self.workflow.session_id, self.workflow.thread_id)
        return dict(commands=[dict(command_id=r.command_id, command=r.command, role=r.role, workdir=r.workdir, exit_code=r.exit_code, timed_out=r.timed_out) for r in current.commands], primary_accepted=self.accepted)

    def execute(self, command, role, workdir):
        if self.accepted:
            raise PlanContractError("主构建接受后停止Agent")
        step = PlanStep(step_id="tool-command", role="build" if role == "diagnostic" else role, command=command, workdir=workdir, source="工具Agent", expected="以实际执行反馈为准")
        if role == "diagnostic":
            # 诊断属于工具动作而非方案阶段，不扩大SimpleBuildPlan的阶段类型。
            step = step.model_copy(update={"role": "diagnostic"})
        self.meter.tracker.observe_elapsed(time.monotonic() - self.meter.started_monotonic)
        self.meter.tracker.consume(commands=1)
        try:
            validate_phase_command(step)
        except PlanContractError as exc:
            return dict(accepted=False, reason=str(exc))
        remaining = min(self.meter.tracker.remaining().node_seconds, self.workflow._remaining())
        if remaining < 1:
            raise PlanContractError("主任务时间已耗尽")
        record, output = self.workflow._post_command(step, min(self.workflow.budget.command_timeout_seconds, int(remaining)))
        return dict(command_id=record.command_id, exit_code=record.exit_code, timed_out=record.timed_out, output_tail=output.combined_output[-3000:], log_path="logs/" + Path(record.log_path).name)

    def submit(self, supporting_command_id, recipe_command_ids):
        w = self.workflow
        if self.accepted:
            return dict(accepted=True)
        w._observe()
        records = {r.command_id: r for r in w._session.commands}
        if not recipe_command_ids or len(set(recipe_command_ids)) != len(recipe_command_ids):
            return dict(accepted=False, reason="需要不重复的有序成功构建recipe")
        order = {r.command_id: i for i, r in enumerate(w._session.commands)}
        if any(c not in records for c in recipe_command_ids) or [order[c] for c in recipe_command_ids] != sorted(order[c] for c in recipe_command_ids):
            return dict(accepted=False, reason="recipe须引用实际命令且保持执行顺序")
        rows = [records[c] for c in recipe_command_ids]
        if supporting_command_id not in recipe_command_ids or any(r.exit_code != 0 or r.timed_out or r.role not in {"dependency", "configure", "build"} for r in rows):
            return dict(accepted=False, reason="recipe不能包含失败、诊断或未执行动作")
        supporting = records[supporting_command_id]
        if supporting.role != "build" or "build" not in operations.infer_command_roles(supporting.command):
            return dict(accepted=False, reason="supporting命令必须为实际成功构建")
        source_unchanged(w.root, w.baseline)
        w.primary = primary_artifacts(task=w.plan.task, reference=w.reference, root=w.root, baseline=w.baseline, deadline=time.monotonic() + min(30, w._remaining()))
        if w.primary["status"] != "passed":
            return dict(accepted=False, reason="主要组件未覆盖", primary_components=w.primary)
        # 工具Agent允许依赖/配置/构建交错；只保存实际顺序，不给基线套Workflow全局阶段排序。
        steps = tuple(
            PlanStep(step_id="build" if r.command_id == supporting_command_id else "tool-" + str(i), role=r.role, command=r.command, workdir=r.workdir, source="工具Agent实际成功命令", expected="实际成功") for i, r in enumerate(rows)
        )
        w.plan = w.plan.model_copy(update={"steps": steps})
        w.completed = {s.step_id: r.command_id for s, r in zip(steps, rows)}
        w.status = "primary_completed"
        w.layers.update(command_build_passed=True, primary_build_completed=True)
        w.timings["time_to_primary_seconds"] = time.monotonic() - w.started
        (w.directory / "primary-result.json").write_text(json.dumps(dict(method="strong_tool_agent", layers=w.layers, primary=w.primary, recipe_command_ids=recipe_command_ids), ensure_ascii=False, indent=2) + "\n")
        self.accepted = True
        return dict(accepted=True, primary_build_completed=True)

    def tools(self):
        @tool
        def reset_generated_outputs() -> str:
            """显式清理本次源码树新增生成文件，保护所有原输入；返回需要纳入重放recipe的实际命令ID。"""
            step = generated_reset_step(self.workflow.baseline)
            return json.dumps(self.execute(step.command, step.role, step.workdir), ensure_ascii=False)

        @tool
        def run_build_command(command: str, command_role: Literal["dependency", "configure", "build", "diagnostic"], workdir: str = "/workspace/repo") -> str:
            """执行独立的一条构建阶段或诊断指令，返回实际命令ID、退出码和日志。"""
            return json.dumps(self.execute(command, command_role, workdir), ensure_ascii=False)

        @tool
        def submit_primary_build(supporting_command_id: str, recipe_command_ids: list[str]) -> str:
            """提交实际成功构建和最小有序recipe，系统独立检查主要组件，接受后Agent立即停止。"""
            return json.dumps(self.submit(supporting_command_id, recipe_command_ids), ensure_ascii=False)

        return [run_build_command, reset_generated_outputs, submit_primary_build]


def run_simple_tool_agent(*, model, service, source_root, session_root, meter):
    meter.requires_structured_response = False
    meter.ledger.append("agent.started", recovery=False, contract="simple-tool-build-v1")
    agent = create_agent(model=model, tools=[*safe_readonly_tools(source_root, session_root), *service.tools()], system_prompt=SIMPLE_TOOL_PROMPT, middleware=[StopWhenVerified(lambda: service.accepted), meter])
    return agent.invoke({"messages": [HumanMessage(content="依据公开目标完成主要构建。")]}, config={"max_concurrency": 1, "recursion_limit": 200, "callbacks": [PlanResponseCapture(meter)]})
