#!/usr/bin/env python3
"""Issue #233 六 case confirmatory candidate 的 pre-result bootstrap amendment。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_ROOT = REPO_ROOT / "scripts"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/233"
SCHEMA_VERSION = "forge-opaque-provenance-confirmatory-candidate-2.0.0"
DOCUMENT_TYPE = "forge_opaque_provenance_confirmatory_candidate_v2"

PARENT_MANIFEST_PATH = "benchmarks/manifests/cpp-opaque-provenance-confirmatory-candidate.json"
PARENT_MANIFEST_SHA256 = "8b7c2e193204a1f1c0b077933d716e66c1138ff3bc7ef54c490c3299652da1e3"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-opaque-provenance-confirmatory-candidate-v2.md"
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-confirmatory-candidate-v2.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-confirmatory-candidate-v2.schema.json"

SQL_PARSER_CASE_ID = "sql-parser-shared"
SQL_PARSER_BOOTSTRAP = "cd src/parser && bison bison_parser.y --output=bison_parser.cpp --defines=bison_parser.h --verbose"


class ConfirmatoryCandidateV2Error(RuntimeError):
    """v2 amendment 超出允许差异或授权边界。"""


def _load_parent_module():
    path = SCRIPT_ROOT / "forge_opaque_provenance_confirmatory_candidate_protocol.py"
    spec = importlib.util.spec_from_file_location(
        "forge_opaque_provenance_confirmatory_candidate_v2_parent",
        path,
    )
    if spec is None or spec.loader is None:
        raise ConfirmatoryCandidateV2Error("无法加载 #230 parent protocol")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


parent = _load_parent_module()
CASE_ORDER = parent.CASE_ORDER


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


def _parent_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    path = repo_root / PARENT_MANIFEST_PATH
    if file_sha256(path) != PARENT_MANIFEST_SHA256:
        raise ConfirmatoryCandidateV2Error("#230 parent manifest 发生漂移")
    value = json.loads(path.read_text(encoding="utf-8"))
    return parent.validate_manifest(value, repo_root)


def _amendment() -> dict[str, Any]:
    return {
        "issue_url": ISSUE_URL,
        "mode": "pre_result_lifecycle_reproducibility_amendment",
        "parent_manifest": {
            "path": PARENT_MANIFEST_PATH,
            "canonical_sha256": PARENT_MANIFEST_SHA256,
            "modified": False,
        },
        "trigger": {
            "case_id": SQL_PARSER_CASE_ID,
            "classification": "clean_replay_sha256_mismatch",
            "provider_results_observed": False,
            "root_cause": "checkout mtime can select tracked or regenerated Bison parser sources",
        },
        "allowed_semantic_delta": {
            "path": "cases[sql-parser-shared].bootstrap_commands",
            "before": [],
            "after": [SQL_PARSER_BOOTSTRAP],
        },
        "verifier_relaxation": False,
        "schedule_modified": False,
        "artifact_oracle_modified": False,
    }


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    preregistration = repo_root / PREREGISTRATION_PATH
    if not preregistration.is_file():
        raise ConfirmatoryCandidateV2Error("v2 preregistration 不存在")
    value = copy.deepcopy(_parent_manifest(repo_root))
    value["$schema"] = "../schemas/forge-opaque-provenance-confirmatory-candidate-v2.schema.json"
    value["schema_version"] = SCHEMA_VERSION
    value["document_type"] = DOCUMENT_TYPE
    value["amendment"] = _amendment()
    matches = [case for case in value["cases"] if case["case_id"] == SQL_PARSER_CASE_ID]
    if len(matches) != 1 or matches[0]["bootstrap_commands"] != []:
        raise ConfirmatoryCandidateV2Error("sql-parser-shared parent bootstrap 发生漂移")
    matches[0]["bootstrap_commands"] = [SQL_PARSER_BOOTSTRAP]
    value["preregistration"] = {
        "path": PREREGISTRATION_PATH,
        "file_sha256": file_sha256(preregistration),
    }
    return value


def validate_allowed_delta(value: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    normalized = copy.deepcopy(value)
    if normalized.pop("amendment", None) != _amendment():
        raise ConfirmatoryCandidateV2Error("amendment metadata 发生漂移")
    normalized["$schema"] = "../schemas/forge-opaque-provenance-confirmatory-candidate.schema.json"
    normalized["schema_version"] = parent.SCHEMA_VERSION
    normalized["document_type"] = parent.DOCUMENT_TYPE
    matches = [case for case in normalized["cases"] if case["case_id"] == SQL_PARSER_CASE_ID]
    if len(matches) != 1 or matches[0]["bootstrap_commands"] != [SQL_PARSER_BOOTSTRAP]:
        raise ConfirmatoryCandidateV2Error("v2 bootstrap delta 发生漂移")
    matches[0]["bootstrap_commands"] = []
    parent_value = _parent_manifest(repo_root)
    normalized["preregistration"] = copy.deepcopy(parent_value["preregistration"])
    if normalized != parent_value:
        raise ConfirmatoryCandidateV2Error("v2 包含未授权的额外语义差异")
    return {
        "status": "passed",
        "parent_manifest_sha256": PARENT_MANIFEST_SHA256,
        "case_id": SQL_PARSER_CASE_ID,
        "bootstrap_before": [],
        "bootstrap_after": [SQL_PARSER_BOOTSTRAP],
        "schedule_identity_sha256": value["schedule"]["identity_sha256"],
        "schedule_modified": False,
        "artifact_oracle_modified": False,
        "verifier_relaxation": False,
    }


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    expected = generate_manifest(repo_root)
    if not isinstance(value, dict) or value != expected:
        raise ConfirmatoryCandidateV2Error("confirmatory candidate v2 manifest 发生漂移")
    validate_allowed_delta(value, repo_root)
    authorization = value["authorization"]
    if any(item for key, item in authorization.items() if key.endswith("_authorized")):
        raise ConfirmatoryCandidateV2Error("v2 意外授权了外部执行")
    if authorization["model_tokens_authorized"] != 0:
        raise ConfirmatoryCandidateV2Error("v2 意外授权了 model token")
    return value


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    frozen = manifest or generate_manifest()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-opaque-provenance-confirmatory-candidate-v2.schema.json",
        "title": "Forge opaque provenance confirmatory candidate v2",
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
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="确定性写入 v2 manifest 与 const schema")
    args = parser.parse_args(argv)
    manifest = generate_manifest()
    schema = schema_document(manifest)
    if args.write:
        _write_json(DEFAULT_MANIFEST, manifest)
        _write_json(DEFAULT_SCHEMA, schema)
    else:
        validate_manifest(json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8")))
        if json.loads(DEFAULT_SCHEMA.read_text(encoding="utf-8")) != schema:
            raise ConfirmatoryCandidateV2Error("confirmatory candidate v2 schema 发生漂移")
    print(json.dumps(validate_static_gate(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
