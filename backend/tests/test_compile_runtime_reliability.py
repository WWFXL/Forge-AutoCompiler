import asyncio
import json
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.runnables import RunnableLambda
from langgraph.runtime import Runtime

from deerflow.agents.middlewares.compile_termination_middleware import CompileTerminationMiddleware
from deerflow.compile import operations
from deerflow.compile.docker_runtime import CompileDockerRuntime, ContainerCleanupResult, ManagedCompileContainer, RuntimeConfig
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.operations import CompileOperationsServices
from deerflow.compile.paths import get_repro_dir
from deerflow.compile.schemas import BuildCommandRecord, CommandResult, ReplayRecipe, ReplayRecipeStep, ReplayVerificationResult
from deerflow.config.paths import Paths
from deerflow.tools import bound_compile_tools
from deerflow.tools.builtins import agent_compile_tools

VALID_IMAGE_ID = f"sha256:{'1' * 64}"


@pytest.fixture(autouse=True)
def isolate_compile_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace_root = tmp_path / "workspace"
    monkeypatch.setenv("DEER_FLOW_WORKSPACE_ROOT", str(workspace_root))
    monkeypatch.setenv("DEER_FLOW_HOST_WORKSPACE_ROOT", str(workspace_root))


def make_test_paths(tmp_path: Path) -> Paths:
    return Paths(
        base_dir=tmp_path / ".deer-flow",
        workspace_root=tmp_path / "service-workspace",
        host_workspace_root=str(tmp_path / "host-workspace"),
    )


def test_run_container_bash_schema_requires_a_supported_logical_role() -> None:
    schema = bound_compile_tools.run_container_bash.args_schema.model_json_schema()

    assert "command_role" in schema["required"]
    assert set(schema["properties"]["command_role"]["enum"]) == {
        "dependency",
        "configure",
        "build",
        "diagnostic",
        "smoke",
        "artifact_stage",
    }


def test_run_container_bash_rejects_an_unsupported_role_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-invalid-command-role",
        repo_url="https://example.com/repo.git",
    )
    runtime = SimpleNamespace(exec=lambda *_args, **_kwargs: pytest.fail("invalid role reached runtime"))
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    with pytest.raises(ValueError, match="Unsupported compile command role"):
        bound_compile_tools._run_container_bash_impl(
            session=session,
            command="printf invalid",
            command_role="other",  # type: ignore[arg-type]
        )


def test_runtime_strict_shell_prelude_preserves_pipeline_and_sequence_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[list[str]] = []

    def fake_run(command, **_kwargs):
        observed.append(command)
        return SimpleNamespace(returncode=9, stdout="", stderr="failed\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runtime = CompileDockerRuntime(config=RuntimeConfig())
    session = operations.CompileSession(
        session_id="session-strict-shell",
        thread_id="thread-strict-shell",
        repo_url="https://example.com/repo.git",
        branch=None,
        image="autocompiler:gcc13",
        status="ready",
        container_id="container-strict-shell",
    )

    result = runtime.exec(
        session,
        "false | tee output.log; echo done",
        strict_shell=True,
    )

    assert result.exit_code == 9
    assert observed[0][-2:] == ["-lc", "set -euo pipefail\nfalse | tee output.log; echo done"]


def test_mixed_logical_stages_are_rejected_before_container_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-mixed-stage",
        repo_url="https://example.com/repo.git",
    )
    runtime = SimpleNamespace(exec=lambda *_args, **_kwargs: pytest.fail("mixed stage reached runtime"))
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    result, message, record = bound_compile_tools._run_container_bash_impl(
        session=session,
        command="cmake -S . -B build && cmake --build build && cp build/app /artifacts/app",
        command_role="build",
    )

    assert result.exit_code == 126
    assert record.termination == "policy_rejected"
    assert "classification=mixed_logical_stages" in message
    assert Path(record.log_path or "").read_text(encoding="utf-8").startswith("A run_container_bash call")


@pytest.mark.parametrize(
    "command",
    [
        "set +e\nfalse",
        "set +u; printf ok",
        "set +o pipefail\nfalse | true",
    ],
)
def test_strict_shell_options_cannot_be_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-strict-shell-disable",
        repo_url="https://example.com/repo.git",
    )
    runtime = SimpleNamespace(exec=lambda *_args, **_kwargs: pytest.fail("disabled strict shell reached runtime"))
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    result, message, record = bound_compile_tools._run_container_bash_impl(
        session=session,
        command=command,
        command_role="diagnostic",
    )

    assert result.exit_code == 126
    assert record.termination == "policy_rejected"
    assert "classification=strict_shell_disabled" in message
    assert "may not disable" in Path(record.log_path or "").read_text(encoding="utf-8")


def test_standard_runnable_config_run_id_is_used_for_compile_ownership() -> None:
    tool_runtime = SimpleNamespace(
        context={},
        config={"configurable": {"thread_id": "thread-config-run"}, "run_id": "run-from-runnable-config"},
    )
    middleware_runtime = Runtime(context={})

    assert agent_compile_tools._get_run_id(tool_runtime) == "run-from-runnable-config"
    identity = RunnableLambda(lambda _: CompileTerminationMiddleware._run_identity(middleware_runtime)).invoke(
        None,
        config={
            "configurable": {
                "thread_id": "thread-config-run",
                "run_id": "run-from-runnable-config",
            }
        },
    )
    assert identity == (
        "thread-config-run",
        "run-from-runnable-config",
    )


def test_prepare_tool_refuses_to_create_an_unowned_session() -> None:
    runtime = SimpleNamespace(
        context={"thread_id": "thread-without-run"},
        config={"configurable": {"thread_id": "thread-without-run"}},
    )

    with pytest.raises(RuntimeError, match="Missing run_id"):
        agent_compile_tools.prepare_compile_session.func(
            runtime=runtime,
            repo_url="https://example.com/repo.git",
            tool_call_id="tool-prepare-without-run",
        )


def test_lead_cleanup_does_not_expand_to_the_whole_thread_without_run_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(
        operations,
        "finalize_unfinished_thread_sessions_impl",
        lambda **kwargs: calls.append(kwargs),
    )
    middleware = CompileTerminationMiddleware(cleanup_run_on_end=True)
    runtime = Runtime(context={"thread_id": "thread-without-run"})

    assert asyncio.run(middleware.aafter_agent({}, runtime)) is None
    assert calls == []


class _PrepareRuntime:
    def __init__(self) -> None:
        self.create_calls = 0
        self.cleanup_calls = 0
        self._lock = threading.Lock()

    def create_container(self, session) -> str:
        with self._lock:
            self.create_calls += 1
        session.container_id = "container-shared"
        session.container_name = "deerflow-compile-shared"
        session.image_id = VALID_IMAGE_ID
        return session.container_id

    def stop_and_remove_container(self, _session) -> ContainerCleanupResult:
        self.cleanup_calls += 1
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)


def test_prepare_reuses_the_same_active_session_and_container_for_a_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    runtime = _PrepareRuntime()
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    first = operations.prepare_compile_session_impl(
        thread_id="thread-prepare-reuse",
        run_id="run-prepare-reuse",
        repo_url="https://example.com/repo.git",
        branch="main",
    )
    second = operations.prepare_compile_session_impl(
        thread_id="thread-prepare-reuse",
        run_id="run-prepare-reuse",
        repo_url="https://example.com/repo.git",
        branch="main",
    )

    assert second.session_id == first.session_id
    assert second.container_id == first.container_id
    assert runtime.create_calls == 1
    assert len(manager.list_sessions("thread-prepare-reuse")) == 1


def test_concurrent_prepare_creates_exactly_one_active_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    runtime = _PrepareRuntime()
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    def prepare(_index: int):
        return operations.prepare_compile_session_impl(
            thread_id="thread-concurrent-prepare",
            run_id="run-concurrent-prepare",
            repo_url="https://example.com/repo.git",
            branch="main",
        )

    with ThreadPoolExecutor(max_workers=16) as executor:
        sessions = list(executor.map(prepare, range(100)))

    assert len({session.session_id for session in sessions}) == 1
    assert len({session.container_id for session in sessions}) == 1
    assert runtime.create_calls == 1
    assert len(manager.list_sessions("thread-concurrent-prepare")) == 1


def test_prepare_rejects_a_different_request_in_the_same_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    runtime = _PrepareRuntime()
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))
    operations.prepare_compile_session_impl(
        thread_id="thread-prepare-conflict",
        run_id="run-prepare-conflict",
        repo_url="https://example.com/first.git",
        branch="main",
    )

    with pytest.raises(operations.CompileSessionConflictError) as raised:
        operations.prepare_compile_session_impl(
            thread_id="thread-prepare-conflict",
            run_id="run-prepare-conflict",
            repo_url="https://example.com/second.git",
            branch="main",
        )

    assert raised.value.classification == "active_session_conflict"
    assert runtime.create_calls == 1


def test_parallel_bash_commands_use_command_ids_as_unique_log_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-command-logs",
        repo_url="https://example.com/repo.git",
    )
    barrier = threading.Barrier(100)

    def fake_exec(_session, command, **kwargs):
        barrier.wait(timeout=10)
        Path(kwargs["log_path"]).write_text(command + "\n", encoding="utf-8")
        return CommandResult(
            exit_code=0,
            stdout="ok\n",
            stderr="",
            combined_output="ok\n",
            log_path=kwargs["log_path"],
        )

    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=SimpleNamespace(exec=fake_exec)),
    )

    def execute(index: int):
        return bound_compile_tools._run_container_bash_impl(
            session=session,
            command=f"printf diagnostic-{index}",
            command_role="diagnostic",
        )[2]

    with ThreadPoolExecutor(max_workers=100) as executor:
        records = list(executor.map(execute, range(100)))

    assert len({record.command_id for record in records}) == 100
    assert len({record.log_path for record in records}) == 100
    assert all(Path(record.log_path or "").name == f"{record.command_id}.log" for record in records)
    assert len(list(manager.local_logs_dir(session).glob("command_*.log"))) == 100


def test_bash_tool_exposes_only_the_container_log_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-container-log-path",
        repo_url="https://example.com/repo.git",
    )

    def fake_exec(_session, _command, **kwargs):
        return CommandResult(
            exit_code=0,
            stdout="ok\n",
            stderr="",
            combined_output="ok\n",
            log_path=kwargs["log_path"],
        )

    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=SimpleNamespace(exec=fake_exec)),
    )

    _result, message, record = bound_compile_tools._run_container_bash_impl(
        session=session,
        command="printf ok",
        command_role="diagnostic",
    )

    assert f"log_path=/logs/{record.command_id}.log" in message
    assert str(tmp_path) not in message
    assert record.log_path is not None
    assert Path(record.log_path).is_absolute()


def _append_recipe_command(session, *, command_id: str, role: str, command: str, exit_code: int = 0) -> None:
    session.commands.append(
        BuildCommandRecord(
            stage="bash",
            command=command,
            workdir="/workspace/repo",
            command_id=command_id,
            role=role,
            exit_code=exit_code,
        )
    )


def test_replay_bundle_uses_only_explicit_recipe_command_ids(tmp_path: Path) -> None:
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-explicit-recipe",
        repo_url="https://example.com/repo.git",
    )
    session.commit_sha = "a" * 40
    _append_recipe_command(session, command_id="command_configure", role="configure", command="cmake -S . -B build")
    _append_recipe_command(session, command_id="command_diagnostic", role="diagnostic", command="find build -type f")
    _append_recipe_command(session, command_id="command_build", role="build", command="cmake --build build")
    _append_recipe_command(session, command_id="command_stage", role="artifact_stage", command="cp build/app /artifacts/app")
    session.post_build_supporting_command_id = "command_build"
    manager.save_session(session)

    recipe = operations.build_replay_recipe(
        session,
        supporting_command_id="command_build",
        recipe_command_ids=["command_configure", "command_build", "command_stage"],
        verification_command_ids=[],
    )
    script = operations._write_repro_bundle(session, recipe).read_text(encoding="utf-8")

    assert [step.command_id for step in recipe.steps] == [
        "command_configure",
        "command_build",
        "command_stage",
    ]
    assert "find build -type f" not in script
    assert script.count("set -euo pipefail") == 4


@pytest.mark.parametrize(
    ("recipe_ids", "classification", "offending_command_id"),
    [
        (["command_configure", "command_diagnostic", "command_build", "command_stage"], "recipe_role_not_allowed", "command_diagnostic"),
        (["command_configure", "command_failed", "command_build", "command_stage"], "recipe_command_not_successful", "command_failed"),
        (["command_build", "command_configure", "command_stage"], "recipe_command_out_of_order", "command_configure"),
        (["command_configure", "command_build", "command_build", "command_stage"], "recipe_command_duplicate", "command_build"),
    ],
)
def test_replay_recipe_rejects_nonportable_audit_history(
    tmp_path: Path,
    recipe_ids: list[str],
    classification: str,
    offending_command_id: str,
) -> None:
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id=f"thread-recipe-{classification}",
        repo_url="https://example.com/repo.git",
    )
    session.commit_sha = "a" * 40
    _append_recipe_command(session, command_id="command_configure", role="configure", command="cmake -S . -B build")
    _append_recipe_command(session, command_id="command_diagnostic", role="diagnostic", command="find build -type f")
    _append_recipe_command(session, command_id="command_failed", role="dependency", command="apt-get update", exit_code=1)
    _append_recipe_command(session, command_id="command_build", role="build", command="cmake --build build")
    _append_recipe_command(session, command_id="command_stage", role="artifact_stage", command="cp build/app /artifacts/app")
    session.post_build_supporting_command_id = "command_build"
    manager.save_session(session)

    with pytest.raises(operations.ReplayRecipeError) as raised:
        operations.build_replay_recipe(
            session,
            supporting_command_id="command_build",
            recipe_command_ids=recipe_ids,
            verification_command_ids=[],
        )

    assert raised.value.classification == classification
    assert raised.value.offending_command_id == offending_command_id


def test_submit_reports_structured_replay_recipe_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-structured-recipe-error",
        repo_url="https://example.com/repo.git",
    )
    session.commit_sha = "a" * 40
    artifact = Path(session.leadagent_artifacts_dir) / "libexample.a"
    artifact.write_bytes(b"compiled-artifact")
    _append_recipe_command(
        session,
        command_id="command_diagnostic",
        role="diagnostic",
        command="find build -type f",
    )
    _append_recipe_command(
        session,
        command_id="command_build",
        role="build",
        command="cmake --build build",
    )
    _append_recipe_command(
        session,
        command_id="command_stage",
        role="artifact_stage",
        command="cp build/libexample.a /artifacts/libexample.a",
    )
    session.post_build_supporting_command_id = "command_build"
    manager.save_session(session)
    monkeypatch.setattr(operations, "_classify_compiled_artifact", lambda _path: "static_library")
    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=SimpleNamespace()),
    )

    payload = json.loads(
        operations.submit_build_result_impl(
            session=session,
            supporting_command_id="command_build",
            recipe_command_ids=[
                "command_diagnostic",
                "command_build",
                "command_stage",
            ],
            verification_command_ids=[],
        )
    )

    assert payload["status"] == "failed"
    assert payload["classification"] == "recipe_role_not_allowed"
    assert payload["offending_command_id"] == "command_diagnostic"


def test_compile_container_labels_include_complete_run_ownership(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-container-labels",
        run_id="run-container-labels",
        repo_url="https://example.com/repo.git",
    )
    observed: list[list[str]] = []

    def fake_run(command, **_kwargs):
        observed.append(command)
        if command[:2] == ["docker", "network"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[:2] == ["docker", "run"]:
            return SimpleNamespace(returncode=0, stdout="container-id\n", stderr="")
        if command[:2] == ["docker", "inspect"]:
            return SimpleNamespace(returncode=0, stdout=f"{VALID_IMAGE_ID}\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(subprocess, "run", fake_run)
    CompileDockerRuntime(manager=manager).create_container(session)
    docker_run = next(command for command in observed if command[:2] == ["docker", "run"])

    assert "deerflow.compile.managed=true" in docker_run
    assert "deerflow.compile.run_id=run-container-labels" in docker_run
    assert "deerflow.compile.thread_id=thread-container-labels" in docker_run
    assert f"deerflow.compile.session_id={session.session_id}" in docker_run


class _OrphanRuntime:
    def __init__(self, containers: list[ManagedCompileContainer]) -> None:
        self.containers = containers
        self.removed: list[str] = []

    def list_managed_containers(self) -> list[ManagedCompileContainer]:
        return self.containers

    def stop_and_remove_container_reference(self, _session, *, container_id, **_kwargs) -> ContainerCleanupResult:
        self.removed.append(container_id)
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)


def _owned_container(session, *, container_id: str, labels: dict[str, str] | None = None) -> ManagedCompileContainer:
    ownership = {
        "deerflow.compile.managed": "true",
        "deerflow.compile.role": "compile",
        "deerflow.compile.run_id": session.run_id or "",
        "deerflow.compile.session_id": session.session_id,
        "deerflow.compile.thread_id": session.thread_id,
    }
    ownership.update(labels or {})
    return ManagedCompileContainer(
        container_id=container_id,
        container_name=f"container-{container_id}",
        labels=ownership,
    )


def test_orphan_reconciliation_removes_only_proven_terminal_owned_containers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    terminal = manager.create_session(
        thread_id="thread-orphan-terminal",
        run_id="run-orphan-terminal",
        repo_url="https://example.com/terminal.git",
    )
    terminal.container_id = "terminal-id"
    terminal.container_name = "container-terminal-id"
    terminal.status = "failed"
    manager.save_session(terminal)
    active = manager.create_session(
        thread_id="thread-orphan-active",
        run_id="run-orphan-active",
        repo_url="https://example.com/active.git",
    )
    active.container_id = "active-id"
    active.container_name = "container-active-id"
    active.status = "ready"
    manager.save_session(active)
    incomplete = _owned_container(terminal, container_id="incomplete-id")
    del incomplete.labels["deerflow.compile.run_id"]
    runtime = _OrphanRuntime(
        [
            _owned_container(terminal, container_id="terminal-id"),
            _owned_container(active, container_id="active-id"),
            incomplete,
        ]
    )
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    result = operations.reconcile_orphaned_compile_containers_impl()

    assert result == {
        "scan_succeeded": True,
        "observed_count": 3,
        "removed_count": 1,
        "remaining_count": 2,
        "skipped_count": 2,
        "remaining_container_ids": ["active-id", "incomplete-id"],
    }
    assert runtime.removed == ["terminal-id"]


class _ReplayDedupRuntime:
    def __init__(self) -> None:
        self.config = SimpleNamespace(replay_timeout_seconds=1200)
        self.create_calls = 0

    @staticmethod
    def replay_container_name(_session, attempt_id: str) -> str:
        return f"replay-{attempt_id}"

    def create_replay_container(self, *_args, **_kwargs):
        self.create_calls += 1
        raise RuntimeError("test replay creation reached")

    @staticmethod
    def stop_and_remove_replay_container(*_args, **_kwargs) -> ContainerCleanupResult:
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)


def _replay_recipe(fingerprint: str) -> ReplayRecipe:
    return ReplayRecipe(
        supporting_command_id="command-build",
        steps=[
            ReplayRecipeStep(
                command_id="command-build",
                role="build",
                command_sha256="a" * 64,
                workdir_sha256="b" * 64,
            )
        ],
        fingerprint=fingerprint,
    )


def test_deterministic_replay_failure_is_reused_without_creating_a_container(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-replay-dedup",
        repo_url="https://example.com/repo.git",
    )
    session.status = "verification_failed"
    session.commit_sha = "a" * 40
    session.image_id = VALID_IMAGE_ID
    session.replay_recipe = _replay_recipe("c" * 64)
    previous = ReplayVerificationResult(
        attempt_id="replay-existing",
        status="failed",
        image=session.image,
        image_id=VALID_IMAGE_ID,
        commit_sha=session.commit_sha,
        recipe_sha256="d" * 64,
        recipe_fingerprint=session.replay_recipe.fingerprint,
        primary_failure_classification="sha256_mismatch",
        cleanup_succeeded=True,
    )
    session.replay_attempts = [previous]
    manager.save_session(session)
    runtime = _ReplayDedupRuntime()
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    returned = operations.verify_clean_replay_impl(session=session)

    assert returned.attempt_id == previous.attempt_id
    assert runtime.create_calls == 0


def test_changed_replay_recipe_creates_a_new_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-replay-changed",
        repo_url="https://example.com/repo.git",
    )
    session.status = "verification_failed"
    session.commit_sha = "a" * 40
    session.image_id = VALID_IMAGE_ID
    session.replay_recipe = _replay_recipe("new-fingerprint")
    session.replay_attempts = [
        ReplayVerificationResult(
            attempt_id="replay-existing",
            status="failed",
            image=session.image,
            image_id=VALID_IMAGE_ID,
            commit_sha=session.commit_sha,
            recipe_sha256="d" * 64,
            recipe_fingerprint="old-fingerprint",
            primary_failure_classification="sha256_mismatch",
            cleanup_succeeded=True,
        )
    ]
    repro_dir = Path(session.leadagent_repro_dir)
    repro_dir.mkdir(parents=True, exist_ok=True)
    (repro_dir / "build.sh").write_text("#!/usr/bin/env bash\ntrue\n", encoding="utf-8")
    manager.save_session(session)
    runtime = _ReplayDedupRuntime()
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    returned = operations.verify_clean_replay_impl(session=session)

    assert returned.attempt_id != "replay-existing"
    assert returned.primary_failure_classification == "internal_error"
    assert runtime.create_calls == 1


def test_lead_after_agent_finalizes_unfinished_run_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def finalize(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(operations, "finalize_unfinished_thread_sessions_impl", finalize)
    middleware = CompileTerminationMiddleware(cleanup_run_on_end=True)
    runtime = Runtime(context={"thread_id": "thread-after-agent", "run_id": "run-after-agent"})

    assert asyncio.run(middleware.aafter_agent({}, runtime)) is None
    assert calls == [
        {
            "thread_id": "thread-after-agent",
            "run_id": "run-after-agent",
        }
    ]


def test_replay_recipe_is_persisted_in_session_round_trip(tmp_path: Path) -> None:
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-recipe-round-trip",
        repo_url="https://example.com/repo.git",
    )
    session.commit_sha = "a" * 40
    _append_recipe_command(session, command_id="command_build", role="build", command="cmake --build build")
    _append_recipe_command(session, command_id="command_stage", role="artifact_stage", command="cp build/app /artifacts/app")
    session.post_build_supporting_command_id = "command_build"
    session.replay_recipe = operations.build_replay_recipe(
        session,
        supporting_command_id="command_build",
        recipe_command_ids=["command_build", "command_stage"],
        verification_command_ids=[],
    )
    manager.save_session(session)

    reloaded = manager.load_session(session.session_id, session.thread_id)

    assert reloaded.replay_recipe is not None
    assert [step.command_id for step in reloaded.replay_recipe.steps] == ["command_build", "command_stage"]
    assert get_repro_dir(session.session_id, session.thread_id, manager.paths).is_dir()
