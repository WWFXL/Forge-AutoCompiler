"""生产规划接口在旧65分钟拒绝区仍能纠错，并保持共同测试义务。"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_rtorrent_fixed_contract import FixedVerifierRegistry  # noqa: E402
from forge_build_test_preparation_comparison import PreparationMeter, execution_window, preparation_obligation  # noqa: E402

from deerflow.compile import operations  # noqa: E402
from deerflow.compile.operation_window import OperationWindow  # noqa: E402
from deerflow.compile.plan_agent import PlanAgentLedger  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402
from deerflow.compile.staged_verification import StagedVerificationTask  # noqa: E402
from deerflow.compile.unified_plan_equivalent_observed import propose_observed  # noqa: E402


def test_time_window_preserves_short_request_and_full_replay():
    now = datetime.now(UTC)
    policy = OperationWindow((now + timedelta(seconds=1000)).isoformat())
    policy.request(now=now)
    assert policy.command_timeout(1200, now=now) == 700
    with pytest.raises(PlanContractError, match="clean_replay"):
        policy.replay(1200, now=now)
    with pytest.raises(PlanContractError, match="model_request"):
        policy.request(now=now + timedelta(seconds=401))
    with pytest.raises(PlanContractError, match="command"):
        policy.command_timeout(1200, now=now + timedelta(seconds=701))


def test_real_production_correction_carries_obligation_inside_old_blocked_hour(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    spec = json.loads((repo / "benchmarks/manifests/cpp-build-rtorrent-generation-observation-probe-v1.json").read_text())
    item = spec["project"]
    task = StagedVerificationTask.model_validate(item["task"])
    obligation = preparation_obligation(item)
    assert len(obligation["author_build_declarations"]) == 2
    assert all("check_PROGRAMS" in r["excerpt"] for r in obligation["author_build_declarations"])
    packet = dict(task=task.model_dump(mode="json"), source_packet=[], current_plan=None, handoff=None)
    meter = PreparationMeter(
        PlanAgentLedger(tmp_path / "agent"), registry=FixedVerifierRegistry(packet["task"]), obligation=obligation, accepted_models=("scripted-gate",), deadline=(datetime.now(UTC) + timedelta(minutes=20)).isoformat(), packet=lambda: packet
    )
    build = dict(step_id="build", role="build", command="make -j2", source="Makefile.am", expected="编译")
    invalid = dict(reason="真实结构负例", steps=[dict(build, step_id="first"), dict(build, role="configure")])
    valid = dict(reason="修订", steps=[build])

    class GateModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    replies = [
        AIMessage(content="", tool_calls=[dict(name="ObservedBuildActions", args=a, id=f"reply-{i}")], usage_metadata=dict(input_tokens=0, output_tokens=0, total_tokens=0), response_metadata=dict(model_name="scripted-gate"))
        for i, a in enumerate((invalid, valid))
    ]
    plan, _ = propose_observed(model=GateModel(responses=replies), task=task, source_root=tmp_path, session_root=tmp_path, meter=meter)
    assert plan.revision == 1 and meter.summary()["model_requests"] == 2
    assert meter.summary()["unknown_usage_requests"] == 0
    for n in (1, 2):
        material = json.loads((tmp_path / f"agent/contract-material-{n}.json").read_text())
        assert material["projected"]["common_test_preparation"] == obligation
    request = json.loads((tmp_path / "agent/request-2.json").read_text())
    assert "common_test_preparation" in request["system_message"]["content"]
    assert "rejected_candidate" in request["messages"][0]["content"]


def test_actual_runtime_entry_caps_command_and_replay_separately(monkeypatch):
    import forge_build_prepared_arm as prepared
    from forge_build_rtorrent_template_reset_gate_v2 import HostIdentityRuntime

    calls = []
    monkeypatch.setattr(HostIdentityRuntime, "exec", lambda *a, **kw: calls.append(kw["timeout_seconds"]))
    # 只替换Docker执行点；实际新Runtime.exec仍负责预算计算。
    deadline = (datetime.now(UTC) + timedelta(seconds=1000)).isoformat()
    with execution_window(deadline):
        runtime = object.__new__(prepared.CompileDockerRuntime)
        runtime.manager = type("Manager", (), {"log_event": lambda *a, **kw: None})()
        runtime.exec(object(), "true", timeout_seconds=1200)
        assert 695 <= calls[0] <= 700
        with pytest.raises(PlanContractError, match="clean_replay"):
            operations.verify_clean_replay_impl(session=object(), timeout_seconds=1200)
