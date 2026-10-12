#!/usr/bin/env python3
"""Issue #425：合法相对符号链接 checkpoint 恢复门禁。"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import tarfile
import tempfile
from pathlib import Path
from typing import Callable

from forge_checkpoint_archive import (
    CheckpointRestoreError,
    checkpoint_tree_sha256,
    restore_checkpoint_archive,
)

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
IDENTITY = "symlink-safe-checkpoint-restore-gate-v1"
V4_STATE_ROOT = (
    REPO_ROOT
    / ".compile-sessions/benchmark-evidence-dynamic-budget-trajectory-qualification-v4"
    / "states/autotools-libestr-state-3/checkpoint"
)
V4_CANONICAL_WORKSPACE = (
    REPO_ROOT
    / ".compile-sessions/benchmark-evidence-dynamic-budget-trajectory-qualification-v4"
    / "working/autotools-libestr/canonical-workspace"
)
V4_IGNORED_FILE_NAMES = frozenset(
    {"CMakeConfigureLog.yaml", "CMakeOutput.log", "CMakeError.log", "config.log"}
)
V4_IGNORED_DIRECTORY_NAMES = frozenset({"autom4te.cache"})
REPORT_JSON_PATH = (
    REPO_ROOT / "benchmarks/reports/cpp-symlink-safe-checkpoint-restore-gate-v1.json"
)
REPORT_MD_PATH = (
    REPO_ROOT / "benchmarks/reports/cpp-symlink-safe-checkpoint-restore-gate-v1.md"
)


def _add_file(archive: tarfile.TarFile, name: str, content: bytes) -> None:
    member = tarfile.TarInfo(name)
    member.size = len(content)
    member.mode = 0o644
    archive.addfile(member, io.BytesIO(content))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _add_link(
    archive: tarfile.TarFile,
    name: str,
    target: str,
    *,
    hardlink: bool = False,
) -> None:
    member = tarfile.TarInfo(name)
    member.type = tarfile.LNKTYPE if hardlink else tarfile.SYMTYPE
    member.linkname = target
    member.mode = 0o777
    archive.addfile(member)


def _write_archive(path: Path, builder: Callable[[tarfile.TarFile], None]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        builder(archive)


def _expect_rejected(
    root: Path,
    name: str,
    builder: Callable[[tarfile.TarFile], None],
) -> dict[str, object]:
    archive_path = root / f"{name}.tar.gz"
    destination = root / f"{name}-restored"
    _write_archive(archive_path, builder)
    try:
        restore_checkpoint_archive(archive_path, destination)
    except CheckpointRestoreError:
        return {"case": name, "passed": not destination.exists(), "published": False}
    return {"case": name, "passed": False, "published": destination.exists()}


def _run_synthetic_cases(root: Path) -> list[dict[str, object]]:
    legal_archive = root / "legal-relative-symlink.tar.gz"

    def legal_builder(archive: tarfile.TarFile) -> None:
        _add_file(archive, "src/libestr.la", b"libestr metadata\n")
        _add_link(archive, "src/.libs/libestr.la", "../libestr.la")

    _write_archive(legal_archive, legal_builder)
    legal_destination = root / "legal-relative-symlink-restored"
    legal_hash = restore_checkpoint_archive(legal_archive, legal_destination)
    legal_link = legal_destination / "src/.libs/libestr.la"
    cases: list[dict[str, object]] = [
        {
            "case": "legal_parent_relative_symlink",
            "passed": (
                legal_link.is_symlink()
                and os.readlink(legal_link) == "../libestr.la"
                and legal_link.read_bytes() == b"libestr metadata\n"
                and legal_hash == checkpoint_tree_sha256(legal_destination)
            ),
            "published": legal_destination.exists(),
        }
    ]

    cases.append(
        _expect_rejected(
            root,
            "escaping_relative_symlink",
            lambda archive: _add_link(archive, "src/.libs/escape", "../../../outside"),
        )
    )
    cases.append(
        _expect_rejected(
            root,
            "absolute_symlink",
            lambda archive: _add_link(archive, "src/escape", "/etc/passwd"),
        )
    )
    cases.append(
        _expect_rejected(
            root,
            "escaping_hardlink",
            lambda archive: _add_link(
                archive, "src/hardlink", "../outside", hardlink=True
            ),
        )
    )

    def device_builder(archive: tarfile.TarFile) -> None:
        member = tarfile.TarInfo("device")
        member.type = tarfile.CHRTYPE
        member.devmajor = 1
        member.devminor = 3
        archive.addfile(member)

    cases.append(_expect_rejected(root, "character_device", device_builder))

    def fifo_builder(archive: tarfile.TarFile) -> None:
        member = tarfile.TarInfo("pipe")
        member.type = tarfile.FIFOTYPE
        archive.addfile(member)

    cases.append(_expect_rejected(root, "fifo", fifo_builder))

    hash_archive = root / "hash-mismatch.tar.gz"
    _write_archive(hash_archive, lambda archive: _add_file(archive, "value", b"x"))
    hash_destination = root / "hash-mismatch-restored"
    try:
        restore_checkpoint_archive(
            hash_archive,
            hash_destination,
            expected_tree_sha256="0" * 64,
        )
    except CheckpointRestoreError:
        hash_passed = not hash_destination.exists()
    else:
        hash_passed = False
    cases.append(
        {
            "case": "tree_hash_mismatch_not_published",
            "passed": hash_passed,
            "published": hash_destination.exists(),
        }
    )
    return cases


def _run_v4_read_only_case(root: Path) -> dict[str, object]:
    archive_path = V4_STATE_ROOT / "workspace.tar.gz"
    message_path = V4_STATE_ROOT / "message.json"
    source_hashes_before = {
        "workspace_archive_sha256": _sha256_file(archive_path),
        "message_sha256": _sha256_file(message_path),
        "canonical_workspace_tree_sha256": checkpoint_tree_sha256(
            V4_CANONICAL_WORKSPACE
        ),
    }
    message = json.loads(message_path.read_text(encoding="utf-8"))
    expected_full = checkpoint_tree_sha256(V4_CANONICAL_WORKSPACE)
    expected_decision = message["workspace_tree_sha256"]
    destination = root / "v4-libestr-restored"
    observed_full = restore_checkpoint_archive(
        archive_path,
        destination,
        expected_tree_sha256=expected_full,
    )
    observed_decision = checkpoint_tree_sha256(
        destination,
        ignored_file_names=V4_IGNORED_FILE_NAMES,
        ignored_directory_names=V4_IGNORED_DIRECTORY_NAMES,
    )
    link = destination / "src/.libs/libestr.la"
    source_hashes_after = {
        "workspace_archive_sha256": _sha256_file(archive_path),
        "message_sha256": _sha256_file(message_path),
        "canonical_workspace_tree_sha256": checkpoint_tree_sha256(
            V4_CANONICAL_WORKSPACE
        ),
    }
    source_mutated = source_hashes_before != source_hashes_after
    return {
        "case": "v4_libestr_checkpoint_round_trip",
        "passed": (
            observed_full == expected_full
            and observed_decision == expected_decision
            and link.is_symlink()
            and os.readlink(link) == "../libestr.la"
            and not source_mutated
        ),
        "expected_full_tree_sha256": expected_full,
        "observed_full_tree_sha256": observed_full,
        "expected_decision_tree_sha256": expected_decision,
        "observed_decision_tree_sha256": observed_decision,
        "link_target": os.readlink(link) if link.is_symlink() else None,
        "source_hashes_before": source_hashes_before,
        "source_hashes_after": source_hashes_after,
        "source_mutated": source_mutated,
    }


def run_gate() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="forge-symlink-restore-gate-") as raw:
        root = Path(raw)
        cases = _run_synthetic_cases(root)
        v4_case = _run_v4_read_only_case(root)
        cases.append(v4_case)
    passed = all(item["passed"] is True for item in cases)
    return {
        "schema_version": "1.0.0",
        "identity": IDENTITY,
        "status": "passed" if passed else "failed",
        "decision": (
            "proceed_to_dynamic_budget_trajectory_qualification_v5_design"
            if passed
            else "stop_before_dynamic_budget_trajectory_qualification_v5"
        ),
        "cases": cases,
        "summary": {
            "passed": sum(item["passed"] is True for item in cases),
            "total": len(cases),
            "credential_read": False,
            "provider_requests": 0,
            "v4_evidence_mutated": v4_case["source_mutated"],
        },
        "interpretation": {
            "supports": [
                "checkpoint 恢复器可区分合法相对 symlink 与越界链接",
                "v4 libestr checkpoint 可保持 tree hash 无损恢复",
            ],
            "does_not_support": [
                "动态预算 controller 的成功率、成本或时间效果",
                "Jev 或 Agent continuation 的能力",
                "v5 跨构建系统轨迹资格已经通过",
            ],
        },
    }


def _render_markdown(report: dict[str, object]) -> str:
    summary = report["summary"]
    assert isinstance(summary, dict)
    cases = report["cases"]
    assert isinstance(cases, list)
    lines = [
        "# Symlink-safe checkpoint restore gate v1",
        "",
        f"**决定：`{report['decision']}`。**",
        "",
        f"状态：`{report['status']}`；门禁通过 `{summary['passed']}/{summary['total']}`。",
        "",
        "## 门禁结果",
        "",
        "| Case | 通过 |",
        "| --- | --- |",
    ]
    lines.extend(
        f"| `{item['case']}` | {'是' if item['passed'] else '否'} |" for item in cases
    )
    lines.extend(
        [
            "",
            "## 结论边界",
            "",
            "本门禁是工程修复验证。通过只说明合法 libtool 相对符号链接能够安全恢复，并解除全新 v5 轨迹资格的基础设施阻塞；不评价动态预算、Jev、Agent 或 controller 效果。",
            "",
            "v1-v4 identity、runner、报告与 raw evidence 均保持只读；本门禁未续跑 v4。",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(report: dict[str, object]) -> None:
    REPORT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    REPORT_MD_PATH.write_text(_render_markdown(report), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("run",))
    args = parser.parse_args()
    if args.command == "run":
        report = run_gate()
        write_report(report)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["status"] == "passed" else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
