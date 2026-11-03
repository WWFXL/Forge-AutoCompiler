"""失败过程提炼与逐条条件选择；不把检索命中当作实际采用。"""

from __future__ import annotations

import json
import tarfile
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field

from deerflow.compile.build_experience import Experience, ExperienceBank, fingerprint, words


class Applicability(BaseModel):
    model_config = ConfigDict(extra="forbid")
    required_files: list[str] = Field(max_length=5)
    declaration_terms: list[str] = Field(max_length=5)
    error_markers: list[str] = Field(max_length=5)


class ProcessExperience(Experience):
    command_ids: list[str] = Field(max_length=12)
    evidence_ids: list[str] = Field(min_length=1, max_length=12)
    failed_attempt: str | None = Field(max_length=1200)
    feedback: str = Field(min_length=1, max_length=1200)
    observed_revision: str | None = Field(max_length=1600)
    applicability: Applicability


class ProcessExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    experiences: list[ProcessExperience] = Field(max_length=2)


def validate_process_extraction(value: dict, trace: dict) -> list[dict]:
    parsed = ProcessExtraction.model_validate(value)
    commands = {row["command_id"]: row for row in trace["commands"]}
    evidence = set(commands) | {o["evidence_id"] for o in trace["process_observations"]}
    result = []
    for entry in parsed.experiences:
        if not set(entry.command_ids) <= commands.keys() or not set(entry.evidence_ids) <= evidence:
            raise ValueError("经验引用了来源中不存在的命令或过程证据")
        if entry.outcome == "effective" and not any(commands[c]["exit_code"] == 0 and not commands[c].get("timed_out") for c in entry.command_ids):
            raise ValueError("有效动作必须有实际成功命令；不等于整个任务成功")
        item = entry.model_dump() | dict(source_id=trace["source_id"], source_family=trace["family"], build_system=trace["build_system"], observed_validation=trace["observed_validation"])
        item["experience_id"] = fingerprint(item)
        result.append(item)
    return result


def archive_facts(path: str) -> dict:
    """只读固定归档；缺少声明命中记为未确认，不推断项目不存在该能力。"""
    files, declarations = [], []
    names = {"CMakeLists.txt", "Makefile", "Makefile.am", "configure.ac", "configure.in", "meson.build"}
    with tarfile.open(path) as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            name = PurePosixPath(member.name).name
            files.append(name)
            if (name in names or name.endswith(".cmake")) and member.size <= 256000:
                stream = archive.extractfile(member)
                if stream is not None:
                    declarations.append(dict(path=member.name, text=stream.read().decode(errors="replace")))
    return dict(files=sorted(set(files)), declarations=declarations, scope="frozen_archive_build_declarations_only")


class ConditionedBank(ExperienceBank):
    def __init__(self, sources, entries, facts, record_path: Path | None = None):
        super().__init__(sources, entries)
        self.facts, self.record_path = facts, record_path

    def retrieve(self, *, build_system, family, stage, text, mode, limit_bytes=12000, top_k=3):
        if mode == "none":
            return super().retrieve(build_system=build_system, family=family, stage=stage, text=text, mode=mode)
        facts = self.facts[family]
        declarations = "\n".join(d["text"] for d in facts["declarations"]).lower()
        packet = json.loads(text)
        handoff = json.dumps(packet.get("handoff") or {}, ensure_ascii=False).lower()
        query = words(text)
        stage_alias = {"smoke": "verification", "artifact_stage": "delivery"}.get(stage, stage)
        ranked, decisions = [], []
        for entry in self.entries:
            if entry["source_family"] == family or entry["build_system"] != build_system:
                continue
            conditions = entry["applicability"]
            checks = [dict(kind="file", value=f, status="confirmed" if f in facts["files"] else "absent") for f in conditions["required_files"]]
            checks += [dict(kind="declaration", value=t, status="confirmed" if t.lower() in declarations else "unconfirmed") for t in conditions["declaration_terms"]]
            markers = conditions["error_markers"]
            if markers:
                checks.append(dict(kind="current_error", value=markers, status="confirmed" if handoff != "{}" and any(m.lower() in handoff for m in markers) else "unconfirmed"))
            reasons = []
            if any(c["status"] != "confirmed" for c in checks):
                reasons.append("required_signal_not_confirmed")
            if stage_alias not in ("initial", "recovery", entry["stage"]):
                reasons.append("different_stage")
            overlap = query & words(" ".join([entry["state"], entry["action"], *entry["conditions"]]))
            if not checks and len(overlap) < 2:
                reasons.append("weak_relevance")
            score = len(overlap) + 3 * sum(c["status"] == "confirmed" for c in checks)
            decision = dict(experience_id=entry["experience_id"], source_id=entry["source_id"], checks=checks, score=score, excluded_reasons=reasons, selected=False)
            decisions.append(decision)
            if not reasons:
                ranked.append((-score, entry["experience_id"], entry, decision))
        selected, size = [], 0
        for _, _, entry, decision in sorted(ranked):
            if len(selected) >= top_k:
                break
            # 每条独立装配，完整保留动作与证据；不附加同来源的其他经验。
            material = {k: v for k, v in entry.items() if k not in {"observed_validation", "source_family", "build_system"}}
            item = dict(
                source_id=entry["source_id"],
                source_family=entry["source_family"],
                source_validation=entry["observed_validation"],
                material=[material],
                applicability_checks=decision["checks"],
                remaining_conditions="自然语言条件和版本仍须Agent核对；静态信号不证明动作适用或因果",
            )
            length = len(json.dumps(item, ensure_ascii=False).encode())
            if size + length > limit_bytes:
                decision["excluded_reasons"].append("context_budget")
                continue
            selected.append(item)
            size += length
            decision["selected"] = True
        result = dict(mode=mode, sources=sorted({s["source_id"] for s in selected}), items=selected, bytes=size, maximum_bytes=limit_bytes, top_k=top_k)
        if self.record_path:
            with self.record_path.open("a") as file:
                file.write(json.dumps(dict(stage=stage, query_sha256=fingerprint(packet), decisions=decisions, selected_ids=[d["experience_id"] for d in decisions if d["selected"]], bytes=size), ensure_ascii=False) + "\n")
        return result
