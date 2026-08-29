"""Issue #174 opaque build provenance P2 契约的零 provider 门禁。"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_opaque_build_provenance_gate.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("forge_opaque_build_provenance_gate_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load_module()


def _frozen(attempt_id: str = "attempt-p2"):
    return gate._frozen_identity(attempt_id)


def _record(frozen, *, command_id: str, sequence: int, executable: str, argv: tuple[str, ...], previous_hash: str, output: bool = False, **overrides):
    values = {
        "physical_attempt_id": frozen.physical_attempt_id,
        "repository_url": frozen.repository_url,
        "commit_sha": frozen.commit_sha,
        "image_id": frozen.image_id,
        "workdir": frozen.workdir,
    }
    values.update(overrides)
    return gate.record_invocation(
        command_id=command_id,
        sequence=sequence,
        executable=executable,
        argv=argv,
        previous_hash=previous_hash,
        output_paths=(frozen.artifact_relative_path,) if output else (),
        **values,
    )


def _artifact(frozen, producer, observed_after_sequence: int):
    return gate._artifact(frozen, producer.command_id, observed_after_sequence)


def _configure_and_native(frozen, *, native_executable: str = "ninja", native_build_directory: str | None = None, wrapper: bool = False):
    configure = _record(
        frozen,
        command_id="configure",
        sequence=1,
        executable="cmake",
        argv=("-S", frozen.workdir, "-B", frozen.build_directory, "-G", "Ninja"),
        previous_hash=gate.ZERO_HASH,
    )
    build_directory = native_build_directory or frozen.build_directory
    if wrapper:
        producer = _record(
            frozen,
            command_id="build",
            sequence=2,
            executable="bash",
            argv=("-lc", 'ninja -C "$0" "$1"'),
            previous_hash=configure.ledger_hash,
            output=True,
            leaf_executable=native_executable,
            leaf_argv=("-C", build_directory, frozen.target),
            leaf_workdir=frozen.workdir,
            wrapper_sha256="4" * 64,
        )
    else:
        producer = _record(
            frozen,
            command_id="build",
            sequence=2,
            executable=native_executable,
            argv=("-C", build_directory, frozen.target),
            previous_hash=configure.ledger_hash,
            output=True,
        )
    link = gate.GeneratorLink(
        schema_version=gate.SCHEMA_VERSION,
        physical_attempt_id=frozen.physical_attempt_id,
        configure_command_id=configure.command_id,
        configure_ledger_hash=configure.ledger_hash,
        repository_url=frozen.repository_url,
        commit_sha=frozen.commit_sha,
        image_id=frozen.image_id,
        source_directory=frozen.workdir,
        build_directory=frozen.build_directory,
        generator=frozen.generator,
        build_tree_sha256=frozen.build_tree_sha256,
        generated_at_sequence=configure.sequence,
    )
    return (configure, producer), link


def test_direct_cmake_build_is_p2_proven() -> None:
    frozen = _frozen()
    producer = _record(
        frozen,
        command_id="build",
        sequence=1,
        executable="cmake",
        argv=("--build", frozen.build_directory, "--target", frozen.target),
        previous_hash=gate.ZERO_HASH,
        output=True,
    )
    decision = gate.evaluate_p2(frozen, (producer,), _artifact(frozen, producer, 2))
    assert (decision.status, decision.classification, decision.proof_mode) == ("proven", None, "direct_cmake")


def test_trusted_cmake_configure_and_native_ninja_are_p2_proven() -> None:
    frozen = _frozen()
    history, link = _configure_and_native(frozen)
    decision = gate.evaluate_p2(frozen, history, _artifact(frozen, history[-1], 3), (link,))
    assert (decision.status, decision.classification, decision.proof_mode) == ("proven", None, "native_ninja")


def test_native_ninja_with_artifact_but_without_generator_link_is_unproven() -> None:
    frozen = _frozen()
    history, _link = _configure_and_native(frozen)
    decision = gate.evaluate_p2(frozen, history, _artifact(frozen, history[-1], 3))
    assert (decision.status, decision.classification, decision.reason) == ("unproven", gate.FAULT_FAMILY, "missing_trusted_generator_link")


def test_transparent_wrapper_with_complete_generator_link_is_p2_proven() -> None:
    frozen = _frozen()
    history, link = _configure_and_native(frozen, wrapper=True)
    decision = gate.evaluate_p2(frozen, history, _artifact(frozen, history[-1], 3), (link,))
    assert decision.status == "proven"
    assert decision.proof_mode == "native_ninja"


@pytest.mark.parametrize("model_role", [None, "build"])
def test_opaque_wrapper_and_model_role_are_not_reference_truth(model_role: str | None) -> None:
    frozen = _frozen()
    producer = _record(
        frozen,
        command_id="build",
        sequence=1,
        executable="bash",
        argv=("-lc", "opaque-build-wrapper"),
        previous_hash=gate.ZERO_HASH,
        output=True,
        model_declared_role=model_role,
    )
    decision = gate.evaluate_p2(frozen, (producer,), _artifact(frozen, producer, 2))
    assert (decision.status, decision.classification, decision.reason) == ("unproven", gate.FAULT_FAMILY, "opaque_wrapper")


def test_configure_and_build_directory_mismatch_is_unproven() -> None:
    frozen = _frozen()
    history, link = _configure_and_native(frozen, native_build_directory="/workspace/repo/other-build")
    decision = gate.evaluate_p2(frozen, history, _artifact(frozen, history[-1], 3), (link,))
    assert (decision.status, decision.reason) == ("unproven", "native_build_invocation_not_bound")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository_url", "https://github.com/example/drift.git"),
        ("commit_sha", "6" * 40),
        ("image_id", "sha256:" + "7" * 64),
        ("physical_attempt_id", "attempt-other"),
    ],
)
def test_source_image_and_attempt_drift_fail_closed(field: str, value: str) -> None:
    frozen = _frozen()
    producer = _record(
        frozen,
        command_id="build",
        sequence=1,
        executable="cmake",
        argv=("--build", frozen.build_directory, "--target", frozen.target),
        previous_hash=gate.ZERO_HASH,
        output=True,
        **{field: value},
    )
    with pytest.raises(gate.ProvenanceContractError, match="identity drifted"):
        gate.evaluate_p2(frozen, (producer,), _artifact(frozen, producer, 2))


@pytest.mark.parametrize(
    ("field", "value"),
    [("artifact_type", "static_library"), ("size", 99), ("sha256", "8" * 64), ("physical_attempt_id", "attempt-other")],
)
def test_artifact_identity_drift_fails_closed(field: str, value) -> None:
    frozen = _frozen()
    producer = _record(
        frozen,
        command_id="build",
        sequence=1,
        executable="cmake",
        argv=("--build", frozen.build_directory, "--target", frozen.target),
        previous_hash=gate.ZERO_HASH,
        output=True,
    )
    artifact = replace(_artifact(frozen, producer, 2), **{field: value})
    with pytest.raises(gate.ProvenanceContractError, match="artifact identity drifted"):
        gate.evaluate_p2(frozen, (producer,), artifact)


def test_ledger_hash_and_order_drift_fail_closed() -> None:
    frozen = _frozen()
    history, link = _configure_and_native(frozen)
    artifact = _artifact(frozen, history[-1], 3)
    hash_drift = replace(history[-1], ledger_hash="9" * 64)
    with pytest.raises(gate.ProvenanceContractError, match="ledger hash drifted"):
        gate.evaluate_p2(frozen, (history[0], hash_drift), artifact, (link,))
    with pytest.raises(gate.ProvenanceContractError, match="order or hash chain drifted"):
        gate.evaluate_p2(frozen, tuple(reversed(history)), artifact, (link,))


@pytest.mark.parametrize(("field", "value"), [("configure_ledger_hash", "8" * 64), ("build_tree_sha256", "9" * 64)])
def test_generator_link_and_build_tree_drift_fail_closed(field: str, value: str) -> None:
    frozen = _frozen()
    history, link = _configure_and_native(frozen)
    with pytest.raises(gate.ProvenanceContractError, match="generator link or build-tree identity drifted"):
        gate.evaluate_p2(frozen, history, _artifact(frozen, history[-1], 3), (replace(link, **{field: value}),))


def test_controlled_fault_preserves_command_history_byte_identity() -> None:
    frozen = _frozen()
    history, _link = _configure_and_native(frozen)
    decision = gate.evaluate_p2(frozen, history, _artifact(frozen, history[-1], 3))
    manifest = gate.build_controlled_fault_manifest(history, history, decision)
    assert manifest.command_history_unchanged is True
    assert manifest.command_history_sha256_before == manifest.command_history_sha256_after
    assert manifest.expected_classification == gate.EXPECTED_CLASSIFICATION
    assert manifest.replay_attempts == 0

    rewritten = (history[0], replace(history[1], model_declared_role="build"))
    with pytest.raises(gate.ProvenanceContractError):
        gate.build_controlled_fault_manifest(history, rewritten, decision)


def test_cli_reports_reference_fault_and_zero_provider_counts() -> None:
    completed = subprocess.run([sys.executable, str(SCRIPT_PATH), "validate"], check=True, capture_output=True, text=True)
    result = json.loads(completed.stdout)
    assert result["provider_calls"] == 0
    assert result["formal_attempts"] == 0
    assert result["model_tokens"] == 0
    assert result["reference"]["direct_cmake"]["status"] == "proven"
    assert result["reference"]["trusted_cmake_to_native_ninja"]["status"] == "proven"
    assert result["fault"]["decision"]["classification"] == gate.FAULT_FAMILY
    assert result["fault"]["manifest"]["expected_classification"] == gate.EXPECTED_CLASSIFICATION
    assert result["fault"]["manifest"]["command_history_unchanged"] is True
    assert result["fault"]["manifest"]["replay_attempts"] == 0


def test_gate_source_has_no_provider_secret_or_production_parser_access() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for forbidden in ("create_chat_model", "DEEPSEEK_API_KEY", "OpenAI_AK", "compile.operations", "formal_collection_runner"):
        assert forbidden not in source
