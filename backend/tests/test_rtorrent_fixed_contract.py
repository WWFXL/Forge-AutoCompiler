"""固定验证脚本完整保留、按需取回及共同多轮接口。"""

import copy
import json
import sys
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from test_plan_agent import ScriptedPlanModel, proposal, response
from test_plan_agent import task as original_task

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_rtorrent_fixed_contract import (
    META,
    PREFIX,
    ContractMeter,
    ContractWorkingSet,
    FixedVerifierRegistry,
    contract_interfaces,
)  # noqa: E402
from forge_build_rtorrent_shared_values import restore_values  # noqa: E402

from deerflow.compile.plan_agent import PlanAgentLedger  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402
from deerflow.compile.recovery_text_factors import restore_factor_packet  # noqa: E402
from deerflow.compile.unified_plan_equivalent_observed import propose_observed  # noqa: E402


def task_and_registry():
    task = original_task.__wrapped__()
    fixed = task.verification_steps[0].model_copy(update={"command": "printf '固定验证中文😀'\n" * 900})
    task = task.model_copy(update={"verification_steps": (fixed,)})
    return task, FixedVerifierRegistry(task.model_dump(mode="json"))


def test_reference_keeps_every_original_value_and_full_command():
    task, registry = task_and_registry()
    packet = dict(
        task=task.model_dump(mode="json"),
        current_plan=task.materialize(proposal(task), revision=1).model_dump(mode="json"),
        state={"marker": "authoritative"},
    )
    before = copy.deepcopy(packet)
    view = registry.project(packet)
    assert packet == before and registry.restore(view) == packet
    assert view["task"]["verification_steps"][0]["command"].startswith(PREFIX)
    assert len(json.dumps(view).encode()) < len(json.dumps(packet).encode())
    assert view["task"]["verification_steps"][0]["required_output"] == packet["task"]["verification_steps"][0]["required_output"]


def test_all_utf8_and_emoji_retrieved_exactly_without_character_loss():
    task, registry = task_and_registry()
    key = next(iter(registry.commands))
    pieces, position = [], 0
    while True:
        row = registry.read(key, position)
        assert row["accepted"] and len(row["content"].encode()) <= 8000 and len(row["content"]) <= 4000
        pieces.append(row["content"])
        if row["next_char"] is None:
            break
        assert row["next_char"] > position
        position = row["next_char"]
    recovered = "".join(pieces)
    assert recovered == task.verification_steps[0].command and sha256(recovered.encode()).hexdigest() == key


@pytest.mark.parametrize("key,offset", [("unknown", 0), ("known", -1), ("known", 10**9), ("known", True)])
def test_unknown_or_invalid_read_rejected_without_access(key, offset):
    _, registry = task_and_registry()
    row = registry.read(next(iter(registry.commands)) if key == "known" else key, offset)
    assert not row["accepted"] and "content" not in row


@pytest.mark.parametrize("fault", ["missing", "registry", "unknown", "changed", "metadata"])
def test_corrupt_or_weakened_contract_view_rejected(fault):
    task, registry = task_and_registry()
    view = registry.project({"task": task.model_dump(mode="json")})
    if fault == "missing":
        del view[META]
    elif fault == "registry":
        view[META]["registry_sha256"] = "0" * 64
    elif fault == "unknown":
        view["task"]["verification_steps"][0]["command"] = PREFIX + "0" * 64
    elif fault == "changed":
        view["task"]["verification_steps"][0]["required_output"] = []
    else:
        view[META]["commands"] = {}
    with pytest.raises(PlanContractError):
        registry.restore(view)


def test_short_contract_has_no_external_reference():
    task = original_task.__wrapped__()
    registry = FixedVerifierRegistry(task.model_dump(mode="json"))
    packet = {"task": task.model_dump(mode="json")}
    assert registry.project(packet) == packet and registry.restore(packet) == packet


def test_actual_multiturn_graph_reads_script_then_returns_original_fixed_tests(
    tmp_path,
):
    task, registry = task_and_registry()
    key = next(iter(registry.commands))
    meter = ContractMeter(
        PlanAgentLedger(tmp_path / "agent"),
        registry=registry,
        accepted_models=("test-model",),
        deadline=(datetime.now(UTC) + timedelta(hours=3)).isoformat(),
        packet=lambda: dict(task=task.model_dump(mode="json"), source_packet=[]),
    )
    actions = []
    for step in proposal(task).steps:
        if step.role in ("dependency", "configure", "build"):
            value = step.model_dump(mode="json")
            value["stdout_contains"] = value.pop("required_output")
            actions.append(value)
    model = ScriptedPlanModel(
        responses=[
            response("read_fixed_contract", {"command_sha256": key}),
            response(
                "ObservedBuildActions",
                dict(reason="零Provider合同读取与原测试装配", steps=actions),
            ),
        ]
    )
    with contract_interfaces(registry):
        plan, _ = propose_observed(
            model=model,
            task=task,
            source_root=tmp_path,
            session_root=tmp_path,
            meter=meter,
        )
    assert tuple(s for s in plan.steps if s.role == "smoke") == task.verification_steps
    assert meter.summary()["model_requests"] == 2 and meter.summary()["tool_calls"] == 1
    request = json.loads((tmp_path / "agent/request-2.json").read_text())
    payload = json.loads(request["messages"][0]["content"])
    view = restore_values(restore_factor_packet({k: v for k, v in payload.items() if k not in ("recent_tool_results", "remaining_budget")}))
    original = registry.restore(view)
    assert original["task"] == task.model_dump(mode="json")
    assert original["source_packet"][0]["tool"] == "read_fixed_contract"
    assert original["read_index"][0]["accepted"]
    assert meter.tracker.limits.max_model_requests == 73 and meter.tracker.limits.max_tool_calls == 48 and meter.tracker.limits.max_recorded_tokens == 400000


def test_working_set_keeps_rejected_read_in_index_only():
    working = ContractWorkingSet()
    working.observe(
        "read_fixed_contract",
        {"command_sha256": "unknown"},
        json.dumps(dict(accepted=False, error="unknown")),
    )
    assert working.index[0]["accepted"] is False and not working.entries


def test_common_interface_patches_restore_original_tools_and_prompts(tmp_path):
    from deerflow.compile import plan_agent_context as context
    from deerflow.compile import plan_agent_provenance as provenance
    from deerflow.compile import unified_plan_equivalent_observed as observed

    _, registry = task_and_registry()
    originals = (
        context.safe_readonly_tools,
        provenance.safe_readonly_tools,
        observed.safe_readonly_tools,
        observed.OBSERVED_PROMPT,
    )
    with contract_interfaces(registry):
        for module in (context, provenance, observed):
            assert [t.name for t in module.safe_readonly_tools(tmp_path, tmp_path)] == [
                "list_source",
                "read_source",
                "read_failure_log",
                "read_fixed_contract",
            ]
    assert (
        context.safe_readonly_tools,
        provenance.safe_readonly_tools,
        observed.safe_readonly_tools,
        observed.OBSERVED_PROMPT,
    ) == originals


def test_reference_cannot_replace_original_executable_verification_in_plan():
    task, registry = task_and_registry()
    candidate = proposal(task)
    key = next(iter(registry.commands))
    candidate.steps = [step.model_copy(update={"command": PREFIX + key}) if step.role == "smoke" else step for step in candidate.steps]
    with pytest.raises(PlanContractError, match="验证"):
        task.materialize(candidate, revision=1)


def test_large_irreducible_state_still_stops_before_model_response(tmp_path):
    task, registry = task_and_registry()
    state = "".join(sha256(str(i).encode()).hexdigest() for i in range(900))
    meter = ContractMeter(
        PlanAgentLedger(tmp_path / "agent"),
        registry=registry,
        accepted_models=("test-model",),
        deadline=(datetime.now(UTC) + timedelta(hours=3)).isoformat(),
        packet=lambda: dict(
            task=task.model_dump(mode="json"),
            state={"diagnostic": state},
            source_packet=[],
        ),
    )
    model = ScriptedPlanModel(responses=[response("PlanProposal", proposal(task).model_dump(mode="json"))])
    with contract_interfaces(registry), pytest.raises(PlanContractError, match="50000"):
        propose_observed(
            model=model,
            task=task,
            source_root=tmp_path,
            session_root=tmp_path,
            meter=meter,
        )
    assert meter.summary()["model_requests"] == 0


def test_actual_context_graph_reads_contract_and_materializes_original_tests(tmp_path):
    from deerflow.compile.plan_agent_context import propose_with_context

    task, registry = task_and_registry()
    key = next(iter(registry.commands))
    meter = ContractMeter(
        PlanAgentLedger(tmp_path / "agent"),
        registry=registry,
        accepted_models=("test-model",),
        deadline=(datetime.now(UTC) + timedelta(hours=3)).isoformat(),
        packet=lambda: dict(task=task.model_dump(mode="json"), source_packet=[]),
    )
    model = ScriptedPlanModel(
        responses=[
            response("read_fixed_contract", {"command_sha256": key}),
            response("PlanProposal", proposal(task).model_dump(mode="json")),
        ]
    )
    with contract_interfaces(registry):
        plan, _ = propose_with_context(
            model=model,
            task=task,
            source_root=tmp_path,
            session_root=tmp_path,
            meter=meter,
        )
    assert tuple(s for s in plan.steps if s.role == "smoke") == task.verification_steps
    assert meter.summary()["model_requests"] == 2 and meter.summary()["tool_calls"] == 1


@pytest.mark.parametrize("successful", [True, False])
def test_actual_strong_graph_reads_reference_but_fixed_test_service_executes_original(tmp_path, monkeypatch, successful):
    from types import SimpleNamespace

    from langchain_core.messages import AIMessage

    from deerflow.compile.plan_agent_canary import ToolBuildService
    from deerflow.compile.plan_agent_provenance import run_tool_agent_automatic

    task, registry = task_and_registry()
    key = next(iter(registry.commands))
    meter = ContractMeter(
        PlanAgentLedger(tmp_path / "agent"),
        registry=registry,
        accepted_models=("test-model",),
        deadline=(datetime.now(UTC) + timedelta(hours=3)).isoformat(),
        packet=lambda: dict(task=task.model_dump(mode="json"), source_packet=[]),
    )
    service = ToolBuildService(
        task=task,
        session=None,
        manager=None,
        source_root=tmp_path,
        frozen={},
        meter=meter,
    )
    calls = []

    def execute(command, role, workdir):
        calls.append((command, role, workdir))
        return dict(command_id="fixed-command", exit_code=0 if successful else 1), SimpleNamespace(exit_code=0 if successful else 1, combined_output="100% tests passed")

    monkeypatch.setattr(service, "execute", execute)
    # 最后文本只用于终结脚本图，不触发提交，也不能宣告strict成功。
    final = AIMessage(
        content="脚本图结束，未提交验收",
        response_metadata={"model_name": "test-model"},
        usage_metadata=dict(input_tokens=0, output_tokens=0, total_tokens=0),
    )
    model = ScriptedPlanModel(
        responses=[
            response("read_fixed_contract", {"command_sha256": key}),
            response("run_fixed_tests", {}),
            final,
        ]
    )
    with contract_interfaces(registry):
        run_tool_agent_automatic(
            model=model,
            service=service,
            source_root=tmp_path,
            session_root=tmp_path,
            meter=meter,
        )
    assert calls == [(s.command, "smoke", s.workdir) for s in task.verification_steps]
    assert all(not command.startswith(PREFIX) for command, _, _ in calls)
    assert service.verifications == ({task.verification_steps[0].step_id: "fixed-command"} if successful else {})
    assert not service.verified and meter.summary()["model_requests"] == 3 and meter.summary()["tool_calls"] == 2
