#!/usr/bin/env python3
"""生成契约驱动修复 mechanism v1 availability qualification 候选 amendment。"""

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

import forge_contract_driven_repair_mechanism_v1_authorized_protocol as parent  # noqa: E402

SCHEMA_VERSION = (
    "forge-contract-driven-repair-mechanism-v1-availability-candidate-1.0.0"
)
DOCUMENT_TYPE = "forge_contract_driven_repair_mechanism_v1_availability_candidate"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/357"
IMPLEMENTATION_RELEASE_REVISION = "25b358814e4749031cc7fd3d83139a79d884f7a4"
PARENT_MANIFEST_CANONICAL_SHA256 = (
    "840eac32711fc69e88609aa00b7e308fd7854bc2b7f5f4c3bffc6b5d0d39a0a0"
)
PARENT_MANIFEST_FILE_SHA256 = (
    "3290255fb2414a22a6133696ac96e2f0f2760b943e0377c3c2612380c04dde23"
)

PROTOCOL_PATH = "scripts/forge_contract_driven_repair_mechanism_v1_availability_candidate_protocol.py"
RUNNER_PATH = (
    "scripts/forge_contract_driven_repair_mechanism_v1_availability_candidate_runner.py"
)
MANIFEST_PATH = "benchmarks/manifests/cpp-contract-driven-repair-mechanism-v1-availability-candidate.json"
SCHEMA_PATH = "benchmarks/schemas/forge-contract-driven-repair-mechanism-v1-availability-candidate.schema.json"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-contract-driven-repair-mechanism-v1-availability-candidate.md"

DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_PATH

FROZEN_CANDIDATE_PATHS = (
    parent.MANIFEST_PATH,
    parent.SCHEMA_PATH,
    parent.PREREGISTRATION_PATH,
    parent.PROTOCOL_PATH,
    parent.RUNNER_PATH,
    PREREGISTRATION_PATH,
    PROTOCOL_PATH,
    RUNNER_PATH,
)


class AvailabilityCandidateProtocolError(RuntimeError):
    """父身份、implementation release 或 availability 合同发生漂移。"""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AvailabilityCandidateProtocolError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise AvailabilityCandidateProtocolError(f"JSON 顶层必须为对象: {path}")
    return value


def _parent_manifest(repo_root: Path) -> dict[str, Any]:
    path = repo_root / parent.MANIFEST_PATH
    value = parent.load_manifest(path, repo_root)
    if parent.candidate.canonical_sha256(value) != PARENT_MANIFEST_CANONICAL_SHA256:
        raise AvailabilityCandidateProtocolError(
            "父 authorized canonical identity 发生漂移"
        )
    if parent.candidate.file_sha256(path) != PARENT_MANIFEST_FILE_SHA256:
        raise AvailabilityCandidateProtocolError("父 authorized manifest 文件发生漂移")
    return value


def _frozen_candidate_components(repo_root: Path) -> dict[str, str]:
    return {
        path: parent.candidate.file_sha256(repo_root / path)
        for path in FROZEN_CANDIDATE_PATHS
    }


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    parent_manifest = _parent_manifest(repo_root)
    value = copy.deepcopy(parent_manifest)
    value.update(
        {
            "$schema": "../schemas/forge-contract-driven-repair-mechanism-v1-availability-candidate.schema.json",
            "schema_version": SCHEMA_VERSION,
            "document_type": DOCUMENT_TYPE,
            "issue_url": ISSUE_URL,
            "status": "availability_qualification_candidate_not_execution_authorized",
        }
    )
    value["development_revision"] = {
        "scientific_contract_release_revision": parent.SCIENTIFIC_CONTRACT_RELEASE_REVISION,
        "authorized_implementation_revision": IMPLEMENTATION_RELEASE_REVISION,
        "implementation_revision_frozen": True,
        "execution_revision_policy": "clean_descendant_of_authorized_implementation_and_record_exact_revision",
        "formal_execution_requires_release_branch": "main",
    }
    value["authorization"] = {
        "identity_implementation_authorized": True,
        "availability_candidate_implementation_authorized": True,
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
    value["parent_authorized"] = {
        "manifest_path": parent.MANIFEST_PATH,
        "manifest_canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "manifest_file_sha256": PARENT_MANIFEST_FILE_SHA256,
        "implementation_release_revision": IMPLEMENTATION_RELEASE_REVISION,
        "pull_request": "https://github.com/WWFXL/Forge-AutoCompiler/pull/356",
        "read_only": True,
        "scientific_contract_inherited_without_change": True,
        "evidence_identity_inherited_without_change": True,
        "historical_outcomes_imported": False,
        "historical_evidence_reused": False,
    }
    availability = copy.deepcopy(
        parent_manifest["transport_and_stopping"]["availability_qualification"]
    )
    value["availability_candidate"] = {
        "contract": availability,
        "provider_profile": parent_manifest["provider_candidate"]["profile"],
        "actual_model": parent_manifest["provider_candidate"]["actual_model"],
        "max_recorded_tokens": None,
        "token_accounting": copy.deepcopy(
            parent_manifest["budget_candidate"]["token_accounting"]
        ),
        "execution_authorized": False,
        "credential_read_authorized": False,
        "provider_calls_authorized": False,
        "model_creation_authorized": False,
        "model_tokens_authorized": False,
        "marker_write_authorized": False,
        "formal_batch_creation_authorized": False,
        "result_observed": False,
    }
    value["availability_candidate_runtime"] = {
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
            "verify_clean_descendant_revision": IMPLEMENTATION_RELEASE_REVISION,
            "verify_parent_and_component_hashes": True,
            "verify_linux_docker_daemon_compose_and_socket": True,
            "verify_compile_image_id": True,
            "verify_zero_managed_containers_paused_parents_and_images": True,
            "verify_evidence_directory_absent": True,
            "creates_evidence_or_marker": False,
        },
    }
    value["frozen_availability_candidate_components"] = _frozen_candidate_components(
        repo_root
    )
    return value


def validate_allowed_delta(
    value: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    parent_manifest = _parent_manifest(repo_root)
    for field in parent.SCIENTIFIC_CONTRACT_FIELDS:
        if value.get(field) != parent_manifest.get(field):
            raise AvailabilityCandidateProtocolError(
                f"availability candidate 改写父科学合同: {field}"
            )
    if value.get("candidate_evidence") != parent_manifest.get("candidate_evidence"):
        raise AvailabilityCandidateProtocolError(
            "availability candidate 改写 evidence identity"
        )
    if (
        value.get("availability_candidate", {}).get("contract")
        != parent_manifest["transport_and_stopping"]["availability_qualification"]
    ):
        raise AvailabilityCandidateProtocolError("availability request 合同发生漂移")
    if value != generate_manifest(repo_root):
        raise AvailabilityCandidateProtocolError(
            "availability candidate 包含未预注册差异"
        )
    return {
        "status": "passed",
        "parent_manifest_canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "authorized_implementation_revision": IMPLEMENTATION_RELEASE_REVISION,
        "availability_logical_request_count": 1,
        "availability_max_request_attempts": 2,
        "availability_execution_authorized": False,
        "formal_collection_execution_authorized": False,
        "provider_calls": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
    }


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-contract-driven-repair-mechanism-v1-availability-candidate.schema.json",
        "title": "Forge contract-driven repair mechanism v1 availability qualification candidate",
        "const": manifest,
    }


def validate_manifest(
    value: dict[str, Any],
    repo_root: Path = REPO_ROOT,
    *,
    check_schema_file: bool = True,
) -> dict[str, Any]:
    if value != generate_manifest(repo_root):
        raise AvailabilityCandidateProtocolError(
            "availability candidate manifest 与确定性生成结果不一致"
        )
    validate_allowed_delta(value, repo_root)
    authorization = value["authorization"]
    if authorization.get("identity_implementation_authorized") is not True:
        raise AvailabilityCandidateProtocolError("父 identity implementation 授权丢失")
    if (
        authorization.get("availability_candidate_implementation_authorized")
        is not True
    ):
        raise AvailabilityCandidateProtocolError("availability candidate 实现未获授权")
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
    ):
        if authorization.get(field) is not False:
            raise AvailabilityCandidateProtocolError("执行授权分层未保持关闭")
    contract = value["availability_candidate"]["contract"]
    if (
        contract["logical_request_count"] != 1
        or contract["max_request_attempts_including_transport_retry"] != 2
        or contract["request"] != "Reply exactly with FORGE_READY."
        or contract["expected_response"] != "FORGE_READY"
        or contract["experiment_content_included"] is not False
    ):
        raise AvailabilityCandidateProtocolError(
            "availability 合同不再是唯一无实验内容请求"
        )
    schema = generate_schema(value)
    jsonschema.Draft202012Validator.check_schema(schema)
    if check_schema_file:
        stored = _load_json(repo_root / SCHEMA_PATH)
        if stored != schema:
            raise AvailabilityCandidateProtocolError(
                "availability const Schema 发生漂移"
            )
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
    if manifest["frozen_availability_candidate_components"] != (
        _frozen_candidate_components(repo_root)
    ):
        raise AvailabilityCandidateProtocolError(
            "availability candidate component SHA-256 发生漂移"
        )


def plan_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    validated = validate_manifest(manifest)
    contract = validated["availability_candidate"]["contract"]
    return {
        "status": "availability_qualification_candidate_not_execution_authorized",
        "manifest_sha256": parent.candidate.canonical_sha256(validated),
        "parent_manifest_canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "authorized_implementation_revision": IMPLEMENTATION_RELEASE_REVISION,
        "provider_profile": validated["availability_candidate"]["provider_profile"],
        "actual_model": validated["availability_candidate"]["actual_model"],
        "logical_request_count": contract["logical_request_count"],
        "max_request_attempts": contract[
            "max_request_attempts_including_transport_retry"
        ],
        "evidence_directory": validated["candidate_evidence"]["directory"],
        "availability_execution_authorized": False,
        "formal_collection_execution_authorized": False,
        "provider_calls": 0,
        "credential_reads": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
        "model_tokens": 0,
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
            "manifest_sha256": parent.candidate.canonical_sha256(manifest),
            "provider_calls": 0,
            "credential_reads": 0,
            "formal_attempts": 0,
            "formal_evidence_writes": 0,
            "model_tokens": 0,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
