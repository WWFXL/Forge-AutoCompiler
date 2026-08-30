#!/usr/bin/env python3
"""Issue #226 OpenH264 provenance 单配对 execution amendment。"""

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
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-openh264-execution.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-openh264-execution.schema.json"
PARENT_MANIFEST_PATH = "benchmarks/manifests/cpp-opaque-provenance-openh264-candidate.json"
REFERENCE_EXECUTION_PATH = "benchmarks/manifests/cpp-opaque-provenance-r3-make-execution.json"
RUNTIME_ADAPTER_PATH = "scripts/forge_opaque_provenance_openh264_execution_runner.py"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-opaque-provenance-openh264-execution.md"

SCHEMA_VERSION = "forge-opaque-provenance-openh264-execution-1.0.0"
DOCUMENT_TYPE = "forge_opaque_provenance_openh264_execution_amendment"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/226"
AUTHORIZATION_BASELINE_COMMIT = "185fcbed4e7ad01f6eae6cb247304601f480f83f"
PARENT_MANIFEST_CANONICAL_SHA256 = "ab29737969549ddf3d309fb2868a0254b8a346842cc1e168d7e475d123f4e0d6"
PARENT_EVIDENCE_IDENTITY_SHA256 = "dd777763ab03ec6853c7e36299b78acff3e0383ca8b808f0c59b51744669b683"
REFERENCE_EXECUTION_FILE_SHA256 = "2a435b7846d510776d4364deb92846f4e6a142fb0e8a822d0634c9fc0a3de76f"
PAIR_ID = "opaque-provenance-openh264-pair-01"
COMPILE_IMAGE = "forge-openh264-execution:issue226-v1"

FROZEN_PARENT_SHA256 = {
    PARENT_MANIFEST_PATH: "ecdf5ad13996c1f7592f421ede5deb6fea00d42f40c7aabb82e0959f6405bb08",
    "benchmarks/schemas/forge-opaque-provenance-openh264-candidate.schema.json": ("65a685aa330d45df7c78dffe7fe4797dcce6c0803e34ad206fea56468208ad14"),
    "benchmarks/preregistrations/cpp-opaque-provenance-openh264-candidate.md": ("51c1f34f7e6a194ca8e60d95ee9f70233b9a9ddf0dbe5ff3cfa9b26511b95255"),
    "scripts/forge_opaque_provenance_openh264_candidate_gate.py": ("5963e3af5b4630022720a889956e63af65f29f325498e99bfb2036d97f3b379c"),
    "backend/tests/test_forge_opaque_provenance_openh264_candidate.py": ("6deba2741b1b3e7dba4aeb5c5694af9807734ce6674a05090d09928aad808a7f"),
    "backend/tests/test_forge_opaque_provenance_openh264_candidate_docker.py": ("2afe2aa3a49c94ecb16a6ee42aeb4a49a2b87f0f3d01096d300e84f023a48f75"),
    "scripts/forge_opaque_provenance_r3_make_execution_runner.py": ("5e955e79a15b00cd97726d1254d9716f5f8f18225c2149078f51a2adba420955"),
    "scripts/forge_opaque_provenance_r3_make_execution_failure_gate.py": ("cd36955c5256fa4376d0b5a4b60c139352ec2f8beb59c9b88741ad681b5bdb06"),
    REFERENCE_EXECUTION_PATH: REFERENCE_EXECUTION_FILE_SHA256,
}


class ProtocolError(RuntimeError):
    """OpenH264 execution 身份、授权、预算或冻结组件无效。"""


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


def _load_parent_gate(repo_root: Path = REPO_ROOT):
    path = repo_root / "scripts/forge_opaque_provenance_openh264_candidate_gate.py"
    name = "forge_opaque_provenance_openh264_execution_parent"
    existing = sys.modules.get(name)
    if existing is not None and Path(existing.__file__).resolve() == path.resolve():
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ProtocolError("cannot load OpenH264 candidate gate")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"cannot load {label}") from exc
    if not isinstance(value, dict):
        raise ProtocolError(f"{label} must be an object")
    return value


def _parent_manifest(repo_root: Path = REPO_ROOT) -> tuple[dict[str, Any], Any]:
    parent_gate = _load_parent_gate(repo_root)
    parent = parent_gate.load_manifest(repo_root / PARENT_MANIFEST_PATH, repo_root)
    if parent_gate.canonical_sha256(parent) != PARENT_MANIFEST_CANONICAL_SHA256:
        raise ProtocolError("OpenH264 candidate canonical identity drifted")
    if parent["evidence"]["identity_sha256"] != PARENT_EVIDENCE_IDENTITY_SHA256:
        raise ProtocolError("OpenH264 candidate evidence identity drifted")
    return parent, parent_gate


def verify_parent_components(repo_root: Path = REPO_ROOT) -> None:
    actual = {path: file_sha256(repo_root / path) for path in sorted(FROZEN_PARENT_SHA256)}
    if actual != FROZEN_PARENT_SHA256:
        raise ProtocolError("OpenH264 execution parent components drifted")


def _evidence_identity(
    *,
    case: dict[str, Any],
    provider: dict[str, Any],
    schedule: list[dict[str, Any]],
    repair_packet: dict[str, Any],
) -> str:
    return canonical_sha256(
        {
            "schema_version": "forge-opaque-provenance-openh264-execution-evidence-1.0.0",
            "parent_evidence_identity_sha256": PARENT_EVIDENCE_IDENTITY_SHA256,
            "case": case,
            "provider": provider,
            "schedule": schedule,
            "repair_packet": repair_packet,
            "compile_image": COMPILE_IMAGE,
        }
    )


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    verify_parent_components(repo_root)
    parent, _parent_gate = _parent_manifest(repo_root)
    reference = _load_object(
        repo_root / REFERENCE_EXECUTION_PATH,
        "R3 execution reference policy",
    )
    runtime_path = repo_root / RUNTIME_ADAPTER_PATH
    preregistration_path = repo_root / PREREGISTRATION_PATH
    if not runtime_path.is_file() or not preregistration_path.is_file():
        raise ProtocolError("OpenH264 execution runtime or preregistration is missing")

    case = copy.deepcopy(parent["case"])
    case.update(
        {
            "compile_image": COMPILE_IMAGE,
            "source_subdir": ".",
            "reference_case_id": parent["case"]["case_id"],
        }
    )
    provider = copy.deepcopy(reference["provider"])
    provider["status"] = "active_authorized"
    schedule = [
        {
            "pair_id": PAIR_ID,
            "order": 1,
            "case_id": case["case_id"],
            "arm_order": ["baseline", "treatment"],
            "state_matched": True,
            "treatment_exposure_only": "repair_packet",
            "shared_measurement_policy": "openh264_bounded_make_with_r0_observability_v1",
        }
    ]
    runtime_parity = copy.deepcopy(reference["runtime_parity"])
    runtime_parity["action_surface"] = {
        "direct_executables": ["make", "gmake"],
        "build_directory": case["build_directory"],
        "target": case["target"],
        "jobs": copy.deepcopy(parent["runtime_parity"]["jobs"]),
        "artifact_stage": copy.deepcopy(parent["runtime_parity"]["artifact_stage"]),
    }
    repair_packet = copy.deepcopy(parent["repair_packet"])
    evidence_identity = _evidence_identity(
        case=case,
        provider=provider,
        schedule=schedule,
        repair_packet=repair_packet,
    )
    evidence_root = "/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-openh264-execution-v1"
    return {
        "$schema": "../schemas/forge-opaque-provenance-openh264-execution.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "authorization": {
            "issue_url": ISSUE_URL,
            "checkpoint_creation_authorized": True,
            "reachability_request_authorized": True,
            "provider_calls_authorized": True,
            "formal_attempts_authorized": True,
            "pair_collection_authorized": True,
            "credential_read_authorized": True,
            "model_creation_authorized": True,
            "docker_execution_authorized": True,
            "evidence_write_authorized": True,
            "model_tokens_authorized": 245_000,
        },
        "parent": {
            "manifest_path": PARENT_MANIFEST_PATH,
            "schema_version": parent["schema_version"],
            "canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
            "file_sha256": FROZEN_PARENT_SHA256[PARENT_MANIFEST_PATH],
            "evidence_identity_sha256": PARENT_EVIDENCE_IDENTITY_SHA256,
            "authorization_baseline_commit": AUTHORIZATION_BASELINE_COMMIT,
            "release_revision_policy": "descendant-compatible",
        },
        "case": case,
        "provider": provider,
        "checkpoint": {
            **copy.deepcopy(reference["checkpoint"]),
            "source_gate": "issue-224-openh264-lifecycle-zero-provider",
        },
        "continuation": copy.deepcopy(reference["continuation"]),
        "schedule": schedule,
        "schedule_sha256": canonical_sha256(schedule),
        "repair_packet": repair_packet,
        "budget": copy.deepcopy(reference["budget"]),
        "runtime_parity": runtime_parity,
        "r0_observability": copy.deepcopy(reference["r0_observability"]),
        "dependency_fixture": {
            **copy.deepcopy(parent["lifecycle_fixture"]),
            "compile_image": COMPILE_IMAGE,
            "preparation_container_name": "forge-openh264-issue226-image-prep",
            "docker_label": "forge.opaque_provenance.issue226",
            "prepare_once": True,
            "cleanup_required": True,
        },
        "evidence": {
            "schema_version": "forge-opaque-provenance-openh264-execution-evidence-1.0.0",
            "directory": evidence_root,
            "checkpoint_manifest": f"checkpoints/{PAIR_ID}/checkpoint.json",
            "parent_ledger": f"checkpoints/{PAIR_ID}/parent/events.jsonl",
            "pair_ledger": f"pairs/{PAIR_ID}/events.jsonl",
            "arm_ledger_directory": f"pairs/{PAIR_ID}/arms",
            "reachability_marker": "markers/reachability.json",
            "dependency_fixture_marker": "markers/dependency-fixture.json",
            "pair_marker": "markers/pair.json",
            "reachability_report": "reports/reachability.json",
            "dependency_fixture_report": "reports/dependency-fixture.json",
            "dependency_fixture_cleanup_report": "reports/dependency-fixture-cleanup.json",
            "canary_report": "reports/canary.json",
            "append_only": True,
            "status": "authorized_not_created",
            "zero_provider_preflight_writes_evidence": False,
            "identity_sha256": evidence_identity,
        },
        "execution": {
            **copy.deepcopy(reference["execution"]),
            "pair_marker": "markers/pair.json",
            "parent_ledger": f"checkpoints/{PAIR_ID}/parent/events.jsonl",
            "arm_ledger_directory": f"pairs/{PAIR_ID}/arms",
            "report_schema_version": "forge-opaque-provenance-openh264-report-1.0.0",
            "report_document_type": "forge_opaque_provenance_openh264_report",
        },
        "stopping": copy.deepcopy(reference["stopping"]),
        "opportunities": {
            **copy.deepcopy(reference["opportunities"]),
            "required_order": ["reachability", PAIR_ID],
        },
        "analysis": {
            **copy.deepcopy(parent["analysis"]),
            "purpose": "independent_openh264_make_conversion_replication",
            "unit_of_analysis": "single_state_matched_make_pair",
            "p_value_computed": False,
        },
        "preflight": {
            **copy.deepcopy(reference["preflight"]),
            "authorization_baseline_commit": AUTHORIZATION_BASELINE_COMMIT,
            "require_empty_dependency_fixture": True,
            "require_full_agent_construction_gate": True,
        },
        "preregistration": {
            "path": PREREGISTRATION_PATH,
            "file_sha256": file_sha256(preregistration_path),
        },
        "runtime_adapter": {
            "path": RUNTIME_ADAPTER_PATH,
            "file_sha256": file_sha256(runtime_path),
            "derived_from_path": "scripts/forge_opaque_provenance_r3_make_execution_runner.py",
            "derived_from_sha256": FROZEN_PARENT_SHA256["scripts/forge_opaque_provenance_r3_make_execution_runner.py"],
            "commands": ["validate", "preflight", "reachability", "pair"],
            "corrected_runtime_bindings_required": True,
            "dependency_fixture_cleanup_required": True,
        },
        "frozen_parent_components": copy.deepcopy(FROZEN_PARENT_SHA256),
    }


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if not isinstance(value, dict) or value != generate_manifest(repo_root):
        raise ProtocolError("OpenH264 execution manifest drifted")
    authorization = value["authorization"]
    if not all(current is True for key, current in authorization.items() if key.endswith("_authorized") and key != "model_tokens_authorized"):
        raise ProtocolError("OpenH264 execution authorization is incomplete")
    if authorization["model_tokens_authorized"] != 245_000:
        raise ProtocolError("OpenH264 execution token authorization drifted")
    if value["evidence"]["status"] != "authorized_not_created":
        raise ProtocolError("OpenH264 execution evidence status drifted")
    return value


def load_manifest(
    path: Path = DEFAULT_MANIFEST,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    return validate_manifest(_load_object(path, "OpenH264 execution manifest"), repo_root)


def verify_frozen_components(
    manifest: dict[str, Any],
    repo_root: Path = REPO_ROOT,
) -> None:
    validate_manifest(manifest, repo_root)
    verify_parent_components(repo_root)


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    frozen = manifest or generate_manifest()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": ("https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-opaque-provenance-openh264-execution.schema.json"),
        "title": "Forge opaque provenance OpenH264 execution amendment",
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
