"""在一次交接内修订并执行局部动作，确认实际进展后交还Workflow。"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from pydantic import ValidationError

from deerflow.compile.goal_state import GoalStateWorkflow
from deerflow.compile.plan_agent import PlanResponseCapture
from deerflow.compile.plan_agent_canary import StopWhenVerified
from deerflow.compile.plan_agent_context import safe_readonly_tools
from deerflow.compile.plan_workflow import BuildPlan, PlanContractError
from deerflow.compile.source_preparation import PREPARATION_ID
from deerflow.compile.unified_plan_equivalent_observed import ObservedBuildActions, assemble_observed, execution_changed

RANK = {"dependency": 0, "configure": 1, "build": 2}


class LocalRecoveryInputError(PlanContractError):
    """Agent可以修正的输入错误；运行时、计量及源码异常直接终止。"""


class LocalRecovery:
    """只使用Workflow的真实执行通道；固定测试和交付不开放给恢复Agent。"""

    def __init__(self, workflow, task):
        workflow._observe()
        if workflow.status != "needs_handoff" or not workflow.handoff:
            raise PlanContractError("局部恢复需要活动交接")
        self.workflow, self.task = workflow, task
        self.initial = deepcopy(workflow.handoff)
        failed = next((s for s in workflow.plan.steps if s.step_id == self.initial.get("step_id")), None)
        self.target = failed.role if failed and failed.role in RANK else "build"
        self.returned = False
        self.revisions = 0
        self.executed = []
        self.attempts = set()
        self.last_result = None
        self.workflow.meter.ledger.append("local_recovery.started", handoff=self.initial, target_role=self.target)

    def observe(self):
        wf = self.workflow
        return {
            "target_role": self.target,
            "return_condition": "目标角色及其前置动作均有有效成功记录；适用配置目标必须满足；原测试与交付交由Workflow继续",
            "current_plan": wf.plan.model_dump(mode="json"),
            "state": wf.snapshot(),
            "last_result": self.last_result,
            "executed_command_ids": list(self.executed),
            "returned": self.returned,
        }

    def _active(self):
        wf = self.workflow
        wf._observe()
        if self.returned or wf.status != "needs_handoff" or not wf.handoff or wf.handoff["handoff_id"] != self.initial["handoff_id"]:
            raise PlanContractError("局部交接已失效或已交还")
        if wf._remaining() <= 0:
            raise PlanContractError("局部恢复执行资源不足")

    def revise(self, actions: ObservedBuildActions):
        wf = self.workflow
        with wf.manager.session_lock(wf.thread_id, wf.session_id):
            self._active()
            try:
                plan = assemble_observed(self.task, actions, revision=wf.plan.revision + 1)
                # 归档源码准备由系统添加，不能由Agent重复或更改。
                if wf.plan.steps[0].step_id == PREPARATION_ID:
                    plan = BuildPlan.model_validate({**plan.model_dump(), "steps": (wf.plan.steps[0], *plan.steps)})
            except (PlanContractError, ValidationError) as exc:
                raise LocalRecoveryInputError(str(exc)) from exc
            if not execution_changed(wf.plan, plan):
                raise LocalRecoveryInputError("无执行变化的修订不能触发重复执行")
            wf.apply_revision(handoff_id=self.initial["handoff_id"], plan=plan, reason=actions.reason)
            self.revisions += 1
            wf.status = "needs_handoff"
            wf.handoff = {**self.initial, "plan_sha256": plan.fingerprint(), "command_frontier": wf._expected_frontier}
            wf.meter.ledger.append("local_recovery.revised", revision=plan.revision, plan_sha256=plan.fingerprint())
            wf._persist()
            return self.observe()

    def execute(self, step_id: str):
        wf = self.workflow
        with wf.manager.session_lock(wf.thread_id, wf.session_id):
            self._active()
            if wf.commands_used >= wf.budget.max_commands:
                raise PlanContractError("局部恢复执行资源不足")
            step = next((s for s in wf.plan.steps if s.step_id == step_id), None)
            if step is None or step.role not in RANK or RANK[step.role] > RANK[self.target]:
                raise LocalRecoveryInputError("只能执行恢复目标及其前置构建动作，不能接管原测试或交付")
            remaining = [s for s in wf.plan.steps if s.step_id not in wf.completed and s.role in RANK]
            if not self.revisions or not remaining or remaining[0].step_id != step_id or not set(step.requires).issubset(wf.completed):
                raise LocalRecoveryInputError("先修订方案，再执行下一就绪步骤；已成功步骤不重复")
            inputs = tuple((s.step_id, wf.completed.get(s.step_id)) for s in wf.plan.steps[: wf.plan.steps.index(step)])
            signature = (step.role, step.command, step.workdir, step.required_output, inputs)
            if signature in self.attempts:
                raise LocalRecoveryInputError("相同动作和前置执行证据已尝试；必须实际改变动作或前置状态")
            self.attempts.add(signature)
            before = {r.command_id for r in wf._session.commands}
            passed = wf._execute(step)
            records = [r for r in wf._session.commands if r.command_id not in before]
            self.executed.extend(r.command_id for r in records)
            self.last_result = {"step_id": step_id, "passed": passed, "commands": [wf._command_evidence(r) for r in records], "configuration_state": deepcopy(wf.goal_state)}
            wf.handoff.update(plan_sha256=wf.plan.fingerprint(), command_frontier=wf._expected_frontier)
            wf.meter.ledger.append("local_recovery.executed", **self.last_result)
            wf._persist()
            return self.last_result

    def finish(self):
        wf = self.workflow
        with wf.manager.session_lock(wf.thread_id, wf.session_id):
            self._active()
            needed = [s for s in wf.plan.steps if s.role in RANK and RANK[s.role] <= RANK[self.target]]
            if not needed or any(s.step_id not in wf.completed for s in needed):
                raise LocalRecoveryInputError("恢复目标尚无完整有效执行证据，不能交还")
            if self.target in {"configure", "build"} and wf.goals and wf.goal_state["status"] != "satisfied":
                raise LocalRecoveryInputError("配置目标仍未知或偏离，不能交还")
            if not self.executed or not self.revisions:
                raise LocalRecoveryInputError("必须完成实际修订与执行，不能把旧状态自报为恢复")
            self.returned = True
            wf.status, wf.handoff = "pending", None
            wf.meter.ledger.append("local_recovery.returned", target_role=self.target, completed=dict(wf.completed), command_ids=self.executed, revisions=self.revisions)
            wf._persist()
            return self.observe()


class LocalRecoveryWorkflow(GoalStateWorkflow):
    """复用原执行器；局部恢复过程由回调处理，正常路径仍直接执行。"""

    def __init__(self, *, recover, **kwargs):
        self.recover = recover
        super().__init__(**kwargs)

    def run(self):
        state = super().run()
        while state["status"] == "needs_handoff":
            self.recover(self)
            if self.status != "pending":
                raise PlanContractError("恢复未交还可继续状态")
            state = super().run()
        return state

    def verify(self):
        state = super().verify()
        while state["status"] == "needs_handoff":
            self.recover(self)
            state = self.run()
            if state["status"] != "ready_for_verification":
                return state
            state = super().verify()
        return state


LOCAL_PROMPT = """你是C/C++构建的局部恢复Agent。在当前一次交接内分析真实失败，修订并执行恢复目标及前置动作，然后立即交还Workflow。
固定源码、原测试、目标和交付不允许修改。最多2并行、严格Shell、每条命令一个逻辑阶段，不访问宿主或个人知识库。
先按需用源码/日志工具诊断。revise_recovery_plan接收完整ObservedBuildActions的JSON，仅dependency/configure/build，按此顺序，最后步骤标识必须build。
字段包括reason及steps；每步step_id/role/command/source/expected/workdir/requires/stdout_contains/files_exist/directories_exist/diagnostic_paths。
使用/workspace/repo；存在性检查使用files_exist/directories_exist，不要将文件路径放进日志断言。系统固定测试、stage、forge-source-prepare不要返回。
execute_recovery_step通过容器bash实际执行已修订方案的下一步，返回真实结果。失败后可继续读日志并再次修订。需要的依赖和配置修复必须进入完整方案，以便干净重放；逻辑失效不会自动清理旧缓存。
不能直接运行整个后续流程、原测试或交付。目标及前置动作成功且适用配置目标满足后调用return_to_workflow，不用普通文本自报成功。
"""


def run_local_agent(*, model, workflow, task, session_root):
    recovery = LocalRecovery(workflow, task)
    meter = workflow.meter

    def feedback(operation):
        try:
            value = operation()
            # 模型只看容器日志路径，不暴露宿主Session路径。
            rendered = json.dumps(value, ensure_ascii=False, default=str)
            rendered = rendered.replace(str(session_root), "")
            return rendered
        except (LocalRecoveryInputError, ValidationError) as exc:
            # 只有输入问题可继续诊断；预算、源码、外部状态及Provider异常直接传播。
            meter.ledger.append("local_recovery.input_rejected", detail=str(exc)[:3000])
            return json.dumps({"accepted": False, "error": str(exc)[:3000]}, ensure_ascii=False)

    @tool
    def revise_recovery_plan(actions_json: str) -> str:
        """提交完整ObservedBuildActions JSON；校验后保留有效前缀并失效变化后缀，不自动执行。"""
        return feedback(lambda: recovery.revise(ObservedBuildActions.model_validate_json(actions_json)))

    @tool
    def execute_recovery_step(step_id: str) -> str:
        """实际执行当前修订方案的下一就绪步骤，返回退出码、日志和配置状态；不允许测试或交付。"""
        return feedback(lambda: recovery.execute(step_id))

    @tool
    def return_to_workflow() -> str:
        """恢复目标有实际成功证据后交还Workflow；原测试和交付由系统继续。"""
        return feedback(recovery.finish)

    original_packet = meter.packet

    def packet():
        # 状态仍绑定真实命令；模型收到的路径统一为Session内相对路径。
        value = {**original_packet(), "local_recovery": recovery.observe()}
        return json.loads(json.dumps(value, ensure_ascii=False).replace(str(session_root) + "/", ""))

    meter.packet = packet
    meter.requires_structured_response = False
    meter.accepts_text_candidates = False
    meter.ledger.append("agent.started", recovery=True, revision=workflow.plan.revision + 1, contract="LocalRecovery")
    try:
        agent = create_agent(
            model=model,
            tools=[*safe_readonly_tools(workflow.source_root, Path(session_root)), revise_recovery_plan, execute_recovery_step, return_to_workflow],
            system_prompt=LOCAL_PROMPT,
            middleware=[meter, StopWhenVerified(lambda: recovery.returned)],
        )
        agent.invoke({"messages": [HumanMessage(content="根据当前实际状态修复并交还Workflow。")]}, config={"max_concurrency": 1, "recursion_limit": 100, "callbacks": [PlanResponseCapture(meter)]})
        if not recovery.returned:
            raise PlanContractError("Agent没有完成有证据的局部恢复交还")
    finally:
        meter.packet = original_packet
