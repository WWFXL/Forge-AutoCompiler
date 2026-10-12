#!/usr/bin/env python3
"""Issue #423 动态预算多步轨迹 benchmark 零 Provider 资格 runner。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tarfile
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

IDENTITY = "cpp-dynamic-budget-trajectory-benchmark-qualification-v1"
SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests" / f"{IDENTITY}.json"
REPORT_JSON_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.json"
REPORT_MD_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.md"
HISTORICAL_MANIFEST_PATH = (
    REPO_ROOT / "benchmarks/manifests/cpp-jev-formal-comparison-v6.json"
)
SYSTEMS = ("cmake", "make", "autotools")
BUDGET_FIELDS = (
    "wall_clock_milliseconds",
    "provider_requests",
    "input_tokens",
    "output_tokens",
    "provider_cost_microusd",
    "build_executions",
)
PROVIDER_FIELDS = (
    "provider_requests",
    "input_tokens",
    "output_tokens",
    "provider_cost_microusd",
)
ALLOWED_ROLES = frozenset({"configure", "build", "smoke", "artifact_stage"})
LABEL_KEY = "forge.dynamic_budget_trajectory_identity"


class QualificationError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise QualificationError(f"JSON root must be object: {path}")
    return value


def _write_json_atomic(path: Path, value: Any, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if exclusive and path.exists():
        temporary.unlink()
        raise QualificationError(f"create-once path already exists: {path}")
    os.replace(temporary, path)


def _run(
    argv: list[str],
    *,
    cwd: Path = REPO_ROOT,
    timeout: int | float | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, cwd=cwd, text=True, capture_output=True, timeout=timeout, check=False
    )


def _preview(value: str, limit: int = 2000) -> str:
    return value if len(value) <= limit else value[-limit:]


def _budget_zero() -> dict[str, int]:
    return {field: 0 for field in BUDGET_FIELDS}


def _budget_add(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    return {field: left[field] + right[field] for field in BUDGET_FIELDS}


def _require_exact_fields(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise QualificationError(f"{label} fields drifted")
    return value


def _validate_budget(value: Any, label: str) -> dict[str, int]:
    budget = _require_exact_fields(value, set(BUDGET_FIELDS), label)
    for field in BUDGET_FIELDS:
        if type(budget[field]) is not int or budget[field] < 0:
            raise QualificationError(f"{label}.{field} must be non-negative integer")
    return budget


def _historical_evaluation_families() -> set[str]:
    manifest = _load_json(HISTORICAL_MANIFEST_PATH)
    text = json.dumps(manifest).lower()
    families: set[str] = set()
    for project in manifest.get("experiment", {}).get("projects", []):
        family = project.get("project_family")
        if isinstance(family, str):
            families.add(family.lower().removeprefix("https://"))
    if not families:
        for token in (
            "libgit2/libgit2",
            "simdjson/simdjson",
            "google/benchmark",
            "pcre2project/pcre2",
            "haproxy/haproxy",
            "cc65/cc65",
            "bellard/quickjs",
            "redis/redis",
            "libarchive/libarchive",
            "curl/curl",
            "jemalloc/jemalloc",
            "wolfssl/wolfssl",
        ):
            if token in text:
                families.add(f"github.com/{token}")
    return families


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    required = {
        "$schema",
        "schema_version",
        "identity",
        "issue",
        "parent_issue",
        "implementation_revision",
        "image",
        "authorization",
        "evidence_root",
        "repetitions_per_state",
        "states_per_project",
        "shared_block_budget",
        "allocation",
        "projects",
        "qualification",
    }
    _require_exact_fields(manifest, required, "manifest")
    if manifest["identity"] != IDENTITY or manifest["issue"] != 423:
        raise QualificationError("identity or tracking issue drifted")
    if manifest["repetitions_per_state"] != 2 or manifest["states_per_project"] != 3:
        raise QualificationError("state/repetition schedule drifted")
    authorization = manifest["authorization"]
    if authorization != {
        "zero_provider_collection": True,
        "credential_read": False,
        "provider_request": False,
        "agent_continuation": False,
        "controller_implementation": False,
        "historical_evidence_write": False,
    }:
        raise QualificationError("authorization boundary drifted")
    image = _require_exact_fields(manifest["image"], {"reference", "id"}, "image")
    if not isinstance(image["id"], str) or not image["id"].startswith("sha256:"):
        raise QualificationError("full image ID is required")
    block_budget = _validate_budget(
        manifest["shared_block_budget"], "shared_block_budget"
    )
    if any(block_budget[field] != 0 for field in PROVIDER_FIELDS):
        raise QualificationError("Provider dimensions must have zero limits")
    if block_budget["build_executions"] != 18:
        raise QualificationError("shared build execution limit drifted")

    projects = manifest["projects"]
    if not isinstance(projects, list) or len(projects) != 9:
        raise QualificationError("exactly nine projects are required")
    counts: Counter[str] = Counter()
    families: set[str] = set()
    case_ids: set[str] = set()
    historical = _historical_evaluation_families()
    for project in projects:
        required_project = {
            "case_id",
            "build_system",
            "project_family",
            "repository_url",
            "commit_sha",
            "actions",
        }
        _require_exact_fields(project, required_project, "project")
        system = project["build_system"]
        family = project["project_family"].lower()
        if system not in SYSTEMS:
            raise QualificationError(f"unsupported build system: {system}")
        if project["case_id"] in case_ids or family in families:
            raise QualificationError("case/project families must be unique")
        if family in historical:
            raise QualificationError(
                f"project overlaps historical Jev evaluation: {family}"
            )
        if (
            not isinstance(project["commit_sha"], str)
            or len(project["commit_sha"]) != 40
        ):
            raise QualificationError("exact 40-hex commit is required")
        int(project["commit_sha"], 16)
        actions = project["actions"]
        if not isinstance(actions, list) or len(actions) != 3:
            raise QualificationError("each project requires three actions")
        action_ids: set[str] = set()
        for action in actions:
            _require_exact_fields(
                action, {"action_id", "role", "command", "declared_outputs"}, "action"
            )
            if action["action_id"] in action_ids or action["role"] not in ALLOWED_ROLES:
                raise QualificationError("action identity or role is invalid")
            if not isinstance(action["command"], str) or not action["command"].strip():
                raise QualificationError("action command is empty")
            if (
                not isinstance(action["declared_outputs"], list)
                or not action["declared_outputs"]
            ):
                raise QualificationError("declared outputs are required")
            action_ids.add(action["action_id"])
        counts[system] += 1
        case_ids.add(project["case_id"])
        families.add(family)
    if counts != Counter({system: 3 for system in SYSTEMS}):
        raise QualificationError("three projects per build system are required")

    allocation = _require_exact_fields(
        manifest["allocation"],
        {
            "first_project",
            "second_project",
            "third_project_before_stop",
            "stopped_reservation",
        },
        "allocation",
    )
    for label, value in allocation.items():
        _require_exact_fields(
            value,
            {"wall_clock_milliseconds", "build_executions"},
            f"allocation.{label}",
        )
        if any(type(value[field]) is not int or value[field] < 0 for field in value):
            raise QualificationError("allocation values must be non-negative integers")
    if allocation["third_project_before_stop"] != {
        "wall_clock_milliseconds": 0,
        "build_executions": 0,
    }:
        raise QualificationError("third project must start without allocation")
    if allocation["stopped_reservation"] != {
        "wall_clock_milliseconds": 300000,
        "build_executions": 6,
    }:
        raise QualificationError("stopped reservation drifted")
    return manifest


def _docker_image_id(reference: str) -> str:
    result = _run(
        ["docker", "image", "inspect", reference, "--format", "{{.Id}}"], timeout=30
    )
    if result.returncode != 0:
        raise QualificationError(f"Docker image unavailable: {_preview(result.stderr)}")
    return result.stdout.strip()


def _managed_containers() -> list[str]:
    result = _run(
        ["docker", "ps", "-aq", "--filter", f"label={LABEL_KEY}={IDENTITY}"], timeout=30
    )
    if result.returncode != 0:
        raise QualificationError(
            f"cannot list managed containers: {_preview(result.stderr)}"
        )
    return [line for line in result.stdout.splitlines() if line]


def _cleanup_managed_containers() -> list[str]:
    containers = _managed_containers()
    if containers:
        result = _run(["docker", "rm", "-f", *containers], timeout=60)
        if result.returncode != 0:
            raise QualificationError(
                f"managed container cleanup failed: {_preview(result.stderr)}"
            )
    return _managed_containers()


def preflight(manifest: dict[str, Any], *, require_absent: bool) -> dict[str, Any]:
    validate_manifest(manifest)
    evidence_root = REPO_ROOT / manifest["evidence_root"]
    if require_absent and evidence_root.exists():
        raise QualificationError(
            f"create-once evidence root already exists: {evidence_root}"
        )
    actual_image_id = _docker_image_id(manifest["image"]["reference"])
    if actual_image_id != manifest["image"]["id"]:
        raise QualificationError("Docker image identity drifted")
    containers = _managed_containers()
    if containers:
        raise QualificationError(
            f"managed containers exist before execution: {containers}"
        )
    return {
        "ready": True,
        "manifest_sha256": _sha256_file(MANIFEST_PATH),
        "manifest_canonical_sha256": _canonical_sha256(manifest),
        "image_id": actual_image_id,
        "managed_containers": containers,
        "credential_read": False,
        "provider_requests": 0,
    }


def _tree_entries(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not root.exists():
        return entries
    for path in sorted(
        root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
    ):
        relative = path.relative_to(root).as_posix()
        if relative == ".git" or relative.startswith(".git/"):
            continue
        mode = stat.S_IMODE(path.lstat().st_mode) & 0o111
        if path.is_symlink():
            entries.append(
                {
                    "path": relative,
                    "kind": "symlink",
                    "mode": mode,
                    "target": os.readlink(path),
                }
            )
        elif path.is_file():
            entries.append(
                {
                    "path": relative,
                    "kind": "file",
                    "mode": mode,
                    "size": path.stat().st_size,
                    "sha256": _sha256_file(path),
                }
            )
    return entries


def _tree_sha256(root: Path) -> str:
    return _canonical_sha256(_tree_entries(root))


def _create_snapshot(root: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, "w:gz", compresslevel=1) as archive:
        for path in sorted(
            root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
        ):
            relative = path.relative_to(root)
            if relative.parts and relative.parts[0] == ".git":
                continue
            archive.add(path, arcname=relative.as_posix(), recursive=False)
    return _sha256_file(destination)


def _restore_snapshot(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(source, "r:gz") as archive:
        archive.extractall(destination, filter="data")


def _path_signature(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        return {"kind": "symlink", "target": os.readlink(path)}
    if path.is_file():
        return {
            "kind": "file",
            "size": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
    if path.is_dir():
        return {"kind": "directory", "tree_sha256": _tree_sha256(path)}
    return {"kind": "missing"}


def _declared_output_signatures(
    action: dict[str, Any], workspace: Path, artifacts: Path
) -> dict[str, Any]:
    signatures: dict[str, Any] = {}
    for raw_path in action["declared_outputs"]:
        if raw_path == "/artifacts" or raw_path.startswith("/artifacts/"):
            relative = raw_path.removeprefix("/artifacts").lstrip("/")
            path = artifacts / relative
        else:
            if raw_path.startswith("/") or ".." in Path(raw_path).parts:
                raise QualificationError(f"declared output path is unsafe: {raw_path}")
            path = workspace / raw_path
        signature = _path_signature(path)
        if signature["kind"] == "missing":
            raise QualificationError(f"declared output is missing: {raw_path}")
        signatures[raw_path] = signature
    return signatures


def _source_identity(project: dict[str, Any]) -> dict[str, str]:
    payload = {
        "repository_url": project["repository_url"],
        "commit_sha": project["commit_sha"],
    }
    return {**payload, "sha256": _canonical_sha256(payload)}


def _clone_source(project: dict[str, Any], destination: Path) -> None:
    clone = _run(
        [
            "git",
            "clone",
            "--quiet",
            "--filter=blob:none",
            "--no-checkout",
            project["repository_url"],
            str(destination),
        ],
        timeout=180,
    )
    if clone.returncode != 0:
        raise QualificationError(
            f"source clone failed for {project['case_id']}: {_preview(clone.stderr)}"
        )
    checkout = _run(
        [
            "git",
            "-C",
            str(destination),
            "checkout",
            "--quiet",
            "--detach",
            project["commit_sha"],
        ],
        timeout=180,
    )
    if checkout.returncode != 0:
        raise QualificationError(
            f"exact commit checkout failed for {project['case_id']}: {_preview(checkout.stderr)}"
        )
    actual = _run(["git", "-C", str(destination), "rev-parse", "HEAD"], timeout=30)
    if actual.returncode != 0 or actual.stdout.strip() != project["commit_sha"]:
        raise QualificationError(f"source identity mismatch for {project['case_id']}")
    shutil.rmtree(destination / ".git")


def _run_continuation(
    *,
    manifest: dict[str, Any],
    project: dict[str, Any],
    action: dict[str, Any],
    state_id: str,
    repetition: int,
    checkpoint_dir: Path,
    output_dir: Path,
) -> tuple[dict[str, Any], Path, Path]:
    workspace = output_dir / "workspace"
    artifacts = output_dir / "artifacts"
    _restore_snapshot(checkpoint_dir / "workspace.tar.gz", workspace)
    _restore_snapshot(checkpoint_dir / "artifacts.tar.gz", artifacts)
    name = f"forge-dbt-{uuid.uuid4().hex[:16]}"
    argv = [
        "docker",
        "run",
        "--name",
        name,
        "--label",
        f"{LABEL_KEY}={IDENTITY}",
    ]
    if globals().get("DETERMINISTIC_HOSTNAME", False):
        argv.extend(["--hostname", state_id])
    argv.extend(
        [
            "--network",
            "none",
            "--cpus",
            "2",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--env",
            "HOME=/tmp",
            "-v",
            f"{workspace}:/workspace/repo",
            "-v",
            f"{artifacts}:/artifacts",
            "-w",
            "/workspace/repo",
            manifest["image"]["id"],
            "bash",
            "-lc",
            f"set -euo pipefail\n{action['command']}",
        ]
    )
    started = time.monotonic_ns()
    timed_out = False
    try:
        completed = _run(argv, timeout=180)
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = 124
        stdout = (
            exc.stdout.decode(errors="replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or "")
        )
        stderr = (
            exc.stderr.decode(errors="replace")
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or "")
        )
    finally:
        _run(["docker", "rm", "-f", name], timeout=30)
    duration_ms = max(1, (time.monotonic_ns() - started + 999_999) // 1_000_000)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "stdout.log").write_text(stdout, encoding="utf-8", errors="replace")
    (output_dir / "stderr.log").write_text(stderr, encoding="utf-8", errors="replace")
    declared = (
        _declared_output_signatures(action, workspace, artifacts)
        if exit_code == 0
        else {}
    )
    successor = {
        "state_id": state_id,
        "case_id": project["case_id"],
        "action_id": action["action_id"],
        "action_role": action["role"],
        "exit_code": exit_code,
        "timed_out": timed_out,
        "declared_outputs": declared,
        "workspace_tree_sha256": _tree_sha256(workspace),
        "artifacts_tree_sha256": _tree_sha256(artifacts),
    }
    result = {
        "repetition": repetition,
        "container_name": name,
        "duration_milliseconds": duration_ms,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stdout_sha256": _sha256_bytes(stdout.encode()),
        "stderr_sha256": _sha256_bytes(stderr.encode()),
        "stdout_preview": _preview(stdout),
        "stderr_preview": _preview(stderr),
        "successor": successor,
        "successor_sha256": _canonical_sha256(successor),
    }
    _write_json_atomic(output_dir / "result.json", result, exclusive=True)
    return result, workspace, artifacts


def _checkpoint(
    *,
    manifest: dict[str, Any],
    project: dict[str, Any],
    state_id: str,
    workspace: Path,
    artifacts: Path,
    message: dict[str, Any],
    budget_before: dict[str, int],
    checkpoint_dir: Path,
) -> dict[str, Any]:
    checkpoint_dir.mkdir(parents=True, exist_ok=False)
    workspace_sha = _create_snapshot(workspace, checkpoint_dir / "workspace.tar.gz")
    artifacts_sha = _create_snapshot(artifacts, checkpoint_dir / "artifacts.tar.gz")
    message_sha = _canonical_sha256(message)
    budget_sha = _canonical_sha256(budget_before)
    payload = {
        "state_id": state_id,
        "source": _source_identity(project),
        "image_id": manifest["image"]["id"],
        "workspace_snapshot_sha256": workspace_sha,
        "artifacts_snapshot_sha256": artifacts_sha,
        "message_sha256": message_sha,
        "budget_sha256": budget_sha,
    }
    checkpoint = {**payload, "checkpoint_sha256": _canonical_sha256(payload)}
    _write_json_atomic(checkpoint_dir / "message.json", message, exclusive=True)
    _write_json_atomic(checkpoint_dir / "budget.json", budget_before, exclusive=True)
    _write_json_atomic(checkpoint_dir / "checkpoint.json", checkpoint, exclusive=True)
    return checkpoint


def _budget_record(
    before: dict[str, int], repetitions: list[dict[str, Any]]
) -> dict[str, Any]:
    delta = _budget_zero()
    delta["wall_clock_milliseconds"] = sum(
        item["duration_milliseconds"] for item in repetitions
    )
    delta["build_executions"] = len(repetitions)
    after = _budget_add(before, delta)
    return {
        "before": before,
        "delta": delta,
        "after": after,
        "conserved": after == _budget_add(before, delta),
    }


def _inventory(root: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "inventory.json":
            files.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": _sha256_file(path),
                }
            )
    return {
        "files": files,
        "file_count": len(files),
        "total_bytes": sum(item["size"] for item in files),
        "canonical_sha256": _canonical_sha256(files),
    }


def _qualification(result: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    states = result.get("states", [])
    projects = result.get("projects", [])
    blocks = result.get("blocks", [])
    gates = {
        "project_coverage": len(projects) == 9
        and Counter(item["build_system"] for item in projects)
        == Counter({system: 3 for system in SYSTEMS}),
        "multistep_coverage": len(states) == 27
        and all(item.get("state_count") == 3 for item in projects),
        "checkpoint_binding": len(states) == 27
        and all(
            len(item.get("checkpoint", {}).get("checkpoint_sha256", "")) == 64
            for item in states
        ),
        "clean_continuations": len(states) == 27
        and sum(len(item.get("repetitions", [])) for item in states) == 54
        and all(
            rep["exit_code"] == 0 for item in states for rep in item["repetitions"]
        ),
        "repetition_consistency": len(states) == 27
        and all(item.get("consistent") is True for item in states),
        "budget_conservation": len(states) == 27
        and all(item.get("budget", {}).get("conserved") is True for item in states)
        and all(block.get("within_limit") is True for block in blocks),
        "stop_transfer": len(blocks) == 3
        and all(
            block.get("stop_transfer", {}).get("passed") is True for block in blocks
        ),
        "post_action_observation": len(states) == 27
        and all(
            item.get("successor_observed") is True and item.get("agent_calls") == 0
            for item in states
        ),
        "cleanup": result.get("managed_containers_after_cleanup") == [],
    }
    passed = all(gates.values())
    return {
        "gates": gates,
        "passed": passed,
        "decision": manifest["qualification"]["pass_decision"]
        if passed
        else manifest["qualification"]["fail_decision"],
    }


def execute(manifest: dict[str, Any]) -> dict[str, Any]:
    preflight_result = preflight(manifest, require_absent=True)
    root = REPO_ROOT / manifest["evidence_root"]
    root.mkdir(parents=True, exist_ok=False)
    marker_path = root / "attempt.json"
    result_path = root / "result.json"
    marker = {
        "identity": IDENTITY,
        "status": "running",
        "started_at": _utc_now(),
        "manifest_sha256": preflight_result["manifest_sha256"],
        "credential_read": False,
        "provider_requests": 0,
    }
    _write_json_atomic(marker_path, marker, exclusive=True)
    result: dict[str, Any] = {
        "schema_version": "1.0.0",
        "identity": IDENTITY,
        "status": "running",
        "started_at": marker["started_at"],
        "completed_at": None,
        "manifest_sha256": preflight_result["manifest_sha256"],
        "manifest_canonical_sha256": preflight_result["manifest_canonical_sha256"],
        "image_id": preflight_result["image_id"],
        "credential_read": False,
        "provider_requests": 0,
        "projects": [],
        "states": [],
        "blocks": [],
        "failure": None,
        "managed_containers_after_cleanup": None,
        "qualification": None,
    }
    working_root = root / "working"
    try:
        for system in SYSTEMS:
            system_projects = [
                project
                for project in manifest["projects"]
                if project["build_system"] == system
            ]
            block_used = _budget_zero()
            allocation_spec = manifest["allocation"]
            allocations = {
                system_projects[0]["case_id"]: dict(allocation_spec["first_project"]),
                system_projects[1]["case_id"]: dict(allocation_spec["second_project"]),
                system_projects[2]["case_id"]: dict(
                    allocation_spec["third_project_before_stop"]
                ),
                "stopped-reservation": dict(allocation_spec["stopped_reservation"]),
            }
            block = {
                "build_system": system,
                "budget_limit": manifest["shared_block_budget"],
                "budget_used": None,
                "allocations_initial": json.loads(json.dumps(allocations)),
                "stop_transfer": None,
                "within_limit": False,
            }
            for project_index, project in enumerate(system_projects):
                if project_index == 2:
                    transfer_before = json.loads(json.dumps(allocations))
                    released = allocations["stopped-reservation"]
                    allocations[project["case_id"]] = dict(released)
                    allocations["stopped-reservation"] = {
                        "wall_clock_milliseconds": 0,
                        "build_executions": 0,
                    }
                    conserved = sum(
                        item["wall_clock_milliseconds"]
                        for item in transfer_before.values()
                    ) == sum(
                        item["wall_clock_milliseconds"] for item in allocations.values()
                    ) and sum(
                        item["build_executions"] for item in transfer_before.values()
                    ) == sum(item["build_executions"] for item in allocations.values())
                    block["stop_transfer"] = {
                        "stopped_task": "stopped-reservation",
                        "recipient": project["case_id"],
                        "before": transfer_before,
                        "after": json.loads(json.dumps(allocations)),
                        "released": released,
                        "conserved": conserved,
                        "passed": False,
                    }
                project_root = working_root / project["case_id"]
                workspace = project_root / "canonical-workspace"
                artifacts = project_root / "canonical-artifacts"
                workspace.parent.mkdir(parents=True, exist_ok=True)
                _clone_source(project, workspace)
                artifacts.mkdir(parents=True, exist_ok=False)
                message = {
                    "case_id": project["case_id"],
                    "observation": "source_ready",
                    "source": _source_identity(project),
                    "previous_action": None,
                }
                project_used = {"wall_clock_milliseconds": 0, "build_executions": 0}
                project_record = {
                    "case_id": project["case_id"],
                    "build_system": system,
                    "project_family": project["project_family"],
                    "state_count": 0,
                    "budget_used": None,
                }
                for state_index, action in enumerate(project["actions"], start=1):
                    state_id = f"{project['case_id']}-state-{state_index}"
                    state_root = root / "states" / state_id
                    checkpoint = _checkpoint(
                        manifest=manifest,
                        project=project,
                        state_id=state_id,
                        workspace=workspace,
                        artifacts=artifacts,
                        message=message,
                        budget_before=block_used,
                        checkpoint_dir=state_root / "checkpoint",
                    )
                    repetitions: list[dict[str, Any]] = []
                    successors: list[tuple[Path, Path]] = []
                    for repetition in (1, 2):
                        (
                            repetition_result,
                            repetition_workspace,
                            repetition_artifacts,
                        ) = _run_continuation(
                            manifest=manifest,
                            project=project,
                            action=action,
                            state_id=state_id,
                            repetition=repetition,
                            checkpoint_dir=state_root / "checkpoint",
                            output_dir=state_root / f"repetition-{repetition}",
                        )
                        repetitions.append(repetition_result)
                        successors.append((repetition_workspace, repetition_artifacts))
                    consistent = (
                        repetitions[0]["successor_sha256"]
                        == repetitions[1]["successor_sha256"]
                    )
                    if any(item["exit_code"] != 0 for item in repetitions):
                        raise QualificationError(f"continuation failed at {state_id}")
                    if not consistent:
                        raise QualificationError(f"continuation mismatch at {state_id}")
                    budget_record = _budget_record(dict(block_used), repetitions)
                    block_used = budget_record["after"]
                    project_used["wall_clock_milliseconds"] += budget_record["delta"][
                        "wall_clock_milliseconds"
                    ]
                    project_used["build_executions"] += budget_record["delta"][
                        "build_executions"
                    ]
                    allocation = allocations[project["case_id"]]
                    if (
                        project_used["wall_clock_milliseconds"]
                        > allocation["wall_clock_milliseconds"]
                        or project_used["build_executions"]
                        > allocation["build_executions"]
                    ):
                        raise QualificationError(
                            f"project allocation exceeded at {state_id}"
                        )
                    if any(
                        block_used[field] > manifest["shared_block_budget"][field]
                        for field in BUDGET_FIELDS
                    ):
                        raise QualificationError(
                            f"shared block budget exceeded at {state_id}"
                        )
                    for field in PROVIDER_FIELDS:
                        if (
                            budget_record["before"][field] != 0
                            or budget_record["delta"][field] != 0
                            or budget_record["after"][field] != 0
                        ):
                            raise QualificationError(
                                "Provider budget changed during zero Provider qualification"
                            )
                    shutil.rmtree(workspace)
                    shutil.rmtree(artifacts)
                    shutil.copytree(successors[0][0], workspace, symlinks=True)
                    shutil.copytree(successors[0][1], artifacts, symlinks=True)
                    message = repetitions[0]["successor"]
                    for repetition_workspace, repetition_artifacts in successors:
                        shutil.rmtree(repetition_workspace)
                        shutil.rmtree(repetition_artifacts)
                    state_record = {
                        "state_id": state_id,
                        "case_id": project["case_id"],
                        "build_system": system,
                        "action_id": action["action_id"],
                        "action_role": action["role"],
                        "checkpoint": checkpoint,
                        "repetitions": repetitions,
                        "consistent": consistent,
                        "budget": budget_record,
                        "successor_observed": True,
                        "agent_calls": 0,
                    }
                    _write_json_atomic(
                        state_root / "state.json", state_record, exclusive=True
                    )
                    result["states"].append(state_record)
                    project_record["state_count"] += 1
                project_record["budget_used"] = project_used
                result["projects"].append(project_record)
                if project_index == 2 and block["stop_transfer"] is not None:
                    released = block["stop_transfer"]["released"]
                    block["stop_transfer"]["passed"] = (
                        block["stop_transfer"]["conserved"]
                        and project_used["build_executions"]
                        == released["build_executions"]
                        and project_used["wall_clock_milliseconds"]
                        <= released["wall_clock_milliseconds"]
                    )
            block["budget_used"] = block_used
            block["within_limit"] = all(
                block_used[field] <= manifest["shared_block_budget"][field]
                for field in BUDGET_FIELDS
            )
            result["blocks"].append(block)
        shutil.rmtree(working_root)
        result["status"] = "completed"
    except Exception as exc:
        result["status"] = "failed"
        result["failure"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        cleanup_error: str | None = None
        try:
            result["managed_containers_after_cleanup"] = _cleanup_managed_containers()
        except Exception as exc:
            cleanup_error = str(exc)
            result["managed_containers_after_cleanup"] = ["cleanup_failed"]
            if result["failure"] is None:
                result["failure"] = {
                    "type": type(exc).__name__,
                    "message": cleanup_error,
                }
            result["status"] = "failed"
        result["completed_at"] = _utc_now()
        result["qualification"] = _qualification(result, manifest)
        if not result["qualification"]["passed"]:
            result["status"] = "failed"
        _write_json_atomic(result_path, result, exclusive=True)
        marker.update(
            {
                "status": result["status"],
                "completed_at": result["completed_at"],
                "decision": result["qualification"]["decision"],
                "failure": result["failure"],
                "credential_read": False,
                "provider_requests": 0,
            }
        )
        _write_json_atomic(marker_path, marker)
        inventory = _inventory(root)
        _write_json_atomic(root / "inventory.json", inventory, exclusive=True)
        if cleanup_error:
            raise QualificationError(cleanup_error)
    write_report(manifest, root)
    return result


def audit_evidence(manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    validate_manifest(manifest)
    result = _load_json(root / "result.json")
    marker = _load_json(root / "attempt.json")
    inventory = _load_json(root / "inventory.json")
    for entry in inventory.get("files", []):
        path = root / entry["path"]
        if (
            not path.is_file()
            or path.stat().st_size != entry["size"]
            or _sha256_file(path) != entry["sha256"]
        ):
            raise QualificationError(f"evidence inventory mismatch: {entry['path']}")
    if inventory.get("canonical_sha256") != _canonical_sha256(
        inventory.get("files", [])
    ):
        raise QualificationError("inventory canonical hash mismatch")
    if marker.get("decision") != result.get("qualification", {}).get("decision"):
        raise QualificationError("marker/result decision mismatch")
    recomputed = _qualification(result, manifest)
    if recomputed != result.get("qualification"):
        raise QualificationError("qualification result is not reproducible")
    if (
        marker.get("credential_read") is not False
        or marker.get("provider_requests") != 0
    ):
        raise QualificationError("zero Provider boundary drifted")
    observed_repetition_paths = sorted(root.glob("states/*/repetition-*/result.json"))
    return {
        "valid": True,
        "status": result["status"],
        "decision": recomputed["decision"],
        "states": len(result.get("states", [])),
        "continuations": len(observed_repetition_paths),
        "inventory_file_count": inventory["file_count"],
        "inventory_total_bytes": inventory["total_bytes"],
        "inventory_canonical_sha256": inventory["canonical_sha256"],
        "credential_read": False,
        "provider_requests": 0,
    }


def _report_payload(manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    audit = audit_evidence(manifest, root)
    result = _load_json(root / "result.json")
    state_durations = [
        item["budget"]["delta"]["wall_clock_milliseconds"] for item in result["states"]
    ]
    observed_repetitions = [
        _load_json(path)
        for path in sorted(root.glob("states/*/repetition-*/result.json"))
    ]
    attempted_states = sorted(
        {
            item.get("successor", {}).get("state_id")
            for item in observed_repetitions
            if item.get("successor", {}).get("state_id")
        }
    )
    failure_classification = None
    if result.get("failure", {}).get("type") == "LinkOutsideDestinationError":
        failure_classification = "checkpoint_restore_infrastructure_failure"
    return {
        "schema_version": "1.0.0",
        "identity": IDENTITY,
        "status": result["status"],
        "decision": result["qualification"]["decision"],
        "manifest_sha256": result["manifest_sha256"],
        "manifest_canonical_sha256": result["manifest_canonical_sha256"],
        "evidence_inventory_canonical_sha256": audit["inventory_canonical_sha256"],
        "summary": {
            "projects_completed": len(result["projects"]),
            "states_completed": len(result["states"]),
            "states_attempted": len(attempted_states),
            "continuations_recorded": len(observed_repetitions),
            "continuations_in_completed_states": sum(
                len(item["repetitions"]) for item in result["states"]
            ),
            "consistent_states": sum(
                item["consistent"] is True for item in result["states"]
            ),
            "successful_recorded_continuations": sum(
                item.get("exit_code") == 0 for item in observed_repetitions
            ),
            "checkpoint_bindings": sum(
                bool(item["checkpoint"].get("checkpoint_sha256"))
                for item in result["states"]
            ),
            "budget_conserved_states": sum(
                item["budget"]["conserved"] is True for item in result["states"]
            ),
            "stop_transfers": sum(
                block["stop_transfer"]["passed"] is True
                for block in result["blocks"]
                if block.get("stop_transfer")
            ),
            "provider_requests": result["provider_requests"],
            "agent_calls": sum(item["agent_calls"] for item in result["states"]),
            "completed_state_wall_clock_milliseconds": sum(state_durations),
            "recorded_continuation_wall_clock_milliseconds": sum(
                item.get("duration_milliseconds", 0) for item in observed_repetitions
            ),
        },
        "partial_observations": {
            "attempted_state_ids": attempted_states,
            "recorded_repetitions": [
                {
                    "state_id": item.get("successor", {}).get("state_id"),
                    "repetition": item.get("repetition"),
                    "exit_code": item.get("exit_code"),
                    "successor_sha256": item.get("successor_sha256"),
                    "workspace_tree_sha256": item.get("successor", {}).get(
                        "workspace_tree_sha256"
                    ),
                    "artifacts_tree_sha256": item.get("successor", {}).get(
                        "artifacts_tree_sha256"
                    ),
                    "declared_outputs": item.get("successor", {}).get(
                        "declared_outputs"
                    ),
                }
                for item in observed_repetitions
            ],
        },
        "blocks": result["blocks"],
        "projects": result["projects"],
        "qualification": result["qualification"],
        "failure": result["failure"],
        "failure_classification": failure_classification,
        "audit": audit,
        "interpretation": {
            "supports": [
                "跨 CMake、Make、Autotools 的确定性多步 checkpoint continuation 资格"
                if result["qualification"]["passed"]
                else "本 identity 的停止结论与已观察缺口",
                "逐动作六维预算守恒和项目 block 共享预算转移"
                if result["qualification"]["passed"]
                else "失败前已观察状态",
            ],
            "does_not_support": [
                "动态预算 controller 的成功率、成本或时间效果",
                "Jev 或 Agent continuation 的能力",
                "自然失败、开放世界或总体项目泛化",
            ],
        },
    }


def _render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    gates = report["qualification"]["gates"]
    if (
        report.get("failure_classification")
        == "checkpoint_restore_infrastructure_failure"
    ):
        next_step = (
            "当前 identity 已停止。下一步先通过独立的 symlink-safe checkpoint restore "
            "工程门禁，再冻结全新的轨迹资格 identity；不得续跑或补齐当前 evidence。"
        )
    else:
        next_step = (
            "下一步若通过，只允许设计独立的 Agent continuation 资格：从同源 checkpoint "
            "重复运行固定 Agent continuation，先估计方差、成本和可恢复性，再决定是否实现 "
            "controller。"
        )
    lines = [
        "# 动态预算多步轨迹 benchmark 资格结果",
        "",
        f"**决定：`{report['decision']}`。**",
        "",
        f"状态：`{report['status']}`。本 identity 有 {summary['states_attempted']} 个状态记录了 continuation，共记录 {summary['continuations_recorded']} 个禁网 Docker continuation；完整项目和状态分别为 {summary['projects_completed']}、{summary['states_completed']}。",
        "",
        "## 核心结果",
        "",
        f"- 已记录成功 continuation：`{summary['successful_recorded_continuations']}/{summary['continuations_recorded']}`；",
        f"- 重复一致的完整状态：`{summary['consistent_states']}/{summary['states_completed']}`；",
        f"- 完整状态 checkpoint 绑定：`{summary['checkpoint_bindings']}/{summary['states_completed']}`；",
        f"- 完整状态预算守恒：`{summary['budget_conserved_states']}/{summary['states_completed']}`；",
        f"- stop reservation 转移：`{summary['stop_transfers']}/3`；",
        f"- Provider requests：`{summary['provider_requests']}`；Agent calls：`{summary['agent_calls']}`；",
        f"- 已记录 continuation 累计动作 wall clock：`{summary['recorded_continuation_wall_clock_milliseconds']} ms`。",
        "",
        "## 资格门槛",
        "",
        "| 门槛 | 通过 |",
        "| --- | --- |",
    ]
    lines.extend(
        f"| `{name}` | {'是' if passed else '否'} |" for name, passed in gates.items()
    )
    if report.get("failure"):
        lines.extend(
            [
                "",
                "## 停止原因",
                "",
                f"- 分类：`{report.get('failure_classification') or 'qualification_failure'}`；",
                f"- 类型：`{report['failure'].get('type')}`；",
                f"- 观察：{report['failure'].get('message')}。",
            ]
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "本结果只评价轨迹 benchmark 的恢复、重复性、计量与共享预算语义。它不评价动态预算 controller、Jev 或 Agent 的效果，也不支持自然失败或开放世界外推。",
            "",
            next_step,
            "",
            "## Evidence",
            "",
            f"- Manifest SHA-256：`{report['manifest_sha256']}`；",
            f"- Manifest canonical SHA-256：`{report['manifest_canonical_sha256']}`；",
            f"- Evidence inventory canonical SHA-256：`{report['evidence_inventory_canonical_sha256']}`；",
            f"- Evidence files：`{report['audit']['inventory_file_count']}`，`{report['audit']['inventory_total_bytes']}` bytes。",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    report = _report_payload(manifest, root)
    _write_json_atomic(REPORT_JSON_PATH, report)
    REPORT_MD_PATH.write_text(_render_markdown(report), encoding="utf-8")
    return report


def _plan(manifest: dict[str, Any]) -> dict[str, Any]:
    validate_manifest(manifest)
    return {
        "identity": IDENTITY,
        "issue": manifest["issue"],
        "systems": list(SYSTEMS),
        "projects": len(manifest["projects"]),
        "states": len(manifest["projects"]) * manifest["states_per_project"],
        "continuations": len(manifest["projects"])
        * manifest["states_per_project"]
        * manifest["repetitions_per_state"],
        "credential_read": False,
        "provider_requests": 0,
        "agent_continuation": False,
        "controller_implementation": False,
        "evidence_root": manifest["evidence_root"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=("validate", "plan", "preflight", "run", "audit", "report")
    )
    args = parser.parse_args()
    manifest = validate_manifest(_load_json(MANIFEST_PATH))
    if args.command == "validate":
        output = {
            "valid": True,
            "manifest_sha256": _sha256_file(MANIFEST_PATH),
            "manifest_canonical_sha256": _canonical_sha256(manifest),
        }
    elif args.command == "plan":
        output = _plan(manifest)
    elif args.command == "preflight":
        output = preflight(manifest, require_absent=True)
    elif args.command == "run":
        output = execute(manifest)
    else:
        root = REPO_ROOT / manifest["evidence_root"]
        output = (
            audit_evidence(manifest, root)
            if args.command == "audit"
            else write_report(manifest, root)
        )
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
