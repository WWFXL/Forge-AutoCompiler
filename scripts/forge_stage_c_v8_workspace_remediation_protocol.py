#!/usr/bin/env python3
"""生成并校验 Stage C v8 workspace remediation 未授权候选身份。"""

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

import forge_stage_c_v7_prefreeze_canary_authorized_protocol as parent  # noqa: E402

SCHEMA_VERSION = "forge-stage-c-v8-workspace-remediation-canary-candidate-1.0.0"
DOCUMENT_TYPE = "forge_stage_c_v8_workspace_remediation_canary_candidate"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/345"
SOURCE_MAIN_REVISION = "5a01b2ac51da57b699202de02dec6065a8f643be"

PARENT_MANIFEST_PATH = parent.MANIFEST_RELATIVE_PATH
PARENT_SCHEMA_PATH = parent.SCHEMA_RELATIVE_PATH
PARENT_PROTOCOL_PATH = parent.PROTOCOL_PATH
PARENT_RUNNER_PATH = parent.RUNNER_PATH
PARENT_PREREGISTRATION_PATH = parent.PREREGISTRATION_PATH
PARENT_MANIFEST_CANONICAL_SHA256 = "261da6d0d0416073998d9aed544c99dba3097784fa2c3edd0022a2cd96e3086f"
PARENT_MANIFEST_FILE_SHA256 = "e311add867c1aa88b1776c6fe08a3ea59d94edbe17e48bb37ae36054688e77ef"
PARENT_SCHEMA_FILE_SHA256 = "8b770fa712e3fc11587e8e3591a65a6f88cc8f141be69abde847031888b49147"
PARENT_PROTOCOL_FILE_SHA256 = "bb4c122719b638b9842b4b61037fd109739b9bb06a397ca107745fa12a440146"
PARENT_RUNNER_FILE_SHA256 = "21375f95956e4268fda7448c2788597d9d095221608bbdd3fe0a99d5d21ff6bf"
PARENT_PREREGISTRATION_FILE_SHA256 = "f57b750180977788bd774e8a04c00bee9bec4491e4045117cab6583dbb9412fa"

FAILURE_AUDIT_PATH = "benchmarks/reports/cpp-stage-c-v7-workspace-failure-audit.json"
FAILURE_AUDIT_REPORT_PATH = "benchmarks/reports/cpp-stage-c-v7-workspace-failure-audit.md"
FAILURE_AUDIT_FILE_SHA256 = "bbe7c554fdf82a6fafddc304d20f6737995a95250d8a939ec747f58e9a009845"
FAILURE_AUDIT_REPORT_FILE_SHA256 = "bcf2b083a88bf85a301e50eb623d4065dd27e5d0474243bd159cbe8d5dfdda0f"

PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-stage-c-v8-workspace-remediation-canary-candidate.md"
PROTOCOL_PATH = "scripts/forge_stage_c_v8_workspace_remediation_protocol.py"
RUNNER_PATH = "scripts/forge_stage_c_v8_workspace_remediation_runner.py"
MANIFEST_RELATIVE_PATH = "benchmarks/manifests/cpp-stage-c-v8-workspace-remediation-canary-candidate.json"
SCHEMA_RELATIVE_PATH = "benchmarks/schemas/forge-stage-c-v8-workspace-remediation-canary-candidate.schema.json"
EVIDENCE_DIRECTORY_RELATIVE = ".compile-sessions/benchmark-evidence-stage-c-v8-workspace-remediation-canary-candidate"

DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_RELATIVE_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_RELATIVE_PATH


class StageCV8ProtocolError(RuntimeError):
    """v7 失败来源、v8 路径合同或未授权边界无效。"""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageCV8ProtocolError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise StageCV8ProtocolError(f"JSON 根节点必须是对象: {path}")
    return value


def _file_sha256(path: Path) -> str:
    return parent.parent.file_sha256(path)


def _canonical_sha256(value: dict[str, Any]) -> str:
    return parent.parent.canonical_sha256(value)


def _require_file(repo_root: Path, relative_path: str, expected_sha256: str) -> None:
    path = repo_root / relative_path
    if path.is_symlink() or not path.is_file() or _file_sha256(path) != expected_sha256:
        raise StageCV8ProtocolError(f"冻结来源文件发生漂移: {relative_path}")


def _load_parent(repo_root: Path) -> dict[str, Any]:
    expected = {
        PARENT_MANIFEST_PATH: PARENT_MANIFEST_FILE_SHA256,
        PARENT_SCHEMA_PATH: PARENT_SCHEMA_FILE_SHA256,
        PARENT_PROTOCOL_PATH: PARENT_PROTOCOL_FILE_SHA256,
        PARENT_RUNNER_PATH: PARENT_RUNNER_FILE_SHA256,
        PARENT_PREREGISTRATION_PATH: PARENT_PREREGISTRATION_FILE_SHA256,
    }
    for relative_path, digest in expected.items():
        _require_file(repo_root, relative_path, digest)
    value = parent.load_manifest(repo_root / PARENT_MANIFEST_PATH, repo_root)
    if _canonical_sha256(value) != PARENT_MANIFEST_CANONICAL_SHA256:
        raise StageCV8ProtocolError("Stage C v7 parent canonical identity 漂移")
    return value


def validate_failure_audit(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    _require_file(repo_root, FAILURE_AUDIT_PATH, FAILURE_AUDIT_FILE_SHA256)
    _require_file(repo_root, FAILURE_AUDIT_REPORT_PATH, FAILURE_AUDIT_REPORT_FILE_SHA256)
    value = _load_json(repo_root / FAILURE_AUDIT_PATH)
    identity = value.get("identity", {})
    inventory = value.get("evidence_inventory", {})
    reachability = value.get("reachability", {})
    attempt = value.get("theora_attempt", {})
    decision = value.get("decision", {})
    root_cause = value.get("root_cause", {})
    files = inventory.get("files")
    if (
        value.get("document_type") != "forge_stage_c_v7_workspace_failure_audit"
        or value.get("classification") != "compile_session_workspace_permission_failure_before_session_creation"
        or identity.get("manifest_sha256") != PARENT_MANIFEST_CANONICAL_SHA256
        or identity.get("manifest_file_sha256") != PARENT_MANIFEST_FILE_SHA256
        or identity.get("release_revision") != SOURCE_MAIN_REVISION
        or inventory.get("file_count") != 7
        or inventory.get("total_size_bytes") != 7416
        or inventory.get("inventory_sha256") != "ca7e467911c5ac798bc9ed2042b5dd949bab9bbabbefa31e0bc0c5ee954e404f"
        or not isinstance(files, list)
        or [item.get("path") for item in files] != sorted(item.get("path") for item in files)
        or reachability
        != {
            "actual_model": "deepseek-flash",
            "input_tokens": 46,
            "output_tokens": 24,
            "passed": True,
            "request_count": 1,
            "response_sha256": "d8cfba618307633efcbc5f294402ae2b85536728a368be8cce0dad23649e0da6",
            "total_tokens": 70,
        }
        or attempt.get("model_requests") != 0
        or attempt.get("recorded_tokens") != 0
        or attempt.get("session_id") is not None
        or attempt.get("error_class") != "PermissionError"
        or root_cause.get("error_message_sha256") != "1f6ef3419a6797fe5790dbbb695d535aa96b670c8065c80f28c09699db93e6a6"
        or decision.get("old_batch_resumable") is not False
        or decision.get("retry_authorized") is not False
        or decision.get("replacement_authorized") is not False
        or decision.get("provider_execution_authorized") is not False
    ):
        raise StageCV8ProtocolError("Stage C v7 workspace 失败审计语义漂移")
    return value


def _schedule(parent_manifest: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(parent_manifest["schedule"])
    for attempt in value["attempts"]:
        task_id = attempt["task_id"]
        attempt["attempt_id"] = f"stage-c-v8-{task_id}-workspace-remediation-b-canary"
        attempt["canary_id"] = f"stage-c-v8-{task_id}-workspace-remediation-canary"
    return value


def _frozen_candidate_components(repo_root: Path) -> dict[str, str]:
    paths = (
        PARENT_MANIFEST_PATH,
        PARENT_SCHEMA_PATH,
        PARENT_PROTOCOL_PATH,
        PARENT_RUNNER_PATH,
        PARENT_PREREGISTRATION_PATH,
        FAILURE_AUDIT_PATH,
        FAILURE_AUDIT_REPORT_PATH,
        PREREGISTRATION_PATH,
        PROTOCOL_PATH,
        RUNNER_PATH,
        parent.parent.RUNTIME_V3_PATH,
        parent.parent.CANDIDATE_VERIFIER_PATH,
        parent.parent.EXTERNAL_EVALUATOR_V4_PATH,
    )
    result: dict[str, str] = {}
    for relative_path in paths:
        path = repo_root / relative_path
        if path.is_symlink() or not path.is_file():
            raise StageCV8ProtocolError(f"v8 candidate 组件不存在: {relative_path}")
        result[relative_path] = _file_sha256(path)
    return result


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    source = _load_parent(repo_root)
    validate_failure_audit(repo_root)
    value = copy.deepcopy(source)
    value.update(
        {
            "$schema": "../schemas/forge-stage-c-v8-workspace-remediation-canary-candidate.schema.json",
            "schema_version": SCHEMA_VERSION,
            "document_type": DOCUMENT_TYPE,
            "issue_url": ISSUE_URL,
            "purpose": "stage_c_v8_workspace_remediation_canary_candidate",
            "status": "candidate_not_authorized",
        }
    )
    value["authorization"] = {
        "candidate_identity_only": True,
        "credential_read_authorized": False,
        "provider_calls_authorized": False,
        "model_creation_authorized": False,
        "reachability_request_authorized": False,
        "docker_execution_authorized": False,
        "formal_stage_c_attempts_authorized": False,
        "evidence_write_authorized": False,
        "model_tokens_authorized": False,
        "model_token_ceiling": None,
        "stage_c_execution_started": False,
    }
    value["execution"] = {
        "source_main_revision": SOURCE_MAIN_REVISION,
        "release_branch": "main",
        "docker": copy.deepcopy(source["execution"]["docker"]),
        "evidence_directory_relative": EVIDENCE_DIRECTORY_RELATIVE,
        "workspace": {
            "binding": "release_repository_root",
            "process_workspace_root": ".",
            "host_workspace_root": ".",
            "compile_sessions_relative_path": ".compile-sessions",
            "process_host_roots_must_match": True,
            "repository_root_must_not_be_symlink": True,
            "compile_sessions_root_must_not_be_symlink": True,
            "compile_sessions_root_must_be_writable": True,
            "preflight_before_credential_model_provider_or_marker": True,
        },
        "planned_authorized_markers": {
            "reachability": "markers/reachability.json",
            "batch": "markers/batch.json",
            "attempt_template": "attempts/{sequence:02d}-{task_id}/attempt.json",
        },
        "commands": ["validate", "preflight", "show-plan"],
    }
    value["schedule"] = _schedule(source)
    value["parent_authorized_v7"] = {
        "manifest_path": PARENT_MANIFEST_PATH,
        "manifest_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "manifest_file_sha256": PARENT_MANIFEST_FILE_SHA256,
        "release_revision": SOURCE_MAIN_REVISION,
        "read_only": True,
        "outcomes_imported": False,
        "batch_resumable": False,
    }
    value["failure_audit"] = {
        "path": FAILURE_AUDIT_PATH,
        "file_sha256": FAILURE_AUDIT_FILE_SHA256,
        "report_path": FAILURE_AUDIT_REPORT_PATH,
        "report_file_sha256": FAILURE_AUDIT_REPORT_FILE_SHA256,
    }
    value["preregistration"] = {
        "path": PREREGISTRATION_PATH,
        "file_sha256": _file_sha256(repo_root / PREREGISTRATION_PATH),
    }
    value["frozen_candidate_components"] = _frozen_candidate_components(repo_root)
    return value


def validate_allowed_delta(value: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    source = _load_parent(repo_root)
    for key in ("provider", "environment", "budget", "methods", "candidate_contract", "external_evaluator", "tasks", "analysis", "historical_inputs"):
        if value.get(key) != source.get(key):
            raise StageCV8ProtocolError(f"v8 candidate 改写了父科学合同: {key}")
    expected_order = [item["task_id"] for item in source["schedule"]["attempts"]]
    if [item.get("task_id") for item in value.get("schedule", {}).get("attempts", [])] != expected_order:
        raise StageCV8ProtocolError("v8 candidate 改写了任务顺序")
    if value != generate_manifest(repo_root):
        raise StageCV8ProtocolError("v8 candidate 包含未预注册差异")
    return {
        "status": "passed",
        "parent_manifest_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "attempt_order": expected_order,
        "token_ceiling": None,
        "provider_calls_during_validation": 0,
        "formal_attempts_during_validation": 0,
        "model_tokens_during_validation": 0,
    }


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-stage-c-v8-workspace-remediation-canary-candidate.schema.json",
        "title": "Forge Stage C v8 workspace remediation canary candidate",
        "const": manifest,
    }


def validate_manifest(value: dict[str, Any], repo_root: Path = REPO_ROOT, *, check_schema_file: bool = True) -> dict[str, Any]:
    validate_allowed_delta(value, repo_root)
    authorization = value.get("authorization", {})
    if authorization.get("candidate_identity_only") is not True or any(
        authorization.get(field) is not False
        for field in (
            "credential_read_authorized",
            "provider_calls_authorized",
            "model_creation_authorized",
            "reachability_request_authorized",
            "docker_execution_authorized",
            "formal_stage_c_attempts_authorized",
            "evidence_write_authorized",
            "model_tokens_authorized",
            "stage_c_execution_started",
        )
    ):
        raise StageCV8ProtocolError("v8 candidate 未授权边界未闭合")
    schema = generate_schema(value)
    jsonschema.Draft202012Validator.check_schema(schema)
    if check_schema_file:
        stored = _load_json(repo_root / SCHEMA_RELATIVE_PATH)
        if stored != schema:
            raise StageCV8ProtocolError("v8 candidate const Schema 漂移")
        jsonschema.validate(value, stored)
    return value


def load_manifest(path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    return validate_manifest(_load_json(path), repo_root)


def verify_frozen_components(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> None:
    validate_manifest(manifest, repo_root)
    if manifest["frozen_candidate_components"] != _frozen_candidate_components(repo_root):
        raise StageCV8ProtocolError("v8 candidate 组件发生漂移")


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
        result: Any = {"status": "generated", "manifest_sha256": _canonical_sha256(manifest)}
    else:
        manifest = load_manifest(args.manifest)
        result = (
            validate_allowed_delta(manifest)
            if args.command == "delta"
            else {
                "status": "valid",
                "manifest_sha256": _canonical_sha256(manifest),
                "provider_calls": 0,
                "formal_attempts": 0,
                "model_tokens": 0,
            }
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
