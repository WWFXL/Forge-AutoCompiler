"""简洁任务的两层经验：精确方案复用，以及每次规划/恢复开始的一次建议检索。"""

from __future__ import annotations

import copy
import json

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deerflow.compile.plan_workflow import PlanContractError, PlanStep
from deerflow.compile.project_experience import StateTargetBank, domain_terms
from deerflow.compile.simple_build_task import SIMPLE_GOAL, PublicBuildTask, SimpleBuildPlan

SIMPLE_EXPERIENCE_PROMPT = """
historical_build_experience是其他项目的简短条件化动作建议，仅辅助当前规划，不是待逐项完成的检查清单。
优先使用当前已读文件判断适用性；不适用的建议直接忽略，不为核查旧经验另行遍历源码。
仅在当前证据支持conditions时采用action，注意not_applicable；outcome仅表示来源局部观察。
不能照搬其他项目的选项、路径或依赖，不能因此添加目标/测试要求。经验不能覆盖当前任务、真实失败和独立验证。
"""


def recipe_validation_succeeded(task: PublicBuildTask, validation: dict) -> bool:
    """按来源的真实任务范围保存方案；主构建成功不能冒称旧完整任务通过。"""
    layers = validation.get("layers", {})
    completed = validation.get("validation_scope") == "main_build" and layers.get("main_build_task_completed") is True and layers.get("delivery") == "passed" if task.task_version == "main-build-v1" else layers.get("full_completed") is True
    return bool(completed and validation.get("source_unchanged") is True and validation.get("cleanup", {}).get("succeeded") is True and layers.get("clean_replay") == "passed" and layers.get("delivery") in {None, "passed"})


class SimpleProjectRecipe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(min_length=1)
    task: PublicBuildTask
    steps: tuple[PlanStep, ...]
    observed_validation: dict

    @model_validator(mode="after")
    def successful_source(self):
        if not recipe_validation_succeeded(self.task, self.observed_validation):
            raise ValueError("加载的成功方案缺少对应任务成功、源码、重放或清理依据")
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
    if not recipe_validation_succeeded(plan.task, validation):
        raise PlanContractError("仅对应任务成功、源码保持且交付/重放/清理成功的轨迹可登记可执行方案")
    return SimpleProjectRecipe(source_id=source_id, task=plan.task, steps=plan.steps, observed_validation=copy.deepcopy(validation))


def select_simple_recipe(*, recipes, task: PublicBuildTask) -> SimpleProjectRecipe | None:
    """按完整公开任务查找成功方案；库名相同不足以复用，重复身份须先消歧。"""
    matches = [recipe for recipe in recipes if recipe.match(task)]
    if len(matches) > 1:
        raise PlanContractError("成功方案库含多个相同任务身份，不能隐式按顺序挑选")
    return matches[0] if matches else None


class SimpleStateTargetBank(StateTargetBank):
    """从旧库选择匹配当前证据的少量动作；不附带整份来源轨迹和其他阶段经验。"""

    def retrieve(self, *, build_system, family, stage, text, mode, limit_bytes=4096, top_k=2):
        if mode == "none":
            return dict(mode=mode, sources=[], items=[], bytes=0)
        if mode != "structured":
            raise ValueError("简洁任务只支持无经验或条件化动作建议")
        packet = json.loads(text)
        task = packet.get("task", {})
        # 不使用库名、SHA、参考命令或整套验收脚本匹配；通用目标不能制造相似性。
        visible = dict(clarification=task.get("common_clarification"), source_packet=packet.get("source_packet", []), handoff=packet.get("handoff"))
        generic = domain_terms(SIMPLE_GOAL) | {"cmake", "make", "autotools", "readme", "build", "configure", "source_packet", "content", "path", "true", "false", "null"}
        query = domain_terms(json.dumps(visible, ensure_ascii=False)) - generic
        ranked = []
        for index, entry in enumerate(self.entries):
            source = self.sources[entry["source_id"]]
            if source["family"] == family or source["build_system"] != build_system:
                continue
            if entry["stage"] not in ({"dependency", "configure", "build"} if stage == "initial" else {stage}):
                continue
            # 只匹配适用条件与已观察状态，不能因“不适用”或动作里碰巧出现词项而入选。
            terms = domain_terms(json.dumps(dict(conditions=entry.get("conditions", []), state=entry.get("state", "")), ensure_ascii=False)) - generic
            matched = sorted(query & terms)
            if not matched:
                continue
            ranked.append((-len(matched), entry["source_id"], index, entry, matched))
        selected, size = [], 0
        for _, identifier, index, entry, matched in sorted(ranked):
            if len(selected) >= top_k:
                break
            advice = {k: entry[k] for k in ("stage", "conditions", "state", "action", "outcome", "not_applicable", "verification_scope", "command_ids") if k in entry}
            item = dict(source_id=identifier, experience_id=entry.get("experience_id", str(index)), source_family=self.sources[identifier]["family"], matched_terms=matched[:8], advice=advice)
            length = len(json.dumps(item, ensure_ascii=False).encode())
            if size + length <= limit_bytes:
                selected.append(item)
                size += length
        return dict(mode=mode, sources=list(dict.fromkeys(s["source_id"] for s in selected)), items=selected, bytes=size, maximum_bytes=limit_bytes, top_k=top_k, policy="matched_action_advice_v1", abstained=not bool(selected))


def select_simple_experience(*, bank, task, packet, family, ledger):
    """调用方在一次Agent任务开始时调用一次；结果固定到该次任务结束。"""
    handoff = packet.get("handoff") or {}
    stage = "initial"
    if handoff:
        step = next((s for s in (packet.get("current_plan") or {}).get("steps", []) if s["step_id"] == handoff.get("step_id")), {})
        stage = step.get("role", "build" if handoff.get("primary_components") else "recovery")
    context = bank.retrieve(build_system=task.build_system, family=family, stage=stage, text=json.dumps(packet, ensure_ascii=False), mode="structured")
    ledger.append("experience.retrieved", stage=stage, source_ids=context["sources"], bytes=context["bytes"], policy="once_per_agent_task", selection=context.get("policy"), abstained=not bool(context["sources"]))
    return copy.deepcopy(context)
