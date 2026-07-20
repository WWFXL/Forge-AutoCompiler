#!/usr/bin/env python3
"""Validate Forge C/C++ benchmark manifests and record bounded run evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit, urlunsplit


SCHEMA_VERSION = "1.0.0"
MANIFEST_DOCUMENT_TYPE = "manifest"
RUN_RECORD_DOCUMENT_TYPE = "run_record"
CANONICAL_JSON_ALGORITHM = "json-sort-keys-compact-utf8"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_COMMIT_SHA_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_IDENTIFIER_RE = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")
_ENV_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SESSION_ID_RE = re.compile(r"[0-9a-f]{12}")
_RUN_ID_RE = re.compile(r"(?:[0-9a-f]{12,64}|[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,})")
_HOST_PATH_RE = re.compile(
    r"(?i)^(?:[A-Z]:[\\/]|\\\\|/mnt/[A-Z](?:/|$)|/(?:home|Users|root|tmp|var|etc)(?:/|$))"
)
_SECRET_VALUE_RE = re.compile(
    r"(?i)(?:sk-[A-Za-z0-9_-]{8,}|bearer\s+[A-Za-z0-9._~-]+|gh[opsu]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [^-]*PRIVATE KEY-----)"
)
_SECRET_KEYS = {
    "access_key",
    "access_token",
    "api_key",
    "api_key_value",
    "credential",
    "credentials",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "token",
}
_LANGUAGES = {"C", "C++"}
_BUILD_SYSTEMS = {"cmake", "make", "autotools"}
_GATE_RESULTS = {"pass", "reject"}
_SESSION_STATUSES = {
    "created",
    "ready",
    "source_ready",
    "inspected",
    "replay_verifying",
    "verified",
    "verification_failed",
    "completed",
    "failed",
    "cancelled",
    "timed_out",
}
_VERIFICATION_STATUSES = {"candidate_ready", "passed", "failed"}
_RAW_CANDIDATE_STATUSES = {"passed", "failed"}
_RAW_REPLAY_STATUSES = {
    "pending",
    "running",
    "passed",
    "failed",
    "timed_out",
    "cancelled",
    "not_run",
}
_REPLAY_FAILURE_CLASSIFICATIONS = {
    "artifact_set_mismatch",
    "cancelled",
    "cleanup_failed",
    "image_identity_unavailable",
    "internal_error",
    "recipe_execution_failed",
    "recipe_snapshot_mismatch",
    "session_terminated",
    "sha256_mismatch",
    "size_mismatch",
    "smoke_mismatch",
    "timeout",
    "type_mismatch",
}
_ARTIFACT_TYPES = {"executable", "shared_library", "object", "static_library"}
_COMPONENT_PATHS = {
    "backend/packages/harness/deerflow/subagents/builtins/compiler_agent.py",
    "backend/packages/harness/deerflow/agents/lead_agent/prompt.py",
    "backend/packages/harness/deerflow/tools/bound_compile_tools.py",
    "backend/packages/harness/deerflow/tools/builtins/agent_compile_tools.py",
    "docker/compile/Dockerfile",
    "config.example.yaml",
    "backend/uv.lock",
}
_PROTOCOL_ARTIFACT_PATHS = {
    "scripts/forge_benchmark.py",
    "benchmarks/schemas/forge-cpp-benchmark-v1.schema.json",
}


class BenchmarkError(ValueError):
    """A safe, user-facing benchmark validation error."""


def _fail(path: str, message: str) -> None:
    raise BenchmarkError(f"{path}: {message}")


def _as_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    return value


def _as_array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(path, "must be an array")
    return value


def _required(container: dict[str, Any], key: str, path: str) -> Any:
    if key not in container:
        _fail(path, f"missing required field {key!r}")
    return container[key]


def _require_exact_keys(
    container: dict[str, Any],
    required: set[str],
    path: str,
    *,
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    missing = required - set(container)
    extra = set(container) - required - optional
    if missing:
        _fail(path, f"missing required fields: {', '.join(sorted(missing))}")
    if extra:
        _fail(path, f"unsupported fields: {', '.join(sorted(extra))}")


def _required_string(container: dict[str, Any], key: str, path: str) -> str:
    value = _required(container, key, path)
    if not isinstance(value, str) or not value:
        _fail(f"{path}.{key}", "must be a non-empty string")
    return value


def _required_int(
    container: dict[str, Any], key: str, path: str, *, minimum: int = 0
) -> int:
    value = _required(container, key, path)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(f"{path}.{key}", f"must be an integer >= {minimum}")
    return value


def _validate_identifier(value: str, path: str) -> str:
    if len(value) > 80 or not _IDENTIFIER_RE.fullmatch(value):
        _fail(path, "must be a bounded identifier")
    return value


def _validate_sha256(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        _fail(path, "must be a lowercase 64-character SHA-256")
    return value


def _validate_commit_sha(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _COMMIT_SHA_RE.fullmatch(value):
        _fail(
            path,
            "must be a full lowercase 40- or 64-character commit SHA, not a movable ref",
        )
    return value


def _validate_repo_url(value: Any, path: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in ("\0", "\r", "\n"))
    ):
        _fail(path, "must be a non-empty remote repository URL")
    if len(value) > 2048 or any(character.isspace() for character in value):
        _fail(path, "must be a bounded URL without whitespace")
    if _HOST_PATH_RE.search(value) or value.startswith(("/", "./", "../", "~")):
        _fail(path, "must be a remote repository URL, not a host path")

    parsed = urlsplit(value)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        _fail(path, "must use an HTTPS URL")
    if parsed.username is not None or parsed.password is not None:
        _fail(path, "must not embed credentials")
    if parsed.query or parsed.fragment:
        _fail(path, "must not contain query parameters or fragments")
    try:
        parsed.port
    except ValueError:
        _fail(path, "contains an invalid port")
    if not re.fullmatch(
        r"https://(?![^/?#]*@)[A-Za-z0-9.-]+(?::[0-9]{1,5})?/[A-Za-z0-9._~!$&'()*+,;=:@%/-]+",
        value,
    ):
        _fail(
            path, "contains characters outside the frozen HTTPS repository URL grammar"
        )
    return value


def _canonical_repo_identity(value: str) -> str:
    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    port = parsed.port
    if port is not None and not (
        (scheme == "https" and port == 443)
        or (scheme == "http" and port == 80)
        or (scheme == "ssh" and port == 22)
    ):
        hostname = f"{hostname}:{port}"
    path = parsed.path.rstrip("/")
    if path.lower().endswith(".git"):
        path = path[:-4]
    return urlunsplit((scheme, hostname, path, "", ""))


def _validate_endpoint(value: Any, path: str) -> str:
    if not isinstance(value, str) or value != value.strip() or len(value) > 2048:
        _fail(path, "must be an HTTPS URL ending in /v1")
    parsed = urlsplit(value)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        _fail(path, "must be an HTTPS URL without credentials")
    if parsed.query or parsed.fragment or parsed.path.rstrip("/") != "/v1":
        _fail(path, "must end in /v1 and contain no query or fragment")
    return value


def _scan_for_unsafe_values(value: Any, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                _fail("manifest", "object keys must be strings")
            normalized_key = key.lower()
            secret_key = normalized_key in _SECRET_KEYS or re.search(
                r"(?:^|_)(?:secret|password|token|api_key|access_key|private_key)(?:_|$)",
                normalized_key,
            )
            if secret_key:
                _fail(
                    ".".join(("manifest", *path, key)),
                    "secret-bearing fields are forbidden",
                )
            _scan_for_unsafe_values(child, (*path, key))
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _scan_for_unsafe_values(child, (*path, str(index)))
        return
    if not isinstance(value, str):
        return
    manifest_path = ".".join(("manifest", *path))
    if any(character in value for character in ("\0", "\r", "\n")):
        _fail(manifest_path, "control characters are forbidden")
    if _SECRET_VALUE_RE.search(value):
        _fail(manifest_path, "a credential-like value is forbidden")
    if _HOST_PATH_RE.search(value):
        _fail(manifest_path, "host absolute paths are forbidden")
    if (
        value == ".env"
        or value.startswith(".env.")
        or "/.env" in value.replace("\\", "/")
    ):
        _fail(manifest_path, ".env references are forbidden")


def _validate_component_hashes(forge: dict[str, Any]) -> None:
    hashes = _as_object(
        _required(forge, "component_sha256", "manifest.forge"),
        "manifest.forge.component_sha256",
    )
    if set(hashes) != _COMPONENT_PATHS:
        _fail(
            "manifest.forge.component_sha256",
            "must contain exactly the seven required frozen component hashes",
        )
    for component_path, digest in hashes.items():
        if (
            not isinstance(component_path, str)
            or not component_path
            or component_path.startswith(("/", "\\"))
        ):
            _fail(
                "manifest.forge.component_sha256",
                "component paths must be non-empty repository-relative paths",
            )
        pure_path = PurePosixPath(component_path.replace("\\", "/"))
        if ".." in pure_path.parts or _HOST_PATH_RE.search(component_path):
            _fail(
                f"manifest.forge.component_sha256.{component_path}",
                "component path must stay inside the repository",
            )
        _validate_sha256(digest, f"manifest.forge.component_sha256.{component_path}")


def _validate_model(model: dict[str, Any]) -> None:
    _require_exact_keys(
        model,
        {
            "endpoint",
            "credential_env",
            "roles",
            "fallback_policy",
            "request_timeout_seconds",
            "max_retries",
        },
        "manifest.model",
    )
    _validate_endpoint(
        _required(model, "endpoint", "manifest.model"), "manifest.model.endpoint"
    )
    credential_env = _required_string(model, "credential_env", "manifest.model")
    if not _ENV_NAME_RE.fullmatch(credential_env) or credential_env != "OpenAI_AK":
        _fail(
            "manifest.model.credential_env",
            "must be the environment-variable name 'OpenAI_AK'",
        )
    if _required_string(model, "fallback_policy", "manifest.model") != "forbidden":
        _fail(
            "manifest.model.fallback_policy",
            "must be 'forbidden' for an auditable baseline",
        )
    roles = _as_object(
        _required(model, "roles", "manifest.model"), "manifest.model.roles"
    )
    if set(roles) != {"lead", "compiler"}:
        _fail("manifest.model.roles", "must define exactly lead and compiler")
    for role_name in ("lead", "compiler"):
        role = roles[role_name]
        if (
            not isinstance(role, str)
            or not role
            or len(role) > 160
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:+/@-]*", role)
        ):
            _fail(f"manifest.model.roles.{role_name}", "must be a bounded model token")
    if roles["lead"] != roles["compiler"]:
        _fail(
            "manifest.model.roles",
            "baseline lead and compiler roles must use the same model",
        )
    if (
        _required_int(model, "request_timeout_seconds", "manifest.model", minimum=1)
        > 86400
    ):
        _fail("manifest.model.request_timeout_seconds", "must not exceed 86400")
    if _required_int(model, "max_retries", "manifest.model", minimum=0) > 100:
        _fail("manifest.model.max_retries", "must not exceed 100")


def _validate_runtime(runtime: dict[str, Any]) -> None:
    _require_exact_keys(
        runtime,
        {
            "compile_image",
            "image_id",
            "replay_timeout_seconds",
            "cleanup_timeout_seconds",
            "docker_control_timeout_seconds",
            "compiler_max_turns",
            "subagent_timeout_seconds",
            "max_parallel_runs",
            "backend_processes",
            "network_policy",
            "host",
        },
        "manifest.runtime",
    )
    compile_image = _required_string(runtime, "compile_image", "manifest.runtime")
    if len(compile_image) > 160 or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:+/@-]*", compile_image
    ):
        _fail("manifest.runtime.compile_image", "must be a bounded image token")
    image_id = _required_string(runtime, "image_id", "manifest.runtime")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        _fail("manifest.runtime.image_id", "must be an immutable sha256 image ID")
    maximums = {
        "replay_timeout_seconds": 86400,
        "cleanup_timeout_seconds": 3600,
        "docker_control_timeout_seconds": 3600,
        "compiler_max_turns": 1000,
        "subagent_timeout_seconds": 86400,
        "max_parallel_runs": 1,
        "backend_processes": 1,
    }
    for key, maximum in maximums.items():
        if _required_int(runtime, key, "manifest.runtime", minimum=1) > maximum:
            _fail(f"manifest.runtime.{key}", f"must not exceed {maximum}")
    if runtime["max_parallel_runs"] != 1 or runtime["backend_processes"] != 1:
        _fail(
            "manifest.runtime",
            "pilot runs require one backend process and max_parallel_runs=1",
        )
    network_policy = _as_object(
        _required(runtime, "network_policy", "manifest.runtime"),
        "manifest.runtime.network_policy",
    )
    if network_policy != {
        "network_name": "compile_network_wwf_v1",
        "egress": "enabled_for_clone_and_dependencies",
    }:
        _fail(
            "manifest.runtime.network_policy",
            "must freeze the compile network name and dependency egress policy",
        )
    host = _as_object(
        _required(runtime, "host", "manifest.runtime"), "manifest.runtime.host"
    )
    _require_exact_keys(
        host,
        {
            "wsl_distribution",
            "cpu_count",
            "memory_kib",
            "kernel",
            "architecture",
            "docker_server_version",
        },
        "manifest.runtime.host",
    )
    for key in ("wsl_distribution", "kernel", "architecture", "docker_server_version"):
        _required_string(host, key, "manifest.runtime.host")
    _required_int(host, "cpu_count", "manifest.runtime.host", minimum=1)
    _required_int(host, "memory_kib", "manifest.runtime.host", minimum=1)
    if host["architecture"] not in {"x86_64", "aarch64"}:
        _fail("manifest.runtime.host.architecture", "must be x86_64 or aarch64")
    if not re.fullmatch(
        r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?", host["docker_server_version"]
    ):
        _fail(
            "manifest.runtime.host.docker_server_version",
            "must be a semantic Docker server version",
        )


def _validate_conditions(value: Any) -> set[str]:
    conditions = _as_array(value, "manifest.conditions")
    if len(conditions) != 1:
        _fail("manifest.conditions", "must contain exactly the baseline condition")
    condition_ids: set[str] = set()
    for index, item in enumerate(conditions):
        path = f"manifest.conditions[{index}]"
        condition = _as_object(item, path)
        _require_exact_keys(
            condition,
            {
                "id",
                "memory_enabled",
                "skills_enabled",
                "repetitions",
                "acceptance_gate",
            },
            path,
        )
        condition_id = _validate_identifier(
            _required_string(condition, "id", path), f"{path}.id"
        )
        if condition_id in condition_ids:
            _fail(f"{path}.id", "duplicate condition ID")
        condition_ids.add(condition_id)
        if condition_id != "baseline":
            _fail(f"{path}.id", "must be 'baseline'")
        if (
            condition.get("memory_enabled") is not False
            or condition.get("skills_enabled") is not False
        ):
            _fail(path, "baseline conditions must disable Memory and Skill")
        if _required_int(condition, "repetitions", path, minimum=1) > 1000:
            _fail(f"{path}.repetitions", "must not exceed 1000")
        if _required_string(condition, "acceptance_gate", path) != "clean_replay":
            _fail(f"{path}.acceptance_gate", "must be 'clean_replay'")
    return condition_ids


def _validate_oracle(value: Any, path: str) -> None:
    oracle = _as_object(value, path)
    _require_exact_keys(
        oracle,
        {
            "expected_candidate_status",
            "expected_clean_replay_status",
            "required_artifacts",
        },
        path,
        optional={"expected_replay_failure_classification"},
    )
    for key in ("expected_candidate_status", "expected_clean_replay_status"):
        status = _required_string(oracle, key, path)
        if status not in _GATE_RESULTS:
            _fail(f"{path}.{key}", "must be 'pass' or 'reject'")
    if "expected_replay_failure_classification" in oracle:
        failure_classification = oracle["expected_replay_failure_classification"]
        if (
            failure_classification is not None
            and failure_classification not in _REPLAY_FAILURE_CLASSIFICATIONS
        ):
            _fail(
                f"{path}.expected_replay_failure_classification",
                "must be null or a supported replay failure classification",
            )
    artifacts = _as_array(
        _required(oracle, "required_artifacts", path), f"{path}.required_artifacts"
    )
    if not artifacts:
        _fail(
            f"{path}.required_artifacts", "must contain at least one required artifact"
        )
    observed_artifacts: set[tuple[str, str]] = set()
    for artifact_index, artifact in enumerate(artifacts):
        artifact_path = f"{path}.required_artifacts[{artifact_index}]"
        artifact_object = _as_object(artifact, artifact_path)
        if set(artifact_object) != {"relative_path", "artifact_type"}:
            _fail(artifact_path, "must contain exactly relative_path and artifact_type")
        relative_path = _required_string(
            artifact_object, "relative_path", artifact_path
        )
        pure_path = PurePosixPath(relative_path)
        if (
            pure_path.is_absolute()
            or ".." in pure_path.parts
            or "\\" in relative_path
            or len(relative_path) > 512
        ):
            _fail(
                f"{artifact_path}.relative_path",
                "must be a safe path relative to /artifacts",
            )
        artifact_type = _required_string(
            artifact_object, "artifact_type", artifact_path
        )
        if artifact_type not in _ARTIFACT_TYPES:
            _fail(
                f"{artifact_path}.artifact_type",
                "must be a supported compiled artifact type",
            )
        artifact_key = (relative_path, artifact_type)
        if artifact_key in observed_artifacts:
            _fail(artifact_path, "duplicates an earlier required artifact")
        observed_artifacts.add(artifact_key)


def _validate_constraints(value: Any, path: str) -> None:
    constraints = _as_object(value, path)
    _require_exact_keys(
        constraints,
        {
            "required_system_packages",
            "build_arguments",
            "environment",
            "minimum_replay_delay_seconds",
        },
        path,
    )
    packages = _as_array(
        _required(constraints, "required_system_packages", path),
        f"{path}.required_system_packages",
    )
    if any(
        not isinstance(package, str)
        or not package
        or len(package) > 128
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+-]*", package)
        for package in packages
    ):
        _fail(
            f"{path}.required_system_packages",
            "must contain only non-empty package names",
        )
    if len(set(packages)) != len(packages):
        _fail(
            f"{path}.required_system_packages",
            "must not contain duplicate package names",
        )
    build_arguments = _as_object(
        _required(constraints, "build_arguments", path),
        f"{path}.build_arguments",
    )
    _require_exact_keys(
        build_arguments,
        {"cmake", "configure"},
        f"{path}.build_arguments",
    )
    for build_system in ("cmake", "configure"):
        arguments = _as_array(
            build_arguments[build_system],
            f"{path}.build_arguments.{build_system}",
        )
        if len(arguments) > 64 or any(
            not isinstance(argument, str)
            or not argument
            or len(argument) > 256
            or any(character in argument for character in ("\0", "\r", "\n"))
            for argument in arguments
        ):
            _fail(
                f"{path}.build_arguments.{build_system}",
                "must contain at most 64 bounded argv tokens",
            )
    environment = _as_object(
        _required(constraints, "environment", path), f"{path}.environment"
    )
    allowed_environment_keys = {"CFLAGS", "SOURCE_DATE_EPOCH"}
    if not set(environment) <= allowed_environment_keys:
        _fail(
            f"{path}.environment",
            "may contain only CFLAGS and SOURCE_DATE_EPOCH",
        )
    if "CFLAGS" in environment and (
        not isinstance(environment["CFLAGS"], str)
        or not environment["CFLAGS"]
        or len(environment["CFLAGS"]) > 256
        or any(character in environment["CFLAGS"] for character in ("\0", "\r", "\n"))
    ):
        _fail(
            f"{path}.environment.CFLAGS",
            "must be a bounded non-empty string",
        )
    if "SOURCE_DATE_EPOCH" in environment:
        source_date_epoch = environment["SOURCE_DATE_EPOCH"]
        if source_date_epoch is not None and (
            not isinstance(source_date_epoch, str)
            or not source_date_epoch
            or len(source_date_epoch) > 128
            or any(character in source_date_epoch for character in ("\0", "\r", "\n"))
        ):
            _fail(
                f"{path}.environment.SOURCE_DATE_EPOCH",
                "must be null (explicitly unset) or a bounded string",
            )
    delay = _required(constraints, "minimum_replay_delay_seconds", path)
    if (
        isinstance(delay, bool)
        or not isinstance(delay, (int, float))
        or not 0 <= delay <= 3600
    ):
        _fail(
            f"{path}.minimum_replay_delay_seconds",
            "must be a number from 0 through 3600",
        )


def _validate_cases(value: Any) -> set[str]:
    cases = _as_array(value, "manifest.cases")
    if len(cases) != 5:
        _fail("manifest.cases", "must contain exactly five pilot cases")
    case_ids: set[str] = set()
    repositories: set[str] = set()
    for index, item in enumerate(cases):
        path = f"manifest.cases[{index}]"
        case = _as_object(item, path)
        _require_exact_keys(
            case,
            {
                "id",
                "repository_url",
                "commit_sha",
                "languages",
                "build_system",
                "license",
                "oracle",
                "constraints",
            },
            path,
        )
        case_id = _validate_identifier(_required_string(case, "id", path), f"{path}.id")
        if case_id in case_ids:
            _fail(f"{path}.id", "duplicate case ID")
        case_ids.add(case_id)
        repository_url = _validate_repo_url(
            _required(case, "repository_url", path), f"{path}.repository_url"
        )
        repository_identity = _canonical_repo_identity(repository_url)
        if repository_identity in repositories:
            _fail(f"{path}.repository_url", "duplicate pilot repository")
        repositories.add(repository_identity)
        _validate_commit_sha(_required(case, "commit_sha", path), f"{path}.commit_sha")
        languages = _as_array(_required(case, "languages", path), f"{path}.languages")
        if not languages or any(
            not isinstance(language, str) or language not in _LANGUAGES
            for language in languages
        ):
            _fail(f"{path}.languages", "must contain unique C and/or C++ values only")
        if len(set(languages)) != len(languages):
            _fail(f"{path}.languages", "must contain unique C and/or C++ values only")
        build_system = _required_string(case, "build_system", path)
        if build_system not in _BUILD_SYSTEMS:
            _fail(f"{path}.build_system", "must be cmake, make, or autotools")
        license_name = _required_string(case, "license", path)
        if len(license_name) > 160 or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9 .()+-]*", license_name
        ):
            _fail(f"{path}.license", "must be a bounded license identifier")
        _validate_oracle(_required(case, "oracle", path), f"{path}.oracle")
        _validate_constraints(
            _required(case, "constraints", path), f"{path}.constraints"
        )
    return case_ids


def _validate_manifest_impl(document: Any) -> dict[str, Any]:
    manifest = _as_object(document, "manifest")
    _require_exact_keys(
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
        _fail(
            "manifest.schema_version", f"unsupported version; expected {SCHEMA_VERSION}"
        )
    if manifest.get("document_type") != MANIFEST_DOCUMENT_TYPE:
        _fail("manifest.document_type", "must be 'manifest'")
    if manifest.get("manifest_canonicalization") != CANONICAL_JSON_ALGORITHM:
        _fail(
            "manifest.manifest_canonicalization",
            f"must be {CANONICAL_JSON_ALGORITHM!r}",
        )
    for key in (
        "benchmark",
        "scope",
        "forge",
        "protocol_artifact_sha256",
        "model",
        "runtime",
        "conditions",
        "cases",
    ):
        _required(manifest, key, "manifest")
    _scan_for_unsafe_values(manifest)

    benchmark = _as_object(manifest["benchmark"], "manifest.benchmark")
    _require_exact_keys(
        benchmark, {"id", "name", "purpose", "dataset_provenance"}, "manifest.benchmark"
    )
    _validate_identifier(
        _required_string(benchmark, "id", "manifest.benchmark"), "manifest.benchmark.id"
    )
    if len(_required_string(benchmark, "name", "manifest.benchmark")) > 160:
        _fail("manifest.benchmark.name", "must not exceed 160 characters")
    if (
        _required_string(benchmark, "purpose", "manifest.benchmark")
        != "clean_replay_collection_calibration"
    ):
        _fail(
            "manifest.benchmark.purpose",
            "must freeze the clean replay collection calibration purpose",
        )
    if (
        _required_string(benchmark, "dataset_provenance", "manifest.benchmark")
        != "self_selected_calibration_set"
    ):
        _fail(
            "manifest.benchmark.dataset_provenance",
            "must identify the self-selected calibration set",
        )
    scope = _as_object(manifest["scope"], "manifest.scope")
    _require_exact_keys(
        scope,
        {"languages", "phase", "formal_comparison_enabled", "instrumentation_blocker"},
        "manifest.scope",
    )
    scope_languages = _as_array(
        _required(scope, "languages", "manifest.scope"), "manifest.scope.languages"
    )
    if (
        len(scope_languages) != 2
        or any(
            not isinstance(language, str) or language not in _LANGUAGES
            for language in scope_languages
        )
        or set(scope_languages) != _LANGUAGES
    ):
        _fail("manifest.scope.languages", "must contain exactly C and C++")
    if (
        scope.get("phase") != "pilot"
        or scope.get("formal_comparison_enabled") is not False
        or scope.get("instrumentation_blocker") is not True
    ):
        _fail("manifest.scope", "must remain a blocked pilot, not a formal comparison")

    forge = _as_object(manifest["forge"], "manifest.forge")
    _require_exact_keys(
        forge, {"repository_url", "commit_sha", "component_sha256"}, "manifest.forge"
    )
    _validate_repo_url(
        _required(forge, "repository_url", "manifest.forge"),
        "manifest.forge.repository_url",
    )
    _validate_commit_sha(
        _required(forge, "commit_sha", "manifest.forge"), "manifest.forge.commit_sha"
    )
    _validate_component_hashes(forge)
    protocol_hashes = _as_object(
        manifest["protocol_artifact_sha256"],
        "manifest.protocol_artifact_sha256",
    )
    if set(protocol_hashes) != _PROTOCOL_ARTIFACT_PATHS:
        _fail(
            "manifest.protocol_artifact_sha256",
            "must contain exactly the recorder and benchmark schema hashes",
        )
    for artifact_path, digest in protocol_hashes.items():
        _validate_sha256(
            digest,
            f"manifest.protocol_artifact_sha256.{artifact_path}",
        )
    _validate_model(_as_object(manifest["model"], "manifest.model"))
    _validate_runtime(_as_object(manifest["runtime"], "manifest.runtime"))
    _validate_conditions(manifest["conditions"])
    _validate_cases(manifest["cases"])
    return manifest


def validate_manifest(document: Any) -> dict[str, Any]:
    """Validate the manifest contract without reading repository files."""
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
        raise BenchmarkError(
            "manifest: cannot be represented as canonical JSON"
        ) from exc


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()


def verify_frozen_components(manifest: dict[str, Any], repo_root: Path) -> None:
    """Verify every frozen component against ordinary files in the repository."""
    validate_manifest(manifest)
    try:
        resolved_root = repo_root.resolve(strict=True)
    except OSError as exc:
        raise BenchmarkError(
            "frozen_components: repository root is unavailable"
        ) from exc
    if not resolved_root.is_dir():
        raise BenchmarkError("frozen_components: repository root must be a directory")

    hash_groups = (
        (
            "manifest.forge.component_sha256",
            manifest["forge"]["component_sha256"],
        ),
        (
            "manifest.protocol_artifact_sha256",
            manifest["protocol_artifact_sha256"],
        ),
    )
    for path_prefix, hashes in hash_groups:
        for relative_path, expected_sha256 in hashes.items():
            candidate = resolved_root
            for part in PurePosixPath(relative_path).parts:
                candidate /= part
                if candidate.is_symlink():
                    _fail(
                        f"{path_prefix}.{relative_path}",
                        "must reference an ordinary file, not a symlink",
                    )
            if not candidate.exists():
                _fail(
                    f"{path_prefix}.{relative_path}",
                    "references a missing file",
                )
            if not candidate.is_file():
                _fail(
                    f"{path_prefix}.{relative_path}",
                    "must reference an ordinary file",
                )
            try:
                resolved_candidate = candidate.resolve(strict=True)
                resolved_candidate.relative_to(resolved_root)
                digest = hashlib.sha256()
                with resolved_candidate.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
            except (OSError, ValueError) as exc:
                raise BenchmarkError(
                    f"{path_prefix}.{relative_path}: could not safely hash the frozen file"
                ) from exc
            if digest.hexdigest() != expected_sha256:
                _fail(
                    f"{path_prefix}.{relative_path}",
                    "does not match the current repository file",
                )


def load_json_document(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BenchmarkError("document: could not read valid UTF-8 JSON") from exc
    return _as_object(value, "document")


def _safe_optional_enum(value: Any, allowed: set[str]) -> str | None:
    return value if isinstance(value, str) and value in allowed else None


def _safe_optional_int(value: Any, *, minimum: int | None = None) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if minimum is not None and value < minimum:
        return None
    return value


def _safe_optional_number(
    value: Any, *, minimum: float | None = None
) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not (-sys.float_info.max <= value <= sys.float_info.max):
        return None
    if minimum is not None and value < minimum:
        return None
    return value


def _safe_optional_sha256(value: Any) -> str | None:
    return value if isinstance(value, str) and _SHA256_RE.fullmatch(value) else None


def _safe_optional_image(value: Any) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 160:
        return None
    return value if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:+/@-]*", value) else None


def _safe_optional_image_id(value: Any) -> str | None:
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value)
        else None
    )


def _safe_optional_commit_sha(value: Any) -> str | None:
    return value if isinstance(value, str) and _COMMIT_SHA_RE.fullmatch(value) else None


def _safe_attempt_id(value: Any) -> str | None:
    return value if isinstance(value, str) and _SESSION_ID_RE.fullmatch(value) else None


def _load_workflow_events(path: Path, session_id: str) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise BenchmarkError("workflow: could not read logs/workflow.log") from exc
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BenchmarkError(
                f"workflow: line {line_number} is not valid JSON"
            ) from exc
        if not isinstance(event, dict) or not isinstance(event.get("event"), str):
            _fail(f"workflow[{line_number}]", "must be an event object")
        event_session_id = event.get("session_id")
        if event_session_id != session_id:
            _fail(
                f"workflow[{line_number}].session_id",
                "must be present and match session.json",
            )
        events.append(event)
    return events


def _latest_submit_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    for event in events:
        if event.get("event") in {
            "submit.started",
            "submit.completed",
            "submit.aborted",
        }:
            latest = event
    return latest


def _normalized_submit_event(
    event: dict[str, Any] | None,
) -> tuple[str, dict[str, Any] | None]:
    if event is None:
        return "not_observed", None
    event_name = event["event"]
    if event_name == "submit.started":
        return "started", {
            "event": event_name,
            "stage": None,
            "status": None,
            "artifact_count": None,
            "failed_checks": None,
            "candidate_status": None,
            "replay_status": None,
            "replay_attempt_id": None,
        }
    if event_name == "submit.aborted":
        return "aborted", {
            "event": event_name,
            "stage": _safe_optional_enum(
                event.get("stage"),
                {"entry", "candidate_checkpoint", "final_checkpoint"},
            ),
            "status": _safe_optional_enum(
                event.get("status"), {"completed", "failed", "cancelled", "timed_out"}
            ),
            "artifact_count": None,
            "failed_checks": None,
            "candidate_status": None,
            "replay_status": None,
            "replay_attempt_id": None,
        }
    return "completed", {
        "event": event_name,
        "stage": None,
        "status": _safe_optional_enum(event.get("status"), {"passed", "failed"}),
        "artifact_count": _safe_optional_int(event.get("artifact_count"), minimum=0),
        "failed_checks": _safe_optional_int(event.get("failed_checks"), minimum=0),
        "candidate_status": _safe_optional_enum(
            event.get("candidate_status"), _RAW_CANDIDATE_STATUSES
        ),
        "replay_status": _safe_optional_enum(
            event.get("replay_status"), _RAW_REPLAY_STATUSES
        ),
        "replay_attempt_id": _safe_attempt_id(event.get("replay_attempt_id")),
    }


def _normalized_completion_event(
    events: list[dict[str, Any]],
) -> dict[str, Any] | None:
    latest_submit_index: int | None = None
    latest_submit_name: str | None = None
    for index, event in enumerate(events):
        if event.get("event") in {
            "submit.started",
            "submit.completed",
            "submit.aborted",
        }:
            latest_submit_index = index
            latest_submit_name = event["event"]
    latest: dict[str, Any] | None = None
    start_index = latest_submit_index + 1 if latest_submit_index is not None else 0
    for event in events[start_index:]:
        if (
            latest_submit_name == "submit.completed"
            and event.get("event") == "artifact.finalization_recheck"
            and isinstance(event.get("passed"), bool)
        ):
            latest = {
                "event": "artifact.finalization_recheck",
                "reason": None,
                "passed": event["passed"],
            }
        elif (
            event.get("event") == "finalize.deferred"
            and event.get("reason") == "container_cleanup_failed"
        ):
            latest = {
                "event": "finalize.deferred",
                "reason": "container_cleanup_failed",
                "passed": None,
            }
        elif event.get("event") == "finalize.completed" and latest is None:
            status = _safe_optional_enum(
                event.get("status"), {"completed", "failed", "cancelled", "timed_out"}
            )
            if status is not None:
                latest = {
                    "event": "finalize.completed",
                    "reason": None if status == "completed" else status,
                    "passed": True if status == "completed" else None,
                }
    return latest


def _find_replay_attempt(
    session: dict[str, Any], attempt_id: str | None
) -> dict[str, Any] | None:
    if attempt_id is None:
        return None
    attempts = session.get("replay_attempts")
    if not isinstance(attempts, list):
        return None
    matches = [
        attempt
        for attempt in attempts
        if isinstance(attempt, dict) and attempt.get("attempt_id") == attempt_id
    ]
    if len(matches) > 1:
        _fail("session.replay_attempts", "contains duplicate attempt IDs")
    return matches[0] if matches else None


def _normalized_replay_attempt(attempt: dict[str, Any] | None) -> dict[str, Any] | None:
    if attempt is None:
        return None
    cleanup = attempt.get("cleanup_succeeded")
    return {
        "attempt_id": _safe_attempt_id(attempt.get("attempt_id")),
        "image": _safe_optional_image(attempt.get("image")),
        "image_id": _safe_optional_image_id(attempt.get("image_id")),
        "commit_sha": _safe_optional_commit_sha(attempt.get("commit_sha")),
        "status": _safe_optional_enum(
            attempt.get("status"), _RAW_REPLAY_STATUSES - {"not_run"}
        ),
        "failure_classification": _safe_optional_enum(
            attempt.get("failure_classification"), _REPLAY_FAILURE_CLASSIFICATIONS
        ),
        "exit_code": _safe_optional_int(attempt.get("exit_code")),
        "cleanup_succeeded": cleanup if isinstance(cleanup, bool) else None,
        "duration_seconds": _safe_optional_number(
            attempt.get("duration_seconds"), minimum=0
        ),
        "timeout_seconds": _safe_optional_int(
            attempt.get("timeout_seconds"), minimum=1
        ),
        "recipe_sha256": _safe_optional_sha256(attempt.get("recipe_sha256")),
    }


def _artifact_relative_path(source_path: Any) -> str | None:
    if (
        not isinstance(source_path, str)
        or not source_path.startswith("/artifacts/")
        or "\\" in source_path
        or any(
            ord(character) < 0x20 or ord(character) == 0x7F for character in source_path
        )
    ):
        return None
    path = PurePosixPath(source_path)
    root = PurePosixPath("/artifacts")
    if ".." in path.parts or root not in path.parents:
        return None
    relative = path.relative_to(root).as_posix()
    if (
        not relative
        or len(relative) > 512
        or _HOST_PATH_RE.search(relative)
        or ".compile-sessions" in path.parts
    ):
        return None
    return relative


def _normalized_artifacts(
    session: dict[str, Any], *, include: bool
) -> list[dict[str, Any]] | None:
    if not include or not isinstance(session.get("artifacts"), list):
        return None
    if len(session["artifacts"]) > 1000:
        _fail("session.artifacts", "must not contain more than 1000 artifacts")
    normalized = []
    for artifact in session["artifacts"]:
        if not isinstance(artifact, dict):
            continue
        normalized.append(
            {
                "relative_path": _artifact_relative_path(artifact.get("source_path")),
                "artifact_type": _safe_optional_enum(
                    artifact.get("artifact_type"), _ARTIFACT_TYPES
                ),
                "size_bytes": _safe_optional_int(artifact.get("size_bytes"), minimum=0),
                "sha256": _safe_optional_sha256(artifact.get("sha256")),
                "smoke_exit_code": _safe_optional_int(artifact.get("smoke_exit_code")),
                "smoke_output_sha256": _safe_optional_sha256(
                    artifact.get("smoke_output_sha256")
                ),
            }
        )
    return normalized


def _command_summary(session: dict[str, Any]) -> dict[str, int | None] | None:
    commands = session.get("commands")
    if not isinstance(commands, list):
        return None
    valid_commands = [command for command in commands if isinstance(command, dict)]
    return {
        "total": len(valid_commands),
        "successful_bash": sum(
            command.get("stage") == "bash"
            and isinstance(command.get("exit_code"), int)
            and not isinstance(command.get("exit_code"), bool)
            and command.get("exit_code") == 0
            for command in valid_commands
        ),
        "failed_bash": sum(
            command.get("stage") == "bash"
            and isinstance(command.get("exit_code"), int)
            and not isinstance(command.get("exit_code"), bool)
            and command.get("exit_code") != 0
            for command in valid_commands
        ),
    }


def _duration_seconds(started_at: Any, completed_at: Any) -> float | None:
    if not isinstance(started_at, str) or not isinstance(completed_at, str):
        return None
    try:
        started = datetime.fromisoformat(started_at)
        completed = datetime.fromisoformat(completed_at)
    except ValueError:
        return None
    if started.tzinfo is None or completed.tzinfo is None:
        return None
    duration = (completed - started).total_seconds()
    return round(duration, 6) if duration >= 0 else None


def _validate_nullable_boolean(value: Any, path: str) -> None:
    if value is not None and not isinstance(value, bool):
        _fail(path, "must be a boolean or null")


def _validate_nullable_integer(
    value: Any, path: str, *, minimum: int | None = None
) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(path, "must be an integer or null")
    if minimum is not None and value < minimum:
        _fail(path, f"must be null or an integer >= {minimum}")


def _validate_nullable_number(
    value: Any, path: str, *, minimum: float | None = None
) -> None:
    if value is None:
        return
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not (-sys.float_info.max <= value <= sys.float_info.max)
    ):
        _fail(path, "must be a finite number or null")
    if minimum is not None and value < minimum:
        _fail(path, f"must be null or a number >= {minimum}")


def _validate_nullable_enum(value: Any, allowed: set[str], path: str) -> None:
    if value is not None and (not isinstance(value, str) or value not in allowed):
        _fail(path, f"must be null or one of: {', '.join(sorted(allowed))}")


def _validate_nullable_sha256(value: Any, path: str) -> None:
    if value is not None:
        _validate_sha256(value, path)


def _validate_nullable_safe_token(value: Any, path: str) -> None:
    if value is None:
        return
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 160
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:+/@-]*", value)
    ):
        _fail(path, "must be null or a bounded safe token")


def _validate_normalized_artifact(value: Any, path: str) -> None:
    artifact = _as_object(value, path)
    _require_exact_keys(
        artifact,
        {
            "relative_path",
            "artifact_type",
            "size_bytes",
            "sha256",
            "smoke_exit_code",
            "smoke_output_sha256",
        },
        path,
    )
    relative_path = artifact["relative_path"]
    if relative_path is not None:
        if (
            not isinstance(relative_path, str)
            or not relative_path
            or len(relative_path) > 512
            or relative_path.startswith("/")
            or "\\" in relative_path
            or any(
                ord(character) < 0x20 or ord(character) == 0x7F
                for character in relative_path
            )
            or ".." in PurePosixPath(relative_path).parts
            or _HOST_PATH_RE.search(relative_path)
        ):
            _fail(
                f"{path}.relative_path", "must be null or a safe bounded relative path"
            )
    _validate_nullable_enum(
        artifact["artifact_type"], _ARTIFACT_TYPES, f"{path}.artifact_type"
    )
    _validate_nullable_integer(artifact["size_bytes"], f"{path}.size_bytes", minimum=0)
    _validate_nullable_sha256(artifact["sha256"], f"{path}.sha256")
    _validate_nullable_integer(artifact["smoke_exit_code"], f"{path}.smoke_exit_code")
    _validate_nullable_sha256(
        artifact["smoke_output_sha256"], f"{path}.smoke_output_sha256"
    )
    if artifact["artifact_type"] == "executable" and (
        artifact["smoke_exit_code"] != 0 or artifact["smoke_output_sha256"] is None
    ):
        _fail(path, "executable evidence requires a successful bounded smoke result")


def _validate_submit_evidence(value: Any, path: str) -> None:
    if value is None:
        return
    event = _as_object(value, path)
    keys = {
        "event",
        "stage",
        "status",
        "failed_checks",
        "replay_attempt_id",
        "artifact_count",
        "candidate_status",
        "replay_status",
    }
    _require_exact_keys(event, keys, path)
    event_name = _required_string(event, "event", path)
    if event_name not in {"submit.started", "submit.completed", "submit.aborted"}:
        _fail(f"{path}.event", "must be a supported submit event")
    _validate_nullable_enum(
        event["stage"],
        {"entry", "candidate_checkpoint", "final_checkpoint"},
        f"{path}.stage",
    )
    _validate_nullable_enum(
        event["status"],
        {"passed", "failed", "completed", "cancelled", "timed_out"},
        f"{path}.status",
    )
    _validate_nullable_integer(
        event["failed_checks"], f"{path}.failed_checks", minimum=0
    )
    _validate_nullable_safe_token(
        event["replay_attempt_id"], f"{path}.replay_attempt_id"
    )
    _validate_nullable_integer(
        event["artifact_count"], f"{path}.artifact_count", minimum=0
    )
    _validate_nullable_enum(
        event["candidate_status"], _RAW_CANDIDATE_STATUSES, f"{path}.candidate_status"
    )
    _validate_nullable_enum(
        event["replay_status"],
        {"passed", "failed", "timed_out", "cancelled", "not_run"},
        f"{path}.replay_status",
    )
    remaining_values = tuple(event[key] for key in keys - {"event"})
    if event_name == "submit.started" and any(
        value is not None for value in remaining_values
    ):
        _fail(path, "submit.started may not claim an outcome")
    if event_name == "submit.aborted" and any(
        event[key] is not None
        for key in {
            "failed_checks",
            "replay_attempt_id",
            "artifact_count",
            "candidate_status",
            "replay_status",
        }
    ):
        _fail(
            path, "submit.aborted may preserve only bounded stage and status evidence"
        )
    if event_name == "submit.completed":
        if event["stage"] is not None or any(
            event[key] is None
            for key in {
                "status",
                "failed_checks",
                "artifact_count",
                "candidate_status",
                "replay_status",
            }
        ):
            _fail(path, "submit.completed requires complete bounded evidence")
        if event["status"] not in {"passed", "failed"}:
            _fail(f"{path}.status", "completed submit status must be passed or failed")
        if event["status"] == "passed" and (
            event["candidate_status"] != "passed"
            or event["replay_status"] != "passed"
            or event["failed_checks"] != 0
            or event["artifact_count"] < 1
        ):
            _fail(path, "passed submit fields are inconsistent")
        if event["status"] == "failed" and (
            event["replay_status"] == "passed" or event["failed_checks"] == 0
        ):
            _fail(path, "failed submit fields are inconsistent")
        if event["candidate_status"] == "failed" and (
            event["status"] != "failed"
            or event["replay_status"] != "not_run"
            or event["replay_attempt_id"] is not None
        ):
            _fail(path, "candidate rejection may not claim a replay")
        if event["candidate_status"] == "passed" and event["replay_status"] not in {
            "passed",
            "failed",
            "timed_out",
            "cancelled",
        }:
            _fail(path, "candidate pass requires a terminal replay")


def _validate_replay_evidence(value: Any, path: str) -> None:
    if value is None:
        return
    attempt = _as_object(value, path)
    _require_exact_keys(
        attempt,
        {
            "attempt_id",
            "image",
            "image_id",
            "commit_sha",
            "status",
            "failure_classification",
            "exit_code",
            "cleanup_succeeded",
            "duration_seconds",
            "timeout_seconds",
            "recipe_sha256",
        },
        path,
    )
    _validate_nullable_safe_token(attempt["attempt_id"], f"{path}.attempt_id")
    _validate_nullable_safe_token(attempt["image"], f"{path}.image")
    image_id = attempt["image_id"]
    if image_id is not None and (
        not isinstance(image_id, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id)
    ):
        _fail(f"{path}.image_id", "must be null or an immutable image ID")
    if attempt["commit_sha"] is not None:
        _validate_commit_sha(attempt["commit_sha"], f"{path}.commit_sha")
    _validate_nullable_enum(
        attempt["status"], _RAW_REPLAY_STATUSES - {"not_run"}, f"{path}.status"
    )
    _validate_nullable_enum(
        attempt["failure_classification"],
        _REPLAY_FAILURE_CLASSIFICATIONS,
        f"{path}.failure_classification",
    )
    _validate_nullable_integer(attempt["exit_code"], f"{path}.exit_code")
    _validate_nullable_boolean(
        attempt["cleanup_succeeded"], f"{path}.cleanup_succeeded"
    )
    _validate_nullable_number(
        attempt["duration_seconds"], f"{path}.duration_seconds", minimum=0
    )
    _validate_nullable_integer(
        attempt["timeout_seconds"], f"{path}.timeout_seconds", minimum=0
    )
    _validate_nullable_sha256(attempt["recipe_sha256"], f"{path}.recipe_sha256")
    terminal_statuses = {"passed", "failed", "timed_out", "cancelled"}
    if attempt["status"] in terminal_statuses and (
        attempt["attempt_id"] is None
        or attempt["image"] is None
        or attempt["commit_sha"] is None
        or attempt["cleanup_succeeded"] is None
        or attempt["duration_seconds"] is None
        or attempt["timeout_seconds"] is None
        or attempt["timeout_seconds"] < 1
    ):
        _fail(
            path, "terminal replay evidence must preserve bounded identity and timing"
        )
    if attempt["status"] == "passed" and (
        attempt["image_id"] is None
        or attempt["failure_classification"] is not None
        or attempt["exit_code"] != 0
        or attempt["cleanup_succeeded"] is not True
        or attempt["recipe_sha256"] is None
    ):
        _fail(path, "passed replay evidence must be complete and clean")
    if attempt["status"] in {"failed", "timed_out", "cancelled"}:
        if attempt["failure_classification"] is None:
            _fail(path, "rejected replay evidence requires a failure classification")
        if (
            attempt["image_id"] is None
            and attempt["failure_classification"] != "image_identity_unavailable"
        ):
            _fail(
                path,
                "rejected replay evidence requires an image ID unless identity was unavailable",
            )
    if (
        attempt["status"] == "timed_out"
        and attempt["failure_classification"] != "timeout"
    ):
        _fail(path, "timed-out replay evidence requires timeout classification")


def _validate_completion_evidence(value: Any, path: str) -> None:
    if value is None:
        return
    event = _as_object(value, path)
    _require_exact_keys(event, {"event", "reason", "passed"}, path)
    if event["event"] == "artifact.finalization_recheck":
        if event["reason"] is not None or not isinstance(event["passed"], bool):
            _fail(
                path, "finalization recheck requires a boolean result and null reason"
            )
    elif event["event"] == "finalize.deferred":
        if event["reason"] != "container_cleanup_failed" or event["passed"] is not None:
            _fail(path, "finalize.deferred requires the bounded cleanup-failure reason")
    elif event["event"] == "finalize.completed":
        if event["reason"] is None:
            if event["passed"] is not True:
                _fail(path, "successful finalize.completed requires passed=true")
        elif (
            event["reason"] not in {"failed", "cancelled", "timed_out"}
            or event["passed"] is not None
        ):
            _fail(
                path,
                "interrupted finalize.completed requires a bounded terminal reason",
            )
    else:
        _fail(f"{path}.event", "must be a supported completion event")


def _validate_run_record_impl(document: Any) -> dict[str, Any]:
    record = _as_object(document, "run_record")
    _require_exact_keys(
        record,
        {
            "schema_version",
            "document_type",
            "benchmark_id",
            "manifest_sha256",
            "manifest_canonicalization",
            "recorded_at",
            "case_id",
            "condition",
            "repetition",
            "source",
            "outcome",
            "failure_attribution",
            "evidence",
        },
        "run_record",
        optional={"$schema"},
    )
    if record["schema_version"] != SCHEMA_VERSION:
        _fail("run_record.schema_version", f"must be {SCHEMA_VERSION!r}")
    if record["document_type"] != RUN_RECORD_DOCUMENT_TYPE:
        _fail("run_record.document_type", "must be 'run_record'")
    if record["manifest_canonicalization"] != CANONICAL_JSON_ALGORITHM:
        _fail(
            "run_record.manifest_canonicalization",
            f"must be {CANONICAL_JSON_ALGORITHM!r}",
        )
    if "$schema" in record and (
        not isinstance(record["$schema"], str)
        or not record["$schema"]
        or len(record["$schema"]) > 2048
    ):
        _fail("run_record.$schema", "must be a bounded non-empty string")
    _validate_identifier(
        _required_string(record, "benchmark_id", "run_record"),
        "run_record.benchmark_id",
    )
    _validate_sha256(record["manifest_sha256"], "run_record.manifest_sha256")
    recorded_at = _required_string(record, "recorded_at", "run_record")
    try:
        parsed_recorded_at = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
    except ValueError:
        parsed_recorded_at = None
    if parsed_recorded_at is None or parsed_recorded_at.tzinfo is None:
        _fail("run_record.recorded_at", "must be a timezone-aware date-time")
    _validate_identifier(
        _required_string(record, "case_id", "run_record"), "run_record.case_id"
    )
    _validate_identifier(
        _required_string(record, "condition", "run_record"), "run_record.condition"
    )
    _required_int(record, "repetition", "run_record", minimum=1)

    source = _as_object(record["source"], "run_record.source")
    _require_exact_keys(
        source,
        {
            "session_id",
            "run_id",
            "repository_url",
            "commit_sha",
            "build_system",
            "image_id",
        },
        "run_record.source",
    )
    if not isinstance(source["session_id"], str) or not _SESSION_ID_RE.fullmatch(
        source["session_id"]
    ):
        _fail(
            "run_record.source.session_id",
            "must be a 12-character hexadecimal compile-session ID",
        )
    run_id = source["run_id"]
    if run_id is not None and (
        not isinstance(run_id, str)
        or len(run_id) > 160
        or not _RUN_ID_RE.fullmatch(run_id)
    ):
        _fail("run_record.source.run_id", "must be null or a bounded run ID")
    _validate_repo_url(source["repository_url"], "run_record.source.repository_url")
    if source["commit_sha"] is not None:
        _validate_commit_sha(source["commit_sha"], "run_record.source.commit_sha")
    _validate_nullable_enum(
        source["build_system"], _BUILD_SYSTEMS, "run_record.source.build_system"
    )
    image_id = source["image_id"]
    if image_id is not None and (
        not isinstance(image_id, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id)
    ):
        _fail("run_record.source.image_id", "must be null or an immutable image ID")

    outcome = _as_object(record["outcome"], "run_record.outcome")
    _require_exact_keys(
        outcome,
        {
            "session_status",
            "submit_status",
            "candidate_status",
            "clean_replay_status",
            "replay_failure_classification",
            "replay_cleanup_succeeded",
            "verification_status",
            "artifact_count",
            "finalized",
            "oracle_match",
        },
        "run_record.outcome",
    )
    _validate_nullable_enum(
        outcome["session_status"],
        _SESSION_STATUSES,
        "run_record.outcome.session_status",
    )
    if outcome["submit_status"] not in {
        "not_observed",
        "started",
        "aborted",
        "completed",
    }:
        _fail("run_record.outcome.submit_status", "must be a supported submit status")
    _validate_nullable_enum(
        outcome["candidate_status"],
        _GATE_RESULTS,
        "run_record.outcome.candidate_status",
    )
    _validate_nullable_enum(
        outcome["clean_replay_status"],
        _GATE_RESULTS,
        "run_record.outcome.clean_replay_status",
    )
    _validate_nullable_enum(
        outcome["replay_failure_classification"],
        _REPLAY_FAILURE_CLASSIFICATIONS,
        "run_record.outcome.replay_failure_classification",
    )
    _validate_nullable_boolean(
        outcome["replay_cleanup_succeeded"],
        "run_record.outcome.replay_cleanup_succeeded",
    )
    _validate_nullable_enum(
        outcome["verification_status"],
        _VERIFICATION_STATUSES,
        "run_record.outcome.verification_status",
    )
    _validate_nullable_integer(
        outcome["artifact_count"], "run_record.outcome.artifact_count", minimum=0
    )
    _validate_nullable_boolean(outcome["finalized"], "run_record.outcome.finalized")
    _validate_nullable_boolean(
        outcome["oracle_match"], "run_record.outcome.oracle_match"
    )

    attribution = _as_object(
        record["failure_attribution"], "run_record.failure_attribution"
    )
    attribution_keys = {
        "model_endpoint",
        "agent",
        "build",
        "candidate_generation",
        "clean_replay",
        "cleanup",
        "completion",
    }
    _require_exact_keys(attribution, attribution_keys, "run_record.failure_attribution")
    for key in attribution_keys:
        _validate_nullable_boolean(
            attribution[key], f"run_record.failure_attribution.{key}"
        )
    for key in {"model_endpoint", "agent", "build"}:
        if attribution[key] is not None:
            _fail(
                f"run_record.failure_attribution.{key}",
                "must be null until the pre-model evidence ledger exists",
            )

    evidence = _as_object(record["evidence"], "run_record.evidence")
    _require_exact_keys(
        evidence,
        {
            "submit_event",
            "replay_attempt",
            "completion_event",
            "command_summary",
            "artifacts",
            "session_duration_seconds",
        },
        "run_record.evidence",
    )
    _validate_submit_evidence(
        evidence["submit_event"], "run_record.evidence.submit_event"
    )
    _validate_replay_evidence(
        evidence["replay_attempt"], "run_record.evidence.replay_attempt"
    )
    _validate_completion_evidence(
        evidence["completion_event"], "run_record.evidence.completion_event"
    )
    command_summary = evidence["command_summary"]
    if command_summary is not None:
        command_summary = _as_object(
            command_summary, "run_record.evidence.command_summary"
        )
        _require_exact_keys(
            command_summary,
            {"total", "successful_bash", "failed_bash"},
            "run_record.evidence.command_summary",
        )
        for key in ("total", "successful_bash", "failed_bash"):
            _validate_nullable_integer(
                command_summary[key],
                f"run_record.evidence.command_summary.{key}",
                minimum=0,
            )
        counts = tuple(command_summary.values())
        if all(value is not None for value in counts) and (
            command_summary["successful_bash"] + command_summary["failed_bash"]
            > command_summary["total"]
        ):
            _fail(
                "run_record.evidence.command_summary",
                "bash outcome counts must not exceed the command total",
            )
    artifacts = evidence["artifacts"]
    if artifacts is not None:
        artifacts = _as_array(artifacts, "run_record.evidence.artifacts")
        if len(artifacts) > 1000:
            _fail(
                "run_record.evidence.artifacts", "must not contain more than 1000 items"
            )
        for index, artifact in enumerate(artifacts):
            _validate_normalized_artifact(
                artifact, f"run_record.evidence.artifacts[{index}]"
            )
    _validate_nullable_number(
        evidence["session_duration_seconds"],
        "run_record.evidence.session_duration_seconds",
        minimum=0,
    )

    completion_event = evidence["completion_event"]
    completion_failed = completion_event is not None and (
        completion_event["event"] == "finalize.deferred"
        or completion_event["passed"] is False
    )
    submit_status = outcome["submit_status"]
    submit_event = evidence["submit_event"]
    expected_event = {
        "started": "submit.started",
        "aborted": "submit.aborted",
        "completed": "submit.completed",
    }.get(submit_status)
    if expected_event is None:
        if submit_event is not None:
            _fail(
                "run_record.evidence.submit_event",
                "must be null when no submit was observed",
            )
    elif submit_event is None or submit_event["event"] != expected_event:
        _fail(
            "run_record.evidence.submit_event", "does not match outcome.submit_status"
        )

    if submit_status != "completed":
        if (
            any(
                outcome[key] is not None
                for key in {
                    "candidate_status",
                    "clean_replay_status",
                    "replay_failure_classification",
                    "replay_cleanup_succeeded",
                    "verification_status",
                    "artifact_count",
                }
            )
            or evidence["artifacts"] is not None
            or evidence["replay_attempt"] is not None
        ):
            _fail(
                "run_record", "an incomplete submit may not claim acceptance evidence"
            )
    else:
        if submit_event is None:
            _fail(
                "run_record.evidence.submit_event",
                "completed submit evidence is required",
            )
        if outcome["artifact_count"] != submit_event["artifact_count"]:
            _fail("run_record.outcome.artifact_count", "does not match submit evidence")
        if artifacts is None or outcome["artifact_count"] != len(artifacts):
            _fail(
                "run_record.evidence.artifacts",
                "does not match the submitted artifact count",
            )
        raw_candidate = submit_event["candidate_status"]
        expected_candidate = "pass" if raw_candidate == "passed" else "reject"
        if outcome["candidate_status"] != expected_candidate:
            _fail(
                "run_record.outcome.candidate_status", "does not match submit evidence"
            )
        replay_attempt = evidence["replay_attempt"]
        image_identity_unavailable = (
            replay_attempt is not None
            and replay_attempt["failure_classification"] == "image_identity_unavailable"
        )
        if source["commit_sha"] is None or (
            source["image_id"] is None and not image_identity_unavailable
        ):
            _fail(
                "run_record.source",
                "completed submit requires commit and image identity",
            )
        replay_status = submit_event["replay_status"]
        if replay_status == "not_run":
            if (
                submit_event["replay_attempt_id"] is not None
                or replay_attempt is not None
            ):
                _fail(
                    "run_record.evidence.replay_attempt",
                    "must be null when replay was not run",
                )
        elif (
            replay_attempt is None
            or replay_attempt["attempt_id"] != submit_event["replay_attempt_id"]
            or replay_attempt["status"] != replay_status
        ):
            _fail(
                "run_record.evidence.replay_attempt", "does not match submit evidence"
            )
        expected_clean_replay_status = (
            None
            if replay_status == "not_run"
            else "pass"
            if replay_status == "passed"
            else "reject"
        )
        if outcome["clean_replay_status"] != expected_clean_replay_status:
            _fail(
                "run_record.outcome.clean_replay_status",
                "does not match submit replay evidence",
            )
        if (
            submit_event["status"] == "failed"
            and outcome["verification_status"] != "failed"
        ):
            _fail(
                "run_record.outcome.verification_status",
                "must be failed for a rejected submit",
            )
        if submit_event["status"] == "passed":
            allowed_passed_session_statuses = {"verified", "completed"}
            if completion_failed:
                allowed_passed_session_statuses |= {
                    "verification_failed",
                    "failed",
                    "cancelled",
                    "timed_out",
                }
            if (
                completion_event is not None
                and completion_event["event"] == "finalize.completed"
                and completion_event["reason"] in {"failed", "cancelled", "timed_out"}
                and outcome["finalized"] is True
            ):
                allowed_passed_session_statuses.add(completion_event["reason"])
            if outcome["session_status"] not in allowed_passed_session_statuses:
                _fail(
                    "run_record.outcome.session_status",
                    "does not match a passed submit lifecycle",
                )
        elif outcome["session_status"] not in {
            "verification_failed",
            "failed",
            "cancelled",
            "timed_out",
        }:
            _fail(
                "run_record.outcome.session_status",
                "does not match a rejected submit lifecycle",
            )

    candidate_status = outcome["candidate_status"]
    expected_candidate_attribution = (
        False
        if candidate_status == "pass"
        else True
        if candidate_status == "reject"
        else None
    )
    if attribution["candidate_generation"] is not expected_candidate_attribution:
        _fail(
            "run_record.failure_attribution.candidate_generation",
            "does not match the candidate decision",
        )
    if candidate_status == "pass":
        if (
            outcome["verification_status"] not in {"passed", "failed"}
            or outcome["artifact_count"] is None
            or outcome["artifact_count"] < 1
            or artifacts is None
            or not artifacts
        ):
            _fail("run_record.evidence.artifacts", "candidate pass requires artifacts")
        paths: set[str] = set()
        for artifact in artifacts:
            relative_path = artifact["relative_path"]
            if (
                relative_path is None
                or artifact["artifact_type"] is None
                or artifact["size_bytes"] is None
                or artifact["size_bytes"] < 1
                or artifact["sha256"] is None
                or relative_path in paths
            ):
                _fail(
                    "run_record.evidence.artifacts",
                    "candidate pass requires complete unique artifact evidence",
                )
            paths.add(relative_path)

    replay_attempt = evidence["replay_attempt"]
    if replay_attempt is None:
        if (
            outcome["replay_failure_classification"] is not None
            or outcome["replay_cleanup_succeeded"] is not None
        ):
            _fail("run_record.outcome", "claims replay evidence that was not persisted")
    elif (
        outcome["replay_failure_classification"]
        != replay_attempt["failure_classification"]
        or outcome["replay_cleanup_succeeded"]
        is not replay_attempt["cleanup_succeeded"]
    ):
        _fail("run_record.outcome", "does not match persisted replay evidence")
    if outcome["clean_replay_status"] == "pass":
        if (
            candidate_status != "pass"
            or replay_attempt is None
            or replay_attempt["status"] != "passed"
            or outcome["replay_failure_classification"] is not None
            or outcome["replay_cleanup_succeeded"] is not True
            or attribution["clean_replay"] is not False
            or attribution["cleanup"] is not False
        ):
            _fail(
                "run_record.outcome.clean_replay_status",
                "pass lacks clean replay evidence",
            )
    if outcome["replay_failure_classification"] == "cleanup_failed" and (
        outcome["clean_replay_status"] != "reject"
        or outcome["replay_cleanup_succeeded"] is not False
        or attribution["clean_replay"] is not None
        or attribution["cleanup"] is not True
    ):
        _fail("run_record.outcome", "cleanup failure attribution is inconsistent")
    expected_clean_replay_attribution = (
        False
        if outcome["clean_replay_status"] == "pass"
        else None
        if outcome["replay_failure_classification"] == "cleanup_failed"
        else True
        if outcome["clean_replay_status"] == "reject"
        else None
    )
    if attribution["clean_replay"] is not expected_clean_replay_attribution:
        _fail(
            "run_record.failure_attribution.clean_replay",
            "does not match the replay decision",
        )
    expected_cleanup_attribution = None
    if replay_attempt is not None:
        if (
            replay_attempt["failure_classification"] == "cleanup_failed"
            or replay_attempt["cleanup_succeeded"] is False
        ):
            expected_cleanup_attribution = True
        elif replay_attempt["cleanup_succeeded"] is True:
            expected_cleanup_attribution = False
    if attribution["cleanup"] is not expected_cleanup_attribution:
        _fail(
            "run_record.failure_attribution.cleanup",
            "does not match replay cleanup evidence",
        )
    if outcome["session_status"] == "completed" and (
        candidate_status != "pass"
        or outcome["clean_replay_status"] != "pass"
        or outcome["finalized"] is not True
        or attribution["completion"] is not False
    ):
        _fail(
            "run_record.outcome.session_status", "completed requires accepted evidence"
        )
    if (
        submit_status == "completed"
        and submit_event["status"] == "passed"
        and outcome["verification_status"] == "failed"
        and not completion_failed
    ):
        _fail(
            "run_record.outcome.verification_status",
            "post-submit failure requires explicit completion evidence",
        )
    if outcome["session_status"] == "completed" and completion_failed:
        _fail(
            "run_record.evidence.completion_event",
            "completed session may not preserve a terminal completion failure",
        )
    if (
        completion_event is not None
        and completion_event["event"] == "finalize.completed"
    ):
        expected_reason = (
            None
            if outcome["session_status"] == "completed"
            else outcome["session_status"]
        )
        if (
            outcome["finalized"] is not True
            or completion_event["reason"] != expected_reason
        ):
            _fail(
                "run_record.evidence.completion_event",
                "does not match the finalized session status",
            )
    if submit_status != "completed" and attribution["completion"] is False:
        _fail(
            "run_record.failure_attribution.completion",
            "may not claim successful completion before submit completion",
        )
    if attribution["completion"] is True and (
        not completion_failed
        or (
            completion_event["event"] == "artifact.finalization_recheck"
            and (candidate_status != "pass" or outcome["clean_replay_status"] != "pass")
        )
    ):
        _fail(
            "run_record.failure_attribution.completion",
            "requires explicit post-submit failure evidence",
        )
    if completion_failed and attribution["completion"] is not True:
        _fail(
            "run_record.failure_attribution.completion",
            "must attribute the explicit completion failure",
        )
    return record


def validate_run_record(document: Any) -> dict[str, Any]:
    """Validate a normalized run record without optional third-party packages."""
    try:
        return _validate_run_record_impl(document)
    except BenchmarkError:
        raise
    except (AttributeError, OverflowError, TypeError, ValueError) as exc:
        raise BenchmarkError("run_record: contains a malformed value") from exc


def _manifest_case(manifest: dict[str, Any], case_id: str) -> dict[str, Any]:
    cases = [case for case in manifest["cases"] if case["id"] == case_id]
    if len(cases) != 1:
        _fail("record.case_id", "does not identify exactly one manifest case")
    return cases[0]


def _manifest_condition(
    manifest: dict[str, Any], condition_id: str, repetition: int
) -> dict[str, Any]:
    conditions = [
        condition
        for condition in manifest["conditions"]
        if condition["id"] == condition_id
    ]
    if len(conditions) != 1:
        _fail("record.condition", "does not identify exactly one manifest condition")
    condition = conditions[0]
    if repetition < 1 or repetition > condition["repetitions"]:
        _fail("record.repetition", "is outside the condition's declared repetitions")
    return condition


def build_run_record(
    *,
    manifest: dict[str, Any],
    case_id: str,
    condition_id: str,
    repetition: int,
    session: dict[str, Any],
    workflow_events: list[dict[str, Any]],
) -> dict[str, Any]:
    validate_manifest(manifest)
    case = _manifest_case(manifest, case_id)
    _manifest_condition(manifest, condition_id, repetition)

    session_repo_url = _validate_repo_url(session.get("repo_url"), "session.repo_url")
    raw_commit_sha = session.get("commit_sha")
    session_commit_sha = (
        None
        if raw_commit_sha is None
        else _validate_commit_sha(raw_commit_sha, "session.commit_sha")
    )
    raw_session_image = session.get("image")
    session_image = _safe_optional_image(raw_session_image)
    if raw_session_image is not None and session_image is None:
        _fail("session.image", "must be a bounded image token or null")
    raw_session_image_id = session.get("image_id")
    session_image_id = _safe_optional_image_id(raw_session_image_id)
    if raw_session_image_id is not None and session_image_id is None:
        _fail("session.image_id", "must be an immutable image ID or null")
    if _canonical_repo_identity(session_repo_url) != _canonical_repo_identity(
        case["repository_url"]
    ):
        _fail("session.repo_url", "does not match the selected manifest case")
    if session_commit_sha is not None and session_commit_sha != case["commit_sha"]:
        _fail("session.commit_sha", "does not match the selected manifest case")
    if (
        session_image is not None
        and session_image != manifest["runtime"]["compile_image"]
    ):
        _fail("session.image", "does not match the frozen manifest image")
    if (
        session_image_id is not None
        and session_image_id != manifest["runtime"]["image_id"]
    ):
        _fail("session.image_id", "does not match the frozen immutable image ID")

    raw_session_id = session.get("session_id")
    if not isinstance(raw_session_id, str) or not _SESSION_ID_RE.fullmatch(
        raw_session_id
    ):
        _fail(
            "session.session_id",
            "must be a 12-character hexadecimal compile-session ID",
        )
    submit_status, submit_evidence = _normalized_submit_event(
        _latest_submit_event(workflow_events)
    )
    completion_evidence = _normalized_completion_event(workflow_events)
    completion_failure_observed = completion_evidence is not None and (
        completion_evidence["event"] == "finalize.deferred"
        or completion_evidence["passed"] is False
    )
    if submit_status == "completed" and (
        session_commit_sha is None or session_image is None
    ):
        _fail(
            "session",
            "a completed submit requires frozen commit and image identity",
        )
    replay_attempt_id = (
        submit_evidence["replay_attempt_id"] if submit_evidence is not None else None
    )
    replay_evidence = _normalized_replay_attempt(
        _find_replay_attempt(session, replay_attempt_id)
    )
    image_identity_unavailable = (
        replay_evidence is not None
        and replay_evidence["failure_classification"] == "image_identity_unavailable"
    )
    if (
        submit_status == "completed"
        and session_image_id is None
        and not image_identity_unavailable
    ):
        _fail("session.image_id", "completed submit requires frozen image identity")

    candidate_status = None
    clean_replay_status = None
    if submit_status == "completed" and submit_evidence is not None:
        required_submit_values = (
            submit_evidence["status"],
            submit_evidence["artifact_count"],
            submit_evidence["failed_checks"],
            submit_evidence["candidate_status"],
            submit_evidence["replay_status"],
        )
        if any(value is None for value in required_submit_values):
            _fail("workflow.submit.completed", "is missing required bounded evidence")
        event_status = submit_evidence["status"]
        raw_candidate = submit_evidence["candidate_status"]
        event_replay_status = submit_evidence["replay_status"]
        event_failed_checks = submit_evidence["failed_checks"]
        event_artifact_count = submit_evidence["artifact_count"]
        if event_status == "passed" and (
            raw_candidate != "passed"
            or event_replay_status != "passed"
            or event_failed_checks != 0
            or event_artifact_count < 1
        ):
            _fail(
                "workflow.submit.completed",
                "passed status is inconsistent with candidate, replay, checks, or artifacts",
            )
        if event_status == "failed" and (
            event_replay_status == "passed" or event_failed_checks == 0
        ):
            _fail(
                "workflow.submit.completed",
                "failed status is inconsistent with replay or failed_checks",
            )
        if raw_candidate == "failed" and (
            event_status != "failed"
            or event_replay_status != "not_run"
            or replay_attempt_id is not None
        ):
            _fail(
                "workflow.submit.completed",
                "candidate rejection must not claim or link a clean replay",
            )
        if raw_candidate == "passed" and event_replay_status not in {
            "passed",
            "failed",
            "timed_out",
            "cancelled",
        }:
            _fail(
                "workflow.submit.completed",
                "candidate pass requires a terminal clean replay result",
            )
        candidate_status = (
            "pass"
            if raw_candidate == "passed"
            else "reject"
            if raw_candidate == "failed"
            else None
        )
        if event_replay_status == "not_run":
            if replay_attempt_id is not None:
                _fail(
                    "workflow.submit.completed",
                    "links a replay attempt while replay_status is not_run",
                )
        else:
            if replay_attempt_id is None or replay_evidence is None:
                _fail(
                    "workflow.submit.completed",
                    "does not link to its persisted replay attempt",
                )
            if (
                replay_evidence["attempt_id"] != replay_attempt_id
                or replay_evidence["status"] != event_replay_status
            ):
                _fail(
                    "session.replay_attempts",
                    "does not match the completed submit event",
                )
            expected_replay_identity = {
                "image": manifest["runtime"]["compile_image"],
                "image_id": manifest["runtime"]["image_id"],
                "commit_sha": case["commit_sha"],
                "timeout_seconds": manifest["runtime"]["replay_timeout_seconds"],
            }
            for identity_field, expected_value in expected_replay_identity.items():
                observed_value = replay_evidence[identity_field]
                if observed_value is not None and observed_value != expected_value:
                    _fail(
                        f"session.replay_attempts.{identity_field}",
                        "does not match the frozen manifest",
                    )
            if event_replay_status == "passed":
                expected_replay_identity = (
                    manifest["runtime"]["compile_image"],
                    manifest["runtime"]["image_id"],
                    case["commit_sha"],
                )
                actual_replay_identity = (
                    replay_evidence["image"],
                    replay_evidence["image_id"],
                    replay_evidence["commit_sha"],
                )
                if any(value is None for value in actual_replay_identity):
                    _fail(
                        "session.replay_attempts",
                        "passed replay evidence is missing frozen image or commit identity",
                    )
                if actual_replay_identity != expected_replay_identity:
                    _fail(
                        "session.replay_attempts",
                        "passed replay identity does not match the frozen manifest",
                    )
                complete_pass_evidence = (
                    replay_evidence["cleanup_succeeded"] is True
                    and replay_evidence["exit_code"] == 0
                    and replay_evidence["failure_classification"] is None
                    and replay_evidence["duration_seconds"] is not None
                    and replay_evidence["timeout_seconds"] is not None
                    and replay_evidence["recipe_sha256"] is not None
                )
                if not complete_pass_evidence:
                    _fail(
                        "session.replay_attempts",
                        "passed replay evidence is incomplete",
                    )
                clean_replay_status = "pass"
            elif event_replay_status in {"failed", "timed_out", "cancelled"}:
                clean_replay_status = "reject"

    verification = session.get("verification")
    verification_status = None
    verification_artifact_count = None
    verification_failed_checks = None
    if submit_status == "completed" and isinstance(verification, dict):
        verification_status = _safe_optional_enum(
            verification.get("status"), _VERIFICATION_STATUSES
        )
        verification_artifact_count = _safe_optional_int(
            verification.get("artifact_count"), minimum=0
        )
        verification_failed_checks = _safe_optional_int(
            verification.get("failed_checks"), minimum=0
        )
    artifact_count = (
        submit_evidence["artifact_count"]
        if submit_status == "completed" and submit_evidence is not None
        else None
    )
    normalized_artifacts = _normalized_artifacts(
        session, include=submit_status == "completed"
    )
    if submit_status == "completed" and submit_evidence is not None:
        if (
            verification_status is None
            or verification_artifact_count is None
            or verification_failed_checks is None
            or normalized_artifacts is None
            or artifact_count != len(normalized_artifacts)
            or artifact_count != verification_artifact_count
            or verification_failed_checks < submit_evidence["failed_checks"]
        ):
            _fail(
                "session.verification",
                "does not preserve the completed submit's bounded counts",
            )
        if submit_evidence["status"] == "failed" and verification_status != "failed":
            _fail(
                "session.verification.status",
                "must be failed for a rejected submit",
            )
        if (
            submit_evidence["status"] == "passed"
            and verification_status == "failed"
            and not completion_failure_observed
        ):
            _fail(
                "session.verification.status",
                "post-submit failure requires bounded completion evidence",
            )
    if candidate_status == "pass":
        candidate_snapshot_complete = (
            verification_status in {"passed", "failed"}
            and artifact_count is not None
            and artifact_count >= 1
            and normalized_artifacts is not None
            and len(normalized_artifacts) == artifact_count
        )
        if candidate_snapshot_complete:
            relative_paths: set[str] = set()
            for artifact in normalized_artifacts:
                relative_path = artifact["relative_path"]
                artifact_complete = (
                    relative_path is not None
                    and artifact["artifact_type"] is not None
                    and artifact["size_bytes"] is not None
                    and artifact["size_bytes"] > 0
                    and artifact["sha256"] is not None
                )
                if artifact["artifact_type"] == "executable":
                    artifact_complete = (
                        artifact_complete
                        and artifact["smoke_exit_code"] == 0
                        and artifact["smoke_output_sha256"] is not None
                    )
                if not artifact_complete or relative_path in relative_paths:
                    candidate_snapshot_complete = False
                    break
                relative_paths.add(relative_path)
        if not candidate_snapshot_complete:
            _fail(
                "session.artifacts",
                "candidate pass requires a complete, unique, bounded artifact snapshot",
            )
    finalized = isinstance(session.get("finalized_at"), str) and bool(
        session["finalized_at"]
    )
    session_status = _safe_optional_enum(session.get("status"), _SESSION_STATUSES)
    replay_cleanup = (
        replay_evidence["cleanup_succeeded"] if replay_evidence is not None else None
    )

    run_id = session.get("run_id")
    safe_run_id = (
        run_id
        if isinstance(run_id, str)
        and len(run_id) <= 160
        and _RUN_ID_RE.fullmatch(run_id)
        else None
    )
    if session_status == "completed" and (
        candidate_status != "pass" or clean_replay_status != "pass"
    ):
        _fail(
            "session.status",
            "completed requires candidate and clean replay acceptance",
        )
    terminal_finalize_observed = (
        completion_evidence is not None
        and completion_evidence["event"] == "finalize.completed"
        and completion_evidence["reason"] == session_status
        and finalized
    )
    if (
        candidate_status == "pass"
        and clean_replay_status == "pass"
        and session_status in {"failed", "cancelled", "timed_out"}
        and not (completion_failure_observed or terminal_finalize_observed)
    ):
        _fail(
            "session.status",
            "post-submit terminal failure requires bounded completion evidence",
        )
    build_system = _safe_optional_enum(session.get("build_system"), _BUILD_SYSTEMS)
    if build_system is not None and build_system != case["build_system"]:
        _fail("session.build_system", "does not match the selected manifest case")
    source = {
        "session_id": raw_session_id,
        "run_id": safe_run_id,
        "repository_url": case["repository_url"],
        "commit_sha": session_commit_sha,
        "build_system": build_system,
        "image_id": session_image_id,
    }
    outcome = {
        "session_status": session_status,
        "submit_status": submit_status,
        "candidate_status": candidate_status,
        "clean_replay_status": clean_replay_status,
        "replay_failure_classification": replay_evidence["failure_classification"]
        if replay_evidence is not None
        else None,
        "replay_cleanup_succeeded": replay_cleanup,
        "verification_status": verification_status,
        "artifact_count": artifact_count,
        "finalized": finalized,
        "oracle_match": None,
    }
    replay_failure_classification = (
        replay_evidence["failure_classification"]
        if replay_evidence is not None
        else None
    )
    clean_replay_failure = None
    if clean_replay_status == "pass":
        clean_replay_failure = False
    elif (
        clean_replay_status == "reject"
        and replay_failure_classification != "cleanup_failed"
    ):
        clean_replay_failure = True
    cleanup_failure = None
    if replay_evidence is not None:
        if replay_failure_classification == "cleanup_failed" or replay_cleanup is False:
            cleanup_failure = True
        elif replay_cleanup is True:
            cleanup_failure = False
    failure_attribution = {
        "model_endpoint": None,
        "agent": None,
        "build": None,
        "candidate_generation": (
            candidate_status == "reject" if candidate_status is not None else None
        ),
        "clean_replay": clean_replay_failure,
        "cleanup": cleanup_failure,
        "completion": (
            False
            if session_status == "completed"
            else True
            if completion_failure_observed
            else None
        ),
    }
    evidence = {
        "submit_event": submit_evidence,
        "replay_attempt": replay_evidence,
        "completion_event": completion_evidence,
        "command_summary": _command_summary(session),
        "artifacts": normalized_artifacts,
        "session_duration_seconds": _duration_seconds(
            session.get("created_at"),
            session.get("completed_at") or session.get("finalized_at"),
        ),
    }
    record = {
        "schema_version": SCHEMA_VERSION,
        "document_type": RUN_RECORD_DOCUMENT_TYPE,
        "benchmark_id": manifest["benchmark"]["id"],
        "manifest_sha256": manifest_sha256(manifest),
        "manifest_canonicalization": CANONICAL_JSON_ALGORITHM,
        "recorded_at": datetime.now(UTC).isoformat(),
        "case_id": case_id,
        "condition": condition_id,
        "repetition": repetition,
        "source": source,
        "outcome": outcome,
        "failure_attribution": failure_attribution,
        "evidence": evidence,
    }
    return validate_run_record(record)


def _record_slot(document: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    return (
        document.get("benchmark_id"),
        document.get("case_id"),
        document.get("condition"),
        document.get("repetition"),
    )


def _preflight_duplicate(output: Path, slot: tuple[Any, Any, Any, Any]) -> None:
    if not output.exists():
        return
    if output.is_symlink() or not output.is_file():
        raise BenchmarkError("output: must be a regular JSONL file")
    try:
        lines = output.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise BenchmarkError("output: could not read existing JSONL records") from exc
    seen_slots: set[tuple[Any, Any, Any, Any]] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            existing = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BenchmarkError(
                f"output: existing line {line_number} is not valid JSON"
            ) from exc
        if (
            not isinstance(existing, dict)
            or existing.get("document_type") != RUN_RECORD_DOCUMENT_TYPE
        ):
            _fail(f"output[{line_number}]", "is not a run_record")
        try:
            validate_run_record(existing)
        except BenchmarkError as exc:
            raise BenchmarkError(
                f"output: existing line {line_number} is not a valid run_record"
            ) from exc
        existing_slot = _record_slot(existing)
        if existing_slot in seen_slots:
            raise BenchmarkError(
                f"output: existing line {line_number} duplicates an earlier slot"
            )
        seen_slots.add(existing_slot)
        if existing_slot == slot:
            raise BenchmarkError(
                "output: duplicate benchmark/case/condition/repetition slot"
            )


def append_run_record(output: Path, record: dict[str, Any]) -> None:
    validate_run_record(record)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BenchmarkError("output: could not create the output directory") from exc
    lock_path = output.with_name(f".{output.name}.lock")
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise BenchmarkError("output: another recorder holds the append lock") from exc
    except OSError as exc:
        raise BenchmarkError("output: could not create the append lock") from exc
    try:
        os.close(lock_fd)
        _preflight_duplicate(output, _record_slot(record))
        payload = (
            json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        try:
            existing = output.read_bytes() if output.exists() else b""
        except OSError as exc:
            raise BenchmarkError("output: could not read existing JSONL bytes") from exc
        if existing and not existing.endswith(b"\n"):
            raise BenchmarkError("output: existing JSONL must end with a newline")
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=output.parent,
                prefix=f".{output.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_path = stream.name
                stream.write(existing)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, output)
            if os.name == "posix":
                directory_fd = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        except OSError as exc:
            raise BenchmarkError(
                "output: could not atomically append the run record"
            ) from exc
        finally:
            if temporary_path:
                try:
                    Path(temporary_path).unlink(missing_ok=True)
                except OSError:
                    pass
    finally:
        try:
            lock_path.unlink()
        except OSError:
            pass


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser(
        "validate-manifest", help="validate and hash a benchmark manifest"
    )
    validate_parser.add_argument("manifest", type=Path)

    record_parser = subparsers.add_parser(
        "record", help="normalize one compile session into append-only JSONL"
    )
    record_parser.add_argument("--manifest", type=Path, required=True)
    record_parser.add_argument("--case-id", required=True)
    record_parser.add_argument("--condition", required=True)
    record_parser.add_argument("--repetition", type=int, required=True)
    record_parser.add_argument("--session-json", type=Path, required=True)
    record_parser.add_argument("--workflow-log", type=Path)
    record_parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        manifest = validate_manifest(load_json_document(args.manifest))
        verify_frozen_components(manifest, REPOSITORY_ROOT)
        if args.command == "validate-manifest":
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

        session = load_json_document(args.session_json)
        raw_session_id = session.get("session_id")
        if not isinstance(raw_session_id, str):
            _fail("session.session_id", "must be a string")
        workflow_path = (
            args.workflow_log or args.session_json.parent / "logs" / "workflow.log"
        )
        events = _load_workflow_events(workflow_path, raw_session_id)
        record = build_run_record(
            manifest=manifest,
            case_id=args.case_id,
            condition_id=args.condition,
            repetition=args.repetition,
            session=session,
            workflow_events=events,
        )
        append_run_record(args.output, record)
        print(json.dumps(record, ensure_ascii=False, sort_keys=True))
        return 0
    except BenchmarkError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
