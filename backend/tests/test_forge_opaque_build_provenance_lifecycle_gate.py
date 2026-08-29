"""Issue #176 opaque build provenance 生命周期适配的零 provider 门禁。"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
SCRIPT_PATH = SCRIPTS_DIR / "forge_opaque_build_provenance_lifecycle_gate.py"


def _load_module():
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location("forge_opaque_build_provenance_lifecycle_gate_test", SCRIPT_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


gate = _load_module()


def test_parent_checkpoint_is_single_unproven_pre_replay_identity() -> None:
    checkpoint = gate.build_failure_checkpoint()
    assert checkpoint.validate() is checkpoint
    assert checkpoint.decision.status == "unproven"
    assert checkpoint.decision.classification == gate.provenance.FAULT_FAMILY
    assert checkpoint.decision.reason == gate.PROOF_STATUS
    assert checkpoint.replay_attempts == 0
    assert checkpoint.parent_history_sha256 == gate.provenance.command_history_sha256(checkpoint.invocations)


def test_arms_share_one_checkpoint_and_only_treatment_receives_packet() -> None:
    checkpoint = gate.build_failure_checkpoint()
    arms = gate.derive_arms(checkpoint)
    gate.validate_arm_pair(checkpoint, arms)
    baseline = arms[gate.BASELINE_ARM]
    treatment = arms[gate.TREATMENT_ARM]
    assert baseline.parent_checkpoint_sha256 == treatment.parent_checkpoint_sha256 == checkpoint.checkpoint_sha256
    assert baseline.common_state_sha256 == treatment.common_state_sha256
    assert "repair_packet" not in baseline.feedback
    assert {key: value for key, value in treatment.feedback.items() if key != "repair_packet"} == baseline.feedback


def test_repair_packet_is_whitelisted_and_does_not_leak_a_complete_command() -> None:
    checkpoint = gate.build_failure_checkpoint()
    packet = asdict(gate.build_repair_packet(checkpoint.frozen))
    assert gate.validate_repair_packet(packet, checkpoint.frozen).proof_status == gate.PROOF_STATUS
    serialized = json.dumps(packet, sort_keys=True).lower()
    for forbidden in ("cmake --build", "ninja -c", "bash -lc", "argv", "command_line", "shell"):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update(command="cmake --build /workspace/repo/build"), "field set drifted"),
        (lambda value: value.update(build_directory="/workspace/repo/other"), "identity or whitelist drifted"),
        (lambda value: value.update(target="other"), "identity or whitelist drifted"),
        (lambda value: value.update(proof_status="proven"), "identity or whitelist drifted"),
    ],
)
def test_repair_packet_drift_fails_closed(mutation, message: str) -> None:
    checkpoint = gate.build_failure_checkpoint()
    packet = asdict(gate.build_repair_packet(checkpoint.frozen))
    mutation(packet)
    with pytest.raises(gate.LifecycleGateError, match=message):
        gate.validate_repair_packet(packet, checkpoint.frozen)


def test_baseline_remains_unproven_without_candidate_or_replay() -> None:
    checkpoint = gate.build_failure_checkpoint()
    arm = gate.derive_arms(checkpoint)[gate.BASELINE_ARM]
    observers = gate.ContractObservers()
    outcome = gate.run_arm(checkpoint, arm, observers)
    assert outcome.p2_decision.status == "unproven"
    assert outcome.p2_decision.reason == gate.PROOF_STATUS
    assert outcome.appended_command_ids == ()
    assert outcome.candidate_status == "not_run"
    assert outcome.clean_replay_status == "not_run"
    assert outcome.cleanup_status == "passed"
    assert observers.calls == ["cleanup"]


def test_treatment_appends_trusted_invocation_and_closes_observed_lifecycle() -> None:
    checkpoint = gate.build_failure_checkpoint()
    arm = gate.derive_arms(checkpoint)[gate.TREATMENT_ARM]
    observers = gate.ContractObservers()
    outcome = gate.run_arm(checkpoint, arm, observers)
    assert outcome.p2_decision.status == "proven"
    assert outcome.p2_decision.proof_mode == "direct_cmake"
    assert outcome.parent_history_sha256 == checkpoint.parent_history_sha256
    assert outcome.appended_command_ids == ("continuation-trusted-cmake-build",)
    assert outcome.continuation_history_sha256 != checkpoint.parent_history_sha256
    assert (outcome.candidate_status, outcome.clean_replay_status, outcome.cleanup_status) == ("passed", "passed", "passed")
    assert observers.calls == ["candidate", "clean_replay", "cleanup"]
    assert len(outcome.observation_subject_sha256) == 64


def test_baseline_rejects_treatment_packet_leakage() -> None:
    checkpoint = gate.build_failure_checkpoint()
    baseline = gate.derive_arms(checkpoint)[gate.BASELINE_ARM]
    feedback = copy.deepcopy(baseline.feedback)
    feedback["repair_packet"] = asdict(gate.build_repair_packet(checkpoint.frozen))
    with pytest.raises(gate.LifecycleGateError, match="baseline arm was exposed"):
        replace(baseline, feedback=feedback).validate(checkpoint)


@pytest.mark.parametrize(
    ("fail_at", "expected_calls", "message"),
    [
        ("candidate", ["candidate", "cleanup"], "candidate observer failed closed"),
        ("clean_replay", ["candidate", "clean_replay", "cleanup"], "clean replay observer failed closed"),
        ("cleanup", ["candidate", "clean_replay", "cleanup"], "cleanup observer failed closed"),
    ],
)
def test_observer_failure_blocks_later_stages_and_cleanup_still_runs(fail_at: str, expected_calls: list[str], message: str) -> None:
    checkpoint = gate.build_failure_checkpoint()
    treatment = gate.derive_arms(checkpoint)[gate.TREATMENT_ARM]
    observers = gate.ContractObservers(fail_at=fail_at)
    with pytest.raises(gate.LifecycleGateError, match=message):
        gate.run_arm(checkpoint, treatment, observers)
    assert observers.calls == expected_calls


def test_observer_result_from_another_subject_fails_closed() -> None:
    class UnboundCandidateObservers(gate.ContractObservers):
        def candidate(self, subject_sha256: str):
            result = super().candidate(subject_sha256)
            return replace(result, subject_sha256="7" * 64)

    checkpoint = gate.build_failure_checkpoint()
    treatment = gate.derive_arms(checkpoint)[gate.TREATMENT_ARM]
    observers = UnboundCandidateObservers()
    with pytest.raises(gate.LifecycleGateError, match="candidate observer subject identity drifted"):
        gate.run_arm(checkpoint, treatment, observers)
    assert observers.calls == ["candidate", "cleanup"]


def test_parent_ledger_and_artifact_drift_fail_closed() -> None:
    checkpoint = gate.build_failure_checkpoint()
    bad_invocation = replace(checkpoint.invocations[-1], ledger_hash="9" * 64)
    with pytest.raises(gate.LifecycleGateError, match="checkpoint P2 evidence is invalid"):
        replace(checkpoint, invocations=(checkpoint.invocations[0], bad_invocation)).validate()
    with pytest.raises(gate.LifecycleGateError, match="checkpoint P2 evidence is invalid"):
        replace(checkpoint, artifact=replace(checkpoint.artifact, sha256="8" * 64)).validate()


def test_cli_reports_contract_observation_boundary_and_zero_counts() -> None:
    completed = subprocess.run([sys.executable, str(SCRIPT_PATH), "validate"], check=True, capture_output=True, text=True)
    result = json.loads(completed.stdout)
    assert result["arm_common_state_equal"] is True
    assert result["treatment_exposure_only"] == "repair_packet"
    assert result["baseline"]["p2_decision"]["status"] == "unproven"
    assert result["treatment"]["p2_decision"]["status"] == "proven"
    assert result["treatment"]["observer_order"] == ["candidate", "clean_replay", "cleanup"]
    assert result["observation_mode"] == "deterministic_contract_callback"
    assert result["docker_executed"] is False
    assert (result["provider_calls"], result["formal_attempts"], result["model_tokens"]) == (0, 0, 0)


def test_source_does_not_access_provider_docker_or_production_lifecycle() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for forbidden in ("create_chat_model", "deepseek_api_key", "openai_ak", "import docker", "docker.from_env", "compile.operations", "forge_real_lifecycle_checkpoint_gate"):
        assert forbidden not in source.lower()
