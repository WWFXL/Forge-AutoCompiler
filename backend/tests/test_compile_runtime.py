import hashlib
import json
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow.compile import operations
from deerflow.compile.docker_runtime import DEFAULT_NETWORK, CompileDockerRuntime, ContainerCleanupResult, ReplayContainerHandle, RuntimeConfig
from deerflow.compile.evidence import ExperimentLedger, ExperimentPolicy, activate_experiment, deactivate_experiment, new_evidence_id
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.operations import CompileOperationsServices, _classify_compiled_artifact, _write_repro_bundle, clone_repository_impl, submit_build_result_impl, verify_clean_replay_impl
from deerflow.compile.paths import (
    get_compile_sessions_root,
    get_host_replay_artifacts_dir,
    get_host_replay_logs_dir,
    get_host_replay_recipe_dir,
    get_host_replay_workspace_dir,
    get_host_session_dir,
    get_host_workspace_dir,
    get_metadata_path,
    get_replay_artifacts_dir,
    get_replay_logs_dir,
    get_replay_recipe_dir,
    get_replay_workspace_dir,
    get_session_dir,
)
from deerflow.compile.schemas import BuildArtifact, BuildCommandRecord, CommandResult, CompileSession, ReplayArtifactComparison, ReplayVerificationResult, VerificationCheck, VerificationResult
from deerflow.config.paths import Paths
from deerflow.tools import bound_compile_tools

VALID_IMAGE_ID = f"sha256:{'1' * 64}"


@pytest.fixture(autouse=True)
def isolate_compile_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace_root = tmp_path / "workspace"
    monkeypatch.setenv("DEER_FLOW_WORKSPACE_ROOT", str(workspace_root))
    monkeypatch.setenv("DEER_FLOW_HOST_WORKSPACE_ROOT", str(workspace_root))


def make_test_paths(tmp_path: Path, *, host_workspace_root: str | None = None) -> Paths:
    return Paths(
        base_dir=tmp_path / ".deer-flow",
        workspace_root=tmp_path / "service-workspace",
        host_workspace_root=host_workspace_root or str(tmp_path / "host-workspace"),
    )


def add_replayable_build_command(session: CompileSession, command: str = "cmake --build build") -> None:
    session.commands.append(
        BuildCommandRecord(
            stage="bash",
            command=command,
            workdir="/workspace/repo",
            exit_code=0,
        )
    )


@pytest.mark.parametrize(
    ("command", "expected", "matches"),
    [
        ("cmake -S . -B build -DA=1 -DB=2", ("-DA=1", "-DB=2"), True),
        ("cmake -S . -B build -DB=2 -DA=1", ("-DA=1", "-DB=2"), False),
        ("./configure --prefix=/usr --disable-shared", ("--prefix=/usr",), True),
        ("cmake -S . -B build", ("-DA=1",), False),
    ],
)
def test_benchmark_arguments_must_be_observed_in_declared_order(
    command: str,
    expected: tuple[str, ...],
    matches: bool,
) -> None:
    assert operations._command_contains_arguments(command, expected) is matches


def test_inspect_build_system_persists_all_repository_capabilities(tmp_path: Path, monkeypatch) -> None:
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-multi-build-system",
        repo_url="https://example.com/repo.git",
    )
    repo_dir = Path(session.leadagent_repo_dir)
    repo_dir.mkdir(parents=True)
    for marker in ("CMakeLists.txt", "Makefile", "configure"):
        (repo_dir / marker).write_text("fixture\n", encoding="utf-8")
    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=SimpleNamespace()),
    )

    primary, detected, _suggested = operations.inspect_build_system_impl(session=session)

    reloaded = manager.load_session(session.session_id, session.thread_id)
    assert primary == "cmake"
    assert detected == [
        ("cmake", "CMakeLists.txt"),
        ("make", "Makefile"),
        ("autotools", "configure"),
    ]
    assert reloaded.build_system == "cmake"
    assert reloaded.build_system_capabilities == ["cmake", "make", "autotools"]
    assert reloaded.selected_build_system is None
    assert reloaded.executed_build_system is None


@pytest.mark.parametrize(
    ("marker", "first_suggestion"),
    [
        ("configure.ac", "autoreconf -fi && ./configure"),
        ("configure.in", "autoreconf -fi && ./configure"),
        ("autogen.sh", "chmod +x ./autogen.sh && ./autogen.sh"),
    ],
)
def test_inspect_build_system_detects_source_autotools_markers(
    tmp_path: Path,
    monkeypatch,
    marker: str,
    first_suggestion: str,
) -> None:
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id=f"thread-autotools-{marker.replace('.', '-')}",
        repo_url="https://example.com/repo.git",
    )
    repo_dir = Path(session.leadagent_repo_dir)
    repo_dir.mkdir(parents=True)
    (repo_dir / marker).write_text("fixture\n", encoding="utf-8")
    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=SimpleNamespace()),
    )

    primary, detected, suggested = operations.inspect_build_system_impl(session=session)

    assert primary == "autotools"
    assert detected == [("autotools", marker)]
    assert suggested[0] == first_suggestion
    assert manager.load_session(session.session_id, session.thread_id).build_system_capabilities == ["autotools"]


@pytest.mark.parametrize(
    ("command", "declared", "effective", "inferred"),
    [
        ("cmake --build build -j2", "other", "build", "build"),
        ("make -j2", "other", "build", "build"),
        ("ninja -C build", "other", "build", "build"),
        ("cmake -S . -B build", "other", "configure", "configure"),
        ("autoreconf -fi && ./configure", "other", "configure", "configure"),
        ("cp build/libexample.a /artifacts/", "other", "artifact_stage", "artifact_stage"),
        ("cmake --install build --prefix /artifacts", "other", "artifact_stage", "artifact_stage"),
        ("make install DESTDIR=/artifacts", "other", "artifact_stage", "artifact_stage"),
        ("apt-get install -y texinfo", "other", "dependency_setup", "dependency_setup"),
        ("make -j2 && cp libexample.a /artifacts/", "other", "build", "build"),
        ("bash -lc 'apt-get install -y texinfo && make -j2 && cp libexample.a /artifacts/'", "other", "build", "build"),
        ("make clean && cp old.a /artifacts/", "other", "artifact_stage", "artifact_stage"),
        ("make clean", "other", "other", None),
        ("ninja -C build clean", "build", "other", None),
        ("cmake --build build --target clean", "build", "other", None),
        ("make clean all", "other", "build", "build"),
        ("printf 'not a build'", "build", "other", None),
        ("find build -type f", "smoke", "smoke", None),
    ],
)
def test_command_role_is_resolved_from_server_side_evidence(
    command: str,
    declared: str,
    effective: str,
    inferred: str | None,
) -> None:
    assert operations.resolve_command_role(command, declared) == (effective, inferred)


def test_compound_command_analysis_retains_every_control_plane_role() -> None:
    assert operations.infer_command_roles("apt-get install -y texinfo && make -j2 && cp lib.a /artifacts/") == {
        "dependency_setup",
        "build",
        "artifact_stage",
    }
    assert operations.infer_command_roles("make clean && cp old.a /artifacts/") == {
        "housekeeping",
        "artifact_stage",
    }
    assert operations.infer_command_roles("bash -lc 'apt-get install -y texinfo && make -j2 && cp lib.a /artifacts/'") == {
        "dependency_setup",
        "build",
        "artifact_stage",
    }


def test_successful_mislabelled_build_enters_persisted_post_build_fence(tmp_path: Path, monkeypatch) -> None:
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-post-build-fence",
        repo_url="https://example.com/repo.git",
    )
    runtime_calls: list[str] = []

    def fake_exec(_session, command, **kwargs):
        runtime_calls.append(command)
        return CommandResult(
            exit_code=0,
            stdout="built\n",
            stderr="",
            combined_output="built\n",
            log_path=kwargs.get("log_path"),
        )

    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=SimpleNamespace(exec=fake_exec)),
    )

    build_result, _message, build_record = bound_compile_tools._run_container_bash_impl(
        session=session,
        command="cmake --build build -j2",
        command_role="other",
    )
    rejected_result, _rejected_message, rejected_record = bound_compile_tools._run_container_bash_impl(
        session=session,
        command="cmake -S . -B build-again",
        command_role="other",
    )

    reloaded = manager.load_session(session.session_id, session.thread_id)
    assert build_result.exit_code == 0
    assert build_record.role == "build"
    assert reloaded.post_build_supporting_command_id == build_record.command_id
    assert reloaded.post_build_commands_remaining == 2
    assert rejected_result.exit_code == 126
    assert rejected_record.role == "configure"
    assert rejected_record.termination == "policy_rejected"
    assert runtime_calls == ["cmake --build build -j2"]


@pytest.mark.parametrize(
    ("commands", "supporting_command_id", "expected"),
    [
        (
            [BuildCommandRecord(stage="bash", command="cmake --build build -j2", workdir="/workspace/repo", command_id="build", role="build", exit_code=0)],
            "build",
            "cmake",
        ),
        (
            [BuildCommandRecord(stage="bash", command="cmake -S . -B build && make -C build -j2", workdir="/workspace/repo", command_id="build", role="build", exit_code=0)],
            "build",
            "cmake",
        ),
        (
            [BuildCommandRecord(stage="bash", command="make -j2", workdir="/workspace/repo", command_id="build", role="build", exit_code=0)],
            "build",
            "make",
        ),
        (
            [
                BuildCommandRecord(stage="bash", command="./configure --disable-shared", workdir="/workspace/repo", command_id="configure", role="configure", exit_code=0),
                BuildCommandRecord(stage="bash", command="make -j2", workdir="/workspace/repo", command_id="build", role="build", exit_code=0),
            ],
            "build",
            "autotools",
        ),
    ],
)
def test_submit_gate_infers_executed_build_system_from_successful_commands(
    commands: list[BuildCommandRecord],
    supporting_command_id: str,
    expected: str,
) -> None:
    assert operations._infer_executed_build_system(commands, supporting_command_id) == expected


def test_submit_gate_does_not_treat_build_system_name_as_command_evidence() -> None:
    commands = [
        BuildCommandRecord(
            stage="bash",
            command="printf 'make build finished'",
            workdir="/workspace/repo",
            command_id="build",
            role="build",
            exit_code=0,
        )
    ]

    assert operations._infer_executed_build_system(commands, "build") is None


def test_submit_gate_rejects_observed_build_system_mismatch(tmp_path: Path) -> None:
    thread_id = "thread-build-system-submit-gate"
    session = CompileSession(
        session_id="session-build-system-submit-gate",
        thread_id=thread_id,
        repo_url="https://example.com/repo.git",
        branch=None,
        image="autocompiler:gcc13",
        status="inspected",
        build_system="cmake",
        build_system_capabilities=["cmake", "make"],
        selected_build_system="cmake",
        metadata_path="session.json",
        leadagent_repo_dir="workspace/repo",
        leadagent_artifacts_dir="artifacts",
        leadagent_logs_dir="logs",
        leadagent_repro_dir="repro",
        commands=[
            BuildCommandRecord(
                stage="bash",
                command="make -j2",
                workdir="/workspace/repo",
                command_id="command-build",
                role="build",
                exit_code=0,
            )
        ],
    )
    ledger = ExperimentLedger.create(
        tmp_path / "build-system-submit-gate.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"thread_id": thread_id},
    )
    policy = ExperimentPolicy(
        benchmark_id="forge-cpp-pilot-v4",
        manifest_sha256="1" * 64,
        case_id="fixture",
        condition="baseline",
        repetition=1,
        expected_repo_url=session.repo_url,
        expected_commit_sha="2" * 40,
        expected_build_system="cmake",
        compile_image=session.image,
        image_id=VALID_IMAGE_ID,
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
        configure_arguments=(),
        environment=(),
        minimum_replay_delay_seconds=0,
    )
    activate_experiment(
        thread_id=thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=policy,
    )
    try:
        passed, failures, executed_build_system = operations._experiment_submit_constraints(
            session,
            "command-build",
        )
    finally:
        deactivate_experiment(thread_id)

    assert passed is False
    assert failures == ["build_system_mismatch"]
    assert executed_build_system == "make"
    deviation = ledger.read()[-1]
    assert deviation["event"] == "protocol.deviation"
    assert deviation["payload"]["phase"] == "submit"
    assert deviation["payload"]["selected_build_system"] == "cmake"
    assert deviation["payload"]["observed_build_system"] == "make"
    assert deviation["payload"]["submit_allowed"] is False


def test_submit_gate_rejects_unproven_build_system(tmp_path: Path) -> None:
    thread_id = "thread-build-system-unproven"
    session = CompileSession(
        session_id="session-build-system-unproven",
        thread_id=thread_id,
        repo_url="https://example.com/repo.git",
        branch=None,
        image="autocompiler:gcc13",
        status="inspected",
        build_system="cmake",
        build_system_capabilities=["cmake"],
        selected_build_system="cmake",
        commands=[BuildCommandRecord(stage="bash", command="ninja -C build", workdir="/workspace/repo", command_id="command-build", role="build", exit_code=0)],
    )
    ledger = ExperimentLedger.create(
        tmp_path / "build-system-unproven.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"thread_id": thread_id},
    )
    policy = ExperimentPolicy(
        benchmark_id="forge-cpp-pilot-v4",
        manifest_sha256="1" * 64,
        case_id="fixture",
        condition="baseline",
        repetition=1,
        expected_repo_url=session.repo_url,
        expected_commit_sha="2" * 40,
        expected_build_system="cmake",
        compile_image=session.image,
        image_id=VALID_IMAGE_ID,
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
        configure_arguments=(),
        environment=(),
        minimum_replay_delay_seconds=0,
    )
    activate_experiment(
        thread_id=thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=policy,
    )
    try:
        passed, failures, executed_build_system = operations._experiment_submit_constraints(session, "command-build")
    finally:
        deactivate_experiment(thread_id)

    assert passed is False
    assert failures == ["build_system_unproven"]
    assert executed_build_system is None
    assert ledger.read()[-1]["payload"]["classification"] == "build_system_unproven"


def install_passed_replay_stub(monkeypatch) -> None:
    def fake_verify_clean_replay(*, session: CompileSession, timeout_seconds: int | None = None) -> ReplayVerificationResult:
        del timeout_seconds
        session.image_id = session.image_id or VALID_IMAGE_ID
        recipe_path = Path(session.leadagent_repro_dir) / "build.sh"
        result = ReplayVerificationResult(
            attempt_id="stubbed-pass",
            status="passed",
            image=session.image,
            image_id=session.image_id,
            commit_sha=session.commit_sha or "",
            recipe_sha256=hashlib.sha256(recipe_path.read_bytes()).hexdigest(),
            cleanup_succeeded=True,
        )
        session.replay_attempts.append(result)
        return result

    monkeypatch.setattr(operations, "verify_clean_replay_impl", fake_verify_clean_replay)


class FakeReplayRuntime:
    def __init__(
        self,
        manager: CompileSessionManager,
        *,
        build_exit_code: int = 0,
        cleanup_result: ContainerCleanupResult | None = None,
        build_exception: BaseException | None = None,
        mutate_replay_artifact=None,
        smoke_output: str = "Hello Matt!\n",
    ):
        self.manager = manager
        self.config = SimpleNamespace(replay_timeout_seconds=30)
        self.build_exit_code = build_exit_code
        self.cleanup_result = cleanup_result or ContainerCleanupResult(succeeded=True, stopped=True, removed=True)
        self.build_exception = build_exception
        self.mutate_replay_artifact = mutate_replay_artifact
        self.smoke_output = smoke_output
        self.attempt_id: str | None = None
        self.events: list[tuple] = []

    def replay_container_name(self, session: CompileSession, attempt_id: str) -> str:
        del session
        return f"replay-{attempt_id}"

    def create_replay_container(self, session: CompileSession, *, attempt_id: str, timeout_seconds: int) -> ReplayContainerHandle:
        self.attempt_id = attempt_id
        self.events.append(("create", attempt_id, timeout_seconds))
        assert (get_replay_recipe_dir(session.session_id, session.thread_id, attempt_id, self.manager.paths) / "build.sh").is_file()
        assert not any(get_replay_workspace_dir(session.session_id, session.thread_id, attempt_id, self.manager.paths).iterdir())
        assert not any(get_replay_artifacts_dir(session.session_id, session.thread_id, attempt_id, self.manager.paths).iterdir())
        assert not any(get_replay_logs_dir(session.session_id, session.thread_id, attempt_id, self.manager.paths).iterdir())
        return ReplayContainerHandle(container_id="replay-container-id", container_name=f"replay-{attempt_id}", image_id=session.image_id or "")

    def exec_replay_container(
        self,
        session: CompileSession,
        handle: ReplayContainerHandle,
        command: str = "bash /repro/build.sh",
        workdir: str = "/workspace",
        timeout_seconds: int | None = None,
        log_path: str | None = None,
    ) -> CommandResult:
        del handle, workdir
        self.events.append(("exec", command, timeout_seconds, log_path))
        if command == "bash /repro/build.sh":
            if self.build_exception is not None:
                raise self.build_exception
            if self.build_exit_code == 0:
                assert self.attempt_id is not None
                original_dir = Path(session.leadagent_artifacts_dir)
                replay_dir = get_replay_artifacts_dir(session.session_id, session.thread_id, self.attempt_id, self.manager.paths)
                for original_path in original_dir.rglob("*"):
                    if not original_path.is_file():
                        continue
                    replay_path = replay_dir / original_path.relative_to(original_dir)
                    replay_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(original_path, replay_path)
                if self.mutate_replay_artifact is not None:
                    self.mutate_replay_artifact(replay_dir / "hello")
            return CommandResult(
                exit_code=self.build_exit_code,
                stdout="",
                stderr="recipe failed\n" if self.build_exit_code else "",
                combined_output="recipe failed\n" if self.build_exit_code else "",
                log_path=log_path,
            )
        return CommandResult(
            exit_code=0,
            stdout=self.smoke_output,
            stderr="",
            combined_output=self.smoke_output,
            log_path=log_path,
        )

    def stop_and_remove_replay_container(
        self,
        session: CompileSession,
        handle: ReplayContainerHandle | None = None,
        *,
        container_id: str | None = None,
        container_name: str | None = None,
    ) -> ContainerCleanupResult:
        del session
        self.events.append(("cleanup", handle.container_id if handle else container_id, handle.container_name if handle else container_name))
        return self.cleanup_result


def make_replay_ready_session(tmp_path: Path, *, commands: list[BuildCommandRecord] | None = None) -> tuple[CompileSessionManager, CompileSession]:
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-clean-replay", repo_url="https://example.com/repo.git")
    session.commit_sha = "a" * 40
    session.image_id = VALID_IMAGE_ID
    if commands is None:
        add_replayable_build_command(session, "cmake --build build && cp build/hello /artifacts/hello")
    else:
        session.commands = commands
    _write_repro_bundle(session)
    artifact_path = Path(session.leadagent_artifacts_dir) / "hello"
    write_elf(artifact_path, 2)
    artifact_bytes = artifact_path.read_bytes()
    session.artifacts = [
        BuildArtifact(
            path=manager.relative_path(session, artifact_path),
            artifact_type="executable",
            size_bytes=len(artifact_bytes),
            source_path="/artifacts/hello",
            sha256=hashlib.sha256(artifact_bytes).hexdigest(),
            smoke_command="/artifacts/hello -version",
            smoke_exit_code=0,
            smoke_output="Hello Matt!\n",
            smoke_output_sha256=hashlib.sha256(b"Hello Matt!\n").hexdigest(),
        )
    ]
    session.verification = VerificationResult(status="candidate_ready", artifact_count=1)
    manager.save_session(session)
    return manager, session


def write_elf(path: Path, elf_type: int, *, has_interpreter: bool = False, has_entry_point: bool | None = None) -> None:
    header = bytearray(64)
    header[:4] = b"\x7fELF"
    header[4] = 2  # ELF64
    header[5] = 1  # little-endian
    header[6] = 1  # ELF version
    header[16:18] = elf_type.to_bytes(2, byteorder="little")
    header[18:20] = (62).to_bytes(2, byteorder="little")  # x86-64
    header[20:24] = (1).to_bytes(4, byteorder="little")
    header[52:54] = (64).to_bytes(2, byteorder="little")
    if elf_type == 1:
        header[40:48] = (64).to_bytes(8, byteorder="little")
        header[58:60] = (64).to_bytes(2, byteorder="little")
        header[60:62] = (3).to_bytes(2, byteorder="little")
        header[62:64] = (2).to_bytes(2, byteorder="little")
        null_section = bytearray(64)
        text_section = bytearray(64)
        text_section[4:8] = (1).to_bytes(4, byteorder="little")
        text_section[24:32] = (256).to_bytes(8, byteorder="little")
        text_section[32:40] = (1).to_bytes(8, byteorder="little")
        names = b"\0.text\0.shstrtab\0"
        name_section = bytearray(64)
        name_section[4:8] = (3).to_bytes(4, byteorder="little")
        name_section[24:32] = (257).to_bytes(8, byteorder="little")
        name_section[32:40] = len(names).to_bytes(8, byteorder="little")
        header.extend(null_section + text_section + name_section + b"\x90" + names)
    else:
        if has_entry_point is None:
            has_entry_point = elf_type == 2 or has_interpreter
        if has_entry_point:
            header[24:32] = (0x1000).to_bytes(8, byteorder="little")
        dynamic_payload = b"\0" * 16 if elf_type == 3 and not has_interpreter and not has_entry_point else b""
        interpreter_payload = b"/lib64/ld-linux-x86-64.so.2\0" if has_interpreter else b""
        program_count = 1 + int(bool(dynamic_payload or interpreter_payload))
        file_size = 64 + program_count * 56 + len(dynamic_payload) + len(interpreter_payload)
        header[32:40] = (64).to_bytes(8, byteorder="little")
        header[54:56] = (56).to_bytes(2, byteorder="little")
        header[56:58] = program_count.to_bytes(2, byteorder="little")
        load_header = bytearray(56)
        load_header[:4] = (1).to_bytes(4, byteorder="little")
        load_header[32:40] = file_size.to_bytes(8, byteorder="little")
        load_header[40:48] = file_size.to_bytes(8, byteorder="little")
        header.extend(load_header)
        if has_interpreter:
            interpreter_header = bytearray(56)
            interpreter_header[:4] = (3).to_bytes(4, byteorder="little")
            interpreter_header[8:16] = (64 + program_count * 56).to_bytes(8, byteorder="little")
            interpreter_header[32:40] = len(interpreter_payload).to_bytes(8, byteorder="little")
            interpreter_header[40:48] = len(interpreter_payload).to_bytes(8, byteorder="little")
            header.extend(interpreter_header)
        elif dynamic_payload:
            dynamic_header = bytearray(56)
            dynamic_header[:4] = (2).to_bytes(4, byteorder="little")
            dynamic_header[8:16] = (64 + program_count * 56).to_bytes(8, byteorder="little")
            dynamic_header[32:40] = len(dynamic_payload).to_bytes(8, byteorder="little")
            dynamic_header[40:48] = len(dynamic_payload).to_bytes(8, byteorder="little")
            header.extend(dynamic_header)
        header.extend(dynamic_payload + interpreter_payload)
    path.write_bytes(header)


def write_empty_elf(path: Path, elf_type: int) -> None:
    header = bytearray(64)
    header[:4] = b"\x7fELF"
    header[4:7] = bytes((2, 1, 1))
    header[16:18] = elf_type.to_bytes(2, byteorder="little")
    header[18:20] = (62).to_bytes(2, byteorder="little")
    header[20:24] = (1).to_bytes(4, byteorder="little")
    header[52:54] = (64).to_bytes(2, byteorder="little")
    if elf_type == 1:
        header[40:48] = (64).to_bytes(8, byteorder="little")
        header[58:60] = (64).to_bytes(2, byteorder="little")
        header[60:62] = (1).to_bytes(2, byteorder="little")
        header.extend(bytearray(64))
    else:
        header[24:32] = (0x1000).to_bytes(8, byteorder="little")
        header[32:40] = (64).to_bytes(8, byteorder="little")
        header[54:56] = (56).to_bytes(2, byteorder="little")
        header[56:58] = (1).to_bytes(2, byteorder="little")
        load_header = bytearray(56)
        load_header[:4] = (1).to_bytes(4, byteorder="little")
        header.extend(load_header)
    path.write_bytes(header)


def write_static_archive(path: Path) -> None:
    object_path = path.with_suffix(".member.o")
    write_elf(object_path, 1)
    payload = object_path.read_bytes()
    object_path.unlink()
    member_header = b"".join(
        [
            b"member.o/".ljust(16),
            b"0".ljust(12),
            b"0".ljust(6),
            b"0".ljust(6),
            b"100644".ljust(8),
            str(len(payload)).encode("ascii").ljust(10),
            b"`\n",
        ]
    )
    path.write_bytes(b"!<arch>\n" + member_header + payload + (b"\n" if len(payload) % 2 else b""))


def test_create_session_creates_expected_directory_layout(tmp_path: Path):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))

    session = manager.create_session(thread_id="thread-1", repo_url="https://example.com/repo.git", branch="main")

    session_dir = get_session_dir(session.session_id, session.thread_id, manager.paths)
    assert session_dir.exists()
    assert (session_dir / "workspace").exists()
    assert (session_dir / "artifacts").exists()
    assert (session_dir / "logs").exists()
    assert (session_dir / "repro").exists()
    assert get_metadata_path(session.session_id, session.thread_id, manager.paths).exists()


def test_create_session_under_compile_sessions_root(tmp_path: Path):
    paths = make_test_paths(tmp_path)
    manager = CompileSessionManager(paths=paths)

    session = manager.create_session(thread_id="abc", repo_url="https://example.com/repo.git")

    compile_root = get_compile_sessions_root(paths)
    session_dir = get_session_dir(session.session_id, session.thread_id, paths)
    assert session_dir == compile_root / "abc" / session.session_id
    assert Path(session.metadata_path).parent == session_dir
    assert get_host_session_dir(session.session_id, session.thread_id, paths).startswith(paths.host_workspace_root_str())


def test_save_and_load_session_roundtrip(tmp_path: Path):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-2", repo_url="https://example.com/repo.git")
    session.container_id = "container-123"
    session.container_name = "demo-container"
    session.build_system = "make"
    session.build_system_capabilities = ["cmake", "make"]
    session.selected_build_system = "make"
    session.executed_build_system = "make"
    session.summary = "done"
    session.commands.append(BuildCommandRecord(stage="clone", command="git clone ...", workdir="/workspace"))
    session.artifacts.append(BuildArtifact(path="artifacts/app", artifact_type="binary", size_bytes=123))
    manager.save_session(session)

    loaded = manager.load_session(session.session_id, session.thread_id)

    assert isinstance(loaded, CompileSession)
    assert loaded.container_id == "container-123"
    assert loaded.build_system == "make"
    assert loaded.build_system_capabilities == ["cmake", "make"]
    assert loaded.selected_build_system == "make"
    assert loaded.executed_build_system == "make"
    assert loaded.summary == "done"
    assert len(loaded.commands) == 1
    assert len(loaded.artifacts) == 1


def test_mark_status_sets_completed_at_for_terminal_state(tmp_path: Path):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-3", repo_url="https://example.com/repo.git")

    manager.mark_session_status(session, "completed", summary="ok")

    assert session.completed_at is not None
    assert session.summary == "ok"


def test_mark_status_clears_stale_error_and_preserves_completion_time(tmp_path: Path):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-status", repo_url="https://example.com/repo.git")
    manager.mark_session_status(session, "verification_failed", error="old failure")

    manager.mark_session_status(session, "verified")
    assert session.error is None
    assert session.completed_at is None

    manager.mark_session_status(session, "completed")
    completed_at = session.completed_at
    manager.mark_session_status(session, "completed")
    assert session.completed_at == completed_at


def test_finalize_is_idempotent_and_preserves_first_terminal_result(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-finalize", repo_url="https://example.com/repo.git")
    session.status = "verified"
    session.commit_sha = "a" * 40
    session.artifacts = [BuildArtifact(path="artifacts/hello", artifact_type="executable", size_bytes=128)]
    session.verification = VerificationResult(status="passed", artifact_count=1)
    add_replayable_build_command(session)
    manager.save_session(session)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=SimpleNamespace()))

    operations.finalize_compile_session_impl(session=session, status="completed")
    completed_at = session.completed_at
    finalized_at = session.finalized_at
    reloaded = manager.load_session(session.session_id, session.thread_id)
    operations.finalize_compile_session_impl(
        session=reloaded,
        status="failed",
        error="must not replace the first result",
    )

    assert reloaded.status == "completed"
    assert reloaded.error is None
    assert reloaded.completed_at == completed_at
    assert reloaded.finalized_at == finalized_at
    workflow_log = Path(session.leadagent_logs_dir) / "workflow.log"
    events = [json.loads(line) for line in workflow_log.read_text(encoding="utf-8").splitlines()]
    assert sum(event["event"] == "finalize.completed" for event in events) == 1
    assert sum(event["event"] == "session.status_changed" and event["status"] == "completed" for event in events) == 1


def test_manager_rejects_stale_save_and_status_change_after_finalization(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-finalized-write-fence", repo_url="https://example.com/repo.git")
    stale = manager.load_session(session.session_id, session.thread_id)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=SimpleNamespace()))
    operations.finalize_compile_session_impl(session=session, status="cancelled", error="Parent run was cancelled.")
    terminal_snapshot = session.to_dict()

    stale.status = "verified"
    stale.finalized_at = None
    stale.error = None
    stale.artifacts.append(BuildArtifact(path="artifacts/late", artifact_type="executable", size_bytes=1))

    assert manager.save_session(stale) is False
    manager.mark_session_status(stale, "verification_failed", error="late submit")

    assert stale.to_dict() == terminal_snapshot
    assert manager.load_session(session.session_id, session.thread_id).to_dict() == terminal_snapshot


def test_stale_terminal_status_update_preserves_termination_fence(tmp_path: Path):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-termination-write-fence", repo_url="https://example.com/repo.git")
    stale = manager.load_session(session.session_id, session.thread_id)
    session.termination_requested_at = operations.utc_now_iso()
    session.termination_status = "cancelled"
    manager.save_session(session)

    manager.mark_session_status(stale, "failed", error="late worker failed")
    authoritative = manager.load_session(session.session_id, session.thread_id)

    assert authoritative.status == "failed"
    assert authoritative.termination_requested_at == session.termination_requested_at
    assert authoritative.termination_status == "cancelled"
    manager.mark_session_status(stale, "verified")
    assert manager.load_session(session.session_id, session.thread_id).status == "failed"


def test_normal_finalize_cannot_override_persisted_termination_request(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-termination-finalize", repo_url="https://example.com/repo.git")

    def cleanup(_session: CompileSession) -> ContainerCleanupResult:
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=SimpleNamespace(stop_and_remove_container=cleanup)),
    )
    operations.cleanup_compile_session_container_impl(
        session=session,
        interrupted_status="timed_out",
        error="Compiler timed out.",
    )

    operations.finalize_compile_session_impl(session=session, status="completed", summary="late success")

    reloaded = manager.load_session(session.session_id, session.thread_id)
    assert reloaded.status == "timed_out"
    assert reloaded.error == "Compiler timed out."
    assert reloaded.summary == "Compiler timed out."
    assert reloaded.termination_status == "timed_out"


def test_finalize_failed_session_does_not_generate_repro_bundle(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-failed-finalize", repo_url="https://example.com/repo.git")
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=SimpleNamespace()))

    operations.finalize_compile_session_impl(session=session, status="failed", error="clone failed")

    assert session.status == "failed"
    assert not (Path(session.metadata_path).parent / "repro" / "build.sh").exists()


def test_cleanup_finalized_session_still_reconciles_known_container(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-finalized-cleanup", repo_url="https://example.com/repo.git")
    session.container_id = "late-container-id"
    session.container_name = "late-container-name"
    manager.save_session(session)
    cleanup_calls: list[tuple[str | None, str | None]] = []

    def cleanup(session_arg: CompileSession) -> ContainerCleanupResult:
        cleanup_calls.append((session_arg.container_id, session_arg.container_name))
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=SimpleNamespace(stop_and_remove_container=cleanup)),
    )
    operations.finalize_compile_session_impl(session=session, status="cancelled", error="Parent run was cancelled.")

    updated, cleanup_result = operations.cleanup_compile_session_container_impl(session=session)

    assert updated.status == "cancelled"
    assert cleanup_result.succeeded is True
    assert cleanup_calls == [("late-container-id", "late-container-name")]


def test_cleanup_finalized_session_persists_replay_cleanup_without_repeating_it(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-finalized-replay-cleanup", repo_url="https://example.com/repo.git")
    session.replay_attempts.append(
        ReplayVerificationResult(
            attempt_id="late-replay",
            status="running",
            image=session.image,
            image_id=VALID_IMAGE_ID,
            commit_sha="a" * 40,
            recipe_sha256="b" * 64,
            container_id="late-replay-id",
            container_name="late-replay-name",
        )
    )
    manager.save_session(session)
    replay_cleanup_calls: list[tuple[str | None, str | None]] = []

    def cleanup_compile(_session: CompileSession) -> ContainerCleanupResult:
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    def cleanup_replay(
        _session: CompileSession,
        _handle=None,
        *,
        container_id: str | None = None,
        container_name: str | None = None,
    ) -> ContainerCleanupResult:
        replay_cleanup_calls.append((container_id, container_name))
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(
            manager=manager,
            runtime=SimpleNamespace(
                stop_and_remove_container=cleanup_compile,
                stop_and_remove_replay_container=cleanup_replay,
            ),
        ),
    )
    operations.finalize_compile_session_impl(session=session, status="cancelled", error="Parent run was cancelled.")

    operations.cleanup_compile_session_container_impl(session=session)
    operations.cleanup_compile_session_container_impl(session=session)

    reloaded = manager.load_session(session.session_id, session.thread_id)
    attempt = reloaded.replay_attempts[-1]
    assert attempt.status == "cancelled"
    assert attempt.cleanup_succeeded is True
    assert replay_cleanup_calls == [("late-replay-id", "late-replay-name")]
    workflow_events = [json.loads(line) for line in manager.workflow_log_path(reloaded).read_text(encoding="utf-8").splitlines()]
    assert sum(event["event"] == "replay.completed" and event.get("completed_by") == "parent_cleanup" for event in workflow_events) == 1


def test_finalized_replay_cleanup_merge_ignores_tampered_immutable_evidence(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-finalized-replay-merge", repo_url="https://example.com/repo.git")
    session.replay_attempts.append(
        ReplayVerificationResult(
            attempt_id="authoritative-attempt",
            status="running",
            image=session.image,
            image_id=VALID_IMAGE_ID,
            commit_sha="a" * 40,
            recipe_sha256="b" * 64,
            container_id="authoritative-container",
            container_name="authoritative-name",
        )
    )
    manager.save_session(session)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=SimpleNamespace()))
    operations.finalize_compile_session_impl(session=session, status="cancelled", error="Parent run was cancelled.")
    proposed = manager.load_session(session.session_id, session.thread_id)
    proposed_attempt = proposed.replay_attempts[0]
    proposed_attempt.status = "cancelled"
    proposed_attempt.cleanup_succeeded = True
    proposed_attempt.image_id = f"sha256:{'f' * 64}"
    proposed_attempt.commit_sha = "c" * 40
    proposed_attempt.recipe_sha256 = "d" * 64
    proposed_attempt.container_id = "tampered-container"
    proposed.replay_attempts.append(
        ReplayVerificationResult(
            attempt_id="injected-attempt",
            status="passed",
            image=session.image,
            image_id=VALID_IMAGE_ID,
            commit_sha="e" * 40,
            recipe_sha256="f" * 64,
        )
    )

    assert manager.save_session(
        proposed,
        allow_lifecycle_fenced=True,
        merge_finalized_replay_cleanup=True,
    )

    reloaded = manager.load_session(session.session_id, session.thread_id)
    assert len(reloaded.replay_attempts) == 1
    attempt = reloaded.replay_attempts[0]
    assert attempt.status == "cancelled"
    assert attempt.cleanup_succeeded is True
    assert attempt.image_id == VALID_IMAGE_ID
    assert attempt.commit_sha == "a" * 40
    assert attempt.recipe_sha256 == "b" * 64
    assert attempt.container_id == "authoritative-container"


def test_replay_cleanup_retry_persists_success_and_emits_retry_event(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-replay-cleanup-retry", repo_url="https://example.com/repo.git")
    session.replay_attempts.append(
        ReplayVerificationResult(
            attempt_id="retry-attempt",
            status="running",
            image=session.image,
            image_id=VALID_IMAGE_ID,
            commit_sha="a" * 40,
            recipe_sha256="b" * 64,
            container_id="retry-container",
            container_name="retry-name",
        )
    )
    manager.save_session(session)
    replay_results = iter(
        [
            ContainerCleanupResult(succeeded=False, stopped=False, removed=False),
            ContainerCleanupResult(succeeded=True, stopped=True, removed=True),
        ]
    )
    replay_cleanup_calls = 0

    def cleanup_compile(_session: CompileSession) -> ContainerCleanupResult:
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    def cleanup_replay(*_args, **_kwargs) -> ContainerCleanupResult:
        nonlocal replay_cleanup_calls
        replay_cleanup_calls += 1
        return next(replay_results)

    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(
            manager=manager,
            runtime=SimpleNamespace(
                stop_and_remove_container=cleanup_compile,
                stop_and_remove_replay_container=cleanup_replay,
            ),
        ),
    )

    operations.cleanup_compile_session_container_impl(
        session=session,
        interrupted_status="cancelled",
        error="Parent run was cancelled.",
    )
    operations.cleanup_compile_session_container_impl(session=session)
    operations.cleanup_compile_session_container_impl(session=session)

    reloaded = manager.load_session(session.session_id, session.thread_id)
    assert reloaded.replay_attempts[-1].cleanup_succeeded is True
    assert replay_cleanup_calls == 2
    workflow_events = [json.loads(line) for line in manager.workflow_log_path(reloaded).read_text(encoding="utf-8").splitlines()]
    assert sum(event["event"] == "replay.completed" and event.get("completed_by") == "parent_cleanup_retry" for event in workflow_events) == 1


def test_concurrent_finalize_with_stale_copies_commits_one_terminal_result(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-concurrent-finalize", repo_url="https://example.com/repo.git")
    manager.save_session(session)
    first = manager.load_session(session.session_id, session.thread_id)
    second = manager.load_session(session.session_id, session.thread_id)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=SimpleNamespace()))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(operations.finalize_compile_session_impl, session=first, status="completed"),
            pool.submit(
                operations.finalize_compile_session_impl,
                session=second,
                status="failed",
                error="competing terminal result",
            ),
        ]
        results = [future.result() for future in futures]

    authoritative = manager.load_session(session.session_id, session.thread_id)
    assert {result.status for result in results} == {authoritative.status}
    workflow_log = Path(session.leadagent_logs_dir) / "workflow.log"
    events = [json.loads(line) for line in workflow_log.read_text(encoding="utf-8").splitlines()]
    assert sum(event["event"] == "finalize.completed" for event in events) == 1


def test_parent_run_cleanup_finalizes_unfinished_session_once(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-cancelled", repo_url="https://example.com/repo.git")
    session.status = "inspected"
    session.container_id = "container-123"
    manager.save_session(session)
    cleanup_calls: list[str] = []

    def cleanup(session_arg):
        cleanup_calls.append(session_arg.session_id)
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(
            manager=manager,
            runtime=SimpleNamespace(stop_and_remove_container=cleanup),
        ),
    )

    finalized = operations.finalize_unfinished_thread_sessions_impl(
        thread_id=session.thread_id,
        interrupted_status="cancelled",
        error="Parent run was cancelled.",
    )
    repeated = operations.finalize_unfinished_thread_sessions_impl(
        thread_id=session.thread_id,
        interrupted_status="cancelled",
        error="Parent run was cancelled.",
    )

    assert len(finalized) == 1
    assert repeated == []
    loaded = manager.load_session(session.session_id, session.thread_id)
    assert loaded.status == "cancelled"
    assert loaded.error == "Parent run was cancelled."
    assert loaded.completed_at is not None
    assert loaded.finalized_at is not None
    assert cleanup_calls == [session.session_id]
    workflow_log = Path(loaded.leadagent_logs_dir) / "workflow.log"
    events = [json.loads(line) for line in workflow_log.read_text(encoding="utf-8").splitlines()]
    assert sum(event["event"] == "finalize.completed" for event in events) == 1


def test_parent_run_cleanup_only_touches_sessions_owned_by_that_run(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    old_session = manager.create_session(
        thread_id="thread-overlap",
        run_id="run-old",
        repo_url="https://example.com/old.git",
    )
    new_session = manager.create_session(
        thread_id="thread-overlap",
        run_id="run-new",
        repo_url="https://example.com/new.git",
    )
    cleanup_calls: list[str] = []

    def cleanup(session_arg):
        cleanup_calls.append(session_arg.session_id)
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=SimpleNamespace(stop_and_remove_container=cleanup)),
    )

    finalized = operations.finalize_unfinished_thread_sessions_impl(
        thread_id=old_session.thread_id,
        run_id="run-old",
        interrupted_status="cancelled",
        error="Old run was replaced.",
    )

    assert [item.session_id for item in finalized] == [old_session.session_id]
    assert cleanup_calls == [old_session.session_id]
    assert manager.load_session(old_session.session_id, old_session.thread_id).finalized_at is not None
    loaded_new = manager.load_session(new_session.session_id, new_session.thread_id)
    assert loaded_new.status == "created"
    assert loaded_new.finalized_at is None


def test_cleanup_failure_remains_retryable_until_container_is_removed(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-cleanup-retry",
        run_id="run-cleanup-retry",
        repo_url="https://example.com/repo.git",
    )
    results = iter(
        [
            ContainerCleanupResult(succeeded=False, stopped=False, removed=False),
            ContainerCleanupResult(succeeded=True, stopped=True, removed=True),
        ]
    )
    cleanup_calls = 0

    def cleanup(_session):
        nonlocal cleanup_calls
        cleanup_calls += 1
        return next(results)

    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=SimpleNamespace(stop_and_remove_container=cleanup)),
    )

    operations.finalize_unfinished_thread_sessions_impl(
        thread_id=session.thread_id,
        run_id=session.run_id,
        interrupted_status="timed_out",
        error="Compiler timed out.",
    )
    after_failure = manager.load_session(session.session_id, session.thread_id)
    assert after_failure.status == "failed"
    assert after_failure.finalized_at is None
    assert after_failure.termination_status == "timed_out"
    assert after_failure.termination_error == "Compiler timed out."

    operations.finalize_unfinished_thread_sessions_impl(
        thread_id=session.thread_id,
        run_id=session.run_id,
        interrupted_status="cancelled",
        error="Parent run was cancelled.",
    )
    after_retry = manager.load_session(session.session_id, session.thread_id)
    assert after_retry.status == "timed_out"
    assert after_retry.error == "Compiler timed out."
    assert after_retry.termination_status == "timed_out"
    assert after_retry.finalized_at is not None
    assert cleanup_calls == 2


def test_parent_cleanup_reloads_session_before_stopping_container(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-stale-cleanup",
        run_id="run-stale-cleanup",
        repo_url="https://example.com/repo.git",
    )
    stale_snapshot = manager.load_session(session.session_id, session.thread_id)
    session.container_id = "container-created-after-snapshot"
    manager.save_session(session)
    cleanup_container_ids: list[str | None] = []

    def cleanup(session_arg):
        cleanup_container_ids.append(session_arg.container_id)
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    monkeypatch.setattr(manager, "list_sessions", lambda _thread_id: [stale_snapshot])
    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=SimpleNamespace(stop_and_remove_container=cleanup)),
    )

    operations.finalize_unfinished_thread_sessions_impl(
        thread_id=session.thread_id,
        run_id=session.run_id,
        interrupted_status="cancelled",
        error="Parent run was cancelled.",
    )

    assert cleanup_container_ids == ["container-created-after-snapshot"]


def test_host_workspace_path_preserves_windows_style(tmp_path: Path):
    paths = make_test_paths(tmp_path, host_workspace_root=r"C:\Users\developer\Forge-AutoCompiler")
    manager = CompileSessionManager(paths=paths)
    session = manager.create_session(thread_id="windows-thread", repo_url="https://example.com/repo.git")

    assert get_host_workspace_dir(session.session_id, session.thread_id, paths) == (rf"C:\Users\developer\Forge-AutoCompiler\.compile-sessions\windows-thread\{session.session_id}\workspace")


def test_cleanup_reports_stopped_container_without_claiming_removal(monkeypatch):
    runtime = CompileDockerRuntime(config=RuntimeConfig(remove_on_cleanup=False))
    session = CompileSession(
        session_id="session-cleanup",
        thread_id="thread-cleanup",
        repo_url="https://example.com/repo.git",
        branch=None,
        image="autocompiler:gcc13",
        status="verified",
        container_id="container-123",
    )

    def fake_run(command, **kwargs):
        del kwargs
        assert command == ["docker", "stop", "container-123"]
        return SimpleNamespace(returncode=0, stdout="container-123\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runtime.stop_and_remove_container(session)

    assert result.succeeded is True
    assert result.stopped is True
    assert result.removed is False


def test_docker_runtime_uses_paths_host_workspace_root(tmp_path: Path, monkeypatch):
    host_root = tmp_path / "docker-host"
    paths = make_test_paths(tmp_path, host_workspace_root=str(host_root))
    manager = CompileSessionManager(paths=paths)
    session = manager.create_session(thread_id="thread-runtime", repo_url="https://example.com/repo.git")
    runtime = CompileDockerRuntime(config=RuntimeConfig(network=DEFAULT_NETWORK), manager=manager)
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        del kwargs
        commands.append(command)
        if command[:3] == ["docker", "inspect", "--format"]:
            return type("Result", (), {"stdout": f"{VALID_IMAGE_ID}\n", "stderr": "", "returncode": 0})()
        return type("Result", (), {"stdout": "container-id\n", "stderr": "", "returncode": 0})()

    monkeypatch.setattr("deerflow.compile.docker_runtime.subprocess.run", fake_run)

    runtime.create_container(session)

    docker_command = next(command for command in commands if command[:2] == ["docker", "run"])
    assert ["docker", "network", "inspect", DEFAULT_NETWORK] in commands
    assert f"{host_root / '.compile-sessions' / session.thread_id / session.session_id / 'workspace'}:/workspace" in docker_command
    assert "HOST_PROJECT_ROOT" not in docker_command


def test_docker_runtime_applies_experiment_labels_and_public_environment_only(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    thread_id = "thread-experiment-runtime"
    session = manager.create_session(thread_id=thread_id, repo_url="https://example.com/repo.git")
    ledger = ExperimentLedger.create(
        tmp_path / "evidence.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"thread_id": thread_id},
    )
    policy = ExperimentPolicy(
        benchmark_id="forge-cpp-pilot-v1",
        manifest_sha256="1" * 64,
        case_id="fixture",
        condition="baseline",
        repetition=1,
        expected_repo_url=session.repo_url,
        expected_commit_sha="2" * 40,
        expected_build_system="cmake",
        compile_image=session.image,
        image_id=VALID_IMAGE_ID,
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
        configure_arguments=(),
        environment=(("CFLAGS", "-O2"), ("SOURCE_DATE_EPOCH", None)),
        minimum_replay_delay_seconds=0,
    )
    active = activate_experiment(
        thread_id=thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=policy,
    )
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        del kwargs
        commands.append(command)
        if command[:3] == ["docker", "inspect", "--format"]:
            return SimpleNamespace(stdout=f"{VALID_IMAGE_ID}\n", stderr="", returncode=0)
        return SimpleNamespace(stdout="container-id\n", stderr="", returncode=0)

    monkeypatch.setattr("deerflow.compile.docker_runtime.subprocess.run", fake_run)
    try:
        CompileDockerRuntime(manager=manager).create_container(session)
    finally:
        deactivate_experiment(thread_id)

    docker_command = next(command for command in commands if command[:2] == ["docker", "run"])
    assert f"deerflow.compile.experiment_id={active.experiment_id}" in docker_command
    assert f"deerflow.compile.physical_attempt_id={active.physical_attempt_id}" in docker_command
    assert "CFLAGS=-O2" in docker_command
    assert not any(argument.startswith("SOURCE_DATE_EPOCH=") for argument in docker_command)
    assert policy.credential_env not in docker_command


def test_docker_runtime_creates_missing_network(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-network", repo_url="https://example.com/repo.git")
    runtime = CompileDockerRuntime(config=RuntimeConfig(network=DEFAULT_NETWORK), manager=manager)
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        del kwargs
        commands.append(command)
        if command[:3] == ["docker", "inspect", "--format"]:
            return type("Result", (), {"stdout": f"{VALID_IMAGE_ID}\n", "stderr": "", "returncode": 0})()
        if command[:3] == ["docker", "network", "inspect"]:
            return type("Result", (), {"stdout": "", "stderr": "not found", "returncode": 1})()
        return type("Result", (), {"stdout": "container-id\n", "stderr": "", "returncode": 0})()

    monkeypatch.setattr("deerflow.compile.docker_runtime.subprocess.run", fake_run)

    runtime.create_container(session)

    assert ["docker", "network", "create", DEFAULT_NETWORK] in commands


def test_docker_runtime_passes_runtime_proxy_values_out_of_band(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-proxy", repo_url="https://example.com/repo.git")
    proxy_url = "http://127.0.0.1:7897"
    monkeypatch.setenv("COMPILE_RUNTIME_NETWORK", "host")
    monkeypatch.setenv("COMPILE_RUNTIME_HTTP_PROXY", proxy_url)
    monkeypatch.setenv("COMPILE_RUNTIME_HTTPS_PROXY", proxy_url)
    monkeypatch.setenv("COMPILE_RUNTIME_NO_PROXY", "localhost,127.0.0.1")
    calls: list[tuple[list[str], dict]] = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[:3] == ["docker", "inspect", "--format"]:
            return type("Result", (), {"stdout": f"{VALID_IMAGE_ID}\n", "stderr": "", "returncode": 0})()
        return type("Result", (), {"stdout": "container-id\n", "stderr": "", "returncode": 0})()

    monkeypatch.setattr("deerflow.compile.docker_runtime.subprocess.run", fake_run)

    CompileDockerRuntime(manager=manager).create_container(session)

    commands = [command for command, _ in calls]
    assert ["docker", "network", "inspect", "host"] in commands
    docker_command, docker_kwargs = next((command, kwargs) for command, kwargs in calls if command[:2] == ["docker", "run"])
    assert ["--network", "host"] == docker_command[docker_command.index("--network") : docker_command.index("--network") + 2]
    assert ["--add-host", "host.docker.internal:host-gateway"] == docker_command[docker_command.index("--add-host") : docker_command.index("--add-host") + 2]
    assert docker_command.count("-e") == 6
    assert "HTTP_PROXY" in docker_command
    assert "http_proxy" in docker_command
    assert "HTTPS_PROXY" in docker_command
    assert "https_proxy" in docker_command
    assert "NO_PROXY" in docker_command
    assert "no_proxy" in docker_command
    assert proxy_url not in docker_command
    assert docker_kwargs["env"]["HTTP_PROXY"] == proxy_url
    assert docker_kwargs["env"]["https_proxy"] == proxy_url
    assert docker_kwargs["env"]["NO_PROXY"] == "localhost,127.0.0.1"


def test_docker_runtime_exec_enforces_timeout_inside_container(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-exec-timeout", repo_url="https://example.com/repo.git")
    session.container_id = "container-123"
    calls: list[tuple[list[str], dict]] = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout="ok\n", stderr="", returncode=0)

    monkeypatch.setattr("deerflow.compile.docker_runtime.subprocess.run", fake_run)

    result = CompileDockerRuntime(manager=manager).exec(session, "echo ok", timeout_seconds=7)

    docker_command, docker_kwargs = calls[0]
    assert docker_command[-7:] == ["timeout", "--signal=TERM", "--kill-after=5s", "7s", "bash", "-lc", "echo ok"]
    assert docker_kwargs["timeout"] == 17
    assert result.exit_code == 0


def test_docker_runtime_exec_records_docker_client_timeout(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-client-timeout", repo_url="https://example.com/repo.git")
    session.container_id = "container-123"
    log_path = tmp_path / "timeout.log"

    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output="partial output\n", stderr="stalled\n")

    monkeypatch.setattr("deerflow.compile.docker_runtime.subprocess.run", fake_run)

    result = CompileDockerRuntime(manager=manager).exec(session, "long-command", timeout_seconds=3, log_path=str(log_path))

    assert result.exit_code == 124
    assert result.stdout == "partial output\n"
    assert result.stderr == "stalled\n"
    assert "3-second container timeout" in result.combined_output
    assert log_path.read_text(encoding="utf-8") == result.combined_output


def test_clone_repository_runs_git_inside_compile_container(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-clone", repo_url="https://example.com/repo.git")
    session.container_id = "container-123"
    calls: list[tuple[str, str | None, str | None]] = []

    def fake_exec(session_arg, command, workdir=None, timeout_seconds=600, log_path=None):
        del timeout_seconds
        assert session_arg is session
        calls.append((command, workdir, log_path))
        if "git clone" in command:
            Path(session.leadagent_repo_dir).mkdir(parents=True)
            return CommandResult(exit_code=0, stdout="", stderr="", combined_output="", log_path=log_path)
        return CommandResult(exit_code=0, stdout="abc123\n", stderr="", combined_output="abc123\n")

    services = CompileOperationsServices(manager=manager, runtime=SimpleNamespace(exec=fake_exec))
    monkeypatch.setattr(operations, "_services", services)

    result, message = clone_repository_impl(
        session=session,
        repo_url=session.repo_url,
        branch="release branch",
        depth=1,
    )

    assert result.exit_code == 0
    assert calls[0][0] == "rm -rf -- /workspace/repo && git clone --depth 1 --branch 'release branch' https://example.com/repo.git /workspace/repo"
    assert calls[0][1] == "/workspace"
    assert calls[0][2].endswith("001_clone_attempt_1.log")
    assert calls[1][:2] == (
        "git config --global --replace-all safe.directory /workspace/repo && git -C /workspace/repo rev-parse HEAD",
        "/workspace",
    )
    assert session.commit_sha == "abc123"
    assert session.status == "source_ready"
    assert "Repository cloned successfully" in message


def test_exact_commit_clone_marks_repository_safe_before_git_c_operations(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    repo_url = "https://example.com/repo.git"
    commit_sha = "0123456789abcdef0123456789abcdef01234567"
    session = manager.create_session(thread_id="thread-exact-clone", repo_url=repo_url)
    session.container_id = "container-123"
    calls: list[str] = []

    def fake_exec(session_arg, command, **_kwargs):
        assert session_arg is session
        calls.append(command)
        if command.endswith("rev-parse HEAD"):
            return CommandResult(exit_code=0, stdout=f"{commit_sha}\n", stderr="", combined_output=f"{commit_sha}\n")
        return CommandResult(exit_code=0, stdout="", stderr="", combined_output="")

    active = SimpleNamespace(policy=SimpleNamespace(expected_repo_url=repo_url, expected_commit_sha=commit_sha))
    monkeypatch.setattr(operations, "get_active_experiment", lambda _thread_id: active)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=SimpleNamespace(exec=fake_exec)))

    result, message = clone_repository_impl(session=session, repo_url=repo_url, max_retries=1)

    assert result.exit_code == 0
    exact_clone_command = calls[0]
    safe_directory = "git config --global --replace-all safe.directory /workspace/repo"
    first_git_c = "git -C /workspace/repo remote add origin"
    assert safe_directory in exact_clone_command
    assert exact_clone_command.index(safe_directory) < exact_clone_command.index(first_git_c)
    assert session.commit_sha == commit_sha
    assert session.status == "source_ready"
    assert "Repository cloned successfully" in message


def test_clone_repository_retries_with_container_side_cleanup(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-clone-retry", repo_url="https://example.com/repo.git")
    session.container_id = "container-123"
    calls: list[tuple[str, str | None, str | None]] = []
    clone_results = iter(
        [
            CommandResult(exit_code=124, stdout="", stderr="timed out", combined_output="timed out"),
            CommandResult(exit_code=0, stdout="", stderr="", combined_output=""),
        ]
    )

    def fake_exec(session_arg, command, workdir=None, timeout_seconds=600, log_path=None):
        del timeout_seconds
        assert session_arg is session
        calls.append((command, workdir, log_path))
        if "git clone" in command:
            return next(clone_results)
        return CommandResult(exit_code=0, stdout="def456\n", stderr="", combined_output="def456\n")

    services = CompileOperationsServices(manager=manager, runtime=SimpleNamespace(exec=fake_exec))
    monkeypatch.setattr(operations, "_services", services)

    result, message = clone_repository_impl(session=session, repo_url=session.repo_url, max_retries=2)

    clone_calls = [call for call in calls if "git clone" in call[0]]
    assert result.exit_code == 0
    assert len(clone_calls) == 2
    assert all(call[0].startswith("rm -rf -- /workspace/repo && git clone") for call in clone_calls)
    assert clone_calls[0][2].endswith("001_clone_attempt_1.log")
    assert clone_calls[1][2].endswith("001_clone_attempt_2.log")
    assert session.commit_sha == "def456"
    assert session.status == "source_ready"
    assert "Repository cloned successfully" in message


def test_clone_repository_persists_effective_source_for_replay(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-clone-override",
        repo_url="https://example.com/old.git",
        branch="prepared-branch",
    )
    session.container_id = "container-123"
    actual_repo_url = "https://example.com/actual.git"
    commit_sha = "0123456789abcdef0123456789abcdef01234567"
    calls: list[str] = []

    def fake_exec(session_arg, command, **kwargs):
        del kwargs
        assert session_arg is session
        calls.append(command)
        if "git clone" in command:
            return CommandResult(exit_code=0, stdout="", stderr="", combined_output="")
        return CommandResult(exit_code=0, stdout=f"{commit_sha}\n", stderr="", combined_output=f"{commit_sha}\n")

    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=SimpleNamespace(exec=fake_exec)))

    result, _ = clone_repository_impl(session=session, repo_url=actual_repo_url)

    assert result.exit_code == 0
    assert calls[0] == "rm -rf -- /workspace/repo && git clone --depth 1 --branch prepared-branch https://example.com/actual.git /workspace/repo"
    assert session.repo_url == actual_repo_url
    assert session.branch == "prepared-branch"
    assert session.commit_sha == commit_sha
    reloaded = manager.load_session(session.session_id, session.thread_id)
    assert reloaded.repo_url == actual_repo_url
    assert reloaded.branch == "prepared-branch"


def test_compiled_artifact_classifier_uses_file_format_not_mode(tmp_path: Path):
    executable = tmp_path / "app"
    pie_executable = tmp_path / "pie-app"
    shared_library = tmp_path / "libapp.so"
    static_pie = tmp_path / "static-pie"
    object_file = tmp_path / "app.o"
    static_library = tmp_path / "libapp.a"
    text_log = tmp_path / "commands.log"

    write_elf(executable, 2)
    write_elf(pie_executable, 3, has_interpreter=True)
    write_elf(shared_library, 3)
    write_elf(static_pie, 3, has_entry_point=True)
    write_elf(object_file, 1)
    write_static_archive(static_library)
    text_log.write_text("echo this must never run\n", encoding="utf-8")
    text_log.chmod(0o777)

    assert _classify_compiled_artifact(executable) == "executable"
    assert _classify_compiled_artifact(pie_executable) == "executable"
    assert _classify_compiled_artifact(shared_library) == "shared_library"
    assert _classify_compiled_artifact(static_pie) == "executable"
    assert _classify_compiled_artifact(object_file) == "object"
    assert _classify_compiled_artifact(static_library) == "static_library"
    assert _classify_compiled_artifact(text_log) is None


def test_compiled_artifact_classifier_rejects_truncated_headers(tmp_path: Path):
    truncated_elf = tmp_path / "truncated.o"
    empty_archive = tmp_path / "empty.a"
    truncated_archive = tmp_path / "truncated.a"
    truncated_elf.write_bytes(b"\x7fELF" + bytes(60))
    empty_archive.write_bytes(b"!<arch>\n")
    truncated_archive.write_bytes(b"!<arch>\nmember.o/")

    assert _classify_compiled_artifact(truncated_elf) is None
    assert _classify_compiled_artifact(empty_archive) is None
    assert _classify_compiled_artifact(truncated_archive) is None


def test_compiled_artifact_classifier_rejects_empty_structural_shells(tmp_path: Path):
    executable = tmp_path / "empty-app"
    object_file = tmp_path / "empty.o"
    archive = tmp_path / "empty.a"
    write_empty_elf(executable, 2)
    write_empty_elf(object_file, 1)
    payload = object_file.read_bytes()
    member_header = b"".join(
        [
            b"empty.o/".ljust(16),
            b"0".ljust(12),
            b"0".ljust(6),
            b"0".ljust(6),
            b"100644".ljust(8),
            str(len(payload)).encode("ascii").ljust(10),
            b"`\n",
        ]
    )
    archive.write_bytes(b"!<arch>\n" + member_header + payload + (b"\n" if len(payload) % 2 else b""))

    assert _classify_compiled_artifact(executable) is None
    assert _classify_compiled_artifact(object_file) is None
    assert _classify_compiled_artifact(archive) is None


@pytest.mark.skipif(shutil.which("gcc") is None or shutil.which("ar") is None, reason="requires a C toolchain")
def test_compiled_artifact_classifier_accepts_real_gcc_and_ar_outputs(tmp_path: Path):
    source = tmp_path / "artifact.c"
    executable = tmp_path / "artifact"
    shared_library = tmp_path / "libartifact.so"
    object_file = tmp_path / "artifact.o"
    static_library = tmp_path / "libartifact.a"
    source.write_text("int value(void) { return 7; }\nint main(void) { return value(); }\n", encoding="utf-8")

    subprocess.run(["gcc", str(source), "-o", str(executable)], check=True, capture_output=True)
    subprocess.run(["gcc", "-shared", "-fPIC", str(source), "-o", str(shared_library)], check=True, capture_output=True)
    subprocess.run(["gcc", "-c", str(source), "-o", str(object_file)], check=True, capture_output=True)
    subprocess.run(["ar", "rcs", str(static_library), str(object_file)], check=True, capture_output=True)

    assert _classify_compiled_artifact(executable) == "executable"
    assert _classify_compiled_artifact(shared_library) == "shared_library"
    assert _classify_compiled_artifact(object_file) == "object"
    assert _classify_compiled_artifact(static_library) == "static_library"


@pytest.mark.skipif(shutil.which("gcc") is None, reason="requires gcc")
def test_compiled_artifact_classifier_recognizes_real_static_pie(tmp_path: Path):
    source = tmp_path / "static-pie.c"
    executable = tmp_path / "static-pie"
    source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
    result = subprocess.run(["gcc", "-static-pie", str(source), "-o", str(executable)], check=False, capture_output=True)
    if result.returncode != 0:
        pytest.skip("toolchain does not support static PIE")

    assert _classify_compiled_artifact(executable) == "executable"


def test_repro_bundle_pins_commit_and_renders_only_successful_bash_commands(tmp_path: Path):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(
        thread_id="thread-repro-contract",
        repo_url="https://example.com/O'Reilly/repo.git",
    )
    session.commit_sha = "0123456789abcdef0123456789abcdef01234567"
    session.commands = [
        BuildCommandRecord(
            stage="clone",
            command="rm -rf /workspace/repo && git clone https://moving.example/repo.git /workspace/repo",
            workdir="/workspace",
            exit_code=0,
        ),
        BuildCommandRecord(
            stage="bash",
            command="cmake -S . -B 'build dir'",
            workdir="/workspace/repo",
            exit_code=0,
        ),
        BuildCommandRecord(
            stage="bash",
            command="cmake --build broken",
            workdir="/workspace/repo",
            exit_code=1,
        ),
        BuildCommandRecord(
            stage="bash",
            command="cmake --build timed-out",
            workdir="/workspace/repo",
            exit_code=124,
        ),
        BuildCommandRecord(
            stage="bash",
            command="cmake --build unfinished",
            workdir="/workspace/repo",
            exit_code=None,
        ),
        BuildCommandRecord(
            stage="inspect",
            command="echo inspect-only",
            workdir="/workspace/repo",
            exit_code=0,
        ),
        BuildCommandRecord(
            stage="bash",
            command="cmake --build . && cp hello /artifacts/hello",
            workdir="/workspace/repo/build dir",
            exit_code=0,
        ),
        BuildCommandRecord(
            stage="bash",
            command="test -f hello",
            workdir="/artifacts",
            exit_code=0,
        ),
        BuildCommandRecord(
            stage="submit",
            command="submit build result from /artifacts",
            workdir=str(Path(session.metadata_path).parent),
            exit_code=0,
        ),
    ]

    build_path = _write_repro_bundle(session)
    script = build_path.read_text(encoding="utf-8")

    assert f"REPO_URL={operations.shell_quote(session.repo_url)}" in script
    assert f"COMMIT_SHA={session.commit_sha}" in script
    assert 'git fetch --depth 1 origin "$COMMIT_SHA"' in script
    assert 'test "$(git rev-parse HEAD)" = "$COMMIT_SHA"' in script
    assert 'find "$WORKSPACE_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +' in script
    assert 'find "$ARTIFACTS_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +' in script
    assert 'git init --quiet "$REPO_DIR"' in script
    assert 'git config --global --add safe.directory "$REPO_DIR"' in script
    assert f"bash -lc {operations.shell_quote("cmake -S . -B 'build dir'")}" in script
    assert "cd -- '/workspace/repo/build dir'" in script
    assert f"bash -lc {operations.shell_quote('cmake --build . && cp hello /artifacts/hello')}" in script
    assert "cd -- /artifacts" in script
    assert "bash -lc 'test -f hello'" in script
    assert "cmake --build broken" not in script
    assert "cmake --build timed-out" not in script
    assert "cmake --build unfinished" not in script
    assert "inspect-only" not in script
    assert "submit build result" not in script
    assert "moving.example" not in script
    assert session.session_id not in script
    assert ".compile-sessions" not in script
    subprocess.run(["bash", "-n", str(build_path)], check=True, capture_output=True)


@pytest.mark.parametrize(
    "workdir",
    [
        "relative/repo",
        "/workspace/../etc",
        "/workspace/.compile-sessions/thread/session/workspace/repo",
        r"C:\Users\YiWei\Forge\repo",
    ],
)
def test_repro_bundle_rejects_non_container_workdir(tmp_path: Path, workdir: str):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-repro-workdir", repo_url="https://example.com/repo.git")
    session.commit_sha = "a" * 40
    session.commands = [
        BuildCommandRecord(
            stage="bash",
            command="cmake --build .",
            workdir=workdir,
            exit_code=0,
        )
    ]

    with pytest.raises(ValueError, match="replay workdir"):
        _write_repro_bundle(session)


@pytest.mark.parametrize(
    "command",
    [
        "cp /workspace/.compile-sessions/thread/session/artifacts/hello /artifacts/hello",
        r"cp C:\Users\YiWei\Forge\hello /artifacts/hello",
        "printf x >/mnt/c/Users/YiWei/out",
        r"printf x >C:\Users\YiWei\out",
        "PATH=/tmp:/mnt/c/Windows cmake --build .",
    ],
)
def test_repro_bundle_rejects_host_path_in_command(tmp_path: Path, command: str):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-repro-command", repo_url="https://example.com/repo.git")
    session.commit_sha = "a" * 40
    session.commands = [
        BuildCommandRecord(
            stage="bash",
            command=command,
            workdir="/workspace/repo",
            exit_code=0,
        )
    ]

    with pytest.raises(ValueError, match="replay command"):
        _write_repro_bundle(session)


def test_repro_bundle_requires_commit_sha(tmp_path: Path):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-repro-commit", repo_url="https://example.com/repo.git")

    with pytest.raises(ValueError, match="commit_sha"):
        _write_repro_bundle(session)


def test_repro_bundle_rejects_empty_successful_recipe_and_removes_stale_script(tmp_path: Path):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-empty-repro", repo_url="https://example.com/repo.git")
    session.commit_sha = "a" * 40
    build_path = Path(session.metadata_path).parent / "repro" / "build.sh"
    build_path.parent.mkdir(parents=True, exist_ok=True)
    build_path.write_text("stale unsafe replay\n", encoding="utf-8")

    with pytest.raises(ValueError, match="successful bash command"):
        _write_repro_bundle(session)

    assert not build_path.exists()


@pytest.mark.parametrize(
    ("commit_sha", "expected_init"),
    [
        ("A" * 40, 'git init --quiet "$REPO_DIR"'),
        ("B" * 64, 'git init --object-format=sha256 --quiet "$REPO_DIR"'),
    ],
)
def test_repro_bundle_normalizes_commit_sha_and_selects_git_object_format(tmp_path: Path, commit_sha: str, expected_init: str):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-repro-object-format", repo_url="https://example.com/repo.git")
    session.commit_sha = commit_sha
    add_replayable_build_command(session)

    script = _write_repro_bundle(session).read_text(encoding="utf-8")

    assert f"COMMIT_SHA={commit_sha.lower()}" in script
    assert expected_init in script


@pytest.mark.parametrize(
    "commit_sha",
    [
        "main",
        "a" * 39,
        "a" * 40 + "; touch /tmp/pwned",
    ],
)
def test_repro_bundle_rejects_invalid_commit_sha(tmp_path: Path, commit_sha: str):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-invalid-commit", repo_url="https://example.com/repo.git")
    session.commit_sha = commit_sha

    with pytest.raises(ValueError, match="commit_sha"):
        _write_repro_bundle(session)


@pytest.mark.parametrize(
    "repo_url",
    [
        "https://token@example.com/private/repo.git",
        "https://example.com/private/repo.git?token=secret",
        "ssh://git@example.com/private/repo.git?token=secret",
        "git@example.com:private/repo.git?token=secret",
        "git@example.com:private/repo.git#main",
        "file:///tmp/repo",
        "/mnt/c/Users/YiWei/repo",
        r"C:\Users\YiWei\repo",
    ],
)
def test_repro_bundle_rejects_credentialed_or_local_repo_url(tmp_path: Path, repo_url: str):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-invalid-repo-url", repo_url=repo_url)
    session.commit_sha = "a" * 40

    with pytest.raises(ValueError, match="repo_url"):
        _write_repro_bundle(session)


def test_submit_rejects_artifact_when_repro_bundle_is_not_commit_pinned(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-unpinned-repro", repo_url="https://example.com/repo.git")
    write_elf(Path(session.leadagent_artifacts_dir) / "hello", 2)

    def fake_exec(*args, **kwargs):
        return CommandResult(exit_code=0, stdout="Hello Matt!\n", stderr="", combined_output="Hello Matt!\n")

    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=SimpleNamespace(exec=fake_exec)))

    payload = json.loads(submit_build_result_impl(session=session))

    assert payload["status"] == "failed"
    assert "replay bundle" in payload["message"].lower()
    assert session.status == "verification_failed"
    assert session.verification is not None
    assert session.verification.failed_checks == 1
    assert any(check.name == "repro_bundle" and not check.passed for check in session.verification.checks)
    assert not (Path(session.metadata_path).parent / "repro" / "build.sh").exists()


def test_submit_rejects_executable_mode_text_without_running_it(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-text-artifact", repo_url="https://example.com/repo.git")
    text_log = Path(session.leadagent_artifacts_dir) / "commands.log"
    text_log.write_text("echo this must never run\n", encoding="utf-8")
    text_log.chmod(0o777)

    def fail_exec(*args, **kwargs):
        raise AssertionError("Text artifacts must not be executed")

    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=SimpleNamespace(exec=fail_exec)))

    payload = json.loads(submit_build_result_impl(session=session))

    assert payload["status"] == "failed"
    assert payload["artifact_count"] == 0
    assert "No recognized compiled artifacts" in payload["message"]
    assert session.status == "verification_failed"


def test_submit_rejects_symlinked_system_executable_without_running_it(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-symlink-artifact", repo_url="https://example.com/repo.git")
    symlink = Path(session.leadagent_artifacts_dir) / "fake-app"
    symlink.symlink_to("/bin/true")

    def fail_exec(*args, **kwargs):
        raise AssertionError("Symlinked artifacts must not be executed")

    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=SimpleNamespace(exec=fail_exec)))

    payload = json.loads(submit_build_result_impl(session=session))

    assert payload["status"] == "failed"
    assert payload["artifact_count"] == 0
    assert session.status == "verification_failed"


def test_submit_smokes_only_elf_executable_and_ignores_text(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-mixed-artifacts", repo_url="https://example.com/repo.git")
    session.commit_sha = "a" * 40
    add_replayable_build_command(session, "cmake --build build && cp build/hello /artifacts/hello")
    session.error = "stale verification failure"
    manager.save_session(session)
    artifacts_dir = Path(session.leadagent_artifacts_dir)
    write_elf(artifacts_dir / "hello", 2)
    text_log = artifacts_dir / "verification.log"
    text_log.write_text("", encoding="utf-8")
    text_log.chmod(0o777)
    calls: list[str] = []

    def fake_exec(session_arg, command, **kwargs):
        assert session_arg is session
        calls.append(command)
        return CommandResult(exit_code=0, stdout="Hello Matt!\n", stderr="", combined_output="Hello Matt!\n")

    install_passed_replay_stub(monkeypatch)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=SimpleNamespace(exec=fake_exec)))

    payload = json.loads(submit_build_result_impl(session=session))

    assert payload["status"] == "passed"
    assert payload["artifact_count"] == 1
    assert payload["artifacts"][0]["artifact_type"] == "executable"
    assert calls == ["/artifacts/hello -version"]
    assert session.status == "verified"
    assert session.error is None
    assert session.completed_at is None
    assert all(command.stage != "submit" for command in session.commands)
    assert (Path(session.metadata_path).parent / "repro" / "build.sh").exists()


@pytest.mark.parametrize(
    ("filename", "file_type", "expected_type"),
    [
        ("libapp.so", "shared", "shared_library"),
        ("app.o", "object", "object"),
        ("libapp.a", "archive", "static_library"),
    ],
)
def test_submit_accepts_non_executable_compiled_outputs_without_smoke(tmp_path: Path, monkeypatch, filename: str, file_type: str, expected_type: str):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id=f"thread-{file_type}", repo_url="https://example.com/repo.git")
    session.commit_sha = "a" * 40
    add_replayable_build_command(session, f"cmake --build build && cp build/{filename} /artifacts/{filename}")
    manager.save_session(session)
    artifact = Path(session.leadagent_artifacts_dir) / filename
    if file_type == "shared":
        write_elf(artifact, 3)
    elif file_type == "object":
        write_elf(artifact, 1)
    else:
        write_static_archive(artifact)

    def fail_exec(*args, **kwargs):
        raise AssertionError("Non-executable compiled artifacts must not be smoke-tested")

    install_passed_replay_stub(monkeypatch)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=SimpleNamespace(exec=fail_exec)))

    payload = json.loads(submit_build_result_impl(session=session))

    assert payload["status"] == "passed"
    assert payload["artifacts"][0]["artifact_type"] == expected_type
    assert session.status == "verified"


def test_submit_resuming_after_parent_finalization_cannot_create_replay_or_overwrite_cancelled_session(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-late-submit", repo_url="https://example.com/repo.git")
    session.status = "inspected"
    session.commit_sha = "a" * 40
    session.image_id = VALID_IMAGE_ID
    add_replayable_build_command(session, "cmake --build build && cp build/hello /artifacts/hello")
    manager.save_session(session)
    write_elf(Path(session.leadagent_artifacts_dir) / "hello", 2)
    entered = threading.Event()
    release = threading.Event()

    class GatedSubmitRuntime(FakeReplayRuntime):
        def exec(self, _session: CompileSession, command: str, **_kwargs) -> CommandResult:
            assert command == "/artifacts/hello -version"
            entered.set()
            assert release.wait(10)
            return CommandResult(
                exit_code=0,
                stdout="Hello Matt!\n",
                stderr="",
                combined_output="Hello Matt!\n",
            )

        def stop_and_remove_container(self, _session: CompileSession) -> ContainerCleanupResult:
            return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    runtime = GatedSubmitRuntime(manager)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(submit_build_result_impl, session=session)
        try:
            assert entered.wait(5)
            parent_session = manager.load_session(session.session_id, session.thread_id)
            operations.cleanup_and_finalize_compile_session_impl(
                session=parent_session,
                interrupted_status="cancelled",
                error="Parent run was cancelled.",
            )
            authoritative = manager.load_session(session.session_id, session.thread_id)
            terminal_snapshot = (
                authoritative.status,
                authoritative.error,
                authoritative.summary,
                authoritative.completed_at,
                authoritative.finalized_at,
                authoritative.termination_requested_at,
            )
        finally:
            release.set()
        payload = json.loads(future.result(timeout=10))

    reloaded = manager.load_session(session.session_id, session.thread_id)
    assert payload["status"] == "cancelled"
    assert terminal_snapshot[0] == "cancelled"
    assert (
        reloaded.status,
        reloaded.error,
        reloaded.summary,
        reloaded.completed_at,
        reloaded.finalized_at,
        reloaded.termination_requested_at,
    ) == terminal_snapshot
    assert reloaded.artifacts == []
    assert reloaded.verification is None
    assert reloaded.replay_attempts == []
    assert not any(event[0] == "create" for event in runtime.events)
    workflow_events = [json.loads(line) for line in (Path(reloaded.leadagent_logs_dir) / "workflow.log").read_text(encoding="utf-8").splitlines()]
    assert not any(event["event"] in {"replay.started", "verification.accepted"} for event in workflow_events)
    assert sum(event["event"] == "finalize.completed" for event in workflow_events) == 1


def test_clean_replay_matching_executable_persists_structured_checks_and_cleans_up(tmp_path: Path, monkeypatch):
    manager, session = make_replay_ready_session(tmp_path)
    original_artifact = Path(session.leadagent_artifacts_dir) / "hello"
    original_sha256 = hashlib.sha256(original_artifact.read_bytes()).hexdigest()
    workspace_sentinel = Path(session.leadagent_repo_dir) / "original-session-state"
    workspace_sentinel.parent.mkdir(parents=True, exist_ok=True)
    workspace_sentinel.write_text("must remain untouched\n", encoding="utf-8")
    runtime = FakeReplayRuntime(manager)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    attempt = verify_clean_replay_impl(session=session, timeout_seconds=20)

    assert attempt.status == "passed"
    assert attempt.failure_classification is None
    assert attempt.exit_code == 0
    assert attempt.cleanup_succeeded is True
    assert attempt.image_id == VALID_IMAGE_ID
    assert attempt.commit_sha == "a" * 40
    assert attempt.duration_seconds is not None
    assert attempt.duration_seconds >= 0
    checks = {check.name: check for check in attempt.checks}
    expected_checks = {
        "recipe_snapshot",
        "image_identity",
        "recipe_execution",
        "artifact_set",
        "artifact_1_type",
        "artifact_1_size",
        "artifact_1_sha256",
        "artifact_1_smoke",
        "container_cleanup",
    }
    assert expected_checks <= checks.keys()
    assert all(checks[name].passed for name in expected_checks)
    assert checks["artifact_set"].expected == ["hello"]
    assert checks["artifact_set"].actual == ["hello"]
    assert checks["artifact_1_sha256"].expected == original_sha256
    assert checks["artifact_1_sha256"].actual == original_sha256
    assert checks["artifact_1_smoke"].actual == {
        "command": "/artifacts/hello -version",
        "exit_code": 0,
        "output": "Hello Matt!\n",
        "output_sha256": hashlib.sha256(b"Hello Matt!\n").hexdigest(),
    }
    assert len(attempt.artifacts) == 1
    comparison = attempt.artifacts[0]
    assert comparison.path == "hello"
    assert comparison.type_matches is True
    assert comparison.size_matches is True
    assert comparison.sha256_matches is True
    assert comparison.smoke_matches is True
    assert comparison.passed is True
    assert runtime.events[-1] == ("cleanup", "replay-container-id", f"replay-{attempt.attempt_id}")
    assert sum(event[0] == "cleanup" for event in runtime.events) == 1
    assert hashlib.sha256(original_artifact.read_bytes()).hexdigest() == original_sha256
    assert workspace_sentinel.read_text(encoding="utf-8") == "must remain untouched\n"
    reloaded = manager.load_session(session.session_id, session.thread_id)
    assert reloaded.status == "replay_verifying"
    assert reloaded.replay_attempts[-1].status == "passed"


def test_clean_replay_rejects_recipe_that_depends_on_failed_command_side_effect(tmp_path: Path, monkeypatch):
    failed_configure = BuildCommandRecord(
        stage="bash",
        command="cmake -S . -B build && false",
        workdir="/workspace/repo",
        exit_code=1,
    )
    successful_build = BuildCommandRecord(
        stage="bash",
        command="cmake --build build && cp build/hello /artifacts/hello",
        workdir="/workspace/repo",
        exit_code=0,
    )
    manager, session = make_replay_ready_session(tmp_path, commands=[failed_configure, successful_build])
    original_history = [record.__dict__.copy() for record in session.commands]
    script = (Path(session.leadagent_repro_dir) / "build.sh").read_text(encoding="utf-8")
    assert failed_configure.command not in script
    assert successful_build.command in script
    runtime = FakeReplayRuntime(manager, build_exit_code=2)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    attempt = verify_clean_replay_impl(session=session)

    assert attempt.status == "failed"
    assert attempt.failure_classification == "recipe_execution_failed"
    assert attempt.exit_code == 2
    assert attempt.cleanup_succeeded is True
    assert next(check for check in attempt.checks if check.name == "recipe_execution").passed is False
    assert not any(check.name == "artifact_set" for check in attempt.checks)
    assert [record.__dict__.copy() for record in session.commands] == original_history
    reloaded = manager.load_session(session.session_id, session.thread_id)
    assert [record.__dict__.copy() for record in reloaded.commands] == original_history


def test_clean_replay_same_type_and_size_sha_mismatch_is_not_verified(tmp_path: Path, monkeypatch):
    manager, session = make_replay_ready_session(tmp_path)

    def mutate_entry_point(path: Path) -> None:
        payload = bytearray(path.read_bytes())
        payload[24] ^= 1
        path.write_bytes(payload)
        assert _classify_compiled_artifact(path) == "executable"

    runtime = FakeReplayRuntime(manager, mutate_replay_artifact=mutate_entry_point)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    attempt = verify_clean_replay_impl(session=session)

    assert attempt.status == "failed"
    assert attempt.failure_classification == "sha256_mismatch"
    comparison = attempt.artifacts[0]
    assert comparison.type_matches is True
    assert comparison.size_matches is True
    assert comparison.sha256_matches is False
    assert comparison.smoke_matches is True
    assert comparison.mismatches == ["sha256"]
    assert comparison.expected_sha256 != comparison.actual_sha256
    assert next(check for check in attempt.checks if check.name == "artifact_1_sha256").passed is False
    assert attempt.cleanup_succeeded is True


def test_clean_replay_artifact_set_mismatch_is_not_verified(tmp_path: Path, monkeypatch):
    manager, session = make_replay_ready_session(tmp_path)

    def replace_expected_artifact(path: Path) -> None:
        path.unlink()
        write_elf(path.with_name("unexpected"), 2)

    runtime = FakeReplayRuntime(manager, mutate_replay_artifact=replace_expected_artifact)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    attempt = verify_clean_replay_impl(session=session)

    assert attempt.status == "failed"
    assert attempt.failure_classification == "artifact_set_mismatch"
    artifact_set = next(check for check in attempt.checks if check.name == "artifact_set")
    assert artifact_set.expected == ["hello"]
    assert artifact_set.actual == ["unexpected"]
    assert artifact_set.passed is False


def test_clean_replay_artifact_type_mismatch_is_not_verified(tmp_path: Path, monkeypatch):
    manager, session = make_replay_ready_session(tmp_path)
    runtime = FakeReplayRuntime(manager, mutate_replay_artifact=lambda path: write_elf(path, 3))
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    attempt = verify_clean_replay_impl(session=session)

    assert attempt.status == "failed"
    assert attempt.failure_classification == "type_mismatch"
    comparison = attempt.artifacts[0]
    assert comparison.expected_type == "executable"
    assert comparison.actual_type == "shared_library"
    assert comparison.type_matches is False


def test_clean_replay_artifact_size_mismatch_is_not_verified(tmp_path: Path, monkeypatch):
    manager, session = make_replay_ready_session(tmp_path)

    def append_valid_trailing_bytes(path: Path) -> None:
        path.write_bytes(path.read_bytes() + b"trailing-bytes")
        assert _classify_compiled_artifact(path) == "executable"

    runtime = FakeReplayRuntime(manager, mutate_replay_artifact=append_valid_trailing_bytes)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    attempt = verify_clean_replay_impl(session=session)

    assert attempt.status == "failed"
    assert attempt.failure_classification == "size_mismatch"
    comparison = attempt.artifacts[0]
    assert comparison.type_matches is True
    assert comparison.size_matches is False
    assert comparison.actual_size_bytes > comparison.expected_size_bytes


@pytest.mark.parametrize("artifact_type", ["shared_library", "static_library"])
def test_clean_replay_accepts_matching_non_executable_artifacts_without_smoke(tmp_path: Path, monkeypatch, artifact_type: str):
    manager, session = make_replay_ready_session(tmp_path)
    artifact_path = Path(session.leadagent_artifacts_dir) / "hello"
    if artifact_type == "shared_library":
        write_elf(artifact_path, 3)
    else:
        write_static_archive(artifact_path)
    payload = artifact_path.read_bytes()
    session.artifacts = [
        BuildArtifact(
            path=manager.relative_path(session, artifact_path),
            artifact_type=artifact_type,
            size_bytes=len(payload),
            source_path="/artifacts/hello",
            sha256=hashlib.sha256(payload).hexdigest(),
        )
    ]
    manager.save_session(session)
    runtime = FakeReplayRuntime(manager)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    attempt = verify_clean_replay_impl(session=session)

    assert attempt.status == "passed"
    comparison = attempt.artifacts[0]
    assert comparison.actual_type == artifact_type
    assert comparison.smoke_matches is True
    assert comparison.actual_smoke_command is None
    assert [event[1] for event in runtime.events if event[0] == "exec"] == ["bash /repro/build.sh"]


def test_clean_replay_timeout_is_classified_and_always_cleaned_up(tmp_path: Path, monkeypatch):
    manager, session = make_replay_ready_session(tmp_path)
    runtime = FakeReplayRuntime(manager, build_exit_code=124)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    attempt = verify_clean_replay_impl(session=session, timeout_seconds=7)

    assert attempt.status == "timed_out"
    assert attempt.failure_classification == "timeout"
    assert attempt.exit_code == 124
    assert attempt.cleanup_succeeded is True
    assert next(check for check in attempt.checks if check.name == "recipe_execution").actual == 124
    assert not any(check.name == "artifact_set" for check in attempt.checks)
    create_event = next(event for event in runtime.events if event[0] == "create")
    build_event = next(event for event in runtime.events if event[:2] == ("exec", "bash /repro/build.sh"))
    assert 1 <= create_event[2] <= 7
    assert 1 <= build_event[2] <= 7
    assert runtime.events[-1][0] == "cleanup"


def test_clean_replay_base_exception_persists_cancellation_cleans_up_and_reraises(tmp_path: Path, monkeypatch):
    manager, session = make_replay_ready_session(tmp_path)
    runtime = FakeReplayRuntime(manager, build_exception=KeyboardInterrupt())
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    with pytest.raises(KeyboardInterrupt):
        verify_clean_replay_impl(session=session)

    assert runtime.events[-1][0] == "cleanup"
    assert sum(event[0] == "cleanup" for event in runtime.events) == 1
    reloaded = manager.load_session(session.session_id, session.thread_id)
    attempt = reloaded.replay_attempts[-1]
    assert attempt.status == "cancelled"
    assert attempt.failure_classification == "cancelled"
    assert attempt.cleanup_succeeded is True
    assert attempt.completed_at is not None
    assert any("KeyboardInterrupt" in note for note in attempt.notes)


def test_clean_replay_cleanup_failure_blocks_an_otherwise_matching_result(tmp_path: Path, monkeypatch):
    manager, session = make_replay_ready_session(tmp_path)
    runtime = FakeReplayRuntime(
        manager,
        cleanup_result=ContainerCleanupResult(succeeded=False, stopped=True, removed=False),
    )
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    attempt = verify_clean_replay_impl(session=session)

    assert attempt.status == "failed"
    assert attempt.failure_classification == "cleanup_failed"
    assert attempt.exit_code == 0
    assert attempt.cleanup_succeeded is False
    assert attempt.artifacts[0].passed is True
    cleanup_check = next(check for check in attempt.checks if check.name == "container_cleanup")
    assert cleanup_check.passed is False
    assert cleanup_check.actual == {"stopped": True, "removed": False}


def test_clean_replay_preserves_execution_failure_as_primary_when_cleanup_also_fails(tmp_path: Path, monkeypatch):
    manager, session = make_replay_ready_session(tmp_path)
    runtime = FakeReplayRuntime(
        manager,
        build_exit_code=2,
        cleanup_result=ContainerCleanupResult(succeeded=False, stopped=True, removed=False),
    )
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    attempt = verify_clean_replay_impl(session=session)

    assert attempt.status == "failed"
    assert attempt.failure_classification == "recipe_execution_failed"
    assert attempt.primary_failure_classification == "recipe_execution_failed"
    assert attempt.secondary_failure_classifications == ["cleanup_failed"]
    assert attempt.cleanup_succeeded is False


def test_replay_schema_roundtrip_preserves_structured_checks_and_artifacts(tmp_path: Path):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-replay-schema", repo_url="https://example.com/repo.git")
    session.image_id = VALID_IMAGE_ID
    session.replay_attempts = [
        ReplayVerificationResult(
            attempt_id="attempt-schema",
            status="failed",
            image=session.image,
            image_id=VALID_IMAGE_ID,
            commit_sha="a" * 40,
            recipe_sha256="b" * 64,
            timeout_seconds=45,
            cleanup_succeeded=True,
            failure_classification="sha256_mismatch",
            checks=[
                VerificationCheck(
                    name="artifact_1_sha256",
                    target="hello",
                    command="clean_replay",
                    passed=False,
                    expected="c" * 64,
                    actual="d" * 64,
                )
            ],
            artifacts=[
                ReplayArtifactComparison(
                    path="hello",
                    expected_type="executable",
                    actual_type="executable",
                    expected_size_bytes=120,
                    actual_size_bytes=120,
                    expected_sha256="c" * 64,
                    actual_sha256="d" * 64,
                    expected_smoke_output_sha256="e" * 64,
                    actual_smoke_output_sha256="f" * 64,
                    type_matches=True,
                    size_matches=True,
                    smoke_matches=True,
                    mismatches=["sha256"],
                )
            ],
        )
    ]
    manager.save_session(session)

    loaded = manager.load_session(session.session_id, session.thread_id)

    assert isinstance(loaded.replay_attempts[0], ReplayVerificationResult)
    assert isinstance(loaded.replay_attempts[0].checks[0], VerificationCheck)
    assert isinstance(loaded.replay_attempts[0].artifacts[0], ReplayArtifactComparison)
    assert loaded.replay_attempts[0].checks[0].expected == "c" * 64
    assert loaded.replay_attempts[0].artifacts[0].mismatches == ["sha256"]
    assert loaded.replay_attempts[0].timeout_seconds == 45
    assert loaded.replay_attempts[0].artifacts[0].expected_smoke_output_sha256 == "e" * 64


def test_compile_session_loads_legacy_metadata_without_replay_fields(tmp_path: Path):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-legacy-schema", repo_url="https://example.com/repo.git")
    payload = session.to_dict()
    payload.pop("image_id")
    payload.pop("replay_attempts")
    Path(session.metadata_path).write_text(json.dumps(payload), encoding="utf-8")

    loaded = manager.load_session(session.session_id, session.thread_id)

    assert loaded.image_id is None
    assert loaded.replay_attempts == []


def test_replay_docker_command_uses_immutable_image_isolated_mounts_read_only_recipe_and_timeout(tmp_path: Path, monkeypatch):
    paths = make_test_paths(tmp_path)
    manager = CompileSessionManager(paths=paths)
    session = manager.create_session(thread_id="thread-replay-runtime", repo_url="https://example.com/repo.git")
    session.image_id = VALID_IMAGE_ID
    attempt_id = "attempt123"
    recipe_dir = get_replay_recipe_dir(session.session_id, session.thread_id, attempt_id, paths)
    workspace_dir = get_replay_workspace_dir(session.session_id, session.thread_id, attempt_id, paths)
    artifacts_dir = get_replay_artifacts_dir(session.session_id, session.thread_id, attempt_id, paths)
    logs_dir = get_replay_logs_dir(session.session_id, session.thread_id, attempt_id, paths)
    for directory in (recipe_dir, workspace_dir, artifacts_dir, logs_dir):
        directory.mkdir(parents=True, exist_ok=True)
    (recipe_dir / "build.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    calls: list[tuple[list[str], dict]] = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[:3] == ["docker", "network", "inspect"]:
            return SimpleNamespace(returncode=0, stdout="network\n", stderr="")
        if command[:3] == ["docker", "inspect", "--format"]:
            return SimpleNamespace(returncode=0, stdout=f"{VALID_IMAGE_ID}\n", stderr="")
        if command[:2] == ["docker", "run"]:
            return SimpleNamespace(returncode=0, stdout="replay-container-id\n", stderr="")
        if command[:2] == ["docker", "exec"]:
            return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")
        raise AssertionError(f"Unexpected Docker command: {command}")

    monkeypatch.setattr("deerflow.compile.docker_runtime.subprocess.run", fake_run)
    runtime = CompileDockerRuntime(config=RuntimeConfig(network=DEFAULT_NETWORK, replay_timeout_seconds=30), manager=manager)

    handle = runtime.create_replay_container(session, attempt_id=attempt_id, timeout_seconds=17)
    result = runtime.exec_replay_container(session, handle, timeout_seconds=11)

    assert result.exit_code == 0
    docker_run, run_kwargs = next((command, kwargs) for command, kwargs in calls if command[:2] == ["docker", "run"])
    assert docker_run[-4:] == [VALID_IMAGE_ID, "tail", "-f", "/dev/null"]
    assert session.image not in docker_run
    assert f"{get_host_replay_recipe_dir(session.session_id, session.thread_id, attempt_id, paths)}:/repro:ro" in docker_run
    assert f"{get_host_replay_workspace_dir(session.session_id, session.thread_id, attempt_id, paths)}:/workspace" in docker_run
    assert f"{get_host_replay_artifacts_dir(session.session_id, session.thread_id, attempt_id, paths)}:/artifacts" in docker_run
    assert f"{get_host_replay_logs_dir(session.session_id, session.thread_id, attempt_id, paths)}:/logs" in docker_run
    assert all(f"{get_host_workspace_dir(session.session_id, session.thread_id, paths)}:" not in item for item in docker_run)
    assert run_kwargs["timeout"] == 17
    docker_exec, exec_kwargs = next((command, kwargs) for command, kwargs in calls if command[:2] == ["docker", "exec"])
    assert docker_exec[-7:] == ["timeout", "--signal=TERM", "--kill-after=5s", "11s", "bash", "-lc", "bash /repro/build.sh"]
    assert exec_kwargs["timeout"] == 21


def test_clean_replay_create_timeout_is_persisted_as_timed_out(tmp_path: Path, monkeypatch):
    manager, session = make_replay_ready_session(tmp_path)

    class CreateTimeoutRuntime(FakeReplayRuntime):
        def create_replay_container(self, session: CompileSession, *, attempt_id: str, timeout_seconds: int):
            self.attempt_id = attempt_id
            raise subprocess.TimeoutExpired(["docker", "network", "inspect"], timeout_seconds)

    runtime = CreateTimeoutRuntime(manager)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    attempt = verify_clean_replay_impl(session=session, timeout_seconds=7)

    assert attempt.status == "timed_out"
    assert attempt.failure_classification == "timeout"
    assert attempt.timeout_seconds == 7
    assert attempt.completed_at is not None
    assert attempt.duration_seconds is not None
    reloaded = manager.load_session(session.session_id, session.thread_id).replay_attempts[-1]
    assert reloaded.status == "timed_out"
    assert reloaded.timeout_seconds == 7


def test_parent_recorded_replay_cancellation_wins_over_worker_save(tmp_path: Path, monkeypatch):
    manager, session = make_replay_ready_session(tmp_path)

    class ParentCancellingRuntime(FakeReplayRuntime):
        def exec_replay_container(self, session: CompileSession, handle: ReplayContainerHandle, **kwargs):
            if kwargs.get("command", "bash /repro/build.sh") == "bash /repro/build.sh":
                current = self.manager.load_session(session.session_id, session.thread_id)
                authoritative = current.replay_attempts[-1]
                authoritative.status = "cancelled"
                authoritative.failure_classification = "cancelled"
                authoritative.cleanup_succeeded = True
                authoritative.completed_at = authoritative.completed_at or operations.utc_now_iso()
                authoritative.notes.append("Parent cancellation is authoritative.")
                self.manager.save_session(current)
            return super().exec_replay_container(session, handle, **kwargs)

    runtime = ParentCancellingRuntime(manager)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    attempt = verify_clean_replay_impl(session=session)

    assert attempt.status == "cancelled"
    assert attempt.failure_classification == "cancelled"
    assert attempt.cleanup_succeeded is True
    assert "Parent cancellation is authoritative." in attempt.notes
    reloaded = manager.load_session(session.session_id, session.thread_id).replay_attempts[-1]
    assert reloaded.status == "cancelled"
    assert reloaded.failure_classification == "cancelled"


def test_parent_cancellation_before_docker_run_prevents_replay_creation(tmp_path: Path, monkeypatch):
    manager, session = make_replay_ready_session(tmp_path)

    class CancelBeforeCreateRuntime(FakeReplayRuntime):
        def replay_container_name(self, session: CompileSession, attempt_id: str) -> str:
            current = self.manager.load_session(session.session_id, session.thread_id)
            operations.cleanup_compile_session_container_impl(session=current)
            return super().replay_container_name(session, attempt_id)

        def stop_and_remove_container(self, _session: CompileSession):
            return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

        def create_replay_container(self, *args, **kwargs):
            self.events.append(("create", args, kwargs))
            raise AssertionError("Cancellation before docker run must prevent replay container creation")

    runtime = CancelBeforeCreateRuntime(manager)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    attempt = verify_clean_replay_impl(session=session)

    assert attempt.status == "cancelled"
    assert attempt.failure_classification == "cancelled"
    assert not any(event[0] == "create" for event in runtime.events)
    assert attempt.cleanup_succeeded is True


def test_parent_cleanup_waits_for_replay_create_checkpoint_and_removes_by_container_id(tmp_path: Path, monkeypatch):
    manager, session = make_replay_ready_session(tmp_path)
    create_entered = threading.Event()
    release_create = threading.Event()
    cleanup_started = threading.Event()
    parent_removed_container = threading.Event()
    cleanup_calls: list[tuple[bool, str | None]] = []

    class GatedCreateRuntime(FakeReplayRuntime):
        def create_replay_container(self, session: CompileSession, *, attempt_id: str, timeout_seconds: int) -> ReplayContainerHandle:
            create_entered.set()
            assert release_create.wait(10)
            return super().create_replay_container(
                session,
                attempt_id=attempt_id,
                timeout_seconds=timeout_seconds,
            )

        def exec_replay_container(self, session: CompileSession, handle: ReplayContainerHandle, **kwargs) -> CommandResult:
            if kwargs.get("command", "bash /repro/build.sh") == "bash /repro/build.sh":
                assert parent_removed_container.wait(10)
            return super().exec_replay_container(session, handle, **kwargs)

        def stop_and_remove_replay_container(
            self,
            session: CompileSession,
            handle: ReplayContainerHandle | None = None,
            *,
            container_id: str | None = None,
            container_name: str | None = None,
        ) -> ContainerCleanupResult:
            resolved_id = handle.container_id if handle is not None else container_id
            cleanup_calls.append((handle is None, resolved_id))
            if handle is None:
                parent_removed_container.set()
            return super().stop_and_remove_replay_container(
                session,
                handle,
                container_id=container_id,
                container_name=container_name,
            )

        def stop_and_remove_container(self, _session: CompileSession) -> ContainerCleanupResult:
            return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    runtime = GatedCreateRuntime(manager)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    def parent_cleanup():
        cleanup_started.set()
        current = manager.load_session(session.session_id, session.thread_id)
        return operations.cleanup_compile_session_container_impl(
            session=current,
            interrupted_status="cancelled",
            error="Parent run was cancelled.",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        replay_future = pool.submit(verify_clean_replay_impl, session=session)
        assert create_entered.wait(5)
        cleanup_future = pool.submit(parent_cleanup)
        assert cleanup_started.wait(5)
        assert not parent_removed_container.is_set()
        release_create.set()
        _updated, cleanup_result = cleanup_future.result(timeout=10)
        attempt = replay_future.result(timeout=10)

    assert cleanup_result.succeeded is True
    assert cleanup_calls[0] == (True, "replay-container-id")
    assert attempt.status == "cancelled"
    authoritative = manager.load_session(session.session_id, session.thread_id)
    assert authoritative.termination_status == "cancelled"
    assert authoritative.replay_attempts[-1].container_id == "replay-container-id"


def test_clean_replay_compares_full_smoke_output_hash_beyond_preview(tmp_path: Path, monkeypatch):
    manager, session = make_replay_ready_session(tmp_path)
    shared_preview = "x" * 4000
    expected_output = shared_preview + "expected suffix\n"
    actual_output = shared_preview + "different suffix\n"
    session.artifacts[0].smoke_output = shared_preview
    session.artifacts[0].smoke_output_sha256 = hashlib.sha256(expected_output.encode()).hexdigest()
    manager.save_session(session)
    runtime = FakeReplayRuntime(manager, smoke_output=actual_output)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))

    attempt = verify_clean_replay_impl(session=session)

    assert attempt.status == "failed"
    assert attempt.failure_classification == "smoke_mismatch"
    comparison = attempt.artifacts[0]
    assert comparison.expected_smoke_output == comparison.actual_smoke_output == shared_preview
    assert comparison.expected_smoke_output_sha256 != comparison.actual_smoke_output_sha256
    assert comparison.smoke_matches is False


def test_replay_network_inspect_timeout_is_bounded(tmp_path: Path, monkeypatch):
    paths = make_test_paths(tmp_path)
    manager = CompileSessionManager(paths=paths)
    session = manager.create_session(thread_id="thread-network-timeout", repo_url="https://example.com/repo.git")
    session.image_id = VALID_IMAGE_ID
    attempt_id = "network-timeout"
    recipe_dir = get_replay_recipe_dir(session.session_id, session.thread_id, attempt_id, paths)
    for directory in (
        recipe_dir,
        get_replay_workspace_dir(session.session_id, session.thread_id, attempt_id, paths),
        get_replay_artifacts_dir(session.session_id, session.thread_id, attempt_id, paths),
        get_replay_logs_dir(session.session_id, session.thread_id, attempt_id, paths),
    ):
        directory.mkdir(parents=True, exist_ok=True)
    (recipe_dir / "build.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

    def fake_run(command, **kwargs):
        assert command[:3] == ["docker", "network", "inspect"]
        assert 1 <= kwargs["timeout"] <= 4
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr("deerflow.compile.docker_runtime.subprocess.run", fake_run)
    runtime = CompileDockerRuntime(config=RuntimeConfig(network=DEFAULT_NETWORK), manager=manager)

    with pytest.raises(subprocess.TimeoutExpired):
        runtime.create_replay_container(session, attempt_id=attempt_id, timeout_seconds=4)


def test_replay_run_timeout_retries_cleanup_until_late_container_is_removed(tmp_path: Path, monkeypatch):
    paths = make_test_paths(tmp_path)
    manager = CompileSessionManager(paths=paths)
    session = manager.create_session(thread_id="thread-run-timeout-late-create", repo_url="https://example.com/repo.git")
    session.image_id = VALID_IMAGE_ID
    attempt_id = "run-timeout-late-create"
    recipe_dir = get_replay_recipe_dir(session.session_id, session.thread_id, attempt_id, paths)
    for directory in (
        recipe_dir,
        get_replay_workspace_dir(session.session_id, session.thread_id, attempt_id, paths),
        get_replay_artifacts_dir(session.session_id, session.thread_id, attempt_id, paths),
        get_replay_logs_dir(session.session_id, session.thread_id, attempt_id, paths),
    ):
        directory.mkdir(parents=True, exist_ok=True)
    (recipe_dir / "build.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    run_timeout = subprocess.TimeoutExpired(["docker", "run"], 5)
    remove_calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        if command[:3] == ["docker", "network", "inspect"]:
            return SimpleNamespace(returncode=0, stdout="network\n", stderr="")
        if command[:2] == ["docker", "run"]:
            raise run_timeout
        if command[:3] == ["docker", "rm", "-f"]:
            remove_calls.append(command)
            if len(remove_calls) == 1:
                return SimpleNamespace(returncode=1, stdout="", stderr="Error: No such container")
            return SimpleNamespace(returncode=0, stdout=f"{command[-1]}\n", stderr="")
        raise AssertionError(f"Unexpected Docker command: {command}")

    monkeypatch.setattr("deerflow.compile.docker_runtime.subprocess.run", fake_run)
    runtime = CompileDockerRuntime(
        config=RuntimeConfig(network=DEFAULT_NETWORK, cleanup_timeout_seconds=3),
        manager=manager,
    )

    with pytest.raises(subprocess.TimeoutExpired) as exc_info:
        runtime.create_replay_container(session, attempt_id=attempt_id, timeout_seconds=5)

    assert exc_info.value is run_timeout
    assert len(remove_calls) == 2
    assert all(command[-1] == runtime.replay_container_name(session, attempt_id) for command in remove_calls)


def test_replay_run_timeout_reconciliation_is_bounded_when_container_never_appears(tmp_path: Path, monkeypatch):
    paths = make_test_paths(tmp_path)
    manager = CompileSessionManager(paths=paths)
    session = manager.create_session(thread_id="thread-run-timeout-missing", repo_url="https://example.com/repo.git")
    session.image_id = VALID_IMAGE_ID
    attempt_id = "run-timeout-missing"
    recipe_dir = get_replay_recipe_dir(session.session_id, session.thread_id, attempt_id, paths)
    for directory in (
        recipe_dir,
        get_replay_workspace_dir(session.session_id, session.thread_id, attempt_id, paths),
        get_replay_artifacts_dir(session.session_id, session.thread_id, attempt_id, paths),
        get_replay_logs_dir(session.session_id, session.thread_id, attempt_id, paths),
    ):
        directory.mkdir(parents=True, exist_ok=True)
    (recipe_dir / "build.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    clock = [0.0]
    remove_timeouts: list[float] = []
    run_timeout = subprocess.TimeoutExpired(["docker", "run"], 5)

    def fake_monotonic() -> float:
        return clock[0]

    def fake_sleep(seconds: float) -> None:
        clock[0] += seconds

    def fake_run(command, **kwargs):
        if command[:3] == ["docker", "network", "inspect"]:
            return SimpleNamespace(returncode=0, stdout="network\n", stderr="")
        if command[:2] == ["docker", "run"]:
            raise run_timeout
        if command[:3] == ["docker", "rm", "-f"]:
            remove_timeouts.append(kwargs["timeout"])
            return SimpleNamespace(returncode=1, stdout="", stderr="Error: No such container")
        raise AssertionError(f"Unexpected Docker command: {command}")

    monkeypatch.setattr("deerflow.compile.docker_runtime.time.monotonic", fake_monotonic)
    monkeypatch.setattr("deerflow.compile.docker_runtime.time.sleep", fake_sleep)
    monkeypatch.setattr("deerflow.compile.docker_runtime.subprocess.run", fake_run)
    runtime = CompileDockerRuntime(
        config=RuntimeConfig(network=DEFAULT_NETWORK, cleanup_timeout_seconds=2),
        manager=manager,
    )

    with pytest.raises(subprocess.TimeoutExpired) as exc_info:
        runtime.create_replay_container(session, attempt_id=attempt_id, timeout_seconds=5)

    assert exc_info.value is run_timeout
    assert clock[0] == 2.0
    assert len(remove_timeouts) == 4
    assert all(0 < timeout <= 2.0 for timeout in remove_timeouts)


def test_replay_image_inspect_timeout_cleans_by_precomputed_name(tmp_path: Path, monkeypatch):
    paths = make_test_paths(tmp_path)
    manager = CompileSessionManager(paths=paths)
    session = manager.create_session(thread_id="thread-image-timeout", repo_url="https://example.com/repo.git")
    session.image_id = VALID_IMAGE_ID
    attempt_id = "image-timeout"
    recipe_dir = get_replay_recipe_dir(session.session_id, session.thread_id, attempt_id, paths)
    for directory in (
        recipe_dir,
        get_replay_workspace_dir(session.session_id, session.thread_id, attempt_id, paths),
        get_replay_artifacts_dir(session.session_id, session.thread_id, attempt_id, paths),
        get_replay_logs_dir(session.session_id, session.thread_id, attempt_id, paths),
    ):
        directory.mkdir(parents=True, exist_ok=True)
    (recipe_dir / "build.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        assert kwargs.get("timeout") is not None
        if command[:3] == ["docker", "network", "inspect"]:
            return SimpleNamespace(returncode=0, stdout="network\n", stderr="")
        if command[:2] == ["docker", "run"]:
            return SimpleNamespace(returncode=0, stdout="late-container-id\n", stderr="")
        if command[:3] == ["docker", "inspect", "--format"]:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        if command[:2] == ["docker", "stop"] or command[:3] == ["docker", "rm", "-f"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="Error: No such container")
        raise AssertionError(f"Unexpected Docker command: {command}")

    monkeypatch.setattr("deerflow.compile.docker_runtime.subprocess.run", fake_run)
    runtime = CompileDockerRuntime(config=RuntimeConfig(network=DEFAULT_NETWORK), manager=manager)

    with pytest.raises(subprocess.TimeoutExpired):
        runtime.create_replay_container(session, attempt_id=attempt_id, timeout_seconds=5)

    assert any(command[:3] == ["docker", "rm", "-f"] for command in calls)


def test_cleanup_stop_timeout_falls_back_to_bounded_force_remove(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-cleanup-timeout", repo_url="https://example.com/repo.git")
    session.container_id = "container-timeout"
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        assert kwargs["timeout"] <= 4
        if command[:2] == ["docker", "stop"]:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        if command[:3] == ["docker", "rm", "-f"]:
            return SimpleNamespace(returncode=0, stdout="container-timeout\n", stderr="")
        raise AssertionError(f"Unexpected Docker command: {command}")

    monkeypatch.setattr("deerflow.compile.docker_runtime.subprocess.run", fake_run)
    runtime = CompileDockerRuntime(
        config=RuntimeConfig(remove_on_cleanup=True, cleanup_timeout_seconds=4),
        manager=manager,
    )

    result = runtime.stop_and_remove_container(session)

    assert result.succeeded is True
    assert result.stopped is False
    assert result.removed is True
    assert [command[:2] for command in calls] == [["docker", "stop"], ["docker", "rm"]]


def test_cleanup_remove_timeout_is_reported_without_hanging(tmp_path: Path, monkeypatch):
    manager = CompileSessionManager(paths=make_test_paths(tmp_path))
    session = manager.create_session(thread_id="thread-remove-timeout", repo_url="https://example.com/repo.git")
    session.container_id = "container-timeout"

    def fake_run(command, **kwargs):
        assert kwargs["timeout"] <= 4
        if command[:2] == ["docker", "stop"]:
            return SimpleNamespace(returncode=0, stdout="container-timeout\n", stderr="")
        if command[:3] == ["docker", "rm", "-f"]:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        raise AssertionError(f"Unexpected Docker command: {command}")

    monkeypatch.setattr("deerflow.compile.docker_runtime.subprocess.run", fake_run)
    runtime = CompileDockerRuntime(
        config=RuntimeConfig(remove_on_cleanup=True, cleanup_timeout_seconds=4),
        manager=manager,
    )

    result = runtime.stop_and_remove_container(session)

    assert result.succeeded is False
    assert result.stopped is True
    assert result.removed is False


def test_finalize_rejects_original_artifact_mutated_after_replay(tmp_path: Path, monkeypatch):
    manager, session = make_replay_ready_session(tmp_path)
    replay_runtime = FakeReplayRuntime(manager)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=replay_runtime))
    attempt = verify_clean_replay_impl(session=session)
    assert attempt.status == "passed"
    session.verification = VerificationResult(status="passed", artifact_count=1)
    manager.mark_session_status(session, "verified")

    artifact_path = Path(session.leadagent_artifacts_dir) / "hello"
    artifact_path.write_bytes(artifact_path.read_bytes() + b"changed-after-replay")

    def cleanup(_session: CompileSession):
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=SimpleNamespace(stop_and_remove_container=cleanup)),
    )

    updated, cleanup_result = operations.cleanup_and_finalize_compile_session_impl(session=session)

    assert cleanup_result.succeeded is True
    assert updated.status == "failed"
    assert updated.finalized_at is not None
    assert "changed after clean replay" in (updated.error or "")
    final_check = next(check for check in updated.verification.checks if check.name == "accepted_artifacts_unchanged_after_cleanup")
    assert final_check.passed is False
    assert "sha256:hello" in final_check.actual["mismatches"]
