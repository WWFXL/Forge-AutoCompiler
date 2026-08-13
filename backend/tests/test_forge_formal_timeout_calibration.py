from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "scripts" / "forge_formal_timeout_calibration_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts" / "forge_formal_timeout_calibration_runner.py"
REPORT_PATH = REPO_ROOT / "scripts" / "forge_formal_timeout_calibration_report.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-timeout-calibration.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-timeout-calibration.schema.json"
PARENT_FILES = {
    "benchmarks/manifests/cpp-formal-v4-canary-amendment.json": "74a4133bad3b9b0566c3248aaed3ce58f1afb95c",
    "benchmarks/schemas/forge-cpp-formal-collection-v4-canary-amendment.schema.json": "5006c922e6043913c5aa9111bdb1ec46b04aad2f",
    "scripts/forge_formal_collection_v4_canary_amendment_protocol.py": "0aa5ba6345a1b92e81ba65419360e7e422a001d2",
    "scripts/forge_formal_collection_v4_canary_amendment_runner.py": "4da71f20537b1d2318141222546174c03881422a",
    "scripts/forge_formal_collection_v4_canary_amendment_report.py": "cf34697e796fedd15df170f8415d910f9db3b45f",
}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


protocol = _load_module("forge_formal_timeout_calibration_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_formal_timeout_calibration_runner_test", RUNNER_PATH)
report = _load_module("forge_formal_timeout_calibration_report_test", REPORT_PATH)


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_is_deterministic_schema_valid_and_single_variable() -> None:
    manifest = load_manifest()

    assert protocol.validate_manifest(manifest) == manifest
    assert protocol.generate_manifest() == manifest
    assert manifest["schema_version"] == "formal-collection-4.5.0-timeout-calibration"
    assert manifest["scope"]["formal_comparison_enabled"] is False
    assert manifest["authorization"]["issue_url"].endswith("/issues/117")
    assert manifest["authorization"]["collection_constraints"]["authorized_schedule_orders"] == [1, 2]
    assert manifest["authorization"]["collection_constraints"]["formal_primary_pooling_forbidden"] is True
    assert {(profile["request_timeout_seconds"], profile["max_retries"]) for profile in manifest["model_profiles"].values()} == {(300, 0)}

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(manifest, schema)


def test_calibration_uses_one_attempt_per_provider() -> None:
    slots = runner._authorized_slots(load_manifest())

    assert [slot["order"] for slot in slots] == [1, 2]
    assert [(slot["condition_id"], slot["repetition"]) for slot in slots] == [
        ("richlab-gpt-5.5", 1),
        ("deepseek-v4-flash", 1),
    ]


def test_parent_protocol_files_remain_byte_identical() -> None:
    for relative_path, expected_git_blob in PARENT_FILES.items():
        payload = (REPO_ROOT / relative_path).read_bytes()
        header = f"blob {len(payload)}\0".encode()
        assert hashlib.sha1(header + payload).hexdigest() == expected_git_blob


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["model_profiles"]["richlab-gpt-5.5"].update(request_timeout_seconds=120),
        lambda value: value["model_profiles"]["deepseek-v4-flash"].update(max_retries=1),
        lambda value: value["scope"].update(formal_comparison_enabled=True),
        lambda value: value["authorization"]["collection_constraints"].update(authorized_schedule_orders=[1]),
        lambda value: value["authorization"]["collection_constraints"].update(formal_primary_pooling_forbidden=False),
    ],
)
def test_manifest_rejects_timeout_retry_or_scope_drift(mutation) -> None:
    manifest = copy.deepcopy(load_manifest())
    mutation(manifest)

    with pytest.raises(protocol.BenchmarkError):
        protocol.validate_manifest(manifest)


def test_batch_is_bounded_to_two_attempts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    captured: dict[str, object] = {}

    def run_parent(*args, **kwargs):
        captured.update(kwargs)
        return {
            "status": "authorized_complete_project_block_reached",
            "next_authorized_index": 2,
        }

    monkeypatch.setattr(runner._runner, "run_formal_batch", run_parent)
    result = runner.run_timeout_calibration_batch(
        manifest,
        manifest_path=MANIFEST_PATH,
        output_dir=tmp_path,
        max_attempts=2,
        check_endpoint=False,
    )

    assert result["status"] == "timeout_calibration_complete"
    assert captured["max_attempts"] == 2
    with pytest.raises(runner.RunnerError, match="at most two"):
        runner.run_timeout_calibration_batch(
            manifest,
            manifest_path=MANIFEST_PATH,
            output_dir=tmp_path,
            max_attempts=3,
        )


def test_build_policy_keeps_300_seconds_and_zero_retries() -> None:
    manifest = load_manifest()
    policy = runner.build_policy(
        manifest,
        case_id="cppitertools",
        condition_id="richlab-gpt-5.5",
        repetition=1,
    )

    assert policy.request_timeout_seconds == 300
    assert policy.model_max_retries == 0


def test_run_attempt_preserves_existing_attempt_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest()
    captured: dict[str, object] = {}
    monkeypatch.setattr(runner._runner, "_authorized_output_dir", lambda _manifest: tmp_path)
    monkeypatch.setattr(runner._runner, "_ensure_token_budget_remaining", lambda *args, **kwargs: 0)

    def fake_run(_manifest, _ledger_path, **kwargs):
        captured.update(kwargs)
        return {"status": "failed"}

    monkeypatch.setattr(runner._runner, "_original_run_attempt", fake_run)
    runner.run_attempt(manifest, tmp_path / "attempt.jsonl")

    budget = captured["attempt_budget"]
    assert budget.total_wall_clock_seconds == 1_800
    assert budget.max_compiler_invocations == 2
    assert budget.max_model_requests == 48


def test_report_forbids_primary_pooling(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    synthetic = {
        "report_version": "parent",
        "scope": {
            "formal_comparison_enabled": True,
            "paired_primary_eligible": True,
            "descriptive_only": False,
        },
        "collection": {"stop_reason": "authorized_complete_project_block_reached"},
        "interpretation": {},
        "limitations": [],
    }
    monkeypatch.setattr(report.parent_report, "build_report", lambda *args, **kwargs: synthetic)

    result = report.build_report(load_manifest(), tmp_path)

    assert result["scope"] == {
        "formal_comparison_enabled": False,
        "paired_primary_eligible": False,
        "descriptive_only": True,
    }
    assert result["collection"]["stop_reason"] == "timeout_calibration_complete"
    assert result["interpretation"]["request_timeout_seconds"] == 300
    assert result["interpretation"]["provider_retries"] == 0
    assert result["interpretation"]["formal_primary_pooling_forbidden"] is True
