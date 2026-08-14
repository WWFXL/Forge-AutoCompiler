#!/usr/bin/env python3
"""生成并校验未授权 verifier-driven repair pilot runtime identity。"""

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
REPOSITORY_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", SCRIPT_ROOT.parent)).resolve()
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_verifier_repair_runtime as repair_runtime  # noqa: E402

SCHEMA_VERSION = "verifier-driven-repair-pilot-runtime-1.0.0"
BASE_COMMIT = "97f252b414a6f2acbac694b116ed75acef6ac988"
DESIGN_SHA256 = "c20d767253dd2a5f0fbba7e6aebfccd5b6ac0f94c3f417dddccd3b498439b420"
MODEL_SOURCE_SHA256 = "31e48e14e32113a556d44f6fa62cd98235acc884baf8a98240410e513a093f1e"

DEFAULT_DESIGN = (
    REPOSITORY_ROOT
    / "benchmarks"
    / "preregistrations"
    / "cpp-verifier-driven-repair-pilot-v1.json"
)
DEFAULT_CASE_PROTOCOL = (
    REPOSITORY_ROOT / "benchmarks" / "preregistrations" / "cpp-formal-v1-cases.json"
)
DEFAULT_MODEL_SOURCE = (
    REPOSITORY_ROOT / "benchmarks" / "manifests" / "cpp-formal-timeout-calibration.json"
)
DEFAULT_MANIFEST = (
    REPOSITORY_ROOT
    / "benchmarks"
    / "manifests"
    / "cpp-verifier-repair-pilot-runtime-candidate.json"
)
DEFAULT_SCHEMA = (
    REPOSITORY_ROOT
    / "benchmarks"
    / "schemas"
    / "forge-verifier-repair-pilot-runtime-v1.schema.json"
)
DEFAULT_PACKET_SCHEMA = (
    REPOSITORY_ROOT
    / "benchmarks"
    / "schemas"
    / "forge-verifier-repair-packet-v1.schema.json"
)

IMPLEMENTATION_PATHS = {
    "benchmarks/schemas/forge-verifier-repair-packet-v1.schema.json",
    "scripts/forge_verifier_repair_runtime.py",
    "scripts/forge_verifier_repair_pilot_protocol.py",
    "scripts/forge_verifier_repair_pilot_runner.py",
    "scripts/forge_verifier_repair_pilot_analyzer.py",
}


class ProtocolError(ValueError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"cannot read JSON document: {path}") from exc
    if not isinstance(value, dict):
        raise ProtocolError(f"JSON document must be an object: {path}")
    return value


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_paths(repo_root: Path, paths: set[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative_path in sorted(paths):
        path = repo_root / relative_path
        if not path.is_file():
            raise ProtocolError(f"implementation component is missing: {relative_path}")
        hashes[relative_path] = _file_sha256(path)
    return hashes


def _parents(
    design: dict[str, Any] | None = None,
    case_protocol: dict[str, Any] | None = None,
    model_source: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    selected_design = design or _load_json(DEFAULT_DESIGN)
    selected_cases = case_protocol or _load_json(DEFAULT_CASE_PROTOCOL)
    selected_models = model_source or _load_json(DEFAULT_MODEL_SOURCE)
    if _file_sha256(DEFAULT_DESIGN) != DESIGN_SHA256:
        raise ProtocolError("verifier-driven repair design SHA-256 does not match")
    if _file_sha256(DEFAULT_MODEL_SOURCE) != MODEL_SOURCE_SHA256:
        raise ProtocolError("model source SHA-256 does not match")
    if (
        selected_design.get("protocolization", {}).get("collection_authorized")
        is not False
    ):
        raise ProtocolError("parent design must remain collection_authorized=false")
    return selected_design, selected_cases, selected_models


def _selected_cases(
    design: dict[str, Any], case_protocol: dict[str, Any]
) -> list[dict[str, Any]]:
    source_by_id = {case["id"]: case for case in case_protocol.get("cases", [])}
    selected: list[dict[str, Any]] = []
    for frozen in design["case_selection"]["cases"]:
        source = source_by_id.get(frozen["id"])
        if source is None:
            raise ProtocolError(
                f"selected case is missing from formal-v1: {frozen['id']}"
            )
        artifact = source["artifact_oracle"]["required_artifacts"][0]
        if (
            source["repository_url"] != frozen["repository_url"]
            or source["commit"] != frozen["commit"]
            or source["build_system"] != frozen["build_system"]
            or artifact["staged_relative_path"] != frozen["required_artifact"]
        ):
            raise ProtocolError(f"selected case drifted from formal-v1: {frozen['id']}")
        selected.append(copy.deepcopy(source))
    return selected


def _model_profiles(design: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    profiles = source.get("model_profiles", {})
    selected: dict[str, Any] = {}
    for condition in design["provider_conditions"]:
        profile = profiles.get(condition["id"])
        if not isinstance(profile, dict):
            raise ProtocolError(f"model profile is missing: {condition['id']}")
        if set(profile.get("roles", {}).values()) != {condition["model"]}:
            raise ProtocolError(f"model profile identity drifted: {condition['id']}")
        selected[condition["id"]] = copy.deepcopy(profile)
    return selected


def generate_manifest(
    repo_root: Path = REPOSITORY_ROOT,
    *,
    design: dict[str, Any] | None = None,
    case_protocol: dict[str, Any] | None = None,
    model_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    design, case_protocol, model_source = _parents(design, case_protocol, model_source)
    packet_schema = repair_runtime.repair_packet_schema()
    return {
        "$schema": "../schemas/forge-verifier-repair-pilot-runtime-v1.schema.json",
        "schema_version": SCHEMA_VERSION,
        "benchmark": {
            "id": "forge-cpp-verifier-driven-repair-pilot-runtime-candidate",
            "purpose": "freeze a baseline-versus-structured-verifier-feedback paired pilot runtime without authorizing collection",
            "languages": ["C", "C++"],
        },
        "protocolization": {
            "issue": 125,
            "base_commit": BASE_COMMIT,
            "design_parent": {
                "path": "benchmarks/preregistrations/cpp-verifier-driven-repair-pilot-v1.json",
                "sha256": DESIGN_SHA256,
            },
            "model_source": {
                "path": "benchmarks/manifests/cpp-formal-timeout-calibration.json",
                "sha256": MODEL_SOURCE_SHA256,
            },
            "runtime_implementation_authorized": True,
            "collection_authorized": False,
            "provider_canary_forbidden": True,
            "physical_attempt_creation_forbidden": True,
            "model_execution_forbidden": True,
            "batch_execution_forbidden": True,
        },
        "runtime": {
            "adapter": "scripts/forge_verifier_repair_runtime.py",
            "packet_schema_version": repair_runtime.PACKET_SCHEMA_VERSION,
            "sidecar_schema_version": repair_runtime.SIDECAR_SCHEMA_VERSION,
            "baseline_byte_identity_required": True,
            "shared_compile_components_modified": False,
            "compile_image": model_source["runtime"]["compile_image"],
            "image_id": model_source["runtime"]["image_id"],
            "control_plane_topology": "compose-dood",
            "docker_daemon_provider": "ubuntu-native",
        },
        "repair_packet": {
            "schema_path": "benchmarks/schemas/forge-verifier-repair-packet-v1.schema.json",
            "schema_sha256": hashlib.sha256(
                (json.dumps(packet_schema, ensure_ascii=False, indent=2) + "\n").encode(
                    "utf-8"
                )
            ).hexdigest(),
            "actionable_classifications": sorted(repair_runtime.REPAIR_GOALS),
            "repair_goals": dict(sorted(repair_runtime.REPAIR_GOALS.items())),
            "forbidden_content": [
                "stdout",
                "stderr",
                "prompt",
                "model_body",
                "credential",
                "host_path",
                "generated_repair_command",
            ],
        },
        "cases": _selected_cases(design, case_protocol),
        "model_profiles": _model_profiles(design, model_source),
        "treatments": copy.deepcopy(design["treatments"]),
        "pilot_schedule": copy.deepcopy(design["pilot_schedule"]),
        "budget": copy.deepcopy(design["budget_proposal"]),
        "outcomes": copy.deepcopy(design["outcomes"]),
        "fidelity_gate": {
            "statuses": ["passed", "not_exposed", "failed"],
            "baseline_packet_count": 0,
            "treatment_requires_packet_for_each_actionable_submit": True,
            "paired_analysis_requires_both_arms": True,
            "p_value_forbidden": True,
            "model_ranking_forbidden": True,
        },
        "implementation_sha256": _hash_paths(repo_root, IMPLEMENTATION_PATHS),
    }


def validate_manifest(
    document: Any, repo_root: Path = REPOSITORY_ROOT
) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ProtocolError("runtime candidate manifest must be an object")
    expected = generate_manifest(repo_root)
    if document != expected:
        raise ProtocolError(
            "runtime candidate manifest does not match the frozen implementation"
        )
    if (
        len(document["pilot_schedule"]) != 12
        or len({slot["pair_id"] for slot in document["pilot_schedule"]}) != 6
    ):
        raise ProtocolError(
            "runtime candidate schedule must contain 12 slots and 6 pairs"
        )
    if document["protocolization"]["collection_authorized"] is not False:
        raise ProtocolError("runtime candidate must not authorize collection")
    return document


def manifest_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-verifier-repair-pilot-runtime-v1.schema.json",
        "title": "Forge verifier-driven repair pilot runtime candidate",
        "const": generate_manifest(),
    }


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def generate_artifacts() -> dict[str, Any]:
    _write_json(DEFAULT_PACKET_SCHEMA, repair_runtime.repair_packet_schema())
    manifest = generate_manifest()
    _write_json(DEFAULT_MANIFEST, manifest)
    _write_json(DEFAULT_SCHEMA, manifest_schema())
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("generate")
    validate = subparsers.add_parser("validate-manifest")
    validate.add_argument("manifest", type=Path, nargs="?", default=DEFAULT_MANIFEST)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = (
            generate_artifacts()
            if args.command == "generate"
            else validate_manifest(_load_json(args.manifest))
        )
    except (OSError, ProtocolError, repair_runtime.RepairRuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "collection_authorized": False,
                "manifest_sha256": manifest_sha256(manifest),
                "status": "valid",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
