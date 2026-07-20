from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow.compile import operations
from deerflow.compile.docker_runtime import ContainerCleanupResult
from deerflow.compile.evidence import ExperimentLedger
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.operations import CompileOperationsServices
from deerflow.config.paths import Paths
from deerflow.tools.builtins.task_tool import _with_benchmark_constraints

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "forge_benchmark_runner.py"
SPEC = importlib.util.spec_from_file_location("forge_benchmark_runner", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
forge_benchmark_runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(forge_benchmark_runner)


def load_manifest() -> dict:
    path = REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v1.json"
    return forge_benchmark_runner._load_manifest(path)


def load_v2_manifest() -> dict:
    path = REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v2.json"
    return forge_benchmark_runner._load_manifest(path)


def load_v3_manifest() -> dict:
    path = REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v3.json"
    return forge_benchmark_runner._load_manifest(path)


def ready_preflight(manifest: dict, *, ready: bool = True) -> dict:
    return {
        "ready": ready,
        "manifest_sha256": forge_benchmark_runner._manifest_sha256(manifest),
        "manifest_file_sha256": "1" * 64,
        "forge": {
            "revision": manifest["forge"]["commit_sha"],
            "dirty": False,
            "expected_revision": manifest["forge"]["commit_sha"],
            "components": {},
        },
        "protocol": {},
        "runtime": {
            "image_id": manifest["runtime"]["image_id"],
            "docker_server_version": manifest["runtime"]["host"]["docker_server_version"],
            "platform_system": "Linux",
            "platform_machine": "x86_64",
        },
        "checks": {"fixture_ready": ready},
    }


def test_build_policy_applies_frozen_case_and_model_constraints() -> None:
    manifest = load_manifest()

    policy = forge_benchmark_runner.build_policy(
        manifest,
        case_id="fmt",
        condition_id="baseline",
        repetition=1,
    )

    assert policy.model_name == "gpt-5.6-sol"
    assert policy.model_max_retries == 0
    assert policy.memory_enabled is False
    assert policy.skills_enabled is False
    assert policy.expected_commit_sha == manifest["cases"][0]["commit_sha"]
    assert policy.process_environment == manifest["cases"][0]["constraints"]["environment"]


@pytest.mark.parametrize(
    ("manifest_loader", "manifest_name"),
    [
        (load_v2_manifest, "cpp-pilot-v2.json"),
        (load_v3_manifest, "cpp-pilot-v3.json"),
    ],
)
def test_runnable_preflight_accepts_clean_descendant_with_frozen_components(
    monkeypatch: pytest.MonkeyPatch,
    manifest_loader,
    manifest_name: str,
) -> None:
    manifest = manifest_loader()
    expected_hashes = {
        **manifest["forge"]["component_sha256"],
        **manifest["protocol_artifact_sha256"],
    }

    monkeypatch.setattr(
        forge_benchmark_runner,
        "_git_state",
        lambda _repo_root: {"revision": "f" * 40, "dirty": False},
    )
    monkeypatch.setattr(
        forge_benchmark_runner,
        "_baseline_is_ancestor",
        lambda _repo_root, _baseline: True,
    )

    def frozen_sha(path: Path) -> str:
        normalized = path.as_posix()
        return next(
            (digest for relative_path, digest in expected_hashes.items() if normalized.endswith(relative_path)),
            "a" * 64,
        )

    monkeypatch.setattr(forge_benchmark_runner, "_sha256_file", frozen_sha)
    monkeypatch.setattr(forge_benchmark_runner, "_credential_present", lambda _name: True)
    monkeypatch.setattr(forge_benchmark_runner, "_endpoint_reachable", lambda _endpoint: True)
    monkeypatch.setattr(forge_benchmark_runner, "_compose_dood_present", lambda _repo_root: True)

    def docker_state(arguments: list[str], *, cwd: Path = REPO_ROOT) -> tuple[int, str]:
        del cwd
        if arguments[:3] == ["docker", "image", "inspect"]:
            return 0, manifest["runtime"]["image_id"]
        if arguments[:3] == ["docker", "network", "inspect"]:
            return 0, ""
        if arguments[:2] == ["docker", "version"]:
            return 0, manifest["runtime"]["host"]["docker_server_version"]
        raise AssertionError(arguments)

    monkeypatch.setattr(forge_benchmark_runner, "_run_command", docker_state)

    preflight = forge_benchmark_runner.collect_preflight(
        manifest,
        repo_root=REPO_ROOT,
        manifest_path=REPO_ROOT / "benchmarks" / "manifests" / manifest_name,
    )

    assert preflight["ready"] is True
    assert preflight["checks"]["forge_head_equals_baseline"] is False
    assert preflight["checks"]["forge_revision_matches"] is True
    assert preflight["checks"]["forge_baseline_is_ancestor"] is True
    assert preflight["checks"]["forge_baseline_satisfied"] is True
    assert preflight["checks"]["control_plane_topology_matches"] is True
    assert preflight["runtime"]["control_plane_topology"] == "compose-dood"


@pytest.mark.parametrize("manifest_loader", [load_v2_manifest, load_v3_manifest])
def test_runnable_preflight_rejects_missing_baseline_or_compose_dood(
    monkeypatch: pytest.MonkeyPatch,
    manifest_loader,
) -> None:
    manifest = manifest_loader()
    monkeypatch.setattr(
        forge_benchmark_runner,
        "_git_state",
        lambda _repo_root: {"revision": "f" * 40, "dirty": False},
    )
    monkeypatch.setattr(forge_benchmark_runner, "_baseline_is_ancestor", lambda *_args: False)
    monkeypatch.setattr(forge_benchmark_runner, "_compose_dood_present", lambda _repo_root: False)
    monkeypatch.setattr(forge_benchmark_runner, "_sha256_file", lambda _path: None)
    monkeypatch.setattr(forge_benchmark_runner, "_credential_present", lambda _name: True)
    monkeypatch.setattr(forge_benchmark_runner, "_endpoint_reachable", lambda _endpoint: True)
    monkeypatch.setattr(forge_benchmark_runner, "_run_command", lambda *_args, **_kwargs: (1, ""))

    preflight = forge_benchmark_runner.collect_preflight(manifest)

    assert preflight["ready"] is False
    assert preflight["checks"]["forge_revision_matches"] is False
    assert preflight["checks"]["forge_baseline_satisfied"] is False
    assert preflight["checks"]["control_plane_topology_matches"] is False


def test_compiler_prompt_receives_ordered_manifest_constraints() -> None:
    manifest = load_manifest()
    policy = forge_benchmark_runner.build_policy(
        manifest,
        case_id="fmt",
        condition_id="baseline",
        repetition=1,
    )

    prompt = _with_benchmark_constraints("Compile this repository.", policy)

    positions = [prompt.index(argument) for argument in policy.cmake_arguments]
    assert positions == sorted(positions)
    assert "command_role" in prompt
    assert "supporting_command_id" in prompt
    assert policy.credential_env not in prompt


def test_create_attempt_rejects_duplicate_slot_and_links_explicit_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    preflight = ready_preflight(manifest)
    monkeypatch.setattr(
        forge_benchmark_runner,
        "collect_preflight",
        lambda *args, **kwargs: preflight,
    )

    original, _ = forge_benchmark_runner.create_attempt(
        manifest,
        case_id="fmt",
        condition_id="baseline",
        repetition=1,
        output_dir=tmp_path,
    )
    with pytest.raises(forge_benchmark_runner.RunnerError, match="already has physical evidence"):
        forge_benchmark_runner.create_attempt(
            manifest,
            case_id="fmt",
            condition_id="baseline",
            repetition=1,
            output_dir=tmp_path,
        )

    replacement, _ = forge_benchmark_runner.create_attempt(
        manifest,
        case_id="fmt",
        condition_id="baseline",
        repetition=1,
        output_dir=tmp_path,
        replacement_for=original.physical_attempt_id,
    )

    assert replacement.experiment_id == original.experiment_id
    assert replacement.physical_attempt_id != original.physical_attempt_id
    assert replacement.read()[0]["payload"]["replacement_for_physical_attempt_id"] == original.physical_attempt_id


def test_run_refuses_failed_preflight_before_importing_model_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    preflight = ready_preflight(manifest, ready=False)
    monkeypatch.setattr(
        forge_benchmark_runner,
        "collect_preflight",
        lambda *args, **kwargs: preflight,
    )
    ledger, _ = forge_benchmark_runner.create_attempt(
        manifest,
        case_id="fmt",
        condition_id="baseline",
        repetition=1,
        output_dir=tmp_path,
    )

    with pytest.raises(forge_benchmark_runner.RunnerError, match="did not pass preflight"):
        forge_benchmark_runner.run_attempt(manifest, ledger.path)

    assert not any(event["event"].startswith("model.") for event in ledger.read())


@pytest.mark.parametrize("manifest_loader", [load_v2_manifest, load_v3_manifest])
def test_runnable_run_refuses_non_compose_process_before_model_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manifest_loader,
) -> None:
    manifest = manifest_loader()
    preflight = ready_preflight(manifest)
    monkeypatch.setattr(
        forge_benchmark_runner,
        "collect_preflight",
        lambda *args, **kwargs: preflight,
    )
    ledger, _ = forge_benchmark_runner.create_attempt(
        manifest,
        case_id="fmt",
        condition_id="baseline",
        repetition=1,
        output_dir=tmp_path,
    )
    monkeypatch.setattr(
        forge_benchmark_runner,
        "_running_inside_compose_dood",
        lambda _repo_root: False,
    )

    with pytest.raises(forge_benchmark_runner.RunnerError, match="frozen Compose/DooD"):
        forge_benchmark_runner.run_attempt(manifest, ledger.path)

    events = ledger.read()
    assert events[-1]["event"] == "runtime.topology_rejected"
    assert not any(event["event"].startswith("model.") for event in events)


def test_runner_defaults_to_v3_manifest() -> None:
    args = forge_benchmark_runner._build_parser().parse_args(["preflight"])

    assert args.manifest == REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v3.json"


def test_keyboard_interrupt_keeps_attempt_recoverable_and_reconciles_orphans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    preflight = ready_preflight(manifest)
    monkeypatch.setattr(
        forge_benchmark_runner,
        "collect_preflight",
        lambda *args, **kwargs: preflight,
    )
    ledger, _ = forge_benchmark_runner.create_attempt(
        manifest,
        case_id="fmt",
        condition_id="baseline",
        repetition=1,
        output_dir=tmp_path,
    )

    class InterruptingClient:
        def __init__(self, **kwargs) -> None:
            del kwargs

        def stream(self, message: str, *, thread_id: str):
            del message, thread_id
            raise KeyboardInterrupt

    import deerflow.client

    monkeypatch.setattr(deerflow.client, "DeerFlowClient", InterruptingClient)
    monkeypatch.setattr(
        forge_benchmark_runner,
        "reconcile_orphans",
        lambda _attempt_id: {
            "scan_succeeded": True,
            "orphan_count": 0,
            "removed_count": 0,
            "cleanup_succeeded": True,
        },
    )

    with pytest.raises(KeyboardInterrupt):
        forge_benchmark_runner.run_attempt(manifest, ledger.path)

    events = ExperimentLedger.verify_path(ledger.path)
    assert "run.failed" in [event["event"] for event in events]
    assert events[-1]["event"] == "orphan.reconciled"
    assert not any(event["event"] == "experiment.completed" for event in events)
    ExperimentLedger.open(ledger.path).append("recovery.recorded", {"status": "interrupted"})


@pytest.mark.parametrize("raise_error", [False, True])
def test_run_terminalizes_unfinished_session_after_client_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raise_error: bool,
) -> None:
    manifest = load_manifest()
    preflight = ready_preflight(manifest)
    monkeypatch.setattr(
        forge_benchmark_runner,
        "collect_preflight",
        lambda *args, **kwargs: preflight,
    )
    ledger, _ = forge_benchmark_runner.create_attempt(
        manifest,
        case_id="fmt",
        condition_id="baseline",
        repetition=1,
        output_dir=tmp_path / "evidence",
    )
    thread_id = ledger.read()[0]["payload"]["thread_id"]
    manager = CompileSessionManager(
        paths=Paths(
            base_dir=tmp_path / "state",
            workspace_root=tmp_path / "workspace",
            host_workspace_root=str(tmp_path / "workspace"),
        )
    )
    cleanup_calls: list[str] = []

    def stop_and_remove_container(session):
        cleanup_calls.append(session.session_id)
        return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)

    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(
            manager=manager,
            runtime=SimpleNamespace(stop_and_remove_container=stop_and_remove_container),
        ),
    )

    class ReturningClient:
        def __init__(self, **kwargs) -> None:
            del kwargs

        def stream(self, message: str, *, thread_id: str):
            del message
            session = manager.create_session(thread_id=thread_id, repo_url="https://example.com/repo.git")
            session.container_id = "container-123"
            manager.save_session(session)
            manager.mark_session_status(session, "ready")
            if raise_error:
                raise TimeoutError
            return iter(())

    import deerflow.client

    monkeypatch.setattr(deerflow.client, "DeerFlowClient", ReturningClient)
    monkeypatch.setattr(
        forge_benchmark_runner,
        "reconcile_orphans",
        lambda _attempt_id: {
            "scan_succeeded": True,
            "orphan_count": 0,
            "removed_count": 0,
            "cleanup_succeeded": True,
        },
    )

    result = forge_benchmark_runner.run_attempt(manifest, ledger.path)

    sessions = manager.list_sessions(thread_id)
    assert len(sessions) == 1
    finalized = manager.load_session(sessions[0].session_id, thread_id)
    assert finalized.status == "failed"
    assert finalized.finalized_at is not None
    assert (finalized.termination_status == "failed") is raise_error
    assert cleanup_calls == [finalized.session_id]
    assert result["session_finalization_succeeded"] is True
    completed = ledger.read()[-1]
    assert completed["event"] == "experiment.completed"
    assert completed["payload"]["session_finalization_succeeded"] is True


def test_run_retries_session_finalization_after_orphan_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    preflight = ready_preflight(manifest)
    monkeypatch.setattr(
        forge_benchmark_runner,
        "collect_preflight",
        lambda *args, **kwargs: preflight,
    )
    ledger, _ = forge_benchmark_runner.create_attempt(
        manifest,
        case_id="fmt",
        condition_id="baseline",
        repetition=1,
        output_dir=tmp_path / "evidence",
    )
    call_order: list[str] = []
    finalization_results = iter([False, True])

    class ReturningClient:
        def __init__(self, **kwargs) -> None:
            del kwargs

        def stream(self, message: str, *, thread_id: str):
            del message, thread_id
            return iter(())

    import deerflow.client

    monkeypatch.setattr(deerflow.client, "DeerFlowClient", ReturningClient)

    def finalize_sessions(
        thread_id: str,
        *,
        interrupted_status: str | None,
        error: str | None,
    ) -> bool:
        del thread_id
        assert interrupted_status is None
        assert error is None
        call_order.append("finalize")
        return next(finalization_results)

    def reconcile(_attempt_id: str) -> dict[str, object]:
        call_order.append("reconcile")
        return {
            "scan_succeeded": True,
            "orphan_count": 1,
            "removed_count": 1,
            "cleanup_succeeded": True,
        }

    monkeypatch.setattr(
        forge_benchmark_runner,
        "_finalize_attempt_sessions",
        finalize_sessions,
    )
    monkeypatch.setattr(forge_benchmark_runner, "reconcile_orphans", reconcile)

    result = forge_benchmark_runner.run_attempt(manifest, ledger.path)

    assert call_order == ["finalize", "reconcile", "finalize"]
    assert result["session_finalization_succeeded"] is True
    completed = ledger.read()[-1]
    assert completed["event"] == "experiment.completed"
    assert completed["payload"]["session_finalization_succeeded"] is True


def test_gate_recomputation_detects_tampering_and_oracle_is_independent() -> None:
    manifest = load_manifest()
    case = next(case for case in manifest["cases"] if case["id"] == "fmt")
    expected_artifact = case["oracle"]["required_artifacts"][0]
    events = [
        {"event": "experiment.started", "payload": {"policy": {"case_id": "fmt"}}},
        {
            "event": "command.completed",
            "payload": {
                "command_id": "command-1",
                "role": "build",
                "exit_code": 0,
                "timed_out": False,
            },
        },
        {
            "event": "replay.completed",
            "payload": {
                "replay_attempt_id": "replay-1",
                "status": "passed",
                "cleanup_succeeded": True,
                "primary_failure_classification": None,
            },
        },
        {
            "event": "submit.completed",
            "payload": {
                "submit_attempt_id": "submit-1",
                "supporting_command_id": "command-1",
                "candidate_status": "passed",
                "artifacts": [
                    {
                        "path": expected_artifact["relative_path"],
                        "artifact_type": expected_artifact["artifact_type"],
                    }
                ],
                "checks": [{"passed": True}],
                "recipe_sha256": "2" * 64,
                "replay": {
                    "replay_attempt_id": "replay-1",
                    "status": "passed",
                    "primary_failure_classification": None,
                },
                "gates": {
                    "exit_code": True,
                    "candidate_only": True,
                    "replay_ready": True,
                    "clean_replay": False,
                    "delivered": None,
                },
            },
        },
        {
            "event": "delivery.completed",
            "payload": {"submit_attempt_id": "submit-1", "delivered": True},
        },
    ]

    gates = forge_benchmark_runner.recompute_gates(events)
    oracle = forge_benchmark_runner.run_oracle(manifest, events)

    assert gates["valid"] is False
    assert gates["mismatches"] == [
        {
            "submit_attempt_id": "submit-1",
            "gate": "clean_replay",
            "recorded": False,
            "recomputed": True,
        }
    ]
    assert oracle["passed"] is True
