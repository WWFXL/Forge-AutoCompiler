from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "scripts" / "forge_formal_collection_v3_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts" / "forge_formal_collection_v3_runner.py"
PARENT_MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-v2-authorized-collection.json"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-v3-collection.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-collection-v3.schema.json"

PARENT_FILE_SHA256 = {
    "benchmarks/manifests/cpp-formal-v2-authorized-collection.json": ("2a7466c57ef0de1d39d64c4e2987a073790e1f147bd83d8fd24439f6494a60dc"),
    "benchmarks/schemas/forge-cpp-formal-collection-v2-authorized.schema.json": ("f562667fffac23a22da52bfa2425769bd659b5e51854f1ae8e019954cbe23dc6"),
    "scripts/forge_formal_collection_v2_authorized_protocol.py": ("33aec026fd851351577e35f4a83566d693277309dbb23bae94de2deb2e655bfc"),
    "scripts/forge_formal_collection_v2_authorized_runner.py": ("45dae0a84dd968bb9cca9ab3d0ae7ce3c96c69867393e5967ec48d7e07499a67"),
}
V2_CANONICAL_SHA256 = "f7888bbbf1d5f2b404d5769f73442308a7234559bb5c6bcec3533f39fc69e923"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


formal_collection = _load_module(
    "forge_formal_collection_v3_protocol_test",
    PROTOCOL_PATH,
)
runner = _load_module(
    "forge_formal_collection_v3_runner_test",
    RUNNER_PATH,
)


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


def test_v3_manifest_is_committed_and_schema_valid() -> None:
    manifest = load_manifest()
    parent = json.loads(PARENT_MANIFEST_PATH.read_text(encoding="utf-8"))

    assert formal_collection.validate_manifest(manifest) == manifest
    assert manifest["collection_plan"] == parent["collection_plan"]
    assert manifest["cases"] == parent["cases"]
    assert manifest["conditions"] == parent["conditions"]
    assert manifest["scope"]["collection_authorized"] is False
    assert manifest["scope"]["formal_comparison_enabled"] is False
    assert parent["scope"]["collection_authorized"] is True

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(manifest, schema)


def test_v3_binds_repaired_baseline_parent_and_excluded_v2_evidence() -> None:
    manifest = load_manifest()
    authorization = manifest["authorization"]
    excluded = authorization["excluded_v2_launch"]

    assert manifest["forge"]["commit_sha"] == ("4578739983f5d23cb3e21ff619b1e33aba702859")
    assert authorization["issue_url"].endswith("/issues/90")
    assert authorization["parent_manifest"]["canonical_sha256"] == V2_CANONICAL_SHA256
    assert authorization["budget_request"] == {
        "confirmed": False,
        "maximum_tokens": 29315818,
        "tokens_observed_in_excluded_v2": 143286,
        "remaining_tokens_ceiling": 29172532,
    }
    assert excluded["status"] == "excluded_infrastructure_launch"
    assert excluded["attempts"] == 10
    assert excluded["model_requests_started"] == 32
    assert excluded["model_requests_completed"] == 32
    assert excluded["recorded_tokens"] == 143286
    assert excluded["oracle_passes"] == 0
    assert excluded["build_system_mismatch_attempts"] == 10
    assert excluded["residual_containers"] == 0
    assert len(excluded["ledger_sha256"]) == 10
    assert authorization["collection_constraints"]["required_runtime_launch_checks"] == ["evidence_mount_source_matches_host_workspace"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["scope"].update(collection_authorized=True),
        lambda value: value["scope"].update(formal_comparison_enabled=True),
        lambda value: value["authorization"]["budget_request"].update(confirmed=True),
        lambda value: value["authorization"]["excluded_v2_launch"].update(recorded_tokens=143285),
        lambda value: value["collection_plan"].reverse(),
    ],
)
def test_v3_rejects_authorization_parent_or_evidence_drift(mutation) -> None:
    manifest = copy.deepcopy(load_manifest())
    mutation(manifest)

    with pytest.raises(formal_collection.BenchmarkError):
        formal_collection.validate_manifest(manifest)


def test_authorized_v2_parent_files_remain_byte_identical() -> None:
    for relative_path, expected in PARENT_FILE_SHA256.items():
        actual = hashlib.sha256((REPO_ROOT / relative_path).read_bytes()).hexdigest()
        assert actual == expected


def test_v3_runner_loads_unapproved_policy_and_shared_v2_runtime() -> None:
    manifest = runner._load_manifest(MANIFEST_PATH)
    first_slot = manifest["collection_plan"][0]
    policy = runner.build_policy(
        manifest,
        case_id=first_slot["case_id"],
        condition_id=first_slot["condition_id"],
        repetition=first_slot["repetition"],
    )

    assert policy.benchmark_id == "forge-cpp-formal-v3-collection"
    assert policy.memory_enabled is False
    assert policy.artifact_instructions
    assert runner.protocol.SCHEMA_VERSION == formal_collection.SCHEMA_VERSION
    assert runner._runner.asyncio is not None


@pytest.mark.parametrize(
    ("root", "source", "expected"),
    [
        (
            "/mnt/c/work/Forge-AutoCompiler",
            "/mnt/c/work/Forge-AutoCompiler/.compile-sessions",
            True,
        ),
        (
            "/mnt/c/work/Forge-AutoCompiler/",
            "/mnt/c/work/Forge-AutoCompiler/.compile-sessions/",
            True,
        ),
        (
            "/mnt/c/work/Forge-AutoCompiler",
            "/.compile-sessions",
            False,
        ),
        ("", "/mnt/c/work/Forge-AutoCompiler/.compile-sessions", False),
        ("/", "/.compile-sessions", False),
    ],
)
def test_evidence_mount_source_must_match_host_workspace(
    root: str,
    source: str,
    expected: bool,
) -> None:
    assert (
        runner._evidence_mount_source_matches_host_workspace(
            _evidence_mount(source),
            host_workspace_root=root,
        )
        is expected
    )


def test_runtime_preflight_adds_mount_source_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DEER_FLOW_HOST_WORKSPACE_ROOT",
        "/mnt/c/work/Forge-AutoCompiler",
    )
    monkeypatch.setattr(
        runner,
        "_original_collect_runtime_launch_preflight",
        lambda *args, **kwargs: {
            "ready": True,
            "checks": {"evidence_mount_is_bind_rw": True},
        },
    )
    monkeypatch.setattr(
        runner._runner,
        "_current_container_metadata",
        lambda *args, **kwargs: (
            {},
            _evidence_mount("/.compile-sessions"),
        ),
    )

    rejected = runner.collect_runtime_launch_preflight(tmp_path)
    assert rejected["ready"] is False
    assert rejected["checks"]["evidence_mount_source_matches_host_workspace"] is False

    monkeypatch.setattr(
        runner._runner,
        "_current_container_metadata",
        lambda *args, **kwargs: (
            {},
            _evidence_mount("/mnt/c/work/Forge-AutoCompiler/.compile-sessions"),
        ),
    )
    accepted = runner.collect_runtime_launch_preflight(tmp_path)
    assert accepted["ready"] is True
    assert accepted["checks"]["evidence_mount_source_matches_host_workspace"] is True


def test_all_unapproved_cli_actions_are_rejected_without_evidence(
    tmp_path: Path,
) -> None:
    manifest = load_manifest()
    first_slot = manifest["collection_plan"][0]
    common = ["--manifest", str(MANIFEST_PATH)]

    commands = [
        [
            "provider-canary",
            *common,
            "--output-dir",
            str(tmp_path),
        ],
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
