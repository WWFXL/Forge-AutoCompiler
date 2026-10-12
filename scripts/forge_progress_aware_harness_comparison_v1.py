#!/usr/bin/env python3
"""Issue #433：进展感知结构化 Harness H0/H1 配对比较 v1。"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_PATH.parent)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_agent_continuation_qualification_v2 as base  # noqa: E402

from deerflow.compile import agent_workflow_runtime_v4 as runtime_v4  # noqa: E402

IDENTITY = "cpp-progress-aware-harness-comparison-v1"
TRACKING_ISSUE = 433
BRANCH = "yiwei/433-h0-h1-provider-comparison"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests" / f"{IDENTITY}.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-progress-aware-harness-comparison-v1.schema.json"
PREREGISTRATION_PATH = REPO_ROOT / "benchmarks/preregistrations" / f"{IDENTITY}.md"
SPEC_PATH = REPO_ROOT / "docs/superpowers/specs/2026-10-13-progress-aware-harness-comparison-v1-design.md"
PLAN_PATH = REPO_ROOT / "docs/superpowers/plans/2026-10-13-progress-aware-harness-comparison-v1.md"
REPORT_JSON_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.json"
REPORT_MD_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.md"
COMPONENT_PATHS = (
    "scripts/forge_progress_aware_harness_comparison_v1.py",
    "scripts/forge_agent_continuation_qualification_v2.py",
    "scripts/forge_checkpoint_archive.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v2.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v3.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v4.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_schemas.py",
    "backend/packages/harness/deerflow/compile/candidate_verifier.py",
    "backend/packages/harness/deerflow/compile/external_evaluator_v4.py",
    "backend/packages/harness/deerflow/compile/operations.py",
    "backend/packages/harness/deerflow/tools/bound_compile_tools.py",
    "backend/tests/test_forge_progress_aware_harness_comparison_v1.py",
    "benchmarks/schemas/forge-progress-aware-harness-comparison-v1.schema.json",
    "benchmarks/preregistrations/cpp-progress-aware-harness-comparison-v1.md",
    "docs/superpowers/specs/2026-10-13-progress-aware-harness-comparison-v1-design.md",
    "docs/superpowers/plans/2026-10-13-progress-aware-harness-comparison-v1.md",
)
TREATMENTS = ("h0_runtime_v3", "h1_runtime_v4")
ALLOWED_TERMINALS = {
    "strict_success",
    "evaluated_failure",
    "no_candidate",
    "budget_exhausted",
    "timeout",
    "arm_error",
}

QualificationError = base.QualificationError
_BASE_PREFLIGHT = base.preflight
_BASE_PREPARE_SESSION = base._prepare_restored_session
_BASE_NODE_INPUT = base._node_input
_BASE_EXPERIMENT_POLICY = base._experiment_policy
_BASE_RUN_V3 = base.runtime_v3.run_agent_workflow_node_v3
_ACTIVE_TREATMENT = "reference"


def _manifest() -> dict[str, Any]:
    return base._load_json(MANIFEST_PATH)


def _activate_base() -> None:
    base.IDENTITY = IDENTITY
    base.TRACKING_ISSUE = TRACKING_ISSUE
    base.BRANCH = BRANCH
    base.SCRIPT_PATH = SCRIPT_PATH
    base.MANIFEST_PATH = MANIFEST_PATH
    base.SCHEMA_PATH = SCHEMA_PATH
    base.PREREGISTRATION_PATH = PREREGISTRATION_PATH
    base.SPEC_PATH = SPEC_PATH
    base.PLAN_PATH = PLAN_PATH
    base.REPORT_JSON_PATH = REPORT_JSON_PATH
    base.REPORT_MD_PATH = REPORT_MD_PATH
    base.COMPONENT_PATHS = COMPONENT_PATHS
    base.validate_manifest = validate_manifest
    base.preflight = preflight
    base._prepare_restored_session = _prepare_restored_session
    base._node_input = _node_input
    base._experiment_policy = _experiment_policy
    base.runtime_v3.run_agent_workflow_node_v3 = _run_node


def _validate_inventory(root: Path, expected: str, label: str) -> None:
    inventory = base._load_json(root / "inventory.json")
    files = inventory.get("files")
    if not isinstance(files, list) or inventory.get("canonical_sha256") != expected or base._canonical_sha256(files) != expected:
        raise QualificationError(f"{label} inventory 漂移")
    for item in files:
        path = root / item["path"]
        if not path.is_file() or path.stat().st_size != item["size"] or base._file_sha256(path) != item["sha256"]:
            raise QualificationError(f"{label} evidence 文件漂移: {item['path']}")


def _source_archive(manifest: dict[str, Any], task: dict[str, Any]) -> Path:
    source = manifest["source_archives"][task["task_id"]]
    checkpoint, _message, _budget = base._checkpoint_payload(source["checkpoint_state_id"])
    if (
        checkpoint["checkpoint_sha256"] != source["checkpoint_sha256"]
        or checkpoint["workspace_snapshot_sha256"] != source["sha256"]
        or checkpoint["source"]["repository_url"] != task["repository_url"]
        or checkpoint["source"]["commit_sha"] != task["commit_sha"]
    ):
        raise QualificationError(f"离线源码 identity 漂移: {task['task_id']}")
    path = base.PARENT_STATE_ROOT / source["checkpoint_state_id"] / "checkpoint/workspace.tar.gz"
    if not path.is_file() or base._file_sha256(path) != source["sha256"]:
        raise QualificationError(f"离线源码 archive 漂移: {task['task_id']}")
    return path


def _treatment_order(block_sequence: int) -> tuple[str, str]:
    return TREATMENTS if block_sequence % 2 == 1 else tuple(reversed(TREATMENTS))


def validate_manifest(manifest: dict[str, Any], *, require_components: bool = True) -> dict[str, Any]:
    _activate_base()
    if manifest.get("identity") != IDENTITY or manifest.get("issue") != TRACKING_ISSUE or manifest.get("branch") != BRANCH:
        raise QualificationError("manifest identity 漂移")
    expected_authorization = {
        "zero_provider_q0": True,
        "credential_read_after_q0": True,
        "provider_canary_formal": True,
        "formal_evidence_write": True,
        "historical_evidence_write": False,
        "replacement": False,
        "backfill": False,
        "controller_implementation": False,
        "jev_calls": False,
    }
    if manifest.get("authorization") != expected_authorization:
        raise QualificationError("授权边界漂移")
    base._validate_parent_inventory(manifest)
    for name, control in manifest.get("historical_controls", {}).items():
        if control.get("use_in_effect_estimate") is not False:
            raise QualificationError("历史 outcome 不得进入新 effect estimate")
        _validate_inventory(REPO_ROOT / control["evidence_root"], control["inventory_canonical_sha256"], name)
    tasks = manifest.get("tasks", [])
    if len(tasks) != 9 or Counter(task.get("build_system") for task in tasks) != Counter({"cmake": 3, "make": 3, "autotools": 3}):
        raise QualificationError("task 构建系统分层无效")
    if len({task.get("task_id") for task in tasks}) != 9 or set(manifest.get("source_archives", {})) != {task["task_id"] for task in tasks}:
        raise QualificationError("task/source archive identity 无效")
    depths = Counter(int(task["checkpoint_state_id"].rsplit("-", 1)[-1]) for task in tasks)
    if depths != Counter({1: 3, 2: 3, 3: 3}):
        raise QualificationError("checkpoint depth 覆盖无效")
    for task in tasks:
        checkpoint, _message, _budget = base._checkpoint_payload(task["checkpoint_state_id"])
        if checkpoint["source"]["repository_url"] != task["repository_url"] or checkpoint["source"]["commit_sha"] != task["commit_sha"]:
            raise QualificationError(f"checkpoint source identity 漂移: {task['task_id']}")
        if checkpoint["image_id"] != manifest["environment"]["image_id"]:
            raise QualificationError(f"checkpoint image identity 漂移: {task['task_id']}")
        if not task.get("reference_commands") or task["reference_commands"][-1].get("role") != "artifact_stage":
            raise QualificationError(f"reference recipe 不闭合: {task['task_id']}")
        _source_archive(manifest, task)
    canaries = manifest.get("canary_checkpoints", [])
    if len(canaries) != 3 or {item["task_id"].split("-", 1)[0] for item in canaries} != {"cmake", "make", "autotools"}:
        raise QualificationError("canary 构建系统覆盖无效")
    schedule = manifest.get("formal_schedule", [])
    if [item.get("sequence") for item in schedule] != list(range(1, 28)):
        raise QualificationError("formal block sequence 无效")
    expected = Counter((task["task_id"], repetition) for task in tasks for repetition in (1, 2, 3))
    if Counter((item.get("task_id"), item.get("repetition")) for item in schedule) != expected:
        raise QualificationError("formal schedule 不满足 9 x 3 pairs")
    provider = manifest.get("provider", {})
    if provider.get("profile") != "deepseek-flash" or provider.get("model_max_retries") != 0 or provider.get("streaming") is not False or provider.get("thinking_enabled") is not False:
        raise QualificationError("Provider 合同漂移")
    budget = manifest.get("budget", {})
    if budget.get("provider_arms") != 60 or budget.get("total_provider_requests") != 1_440 or budget.get("total_recorded_tokens") != 18_000_000 or budget.get("total_provider_cost_usd_ceiling") != 21.6:
        raise QualificationError("总体 Provider 预算漂移")
    qualification = manifest.get("qualification", {})
    if qualification.get("formal_blocks") != 27 or qualification.get("formal_arms") != 54 or qualification.get("cluster_bootstrap_samples") != 10_000:
        raise QualificationError("资格分析合同漂移")
    components = manifest.get("components", {})
    if require_components:
        if set(components) != set(COMPONENT_PATHS):
            raise QualificationError("冻结组件集合无效")
        for relative, expected_sha256 in components.items():
            if base._file_sha256(REPO_ROOT / relative) != expected_sha256:
                raise QualificationError(f"冻结组件漂移: {relative}")
    return manifest


def preflight(manifest: dict[str, Any], *, phase: str) -> dict[str, Any]:
    _activate_base()
    return _BASE_PREFLIGHT(manifest, phase=phase)


def _bind_source_archive(manifest: dict[str, Any], task: dict[str, Any], session: Any) -> str:
    source = _source_archive(manifest, task)
    destination = Path(session.leadagent_repro_dir) / "source.tar"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    observed = base._file_sha256(destination)
    if observed != manifest["source_archives"][task["task_id"]]["sha256"]:
        raise QualificationError("Session replay source archive 漂移")
    session.replay_source_archive_sha256 = observed
    base.get_compile_services().manager.save_session(session)
    return observed


def _prepare_restored_session(
    manifest: dict[str, Any],
    task: dict[str, Any],
    state_id: str,
    *,
    thread_id: str,
    run_id: str,
) -> tuple[Any, dict[str, Any], dict[str, Any], dict[str, Any]]:
    session, checkpoint, message, parent_budget = _BASE_PREPARE_SESSION(
        manifest,
        task,
        state_id,
        thread_id=thread_id,
        run_id=run_id,
    )
    _bind_source_archive(manifest, task, session)
    return session, checkpoint, message, parent_budget


def _node_input(*args: Any, **kwargs: Any) -> Any:
    original = _BASE_NODE_INPUT(*args, **kwargs)
    manifest = args[0] if args else kwargs["manifest"]
    task = args[1] if len(args) > 1 else kwargs["task"]
    observation = dict(original.initial_observation)
    observation.update(
        {
            "harness_treatment": _ACTIVE_TREATMENT,
            "replay_source_archive_sha256": manifest["source_archives"][task["task_id"]]["sha256"],
        }
    )
    return replace(
        original,
        operation_policy_ref=f"issue-433-progress-aware-comparison-v1-{_ACTIVE_TREATMENT}",
        initial_observation=observation,
    )


def _experiment_policy(manifest: dict[str, Any], task: dict[str, Any], repetition: int) -> Any:
    return replace(_BASE_EXPERIMENT_POLICY(manifest, task, repetition), condition=_ACTIVE_TREATMENT)


async def _run_node(**kwargs: Any) -> Any:
    if _ACTIVE_TREATMENT == "h0_runtime_v3":
        return await _BASE_RUN_V3(**kwargs)
    if _ACTIVE_TREATMENT == "h1_runtime_v4":
        return await runtime_v4.run_agent_workflow_node_v4(**kwargs)
    raise QualificationError(f"Provider arm treatment 无效: {_ACTIVE_TREATMENT}")


def _events(arm_dir: Path) -> list[dict[str, Any]]:
    paths = sorted((arm_dir / "session-evidence").rglob("events.jsonl"))
    if len(paths) != 1:
        return []
    return [json.loads(line) for line in paths[0].read_text(encoding="utf-8").splitlines() if line]


def _harness_metrics(arm_dir: Path, treatment: str, expected_source_sha256: str) -> dict[str, Any]:
    events = _events(arm_dir)
    event_types = Counter(event.get("event_type") for event in events)
    compactions = [event.get("payload", {}) for event in events if event.get("event_type") == "harness.context_compacted"]
    rejections = [event.get("payload", {}).get("reason") for event in events if event.get("event_type") == "harness.tool_rejected"]
    commands: list[dict[str, Any]] = []
    session_path = arm_dir / "session-evidence/session.json"
    source_bound = False
    script = ""
    if session_path.is_file():
        session = base._load_json(session_path)
        commands = list(session.get("commands", []))
        source_bound = session.get("replay_source_archive_sha256") == expected_source_sha256
        script_path = arm_dir / "session-evidence/repro/build.sh"
        script = script_path.read_text(encoding="utf-8") if script_path.is_file() else ""
    submit_started = next((index for index, event in enumerate(events) if event.get("event_type") == "candidate.submit_started"), None)
    requests_before_submit = None
    if submit_started is not None:
        requests_before_submit = sum(event.get("event_type") == "model.request_started" for event in events[:submit_started])
    return {
        "treatment": treatment,
        "progress_snapshots": event_types["harness.progress_snapshot"],
        "context_compactions": len(compactions),
        "effective_context_compactions": sum(item.get("retained_message_count", 0) < item.get("original_message_count", 0) for item in compactions),
        "ready_guard_rejections": rejections.count("candidate_ready_requires_submit"),
        "diagnostic_guard_rejections": rejections.count("diagnostic_no_progress_limit"),
        "diagnostic_commands": sum(command.get("role") == "diagnostic" for command in commands),
        "commands": len(commands),
        "candidate_submit_started": submit_started is not None,
        "model_requests_before_submit": requests_before_submit,
        "offline_source_bound": source_bound,
        "replay_archive_extract_present": "tar -xf" in script if script else None,
        "replay_git_fetch_present": "git fetch" in script if script else None,
    }


async def _run_assigned_arm(
    manifest: dict[str, Any],
    *,
    phase: str,
    sequence: int,
    pair_sequence: int,
    treatment: str,
    task: dict[str, Any],
    state_id: str,
    repetition: int,
    arm_dir: Path,
    release_revision: str,
) -> dict[str, Any]:
    global _ACTIVE_TREATMENT
    assignment = {
        "identity": IDENTITY,
        "phase": phase,
        "sequence": sequence,
        "pair_sequence": pair_sequence,
        "task_id": task["task_id"],
        "checkpoint_state_id": state_id,
        "repetition": repetition,
        "treatment": treatment,
    }
    assignment_path = arm_dir / "assignment.json"
    if assignment_path.exists():
        if base._load_json(assignment_path) != assignment:
            raise QualificationError("arm assignment 漂移")
    else:
        base._write_once_json(assignment_path, assignment)
    previous = _ACTIVE_TREATMENT
    _ACTIVE_TREATMENT = treatment
    try:
        result = await base._run_agent_arm(
            manifest,
            phase=phase,
            sequence=sequence,
            task=task,
            state_id=state_id,
            repetition=repetition,
            arm_dir=arm_dir,
            release_revision=release_revision,
        )
    finally:
        _ACTIVE_TREATMENT = previous
    metrics = _harness_metrics(arm_dir, treatment, manifest["source_archives"][task["task_id"]]["sha256"])
    base._write_once_json(arm_dir / "harness-metrics.json", metrics)
    return {**result, "pair_sequence": pair_sequence, "treatment": treatment, "harness_metrics": metrics}


def _load_completed_arm(arm_dir: Path, expected: dict[str, Any]) -> dict[str, Any]:
    assignment = base._load_json(arm_dir / "assignment.json")
    if any(assignment.get(key) != value for key, value in expected.items()):
        raise QualificationError("completed arm assignment 漂移")
    result = base._load_json(arm_dir / "result.json")
    metrics = base._load_json(arm_dir / "harness-metrics.json")
    return {**result, "pair_sequence": assignment["pair_sequence"], "treatment": assignment["treatment"], "harness_metrics": metrics}


def _totals(outcomes: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "provider_requests": sum(item["token_accounting"]["requests_started"] for item in outcomes),
        "recorded_tokens": sum((item["token_accounting"]["recorded_tokens"] or 0) for item in outcomes),
        "provider_cost_microusd": sum(item["budget"]["delta"]["provider_cost_microusd"] for item in outcomes if item.get("budget")),
    }


def _check_total_budget(manifest: dict[str, Any], outcomes: list[dict[str, Any]]) -> None:
    totals = _totals(outcomes)
    budget = manifest["budget"]
    if totals["provider_requests"] > budget["total_provider_requests"] or totals["recorded_tokens"] > budget["total_recorded_tokens"] or totals["provider_cost_microusd"] > round(budget["total_provider_cost_usd_ceiling"] * 1_000_000):
        raise QualificationError("Provider 批次总预算上限被突破")


def _arm_complete(item: dict[str, Any]) -> bool:
    return bool(
        item.get("terminal_classification") in ALLOWED_TERMINALS
        and item.get("budget") is not None
        and item["budget"].get("complete") is True
        and item["budget"].get("conserved") is True
        and item.get("post_action_observation") is not None
        and item.get("cleanup_succeeded") is True
        and item.get("error_class") is None
        and item.get("harness_metrics", {}).get("offline_source_bound") is True
    )


def execute_q0(manifest: dict[str, Any]) -> dict[str, Any]:
    global _ACTIVE_TREATMENT
    _activate_base()
    previous = _ACTIVE_TREATMENT
    _ACTIVE_TREATMENT = "reference"
    try:
        return base.execute_q0(manifest)
    finally:
        _ACTIVE_TREATMENT = previous


def execute_q1(manifest: dict[str, Any]) -> dict[str, Any]:
    _activate_base()
    preflight_result = preflight(manifest, phase="q1")
    root = REPO_ROOT / manifest["evidence_root"]
    base._require_phase_passed(root, "q0", preflight_result["manifest_sha256"], preflight_result["release_revision"])
    base._provider_preflight(manifest)
    marker_path = base._phase_marker(root, "q1")
    base._start_marker(marker_path, preflight_result["manifest_sha256"], preflight_result["release_revision"])
    outcomes: list[dict[str, Any]] = []
    try:
        for pair_sequence, canary in enumerate(manifest["canary_checkpoints"], 1):
            task = base._task(manifest, canary["task_id"])
            for offset, treatment in enumerate(_treatment_order(pair_sequence), 1):
                sequence = (pair_sequence - 1) * 2 + offset
                arm_dir = root / "q1/arms" / f"{sequence:02d}-{task['task_id']}-{treatment}"
                outcome = asyncio.run(
                    _run_assigned_arm(
                        manifest,
                        phase="q1",
                        sequence=sequence,
                        pair_sequence=pair_sequence,
                        treatment=treatment,
                        task=task,
                        state_id=canary["checkpoint_state_id"],
                        repetition=1,
                        arm_dir=arm_dir,
                        release_revision=preflight_result["release_revision"],
                    )
                )
                outcomes.append(outcome)
                _check_total_budget(manifest, outcomes)
        passed = len(outcomes) == 6 and all(_arm_complete(item) for item in outcomes)
        result = {
            "phase": "q1",
            "manifest_sha256": preflight_result["manifest_sha256"],
            "release_revision": preflight_result["release_revision"],
            "outcomes": outcomes,
            "strict_success": {treatment: sum(item["strict_success"] for item in outcomes if item["treatment"] == treatment) for treatment in TREATMENTS},
            "passed": passed,
            "completed_at": base._now(),
        }
        base._write_once_json(root / "q1/result.json", result)
        base._finish_marker(marker_path, "passed" if passed else "failed")
        if not passed:
            raise QualificationError("Q1 配对 canary 未通过工程闭合门禁")
        return result
    except BaseException as exc:
        if not (root / "q1/result.json").exists():
            base._write_once_json(
                root / "q1/result.json",
                {
                    "phase": "q1",
                    "manifest_sha256": preflight_result["manifest_sha256"],
                    "release_revision": preflight_result["release_revision"],
                    "outcomes": outcomes,
                    "passed": False,
                    "error_class": type(exc).__name__,
                    "completed_at": base._now(),
                },
            )
        if base._load_json(marker_path).get("status") == "started":
            base._finish_marker(marker_path, "failed", type(exc).__name__)
        raise


def _bootstrap_lower_bound(manifest: dict[str, Any], outcomes: list[dict[str, Any]]) -> float:
    by_task_treatment: dict[tuple[str, str], list[float]] = defaultdict(list)
    for item in outcomes:
        by_task_treatment[(item["task_id"], item["treatment"])].append(float(item["strict_success"]))
    task_effects = []
    for task in manifest["tasks"]:
        task_id = task["task_id"]
        h0 = by_task_treatment[(task_id, TREATMENTS[0])]
        h1 = by_task_treatment[(task_id, TREATMENTS[1])]
        if len(h0) != 3 or len(h1) != 3:
            return -1.0
        task_effects.append(sum(h1) / 3 - sum(h0) / 3)
    rng = random.Random(manifest["qualification"]["cluster_bootstrap_seed"])
    samples = []
    for _ in range(manifest["qualification"]["cluster_bootstrap_samples"]):
        samples.append(sum(rng.choice(task_effects) for _task in task_effects) / len(task_effects))
    samples.sort()
    return samples[int(0.05 * len(samples))]


def _formal_qualification(manifest: dict[str, Any], outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    by_treatment = {treatment: [item for item in outcomes if item.get("treatment") == treatment] for treatment in TREATMENTS}
    pair_counts = Counter((item.get("pair_sequence"), item.get("treatment")) for item in outcomes)
    hard_gates = {
        "classified_terminal": len(outcomes) == 54 and all(item.get("terminal_classification") in ALLOWED_TERMINALS for item in outcomes),
        "paired_schedule_complete": len(pair_counts) == 54 and all(pair_counts[(pair, treatment)] == 1 for pair in range(1, 28) for treatment in TREATMENTS),
        "cost_and_budget_complete": len(outcomes) == 54 and all(item.get("budget") is not None and item["budget"].get("complete") is True and item["budget"].get("conserved") is True for item in outcomes),
        "parent_checkpoint_binding": len(outcomes) == 54 and all(isinstance(item.get("checkpoint_sha256"), str) and len(item["checkpoint_sha256"]) == 64 for item in outcomes),
        "offline_source_binding": len(outcomes) == 54 and all(item.get("harness_metrics", {}).get("offline_source_bound") is True for item in outcomes),
        "post_action_observation": len(outcomes) == 54 and all(item.get("post_action_observation") is not None for item in outcomes),
        "cleanup": len(outcomes) == 54 and all(item.get("cleanup_succeeded") is True for item in outcomes),
        "no_infrastructure_error": len(outcomes) == 54 and all(item.get("error_class") is None for item in outcomes),
    }
    strict = {treatment: sum(item.get("strict_success") is True for item in rows) for treatment, rows in by_treatment.items()}
    rates = {treatment: strict[treatment] / 27 if len(by_treatment[treatment]) == 27 else 0.0 for treatment in TREATMENTS}
    difference = rates[TREATMENTS[1]] - rates[TREATMENTS[0]]
    lower_bound = _bootstrap_lower_bound(manifest, outcomes)
    costs = {treatment: sum(item["budget"]["delta"]["provider_cost_microusd"] for item in rows if item.get("budget")) for treatment, rows in by_treatment.items()}
    cost_reduction = 1 - costs[TREATMENTS[1]] / costs[TREATMENTS[0]] if costs[TREATMENTS[0]] > 0 else 0.0
    cost_increase = costs[TREATMENTS[1]] / costs[TREATMENTS[0]] - 1 if costs[TREATMENTS[0]] > 0 else float("inf")
    system_strict: dict[str, dict[str, int]] = {}
    for system in ("cmake", "make", "autotools"):
        system_strict[system] = {treatment: sum(item.get("strict_success") is True and item.get("build_system") == system for item in by_treatment[treatment]) for treatment in TREATMENTS}
    no_system_regression = all(values[TREATMENTS[1]] >= values[TREATMENTS[0]] for values in system_strict.values())
    q = manifest["qualification"]
    primary_path = lower_bound >= q["strict_success_noninferiority_margin"] and cost_reduction >= q["minimum_cost_reduction"] and no_system_regression
    alternative_path = difference >= q["alternative_minimum_success_improvement"] and lower_bound > 0 and cost_increase <= q["alternative_maximum_cost_increase"] and no_system_regression
    behavior_gates = {
        "primary_noninferiority_and_cost": primary_path,
        "alternative_success_improvement": alternative_path,
        "system_non_regression": no_system_regression,
    }
    passed = all(hard_gates.values()) and (primary_path or alternative_path)
    return {
        "hard_gates": hard_gates,
        "behavior_gates": behavior_gates,
        "strict_success": strict,
        "strict_success_rates": rates,
        "strict_success_difference_h1_minus_h0": difference,
        "cluster_bootstrap_one_sided_95_lower_bound": lower_bound,
        "provider_cost_microusd": costs,
        "provider_cost_reduction_h1_vs_h0": cost_reduction,
        "provider_cost_increase_h1_vs_h0": cost_increase,
        "strict_success_by_system": system_strict,
        "passed": passed,
        "decision": q["pass_decision"] if passed else q["fail_decision"],
    }


def execute_q2(manifest: dict[str, Any]) -> dict[str, Any]:
    _activate_base()
    preflight_result = preflight(manifest, phase="q2")
    root = REPO_ROOT / manifest["evidence_root"]
    base._require_phase_passed(root, "q0", preflight_result["manifest_sha256"], preflight_result["release_revision"])
    q1 = base._require_phase_passed(root, "q1", preflight_result["manifest_sha256"], preflight_result["release_revision"])
    base._provider_preflight(manifest)
    marker_path = base._phase_marker(root, "q2")
    if not marker_path.exists():
        base._start_marker(marker_path, preflight_result["manifest_sha256"], preflight_result["release_revision"])
    if base._load_json(marker_path).get("status") != "started":
        raise QualificationError("Q2 已封口")
    outcomes: list[dict[str, Any]] = []
    try:
        for block in manifest["formal_schedule"]:
            task = base._task(manifest, block["task_id"])
            for offset, treatment in enumerate(_treatment_order(block["sequence"]), 1):
                sequence = (block["sequence"] - 1) * 2 + offset
                arm_dir = root / "q2/arms" / f"{sequence:02d}-p{block['sequence']:02d}-{task['task_id']}-r{block['repetition']}-{treatment}"
                expected = {
                    "phase": "q2",
                    "sequence": sequence,
                    "pair_sequence": block["sequence"],
                    "task_id": task["task_id"],
                    "checkpoint_state_id": task["checkpoint_state_id"],
                    "repetition": block["repetition"],
                    "treatment": treatment,
                }
                if (arm_dir / "result.json").is_file():
                    outcomes.append(_load_completed_arm(arm_dir, expected))
                    continue
                if (arm_dir / "attempt.json").exists():
                    raise QualificationError("Q2 存在 started 但无 result 的 arm，禁止 retry")
                outcomes.append(
                    asyncio.run(
                        _run_assigned_arm(
                            manifest,
                            phase="q2",
                            sequence=sequence,
                            pair_sequence=block["sequence"],
                            treatment=treatment,
                            task=task,
                            state_id=task["checkpoint_state_id"],
                            repetition=block["repetition"],
                            arm_dir=arm_dir,
                            release_revision=preflight_result["release_revision"],
                        )
                    )
                )
                _check_total_budget(manifest, [*q1["outcomes"], *outcomes])
        qualification = _formal_qualification(manifest, outcomes)
        result = {
            "phase": "q2",
            "manifest_sha256": preflight_result["manifest_sha256"],
            "release_revision": preflight_result["release_revision"],
            "outcomes": outcomes,
            "qualification": qualification,
            "passed": all(qualification["hard_gates"].values()),
            "completed_at": base._now(),
        }
        base._write_once_json(root / "q2/result.json", result)
        base._finish_marker(marker_path, "passed" if result["passed"] else "failed")
        return result
    except BaseException as exc:
        if base._load_json(marker_path).get("status") == "started":
            base._finish_marker(marker_path, "failed", type(exc).__name__)
        if not (root / "q2/result.json").exists():
            base._write_once_json(
                root / "q2/result.json",
                {
                    "phase": "q2",
                    "manifest_sha256": preflight_result["manifest_sha256"],
                    "release_revision": preflight_result["release_revision"],
                    "outcomes": outcomes,
                    "qualification": _formal_qualification(manifest, outcomes),
                    "passed": False,
                    "error_class": type(exc).__name__,
                    "completed_at": base._now(),
                },
            )
        raise


def audit(manifest: dict[str, Any], *, seal: bool = False) -> dict[str, Any]:
    validate_manifest(manifest)
    root = REPO_ROOT / manifest["evidence_root"]
    identity = base._load_json(root / "identity.json")
    q0 = base._load_json(root / "q0/result.json")
    q1 = base._load_json(root / "q1/result.json")
    q2 = base._load_json(root / "q2/result.json")
    expected_manifest_sha256 = base._canonical_sha256(manifest)
    phase_hashes = {item.get("manifest_sha256") for item in (identity, q0, q1, q2)}
    releases = {item.get("release_revision") for item in (identity, q0, q1, q2)}
    valid = (
        phase_hashes == {expected_manifest_sha256}
        and len(releases) == 1
        and q0.get("passed") is True
        and q1.get("passed") is True
        and len(q2.get("outcomes", [])) == 54
        and _formal_qualification(manifest, q2["outcomes"]) == q2.get("qualification")
    )
    base._require_zero_managed_resources()
    inventory_path = root / "inventory.json"
    inventory = base._inventory(root)
    if seal:
        if inventory_path.exists():
            raise QualificationError("inventory 已封口")
        base._write_once_json(inventory_path, inventory)
    elif inventory_path.exists():
        recorded = base._load_json(inventory_path)
        valid = valid and recorded == inventory
        inventory = recorded
    return {
        "identity": IDENTITY,
        "valid": valid,
        "manifest_sha256": expected_manifest_sha256,
        "release_revision": next(iter(releases)) if len(releases) == 1 else None,
        "q0_passed": q0.get("passed"),
        "q1_passed": q1.get("passed"),
        "decision": q2.get("qualification", {}).get("decision"),
        "inventory": inventory,
        "zero_managed_resources": True,
    }


def _treatment_summary(outcomes: list[dict[str, Any]], treatment: str) -> dict[str, Any]:
    rows = [item for item in outcomes if item["treatment"] == treatment]
    return {
        "arms": len(rows),
        "strict_success": sum(item["strict_success"] for item in rows),
        "provider_requests": sum(item["token_accounting"]["requests_started"] for item in rows),
        "input_tokens": sum(item["token_accounting"]["input_tokens"] or 0 for item in rows),
        "output_tokens": sum(item["token_accounting"]["output_tokens"] or 0 for item in rows),
        "recorded_tokens": sum(item["token_accounting"]["recorded_tokens"] or 0 for item in rows),
        "provider_cost_microusd": sum(item["budget"]["delta"]["provider_cost_microusd"] for item in rows if item.get("budget")),
        "wall_clock_milliseconds": sum(item["duration_milliseconds"] for item in rows),
        "budget_exhausted": sum(item["terminal_classification"] == "budget_exhausted" for item in rows),
        "no_candidate": sum(item["terminal_classification"] == "no_candidate" for item in rows),
        "diagnostic_commands": sum(item["harness_metrics"]["diagnostic_commands"] for item in rows),
        "ready_guard_rejections": sum(item["harness_metrics"]["ready_guard_rejections"] for item in rows),
        "effective_context_compactions": sum(item["harness_metrics"]["effective_context_compactions"] for item in rows),
    }


def write_report(manifest: dict[str, Any]) -> dict[str, Any]:
    root = REPO_ROOT / manifest["evidence_root"]
    audit_result = audit(manifest)
    if not audit_result["valid"]:
        raise QualificationError("evidence audit 未通过")
    q0 = base._load_json(root / "q0/result.json")
    q1 = base._load_json(root / "q1/result.json")
    q2 = base._load_json(root / "q2/result.json")
    summaries = {treatment: _treatment_summary(q2["outcomes"], treatment) for treatment in TREATMENTS}
    report = {
        "identity": IDENTITY,
        "status": "completed",
        "decision": q2["qualification"]["decision"],
        "q0": {"strict_success": q0["strict_success"], "cases": len(q0["outcomes"])},
        "q1": {"arms": len(q1["outcomes"]), "strict_success": q1["strict_success"]},
        "q2": {"treatments": summaries, "qualification": q2["qualification"]},
        "audit": audit_result,
        "interpretation_boundary": "只评价冻结受控 checkpoint、deepseek-flash 和固定预算下 Runtime v4 相对 Runtime v3 的 Harness 整体处理效应；不评价 Jev、动态预算、自然失败、开放世界或通用 Agent Harness。",
        "completed_at": base._now(),
    }
    REPORT_JSON_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    q = q2["qualification"]
    h0 = summaries[TREATMENTS[0]]
    h1 = summaries[TREATMENTS[1]]
    markdown = (
        "# 进展感知结构化 Harness H0/H1 配对比较 v1 结果\n\n"
        f"**决定：`{report['decision']}`。**\n\n"
        f"Q0 reference strict：`{q0['strict_success']}/9`；Q1 配对 canary：`{len(q1['outcomes'])}/6` arms 分类闭合。\n\n"
        "## 正式结果\n\n"
        f"- Strict success：H0 `{h0['strict_success']}/27`，H1 `{h1['strict_success']}/27`；\n"
        f"- H1-H0 strict difference：`{q['strict_success_difference_h1_minus_h0']:.3f}`，task-cluster 单侧 95% 下界 `{q['cluster_bootstrap_one_sided_95_lower_bound']:.3f}`；\n"
        f"- Provider cost：H0 `${h0['provider_cost_microusd'] / 1_000_000:.6f}`，H1 `${h1['provider_cost_microusd'] / 1_000_000:.6f}`，reduction `{q['provider_cost_reduction_h1_vs_h0']:.1%}`；\n"
        f"- Recorded tokens：H0 `{h0['recorded_tokens']}`，H1 `{h1['recorded_tokens']}`；\n"
        f"- Budget exhausted：H0 `{h0['budget_exhausted']}`，H1 `{h1['budget_exhausted']}`；no candidate：H0 `{h0['no_candidate']}`，H1 `{h1['no_candidate']}`；\n"
        f"- 分系统 strict：`{json.dumps(q['strict_success_by_system'], ensure_ascii=False, sort_keys=True)}`。\n\n"
        "## 门禁\n\n" + "\n".join(f"- `{name}`：{'通过' if value else '失败'}" for name, value in {**q["hard_gates"], **q["behavior_gates"]}.items()) + "\n\n## 解释边界\n\n" + report["interpretation_boundary"] + "\n\n## Evidence\n\n"
        f"- Manifest canonical SHA-256：`{audit_result['manifest_sha256']}`；\n"
        f"- Inventory canonical SHA-256：`{audit_result['inventory']['canonical_sha256']}`；\n"
        f"- Evidence files：`{audit_result['inventory']['file_count']}`，`{audit_result['inventory']['total_bytes']}` bytes。\n"
    )
    REPORT_MD_PATH.write_text(markdown, encoding="utf-8")
    return report


def _plan(manifest: dict[str, Any]) -> dict[str, Any]:
    validate_manifest(manifest, require_components=False)
    return {
        "identity": IDENTITY,
        "issue": TRACKING_ISSUE,
        "q0_cases": len(manifest["tasks"]),
        "canary_pairs": len(manifest["canary_checkpoints"]),
        "canary_arms": len(manifest["canary_checkpoints"]) * 2,
        "formal_pairs": len(manifest["formal_schedule"]),
        "formal_arms": len(manifest["formal_schedule"]) * 2,
        "provider_request_ceiling": manifest["budget"]["total_provider_requests"],
        "provider_token_ceiling": manifest["budget"]["total_recorded_tokens"],
        "provider_cost_usd_ceiling": manifest["budget"]["total_provider_cost_usd_ceiling"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("validate", "plan", "preflight-q0", "preflight-q1", "preflight-q2", "q0", "q1", "q2", "audit", "seal", "report"),
    )
    arguments = parser.parse_args()
    manifest = _manifest()
    if arguments.command == "validate":
        payload = {"valid": True, "manifest_sha256": base._canonical_sha256(validate_manifest(manifest))}
    elif arguments.command == "plan":
        payload = _plan(manifest)
    elif arguments.command.startswith("preflight-"):
        payload = preflight(manifest, phase=arguments.command.removeprefix("preflight-"))
    elif arguments.command == "q0":
        payload = execute_q0(manifest)
    elif arguments.command == "q1":
        payload = execute_q1(manifest)
    elif arguments.command == "q2":
        payload = execute_q2(manifest)
    elif arguments.command == "audit":
        payload = audit(manifest)
    elif arguments.command == "seal":
        payload = audit(manifest, seal=True)
    else:
        payload = write_report(manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
