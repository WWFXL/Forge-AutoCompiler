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

import forge_typed_semantic_routing_pilot_v2 as pilot  # noqa: E402


def test_generated_contract_is_frozen_balanced_and_zero_provider() -> None:
    pool = pilot.generate_source_pool()
    manifest = pilot.generate_manifest(pool)

    assert pool == pilot.v1.load_json(pilot.DEFAULT_SOURCE_POOL)
    assert manifest == pilot.v1.load_json(pilot.DEFAULT_MANIFEST)
    assert pilot.generate_schema(manifest) == pilot.v1.load_json(pilot.DEFAULT_SCHEMA)
    assert Counter(task["selected_build_system"] for task in pool["tasks"]) == {
        "cmake": 2,
        "make": 2,
        "autotools": 2,
    }
    assert len({task["project_family"] for task in pool["tasks"]}) == 6
    v1_ids = {task["task_id"] for task in pilot.v1.load_json(pilot.V1_SOURCE_POOL)["tasks"]}
    assert not ({task["task_id"] for task in pool["tasks"]} & v1_ids)
    assert manifest["authorization"]["provider_calls_authorized"] is False
    assert manifest["authorization"]["credential_read_authorized"] is False
    assert manifest["authorization"]["model_calls_authorized"] is False
    assert manifest["authorization"]["model_tokens_authorized"] == 0
    assert manifest["benchmark_design"]["old_agent_action_is_ground_truth"] is False
    assert manifest["decision_rule"]["threshold_adjustment_after_results"] is False


def test_model_inputs_hold_phase_facts_constant_and_do_not_leak_fault_identity() -> None:
    task = pilot.generate_source_pool()["tasks"][0]
    states = [pilot._state_record(task, fault, "compiler diagnostic text") for fault in pilot.FAULT_TYPES]

    assert len({pilot.v1.canonical_sha256(state["phase_facts"]) for state in states}) == 1
    assert all(state["phase_facts"] == pilot.EXPECTED_PHASE_FACTS for state in states)
    assert all("fault" not in state for state in states)
    assert all([action["action_family"] for action in state["candidate_actions"]] == list(pilot.ACTION_FAMILIES) for state in states)
    command_hashes = {pilot.v1.canonical_sha256([action["bound_commands"] for action in state["candidate_actions"]]) for state in states}
    assert len(command_hashes) == 1
    for state in states:
        payload = json.dumps(state["model_input"], sort_keys=True)
        commands = json.dumps([action["bound_commands"] for action in state["candidate_actions"]], sort_keys=True)
        for fault in pilot.FAULT_TYPES:
            assert fault not in payload
            assert fault not in state["state_id"]
            assert fault not in commands
        assert task["task_id"] not in state["state_id"]


def test_fault_triggers_use_opaque_wrong_target_and_real_build_inputs() -> None:
    for task in pilot.generate_source_pool()["tasks"]:
        missing = pilot._fault_trigger_command(task, "missing_compile_input")
        invalid = pilot._fault_trigger_command(task, "invalid_build_state")
        wrong = pilot._fault_trigger_command(task, "wrong_build_target")

        assert task["fault_file"] in missing
        assert "missing_compile_input" not in missing
        assert "invalid_build_state" not in invalid
        assert pilot.OPAQUE_TARGET in wrong
        assert "wrong_build_target" not in wrong


def test_labels_are_derived_from_strict_outcomes_then_frozen_cost() -> None:
    task = pilot.generate_source_pool()["tasks"][0]
    states = [pilot._state_record(task, fault, f"log {index}") for index, fault in enumerate(pilot.FAULT_TYPES)]
    successful = {
        states[0]["state_id"]: {"dependency", "escalate_agent"},
        states[1]["state_id"]: {"configure", "escalate_agent"},
        states[2]["state_id"]: set(pilot.ACTION_FAMILIES),
    }
    outcomes = []
    for state in states:
        for family in pilot.ACTION_FAMILIES:
            strict_success = family in successful[state["state_id"]]
            signature = {
                "action_family": family,
                "action_exit_class": "success" if strict_success else "failure",
                "continuation_exit_class": "success" if strict_success else "not_run",
                "strict_success": strict_success,
            }
            for replicate in (1, 2):
                outcomes.append(
                    {
                        "state_id": state["state_id"],
                        "action_family": family,
                        "replicate": replicate,
                        "strict_success": strict_success,
                        "replay_signature": signature,
                    }
                )

    labels, replay = pilot._derive_labels(states, outcomes)

    assert {row["state_id"]: row["optimal_action"] for row in labels} == {
        states[0]["state_id"]: "dependency",
        states[1]["state_id"]: "configure",
        states[2]["state_id"]: "build",
    }
    assert replay == {
        "state_action_pair_count": 12,
        "consistent_state_action_pair_count": 12,
        "replay_consistency": 1.0,
    }


def test_selection_exclusions_are_prefreeze_and_result_blind() -> None:
    pool = pilot.generate_source_pool()
    exclusions = {row["task_id"]: row for row in pool["selection_audit"]["excluded_before_freeze"]}

    assert set(exclusions) == {"libcheck", "jpegoptim", "libusb"}
    assert all(row["outcome_matrix_observed"] is False for row in exclusions.values())
    assert exclusions["libusb"]["reason"] == "git_archive_clean_replay_version_string_is_not_bitwise_stable"


def test_tfidf_baseline_supports_frozen_three_class_one_vs_rest() -> None:
    states = []
    labels = []
    for project_index in range(6):
        project_family = f"example.test/project-{project_index}"
        build_system = pilot.BUILD_SYSTEMS[project_index % 3]
        for class_index, action in enumerate(("dependency", "configure", "build")):
            state_id = f"s-{project_index}-{class_index}"
            states.append(
                {
                    "state_id": state_id,
                    "project_family": project_family,
                    "build_system": build_system,
                    "semantic_failure_log": f"shared compiler diagnostic classword{class_index}",
                }
            )
            labels.append({"state_id": state_id, "optimal_action": action})

    result = pilot._tfidf_baseline(states, labels)

    assert result["state_count"] == 18
    assert result["top1_accuracy"] == 1.0


@pytest.mark.skipif(os.getenv("FORGE_RUN_SEMANTIC_ROUTING_DOCKER") != "1", reason="需要显式启用 Docker 集成门禁")
def test_docker_preflight_uses_frozen_image_and_zero_provider() -> None:
    manifest, pool = pilot.load_contract()

    result = pilot.preflight(manifest, pool, require_clean=False)

    assert result["ready"] is True
    assert result["task_count"] == 6
    assert result["expected_state_count"] == 18
    assert result["expected_action_branch_count"] == 144
    assert result["provider_calls"] == 0
    assert result["credential_reads"] == 0
    assert result["model_calls"] == 0
    assert result["model_tokens"] == 0
