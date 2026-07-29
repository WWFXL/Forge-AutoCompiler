from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow.compile import operations
from deerflow.compile.docker_runtime import ContainerCleanupResult
from deerflow.compile.evidence import ExperimentLedger, new_evidence_id, record_experiment_event
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


def load_v4_manifest() -> dict:
    path = REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v4.json"
    return forge_benchmark_runner._load_manifest(path)


def load_v5_manifest() -> dict:
    path = REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v5.json"
    return forge_benchmark_runner._load_manifest(path)


def load_v6_manifest() -> dict:
    path = REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v6.json"
    return forge_benchmark_runner._load_manifest(path)


def load_v7_manifest() -> dict:
    path = REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v7.json"
    return forge_benchmark_runner._load_manifest(path)


def load_v8_manifest() -> dict:
    path = REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v8.json"
    return forge_benchmark_runner._load_manifest(path)


def ready_preflight(manifest: dict, *, ready: bool = True) -> dict:
    return {
        "ready": ready,
        "launch_ready": True,
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


def ready_runtime_launch() -> dict:
    checks = {
        "runtime_process_is_langgraph_compose": True,
        "docker_socket_is_bind_rw": True,
        "runner_interpreter_matches": True,
        "runtime_imports_available": True,
        "evidence_mount_is_bind_rw": True,
        "evidence_output_within_mount": True,
        "evidence_output_writable": True,
    }
    return {"ready": True, "checks": checks}


@pytest.fixture(autouse=True)
def _runtime_launch_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        forge_benchmark_runner,
        "collect_runtime_launch_preflight",
        lambda *_args, **_kwargs: ready_runtime_launch(),
    )


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
    assert policy.expected_build_system == manifest["cases"][0]["build_system"]
    assert policy.process_environment == manifest["cases"][0]["constraints"]["environment"]


@pytest.mark.parametrize("case_id", ["fmt", "hiredis", "libcheck"])
def test_build_policy_freezes_each_supported_build_system(case_id: str) -> None:
    manifest = load_v3_manifest()
    case = next(case for case in manifest["cases"] if case["id"] == case_id)

    policy = forge_benchmark_runner.build_policy(
        manifest,
        case_id=case_id,
        condition_id="baseline",
        repetition=1,
    )

    assert policy.expected_build_system == case["build_system"]
    assert policy.to_payload()["expected_build_system"] == case["build_system"]


def test_v7_build_policy_records_separate_compiler_budgets() -> None:
    manifest = load_v7_manifest()

    policy = forge_benchmark_runner.build_policy(
        manifest,
        case_id="fmt",
        condition_id="baseline",
        repetition=1,
    )

    assert policy.compiler_max_turns == 36
    assert policy.subagent_timeout_seconds == 900
    assert policy.compiler_model_turn_limit == 36
    assert policy.compiler_graph_recursion_limit == 96
    assert policy.compiler_wall_clock_seconds == 900
    assert policy.compiler_post_build_reserve_seconds == 120
    assert policy.to_payload()["compiler_model_turn_limit"] == 36
    assert policy.to_payload()["compiler_graph_recursion_limit"] == 96
    assert policy.to_payload()["compiler_wall_clock_seconds"] == 900
    assert policy.to_payload()["compiler_post_build_reserve_seconds"] == 120


@pytest.mark.parametrize(
    ("condition_id", "model_name", "endpoint", "credential_env"),
    [
        (
            "richlab-gpt-5.5",
            "gpt-5.5",
            "https://richlab-api-x.choosefire.com/v1",
            "OpenAI_AK",
        ),
        (
            "deepseek-v4-flash",
            "deepseek-v4-flash",
            "https://api.deepseek.com",
            "DEEPSEEK_API_KEY",
        ),
    ],
)
def test_v8_build_policy_routes_each_condition_to_one_provider(
    condition_id: str,
    model_name: str,
    endpoint: str,
    credential_env: str,
) -> None:
    manifest = load_v8_manifest()

    policy = forge_benchmark_runner.build_policy(
        manifest,
        case_id="fmt",
        condition_id=condition_id,
        repetition=1,
    )

    assert policy.model_name == model_name
    assert policy.endpoint == endpoint
    assert policy.credential_env == credential_env
    assert policy.model_max_retries == 0
    assert policy.memory_enabled is False
    assert policy.skills_enabled is False


def test_v6_build_policy_payload_keeps_legacy_budget_shape() -> None:
    manifest = load_v6_manifest()

    payload = forge_benchmark_runner.build_policy(
        manifest,
        case_id="fmt",
        condition_id="baseline",
        repetition=1,
    ).to_payload()

    assert payload["compiler_max_turns"] == 36
    assert payload["subagent_timeout_seconds"] == 300
    assert "compiler_model_turn_limit" not in payload
    assert "compiler_graph_recursion_limit" not in payload
    assert "compiler_wall_clock_seconds" not in payload
    assert "compiler_post_build_reserve_seconds" not in payload


@pytest.mark.parametrize(
    ("manifest_loader", "manifest_name"),
    [
        (load_v2_manifest, "cpp-pilot-v2.json"),
        (load_v3_manifest, "cpp-pilot-v3.json"),
        (load_v4_manifest, "cpp-pilot-v4.json"),
        (load_v5_manifest, "cpp-pilot-v5.json"),
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
    monkeypatch.setattr(
        forge_benchmark_runner,
        "collect_runtime_launch_preflight",
        lambda *_args, **_kwargs: ready_runtime_launch(),
    )

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


@pytest.mark.parametrize("manifest_loader", [load_v2_manifest, load_v3_manifest, load_v4_manifest, load_v5_manifest])
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
    monkeypatch.setattr(
        forge_benchmark_runner,
        "collect_runtime_launch_preflight",
        lambda *_args, **_kwargs: {
            "ready": False,
            "checks": {key: False for key in ready_runtime_launch()["checks"]},
        },
    )
    monkeypatch.setattr(forge_benchmark_runner, "_sha256_file", lambda _path: None)
    monkeypatch.setattr(forge_benchmark_runner, "_credential_present", lambda _name: True)
    monkeypatch.setattr(forge_benchmark_runner, "_endpoint_reachable", lambda _endpoint: True)
    monkeypatch.setattr(forge_benchmark_runner, "_run_command", lambda *_args, **_kwargs: (1, ""))

    preflight = forge_benchmark_runner.collect_preflight(manifest)

    assert preflight["ready"] is False
    assert preflight["checks"]["forge_revision_matches"] is False
    assert preflight["checks"]["forge_baseline_satisfied"] is False
    assert preflight["checks"]["control_plane_topology_matches"] is False


def test_v8_preflight_checks_both_providers_without_exposing_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_v8_manifest()
    expected_hashes = {
        **manifest["forge"]["component_sha256"],
        **manifest["protocol_artifact_sha256"],
    }
    checked_endpoints: list[str] = []

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
    monkeypatch.setattr(
        forge_benchmark_runner,
        "_sha256_file",
        lambda path: next(
            (digest for relative_path, digest in expected_hashes.items() if path.as_posix().endswith(relative_path)),
            "a" * 64,
        ),
    )
    monkeypatch.setattr(
        forge_benchmark_runner,
        "_credential_present",
        lambda name: name == "OpenAI_AK",
    )
    monkeypatch.setattr(
        forge_benchmark_runner,
        "_model_config_matches",
        lambda _model: True,
    )

    def endpoint_reachable(endpoint: str) -> bool:
        checked_endpoints.append(endpoint)
        return True

    monkeypatch.setattr(
        forge_benchmark_runner,
        "_endpoint_reachable",
        endpoint_reachable,
    )
    monkeypatch.setattr(
        forge_benchmark_runner,
        "_compose_dood_present",
        lambda _repo_root: True,
    )

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
        runtime_launch=ready_runtime_launch(),
    )

    assert preflight["ready"] is False
    assert preflight["checks"]["credential_present"] is False
    assert set(checked_endpoints) == {
        "https://richlab-api-x.choosefire.com/v1",
        "https://api.deepseek.com",
    }
    assert preflight["models"] == {
        "richlab-gpt-5.5": {
            "credential_present": True,
            "endpoint_reachable": True,
            "configuration_matches": True,
        },
        "deepseek-v4-flash": {
            "credential_present": False,
            "endpoint_reachable": True,
            "configuration_matches": True,
        },
    }
    serialized = json.dumps(preflight, sort_keys=True)
    assert "OpenAI_AK" not in serialized
    assert "DEEPSEEK_API_KEY" not in serialized


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
    assert policy.expected_build_system in prompt
    assert f"selected {policy.selected_build_system}" in prompt
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
    assert original.read()[0]["payload"]["policy"]["expected_build_system"] == "cmake"
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


def test_v8_create_attempt_enforces_first_slot_seriality_and_no_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_v8_manifest()
    monkeypatch.setattr(
        forge_benchmark_runner,
        "collect_preflight",
        lambda *args, **kwargs: ready_preflight(manifest),
    )

    with pytest.raises(forge_benchmark_runner.RunnerError, match="not next"):
        forge_benchmark_runner.create_attempt(
            manifest,
            case_id="fmt",
            condition_id="deepseek-v4-flash",
            repetition=1,
            output_dir=tmp_path,
        )
    assert not list(tmp_path.rglob("*.jsonl"))

    first, _ = forge_benchmark_runner.create_attempt(
        manifest,
        case_id="fmt",
        condition_id="richlab-gpt-5.5",
        repetition=1,
        output_dir=tmp_path,
    )
    assert first.read()[0]["payload"]["policy"]["model_name"] == "gpt-5.5"

    with pytest.raises(forge_benchmark_runner.RunnerError, match="previous v8 slot"):
        forge_benchmark_runner.create_attempt(
            manifest,
            case_id="fmt",
            condition_id="deepseek-v4-flash",
            repetition=1,
            output_dir=tmp_path,
        )
    with pytest.raises(forge_benchmark_runner.RunnerError, match="forbids replacement"):
        forge_benchmark_runner.create_attempt(
            manifest,
            case_id="fmt",
            condition_id="richlab-gpt-5.5",
            repetition=1,
            output_dir=tmp_path,
            replacement_for=first.physical_attempt_id,
        )
    assert len(list(tmp_path.rglob("*.jsonl"))) == 1


def test_v8_create_attempt_blocks_on_invalid_existing_evidence(
    tmp_path: Path,
) -> None:
    manifest = load_v8_manifest()
    broken = tmp_path / "broken.jsonl"
    broken.write_text('{"not":"a valid ledger"}\n', encoding="utf-8")

    with pytest.raises(forge_benchmark_runner.RunnerError, match="invalid ledger"):
        forge_benchmark_runner.create_attempt(
            manifest,
            case_id="fmt",
            condition_id="richlab-gpt-5.5",
            repetition=1,
            output_dir=tmp_path,
        )

    assert list(tmp_path.rglob("*.jsonl")) == [broken]


def test_create_attempt_rejects_runtime_launch_failure_before_creating_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    monkeypatch.setattr(
        forge_benchmark_runner,
        "collect_runtime_launch_preflight",
        lambda *args, **kwargs: {
            "ready": False,
            "checks": {"runner_interpreter_matches": False},
        },
    )
    monkeypatch.setattr(
        forge_benchmark_runner,
        "collect_preflight",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("full preflight must not run"),
        ),
    )

    with pytest.raises(forge_benchmark_runner.RunnerError, match="before physical-attempt ledger"):
        forge_benchmark_runner.create_attempt(
            manifest,
            case_id="fmt",
            condition_id="baseline",
            repetition=1,
            output_dir=tmp_path,
        )

    assert not list(tmp_path.rglob("*.jsonl"))


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


@pytest.mark.parametrize("manifest_loader", [load_v2_manifest, load_v3_manifest, load_v4_manifest, load_v5_manifest])
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


def test_runner_defaults_to_v8_manifest() -> None:
    args = forge_benchmark_runner._build_parser().parse_args(
        [
            "preflight",
            "--output-dir",
            "/workspace/.compile-sessions/benchmark-evidence-v8",
        ]
    )

    assert args.manifest == REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v8.json"


def test_runtime_preflight_requires_explicit_output_directory() -> None:
    with pytest.raises(SystemExit):
        forge_benchmark_runner._build_parser().parse_args(["runtime-preflight"])


def test_runner_interpreter_requires_backend_virtual_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(forge_benchmark_runner.sys, "prefix", "/usr/local")
    monkeypatch.setattr(forge_benchmark_runner.sys, "base_prefix", "/usr/local")
    monkeypatch.setattr(forge_benchmark_runner.sys, "executable", "/usr/local/bin/python3")

    assert forge_benchmark_runner._runner_interpreter_matches() is False

    monkeypatch.setattr(forge_benchmark_runner.sys, "prefix", "/app/backend/.venv")
    monkeypatch.setattr(forge_benchmark_runner.sys, "base_prefix", "/usr/local")
    monkeypatch.setattr(forge_benchmark_runner.sys, "executable", "/app/backend/.venv/bin/python")

    assert forge_benchmark_runner._runner_interpreter_matches() is True


def test_runtime_import_failure_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        forge_benchmark_runner.importlib,
        "import_module",
        lambda _name: (_ for _ in ()).throw(ModuleNotFoundError("private details")),
    )

    assert forge_benchmark_runner._runtime_imports_available() is False


def test_evidence_output_checks_require_mount_containment_and_writability(
    tmp_path: Path,
) -> None:
    mount_root = tmp_path / "compile-sessions"
    mount_root.mkdir()
    output_dir = mount_root / "benchmark-evidence-v8"

    assert forge_benchmark_runner._evidence_output_checks(
        output_dir,
        mount_root=mount_root,
    ) == (True, True)
    assert not list(output_dir.glob(".forge-runtime-preflight-*"))
    assert forge_benchmark_runner._evidence_output_checks(
        tmp_path / "outside",
        mount_root=mount_root,
    ) == (False, False)
    assert forge_benchmark_runner._evidence_output_checks(
        mount_root,
        mount_root=mount_root,
    ) == (False, False)


def test_evidence_output_checks_report_unwritable_without_error_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mount_root = tmp_path / "compile-sessions"
    mount_root.mkdir()
    output_dir = mount_root / "benchmark-evidence-v8"
    monkeypatch.setattr(
        forge_benchmark_runner.tempfile,
        "mkstemp",
        lambda **_kwargs: (_ for _ in ()).throw(PermissionError("private path details")),
    )

    assert forge_benchmark_runner._evidence_output_checks(
        output_dir,
        mount_root=mount_root,
    ) == (True, False)


@pytest.mark.parametrize(
    "mount",
    [
        {
            "Type": "volume",
            "Destination": "/workspace/.compile-sessions",
            "RW": True,
        },
        {
            "Type": "bind",
            "Destination": "/workspace/.compile-sessions",
            "RW": False,
        },
        {
            "Type": "bind",
            "Destination": "/workspace/other",
            "RW": True,
        },
    ],
)
def test_evidence_mount_requires_exact_writable_bind(mount: dict) -> None:
    assert forge_benchmark_runner._evidence_mount_is_bind_rw([mount]) is False


def test_evidence_output_checks_reject_symlink_escape(
    tmp_path: Path,
) -> None:
    mount_root = tmp_path / "compile-sessions"
    outside = tmp_path / "outside"
    mount_root.mkdir()
    outside.mkdir()
    link = mount_root / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")

    assert forge_benchmark_runner._evidence_output_checks(
        link / "evidence",
        mount_root=mount_root,
    ) == (False, False)


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

        async def astream(self, message: str, *, thread_id: str):
            del message, thread_id
            raise KeyboardInterrupt
            yield  # pragma: no cover

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

        async def astream(self, message: str, *, thread_id: str):
            del message
            session = manager.create_session(thread_id=thread_id, repo_url="https://example.com/repo.git")
            session.container_id = "container-123"
            manager.save_session(session)
            manager.mark_session_status(session, "ready")
            if raise_error:
                raise TimeoutError
            return
            yield  # pragma: no cover

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

        async def astream(self, message: str, *, thread_id: str):
            del message, thread_id
            return
            yield  # pragma: no cover

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


def test_run_records_no_compile_progress_without_raw_stream_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    monkeypatch.setattr(
        forge_benchmark_runner,
        "collect_preflight",
        lambda *args, **kwargs: ready_preflight(manifest),
    )
    ledger, _ = forge_benchmark_runner.create_attempt(
        manifest,
        case_id="fmt",
        condition_id="baseline",
        repetition=1,
        output_dir=tmp_path,
    )
    raw_content = "sk-stream-content-must-not-enter-ledger C:\\Users\\private"

    class NoActionClient:
        def __init__(self, **kwargs) -> None:
            del kwargs

        async def astream(self, message: str, *, thread_id: str):
            del message
            record_experiment_event(
                thread_id,
                "model.request_completed",
                model_request_id=new_evidence_id("model_request"),
                actual_model="provider-confirmed-model",
            )
            yield SimpleNamespace(
                type="messages-tuple",
                data={"type": "ai", "content": raw_content},
            )
            yield SimpleNamespace(type="end", data={"usage": {}})

    import deerflow.client

    monkeypatch.setattr(deerflow.client, "DeerFlowClient", NoActionClient)
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

    assert result["status"] == "failed"
    events = ledger.read()
    no_progress = next(event for event in events if event["event"] == "agent.no_compile_progress")
    assert no_progress["payload"]["completed_model_request_count"] == 1
    assert no_progress["payload"]["tool_call_count"] == 0
    assert no_progress["payload"]["compile_tool_call_count"] == 0
    assert no_progress["payload"]["stream_completed"] is True
    assert no_progress["payload"]["terminal"] is True
    assert raw_content not in ledger.path.read_text(encoding="utf-8")


def test_run_does_not_mark_progress_missing_after_compile_tool_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    monkeypatch.setattr(
        forge_benchmark_runner,
        "collect_preflight",
        lambda *args, **kwargs: ready_preflight(manifest),
    )
    ledger, _ = forge_benchmark_runner.create_attempt(
        manifest,
        case_id="fmt",
        condition_id="baseline",
        repetition=1,
        output_dir=tmp_path,
    )
    raw_arguments = {"prompt": "must not enter evidence"}

    class CompileActionClient:
        def __init__(self, **kwargs) -> None:
            del kwargs

        async def astream(self, message: str, *, thread_id: str):
            del message
            record_experiment_event(
                thread_id,
                "model.request_completed",
                model_request_id=new_evidence_id("model_request"),
                actual_model="provider-confirmed-model",
            )
            yield SimpleNamespace(
                type="messages-tuple",
                data={
                    "type": "ai",
                    "content": "",
                    "tool_calls": [
                        {
                            "name": "task",
                            "id": "call-compile",
                            "args": raw_arguments,
                        }
                    ],
                },
            )
            yield SimpleNamespace(type="end", data={"usage": {}})

    import deerflow.client

    monkeypatch.setattr(deerflow.client, "DeerFlowClient", CompileActionClient)
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

    forge_benchmark_runner.run_attempt(manifest, ledger.path)

    events = ledger.read()
    assert not any(event["event"] == "agent.no_compile_progress" for event in events)
    assert "must not enter evidence" not in ledger.path.read_text(encoding="utf-8")


def test_run_does_not_mark_progress_missing_when_stream_does_not_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    monkeypatch.setattr(
        forge_benchmark_runner,
        "collect_preflight",
        lambda *args, **kwargs: ready_preflight(manifest),
    )
    ledger, _ = forge_benchmark_runner.create_attempt(
        manifest,
        case_id="fmt",
        condition_id="baseline",
        repetition=1,
        output_dir=tmp_path,
    )

    class IncompleteStreamClient:
        def __init__(self, **kwargs) -> None:
            del kwargs

        async def astream(self, message: str, *, thread_id: str):
            del message
            record_experiment_event(
                thread_id,
                "model.request_completed",
                model_request_id=new_evidence_id("model_request"),
                actual_model="provider-confirmed-model",
            )
            yield SimpleNamespace(type="messages-tuple", data={"type": "ai"})

    import deerflow.client

    monkeypatch.setattr(deerflow.client, "DeerFlowClient", IncompleteStreamClient)
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

    forge_benchmark_runner.run_attempt(manifest, ledger.path)

    assert not any(event["event"] == "agent.no_compile_progress" for event in ledger.read())


def test_offline_failure_domains_keep_missing_evidence_null() -> None:
    assert forge_benchmark_runner.recompute_failure_domains([]) == {
        "model_endpoint": None,
        "agent_tool": None,
        "build": None,
        "submit_replay": None,
        "completion": None,
    }


def test_v5_records_final_build_identity_from_authoritative_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = CompileSessionManager(
        paths=Paths(
            base_dir=tmp_path / "state",
            workspace_root=tmp_path / "workspace",
            host_workspace_root=str(tmp_path / "workspace"),
        )
    )
    session = manager.create_session(
        thread_id="thread-v5-identity",
        repo_url="https://github.com/redis/hiredis",
    )
    session.build_system_capabilities = ["cmake", "make"]
    session.selected_build_system = "make"
    session.executed_build_system = "make"
    manager.save_session(session)
    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=SimpleNamespace()),
    )
    ledger = ExperimentLedger.create(
        tmp_path / "identity.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"thread_id": "thread-v5-identity"},
    )

    assert forge_benchmark_runner._record_attempt_build_identity("thread-v5-identity", ledger) is True
    snapshot = ledger.read()[-1]
    assert snapshot["event"] == "build.identity_snapshot"
    assert snapshot["payload"] == {
        "session_id": session.session_id,
        "build_system_capabilities": ["cmake", "make"],
        "selected_build_system": "make",
        "executed_build_system": "make",
    }


def test_v5_offline_identity_gate_requires_snapshot_and_proven_submit_path() -> None:
    started = {
        "event": "experiment.started",
        "payload": {
            "policy": {
                "benchmark_id": "forge-cpp-clean-replay-pilot-v5",
                "expected_build_system": "make",
            }
        },
    }
    executed_without_snapshot = [started, {"event": "runtime.topology_verified", "payload": {}}]

    assert forge_benchmark_runner.recompute_build_identity(executed_without_snapshot)["valid"] is False

    with_snapshot = [
        *executed_without_snapshot,
        {
            "event": "build.identity_snapshot",
            "payload": {
                "session_id": "abcdef123456",
                "build_system_capabilities": ["cmake", "make"],
                "selected_build_system": "make",
                "executed_build_system": "make",
            },
        },
        {"event": "submit.completed", "payload": {"session_id": "abcdef123456"}},
    ]
    identity = forge_benchmark_runner.recompute_build_identity(with_snapshot)

    assert identity["valid"] is True
    assert identity["submit_identity_proven"] is True


def test_offline_failure_domains_separate_agent_and_runtime_failures() -> None:
    events = [
        {
            "event": "failure.recorded",
            "payload": {
                "domain": "model_endpoint",
                "classification": "timeout",
            },
        },
        {
            "event": "agent.tool_failed",
            "payload": {
                "exception_class": "RuntimeError",
                "tool_name": "task",
                "terminal": False,
            },
        },
        {
            "event": "agent.no_compile_progress",
            "payload": {
                "classification": "no_compile_tool_call",
                "terminal": True,
            },
        },
        {
            "event": "failure.recorded",
            "payload": {
                "domain": "agent_tool",
                "classification": "subagent_timeout",
            },
        },
        {
            "event": "failure.recorded",
            "payload": {
                "domain": "build",
                "classification": "dependency_setup_failed",
            },
        },
        {
            "event": "failure.recorded",
            "payload": {
                "domain": "verification",
                "classification": "artifact_hash_mismatch",
            },
        },
        {
            "event": "run.failed",
            "payload": {"classification": "KeyboardInterrupt"},
        },
    ]

    domains = forge_benchmark_runner.recompute_failure_domains(events)

    assert domains["model_endpoint"] == [{"event": "failure.recorded", "classification": "timeout"}]
    assert domains["agent_tool"] == [
        {
            "event": "agent.tool_failed",
            "classification": "RuntimeError",
            "tool_name": "task",
            "terminal": False,
        },
        {
            "event": "agent.no_compile_progress",
            "classification": "no_compile_tool_call",
            "terminal": True,
        },
        {
            "event": "failure.recorded",
            "classification": "subagent_timeout",
        },
    ]
    assert domains["build"] == [
        {
            "event": "failure.recorded",
            "classification": "dependency_setup_failed",
        }
    ]
    assert domains["submit_replay"] == [
        {
            "event": "failure.recorded",
            "classification": "artifact_hash_mismatch",
        }
    ]
    assert domains["completion"] == [{"event": "run.failed", "classification": "KeyboardInterrupt"}]


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
    assert oracle["replay_artifact_diff"]["available"] is False


def test_gate_recomputation_keeps_candidate_independent_from_failed_clean_replay() -> None:
    events = [
        {"event": "experiment.started", "payload": {"policy": {"case_id": "sysstat-nondeterministic"}}},
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
                "status": "failed",
                "cleanup_succeeded": True,
                "primary_failure_classification": "sha256_mismatch",
            },
        },
        {
            "event": "submit.completed",
            "payload": {
                "submit_attempt_id": "submit-1",
                "supporting_command_id": "command-1",
                "candidate_status": "passed",
                "artifacts": [{"path": "sar", "artifact_type": "executable"}],
                "checks": [
                    {"name": "sar_exists", "passed": True},
                    {"name": "repro_bundle", "passed": True},
                    {"name": "clean_replay", "passed": False},
                ],
                "recipe_sha256": "2" * 64,
                "replay": {
                    "replay_attempt_id": "replay-1",
                    "status": "failed",
                    "primary_failure_classification": "sha256_mismatch",
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
    ]

    gates = forge_benchmark_runner.recompute_gates(events)

    assert gates["valid"] is True
    assert gates["mismatches"] == []
    assert gates["submits"][0]["gates"]["candidate_only"] is True
    assert gates["submits"][0]["gates"]["clean_replay"] is False


def test_gate_recomputation_rejects_failed_candidate_check() -> None:
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
            "event": "submit.completed",
            "payload": {
                "submit_attempt_id": "submit-1",
                "supporting_command_id": "command-1",
                "candidate_status": "passed",
                "artifacts": [{"path": "libfmt.a", "artifact_type": "static_library"}],
                "checks": [
                    {"name": "libfmt.a_exists", "passed": False},
                    {"name": "repro_bundle", "passed": True},
                ],
                "recipe_sha256": None,
                "replay": None,
                "gates": {
                    "exit_code": True,
                    "candidate_only": False,
                    "replay_ready": False,
                    "clean_replay": False,
                    "delivered": None,
                },
            },
        },
    ]

    gates = forge_benchmark_runner.recompute_gates(events)

    assert gates["valid"] is True
    assert gates["mismatches"] == []
    assert gates["submits"][0]["gates"]["candidate_only"] is False


def _oracle_events(
    *,
    artifacts: list[dict],
    replay_artifacts: list[dict] | None = None,
    replay_status: str = "passed",
) -> list[dict]:
    return [
        {"event": "experiment.started", "payload": {"policy": {"case_id": "fmt"}}},
        {
            "event": "replay.completed",
            "payload": {
                "replay_attempt_id": "replay-1",
                "status": replay_status,
                "cleanup_succeeded": True,
                "primary_failure_classification": (None if replay_status == "passed" else "artifact_mismatch"),
                "artifacts": replay_artifacts or [],
            },
        },
        {
            "event": "submit.completed",
            "payload": {
                "submit_attempt_id": "submit-1",
                "candidate_status": "passed",
                "artifacts": artifacts,
                "replay": {
                    "replay_attempt_id": "replay-1",
                    "status": replay_status,
                    "primary_failure_classification": (None if replay_status == "passed" else "artifact_mismatch"),
                },
            },
        },
    ]


@pytest.mark.parametrize(
    ("artifact_type", "path"),
    [
        ("static_library", "libsample.a"),
        ("shared_library", "libsample.so"),
        ("executable", "sample"),
    ],
)
def test_oracle_records_empty_identity_diff_for_matching_artifact_types(
    artifact_type: str,
    path: str,
) -> None:
    manifest = load_manifest()
    case = next(case for case in manifest["cases"] if case["id"] == "fmt")
    case["oracle"]["required_artifacts"] = [{"relative_path": path, "artifact_type": artifact_type}]
    events = _oracle_events(
        artifacts=[
            {
                "path": path,
                "artifact_type": artifact_type,
                "size_bytes": 123,
                "sha256": "1" * 64,
                "smoke_exit_code": 0 if artifact_type == "executable" else None,
                "smoke_output_sha256": ("2" * 64 if artifact_type == "executable" else None),
            }
        ],
    )

    oracle = forge_benchmark_runner.run_oracle(manifest, events)

    assert oracle["passed"] is True
    assert oracle["artifact_oracle_passed"] is True
    assert oracle["artifact_identity_diff"] == {
        "expected_count": 1,
        "observed_count": 1,
        "matched_count": 1,
        "expected_only_count": 0,
        "observed_only_count": 0,
        "type_mismatch_count": 0,
        "expected_only": [],
        "observed_only": [],
        "type_mismatches": [],
        "truncated": False,
    }
    assert oracle["replay_artifact_diff"] == {
        "available": True,
        "mismatch_count": 0,
        "mismatches": [],
        "truncated": False,
    }


def test_oracle_records_expected_observed_type_diff_with_bounded_identity(
    tmp_path: Path,
) -> None:
    manifest = load_manifest()
    case = next(case for case in manifest["cases"] if case["id"] == "fmt")
    case["oracle"]["required_artifacts"] = [{"relative_path": "libsample.a", "artifact_type": "static_library"}]
    events = _oracle_events(
        artifacts=[
            {
                "path": "libsample.a",
                "artifact_type": "shared_library",
                "size_bytes": 456,
                "sha256": "3" * 64,
                "smoke_exit_code": None,
                "smoke_output_sha256": None,
            }
        ],
        replay_artifacts=[
            {
                "path": "libsample.a",
                "expected_type": "static_library",
                "actual_type": "shared_library",
                "expected_size_bytes": 123,
                "actual_size_bytes": 456,
                "expected_sha256": "1" * 64,
                "actual_sha256": "3" * 64,
                "expected_smoke_exit_code": None,
                "actual_smoke_exit_code": None,
                "expected_smoke_output_sha256": None,
                "actual_smoke_output_sha256": None,
                "actual_smoke_command": "C:\\Users\\person\\secret.exe --help",
                "actual_smoke_output": "sensitive model output",
                "passed": False,
                "mismatches": ["sha256", "size", "type"],
            }
        ],
    )

    oracle = forge_benchmark_runner.run_oracle(manifest, events)

    assert oracle["passed"] is False
    assert oracle["artifact_oracle_passed"] is False
    identity_diff = oracle["artifact_identity_diff"]
    assert identity_diff["expected_only"] == [{"path": "libsample.a", "artifact_type": "static_library"}]
    assert identity_diff["observed_only"] == [
        {
            "path": "libsample.a",
            "artifact_type": "shared_library",
            "size_bytes": 456,
            "sha256": "3" * 64,
            "smoke_exit_code": None,
            "smoke_output_sha256": None,
        }
    ]
    assert identity_diff["type_mismatches"] == [
        {
            "path": "libsample.a",
            "expected_artifact_types": ["static_library"],
            "observed_artifact_types": ["shared_library"],
        }
    ]
    replay_diff = oracle["replay_artifact_diff"]
    assert replay_diff["mismatch_count"] == 1
    assert replay_diff["mismatches"][0]["mismatches"] == ["type", "size", "sha256"]
    serialized = json.dumps(oracle)
    assert "C:\\\\Users" not in serialized
    assert "actual_smoke_command" not in serialized
    assert "actual_smoke_output" not in serialized
    assert "sensitive model output" not in serialized
    ledger = ExperimentLedger.create(
        tmp_path / "artifact-diff.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"case_id": "fmt"},
    )
    ledger.append("oracle.completed", oracle)
    assert ExperimentLedger.verify_path(ledger.path)[-1]["payload"] == oracle


def test_oracle_records_executable_smoke_hash_diff_without_output() -> None:
    manifest = load_manifest()
    case = next(case for case in manifest["cases"] if case["id"] == "fmt")
    case["oracle"]["required_artifacts"] = [{"relative_path": "sample", "artifact_type": "executable"}]
    events = _oracle_events(
        artifacts=[
            {
                "path": "sample",
                "artifact_type": "executable",
                "size_bytes": 10,
                "sha256": "4" * 64,
                "smoke_exit_code": 0,
                "smoke_output_sha256": "5" * 64,
            }
        ],
        replay_status="failed",
        replay_artifacts=[
            {
                "path": "sample",
                "expected_type": "executable",
                "actual_type": "executable",
                "expected_size_bytes": 10,
                "actual_size_bytes": 10,
                "expected_sha256": "4" * 64,
                "actual_sha256": "4" * 64,
                "expected_smoke_exit_code": 0,
                "actual_smoke_exit_code": 1,
                "expected_smoke_output_sha256": "5" * 64,
                "actual_smoke_output_sha256": "6" * 64,
                "actual_smoke_output": "private output",
                "passed": False,
                "mismatches": ["smoke"],
            }
        ],
    )

    oracle = forge_benchmark_runner.run_oracle(manifest, events)

    assert oracle["artifact_oracle_passed"] is True
    assert oracle["passed"] is False
    mismatch = oracle["replay_artifact_diff"]["mismatches"][0]
    assert mismatch["mismatches"] == ["smoke"]
    assert mismatch["expected_smoke_exit_code"] == 0
    assert mismatch["observed_smoke_exit_code"] == 1
    assert mismatch["expected_smoke_output_sha256"] == "5" * 64
    assert mismatch["observed_smoke_output_sha256"] == "6" * 64
    assert "private output" not in json.dumps(oracle)


def test_oracle_artifact_diff_is_sorted_and_bounded() -> None:
    manifest = load_manifest()
    case = next(case for case in manifest["cases"] if case["id"] == "fmt")
    case["oracle"]["required_artifacts"] = [{"relative_path": "required.a", "artifact_type": "static_library"}]
    artifacts = [
        {
            "path": "required.a",
            "artifact_type": "static_library",
        },
        *[
            {
                "path": f"extra-{index:03d}.so",
                "artifact_type": "shared_library",
                "size_bytes": index,
                "sha256": f"{index:064x}",
            }
            for index in reversed(range(65))
        ],
    ]

    oracle = forge_benchmark_runner.run_oracle(
        manifest,
        _oracle_events(artifacts=artifacts),
    )

    artifact_diff = oracle["artifact_identity_diff"]
    assert oracle["passed"] is True
    assert artifact_diff["observed_only_count"] == 65
    assert len(artifact_diff["observed_only"]) == 64
    assert artifact_diff["observed_only"][0]["path"] == "extra-000.so"
    assert artifact_diff["observed_only"][-1]["path"] == "extra-063.so"
    assert artifact_diff["truncated"] is True
