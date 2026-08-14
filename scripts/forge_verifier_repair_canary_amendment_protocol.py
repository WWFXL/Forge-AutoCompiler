#!/usr/bin/env python3
"""生成并校验 verifier-driven repair 单次 canary 修订协议。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", SCRIPT_ROOT.parent)).resolve()
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_verifier_repair_authorized_protocol as parent_protocol  # noqa: E402

SCHEMA_VERSION = "verifier-driven-repair-pilot-canary-amendment-1.0.0"
BASELINE_COMMIT = "9a63bc0ac07b71a531a5400197f0fb836b687fc1"
PARENT_CANONICAL_SHA256 = "ff30e38d643c211c3f2f6d33a6f9424d9410168d81ecb2c4f47ffb79e4a61875"
EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-verifier-repair-canary-amendment"
SUPERSEDED_EVIDENCE_DIRECTORY = parent_protocol.EVIDENCE_DIRECTORY

REVISION_POLICY = parent_protocol.REVISION_POLICY
CONTROL_PLANE_TOPOLOGY = parent_protocol.CONTROL_PLANE_TOPOLOGY
DOCKER_DAEMON_PROVIDER = parent_protocol.DOCKER_DAEMON_PROVIDER
DOCKER_SOCKET_PATH = parent_protocol.DOCKER_SOCKET_PATH
RECORDED_TOKEN_LIMIT = parent_protocol.RECORDED_TOKEN_LIMIT
EXPECTED_RECORDED_TOKENS = parent_protocol.EXPECTED_RECORDED_TOKENS

DEFAULT_PARENT_MANIFEST = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-verifier-repair-pilot-authorized.json"
DEFAULT_MANIFEST = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-verifier-repair-pilot-canary-amendment.json"
DEFAULT_SCHEMA = REPOSITORY_ROOT / "benchmarks" / "schemas" / "forge-verifier-repair-pilot-canary-amendment-v1.schema.json"

PROTOCOL_ARTIFACT_PATHS = {
    "scripts/forge_verifier_repair_canary_amendment_protocol.py",
    "scripts/forge_verifier_repair_canary_amendment_runner.py",
    "scripts/forge_verifier_repair_canary_amendment_report.py",
}

SUPERSEDED_CANARY_TERMINAL = {
    "benchmark_id": "forge-verifier-driven-repair-pilot-authorized",
    "manifest_sha256": PARENT_CANONICAL_SHA256,
    "evidence_directory": SUPERSEDED_EVIDENCE_DIRECTORY,
    "marker_relative_path": "provider-canaries/verifier-repair-provider-canary-attempt.json",
    "marker_sha256": "1a2b7bc7547e30ef56b1340420e435bd44b2f56df5e025a90653f5f88a39bcd7",
    "status": "failed",
    "error_class": None,
    "provider_report_relative_path": "provider-canaries/provider_canary_2de75d5184664bb08d572e026161cef9.json",
    "provider_report_sha256": "a8cc041ba4213a9f35169e4c48273c4ba4911e84e467c7f55fd5143bff2283a5",
    "provider_report_count": 1,
    "formal_ledger_count": 0,
}

ProtocolError = parent_protocol.ProtocolError
canonical_json_bytes = parent_protocol.canonical_json_bytes


def _load_json(path: Path) -> dict[str, Any]:
    return parent_protocol._load_json(path)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_paths(repo_root: Path, paths: set[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative_path in sorted(paths):
        path = repo_root / relative_path
        if not path.is_file():
            raise ProtocolError(f"protocol artifact is missing: {relative_path}")
        hashes[relative_path] = _file_sha256(path)
    return hashes


def _parent_manifest(document: dict[str, Any] | None = None) -> dict[str, Any]:
    parent = parent_protocol.validate_manifest(document or _load_json(DEFAULT_PARENT_MANIFEST))
    if parent_protocol.manifest_sha256(parent) != PARENT_CANONICAL_SHA256:
        raise ProtocolError("parent authorized manifest canonical SHA-256 drifted")
    return parent


def _authorization(parent: dict[str, Any]) -> dict[str, Any]:
    authorization = copy.deepcopy(parent["authorization"])
    authorization.update(
        {
            "id": "forge-verifier-driven-repair-pilot-canary-amendment",
            "status": "authorized_single_canary_amendment",
            "authorized_on": "2026-08-14",
            "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/131",
            "implementation_baseline_commit": BASELINE_COMMIT,
            "parent_manifest": {
                "id": parent["benchmark"]["id"],
                "path": "benchmarks/manifests/cpp-verifier-repair-pilot-authorized.json",
                "canonical_sha256": PARENT_CANONICAL_SHA256,
            },
            "superseded_canary_terminal": copy.deepcopy(SUPERSEDED_CANARY_TERMINAL),
            "nonformal_diagnostic": {
                "provider_condition": "richlab-gpt-5.5",
                "request_count": 1,
                "request_timeout_seconds": 60,
                "max_retries": 0,
                "duration_ms": 5983,
                "passed": True,
                "excluded_from_formal_evidence": True,
                "response_body_storage_forbidden": True,
            },
            "new_canary": {
                "maximum_attempts": 1,
                "authenticated_requests_per_provider": 1,
                "request_timeout_seconds": 300,
                "max_retries": 0,
                "success_required_before_first_ledger": True,
            },
        }
    )
    authorization["network_observation"] = {
        **authorization["network_observation"],
        "last_observed_access_medium": "wifi",
    }
    authorization["collection_constraints"]["evidence_directory"] = EVIDENCE_DIRECTORY
    return authorization


def generate_manifest(
    repo_root: Path = REPOSITORY_ROOT,
    *,
    parent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parent = _parent_manifest(parent)
    manifest = copy.deepcopy(parent)
    manifest["$schema"] = "../schemas/forge-verifier-repair-pilot-canary-amendment-v1.schema.json"
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["benchmark"] = {
        "id": "forge-verifier-driven-repair-pilot-canary-amendment",
        "name": "Forge C/C++ verifier-driven repair paired pilot canary amendment",
        "purpose": "execute one new authenticated provider canary before the unchanged paired pilot",
    }
    manifest["scope"] = {
        **copy.deepcopy(parent["scope"]),
        "phase": "verifier_driven_repair_pilot_canary_amendment",
    }
    manifest["authorization"] = _authorization(parent)
    manifest["forge"] = {
        **copy.deepcopy(parent["forge"]),
        "commit_sha": BASELINE_COMMIT,
    }
    manifest["protocol_artifact_sha256"] = _hash_paths(repo_root, PROTOCOL_ARTIFACT_PATHS)
    return manifest


def validate_manifest(
    document: Any,
    repo_root: Path = REPOSITORY_ROOT,
    *,
    parent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ProtocolError("canary amendment manifest must be an object")
    expected = generate_manifest(repo_root, parent=parent)
    if document != expected:
        raise ProtocolError("canary amendment manifest does not match the frozen protocol")
    return document


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()


def schema_document() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-verifier-repair-pilot-canary-amendment-v1.schema.json",
        "title": "Forge verifier-driven repair pilot canary amendment",
        "const": generate_manifest(),
    }


def verify_frozen_components(manifest: dict[str, Any], repo_root: Path = REPOSITORY_ROOT) -> None:
    validate_manifest(manifest, repo_root)
    parent = _parent_manifest(_load_json(DEFAULT_PARENT_MANIFEST))
    parent_protocol.verify_frozen_components(parent, repo_root)
    for relative_path, expected in manifest["protocol_artifact_sha256"].items():
        if _file_sha256(repo_root / relative_path) != expected:
            raise ProtocolError(f"canary amendment protocol artifact drifted: {relative_path}")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    generate.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    validate = subparsers.add_parser("validate-manifest")
    validate.add_argument("manifest", type=Path, nargs="?", default=DEFAULT_MANIFEST)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "generate":
            manifest = generate_manifest()
            _write_json(args.manifest, manifest)
            _write_json(args.schema, schema_document())
        else:
            manifest = validate_manifest(_load_json(args.manifest))
            verify_frozen_components(manifest)
    except (OSError, ProtocolError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "authorized_complete_pairs": 6,
                "authorized_slots": 12,
                "manifest_sha256": manifest_sha256(manifest),
                "maximum_recorded_tokens": RECORDED_TOKEN_LIMIT,
                "status": "valid",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
