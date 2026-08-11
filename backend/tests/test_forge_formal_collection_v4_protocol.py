from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "scripts" / "forge_formal_collection_v4_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts" / "forge_formal_collection_v4_runner.py"
PARENT_MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-v3-authorized-collection.json"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-v4-collection.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-collection-v4.schema.json"
PARENT_CANONICAL_SHA256 = "87968a3a1dc858c5eb2881e32711da0e2912b90a50437d9534babc37bef67cb5"
PARENT_FILE_SHA256 = {
    "benchmarks/manifests/cpp-formal-v3-authorized-collection.json": ("3c88c86fc2bba43fcbde1706e500a8cd41547d6481ae02dfa493b55c55c90045"),
    "benchmarks/schemas/forge-cpp-formal-collection-v3-authorized.schema.json": ("30e6506a25090548bc29b650c74c5b9205008aeb8222af8393a6da9549a4284d"),
    "scripts/forge_formal_collection_v3_authorized_protocol.py": ("148ee83f732973f4e3dca0c8386683a4e8135eade4eede76702896f1222b5868"),
    "scripts/forge_formal_collection_v3_authorized_runner.py": ("88a16306fcda5df0ea0128b545db80ea76c9405cb48eab57eeca6d7b2a357158"),
    "benchmarks/reports/cpp-formal-v3-initial-batch.json": ("1140637ae8ba519aedc9185099e27ddb652f2ee0a31ab2586705d505c312381f"),
    "benchmarks/reports/cpp-formal-v3-initial-batch.md": ("c7e5ff42ae26871d18032e9efa6a919b0a46d334c97a0487eb7e716e393d74c9"),
}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


formal_collection = _load_module("forge_formal_collection_v4_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_formal_collection_v4_runner_test", RUNNER_PATH)


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _evidence_mount(source: str) -> list[dict]:
    return [
        {
            "Type": "bind",
            "Source": source,
            "Destination": "/workspace/.compile-sessions",
            "RW": True,
        }
    ]


def test_v4_manifest_remains_valid_after_reviewed_runtime_successor() -> None:
    manifest = load_manifest()
    parent = json.loads(PARENT_MANIFEST_PATH.read_text(encoding="utf-8"))

    assert formal_collection.validate_manifest(manifest) == manifest
    assert formal_collection.manifest_sha256(manifest) == "bb151473b276c48b9faf287a9dcbdddd96145abf3acc605f952275cf3d3f6720"
    regenerated = formal_collection.generate_manifest()
    assert regenerated != manifest
    for field in set(manifest) - {
        "forge",
        "protocol_artifact_sha256",
        "prompt_sha256",
    }:
        assert regenerated[field] == manifest[field]
    assert regenerated["forge"]["commit_sha"] == manifest["forge"]["commit_sha"]
    assert regenerated["forge"]["component_sha256"] != manifest["forge"]["component_sha256"]
    assert manifest["collection_plan"] == parent["collection_plan"]
    assert manifest["cases"] == parent["cases"]
    assert manifest["conditions"] == parent["conditions"]
    assert manifest["scope"]["collection_authorized"] is False
    assert manifest["scope"]["formal_comparison_enabled"] is False
    assert parent["scope"]["collection_authorized"] is True

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(manifest, schema)


def test_v4_binds_attempt_resource_and_analysis_boundaries() -> None:
    manifest = load_manifest()

    assert manifest["attempt_budget"] == formal_collection.ATTEMPT_BUDGET
    assert manifest["resource_preflight"] == formal_collection.RESOURCE_PREFLIGHT
    assert manifest["analysis_plan"] == formal_collection.ANALYSIS_PLAN
    assert manifest["authorization"]["issue_url"].endswith("/issues/103")
    assert manifest["authorization"]["parent_manifest"]["canonical_sha256"] == PARENT_CANONICAL_SHA256
    assert manifest["authorization"]["v3_initial_batch"]["analyzed_slots"] == 7
    assert manifest["attempt_budget"]["total_wall_clock_seconds"] == 1800
    assert manifest["attempt_budget"]["cleanup_reserve_seconds"] == 120
    assert manifest["attempt_budget"]["max_compiler_invocations"] == 2
    assert manifest["attempt_budget"]["max_model_requests"] == 48
    assert manifest["resource_preflight"]["minimum_available_memory_bytes"] == 2 * 1024**3


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["scope"].update(collection_authorized=True),
        lambda value: value["attempt_budget"].update(total_wall_clock_seconds=1801),
        lambda value: value["attempt_budget"].update(max_compiler_invocations=3),
        lambda value: value["resource_preflight"].update(minimum_available_memory_bytes=1),
        lambda value: value["analysis_plan"].update(protocol_version_pooling="allowed"),
        lambda value: value["authorization"]["collection_constraints"].update(model_execution_forbidden=False),
        lambda value: value["collection_plan"].reverse(),
    ],
)
def test_v4_rejects_authorization_budget_resource_or_analysis_drift(mutation) -> None:
    manifest = copy.deepcopy(load_manifest())
    mutation(manifest)

    with pytest.raises(formal_collection.BenchmarkError):
        formal_collection.validate_manifest(manifest)


def test_v3_parent_and_report_files_remain_byte_identical() -> None:
    for relative_path, expected in PARENT_FILE_SHA256.items():
        assert hashlib.sha256((REPO_ROOT / relative_path).read_bytes()).hexdigest() == expected


def test_v4_runner_loads_policy_without_authorizing_collection() -> None:
    manifest = runner._load_manifest(MANIFEST_PATH)
    first_slot = manifest["collection_plan"][0]
    policy = runner.build_policy(
        manifest,
        case_id=first_slot["case_id"],
        condition_id=first_slot["condition_id"],
        repetition=first_slot["repetition"],
    )

    assert policy.benchmark_id == "forge-cpp-formal-v4-collection"
    assert policy.memory_enabled is False
    assert policy.artifact_instructions
    assert runner.protocol.SCHEMA_VERSION == formal_collection.SCHEMA_VERSION


def test_runtime_preflight_requires_memory_daemon_and_mount_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEER_FLOW_HOST_WORKSPACE_ROOT", "/mnt/c/work/Forge-AutoCompiler")
    monkeypatch.setattr(
        runner,
        "_original_collect_runtime_launch_preflight",
        lambda *args, **kwargs: {"ready": True, "checks": {"base": True}},
    )
    monkeypatch.setattr(
        runner._runner,
        "_current_container_metadata",
        lambda *args, **kwargs: (
            {},
            _evidence_mount("/mnt/c/work/Forge-AutoCompiler/.compile-sessions"),
        ),
    )
    monkeypatch.setattr(runner, "_available_memory_bytes", lambda: 3 * 1024**3)
    monkeypatch.setattr(
        runner,
        "_docker_daemon_probe",
        lambda timeout: {"responded": True, "latency_seconds": 0.25},
    )

    result = runner.collect_runtime_launch_preflight(tmp_path)

    assert result["ready"] is True
    assert all(result["checks"].values())
    assert result["observations"]["available_memory_bytes"] == 3 * 1024**3
    assert "server_version" not in result["observations"]


@pytest.mark.parametrize(
    ("memory", "daemon", "failed_check"),
    [
        (
            1024**3,
            {"responded": True, "latency_seconds": 0.25},
            "host_available_memory_at_least_minimum",
        ),
        (
            3 * 1024**3,
            {"responded": False, "latency_seconds": 10.0},
            "docker_daemon_responded",
        ),
        (
            3 * 1024**3,
            {"responded": True, "latency_seconds": 5.1},
            "docker_daemon_latency_within_limit",
        ),
    ],
)
def test_runtime_preflight_rejects_each_resource_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    memory: int,
    daemon: dict,
    failed_check: str,
) -> None:
    monkeypatch.setenv("DEER_FLOW_HOST_WORKSPACE_ROOT", "/mnt/c/work/Forge-AutoCompiler")
    monkeypatch.setattr(
        runner,
        "_original_collect_runtime_launch_preflight",
        lambda *args, **kwargs: {"ready": True, "checks": {"base": True}},
    )
    monkeypatch.setattr(
        runner._runner,
        "_current_container_metadata",
        lambda *args, **kwargs: (
            {},
            _evidence_mount("/mnt/c/work/Forge-AutoCompiler/.compile-sessions"),
        ),
    )
    monkeypatch.setattr(runner, "_available_memory_bytes", lambda: memory)
    monkeypatch.setattr(runner, "_docker_daemon_probe", lambda timeout: daemon)

    result = runner.collect_runtime_launch_preflight(tmp_path)

    assert result["ready"] is False
    assert result["checks"][failed_check] is False


def test_attempt_budget_state_blocks_new_work_at_each_boundary() -> None:
    manifest = load_manifest()
    events = [
        *[{"event": "model.request_started", "payload": {}} for _ in range(manifest["attempt_budget"]["max_model_requests"])],
        *[{"event": "agent.subagent_terminated", "payload": {"role": "compiler"}} for _ in range(manifest["attempt_budget"]["max_compiler_invocations"])],
    ]

    state = runner.attempt_budget_state(manifest, events, elapsed_seconds=100)
    assert state["allow_new_model_request"] is False
    assert state["allow_new_compiler_invocation"] is False
    assert state["cleanup_required"] is True
    assert state["within_total_wall_clock"] is True

    deadline = runner.attempt_budget_state(manifest, [], elapsed_seconds=1680)
    assert deadline["allow_new_work"] is False
    assert deadline["cleanup_required"] is True

    overrun = runner.attempt_budget_state(manifest, [], elapsed_seconds=1800.001)
    assert overrun["within_total_wall_clock"] is False


def test_attempt_budget_checkpoints_reject_new_work_but_allow_cleanup() -> None:
    manifest = load_manifest()
    events = [{"event": "model.request_started", "payload": {}} for _ in range(manifest["attempt_budget"]["max_model_requests"])]

    with pytest.raises(runner.RunnerError, match="model-request budget"):
        runner.require_attempt_budget_checkpoint(
            manifest,
            events,
            elapsed_seconds=100,
            checkpoint="before_provider_request",
        )
    with pytest.raises(runner.RunnerError, match="work deadline"):
        runner.require_attempt_budget_checkpoint(
            manifest,
            [],
            elapsed_seconds=1680,
            checkpoint="before_submit_or_replay",
        )

    finalize = runner.require_attempt_budget_checkpoint(
        manifest,
        events,
        elapsed_seconds=1801,
        checkpoint="before_finalize",
    )
    cleanup = runner.require_attempt_budget_checkpoint(
        manifest,
        events,
        elapsed_seconds=1801,
        checkpoint="before_cleanup",
    )
    assert finalize["within_total_wall_clock"] is False
    assert cleanup["cleanup_required"] is True


def test_all_unapproved_cli_actions_are_rejected_without_evidence(
    tmp_path: Path,
) -> None:
    manifest = load_manifest()
    first_slot = manifest["collection_plan"][0]
    common = ["--manifest", str(MANIFEST_PATH)]
    commands = [
        ["provider-canary", *common, "--output-dir", str(tmp_path)],
        [
            "create-attempt",
            *common,
            "--case",
            first_slot["case_id"],
            "--condition",
            first_slot["condition_id"],
            "--repetition",
            str(first_slot["repetition"]),
            "--output-dir",
            str(tmp_path),
            "--skip-endpoint-check",
        ],
        [
            "run",
            *common,
            "--ledger",
            str(tmp_path / "missing.jsonl"),
            "--skip-endpoint-check",
        ],
        [
            "run-batch",
            *common,
            "--output-dir",
            str(tmp_path),
            "--max-attempts",
            "1",
            "--skip-endpoint-check",
        ],
    ]

    for command in commands:
        assert runner.main(command) == 2

    assert list(tmp_path.rglob("*.jsonl")) == []
    assert list(tmp_path.rglob("*.json")) == []
