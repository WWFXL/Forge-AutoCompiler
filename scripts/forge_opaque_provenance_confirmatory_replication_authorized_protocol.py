#!/usr/bin/env python3
"""Issue #247 opaque provenance independent replication 授权协议。"""

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
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "benchmarks/manifests/cpp-opaque-provenance-confirmatory-replication-authorized.json"
)
DEFAULT_SCHEMA = (
    REPO_ROOT
    / "benchmarks/schemas/forge-opaque-provenance-confirmatory-replication-authorized.schema.json"
)
PARENT_MANIFEST_PATH = (
    "benchmarks/manifests/cpp-opaque-provenance-confirmatory-replication-candidate.json"
)
RUNTIME_PATH = (
    "scripts/forge_opaque_provenance_confirmatory_replication_authorized_runner.py"
)
LIFECYCLE_GATE_PATH = (
    "scripts/forge_opaque_provenance_confirmatory_replication_lifecycle_gate.py"
)
PAIR_EXECUTOR_PATH = (
    "scripts/forge_opaque_provenance_confirmatory_execution_repair_adapter.py"
)
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-opaque-provenance-confirmatory-replication-authorized.md"

SCHEMA_VERSION = "forge-opaque-provenance-confirmatory-replication-authorized-1.0.0"
DOCUMENT_TYPE = "forge_opaque_provenance_confirmatory_replication_authorized"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/247"
AUTHORIZATION_BASELINE_COMMIT = "d3b25da4d8e95d781828ac367929741fd82c4a41"
PARENT_MANIFEST_CANONICAL_SHA256 = (
    "7b1817becba4ec57eb9726be0e1faaa5427af309dca7552634e3f6a3a1b5d938"
)
PARENT_MANIFEST_FILE_SHA256 = (
    "b6eb90bfc5242dec1881627101de3c0c4589c5863700293d92bec80bea2de324"
)
LIFECYCLE_GATE_FILE_SHA256 = (
    "0f385161047ee1eb8adc6ab55161447cddef28d479f96ef220762f4296ab5a25"
)

FROZEN_PARENT_PATHS = (
    PARENT_MANIFEST_PATH,
    "benchmarks/schemas/forge-opaque-provenance-confirmatory-replication-candidate.schema.json",
    "benchmarks/preregistrations/cpp-opaque-provenance-confirmatory-replication-candidate.md",
    "scripts/forge_opaque_provenance_confirmatory_replication_candidate_protocol.py",
    LIFECYCLE_GATE_PATH,
    "benchmarks/preregistrations/cpp-opaque-provenance-confirmatory-replication-lifecycle-zero-provider-gate.md",
    PAIR_EXECUTOR_PATH,
)


class ProtocolError(RuntimeError):
    """Replication 授权 identity、父候选、预算或 runtime 发生漂移。"""


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
    path = (
        repo_root
        / "scripts/forge_opaque_provenance_confirmatory_replication_candidate_protocol.py"
    )
    name = "forge_confirmatory_replication_authorized_parent"
    existing = sys.modules.get(name)
    if existing is not None and Path(existing.__file__).resolve() == path.resolve():
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ProtocolError("无法加载 Issue #243 parent protocol")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _parent_manifest(repo_root: Path = REPO_ROOT) -> tuple[dict[str, Any], Any]:
    parent = _load_parent_protocol(repo_root)
    path = repo_root / PARENT_MANIFEST_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError("无法读取 Issue #243 parent manifest") from exc
    manifest = parent.validate_manifest(value, repo_root)
    if parent.canonical_sha256(manifest) != PARENT_MANIFEST_CANONICAL_SHA256:
        raise ProtocolError("Issue #243 parent canonical identity 发生漂移")
    if file_sha256(path) != PARENT_MANIFEST_FILE_SHA256:
        raise ProtocolError("Issue #243 parent 文件 identity 发生漂移")
    return manifest, parent


def _frozen_parent_sha256(repo_root: Path) -> dict[str, str]:
    return {path: file_sha256(repo_root / path) for path in FROZEN_PARENT_PATHS}


def _authorized_execution(parent: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    candidate = parent["replication_candidate"]
    runtime_path = repo_root / RUNTIME_PATH
    preregistration_path = repo_root / PREREGISTRATION_PATH
    if not runtime_path.is_file() or not preregistration_path.is_file():
        raise ProtocolError("replication authorized runtime 或预注册不存在")
    if file_sha256(repo_root / LIFECYCLE_GATE_PATH) != LIFECYCLE_GATE_FILE_SHA256:
        raise ProtocolError("Issue #245 lifecycle gate 发生漂移")
    provider = copy.deepcopy(candidate["provider_candidate"])
    provider["status"] = "active_authorized"
    budget = copy.deepcopy(candidate["budget_candidate"])
    budget["authorized"] = True
    evidence = copy.deepcopy(candidate["evidence_candidate"])
    evidence["writes_authorized"] = True
    preflight = copy.deepcopy(candidate["preflight_candidate"])
    preflight["lifecycle_gate"] = {
        "path": LIFECYCLE_GATE_PATH,
        "file_sha256": LIFECYCLE_GATE_FILE_SHA256,
        "status": "passed",
        "release_commit": AUTHORIZATION_BASELINE_COMMIT,
    }
    return {
        "issue_url": ISSUE_URL,
        "status": "authorized_not_started",
        "authorization_baseline_commit": AUTHORIZATION_BASELINE_COMMIT,
        "release_revision_policy": "descendant_merged_main_recorded_before_first_request",
        "provider": provider,
        "budget": budget,
        "evidence": evidence,
        "preflight": preflight,
        "execution": {
            "reachability_prompt": "Reply with exactly CANARY_OK and nothing else.",
            "reachability_expected_response": "CANARY_OK",
            "single_asyncio_loop_for_batch": True,
            "checkpoint_capture_restore_reimplemented": False,
            "runtime_path": RUNTIME_PATH,
            "runtime_file_sha256": file_sha256(runtime_path),
            "pair_executor_adapter": PAIR_EXECUTOR_PATH,
            "pair_executor_file_sha256": candidate["runtime_candidate"][
                "runtime_file_sha256"
            ],
            "pair_executor_entrypoint": candidate["runtime_candidate"]["entrypoint"],
            "commands": ["validate", "preflight", "reachability", "batch", "report"],
        },
        "terminal_taxonomy": copy.deepcopy(
            parent["execution_candidate"]["terminal_taxonomy"]
        ),
        "analysis": copy.deepcopy(candidate["analysis"]),
        "relationship_to_v1": copy.deepcopy(candidate["relationship_to_v1"]),
        "preregistration": {
            "path": PREREGISTRATION_PATH,
            "file_sha256": file_sha256(preregistration_path),
        },
    }


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    parent, _parent_protocol = _parent_manifest(repo_root)
    value = copy.deepcopy(parent)
    value["$schema"] = (
        "../schemas/forge-opaque-provenance-confirmatory-replication-authorized.schema.json"
    )
    value["schema_version"] = SCHEMA_VERSION
    value["document_type"] = DOCUMENT_TYPE
    value["runtime_contract"]["provider_identity_status"] = "active_authorized"
    ceiling = parent["replication_candidate"]["budget_candidate"][
        "batch_maximum_recorded_tokens"
    ]
    value["authorization"] = {
        "provider_calls_authorized": True,
        "credential_read_authorized": True,
        "model_creation_authorized": True,
        "reachability_request_authorized": True,
        "checkpoint_creation_authorized": True,
        "pair_collection_authorized": True,
        "formal_attempts_authorized": True,
        "docker_execution_authorized": True,
        "evidence_write_authorized": True,
        "model_tokens_authorized": ceiling,
    }
    value["future_state"] = {
        "checkpoint_status": "authorized_not_created",
        "evidence_status": "authorized_not_created",
        "execution_runner_status": "authorized_repair_adapter_runner",
        "execution_requires_new_amendment": False,
    }
    value["authorized_execution"] = _authorized_execution(parent, repo_root)
    value["frozen_replication_components"] = _frozen_parent_sha256(repo_root)
    value["preregistration"] = copy.deepcopy(
        value["authorized_execution"]["preregistration"]
    )
    return value


def validate_allowed_delta(
    value: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    parent, _parent_protocol = _parent_manifest(repo_root)
    normalized = copy.deepcopy(value)
    authorized = normalized.pop("authorized_execution", None)
    normalized.pop("frozen_replication_components", None)
    normalized["$schema"] = parent["$schema"]
    normalized["schema_version"] = parent["schema_version"]
    normalized["document_type"] = parent["document_type"]
    normalized["runtime_contract"] = copy.deepcopy(parent["runtime_contract"])
    normalized["authorization"] = copy.deepcopy(parent["authorization"])
    normalized["future_state"] = copy.deepcopy(parent["future_state"])
    normalized["preregistration"] = copy.deepcopy(parent["preregistration"])
    if normalized != parent:
        differing = sorted(
            key
            for key in set(normalized) | set(parent)
            if normalized.get(key) != parent.get(key)
        )
        raise ProtocolError(
            f"replication authorized amendment 包含未预注册的父协议差异: {differing}"
        )
    if authorized != _authorized_execution(parent, repo_root):
        raise ProtocolError("replication authorized execution identity 发生漂移")
    relationship = authorized["relationship_to_v1"]
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
        raise ProtocolError("authorized amendment 意外导入或延长 confirmatory v1")
    return {
        "status": "passed",
        "parent_manifest_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        "schedule_identity_sha256": parent["schedule"]["identity_sha256"],
        "evidence_identity_sha256": authorized["evidence"]["identity_sha256"],
        "verifier_relaxation": False,
        "historical_outcomes_imported": False,
        "v1_attempt_extended": False,
    }


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    expected = generate_manifest(repo_root)
    if not isinstance(value, dict) or value != expected:
        raise ProtocolError("authorized replication manifest 发生漂移")
    validate_allowed_delta(value, repo_root)
    authorization = value["authorization"]
    execution = value["authorized_execution"]
    if (
        authorization["model_tokens_authorized"]
        != execution["budget"]["batch_maximum_recorded_tokens"]
    ):
        raise ProtocolError("replication 授权 token ceiling 发生漂移")
    if not all(
        item is True
        for key, item in authorization.items()
        if key.endswith("_authorized") and key != "model_tokens_authorized"
    ):
        raise ProtocolError("replication 真实执行授权未闭合")
    if (
        execution["provider"]["fallback"] != "forbidden"
        or execution["provider"]["max_retries"] != 0
    ):
        raise ProtocolError("replication provider retry/fallback 边界发生漂移")
    return value


def load_manifest(
    path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError("无法读取 authorized replication manifest") from exc
    return validate_manifest(value, repo_root)


def verify_frozen_components(
    manifest: dict[str, Any], repo_root: Path = REPO_ROOT
) -> None:
    if manifest["frozen_replication_components"] != _frozen_parent_sha256(repo_root):
        raise ProtocolError("Issue #243/#245 冻结组件发生漂移")
    execution = manifest["authorized_execution"]["execution"]
    if (
        file_sha256(repo_root / execution["runtime_path"])
        != execution["runtime_file_sha256"]
    ):
        raise ProtocolError("replication authorized runtime 发生漂移")
    if (
        file_sha256(repo_root / execution["pair_executor_adapter"])
        != execution["pair_executor_file_sha256"]
    ):
        raise ProtocolError("replication pair executor 发生漂移")


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    frozen = manifest or generate_manifest()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-opaque-provenance-confirmatory-replication-authorized.schema.json",
        "title": "Forge opaque provenance confirmatory independent replication authorized amendment",
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
        if json.loads(args.schema.read_text(encoding="utf-8")) != schema_document(
            manifest
        ):
            raise ProtocolError("authorized replication const schema 发生漂移")
    print(
        json.dumps(
            {
                "manifest_sha256": canonical_sha256(manifest),
                "authorization": manifest["authorization"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
