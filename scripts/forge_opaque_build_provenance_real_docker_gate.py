#!/usr/bin/env python3
"""Issue #178 opaque build provenance 真实 Docker 生命周期门禁适配器。"""

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

SCHEMA_VERSION = "forge-opaque-build-provenance-real-docker-gate-1.0.0"
CASE_ID = "cppitertools-opaque-provenance-real-docker"
REPOSITORY_URL = "https://github.com/ryanhaining/cppitertools"
COMMIT_SHA = "531b3d753d2bbfe3b0ababe61c2e95e965c54a66"
COMPILE_IMAGE = "autocompiler:gcc13"
WORKDIR = "/workspace/repo"
BUILD_DIRECTORY = "/workspace/repo/build"
BUILD_OUTPUT = "build/accumulate_examples"
STAGED_ARTIFACT = "accumulate_examples"
TARGET = "accumulate_examples"
PROOF_STATUS = "opaque_wrapper"
REPAIR_GOAL = "Execute and record a trusted build-system invocation bound to the frozen build directory and target, then submit again."

_PARENT_INNER_COMMAND = "rm -rf build && cmake -S examples -B build -G Ninja -DCMAKE_BUILD_TYPE=Release && cmake --build build --target accumulate_examples -j2 && cp build/accumulate_examples /artifacts/accumulate_examples"
PARENT_COMMAND = f"sh -c {shlex.quote(_PARENT_INNER_COMMAND)}"
TREATMENT_BUILD_COMMAND = "cmake --build /workspace/repo/build --target accumulate_examples -j2"
TREATMENT_STAGE_COMMAND = "cp /workspace/repo/build/accumulate_examples /artifacts/accumulate_examples"

SCRIPTS_DIR = Path(__file__).resolve().parent


class RealDockerGateError(RuntimeError):
    """真实 gate 的预注册 identity 或确定性契约无效。"""


def _load_provenance_module():
    module_path = SCRIPTS_DIR / "forge_opaque_build_provenance_gate.py"
    module_name = "forge_opaque_build_provenance_real_docker_reference"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RealDockerGateError("cannot load the P2 reference evaluator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


provenance = _load_provenance_module()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def build_repair_packet() -> dict[str, str]:
    return {
        "schema_version": "forge-opaque-provenance-repair-packet-1.0.0",
        "primary_classification": provenance.EXPECTED_CLASSIFICATION,
        "mechanism_classification": provenance.FAULT_FAMILY,
        "expected_build_system": "cmake",
        "selected_build_system": "cmake",
        "build_directory": BUILD_DIRECTORY,
        "target": TARGET,
        "proof_status": PROOF_STATUS,
        "repair_goal": REPAIR_GOAL,
    }


def validate_repair_packet(value: dict[str, Any]) -> dict[str, str]:
    expected = build_repair_packet()
    if value != expected:
        raise RealDockerGateError("repair packet identity or whitelist drifted")
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
            raise RealDockerGateError("repair packet leaked a forbidden solution field")
    return expected


def validate_parent_command_contract() -> dict[str, Any]:
    roles = operations.infer_command_roles(PARENT_COMMAND)
    expected_roles = {"configure", "build", "artifact_stage"}
    if roles != expected_roles:
        raise RealDockerGateError(f"parent wrapper roles drifted: {sorted(roles)}")
    if operations._command_invokes(PARENT_COMMAND, "cmake"):
        raise RealDockerGateError("parent wrapper unexpectedly proves CMake identity")
    if not operations._command_invokes(PARENT_COMMAND, "sh"):
        raise RealDockerGateError("parent wrapper top-level identity drifted")
    if operations.infer_command_role(PARENT_COMMAND) != "build":
        raise RealDockerGateError("parent wrapper no longer resolves to a build command")
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
        generator="Ninja",
        build_tree_sha256=build_tree_sha256,
        target=TARGET,
        artifact_relative_path=BUILD_OUTPUT,
        artifact_type="executable",
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


def evaluate_parent(frozen: Any, *, parent_command_id: str):
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
    if decision.status != "unproven" or decision.classification != provenance.FAULT_FAMILY or decision.reason != PROOF_STATUS:
        raise RealDockerGateError("parent did not produce the frozen opaque-wrapper P2 failure")
    return decision, (parent,)


def evaluate_treatment(
    frozen: Any,
    *,
    parent_command_id: str,
    treatment_build_command_id: str,
    treatment_stage_command_id: str,
):
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
        argv=(frozen.artifact_relative_path, f"/artifacts/{STAGED_ARTIFACT}"),
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
        raise RealDockerGateError("treatment did not convert the frozen P2 outcome")
    if invocations[:1] != (parent,):
        raise RealDockerGateError("treatment rewrote parent command history")
    return decision, invocations


def validate_gate_contract() -> dict[str, Any]:
    command_contract = validate_parent_command_contract()
    packet = validate_repair_packet(build_repair_packet())
    frozen = build_frozen_identity(
        image_id="sha256:" + "2" * 64,
        physical_attempt_id="attempt-real-docker-contract",
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
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": CASE_ID,
        "command_contract": command_contract,
        "repair_packet": packet,
        "parent": asdict(parent),
        "treatment": asdict(treatment),
        "parent_history_sha256": provenance.command_history_sha256(parent_history),
        "treatment_history_sha256": provenance.command_history_sha256(treatment_history),
        "parent_history_prefix_preserved": treatment_history[: len(parent_history)] == parent_history,
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
    print(json.dumps(validate_gate_contract(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
