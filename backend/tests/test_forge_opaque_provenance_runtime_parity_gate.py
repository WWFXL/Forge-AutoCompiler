"""Issue #186 runtime-parity gate 的零 provider 静态测试。"""

from __future__ import annotations

import importlib.util
import inspect
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_deepseek import ChatDeepSeek

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
SCRIPT_PATH = SCRIPTS_DIR / "forge_opaque_provenance_runtime_parity_gate.py"


def _load_module():
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location("forge_opaque_provenance_runtime_parity_gate_test", SCRIPT_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


gate = _load_module()


def test_action_budget_is_split_and_atomic_under_concurrency() -> None:
    budget = gate.AtomicActionBudget()

    def claim_inspection() -> bool:
        try:
            budget.claim("inspection")
        except gate.RuntimeParityGateError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=12) as pool:
        accepted = list(pool.map(lambda _index: claim_inspection(), range(20)))

    assert sum(accepted) == 4
    snapshot = budget.snapshot()
    assert snapshot["limits"] == gate.ACTION_LIMITS
    assert snapshot["consumed"]["inspection"] == 4
    assert snapshot["remaining"]["inspection"] == 0


def test_repair_build_is_bound_to_frozen_directory_and_target() -> None:
    policy = gate.FrozenActionPolicy()
    gate.validate_repair_build(gate.opaque.TREATMENT_BUILD_COMMAND, workdir=policy.workdir, policy=policy)
    for command in (
        "cmake --build /workspace/repo/other --target accumulate_examples -j2",
        "cmake --build /workspace/repo/build --target another -j2",
        "cmake --build /workspace/repo/build --target accumulate_examples && id",
        "cmake -S examples -B build",
    ):
        with pytest.raises(gate.RuntimeParityGateError):
            gate.validate_repair_build(command, workdir=policy.workdir, policy=policy)


def test_stage_is_exact_and_reserves_submit_before_execution() -> None:
    calls: list[dict] = []

    class FakeTool:
        def invoke(self, payload):
            calls.append(payload)
            return json.dumps({"automatic_submit": {"status": "passed"}})

    adapter = gate.RuntimeParityToolAdapter(run_tool=FakeTool(), submit_tool=FakeTool())
    result = json.loads(adapter.run(gate.opaque.TREATMENT_STAGE_COMMAND, command_role="artifact_stage"))
    assert result["automatic_submit"]["status"] == "passed"
    snapshot = adapter.budget.snapshot()
    assert snapshot["consumed"]["artifact_stage"] == 1
    assert snapshot["consumed"]["submit"] == 1
    assert calls[0]["workdir"] == gate.opaque.WORKDIR


def test_repair_build_reserves_submit_when_parent_artifact_is_already_staged() -> None:
    class FakeTool:
        def invoke(self, _payload):
            return json.dumps({"automatic_submit": {"status": "passed"}})

    adapter = gate.RuntimeParityToolAdapter(
        run_tool=FakeTool(),
        submit_tool=FakeTool(),
        staged_artifacts_present=lambda: True,
    )
    result = json.loads(adapter.run(gate.opaque.TREATMENT_BUILD_COMMAND, command_role="build"))
    assert result["automatic_submit"]["status"] == "passed"
    consumed = adapter.budget.snapshot()["consumed"]
    assert consumed["repair_build"] == 1
    assert consumed["submit"] == 1


def test_adapter_rejects_forbidden_and_over_budget_actions_before_tool_call() -> None:
    calls: list[dict] = []

    class FakeTool:
        def invoke(self, payload):
            calls.append(payload)
            return "ok"

    adapter = gate.RuntimeParityToolAdapter(run_tool=FakeTool(), submit_tool=FakeTool())
    with pytest.raises(gate.RuntimeParityGateError, match="forbidden"):
        adapter.run("cmake -S examples -B build", command_role="configure")
    assert calls == []

    for _ in range(gate.ACTION_LIMITS["repair_build"]):
        assert adapter.run(gate.opaque.TREATMENT_BUILD_COMMAND, command_role="build") == "ok"
    with pytest.raises(gate.RuntimeParityGateError, match="repair_build budget exhausted"):
        adapter.run(gate.opaque.TREATMENT_BUILD_COMMAND, command_role="build")
    assert len(calls) == gate.ACTION_LIMITS["repair_build"]

    submit_adapter = gate.RuntimeParityToolAdapter(run_tool=FakeTool(), submit_tool=FakeTool())
    for _ in range(gate.ACTION_LIMITS["submit"]):
        assert submit_adapter.submit() == "ok"
    with pytest.raises(gate.RuntimeParityGateError, match="submit budget exhausted"):
        submit_adapter.submit()
    assert len(calls) == gate.ACTION_LIMITS["repair_build"] + gate.ACTION_LIMITS["submit"]


def test_serial_tool_call_contract_uses_supported_langchain_setting() -> None:
    assert "parallel_tool_calls" in inspect.signature(ChatDeepSeek.bind_tools).parameters
    assert gate.serial_model_settings({"temperature": 0}) == {
        "temperature": 0,
        "parallel_tool_calls": False,
    }
    request = SimpleNamespace(
        model_settings={"temperature": 0},
        override=lambda **updates: SimpleNamespace(**updates),
    )
    captured = gate.SerialToolCallMiddleware().wrap_model_call(request, lambda value: value)
    assert captured.model_settings["parallel_tool_calls"] is False


def test_cli_is_zero_provider_and_records_measurement_censoring() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "validate"],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert result["measurement_classification"] == "measurement_policy_censored"
    assert result["intervention_classification"] == "intervention_delivery_failure"
    assert result["parallel_tool_calls"] is False
    assert result["fence_released_before_capture"] is True
    assert (result["provider_calls"], result["formal_attempts"], result["model_tokens"]) == (0, 0, 0)


def test_source_does_not_access_credentials_or_modify_frozen_evidence() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    for forbidden in (
        "create_chat_model",
        "openai_ak",
        "deepseek_api_key",
        "os.getenv",
        "execute_reachability",
        "execute_pair",
        "benchmark-evidence-opaque-provenance-minimal-canary-authorized-v1",
    ):
        assert forbidden not in source
