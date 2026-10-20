"""重复长文本的可逆引用；原始任务、权威状态与50k门禁不变。"""

from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from hashlib import sha256

from deerflow.compile.plan_workflow import PlanContractError

REF = "__forge_shared_text_sha256__"
TABLE = "forge_shared_texts"
META = "forge_reference_encoding"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def referenced_packet(packet):
    """只合并完全相同的长字符串；每个原位置仍显式可恢复。"""
    counts = Counter()

    def scan(value):
        if isinstance(value, dict):
            if any(k in value for k in (REF, TABLE, META)):
                raise PlanContractError("状态材料与引用保留字段冲突")
            for child in value.values():
                scan(child)
        elif isinstance(value, list):
            for child in value:
                scan(child)
        elif isinstance(value, str) and len(value.encode()) >= 512:
            counts[value] += 1

    scan(packet)
    repeated = {v for v, n in counts.items() if n > 1}
    if not repeated:
        return deepcopy(packet)
    table = {}

    def encode(value):
        if isinstance(value, dict):
            return {k: encode(v) for k, v in value.items()}
        if isinstance(value, list):
            return [encode(v) for v in value]
        if isinstance(value, str) and value in repeated:
            key = sha256(value.encode()).hexdigest()
            if key in table and table[key] != value:
                raise PlanContractError("长文本哈希冲突")
            table[key] = value
            return {REF: key}
        return value

    result = encode(packet)
    result[TABLE] = table
    result[META] = {
        "format": "forge-shared-text-v1",
        "original_canonical_sha256": sha256(canonical(packet)).hexdigest(),
        "instruction": "任意仅含__forge_shared_text_sha256__的对象表示forge_shared_texts中该SHA对应的完整原字符串。引用是文本替换，不是缺失材料；固定任务、全部命令和状态字段保持原义。",
    }
    if len(json.dumps(result, ensure_ascii=False).encode()) >= len(json.dumps(packet, ensure_ascii=False).encode()):
        return deepcopy(packet)
    if restore_packet(result) != packet:
        raise PlanContractError("引用未完整保留权威材料")
    return result


def restore_packet(packet):
    """核验所有文本与完整原包哈希，拒绝悬空/篡改/含糊引用。"""
    if META not in packet:
        return deepcopy(packet)
    table, meta = packet[TABLE], packet[META]
    if meta["format"] != "forge-shared-text-v1" or any(not isinstance(v, str) or sha256(v.encode()).hexdigest() != k for k, v in table.items()):
        raise PlanContractError("共享文本身份不符")

    def decode(value):
        if isinstance(value, dict):
            if REF in value:
                if set(value) != {REF} or value[REF] not in table:
                    raise PlanContractError("悬空或含糊引用")
                return table[value[REF]]
            return {k: decode(v) for k, v in value.items()}
        if isinstance(value, list):
            return [decode(v) for v in value]
        return value

    result = decode({k: v for k, v in packet.items() if k not in (TABLE, META)})
    if sha256(canonical(result)).hexdigest() != meta["original_canonical_sha256"]:
        raise PlanContractError("恢复材料完整哈希不符")
    return result


class SharedTextPacketMixin:
    """在既有投影/证据工作集之后引用去重，沿用原计量与门禁。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        original_packet = self.packet
        self.packet = lambda: referenced_packet(original_packet())
