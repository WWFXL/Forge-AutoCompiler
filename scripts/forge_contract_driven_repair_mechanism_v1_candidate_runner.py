#!/usr/bin/env python3
"""只读检查契约驱动修复 mechanism v1 candidate；真实执行保持关闭。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_contract_driven_repair_mechanism_v1_candidate_protocol as protocol  # noqa: E402

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
READ_ONLY_COMMANDS = ("validate", "plan", "show-checkpoint")
BLOCKED_COMMANDS = ("reachability", "run", "batch")


class CandidateRunnerError(RuntimeError):
    """candidate runner 收到无效计划或真实执行请求。"""


def validate_candidate(manifest: dict[str, Any]) -> dict[str, Any]:
    validated = protocol.validate_manifest(manifest)
    runtime = validated["runtime_candidate"]
    if runtime["commands_allowed_by_candidate_runner"] != list(READ_ONLY_COMMANDS):
        raise CandidateRunnerError("candidate 只读命令集合发生漂移")
    if runtime["commands_fail_closed"] != list(BLOCKED_COMMANDS):
        raise CandidateRunnerError("candidate fail-closed 命令集合发生漂移")
    return {
        "status": "candidate_valid_not_authorized",
        "manifest_sha256": protocol.canonical_sha256(validated),
        "release_revision": None,
        "provider_calls": 0,
        "credential_reads": 0,
        "docker_executions": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
        "model_tokens": 0,
    }


def plan(manifest: dict[str, Any]) -> dict[str, Any]:
    validate_candidate(manifest)
    summary = protocol.plan_summary(manifest)
    summary["projects"] = manifest["schedule"]["projects"]
    summary["checkpoints"] = manifest["schedule"]["checkpoints"]
    return summary


def show_checkpoint(manifest: dict[str, Any], checkpoint_id: str) -> dict[str, Any]:
    validate_candidate(manifest)
    matches = [
        checkpoint
        for checkpoint in manifest["schedule"]["checkpoints"]
        if checkpoint["checkpoint_id"] == checkpoint_id
    ]
    if len(matches) != 1:
        raise CandidateRunnerError(f"未知或重复 checkpoint: {checkpoint_id}")
    return {
        "status": "candidate_checkpoint_not_authorized",
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "checkpoint": matches[0],
        "provider_calls": 0,
        "credential_reads": 0,
        "docker_executions": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
    }


def external_evaluator_identity(
    checkpoint: dict[str, Any], arm_plan: dict[str, Any]
) -> dict[str, str]:
    if arm_plan not in checkpoint.get("arms", []):
        raise CandidateRunnerError("evaluation arm 不属于指定 checkpoint")
    return {
        "opaque_evaluation_id": arm_plan["opaque_evaluation_id"],
        "checkpoint_id": checkpoint["checkpoint_id"],
        "task_id": checkpoint["task_id"],
    }


def _reject_execution(command: str) -> None:
    if command not in BLOCKED_COMMANDS:
        raise CandidateRunnerError(f"未知执行命令: {command}")
    raise CandidateRunnerError(
        f"candidate runner 禁止 {command}；必须先派生并合并独立 authorized identity"
    )


def execute_reachability() -> None:
    _reject_execution("reachability")


def run_arm() -> None:
    _reject_execution("run")


def run_batch() -> None:
    _reject_execution("batch")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=READ_ONLY_COMMANDS + BLOCKED_COMMANDS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--checkpoint-id")
    args = parser.parse_args(argv)

    if args.command in BLOCKED_COMMANDS:
        _reject_execution(args.command)
    manifest = protocol.load_manifest(args.manifest)
    if args.command == "validate":
        result: Any = validate_candidate(manifest)
    elif args.command == "plan":
        result = plan(manifest)
    else:
        if not args.checkpoint_id:
            parser.error("show-checkpoint 需要 --checkpoint-id")
        result = show_checkpoint(manifest, args.checkpoint_id)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
