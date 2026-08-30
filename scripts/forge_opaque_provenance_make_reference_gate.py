#!/usr/bin/env python3
"""Issue #202 Make opaque provenance 的 R2 零 provider reference gate。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import posixpath
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_opaque_build_provenance_gate as provenance  # noqa: E402

SCHEMA_VERSION = "forge-opaque-provenance-make-reference-gate-1.0.0"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/202"
SOURCE_PROTOCOL_PATH = "benchmarks/preregistrations/cpp-formal-v1-cases.json"
SOURCE_PROTOCOL_FILE_SHA256 = "55fc4ea1cc634376b5016fa3421736a66c284b293b9b8f10185e837e12db3fee"
SOURCE_CASES_SHA256 = "3adb51f7c4cee22219c6ef4035fa0bc1e1dc6764e6246ad0dc4f612a03bb31ca"
CMAKE_EVALUATOR_PATH = "scripts/forge_opaque_build_provenance_gate.py"
CMAKE_EVALUATOR_SHA256 = "0f21ece5f3419a477925515f5312a009b0d447c1fa982f9e7fb626bf0f30e07a"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-opaque-provenance-make-reference-gate.md"

WORKDIR = "/workspace/repo"
TARGET = "libhoedown.a"
BUILD_OUTPUT = "libhoedown.a"
STAGED_ARTIFACT = "libhoedown.a"
ARTIFACT_TYPE = "static_library"
PARENT_COMMAND = "sh -c 'make libhoedown.a -j2 && cp libhoedown.a /artifacts/libhoedown.a'"
TREATMENT_COMMAND = "make libhoedown.a -j2"

GNU_MAKE_OPTIONS_URL = "https://www.gnu.org/software/make/manual/html_node/Options-Summary.html"
SLSA_PROVENANCE_URL = "https://slsa.dev/spec/v1.1/provenance"
UPSTREAM_MAKEFILE_URL = "https://raw.githubusercontent.com/kjdev/hoextdown/1ef9a71957570c2a65b7daa1b2f693ad87daf385/Makefile"
UPSTREAM_MAKEFILE_SHA256 = "534aa41e0ec89d2fcce9de0513a1f241ba965af568e801e089470301cc66288d"

HOEXTDOWN_SOURCE_CASE = {
    "id": "hoextdown",
    "repository_url": "https://github.com/kjdev/hoextdown",
    "commit": "1ef9a71957570c2a65b7daa1b2f693ad87daf385",
    "build_system": "make",
    "review_state": "reviewed",
    "result_data_consulted": False,
    "recipe": {
        "source_subdir": ".",
        "bootstrap_commands": [],
        "configure_arguments": [],
        "build_targets": [TARGET],
        "required_system_packages": ["build-essential"],
    },
    "artifact_oracle": {
        "required_artifacts": [
            {
                "staged_relative_path": STAGED_ARTIFACT,
                "build_output_path": BUILD_OUTPUT,
                "artifact_type": ARTIFACT_TYPE,
                "producing_target": TARGET,
            }
        ]
    },
    "evidence": [
        {
            "kind": "upstream_exact_commit",
            "path": "Makefile",
            "url": "https://github.com/kjdev/hoextdown/blob/1ef9a71957570c2a65b7daa1b2f693ad87daf385/Makefile",
            "supports": ["build_path", "artifact_identity"],
        },
        {
            "kind": "oss_fuzz_snapshot",
            "path": "hoextdown/build.sh",
            "url": "https://github.com/google/oss-fuzz/blob/08682bfc14e31d12fcc94b52b4805d7994fb70fd/projects/hoextdown/build.sh",
            "supports": ["build_path"],
        },
    ],
}


class MakeReferenceError(RuntimeError):
    """Make case、invocation、artifact 或 reference identity 无效。"""


@dataclass(frozen=True)
class MakeFrozenIdentity:
    schema_version: str
    case_id: str
    repository_url: str
    commit_sha: str
    image_id: str
    physical_attempt_id: str
    workdir: str
    target: str
    artifact_relative_path: str
    artifact_type: str
    artifact_size: int
    artifact_sha256: str

    def validate(self) -> MakeFrozenIdentity:
        if self.schema_version != SCHEMA_VERSION or not self.case_id or not self.physical_attempt_id or not self.target:
            raise MakeReferenceError("frozen Make identity is incomplete")
        if not provenance.COMMIT_PATTERN.fullmatch(self.commit_sha):
            raise MakeReferenceError("frozen Make commit is invalid")
        if not provenance.SHA256_PATTERN.fullmatch(self.image_id.removeprefix("sha256:")):
            raise MakeReferenceError("frozen Make image is invalid")
        _require_absolute_path(self.workdir, "frozen workdir")
        _require_relative_path(self.artifact_relative_path, "frozen artifact")
        if self.artifact_type not in {
            "executable",
            "shared_library",
            "static_library",
            "object",
        }:
            raise MakeReferenceError("frozen artifact type is invalid")
        if self.artifact_size <= 0 or not provenance.SHA256_PATTERN.fullmatch(self.artifact_sha256):
            raise MakeReferenceError("frozen artifact content identity is invalid")
        return self


@dataclass(frozen=True)
class MakeInvocation:
    effective_directory: str
    target: str
    jobs: str | None


@dataclass(frozen=True)
class MakeProvenanceDecision:
    schema_version: str
    status: str
    classification: str | None
    reason: str
    proof_mode: str | None
    producer_command_id: str


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_absolute_path(value: str, label: str) -> None:
    path = PurePosixPath(value)
    if not value or not path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise MakeReferenceError(f"{label} must be a normalized absolute path")


def _require_relative_path(value: str, label: str) -> None:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise MakeReferenceError(f"{label} must be a normalized relative path")


def load_source_case(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    path = repo_root / SOURCE_PROTOCOL_PATH
    if file_sha256(path) != SOURCE_PROTOCOL_FILE_SHA256:
        raise MakeReferenceError("formal v1 source protocol file drifted")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MakeReferenceError("cannot load formal v1 source protocol") from exc
    if not isinstance(document, dict) or document.get("protocolization", {}).get("case_protocol_sha256") != SOURCE_CASES_SHA256:
        raise MakeReferenceError("formal v1 case protocol identity drifted")
    matches = [case for case in document.get("cases", []) if isinstance(case, dict) and case.get("id") == "hoextdown"]
    if matches != [HOEXTDOWN_SOURCE_CASE]:
        raise MakeReferenceError("result-blind hoextdown case fields drifted")
    return copy.deepcopy(matches[0])


def _effective_directory(current: str, value: str) -> str:
    if not value:
        raise MakeReferenceError("Make directory option is missing a value")
    path = value if value.startswith("/") else posixpath.join(current, value)
    normalized = posixpath.normpath(path)
    _require_absolute_path(normalized, "Make effective directory")
    return normalized


def parse_make_invocation(
    executable: str,
    argv: tuple[str, ...],
    *,
    workdir: str,
) -> MakeInvocation:
    leaf = PurePosixPath(executable).name
    if leaf not in {"make", "gmake"}:
        raise MakeReferenceError("trusted invocation is not GNU-compatible Make")
    _require_absolute_path(workdir, "Make invocation workdir")
    effective_directory = workdir
    targets: list[str] = []
    jobs: str | None = None
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument in {"-C", "--directory"}:
            index += 1
            if index >= len(argv):
                raise MakeReferenceError("Make directory option is missing a value")
            effective_directory = _effective_directory(effective_directory, argv[index])
        elif argument.startswith("--directory="):
            effective_directory = _effective_directory(effective_directory, argument.split("=", 1)[1])
        elif argument == "-j" or argument == "--jobs":
            value = None
            if index + 1 < len(argv) and argv[index + 1].isdigit():
                index += 1
                value = argv[index]
            jobs = value or "unbounded"
        elif argument.startswith("-j") and argument != "-j":
            value = argument[2:]
            if not value.isdigit():
                raise MakeReferenceError("Make -j value is invalid")
            jobs = value
        elif argument.startswith("--jobs="):
            value = argument.split("=", 1)[1]
            if not value.isdigit():
                raise MakeReferenceError("Make --jobs value is invalid")
            jobs = value
        elif argument.startswith("-"):
            raise MakeReferenceError("Make invocation contains an unregistered option")
        else:
            if "=" in argument:
                raise MakeReferenceError("Make variable assignments are forbidden")
            targets.append(argument)
        index += 1
    if len(targets) != 1:
        raise MakeReferenceError("Make invocation must name exactly one target")
    return MakeInvocation(effective_directory, targets[0], jobs)


def _assert_run_identity(
    frozen: MakeFrozenIdentity,
    invocation: provenance.InvocationEvidence,
) -> None:
    actual = (
        invocation.repository_url,
        invocation.commit_sha,
        invocation.image_id,
        invocation.physical_attempt_id,
    )
    expected = (
        frozen.repository_url,
        frozen.commit_sha,
        frozen.image_id,
        frozen.physical_attempt_id,
    )
    if actual != expected:
        raise MakeReferenceError("trusted Make invocation identity drifted")


def _assert_artifact_identity(
    frozen: MakeFrozenIdentity,
    artifact: provenance.ArtifactIdentity,
) -> None:
    artifact.validate()
    actual_run = (
        artifact.repository_url,
        artifact.commit_sha,
        artifact.image_id,
        artifact.physical_attempt_id,
    )
    expected_run = (
        frozen.repository_url,
        frozen.commit_sha,
        frozen.image_id,
        frozen.physical_attempt_id,
    )
    actual_artifact = (
        artifact.relative_path,
        artifact.artifact_type,
        artifact.size,
        artifact.sha256,
    )
    expected_artifact = (
        frozen.artifact_relative_path,
        frozen.artifact_type,
        frozen.artifact_size,
        frozen.artifact_sha256,
    )
    if actual_run != expected_run or actual_artifact != expected_artifact:
        raise MakeReferenceError("Make artifact identity drifted")


def _unproven(producer: provenance.InvocationEvidence, reason: str) -> MakeProvenanceDecision:
    return MakeProvenanceDecision(
        SCHEMA_VERSION,
        "unproven",
        provenance.FAULT_FAMILY,
        reason,
        None,
        producer.command_id,
    )


def evaluate_make_p2(
    frozen: MakeFrozenIdentity,
    invocations: tuple[provenance.InvocationEvidence, ...],
    artifact: provenance.ArtifactIdentity,
) -> MakeProvenanceDecision:
    """按冻结的 Make reference criterion 判定 artifact provenance。"""

    frozen.validate()
    provenance.verify_ledger(invocations)
    for invocation in invocations:
        _assert_run_identity(frozen, invocation)
    _assert_artifact_identity(frozen, artifact)
    commands = {item.command_id: item for item in invocations}
    producer = commands.get(artifact.producer_command_id)
    if producer is None:
        raise MakeReferenceError("artifact producer is absent from the trusted ledger")
    if artifact.observed_after_sequence <= producer.sequence or artifact.relative_path not in producer.output_paths:
        raise MakeReferenceError("artifact is not bound to its producer invocation")
    if producer.exit_code != 0 or producer.timed_out:
        return _unproven(producer, "producer_invocation_failed")
    if producer.leaf_executable is None or producer.leaf_argv is None or producer.leaf_workdir is None:
        return _unproven(producer, "opaque_wrapper")
    try:
        parsed = parse_make_invocation(
            producer.leaf_executable,
            producer.leaf_argv,
            workdir=producer.leaf_workdir,
        )
    except MakeReferenceError:
        return _unproven(producer, "trusted_make_invocation_invalid")
    if parsed.effective_directory != frozen.workdir:
        return _unproven(producer, "trusted_make_directory_mismatch")
    if parsed.target != frozen.target:
        return _unproven(producer, "trusted_make_target_mismatch")
    return MakeProvenanceDecision(
        SCHEMA_VERSION,
        "proven",
        None,
        "trusted_direct_make_target",
        "direct_make",
        producer.command_id,
    )


def build_frozen_identity() -> MakeFrozenIdentity:
    return MakeFrozenIdentity(
        schema_version=SCHEMA_VERSION,
        case_id="hoextdown-opaque-provenance-r2",
        repository_url=HOEXTDOWN_SOURCE_CASE["repository_url"],
        commit_sha=HOEXTDOWN_SOURCE_CASE["commit"],
        image_id="sha256:" + "2" * 64,
        physical_attempt_id="attempt-r2-make-reference",
        workdir=WORKDIR,
        target=TARGET,
        artifact_relative_path=BUILD_OUTPUT,
        artifact_type=ARTIFACT_TYPE,
        artifact_size=4096,
        artifact_sha256="3" * 64,
    ).validate()


def _artifact(
    frozen: MakeFrozenIdentity,
    producer_command_id: str,
    *,
    observed_after_sequence: int,
) -> provenance.ArtifactIdentity:
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


def validate_gate(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    source_case = load_source_case(repo_root)
    if file_sha256(repo_root / CMAKE_EVALUATOR_PATH) != CMAKE_EVALUATOR_SHA256:
        raise MakeReferenceError("frozen CMake evaluator drifted")
    preregistration_sha256 = file_sha256(repo_root / PREREGISTRATION_PATH)
    frozen = build_frozen_identity()
    parent = provenance.record_invocation(
        command_id="parent-opaque-wrapper",
        physical_attempt_id=frozen.physical_attempt_id,
        sequence=1,
        repository_url=frozen.repository_url,
        commit_sha=frozen.commit_sha,
        image_id=frozen.image_id,
        executable="sh",
        argv=("-c", "make libhoedown.a -j2 && cp libhoedown.a /artifacts/libhoedown.a"),
        workdir=frozen.workdir,
        previous_hash=provenance.ZERO_HASH,
        output_paths=(frozen.artifact_relative_path,),
        model_declared_role="build",
    )
    parent_decision = evaluate_make_p2(
        frozen,
        (parent,),
        _artifact(frozen, parent.command_id, observed_after_sequence=2),
    )
    direct = provenance.record_invocation(
        command_id="treatment-direct-make",
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
    treatment_decision = evaluate_make_p2(
        frozen,
        (parent, direct),
        _artifact(frozen, direct.command_id, observed_after_sequence=3),
    )
    if parent_decision.status != "unproven" or parent_decision.reason != "opaque_wrapper" or treatment_decision.status != "proven" or treatment_decision.proof_mode != "direct_make":
        raise MakeReferenceError("Make parent/treatment reference outcome drifted")
    return {
        "schema_version": SCHEMA_VERSION,
        "issue_url": ISSUE_URL,
        "source_protocol": {
            "path": SOURCE_PROTOCOL_PATH,
            "file_sha256": SOURCE_PROTOCOL_FILE_SHA256,
            "case_protocol_sha256": SOURCE_CASES_SHA256,
            "audit_mode": "result-blind-static-document-review",
            "source_case": source_case,
        },
        "case_id": frozen.case_id,
        "mature_conventions": {
            "gnu_make_options": GNU_MAKE_OPTIONS_URL,
            "slsa_provenance": SLSA_PROVENANCE_URL,
            "upstream_makefile": UPSTREAM_MAKEFILE_URL,
            "upstream_makefile_sha256": UPSTREAM_MAKEFILE_SHA256,
        },
        "frozen_identity": asdict(frozen),
        "parent": asdict(parent_decision),
        "treatment_contract": asdict(treatment_decision),
        "parent_history_sha256": provenance.command_history_sha256((parent,)),
        "treatment_history_sha256": provenance.command_history_sha256((parent, direct)),
        "parent_prefix_preserved": True,
        "preregistration_sha256": preregistration_sha256,
        "provider_calls": 0,
        "credential_read": False,
        "docker_executed": False,
        "checkpoint_created": False,
        "formal_attempts": 0,
        "model_tokens": 0,
        "evidence_writes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate",))
    parser.parse_args(argv)
    print(json.dumps(validate_gate(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
