#!/usr/bin/env python3
"""Issue #297 Phase 5 v2 授权修订协议。"""

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

import forge_agent_workflow_stage_b_phase5_v2_candidate_protocol as candidate  # noqa: E402

SCHEMA_VERSION = "forge-agent-workflow-stage-b-phase5-v2-authorized-1.0.0"
DOCUMENT_TYPE = "forge_agent_workflow_stage_b_phase5_v2_authorized"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/297"
AUTHORIZATION_BASELINE_COMMIT = "03a870eeef54f3fe591b115428dba51637acbcca"
PARENT_MANIFEST_CANONICAL_SHA256 = "babc7d2f07058aa7968bea19cd8e022eea6442bd64388c99965f5333d12e4ee3"
MANIFEST_RELATIVE_PATH = "benchmarks/manifests/cpp-agent-workflow-stage-b-phase5-v2-authorized.json"
SCHEMA_RELATIVE_PATH = "benchmarks/schemas/forge-agent-workflow-stage-b-phase5-v2-authorized.schema.json"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-agent-workflow-stage-b-phase5-v2-authorized.md"
PROTOCOL_PATH = "scripts/forge_agent_workflow_stage_b_phase5_v2_authorized_protocol.py"
RUNNER_PATH = "scripts/forge_agent_workflow_stage_b_phase5_v2_authorized_runner.py"
EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-agent-workflow-stage-b-phase5-v2-authorized"

DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_RELATIVE_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_RELATIVE_PATH


class Phase5V2AuthorizedProtocolError(RuntimeError):
    """Phase 5 v2 授权修订身份或允许差异发生漂移。"""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase5V2AuthorizedProtocolError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise Phase5V2AuthorizedProtocolError(f"JSON 根节点必须是对象: {path}")
    return value


def _parent_manifest(repo_root: Path) -> dict[str, Any]:
    value = candidate.load_manifest(repo_root / candidate.MANIFEST_RELATIVE_PATH, repo_root)
    if candidate.canonical_sha256(value) != PARENT_MANIFEST_CANONICAL_SHA256:
        raise Phase5V2AuthorizedProtocolError("Phase 5 v2 父候选 canonical identity 发生漂移")
    return value


def _frozen_authorized_components(repo_root: Path) -> dict[str, str]:
    paths = (PREREGISTRATION_PATH, PROTOCOL_PATH, RUNNER_PATH)
    return {path: candidate.file_sha256(repo_root / path) for path in paths}


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    parent = _parent_manifest(repo_root)
    value = copy.deepcopy(parent)
    value.update(
        {
            "$schema": ("../schemas/forge-agent-workflow-stage-b-phase5-v2-authorized.schema.json"),
            "schema_version": SCHEMA_VERSION,
            "document_type": DOCUMENT_TYPE,
            "issue_url": ISSUE_URL,
            "status": "authorized_not_executed",
        }
    )
    value["authorization"] = {
        "provider_calls_authorized": True,
        "credential_read_authorized": True,
        "model_creation_authorized": True,
        "reachability_request_authorized": True,
        "docker_execution_authorized": True,
        "evidence_write_authorized": True,
        "formal_attempts_authorized": True,
        "model_tokens_authorized": (parent["budget_candidate"]["batch_max_recorded_tokens"] + 5_000),
    }
    value["runtime_candidate"]["protocol_path"] = PROTOCOL_PATH
    value["runtime_candidate"]["runner_path"] = RUNNER_PATH
    value["evidence_candidate"]["directory"] = EVIDENCE_DIRECTORY
    value["evidence_candidate"]["writes_authorized"] = True
    value["authorized_execution"] = {
        "authorization_baseline_commit": AUTHORIZATION_BASELINE_COMMIT,
        "release_branch": "main",
        "release_revision_policy": ("descendant_of_authorization_baseline_and_record_each_attempt"),
        "parent_manifest_path": candidate.MANIFEST_RELATIVE_PATH,
        "parent_manifest_canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "qualification_result_sha256": candidate.QUALIFICATION_RESULT_SHA256,
        "network_access_medium_env": "FORGE_NETWORK_ACCESS_MEDIUM",
        "network_access_medium": "ethernet",
        "reachability": {
            "maximum_requests": 1,
            "maximum_recorded_tokens": 5_000,
            "prompt": "Reply with exactly CANARY_OK and nothing else.",
            "expected_response": "CANARY_OK",
            "marker": "markers/reachability.json",
            "report": "reports/reachability.json",
        },
        "attempt_id_template": "phase5-v2-{task_id}-attempt-1",
        "thread_id_prefix": "phase5-v2",
        "evaluation_id_template": "phase5-v2-{task_id}-evaluation-v2",
        "task_marker_path": "tasks/{task_id}/attempt.json",
        "task_result_path": parent["evidence_candidate"]["task_result_path"],
        "batch_marker": parent["evidence_candidate"]["batch_marker"],
        "batch_report": parent["evidence_candidate"]["batch_report"],
        "stage_c_decision_package": "reports/stage-c-decision.json",
        "resume_policy": "completed_contiguous_prefix_only",
        "commands": ["validate", "preflight", "reachability", "batch", "report"],
    }
    value["frozen_authorized_components"] = _frozen_authorized_components(repo_root)
    return value


def validate_allowed_delta(value: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    parent = _parent_manifest(repo_root)
    normalized = copy.deepcopy(value)
    authorized_execution = normalized.pop("authorized_execution", None)
    frozen_components = normalized.pop("frozen_authorized_components", None)
    for key in ("$schema", "schema_version", "document_type", "issue_url", "status"):
        normalized[key] = parent[key]
    normalized["authorization"] = copy.deepcopy(parent["authorization"])
    normalized["runtime_candidate"] = copy.deepcopy(parent["runtime_candidate"])
    normalized["evidence_candidate"] = copy.deepcopy(parent["evidence_candidate"])
    if normalized != parent:
        raise Phase5V2AuthorizedProtocolError("authorized amendment 包含未预注册的父候选差异")
    expected = generate_manifest(repo_root)
    if authorized_execution != expected["authorized_execution"] or frozen_components != expected["frozen_authorized_components"]:
        raise Phase5V2AuthorizedProtocolError("authorized execution identity 发生漂移")
    return {
        "status": "passed",
        "parent_manifest_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "qualification_result_sha256": candidate.QUALIFICATION_RESULT_SHA256,
        "task_count": len(parent["tasks"]),
        "task_order": parent["schedule"]["order"],
        "historical_evidence_reused": False,
        "unbiased_success_rate_claim_allowed": False,
    }


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": ("https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-agent-workflow-stage-b-phase5-v2-authorized.schema.json"),
        "title": "Forge Agent Workflow Stage B Phase 5 v2 authorized amendment",
        "const": manifest,
    }


def validate_manifest(value: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    expected = generate_manifest(repo_root)
    if value != expected:
        raise Phase5V2AuthorizedProtocolError("Phase 5 v2 authorized manifest 与确定性生成结果不一致")
    validate_allowed_delta(value, repo_root)
    authorization = value["authorization"]
    required = (
        "provider_calls_authorized",
        "credential_read_authorized",
        "model_creation_authorized",
        "reachability_request_authorized",
        "docker_execution_authorized",
        "evidence_write_authorized",
        "formal_attempts_authorized",
    )
    if not all(authorization[key] is True for key in required):
        raise Phase5V2AuthorizedProtocolError("Phase 5 v2 真实执行授权未闭合")
    expected_tokens = value["budget_candidate"]["batch_max_recorded_tokens"] + value["authorized_execution"]["reachability"]["maximum_recorded_tokens"]
    if authorization["model_tokens_authorized"] != expected_tokens:
        raise Phase5V2AuthorizedProtocolError("Phase 5 v2 授权 token ceiling 发生漂移")
    schema = generate_schema(expected)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(value, schema)
    return value


def load_manifest(path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    return validate_manifest(_load_json(path), repo_root)


def verify_frozen_components(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> None:
    validate_manifest(manifest, repo_root)
    if manifest["frozen_authorized_components"] != _frozen_authorized_components(repo_root):
        raise Phase5V2AuthorizedProtocolError("Phase 5 v2 authorized 组件发生漂移")


def write_artifacts(repo_root: Path = REPO_ROOT) -> None:
    manifest = generate_manifest(repo_root)
    schema = generate_schema(manifest)
    for relative_path, value in (
        (MANIFEST_RELATIVE_PATH, manifest),
        (SCHEMA_RELATIVE_PATH, schema),
    ):
        path = repo_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate", "delta"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    if args.command == "generate":
        write_artifacts()
        manifest = load_manifest(args.manifest)
        result: Any = {
            "status": "generated",
            "manifest": MANIFEST_RELATIVE_PATH,
            "schema": SCHEMA_RELATIVE_PATH,
        }
    else:
        manifest = load_manifest(args.manifest)
        result = validate_allowed_delta(manifest) if args.command == "delta" else {"status": "valid"}
    result["manifest_sha256"] = candidate.canonical_sha256(manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
