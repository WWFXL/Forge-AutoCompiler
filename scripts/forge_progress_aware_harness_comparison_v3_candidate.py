#!/usr/bin/env python3
"""Issue #438：生成并校验 H0/H1 v3 未授权确认性复现 candidate。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent

IDENTITY = "cpp-progress-aware-harness-comparison-v3-candidate"
TRACKING_ISSUE = 438
BRANCH = "yiwei/438-h0-h1-v3-replication"
SCHEMA_ID = "forge-progress-aware-harness-comparison-v3-candidate"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests" / f"{IDENTITY}.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas" / f"{SCHEMA_ID}.schema.json"
PREREGISTRATION_PATH = REPO_ROOT / "benchmarks/preregistrations" / f"{IDENTITY}.md"
SPEC_PATH = REPO_ROOT / "docs/superpowers/specs/2026-10-13-progress-aware-harness-comparison-v3-design.md"
PLAN_PATH = REPO_ROOT / "docs/superpowers/plans/2026-10-13-progress-aware-harness-comparison-v3.md"

PARENT_MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-progress-aware-harness-comparison-v2.json"
PARENT_MANIFEST_CANONICAL_SHA256 = "2891fcf708efda329686fb31b11abb25ec20e5716fa5219c5859a13c9a015018"
PARENT_EVIDENCE_ROOT = REPO_ROOT / ".compile-sessions/benchmark-evidence-progress-aware-harness-comparison-v2"
PARENT_INVENTORY_CANONICAL_SHA256 = "fb8f77bf05885dcb2f008fc2799de8361f7dd91af558815b7cff42b01cd5dce8"
CHECKPOINT_EVIDENCE_ROOT = REPO_ROOT / ".compile-sessions/benchmark-evidence-dynamic-budget-trajectory-qualification-v5"
CHECKPOINT_INVENTORY_CANONICAL_SHA256 = "b29d6738344771f2b1a31d4d874390342fadfe5d6cad79db0d6a6c83f40d35d1"

FROZEN_REPORTS = {
    "benchmarks/reports/cpp-progress-aware-harness-comparison-v2.json": "04a649c2bc3ec2e224fab3e449f6b771b05d7ba1cc18e74e844868573858d29a",
    "benchmarks/reports/cpp-progress-aware-harness-comparison-v2.md": "2e75516fb05f5d3a2952b65bfbc21ac4df5796a3f3067d008e50696f2df9742f",
    "benchmarks/reports/cpp-agent-token-budget-semantics-gate-v1.json": "1360c61e7588ab81242520807dac98d79e42a0788813fedebe3fb9c1cf36c6b1",
    "benchmarks/reports/cpp-agent-token-budget-semantics-gate-v1.md": "c9887c7bc7af3de0e148ed9cf985718d99c6b1a6056d30a72a64b528fd298368",
}

COMPONENT_PATHS = (
    "scripts/forge_progress_aware_harness_comparison_v3_candidate.py",
    "scripts/forge_progress_aware_harness_comparison_v2.py",
    "scripts/forge_progress_aware_harness_comparison_v1.py",
    "scripts/forge_agent_continuation_qualification_v2.py",
    "scripts/forge_checkpoint_archive.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_node.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v3.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v4.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_schemas.py",
    "backend/packages/harness/deerflow/compile/candidate_verifier.py",
    "backend/packages/harness/deerflow/compile/external_evaluator_v4.py",
    "backend/packages/harness/deerflow/compile/operations.py",
    "backend/packages/harness/deerflow/tools/bound_compile_tools.py",
    "benchmarks/preregistrations/cpp-progress-aware-harness-comparison-v3-candidate.md",
    "docs/superpowers/specs/2026-10-13-progress-aware-harness-comparison-v3-design.md",
    "docs/superpowers/plans/2026-10-13-progress-aware-harness-comparison-v3.md",
)

DEPTH_ROTATION = {1: 3, 2: 1, 3: 2}
CANARY_CHECKPOINTS = (
    {"task_id": "cmake-cli11", "checkpoint_state_id": "cmake-cli11-state-3"},
    {"task_id": "make-tiny-aes-c", "checkpoint_state_id": "make-tiny-aes-c-state-3"},
    {"task_id": "autotools-libfastjson", "checkpoint_state_id": "autotools-libfastjson-state-3"},
)


class CandidateError(RuntimeError):
    """Candidate identity、父证据或未授权边界发生漂移。"""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise CandidateError(f"JSON 根必须是 object: {path}")
    return value


def _parent_manifest() -> dict[str, Any]:
    parent = _load_json(PARENT_MANIFEST_PATH)
    if canonical_sha256(parent) != PARENT_MANIFEST_CANONICAL_SHA256:
        raise CandidateError("v2 manifest canonical identity 漂移")
    return parent


def _inventory_identity(root: Path, expected: str, *, verify_files: bool) -> dict[str, Any]:
    inventory = _load_json(root / "inventory.json")
    files = inventory.get("files")
    if not isinstance(files, list) or inventory.get("canonical_sha256") != expected or canonical_sha256(files) != expected:
        raise CandidateError(f"冻结 inventory 漂移: {root.name}")
    if verify_files:
        for item in files:
            path = root / item["path"]
            if not path.is_file() or path.stat().st_size != item["size"] or file_sha256(path) != item["sha256"]:
                raise CandidateError(f"冻结 evidence 文件漂移: {root.name}/{item['path']}")
    return {
        "canonical_sha256": expected,
        "file_count": len(files),
        "total_bytes": sum(item["size"] for item in files),
    }


def _state_depth(state_id: str) -> int:
    match = re.fullmatch(r".+-state-([123])", state_id)
    if match is None:
        raise CandidateError(f"无效 checkpoint state id: {state_id}")
    return int(match.group(1))


def _rotated_tasks(parent: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for parent_task in parent["tasks"]:
        task = copy.deepcopy(parent_task)
        old_state = task["checkpoint_state_id"]
        new_depth = DEPTH_ROTATION[_state_depth(old_state)]
        task["checkpoint_state_id"] = f"{task['task_id']}-state-{new_depth}"
        tasks.append(task)
    return tasks


def _observed_v2_effect_checkpoints() -> set[str]:
    observed: set[str] = set()
    for phase in ("q1", "q2"):
        result = _load_json(PARENT_EVIDENCE_ROOT / phase / "result.json")
        for item in result.get("outcomes", []):
            state_id = item.get("checkpoint_state_id")
            if isinstance(state_id, str):
                observed.add(state_id)
    if len(observed) != 12:
        raise CandidateError("v2 effect checkpoint 集合漂移")
    return observed


def _validate_checkpoint(task: dict[str, Any]) -> dict[str, Any]:
    state_id = task["checkpoint_state_id"]
    checkpoint_dir = CHECKPOINT_EVIDENCE_ROOT / "states" / state_id / "checkpoint"
    checkpoint = _load_json(checkpoint_dir / "checkpoint.json")
    if checkpoint.get("state_id") != state_id:
        raise CandidateError(f"checkpoint state identity 漂移: {state_id}")
    source = checkpoint.get("source", {})
    if source.get("repository_url") != task["repository_url"] or source.get("commit_sha") != task["commit_sha"]:
        raise CandidateError(f"checkpoint source identity 漂移: {state_id}")
    checkpoint_payload = {key: value for key, value in checkpoint.items() if key != "checkpoint_sha256"}
    if checkpoint.get("checkpoint_sha256") != canonical_sha256(checkpoint_payload):
        raise CandidateError(f"checkpoint hash 漂移: {state_id}")
    binary_files = {
        "workspace.tar.gz": checkpoint.get("workspace_snapshot_sha256"),
        "artifacts.tar.gz": checkpoint.get("artifacts_snapshot_sha256"),
    }
    for name, expected in binary_files.items():
        path = checkpoint_dir / name
        if not isinstance(expected, str) or file_sha256(path) != expected:
            raise CandidateError(f"checkpoint payload 漂移: {state_id}/{name}")
    json_files = {
        "message.json": checkpoint.get("message_sha256"),
        "budget.json": checkpoint.get("budget_sha256"),
    }
    for name, expected in json_files.items():
        if not isinstance(expected, str) or canonical_sha256(_load_json(checkpoint_dir / name)) != expected:
            raise CandidateError(f"checkpoint payload 漂移: {state_id}/{name}")
    return checkpoint


def _frozen_components() -> dict[str, str]:
    components: dict[str, str] = {}
    for relative in COMPONENT_PATHS:
        path = REPO_ROOT / relative
        if not path.is_file():
            raise CandidateError(f"冻结组件不存在: {relative}")
        components[relative] = file_sha256(path)
    return components


def generate_manifest() -> dict[str, Any]:
    parent = _parent_manifest()
    tasks = _rotated_tasks(parent)
    per_arm = copy.deepcopy(parent["budget"]["per_arm"])
    per_arm["max_recorded_tokens_per_response"] = 100_000
    qualification = copy.deepcopy(parent["qualification"])
    qualification["pass_decision"] = "supports_same_project_cross_state_progress_aware_harness_replication"
    value = {
        "$schema": SCHEMA_ID,
        "schema_version": "1.0.0",
        "identity": IDENTITY,
        "issue": TRACKING_ISSUE,
        "branch": BRANCH,
        "status": "candidate_not_authorized",
        "release_revision": None,
        "parent": copy.deepcopy(parent["parent"]),
        "observed_parent": {
            "identity": parent["identity"],
            "manifest_path": str(PARENT_MANIFEST_PATH.relative_to(REPO_ROOT)),
            "manifest_canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
            "evidence_root": str(PARENT_EVIDENCE_ROOT.relative_to(REPO_ROOT)),
            "inventory_canonical_sha256": PARENT_INVENTORY_CANONICAL_SHA256,
            "decision": "stop_progress_aware_harness_as_primary_mechanism",
            "result_observed_before_v3_design": True,
        },
        "engineering_gate": {
            "identity": "cpp-agent-token-budget-semantics-gate-v1",
            "decision": "proceed_to_progress_aware_harness_v3_replication_decision",
            "release_revision": "e158858fb913a95b4c2a2dad02e02eca03b98393",
            "report_sha256": copy.deepcopy(FROZEN_REPORTS),
        },
        "historical_controls": copy.deepcopy(parent["historical_controls"]),
        "authorization": {
            "credential_read_authorized": False,
            "provider_calls_authorized": False,
            "model_creation_authorized": False,
            "docker_execution_authorized": False,
            "reference_execution_authorized": False,
            "canary_execution_authorized": False,
            "formal_execution_authorized": False,
            "formal_evidence_write_authorized": False,
            "historical_evidence_write_authorized": False,
            "replacement_authorized": False,
            "backfill_authorized": False,
            "controller_implementation_authorized": False,
            "jev_calls_authorized": False,
            "model_tokens_authorized": 0,
        },
        "environment": copy.deepcopy(parent["environment"]),
        "provider": {**copy.deepcopy(parent["provider"]), "status": "selected_not_authorized"},
        "budget": {
            "per_arm": per_arm,
            "provider_arms": 60,
            "total_provider_requests": 1_440,
            "total_recorded_tokens_stop_threshold": 18_000_000,
            "total_authorized_recorded_tokens": 24_000_000,
            "total_provider_cost_usd_ceiling": 28.8,
        },
        "planned_evidence_root": ".compile-sessions/benchmark-evidence-progress-aware-harness-comparison-v3",
        "components": _frozen_components(),
        "source_archives": copy.deepcopy(parent["source_archives"]),
        "tasks": tasks,
        "canary_checkpoints": [copy.deepcopy(item) for item in CANARY_CHECKPOINTS],
        "formal_schedule": copy.deepcopy(parent["formal_schedule"]),
        "treatments": {
            "h0": "h0_runtime_v3",
            "h1": "h1_runtime_v4",
            "treatment_definition_changed_from_v2": False,
        },
        "qualification": qualification,
        "replication": {
            "classification": "post_observation_same_project_cross_state_confirmatory_replication",
            "project_families_reused": 9,
            "formal_effect_checkpoints_reused_from_v2": 0,
            "checkpoint_selection_rule": "v2_depth_rotation_1_to_3_2_to_1_3_to_2",
            "historical_outcomes_imported": False,
            "historical_effect_estimates_pooled": False,
            "v2_observed_summary": {
                "h0_strict": 16,
                "h1_strict": 22,
                "formal_arms_per_treatment": 27,
                "h0_provider_cost_usd": 1.619287,
                "h1_provider_cost_usd": 0.707752,
                "budget_complete": False,
            },
            "maximum_observed_v2_response_tokens": 60_594,
            "claim_scope": "same_project_families_cross_checkpoint_depths",
            "unseen_project_generalization": False,
        },
        "preregistration": {
            "path": str(PREREGISTRATION_PATH.relative_to(REPO_ROOT)),
            "sha256": file_sha256(PREREGISTRATION_PATH),
        },
        "future_execution": {
            "authorized_identity_required": True,
            "candidate_manifest_mutation_forbidden": True,
            "q0_q1_q2_available": False,
        },
    }
    return value


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "Forge progress-aware harness H0/H1 v3 candidate",
        "const": manifest or generate_manifest(),
    }


def validate_manifest(value: Any, *, verify_inventory_files: bool = False) -> dict[str, Any]:
    expected = generate_manifest()
    if not isinstance(value, dict) or value != expected:
        raise CandidateError("v3 candidate manifest 发生漂移")
    authorization = value["authorization"]
    if any(item is not False for key, item in authorization.items() if key.endswith("_authorized") and key != "model_tokens_authorized"):
        raise CandidateError("candidate 意外授权了外部工作")
    if authorization["model_tokens_authorized"] != 0:
        raise CandidateError("candidate 意外授权了 model token")

    per_arm = value["budget"]["per_arm"]
    if per_arm["max_recorded_tokens"] != 300_000 or per_arm["max_recorded_tokens_per_response"] != 100_000:
        raise CandidateError("Token T/R 合同漂移")
    if value["budget"]["total_authorized_recorded_tokens"] != value["budget"]["provider_arms"] * 400_000:
        raise CandidateError("总体 Token 授权上界漂移")

    parent = _parent_manifest()
    if value["formal_schedule"] != parent["formal_schedule"] or value["source_archives"] != parent["source_archives"]:
        raise CandidateError("schedule 或 source archive 发生未声明变化")
    for task, parent_task in zip(value["tasks"], parent["tasks"], strict=True):
        normalized = copy.deepcopy(task)
        normalized["checkpoint_state_id"] = parent_task["checkpoint_state_id"]
        if normalized != parent_task:
            raise CandidateError(f"任务除 checkpoint 深度外发生变化: {task['task_id']}")

    observed = _observed_v2_effect_checkpoints()
    formal_states = {task["checkpoint_state_id"] for task in value["tasks"]}
    canary_states = {item["checkpoint_state_id"] for item in value["canary_checkpoints"]}
    if formal_states & observed or canary_states & observed or formal_states & canary_states:
        raise CandidateError("v3 checkpoint 与 v2 effect arm 或 canary 重叠")
    for task in value["tasks"]:
        _validate_checkpoint(task)
    task_by_id = {task["task_id"]: task for task in value["tasks"]}
    for canary in value["canary_checkpoints"]:
        task = copy.deepcopy(task_by_id[canary["task_id"]])
        task["checkpoint_state_id"] = canary["checkpoint_state_id"]
        _validate_checkpoint(task)

    _inventory_identity(PARENT_EVIDENCE_ROOT, PARENT_INVENTORY_CANONICAL_SHA256, verify_files=verify_inventory_files)
    _inventory_identity(CHECKPOINT_EVIDENCE_ROOT, CHECKPOINT_INVENTORY_CANONICAL_SHA256, verify_files=verify_inventory_files)
    for relative, expected_sha256 in FROZEN_REPORTS.items():
        if file_sha256(REPO_ROOT / relative) != expected_sha256:
            raise CandidateError(f"冻结报告漂移: {relative}")
    return value


def validate_static_gate(*, verify_inventory_files: bool = True) -> dict[str, Any]:
    manifest = validate_manifest(generate_manifest(), verify_inventory_files=verify_inventory_files)
    depths: dict[str, list[int]] = {}
    for task in manifest["tasks"]:
        depths.setdefault(task["build_system"], []).append(_state_depth(task["checkpoint_state_id"]))
    return {
        "status": "passed",
        "identity": IDENTITY,
        "manifest_canonical_sha256": canonical_sha256(manifest),
        "formal_checkpoints": len(manifest["tasks"]),
        "canary_checkpoints": len(manifest["canary_checkpoints"]),
        "formal_pairs": len(manifest["formal_schedule"]),
        "formal_arms": manifest["qualification"]["formal_arms"],
        "depths_by_build_system": {name: sorted(items) for name, items in sorted(depths.items())},
        "v2_effect_checkpoint_overlap": 0,
        "provider_calls": 0,
        "credential_read": False,
        "docker_executed": False,
        "formal_attempts": 0,
        "model_tokens": 0,
        "evidence_writes": 0,
    }


def plan() -> dict[str, Any]:
    manifest = validate_manifest(generate_manifest())
    return {
        "identity": manifest["identity"],
        "status": manifest["status"],
        "classification": manifest["replication"]["classification"],
        "formal_schedule": manifest["formal_schedule"],
        "formal_checkpoints": [task["checkpoint_state_id"] for task in manifest["tasks"]],
        "canary_checkpoints": manifest["canary_checkpoints"],
        "budget": manifest["budget"],
        "authorization": manifest["authorization"],
        "next_required_identity": "cpp-progress-aware-harness-comparison-v3-authorized",
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate", "plan", "static-gate"))
    arguments = parser.parse_args(argv)
    if arguments.command == "generate":
        manifest = generate_manifest()
        _write_json(MANIFEST_PATH, manifest)
        _write_json(SCHEMA_PATH, schema_document(manifest))
        payload = {"written": True, "manifest_canonical_sha256": canonical_sha256(manifest)}
    elif arguments.command == "validate":
        manifest = validate_manifest(_load_json(MANIFEST_PATH))
        if _load_json(SCHEMA_PATH) != schema_document(manifest):
            raise CandidateError("const Schema 发生漂移")
        payload = {"valid": True, "manifest_canonical_sha256": canonical_sha256(manifest)}
    elif arguments.command == "plan":
        payload = plan()
    else:
        payload = validate_static_gate()
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
