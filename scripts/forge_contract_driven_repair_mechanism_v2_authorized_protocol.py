#!/usr/bin/env python3
"""生成并校验 mechanism v2 release-bound、未执行授权身份。"""

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

import forge_contract_driven_repair_mechanism_v2_candidate_protocol as candidate  # noqa: E402

SCHEMA_VERSION = "forge-contract-driven-repair-mechanism-v2-authorized-identity-1.0.0"
DOCUMENT_TYPE = "forge_contract_driven_repair_mechanism_v2_authorized_identity"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/369"
SCIENTIFIC_CONTRACT_RELEASE_REVISION = "70b257c840f4065285c047ba6207ffe99f8dcb36"
PARENT_MANIFEST_CANONICAL_SHA256 = (
    "40ea47064e7345a03c1d4dbbe13316f4e3575e29c561709d6561a135c4e25f0d"
)
PARENT_MANIFEST_FILE_SHA256 = (
    "9d60eeb76f4426fca1dc44f759986a4d4f93ba496be7cc8158ac3d88c0cb22c4"
)

PROTOCOL_PATH = (
    "scripts/forge_contract_driven_repair_mechanism_v2_authorized_protocol.py"
)
RUNNER_PATH = "scripts/forge_contract_driven_repair_mechanism_v2_authorized_runner.py"
MANIFEST_PATH = (
    "benchmarks/manifests/cpp-contract-driven-repair-mechanism-v2-authorized.json"
)
SCHEMA_PATH = "benchmarks/schemas/forge-contract-driven-repair-mechanism-v2-authorized.schema.json"
PREREGISTRATION_PATH = (
    "benchmarks/preregistrations/cpp-contract-driven-repair-mechanism-v2-authorized.md"
)
TEST_PATH = "backend/tests/test_forge_contract_driven_repair_mechanism_v2_authorized.py"

DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_PATH

FROZEN_AUTHORIZED_COMPONENT_PATHS = (
    candidate.MANIFEST_PATH,
    candidate.SCHEMA_PATH,
    candidate.PREREGISTRATION_PATH,
    candidate.PROTOCOL_PATH,
    candidate.RUNNER_PATH,
    "backend/tests/test_forge_contract_driven_repair_mechanism_v2_candidate.py",
    "backend/tests/test_forge_contract_driven_repair_mechanism_v2_candidate_docker.py",
    PREREGISTRATION_PATH,
    PROTOCOL_PATH,
    RUNNER_PATH,
    TEST_PATH,
)


class AuthorizedProtocolError(RuntimeError):
    """v2 release、父 candidate 或未授权边界发生漂移。"""


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
    if candidate.candidate.canonical_sha256(value) != (
        PARENT_MANIFEST_CANONICAL_SHA256
    ):
        raise AuthorizedProtocolError("父 v2 candidate canonical SHA-256 漂移")
    if candidate.candidate.file_sha256(path) != PARENT_MANIFEST_FILE_SHA256:
        raise AuthorizedProtocolError("父 v2 candidate manifest 文件 SHA-256 漂移")
    return value


def _frozen_authorized_components(repo_root: Path) -> dict[str, str]:
    return {
        path: candidate.candidate.file_sha256(repo_root / path)
        for path in FROZEN_AUTHORIZED_COMPONENT_PATHS
    }


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    parent = _parent_manifest(repo_root)
    value = copy.deepcopy(parent)
    value.update(
        {
            "$schema": "../schemas/forge-contract-driven-repair-mechanism-v2-authorized.schema.json",
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
        "execution_revision_policy": (
            "future_execution_release_must_be_clean_main_equal_origin_main_descendant_of_scientific_contract_release"
        ),
        "execution_requires_release_branch": "main",
    }
    value["authorization"] = {
        "identity_implementation_authorized": True,
        "availability_execution_completed": False,
        "credential_read_authorized": False,
        "provider_calls_authorized": False,
        "model_creation_authorized": False,
        "model_tokens_authorized": False,
        "docker_session_creation_authorized": False,
        "formal_collection_execution_authorized": False,
        "formal_attempts_authorized": False,
        "formal_evidence_write_authorized": False,
        "execution_started": False,
    }
    value["parent_candidate"] = {
        "manifest_path": candidate.MANIFEST_PATH,
        "manifest_canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "manifest_file_sha256": PARENT_MANIFEST_FILE_SHA256,
        "scientific_contract_release_revision": SCIENTIFIC_CONTRACT_RELEASE_REVISION,
        "schedule_inherited_without_change": True,
        "opaque_ids_inherited_without_change": True,
        "evidence_directory_inherited_without_change": True,
        "historical_evidence_reused": False,
        "historical_outcomes_imported": False,
        "read_only": True,
    }
    value["availability_execution_runtime"] = {
        "protocol_path": PROTOCOL_PATH,
        "runner_path": RUNNER_PATH,
        "commands": ["availability"],
        "availability_execution_authorized": False,
        "historical_availability_reused": False,
        "fail_closed_without_separate_authorization": True,
    }
    value["independent_runtime"] = {
        "commands_allowed_without_execution_authorization": [
            "validate",
            "plan",
            "preflight",
        ],
        "commands_fail_closed_without_separate_authorization": [
            "availability",
            "batch",
            "report",
            "audit",
        ],
        "provider_calls": 0,
        "credential_reads": 0,
        "docker_sessions_created": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
    }
    formal_execution = copy.deepcopy(value["formal_execution"])
    formal_execution.update(
        {
            "protocol_path": PROTOCOL_PATH,
            "runner_path": RUNNER_PATH,
            "execution_authorized": False,
        }
    )
    formal_execution["preflight"] = {
        "before_credential_model_provider_marker_or_docker_session": True,
        "require_branch_after_release": "main",
        "require_head_equals_origin_main_after_release": True,
        "require_clean_descendant_revision": SCIENTIFIC_CONTRACT_RELEASE_REVISION,
        "verify_parent_and_component_hashes": True,
        "verify_compile_image_id": True,
        "verify_zero_managed_resources": True,
        "verify_old_evidence_inventory_read_only": True,
        "verify_new_evidence_directory_absent": True,
        "verify_provider_config_or_credential": False,
        "creates_evidence_or_marker": False,
    }
    value["formal_execution"] = formal_execution
    frozen = _frozen_authorized_components(repo_root)
    value["frozen_authorized_components"] = frozen
    value["frozen_formal_execution_components"] = {
        **copy.deepcopy(parent["frozen_formal_execution_components"]),
        PROTOCOL_PATH: frozen[PROTOCOL_PATH],
        RUNNER_PATH: frozen[RUNNER_PATH],
    }
    return value


def validate_allowed_delta(
    value: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    parent = _parent_manifest(repo_root)
    for field in candidate.source.parent.parent.parent.SCIENTIFIC_CONTRACT_FIELDS:
        if value.get(field) != parent.get(field):
            raise AuthorizedProtocolError(
                f"release-bound identity 改写父科学合同: {field}"
            )
    for field in (
        "formal_execution_tasks",
        "budget_candidate",
        "transport_and_stopping",
        "candidate_evidence",
        "independent_identity",
    ):
        if value.get(field) != parent.get(field):
            raise AuthorizedProtocolError(
                f"release-bound identity 改写父冻结字段: {field}"
            )
    if value != generate_manifest(repo_root):
        raise AuthorizedProtocolError("release-bound identity 包含未预注册差异")
    return {
        "status": "passed",
        "parent_manifest_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "scientific_contract_release_revision": SCIENTIFIC_CONTRACT_RELEASE_REVISION,
        "arm_count": 36,
        "historical_outcomes_imported": False,
        "formal_collection_execution_authorized": False,
        "provider_calls": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
    }


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-contract-driven-repair-mechanism-v2-authorized.schema.json",
        "title": "Forge contract-driven repair mechanism v2 release-bound identity",
        "const": manifest,
    }


def validate_manifest(
    value: dict[str, Any],
    repo_root: Path = REPO_ROOT,
    *,
    check_schema_file: bool = True,
) -> dict[str, Any]:
    if value != generate_manifest(repo_root):
        raise AuthorizedProtocolError("release-bound manifest 与确定性生成结果不一致")
    validate_allowed_delta(value, repo_root)
    authorization = value["authorization"]
    if authorization.get("identity_implementation_authorized") is not True:
        raise AuthorizedProtocolError("release-bound identity 实现授权未冻结")
    for field, actual in authorization.items():
        if field == "identity_implementation_authorized":
            continue
        if actual is not False:
            raise AuthorizedProtocolError(
                f"release-bound identity 包含真实执行授权: {field}"
            )
    availability = value["availability_execution"]
    for field in (
        "credential_read_authorized",
        "execution_authorized",
        "marker_write_authorized",
        "model_creation_authorized",
        "model_tokens_authorized",
        "provider_calls_authorized",
    ):
        if availability.get(field) is not False:
            raise AuthorizedProtocolError(
                f"release-bound availability 包含执行授权: {field}"
            )
    schema = generate_schema(value)
    jsonschema.Draft202012Validator.check_schema(schema)
    if check_schema_file:
        stored = _load_json(repo_root / SCHEMA_PATH)
        if stored != schema:
            raise AuthorizedProtocolError("release-bound const Schema 漂移")
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
    if manifest["frozen_authorized_components"] != (
        _frozen_authorized_components(repo_root)
    ):
        raise AuthorizedProtocolError("release-bound component SHA-256 漂移")


def plan_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    value = validate_manifest(manifest)
    return {
        "status": "release_bound_identity_not_execution_authorized",
        "manifest_sha256": candidate.candidate.canonical_sha256(value),
        "parent_manifest_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "scientific_contract_release_revision": SCIENTIFIC_CONTRACT_RELEASE_REVISION,
        "project_count": len(value["schedule"]["projects"]),
        "checkpoint_count": len(value["schedule"]["checkpoints"]),
        "arm_count": sum(
            len(checkpoint["arms"]) for checkpoint in value["schedule"]["checkpoints"]
        ),
        "execution_authorization_required": True,
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
            "manifest_sha256": candidate.candidate.canonical_sha256(manifest),
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
