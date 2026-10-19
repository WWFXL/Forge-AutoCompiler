"""新实验专用的接管材料投影；权威状态和原始日志保持只读。"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256

from deerflow.compile.plan_agent_context import ContextCanaryMeter
from deerflow.compile.plan_workflow import PlanContractError


def project_handoff_packet(packet):
    """去掉状态内重复日志预览，保留身份、全部命令元数据与原日志哈希。"""
    result = deepcopy(packet)
    state_handoff = result.get("state", {}).get("handoff")
    active_handoff = result.get("handoff")
    if not state_handoff or not active_handoff:
        return result
    identity = ("handoff_id", "reason", "step_id", "plan_sha256", "command_frontier", "return_contract")
    if any(state_handoff.get(key) != active_handoff.get(key) for key in identity):
        raise PlanContractError("接管材料与权威状态身份不一致")
    # 顶层handoff仍携带执行器已有的最近三条预览，较早日志可按记录路径重读。
    # 不删除任何命令、预算、完成步骤、固定测试或方案，也不放宽原50k门禁。
    for record in state_handoff.get("recent_commands", []):
        if "output_tail" in record:
            raw = record.pop("output_tail").encode("utf-8")
            record["omitted_output_tail"] = {"utf8_bytes": len(raw), "sha256": sha256(raw).hexdigest(), "reason": "日志按log_path显式重读；顶层handoff保留近期预览"}
    return result


class HandoffContextMeter(ContextCanaryMeter):
    """复用原费用、请求、工具schema与消息大小门禁，只投影重复日志。"""

    def __init__(self, *args, packet, **kwargs):
        super().__init__(*args, packet=lambda: project_handoff_packet(packet()), **kwargs)
