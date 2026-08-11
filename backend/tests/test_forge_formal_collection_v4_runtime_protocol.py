from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "scripts" / "forge_formal_collection_v4_runtime_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts" / "forge_formal_collection_v4_runtime_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-v4-runtime-candidate.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-collection-v4-runtime-candidate.schema.json"
PARENT_FILE_SHA256 = {
    "scripts/forge_formal_collection_v4_protocol.py": ("a021ceafa91af6e308bba2f702ab1e8ce985b672e1097ddbea479db336959704"),
    "scripts/forge_formal_collection_v4_runner.py": ("4470d28388fcff73498a509e382716edc864ee1503b8791d39fa516a9ae5b73a"),
    "benchmarks/manifests/cpp-formal-v4-collection.json": ("68e752e2ec85964045a9c7e27e87cf61e20b500a127e9326e28c1b4ad6bd592a"),
    "benchmarks/schemas/forge-cpp-formal-collection-v4.schema.json": ("6ac282bbbe47cd871f582d26b002bf0e3650bcfe5de03b0692225b57ba4acd72"),
    "benchmarks/preregistrations/cpp-formal-v4-amendment.md": ("90e43a47bb54a9de036d026faeaacfedf051a6e4ec0f82da355c32a29198aef4"),
}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


protocol = _load_module("forge_formal_collection_v4_runtime_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_formal_collection_v4_runtime_runner_test", RUNNER_PATH)


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_runtime_candidate_is_schema_valid_deterministic_and_unapproved() -> None:
    manifest = load_manifest()

    assert protocol.validate_manifest(manifest) == manifest
    assert protocol.generate_manifest() == manifest
    assert manifest["schema_version"] == "formal-collection-4.1.0-runtime-candidate"
    assert manifest["scope"]["collection_authorized"] is False
    assert manifest["scope"]["formal_comparison_enabled"] is False
    assert manifest["forge"]["commit_sha"] == ("3ac49b92eedecf4932a829e75465dd7ddd16b97e")
    assert manifest["authorization"]["issue_url"].endswith("/issues/105")
    assert manifest["authorization"]["collection_constraints"] == {
        "collection_authorized": False,
        "provider_canary_forbidden": True,
        "physical_attempt_creation_forbidden": True,
        "model_execution_forbidden": True,
        "batch_execution_forbidden": True,
        "complete_project_blocks_require_confirmation": True,
        "slot_count_requires_confirmation": True,
        "recorded_token_budget_requires_confirmation": True,
        "replacement_forbidden": True,
        "fallback_forbidden": True,
        "retry_forbidden": True,
        "backfill_forbidden": True,
    }

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(manifest, schema)


def test_runtime_candidate_preserves_v4_design_and_parent_bytes() -> None:
    manifest = load_manifest()
    parent = json.loads((REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-v4-collection.json").read_text(encoding="utf-8"))

    for field in (
        "source_protocols",
        "model_profiles",
        "runtime",
        "budget",
        "conditions",
        "collection_plan",
        "schedule_sha256",
        "cases",
        "attempt_budget",
        "resource_preflight",
        "analysis_plan",
    ):
        assert manifest[field] == parent[field]
    assert manifest["attempt_budget"]["total_wall_clock_seconds"] == 1800
    assert manifest["attempt_budget"]["cleanup_reserve_seconds"] == 120
    assert manifest["attempt_budget"]["max_compiler_invocations"] == 2
    assert manifest["attempt_budget"]["max_model_requests"] == 48
    assert manifest["authorization"]["parent_manifest"]["canonical_sha256"] == "bb151473b276c48b9faf287a9dcbdddd96145abf3acc605f952275cf3d3f6720"

    for relative_path, expected in PARENT_FILE_SHA256.items():
        assert hashlib.sha256((REPO_ROOT / relative_path).read_bytes()).hexdigest() == expected


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["scope"].update(collection_authorized=True),
        lambda value: value["attempt_budget"].update(total_wall_clock_seconds=1801),
        lambda value: value["attempt_budget"].update(max_model_requests=49),
        lambda value: value["authorization"]["collection_constraints"].update(model_execution_forbidden=False),
        lambda value: value["collection_plan"].reverse(),
    ],
)
def test_runtime_candidate_rejects_protocol_or_authorization_drift(
    mutation,
) -> None:
    manifest = copy.deepcopy(load_manifest())
    mutation(manifest)

    with pytest.raises(protocol.BenchmarkError):
        protocol.validate_manifest(manifest)


def test_runtime_runner_injects_reviewed_budget_into_future_authorized_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    captured = {}

    def fake_run_attempt(
        observed_manifest,
        ledger_path,
        *,
        async_runner,
        attempt_budget,
    ):
        captured.update(
            manifest=observed_manifest,
            ledger_path=ledger_path,
            async_runner=async_runner,
            attempt_budget=attempt_budget,
        )
        return {"status": "not-executed"}

    monkeypatch.setattr(runner, "_original_run_attempt", fake_run_attempt)

    result = runner.run_attempt_with_budget(
        manifest,
        tmp_path / "not-created.jsonl",
    )

    assert result == {"status": "not-executed"}
    budget = captured["attempt_budget"]
    assert budget.total_wall_clock_seconds == 1800
    assert budget.work_deadline_seconds == 1680
    assert budget.cleanup_reserve_seconds == 120
    assert budget.max_compiler_invocations == 2
    assert budget.max_model_requests == 48
    assert not captured["ledger_path"].exists()


def test_runtime_runner_loads_policy_without_authorizing_collection() -> None:
    manifest = runner._load_manifest(MANIFEST_PATH)
    first_slot = manifest["collection_plan"][0]

    policy = runner.build_policy(
        manifest,
        case_id=first_slot["case_id"],
        condition_id=first_slot["condition_id"],
        repetition=first_slot["repetition"],
    )

    assert policy.benchmark_id == "forge-cpp-formal-v4-runtime-candidate"
    assert policy.memory_enabled is False
    assert policy.artifact_instructions


def test_runtime_candidate_cli_rejects_all_external_actions_without_evidence(
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
