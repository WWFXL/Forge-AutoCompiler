"""Issue #202 Make opaque provenance R2 reference gate 测试。"""

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
SCRIPT_PATH = SCRIPTS_DIR / "forge_opaque_provenance_make_reference_gate.py"


def _load_module():
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location("forge_opaque_provenance_make_reference_gate_test", SCRIPT_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


gate = _load_module()


def _invocation(
    frozen,
    *,
    executable: str = "make",
    argv: tuple[str, ...] | None = None,
    workdir: str | None = None,
    exit_code: int = 0,
    timed_out: bool = False,
    repository_url: str | None = None,
):
    return gate.provenance.record_invocation(
        command_id="direct-make",
        physical_attempt_id=frozen.physical_attempt_id,
        sequence=1,
        repository_url=repository_url or frozen.repository_url,
        commit_sha=frozen.commit_sha,
        image_id=frozen.image_id,
        executable=executable,
        argv=argv or (frozen.target, "-j2"),
        workdir=workdir or frozen.workdir,
        previous_hash=gate.provenance.ZERO_HASH,
        exit_code=exit_code,
        timed_out=timed_out,
        output_paths=(frozen.artifact_relative_path,),
        model_declared_role="build",
    )


def _artifact(frozen, producer_id: str = "direct-make"):
    return gate.provenance.ArtifactIdentity(
        schema_version=gate.provenance.SCHEMA_VERSION,
        physical_attempt_id=frozen.physical_attempt_id,
        producer_command_id=producer_id,
        repository_url=frozen.repository_url,
        commit_sha=frozen.commit_sha,
        image_id=frozen.image_id,
        relative_path=frozen.artifact_relative_path,
        artifact_type=frozen.artifact_type,
        size=frozen.artifact_size,
        sha256=frozen.artifact_sha256,
        observed_after_sequence=2,
    )


@pytest.mark.parametrize(
    ("executable", "argv", "workdir", "jobs"),
    [
        ("make", ("libhoedown.a", "-j2"), "/workspace/repo", "2"),
        (
            "/usr/bin/gmake",
            ("-C", "/workspace/repo", "--jobs=3", "libhoedown.a"),
            "/workspace",
            "3",
        ),
        (
            "make",
            ("--directory=repo", "libhoedown.a", "-j", "4"),
            "/workspace",
            "4",
        ),
        (
            "make",
            ("-C", "/workspace", "-C", "repo", "libhoedown.a", "--jobs"),
            "/tmp",
            "unbounded",
        ),
    ],
)
def test_parse_make_invocation_normalizes_directory_target_and_jobs(
    executable: str,
    argv: tuple[str, ...],
    workdir: str,
    jobs: str,
) -> None:
    parsed = gate.parse_make_invocation(executable, argv, workdir=workdir)
    assert parsed == gate.MakeInvocation(
        effective_directory="/workspace/repo",
        target="libhoedown.a",
        jobs=jobs,
    )


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (("CC=clang", "libhoedown.a"), "variable assignments"),
        (("libhoedown.a", "all"), "exactly one target"),
        (("-k", "libhoedown.a"), "unregistered option"),
        (("-C",), "missing a value"),
        (("--directory=", "libhoedown.a"), "missing a value"),
        (("libhoedown.a", "-jmany"), "-j value"),
        (("libhoedown.a", "--jobs=many"), "--jobs value"),
    ],
)
def test_parse_make_invocation_rejects_unregistered_semantics(argv: tuple[str, ...], message: str) -> None:
    with pytest.raises(gate.MakeReferenceError, match=message):
        gate.parse_make_invocation("make", argv, workdir=gate.WORKDIR)


def test_reference_gate_freezes_result_blind_case_and_expected_outcomes() -> None:
    report = gate.validate_gate(REPO_ROOT)
    assert report["schema_version"] == ("forge-opaque-provenance-make-reference-gate-1.0.0")
    assert report["source_protocol"]["source_case"] == gate.HOEXTDOWN_SOURCE_CASE
    assert report["source_protocol"]["source_case"]["result_data_consulted"] is False
    assert report["parent"]["status"] == "unproven"
    assert report["parent"]["reason"] == "opaque_wrapper"
    assert report["treatment_contract"]["status"] == "proven"
    assert report["treatment_contract"]["proof_mode"] == "direct_make"
    assert report["parent_prefix_preserved"] is True
    assert report["mature_conventions"]["upstream_makefile_sha256"] == ("534aa41e0ec89d2fcce9de0513a1f241ba965af568e801e089470301cc66288d")


def test_direct_make_proves_exact_target_and_artifact() -> None:
    frozen = gate.build_frozen_identity()
    invocation = _invocation(frozen)
    decision = gate.evaluate_make_p2(frozen, (invocation,), _artifact(frozen))
    assert decision == gate.MakeProvenanceDecision(
        schema_version=gate.SCHEMA_VERSION,
        status="proven",
        classification=None,
        reason="trusted_direct_make_target",
        proof_mode="direct_make",
        producer_command_id="direct-make",
    )


@pytest.mark.parametrize(
    ("argv", "workdir", "reason"),
    [
        (("libhoedown.a",), "/workspace/other", "trusted_make_directory_mismatch"),
        (("all",), "/workspace/repo", "trusted_make_target_mismatch"),
        (
            ("CC=clang", "libhoedown.a"),
            "/workspace/repo",
            "trusted_make_invocation_invalid",
        ),
    ],
)
def test_make_directory_target_or_parameters_drift_fail_closed(argv: tuple[str, ...], workdir: str, reason: str) -> None:
    frozen = gate.build_frozen_identity()
    invocation = _invocation(frozen, argv=argv, workdir=workdir)
    decision = gate.evaluate_make_p2(frozen, (invocation,), _artifact(frozen))
    assert decision.status == "unproven"
    assert decision.classification == gate.provenance.FAULT_FAMILY
    assert decision.reason == reason


def test_failed_or_timed_out_make_producer_is_unproven() -> None:
    frozen = gate.build_frozen_identity()
    for invocation in (
        _invocation(frozen, exit_code=2),
        _invocation(frozen, exit_code=124, timed_out=True),
    ):
        decision = gate.evaluate_make_p2(frozen, (invocation,), _artifact(frozen))
        assert decision.status == "unproven"
        assert decision.reason == "producer_invocation_failed"


def test_run_or_artifact_identity_drift_is_invalid_evidence() -> None:
    frozen = gate.build_frozen_identity()
    invocation = _invocation(frozen, repository_url="https://github.com/example/drift")
    with pytest.raises(gate.MakeReferenceError, match="invocation identity drifted"):
        gate.evaluate_make_p2(frozen, (invocation,), _artifact(frozen))

    valid = _invocation(frozen)
    drifted_artifact = replace(_artifact(frozen), sha256="4" * 64)
    with pytest.raises(gate.MakeReferenceError, match="artifact identity drifted"):
        gate.evaluate_make_p2(frozen, (valid,), drifted_artifact)


def test_artifact_must_be_bound_to_existing_producer() -> None:
    frozen = gate.build_frozen_identity()
    invocation = _invocation(frozen)
    with pytest.raises(gate.MakeReferenceError, match="producer is absent"):
        gate.evaluate_make_p2(
            frozen,
            (invocation,),
            _artifact(frozen, producer_id="missing-producer"),
        )
    early = replace(_artifact(frozen), observed_after_sequence=1)
    with pytest.raises(gate.MakeReferenceError, match="not bound"):
        gate.evaluate_make_p2(frozen, (invocation,), early)


def test_frozen_cmake_reference_gate_remains_unchanged() -> None:
    assert gate.file_sha256(REPO_ROOT / gate.CMAKE_EVALUATOR_PATH) == (gate.CMAKE_EVALUATOR_SHA256)
    report = gate.provenance.validate_gate()
    assert report["fault"]["decision"]["status"] == "unproven"
    assert report["reference"]["direct_cmake"]["proof_mode"] == "direct_cmake"


def test_cli_is_zero_provider_and_does_not_write_evidence() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "validate"],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout)
    assert (
        report["provider_calls"],
        report["credential_read"],
        report["docker_executed"],
        report["checkpoint_created"],
        report["formal_attempts"],
        report["model_tokens"],
        report["evidence_writes"],
    ) == (0, False, False, False, 0, 0, 0)


def test_source_has_no_provider_docker_or_result_evidence_entrypoint() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    for forbidden in (
        "create_chat_model",
        "deepseek_api_key",
        "openai_ak",
        "os.getenv",
        "docker.from_env",
        "execute_reachability",
        "execute_pair",
        "benchmark-evidence-opaque-provenance-r1-yyjson-v1",
    ):
        assert forbidden not in source
