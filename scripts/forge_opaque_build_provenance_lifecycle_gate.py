#!/usr/bin/env python3
"""Issue #176 opaque build provenance 的零 provider 生命周期门禁。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Any

import forge_opaque_build_provenance_gate as provenance

SCHEMA_VERSION = "forge-opaque-build-provenance-lifecycle-gate-1.0.0"
PACKET_SCHEMA_VERSION = "forge-opaque-build-provenance-repair-packet-1.0.0"
BASELINE_ARM = "baseline"
TREATMENT_ARM = "treatment"
ARMS = (BASELINE_ARM, TREATMENT_ARM)
REPAIR_GOAL = "Execute and record a trusted build bound to the frozen build tree, then resubmit."
PROOF_STATUS = "missing_trusted_generator_link"
SESSION_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,95}$")
FORBIDDEN_PACKET_FIELDS = frozenset({"argv", "command", "command_line", "prompt", "shell", "solution"})


class LifecycleGateError(RuntimeError):
    """生命周期 checkpoint、packet 或 observer 契约无效。"""


def canonical_sha256(value: Any) -> str:
    return provenance.canonical_sha256(value)


@dataclass(frozen=True)
class FailureCheckpoint:
    """失败 submit 后、continuation 前冻结的单一 P2 checkpoint。"""

    schema_version: str
    checkpoint_id: str
    frozen: provenance.FrozenIdentity
    invocations: tuple[provenance.InvocationEvidence, ...]
    artifact: provenance.ArtifactIdentity
    decision: provenance.ProvenanceDecision
    parent_history_sha256: str
    neutral_feedback: dict[str, Any]
    neutral_feedback_sha256: str
    replay_attempts: int

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "checkpoint_id": self.checkpoint_id,
            "frozen": asdict(self.frozen),
            "invocations": [asdict(item) for item in self.invocations],
            "artifact": asdict(self.artifact),
            "decision": asdict(self.decision),
            "parent_history_sha256": self.parent_history_sha256,
            "neutral_feedback": copy.deepcopy(self.neutral_feedback),
            "neutral_feedback_sha256": self.neutral_feedback_sha256,
            "replay_attempts": self.replay_attempts,
        }

    @property
    def checkpoint_sha256(self) -> str:
        return canonical_sha256(self.payload())

    def validate(self) -> FailureCheckpoint:
        if self.schema_version != SCHEMA_VERSION or not SESSION_PATTERN.fullmatch(self.checkpoint_id):
            raise LifecycleGateError("checkpoint identity is invalid")
        try:
            decision = provenance.evaluate_p2(self.frozen, self.invocations, self.artifact)
            history_sha256 = provenance.command_history_sha256(self.invocations)
        except provenance.ProvenanceContractError as exc:
            raise LifecycleGateError("checkpoint P2 evidence is invalid") from exc
        if decision != self.decision or (decision.status, decision.classification, decision.reason) != (
            "unproven",
            provenance.FAULT_FAMILY,
            PROOF_STATUS,
        ):
            raise LifecycleGateError("checkpoint is not the frozen opaque provenance failure")
        if history_sha256 != self.parent_history_sha256:
            raise LifecycleGateError("checkpoint parent history identity drifted")
        if self.neutral_feedback_sha256 != canonical_sha256(self.neutral_feedback):
            raise LifecycleGateError("checkpoint neutral feedback identity drifted")
        expected_feedback = {
            "status": "failed",
            "submit_attempt_id": "submit-opaque-provenance-1",
            "primary_classification": provenance.EXPECTED_CLASSIFICATION,
            "mechanism_classification": provenance.FAULT_FAMILY,
            "proof_status": PROOF_STATUS,
            "p2_status": "unproven",
            "replay_attempts": 0,
        }
        if self.neutral_feedback != expected_feedback or self.replay_attempts != 0:
            raise LifecycleGateError("checkpoint submit or replay identity drifted")
        return self


@dataclass(frozen=True)
class RepairPacket:
    """Treatment 唯一允许附加的白名单 provenance repair 信息。"""

    schema_version: str
    primary_classification: str
    mechanism_classification: str
    expected_build_system: str
    selected_build_system: str
    build_directory: str
    target: str
    proof_status: str
    repair_goal: str

    def validate(self, frozen: provenance.FrozenIdentity) -> RepairPacket:
        expected = {
            "schema_version": PACKET_SCHEMA_VERSION,
            "primary_classification": provenance.EXPECTED_CLASSIFICATION,
            "mechanism_classification": provenance.FAULT_FAMILY,
            "expected_build_system": "cmake",
            "selected_build_system": "cmake",
            "build_directory": frozen.build_directory,
            "target": frozen.target,
            "proof_status": PROOF_STATUS,
            "repair_goal": REPAIR_GOAL,
        }
        if asdict(self) != expected:
            raise LifecycleGateError("repair packet identity or whitelist drifted")
        lowered = self.repair_goal.lower()
        if "cmake --build" in lowered or "ninja -c" in lowered or "bash -lc" in lowered:
            raise LifecycleGateError("repair packet leaked a complete command")
        return self


@dataclass(frozen=True)
class ArmCheckpoint:
    schema_version: str
    arm: str
    session_id: str
    parent_checkpoint_sha256: str
    common_state_sha256: str
    feedback: dict[str, Any]

    def validate(self, checkpoint: FailureCheckpoint) -> ArmCheckpoint:
        checkpoint.validate()
        if self.schema_version != SCHEMA_VERSION or self.arm not in ARMS or not SESSION_PATTERN.fullmatch(self.session_id):
            raise LifecycleGateError("arm checkpoint identity is invalid")
        if self.parent_checkpoint_sha256 != checkpoint.checkpoint_sha256 or self.common_state_sha256 != checkpoint.checkpoint_sha256:
            raise LifecycleGateError("arm checkpoint is not derived from the frozen parent")
        neutral = checkpoint.neutral_feedback
        if self.arm == BASELINE_ARM:
            if self.feedback != neutral or "repair_packet" in self.feedback:
                raise LifecycleGateError("baseline arm was exposed to a repair packet")
        else:
            without_packet = {key: value for key, value in self.feedback.items() if key != "repair_packet"}
            if without_packet != neutral or set(self.feedback) != set(neutral) | {"repair_packet"}:
                raise LifecycleGateError("treatment feedback differs outside the repair packet")
            validate_repair_packet(self.feedback["repair_packet"], checkpoint.frozen)
        return self


@dataclass(frozen=True)
class ObserverResult:
    stage: str
    status: str
    observation_id: str
    subject_sha256: str
    mode: str = "deterministic_contract_callback"

    def validate(self, expected_stage: str, expected_subject_sha256: str) -> ObserverResult:
        if self.stage != expected_stage or self.status not in {"passed", "failed"} or not SESSION_PATTERN.fullmatch(self.observation_id):
            raise LifecycleGateError(f"{expected_stage} observer returned an invalid result")
        if self.subject_sha256 != expected_subject_sha256:
            raise LifecycleGateError(f"{expected_stage} observer subject identity drifted")
        if self.mode != "deterministic_contract_callback":
            raise LifecycleGateError(f"{expected_stage} observer mode drifted")
        return self


@dataclass(frozen=True)
class ArmOutcome:
    schema_version: str
    arm: str
    p2_decision: provenance.ProvenanceDecision
    parent_history_sha256: str
    continuation_history_sha256: str
    appended_command_ids: tuple[str, ...]
    candidate_status: str
    clean_replay_status: str
    cleanup_status: str
    observer_order: tuple[str, ...]
    observation_subject_sha256: str


class ContractObservers:
    """记录 lifecycle 顺序的确定性 observer；不执行 Docker 或真实 verifier。"""

    def __init__(self, *, fail_at: str | None = None) -> None:
        if fail_at not in {None, "candidate", "clean_replay", "cleanup"}:
            raise LifecycleGateError("unknown observer failure stage")
        self.fail_at = fail_at
        self.calls: list[str] = []

    def _observe(self, stage: str, subject_sha256: str) -> ObserverResult:
        self.calls.append(stage)
        return ObserverResult(stage, "failed" if self.fail_at == stage else "passed", f"{stage.replace('_', '-')}-observation", subject_sha256)

    def candidate(self, subject_sha256: str) -> ObserverResult:
        return self._observe("candidate", subject_sha256)

    def clean_replay(self, subject_sha256: str) -> ObserverResult:
        return self._observe("clean_replay", subject_sha256)

    def cleanup(self, subject_sha256: str) -> ObserverResult:
        return self._observe("cleanup", subject_sha256)


def validate_repair_packet(value: Any, frozen: provenance.FrozenIdentity) -> RepairPacket:
    if not isinstance(value, dict) or set(value) != set(RepairPacket.__dataclass_fields__):
        raise LifecycleGateError("repair packet field set drifted")
    if any(key in FORBIDDEN_PACKET_FIELDS for key in value):
        raise LifecycleGateError("repair packet contains a forbidden solution field")
    try:
        packet = RepairPacket(**value)
    except TypeError as exc:
        raise LifecycleGateError("repair packet cannot be parsed") from exc
    return packet.validate(frozen)


def build_failure_checkpoint() -> FailureCheckpoint:
    artifact_bytes = b"synthetic-cmake-artifact-v1"
    frozen = provenance.FrozenIdentity(
        schema_version=provenance.SCHEMA_VERSION,
        case_id="cmake-opaque-provenance-lifecycle-case",
        repository_url="https://github.com/example/opaque-provenance-fixture.git",
        commit_sha="1" * 40,
        image_id="sha256:" + "2" * 64,
        physical_attempt_id="attempt-lifecycle-parent",
        workdir="/workspace/repo",
        build_directory="/workspace/repo/build",
        generator="Ninja",
        build_tree_sha256="3" * 64,
        target="fixture",
        artifact_relative_path="build/fixture",
        artifact_type="executable",
        artifact_size=len(artifact_bytes),
        artifact_sha256=hashlib.sha256(artifact_bytes).hexdigest(),
    )
    configure = provenance.record_invocation(
        command_id="parent-configure",
        physical_attempt_id=frozen.physical_attempt_id,
        sequence=1,
        repository_url=frozen.repository_url,
        commit_sha=frozen.commit_sha,
        image_id=frozen.image_id,
        executable="cmake",
        argv=("-S", frozen.workdir, "-B", frozen.build_directory, "-G", frozen.generator),
        workdir=frozen.workdir,
        previous_hash=provenance.ZERO_HASH,
    )
    native_build = provenance.record_invocation(
        command_id="parent-native-build",
        physical_attempt_id=frozen.physical_attempt_id,
        sequence=2,
        repository_url=frozen.repository_url,
        commit_sha=frozen.commit_sha,
        image_id=frozen.image_id,
        executable="ninja",
        argv=("-C", frozen.build_directory, frozen.target),
        workdir=frozen.workdir,
        previous_hash=configure.ledger_hash,
        output_paths=(frozen.artifact_relative_path,),
    )
    invocations = (configure, native_build)
    artifact = provenance.ArtifactIdentity(
        schema_version=provenance.SCHEMA_VERSION,
        physical_attempt_id=frozen.physical_attempt_id,
        producer_command_id=native_build.command_id,
        repository_url=frozen.repository_url,
        commit_sha=frozen.commit_sha,
        image_id=frozen.image_id,
        relative_path=frozen.artifact_relative_path,
        artifact_type=frozen.artifact_type,
        size=frozen.artifact_size,
        sha256=frozen.artifact_sha256,
        observed_after_sequence=3,
    )
    decision = provenance.evaluate_p2(frozen, invocations, artifact)
    neutral_feedback = {
        "status": "failed",
        "submit_attempt_id": "submit-opaque-provenance-1",
        "primary_classification": provenance.EXPECTED_CLASSIFICATION,
        "mechanism_classification": provenance.FAULT_FAMILY,
        "proof_status": PROOF_STATUS,
        "p2_status": "unproven",
        "replay_attempts": 0,
    }
    return FailureCheckpoint(
        schema_version=SCHEMA_VERSION,
        checkpoint_id="opaque-provenance-checkpoint-1",
        frozen=frozen,
        invocations=invocations,
        artifact=artifact,
        decision=decision,
        parent_history_sha256=provenance.command_history_sha256(invocations),
        neutral_feedback=neutral_feedback,
        neutral_feedback_sha256=canonical_sha256(neutral_feedback),
        replay_attempts=0,
    ).validate()


def build_repair_packet(frozen: provenance.FrozenIdentity) -> RepairPacket:
    return RepairPacket(
        schema_version=PACKET_SCHEMA_VERSION,
        primary_classification=provenance.EXPECTED_CLASSIFICATION,
        mechanism_classification=provenance.FAULT_FAMILY,
        expected_build_system="cmake",
        selected_build_system="cmake",
        build_directory=frozen.build_directory,
        target=frozen.target,
        proof_status=PROOF_STATUS,
        repair_goal=REPAIR_GOAL,
    ).validate(frozen)


def derive_arms(checkpoint: FailureCheckpoint) -> dict[str, ArmCheckpoint]:
    checkpoint.validate()
    packet = asdict(build_repair_packet(checkpoint.frozen))
    baseline = ArmCheckpoint(
        SCHEMA_VERSION,
        BASELINE_ARM,
        "baseline-opaque-provenance-session",
        checkpoint.checkpoint_sha256,
        checkpoint.checkpoint_sha256,
        copy.deepcopy(checkpoint.neutral_feedback),
    )
    treatment_feedback = copy.deepcopy(checkpoint.neutral_feedback)
    treatment_feedback["repair_packet"] = packet
    treatment = ArmCheckpoint(
        SCHEMA_VERSION,
        TREATMENT_ARM,
        "treatment-opaque-provenance-session",
        checkpoint.checkpoint_sha256,
        checkpoint.checkpoint_sha256,
        treatment_feedback,
    )
    arms = {BASELINE_ARM: baseline.validate(checkpoint), TREATMENT_ARM: treatment.validate(checkpoint)}
    validate_arm_pair(checkpoint, arms)
    return arms


def validate_arm_pair(checkpoint: FailureCheckpoint, arms: dict[str, ArmCheckpoint]) -> None:
    if set(arms) != set(ARMS):
        raise LifecycleGateError("lifecycle gate requires exactly two frozen arms")
    baseline = arms[BASELINE_ARM].validate(checkpoint)
    treatment = arms[TREATMENT_ARM].validate(checkpoint)
    if baseline.session_id == treatment.session_id:
        raise LifecycleGateError("arm session identities must be isolated")
    if baseline.common_state_sha256 != treatment.common_state_sha256:
        raise LifecycleGateError("arm common checkpoint state drifted")
    if {key: value for key, value in treatment.feedback.items() if key != "repair_packet"} != baseline.feedback:
        raise LifecycleGateError("treatment differs from baseline outside repair_packet")


def _append_treatment_invocation(checkpoint: FailureCheckpoint) -> tuple[tuple[provenance.InvocationEvidence, ...], provenance.ArtifactIdentity]:
    parent = checkpoint.invocations
    continuation = provenance.record_invocation(
        command_id="continuation-trusted-cmake-build",
        physical_attempt_id=checkpoint.frozen.physical_attempt_id,
        sequence=len(parent) + 1,
        repository_url=checkpoint.frozen.repository_url,
        commit_sha=checkpoint.frozen.commit_sha,
        image_id=checkpoint.frozen.image_id,
        executable="cmake",
        argv=("--build", checkpoint.frozen.build_directory, "--target", checkpoint.frozen.target),
        workdir=checkpoint.frozen.workdir,
        previous_hash=parent[-1].ledger_hash,
        output_paths=(checkpoint.frozen.artifact_relative_path,),
    )
    artifact = replace(
        checkpoint.artifact,
        producer_command_id=continuation.command_id,
        observed_after_sequence=continuation.sequence + 1,
    )
    return (*parent, continuation), artifact


def run_arm(checkpoint: FailureCheckpoint, arm: ArmCheckpoint, observers: ContractObservers) -> ArmOutcome:
    checkpoint.validate()
    arm.validate(checkpoint)
    parent_sha256 = provenance.command_history_sha256(checkpoint.invocations)
    if arm.arm == BASELINE_ARM:
        invocations = checkpoint.invocations
        artifact = checkpoint.artifact
    else:
        validate_repair_packet(arm.feedback["repair_packet"], checkpoint.frozen)
        invocations, artifact = _append_treatment_invocation(checkpoint)
    if invocations[: len(checkpoint.invocations)] != checkpoint.invocations:
        raise LifecycleGateError("continuation rewrote the parent command history")

    try:
        decision = provenance.evaluate_p2(checkpoint.frozen, invocations, artifact)
    except provenance.ProvenanceContractError as exc:
        raise LifecycleGateError("continuation P2 evaluation failed closed") from exc

    candidate_status = "not_run"
    replay_status = "not_run"
    cleanup_status = "not_run"
    continuation_history_sha256 = provenance.command_history_sha256(invocations)
    observation_subject_sha256 = canonical_sha256(
        {
            "checkpoint_sha256": checkpoint.checkpoint_sha256,
            "arm": arm.arm,
            "session_id": arm.session_id,
            "p2_decision": asdict(decision),
            "continuation_history_sha256": continuation_history_sha256,
        }
    )
    try:
        if arm.arm == BASELINE_ARM:
            if decision.status != "unproven" or decision.reason != PROOF_STATUS:
                raise LifecycleGateError("baseline unexpectedly converted provenance")
        else:
            if decision.status != "proven":
                raise LifecycleGateError("treatment did not convert provenance to P2")
            candidate = observers.candidate(observation_subject_sha256).validate("candidate", observation_subject_sha256)
            candidate_status = candidate.status
            if candidate.status != "passed":
                raise LifecycleGateError("candidate observer failed closed")
            replay = observers.clean_replay(observation_subject_sha256).validate("clean_replay", observation_subject_sha256)
            replay_status = replay.status
            if replay.status != "passed":
                raise LifecycleGateError("clean replay observer failed closed")
    finally:
        cleanup = observers.cleanup(observation_subject_sha256).validate("cleanup", observation_subject_sha256)
        cleanup_status = cleanup.status
        if cleanup.status != "passed":
            raise LifecycleGateError("cleanup observer failed closed")

    appended_ids = tuple(item.command_id for item in invocations[len(checkpoint.invocations) :])
    return ArmOutcome(
        schema_version=SCHEMA_VERSION,
        arm=arm.arm,
        p2_decision=decision,
        parent_history_sha256=parent_sha256,
        continuation_history_sha256=continuation_history_sha256,
        appended_command_ids=appended_ids,
        candidate_status=candidate_status,
        clean_replay_status=replay_status,
        cleanup_status=cleanup_status,
        observer_order=tuple(observers.calls),
        observation_subject_sha256=observation_subject_sha256,
    )


def validate_gate() -> dict[str, Any]:
    checkpoint = build_failure_checkpoint()
    arms = derive_arms(checkpoint)
    baseline = run_arm(checkpoint, arms[BASELINE_ARM], ContractObservers())
    treatment = run_arm(checkpoint, arms[TREATMENT_ARM], ContractObservers())
    return {
        "schema_version": SCHEMA_VERSION,
        "checkpoint_sha256": checkpoint.checkpoint_sha256,
        "parent_history_sha256": checkpoint.parent_history_sha256,
        "arm_common_state_equal": arms[BASELINE_ARM].common_state_sha256 == arms[TREATMENT_ARM].common_state_sha256,
        "treatment_exposure_only": "repair_packet",
        "baseline": asdict(baseline),
        "treatment": asdict(treatment),
        "observation_mode": "deterministic_contract_callback",
        "docker_executed": False,
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate",))
    return parser


def main(argv: list[str] | None = None) -> int:
    _parser().parse_args(argv)
    print(json.dumps(validate_gate(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
