#!/usr/bin/env python3
"""Issue #411 自然构建失败 source qualification v1。"""

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
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
IDENTITY = "cpp-jev-natural-failure-source-qualification-v1"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests" / f"{IDENTITY}.json"
SCHEMA_PATH = (
    REPO_ROOT
    / "benchmarks/schemas/forge-jev-natural-failure-source-qualification-v1.schema.json"
)
SOURCE_POOL_PATH = (
    REPO_ROOT / "benchmarks/fixtures/cpp-jev-natural-failure-source-pool-v1.json"
)
PREREGISTRATION_PATH = REPO_ROOT / "benchmarks/preregistrations" / f"{IDENTITY}.md"
DEFAULT_REPORT_JSON_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.json"
DEFAULT_REPORT_MARKDOWN_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.md"

SYSTEMS = ("cmake", "make", "autotools")
ROLES = ("design", "calibration", "evaluation")
ROLE_BY_RANK = {
    1: "design",
    2: "design",
    3: "calibration",
    4: "calibration",
    5: "evaluation",
    6: "evaluation",
    7: "evaluation",
    8: "evaluation",
}
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
            "cmake error at cmakelists.txt",
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
    (
        "compile_error",
        (
            "error:",
            "undefined reference to",
            "collect2: error",
        ),
    ),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _sha256_bytes(payload)


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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
    if REPO_ROOT != path and REPO_ROOT not in path.parents:
        raise ValueError(f"manifest 路径越界: {value}")
    return path


def _selection_key(seed: str, family: str) -> str:
    return _sha256_bytes(f"{seed}\0{family}".encode())


def validate_protocol() -> dict[str, Any]:
    manifest = _load_json(MANIFEST_PATH)
    schema = _load_json(SCHEMA_PATH)
    source_pool = _load_json(SOURCE_POOL_PATH)
    jsonschema.Draft202012Validator(schema).validate(manifest)

    errors: list[str] = []
    if manifest["source_pool"]["path"] != str(SOURCE_POOL_PATH.relative_to(REPO_ROOT)):
        errors.append("source_pool_path_mismatch")
    if _sha256_file(SOURCE_POOL_PATH) != manifest["source_pool"]["sha256"]:
        errors.append("source_pool_hash_mismatch")
    tasks = source_pool.get("tasks")
    if (
        not isinstance(tasks, list)
        or len(tasks) != manifest["source_pool"]["task_count"]
    ):
        errors.append("source_pool_task_count_mismatch")
        tasks = []

    seen_ids: set[str] = set()
    seen_families: set[str] = set()
    by_system: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seed = source_pool.get("selection_seed")
    for task in tasks:
        task_id = task.get("task_id")
        family = task.get("project_family")
        system = task.get("selected_build_system")
        rank = task.get("system_rank")
        if task_id in seen_ids:
            errors.append(f"duplicate_task_id:{task_id}")
        if family in seen_families:
            errors.append(f"duplicate_project_family:{family}")
        seen_ids.add(task_id)
        seen_families.add(family)
        if system not in SYSTEMS:
            errors.append(f"unknown_build_system:{task_id}")
            continue
        if ROLE_BY_RANK.get(rank) != task.get("role"):
            errors.append(f"role_rank_mismatch:{task_id}")
        if not isinstance(seed, str) or task.get("selection_key") != _selection_key(
            seed, family
        ):
            errors.append(f"selection_key_mismatch:{task_id}")
        if not re.fullmatch(r"[0-9a-f]{40}", str(task.get("commit_sha"))):
            errors.append(f"invalid_commit_sha:{task_id}")
        if int(task.get("github_size_kib", 10**9)) > 300000:
            errors.append(f"repository_size_limit_exceeded:{task_id}")
        by_system[system].append(task)

    expected_counts = {"cmake": 8, "make": 8, "autotools": 6}
    for system, expected in expected_counts.items():
        ordered = sorted(by_system[system], key=lambda row: row["system_rank"])
        if len(ordered) != expected:
            errors.append(f"system_task_count_mismatch:{system}")
        if [row["system_rank"] for row in ordered] != list(range(1, expected + 1)):
            errors.append(f"system_rank_sequence_mismatch:{system}")
        if [row["selection_key"] for row in ordered] != sorted(
            row["selection_key"] for row in ordered
        ):
            errors.append(f"selection_order_mismatch:{system}")

    for relative, expected_hash in manifest["parents"].items():
        parent = _path_from_manifest(relative)
        if not parent.is_file() or _sha256_file(parent) != expected_hash:
            errors.append(f"parent_hash_mismatch:{relative}")

    authorization = manifest["authorization"]
    authorized = bool(authorization["execution"])
    expected_attempts = 1 if authorized else 0
    if authorization["formal_attempts"] != expected_attempts:
        errors.append("formal_attempt_authorization_mismatch")
    if bool(authorization["formal_evidence_write"]) != authorized:
        errors.append("evidence_authorization_mismatch")
    if authorization["credential_reads"] or authorization["provider_calls"]:
        errors.append("zero_provider_boundary_violated")
    if manifest["budget"]["provider_requests"] or manifest["budget"]["model_tokens"]:
        errors.append("nonzero_provider_budget")

    result = {
        "identity": IDENTITY,
        "valid": not errors,
        "errors": errors,
        "manifest_canonical_sha256": _canonical_sha256(manifest),
        "source_pool_sha256": _sha256_file(SOURCE_POOL_PATH),
        "task_count": len(tasks),
        "authorization": "execution" if authorized else "candidate_only",
    }
    if errors:
        raise ValueError(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def _managed_containers() -> list[str]:
    completed = _run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"label=forge.experiment={IDENTITY}",
            "--format",
            "{{.Names}}",
        ],
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "docker ps failed")
    return [line for line in completed.stdout.splitlines() if line.strip()]


def preflight(*, require_authorized: bool) -> dict[str, Any]:
    protocol = validate_protocol()
    manifest = _load_json(MANIFEST_PATH)
    errors: list[str] = []
    runtime = _run([str(REPO_ROOT / "scripts/require-docker-runtime.sh")], timeout=60)
    if runtime.returncode != 0:
        errors.append("docker_runtime_unavailable")
    image = _run(
        [
            "docker",
            "image",
            "inspect",
            manifest["environment"]["compile_image"],
            "--format",
            "{{.Id}}",
        ],
        timeout=30,
    )
    image_id = image.stdout.strip() if image.returncode == 0 else None
    if image_id != manifest["environment"]["image_id"]:
        errors.append("compile_image_identity_mismatch")

    branch = _git("branch", "--show-current")
    head = _git("rev-parse", "HEAD")
    if branch != manifest["branch"]:
        errors.append("branch_mismatch")
    design_ancestor = (
        _run(
            ["git", "merge-base", "--is-ancestor", manifest["design_revision"], head]
        ).returncode
        == 0
    )
    if not design_ancestor:
        errors.append("design_revision_not_ancestor")
    implementation = manifest["implementation_revision"]
    if implementation:
        implementation_ancestor = (
            _run(
                ["git", "merge-base", "--is-ancestor", implementation, head]
            ).returncode
            == 0
        )
        if not implementation_ancestor:
            errors.append("implementation_revision_not_ancestor")
    elif require_authorized:
        errors.append("implementation_revision_unfrozen")

    status = _git("status", "--short")
    if require_authorized and status:
        errors.append("worktree_not_clean")
    evidence_root = _path_from_manifest(manifest["evidence"]["root"])
    work_root = _path_from_manifest(manifest["evidence"]["work_root"])
    report_json = _path_from_manifest(manifest["evidence"]["report_json"])
    report_markdown = _path_from_manifest(manifest["evidence"]["report_markdown"])
    for name, path in (
        ("evidence_root", evidence_root),
        ("work_root", work_root),
        ("report_json", report_json),
        ("report_markdown", report_markdown),
    ):
        if path.exists():
            errors.append(f"create_once_path_exists:{name}")
    containers = _managed_containers() if runtime.returncode == 0 else []
    if containers:
        errors.append("managed_containers_present")
    authorization = manifest["authorization"]
    if require_authorized and not (
        authorization["execution"]
        and authorization["formal_evidence_write"]
        and authorization["formal_attempts"] == 1
    ):
        errors.append("execution_not_authorized")

    return {
        **protocol,
        "ready": not errors,
        "errors": errors,
        "branch": branch,
        "head": head,
        "image_id": image_id,
        "worktree_clean": not bool(status),
        "managed_containers": containers,
        "credential_reads": 0,
        "provider_requests": 0,
        "model_tokens": 0,
    }


def source_contract_reason(source: Path, build_system: str) -> str | None:
    if build_system == "cmake":
        return None if (source / "CMakeLists.txt").is_file() else "cmakelists_missing"
    if build_system == "make":
        markers = ("Makefile", "makefile", "GNUmakefile")
        return (
            None
            if any((source / marker).is_file() for marker in markers)
            else "root_makefile_missing"
        )
    if build_system == "autotools":
        markers = ("autogen.sh", "bootstrap", "configure.ac", "configure.in")
        return (
            None
            if any((source / marker).is_file() for marker in markers)
            else "autotools_entrypoint_missing"
        )
    return "unknown_build_system"


def initial_commands(
    source: Path, manifest: dict[str, Any], build_system: str
) -> list[dict[str, str]]:
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
        *[
            dict(row)
            for row in manifest["initial_paths"]["autotools"]["after_bootstrap"]
        ],
    ]


def normalize_error_category(stdout: str, stderr: str) -> str:
    text = f"{stdout}\n{stderr}".lower()
    text = re.sub(r"/workspace(?:/[^\s:'\"]+)*", "<workspace>", text)
    text = re.sub(r":\d+(?::\d+)?", ":<line>", text)
    for category, patterns in ERROR_PATTERNS:
        if any(pattern in text for pattern in patterns):
            return category
    return "unknown_build_failure"


def _remove_container(name: str) -> None:
    _run(["docker", "rm", "-f", name], timeout=30)


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
    timeout = max(
        1,
        min(
            int(manifest["budget"]["command_timeout_seconds"]),
            int(remaining_session_seconds),
        ),
    )
    name = f"forge-411-{task_id}-{replicate}-{uuid.uuid4().hex[:8]}"
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
        elapsed = time.monotonic() - started
        infrastructure = completed.returncode == 125 or completed.stderr.startswith(
            "docker:"
        )
        return {
            "phase": phase,
            "command": command,
            "exit_code": completed.returncode,
            "timed_out": False,
            "infrastructure_failure": infrastructure,
            "elapsed_seconds": elapsed,
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
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }
    finally:
        _remove_container(name)


def _clone_source(
    task: dict[str, Any], destination: Path, manifest: dict[str, Any]
) -> dict[str, Any]:
    env = os.environ.copy()
    env["GIT_LFS_SKIP_SMUDGE"] = "1"
    started = time.monotonic()
    clone = _run(
        [
            "git",
            "clone",
            "--filter=blob:none",
            "--no-checkout",
            task["repository_url"],
            str(destination),
        ],
        timeout=manifest["budget"]["clone_timeout_seconds"],
        env=env,
    )
    if clone.returncode != 0:
        return {
            "succeeded": False,
            "stage": "clone",
            "elapsed_seconds": time.monotonic() - started,
            "stdout": clone.stdout,
            "stderr": clone.stderr,
        }
    checkout = _run(
        ["git", "checkout", "--detach", task["commit_sha"]],
        cwd=destination,
        timeout=manifest["budget"]["clone_timeout_seconds"],
        env=env,
    )
    if checkout.returncode != 0:
        return {
            "succeeded": False,
            "stage": "checkout",
            "elapsed_seconds": time.monotonic() - started,
            "stdout": checkout.stdout,
            "stderr": checkout.stderr,
        }
    submodule = _run(
        ["git", "submodule", "update", "--init", "--recursive", "--depth", "1"],
        cwd=destination,
        timeout=manifest["budget"]["submodule_timeout_seconds"],
        env=env,
    )
    if submodule.returncode != 0:
        return {
            "succeeded": False,
            "stage": "submodule",
            "elapsed_seconds": time.monotonic() - started,
            "stdout": submodule.stdout,
            "stderr": submodule.stderr,
        }
    head = _run(["git", "rev-parse", "HEAD"], cwd=destination, timeout=30)
    status = _run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=destination,
        timeout=30,
    )
    submodule_status = _run(
        ["git", "submodule", "status", "--recursive"], cwd=destination, timeout=60
    )
    identity_payload = {
        "commit_sha": head.stdout.strip(),
        "submodules": sorted(submodule_status.stdout.splitlines()),
    }
    clean = not status.stdout.strip()
    succeeded = head.stdout.strip() == task["commit_sha"] and clean
    return {
        "succeeded": succeeded,
        "stage": "source_identity" if not succeeded else "complete",
        "elapsed_seconds": time.monotonic() - started,
        "stdout": clone.stdout + checkout.stdout + submodule.stdout,
        "stderr": clone.stderr + checkout.stderr + submodule.stderr,
        "head": head.stdout.strip(),
        "clean": clean,
        "status": status.stdout,
        "submodules": identity_payload["submodules"],
        "source_identity_sha256": _canonical_sha256(identity_payload),
    }


def _write_command_logs(
    evidence_task_root: Path,
    replicate: int,
    index: int,
    command: dict[str, Any],
) -> dict[str, Any]:
    prefix = evidence_task_root / f"replicate-{replicate}-command-{index}"
    stdout_path = prefix.with_suffix(".stdout.log")
    stderr_path = prefix.with_suffix(".stderr.log")
    stdout_path.write_text(command.pop("stdout"), encoding="utf-8", errors="replace")
    stderr_path.write_text(command.pop("stderr"), encoding="utf-8", errors="replace")
    command["stdout_path"] = str(stdout_path.relative_to(REPO_ROOT))
    command["stderr_path"] = str(stderr_path.relative_to(REPO_ROOT))
    command["stdout_sha256"] = _sha256_file(stdout_path)
    command["stderr_sha256"] = _sha256_file(stderr_path)
    return command


def _run_replicate(
    *,
    source: Path,
    workspace: Path,
    evidence_task_root: Path,
    task: dict[str, Any],
    replicate: int,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    shutil.copytree(source, workspace, symlinks=True)
    commands = initial_commands(workspace, manifest, task["selected_build_system"])
    started = time.monotonic()
    observed: list[dict[str, Any]] = []
    for index, command in enumerate(commands, start=1):
        remaining = manifest["budget"]["session_timeout_seconds"] - (
            time.monotonic() - started
        )
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
                    task_id=task["task_id"],
                    replicate=replicate,
                    manifest=manifest,
                    remaining_session_seconds=remaining,
                )
            )
        if (
            observed[-1]["exit_code"] != 0
            or observed[-1]["timed_out"]
            or observed[-1]["infrastructure_failure"]
        ):
            break

    for index, command in enumerate(observed, start=1):
        _write_command_logs(evidence_task_root, replicate, index, command)
    final = observed[-1]
    if final["timed_out"]:
        outcome = "timeout"
        error_category = "timeout"
    elif final["infrastructure_failure"]:
        outcome = "infrastructure_failure"
        error_category = "docker_runtime_failure"
    elif final["exit_code"] == 0:
        outcome = "initial_success"
        error_category = None
    else:
        outcome = "bounded_failure"
        stdout = (REPO_ROOT / final["stdout_path"]).read_text(
            encoding="utf-8", errors="replace"
        )
        stderr = (REPO_ROOT / final["stderr_path"]).read_text(
            encoding="utf-8", errors="replace"
        )
        error_category = normalize_error_category(stdout, stderr)
    result = {
        "replicate": replicate,
        "outcome": outcome,
        "failure_phase": final["phase"] if outcome != "initial_success" else None,
        "error_category": error_category,
        "elapsed_seconds": time.monotonic() - started,
        "commands": observed,
    }
    _write_json_atomic(evidence_task_root / f"replicate-{replicate}.json", result)
    shutil.rmtree(workspace)
    return result


def _classify_task(replicates: list[dict[str, Any]]) -> tuple[str, str]:
    outcomes = [row["outcome"] for row in replicates]
    if all(outcome == "initial_success" for outcome in outcomes):
        return "initial_success", "both_initial_paths_succeeded"
    if any(outcome == "infrastructure_failure" for outcome in outcomes):
        return "infrastructure_failure", "replicate_infrastructure_failure"
    if any(outcome == "timeout" for outcome in outcomes):
        return "timeout", "replicate_timeout"
    if outcomes != ["bounded_failure", "bounded_failure"]:
        return "inconsistent_failure", "replicate_outcomes_differ"
    phases = {row["failure_phase"] for row in replicates}
    categories = {row["error_category"] for row in replicates}
    if len(phases) != 1 or len(categories) != 1:
        return "inconsistent_failure", "failure_phase_or_category_differs"
    return "stable_natural_failure", "two_clean_replays_agree"


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


def _decision(
    results: list[dict[str, Any]], manifest: dict[str, Any]
) -> dict[str, Any]:
    stable = [
        row for row in results if row["classification"] == "stable_natural_failure"
    ]
    counts: dict[str, dict[str, int]] = {
        system: {role: 0 for role in ROLES} for system in SYSTEMS
    }
    for row in stable:
        counts[row["selected_build_system"]][row["role"]] += 1
    required = manifest["qualification"]["required_by_system_and_role"]
    failures = [
        f"{system}:{role}:{counts[system][role]}<{required[role]}"
        for system in SYSTEMS
        for role in ROLES
        if counts[system][role] < required[role]
    ]
    passed = not failures
    return {
        "passed": passed,
        "decision": (
            manifest["qualification"]["pass_decision"]
            if passed
            else manifest["qualification"]["fail_decision"]
        ),
        "stable_failure_counts": counts,
        "failed_requirements": failures,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Jev 自然构建失败 source qualification v1 结果",
        "",
        f"- 状态：`{report['status']}`",
        f"- 决定：`{report['qualification']['decision']}`",
        f"- 候选：{report['summary']['tasks_total']}；稳定自然失败：{report['summary']['stable_natural_failures']}",
        "- Provider：0 request / 0 token；credential：0 read",
        "",
        "## 角色配额",
        "",
        "| 构建系统 | design | calibration | evaluation |",
        "| --- | ---: | ---: | ---: |",
    ]
    counts = report["qualification"]["stable_failure_counts"]
    for system in SYSTEMS:
        lines.append(
            f"| {system} | {counts[system]['design']} | {counts[system]['calibration']} | {counts[system]['evaluation']} |"
        )
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
        failure = row.get("stable_failure") or "-"
        lines.append(
            f"| `{row['task_id']}` | {row['selected_build_system']} | {row['role']} | "
            f"`{row['classification']}` | {failure} |"
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "本结果只评估冻结项目能否形成稳定自然失败来源。它不验证 reference recipe、动作矩阵、",
            "Jev/Agent 效果、成本收益或动态预算控制。",
            "",
        ]
    )
    return "\n".join(lines)


def execute() -> dict[str, Any]:
    preflight_result = preflight(require_authorized=True)
    if not preflight_result["ready"]:
        raise RuntimeError(
            "preflight_failed:"
            + json.dumps(preflight_result["errors"], ensure_ascii=False)
        )
    manifest = _load_json(MANIFEST_PATH)
    source_pool = _load_json(SOURCE_POOL_PATH)
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
        "source_pool_sha256": preflight_result["source_pool_sha256"],
        "tasks_completed": 0,
        "credential_reads": 0,
        "provider_requests": 0,
        "model_tokens": 0,
    }
    _write_json_atomic(marker_path, marker)
    shutil.copy2(MANIFEST_PATH, evidence_root / "manifest.json")
    shutil.copy2(SOURCE_POOL_PATH, evidence_root / "source-pool.json")
    results: list[dict[str, Any]] = []
    global_error: str | None = None
    try:
        for task in source_pool["tasks"]:
            if (
                time.monotonic() - started_monotonic
                >= manifest["budget"]["total_wall_clock_seconds"]
            ):
                raise TimeoutError("batch_total_wall_clock_exhausted")
            task_root = evidence_root / "tasks" / task["task_id"]
            task_root.mkdir(parents=True, exist_ok=False)
            source = work_root / f"source-{task['task_id']}"
            clone = _clone_source(task, source, manifest)
            clone_stdout = task_root / "source.stdout.log"
            clone_stderr = task_root / "source.stderr.log"
            clone_stdout.write_text(
                clone.pop("stdout"), encoding="utf-8", errors="replace"
            )
            clone_stderr.write_text(
                clone.pop("stderr"), encoding="utf-8", errors="replace"
            )
            clone["stdout_sha256"] = _sha256_file(clone_stdout)
            clone["stderr_sha256"] = _sha256_file(clone_stderr)
            clone["stdout_path"] = str(clone_stdout.relative_to(REPO_ROOT))
            clone["stderr_path"] = str(clone_stderr.relative_to(REPO_ROOT))
            _write_json_atomic(task_root / "source.json", clone)
            result = {
                "task_id": task["task_id"],
                "project_family": task["project_family"],
                "selected_build_system": task["selected_build_system"],
                "role": task["role"],
                "system_rank": task["system_rank"],
                "commit_sha": task["commit_sha"],
                "source": clone,
                "replicates": [],
            }
            if not clone["succeeded"]:
                result["classification"] = "infrastructure_failure"
                result["reason"] = f"source_{clone['stage']}_failed"
            else:
                contract_reason = source_contract_reason(
                    source, task["selected_build_system"]
                )
                if contract_reason:
                    result["classification"] = "source_contract_ineligible"
                    result["reason"] = contract_reason
                else:
                    for replicate in range(
                        1, manifest["budget"]["replicates_per_task"] + 1
                    ):
                        workspace = (
                            work_root / f"workspace-{task['task_id']}-{replicate}"
                        )
                        replicate_result = _run_replicate(
                            source=source,
                            workspace=workspace,
                            evidence_task_root=task_root,
                            task=task,
                            replicate=replicate,
                            manifest=manifest,
                        )
                        result["replicates"].append(replicate_result)
                    classification, reason = _classify_task(result["replicates"])
                    result["classification"] = classification
                    result["reason"] = reason
                    if classification == "stable_natural_failure":
                        first = result["replicates"][0]
                        result["stable_failure"] = (
                            f"{first['failure_phase']} / {first['error_category']}"
                        )
            _write_json_atomic(task_root / "result.json", result)
            results.append(result)
            if source.exists():
                shutil.rmtree(source)
            containers = _managed_containers()
            if containers:
                raise RuntimeError(f"managed_containers_after_task:{containers}")
            marker["tasks_completed"] = len(results)
            marker["last_task_id"] = task["task_id"]
            _write_json_atomic(marker_path, marker)
    except BaseException as exc:
        global_error = f"{type(exc).__name__}:{exc}"
    finally:
        if work_root.exists():
            shutil.rmtree(work_root)
        remaining = _managed_containers()
        for name in remaining:
            _remove_container(name)

    qualification = _decision(results, manifest)
    classifications = Counter(row["classification"] for row in results)
    status = "completed" if global_error is None else "failed"
    if global_error is not None:
        qualification = {
            **qualification,
            "passed": False,
            "decision": "attempt_failed",
            "global_error": global_error,
        }
    inventory = _inventory(evidence_root)
    report = {
        "schema_version": "forge-jev-natural-failure-source-qualification-report-1.0.0",
        "identity": IDENTITY,
        "status": status,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "execution_revision": preflight_result["head"],
        "manifest_canonical_sha256": preflight_result["manifest_canonical_sha256"],
        "source_pool_sha256": preflight_result["source_pool_sha256"],
        "summary": {
            "tasks_total": len(source_pool["tasks"]),
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
            "evidence_inventory_canonical_sha256": report[
                "evidence_inventory_canonical_sha256"
            ],
            "managed_containers_after_cleanup": _managed_containers(),
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
    if (
        marker.get("credential_reads")
        or marker.get("provider_requests")
        or marker.get("model_tokens")
    ):
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
    parser.add_argument(
        "command", choices=("protocol-validate", "preflight", "execute", "audit")
    )
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
