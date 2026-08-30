#!/usr/bin/env python3
"""Issue #188 opaque provenance runtime-parity provider amendment 候选协议。"""

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
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-runtime-parity-provider-amendment-candidate.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-runtime-parity-provider-amendment-candidate.schema.json"
PARENT_MANIFEST_PATH = "benchmarks/manifests/cpp-opaque-provenance-minimal-canary-execution.json"
RUNTIME_ADAPTER_PATH = "scripts/forge_opaque_provenance_provider_amendment_candidate_runner.py"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-opaque-provenance-runtime-parity-provider-amendment-candidate.md"

SCHEMA_VERSION = "forge-opaque-provenance-runtime-parity-provider-amendment-candidate-1.0.0"
DOCUMENT_TYPE = "forge_opaque_provenance_runtime_parity_provider_amendment_candidate"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/188"
AUTHORIZATION_BASELINE_COMMIT = "ad6e7c1143d23eeca0cd8f98dcb76023e6b81626"
PARENT_MANIFEST_SHA256 = "bbb50851419ec8c1e1efb4bc5612cb13e4ab0154df574dc7359009e2fb90529a"
PARENT_EVIDENCE_IDENTITY_SHA256 = "f83fb4a3d228c82839df68905ee603c79095c919fe0cc8ab0c52ce4debaeb538"
HISTORICAL_CANARY_REPORT_SHA256 = "e6ee3e2db68c191e7c4e278071ea14a32e6ef362d82194d07697b0ea24034da0"
PAIR_ID = "opaque-provenance-cppitertools-runtime-parity-pair-01"
EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-runtime-parity-amendment-v1"
EVIDENCE_SCHEMA_VERSION = "forge-opaque-provenance-runtime-parity-amendment-evidence-1.0.0"

FROZEN_PARENT_PATHS = {
    PARENT_MANIFEST_PATH,
    "benchmarks/preregistrations/cpp-opaque-provenance-minimal-canary-execution.md",
    "benchmarks/schemas/forge-opaque-provenance-minimal-canary-execution.schema.json",
    "scripts/forge_opaque_provenance_minimal_canary_execution_protocol.py",
    "scripts/forge_opaque_provenance_minimal_canary_execution_runner.py",
    "benchmarks/preregistrations/cpp-opaque-provenance-runtime-parity-zero-provider-gate.md",
    "scripts/forge_opaque_provenance_runtime_parity_gate.py",
}


class ProtocolError(RuntimeError):
    """候选、父身份、runtime-parity 合同或 evidence identity 发生漂移。"""


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
    path = repo_root / "scripts/forge_opaque_provenance_minimal_canary_execution_protocol.py"
    name = "forge_opaque_provenance_provider_amendment_candidate_parent"
    existing = sys.modules.get(name)
    if existing is not None and Path(existing.__file__).resolve() == path.resolve():
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ProtocolError("cannot load #184 execution protocol")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _parent_manifest(repo_root: Path = REPO_ROOT) -> tuple[dict[str, Any], Any]:
    parent = _load_parent_protocol(repo_root)
    manifest = parent.load_manifest(repo_root / PARENT_MANIFEST_PATH, repo_root)
    if parent.canonical_sha256(manifest) != PARENT_MANIFEST_SHA256:
        raise ProtocolError("#184 execution manifest identity drifted")
    if manifest["evidence"]["identity_sha256"] != PARENT_EVIDENCE_IDENTITY_SHA256:
        raise ProtocolError("#184 evidence identity drifted")
    return manifest, parent


def _hash_paths(repo_root: Path, paths: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative_path in sorted(paths):
        path = repo_root / relative_path
        if not path.is_file():
            raise ProtocolError(f"frozen component missing: {relative_path}")
        result[relative_path] = file_sha256(path)
    return result


def _evidence_identity() -> dict[str, Any]:
    identity = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "directory": EVIDENCE_DIRECTORY,
        "preflight_snapshot": "preflight/preflight.json",
        "reachability_marker": "markers/reachability.json",
        "pair_marker": "markers/pair.json",
        "pair_ledger": f"pairs/{PAIR_ID}/events.jsonl",
        "arm_ledger_directory": f"pairs/{PAIR_ID}/arms",
        "reachability_report": "reports/reachability.json",
        "canary_report": "reports/canary.json",
        "append_only": True,
        "marker_consumed_on_start": True,
        "zero_provider_preflight_writes_evidence": False,
    }
    return {**identity, "identity_sha256": canonical_sha256(identity)}


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    parent_manifest, parent = _parent_manifest(repo_root)
    runtime_path = repo_root / RUNTIME_ADAPTER_PATH
    preregistration_path = repo_root / PREREGISTRATION_PATH
    if not runtime_path.is_file():
        raise ProtocolError(f"runtime adapter missing: {RUNTIME_ADAPTER_PATH}")
    if not preregistration_path.is_file():
        raise ProtocolError(f"preregistration missing: {PREREGISTRATION_PATH}")
    provider = copy.deepcopy(parent_manifest["provider"])
    provider["status"] = "candidate_not_authorized"
    schedule = [
        {
            "pair_id": PAIR_ID,
            "order": 1,
            "case_id": parent_manifest["case"]["case_id"],
            "arm_order": ["baseline", "treatment"],
            "treatment_exposure_only": "repair_packet",
            "shared_measurement_policy": "runtime_parity_v1",
            "historical_pair_relationship": "independent_amendment_not_retry_replacement_backfill_or_extension",
        }
    ]
    return {
        "$schema": "../schemas/forge-opaque-provenance-runtime-parity-provider-amendment-candidate.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "authorization": {
            "issue_url": ISSUE_URL,
            "candidate_generation_authorized": True,
            "zero_provider_preflight_authorized": True,
            "reachability_request_authorized": False,
            "provider_calls_authorized": False,
            "formal_attempts_authorized": False,
            "canary_collection_authorized": False,
            "credential_read_authorized": False,
            "model_tokens_authorized": 0,
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
        "historical_evidence": {
            "directory": parent_manifest["evidence"]["directory"],
            "canary_report": parent_manifest["evidence"]["canary_report"],
            "canary_report_sha256": HISTORICAL_CANARY_REPORT_SHA256,
            "immutable": True,
            "reuse_forbidden": True,
        },
        "case": copy.deepcopy(parent_manifest["case"]),
        "provider": provider,
        "continuation": copy.deepcopy(parent_manifest["continuation"]),
        "schedule": schedule,
        "schedule_sha256": canonical_sha256(schedule),
        "budget": copy.deepcopy(parent_manifest["budget"]),
        "stopping": copy.deepcopy(parent_manifest["stopping"]),
        "analysis": {
            "purpose": "intervention_delivery_and_conversion_canary_only",
            "unit_of_analysis": "single_independent_runtime_parity_checkpoint_pair",
            "descriptive_only": True,
            "treatment_effect_estimated": False,
            "p_value_computed": False,
            "model_ranking_performed": False,
            "historical_pairs_pooled": False,
            "historical_pair_replacement": False,
        },
        "runtime_parity": {
            "measurement_classification": "measurement_policy_censored",
            "intervention_classification": "intervention_delivery_failure",
            "parent_submit_uses_bound_wrapper": True,
            "fence_released_before_capture": True,
            "action_limits": {"inspection": 4, "repair_build": 2, "artifact_stage": 2, "submit": 2},
            "atomic_budget_claim": True,
            "parallel_tool_calls": False,
            "repair_build_directory": parent_manifest["case"]["build_directory"],
            "repair_build_target": parent_manifest["case"]["target"],
            "staged_artifact": parent_manifest["case"]["staged_artifact"],
            "forbidden_actions": ["clone", "configure", "dependency", "housekeeping", "manual_replay", "compound_build_stage"],
            "candidate_verification_required": True,
            "clean_replay_required": True,
            "cleanup_required": True,
        },
        "evidence": _evidence_identity(),
        "opportunities": {
            "maximum_reachability_requests": 1,
            "maximum_canary_pairs": 1,
            "required_order": ["reachability", PAIR_ID],
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
            "allowed_network_media": ["wired", "wifi", "mobile_hotspot"],
            "require_empty_candidate_evidence_directory": True,
            "require_historical_canary_report_hash": True,
            "managed_container_prefixes": ["deerflow-compile-", "deerflow-replay-"],
            "require_zero_managed_orphans": True,
        },
        "preregistration": {
            "path": PREREGISTRATION_PATH,
            "file_sha256": file_sha256(preregistration_path),
        },
        "runtime_adapter": {
            "path": RUNTIME_ADAPTER_PATH,
            "file_sha256": file_sha256(runtime_path),
            "commands": ["validate", "plan", "preflight"],
            "credential_read_supported": False,
            "provider_model_creation_supported": False,
            "reachability_execute_supported": False,
            "pair_execute_supported": False,
        },
        "frozen_parent_components": _hash_paths(repo_root, FROZEN_PARENT_PATHS),
    }


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError("manifest must be an object")
    if value != generate_manifest(repo_root):
        raise ProtocolError("runtime-parity provider amendment candidate manifest drifted")
    budget = value["budget"]
    if budget["recorded_tokens_per_pair"] + budget["reachability_maximum_recorded_tokens"] != budget["stage_maximum_recorded_tokens"]:
        raise ProtocolError("stage token budget is not closed")
    if value["runtime_parity"]["action_limits"] != {"inspection": 4, "repair_build": 2, "artifact_stage": 2, "submit": 2}:
        raise ProtocolError("runtime-parity action limits drifted")
    return value


def load_manifest(path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError("cannot read runtime-parity provider amendment candidate manifest") from exc
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
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-opaque-provenance-runtime-parity-provider-amendment-candidate.schema.json",
        "title": "Forge opaque provenance runtime-parity provider amendment candidate",
        "const": frozen,
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


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
        verify_frozen_components(manifest)
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
