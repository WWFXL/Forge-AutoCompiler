"""恢复因子完整性、固定任务保持与共同meter真实准入回归。"""

import json
from copy import deepcopy

import pytest

from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.recovery_text_factors import FACTOR_TABLE, factor_packet, restore_factor_packet
from deerflow.compile.shared_text_packet import referenced_packet


def packet():
    command = 'python3 -c "' + ", ".join(f"original_suite::original_test_{index}" for index in range(80)) + '"'
    return {"task": {"tests": command}, "current_plan": {"tests": command}, "handoff": {"failed": True, "command": "false"}, "state": {"status": "needs_handoff"}}


def test_readable_factors_roundtrip_preserves_every_test_and_failure_without_mutation():
    original = packet()
    before = deepcopy(original)
    encoded = factor_packet(original)
    assert encoded[FACTOR_TABLE]
    assert original == before and restore_factor_packet(encoded) == before
    assert len(json.dumps(encoded)) < len(json.dumps(original))
    assert all(isinstance(text, str) for text in encoded[FACTOR_TABLE])


@pytest.mark.parametrize("kind", ["factor", "state", "dangling"])
def test_corrupt_material_is_rejected(kind):
    encoded = factor_packet(packet())
    if kind == "factor":
        encoded[FACTOR_TABLE][0] += "changed"
    elif kind == "state":
        encoded["state"]["status"] = "passed"
    else:
        encoded["state"]["status"] = "~9999~"
    with pytest.raises(PlanContractError):
        restore_factor_packet(encoded)


def test_normal_request_representation_is_exactly_unchanged():
    original = packet()
    original["handoff"] = None
    assert factor_packet(original) == referenced_packet(original)


@pytest.mark.parametrize("value", [{"handoff": {"value": "~0~"}}, {"handoff": {}, FACTOR_TABLE: []}])
def test_reserved_reference_cannot_be_injected(value):
    if not value["handoff"]:
        value["handoff"] = {"failed": True}
    with pytest.raises(PlanContractError):
        factor_packet(value)


def test_actual_meter_keeps_original_limits_and_restores_fixed_task(tmp_path):
    from datetime import UTC, datetime, timedelta

    from forge_build_rtorrent_recovery_meter import RecoveryQualificationMeter
    from test_shared_text_packet import model_and_task

    from deerflow.compile.plan_agent import PlanAgentLedger
    from deerflow.compile.plan_agent_context import propose_with_context

    model, task = model_and_task()
    original = packet()
    original["task"]["fixed_identity"] = task.model_dump(mode="json")
    meter = RecoveryQualificationMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat(), packet=lambda: original)
    propose_with_context(model=model, task=task, source_root=tmp_path, session_root=tmp_path, meter=meter)
    sent = json.loads((tmp_path / "agent/request-1.json").read_text())
    assert len(json.dumps({key: sent[key] for key in ("messages", "system_message")}, ensure_ascii=False).encode()) <= 50000
    assert len(json.dumps(sent["tools"], ensure_ascii=False).encode()) <= 8000
    payload = json.loads(sent["messages"][0]["content"])
    restored = restore_factor_packet({key: value for key, value in payload.items() if key not in ("recent_tool_results", "remaining_budget")})
    assert restored["task"] == original["task"] and restored["handoff"] == original["handoff"]
    assert meter.summary()["model_requests"] == 1
