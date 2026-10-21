"""rtorrent 最新三策略共同入口与实际材料收据；不读取模型凭据。"""

from __future__ import annotations

import os
from unittest.mock import patch

import forge_build_rtorrent_arm as arm_module
from forge_build_full_strategy_runtime import StrategyMeter
from forge_build_full_strategy_runtime_v2 import QualificationAwareMeter
from forge_build_rtorrent_template_reset_gate_v2 import HostIdentityRuntime
from forge_build_unified_plan import METHODS

from deerflow.compile.generated_file_boundary import FileBoundary
from deerflow.compile.plan_agent_provenance import run_tool_agent_automatic
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.recovery_text_factors import factor_packet, restore_factor_packet
from deerflow.compile.staged_verification import boundary_tool_actions
from deerflow.compile.unified_plan_equivalent_observed import observed_planner


class MaterialReceiptMixin:
    """在原投影之后保存编码前/后原包；不改变消息大小或费用门禁。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        original = self.packet
        self.material_sequence = 0

        def packet():
            value = original()
            encoded = factor_packet(value)
            if restore_factor_packet(encoded) != value:
                raise PlanContractError("共同材料不能完整还原")
            self.material_sequence += 1
            self.ledger.save(f"material-{self.material_sequence}.json", dict(projected=value, encoded=encoded))
            return encoded

        self.packet = packet


class CommonQualificationMeter(MaterialReceiptMixin, QualificationAwareMeter):
    """仅工程脚本使用零费用时限；其他计量、请求和材料门禁保持。"""


class CommonStrategyMeter(MaterialReceiptMixin, StrategyMeter):
    """供后续独立真实身份绑定；不提供 Provider 构造或调用入口。"""


def run_strategy(*, method, item, protocol, root, model, meter_factory, qualification_reference=None, executor=None):
    """模型与资格参考由调用者显式传入；两 Workflow 使用同一恢复器。"""
    if method not in METHODS:
        raise PlanContractError("未知三策略方法")
    boundary = FileBoundary.model_validate(item["file_boundary"])
    planner = observed_planner("tool" if method == METHODS[0] else "model", generator=lambda task, source_root: boundary_tool_actions(task, source_root, boundary))
    with patch.object(arm_module, "CompileDockerRuntime", HostIdentityRuntime), patch.dict(os.environ, {"FORGE_HOST_UID": str(os.getuid()), "FORGE_HOST_GID": str(os.getgid())}):
        return (executor or arm_module.run_arm)(
            item=item,
            arm="tool" if method == METHODS[2] else "plan",
            protocol=protocol,
            root=root,
            model=model,
            reference=qualification_reference,
            meter_factory=meter_factory,
            planner=planner,
            tool_runner=run_tool_agent_automatic,
            command_timeout_seconds=1200,
            replay_timeout_seconds=1200,
        )
