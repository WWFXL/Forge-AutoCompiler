from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest

from deerflow.models import factory as model_factory

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "scripts" / "forge_formal_collection_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts" / "forge_formal_collection_runner.py"
PARENT_MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-v1.json"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-v1-collection.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-collection-v1.schema.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


formal_collection = _load_module("forge_formal_collection_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_benchmark_runner_formal_collection_test", RUNNER_PATH)


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _successful_canary_report(manifest: dict, output_dir: Path) -> Path:
    report = {
        "schema_version": "formal-provider-canary-1.0.0",
        "document_type": "formal_provider_canary",
        "canary_id": "provider_canary_" + "1" * 32,
        "benchmark_id": manifest["benchmark"]["id"],
        "manifest_sha256": formal_collection.manifest_sha256(manifest),
        "control_plane_topology": formal_collection.CONTROL_PLANE_TOPOLOGY,
        "conditions": [{"id": condition["id"], "passed": True} for condition in manifest["conditions"]],
        "passed": True,
    }
    path = output_dir / runner._PROVIDER_CANARY_DIRNAME / "provider_canary_test.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def _fake_runtime_preflight() -> dict:
    return {"ready": True, "checks": {"runtime": True}}


def _fake_preflight(manifest: dict, *, ready: bool) -> dict:
    return {
        "ready": ready,
        "manifest_sha256": formal_collection.manifest_sha256(manifest),
        "manifest_file_sha256": "1" * 64,
        "forge": {},
        "protocol": {},
        "runtime": {},
        "checks": {"ready": ready},
    }


def test_authorized_manifest_is_generated_committed_and_schema_valid() -> None:
    manifest = load_manifest()
    parent = json.loads(PARENT_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert formal_collection.generate_manifest() == manifest
    assert formal_collection.validate_manifest(manifest) == manifest
    assert manifest["scope"]["collection_authorized"] is True
    assert parent["scope"]["collection_authorized"] is False
    assert manifest["collection_plan"] == parent["collection_plan"]
    assert manifest["cases"] == parent["cases"]
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(manifest, schema)


def test_authorization_binds_parent_budget_issue_and_batch_limit() -> None:
    manifest = load_manifest()
    authorization = manifest["authorization"]
    assert authorization["parent_manifest"]["canonical_sha256"] == ("50ee3b447648d3149789a4b72bdab7a58c067b68f9cbca2a993e7843cd3889b1")
    assert authorization["issue_url"].endswith("/issues/82")
    assert authorization["budget_confirmation"] == {
        "confirmed": True,
        "maximum_tokens": 29396970,
        "maximum_serial_hours": 31.301,
    }
    assert authorization["collection_constraints"]["initial_batch_size"] == 10
    assert authorization["collection_constraints"]["provider_canary_required_before_first_ledger"] is True


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["authorization"]["budget_confirmation"].update(confirmed=False),
        lambda value: value["scope"].update(collection_authorized=False),
        lambda value: value["collection_plan"].reverse(),
        lambda value: value["cases"][0]["protocol"].update(source_subdir="../escape"),
    ],
)
def test_authorized_manifest_rejects_identity_or_parent_drift(mutation) -> None:
    manifest = copy.deepcopy(load_manifest())
    mutation(manifest)
    with pytest.raises(formal_collection.BenchmarkError):
        formal_collection.validate_manifest(manifest)


def test_runner_loads_authorized_policy_with_formal_artifact_contract() -> None:
    manifest = runner._load_manifest(MANIFEST_PATH)
    first_slot = manifest["collection_plan"][0]
    policy = runner.build_policy(
        manifest,
        case_id=first_slot["case_id"],
        condition_id=first_slot["condition_id"],
        repetition=first_slot["repetition"],
    )
    case = next(case for case in manifest["cases"] if case["id"] == first_slot["case_id"])
    assert policy.benchmark_id == "forge-cpp-formal-v1-collection"
    assert policy.artifact_instructions
    assert policy.source_subdir == case["protocol"]["source_subdir"]


def test_formal_attempt_requires_successful_canary_before_ledger(tmp_path: Path) -> None:
    manifest = load_manifest()
    first_slot = manifest["collection_plan"][0]
    with pytest.raises(runner.RunnerError, match="canary"):
        runner.create_attempt(
            manifest,
            case_id=first_slot["case_id"],
            condition_id=first_slot["condition_id"],
            repetition=first_slot["repetition"],
            output_dir=tmp_path,
            check_endpoint=False,
        )
    assert list(tmp_path.rglob("*.jsonl")) == []


def test_formal_preflight_failure_does_not_create_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    first_slot = manifest["collection_plan"][0]
    _successful_canary_report(manifest, tmp_path)
    monkeypatch.setattr(
        runner,
        "collect_runtime_launch_preflight",
        lambda *args, **kwargs: _fake_runtime_preflight(),
    )
    monkeypatch.setattr(
        runner,
        "collect_preflight",
        lambda *args, **kwargs: _fake_preflight(manifest, ready=False),
    )
    with pytest.raises(runner.RunnerError, match="before physical-attempt ledger"):
        runner.create_attempt(
            manifest,
            case_id=first_slot["case_id"],
            condition_id=first_slot["condition_id"],
            repetition=first_slot["repetition"],
            output_dir=tmp_path,
            check_endpoint=False,
        )
    assert list(tmp_path.rglob("*.jsonl")) == []


def test_dual_provider_canary_writes_sanitized_append_only_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()

    class FakeModel:
        def invoke(self, _message: str):
            return SimpleNamespace(content="CANARY_OK")

    monkeypatch.setattr(runner, "_running_inside_compose_dood", lambda _repo_root: True)
    monkeypatch.setattr(
        runner,
        "collect_preflight",
        lambda *args, **kwargs: _fake_preflight(manifest, ready=True),
    )
    monkeypatch.setattr(
        model_factory,
        "create_chat_model",
        lambda **kwargs: FakeModel(),
    )
    result = runner.collect_provider_canary(
        manifest,
        manifest_path=MANIFEST_PATH,
        output_dir=tmp_path,
        repo_root=tmp_path,
    )
    assert result["passed"] is True
    assert len(result["conditions"]) == 2
    report_path = Path(result["report_path"])
    report_text = report_path.read_text(encoding="utf-8")
    assert "CANARY_OK" not in report_text
    assert "api_key" not in report_text
    assert runner._successful_provider_canary(manifest, output_dir=tmp_path) == report_path


def test_formal_batch_stops_at_the_ten_slot_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    created_slots: list[tuple[str, str, int]] = []

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
        ledger = SimpleNamespace(
            path=tmp_path / f"ledger-{index}.jsonl",
            physical_attempt_id=f"physical_attempt_{index:032x}",
        )
        return ledger, {}

    monkeypatch.setattr(runner, "_observed_collection_ledgers", lambda *args, **kwargs: [])
    monkeypatch.setattr(runner, "create_attempt", fake_create_attempt)
    monkeypatch.setattr(runner, "run_attempt", lambda *args, **kwargs: {"status": "failed"})
    result = runner.run_formal_batch(
        manifest,
        manifest_path=MANIFEST_PATH,
        output_dir=tmp_path,
        max_attempts=10,
    )
    expected = [(slot["case_id"], slot["condition_id"], slot["repetition"]) for slot in manifest["collection_plan"][:10]]
    assert created_slots == expected
    assert result["start_slot_index"] == 0
    assert result["next_slot_index"] == 10
    assert result["batch_end_slot_index"] == 10
    assert result["attempts_completed"] == 10
    with pytest.raises(runner.RunnerError, match="between 1 and 10"):
        runner.run_formal_batch(
            manifest,
            manifest_path=MANIFEST_PATH,
            output_dir=tmp_path,
            max_attempts=11,
        )
