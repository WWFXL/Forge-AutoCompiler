"""源码隔离、跨阶段预算和实际结构化方案图的零 Provider 回归。"""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from langchain_core.messages import AIMessage
from test_plan_agent import ScriptedPlanModel, proposal, response
from test_plan_agent import task as original_task

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.plan_cross_system import CrossSystemMeter, SharedResearchBudget, before_deadline, collect_packet, diagnostic_packet, propose_cross_system, validate_task_policy
from deerflow.compile.plan_workflow import PlanContractError


@pytest.fixture
def shared(tmp_path):
    (tmp_path / "authorization.json").write_text(json.dumps({"deadline_utc": (datetime.now(UTC) + timedelta(hours=2)).isoformat(), "max_new_provider_cost_usd": 20}))
    (tmp_path / "budget-events.jsonl").write_text(json.dumps({"event": "unexpected_live_test_requests", "reserved_cost_usd": 1}) + "\n")
    return SharedResearchBudget(tmp_path)


def test_shared_stage_keeps_reservation_until_completion_and_never_reuses_identity(shared):
    shared.append({"event": "stage.started", "identity": "first", "reserved_cost_usd": "4"})
    with pytest.raises(PlanContractError, match="未结束"):
        shared.append({"event": "stage.started", "identity": "second", "reserved_cost_usd": "4"})
    with pytest.raises(PlanContractError, match="不匹配"):
        shared.append({"event": "stage.completed", "identity": "first", "charged_cost_usd": "4.01"})
    shared.append({"event": "stage.completed", "identity": "first", "charged_cost_usd": "0.50"})
    with pytest.raises(PlanContractError, match="重复"):
        shared.append({"event": "stage.started", "identity": "first", "reserved_cost_usd": "4"})
    with pytest.raises(PlanContractError, match="预算不足"):
        shared.append({"event": "stage.started", "identity": "second", "reserved_cost_usd": "18.51"})
    shared.append({"event": "stage.started", "identity": "second", "reserved_cost_usd": "18.50"})


def test_deadline_rejects_insufficient_cleanup_time_and_naive_times():
    now = datetime.now(UTC)
    with pytest.raises(PlanContractError):
        before_deadline((now + timedelta(seconds=299)).isoformat(), 300, now=now)
    with pytest.raises(PlanContractError):
        before_deadline("2026-10-20T07:00:00", 300, now=now)
    before_deadline((now + timedelta(seconds=301)).isoformat(), 300, now=now)


def test_packet_is_bounded_tracks_truncation_and_rejects_source_escape(tmp_path):
    (tmp_path / "README.md").write_text("源文件" * 20000)
    rows = collect_packet(tmp_path, "make")
    assert rows[0]["truncated"] and rows[0]["sha256"]
    assert len(json.dumps(rows, ensure_ascii=False).encode()) <= 36000
    (tmp_path / "Makefile").symlink_to(tmp_path.parent / "private-config")
    with pytest.raises(PlanContractError, match="逃出"):
        collect_packet(tmp_path, "make")


def test_real_structured_graph_uses_make_packet_and_preserves_fixed_verification(tmp_path):
    task = original_task.__wrapped__().model_copy(update={"build_system": "make"})
    (tmp_path / "Makefile").write_text("SOURCE_ONLY_MARKER\n")
    model = ScriptedPlanModel(responses=[response("PlanProposal", proposal(task).model_dump(mode="json"))])
    meter = CrossSystemMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat())
    plan, _ = propose_cross_system(model=model, task=task, source_root=tmp_path, meter=meter)
    assert plan.build_system == "make" and tuple(s for s in plan.steps if s.role == "smoke") == task.verification_steps
    request = (tmp_path / "agent/request-1.json").read_text()
    assert "SOURCE_ONLY_MARKER" in request
    assert meter.summary()["model_requests"] == 1


def test_project_reserves_entire_next_request_before_provider(tmp_path):
    meter = CrossSystemMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat())
    meter.cost_usd = Decimal("1.61")
    with pytest.raises(PlanContractError, match="项目费用"):
        meter._before_request()
    assert meter.summary()["model_requests"] == 0


@pytest.mark.parametrize("finish", ["length", "stop"])
def test_nonproposal_stops_after_one_response_with_known_usage(tmp_path, finish):
    task = original_task.__wrapped__().model_copy(update={"build_system": "make"})
    truncated = AIMessage(
        content="", additional_kwargs={"reasoning_content": "仅推理而无方案"}, response_metadata={"model_name": "test-model", "finish_reason": finish}, usage_metadata={"input_tokens": 3, "output_tokens": 8192, "total_tokens": 8195}
    )
    model = ScriptedPlanModel(responses=[truncated, response("PlanProposal", proposal(task).model_dump(mode="json"))])
    meter = CrossSystemMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat())
    with pytest.raises(PlanContractError, match="不自动重试"):
        propose_cross_system(model=model, task=task, source_root=tmp_path, meter=meter)
    assert meter.summary()["model_requests"] == 1
    assert meter.summary()["recorded_tokens"] == 8195
    assert meter.summary()["unknown_usage_requests"] == 0
    assert (tmp_path / "agent/response-1.json").exists()
    assert not (tmp_path / "agent/request-2.json").exists()


def test_malformed_proposal_is_not_implicitly_retried(tmp_path):
    task = original_task.__wrapped__().model_copy(update={"build_system": "make"})
    model = ScriptedPlanModel(responses=[response("PlanProposal", {"reason": "缺少步骤"}), response("PlanProposal", proposal(task).model_dump(mode="json"))])
    meter = CrossSystemMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat())
    with pytest.raises(Exception, match="PlanProposal"):
        propose_cross_system(model=model, task=task, source_root=tmp_path, meter=meter)
    assert meter.summary()["model_requests"] == 1
    assert meter.summary()["unknown_usage_requests"] == 0
    assert not (tmp_path / "agent/request-2.json").exists()


def test_handoff_carries_captured_failure_without_reading_outside_logs(tmp_path):
    root = tmp_path / "logs/plan-diagnostics/command-one/tests"
    root.mkdir(parents=True)
    (root / "stress_mt.log").write_text("LIBUSB_ERROR_NO_DEVICE\n" + "x" * 2000)
    handoff = {"recent_commands": [{"diagnostic_directory": "logs/plan-diagnostics/command-one"}]}
    rows = diagnostic_packet(tmp_path, handoff)
    assert len(rows) == 1 and rows[0]["truncated"]
    assert "LIBUSB_ERROR_NO_DEVICE" in rows[0]["content"] and rows[0]["sha256"]
    (root / "outside.log").symlink_to(tmp_path.parent / "private")
    with pytest.raises(PlanContractError, match="逃出"):
        diagnostic_packet(tmp_path, handoff)


@pytest.mark.parametrize("command", ["./configure --disable-udev", "./configure --enable-udev=no", "make TESTS=stress", "./configure --disable-tests-build"])
def test_fixed_backend_and_test_set_cannot_be_disabled(command):
    task = original_task.__wrapped__().model_copy(update={"build_system": "autotools"})
    candidate = proposal(task)
    candidate.steps[0] = candidate.steps[0].model_copy(update={"command": command})
    with pytest.raises(PlanContractError, match="固定后端"):
        validate_task_policy(task.materialize(candidate, revision=1))
