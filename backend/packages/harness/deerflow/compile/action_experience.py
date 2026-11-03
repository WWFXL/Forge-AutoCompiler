"""短动作经验和每次Agent任务的固定经验快照；动态状态继续逐轮更新。"""

from __future__ import annotations

import copy
import json

from pydantic import BaseModel, ConfigDict, Field

from deerflow.compile.build_experience import fingerprint, query_state
from deerflow.compile.conditioned_experience import ConditionedBank, ProcessExperience, validate_process_extraction


class ActionExperience(ProcessExperience):
    conditions: list[str] = Field(min_length=1, max_length=2)
    state: str = Field(min_length=1, max_length=160)
    action: str = Field(min_length=1, max_length=320)
    not_applicable: list[str] = Field(min_length=1, max_length=2)
    verification_scope: str = Field(min_length=1, max_length=160)
    failed_attempt: str | None = Field(max_length=160)
    feedback: str = Field(min_length=1, max_length=160)
    observed_revision: str | None = Field(max_length=240)
    check_before_action: list[str] = Field(min_length=1, max_length=2)
    expected_observation: str = Field(min_length=1, max_length=200)


class ActionExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    experiences: list[ActionExperience] = Field(max_length=2)


def validate_action_extraction(value: dict, trace: dict) -> list[dict]:
    """复用真实命令/过程绑定；短材料的语义适用性仍须在当前项目核对。"""
    result = []
    for entry in ActionExtraction.model_validate(value).experiences:
        item = entry.model_dump()
        extra = {key: item.pop(key) for key in ("check_before_action", "expected_observation")}
        bound = validate_process_extraction(dict(experiences=[item]), trace)[0]
        bound.update(extra)
        # 不截断命令、前提或证据；超限提炼作为被拒响应保留，不自动补提炼。
        if len(json.dumps(bound, ensure_ascii=False).encode()) > 3200:
            raise ValueError("单条动作经验超过3200字节")
        bound.pop("experience_id")
        bound["experience_id"] = fingerprint(bound)
        result.append(bound)
    return result


class ActionBank(ConditionedBank):
    def retrieve(self, **kwargs):
        return super().retrieve(**(kwargs | dict(top_k=2, limit_bytes=6000)))


class TaskExperience:
    """初始规划和每次恢复各选一次；空结果也缓存，不冻结执行反馈。"""

    def __init__(self, *, task, family, bank, mode, ledger):
        self.task, self.family, self.bank = task, family, bank
        self.mode, self.ledger = mode, ledger
        self.episode = 0
        self.snapshot = None
        self.bank_sha256 = fingerprint(dict(sources=list(bank.sources), entries=bank.entries))

    def begin(self, packet):
        state = query_state(self.task, packet)
        self.episode += 1
        context = self.bank.retrieve(build_system=self.task.build_system, family=self.family, stage=state["stage"], text=state["text"], mode=self.mode)
        self.snapshot = copy.deepcopy(context)
        self.context_sha256 = fingerprint(context)
        self.ledger.append("experience.task_selected", episode=self.episode, stage=state["stage"], mode=self.mode, source_ids=context["sources"], bytes=context["bytes"], bank_sha256=self.bank_sha256, context_sha256=self.context_sha256)

    def attach(self, packet):
        if self.snapshot is None:
            raise RuntimeError("必须先开始规划或恢复任务，才能使用经验快照")
        return {**packet, "historical_build_experience": copy.deepcopy(self.snapshot)}

    def used(self, request_sequence):
        self.ledger.append("experience.context_used", episode=self.episode, request_sequence=request_sequence, context_sha256=self.context_sha256, bytes=self.snapshot["bytes"])
