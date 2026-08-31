#!/usr/bin/env python3
"""Issue #243 opaque provenance 独立 replication 的未授权候选协议。"""

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

SCHEMA_VERSION = "forge-opaque-provenance-confirmatory-replication-candidate-1.0.0"
DOCUMENT_TYPE = "forge_opaque_provenance_confirmatory_replication_candidate"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/243"
BASELINE_COMMIT = "c38f73816be706f7e8ef7115422bb9878d675493"
PARENT_MANIFEST_PATH = "benchmarks/manifests/cpp-opaque-provenance-confirmatory-execution-authorized.json"
PARENT_MANIFEST_CANONICAL_SHA256 = "68349316cfdbe8411c49c7ffc9491760bf19fb10e0583f40a47dd0c91ea31e78"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-opaque-provenance-confirmatory-replication-candidate.md"
RUNTIME_PATH = "scripts/forge_opaque_provenance_confirmatory_execution_repair_adapter.py"
EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-confirmatory-replication-v1"
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-confirmatory-replication-candidate.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-confirmatory-replication-candidate.schema.json"

FROZEN_DECISION_COMPONENTS = {
    PARENT_MANIFEST_PATH: "134b01b07843b9c3fe31075d2a5340c5203ef277ec6c797fac5e975974da53eb",
    "benchmarks/fixtures/opaque-provenance-confirmatory-v1-evidence-inventory.json": "e7581a24f589b474899759fba019385888fe4c15519d3cd5d98f1dd14feb63cb",
    "benchmarks/preregistrations/cpp-opaque-provenance-confirmatory-v1-recovery-decision.md": "1af127ee2303b0f60a5fad13c8e6a9b9be1d1fc466c1880978cf688f48d2b4d3",
    RUNTIME_PATH: "c8a13388f6c53d308b34f013bf4a9f449190a10e779667cdf73b0e8ef1da2544",
}
V1_INVENTORY_ENTRIES_SHA256 = "dc7e53020af27929ea334376628c37f02236ae5510166c07109a1ddde7f5f431"


class ReplicationCandidateError(RuntimeError):
    """独立 replication identity、父尝试或授权边界发生漂移。"""


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
    path = repo_root / "scripts/forge_opaque_provenance_confirmatory_execution_authorized_protocol.py"
    name = "forge_confirmatory_replication_candidate_parent"
    existing = sys.modules.get(name)
    if existing is not None and Path(existing.__file__).resolve() == path.resolve():
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ReplicationCandidateError("无法加载 confirmatory v1 authorized protocol")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _parent_manifest(repo_root: Path = REPO_ROOT) -> tuple[dict[str, Any], Any]:
    parent_protocol = _load_parent_protocol(repo_root)
    try:
        value = json.loads((repo_root / PARENT_MANIFEST_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplicationCandidateError("无法读取 confirmatory v1 authorized manifest") from exc
    manifest = parent_protocol.validate_manifest(value, repo_root)
    if parent_protocol.canonical_sha256(manifest) != PARENT_MANIFEST_CANONICAL_SHA256:
        raise ReplicationCandidateError("confirmatory v1 canonical identity 发生漂移")
    return manifest, parent_protocol


def _verify_decision_components(repo_root: Path) -> None:
    for relative, expected in FROZEN_DECISION_COMPONENTS.items():
        if file_sha256(repo_root / relative) != expected:
            raise ReplicationCandidateError(f"recovery decision component 发生漂移: {relative}")
    inventory = json.loads((repo_root / "benchmarks/fixtures/opaque-provenance-confirmatory-v1-evidence-inventory.json").read_text(encoding="utf-8"))
    if inventory.get("entries_sha256") != V1_INVENTORY_ENTRIES_SHA256:
        raise ReplicationCandidateError("v1 evidence inventory identity 发生漂移")


def _evidence_identity(parent: dict[str, Any]) -> str:
    return canonical_sha256(
        {
            "issue_url": ISSUE_URL,
            "baseline_commit": BASELINE_COMMIT,
            "parent_manifest_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
            "v1_inventory_entries_sha256": V1_INVENTORY_ENTRIES_SHA256,
            "schedule_identity_sha256": parent["schedule"]["identity_sha256"],
            "runtime_file_sha256": FROZEN_DECISION_COMPONENTS[RUNTIME_PATH],
            "directory": EVIDENCE_DIRECTORY,
            "historical_outcomes_imported": False,
        }
    )


def _replication_candidate(parent: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    preregistration = repo_root / PREREGISTRATION_PATH
    if not preregistration.is_file():
        raise ReplicationCandidateError("replication candidate 预注册不存在")
    provider = copy.deepcopy(parent["authorized_execution"]["provider"])
    provider["status"] = "selected_not_authorized"
    return {
        "issue_url": ISSUE_URL,
        "status": "candidate_not_authorized",
        "baseline_commit": BASELINE_COMMIT,
        "relationship_to_v1": {
            "parent_manifest_path": PARENT_MANIFEST_PATH,
            "parent_manifest_canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
            "v1_inventory_entries_sha256": V1_INVENTORY_ENTRIES_SHA256,
            "v1_attempt_status": "failed_mechanism_attempt_closed",
            "historical_outcomes_imported": False,
            "v1_attempt_extended": False,
            "replacement": False,
            "backfill": False,
            "gpac_provider_opportunity_consumed": False,
            "gpac_v1_attempt_resumed": False,
        },
        "provider_candidate": provider,
        "budget_candidate": {
            **copy.deepcopy(parent["authorized_execution"]["budget"]),
            "authorized": False,
        },
        "evidence_candidate": {
            **copy.deepcopy(parent["authorized_execution"]["evidence"]),
            "directory": EVIDENCE_DIRECTORY,
            "identity_sha256": _evidence_identity(parent),
            "historical_evidence_reused": False,
            "historical_outcomes_imported": False,
            "writes_authorized": False,
        },
        "runtime_candidate": {
            "pair_executor_adapter": RUNTIME_PATH,
            "entrypoint": "execute_real_pair",
            "runtime_file_sha256": FROZEN_DECISION_COMPONENTS[RUNTIME_PATH],
            "frozen_v1_runner_modified": False,
            "capture_before_commit_cleanup_required": True,
            "broad_docker_cleanup_forbidden": True,
        },
        "preflight_candidate": {
            **copy.deepcopy(parent["authorized_execution"]["preflight"]),
            "require_baseline_commit_ancestor": True,
            "require_empty_replication_evidence_directory": True,
            "require_v1_inventory_match": True,
        },
        "analysis": {
            "unit": "project_block",
            "replicates_per_project": 2,
            "primary_test": "two_sided_exact_sign_flip",
            "historical_outcomes_imported": False,
            "historical_exploratory_pairs_pooled": False,
            "model_ranking_performed": False,
        },
        "preregistration": {
            "path": PREREGISTRATION_PATH,
            "file_sha256": file_sha256(preregistration),
        },
    }


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    _verify_decision_components(repo_root)
    parent, _parent_protocol = _parent_manifest(repo_root)
    value = copy.deepcopy(parent)
    value.pop("authorized_execution")
    value["$schema"] = "../schemas/forge-opaque-provenance-confirmatory-replication-candidate.schema.json"
    value["schema_version"] = SCHEMA_VERSION
    value["document_type"] = DOCUMENT_TYPE
    value["runtime_contract"]["provider_identity_status"] = "selected_not_authorized"
    value["authorization"] = {
        "provider_calls_authorized": False,
        "credential_read_authorized": False,
        "model_creation_authorized": False,
        "reachability_request_authorized": False,
        "checkpoint_creation_authorized": False,
        "pair_collection_authorized": False,
        "formal_attempts_authorized": False,
        "docker_execution_authorized": False,
        "evidence_write_authorized": False,
        "model_tokens_authorized": 0,
    }
    value["future_state"] = {
        "checkpoint_status": "candidate_not_created",
        "evidence_status": "candidate_not_created",
        "execution_runner_status": "candidate_not_authorized",
        "execution_requires_new_amendment": True,
    }
    value["replication_candidate"] = _replication_candidate(parent, repo_root)
    value["frozen_decision_components"] = copy.deepcopy(FROZEN_DECISION_COMPONENTS)
    value["preregistration"] = copy.deepcopy(value["replication_candidate"]["preregistration"])
    return value


def validate_allowed_delta(value: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    parent, _parent_protocol = _parent_manifest(repo_root)
    normalized = copy.deepcopy(value)
    candidate = normalized.pop("replication_candidate", None)
    frozen = normalized.pop("frozen_decision_components", None)
    normalized["authorized_execution"] = copy.deepcopy(parent["authorized_execution"])
    normalized["$schema"] = parent["$schema"]
    normalized["schema_version"] = parent["schema_version"]
    normalized["document_type"] = parent["document_type"]
    normalized["runtime_contract"] = copy.deepcopy(parent["runtime_contract"])
    normalized["authorization"] = copy.deepcopy(parent["authorization"])
    normalized["future_state"] = copy.deepcopy(parent["future_state"])
    normalized["preregistration"] = copy.deepcopy(parent["preregistration"])
    if normalized != parent:
        raise ReplicationCandidateError("replication candidate 包含未声明的父协议差异")
    if candidate != _replication_candidate(parent, repo_root):
        raise ReplicationCandidateError("replication candidate identity 发生漂移")
    if frozen != FROZEN_DECISION_COMPONENTS:
        raise ReplicationCandidateError("frozen decision components 发生漂移")
    relationship = candidate["relationship_to_v1"]
    if any(
        relationship[field]
        for field in (
            "historical_outcomes_imported",
            "v1_attempt_extended",
            "replacement",
            "backfill",
            "gpac_v1_attempt_resumed",
        )
    ):
        raise ReplicationCandidateError("candidate 意外导入或延长了 v1")
    return {
        "status": "passed",
        "schedule_identity_sha256": parent["schedule"]["identity_sha256"],
        "evidence_identity_sha256": candidate["evidence_candidate"]["identity_sha256"],
        "historical_outcomes_imported": False,
        "v1_attempt_extended": False,
        "verifier_relaxation": False,
    }


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    expected = generate_manifest(repo_root)
    if not isinstance(value, dict) or value != expected:
        raise ReplicationCandidateError("confirmatory replication candidate manifest 发生漂移")
    validate_allowed_delta(value, repo_root)
    authorization = value["authorization"]
    if any(item for key, item in authorization.items() if key.endswith("_authorized")):
        raise ReplicationCandidateError("candidate 意外授权了外部执行")
    if authorization["model_tokens_authorized"] != 0:
        raise ReplicationCandidateError("candidate 意外授权了 model token")
    parent, _parent_protocol = _parent_manifest(repo_root)
    if value["replication_candidate"]["evidence_candidate"]["directory"] == parent["authorized_execution"]["evidence"]["directory"]:
        raise ReplicationCandidateError("replication candidate 复用了 v1 evidence directory")
    return value


def verify_frozen_components(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> None:
    _verify_decision_components(repo_root)
    if manifest["frozen_decision_components"] != FROZEN_DECISION_COMPONENTS:
        raise ReplicationCandidateError("manifest 冻结组件 identity 发生漂移")
    runtime = manifest["replication_candidate"]["runtime_candidate"]
    if file_sha256(repo_root / runtime["pair_executor_adapter"]) != runtime["runtime_file_sha256"]:
        raise ReplicationCandidateError("repair adapter runtime 发生漂移")


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    frozen = manifest or generate_manifest()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-opaque-provenance-confirmatory-replication-candidate.schema.json",
        "title": "Forge opaque provenance confirmatory independent replication candidate",
        "const": frozen,
    }


def validate_static_gate(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    manifest = generate_manifest(repo_root)
    delta = validate_allowed_delta(manifest, repo_root)
    return {
        "status": "passed",
        "manifest_sha256": canonical_sha256(manifest),
        "allowed_delta": delta,
        "case_count": len(manifest["cases"]),
        "pair_count": len(manifest["schedule"]["pairs"]),
        "provider_calls": 0,
        "credential_read": False,
        "docker_executed": False,
        "checkpoint_created": False,
        "formal_attempts": 0,
        "model_tokens": 0,
        "evidence_writes": 0,
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
    parser.add_argument("--write", action="store_true", help="确定性写入 candidate manifest 与 const schema")
    args = parser.parse_args(argv)
    manifest = generate_manifest()
    schema = schema_document(manifest)
    if args.write:
        _write_json(DEFAULT_MANIFEST, manifest)
        _write_json(DEFAULT_SCHEMA, schema)
    else:
        validate_manifest(json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8")))
        if json.loads(DEFAULT_SCHEMA.read_text(encoding="utf-8")) != schema:
            raise ReplicationCandidateError("replication candidate const schema 发生漂移")
    print(json.dumps(validate_static_gate(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
