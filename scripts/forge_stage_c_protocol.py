#!/usr/bin/env python3
"""生成并校验 Stage C 十二项目配对校准的授权执行身份。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_stage_c_task_qualification as qualification  # noqa: E402

SCHEMA_VERSION = "forge-stage-c-paired-calibration-authorized-1.0.0"
DOCUMENT_TYPE = "forge_stage_c_paired_calibration_authorized"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/312"
AUTHORIZATION_BASELINE_COMMIT = "d161e41e58b855640b3c8e09cfacfcfd3aa661ea"
MANIFEST_RELATIVE_PATH = (
    "benchmarks/manifests/cpp-stage-c-paired-calibration-authorized.json"
)
SCHEMA_RELATIVE_PATH = (
    "benchmarks/schemas/forge-stage-c-paired-calibration-authorized.schema.json"
)
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-stage-c-paired-calibration.md"
QUALIFICATION_RESULT_PATH = "benchmarks/fixtures/stage-c-task-qualification-result.json"
RUNNER_PATH = "scripts/forge_stage_c_runner.py"
PROTOCOL_PATH = "scripts/forge_stage_c_protocol.py"
BASELINE_ADAPTER_PATH = "scripts/forge_stage_c_controlled_baseline.py"
DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_RELATIVE_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_RELATIVE_PATH
DEFAULT_RESULT = REPO_ROOT / QUALIFICATION_RESULT_PATH


class StageCProtocolError(RuntimeError):
    """Stage C manifest、资格回执、调度或授权边界无效。"""


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
    return qualification.file_sha256(path)


def _selection_order(pool: dict[str, Any]) -> list[dict[str, Any]]:
    seed = pool["selection_seed"]
    return sorted(
        pool["tasks"],
        key=lambda item: qualification.selection_key(
            seed, item["repository_url"], item["commit_sha"]
        ),
    )


def _schedule(pool: dict[str, Any]) -> dict[str, Any]:
    projects = [task["task_id"] for task in _selection_order(pool)]
    pairs: list[dict[str, Any]] = []
    for replicate in (1, 2):
        for index, task_id in enumerate(projects):
            first_order = ["A", "B"] if index < 6 else ["B", "A"]
            arm_order = first_order if replicate == 1 else list(reversed(first_order))
            pair_id = f"stage-c-{task_id}-r{replicate}"
            pairs.append(
                {
                    "pair_id": pair_id,
                    "task_id": task_id,
                    "replicate": replicate,
                    "arm_order": arm_order,
                    "attempt_ids": {
                        arm: f"{pair_id}-{arm.lower()}" for arm in arm_order
                    },
                }
            )
    return {
        "selection_seed": pool["selection_seed"],
        "project_order": projects,
        "replicates_per_project": 2,
        "pair_count": 24,
        "physical_attempt_count": 48,
        "pairs": pairs,
        "first_arm_failure_blocks_second": False,
        "replacement": False,
        "retry": False,
        "backfill": False,
        "reorder_after_outcome": False,
    }


def _public_tasks(
    pool: dict[str, Any],
    plan: dict[str, Any],
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    plans = {task["task_id"]: task for task in plan["tasks"]}
    receipts = {task["task_id"]: task for task in result["tasks"]}
    tasks: list[dict[str, Any]] = []
    for source in pool["tasks"]:
        task_id = source["task_id"]
        task_plan = plans[task_id]
        receipt = receipts[task_id]
        task = copy.deepcopy(source)
        task["selection_key"] = qualification.selection_key(
            pool["selection_seed"], source["repository_url"], source["commit_sha"]
        )
        task["target_contract"] = copy.deepcopy(task_plan["target"])
        task["oracle"] = copy.deepcopy(task_plan["oracle"])
        task["qualification_receipt"] = {
            "passed": receipt["passed"],
            "bitwise_reproducible": receipt["bitwise_reproducible"],
            "replicate_count": len(receipt["replicates"]),
            "receipt_sha256": canonical_sha256(receipt),
        }
        tasks.append(task)
    return tasks


def _frozen_components(repo_root: Path) -> dict[str, str]:
    paths = (
        PREREGISTRATION_PATH,
        qualification.DEFAULT_POOL.relative_to(REPO_ROOT).as_posix(),
        qualification.DEFAULT_PLAN.relative_to(REPO_ROOT).as_posix(),
        qualification.DEFAULT_SCHEMA.relative_to(REPO_ROOT).as_posix(),
        QUALIFICATION_RESULT_PATH,
        "docker/compile/Dockerfile.stage-c",
        BASELINE_ADAPTER_PATH,
        PROTOCOL_PATH,
        RUNNER_PATH,
        "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v2.py",
        "backend/packages/harness/deerflow/compile/external_evaluator_v4.py",
    )
    missing = [path for path in paths if not (repo_root / path).is_file()]
    if missing:
        raise StageCProtocolError(f"Stage C frozen component 缺失: {','.join(missing)}")
    return {path: file_sha256(repo_root / path) for path in paths}


def generate_manifest(
    repo_root: Path = REPO_ROOT,
    *,
    result_path: Path | None = None,
) -> dict[str, Any]:
    pool = qualification.validate_source_pool(
        qualification.load_json(
            repo_root / qualification.DEFAULT_POOL.relative_to(REPO_ROOT)
        )
    )
    plan = qualification.validate_plan(
        qualification.load_json(
            repo_root / qualification.DEFAULT_PLAN.relative_to(REPO_ROOT)
        ),
        pool=pool,
        check_schema_file=repo_root == REPO_ROOT,
    )
    actual_result_path = result_path or repo_root / QUALIFICATION_RESULT_PATH
    result = qualification.validate_result(
        qualification.load_json(actual_result_path), plan, pool
    )
    preregistration = repo_root / PREREGISTRATION_PATH
    if not preregistration.is_file():
        raise StageCProtocolError("Stage C 预注册不存在")
    schedule = _schedule(pool)
    per_arm_tokens = 300_000
    reachability_tokens = 5_000
    total_tokens = (
        schedule["physical_attempt_count"] * per_arm_tokens + reachability_tokens
    )
    if total_tokens != 14_405_000:
        raise StageCProtocolError("Stage C token ceiling 计算错误")
    return {
        "$schema": "../schemas/forge-stage-c-paired-calibration-authorized.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "issue_url": ISSUE_URL,
        "status": "authorized_not_executed",
        "purpose": "stage_c_controlled_paired_calibration",
        "authorization": {
            "provider_calls_authorized": True,
            "credential_read_authorized": True,
            "model_creation_authorized": True,
            "reachability_request_authorized": True,
            "docker_execution_authorized": True,
            "evidence_write_authorized": True,
            "formal_stage_c_attempts_authorized": True,
            "model_tokens_authorized": total_tokens,
            "stage_c_execution_started": False,
        },
        "qualification": {
            "plan_path": qualification.DEFAULT_PLAN.relative_to(REPO_ROOT).as_posix(),
            "plan_canonical_sha256": canonical_sha256(plan),
            "result_path": QUALIFICATION_RESULT_PATH,
            "result_file_sha256": file_sha256(actual_result_path),
            "result_canonical_sha256": canonical_sha256(result),
            "reference_build_count": result["reference_build_count"],
            "provider_request_count": 0,
            "formal_stage_c_attempt_created": False,
        },
        "environment": {
            "compile_image": plan["environment"]["image_tag"],
            "image_id": result["image_id"],
            "base_image_digest": plan["environment"]["base_image_digest"],
            "ubuntu_snapshot": result["ubuntu_snapshot"],
            "parallel_jobs": 4,
            "cpu_limit": 4,
            "network_policy": {
                "source_clone": "task_remote_and_exact_submodules_only",
                "dependency": "frozen_image_only",
                "configure_build_stage_oracle_replay": "none",
            },
            "fresh_workspace_per_arm": True,
            "mutable_cache_shared": False,
        },
        "provider": {
            "provider": "deepseek",
            "profile": "deepseek-flash",
            "actual_model": "deepseek-flash",
            "endpoint": "https://api.deepseek.com",
            "credential_env_name": "DEEPSEEK_API_KEY",
            "request_timeout_seconds": 300,
            "model_max_retries": 0,
            "fallback_enabled": False,
            "parallel_tool_calls": False,
            "temperature": "provider_default_unsupported_freeze",
            "top_p": "provider_default_unsupported_freeze",
            "seed": "provider_unsupported",
        },
        "budget": {
            "per_arm": {
                "max_recorded_tokens": per_arm_tokens,
                "max_model_requests": 24,
                "work_timeout_seconds": 1800,
                "cleanup_reserve_seconds": 120,
                "command_timeout_seconds": 900,
                "evaluator_timeout_seconds": 1800,
                "replay_timeout_seconds": 1800,
                "forge_max_agent_steps": 64,
                "forge_max_tool_calls": 48,
                "forge_max_commands": 32,
            },
            "reachability_max_requests": 1,
            "reachability_max_recorded_tokens": reachability_tokens,
            "formal_arm_count": 48,
            "formal_arms_max_recorded_tokens": 14_400_000,
            "total_max_recorded_tokens": total_tokens,
            "pair_boundary_gate": True,
        },
        "methods": {
            "A": {
                "name": "cxxcrafter-controlled",
                "adapter_path": BASELINE_ADAPTER_PATH,
                "control_flow": [
                    "parser",
                    "dockerfile_generator",
                    "executor",
                    "llm_judge",
                    "modifier_loop",
                ],
                "internal_judge_is_final_truth": False,
            },
            "B": {
                "name": "forge-agent-workflow-node-v2",
                "runtime_path": "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v2.py",
                "zero_model_fast_path": False,
                "evaluator_feedback_to_agent": False,
            },
        },
        "candidate_contract": {
            "schema_version": "forge-stage-c-unified-candidate-1.0.0",
            "kinds": {"A": "dockerfile", "B": "forge_submit_candidate_v1"},
            "required_identity": [
                "manifest_sha256",
                "release_revision",
                "task_id",
                "pair_id",
                "replicate",
                "arm",
                "attempt_id",
                "candidate_sha256",
                "artifact_manifest_sha256",
            ],
        },
        "external_evaluator": {
            "name": "stage-c-unified-external-evaluator-v1",
            "forge_backend": "external-evaluator-v4",
            "forge_backend_path": "backend/packages/harness/deerflow/compile/external_evaluator_v4.py",
            "layers": ["S0", "S1", "S2", "S3", "S4", "S5"],
            "strict_success": "all_layers_passed",
            "result_feedback_to_method": False,
        },
        "tasks": _public_tasks(pool, plan, result),
        "schedule": schedule,
        "analysis": {
            "independent_unit": "project",
            "primary_estimand": "mean_project_level_paired_delta",
            "pair_delta": "strict_success_B_minus_strict_success_A",
            "project_score": "mean_of_two_replicate_pair_deltas",
            "stage_b_outcomes_imported": False,
            "incomplete_pair_in_paired_estimate": False,
            "deployment_itt_includes_all_registered_arms": True,
        },
        "execution": {
            "authorization_baseline_commit": AUTHORIZATION_BASELINE_COMMIT,
            "release_branch": "main",
            "release_revision_policy": "descendant_of_authorization_baseline_and_record_each_attempt",
            "network_access_medium_env": "FORGE_NETWORK_ACCESS_MEDIUM",
            "network_access_medium": "ethernet",
            "evidence_directory": "/workspace/.compile-sessions/benchmark-evidence-stage-c-paired-calibration-v1",
            "create_once": True,
            "commands": ["validate", "preflight", "reachability", "batch", "report"],
            "reachability_marker": "markers/reachability.json",
            "reachability_report": "reports/reachability.json",
            "batch_marker": "markers/batch.json",
            "batch_report": "reports/stage-c-deployment.json",
            "paired_report": "reports/stage-c-paired.json",
            "inventory_report": "reports/stage-c-inventory.json",
            "pair_path": "pairs/{pair_id}",
            "arm_result_path": "pairs/{pair_id}/{arm}/result.json",
            "resume_policy": "completed_contiguous_pair_prefix_only",
        },
        "preregistration": {
            "path": PREREGISTRATION_PATH,
            "file_sha256": file_sha256(preregistration),
        },
        "frozen_components": _frozen_components(repo_root),
    }


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-stage-c-paired-calibration-authorized.schema.json",
        "title": "Forge Stage C paired calibration authorized",
        "const": manifest,
    }


def validate_manifest(
    value: dict[str, Any],
    repo_root: Path = REPO_ROOT,
    *,
    result_path: Path | None = None,
    check_schema_file: bool = True,
) -> dict[str, Any]:
    expected = generate_manifest(repo_root, result_path=result_path)
    if value != expected:
        raise StageCProtocolError("Stage C manifest 与确定性生成结果不一致")
    schedule = value["schedule"]
    if len(schedule["pairs"]) != 24:
        raise StageCProtocolError("Stage C 必须包含 24 pairs")
    counts = {"A": 0, "B": 0}
    project_orders: dict[str, list[list[str]]] = {}
    for pair in schedule["pairs"]:
        if sorted(pair["arm_order"]) != ["A", "B"]:
            raise StageCProtocolError("每个 pair 必须且只能包含 A/B 两臂")
        counts[pair["arm_order"][0]] += 1
        project_orders.setdefault(pair["task_id"], []).append(pair["arm_order"])
    if counts != {"A": 12, "B": 12}:
        raise StageCProtocolError("Stage C 首臂顺序未平衡")
    if any(
        len(orders) != 2 or orders[1] != list(reversed(orders[0]))
        for orders in project_orders.values()
    ):
        raise StageCProtocolError("项目内 replicate arm order 未反向平衡")
    if any("reference_recipe" in task for task in value["tasks"]):
        raise StageCProtocolError("Stage C public manifest 泄漏 reference recipe")
    schema = generate_schema(expected)
    jsonschema.Draft202012Validator.check_schema(schema)
    if check_schema_file:
        schema_path = repo_root / SCHEMA_RELATIVE_PATH
        if not schema_path.is_file() or qualification.load_json(schema_path) != schema:
            raise StageCProtocolError("Stage C const Schema 缺失或漂移")
        jsonschema.validate(value, qualification.load_json(schema_path))
    return value


def load_manifest(
    path: Path = DEFAULT_MANIFEST,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    return validate_manifest(qualification.load_json(path), repo_root)


def release_revision(repo_root: Path = REPO_ROOT) -> str:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", AUTHORIZATION_BASELINE_COMMIT, revision],
        cwd=repo_root,
        check=False,
    )
    if ancestor.returncode != 0:
        raise StageCProtocolError("当前 release 不是 authorization baseline 的后代")
    return revision


def write_generated(manifest: dict[str, Any]) -> None:
    DEFAULT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_SCHEMA.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    DEFAULT_SCHEMA.write_text(
        json.dumps(
            generate_schema(manifest), ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate", "show-schedule"))
    args = parser.parse_args(argv)
    if args.command == "generate":
        manifest = generate_manifest()
        write_generated(manifest)
        result: Any = {
            "status": "generated",
            "manifest_sha256": canonical_sha256(manifest),
            "pair_count": 24,
            "physical_attempt_count": 48,
        }
    else:
        manifest = load_manifest()
        if args.command == "validate":
            result = {
                "status": "valid",
                "manifest_sha256": canonical_sha256(manifest),
                "release_revision": release_revision(),
                "provider_calls": 0,
                "formal_stage_c_attempts": 0,
                "model_tokens": 0,
            }
        else:
            result = manifest["schedule"]
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
