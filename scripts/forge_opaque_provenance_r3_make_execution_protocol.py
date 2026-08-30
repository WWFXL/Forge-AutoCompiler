#!/usr/bin/env python3
"""Issue #218 R3 Make 单配对 execution amendment。"""

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
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-r3-make-execution.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-r3-make-execution.schema.json"
PARENT_MANIFEST_PATH = "benchmarks/manifests/cpp-opaque-provenance-r3-make-candidate.json"
RUNTIME_ADAPTER_PATH = "scripts/forge_opaque_provenance_r3_make_execution_runner.py"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-opaque-provenance-r3-make-execution.md"

SCHEMA_VERSION = "forge-opaque-provenance-r3-make-execution-1.0.0"
DOCUMENT_TYPE = "forge_opaque_provenance_r3_make_execution_amendment"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/218"
AUTHORIZATION_BASELINE_COMMIT = "4190ad433bf015e93b68fdefc4eb8de8b11c25a2"
PARENT_MANIFEST_CANONICAL_SHA256 = "e45c9a5cfbba70d30ee2c82a68631a3430ea3e66748d808888660cae5c105d7b"
PARENT_EVIDENCE_IDENTITY_SHA256 = "17bf1a758d953f4e0c579039c97c8a3e669caf92ca720f93b3edfe29116c9890"
REFERENCE_CASE_ID = "hoextdown-opaque-provenance-r2-make-lifecycle"

FROZEN_PARENT_PATHS = {
    PARENT_MANIFEST_PATH,
    "benchmarks/preregistrations/cpp-opaque-provenance-r3-make-candidate.md",
    "benchmarks/schemas/forge-opaque-provenance-r3-make-candidate.schema.json",
    "scripts/forge_opaque_provenance_r3_make_candidate_protocol.py",
    "scripts/forge_opaque_provenance_r3_make_candidate_runner.py",
    "backend/tests/test_forge_opaque_provenance_r3_make_candidate.py",
}
FROZEN_PARENT_SHA256 = {
    PARENT_MANIFEST_PATH: "96b1a5a715572022bd4641360d337e6c9839e77c5a4cdbc52f5150b2dbce4a2a",
    "benchmarks/preregistrations/cpp-opaque-provenance-r3-make-candidate.md": "57d56d685ed76d3ad2957906a4fe46b23dd3e8eb17302542706bac10b476e9a9",
    "benchmarks/schemas/forge-opaque-provenance-r3-make-candidate.schema.json": "478cc5044f96ed20dd4e26127a1d51c30a55ca8a8014d3c8da68395a78898c1f",
    "scripts/forge_opaque_provenance_r3_make_candidate_protocol.py": "09dd3c85ba82f7b9e5a628fdefd7ceaaf27288bf9724b48115098b14cc6234a1",
    "scripts/forge_opaque_provenance_r3_make_candidate_runner.py": "b8ec84f3835ecbbc462232b676c5ebf72e15a7f021be2a148d1b85d8138e9be0",
    "backend/tests/test_forge_opaque_provenance_r3_make_candidate.py": "1240d5c1afad071b99cc59943b7c406bd03954c6c2eec0e15dbdcabbc538d917",
}


class ProtocolError(RuntimeError):
    """R3 execution 身份、预算、授权或冻结组件无效。"""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_parent_protocol(repo_root: Path = REPO_ROOT):
    path = repo_root / "scripts/forge_opaque_provenance_r3_make_candidate_protocol.py"
    name = "forge_opaque_provenance_r3_make_execution_parent"
    existing = sys.modules.get(name)
    if existing is not None and Path(existing.__file__).resolve() == path.resolve():
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ProtocolError("cannot load R3 Make candidate")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _parent_manifest(repo_root: Path = REPO_ROOT) -> tuple[dict[str, Any], Any]:
    parent = _load_parent_protocol(repo_root)
    manifest = parent.load_manifest(repo_root / PARENT_MANIFEST_PATH, repo_root)
    if parent.canonical_sha256(manifest) != PARENT_MANIFEST_CANONICAL_SHA256:
        raise ProtocolError("R3 Make candidate canonical identity drifted")
    if manifest["evidence"]["identity_sha256"] != PARENT_EVIDENCE_IDENTITY_SHA256:
        raise ProtocolError("R3 Make candidate evidence identity drifted")
    return manifest, parent


def _hash_paths(repo_root: Path, paths: set[str]) -> dict[str, str]:
    result = {path: file_sha256(repo_root / path) for path in sorted(paths)}
    if result != FROZEN_PARENT_SHA256:
        raise ProtocolError("R3 candidate frozen component identity drifted")
    return result


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    parent, _parent_protocol = _parent_manifest(repo_root)
    runtime_path = repo_root / RUNTIME_ADAPTER_PATH
    preregistration_path = repo_root / PREREGISTRATION_PATH
    if not runtime_path.is_file() or not preregistration_path.is_file():
        raise ProtocolError("R3 execution runtime or preregistration is missing")

    case = copy.deepcopy(parent["case"])
    case["reference_case_id"] = REFERENCE_CASE_ID
    provider = copy.deepcopy(parent["provider"])
    provider["status"] = "active_authorized"
    evidence = {
        "schema_version": "forge-opaque-provenance-r3-make-evidence-1.0.0",
        "directory": "/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-r3-hoextdown-v1",
        "checkpoint_manifest": "checkpoints/opaque-provenance-r3-hoextdown-pair-01/checkpoint.json",
        "parent_ledger": "checkpoints/opaque-provenance-r3-hoextdown-pair-01/parent/events.jsonl",
        "pair_ledger": "pairs/opaque-provenance-r3-hoextdown-pair-01/events.jsonl",
        "arm_ledger_directory": "pairs/opaque-provenance-r3-hoextdown-pair-01/arms",
        "reachability_marker": "markers/reachability.json",
        "pair_marker": "markers/pair.json",
        "canary_report": "reports/canary.json",
        "append_only": True,
        "status": "authorized_not_created",
        "zero_provider_preflight_writes_evidence": False,
        "identity_sha256": PARENT_EVIDENCE_IDENTITY_SHA256,
    }
    return {
        "$schema": "../schemas/forge-opaque-provenance-r3-make-execution.schema.json",
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
            "model_tokens_authorized": 245000,
        },
        "parent": {
            "manifest_path": PARENT_MANIFEST_PATH,
            "schema_version": parent["schema_version"],
            "canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
            "file_sha256": FROZEN_PARENT_SHA256[PARENT_MANIFEST_PATH],
            "evidence_identity_sha256": PARENT_EVIDENCE_IDENTITY_SHA256,
            "authorization_baseline_commit": AUTHORIZATION_BASELINE_COMMIT,
            "release_revision_policy": "descendant-compatible",
        },
        "case": case,
        "checkpoint": {
            "source_gate": "issue-214-r3-make-lifecycle-zero-provider",
            "creation_timing": "after_reachability_before_arm_continuation",
            "capture_point": "after-neutral-tool-message-before-continuation",
            "identity_materialized_during_pair": True,
            "arm_state_matching": ["message", "environment", "budget"],
            "preexisting_checkpoint_reuse_forbidden": True,
        },
        "provider": provider,
        "continuation": copy.deepcopy(parent["continuation"]),
        "schedule": copy.deepcopy(parent["schedule"]),
        "schedule_sha256": parent["schedule_sha256"],
        "repair_packet": copy.deepcopy(parent["repair_packet"]),
        "budget": {
            "maximum_reachability_requests": 1,
            "reachability_maximum_recorded_tokens": 5000,
            "recorded_tokens_per_arm": 120000,
            "recorded_tokens_per_pair": 240000,
            "stage_maximum_recorded_tokens": 245000,
            "enforcement": "after_reachability_and_each_arm_before_continuation",
        },
        "stopping": copy.deepcopy(parent["stopping"]),
        "analysis": copy.deepcopy(parent["analysis"]),
        "runtime_parity": copy.deepcopy(parent["runtime_parity"]),
        "r0_observability": copy.deepcopy(parent["r0_observability"]),
        "evidence": evidence,
        "opportunities": {
            "maximum_reachability_requests": 1,
            "maximum_pairs": 1,
            "required_order": ["reachability", parent["schedule"][0]["pair_id"]],
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
            "report_schema_version": "forge-opaque-provenance-r3-make-report-1.0.0",
            "report_document_type": "forge_opaque_provenance_r3_make_report",
        },
        "preregistration": {
            "path": PREREGISTRATION_PATH,
            "file_sha256": file_sha256(preregistration_path),
        },
        "runtime_adapter": {
            "path": RUNTIME_ADAPTER_PATH,
            "file_sha256": file_sha256(runtime_path),
            "derived_from_path": "scripts/forge_opaque_provenance_r2_make_execution_runner.py",
            "derived_from_sha256": "0854a836f347d371974594eadb32f72d0cff4361bcb06bd5e1ad2a9effef78c0",
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
    if not isinstance(value, dict) or value != generate_manifest(repo_root):
        raise ProtocolError("R3 Make execution manifest drifted")
    if value["authorization"]["model_tokens_authorized"] != value["budget"]["stage_maximum_recorded_tokens"]:
        raise ProtocolError("R3 Make token authorization drifted")
    if value["case"]["reference_case_id"] != REFERENCE_CASE_ID:
        raise ProtocolError("R3 Make reference case identity drifted")
    return value


def load_manifest(path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError("cannot load R3 Make execution manifest") from exc
    return validate_manifest(value, repo_root)


def verify_frozen_components(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> None:
    if manifest["frozen_parent_components"] != _hash_paths(repo_root, FROZEN_PARENT_PATHS):
        raise ProtocolError("R3 Make execution frozen components drifted")
    if file_sha256(repo_root / RUNTIME_ADAPTER_PATH) != manifest["runtime_adapter"]["file_sha256"]:
        raise ProtocolError("R3 Make execution runtime adapter drifted")


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    frozen = manifest or generate_manifest()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-opaque-provenance-r3-make-execution.schema.json",
        "title": "Forge opaque provenance R3 Make execution amendment",
        "const": frozen,
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


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
    print(json.dumps({"manifest_sha256": canonical_sha256(manifest), "authorization": manifest["authorization"]}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
