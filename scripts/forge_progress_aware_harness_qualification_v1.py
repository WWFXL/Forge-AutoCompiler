#!/usr/bin/env python3
"""Issue #433：进展感知 Agent Harness 的零 Provider 资格门禁。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import Field

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_PATH.parent)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_agent_continuation_qualification_v2 as parent_runner  # noqa: E402

from deerflow.compile.agent_workflow_runtime_v4 import (  # noqa: E402
    run_agent_workflow_node_v4,
)
from deerflow.compile.agent_workflow_schemas import (  # noqa: E402
    AgentBuildNodeInput,
    AgentWorkflowBudget,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowTargetContract,
)
from deerflow.compile.external_evaluator import FunctionalOracleSpec  # noqa: E402
from deerflow.compile.external_evaluator_v4 import (  # noqa: E402
    ForgeCompileEvaluationBackend,
    run_external_evaluator_v4,
)
from deerflow.compile.operations import (  # noqa: E402
    cleanup_and_finalize_compile_session_impl,
    get_compile_services,
)

IDENTITY = "cpp-progress-aware-harness-qualification-v1"
TRACKING_ISSUE = 433
BRANCH = "yiwei/433-progress-aware-harness-qualification"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests" / f"{IDENTITY}.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-progress-aware-harness-qualification-v1.schema.json"
PREREGISTRATION_PATH = REPO_ROOT / "benchmarks/preregistrations" / f"{IDENTITY}.md"
SPEC_PATH = REPO_ROOT / "docs/superpowers/specs/2026-10-12-progress-aware-agent-harness-qualification-design.md"
PLAN_PATH = REPO_ROOT / "docs/superpowers/plans/2026-10-12-progress-aware-agent-harness-qualification.md"
REPORT_JSON_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.json"
REPORT_MD_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.md"
MANAGED_PREFIXES = ("deerflow-compile-", "deerflow-replay-")
COMPONENT_PATHS = (
    "scripts/forge_progress_aware_harness_qualification_v1.py",
    "scripts/forge_agent_continuation_qualification_v2.py",
    "scripts/forge_checkpoint_archive.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v2.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v3.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v4.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_schemas.py",
    "backend/packages/harness/deerflow/compile/candidate_verifier.py",
    "backend/packages/harness/deerflow/compile/external_evaluator.py",
    "backend/packages/harness/deerflow/compile/external_evaluator_v3.py",
    "backend/packages/harness/deerflow/compile/external_evaluator_v4.py",
    "backend/packages/harness/deerflow/compile/operations.py",
    "backend/packages/harness/deerflow/tools/bound_compile_tools.py",
    "backend/tests/test_agent_workflow_runtime_v4.py",
    "backend/tests/test_forge_progress_aware_harness_qualification_v1.py",
    "benchmarks/schemas/forge-progress-aware-harness-qualification-v1.schema.json",
    "benchmarks/preregistrations/cpp-progress-aware-harness-qualification-v1.md",
    "docs/superpowers/specs/2026-10-12-progress-aware-agent-harness-qualification-design.md",
    "docs/superpowers/plans/2026-10-12-progress-aware-agent-harness-qualification.md",
)


class QualificationError(RuntimeError):
    """资格身份、运行或证据不满足冻结合同。"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
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


def _validate_parent_inventory(manifest: dict[str, Any]) -> str:
    root = REPO_ROOT / manifest["parent"]["evidence_root"]
    inventory = _load_json(root / "inventory.json")
    files = inventory.get("files")
    expected = manifest["parent"]["inventory_canonical_sha256"]
    if not isinstance(files, list) or inventory.get("canonical_sha256") != expected:
        raise QualificationError("parent inventory identity 漂移")
    if _canonical_sha256(files) != expected:
        raise QualificationError("parent inventory canonical SHA-256 漂移")
    for item in files:
        path = root / item["path"]
        if not path.is_file() or path.stat().st_size != item["size"] or _file_sha256(path) != item["sha256"]:
            raise QualificationError(f"parent evidence 文件漂移: {item['path']}")
    return expected


def validate_manifest(manifest: dict[str, Any], *, require_components: bool = True) -> dict[str, Any]:
    schema = _load_json(SCHEMA_PATH)
    errors = sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda error: list(error.path))
    if errors:
        raise QualificationError(f"manifest Schema 无效: {errors[0].message}")
    if manifest["identity"] != IDENTITY or manifest["issue"] != TRACKING_ISSUE or manifest["branch"] != BRANCH:
        raise QualificationError("manifest identity 漂移")
    expected_authorization = {
        "credential_reads": False,
        "provider_calls": False,
        "jev_calls": False,
        "formal_attempts": 1,
        "historical_evidence_write": False,
        "replacement": False,
        "backfill": False,
    }
    if manifest["authorization"] != expected_authorization:
        raise QualificationError("授权边界漂移")
    task = manifest["task"]
    if [item["role"] for item in task["commands"]] != [
        "configure",
        "build",
        "artifact_stage",
    ]:
        raise QualificationError("脚本动作顺序漂移")
    checkpoint, _message, _budget = parent_runner._checkpoint_payload(task["checkpoint_state_id"])
    source = checkpoint["source"]
    if (
        source["repository_url"] != task["repository_url"]
        or source["commit_sha"] != task["commit_sha"]
        or checkpoint["checkpoint_sha256"] != manifest["parent"]["checkpoint_sha256"]
        or checkpoint["image_id"] != manifest["environment"]["image_id"]
    ):
        raise QualificationError("parent checkpoint identity 漂移")
    components = manifest["components"]
    if require_components:
        if set(components) != set(COMPONENT_PATHS):
            raise QualificationError("冻结组件集合无效")
        for relative, expected_sha256 in components.items():
            if _file_sha256(REPO_ROOT / relative) != expected_sha256:
                raise QualificationError(f"冻结组件漂移: {relative}")
    _validate_parent_inventory(manifest)
    return manifest


def _require_zero_managed_resources() -> list[str]:
    names = _docker("ps", "-a", "--format", "{{.Names}}")
    managed = sorted(name for name in names.splitlines() if name.startswith(MANAGED_PREFIXES))
    if managed:
        raise QualificationError(f"存在受管容器: {','.join(managed)}")
    return managed


def preflight(manifest: dict[str, Any], *, require_create_once: bool) -> dict[str, Any]:
    validate_manifest(manifest)
    if _git("branch", "--show-current") != BRANCH:
        raise QualificationError("当前分支与 identity 不一致")
    if _git("status", "--porcelain", "--untracked-files=normal"):
        raise QualificationError("正式门禁要求干净工作树")
    head = _git("rev-parse", "HEAD")
    remote_refs = {line.strip() for line in _git("branch", "-r", "--contains", head).splitlines()}
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
    evidence_root = REPO_ROOT / manifest["evidence_root"]
    if require_create_once and evidence_root.exists():
        raise QualificationError("create-once evidence root 已存在")
    os.environ["DEER_FLOW_WORKSPACE_ROOT"] = str(REPO_ROOT)
    os.environ["DEER_FLOW_HOST_WORKSPACE_ROOT"] = str(REPO_ROOT)
    return {
        "release_revision": head,
        "manifest_sha256": _canonical_sha256(manifest),
        "parent_inventory_canonical_sha256": _validate_parent_inventory(manifest),
        "image_id": image_id,
        "credential_reads": 0,
        "provider_requests": 0,
    }


def plan(manifest: dict[str, Any]) -> dict[str, Any]:
    validate_manifest(manifest)
    task = manifest["task"]
    return {
        "identity": IDENTITY,
        "issue": TRACKING_ISSUE,
        "mode": "zero_provider_engineering_gate",
        "checkpoint_state_id": task["checkpoint_state_id"],
        "scripted_actions": [
            *[item["role"] for item in task["commands"]],
            "blocked_diagnostic_after_ready",
            "submit_from_progress_snapshot",
        ],
        "strict_endpoint": [
            "candidate_prefreeze_verifier",
            "external_evaluator_s0_s5",
            "functional_oracle",
            "clean_replay",
            "cleanup",
        ],
        "provider_requests": 0,
        "credential_reads": 0,
        "decision_on_pass": manifest["qualification"]["pass_decision"],
        "decision_on_fail": manifest["qualification"]["fail_decision"],
    }


def _progress_payload(messages: Sequence[BaseMessage]) -> dict[str, Any]:
    for message in reversed(messages):
        content = getattr(message, "content", None)
        if not isinstance(content, str):
            continue
        start_tag = "<authoritative_compile_progress>\n"
        end_tag = "\n</authoritative_compile_progress>"
        if start_tag not in content or end_tag not in content:
            continue
        encoded = content.split(start_tag, 1)[1].split(end_tag, 1)[0]
        value = json.loads(encoded)
        if isinstance(value, dict):
            return value
    raise QualificationError("脚本模型未收到 authoritative progress snapshot")


class ZeroProviderProgressModel(BaseChatModel):
    """只按冻结脚本与权威快照发出工具调用，不访问网络或凭据。"""

    task: dict[str, object]
    calls: int = 0
    observations: list[dict[str, object]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "progress-aware-zero-provider-script-v1"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable:
        del tools, tool_choice, kwargs
        return self

    @staticmethod
    def _call(name: str, args: dict[str, Any], call_id: str) -> AIMessage:
        return AIMessage(
            content="",
            tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
            usage_metadata={
                "input_tokens": 7,
                "output_tokens": 5,
                "total_tokens": 12,
            },
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        progress = _progress_payload(messages)
        self.observations.append(progress)
        commands = self.task["commands"]
        if self.calls < len(commands):
            command = commands[self.calls]
            response = self._call(
                "run_container_bash",
                {
                    "command": command["command"],
                    "command_role": command["role"],
                    "timeout_seconds": command["timeout_seconds"],
                    "workdir": "/workspace/repo",
                },
                f"script-command-{self.calls + 1}",
            )
        elif self.calls == len(commands):
            if progress.get("candidate_ready") is not True:
                raise QualificationError("候选尚未 ready，不能执行 ready guard 探针")
            response = self._call(
                "run_container_bash",
                {
                    "command": "find /artifacts -maxdepth 2 -type f -print",
                    "command_role": "diagnostic",
                    "timeout_seconds": 30,
                    "workdir": "/workspace/repo",
                },
                "script-ready-guard-probe",
            )
        elif self.calls == len(commands) + 1:
            if progress.get("candidate_ready") is not True:
                raise QualificationError("ready guard 后候选状态漂移")
            target = self.task["target"]
            build_ids = progress.get("successful_build_command_ids", [])
            recipe_ids = progress.get("recommended_recipe_command_ids", [])
            mapping = progress.get("recommended_target_mapping", {})
            if not build_ids or mapping != {target["target_id"]: target["artifact_path"]}:
                raise QualificationError("progress snapshot 无法构造冻结提交")
            response = self._call(
                "submit_candidate_v1",
                {
                    "candidate_id": "progress-aware-zero-provider-candidate-v1",
                    "build_system": self.task["build_system"],
                    "supporting_command_ids": build_ids,
                    "artifact_paths": [target["artifact_path"]],
                    "target_mapping": mapping,
                    "recipe_command_ids": recipe_ids,
                    "agent_summary": "Issue #433 zero-provider H1 qualification.",
                    "known_limitations": [],
                },
                "script-submit-from-progress",
            )
        else:
            raise QualificationError("脚本模型收到未预注册的额外请求")
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=response)])


def _oracle(task: dict[str, Any]) -> FunctionalOracleSpec:
    oracle = task["oracle"]
    return FunctionalOracleSpec(
        oracle_ref=f"issue-433-{task['task_id']}-oracle-v1",
        argv=("bash", "-lc", oracle["command"]),
        workdir=oracle["workdir"],
        timeout_seconds=oracle["timeout_seconds"],
    )


def _node_input(
    manifest: dict[str, Any],
    session: Any,
    checkpoint: dict[str, Any],
    message: dict[str, Any],
    parent_budget: dict[str, Any],
    *,
    attempt_id: str,
) -> AgentBuildNodeInput:
    task = manifest["task"]
    target = task["target"]
    return AgentBuildNodeInput(
        task_id=task["task_id"],
        attempt_id=attempt_id,
        session_id=session.session_id,
        repository_url=task["repository_url"],
        commit_sha=task["commit_sha"],
        source_snapshot_sha256=checkpoint["workspace_snapshot_sha256"],
        build_system_candidates=(task["build_system"],),
        target_contract=AgentWorkflowTargetContract(
            target_id=target["target_id"],
            artifact_types=(target["artifact_type"],),
            artifact_path_patterns=(target["artifact_path"],),
            functional_oracle_ref=_oracle(task).oracle_ref,
        ),
        operation_policy_ref="issue-433-progress-aware-zero-provider-v1",
        environment=AgentWorkflowEnvironmentIdentity(
            image_id=manifest["environment"]["image_id"],
            parallel_jobs=manifest["environment"]["parallel_jobs"],
            network_policy=manifest["environment"]["network_policy"],
        ),
        budget=AgentWorkflowBudget(**manifest["budget"]),
        experiment_identity=AgentWorkflowExperimentIdentity(
            manifest_sha256=_canonical_sha256(manifest),
            protocol_sha256=_file_sha256(PREREGISTRATION_PATH),
            runner_sha256=_file_sha256(SCRIPT_PATH),
        ),
        initial_observation={
            "zero_provider": True,
            "harness": "progress-aware-runtime-v4",
            "checkpoint_state_id": task["checkpoint_state_id"],
            "checkpoint_sha256": checkpoint["checkpoint_sha256"],
            "checkpoint_message": message,
            "parent_budget": parent_budget,
            "required_candidate_artifacts": (target["artifact_path"],),
            "selected_build_system": task["build_system"],
        },
    )


def _events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _event_summary(events: Sequence[dict[str, Any]]) -> dict[str, Any]:
    event_types = [event.get("event_type") for event in events]
    progress = [event for event in events if event.get("event_type") == "harness.progress_snapshot"]
    compactions = [event for event in events if event.get("event_type") == "harness.context_compacted"]
    rejections = [event for event in events if event.get("event_type") == "harness.tool_rejected"]
    return {
        "progress_snapshot_count": len(progress),
        "context_compaction_count": len(compactions),
        "effective_compaction_count": sum(int(event.get("payload", {}).get("original_message_count", 0)) > int(event.get("payload", {}).get("retained_message_count", 0)) for event in compactions),
        "ready_guard_rejections": sum(event.get("payload", {}).get("reason") == "candidate_ready_requires_submit" for event in rejections),
        "candidate_submit_accepted": "candidate.submit_accepted" in event_types,
        "candidate_prefreeze_verified": ("candidate.prefreeze_verification_completed" in event_types),
        "event_count": len(events),
    }


def _snapshot_session(session: Any, destination: Path) -> str:
    source = Path(session.metadata_path).parent
    shutil.copytree(source, destination, symlinks=True)
    entries: list[dict[str, Any]] = []
    for path in sorted(destination.rglob("*")):
        relative = path.relative_to(destination).as_posix()
        if path.is_symlink():
            entries.append({"path": relative, "kind": "symlink", "target": os.readlink(path)})
        elif path.is_file():
            entries.append(
                {
                    "path": relative,
                    "kind": "file",
                    "size": path.stat().st_size,
                    "sha256": _file_sha256(path),
                }
            )
    return _canonical_sha256(entries)


def _qualification(result: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    events = result.get("event_summary", {})
    usage = result.get("usage", {})
    gates = {
        "zero_provider_boundary": (result.get("credential_reads") == 0 and result.get("provider_requests") == 0),
        "script_completed": result.get("script_model_calls") == 5,
        "progress_snapshot": events.get("progress_snapshot_count", 0) >= 5,
        "context_compaction": events.get("effective_compaction_count", 0) >= 1,
        "ready_guard": events.get("ready_guard_rejections") == 1,
        "prefreeze_verifier": events.get("candidate_prefreeze_verified") is True,
        "candidate_submit": (events.get("candidate_submit_accepted") is True and result.get("candidate_submitted") is True),
        "strict_endpoint": (result.get("strict_success") is True and result.get("layers") == [{"layer": layer, "status": "passed"} for layer in ("S0", "S1", "S2", "S3", "S4", "S5")]),
        "budget_accounting": (usage.get("model_requests") == 5 and usage.get("tool_calls") == 5 and usage.get("commands") == 3 and usage.get("agent_steps") == 10),
        "cleanup": (result.get("cleanup_succeeded") is True and result.get("managed_containers_after_cleanup") == []),
        "parent_inventory_unchanged": (result.get("parent_inventory_before") == result.get("parent_inventory_after") == manifest["parent"]["inventory_canonical_sha256"]),
    }
    passed = all(gates.values())
    return {
        "gates": gates,
        "passed": passed,
        "decision": (manifest["qualification"]["pass_decision"] if passed else manifest["qualification"]["fail_decision"]),
    }


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


async def _execute_gate(manifest: dict[str, Any], preflight_result: dict[str, Any], root: Path) -> dict[str, Any]:
    task = manifest["task"]
    attempt_id = "zero-provider-gate-v1"
    session = None
    cleanup_succeeded = False
    model = ZeroProviderProgressModel(task=task)
    started = time.monotonic()
    try:
        session, checkpoint, message, parent_budget = parent_runner._prepare_restored_session(
            manifest,
            task,
            task["checkpoint_state_id"],
            thread_id=f"issue-433-gate-{uuid.uuid4().hex[:12]}",
            run_id=f"issue-433-gate-{uuid.uuid4().hex}",
        )
        node_input = _node_input(
            manifest,
            session,
            checkpoint,
            message,
            parent_budget,
            attempt_id=attempt_id,
        )
        oracle = _oracle(task)
        node_result = await run_agent_workflow_node_v4(
            node_input=node_input,
            session=session,
            manager=get_compile_services().manager,
            model=model,
            oracle_registry={oracle.oracle_ref: oracle},
        )
        candidate_path = Path(session.metadata_path).parent / "agent-workflow" / attempt_id / "candidate.json"
        evaluation = run_external_evaluator_v4(
            node_input=node_input,
            node_result=node_result,
            session=session,
            manager=get_compile_services().manager,
            candidate_path=candidate_path,
            evaluation_id="issue-433-zero-provider-evaluation-v1",
            backend=ForgeCompileEvaluationBackend(oracle_registry={oracle.oracle_ref: oracle}),
        )
        finalized, cleanup = cleanup_and_finalize_compile_session_impl(session=session)
        cleanup_succeeded = cleanup.succeeded
        managed = _require_zero_managed_resources()
        workflow_dir = Path(finalized.metadata_path).parent / "agent-workflow" / attempt_id
        event_summary = _event_summary(_events(workflow_dir / "events.jsonl"))
        session_tree_sha256 = _snapshot_session(finalized, root / "session-evidence")
        _write_once_json(
            root / "model-observations.json",
            {
                "model_type": model._llm_type,
                "provider_requests": 0,
                "credential_reads": 0,
                "calls": model.calls,
                "progress_snapshots": model.observations,
            },
        )
        layers = [{"layer": layer.layer, "status": layer.status} for layer in evaluation.layers]
        return {
            "identity": IDENTITY,
            "release_revision": preflight_result["release_revision"],
            "manifest_sha256": preflight_result["manifest_sha256"],
            "checkpoint_state_id": task["checkpoint_state_id"],
            "checkpoint_sha256": checkpoint["checkpoint_sha256"],
            "credential_reads": 0,
            "provider_requests": 0,
            "script_model_calls": model.calls,
            "node_status": node_result.node_status,
            "candidate_submitted": node_result.candidate_submitted,
            "usage": asdict(node_result.usage),
            "event_summary": event_summary,
            "strict_success": evaluation.strict_reproducible_build_success,
            "layers": layers,
            "bitwise_reproducible": evaluation.bitwise_reproducible,
            "cleanup_succeeded": cleanup_succeeded,
            "session_status": finalized.status,
            "managed_containers_after_cleanup": managed,
            "parent_inventory_before": preflight_result["parent_inventory_canonical_sha256"],
            "parent_inventory_after": _validate_parent_inventory(manifest),
            "session_tree_sha256": session_tree_sha256,
            "duration_milliseconds": round((time.monotonic() - started) * 1000),
            "completed_at": _now(),
        }
    finally:
        if session is not None and not cleanup_succeeded:
            try:
                cleanup_and_finalize_compile_session_impl(
                    session=session,
                    interrupted_status="failed",
                    error="Issue #433 zero-provider gate interrupted",
                )
                _require_zero_managed_resources()
            except Exception:
                pass


def run(manifest: dict[str, Any]) -> dict[str, Any]:
    preflight_result = preflight(manifest, require_create_once=True)
    root = REPO_ROOT / manifest["evidence_root"]
    root.mkdir(parents=True, exist_ok=False)
    marker_path = root / "attempt.json"
    _write_once_json(
        marker_path,
        {
            "identity": IDENTITY,
            "issue": TRACKING_ISSUE,
            "status": "started",
            "release_revision": preflight_result["release_revision"],
            "manifest_sha256": preflight_result["manifest_sha256"],
            "credential_reads": 0,
            "provider_requests": 0,
            "started_at": _now(),
            "completed_at": None,
            "error_class": None,
        },
    )
    result: dict[str, Any]
    try:
        result = asyncio.run(_execute_gate(manifest, preflight_result, root))
        result["qualification"] = _qualification(result, manifest)
        _write_once_json(root / "result.json", result)
        marker = _load_json(marker_path)
        marker.update(
            status="passed" if result["qualification"]["passed"] else "failed",
            completed_at=_now(),
        )
        _atomic_json(marker_path, marker)
    except BaseException as exc:
        result = {
            "identity": IDENTITY,
            "release_revision": preflight_result["release_revision"],
            "manifest_sha256": preflight_result["manifest_sha256"],
            "credential_reads": 0,
            "provider_requests": 0,
            "error_class": type(exc).__name__,
            "completed_at": _now(),
            "qualification": {
                "gates": {},
                "passed": False,
                "decision": manifest["qualification"]["fail_decision"],
            },
        }
        if not (root / "result.json").exists():
            _write_once_json(root / "result.json", result)
        marker = _load_json(marker_path)
        marker.update(
            status="failed",
            completed_at=_now(),
            error_class=type(exc).__name__,
        )
        _atomic_json(marker_path, marker)
    finally:
        _write_once_json(root / "inventory.json", _inventory(root))
    write_report(manifest, root)
    return result


def audit(manifest: dict[str, Any]) -> dict[str, Any]:
    validate_manifest(manifest)
    root = REPO_ROOT / manifest["evidence_root"]
    marker = _load_json(root / "attempt.json")
    result = _load_json(root / "result.json")
    inventory = _load_json(root / "inventory.json")
    files = inventory.get("files")
    if not isinstance(files, list) or inventory.get("canonical_sha256") != _canonical_sha256(files):
        raise QualificationError("evidence inventory canonical hash 无效")
    for item in files:
        path = root / item["path"]
        if not path.is_file() or path.stat().st_size != item["size"] or _file_sha256(path) != item["sha256"]:
            raise QualificationError(f"evidence 文件漂移: {item['path']}")
    if marker.get("status") not in {"passed", "failed"}:
        raise QualificationError("attempt 尚未封口")
    if marker.get("credential_reads") != 0 or marker.get("provider_requests") != 0:
        raise QualificationError("零 Provider 边界漂移")
    if result.get("error_class") is None:
        recomputed = _qualification(result, manifest)
        if result.get("qualification") != recomputed:
            raise QualificationError("资格决定无法复算")
    else:
        recomputed = result["qualification"]
    if (marker.get("status") == "passed") != (recomputed.get("passed") is True):
        raise QualificationError("marker/result 状态不一致")
    return {
        "valid": True,
        "identity": IDENTITY,
        "status": marker["status"],
        "decision": recomputed["decision"],
        "passed": recomputed["passed"],
        "inventory_file_count": inventory["file_count"],
        "inventory_total_bytes": inventory["total_bytes"],
        "inventory_canonical_sha256": inventory["canonical_sha256"],
        "credential_reads": 0,
        "provider_requests": 0,
    }


def _write_if_equal_or_absent(path: Path, content: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise QualificationError(f"报告已存在且内容漂移: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def write_report(manifest: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    root = root or REPO_ROOT / manifest["evidence_root"]
    audited = audit(manifest)
    result = _load_json(root / "result.json")
    report = {
        "schema_version": "1.0.0",
        "identity": IDENTITY,
        "status": audited["status"],
        "decision": audited["decision"],
        "passed": audited["passed"],
        "release_revision": result["release_revision"],
        "manifest_sha256": result["manifest_sha256"],
        "evidence_inventory_canonical_sha256": audited["inventory_canonical_sha256"],
        "provider_requests": 0,
        "credential_reads": 0,
        "checkpoint_state_id": result.get("checkpoint_state_id"),
        "strict_success": result.get("strict_success"),
        "layers": result.get("layers", []),
        "usage": result.get("usage", {}),
        "event_summary": result.get("event_summary", {}),
        "qualification": result["qualification"],
        "interpretation": {
            "engineering_gate_only": True,
            "harness_treatment_effect": False,
            "model_capability_claim": False,
            "provider_cost_claim": False,
        },
    }
    json_content = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    event_summary = report["event_summary"]
    usage = report["usage"]
    markdown = (
        f"# `{IDENTITY}` 结果\n\n"
        f"- 状态：`{report['status']}`；\n"
        f"- 决定：`{report['decision']}`；\n"
        f"- 严格成功：`{report['strict_success']}`；\n"
        f"- Provider 请求 / credential 读取：`0 / 0`；\n"
        f"- progress snapshot / 有效上下文裁剪 / ready guard 拒绝："
        f"`{event_summary.get('progress_snapshot_count', 0)} / "
        f"{event_summary.get('effective_compaction_count', 0)} / "
        f"{event_summary.get('ready_guard_rejections', 0)}`；\n"
        f"- 本地脚本模型请求 / 工具调用 / 实际命令："
        f"`{usage.get('model_requests', 0)} / {usage.get('tool_calls', 0)} / "
        f"{usage.get('commands', 0)}`。\n\n"
        "## 结论边界\n\n"
        "该结果只证明 Runtime v4 的进展快照、上下文裁剪、候选就绪门禁、"
        "严格提交和 clean replay 在真实 Docker checkpoint 上闭合。"
        "它不估计 H1 相对 H0 的模型成功率、成本或动态预算效果。\n"
    )
    _write_if_equal_or_absent(REPORT_JSON_PATH, json_content)
    _write_if_equal_or_absent(REPORT_MD_PATH, markdown)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "plan", "run", "audit", "report"))
    arguments = parser.parse_args()
    manifest = _manifest()
    try:
        if arguments.command == "validate":
            result = validate_manifest(manifest)
            output: Any = {
                "valid": True,
                "identity": result["identity"],
                "manifest_sha256": _canonical_sha256(result),
            }
        elif arguments.command == "plan":
            output = plan(manifest)
        elif arguments.command == "run":
            output = run(manifest)
        elif arguments.command == "audit":
            output = audit(manifest)
        else:
            output = write_report(manifest)
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
        if arguments.command == "run":
            return 0 if output.get("qualification", {}).get("passed") else 1
        return 0
    except QualificationError as exc:
        print(
            json.dumps(
                {"valid": False, "error_class": type(exc).__name__, "message": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
