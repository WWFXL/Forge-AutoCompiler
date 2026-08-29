#!/usr/bin/env python3
"""Issue #182 opaque provenance 最小 canary 授权候选协议。"""

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
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-minimal-canary-authorized.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-minimal-canary-authorized.schema.json"
PARENT_MANIFEST_PATH = "benchmarks/manifests/cpp-opaque-provenance-minimal-canary.json"
RUNTIME_ADAPTER_PATH = "scripts/forge_opaque_provenance_minimal_canary_authorized_runner.py"

SCHEMA_VERSION = "forge-opaque-provenance-minimal-canary-authorized-1.0.0"
DOCUMENT_TYPE = "forge_opaque_provenance_minimal_canary_authorized_candidate"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/182"
AUTHORIZATION_BASELINE_COMMIT = "06ba008ddaa77956ce39e97f30f79e27a1a0639e"
PARENT_MANIFEST_SHA256 = "ad5a1ac989c4072ec097a3b0949d5e4393475d6df0896e108dbc313690dd3ee7"
EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-minimal-canary-authorized-v1"
EVIDENCE_SCHEMA_VERSION = "forge-opaque-provenance-minimal-canary-evidence-1.0.0"

FROZEN_PARENT_PATHS = {
    "benchmarks/manifests/cpp-opaque-provenance-minimal-canary.json",
    "benchmarks/preregistrations/cpp-opaque-provenance-minimal-canary.md",
    "benchmarks/schemas/forge-opaque-provenance-minimal-canary.schema.json",
    "scripts/forge_opaque_provenance_minimal_canary_protocol.py",
}


class ProtocolError(RuntimeError):
    """授权候选、父协议或 evidence identity 发生漂移。"""


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
    path = repo_root / "scripts/forge_opaque_provenance_minimal_canary_protocol.py"
    name = "forge_opaque_provenance_minimal_canary_authorized_parent"
    existing = sys.modules.get(name)
    if existing is not None and Path(existing.__file__).resolve() == path.resolve():
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ProtocolError("cannot load parent minimal canary protocol")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _parent_manifest(repo_root: Path = REPO_ROOT) -> tuple[dict[str, Any], Any]:
    parent = _load_parent_protocol(repo_root)
    manifest = parent.load_manifest(repo_root / PARENT_MANIFEST_PATH, repo_root)
    if parent.canonical_sha256(manifest) != PARENT_MANIFEST_SHA256:
        raise ProtocolError("parent minimal canary identity drifted")
    return manifest, parent


def _hash_paths(repo_root: Path, paths: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative_path in sorted(paths):
        path = repo_root / relative_path
        if not path.is_file():
            raise ProtocolError(f"frozen component missing: {relative_path}")
        result[relative_path] = file_sha256(path)
    return result


def _evidence_identity(parent_manifest: dict[str, Any]) -> dict[str, Any]:
    identity = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "directory": EVIDENCE_DIRECTORY,
        "preflight_snapshot": "preflight/preflight.json",
        "reachability_marker": "markers/reachability.json",
        "pair_ledger": f"pairs/{parent_manifest['schedule'][0]['pair_id']}/events.jsonl",
        "canary_report": "reports/canary.json",
        "append_only": True,
        "marker_consumed_on_start": True,
        "zero_provider_preflight_writes_evidence": False,
    }
    return {**identity, "identity_sha256": canonical_sha256(identity)}


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    parent_manifest, parent = _parent_manifest(repo_root)
    evidence = _evidence_identity(parent_manifest)
    runtime_path = repo_root / RUNTIME_ADAPTER_PATH
    if not runtime_path.is_file():
        raise ProtocolError(f"runtime adapter missing: {RUNTIME_ADAPTER_PATH}")
    return {
        "$schema": "../schemas/forge-opaque-provenance-minimal-canary-authorized.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "authorization": {
            "issue_url": ISSUE_URL,
            "runtime_adapter_candidate_authorized": True,
            "zero_provider_preflight_authorized": True,
            "reachability_request_authorized": False,
            "provider_calls_authorized": False,
            "formal_attempts_authorized": False,
            "canary_collection_authorized": False,
            "model_tokens_authorized": 0,
        },
        "parent": {
            "manifest_path": PARENT_MANIFEST_PATH,
            "schema_version": parent_manifest["schema_version"],
            "canonical_sha256": parent.canonical_sha256(parent_manifest),
            "file_sha256": file_sha256(repo_root / PARENT_MANIFEST_PATH),
            "authorization_baseline_commit": AUTHORIZATION_BASELINE_COMMIT,
            "release_revision_policy": "descendant-compatible",
        },
        "case": copy.deepcopy(parent_manifest["case"]),
        "provider": copy.deepcopy(parent_manifest["provider"]),
        "continuation": copy.deepcopy(parent_manifest["continuation"]),
        "schedule": copy.deepcopy(parent_manifest["schedule"]),
        "schedule_sha256": parent_manifest["schedule_sha256"],
        "budget": copy.deepcopy(parent_manifest["budget"]),
        "stopping": copy.deepcopy(parent_manifest["stopping"]),
        "analysis": copy.deepcopy(parent_manifest["analysis"]),
        "evidence": evidence,
        "opportunities": {
            "maximum_reachability_requests": 1,
            "maximum_canary_pairs": 1,
            "required_order": ["reachability", parent_manifest["schedule"][0]["pair_id"]],
            "retry_replacement_backfill_forbidden": True,
        },
        "preflight": {
            "release_branch": "main",
            "require_clean_worktree": True,
            "require_head_equals_origin_main": True,
            "require_authorization_baseline_ancestor": True,
            "docker_provider": "ubuntu-native",
            "docker_context": "default",
            "docker_endpoint": "/var/run/docker.sock",
            "allowed_network_media": ["wired", "wifi", "mobile_hotspot"],
            "require_empty_evidence_directory": True,
            "managed_container_prefixes": ["deerflow-compile-", "deerflow-replay-"],
            "require_zero_managed_orphans": True,
        },
        "runtime_adapter": {
            "path": RUNTIME_ADAPTER_PATH,
            "file_sha256": file_sha256(runtime_path),
            "commands": ["validate", "plan", "preflight"],
            "credential_read_supported": False,
            "provider_model_creation_supported": False,
            "reachability_execute_supported": False,
            "canary_execute_supported": False,
        },
        "frozen_parent_components": _hash_paths(repo_root, FROZEN_PARENT_PATHS),
    }


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError("manifest must be an object")
    if value != generate_manifest(repo_root):
        raise ProtocolError("opaque provenance authorized candidate manifest drifted")
    return value


def load_manifest(path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError("cannot read opaque provenance authorized candidate manifest") from exc
    return validate_manifest(value, repo_root)


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    frozen = manifest or generate_manifest()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-opaque-provenance-minimal-canary-authorized.schema.json",
        "title": "Forge opaque provenance minimal canary authorized candidate",
        "const": frozen,
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "generate":
        manifest = generate_manifest()
        _write_json(args.manifest, manifest)
        _write_json(args.schema, schema_document(manifest))
    else:
        manifest = load_manifest(args.manifest)
    print(
        json.dumps(
            {
                "manifest_sha256": canonical_sha256(manifest),
                "provider_calls": 0,
                "formal_attempts": 0,
                "model_tokens": 0,
                "evidence_writes": 0,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
