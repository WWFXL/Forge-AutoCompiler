"""Issue #297 Phase 5 v2 授权校准协议与生命周期门禁测试。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
PROTOCOL_PATH = SCRIPTS / "forge_agent_workflow_stage_b_phase5_v2_authorized_protocol.py"
RUNNER_PATH = SCRIPTS / "forge_agent_workflow_stage_b_phase5_v2_authorized_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-agent-workflow-stage-b-phase5-v2-authorized.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-agent-workflow-stage-b-phase5-v2-authorized.schema.json"


def _load_module(name: str, path: Path):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_module("forge_agent_workflow_stage_b_phase5_v2_authorized_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_agent_workflow_stage_b_phase5_v2_authorized_runner_test", RUNNER_PATH)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_authorized_manifest_is_deterministic_and_only_contains_allowed_delta() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)

    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.generate_schema(manifest)
    assert protocol.validate_allowed_delta(manifest, REPO_ROOT)["status"] == "passed"
    assert protocol.candidate.canonical_sha256(manifest) == "aa1f9ec280cbbecf91b5e10a9724e9b2462aed8dccc44bfb906c5e3e1ef962ed"
    assert manifest["authorized_execution"]["parent_manifest_canonical_sha256"] == protocol.PARENT_MANIFEST_CANONICAL_SHA256

    drifted = copy.deepcopy(manifest)
    drifted["tasks"][0]["commit_sha"] = "0" * 40
    with pytest.raises(protocol.Phase5V2AuthorizedProtocolError):
        protocol.validate_allowed_delta(drifted, REPO_ROOT)


def test_authorization_freezes_release_image_budget_and_single_reachability() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    authorization = manifest["authorization"]
    execution = manifest["authorized_execution"]

    assert all(item is True for key, item in authorization.items() if key.endswith("_authorized") and key != "model_tokens_authorized")
    assert authorization["model_tokens_authorized"] == 1_805_000
    assert execution["authorization_baseline_commit"] == "03a870eeef54f3fe591b115428dba51637acbcca"
    assert manifest["environment_candidate"]["image_id"] == "sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a"
    assert execution["reachability"]["maximum_requests"] == 1
    assert manifest["schedule"]["attempts_per_task"] == 1
    assert manifest["schedule"]["replacement"] is False
    assert manifest["schedule"]["backfill"] is False


def test_preflight_failure_before_provider_does_not_create_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    monkeypatch.setattr(runner.protocol, "verify_frozen_components", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runner, "_output_dir", lambda _manifest, output_dir: output_dir)
    monkeypatch.setattr(runner, "require_release_identity", lambda *_args, **_kwargs: {"revision": "a" * 40})
    monkeypatch.setattr(runner, "require_network_medium", lambda _manifest: "ethernet")
    monkeypatch.setattr(
        runner,
        "require_docker_identity",
        lambda _manifest: manifest["environment_candidate"]["image_id"],
    )
    monkeypatch.setattr(runner, "require_zero_managed_resources", lambda: None)
    monkeypatch.setattr(
        runner,
        "_provider_config_preflight",
        lambda _manifest: (_ for _ in ()).throw(runner.Phase5V2AuthorizedRunnerError("provider credential env 未注入")),
    )

    with pytest.raises(runner.Phase5V2AuthorizedRunnerError, match="credential"):
        runner.collect_preflight(manifest, output_dir=tmp_path / "evidence", repo_root=REPO_ROOT, require_empty=True)
    assert not (tmp_path / "evidence").exists()


def test_docker_identity_requires_authorized_compose_control_plane(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    hostname = "a" * 12
    inspected = [
        {
            "Id": hostname + "b" * 52,
            "Config": {
                "Hostname": hostname,
                "Labels": {
                    "com.docker.compose.project": "deer-flow-dev",
                    "com.docker.compose.service": "langgraph",
                },
            },
            "Mounts": [{"Destination": "/var/run/docker.sock", "RW": True}],
        }
    ]
    responses = {
        ("docker", "inspect", hostname): json.dumps(inspected),
        ("docker", "version", "--format", "{{.Server.Version}}"): "29.1.3",
        (
            "docker",
            "image",
            "inspect",
            manifest["environment_candidate"]["compile_image"],
            "--format",
            "{{.Id}}",
        ): manifest["environment_candidate"]["image_id"],
    }
    monkeypatch.setenv("HOSTNAME", hostname)
    monkeypatch.setattr(runner, "_docker_socket_is_socket", lambda: True)
    monkeypatch.setattr(runner, "_run_checked", lambda command, _failure: responses[tuple(command)])

    assert runner.require_docker_identity(manifest) == manifest["environment_candidate"]["image_id"]

    inspected[0]["Config"]["Labels"]["com.docker.compose.project"] = "other"
    responses[("docker", "inspect", hostname)] = json.dumps(inspected)
    with pytest.raises(runner.Phase5V2AuthorizedRunnerError, match="control plane"):
        runner.require_docker_identity(manifest)


def test_docker_identity_rejects_read_only_socket_mount(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    hostname = "c" * 12
    inspected = [
        {
            "Id": hostname + "d" * 52,
            "Config": {
                "Hostname": hostname,
                "Labels": {
                    "com.docker.compose.project": "deer-flow-dev",
                    "com.docker.compose.service": "gateway",
                },
            },
            "Mounts": [{"Destination": "/var/run/docker.sock", "RW": False}],
        }
    ]
    monkeypatch.setenv("HOSTNAME", hostname)
    monkeypatch.setattr(runner, "_docker_socket_is_socket", lambda: True)
    monkeypatch.setattr(runner, "_run_checked", lambda *_args: json.dumps(inspected))

    with pytest.raises(runner.Phase5V2AuthorizedRunnerError, match="可写"):
        runner.require_docker_identity(manifest)


class _ReachabilityModel:
    def invoke(self, prompt: str) -> AIMessage:
        assert prompt == "Reply with exactly CANARY_OK and nothing else."
        return AIMessage(
            content="CANARY_OK",
            response_metadata={"model_name": "deepseek-flash"},
            usage_metadata={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        )


def test_reachability_writes_single_create_once_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    revision = "a" * 40
    monkeypatch.setattr(
        runner,
        "collect_preflight",
        lambda *_args, **_kwargs: {"release_revision": revision, "network_access_medium": "ethernet"},
    )

    report = runner.execute_reachability(
        manifest,
        output_dir=tmp_path,
        repo_root=REPO_ROOT,
        model_factory=lambda _manifest: _ReachabilityModel(),
    )

    assert report["passed"] is True
    assert report["request_count"] == 1
    assert report["recorded_tokens"] == 12
    assert runner.require_passed_reachability(manifest, tmp_path, revision) == report
    with pytest.raises(runner.Phase5V2AuthorizedRunnerError, match="不可覆盖"):
        runner.execute_reachability(
            manifest,
            output_dir=tmp_path,
            repo_root=REPO_ROOT,
            model_factory=lambda _manifest: _ReachabilityModel(),
        )


def test_oracle_specs_preserve_compile_and_explicit_uwebsockets_start() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    yyjson = next(task for task in manifest["tasks"] if task["task_id"] == "yyjson")
    uwebsockets = next(task for task in manifest["tasks"] if task["task_id"] == "uwebsockets")

    compile_spec = runner._oracle_spec(yyjson)
    service_spec = runner._oracle_spec(uwebsockets)

    assert compile_spec.argv[:2] == ("sh", "-c")
    assert "base64 -d" in compile_spec.argv[2]
    assert "/artifacts/libyyjson.a" in compile_spec.argv[2]
    assert service_spec.workdir == "/artifacts"
    assert service_spec.argv[:2] == ("sh", "-c")
    assert service_spec.argv[2].startswith("./HelloWorld ")
    assert "http://127.0.0.1:3000/" in service_spec.argv[2]
    assert "|| true" not in service_spec.argv[2]


def test_task_qualification_drift_stops_before_model_creation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    task = manifest["tasks"][0]
    session = SimpleNamespace(
        session_id="session-1",
        thread_id="thread-1",
        commit_sha=task["commit_sha"],
        image_id=manifest["environment_candidate"]["image_id"],
        build_system_capabilities=list(task["build_system_capabilities"]),
        selected_build_system=None,
    )
    model_created = False

    def model_factory(_manifest: dict, _thread_id: str):
        nonlocal model_created
        model_created = True
        return object()

    def clone_exact_commit(**kwargs):
        assert kwargs["commit_sha"] == task["commit_sha"]
        return SimpleNamespace(exit_code=0), "ok"

    monkeypatch.setattr(runner, "activate_experiment", lambda **_kwargs: None)
    monkeypatch.setattr(runner, "deactivate_experiment", lambda _thread_id: None)
    monkeypatch.setattr(
        runner,
        "get_compile_services",
        lambda: SimpleNamespace(manager=SimpleNamespace(save_session=lambda _session: None)),
    )
    monkeypatch.setattr(runner, "prepare_compile_session_impl", lambda **_kwargs: session)
    monkeypatch.setattr(
        runner,
        "clone_repository_impl",
        clone_exact_commit,
    )
    monkeypatch.setattr(
        runner,
        "inspect_build_system_impl",
        lambda **_kwargs: (task["selected_build_system"], [], []),
    )
    monkeypatch.setattr(
        runner.candidate_runner,
        "validate_runtime_probe",
        lambda *_args: (_ for _ in ()).throw(runner.Phase5V2AuthorizedRunnerError("qualification 发生漂移")),
    )
    monkeypatch.setattr(
        runner,
        "_safe_cleanup",
        lambda current: (current, SimpleNamespace(succeeded=True)),
    )

    with pytest.raises(runner.Phase5V2AuthorizedRunnerError, match="qualification"):
        asyncio_run(
            runner.execute_task(
                manifest,
                task,
                release_revision="a" * 40,
                output_dir=tmp_path,
                model_factory=model_factory,
            )
        )

    assert model_created is False
    assert _load(tmp_path / "tasks" / task["task_id"] / "attempt.json")["status"] == "failed"


def _closed_task(manifest: dict, revision: str, task_id: str, *, tokens: int = 10) -> dict:
    return {
        "manifest_sha256": protocol.candidate.canonical_sha256(manifest),
        "release_revision": revision,
        "task_id": task_id,
        "attempt_id": manifest["authorized_execution"]["attempt_id_template"].format(task_id=task_id),
        "candidate_generated_observed": True,
        "candidate_submitted": True,
        "s0_s5": [{"layer": layer, "status": "passed"} for layer in ("S0", "S1", "S2", "S3", "S4", "S5")],
        "strict_reproducible_build_success": True,
        "bitwise_reproducible": True,
        "recorded_tokens": tokens,
        "cleanup_succeeded": True,
        "zero_managed_resources": True,
    }


def test_batch_resumes_only_completed_contiguous_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    revision = "b" * 40
    digest = protocol.candidate.canonical_sha256(manifest)
    monkeypatch.setattr(runner, "collect_preflight", lambda *_args, **_kwargs: {"release_revision": revision})
    monkeypatch.setattr(runner, "require_passed_reachability", lambda *_args, **_kwargs: {"recorded_tokens": 12})
    monkeypatch.setattr(runner, "require_zero_managed_resources", lambda: None)

    for task_id in manifest["schedule"]["order"][:2]:
        task_dir = tmp_path / "tasks" / task_id
        runner._write_once(
            task_dir / "attempt.json",
            {
                "status": "passed",
                "manifest_sha256": digest,
                "release_revision": revision,
                "task_id": task_id,
            },
        )
        runner._write_once(task_dir / "result.json", _closed_task(manifest, revision, task_id))

    runner._claim_marker(
        tmp_path / manifest["authorized_execution"]["batch_marker"],
        document_type="forge_agent_workflow_stage_b_phase5_v2_batch_attempt",
        digest=digest,
        revision=revision,
    )

    invoked: list[str] = []

    async def fake_task(_manifest: dict, task: dict, **_kwargs) -> dict:
        invoked.append(task["task_id"])
        return _closed_task(manifest, revision, task["task_id"])

    report = asyncio_run(
        runner.run_batch_async(
            manifest,
            output_dir=tmp_path,
            repo_root=REPO_ROOT,
            task_executor=fake_task,
        )
    )

    assert invoked == manifest["schedule"]["order"][2:]
    assert report["task_count"] == 6
    assert report["candidate_submitted"] == 6
    assert report["strict_success"] == 6
    assert _load(tmp_path / manifest["authorized_execution"]["stage_c_decision_package"])["stage_c_authorized"] is False


def test_batch_rejects_existing_task_evidence_without_create_once_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    revision = "c" * 40
    digest = protocol.candidate.canonical_sha256(manifest)
    task_id = manifest["schedule"]["order"][0]
    task_dir = tmp_path / "tasks" / task_id
    runner._write_once(
        task_dir / "attempt.json",
        {
            "status": "passed",
            "manifest_sha256": digest,
            "release_revision": revision,
            "task_id": task_id,
        },
    )
    runner._write_once(task_dir / "result.json", _closed_task(manifest, revision, task_id))
    monkeypatch.setattr(
        runner,
        "collect_preflight",
        lambda *_args, **_kwargs: {"release_revision": revision},
    )
    monkeypatch.setattr(
        runner,
        "require_passed_reachability",
        lambda *_args, **_kwargs: {"recorded_tokens": 12},
    )

    with pytest.raises(runner.Phase5V2AuthorizedRunnerError, match="batch marker"):
        asyncio_run(
            runner.run_batch_async(
                manifest,
                output_dir=tmp_path,
                repo_root=REPO_ROOT,
            )
        )


def asyncio_run(coroutine):
    import asyncio

    return asyncio.run(coroutine)


def test_node_input_exposes_frozen_task_specific_observation() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    task = manifest["tasks"][0]
    session = SimpleNamespace(session_id="session-1")

    node_input = runner._node_input(manifest, task, session, "phase5-v2-yyjson-attempt-1")

    assert node_input.environment.image_id == manifest["environment_candidate"]["image_id"]
    assert node_input.build_system_candidates == tuple(task["build_system_capabilities"])
    assert node_input.target_contract.target_id == "yyjson-static-library"
    assert node_input.initial_observation["required_candidate_artifacts"] == ("libyyjson.a", "include/yyjson.h")
    assert node_input.initial_observation["functional_oracle"]["kind"] == "compile_and_run"
    assert node_input.initial_observation["selected_build_system"] == task["selected_build_system"]
    assert node_input.initial_observation["qualification_result_sha256"] == protocol.candidate.QUALIFICATION_RESULT_SHA256
