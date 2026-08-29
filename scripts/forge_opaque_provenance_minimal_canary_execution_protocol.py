#!/usr/bin/env python3
"""Issue #184 opaque provenance 最小 canary 一次性执行 amendment。"""

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
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-minimal-canary-execution.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-minimal-canary-execution.schema.json"
PARENT_MANIFEST_PATH = "benchmarks/manifests/cpp-opaque-provenance-minimal-canary-authorized.json"
RUNTIME_ADAPTER_PATH = "scripts/forge_opaque_provenance_minimal_canary_execution_runner.py"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-opaque-provenance-minimal-canary-execution.md"

SCHEMA_VERSION = "forge-opaque-provenance-minimal-canary-execution-1.0.0"
DOCUMENT_TYPE = "forge_opaque_provenance_minimal_canary_execution_amendment"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/184"
AUTHORIZATION_BASELINE_COMMIT = "323430f1fb3f3fb7ac09c6ea1aefa801298e5619"
PARENT_MANIFEST_SHA256 = "00ce7eaadda3e89b63d093f4e360473fe372850dd39290d69e1a4a7e675e7771"
PARENT_EVIDENCE_IDENTITY_SHA256 = "f83fb4a3d228c82839df68905ee603c79095c919fe0cc8ab0c52ce4debaeb538"

FROZEN_PARENT_PATHS = {
    PARENT_MANIFEST_PATH,
    "benchmarks/preregistrations/cpp-opaque-provenance-minimal-canary-authorized.md",
    "benchmarks/schemas/forge-opaque-provenance-minimal-canary-authorized.schema.json",
    "scripts/forge_opaque_provenance_minimal_canary_authorized_protocol.py",
    "scripts/forge_opaque_provenance_minimal_canary_authorized_runner.py",
    "scripts/forge_opaque_build_provenance_real_docker_gate.py",
    "scripts/forge_multi_checkpoint_behavioral_pilot_v3_authorized_runner.py",
}


class ProtocolError(RuntimeError):
    """执行 amendment、父身份或预算发生漂移。"""


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
    path = repo_root / "scripts/forge_opaque_provenance_minimal_canary_authorized_protocol.py"
    name = "forge_opaque_provenance_minimal_canary_execution_parent"
    existing = sys.modules.get(name)
    if existing is not None and Path(existing.__file__).resolve() == path.resolve():
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ProtocolError("cannot load authorized candidate protocol")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _parent_manifest(repo_root: Path = REPO_ROOT) -> tuple[dict[str, Any], Any]:
    parent = _load_parent_protocol(repo_root)
    manifest = parent.load_manifest(repo_root / PARENT_MANIFEST_PATH, repo_root)
    if parent.canonical_sha256(manifest) != PARENT_MANIFEST_SHA256:
        raise ProtocolError("authorized candidate manifest identity drifted")
    if manifest["evidence"]["identity_sha256"] != PARENT_EVIDENCE_IDENTITY_SHA256:
        raise ProtocolError("authorized evidence identity drifted")
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
    if not runtime_path.is_file():
        raise ProtocolError(f"runtime adapter missing: {RUNTIME_ADAPTER_PATH}")
    provider = copy.deepcopy(parent_manifest["provider"])
    provider["status"] = "active_authorized"
    return {
        "$schema": "../schemas/forge-opaque-provenance-minimal-canary-execution.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "authorization": {
            "issue_url": ISSUE_URL,
            "reachability_request_authorized": True,
            "provider_calls_authorized": True,
            "formal_attempts_authorized": True,
            "canary_collection_authorized": True,
            "model_tokens_authorized": parent_manifest["budget"]["stage_maximum_recorded_tokens"],
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
        "provider": provider,
        "continuation": copy.deepcopy(parent_manifest["continuation"]),
        "schedule": copy.deepcopy(parent_manifest["schedule"]),
        "schedule_sha256": parent_manifest["schedule_sha256"],
        "budget": copy.deepcopy(parent_manifest["budget"]),
        "stopping": copy.deepcopy(parent_manifest["stopping"]),
        "analysis": copy.deepcopy(parent_manifest["analysis"]),
        "evidence": copy.deepcopy(parent_manifest["evidence"]),
        "opportunities": copy.deepcopy(parent_manifest["opportunities"]),
        "preflight": copy.deepcopy(parent_manifest["preflight"]),
        "execution": {
            "release_branch": "main",
            "network_access_medium_env": "FORGE_NETWORK_ACCESS_MEDIUM",
            "reachability_prompt": "Reply with exactly CANARY_OK and nothing else.",
            "reachability_expected_response": "CANARY_OK",
            "reachability_report": "reports/reachability.json",
            "pair_marker": "markers/pair.json",
            "parent_ledger": parent_manifest["evidence"]["pair_ledger"],
            "arm_ledger_directory": f"pairs/{parent_manifest['schedule'][0]['pair_id']}/arms",
        },
        "preregistration": {
            "path": PREREGISTRATION_PATH,
            "file_sha256": file_sha256(repo_root / PREREGISTRATION_PATH),
        },
        "runtime_adapter": {
            "path": RUNTIME_ADAPTER_PATH,
            "file_sha256": file_sha256(runtime_path),
            "commands": ["validate", "preflight", "reachability", "pair"],
            "credential_read_supported": True,
            "provider_model_creation_supported": True,
            "reachability_execute_supported": True,
            "canary_execute_supported": True,
        },
        "frozen_parent_components": _hash_paths(repo_root, FROZEN_PARENT_PATHS),
    }


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError("manifest must be an object")
    if value != generate_manifest(repo_root):
        raise ProtocolError("opaque provenance execution amendment manifest drifted")
    budget = value["budget"]
    if budget["recorded_tokens_per_pair"] + budget["reachability_maximum_recorded_tokens"] != budget["stage_maximum_recorded_tokens"]:
        raise ProtocolError("stage token budget is not closed")
    return value


def load_manifest(path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError("cannot read opaque provenance execution manifest") from exc
    return validate_manifest(value, repo_root)


def verify_frozen_components(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> None:
    validate_manifest(manifest, repo_root)
    if manifest["frozen_parent_components"] != _hash_paths(repo_root, FROZEN_PARENT_PATHS):
        raise ProtocolError("frozen parent components drifted")
    runtime = repo_root / manifest["runtime_adapter"]["path"]
    if file_sha256(runtime) != manifest["runtime_adapter"]["file_sha256"]:
        raise ProtocolError("runtime adapter drifted")
    preregistration = repo_root / manifest["preregistration"]["path"]
    if file_sha256(preregistration) != manifest["preregistration"]["file_sha256"]:
        raise ProtocolError("preregistration drifted")


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    frozen = manifest or generate_manifest()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-opaque-provenance-minimal-canary-execution.schema.json",
        "title": "Forge opaque provenance minimal canary execution amendment",
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
        verify_frozen_components(manifest)
    print(json.dumps({"manifest_sha256": canonical_sha256(manifest), "provider_calls": 0, "formal_attempts": 0, "model_tokens": 0}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
