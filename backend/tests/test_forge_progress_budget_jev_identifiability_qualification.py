from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = REPO_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_progress_budget_jev_identifiability_qualification as qualification  # noqa: E402


def test_generated_contract_is_frozen_balanced_and_zero_provider() -> None:
    pool = qualification.generate_source_pool()
    manifest = qualification.generate_manifest(pool)

    assert pool == qualification.v1.load_json(qualification.DEFAULT_SOURCE_POOL)
    assert manifest == qualification.v1.load_json(qualification.DEFAULT_MANIFEST)
    assert qualification.generate_schema(manifest) == qualification.v1.load_json(qualification.DEFAULT_SCHEMA)
    assert Counter(task["selected_build_system"] for task in pool["tasks"]) == {
        "cmake": 2,
        "make": 2,
        "autotools": 2,
    }
    assert len({task["project_family"] for task in pool["tasks"]}) == 6
    assert manifest["authorization"]["credential_read"] is False
    assert manifest["authorization"]["provider_calls"] is False
    assert manifest["authorization"]["jev_calls"] is False
    assert manifest["authorization"]["agent_calls"] is False
    assert manifest["authorization"]["model_tokens"] == 0
    assert manifest["authorization"]["controller_implementation"] is False
    assert manifest["decision_rule"]["threshold_adjustment_after_results"] is False


def test_state_input_hides_fault_identity_but_exposes_progress() -> None:
    task = qualification.generate_source_pool()["tasks"][0]
    states = [qualification._state_record(task, fault, "shared real build failure") for fault in qualification.FAULT_TYPES]

    for state in states:
        payload = json.dumps(state["model_input"], ensure_ascii=False).lower()
        assert [action["action_family"] for action in state["candidate_actions"]] == list(qualification.ACTION_FAMILIES)
        assert "progress_facts" in state["model_input"]
        for fault in qualification.FAULT_TYPES:
            assert fault not in payload
            assert fault not in state["state_id"]

    compound = states[qualification.FAULT_TYPES.index("compound_recovery")]
    invalid = states[qualification.FAULT_TYPES.index("invalid_build_state")]
    assert compound["semantic_failure_log"] == invalid["semantic_failure_log"]
    assert compound["progress_facts"] != invalid["progress_facts"]


def test_matched_budget_selects_direct_escalate_or_stop() -> None:
    direct_safe = ["dependency", "escalate_agent"]
    agent_only = ["escalate_agent"]

    assert qualification._select_route(direct_safe, qualification.BUDGET_PROFILES["critical"])[:2] == ("stop", None)
    assert qualification._select_route(direct_safe, qualification.BUDGET_PROFILES["local_only"])[:2] == ("direct", "dependency")
    assert qualification._select_route(direct_safe, qualification.BUDGET_PROFILES["agent_capable"])[:2] == ("direct", "dependency")

    assert qualification._select_route(agent_only, qualification.BUDGET_PROFILES["critical"])[:2] == ("stop", None)
    assert qualification._select_route(agent_only, qualification.BUDGET_PROFILES["local_only"])[:2] == ("stop", None)
    assert qualification._select_route(agent_only, qualification.BUDGET_PROFILES["agent_capable"])[:2] == ("escalate_agent", "escalate_agent")


def test_replay_recovery_recipe_adds_missing_generation_step() -> None:
    for task in qualification.generate_source_pool()["tasks"]:
        rejected = qualification._replay_task(task, include_recovery=False)
        repaired = qualification._replay_task(task, include_recovery=True)

        assert rejected["configure_commands"] == task["replay_configure_commands"]
        assert repaired["configure_commands"] == [
            *task["replay_setup_commands"],
            *task["replay_configure_commands"],
        ]
        assert rejected["build_commands"] == repaired["build_commands"]
        assert qualification.MARKER_HEADER not in "\n".join(rejected["configure_commands"][:1]) or task["selected_build_system"] == "cmake"


def test_action_labels_use_two_strict_replicates_and_frozen_cost() -> None:
    task = qualification.generate_source_pool()["tasks"][0]
    states = [qualification._state_record(task, fault, f"log-{index}") for index, fault in enumerate(qualification.FAULT_TYPES)]
    safe = {
        states[0]["state_id"]: {"dependency", "escalate_agent"},
        states[1]["state_id"]: {"configure", "escalate_agent"},
        states[2]["state_id"]: set(qualification.ACTION_FAMILIES),
        states[3]["state_id"]: {"escalate_agent"},
        states[4]["state_id"]: {"dependency", "escalate_agent"},
    }
    outcomes = []
    for state in states:
        for action in qualification.ACTION_FAMILIES:
            strict_success = action in safe[state["state_id"]]
            signature = {
                "action_family": action,
                "action_exit_class": "success" if strict_success else "failure",
                "continuation_exit_class": "success" if strict_success else "not_run",
                "strict_success": strict_success,
                "strict_failure_class": None if strict_success else "candidate",
            }
            for replicate in (1, 2):
                outcomes.append(
                    {
                        "state_id": state["state_id"],
                        "action_family": action,
                        "replicate": replicate,
                        "strict_success": strict_success,
                        "replay_signature": signature,
                    }
                )

    labels, replay = qualification._derive_action_labels(states, outcomes)

    assert [row["optimal_action"] for row in labels] == [
        "dependency",
        "configure",
        "build",
        "escalate_agent",
        "dependency",
    ]
    assert replay["replay_consistency"] == 1.0


def test_prefreeze_exclusions_have_no_formal_outcome() -> None:
    exclusions = qualification.generate_source_pool()["selection_audit"]["excluded_before_freeze"]

    assert {row["project_family"] for row in exclusions} == {
        "github.com/rxi/log.c",
        "github.com/tidwall/hashmap.c",
        "github.com/ebiggers/libdeflate",
    }
    assert all(row["formal_outcome_observed"] is False for row in exclusions)


def test_completed_report_rebuilds_decision_when_present() -> None:
    if not qualification.DEFAULT_JSON_REPORT.exists():
        pytest.skip("正式 qualification 尚未执行")
    manifest, pool = qualification.load_contract()
    report = qualification.validate_report(
        qualification.v1.load_json(qualification.DEFAULT_JSON_REPORT),
        manifest,
        pool,
    )

    assert report["analysis"]["counts"]["state_count"] == 30
    assert report["analysis"]["counts"]["action_branch_count"] == 240
    assert report["analysis"]["counts"]["budget_decision_count"] == 90
    assert qualification.render_markdown(report) == qualification.DEFAULT_MARKDOWN_REPORT.read_text(encoding="utf-8")


@pytest.mark.skipif(
    os.getenv("FORGE_RUN_PROGRESS_BUDGET_JEV_DOCKER") != "1",
    reason="需要显式启用 Docker 集成门禁",
)
def test_docker_preflight_uses_frozen_image_and_zero_provider() -> None:
    manifest, pool = qualification.load_contract()

    result = qualification.preflight(manifest, pool, require_clean=False)

    assert result["ready"] is True
    assert result["project_count"] == 6
    assert result["state_count"] == 30
    assert result["action_branch_count"] == 240
    assert result["budget_decision_count"] == 90
    assert result["provider_calls"] == 0
    assert result["credential_reads"] == 0
    assert result["jev_calls"] == 0
    assert result["agent_calls"] == 0
    assert result["model_tokens"] == 0
