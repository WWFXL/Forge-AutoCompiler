#!/usr/bin/env python3
"""验证 mechanism v2 独立身份；真实执行等待单独授权。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_contract_driven_repair_mechanism_v1_formal_runner as base  # noqa: E402
import forge_contract_driven_repair_mechanism_v1_formal_failure_audit as failure_audit  # noqa: E402

_FROZEN_MARKER_UPDATE = base._update_claimed_marker

import forge_contract_driven_repair_mechanism_v1_formal_marker_repair as marker_repair  # noqa: E402
import forge_contract_driven_repair_mechanism_v2_candidate_protocol as protocol  # noqa: E402

# Repair 模块为兼容旧入口会在 import 时安装；candidate 只允许显式局部绑定。
base._update_claimed_marker = _FROZEN_MARKER_UPDATE

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_OUTPUT_DIR = REPO_ROOT / protocol.EVIDENCE_DIRECTORY
READ_ONLY_COMMANDS = ("validate", "plan", "qualify", "preflight")
BLOCKED_COMMANDS = ("availability", "batch", "report", "audit")

_ORIGINAL_PROTOCOL = base.protocol
_REPAIRED_MARKER_UPDATE = marker_repair.update_claimed_marker
_RUNTIME_BINDING_LOCK = threading.Lock()


class IndependentCandidateRunnerError(RuntimeError):
    """独立 identity release、repair、evidence 或权限边界无效。"""


def _run_checked(argv: list[str], *, cwd: Path) -> str:
    result = subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-3000:]
        raise IndependentCandidateRunnerError(
            f"非模型 preflight 命令失败: {' '.join(argv)}: {detail}"
        )
    return result.stdout.strip()


@contextmanager
def _runtime_binding() -> Iterator[None]:
    """为独立 identity 临时绑定新 protocol 与已审阅 marker repair。"""

    if not _RUNTIME_BINDING_LOCK.acquire(blocking=False):
        raise IndependentCandidateRunnerError(
            "新 identity runtime binding 只允许串行进入"
        )
    observed_protocol = base.protocol
    observed_update = base._update_claimed_marker
    try:
        if observed_protocol is not _ORIGINAL_PROTOCOL:
            raise IndependentCandidateRunnerError(
                "冻结 runner protocol binding 已被修改"
            )
        base.protocol = protocol
        base._update_claimed_marker = _REPAIRED_MARKER_UPDATE
        yield
    finally:
        base.protocol = observed_protocol
        base._update_claimed_marker = observed_update
        _RUNTIME_BINDING_LOCK.release()


def validate_runtime(
    manifest: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    marker_repair._verify_frozen_runner()
    if marker_repair._frozen_update_claimed_marker is not _FROZEN_MARKER_UPDATE:
        raise IndependentCandidateRunnerError("marker repair 未绑定 frozen helper")
    runtime = manifest["independent_runtime"]
    if runtime["commands_allowed_without_execution_authorization"] != list(
        READ_ONLY_COMMANDS
    ) or runtime["commands_fail_closed_without_separate_authorization"] != list(
        BLOCKED_COMMANDS
    ):
        raise IndependentCandidateRunnerError("新 identity runner 命令边界漂移")
    if manifest["formal_execution"].get("execution_authorized") is not False:
        raise IndependentCandidateRunnerError("候选 runner 收到已授权执行身份")
    return {
        "status": "independent_formal_identity_candidate_not_execution_authorized",
        "manifest_sha256": protocol.candidate.canonical_sha256(manifest),
        "marker_repair_status": "marker_update_contract_repaired_for_future_identity",
        "old_observed_arm_excluded": True,
        "availability_execution_authorized": False,
        "formal_collection_execution_authorized": False,
        "provider_calls": 0,
        "credential_reads": 0,
        "docker_sessions_created": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
        "model_tokens": 0,
    }


def qualify_marker_terminalization(manifest: dict[str, Any]) -> dict[str, Any]:
    """用临时非实验文件覆盖 frozen runner 的四类 marker 更新调用。"""

    validate_runtime(manifest)
    with tempfile.TemporaryDirectory(prefix="forge-marker-repair-q-") as directory:
        root = Path(directory)
        attempt = root / "attempt.json"
        normal_batch = root / "normal-batch.json"
        failed_batch = root / "failed-batch.json"
        base._write_once(attempt, {"status": "started", "updated_at": "initial"})
        base._write_once(
            normal_batch,
            {
                "status": "running",
                "completed_arm_count": 0,
                "provider_request_attempt_count": 0,
                "updated_at": "initial",
            },
        )
        base._write_once(
            failed_batch,
            {
                "status": "running",
                "completed_arm_count": 0,
                "updated_at": "initial",
            },
        )
        with _runtime_binding():
            attempt_terminal = base._update_claimed_marker(
                attempt,
                status="complete",
                error_class=None,
                completed_at="terminal",
            )
            batch_progress = base._update_claimed_marker(
                normal_batch,
                completed_arm_count=1,
                endpoint_censored_arm_count=0,
                provider_request_attempt_count=5,
                last_completed_sequence=1,
            )
            batch_terminal = base._update_claimed_marker(
                normal_batch,
                status="completed",
                completed_arm_count=36,
                endpoint_censored_arm_count=0,
                provider_request_attempt_count=36,
                report_sha256="a" * 64,
                completed_at="terminal",
            )
            batch_failure = base._update_claimed_marker(
                failed_batch,
                status="failed",
                error_class="FormalFatalError",
                completed_arm_count=0,
                endpoint_censored_arm_count=0,
                provider_request_attempt_count=0,
                stopped_at="terminal",
            )
        persisted = {
            "attempt_terminal": json.loads(attempt.read_text(encoding="utf-8")),
            "batch_terminal": json.loads(normal_batch.read_text(encoding="utf-8")),
            "batch_failure": json.loads(failed_batch.read_text(encoding="utf-8")),
        }
    if persisted["attempt_terminal"] != attempt_terminal:
        raise IndependentCandidateRunnerError("attempt marker 原子终态未持久化")
    if persisted["batch_terminal"] != batch_terminal:
        raise IndependentCandidateRunnerError("batch marker 正常终态未持久化")
    if persisted["batch_failure"] != batch_failure:
        raise IndependentCandidateRunnerError("batch marker 异常终态未持久化")
    if batch_progress["last_completed_sequence"] != 1:
        raise IndependentCandidateRunnerError("batch progress marker 未更新")
    return {
        "status": "marker_terminalization_qualification_passed",
        "attempt_terminal_status": attempt_terminal["status"],
        "batch_progress_last_sequence": batch_progress["last_completed_sequence"],
        "batch_terminal_status": batch_terminal["status"],
        "batch_failure_status": batch_failure["status"],
        "temporary_files_removed": not root.exists(),
        "provider_calls": 0,
        "credential_reads": 0,
        "docker_sessions_created": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
        "model_tokens": 0,
    }


def _require_release(repo_root: Path) -> dict[str, str]:
    revision = _run_checked(["git", "rev-parse", "HEAD"], cwd=repo_root)
    branch = _run_checked(["git", "branch", "--show-current"], cwd=repo_root)
    origin_main = _run_checked(
        ["git", "rev-parse", "refs/remotes/origin/main"], cwd=repo_root
    )
    _run_checked(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            protocol.IDENTITY_BASELINE_REVISION,
            revision,
        ],
        cwd=repo_root,
    )
    dirty = _run_checked(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo_root
    )
    if branch != "main" or revision != origin_main or dirty:
        raise IndependentCandidateRunnerError(
            "非模型 preflight 要求 clean main == origin/main"
        )
    return {"revision": revision, "branch": branch, "origin_main": origin_main}


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
        raise IndependentCandidateRunnerError("编译镜像 ID 与冻结 identity 不一致")
    return image_id


def _require_old_evidence_read_only(repo_root: Path) -> dict[str, Any]:
    evidence = repo_root / protocol.OLD_EVIDENCE_DIRECTORY
    references = failure_audit.verify_source_inventory(evidence)
    return {
        "directory": protocol.OLD_EVIDENCE_DIRECTORY,
        "file_count": len(references),
        "inventory_sha256": failure_audit._inventory_sha256(references),
        "read_only": True,
        "imported": False,
    }


def _require_new_evidence_absent(
    manifest: dict[str, Any], workspace_root: Path
) -> Path:
    workspace = workspace_root.resolve(strict=True)
    if workspace_root.is_symlink() or workspace != workspace_root.absolute():
        raise IndependentCandidateRunnerError("workspace root 不得经过符号链接")
    compile_sessions = workspace / ".compile-sessions"
    if compile_sessions.is_symlink() or not compile_sessions.is_dir():
        raise IndependentCandidateRunnerError("Compile Session root 不存在或为符号链接")
    evidence = workspace / manifest["candidate_evidence"]["directory"]
    if evidence.exists() or evidence.is_symlink():
        raise IndependentCandidateRunnerError(
            "新 create-once evidence directory 必须不存在"
        )
    if evidence.parent != compile_sessions:
        raise IndependentCandidateRunnerError(
            "新 evidence 未绑定到 Compile Session root"
        )
    return evidence


def collect_preflight(
    manifest: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    validate_runtime(manifest, repo_root)
    release = _require_release(repo_root)
    image_id = _require_docker_identity(manifest, repo_root)
    base._require_zero_managed_resources()
    old_evidence = _require_old_evidence_read_only(repo_root)
    new_evidence = _require_new_evidence_absent(manifest, workspace_root or repo_root)
    return {
        "ready": True,
        "status": "independent_identity_preflight_passed_execution_not_authorized",
        "manifest_sha256": protocol.candidate.canonical_sha256(manifest),
        "observed_clean_release_revision": release["revision"],
        "branch": release["branch"],
        "origin_main": release["origin_main"],
        "compile_image_id": image_id,
        "old_evidence": old_evidence,
        "new_evidence_directory": str(new_evidence),
        "new_evidence_directory_absent": True,
        "zero_managed_resources": True,
        "credential_check": "not_authorized_not_performed",
        "provider_calls": 0,
        "credential_reads": 0,
        "docker_sessions_created": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
        "model_tokens": 0,
    }


def _reject_execution(command: str) -> None:
    raise IndependentCandidateRunnerError(
        f"{command} 需要新的 execution authorization；candidate identity 保持 fail-closed"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=READ_ONLY_COMMANDS + BLOCKED_COMMANDS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest(args.manifest)
    if args.command in BLOCKED_COMMANDS:
        _reject_execution(args.command)
    if args.command == "plan":
        result = protocol.plan_summary(manifest)
    elif args.command == "qualify":
        result = qualify_marker_terminalization(manifest)
    elif args.command == "preflight":
        result = collect_preflight(manifest)
    else:
        result = validate_runtime(manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
