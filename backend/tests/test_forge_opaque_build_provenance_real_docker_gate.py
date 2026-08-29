"""Issue #178 真实 Docker gate adapter 的零 provider 静态门禁。"""

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
SCRIPT_PATH = SCRIPTS_DIR / "forge_opaque_build_provenance_real_docker_gate.py"


def _load_module():
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location(
            "forge_opaque_build_provenance_real_docker_gate_test",
            SCRIPT_PATH,
        )
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
        physical_attempt_id="attempt-static-test",
        build_tree_sha256="3" * 64,
        artifact_size=4096,
        artifact_sha256="4" * 64,
    )


def test_parent_wrapper_is_replayable_but_does_not_prove_cmake_identity() -> None:
    result = gate.validate_parent_command_contract()
    assert result == {
        "roles": ["artifact_stage", "build", "configure"],
        "top_level_executable": "sh",
        "cmake_identity_proven": False,
        "self_contained_replay_step": True,
    }
    assert "cmake -S examples" in gate.PARENT_COMMAND
    assert "cmake --build build" in gate.PARENT_COMMAND
    assert "/artifacts/accumulate_examples" in gate.PARENT_COMMAND


def test_repair_packet_is_whitelisted_and_does_not_leak_a_command() -> None:
    packet = gate.validate_repair_packet(gate.build_repair_packet())
    assert packet["proof_status"] == "opaque_wrapper"
    assert packet["build_directory"] == "/workspace/repo/build"
    serialized = json.dumps(packet, sort_keys=True).lower()
    for forbidden in ("cmake --build", "sh -c", "argv", "api_key"):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(command="cmake --build build"),
        lambda value: value.update(build_directory="/workspace/repo/other"),
        lambda value: value.update(proof_status="proven"),
    ],
)
def test_repair_packet_drift_fails_closed(mutation) -> None:
    packet = gate.build_repair_packet()
    mutation(packet)
    with pytest.raises(gate.RealDockerGateError, match="identity or whitelist drifted"):
        gate.validate_repair_packet(packet)


def test_parent_p2_is_unproven_and_treatment_is_append_only_proven() -> None:
    frozen = _frozen()
    parent, parent_history = gate.evaluate_parent(
        frozen,
        parent_command_id="parent-wrapper",
    )
    treatment, treatment_history = gate.evaluate_treatment(
        frozen,
        parent_command_id="parent-wrapper",
        treatment_build_command_id="treatment-build",
        treatment_stage_command_id="treatment-stage",
    )
    assert parent.status == "unproven"
    assert parent.classification == gate.provenance.FAULT_FAMILY
    assert parent.reason == "opaque_wrapper"
    assert treatment.status == "proven"
    assert treatment.proof_mode == "direct_cmake"
    assert treatment_history[: len(parent_history)] == parent_history
    assert gate.provenance.command_history_sha256(treatment_history) != gate.provenance.command_history_sha256(parent_history)


def test_identity_drift_fails_closed() -> None:
    frozen = _frozen()
    with pytest.raises(gate.provenance.ProvenanceContractError, match="frozen artifact identity is invalid"):
        gate.evaluate_parent(
            replace(frozen, artifact_size=0),
            parent_command_id="parent-wrapper",
        )


def test_cli_reports_zero_external_counts_and_no_docker_execution() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "validate"],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert result["parent"]["status"] == "unproven"
    assert result["treatment"]["status"] == "proven"
    assert result["parent_history_prefix_preserved"] is True
    assert result["docker_executed"] is False
    assert (result["provider_calls"], result["formal_attempts"], result["model_tokens"]) == (0, 0, 0)


def test_source_does_not_access_provider_credentials_or_formal_runner() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    for forbidden in (
        "create_chat_model",
        "openai_ak",
        "deepseek_api_key",
        "os.getenv",
        "import docker",
        "docker.from_env",
        "execute_collection",
    ):
        assert forbidden not in source
