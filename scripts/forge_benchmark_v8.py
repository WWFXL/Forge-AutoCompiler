#!/usr/bin/env python3
"""Validate the runnable Forge C/C++ pilot v8 protocol."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_benchmark as v1  # noqa: E402

SCHEMA_VERSION = "8.0.0"
BASELINE_COMMIT = "54fdf4187f6f6b5fc67b821921331a6af2cfcbb5"
REVISION_POLICY = "baseline_ancestor_with_frozen_components"
CONTROL_PLANE_TOPOLOGY = "compose-dood"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_BUDGETS = {
    "model_turn_limit": 36,
    "graph_recursion_limit": 96,
    "wall_clock_timeout_seconds": 900,
    "post_build_reserve_seconds": 120,
}

COMPONENT_PATHS = {
    "backend/packages/harness/deerflow/agents/lead_agent/agent.py",
    "backend/packages/harness/deerflow/agents/lead_agent/prompt.py",
    "backend/packages/harness/deerflow/agents/middlewares/clarification_middleware.py",
    "backend/packages/harness/deerflow/agents/middlewares/llm_error_handling_middleware.py",
    "backend/packages/harness/deerflow/agents/middlewares/tool_error_handling_middleware.py",
    "backend/packages/harness/deerflow/client.py",
    "backend/packages/harness/deerflow/compile/__init__.py",
    "backend/packages/harness/deerflow/compile/docker_runtime.py",
    "backend/packages/harness/deerflow/compile/evidence.py",
    "backend/packages/harness/deerflow/compile/manager.py",
    "backend/packages/harness/deerflow/compile/operations.py",
    "backend/packages/harness/deerflow/compile/schemas.py",
    "backend/packages/harness/deerflow/models/factory.py",
    "backend/packages/harness/deerflow/subagents/builtins/compiler_agent.py",
    "backend/packages/harness/deerflow/subagents/executor.py",
    "backend/packages/harness/deerflow/tools/bound_compile_tools.py",
    "backend/packages/harness/deerflow/tools/builtins/agent_compile_tools.py",
    "backend/packages/harness/deerflow/tools/builtins/task_tool.py",
    "backend/uv.lock",
    "config.example.yaml",
    "docker/compile/Dockerfile",
    "docker/docker-compose-dev.yaml",
}
PROTOCOL_ARTIFACT_PATHS = {
    "backend/Dockerfile",
    "scripts/forge_benchmark.py",
    "scripts/forge_benchmark_v8.py",
    "scripts/forge_benchmark_runner.py",
    "benchmarks/schemas/forge-cpp-benchmark-v8.schema.json",
}
MODEL_PROFILES = {
    "richlab-gpt-5.5": {
        "endpoint": "https://richlab-api-x.choosefire.com/v1",
        "credential_env": "OpenAI_AK",
        "roles": {"lead": "gpt-5.5", "compiler": "gpt-5.5"},
        "fallback_policy": "forbidden",
        "request_timeout_seconds": 120,
        "max_retries": 0,
    },
    "deepseek-v4-flash": {
        "endpoint": "https://api.deepseek.com",
        "credential_env": "DEEPSEEK_API_KEY",
        "roles": {
            "lead": "deepseek-v4-flash",
            "compiler": "deepseek-v4-flash",
        },
        "fallback_policy": "forbidden",
        "request_timeout_seconds": 120,
        "max_retries": 0,
    },
}
CONDITION_PROFILES = {
    "richlab-gpt-5.5": "richlab-gpt-5.5",
    "deepseek-v4-flash": "deepseek-v4-flash",
}
CASE_IDS = (
    "fmt",
    "hiredis",
    "libcheck",
    "libgit2",
    "sysstat-nondeterministic",
)
COLLECTION_PLAN = tuple(
    {
        "case_id": case_id,
        "condition_id": condition_id,
        "repetition": 1,
    }
    for case_id in CASE_IDS
    for condition_id in CONDITION_PROFILES
)


BenchmarkError = v1.BenchmarkError
load_json_document = v1.load_json_document


def _validate_hash_map(
    value: Any,
    *,
    expected_paths: set[str],
    path: str,
) -> dict[str, Any]:
    hashes = v1._as_object(value, path)
    if set(hashes) != expected_paths:
        v1._fail(path, "must contain exactly the required v8 frozen artifact hashes")
    for relative_path, digest in hashes.items():
        pure_path = PurePosixPath(relative_path)
        if pure_path.is_absolute() or ".." in pure_path.parts or "\\" in relative_path:
            v1._fail(f"{path}.{relative_path}", "must stay inside the repository")
        v1._validate_sha256(digest, f"{path}.{relative_path}")
    return hashes


def _validate_manifest_impl(document: Any) -> dict[str, Any]:
    manifest = v1._as_object(document, "manifest")
    v1._require_exact_keys(
        manifest,
        {
            "schema_version",
            "document_type",
            "manifest_canonicalization",
            "benchmark",
            "scope",
            "forge",
            "protocol_artifact_sha256",
            "model_profiles",
            "runtime",
            "conditions",
            "collection_plan",
            "cases",
        },
        "manifest",
        optional={"$schema"},
    )
    if manifest.get("schema_version") != SCHEMA_VERSION:
        v1._fail("manifest.schema_version", f"unsupported version; expected {SCHEMA_VERSION}")
    v1._scan_for_unsafe_values(manifest)

    scope = v1._as_object(v1._required(manifest, "scope", "manifest"), "manifest.scope")
    if scope.get("instrumentation_blocker") is not False:
        v1._fail(
            "manifest.scope.instrumentation_blocker",
            "must be false for the runnable v8 pilot",
        )

    forge = v1._as_object(v1._required(manifest, "forge", "manifest"), "manifest.forge")
    v1._require_exact_keys(
        forge,
        {"repository_url", "commit_sha", "revision_policy", "component_sha256"},
        "manifest.forge",
    )
    if forge.get("commit_sha") != BASELINE_COMMIT:
        v1._fail(
            "manifest.forge.commit_sha",
            "must bind the reviewed dual-provider canary baseline at main@54fdf418",
        )
    if forge.get("revision_policy") != REVISION_POLICY:
        v1._fail(
            "manifest.forge.revision_policy",
            f"must be {REVISION_POLICY!r}",
        )
    _validate_hash_map(
        v1._required(forge, "component_sha256", "manifest.forge"),
        expected_paths=COMPONENT_PATHS,
        path="manifest.forge.component_sha256",
    )
    _validate_hash_map(
        v1._required(manifest, "protocol_artifact_sha256", "manifest"),
        expected_paths=PROTOCOL_ARTIFACT_PATHS,
        path="manifest.protocol_artifact_sha256",
    )

    runtime = v1._as_object(v1._required(manifest, "runtime", "manifest"), "manifest.runtime")
    if runtime.get("control_plane_topology") != CONTROL_PLANE_TOPOLOGY:
        v1._fail(
            "manifest.runtime.control_plane_topology",
            f"must be {CONTROL_PLANE_TOPOLOGY!r}",
        )
    for key, expected_value in RUNTIME_BUDGETS.items():
        if runtime.get(key) != expected_value:
            v1._fail(
                f"manifest.runtime.{key}",
                f"must freeze the v8 value {expected_value}",
            )
    if runtime["post_build_reserve_seconds"] >= runtime["wall_clock_timeout_seconds"]:
        v1._fail(
            "manifest.runtime.post_build_reserve_seconds",
            "must be smaller than wall_clock_timeout_seconds",
        )

    model_profiles = v1._as_object(
        v1._required(manifest, "model_profiles", "manifest"),
        "manifest.model_profiles",
    )
    if model_profiles != MODEL_PROFILES:
        v1._fail(
            "manifest.model_profiles",
            "must freeze the independent RichLab and DeepSeek profiles",
        )

    conditions = v1._required(manifest, "conditions", "manifest")
    if not isinstance(conditions, list):
        v1._fail("manifest.conditions", "must be an array")
    if len(conditions) != len(CONDITION_PROFILES):
        v1._fail("manifest.conditions", "must contain exactly two provider conditions")
    observed_conditions: dict[str, str] = {}
    for index, raw_condition in enumerate(conditions):
        path = f"manifest.conditions[{index}]"
        condition = v1._as_object(raw_condition, path)
        v1._require_exact_keys(
            condition,
            {
                "id",
                "model_profile",
                "memory_enabled",
                "skills_enabled",
                "repetitions",
                "acceptance_gate",
            },
            path,
        )
        condition_id = condition.get("id")
        model_profile = condition.get("model_profile")
        if not isinstance(condition_id, str) or not isinstance(model_profile, str):
            v1._fail(path, "must name a condition and model profile")
        if condition_id in observed_conditions:
            v1._fail(f"{path}.id", "must be unique")
        observed_conditions[condition_id] = model_profile
        if condition.get("memory_enabled") is not False or condition.get("skills_enabled") is not False or condition.get("repetitions") != 1 or condition.get("acceptance_gate") != "clean_replay":
            v1._fail(path, "must freeze Memory/Skills off, one slot, and clean replay")
    if observed_conditions != CONDITION_PROFILES:
        v1._fail(
            "manifest.conditions",
            "must map each condition to its same-named frozen model profile",
        )

    collection_plan = v1._required(manifest, "collection_plan", "manifest")
    if not isinstance(collection_plan, list):
        v1._fail("manifest.collection_plan", "must be an array")
    if collection_plan != list(COLLECTION_PLAN):
        v1._fail(
            "manifest.collection_plan",
            "must freeze the ten non-replaceable slots in interleaved order",
        )

    compatibility_manifest = _compatibility_manifest(manifest)
    v1.validate_manifest(compatibility_manifest)
    if manifest["benchmark"]["id"] != "forge-cpp-clean-replay-pilot-v8":
        v1._fail("manifest.benchmark.id", "must identify the v8 clean-replay pilot")
    if tuple(case["id"] for case in manifest["cases"]) != CASE_IDS:
        v1._fail("manifest.cases", "must retain the ordered five-case v7 calibration set")
    return manifest


def _compatibility_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    forge = manifest["forge"]
    compatibility_manifest = copy.deepcopy(manifest)
    compatibility_manifest["schema_version"] = v1.SCHEMA_VERSION
    compatibility_manifest["model"] = copy.deepcopy(compatibility_manifest["model_profiles"]["richlab-gpt-5.5"])
    compatibility_manifest.pop("model_profiles")
    compatibility_manifest.pop("collection_plan")
    compatibility_manifest["conditions"] = [
        {
            "id": "baseline",
            "memory_enabled": False,
            "skills_enabled": False,
            "repetitions": 1,
            "acceptance_gate": "clean_replay",
        }
    ]
    compatibility_manifest["scope"]["instrumentation_blocker"] = True
    compatibility_manifest["forge"].pop("revision_policy")
    compatibility_manifest["forge"]["component_sha256"] = {path: forge["component_sha256"][path] for path in v1._COMPONENT_PATHS}
    compatibility_manifest["runtime"].pop("control_plane_topology")
    compatibility_manifest["runtime"]["compiler_max_turns"] = compatibility_manifest["runtime"].pop("model_turn_limit")
    compatibility_manifest["runtime"]["subagent_timeout_seconds"] = compatibility_manifest["runtime"].pop("wall_clock_timeout_seconds")
    compatibility_manifest["runtime"].pop("graph_recursion_limit")
    compatibility_manifest["runtime"].pop("post_build_reserve_seconds")
    compatibility_manifest["protocol_artifact_sha256"] = {
        "scripts/forge_benchmark.py": manifest["protocol_artifact_sha256"]["scripts/forge_benchmark.py"],
        "benchmarks/schemas/forge-cpp-benchmark-v1.schema.json": manifest["protocol_artifact_sha256"]["benchmarks/schemas/forge-cpp-benchmark-v8.schema.json"],
    }
    return compatibility_manifest


def validate_manifest(document: Any) -> dict[str, Any]:
    """Validate a v8 manifest without reading repository files."""
    try:
        return _validate_manifest_impl(document)
    except BenchmarkError:
        raise
    except (AttributeError, OverflowError, TypeError, ValueError) as exc:
        raise BenchmarkError("manifest: contains a malformed value") from exc


def canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    validate_manifest(manifest)
    try:
        return json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise BenchmarkError("manifest: cannot be represented as canonical JSON") from exc


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()


def _validate_build_identity(
    capabilities: Any,
    selected: Any,
    executed: Any,
    *,
    path: str,
) -> tuple[list[str], str | None, str | None]:
    if not isinstance(capabilities, list) or len(capabilities) > len(v1._BUILD_SYSTEMS) or len(set(capabilities)) != len(capabilities) or any(value not in v1._BUILD_SYSTEMS for value in capabilities):
        v1._fail(f"{path}.build_system_capabilities", "must be a unique supported build-system list")
    for key, value in (("selected_build_system", selected), ("executed_build_system", executed)):
        if value is not None and value not in v1._BUILD_SYSTEMS:
            v1._fail(f"{path}.{key}", "must be null or a supported build system")
    if selected is not None and selected not in capabilities:
        v1._fail(f"{path}.selected_build_system", "must belong to build_system_capabilities")
    return capabilities, selected, executed


def validate_run_record(document: Any) -> dict[str, Any]:
    """Validate a v8 run record with explicit build-system identity facts."""
    try:
        record = v1._as_object(document, "run_record")
        if record.get("schema_version") != SCHEMA_VERSION:
            v1._fail("run_record.schema_version", f"must be {SCHEMA_VERSION!r}")
        source = v1._as_object(v1._required(record, "source", "run_record"), "run_record.source")
        v1._require_exact_keys(
            source,
            {
                "session_id",
                "run_id",
                "repository_url",
                "commit_sha",
                "build_system",
                "build_system_capabilities",
                "selected_build_system",
                "executed_build_system",
                "image_id",
            },
            "run_record.source",
        )
        _capabilities, selected, executed = _validate_build_identity(
            source["build_system_capabilities"],
            source["selected_build_system"],
            source["executed_build_system"],
            path="run_record.source",
        )
        if source["build_system"] != executed:
            v1._fail("run_record.source.build_system", "must equal the explicit executed build system")
        outcome = v1._as_object(v1._required(record, "outcome", "run_record"), "run_record.outcome")
        if outcome.get("candidate_status") == "pass" and (selected is None or executed is None or executed != selected):
            v1._fail("run_record.source", "candidate pass requires matching selected and executed build-system evidence")

        compatibility_record = copy.deepcopy(record)
        compatibility_record["schema_version"] = v1.SCHEMA_VERSION
        compatibility_source = compatibility_record["source"]
        compatibility_source.pop("build_system_capabilities")
        compatibility_source.pop("selected_build_system")
        compatibility_source.pop("executed_build_system")
        v1.validate_run_record(compatibility_record)
        return record
    except BenchmarkError:
        raise
    except (AttributeError, OverflowError, TypeError, ValueError) as exc:
        raise BenchmarkError("run_record: contains a malformed value") from exc


def build_run_record(
    *,
    manifest: dict[str, Any],
    case_id: str,
    condition_id: str,
    repetition: int,
    session: dict[str, Any],
    workflow_events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a v8 record without inferring observed identity from the manifest."""
    validate_manifest(manifest)
    capabilities = copy.deepcopy(session.get("build_system_capabilities", []))
    selected = session.get("selected_build_system")
    executed = session.get("executed_build_system")
    _validate_build_identity(capabilities, selected, executed, path="session")
    case = next((candidate for candidate in manifest["cases"] if candidate["id"] == case_id), None)
    if case is None:
        v1._fail("record.case_id", "does not name a manifest case")
    if not any(condition["id"] == condition_id for condition in manifest["conditions"]):
        v1._fail("record.condition", "does not name a manifest condition")
    if selected is not None and selected != case["build_system"]:
        v1._fail("session.selected_build_system", "does not match the selected manifest case")

    compatibility_session = copy.deepcopy(session)
    compatibility_session["build_system"] = selected
    record = v1.build_run_record(
        manifest=_compatibility_manifest(manifest),
        case_id=case_id,
        condition_id="baseline",
        repetition=repetition,
        session=compatibility_session,
        workflow_events=workflow_events,
    )
    record["schema_version"] = SCHEMA_VERSION
    record["manifest_sha256"] = manifest_sha256(manifest)
    record["condition"] = condition_id
    record["source"].update(
        {
            "build_system": executed,
            "build_system_capabilities": capabilities,
            "selected_build_system": selected,
            "executed_build_system": executed,
        }
    )
    return validate_run_record(record)


def verify_frozen_components(manifest: dict[str, Any], repo_root: Path) -> None:
    """Verify the v8 runtime and protocol files against the current clean tree."""
    validate_manifest(manifest)
    try:
        resolved_root = repo_root.resolve(strict=True)
    except OSError as exc:
        raise BenchmarkError("frozen_components: repository root is unavailable") from exc
    if not resolved_root.is_dir():
        raise BenchmarkError("frozen_components: repository root must be a directory")

    for path_prefix, hashes in (
        ("manifest.forge.component_sha256", manifest["forge"]["component_sha256"]),
        ("manifest.protocol_artifact_sha256", manifest["protocol_artifact_sha256"]),
    ):
        for relative_path, expected_sha256 in hashes.items():
            candidate = resolved_root
            for part in PurePosixPath(relative_path).parts:
                candidate /= part
                if candidate.is_symlink():
                    v1._fail(f"{path_prefix}.{relative_path}", "must reference an ordinary file, not a symlink")
            if not candidate.is_file():
                v1._fail(f"{path_prefix}.{relative_path}", "references a missing ordinary file")
            try:
                resolved_candidate = candidate.resolve(strict=True)
                resolved_candidate.relative_to(resolved_root)
                actual_sha256 = hashlib.sha256(resolved_candidate.read_bytes()).hexdigest()
            except (OSError, ValueError) as exc:
                raise BenchmarkError(f"{path_prefix}.{relative_path}: could not be read safely") from exc
            if actual_sha256 != expected_sha256:
                v1._fail(f"{path_prefix}.{relative_path}", "does not match the current repository file")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser(
        "validate-manifest",
        help="validate and hash a runnable v8 benchmark manifest",
    )
    validate_parser.add_argument("manifest", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        manifest = validate_manifest(load_json_document(args.manifest))
        verify_frozen_components(manifest, REPOSITORY_ROOT)
        print(
            json.dumps(
                {
                    "benchmark_id": manifest["benchmark"]["id"],
                    "cases": len(manifest["cases"]),
                    "manifest_sha256": manifest_sha256(manifest),
                    "status": "valid",
                },
                sort_keys=True,
            )
        )
        return 0
    except (BenchmarkError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
