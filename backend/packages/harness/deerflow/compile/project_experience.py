"""项目配方直接复用与面向当前状态/目标的历史经验选择。"""

from __future__ import annotations

import copy
import json
import re

from pydantic import BaseModel, ConfigDict

from deerflow.compile.build_experience import ExperienceBank, fingerprint, words
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.unified_plan_equivalent import BuildActions, assemble_plan


class ProjectRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    task: dict
    actions: BuildActions
    observed_validation: dict

    def match(self, task) -> str | None:
        """同源码/镜像/产物才能试用；目标变化显式标为试用，不能算精确命中。"""
        current = task.model_dump(mode="json")
        identity = ("repository_url", "commit_sha", "source_archive_sha256", "image_id", "build_system", "artifact_paths")
        if any(self.task[k] != current[k] for k in identity):
            return None
        return "exact" if self.task["verification_steps"] == current["verification_steps"] else "goal_changed_trial"

    def materialize(self, task):
        if self.match(task) is None:
            raise PlanContractError("配方源码、镜像或产物不匹配")
        return assemble_plan(task, self.actions, revision=1)


def verified_recipe(*, source_id, task, plan, validation):
    """由已验证最终方案提取命令；不请模型重写，也不把失败候选升级为配方。"""
    if not (validation.get("full_completed") and validation.get("source_unchanged") is True and validation.get("cleanup", {}).get("succeeded") and any(r.get("status") == "passed" for r in validation.get("replay", []))):
        raise PlanContractError("只有完整成功且源码保持、重放和清理成功才登记配方")
    actions = BuildActions(reason="复用已验证的阶段命令", steps=[s.model_dump() for s in plan.steps if s.role in ("dependency", "configure", "build")])
    recipe = ProjectRecipe(source_id=source_id, task=task.model_dump(mode="json"), actions=actions, observed_validation=copy.deepcopy(validation))
    if assemble_plan(task, actions, revision=plan.revision) != plan:
        raise PlanContractError("来源最终方案不符合共享测试/交付装配")
    return recipe


def recipe_planner(original, recipe: ProjectRecipe, *, allow_goal_trial=False):
    def planner(**kwargs):
        if kwargs.get("current_plan") is not None:
            return original(**kwargs)
        task, ledger = kwargs["task"], kwargs["meter"].ledger
        match = recipe.match(task)
        if match == "exact" or (match == "goal_changed_trial" and allow_goal_trial):
            plan = recipe.materialize(task)
            ledger.append("recipe.selected", source_id=recipe.source_id, match=match, recipe_sha256=fingerprint(recipe.model_dump(mode="json")), model_planning_skipped=True)
            ledger.save("plan-1.json", plan.model_dump(mode="json"))
            return plan, "直接执行历史配方；当前固定测试仍完整装配"
        ledger.append("recipe.abstained", match=match)
        return original(**kwargs)

    return planner


def domain_terms(text: str) -> set[str]:
    """保留构建标识与中文短语；不把哈希、来源编号当相似性证据。"""
    terms = words(text)
    for span in re.findall(r"[\u4e00-\u9fff]+", text):
        terms.update(span[i : i + 2] for i in range(len(span) - 1))
    return {t for t in terms if not re.fullmatch(r"[a-f0-9]{16,}", t)}


class StateTargetBank(ExperienceBank):
    """共享旧库及来源材料，仅改变排序/弃权；任务内快照由现有接口负责。"""

    def retrieve(self, *, build_system, family, stage, text, mode, limit_bytes=12000, top_k=3):
        if mode == "none":
            return super().retrieve(build_system=build_system, family=family, stage=stage, text=text, mode=mode, limit_bytes=limit_bytes, top_k=top_k)
        packet = json.loads(text)
        task, handoff = packet.get("task", {}), packet.get("handoff", {})
        # 不用源码身份、长固定验收脚本或未来日志制造词项重叠。
        target_text = json.dumps(
            dict(artifacts=task.get("artifact_paths", []), goals=[dict(expected=s.get("expected"), source=s.get("source"), required_output=s.get("required_output", [])) for s in task.get("verification_steps", [])]), ensure_ascii=False
        )
        goal_terms, failure_terms = domain_terms(target_text), domain_terms(json.dumps(handoff, ensure_ascii=False)) if handoff else set()
        stage = {"smoke": "verification", "artifact_stage": "delivery"}.get(stage, stage)
        ranked = []
        for source in self.sources.values():
            if source["family"] == family or source["build_system"] != build_system:
                continue
            entries = [e for e in self.entries if e["source_id"] == source["source_id"]]
            scores = []
            for entry in entries:
                if handoff and entry["stage"] != stage:
                    continue
                terms = domain_terms(json.dumps({k: entry[k] for k in ("conditions", "state", "action", "not_applicable")}, ensure_ascii=False))
                overlap = len(goal_terms & terms)
                error_overlap = len(failure_terms & terms)
                # 初始规划强调任务目标；恢复优先真实错误及同阶段证据。
                score = overlap + 3 * error_overlap
                if score:
                    scores.append(score)
            if scores:
                ranked.append((-max(scores), source["source_id"], source, entries))
        selected, size = [], 0
        for _, identifier, source, entries in sorted(ranked)[:top_k]:
            item = dict(source_id=identifier, source_family=source["family"], source_validation=source["observed_validation"], material=entries)
            length = len(json.dumps(item, ensure_ascii=False).encode())
            if size + length <= limit_bytes:
                selected.append(item)
                size += length
        return dict(mode=mode, sources=[s["source_id"] for s in selected], items=selected, bytes=size, maximum_bytes=limit_bytes, top_k=top_k)
