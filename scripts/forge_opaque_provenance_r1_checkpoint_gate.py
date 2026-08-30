#!/usr/bin/env python3
"""Issue #198 yyjson opaque provenance R1 真实 checkpoint 零 provider 门禁。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shlex
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from deerflow.compile import operations

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_opaque_build_provenance_gate as provenance  # noqa: E402
import forge_opaque_provenance_r1_candidate_protocol as candidate_protocol  # noqa: E402

SCHEMA_VERSION = "forge-opaque-provenance-r1-checkpoint-gate-1.0.0"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/198"
WORKDIR = "/workspace/repo"
GENERATOR = "Ninja"
PROOF_STATUS = "opaque_wrapper"
REPAIR_GOAL = "Execute and record a trusted build-system invocation bound to the frozen build directory and target, then submit again."


class CheckpointGateError(RuntimeError):
    """R1 candidate、parent command、repair packet 或 P2 identity 无效。"""


def _load_module(name: str, filename: str):
    path = SCRIPT_ROOT / filename
    existing = sys.modules.get(name)
    if existing is not None and Path(existing.__file__).resolve() == path.resolve():
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise CheckpointGateError(f"cannot load frozen component: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


observability = _load_module(
    "forge_opaque_provenance_r1_checkpoint_observability",
    "forge_opaque_provenance_rejection_observability_gate.py",
)


def _candidate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    return candidate_protocol.load_manifest(
        candidate_protocol.DEFAULT_MANIFEST, repo_root
    )


_MANIFEST = _candidate_manifest()
_CASE = _MANIFEST["case"]
CASE_ID = _CASE["case_id"]
REPOSITORY_URL = _CASE["repository_url"]
COMMIT_SHA = _CASE["commit_sha"]
COMPILE_IMAGE = _CASE["compile_image"]
SOURCE_SUBDIR = _CASE["source_subdir"]
BUILD_DIRECTORY = _CASE["build_directory"]
BUILD_OUTPUT = _CASE["build_output"]
STAGED_ARTIFACT = _CASE["staged_artifact"]
ARTIFACT_TYPE = _CASE["artifact_type"]
TARGET = _CASE["target"]
CONFIGURE_ARGUMENTS = tuple(_CASE["configure_arguments"])
REQUIRED_SYSTEM_PACKAGES = tuple(_CASE["required_system_packages"])
CANDIDATE_MANIFEST_SHA256 = candidate_protocol.canonical_sha256(_MANIFEST)

_CONFIGURE = " ".join(
    ["cmake", "-S", SOURCE_SUBDIR, "-B", "build", "-G", GENERATOR, *CONFIGURE_ARGUMENTS]
)
_PARENT_INNER_COMMAND = (
    f"rm -rf build && {_CONFIGURE} && "
    f"cmake --build build --target {TARGET} -j2 && "
    f"cp {BUILD_OUTPUT} /artifacts/{STAGED_ARTIFACT}"
)
PARENT_COMMAND = f"sh -c {shlex.quote(_PARENT_INNER_COMMAND)}"
TREATMENT_BUILD_COMMAND = f"cmake --build {BUILD_DIRECTORY} --target {TARGET} -j2"
TREATMENT_STAGE_COMMAND = (
    f"cp /workspace/repo/{BUILD_OUTPUT} /artifacts/{STAGED_ARTIFACT}"
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def build_repair_packet() -> dict[str, str]:
    packet = dict(_candidate_manifest()["repair_packet"]["template"])
    if list(packet) != candidate_protocol.REPAIR_PACKET_FIELDS:
        raise CheckpointGateError("repair packet fields drifted")
    return packet


def validate_repair_packet(value: dict[str, Any]) -> dict[str, str]:
    expected = build_repair_packet()
    if value != expected:
        raise CheckpointGateError("repair packet identity or whitelist drifted")
    serialized = canonical_bytes(value).decode("utf-8").lower()
    for forbidden in (
        "cmake --build",
        "bash -lc",
        "sh -c",
        "argv",
        "command_line",
        "shell",
        "secret",
        "api_key",
    ):
        if forbidden in serialized:
            raise CheckpointGateError("repair packet leaked a forbidden solution field")
    return expected


def validate_parent_command_contract() -> dict[str, Any]:
    roles = operations.infer_command_roles(PARENT_COMMAND)
    expected_roles = {"configure", "build", "artifact_stage"}
    if roles != expected_roles:
        raise CheckpointGateError(f"parent wrapper roles drifted: {sorted(roles)}")
    if operations._command_invokes(PARENT_COMMAND, "cmake"):
        raise CheckpointGateError("parent wrapper unexpectedly proves CMake identity")
    if (
        not operations._command_invokes(PARENT_COMMAND, "sh")
        or operations.infer_command_role(PARENT_COMMAND) != "build"
    ):
        raise CheckpointGateError("parent wrapper top-level identity drifted")
    return {
        "roles": sorted(roles),
        "top_level_executable": "sh",
        "cmake_identity_proven": False,
        "self_contained_replay_step": True,
    }


def build_frozen_identity(
    *,
    image_id: str,
    physical_attempt_id: str,
    build_tree_sha256: str,
    artifact_size: int,
    artifact_sha256: str,
):
    return provenance.FrozenIdentity(
        schema_version=provenance.SCHEMA_VERSION,
        case_id=CASE_ID,
        repository_url=REPOSITORY_URL,
        commit_sha=COMMIT_SHA,
        image_id=image_id,
        physical_attempt_id=physical_attempt_id,
        workdir=WORKDIR,
        build_directory=BUILD_DIRECTORY,
        generator=GENERATOR,
        build_tree_sha256=build_tree_sha256,
        target=TARGET,
        artifact_relative_path=BUILD_OUTPUT,
        artifact_type=ARTIFACT_TYPE,
        artifact_size=artifact_size,
        artifact_sha256=artifact_sha256,
    ).validate()


def _parent_invocation(frozen: Any, command_id: str):
    return provenance.record_invocation(
        command_id=command_id,
        physical_attempt_id=frozen.physical_attempt_id,
        sequence=1,
        repository_url=frozen.repository_url,
        commit_sha=frozen.commit_sha,
        image_id=frozen.image_id,
        executable="sh",
        argv=("-c", _PARENT_INNER_COMMAND),
        workdir=frozen.workdir,
        previous_hash=provenance.ZERO_HASH,
        output_paths=(frozen.artifact_relative_path,),
        model_declared_role="build",
    )


def _validate_case_identity(frozen: Any) -> None:
    frozen.validate()
    expected = {
        "case_id": CASE_ID,
        "repository_url": REPOSITORY_URL,
        "commit_sha": COMMIT_SHA,
        "workdir": WORKDIR,
        "build_directory": BUILD_DIRECTORY,
        "generator": GENERATOR,
        "target": TARGET,
        "artifact_relative_path": BUILD_OUTPUT,
        "artifact_type": ARTIFACT_TYPE,
    }
    if any(getattr(frozen, field) != value for field, value in expected.items()):
        raise CheckpointGateError("R1 frozen case identity drifted")


def evaluate_parent(frozen: Any, *, parent_command_id: str):
    _validate_case_identity(frozen)
    parent = _parent_invocation(frozen, parent_command_id)
    artifact = provenance.ArtifactIdentity(
        schema_version=provenance.SCHEMA_VERSION,
        physical_attempt_id=frozen.physical_attempt_id,
        producer_command_id=parent.command_id,
        repository_url=frozen.repository_url,
        commit_sha=frozen.commit_sha,
        image_id=frozen.image_id,
        relative_path=frozen.artifact_relative_path,
        artifact_type=frozen.artifact_type,
        size=frozen.artifact_size,
        sha256=frozen.artifact_sha256,
        observed_after_sequence=2,
    )
    decision = provenance.evaluate_p2(frozen, (parent,), artifact)
    if (
        decision.status != "unproven"
        or decision.classification != provenance.FAULT_FAMILY
        or decision.reason != PROOF_STATUS
    ):
        raise CheckpointGateError(
            "parent did not produce the frozen opaque-wrapper P2 failure"
        )
    return decision, (parent,)


def evaluate_treatment(
    frozen: Any,
    *,
    parent_command_id: str,
    treatment_build_command_id: str,
    treatment_stage_command_id: str,
):
    _validate_case_identity(frozen)
    parent = _parent_invocation(frozen, parent_command_id)
    build = provenance.record_invocation(
        command_id=treatment_build_command_id,
        physical_attempt_id=frozen.physical_attempt_id,
        sequence=2,
        repository_url=frozen.repository_url,
        commit_sha=frozen.commit_sha,
        image_id=frozen.image_id,
        executable="cmake",
        argv=("--build", frozen.build_directory, "--target", frozen.target, "-j2"),
        workdir=frozen.workdir,
        previous_hash=parent.ledger_hash,
        output_paths=(frozen.artifact_relative_path,),
        model_declared_role="build",
    )
    stage = provenance.record_invocation(
        command_id=treatment_stage_command_id,
        physical_attempt_id=frozen.physical_attempt_id,
        sequence=3,
        repository_url=frozen.repository_url,
        commit_sha=frozen.commit_sha,
        image_id=frozen.image_id,
        executable="cp",
        argv=(
            f"/workspace/repo/{frozen.artifact_relative_path}",
            f"/artifacts/{STAGED_ARTIFACT}",
        ),
        workdir=frozen.workdir,
        previous_hash=build.ledger_hash,
        model_declared_role="artifact_stage",
    )
    artifact = provenance.ArtifactIdentity(
        schema_version=provenance.SCHEMA_VERSION,
        physical_attempt_id=frozen.physical_attempt_id,
        producer_command_id=build.command_id,
        repository_url=frozen.repository_url,
        commit_sha=frozen.commit_sha,
        image_id=frozen.image_id,
        relative_path=frozen.artifact_relative_path,
        artifact_type=frozen.artifact_type,
        size=frozen.artifact_size,
        sha256=frozen.artifact_sha256,
        observed_after_sequence=4,
    )
    invocations = (parent, build, stage)
    decision = provenance.evaluate_p2(frozen, invocations, artifact)
    if decision.status != "proven" or decision.proof_mode != "direct_cmake":
        raise CheckpointGateError("treatment did not convert the frozen P2 outcome")
    return decision, invocations


def validate_gate_contract() -> dict[str, Any]:
    manifest = _candidate_manifest()
    if (
        manifest["checkpoint"]["status"] != "not_created"
        or manifest["authorization"]["docker_execution_authorized"] is not False
    ):
        raise CheckpointGateError("#196 candidate authorization boundary drifted")
    frozen = build_frozen_identity(
        image_id="sha256:" + "2" * 64,
        physical_attempt_id="attempt-r1-checkpoint-contract",
        build_tree_sha256="3" * 64,
        artifact_size=4096,
        artifact_sha256="4" * 64,
    )
    parent, parent_history = evaluate_parent(frozen, parent_command_id="parent-wrapper")
    treatment, treatment_history = evaluate_treatment(
        frozen,
        parent_command_id="parent-wrapper",
        treatment_build_command_id="treatment-cmake-build",
        treatment_stage_command_id="treatment-artifact-stage",
    )
    r0 = observability.validate_gate()
    return {
        "schema_version": SCHEMA_VERSION,
        "issue_url": ISSUE_URL,
        "candidate_manifest_sha256": candidate_protocol.canonical_sha256(manifest),
        "case_id": CASE_ID,
        "case": manifest["case"],
        "command_contract": validate_parent_command_contract(),
        "repair_packet": validate_repair_packet(build_repair_packet()),
        "parent": asdict(parent),
        "treatment_contract_only": asdict(treatment),
        "parent_history_sha256": provenance.command_history_sha256(parent_history),
        "treatment_history_sha256": provenance.command_history_sha256(
            treatment_history
        ),
        "parent_history_prefix_preserved": treatment_history[: len(parent_history)]
        == parent_history,
        "r0_observability": {
            "schema_version": r0["schema_version"],
            "companion_event": r0["observation_event"],
            "atomic_fields": r0["atomic_observability_fields"],
            "legacy_tool_failed_schema_preserved": r0[
                "legacy_tool_failed_schema_preserved"
            ],
            "raw_command_persisted": r0["raw_command_persisted"],
        },
        "checkpoint_created": False,
        "docker_executed": False,
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
        "credential_read": False,
        "candidate_evidence_writes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate",))
    parser.parse_args(argv)
    print(
        json.dumps(
            validate_gate_contract(), ensure_ascii=False, indent=2, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
