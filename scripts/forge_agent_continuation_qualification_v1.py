#!/usr/bin/env python3
"""Issue #429：固定 Agent continuation 资格实验。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_PATH.parent)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_agent_workflow_stage_b_calibration_authorized_runner as model_runner  # noqa: E402
import forge_checkpoint_archive as checkpoint_archive  # noqa: E402

from deerflow.compile import agent_workflow_runtime_v3 as runtime_v3  # noqa: E402
from deerflow.compile.agent_workflow_runtime import (  # noqa: E402
    AgentWorkflowBudgetTracker,
    AgentWorkflowCandidateStore,
    AgentWorkflowEvidenceLedger,
)
from deerflow.compile.agent_workflow_schemas import (  # noqa: E402
    AgentBuildNodeInput,
    AgentBuildNodeResult,
    AgentWorkflowBudget,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowTargetContract,
    AgentWorkflowUsage,
    SubmitCandidateRequest,
)
from deerflow.compile.agent_workflow_node import (  # noqa: E402
    AgentWorkflowNodeStatus,
    AgentWorkflowStateMachine,
)
from deerflow.compile.candidate_verifier import CandidateVerifier  # noqa: E402
from deerflow.compile.evidence import (  # noqa: E402
    ExperimentLedger,
    ExperimentPolicy,
    activate_experiment,
    deactivate_experiment,
    new_evidence_id,
)
from deerflow.compile.external_evaluator import FunctionalOracleSpec  # noqa: E402
from deerflow.compile.external_evaluator_v4 import (  # noqa: E402
    ForgeCompileEvaluationBackend,
    run_external_evaluator_v4,
)
from deerflow.compile.operations import (  # noqa: E402
    cleanup_and_finalize_compile_session_impl,
    get_compile_services,
    inspect_build_system_impl,
    prepare_compile_session_impl,
)
from deerflow.tools.bound_compile_tools import _run_container_bash_impl  # noqa: E402

IDENTITY = "cpp-agent-continuation-qualification-v1"
TRACKING_ISSUE = 429
BRANCH = "yiwei/429-agent-continuation-qualification-v1"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests" / f"{IDENTITY}.json"
SCHEMA_PATH = (
    REPO_ROOT
    / "benchmarks/schemas/forge-agent-continuation-qualification-v1.schema.json"
)
PREREGISTRATION_PATH = REPO_ROOT / "benchmarks/preregistrations" / f"{IDENTITY}.md"
SPEC_PATH = (
    REPO_ROOT
    / "docs/superpowers/specs/2026-10-12-agent-continuation-qualification-v1-design.md"
)
PLAN_PATH = (
    REPO_ROOT
    / "docs/superpowers/plans/2026-10-12-agent-continuation-qualification-v1.md"
)
REPORT_JSON_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.json"
REPORT_MD_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.md"
PARENT_STATE_ROOT = (
    REPO_ROOT
    / ".compile-sessions/benchmark-evidence-dynamic-budget-trajectory-qualification-v5/states"
)
MANAGED_PREFIXES = ("deerflow-compile-", "deerflow-replay-")
COMPONENT_PATHS = (
    "scripts/forge_agent_continuation_qualification_v1.py",
    "backend/tests/test_forge_agent_continuation_qualification_v1.py",
    "benchmarks/schemas/forge-agent-continuation-qualification-v1.schema.json",
    "benchmarks/preregistrations/cpp-agent-continuation-qualification-v1.md",
    "docs/superpowers/specs/2026-10-12-agent-continuation-qualification-v1-design.md",
    "docs/superpowers/plans/2026-10-12-agent-continuation-qualification-v1.md",
)
REPLAY_ROLES = frozenset(
    {"dependency", "dependency_setup", "configure", "build", "artifact_stage"}
)


class QualificationError(RuntimeError):
    """实验身份、运行或证据不满足冻结合同。"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QualificationError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise QualificationError(f"JSON 根节点必须是对象: {path}")
    return value


def _write_once_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise QualificationError(f"create-once evidence 已存在: {path}") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp-{uuid.uuid4().hex}")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _git(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={REPO_ROOT}", *arguments],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise QualificationError("Git identity 核验失败")
    return completed.stdout.strip()


def _docker(*arguments: str) -> str:
    completed = subprocess.run(
        ["docker", *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise QualificationError("Docker identity 核验失败")
    return completed.stdout.strip()


def _manifest() -> dict[str, Any]:
    return _load_json(MANIFEST_PATH)


def _task(manifest: dict[str, Any], task_id: str) -> dict[str, Any]:
    matches = [task for task in manifest["tasks"] if task["task_id"] == task_id]
    if len(matches) != 1:
        raise QualificationError(f"未知或重复 task: {task_id}")
    return matches[0]


def _checkpoint_dir(state_id: str) -> Path:
    return PARENT_STATE_ROOT / state_id / "checkpoint"


def _checkpoint_payload(
    state_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    directory = _checkpoint_dir(state_id)
    checkpoint = _load_json(directory / "checkpoint.json")
    message = _load_json(directory / "message.json")
    budget = _load_json(directory / "budget.json")
    payload = {
        key: value for key, value in checkpoint.items() if key != "checkpoint_sha256"
    }
    if checkpoint.get("checkpoint_sha256") != _canonical_sha256(payload):
        raise QualificationError(f"parent checkpoint hash 漂移: {state_id}")
    if checkpoint.get("workspace_snapshot_sha256") != _file_sha256(
        directory / "workspace.tar.gz"
    ):
        raise QualificationError(f"parent workspace snapshot 漂移: {state_id}")
    if checkpoint.get("artifacts_snapshot_sha256") != _file_sha256(
        directory / "artifacts.tar.gz"
    ):
        raise QualificationError(f"parent artifacts snapshot 漂移: {state_id}")
    if checkpoint.get("message_sha256") != _canonical_sha256(message):
        raise QualificationError(f"parent message hash 漂移: {state_id}")
    if checkpoint.get("budget_sha256") != _canonical_sha256(budget):
        raise QualificationError(f"parent budget hash 漂移: {state_id}")
    return checkpoint, message, budget


def _validate_parent_inventory(manifest: dict[str, Any]) -> None:
    root = REPO_ROOT / manifest["parent"]["evidence_root"]
    inventory = _load_json(root / "inventory.json")
    if (
        inventory.get("canonical_sha256")
        != manifest["parent"]["inventory_canonical_sha256"]
    ):
        raise QualificationError("parent inventory canonical SHA-256 漂移")
    files = inventory.get("files")
    if (
        not isinstance(files, list)
        or _canonical_sha256(files) != inventory["canonical_sha256"]
    ):
        raise QualificationError("parent inventory 内容无效")
    for item in files:
        path = root / item["path"]
        if (
            not path.is_file()
            or path.stat().st_size != item["size"]
            or _file_sha256(path) != item["sha256"]
        ):
            raise QualificationError(f"parent evidence 文件漂移: {item['path']}")


def validate_manifest(
    manifest: dict[str, Any], *, require_components: bool = True
) -> dict[str, Any]:
    if (
        manifest.get("identity") != IDENTITY
        or manifest.get("issue") != TRACKING_ISSUE
        or manifest.get("branch") != BRANCH
    ):
        raise QualificationError("manifest identity 漂移")
    expected_authorization = {
        "zero_provider_q0": True,
        "credential_read_after_q0": True,
        "provider_q1_q2": True,
        "formal_evidence_write": True,
        "historical_evidence_write": False,
        "replacement": False,
        "backfill": False,
        "controller_implementation": False,
        "jev_calls": False,
    }
    if manifest.get("authorization") != expected_authorization:
        raise QualificationError("授权边界漂移")
    tasks = manifest.get("tasks", [])
    if len(tasks) != 9 or Counter(
        task.get("build_system") for task in tasks
    ) != Counter({"cmake": 3, "make": 3, "autotools": 3}):
        raise QualificationError("正式 task 分层无效")
    if len({task.get("task_id") for task in tasks}) != 9:
        raise QualificationError("task identity 不唯一")
    depths = Counter(
        int(task["checkpoint_state_id"].rsplit("-", 1)[-1]) for task in tasks
    )
    if depths != Counter({1: 3, 2: 3, 3: 3}):
        raise QualificationError("checkpoint depth 覆盖无效")
    for task in tasks:
        checkpoint, _message, _budget = _checkpoint_payload(task["checkpoint_state_id"])
        source = checkpoint.get("source", {})
        if (
            source.get("repository_url") != task["repository_url"]
            or source.get("commit_sha") != task["commit_sha"]
        ):
            raise QualificationError(
                f"checkpoint source identity 漂移: {task['task_id']}"
            )
        if checkpoint.get("image_id") != manifest["environment"]["image_id"]:
            raise QualificationError(
                f"checkpoint image identity 漂移: {task['task_id']}"
            )
        if (
            not task.get("reference_commands")
            or task["reference_commands"][-1].get("role") != "artifact_stage"
        ):
            raise QualificationError(f"reference recipe 不闭合: {task['task_id']}")
        if not task.get("oracle", {}).get("command"):
            raise QualificationError(f"functional oracle 缺失: {task['task_id']}")
    canaries = manifest.get("canary_checkpoints", [])
    if len(canaries) != 3 or {
        item["task_id"].split("-", 1)[0] for item in canaries
    } != {"cmake", "make", "autotools"}:
        raise QualificationError("canary 构建系统覆盖无效")
    for item in canaries:
        task = _task(manifest, item["task_id"])
        checkpoint, _message, _budget = _checkpoint_payload(item["checkpoint_state_id"])
        if checkpoint["source"]["commit_sha"] != task["commit_sha"]:
            raise QualificationError("canary checkpoint source 漂移")
    schedule = manifest.get("formal_schedule", [])
    if [item.get("sequence") for item in schedule] != list(range(1, 28)):
        raise QualificationError("formal schedule sequence 无效")
    counts = Counter((item.get("task_id"), item.get("repetition")) for item in schedule)
    expected = Counter(
        (task["task_id"], repetition) for task in tasks for repetition in (1, 2, 3)
    )
    if counts != expected:
        raise QualificationError("formal schedule 不满足 9 x 3")
    provider = manifest.get("provider", {})
    if (
        provider.get("profile") != "deepseek-flash"
        or provider.get("model_max_retries") != 0
        or provider.get("streaming") is not False
    ):
        raise QualificationError("Provider 合同漂移")
    budget = manifest.get("budget", {})
    if (
        budget.get("provider_arms") != 30
        or budget.get("total_provider_requests") != 720
        or budget.get("total_recorded_tokens") != 9_000_000
    ):
        raise QualificationError("总体 Provider 预算漂移")
    components = manifest.get("components", {})
    if require_components:
        if set(components) != set(COMPONENT_PATHS):
            raise QualificationError("冻结组件集合无效")
        for relative, expected_sha256 in components.items():
            if _file_sha256(REPO_ROOT / relative) != expected_sha256:
                raise QualificationError(f"冻结组件漂移: {relative}")
    _validate_parent_inventory(manifest)
    return manifest


def _require_zero_managed_resources() -> None:
    names = _docker("ps", "-a", "--format", "{{.Names}}")
    managed = sorted(
        name for name in names.splitlines() if name.startswith(MANAGED_PREFIXES)
    )
    paused = _docker(
        "ps",
        "-q",
        "--filter",
        "status=paused",
        "--filter",
        "label=deerflow.compile.managed=true",
    )
    images = _docker("images", "-q", "--filter", "label=deerflow.compile.managed=true")
    if managed or paused or images:
        raise QualificationError("存在 Compile Session/replay/paused/image 受管资源")


def preflight(manifest: dict[str, Any], *, phase: str) -> dict[str, Any]:
    validate_manifest(manifest)
    if _git("branch", "--show-current") != BRANCH:
        raise QualificationError("当前分支与 identity 不一致")
    if _git("status", "--porcelain", "--untracked-files=normal"):
        raise QualificationError("实验执行要求干净工作树")
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
    _require_zero_managed_resources()
    root = REPO_ROOT / manifest["evidence_root"]
    if phase == "q0" and root.exists():
        raise QualificationError("Q0 create-once evidence root 已存在")
    if phase != "q0" and not root.is_dir():
        raise QualificationError("前置 evidence root 不存在")
    os.environ["DEER_FLOW_WORKSPACE_ROOT"] = str(REPO_ROOT)
    os.environ["DEER_FLOW_HOST_WORKSPACE_ROOT"] = str(REPO_ROOT)
    return {
        "release_revision": head,
        "manifest_sha256": _canonical_sha256(manifest),
        "image_id": image_id,
    }


def _phase_marker(root: Path, phase: str) -> Path:
    return root / phase / "attempt.json"


def _start_marker(path: Path, manifest_sha256: str, release_revision: str) -> None:
    _write_once_json(
        path,
        {
            "identity": IDENTITY,
            "phase": path.parent.name,
            "manifest_sha256": manifest_sha256,
            "release_revision": release_revision,
            "status": "started",
            "error_class": None,
            "started_at": _now(),
            "completed_at": None,
        },
    )


def _finish_marker(path: Path, status: str, error_class: str | None = None) -> None:
    marker = _load_json(path)
    if marker.get("status") != "started":
        raise QualificationError("phase marker 不是 started")
    marker.update(status=status, error_class=error_class, completed_at=_now())
    _atomic_json(path, marker)


def _require_phase_passed(
    root: Path, phase: str, manifest_sha256: str, release_revision: str
) -> dict[str, Any]:
    marker = _load_json(_phase_marker(root, phase))
    result = _load_json(root / phase / "result.json")
    if (
        marker.get("status") != "passed"
        or marker.get("manifest_sha256") != manifest_sha256
        or marker.get("release_revision") != release_revision
        or result.get("passed") is not True
        or result.get("manifest_sha256") != manifest_sha256
        or result.get("release_revision") != release_revision
    ):
        raise QualificationError(f"前置阶段未通过: {phase}")
    return result


def _copy_restored_archive(source: Path, destination: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="forge-agent-continuation-") as temporary:
        restored = Path(temporary) / "restored"
        checkpoint_archive.restore_checkpoint_archive(source, restored)
        for child in restored.iterdir():
            target = destination / child.name
            if child.is_dir() and not child.is_symlink():
                shutil.copytree(child, target, symlinks=True, dirs_exist_ok=True)
            elif child.is_symlink():
                target.symlink_to(os.readlink(child))
            else:
                shutil.copy2(child, target, follow_symlinks=False)


def _disconnect_container_networks(container_id: str) -> None:
    networks = _docker(
        "inspect",
        container_id,
        "--format",
        "{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}",
    )
    for network in networks.split():
        completed = subprocess.run(
            ["docker", "network", "disconnect", network, container_id],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if completed.returncode != 0:
            raise QualificationError("无法断开 checkpoint continuation 网络")


def _prepare_restored_session(
    manifest: dict[str, Any],
    task: dict[str, Any],
    state_id: str,
    *,
    thread_id: str,
    run_id: str,
) -> tuple[Any, dict[str, Any], dict[str, Any], dict[str, Any]]:
    checkpoint, message, parent_budget = _checkpoint_payload(state_id)
    services = get_compile_services()
    session = prepare_compile_session_impl(
        thread_id=thread_id,
        repo_url=task["repository_url"],
        run_id=run_id,
        task_description=f"Issue #429 checkpoint continuation: {state_id}",
    )
    if session.image_id != manifest["environment"]["image_id"]:
        raise QualificationError("Compile Session image identity 漂移")
    _disconnect_container_networks(session.container_id)
    repo_dir = Path(session.leadagent_repo_dir)
    if repo_dir.exists():
        if any(repo_dir.iterdir()):
            raise QualificationError("恢复前 repo 目录非空")
        repo_dir.rmdir()
    checkpoint_archive.restore_checkpoint_archive(
        _checkpoint_dir(state_id) / "workspace.tar.gz", repo_dir
    )
    artifacts_dir = Path(session.leadagent_artifacts_dir)
    if any(artifacts_dir.iterdir()):
        raise QualificationError("恢复前 artifacts 目录非空")
    _copy_restored_archive(
        _checkpoint_dir(state_id) / "artifacts.tar.gz", artifacts_dir
    )
    session.commit_sha = task["commit_sha"]
    services.manager.save_session(session)
    services.manager.mark_session_status(session, "source_ready")
    primary, detected, _suggested = inspect_build_system_impl(session=session)
    detected_systems = [system for system, _marker in detected]
    if task["build_system"] not in detected_systems:
        raise QualificationError(
            f"恢复 checkpoint 缺少 build-system marker: {state_id}"
        )
    session.selected_build_system = task["build_system"]
    services.manager.save_session(session)
    return session, checkpoint, message, parent_budget


def _budget(manifest: dict[str, Any]) -> AgentWorkflowBudget:
    return AgentWorkflowBudget(**manifest["budget"]["per_arm"])


def _oracle(task: dict[str, Any]) -> FunctionalOracleSpec:
    oracle = task["oracle"]
    return FunctionalOracleSpec(
        oracle_ref=f"issue-429-{task['task_id']}-oracle-v1",
        argv=("bash", "-lc", oracle["command"]),
        workdir=oracle["workdir"],
        timeout_seconds=oracle["timeout_seconds"],
    )


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
    target = task["target"]
    return AgentBuildNodeInput(
        task_id=task["task_id"],
        attempt_id=attempt_id,
        session_id=session.session_id,
        repository_url=task["repository_url"],
        commit_sha=task["commit_sha"],
        build_system_candidates=(task["build_system"],),
        target_contract=AgentWorkflowTargetContract(
            target_id=target["target_id"],
            artifact_types=(target["artifact_type"],),
            artifact_path_patterns=(target["artifact_path"],),
            functional_oracle_ref=_oracle(task).oracle_ref,
        ),
        operation_policy_ref="issue-429-fixed-agent-continuation-v1",
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
            "continuation_mode": "restored_checkpoint",
            "checkpoint_state_id": state_id,
            "checkpoint_sha256": checkpoint["checkpoint_sha256"],
            "checkpoint_message": message,
            "parent_budget": parent_budget,
            "required_candidate_artifacts": (target["artifact_path"],),
            "selected_build_system": task["build_system"],
            "instruction": "Continue from the restored repository state. Re-run every command needed for a complete clean-replay recipe because prior checkpoint commands have no command IDs in this Session. Submit only after the required artifact is staged.",
        },
        source_snapshot_sha256=checkpoint["workspace_snapshot_sha256"],
    )


def _candidate_path(session: Any, attempt_id: str) -> Path:
    return (
        Path(session.metadata_path).parent
        / "agent-workflow"
        / attempt_id
        / "candidate.json"
    )


def _direct_candidate(
    *,
    node_input: AgentBuildNodeInput,
    session: Any,
    records: list[Any],
) -> tuple[AgentBuildNodeResult, Path]:
    services = get_compile_services()
    workflow_dir = (
        Path(session.metadata_path).parent / "agent-workflow" / node_input.attempt_id
    )
    workflow_dir.mkdir(parents=True, exist_ok=False)
    (workflow_dir / "input.json").write_text(
        node_input.canonical_json() + "\n", encoding="utf-8"
    )
    ledger = AgentWorkflowEvidenceLedger(
        workflow_dir / "events.jsonl", node_input=node_input, run_id=session.run_id
    )
    ledger.append("attempt.registered", input_sha256=node_input.canonical_sha256())
    ledger.append("node.ready")
    ledger.append("node.started", controller="q0_reference_recipe")
    state = AgentWorkflowStateMachine()
    state.transition(AgentWorkflowNodeStatus.READY)
    state.transition(AgentWorkflowNodeStatus.RUNNING)
    tracker = AgentWorkflowBudgetTracker(node_input.budget)
    store = AgentWorkflowCandidateStore(state, tracker)
    candidate_path = workflow_dir / "candidate.json"
    verifier = CandidateVerifier(
        oracle_spec=_oracle(_task(_manifest(), node_input.task_id))
    )
    if not runtime_v3._RUNTIME_BINDING_LOCK.acquire(blocking=False):
        raise QualificationError("Runtime v3 binding 已被占用")
    try:
        if runtime_v3._active_verifier is not None:
            raise QualificationError("Runtime v3 verifier 已被占用")
        runtime_v3._active_verifier = verifier
        service = runtime_v3.AgentWorkflowCandidateService(
            node_input=node_input,
            session=session,
            manager=services.manager,
            store=store,
            candidate_path=candidate_path,
            ledger=ledger,
        )
    finally:
        runtime_v3._active_verifier = None
        runtime_v3._RUNTIME_BINDING_LOCK.release()
    successful = [
        record for record in records if record.exit_code == 0 and not record.timed_out
    ]
    build_records = [record for record in successful if record.role == "build"]
    if not build_records:
        raise QualificationError("reference recipe 缺少 supporting build")
    target = _task(_manifest(), node_input.task_id)["target"]
    response = service.submit(
        SubmitCandidateRequest(
            candidate_id=f"q0-{node_input.task_id}-reference",
            build_system=_task(_manifest(), node_input.task_id)["build_system"],
            supporting_command_ids=(build_records[-1].command_id,),
            artifact_paths=(target["artifact_path"],),
            target_mapping={target["target_id"]: target["artifact_path"]},
            recipe_command_ids=tuple(
                record.command_id
                for record in successful
                if record.role in REPLAY_ROLES
            ),
            agent_summary="Issue #429 Q0 frozen reference recipe.",
        )
    )
    if not response.accepted:
        raise QualificationError(
            f"Q0 candidate 被拒绝: {','.join(response.rejection_codes)}"
        )
    current = services.manager.load_session(session.session_id, session.thread_id)
    session.__dict__.update(current.__dict__)
    ledger.append("node.terminal", node_status="submitted", primary_failure=None)
    result = AgentBuildNodeResult(
        node_status="submitted",
        candidate_generated_observed=True,
        candidate_submitted=True,
        submission_id=response.submission_id,
        candidate_record_sha256=response.candidate_record_sha256,
        usage=AgentWorkflowUsage(0, 0, 0, 0, len(records)),
        wall_clock_ms=0,
        evidence_head_sha256=ledger.head_sha256,
        session_terminal_status=session.status,
    )
    result.validate()
    return result, candidate_path


def _evaluate(
    task: dict[str, Any],
    node_input: AgentBuildNodeInput,
    node_result: AgentBuildNodeResult,
    session: Any,
    candidate_path: Path,
    evaluation_id: str,
) -> Any:
    services = get_compile_services()
    return run_external_evaluator_v4(
        node_input=node_input,
        node_result=node_result,
        session=session,
        manager=services.manager,
        candidate_path=candidate_path,
        evaluation_id=evaluation_id,
        backend=ForgeCompileEvaluationBackend(
            oracle_registry={_oracle(task).oracle_ref: _oracle(task)}
        ),
    )


def _safe_cleanup(
    session: Any, *, interrupted_status: str | None = None, error: str | None = None
) -> tuple[Any, Any]:
    finalized, cleanup = cleanup_and_finalize_compile_session_impl(
        session=session, interrupted_status=interrupted_status, error=error
    )
    _require_zero_managed_resources()
    if not cleanup.succeeded or finalized.finalized_at is None:
        raise QualificationError("Compile Session cleanup 或 terminalization 未闭合")
    return finalized, cleanup


def _snapshot_session(session: Any, destination: Path) -> str:
    source = Path(session.metadata_path).parent
    shutil.copytree(source, destination, symlinks=True)
    entries = []
    for path in sorted(destination.rglob("*")):
        if path.is_file() and not path.is_symlink():
            entries.append(
                {
                    "path": path.relative_to(destination).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": _file_sha256(path),
                }
            )
        elif path.is_symlink():
            entries.append(
                {
                    "path": path.relative_to(destination).as_posix(),
                    "target": os.readlink(path),
                    "kind": "symlink",
                }
            )
    return _canonical_sha256(entries)


def _run_reference_case(
    manifest: dict[str, Any],
    task: dict[str, Any],
    case_dir: Path,
    release_revision: str,
) -> dict[str, Any]:
    thread_id = f"issue-429-q0-{task['task_id']}-{uuid.uuid4().hex[:12]}"
    session = None
    cleanup_succeeded = False
    started = time.monotonic()
    try:
        session, checkpoint, message, parent_budget = _prepare_restored_session(
            manifest,
            task,
            task["checkpoint_state_id"],
            thread_id=thread_id,
            run_id=f"issue-429-q0-{uuid.uuid4().hex}",
        )
        attempt_id = f"q0-{task['task_id']}-reference"
        node_input = _node_input(
            manifest,
            task,
            session,
            attempt_id=attempt_id,
            state_id=task["checkpoint_state_id"],
            checkpoint=checkpoint,
            message=message,
            parent_budget=parent_budget,
        )
        records = []
        for item in task["reference_commands"]:
            result, _message, record = _run_container_bash_impl(
                session=get_compile_services().manager.load_session(
                    session.session_id, session.thread_id
                ),
                command=item["command"],
                command_role=item["role"],
                timeout_seconds=manifest["budget"]["per_arm"][
                    "command_timeout_seconds"
                ],
                workdir="/workspace/repo",
            )
            records.append(record)
            if result.exit_code != 0 or record.timed_out:
                raise QualificationError(
                    f"Q0 reference command 失败: {task['task_id']}:{item['role']}"
                )
        node_result, candidate_path = _direct_candidate(
            node_input=node_input, session=session, records=records
        )
        evaluation = _evaluate(
            task,
            node_input,
            node_result,
            session,
            candidate_path,
            f"q0-{task['task_id']}-evaluation-v1",
        )
        finalized, cleanup = _safe_cleanup(session)
        cleanup_succeeded = True
        session_tree_sha256 = _snapshot_session(
            finalized, case_dir / "session-evidence"
        )
        return {
            "task_id": task["task_id"],
            "checkpoint_state_id": task["checkpoint_state_id"],
            "checkpoint_sha256": checkpoint["checkpoint_sha256"],
            "release_revision": release_revision,
            "strict_success": evaluation.strict_reproducible_build_success,
            "layers": [asdict(layer) for layer in evaluation.layers],
            "bitwise_reproducible": evaluation.bitwise_reproducible,
            "session_status": finalized.status,
            "cleanup_succeeded": cleanup.succeeded,
            "session_tree_sha256": session_tree_sha256,
            "duration_milliseconds": round((time.monotonic() - started) * 1000),
        }
    finally:
        if session is not None and not cleanup_succeeded:
            try:
                _safe_cleanup(
                    session,
                    interrupted_status="failed",
                    error="Q0 reference case interrupted",
                )
            except Exception:
                pass


def execute_q0(manifest: dict[str, Any]) -> dict[str, Any]:
    preflight_result = preflight(manifest, phase="q0")
    root = REPO_ROOT / manifest["evidence_root"]
    root.mkdir(parents=True, exist_ok=False)
    _write_once_json(
        root / "identity.json",
        {
            "identity": IDENTITY,
            "manifest_sha256": preflight_result["manifest_sha256"],
            "release_revision": preflight_result["release_revision"],
            "parent_inventory_canonical_sha256": manifest["parent"][
                "inventory_canonical_sha256"
            ],
            "created_at": _now(),
        },
    )
    marker_path = _phase_marker(root, "q0")
    _start_marker(
        marker_path,
        preflight_result["manifest_sha256"],
        preflight_result["release_revision"],
    )
    outcomes = []
    try:
        for sequence, task in enumerate(manifest["tasks"], 1):
            case_dir = root / "q0/cases" / f"{sequence:02d}-{task['task_id']}"
            outcome = _run_reference_case(
                manifest, task, case_dir, preflight_result["release_revision"]
            )
            _write_once_json(case_dir / "result.json", outcome)
            outcomes.append(outcome)
            if outcome["strict_success"] is not True:
                raise QualificationError(f"Q0 strict closure 失败: {task['task_id']}")
        passed = len(outcomes) == manifest["qualification"][
            "q0_required_strict"
        ] and all(item["strict_success"] for item in outcomes)
        result = {
            "phase": "q0",
            "manifest_sha256": preflight_result["manifest_sha256"],
            "release_revision": preflight_result["release_revision"],
            "provider_requests": 0,
            "credential_reads": 0,
            "strict_success": sum(item["strict_success"] is True for item in outcomes),
            "outcomes": outcomes,
            "passed": passed,
            "completed_at": _now(),
        }
        _write_once_json(root / "q0/result.json", result)
        _finish_marker(marker_path, "passed" if passed else "failed")
        return result
    except BaseException as exc:
        failure = {
            "phase": "q0",
            "manifest_sha256": preflight_result["manifest_sha256"],
            "release_revision": preflight_result["release_revision"],
            "provider_requests": 0,
            "credential_reads": 0,
            "outcomes": outcomes,
            "passed": False,
            "error_class": type(exc).__name__,
            "completed_at": _now(),
        }
        if not (root / "q0/result.json").exists():
            _write_once_json(root / "q0/result.json", failure)
        _finish_marker(marker_path, "failed", type(exc).__name__)
        raise


def _experiment_policy(
    manifest: dict[str, Any], task: dict[str, Any], repetition: int
) -> ExperimentPolicy:
    provider = manifest["provider"]
    budget = manifest["budget"]["per_arm"]
    return ExperimentPolicy(
        benchmark_id=IDENTITY,
        manifest_sha256=_canonical_sha256(manifest),
        case_id=task["task_id"],
        condition="fixed_agent_continuation",
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


def _token_observation(events_path: Path) -> dict[str, Any]:
    requests = []
    started = 0
    failed = 0
    for line in events_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        event_type = event.get("event_type")
        payload = event.get("payload", {})
        if event_type == "model.request_started":
            started += 1
        elif event_type == "model.request_failed":
            failed += 1
        elif event_type == "model.request_completed":
            requests.append(
                {
                    "request_sequence": payload.get("request_sequence"),
                    "input_tokens": payload.get("input_tokens"),
                    "output_tokens": payload.get("output_tokens"),
                    "recorded_tokens": payload.get("recorded_tokens"),
                }
            )
    valid = all(
        type(item[field]) is int and item[field] >= 0
        for item in requests
        for field in (
            "request_sequence",
            "input_tokens",
            "output_tokens",
            "recorded_tokens",
        )
    )
    input_tokens = sum(item["input_tokens"] for item in requests) if valid else None
    output_tokens = sum(item["output_tokens"] for item in requests) if valid else None
    recorded_tokens = (
        sum(item["recorded_tokens"] for item in requests) if valid else None
    )
    return {
        "requests_started": started,
        "requests_completed": len(requests),
        "requests_failed": failed,
        "requests": requests,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "recorded_tokens": recorded_tokens,
        "complete": valid and failed == 0 and started == len(requests),
    }


def _budget_record(
    manifest: dict[str, Any],
    parent: dict[str, Any],
    node_result: AgentBuildNodeResult | None,
    tokens: dict[str, Any],
    duration_ms: int,
    session: Any,
) -> dict[str, Any]:
    provider = manifest["provider"]
    input_tokens = tokens["input_tokens"] if tokens["input_tokens"] is not None else 0
    output_tokens = (
        tokens["output_tokens"] if tokens["output_tokens"] is not None else 0
    )
    cost_microusd = round(
        input_tokens * provider["input_price_usd_per_million_tokens"]
        + output_tokens * provider["output_price_usd_per_million_tokens"]
    )
    current = get_compile_services().manager.load_session(
        session.session_id, session.thread_id
    )
    build_executions = sum(record.role in REPLAY_ROLES for record in current.commands)
    delta = {
        "wall_clock_milliseconds": duration_ms,
        "provider_requests": node_result.usage.model_requests
        if node_result is not None
        else tokens["requests_started"],
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "provider_cost_microusd": cost_microusd,
        "build_executions": build_executions,
    }
    before = {key: int(parent.get(key, 0)) for key in delta}
    after = {key: before[key] + delta[key] for key in delta}
    complete = (
        node_result is not None
        and tokens["complete"] is True
        and tokens["recorded_tokens"] == node_result.usage.recorded_tokens
        and tokens["requests_completed"] == node_result.usage.model_requests
    )
    return {
        "before": before,
        "delta": delta,
        "after": after,
        "conserved": all(after[key] == before[key] + delta[key] for key in delta),
        "complete": complete,
    }


async def _run_agent_arm(
    manifest: dict[str, Any],
    *,
    phase: str,
    sequence: int,
    task: dict[str, Any],
    state_id: str,
    repetition: int,
    arm_dir: Path,
    release_revision: str,
) -> dict[str, Any]:
    marker_path = arm_dir / "attempt.json"
    result_path = arm_dir / "result.json"
    if marker_path.exists() or result_path.exists():
        raise QualificationError(f"arm 已被声明，禁止 retry: {phase}:{sequence}")
    _write_once_json(
        marker_path,
        {
            "identity": IDENTITY,
            "phase": phase,
            "sequence": sequence,
            "task_id": task["task_id"],
            "checkpoint_state_id": state_id,
            "repetition": repetition,
            "release_revision": release_revision,
            "manifest_sha256": _canonical_sha256(manifest),
            "status": "started",
            "started_at": _now(),
            "completed_at": None,
            "error_class": None,
        },
    )
    thread_id = f"issue-429-{phase}-{sequence:02d}-{uuid.uuid4().hex[:12]}"
    experiment = ExperimentLedger.create(
        arm_dir / "experiment.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={
            "identity": IDENTITY,
            "phase": phase,
            "sequence": sequence,
            "task_id": task["task_id"],
        },
    )
    session = None
    active = False
    cleanup_succeeded = False
    node_result = None
    evaluation = None
    error_class = None
    checkpoint = None
    parent_budget = None
    started = time.monotonic()
    try:
        activate_experiment(
            thread_id=thread_id,
            experiment_id=experiment.experiment_id,
            physical_attempt_id=experiment.physical_attempt_id,
            ledger=experiment,
            policy=_experiment_policy(manifest, task, repetition),
        )
        active = True
        session, checkpoint, message, parent_budget = _prepare_restored_session(
            manifest,
            task,
            state_id,
            thread_id=thread_id,
            run_id=f"issue-429-{phase}-{sequence:02d}-{uuid.uuid4().hex}",
        )
        attempt_id = f"{phase}-{sequence:02d}-{task['task_id']}-r{repetition}"
        node_input = _node_input(
            manifest,
            task,
            session,
            attempt_id=attempt_id,
            state_id=state_id,
            checkpoint=checkpoint,
            message=message,
            parent_budget=parent_budget,
        )
        model = model_runner._create_provider_model(
            {"provider_candidate": manifest["provider"]},
            experiment_thread_id=thread_id,
        )
        node_result = await runtime_v3.run_agent_workflow_node_v3(
            node_input=node_input,
            session=session,
            manager=get_compile_services().manager,
            model=model,
            oracle_registry={_oracle(task).oracle_ref: _oracle(task)},
        )
        if node_result.candidate_submitted:
            evaluation = _evaluate(
                task,
                node_input,
                node_result,
                session,
                _candidate_path(session, attempt_id),
                f"{phase}-{sequence:02d}-{task['task_id']}-evaluation-v1",
            )
        finalized, cleanup = _safe_cleanup(session)
        cleanup_succeeded = True
        experiment.append("experiment.completed", {"status": "classified"})
    except BaseException as exc:
        error_class = type(exc).__name__
        if active:
            deactivate_experiment(thread_id)
            active = False
        if session is not None and not cleanup_succeeded:
            try:
                finalized, cleanup = _safe_cleanup(
                    session,
                    interrupted_status="failed",
                    error=f"{phase} arm error: {error_class}",
                )
                cleanup_succeeded = True
            except Exception as cleanup_exc:
                error_class = f"{error_class}+{type(cleanup_exc).__name__}"
                cleanup_succeeded = False
    finally:
        if active:
            deactivate_experiment(thread_id)
    duration_ms = round((time.monotonic() - started) * 1000)
    tokens = {
        "requests_started": 0,
        "requests_completed": 0,
        "requests_failed": 0,
        "requests": [],
        "input_tokens": 0,
        "output_tokens": 0,
        "recorded_tokens": 0,
        "complete": node_result is not None and node_result.usage.model_requests == 0,
    }
    if session is not None:
        events_path = (
            Path(session.metadata_path).parent
            / "agent-workflow"
            / f"{phase}-{sequence:02d}-{task['task_id']}-r{repetition}"
            / "events.jsonl"
        )
        if events_path.is_file():
            tokens = _token_observation(events_path)
    budget_record = (
        _budget_record(
            manifest, parent_budget or {}, node_result, tokens, duration_ms, session
        )
        if session is not None
        else None
    )
    strict_success = bool(
        evaluation is not None and evaluation.strict_reproducible_build_success
    )
    if error_class is not None:
        terminal = "arm_error"
    elif (
        node_result is not None
        and node_result.budget_terminal_reason == "node_timeout_seconds"
    ):
        terminal = "timeout"
    elif node_result is not None and node_result.budget_terminal_reason is not None:
        terminal = "budget_exhausted"
    elif strict_success:
        terminal = "strict_success"
    elif evaluation is not None:
        terminal = "evaluated_failure"
    else:
        terminal = "no_candidate"
    post_observation = None
    session_tree_sha256 = None
    if session is not None:
        current = get_compile_services().manager.load_session(
            session.session_id, session.thread_id
        )
        post_observation = {
            "session_status": current.status,
            "command_count": len(current.commands),
            "artifact_count": len(current.artifacts),
            "verification_status": current.verification.status
            if current.verification is not None
            else None,
            "finalized_at": current.finalized_at,
        }
        session_tree_sha256 = _snapshot_session(current, arm_dir / "session-evidence")
    result = {
        "phase": phase,
        "sequence": sequence,
        "task_id": task["task_id"],
        "build_system": task["build_system"],
        "checkpoint_state_id": state_id,
        "checkpoint_depth": int(state_id.rsplit("-", 1)[-1]),
        "checkpoint_sha256": checkpoint.get("checkpoint_sha256")
        if checkpoint
        else None,
        "repetition": repetition,
        "release_revision": release_revision,
        "manifest_sha256": _canonical_sha256(manifest),
        "terminal_classification": terminal,
        "strict_success": strict_success,
        "candidate_submitted": bool(
            node_result is not None and node_result.candidate_submitted
        ),
        "node_result": json.loads(node_result.canonical_json())
        if node_result is not None
        else None,
        "layers": [asdict(layer) for layer in evaluation.layers]
        if evaluation is not None
        else [],
        "token_accounting": tokens,
        "budget": budget_record,
        "post_action_observation": post_observation,
        "cleanup_succeeded": cleanup_succeeded,
        "session_tree_sha256": session_tree_sha256,
        "error_class": error_class,
        "duration_milliseconds": duration_ms,
        "completed_at": _now(),
    }
    _write_once_json(result_path, result)
    marker = _load_json(marker_path)
    marker.update(status="classified", completed_at=_now(), error_class=error_class)
    _atomic_json(marker_path, marker)
    return result


def _provider_preflight(manifest: dict[str, Any]) -> None:
    credential_name = manifest["provider"]["credential_env_name"]
    if not os.environ.get(credential_name):
        raise QualificationError(
            f"缺少冻结 Provider credential 环境变量: {credential_name}"
        )


def execute_q1(manifest: dict[str, Any]) -> dict[str, Any]:
    preflight_result = preflight(manifest, phase="q1")
    root = REPO_ROOT / manifest["evidence_root"]
    _require_phase_passed(
        root,
        "q0",
        preflight_result["manifest_sha256"],
        preflight_result["release_revision"],
    )
    _provider_preflight(manifest)
    marker_path = _phase_marker(root, "q1")
    _start_marker(
        marker_path,
        preflight_result["manifest_sha256"],
        preflight_result["release_revision"],
    )
    outcomes = []
    try:
        for sequence, canary in enumerate(manifest["canary_checkpoints"], 1):
            task = _task(manifest, canary["task_id"])
            outcome = asyncio.run(
                _run_agent_arm(
                    manifest,
                    phase="q1",
                    sequence=sequence,
                    task=task,
                    state_id=canary["checkpoint_state_id"],
                    repetition=1,
                    arm_dir=root / "q1/arms" / f"{sequence:02d}-{task['task_id']}",
                    release_revision=preflight_result["release_revision"],
                )
            )
            outcomes.append(outcome)
        passed = len(outcomes) == 3 and all(
            item["candidate_submitted"]
            and len(item["layers"]) == 6
            and item["budget"] is not None
            and item["budget"]["complete"]
            and item["budget"]["conserved"]
            and item["post_action_observation"] is not None
            and item["cleanup_succeeded"]
            and item["error_class"] is None
            for item in outcomes
        )
        result = {
            "phase": "q1",
            "manifest_sha256": preflight_result["manifest_sha256"],
            "release_revision": preflight_result["release_revision"],
            "classified_candidates": sum(
                item["candidate_submitted"] and len(item["layers"]) == 6
                for item in outcomes
            ),
            "strict_success": sum(item["strict_success"] for item in outcomes),
            "outcomes": outcomes,
            "passed": passed,
            "completed_at": _now(),
        }
        _write_once_json(root / "q1/result.json", result)
        _finish_marker(marker_path, "passed" if passed else "failed")
        if not passed:
            raise QualificationError("Q1 Provider canary 未通过工程闭合门禁")
        return result
    except BaseException as exc:
        if not (root / "q1/result.json").exists():
            _write_once_json(
                root / "q1/result.json",
                {
                    "phase": "q1",
                    "manifest_sha256": preflight_result["manifest_sha256"],
                    "release_revision": preflight_result["release_revision"],
                    "outcomes": outcomes,
                    "passed": False,
                    "error_class": type(exc).__name__,
                    "completed_at": _now(),
                },
            )
        current = _load_json(marker_path)
        if current.get("status") == "started":
            _finish_marker(marker_path, "failed", type(exc).__name__)
        raise


def _formal_qualification(
    manifest: dict[str, Any], outcomes: list[dict[str, Any]]
) -> dict[str, Any]:
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in outcomes:
        by_task[item["task_id"]].append(item)
    checkpoint_rows = []
    for task in manifest["tasks"]:
        rows = by_task[task["task_id"]]
        strict = sum(item["strict_success"] for item in rows)
        checkpoint_rows.append(
            {
                "task_id": task["task_id"],
                "build_system": task["build_system"],
                "checkpoint_depth": int(task["checkpoint_state_id"].rsplit("-", 1)[-1]),
                "strict_success": strict,
                "arms": len(rows),
                "qualified": len(rows) == 3 and strict >= 2,
            }
        )
    hard_gates = {
        "classified_terminal": len(outcomes) == 27
        and all(
            item["terminal_classification"]
            in {
                "strict_success",
                "evaluated_failure",
                "no_candidate",
                "budget_exhausted",
                "timeout",
                "arm_error",
            }
            for item in outcomes
        ),
        "cost_and_budget_complete": len(outcomes) == 27
        and all(
            item["budget"] is not None
            and item["budget"]["complete"]
            and item["budget"]["conserved"]
            for item in outcomes
        ),
        "parent_checkpoint_binding": len(outcomes) == 27
        and all(
            isinstance(item["checkpoint_sha256"], str)
            and len(item["checkpoint_sha256"]) == 64
            for item in outcomes
        ),
        "post_action_observation": len(outcomes) == 27
        and all(item["post_action_observation"] is not None for item in outcomes),
        "cleanup": len(outcomes) == 27
        and all(item["cleanup_succeeded"] for item in outcomes),
        "no_infrastructure_error": len(outcomes) == 27
        and all(item["error_class"] is None for item in outcomes),
    }
    qualified = [row for row in checkpoint_rows if row["qualified"]]
    by_system = Counter(row["build_system"] for row in qualified)
    by_depth = Counter(row["checkpoint_depth"] for row in qualified)
    timeout_or_budget = sum(
        item["terminal_classification"] in {"timeout", "budget_exhausted"}
        for item in outcomes
    )
    behavior_gates = {
        "checkpoint_stability": len(qualified)
        >= manifest["qualification"]["minimum_qualified_checkpoints"],
        "system_coverage": all(
            by_system[system]
            >= manifest["qualification"]["minimum_qualified_checkpoints_per_system"]
            for system in ("cmake", "make", "autotools")
        ),
        "depth_coverage": all(
            by_depth[depth]
            >= manifest["qualification"]["minimum_qualified_checkpoints_per_depth"]
            for depth in (1, 2, 3)
        ),
        "timeout_budget_bound": timeout_or_budget
        <= manifest["qualification"]["maximum_timeout_or_budget_exhausted_arms"],
    }
    passed = all(hard_gates.values()) and all(behavior_gates.values())
    return {
        "hard_gates": hard_gates,
        "behavior_gates": behavior_gates,
        "checkpoint_rows": checkpoint_rows,
        "qualified_checkpoints": len(qualified),
        "qualified_by_system": dict(by_system),
        "qualified_by_depth": {str(key): value for key, value in by_depth.items()},
        "timeout_or_budget_exhausted": timeout_or_budget,
        "passed": passed,
        "decision": manifest["qualification"]["pass_decision"]
        if passed
        else manifest["qualification"]["fail_decision"],
    }


def execute_q2(manifest: dict[str, Any]) -> dict[str, Any]:
    preflight_result = preflight(manifest, phase="q2")
    root = REPO_ROOT / manifest["evidence_root"]
    _require_phase_passed(
        root,
        "q0",
        preflight_result["manifest_sha256"],
        preflight_result["release_revision"],
    )
    _require_phase_passed(
        root,
        "q1",
        preflight_result["manifest_sha256"],
        preflight_result["release_revision"],
    )
    _provider_preflight(manifest)
    marker_path = _phase_marker(root, "q2")
    if not marker_path.exists():
        _start_marker(
            marker_path,
            preflight_result["manifest_sha256"],
            preflight_result["release_revision"],
        )
    marker = _load_json(marker_path)
    if marker.get("status") != "started":
        raise QualificationError("Q2 已封口")
    outcomes = []
    try:
        for arm in manifest["formal_schedule"]:
            task = _task(manifest, arm["task_id"])
            arm_dir = (
                root
                / "q2/arms"
                / f"{arm['sequence']:02d}-{task['task_id']}-r{arm['repetition']}"
            )
            result_path = arm_dir / "result.json"
            attempt_path = arm_dir / "attempt.json"
            if result_path.is_file():
                existing = _load_json(result_path)
                if (
                    existing.get("sequence") != arm["sequence"]
                    or existing.get("task_id") != task["task_id"]
                ):
                    raise QualificationError("Q2 completed prefix identity 漂移")
                outcomes.append(existing)
                continue
            if attempt_path.exists():
                raise QualificationError(
                    "Q2 存在 started 但无 result 的 arm，禁止 retry"
                )
            outcome = asyncio.run(
                _run_agent_arm(
                    manifest,
                    phase="q2",
                    sequence=arm["sequence"],
                    task=task,
                    state_id=task["checkpoint_state_id"],
                    repetition=arm["repetition"],
                    arm_dir=arm_dir,
                    release_revision=preflight_result["release_revision"],
                )
            )
            outcomes.append(outcome)
            requests = sum(
                item["token_accounting"]["requests_started"] for item in outcomes
            )
            tokens = sum(
                (item["token_accounting"]["recorded_tokens"] or 0) for item in outcomes
            )
            if (
                requests > manifest["budget"]["total_provider_requests"]
                or tokens > manifest["budget"]["total_recorded_tokens"]
            ):
                raise QualificationError("Q1+Q2 总 Provider 预算上限被突破")
        qualification = _formal_qualification(manifest, outcomes)
        result = {
            "phase": "q2",
            "manifest_sha256": preflight_result["manifest_sha256"],
            "release_revision": preflight_result["release_revision"],
            "outcomes": outcomes,
            "qualification": qualification,
            "passed": qualification["passed"],
            "completed_at": _now(),
        }
        _write_once_json(root / "q2/result.json", result)
        _finish_marker(marker_path, "passed" if qualification["passed"] else "failed")
        return result
    except BaseException as exc:
        current = _load_json(marker_path)
        if current.get("status") == "started":
            _finish_marker(marker_path, "failed", type(exc).__name__)
        if not (root / "q2/result.json").exists():
            _write_once_json(
                root / "q2/result.json",
                {
                    "phase": "q2",
                    "manifest_sha256": preflight_result["manifest_sha256"],
                    "release_revision": preflight_result["release_revision"],
                    "outcomes": outcomes,
                    "qualification": _formal_qualification(manifest, outcomes),
                    "passed": False,
                    "error_class": type(exc).__name__,
                    "completed_at": _now(),
                },
            )
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
    validate_manifest(manifest)
    root = REPO_ROOT / manifest["evidence_root"]
    identity = _load_json(root / "identity.json")
    q0 = _load_json(root / "q0/result.json")
    q1 = _load_json(root / "q1/result.json")
    q2 = _load_json(root / "q2/result.json")
    expected_manifest_sha256 = _canonical_sha256(manifest)
    phase_hashes = {item.get("manifest_sha256") for item in (identity, q0, q1, q2)}
    release_revisions = {
        item.get("release_revision") for item in (identity, q0, q1, q2)
    }
    valid = (
        phase_hashes == {expected_manifest_sha256}
        and len(release_revisions) == 1
        and q0.get("passed") is True
        and q1.get("passed") is True
        and len(q2.get("outcomes", [])) == 27
        and _formal_qualification(manifest, q2["outcomes"]) == q2.get("qualification")
    )
    _require_zero_managed_resources()
    inventory_path = root / "inventory.json"
    inventory = _inventory(root)
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
        "manifest_sha256": expected_manifest_sha256,
        "release_revision": next(iter(release_revisions))
        if len(release_revisions) == 1
        else None,
        "q0_passed": q0.get("passed"),
        "q1_passed": q1.get("passed"),
        "q2_decision": q2.get("qualification", {}).get("decision"),
        "inventory": inventory,
        "zero_managed_resources": True,
    }


def write_report(manifest: dict[str, Any]) -> dict[str, Any]:
    root = REPO_ROOT / manifest["evidence_root"]
    audit_result = audit(manifest)
    if not audit_result["valid"]:
        raise QualificationError("evidence audit 未通过")
    q0 = _load_json(root / "q0/result.json")
    q1 = _load_json(root / "q1/result.json")
    q2 = _load_json(root / "q2/result.json")
    outcomes = q2["outcomes"]
    totals = {
        "strict_success": sum(item["strict_success"] for item in outcomes),
        "provider_requests": sum(
            item["token_accounting"]["requests_started"] for item in outcomes
        ),
        "input_tokens": sum(
            item["token_accounting"]["input_tokens"] or 0 for item in outcomes
        ),
        "output_tokens": sum(
            item["token_accounting"]["output_tokens"] or 0 for item in outcomes
        ),
        "provider_cost_microusd": sum(
            item["budget"]["delta"]["provider_cost_microusd"]
            for item in outcomes
            if item["budget"]
        ),
        "wall_clock_milliseconds": sum(
            item["duration_milliseconds"] for item in outcomes
        ),
    }
    report = {
        "identity": IDENTITY,
        "status": "completed",
        "decision": q2["qualification"]["decision"],
        "q0": {"strict_success": q0["strict_success"], "cases": len(q0["outcomes"])},
        "q1": {
            "classified_candidates": q1["classified_candidates"],
            "strict_success": q1["strict_success"],
        },
        "q2": {"totals": totals, "qualification": q2["qualification"]},
        "audit": audit_result,
        "interpretation_boundary": "只评价冻结受控 checkpoint 上固定 Agent continuation 的稳定性、成本完整性和恢复性；不评价动态预算 controller、Jev、自然失败或开放世界。",
        "completed_at": _now(),
    }
    REPORT_JSON_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    q = q2["qualification"]
    markdown = (
        "# 固定 Agent continuation 资格 v1 结果\n\n"
        f"**决定：`{report['decision']}`。**\n\n"
        f"Q0 reference strict：`{q0['strict_success']}/9`；Q1 classified candidate：`{q1['classified_candidates']}/3`，strict：`{q1['strict_success']}/3`。\n\n"
        "## Q2 正式资格\n\n"
        f"- Strict success arms：`{totals['strict_success']}/27`；\n"
        f"- 达标 checkpoint：`{q['qualified_checkpoints']}/9`；\n"
        f"- 分构建系统达标：`{json.dumps(q['qualified_by_system'], ensure_ascii=False, sort_keys=True)}`；\n"
        f"- 分深度达标：`{json.dumps(q['qualified_by_depth'], ensure_ascii=False, sort_keys=True)}`；\n"
        f"- timeout/budget exhausted：`{q['timeout_or_budget_exhausted']}/27`；\n"
        f"- Provider requests：`{totals['provider_requests']}`；input/output tokens：`{totals['input_tokens']}/{totals['output_tokens']}`；\n"
        f"- 估算 Provider 成本：`${totals['provider_cost_microusd'] / 1_000_000:.6f}`；累计 arm wall clock：`{totals['wall_clock_milliseconds']} ms`。\n\n"
        "## 门禁\n\n"
        + "\n".join(
            f"- `{name}`：{'通过' if value else '失败'}"
            for name, value in {**q["hard_gates"], **q["behavior_gates"]}.items()
        )
        + "\n\n## 解释边界\n\n"
        + report["interpretation_boundary"]
        + "\n\n## Evidence\n\n"
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
        "q0_cases": [task["checkpoint_state_id"] for task in manifest["tasks"]],
        "q1_cases": [
            item["checkpoint_state_id"] for item in manifest["canary_checkpoints"]
        ],
        "q2_arms": len(manifest["formal_schedule"]),
        "provider_request_ceiling": manifest["budget"]["total_provider_requests"],
        "provider_token_ceiling": manifest["budget"]["total_recorded_tokens"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "validate",
            "plan",
            "preflight-q0",
            "preflight-q1",
            "preflight-q2",
            "q0",
            "q1",
            "q2",
            "audit",
            "seal",
            "report",
        ),
    )
    arguments = parser.parse_args()
    manifest = _manifest()
    if arguments.command == "validate":
        payload = {
            "valid": True,
            "manifest_sha256": _canonical_sha256(validate_manifest(manifest)),
        }
    elif arguments.command == "plan":
        payload = _plan(manifest)
    elif arguments.command.startswith("preflight-"):
        payload = preflight(
            manifest, phase=arguments.command.removeprefix("preflight-")
        )
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
