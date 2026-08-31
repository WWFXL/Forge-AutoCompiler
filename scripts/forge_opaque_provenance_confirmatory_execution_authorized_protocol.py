#!/usr/bin/env python3
"""Issue #237 六 case opaque provenance 确认性执行授权协议。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-confirmatory-execution-authorized.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-confirmatory-execution-authorized.schema.json"
PARENT_MANIFEST_PATH = "benchmarks/manifests/cpp-opaque-provenance-confirmatory-execution-candidate.json"
RUNTIME_PATH = "scripts/forge_opaque_provenance_confirmatory_execution_authorized_runner.py"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-opaque-provenance-confirmatory-execution-authorized.md"

SCHEMA_VERSION = "forge-opaque-provenance-confirmatory-execution-authorized-1.0.0"
DOCUMENT_TYPE = "forge_opaque_provenance_confirmatory_execution_authorized"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/237"
AUTHORIZATION_BASELINE_COMMIT = "0c5b7b4f4130fb1a2a17611b3f74b8cc90359fd6"
PARENT_MANIFEST_CANONICAL_SHA256 = "0c0a9aeba1f25365ca26e4dfc83d987819e562c3f3fb68d3bfc1ec9f31f0eaf9"
EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-confirmatory-v1"

FROZEN_PARENT_PATHS = (
    PARENT_MANIFEST_PATH,
    "benchmarks/schemas/forge-opaque-provenance-confirmatory-execution-candidate.schema.json",
    "benchmarks/preregistrations/cpp-opaque-provenance-confirmatory-execution-candidate.md",
    "scripts/forge_opaque_provenance_confirmatory_execution_candidate_protocol.py",
    "scripts/forge_opaque_provenance_confirmatory_execution_composition_gate.py",
    "scripts/forge_opaque_provenance_confirmatory_lifecycle_gate.py",
    "backend/tests/test_forge_opaque_provenance_confirmatory_execution_candidate.py",
)


class ProtocolError(RuntimeError):
    """授权 identity、父候选、预算或 runtime 发生漂移。"""


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


def _load_parent_protocol(repo_root: Path = REPO_ROOT):
    path = repo_root / "scripts/forge_opaque_provenance_confirmatory_execution_candidate_protocol.py"
    name = "forge_confirmatory_execution_authorized_parent"
    existing = sys.modules.get(name)
    if existing is not None and Path(existing.__file__).resolve() == path.resolve():
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ProtocolError("无法加载 Issue #235 parent protocol")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _parent_manifest(repo_root: Path = REPO_ROOT) -> tuple[dict[str, Any], Any]:
    parent = _load_parent_protocol(repo_root)
    path = repo_root / PARENT_MANIFEST_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError("无法读取 Issue #235 parent manifest") from exc
    manifest = parent.validate_manifest(value, repo_root)
    if parent.canonical_sha256(manifest) != PARENT_MANIFEST_CANONICAL_SHA256:
        raise ProtocolError("Issue #235 parent canonical identity 发生漂移")
    return manifest, parent


def _frozen_parent_sha256(repo_root: Path) -> dict[str, str]:
    return {path: file_sha256(repo_root / path) for path in FROZEN_PARENT_PATHS}


def _evidence_identity(parent: dict[str, Any]) -> str:
    return canonical_sha256(
        {
            "issue_url": ISSUE_URL,
            "parent_manifest_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
            "schedule_identity_sha256": parent["schedule"]["identity_sha256"],
            "provider": parent["execution_candidate"]["provider"],
            "directory": EVIDENCE_DIRECTORY,
            "historical_evidence_reused": False,
        }
    )


def _authorized_execution(parent: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    runtime_path = repo_root / RUNTIME_PATH
    preregistration_path = repo_root / PREREGISTRATION_PATH
    if not runtime_path.is_file() or not preregistration_path.is_file():
        raise ProtocolError("authorized runtime 或预注册不存在")
    return {
        "issue_url": ISSUE_URL,
        "status": "authorized_not_started",
        "authorization_baseline_commit": AUTHORIZATION_BASELINE_COMMIT,
        "release_revision_policy": "descendant_merged_main_recorded_before_first_request",
        "provider": {
            **copy.deepcopy(parent["execution_candidate"]["provider"]),
            "status": "active_authorized",
        },
        "evidence": {
            "schema_version": "forge-opaque-provenance-confirmatory-evidence-1.0.0",
            "directory": EVIDENCE_DIRECTORY,
            "identity_sha256": _evidence_identity(parent),
            "reachability_marker": "markers/reachability.json",
            "reachability_report": "reports/reachability.json",
            "batch_marker": "markers/batch.json",
            "batch_report": "reports/batch.json",
            "pair_directory_pattern": "pairs/{pair_id}",
            "pair_marker": "markers/pair.json",
            "pair_report": "reports/pair.json",
            "pair_outcome": "reports/pair-outcome.json",
            "parent_ledger": "ledgers/parent.jsonl",
            "arm_ledger_directory": "ledgers/arms",
            "append_only": True,
            "create_once": True,
            "historical_evidence_reused": False,
            "zero_provider_preflight_writes_evidence": False,
        },
        "budget": {
            "maximum_reachability_requests": 1,
            "reachability_maximum_recorded_tokens": 5000,
            "recorded_tokens_per_arm": 120000,
            "recorded_tokens_per_pair": 240000,
            "batch_maximum_recorded_tokens": parent["runtime_contract"]["batch_recorded_token_ceiling"],
            "enforcement": "before_each_pair_and_after_each_arm",
        },
        "preflight": {
            "release_branch": "main",
            "require_clean_worktree": True,
            "require_head_equals_origin_main": True,
            "require_authorization_baseline_ancestor": True,
            "docker_provider": "ubuntu-native",
            "docker_context": "default",
            "docker_endpoint": "/var/run/docker.sock",
            "control_plane": "compose-dood-on-ubuntu-native-engine",
            "allowed_network_media": ["wired", "wifi", "mobile_hotspot"],
            "network_access_medium_env": "FORGE_NETWORK_ACCESS_MEDIUM",
            "credential_check": "environment_variable_presence_only",
            "require_empty_evidence_directory_before_reachability": True,
            "managed_container_prefixes": ["deerflow-compile-", "deerflow-replay-"],
            "require_zero_managed_orphans": True,
        },
        "execution": {
            "reachability_prompt": "Reply with exactly CANARY_OK and nothing else.",
            "reachability_expected_response": "CANARY_OK",
            "single_asyncio_loop_for_batch": True,
            "checkpoint_capture_restore_reimplemented": False,
            "pair_runtime_reuse": {
                "cmake": "scripts/forge_opaque_provenance_minimal_canary_execution_runner.py",
                "make": "scripts/forge_opaque_provenance_r3_make_execution_runner.py",
                "checkpoint": "scripts/forge_real_lifecycle_checkpoint_gate.py",
                "batch": "scripts/forge_checkpoint_behavioral_pilot_v2_runner.py",
            },
            "runtime_path": RUNTIME_PATH,
            "runtime_file_sha256": file_sha256(runtime_path),
            "commands": ["validate", "preflight", "reachability", "batch", "report"],
        },
        "terminal_taxonomy": copy.deepcopy(parent["execution_candidate"]["terminal_taxonomy"]),
        "preregistration": {
            "path": PREREGISTRATION_PATH,
            "file_sha256": file_sha256(preregistration_path),
        },
    }


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    parent, _parent_protocol = _parent_manifest(repo_root)
    value = copy.deepcopy(parent)
    value["$schema"] = "../schemas/forge-opaque-provenance-confirmatory-execution-authorized.schema.json"
    value["schema_version"] = SCHEMA_VERSION
    value["document_type"] = DOCUMENT_TYPE
    value["runtime_contract"]["provider_identity_status"] = "active_authorized"
    value["authorization"] = {
        "provider_calls_authorized": True,
        "credential_read_authorized": True,
        "model_creation_authorized": True,
        "reachability_request_authorized": True,
        "checkpoint_creation_authorized": True,
        "pair_collection_authorized": True,
        "formal_attempts_authorized": True,
        "docker_execution_authorized": True,
        "evidence_write_authorized": True,
        "model_tokens_authorized": parent["runtime_contract"]["batch_recorded_token_ceiling"],
    }
    value["future_state"] = {
        "checkpoint_status": "authorized_not_created",
        "evidence_status": "authorized_not_created",
        "execution_runner_status": "authorized_real_pair_runner",
        "execution_requires_new_amendment": False,
    }
    value["authorized_execution"] = _authorized_execution(parent, repo_root)
    value["frozen_parent_components"] = _frozen_parent_sha256(repo_root)
    value["preregistration"] = copy.deepcopy(value["authorized_execution"]["preregistration"])
    return value


def validate_allowed_delta(value: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    parent, _parent_protocol = _parent_manifest(repo_root)
    normalized = copy.deepcopy(value)
    authorized = normalized.pop("authorized_execution", None)
    normalized.pop("frozen_parent_components", None)
    normalized["$schema"] = parent["$schema"]
    normalized["schema_version"] = parent["schema_version"]
    normalized["document_type"] = parent["document_type"]
    normalized["runtime_contract"] = copy.deepcopy(parent["runtime_contract"])
    normalized["authorization"] = copy.deepcopy(parent["authorization"])
    normalized["future_state"] = copy.deepcopy(parent["future_state"])
    normalized["preregistration"] = copy.deepcopy(parent["preregistration"])
    if normalized != parent:
        raise ProtocolError("authorized amendment 包含未预注册的父协议差异")
    if authorized != _authorized_execution(parent, repo_root):
        raise ProtocolError("authorized execution identity 发生漂移")
    return {
        "status": "passed",
        "parent_manifest_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "schedule_identity_sha256": parent["schedule"]["identity_sha256"],
        "evidence_identity_sha256": authorized["evidence"]["identity_sha256"],
        "verifier_relaxation": False,
        "historical_evidence_reused": False,
    }


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    expected = generate_manifest(repo_root)
    if not isinstance(value, dict) or value != expected:
        raise ProtocolError("authorized confirmatory manifest 发生漂移")
    validate_allowed_delta(value, repo_root)
    authorization = value["authorization"]
    if authorization["model_tokens_authorized"] != value["authorized_execution"]["budget"]["batch_maximum_recorded_tokens"]:
        raise ProtocolError("授权 token ceiling 发生漂移")
    if not all(item is True for key, item in authorization.items() if key.endswith("_authorized") and key != "model_tokens_authorized"):
        raise ProtocolError("真实执行授权未闭合")
    return value


def load_manifest(
    path: Path = DEFAULT_MANIFEST,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError("无法读取 authorized confirmatory manifest") from exc
    return validate_manifest(value, repo_root)


def verify_frozen_components(
    manifest: dict[str, Any],
    repo_root: Path = REPO_ROOT,
) -> None:
    if manifest["frozen_parent_components"] != _frozen_parent_sha256(repo_root):
        raise ProtocolError("Issue #235 冻结组件发生漂移")
    execution = manifest["authorized_execution"]["execution"]
    if file_sha256(repo_root / execution["runtime_path"]) != execution["runtime_file_sha256"]:
        raise ProtocolError("authorized runtime 发生漂移")


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    frozen = manifest or generate_manifest()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-opaque-provenance-confirmatory-execution-authorized.schema.json",
        "title": "Forge opaque provenance confirmatory execution authorized amendment",
        "const": frozen,
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args(argv)
    if args.command == "generate":
        manifest = generate_manifest()
        _write_json(args.manifest, manifest)
        _write_json(args.schema, schema_document(manifest))
    else:
        manifest = load_manifest(args.manifest)
        if json.loads(args.schema.read_text(encoding="utf-8")) != schema_document(manifest):
            raise ProtocolError("authorized const schema 发生漂移")
    print(
        json.dumps(
            {
                "manifest_sha256": canonical_sha256(manifest),
                "authorization": manifest["authorization"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
