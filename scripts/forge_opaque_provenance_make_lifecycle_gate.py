#!/usr/bin/env python3
"""Issue #204 Make opaque provenance 的真实 lifecycle 零 provider 适配器。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shlex
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from deerflow.compile import operations

SCHEMA_VERSION = "forge-opaque-provenance-make-lifecycle-gate-1.0.0"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/204"
REFERENCE_GATE_PATH = "scripts/forge_opaque_provenance_make_reference_gate.py"
REFERENCE_GATE_SHA256 = "5df722d6115aa879a9dbe43fb5f98278ff72df6958ae99f22fe4cb2f6d16c14a"
CASE_ID = "hoextdown-opaque-provenance-r2-make-lifecycle"
REPOSITORY_URL = "https://github.com/kjdev/hoextdown"
COMMIT_SHA = "1ef9a71957570c2a65b7daa1b2f693ad87daf385"
COMPILE_IMAGE = "autocompiler:gcc13"
WORKDIR = "/workspace/repo"
BUILD_OUTPUT = "libhoedown.a"
STAGED_ARTIFACT = "libhoedown.a"
ARTIFACT_TYPE = "static_library"
TARGET = "libhoedown.a"
PROOF_STATUS = "opaque_wrapper"
REPAIR_GOAL = "Execute and record a trusted build-system invocation bound to the frozen directory and target, then submit again."

_PARENT_INNER_COMMAND = "make clean && make libhoedown.a -j2 && cp libhoedown.a /artifacts/libhoedown.a"
PARENT_COMMAND = f"sh -c {shlex.quote(_PARENT_INNER_COMMAND)}"
TREATMENT_BUILD_COMMAND = "make libhoedown.a -j2"
TREATMENT_STAGE_COMMAND = "cp libhoedown.a /artifacts/libhoedown.a"

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent


class MakeLifecycleGateError(RuntimeError):
    """Make lifecycle identity、packet 或 P2 合同无效。"""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_reference_module():
    module_path = SCRIPTS_DIR / Path(REFERENCE_GATE_PATH).name
    module_name = "forge_opaque_provenance_make_lifecycle_reference"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise MakeLifecycleGateError("cannot load the Make P2 reference evaluator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


reference = _load_reference_module()
provenance = reference.provenance


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
        "expected_build_system": "make",
        "selected_build_system": "make",
        "build_directory": WORKDIR,
        "target": TARGET,
        "proof_status": PROOF_STATUS,
        "repair_goal": REPAIR_GOAL,
    }


def validate_repair_packet(value: dict[str, Any]) -> dict[str, str]:
    expected = build_repair_packet()
    if value != expected:
        raise MakeLifecycleGateError("repair packet identity or whitelist drifted")
    serialized = canonical_bytes(value).decode("utf-8").lower()
    for forbidden in (
        "make libhoedown.a",
        "bash -lc",
        "sh -c",
        "argv",
        "command_line",
        "shell",
        "secret",
        "api_key",
    ):
        if forbidden in serialized:
            raise MakeLifecycleGateError("repair packet leaked a forbidden solution field")
    return expected


def validate_parent_command_contract() -> dict[str, Any]:
    roles = operations.infer_command_roles(PARENT_COMMAND)
    expected_roles = {"artifact_stage", "build", "housekeeping"}
    if roles != expected_roles:
        raise MakeLifecycleGateError(f"parent wrapper roles drifted: {sorted(roles)}")
    if operations._command_invokes(PARENT_COMMAND, "make"):
        raise MakeLifecycleGateError("parent wrapper unexpectedly proves Make identity")
    if not operations._command_invokes(PARENT_COMMAND, "sh"):
        raise MakeLifecycleGateError("parent wrapper top-level identity drifted")
    if operations.infer_command_role(PARENT_COMMAND) != "build":
        raise MakeLifecycleGateError("parent wrapper no longer resolves to a build command")
    return {
        "roles": sorted(roles),
        "top_level_executable": "sh",
        "make_identity_proven": False,
        "self_contained_replay_step": True,
    }


def build_frozen_identity(
    *,
    image_id: str,
    physical_attempt_id: str,
    artifact_size: int,
    artifact_sha256: str,
):
    return reference.MakeFrozenIdentity(
        schema_version=reference.SCHEMA_VERSION,
        case_id=CASE_ID,
        repository_url=REPOSITORY_URL,
        commit_sha=COMMIT_SHA,
        image_id=image_id,
        physical_attempt_id=physical_attempt_id,
        workdir=WORKDIR,
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
    actual = (
        frozen.schema_version,
        frozen.case_id,
        frozen.repository_url,
        frozen.commit_sha,
        frozen.workdir,
        frozen.target,
        frozen.artifact_relative_path,
        frozen.artifact_type,
    )
    expected = (
        reference.SCHEMA_VERSION,
        CASE_ID,
        REPOSITORY_URL,
        COMMIT_SHA,
        WORKDIR,
        TARGET,
        BUILD_OUTPUT,
        ARTIFACT_TYPE,
    )
    if actual != expected:
        raise MakeLifecycleGateError("frozen Make lifecycle case identity drifted")


def _artifact(frozen: Any, producer_command_id: str, *, observed_after_sequence: int):
    return provenance.ArtifactIdentity(
        schema_version=provenance.SCHEMA_VERSION,
        physical_attempt_id=frozen.physical_attempt_id,
        producer_command_id=producer_command_id,
        repository_url=frozen.repository_url,
        commit_sha=frozen.commit_sha,
        image_id=frozen.image_id,
        relative_path=frozen.artifact_relative_path,
        artifact_type=frozen.artifact_type,
        size=frozen.artifact_size,
        sha256=frozen.artifact_sha256,
        observed_after_sequence=observed_after_sequence,
    )


def evaluate_parent(frozen: Any, *, parent_command_id: str):
    _validate_case_identity(frozen)
    parent = _parent_invocation(frozen, parent_command_id)
    decision = reference.evaluate_make_p2(
        frozen,
        (parent,),
        _artifact(frozen, parent.command_id, observed_after_sequence=2),
    )
    if decision.status != "unproven" or decision.classification != provenance.FAULT_FAMILY or decision.reason != PROOF_STATUS:
        raise MakeLifecycleGateError("parent did not produce the frozen opaque-wrapper P2 failure")
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
        executable="make",
        argv=(frozen.target, "-j2"),
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
    invocations = (parent, build, stage)
    decision = reference.evaluate_make_p2(
        frozen,
        invocations,
        _artifact(frozen, build.command_id, observed_after_sequence=4),
    )
    if decision.status != "proven" or decision.proof_mode != "direct_make":
        raise MakeLifecycleGateError("treatment did not convert the frozen Make P2 outcome")
    if invocations[:1] != (parent,):
        raise MakeLifecycleGateError("treatment rewrote parent command history")
    return decision, invocations


def validate_gate_contract(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if file_sha256(repo_root / REFERENCE_GATE_PATH) != REFERENCE_GATE_SHA256:
        raise MakeLifecycleGateError("frozen Make reference evaluator drifted")
    source_case = reference.load_source_case(repo_root)
    command_contract = validate_parent_command_contract()
    packet = validate_repair_packet(build_repair_packet())
    frozen = build_frozen_identity(
        image_id="sha256:" + "2" * 64,
        physical_attempt_id="attempt-r2-make-lifecycle-contract",
        artifact_size=4096,
        artifact_sha256="4" * 64,
    )
    parent, parent_history = evaluate_parent(frozen, parent_command_id="parent-wrapper")
    treatment, treatment_history = evaluate_treatment(
        frozen,
        parent_command_id="parent-wrapper",
        treatment_build_command_id="treatment-make-build",
        treatment_stage_command_id="treatment-artifact-stage",
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "issue_url": ISSUE_URL,
        "case_id": CASE_ID,
        "source_case": source_case,
        "reference_gate_sha256": REFERENCE_GATE_SHA256,
        "command_contract": command_contract,
        "repair_packet": packet,
        "parent": asdict(parent),
        "treatment_contract": asdict(treatment),
        "parent_history_sha256": provenance.command_history_sha256(parent_history),
        "treatment_history_sha256": provenance.command_history_sha256(treatment_history),
        "parent_history_prefix_preserved": treatment_history[: len(parent_history)] == parent_history,
        "docker_executed": False,
        "provider_calls": 0,
        "credential_read": False,
        "formal_attempts": 0,
        "model_tokens": 0,
        "evidence_writes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate",))
    parser.parse_args(argv)
    print(json.dumps(validate_gate_contract(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
