#!/usr/bin/env python3
"""检查 release-bound identity；Provider 与正式采集等待独立执行授权。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_contract_driven_repair_mechanism_v1_authorized_protocol as protocol  # noqa: E402

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
READ_ONLY_COMMANDS = ("validate", "plan", "preflight")
BLOCKED_COMMANDS = ("availability", "batch")
MANAGED_CONTAINER_PREFIXES = (
    "deerflow-compile-",
    "deerflow-replay-",
    "forge-stage-c-arm-a-",
    "forge-stage-c-qualification-",
    "forge-runtime-v3-q-",
)


class AuthorizedRunnerError(RuntimeError):
    """release、Docker、evidence 或执行授权边界无效。"""


def _run_checked(argv: list[str], *, cwd: Path) -> str:
    result = subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise AuthorizedRunnerError(
            f"非模型 preflight 命令失败: {' '.join(argv)}: {detail}"
        )
    return result.stdout.strip()


def validate_runtime(
    manifest: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    runtime = manifest["authorized_runtime"]
    if runtime["commands_allowed_without_execution_authorization"] != list(
        READ_ONLY_COMMANDS
    ) or runtime["commands_fail_closed_without_separate_authorization"] != list(
        BLOCKED_COMMANDS
    ):
        raise AuthorizedRunnerError("authorized runner 命令边界发生漂移")
    return {
        "status": "release_bound_identity_not_execution_authorized",
        "manifest_sha256": protocol.candidate.canonical_sha256(manifest),
        "scientific_contract_release_revision": protocol.SCIENTIFIC_CONTRACT_RELEASE_REVISION,
        "availability_execution_authorized": False,
        "formal_collection_execution_authorized": False,
        "provider_calls": 0,
        "credential_reads": 0,
        "docker_sessions_created": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
        "model_tokens": 0,
    }


def _require_release(repo_root: Path) -> str:
    revision = _run_checked(["git", "rev-parse", "HEAD"], cwd=repo_root)
    _run_checked(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            protocol.SCIENTIFIC_CONTRACT_RELEASE_REVISION,
            revision,
        ],
        cwd=repo_root,
    )
    dirty = _run_checked(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo_root
    )
    if dirty:
        raise AuthorizedRunnerError("非模型 preflight 要求干净工作树")
    return revision


def _require_docker_identity(manifest: dict[str, Any], repo_root: Path) -> str:
    _run_checked(
        ["bash", str(repo_root / "scripts/require-docker-runtime.sh")], cwd=repo_root
    )
    environment = manifest["environment_identity"]
    image_id = _run_checked(
        [
            "docker",
            "image",
            "inspect",
            environment["compile_image"],
            "--format",
            "{{.Id}}",
        ],
        cwd=repo_root,
    )
    if image_id != environment["image_id"]:
        raise AuthorizedRunnerError("编译镜像 ID 与 release-bound identity 不一致")
    return image_id


def _require_zero_managed_resources(repo_root: Path) -> None:
    names = _run_checked(
        ["docker", "ps", "-a", "--format", "{{.Names}}"], cwd=repo_root
    ).splitlines()
    managed_names = sorted(
        name for name in names if name.startswith(MANAGED_CONTAINER_PREFIXES)
    )
    labelled = _run_checked(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            "label=deerflow.compile.managed=true",
        ],
        cwd=repo_root,
    )
    paused = _run_checked(
        [
            "docker",
            "ps",
            "-q",
            "--filter",
            "status=paused",
            "--filter",
            "label=deerflow.compile.managed=true",
        ],
        cwd=repo_root,
    )
    compile_images = _run_checked(
        [
            "docker",
            "images",
            "-q",
            "--filter",
            "label=deerflow.compile.managed=true",
        ],
        cwd=repo_root,
    )
    stage_c_images = _run_checked(
        [
            "docker",
            "images",
            "-q",
            "--filter",
            "label=forge.stage-c.managed=true",
        ],
        cwd=repo_root,
    )
    if managed_names or labelled or paused or compile_images or stage_c_images:
        raise AuthorizedRunnerError(
            "存在受管 container、paused parent 或 snapshot image"
        )


def _require_evidence_absent(manifest: dict[str, Any], workspace_root: Path) -> Path:
    workspace = workspace_root.resolve(strict=True)
    if workspace_root.is_symlink() or workspace != workspace_root.absolute():
        raise AuthorizedRunnerError("workspace root 不得经过符号链接")
    compile_sessions = workspace / ".compile-sessions"
    if compile_sessions.is_symlink() or not compile_sessions.is_dir():
        raise AuthorizedRunnerError("Compile Session root 不存在或为符号链接")
    evidence = workspace / manifest["candidate_evidence"]["directory"]
    if evidence.exists() or evidence.is_symlink():
        raise AuthorizedRunnerError("create-once evidence directory 必须尚不存在")
    if evidence.parent != compile_sessions:
        raise AuthorizedRunnerError("evidence directory 未绑定到 Compile Session root")
    return evidence


def collect_preflight(
    manifest: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    validate_runtime(manifest, repo_root)
    revision = _require_release(repo_root)
    image_id = _require_docker_identity(manifest, repo_root)
    _require_zero_managed_resources(repo_root)
    evidence = _require_evidence_absent(manifest, workspace_root or repo_root)
    return {
        "ready": True,
        "status": "non_model_preflight_passed_execution_not_authorized",
        "manifest_sha256": protocol.candidate.canonical_sha256(manifest),
        "scientific_contract_release_revision": protocol.SCIENTIFIC_CONTRACT_RELEASE_REVISION,
        "observed_clean_descendant_revision": revision,
        "compile_image_id": image_id,
        "evidence_directory": str(evidence),
        "zero_managed_resources": True,
        "evidence_directory_absent": True,
        "provider_calls": 0,
        "credential_reads": 0,
        "docker_sessions_created": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
        "model_tokens": 0,
    }


def _reject_execution(command: str) -> None:
    if command not in BLOCKED_COMMANDS:
        raise AuthorizedRunnerError(f"未知执行命令: {command}")
    raise AuthorizedRunnerError(
        f"{command} 尚未获得独立执行授权；禁止读取 credential、调用 Provider 或创建 evidence"
    )


def execute_availability() -> None:
    _reject_execution("availability")


def run_batch() -> None:
    _reject_execution("batch")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=READ_ONLY_COMMANDS + BLOCKED_COMMANDS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    if args.command in BLOCKED_COMMANDS:
        _reject_execution(args.command)
    manifest = protocol.load_manifest(args.manifest)
    if args.command == "validate":
        result: Any = validate_runtime(manifest)
    elif args.command == "plan":
        result = protocol.plan_summary(manifest)
    else:
        result = collect_preflight(manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
