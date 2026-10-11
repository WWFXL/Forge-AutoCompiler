#!/usr/bin/env python3
"""Issue #415 自然构建失败 Linux applicability source catalog v3。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import jsonschema

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
IDENTITY = "cpp-jev-natural-failure-linux-applicability-v3"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests" / f"{IDENTITY}.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-jev-natural-failure-linux-applicability-v3.schema.json"
DEFAULT_REPORT_JSON_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.json"
DEFAULT_REPORT_MARKDOWN_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.md"

SYSTEMS = ("cmake", "make", "autotools")
NETWORK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cmake_fetch_content", re.compile(r"\bFetchContent_(?:Declare|Populate|MakeAvailable)\s*\(", re.IGNORECASE)),
    ("cmake_external_project", re.compile(r"\bExternalProject_Add\s*\(", re.IGNORECASE)),
    ("cmake_file_download", re.compile(r"\bfile\s*\(\s*DOWNLOAD\b", re.IGNORECASE)),
    ("git_clone", re.compile(r"\bgit\s+clone\b", re.IGNORECASE)),
    ("curl_command", re.compile(r"(?:^|[;&|]\s*)curl\s+", re.IGNORECASE | re.MULTILINE)),
    ("wget_command", re.compile(r"(?:^|[;&|]\s*)wget\s+", re.IGNORECASE | re.MULTILINE)),
)
ENTRY_SIGNAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("apple_target_triple", re.compile(r"-target\s+[^\s]*apple-(?:macos|darwin)", re.IGNORECASE)),
    ("apple_forced_sysroot", re.compile(r"(?:CMAKE_OSX_SYSROOT|(?:^|\s)-isysroot\s+[^\s]*MacOSX)", re.IGNORECASE | re.MULTILINE)),
    ("apple_toolchain", re.compile(r"\b(?:xcodebuild|xcrun)\b", re.IGNORECASE)),
    ("apple_framework_link", re.compile(r"(?:^|[\s\"'])-framework\s+[A-Za-z]", re.IGNORECASE | re.MULTILINE)),
    ("macho_universal", re.compile(r"\blipo\s+(?:-[A-Za-z-]+\s+)*", re.IGNORECASE)),
    ("windows_msbuild", re.compile(r"\b(?:msbuild(?:\.exe)?|devenv(?:\.com|\.exe)?|nmake(?:\.exe)?)\b", re.IGNORECASE)),
    (
        "windows_msvc_compiler",
        re.compile(
            r"(?:^|\n)\s*(?:(?:CC|CXX)\s*[:?+]?=\s*cl(?:\.exe)?\b|(?:LD|LINK)\s*[:?+]?=\s*link(?:\.exe)?\b|(?:cl|link)(?:\.exe)?\s+/[A-Za-z])",
            re.IGNORECASE,
        ),
    ),
    ("windows_wdk", re.compile(r"\b(?:WindowsDriverKit|WDKContentRoot|KernelModeDriver|WDM)\b", re.IGNORECASE)),
    ("windows_forced_target", re.compile(r"CMAKE_SYSTEM_NAME\s+(?:\"?Windows\"?)", re.IGNORECASE)),
    ("bare_metal_toolchain", re.compile(r"\b(?:arm-none-eabi|avr|riscv(?:32|64)?-(?:unknown-)?elf|xtensa[^\s]*-elf)-(?:(?:g|clang\+*)cc|g\+\+|ld|ar)\b", re.IGNORECASE)),
    ("kernel_default_endpoint", re.compile(r"(?:^|\s)(?:bzImage|vmlinux|uImage)(?:\s|$|:)", re.IGNORECASE | re.MULTILINE)),
    ("firmware_default_endpoint", re.compile(r"(?:^|\s)(?:flash|firmware)\s*:\s*[^\n]*(?:\.hex|\.bin|\.elf)", re.IGNORECASE | re.MULTILINE)),
)
LINUX_ENTRY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "explicit_linux_branch",
        re.compile(
            r"(?:\b(?:if|ifeq|elseif|elif|case)\b|CMAKE_(?:HOST_)?SYSTEM_NAME|UNAME[_A-Z]*)[^\n]{0,120}(?:Linux|__linux__)",
            re.IGNORECASE,
        ),
    ),
    ("uname_linux_branch", re.compile(r"(?:uname\s+-s|UNAME_S)[^\n]{0,120}Linux", re.IGNORECASE)),
    ("linux_target_triple", re.compile(r"\b(?:x86_64|aarch64|arm|i[3-6]86)-[^\s]*linux(?:-gnu)?\b", re.IGNORECASE)),
)
DOCUMENT_EXCLUSION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("document_macos_only", re.compile(r"\b(?:macOS|Mac OS X|OS X)[ -]only\b|\bonly (?:supports?|runs? on) (?:macOS|Mac OS X|OS X)\b", re.IGNORECASE)),
    ("document_windows_only", re.compile(r"\bWindows[ -]only\b|\bonly (?:supports?|runs? on) Windows\b", re.IGNORECASE)),
    ("document_bare_metal_only", re.compile(r"\b(?:bare[ -]metal|firmware)[ -]only\b|\bonly (?:supports?|targets?) (?:bare[ -]metal|firmware)\b", re.IGNORECASE)),
)
DOCUMENT_NAME_PATTERN = re.compile(r"^(?:README(?:\..+)?|BUILD(?:ING)?(?:\..+)?|INSTALL(?:\..+)?)$", re.IGNORECASE)
STRONG_EXCLUSION_SIGNALS = frozenset(
    {
        "apple_target_triple",
        "apple_forced_sysroot",
        "apple_toolchain",
        "macho_universal",
        "windows_msbuild",
        "windows_msvc_compiler",
        "windows_wdk",
        "windows_forced_target",
        "bare_metal_toolchain",
        "kernel_default_endpoint",
        "firmware_default_endpoint",
    }
)
GITHUB_URL_PATTERN = re.compile(r"^https://github\.com/([^/]+)/([^/#?]+)", re.IGNORECASE)
PROJECT_FAMILY_PATTERN = re.compile(r"^github\.com/([^/]+)/([^/]+)$", re.IGNORECASE)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON 根必须是 object: {path}")
    return value


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(payload)


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _run(
    argv: list[str],
    *,
    cwd: Path = REPO_ROOT,
    timeout: int | float | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _git(*args: str) -> str:
    completed = _run(["git", *args])
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git command failed")
    return completed.stdout.strip()


def _path_from_manifest(value: str) -> Path:
    path = (REPO_ROOT / value).resolve()
    if path != REPO_ROOT and REPO_ROOT not in path.parents:
        raise ValueError(f"manifest 路径越界: {value}")
    return path


def _walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_strings(item)


def _normalize_family(value: str) -> str | None:
    github_match = GITHUB_URL_PATTERN.match(value)
    if github_match:
        owner, repository = github_match.groups()
    else:
        family_match = PROJECT_FAMILY_PATTERN.match(value)
        if not family_match:
            return None
        owner, repository = family_match.groups()
    repository = re.sub(r"\.git$", "", repository, flags=re.IGNORECASE)
    return f"{owner}/{repository}".lower()


def historical_project_families(revision: str) -> list[str]:
    output = _git(
        "ls-tree",
        "-r",
        "--name-only",
        revision,
        "--",
        "benchmarks/fixtures",
        "benchmarks/manifests",
    )
    families: set[str] = set()
    for relative in output.splitlines():
        if not relative.endswith(".json"):
            continue
        raw = _git("show", f"{revision}:{relative}")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"历史 JSON 无法解析: {relative}") from exc
        for text in _walk_strings(value):
            family = _normalize_family(text)
            if family:
                families.add(family)
    return sorted(families)


def observed_v2_project_families(path: Path) -> list[str]:
    report = _load_json(path)
    repositories = report.get("repositories")
    if not isinstance(repositories, list):
        raise ValueError("v2 catalog repositories missing")
    families = {str(row["project_family"]).lower() for row in repositories if isinstance(row, dict) and isinstance(row.get("project_family"), str)}
    if len(families) != len(repositories):
        raise ValueError("v2 catalog project families are missing or duplicated")
    return sorted(families)


def exclusion_project_families(manifest: dict[str, Any]) -> list[str]:
    history = historical_project_families(manifest["history_exclusion"]["revision"])
    observed_path = _path_from_manifest(manifest["history_exclusion"]["v2_catalog_path"])
    if _sha256_file(observed_path) != manifest["history_exclusion"]["v2_catalog_sha256"]:
        raise ValueError("v2_catalog_hash_mismatch")
    return sorted(set(history) | set(observed_v2_project_families(observed_path)))


def validate_protocol() -> dict[str, Any]:
    manifest = _load_json(MANIFEST_PATH)
    schema = _load_json(SCHEMA_PATH)
    jsonschema.Draft202012Validator(schema).validate(manifest)
    errors: list[str] = []

    if [row["language"] for row in manifest["search"]["queries"]] != ["C", "C++"]:
        errors.append("search_language_order_mismatch")
    if [row["id"] for row in manifest["search"]["queries"]] != ["c", "cpp"]:
        errors.append("search_id_order_mismatch")

    history = exclusion_project_families(manifest)
    expected_history = manifest["history_exclusion"]
    if len(history) != expected_history["project_family_count"]:
        errors.append("history_project_family_count_mismatch")
    if _canonical_sha256(history) != expected_history["canonical_sha256"]:
        errors.append("history_project_family_hash_mismatch")

    for relative, expected_hash in manifest["parents"].items():
        parent = _path_from_manifest(relative)
        if not parent.is_file() or _sha256_file(parent) != expected_hash:
            errors.append(f"parent_hash_mismatch:{relative}")

    source_contract = manifest["source_contract"]
    if tuple(source_contract["systems"]) != SYSTEMS:
        errors.append("system_order_mismatch")
    if set(source_contract["network_signal_names"]) != {name for name, _ in NETWORK_PATTERNS}:
        errors.append("network_signal_contract_mismatch")
    if set(source_contract["entry_signal_names"]) != {name for name, _ in ENTRY_SIGNAL_PATTERNS}:
        errors.append("entry_signal_contract_mismatch")
    if set(source_contract["linux_signal_names"]) != {name for name, _ in LINUX_ENTRY_PATTERNS}:
        errors.append("linux_signal_contract_mismatch")
    if set(source_contract["document_exclusion_signal_names"]) != {name for name, _ in DOCUMENT_EXCLUSION_PATTERNS}:
        errors.append("document_signal_contract_mismatch")
    if source_contract["submodules_allowed"]:
        errors.append("submodule_contract_mismatch")

    fixture_path = _path_from_manifest(manifest["regression_fixture"]["path"])
    if not fixture_path.is_file() or _sha256_file(fixture_path) != manifest["regression_fixture"]["sha256"]:
        errors.append("regression_fixture_hash_mismatch")
    else:
        fixture = _load_json(fixture_path)
        for case in fixture.get("cases", []):
            decision = assess_linux_applicability(
                system=case["system"],
                entry_files=[{"path": case["entry_path"], "text": case["entry_text"]}],
                document_files=[{"path": row["path"], "text": row["text"]} for row in case.get("documents", [])],
            )
            if decision["classification"] != case["expected_classification"]:
                errors.append(f"regression_classification_mismatch:{case['id']}")
            expected_signals = set(case.get("expected_entry_signals", []))
            if not expected_signals.issubset(decision["entry_signals"]):
                errors.append(f"regression_signal_mismatch:{case['id']}")

    authorization = manifest["authorization"]
    authorized = bool(authorization["execution"])
    if authorization["formal_attempts"] != (1 if authorized else 0):
        errors.append("formal_attempt_authorization_mismatch")
    if bool(authorization["formal_evidence_write"]) != authorized:
        errors.append("formal_evidence_authorization_mismatch")
    if authorized and not manifest["implementation_revision"]:
        errors.append("authorized_without_implementation_revision")
    if any(
        manifest["budget"][key]
        for key in (
            "build_commands",
            "docker_containers",
            "credential_reads",
            "provider_requests",
            "model_tokens",
        )
    ):
        errors.append("zero_execution_boundary_violated")

    result = {
        "identity": IDENTITY,
        "valid": not errors,
        "errors": errors,
        "authorization": "execution" if authorized else "candidate_only",
        "manifest_canonical_sha256": _canonical_sha256(manifest),
        "history_project_family_count": len(history),
        "history_project_family_canonical_sha256": _canonical_sha256(history),
    }
    if errors:
        raise ValueError(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def preflight(*, require_authorized: bool) -> dict[str, Any]:
    protocol = validate_protocol()
    manifest = _load_json(MANIFEST_PATH)
    errors: list[str] = []
    branch = _git("branch", "--show-current")
    head = _git("rev-parse", "HEAD")
    if branch != manifest["branch"]:
        errors.append("branch_mismatch")
    if _run(["git", "merge-base", "--is-ancestor", manifest["design_revision"], head]).returncode != 0:
        errors.append("design_revision_not_ancestor")
    implementation = manifest["implementation_revision"]
    if implementation and _run(["git", "merge-base", "--is-ancestor", implementation, head]).returncode != 0:
        errors.append("implementation_revision_not_ancestor")
    if require_authorized and not manifest["authorization"]["execution"]:
        errors.append("execution_not_authorized")
    if require_authorized and _git("status", "--porcelain"):
        errors.append("worktree_not_clean")

    evidence_root = _path_from_manifest(manifest["evidence"]["root"])
    report_json = _path_from_manifest(manifest["evidence"]["report_json"])
    report_markdown = _path_from_manifest(manifest["evidence"]["report_markdown"])
    if evidence_root.exists():
        errors.append("evidence_root_already_exists")
    if report_json.exists() or report_markdown.exists():
        errors.append("report_already_exists")

    gh_version = _run(["gh", "--version"], timeout=15)
    if gh_version.returncode != 0:
        errors.append("gh_cli_unavailable")
    rate = _run(["gh", "api", "rate_limit", "--jq", ".resources.core.remaining"], timeout=30)
    if rate.returncode != 0:
        errors.append("github_api_unavailable")

    return {
        **protocol,
        "ready": not errors,
        "errors": errors,
        "branch": branch,
        "head": head,
        "github_core_rate_remaining": int(rate.stdout.strip()) if rate.returncode == 0 else None,
    }


def find_network_signals(text: str) -> list[str]:
    return [name for name, pattern in NETWORK_PATTERNS if pattern.search(text)]


def find_entry_signals(text: str) -> list[str]:
    return [name for name, pattern in ENTRY_SIGNAL_PATTERNS if pattern.search(text)]


def find_linux_signals(text: str) -> list[str]:
    return [name for name, pattern in LINUX_ENTRY_PATTERNS if pattern.search(text)]


def find_document_exclusion_signals(text: str) -> list[str]:
    return [name for name, pattern in DOCUMENT_EXCLUSION_PATTERNS if pattern.search(text)]


def assess_linux_applicability(
    *,
    system: str,
    entry_files: list[dict[str, Any]],
    document_files: list[dict[str, Any]],
) -> dict[str, Any]:
    readable_entries = [row for row in entry_files if isinstance(row.get("text"), str)]
    entry_signals = sorted({signal for row in readable_entries for signal in find_entry_signals(row["text"])})
    linux_signals = sorted({signal for row in readable_entries for signal in find_linux_signals(row["text"])})
    readable_documents = [row for row in document_files if isinstance(row.get("text"), str)]
    document_errors = sorted({str(row["error"]) for row in document_files if isinstance(row.get("error"), str)})
    document_exclusion_signals = sorted({signal for row in readable_documents for signal in find_document_exclusion_signals(row["text"])})
    document_linux_signals = sorted({signal for row in readable_documents for signal in find_linux_signals(row["text"])})
    strong_exclusions = sorted(set(entry_signals) & STRONG_EXCLUSION_SIGNALS)

    if not readable_entries:
        classification = "ambiguous"
        reason = "entrypoint_unreadable"
    elif linux_signals:
        classification = "linux_applicable"
        reason = "explicit_linux_entry_path"
    elif strong_exclusions:
        classification = "platform_ineligible"
        reason = "exclusive_entry_without_linux_path"
    elif document_exclusion_signals:
        classification = "platform_ineligible"
        reason = "document_declares_exclusive_platform"
    elif document_errors:
        classification = "ambiguous"
        reason = "document_unreadable"
    else:
        classification = "linux_applicable"
        reason = "portable_entry_without_exclusive_signal"

    return {
        "system": system,
        "classification": classification,
        "reason": reason,
        "entry_signals": entry_signals,
        "strong_exclusion_signals": strong_exclusions,
        "linux_entry_signals": linux_signals,
        "document_exclusion_signals": document_exclusion_signals,
        "document_linux_signals": document_linux_signals,
        "document_errors": document_errors,
        "entry_paths": [row.get("path") for row in entry_files],
        "document_paths": [row.get("path") for row in document_files],
    }


def supported_systems(root_paths: set[str], root_markers: dict[str, list[str]]) -> list[str]:
    return [system for system in SYSTEMS if any(marker in root_paths for marker in root_markers[system])]


def _api_json(endpoint: str, timeout: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    started = time.monotonic()
    try:
        completed = _run(["gh", "api", endpoint], timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return None, {
            "kind": "timeout",
            "endpoint": endpoint,
            "elapsed_seconds": time.monotonic() - started,
            "stdout_sha256": _sha256_bytes((exc.stdout or "").encode()),
            "stderr_sha256": _sha256_bytes((exc.stderr or "").encode()),
        }
    if completed.returncode != 0:
        return None, {
            "kind": "api_error",
            "endpoint": endpoint,
            "exit_code": completed.returncode,
            "elapsed_seconds": time.monotonic() - started,
            "stdout_sha256": _sha256_bytes(completed.stdout.encode()),
            "stderr_sha256": _sha256_bytes(completed.stderr.encode()),
            "stderr_preview": completed.stderr[:500],
        }
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None, {
            "kind": "invalid_json",
            "endpoint": endpoint,
            "elapsed_seconds": time.monotonic() - started,
            "stdout_sha256": _sha256_bytes(completed.stdout.encode()),
            "stderr_sha256": _sha256_bytes(completed.stderr.encode()),
        }
    if not isinstance(value, dict):
        return None, {"kind": "unexpected_json_type", "endpoint": endpoint}
    return value, None


def _decode_blob(value: dict[str, Any], maximum_bytes: int) -> tuple[str | None, str | None]:
    if value.get("encoding") != "base64" or not isinstance(value.get("content"), str):
        return None, "unsupported_blob_encoding"
    try:
        payload = base64.b64decode(value["content"], validate=False)
    except (ValueError, TypeError):
        return None, "invalid_blob_base64"
    if len(payload) > maximum_bytes:
        return None, "entry_blob_too_large"
    return payload.decode("utf-8", errors="replace"), None


def catalog_repository(candidate: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    timeout = int(manifest["budget"]["request_timeout_seconds"])
    family = candidate["project_family"]
    full_name = candidate["full_name"]
    default_branch = candidate.get("default_branch")
    base = {
        "project_family": family,
        "full_name": full_name,
        "repository_url": candidate["repository_url"],
        "search_query_ids": candidate["search_query_ids"],
        "search_metadata": candidate["search_metadata"],
    }
    if not isinstance(default_branch, str) or not default_branch:
        return {**base, "classification": "infrastructure_failure", "reason": "default_branch_missing"}

    commit_endpoint = f"repos/{full_name}/commits/{quote(default_branch, safe='')}"
    commit, error = _api_json(commit_endpoint, timeout)
    if error:
        return {**base, "classification": "infrastructure_failure", "reason": "commit_lookup_failed", "error": error}
    assert commit is not None
    commit_sha = commit.get("sha")
    if not isinstance(commit_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        return {**base, "classification": "infrastructure_failure", "reason": "invalid_commit_sha"}

    tree_endpoint = f"repos/{full_name}/git/trees/{commit_sha}"
    tree, error = _api_json(tree_endpoint, timeout)
    if error:
        return {
            **base,
            "commit_sha": commit_sha,
            "classification": "infrastructure_failure",
            "reason": "root_tree_lookup_failed",
            "error": error,
        }
    assert tree is not None
    entries = tree.get("tree")
    if not isinstance(entries, list) or tree.get("truncated") is True:
        return {
            **base,
            "commit_sha": commit_sha,
            "classification": "infrastructure_failure",
            "reason": "invalid_or_truncated_root_tree",
        }
    root_blobs = {row["path"]: row for row in entries if isinstance(row, dict) and row.get("type") == "blob" and isinstance(row.get("path"), str)}
    root_paths = set(root_blobs)
    observed_systems = supported_systems(root_paths, manifest["source_contract"]["root_markers"])
    result = {
        **base,
        "commit_sha": commit_sha,
        "commit_committed_at": commit.get("commit", {}).get("committer", {}).get("date"),
        "root_tree_sha": tree.get("sha"),
        "root_entry_count": len(entries),
        "root_paths_sha256": _canonical_sha256(sorted(root_paths)),
        "observed_systems": observed_systems,
        "eligible_systems": [],
        "system_scans": {},
        "document_scans": [],
    }
    if ".gitmodules" in root_paths:
        return {**result, "classification": "source_ineligible", "reason": "submodule_manifest_present"}
    if not observed_systems:
        return {**result, "classification": "source_ineligible", "reason": "root_entrypoint_missing"}

    maximum_bytes = int(manifest["source_contract"]["max_entry_blob_bytes"])
    maximum_documents = int(manifest["source_contract"]["max_document_files"])
    document_inputs: list[dict[str, Any]] = []
    document_paths = sorted(path for path in root_blobs if DOCUMENT_NAME_PATTERN.fullmatch(path))[:maximum_documents]
    for path in document_paths:
        entry = root_blobs[path]
        if int(entry.get("size") or 0) > maximum_bytes:
            document_inputs.append({"path": path, "error": "document_blob_too_large"})
            result["document_scans"].append({"path": path, "blob_sha": entry.get("sha"), "size": entry.get("size"), "error": "document_blob_too_large"})
            continue
        blob_endpoint = f"repos/{full_name}/git/blobs/{entry['sha']}"
        blob, error = _api_json(blob_endpoint, timeout)
        if error:
            return {
                **result,
                "classification": "infrastructure_failure",
                "reason": "document_blob_lookup_failed",
                "failed_document": path,
                "error": error,
            }
        assert blob is not None
        text, decode_error = _decode_blob(blob, maximum_bytes)
        if decode_error:
            document_inputs.append({"path": path, "error": decode_error})
            result["document_scans"].append({"path": path, "blob_sha": entry.get("sha"), "size": entry.get("size"), "error": decode_error})
            continue
        assert text is not None
        payload = text.encode("utf-8")
        document_inputs.append({"path": path, "text": text})
        result["document_scans"].append(
            {
                "path": path,
                "blob_sha": entry.get("sha"),
                "size": len(payload),
                "content_sha256": _sha256_bytes(payload),
                "exclusion_signals": find_document_exclusion_signals(text),
                "linux_signals": find_linux_signals(text),
            }
        )

    for system in observed_systems:
        markers = [marker for marker in manifest["source_contract"]["root_markers"][system] if marker in root_blobs]
        files: list[dict[str, Any]] = []
        entry_inputs: list[dict[str, Any]] = []
        network_signals: set[str] = set()
        scan_errors: set[str] = set()
        for marker in markers:
            entry = root_blobs[marker]
            if int(entry.get("size") or 0) > maximum_bytes:
                files.append({"path": marker, "blob_sha": entry.get("sha"), "size": entry.get("size"), "error": "entry_blob_too_large"})
                scan_errors.add("entry_blob_unreadable")
                continue
            blob_endpoint = f"repos/{full_name}/git/blobs/{entry['sha']}"
            blob, error = _api_json(blob_endpoint, timeout)
            if error:
                return {
                    **result,
                    "classification": "infrastructure_failure",
                    "reason": "entry_blob_lookup_failed",
                    "failed_system": system,
                    "failed_entry": marker,
                    "error": error,
                }
            assert blob is not None
            text, decode_error = _decode_blob(blob, maximum_bytes)
            if decode_error:
                files.append({"path": marker, "blob_sha": entry.get("sha"), "size": entry.get("size"), "error": decode_error})
                scan_errors.add("entry_blob_unreadable")
                continue
            assert text is not None
            signals = find_network_signals(text)
            network_signals.update(signals)
            entry_inputs.append({"path": marker, "text": text})
            files.append(
                {
                    "path": marker,
                    "blob_sha": entry.get("sha"),
                    "size": len(text.encode("utf-8")),
                    "content_sha256": _sha256_bytes(text.encode("utf-8")),
                    "network_signals": signals,
                    "entry_signals": find_entry_signals(text),
                    "linux_signals": find_linux_signals(text),
                }
            )
        applicability = assess_linux_applicability(
            system=system,
            entry_files=entry_inputs,
            document_files=document_inputs,
        )
        eligible = not network_signals and not scan_errors and applicability["classification"] == "linux_applicable"
        result["system_scans"][system] = {
            "entry_files": files,
            "network_signals": sorted(network_signals),
            "scan_errors": sorted(scan_errors),
            "applicability": applicability,
            "eligible": eligible,
        }
        if eligible:
            result["eligible_systems"].append(system)

    if result["eligible_systems"]:
        result["classification"] = "source_eligible"
        result["reason"] = "linux_applicability_contract_passed"
    else:
        result["classification"] = "source_ineligible"
        classifications = {scan.get("applicability", {}).get("classification") for scan in result["system_scans"].values()}
        if "platform_ineligible" in classifications:
            result["reason"] = "platform_or_endpoint_ineligible"
        elif "ambiguous" in classifications:
            result["reason"] = "linux_applicability_ambiguous"
        else:
            result["reason"] = "network_or_entry_blob_signal"
    return result


def catalog_repositories(
    candidates: list[dict[str, Any]],
    catalog_one: Callable[[dict[str, Any]], dict[str, Any]],
    on_result: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        try:
            result = catalog_one(candidate)
        except Exception as exc:
            result = {
                "project_family": candidate["project_family"],
                "full_name": candidate["full_name"],
                "repository_url": candidate["repository_url"],
                "classification": "infrastructure_failure",
                "reason": "unhandled_repository_exception",
                "error": {"kind": type(exc).__name__, "message": str(exc)[:500]},
            }
        results.append(result)
        if on_result:
            on_result(result)
    return results


def _edge_key(seed: str, family: str, system: str) -> str:
    return _sha256_bytes(f"{seed}\0{family}\0{system}".encode())


def _selection_key(seed: str, family: str) -> str:
    return _sha256_bytes(f"{seed}\0{family}".encode())


def allocate_projects(results: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    seed = manifest["selection"]["seed"]
    required = int(manifest["selection"]["required_per_system"])
    eligible = [row for row in results if row.get("classification") == "source_eligible"]
    allocations: dict[str, list[dict[str, Any]]] = {system: [] for system in SYSTEMS}
    used: set[str] = set()

    while any(len(allocations[system]) < required for system in SYSTEMS):
        pending = [system for system in SYSTEMS if len(allocations[system]) < required]
        available = {system: [row for row in eligible if row["project_family"] not in used and system in row["eligible_systems"]] for system in pending}
        system = min(pending, key=lambda item: (len(available[item]), SYSTEMS.index(item)))
        if not available[system]:
            break
        chosen = min(available[system], key=lambda row: _edge_key(seed, row["project_family"], system))
        used.add(chosen["project_family"])
        allocations[system].append(
            {
                "project_family": chosen["project_family"],
                "full_name": chosen["full_name"],
                "repository_url": chosen["repository_url"],
                "commit_sha": chosen["commit_sha"],
                "commit_committed_at": chosen.get("commit_committed_at"),
                "selected_build_system": system,
                "edge_key": _edge_key(seed, chosen["project_family"], system),
                "selection_key": _selection_key(seed, chosen["project_family"]),
            }
        )

    flat: list[dict[str, Any]] = []
    for system in SYSTEMS:
        ordered = sorted(allocations[system], key=lambda row: row["selection_key"])
        for rank, row in enumerate(ordered, start=1):
            flat.append({**row, "system_rank": rank})
    counts = {system: len(allocations[system]) for system in SYSTEMS}
    passed = all(counts[system] == required for system in SYSTEMS)
    return {
        "passed": passed,
        "decision": manifest["selection"]["pass_decision"] if passed else manifest["selection"]["fail_decision"],
        "required_per_system": required,
        "counts": counts,
        "failed_requirements": [f"{system}:{counts[system]}<{required}" for system in SYSTEMS if counts[system] < required],
        "projects": flat,
    }


def _search_repositories(query: dict[str, Any], timeout: int) -> list[dict[str, Any]]:
    argv = [
        "gh",
        "search",
        "repos",
        "--language",
        query["language"],
        "--stars",
        query["stars"],
        "--size",
        query["size_kib"],
        "--archived=false",
        "--include-forks=false",
        "--updated",
        query["updated"],
        "--sort",
        query["sort"],
        "--order",
        query["order"],
        "--limit",
        str(query["limit"]),
        "--json",
        "defaultBranch,fullName,isArchived,isFork,isPrivate,language,pushedAt,size,stargazersCount,url,visibility",
    ]
    completed = _run(argv, timeout=timeout)
    if completed.returncode != 0:
        raise RuntimeError(f"repository_search_failed:{query['id']}:{completed.stderr[:500]}")
    value = json.loads(completed.stdout)
    if not isinstance(value, list):
        raise ValueError(f"repository_search_not_array:{query['id']}")
    return value


def prepare_candidates(snapshots: dict[str, list[dict[str, Any]]], history: set[str], maximum_results: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
    combined: dict[str, dict[str, Any]] = {}
    excluded_history = 0
    invalid = 0
    for query_id, rows in snapshots.items():
        for row in rows:
            full_name = row.get("fullName")
            if not isinstance(full_name, str) or full_name.count("/") != 1:
                invalid += 1
                continue
            family = full_name.lower()
            if family in history:
                excluded_history += 1
                continue
            if row.get("isArchived") or row.get("isFork") or row.get("isPrivate") or row.get("visibility") != "public":
                invalid += 1
                continue
            existing = combined.get(family)
            if existing is None:
                combined[family] = {
                    "project_family": family,
                    "full_name": full_name,
                    "repository_url": row["url"],
                    "default_branch": row.get("defaultBranch"),
                    "search_query_ids": [query_id],
                    "search_metadata": {
                        "language": row.get("language"),
                        "pushed_at": row.get("pushedAt"),
                        "size_kib": row.get("size"),
                        "stargazers_count": row.get("stargazersCount"),
                    },
                }
            elif query_id not in existing["search_query_ids"]:
                existing["search_query_ids"].append(query_id)
    if sum(len(rows) for rows in snapshots.values()) > maximum_results:
        raise ValueError("maximum_search_results_exceeded")
    candidates = sorted(combined.values(), key=lambda row: row["project_family"])
    return candidates, {
        "raw_results": sum(len(rows) for rows in snapshots.values()),
        "unique_unseen_candidates": len(candidates),
        "history_exclusions": excluded_history,
        "invalid_or_policy_exclusions": invalid,
    }


def _inventory(evidence_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(evidence_root.rglob("*")):
        if path.is_file() and path.name != "marker.json":
            rows.append(
                {
                    "path": str(path.relative_to(evidence_root)),
                    "bytes": path.stat().st_size,
                    "sha256": _sha256_file(path),
                }
            )
    return rows


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Jev 自然失败 Linux applicability v3 结果",
        "",
        f"- 状态：`{report['status']}`",
        f"- 决定：`{report['qualification']['decision']}`",
        f"- 原始搜索结果：{report['summary']['raw_search_results']}；未见候选：{report['summary']['unique_unseen_candidates']}",
        f"- Linux-applicable 仓库：{report['summary']['source_eligible']}；基础设施失败：{report['summary']['infrastructure_failures']}",
        f"- 平台不合格边：{report['summary']['platform_ineligible_edges']}；ambiguous 边：{report['summary']['ambiguous_edges']}",
        "- build / Docker / credential / Provider / model token：0 / 0 / 0 / 0 / 0",
        "",
        "## 分配配额",
        "",
        "| 构建系统 | 合格分配 | 要求 |",
        "| --- | ---: | ---: |",
    ]
    for system in SYSTEMS:
        lines.append(f"| {system} | {report['qualification']['counts'][system]} | {report['qualification']['required_per_system']} |")
    lines.extend(
        [
            "",
            "## 冻结项目",
            "",
            "| 系统 | reserve 排名 | 项目 | exact commit |",
            "| --- | ---: | --- | --- |",
        ]
    )
    for row in report["qualification"]["projects"]:
        lines.append(f"| {row['selected_build_system']} | {row['system_rank']} | `{row['project_family']}` | `{row['commit_sha']}` |")
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "本结果只评价 source-only Linux applicability 必要条件与采集隔离。它没有运行构建，不证明",
            "Linux 构建成功、自然失败或 reference closure，也不评价 Jev、Agent、动作路由、成本收益或",
            "动态预算控制。后续必须先做 build + reference qualification，再分配实验角色。",
            "",
        ]
    )
    return "\n".join(lines)


def execute() -> dict[str, Any]:
    preflight_result = preflight(require_authorized=True)
    if not preflight_result["ready"]:
        raise RuntimeError("preflight_failed:" + json.dumps(preflight_result["errors"], ensure_ascii=False))
    manifest = _load_json(MANIFEST_PATH)
    evidence_root = _path_from_manifest(manifest["evidence"]["root"])
    report_json_path = _path_from_manifest(manifest["evidence"]["report_json"])
    report_markdown_path = _path_from_manifest(manifest["evidence"]["report_markdown"])
    evidence_root.mkdir(parents=True, exist_ok=False)
    marker_path = evidence_root / "marker.json"
    started_at = _utc_now()
    started_monotonic = time.monotonic()
    marker: dict[str, Any] = {
        "identity": IDENTITY,
        "status": "running",
        "started_at": started_at,
        "execution_revision": preflight_result["head"],
        "manifest_canonical_sha256": preflight_result["manifest_canonical_sha256"],
        "repositories_completed": 0,
        "build_commands": 0,
        "docker_containers": 0,
        "credential_reads": 0,
        "provider_requests": 0,
        "model_tokens": 0,
    }
    _write_json_atomic(marker_path, marker)
    shutil.copy2(MANIFEST_PATH, evidence_root / "manifest.json")
    history = exclusion_project_families(manifest)
    _write_json_atomic(evidence_root / "history-exclusions.json", history)

    snapshots: dict[str, list[dict[str, Any]]] = {}
    candidates: list[dict[str, Any]] = []
    candidate_summary = {"raw_results": 0, "unique_unseen_candidates": 0, "history_exclusions": 0, "invalid_or_policy_exclusions": 0}
    results: list[dict[str, Any]] = []
    global_error: str | None = None
    try:
        for query in manifest["search"]["queries"]:
            snapshot = _search_repositories(query, int(manifest["budget"]["request_timeout_seconds"]))
            snapshots[query["id"]] = snapshot
            _write_json_atomic(evidence_root / f"search-{query['id']}.json", snapshot)
        candidates, candidate_summary = prepare_candidates(
            snapshots,
            set(history),
            int(manifest["budget"]["maximum_search_results"]),
        )
        _write_json_atomic(evidence_root / "candidates.json", candidates)

        def persist(result: dict[str, Any]) -> None:
            nonlocal marker
            slug = result["project_family"].replace("/", "--")
            _write_json_atomic(evidence_root / "repositories" / slug / "result.json", result)
            marker["repositories_completed"] += 1
            marker["last_project_family"] = result["project_family"]
            _write_json_atomic(marker_path, marker)

        def catalog_one(candidate: dict[str, Any]) -> dict[str, Any]:
            if time.monotonic() - started_monotonic >= manifest["budget"]["total_wall_clock_seconds"]:
                raise TimeoutError("catalog_total_wall_clock_exhausted")
            return catalog_repository(candidate, manifest)

        results = catalog_repositories(candidates, catalog_one, persist)
    except Exception as exc:
        global_error = f"{type(exc).__name__}:{exc}"

    qualification = allocate_projects(results, manifest)
    status = "completed" if global_error is None else "failed"
    if global_error is not None:
        qualification = {
            **qualification,
            "passed": False,
            "decision": "attempt_failed",
            "global_error": global_error,
        }
    inventory = _inventory(evidence_root)
    source_eligible = sum(row.get("classification") == "source_eligible" for row in results)
    infrastructure_failures = sum(row.get("classification") == "infrastructure_failure" for row in results)
    platform_ineligible_edges = sum(scan.get("applicability", {}).get("classification") == "platform_ineligible" for row in results for scan in row.get("system_scans", {}).values())
    ambiguous_edges = sum(scan.get("applicability", {}).get("classification") == "ambiguous" for row in results for scan in row.get("system_scans", {}).values())
    report = {
        "schema_version": "forge-jev-natural-failure-linux-applicability-report-3.0.0",
        "identity": IDENTITY,
        "status": status,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "execution_revision": preflight_result["head"],
        "manifest_canonical_sha256": preflight_result["manifest_canonical_sha256"],
        "summary": {
            "raw_search_results": candidate_summary["raw_results"],
            "unique_unseen_candidates": candidate_summary["unique_unseen_candidates"],
            "history_exclusions": candidate_summary["history_exclusions"],
            "invalid_or_policy_exclusions": candidate_summary["invalid_or_policy_exclusions"],
            "repositories_completed": len(results),
            "source_eligible": source_eligible,
            "infrastructure_failures": infrastructure_failures,
            "platform_ineligible_edges": platform_ineligible_edges,
            "ambiguous_edges": ambiguous_edges,
            "elapsed_seconds": time.monotonic() - started_monotonic,
            "build_commands": 0,
            "docker_containers": 0,
            "credential_reads": 0,
            "provider_requests": 0,
            "model_tokens": 0,
        },
        "qualification": qualification,
        "repositories": results,
        "evidence_inventory": inventory,
        "evidence_inventory_canonical_sha256": _canonical_sha256(inventory),
        "interpretation": manifest["interpretation"],
    }
    _write_json_atomic(report_json_path, report)
    report_markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    marker.update(
        {
            "status": status,
            "completed_at": report["completed_at"],
            "repositories_completed": len(results),
            "decision": qualification["decision"],
            "report_json_sha256": _sha256_file(report_json_path),
            "report_markdown_sha256": _sha256_file(report_markdown_path),
            "evidence_inventory_canonical_sha256": report["evidence_inventory_canonical_sha256"],
        }
    )
    _write_json_atomic(marker_path, marker)
    if status != "completed":
        raise RuntimeError(global_error or "formal attempt failed")
    return report


def audit() -> dict[str, Any]:
    manifest = _load_json(MANIFEST_PATH)
    evidence_root = _path_from_manifest(manifest["evidence"]["root"])
    report_json_path = _path_from_manifest(manifest["evidence"]["report_json"])
    report_markdown_path = _path_from_manifest(manifest["evidence"]["report_markdown"])
    marker = _load_json(evidence_root / "marker.json")
    report = _load_json(report_json_path)
    inventory = _inventory(evidence_root)
    errors: list[str] = []
    if marker.get("status") != "completed" or report.get("status") != "completed":
        errors.append("attempt_not_completed")
    if marker.get("report_json_sha256") != _sha256_file(report_json_path):
        errors.append("report_json_hash_mismatch")
    if marker.get("report_markdown_sha256") != _sha256_file(report_markdown_path):
        errors.append("report_markdown_hash_mismatch")
    inventory_hash = _canonical_sha256(inventory)
    if marker.get("evidence_inventory_canonical_sha256") != inventory_hash:
        errors.append("evidence_inventory_hash_mismatch")
    if report.get("evidence_inventory_canonical_sha256") != inventory_hash:
        errors.append("report_inventory_hash_mismatch")
    for key in ("build_commands", "docker_containers", "credential_reads", "provider_requests", "model_tokens"):
        if marker.get(key) or report.get("summary", {}).get(key):
            errors.append(f"zero_boundary_violated:{key}")
    return {
        "identity": IDENTITY,
        "valid": not errors,
        "errors": errors,
        "decision": report.get("qualification", {}).get("decision"),
        "report_json_sha256": _sha256_file(report_json_path),
        "report_markdown_sha256": _sha256_file(report_markdown_path),
        "evidence_inventory_canonical_sha256": inventory_hash,
        "evidence_files": len(inventory),
        "evidence_bytes": sum(row["bytes"] for row in inventory),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("protocol-validate", "preflight", "execute", "audit"))
    args = parser.parse_args()
    if args.command == "protocol-validate":
        value = validate_protocol()
    elif args.command == "preflight":
        value = preflight(require_authorized=False)
    elif args.command == "execute":
        value = execute()
    else:
        value = audit()
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if value.get("valid", value.get("ready", True)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
