from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "scripts" / "forge_formal_collection_v3_authorized_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts" / "forge_formal_collection_v3_authorized_runner.py"
PARENT_MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-v3-collection.json"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-v3-authorized-collection.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-collection-v3-authorized.schema.json"
PARENT_CANONICAL_SHA256 = "9777816f157078ae555969c6c77ca8734ca4e1417235f57c98a628c384031b5d"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


formal_collection = _load_module(
    "forge_formal_collection_v3_authorized_protocol_test",
    PROTOCOL_PATH,
)
runner = _load_module(
    "forge_formal_collection_v3_authorized_runner_test",
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


def test_authorized_v3_manifest_is_committed_and_schema_valid() -> None:
    manifest = load_manifest()
    parent = json.loads(PARENT_MANIFEST_PATH.read_text(encoding="utf-8"))

    assert formal_collection.validate_manifest(manifest) == manifest
    assert manifest["collection_plan"] == parent["collection_plan"]
    assert manifest["cases"] == parent["cases"]
    assert manifest["conditions"] == parent["conditions"]
    assert manifest["scope"]["collection_authorized"] is True
    assert parent["scope"]["collection_authorized"] is False
    assert manifest["model_profiles"]["richlab-gpt-5.5"]["endpoint"] == ("https://rich-api.choosefire.com/v1")

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(manifest, schema)


def test_authorization_binds_owner_budget_network_and_boundaries() -> None:
    authorization = load_manifest()["authorization"]

    assert authorization["authorized_on"] == "2026-08-11"
    assert authorization["issue_url"].endswith("/issues/95")
    assert authorization["parent_manifest"]["canonical_sha256"] == (PARENT_CANONICAL_SHA256)
    assert authorization["network_observation"] == {
        "access_medium": "mobile_hotspot",
        "browser_ui_required": False,
    }
    assert authorization["budget_confirmation"]["maximum_recorded_tokens"] == 1_633_165
    constraints = authorization["collection_constraints"]
    assert constraints["authorized_slot_count"] == 10
    assert constraints["remaining_slot_count"] == 170
    assert constraints["remaining_slots_require_additional_confirmation"] is True
    assert constraints["evidence_directory"].endswith("benchmark-evidence-formal-v3-authorized")
    assert constraints["required_runtime_launch_checks"] == ["evidence_mount_source_matches_host_workspace"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["scope"].update(collection_authorized=False),
        lambda value: value["authorization"]["budget_confirmation"].update(maximum_recorded_tokens=1_633_166),
        lambda value: value["authorization"]["network_observation"].update(access_medium="wifi"),
        lambda value: value["authorization"]["collection_constraints"].update(authorized_slot_count=11),
        lambda value: value["model_profiles"]["richlab-gpt-5.5"].update(endpoint="https://example.invalid/v1"),
        lambda value: value["collection_plan"].reverse(),
    ],
)
def test_authorized_v3_rejects_identity_or_parent_drift(mutation) -> None:
    manifest = copy.deepcopy(load_manifest())
    mutation(manifest)

    with pytest.raises(formal_collection.BenchmarkError):
        formal_collection.validate_manifest(manifest)


def test_runner_loads_authorized_policy_and_real_execution_methods() -> None:
    manifest = runner._load_manifest(MANIFEST_PATH)
    first_slot = manifest["collection_plan"][0]
    policy = runner.build_policy(
        manifest,
        case_id=first_slot["case_id"],
        condition_id=first_slot["condition_id"],
        repetition=first_slot["repetition"],
    )

    assert policy.benchmark_id == "forge-cpp-formal-v3-authorized-collection"
    assert policy.endpoint == "https://rich-api.choosefire.com/v1"
    assert policy.memory_enabled is False
    assert policy.artifact_instructions
    assert runner._original_collect_provider_canary.__module__.endswith("_base")
    assert runner._original_create_attempt.__module__.endswith("_base")
    assert runner._original_run_attempt.__module__.endswith("_base")


def test_default_cli_manifest_is_the_authorized_v3_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    def fake_main(arguments: list[str]) -> int:
        captured.extend(arguments)
        return 0

    monkeypatch.setattr(runner._runner, "main", fake_main)

    assert runner.main(["preflight", "--output-dir", "/tmp/evidence"]) == 0
    assert captured[:3] == ["preflight", "--manifest", str(MANIFEST_PATH)]


def test_evidence_mount_source_gate_is_retained() -> None:
    assert runner._evidence_mount_source_matches_host_workspace(
        _evidence_mount("/mnt/c/work/Forge-AutoCompiler/.compile-sessions"),
        host_workspace_root="/mnt/c/work/Forge-AutoCompiler",
    )
    assert not runner._evidence_mount_source_matches_host_workspace(
        _evidence_mount("/.compile-sessions"),
        host_workspace_root="/mnt/c/work/Forge-AutoCompiler",
    )


def test_attempt_after_authorized_boundary_is_rejected_without_ledger(
    tmp_path: Path,
) -> None:
    manifest = load_manifest()
    slot = manifest["collection_plan"][10]

    with pytest.raises(runner.RunnerError, match="initial authorization"):
        runner.create_attempt(
            manifest,
            case_id=slot["case_id"],
            condition_id=slot["condition_id"],
            repetition=slot["repetition"],
            output_dir=tmp_path,
            manifest_path=MANIFEST_PATH,
            check_endpoint=False,
        )

    assert list(tmp_path.rglob("*.jsonl")) == []


def test_wrong_evidence_directory_is_rejected_before_canary(
    tmp_path: Path,
) -> None:
    with pytest.raises(runner.RunnerError, match="evidence directory"):
        runner.collect_provider_canary(
            load_manifest(),
            manifest_path=MANIFEST_PATH,
            output_dir=tmp_path,
        )


def test_recorded_token_boundary_blocks_next_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    slot = manifest["collection_plan"][0]
    observed = [
        (
            {
                "case_id": slot["case_id"],
                "condition_id": slot["condition_id"],
                "repetition": slot["repetition"],
            },
            [
                {
                    "event": "model.request_completed",
                    "payload": {"token_usage": {"total_tokens": 1_633_165}},
                }
            ],
        )
    ]
    monkeypatch.setattr(
        runner._runner,
        "_observed_collection_ledgers",
        lambda *args, **kwargs: observed,
    )

    with pytest.raises(runner.RunnerError, match="recorded-token boundary"):
        runner.create_attempt(
            manifest,
            case_id=slot["case_id"],
            condition_id=slot["condition_id"],
            repetition=slot["repetition"],
            output_dir=Path(manifest["authorization"]["collection_constraints"]["evidence_directory"]),
            manifest_path=MANIFEST_PATH,
            check_endpoint=False,
        )
