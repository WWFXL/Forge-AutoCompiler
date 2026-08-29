#!/usr/bin/env python3
"""执行 Issue #161 checkpoint 六配对 pilot recovery amendment。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", SCRIPT_ROOT.parent)).resolve()
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_checkpoint_censored_pilot_protocol as v1_protocol  # noqa: E402
import forge_checkpoint_censored_pilot_recovery_protocol as protocol  # noqa: E402
import forge_checkpoint_censored_pilot_runner as v1_runner  # noqa: E402

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_OUTPUT_DIR = protocol.DEFAULT_OUTPUT_DIR
BATCH_MARKER = "markers/recovery-attempt.json"
PILOT_REPORT = "reports/pilot.json"
IMPORTED_OUTCOME = "imports/pair-01.json"


class RecoveryError(RuntimeError):
    """Recovery identity、导入 evidence 或停止规则失败。"""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise RecoveryError(f"JSON 根节点必须是对象: {path}")
    return value


def _file_snapshot(database: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in (database, Path(f"{database}-wal"), Path(f"{database}-shm")):
        if path.is_file():
            result[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def coordinator_terminal_from_copy(pair_dir: Path) -> dict[str, Any]:
    database = (pair_dir / "checkpoint" / "coordinator.sqlite").resolve()
    if not database.is_file():
        raise RecoveryError("pair 缺少 checkpoint coordinator evidence")
    before = _file_snapshot(database)
    with tempfile.TemporaryDirectory(prefix="forge-coordinator-audit-") as temp:
        target = Path(temp) / database.name
        for source in (
            database,
            Path(f"{database}-wal"),
            Path(f"{database}-shm"),
        ):
            if source.is_file():
                shutil.copy2(source, Path(temp) / source.name)
        copied_shm = Path(f"{target}-shm")
        copied_shm.unlink(missing_ok=True)
        try:
            with sqlite3.connect(target) as connection:
                rows = connection.execute("SELECT capture_id, phase, payload_json FROM checkpoint_capture").fetchall()
        except sqlite3.Error as exc:
            raise RecoveryError("无法从 coordinator 临时副本恢复 WAL") from exc
    after = _file_snapshot(database)
    if before != after:
        raise RecoveryError("copy-based 审计期间 coordinator 源文件发生变化")
    if len(rows) != 1:
        raise RecoveryError("pair coordinator capture 数量不是 1")
    capture_id, phase, payload_raw = rows[0]
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError as exc:
        raise RecoveryError("pair coordinator payload 不是有效 JSON") from exc
    if phase != "cleaned" or payload.get("cleanup", {}).get("succeeded") is not True:
        raise RecoveryError("pair cleanup 未闭合")
    return {
        "capture_id": capture_id,
        "phase": phase,
        "cleanup_succeeded": True,
        "audit": "copied-main-wal-shm",
        "source_files": sorted(before),
    }


def _git(repo_root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo_root}", *arguments],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RecoveryError("无法验证 recovery release Git identity")
    return result.stdout.strip()


def require_release_identity(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, str]:
    protocol.verify_frozen_components(manifest, repo_root)
    branch = _git(repo_root, "branch", "--show-current")
    revision = _git(repo_root, "rev-parse", "HEAD")
    origin_main = _git(repo_root, "rev-parse", "origin/main")
    dirty = _git(repo_root, "status", "--porcelain", "--untracked-files=normal")
    if branch != "main" or revision != origin_main or dirty:
        raise RecoveryError("真实 recovery 需要干净的 main == origin/main")
    baseline = manifest["execution"]["authorization_baseline_commit"]
    if _git(repo_root, "merge-base", baseline, revision) != baseline:
        raise RecoveryError("当前 release 不是 recovery baseline 的后代")
    return {"branch": branch, "revision": revision, "origin_main": origin_main}


@contextmanager
def _adapt_v1_runner(manifest: dict[str, Any]) -> Iterator[None]:
    original_verify = v1_runner.protocol.verify_frozen_components
    original_coordinator = v1_runner._coordinator_terminal
    v1_runner.protocol.verify_frozen_components = lambda _value, repo_root=REPO_ROOT: protocol.verify_frozen_components(manifest, repo_root)
    v1_runner._coordinator_terminal = coordinator_terminal_from_copy
    try:
        yield
    finally:
        v1_runner.protocol.verify_frozen_components = original_verify
        v1_runner._coordinator_terminal = original_coordinator


def _import_pair_one(manifest: dict[str, Any]) -> dict[str, Any]:
    v1_manifest = _load_json(protocol.V1_MANIFEST_PATH)
    if v1_protocol.canonical_sha256(v1_manifest) != protocol.V1_CANONICAL_SHA256:
        raise RecoveryError("导入的 v1 manifest identity 发生漂移")
    pair = v1_manifest["schedule"][0]
    pair_dir = protocol.V1_OUTPUT_DIR / "pairs" / pair["pair_id"]
    pair_manifest = v1_runner._pair_manifest(v1_manifest, pair)
    pair_manifest["execution"]["evidence_directory"] = str(pair_dir)
    report = _load_json(pair_dir / "reports" / "controlled-pair.json")
    with _adapt_v1_runner(manifest):
        outcome = v1_runner._passed_outcome(v1_manifest, pair, pair_manifest, pair_dir, report)
    if outcome["recorded_tokens"] != protocol.IMPORTED_RECORDED_TOKENS:
        raise RecoveryError("导入 pair-01 的 recorded tokens 发生漂移")
    outcome["manifest_sha256"] = protocol.canonical_sha256(manifest)
    outcome["source"] = {
        "kind": "frozen-v1-complete-pair",
        "manifest_sha256": protocol.V1_CANONICAL_SHA256,
        "evidence_directory": str(protocol.V1_OUTPUT_DIR),
        "rerun": False,
    }
    return outcome


def _claim_marker(path: Path, digest: str, revision: str) -> dict[str, Any]:
    if path.exists():
        marker = _load_json(path)
        if marker.get("manifest_sha256") != digest or marker.get("release_revision") != revision or marker.get("status") not in {"started", "passed"}:
            raise RecoveryError("recovery marker identity 或终态无效")
        return marker
    value = {
        "schema_version": "forge-checkpoint-censored-pilot-recovery-attempt-1.0.0",
        "document_type": "forge_checkpoint_censored_pilot_recovery_attempt",
        "manifest_sha256": digest,
        "release_revision": revision,
        "status": "started",
        "error_class": None,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    v1_runner._write_once(path, value)
    return value


def run_recovery(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    pair_executor: v1_runner.PairExecutor | None = None,
) -> dict[str, Any]:
    protocol.validate_manifest(manifest, repo_root)
    if output_dir.resolve(strict=False) != Path(manifest["execution"]["evidence_directory"]).resolve(strict=False):
        raise RecoveryError("recovery evidence 必须写入独立冻结目录")
    release = require_release_identity(manifest, repo_root)
    v1_runner.require_network_medium(manifest)
    v1_runner.primary.require_compose_dood()
    protocol.verify_v1_evidence(manifest, repo_root=repo_root)
    v1_manifest = _load_json(protocol.V1_MANIFEST_PATH)
    v1_protocol.verify_parent_evidence(v1_manifest)
    v1_runner.require_zero_managed_containers()
    digest = protocol.canonical_sha256(manifest)
    marker_path = output_dir / BATCH_MARKER
    marker = _claim_marker(marker_path, digest, release["revision"])
    report_path = output_dir / PILOT_REPORT
    if marker["status"] == "passed":
        report = _load_json(report_path)
        if report.get("manifest_sha256") != digest:
            raise RecoveryError("已完成 recovery report identity 发生漂移")
        return report

    outcomes: list[dict[str, Any]] = []
    try:
        imported_path = output_dir / IMPORTED_OUTCOME
        if imported_path.exists():
            imported = _load_json(imported_path)
        else:
            imported = _import_pair_one(manifest)
            v1_runner._write_once(imported_path, imported)
        if imported.get("manifest_sha256") != digest or imported.get("pair_id") != "pair-01" or imported.get("status") != "complete":
            raise RecoveryError("导入 pair-01 outcome 无效")
        outcomes.append(imported)

        with asyncio.Runner() as async_runner, _adapt_v1_runner(manifest):
            for pair in manifest["schedule"][1:]:
                pair_dir = output_dir / "pairs" / pair["pair_id"]
                outcome_path = pair_dir / v1_runner.PAIR_OUTCOME
                if outcome_path.exists():
                    outcome = _load_json(outcome_path)
                    if outcome.get("manifest_sha256") != digest or outcome.get("pair_id") != pair["pair_id"] or outcome.get("status") not in {"complete", "endpoint_censored"}:
                        raise RecoveryError("已有 recovery pair outcome 无效")
                else:
                    if pair_dir.exists() and any(pair_dir.iterdir()):
                        raise RecoveryError(f"{pair['pair_id']} 已开始但没有终态，禁止补跑")
                    v1_runner.require_zero_managed_containers()
                    if pair_executor is None:
                        outcome = v1_runner.execute_real_pair(manifest, pair, pair_dir, async_runner)
                    else:
                        outcome = pair_executor(manifest, pair, pair_dir)
                    if outcome.get("status") not in {
                        "complete",
                        "endpoint_censored",
                    }:
                        raise RecoveryError("非 endpoint 失败关闭 recovery")
                    v1_runner._write_once(outcome_path, outcome)
                outcomes.append(outcome)
                additional = sum(item["recorded_tokens"] for item in outcomes[1:])
                total = sum(item["recorded_tokens"] for item in outcomes)
                if additional > protocol.ADDITIONAL_RECORDED_TOKEN_LIMIT or total > protocol.TOTAL_RECORDED_TOKEN_LIMIT:
                    raise RecoveryError("recovery 超过 recorded-token 机械上限")
                v1_runner.require_zero_managed_containers()
        if len(outcomes) != 6:
            raise RecoveryError("recovery 未形成原预注册 6 pair 终态")
        report = v1_runner.summarize(manifest, release, outcomes)
        report["recovery"] = {
            "imported_pair_ids": ["pair-01"],
            "executed_pair_ids": [f"pair-{number:02d}" for number in range(2, 7)],
            "replacement": False,
            "backfill": False,
            "coordinator_audit": "copy-main-wal-shm-then-read-copy",
        }
        v1_runner._write_once(report_path, report)
        marker.update(
            status="passed",
            error_class=None,
            updated_at=datetime.now(UTC).isoformat(),
        )
        v1_runner._atomic_write(marker_path, marker)
        return report
    except BaseException as exc:
        marker.update(
            status="failed",
            error_class=type(exc).__name__,
            updated_at=datetime.now(UTC).isoformat(),
        )
        v1_runner._atomic_write(marker_path, marker)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "run", "report"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    try:
        manifest = protocol.validate_manifest(_load_json(args.manifest))
        if args.command == "validate":
            protocol.verify_frozen_components(manifest)
            result = {
                "status": "valid",
                "manifest_sha256": protocol.canonical_sha256(manifest),
                "provider_calls": 0,
            }
        elif args.command == "report":
            result = _load_json(args.output_dir / PILOT_REPORT)
            if result.get("manifest_sha256") != protocol.canonical_sha256(manifest):
                raise RecoveryError("recovery report identity 发生漂移")
        else:
            result = run_recovery(manifest, output_dir=args.output_dir)
    except (OSError, RecoveryError, protocol.ProtocolError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
