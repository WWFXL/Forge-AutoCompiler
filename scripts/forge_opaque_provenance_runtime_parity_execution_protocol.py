#!/usr/bin/env python3
"""Issue #190 opaque provenance runtime-parity 一次性 execution amendment。"""

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
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-runtime-parity-execution.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-runtime-parity-execution.schema.json"
PARENT_MANIFEST_PATH = "benchmarks/manifests/cpp-opaque-provenance-runtime-parity-provider-amendment-candidate.json"
RUNTIME_ADAPTER_PATH = "scripts/forge_opaque_provenance_runtime_parity_execution_runner.py"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-opaque-provenance-runtime-parity-execution.md"

SCHEMA_VERSION = "forge-opaque-provenance-runtime-parity-execution-1.0.0"
DOCUMENT_TYPE = "forge_opaque_provenance_runtime_parity_execution_amendment"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/190"
AUTHORIZATION_BASELINE_COMMIT = "1ba74646932249945aebb209f2d1ceff7356ca15"
PARENT_MANIFEST_SHA256 = "27b161720d3ab1208d6792e59df4509a611c3967645787a083b0fb9bdc6bdcb2"
PARENT_EVIDENCE_IDENTITY_SHA256 = "ce7e4277bcedab8b203ebe51863877b2d3f958e838ed7dcc960a47f23981c25a"

FROZEN_PARENT_PATHS = {
    PARENT_MANIFEST_PATH,
    "benchmarks/preregistrations/cpp-opaque-provenance-runtime-parity-provider-amendment-candidate.md",
    "benchmarks/schemas/forge-opaque-provenance-runtime-parity-provider-amendment-candidate.schema.json",
    "scripts/forge_opaque_provenance_provider_amendment_candidate_protocol.py",
    "scripts/forge_opaque_provenance_provider_amendment_candidate_runner.py",
    "scripts/forge_opaque_provenance_minimal_canary_execution_runner.py",
    "scripts/forge_opaque_provenance_runtime_parity_gate.py",
}


class ProtocolError(RuntimeError):
    """Execution amendment、父身份或预算发生漂移。"""


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
    path = repo_root / "scripts/forge_opaque_provenance_provider_amendment_candidate_protocol.py"
    name = "forge_opaque_provenance_runtime_parity_execution_parent"
    existing = sys.modules.get(name)
    if existing is not None and Path(existing.__file__).resolve() == path.resolve():
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ProtocolError("cannot load runtime-parity amendment candidate")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _parent_manifest(repo_root: Path = REPO_ROOT) -> tuple[dict[str, Any], Any]:
    parent = _load_parent_protocol(repo_root)
    manifest = parent.load_manifest(repo_root / PARENT_MANIFEST_PATH, repo_root)
    if parent.canonical_sha256(manifest) != PARENT_MANIFEST_SHA256:
        raise ProtocolError("runtime-parity candidate manifest identity drifted")
    if manifest["evidence"]["identity_sha256"] != PARENT_EVIDENCE_IDENTITY_SHA256:
        raise ProtocolError("runtime-parity candidate evidence identity drifted")
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
    return {
        "$schema": "../schemas/forge-opaque-provenance-runtime-parity-execution.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "authorization": {
            "issue_url": ISSUE_URL,
            "reachability_request_authorized": True,
            "provider_calls_authorized": True,
            "formal_attempts_authorized": True,
            "canary_collection_authorized": True,
            "credential_read_authorized": True,
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
        "historical_evidence": copy.deepcopy(parent_manifest["historical_evidence"]),
        "case": copy.deepcopy(parent_manifest["case"]),
        "provider": provider,
        "continuation": copy.deepcopy(parent_manifest["continuation"]),
        "schedule": copy.deepcopy(parent_manifest["schedule"]),
        "schedule_sha256": parent_manifest["schedule_sha256"],
        "budget": copy.deepcopy(parent_manifest["budget"]),
        "stopping": copy.deepcopy(parent_manifest["stopping"]),
        "analysis": copy.deepcopy(parent_manifest["analysis"]),
        "runtime_parity": copy.deepcopy(parent_manifest["runtime_parity"]),
        "evidence": copy.deepcopy(parent_manifest["evidence"]),
        "opportunities": copy.deepcopy(parent_manifest["opportunities"]),
        "preflight": copy.deepcopy(parent_manifest["preflight"]),
        "execution": {
            "release_branch": "main",
            "network_access_medium_env": "FORGE_NETWORK_ACCESS_MEDIUM",
            "reachability_prompt": "Reply with exactly CANARY_OK and nothing else.",
            "reachability_expected_response": "CANARY_OK",
            "reachability_report": parent_manifest["evidence"]["reachability_report"],
            "pair_marker": parent_manifest["evidence"]["pair_marker"],
            "parent_ledger": parent_manifest["evidence"]["pair_ledger"],
            "arm_ledger_directory": parent_manifest["evidence"]["arm_ledger_directory"],
            "report_schema_version": "forge-opaque-provenance-runtime-parity-report-1.0.0",
            "report_document_type": "forge_opaque_provenance_runtime_parity_report",
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
            "reachability_execute_supported": True,
            "pair_execute_supported": True,
        },
        "frozen_parent_components": _hash_paths(repo_root, FROZEN_PARENT_PATHS),
    }


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError("manifest must be an object")
    if value != generate_manifest(repo_root):
        raise ProtocolError("runtime-parity execution amendment manifest drifted")
    budget = value["budget"]
    if budget["recorded_tokens_per_pair"] + budget["reachability_maximum_recorded_tokens"] != budget["stage_maximum_recorded_tokens"]:
        raise ProtocolError("stage token budget is not closed")
    if value["runtime_parity"]["parallel_tool_calls"] is not False:
        raise ProtocolError("parallel tool calls must remain disabled")
    return value


def load_manifest(path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError("cannot read runtime-parity execution manifest") from exc
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
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-opaque-provenance-runtime-parity-execution.schema.json",
        "title": "Forge opaque provenance runtime-parity execution amendment",
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
