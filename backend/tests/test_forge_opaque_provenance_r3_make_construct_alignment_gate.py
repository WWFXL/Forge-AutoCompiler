"""Issue #212 R3 Make 构造对齐零 provider 测试。"""

from __future__ import annotations

import importlib.util
import shlex
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _load():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    path = SCRIPTS_DIR / "forge_opaque_provenance_r3_make_construct_alignment_gate.py"
    spec = importlib.util.spec_from_file_location("forge_r3_make_construct_alignment_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load()


@pytest.mark.parametrize(
    ("command", "jobs"),
    [
        ("make libhoedown.a", None),
        ("make -j1 libhoedown.a", "1"),
        ("make --jobs 2 libhoedown.a", "2"),
        ("gmake -C /workspace/repo --jobs=2 libhoedown.a", "2"),
    ],
)
def test_runtime_accepts_public_bounded_jobs_contract(command: str, jobs: str | None) -> None:
    invocation = gate.validate_repair_build(command, workdir=gate.lifecycle.WORKDIR)
    assert invocation.jobs == jobs
    assert invocation.effective_directory == gate.lifecycle.WORKDIR
    assert invocation.target == gate.lifecycle.TARGET


@pytest.mark.parametrize(
    ("command", "classification"),
    [
        ("make -j libhoedown.a", "repair_build_jobs_unbounded"),
        ("make -j0 libhoedown.a", "repair_build_jobs_out_of_bounds"),
        ("make -j3 libhoedown.a", "repair_build_jobs_out_of_bounds"),
        ("make -jmany libhoedown.a", "repair_build_arguments_invalid"),
        ("make -C /workspace/other libhoedown.a", "repair_build_directory_drift"),
        ("make other", "repair_build_target_drift"),
        ("make CFLAGS=-O3 libhoedown.a", "repair_build_arguments_invalid"),
        ("cmake --build build", "repair_build_invocation_invalid"),
    ],
)
def test_runtime_rejects_out_of_contract_actions(
    command: str,
    classification: str,
) -> None:
    with pytest.raises(gate.ConstructAlignmentGateError) as raised:
        gate.validate_repair_build(command, workdir=gate.lifecycle.WORKDIR)
    assert raised.value.evidence_rejection_classification == classification
    assert raised.value.evidence_action_kind == "repair_build"


def test_every_runtime_admissible_example_satisfies_frozen_p2_parser() -> None:
    for command in (
        "make libhoedown.a",
        "make -j1 libhoedown.a",
        "gmake --jobs=2 libhoedown.a",
    ):
        invocation = gate.validate_repair_build(command, workdir=gate.lifecycle.WORKDIR)
        frozen = gate.lifecycle.reference.build_frozen_identity()
        parent = gate.lifecycle.provenance.record_invocation(
            command_id="parent",
            physical_attempt_id=frozen.physical_attempt_id,
            sequence=1,
            repository_url=frozen.repository_url,
            commit_sha=frozen.commit_sha,
            image_id=frozen.image_id,
            executable="sh",
            argv=("-c", "opaque parent"),
            workdir=frozen.workdir,
            previous_hash=gate.lifecycle.provenance.ZERO_HASH,
            output_paths=(frozen.artifact_relative_path,),
            model_declared_role="build",
        )
        tokens = shlex.split(command)
        direct = gate.lifecycle.provenance.record_invocation(
            command_id="direct",
            physical_attempt_id=frozen.physical_attempt_id,
            sequence=2,
            repository_url=frozen.repository_url,
            commit_sha=frozen.commit_sha,
            image_id=frozen.image_id,
            executable=tokens[0],
            argv=tuple(tokens[1:]),
            workdir=frozen.workdir,
            previous_hash=parent.ledger_hash,
            output_paths=(frozen.artifact_relative_path,),
            model_declared_role="build",
        )
        artifact = gate.lifecycle.reference._artifact(
            frozen,
            direct.command_id,
            observed_after_sequence=3,
        )
        decision = gate.lifecycle.reference.evaluate_make_p2(
            frozen,
            (parent, direct),
            artifact,
        )
        assert invocation.effective_directory == frozen.workdir
        assert invocation.target == frozen.target
        assert decision.status == "proven"
        assert decision.proof_mode == "direct_make"


def test_shared_tool_contract_is_identical_and_packet_is_only_exposure() -> None:
    baseline = gate.build_arm_contract("baseline")
    treatment = gate.build_arm_contract("treatment")
    assert baseline["tool_description"] == treatment["tool_description"]
    assert baseline["action_surface"] == treatment["action_surface"]
    assert "repair_packet" not in baseline
    assert treatment["repair_packet"] == gate.lifecycle.build_repair_packet()
    lowered = baseline["tool_description"].lower()
    assert "jobs" in lowered
    assert "1 或 2" in lowered
    assert "build 与 artifact stage" in lowered
    assert "/workspace/repo/libhoedown.a" in lowered
    assert "/artifacts/libhoedown.a" in lowered


def test_compound_build_and_stage_is_not_part_of_shared_contract() -> None:
    with pytest.raises(gate.ConstructAlignmentGateError):
        gate.validate_repair_build(
            "make libhoedown.a && cp libhoedown.a /artifacts/libhoedown.a",
            workdir=gate.lifecycle.WORKDIR,
        )


def test_gate_is_zero_provider_and_freezes_r2_components() -> None:
    report = gate.validate_gate_contract(REPO_ROOT)
    assert report["frozen_components_verified"] == len(gate.FROZEN_COMPONENTS)
    assert len(report["preregistration_sha256"]) == 64
    assert report["shared_tool_contract_identical"] is True
    assert report["treatment_exposure_only"] == "repair_packet"
    assert report["repair_packet_unchanged"] is True
    assert report["p2_identity_includes_jobs"] is False
    assert report["jobs_policy"] == {
        "omitted_allowed": True,
        "minimum": 1,
        "maximum": 2,
    }
    assert (
        report["provider_calls"],
        report["credential_read"],
        report["docker_executed"],
        report["checkpoint_created"],
        report["formal_attempts"],
        report["model_tokens"],
        report["evidence_writes"],
    ) == (0, False, False, False, 0, 0, 0)
