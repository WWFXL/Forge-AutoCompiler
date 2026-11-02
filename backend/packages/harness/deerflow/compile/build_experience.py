"""构建领域的条件化经验；建议影响规划，不替代实际执行与验收。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Experience(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conditions: list[str] = Field(min_length=1, max_length=8)
    stage: Literal["dependency", "configure", "build", "verification", "delivery"]
    state: str = Field(min_length=1, max_length=1600)
    action: str = Field(min_length=1, max_length=2400)
    outcome: Literal["effective", "ineffective", "hypothesis"]
    not_applicable: list[str] = Field(min_length=1, max_length=6)
    command_ids: list[str] = Field(min_length=1, max_length=12)
    verification_scope: str = Field(min_length=1, max_length=1600)


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    experiences: list[Experience] = Field(max_length=3)


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z0-9_+.-]{2,}", text.lower()))


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_extraction(value: dict, trace: dict) -> list[dict]:
    """绑定实际命令；完整验收的标签由程序给出，模型不能自行升级。"""
    parsed = Extraction.model_validate(value)
    commands = {row["command_id"]: row for row in trace["commands"]}
    result = []
    for entry in parsed.experiences:
        if not set(entry.command_ids).issubset(commands):
            raise ValueError("经验引用了来源中不存在的命令")
        if entry.outcome == "effective" and not any(commands[c]["exit_code"] == 0 and not commands[c].get("timed_out") for c in entry.command_ids):
            raise ValueError("有效动作必须至少有实际成功命令，且不等于任务完整通过")
        item = {**entry.model_dump(), "source_id": trace["source_id"], "source_family": trace["family"], "build_system": trace["build_system"], "observed_validation": trace["observed_validation"]}
        item["experience_id"] = fingerprint(item)
        if item["experience_id"] not in {r["experience_id"] for r in result}:
            result.append(item)
    return result


def query_state(task, packet: dict) -> dict:
    """初始阶段不读取未来日志；恢复阶段仅消费当前真实交接。"""
    handoff = packet.get("handoff") or packet.get("execution_handoff") or {}
    current = packet.get("current_plan")
    stage = "initial"
    if handoff:
        stage = handoff.get("role") or handoff.get("stage") or "recovery"
        if isinstance(current, dict):
            step = next((s for s in current.get("steps", []) if s.get("step_id") == handoff.get("step_id")), {})
            stage = step.get("role", stage)
    return dict(build_system=task.build_system, stage=stage, text=json.dumps(dict(task=task.model_dump(mode="json"), handoff=handoff), ensure_ascii=False))


class ExperienceBank:
    def __init__(self, sources: list[dict], entries: list[dict]):
        self.sources = {s["source_id"]: s for s in sources}
        self.entries = entries

    @classmethod
    def load(cls, path: Path):
        value = json.loads(path.read_text())
        return cls(value["sources"], value["entries"])

    def retrieve(self, *, build_system: str, family: str, stage: str, text: str, mode: str, limit_bytes: int = 12000, top_k: int = 3) -> dict:
        if mode not in ("none", "raw", "structured"):
            raise ValueError("未知经验处理")
        if mode == "none":
            return dict(mode=mode, sources=[], items=[], bytes=0)
        query = words(text)
        ranked = []
        for source in self.sources.values():
            if source["family"] == family or source["build_system"] != build_system:
                continue
            # 两处理共用原材料索引；结构化组不使用更有利的额外搜索器。
            terms = words(source["retrieval_text"])
            stages = {c.get("role") for c in source["commands"]}
            score = len(query & terms) / max(1, len(query)) + (1 if stage in stages else 0)
            ranked.append((-score, source["source_id"], source))
        selected, selected_sources, size = [], [], 0
        for _, identifier, source in sorted(ranked)[:top_k]:
            material = source["raw_context"] if mode == "raw" else [e for e in self.entries if e["source_id"] == identifier]
            if not material:
                continue
            item = dict(source_id=identifier, source_family=source["family"], source_validation=source["observed_validation"], material=material)
            length = len(json.dumps(item, ensure_ascii=False).encode())
            # 不截断命令或JSON；两个处理采用相同总字节上限，记录实际额度。
            if size + length > limit_bytes:
                continue
            selected.append(item)
            selected_sources.append(identifier)
            size += length
        return dict(mode=mode, sources=selected_sources, items=selected, bytes=size, maximum_bytes=limit_bytes, top_k=top_k)


EXPERIENCE_PROMPT = """
historical_build_experience为其他项目的历史材料，仅是条件化建议。必须核对当前源码、版本、依赖和目标；
旧项目名、选项和机器路径不可照搬。outcome=effective只表示来源命令的局部观察，不保证当前项目或全部验收成功。
ineffective为已知无效尝试，hypothesis尚未验证。经验不得覆盖真实失败、原测试、交付、源码保护或重放要求。
没有适用经验时按当前证据正常规划/恢复；不能为了遵从经验而凭空添加依赖或强设HAVE_*变量。
"""
