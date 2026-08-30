#!/usr/bin/env python3
"""Issue #200 yyjson opaque provenance R1 一次性 execution amendment。"""

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
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-r1-execution.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-r1-execution.schema.json"
PARENT_MANIFEST_PATH = "benchmarks/manifests/cpp-opaque-provenance-r1-checkpoint-candidate.json"
RUNTIME_ADAPTER_PATH = "scripts/forge_opaque_provenance_r1_execution_runner.py"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-opaque-provenance-r1-execution.md"

SCHEMA_VERSION = "forge-opaque-provenance-r1-execution-1.0.0"
DOCUMENT_TYPE = "forge_opaque_provenance_r1_execution_amendment"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/200"
AUTHORIZATION_BASELINE_COMMIT = "6e0abe1483ace50174574b7405e26ad8bda2f845"
PARENT_MANIFEST_SHA256 = "b89e63c4362befcdc409c60fe0334c1e9e4f62a26e369d55b676f23c1ffd202b"
PARENT_EVIDENCE_IDENTITY_SHA256 = "d4b5f051bde5c66e5a1b4c67da72c91443d15c614b209941f71d7a02c4f57077"

FROZEN_PARENT_PATHS = {
    PARENT_MANIFEST_PATH,
    "benchmarks/preregistrations/cpp-opaque-provenance-r1-checkpoint-candidate.md",
    "benchmarks/preregistrations/cpp-opaque-provenance-r1-checkpoint-zero-provider-gate.md",
    "benchmarks/schemas/forge-opaque-provenance-r1-checkpoint-candidate.schema.json",
    "scripts/forge_opaque_provenance_r1_candidate_protocol.py",
    "scripts/forge_opaque_provenance_r1_candidate_runner.py",
    "scripts/forge_opaque_provenance_r1_checkpoint_gate.py",
    "backend/tests/test_forge_opaque_provenance_r1_candidate.py",
    "backend/tests/test_forge_opaque_provenance_r1_checkpoint_gate.py",
    "backend/tests/test_forge_opaque_provenance_r1_checkpoint_gate_docker.py",
}


class ProtocolError(RuntimeError):
    """R1 execution 身份、父组件、预算或授权发生漂移。"""


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
    path = repo_root / "scripts/forge_opaque_provenance_r1_candidate_protocol.py"
    name = "forge_opaque_provenance_r1_execution_parent"
    existing = sys.modules.get(name)
    if existing is not None and Path(existing.__file__).resolve() == path.resolve():
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ProtocolError("cannot load R1 checkpoint candidate")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _parent_manifest(repo_root: Path = REPO_ROOT) -> tuple[dict[str, Any], Any]:
    parent = _load_parent_protocol(repo_root)
    manifest = parent.load_manifest(repo_root / PARENT_MANIFEST_PATH, repo_root)
    if parent.canonical_sha256(manifest) != PARENT_MANIFEST_SHA256:
        raise ProtocolError("R1 candidate manifest identity drifted")
    if manifest["evidence"]["identity_sha256"] != PARENT_EVIDENCE_IDENTITY_SHA256:
        raise ProtocolError("R1 candidate evidence identity drifted")
    return manifest, parent


def _hash_paths(repo_root: Path, paths: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative_path in sorted(paths):
        path = repo_root / relative_path
        if not path.is_file():
            raise ProtocolError(f"frozen component missing: {relative_path}")
        result[relative_path] = file_sha256(path)
    return result


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    parent_manifest, parent = _parent_manifest(repo_root)
    runtime_path = repo_root / RUNTIME_ADAPTER_PATH
    preregistration_path = repo_root / PREREGISTRATION_PATH
    if not runtime_path.is_file() or not preregistration_path.is_file():
        raise ProtocolError("runtime adapter or preregistration missing")

    provider = copy.deepcopy(parent_manifest["provider"])
    provider["status"] = "active_authorized"
    runtime_parity = copy.deepcopy(parent_manifest["runtime_parity"])
    runtime_parity.update(
        parent_submit_uses_bound_wrapper=True,
        fence_released_before_capture=True,
        observable_adapter="ObservableRuntimeParityToolAdapter",
        rejection_registry="RejectionObservationRegistry",
    )
    evidence = copy.deepcopy(parent_manifest["evidence"])
    evidence["status"] = "authorized_not_created"
    return {
        "$schema": "../schemas/forge-opaque-provenance-r1-execution.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "authorization": {
            "issue_url": ISSUE_URL,
            "checkpoint_creation_authorized": True,
            "reachability_request_authorized": True,
            "provider_calls_authorized": True,
            "formal_attempts_authorized": True,
            "pair_collection_authorized": True,
            "credential_read_authorized": True,
            "model_creation_authorized": True,
            "docker_execution_authorized": True,
            "evidence_write_authorized": True,
            "model_tokens_authorized": 245_000,
        },
        "parent": {
            "manifest_path": PARENT_MANIFEST_PATH,
            "schema_version": parent_manifest["schema_version"],
            "canonical_sha256": parent.canonical_sha256(parent_manifest),
            "file_sha256": file_sha256(repo_root / PARENT_MANIFEST_PATH),
            "evidence_identity_sha256": parent_manifest["evidence"]["identity_sha256"],
            "authorization_baseline_commit": AUTHORIZATION_BASELINE_COMMIT,
            "release_revision_policy": "descendant-compatible",
        },
        "case": copy.deepcopy(parent_manifest["case"]),
        "independence": copy.deepcopy(parent_manifest["independence"]),
        "checkpoint": {
            "source_gate": "issue-198-real-docker-zero-provider",
            "creation_timing": "after_reachability_before_arm_continuation",
            "capture_point": "after-neutral-tool-message-before-continuation",
            "identity_materialized_during_pair": True,
            "arm_state_matching": ["message", "environment", "budget"],
            "preexisting_checkpoint_reuse_forbidden": True,
        },
        "provider": provider,
        "continuation": copy.deepcopy(parent_manifest["continuation"]),
        "schedule": copy.deepcopy(parent_manifest["schedule"]),
        "schedule_sha256": parent_manifest["schedule_sha256"],
        "repair_packet": copy.deepcopy(parent_manifest["repair_packet"]),
        "budget": {
            "maximum_reachability_requests": 1,
            "reachability_maximum_recorded_tokens": 5_000,
            "recorded_tokens_per_arm": 120_000,
            "recorded_tokens_per_pair": 240_000,
            "stage_maximum_recorded_tokens": 245_000,
            "enforcement": "after_reachability_and_each_arm_before_continuation",
        },
        "stopping": {
            **copy.deepcopy(parent_manifest["stopping"]),
            "classified_arm_outcome_continues_other_arm": True,
            "endpoint_timeout_censors_arm_and_continues": True,
        },
        "analysis": copy.deepcopy(parent_manifest["analysis"]),
        "runtime_parity": runtime_parity,
        "r0_observability": copy.deepcopy(parent_manifest["r0_observability"]),
        "evidence": evidence,
        "opportunities": {
            "maximum_reachability_requests": 1,
            "maximum_pairs": 1,
            "required_order": ["reachability", parent_manifest["schedule"][0]["pair_id"]],
            "marker_consumed_on_start": True,
            "retry_replacement_backfill_forbidden": True,
            "schedule_extension_forbidden": True,
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
            "require_empty_evidence_directory": True,
            "managed_container_prefixes": ["deerflow-compile-", "deerflow-replay-"],
            "require_zero_managed_orphans": True,
        },
        "execution": {
            "release_branch": "main",
            "network_access_medium_env": "FORGE_NETWORK_ACCESS_MEDIUM",
            "reachability_prompt": "Reply with exactly CANARY_OK and nothing else.",
            "reachability_expected_response": "CANARY_OK",
            "reachability_report": "reports/reachability.json",
            "pair_marker": evidence["pair_marker"],
            "parent_ledger": evidence["parent_ledger"],
            "arm_ledger_directory": evidence["arm_ledger_directory"],
            "report_schema_version": "forge-opaque-provenance-r1-report-1.0.0",
            "report_document_type": "forge_opaque_provenance_r1_report",
        },
        "preregistration": {
            "path": PREREGISTRATION_PATH,
            "file_sha256": file_sha256(preregistration_path),
        },
        "runtime_adapter": {
            "path": RUNTIME_ADAPTER_PATH,
            "file_sha256": file_sha256(runtime_path),
            "commands": ["validate", "preflight", "reachability", "pair"],
            "credential_read_supported": True,
            "provider_model_creation_supported": True,
            "checkpoint_execute_supported": True,
            "reachability_execute_supported": True,
            "pair_execute_supported": True,
            "r0_companion_evidence_supported": True,
        },
        "frozen_parent_components": _hash_paths(repo_root, FROZEN_PARENT_PATHS),
    }


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError("manifest must be an object")
    if value != generate_manifest(repo_root):
        raise ProtocolError("R1 execution amendment manifest drifted")
    budget = value["budget"]
    if budget["recorded_tokens_per_pair"] + budget["reachability_maximum_recorded_tokens"] != budget["stage_maximum_recorded_tokens"]:
        raise ProtocolError("stage token budget is not closed")
    if value["runtime_parity"]["parallel_tool_calls"] is not False:
        raise ProtocolError("parallel tool calls must remain disabled")
    if value["r0_observability"]["companion_required_for_classified_rejection"] is not True:
        raise ProtocolError("classified rejection companion evidence is required")
    return value


def load_manifest(path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError("cannot read R1 execution manifest") from exc
    return validate_manifest(value, repo_root)


def verify_frozen_components(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> None:
    validate_manifest(manifest, repo_root)
    if manifest["frozen_parent_components"] != _hash_paths(repo_root, FROZEN_PARENT_PATHS):
        raise ProtocolError("frozen parent components drifted")
    for section in ("runtime_adapter", "preregistration"):
        path = repo_root / manifest[section]["path"]
        if file_sha256(path) != manifest[section]["file_sha256"]:
            raise ProtocolError(f"{section} drifted")


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    frozen = manifest or generate_manifest()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-opaque-provenance-r1-execution.schema.json",
        "title": "Forge opaque provenance R1 execution amendment",
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
        verify_frozen_components(manifest)
    print(
        json.dumps(
            {
                "manifest_sha256": canonical_sha256(manifest),
                "provider_calls": 0,
                "formal_attempts": 0,
                "model_tokens": 0,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
