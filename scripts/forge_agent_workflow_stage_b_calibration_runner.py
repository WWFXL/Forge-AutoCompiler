#!/usr/bin/env python3
"""Issue #289 Phase 5 候选 runner；真实执行需 authorized amendment。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_agent_workflow_stage_b_calibration_protocol as protocol  # noqa: E402

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST


class Phase5RunnerError(RuntimeError):
    """Phase 5 runner 未获授权或运行合同无效。"""


def validate_runtime(manifest: dict[str, Any], repo_root: Path = protocol.REPO_ROOT) -> dict[str, Any]:
    validated = protocol.validate_manifest(manifest, repo_root)
    runtime = validated["runtime_candidate"]
    if runtime["orchestration_mode"] != "agent_workflow_node_v1":
        raise Phase5RunnerError("Phase 5 orchestration mode 发生漂移")
    if runtime["external_evaluator"] != "external-evaluator-v1":
        raise Phase5RunnerError("Phase 5 evaluator identity 发生漂移")
    if not runtime["clean_replay_required"] or not runtime["finalize_and_cleanup_required"] or not runtime["zero_managed_orphans_required"]:
        raise Phase5RunnerError("Phase 5 lifecycle 不变量未冻结")
    return {
        "status": "candidate_valid_not_authorized",
        "manifest_sha256": protocol.canonical_sha256(validated),
        "task_count": len(validated["tasks"]),
        "schedule": validated["schedule"]["order"],
        "provider_calls": 0,
        "credential_reads": 0,
        "docker_executions": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
        "evidence_writes": 0,
    }


def _require_execution_authorization(manifest: dict[str, Any]) -> None:
    authorization = manifest["authorization"]
    required = (
        "provider_calls_authorized",
        "credential_read_authorized",
        "model_creation_authorized",
        "reachability_request_authorized",
        "docker_execution_authorized",
        "evidence_write_authorized",
        "formal_attempts_authorized",
    )
    if not all(authorization[field] is True for field in required) or authorization["model_tokens_authorized"] <= 0:
        raise Phase5RunnerError("Phase 5 candidate 未授权真实执行；必须先合并并派生 authorized amendment")
    if manifest["environment_candidate"]["image_id"] is None:
        raise Phase5RunnerError("authorized amendment 必须冻结完整 Docker image ID")


def execute_reachability(manifest: dict[str, Any]) -> dict[str, Any]:
    validate_runtime(manifest)
    _require_execution_authorization(manifest)
    raise Phase5RunnerError("当前 candidate runner 不接受真实 reachability；请使用版本化 authorized runner")


def run_batch(manifest: dict[str, Any]) -> dict[str, Any]:
    validate_runtime(manifest)
    _require_execution_authorization(manifest)
    raise Phase5RunnerError("当前 candidate runner 不接受真实 batch；请使用版本化 authorized runner")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "audit", "preflight", "reachability", "batch"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest(args.manifest)
    if args.command == "validate":
        result: Any = validate_runtime(manifest)
    elif args.command == "audit":
        result = manifest["historical_baseline"]["audit"]
    elif args.command == "preflight":
        result = protocol.collect_preflight(manifest)
    elif args.command == "reachability":
        result = execute_reachability(manifest)
    else:
        result = run_batch(manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
