from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "scripts" / "forge_formal_collection_v4_authorized_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts" / "forge_formal_collection_v4_authorized_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-v4-authorized-initial-block.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-collection-v4-authorized.schema.json"
PARENT_MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-v4-ubuntu-candidate.json"
PARENT_CANONICAL_SHA256 = "77e80eb39b01eeba73d1fdd07e2b8da658032fcc124cacbf45ae2d06f6831601"
PARENT_FILE_SHA256 = {
    "scripts/forge_formal_collection_v4_ubuntu_protocol.py": "273ba1b711b9d89c218ccae2fd95f6d934b4af1b6fdc39715dbcbea6f4602a31",
    "scripts/forge_formal_collection_v4_ubuntu_runner.py": "070f48d76d9a06f9f68d67f6abcdf3e885a5d1096c7b7725aa5df56a09082cc8",
    "benchmarks/manifests/cpp-formal-v4-ubuntu-candidate.json": "2526ad6d9765577ad5256330579b182ba855bc6ddf29d92367922069e5de26fd",
    "benchmarks/schemas/forge-cpp-formal-collection-v4-ubuntu-candidate.schema.json": "2a3ab3b2d3a0543470f136e8465fd64cee2cc5dc9f6343b4b40a7a186739e55f",
    "benchmarks/preregistrations/cpp-formal-v4-ubuntu-gate-and-initial-block.md": "4118549635ec99b60d9126f1ae82f7d6df74e4b699c57aa3448d302e26aa312d",
}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


protocol = _load_module(
    "forge_formal_collection_v4_authorized_protocol_test",
    PROTOCOL_PATH,
)
runner = _load_module(
    "forge_formal_collection_v4_authorized_runner_test",
    RUNNER_PATH,
)


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_authorized_manifest_is_deterministic_schema_valid_and_bounded() -> None:
    manifest = load_manifest()

    assert protocol.validate_manifest(manifest) == manifest
    assert protocol.generate_manifest() == manifest
    assert manifest["schema_version"] == "formal-collection-4.3.0-ubuntu-authorized"
    assert manifest["scope"]["collection_authorized"] is True
    assert manifest["scope"]["formal_comparison_enabled"] is True
    assert manifest["forge"]["commit_sha"] == "c079f31c1623111e3dd776952b151181cfa37a00"
    assert manifest["runtime"]["docker_daemon_provider"] == "ubuntu-native"
    assert manifest["runtime"]["docker_socket_path"] == "/var/run/docker.sock"

    authorization = manifest["authorization"]
    assert authorization["issue_url"].endswith("/issues/111")
    assert authorization["parent_manifest"]["canonical_sha256"] == PARENT_CANONICAL_SHA256
    assert authorization["budget_confirmation"]["maximum_recorded_tokens"] == 980_000
    assert authorization["collection_constraints"]["authorized_schedule_orders"] == [1, 2, 73, 74, 153, 154]
    assert authorization["collection_constraints"]["provider_canary_max_attempts"] == 1

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(manifest, schema)


def test_authorized_slots_preserve_original_schedule_identity() -> None:
    slots = runner._authorized_slots(load_manifest())

    assert [slot["order"] for slot in slots] == [1, 2, 73, 74, 153, 154]
    assert {slot["case_id"] for slot in slots} == {"cppitertools"}
    assert {(slot["condition_id"], slot["repetition"]) for slot in slots} == {(condition, repetition) for condition in ("richlab-gpt-5.5", "deepseek-v4-flash") for repetition in range(1, 4)}
    assert len(load_manifest()["collection_plan"]) == 180


def test_parent_ubuntu_candidate_files_remain_byte_identical() -> None:
    for relative_path, expected in PARENT_FILE_SHA256.items():
        assert hashlib.sha256((REPO_ROOT / relative_path).read_bytes()).hexdigest() == expected


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["scope"].update(collection_authorized=False),
        lambda value: value["runtime"].update(docker_daemon_provider="docker-desktop-wsl2"),
        lambda value: value["authorization"]["budget_confirmation"].update(maximum_recorded_tokens=980_001),
        lambda value: value["authorization"]["collection_constraints"].update(authorized_schedule_orders=[1, 2]),
        lambda value: value["authorization"]["collection_constraints"].update(provider_canary_max_attempts=2),
        lambda value: value["initial_batch_decision"].update(status="pending_experiment_owner_confirmation"),
        lambda value: value["collection_plan"].reverse(),
    ],
)
def test_authorized_manifest_rejects_environment_budget_or_identity_drift(mutation) -> None:
    manifest = copy.deepcopy(load_manifest())
    mutation(manifest)

    with pytest.raises(protocol.BenchmarkError):
        protocol.validate_manifest(manifest)


def test_authorized_order_projects_only_the_six_reviewed_slots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    slots = runner._authorized_slots(manifest)
    monkeypatch.setattr(runner, "_observed_authorized_ledgers", lambda *args, **kwargs: [])

    assert (
        runner._enforce_authorized_order(
            manifest,
            case_id=slots[0]["case_id"],
            condition_id=slots[0]["condition_id"],
            repetition=slots[0]["repetition"],
            output_dir=tmp_path,
        )
        == 0
    )
    with pytest.raises(runner.RunnerError, match="not next"):
        runner._enforce_authorized_order(
            manifest,
            case_id=slots[1]["case_id"],
            condition_id=slots[1]["condition_id"],
            repetition=slots[1]["repetition"],
            output_dir=tmp_path,
        )


def test_create_attempt_bypasses_only_the_parent_prefix_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    slot = runner._authorized_slots(manifest)[0]
    captured: dict[str, object] = {}

    monkeypatch.setattr(runner, "_require_authorized_output_dir", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "_ensure_token_budget_remaining", lambda *args, **kwargs: 0)
    monkeypatch.setattr(runner, "_enforce_authorized_order", lambda *args, **kwargs: 0)

    def fake_create(*args, **kwargs):
        captured["parent_gate"] = runner._runner._enforce_frozen_collection_order
        captured["kwargs"] = kwargs
        return "ledger", {"ready": True}

    original_parent_gate = runner._runner._enforce_frozen_collection_order
    monkeypatch.setattr(runner, "_original_create_attempt", fake_create)

    assert (
        runner.create_attempt(
            manifest,
            case_id=slot["case_id"],
            condition_id=slot["condition_id"],
            repetition=slot["repetition"],
            output_dir=tmp_path,
        )[0]
        == "ledger"
    )
    assert captured["parent_gate"] is not original_parent_gate
    assert runner._runner._enforce_frozen_collection_order is original_parent_gate


def test_token_boundary_rejects_before_attempt_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    observed = [
        (
            runner._slot_identity(runner._authorized_slots(manifest)[0]),
            [
                {
                    "event": "model.request_completed",
                    "payload": {"token_usage": {"total_tokens": 980_000}},
                }
            ],
        )
    ]
    monkeypatch.setattr(
        runner,
        "_observed_authorized_ledgers",
        lambda *args, **kwargs: observed,
    )

    with pytest.raises(runner.RunnerError, match="recorded-token boundary"):
        runner._ensure_token_budget_remaining(manifest, output_dir=tmp_path)


def test_provider_canary_is_consumed_once_after_empty_and_zero_orphan_gates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    monkeypatch.setattr(runner, "_require_authorized_output_dir", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "_observed_authorized_ledgers", lambda *args, **kwargs: [])
    monkeypatch.setattr(runner, "_formal_container_ids", lambda: [])
    monkeypatch.setattr(
        runner,
        "_original_collect_provider_canary",
        lambda *args, **kwargs: {"passed": True},
    )

    assert (
        runner.collect_provider_canary(
            manifest,
            manifest_path=MANIFEST_PATH,
            output_dir=tmp_path,
        )["passed"]
        is True
    )
    marker = json.loads(runner._canary_marker_path(tmp_path).read_text(encoding="utf-8"))
    assert marker["status"] == "passed"

    with pytest.raises(runner.RunnerError, match="already been consumed"):
        runner.collect_provider_canary(
            manifest,
            manifest_path=MANIFEST_PATH,
            output_dir=tmp_path,
        )


def test_provider_canary_failure_is_terminal_and_does_not_create_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    monkeypatch.setattr(runner, "_require_authorized_output_dir", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "_observed_authorized_ledgers", lambda *args, **kwargs: [])
    monkeypatch.setattr(runner, "_formal_container_ids", lambda: [])

    def fail(*args, **kwargs):
        raise runner.RunnerError("endpoint failed")

    monkeypatch.setattr(runner, "_original_collect_provider_canary", fail)

    with pytest.raises(runner.RunnerError, match="endpoint failed"):
        runner.collect_provider_canary(
            manifest,
            manifest_path=MANIFEST_PATH,
            output_dir=tmp_path,
        )
    marker = json.loads(runner._canary_marker_path(tmp_path).read_text(encoding="utf-8"))
    assert marker["status"] == "failed"
    assert marker["error_class"] == "RunnerError"
    assert list(tmp_path.rglob("*.jsonl")) == []


@pytest.mark.parametrize("container_ids", [None, ["container-id"]])
def test_provider_canary_rejects_failed_reconciliation_or_residual_containers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    container_ids: list[str] | None,
) -> None:
    manifest = load_manifest()
    monkeypatch.setattr(runner, "_require_authorized_output_dir", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "_observed_authorized_ledgers", lambda *args, **kwargs: [])
    monkeypatch.setattr(runner, "_formal_container_ids", lambda: container_ids)

    with pytest.raises(runner.RunnerError):
        runner.collect_provider_canary(
            manifest,
            manifest_path=MANIFEST_PATH,
            output_dir=tmp_path,
        )
    assert not runner._canary_marker_path(tmp_path).exists()


def test_runtime_preflight_retains_ubuntu_daemon_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {"ready": True, "checks": {"docker_daemon_provider_matches": True}}
    monkeypatch.setattr(
        runner.ubuntu_runner,
        "collect_runtime_launch_preflight",
        lambda *args, **kwargs: expected,
    )

    assert runner.collect_runtime_launch_preflight(tmp_path) == expected


def test_run_attempt_injects_reviewed_attempt_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    captured: dict[str, object] = {}
    monkeypatch.setattr(runner, "_authorized_output_dir", lambda manifest: tmp_path)
    monkeypatch.setattr(runner, "_ensure_token_budget_remaining", lambda *args, **kwargs: 0)

    def fake_run(manifest, ledger_path, **kwargs):
        captured.update(kwargs)
        return {"status": "failed"}

    monkeypatch.setattr(runner, "_original_run_attempt", fake_run)

    assert runner.run_attempt(manifest, tmp_path / "attempt.jsonl")["status"] == "failed"
    budget = captured["attempt_budget"]
    assert budget.total_wall_clock_seconds == 1_800
    assert budget.cleanup_reserve_seconds == 120
    assert budget.max_compiler_invocations == 2
    assert budget.max_model_requests == 48


def test_batch_uses_original_schedule_orders_in_authorized_sequence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    created: list[tuple[str, str, int]] = []
    ledgers: list[tuple[dict, list[dict]]] = []
    monkeypatch.setattr(runner, "_require_authorized_output_dir", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "_observed_authorized_ledgers", lambda *args, **kwargs: list(ledgers))
    monkeypatch.setattr(runner, "_ensure_token_budget_remaining", lambda *args, **kwargs: 0)

    def fake_create(manifest, *, case_id, condition_id, repetition, **kwargs):
        created.append((case_id, condition_id, repetition))
        return SimpleNamespace(
            path=tmp_path / f"{len(created)}.jsonl",
            physical_attempt_id=f"physical_attempt_{len(created)}",
        ), {"ready": True}

    monkeypatch.setattr(runner, "create_attempt", fake_create)
    monkeypatch.setattr(runner, "run_attempt", lambda *args, **kwargs: {"status": "failed"})

    result = runner.run_formal_batch(
        manifest,
        manifest_path=MANIFEST_PATH,
        output_dir=tmp_path,
        max_attempts=6,
        check_endpoint=False,
    )

    assert result["status"] == "authorized_complete_project_block_reached"
    assert [entry["schedule_order"] for entry in result["results"]] == [1, 2, 73, 74, 153, 154]
    assert created == [(slot["case_id"], slot["condition_id"], slot["repetition"]) for slot in runner._authorized_slots(manifest)]
