from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_jev_formal_comparison_v6.py"
SCRIPTS_ROOT = str(REPO_ROOT / "scripts")
if SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, SCRIPTS_ROOT)


def _load_module():
    spec = importlib.util.spec_from_file_location("forge_jev_formal_comparison_v6", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def formal():
    return _load_module()


def test_unseen_cases_are_balanced_across_systems_and_actions(formal) -> None:
    assert len(formal.CASE_SPECS) == 12
    assert len({case["task_id"] for case in formal.CASE_SPECS}) == 12
    assert {formal._task(case["task_id"])["selected_build_system"] for case in formal.CASE_SPECS} == {"cmake", "make", "autotools"}
    for build_system in ("cmake", "make", "autotools"):
        assert sum(formal._task(case["task_id"])["selected_build_system"] == build_system for case in formal.CASE_SPECS) == 4
    for action in ("dependency", "configure", "build"):
        assert sum(case["expected_action"] == action for case in formal.CASE_SPECS) == 4


def test_schedule_has_two_repetitions_and_balanced_positions(formal) -> None:
    assert len(formal.SCHEDULE) == 72
    for task in formal.TASKS:
        assert all(sum(task_id == task["task_id"] and candidate == arm for task_id, candidate in formal.SCHEDULE) == 2 for arm in formal.ARMS)
    for repetition in range(1, formal.REPETITIONS + 1):
        rows = [(index, task_id, arm) for index, (task_id, arm) in enumerate(formal.SCHEDULE, start=1) if formal._repetition_for_sequence(index) == repetition]
        assert len(rows) == 36
        for position in range(3):
            positioned = [arm for offset, (_index, _task_id, arm) in enumerate(rows) if offset % 3 == position]
            assert all(positioned.count(arm) == 4 for arm in formal.ARMS)


def test_rule_gate_and_direct_commands_are_frozen(formal) -> None:
    assert formal.rule_route({}) == "build"
    for case in formal.CASE_SPECS:
        task = formal._task(case["task_id"])
        state = formal.semantic_v2._state_record(task, case["fault_type"], "failure")
        commands = formal._commands(task, case["fault_type"], case["expected_action"])
        expected = next(row["bound_commands"] for row in state["candidate_actions"] if row["action_family"] == case["expected_action"])
        assert commands == expected


def test_v6_preserves_project_selection_and_repairs_only_failed_contracts(formal) -> None:
    assert "ffmpeg" not in {task["task_id"] for task in formal.TASKS}
    assert formal._task("quickjs")["commit_sha"] == "9d01a96849dbbe653da65f231cd40bddc7457ae2"
    assert formal._task("quickjs")["configure_repair_commands"] == [
        "git checkout HEAD -- Makefile",
        "test -f Makefile",
    ]
    assert formal._task("redis")["build_commands"] == ["SOURCE_DATE_EPOCH=1791622465 make -j4 BUILD_TLS=no MALLOC=libc redis-server"]
    assert formal._task("redis")["configure_commands"] == [
        "test -f Makefile",
        "cd src && SOURCE_DATE_EPOCH=1791622465 ./mkreleasehdr.sh",
    ]
    assert formal._task("wolfssl")["artifact_stage_commands"] == [
        "mkdir -p /artifacts/lib /artifacts/include && cp src/.libs/libwolfssl.a /artifacts/lib/ && tar --exclude=wolfssl/wolfcrypt/fips.h -cf - wolfssl | tar -xf - -C /artifacts/include"
    ]


def test_budget_and_primary_thresholds_are_frozen(formal) -> None:
    assert formal.TOTAL_AGENT_REQUEST_CEILING == 72 * 24
    assert formal.TOTAL_AGENT_TOKEN_CEILING == 72 * 300_000
    assert formal.TOTAL_JEV_REQUEST_CEILING == 24
    assert formal.NONINFERIORITY_MARGIN == -0.10
    assert formal.MINIMUM_COST_REDUCTION == 0.20
    assert formal.BOOTSTRAP_SAMPLES == 20_000


def test_jev_route_uses_calibration_and_awaits_strict_verification(formal) -> None:
    task = formal._task("libgit2")
    state = formal.semantic_v2._state_record(task, "invalid_build_state", "Makefile:1: missing separator")
    fingerprint = "f" * 64
    decision = formal.TypedDecision(
        state_id=state["state_id"],
        model=formal.CALIBRATION.model,
        request_fingerprint=fingerprint,
        primary_choice="configure",
        reverse_choice="configure",
        probabilities={
            "dependency": 0.01,
            "configure": 0.97,
            "build": 0.01,
            "escalate_agent": 0.01,
        },
        reverse_probabilities={
            "dependency": 0.01,
            "configure": 0.97,
            "build": 0.01,
            "escalate_agent": 0.01,
        },
    )
    action, route = formal.choose_jev_route(state, decision)
    assert action == "configure"
    assert route["disposition"] == "direct_execute"
    assert route["dispatch_disposition"] == "awaiting_strict_verification"


def test_manifest_authorization_and_claim_boundaries(formal, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(formal, "_git", lambda *args: "a" * 40)
    monkeypatch.setattr(formal, "_git_blob_sha256", lambda revision, path: "b" * 64)
    monkeypatch.setattr(formal, "file_sha256", lambda path: "c" * 64)
    manifest = formal.build_manifest("a" * 40)
    assert manifest["authorization"]["formal_attempts"] == 72
    assert manifest["authorization"]["replacement"] is False
    assert manifest["analysis"]["noninferiority_margin"] == -0.10
    assert manifest["interpretation"] == {
        "controlled_failure_formal_comparison": True,
        "natural_failure_generalization": False,
        "strict_success_noninferiority": True,
        "cost_savings_claim": True,
        "dynamic_budget_claim": False,
    }


def test_oracles_and_compiled_targets_are_constructible(formal) -> None:
    for task in formal.TASKS:
        target_path, target_type = formal._compiled_target(task)
        assert target_path in task["target"]["required_artifacts"]
        assert target_type in {"executable", "static_library"}
        formal._oracle_spec(task).validate()


def test_token_cost_and_batch_aggregation(formal) -> None:
    row = {
        "agent_usage": {
            "model_requests": 1,
            "recorded_tokens": 5,
            "input_tokens": 3,
            "output_tokens": 2,
            "estimated_cost_usd": formal._agent_cost_usd(3, 2),
        },
        "jev_usage": {
            "model_requests": 1,
            "input_tokens": 7,
            "cost_usd": 0.0001,
        },
    }
    totals = formal._batch_totals([row, row])
    assert totals["agent_requests"] == 2
    assert totals["agent_recorded_tokens"] == 10
    assert totals["agent_input_tokens"] == 6
    assert totals["agent_output_tokens"] == 4
    assert totals["jev_requests"] == 2
    assert totals["jev_input_tokens"] == 14
    assert totals["total_provider_estimated_cost_usd"] == pytest.approx(totals["agent_estimated_cost_usd"] + 0.0002)


def _row(task_id: str, arm: str, success: bool, cost: float) -> dict:
    return {
        "task_id": task_id,
        "arm": arm,
        "strict_reproducible_build_success": success,
        "duration_ms": 1000,
        "escalated_agent": arm != "jev_gate_agent",
        "agent_usage": {
            "model_requests": int(arm != "jev_gate_agent"),
            "recorded_tokens": 1,
            "estimated_cost_usd": cost,
        },
        "jev_usage": {
            "model_requests": int(arm == "jev_gate_agent"),
            "cost_usd": 0.0,
        },
    }


def test_clustered_bootstrap_resamples_project_families(formal) -> None:
    rows = []
    for case in formal.CASE_SPECS:
        for _repetition in (1, 2):
            rows.extend(
                [
                    _row(case["task_id"], "always_agent", True, 1.0),
                    _row(case["task_id"], "rule_gate_agent", True, 0.5),
                    _row(case["task_id"], "jev_gate_agent", True, 0.1),
                ]
            )
    result = formal._clustered_bootstrap(rows)
    assert result["unit"] == "project_family"
    assert result["strict_success_difference"]["one_sided_95_lower"] == 0
    assert result["provider_cost_reduction"]["two_sided_95_interval"] == pytest.approx([0.9, 0.9])
