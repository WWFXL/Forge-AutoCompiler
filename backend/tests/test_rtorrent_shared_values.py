"""共享完整JSON值的可逆性、损坏拒绝及真实多轮middleware接线。"""

import copy
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_plan_agent import ScriptedPlanModel, proposal, response
from test_plan_agent import task as original_task

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_rtorrent_shared_values import META, REF, TABLE, SharedValueMeter, encode_packet, restore_values, share_values  # noqa: E402

from deerflow.compile.plan_agent import PlanAgentLedger  # noqa: E402
from deerflow.compile.plan_agent_context import propose_with_context  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402
from deerflow.compile.recovery_text_factors import restore_factor_packet  # noqa: E402


def sample():
    row = {"tests": [{"id": f"test-{i}", "command": "execute_original_author_test", "expected": i} for i in range(25)]}
    return {"task": copy.deepcopy(row), "current_plan": copy.deepcopy(row), "state": copy.deepcopy(row), "source_packet": []}


def test_nested_values_roundtrip_keeps_every_field_and_input():
    packet = sample()
    original = copy.deepcopy(packet)
    encoded = share_values(packet)
    assert TABLE in encoded and packet == original
    assert restore_values(encoded) == original
    assert restore_values(restore_factor_packet(encode_packet(packet))) == original
    assert len(json.dumps(encoded).encode()) < len(json.dumps(packet).encode())


@pytest.mark.parametrize("fault", ["value", "dangling", "ambiguous", "metadata", "digest", "nested", "missing_meta"])
def test_corruption_is_rejected(fault):
    encoded = share_values(sample())
    key = next(iter(encoded[TABLE]))
    if fault == "value":
        encoded[TABLE][key]["changed"] = True
    elif fault == "dangling":
        encoded["task"] = {REF: "0" * 64}
    elif fault == "ambiguous":
        encoded["task"]["extra"] = True
    elif fault == "metadata":
        encoded[META]["format"] = "unknown"
    elif fault == "digest":
        encoded[META]["original_canonical_sha256"] = "0" * 64
    elif fault == "nested":
        encoded[TABLE][key] = {REF: key}
    else:
        del encoded[META]
    with pytest.raises(PlanContractError):
        restore_values(encoded)


@pytest.mark.parametrize("key", [REF, TABLE, META])
def test_reserved_keys_rejected_even_in_nested_list(key):
    with pytest.raises(PlanContractError):
        share_values({"nested": [{key: "collision"}]})


def test_small_or_unprofitable_packet_unchanged():
    small = {"a": [1, 2], "b": [1, 2]}
    assert share_values(small) == small
    assert encode_packet(small) == small


def test_real_multiturn_graph_preserves_read_feedback_and_budget(tmp_path):
    task = original_task.__wrapped__()
    (tmp_path / "README.md").write_text("REAL-READ-EVIDENCE")
    packet = {**sample(), "task": task.model_dump(mode="json")}
    model = ScriptedPlanModel(responses=[response("read_source", {"path": "README.md"}), response("PlanProposal", proposal(task).model_dump(mode="json"))])
    meter = SharedValueMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline=(datetime.now(UTC) + timedelta(hours=3)).isoformat(), packet=lambda: packet)
    plan, _ = propose_with_context(model=model, task=task, source_root=tmp_path, session_root=tmp_path, meter=meter)
    assert plan and meter.summary()["model_requests"] == 2 and meter.summary()["tool_calls"] == 1
    actual = json.loads((tmp_path / "agent/request-2.json").read_text())
    payload = json.loads(actual["messages"][0]["content"])
    plain = restore_values(restore_factor_packet({k: v for k, v in payload.items() if k not in ("remaining_budget", "recent_tool_results")}))
    assert plain["task"] == task.model_dump(mode="json")
    assert "REAL-READ-EVIDENCE" in json.dumps(plain["source_packet"])
    assert payload["remaining_budget"]["model_requests"] == 72
    assert meter.tracker.limits.max_recorded_tokens == 400000 and meter.tracker.limits.max_tool_calls == 48


def test_irreducible_large_packet_still_rejected_before_response(tmp_path):
    import hashlib

    text = "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(850))
    packet = {"task": text, "source_packet": []}
    meter = SharedValueMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline=(datetime.now(UTC) + timedelta(hours=3)).isoformat(), packet=lambda: packet)
    task = original_task.__wrapped__()
    model = ScriptedPlanModel(responses=[response("PlanProposal", proposal(task).model_dump(mode="json"))])
    with pytest.raises(PlanContractError, match="50000"):
        propose_with_context(model=model, task=task, source_root=tmp_path, session_root=tmp_path, meter=meter)
    assert meter.summary()["model_requests"] == 0
