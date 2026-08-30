#!/usr/bin/env python3
"""Issue #235 六 case confirmatory execution 的未授权候选协议。"""

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
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/235"
SCHEMA_VERSION = "forge-opaque-provenance-confirmatory-execution-candidate-1.0.0"
DOCUMENT_TYPE = "forge_opaque_provenance_confirmatory_execution_candidate"

PARENT_MANIFEST_PATH = "benchmarks/manifests/cpp-opaque-provenance-confirmatory-candidate-v2.json"
PARENT_MANIFEST_FILE_SHA256 = "c9026aa28268619485f2c7b2e72dbf70b8105e8aca2253d4226debcfc1da7133"
PARENT_MANIFEST_SHA256 = "ca2dd38f4dd298272f5e2203484857cbc72a6fc86e161dabefed2a61b54b6812"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-opaque-provenance-confirmatory-execution-candidate.md"
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-confirmatory-execution-candidate.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-confirmatory-execution-candidate.schema.json"

FROZEN_COMPONENTS = {
    "scripts/forge_opaque_provenance_confirmatory_lifecycle_gate.py": "e4f06fedec242b31448e5eaa1a6c271cc3e33fa197919434aac9510d2f900f64",
    "scripts/forge_opaque_provenance_runtime_parity_gate.py": "251cc446cc508552d85cdf82238192b702bbb2e51ee428c42d47188d0f12b40b",
    "scripts/forge_opaque_provenance_rejection_observability_gate.py": "695c6188acf92f4e34dcbaf4c6f049ca4b024e9bdd1eb91085c0c8d5d0ace158",
    "scripts/forge_opaque_provenance_r3_make_candidate_runner.py": "b8ec84f3835ecbbc462232b676c5ebf72e15a7f021be2a148d1b85d8138e9be0",
    "scripts/forge_opaque_provenance_r3_make_execution_failure_gate.py": "cd36955c5256fa4376d0b5a4b60c139352ec2f8beb59c9b88741ad681b5bdb06",
    "scripts/forge_opaque_provenance_r3_make_agent_construction_gate.py": "f5a0af19e2ff1cc7dd90f096132d537ec3db4867649571640c29d8262f890e5a",
    "scripts/forge_checkpoint_behavioral_pilot_v2_runner.py": "82a041ea3c7a8de762a014aaf405ccb10e62e1baaa5a79d22548c8af98dccd95",
}


class ConfirmatoryExecutionCandidateError(RuntimeError):
    """确认性 execution candidate 身份、授权或停止规则发生漂移。"""


def _load_parent_module():
    path = SCRIPT_ROOT / "forge_opaque_provenance_confirmatory_candidate_v2_protocol.py"
    spec = importlib.util.spec_from_file_location("forge_confirmatory_execution_parent", path)
    if spec is None or spec.loader is None:
        raise ConfirmatoryExecutionCandidateError("无法加载 Issue #233 parent protocol")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


parent = _load_parent_module()
CASE_ORDER = parent.CASE_ORDER


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


def verify_frozen_components(repo_root: Path = REPO_ROOT) -> None:
    for relative_path, expected in FROZEN_COMPONENTS.items():
        if file_sha256(repo_root / relative_path) != expected:
            raise ConfirmatoryExecutionCandidateError(f"冻结组件发生漂移: {relative_path}")


def _parent_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    path = repo_root / PARENT_MANIFEST_PATH
    if file_sha256(path) != PARENT_MANIFEST_FILE_SHA256:
        raise ConfirmatoryExecutionCandidateError("Issue #233 parent manifest 文件发生漂移")
    value = json.loads(path.read_text(encoding="utf-8"))
    if canonical_sha256(value) != PARENT_MANIFEST_SHA256:
        raise ConfirmatoryExecutionCandidateError("Issue #233 parent manifest identity 发生漂移")
    return parent.validate_manifest(value, repo_root)


def build_repair_packet(case: dict[str, Any]) -> dict[str, str]:
    build_directory = "/workspace/repo/build" if case["build_system"] == "cmake" else "/workspace/repo"
    return {
        "schema_version": "forge-opaque-provenance-repair-packet-1.0.0",
        "primary_classification": "build_system_unproven",
        "mechanism_classification": "opaque_build_provenance",
        "expected_build_system": case["build_system"],
        "selected_build_system": case["build_system"],
        "build_directory": build_directory,
        "target": case["direct_target"],
        "proof_status": "opaque_wrapper",
        "repair_goal": "produce a provenance-compliant direct build and submit the frozen artifact",
    }


def _execution_candidate(parent_manifest: dict[str, Any]) -> dict[str, Any]:
    packets = {case["case_id"]: build_repair_packet(case) for case in parent_manifest["cases"]}
    return {
        "issue_url": ISSUE_URL,
        "status": "composition_gate_only_not_authorized",
        "parent": {"path": PARENT_MANIFEST_PATH, "file_sha256": PARENT_MANIFEST_FILE_SHA256, "canonical_sha256": PARENT_MANIFEST_SHA256, "modified": False},
        "provider": {
            "status": "selected_not_authorized",
            "id": "deepseek-v4-flash",
            "endpoint": "https://api.deepseek.com",
            "credential_env": "DEEPSEEK_API_KEY",
            "model": "deepseek-v4-flash",
            "request_timeout_seconds": 300,
            "max_retries": 0,
            "fallback": "forbidden",
            "streaming": False,
        },
        "evidence": {
            "directory": "/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-confirmatory-v1",
            "reachability_marker": "markers/reachability.json",
            "reachability_report": "reports/reachability.json",
            "batch_marker": "markers/batch.json",
            "batch_report": "reports/batch.json",
            "pair_directory_pattern": "pairs/{pair_id}",
            "create_once": True,
            "historical_evidence_reused": False,
        },
        "orchestration": {
            "lifecycle_adapter": "scripts/forge_opaque_provenance_confirmatory_lifecycle_gate.py",
            "cmake_action_policy": "scripts/forge_opaque_provenance_runtime_parity_gate.py",
            "make_action_policy": "scripts/forge_opaque_provenance_r3_make_candidate_runner.py",
            "r0_observability_required": True,
            "full_agent_construction_required": True,
            "single_asyncio_loop_for_batch": True,
            "checkpoint_capture_restore_reimplemented": False,
            "real_pair_runner_implemented": False,
        },
        "repair_packets": packets,
        "terminal_taxonomy": {
            "continue": ["valid", "endpoint_censored", "model_behavior_outcome"],
            "stop_batch": ["mechanism_invalid", "identity_invalid", "evidence_invalid", "cleanup_failed", "orphan_detected", "token_ceiling_reached"],
            "replacement_forbidden": True,
            "backfill_forbidden": True,
        },
        "planned_authorized_amendment": {
            "reachability_requests": 1,
            "scheduled_pairs": parent_manifest["schedule"]["pair_count"],
            "scheduled_arms": parent_manifest["schedule"]["arm_count"],
            "batch_recorded_token_ceiling": parent_manifest["runtime_contract"]["batch_recorded_token_ceiling"],
            "release_commit_required": True,
            "separate_authorization_required": True,
        },
        "frozen_components": copy.deepcopy(FROZEN_COMPONENTS),
    }


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    verify_frozen_components(repo_root)
    preregistration = repo_root / PREREGISTRATION_PATH
    if not preregistration.is_file():
        raise ConfirmatoryExecutionCandidateError("execution candidate 预注册不存在")
    value = copy.deepcopy(_parent_manifest(repo_root))
    value["$schema"] = "../schemas/forge-opaque-provenance-confirmatory-execution-candidate.schema.json"
    value["schema_version"] = SCHEMA_VERSION
    value["document_type"] = DOCUMENT_TYPE
    value["runtime_contract"]["provider_identity_status"] = "selected_not_authorized"
    value["future_state"]["execution_runner_status"] = "composition_gate_only"
    value["execution_candidate"] = _execution_candidate(value)
    value["preregistration"] = {"path": PREREGISTRATION_PATH, "file_sha256": file_sha256(preregistration)}
    return value


def validate_allowed_delta(value: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    normalized = copy.deepcopy(value)
    candidate = normalized.pop("execution_candidate", None)
    parent_value = _parent_manifest(repo_root)
    if candidate != _execution_candidate(parent_value):
        raise ConfirmatoryExecutionCandidateError("execution candidate metadata 发生漂移")
    normalized["$schema"] = "../schemas/forge-opaque-provenance-confirmatory-candidate-v2.schema.json"
    normalized["schema_version"] = parent.SCHEMA_VERSION
    normalized["document_type"] = parent.DOCUMENT_TYPE
    normalized["runtime_contract"]["provider_identity_status"] = parent_value["runtime_contract"]["provider_identity_status"]
    normalized["future_state"]["execution_runner_status"] = parent_value["future_state"]["execution_runner_status"]
    normalized["preregistration"] = copy.deepcopy(parent_value["preregistration"])
    if normalized != parent_value:
        raise ConfirmatoryExecutionCandidateError("execution candidate 包含未授权的父协议差异")
    return {
        "status": "passed",
        "parent_manifest_sha256": PARENT_MANIFEST_SHA256,
        "schedule_identity_sha256": value["schedule"]["identity_sha256"],
        "provider_status": candidate["provider"]["status"],
        "real_pair_runner_implemented": False,
        "verifier_relaxation": False,
    }


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    expected = generate_manifest(repo_root)
    if not isinstance(value, dict) or value != expected:
        raise ConfirmatoryExecutionCandidateError("confirmatory execution candidate manifest 发生漂移")
    validate_allowed_delta(value, repo_root)
    if value["authorization"] != _parent_manifest(repo_root)["authorization"]:
        raise ConfirmatoryExecutionCandidateError("candidate 修改了父授权边界")
    if any(item for key, item in value["authorization"].items() if key.endswith("_authorized")) or value["authorization"]["model_tokens_authorized"] != 0:
        raise ConfirmatoryExecutionCandidateError("candidate 意外授权了真实执行")
    return value


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    frozen = manifest or generate_manifest()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-opaque-provenance-confirmatory-execution-candidate.schema.json",
        "title": "Forge opaque provenance confirmatory execution candidate",
        "const": frozen,
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate"))
    args = parser.parse_args(argv)
    manifest = generate_manifest()
    if args.command == "generate":
        _write_json(DEFAULT_MANIFEST, manifest)
        _write_json(DEFAULT_SCHEMA, schema_document(manifest))
    else:
        validate_manifest(json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8")))
        if json.loads(DEFAULT_SCHEMA.read_text(encoding="utf-8")) != schema_document(manifest):
            raise ConfirmatoryExecutionCandidateError("execution candidate const schema 发生漂移")
    print(json.dumps({"manifest_sha256": canonical_sha256(manifest), "allowed_delta": validate_allowed_delta(manifest)}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
