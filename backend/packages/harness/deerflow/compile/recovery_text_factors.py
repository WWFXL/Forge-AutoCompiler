"""恢复材料的可读、可逆文本因子；固定任务和原50k门禁保持。"""

from __future__ import annotations

import json
import re
from collections import Counter
from hashlib import sha256

from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.shared_text_packet import canonical, referenced_packet, restore_packet

FACTOR_TABLE = "forge_recovery_text_factors"
FACTOR_META = "forge_recovery_factor_encoding"
MARKER = re.compile(r"~(\d+)~")


def map_strings(value, transform):
    if isinstance(value, str):
        return transform(value)
    if isinstance(value, list):
        return [map_strings(child, transform) for child in value]
    if isinstance(value, dict):
        return {key: map_strings(child, transform) for key, child in value.items()}
    return value


def factor_packet(packet):
    """仅恢复时折叠重复子串，字典保存可读原文；不截断或编码为压缩二进制。"""
    if not packet.get("handoff"):
        return referenced_packet(packet)
    strings = []

    def collect(text):
        if MARKER.search(text):
            raise PlanContractError("恢复材料含保留文本因子标记")
        strings.append(text)
        return text

    def validate_keys(value):
        if isinstance(value, dict):
            if any(key in value for key in (FACTOR_TABLE, FACTOR_META)):
                raise PlanContractError("恢复材料含保留因子字段")
            for child in value.values():
                validate_keys(child)
        elif isinstance(value, list):
            for child in value:
                validate_keys(child)

    validate_keys(packet)
    encoded = referenced_packet(packet)
    map_strings(encoded, collect)
    factors = []
    # 只引用独立原文，不允许因子间递归；固定枚举顺序和计分确保表示确定。
    for index in range(128):
        counts = Counter()
        marker = f"~{index}~"
        for text in strings:
            for width in (96, 48, 24, 16):
                for start in range(len(text) - width + 1):
                    part = text[start : start + width]
                    if "~" not in part:
                        counts[part] += 1
        if not counts:
            break

        def upper(part):
            return (counts[part] - 1) * (len(part.encode()) - len(marker)) - len(part.encode()) - 20

        candidates = sorted(counts, key=upper, reverse=True)[:50]

        def saving(part):
            return sum(text.count(part) for text in strings) * (len(part.encode()) - len(marker)) - len(part.encode()) - 20

        best = max(candidates, key=saving)
        if saving(best) <= 0:
            break
        factors.append(best)
        strings = [text.replace(best, marker) for text in strings]
    iterator = iter(strings)
    result = map_strings(encoded, lambda _: next(iterator))
    result[FACTOR_TABLE] = factors
    result[FACTOR_META] = {
        "format": "forge-readable-text-factors-v1",
        "original_canonical_sha256": sha256(canonical(packet)).hexdigest(),
        "instruction": "字符串内~数字~表示forge_recovery_text_factors对应零起始索引的完整原文；先逐字展开因子，再展开forge_shared_texts。字典是可读原文，全部命令、测试、状态和失败不变。",
    }
    if restore_factor_packet(result) != packet:
        raise PlanContractError("恢复因子未保留完整材料")
    if len(json.dumps(result, ensure_ascii=False).encode()) >= len(json.dumps(encoded, ensure_ascii=False).encode()):
        return encoded
    return result


def restore_factor_packet(packet):
    """还原并核对完整原包；拒绝篡改、悬空、递归或含糊引用。"""
    if FACTOR_META not in packet:
        return restore_packet(packet)
    factors, meta = packet[FACTOR_TABLE], packet[FACTOR_META]
    if meta["format"] != "forge-readable-text-factors-v1" or not isinstance(factors, list) or len(factors) > 128 or any(not isinstance(value, str) or MARKER.search(value) for value in factors):
        raise PlanContractError("恢复因子表无效")

    def expand(text):
        def replace(match):
            index = int(match[1])
            if index >= len(factors):
                raise PlanContractError("恢复因子悬空")
            return factors[index]

        return MARKER.sub(replace, text)

    value = map_strings({key: value for key, value in packet.items() if key not in (FACTOR_TABLE, FACTOR_META)}, expand)
    result = restore_packet(value)
    if sha256(canonical(result)).hexdigest() != meta["original_canonical_sha256"]:
        raise PlanContractError("恢复因子完整原包身份不符")
    return result


class RecoveryFactorMixin:
    """复用相同meter和实际消息/schema门禁；正常起始请求表示不变。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        original = self.packet
        self.packet = lambda: factor_packet(original())
