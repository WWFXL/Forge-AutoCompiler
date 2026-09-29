#!/usr/bin/env python3
"""生成契约驱动修复 mechanism v1 release-bound 授权身份。"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_contract_driven_repair_mechanism_v1_candidate_protocol as candidate  # noqa: E402

SCHEMA_VERSION = "forge-contract-driven-repair-mechanism-v1-authorized-identity-1.0.0"
DOCUMENT_TYPE = "forge_contract_driven_repair_mechanism_v1_authorized_identity"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/355"
SCIENTIFIC_CONTRACT_RELEASE_REVISION = "a63f328b0cd2771ec656414e697ebbb831391ed9"
PARENT_MANIFEST_CANONICAL_SHA256 = (
    "fc1ec9adfb9961e258e4bb8fad8f1ae2f0f5e1b1356748d53d5783dd55700f8f"
)
PARENT_MANIFEST_FILE_SHA256 = (
    "18edcd30bf50fce775594b2e26333f2c0837013a68ad1af64554788400187e8a"
)
COMPILE_IMAGE = "autocompiler:stage-c-v1"
COMPILE_IMAGE_ID = (
    "sha256:adbef4a26de49e9cd2c361a50b5fe2a000073a343b072ed0e515cc67e6e758b1"
)
DOCKERFILE_SHA256 = "023b38d30139eeacbb6e46643ec2deaa375d8516e43d2d0a8c730475bd3b85ac"
EVIDENCE_DIRECTORY = ".compile-sessions/benchmark-evidence-contract-driven-repair-mechanism-v1-authorized"

PROTOCOL_PATH = (
    "scripts/forge_contract_driven_repair_mechanism_v1_authorized_protocol.py"
)
RUNNER_PATH = "scripts/forge_contract_driven_repair_mechanism_v1_authorized_runner.py"
MANIFEST_PATH = (
    "benchmarks/manifests/cpp-contract-driven-repair-mechanism-v1-authorized.json"
)
SCHEMA_PATH = "benchmarks/schemas/forge-contract-driven-repair-mechanism-v1-authorized.schema.json"
PREREGISTRATION_PATH = (
    "benchmarks/preregistrations/cpp-contract-driven-repair-mechanism-v1-authorized.md"
)

DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_PATH

FROZEN_AUTHORIZED_PATHS = (
    candidate.MANIFEST_PATH,
    candidate.SCHEMA_PATH,
    candidate.PREREGISTRATION_PATH,
    candidate.PROTOCOL_PATH,
    candidate.RUNNER_PATH,
    "benchmarks/fixtures/stage-c-task-qualification-result.json",
    "scripts/forge_runtime_v3_three_arm_qualification.py",
    "backend/tests/test_forge_runtime_v3_three_arm_qualification_docker.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v3.py",
    "backend/packages/harness/deerflow/compile/candidate_verifier.py",
    "scripts/forge_opaque_build_provenance_gate.py",
    "backend/packages/harness/deerflow/compile/external_evaluator_v3.py",
    "backend/packages/harness/deerflow/compile/operations.py",
    "backend/packages/harness/deerflow/tools/bound_compile_tools.py",
    "scripts/require-docker-runtime.sh",
    PREREGISTRATION_PATH,
    PROTOCOL_PATH,
    RUNNER_PATH,
)

SCIENTIFIC_CONTRACT_FIELDS = (
    "provider_candidate",
    "budget_candidate",
    "transport_and_stopping",
    "feedback_contract",
    "checkpoint_contract",
    "strict_endpoint",
    "analysis",
    "tasks",
    "schedule",
    "runtime_candidate",
    "runtime_v3_qualification",
    "interpretation_boundary",
)


class AuthorizedProtocolError(RuntimeError):
    """release binding、父科学合同或授权身份发生漂移。"""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthorizedProtocolError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise AuthorizedProtocolError(f"JSON 顶层必须为对象: {path}")
    return value


def _parent_manifest(repo_root: Path) -> dict[str, Any]:
    path = repo_root / candidate.MANIFEST_PATH
    value = candidate.load_manifest(path, repo_root)
    if candidate.canonical_sha256(value) != PARENT_MANIFEST_CANONICAL_SHA256:
        raise AuthorizedProtocolError("父 candidate canonical identity 发生漂移")
    if candidate.file_sha256(path) != PARENT_MANIFEST_FILE_SHA256:
        raise AuthorizedProtocolError("父 candidate manifest 文件发生漂移")
    return value


def _qualification_environment(repo_root: Path) -> dict[str, Any]:
    result = _load_json(
        repo_root / "benchmarks/fixtures/stage-c-task-qualification-result.json"
    )
    if (
        result.get("status") != "passed"
        or result.get("image_id") != COMPILE_IMAGE_ID
        or result.get("dockerfile_sha256") != DOCKERFILE_SHA256
        or result.get("provider_request_count") != 0
        or result.get("formal_stage_c_attempt_created") is not False
        or result.get("formal_stage_c_evidence_written") is not False
    ):
        raise AuthorizedProtocolError("Stage C qualification environment 发生漂移")
    return {
        "compile_image": COMPILE_IMAGE,
        "image_id": COMPILE_IMAGE_ID,
        "dockerfile_sha256": DOCKERFILE_SHA256,
        "ubuntu_snapshot": result["ubuntu_snapshot"],
        "parallel_jobs": 4,
        "network_policy": "clone_then_network_none",
    }


def _frozen_authorized_components(repo_root: Path) -> dict[str, str]:
    return {
        path: candidate.file_sha256(repo_root / path)
        for path in FROZEN_AUTHORIZED_PATHS
    }


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    parent = _parent_manifest(repo_root)
    value = copy.deepcopy(parent)
    value.update(
        {
            "$schema": "../schemas/forge-contract-driven-repair-mechanism-v1-authorized.schema.json",
            "schema_version": SCHEMA_VERSION,
            "document_type": DOCUMENT_TYPE,
            "issue_url": ISSUE_URL,
            "status": "release_bound_identity_not_execution_authorized",
        }
    )
    value["development_revision"] = {
        "scientific_contract_release_revision": SCIENTIFIC_CONTRACT_RELEASE_REVISION,
        "release_revision_frozen": True,
        "authorized_implementation_revision": None,
        "execution_revision_policy": "clean_descendant_of_scientific_contract_release_and_record_exact_revision",
        "formal_execution_requires_release_branch": "main",
    }
    value["authorization"] = {
        "identity_implementation_authorized": True,
        "availability_execution_authorized": False,
        "formal_collection_execution_authorized": False,
        "credential_read_authorized": False,
        "provider_calls_authorized": False,
        "model_creation_authorized": False,
        "docker_session_creation_authorized": False,
        "formal_attempts_authorized": False,
        "formal_evidence_write_authorized": False,
        "model_tokens_authorized": False,
        "execution_started": False,
    }
    value["candidate_evidence"] = {
        "directory": EVIDENCE_DIRECTORY,
        "create_once": True,
        "must_not_exist_before_authorized_marker": True,
        "historical_evidence_reused": False,
        "writes_authorized": False,
        "availability_marker": "markers/availability.json",
        "batch_marker": "markers/batch.json",
        "attempt_template": "attempts/{sequence:02d}-{opaque_clone_id}/attempt.json",
        "result_template": "attempts/{sequence:02d}-{opaque_clone_id}/result.json",
        "batch_report": "reports/contract-driven-repair-mechanism-v1.json",
    }
    value["parent_candidate"] = {
        "manifest_path": candidate.MANIFEST_PATH,
        "manifest_canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "manifest_file_sha256": PARENT_MANIFEST_FILE_SHA256,
        "scientific_contract_release_revision": SCIENTIFIC_CONTRACT_RELEASE_REVISION,
        "pull_request": "https://github.com/WWFXL/Forge-AutoCompiler/pull/354",
        "read_only": True,
        "schedule_inherited_without_change": True,
        "historical_outcomes_imported": False,
        "historical_evidence_reused": False,
    }
    value["environment_identity"] = _qualification_environment(repo_root)
    value["authorized_runtime"] = {
        "protocol_path": PROTOCOL_PATH,
        "runner_path": RUNNER_PATH,
        "commands_allowed_without_execution_authorization": [
            "validate",
            "plan",
            "preflight",
        ],
        "commands_fail_closed_without_separate_authorization": [
            "availability",
            "batch",
        ],
        "preflight": {
            "before_credential_model_provider_marker_or_docker_session": True,
            "verify_clean_descendant_revision": True,
            "verify_parent_and_component_hashes": True,
            "verify_linux_docker_daemon_compose_and_socket": True,
            "verify_compile_image_id": True,
            "verify_zero_managed_containers_paused_parents_and_images": True,
            "verify_evidence_directory_absent": True,
            "creates_evidence_or_marker": False,
        },
        "availability": copy.deepcopy(
            parent["transport_and_stopping"]["availability_qualification"]
        ),
        "formal_collection": {
            "arm_count": parent["budget_candidate"]["formal_arm_count"],
            "strictly_serial": True,
            "schedule_extension_allowed": False,
            "replacement_or_backfill_allowed": False,
        },
    }
    value["frozen_authorized_components"] = _frozen_authorized_components(repo_root)
    return value


def validate_allowed_delta(
    value: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    parent = _parent_manifest(repo_root)
    for field in SCIENTIFIC_CONTRACT_FIELDS:
        if value.get(field) != parent.get(field):
            raise AuthorizedProtocolError(
                f"authorized identity 改写父科学合同: {field}"
            )
    if value != generate_manifest(repo_root):
        raise AuthorizedProtocolError("authorized identity 包含未预注册差异")
    return {
        "status": "passed",
        "parent_manifest_canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "scientific_contract_release_revision": SCIENTIFIC_CONTRACT_RELEASE_REVISION,
        "project_count": len(value["schedule"]["projects"]),
        "checkpoint_count": len(value["schedule"]["checkpoints"]),
        "formal_arm_count": value["budget_candidate"]["formal_arm_count"],
        "schedule_inherited_without_change": True,
        "provider_calls": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
    }


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-contract-driven-repair-mechanism-v1-authorized.schema.json",
        "title": "Forge contract-driven repair mechanism v1 release-bound authorized identity",
        "const": manifest,
    }


def validate_manifest(
    value: dict[str, Any],
    repo_root: Path = REPO_ROOT,
    *,
    check_schema_file: bool = True,
) -> dict[str, Any]:
    expected = generate_manifest(repo_root)
    if value != expected:
        raise AuthorizedProtocolError("authorized manifest 与确定性生成结果不一致")
    validate_allowed_delta(value, repo_root)
    authorization = value["authorization"]
    if authorization.get("identity_implementation_authorized") is not True or any(
        authorization.get(field) is not False
        for field in (
            "availability_execution_authorized",
            "formal_collection_execution_authorized",
            "credential_read_authorized",
            "provider_calls_authorized",
            "model_creation_authorized",
            "docker_session_creation_authorized",
            "formal_attempts_authorized",
            "formal_evidence_write_authorized",
            "model_tokens_authorized",
            "execution_started",
        )
    ):
        raise AuthorizedProtocolError("执行授权分层未保持关闭")
    if value["development_revision"]["authorized_implementation_revision"] is not None:
        raise AuthorizedProtocolError("实现合并前不得预填 authorized revision")
    schema = generate_schema(value)
    jsonschema.Draft202012Validator.check_schema(schema)
    if check_schema_file:
        stored = _load_json(repo_root / SCHEMA_PATH)
        if stored != schema:
            raise AuthorizedProtocolError("authorized const Schema 发生漂移")
        jsonschema.validate(value, stored)
    return value


def load_manifest(
    path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    return validate_manifest(_load_json(path), repo_root)


def verify_frozen_components(
    manifest: dict[str, Any], repo_root: Path = REPO_ROOT
) -> None:
    validate_manifest(manifest, repo_root)
    if manifest["frozen_authorized_components"] != _frozen_authorized_components(
        repo_root
    ):
        raise AuthorizedProtocolError("authorized component SHA-256 发生漂移")


def plan_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    validated = validate_manifest(manifest)
    return {
        "status": "release_bound_identity_not_execution_authorized",
        "manifest_sha256": candidate.canonical_sha256(validated),
        "scientific_contract_release_revision": SCIENTIFIC_CONTRACT_RELEASE_REVISION,
        "project_count": len(validated["schedule"]["projects"]),
        "checkpoint_count": len(validated["schedule"]["checkpoints"]),
        "formal_arm_count": validated["budget_candidate"]["formal_arm_count"],
        "evidence_directory": EVIDENCE_DIRECTORY,
        "availability_execution_authorized": False,
        "formal_collection_execution_authorized": False,
        "provider_calls": 0,
        "credential_reads": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
    }


def write_artifacts(repo_root: Path = REPO_ROOT) -> None:
    manifest = generate_manifest(repo_root)
    schema = generate_schema(manifest)
    for relative_path, value in ((MANIFEST_PATH, manifest), (SCHEMA_PATH, schema)):
        path = repo_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate", "delta", "plan"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    if args.command == "generate":
        write_artifacts()
    manifest = load_manifest(args.manifest)
    if args.command == "delta":
        result: Any = validate_allowed_delta(manifest)
    elif args.command == "plan":
        result = plan_summary(manifest)
    else:
        result = {
            "status": "generated" if args.command == "generate" else "valid",
            "manifest_sha256": candidate.canonical_sha256(manifest),
            "provider_calls": 0,
            "credential_reads": 0,
            "formal_attempts": 0,
            "formal_evidence_writes": 0,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
