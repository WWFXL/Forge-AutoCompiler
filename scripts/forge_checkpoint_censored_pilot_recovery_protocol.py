#!/usr/bin/env python3
"""Issue #161 coordinator WAL 审计 recovery amendment 协议。"""

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
REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", SCRIPT_ROOT.parent)).resolve()
V1_MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-checkpoint-censored-pilot-v1.json"
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-checkpoint-censored-pilot-recovery-v1.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks" / "schemas" / "forge-checkpoint-censored-pilot-recovery-v1.schema.json"
V1_OUTPUT_DIR = Path("/workspace/.compile-sessions/benchmark-evidence-checkpoint-censored-pilot-v1")
DEFAULT_OUTPUT_DIR = Path("/workspace/.compile-sessions/benchmark-evidence-checkpoint-censored-pilot-recovery-v1")

SCHEMA_VERSION = "forge-checkpoint-censored-pilot-recovery-1.0.0"
DOCUMENT_TYPE = "forge_checkpoint_censored_pilot_recovery"
V1_CANONICAL_SHA256 = "d5edd9683def7c8842ad1eb0471cce877b47b52b2939f1b45d9c2a51f2362391"
IMPORTED_RECORDED_TOKENS = 23_811
ADDITIONAL_RECORDED_TOKEN_LIMIT = 1_200_000
TOTAL_RECORDED_TOKEN_LIMIT = 1_440_000

V1_COMPONENTS = {
    "benchmarks/manifests/cpp-verifier-checkpoint-censored-pilot-v1.json": ("640c463331ab2eaded74417a1311fc841c6561fc98153dbed88a9754619a67ee"),
    "scripts/forge_checkpoint_censored_pilot_protocol.py": ("b48b43568d0a1f4c1c548e56aeb7e31a94ef6bb40c515fdcedf0edda5e650758"),
    "scripts/forge_checkpoint_censored_pilot_runner.py": ("819a8d25d65d1e6019c1d994515ee5534533513e3dcc299ca75a043480c3d768"),
}

V1_EVIDENCE = {
    "markers/pilot-attempt.json": ("90637cef19d2859c3067c6b1b982d8b91c180a94b20d999a5349948c68023575"),
    "pairs/pair-01/checkpoint/coordinator.sqlite": ("304288805942f5b210c82e06d421a6264edc344b7ff15066ddb6a91456c89a7c"),
    "pairs/pair-01/checkpoint/messages.sqlite": ("7a16adf27013d6e6f76a4c11c43f179ea63436f8dfec253359a4644feca633e9"),
    "pairs/pair-01/ledgers/baseline.jsonl": ("717755fa47d5f585282a76b4767454b8fe446c39f453375dc8f6bb6d38375aea"),
    "pairs/pair-01/ledgers/parent.jsonl": ("858097dfa4ce93815e304f14974a799e35d15d5286293470e22c8686bebf738d"),
    "pairs/pair-01/ledgers/treatment.jsonl": ("c504c61b3a492d00740d3abbf3cb19a457a6599a5212602b4d1f1f0c612ab840"),
    "pairs/pair-01/markers/pair-attempt.json": ("8178d32c61f4ed4425aa5dfa0ad155ba86fcf9626ef1b31bfe0eee1492f5de5d"),
    "pairs/pair-01/reports/controlled-pair.json": ("afad25b4c41ae3098b7feb4711d8f4f746f856a9e9773052c13b05a6054471f4"),
}

V1_SESSION_TERMINALS = {
    ".compile-sessions/baseline-primary-canary-a8d91e3243a3-thread/baseline-primary-canary-a8d91e3243a3-session/session.json": ("39cc1947501b01b63afa25479d35e9e4531193a33b4923701f326d9dbf1f6847"),
    ".compile-sessions/parent-0f56a49c49ea/parent-7f16996f020f/session.json": ("281308e574ce629a01026c3611397c7ceca47fc8a780cd71a140b5285d82337d"),
    ".compile-sessions/treatment-primary-canary-a8d91e3243a3-thread/treatment-primary-canary-a8d91e3243a3-session/session.json": ("b0b94326e284456f5c0c8cc7272efc95a465d8c43680e6c49759f11e0fdc1bbf"),
}

PROTOCOL_ARTIFACT_PATHS = {
    "scripts/forge_checkpoint_censored_pilot_recovery_protocol.py",
    "scripts/forge_checkpoint_censored_pilot_recovery_runner.py",
    "backend/tests/test_forge_checkpoint_censored_pilot_recovery.py",
    "benchmarks/preregistrations/cpp-verifier-checkpoint-censored-pilot-recovery-v1.md",
}


class ProtocolError(RuntimeError):
    """Recovery amendment identity 或冻结 evidence 发生漂移。"""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ProtocolError(f"JSON 根节点必须是对象: {path}")
    return value


def _hash_protocol_artifacts(repo_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative_path in sorted(PROTOCOL_ARTIFACT_PATHS):
        path = repo_root / relative_path
        if not path.is_file():
            raise ProtocolError(f"recovery 协议制品缺失: {relative_path}")
        result[relative_path] = file_sha256(path)
    return result


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    parent = _load_json(repo_root / V1_MANIFEST_PATH.relative_to(REPO_ROOT))
    if canonical_sha256(parent) != V1_CANONICAL_SHA256:
        raise ProtocolError("v1 manifest canonical identity 发生漂移")
    manifest = copy.deepcopy(parent)
    manifest["$schema"] = "../schemas/forge-checkpoint-censored-pilot-recovery-v1.schema.json"
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["document_type"] = DOCUMENT_TYPE
    manifest["authorization"] = {
        "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/161",
        "authorized_by": "experiment_owner",
        "route": "B-recovery",
        "pilot_collection_authorized": True,
        "authorized_additional_pairs": 5,
        "maximum_additional_recorded_tokens": ADDITIONAL_RECORDED_TOKEN_LIMIT,
        "maximum_total_recorded_tokens": TOTAL_RECORDED_TOKEN_LIMIT,
    }
    manifest["budget"].update(
        imported_recorded_tokens=IMPORTED_RECORDED_TOKENS,
        additional_recorded_token_limit=ADDITIONAL_RECORDED_TOKEN_LIMIT,
        stage_maximum_recorded_tokens=TOTAL_RECORDED_TOKEN_LIMIT,
    )
    manifest["execution"].update(
        evidence_directory=str(DEFAULT_OUTPUT_DIR),
        authorization_baseline_commit="95dafbe7ca2f69c2beb2b5a4c9779b8619c70736",
        recovery_import="pair-01",
        recovery_execution_pairs=[
            "pair-02",
            "pair-03",
            "pair-04",
            "pair-05",
            "pair-06",
        ],
        coordinator_audit="copy-main-wal-shm-then-read-copy",
    )
    manifest["recovery"] = {
        "parent_manifest_canonical_sha256": V1_CANONICAL_SHA256,
        "parent_components": dict(sorted(V1_COMPONENTS.items())),
        "imported_pair": {
            "pair_id": "pair-01",
            "status": "complete",
            "recorded_tokens": IMPORTED_RECORDED_TOKENS,
            "source_directory": str(V1_OUTPUT_DIR),
            "expected_file_count": len(V1_EVIDENCE),
            "files": dict(sorted(V1_EVIDENCE.items())),
            "session_terminals": dict(sorted(V1_SESSION_TERMINALS.items())),
            "rerun_forbidden": True,
        },
        "failure_classification": "post_pair_coordinator_wal_visibility_race",
        "replacement": False,
        "backfill": False,
    }
    manifest["protocol_artifacts"] = _hash_protocol_artifacts(repo_root)
    return manifest


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if not isinstance(value, dict) or value != generate_manifest(repo_root):
        raise ProtocolError("recovery manifest 与冻结协议不一致")
    if value["execution"]["recovery_execution_pairs"] != [f"pair-{number:02d}" for number in range(2, 7)]:
        raise ProtocolError("recovery 只能执行 pair-02 至 pair-06")
    return value


def verify_frozen_components(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> None:
    validate_manifest(manifest, repo_root)
    for relative_path, expected in manifest["recovery"]["parent_components"].items():
        path = repo_root / relative_path
        if not path.is_file() or file_sha256(path) != expected:
            raise ProtocolError(f"v1 冻结组件发生漂移: {relative_path}")
    for relative_path, expected in manifest["protocol_artifacts"].items():
        path = repo_root / relative_path
        if not path.is_file() or file_sha256(path) != expected:
            raise ProtocolError(f"recovery 协议制品发生漂移: {relative_path}")


def verify_v1_evidence(
    manifest: dict[str, Any],
    *,
    output_dir: Path = V1_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    imported = manifest["recovery"]["imported_pair"]
    expected = imported["files"]
    actual = {path.relative_to(output_dir).as_posix() for path in output_dir.rglob("*") if path.is_file()}
    if actual != set(expected):
        raise ProtocolError("v1 pilot evidence 文件集合发生漂移")
    for relative_path, digest in expected.items():
        if file_sha256(output_dir / relative_path) != digest:
            raise ProtocolError(f"v1 pilot evidence hash 发生漂移: {relative_path}")
    for relative_path, digest in imported["session_terminals"].items():
        if file_sha256(repo_root / relative_path) != digest:
            raise ProtocolError(f"v1 Session 终态发生漂移: {relative_path}")
    return {
        "status": "valid",
        "file_count": len(actual),
        "imported_pair": imported["pair_id"],
        "recorded_tokens": imported["recorded_tokens"],
    }


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": ("https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-checkpoint-censored-pilot-recovery-v1.schema.json"),
        "title": "Forge checkpoint censored pilot recovery amendment",
        "const": manifest or generate_manifest(),
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
    parser.add_argument("command", choices=("generate", "validate", "validate-v1-evidence"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--v1-output-dir", type=Path, default=V1_OUTPUT_DIR)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            manifest = generate_manifest()
            _write_json(args.manifest, manifest)
            _write_json(args.schema, schema_document(manifest))
            status = "generated"
        else:
            manifest = validate_manifest(_load_json(args.manifest))
            verify_frozen_components(manifest)
            if args.command == "validate-v1-evidence":
                verify_v1_evidence(manifest, output_dir=args.v1_output_dir)
            status = "valid"
    except (OSError, ProtocolError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": status,
                "manifest_sha256": canonical_sha256(manifest),
                "imported_pairs": 1,
                "authorized_additional_pairs": 5,
                "maximum_additional_recorded_tokens": (ADDITIONAL_RECORDED_TOKEN_LIMIT),
                "provider_calls": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
