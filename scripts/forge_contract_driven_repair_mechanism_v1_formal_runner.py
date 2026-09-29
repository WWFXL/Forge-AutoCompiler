#!/usr/bin/env python3
"""执行、恢复并审计契约驱动修复 mechanism v1 36-arm formal collection。"""

from __future__ import annotations

import argparse
import asyncio
import base64
import copy
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from typing import Any, override

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_contract_driven_repair_mechanism_v1_formal_protocol as protocol  # noqa: E402
import forge_runtime_v3_three_arm_qualification as qualification  # noqa: E402
import forge_stage_c_runner as stage_c  # noqa: E402
import forge_stage_c_v8_workspace_remediation_runner as stage_c_v8  # noqa: E402

from langchain.agents.middleware.types import (  # noqa: E402
    ModelCallResult,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import AIMessage  # noqa: E402

from deerflow.compile import agent_workflow_runtime as runtime_v1  # noqa: E402
from deerflow.compile import agent_workflow_runtime_v2 as runtime_v2  # noqa: E402
from deerflow.compile import agent_workflow_runtime_v3 as runtime_v3  # noqa: E402
from deerflow.compile.agent_workflow_node import AgentWorkflowBudgetSnapshot  # noqa: E402
from deerflow.compile.agent_workflow_schemas import (  # noqa: E402
    AgentBuildNodeInput,
    AgentBuildNodeResult,
    AgentWorkflowBudget,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowTargetContract,
    SubmitCandidateRequest,
)
from deerflow.compile.candidate_verifier import (  # noqa: E402
    CandidateVerifier,
    SystemOwnedFunctionalCheckRunner,
    scan_delivery,
)
from deerflow.compile.evidence import (  # noqa: E402
    ExperimentLedger,
    ExperimentPolicy,
    activate_experiment,
    deactivate_experiment,
    model_response_metadata,
    new_evidence_id,
)
from deerflow.compile.external_evaluator_v3 import (  # noqa: E402
    ForgeCompileEvaluationBackend,
    run_external_evaluator_v3,
)
from deerflow.compile.manager import CompileSessionManager  # noqa: E402
from deerflow.compile.operations import (  # noqa: E402
    cleanup_and_finalize_compile_session_impl,
    clone_repository_impl,
    get_compile_services,
    inspect_build_system_impl,
    prepare_compile_session_impl,
)
from deerflow.compile.schemas import CompileSession  # noqa: E402
from deerflow.tools.bound_compile_tools import _run_container_bash_impl  # noqa: E402

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_OUTPUT_DIR = REPO_ROOT / protocol.parent.parent.parent.EVIDENCE_DIRECTORY
CAPTURE_LABEL = "forge.contract-repair-formal.capture"
FORMAL_MARKER_SCHEMA_VERSION = "forge-contract-repair-formal-marker-1.0.0"
FORMAL_RESULT_SCHEMA_VERSION = "forge-contract-repair-formal-result-1.0.0"
FORMAL_REPORT_SCHEMA_VERSION = "forge-contract-repair-formal-report-1.0.0"
TERMINAL_ARM_STATUSES = frozenset({"complete", "endpoint_censored", "failed"})


class FormalRunnerError(RuntimeError):
    """正式采集 identity、evidence、运行时或分析合同无效。"""


class FormalFatalError(FormalRunnerError):
    """必须停止整个 identity 的基础设施或权威异常。"""


class EndpointCensoredError(FormalRunnerError):
    """Provider 在允许的一次 transport retry 后仍未返回可计量响应。"""


class ModelIdentityError(FormalFatalError):
    """Provider 返回的 actual model 与冻结 identity 不一致。"""


@dataclass
class ContinuationContext:
    checkpoint_id: str
    parent_request: dict[str, Any]
    parent_history: list[dict[str, Any]]
    feedback: dict[str, Any]
    parent_budget: AgentWorkflowBudgetSnapshot
    expected_model: str
    provenance_evaluator: Callable[[SubmitCandidateRequest], dict[str, Any]] | None
    request_attempts: list[dict[str, Any]]
    endpoint_censored: bool = False
    fatal_error_class: str | None = None


_active_continuation: ContinuationContext | None = None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FormalRunnerError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise FormalRunnerError(f"JSON 顶层必须为对象: {path}")
    return value


def _write_once(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise FormalRunnerError(f"不可覆盖已存在的 formal evidence: {path}") from exc


def _write_bytes_once(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise FormalRunnerError(f"不可覆盖已存在的 formal evidence: {path}") from exc


def _update_claimed_marker(path: Path, updates: Mapping[str, Any]) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise FormalRunnerError(f"formal marker 不存在或不是普通文件: {path}")
    marker = _load_json(path)
    marker.update(copy.deepcopy(dict(updates)))
    marker["updated_at"] = _utc_now()
    temporary = path.with_suffix(path.suffix + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise FormalRunnerError(f"formal marker 临时路径已存在: {temporary}")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(marker, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return marker


def _run_checked(argv: list[str], *, cwd: Path = REPO_ROOT, timeout: int = 120) -> str:
    result = subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-3000:]
        raise FormalRunnerError(f"命令失败: {shlex.join(argv)}: {detail}")
    return result.stdout.strip()


def _manifest_sha256(manifest: dict[str, Any]) -> str:
    return protocol.parent.parent.parent.candidate.canonical_sha256(manifest)


def _task(manifest: dict[str, Any], task_id: str) -> dict[str, Any]:
    matches = [
        item
        for item in manifest["formal_execution_tasks"]
        if item["task_id"] == task_id
    ]
    if len(matches) != 1:
        raise FormalRunnerError(f"formal task 缺失或重复: {task_id}")
    return matches[0]


def _checkpoint_slug(checkpoint: dict[str, Any]) -> str:
    return f"{checkpoint['task_id']}-{checkpoint['stratum']}".replace("_", "-")


def _checkpoint_paths(
    manifest: dict[str, Any], output_dir: Path, checkpoint: dict[str, Any]
) -> tuple[Path, Path]:
    values = {
        "checkpoint_sequence": checkpoint["checkpoint_sequence"],
        "checkpoint_slug": _checkpoint_slug(checkpoint),
    }
    execution = manifest["formal_execution"]
    return (
        output_dir / execution["checkpoint_marker_template"].format(**values),
        output_dir / execution["checkpoint_ledger_template"].format(**values),
    )


def _arm_paths(
    manifest: dict[str, Any], output_dir: Path, arm: dict[str, Any]
) -> dict[str, Path]:
    values = {
        "sequence": arm["sequence"],
        "opaque_clone_id": arm["opaque_clone_id"],
    }
    execution = manifest["formal_execution"]
    return {
        "marker": output_dir / execution["arm_marker_template"].format(**values),
        "result": output_dir / execution["arm_result_template"].format(**values),
        "ledger": output_dir / execution["arm_ledger_template"].format(**values),
        "runtime_events": output_dir
        / execution["arm_runtime_events_template"].format(**values),
        "candidate": output_dir / execution["arm_candidate_template"].format(**values),
    }


def _output_dir(manifest: dict[str, Any], output_dir: Path, repo_root: Path) -> Path:
    root = repo_root.resolve(strict=True)
    expected = root / manifest["candidate_evidence"]["directory"]
    if (
        output_dir.resolve(strict=False) != expected
        or expected.parent != root / ".compile-sessions"
        or output_dir.is_symlink()
    ):
        raise FormalRunnerError("formal evidence 未绑定到冻结的 create-once 路径")
    return expected


def _formal_relative_files(manifest: dict[str, Any]) -> set[str]:
    result = {
        manifest["formal_execution"]["batch_marker"],
        manifest["formal_execution"]["batch_report"],
    }
    for checkpoint in manifest["schedule"]["checkpoints"]:
        marker, ledger = _checkpoint_paths(manifest, Path("."), checkpoint)
        result.update({marker.as_posix(), ledger.as_posix()})
        for arm in checkpoint["arms"]:
            result.update(
                path.as_posix()
                for path in _arm_paths(manifest, Path("."), arm).values()
            )
    return result


def validate_runtime(
    manifest: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    execution = manifest["formal_execution"]
    if execution["commands"] != [
        "validate",
        "plan",
        "preflight",
        "batch",
        "report",
        "audit",
    ]:
        raise FormalRunnerError("formal runner 命令边界发生漂移")
    if len(_formal_relative_files(manifest)) != 2 + 12 * 2 + 36 * 5:
        raise FormalRunnerError("formal evidence path 数量或唯一性发生漂移")
    _validate_all_node_inputs(manifest)
    return {
        "status": "formal_collection_authorized_not_started",
        "manifest_sha256": _manifest_sha256(manifest),
        "checkpoint_count": 12,
        "arm_count": 36,
        "maximum_provider_request_attempts": 288,
        "provider_calls": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
        "model_tokens": 0,
    }


def _require_release_identity(repo_root: Path) -> dict[str, str]:
    revision = _run_checked(["git", "rev-parse", "HEAD"], cwd=repo_root)
    origin_main = _run_checked(["git", "rev-parse", "origin/main"], cwd=repo_root)
    branch = _run_checked(["git", "branch", "--show-current"], cwd=repo_root)
    dirty = _run_checked(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo_root
    )
    _run_checked(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            protocol.AVAILABILITY_AUDIT_RELEASE_REVISION,
            revision,
        ],
        cwd=repo_root,
    )
    if branch != "main" or revision != origin_main or dirty:
        raise FormalRunnerError("formal execution 要求干净 main 且 HEAD == origin/main")
    return {"revision": revision, "branch": branch, "origin_main": origin_main}


def _verify_availability(manifest: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    receipt = manifest["availability_receipt"]
    marker_path = output_dir / receipt["marker_path"]
    if (
        protocol.parent.parent.parent.candidate.file_sha256(marker_path)
        != receipt["marker_file_sha256"]
    ):
        raise FormalRunnerError("availability marker 文件哈希发生漂移")
    marker = _load_json(marker_path)
    attempt = marker.get("attempts", [{}])[-1]
    if (
        marker.get("status") != receipt["required_status"]
        or marker.get("passed") is not receipt["required_passed"]
        or marker.get("manifest_sha256") != receipt["manifest_canonical_sha256"]
        or marker.get("execution_revision") != receipt["execution_revision"]
        or marker.get("request_attempt_count") != receipt["request_attempt_count"]
        or marker.get("recorded_total_tokens") != receipt["recorded_total_tokens"]
        or marker.get("actual_model_required")
        != manifest["provider_candidate"]["actual_model"]
        or attempt.get("actual_model") != manifest["provider_candidate"]["actual_model"]
        or attempt.get("model_identity_match") is not True
        or attempt.get("tool_side_effect_count") != 0
    ):
        raise FormalRunnerError("availability marker 语义与 formal identity 不一致")
    return marker


def _provider_config_preflight(manifest: dict[str, Any]) -> None:
    from deerflow.config import get_app_config

    provider = manifest["provider_candidate"]
    configured = get_app_config().get_model_config(provider["profile"])
    if configured is None:
        raise FormalRunnerError("config.yaml 缺少冻结 Provider model")
    settings = configured.model_dump(exclude_none=True)
    endpoint = settings.get(
        "base_url", settings.get("api_base", settings.get("openai_api_base"))
    )
    if (
        settings.get("model") != provider["actual_model"]
        or endpoint is None
        or str(endpoint).rstrip("/") != provider["endpoint"].rstrip("/")
    ):
        raise FormalRunnerError("Provider model 或 endpoint 配置发生漂移")
    if not os.environ.get(provider["credential_env_name"], "").strip():
        raise FormalRunnerError("Provider credential env 未注入")


def _managed_resources() -> dict[str, list[str]]:
    containers = _run_checked(
        ["docker", "ps", "-a", "--format", "{{.Names}}"]
    ).splitlines()
    managed_containers = sorted(
        name
        for name in containers
        if name.startswith("forge-compile-")
        or name.startswith("forge-stage-c-")
        or name.startswith("forge-runtime-v3-")
    )
    images = _run_checked(
        ["docker", "images", "-q", "--filter", f"label={CAPTURE_LABEL}"]
    ).splitlines()
    return {"containers": managed_containers, "images": sorted(set(images))}


def _require_zero_managed_resources() -> None:
    stage_c.require_zero_managed_resources()
    resources = _managed_resources()
    if resources["containers"] or resources["images"]:
        raise FormalFatalError(
            "formal execution 存在 managed container 或 capture image orphan"
        )


def _require_docker_identity(manifest: dict[str, Any]) -> dict[str, str]:
    _run_checked(["bash", "scripts/require-docker-runtime.sh"])
    context = _run_checked(["docker", "context", "show"])
    endpoint = _run_checked(
        [
            "docker",
            "context",
            "inspect",
            context,
            "--format",
            "{{.Endpoints.docker.Host}}",
        ]
    )
    image = manifest["environment_identity"]
    observed = _run_checked(
        ["docker", "image", "inspect", image["compile_image"], "--format", "{{.Id}}"]
    )
    if endpoint != "unix:///var/run/docker.sock" or observed != image["image_id"]:
        raise FormalRunnerError("Docker endpoint 或 compile image identity 发生漂移")
    return {"context": context, "endpoint": endpoint, "image_id": observed}


def _existing_formal_files(manifest: dict[str, Any], output_dir: Path) -> list[str]:
    expected = _formal_relative_files(manifest)
    if not output_dir.exists():
        return []
    return sorted(
        relative
        for path in output_dir.rglob("*")
        if path.is_file()
        and (relative := path.relative_to(output_dir).as_posix()) in expected
    )


def collect_preflight(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    require_formal_absent: bool = True,
) -> dict[str, Any]:
    validate_runtime(manifest, repo_root)
    evidence = _output_dir(manifest, output_dir, repo_root)
    release = _require_release_identity(repo_root)
    docker = _require_docker_identity(manifest)
    _require_zero_managed_resources()
    availability = _verify_availability(manifest, evidence)
    formal_files = _existing_formal_files(manifest, evidence)
    if require_formal_absent and formal_files:
        raise FormalRunnerError(
            "formal preflight 要求 batch/checkpoint/arm evidence 尚不存在"
        )
    _provider_config_preflight(manifest)
    return {
        "ready": True,
        "status": "formal_collection_preflight_passed_not_started",
        "manifest_sha256": _manifest_sha256(manifest),
        "release_revision": release["revision"],
        "branch": release["branch"],
        "origin_main": release["origin_main"],
        "docker": docker,
        "availability_marker_sha256": protocol.AVAILABILITY_MARKER_FILE_SHA256,
        "availability_status": availability["status"],
        "formal_files": formal_files,
        "credential_check": "environment_variable_presence_only",
        "zero_managed_resources": True,
        "provider_calls": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
        "model_tokens": 0,
    }


def _load_terminal_arm(
    manifest: dict[str, Any], output_dir: Path, arm: dict[str, Any]
) -> dict[str, Any] | None:
    paths = _arm_paths(manifest, output_dir, arm)
    existing = {name for name, path in paths.items() if path.exists()}
    if not existing:
        return None
    if existing != set(paths):
        raise FormalRunnerError(
            f"arm {arm['sequence']} evidence 不是完整 create-once 终态"
        )
    marker = _load_json(paths["marker"])
    result = _load_json(paths["result"])
    if (
        marker.get("status") not in TERMINAL_ARM_STATUSES
        or result.get("status") != marker.get("status")
        or marker.get("sequence") != arm["sequence"]
        or result.get("sequence") != arm["sequence"]
        or marker.get("opaque_clone_id") != arm["opaque_clone_id"]
        or result.get("opaque_clone_id") != arm["opaque_clone_id"]
        or result.get("manifest_sha256") != _manifest_sha256(manifest)
    ):
        raise FormalRunnerError(f"arm {arm['sequence']} terminal evidence 无效")
    return result


def completed_prefix(
    manifest: dict[str, Any],
    output_dir: Path,
    *,
    require_checkpoint_boundary: bool = False,
) -> list[dict[str, Any]]:
    completed: list[dict[str, Any]] = []
    gap_seen = False
    for checkpoint in manifest["schedule"]["checkpoints"]:
        checkpoint_marker, checkpoint_ledger = _checkpoint_paths(
            manifest, output_dir, checkpoint
        )
        checkpoint_exists = checkpoint_marker.exists() or checkpoint_ledger.exists()
        for arm in checkpoint["arms"]:
            result = _load_terminal_arm(manifest, output_dir, arm)
            if result is None:
                gap_seen = True
            elif gap_seen:
                raise FormalRunnerError("formal evidence 不是冻结 schedule 的连续前缀")
            else:
                completed.append(result)
        if checkpoint_exists and not (
            checkpoint_marker.exists() and checkpoint_ledger.exists()
        ):
            raise FormalRunnerError("checkpoint evidence 处于不完整终态")
        if checkpoint_exists:
            checkpoint_value = qualification.validate_checkpoint(checkpoint_marker)
            if (
                checkpoint_value.get("formal_manifest_sha256")
                != _manifest_sha256(manifest)
                or checkpoint_value.get("checkpoint_id") != checkpoint["checkpoint_id"]
            ):
                raise FormalRunnerError("checkpoint marker 与 formal identity 不一致")
        arm_count = sum(
            result["checkpoint_id"] == checkpoint["checkpoint_id"]
            for result in completed
        )
        if (
            require_checkpoint_boundary
            and checkpoint_exists
            and arm_count not in {0, 3}
        ):
            raise FormalRunnerError("只允许恢复完整 checkpoint 前缀")
    return completed


def _exact_sign_flip(project_scores: list[float]) -> dict[str, Any]:
    if not project_scores:
        raise FormalRunnerError("exact sign-flip 缺少 project scores")
    observed = abs(sum(project_scores) / len(project_scores))
    statistics = [
        abs(
            sum(sign * score for sign, score in zip(signs, project_scores, strict=True))
            / len(project_scores)
        )
        for signs in product((-1, 1), repeat=len(project_scores))
    ]
    extreme = sum(value + 1e-12 >= observed for value in statistics)
    return {
        "method": "two_sided_exact_project_level_sign_flip",
        "project_scores": project_scores,
        "observed_mean": sum(project_scores) / len(project_scores),
        "permutation_count": len(statistics),
        "extreme_count": extreme,
        "p_value": extreme / len(statistics),
    }


def _comparison_analysis(
    manifest: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    lower: str,
    upper: str,
    confirmatory: bool,
) -> dict[str, Any]:
    by_key = {
        (item["checkpoint_id"], item["condition"]): item
        for item in results
        if item.get("status") == "complete"
    }
    observed: list[dict[str, Any]] = []
    project_scores: list[float] = []
    complete_projects = True
    for project in manifest["schedule"]["projects"]:
        differences: list[int] = []
        for stratum in ("delivery_target", "provenance"):
            checkpoint_id = f"{project['task_id']}:{stratum}"
            left = by_key.get((checkpoint_id, lower))
            right = by_key.get((checkpoint_id, upper))
            if left is None or right is None:
                continue
            difference = int(right["strict_post_checkpoint_conversion"]) - int(
                left["strict_post_checkpoint_conversion"]
            )
            differences.append(difference)
            observed.append(
                {
                    "checkpoint_id": checkpoint_id,
                    "difference": difference,
                }
            )
        if len(differences) == 2:
            project_scores.append(sum(differences) / 2)
        else:
            complete_projects = False
    missing = 12 - len(observed)
    observed_sum = sum(item["difference"] for item in observed)
    result = {
        "comparison": f"{lower}_vs_{upper}",
        "complete_checkpoint_count": len(observed),
        "missing_checkpoint_count": missing,
        "observed_complete_estimate": (
            observed_sum / len(observed) if observed else None
        ),
        "identification_interval": [
            (observed_sum - missing) / 12,
            (observed_sum + missing) / 12,
        ],
        "project_scores": project_scores if complete_projects else None,
        "exact_test": (
            _exact_sign_flip(project_scores)
            if confirmatory and complete_projects and len(project_scores) == 6
            else None
        ),
    }
    return result


def build_report(
    manifest: dict[str, Any], results: list[dict[str, Any]]
) -> dict[str, Any]:
    primary = _comparison_analysis(
        manifest, results, lower="c0", upper="t1", confirmatory=True
    )
    primary_test = primary["exact_test"]
    primary_gate = bool(
        primary_test
        and primary_test["p_value"] <= manifest["analysis"]["primary"]["alpha"]
        and primary_test["observed_mean"] >= 1 / 3
    )
    secondary = _comparison_analysis(
        manifest,
        results,
        lower="t1",
        upper="t2",
        confirmatory=primary_gate,
    )
    supportive = _comparison_analysis(
        manifest, results, lower="c0", upper="t2", confirmatory=False
    )
    censored = [item for item in results if item.get("status") == "endpoint_censored"]
    request_attempts = sum(
        int(item.get("provider_request_attempts", 0)) for item in results
    )
    tokens = {
        field: sum(int(item.get(field, 0)) for item in results)
        for field in (
            "recorded_input_tokens",
            "recorded_output_tokens",
            "recorded_total_tokens",
        )
    }
    return {
        "schema_version": FORMAL_REPORT_SCHEMA_VERSION,
        "document_type": "forge_contract_repair_formal_report",
        "manifest_sha256": _manifest_sha256(manifest),
        "status": (
            "stopped_after_second_endpoint_censor"
            if len(censored) >= 2
            else "complete"
            if len(results) == 36
            else "incomplete"
        ),
        "observed_arm_count": len(results),
        "complete_arm_count": sum(item.get("status") == "complete" for item in results),
        "endpoint_censored_arm_count": len(censored),
        "endpoint_censored_sequences": [item["sequence"] for item in censored],
        "provider_request_attempts": request_attempts,
        **tokens,
        "primary": primary,
        "primary_fixed_sequence_gate_passed": primary_gate,
        "secondary": secondary,
        "supportive": supportive,
        "interpretation_boundary": manifest["interpretation_boundary"],
        "generated_at": _utc_now(),
    }


def _node_input(
    manifest: dict[str, Any],
    task: dict[str, Any],
    session: CompileSession,
    checkpoint_id: str,
    opaque_clone_id: str,
) -> AgentBuildNodeInput:
    budget = manifest["budget_candidate"]["per_arm"]
    target = task["target_contract"]
    compiled_types = tuple(
        item for item in target["artifact_types"] if item != "support_file"
    )
    build_systems = tuple(
        item
        for item in task["build_system_capabilities"]
        if item in {"cmake", "make", "autotools"}
    )
    if not compiled_types or task["selected_build_system"] not in build_systems:
        raise FormalRunnerError(f"{task['task_id']} target/build-system 合同无效")
    frozen = manifest["frozen_formal_execution_components"]
    return AgentBuildNodeInput(
        task_id=task["task_id"],
        attempt_id=opaque_clone_id,
        session_id=session.session_id,
        repository_url=task["repository_url"],
        commit_sha=task["commit_sha"],
        source_snapshot_sha256=task["source_snapshot_sha256"],
        build_system_candidates=build_systems,
        target_contract=AgentWorkflowTargetContract(
            target_id=target["target_id"],
            artifact_types=compiled_types,
            artifact_path_patterns=tuple(target["required_artifacts"]),
            functional_oracle_ref=f"stage-c-{task['task_id']}-oracle-v1",
        ),
        operation_policy_ref="contract-repair-formal-continuation-v1",
        environment=AgentWorkflowEnvironmentIdentity(
            image_id=session.image_id or manifest["environment_identity"]["image_id"],
            parallel_jobs=manifest["environment_identity"]["parallel_jobs"],
            network_policy="clone_then_network_none",
        ),
        budget=AgentWorkflowBudget(
            max_model_requests=budget["max_model_request_attempts"],
            max_recorded_tokens=None,
            max_agent_steps=budget["max_graph_steps"],
            max_tool_calls=budget["max_tool_calls"],
            max_commands=budget["max_commands"],
            node_timeout_seconds=budget["continuation_timeout_seconds"],
            command_timeout_seconds=budget["command_timeout_seconds"],
            evaluator_timeout_seconds=budget["evaluator_timeout_seconds"],
            replay_timeout_seconds=budget["clean_replay_timeout_seconds"],
            cleanup_timeout_seconds=budget["cleanup_reserve_seconds"],
        ),
        experiment_identity=AgentWorkflowExperimentIdentity(
            manifest_sha256=_manifest_sha256(manifest),
            protocol_sha256=frozen[protocol.PROTOCOL_PATH],
            runner_sha256=frozen[protocol.RUNNER_PATH],
        ),
        initial_observation={
            "required_candidate_artifacts": tuple(target["required_artifacts"]),
            "build_system_capabilities": tuple(task["build_system_capabilities"]),
            "selected_build_system": task["selected_build_system"],
            "checkpoint_id": checkpoint_id,
            "network_after_clone": "none",
        },
    )


def _validate_all_node_inputs(manifest: dict[str, Any]) -> None:
    opaque_ids: set[str] = set()
    evaluation_ids: set[str] = set()
    for checkpoint in manifest["schedule"]["checkpoints"]:
        task = _task(manifest, checkpoint["task_id"])
        for arm in checkpoint["arms"]:
            session = type(
                "FormalContractSession",
                (),
                {
                    "session_id": "formalcontract",
                    "image_id": manifest["environment_identity"]["image_id"],
                },
            )()
            _node_input(
                manifest,
                task,
                session,
                checkpoint["checkpoint_id"],
                arm["opaque_clone_id"],
            ).validate()
            if arm["opaque_clone_id"] in opaque_ids:
                raise FormalRunnerError("opaque clone identity 重复")
            if arm["opaque_evaluation_id"] in evaluation_ids:
                raise FormalRunnerError("opaque evaluation identity 重复")
            opaque_ids.add(arm["opaque_clone_id"])
            evaluation_ids.add(arm["opaque_evaluation_id"])


def evaluate_generalized_p2(
    session: CompileSession,
    request: SubmitCandidateRequest,
    *,
    selected_build_system: str,
) -> dict[str, Any]:
    commands = {item.command_id: item for item in session.commands}
    supporting = [
        commands.get(command_id) for command_id in request.supporting_command_ids
    ]
    direct: list[str] = []
    for command in supporting:
        if command is None or command.exit_code != 0 or command.timed_out:
            continue
        try:
            argv = shlex.split(command.command)
        except ValueError:
            continue
        while argv and "=" in argv[0] and not argv[0].startswith(("/", "./")):
            argv.pop(0)
        executable = Path(argv[0]).name if argv else ""
        if (
            selected_build_system == "cmake"
            and executable == "cmake"
            and "--build" in argv[1:]
        ):
            direct.append(command.command_id)
        elif selected_build_system in {"make", "autotools"} and executable in {
            "make",
            "gmake",
        }:
            if not any(
                value == "install" or value.endswith("-install") for value in argv[1:]
            ):
                direct.append(command.command_id)
    if direct:
        return {
            "status": "proven",
            "classification": "build_system_proven",
            "reason": "trusted_direct_compiler_tool_surface",
            "proof_mode": "trusted_direct_compiler_tool_surface",
            "supporting_command_ids": direct,
            "paths": sorted(request.artifact_paths),
            "expected": [selected_build_system],
            "actual": ["trusted_direct_compiler_tool_surface"],
        }
    return {
        "status": "unproven",
        "classification": "build_system_unproven",
        "reason": "opaque_wrapper",
        "proof_mode": None,
        "supporting_command_ids": [],
        "paths": sorted(request.artifact_paths),
        "expected": [selected_build_system],
        "actual": ["opaque_wrapper"],
    }


def _generalized_p2_evaluator(
    session: CompileSession, selected_build_system: str
) -> Callable[[SubmitCandidateRequest], dict[str, Any]]:
    def evaluate(request: SubmitCandidateRequest) -> dict[str, Any]:
        return evaluate_generalized_p2(
            session,
            request,
            selected_build_system=selected_build_system,
        )

    return evaluate


def _response_usage(response: ModelResponse) -> tuple[str | None, int, int, int, bool]:
    actual_models: set[str] = set()
    input_tokens = output_tokens = total_tokens = 0
    response_observed = False
    for message in response.result:
        if not isinstance(message, AIMessage):
            continue
        actual_model, usage = model_response_metadata(message)
        if actual_model:
            actual_models.add(actual_model)
        input_value = usage.get("prompt_tokens", usage.get("input_tokens", 0))
        output_value = usage.get("completion_tokens", usage.get("output_tokens", 0))
        total_value = usage.get("total_tokens", 0)
        if any(
            type(value) is not int or value < 0
            for value in (input_value, output_value, total_value)
        ):
            raise FormalFatalError("Provider token metadata 无效")
        input_tokens += input_value
        output_tokens += output_value
        total_tokens += total_value
        content = getattr(message, "content", None)
        response_observed = (
            response_observed
            or bool(content)
            or bool(getattr(message, "tool_calls", None))
        )
    if len(actual_models) > 1:
        raise ModelIdentityError(
            "单次 Provider response 包含多个 actual model identity"
        )
    actual_model = next(iter(actual_models), None)
    return actual_model, input_tokens, output_tokens, total_tokens, response_observed


class FormalExecutionMiddleware(runtime_v1.AgentWorkflowExecutionMiddleware):
    def _attempt_record(
        self,
        *,
        sequence: int,
        started: float,
        response_received: bool,
        actual_model: str | None,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        error_class: str | None,
        retry_eligible: bool,
    ) -> None:
        context = _active_continuation
        if context is None:
            raise FormalFatalError("formal continuation context 未绑定")
        context.request_attempts.append(
            {
                "request_sequence": sequence,
                "response_received": response_received,
                "actual_model": actual_model,
                "model_identity_match": actual_model == context.expected_model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "tool_side_effect_count": 0,
                "error_class": error_class,
                "retry_eligible": retry_eligible,
                "duration_ms": round((time.perf_counter() - started) * 1000),
            }
        )

    def _complete(self, response: ModelResponse, sequence: int, started: float) -> bool:
        context = _active_continuation
        if context is None:
            raise FormalFatalError("formal continuation context 未绑定")
        actual_model, input_tokens, output_tokens, total_tokens, observed = (
            _response_usage(response)
        )
        retry_eligible = not observed and total_tokens == 0
        self.ledger.append(
            "model.request_completed",
            request_sequence=sequence,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            recorded_tokens=total_tokens,
            actual_model=actual_model,
            response_received=observed,
            retry_eligible=retry_eligible,
        )
        self.tracker.consume(recorded_tokens=total_tokens)
        self._attempt_record(
            sequence=sequence,
            started=started,
            response_received=observed,
            actual_model=actual_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            error_class=None,
            retry_eligible=retry_eligible,
        )
        if actual_model != context.expected_model:
            context.fatal_error_class = ModelIdentityError.__name__
            raise ModelIdentityError("Provider actual model identity 发生漂移")
        return retry_eligible

    def _failed(self, sequence: int, started: float, exc: BaseException) -> None:
        self.ledger.append(
            "model.request_failed",
            request_sequence=sequence,
            error_class=type(exc).__name__,
            retry_eligible=True,
        )
        self._attempt_record(
            sequence=sequence,
            started=started,
            response_received=False,
            actual_model=None,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            error_class=type(exc).__name__,
            retry_eligible=True,
        )

    def _before_retry(self) -> int:
        context = _active_continuation
        if context is None:
            raise FormalFatalError("formal continuation context 未绑定")
        if (
            self.tracker.snapshot().model_requests
            >= self.tracker.limits.max_model_requests
        ):
            context.endpoint_censored = True
            raise EndpointCensoredError("transport retry 无剩余 request attempt budget")
        return self._before_request()

    def _sync_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        serial = request.override(
            model_settings={
                **(request.model_settings or {}),
                "parallel_tool_calls": False,
            }
        )
        for retry_index in range(2):
            sequence = (
                self._before_request() if retry_index == 0 else self._before_retry()
            )
            started = time.perf_counter()
            try:
                response = handler(serial)
            except Exception as exc:
                self._failed(sequence, started, exc)
                if retry_index == 0:
                    continue
                assert _active_continuation is not None
                _active_continuation.endpoint_censored = True
                raise EndpointCensoredError(
                    "Provider transport retry exhausted"
                ) from exc
            retry_eligible = self._complete(response, sequence, started)
            if not retry_eligible:
                return response
            if retry_index == 1:
                assert _active_continuation is not None
                _active_continuation.endpoint_censored = True
                raise EndpointCensoredError(
                    "Provider returned two empty unmetered responses"
                )
        raise AssertionError("unreachable")

    async def _async_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        serial = request.override(
            model_settings={
                **(request.model_settings or {}),
                "parallel_tool_calls": False,
            }
        )
        for retry_index in range(2):
            sequence = (
                self._before_request() if retry_index == 0 else self._before_retry()
            )
            started = time.perf_counter()
            try:
                response = await handler(serial)
            except Exception as exc:
                self._failed(sequence, started, exc)
                if retry_index == 0:
                    continue
                assert _active_continuation is not None
                _active_continuation.endpoint_censored = True
                raise EndpointCensoredError(
                    "Provider transport retry exhausted"
                ) from exc
            retry_eligible = self._complete(response, sequence, started)
            if not retry_eligible:
                return response
            if retry_index == 1:
                assert _active_continuation is not None
                _active_continuation.endpoint_censored = True
                raise EndpointCensoredError(
                    "Provider returned two empty unmetered responses"
                )
        raise AssertionError("unreachable")

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        return self._sync_call(request, handler)

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        return await self._async_call(request, handler)


class FormalCandidateService(qualification.RuntimeV3QualificationCandidateService):
    def __init__(self, **kwargs: Any) -> None:
        context = _active_continuation
        if context is None:
            raise FormalFatalError("formal continuation context 未绑定")
        super().__init__(
            provenance_evaluator=context.provenance_evaluator,
            **kwargs,
        )


class FormalNodeRunner(runtime_v3.AgentWorkflowNodeRunner):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        context = _active_continuation
        if context is None:
            raise FormalFatalError("formal continuation context 未绑定")
        snapshot = context.parent_budget
        self.tracker.consume(
            model_requests=snapshot.model_requests,
            recorded_tokens=snapshot.recorded_tokens,
            agent_steps=snapshot.agent_steps,
            tool_calls=snapshot.tool_calls,
            commands=snapshot.commands,
        )

    def _task_prompt(self) -> str:
        context = _active_continuation
        if context is None:
            raise FormalFatalError("formal continuation context 未绑定")
        continuation = {
            "checkpoint_id": context.checkpoint_id,
            "parent_candidate_request": context.parent_request,
            "parent_command_history": context.parent_history,
            "feedback_projection": context.feedback,
        }
        return (
            super()._task_prompt()
            + "冻结 parent candidate 已被拒绝；从完全相同的失败现场继续。"
            + "continuation_checkpoint="
            + json.dumps(
                continuation,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "。只能使用绑定工具修复并重新提交候选。"
        )


def _create_formal_agent(*args: Any, **kwargs: Any) -> Any:
    middleware = kwargs.get("middleware") or ()
    execution = next(
        (item for item in middleware if isinstance(item, FormalExecutionMiddleware)),
        None,
    )
    if execution is None:
        raise FormalFatalError("formal Runtime v3 缺少 transport-aware middleware")
    return runtime_v2._RecursionGuardAgent(
        runtime_v3._agent_factory(*args, **kwargs), execution
    )


async def run_formal_continuation(
    *,
    node_input: AgentBuildNodeInput,
    session: CompileSession,
    manager: CompileSessionManager,
    model: Any,
    oracle_spec: Any,
    context: ContinuationContext,
) -> AgentBuildNodeResult:
    global _active_continuation
    if not runtime_v3._RUNTIME_BINDING_LOCK.acquire(blocking=False):
        raise FormalFatalError("Runtime v3 只允许 formal 串行执行")
    originals = (
        runtime_v1.create_agent,
        runtime_v1.AgentWorkflowCandidateService,
        runtime_v1.AgentWorkflowNodeRunner,
        runtime_v1.AgentWorkflowExecutionMiddleware,
    )
    try:
        expected = (
            runtime_v3._ORIGINAL_CREATE_AGENT,
            runtime_v3._ORIGINAL_CANDIDATE_SERVICE,
            runtime_v3._ORIGINAL_NODE_RUNNER,
            runtime_v1.AgentWorkflowExecutionMiddleware,
        )
        if originals[:3] != expected[:3] or runtime_v3._active_verifier is not None:
            raise FormalFatalError("Runtime v1/v3 binding 已被其他执行修改")
        _active_continuation = context
        runtime_v3._active_verifier = CandidateVerifier(oracle_spec=oracle_spec)
        runtime_v1.create_agent = _create_formal_agent
        runtime_v1.AgentWorkflowCandidateService = FormalCandidateService
        runtime_v1.AgentWorkflowNodeRunner = FormalNodeRunner
        runtime_v1.AgentWorkflowExecutionMiddleware = FormalExecutionMiddleware
        try:
            return await runtime_v1.run_agent_workflow_node_v1(
                node_input=node_input,
                session=session,
                manager=manager,
                model=model,
            )
        finally:
            (
                runtime_v1.create_agent,
                runtime_v1.AgentWorkflowCandidateService,
                runtime_v1.AgentWorkflowNodeRunner,
                runtime_v1.AgentWorkflowExecutionMiddleware,
            ) = originals
            runtime_v3._active_verifier = None
            _active_continuation = None
    finally:
        runtime_v3._RUNTIME_BINDING_LOCK.release()


@contextmanager
def _runtime_identity(manifest: dict[str, Any], repo_root: Path):
    services = get_compile_services()
    manager = services.manager
    runtime = services.runtime
    environment = manifest["environment_identity"]
    budget = manifest["budget_candidate"]["per_arm"]
    original = (
        manager.paths,
        manager.default_image,
        manager.parallel_jobs,
        runtime.config.image,
        runtime.config.parallel_jobs,
        runtime.config.replay_timeout_seconds,
    )
    try:
        manager.paths = stage_c_v8._explicit_paths(repo_root)
        manager.default_image = environment["compile_image"]
        manager.parallel_jobs = environment["parallel_jobs"]
        runtime.config.image = environment["compile_image"]
        runtime.config.parallel_jobs = environment["parallel_jobs"]
        runtime.config.replay_timeout_seconds = budget["clean_replay_timeout_seconds"]
        yield services
    finally:
        (
            manager.paths,
            manager.default_image,
            manager.parallel_jobs,
            runtime.config.image,
            runtime.config.parallel_jobs,
            runtime.config.replay_timeout_seconds,
        ) = original


def _tree_manifest(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(
        root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
    ):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        entry: dict[str, Any] = {
            "path": relative,
            "mode": metadata.st_mode & 0o7777,
        }
        if path.is_symlink():
            entry.update(type="symlink", target=os.readlink(path))
        elif path.is_dir():
            entry["type"] = "directory"
        elif path.is_file():
            entry.update(
                type="file",
                size=metadata.st_size,
                sha256=protocol.parent.parent.parent.candidate.file_sha256(path),
            )
        else:
            entry["type"] = "other"
        entries.append(entry)
    return entries


def _copy_tree(source: Path, target: Path) -> None:
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(source, target, symlinks=True)


def _capture_environment(
    parent: CompileSession,
    *,
    checkpoint_id: str,
    snapshot_root: Path,
) -> dict[str, Any]:
    if not parent.container_id:
        raise FormalFatalError("parent checkpoint 缺少活动容器")
    snapshot_root.mkdir(parents=True, exist_ok=False)
    _run_checked(["docker", "pause", parent.container_id], timeout=30)
    image_id: str | None = None
    try:
        image_id = _run_checked(
            [
                "docker",
                "commit",
                "--no-pause",
                "--change",
                f"LABEL {CAPTURE_LABEL}={checkpoint_id}",
                parent.container_id,
            ],
            timeout=300,
        )
        if not image_id.startswith("sha256:"):
            raise FormalFatalError("checkpoint capture image identity 无效")
        _copy_tree(Path(parent.leadagent_repo_dir).parent, snapshot_root / "workspace")
        _copy_tree(Path(parent.leadagent_artifacts_dir), snapshot_root / "artifacts")
        _copy_tree(Path(parent.leadagent_repro_dir), snapshot_root / "repro")
    finally:
        _run_checked(["docker", "unpause", parent.container_id], timeout=30)
    return {
        "continuation_image_id": image_id,
        "workspace": str(snapshot_root / "workspace"),
        "artifacts": str(snapshot_root / "artifacts"),
        "repro": str(snapshot_root / "repro"),
        "identity": {
            "image_id": image_id,
            "workspace_sha256": qualification.canonical_sha256(
                _tree_manifest(snapshot_root / "workspace")
            ),
            "artifacts_sha256": qualification.canonical_sha256(
                _tree_manifest(snapshot_root / "artifacts")
            ),
            "repro_sha256": qualification.canonical_sha256(
                _tree_manifest(snapshot_root / "repro")
            ),
        },
    }


def _environment_identity(session: CompileSession) -> dict[str, Any]:
    return {
        "image_id": session.image_id,
        "workspace_sha256": qualification.canonical_sha256(
            _tree_manifest(Path(session.leadagent_repo_dir).parent)
        ),
        "artifacts_sha256": qualification.canonical_sha256(
            _tree_manifest(Path(session.leadagent_artifacts_dir))
        ),
        "repro_sha256": qualification.canonical_sha256(
            _tree_manifest(Path(session.leadagent_repro_dir))
        ),
    }


def _copy_parent_state(parent: CompileSession, arm: CompileSession) -> None:
    for field_name in (
        "commit_sha",
        "build_system",
        "build_system_capabilities",
        "selected_build_system",
        "executed_build_system",
        "post_build_supporting_command_id",
        "post_build_started_at",
        "post_build_commands_remaining",
        "commands",
        "artifacts",
        "verification",
        "summary",
        "error",
        "replay_source_archive_sha256",
    ):
        setattr(arm, field_name, copy.deepcopy(getattr(parent, field_name)))
    arm.status = parent.status
    arm.replay_attempts = []


def _provision_arm(
    *,
    manager: CompileSessionManager,
    runtime: Any,
    parent: CompileSession,
    captured: dict[str, Any],
    opaque_clone_id: str,
) -> CompileSession:
    arm = manager.create_session(
        thread_id=opaque_clone_id,
        repo_url=parent.repo_url,
        branch=parent.branch,
        image=captured["continuation_image_id"],
        run_id=f"formal-{opaque_clone_id}",
    )
    _copy_parent_state(parent, arm)
    _copy_tree(Path(captured["workspace"]), Path(arm.leadagent_repo_dir).parent)
    _copy_tree(Path(captured["artifacts"]), Path(arm.leadagent_artifacts_dir))
    _copy_tree(Path(captured["repro"]), Path(arm.leadagent_repro_dir))
    manager.save_session(arm)
    runtime.create_container(arm)
    manager.save_session(arm)
    if _environment_identity(arm) != captured["identity"]:
        raise FormalFatalError("provisioned arm 与 parent checkpoint 环境不一致")
    return arm


def _remove_capture_image(image_id: str | None) -> None:
    if not image_id:
        return
    result = subprocess.run(
        ["docker", "image", "rm", "-f", image_id],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise FormalFatalError("formal checkpoint capture image cleanup 失败")


def _reference_command_role(command: str) -> str:
    stripped = command.lstrip()
    if stripped.startswith(("cmake --install", "make install", "make PREFIX=")):
        return "artifact_stage"
    if (
        "mkdir -p /artifacts" in stripped
        or " /artifacts/" in stripped
        and "cp " in stripped
    ):
        return "artifact_stage"
    if stripped.startswith(("cmake -S", "./configure", "./autogen.sh", "autoreconf ")):
        return "configure"
    return "build"


def _run_tool(
    session: CompileSession,
    command: str,
    role: str,
    *,
    timeout_seconds: int,
) -> Any:
    result, _message, record = _run_container_bash_impl(
        session=session,
        command=command,
        command_role=role,
        timeout_seconds=timeout_seconds,
        workdir="/workspace/repo",
    )
    if result.exit_code != 0:
        raise FormalFatalError(f"parent reference recipe 失败: {type(result).__name__}")
    return record


def _delivery_normalization_command(
    task: dict[str, Any], session: CompileSession
) -> str | None:
    required = set(task["target_contract"]["required_artifacts"])
    delivery = scan_delivery(Path(session.leadagent_artifacts_dir))
    removable = set(delivery.invalid_paths)
    removable.update(
        entry.relative_path
        for entry in delivery.entries
        if entry.relative_path not in required
        and (
            entry.size_bytes == 0
            or entry.artifact_type
            in {"executable", "shared_library", "static_library", "object"}
        )
    )
    if not removable:
        return None
    if any(
        path in {"", "."} or Path(path).is_absolute() or ".." in Path(path).parts
        for path in removable
    ):
        raise FormalFatalError("delivery normalization path 越界")
    paths = " ".join(
        shlex.quote(f"/artifacts/{relative_path}")
        for relative_path in sorted(removable)
    )
    return f"rm -f -- {paths}"


def _run_delivery_normalization(
    task: dict[str, Any],
    session: CompileSession,
    *,
    timeout_seconds: int,
) -> Any | None:
    command = _delivery_normalization_command(task, session)
    if command is None:
        return None
    return _run_tool(
        session,
        command,
        "artifact_stage",
        timeout_seconds=timeout_seconds,
    )


def _run_direct_reference_recipe(
    task: dict[str, Any], session: CompileSession, *, timeout_seconds: int
) -> list[Any]:
    records: list[Any] = []
    for command in task["reference_recipe"]:
        role = _reference_command_role(command)
        executable_command = command
        if role == "artifact_stage" and "/artifacts" not in command:
            executable_command = f"test -d /artifacts && {command}"
        records.append(
            _run_tool(
                session,
                executable_command,
                role,
                timeout_seconds=timeout_seconds,
            )
        )
    normalization = _run_delivery_normalization(
        task,
        session,
        timeout_seconds=timeout_seconds,
    )
    if normalization is not None:
        records.append(normalization)
    return records


def _run_opaque_reference_recipe(
    task: dict[str, Any],
    session: CompileSession,
    *,
    runtime: Any,
    timeout_seconds: int,
) -> Any:
    script_path = f"/tmp/forge-formal-opaque-{uuid.uuid4().hex}.sh"
    body = "#!/bin/bash\nset -euo pipefail\ncd /workspace/repo\n" + "\n".join(
        task["reference_recipe"]
    )
    encoded = base64.b64encode(body.encode("utf-8")).decode("ascii")
    injection = runtime.exec(
        session,
        f"printf %s {shlex.quote(encoded)} | base64 -d > {shlex.quote(script_path)} && chmod 700 {shlex.quote(script_path)}",
        workdir="/workspace/repo",
        timeout_seconds=30,
        strict_shell=True,
    )
    if injection.exit_code != 0:
        raise FormalFatalError("无法注入 system-owned opaque parent recipe")
    try:
        return _run_tool(
            session,
            script_path,
            "build",
            timeout_seconds=timeout_seconds,
        )
    finally:
        removal = runtime.exec(
            session,
            f"rm -f {shlex.quote(script_path)}",
            workdir="/workspace/repo",
            timeout_seconds=30,
            strict_shell=True,
        )
        if removal.exit_code != 0:
            raise FormalFatalError("无法删除 system-owned opaque parent recipe")


def _artifact_stage_fence_command(task: dict[str, Any]) -> str:
    required = task["target_contract"]["required_artifacts"]
    if not required:
        raise FormalFatalError("artifact-stage fence 缺少冻结 required artifacts")
    return " && ".join(
        f"test -s {shlex.quote('/artifacts/' + relative_path)}"
        for relative_path in required
    )


def _compiled_target_path(task: dict[str, Any], session: CompileSession) -> str:
    delivery = scan_delivery(Path(session.leadagent_artifacts_dir))
    required = set(task["target_contract"]["required_artifacts"])
    compiled = [
        entry.relative_path
        for entry in delivery.entries
        if entry.relative_path in required
        and entry.artifact_type
        in {"executable", "shared_library", "static_library", "object"}
    ]
    if len(compiled) != 1:
        raise FormalFatalError(
            f"{task['task_id']} 必须恰有一个 target-mapped compiled artifact"
        )
    return compiled[0]


def _candidate_request(
    task: dict[str, Any],
    *,
    supporting_command_ids: tuple[str, ...],
    recipe_command_ids: tuple[str, ...],
    target_path: str,
    correct_mapping: bool,
) -> SubmitCandidateRequest:
    target_id = task["target_contract"]["target_id"]
    mapping_id = target_id if correct_mapping else f"invalid-{target_id}"
    return SubmitCandidateRequest(
        candidate_id=f"formal-parent-{task['task_id']}",
        build_system=task["selected_build_system"],
        supporting_command_ids=supporting_command_ids,
        artifact_paths=tuple(task["target_contract"]["required_artifacts"]),
        target_mapping={mapping_id: target_path},
        recipe_command_ids=recipe_command_ids,
        agent_summary="Frozen formal parent candidate.",
    )


def _parent_message_prefix(
    checkpoint: dict[str, Any],
    request: SubmitCandidateRequest,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "checkpoint_id": checkpoint["checkpoint_id"],
        "instruction": "continue after authoritative candidate rejection",
        "parent_candidate_request": json.loads(request.canonical_json()),
        "parent_command_history": history,
        "feedback_slot": "projection_only",
    }


def _capture_checkpoint(
    manifest: dict[str, Any],
    checkpoint: dict[str, Any],
    *,
    output_dir: Path,
    services: Any,
) -> dict[str, Any]:
    task = _task(manifest, checkpoint["task_id"])
    checkpoint_path, ledger_path = _checkpoint_paths(manifest, output_dir, checkpoint)
    parent = prepare_compile_session_impl(
        thread_id=f"formal-parent-{checkpoint['checkpoint_sequence']:02d}-{uuid.uuid4().hex[:12]}",
        repo_url=task["repository_url"],
        run_id=f"formal-parent-{uuid.uuid4().hex}",
        task_description=f"Formal checkpoint {checkpoint['checkpoint_id']}",
    )
    captured: dict[str, Any] | None = None
    try:
        clone, _message = clone_repository_impl(
            session=parent,
            repo_url=task["repository_url"],
            commit_sha=task["commit_sha"],
            depth=1,
            max_retries=1,
        )
        if clone.exit_code != 0 or parent.commit_sha != task["commit_sha"]:
            raise FormalFatalError("parent checkpoint 无法检出冻结 commit")
        stage_c_v8._bind_replay_source_archive(task, parent, services.manager)
        primary, _detected, _suggested = inspect_build_system_impl(session=parent)
        if (
            primary not in task["build_system_capabilities"]
            or task["selected_build_system"] not in parent.build_system_capabilities
        ):
            raise FormalFatalError("parent checkpoint build-system identity 漂移")
        parent.selected_build_system = task["selected_build_system"]
        services.manager.save_session(parent)
        with stage_c._offline_runtime(parent):
            command_timeout = manifest["budget_candidate"]["per_arm"][
                "command_timeout_seconds"
            ]
            if checkpoint["stratum"] == "delivery_target":
                records = _run_direct_reference_recipe(
                    task, parent, timeout_seconds=command_timeout
                )
                supporting = tuple(
                    record.command_id for record in records if record.role == "build"
                )[-1:]
                recipe_ids = tuple(record.command_id for record in records)
            else:
                wrapper = _run_opaque_reference_recipe(
                    task,
                    parent,
                    runtime=services.runtime,
                    timeout_seconds=command_timeout,
                )
                normalization = _run_delivery_normalization(
                    task,
                    parent,
                    timeout_seconds=command_timeout,
                )
                artifact_stage_fence = _run_tool(
                    parent,
                    _artifact_stage_fence_command(task),
                    "artifact_stage",
                    timeout_seconds=command_timeout,
                )
                records = [wrapper]
                if normalization is not None:
                    records.append(normalization)
                records.append(artifact_stage_fence)
                supporting = (wrapper.command_id,)
                recipe_ids = tuple(record.command_id for record in records)
            target_path = _compiled_target_path(task, parent)
            request = _candidate_request(
                task,
                supporting_command_ids=supporting,
                recipe_command_ids=recipe_ids,
                target_path=target_path,
                correct_mapping=checkpoint["stratum"] == "provenance",
            )
            oracle_spec = stage_c._oracle_spec(task)
            functional_precheck = None
            if checkpoint["stratum"] == "delivery_target":
                functional_precheck = SystemOwnedFunctionalCheckRunner().run(
                    spec=oracle_spec,
                    session=parent,
                    manager=services.manager,
                )
                if not functional_precheck.passed:
                    raise FormalFatalError("delivery parent functional oracle 未通过")
            parent_input = _node_input(
                manifest,
                task,
                parent,
                checkpoint["checkpoint_id"],
                f"parent-{checkpoint['checkpoint_sequence']:02d}",
            )
            _state, tracker, store = qualification.create_store(parent_input.budget)
            tracker.consume(tool_calls=1)
            parent_ledger = runtime_v1.AgentWorkflowEvidenceLedger(
                ledger_path,
                node_input=parent_input,
                run_id=parent.run_id or "",
            )
            provenance_evaluator = (
                _generalized_p2_evaluator(parent, task["selected_build_system"])
                if checkpoint["stratum"] == "provenance"
                else None
            )
            service = qualification.create_candidate_service(
                verifier=CandidateVerifier(oracle_spec=oracle_spec),
                provenance_evaluator=provenance_evaluator,
                node_input=parent_input,
                session=parent,
                manager=services.manager,
                store=store,
                candidate_path=Path(parent.metadata_path).parent
                / "formal-parent-candidate.json",
                ledger=parent_ledger,
            )
            rejection = service.submit(request)
            expected_code = (
                "target_mapping_invalid"
                if checkpoint["stratum"] == "delivery_target"
                else "build_system_unproven"
            )
            if rejection.accepted or rejection.rejection_codes != (expected_code,):
                raise FormalFatalError("parent checkpoint 未形成唯一冻结 rejection")
            finding = (
                rejection.rejection_details[0].as_payload()
                if checkpoint["stratum"] == "delivery_target"
                else service.last_provenance_finding
            )
            if finding is None:
                raise FormalFatalError("parent checkpoint 缺少 authoritative finding")
            history = [asdict(command) for command in parent.commands]
            budget_snapshot = tracker.snapshot()
            snapshot_root = (
                Path(parent.metadata_path).parent / "formal-checkpoint-snapshot"
            )
            captured = _capture_environment(
                parent,
                checkpoint_id=checkpoint["checkpoint_id"],
                snapshot_root=snapshot_root,
            )
            rejection_event = {
                "response": json.loads(rejection.canonical_json()),
                "finding": qualification.normalize_finding(finding),
            }
            prefix = _parent_message_prefix(checkpoint, request, history)
            common_state = {
                "source": {
                    "repository_url": task["repository_url"],
                    "commit_sha": task["commit_sha"],
                    "source_snapshot_sha256": task["source_snapshot_sha256"],
                },
                "parent_history_sha256": qualification.canonical_sha256(history),
                "candidate_request_sha256": request.canonical_sha256(),
                "rejection_event_sha256": qualification.canonical_sha256(
                    rejection_event
                ),
                "message_prefix_sha256": qualification.canonical_sha256(prefix),
                "environment": captured["identity"],
                "budget": asdict(budget_snapshot),
                "tool_policy": qualification.TOOL_POLICY,
                "authorities": manifest["frozen_formal_execution_components"],
            }
            pair_id = checkpoint["checkpoint_id"]
            projections = qualification.build_projection_set(
                pair_id=pair_id,
                stratum=checkpoint["stratum"],
                finding=finding,
            )
            states = qualification.build_arm_states(
                common_state=common_state, projections=projections
            )
            qualification.validate_state_matched(
                states, pair_id=pair_id, stratum=checkpoint["stratum"]
            )
            checkpoint_marker = qualification.persist_checkpoint(
                checkpoint_path,
                {
                    "schema_version": FORMAL_MARKER_SCHEMA_VERSION,
                    "document_type": "forge_contract_repair_formal_checkpoint",
                    "formal_manifest_sha256": _manifest_sha256(manifest),
                    "checkpoint_id": checkpoint["checkpoint_id"],
                    "checkpoint_sequence": checkpoint["checkpoint_sequence"],
                    "task_id": checkpoint["task_id"],
                    "stratum": checkpoint["stratum"],
                    "capture": captured,
                    "common_state": common_state,
                    "parent_candidate_request": json.loads(request.canonical_json()),
                    "parent_command_history": history,
                    "authoritative_rejection": rejection_event,
                    "functional_precheck": (
                        asdict(functional_precheck)
                        if functional_precheck is not None
                        else rejection_event["response"]["rejection_details"] == []
                    ),
                    "feedback_projections": {
                        name: envelope.payload for name, envelope in projections.items()
                    },
                    "provider_calls": 0,
                    "formal_attempts": 0,
                    "status": "captured",
                    "captured_at": _utc_now(),
                },
            )
            return {
                "parent": parent,
                "task": task,
                "captured": captured,
                "checkpoint_marker": checkpoint_marker,
                "parent_request": json.loads(request.canonical_json()),
                "parent_history": history,
                "parent_budget": budget_snapshot,
                "projections": projections,
                "oracle_spec": oracle_spec,
            }
    except BaseException:
        if captured is not None:
            _remove_capture_image(captured.get("continuation_image_id"))
        cleanup_and_finalize_compile_session_impl(
            session=parent,
            interrupted_status="failed",
            error="Formal checkpoint capture failed.",
        )
        raise


def _experiment_policy(
    manifest: dict[str, Any],
    task: dict[str, Any],
    arm: dict[str, Any],
    *,
    image_id: str,
) -> ExperimentPolicy:
    provider = manifest["provider_candidate"]
    budget = manifest["budget_candidate"]["per_arm"]
    return ExperimentPolicy(
        benchmark_id="forge-contract-driven-repair-mechanism-v1",
        manifest_sha256=_manifest_sha256(manifest),
        case_id=arm["opaque_clone_id"],
        condition="runtime-v3-formal-continuation",
        repetition=1,
        expected_repo_url=task["repository_url"],
        expected_commit_sha=task["commit_sha"],
        expected_build_system=task["selected_build_system"],
        compile_image=manifest["environment_identity"]["compile_image"],
        image_id=image_id,
        model_name=provider["profile"],
        endpoint=provider["endpoint"],
        credential_env=provider["credential_env_name"],
        request_timeout_seconds=provider["request_timeout_seconds"],
        model_max_retries=0,
        compiler_max_turns=budget["max_turns"],
        subagent_timeout_seconds=budget["continuation_timeout_seconds"],
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=(),
        cmake_arguments=(),
        configure_arguments=(),
        environment=(),
        minimum_replay_delay_seconds=0,
        compiler_model_turn_limit=budget["max_model_request_attempts"],
        compiler_graph_recursion_limit=budget["max_graph_steps"],
        compiler_wall_clock_seconds=budget["continuation_timeout_seconds"],
        compiler_post_build_reserve_seconds=budget["cleanup_reserve_seconds"],
    )


def _create_provider_model(manifest: dict[str, Any], thread_id: str) -> Any:
    from deerflow.models.factory import create_chat_model

    provider = manifest["provider_candidate"]
    model = create_chat_model(
        name=provider["profile"],
        thinking_enabled=False,
        experiment_thread_id=thread_id,
        experiment_role="compiler",
    )
    if bool(getattr(model, "streaming", False)):
        raise FormalFatalError("formal Provider 必须关闭 streaming")
    return model


def _claim_arm_marker(
    path: Path,
    manifest: dict[str, Any],
    checkpoint: dict[str, Any],
    arm: dict[str, Any],
    *,
    release_revision: str,
) -> None:
    _write_once(
        path,
        {
            "schema_version": FORMAL_MARKER_SCHEMA_VERSION,
            "document_type": "forge_contract_repair_formal_arm_marker",
            "manifest_sha256": _manifest_sha256(manifest),
            "release_revision": release_revision,
            "checkpoint_id": checkpoint["checkpoint_id"],
            "sequence": arm["sequence"],
            "opaque_clone_id": arm["opaque_clone_id"],
            "status": "started",
            "error_class": None,
            "started_at": _utc_now(),
            "updated_at": _utc_now(),
        },
    )


def _layer_passed(evaluation: Any, layer_name: str) -> bool:
    return bool(
        evaluation
        and next(
            (layer.status for layer in evaluation.layers if layer.layer == layer_name),
            None,
        )
        == "passed"
    )


async def execute_arm(
    manifest: dict[str, Any],
    checkpoint: dict[str, Any],
    arm: dict[str, Any],
    captured_checkpoint: dict[str, Any],
    *,
    output_dir: Path,
    release_revision: str,
    services: Any,
    model_factory: Callable[[dict[str, Any], str], Any] = _create_provider_model,
) -> dict[str, Any]:
    paths = _arm_paths(manifest, output_dir, arm)
    _claim_arm_marker(
        paths["marker"],
        manifest,
        checkpoint,
        arm,
        release_revision=release_revision,
    )
    task = captured_checkpoint["task"]
    ledger = ExperimentLedger.create(
        paths["ledger"],
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={
            "manifest_sha256": _manifest_sha256(manifest),
            "release_revision": release_revision,
            "checkpoint_id": checkpoint["checkpoint_id"],
            "opaque_clone_id": arm["opaque_clone_id"],
        },
    )
    arm_session: CompileSession | None = None
    node_result = evaluation = finalized = cleanup = None
    runtime_events_source: Path | None = None
    candidate_source: Path | None = None
    active = False
    error_class: str | None = None
    fatal_error: BaseException | None = None
    started = time.perf_counter()
    request_attempts: list[dict[str, Any]] = []
    context: ContinuationContext | None = None
    try:
        arm_session = _provision_arm(
            manager=services.manager,
            runtime=services.runtime,
            parent=captured_checkpoint["parent"],
            captured=captured_checkpoint["captured"],
            opaque_clone_id=arm["opaque_clone_id"],
        )
        thread_id = arm["opaque_clone_id"]
        activate_experiment(
            thread_id=thread_id,
            experiment_id=ledger.experiment_id,
            physical_attempt_id=ledger.physical_attempt_id,
            ledger=ledger,
            policy=_experiment_policy(
                manifest,
                task,
                arm,
                image_id=arm_session.image_id or "",
            ),
        )
        active = True
        provenance_evaluator = (
            _generalized_p2_evaluator(arm_session, task["selected_build_system"])
            if checkpoint["stratum"] == "provenance"
            else None
        )
        context = ContinuationContext(
            checkpoint_id=checkpoint["checkpoint_id"],
            parent_request=copy.deepcopy(captured_checkpoint["parent_request"]),
            parent_history=copy.deepcopy(captured_checkpoint["parent_history"]),
            feedback=copy.deepcopy(
                captured_checkpoint["projections"][arm["condition"]].payload
            ),
            parent_budget=captured_checkpoint["parent_budget"],
            expected_model=manifest["provider_candidate"]["actual_model"],
            provenance_evaluator=provenance_evaluator,
            request_attempts=request_attempts,
        )
        arm_state = {
            "common_state": {
                **copy.deepcopy(
                    captured_checkpoint["checkpoint_marker"]["common_state"]
                ),
                "environment": _environment_identity(arm_session),
                "budget": asdict(context.parent_budget),
            },
            "feedback": context.feedback,
        }
        all_states = {
            name: {
                "common_state": copy.deepcopy(arm_state["common_state"]),
                "feedback": copy.deepcopy(envelope.payload),
            }
            for name, envelope in captured_checkpoint["projections"].items()
        }
        qualification.validate_state_matched(
            all_states,
            pair_id=checkpoint["checkpoint_id"],
            stratum=checkpoint["stratum"],
        )
        node_input = _node_input(
            manifest,
            task,
            arm_session,
            checkpoint["checkpoint_id"],
            arm["opaque_clone_id"],
        )
        with stage_c._offline_runtime(arm_session):
            node_result = await run_formal_continuation(
                node_input=node_input,
                session=arm_session,
                manager=services.manager,
                model=model_factory(manifest, thread_id),
                oracle_spec=captured_checkpoint["oracle_spec"],
                context=context,
            )
            workflow_dir = (
                Path(arm_session.metadata_path).parent
                / "agent-workflow"
                / arm["opaque_clone_id"]
            )
            runtime_events_source = workflow_dir / "events.jsonl"
            candidate_source = workflow_dir / "candidate.json"
            if context.fatal_error_class:
                raise ModelIdentityError("formal model identity gate failed")
            if not context.endpoint_censored and node_result.candidate_submitted:
                evaluation = run_external_evaluator_v3(
                    node_input=node_input,
                    node_result=node_result,
                    session=arm_session,
                    manager=services.manager,
                    candidate_path=candidate_source,
                    evaluation_id=arm["opaque_evaluation_id"],
                    backend=ForgeCompileEvaluationBackend(
                        oracle_registry={
                            captured_checkpoint[
                                "oracle_spec"
                            ].oracle_ref: captured_checkpoint["oracle_spec"]
                        }
                    ),
                )
                if any(layer.status == "invalid" for layer in evaluation.layers):
                    raise FormalFatalError(
                        "external evaluator 出现 internal invalid layer"
                    )
    except ModelIdentityError as exc:
        error_class = type(exc).__name__
        fatal_error = exc
    except FormalFatalError as exc:
        error_class = type(exc).__name__
        fatal_error = exc
    except BaseException as exc:
        if context is not None and context.endpoint_censored:
            error_class = EndpointCensoredError.__name__
        else:
            error_class = type(exc).__name__
            fatal_error = FormalFatalError(
                f"formal arm 未分类运行异常: {type(exc).__name__}"
            )
    finally:
        if active:
            deactivate_experiment(arm["opaque_clone_id"])
        if arm_session is not None:
            try:
                finalized, cleanup = cleanup_and_finalize_compile_session_impl(
                    session=arm_session,
                    interrupted_status=(
                        "cancelled"
                        if context is not None and context.endpoint_censored
                        else "failed"
                    ),
                    error=(
                        "Formal endpoint censored."
                        if context is not None and context.endpoint_censored
                        else None
                    ),
                )
            except BaseException as exc:
                fatal_error = FormalFatalError(
                    f"arm cleanup exception: {type(exc).__name__}"
                )
                error_class = type(fatal_error).__name__
    cleanup_succeeded = bool(
        cleanup
        and cleanup.succeeded
        and finalized
        and finalized.finalized_at is not None
    )
    if arm_session is not None and arm_session.container_id:
        inspected = subprocess.run(
            ["docker", "container", "inspect", arm_session.container_id],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if inspected.returncode == 0:
            cleanup_succeeded = False
    if not cleanup_succeeded:
        fatal_error = FormalFatalError("formal arm cleanup 未闭合")
        error_class = type(fatal_error).__name__
    if runtime_events_source is not None and runtime_events_source.is_file():
        _write_bytes_once(paths["runtime_events"], runtime_events_source.read_bytes())
    else:
        _write_bytes_once(paths["runtime_events"], b"")
    if candidate_source is not None and candidate_source.is_file():
        _write_bytes_once(paths["candidate"], candidate_source.read_bytes())
    else:
        _write_once(paths["candidate"], {"candidate_present": False})
    usage = node_result.usage if node_result is not None else None
    totals = {
        "recorded_input_tokens": sum(item["input_tokens"] for item in request_attempts),
        "recorded_output_tokens": sum(
            item["output_tokens"] for item in request_attempts
        ),
        "recorded_total_tokens": sum(item["total_tokens"] for item in request_attempts),
    }
    if usage is not None and (
        usage.model_requests != len(request_attempts)
        or usage.recorded_tokens != totals["recorded_total_tokens"]
    ):
        fatal_error = FormalFatalError("Runtime usage 与逐请求 token ledger 不闭合")
        error_class = type(fatal_error).__name__
    censored = bool(context and context.endpoint_censored)
    status = (
        "failed" if fatal_error else "endpoint_censored" if censored else "complete"
    )
    candidate_accepted = bool(node_result and node_result.candidate_submitted)
    functional_passed = _layer_passed(evaluation, "S3")
    provenance_passed = _layer_passed(evaluation, "S2")
    evaluator_passed = bool(evaluation and evaluation.strict_reproducible_build_success)
    clean_replay_passed = _layer_passed(evaluation, "S4")
    strict = bool(
        status == "complete"
        and candidate_accepted
        and functional_passed
        and provenance_passed
        and evaluator_passed
        and clean_replay_passed
        and cleanup_succeeded
    )
    result = {
        "schema_version": FORMAL_RESULT_SCHEMA_VERSION,
        "document_type": "forge_contract_repair_formal_arm_result",
        "manifest_sha256": _manifest_sha256(manifest),
        "release_revision": release_revision,
        "checkpoint_id": checkpoint["checkpoint_id"],
        "task_id": checkpoint["task_id"],
        "stratum": checkpoint["stratum"],
        "sequence": arm["sequence"],
        "opaque_clone_id": arm["opaque_clone_id"],
        "opaque_evaluation_id": arm["opaque_evaluation_id"],
        "condition": arm["condition"],
        "status": status,
        "candidate_accepted": candidate_accepted,
        "functional_oracle_passed": functional_passed,
        "provenance_passed": provenance_passed,
        "external_evaluator_v3_passed": evaluator_passed,
        "clean_replay_passed": clean_replay_passed,
        "cleanup_closed": cleanup_succeeded,
        "zero_managed_orphans": cleanup_succeeded,
        "strict_post_checkpoint_conversion": strict,
        "provider_request_attempts": len(request_attempts),
        "request_token_ledger": request_attempts,
        **totals,
        "model_behavior_terminal": (
            None
            if censored or fatal_error is not None
            else node_result.primary_failure
            if node_result is not None
            else "node_not_started"
        ),
        "error_class": error_class,
        "s0_s5": (
            [asdict(layer) for layer in evaluation.layers]
            if evaluation is not None
            else []
        ),
        "evaluation_sha256": (
            evaluation.canonical_sha256() if evaluation is not None else None
        ),
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "completed_at": _utc_now(),
    }
    _write_once(paths["result"], result)
    ledger.append(
        "experiment.completed",
        {
            "status": status,
            "result_sha256": protocol.parent.parent.parent.candidate.file_sha256(
                paths["result"]
            ),
        },
    )
    _update_claimed_marker(
        paths["marker"], status=status, error_class=error_class, completed_at=_utc_now()
    )
    if fatal_error is not None:
        raise fatal_error
    return result


def _claim_batch_marker(
    manifest: dict[str, Any], path: Path, *, release_revision: str
) -> None:
    _write_once(
        path,
        {
            "schema_version": FORMAL_MARKER_SCHEMA_VERSION,
            "document_type": "forge_contract_repair_formal_batch_marker",
            "manifest_sha256": _manifest_sha256(manifest),
            "release_revision": release_revision,
            "status": "running",
            "completed_checkpoint_count": 0,
            "completed_arm_count": 0,
            "endpoint_censored_arm_count": 0,
            "provider_request_attempt_count": 0,
            "started_at": _utc_now(),
            "updated_at": _utc_now(),
        },
    )


def _checkpoint_cleanup(captured: dict[str, Any], services: Any) -> None:
    parent = captured["parent"]
    cleanup_error: BaseException | None = None
    try:
        finalized, cleanup = cleanup_and_finalize_compile_session_impl(
            session=parent,
            interrupted_status="cancelled",
            error="Formal parent checkpoint completed.",
        )
        if not cleanup.succeeded or finalized.finalized_at is None:
            cleanup_error = FormalFatalError("formal parent checkpoint cleanup 未闭合")
    except BaseException as exc:
        cleanup_error = FormalFatalError(
            f"formal parent cleanup exception: {type(exc).__name__}"
        )
    try:
        _remove_capture_image(captured["captured"]["continuation_image_id"])
    except BaseException as exc:
        cleanup_error = FormalFatalError(
            f"formal capture image cleanup exception: {type(exc).__name__}"
        )
    if cleanup_error is not None:
        raise cleanup_error
    _require_zero_managed_resources()


async def execute_batch(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    model_factory: Callable[[dict[str, Any], str], Any] = _create_provider_model,
) -> dict[str, Any]:
    output_dir = _output_dir(manifest, output_dir, repo_root)
    batch_marker = output_dir / manifest["formal_execution"]["batch_marker"]
    report_path = output_dir / manifest["formal_execution"]["batch_report"]
    if not batch_marker.exists():
        preflight = collect_preflight(
            manifest,
            output_dir=output_dir,
            repo_root=repo_root,
            require_formal_absent=True,
        )
        _claim_batch_marker(
            manifest,
            batch_marker,
            release_revision=preflight["release_revision"],
        )
        results: list[dict[str, Any]] = []
    else:
        preflight = collect_preflight(
            manifest,
            output_dir=output_dir,
            repo_root=repo_root,
            require_formal_absent=False,
        )
        marker = _load_json(batch_marker)
        if marker.get("status") != "running" or report_path.exists():
            raise FormalRunnerError("formal batch 已终结，禁止重跑")
        results = completed_prefix(
            manifest, output_dir, require_checkpoint_boundary=True
        )
    release_revision = preflight["release_revision"]
    completed_sequences = {item["sequence"] for item in results}
    censored_count = sum(item["status"] == "endpoint_censored" for item in results)
    try:
        with _runtime_identity(manifest, repo_root) as services:
            for checkpoint in manifest["schedule"]["checkpoints"]:
                if all(
                    arm["sequence"] in completed_sequences for arm in checkpoint["arms"]
                ):
                    continue
                captured: dict[str, Any] | None = None
                stop_after_checkpoint = False
                try:
                    captured = _capture_checkpoint(
                        manifest,
                        checkpoint,
                        output_dir=output_dir,
                        services=services,
                    )
                    for arm in checkpoint["arms"]:
                        result = await execute_arm(
                            manifest,
                            checkpoint,
                            arm,
                            captured,
                            output_dir=output_dir,
                            release_revision=release_revision,
                            services=services,
                            model_factory=model_factory,
                        )
                        results.append(result)
                        completed_sequences.add(arm["sequence"])
                        censored_count += result["status"] == "endpoint_censored"
                        _update_claimed_marker(
                            batch_marker,
                            completed_arm_count=len(results),
                            endpoint_censored_arm_count=censored_count,
                            provider_request_attempt_count=sum(
                                item["provider_request_attempts"] for item in results
                            ),
                            last_completed_sequence=arm["sequence"],
                        )
                        if (
                            censored_count
                            >= manifest["formal_execution"][
                                "endpoint_censored_arm_stop_count"
                            ]
                        ):
                            stop_after_checkpoint = True
                            break
                finally:
                    if captured is not None:
                        _checkpoint_cleanup(captured, services)
                completed_checkpoint_count = sum(
                    all(arm["sequence"] in completed_sequences for arm in item["arms"])
                    for item in manifest["schedule"]["checkpoints"]
                )
                _update_claimed_marker(
                    batch_marker,
                    completed_checkpoint_count=completed_checkpoint_count,
                )
                if stop_after_checkpoint:
                    break
        report = build_report(manifest, results)
        _write_once(report_path, report)
        terminal_status = report["status"]
        _update_claimed_marker(
            batch_marker,
            status=terminal_status,
            completed_arm_count=len(results),
            endpoint_censored_arm_count=censored_count,
            provider_request_attempt_count=sum(
                item["provider_request_attempts"] for item in results
            ),
            report_sha256=protocol.parent.parent.parent.candidate.file_sha256(
                report_path
            ),
            completed_at=_utc_now(),
        )
        return report
    except BaseException as exc:
        _update_claimed_marker(
            batch_marker,
            status="failed",
            error_class=type(exc).__name__,
            completed_arm_count=len(results),
            endpoint_censored_arm_count=censored_count,
            provider_request_attempt_count=sum(
                item.get("provider_request_attempts", 0) for item in results
            ),
            stopped_at=_utc_now(),
        )
        raise


def audit_batch(
    manifest: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR
) -> dict[str, Any]:
    output_dir = _output_dir(manifest, output_dir, REPO_ROOT)
    marker_path = output_dir / manifest["formal_execution"]["batch_marker"]
    report_path = output_dir / manifest["formal_execution"]["batch_report"]
    marker = _load_json(marker_path)
    report = _load_json(report_path)
    results = completed_prefix(manifest, output_dir)
    expected = build_report(manifest, results)
    for volatile in ("generated_at",):
        expected[volatile] = report.get(volatile)
    if report != expected:
        raise FormalRunnerError("formal report 与 create-once arm evidence 不一致")
    if (
        marker.get("manifest_sha256") != _manifest_sha256(manifest)
        or marker.get("status") != report["status"]
        or marker.get("completed_arm_count") != len(results)
        or marker.get("report_sha256")
        != protocol.parent.parent.parent.candidate.file_sha256(report_path)
    ):
        raise FormalRunnerError("formal batch marker 与 report 不一致")
    if (
        report["provider_request_attempts"]
        > manifest["formal_execution"]["formal_provider_request_attempt_limit"]
    ):
        raise FormalRunnerError("formal request attempt 总量超过冻结上限")
    return {
        "status": "passed",
        "batch_status": report["status"],
        "manifest_sha256": _manifest_sha256(manifest),
        "report_sha256": protocol.parent.parent.parent.candidate.file_sha256(
            report_path
        ),
        "observed_arm_count": len(results),
        "endpoint_censored_arm_count": report["endpoint_censored_arm_count"],
        "provider_request_attempts": report["provider_request_attempts"],
        "recorded_total_tokens": report["recorded_total_tokens"],
    }


def show_plan(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        **protocol.plan_summary(manifest),
        "checkpoint_order": [
            item["checkpoint_id"] for item in manifest["schedule"]["checkpoints"]
        ],
        "arm_sequence": [
            {
                "sequence": arm["sequence"],
                "checkpoint_id": checkpoint["checkpoint_id"],
                "condition": arm["condition"],
                "opaque_clone_id": arm["opaque_clone_id"],
            }
            for checkpoint in manifest["schedule"]["checkpoints"]
            for arm in checkpoint["arms"]
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("validate", "plan", "preflight", "batch", "report", "audit")
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest(args.manifest)
    if args.command == "validate":
        result: Mapping[str, Any] = validate_runtime(manifest)
    elif args.command == "plan":
        result = show_plan(manifest)
    elif args.command == "preflight":
        result = collect_preflight(
            manifest, output_dir=args.output_dir, require_formal_absent=True
        )
    elif args.command == "batch":
        result = asyncio.run(execute_batch(manifest, output_dir=args.output_dir))
    elif args.command == "report":
        results = completed_prefix(manifest, args.output_dir)
        result = build_report(manifest, results)
    else:
        result = audit_batch(manifest, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
