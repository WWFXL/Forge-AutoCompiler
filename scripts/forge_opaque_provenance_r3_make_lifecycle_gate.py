#!/usr/bin/env python3
"""Issue #214 R3 Make jobs 动作的真实 lifecycle 适配器。"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import forge_opaque_provenance_make_lifecycle_gate as lifecycle
import forge_opaque_provenance_r3_make_construct_alignment_gate as alignment

SCHEMA_VERSION = "forge-opaque-provenance-r3-make-lifecycle-gate-1.0.0"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/214"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-opaque-provenance-r3-make-lifecycle-zero-provider-gate.md"
LEGACY_DOCKER_TEST_PATH = "backend/tests/test_forge_opaque_provenance_make_lifecycle_gate_docker.py"
LEGACY_DOCKER_TEST_SHA256 = "5d4dead7f121433e6b82dca150ba7375e79c76b569c1172f36532f30c51ad652"

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent


class R3MakeLifecycleGateError(RuntimeError):
    """R3 lifecycle profile、冻结边界或 P2 结果无效。"""


@dataclass(frozen=True)
class MakeJobsProfile:
    profile_id: str
    build_command: str
    expected_jobs: str | None


PROFILES = {
    profile.profile_id: profile
    for profile in (
        MakeJobsProfile("jobs-omitted", "make libhoedown.a", None),
        MakeJobsProfile("jobs-1", "make -j1 libhoedown.a", "1"),
    )
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_profile(profile_id: str) -> MakeJobsProfile:
    try:
        return PROFILES[profile_id]
    except KeyError as exc:
        raise R3MakeLifecycleGateError(f"未知 R3 Make jobs profile: {profile_id}") from exc


def evaluate_treatment(
    frozen: Any,
    *,
    profile_id: str,
    parent_command_id: str,
    treatment_build_command_id: str,
    treatment_stage_command_id: str,
):
    """使用公开 jobs profile 建立 direct Make provenance，不改写 parent 历史。"""

    profile = get_profile(profile_id)
    invocation = alignment.validate_repair_build(profile.build_command, workdir=frozen.workdir)
    if invocation.jobs != profile.expected_jobs:
        raise R3MakeLifecycleGateError("R3 Make jobs 解析结果偏离 profile")
    tokens = shlex.split(profile.build_command)
    lifecycle._validate_case_identity(frozen)
    parent = lifecycle._parent_invocation(frozen, parent_command_id)
    build = lifecycle.provenance.record_invocation(
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
    stage = lifecycle.provenance.record_invocation(
        command_id=treatment_stage_command_id,
        physical_attempt_id=frozen.physical_attempt_id,
        sequence=3,
        repository_url=frozen.repository_url,
        commit_sha=frozen.commit_sha,
        image_id=frozen.image_id,
        executable="cp",
        argv=(frozen.artifact_relative_path, f"/artifacts/{lifecycle.STAGED_ARTIFACT}"),
        workdir=frozen.workdir,
        previous_hash=build.ledger_hash,
        model_declared_role="artifact_stage",
    )
    invocations = (parent, build, stage)
    decision = lifecycle.reference.evaluate_make_p2(
        frozen,
        invocations,
        lifecycle._artifact(frozen, build.command_id, observed_after_sequence=4),
    )
    if decision.status != "proven" or decision.proof_mode != "direct_make":
        raise R3MakeLifecycleGateError("R3 treatment 未转换 Make P2 结果")
    return decision, invocations


def build_docker_adapter(profile_id: str) -> SimpleNamespace:
    """向冻结 #204 Docker 编排提供相同窄接口。"""

    profile = get_profile(profile_id)

    def evaluate_profile_treatment(frozen: Any, **kwargs: str):
        return evaluate_treatment(frozen, profile_id=profile.profile_id, **kwargs)

    return SimpleNamespace(
        COMPILE_IMAGE=lifecycle.COMPILE_IMAGE,
        WORKDIR=lifecycle.WORKDIR,
        REPOSITORY_URL=lifecycle.REPOSITORY_URL,
        COMMIT_SHA=lifecycle.COMMIT_SHA,
        TARGET=lifecycle.TARGET,
        STAGED_ARTIFACT=lifecycle.STAGED_ARTIFACT,
        BUILD_OUTPUT=lifecycle.BUILD_OUTPUT,
        ARTIFACT_TYPE=lifecycle.ARTIFACT_TYPE,
        PARENT_COMMAND=lifecycle.PARENT_COMMAND,
        TREATMENT_BUILD_COMMAND=profile.build_command,
        TREATMENT_STAGE_COMMAND=lifecycle.TREATMENT_STAGE_COMMAND,
        CASE_ID=lifecycle.CASE_ID,
        provenance=lifecycle.provenance,
        validate_gate_contract=lambda: validate_gate_contract(),
        build_frozen_identity=lifecycle.build_frozen_identity,
        evaluate_parent=lifecycle.evaluate_parent,
        evaluate_treatment=evaluate_profile_treatment,
        build_repair_packet=lifecycle.build_repair_packet,
        validate_repair_packet=lifecycle.validate_repair_packet,
    )


def validate_gate_contract(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    alignment.validate_gate_contract(repo_root)
    lifecycle.validate_gate_contract(repo_root)
    if file_sha256(repo_root / LEGACY_DOCKER_TEST_PATH) != LEGACY_DOCKER_TEST_SHA256:
        raise R3MakeLifecycleGateError("冻结 #204 Docker orchestration 发生漂移")

    profile_results = []
    for index, profile in enumerate(PROFILES.values(), start=1):
        frozen = lifecycle.build_frozen_identity(
            image_id="sha256:" + str(index) * 64,
            physical_attempt_id=f"attempt-r3-make-lifecycle-{profile.profile_id}",
            artifact_size=4096,
            artifact_sha256=str(index + 2) * 64,
        )
        parent, parent_history = lifecycle.evaluate_parent(frozen, parent_command_id="parent-wrapper")
        treatment, treatment_history = evaluate_treatment(
            frozen,
            profile_id=profile.profile_id,
            parent_command_id="parent-wrapper",
            treatment_build_command_id=f"{profile.profile_id}-make-build",
            treatment_stage_command_id=f"{profile.profile_id}-artifact-stage",
        )
        if treatment_history[: len(parent_history)] != parent_history:
            raise R3MakeLifecycleGateError("R3 treatment 改写了 parent provenance 历史")
        profile_results.append(
            {
                "profile": asdict(profile),
                "parent": asdict(parent),
                "treatment": asdict(treatment),
                "parent_history_prefix_preserved": True,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "issue_url": ISSUE_URL,
        "preregistration_sha256": file_sha256(repo_root / PREREGISTRATION_PATH),
        "legacy_docker_orchestration_sha256": LEGACY_DOCKER_TEST_SHA256,
        "profiles": profile_results,
        "lifecycle_assertions": [
            "production_compile_session",
            "candidate_verification",
            "clean_replay",
            "r0_classification",
            "zero_orphan_cleanup",
        ],
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
