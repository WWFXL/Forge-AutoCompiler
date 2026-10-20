"""重复命令/固定测试可逆引用，真实middleware仍拒绝超大唯一核心。"""

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_agent_context import propose_with_context
from deerflow.compile.plan_handoff_context import HandoffContextMeter
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.shared_text_packet import META, REF, TABLE, SharedTextPacketMixin, referenced_packet, restore_packet


def materials():
    command = "固定测试命令与原始多行日志\n" * 600
    return {
        "task": {"verification_steps": [{"command": command, "required_output": ["完整通过"]}]},
        "current_plan": {"steps": [{"command": command}]},
        "state": {"commands_used": 4, "completed": {"build": "id"}, "history": [{"command": command, "exit_code": 1, "timed_out": False}]},
        "source_packet": [],
        "remaining_budget": {"model_requests": 11},
    }


def test_large_unicode_repeated_task_command_history_roundtrip_without_mutation():
    original = materials()
    before = deepcopy(original)
    encoded = referenced_packet(original)
    assert original == before and restore_packet(encoded) == original
    assert len(json.dumps(encoded, ensure_ascii=False).encode()) < len(json.dumps(original, ensure_ascii=False).encode()) / 2
    assert len(encoded[TABLE]) == 1
    assert encoded["state"]["history"][0]["exit_code"] == 1
    assert encoded["remaining_budget"] == original["remaining_budget"]


def test_unique_values_are_preserved_without_wrapper_or_truncation():
    original = {"task": "唯一长文本" * 20000, "state": {"status": "failed"}}
    assert referenced_packet(original) == original and META not in referenced_packet(original)


@pytest.mark.parametrize("key", [REF, TABLE, META])
def test_existing_reserved_keys_cannot_be_confused_with_an_encoding(key):
    with pytest.raises(PlanContractError, match="保留字段"):
        referenced_packet({"state": {key: "untrusted"}})


@pytest.mark.parametrize("change", ["text", "dangling", "extra_ref_key", "core"])
def test_tampered_text_reference_or_authoritative_state_is_rejected(change):
    encoded = referenced_packet(materials())
    key = next(iter(encoded[TABLE]))
    if change == "text":
        encoded[TABLE][key] += "更改"
    elif change == "dangling":
        encoded["current_plan"]["steps"][0]["command"][REF] = "0" * 64
    elif change == "extra_ref_key":
        encoded["current_plan"]["steps"][0]["command"]["other"] = "ambiguous"
    else:
        encoded["state"]["commands_used"] = 0
    with pytest.raises(PlanContractError):
        restore_packet(encoded)


class ReferencedMeter(SharedTextPacketMixin, HandoffContextMeter):
    pass


def model_and_task():
    from test_plan_agent import ScriptedPlanModel, proposal, response
    from test_plan_agent import task as fixture

    task = fixture.__wrapped__()
    return ScriptedPlanModel(responses=[response("PlanProposal", proposal(task).model_dump(mode="json"))]), task


def test_actual_agent_middleware_can_send_reversible_repeated_core_with_zero_provider(tmp_path):
    model, task = model_and_task()
    packet = materials()
    packet.pop("remaining_budget")
    packet["task"]["identity"] = task.model_dump(mode="json")
    meter = ReferencedMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat(), packet=lambda: packet)
    propose_with_context(model=model, task=task, source_root=tmp_path, session_root=tmp_path, meter=meter)
    sent = json.loads((tmp_path / "agent/request-1.json").read_text())
    assert len(json.dumps({k: sent[k] for k in ("messages", "system_message")}, ensure_ascii=False).encode()) <= 50000
    payload = json.loads(sent["messages"][0]["content"])
    assert restore_packet({k: v for k, v in payload.items() if k not in ("recent_tool_results", "remaining_budget")})["task"] == packet["task"]
    assert meter.summary()["model_requests"] == 1


def test_same_middleware_still_rejects_oversized_unique_core_before_request(tmp_path):
    model, task = model_and_task()
    packet = {"task": task.model_dump(mode="json"), "state": {"unique": "不得截断核心" * 20000}, "source_packet": []}
    meter = ReferencedMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat(), packet=lambda: packet)
    with pytest.raises(PlanContractError, match="超过50000字节"):
        propose_with_context(model=model, task=task, source_root=tmp_path, session_root=tmp_path, meter=meter)
    assert meter.summary()["model_requests"] == 0 and not list((tmp_path / "agent").glob("request-*.json"))
