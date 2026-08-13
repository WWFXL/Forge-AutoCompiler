#!/usr/bin/env python3
"""生成并校验 300 秒超时校准 canary 接线修订协议。"""

from __future__ import annotations

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

import forge_benchmark as v1  # noqa: E402
import forge_formal_runtime_protocol as _hasher  # noqa: E402
import forge_formal_timeout_calibration_protocol as parent_protocol  # noqa: E402

SCHEMA_VERSION = "formal-collection-4.6.0-timeout-canary-amendment"
BASELINE_COMMIT = "170d0c0524f958faa9cad7e05ddec20bbd3eaa4d"
PARENT_CANONICAL_SHA256 = "aeb1e66b85da53dbbe91c33059825d092143a4c0fa0b3045c327524767c9b10b"
EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-formal-timeout-canary-amendment"
SUPERSEDED_EVIDENCE_DIRECTORY = parent_protocol.EVIDENCE_DIRECTORY

REVISION_POLICY = parent_protocol.REVISION_POLICY
CONTROL_PLANE_TOPOLOGY = parent_protocol.CONTROL_PLANE_TOPOLOGY
DOCKER_DAEMON_PROVIDER = parent_protocol.DOCKER_DAEMON_PROVIDER
DOCKER_SOCKET_PATH = parent_protocol.DOCKER_SOCKET_PATH
COMPONENT_PATHS = parent_protocol.COMPONENT_PATHS
REQUEST_TIMEOUT_SECONDS = parent_protocol.REQUEST_TIMEOUT_SECONDS
AUTHORIZED_SCHEDULE_ORDERS = parent_protocol.AUTHORIZED_SCHEDULE_ORDERS
RECORDED_TOKEN_LIMIT = parent_protocol.RECORDED_TOKEN_LIMIT

DEFAULT_PARENT_MANIFEST = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-formal-timeout-calibration.json"
DEFAULT_MANIFEST = REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-formal-timeout-canary-amendment.json"
DEFAULT_SCHEMA = REPOSITORY_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-timeout-canary-amendment.schema.json"
PROTOCOL_ARTIFACT_PATHS = parent_protocol.PROTOCOL_ARTIFACT_PATHS | {
    "scripts/forge_formal_timeout_calibration_canary_amendment_protocol.py",
    "scripts/forge_formal_timeout_calibration_canary_amendment_runner.py",
    "scripts/forge_formal_timeout_calibration_canary_amendment_report.py",
    "benchmarks/preregistrations/cpp-formal-timeout-canary-amendment.md",
    "benchmarks/schemas/forge-cpp-formal-timeout-canary-amendment.schema.json",
}

SUPERSEDED_CANARY_TERMINAL = {
    "benchmark_id": "forge-cpp-formal-timeout-calibration",
    "manifest_sha256": PARENT_CANONICAL_SHA256,
    "evidence_directory": SUPERSEDED_EVIDENCE_DIRECTORY,
    "marker_relative_path": "provider-canaries/formal-v4-provider-canary-attempt.json",
    "marker_sha256": "cf4793d005d604f6ec287340675455932513c6c35641da27b7142b46526dc435",
    "status": "failed",
    "error_class": "RunnerError",
    "provider_report_count": 0,
    "formal_ledger_count": 0,
}

BenchmarkError = v1.BenchmarkError
load_json_document = v1.load_json_document
canonical_json_bytes = parent_protocol.canonical_json_bytes


def _parent_manifest(document: dict[str, Any] | None = None) -> dict[str, Any]:
    parent = parent_protocol.validate_manifest(document or load_json_document(DEFAULT_PARENT_MANIFEST))
    if parent_protocol.manifest_sha256(parent) != PARENT_CANONICAL_SHA256:
        v1._fail("manifest.authorization.parent_manifest", "does not match timeout calibration")
    return parent


def _authorization(parent: dict[str, Any]) -> dict[str, Any]:
    authorization = copy.deepcopy(parent["authorization"])
    authorization.update(
        {
            "id": "forge-cpp-formal-timeout-canary-amendment",
            "status": "authorized_bounded_timeout_canary_amendment",
            "authorized_on": "2026-08-14",
            "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/119",
            "implementation_baseline_commit": BASELINE_COMMIT,
            "superseded_canary_terminal": copy.deepcopy(SUPERSEDED_CANARY_TERMINAL),
            "new_canary": {
                "maximum_attempts": 1,
                "anonymous_models_endpoint_preflight": "forbidden",
                "authenticated_provider_request_required": True,
                "success_required_before_first_ledger": True,
            },
            "parent_manifest": {
                "id": parent["benchmark"]["id"],
                "path": "benchmarks/manifests/cpp-formal-timeout-calibration.json",
                "canonical_sha256": parent_protocol.manifest_sha256(parent),
            },
        }
    )
    authorization["collection_constraints"]["evidence_directory"] = EVIDENCE_DIRECTORY
    return authorization


def _build_manifest(repo_root: Path, *, parent: dict[str, Any]) -> dict[str, Any]:
    manifest = copy.deepcopy(parent)
    manifest["$schema"] = "../schemas/forge-cpp-formal-timeout-canary-amendment.schema.json"
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["benchmark"] = {
        "id": "forge-cpp-formal-timeout-canary-amendment",
        "name": "Forge C/C++ formal timeout calibration canary amendment",
        "purpose": "repair the authenticated canary path without anonymous endpoint probing",
        "dataset_provenance": parent["benchmark"]["dataset_provenance"],
    }
    manifest["scope"] = {
        **copy.deepcopy(parent["scope"]),
        "phase": "formal_timeout_canary_amendment",
    }
    manifest["forge"] = {
        **copy.deepcopy(parent["forge"]),
        "commit_sha": BASELINE_COMMIT,
        "component_sha256": _hasher._hash_paths(repo_root, COMPONENT_PATHS),
    }
    manifest["protocol_artifact_sha256"] = _hasher._hash_paths(repo_root, PROTOCOL_ARTIFACT_PATHS)
    manifest["prompt_sha256"] = _hasher._hash_paths(repo_root, set(parent["prompt_sha256"]))
    manifest["authorization"] = _authorization(parent)
    return manifest


def generate_manifest(repo_root: Path = REPOSITORY_ROOT, *, parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return _build_manifest(repo_root, parent=_parent_manifest(parent))


def selected_slots(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    by_order = {slot["order"]: slot for slot in manifest["collection_plan"]}
    return [by_order[order] for order in AUTHORIZED_SCHEDULE_ORDERS]


def validate_manifest(document: Any, *, repo_root: Path = REPOSITORY_ROOT, parent: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        manifest = v1._as_object(document, "manifest")
        expected = _build_manifest(repo_root, parent=_parent_manifest(parent))
        if manifest != expected:
            v1._fail("manifest", "must match the timeout canary amendment exactly")
        return manifest
    except BenchmarkError:
        raise
    except (AttributeError, KeyError, OSError, TypeError, ValueError) as exc:
        raise BenchmarkError(f"manifest: invalid timeout canary amendment: {exc}") from exc


def canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return canonical_json_bytes(manifest)


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()


def verify_frozen_components(manifest: dict[str, Any], repo_root: Path = REPOSITORY_ROOT) -> None:
    validate_manifest(manifest, repo_root=repo_root)
    for path_prefix, hashes in (
        ("manifest.forge.component_sha256", manifest["forge"]["component_sha256"]),
        ("manifest.protocol_artifact_sha256", manifest["protocol_artifact_sha256"]),
        ("manifest.prompt_sha256", manifest["prompt_sha256"]),
    ):
        for relative_path, expected in hashes.items():
            if _hasher._file_sha256(repo_root / relative_path) != expected:
                v1._fail(f"{path_prefix}.{relative_path}", "does not match")


def _hash_map_schema(paths: set[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "required": sorted(paths),
        "additionalProperties": False,
        "properties": {path: {"type": "string", "pattern": "^[0-9a-f]{64}$"} for path in sorted(paths)},
    }


def schema_document() -> dict[str, Any]:
    schema = copy.deepcopy(parent_protocol.schema_document())
    parent = _parent_manifest()
    expected = _build_manifest(REPOSITORY_ROOT, parent=parent)
    schema["$id"] = "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-cpp-formal-timeout-canary-amendment.schema.json"
    schema["title"] = "Forge C/C++ formal timeout calibration canary amendment"
    properties = schema["properties"]
    properties["$schema"] = {"const": expected["$schema"]}
    properties["schema_version"] = {"const": SCHEMA_VERSION}
    properties["benchmark"] = {"const": expected["benchmark"]}
    properties["scope"] = {"const": expected["scope"]}
    properties["forge"]["properties"]["commit_sha"] = {"const": BASELINE_COMMIT}
    properties["forge"]["properties"]["component_sha256"] = _hash_map_schema(COMPONENT_PATHS)
    properties["protocol_artifact_sha256"] = _hash_map_schema(PROTOCOL_ARTIFACT_PATHS)
    properties["prompt_sha256"] = _hash_map_schema(set(parent["prompt_sha256"]))
    properties["authorization"] = {"const": _authorization(parent)}
    return schema


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    generate.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    validate = subparsers.add_parser("validate-manifest")
    validate.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            _write_json(args.schema, schema_document())
            manifest = generate_manifest()
            _write_json(args.manifest, manifest)
        else:
            manifest = validate_manifest(load_json_document(args.manifest))
            verify_frozen_components(manifest)
        print(json.dumps({"benchmark_id": manifest["benchmark"]["id"], "manifest_sha256": manifest_sha256(manifest), "status": "valid"}, sort_keys=True))
        return 0
    except (BenchmarkError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
