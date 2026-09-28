#!/usr/bin/env python3
"""生成并校验 Stage C v8 workspace remediation authorized canary identity。"""

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

import forge_stage_c_v8_workspace_remediation_protocol as parent  # noqa: E402

SCHEMA_VERSION = "forge-stage-c-v8-workspace-remediation-canary-authorized-1.0.0"
DOCUMENT_TYPE = "forge_stage_c_v8_workspace_remediation_canary_authorized"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/347"
AUTHORIZATION_BASELINE_COMMIT = "efc79e306960f25b96336f13b8cae1b6d8df2eb9"

PARENT_MANIFEST_PATH = parent.MANIFEST_RELATIVE_PATH
PARENT_SCHEMA_PATH = parent.SCHEMA_RELATIVE_PATH
PARENT_PROTOCOL_PATH = parent.PROTOCOL_PATH
PARENT_RUNNER_PATH = parent.RUNNER_PATH
PARENT_PREREGISTRATION_PATH = parent.PREREGISTRATION_PATH
PARENT_MANIFEST_CANONICAL_SHA256 = "4ed33a827d2c801ed1b0f56c717ee332f0a65141ed8d07d05326ff373dd07f6d"
PARENT_MANIFEST_FILE_SHA256 = "fd45d1a90a8880ad0becff5d9f11fa8f6e1eea305f33e820f986a333d5f4e981"
PARENT_SCHEMA_FILE_SHA256 = "f8f5496ac1cb1bf691e47b3e1d350cdebf29140bbb4c8b57acef4dab37817190"
PARENT_PROTOCOL_FILE_SHA256 = "5862ccf4bc86ebc0d58a58c74cfff66032d900af58a44b5c2a54a8643cf4c2aa"
PARENT_RUNNER_FILE_SHA256 = "5ac881c3ee1e9b7cbacd54ac1af86cf0a5e677828704c7b4d021bbbbd7eac64c"
PARENT_PREREGISTRATION_FILE_SHA256 = "32d86e3d9335c29c1b4374d88724f2c7123141f6e192ae42690a0d8e2397fa18"

MANIFEST_RELATIVE_PATH = "benchmarks/manifests/cpp-stage-c-v8-workspace-remediation-canary-authorized.json"
SCHEMA_RELATIVE_PATH = "benchmarks/schemas/forge-stage-c-v8-workspace-remediation-canary-authorized.schema.json"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-stage-c-v8-workspace-remediation-canary-authorized.md"
PROTOCOL_PATH = "scripts/forge_stage_c_v8_workspace_remediation_authorized_protocol.py"
RUNNER_PATH = "scripts/forge_stage_c_v8_workspace_remediation_authorized_runner.py"
EVIDENCE_DIRECTORY_RELATIVE = ".compile-sessions/benchmark-evidence-stage-c-v8-workspace-remediation-canary-authorized-v1"

DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_RELATIVE_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_RELATIVE_PATH


class StageCV8AuthorizedProtocolError(RuntimeError):
    """授权 identity、父 candidate 或允许差异无效。"""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageCV8AuthorizedProtocolError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise StageCV8AuthorizedProtocolError(f"JSON 根节点必须是对象: {path}")
    return value


def file_sha256(path: Path) -> str:
    return parent.parent.parent.file_sha256(path)


def canonical_sha256(value: dict[str, Any]) -> str:
    return parent.parent.parent.canonical_sha256(value)


def _require_file_hash(repo_root: Path, relative_path: str, expected: str) -> None:
    path = repo_root / relative_path
    if path.is_symlink() or not path.is_file() or file_sha256(path) != expected:
        raise StageCV8AuthorizedProtocolError(f"冻结父文件发生漂移: {relative_path}")


def _parent_manifest(repo_root: Path) -> dict[str, Any]:
    expected = {
        PARENT_MANIFEST_PATH: PARENT_MANIFEST_FILE_SHA256,
        PARENT_SCHEMA_PATH: PARENT_SCHEMA_FILE_SHA256,
        PARENT_PROTOCOL_PATH: PARENT_PROTOCOL_FILE_SHA256,
        PARENT_RUNNER_PATH: PARENT_RUNNER_FILE_SHA256,
        PARENT_PREREGISTRATION_PATH: PARENT_PREREGISTRATION_FILE_SHA256,
    }
    for relative_path, digest in expected.items():
        _require_file_hash(repo_root, relative_path, digest)
    value = parent.load_manifest(repo_root / PARENT_MANIFEST_PATH, repo_root)
    if canonical_sha256(value) != PARENT_MANIFEST_CANONICAL_SHA256:
        raise StageCV8AuthorizedProtocolError("Stage C v8 父 candidate canonical identity 漂移")
    return value


def _frozen_components(repo_root: Path) -> dict[str, str]:
    paths = (
        PARENT_MANIFEST_PATH,
        PARENT_SCHEMA_PATH,
        PARENT_PROTOCOL_PATH,
        PARENT_RUNNER_PATH,
        PARENT_PREREGISTRATION_PATH,
        PREREGISTRATION_PATH,
        PROTOCOL_PATH,
        RUNNER_PATH,
        parent.parent.parent.RUNTIME_V3_PATH,
        parent.parent.parent.CANDIDATE_VERIFIER_PATH,
        parent.parent.parent.EXTERNAL_EVALUATOR_V4_PATH,
    )
    result: dict[str, str] = {}
    for relative_path in paths:
        path = repo_root / relative_path
        if path.is_symlink() or not path.is_file():
            raise StageCV8AuthorizedProtocolError(f"授权组件不存在: {relative_path}")
        result[relative_path] = file_sha256(path)
    return result


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    source = _parent_manifest(repo_root)
    value = copy.deepcopy(source)
    value.update(
        {
            "$schema": "../schemas/forge-stage-c-v8-workspace-remediation-canary-authorized.schema.json",
            "schema_version": SCHEMA_VERSION,
            "document_type": DOCUMENT_TYPE,
            "issue_url": ISSUE_URL,
            "purpose": "stage_c_v8_workspace_remediation_provider_canary_authorized",
            "status": "authorized_not_executed",
        }
    )
    value["authorization"] = {
        "authorized_by": "experiment_owner",
        "credential_read_authorized": True,
        "provider_calls_authorized": True,
        "model_creation_authorized": True,
        "reachability_request_authorized": True,
        "docker_execution_authorized": True,
        "formal_stage_c_attempts_authorized": True,
        "evidence_write_authorized": True,
        "model_tokens_authorized": True,
        "model_token_ceiling": None,
        "stage_c_execution_started": False,
    }
    value["execution"] = {
        "source_main_revision": AUTHORIZATION_BASELINE_COMMIT,
        "release_branch": "main",
        "authorization_baseline_commit": AUTHORIZATION_BASELINE_COMMIT,
        "release_revision_policy": "clean_main_equals_origin_main_and_descends_from_authorization_baseline",
        "evidence_directory_relative": EVIDENCE_DIRECTORY_RELATIVE,
        "workspace": copy.deepcopy(source["execution"]["workspace"]),
        "create_once": True,
        "fresh_thread_session_and_evidence_per_attempt": True,
        "network_access_medium_env": "FORGE_NETWORK_ACCESS_MEDIUM",
        "network_access_medium": "ethernet",
        "docker": copy.deepcopy(source["execution"]["docker"]),
        "reachability": {
            "prompt": "Reply with exactly STAGE_C_V8_WORKSPACE_OK and nothing else.",
            "expected_response": "STAGE_C_V8_WORKSPACE_OK",
            "maximum_requests": 1,
            "maximum_recorded_tokens": None,
            "retry_forbidden": True,
            "marker": "markers/reachability.json",
            "report": "reports/reachability.json",
        },
        "batch_marker": "markers/batch.json",
        "attempt_marker_template": "attempts/{sequence:02d}-{task_id}/attempt.json",
        "attempt_result_template": "attempts/{sequence:02d}-{task_id}/result.json",
        "attempt_ledger_template": "attempts/{sequence:02d}-{task_id}/experiment.jsonl",
        "batch_report": "reports/canary.json",
        "resume_policy": "completed_contiguous_prefix_only",
        "commands": ["validate", "preflight", "reachability", "run", "report"],
    }
    value["analysis"].update(
        {
            "descriptive_canary_only": True,
            "treatment_effect_estimated": False,
            "p_value_computed": False,
            "model_ranking_authorized": False,
        }
    )
    value["parent_candidate"] = {
        "manifest_path": PARENT_MANIFEST_PATH,
        "canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "file_sha256": PARENT_MANIFEST_FILE_SHA256,
        "schema_path": PARENT_SCHEMA_PATH,
        "schema_file_sha256": PARENT_SCHEMA_FILE_SHA256,
        "protocol_path": PARENT_PROTOCOL_PATH,
        "protocol_file_sha256": PARENT_PROTOCOL_FILE_SHA256,
        "runner_path": PARENT_RUNNER_PATH,
        "runner_file_sha256": PARENT_RUNNER_FILE_SHA256,
        "preregistration_path": PARENT_PREREGISTRATION_PATH,
        "preregistration_file_sha256": PARENT_PREREGISTRATION_FILE_SHA256,
        "historical_evidence_reused": False,
        "historical_outcomes_imported": False,
    }
    value["preregistration"] = {
        "path": PREREGISTRATION_PATH,
        "file_sha256": file_sha256(repo_root / PREREGISTRATION_PATH),
    }
    value["frozen_authorized_components"] = _frozen_components(repo_root)
    return value


def validate_allowed_delta(value: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    source = _parent_manifest(repo_root)
    preserved_keys = (
        "provider",
        "environment",
        "budget",
        "methods",
        "candidate_contract",
        "external_evaluator",
        "tasks",
        "schedule",
        "historical_inputs",
        "failure_audit",
        "parent_authorized_v7",
    )
    if any(value.get(key) != source.get(key) for key in preserved_keys):
        raise StageCV8AuthorizedProtocolError("授权 identity 改写了父 candidate 的冻结合同")
    if value.get("execution", {}).get("workspace") != source["execution"]["workspace"]:
        raise StageCV8AuthorizedProtocolError("授权 identity 改写了 v8 workspace 合同")
    if value != generate_manifest(repo_root):
        raise StageCV8AuthorizedProtocolError("授权 identity 包含未预注册差异")
    return {
        "status": "passed",
        "parent_manifest_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "attempt_order": [item["task_id"] for item in value["schedule"]["attempts"]],
        "token_ceiling": None,
        "provider_calls_during_validation": 0,
        "formal_attempts_during_validation": 0,
        "model_tokens_during_validation": 0,
    }


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-stage-c-v8-workspace-remediation-canary-authorized.schema.json",
        "title": "Forge Stage C v8 workspace remediation authorized canary",
        "const": manifest,
    }


def validate_manifest(value: dict[str, Any], repo_root: Path = REPO_ROOT, *, check_schema_file: bool = True) -> dict[str, Any]:
    validate_allowed_delta(value, repo_root)
    authorization = value["authorization"]
    required = (
        "credential_read_authorized",
        "provider_calls_authorized",
        "model_creation_authorized",
        "reachability_request_authorized",
        "docker_execution_authorized",
        "formal_stage_c_attempts_authorized",
        "evidence_write_authorized",
        "model_tokens_authorized",
    )
    if any(authorization.get(field) is not True for field in required) or authorization.get("model_token_ceiling") is not None:
        raise StageCV8AuthorizedProtocolError("Stage C v8 授权边界未闭合")
    budget = value["budget"]
    if any(budget.get(field) is not None for field in ("reachability_max_recorded_tokens", "canary_attempts_max_recorded_tokens", "total_max_recorded_tokens")):
        raise StageCV8AuthorizedProtocolError("Stage C v8 token 上限必须保持 null")
    if budget["per_attempt"].get("max_recorded_tokens") is not None or budget["token_accounting"].get("token_total_is_termination_condition") is not False:
        raise StageCV8AuthorizedProtocolError("Stage C v8 token 必须只计量、不终止")
    schema = generate_schema(value)
    jsonschema.Draft202012Validator.check_schema(schema)
    if check_schema_file:
        stored = _load_json(repo_root / SCHEMA_RELATIVE_PATH)
        if stored != schema:
            raise StageCV8AuthorizedProtocolError("Stage C v8 authorized const Schema 漂移")
        jsonschema.validate(value, stored)
    return value


def load_manifest(path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    return validate_manifest(_load_json(path), repo_root)


def verify_frozen_components(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> None:
    validate_manifest(manifest, repo_root)
    if manifest["frozen_authorized_components"] != _frozen_components(repo_root):
        raise StageCV8AuthorizedProtocolError("Stage C v8 authorized 组件发生漂移")


def write_artifacts(repo_root: Path = REPO_ROOT) -> None:
    manifest = generate_manifest(repo_root)
    for relative_path, value in (
        (MANIFEST_RELATIVE_PATH, manifest),
        (SCHEMA_RELATIVE_PATH, generate_schema(manifest)),
    ):
        path = repo_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate", "delta"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    if args.command == "generate":
        write_artifacts()
        manifest = load_manifest(args.manifest)
        result: Any = {"status": "generated", "manifest_sha256": canonical_sha256(manifest)}
    else:
        manifest = load_manifest(args.manifest)
        result = (
            validate_allowed_delta(manifest)
            if args.command == "delta"
            else {
                "status": "valid",
                "manifest_sha256": canonical_sha256(manifest),
                "provider_calls": 0,
                "formal_attempts": 0,
                "model_tokens": 0,
            }
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
