from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "scripts" / "forge_formal_collection_v2_authorized_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts" / "forge_formal_collection_v2_authorized_runner.py"
PARENT_MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-v2-collection.json"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-v2-authorized-collection.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-collection-v2-authorized.schema.json"

CANDIDATE_FILE_SHA256 = {
    "benchmarks/manifests/cpp-formal-v2-collection.json": ("e2537295a33ab52c136121ad02dc1034040bc95d52253944433884f10f629002"),
    "benchmarks/schemas/forge-cpp-formal-collection-v2.schema.json": ("aebe5e227419a47d248f3bbdc7b1cb4edae680acdd852ca1d29538be358f0f30"),
    "scripts/forge_formal_collection_v2_protocol.py": ("f35be9b66801defb5cf924089b00be801c12e121b1d7f33c565493bb08608499"),
    "scripts/forge_formal_collection_v2_runner.py": ("35f6b23ebbbb1e7bc5b540a0b9bfd627d23b75957095922aa79c2db396b64c4b"),
}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


formal_collection = _load_module(
    "forge_formal_collection_v2_authorized_protocol_test",
    PROTOCOL_PATH,
)
runner = _load_module(
    "forge_formal_collection_v2_authorized_runner_test",
    RUNNER_PATH,
)


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_authorized_manifest_is_committed_and_schema_valid() -> None:
    manifest = load_manifest()
    parent = json.loads(PARENT_MANIFEST_PATH.read_text(encoding="utf-8"))

    assert formal_collection.validate_manifest(manifest) == manifest
    assert manifest["collection_plan"] == parent["collection_plan"]
    assert manifest["cases"] == parent["cases"]
    assert manifest["scope"]["collection_authorized"] is True
    assert manifest["scope"]["formal_comparison_enabled"] is True
    assert parent["scope"]["collection_authorized"] is False

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(manifest, schema)


def test_authorization_binds_candidate_budget_issue_and_ten_slot_limit() -> None:
    authorization = load_manifest()["authorization"]

    assert authorization["issue_url"].endswith("/issues/86")
    assert authorization["parent_manifest"]["canonical_sha256"] == ("843cc7386d05af0bb0285852fc128a0693302253aabe2a300bad3efcf41330d3")
    assert authorization["budget_confirmation"]["confirmed"] is True
    assert authorization["budget_confirmation"]["maximum_tokens"] == 29315818
    assert authorization["collection_constraints"]["authorized_slot_count"] == 10
    assert authorization["collection_constraints"]["remaining_slots_require_additional_confirmation"] is True
    assert len(authorization["superseded_launch"]["ledger_sha256"]) == 10


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["scope"].update(collection_authorized=False),
        lambda value: value["authorization"]["budget_confirmation"].update(confirmed=False),
        lambda value: value["authorization"]["collection_constraints"].update(authorized_slot_count=11),
        lambda value: value["collection_plan"].reverse(),
    ],
)
def test_authorized_manifest_rejects_identity_or_parent_drift(
    mutation,
) -> None:
    manifest = copy.deepcopy(load_manifest())
    mutation(manifest)

    with pytest.raises(formal_collection.BenchmarkError):
        formal_collection.validate_manifest(manifest)


def test_candidate_protocol_files_remain_byte_identical() -> None:
    for relative_path, expected in CANDIDATE_FILE_SHA256.items():
        actual = hashlib.sha256((REPO_ROOT / relative_path).read_bytes()).hexdigest()
        assert actual == expected


def test_runner_loads_authorized_policy_and_shared_v2_runtime() -> None:
    manifest = runner._load_manifest(MANIFEST_PATH)
    first_slot = manifest["collection_plan"][0]
    policy = runner.build_policy(
        manifest,
        case_id=first_slot["case_id"],
        condition_id=first_slot["condition_id"],
        repetition=first_slot["repetition"],
    )

    assert policy.benchmark_id == "forge-cpp-formal-v2-authorized-collection"
    assert policy.memory_enabled is False
    assert policy.artifact_instructions
    assert runner.protocol_formal_collection.SCHEMA_VERSION == formal_collection.SCHEMA_VERSION


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


def test_batch_cannot_resume_after_authorized_ten_slot_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    observed = [
        (
            {
                "case_id": slot["case_id"],
                "condition_id": slot["condition_id"],
                "repetition": slot["repetition"],
            },
            [{"event": "experiment.completed"}],
        )
        for slot in manifest["collection_plan"][:10]
    ]
    monkeypatch.setattr(
        runner._runner,
        "_observed_collection_ledgers",
        lambda *args, **kwargs: observed,
    )

    with pytest.raises(runner.RunnerError, match="already been reached"):
        runner.run_formal_batch(
            manifest,
            manifest_path=MANIFEST_PATH,
            output_dir=tmp_path,
            max_attempts=1,
            check_endpoint=False,
        )


def test_authorized_runner_retains_shared_asyncio_batch_implementation() -> None:
    assert runner._original_run_formal_batch.__module__ == ("forge_formal_collection_v2_runner")
    assert "asyncio.Runner" in (
        runner._original_run_formal_batch.__annotations__.get("return", "")
        if isinstance(
            runner._original_run_formal_batch.__annotations__.get("return"),
            str,
        )
        else ""
    ) or hasattr(runner._runner, "asyncio")
