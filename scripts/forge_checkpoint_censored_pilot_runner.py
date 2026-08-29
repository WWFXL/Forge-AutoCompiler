#!/usr/bin/env python3
"""执行 Issue #159 endpoint 删失容忍 checkpoint 六配对 pilot。"""

from __future__ import annotations

import argparse
import asyncio
import copy
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", SCRIPT_ROOT.parent)).resolve()
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_checkpoint_censored_pilot_protocol as protocol  # noqa: E402

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_OUTPUT_DIR = protocol.DEFAULT_OUTPUT_DIR
BATCH_MARKER = "markers/pilot-attempt.json"
PAIR_MARKER = "pair-attempt.json"
PAIR_OUTCOME = "reports/pair-outcome.json"
PILOT_REPORT = "reports/pilot.json"
MANAGED_CONTAINER_PREFIXES = ("deerflow-compile-", "deerflow-replay-")


class PilotError(RuntimeError):
    """pilot identity、evidence、cleanup 或停止规则失败。"""


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise PilotError(f"无法加载 runner 模块: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


parent_adapter = _load_module(
    "forge_checkpoint_censored_pilot_parent_adapter",
    SCRIPT_ROOT / "forge_checkpoint_primary_canary_amendment_authorized.py",
)
primary = parent_adapter.primary_canary


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise PilotError(f"JSON 根节点必须是对象: {path}")
    return value


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _write_once(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
    except FileExistsError as exc:
        raise PilotError(f"不可覆盖已存在的 evidence: {path}") from exc


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
        raise PilotError("无法验证 release Git identity")
    return result.stdout.strip()


def require_release_identity(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, str]:
    protocol.verify_frozen_components(manifest, repo_root)
    branch = _git(repo_root, "branch", "--show-current")
    revision = _git(repo_root, "rev-parse", "HEAD")
    origin_main = _git(repo_root, "rev-parse", "origin/main")
    dirty = _git(repo_root, "status", "--porcelain", "--untracked-files=normal")
    execution = manifest["execution"]
    if branch != execution["release_branch"]:
        raise PilotError("真实 pilot 只能在合并后的 main 分支运行")
    if revision != origin_main:
        raise PilotError("HEAD 与 origin/main 不一致，禁止真实 pilot")
    if dirty:
        raise PilotError("工作树不干净，禁止真实 pilot")
    baseline = execution["authorization_baseline_commit"]
    if _git(repo_root, "merge-base", baseline, revision) != baseline:
        raise PilotError("当前 release 不是授权 baseline 的后代")
    return {"branch": branch, "revision": revision, "origin_main": origin_main}


def require_network_medium(manifest: dict[str, Any]) -> str:
    execution = manifest["execution"]
    name = execution["network_access_medium_env"]
    medium = os.environ.get(name)
    if medium != execution["network_access_medium"]:
        raise PilotError(f"必须通过 {name}=wifi 确认当前网络介质")
    return medium


def managed_containers() -> list[str]:
    result = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise PilotError("无法核验 Compile Session/replay 容器清单")
    return sorted(name for name in result.stdout.splitlines() if name.startswith(MANAGED_CONTAINER_PREFIXES))


def require_zero_managed_containers() -> None:
    names = managed_containers()
    if names:
        raise PilotError("存在 Compile Session/replay orphan，禁止继续 pilot")


def _pair_manifest(manifest: dict[str, Any], pair: dict[str, Any]) -> dict[str, Any]:
    parent_path = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-checkpoint-primary-canary-amendment-authorized.json"
    value = _load_json(parent_path)
    value["schema_version"] = "forge-checkpoint-censored-pair-runtime-1.0.0"
    value["document_type"] = "forge_checkpoint_censored_pair_runtime"
    value["scope"]["pilot_collection_authorized"] = True
    value["continuation"]["arm_order"] = copy.deepcopy(pair["arm_order"])
    value["budget"] = {
        "reachability_requests": 0,
        "reachability_expected_tokens": 0,
        "reachability_maximum_tokens": 0,
        "mechanism_canary_expected_tokens": 120_000,
        "mechanism_canary_maximum_tokens": 240_000,
        "stage_expected_tokens": 120_000,
        "stage_maximum_tokens": 240_000,
    }
    pair_dir = DEFAULT_OUTPUT_DIR / "pairs" / pair["pair_id"]
    value["execution"]["evidence_directory"] = str(pair_dir)
    value["execution"]["controlled_pair_marker"] = PAIR_MARKER
    value["execution"]["authorization_baseline_commit"] = manifest["execution"]["authorization_baseline_commit"]
    value["authorization"] = {
        "issue_url": manifest["authorization"]["issue_url"],
        "authorized_reachability_attempts": 0,
        "authorized_controlled_pairs": 1,
        "stage_maximum_tokens": 240_000,
        "pilot_collection_authorized": True,
    }
    value["pilot"] = {
        "parent_manifest_sha256": protocol.canonical_sha256(manifest),
        "pair_id": pair["pair_id"],
        "order": pair["order"],
        "endpoint_timeout_censors_pair_and_continues": True,
    }
    return value


class _AsyncioProxy:
    def __init__(self, runner: asyncio.Runner):
        self._runner = runner

    def run(self, coroutine: Any) -> Any:
        return self._runner.run(coroutine)

    def __getattr__(self, name: str) -> Any:
        return getattr(asyncio, name)


@contextmanager
def _adapt_parent_runner(
    manifest: dict[str, Any],
    pair_manifest: dict[str, Any],
    async_runner: asyncio.Runner,
) -> Iterator[None]:
    original = {
        "validate_manifest": primary.validate_manifest,
        "verify_frozen_artifacts": primary.verify_frozen_artifacts,
        "require_release_identity": primary.require_release_identity,
        "require_passed_reachability": primary.require_passed_reachability,
        "PAIR_MARKER": primary.PAIR_MARKER,
        "asyncio": primary.asyncio,
    }

    def validate(value: Any) -> dict[str, Any]:
        if value != pair_manifest:
            raise PilotError("pair runtime manifest 发生漂移")
        return value

    def verify(value: dict[str, Any], repo_root: Path = REPO_ROOT) -> None:
        validate(value)
        protocol.verify_frozen_components(manifest, repo_root)

    def release(value: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, str]:
        validate(value)
        return require_release_identity(manifest, repo_root)

    primary.validate_manifest = validate
    primary.verify_frozen_artifacts = verify
    primary.require_release_identity = release
    primary.require_passed_reachability = lambda *_args, **_kwargs: {
        "recorded_tokens": 0,
        "inherited_reachability": False,
    }
    primary.PAIR_MARKER = PAIR_MARKER
    primary.asyncio = _AsyncioProxy(async_runner)
    try:
        yield
    finally:
        for name, value in original.items():
            setattr(primary, name, value)


def _coordinator_terminal(pair_dir: Path) -> dict[str, Any]:
    database = (pair_dir / "checkpoint" / "coordinator.sqlite").resolve()
    if not database.is_file():
        raise PilotError("pair 缺少 checkpoint coordinator evidence")
    uri = f"file:{database.as_posix()}?immutable=1"
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            rows = connection.execute("SELECT capture_id, phase, payload_json FROM checkpoint_capture").fetchall()
    except (sqlite3.Error, OSError) as exc:
        raise PilotError("无法以 immutable=1 审计 coordinator evidence") from exc
    if len(rows) != 1:
        raise PilotError("pair coordinator capture 数量不是 1")
    capture_id, phase, payload_raw = rows[0]
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError as exc:
        raise PilotError("pair coordinator payload 不是有效 JSON") from exc
    if phase != "cleaned" or payload.get("cleanup", {}).get("succeeded") is not True:
        raise PilotError("pair cleanup 未闭合")
    return {"capture_id": capture_id, "phase": phase, "cleanup_succeeded": True}


def _ledger_events(pair_dir: Path) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for arm in ("baseline", "treatment"):
        path = pair_dir / "ledgers" / f"{arm}.jsonl"
        if path.is_file():
            result[arm] = primary.ExperimentLedger.verify_path(path)
    if not result:
        raise PilotError("pair 没有 arm ledger")
    return result


def _recorded_tokens(events: list[dict[str, Any]]) -> int:
    total = 0
    for event in events:
        if event["event"] != "model.request_completed":
            continue
        usage = event["payload"].get("token_usage")
        tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
        if type(tokens) is not int or tokens < 0:
            raise PilotError("完成请求缺少有效 recorded token usage")
        total += tokens
    return total


def _arm_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    started_at = datetime.fromisoformat(events[0]["occurred_at"])
    completed_at = datetime.fromisoformat(events[-1]["occurred_at"])
    return {
        "model_requests": sum(event["event"] == "model.request_started" for event in events),
        "submit_attempts": sum(event["event"] == "submit.started" for event in events),
        "clean_replay_attempts": sum(event["event"] == "replay.started" for event in events),
        "recorded_tokens": _recorded_tokens(events),
        "ledger_wall_clock_seconds": round((completed_at - started_at).total_seconds(), 6),
    }


def _endpoint_timeout_outcome(
    manifest: dict[str, Any],
    pair: dict[str, Any],
    pair_manifest: dict[str, Any],
    pair_dir: Path,
    error: BaseException,
) -> dict[str, Any]:
    marker = _load_json(pair_dir / "markers" / PAIR_MARKER)
    if marker.get("status") != "failed" or marker.get("manifest_sha256") != protocol.canonical_sha256(pair_manifest):
        raise PilotError("失败 pair marker identity 或终态无效") from error
    coordinator = _coordinator_terminal(pair_dir)
    require_zero_managed_containers()
    ledgers = _ledger_events(pair_dir)
    failures: list[tuple[str, dict[str, Any]]] = []
    classifications: list[tuple[str, dict[str, Any]]] = []
    metrics_by_arm: dict[str, dict[str, Any]] = {}
    for arm, events in ledgers.items():
        metrics_by_arm[arm] = _arm_metrics(events)
        failures.extend((arm, event) for event in events if event["event"] in {"model.request_failed", "model.request_cancelled"})
        classifications.extend((arm, event) for event in events if event["event"] == "failure.recorded" and event["payload"].get("primary") is True)
    if any(metrics["recorded_tokens"] > manifest["continuation"]["maximum_recorded_tokens_per_arm"] for metrics in metrics_by_arm.values()):
        raise PilotError("endpoint-censored arm 超过 recorded-token 上限") from error
    if len(failures) != 1 or failures[0][1]["event"] != "model.request_failed":
        raise PilotError("失败 pair 不是唯一 endpoint timeout") from error
    failed_arm, failed = failures[0]
    payload = failed["payload"]
    matching = [
        item
        for arm, item in classifications
        if arm == failed_arm and item["payload"].get("domain") == "model_endpoint" and item["payload"].get("classification") == "timeout" and "retry_exhausted" in item["payload"].get("secondary_classifications", [])
    ]
    if payload.get("classification") != "timeout" or payload.get("retry_exhausted") is not True or payload.get("status_code") is not None or len(matching) != 1 or len(classifications) != 1:
        raise PilotError("失败 pair 不满足预注册 endpoint timeout 删失定义") from error
    return {
        "schema_version": "forge-checkpoint-censored-pair-outcome-1.0.0",
        "document_type": "forge_checkpoint_censored_pair_outcome",
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "pair_manifest_sha256": protocol.canonical_sha256(pair_manifest),
        "pair_id": pair["pair_id"],
        "order": pair["order"],
        "arm_order": pair["arm_order"],
        "status": "endpoint_censored",
        "endpoint_timeout_arm": failed_arm,
        "metrics_by_arm": metrics_by_arm,
        "recorded_tokens": sum(metrics["recorded_tokens"] for metrics in metrics_by_arm.values()),
        "conditional_mechanism_contribution": 0,
        "itt_attrition_contribution": 1,
        "coordinator": coordinator,
        "error_class": type(error).__name__,
        "completed_at": datetime.now(UTC).isoformat(),
    }


def _passed_outcome(
    manifest: dict[str, Any],
    pair: dict[str, Any],
    pair_manifest: dict[str, Any],
    pair_dir: Path,
    report: dict[str, Any],
) -> dict[str, Any]:
    if report.get("passed") is not True or report.get("complete_pair") is not True or report.get("arm_order") != pair["arm_order"]:
        raise PilotError("passed pair report 终态无效")
    coordinator = _coordinator_terminal(pair_dir)
    require_zero_managed_containers()
    arms = report.get("arms")
    if not isinstance(arms, list) or {item.get("arm") for item in arms} != {
        "baseline",
        "treatment",
    }:
        raise PilotError("passed pair 缺少双臂结果")
    tokens_by_arm = {item["arm"]: item["recorded_tokens"] for item in arms}
    if any(type(tokens) is not int or tokens < 0 or tokens > manifest["continuation"]["maximum_recorded_tokens_per_arm"] for tokens in tokens_by_arm.values()):
        raise PilotError("passed pair arm token evidence 无效")
    ledgers = _ledger_events(pair_dir)
    if set(ledgers) != {"baseline", "treatment"}:
        raise PilotError("passed pair 缺少双臂 ledger")
    metrics_by_arm = {arm: _arm_metrics(events) for arm, events in ledgers.items()}
    if any(metrics_by_arm[arm]["recorded_tokens"] != tokens_by_arm[arm] for arm in metrics_by_arm):
        raise PilotError("passed pair report 与 ledger token 不一致")
    return {
        "schema_version": "forge-checkpoint-censored-pair-outcome-1.0.0",
        "document_type": "forge_checkpoint_censored_pair_outcome",
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "pair_manifest_sha256": protocol.canonical_sha256(pair_manifest),
        "pair_id": pair["pair_id"],
        "order": pair["order"],
        "arm_order": pair["arm_order"],
        "status": "complete",
        "arms": arms,
        "metrics_by_arm": metrics_by_arm,
        "recorded_tokens": sum(tokens_by_arm.values()),
        "conditional_mechanism_contribution": 1,
        "itt_attrition_contribution": 1,
        "coordinator": coordinator,
        "completed_at": datetime.now(UTC).isoformat(),
    }


def execute_real_pair(
    manifest: dict[str, Any],
    pair: dict[str, Any],
    pair_dir: Path,
    async_runner: asyncio.Runner,
) -> dict[str, Any]:
    pair_manifest = _pair_manifest(manifest, pair)
    pair_manifest["execution"]["evidence_directory"] = str(pair_dir)
    with _adapt_parent_runner(manifest, pair_manifest, async_runner):
        try:
            with parent_adapter.build_layout.use_windows_safe_build_layout(primary):
                report = primary.run_controlled_pair(
                    pair_manifest,
                    output_dir=pair_dir,
                    repo_root=REPO_ROOT,
                )
        except BaseException as exc:
            return _endpoint_timeout_outcome(manifest, pair, pair_manifest, pair_dir, exc)
    return _passed_outcome(manifest, pair, pair_manifest, pair_dir, report)


def _claim_batch_marker(path: Path, manifest_sha256: str, revision: str) -> dict[str, Any]:
    if path.exists():
        marker = _load_json(path)
        if marker.get("manifest_sha256") != manifest_sha256 or marker.get("release_revision") != revision:
            raise PilotError("已有 batch marker identity 发生漂移")
        if marker.get("status") not in {"started", "passed"}:
            raise PilotError("已有 batch marker 已失败关闭")
        return marker
    value = {
        "schema_version": "forge-checkpoint-censored-pilot-attempt-1.0.0",
        "document_type": "forge_checkpoint_censored_pilot_attempt",
        "manifest_sha256": manifest_sha256,
        "release_revision": revision,
        "status": "started",
        "error_class": None,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _write_once(path, value)
    return value


def summarize(
    manifest: dict[str, Any],
    release: dict[str, str],
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    complete = [item for item in outcomes if item["status"] == "complete"]
    censored = [item for item in outcomes if item["status"] == "endpoint_censored"]
    tokens = sum(item["recorded_tokens"] for item in outcomes)
    metric_names = ("model_requests", "submit_attempts", "clean_replay_attempts", "recorded_tokens", "ledger_wall_clock_seconds")
    paired_deltas = {name: [round(item["metrics_by_arm"]["treatment"][name] - item["metrics_by_arm"]["baseline"][name], 6) for item in complete] for name in metric_names}
    return {
        "schema_version": "forge-checkpoint-censored-pilot-report-1.0.0",
        "document_type": "forge_checkpoint_censored_pilot_report",
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "release_revision": release["revision"],
        "network_access_medium": manifest["execution"]["network_access_medium"],
        "status": "completed_with_censoring" if censored else "completed",
        "itt_attrition": {
            "scheduled_pairs": protocol.PAIR_COUNT,
            "observed_pairs": len(outcomes),
            "complete_pairs": len(complete),
            "endpoint_censored_pairs": len(censored),
            "endpoint_censored_pair_ids": [item["pair_id"] for item in censored],
            "endpoint_timeout_arms": {arm: sum(item.get("endpoint_timeout_arm") == arm for item in censored) for arm in ("baseline", "treatment")},
            "observed_arm_attempts": {arm: sum(arm in item.get("metrics_by_arm", {}) for item in outcomes) for arm in ("baseline", "treatment")},
        },
        "conditional_mechanism": {
            "eligible_complete_pairs": len(complete),
            "pair_ids": [item["pair_id"] for item in complete],
            "repair_conversion": {"baseline_passed": len(complete), "treatment_passed": len(complete)},
            "paired_deltas_treatment_minus_baseline": paired_deltas,
            "mean_paired_deltas": {name: (round(sum(values) / len(values), 6) if values else None) for name, values in paired_deltas.items()},
            "descriptive_only": True,
            "model_ranking_performed": False,
            "p_value_computed": False,
        },
        "recorded_tokens": tokens,
        "maximum_recorded_tokens": manifest["budget"]["stage_maximum_recorded_tokens"],
        "pairs": outcomes,
        "completed_at": datetime.now(UTC).isoformat(),
    }


PairExecutor = Callable[[dict[str, Any], dict[str, Any], Path], dict[str, Any]]


def run_pilot(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    pair_executor: PairExecutor | None = None,
) -> dict[str, Any]:
    protocol.validate_manifest(manifest, repo_root)
    expected = Path(manifest["execution"]["evidence_directory"]).resolve(strict=False)
    if output_dir.resolve(strict=False) != expected:
        raise PilotError("pilot evidence 必须写入冻结授权目录")
    release = require_release_identity(manifest, repo_root)
    require_network_medium(manifest)
    primary.require_compose_dood()
    protocol.verify_parent_evidence(manifest)
    require_zero_managed_containers()
    digest = protocol.canonical_sha256(manifest)
    marker_path = output_dir / BATCH_MARKER
    marker = _claim_batch_marker(marker_path, digest, release["revision"])
    report_path = output_dir / PILOT_REPORT
    if marker["status"] == "passed":
        report = _load_json(report_path)
        if report.get("manifest_sha256") != digest:
            raise PilotError("已完成 pilot report identity 发生漂移")
        return report

    outcomes: list[dict[str, Any]] = []
    try:
        with asyncio.Runner() as async_runner:
            for pair in manifest["schedule"]:
                pair_dir = output_dir / "pairs" / pair["pair_id"]
                outcome_path = pair_dir / PAIR_OUTCOME
                if outcome_path.exists():
                    outcome = _load_json(outcome_path)
                    if outcome.get("manifest_sha256") != digest or outcome.get("pair_id") != pair["pair_id"] or outcome.get("status") not in {"complete", "endpoint_censored"}:
                        raise PilotError("已有 pair outcome identity 或终态无效")
                else:
                    if pair_dir.exists() and any(pair_dir.iterdir()):
                        raise PilotError(f"{pair['pair_id']} 已开始但没有终态，禁止自动补跑")
                    require_zero_managed_containers()
                    if pair_executor is None:
                        outcome = execute_real_pair(manifest, pair, pair_dir, async_runner)
                    else:
                        outcome = pair_executor(manifest, pair, pair_dir)
                    if outcome.get("status") not in {
                        "complete",
                        "endpoint_censored",
                    }:
                        raise PilotError("非 endpoint 失败关闭 pilot")
                    _write_once(outcome_path, outcome)
                outcomes.append(outcome)
                recorded = sum(item["recorded_tokens"] for item in outcomes)
                if recorded > manifest["budget"]["stage_maximum_recorded_tokens"]:
                    raise PilotError("pilot 超过 recorded-token 机械上限")
                require_zero_managed_containers()
        if len(outcomes) != protocol.PAIR_COUNT:
            raise PilotError("pilot 未形成 6 个预注册 pair 终态")
        report = summarize(manifest, release, outcomes)
        _write_once(report_path, report)
        marker.update(
            status="passed",
            error_class=None,
            updated_at=datetime.now(UTC).isoformat(),
        )
        _atomic_write(marker_path, marker)
        return report
    except BaseException as exc:
        marker.update(
            status="failed",
            error_class=type(exc).__name__,
            updated_at=datetime.now(UTC).isoformat(),
        )
        _atomic_write(marker_path, marker)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "run", "report"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
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
                raise PilotError("pilot report identity 发生漂移")
        else:
            result = run_pilot(manifest, output_dir=args.output_dir)
    except (OSError, PilotError, protocol.ProtocolError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
