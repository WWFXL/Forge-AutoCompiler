#!/usr/bin/env python3
"""Validate the runnable Forge C/C++ pilot v4 manifest."""

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

SCHEMA_VERSION = "4.0.0"
BASELINE_COMMIT = "1e4bad22117ad01058310a8625925e7801a8eff2"
REVISION_POLICY = "baseline_ancestor_with_frozen_components"
CONTROL_PLANE_TOPOLOGY = "compose-dood"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

COMPONENT_PATHS = {
    "backend/packages/harness/deerflow/agents/lead_agent/agent.py",
    "backend/packages/harness/deerflow/agents/lead_agent/prompt.py",
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
    "scripts/forge_benchmark.py",
    "scripts/forge_benchmark_v4.py",
    "scripts/forge_benchmark_runner.py",
    "benchmarks/schemas/forge-cpp-benchmark-v4.schema.json",
}


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
        v1._fail(path, "must contain exactly the required v4 frozen artifact hashes")
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
            "model",
            "runtime",
            "conditions",
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
            "must be false for the runnable v4 pilot",
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
            "must bind the Issue #24/#25/#26 fixed implementation baseline",
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

    model = v1._as_object(v1._required(manifest, "model", "manifest"), "manifest.model")
    if model.get("endpoint") != "https://richlab-api-x.choosefire.com/v1":
        v1._fail("manifest.model.endpoint", "must use the frozen pilot endpoint")
    if model.get("roles") != {"lead": "gpt-5.6-sol", "compiler": "gpt-5.6-sol"}:
        v1._fail("manifest.model.roles", "must use gpt-5.6-sol for both roles")
    if model.get("request_timeout_seconds") != 120 or model.get("max_retries") != 0:
        v1._fail("manifest.model", "must freeze a 120-second timeout and zero retries")

    compatibility_manifest = copy.deepcopy(manifest)
    compatibility_manifest["schema_version"] = v1.SCHEMA_VERSION
    compatibility_manifest["scope"]["instrumentation_blocker"] = True
    compatibility_manifest["forge"].pop("revision_policy")
    compatibility_manifest["forge"]["component_sha256"] = {path: forge["component_sha256"][path] for path in v1._COMPONENT_PATHS}
    compatibility_manifest["runtime"].pop("control_plane_topology")
    compatibility_manifest["protocol_artifact_sha256"] = {
        "scripts/forge_benchmark.py": manifest["protocol_artifact_sha256"]["scripts/forge_benchmark.py"],
        "benchmarks/schemas/forge-cpp-benchmark-v1.schema.json": manifest["protocol_artifact_sha256"]["benchmarks/schemas/forge-cpp-benchmark-v4.schema.json"],
    }
    v1.validate_manifest(compatibility_manifest)
    if manifest["benchmark"]["id"] != "forge-cpp-clean-replay-pilot-v4":
        v1._fail("manifest.benchmark.id", "must identify the v4 clean-replay pilot")
    if manifest["conditions"][0]["repetitions"] != 1:
        v1._fail("manifest.conditions[0].repetitions", "must be 1 for the five-case pilot")
    return manifest


def validate_manifest(document: Any) -> dict[str, Any]:
    """Validate a v4 manifest without reading repository files."""
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


def verify_frozen_components(manifest: dict[str, Any], repo_root: Path) -> None:
    """Verify the v4 runtime and protocol files against the current clean tree."""
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
        help="validate and hash a runnable v4 benchmark manifest",
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
