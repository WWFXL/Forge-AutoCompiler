"""Opt-in Docker integration coverage for clean compile replay.

Run explicitly with FORGE_RUN_DOCKER_INTEGRATION=1 after building
the autocompiler:gcc13 image. The default backend test suite skips this file.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow.compile import operations
from deerflow.compile.docker_runtime import CompileDockerRuntime
from deerflow.compile.evidence import ExperimentLedger, ExperimentPolicy, activate_experiment, deactivate_experiment, new_evidence_id
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.operations import (
    CompileOperationsServices,
    _classify_compiled_artifact,
    _write_repro_bundle,
    cleanup_and_finalize_compile_session_impl,
    clone_repository_impl,
    finalize_unfinished_thread_sessions_impl,
    inspect_build_system_impl,
    verify_clean_replay_impl,
)
from deerflow.compile.schemas import BuildArtifact, BuildCommandRecord, CommandResult, CompileSession, VerificationResult
from deerflow.config.paths import Paths
from deerflow.tools import bound_compile_tools
from deerflow.tools.builtins import agent_compile_tools

task_tool_module = importlib.import_module("deerflow.tools.builtins.task_tool")

REPO_URL = "https://github.com/MattClarkson/CMakeHelloWorld.git"
COMMIT_SHA = "6fda0b169299b1241ed883c8d4af8519da30ce52"
HIREDIS_REPO_URL = "https://github.com/redis/hiredis"
HIREDIS_COMMIT_SHA = "60e5075d4ac77424809f855ba3e398df7aacefe8"
LIBCHECK_REPO_URL = "https://github.com/libcheck/check"
LIBCHECK_COMMIT_SHA = "11970a7e112dfe243a2e68773f014687df2900e8"
COMPILE_IMAGE = "autocompiler:gcc13"
COMPILE_IMAGE_ID = "sha256:900d7ce4b902b79df5c64ffab88631b251538f1bde578c4dd2bf91558e9d1554"
DOCKER_INTEGRATION_ENABLED = os.getenv("FORGE_RUN_DOCKER_INTEGRATION") == "1"

pytestmark = pytest.mark.skipif(
    not DOCKER_INTEGRATION_ENABLED,
    reason="set FORGE_RUN_DOCKER_INTEGRATION=1 to run real Docker replay tests",
)


@pytest.fixture(scope="module", autouse=True)
def require_docker_and_compile_image():
    if not DOCKER_INTEGRATION_ENABLED:
        yield
        return

    if shutil.which("docker") is None:
        pytest.fail("FORGE_RUN_DOCKER_INTEGRATION=1 requires the docker CLI")
    daemon = subprocess.run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if daemon.returncode != 0:
        pytest.fail(f"Docker daemon is unavailable: {daemon.stderr.strip()}")
    image = subprocess.run(
        ["docker", "image", "inspect", COMPILE_IMAGE],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if image.returncode != 0:
        pytest.fail(f"Required image {COMPILE_IMAGE!r} is unavailable")
    yield


def _run_checked(
    runtime: CompileDockerRuntime,
    session: CompileSession,
    command: str,
    *,
    workdir: str,
    expected_exit_code: int = 0,
    timeout_seconds: int = 600,
) -> CommandResult:
    result = runtime.exec(
        session,
        command,
        workdir=workdir,
        timeout_seconds=timeout_seconds,
    )
    assert result.exit_code == expected_exit_code, result.combined_output
    return result


def _record_build_command(
    manager: CompileSessionManager,
    session: CompileSession,
    command: str,
    result: CommandResult,
) -> None:
    manager.record_command(
        session,
        BuildCommandRecord(
            stage="bash",
            command=command,
            workdir="/workspace/repo",
            exit_code=result.exit_code,
        ),
    )


def _prepare_original_build(
    manager: CompileSessionManager,
    runtime: CompileDockerRuntime,
    session: CompileSession,
    *,
    failed_configure_side_effect: bool,
) -> None:
    clone_command = (
        "rm -rf -- /workspace/repo && "
        "git config --global --add safe.directory /workspace/repo && "
        f"git clone --no-checkout {REPO_URL} /workspace/repo && "
        f"git -C /workspace/repo checkout --detach {COMMIT_SHA} && "
        f'test "$(git -C /workspace/repo rev-parse HEAD)" = {COMMIT_SHA}'
    )
    _run_checked(runtime, session, clone_command, workdir="/workspace")

    configure_command = "cmake -S . -B build"
    expected_configure_exit = 0
    if failed_configure_side_effect:
        configure_command += " && false"
        expected_configure_exit = 1
    configure_result = _run_checked(
        runtime,
        session,
        configure_command,
        workdir="/workspace/repo",
        expected_exit_code=expected_configure_exit,
    )
    _record_build_command(manager, session, configure_command, configure_result)

    build_command = "cmake --build build --parallel && cp build/hello /artifacts/hello"
    build_result = _run_checked(
        runtime,
        session,
        build_command,
        workdir="/workspace/repo",
    )
    _record_build_command(manager, session, build_command, build_result)

    artifact_path = Path(session.leadagent_artifacts_dir) / "hello"
    assert artifact_path.is_file()
    assert _classify_compiled_artifact(artifact_path) == "executable"
    smoke_command = "/artifacts/hello -version"
    smoke_result = _run_checked(
        runtime,
        session,
        smoke_command,
        workdir="/workspace",
        timeout_seconds=30,
    )
    artifact_bytes = artifact_path.read_bytes()
    session.artifacts = [
        BuildArtifact(
            path=manager.relative_path(session, artifact_path),
            artifact_type="executable",
            size_bytes=len(artifact_bytes),
            source_path="/artifacts/hello",
            sha256=hashlib.sha256(artifact_bytes).hexdigest(),
            smoke_command=smoke_command,
            smoke_exit_code=smoke_result.exit_code,
            smoke_output=smoke_result.combined_output[:4000],
            smoke_output_sha256=hashlib.sha256(smoke_result.combined_output.encode()).hexdigest(),
        )
    ]
    session.verification = VerificationResult(
        status="candidate_ready",
        artifact_count=1,
    )
    session.commit_sha = COMMIT_SHA
    _write_repro_bundle(session)
    manager.save_session(session)


def _assert_no_replay_container(session: CompileSession) -> None:
    result = subprocess.run(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            "label=deerflow.compile.role=replay",
            "--filter",
            f"label=deerflow.compile.session_id={session.session_id}",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def _run_post_build_fixture(
    monkeypatch,
    *,
    case_id: str,
    repo_url: str,
    commit_sha: str,
    build_system: str,
    required_system_packages: tuple[str, ...],
    dependency_command: str | None,
    configure_arguments: tuple[str, ...],
    configure_command: str | None,
    build_command: str,
    stage_command: str,
    expected_marker: str,
    expected_artifact_names: set[str],
) -> None:
    paths = Paths()
    manager = CompileSessionManager(paths=paths, default_image=COMPILE_IMAGE)
    thread_id = f"docker-post-build-{case_id}-{uuid.uuid4().hex[:12]}"
    session = manager.create_session(
        thread_id=thread_id,
        repo_url=repo_url,
        image=COMPILE_IMAGE,
    )
    runtime = CompileDockerRuntime(manager=manager)
    ledger = ExperimentLedger.create(
        Path(session.metadata_path).parent / f"{case_id}.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"thread_id": thread_id},
    )
    policy = ExperimentPolicy(
        benchmark_id="forge-cpp-post-build-e2e",
        manifest_sha256="4" * 64,
        case_id=case_id,
        condition="non-pilot-integration",
        repetition=1,
        expected_repo_url=repo_url,
        expected_commit_sha=commit_sha,
        expected_build_system=build_system,
        compile_image=COMPILE_IMAGE,
        image_id=COMPILE_IMAGE_ID,
        model_name="deterministic-tools",
        endpoint="https://example.invalid/v1",
        credential_env="OpenAI_AK",
        request_timeout_seconds=120,
        model_max_retries=0,
        compiler_max_turns=36,
        subagent_timeout_seconds=300,
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=required_system_packages,
        cmake_arguments=(),
        configure_arguments=configure_arguments,
        environment=(),
        minimum_replay_delay_seconds=0,
    )
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))
    activate_experiment(
        thread_id=thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=policy,
    )
    try:
        runtime.create_container(session)
        manager.save_session(session)
        clone_result, _message = clone_repository_impl(
            session=session,
            repo_url=repo_url,
            max_retries=3,
        )
        assert clone_result.exit_code == 0, clone_result.combined_output
        assert session.commit_sha == commit_sha

        identify_result = agent_compile_tools.identify_build_system.func(
            runtime=SimpleNamespace(
                state={agent_compile_tools.COMPILE_SESSION_STATE_KEY: session.session_id},
                context={"thread_id": thread_id},
                config={"configurable": {}},
            ),
            tool_call_id=f"tool-identify-{case_id}",
        )
        assert identify_result.update.get("compile_terminal") is not True
        selected = manager.load_session(session.session_id, thread_id)
        assert selected.selected_build_system == build_system
        assert build_system in selected.build_system_capabilities
        assert (
            runtime.exec(
                selected,
                f"test -f /workspace/repo/{expected_marker}",
                workdir="/workspace",
                timeout_seconds=30,
            ).exit_code
            == 0
        )

        run_tool = next(tool for tool in bound_compile_tools.get_bound_compile_tools(session) if tool.name == "run_container_bash")
        if dependency_command is not None:
            dependency_setup = run_tool.func(
                command=dependency_command,
                command_role="dependency_setup",
            )
            assert "command_role=dependency_setup" in dependency_setup
            assert "exit_code=0\n" in dependency_setup, dependency_setup
        if configure_command is not None:
            configured = run_tool.func(
                command=configure_command,
                command_role="other",
            )
            assert "command_role=configure" in configured
            assert "exit_code=0\n" in configured, configured

        built = run_tool.func(
            command=build_command,
            command_role="other",
        )
        assert "command_role=build" in built
        assert "exit_code=0\n" in built, built
        staged = json.loads(
            run_tool.func(
                command=stage_command,
                command_role="other",
            )
        )
        assert staged["command"]["command_role"] == "artifact_stage"
        assert staged["automatic_submit"]["status"] == "passed"
        assert staged["automatic_submit"]["replay_status"] == "passed"

        finalized, cleanup = cleanup_and_finalize_compile_session_impl(session=session)
        assert cleanup.succeeded is True
        assert cleanup.removed is True
        assert finalized.status == "completed"
        assert finalized.selected_build_system == build_system
        assert finalized.executed_build_system == build_system
        assert {Path(artifact.path).name for artifact in finalized.artifacts} == expected_artifact_names
        assert ExperimentLedger.verify_path(ledger.path)[-1]["event"] == "delivery.completed"
        _assert_no_replay_container(finalized)
    finally:
        deactivate_experiment(thread_id)
        runtime.stop_and_remove_container(session)
        shutil.rmtree(Path(session.metadata_path).parent.parent, ignore_errors=True)


def _run_replay_scenario(monkeypatch, *, failed_configure_side_effect: bool):
    paths = Paths()
    manager = CompileSessionManager(paths=paths, default_image=COMPILE_IMAGE)
    thread_id = f"docker-replay-{uuid.uuid4().hex[:12]}"
    session = manager.create_session(
        thread_id=thread_id,
        repo_url=REPO_URL,
        image=COMPILE_IMAGE,
    )
    runtime = CompileDockerRuntime(manager=manager)
    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=runtime),
    )
    try:
        runtime.create_container(session)
        manager.save_session(session)
        assert session.image_id is not None
        assert session.image_id.startswith("sha256:")
        _prepare_original_build(
            manager,
            runtime,
            session,
            failed_configure_side_effect=failed_configure_side_effect,
        )
        script = (Path(session.leadagent_repro_dir) / "build.sh").read_text(encoding="utf-8")
        assert "cmake --build build --parallel && cp build/hello /artifacts/hello" in script
        if failed_configure_side_effect:
            assert "cmake -S . -B build && false" not in script
        original_artifact = Path(session.leadagent_artifacts_dir) / "hello"
        original_sha256 = hashlib.sha256(original_artifact.read_bytes()).hexdigest()

        attempt = verify_clean_replay_impl(session=session, timeout_seconds=180)

        assert hashlib.sha256(original_artifact.read_bytes()).hexdigest() == original_sha256
        assert attempt.cleanup_succeeded is True
        _assert_no_replay_container(session)
        return attempt
    finally:
        compile_cleanup = runtime.stop_and_remove_container(session)
        shutil.rmtree(Path(session.metadata_path).parent.parent, ignore_errors=True)
        assert compile_cleanup.succeeded is True
        assert compile_cleanup.removed is True


def test_exact_commit_clone_accepts_bind_mounted_workspace_ownership(monkeypatch):
    paths = Paths()
    manager = CompileSessionManager(paths=paths, default_image=COMPILE_IMAGE)
    thread_id = f"docker-clone-{uuid.uuid4().hex[:12]}"
    session = manager.create_session(
        thread_id=thread_id,
        repo_url=REPO_URL,
        image=COMPILE_IMAGE,
    )
    runtime = CompileDockerRuntime(manager=manager)
    policy = SimpleNamespace(expected_repo_url=REPO_URL, expected_commit_sha=COMMIT_SHA)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))
    monkeypatch.setattr(operations, "get_active_experiment", lambda active_thread_id: SimpleNamespace(policy=policy) if active_thread_id == thread_id else None)
    try:
        runtime.create_container(session)
        manager.save_session(session)

        result, _message = clone_repository_impl(
            session=session,
            repo_url=REPO_URL,
            max_retries=1,
        )

        assert result.exit_code == 0, result.combined_output
        assert session.commit_sha == COMMIT_SHA
        assert session.status == "source_ready"
    finally:
        compile_cleanup = runtime.stop_and_remove_container(session)
        shutil.rmtree(Path(session.metadata_path).parent.parent, ignore_errors=True)
        assert compile_cleanup.succeeded is True
        assert compile_cleanup.removed is True


def test_unfinished_session_finalization_removes_real_compile_container(monkeypatch):
    paths = Paths()
    manager = CompileSessionManager(paths=paths, default_image=COMPILE_IMAGE)
    thread_id = f"docker-finalize-{uuid.uuid4().hex[:12]}"
    session = manager.create_session(
        thread_id=thread_id,
        repo_url=REPO_URL,
        image=COMPILE_IMAGE,
    )
    runtime = CompileDockerRuntime(manager=manager)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))
    try:
        runtime.create_container(session)
        manager.save_session(session)
        manager.mark_session_status(session, "ready")

        finalized = finalize_unfinished_thread_sessions_impl(thread_id=thread_id)

        assert len(finalized) == 1
        reloaded = manager.load_session(session.session_id, thread_id)
        assert reloaded.status == "failed"
        assert reloaded.finalized_at is not None
        inspect = subprocess.run(
            ["docker", "inspect", session.container_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert inspect.returncode != 0
    finally:
        runtime.stop_and_remove_container(session)
        shutil.rmtree(Path(session.metadata_path).parent.parent, ignore_errors=True)


def test_build_system_mismatch_stops_before_real_compiler_delegation(monkeypatch):
    paths = Paths()
    manager = CompileSessionManager(paths=paths, default_image=COMPILE_IMAGE)
    thread_id = f"docker-build-system-gate-{uuid.uuid4().hex[:12]}"
    session = manager.create_session(
        thread_id=thread_id,
        repo_url=REPO_URL,
        image=COMPILE_IMAGE,
    )
    runtime = CompileDockerRuntime(manager=manager)
    ledger = ExperimentLedger.create(
        Path(session.metadata_path).parent / "build-system-gate.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"thread_id": thread_id},
    )
    policy = ExperimentPolicy(
        benchmark_id="forge-cpp-pilot-v4",
        manifest_sha256="1" * 64,
        case_id="cmake-mismatch-fixture",
        condition="baseline",
        repetition=1,
        expected_repo_url=REPO_URL,
        expected_commit_sha=COMMIT_SHA,
        expected_build_system="autotools",
        compile_image=COMPILE_IMAGE,
        image_id="sha256:" + "1" * 64,
        model_name="gpt-5.6-sol",
        endpoint="https://example.invalid/v1",
        credential_env="OpenAI_AK",
        request_timeout_seconds=120,
        model_max_retries=0,
        compiler_max_turns=36,
        subagent_timeout_seconds=180,
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=(),
        cmake_arguments=(),
        configure_arguments=("--disable-subunit",),
        environment=(),
        minimum_replay_delay_seconds=0,
    )
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))
    activate_experiment(
        thread_id=thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=policy,
    )
    try:
        runtime.create_container(session)
        manager.save_session(session)
        clone_result, _message = clone_repository_impl(
            session=session,
            repo_url=REPO_URL,
            max_retries=1,
        )
        assert clone_result.exit_code == 0, clone_result.combined_output

        result = agent_compile_tools.identify_build_system.func(
            runtime=SimpleNamespace(
                state={agent_compile_tools.COMPILE_SESSION_STATE_KEY: session.session_id},
                context={"thread_id": thread_id},
                config={"configurable": {}},
            ),
            tool_call_id="tool-real-build-system-mismatch",
        )

        reloaded = manager.load_session(session.session_id, thread_id)
        assert result.update["compile_terminal"] is True
        assert reloaded.build_system == "cmake"
        assert reloaded.status == "failed"
        assert reloaded.finalized_at is not None
        assert not reloaded.commands or all(command.role != "build" for command in reloaded.commands)
        inspect = subprocess.run(
            ["docker", "inspect", session.container_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert inspect.returncode != 0
        events = ledger.read()
        assert [event["event"] for event in events if event["event"] in {"build.system_checked", "protocol.deviation"}] == [
            "build.system_checked",
            "protocol.deviation",
        ]
        deviation = next(event for event in events if event["event"] == "protocol.deviation")
        assert deviation["payload"]["expected_build_system"] == "autotools"
        assert deviation["payload"]["observed_build_system"] == "cmake"
        assert deviation["payload"]["compiler_allowed"] is False
        assert deviation["payload"]["cleanup_succeeded"] is True
        assert deviation["payload"]["session_finalized"] is True
    finally:
        deactivate_experiment(thread_id)
        runtime.stop_and_remove_container(session)
        shutil.rmtree(Path(session.metadata_path).parent.parent, ignore_errors=True)


@pytest.mark.parametrize(
    ("classification", "terminal_status"),
    [
        ("model_turn_limit", "failed"),
        ("graph_recursion_limit", "failed"),
        ("compiler_wall_clock_timeout", "timed_out"),
        ("post_build_reserve_exhausted", "timed_out"),
    ],
)
def test_compiler_budget_termination_cleans_real_container_and_records_bounded_evidence(
    monkeypatch,
    classification: str,
    terminal_status: str,
):
    paths = Paths()
    manager = CompileSessionManager(paths=paths, default_image=COMPILE_IMAGE)
    thread_id = f"docker-budget-{classification}-{uuid.uuid4().hex[:8]}"
    session = manager.create_session(
        thread_id=thread_id,
        repo_url=REPO_URL,
        image=COMPILE_IMAGE,
    )
    runtime = CompileDockerRuntime(manager=manager)
    ledger = ExperimentLedger.create(
        Path(session.metadata_path).parent / "compiler-budget.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"thread_id": thread_id},
    )
    policy = ExperimentPolicy(
        benchmark_id="forge-cpp-post-v6-budget-fixture",
        manifest_sha256="6" * 64,
        case_id="compiler-budget-fixture",
        condition="non-pilot-integration",
        repetition=1,
        expected_repo_url=REPO_URL,
        expected_commit_sha=COMMIT_SHA,
        expected_build_system="cmake",
        compile_image=COMPILE_IMAGE,
        image_id=COMPILE_IMAGE_ID,
        model_name="deterministic-tools",
        endpoint="https://example.invalid/v1",
        credential_env="OpenAI_AK",
        request_timeout_seconds=120,
        model_max_retries=0,
        compiler_max_turns=36,
        subagent_timeout_seconds=300,
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=(),
        cmake_arguments=(),
        configure_arguments=(),
        environment=(),
        minimum_replay_delay_seconds=0,
        compiler_model_turn_limit=12,
        compiler_graph_recursion_limit=48,
        compiler_wall_clock_seconds=300,
        compiler_post_build_reserve_seconds=60,
    )
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))
    monkeypatch.setattr(task_tool_module, "request_cancel_background_task", lambda _task_id: True)
    monkeypatch.setattr(task_tool_module, "wait_for_background_task_shutdown", lambda _task_id, _timeout: True)
    monkeypatch.setattr(task_tool_module, "cleanup_background_task", lambda _task_id: None)
    activate_experiment(
        thread_id=thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=policy,
    )
    try:
        runtime.create_container(session)
        manager.save_session(session)
        manager.mark_session_status(session, "ready")

        worker_stopped = asyncio.run(
            task_tool_module._cancel_and_reap_task(
                task_id=f"task-{classification}",
                subagent_type="compiler",
                compile_state={agent_compile_tools.COMPILE_SESSION_STATE_KEY: session.session_id},
                thread_id=thread_id,
                terminal_status=terminal_status,
                error=f"deterministic {classification} fixture",
                shutdown_timeout_seconds=30,
            )
        )
        budget_snapshot = {
            "model_turn_limit": 12,
            "model_turn_count": 4,
            "graph_recursion_limit": 48,
            "wall_clock_limit_seconds": 300,
            "elapsed_seconds": 45.0,
            "post_build_reserve_seconds": 60,
            "post_build_started": False,
        }
        task_tool_module._record_subagent_terminal_evidence(
            thread_id=thread_id,
            task_id=f"task-{classification}",
            subagent_type="compiler",
            status=terminal_status,
            classification=classification,
            worker_stopped=worker_stopped,
            budget_snapshot=budget_snapshot,
        )

        assert worker_stopped is True
        reloaded = manager.load_session(session.session_id, thread_id)
        assert reloaded.status == terminal_status
        assert reloaded.finalized_at is not None
        inspect = subprocess.run(
            ["docker", "inspect", session.container_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert inspect.returncode != 0
        terminal_events = [event for event in ledger.read() if event["event"] == "agent.subagent_terminated"]
        assert len(terminal_events) == 1
        assert terminal_events[0]["payload"]["classification"] == classification
        assert terminal_events[0]["payload"]["budget_snapshot"] == budget_snapshot
    finally:
        deactivate_experiment(thread_id)
        runtime.stop_and_remove_container(session)
        shutil.rmtree(Path(session.metadata_path).parent.parent, ignore_errors=True)


def test_missing_frozen_arguments_stop_before_real_build_and_replay(monkeypatch):
    paths = Paths()
    manager = CompileSessionManager(paths=paths, default_image=COMPILE_IMAGE)
    thread_id = f"docker-build-argument-gate-{uuid.uuid4().hex[:12]}"
    session = manager.create_session(
        thread_id=thread_id,
        repo_url=REPO_URL,
        image=COMPILE_IMAGE,
    )
    runtime = CompileDockerRuntime(manager=manager)
    ledger = ExperimentLedger.create(
        Path(session.metadata_path).parent / "build-argument-gate.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"thread_id": thread_id},
    )
    policy = ExperimentPolicy(
        benchmark_id="forge-cpp-post-v6-argument-gate",
        manifest_sha256="5" * 64,
        case_id="cmake-argument-fixture",
        condition="non-pilot-integration",
        repetition=1,
        expected_repo_url=REPO_URL,
        expected_commit_sha=COMMIT_SHA,
        expected_build_system="cmake",
        compile_image=COMPILE_IMAGE,
        image_id=COMPILE_IMAGE_ID,
        model_name="deterministic-tools",
        endpoint="https://example.invalid/v1",
        credential_env="OpenAI_AK",
        request_timeout_seconds=120,
        model_max_retries=0,
        compiler_max_turns=36,
        subagent_timeout_seconds=300,
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=(),
        cmake_arguments=("-DBUILD_TESTING=OFF",),
        configure_arguments=(),
        environment=(),
        minimum_replay_delay_seconds=0,
    )
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))
    activate_experiment(
        thread_id=thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=policy,
    )
    try:
        runtime.create_container(session)
        manager.save_session(session)
        clone_result, _message = clone_repository_impl(
            session=session,
            repo_url=REPO_URL,
            max_retries=1,
        )
        assert clone_result.exit_code == 0, clone_result.combined_output

        identify_result = agent_compile_tools.identify_build_system.func(
            runtime=SimpleNamespace(
                state={agent_compile_tools.COMPILE_SESSION_STATE_KEY: session.session_id},
                context={"thread_id": thread_id},
                config={"configurable": {}},
            ),
            tool_call_id="tool-real-build-argument-gate",
        )
        assert identify_result.update.get("compile_terminal") is not True

        run_tool = next(tool for tool in bound_compile_tools.get_bound_compile_tools(session) if tool.name == "run_container_bash")
        configured = run_tool.func(
            command="cmake -S . -B build",
            command_role="other",
        )
        rejected = run_tool.func(
            command="cmake --build build -j2",
            command_role="other",
        )

        assert "command_role=configure" in configured
        assert "exit_code=0\n" in configured, configured
        assert "exit_code=126 (Policy rejected)" in rejected
        assert "classification=cmake_arguments_not_observed" in rejected
        reloaded = manager.load_session(session.session_id, thread_id)
        assert reloaded.post_build_supporting_command_id is None
        assert reloaded.replay_attempts == []
        assert (
            runtime.exec(
                reloaded,
                "test ! -e build/hello",
                workdir="/workspace/repo",
                timeout_seconds=30,
            ).exit_code
            == 0
        )
        _assert_no_replay_container(reloaded)

        events = ledger.read()
        deviation = next(event for event in events if event["event"] == "protocol.deviation")
        assert deviation["payload"]["phase"] == "pre_build"
        assert deviation["payload"]["classification"] == "cmake_arguments_not_observed"
        assert deviation["payload"]["command_executed"] is False
    finally:
        deactivate_experiment(thread_id)
        runtime.stop_and_remove_container(session)
        shutil.rmtree(Path(session.metadata_path).parent.parent, ignore_errors=True)


def test_post_build_handoff_corrects_role_and_auto_submits_cmake_fixture(monkeypatch):
    paths = Paths()
    manager = CompileSessionManager(paths=paths, default_image=COMPILE_IMAGE)
    thread_id = f"docker-post-build-handoff-{uuid.uuid4().hex[:12]}"
    session = manager.create_session(
        thread_id=thread_id,
        repo_url=REPO_URL,
        image=COMPILE_IMAGE,
    )
    runtime = CompileDockerRuntime(manager=manager)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))
    try:
        runtime.create_container(session)
        manager.save_session(session)
        clone_result, _message = clone_repository_impl(
            session=session,
            repo_url=REPO_URL,
            max_retries=1,
        )
        assert clone_result.exit_code == 0, clone_result.combined_output
        primary, detected, _suggested = inspect_build_system_impl(session=session)
        assert primary == "cmake"
        assert ("cmake", "CMakeLists.txt") in detected

        run_tool = next(tool for tool in bound_compile_tools.get_bound_compile_tools(session) if tool.name == "run_container_bash")
        configure_result = run_tool.func(
            command="cmake -S . -B build",
            command_role="other",
        )
        assert "command_role=configure" in configure_result
        build_result = run_tool.func(
            command="cmake --build build --parallel",
            command_role="other",
        )
        assert "command_role=build" in build_result

        post_build = manager.load_session(session.session_id, thread_id)
        assert post_build.post_build_supporting_command_id is not None
        rejected = run_tool.func(
            command="cmake -S . -B build-again",
            command_role="other",
        )
        assert "exit_code=126 (Policy rejected)" in rejected

        staged = json.loads(
            run_tool.func(
                command="cp build/hello /artifacts/hello",
                command_role="other",
            )
        )
        assert staged["command"]["command_role"] == "artifact_stage"
        assert staged["automatic_submit"]["status"] == "passed"
        assert staged["automatic_submit"]["replay_status"] == "passed"

        finalized, cleanup = cleanup_and_finalize_compile_session_impl(session=session)
        assert cleanup.succeeded is True
        assert cleanup.removed is True
        assert finalized.status == "completed"
        assert finalized.finalized_at is not None
        assert len(finalized.artifacts) == 1
        _assert_no_replay_container(finalized)
    finally:
        runtime.stop_and_remove_container(session)
        shutil.rmtree(Path(session.metadata_path).parent.parent, ignore_errors=True)


def test_post_build_handoff_auto_submits_compound_build_and_stage(monkeypatch):
    paths = Paths()
    manager = CompileSessionManager(paths=paths, default_image=COMPILE_IMAGE)
    thread_id = f"docker-post-build-compound-{uuid.uuid4().hex[:12]}"
    session = manager.create_session(
        thread_id=thread_id,
        repo_url=REPO_URL,
        image=COMPILE_IMAGE,
    )
    runtime = CompileDockerRuntime(manager=manager)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))
    try:
        runtime.create_container(session)
        manager.save_session(session)
        clone_result, _message = clone_repository_impl(
            session=session,
            repo_url=REPO_URL,
            max_retries=1,
        )
        assert clone_result.exit_code == 0, clone_result.combined_output
        primary, _detected, _suggested = inspect_build_system_impl(session=session)
        assert primary == "cmake"

        run_tool = next(tool for tool in bound_compile_tools.get_bound_compile_tools(session) if tool.name == "run_container_bash")
        configured = run_tool.func(
            command="cmake -S . -B build",
            command_role="other",
        )
        assert "command_role=configure" in configured
        submitted = json.loads(
            run_tool.func(
                command="cmake --build build --parallel && cp build/hello /artifacts/hello",
                command_role="other",
            )
        )
        assert submitted["command"]["command_role"] == "build"
        assert submitted["automatic_submit"]["status"] == "passed"
        assert submitted["automatic_submit"]["replay_status"] == "passed"

        finalized, cleanup = cleanup_and_finalize_compile_session_impl(session=session)
        assert cleanup.succeeded is True
        assert cleanup.removed is True
        assert finalized.status == "completed"
        assert {Path(artifact.path).name for artifact in finalized.artifacts} == {"hello"}
        _assert_no_replay_container(finalized)
    finally:
        runtime.stop_and_remove_container(session)
        shutil.rmtree(Path(session.metadata_path).parent.parent, ignore_errors=True)


def test_post_build_handoff_auto_submits_make_fixture(monkeypatch):
    _run_post_build_fixture(
        monkeypatch,
        case_id="hiredis-make",
        repo_url=HIREDIS_REPO_URL,
        commit_sha=HIREDIS_COMMIT_SHA,
        build_system="make",
        required_system_packages=(),
        dependency_command=None,
        configure_arguments=(),
        configure_command=None,
        build_command="make -j2",
        stage_command="cp libhiredis.a libhiredis.so /artifacts/",
        expected_marker="Makefile",
        expected_artifact_names={"libhiredis.a", "libhiredis.so"},
    )


def test_post_build_handoff_detects_source_autotools_and_auto_submits(monkeypatch):
    _run_post_build_fixture(
        monkeypatch,
        case_id="libcheck-autotools",
        repo_url=LIBCHECK_REPO_URL,
        commit_sha=LIBCHECK_COMMIT_SHA,
        build_system="autotools",
        required_system_packages=("texinfo",),
        dependency_command="apt-get update && apt-get install -y --no-install-recommends texinfo",
        configure_arguments=("--disable-subunit",),
        configure_command="autoreconf -fi && ./configure --disable-subunit",
        build_command="make -j2",
        stage_command="cp src/.libs/libcheck.a /artifacts/libcheck.a",
        expected_marker="configure.ac",
        expected_artifact_names={"libcheck.a"},
    )


def test_clean_replay_rebuilds_pinned_cmake_fixture_in_fresh_container(monkeypatch):
    attempt = _run_replay_scenario(
        monkeypatch,
        failed_configure_side_effect=False,
    )

    assert attempt.status == "passed"
    assert attempt.failure_classification is None
    assert attempt.exit_code == 0
    assert len(attempt.artifacts) == 1
    comparison = attempt.artifacts[0]
    assert comparison.path == "hello"
    assert comparison.type_matches is True
    assert comparison.size_matches is True
    assert comparison.sha256_matches is True
    assert comparison.smoke_matches is True
    assert comparison.passed is True


def test_clean_replay_rejects_success_recipe_dependent_on_failed_configure_side_effect(monkeypatch):
    attempt = _run_replay_scenario(
        monkeypatch,
        failed_configure_side_effect=True,
    )

    assert attempt.status == "failed"
    assert attempt.failure_classification == "recipe_execution_failed"
    assert attempt.exit_code not in {None, 0}
    assert not any(check.name == "artifact_set" for check in attempt.checks)
