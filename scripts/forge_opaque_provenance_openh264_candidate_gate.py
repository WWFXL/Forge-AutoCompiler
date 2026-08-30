#!/usr/bin/env python3
"""Issue #224 OpenH264 独立 Make checkpoint 的零 provider candidate/lifecycle 门禁。"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import shlex
import sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/224"
SCHEMA_VERSION = "forge-opaque-provenance-openh264-candidate-1.0.0"
DOCUMENT_TYPE = "forge_opaque_provenance_openh264_candidate"
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-openh264-candidate.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-openh264-candidate.schema.json"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-opaque-provenance-openh264-candidate.md"
SOURCE_PROTOCOL_PATH = "benchmarks/preregistrations/cpp-formal-v1-cases.json"
SOURCE_PROTOCOL_SHA256 = "55fc4ea1cc634376b5016fa3421736a66c284b293b9b8f10185e837e12db3fee"

CASE_ID = "openh264-opaque-provenance-r4-make"
SOURCE_CASE_ID = "openh264"
REPOSITORY_URL = "https://github.com/cisco/openh264"
COMMIT_SHA = "4a2615fac570c6ca1ed4f157b9fdab9466edfd80"
COMPILE_IMAGE = "autocompiler:gcc13"
WORKDIR = "/workspace/repo"
TARGET = "libopenh264.a"
BUILD_OUTPUT = "libopenh264.a"
STAGED_ARTIFACT = "libopenh264.a"
ARTIFACT_TYPE = "static_library"
PARENT_COMMAND = "sh -c 'make clean && make -j2 libopenh264.a && cp libopenh264.a /artifacts/libopenh264.a'"
_PARENT_INNER_COMMAND = "make clean && make -j2 libopenh264.a && cp libopenh264.a /artifacts/libopenh264.a"
TREATMENT_BUILD_COMMAND = "make -j1 libopenh264.a"
TREATMENT_STAGE_COMMAND = "cp libopenh264.a /artifacts/libopenh264.a"
PROOF_STATUS = "opaque_wrapper"
REPAIR_GOAL = "Execute and record a trusted build-system invocation bound to the frozen directory and target, then submit again."
EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-r4-openh264-candidate-v1"

UPSTREAM_MAKEFILE_URL = f"https://github.com/cisco/openh264/blob/{COMMIT_SHA}/Makefile"
UPSTREAM_MAKEFILE_SHA256 = "202daf149e44d1fd34017ce68e1ea8020187f1be50e869946446b3592456291b"
OSS_FUZZ_RECIPE_URL = "https://github.com/google/oss-fuzz/blob/08682bfc14e31d12fcc94b52b4805d7994fb70fd/projects/openh264/build.sh"
OSS_FUZZ_RECIPE_SHA256 = "4f53629516eb904cdd65a13ac427b99bf5d298daa4b7001327f6018f6a8a3ab4"
NASM_DEB_URL = "https://mirrors.ustc.edu.cn/ubuntu/pool/universe/n/nasm/nasm_2.16.01-1build1_amd64.deb"
NASM_DEB_SHA256 = "22eede0f2dd62343b0298182f62f7485704fe02f166395b02c92a8883377e0b3"

FROZEN_COMPONENTS = {
    SOURCE_PROTOCOL_PATH: SOURCE_PROTOCOL_SHA256,
    "scripts/forge_opaque_provenance_make_reference_gate.py": ("5df722d6115aa879a9dbe43fb5f98278ff72df6958ae99f22fe4cb2f6d16c14a"),
    "scripts/forge_opaque_provenance_make_lifecycle_gate.py": ("bb9fc467df0476cc1e7fdcca06bf64d020cb39f0efd48502289d814b3152230b"),
    "scripts/forge_opaque_provenance_r3_make_candidate_runner.py": ("b8ec84f3835ecbbc462232b676c5ebf72e15a7f021be2a148d1b85d8138e9be0"),
    "scripts/forge_opaque_provenance_r3_make_execution_failure_gate.py": ("cd36955c5256fa4376d0b5a4b60c139352ec2f8beb59c9b88741ad681b5bdb06"),
    "scripts/forge_opaque_provenance_r3_make_agent_construction_gate.py": ("f5a0af19e2ff1cc7dd90f096132d537ec3db4867649571640c29d8262f890e5a"),
    "benchmarks/manifests/cpp-opaque-provenance-r3-make-execution.json": ("2a435b7846d510776d4364deb92846f4e6a142fb0e8a822d0634c9fc0a3de76f"),
    "backend/tests/test_forge_opaque_provenance_make_lifecycle_gate_docker.py": ("5d4dead7f121433e6b82dca150ba7375e79c76b569c1172f36532f30c51ad652"),
}


class OpenH264CandidateGateError(RuntimeError):
    """候选身份、动作面、P2 lifecycle 或 construction 组合无效。"""


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


def verify_frozen_components(repo_root: Path = REPO_ROOT) -> None:
    for relative_path, expected in FROZEN_COMPONENTS.items():
        if file_sha256(repo_root / relative_path) != expected:
            raise OpenH264CandidateGateError(f"冻结组件发生漂移: {relative_path}")


def load_source_case(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    source_path = repo_root / SOURCE_PROTOCOL_PATH
    if file_sha256(source_path) != SOURCE_PROTOCOL_SHA256:
        raise OpenH264CandidateGateError("formal v1 source protocol 发生漂移")
    document = json.loads(source_path.read_text(encoding="utf-8"))
    matches = [item for item in document.get("cases", []) if isinstance(item, dict) and item.get("id") == SOURCE_CASE_ID]
    if len(matches) != 1:
        raise OpenH264CandidateGateError("OpenH264 source case 不唯一")
    source_case = matches[0]
    expected_identity = (
        source_case.get("repository_url"),
        source_case.get("commit"),
        source_case.get("build_system"),
        source_case.get("review_state"),
        source_case.get("result_data_consulted"),
    )
    if expected_identity != (
        REPOSITORY_URL,
        COMMIT_SHA,
        "make",
        "reviewed",
        False,
    ):
        raise OpenH264CandidateGateError("OpenH264 source identity 发生漂移")
    if source_case.get("recipe") != {
        "source_subdir": ".",
        "bootstrap_commands": [],
        "configure_arguments": [],
        "build_targets": [TARGET],
        "required_system_packages": ["build-essential", "nasm"],
    }:
        raise OpenH264CandidateGateError("OpenH264 source recipe 发生漂移")
    required = source_case.get("artifact_oracle", {}).get("required_artifacts")
    if required != [
        {
            "staged_relative_path": STAGED_ARTIFACT,
            "build_output_path": BUILD_OUTPUT,
            "artifact_type": ARTIFACT_TYPE,
            "producing_target": TARGET,
        }
    ]:
        raise OpenH264CandidateGateError("OpenH264 artifact oracle 发生漂移")
    return copy.deepcopy(source_case)


def build_repair_packet() -> dict[str, str]:
    return {
        "schema_version": "forge-opaque-provenance-repair-packet-1.0.0",
        "primary_classification": "build_system_unproven",
        "mechanism_classification": "opaque_build_provenance",
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
        raise OpenH264CandidateGateError("repair packet identity 发生漂移")
    serialized = canonical_bytes(value).decode("utf-8").lower()
    for forbidden in (
        "make libopenh264.a",
        "bash -lc",
        "sh -c",
        "argv",
        "command_line",
        "shell",
        "secret",
        "api_key",
    ):
        if forbidden in serialized:
            raise OpenH264CandidateGateError("repair packet 泄漏了解法或敏感字段")
    return expected


def _evidence_identity(source_case: dict[str, Any]) -> str:
    return canonical_sha256(
        {
            "schema_version": "forge-opaque-provenance-openh264-evidence-1.0.0",
            "case": source_case,
            "action_surface": {
                "build_directory": WORKDIR,
                "target": TARGET,
                "jobs": {"omitted_allowed": True, "minimum": 1, "maximum": 2},
                "artifact": STAGED_ARTIFACT,
            },
            "repair_packet": build_repair_packet(),
            "parent_agent_construction_gate": FROZEN_COMPONENTS["scripts/forge_opaque_provenance_r3_make_agent_construction_gate.py"],
        }
    )


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    verify_frozen_components(repo_root)
    source_case = load_source_case(repo_root)
    preregistration = repo_root / PREREGISTRATION_PATH
    if not preregistration.is_file():
        raise OpenH264CandidateGateError("候选预注册不存在")
    return {
        "$schema": "../schemas/forge-opaque-provenance-openh264-candidate.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "authorization": {
            "checkpoint_creation_authorized": False,
            "reachability_request_authorized": False,
            "provider_calls_authorized": False,
            "formal_attempts_authorized": False,
            "pair_collection_authorized": False,
            "credential_read_authorized": False,
            "model_creation_authorized": False,
            "evidence_write_authorized": False,
            "model_tokens_authorized": 0,
        },
        "selection": {
            "issue_url": ISSUE_URL,
            "mode": "result_blind_source_and_evidence_audit",
            "source_protocol": SOURCE_PROTOCOL_PATH,
            "source_protocol_sha256": SOURCE_PROTOCOL_SHA256,
            "source_case": source_case,
            "historical_manifest_mentions": True,
            "historical_physical_evidence_matches": 0,
            "published_report_matches": 0,
            "alternatives_rejected": {
                "sql-parser": "static=yes is required to align target and static-library oracle",
                "lodepng": "OSS-Fuzz bypasses Make and executable smoke adds semantics",
            },
        },
        "case": {
            "case_id": CASE_ID,
            "repository_url": REPOSITORY_URL,
            "commit_sha": COMMIT_SHA,
            "build_system": "make",
            "build_directory": WORKDIR,
            "target": TARGET,
            "build_output": BUILD_OUTPUT,
            "staged_artifact": STAGED_ARTIFACT,
            "artifact_type": ARTIFACT_TYPE,
            "required_system_packages": ["build-essential", "nasm"],
            "bootstrap_commands": [],
            "configure_arguments": [],
        },
        "reference_sources": {
            "upstream_makefile": {
                "url": UPSTREAM_MAKEFILE_URL,
                "sha256": UPSTREAM_MAKEFILE_SHA256,
                "direct_target": TARGET,
            },
            "oss_fuzz_recipe": {
                "url": OSS_FUZZ_RECIPE_URL,
                "sha256": OSS_FUZZ_RECIPE_SHA256,
                "direct_target": TARGET,
            },
            "submodules_at_exact_commit": [],
        },
        "lifecycle_fixture": {
            "base_image": COMPILE_IMAGE,
            "derived_image_persisted": False,
            "nasm_package": {
                "version": "2.16.01-1build1",
                "architecture": "amd64",
                "url": NASM_DEB_URL,
                "sha256": NASM_DEB_SHA256,
                "download_timeout_seconds": 60,
            },
            "apt_index_download_forbidden": True,
        },
        "checkpoint": {
            "status": "not_created",
            "checkpoint_id": None,
            "arm_state_matching": ["message", "environment", "budget"],
            "creation_requires_execution_amendment": True,
        },
        "runtime_parity": {
            "direct_executables": ["make", "gmake"],
            "jobs": {"omitted_allowed": True, "minimum": 1, "maximum": 2},
            "parallel_tool_calls": False,
            "shared_tool_contract_identical": True,
            "treatment_exposure_only": "repair_packet",
            "artifact_stage": {
                "source": f"{WORKDIR}/{BUILD_OUTPUT}",
                "destination": f"/artifacts/{STAGED_ARTIFACT}",
                "separate_from_build": True,
            },
            "candidate_verification_required": True,
            "clean_replay_required": True,
            "cleanup_required": True,
        },
        "repair_packet": build_repair_packet(),
        "agent_construction": {
            "source_issue": 222,
            "full_create_agent_gate_required": True,
            "candidate_policy_injected_into_published_bindings": True,
            "expected_model_requests": 1,
            "provider_calls": 0,
            "model_tokens": 0,
        },
        "evidence": {
            "schema_version": "forge-opaque-provenance-openh264-evidence-1.0.0",
            "directory": EVIDENCE_DIRECTORY,
            "status": "not_created",
            "append_only": True,
            "zero_provider_gate_writes_evidence": False,
            "identity_sha256": _evidence_identity(source_case),
        },
        "analysis": {
            "unit_of_analysis": "future_single_state_matched_make_pair",
            "primary_outcome": ("paired_post_checkpoint_p2_conversion_with_candidate_and_clean_replay"),
            "descriptive_only": True,
            "treatment_effect_estimated": False,
            "historical_pairs_pooled": False,
            "model_ranking_performed": False,
        },
        "preregistration": {
            "path": PREREGISTRATION_PATH,
            "file_sha256": file_sha256(preregistration),
        },
        "frozen_components": copy.deepcopy(FROZEN_COMPONENTS),
    }


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    frozen = manifest or generate_manifest()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": ("https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-opaque-provenance-openh264-candidate.schema.json"),
        "title": "Forge opaque provenance OpenH264 candidate",
        "const": frozen,
    }


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if not isinstance(value, dict) or value != generate_manifest(repo_root):
        raise OpenH264CandidateGateError("OpenH264 candidate manifest 发生漂移")
    if any(value for key, value in value["authorization"].items() if key.endswith("_authorized")):
        raise OpenH264CandidateGateError("candidate 意外授权了外部执行")
    if value["authorization"]["model_tokens_authorized"] != 0:
        raise OpenH264CandidateGateError("candidate 意外授权了 model token")
    return value


def load_manifest(
    path: Path = DEFAULT_MANIFEST,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    return validate_manifest(json.loads(path.read_text(encoding="utf-8")), repo_root)


def _runtime_modules():
    if str(SCRIPT_ROOT) not in sys.path:
        sys.path.insert(0, str(SCRIPT_ROOT))
    import forge_opaque_provenance_make_lifecycle_gate as base_lifecycle
    import forge_opaque_provenance_r3_make_agent_construction_gate as construction
    import forge_opaque_provenance_r3_make_candidate_runner as r3_runtime
    import forge_opaque_provenance_r3_make_execution_failure_gate as failure_gate

    return base_lifecycle, construction, r3_runtime, failure_gate


def build_frozen_identity(
    *,
    image_id: str,
    physical_attempt_id: str,
    artifact_size: int,
    artifact_sha256: str,
):
    base_lifecycle, _construction, _r3_runtime, _failure_gate = _runtime_modules()
    return base_lifecycle.reference.MakeFrozenIdentity(
        schema_version=base_lifecycle.reference.SCHEMA_VERSION,
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


def _validate_case_identity(frozen: Any) -> None:
    actual = (
        frozen.case_id,
        frozen.repository_url,
        frozen.commit_sha,
        frozen.workdir,
        frozen.target,
        frozen.artifact_relative_path,
        frozen.artifact_type,
    )
    expected = (
        CASE_ID,
        REPOSITORY_URL,
        COMMIT_SHA,
        WORKDIR,
        TARGET,
        BUILD_OUTPUT,
        ARTIFACT_TYPE,
    )
    if actual != expected:
        raise OpenH264CandidateGateError("OpenH264 lifecycle identity 发生漂移")


def _parent_invocation(frozen: Any, command_id: str):
    base_lifecycle, _construction, _r3_runtime, _failure_gate = _runtime_modules()
    return base_lifecycle.provenance.record_invocation(
        command_id=command_id,
        physical_attempt_id=frozen.physical_attempt_id,
        sequence=1,
        repository_url=frozen.repository_url,
        commit_sha=frozen.commit_sha,
        image_id=frozen.image_id,
        executable="sh",
        argv=("-c", _PARENT_INNER_COMMAND),
        workdir=frozen.workdir,
        previous_hash=base_lifecycle.provenance.ZERO_HASH,
        output_paths=(frozen.artifact_relative_path,),
        model_declared_role="build",
    )


def _artifact(frozen: Any, producer_command_id: str, *, observed_after_sequence: int):
    base_lifecycle, _construction, _r3_runtime, _failure_gate = _runtime_modules()
    return base_lifecycle.provenance.ArtifactIdentity(
        schema_version=base_lifecycle.provenance.SCHEMA_VERSION,
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
    base_lifecycle, _construction, _r3_runtime, _failure_gate = _runtime_modules()
    _validate_case_identity(frozen)
    parent = _parent_invocation(frozen, parent_command_id)
    decision = base_lifecycle.reference.evaluate_make_p2(
        frozen,
        (parent,),
        _artifact(frozen, parent.command_id, observed_after_sequence=2),
    )
    if decision.status != "unproven" or decision.classification != "opaque_build_provenance" or decision.reason != PROOF_STATUS:
        raise OpenH264CandidateGateError("parent 未形成单一 opaque-wrapper fault")
    return decision, (parent,)


def evaluate_treatment(
    frozen: Any,
    *,
    parent_command_id: str,
    treatment_build_command_id: str,
    treatment_stage_command_id: str,
):
    base_lifecycle, _construction, _r3_runtime, _failure_gate = _runtime_modules()
    _validate_case_identity(frozen)
    parent = _parent_invocation(frozen, parent_command_id)
    tokens = shlex.split(TREATMENT_BUILD_COMMAND)
    build = base_lifecycle.provenance.record_invocation(
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
    stage = base_lifecycle.provenance.record_invocation(
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
    decision = base_lifecycle.reference.evaluate_make_p2(
        frozen,
        invocations,
        _artifact(frozen, build.command_id, observed_after_sequence=4),
    )
    if decision.status != "proven" or decision.proof_mode != "direct_make":
        raise OpenH264CandidateGateError("treatment 未转换 Make P2")
    return decision, invocations


def _candidate_policy():
    _base_lifecycle, _construction, r3_runtime, _failure_gate = _runtime_modules()
    return r3_runtime.R3ActionPolicy(
        workdir=WORKDIR,
        build_directory=WORKDIR,
        target=TARGET,
        build_output=f"{WORKDIR}/{BUILD_OUTPUT}",
        staged_artifact=f"/artifacts/{STAGED_ARTIFACT}",
        maximum_jobs=2,
    )


def validate_static_gate(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    base_lifecycle, _construction, r3_runtime, _failure_gate = _runtime_modules()
    manifest = load_manifest(DEFAULT_MANIFEST, repo_root)
    operations = base_lifecycle.operations
    roles = operations.infer_command_roles(PARENT_COMMAND)
    if roles != {"artifact_stage", "build", "housekeeping"}:
        raise OpenH264CandidateGateError("parent wrapper role 发生漂移")
    if operations._command_invokes(PARENT_COMMAND, "make"):
        raise OpenH264CandidateGateError("parent wrapper 意外暴露 direct Make identity")

    policy = _candidate_policy()
    accepted = {
        command: r3_runtime.classify_action(
            command,
            workdir=WORKDIR,
            command_role="build",
            policy=policy,
        )
        for command in (
            "make libopenh264.a",
            "make -j1 libopenh264.a",
            "gmake --jobs=2 libopenh264.a",
        )
    }
    rejected: dict[str, str] = {}
    for command in (
        "make -j libopenh264.a",
        "make -j0 libopenh264.a",
        "make -j3 libopenh264.a",
        "make libhoedown.a",
    ):
        try:
            r3_runtime.classify_action(
                command,
                workdir=WORKDIR,
                command_role="build",
                policy=policy,
            )
        except r3_runtime.R3RuntimeParityGateError as exc:
            rejected[command] = exc.evidence_rejection_classification
        else:
            raise OpenH264CandidateGateError("非法 build action 未被拒绝")

    frozen = build_frozen_identity(
        image_id="sha256:" + "4" * 64,
        physical_attempt_id="attempt-openh264-candidate-static",
        artifact_size=4096,
        artifact_sha256="5" * 64,
    )
    parent, parent_history = evaluate_parent(frozen, parent_command_id="parent-wrapper")
    treatment, treatment_history = evaluate_treatment(
        frozen,
        parent_command_id="parent-wrapper",
        treatment_build_command_id="treatment-build",
        treatment_stage_command_id="treatment-stage",
    )
    if treatment_history[: len(parent_history)] != parent_history:
        raise OpenH264CandidateGateError("treatment 改写了 parent history")
    return {
        "manifest_sha256": canonical_sha256(manifest),
        "source_case": load_source_case(repo_root),
        "parent": asdict(parent),
        "treatment": asdict(treatment),
        "parent_history_prefix_preserved": True,
        "accepted": accepted,
        "rejected": rejected,
        "provider_calls": 0,
        "credential_read": False,
        "docker_executed": False,
        "formal_evidence_writes": 0,
        "model_tokens": 0,
    }


async def validate_agent_construction() -> dict[str, Any]:
    _base_lifecycle, construction, _r3_runtime, failure_gate = _runtime_modules()
    original = construction.failure_gate.build_runtime_bindings
    if original is not failure_gate.build_runtime_bindings:
        raise OpenH264CandidateGateError("#222 construction binding identity 发生漂移")

    def candidate_bindings():
        parity, observability = original()
        parity.FrozenActionPolicy = _candidate_policy
        return parity, observability

    construction.failure_gate.build_runtime_bindings = candidate_bindings
    try:
        parent_manifest = construction.protocol.load_manifest()
        result = await construction.validate_gate(parent_manifest)
    finally:
        construction.failure_gate.build_runtime_bindings = original
    success = result["success_probe"]
    if (
        success["request_evidence"].get("model.request_started") != 1
        or success["request_evidence"].get("model.request_completed") != 1
        or result["provider_calls"] != 0
        or result["model_tokens"] != 0
        or result["formal_evidence_writes"] != 0
    ):
        raise OpenH264CandidateGateError("OpenH264 construction probe 未闭合")
    return {
        "status": "passed",
        "parent_gate_schema_version": result["schema_version"],
        "candidate_policy": asdict(_candidate_policy()),
        "success_probe": success,
        "failure_probe": result["failure_probe"],
        "cleanup_probe": result["cleanup_probe"],
        "provider_calls": 0,
        "credential_read": False,
        "docker_executed": False,
        "formal_evidence_writes": 0,
        "model_tokens": 0,
    }


def build_docker_adapter(compile_image: str = COMPILE_IMAGE) -> SimpleNamespace:
    base_lifecycle, _construction, _r3_runtime, _failure_gate = _runtime_modules()
    return SimpleNamespace(
        COMPILE_IMAGE=compile_image,
        WORKDIR=WORKDIR,
        REPOSITORY_URL=REPOSITORY_URL,
        COMMIT_SHA=COMMIT_SHA,
        TARGET=TARGET,
        STAGED_ARTIFACT=STAGED_ARTIFACT,
        BUILD_OUTPUT=BUILD_OUTPUT,
        ARTIFACT_TYPE=ARTIFACT_TYPE,
        PARENT_COMMAND=PARENT_COMMAND,
        TREATMENT_BUILD_COMMAND=TREATMENT_BUILD_COMMAND,
        TREATMENT_STAGE_COMMAND=TREATMENT_STAGE_COMMAND,
        CASE_ID=CASE_ID,
        provenance=base_lifecycle.provenance,
        validate_gate_contract=validate_static_gate,
        build_frozen_identity=build_frozen_identity,
        evaluate_parent=evaluate_parent,
        evaluate_treatment=evaluate_treatment,
        build_repair_packet=build_repair_packet,
        validate_repair_packet=validate_repair_packet,
    )


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate", "plan"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args(argv)
    if args.command == "generate":
        manifest = generate_manifest()
        _write_json(args.manifest, manifest)
        _write_json(args.schema, schema_document(manifest))
        result: Any = {"manifest_sha256": canonical_sha256(manifest)}
    elif args.command == "plan":
        manifest = load_manifest(args.manifest)
        result = {
            "manifest_sha256": canonical_sha256(manifest),
            "execution_authorized": False,
            "provider_calls": 0,
            "model_tokens": 0,
            "next_gate": "opt_in_ubuntu_native_docker_lifecycle",
        }
    else:
        manifest = load_manifest(args.manifest)
        result = {
            "manifest_sha256": canonical_sha256(manifest),
            "static_gate": validate_static_gate(),
            "agent_construction": asyncio.run(validate_agent_construction()),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
