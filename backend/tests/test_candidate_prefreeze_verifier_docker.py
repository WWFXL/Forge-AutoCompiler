"""Runtime v3 的 opt-in 零 Provider Docker lifecycle 门禁。"""

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
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import Field

from deerflow.compile import operations
from deerflow.compile.agent_workflow_runtime_v3 import run_agent_workflow_node_v3
from deerflow.compile.agent_workflow_schemas import (
    AgentBuildNodeInput,
    AgentWorkflowBudget,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowTargetContract,
)
from deerflow.compile.docker_runtime import CompileDockerRuntime
from deerflow.compile.external_evaluator_v4 import ForgeCompileEvaluationBackend, FunctionalOracleSpec, run_external_evaluator_v4
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
DOCKER_ENABLED = os.getenv("FORGE_RUN_PREFREEZE_DOCKER") == "1"
SHA256_A = "a" * 64
SHA256_B = "b" * 64
SHA256_C = "c" * 64
COMMAND_ID_PATTERN = re.compile(r"^command_id=(command_[0-9a-f]+)$", re.MULTILINE)
COMMAND_ROLE_PATTERN = re.compile(r"^command_role=([a-z_]+)$", re.MULTILINE)

pytestmark = pytest.mark.skipif(
    not DOCKER_ENABLED,
    reason="set FORGE_RUN_PREFREEZE_DOCKER=1 to run the pre-freeze Docker gate",
)

FIXTURE_FILES = {
    "Makefile": "CC ?= cc\nAR ?= ar\nCFLAGS ?= -O2\nlibsample.a: lib.o\n\t$(AR) rcs $@ $^\nlib.o: lib.c include/sample/api.h include/sample/detail.h\n\t$(CC) $(CFLAGS) -Iinclude -c -o $@ lib.c\n",
    "lib.c": '#include "sample/api.h"\nint sample_add(int left, int right) { return left + right + SAMPLE_OFFSET; }\n',
    "include/sample/api.h": '#ifndef SAMPLE_API_H\n#define SAMPLE_API_H\n#include "detail.h"\nint sample_add(int left, int right);\n#endif\n',
    "include/sample/detail.h": "#ifndef SAMPLE_DETAIL_H\n#define SAMPLE_DETAIL_H\n#define SAMPLE_OFFSET 0\n#endif\n",
    "oracle.c": "#include <sample/api.h>\nint main(void) { return sample_add(2, 3) == 5 ? 0 : 1; }\n",
    "tool.c": "int main(void) { return 0; }\n",
}


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


class DeterministicRepairModel(BaseChatModel):
    calls: int = 0
    bind_kwargs: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "prefreeze-docker-zero-provider"

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

    def _submit(self, messages: list[BaseMessage], *, wrong_mapping: bool, suffix: str) -> AIMessage:
        evidence = _command_evidence(messages)
        supporting = [command_id for command_id, role in evidence if role == "build"]
        recipe = [command_id for command_id, role in evidence if role in {"build", "artifact_stage"}]
        target_mapping = {"sample-static-library": "lib/libsample.a"}
        if wrong_mapping:
            target_mapping["sample-public-headers"] = "include/sample/api.h"
        return _tool_call(
            "submit_candidate_v1",
            {
                "candidate_id": "candidate-prefreeze-docker",
                "build_system": "make",
                "supporting_command_ids": supporting,
                "artifact_paths": ["include/sample/api.h", "lib/libsample.a"],
                "target_mapping": target_mapping,
                "recipe_command_ids": recipe,
                "agent_summary": "Runtime v3 零 Provider lifecycle fixture",
                "known_limitations": [],
            },
            f"submit-{suffix}",
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        actions = (
            lambda: _tool_call(
                "run_container_bash",
                {"command": "make && cc -o tool tool.c", "command_role": "build", "timeout_seconds": 300, "workdir": "/workspace/repo"},
                "build",
            ),
            lambda: _tool_call(
                "run_container_bash",
                {
                    "command": (
                        "mkdir -p /artifacts/include/sample /artifacts/lib /artifacts/bin /artifacts/share/doc "
                        "&& cp include/sample/api.h /artifacts/include/sample/api.h "
                        "&& cp libsample.a /artifacts/lib/libsample.a "
                        "&& cp libsample.a /artifacts/lib/libsample-test.a "
                        "&& cp tool /artifacts/bin/tool "
                        "&& : > /artifacts/share/doc/build.stamp"
                    ),
                    "command_role": "artifact_stage",
                    "timeout_seconds": 300,
                    "workdir": "/workspace/repo",
                },
                "stage-broad",
            ),
            lambda: self._submit(messages, wrong_mapping=False, suffix="broad"),
            lambda: _tool_call(
                "run_container_bash",
                {
                    "command": "rm -f /artifacts/lib/libsample-test.a /artifacts/bin/tool /artifacts/share/doc/build.stamp",
                    "command_role": "artifact_stage",
                    "timeout_seconds": 300,
                    "workdir": "/workspace/repo",
                },
                "stage-trim",
            ),
            lambda: self._submit(messages, wrong_mapping=True, suffix="target"),
            lambda: self._submit(messages, wrong_mapping=False, suffix="oracle-fail"),
            lambda: _tool_call(
                "run_container_bash",
                {
                    "command": "cp include/sample/detail.h /artifacts/include/sample/detail.h",
                    "command_role": "artifact_stage",
                    "timeout_seconds": 300,
                    "workdir": "/workspace/repo",
                },
                "stage-header-closure",
            ),
            lambda: self._submit(messages, wrong_mapping=False, suffix="accepted"),
        )
        response = actions[self.calls]()
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=response)])


def _git(*args: str, cwd: Path) -> str:
    completed = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, timeout=30)
    return completed.stdout.strip()


@pytest.fixture(scope="module")
def fixture_repository(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, str]]:
    root = tmp_path_factory.mktemp("prefreeze-docker-fixture")
    source = root / "source"
    bare = root / "fixture.git"
    source.mkdir()
    for relative_path, content in FIXTURE_FILES.items():
        path = source / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git("init", "--quiet", cwd=source)
    _git("config", "user.name", "Forge Prefreeze Gate", cwd=source)
    _git("config", "user.email", "prefreeze@example.invalid", cwd=source)
    _git("add", ".", cwd=source)
    _git("commit", "--quiet", "-m", "prefreeze fixture", cwd=source)
    commit_sha = _git("rev-parse", "HEAD", cwd=source)
    _git("clone", "--quiet", "--bare", str(source), str(bare), cwd=root)
    _git("update-server-info", cwd=bare)

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    daemon = subprocess.Popen(
        ["git", "daemon", "--reuseaddr", "--export-all", f"--base-path={root}", "--listen=0.0.0.0", f"--port={port}", str(root)],
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
                raise RuntimeError("pre-freeze fixture git daemon failed to start")
            time.sleep(0.05)
    try:
        yield f"git://host.docker.internal:{port}/fixture.git", commit_sha
    finally:
        daemon.terminate()
        try:
            daemon.wait(timeout=5)
        except subprocess.TimeoutExpired:
            daemon.kill()
            daemon.wait(timeout=5)


def _assert_zero_managed_resources() -> None:
    for command in (
        ["docker", "ps", "-aq", "--filter", "label=deerflow.compile.managed=true"],
        ["docker", "ps", "-q", "--filter", "status=paused", "--filter", "label=deerflow.compile.managed=true"],
        ["docker", "images", "-q", "--filter", "label=deerflow.compile.managed=true"],
    ):
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == ""


@pytest.fixture(scope="module", autouse=True)
def require_docker_gate() -> Iterator[None]:
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
    image = subprocess.run(["docker", "image", "inspect", COMPILE_IMAGE], check=False, capture_output=True, text=True, timeout=30)
    if image.returncode != 0:
        pytest.fail(f"Required image {COMPILE_IMAGE!r} is unavailable")
    _assert_zero_managed_resources()
    yield
    _assert_zero_managed_resources()


@pytest.fixture(autouse=True)
def forbid_provider_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise AssertionError("pre-freeze gate must not construct a provider-backed model")

    monkeypatch.setattr(model_factory, "create_chat_model", forbidden)


def _oracle_spec() -> FunctionalOracleSpec:
    return FunctionalOracleSpec(
        oracle_ref="oracle-prefreeze-docker-v1",
        argv=(
            "sh",
            "-c",
            "cc -I/artifacts/include oracle.c /artifacts/lib/libsample.a -o /tmp/prefreeze-oracle && /tmp/prefreeze-oracle",
        ),
        workdir="/workspace/repo",
        timeout_seconds=120,
    )


def _node_input(session: CompileSession, commit_sha: str) -> AgentBuildNodeInput:
    return AgentBuildNodeInput(
        task_id="prefreeze-docker",
        attempt_id="attempt-prefreeze-docker",
        session_id=session.session_id,
        repository_url=session.repo_url,
        commit_sha=commit_sha,
        source_snapshot_sha256=hashlib.sha256(commit_sha.encode()).hexdigest(),
        build_system_candidates=("make",),
        target_contract=AgentWorkflowTargetContract(
            target_id="sample-static-library",
            artifact_types=("static_library",),
            artifact_path_patterns=("lib/libsample.a",),
            functional_oracle_ref="oracle-prefreeze-docker-v1",
        ),
        operation_policy_ref="prefreeze-zero-provider-v1",
        environment=AgentWorkflowEnvironmentIdentity(
            image_id=session.image_id or "",
            parallel_jobs=session.parallel_jobs,
            network_policy="compile-network-v1",
        ),
        budget=AgentWorkflowBudget(
            max_model_requests=12,
            max_recorded_tokens=None,
            max_agent_steps=40,
            max_tool_calls=20,
            max_commands=12,
            node_timeout_seconds=600,
            command_timeout_seconds=300,
            evaluator_timeout_seconds=600,
            replay_timeout_seconds=600,
            cleanup_timeout_seconds=120,
        ),
        experiment_identity=AgentWorkflowExperimentIdentity(
            manifest_sha256=SHA256_A,
            protocol_sha256=SHA256_B,
            runner_sha256=SHA256_C,
        ),
        initial_observation={
            "required_candidate_artifacts": ("include/sample/api.h", "lib/libsample.a"),
            "zero_provider": True,
        },
    )


def _normalize_session_tree(session: CompileSession) -> None:
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


def test_prefreeze_repair_then_external_recompute_replay_and_cleanup(
    fixture_repository: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    paths = Paths(base_dir=tmp_path / ".deer-flow", workspace_root=workspace, host_workspace_root=str(workspace))
    manager = CompileSessionManager(paths=paths, default_image=COMPILE_IMAGE)
    runtime = CompileDockerRuntime(manager=manager)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))
    monkeypatch.setenv("COMPILE_RUNTIME_NO_PROXY", "host.docker.internal,127.0.0.1,localhost")
    repository_url, commit_sha = fixture_repository
    session = prepare_compile_session_impl(
        thread_id=f"prefreeze-docker-{uuid.uuid4().hex[:10]}",
        repo_url=repository_url,
        run_id=f"run-{uuid.uuid4().hex}",
        task_description="Runtime v3 pre-freeze zero-provider lifecycle gate",
    )
    cleaned = False
    try:
        clone, _message = clone_repository_impl(session=session, repo_url=repository_url, max_retries=1)
        assert clone.exit_code == 0, clone.combined_output
        assert session.commit_sha == commit_sha
        primary, _detected, _suggested = inspect_build_system_impl(session=session)
        assert primary == "make"
        session.selected_build_system = "make"
        manager.save_session(session)
        node_input = _node_input(session, commit_sha)
        model = DeterministicRepairModel()
        oracle_spec = _oracle_spec()

        node_result = asyncio.run(
            run_agent_workflow_node_v3(
                node_input=node_input,
                session=session,
                manager=manager,
                model=model,
                oracle_registry={oracle_spec.oracle_ref: oracle_spec},
            )
        )
        assert node_result.node_status == "submitted"
        assert node_result.usage.recorded_tokens == 96
        assert model.calls == 8
        candidate_path = Path(session.metadata_path).parent / "agent-workflow" / node_input.attempt_id / "candidate.json"
        events_path = candidate_path.parent / "events.jsonl"
        events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
        rejection_codes = [event["payload"]["rejection_codes"] for event in events if event["event_type"] == "candidate.submit_rejected"]
        assert rejection_codes == [
            ["delivery_zero_byte", "undeclared_compiled_artifact"],
            ["target_mapping_invalid"],
            ["functional_oracle_failed"],
        ]

        evaluation = run_external_evaluator_v4(
            node_input=node_input,
            node_result=node_result,
            session=session,
            manager=manager,
            candidate_path=candidate_path,
            evaluation_id="prefreeze-docker-evaluation-v4",
            backend=ForgeCompileEvaluationBackend(oracle_registry={oracle_spec.oracle_ref: oracle_spec}),
        )
        assert evaluation.strict_reproducible_build_success is True
        assert evaluation.bitwise_reproducible is True

        finalized, cleanup = cleanup_and_finalize_compile_session_impl(session=session)
        cleaned = True
        assert finalized.status == "completed"
        assert cleanup.succeeded is True
    finally:
        if not cleaned:
            runtime.stop_and_remove_container(session)
        _normalize_session_tree(session)
    _assert_zero_managed_resources()
