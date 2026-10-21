"""多轮材料的完整JSON值共享；只修复表示，不改变任务与资源。"""

from __future__ import annotations

import copy
import json
from collections import Counter
from hashlib import sha256

from forge_build_rtorrent_canary_v2 import AuthorizedMeter
from forge_build_rtorrent_common_v2 import factor_common_packet

from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.recovery_text_factors import restore_factor_packet
from deerflow.compile.shared_text_packet import canonical

REF = "__forge_shared_value_sha256__"
TABLE = "forge_shared_values"
META = "forge_value_reference_encoding"
FORMAT = "forge-shared-json-value-v1"


def share_values(packet):
    """共享完全相同且至少256字节的对象/列表，表内保留完整原值。"""
    counts = Counter()

    def scan(value):
        if isinstance(value, (dict, list)):
            if isinstance(value, dict) and any(k in value for k in (REF, TABLE, META)):
                raise PlanContractError("JSON值共享保留字段冲突")
            key = canonical(value)
            if len(key) >= 256:
                counts[key] += 1
            for child in value.values() if isinstance(value, dict) else value:
                scan(child)

    scan(packet)
    table = {}

    def encode(value, *, top=False):
        if isinstance(value, (dict, list)):
            key = canonical(value)
            if not top and len(key) >= 256 and counts[key] > 1:
                digest = sha256(key).hexdigest()
                if digest in table and canonical(table[digest]) != key:
                    raise PlanContractError("JSON值哈希冲突")
                table[digest] = copy.deepcopy(value)
                return {REF: digest}
            return {k: encode(v) for k, v in value.items()} if isinstance(value, dict) else [encode(v) for v in value]
        return value

    result = encode(packet, top=True)
    if not table:
        return copy.deepcopy(packet)
    result[TABLE] = table
    result[META] = dict(
        format=FORMAT,
        original_canonical_sha256=sha256(canonical(packet)).hexdigest(),
        instruction="仅含__forge_shared_value_sha256__的对象表示forge_shared_values中同SHA的完整JSON值；先展开原文字典，再替换这些对象。全部任务、测试及状态保持。",
    )
    if restore_values(result) != packet:
        raise PlanContractError("JSON共享值未完整还原")
    return result if len(json.dumps(result, ensure_ascii=False).encode()) < len(json.dumps(packet, ensure_ascii=False).encode()) else copy.deepcopy(packet)


def restore_values(packet):
    """核验表和完整原包指纹，拒绝篡改、悬空、含糊及嵌套引用。"""
    if META not in packet:
        if TABLE in packet or REF in packet:
            raise PlanContractError("JSON共享值缺失编码元数据")
        return copy.deepcopy(packet)
    table, meta = packet.get(TABLE), packet[META]
    if not isinstance(table, dict) or not isinstance(meta, dict) or meta.get("format") != FORMAT:
        raise PlanContractError("JSON共享值格式错误")

    def reserved(value):
        if isinstance(value, dict):
            return any(k in value for k in (REF, TABLE, META)) or any(reserved(v) for v in value.values())
        return isinstance(value, list) and any(reserved(v) for v in value)

    for digest, value in table.items():
        if not isinstance(value, (dict, list)) or reserved(value) or sha256(canonical(value)).hexdigest() != digest:
            raise PlanContractError("JSON共享值表身份错误")

    def expand(value):
        if isinstance(value, dict):
            if REF in value:
                if set(value) != {REF} or not isinstance(value[REF], str) or value[REF] not in table:
                    raise PlanContractError("悬空或含糊JSON共享值引用")
                return copy.deepcopy(table[value[REF]])
            if any(k in value for k in (TABLE, META)):
                raise PlanContractError("嵌套JSON共享值元数据")
            return {k: expand(v) for k, v in value.items()}
        return [expand(v) for v in value] if isinstance(value, list) else value

    result = expand({k: v for k, v in packet.items() if k not in (TABLE, META)})
    if sha256(canonical(result)).hexdigest() != meta.get("original_canonical_sha256"):
        raise PlanContractError("JSON共享值完整材料哈希错误")
    return result


def encode_packet(packet):
    """先值共享再原文本因子；无收益时保留原文本表示。"""
    old = factor_common_packet(packet)
    shared = share_values(packet)
    if shared == packet:
        return old
    new = factor_common_packet(shared)
    if restore_values(restore_factor_packet(new)) != packet:
        raise PlanContractError("组合表示不能还原完整材料")
    return new if len(json.dumps(new, ensure_ascii=False).encode()) < len(json.dumps(old, ensure_ascii=False).encode()) else old


class SharedValueMeter(AuthorizedMeter):
    """沿用真实middleware、工作集和原50k/8k/费用门禁。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        original = self.packet
        self.shared_material_sequence = 0

        def packet():
            old = original()
            projected = restore_factor_packet(old)
            encoded = encode_packet(projected)
            self.shared_material_sequence += 1
            self.ledger.save(f"shared-material-{self.shared_material_sequence}.json", dict(projected=projected, encoded=encoded))
            return encoded

        self.packet = packet
