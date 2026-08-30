"""Issue #204 Make opaque provenance lifecycle adapter 的静态门禁。"""

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
SCRIPT_PATH = SCRIPTS_DIR / "forge_opaque_provenance_make_lifecycle_gate.py"


def _load_module():
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location(
            "forge_opaque_provenance_make_lifecycle_gate_test",
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
        physical_attempt_id="attempt-r2-make-lifecycle-test",
        artifact_size=4096,
        artifact_sha256="4" * 64,
    )


def test_case_is_exactly_inherited_from_make_reference_gate() -> None:
    report = gate.validate_gate_contract(REPO_ROOT)
    assert gate.file_sha256(REPO_ROOT / gate.REFERENCE_GATE_PATH) == gate.REFERENCE_GATE_SHA256
    assert report["source_case"] == gate.reference.HOEXTDOWN_SOURCE_CASE
    assert report["source_case"]["result_data_consulted"] is False
    assert gate.CASE_ID == "hoextdown-opaque-provenance-r2-make-lifecycle"
    assert gate.REPOSITORY_URL == "https://github.com/kjdev/hoextdown"
    assert gate.COMMIT_SHA == "1ef9a71957570c2a65b7daa1b2f693ad87daf385"
    assert gate.TARGET == gate.BUILD_OUTPUT == gate.STAGED_ARTIFACT == "libhoedown.a"
    assert gate.ARTIFACT_TYPE == "static_library"


def test_parent_wrapper_is_replayable_but_does_not_prove_make_identity() -> None:
    assert gate.validate_parent_command_contract() == {
        "roles": ["artifact_stage", "build", "housekeeping"],
        "top_level_executable": "sh",
        "make_identity_proven": False,
        "self_contained_replay_step": True,
    }
    assert "make clean" in gate.PARENT_COMMAND
    assert "make libhoedown.a -j2" in gate.PARENT_COMMAND
    assert "cp libhoedown.a /artifacts/libhoedown.a" in gate.PARENT_COMMAND


def test_repair_packet_is_make_bound_and_does_not_leak_a_command() -> None:
    packet = gate.validate_repair_packet(gate.build_repair_packet())
    assert packet["expected_build_system"] == packet["selected_build_system"] == "make"
    assert packet["build_directory"] == gate.WORKDIR
    assert packet["target"] == gate.TARGET
    serialized = json.dumps(packet, sort_keys=True).lower()
    for forbidden in ("make libhoedown.a", "sh -c", "argv", "api_key"):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(command="make libhoedown.a"),
        lambda value: value.update(build_directory="/workspace/repo/other"),
        lambda value: value.update(target="other"),
        lambda value: value.update(expected_build_system="cmake"),
    ],
)
def test_repair_packet_drift_fails_closed(mutation) -> None:
    packet = gate.build_repair_packet()
    mutation(packet)
    with pytest.raises(gate.MakeLifecycleGateError, match="identity or whitelist drifted"):
        gate.validate_repair_packet(packet)


def test_parent_is_unproven_and_treatment_is_append_only_direct_make() -> None:
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
    assert treatment.proof_mode == "direct_make"
    assert treatment_history[: len(parent_history)] == parent_history


def test_artifact_identity_drift_fails_closed() -> None:
    with pytest.raises(gate.MakeLifecycleGateError, match="case identity drifted"):
        gate.evaluate_parent(
            replace(_frozen(), artifact_type="executable"),
            parent_command_id="parent-wrapper",
        )


def test_cli_reports_zero_external_counts_and_no_docker() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "validate"],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout)
    assert report["parent"]["status"] == "unproven"
    assert report["treatment_contract"]["proof_mode"] == "direct_make"
    assert report["parent_history_prefix_preserved"] is True
    assert (
        report["provider_calls"],
        report["credential_read"],
        report["docker_executed"],
        report["formal_attempts"],
        report["model_tokens"],
        report["evidence_writes"],
    ) == (0, False, False, 0, 0, 0)


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
        "benchmark-evidence-opaque-provenance-r1",
    ):
        assert forbidden not in source
