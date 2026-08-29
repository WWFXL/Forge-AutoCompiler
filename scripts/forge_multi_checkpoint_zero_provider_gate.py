#!/usr/bin/env python3
"""Issue #168 多 checkpoint 零 provider 门禁的冻结 case 配置。"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = "forge-multi-checkpoint-zero-provider-gate-1.0.0"
DOCUMENT_TYPE = "forge_multi_checkpoint_zero_provider_gate"
FAULT_FAMILY = "artifact_staging_missing"
EXPECTED_CLASSIFICATION = "candidate_verification_failed"
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-verifier-multi-checkpoint-zero-provider-gate.json"
EXPECTED_CASE_SHA256 = {
    "cppitertools": "745da134b689a7b6de004ec117513603380b5a2cc6117ac93b43b5e121ce2ca2",
    "janet": "97f79827f13f9c8af9906dce37281c39ac7ed1b46af0e7167f90f5e4e98f41bd",
    "libcheck": "2ea0580af644bacbb13394eb5c91f55943b4b8b9b9b7241f1c0bed2964b723cf",
}


class MultiCheckpointGateError(RuntimeError):
    """多 checkpoint gate 配置或历史 identity 无效。"""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative_path(value: str, label: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise MultiCheckpointGateError(f"{label} must be a safe relative path")
    return path.as_posix()


@dataclass(frozen=True)
class CheckpointCase:
    case_id: str
    role: str
    repository_url: str
    commit_sha: str
    language: str
    build_system: str
    source_subdir: str
    build_targets: tuple[str, ...]
    required_system_packages: tuple[str, ...]
    cmake_arguments: tuple[str, ...]
    configure_arguments: tuple[str, ...]
    build_output_relative_path: str
    staged_relative_path: str
    artifact_type: str
    commands: tuple[tuple[str, str], ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> CheckpointCase:
        artifact = value["artifact"]
        return cls(
            case_id=value["case_id"],
            role=value["role"],
            repository_url=value["repository_url"],
            commit_sha=value["commit_sha"],
            language=value["language"],
            build_system=value["build_system"],
            source_subdir=value["source_subdir"],
            build_targets=tuple(value["build_targets"]),
            required_system_packages=tuple(value["required_system_packages"]),
            cmake_arguments=tuple(value["cmake_arguments"]),
            configure_arguments=tuple(value["configure_arguments"]),
            build_output_relative_path=artifact["build_output_relative_path"],
            staged_relative_path=artifact["staged_relative_path"],
            artifact_type=artifact["artifact_type"],
            commands=tuple((item["role"], item["command"]) for item in value["commands"]),
        ).validate()

    def validate(self) -> CheckpointCase:
        if self.role not in {"anchor", "new_gate"} or self.build_system not in {"cmake", "make", "autotools"}:
            raise MultiCheckpointGateError("case role or build system is invalid")
        if self.artifact_type not in {"executable", "static_library"}:
            raise MultiCheckpointGateError("case artifact type is invalid")
        _safe_relative_path(self.build_output_relative_path, "build_output_relative_path")
        _safe_relative_path(self.staged_relative_path, "staged_relative_path")
        if "/" in self.staged_relative_path:
            raise MultiCheckpointGateError("controlled fault v1 requires one top-level staged artifact")
        roles = [role for role, _command in self.commands]
        if roles.count("build") != 1 or roles.count("artifact_stage") != 1 or roles[-1] != "artifact_stage":
            raise MultiCheckpointGateError("case commands require one build and a final artifact_stage")
        if self.required_system_packages and roles.count("dependency_setup") != 1:
            raise MultiCheckpointGateError("cases with required packages require one dependency_setup command")
        if any("\n" in command or "\r" in command for _role, command in self.commands):
            raise MultiCheckpointGateError("case commands must be single-line frozen commands")
        return self

    @property
    def supporting_build_command(self) -> str:
        return next(command for role, command in self.commands if role == "build")


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MultiCheckpointGateError("cannot read multi-checkpoint gate manifest") from exc
    return validate_manifest(value)


def validate_manifest(value: Any) -> dict[str, Any]:
    required = {"$schema", "schema_version", "document_type", "authorization", "fault", "cases", "historical_components"}
    if not isinstance(value, dict) or set(value) != required:
        raise MultiCheckpointGateError("manifest field set is invalid")
    if value["schema_version"] != SCHEMA_VERSION or value["document_type"] != DOCUMENT_TYPE:
        raise MultiCheckpointGateError("manifest identity is invalid")
    if value["authorization"] != {
        "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/168",
        "provider_calls_authorized": False,
        "formal_attempts_authorized": False,
        "model_tokens_authorized": 0,
        "pilot_collection_authorized": False,
    }:
        raise MultiCheckpointGateError("zero-provider authorization boundary drifted")
    if value["fault"] != {
        "family": FAULT_FAMILY,
        "expected_classification": EXPECTED_CLASSIFICATION,
        "replay_attempts_required": 0,
        "required_artifacts_per_case": 1,
    }:
        raise MultiCheckpointGateError("controlled fault identity drifted")
    cases = [CheckpointCase.from_dict(item) for item in value["cases"]]
    if [case.case_id for case in cases] != ["cppitertools", "janet", "libcheck"] or [case.role for case in cases] != ["anchor", "new_gate", "new_gate"]:
        raise MultiCheckpointGateError("frozen case schedule drifted")
    if [case.build_system for case in cases] != ["cmake", "make", "autotools"]:
        raise MultiCheckpointGateError("frozen build-system coverage drifted")
    for item in value["cases"]:
        if canonical_sha256(item) != EXPECTED_CASE_SHA256.get(item["case_id"]):
            raise MultiCheckpointGateError(f"frozen case definition drifted: {item['case_id']}")
    if len({case.staged_relative_path for case in cases}) != len(cases):
        raise MultiCheckpointGateError("case staged artifact identities must be unique")
    return value


def cases(manifest: dict[str, Any]) -> tuple[CheckpointCase, ...]:
    validate_manifest(manifest)
    return tuple(CheckpointCase.from_dict(item) for item in manifest["cases"])


def case_by_id(manifest: dict[str, Any], case_id: str) -> CheckpointCase:
    selected = [case for case in cases(manifest) if case.case_id == case_id]
    if len(selected) != 1:
        raise MultiCheckpointGateError(f"unknown case: {case_id}")
    return selected[0]


def verify_historical_components(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> None:
    validate_manifest(manifest)
    for relative_path, expected in manifest["historical_components"].items():
        path = repo_root / relative_path
        if not path.is_file() or file_sha256(path) != expected:
            raise MultiCheckpointGateError(f"historical component drifted: {relative_path}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "show-case"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--case-id", choices=("cppitertools", "janet", "libcheck"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest = load_manifest(args.manifest)
    verify_historical_components(manifest)
    if args.command == "validate":
        result: Any = {"manifest_sha256": canonical_sha256(manifest), "cases": [case.case_id for case in cases(manifest)], "provider_calls": 0, "formal_attempts": 0, "model_tokens": 0}
    else:
        if args.case_id is None:
            raise MultiCheckpointGateError("show-case requires --case-id")
        result = case_by_id(manifest, args.case_id).__dict__
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
