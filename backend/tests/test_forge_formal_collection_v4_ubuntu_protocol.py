from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "scripts" / "forge_formal_collection_v4_ubuntu_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts" / "forge_formal_collection_v4_ubuntu_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-v4-ubuntu-candidate.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-collection-v4-ubuntu-candidate.schema.json"
PARENT_MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-v4-runtime-candidate.json"
PARENT_FILE_SHA256 = {
    "scripts/forge_formal_collection_v4_runtime_protocol.py": ("e0b14b5e2f224846f1c5c0c213f66e0667a5d008d4e246d37b1b805c4ccf595e"),
    "scripts/forge_formal_collection_v4_runtime_runner.py": ("9b4ba4f4eabb5888fd663b241d69a00dfc5e369474755dd64338b02fc146e42f"),
    "benchmarks/manifests/cpp-formal-v4-runtime-candidate.json": ("88f2fa42b891816fdab7956dc223f8195f49f46479b55700c5030f0568d52144"),
    "benchmarks/schemas/forge-cpp-formal-collection-v4-runtime-candidate.schema.json": ("69bba99ca4fba5afd10e170976f509c90e089a5769d3939cea416411276dda60"),
    "benchmarks/preregistrations/cpp-formal-v4-runtime-amendment.md": ("2fbdbbb2c419e2dcea24be1c6bd5650febdbd64509068e6ecd78fe64a5f9f04a"),
}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


protocol = _load_module(
    "forge_formal_collection_v4_ubuntu_protocol_test",
    PROTOCOL_PATH,
)
runner = _load_module(
    "forge_formal_collection_v4_ubuntu_runner_test",
    RUNNER_PATH,
)


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_ubuntu_candidate_is_deterministic_schema_valid_and_unapproved() -> None:
    manifest = load_manifest()

    assert protocol.validate_manifest(manifest) == manifest
    assert protocol.generate_manifest() == manifest
    assert manifest["schema_version"] == "formal-collection-4.2.0-ubuntu-candidate"
    assert manifest["scope"]["collection_authorized"] is False
    assert manifest["scope"]["formal_comparison_enabled"] is False
    assert manifest["forge"]["commit_sha"] == ("65c2a739ba054375158cbddb27a885e8206a48aa")
    assert manifest["runtime"]["docker_daemon_provider"] == "ubuntu-native"
    assert manifest["runtime"]["docker_socket_path"] == "/var/run/docker.sock"
    assert manifest["authorization"]["issue_url"].endswith("/issues/109")

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(manifest, schema)


def test_initial_batch_is_one_complete_result_independent_project_block() -> None:
    manifest = load_manifest()
    decision = manifest["initial_batch_decision"]
    selected = [slot for slot in manifest["collection_plan"] if slot["order"] in decision["selected_schedule_orders"]]

    assert decision["selection_rule"] == "first_project_in_frozen_schedule"
    assert decision["project_ids"] == ["cppitertools"]
    assert decision["selected_schedule_orders"] == [1, 2, 73, 74, 153, 154]
    assert decision["planned_attempts"] == 6
    assert decision["maximum_recorded_tokens"] == 980_000
    assert len(selected) == 6
    assert {slot["case_id"] for slot in selected} == {"cppitertools"}
    assert {(slot["condition_id"], slot["repetition"]) for slot in selected} == {(condition["id"], repetition) for condition in manifest["conditions"] for repetition in range(1, 4)}


def test_parent_runtime_candidate_files_remain_byte_identical() -> None:
    parent = json.loads(PARENT_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest = load_manifest()

    assert manifest["authorization"]["parent_manifest"]["canonical_sha256"] == ("d1c211e638ee2fd71c5c2f9e70f250306a131f9ae8759c9bd064e48a96252473")
    assert manifest["collection_plan"] == parent["collection_plan"]
    assert manifest["conditions"] == parent["conditions"]
    assert manifest["attempt_budget"] == parent["attempt_budget"]
    for relative_path, expected in PARENT_FILE_SHA256.items():
        assert hashlib.sha256((REPO_ROOT / relative_path).read_bytes()).hexdigest() == (expected)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["scope"].update(collection_authorized=True),
        lambda value: value["runtime"].update(docker_daemon_provider="docker-desktop-wsl2"),
        lambda value: value["resource_preflight"].update(docker_socket_path="//./pipe/dockerDesktopLinuxEngine"),
        lambda value: value["initial_batch_decision"].update(selected_schedule_orders=[1, 2]),
        lambda value: value["initial_batch_decision"].update(maximum_recorded_tokens=980_001),
        lambda value: value["authorization"]["collection_constraints"].update(model_execution_forbidden=False),
    ],
)
def test_ubuntu_candidate_rejects_environment_budget_or_authorization_drift(
    mutation,
) -> None:
    manifest = copy.deepcopy(load_manifest())
    mutation(manifest)

    with pytest.raises(protocol.BenchmarkError):
        protocol.validate_manifest(manifest)


def test_runtime_preflight_accepts_only_ubuntu_native_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
            [
                {
                    "Type": "bind",
                    "Source": "/var/run/docker.sock",
                    "Destination": "/var/run/docker.sock",
                    "RW": True,
                }
            ],
        ),
    )
    monkeypatch.setattr(
        runner,
        "_docker_daemon_provider_probe",
        lambda timeout: {
            "provider": "ubuntu-native",
            "responded": True,
            "latency_seconds": 0.1,
        },
    )

    result = runner.collect_runtime_launch_preflight(tmp_path)

    assert result["ready"] is True
    assert result["checks"]["docker_daemon_provider_matches"] is True
    assert result["checks"]["docker_socket_source_matches_native_path"] is True
    assert result["observations"]["docker_daemon_provider"] == "ubuntu-native"
    assert "operating_system" not in result["observations"]


@pytest.mark.parametrize(
    ("provider", "source", "failed_check"),
    [
        (
            "other",
            "/var/run/docker.sock",
            "docker_daemon_provider_matches",
        ),
        (
            "ubuntu-native",
            "/run/desktop/mnt/host/wsl/docker-desktop-bind-mounts/socket",
            "docker_socket_source_matches_native_path",
        ),
    ],
)
def test_runtime_preflight_rejects_desktop_or_socket_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    source: str,
    failed_check: str,
) -> None:
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
            [
                {
                    "Type": "bind",
                    "Source": source,
                    "Destination": "/var/run/docker.sock",
                    "RW": True,
                }
            ],
        ),
    )
    monkeypatch.setattr(
        runner,
        "_docker_daemon_provider_probe",
        lambda timeout: {
            "provider": provider,
            "responded": True,
            "latency_seconds": 0.1,
        },
    )

    result = runner.collect_runtime_launch_preflight(tmp_path)

    assert result["ready"] is False
    assert result["checks"][failed_check] is False


def test_unapproved_candidate_rejects_external_actions_without_evidence(
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
