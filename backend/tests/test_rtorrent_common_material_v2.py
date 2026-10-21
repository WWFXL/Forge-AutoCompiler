"""初始和恢复包的共同编码、篡改拒绝与实际初始失败回归。"""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_rtorrent_common_v2 import factor_common_packet  # noqa: E402

from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402
from deerflow.compile.recovery_text_factors import restore_factor_packet  # noqa: E402


@pytest.mark.parametrize("handoff", [None, {"reason": "real_failure"}])
def test_common_encoding_keeps_phase_and_every_original_value(handoff):
    text = "保留完整任务、测试、日志及动作。" * 40
    packet = dict(task={"tests": text}, current_plan={"tests": text}, state={"command": "x" * 4000}, handoff=handoff)
    original = copy.deepcopy(packet)
    encoded = factor_common_packet(packet)
    assert packet == original and restore_factor_packet(encoded) == original
    assert restore_factor_packet(encoded)["handoff"] == handoff
    changed = copy.deepcopy(encoded)
    changed["state"]["command"] += "改动"
    with pytest.raises(PlanContractError):
        restore_factor_packet(changed)


def test_short_packet_is_not_inflated_and_reserved_markers_rejected():
    value = dict(task="brief", handoff=None)
    assert factor_common_packet(value) == value
    with pytest.raises(PlanContractError):
        factor_common_packet({"task": "~1~"})
    with pytest.raises(PlanContractError):
        factor_common_packet({"task": {"forge_recovery_text_factors": []}})
