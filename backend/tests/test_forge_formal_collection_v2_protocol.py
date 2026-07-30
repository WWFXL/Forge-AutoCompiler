from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest

from deerflow.config.memory_config import get_memory_config

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "scripts" / "forge_formal_collection_v2_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts" / "forge_formal_collection_v2_runner.py"
PARENT_MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-v1-collection.json"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-v2-collection.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-collection-v2.schema.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


formal_collection_v2 = _load_module(
    "forge_formal_collection_v2_protocol_test",
    PROTOCOL_PATH,
)
runner_v2 = _load_module(
    "forge_formal_collection_v2_runner_test",
    RUNNER_PATH,
)


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_v2_candidate_is_committed_and_schema_valid() -> None:
    manifest = load_manifest()
    parent = json.loads(PARENT_MANIFEST_PATH.read_text(encoding="utf-8"))

    assert formal_collection_v2.validate_manifest(manifest) == manifest
    assert manifest["collection_plan"] == parent["collection_plan"]
    assert manifest["cases"] == parent["cases"]
    assert manifest["scope"]["collection_authorized"] is False
    assert manifest["scope"]["formal_comparison_enabled"] is False
    assert manifest["authorization"]["budget_request"]["confirmed"] is False
    assert manifest["authorization"]["status"] == "pending_experiment_owner_confirmation"

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(manifest, schema)


def test_v2_candidate_binds_superseded_launch_and_remaining_budget() -> None:
    authorization = load_manifest()["authorization"]

    assert authorization["issue_url"].endswith("/issues/84")
    assert authorization["parent_manifest"]["canonical_sha256"] == ("8cfd909724a540a87fee9d68f7dafc0095964dd61150083a76f2ffdadc533aeb")
    assert authorization["budget_request"]["remaining_tokens_ceiling"] == 29315818
    assert authorization["superseded_launch"]["attempts"] == 10
    assert authorization["superseded_launch"]["connection_error_attempts"] == 6
    assert authorization["superseded_launch"]["build_system_mismatch_attempts"] == 4
    assert len(authorization["superseded_launch"]["ledger_sha256"]) == 10


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["scope"].update(collection_authorized=True),
        lambda value: value["authorization"]["budget_request"].update(confirmed=True),
        lambda value: value["authorization"]["superseded_launch"]["ledger_sha256"].update({"slot-000": "0" * 64}),
        lambda value: value["collection_plan"].reverse(),
    ],
)
def test_v2_candidate_rejects_authorization_or_launch_audit_drift(
    mutation,
) -> None:
    manifest = copy.deepcopy(load_manifest())
    mutation(manifest)

    with pytest.raises(formal_collection_v2.BenchmarkError):
        formal_collection_v2.validate_manifest(manifest)


def test_v2_candidate_binds_repaired_runtime_components() -> None:
    manifest = load_manifest()
    component_hashes = manifest["forge"]["component_sha256"]

    assert ("backend/packages/harness/deerflow/agents/middlewares/memory_middleware.py") in component_hashes
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is unavailable in the minimal backend image")
    for relative_path, expected_digest in component_hashes.items():
        result = subprocess.run(
            [git, "show", f"{manifest['forge']['commit_sha']}:{relative_path}"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
        )
        assert hashlib.sha256(result.stdout).hexdigest() == expected_digest


def test_v2_attempt_context_disables_and_restores_memory() -> None:
    original = get_memory_config()
    policy = SimpleNamespace(memory_enabled=False)

    with runner_v2._benchmark_memory_scope(policy):
        current = get_memory_config()
        assert current.enabled is False
        assert current.injection_enabled is False

    assert get_memory_config() is original


def test_v2_attempt_message_freezes_the_lead_tool_sequence() -> None:
    policy = SimpleNamespace(
        expected_repo_url="https://example.com/repo",
        expected_commit_sha="1" * 40,
    )

    message = runner_v2._attempt_message(policy)

    assert ('prepare_compile_session -> clone_repository -> identify_build_system -> task(subagent_type="compiler") -> finalize_session') in message
    assert "Do not call finalize_session until" in message


def test_v2_candidate_cannot_run_canary_or_create_ledger(
    tmp_path: Path,
) -> None:
    manifest = load_manifest()
    first_slot = manifest["collection_plan"][0]

    with pytest.raises(runner_v2.RunnerError, match="not authorized"):
        runner_v2.collect_provider_canary(
            manifest,
            manifest_path=MANIFEST_PATH,
            output_dir=tmp_path,
            repo_root=tmp_path,
        )
    with pytest.raises(runner_v2.RunnerError, match="not authorized"):
        runner_v2.create_attempt(
            manifest,
            case_id=first_slot["case_id"],
            condition_id=first_slot["condition_id"],
            repetition=first_slot["repetition"],
            output_dir=tmp_path,
            manifest_path=MANIFEST_PATH,
            check_endpoint=False,
        )

    assert list(tmp_path.rglob("*.json")) == []
    assert list(tmp_path.rglob("*.jsonl")) == []


def test_v2_batch_reuses_one_asyncio_runner_for_all_slots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    created_slots: list[tuple[str, str, int]] = []
    observed_runner_ids: list[int] = []

    def fake_create_attempt(
        _manifest: dict,
        *,
        case_id: str,
        condition_id: str,
        repetition: int,
        **_kwargs,
    ):
        created_slots.append((case_id, condition_id, repetition))
        index = len(created_slots)
        return (
            SimpleNamespace(
                path=tmp_path / f"ledger-{index}.jsonl",
                physical_attempt_id=f"physical_attempt_{index:032x}",
            ),
            {},
        )

    def fake_run_attempt(
        _manifest: dict,
        _ledger_path: Path,
        *,
        async_runner: asyncio.Runner,
    ) -> dict:
        assert isinstance(async_runner, asyncio.Runner)
        observed_runner_ids.append(id(async_runner))
        return {"status": "failed"}

    monkeypatch.setattr(
        runner_v2,
        "_observed_collection_ledgers",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(runner_v2, "create_attempt", fake_create_attempt)
    monkeypatch.setattr(runner_v2, "run_attempt", fake_run_attempt)

    result = runner_v2.run_formal_batch(
        manifest,
        manifest_path=MANIFEST_PATH,
        output_dir=tmp_path,
        max_attempts=10,
    )

    expected = [
        (
            slot["case_id"],
            slot["condition_id"],
            slot["repetition"],
        )
        for slot in manifest["collection_plan"][:10]
    ]
    assert created_slots == expected
    assert len(set(observed_runner_ids)) == 1
    assert result["attempts_completed"] == 10
    assert result["next_slot_index"] == 10
    assert result["batch_end_slot_index"] == 10
