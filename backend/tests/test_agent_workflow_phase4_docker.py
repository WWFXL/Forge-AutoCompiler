"""单 Agent Workflow Node Phase 4 的 opt-in 零 Provider Docker 门禁。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import socket
import subprocess
import time
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import Field

from deerflow.compile import operations
from deerflow.compile.agent_workflow_runtime import run_agent_workflow_node_v1
from deerflow.compile.agent_workflow_schemas import (
    AgentBuildNodeInput,
    AgentBuildNodeResult,
    AgentWorkflowBudget,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowTargetContract,
)
from deerflow.compile.docker_runtime import CompileDockerRuntime, ContainerCleanupResult
from deerflow.compile.external_evaluator import (
    ExternalEvaluationResult,
    ExternalEvaluatorBackendResult,
    ForgeCompileEvaluationBackend,
    FunctionalOracleSpec,
    run_external_evaluator_v1,
)
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.operations import (
    CompileOperationsServices,
    cleanup_and_finalize_compile_session_impl,
    clone_repository_impl,
    inspect_build_system_impl,
    prepare_compile_session_impl,
)
from deerflow.compile.schemas import CompileSession
from deerflow.config.paths import Paths
from deerflow.models import factory as model_factory

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPILE_IMAGE = "autocompiler:gcc13"
DOCKER_ENABLED = os.getenv("FORGE_RUN_AGENT_WORKFLOW_PHASE4_DOCKER") == "1"
SHA256_A = "a" * 64
SHA256_B = "b" * 64
SHA256_C = "c" * 64
COMMAND_ID_PATTERN = re.compile(r"^command_id=(command_[0-9a-f]+)$", re.MULTILINE)
COMMAND_ROLE_PATTERN = re.compile(r"^command_role=([a-z_]+)$", re.MULTILINE)

pytestmark = pytest.mark.skipif(
    not DOCKER_ENABLED,
    reason="set FORGE_RUN_AGENT_WORKFLOW_PHASE4_DOCKER=1 to run the Phase 4 Docker gate",
)


@dataclass(frozen=True)
class FixtureCase:
    case_id: str
    build_system: str
    files: Mapping[str, str]
    commands: tuple[tuple[str, str], ...]
    artifact_path: str
    marker: str


COMMON_SOURCE = """#include <stdio.h>
int main(void) {
    puts("phase4-ok");
    return 0;
}
"""

CASES = (
    FixtureCase(
        case_id="cmake",
        build_system="cmake",
        files={
            "CMakeLists.txt": "cmake_minimum_required(VERSION 3.16)\nproject(phase4 C)\nadd_executable(phase4 main.c)\n",
            "main.c": COMMON_SOURCE,
        },
        commands=(
            ("configure", "cmake -S . -B build"),
            ("build", "cmake --build build --parallel"),
            ("artifact_stage", "cp build/phase4 /artifacts/phase4-cmake"),
        ),
        artifact_path="phase4-cmake",
        marker="CMakeLists.txt",
    ),
    FixtureCase(
        case_id="make",
        build_system="make",
        files={
            "Makefile": "CC ?= cc\nCFLAGS ?= -O2\nphase4: main.c\n\t$(CC) $(CFLAGS) -o $@ $<\n",
            "main.c": COMMON_SOURCE,
        },
        commands=(
            ("build", "make"),
            ("artifact_stage", "cp phase4 /artifacts/phase4-make"),
        ),
        artifact_path="phase4-make",
        marker="Makefile",
    ),
    FixtureCase(
        case_id="autotools",
        build_system="autotools",
        files={
            "configure.ac": "AC_INIT([phase4], [1.0])\nAM_INIT_AUTOMAKE([foreign])\nAC_PROG_CC\nAC_CONFIG_FILES([Makefile])\nAC_OUTPUT\n",
            "Makefile.am": "bin_PROGRAMS = phase4\nphase4_SOURCES = main.c\n",
            "main.c": COMMON_SOURCE,
        },
        commands=(
            ("configure", "autoreconf -fi && ./configure"),
            ("build", "make"),
            ("artifact_stage", "cp phase4 /artifacts/phase4-autotools"),
        ),
        artifact_path="phase4-autotools",
        marker="configure.ac",
    ),
)
CASE_BY_ID = {case.case_id: case for case in CASES}


class DeterministicBuildModel(BaseChatModel):
    case_id: str
    build_system: str
    commands: tuple[tuple[str, str], ...]
    artifact_path: str
    calls: int = 0
    bind_kwargs: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "phase4-deterministic-zero-provider"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable:
        del tools, tool_choice
        self.bind_kwargs.append(kwargs)
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        if self.calls < len(self.commands):
            role, command = self.commands[self.calls]
            response = _tool_call(
                "run_container_bash",
                {
                    "command": command,
                    "command_role": role,
                    "timeout_seconds": 300,
                    "workdir": "/workspace/repo",
                },
                f"{self.case_id}-command-{self.calls + 1}",
            )
        else:
            command_evidence = _command_evidence(messages)
            recipe_command_ids = [command_id for command_id, role in command_evidence if role in {"configure", "build", "artifact_stage"}]
            supporting_command_ids = [command_id for command_id, role in command_evidence if role == "build"]
            response = _tool_call(
                "submit_candidate_v1",
                {
                    "candidate_id": f"candidate-{self.case_id}",
                    "build_system": self.build_system,
                    "supporting_command_ids": supporting_command_ids,
                    "artifact_paths": [self.artifact_path],
                    "target_mapping": {f"target-{self.case_id}": self.artifact_path},
                    "recipe_command_ids": recipe_command_ids,
                    "agent_summary": "确定性 Phase 4 fixture 已生成候选。",
                    "known_limitations": [],
                },
                f"{self.case_id}-submit",
            )
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=response)])


class StaticModel(BaseChatModel):
    response: AIMessage

    @property
    def _llm_type(self) -> str:
        return "phase4-static-zero-provider"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable:
        del tools, tool_choice, kwargs
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        return ChatResult(generations=[ChatGeneration(message=self.response)])


class SlowModel(StaticModel):
    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        await asyncio.sleep(5)
        return ChatResult(generations=[ChatGeneration(message=self.response)])


class RaisingBackend:
    def evaluate(self, **kwargs: Any) -> ExternalEvaluatorBackendResult:
        del kwargs
        raise RuntimeError("phase4 evaluator fault")


def _tool_call(name: str, args: dict[str, Any], call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
        usage_metadata={"input_tokens": 8, "output_tokens": 4, "total_tokens": 12},
    )


def _command_evidence(messages: Sequence[BaseMessage]) -> list[tuple[str, str]]:
    evidence: list[tuple[str, str]] = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        content = message.content if isinstance(message.content, str) else json.dumps(message.content)
        command_id = COMMAND_ID_PATTERN.search(content)
        role = COMMAND_ROLE_PATTERN.search(content)
        if command_id is not None and role is not None:
            evidence.append((command_id.group(1), role.group(1)))
    return evidence


def _git(*args: str, cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout.strip()


def _create_fixture_repository(root: Path, case: FixtureCase) -> str:
    source = root / f"{case.case_id}-source"
    bare = root / f"{case.case_id}.git"
    source.mkdir()
    for relative_path, content in case.files.items():
        path = source / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git("init", "--quiet", cwd=source)
    _git("config", "user.name", "Forge Phase4 Gate", cwd=source)
    _git("config", "user.email", "phase4@example.invalid", cwd=source)
    _git("add", ".", cwd=source)
    _git("commit", "--quiet", "-m", f"fixture {case.case_id}", cwd=source)
    commit_sha = _git("rev-parse", "HEAD", cwd=source)
    _git("clone", "--quiet", "--bare", str(source), str(bare), cwd=root)
    _git("update-server-info", cwd=bare)
    return commit_sha


@pytest.fixture(scope="module")
def fixture_repositories(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, tuple[str, str]]]:
    root = tmp_path_factory.mktemp("phase4-fixtures")
    commits = {case.case_id: _create_fixture_repository(root, case) for case in CASES}
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    daemon = subprocess.Popen(
        [
            "git",
            "daemon",
            "--reuseaddr",
            "--export-all",
            f"--base-path={root}",
            "--listen=0.0.0.0",
            f"--port={port}",
            str(root),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 5
    while True:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            if daemon.poll() is not None or time.monotonic() >= deadline:
                daemon.terminate()
                raise RuntimeError("Phase 4 fixture git daemon failed to start")
            time.sleep(0.05)
    try:
        yield {
            case.case_id: (
                f"git://host.docker.internal:{port}/{case.case_id}.git",
                commits[case.case_id],
            )
            for case in CASES
        }
    finally:
        daemon.terminate()
        try:
            daemon.wait(timeout=5)
        except subprocess.TimeoutExpired:
            daemon.kill()
            daemon.wait(timeout=5)


@pytest.fixture(scope="module", autouse=True)
def require_phase4_docker_gate() -> Iterator[None]:
    if not DOCKER_ENABLED:
        yield
        return
    required = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "require-docker-runtime.sh")],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if required.returncode != 0:
        pytest.fail(required.stderr.strip() or required.stdout.strip())
    image = subprocess.run(
        ["docker", "image", "inspect", COMPILE_IMAGE],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if image.returncode != 0:
        pytest.fail(f"Required image {COMPILE_IMAGE!r} is unavailable")
    _assert_zero_managed_resources()
    yield
    _assert_zero_managed_resources()


@pytest.fixture(autouse=True)
def forbid_provider_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise AssertionError("Phase 4 gate must not construct a provider-backed model")

    monkeypatch.setattr(model_factory, "create_chat_model", forbidden)


def _assert_zero_managed_resources() -> None:
    queries = (
        ["docker", "ps", "-aq", "--filter", "label=deerflow.compile.managed=true"],
        ["docker", "ps", "-q", "--filter", "status=paused", "--filter", "label=deerflow.compile.managed=true"],
        ["docker", "images", "-q", "--filter", "label=deerflow.compile.managed=true"],
    )
    for command in queries:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == ""


def _make_budget(**overrides: int | float) -> AgentWorkflowBudget:
    values: dict[str, int | float] = {
        "max_model_requests": 8,
        "max_recorded_tokens": 10_000,
        "max_agent_steps": 24,
        "max_tool_calls": 16,
        "max_commands": 8,
        "node_timeout_seconds": 600,
        "command_timeout_seconds": 300,
        "evaluator_timeout_seconds": 600,
        "replay_timeout_seconds": 600,
        "cleanup_timeout_seconds": 120,
    }
    values.update(overrides)
    return AgentWorkflowBudget(**values)  # type: ignore[arg-type]


def _make_node_input(
    *,
    case: FixtureCase,
    session: CompileSession,
    attempt_id: str,
    budget: AgentWorkflowBudget | None = None,
) -> AgentBuildNodeInput:
    assert session.commit_sha is not None
    assert session.image_id is not None
    return AgentBuildNodeInput(
        task_id=f"phase4-{case.case_id}",
        attempt_id=attempt_id,
        session_id=session.session_id,
        repository_url=session.repo_url,
        commit_sha=session.commit_sha,
        source_snapshot_sha256=hashlib.sha256(session.commit_sha.encode()).hexdigest(),
        build_system_candidates=(case.build_system,),
        target_contract=AgentWorkflowTargetContract(
            target_id=f"target-{case.case_id}",
            artifact_types=("executable",),
            artifact_path_patterns=(case.artifact_path,),
            functional_oracle_ref=f"oracle-{case.case_id}",
        ),
        operation_policy_ref="phase4-zero-provider-v1",
        environment=AgentWorkflowEnvironmentIdentity(
            image_id=session.image_id,
            parallel_jobs=session.parallel_jobs,
            network_policy="compile-network-v1",
        ),
        budget=budget or _make_budget(),
        experiment_identity=AgentWorkflowExperimentIdentity(
            manifest_sha256=SHA256_A,
            protocol_sha256=SHA256_B,
            runner_sha256=SHA256_C,
        ),
        initial_observation={"build_system": case.build_system, "zero_provider": True},
    )


def _prepare_session(
    *,
    case: FixtureCase,
    repository: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[CompileSessionManager, CompileDockerRuntime, CompileSession]:
    workspace = tmp_path / "workspace"
    paths = Paths(
        base_dir=tmp_path / ".deer-flow",
        workspace_root=workspace,
        host_workspace_root=str(workspace),
    )
    manager = CompileSessionManager(paths=paths, default_image=COMPILE_IMAGE)
    runtime = CompileDockerRuntime(manager=manager)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))
    monkeypatch.setenv("COMPILE_RUNTIME_NO_PROXY", "host.docker.internal,127.0.0.1,localhost")
    repository_url, commit_sha = repository
    session = prepare_compile_session_impl(
        thread_id=f"phase4-{case.case_id}-{uuid.uuid4().hex[:10]}",
        repo_url=repository_url,
        run_id=f"run-{uuid.uuid4().hex}",
        task_description="Phase 4 zero-provider integration gate",
    )
    try:
        clone, _message = clone_repository_impl(
            session=session,
            repo_url=repository_url,
            max_retries=1,
        )
        assert clone.exit_code == 0, clone.combined_output
        assert session.commit_sha == commit_sha
        primary, detected, _suggested = inspect_build_system_impl(session=session)
        assert primary == case.build_system
        assert (case.build_system, case.marker) in detected
        session.selected_build_system = primary
        manager.save_session(session)
    except BaseException:
        runtime.stop_and_remove_container(session)
        _normalize_test_session_tree(session)
        raise
    return manager, runtime, session


def _candidate_path(session: CompileSession, attempt_id: str) -> Path:
    return Path(session.metadata_path).parent / "agent-workflow" / attempt_id / "candidate.json"


async def _run_build_node(
    *,
    case: FixtureCase,
    session: CompileSession,
    manager: CompileSessionManager,
    attempt_id: str,
) -> tuple[AgentBuildNodeInput, AgentBuildNodeResult]:
    node_input = _make_node_input(case=case, session=session, attempt_id=attempt_id)
    model = DeterministicBuildModel(
        case_id=case.case_id,
        build_system=case.build_system,
        commands=case.commands,
        artifact_path=case.artifact_path,
    )
    result = await run_agent_workflow_node_v1(
        node_input=node_input,
        session=session,
        manager=manager,
        model=model,
    )
    assert result.node_status == "submitted"
    assert result.candidate_submitted is True
    assert model.calls == len(case.commands) + 1
    assert any(item.get("parallel_tool_calls") is False for item in model.bind_kwargs)
    return node_input, result


def _run_evaluator(
    *,
    case: FixtureCase,
    session: CompileSession,
    manager: CompileSessionManager,
    node_input: AgentBuildNodeInput,
    node_result: AgentBuildNodeResult,
    attempt_id: str,
    backend: Any | None = None,
) -> ExternalEvaluationResult:
    evaluator_backend = backend or ForgeCompileEvaluationBackend(
        oracle_registry={
            f"oracle-{case.case_id}": FunctionalOracleSpec(
                oracle_ref=f"oracle-{case.case_id}",
                argv=(f"/artifacts/{case.artifact_path}", "--help"),
                workdir="/artifacts",
            )
        }
    )
    return run_external_evaluator_v1(
        node_input=node_input,
        node_result=node_result,
        session=session,
        manager=manager,
        candidate_path=_candidate_path(session, attempt_id),
        evaluation_id=f"evaluation-{attempt_id}",
        backend=evaluator_backend,
    )


def _cleanup(runtime: CompileDockerRuntime, session: CompileSession) -> None:
    try:
        cleanup_and_finalize_compile_session_impl(session=session)
    finally:
        runtime.stop_and_remove_container(session)
        _normalize_test_session_tree(session)
    _assert_zero_managed_resources()


def _normalize_test_session_tree(session: CompileSession) -> None:
    session_dir = Path(session.metadata_path).parent
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{session_dir}:/target",
            COMPILE_IMAGE,
            "sh",
            "-c",
            f"chown -R {os.getuid()}:{os.getgid()} /target && chmod -R u+rwX /target",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("case_id", [case.case_id for case in CASES])
def test_phase4_success_chain_covers_submit_s0_s5_replay_finalize_and_cleanup(
    case_id: str,
    fixture_repositories: dict[str, tuple[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = CASE_BY_ID[case_id]
    manager, runtime, session = _prepare_session(
        case=case,
        repository=fixture_repositories[case_id],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    try:
        attempt_id = f"attempt-{case_id}"
        node_input, node_result = asyncio.run(
            _run_build_node(
                case=case,
                session=session,
                manager=manager,
                attempt_id=attempt_id,
            )
        )
        evaluation = _run_evaluator(
            case=case,
            session=session,
            manager=manager,
            node_input=node_input,
            node_result=node_result,
            attempt_id=attempt_id,
        )
        assert evaluation.strict_reproducible_build_success is True
        assert [layer.status for layer in evaluation.layers] == ["passed"] * 6
        assert evaluation.bitwise_reproducible is True

        finalized, cleanup = cleanup_and_finalize_compile_session_impl(session=session)
        assert cleanup.succeeded is True
        assert cleanup.removed is True
        assert finalized.status == "completed"
        assert finalized.finalized_at is not None
        assert finalized.replay_attempts[-1].status == "passed"
        build_commands = [command for command in finalized.commands if command.role in {"configure", "build", "artifact_stage", "smoke"}]
        assert build_commands
        assert all(command.command_id and command.completed_at and command.exit_code == 0 for command in build_commands)
        assert all(command.log_path and Path(command.log_path).is_file() for command in build_commands)
    finally:
        _cleanup(runtime, session)


def test_phase4_no_submit_finalizes_and_cleans_real_session(
    fixture_repositories: dict[str, tuple[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = CASE_BY_ID["make"]
    manager, runtime, session = _prepare_session(
        case=case,
        repository=fixture_repositories[case.case_id],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    try:
        node_input = _make_node_input(case=case, session=session, attempt_id="attempt-no-submit")
        result = asyncio.run(
            run_agent_workflow_node_v1(
                node_input=node_input,
                session=session,
                manager=manager,
                model=StaticModel(response=AIMessage(content="没有候选可提交。")),
                finalizer=lambda current: cleanup_and_finalize_compile_session_impl(session=current),
            )
        )
        assert result.node_status == "no_submission"
        assert result.candidate_submitted is False
        current = manager.load_session(session.session_id, session.thread_id)
        assert current.status == "failed"
        assert current.finalized_at is not None
    finally:
        _cleanup(runtime, session)


def test_phase4_replay_bitwise_mismatch_is_auxiliary_not_strict_failure(
    fixture_repositories: dict[str, tuple[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = CASE_BY_ID["make"]
    manager, runtime, session = _prepare_session(
        case=case,
        repository=fixture_repositories[case.case_id],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    try:
        attempt_id = "attempt-replay-mismatch"
        node_input, node_result = asyncio.run(_run_build_node(case=case, session=session, manager=manager, attempt_id=attempt_id))
        mutation = runtime.exec(
            session,
            "printf '%s\\n' '#include <stdio.h>' 'const char phase4_build_id[] = \"alternate\";' 'int main(void) { puts(\"phase4-ok\"); return 0; }' | cc -x c -o /artifacts/phase4-make -",
            workdir="/workspace/repo",
            timeout_seconds=60,
        )
        assert mutation.exit_code == 0, mutation.combined_output
        evaluation = _run_evaluator(
            case=case,
            session=session,
            manager=manager,
            node_input=node_input,
            node_result=node_result,
            attempt_id=attempt_id,
        )
        assert evaluation.strict_reproducible_build_success is True
        assert evaluation.bitwise_reproducible is False
        s5 = evaluation.layers[-1]
        assert s5.status == "passed"
        assert "functional_replay_passed_bitwise_mismatch" in s5.reason_codes
        current = manager.load_session(session.session_id, session.thread_id)
        replay = current.replay_attempts[-1]
        assert replay.failure_classification == "size_mismatch"
        assert replay.artifacts[0].mismatches == ["size", "sha256"]
        assert replay.artifacts[0].type_matches is True
        assert replay.artifacts[0].smoke_matches is True
    finally:
        _cleanup(runtime, session)


def test_phase4_evaluator_exception_writes_failure_and_still_cleans(
    fixture_repositories: dict[str, tuple[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = CASE_BY_ID["make"]
    manager, runtime, session = _prepare_session(
        case=case,
        repository=fixture_repositories[case.case_id],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    try:
        attempt_id = "attempt-evaluator-exception"
        node_input, node_result = asyncio.run(_run_build_node(case=case, session=session, manager=manager, attempt_id=attempt_id))
        evaluation = _run_evaluator(
            case=case,
            session=session,
            manager=manager,
            node_input=node_input,
            node_result=node_result,
            attempt_id=attempt_id,
            backend=RaisingBackend(),
        )
        assert evaluation.strict_reproducible_build_success is False
        assert evaluation.primary_failure == "evaluator_internal_error"
        evaluation_dir = _candidate_path(session, attempt_id).parent / "evaluations" / f"evaluation-{attempt_id}"
        failure = json.loads((evaluation_dir / "failure.json").read_text(encoding="utf-8"))
        assert failure["classification"] == "evaluator_internal_error"
        assert (evaluation_dir / "result.json").is_file()
        assert (evaluation_dir / "summary.json").is_file()
    finally:
        _cleanup(runtime, session)


def test_phase4_cancel_finalizes_and_cleans_real_session(
    fixture_repositories: dict[str, tuple[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = CASE_BY_ID["make"]
    manager, runtime, session = _prepare_session(
        case=case,
        repository=fixture_repositories[case.case_id],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    async def run_cancelled() -> AgentBuildNodeResult:
        task = asyncio.create_task(
            run_agent_workflow_node_v1(
                node_input=_make_node_input(case=case, session=session, attempt_id="attempt-cancel"),
                session=session,
                manager=manager,
                model=SlowModel(response=AIMessage(content="late")),
                finalizer=lambda current: cleanup_and_finalize_compile_session_impl(
                    session=current,
                    interrupted_status="cancelled",
                    error="Phase 4 cancellation injection.",
                ),
            )
        )
        await asyncio.sleep(0.1)
        task.cancel()
        return await task

    try:
        result = asyncio.run(run_cancelled())
        assert result.node_status == "cancelled"
        assert result.primary_failure == "cancelled"
        current = manager.load_session(session.session_id, session.thread_id)
        assert current.status == "cancelled"
        assert current.finalized_at is not None
    finally:
        _cleanup(runtime, session)


def test_phase4_timeout_finalizes_and_cleans_real_session(
    fixture_repositories: dict[str, tuple[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = CASE_BY_ID["make"]
    manager, runtime, session = _prepare_session(
        case=case,
        repository=fixture_repositories[case.case_id],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    try:
        node_input = _make_node_input(
            case=case,
            session=session,
            attempt_id="attempt-timeout",
            budget=_make_budget(node_timeout_seconds=1),
        )
        result = asyncio.run(
            run_agent_workflow_node_v1(
                node_input=node_input,
                session=session,
                manager=manager,
                model=SlowModel(response=AIMessage(content="late")),
                finalizer=lambda current: cleanup_and_finalize_compile_session_impl(
                    session=current,
                    interrupted_status="timed_out",
                    error="Phase 4 timeout injection.",
                ),
            )
        )
        assert result.node_status == "no_submission"
        assert result.primary_failure == "budget_exhausted"
        assert result.budget_terminal_reason == "node_timeout_seconds"
        current = manager.load_session(session.session_id, session.thread_id)
        assert current.status == "timed_out"
        assert current.finalized_at is not None
    finally:
        _cleanup(runtime, session)


def test_phase4_cleanup_failure_is_deferred_then_retry_removes_container(
    fixture_repositories: dict[str, tuple[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = CASE_BY_ID["make"]
    manager, runtime, session = _prepare_session(
        case=case,
        repository=fixture_repositories[case.case_id],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    cleanup_results: list[ContainerCleanupResult] = []
    real_cleanup = runtime.stop_and_remove_container

    def fail_cleanup(current: CompileSession) -> ContainerCleanupResult:
        del current
        return ContainerCleanupResult(succeeded=False, stopped=False, removed=False)

    monkeypatch.setattr(runtime, "stop_and_remove_container", fail_cleanup)
    try:
        result = asyncio.run(
            run_agent_workflow_node_v1(
                node_input=_make_node_input(case=case, session=session, attempt_id="attempt-cleanup-failure"),
                session=session,
                manager=manager,
                model=StaticModel(response=AIMessage(content="没有候选可提交。")),
                finalizer=lambda current: cleanup_results.append(cleanup_and_finalize_compile_session_impl(session=current)[1]),
            )
        )
        assert result.node_status == "no_submission"
        assert cleanup_results == [ContainerCleanupResult(succeeded=False, stopped=False, removed=False)]
        current = manager.load_session(session.session_id, session.thread_id)
        assert current.status == "failed"
        assert current.finalized_at is None
        assert current.error is not None and "cleanup failed" in current.error.lower()

        monkeypatch.setattr(runtime, "stop_and_remove_container", real_cleanup)
        retried, cleanup = cleanup_and_finalize_compile_session_impl(session=current)
        assert cleanup.succeeded is True
        assert cleanup.removed is True
        assert retried.status == "failed"
        assert retried.finalized_at is not None
    finally:
        monkeypatch.setattr(runtime, "stop_and_remove_container", real_cleanup)
        _cleanup(runtime, session)
