"""简洁任务的两层经验：精确方案复用，以及每次规划/恢复开始的一次建议检索。"""

from __future__ import annotations

import copy
import json

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deerflow.compile.plan_workflow import PlanContractError, PlanStep
from deerflow.compile.project_experience import StateTargetBank
from deerflow.compile.simple_build_task import PublicBuildTask, SimpleBuildPlan


class SimpleProjectRecipe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(min_length=1)
    task: PublicBuildTask
    steps: tuple[PlanStep, ...]
    observed_validation: dict

    @model_validator(mode="after")
    def successful_source(self):
        value = self.observed_validation
        if not (value.get("layers", {}).get("full_completed") is True and value.get("source_unchanged") is True and value.get("cleanup", {}).get("succeeded") is True and value.get("layers", {}).get("clean_replay") == "passed"):
            raise ValueError("加载的成功方案缺少完整成功、源码、重放或清理依据")
        SimpleBuildPlan(task=self.task, steps=self.steps)
        return self

    def match(self, task: PublicBuildTask) -> bool:
        # plan_id仅是运行标签；源码、镜像、平台、目标、澄清与并行资源必须全部相同。
        return self.task.model_dump(exclude={"plan_id"}) == task.model_dump(exclude={"plan_id"})

    def materialize(self, task: PublicBuildTask) -> SimpleBuildPlan:
        if not self.match(task):
            raise PlanContractError("成功方案与当前公开任务不精确匹配")
        return SimpleBuildPlan(task=task, steps=self.steps)


def verified_simple_recipe(*, source_id, plan, validation):
    """保存实际成功动作及层级；不迁入旧固定测试/产物路径，也不请模型改写。"""
    if not (
        validation.get("layers", {}).get("full_completed") is True and validation.get("source_unchanged") is True and validation.get("cleanup", {}).get("succeeded") is True and validation.get("layers", {}).get("clean_replay") == "passed"
    ):
        raise PlanContractError("仅完整成功、源码保持且重放/清理成功的轨迹可登记可执行方案")
    return SimpleProjectRecipe(source_id=source_id, task=plan.task, steps=plan.steps, observed_validation=copy.deepcopy(validation))


class SimpleStateTargetBank(StateTargetBank):
    """复用已有库、排序及额度；目标词项改取简洁公开任务与已观察源码。"""

    def retrieve(self, **kwargs):
        if kwargs["mode"] == "none":
            return super().retrieve(**kwargs)
        packet = json.loads(kwargs["text"])
        task = packet.get("task", {})
        # 仅是旧排序器的内部输入适配，评测参考不参与检索或模型输入。
        public_target = dict(goal=task.get("goal"), clarification=task.get("common_clarification"), source_packet=packet.get("source_packet", []))
        packet["task"] = dict(verification_steps=[dict(expected=json.dumps(public_target, ensure_ascii=False))])
        return super().retrieve(**(kwargs | dict(text=json.dumps(packet, ensure_ascii=False))))


def select_simple_experience(*, bank, task, packet, family, ledger):
    """调用方在一次Agent任务开始时调用一次；结果固定到该次任务结束。"""
    handoff = packet.get("handoff") or {}
    stage = "initial"
    if handoff:
        step = next((s for s in (packet.get("current_plan") or {}).get("steps", []) if s["step_id"] == handoff.get("step_id")), {})
        stage = step.get("role", "build" if handoff.get("primary_components") else "recovery")
    context = bank.retrieve(build_system=task.build_system, family=family, stage=stage, text=json.dumps(packet, ensure_ascii=False), mode="structured")
    ledger.append("experience.retrieved", stage=stage, source_ids=context["sources"], bytes=context["bytes"], policy="once_per_agent_task")
    return copy.deepcopy(context)
