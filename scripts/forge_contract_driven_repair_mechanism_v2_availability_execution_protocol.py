#!/usr/bin/env python3
"""生成并校验 mechanism v2 独立 availability 授权执行身份。"""

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

import forge_contract_driven_repair_mechanism_v2_authorized_protocol as parent  # noqa: E402

SCHEMA_VERSION = (
    "forge-contract-driven-repair-mechanism-v2-availability-execution-1.0.0"
)
DOCUMENT_TYPE = "forge_contract_driven_repair_mechanism_v2_availability_execution"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/371"
RELEASE_BOUND_IDENTITY_REVISION = "646ff59a67b27038b241358261bc92adcb100eb6"
PARENT_MANIFEST_CANONICAL_SHA256 = (
    "9ce0b7ebef27f03c4c918e4e20577cacfac971a947e60e9a787914bdc6e08197"
)
PARENT_MANIFEST_FILE_SHA256 = (
    "945be3f344a97cc8fb3cf16aa3a89dc18e8ec3525519f490bedb73e3254c9118"
)

PROTOCOL_PATH = "scripts/forge_contract_driven_repair_mechanism_v2_availability_execution_protocol.py"
RUNNER_PATH = (
    "scripts/forge_contract_driven_repair_mechanism_v2_availability_execution_runner.py"
)
MANIFEST_PATH = "benchmarks/manifests/cpp-contract-driven-repair-mechanism-v2-availability-execution.json"
SCHEMA_PATH = "benchmarks/schemas/forge-contract-driven-repair-mechanism-v2-availability-execution.schema.json"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-contract-driven-repair-mechanism-v2-availability-execution.md"
TEST_PATH = "backend/tests/test_forge_contract_driven_repair_mechanism_v2_availability_execution.py"

DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_PATH

FROZEN_AVAILABILITY_COMPONENT_PATHS = (
    parent.MANIFEST_PATH,
    parent.SCHEMA_PATH,
    parent.PREREGISTRATION_PATH,
    parent.PROTOCOL_PATH,
    parent.RUNNER_PATH,
    parent.TEST_PATH,
    "config.yaml",
    "backend/packages/harness/deerflow/config/__init__.py",
    "backend/packages/harness/deerflow/config/app_config.py",
    "backend/packages/harness/deerflow/models/factory.py",
    "backend/packages/harness/deerflow/compile/evidence.py",
    PREREGISTRATION_PATH,
    PROTOCOL_PATH,
    RUNNER_PATH,
    TEST_PATH,
)


class AvailabilityExecutionProtocolError(RuntimeError):
    """父 identity、release、Provider 或 availability 合同发生漂移。"""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AvailabilityExecutionProtocolError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise AvailabilityExecutionProtocolError(f"JSON 顶层必须为对象: {path}")
    return value


def _parent_manifest(repo_root: Path) -> dict[str, Any]:
    path = repo_root / parent.MANIFEST_PATH
    value = parent.load_manifest(path, repo_root)
    if parent.candidate.candidate.canonical_sha256(value) != (
        PARENT_MANIFEST_CANONICAL_SHA256
    ):
        raise AvailabilityExecutionProtocolError(
            "父 release-bound canonical SHA-256 漂移"
        )
    if parent.candidate.candidate.file_sha256(path) != PARENT_MANIFEST_FILE_SHA256:
        raise AvailabilityExecutionProtocolError(
            "父 release-bound manifest 文件 SHA-256 漂移"
        )
    return value


def _frozen_availability_components(repo_root: Path) -> dict[str, str]:
    return {
        path: parent.candidate.candidate.file_sha256(repo_root / path)
        for path in FROZEN_AVAILABILITY_COMPONENT_PATHS
    }


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    parent_manifest = _parent_manifest(repo_root)
    value = copy.deepcopy(parent_manifest)
    value.update(
        {
            "$schema": "../schemas/forge-contract-driven-repair-mechanism-v2-availability-execution.schema.json",
            "schema_version": SCHEMA_VERSION,
            "document_type": DOCUMENT_TYPE,
            "issue_url": ISSUE_URL,
            "status": "availability_execution_authorized_not_started",
        }
    )
    value["development_revision"] = {
        "scientific_contract_release_revision": (
            parent.SCIENTIFIC_CONTRACT_RELEASE_REVISION
        ),
        "release_bound_identity_revision": RELEASE_BOUND_IDENTITY_REVISION,
        "availability_execution_implementation_revision": None,
        "execution_revision_policy": (
            "clean_main_equal_origin_main_descendant_of_release_bound_identity"
        ),
        "execution_requires_release_branch": "main",
    }
    value["authorization"] = {
        "identity_implementation_authorized": True,
        "availability_execution_implementation_authorized": True,
        "availability_execution_authorized": True,
        "availability_execution_completed": False,
        "credential_read_authorized": True,
        "provider_calls_authorized": True,
        "model_creation_authorized": True,
        "model_tokens_authorized": True,
        "availability_marker_write_authorized": True,
        "docker_session_creation_authorized": False,
        "formal_collection_execution_authorized": False,
        "formal_attempts_authorized": False,
        "formal_evidence_write_authorized": False,
        "execution_started": False,
    }
    evidence = copy.deepcopy(parent_manifest["candidate_evidence"])
    evidence.update(
        {
            "writes_authorized": True,
            "availability_marker_write_authorized": True,
            "formal_evidence_write_authorized": False,
            "authorized_write_paths": [evidence["availability_marker"]],
        }
    )
    value["candidate_evidence"] = evidence
    value["parent_release_bound_identity"] = {
        "manifest_path": parent.MANIFEST_PATH,
        "manifest_canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "manifest_file_sha256": PARENT_MANIFEST_FILE_SHA256,
        "release_bound_identity_revision": RELEASE_BOUND_IDENTITY_REVISION,
        "pull_request": "https://github.com/WWFXL/Forge-AutoCompiler/pull/370",
        "read_only": True,
        "scientific_contract_inherited_without_change": True,
        "schedule_inherited_without_change": True,
        "opaque_ids_inherited_without_change": True,
        "evidence_directory_inherited_without_change": True,
        "historical_availability_reused": False,
        "historical_outcomes_imported": False,
        "historical_evidence_reused": False,
    }
    availability = copy.deepcopy(parent_manifest["availability_execution"])
    availability.update(
        {
            "status": "independent_execution_authorized_not_started",
            "execution_authorized": True,
            "credential_read_authorized": True,
            "provider_calls_authorized": True,
            "model_creation_authorized": True,
            "model_tokens_authorized": True,
            "marker_write_authorized": True,
            "formal_batch_creation_authorized": False,
            "result_observed": False,
        }
    )
    value["availability_execution"] = availability
    value["availability_execution_runtime"] = {
        "protocol_path": PROTOCOL_PATH,
        "runner_path": RUNNER_PATH,
        "commands": [
            "validate",
            "plan",
            "preflight",
            "availability",
            "audit",
            "batch",
            "report",
        ],
        "blocked_commands": ["batch", "report"],
        "formal_collection_fails_closed": True,
        "preflight": {
            "before_model_provider_marker_or_docker_session": True,
            "require_branch": "main",
            "require_head_equals_origin_main": True,
            "require_clean_descendant_revision": RELEASE_BOUND_IDENTITY_REVISION,
            "verify_parent_and_component_hashes": True,
            "verify_linux_docker_daemon_compose_and_socket": True,
            "verify_compile_image_id": True,
            "verify_zero_managed_resources": True,
            "verify_old_evidence_inventory_read_only": True,
            "verify_new_evidence_directory_absent": True,
            "verify_provider_config": True,
            "verify_credential_presence_without_value_retention": True,
            "creates_evidence_or_marker": False,
        },
    }
    value["independent_runtime"] = {
        "commands_allowed": ["validate", "plan", "preflight", "availability", "audit"],
        "commands_fail_closed": ["batch", "report"],
        "formal_collection_execution_authorized": False,
    }
    value["frozen_availability_execution_components"] = _frozen_availability_components(
        repo_root
    )
    return value


def validate_allowed_delta(
    value: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    parent_manifest = _parent_manifest(repo_root)
    for (
        field
    ) in parent.candidate.source.parent.parent.parent.SCIENTIFIC_CONTRACT_FIELDS:
        if value.get(field) != parent_manifest.get(field):
            raise AvailabilityExecutionProtocolError(
                f"availability execution 改写父科学合同: {field}"
            )
    for field in (
        "formal_execution_tasks",
        "budget_candidate",
        "transport_and_stopping",
        "independent_identity",
        "formal_execution",
    ):
        if value.get(field) != parent_manifest.get(field):
            raise AvailabilityExecutionProtocolError(
                f"availability execution 改写父冻结字段: {field}"
            )
    if (
        value["candidate_evidence"]["directory"]
        != parent_manifest["candidate_evidence"]["directory"]
    ):
        raise AvailabilityExecutionProtocolError(
            "availability execution 改写 evidence 目录"
        )
    if (
        value["availability_execution"]["contract"]
        != parent_manifest["availability_execution"]["contract"]
    ):
        raise AvailabilityExecutionProtocolError("availability request 合同发生漂移")
    if value != generate_manifest(repo_root):
        raise AvailabilityExecutionProtocolError(
            "availability execution 包含未预注册差异"
        )
    return {
        "status": "passed",
        "parent_manifest_canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "release_bound_identity_revision": RELEASE_BOUND_IDENTITY_REVISION,
        "availability_logical_request_count": 1,
        "availability_max_request_attempts": 2,
        "availability_execution_authorized": True,
        "formal_collection_execution_authorized": False,
        "provider_calls": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
    }


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-contract-driven-repair-mechanism-v2-availability-execution.schema.json",
        "title": "Forge contract-driven repair mechanism v2 availability execution",
        "const": manifest,
    }


def validate_manifest(
    value: dict[str, Any],
    repo_root: Path = REPO_ROOT,
    *,
    check_schema_file: bool = True,
) -> dict[str, Any]:
    if value != generate_manifest(repo_root):
        raise AvailabilityExecutionProtocolError(
            "availability execution manifest 与确定性生成结果不一致"
        )
    validate_allowed_delta(value, repo_root)
    authorization = value["authorization"]
    authorized = {
        "identity_implementation_authorized",
        "availability_execution_implementation_authorized",
        "availability_execution_authorized",
        "credential_read_authorized",
        "provider_calls_authorized",
        "model_creation_authorized",
        "model_tokens_authorized",
        "availability_marker_write_authorized",
    }
    for field, actual in authorization.items():
        expected = field in authorized
        if actual is not expected:
            raise AvailabilityExecutionProtocolError(
                f"availability authorization 漂移: {field}"
            )
    execution = value["availability_execution"]
    for field in (
        "execution_authorized",
        "credential_read_authorized",
        "provider_calls_authorized",
        "model_creation_authorized",
        "model_tokens_authorized",
        "marker_write_authorized",
    ):
        if execution.get(field) is not True:
            raise AvailabilityExecutionProtocolError(
                f"availability execution 权限未冻结: {field}"
            )
    if (
        execution["actual_model"] != "deepseek-flash"
        or execution["max_recorded_tokens"] is not None
        or execution["sdk_retry_count"] != 0
        or execution["manual_retry_allowed"] is not False
        or execution["fallback_enabled"] is not False
        or execution["parallel_tool_calls"] is not False
        or execution["tool_side_effect_count"] != 0
        or execution["formal_batch_creation_authorized"] is not False
    ):
        raise AvailabilityExecutionProtocolError("availability 执行合同发生漂移")
    if value["candidate_evidence"]["authorized_write_paths"] != [
        value["candidate_evidence"]["availability_marker"]
    ]:
        raise AvailabilityExecutionProtocolError(
            "availability evidence 写入范围发生漂移"
        )
    schema = generate_schema(value)
    jsonschema.Draft202012Validator.check_schema(schema)
    if check_schema_file:
        stored = _load_json(repo_root / SCHEMA_PATH)
        if stored != schema:
            raise AvailabilityExecutionProtocolError(
                "availability execution const Schema 漂移"
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
    if manifest["frozen_availability_execution_components"] != (
        _frozen_availability_components(repo_root)
    ):
        raise AvailabilityExecutionProtocolError(
            "availability execution component SHA-256 漂移"
        )


def plan_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    value = validate_manifest(manifest)
    execution = value["availability_execution"]
    return {
        "status": "availability_execution_authorized_not_started",
        "manifest_sha256": parent.candidate.candidate.canonical_sha256(value),
        "parent_manifest_canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "release_bound_identity_revision": RELEASE_BOUND_IDENTITY_REVISION,
        "provider_profile": execution["provider_profile"],
        "actual_model": execution["actual_model"],
        "logical_request_count": execution["contract"]["logical_request_count"],
        "max_request_attempts": execution["contract"][
            "max_request_attempts_including_transport_retry"
        ],
        "max_recorded_tokens": execution["max_recorded_tokens"],
        "evidence_directory": value["candidate_evidence"]["directory"],
        "availability_marker": execution["marker"],
        "availability_execution_authorized": True,
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
            "manifest_sha256": parent.candidate.candidate.canonical_sha256(manifest),
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
