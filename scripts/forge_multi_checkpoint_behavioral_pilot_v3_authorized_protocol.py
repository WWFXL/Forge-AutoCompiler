#!/usr/bin/env python3
"""Issue #172 多 checkpoint behavioral pilot v3 授权采集协议。"""

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
PARENT_MANIFEST_PATH = "benchmarks/manifests/cpp-verifier-multi-checkpoint-behavioral-pilot-v3.json"
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-verifier-multi-checkpoint-behavioral-pilot-v3-authorized.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-multi-checkpoint-behavioral-pilot-v3-authorized.schema.json"
EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-multi-checkpoint-behavioral-pilot-v3-authorized"
DEFAULT_OUTPUT_DIR = Path(EVIDENCE_DIRECTORY)

SCHEMA_VERSION = "forge-multi-checkpoint-behavioral-pilot-3.1.0-authorized"
DOCUMENT_TYPE = "forge_multi_checkpoint_behavioral_pilot_authorized"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/172"
AUTHORIZATION_BASELINE = "4cd3b900bf23facd71c1e1905ff8de040ac598b6"
PARENT_COMPONENT_PATHS = {
    PARENT_MANIFEST_PATH,
    "benchmarks/schemas/forge-multi-checkpoint-behavioral-pilot-v3.schema.json",
    "scripts/forge_multi_checkpoint_behavioral_pilot_v3_protocol.py",
    "scripts/forge_multi_checkpoint_behavioral_pilot_v3_runner.py",
}


class ProtocolError(RuntimeError):
    """授权协议、父协议或预算 identity 无效。"""


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
    path = repo_root / "scripts/forge_multi_checkpoint_behavioral_pilot_v3_protocol.py"
    name = "forge_multi_checkpoint_behavioral_pilot_v3_authorized_parent"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ProtocolError("cannot load frozen v3 parent protocol")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"cannot read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ProtocolError(f"JSON root must be an object: {path}")
    return value


def _hash_paths(repo_root: Path, paths: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative_path in sorted(paths):
        path = repo_root / relative_path
        if not path.is_file():
            raise ProtocolError(f"parent component missing: {relative_path}")
        result[relative_path] = file_sha256(path)
    return result


def parent_manifest(repo_root: Path = REPO_ROOT) -> tuple[dict[str, Any], Any]:
    parent = _load_parent_protocol(repo_root)
    manifest = parent.validate_manifest(_load_json(repo_root / PARENT_MANIFEST_PATH), repo_root)
    parent.verify_frozen_components(manifest, repo_root)
    return manifest, parent


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    parent_value, parent = parent_manifest(repo_root)
    value = copy.deepcopy(parent_value)
    value["$schema"] = "../schemas/forge-multi-checkpoint-behavioral-pilot-v3-authorized.schema.json"
    value["schema_version"] = SCHEMA_VERSION
    value["document_type"] = DOCUMENT_TYPE
    value["authorization"] = {
        "issue_url": ISSUE_URL,
        "authorized_by": "experiment_owner",
        "provider_calls_authorized": True,
        "formal_attempts_authorized": True,
        "model_tokens_authorized": 1_440_000,
        "pilot_collection_authorized": True,
        "authorized_provider_canaries": 1,
        "authorized_pairs": 6,
    }
    value["canary"] = {
        "prompt": "Reply with exactly CANARY_OK and nothing else.",
        "expected_response": "CANARY_OK",
        "maximum_requests": 1,
        "maximum_recorded_tokens": 5_000,
        "success_required_before_first_pair": True,
        "retry_forbidden": True,
    }
    value["execution"].update(
        {
            "mode": "authorized_collection",
            "network_access_medium_env": "FORGE_NETWORK_ACCESS_MEDIUM",
            "network_access_medium": "wifi",
            "evidence_directory": EVIDENCE_DIRECTORY,
            "canary_marker": "markers/provider-canary-attempt.json",
            "batch_marker": "markers/pilot-attempt.json",
            "pair_marker": "markers/pair-attempt.json",
            "authorization_baseline_commit": AUTHORIZATION_BASELINE,
        }
    )
    value["parent_protocol"] = {
        "manifest_path": PARENT_MANIFEST_PATH,
        "schema_version": parent_value["schema_version"],
        "canonical_sha256": parent.canonical_sha256(parent_value),
        "file_sha256": file_sha256(repo_root / PARENT_MANIFEST_PATH),
        "components": _hash_paths(repo_root, PARENT_COMPONENT_PATHS),
    }
    value.pop("frozen_components")
    return value


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if not isinstance(value, dict) or value != generate_manifest(repo_root):
        raise ProtocolError("authorized multi-checkpoint behavioral v3 manifest drifted")
    if value["budget"]["stage_maximum_recorded_tokens"] != value["authorization"]["model_tokens_authorized"]:
        raise ProtocolError("authorized token ceiling does not match the frozen stage budget")
    return value


def verify_frozen_components(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> None:
    validate_manifest(manifest, repo_root)
    parent_value, parent = parent_manifest(repo_root)
    if manifest["parent_protocol"] != {
        "manifest_path": PARENT_MANIFEST_PATH,
        "schema_version": parent_value["schema_version"],
        "canonical_sha256": parent.canonical_sha256(parent_value),
        "file_sha256": file_sha256(repo_root / PARENT_MANIFEST_PATH),
        "components": _hash_paths(repo_root, PARENT_COMPONENT_PATHS),
    }:
        raise ProtocolError("frozen parent protocol drifted")


def load_manifest(path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    return validate_manifest(_load_json(path), repo_root)


def case_definitions(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    validate_manifest(manifest, repo_root)
    _parent_value, parent = parent_manifest(repo_root)
    return parent.case_definitions(_parent_value, repo_root)


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    frozen = manifest or generate_manifest()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-multi-checkpoint-behavioral-pilot-v3-authorized.schema.json",
        "title": "Forge authorized multi-checkpoint behavioral pilot v3",
        "const": frozen,
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
                "provider_canaries": manifest["authorization"]["authorized_provider_canaries"],
                "pairs": manifest["authorization"]["authorized_pairs"],
                "maximum_recorded_tokens": manifest["authorization"]["model_tokens_authorized"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
