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
PROTOCOL_PATH = REPO_ROOT / "scripts" / "forge_formal_collection_v4_canary_amendment_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts" / "forge_formal_collection_v4_canary_amendment_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-v4-canary-amendment.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-collection-v4-canary-amendment.schema.json"
PARENT_FILES = {
    "scripts/forge_formal_collection_v4_authorized_protocol.py": "5adb07e261e14cbd3831e8d58a08d83a1efe97b80b4d9acf499fadd6acd74574",
    "scripts/forge_formal_collection_v4_authorized_runner.py": "96181cbb03a5e660cccf7cc8bfa8a0bfb5d25fa07633eafec71095df611aa15d",
    "scripts/forge_formal_collection_v4_authorized_report.py": "2fc3b3efe325c3f3bd4dea61b7775c91a3cf1144ee978c2b5524130a6ef58641",
    "benchmarks/manifests/cpp-formal-v4-authorized-initial-block.json": "5f4b2b6af6aac80d43591073f51f9524a71b9c9191deab48c6872dbb731e4ef6",
    "benchmarks/schemas/forge-cpp-formal-collection-v4-authorized.schema.json": "12f8610792f81ce19106fda5a1e602e391487b274bfa7bfabeb02b3942d5c20a",
    "benchmarks/preregistrations/cpp-formal-v4-authorized-initial-block.md": "7d77fd41f0df1692c79808bc8dfe13a0267fb89f7238f0ed3cfbe7152b7344f1",
}
LEGACY_MARKER_BYTES = b"""{
  "benchmark_id": "forge-cpp-formal-v4-authorized-initial-block",
  "document_type": "formal_provider_canary_attempt",
  "error_class": "RunnerError",
  "manifest_sha256": "8f05820d97054d16cc0cf1ee5646089ccf8f5c9c56108f2781ec45a70c7ccf03",
  "schema_version": "formal-provider-canary-attempt-1.0.0",
  "status": "failed",
  "updated_at": "2026-08-12T15:45:00.601026+00:00"
}
"""


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


protocol = _load_module(
    "forge_formal_collection_v4_canary_amendment_protocol_test",
    PROTOCOL_PATH,
)
runner = _load_module(
    "forge_formal_collection_v4_canary_amendment_runner_test",
    RUNNER_PATH,
)


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_is_deterministic_schema_valid_and_bounded() -> None:
    manifest = load_manifest()

    assert protocol.validate_manifest(manifest) == manifest
    assert protocol.generate_manifest() == manifest
    assert manifest["schema_version"] == "formal-collection-4.4.0-canary-amendment"
    assert manifest["forge"]["commit_sha"] == "efc640fedbc4da2e00d553fd37adaa693e8abaa2"
    assert manifest["authorization"]["issue_url"].endswith("/issues/115")
    assert manifest["authorization"]["network_observation"]["access_medium"] == "mobile_hotspot"
    assert manifest["authorization"]["diagnostics"]["maximum_attempts_per_provider"] == 2
    assert manifest["authorization"]["new_canary"]["maximum_attempts"] == 1
    assert manifest["authorization"]["budget_confirmation"]["maximum_recorded_tokens"] == 980_000
    assert manifest["authorization"]["collection_constraints"]["authorized_schedule_orders"] == [1, 2, 73, 74, 153, 154]
    assert manifest["authorization"]["superseded_canary_terminal"]["manifest_sha256"] == ("8f05820d97054d16cc0cf1ee5646089ccf8f5c9c56108f2781ec45a70c7ccf03")

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(manifest, schema)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["authorization"]["diagnostics"].update(maximum_attempts_per_provider=3),
        lambda value: value["authorization"]["diagnostics"].update(response_body_storage_forbidden=False),
        lambda value: value["authorization"]["diagnostics"].update(stop_conditions=["all_providers_terminal"]),
        lambda value: value["authorization"]["new_canary"].update(maximum_attempts=2),
        lambda value: value["authorization"]["new_canary"].update(anonymous_models_endpoint_preflight="required"),
        lambda value: value["authorization"]["superseded_canary_terminal"].update(status="passed"),
        lambda value: value["authorization"]["collection_constraints"].update(authorized_schedule_orders=[1, 2]),
        lambda value: value["authorization"]["budget_confirmation"].update(maximum_recorded_tokens=980_001),
    ],
)
def test_manifest_rejects_diagnostic_canary_or_collection_drift(mutation) -> None:
    manifest = copy.deepcopy(load_manifest())
    mutation(manifest)

    with pytest.raises(protocol.BenchmarkError):
        protocol.validate_manifest(manifest)


def test_parent_authorized_files_remain_byte_identical() -> None:
    for relative_path, expected in PARENT_FILES.items():
        assert hashlib.sha256((REPO_ROOT / relative_path).read_bytes()).hexdigest() == expected


def test_legacy_terminal_requires_exact_marker_and_empty_layer(tmp_path: Path) -> None:
    manifest = load_manifest()
    marker_path = tmp_path / "provider-canaries" / "formal-v4-provider-canary-attempt.json"
    marker_path.parent.mkdir(parents=True)
    assert hashlib.sha256(LEGACY_MARKER_BYTES).hexdigest() == ("9ab297d091967c15fae4f90caf18657b25214903b849fa3a695cd749fc19f724")
    marker_path.write_bytes(LEGACY_MARKER_BYTES)

    result = runner._verify_legacy_terminal(manifest, legacy_output_dir=tmp_path)

    assert result["status"] == "failed"
    assert result["provider_report_count"] == 0
    assert result["formal_ledger_count"] == 0

    (marker_path.parent / "unexpected.json").write_text("{}", encoding="utf-8")
    with pytest.raises(runner.RunnerError, match="no longer empty"):
        runner._verify_legacy_terminal(manifest, legacy_output_dir=tmp_path)


def _patch_diagnostic_gates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(runner, "_diagnostic_output_dir", lambda _manifest: tmp_path)
    monkeypatch.setattr(runner, "_verify_legacy_terminal", lambda *args, **kwargs: {"status": "failed"})
    monkeypatch.setattr(runner, "_formal_container_ids", lambda: [])
    monkeypatch.setattr(runner._runner, "_running_inside_compose_dood", lambda _repo_root: True)
    monkeypatch.setattr(runner, "_original_collect_preflight", lambda *args, **kwargs: {"ready": True})
    monkeypatch.setattr(runner, "_diagnostic_model_config_matches", lambda *args, **kwargs: True)


def test_diagnostics_retry_only_after_failure_and_stop_after_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    _patch_diagnostic_gates(monkeypatch, tmp_path)
    issued: list[str] = []

    def issue(model_name: str, _prompt: str, max_output_tokens: int) -> bool:
        issued.append(model_name)
        assert max_output_tokens == 32
        if model_name == "gpt-5.5" and issued.count(model_name) == 1:
            raise TimeoutError
        return True

    summary = runner.collect_endpoint_diagnostics(
        manifest,
        manifest_path=MANIFEST_PATH,
        output_dir=tmp_path,
        request_issuer=issue,
    )

    assert summary["passed"] is True
    assert issued == ["gpt-5.5", "gpt-5.5", "deepseek-v4-flash"]
    attempts = sorted((tmp_path / "attempts").glob("*.json"))
    assert len(attempts) == 6
    assert all(set(json.loads(path.read_text(encoding="utf-8"))) == runner._DIAGNOSTIC_ATTEMPT_KEYS for path in attempts)
    assert all("DIAGNOSTIC_OK" not in path.read_text(encoding="utf-8") for path in attempts)

    second = runner.collect_endpoint_diagnostics(
        manifest,
        manifest_path=MANIFEST_PATH,
        output_dir=tmp_path,
        request_issuer=lambda *_args: pytest.fail("terminal diagnostics must not issue another request"),
    )
    assert second == summary


def test_started_diagnostic_reservation_consumes_an_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    _patch_diagnostic_gates(monkeypatch, tmp_path)
    provider = manifest["authorization"]["diagnostics"]["providers"][0]
    path = runner._diagnostic_attempt_path(
        tmp_path,
        condition_id=provider["condition_id"],
        attempt=1,
    )
    runner._write_json_exclusive(
        path,
        {
            "schema_version": "formal-endpoint-diagnostic-attempt-1.0.0",
            "document_type": "formal_endpoint_diagnostic_attempt",
            "benchmark_id": manifest["benchmark"]["id"],
            "manifest_sha256": protocol.manifest_sha256(manifest),
            "condition_id": provider["condition_id"],
            "provider": provider["provider"],
            "model": provider["model"],
            "attempt": 1,
            "status": "started",
            "started_at": "2000-01-01T00:00:00+00:00",
            "completed_at": None,
            "duration_ms": None,
            "response_nonempty": False,
            "error_class": None,
            "passed": False,
        },
    )
    issued: list[str] = []

    summary = runner.collect_endpoint_diagnostics(
        manifest,
        manifest_path=MANIFEST_PATH,
        output_dir=tmp_path,
        request_issuer=lambda model, *_args: issued.append(model) or True,
    )

    assert summary["passed"] is True
    assert issued == ["gpt-5.5", "deepseek-v4-flash"]
    assert [condition["attempt_count"] for condition in summary["conditions"]] == [2, 1]


def test_failed_diagnostics_consume_two_attempts_and_block_canary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    _patch_diagnostic_gates(monkeypatch, tmp_path)

    summary = runner.collect_endpoint_diagnostics(
        manifest,
        manifest_path=MANIFEST_PATH,
        output_dir=tmp_path,
        request_issuer=lambda *_args: False,
    )

    assert summary["passed"] is False
    assert [condition["attempt_count"] for condition in summary["conditions"]] == [2, 2]
    with pytest.raises(runner.RunnerError, match="must pass"):
        runner._load_diagnostic_summary(
            manifest,
            output_dir=tmp_path,
            require_passed=True,
        )


def test_diagnostics_reject_unexpected_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    _patch_diagnostic_gates(monkeypatch, tmp_path)
    (tmp_path / "unexpected.txt").write_text("not evidence", encoding="utf-8")

    with pytest.raises(runner.RunnerError, match="unexpected file"):
        runner.collect_endpoint_diagnostics(
            manifest,
            manifest_path=MANIFEST_PATH,
            output_dir=tmp_path,
            request_issuer=lambda *_args: True,
        )


def test_canary_is_consumed_once_and_skips_anonymous_models_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    monkeypatch.setattr(runner, "_formal_output_dir", lambda _manifest: tmp_path)
    monkeypatch.setattr(runner, "_verify_legacy_terminal", lambda *args, **kwargs: {"status": "failed"})
    monkeypatch.setattr(runner, "_load_diagnostic_summary", lambda *args, **kwargs: {"passed": True})
    monkeypatch.setattr(runner, "_observed_authorized_ledgers", lambda *args, **kwargs: [])
    monkeypatch.setattr(runner, "_formal_container_ids", lambda: [])
    original_preflight = runner._runner.collect_preflight

    def collect(*args, **kwargs):
        assert runner._runner.collect_preflight is not original_preflight
        return {"passed": True}

    monkeypatch.setattr(runner, "_original_collect_provider_canary", collect)

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


def test_orphan_canary_report_blocks_new_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    monkeypatch.setattr(runner, "_formal_output_dir", lambda _manifest: tmp_path)
    monkeypatch.setattr(runner, "_verify_legacy_terminal", lambda *args, **kwargs: {"status": "failed"})
    monkeypatch.setattr(runner, "_load_diagnostic_summary", lambda *args, **kwargs: {"passed": True})
    monkeypatch.setattr(runner, "_observed_authorized_ledgers", lambda *args, **kwargs: [])
    monkeypatch.setattr(runner, "_formal_container_ids", lambda: [])
    directory = tmp_path / "provider-canaries"
    directory.mkdir(parents=True)
    (directory / "orphan.json").write_text("{}", encoding="utf-8")

    with pytest.raises(runner.RunnerError, match="orphan"):
        runner.collect_provider_canary(
            manifest,
            manifest_path=MANIFEST_PATH,
            output_dir=tmp_path,
        )
    assert not runner._canary_marker_path(tmp_path).exists()


def test_create_attempt_requires_successful_new_canary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    slot = runner._authorized_slots(manifest)[0]
    monkeypatch.setattr(runner, "_formal_output_dir", lambda _manifest: tmp_path)
    monkeypatch.setattr(runner, "_verify_legacy_terminal", lambda *args, **kwargs: {"status": "failed"})
    monkeypatch.setattr(runner, "_load_diagnostic_summary", lambda *args, **kwargs: {"passed": True})

    with pytest.raises(runner.RunnerError, match="canary marker"):
        runner.create_attempt(
            manifest,
            case_id=slot["case_id"],
            condition_id=slot["condition_id"],
            repetition=slot["repetition"],
            output_dir=tmp_path,
        )
    assert list(tmp_path.rglob("*.jsonl")) == []


def test_batch_preserves_original_six_slot_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    created: list[tuple[str, str, int, bool]] = []
    monkeypatch.setattr(runner, "_formal_output_dir", lambda _manifest: tmp_path)
    monkeypatch.setattr(runner, "_verify_legacy_terminal", lambda *args, **kwargs: {"status": "failed"})
    monkeypatch.setattr(runner, "_load_diagnostic_summary", lambda *args, **kwargs: {"passed": True})
    monkeypatch.setattr(runner, "_require_successful_canary", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "_observed_authorized_ledgers", lambda *args, **kwargs: [])
    monkeypatch.setattr(runner, "_ensure_token_budget_remaining", lambda *args, **kwargs: 0)

    def create(manifest, *, case_id, condition_id, repetition, check_endpoint, **kwargs):
        created.append((case_id, condition_id, repetition, check_endpoint))
        return SimpleNamespace(
            path=tmp_path / f"{len(created)}.jsonl",
            physical_attempt_id=f"physical_attempt_{len(created)}",
        ), {"ready": True}

    monkeypatch.setattr(runner, "create_attempt", create)
    monkeypatch.setattr(runner, "run_attempt", lambda *args, **kwargs: {"status": "failed"})

    result = runner.run_formal_batch(
        manifest,
        manifest_path=MANIFEST_PATH,
        output_dir=tmp_path,
        max_attempts=6,
    )

    assert [item["schedule_order"] for item in result["results"]] == [1, 2, 73, 74, 153, 154]
    assert all(check_endpoint is False for *_identity, check_endpoint in created)
