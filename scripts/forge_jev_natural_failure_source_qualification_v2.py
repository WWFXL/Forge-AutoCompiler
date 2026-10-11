#!/usr/bin/env python3
"""Issue #413 自然构建失败 source qualification v2。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
IDENTITY = "cpp-jev-natural-failure-source-qualification-v2"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests" / f"{IDENTITY}.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-jev-natural-failure-source-qualification-v2.schema.json"
DEFAULT_REPORT_JSON_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.json"
DEFAULT_REPORT_MARKDOWN_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.md"

SYSTEMS = ("cmake", "make", "autotools")
ROLES = ("design", "calibration", "evaluation")
NETWORK_ERROR_PATTERNS = (
    "could not resolve host",
    "could not resolve hostname",
    "could not resolve proxy",
    "temporary failure in name resolution",
    "network is unreachable",
    "failed to connect to",
    "couldn't connect to server",
    "unable to access 'http",
    'unable to access "http',
    "download step failed",
    "each download failed",
    "failed to download",
    "connection timed out",
)
PLATFORM_ERROR_PATTERNS = (
    "only supported on macos",
    "only supports macos",
    "requires macos",
    "macos is required",
    "only supported on windows",
    "only supports windows",
    "requires windows",
    "windows is required",
    "not supported on linux",
    "unsupported operating system",
)


class BatchBudgetExceeded(TimeoutError):
    """Formal attempt 总 wall-clock 已耗尽。"""


ERROR_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "configure_required",
        (
            "no makefile found",
            "no targets specified and no makefile found",
            "please run configure",
            "config.mk: no such file",
            "no rule to make target 'config.mk'",
        ),
    ),
    (
        "missing_dependency",
        (
            "could not find package",
            "could not find a package configuration file",
            "package requirements (",
            "required package",
            "not found (missing:",
            "fatal error:",
            "no such file or directory",
        ),
    ),
    (
        "missing_tool",
        (
            "command not found",
            "not found in path",
            "unable to find executable",
            "could not find program",
        ),
    ),
    (
        "incompatible_toolchain",
        (
            "cmake version",
            "unsupported compiler",
            "compiler is not supported",
            "requires c++",
        ),
    ),
    (
        "target_or_layout_error",
        (
            "no rule to make target",
            "does not appear to contain cmakelists.txt",
            "the source directory",
        ),
    ),
    ("compile_error", ("error:", "undefined reference to", "collect2: error")),
)


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
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        env=env,
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


def _task_id(task: dict[str, Any]) -> str:
    family = re.sub(r"[^a-z0-9]+", "-", task["project_family"].lower()).strip("-")
    return f"{task['selected_build_system']}-{family}"


def _catalog_tasks(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    catalog_path = _path_from_manifest(manifest["source_catalog"]["path"])
    catalog = _load_json(catalog_path)
    if _sha256_file(catalog_path) != manifest["source_catalog"]["sha256"]:
        raise ValueError("source_catalog_hash_mismatch")
    qualification = catalog.get("qualification", {})
    if qualification.get("decision") != manifest["source_catalog"]["required_decision"]:
        raise ValueError("source_catalog_decision_mismatch")
    tasks = qualification.get("projects")
    if not isinstance(tasks, list) or len(tasks) != manifest["source_catalog"]["task_count"]:
        raise ValueError("source_catalog_task_count_mismatch")
    return [dict(task) for task in tasks]


def validate_protocol() -> dict[str, Any]:
    manifest = _load_json(MANIFEST_PATH)
    schema = _load_json(SCHEMA_PATH)
    jsonschema.Draft202012Validator(schema).validate(manifest)
    tasks = _catalog_tasks(manifest)
    errors: list[str] = []
    seen_families: set[str] = set()
    seen_ids: set[str] = set()
    counts = {system: 0 for system in SYSTEMS}
    roles = {system: Counter() for system in SYSTEMS}
    for task in tasks:
        family = task.get("project_family")
        system = task.get("selected_build_system")
        task_id = _task_id(task)
        if family in seen_families:
            errors.append(f"duplicate_project_family:{family}")
        if task_id in seen_ids:
            errors.append(f"duplicate_task_id:{task_id}")
        seen_families.add(family)
        seen_ids.add(task_id)
        if system not in SYSTEMS:
            errors.append(f"unknown_build_system:{task_id}")
            continue
        if not re.fullmatch(r"[0-9a-f]{40}", str(task.get("commit_sha"))):
            errors.append(f"invalid_commit_sha:{task_id}")
        counts[system] += 1
        roles[system][task.get("role")] += 1
    for system in SYSTEMS:
        if counts[system] != 8:
            errors.append(f"system_task_count_mismatch:{system}")
        if roles[system] != Counter({"design": 2, "calibration": 2, "evaluation": 4}):
            errors.append(f"system_role_count_mismatch:{system}")

    for relative, expected_hash in manifest["parents"].items():
        path = _path_from_manifest(relative)
        if not path.is_file() or _sha256_file(path) != expected_hash:
            errors.append(f"parent_hash_mismatch:{relative}")

    authorization = manifest["authorization"]
    authorized = bool(authorization["execution"])
    if authorization["formal_attempts"] != (1 if authorized else 0):
        errors.append("formal_attempt_authorization_mismatch")
    if bool(authorization["formal_evidence_write"]) != authorized:
        errors.append("formal_evidence_authorization_mismatch")
    if authorized and not manifest["implementation_revision"]:
        errors.append("authorized_without_implementation_revision")
    if any(manifest["budget"][key] for key in ("credential_reads", "provider_requests", "model_tokens")):
        errors.append("zero_provider_boundary_violated")

    result = {
        "identity": IDENTITY,
        "valid": not errors,
        "errors": errors,
        "authorization": "execution" if authorized else "candidate_only",
        "manifest_canonical_sha256": _canonical_sha256(manifest),
        "source_catalog_sha256": manifest["source_catalog"]["sha256"],
        "task_count": len(tasks),
        "counts": counts,
    }
    if errors:
        raise ValueError(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def _managed_containers() -> list[str]:
    completed = _run(
        ["docker", "ps", "-a", "--filter", f"label=forge.experiment={IDENTITY}", "--format", "{{.Names}}"],
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "docker ps failed")
    return [line for line in completed.stdout.splitlines() if line.strip()]


def _remove_container(name: str) -> bool:
    completed = _run(["docker", "rm", "-f", name], timeout=30)
    return completed.returncode == 0


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

    runtime = _run([str(REPO_ROOT / "scripts/require-docker-runtime.sh")], timeout=60)
    if runtime.returncode != 0:
        errors.append("docker_runtime_unavailable")
    image = _run(
        ["docker", "image", "inspect", manifest["environment"]["compile_image"], "--format", "{{.Id}}"],
        timeout=30,
    )
    image_id = image.stdout.strip() if image.returncode == 0 else None
    if image_id != manifest["environment"]["image_id"]:
        errors.append("compile_image_identity_mismatch")
    containers = _managed_containers()
    if containers:
        errors.append("managed_containers_present")

    for key in ("root", "work_root", "report_json", "report_markdown"):
        if _path_from_manifest(manifest["evidence"][key]).exists():
            errors.append(f"evidence_path_already_exists:{key}")
    return {
        **protocol,
        "ready": not errors,
        "errors": errors,
        "branch": branch,
        "head": head,
        "image_id": image_id,
        "managed_containers": containers,
    }


def source_contract_reason(source: Path, build_system: str) -> str | None:
    if (source / ".gitmodules").exists():
        return "submodule_contract_drift"
    if build_system == "cmake":
        return None if (source / "CMakeLists.txt").is_file() else "cmakelists_missing"
    if build_system == "make":
        return None if any((source / marker).is_file() for marker in ("GNUmakefile", "Makefile", "makefile")) else "root_makefile_missing"
    if build_system == "autotools":
        return None if any((source / marker).is_file() for marker in ("configure.ac", "configure.in")) else "autotools_entrypoint_missing"
    return "unknown_build_system"


def initial_commands(source: Path, manifest: dict[str, Any], build_system: str) -> list[dict[str, str]]:
    if build_system in {"cmake", "make"}:
        return [dict(row) for row in manifest["initial_paths"][build_system]]
    if (source / "autogen.sh").is_file():
        bootstrap = "./autogen.sh"
    elif (source / "bootstrap").is_file():
        bootstrap = "./bootstrap"
    else:
        bootstrap = "autoreconf -fi"
    return [
        {"phase": "configure", "command": bootstrap},
        *[dict(row) for row in manifest["initial_paths"]["autotools"]["after_bootstrap"]],
    ]


def normalize_failure(stdout: str, stderr: str) -> tuple[str, str]:
    text = f"{stdout}\n{stderr}".lower()
    text = re.sub(r"/workspace(?:/[^\s:'\"]+)*", "<workspace>", text)
    text = re.sub(r":\d+(?::\d+)?", ":<line>", text)
    if any(pattern in text for pattern in NETWORK_ERROR_PATTERNS):
        return "network_dependency_failure", "network_dependency"
    if any(pattern in text for pattern in PLATFORM_ERROR_PATTERNS):
        return "platform_incompatible", "platform_incompatible"
    for category, patterns in ERROR_PATTERNS:
        if any(pattern in text for pattern in patterns):
            return "bounded_failure", category
    return "bounded_failure", "unknown_build_failure"


def _timeout_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _run_source_stage(
    argv: list[str],
    *,
    cwd: Path,
    timeout: int,
    env: dict[str, str],
    stage: str,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = _run(argv, cwd=cwd, timeout=timeout, env=env)
        return {
            "stage": stage,
            "exit_code": completed.returncode,
            "timed_out": False,
            "elapsed_seconds": time.monotonic() - started,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "stage": stage,
            "exit_code": None,
            "timed_out": True,
            "elapsed_seconds": time.monotonic() - started,
            "stdout": _timeout_text(exc.stdout),
            "stderr": _timeout_text(exc.stderr),
        }


def clone_source(task: dict[str, Any], destination: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    timeout = int(manifest["budget"]["source_stage_timeout_seconds"])
    env = os.environ.copy()
    env["GIT_LFS_SKIP_SMUDGE"] = "1"
    destination.mkdir(parents=True, exist_ok=False)
    stages = [
        (["git", "init", "--quiet"], "init"),
        (["git", "remote", "add", "origin", task["repository_url"]], "remote"),
        (["git", "fetch", "--depth", "1", "origin", task["commit_sha"]], "fetch"),
        (["git", "checkout", "--detach", "FETCH_HEAD"], "checkout"),
    ]
    observed: list[dict[str, Any]] = []
    for argv, stage in stages:
        row = _run_source_stage(argv, cwd=destination, timeout=timeout, env=env, stage=stage)
        observed.append(row)
        if row["timed_out"] or row["exit_code"] != 0:
            return {"succeeded": False, "stage": stage, "timed_out": row["timed_out"], "stages": observed}
    head = _run(["git", "rev-parse", "HEAD"], cwd=destination, timeout=30)
    status = _run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=destination, timeout=30)
    clean = status.returncode == 0 and not status.stdout.strip()
    succeeded = head.returncode == 0 and head.stdout.strip() == task["commit_sha"] and clean
    return {
        "succeeded": succeeded,
        "stage": "complete" if succeeded else "source_identity",
        "timed_out": False,
        "stages": observed,
        "head": head.stdout.strip(),
        "clean": clean,
        "source_identity_sha256": _canonical_sha256({"commit_sha": head.stdout.strip(), "clean": clean, "submodules": []}),
    }


def _persist_source_logs(task_root: Path, source: dict[str, Any]) -> None:
    for index, stage in enumerate(source.get("stages", []), start=1):
        prefix = task_root / f"source-{index}-{stage['stage']}"
        stdout = prefix.with_suffix(".stdout.log")
        stderr = prefix.with_suffix(".stderr.log")
        stdout.write_text(stage.pop("stdout"), encoding="utf-8", errors="replace")
        stderr.write_text(stage.pop("stderr"), encoding="utf-8", errors="replace")
        stage["stdout_path"] = str(stdout.relative_to(REPO_ROOT))
        stage["stderr_path"] = str(stderr.relative_to(REPO_ROOT))
        stage["stdout_sha256"] = _sha256_file(stdout)
        stage["stderr_sha256"] = _sha256_file(stderr)
    _write_json_atomic(task_root / "source.json", source)


def _run_build_command(
    *,
    workspace: Path,
    command: str,
    phase: str,
    task_id: str,
    replicate: int,
    manifest: dict[str, Any],
    remaining_session_seconds: float,
) -> dict[str, Any]:
    timeout = max(1, min(int(manifest["budget"]["command_timeout_seconds"]), int(remaining_session_seconds)))
    name = f"forge-413-{task_id[:30]}-{replicate}-{uuid.uuid4().hex[:8]}"
    argv = [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--network",
        manifest["environment"]["build_network"],
        "--label",
        "forge.managed=true",
        "--label",
        f"forge.experiment={IDENTITY}",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--env",
        "HOME=/tmp",
        "--volume",
        f"{workspace}:/workspace:rw",
        "--workdir",
        "/workspace",
        manifest["environment"]["compile_image"],
        "bash",
        "-lc",
        command,
    ]
    started = time.monotonic()
    try:
        completed = _run(argv, timeout=timeout)
        infrastructure = completed.returncode == 125 or completed.stderr.startswith("docker:")
        return {
            "phase": phase,
            "command": command,
            "exit_code": completed.returncode,
            "timed_out": False,
            "infrastructure_failure": infrastructure,
            "elapsed_seconds": time.monotonic() - started,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "phase": phase,
            "command": command,
            "exit_code": None,
            "timed_out": True,
            "infrastructure_failure": False,
            "elapsed_seconds": time.monotonic() - started,
            "stdout": _timeout_text(exc.stdout),
            "stderr": _timeout_text(exc.stderr),
        }
    finally:
        _remove_container(name)


def _persist_command_logs(task_root: Path, replicate: int, index: int, command: dict[str, Any]) -> None:
    prefix = task_root / f"replicate-{replicate}-command-{index}"
    stdout = prefix.with_suffix(".stdout.log")
    stderr = prefix.with_suffix(".stderr.log")
    stdout.write_text(command.pop("stdout"), encoding="utf-8", errors="replace")
    stderr.write_text(command.pop("stderr"), encoding="utf-8", errors="replace")
    command["stdout_path"] = str(stdout.relative_to(REPO_ROOT))
    command["stderr_path"] = str(stderr.relative_to(REPO_ROOT))
    command["stdout_sha256"] = _sha256_file(stdout)
    command["stderr_sha256"] = _sha256_file(stderr)


def run_replicate(
    *,
    source: Path,
    workspace: Path,
    task_root: Path,
    task: dict[str, Any],
    replicate: int,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        shutil.copytree(source, workspace, symlinks=True)
    except Exception as exc:
        result = {
            "replicate": replicate,
            "outcome": "infrastructure_failure",
            "failure_phase": "workspace_copy",
            "error_category": type(exc).__name__,
            "elapsed_seconds": time.monotonic() - started,
            "commands": [],
        }
        _write_json_atomic(task_root / f"replicate-{replicate}.json", result)
        return result

    observed: list[dict[str, Any]] = []
    try:
        for command in initial_commands(workspace, manifest, task["selected_build_system"]):
            remaining = manifest["budget"]["session_timeout_seconds"] - (time.monotonic() - started)
            if remaining <= 0:
                observed.append(
                    {
                        "phase": command["phase"],
                        "command": command["command"],
                        "exit_code": None,
                        "timed_out": True,
                        "infrastructure_failure": False,
                        "elapsed_seconds": 0.0,
                        "stdout": "",
                        "stderr": "session timeout before command",
                    }
                )
            else:
                observed.append(
                    _run_build_command(
                        workspace=workspace,
                        command=command["command"],
                        phase=command["phase"],
                        task_id=_task_id(task),
                        replicate=replicate,
                        manifest=manifest,
                        remaining_session_seconds=remaining,
                    )
                )
            if observed[-1]["exit_code"] != 0 or observed[-1]["timed_out"] or observed[-1]["infrastructure_failure"]:
                break

        for index, command in enumerate(observed, start=1):
            _persist_command_logs(task_root, replicate, index, command)
        final = observed[-1]
        if final["timed_out"]:
            outcome, category = "timeout", "timeout"
        elif final["infrastructure_failure"]:
            outcome, category = "infrastructure_failure", "docker_runtime_failure"
        elif final["exit_code"] == 0:
            outcome, category = "initial_success", None
        else:
            stdout = (REPO_ROOT / final["stdout_path"]).read_text(encoding="utf-8", errors="replace")
            stderr = (REPO_ROOT / final["stderr_path"]).read_text(encoding="utf-8", errors="replace")
            outcome, category = normalize_failure(stdout, stderr)
        result = {
            "replicate": replicate,
            "outcome": outcome,
            "failure_phase": final["phase"] if outcome != "initial_success" else None,
            "error_category": category,
            "elapsed_seconds": time.monotonic() - started,
            "commands": observed,
        }
        _write_json_atomic(task_root / f"replicate-{replicate}.json", result)
        return result
    finally:
        if workspace.exists():
            shutil.rmtree(workspace)


def classify_task(replicates: list[dict[str, Any]]) -> tuple[str, str]:
    outcomes = [row["outcome"] for row in replicates]
    if outcomes == ["initial_success", "initial_success"]:
        return "initial_success", "both_initial_paths_succeeded"
    if any(outcome == "infrastructure_failure" for outcome in outcomes):
        return "infrastructure_failure", "replicate_infrastructure_failure"
    if any(outcome == "timeout" for outcome in outcomes):
        return "timeout", "replicate_timeout"
    if any(outcome == "network_dependency_failure" for outcome in outcomes):
        return "network_dependency_excluded", "runtime_network_dependency"
    if any(outcome == "platform_incompatible" for outcome in outcomes):
        return "platform_incompatible", "explicit_platform_incompatibility"
    if outcomes != ["bounded_failure", "bounded_failure"]:
        return "inconsistent_failure", "replicate_outcomes_differ"
    phases = {row["failure_phase"] for row in replicates}
    categories = {row["error_category"] for row in replicates}
    if len(phases) != 1 or len(categories) != 1:
        return "inconsistent_failure", "failure_phase_or_category_differs"
    return "stable_natural_failure", "two_clean_replays_agree"


def process_tasks(
    tasks: list[dict[str, Any]],
    process_one: Callable[[dict[str, Any]], dict[str, Any]],
    on_result: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for task in tasks:
        try:
            result = process_one(task)
        except BatchBudgetExceeded:
            raise
        except Exception as exc:
            result = {
                "task_id": _task_id(task),
                "project_family": task["project_family"],
                "selected_build_system": task["selected_build_system"],
                "role": task["role"],
                "classification": "infrastructure_failure",
                "reason": "unhandled_project_exception",
                "error": {"kind": type(exc).__name__, "message": str(exc)[:500]},
                "replicates": [],
            }
        results.append(result)
        if on_result:
            on_result(result)
    return results


def _process_task(
    task: dict[str, Any],
    *,
    manifest: dict[str, Any],
    evidence_root: Path,
    work_root: Path,
) -> dict[str, Any]:
    task_id = _task_id(task)
    task_root = evidence_root / "tasks" / task_id
    task_root.mkdir(parents=True, exist_ok=False)
    source = work_root / f"source-{task_id}"
    result: dict[str, Any] = {
        "task_id": task_id,
        "project_family": task["project_family"],
        "selected_build_system": task["selected_build_system"],
        "role": task["role"],
        "system_rank": task["system_rank"],
        "commit_sha": task["commit_sha"],
        "replicates": [],
    }
    try:
        source_result = clone_source(task, source, manifest)
        _persist_source_logs(task_root, source_result)
        result["source"] = source_result
        if not source_result["succeeded"]:
            result["classification"] = "timeout" if source_result.get("timed_out") else "infrastructure_failure"
            result["reason"] = f"source_{source_result['stage']}_failed"
        else:
            contract_reason = source_contract_reason(source, task["selected_build_system"])
            if contract_reason:
                result["classification"] = "source_contract_ineligible"
                result["reason"] = contract_reason
            else:
                for replicate in range(1, manifest["budget"]["replicates_per_task"] + 1):
                    replicate_result = run_replicate(
                        source=source,
                        workspace=work_root / f"workspace-{task_id}-{replicate}",
                        task_root=task_root,
                        task=task,
                        replicate=replicate,
                        manifest=manifest,
                    )
                    result["replicates"].append(replicate_result)
                classification, reason = classify_task(result["replicates"])
                result["classification"] = classification
                result["reason"] = reason
                if classification == "stable_natural_failure":
                    first = result["replicates"][0]
                    result["stable_failure"] = f"{first['failure_phase']} / {first['error_category']}"
    finally:
        if source.exists():
            shutil.rmtree(source)
        leaked = _managed_containers()
        result["managed_containers_before_cleanup"] = leaked
        cleanup_ok = all(_remove_container(name) for name in leaked)
        result["cleanup_ok"] = cleanup_ok and not _managed_containers()
        if not result["cleanup_ok"]:
            result["classification"] = "infrastructure_failure"
            result["reason"] = "container_cleanup_failed"
        _write_json_atomic(task_root / "result.json", result)
    return result


def _decision(results: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    counts = {system: {role: 0 for role in ROLES} for system in SYSTEMS}
    for row in results:
        if row.get("classification") == "stable_natural_failure":
            counts[row["selected_build_system"]][row["role"]] += 1
    required = manifest["qualification"]["required_by_system_and_role"]
    failures = [f"{system}:{role}:{counts[system][role]}<{required[role]}" for system in SYSTEMS for role in ROLES if counts[system][role] < required[role]]
    cleanup_failures = [row["task_id"] for row in results if not row.get("cleanup_ok", False)]
    if cleanup_failures:
        failures.append(f"cleanup_failures:{len(cleanup_failures)}")
    passed = not failures
    return {
        "passed": passed,
        "decision": manifest["qualification"]["pass_decision"] if passed else manifest["qualification"]["fail_decision"],
        "stable_failure_counts": counts,
        "failed_requirements": failures,
        "cleanup_failures": cleanup_failures,
    }


def _inventory(evidence_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(evidence_root.rglob("*")):
        if path.is_file() and path.name != "marker.json":
            rows.append({"path": str(path.relative_to(evidence_root)), "bytes": path.stat().st_size, "sha256": _sha256_file(path)})
    return rows


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Jev 自然构建失败 source qualification v2 结果",
        "",
        f"- 状态：`{report['status']}`",
        f"- 决定：`{report['qualification']['decision']}`",
        f"- 项目：{report['summary']['tasks_completed']}/{report['summary']['tasks_total']}；稳定自然失败：{report['summary']['stable_natural_failures']}",
        "- Provider：0 request / 0 token；credential：0 read",
        "",
        "## 角色配额",
        "",
        "| 构建系统 | design | calibration | evaluation |",
        "| --- | ---: | ---: | ---: |",
    ]
    counts = report["qualification"]["stable_failure_counts"]
    for system in SYSTEMS:
        lines.append(f"| {system} | {counts[system]['design']} | {counts[system]['calibration']} | {counts[system]['evaluation']} |")
    lines.extend(
        [
            "",
            "## 项目结果",
            "",
            "| 项目 | 系统 | 角色 | 分类 | 失败阶段 / 类别 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in report["tasks"]:
        lines.append(f"| `{row['task_id']}` | {row['selected_build_system']} | {row['role']} | `{row['classification']}` | {row.get('stable_failure', '-')} |")
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "本结果只判断冻结项目能否形成稳定自然失败来源。网络、平台、超时和基础设施失败均不计入；",
            "它不验证 reference recipe、动作矩阵、Jev/Agent 效果、成本收益或动态预算控制。",
            "",
        ]
    )
    return "\n".join(lines)


def execute() -> dict[str, Any]:
    preflight_result = preflight(require_authorized=True)
    if not preflight_result["ready"]:
        raise RuntimeError("preflight_failed:" + json.dumps(preflight_result["errors"], ensure_ascii=False))
    manifest = _load_json(MANIFEST_PATH)
    tasks = _catalog_tasks(manifest)
    evidence_root = _path_from_manifest(manifest["evidence"]["root"])
    work_root = _path_from_manifest(manifest["evidence"]["work_root"])
    report_json_path = _path_from_manifest(manifest["evidence"]["report_json"])
    report_markdown_path = _path_from_manifest(manifest["evidence"]["report_markdown"])
    evidence_root.mkdir(parents=True, exist_ok=False)
    work_root.mkdir(parents=True, exist_ok=False)
    marker_path = evidence_root / "marker.json"
    started_at = _utc_now()
    started_monotonic = time.monotonic()
    marker: dict[str, Any] = {
        "identity": IDENTITY,
        "status": "running",
        "started_at": started_at,
        "execution_revision": preflight_result["head"],
        "manifest_canonical_sha256": preflight_result["manifest_canonical_sha256"],
        "source_catalog_sha256": preflight_result["source_catalog_sha256"],
        "tasks_completed": 0,
        "credential_reads": 0,
        "provider_requests": 0,
        "model_tokens": 0,
    }
    _write_json_atomic(marker_path, marker)
    shutil.copy2(MANIFEST_PATH, evidence_root / "manifest.json")
    shutil.copy2(_path_from_manifest(manifest["source_catalog"]["path"]), evidence_root / "source-catalog.json")
    results: list[dict[str, Any]] = []
    global_error: str | None = None

    def persist(result: dict[str, Any]) -> None:
        task_result_path = evidence_root / "tasks" / result["task_id"] / "result.json"
        _write_json_atomic(task_result_path, result)
        marker["tasks_completed"] += 1
        marker["last_task_id"] = result["task_id"]
        _write_json_atomic(marker_path, marker)

    def process_one(task: dict[str, Any]) -> dict[str, Any]:
        if time.monotonic() - started_monotonic >= manifest["budget"]["total_wall_clock_seconds"]:
            raise BatchBudgetExceeded("batch_total_wall_clock_exhausted")
        return _process_task(task, manifest=manifest, evidence_root=evidence_root, work_root=work_root)

    try:
        results = process_tasks(tasks, process_one, persist)
    except Exception as exc:
        global_error = f"{type(exc).__name__}:{exc}"
    finally:
        if work_root.exists():
            shutil.rmtree(work_root)
        for name in _managed_containers():
            _remove_container(name)

    qualification = _decision(results, manifest)
    remaining = _managed_containers()
    if remaining:
        global_error = f"managed_containers_after_cleanup:{remaining}"
    status = "completed" if global_error is None else "failed"
    if global_error is not None:
        qualification = {**qualification, "passed": False, "decision": "attempt_failed", "global_error": global_error}
    classifications = Counter(row["classification"] for row in results)
    inventory = _inventory(evidence_root)
    report = {
        "schema_version": "forge-jev-natural-failure-source-qualification-report-2.0.0",
        "identity": IDENTITY,
        "status": status,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "execution_revision": preflight_result["head"],
        "manifest_canonical_sha256": preflight_result["manifest_canonical_sha256"],
        "source_catalog_sha256": preflight_result["source_catalog_sha256"],
        "summary": {
            "tasks_total": len(tasks),
            "tasks_completed": len(results),
            "stable_natural_failures": classifications["stable_natural_failure"],
            "classifications": dict(sorted(classifications.items())),
            "elapsed_seconds": time.monotonic() - started_monotonic,
            "credential_reads": 0,
            "provider_requests": 0,
            "model_tokens": 0,
        },
        "qualification": qualification,
        "tasks": results,
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
            "tasks_completed": len(results),
            "decision": qualification["decision"],
            "report_json_sha256": _sha256_file(report_json_path),
            "report_markdown_sha256": _sha256_file(report_markdown_path),
            "evidence_inventory_canonical_sha256": report["evidence_inventory_canonical_sha256"],
            "managed_containers_after_cleanup": remaining,
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
    if marker.get("credential_reads") or marker.get("provider_requests") or marker.get("model_tokens"):
        errors.append("zero_provider_boundary_violated")
    containers = _managed_containers()
    if containers:
        errors.append("managed_containers_present")
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
        "managed_containers": containers,
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
