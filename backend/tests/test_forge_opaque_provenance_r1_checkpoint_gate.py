"""Issue #198 yyjson R1 checkpoint adapter 的零 provider 静态门禁。"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
SCRIPT_PATH = SCRIPTS_DIR / "forge_opaque_provenance_r1_checkpoint_gate.py"


def _load_module():
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location("forge_opaque_provenance_r1_checkpoint_gate_test", SCRIPT_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


gate = _load_module()


def _frozen():
    return gate.build_frozen_identity(
        image_id="sha256:" + "2" * 64,
        physical_attempt_id="attempt-r1-static-test",
        build_tree_sha256="3" * 64,
        artifact_size=4096,
        artifact_sha256="4" * 64,
    )


def test_case_is_exactly_inherited_from_r1_candidate() -> None:
    manifest = gate.candidate_protocol.load_manifest()
    assert gate.CANDIDATE_MANIFEST_SHA256 == gate.candidate_protocol.canonical_sha256(manifest)
    assert gate.CASE_ID == "yyjson-opaque-provenance-r1"
    assert gate.REPOSITORY_URL == "https://github.com/ibireme/yyjson"
    assert gate.COMMIT_SHA == "9365ddc7061033df656578bf86040048b5b5531a"
    assert gate.BUILD_DIRECTORY == "/workspace/repo/build"
    assert gate.TARGET == "yyjson"
    assert gate.BUILD_OUTPUT == "build/libyyjson.a"
    assert gate.STAGED_ARTIFACT == "libyyjson.a"
    assert gate.ARTIFACT_TYPE == "static_library"
    assert list(gate.CONFIGURE_ARGUMENTS) == manifest["case"]["configure_arguments"]


def test_parent_wrapper_is_replayable_but_does_not_prove_cmake_identity() -> None:
    assert gate.validate_parent_command_contract() == {
        "roles": ["artifact_stage", "build", "configure"],
        "top_level_executable": "sh",
        "cmake_identity_proven": False,
        "self_contained_replay_step": True,
    }
    assert "cmake -S . -B build -G Ninja" in gate.PARENT_COMMAND
    assert "cmake --build build --target yyjson" in gate.PARENT_COMMAND
    assert "cp build/libyyjson.a /artifacts/libyyjson.a" in gate.PARENT_COMMAND


def test_repair_packet_is_case_bound_and_does_not_leak_a_command() -> None:
    packet = gate.validate_repair_packet(gate.build_repair_packet())
    assert packet == gate.candidate_protocol.load_manifest()["repair_packet"]["template"]
    assert packet["build_directory"] == gate.BUILD_DIRECTORY
    assert packet["target"] == gate.TARGET
    serialized = json.dumps(packet, sort_keys=True).lower()
    for forbidden in ("cmake --build", "sh -c", "argv", "api_key"):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(command="cmake --build build"),
        lambda value: value.update(build_directory="/workspace/repo/other"),
        lambda value: value.update(target="other"),
    ],
)
def test_repair_packet_drift_fails_closed(mutation) -> None:
    packet = gate.build_repair_packet()
    mutation(packet)
    with pytest.raises(gate.CheckpointGateError, match="identity or whitelist drifted"):
        gate.validate_repair_packet(packet)


def test_parent_is_unproven_and_future_treatment_contract_is_append_only() -> None:
    frozen = _frozen()
    parent, parent_history = gate.evaluate_parent(frozen, parent_command_id="parent-wrapper")
    treatment, treatment_history = gate.evaluate_treatment(
        frozen,
        parent_command_id="parent-wrapper",
        treatment_build_command_id="treatment-build",
        treatment_stage_command_id="treatment-stage",
    )
    assert parent.status == "unproven"
    assert parent.classification == "opaque_build_provenance"
    assert parent.reason == "opaque_wrapper"
    assert treatment.status == "proven"
    assert treatment.proof_mode == "direct_cmake"
    assert treatment_history[: len(parent_history)] == parent_history


def test_artifact_identity_drift_fails_closed() -> None:
    with pytest.raises(gate.CheckpointGateError, match="R1 frozen case identity drifted"):
        gate.evaluate_parent(replace(_frozen(), artifact_type="executable"), parent_command_id="parent-wrapper")


def test_r0_observability_is_a_required_zero_provider_gate() -> None:
    report = gate.validate_gate_contract()
    r0 = report["r0_observability"]
    assert r0["companion_event"] == "agent.tool_rejection_observed"
    assert r0["legacy_tool_failed_schema_preserved"] is True
    assert r0["raw_command_persisted"] is False
    assert r0["atomic_fields"] == gate.candidate_protocol.R0_OBSERVATION_FIELDS


def test_cli_reports_zero_external_counts_and_no_checkpoint() -> None:
    completed = subprocess.run([sys.executable, str(SCRIPT_PATH), "validate"], check=True, capture_output=True, text=True)
    report = json.loads(completed.stdout)
    assert report["parent"]["status"] == "unproven"
    assert report["treatment_contract_only"]["status"] == "proven"
    assert report["parent_history_prefix_preserved"] is True
    assert report["checkpoint_created"] is False
    assert report["docker_executed"] is False
    assert report["credential_read"] is False
    assert report["candidate_evidence_writes"] == 0
    assert (report["provider_calls"], report["formal_attempts"], report["model_tokens"]) == (0, 0, 0)


def test_source_has_no_provider_credential_or_formal_execution_entrypoint() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    for forbidden in (
        "create_chat_model",
        "openai_ak",
        "deepseek_api_key",
        "os.getenv",
        "execute_reachability",
        "execute_pair",
        "docker.from_env",
        "benchmark-evidence-opaque-provenance-r1-yyjson-v1",
    ):
        assert forbidden not in source
