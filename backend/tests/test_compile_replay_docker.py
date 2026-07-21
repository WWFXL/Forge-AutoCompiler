"""Opt-in Docker integration coverage for clean compile replay.

Run explicitly with FORGE_RUN_DOCKER_INTEGRATION=1 after building
the autocompiler:gcc13 image. The default backend test suite skips this file.
"""

from __future__ import annotations

import hashlib
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
from deerflow.compile.operations import CompileOperationsServices, _classify_compiled_artifact, _write_repro_bundle, clone_repository_impl, finalize_unfinished_thread_sessions_impl, verify_clean_replay_impl
from deerflow.compile.schemas import BuildArtifact, BuildCommandRecord, CommandResult, CompileSession, VerificationResult
from deerflow.config.paths import Paths
from deerflow.tools.builtins import agent_compile_tools

REPO_URL = "https://github.com/MattClarkson/CMakeHelloWorld.git"
COMMIT_SHA = "6fda0b169299b1241ed883c8d4af8519da30ce52"
COMPILE_IMAGE = "autocompiler:gcc13"
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
