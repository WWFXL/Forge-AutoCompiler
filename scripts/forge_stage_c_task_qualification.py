#!/usr/bin/env python3
"""Stage C 任务、oracle 与固定镜像的零 Provider 资格门禁。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shlex
import subprocess
import tempfile
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import jsonschema

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
DEFAULT_PLAN = REPO_ROOT / "benchmarks/manifests/cpp-stage-c-task-qualification.json"
DEFAULT_POOL = REPO_ROOT / "benchmarks/fixtures/stage-c-source-pool.json"
DEFAULT_SCHEMA = (
    REPO_ROOT / "benchmarks/schemas/forge-stage-c-task-qualification.schema.json"
)
DEFAULT_RESULT = (
    REPO_ROOT / "benchmarks/fixtures/stage-c-task-qualification-result.json"
)
MANAGED_PREFIX = "forge-stage-c-qualification-"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class StageCTaskQualificationError(RuntimeError):
    """Stage C 资格合同、源码、镜像或 reference build 无效。"""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageCTaskQualificationError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise StageCTaskQualificationError(f"JSON 根节点必须是对象: {path}")
    return value


def write_once(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def selection_key(seed: str, repository_url: str, commit_sha: str) -> str:
    payload = "\0".join((seed, repository_url, commit_sha)).encode()
    return hashlib.sha256(payload).hexdigest()


def _safe_relative(value: str, label: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise StageCTaskQualificationError(f"{label} 必须是安全相对路径")
    return path.as_posix()


def validate_source_pool(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("schema_version") != "forge-stage-c-source-pool-1.0.0":
        raise StageCTaskQualificationError("source pool schema_version 无效")
    if value.get("document_type") != "forge_stage_c_source_pool":
        raise StageCTaskQualificationError("source pool document_type 无效")
    seed = value.get("selection_seed")
    tasks = value.get("tasks")
    if (
        not isinstance(seed, str)
        or not seed
        or not isinstance(tasks, list)
        or len(tasks) != 12
    ):
        raise StageCTaskQualificationError("source pool 必须冻结 seed 和 12 个 task")
    ids: set[str] = set()
    urls: set[str] = set()
    for task in tasks:
        task_id = task.get("task_id")
        url = task.get("repository_url")
        commit = task.get("commit_sha")
        if not isinstance(task_id, str) or not task_id or task_id in ids:
            raise StageCTaskQualificationError("source pool task_id 缺失或重复")
        if (
            not isinstance(url, str)
            or not url.startswith("https://")
            or "@" in url
            or url in urls
        ):
            raise StageCTaskQualificationError(f"{task_id} repository_url 无效或重复")
        if not isinstance(commit, str) or HEX40.fullmatch(commit) is None:
            raise StageCTaskQualificationError(f"{task_id} commit_sha 无效")
        if HEX64.fullmatch(str(task.get("source_snapshot_sha256", ""))) is None:
            raise StageCTaskQualificationError(f"{task_id} source snapshot 无效")
        if HEX64.fullmatch(str(task.get("license_sha256", ""))) is None:
            raise StageCTaskQualificationError(f"{task_id} license identity 无效")
        _safe_relative(str(task.get("license_path", "")), f"{task_id}.license_path")
        ids.add(task_id)
        urls.add(url)
    excluded = set(value["exclusions"]["stage_b_task_ids"])
    if (
        ids & excluded
        or value["exclusions"]["historical_a_or_b_model_results_observed"] is not False
    ):
        raise StageCTaskQualificationError(
            "Stage C task 与 Stage B 或历史 A/B 暴露集合重叠"
        )
    for dimension in ("build_system", "size"):
        expected = value["quotas"][dimension]
        field = f"{dimension}_stratum"
        observed = Counter(task[field] for task in tasks)
        if observed != Counter(expected):
            raise StageCTaskQualificationError(
                f"{dimension} 分层不满足冻结配额: {dict(observed)}"
            )
    return value


def generate_schema(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-stage-c-task-qualification.schema.json",
        "title": "Forge Stage C task qualification",
        "const": plan,
    }


def validate_plan(
    plan: dict[str, Any],
    *,
    pool: dict[str, Any] | None = None,
    check_schema_file: bool = True,
) -> dict[str, Any]:
    if plan.get("schema_version") != "forge-stage-c-task-qualification-1.0.0":
        raise StageCTaskQualificationError("qualification schema_version 无效")
    if plan.get("status") != "planned_not_executed":
        raise StageCTaskQualificationError("qualification plan 必须保持未执行状态")
    authorization = plan.get("authorization")
    if not isinstance(authorization, dict):
        raise StageCTaskQualificationError("qualification authorization 缺失")
    forbidden = (
        "provider_calls_authorized",
        "credential_read_authorized",
        "model_creation_authorized",
        "formal_stage_c_attempts_authorized",
        "formal_stage_c_evidence_write_authorized",
    )
    if any(authorization.get(name) is not False for name in forbidden):
        raise StageCTaskQualificationError("qualification 意外授权了正式 Stage C 能力")
    if authorization.get("reference_builds_authorized") is not True:
        raise StageCTaskQualificationError("reference build 未授权")
    if authorization.get("model_tokens_authorized") != 0:
        raise StageCTaskQualificationError("qualification 必须为 0 model token")
    pool = validate_source_pool(pool or load_json(DEFAULT_POOL))
    pool_tasks = {task["task_id"]: task for task in pool["tasks"]}
    tasks = plan.get("tasks")
    if not isinstance(tasks, list) or [task.get("task_id") for task in tasks] != list(
        pool_tasks
    ):
        raise StageCTaskQualificationError(
            "qualification task 顺序必须与 source pool 一致"
        )
    for task in tasks:
        task_id = task["task_id"]
        target = task.get("target")
        recipe = task.get("reference_recipe")
        oracle = task.get("oracle")
        if not isinstance(target, dict) or not isinstance(recipe, list) or not recipe:
            raise StageCTaskQualificationError(
                f"{task_id} target 或 reference recipe 缺失"
            )
        required = target.get("required_artifacts")
        types = target.get("artifact_types")
        if (
            not isinstance(required, list)
            or not required
            or len(required) != len(types or [])
        ):
            raise StageCTaskQualificationError(f"{task_id} required artifacts 合同无效")
        for relative in required:
            _safe_relative(relative, f"{task_id}.required_artifacts")
        if any(not isinstance(command, str) or not command for command in recipe):
            raise StageCTaskQualificationError(f"{task_id} reference recipe 无效")
        forbidden_tokens = (
            "apt-get",
            "apt ",
            "curl ",
            "wget ",
            "git clone",
            "git fetch",
        )
        if any(token in command for command in recipe for token in forbidden_tokens):
            raise StageCTaskQualificationError(
                f"{task_id} reference build 包含未固定网络动作"
            )
        if not isinstance(oracle, dict) or oracle.get("kind") not in {
            "compile_and_run",
            "command",
        }:
            raise StageCTaskQualificationError(f"{task_id} oracle 无效")
    schema = generate_schema(plan)
    jsonschema.Draft202012Validator.check_schema(schema)
    if check_schema_file:
        if not DEFAULT_SCHEMA.is_file() or load_json(DEFAULT_SCHEMA) != schema:
            raise StageCTaskQualificationError("qualification const Schema 缺失或漂移")
        jsonschema.validate(plan, load_json(DEFAULT_SCHEMA))
    return plan


def load_plan(path: Path = DEFAULT_PLAN) -> dict[str, Any]:
    return validate_plan(load_json(path))


def _run_checked(
    argv: list[str],
    *,
    cwd: Path = REPO_ROOT,
    timeout: int = 120,
    input_text: str | None = None,
) -> str:
    result = subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        input=input_text,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-4000:]
        raise StageCTaskQualificationError(
            f"命令失败 ({result.returncode}): {shlex.join(argv)}\n{detail}"
        )
    return result.stdout.strip()


def require_zero_managed_resources() -> None:
    output = _run_checked(["docker", "ps", "-a", "--format", "{{.Names}}"])
    names = sorted(
        name for name in output.splitlines() if name.startswith(MANAGED_PREFIX)
    )
    if names:
        raise StageCTaskQualificationError(
            f"存在 Stage C qualification orphan: {','.join(names)}"
        )


def image_id(plan: dict[str, Any]) -> str:
    tag = plan["environment"]["image_tag"]
    value = _run_checked(["docker", "image", "inspect", tag, "--format", "{{.Id}}"])
    if not value.startswith("sha256:"):
        raise StageCTaskQualificationError("Stage C image ID 无效")
    return value


def build_image(plan: dict[str, Any]) -> dict[str, Any]:
    require_zero_managed_resources()
    environment = plan["environment"]
    dockerfile = REPO_ROOT / environment["dockerfile_path"]
    _run_checked(
        [
            "docker",
            "build",
            "--pull=false",
            "--tag",
            environment["image_tag"],
            "--file",
            str(dockerfile),
            str(REPO_ROOT),
        ],
        timeout=3600,
    )
    result = {
        "image_tag": environment["image_tag"],
        "image_id": image_id(plan),
        "dockerfile_sha256": file_sha256(dockerfile),
        "ubuntu_snapshot": environment["ubuntu_snapshot"],
        "provider_calls": 0,
        "model_tokens": 0,
        "formal_stage_c_attempts": 0,
    }
    require_zero_managed_resources()
    return result


def preflight(plan: dict[str, Any]) -> dict[str, Any]:
    require_zero_managed_resources()
    dockerfile = REPO_ROOT / plan["environment"]["dockerfile_path"]
    if not dockerfile.is_file():
        raise StageCTaskQualificationError("Stage C Dockerfile 不存在")
    current_image_id: str | None
    try:
        current_image_id = image_id(plan)
    except StageCTaskQualificationError:
        current_image_id = None
    return {
        "ready_for_image_build": True,
        "ready_for_reference_qualification": current_image_id is not None,
        "image_id": current_image_id,
        "dockerfile_sha256": file_sha256(dockerfile),
        "source_pool_canonical_sha256": canonical_sha256(load_json(DEFAULT_POOL)),
        "plan_canonical_sha256": canonical_sha256(plan),
        "task_count": len(plan["tasks"]),
        "provider_calls": 0,
        "model_tokens": 0,
        "formal_stage_c_attempts": 0,
        "zero_managed_resources": True,
    }


def _clone_exact(task: dict[str, Any], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    _run_checked(["git", "init", "--quiet", str(destination)])
    _run_checked(
        [
            "git",
            "-C",
            str(destination),
            "remote",
            "add",
            "origin",
            task["repository_url"],
        ]
    )
    _run_checked(
        [
            "git",
            "-C",
            str(destination),
            "fetch",
            "--quiet",
            "--depth",
            "1",
            "origin",
            task["commit_sha"],
        ],
        timeout=600,
    )
    _run_checked(
        ["git", "-C", str(destination), "checkout", "--quiet", "--detach", "FETCH_HEAD"]
    )
    if (
        _run_checked(["git", "-C", str(destination), "rev-parse", "HEAD"])
        != task["commit_sha"]
    ):
        raise StageCTaskQualificationError(f"{task['task_id']} exact commit 漂移")


def _archive_sha256(source: Path) -> str:
    process = subprocess.Popen(
        ["git", "-C", str(source), "archive", "--format=tar", "HEAD"],
        stdout=subprocess.PIPE,
    )
    digest = hashlib.sha256()
    assert process.stdout is not None
    for chunk in iter(lambda: process.stdout.read(1024 * 1024), b""):
        digest.update(chunk)
    if process.wait(timeout=120) != 0:
        raise StageCTaskQualificationError("git archive 失败")
    return digest.hexdigest()


def _verify_source(task: dict[str, Any], source: Path) -> dict[str, Any]:
    observed_archive = _archive_sha256(source)
    if observed_archive != task["source_snapshot_sha256"]:
        raise StageCTaskQualificationError(f"{task['task_id']} source snapshot 漂移")
    license_path = source / task["license_path"]
    if (
        not license_path.is_file()
        or file_sha256(license_path) != task["license_sha256"]
    ):
        raise StageCTaskQualificationError(f"{task['task_id']} license identity 漂移")
    output = _run_checked(["git", "-C", str(source), "ls-tree", "-r", "HEAD"])
    observed_submodules = {
        fields[3]: fields[2]
        for line in output.splitlines()
        if (fields := line.split(maxsplit=3))[0] == "160000"
    }
    if observed_submodules != task["submodule_commits"]:
        raise StageCTaskQualificationError(f"{task['task_id']} submodule identity 漂移")
    return {
        "commit_sha": task["commit_sha"],
        "source_snapshot_sha256": observed_archive,
        "license_sha256": file_sha256(license_path),
        "submodule_commits": observed_submodules,
    }


def _oracle_script(task: dict[str, Any], suffix: str) -> str:
    oracle = task["oracle"]
    if oracle["kind"] == "command":
        return shlex.join(oracle["argv"])
    extension = ".c" if oracle["language"] == "c11" else ".cc"
    source = f"/tmp/forge-stage-c-oracle-{suffix}{extension}"
    executable = f"/tmp/forge-stage-c-oracle-{suffix}"
    encoded = base64.b64encode(oracle["source"].encode()).decode()
    compile_argv = [
        source if item == "{source}" else executable if item == "{executable}" else item
        for item in oracle["compile_argv"]
    ]
    run_argv = [
        executable if item == "{executable}" else item for item in oracle["run_argv"]
    ]
    return (
        f"printf %s {shlex.quote(encoded)} | base64 -d > {shlex.quote(source)} && "
        f"{shlex.join(compile_argv)} && {shlex.join(run_argv)}"
    )


def _artifact_evidence(task: dict[str, Any], artifacts: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    required = task["target"]["required_artifacts"]
    types = task["target"]["artifact_types"]
    for relative, expected_type in zip(required, types, strict=True):
        path = artifacts / relative
        if not path.is_file() or path.is_symlink() or path.stat().st_size <= 0:
            raise StageCTaskQualificationError(
                f"{task['task_id']} 缺少有效 required artifact: {relative}"
            )
        file_type = _run_checked(["file", "-b", str(path)])
        if expected_type == "static_library":
            members = _run_checked(["ar", "t", str(path)])
            if not members:
                raise StageCTaskQualificationError(
                    f"{task['task_id']} 空静态库: {relative}"
                )
        elif expected_type == "executable" and "executable" not in file_type.lower():
            raise StageCTaskQualificationError(
                f"{task['task_id']} 非 executable: {relative}"
            )
        result.append(
            {
                "path": relative,
                "type": expected_type,
                "size_bytes": path.stat().st_size,
                "sha256": file_sha256(path),
                "file_type": file_type,
            }
        )
    return result


def _run_reference_once(
    plan: dict[str, Any],
    source_task: dict[str, Any],
    qualification_task: dict[str, Any],
    root: Path,
    replicate: int,
    frozen_image_id: str,
) -> dict[str, Any]:
    source = root / "source"
    artifacts = root / "artifacts"
    _clone_exact(source_task, source)
    source_identity = _verify_source(source_task, source)
    artifacts.mkdir(parents=True)
    name = (
        f"{MANAGED_PREFIX}{qualification_task['task_id'][:24]}-{uuid.uuid4().hex[:8]}"
    )
    script = "set -euo pipefail\n" + "\n".join(qualification_task["reference_recipe"])
    started = time.perf_counter()
    try:
        _run_checked(
            [
                "docker",
                "run",
                "--name",
                name,
                "--label",
                "forge.stage-c.qualification=true",
                "--network",
                "none",
                "--cpus",
                str(plan["environment"]["parallel_jobs"]),
                "--volume",
                f"{source.resolve()}:/workspace/repo",
                "--volume",
                f"{artifacts.resolve()}:/artifacts",
                "--workdir",
                "/workspace/repo",
                frozen_image_id,
                "bash",
                "-lc",
                script,
            ],
            timeout=plan["environment"]["per_task_timeout_seconds"],
        )
    finally:
        subprocess.run(
            ["docker", "rm", "-f", name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    evidence = _artifact_evidence(qualification_task, artifacts)
    oracle_name = f"{MANAGED_PREFIX}oracle-{uuid.uuid4().hex[:8]}"
    try:
        _run_checked(
            [
                "docker",
                "run",
                "--name",
                oracle_name,
                "--label",
                "forge.stage-c.qualification=true",
                "--network",
                "none",
                "--volume",
                f"{source.resolve()}:/workspace/repo",
                "--volume",
                f"{artifacts.resolve()}:/artifacts:ro",
                "--workdir",
                qualification_task["oracle"].get("workdir", "/workspace/repo"),
                frozen_image_id,
                "bash",
                "-lc",
                "set -euo pipefail\n"
                + _oracle_script(
                    qualification_task, f"{qualification_task['task_id']}-{replicate}"
                ),
            ],
            timeout=300,
        )
    finally:
        subprocess.run(
            ["docker", "rm", "-f", oracle_name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return {
        "replicate": replicate,
        "source_identity": source_identity,
        "artifacts": evidence,
        "oracle_passed": True,
        "duration_seconds": round(time.perf_counter() - started, 3),
    }


def run_qualification(
    plan: dict[str, Any],
    *,
    output: Path = DEFAULT_RESULT,
    work_root: Path | None = None,
) -> dict[str, Any]:
    if output.exists():
        raise StageCTaskQualificationError("qualification result 已存在，禁止覆盖")
    require_zero_managed_resources()
    frozen_image_id = image_id(plan)
    pool = validate_source_pool(load_json(DEFAULT_POOL))
    pool_by_id = {task["task_id"]: task for task in pool["tasks"]}
    task_results: list[dict[str, Any]] = []
    owner = (
        tempfile.TemporaryDirectory(prefix="forge-stage-c-qualification-")
        if work_root is None
        else None
    )
    root = Path(owner.name) if owner is not None else work_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    try:
        for task in plan["tasks"]:
            task_root = root / task["task_id"]
            first = _run_reference_once(
                plan,
                pool_by_id[task["task_id"]],
                task,
                task_root / "replicate-1",
                1,
                frozen_image_id,
            )
            second = _run_reference_once(
                plan,
                pool_by_id[task["task_id"]],
                task,
                task_root / "replicate-2",
                2,
                frozen_image_id,
            )
            first_hashes = [item["sha256"] for item in first["artifacts"]]
            second_hashes = [item["sha256"] for item in second["artifacts"]]
            bitwise = first_hashes == second_hashes
            if task["target"]["bitwise_required"] and not bitwise:
                raise StageCTaskQualificationError(
                    f"{task['task_id']} 不满足冻结的 bitwise 条件"
                )
            task_results.append(
                {
                    "task_id": task["task_id"],
                    "passed": True,
                    "bitwise_reproducible": bitwise,
                    "replicates": [first, second],
                }
            )
            require_zero_managed_resources()
    finally:
        if owner is not None:
            owner.cleanup()
    result = {
        "schema_version": "forge-stage-c-task-qualification-result-1.0.0",
        "document_type": "forge_stage_c_task_qualification_result",
        "status": "passed",
        "completed_at": datetime.now(UTC).isoformat(),
        "plan_canonical_sha256": canonical_sha256(plan),
        "source_pool_canonical_sha256": canonical_sha256(pool),
        "dockerfile_sha256": file_sha256(
            REPO_ROOT / plan["environment"]["dockerfile_path"]
        ),
        "image_id": frozen_image_id,
        "ubuntu_snapshot": plan["environment"]["ubuntu_snapshot"],
        "task_count": len(task_results),
        "reference_build_count": len(task_results) * 2,
        "provider_request_count": 0,
        "model_created": False,
        "model_tokens": 0,
        "formal_stage_c_attempt_created": False,
        "formal_stage_c_evidence_written": False,
        "zero_managed_resources_before": True,
        "zero_managed_resources_after": True,
        "tasks": task_results,
    }
    validate_result(result, plan, pool)
    write_once(output, result)
    return result


def validate_result(
    result: dict[str, Any],
    plan: dict[str, Any],
    pool: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pool = validate_source_pool(pool or load_json(DEFAULT_POOL))
    if result.get("schema_version") != "forge-stage-c-task-qualification-result-1.0.0":
        raise StageCTaskQualificationError("qualification result schema_version 无效")
    if result.get("status") != "passed":
        raise StageCTaskQualificationError("qualification result 未通过")
    expected = {
        "plan_canonical_sha256": canonical_sha256(plan),
        "source_pool_canonical_sha256": canonical_sha256(pool),
        "dockerfile_sha256": file_sha256(
            REPO_ROOT / plan["environment"]["dockerfile_path"]
        ),
        "ubuntu_snapshot": plan["environment"]["ubuntu_snapshot"],
        "task_count": 12,
        "reference_build_count": 24,
        "provider_request_count": 0,
        "model_created": False,
        "model_tokens": 0,
        "formal_stage_c_attempt_created": False,
        "formal_stage_c_evidence_written": False,
        "zero_managed_resources_before": True,
        "zero_managed_resources_after": True,
    }
    for key, value in expected.items():
        if result.get(key) != value:
            raise StageCTaskQualificationError(f"qualification result {key} 漂移")
    if (
        not isinstance(result.get("image_id"), str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", result["image_id"]) is None
    ):
        raise StageCTaskQualificationError("qualification result image_id 无效")
    task_results = result.get("tasks")
    if not isinstance(task_results, list) or [
        item.get("task_id") for item in task_results
    ] != [task["task_id"] for task in plan["tasks"]]:
        raise StageCTaskQualificationError("qualification result task 顺序漂移")
    pool_by_id = {task["task_id"]: task for task in pool["tasks"]}
    for task, receipt in zip(plan["tasks"], task_results, strict=True):
        if receipt.get("passed") is not True or len(receipt.get("replicates", [])) != 2:
            raise StageCTaskQualificationError(
                f"{task['task_id']} qualification receipt 未闭合"
            )
        expected_source = pool_by_id[task["task_id"]]
        expected_paths = task["target"]["required_artifacts"]
        expected_types = task["target"]["artifact_types"]
        replicate_hashes: list[list[str]] = []
        for expected_replicate, replicate in enumerate(receipt["replicates"], start=1):
            if replicate.get("replicate") != expected_replicate:
                raise StageCTaskQualificationError(
                    f"{task['task_id']} replicate 顺序无效"
                )
            source_identity = replicate.get("source_identity")
            if not isinstance(source_identity, dict) or source_identity != {
                "commit_sha": expected_source["commit_sha"],
                "source_snapshot_sha256": expected_source["source_snapshot_sha256"],
                "license_sha256": expected_source["license_sha256"],
                "submodule_commits": expected_source["submodule_commits"],
            }:
                raise StageCTaskQualificationError(
                    f"{task['task_id']} source identity receipt 漂移"
                )
            artifacts = replicate.get("artifacts")
            if not isinstance(artifacts, list) or len(artifacts) != len(expected_paths):
                raise StageCTaskQualificationError(
                    f"{task['task_id']} artifact receipt 不完整"
                )
            hashes: list[str] = []
            for artifact, expected_path, expected_type in zip(
                artifacts, expected_paths, expected_types, strict=True
            ):
                if (
                    not isinstance(artifact, dict)
                    or artifact.get("path") != expected_path
                    or artifact.get("type") != expected_type
                    or type(artifact.get("size_bytes")) is not int
                    or artifact["size_bytes"] <= 0
                    or HEX64.fullmatch(str(artifact.get("sha256", ""))) is None
                    or not isinstance(artifact.get("file_type"), str)
                    or not artifact["file_type"]
                ):
                    raise StageCTaskQualificationError(
                        f"{task['task_id']} artifact receipt 漂移: {expected_path}"
                    )
                hashes.append(artifact["sha256"])
            if replicate.get("oracle_passed") is not True or not isinstance(
                replicate.get("duration_seconds"), (int, float)
            ):
                raise StageCTaskQualificationError(
                    f"{task['task_id']} oracle receipt 未闭合"
                )
            if (
                isinstance(replicate["duration_seconds"], bool)
                or replicate["duration_seconds"] < 0
            ):
                raise StageCTaskQualificationError(
                    f"{task['task_id']} duration receipt 无效"
                )
            replicate_hashes.append(hashes)
        observed_bitwise = replicate_hashes[0] == replicate_hashes[1]
        if receipt.get("bitwise_reproducible") is not observed_bitwise:
            raise StageCTaskQualificationError(
                f"{task['task_id']} bitwise receipt 与 artifact evidence 不一致"
            )
        if task["target"]["bitwise_required"] and not observed_bitwise:
            raise StageCTaskQualificationError(
                f"{task['task_id']} bitwise receipt 未通过"
            )
    return result


def write_schema(plan: dict[str, Any], path: Path = DEFAULT_SCHEMA) -> None:
    schema = generate_schema(plan)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "generate-schema",
            "validate",
            "preflight",
            "build-image",
            "run",
            "verify-result",
        ),
    )
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--result", type=Path, default=DEFAULT_RESULT)
    parser.add_argument("--work-root", type=Path)
    args = parser.parse_args(argv)
    raw_plan = load_json(args.plan)
    if args.command == "generate-schema":
        validate_plan(raw_plan, check_schema_file=False)
        write_schema(raw_plan)
        result: Any = {"schema_path": str(DEFAULT_SCHEMA), "status": "generated"}
    else:
        plan = validate_plan(raw_plan)
        if args.command == "validate":
            pool = validate_source_pool(load_json(DEFAULT_POOL))
            result = {
                "status": "valid",
                "task_count": len(plan["tasks"]),
                "selection_order": [
                    item["task_id"]
                    for item in sorted(
                        pool["tasks"],
                        key=lambda item: selection_key(
                            pool["selection_seed"],
                            item["repository_url"],
                            item["commit_sha"],
                        ),
                    )
                ],
                "provider_calls": 0,
                "model_tokens": 0,
                "formal_stage_c_attempts": 0,
            }
        elif args.command == "preflight":
            result = preflight(plan)
        elif args.command == "build-image":
            result = build_image(plan)
        elif args.command == "run":
            result = run_qualification(
                plan, output=args.result, work_root=args.work_root
            )
        else:
            result = validate_result(load_json(args.result), plan)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
