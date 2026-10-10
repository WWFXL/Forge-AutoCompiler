from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_jev_end_to_end_canary_v6.py"
SCRIPTS_ROOT = str(REPO_ROOT / "scripts")
if SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, SCRIPTS_ROOT)


def _load_module():
    spec = importlib.util.spec_from_file_location("forge_jev_end_to_end_canary_v6", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def canary():
    return _load_module()


def test_three_build_system_cases_and_balanced_arms(canary) -> None:
    assert {canary._task(case["task_id"])["selected_build_system"] for case in canary.CASE_SPECS} == {"cmake", "make", "autotools"}
    assert {case["expected_action"] for case in canary.CASE_SPECS} == {"dependency", "configure", "build"}
    assert len(canary.SCHEDULE) == 9
    assert all(sum(row[1] == arm for row in canary.SCHEDULE) == 3 for arm in canary.ARMS)
    assert all(sum(row[0] == case["task_id"] for row in canary.SCHEDULE) == 3 for case in canary.CASE_SPECS)


def test_rule_gate_is_frozen_build(canary) -> None:
    assert canary.rule_route({}) == "build"


def test_direct_commands_are_code_bound(canary) -> None:
    for case in canary.CASE_SPECS:
        task = canary._task(case["task_id"])
        commands = canary._commands(task, case["fault_type"], case["expected_action"])
        assert commands
        assert commands == next(row["bound_commands"] for row in canary.semantic_v2._state_record(task, case["fault_type"], "failure")["candidate_actions"] if row["action_family"] == case["expected_action"])


def test_cares_artifact_stage_is_an_explicit_copy_action(canary) -> None:
    commands = canary._task("c-ares")["artifact_stage_commands"]
    assert commands == list(canary.C_ARES_ARTIFACT_STAGE_COMMANDS)
    assert all("make" not in command for command in commands)
    assert all("/artifacts" in command for command in commands)
    assert "include/ares_version.h" in commands[0]


def test_budget_is_bounded(canary) -> None:
    assert canary.AGENT_BUDGET["max_model_requests"] == 24
    assert canary.AGENT_BUDGET["max_recorded_tokens"] == 300_000
    assert canary.TOTAL_AGENT_REQUEST_CEILING == 9 * 24
    assert canary.TOTAL_AGENT_TOKEN_CEILING == 9 * 300_000
    assert canary.TOTAL_JEV_REQUEST_CEILING == 3


def test_jev_route_uses_calibration_and_never_declares_success(canary) -> None:
    task = canary._task("args")
    state = canary.semantic_v2._state_record(task, "invalid_build_state", "Makefile:1: missing separator")
    fingerprint = "f" * 64
    decision = canary.TypedDecision(
        state_id=state["state_id"],
        model=canary.CALIBRATION.model,
        request_fingerprint=fingerprint,
        primary_choice="configure",
        reverse_choice="configure",
        probabilities={"dependency": 0.01, "configure": 0.97, "build": 0.01, "escalate_agent": 0.01},
        reverse_probabilities={"dependency": 0.01, "configure": 0.97, "build": 0.01, "escalate_agent": 0.01},
    )
    action, route = canary.choose_jev_route(state, decision)
    assert action == "configure"
    assert route["disposition"] == "direct_execute"
    assert route["dispatch_disposition"] == "awaiting_strict_verification"


def test_manifest_authorization_and_claim_boundaries(canary, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(canary, "_git", lambda *args: "a" * 40)
    monkeypatch.setattr(canary, "_git_blob_sha256", lambda revision, path: "b" * 64)
    monkeypatch.setattr(canary, "file_sha256", lambda path: "c" * 64)
    manifest = canary.build_manifest("a" * 40)
    assert manifest["authorization"]["formal_attempts"] == 9
    assert manifest["authorization"]["replacement"] is False
    assert manifest["interpretation"] == {
        "canary_only": True,
        "treatment_effect": False,
        "strict_success_noninferiority": False,
        "cost_savings_claim": False,
        "dynamic_budget_claim": False,
    }


def test_target_contracts_and_oracles_are_constructible(canary) -> None:
    for case in canary.CASE_SPECS:
        task = canary._task(case["task_id"])
        target_path, target_type = canary._compiled_target(task)
        assert target_path in task["target"]["required_artifacts"]
        assert target_type in {"executable", "shared_library", "static_library", "object"}
        oracle = canary._oracle_spec(task)
        oracle.validate()
        assert oracle.oracle_ref == canary._oracle_ref(task)


def test_batch_budget_aggregation_fails_closed(canary) -> None:
    row = {
        "agent_usage": {"model_requests": 1, "recorded_tokens": 2},
        "jev_usage": {"model_requests": 1, "input_tokens": 3, "cost_usd": 0.0001},
    }
    totals = canary._batch_totals([row, row])
    assert totals == {
        "agent_requests": 2,
        "agent_recorded_tokens": 4,
        "jev_requests": 2,
        "jev_input_tokens": 6,
        "jev_cost_usd": 0.0002,
    }
    assert canary._within_budget(totals) is True
    totals["jev_requests"] = canary.TOTAL_JEV_REQUEST_CEILING + 1
    assert canary._within_budget(totals) is False


def test_compile_workspace_is_bound_to_repository_root(canary, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEER_FLOW_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("DEER_FLOW_HOST_WORKSPACE_ROOT", raising=False)
    workspace = canary._configure_compile_workspace({"environment": {"workspace_root_binding": "repository_root"}})
    assert workspace == {
        "binding": "repository_root",
        "process_root": ".compile-sessions",
        "host_root": ".compile-sessions",
    }
    assert canary.os.environ["DEER_FLOW_WORKSPACE_ROOT"] == str(canary.REPO_ROOT)
    assert canary.os.environ["DEER_FLOW_HOST_WORKSPACE_ROOT"] == str(canary.REPO_ROOT)


def test_authoritative_build_system_can_select_non_primary_capability(canary, monkeypatch: pytest.MonkeyPatch) -> None:
    task = canary._task("c-ares")
    session = SimpleNamespace()
    monkeypatch.setattr(
        canary,
        "inspect_build_system_impl",
        lambda *, session: (
            "cmake",
            [("cmake", "CMakeLists.txt"), ("autotools", "configure.ac")],
            [],
        ),
    )

    def enforce(*, session, observed_build_system, detected_build_systems):
        assert observed_build_system == "cmake"
        assert detected_build_systems == ["cmake", "autotools"]
        return True, "autotools", None

    monkeypatch.setattr(canary, "_enforce_experiment_build_system", enforce)
    assert canary._select_experiment_build_system(session, task) == (
        "cmake",
        ["cmake", "autotools"],
        "autotools",
    )


@pytest.mark.parametrize(
    ("task_id", "fault_type", "expected_fragment"),
    [
        ("args", "invalid_build_state", "build/Makefile"),
        ("c-ares", "missing_compile_input", "src/lib/ares_library_init.c"),
    ],
)
def test_fault_mutation_runs_inside_compile_runtime(
    canary,
    monkeypatch: pytest.MonkeyPatch,
    task_id: str,
    fault_type: str,
    expected_fragment: str,
) -> None:
    observed: dict[str, object] = {}

    def runtime_exec(session, command, **kwargs):
        observed.update(command=command, kwargs=kwargs)
        return SimpleNamespace(exit_code=0)

    monkeypatch.setattr(
        canary,
        "get_compile_services",
        lambda: SimpleNamespace(runtime=SimpleNamespace(exec=runtime_exec)),
    )
    failure_record = SimpleNamespace(command_id="failure-command", exit_code=2, timed_out=False)
    monkeypatch.setattr(
        canary,
        "_run_bound_commands",
        lambda *args, **kwargs: (False, [failure_record], "controlled failure"),
    )
    events: list[tuple[str, dict[str, object]]] = []
    ledger = SimpleNamespace(append=lambda name, payload: events.append((name, payload)))

    state, returned_record = canary._inject_fault(SimpleNamespace(), canary._task(task_id), fault_type, ledger)

    assert expected_fragment in observed["command"]
    assert observed["kwargs"] == {
        "workdir": "/workspace/repo",
        "timeout_seconds": 30,
        "strict_shell": True,
    }
    assert returned_record is failure_record
    assert state["semantic_failure_log"] == "controlled failure"
    assert [name for name, _payload in events] == [
        "canary.fault_injected",
        "canary.fault_observed",
    ]
