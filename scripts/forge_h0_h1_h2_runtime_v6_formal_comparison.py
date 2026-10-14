#!/usr/bin/env python3
"""Issue #453：执行 Runtime v6 的 H0/H1/H2 十八臂 Provider 正式比较。"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import random
import shutil
import subprocess
import sys
import tarfile
from collections import Counter
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_PATH.parent)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_agent_continuation_qualification_v2 as base  # noqa: E402
import forge_progress_aware_harness_comparison_v3 as accounting  # noqa: E402

from deerflow.compile import agent_workflow_runtime_v4 as runtime_v4  # noqa: E402
from deerflow.compile import agent_workflow_runtime_v6 as runtime_v6  # noqa: E402
from deerflow.compile.agent_workflow_schemas import (  # noqa: E402
    AgentBuildNodeInput,
    AgentWorkflowBudget,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowTargetContract,
)
from deerflow.compile.evidence import ExperimentPolicy  # noqa: E402
from deerflow.compile.external_evaluator import FunctionalOracleSpec  # noqa: E402
from deerflow.compile.operations import (  # noqa: E402
    inspect_build_system_impl,
    prepare_compile_session_impl,
)

IDENTITY = "cpp-progress-aware-h0-h1-h2-runtime-v6-formal-comparison-v1"
TRACKING_ISSUE = 453
BRANCH = "yiwei/453-h0-h1-h2-runtime-v6-formal"
SCHEMA_ID = "forge-progress-aware-h0-h1-h2-runtime-v6-formal-comparison-v1"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests" / f"{IDENTITY}.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas" / f"{SCHEMA_ID}.schema.json"
PREREGISTRATION_PATH = REPO_ROOT / "benchmarks/preregistrations" / f"{IDENTITY}.md"
SPEC_PATH = (
    REPO_ROOT / "docs/superpowers/specs/2026-10-14-h0-h1-h2-runtime-v6-formal-design.md"
)
PLAN_PATH = (
    REPO_ROOT / "docs/superpowers/plans/2026-10-14-h0-h1-h2-runtime-v6-formal.md"
)
REPORT_JSON_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.json"
REPORT_MD_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.md"
EVIDENCE_ROOT = (
    REPO_ROOT
    / ".compile-sessions/benchmark-evidence-cpp-progress-aware-h0-h1-h2-runtime-v6-formal-comparison-v1"
)
PARENT_EVIDENCE_ROOT = (
    REPO_ROOT
    / ".compile-sessions/benchmark-evidence-cpp-progress-aware-h0-h1-h2-runtime-v6-qualification-v1"
)
PARENT_MANIFEST_PATH = (
    REPO_ROOT
    / "benchmarks/manifests/cpp-progress-aware-h0-h1-h2-runtime-v6-qualification-v1.json"
)
PARENT_REPORT_JSON_PATH = (
    REPO_ROOT
    / "benchmarks/reports/cpp-progress-aware-h0-h1-h2-runtime-v6-qualification-v1.json"
)
PARENT_REPORT_MD_PATH = (
    REPO_ROOT
    / "benchmarks/reports/cpp-progress-aware-h0-h1-h2-runtime-v6-qualification-v1.md"
)

PARENT_MANIFEST_CANONICAL_SHA256 = (
    "f0000fe9debd0c101d589ac7f98772b1eb5debab41e21344e1458a1761c558fb"
)
PARENT_RELEASE_REVISION = "e9acb6e97e601bfe39cd528c8f135a3b4d6b047d"
PARENT_INVENTORY_CANONICAL_SHA256 = (
    "bb48a02443a67ab36c93af0013f1811d6411dfef35b4ef8a30e242e4d2c52bd8"
)
PARENT_REPORT_JSON_SHA256 = (
    "806da6216a80b8e677930579774889f9cc75ad36897d7c5543ea623eb075cf69"
)
PARENT_REPORT_MD_SHA256 = (
    "1db3c1fffc7bdfec683b35480c0556dddec954983b02302549df1447028baf65"
)
ALLOWED_PREEXISTING_UNTRACKED = (
    "docs/research/2026-10-13-forge-research-progress-defense.html",
)
TREATMENTS = ("h0_runtime_v3", "h1_runtime_v4", "h2_runtime_v6")
BOOTSTRAP_SEED = 45_320_261_014
BOOTSTRAP_SAMPLES = 10_000
NONINFERIORITY_MARGIN = -0.10
ALLOWED_TERMINALS = frozenset(
    {
        "strict_success",
        "evaluated_failure",
        "no_candidate",
        "budget_exhausted",
        "timeout",
    }
)
COMPONENT_PATHS = (
    "scripts/forge_h0_h1_h2_runtime_v6_formal_comparison.py",
    "scripts/forge_agent_continuation_qualification_v2.py",
    "scripts/forge_progress_aware_harness_comparison_v3.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v3.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v4.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v6.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_schemas.py",
    "backend/packages/harness/deerflow/compile/candidate_verifier.py",
    "backend/packages/harness/deerflow/compile/replay_closure_verifier.py",
    "backend/packages/harness/deerflow/compile/external_evaluator_v4.py",
    "backend/packages/harness/deerflow/compile/operations.py",
    "backend/packages/harness/deerflow/tools/bound_compile_tools.py",
    "benchmarks/preregistrations/cpp-progress-aware-h0-h1-h2-runtime-v6-formal-comparison-v1.md",
    "docs/superpowers/specs/2026-10-14-h0-h1-h2-runtime-v6-formal-design.md",
)

QualificationError = base.QualificationError
_BASE_RUN_AGENT_ARM = base._run_agent_arm
_BASE_RUN_V3 = base.runtime_v3.run_agent_workflow_node_v3
_ACTIVE_TREATMENT = "reference"


def _load_json(path: Path) -> dict[str, Any]:
    return base._load_json(path)


def _write_once_json(path: Path, value: Mapping[str, Any]) -> None:
    base._write_once_json(path, value)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _canonical_sha256(value: Any) -> str:
    return base._canonical_sha256(value)


def _file_sha256(path: Path) -> str:
    return base._file_sha256(path)


def _now() -> str:
    return base._now()


def _frozen_components() -> dict[str, str]:
    return {
        relative: _file_sha256(REPO_ROOT / relative) for relative in COMPONENT_PATHS
    }


def _parent_manifest() -> dict[str, Any]:
    value = _load_json(PARENT_MANIFEST_PATH)
    if _canonical_sha256(value) != PARENT_MANIFEST_CANONICAL_SHA256:
        raise QualificationError("parent manifest canonical identity 漂移")
    return value


def _task_from_parent(task: dict[str, Any]) -> dict[str, Any]:
    target = task["target"]
    return {
        "task_id": task["task_id"],
        "project_family": task["project_family"],
        "build_system": task["build_system"],
        "repository_url": task["repository_url"],
        "commit_sha": task["commit_sha"],
        "source_archive": {
            **task["source_archive"],
            "path": f".compile-sessions/benchmark-evidence-cpp-progress-aware-h0-h1-h2-runtime-v6-qualification-v1/q0/sources/{task['task_id']}.tar.gz",
        },
        "target": copy.deepcopy(target),
        "oracle": {
            "command": task["smoke"],
            "workdir": "/workspace/repo",
            "timeout_seconds": 180,
        },
        "source_state_id": f"{task['task_id']}-state-0",
    }


def generate_manifest() -> dict[str, Any]:
    parent = _parent_manifest()
    tasks = [_task_from_parent(task) for task in parent["tasks"]]
    orders = {
        1: {
            "cmake-cmark": TREATMENTS,
            "make-mpc": (TREATMENTS[1], TREATMENTS[2], TREATMENTS[0]),
            "autotools-expat": (TREATMENTS[2], TREATMENTS[0], TREATMENTS[1]),
        },
        2: {
            "cmake-cmark": (TREATMENTS[2], TREATMENTS[1], TREATMENTS[0]),
            "make-mpc": (TREATMENTS[0], TREATMENTS[2], TREATMENTS[1]),
            "autotools-expat": (TREATMENTS[1], TREATMENTS[0], TREATMENTS[2]),
        },
    }
    schedule = []
    sequence = 0
    for repetition in (1, 2):
        for task in tasks:
            for treatment in orders[repetition][task["task_id"]]:
                sequence += 1
                schedule.append(
                    {
                        "sequence": sequence,
                        "task_id": task["task_id"],
                        "treatment": treatment,
                        "repetition": repetition,
                    }
                )
    per_arm = copy.deepcopy(parent["future_common_budget"])
    return {
        "$schema": SCHEMA_ID,
        "schema_version": "forge-progress-aware-h0-h1-h2-runtime-v6-formal-comparison-1.0.0",
        "identity": IDENTITY,
        "issue": TRACKING_ISSUE,
        "branch": BRANCH,
        "status": "authorized_for_formal_comparison",
        "release_revision": None,
        "release_revision_policy": "clean_pushed_branch_head_recorded_by_q0_before_credential_read",
        "allowed_preexisting_untracked": list(ALLOWED_PREEXISTING_UNTRACKED),
        "parent": {
            "identity": parent["identity"],
            "release_revision": PARENT_RELEASE_REVISION,
            "manifest_path": str(PARENT_MANIFEST_PATH.relative_to(REPO_ROOT)),
            "manifest_canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
            "evidence_root": str(PARENT_EVIDENCE_ROOT.relative_to(REPO_ROOT)),
            "inventory_canonical_sha256": PARENT_INVENTORY_CANONICAL_SHA256,
            "report_json_sha256": PARENT_REPORT_JSON_SHA256,
            "report_md_sha256": PARENT_REPORT_MD_SHA256,
            "decision": "proceed_to_runtime_v6_three_arm_formal_comparison_design",
            "mutation_forbidden": True,
        },
        "authorization": {
            "q0_credential_read": False,
            "q0_provider_calls": False,
            "q1_credential_read_after_q0": True,
            "q1_provider_calls": True,
            "docker": True,
            "new_evidence_write": True,
            "historical_evidence_write": False,
            "replacement": False,
            "backfill": False,
            "jev_calls": False,
            "dynamic_budget_controller": False,
        },
        "authorization_record": {
            "authorized_by": "research_owner",
            "authorized_at": "2026-10-14",
            "tracking_issue": TRACKING_ISSUE,
            "maximum_provider_requests": 648,
            "maximum_recorded_tokens": 12_600_000,
            "maximum_provider_cost_usd": 15.12,
        },
        "provider": {
            "provider": "deepseek",
            "profile": "deepseek-flash",
            "actual_model": "deepseek-flash",
            "endpoint": "https://api.deepseek.com",
            "credential_env_name": "DEEPSEEK_API_KEY",
            "request_timeout_seconds": 300,
            "model_max_retries": 0,
            "thinking_enabled": False,
            "streaming": False,
            "input_price_usd_per_million_tokens": 0.3,
            "output_price_usd_per_million_tokens": 1.2,
        },
        "environment": {
            "compile_image": "autocompiler:gcc13",
            "image_id": "sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a",
            "parallel_jobs": parent["environment"]["parallel_jobs"],
            "network_policy": "offline_frozen_source",
        },
        "budget": {
            "per_arm": per_arm,
            "provider_arms": 18,
            "total_provider_requests": 648,
            "total_recorded_tokens_stop_threshold": 10_800_000,
            "total_authorized_recorded_tokens": 12_600_000,
            "total_provider_cost_usd_ceiling": 15.12,
        },
        "treatments": copy.deepcopy(parent["treatments"]),
        "tasks": tasks,
        "schedule": schedule,
        "analysis": {
            "required_arms": 18,
            "replications_per_cell": 2,
            "primary_estimand": "strict_success_risk_difference_h2_minus_h1",
            "cluster_unit": "project_family",
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_samples": BOOTSTRAP_SAMPLES,
            "one_sided_confidence_level": 0.95,
            "noninferiority_margin": NONINFERIORITY_MARGIN,
            "positive_decision": "supports_runtime_v6_reliability_claim",
            "noninferior_without_activation_decision": "runtime_v6_noninferior_but_mechanism_not_activated",
            "noninferiority_failure_decision": "reject_runtime_v6_due_to_success_noninferiority",
            "invalid_decision": "formal_execution_invalid",
        },
        "evidence_root": str(EVIDENCE_ROOT.relative_to(REPO_ROOT)),
        "components": _frozen_components(),
        "preregistration": {
            "path": str(PREREGISTRATION_PATH.relative_to(REPO_ROOT)),
            "sha256": _file_sha256(PREREGISTRATION_PATH),
        },
    }


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "Forge Runtime v6 H0/H1/H2 formal Provider comparison",
        "const": copy.deepcopy(
            manifest if manifest is not None else generate_manifest()
        ),
    }


def validate_manifest(
    manifest: dict[str, Any],
    *,
    require_components: bool = True,
    require_parent_files: bool = False,
) -> dict[str, Any]:
    if (
        manifest.get("identity") != IDENTITY
        or manifest.get("issue") != TRACKING_ISSUE
        or manifest.get("branch") != BRANCH
    ):
        raise QualificationError("manifest identity 漂移")
    if (
        manifest.get("status") != "authorized_for_formal_comparison"
        or manifest.get("release_revision") is not None
    ):
        raise QualificationError("manifest release policy 漂移")
    if manifest.get("allowed_preexisting_untracked") != list(
        ALLOWED_PREEXISTING_UNTRACKED
    ):
        raise QualificationError("允许的预存未跟踪文件漂移")
    if manifest.get("authorization") != {
        "q0_credential_read": False,
        "q0_provider_calls": False,
        "q1_credential_read_after_q0": True,
        "q1_provider_calls": True,
        "docker": True,
        "new_evidence_write": True,
        "historical_evidence_write": False,
        "replacement": False,
        "backfill": False,
        "jev_calls": False,
        "dynamic_budget_controller": False,
    }:
        raise QualificationError("授权边界漂移")
    if manifest.get("authorization_record") != {
        "authorized_by": "research_owner",
        "authorized_at": "2026-10-14",
        "tracking_issue": TRACKING_ISSUE,
        "maximum_provider_requests": 648,
        "maximum_recorded_tokens": 12_600_000,
        "maximum_provider_cost_usd": 15.12,
    }:
        raise QualificationError("用户授权记录漂移")
    parent = manifest.get("parent", {})
    if (
        parent.get("manifest_canonical_sha256") != PARENT_MANIFEST_CANONICAL_SHA256
        or parent.get("inventory_canonical_sha256") != PARENT_INVENTORY_CANONICAL_SHA256
        or parent.get("release_revision") != PARENT_RELEASE_REVISION
    ):
        raise QualificationError("parent identity 漂移")
    if (
        _file_sha256(PARENT_REPORT_JSON_PATH) != PARENT_REPORT_JSON_SHA256
        or _file_sha256(PARENT_REPORT_MD_PATH) != PARENT_REPORT_MD_SHA256
    ):
        raise QualificationError("parent report 漂移")
    tasks = manifest.get("tasks", [])
    if len(tasks) != 3 or Counter(
        task.get("build_system") for task in tasks
    ) != Counter({"cmake": 1, "make": 1, "autotools": 1}):
        raise QualificationError("未见项目分层无效")
    if len({task.get("task_id") for task in tasks}) != 3:
        raise QualificationError("task identity 重复")
    for task in tasks:
        source = task.get("source_archive", {})
        if (
            len(source.get("sha256", "")) != 64
            or source.get("size", 0) <= 0
            or not task.get("oracle", {}).get("command")
        ):
            raise QualificationError(f"task source/oracle 无效: {task.get('task_id')}")
        if require_parent_files:
            path = REPO_ROOT / source["path"]
            if (
                not path.is_file()
                or path.stat().st_size != source["size"]
                or _file_sha256(path) != source["sha256"]
            ):
                raise QualificationError(
                    f"parent source archive 漂移: {task['task_id']}"
                )
    schedule = manifest.get("schedule", [])
    if [row.get("sequence") for row in schedule] != list(range(1, 19)):
        raise QualificationError("十八臂 sequence 漂移")
    if Counter(
        (row.get("task_id"), row.get("treatment"), row.get("repetition"))
        for row in schedule
    ) != Counter(
        (task["task_id"], treatment, repetition)
        for task in tasks
        for treatment in TREATMENTS
        for repetition in (1, 2)
    ):
        raise QualificationError("十八臂 task/treatment/repetition 覆盖无效")
    expected_order = [
        ("cmake-cmark", "h0_runtime_v3", 1),
        ("cmake-cmark", "h1_runtime_v4", 1),
        ("cmake-cmark", "h2_runtime_v6", 1),
        ("make-mpc", "h1_runtime_v4", 1),
        ("make-mpc", "h2_runtime_v6", 1),
        ("make-mpc", "h0_runtime_v3", 1),
        ("autotools-expat", "h2_runtime_v6", 1),
        ("autotools-expat", "h0_runtime_v3", 1),
        ("autotools-expat", "h1_runtime_v4", 1),
        ("cmake-cmark", "h2_runtime_v6", 2),
        ("cmake-cmark", "h1_runtime_v4", 2),
        ("cmake-cmark", "h0_runtime_v3", 2),
        ("make-mpc", "h0_runtime_v3", 2),
        ("make-mpc", "h2_runtime_v6", 2),
        ("make-mpc", "h1_runtime_v4", 2),
        ("autotools-expat", "h1_runtime_v4", 2),
        ("autotools-expat", "h0_runtime_v3", 2),
        ("autotools-expat", "h2_runtime_v6", 2),
    ]
    if [
        (row["task_id"], row["treatment"], row["repetition"]) for row in schedule
    ] != expected_order:
        raise QualificationError("十八臂平衡顺序漂移")
    provider = manifest.get("provider", {})
    if provider != {
        "provider": "deepseek",
        "profile": "deepseek-flash",
        "actual_model": "deepseek-flash",
        "endpoint": "https://api.deepseek.com",
        "credential_env_name": "DEEPSEEK_API_KEY",
        "request_timeout_seconds": 300,
        "model_max_retries": 0,
        "thinking_enabled": False,
        "streaming": False,
        "input_price_usd_per_million_tokens": 0.3,
        "output_price_usd_per_million_tokens": 1.2,
    }:
        raise QualificationError("Provider 合同漂移")
    if manifest.get("environment") != {
        "compile_image": "autocompiler:gcc13",
        "image_id": "sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a",
        "parallel_jobs": 2,
        "network_policy": "offline_frozen_source",
    }:
        raise QualificationError("执行环境漂移")
    per_arm = manifest.get("budget", {}).get("per_arm", {})
    if per_arm != {
        "authorized_recorded_tokens_per_arm": 700000,
        "cleanup_timeout_seconds": 120,
        "command_timeout_seconds": 900,
        "evaluator_timeout_seconds": 1800,
        "max_agent_steps": 96,
        "max_commands": 48,
        "max_model_requests": 36,
        "max_recorded_tokens": 600000,
        "max_recorded_tokens_per_response": 100000,
        "max_tool_calls": 72,
        "node_timeout_seconds": 1800,
        "replay_timeout_seconds": 1800,
    }:
        raise QualificationError("单臂预算漂移")
    budget = manifest["budget"]
    if (
        budget.get("provider_arms") != 18
        or budget.get("total_provider_requests") != 648
        or budget.get("total_recorded_tokens_stop_threshold") != 10_800_000
        or budget.get("total_authorized_recorded_tokens") != 12_600_000
        or budget.get("total_provider_cost_usd_ceiling") != 15.12
    ):
        raise QualificationError("总体预算漂移")
    if manifest.get("analysis") != {
        "required_arms": 18,
        "replications_per_cell": 2,
        "primary_estimand": "strict_success_risk_difference_h2_minus_h1",
        "cluster_unit": "project_family",
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_samples": BOOTSTRAP_SAMPLES,
        "one_sided_confidence_level": 0.95,
        "noninferiority_margin": NONINFERIORITY_MARGIN,
        "positive_decision": "supports_runtime_v6_reliability_claim",
        "noninferior_without_activation_decision": "runtime_v6_noninferior_but_mechanism_not_activated",
        "noninferiority_failure_decision": "reject_runtime_v6_due_to_success_noninferiority",
        "invalid_decision": "formal_execution_invalid",
    }:
        raise QualificationError("正式分析合同漂移")
    if require_components:
        if set(manifest.get("components", {})) != set(COMPONENT_PATHS):
            raise QualificationError("冻结组件集合漂移")
        for relative, expected in manifest["components"].items():
            if _file_sha256(REPO_ROOT / relative) != expected:
                raise QualificationError(f"冻结组件漂移: {relative}")
        if _file_sha256(PREREGISTRATION_PATH) != manifest.get(
            "preregistration", {}
        ).get("sha256"):
            raise QualificationError("预注册漂移")
    if require_parent_files:
        inventory = _load_json(PARENT_EVIDENCE_ROOT / "inventory.json")
        if (
            inventory.get("canonical_sha256") != PARENT_INVENTORY_CANONICAL_SHA256
            or _canonical_sha256(inventory.get("files"))
            != PARENT_INVENTORY_CANONICAL_SHA256
        ):
            raise QualificationError("parent evidence inventory 漂移")
    return manifest


def _manifest() -> dict[str, Any]:
    return _load_json(MANIFEST_PATH)


def _git(*arguments: str) -> str:
    return base._git(*arguments)


def _docker(*arguments: str) -> str:
    return base._docker(*arguments)


def _task(manifest: dict[str, Any], task_id: str) -> dict[str, Any]:
    matches = [task for task in manifest["tasks"] if task["task_id"] == task_id]
    if len(matches) != 1:
        raise QualificationError(f"未知或重复 task: {task_id}")
    return matches[0]


def _worktree_observation() -> dict[str, Any]:
    lines = [
        line
        for line in _git(
            "status", "--porcelain", "--untracked-files=normal"
        ).splitlines()
        if line
    ]
    allowed = {f"?? {path}" for path in ALLOWED_PREEXISTING_UNTRACKED}
    unexpected = [line for line in lines if line not in allowed]
    if unexpected:
        raise QualificationError(f"实验 release 存在未冻结工作树修改: {unexpected}")
    return {
        "tracked_clean": True,
        "allowed_preexisting_untracked": sorted(
            line[3:] for line in lines if line in allowed
        ),
    }


def preflight(
    manifest: dict[str, Any], *, phase: str, require_absent_evidence: bool = False
) -> dict[str, Any]:
    validate_manifest(manifest, require_parent_files=True)
    if phase not in {"q0", "q1"}:
        raise QualificationError(f"未知阶段: {phase}")
    if _git("branch", "--show-current") != BRANCH:
        raise QualificationError("当前分支与 identity 不一致")
    worktree = _worktree_observation()
    head = _git("rev-parse", "HEAD")
    remote_refs = {
        line.strip() for line in _git("branch", "-r", "--contains", head).splitlines()
    }
    if f"origin/{BRANCH}" not in remote_refs:
        raise QualificationError("实验 release 尚未推送到冻结分支")
    required = subprocess.run(
        [str(REPO_ROOT / "scripts/require-docker-runtime.sh")],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if required.returncode != 0:
        raise QualificationError("Linux Docker runtime 不可用")
    image_id = _docker(
        "image",
        "inspect",
        manifest["environment"]["compile_image"],
        "--format",
        "{{.Id}}",
    )
    if image_id != manifest["environment"]["image_id"]:
        raise QualificationError("Docker image ID 漂移")
    base._require_zero_managed_resources()
    if require_absent_evidence and EVIDENCE_ROOT.exists():
        raise QualificationError("create-once evidence root 已存在")
    if phase == "q1" and not EVIDENCE_ROOT.is_dir():
        raise QualificationError("Q1 前置 evidence root 不存在")
    os.environ["DEER_FLOW_WORKSPACE_ROOT"] = str(REPO_ROOT)
    os.environ["DEER_FLOW_HOST_WORKSPACE_ROOT"] = str(REPO_ROOT)
    return {
        "identity": IDENTITY,
        "phase": phase,
        "release_revision": head,
        "manifest_sha256": _canonical_sha256(manifest),
        "image_id": image_id,
        "worktree": worktree,
        "parent_inventory_canonical_sha256": PARENT_INVENTORY_CANONICAL_SHA256,
    }


def _source_path(task: dict[str, Any]) -> Path:
    path = REPO_ROOT / task["source_archive"]["path"]
    if (
        not path.is_file()
        or path.stat().st_size != task["source_archive"]["size"]
        or _file_sha256(path) != task["source_archive"]["sha256"]
    ):
        raise QualificationError(f"source archive 漂移: {task['task_id']}")
    return path


def _oracle(task: dict[str, Any]) -> FunctionalOracleSpec:
    oracle = task["oracle"]
    return FunctionalOracleSpec(
        oracle_ref=f"issue-453-{task['task_id']}-oracle-v1",
        argv=("bash", "-lc", oracle["command"]),
        workdir=oracle["workdir"],
        timeout_seconds=oracle["timeout_seconds"],
    )


def _budget(manifest: dict[str, Any]) -> AgentWorkflowBudget:
    values = {
        key: value
        for key, value in manifest["budget"]["per_arm"].items()
        if key != "authorized_recorded_tokens_per_arm"
    }
    return AgentWorkflowBudget(**values)


def _prepare_source_session(
    manifest: dict[str, Any],
    task: dict[str, Any],
    state_id: str,
    *,
    thread_id: str,
    run_id: str,
) -> tuple[Any, dict[str, Any], dict[str, Any], dict[str, Any]]:
    if state_id != task["source_state_id"]:
        raise QualificationError("source state identity 漂移")
    services = base.get_compile_services()
    session = prepare_compile_session_impl(
        thread_id=thread_id,
        repo_url=task["repository_url"],
        run_id=run_id,
        task_description=f"Issue #453 Runtime v6 formal comparison: {task['task_id']}:{_ACTIVE_TREATMENT}",
    )
    if session.image_id != manifest["environment"]["image_id"]:
        raise QualificationError("Compile Session image identity 漂移")
    base._disconnect_container_networks(session.container_id)
    repository = Path(session.leadagent_repo_dir)
    if repository.exists() and any(repository.iterdir()):
        raise QualificationError("source restore 前 repo 目录非空")
    repository.mkdir(parents=True, exist_ok=True)
    source = _source_path(task)
    with tarfile.open(source, "r:gz") as archive:
        archive.extractall(repository, filter="data")
    replay_source = Path(session.leadagent_repro_dir) / "source.tar"
    replay_source.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, replay_source)
    session.commit_sha = task["commit_sha"]
    session.replay_source_archive_sha256 = task["source_archive"]["sha256"]
    services.manager.save_session(session)
    services.manager.mark_session_status(session, "source_ready")
    primary, detected, _suggested = inspect_build_system_impl(session=session)
    detected_systems = [system for system, _marker in detected]
    if task["build_system"] not in detected_systems:
        raise QualificationError(f"source 缺少 build-system marker: {task['task_id']}")
    session.selected_build_system = task["build_system"]
    services.manager.save_session(session)
    checkpoint = {
        "checkpoint_sha256": task["source_archive"]["sha256"],
        "workspace_snapshot_sha256": task["source_archive"]["sha256"],
        "source": {
            "repository_url": task["repository_url"],
            "commit_sha": task["commit_sha"],
        },
        "detected_primary": primary,
    }
    message = {
        "role": "user",
        "content": "Build the frozen source project and submit the required artifact.",
    }
    parent_budget = {
        "wall_clock_milliseconds": 0,
        "provider_requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "provider_cost_microusd": 0,
        "build_executions": 0,
    }
    return session, checkpoint, message, parent_budget


def _node_input(
    manifest: dict[str, Any],
    task: dict[str, Any],
    session: Any,
    *,
    attempt_id: str,
    state_id: str,
    checkpoint: dict[str, Any],
    message: dict[str, Any],
    parent_budget: dict[str, Any],
) -> AgentBuildNodeInput:
    del message, parent_budget
    target = task["target"]
    return AgentBuildNodeInput(
        task_id=task["task_id"],
        attempt_id=attempt_id,
        session_id=session.session_id,
        repository_url=task["repository_url"],
        commit_sha=task["commit_sha"],
        source_snapshot_sha256=task["source_archive"]["sha256"],
        build_system_candidates=(task["build_system"],),
        target_contract=AgentWorkflowTargetContract(
            target_id=target["target_id"],
            artifact_types=(target["artifact_type"],),
            artifact_path_patterns=(target["artifact_path"],),
            functional_oracle_ref=_oracle(task).oracle_ref,
        ),
        operation_policy_ref=f"issue-453-runtime-v6-formal-{_ACTIVE_TREATMENT}",
        environment=AgentWorkflowEnvironmentIdentity(
            image_id=manifest["environment"]["image_id"],
            parallel_jobs=manifest["environment"]["parallel_jobs"],
            network_policy=manifest["environment"]["network_policy"],
        ),
        budget=_budget(manifest),
        experiment_identity=AgentWorkflowExperimentIdentity(
            manifest_sha256=_canonical_sha256(manifest),
            protocol_sha256=_file_sha256(PREREGISTRATION_PATH),
            runner_sha256=_file_sha256(SCRIPT_PATH),
        ),
        initial_observation={
            "formal_mode": "runtime_v6_held_out_frozen_source",
            "source_state_id": state_id,
            "source_archive_sha256": checkpoint["workspace_snapshot_sha256"],
            "harness_treatment": _ACTIVE_TREATMENT,
            "required_candidate_artifacts": (target["artifact_path"],),
            "selected_build_system": task["build_system"],
            "instruction": "Build from this clean frozen source. Record every command needed by clean replay, stage only the required artifact, and submit only after a successful build and functional check.",
        },
    )


def _experiment_policy(
    manifest: dict[str, Any], task: dict[str, Any], repetition: int
) -> ExperimentPolicy:
    provider = manifest["provider"]
    budget = manifest["budget"]["per_arm"]
    return ExperimentPolicy(
        benchmark_id=IDENTITY,
        manifest_sha256=_canonical_sha256(manifest),
        case_id=task["task_id"],
        condition=_ACTIVE_TREATMENT,
        repetition=repetition,
        expected_repo_url=task["repository_url"],
        expected_commit_sha=task["commit_sha"],
        expected_build_system=task["build_system"],
        compile_image=manifest["environment"]["compile_image"],
        image_id=manifest["environment"]["image_id"],
        model_name=provider["profile"],
        endpoint=provider["endpoint"],
        credential_env=provider["credential_env_name"],
        request_timeout_seconds=provider["request_timeout_seconds"],
        model_max_retries=provider["model_max_retries"],
        compiler_max_turns=budget["max_model_requests"],
        subagent_timeout_seconds=budget["node_timeout_seconds"],
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=(),
        cmake_arguments=(),
        configure_arguments=(),
        environment=(),
        minimum_replay_delay_seconds=0,
        compiler_model_turn_limit=budget["max_model_requests"],
        compiler_graph_recursion_limit=budget["max_agent_steps"],
        compiler_wall_clock_seconds=budget["node_timeout_seconds"],
        compiler_post_build_reserve_seconds=budget["cleanup_timeout_seconds"],
    )


async def _run_node(**kwargs: Any) -> Any:
    if _ACTIVE_TREATMENT == "h0_runtime_v3":
        return await _BASE_RUN_V3(**kwargs)
    if _ACTIVE_TREATMENT == "h1_runtime_v4":
        return await runtime_v4.run_agent_workflow_node_v4(**kwargs)
    if _ACTIVE_TREATMENT == "h2_runtime_v6":
        return await runtime_v6.run_agent_workflow_node_v6(**kwargs)
    raise QualificationError(f"Provider arm treatment 无效: {_ACTIVE_TREATMENT}")


@contextmanager
def _base_bindings() -> Iterator[None]:
    bindings = {
        "IDENTITY": base.IDENTITY,
        "TRACKING_ISSUE": base.TRACKING_ISSUE,
        "BRANCH": base.BRANCH,
        "SCRIPT_PATH": base.SCRIPT_PATH,
        "MANIFEST_PATH": base.MANIFEST_PATH,
        "PREREGISTRATION_PATH": base.PREREGISTRATION_PATH,
        "_prepare_restored_session": base._prepare_restored_session,
        "_node_input": base._node_input,
        "_experiment_policy": base._experiment_policy,
        "_oracle": base._oracle,
        "_token_observation": base._token_observation,
        "_budget_record": base._budget_record,
    }
    original_run = base.runtime_v3.run_agent_workflow_node_v3
    try:
        base.IDENTITY = IDENTITY
        base.TRACKING_ISSUE = TRACKING_ISSUE
        base.BRANCH = BRANCH
        base.SCRIPT_PATH = SCRIPT_PATH
        base.MANIFEST_PATH = MANIFEST_PATH
        base.PREREGISTRATION_PATH = PREREGISTRATION_PATH
        base._prepare_restored_session = _prepare_source_session
        base._node_input = _node_input
        base._experiment_policy = _experiment_policy
        base._oracle = _oracle
        base._token_observation = accounting._token_observation
        base._budget_record = accounting._budget_record
        base.runtime_v3.run_agent_workflow_node_v3 = _run_node
        yield
    finally:
        for name, value in bindings.items():
            setattr(base, name, value)
        base.runtime_v3.run_agent_workflow_node_v3 = original_run


@contextmanager
def _runtime_identity(manifest: dict[str, Any]) -> Iterator[None]:
    services = base.get_compile_services()
    manager = services.manager
    runtime = services.runtime
    original = (
        manager.default_image,
        manager.parallel_jobs,
        runtime.config.image,
        runtime.config.parallel_jobs,
        runtime.config.replay_timeout_seconds,
    )
    try:
        manager.default_image = manifest["environment"]["compile_image"]
        manager.parallel_jobs = manifest["environment"]["parallel_jobs"]
        runtime.config.image = manifest["environment"]["compile_image"]
        runtime.config.parallel_jobs = manifest["environment"]["parallel_jobs"]
        runtime.config.replay_timeout_seconds = manifest["budget"]["per_arm"][
            "replay_timeout_seconds"
        ]
        yield
    finally:
        (
            manager.default_image,
            manager.parallel_jobs,
            runtime.config.image,
            runtime.config.parallel_jobs,
            runtime.config.replay_timeout_seconds,
        ) = original


def _events(arm_dir: Path) -> list[dict[str, Any]]:
    paths = [
        path
        for path in sorted((arm_dir / "session-evidence").rglob("events.jsonl"))
        if "evaluations" not in path.parts
    ]
    if len(paths) != 1:
        return []
    return [
        json.loads(line)
        for line in paths[0].read_text(encoding="utf-8").splitlines()
        if line
    ]


def _harness_metrics(
    arm_dir: Path, treatment: str, expected_source_sha256: str
) -> dict[str, Any]:
    events = _events(arm_dir)
    event_types = Counter(event.get("event_type") for event in events)
    rejections = [
        event.get("payload", {})
        for event in events
        if event.get("event_type") == "candidate.submit_rejected"
    ]
    session_paths = sorted((arm_dir / "session-evidence").glob("session.json"))
    source_bound = False
    command_count = 0
    diagnostic_commands = 0
    if len(session_paths) == 1:
        session = _load_json(session_paths[0])
        source_bound = (
            session.get("replay_source_archive_sha256") == expected_source_sha256
        )
        commands = session.get("commands", [])
        command_count = len(commands)
        diagnostic_commands = sum(
            command.get("role") == "diagnostic" for command in commands
        )
    frontier_events = [
        event.get("payload", {})
        for event in events
        if event.get("event_type") == "harness.submission_frontier_observed"
    ]
    repair_actions = [
        event.get("payload", {})
        for event in events
        if event.get("event_type") == "harness.repair_action_completed"
    ]
    return {
        "treatment": treatment,
        "progress_snapshots": event_types["harness.progress_snapshot"],
        "context_compactions": event_types["harness.context_compacted"],
        "replay_closure_events": event_types["candidate.replay_closure_completed"],
        "candidate_submit_started": event_types["candidate.submit_started"],
        "candidate_submit_rejected": event_types["candidate.submit_rejected"],
        "replay_closure_rejections": sum(
            any(
                str(code).startswith("replay_")
                or code
                in {
                    "missing_bootstrap_step",
                    "missing_generated_input",
                    "recipe_execution_failed",
                }
                for code in payload.get("rejection_codes", [])
            )
            for payload in rejections
        ),
        "repair_windows_opened": sum(
            payload.get("repair_window_opened") is True for payload in frontier_events
        ),
        "repair_permissions_consumed": event_types[
            "harness.repair_permission_consumed"
        ],
        "repair_actions_completed": len(repair_actions),
        "repair_actions_succeeded": sum(
            payload.get("succeeded") is True for payload in repair_actions
        ),
        "resubmissions": max(0, event_types["candidate.submit_started"] - 1),
        "command_count": command_count,
        "diagnostic_commands": diagnostic_commands,
        "offline_source_bound": source_bound,
    }


def _instrumentation_valid(item: dict[str, Any]) -> bool:
    metrics = item.get("harness_metrics", {})
    requests = item.get("token_accounting", {}).get("requests_completed")
    treatment = item.get("treatment")
    if treatment == "h0_runtime_v3":
        return (
            metrics.get("progress_snapshots") == 0
            and metrics.get("context_compactions") == 0
            and metrics.get("replay_closure_events") == 0
        )
    if treatment == "h1_runtime_v4":
        return (
            type(requests) is int
            and requests > 0
            and metrics.get("progress_snapshots") == requests
            and metrics.get("context_compactions") == requests
            and metrics.get("replay_closure_events") == 0
        )
    if treatment == "h2_runtime_v6":
        return (
            type(requests) is int
            and requests > 0
            and metrics.get("progress_snapshots") == requests
            and metrics.get("context_compactions") == requests
            and type(metrics.get("repair_windows_opened")) is int
            and type(metrics.get("repair_permissions_consumed")) is int
            and type(metrics.get("repair_actions_completed")) is int
        )
    return False


def _arm_complete(item: dict[str, Any]) -> bool:
    return bool(
        item.get("terminal_classification") in ALLOWED_TERMINALS
        and item.get("error_class") is None
        and item.get("cleanup_succeeded") is True
        and item.get("post_action_observation") is not None
        and item.get("harness_metrics", {}).get("offline_source_bound") is True
        and item.get("budget", {}).get("complete") is True
        and item.get("budget", {}).get("conserved") is True
        and accounting._arm_usage_integrity(item)
        and _instrumentation_valid(item)
    )


async def _run_assigned_arm(
    manifest: dict[str, Any],
    *,
    schedule: dict[str, Any],
    arm_dir: Path,
    release_revision: str,
) -> dict[str, Any]:
    global _ACTIVE_TREATMENT
    task = _task(manifest, schedule["task_id"])
    assignment = {
        "identity": IDENTITY,
        "phase": "q1",
        "sequence": schedule["sequence"],
        "task_id": task["task_id"],
        "checkpoint_state_id": task["source_state_id"],
        "repetition": schedule["repetition"],
        "treatment": schedule["treatment"],
    }
    assignment_path = arm_dir / "assignment.json"
    if assignment_path.exists():
        if _load_json(assignment_path) != assignment:
            raise QualificationError("arm assignment 漂移")
    else:
        _write_once_json(assignment_path, assignment)
    previous = _ACTIVE_TREATMENT
    _ACTIVE_TREATMENT = schedule["treatment"]
    try:
        with _base_bindings():
            result = await _BASE_RUN_AGENT_ARM(
                manifest,
                phase="q1",
                sequence=schedule["sequence"],
                task=task,
                state_id=task["source_state_id"],
                repetition=schedule["repetition"],
                arm_dir=arm_dir,
                release_revision=release_revision,
            )
    finally:
        _ACTIVE_TREATMENT = previous
    metrics = _harness_metrics(
        arm_dir, schedule["treatment"], task["source_archive"]["sha256"]
    )
    _write_once_json(arm_dir / "harness-metrics.json", metrics)
    enriched = {
        **result,
        "treatment": schedule["treatment"],
        "harness_metrics": metrics,
    }
    _write_json(arm_dir / "enriched-result.json", enriched)
    return enriched


def _load_completed_arm(arm_dir: Path, schedule: dict[str, Any]) -> dict[str, Any]:
    assignment = _load_json(arm_dir / "assignment.json")
    expected = {
        "sequence": schedule["sequence"],
        "task_id": schedule["task_id"],
        "repetition": schedule["repetition"],
        "treatment": schedule["treatment"],
    }
    if any(assignment.get(key) != value for key, value in expected.items()):
        raise QualificationError("completed arm assignment 漂移")
    return _load_json(arm_dir / "enriched-result.json")


def _totals(outcomes: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "provider_requests": sum(
            item.get("token_accounting", {}).get("requests_started", 0)
            for item in outcomes
        ),
        "recorded_tokens": sum(
            item.get("token_accounting", {}).get("recorded_tokens") or 0
            for item in outcomes
        ),
        "provider_cost_microusd": sum(
            item.get("budget", {}).get("delta", {}).get("provider_cost_microusd", 0)
            for item in outcomes
        ),
    }


def _check_total_budget(
    manifest: dict[str, Any], outcomes: list[dict[str, Any]]
) -> None:
    totals = _totals(outcomes)
    budget = manifest["budget"]
    if (
        totals["provider_requests"] > budget["total_provider_requests"]
        or totals["recorded_tokens"] > budget["total_authorized_recorded_tokens"]
        or totals["provider_cost_microusd"]
        > round(budget["total_provider_cost_usd_ceiling"] * 1_000_000)
    ):
        raise QualificationError("Provider 批次授权上界被突破")


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise QualificationError("bootstrap 样本为空")
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _strict_rate(rows: list[dict[str, Any]], treatment: str) -> float:
    selected = [row for row in rows if row.get("treatment") == treatment]
    if not selected:
        raise QualificationError(f"缺少 treatment observation: {treatment}")
    return sum(row.get("strict_success") is True for row in selected) / len(selected)


def _clustered_bootstrap(
    manifest: dict[str, Any], outcomes: list[dict[str, Any]]
) -> dict[str, Any]:
    families = [task["task_id"] for task in manifest["tasks"]]
    by_family = {
        family: [row for row in outcomes if row.get("task_id") == family]
        for family in families
    }
    rng = random.Random(BOOTSTRAP_SEED)
    differences = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sampled = [rng.choice(families) for _ in families]
        rows = [row for family in sampled for row in by_family[family]]
        differences.append(
            _strict_rate(rows, "h2_runtime_v6") - _strict_rate(rows, "h1_runtime_v4")
        )
    return {
        "unit": "project_family",
        "seed": BOOTSTRAP_SEED,
        "samples": BOOTSTRAP_SAMPLES,
        "one_sided_95_lower": _percentile(differences, 0.05),
        "two_sided_95_interval": [
            _percentile(differences, 0.025),
            _percentile(differences, 0.975),
        ],
    }


def _external_replay_failed(item: dict[str, Any]) -> bool:
    return any(
        layer.get("layer") == "S5" and layer.get("status") != "passed"
        for layer in item.get("layers", [])
    )


def _qualification(
    manifest: dict[str, Any], outcomes: list[dict[str, Any]]
) -> dict[str, Any]:
    schedule_counts = Counter(
        (item.get("task_id"), item.get("treatment")) for item in outcomes
    )
    expected_counts = Counter(
        (row["task_id"], row["treatment"]) for row in manifest["schedule"]
    )
    by_treatment = {
        treatment: [item for item in outcomes if item.get("treatment") == treatment]
        for treatment in TREATMENTS
    }
    totals = _totals(outcomes)
    budget = manifest["budget"]
    hard_gates = {
        "classified_terminal": len(outcomes) == 18
        and all(
            item.get("terminal_classification") in ALLOWED_TERMINALS
            for item in outcomes
        ),
        "schedule_complete": schedule_counts == expected_counts,
        "request_lifecycle_and_usage": len(outcomes) == 18
        and all(accounting._arm_usage_integrity(item) for item in outcomes),
        "budget_conserved": len(outcomes) == 18
        and all(
            item.get("budget", {}).get("complete") is True
            and item.get("budget", {}).get("conserved") is True
            for item in outcomes
        ),
        "source_and_post_observation_bound": len(outcomes) == 18
        and all(
            item.get("harness_metrics", {}).get("offline_source_bound") is True
            and item.get("post_action_observation") is not None
            for item in outcomes
        ),
        "cleanup": len(outcomes) == 18
        and all(item.get("cleanup_succeeded") is True for item in outcomes),
        "no_infrastructure_error": len(outcomes) == 18
        and all(item.get("error_class") is None for item in outcomes),
        "treatment_instrumentation": len(outcomes) == 18
        and all(_instrumentation_valid(item) for item in outcomes),
        "batch_budget": totals["provider_requests"] <= budget["total_provider_requests"]
        and totals["recorded_tokens"] <= budget["total_authorized_recorded_tokens"]
        and totals["provider_cost_microusd"]
        <= round(budget["total_provider_cost_usd_ceiling"] * 1_000_000),
    }
    formal_valid = all(hard_gates.values())
    point_difference = None
    bootstrap = None
    if formal_valid:
        point_difference = _strict_rate(outcomes, "h2_runtime_v6") - _strict_rate(
            outcomes, "h1_runtime_v4"
        )
        bootstrap = _clustered_bootstrap(manifest, outcomes)
    lower_bound = bootstrap["one_sided_95_lower"] if bootstrap is not None else None
    noninferiority_passed = bool(
        formal_valid
        and lower_bound is not None
        and lower_bound >= NONINFERIORITY_MARGIN
    )
    h1_external_replay_failures = sum(
        _external_replay_failed(item) for item in by_treatment["h1_runtime_v4"]
    )
    h2_replay_closure_rejections = sum(
        item.get("harness_metrics", {}).get("replay_closure_rejections", 0)
        for item in by_treatment["h2_runtime_v6"]
    )
    h2_repair_windows_opened = sum(
        item.get("harness_metrics", {}).get("repair_windows_opened", 0)
        for item in by_treatment["h2_runtime_v6"]
    )
    h2_repair_permissions_consumed = sum(
        item.get("harness_metrics", {}).get("repair_permissions_consumed", 0)
        for item in by_treatment["h2_runtime_v6"]
    )
    mechanism_activated = bool(
        h1_external_replay_failures > 0
        and h2_replay_closure_rejections > 0
        and h2_repair_windows_opened > 0
        and h2_repair_permissions_consumed > 0
    )
    analysis = manifest["analysis"]
    if not formal_valid:
        decision = analysis["invalid_decision"]
    elif not noninferiority_passed:
        decision = analysis["noninferiority_failure_decision"]
    elif mechanism_activated:
        decision = analysis["positive_decision"]
    else:
        decision = analysis["noninferior_without_activation_decision"]
    return {
        "hard_gates": hard_gates,
        "formal_valid": formal_valid,
        "provider_totals": totals,
        "primary_analysis": {
            "estimand": analysis["primary_estimand"],
            "strict_success_difference": point_difference,
            "noninferiority_margin": NONINFERIORITY_MARGIN,
            "clustered_bootstrap": bootstrap,
            "noninferiority_passed": noninferiority_passed,
        },
        "mechanism_activation": {
            "h1_external_replay_failures": h1_external_replay_failures,
            "h2_replay_closure_rejections": h2_replay_closure_rejections,
            "h2_repair_windows_opened": h2_repair_windows_opened,
            "h2_repair_permissions_consumed": h2_repair_permissions_consumed,
            "activated": mechanism_activated,
        },
        "passed": formal_valid,
        "decision": decision,
    }


def _phase_marker(phase: str) -> Path:
    return EVIDENCE_ROOT / phase / "attempt.json"


def _start_phase(phase: str, preflight_result: dict[str, Any]) -> None:
    base._start_marker(
        _phase_marker(phase),
        preflight_result["manifest_sha256"],
        preflight_result["release_revision"],
    )


def _finish_phase(phase: str, status: str, error_class: str | None = None) -> None:
    base._finish_marker(_phase_marker(phase), status, error_class)


def _require_q0(
    manifest: dict[str, Any], preflight_result: dict[str, Any]
) -> dict[str, Any]:
    return base._require_phase_passed(
        EVIDENCE_ROOT,
        "q0",
        preflight_result["manifest_sha256"],
        preflight_result["release_revision"],
    )


def execute_q0(manifest: dict[str, Any]) -> dict[str, Any]:
    ready = preflight(manifest, phase="q0", require_absent_evidence=True)
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=False)
    _write_once_json(
        EVIDENCE_ROOT / "identity.json",
        {
            "identity": IDENTITY,
            "manifest_sha256": ready["manifest_sha256"],
            "release_revision": ready["release_revision"],
            "parent_inventory_canonical_sha256": PARENT_INVENTORY_CANONICAL_SHA256,
            "created_at": _now(),
        },
    )
    _start_phase("q0", ready)
    try:
        sources = []
        for task in manifest["tasks"]:
            path = _source_path(task)
            sources.append(
                {
                    "task_id": task["task_id"],
                    "path": task["source_archive"]["path"],
                    "size": path.stat().st_size,
                    "sha256": _file_sha256(path),
                }
            )
        bindings = {
            "h0_runtime_v3": _BASE_RUN_V3.__name__,
            "h1_runtime_v4": runtime_v4.run_agent_workflow_node_v4.__name__,
            "h2_runtime_v6": runtime_v6.run_agent_workflow_node_v6.__name__,
        }
        passed = len(sources) == 3 and bindings == {
            "h0_runtime_v3": "run_agent_workflow_node_v3",
            "h1_runtime_v4": "run_agent_workflow_node_v4",
            "h2_runtime_v6": "run_agent_workflow_node_v6",
        }
        result = {
            "phase": "q0",
            "manifest_sha256": ready["manifest_sha256"],
            "release_revision": ready["release_revision"],
            "parent_inventory_canonical_sha256": PARENT_INVENTORY_CANONICAL_SHA256,
            "sources": sources,
            "runtime_bindings": bindings,
            "credential_reads": 0,
            "provider_requests": 0,
            "model_tokens": 0,
            "passed": passed,
            "completed_at": _now(),
        }
        _write_once_json(EVIDENCE_ROOT / "q0/result.json", result)
        _finish_phase("q0", "passed" if passed else "failed")
        if not passed:
            raise QualificationError("Q0 identity 资格未通过")
        return result
    except BaseException as exc:
        if not (EVIDENCE_ROOT / "q0/result.json").exists():
            _write_once_json(
                EVIDENCE_ROOT / "q0/result.json",
                {
                    "phase": "q0",
                    "manifest_sha256": ready["manifest_sha256"],
                    "release_revision": ready["release_revision"],
                    "credential_reads": 0,
                    "provider_requests": 0,
                    "passed": False,
                    "error_class": type(exc).__name__,
                    "completed_at": _now(),
                },
            )
        if _load_json(_phase_marker("q0")).get("status") == "started":
            _finish_phase("q0", "failed", type(exc).__name__)
        raise


def execute_q1(manifest: dict[str, Any]) -> dict[str, Any]:
    ready = preflight(manifest, phase="q1")
    _require_q0(manifest, ready)
    base._provider_preflight(manifest)
    _start_phase("q1", ready)
    outcomes: list[dict[str, Any]] = []
    try:
        with _runtime_identity(manifest):
            for row in manifest["schedule"]:
                arm_dir = (
                    EVIDENCE_ROOT
                    / "q1/arms"
                    / f"{row['sequence']:02d}-{row['task_id']}-{row['treatment']}"
                )
                if (arm_dir / "enriched-result.json").is_file():
                    outcomes.append(_load_completed_arm(arm_dir, row))
                    continue
                if (arm_dir / "attempt.json").exists():
                    raise QualificationError(
                        "Q1 存在 started 但无 enriched result 的 arm，禁止 retry"
                    )
                outcomes.append(
                    asyncio.run(
                        _run_assigned_arm(
                            manifest,
                            schedule=row,
                            arm_dir=arm_dir,
                            release_revision=ready["release_revision"],
                        )
                    )
                )
                _check_total_budget(manifest, outcomes)
        qualification = _qualification(manifest, outcomes)
        result = {
            "phase": "q1",
            "manifest_sha256": ready["manifest_sha256"],
            "release_revision": ready["release_revision"],
            "outcomes": outcomes,
            "qualification": qualification,
            "passed": qualification["passed"],
            "completed_at": _now(),
        }
        _write_once_json(EVIDENCE_ROOT / "q1/result.json", result)
        _finish_phase("q1", "passed" if result["passed"] else "failed")
        return result
    except BaseException as exc:
        qualification = _qualification(manifest, outcomes)
        if not (EVIDENCE_ROOT / "q1/result.json").exists():
            _write_once_json(
                EVIDENCE_ROOT / "q1/result.json",
                {
                    "phase": "q1",
                    "manifest_sha256": ready["manifest_sha256"],
                    "release_revision": ready["release_revision"],
                    "outcomes": outcomes,
                    "qualification": qualification,
                    "passed": False,
                    "error_class": type(exc).__name__,
                    "completed_at": _now(),
                },
            )
        if _load_json(_phase_marker("q1")).get("status") == "started":
            _finish_phase("q1", "failed", type(exc).__name__)
        raise


def _inventory(root: Path) -> dict[str, Any]:
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "inventory.json":
            files.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": _file_sha256(path),
                }
            )
    return {
        "files": files,
        "file_count": len(files),
        "total_bytes": sum(item["size"] for item in files),
        "canonical_sha256": _canonical_sha256(files),
    }


def audit(manifest: dict[str, Any], *, seal: bool = False) -> dict[str, Any]:
    validate_manifest(manifest, require_parent_files=True)
    identity = _load_json(EVIDENCE_ROOT / "identity.json")
    q0 = _load_json(EVIDENCE_ROOT / "q0/result.json")
    q1 = _load_json(EVIDENCE_ROOT / "q1/result.json")
    digest = _canonical_sha256(manifest)
    phase_hashes = {
        identity.get("manifest_sha256"),
        q0.get("manifest_sha256"),
        q1.get("manifest_sha256"),
    }
    releases = {
        identity.get("release_revision"),
        q0.get("release_revision"),
        q1.get("release_revision"),
    }
    qualification = _qualification(manifest, q1.get("outcomes", []))
    valid = (
        phase_hashes == {digest}
        and len(releases) == 1
        and q0.get("passed") is True
        and qualification == q1.get("qualification")
        and len(q1.get("outcomes", [])) == 18
    )
    base._require_zero_managed_resources()
    inventory_path = EVIDENCE_ROOT / "inventory.json"
    inventory = _inventory(EVIDENCE_ROOT)
    if seal:
        if inventory_path.exists():
            raise QualificationError("inventory 已封口")
        _write_once_json(inventory_path, inventory)
    elif inventory_path.exists():
        recorded = _load_json(inventory_path)
        valid = valid and recorded == inventory
        inventory = recorded
    return {
        "identity": IDENTITY,
        "valid": valid,
        "manifest_sha256": digest,
        "release_revision": next(iter(releases)) if len(releases) == 1 else None,
        "q0_passed": q0.get("passed"),
        "q1_passed": q1.get("passed"),
        "decision": qualification["decision"],
        "inventory": inventory,
        "zero_managed_resources": True,
    }


def _treatment_summary(
    outcomes: list[dict[str, Any]], treatment: str
) -> dict[str, Any]:
    rows = [item for item in outcomes if item.get("treatment") == treatment]
    durations = [item.get("duration_milliseconds", 0) for item in rows]
    return {
        "arms": len(rows),
        "strict_success": sum(item.get("strict_success") is True for item in rows),
        "evaluated_candidates": sum(
            item.get("candidate_submitted") is True and len(item.get("layers", [])) == 6
            for item in rows
        ),
        "provider_requests": sum(
            item.get("token_accounting", {}).get("requests_started", 0) for item in rows
        ),
        "input_tokens": sum(
            item.get("token_accounting", {}).get("input_tokens") or 0 for item in rows
        ),
        "output_tokens": sum(
            item.get("token_accounting", {}).get("output_tokens") or 0 for item in rows
        ),
        "recorded_tokens": sum(
            item.get("token_accounting", {}).get("recorded_tokens") or 0
            for item in rows
        ),
        "provider_cost_microusd": sum(
            item.get("budget", {}).get("delta", {}).get("provider_cost_microusd", 0)
            for item in rows
        ),
        "wall_clock_milliseconds": sum(durations),
        "wall_clock_range_milliseconds": [min(durations), max(durations)]
        if durations
        else [],
        "budget_exhausted": sum(
            item.get("terminal_classification") == "budget_exhausted" for item in rows
        ),
        "no_candidate": sum(
            item.get("terminal_classification") == "no_candidate" for item in rows
        ),
        "replay_closure_events": sum(
            item.get("harness_metrics", {}).get("replay_closure_events", 0)
            for item in rows
        ),
        "replay_closure_rejections": sum(
            item.get("harness_metrics", {}).get("replay_closure_rejections", 0)
            for item in rows
        ),
        "diagnostic_commands": sum(
            item.get("harness_metrics", {}).get("diagnostic_commands", 0)
            for item in rows
        ),
        "repair_windows_opened": sum(
            item.get("harness_metrics", {}).get("repair_windows_opened", 0)
            for item in rows
        ),
        "repair_permissions_consumed": sum(
            item.get("harness_metrics", {}).get("repair_permissions_consumed", 0)
            for item in rows
        ),
        "repair_actions_completed": sum(
            item.get("harness_metrics", {}).get("repair_actions_completed", 0)
            for item in rows
        ),
        "resubmissions": sum(
            item.get("harness_metrics", {}).get("resubmissions", 0) for item in rows
        ),
        "external_replay_failures": sum(_external_replay_failed(item) for item in rows),
    }


def write_report(manifest: dict[str, Any]) -> dict[str, Any]:
    audited = audit(manifest)
    if not audited["valid"]:
        raise QualificationError("evidence audit 未通过")
    q0 = _load_json(EVIDENCE_ROOT / "q0/result.json")
    q1 = _load_json(EVIDENCE_ROOT / "q1/result.json")
    outcomes = q1["outcomes"]
    summaries = {
        treatment: _treatment_summary(outcomes, treatment) for treatment in TREATMENTS
    }
    report = {
        "identity": IDENTITY,
        "status": "completed",
        "decision": q1["qualification"]["decision"],
        "q0": {
            "passed": q0["passed"],
            "credential_reads": q0["credential_reads"],
            "provider_requests": q0["provider_requests"],
        },
        "q1": {
            "arms": len(outcomes),
            "treatments": summaries,
            "qualification": q1["qualification"],
        },
        "audit": audited,
        "interpretation_boundary": "本正式比较只估计三个冻结项目族、两次重复上的 H2-H1 严格成功差值和 Runtime v6 机制是否自然激活；不支持开放世界、项目总体泛化、统计显著性、通用模型排名或动态预算效果。",
        "completed_at": _now(),
    }
    _write_json(REPORT_JSON_PATH, report)
    q = q1["qualification"]
    lines = [
        "# H0/H1/H2 Runtime v6 十八臂 Provider 正式比较结果",
        "",
        f"**决定：`{report['decision']}`。**",
        "",
        f"Q0：通过，0 credential read / 0 Provider request；Q1：`{len(outcomes)}/18` arms 分类终结。",
        "",
        "## 描述性结果",
        "",
    ]
    for treatment in TREATMENTS:
        summary = summaries[treatment]
        lines.append(
            f"- `{treatment}`：strict `{summary['strict_success']}/6`，evaluated `{summary['evaluated_candidates']}/6`，"
            f"requests `{summary['provider_requests']}`，recorded tokens `{summary['recorded_tokens']}`，"
            f"cost `${summary['provider_cost_microusd'] / 1_000_000:.6f}`，diagnostic `{summary['diagnostic_commands']}`，"
            f"replay closure `{summary['replay_closure_events']}`，repair windows `{summary['repair_windows_opened']}`。"
        )
    primary = q["primary_analysis"]
    activation = q["mechanism_activation"]
    bootstrap = primary["clustered_bootstrap"]
    lower = bootstrap["one_sided_95_lower"] if bootstrap is not None else None
    point = primary["strict_success_difference"]
    point_text = "NA" if point is None else f"{point:.3f}"
    lower_text = "NA" if lower is None else f"{lower:.3f}"
    lines.extend(
        [
            "",
            "## 主要分析",
            "",
            f"- H2-H1 strict success 差值：`{point_text}`；",
            f"- 项目族 bootstrap 单侧 95% 下界：`{lower_text}`，非劣界 `{NONINFERIORITY_MARGIN:.2f}`；",
            f"- 非劣：`{primary['noninferiority_passed']}`；机制自然激活：`{activation['activated']}`；",
            f"- H1 S5 replay failure `{activation['h1_external_replay_failures']}`，H2 closure rejection `{activation['h2_replay_closure_rejections']}`，repair window `{activation['h2_repair_windows_opened']}`。",
            "",
            "## 硬门禁",
            "",
        ]
    )
    lines.extend(
        f"- `{name}`：{'通过' if value else '失败'}"
        for name, value in q["hard_gates"].items()
    )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            report["interpretation_boundary"],
            "",
            "## Evidence",
            "",
            f"- Manifest canonical SHA-256：`{audited['manifest_sha256']}`；",
            f"- Inventory canonical SHA-256：`{audited['inventory']['canonical_sha256']}`；",
            f"- Evidence files：`{audited['inventory']['file_count']}`，`{audited['inventory']['total_bytes']}` bytes。",
        ]
    )
    REPORT_MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return report


def seal(manifest: dict[str, Any]) -> dict[str, Any]:
    audited = audit(manifest, seal=True)
    if not audited["valid"]:
        raise QualificationError("封存前 evidence audit 未通过")
    return write_report(manifest)


def plan(manifest: dict[str, Any]) -> dict[str, Any]:
    validate_manifest(manifest, require_components=False)
    return {
        "identity": IDENTITY,
        "issue": TRACKING_ISSUE,
        "tasks": [task["task_id"] for task in manifest["tasks"]],
        "schedule": manifest["schedule"],
        "provider": manifest["provider"]["profile"],
        "provider_request_ceiling": manifest["budget"]["total_provider_requests"],
        "provider_recorded_token_ceiling": manifest["budget"][
            "total_authorized_recorded_tokens"
        ],
        "provider_cost_usd_ceiling": manifest["budget"][
            "total_provider_cost_usd_ceiling"
        ],
        "primary_estimand": manifest["analysis"]["primary_estimand"],
        "noninferiority_margin": manifest["analysis"]["noninferiority_margin"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "generate",
            "validate",
            "plan",
            "preflight-q0",
            "q0",
            "preflight-q1",
            "q1",
            "audit",
            "seal",
            "report",
        ),
    )
    arguments = parser.parse_args(argv)
    if arguments.command == "generate":
        manifest = generate_manifest()
        _write_json(MANIFEST_PATH, manifest)
        _write_json(SCHEMA_PATH, schema_document(manifest))
        payload: Any = {
            "manifest": str(MANIFEST_PATH.relative_to(REPO_ROOT)),
            "schema": str(SCHEMA_PATH.relative_to(REPO_ROOT)),
            "manifest_sha256": _canonical_sha256(manifest),
        }
    else:
        manifest = _manifest()
        if arguments.command == "validate":
            payload = {
                "valid": True,
                "manifest_sha256": _canonical_sha256(validate_manifest(manifest)),
            }
        elif arguments.command == "plan":
            payload = plan(manifest)
        elif arguments.command == "preflight-q0":
            payload = preflight(manifest, phase="q0", require_absent_evidence=True)
        elif arguments.command == "q0":
            payload = execute_q0(manifest)
        elif arguments.command == "preflight-q1":
            payload = preflight(manifest, phase="q1")
        elif arguments.command == "q1":
            payload = execute_q1(manifest)
        elif arguments.command == "audit":
            payload = audit(manifest)
        elif arguments.command == "seal":
            payload = seal(manifest)
        else:
            payload = write_report(manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
