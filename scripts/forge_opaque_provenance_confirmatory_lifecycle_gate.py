#!/usr/bin/env python3
"""Issue #232 六 case opaque provenance 的零 provider lifecycle adapter。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shlex
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from deerflow.compile import operations

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_ROOT = REPO_ROOT / "scripts"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/232"
SCHEMA_VERSION = "forge-opaque-provenance-confirmatory-lifecycle-gate-1.0.0"
COMPILE_IMAGE = "autocompiler:gcc13"
WORKDIR = "/workspace/repo"
BUILD_DIRECTORY = f"{WORKDIR}/build"
GENERATOR = "Ninja"
PROOF_STATUS = "opaque_wrapper"

CANDIDATE_MANIFEST_PATH = "benchmarks/manifests/cpp-opaque-provenance-confirmatory-candidate-v2.json"
CANDIDATE_MANIFEST_FILE_SHA256 = "c9026aa28268619485f2c7b2e72dbf70b8105e8aca2253d4226debcfc1da7133"
CANDIDATE_MANIFEST_SHA256 = "ca2dd38f4dd298272f5e2203484857cbc72a6fc86e161dabefed2a61b54b6812"
COMPILE_DOCKERFILE_PATH = "docker/compile/Dockerfile"
COMPILE_DOCKERFILE_SHA256 = "19c20e59fd8e98f44d08acdc0cce7c6c938df5a77d9f18176ba965d701b74628"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-opaque-provenance-confirmatory-lifecycle-zero-provider-gate.md"


class ConfirmatoryLifecycleGateError(RuntimeError):
    """六 case identity、P2 合同或生命周期边界发生漂移。"""


def _load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_ROOT / filename)
    if spec is None or spec.loader is None:
        raise ConfirmatoryLifecycleGateError(f"无法加载冻结模块: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


candidate = _load_module(
    "forge_opaque_provenance_confirmatory_lifecycle_candidate",
    "forge_opaque_provenance_confirmatory_candidate_v2_protocol.py",
)
cmake_reference = _load_module(
    "forge_opaque_provenance_confirmatory_lifecycle_cmake_reference",
    "forge_opaque_build_provenance_gate.py",
)
make_reference = _load_module(
    "forge_opaque_provenance_confirmatory_lifecycle_make_reference",
    "forge_opaque_provenance_make_reference_gate.py",
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class LifecycleCaseAdapter:
    case_id: str
    repository_url: str
    commit_sha: str
    build_system: str
    bootstrap_commands: tuple[str, ...]
    configure_arguments: tuple[str, ...]
    required_system_packages: tuple[str, ...]
    target: str
    build_output: str
    staged_artifact: str
    artifact_type: str
    parent_inner_command: str
    parent_command: str
    treatment_build_command: str
    treatment_stage_command: str
    expected_proof_mode: str
    build_tree_relative_path: str | None

    @property
    def stage_source(self) -> str:
        return f"{WORKDIR}/{self.build_output}"

    @property
    def stage_destination(self) -> str:
        return f"/artifacts/{self.staged_artifact}"


def _candidate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    path = repo_root / CANDIDATE_MANIFEST_PATH
    if file_sha256(path) != CANDIDATE_MANIFEST_FILE_SHA256:
        raise ConfirmatoryLifecycleGateError("#233 candidate v2 manifest 发生漂移")
    return candidate.validate_manifest(json.loads(path.read_text(encoding="utf-8")), repo_root)


def _cmake_commands(case: dict[str, Any]) -> tuple[str, str, str | None]:
    configure = shlex.join(
        (
            "cmake",
            "-S",
            ".",
            "-B",
            "build",
            "-G",
            GENERATOR,
            *case["configure_arguments"],
        )
    )
    build = shlex.join(
        (
            "cmake",
            "--build",
            BUILD_DIRECTORY,
            "--target",
            case["direct_target"],
            "-j2",
        )
    )
    return configure, build, "build/build.ninja"


def _make_commands(case: dict[str, Any]) -> tuple[list[str], str, None]:
    build = shlex.join(("make", case["direct_target"], "-j2"))
    bootstrap = [f"({command})" for command in case["bootstrap_commands"]]
    return bootstrap, build, None


def build_case_adapter(case_id: str, repo_root: Path = REPO_ROOT) -> LifecycleCaseAdapter:
    manifest = _candidate_manifest(repo_root)
    matches = [item for item in manifest["cases"] if item["case_id"] == case_id]
    if len(matches) != 1:
        raise ConfirmatoryLifecycleGateError(f"未知或重复的 case identity: {case_id}")
    case = matches[0]
    artifact = case["artifact"]
    if case["build_system"] == "cmake":
        configure, build, build_tree = _cmake_commands(case)
        parent_steps = ["rm -rf build", configure, build]
        proof_mode = "direct_cmake"
    elif case["build_system"] == "make":
        bootstrap, build, build_tree = _make_commands(case)
        parent_steps = [*bootstrap, build]
        proof_mode = "direct_make"
    else:
        raise ConfirmatoryLifecycleGateError(f"不支持的构建系统: {case['build_system']}")
    stage = shlex.join(("cp", artifact["stage_source"], artifact["stage_destination"]))
    parent_inner = " && ".join((*parent_steps, stage))
    return LifecycleCaseAdapter(
        case_id=case["case_id"],
        repository_url=case["repository_url"],
        commit_sha=case["commit_sha"],
        build_system=case["build_system"],
        bootstrap_commands=tuple(case["bootstrap_commands"]),
        configure_arguments=tuple(case["configure_arguments"]),
        required_system_packages=tuple(case["required_system_packages"]),
        target=case["direct_target"],
        build_output=artifact["build_output_path"],
        staged_artifact=artifact["staged_relative_path"],
        artifact_type=artifact["artifact_type"],
        parent_inner_command=parent_inner,
        parent_command=f"sh -c {shlex.quote(parent_inner)}",
        treatment_build_command=build,
        treatment_stage_command=stage,
        expected_proof_mode=proof_mode,
        build_tree_relative_path=build_tree,
    )


def build_case_adapters(
    repo_root: Path = REPO_ROOT,
) -> tuple[LifecycleCaseAdapter, ...]:
    return tuple(build_case_adapter(case_id, repo_root) for case_id in candidate.CASE_ORDER)


def build_frozen_identity(
    adapter: LifecycleCaseAdapter,
    *,
    image_id: str,
    physical_attempt_id: str,
    artifact_size: int,
    artifact_sha256: str,
    build_tree_sha256: str | None = None,
):
    if adapter.build_system == "cmake":
        if build_tree_sha256 is None:
            raise ConfirmatoryLifecycleGateError("CMake identity 缺少 build tree SHA-256")
        return cmake_reference.FrozenIdentity(
            schema_version=cmake_reference.SCHEMA_VERSION,
            case_id=adapter.case_id,
            repository_url=adapter.repository_url,
            commit_sha=adapter.commit_sha,
            image_id=image_id,
            physical_attempt_id=physical_attempt_id,
            workdir=WORKDIR,
            build_directory=BUILD_DIRECTORY,
            generator=GENERATOR,
            build_tree_sha256=build_tree_sha256,
            target=adapter.target,
            artifact_relative_path=adapter.build_output,
            artifact_type=adapter.artifact_type,
            artifact_size=artifact_size,
            artifact_sha256=artifact_sha256,
        ).validate()
    if build_tree_sha256 is not None:
        raise ConfirmatoryLifecycleGateError("Make identity 不应包含 build tree SHA-256")
    return make_reference.MakeFrozenIdentity(
        schema_version=make_reference.SCHEMA_VERSION,
        case_id=adapter.case_id,
        repository_url=adapter.repository_url,
        commit_sha=adapter.commit_sha,
        image_id=image_id,
        physical_attempt_id=physical_attempt_id,
        workdir=WORKDIR,
        target=adapter.target,
        artifact_relative_path=adapter.build_output,
        artifact_type=adapter.artifact_type,
        artifact_size=artifact_size,
        artifact_sha256=artifact_sha256,
    ).validate()


def _artifact(frozen: Any, producer_command_id: str, *, observed_after_sequence: int):
    return cmake_reference.ArtifactIdentity(
        schema_version=cmake_reference.SCHEMA_VERSION,
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


def _parent_invocation(adapter: LifecycleCaseAdapter, frozen: Any, command_id: str):
    return cmake_reference.record_invocation(
        command_id=command_id,
        physical_attempt_id=frozen.physical_attempt_id,
        sequence=1,
        repository_url=frozen.repository_url,
        commit_sha=frozen.commit_sha,
        image_id=frozen.image_id,
        executable="sh",
        argv=("-c", adapter.parent_inner_command),
        workdir=frozen.workdir,
        previous_hash=cmake_reference.ZERO_HASH,
        output_paths=(frozen.artifact_relative_path,),
        model_declared_role="build",
    )


def evaluate_parent(adapter: LifecycleCaseAdapter, frozen: Any, *, parent_command_id: str):
    parent = _parent_invocation(adapter, frozen, parent_command_id)
    artifact = _artifact(frozen, parent.command_id, observed_after_sequence=2)
    if adapter.build_system == "cmake":
        decision = cmake_reference.evaluate_p2(frozen, (parent,), artifact)
    else:
        decision = make_reference.evaluate_make_p2(frozen, (parent,), artifact)
    if decision.status != "unproven" or decision.classification != "opaque_build_provenance" or decision.reason != PROOF_STATUS:
        raise ConfirmatoryLifecycleGateError(f"{adapter.case_id} parent 未形成单一 opaque-wrapper fault")
    return decision, (parent,)


def evaluate_treatment(
    adapter: LifecycleCaseAdapter,
    frozen: Any,
    *,
    parent_command_id: str,
    treatment_build_command_id: str,
    treatment_stage_command_id: str,
):
    parent = _parent_invocation(adapter, frozen, parent_command_id)
    tokens = shlex.split(adapter.treatment_build_command)
    build = cmake_reference.record_invocation(
        command_id=treatment_build_command_id,
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
    stage = cmake_reference.record_invocation(
        command_id=treatment_stage_command_id,
        physical_attempt_id=frozen.physical_attempt_id,
        sequence=3,
        repository_url=frozen.repository_url,
        commit_sha=frozen.commit_sha,
        image_id=frozen.image_id,
        executable="cp",
        argv=(adapter.stage_source, adapter.stage_destination),
        workdir=frozen.workdir,
        previous_hash=build.ledger_hash,
        model_declared_role="artifact_stage",
    )
    invocations = (parent, build, stage)
    artifact = _artifact(frozen, build.command_id, observed_after_sequence=4)
    if adapter.build_system == "cmake":
        decision = cmake_reference.evaluate_p2(frozen, invocations, artifact)
    else:
        decision = make_reference.evaluate_make_p2(frozen, invocations, artifact)
    if decision.status != "proven" or decision.proof_mode != adapter.expected_proof_mode:
        raise ConfirmatoryLifecycleGateError(f"{adapter.case_id} treatment 未转换 P2")
    return decision, invocations


def validate_gate_contract(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if file_sha256(repo_root / COMPILE_DOCKERFILE_PATH) != COMPILE_DOCKERFILE_SHA256:
        raise ConfirmatoryLifecycleGateError("compile Dockerfile 发生漂移")
    dockerfile = (repo_root / COMPILE_DOCKERFILE_PATH).read_text(encoding="utf-8")
    installed_packages = {line.strip().removesuffix("\\").strip().removesuffix(";").strip() for line in dockerfile.splitlines()}
    reports: list[dict[str, Any]] = []
    for index, adapter in enumerate(build_case_adapters(repo_root), start=1):
        missing_packages = [package for package in adapter.required_system_packages if package not in installed_packages]
        if missing_packages:
            raise ConfirmatoryLifecycleGateError(f"{adapter.case_id} 依赖未冻结进 compile image: {missing_packages}")
        roles = operations.infer_command_roles(adapter.parent_command)
        if not {"build", "artifact_stage"}.issubset(roles):
            raise ConfirmatoryLifecycleGateError(f"{adapter.case_id} parent command role 发生漂移")
        if operations._command_invokes(adapter.parent_command, adapter.build_system):
            raise ConfirmatoryLifecycleGateError(f"{adapter.case_id} parent 意外暴露 direct build identity")
        if not operations._command_invokes(adapter.treatment_build_command, adapter.build_system):
            raise ConfirmatoryLifecycleGateError(f"{adapter.case_id} treatment 缺少 direct build identity")
        fake_sha = str(index + 1) * 64
        frozen = build_frozen_identity(
            adapter,
            image_id="sha256:" + str(index) * 64,
            physical_attempt_id=f"attempt-confirmatory-lifecycle-{adapter.case_id}",
            build_tree_sha256=fake_sha if adapter.build_system == "cmake" else None,
            artifact_size=4096,
            artifact_sha256=str(index + 2) * 64,
        )
        parent, parent_history = evaluate_parent(adapter, frozen, parent_command_id="parent-wrapper")
        treatment, treatment_history = evaluate_treatment(
            adapter,
            frozen,
            parent_command_id="parent-wrapper",
            treatment_build_command_id="treatment-build",
            treatment_stage_command_id="treatment-stage",
        )
        if treatment_history[: len(parent_history)] != parent_history:
            raise ConfirmatoryLifecycleGateError(f"{adapter.case_id} treatment 改写 parent history")
        reports.append(
            {
                "case": asdict(adapter),
                "parent_roles": sorted(roles),
                "parent": asdict(parent),
                "treatment": asdict(treatment),
                "parent_history_prefix_preserved": True,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "issue_url": ISSUE_URL,
        "candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "candidate_manifest_file_sha256": CANDIDATE_MANIFEST_FILE_SHA256,
        "compile_dockerfile_sha256": COMPILE_DOCKERFILE_SHA256,
        "compile_image": COMPILE_IMAGE,
        "cases": reports,
        "lifecycle_assertions": [
            "exact_commit_bootstrap",
            "parent_single_fault",
            "direct_treatment_conversion",
            "production_artifact_classification",
            "production_clean_replay",
            "production_finalize_and_cleanup",
        ],
        "provider_calls": 0,
        "credential_read": False,
        "checkpoint_created": False,
        "formal_attempts": 0,
        "model_tokens": 0,
        "formal_evidence_writes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate",))
    parser.parse_args(argv)
    print(json.dumps(validate_gate_contract(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
