#!/usr/bin/env python3
"""Issue #174 opaque build provenance 的 P2 零 provider 契约门禁。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from pathlib import PurePosixPath
from typing import Any

SCHEMA_VERSION = "forge-opaque-build-provenance-gate-1.0.0"
FAULT_FAMILY = "opaque_build_provenance"
EXPECTED_CLASSIFICATION = "build_system_unproven"
ZERO_HASH = "0" * 64
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


class ProvenanceContractError(RuntimeError):
    """P2 契约 identity、ledger 或受控 fault 构造无效。"""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _require_sha256(value: str, label: str) -> None:
    if not SHA256_PATTERN.fullmatch(value):
        raise ProvenanceContractError(f"{label} must be a lowercase SHA-256")


def _require_absolute_posix(value: str, label: str) -> None:
    path = PurePosixPath(value)
    if not value or not path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ProvenanceContractError(f"{label} must be a normalized absolute POSIX path")


def _require_relative_posix(value: str, label: str) -> None:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ProvenanceContractError(f"{label} must be a normalized relative POSIX path")


@dataclass(frozen=True)
class ArtifactIdentity:
    """由可信观察面记录并绑定到 producer command 的产物 identity。"""

    schema_version: str
    physical_attempt_id: str
    producer_command_id: str
    repository_url: str
    commit_sha: str
    image_id: str
    relative_path: str
    artifact_type: str
    size: int
    sha256: str
    observed_after_sequence: int

    def validate(self) -> ArtifactIdentity:
        if self.schema_version != SCHEMA_VERSION:
            raise ProvenanceContractError("artifact schema version drifted")
        if not self.physical_attempt_id or not self.producer_command_id or not self.repository_url:
            raise ProvenanceContractError("artifact identity is incomplete")
        if not COMMIT_PATTERN.fullmatch(self.commit_sha):
            raise ProvenanceContractError("artifact commit identity is invalid")
        _require_sha256(self.image_id.removeprefix("sha256:"), "artifact image_id")
        _require_relative_posix(self.relative_path, "artifact relative_path")
        if self.artifact_type not in {"executable", "shared_library", "static_library", "object"}:
            raise ProvenanceContractError("artifact type is invalid")
        if self.size <= 0 or self.observed_after_sequence <= 0:
            raise ProvenanceContractError("artifact size or observation sequence is invalid")
        _require_sha256(self.sha256, "artifact sha256")
        return self


@dataclass(frozen=True)
class FrozenIdentity:
    """预注册 CMake case 的冻结输入、环境、target 与预期产物。"""

    schema_version: str
    case_id: str
    repository_url: str
    commit_sha: str
    image_id: str
    physical_attempt_id: str
    workdir: str
    build_directory: str
    generator: str
    build_tree_sha256: str
    target: str
    artifact_relative_path: str
    artifact_type: str
    artifact_size: int
    artifact_sha256: str

    def validate(self) -> FrozenIdentity:
        if self.schema_version != SCHEMA_VERSION or not self.case_id or not self.repository_url or not self.physical_attempt_id or not self.target:
            raise ProvenanceContractError("frozen identity is incomplete or version drifted")
        if not COMMIT_PATTERN.fullmatch(self.commit_sha):
            raise ProvenanceContractError("frozen commit identity is invalid")
        _require_sha256(self.image_id.removeprefix("sha256:"), "frozen image_id")
        _require_absolute_posix(self.workdir, "frozen workdir")
        _require_absolute_posix(self.build_directory, "frozen build_directory")
        try:
            PurePosixPath(self.build_directory).relative_to(PurePosixPath(self.workdir))
        except ValueError as exc:
            raise ProvenanceContractError("frozen build_directory must be below workdir") from exc
        if self.generator != "Ninja":
            raise ProvenanceContractError("frozen generator identity is invalid")
        _require_sha256(self.build_tree_sha256, "frozen build_tree_sha256")
        _require_relative_posix(self.artifact_relative_path, "frozen artifact_relative_path")
        if self.artifact_type not in {"executable", "shared_library", "static_library", "object"} or self.artifact_size <= 0:
            raise ProvenanceContractError("frozen artifact identity is invalid")
        _require_sha256(self.artifact_sha256, "frozen artifact_sha256")
        return self


@dataclass(frozen=True)
class InvocationEvidence:
    """可信 runtime 产生的规范化 invocation 与 ledger record。"""

    schema_version: str
    command_id: str
    physical_attempt_id: str
    sequence: int
    repository_url: str
    commit_sha: str
    image_id: str
    executable: str
    argv: tuple[str, ...]
    workdir: str
    leaf_executable: str | None
    leaf_argv: tuple[str, ...] | None
    leaf_workdir: str | None
    wrapper_sha256: str | None
    started_at_ns: int
    completed_at_ns: int
    exit_code: int
    timed_out: bool
    output_paths: tuple[str, ...]
    model_declared_role: str | None
    ledger_previous_hash: str
    ledger_hash: str

    def ledger_payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("ledger_hash")
        return value

    def validate(self) -> InvocationEvidence:
        if self.schema_version != SCHEMA_VERSION or not self.command_id or self.sequence <= 0:
            raise ProvenanceContractError("invocation identity is incomplete or version drifted")
        if not COMMIT_PATTERN.fullmatch(self.commit_sha):
            raise ProvenanceContractError("invocation commit identity is invalid")
        _require_sha256(self.image_id.removeprefix("sha256:"), "invocation image_id")
        _require_absolute_posix(self.workdir, "invocation workdir")
        if not self.executable or self.started_at_ns <= 0 or self.completed_at_ns < self.started_at_ns:
            raise ProvenanceContractError("invocation runtime record is invalid")
        if (self.leaf_executable is None) != (self.leaf_argv is None) or (self.leaf_executable is None) != (self.leaf_workdir is None):
            raise ProvenanceContractError("leaf invocation fields must be complete or absent")
        if self.leaf_workdir is not None:
            _require_absolute_posix(self.leaf_workdir, "leaf workdir")
        if self.leaf_executable is not None and self.executable != self.leaf_executable:
            if self.wrapper_sha256 is None:
                raise ProvenanceContractError("transparent wrapper requires wrapper_sha256")
            _require_sha256(self.wrapper_sha256, "wrapper_sha256")
        for output_path in self.output_paths:
            _require_relative_posix(output_path, "invocation output_path")
        _require_sha256(self.ledger_previous_hash, "ledger_previous_hash")
        _require_sha256(self.ledger_hash, "ledger_hash")
        if canonical_sha256(self.ledger_payload()) != self.ledger_hash:
            raise ProvenanceContractError("invocation ledger hash drifted")
        return self


@dataclass(frozen=True)
class GeneratorLink:
    """将可信 CMake configure invocation 绑定到 native build tree。"""

    schema_version: str
    physical_attempt_id: str
    configure_command_id: str
    configure_ledger_hash: str
    repository_url: str
    commit_sha: str
    image_id: str
    source_directory: str
    build_directory: str
    generator: str
    build_tree_sha256: str
    generated_at_sequence: int

    def validate(self) -> GeneratorLink:
        if self.schema_version != SCHEMA_VERSION or not self.physical_attempt_id or not self.configure_command_id or not self.repository_url:
            raise ProvenanceContractError("generator link is incomplete or version drifted")
        if not COMMIT_PATTERN.fullmatch(self.commit_sha):
            raise ProvenanceContractError("generator link commit identity is invalid")
        _require_sha256(self.configure_ledger_hash, "configure_ledger_hash")
        _require_sha256(self.image_id.removeprefix("sha256:"), "generator image_id")
        _require_absolute_posix(self.source_directory, "generator source_directory")
        _require_absolute_posix(self.build_directory, "generator build_directory")
        if self.generator != "Ninja" or self.generated_at_sequence <= 0:
            raise ProvenanceContractError("generator link identity is invalid")
        _require_sha256(self.build_tree_sha256, "build_tree_sha256")
        return self


@dataclass(frozen=True)
class ProvenanceDecision:
    schema_version: str
    status: str
    classification: str | None
    reason: str
    proof_mode: str | None
    producer_command_id: str


@dataclass(frozen=True)
class ControlledFaultManifest:
    schema_version: str
    fault_family: str
    expected_classification: str
    command_history_sha256_before: str
    command_history_sha256_after: str
    command_history_unchanged: bool
    replay_attempts: int


def record_invocation(
    *,
    command_id: str,
    physical_attempt_id: str,
    sequence: int,
    repository_url: str,
    commit_sha: str,
    image_id: str,
    executable: str,
    argv: tuple[str, ...],
    workdir: str,
    previous_hash: str,
    leaf_executable: str | None = None,
    leaf_argv: tuple[str, ...] | None = None,
    leaf_workdir: str | None = None,
    wrapper_sha256: str | None = None,
    exit_code: int = 0,
    timed_out: bool = False,
    output_paths: tuple[str, ...] = (),
    model_declared_role: str | None = None,
) -> InvocationEvidence:
    """构造一条确定性的 trusted-runtime record，并计算 ledger hash。"""

    if leaf_executable is None and executable not in {"bash", "sh", "cmd", "powershell", "pwsh"}:
        leaf_executable, leaf_argv, leaf_workdir = executable, argv, workdir
    draft = InvocationEvidence(
        schema_version=SCHEMA_VERSION,
        command_id=command_id,
        physical_attempt_id=physical_attempt_id,
        sequence=sequence,
        repository_url=repository_url,
        commit_sha=commit_sha,
        image_id=image_id,
        executable=executable,
        argv=argv,
        workdir=workdir,
        leaf_executable=leaf_executable,
        leaf_argv=leaf_argv,
        leaf_workdir=leaf_workdir,
        wrapper_sha256=wrapper_sha256,
        started_at_ns=sequence * 1_000_000,
        completed_at_ns=sequence * 1_000_000 + 100,
        exit_code=exit_code,
        timed_out=timed_out,
        output_paths=output_paths,
        model_declared_role=model_declared_role,
        ledger_previous_hash=previous_hash,
        ledger_hash=ZERO_HASH,
    )
    return replace(draft, ledger_hash=canonical_sha256(draft.ledger_payload())).validate()


def verify_ledger(invocations: tuple[InvocationEvidence, ...]) -> None:
    if not invocations:
        raise ProvenanceContractError("command ledger must not be empty")
    expected_previous = ZERO_HASH
    expected_sequence = 1
    command_ids: set[str] = set()
    for invocation in invocations:
        invocation.validate()
        if invocation.sequence != expected_sequence or invocation.ledger_previous_hash != expected_previous:
            raise ProvenanceContractError("command ledger order or hash chain drifted")
        if invocation.command_id in command_ids:
            raise ProvenanceContractError("command ledger contains a duplicate command_id")
        command_ids.add(invocation.command_id)
        expected_previous = invocation.ledger_hash
        expected_sequence += 1


def command_history_sha256(invocations: tuple[InvocationEvidence, ...]) -> str:
    verify_ledger(invocations)
    return canonical_sha256([asdict(invocation) for invocation in invocations])


def _assert_attempt_identity(frozen: FrozenIdentity, invocation: InvocationEvidence) -> None:
    actual = (invocation.repository_url, invocation.commit_sha, invocation.image_id, invocation.physical_attempt_id)
    expected = (frozen.repository_url, frozen.commit_sha, frozen.image_id, frozen.physical_attempt_id)
    if actual != expected:
        raise ProvenanceContractError(f"trusted invocation identity drifted: {invocation.command_id}")


def _assert_artifact_identity(frozen: FrozenIdentity, artifact: ArtifactIdentity) -> None:
    artifact.validate()
    actual_run = (artifact.repository_url, artifact.commit_sha, artifact.image_id, artifact.physical_attempt_id)
    expected_run = (frozen.repository_url, frozen.commit_sha, frozen.image_id, frozen.physical_attempt_id)
    actual_artifact = (artifact.relative_path, artifact.artifact_type, artifact.size, artifact.sha256)
    expected_artifact = (frozen.artifact_relative_path, frozen.artifact_type, frozen.artifact_size, frozen.artifact_sha256)
    if actual_run != expected_run or actual_artifact != expected_artifact:
        raise ProvenanceContractError("artifact identity drifted")


def _option_value(argv: tuple[str, ...], option: str) -> str | None:
    try:
        index = argv.index(option)
    except ValueError:
        return None
    return argv[index + 1] if index + 1 < len(argv) else None


def _unproven(producer: InvocationEvidence, reason: str) -> ProvenanceDecision:
    return ProvenanceDecision(SCHEMA_VERSION, "unproven", FAULT_FAMILY, reason, None, producer.command_id)


def _validate_generator_identity(frozen: FrozenIdentity, link: GeneratorLink) -> None:
    link.validate()
    actual = (link.repository_url, link.commit_sha, link.image_id, link.physical_attempt_id)
    expected = (frozen.repository_url, frozen.commit_sha, frozen.image_id, frozen.physical_attempt_id)
    if actual != expected:
        raise ProvenanceContractError("generator link identity drifted")


def evaluate_p2(
    frozen: FrozenIdentity,
    invocations: tuple[InvocationEvidence, ...],
    artifact: ArtifactIdentity,
    generator_links: tuple[GeneratorLink, ...] = (),
) -> ProvenanceDecision:
    """按冻结的 P2 reference criterion 判定一次 CMake provenance。"""

    frozen.validate()
    verify_ledger(invocations)
    for invocation in invocations:
        _assert_attempt_identity(frozen, invocation)
    _assert_artifact_identity(frozen, artifact)

    commands = {invocation.command_id: invocation for invocation in invocations}
    producer = commands.get(artifact.producer_command_id)
    if producer is None:
        raise ProvenanceContractError("artifact producer is absent from the trusted ledger")
    if artifact.observed_after_sequence <= producer.sequence or artifact.relative_path not in producer.output_paths:
        raise ProvenanceContractError("artifact is not bound to its producer invocation")
    if producer.exit_code != 0 or producer.timed_out:
        return _unproven(producer, "producer_invocation_failed")
    if producer.leaf_executable is None or producer.leaf_argv is None or producer.leaf_workdir is None:
        return _unproven(producer, "opaque_wrapper")
    if producer.leaf_workdir != frozen.workdir:
        return _unproven(producer, "producer_workdir_mismatch")

    leaf = PurePosixPath(producer.leaf_executable).name
    argv = producer.leaf_argv
    if leaf == "cmake" and _option_value(argv, "--build") == frozen.build_directory:
        target = _option_value(argv, "--target")
        if target == frozen.target:
            return ProvenanceDecision(SCHEMA_VERSION, "proven", None, "trusted_direct_cmake_build", "direct_cmake", producer.command_id)
        return _unproven(producer, "frozen_target_mismatch")

    if leaf != "ninja" or _option_value(argv, "-C") != frozen.build_directory or frozen.target not in argv:
        return _unproven(producer, "native_build_invocation_not_bound")

    matching_links = [link for link in generator_links if link.build_directory == frozen.build_directory]
    for link in generator_links:
        _validate_generator_identity(frozen, link)
    if not matching_links:
        return _unproven(producer, "missing_trusted_generator_link")
    if len(matching_links) != 1:
        raise ProvenanceContractError("native build has an ambiguous generator link")
    link = matching_links[0]
    configure = commands.get(link.configure_command_id)
    if configure is None:
        raise ProvenanceContractError("generator configure command is absent from the trusted ledger")
    if link.configure_ledger_hash != configure.ledger_hash or link.build_tree_sha256 != frozen.build_tree_sha256 or link.generator != frozen.generator:
        raise ProvenanceContractError("generator link or build-tree identity drifted")
    if configure.exit_code != 0 or configure.timed_out or configure.sequence >= producer.sequence or link.generated_at_sequence != configure.sequence:
        return _unproven(producer, "trusted_generator_invocation_invalid")
    if configure.leaf_executable is None or configure.leaf_argv is None or configure.leaf_workdir is None:
        return _unproven(producer, "opaque_generator_wrapper")
    configure_leaf = PurePosixPath(configure.leaf_executable).name
    configure_argv = configure.leaf_argv
    if (
        configure_leaf != "cmake"
        or _option_value(configure_argv, "-S") != link.source_directory
        or _option_value(configure_argv, "-B") != link.build_directory
        or _option_value(configure_argv, "-G") != link.generator
        or link.source_directory != frozen.workdir
    ):
        return _unproven(producer, "trusted_generator_binding_mismatch")
    return ProvenanceDecision(SCHEMA_VERSION, "proven", None, "trusted_cmake_generator_link", "native_ninja", producer.command_id)


def build_controlled_fault_manifest(
    before: tuple[InvocationEvidence, ...],
    after: tuple[InvocationEvidence, ...],
    decision: ProvenanceDecision,
) -> ControlledFaultManifest:
    """证明 fault 只缺 generator evidence，不改写 command history。"""

    before_sha = command_history_sha256(before)
    after_sha = command_history_sha256(after)
    unchanged = before == after and before_sha == after_sha
    if not unchanged:
        raise ProvenanceContractError("controlled fault must not delete, reorder, or rewrite command history")
    if decision.status != "unproven" or decision.classification != FAULT_FAMILY or decision.reason != "missing_trusted_generator_link":
        raise ProvenanceContractError("controlled fault is not the frozen opaque provenance fault")
    return ControlledFaultManifest(SCHEMA_VERSION, FAULT_FAMILY, EXPECTED_CLASSIFICATION, before_sha, after_sha, True, 0)


def _frozen_identity(attempt_id: str) -> FrozenIdentity:
    artifact_bytes = b"synthetic-cmake-artifact-v1"
    return FrozenIdentity(
        schema_version=SCHEMA_VERSION,
        case_id="cmake-opaque-provenance-single-case",
        repository_url="https://github.com/example/opaque-provenance-fixture.git",
        commit_sha="1" * 40,
        image_id="sha256:" + "2" * 64,
        physical_attempt_id=attempt_id,
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


def _artifact(frozen: FrozenIdentity, producer_command_id: str, observed_after_sequence: int) -> ArtifactIdentity:
    return ArtifactIdentity(
        schema_version=SCHEMA_VERSION,
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


def validate_gate() -> dict[str, Any]:
    direct = _frozen_identity("attempt-direct")
    direct_invocation = record_invocation(
        command_id="cmd-direct-build",
        physical_attempt_id=direct.physical_attempt_id,
        sequence=1,
        repository_url=direct.repository_url,
        commit_sha=direct.commit_sha,
        image_id=direct.image_id,
        executable="cmake",
        argv=("--build", direct.build_directory, "--target", direct.target),
        workdir=direct.workdir,
        previous_hash=ZERO_HASH,
        output_paths=(direct.artifact_relative_path,),
    )
    direct_decision = evaluate_p2(direct, (direct_invocation,), _artifact(direct, direct_invocation.command_id, 2))

    native = _frozen_identity("attempt-native")
    configure = record_invocation(
        command_id="cmd-configure",
        physical_attempt_id=native.physical_attempt_id,
        sequence=1,
        repository_url=native.repository_url,
        commit_sha=native.commit_sha,
        image_id=native.image_id,
        executable="cmake",
        argv=("-S", native.workdir, "-B", native.build_directory, "-G", "Ninja"),
        workdir=native.workdir,
        previous_hash=ZERO_HASH,
    )
    native_build = record_invocation(
        command_id="cmd-native-build",
        physical_attempt_id=native.physical_attempt_id,
        sequence=2,
        repository_url=native.repository_url,
        commit_sha=native.commit_sha,
        image_id=native.image_id,
        executable="ninja",
        argv=("-C", native.build_directory, native.target),
        workdir=native.workdir,
        previous_hash=configure.ledger_hash,
        output_paths=(native.artifact_relative_path,),
    )
    link = GeneratorLink(
        schema_version=SCHEMA_VERSION,
        physical_attempt_id=native.physical_attempt_id,
        configure_command_id=configure.command_id,
        configure_ledger_hash=configure.ledger_hash,
        repository_url=native.repository_url,
        commit_sha=native.commit_sha,
        image_id=native.image_id,
        source_directory=native.workdir,
        build_directory=native.build_directory,
        generator=native.generator,
        build_tree_sha256=native.build_tree_sha256,
        generated_at_sequence=configure.sequence,
    )
    native_history = (configure, native_build)
    native_artifact = _artifact(native, native_build.command_id, 3)
    native_decision = evaluate_p2(native, native_history, native_artifact, (link,))
    fault_decision = evaluate_p2(native, native_history, native_artifact)
    fault = build_controlled_fault_manifest(native_history, native_history, fault_decision)

    return {
        "schema_version": SCHEMA_VERSION,
        "reference": {"direct_cmake": asdict(direct_decision), "trusted_cmake_to_native_ninja": asdict(native_decision)},
        "fault": {"decision": asdict(fault_decision), "manifest": asdict(fault)},
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
