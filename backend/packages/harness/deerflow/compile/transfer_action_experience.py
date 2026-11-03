"""跨项目动作候选：通用声明作相关性门槛，来源专名保留为待核对实例。"""

from __future__ import annotations

import copy
import json
import re

from deerflow.compile.action_experience import ActionBank
from deerflow.compile.build_experience import fingerprint, words

BUILD_INPUTS = {"CMakeLists.txt", "Makefile", "makefile", "GNUmakefile", "Makefile.am", "configure.ac", "configure.in"}
CMAKE_COMMANDS = {"check_library_exists", "add_test", "add_subdirectory", "add_library", "find_package", "install"}
MAKE_TARGETS = {"all", "check", "clean", "test"}


def transfer_signals(entry, facts):
    """只抽取语言结构；不把来源选项、符号或目标名断言为当前项目事实。"""
    declarations = "\n".join(d["text"] for d in facts["declarations"])
    checks, examples = [], []
    for name in entry["applicability"]["required_files"]:
        if name in BUILD_INPUTS:
            checks.append(dict(kind="build_input", value=name, confirmed=name in facts["files"]))
        else:
            examples.append(dict(kind="source_file", value=name))
    for term in entry["applicability"]["declaration_terms"]:
        command = term.split("(", 1)[0].lower()
        if command in CMAKE_COMMANDS:
            pattern = r"\b" + re.escape(command) + r"\s*\("
            checks.append(dict(kind="cmake_command", value=command, confirmed=bool(re.search(pattern, declarations, re.I))))
        elif term.lower() == "fetchcontent":
            checks.append(dict(kind="cmake_module", value="FetchContent", confirmed="fetchcontent" in declarations.lower()))
        elif entry["build_system"] == "make" and term.rstrip(":") in MAKE_TARGETS:
            target = term.rstrip(":")
            checks.append(dict(kind="make_target", value=target, confirmed=bool(re.search(r"(?m)^" + re.escape(target) + r"\s*:", declarations))))
        # 即使提取了函数结构，其完整参数仍只是来源实例，不宣称已确认。
        examples.append(dict(kind="source_declaration", value=term))
    return checks, examples


class TransferActionBank(ActionBank):
    def retrieve(self, *, build_system, family, stage, text, mode, **kwargs):
        if mode == "none":
            return super().retrieve(build_system=build_system, family=family, stage=stage, text=text, mode=mode)
        packet = json.loads(text)
        handoff = json.dumps(packet.get("handoff") or {}, ensure_ascii=False).lower()
        stage_alias = {"smoke": "verification", "artifact_stage": "delivery"}.get(stage, stage)
        ranked, decisions = [], []
        for entry in self.entries:
            if entry["source_family"] == family or entry["build_system"] != build_system:
                continue
            checks, examples = transfer_signals(entry, self.facts[family])
            markers = entry["applicability"]["error_markers"]
            if markers:
                checks.append(dict(kind="current_error", value=markers, confirmed=handoff != "{}" and any(m.lower() in handoff for m in markers)))
            reasons = []
            if not checks or not all(c["confirmed"] for c in checks):
                reasons.append("transfer_signal_not_confirmed")
            if stage_alias not in ("initial", "recovery", entry["stage"]):
                reasons.append("different_stage")
            overlap = words(text) & words(" ".join([entry["state"], entry["action"], *entry["conditions"]]))
            score = 3 * sum(c["confirmed"] for c in checks) + len(overlap)
            decision = dict(experience_id=entry["experience_id"], source_id=entry["source_id"], checks=checks, source_examples=examples, score=score, excluded_reasons=reasons, selected=False)
            decisions.append(decision)
            if not reasons:
                ranked.append((-score, entry["experience_id"], entry, decision))
        selected, size = [], 0
        for _, _, entry, decision in sorted(ranked):
            if len(selected) == 2:
                break
            material = copy.deepcopy({k: v for k, v in entry.items() if k not in {"observed_validation", "source_family", "build_system"}})
            material["source_applicability_examples"] = material.pop("applicability")
            item = dict(
                source_id=entry["source_id"],
                source_family=entry["source_family"],
                source_validation=entry["observed_validation"],
                material=[material],
                applicability_checks=decision["checks"],
                remaining_conditions="仅为可迁移候选，尚未证明适用。来源专名/路径/选项均为实例；依据当前源码核对自然语言前提并实例化动作，不得照搬或改变任务要求。核对不满足就忽略，优先复用已有证据。",
            )
            length = len(json.dumps(item, ensure_ascii=False).encode())
            if size + length > 6000:
                decision["excluded_reasons"].append("context_budget")
                continue
            selected.append(item)
            size += length
            decision["selected"] = True
        result = dict(mode=mode, sources=sorted({s["source_id"] for s in selected}), items=selected, bytes=size, maximum_bytes=6000, top_k=2)
        if self.record_path:
            with self.record_path.open("a") as file:
                file.write(json.dumps(dict(stage=stage, query_sha256=fingerprint(packet), decisions=decisions, selected_ids=[d["experience_id"] for d in decisions if d["selected"]], bytes=size), ensure_ascii=False) + "\n")
        return result
