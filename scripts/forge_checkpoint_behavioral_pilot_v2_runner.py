#!/usr/bin/env python3
"""执行 Issue #165 checkpoint 行为终态 v2 六配对实验。"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", SCRIPT_ROOT.parent)).resolve()
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_checkpoint_behavioral_pilot_v2_protocol as protocol  # noqa: E402
import forge_checkpoint_censored_pilot_recovery_runner as recovery_runner  # noqa: E402
import forge_checkpoint_censored_pilot_runner as v1_runner  # noqa: E402

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_OUTPUT_DIR = protocol.DEFAULT_OUTPUT_DIR
BATCH_MARKER = "markers/v2-pilot-attempt.json"
PAIR_MARKER = "pair-attempt.json"
PAIR_OUTCOME = "reports/pair-outcome.json"
PILOT_REPORT = "reports/pilot.json"

primary = v1_runner.primary
parent_adapter = v1_runner.parent_adapter


class BehavioralPilotError(RuntimeError):
    """v2 identity、evidence、预算、cleanup 或终态分类失败。"""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BehavioralPilotError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise BehavioralPilotError(f"JSON 根节点必须是对象: {path}")
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
        raise BehavioralPilotError(f"不可覆盖已存在的 evidence: {path}") from exc


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
        raise BehavioralPilotError("无法验证 v2 release Git identity")
    return result.stdout.strip()


def require_release_identity(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, str]:
    protocol.verify_frozen_components(manifest, repo_root)
    branch = _git(repo_root, "branch", "--show-current")
    revision = _git(repo_root, "rev-parse", "HEAD")
    origin_main = _git(repo_root, "rev-parse", "origin/main")
    dirty = _git(repo_root, "status", "--porcelain", "--untracked-files=normal")
    execution = manifest["execution"]
    if branch != execution["release_branch"] or revision != origin_main or dirty:
        raise BehavioralPilotError("真实 v2 必须位于干净且与 origin/main 一致的 main")
    baseline = execution["authorization_baseline_commit"]
    if _git(repo_root, "merge-base", baseline, revision) != baseline:
        raise BehavioralPilotError("当前 release 不是 v2 授权 baseline 的后代")
    return {"branch": branch, "revision": revision, "origin_main": origin_main}


def require_network_medium(manifest: dict[str, Any]) -> str:
    execution = manifest["execution"]
    if os.environ.get(execution["network_access_medium_env"]) != execution["network_access_medium"]:
        raise BehavioralPilotError("必须通过 FORGE_NETWORK_ACCESS_MEDIUM=wifi 确认当前网络介质")
    return execution["network_access_medium"]


def require_zero_managed_containers() -> None:
    try:
        v1_runner.require_zero_managed_containers()
    except v1_runner.PilotError as exc:
        raise BehavioralPilotError(str(exc)) from exc


def _pair_manifest(manifest: dict[str, Any], pair: dict[str, Any]) -> dict[str, Any]:
    parent_path = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-checkpoint-primary-canary-amendment-authorized.json"
    value = _load_json(parent_path)
    value["schema_version"] = "forge-checkpoint-behavioral-pair-runtime-2.0.0"
    value["document_type"] = "forge_checkpoint_behavioral_pair_runtime"
    value["scope"]["pilot_collection_authorized"] = True
    value["continuation"].update(copy.deepcopy(manifest["continuation"]))
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
        "classified_arm_outcome_continues_other_arm": True,
        "historical_pairs_pooled": False,
    }
    return value


class _AsyncioProxy:
    def __init__(self, runner: asyncio.Runner):
        self._runner = runner

    def run(self, coroutine: Any) -> Any:
        return self._runner.run(coroutine)

    def __getattr__(self, name: str) -> Any:
        return getattr(asyncio, name)


def _request_evidence(manifest: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    started = [event for event in events if event["event"] == "model.request_started"]
    completed = [event for event in events if event["event"] == "model.request_completed"]
    failed = [event for event in events if event["event"] in {"model.request_failed", "model.request_cancelled"}]
    provider = manifest["provider"]
    if len(started) > manifest["continuation"]["maximum_requests_per_arm"]:
        raise BehavioralPilotError("arm 超过模型请求上限")
    if any(
        event["payload"].get("configured_model") != provider["model"]
        or event["payload"].get("observed_endpoint") != provider["endpoint"]
        or event["payload"].get("request_timeout_seconds") != provider["request_timeout_seconds"]
        or event["payload"].get("provider_max_retries") != 0
        for event in started
    ):
        raise BehavioralPilotError("arm 请求 policy identity 发生漂移")
    if any(event["payload"].get("actual_model") != provider["model"] for event in completed):
        raise BehavioralPilotError("arm actual model identity 发生漂移")
    tokens = v1_runner._recorded_tokens(events)
    if tokens > manifest["continuation"]["maximum_recorded_tokens_per_arm"]:
        raise BehavioralPilotError("arm 超过 recorded-token 上限")
    if len(started) != len(completed) + len(failed):
        raise BehavioralPilotError("arm 模型请求 started/terminal 不闭合")
    return {
        "started": started,
        "completed": completed,
        "failed": failed,
        "recorded_tokens": tokens,
    }


def _endpoint_censored_arm(events: list[dict[str, Any]], request: dict[str, Any]) -> bool:
    failed = request["failed"]
    if len(failed) != 1 or failed[0]["event"] != "model.request_failed":
        return False
    payload = failed[0]["payload"]
    classifications = [event for event in events if event["event"] == "failure.recorded" and event["payload"].get("primary") is True]
    matching = [event for event in classifications if event["payload"].get("domain") == "model_endpoint" and event["payload"].get("classification") == "timeout" and "retry_exhausted" in event["payload"].get("secondary_classifications", [])]
    return payload.get("classification") == "timeout" and payload.get("retry_exhausted") is True and payload.get("status_code") is None and len(classifications) == 1 and len(matching) == 1


def _verification_outcome(events: list[dict[str, Any]]) -> dict[str, Any]:
    submit_started = sum(event["event"] == "submit.started" for event in events)
    replay_started = sum(event["event"] == "replay.started" for event in events)
    submit_passed = any(event["event"] == "submit.completed" and event["payload"].get("status") == "passed" for event in events)
    replay_passed = any(event["event"] == "replay.completed" and event["payload"].get("status") == "passed" for event in events)
    if submit_passed and replay_passed:
        status = "passed"
    elif submit_started:
        status = "failed"
    else:
        status = "not_attempted"
    return {
        "status": status,
        "submit_attempts": submit_started,
        "clean_replay_attempts": replay_started,
    }


def classify_arm_terminal(
    manifest: dict[str, Any],
    *,
    arm: str,
    ledger: Any,
    error: Exception,
) -> dict[str, Any]:
    events = ledger.read()
    if not events:
        raise BehavioralPilotError(f"{arm} arm 缺少 ledger evidence") from error
    request = _request_evidence(manifest, events)
    verification = _verification_outcome(events)
    metrics = v1_runner._arm_metrics(events)
    metrics["recorded_tokens"] = request["recorded_tokens"]
    if _endpoint_censored_arm(events, request):
        infrastructure = "endpoint_censored"
        behavior = "not_observed"
    else:
        if request["failed"]:
            if type(error).__name__ in {"TimeoutError", "CancelledError"} and all(event["event"] == "model.request_cancelled" for event in request["failed"]):
                infrastructure = "valid"
                behavior = "work_wall_clock_limit"
            else:
                raise BehavioralPilotError(f"{arm} arm 存在未分类的模型请求失败") from error
        else:
            infrastructure = "valid"
            error_name = type(error).__name__
            if error_name == "GraphRecursionError":
                behavior = "graph_step_limit"
            elif error_name == "TimeoutError":
                behavior = "work_wall_clock_limit"
            elif verification["status"] == "failed":
                behavior = "verification_failed"
            elif verification["status"] == "not_attempted":
                behavior = "no_submit"
            else:
                raise BehavioralPilotError(f"{arm} arm 异常无法归入冻结行为 taxonomy") from error
    ledger.append(
        "experiment.completed",
        {
            "status": "endpoint_censored" if infrastructure == "endpoint_censored" else "model_behavior_outcome",
            "model_behavior": behavior,
            "verification_outcome": verification["status"],
        },
    )
    terminal_events = ledger.read()
    result = {
        "arm": arm,
        "status": "observed",
        "infrastructure": {"status": infrastructure},
        "model_behavior": {
            "status": behavior,
            "terminal_error_class": type(error).__name__,
        },
        "verification_outcome": verification,
        "physical_attempt_id": ledger.physical_attempt_id,
        "model_requests": metrics["model_requests"],
        "recorded_tokens": metrics["recorded_tokens"],
        "actual_model": manifest["provider"]["model"] if request["completed"] else None,
        "metrics": metrics,
        "ledger_head_sha256": terminal_events[-1]["event_sha256"],
    }
    return result


def _passed_arm(result: dict[str, Any], ledger: Any) -> dict[str, Any]:
    events = ledger.read()
    metrics = v1_runner._arm_metrics(events)
    return {
        **result,
        "status": "observed",
        "infrastructure": {"status": "valid"},
        "model_behavior": {"status": "completed", "terminal_error_class": None},
        "verification_outcome": {
            "status": "passed",
            "submit_attempts": metrics["submit_attempts"],
            "clean_replay_attempts": metrics["clean_replay_attempts"],
        },
        "metrics": metrics,
    }


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
        "run_arm_continuation": primary.run_arm_continuation,
    }

    def validate(value: Any) -> dict[str, Any]:
        if value != pair_manifest:
            raise BehavioralPilotError("v2 pair runtime manifest 发生漂移")
        return value

    def verify(value: dict[str, Any], repo_root: Path = REPO_ROOT) -> None:
        validate(value)
        protocol.verify_frozen_components(manifest, repo_root)

    async def capture_arm(*args: Any, **kwargs: Any) -> dict[str, Any]:
        ledger = kwargs["ledger"]
        arm = kwargs["arm"]
        try:
            result = await original["run_arm_continuation"](*args, **kwargs)
        except Exception as exc:
            return classify_arm_terminal(manifest, arm=arm, ledger=ledger, error=exc)
        return _passed_arm(result, ledger)

    primary.validate_manifest = validate
    primary.verify_frozen_artifacts = verify
    primary.require_release_identity = lambda value, repo_root=REPO_ROOT: require_release_identity(manifest, repo_root)
    primary.require_passed_reachability = lambda *_args, **_kwargs: {
        "recorded_tokens": 0,
        "inherited_reachability": False,
    }
    primary.PAIR_MARKER = PAIR_MARKER
    primary.asyncio = _AsyncioProxy(async_runner)
    primary.run_arm_continuation = capture_arm
    try:
        yield
    finally:
        for name, value in original.items():
            setattr(primary, name, value)


def _pair_outcome(
    manifest: dict[str, Any],
    pair: dict[str, Any],
    pair_manifest: dict[str, Any],
    pair_dir: Path,
    report: dict[str, Any],
) -> dict[str, Any]:
    if report.get("complete_pair") is not True or report.get("cleanup_succeeded") is not True or report.get("arm_order") != pair["arm_order"]:
        raise BehavioralPilotError("v2 pair 未形成双臂尝试与 cleanup 终态")
    arms = report.get("arms")
    if not isinstance(arms, list) or {item.get("arm") for item in arms} != {
        "baseline",
        "treatment",
    }:
        raise BehavioralPilotError("v2 pair 缺少唯一双臂结果")
    arm_map = {item["arm"]: item for item in arms}
    taxonomy = manifest["terminal_taxonomy"]
    for arm, item in arm_map.items():
        if (
            item.get("infrastructure", {}).get("status") not in taxonomy["infrastructure"]
            or item.get("model_behavior", {}).get("status") not in taxonomy["model_behavior"]
            or item.get("verification_outcome", {}).get("status") not in taxonomy["verification_outcome"]
        ):
            raise BehavioralPilotError(f"{arm} arm 三层终态不在冻结 taxonomy")
        if item.get("recorded_tokens") != item.get("metrics", {}).get("recorded_tokens") or item["recorded_tokens"] > manifest["continuation"]["maximum_recorded_tokens_per_arm"]:
            raise BehavioralPilotError(f"{arm} arm token evidence 无效")
    coordinator = recovery_runner.coordinator_terminal_from_copy(pair_dir)
    require_zero_managed_containers()
    eligible = all(item["infrastructure"]["status"] == "valid" for item in arm_map.values())
    repair_success = {arm: item["verification_outcome"]["status"] == "passed" for arm, item in arm_map.items()}
    return {
        "schema_version": "forge-checkpoint-behavioral-pair-outcome-2.0.0",
        "document_type": "forge_checkpoint_behavioral_pair_outcome",
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "pair_manifest_sha256": protocol.canonical_sha256(pair_manifest),
        "pair_id": pair["pair_id"],
        "order": pair["order"],
        "arm_order": pair["arm_order"],
        "status": "observed" if eligible else "observed_with_endpoint_censoring",
        "arms": arm_map,
        "recorded_tokens": sum(item["recorded_tokens"] for item in arm_map.values()),
        "primary_mechanism_eligible": eligible,
        "repair_success": repair_success,
        "paired_repair_conversion_delta": int(repair_success["treatment"]) - int(repair_success["baseline"]) if eligible else None,
        "itt_attrition_contribution": 1,
        "coordinator": coordinator,
        "completed_at": datetime.now(UTC).isoformat(),
    }


def execute_real_pair(
    manifest: dict[str, Any],
    pair: dict[str, Any],
    pair_dir: Path,
    async_runner: asyncio.Runner,
    model_factory: Callable[[dict[str, Any], str], Any] | None = None,
) -> dict[str, Any]:
    pair_manifest = _pair_manifest(manifest, pair)
    pair_manifest["execution"]["evidence_directory"] = str(pair_dir)
    with _adapt_parent_runner(manifest, pair_manifest, async_runner):
        with parent_adapter.build_layout.use_windows_safe_build_layout(primary):
            report = primary.run_controlled_pair(
                pair_manifest,
                output_dir=pair_dir,
                repo_root=REPO_ROOT,
                model_factory=model_factory,
            )
    return _pair_outcome(manifest, pair, pair_manifest, pair_dir, report)


def _claim_batch_marker(path: Path, digest: str, revision: str) -> dict[str, Any]:
    if path.exists():
        marker = _load_json(path)
        if marker.get("manifest_sha256") != digest or marker.get("release_revision") != revision:
            raise BehavioralPilotError("已有 v2 batch marker identity 发生漂移")
        if marker.get("status") not in {"started", "passed"}:
            raise BehavioralPilotError("已有 v2 batch marker 已失败关闭")
        return marker
    marker = {
        "schema_version": "forge-checkpoint-behavioral-pilot-attempt-2.0.0",
        "document_type": "forge_checkpoint_behavioral_pilot_attempt",
        "manifest_sha256": digest,
        "release_revision": revision,
        "status": "started",
        "error_class": None,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _write_once(path, marker)
    return marker


def summarize(manifest: dict[str, Any], release: dict[str, str], outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [item for item in outcomes if item["primary_mechanism_eligible"]]
    censored = [item for item in outcomes if not item["primary_mechanism_eligible"]]
    behavior_counts = {arm: dict(sorted(Counter(item["arms"][arm]["model_behavior"]["status"] for item in outcomes).items())) for arm in ("baseline", "treatment")}
    repair_success = {arm: sum(item["repair_success"][arm] for item in eligible) for arm in ("baseline", "treatment")}
    metric_names = (
        "model_requests",
        "submit_attempts",
        "clean_replay_attempts",
        "recorded_tokens",
        "ledger_wall_clock_seconds",
    )
    efficiency = {arm: {name: [item["arms"][arm]["metrics"][name] for item in outcomes if item["arms"][arm]["infrastructure"]["status"] == "valid"] for name in metric_names} for arm in ("baseline", "treatment")}
    return {
        "schema_version": "forge-checkpoint-behavioral-pilot-report-2.0.0",
        "document_type": "forge_checkpoint_behavioral_pilot_report",
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "release_revision": release["revision"],
        "network_access_medium": manifest["execution"]["network_access_medium"],
        "status": "completed_with_endpoint_censoring" if censored else "completed",
        "itt_attrition": {
            "scheduled_pairs": protocol.PAIR_COUNT,
            "observed_pairs": len(outcomes),
            "attempted_arms": {arm: sum(arm in item["arms"] for item in outcomes) for arm in ("baseline", "treatment")},
            "endpoint_censored_pairs": len(censored),
            "endpoint_censored_pair_ids": [item["pair_id"] for item in censored],
        },
        "primary_mechanism": {
            "eligible_pairs": len(eligible),
            "pair_ids": [item["pair_id"] for item in eligible],
            "repair_success": repair_success,
            "paired_conversion_deltas": [item["paired_repair_conversion_delta"] for item in eligible],
            "model_behavior_counts": behavior_counts,
            "descriptive_only": True,
            "p_value_computed": False,
            "model_ranking_performed": False,
        },
        "conditional_efficiency": efficiency,
        "recorded_tokens": sum(item["recorded_tokens"] for item in outcomes),
        "maximum_recorded_tokens": manifest["budget"]["stage_maximum_recorded_tokens"],
        "historical_pairs_pooled": False,
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
    if output_dir.resolve(strict=False) != Path(manifest["execution"]["evidence_directory"]).resolve(strict=False):
        raise BehavioralPilotError("v2 evidence 必须写入冻结授权目录")
    release = require_release_identity(manifest, repo_root)
    require_network_medium(manifest)
    primary.require_compose_dood()
    protocol.verify_historical_evidence(manifest)
    require_zero_managed_containers()
    digest = protocol.canonical_sha256(manifest)
    marker_path = output_dir / BATCH_MARKER
    marker = _claim_batch_marker(marker_path, digest, release["revision"])
    report_path = output_dir / PILOT_REPORT
    if marker["status"] == "passed":
        report = _load_json(report_path)
        if report.get("manifest_sha256") != digest:
            raise BehavioralPilotError("已完成 v2 report identity 发生漂移")
        return report
    outcomes: list[dict[str, Any]] = []
    try:
        with asyncio.Runner() as async_runner:
            for pair in manifest["schedule"]:
                pair_dir = output_dir / "pairs" / pair["pair_id"]
                outcome_path = pair_dir / PAIR_OUTCOME
                if outcome_path.exists():
                    outcome = _load_json(outcome_path)
                    if outcome.get("manifest_sha256") != digest or outcome.get("pair_id") != pair["pair_id"] or outcome.get("status") not in {"observed", "observed_with_endpoint_censoring"}:
                        raise BehavioralPilotError("已有 v2 pair outcome identity 或终态无效")
                else:
                    if pair_dir.exists() and any(pair_dir.iterdir()):
                        raise BehavioralPilotError(f"{pair['pair_id']} 已开始但没有终态，禁止自动补跑")
                    require_zero_managed_containers()
                    outcome = execute_real_pair(manifest, pair, pair_dir, async_runner) if pair_executor is None else pair_executor(manifest, pair, pair_dir)
                    if outcome.get("status") not in {
                        "observed",
                        "observed_with_endpoint_censoring",
                    }:
                        raise BehavioralPilotError("pair 未形成冻结 v2 outcome")
                    _write_once(outcome_path, outcome)
                outcomes.append(outcome)
                if sum(item["recorded_tokens"] for item in outcomes) > manifest["budget"]["stage_maximum_recorded_tokens"]:
                    raise BehavioralPilotError("v2 超过 recorded-token 机械上限")
                require_zero_managed_containers()
        if len(outcomes) != protocol.PAIR_COUNT:
            raise BehavioralPilotError("v2 未形成 6 个预注册 pair 终态")
        report = summarize(manifest, release, outcomes)
        _write_once(report_path, report)
        marker.update(status="passed", error_class=None, updated_at=datetime.now(UTC).isoformat())
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
                raise BehavioralPilotError("v2 report identity 发生漂移")
        else:
            result = run_pilot(manifest, output_dir=args.output_dir)
    except (OSError, BehavioralPilotError, protocol.ProtocolError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
