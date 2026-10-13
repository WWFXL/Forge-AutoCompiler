#!/usr/bin/env python3
"""Issue #449：submit 拒绝后的有界恢复零 Provider 工程门禁。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
if str(HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT))

from langchain_core.callbacks import CallbackManagerForLLMRun  # noqa: E402
from langchain_core.language_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from langchain_core.runnables import Runnable  # noqa: E402
from langchain_core.tools import BaseTool  # noqa: E402
from pydantic import Field  # noqa: E402

from deerflow.compile import agent_workflow_runtime_v5 as runtime_v5  # noqa: E402
from deerflow.compile import operations  # noqa: E402
from deerflow.compile.agent_workflow_runtime import AgentWorkflowBudgetTracker  # noqa: E402
from deerflow.compile.agent_workflow_runtime_v6 import run_agent_workflow_node_v6  # noqa: E402
from deerflow.compile.agent_workflow_schemas import (  # noqa: E402
    AgentBuildNodeInput,
    AgentWorkflowBudget,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowTargetContract,
)
from deerflow.compile.docker_runtime import CompileDockerRuntime  # noqa: E402
from deerflow.compile.external_evaluator import FunctionalOracleSpec  # noqa: E402
from deerflow.compile.manager import CompileSessionManager  # noqa: E402
from deerflow.compile.operations import CompileOperationsServices  # noqa: E402
from deerflow.compile.schemas import BuildCommandRecord, CompileSession, utc_now_iso  # noqa: E402
from deerflow.config.paths import Paths  # noqa: E402

IDENTITY = "cpp-progress-aware-submit-rejection-recovery-gate-v1"
TRACKING_ISSUE = 449
COMPILE_IMAGE = "autocompiler:gcc13"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests" / f"{IDENTITY}.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-progress-aware-submit-rejection-recovery-gate-v1.schema.json"
PREREGISTRATION_PATH = REPO_ROOT / "benchmarks/preregistrations" / f"{IDENTITY}.md"
EVIDENCE_ROOT = REPO_ROOT / ".compile-sessions" / f"benchmark-evidence-{IDENTITY}"
REPORT_JSON = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.json"
REPORT_MD = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.md"
PARENT_EVIDENCE_ROOT = REPO_ROOT / ".compile-sessions/benchmark-evidence-cpp-progress-aware-h0-h1-h2-unseen-provider-canary-v1"
PARENT_INVENTORY_SHA256 = "e911bb1d5d40fc270ede9921bbb4781bcd75d4851bf8fe4ef1f95d02f97e6696"


class QualificationError(RuntimeError):
    """资格合同、执行或 create-once 证据无效。"""


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise QualificationError(f"JSON 顶层必须是 object: {path}")
    return value


def _write_once(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise QualificationError(f"create-once 文件已存在: {path}") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _write_once_json(path: Path, payload: Any) -> None:
    _write_once(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _git_revision() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


def _validate_schema_const(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    if "const" in schema and value != schema["const"]:
        raise QualificationError(f"schema const 不匹配: {path}")
    if schema.get("type") == "object":
        if not isinstance(value, dict):
            raise QualificationError(f"schema type 不匹配: {path}")
        for required in schema.get("required", []):
            if required not in value:
                raise QualificationError(f"manifest 缺少字段: {path}.{required}")
        for key, child in schema.get("properties", {}).items():
            if key in value:
                _validate_schema_const(value[key], child, f"{path}.{key}")


def validate_manifest(*, require_frozen: bool) -> dict[str, Any]:
    manifest = _load_json(MANIFEST_PATH)
    schema = _load_json(SCHEMA_PATH)
    _validate_schema_const(manifest, schema)
    if manifest.get("identity") != IDENTITY or manifest.get("issue") != TRACKING_ISSUE:
        raise QualificationError("manifest identity 或 Issue 不匹配")
    for relative_path, expected in manifest["components"].items():
        if expected == "freeze-before-formal-run":
            if require_frozen:
                raise QualificationError(f"component 尚未冻结: {relative_path}")
            continue
        if _file_sha256(REPO_ROOT / relative_path) != expected:
            raise QualificationError(f"component hash 漂移: {relative_path}")
    preregistration_sha256 = manifest["preregistration"]["sha256"]
    if preregistration_sha256 == "freeze-before-formal-run":
        if require_frozen:
            raise QualificationError("预注册 hash 尚未冻结")
    elif _file_sha256(PREREGISTRATION_PATH) != preregistration_sha256:
        raise QualificationError("预注册 hash 漂移")
    if manifest.get("release_revision_policy") != "bind_current_clean_head_at_identity_creation":
        raise QualificationError("release revision 绑定策略无效")
    return manifest


def _inventory(root: Path) -> dict[str, Any]:
    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "inventory.json"):
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


def audit_parent_evidence() -> dict[str, Any]:
    recorded = _load_json(PARENT_EVIDENCE_ROOT / "inventory.json")
    if recorded.get("canonical_sha256") != PARENT_INVENTORY_SHA256:
        raise QualificationError("#447 recorded inventory canonical SHA-256 漂移")
    if _canonical_sha256(recorded.get("files")) != PARENT_INVENTORY_SHA256:
        raise QualificationError("#447 inventory 文件表 canonical SHA-256 漂移")
    for item in recorded["files"]:
        path = PARENT_EVIDENCE_ROOT / item["path"]
        if not path.is_file() or path.stat().st_size != item["size"] or _file_sha256(path) != item["sha256"]:
            raise QualificationError(f"#447 evidence 文件漂移: {item['path']}")
    return {
        "identity": "cpp-progress-aware-h0-h1-h2-unseen-provider-canary-v1",
        "file_count": recorded["file_count"],
        "total_bytes": recorded["total_bytes"],
        "inventory_canonical_sha256": recorded["canonical_sha256"],
        "valid": True,
    }


class _MemoryManager:
    def __init__(self, session: CompileSession):
        self.session = session

    def load_session(self, session_id: str, thread_id: str | None = None) -> CompileSession:
        if session_id != self.session.session_id or thread_id != self.session.thread_id:
            raise QualificationError("内存 Session identity 漂移")
        return self.session


class _MemoryLedger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def append(self, event_type: str, **payload: Any) -> None:
        self.events.append((event_type, payload))


def _guard_session(root: Path) -> CompileSession:
    artifacts = root / "artifacts/bin"
    artifacts.mkdir(parents=True)
    shutil.copy2("/bin/true", artifacts / "unit_test")
    now = utc_now_iso()
    commands = [
        BuildCommandRecord(
            stage="bash",
            command="make unit_test",
            workdir="/workspace/repo/test",
            command_id="guard-build",
            role="build",
            completed_at=now,
            exit_code=0,
        ),
        BuildCommandRecord(
            stage="bash",
            command="install -Dm755 test/unit_test /artifacts/bin/unit_test",
            workdir="/workspace/repo",
            command_id="guard-stage",
            role="artifact_stage",
            completed_at=now,
            exit_code=0,
        ),
    ]
    return CompileSession(
        session_id="session-v5-deadlock",
        thread_id="thread-v5-deadlock",
        run_id="run-v5-deadlock",
        repo_url="https://example.invalid/mjson-fixture.git",
        branch="main",
        commit_sha="a" * 40,
        image=COMPILE_IMAGE,
        image_id=f"sha256:{'b' * 64}",
        status="inspected",
        selected_build_system="make",
        leadagent_repo_dir=str(root / "workspace/repo"),
        leadagent_artifacts_dir=str(root / "artifacts"),
        leadagent_logs_dir=str(root / "logs"),
        leadagent_repro_dir=str(root / "repro"),
        metadata_path=str(root / "session.json"),
        commands=commands,
    )


def _guard_input(session: CompileSession) -> AgentBuildNodeInput:
    return AgentBuildNodeInput(
        task_id="v5-deadlock-reproduction",
        attempt_id="attempt-v5-deadlock",
        session_id=session.session_id,
        repository_url=session.repo_url,
        commit_sha=session.commit_sha or "",
        source_snapshot_sha256="c" * 64,
        build_system_candidates=("make",),
        target_contract=AgentWorkflowTargetContract(
            target_id="unit-test",
            artifact_types=("executable",),
            artifact_path_patterns=("bin/unit_test",),
            functional_oracle_ref="oracle-unit-test-v1",
        ),
        operation_policy_ref="submit-rejection-recovery-gate-v1",
        environment=AgentWorkflowEnvironmentIdentity(
            image_id=session.image_id or "",
            parallel_jobs=session.parallel_jobs,
            network_policy="none",
        ),
        budget=AgentWorkflowBudget(
            max_model_requests=4,
            max_recorded_tokens=100,
            max_agent_steps=12,
            max_tool_calls=8,
            max_commands=4,
            node_timeout_seconds=60,
            command_timeout_seconds=30,
            evaluator_timeout_seconds=60,
            replay_timeout_seconds=60,
            cleanup_timeout_seconds=30,
        ),
        experiment_identity=AgentWorkflowExperimentIdentity(
            manifest_sha256="d" * 64,
            protocol_sha256="e" * 64,
            runner_sha256="f" * 64,
        ),
        initial_observation={"zero_provider": True},
    )


def reproduce_v5_deadlock() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="forge-v5-deadlock-") as temporary:
        session = _guard_session(Path(temporary))
        manager = _MemoryManager(session)
        ledger = _MemoryLedger()
        middleware = runtime_v5.ReplayClosureHarnessMiddleware(
            node_input=_guard_input(session),
            session=session,
            manager=manager,  # type: ignore[arg-type]
            tracker=AgentWorkflowBudgetTracker(_guard_input(session).budget),
            ledger=ledger,  # type: ignore[arg-type]
            started_monotonic=time.monotonic(),
            closure_store=runtime_v5.ReplayClosureStateStore(),
        )
        before = middleware.snapshot()
        submit = SimpleNamespace(tool_call={"name": "submit_candidate_v1", "args": {}, "id": "deadlock-submit"})

        def rejected(_request: Any) -> ToolMessage:
            session.commands.append(
                BuildCommandRecord(
                    stage="bash",
                    command="/artifacts/bin/unit_test",
                    workdir="/workspace/repo",
                    command_id="trusted-smoke",
                    role="smoke",
                    completed_at=utc_now_iso(),
                    exit_code=0,
                )
            )
            return ToolMessage(
                content='{"accepted":false,"terminal_for_agent":false,"rejection_codes":["recipe_execution_failed"]}',
                tool_call_id="deadlock-submit",
                name="submit_candidate_v1",
                status="error",
            )

        middleware._wrap_tool_result(submit, rejected)
        after = middleware.snapshot()
        repair = SimpleNamespace(
            tool_call={
                "name": "run_container_bash",
                "args": {"command_role": "build"},
                "id": "deadlock-repair",
            }
        )
        reason = middleware._guard_reason(repair, after)
        return {
            "passed": before.command_count + 1 == after.command_count and reason == "candidate_ready_requires_submit",
            "pre_submit_frontier_sha256": middleware._frontier(before),
            "post_submit_frontier_sha256": middleware._frontier(after),
            "command_count_before": before.command_count,
            "command_count_after": after.command_count,
            "repair_guard_reason": reason,
            "provider_requests": 0,
            "credential_reads": 0,
        }


class RecoveryScriptedModel(BaseChatModel):
    calls: int = 0
    initial_build_id: str
    initial_stage_id: str
    snapshots: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "submit-rejection-recovery-scripted-zero-provider"

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
    def _snapshot(messages: list[BaseMessage]) -> dict[str, Any]:
        for message in reversed(messages):
            if not isinstance(message, HumanMessage) or not isinstance(message.content, str):
                continue
            start = message.content.find("<authoritative_compile_progress>\n")
            end = message.content.find("\n</authoritative_compile_progress>")
            if start >= 0 and end > start:
                start += len("<authoritative_compile_progress>\n")
                value = json.loads(message.content[start:end])
                if isinstance(value, dict):
                    return value
        raise QualificationError("scripted model 未收到权威 progress snapshot")

    @staticmethod
    def _tool_call(name: str, args: dict[str, Any], call_id: str) -> AIMessage:
        return AIMessage(
            content="",
            tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
            usage_metadata={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        )

    def _submit_args(self, *, build_id: str, stage_id: str, candidate_id: str) -> dict[str, Any]:
        return {
            "candidate_id": candidate_id,
            "build_system": "make",
            "supporting_command_ids": [build_id],
            "artifact_paths": ["bin/unit_test"],
            "target_mapping": {"unit-test": "bin/unit_test"},
            "recipe_command_ids": [build_id, stage_id],
            "agent_summary": "Issue #449 zero-provider recovery fixture",
            "known_limitations": [],
        }

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        snapshot = self._snapshot(messages)
        self.snapshots.append(snapshot)
        if self.calls == 0:
            message = self._tool_call(
                "submit_candidate_v1",
                self._submit_args(
                    build_id=self.initial_build_id,
                    stage_id=self.initial_stage_id,
                    candidate_id="candidate-dirty-workspace",
                ),
                "submit-dirty-workspace",
            )
        elif self.calls == 1:
            message = self._tool_call(
                "run_container_bash",
                {
                    "command": "make -C test test",
                    "command_role": "build",
                    "timeout_seconds": 120,
                    "workdir": "/workspace/repo",
                },
                "repair-build",
            )
        elif self.calls == 2:
            message = self._tool_call(
                "run_container_bash",
                {
                    "command": "install -Dm755 test/unit_test /artifacts/bin/unit_test",
                    "command_role": "artifact_stage",
                    "timeout_seconds": 120,
                    "workdir": "/workspace/repo",
                },
                "repair-stage",
            )
        elif self.calls == 3:
            message = self._tool_call(
                "submit_candidate_v1",
                self._submit_args(
                    build_id=snapshot["successful_build_command_ids"][-1],
                    stage_id=snapshot["successful_artifact_stage_command_ids"][-1],
                    candidate_id="candidate-repaired-recipe",
                ),
                "submit-repaired-recipe",
            )
        else:
            message = AIMessage(
                content="unexpected extra model call",
                usage_metadata={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            )
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=message)])


def _write_fixture(source: Path) -> None:
    (source / "src").mkdir(parents=True)
    (source / "test").mkdir(parents=True)
    (source / "Makefile").write_text(
        ".PHONY: all docker\nall: test/unit_test docker\ntest/unit_test: test/unit_test.c src/mjson.c\n\t$(CC) -O2 -o $@ $^\ndocker:\n\t@echo 'docker target intentionally unavailable' >&2\n\t@false\n",
        encoding="utf-8",
    )
    (source / "test/Makefile").write_text(
        ".PHONY: test\ntest:\n\t$(CC) -O2 -o unit_test unit_test.c ../src/mjson.c\n",
        encoding="utf-8",
    )
    (source / "test/unit_test.c").write_text(
        '#include <stdio.h>\nint mjson_value(void);\nint main(void) { printf("%d\\n", mjson_value()); return mjson_value() == 7 ? 0 : 1; }\n',
        encoding="utf-8",
    )
    (source / "src/mjson.c").write_text("int mjson_value(void) { return 7; }\n", encoding="utf-8")


def _create_source_archive(source: Path, archive: Path) -> str:
    with tarfile.open(archive, "w") as output:
        for path in sorted(source.rglob("*")):
            info = output.gettarinfo(str(path), arcname=path.relative_to(source).as_posix())
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            info.mtime = 0
            if path.is_file():
                with path.open("rb") as stream:
                    output.addfile(info, stream)
            else:
                output.addfile(info)
    return _file_sha256(archive)


def _record_command(
    *,
    manager: CompileSessionManager,
    runtime: CompileDockerRuntime,
    session: CompileSession,
    command_id: str,
    command: str,
    role: str,
    workdir: str,
) -> BuildCommandRecord:
    started = utc_now_iso()
    result = runtime.exec(
        session,
        command,
        workdir=workdir,
        timeout_seconds=120,
        log_path=str(Path(session.leadagent_logs_dir) / f"{command_id}.log"),
        strict_shell=True,
    )
    record = BuildCommandRecord(
        stage="bash",
        command=command,
        workdir=workdir,
        command_id=command_id,
        role=role,
        timeout_seconds=120,
        timed_out=result.exit_code == 124,
        started_at=started,
        completed_at=utc_now_iso(),
        exit_code=result.exit_code,
        log_path=manager.relative_path(session, result.log_path or ""),
    )
    manager.record_command(session, record)
    return record


def _node_input(
    *,
    session: CompileSession,
    manifest: dict[str, Any],
    source_sha256: str,
) -> AgentBuildNodeInput:
    return AgentBuildNodeInput(
        task_id="make-dirty-workspace-recovery",
        attempt_id="attempt-submit-rejection-recovery",
        session_id=session.session_id,
        repository_url=session.repo_url,
        commit_sha=session.commit_sha or "",
        source_snapshot_sha256=source_sha256,
        build_system_candidates=("make",),
        target_contract=AgentWorkflowTargetContract(
            target_id="unit-test",
            artifact_types=("executable",),
            artifact_path_patterns=("bin/unit_test",),
            functional_oracle_ref="oracle-unit-test-v1",
        ),
        operation_policy_ref="submit-rejection-recovery-gate-v1",
        environment=AgentWorkflowEnvironmentIdentity(
            image_id=session.image_id or "",
            parallel_jobs=session.parallel_jobs,
            network_policy="none",
        ),
        budget=AgentWorkflowBudget(
            max_model_requests=6,
            max_recorded_tokens=1,
            max_agent_steps=20,
            max_tool_calls=8,
            max_commands=4,
            node_timeout_seconds=600,
            command_timeout_seconds=120,
            evaluator_timeout_seconds=120,
            replay_timeout_seconds=180,
            cleanup_timeout_seconds=60,
            max_recorded_tokens_per_response=1,
        ),
        experiment_identity=AgentWorkflowExperimentIdentity(
            manifest_sha256=_canonical_sha256(manifest),
            protocol_sha256=_file_sha256(PREREGISTRATION_PATH),
            runner_sha256=_file_sha256(SCRIPT_PATH),
        ),
        initial_observation={
            "failure": "dirty_workspace_up_to_date_build",
            "required_candidate_artifacts": ("bin/unit_test",),
            "zero_provider": True,
        },
    )


def _managed_containers(thread_id: str) -> list[str]:
    result = subprocess.run(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            "label=deerflow.compile.managed=true",
            "--filter",
            f"label=deerflow.compile.thread_id={thread_id}",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return [line for line in result.stdout.splitlines() if line]


def _agent_events(session: CompileSession) -> list[dict[str, Any]]:
    path = Path(session.metadata_path).parent / "agent-workflow/attempt-submit-rejection-recovery/events.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def run_docker_case(*, workspace_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    paths = Paths(workspace_root=workspace_root, host_workspace_root=str(workspace_root))
    manager = CompileSessionManager(paths=paths, default_image=COMPILE_IMAGE, parallel_jobs=2)
    runtime = CompileDockerRuntime(manager=manager)
    previous_services = operations._services
    operations._services = CompileOperationsServices(manager=manager, runtime=runtime)
    thread_id = f"issue-449-{uuid.uuid4().hex[:10]}"
    session = manager.create_session(
        thread_id=thread_id,
        repo_url="https://example.invalid/mjson-dirty-workspace-fixture.git",
        image=COMPILE_IMAGE,
        run_id=f"qualification-{uuid.uuid4().hex}",
    )
    cleanup_succeeded = False
    started = time.monotonic()
    try:
        source = workspace_root / "fixture-source"
        _write_fixture(source)
        archive = Path(session.leadagent_repro_dir) / "source.tar"
        source_sha256 = _create_source_archive(source, archive)
        shutil.copytree(source, Path(session.leadagent_repo_dir))
        runtime.create_container(session)
        session.commit_sha = hashlib.sha1(f"{IDENTITY}:make-dirty-workspace".encode()).hexdigest()
        session.selected_build_system = "make"
        session.executed_build_system = "make"
        session.replay_source_archive_sha256 = source_sha256
        session.status = "inspected"
        manager.save_session(session)

        dirty = _record_command(
            manager=manager,
            runtime=runtime,
            session=session,
            command_id="initial-top-level-make",
            command="make",
            role="build",
            workdir="/workspace/repo",
        )
        if dirty.exit_code == 0 or not Path(session.leadagent_repo_dir, "test/unit_test").is_file():
            raise QualificationError("脏工作区陷阱未形成：顶层 make 必须失败但留下 unit_test")
        up_to_date = _record_command(
            manager=manager,
            runtime=runtime,
            session=session,
            command_id="initial-up-to-date-build",
            command="make unit_test",
            role="build",
            workdir="/workspace/repo/test",
        )
        stage = _record_command(
            manager=manager,
            runtime=runtime,
            session=session,
            command_id="initial-artifact-stage",
            command="install -Dm755 test/unit_test /artifacts/bin/unit_test",
            role="artifact_stage",
            workdir="/workspace/repo",
        )
        if up_to_date.exit_code != 0 or stage.exit_code != 0:
            raise QualificationError("脏工作区初始 build/stage 未成功")
        current = manager.load_session(session.session_id, session.thread_id)
        current.post_build_supporting_command_id = up_to_date.command_id
        current.post_build_started_at = utc_now_iso()
        current.post_build_commands_remaining = 1
        manager.save_session(current)
        session.__dict__.update(current.__dict__)

        model = RecoveryScriptedModel(
            initial_build_id=up_to_date.command_id,
            initial_stage_id=stage.command_id,
        )
        result = asyncio.run(
            run_agent_workflow_node_v6(
                node_input=_node_input(session=session, manifest=manifest, source_sha256=source_sha256),
                session=session,
                manager=manager,
                model=model,
                oracle_registry={
                    "oracle-unit-test-v1": FunctionalOracleSpec(
                        oracle_ref="oracle-unit-test-v1",
                        argv=("/artifacts/bin/unit_test",),
                        timeout_seconds=30,
                    )
                },
            )
        )
        events = _agent_events(session)
        closure_events = [event for event in events if event["event_type"] == "candidate.replay_closure_completed"]
        rejection_events = [event for event in events if event["event_type"] == "candidate.submit_rejected"]
        recovery_events = [event for event in events if event["event_type"].startswith("harness.repair_")]
        post_release = [event for event in events if event["event_type"] == "harness.post_build_released"]
        current = manager.load_session(session.session_id, session.thread_id)
        repair_builds = [command for command in current.commands if command.command == "make -C test test"]
        repair_stages = [command for command in current.commands if command.command == "install -Dm755 test/unit_test /artifacts/bin/unit_test" and command.command_id != stage.command_id]
        ownership = runtime.exec(
            current,
            f"chown -R {os.getuid()}:{os.getgid()} /workspace /artifacts /logs",
            workdir="/",
            timeout_seconds=30,
        )
        if ownership.exit_code != 0:
            raise QualificationError("无法恢复 qualification 目录所有权")
        cleanup = runtime.stop_and_remove_container(current)
        cleanup_succeeded = cleanup.succeeded and cleanup.removed
        managed_after = _managed_containers(thread_id)
        checks = {
            "node_submitted": result.node_status == "submitted" and result.candidate_submitted,
            "exact_model_requests": result.usage.model_requests == 4 and model.calls == 4,
            "zero_recorded_tokens": result.usage.recorded_tokens == 0,
            "first_closure_rejected_recipe": len(closure_events) == 2 and closure_events[0]["payload"]["passed"] is False and closure_events[0]["payload"]["classification"] == "recipe_execution_failed",
            "second_closure_passed": len(closure_events) == 2 and closure_events[1]["payload"]["passed"] is True,
            "one_submit_rejection": len(rejection_events) == 1 and rejection_events[0]["payload"]["rejection_codes"] == ["recipe_execution_failed"],
            "post_build_released_once": len(post_release) == 1,
            "one_repair_build": len(repair_builds) == 1 and repair_builds[0].exit_code == 0,
            "one_repair_stage": len(repair_stages) == 1 and repair_stages[0].exit_code == 0,
            "repair_window_bounded": sum(event["event_type"] == "harness.repair_permission_consumed" for event in recovery_events) == 2,
            "session_remains_active": current.status == "inspected" and current.finalized_at is None,
            "no_formal_replay_attempt": not current.replay_attempts,
            "cleanup_succeeded": cleanup_succeeded and not managed_after,
        }
        return {
            "case_id": "make-dirty-workspace-recovery",
            "passed": all(checks.values()),
            "checks": checks,
            "node_result": json.loads(result.canonical_json()),
            "closure_results": [event["payload"] for event in closure_events],
            "repair_events": [event["payload"] | {"event_type": event["event_type"]} for event in recovery_events],
            "post_build_release_events": len(post_release),
            "command_count": len(current.commands),
            "model_snapshots": model.snapshots,
            "managed_containers_after_cleanup": managed_after,
            "provider_requests": 0,
            "credential_reads": 0,
            "jev_requests": 0,
            "formal_effect_attempts": 0,
            "duration_seconds": round(time.monotonic() - started, 6),
        }
    finally:
        if not cleanup_succeeded:
            try:
                current = manager.load_session(session.session_id, session.thread_id)
                if current.container_id:
                    runtime.exec(
                        current,
                        f"chown -R {os.getuid()}:{os.getgid()} /workspace /artifacts /logs",
                        workdir="/",
                        timeout_seconds=30,
                    )
                runtime.stop_and_remove_container(current)
            except Exception:
                pass
        operations._services = previous_services


def run_engineering_check() -> dict[str, Any]:
    manifest = validate_manifest(require_frozen=False)
    parent = audit_parent_evidence()
    old_deadlock = reproduce_v5_deadlock()
    with tempfile.TemporaryDirectory(prefix="forge-submit-recovery-") as temporary:
        docker_case = run_docker_case(workspace_root=Path(temporary), manifest=manifest)
    return {
        "identity": IDENTITY,
        "mode": "engineering-check",
        "passed": parent["valid"] and old_deadlock["passed"] and docker_case["passed"],
        "parent_evidence": parent,
        "v5_deadlock_reproduction": old_deadlock,
        "docker_case": docker_case,
    }


def _tracked_worktree_clean() -> bool:
    return not subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout


def run_formal() -> dict[str, Any]:
    manifest = validate_manifest(require_frozen=True)
    if not _tracked_worktree_clean():
        raise QualificationError("formal qualification 要求 tracked worktree 干净")
    if EVIDENCE_ROOT.exists():
        raise QualificationError(f"create-once evidence root 已存在: {EVIDENCE_ROOT}")
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=False)
    identity = {
        "identity": IDENTITY,
        "tracking_issue": TRACKING_ISSUE,
        "release_revision": _git_revision(),
        "manifest_canonical_sha256": _canonical_sha256(manifest),
        "manifest_file_sha256": _file_sha256(MANIFEST_PATH),
        "preregistration_sha256": _file_sha256(PREREGISTRATION_PATH),
        "runner_sha256": _file_sha256(SCRIPT_PATH),
        "credential_reads_authorized": 0,
        "provider_requests_authorized": 0,
        "jev_requests_authorized": 0,
        "formal_effect_attempts_authorized": 0,
        "created_at": utc_now_iso(),
    }
    _write_once_json(EVIDENCE_ROOT / "identity.json", identity)
    parent = audit_parent_evidence()
    _write_once_json(EVIDENCE_ROOT / "parent-audit.json", parent)
    deadlock = reproduce_v5_deadlock()
    _write_once_json(EVIDENCE_ROOT / "q0-v5-deadlock.json", deadlock)
    docker_case = run_docker_case(workspace_root=EVIDENCE_ROOT / "runtime", manifest=manifest)
    _write_once_json(EVIDENCE_ROOT / "q1-docker-recovery.json", docker_case)
    shutil.rmtree(EVIDENCE_ROOT / "runtime", ignore_errors=True)
    gates = {
        "parent_evidence_unchanged": parent["valid"],
        "v5_deadlock_reproduced": deadlock["passed"],
        "docker_recovery_passed": docker_case["passed"],
        "first_closure_recipe_execution_failed": docker_case["checks"]["first_closure_rejected_recipe"],
        "second_closure_passed": docker_case["checks"]["second_closure_passed"],
        "repair_window_bounded": docker_case["checks"]["repair_window_bounded"],
        "strict_candidate_submitted": docker_case["checks"]["node_submitted"],
        "session_and_replay_boundary_preserved": docker_case["checks"]["session_remains_active"] and docker_case["checks"]["no_formal_replay_attempt"],
        "cleanup_closed": docker_case["checks"]["cleanup_succeeded"],
        "zero_provider_boundary": docker_case["provider_requests"] == docker_case["credential_reads"] == docker_case["jev_requests"] == docker_case["formal_effect_attempts"] == 0,
    }
    passed = all(gates.values())
    decision = "proceed_to_unseen_three_arm_formal_comparison_design" if passed else "stop_before_formal_comparison"
    result = {
        "identity": IDENTITY,
        "release_revision": identity["release_revision"],
        "passed": passed,
        "decision": decision,
        "gates": gates,
        "v5_deadlock_reproduction": deadlock,
        "docker_case_summary": {
            "case_id": docker_case["case_id"],
            "passed": docker_case["passed"],
            "checks": docker_case["checks"],
            "closure_classifications": [item["classification"] for item in docker_case["closure_results"]],
            "model_requests": docker_case["node_result"]["usage"]["model_requests"],
            "recorded_tokens": docker_case["node_result"]["usage"]["recorded_tokens"],
            "command_count": docker_case["command_count"],
            "duration_seconds": docker_case["duration_seconds"],
        },
    }
    _write_once_json(EVIDENCE_ROOT / "result.json", result)
    _write_once_json(EVIDENCE_ROOT / "marker.json", {"identity": IDENTITY, "passed": passed, "decision": decision})
    inventory = _inventory(EVIDENCE_ROOT)
    _write_once_json(EVIDENCE_ROOT / "inventory.json", inventory)
    return {**result, "inventory": inventory}


def audit_evidence() -> dict[str, Any]:
    if not EVIDENCE_ROOT.is_dir():
        raise QualificationError("evidence root 不存在")
    recorded = _load_json(EVIDENCE_ROOT / "inventory.json")
    observed = _inventory(EVIDENCE_ROOT)
    parent = audit_parent_evidence()
    result = _load_json(EVIDENCE_ROOT / "result.json")
    managed = subprocess.run(
        ["docker", "ps", "-aq", "--filter", "label=deerflow.compile.managed=true"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.splitlines()
    valid = recorded == observed and result.get("passed") is True and parent["valid"] and not managed
    return {
        "identity": IDENTITY,
        "valid": valid,
        "inventory": recorded,
        "parent_evidence": parent,
        "zero_managed_resources": not managed,
    }


def write_report() -> dict[str, Any]:
    audit = audit_evidence()
    result = _load_json(EVIDENCE_ROOT / "result.json")
    report = {
        **result,
        "inventory_canonical_sha256": audit["inventory"]["canonical_sha256"],
        "inventory_file_count": audit["inventory"]["file_count"],
        "inventory_total_bytes": audit["inventory"]["total_bytes"],
        "audit_valid": audit["valid"],
        "zero_managed_resources": audit["zero_managed_resources"],
        "interpretation_boundary": "zero-provider engineering recovery gate; no treatment effect",
    }
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown = f"""# Submit 拒绝恢复零 Provider 工程门禁结果

- Identity：`{IDENTITY}`
- 结论：`{report["decision"]}`
- 全部门槛：`{report["passed"]}`
- Evidence audit：`{report["audit_valid"]}`
- Inventory canonical SHA-256：`{report["inventory_canonical_sha256"]}`

## 结果

- Runtime v5 旧语义复现：submit 前后 command count 从 `{report["v5_deadlock_reproduction"]["command_count_before"]}` 变为 `{report["v5_deadlock_reproduction"]["command_count_after"]}`，repair guard 返回 `candidate_ready_requires_submit`。
- Runtime v6 Docker 案例：首次 closure 为 `recipe_execution_failed`，修复 build 与重新 stage 各执行一次，第二次 closure 为 `passed`，candidate 成功冻结。
- 脚本化 Agent 共 `{report["docker_case_summary"]["model_requests"]}` 次请求、`{report["docker_case_summary"]["recorded_tokens"]}` recorded tokens；credential、Provider、Jev 和 formal effect attempt 均为 0。
- Session 保持活动，正式 replay attempt 为 0；qualification 结束后受管资源为 0。

该结果只证明已观察到的 submit-rejection 恢复死锁在 Runtime v6 中得到有界修复，并保持 CandidateVerifier、functional oracle 和 replay closure。它不估计 H2 对严格成功率、成本、token、自然失败或未见项目总体的效果。
"""
    REPORT_MD.write_text(markdown, encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "engineering-check", "run", "audit", "report"))
    args = parser.parse_args()
    if args.command == "validate":
        result: dict[str, Any] = {
            "identity": IDENTITY,
            "valid": bool(validate_manifest(require_frozen=False)),
        }
    elif args.command == "engineering-check":
        result = run_engineering_check()
    elif args.command == "run":
        result = run_formal()
    elif args.command == "audit":
        result = audit_evidence()
    else:
        result = write_report()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("passed", result.get("valid", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
