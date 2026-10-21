"""先精确暂存再运行固定测试的任务装配；三策略共用可信CLI验收。"""

from __future__ import annotations

import json
import time
from pathlib import Path

from langchain_core.tools import tool

from deerflow.compile import operations
from deerflow.compile.boundary_execution import BoundaryToolService, BoundaryWorkflow
from deerflow.compile.generated_file_boundary import original_command
from deerflow.compile.plan_agent import PlanProposal, PlanTask
from deerflow.compile.plan_agent_canary import unchanged
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.task_selected_make_plan import selected_make_actions
from deerflow.compile.tool_plan import ToolPlanNeedsAgent


def boundary_tool_actions(task, source_root, boundary):
    """模板不自动改写生成命令；声明与模板bootstrap不一致时明确升级。"""
    actions, receipt = selected_make_actions(task, source_root)
    declared = {(r.command, r.workdir) for r in boundary.generations}
    for step in actions.steps:
        if step.step_id == "bootstrap" and declared and (step.command, step.workdir) not in declared:
            raise ToolPlanNeedsAgent("模板bootstrap不符合预声明生成关系；不猜源码依赖图或替换为人工配方")
    return actions, receipt


class StagedVerificationTask(PlanTask):
    """仅由冻结任务选择装配顺序，模型不能更改测试或暂存指令。"""

    def materialize(self, proposal: PlanProposal, *, revision: int):
        stages = [s for s in proposal.steps if s.role == "artifact_stage"]
        builds = [s for s in proposal.steps if s.role == "build"]
        if len(stages) != 1 or stages[0].step_id != "stage" or not builds:
            raise PlanContractError("共同装配必须包含唯一系统stage和成功构建候选")
        stage = stages[0].model_copy(update={"requires": (builds[-1].step_id,)})
        core = [s for s in proposal.steps if s.role not in ("smoke", "artifact_stage")]
        # super仍逐字段核验全部固定测试，BuildPlan仍验证依赖、阶段及精确交付。
        return super().materialize(PlanProposal(reason=proposal.reason, steps=[*core, stage, *[s for s in proposal.steps if s.role == "smoke"]]), revision=revision)


def submit_fixed_delivery(*, task, boundary, session, supporting_command_id, recipe_command_ids, verification_command_ids):
    """唯一可信提交点：全套原测试仍进verify，只有独立CLI记录用于短smoke。"""
    if len(verification_command_ids) != len(task.verification_steps) or len(set(verification_command_ids)) != len(verification_command_ids):
        raise PlanContractError("完整固定测试记录数量或身份不符")
    records = {r.command_id: r for r in session.commands}
    evidence = None
    for step, command_id in zip(task.verification_steps, verification_command_ids, strict=True):
        record = records.get(command_id)
        if record is None or record.exit_code != 0 or record.timed_out or record.role != "smoke":
            raise PlanContractError("固定测试缺失、失败或超时")
        if (original_command(boundary, record.command), record.workdir) != (step.command, step.workdir):
            raise PlanContractError("固定测试命令被替换")
        output = Path(record.log_path).read_text()
        if not all(marker in output for marker in step.required_output):
            raise PlanContractError("固定测试完整输出依据缺失")
        if step.step_id == "delivery-cli":
            import hashlib

            evidence = operations.SuccessfulCommandVerification(command_id=record.command_id, command=record.command, workdir=record.workdir, exit_code=0, output=output, output_sha256=hashlib.sha256(output.encode()).hexdigest())
    if evidence is None:
        raise PlanContractError("缺少独立交付CLI记录")
    artifacts = Path(session.metadata_path).parent / "artifacts"
    actual = {p.relative_to(artifacts).as_posix() for p in artifacts.rglob("*") if p.is_file() or p.is_symlink()}
    if actual != set(task.artifact_paths):
        raise PlanContractError("精确交付集合不匹配")
    return operations.submit_build_result_impl(
        session=session,
        supporting_command_id=supporting_command_id,
        recipe_command_ids=recipe_command_ids,
        verification_command_ids=verification_command_ids,
        executable_verification_policy=operations.ExecutableVerificationPolicy.successful_commands({"rtorrent": evidence}),
    )


class StagedBoundaryWorkflow(BoundaryWorkflow):
    def __init__(self, *, task, **kwargs):
        self.task = task
        super().__init__(**kwargs)

    def verify(self):
        with self.manager.session_lock(self.thread_id, self.session_id):
            recipe = self.replay_recipe()
            if self._remaining() <= 0:
                self.status = "budget_exhausted"
                self._persist()
                return self.snapshot()
            services = operations.get_compile_services()
            if services.manager is not self.manager or services.runtime is not self.runtime:
                raise PlanContractError("验收服务必须使用同一权威Session")
            submit_fixed_delivery(
                task=self.task,
                boundary=self.boundary,
                session=self._session,
                supporting_command_id=recipe.supporting_command_id,
                recipe_command_ids=[s.command_id for s in recipe.steps],
                verification_command_ids=[s.command_id for s in recipe.verification_steps],
            )
            self._session = self._load()
            self._expected_frontier = self._frontier()
            if self._session.status == "verified" and self._session.replay_attempts and self._session.replay_attempts[-1].status == "passed":
                self.status = "verified"
                self._persist()
                return self.snapshot()
            return self._request_handoff("acceptance_failed")


class StagedBoundaryToolService(BoundaryToolService):
    def tools(self):
        original = super().tools()

        @tool
        def submit_verified_build(supporting_command_id: str, recipe_command_ids: list[str]) -> str:
            """同一固定测试、独立CLI、精确交付和clean replay；不能靠文字宣告成功。"""
            unchanged(self.source_root, self.frozen)
            self.meter.tracker.observe_elapsed(time.monotonic() - self.meter.started_monotonic)
            if self.meter.tracker.remaining().node_seconds <= 0:
                raise PlanContractError("节点时间已耗尽，不开始验收")
            if set(self.verifications) != {s.step_id for s in self.task.verification_steps}:
                return json.dumps({"accepted": False, "reason": "固定完整测试尚未通过"}, ensure_ascii=False)
            message = submit_fixed_delivery(
                task=self.task,
                boundary=self.boundary,
                session=self.current(),
                supporting_command_id=supporting_command_id,
                recipe_command_ids=recipe_command_ids,
                verification_command_ids=[self.verifications[s.step_id] for s in self.task.verification_steps],
            )
            self.verified = self.current().status == "verified"
            return json.dumps({"accepted": self.verified, "result": message}, ensure_ascii=False)

        return [submit_verified_build if t.name == "submit_verified_build" else t for t in original]
