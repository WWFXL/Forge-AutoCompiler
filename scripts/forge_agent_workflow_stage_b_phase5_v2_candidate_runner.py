#!/usr/bin/env python3
"""校验 Phase 5 v2 candidate；真实执行等待独立授权修订。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import MappingProxyType
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_agent_workflow_stage_b_phase5_v2_candidate_protocol as protocol  # noqa: E402

from deerflow.compile.agent_workflow_schemas import (  # noqa: E402
    AgentBuildNodeInput,
    AgentWorkflowBudget,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowTargetContract,
)

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_QUALIFICATION_RESULT = protocol.DEFAULT_QUALIFICATION_RESULT


class Phase5V2CandidateRunnerError(RuntimeError):
    """Phase 5 v2 candidate runtime、qualification 或授权边界无效。"""


def validate_runtime(
    manifest: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    validated = protocol.validate_manifest(manifest, repo_root)
    runtime = validated["runtime_candidate"]
    expected = {
        "orchestration_mode": "agent_workflow_node_v1",
        "external_evaluator": "external-evaluator-v2",
        "qualification_revalidation_before_model_creation": True,
        "clean_replay_required": True,
        "finalize_and_cleanup_required": True,
        "zero_managed_orphans_required": True,
    }
    for field, value in expected.items():
        if runtime.get(field) != value:
            raise Phase5V2CandidateRunnerError(
                f"Phase 5 v2 runtime identity 发生漂移: {field}"
            )
    if (
        runtime.get("protocol_path") != protocol.PROTOCOL_PATH
        or runtime.get("runner_path") != protocol.RUNNER_PATH
    ):
        raise Phase5V2CandidateRunnerError(
            "Phase 5 v2 protocol/runner identity 发生漂移"
        )
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


def collect_preflight(
    manifest: dict[str, Any],
    qualification_result_path: Path = DEFAULT_QUALIFICATION_RESULT,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    validate_runtime(manifest, repo_root)
    result = protocol.collect_preflight(manifest, qualification_result_path, repo_root)
    if any(
        result[field] != 0
        for field in (
            "provider_calls",
            "credential_reads",
            "docker_executions",
            "formal_attempts",
            "model_tokens",
            "evidence_writes",
        )
    ):
        raise Phase5V2CandidateRunnerError(
            "Phase 5 v2 candidate preflight 违反 0 执行边界"
        )
    return result


def validate_runtime_probe(
    manifest: dict[str, Any],
    task: dict[str, Any],
    session: Any,
    primary: str,
) -> str:
    if session.commit_sha != task["commit_sha"]:
        raise Phase5V2CandidateRunnerError(f"{task['task_id']} exact commit 发生漂移")
    if session.image_id != manifest["environment_candidate"]["image_id"]:
        raise Phase5V2CandidateRunnerError(f"{task['task_id']} image identity 发生漂移")
    observed = list(session.build_system_capabilities)
    if (
        observed != task["build_system_capabilities"]
        or primary != task["selected_build_system"]
    ):
        raise Phase5V2CandidateRunnerError(
            f"{task['task_id']} build-system qualification 发生漂移"
        )
    existing = getattr(session, "selected_build_system", None)
    if existing not in (None, task["selected_build_system"]):
        raise Phase5V2CandidateRunnerError(
            f"{task['task_id']} Session build-system selection 发生漂移"
        )
    session.selected_build_system = task["selected_build_system"]
    return session.selected_build_system


def node_input(
    manifest: dict[str, Any],
    task: dict[str, Any],
    session: Any,
    attempt_id: str,
) -> AgentBuildNodeInput:
    protocol_hash = manifest["frozen_components"][protocol.PROTOCOL_PATH]
    runner_hash = manifest["frozen_components"][protocol.RUNNER_PATH]
    value = AgentBuildNodeInput(
        task_id=task["task_id"],
        attempt_id=attempt_id,
        session_id=session.session_id,
        repository_url=task["repository_url"],
        commit_sha=task["commit_sha"],
        build_system_candidates=tuple(task["build_system_capabilities"]),
        target_contract=AgentWorkflowTargetContract(
            target_id=task["target_contract"]["target_id"],
            artifact_types=tuple(task["target_contract"]["artifact_types"]),
            artifact_path_patterns=tuple(
                task["target_contract"]["artifact_path_patterns"]
            ),
            functional_oracle_ref=task["target_contract"]["functional_oracle_ref"],
        ),
        operation_policy_ref=manifest["operation_policy_ref"],
        environment=AgentWorkflowEnvironmentIdentity(
            image_id=manifest["environment_candidate"]["image_id"],
            parallel_jobs=manifest["environment_candidate"]["parallel_jobs"],
            network_policy=manifest["environment_candidate"]["network_policy"],
        ),
        budget=AgentWorkflowBudget(**manifest["budget_candidate"]["per_task"]),
        experiment_identity=AgentWorkflowExperimentIdentity(
            manifest_sha256=protocol.canonical_sha256(manifest),
            protocol_sha256=protocol_hash,
            runner_sha256=runner_hash,
        ),
        initial_observation=MappingProxyType(
            {
                "required_candidate_artifacts": tuple(
                    task["required_candidate_artifacts"]
                ),
                "functional_oracle": task["oracle"],
                "build_system_capabilities": tuple(task["build_system_capabilities"]),
                "selected_build_system": task["selected_build_system"],
                "qualification_result_sha256": manifest["qualification"][
                    "result_sha256"
                ],
            }
        ),
    )
    value.validate()
    return value


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
    if (
        not all(authorization[field] is True for field in required)
        or authorization["model_tokens_authorized"] <= 0
    ):
        raise Phase5V2CandidateRunnerError(
            "Phase 5 v2 candidate 未授权真实执行；必须先派生并合并独立 authorized amendment"
        )


def execute_reachability(manifest: dict[str, Any]) -> dict[str, Any]:
    validate_runtime(manifest)
    _require_execution_authorization(manifest)
    raise Phase5V2CandidateRunnerError("candidate runner 不接受真实 reachability")


def run_batch(manifest: dict[str, Any]) -> dict[str, Any]:
    validate_runtime(manifest)
    _require_execution_authorization(manifest)
    raise Phase5V2CandidateRunnerError("candidate runner 不接受真实 batch")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("validate", "preflight", "reachability", "batch")
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--qualification-result", type=Path, default=DEFAULT_QUALIFICATION_RESULT
    )
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest(args.manifest)
    if args.command == "validate":
        result: Any = validate_runtime(manifest)
    elif args.command == "preflight":
        result = collect_preflight(manifest, args.qualification_result)
    elif args.command == "reachability":
        result = execute_reachability(manifest)
    else:
        result = run_batch(manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
