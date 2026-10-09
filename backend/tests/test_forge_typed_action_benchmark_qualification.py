from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = REPO_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_typed_action_benchmark_qualification as qualification  # noqa: E402


def test_generated_contract_is_frozen_balanced_and_result_blind() -> None:
    pool = qualification.generate_source_pool()
    manifest = qualification.generate_manifest(pool)

    assert pool == qualification.load_json(qualification.DEFAULT_SOURCE_POOL)
    assert manifest == qualification.load_json(qualification.DEFAULT_MANIFEST)
    assert qualification.generate_schema(manifest) == qualification.load_json(qualification.DEFAULT_SCHEMA)
    assert Counter(task["split"] for task in pool["tasks"]) == {"design": 6, "calibration": 6, "evaluation": 12}
    assert Counter(task["selected_build_system"] for task in pool["tasks"]) == {"cmake": 8, "make": 8, "autotools": 8}
    assert len({task["project_family"] for task in pool["tasks"]}) == 24
    assert manifest["authorization"]["provider_calls_authorized"] is False
    assert manifest["authorization"]["credential_read_authorized"] is False
    assert manifest["authorization"]["model_tokens_authorized"] == 0
    assert manifest["benchmark_design"]["old_agent_action_is_ground_truth"] is False
    assert manifest["amendments"] == [
        {
            "amendment": 1,
            "failed_attempt": 1,
            "failure_record_path": "benchmarks/reports/cpp-typed-action-benchmark-qualification-v1-attempt-1-failure.json",
            "failure_record_sha256": qualification.file_sha256(qualification.ATTEMPT_1_FAILURE),
            "fresh_full_rerun_required": True,
            "sole_change": "libuv oracle compile flag -std=c11 -> -std=gnu11",
            "project_replacement": False,
            "threshold_change": False,
            "action_schema_change": False,
        }
    ]


def test_libuv_amendment_changes_only_the_oracle_compile_mode() -> None:
    pool = qualification.generate_source_pool()
    libuv = next(task for task in pool["tasks"] if task["task_id"] == "libuv")

    assert libuv["oracle"]["compile_argv"][1] == "-std=gnu11"
    assert pool["amendments"][0]["reuse_partial_outcomes"] is False
    failure = qualification.load_json(qualification.ATTEMPT_1_FAILURE)
    assert failure["status"] == "invalidated_infrastructure_failure"
    assert failure["formal_qualification_report_written"] is False
    assert failure["recovery"]["project_replacement"] is False
    assert failure["recovery"]["threshold_change"] is False


def test_evaluation_commits_are_strictly_time_shifted() -> None:
    pool = qualification.generate_source_pool()
    development = [qualification._parse_time(task["commit_committed_at"]) for task in pool["tasks"] if task["split"] != "evaluation"]
    evaluation = [qualification._parse_time(task["commit_committed_at"]) for task in pool["tasks"] if task["split"] == "evaluation"]

    assert max(development) < min(evaluation)


def test_state_templates_cover_every_action_family_at_least_twenty_times() -> None:
    pool = qualification.generate_source_pool()
    coverage: Counter[str] = Counter()

    for task in pool["tasks"]:
        for state_kind in qualification.STATE_KINDS:
            families = qualification._candidate_families(task, state_kind)
            assert len(families) == 3
            assert len(set(families)) == 3
            coverage.update(families)

    assert set(coverage) == set(qualification.ACTION_FAMILIES)
    assert min(coverage.values()) >= 20


def test_submit_cannot_be_safe_when_any_strict_check_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = qualification.generate_source_pool()
    task = next(task for task in pool["tasks"] if task["task_id"] == "leveldb")
    state = qualification._state_record(
        task=task,
        state_kind="staged",
        facts=qualification._facts(configured=True, built=True, staged=True, dependency_ready=True),
        last_action=None,
    )
    action = next(action for action in state["candidate_actions"] if action["action_family"] == "submit")
    workspace = tmp_path / "workspace"
    artifacts = tmp_path / "artifacts"
    workspace.mkdir()
    artifacts.mkdir()

    def fake_submit(**_kwargs: Any) -> dict[str, Any]:
        log = tmp_path / "strict.log"
        log.write_text("incomplete\n")
        return {
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 0.1,
            "log_sha256": qualification.file_sha256(log),
            "log_tail": "incomplete",
            "strict_checks": {"candidate": True, "functional": True, "provenance": True, "clean_replay": False},
        }

    monkeypatch.setattr(qualification, "_strict_submit", fake_submit)
    outcome = qualification._execute_candidate(
        manifest=qualification.generate_manifest(pool),
        image="sha256:" + "a" * 64,
        task=task,
        state=state,
        action=action,
        workspace=workspace,
        artifacts=artifacts,
        root=tmp_path,
    )

    assert outcome["exit_code"] == 1
    assert outcome["direct_execution_safe"] is False
    assert outcome["eligible_next_action"] is False


def test_replay_adjudication_stops_when_consistency_misses_threshold() -> None:
    pool = qualification.generate_source_pool()
    manifest = qualification.generate_manifest(pool)
    metrics = {
        "project_count": 24,
        "projects_by_split": {"calibration": 6, "design": 6, "evaluation": 12},
        "state_count": 120,
        "candidate_outcome_count": 720,
        "expected_candidate_outcome_count": 720,
        "reference_closure_count": 48,
        "expected_reference_closure_count": 48,
        "minimum_action_family_state_coverage": 24,
        "replay_consistency": 0.949,
        "all_build_systems_complete": True,
        "all_candidates_bounded": True,
    }
    historical = {"coverage": 1.0}

    decision = qualification._adjudicate(manifest, metrics, historical)

    assert decision["passed"] is False
    assert decision["decision"] == "abandon_controller_and_keep_benchmark"
    assert decision["thresholds_adjusted_after_results"] is False


def test_rule_gate_saturation_blocks_jev_entry_without_provider() -> None:
    manifest, pool = qualification.load_contract()
    report = qualification.validate_report(qualification.load_json(qualification.DEFAULT_JSON_REPORT), manifest, pool)

    audit = qualification.generate_rule_gate_audit(report)

    assert audit["overall"] == {
        "state_count": 120,
        "safe_count": 120,
        "eligible_count": 120,
        "top1_safe_rate": 1.0,
        "direct_execution_coverage": 1.0,
        "wrong_direct_action_rate": 0.0,
    }
    assert audit["eligible_action_multiplicity"] == {"1": 72, "2": 48}
    assert all(metrics["direct_execution_coverage"] == 1.0 for metrics in audit["by_build_system"].values())
    assert audit["phase_b_entry_gate"] == {
        "required_rule_gate_coverage_uplift": 0.1,
        "maximum_possible_coverage_uplift": 0.0,
        "jev_entry_identifiable": False,
    }
    assert audit["decision"] == "stop_jev_provider_qualification_and_redesign_benchmark"
    assert audit["provider_calls"] == 0
    assert audit["model_tokens"] == 0


@pytest.mark.skipif(os.getenv("FORGE_RUN_TYPED_ACTION_DOCKER") != "1", reason="需要显式启用 Docker 集成门禁")
def test_docker_preflight_uses_frozen_image_and_zero_provider() -> None:
    manifest, pool = qualification.load_contract()

    result = qualification.preflight(manifest, pool)

    assert result["ready"] is True
    assert result["task_count"] == 24
    assert result["historical_eligible_decisions"] == 409
    assert result["provider_calls"] == 0
    assert result["credential_reads"] == 0
    assert result["model_tokens"] == 0
