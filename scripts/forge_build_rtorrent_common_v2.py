"""所有阶段共同使用可读可逆因子；旧恢复专用编码与失败证据不改。"""

from __future__ import annotations

import json
from collections import Counter
from hashlib import sha256

from forge_build_full_strategy_runtime import StrategyMeter
from forge_build_full_strategy_runtime_v2 import QualificationAwareMeter
from forge_build_rtorrent_common import run_strategy  # noqa: F401

from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.recovery_text_factors import FACTOR_META, FACTOR_TABLE, MARKER, map_strings, restore_factor_packet
from deerflow.compile.shared_text_packet import canonical, referenced_packet


def factor_common_packet(packet):
    """沿用原算法/格式，但不要求handoff；不添加虚构状态或删除原字段。"""

    def validate_keys(value):
        if isinstance(value, dict):
            if any(k in value for k in (FACTOR_TABLE, FACTOR_META)):
                raise PlanContractError("共同材料含保留因子字段")
            for v in value.values():
                validate_keys(v)
        elif isinstance(value, list):
            for v in value:
                validate_keys(v)

    validate_keys(packet)
    encoded = referenced_packet(packet)
    strings = []

    def collect(text):
        if MARKER.search(text):
            raise PlanContractError("共同材料含保留因子标记")
        strings.append(text)
        return text

    map_strings(encoded, collect)
    factors = []
    for index in range(128):
        marker, counts = f"~{index}~", Counter()
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

        def saving(part):
            return sum(text.count(part) for text in strings) * (len(part.encode()) - len(marker)) - len(part.encode()) - 20

        best = max(sorted(counts, key=upper, reverse=True)[:50], key=saving)
        if saving(best) <= 0:
            break
        factors.append(best)
        strings = [text.replace(best, marker) for text in strings]
    iterator = iter(strings)
    result = map_strings(encoded, lambda _: next(iterator))
    result[FACTOR_TABLE] = factors
    result[FACTOR_META] = dict(
        format="forge-readable-text-factors-v1",
        original_canonical_sha256=sha256(canonical(packet)).hexdigest(),
        instruction="字符串内~数字~表示forge_recovery_text_factors对应零起始索引的完整原文；先逐字展开因子，再展开forge_shared_texts。全部任务、命令、测试及实际状态保持。",
    )
    if restore_factor_packet(result) != packet:
        raise PlanContractError("共同因子不能还原完整原包")
    return result if len(json.dumps(result, ensure_ascii=False).encode()) < len(json.dumps(encoded, ensure_ascii=False).encode()) else encoded


class CommonMaterialV2Mixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        original = self.packet
        self.material_sequence = 0

        def packet():
            value = original()
            encoded = factor_common_packet(value)
            self.material_sequence += 1
            self.ledger.save(f"material-{self.material_sequence}.json", dict(projected=value, encoded=encoded))
            return encoded

        self.packet = packet


class CommonQualificationMeterV2(CommonMaterialV2Mixin, QualificationAwareMeter):
    """零Provider脚本资格；原限额保持。"""


class CommonStrategyMeterV2(CommonMaterialV2Mixin, StrategyMeter):
    """真实三策略同一编码和完整计量；本类本身不读取凭据。"""
