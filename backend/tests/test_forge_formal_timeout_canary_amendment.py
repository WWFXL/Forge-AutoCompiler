from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "scripts" / "forge_formal_timeout_calibration_canary_amendment_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts" / "forge_formal_timeout_calibration_canary_amendment_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-timeout-canary-amendment.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-timeout-canary-amendment.schema.json"
PARENT_FILES = {
    "benchmarks/manifests/cpp-formal-timeout-calibration.json": "e38a3adc19f1f3a988d2beb915a46ffa5c6f4953",
    "benchmarks/schemas/forge-cpp-formal-timeout-calibration.schema.json": "6c61cebcc3c0cd9781d8cc4ff63cf9e8a9d9249f",
    "scripts/forge_formal_timeout_calibration_protocol.py": "4bcd26cd03a51fad22d9416545477ec2c709c2aa",
    "scripts/forge_formal_timeout_calibration_runner.py": "a723abdf3f3319a4ed875a8f07e45ff35e7aad56",
    "scripts/forge_formal_timeout_calibration_report.py": "2ff0b44e82750d3546bed4590109f2c8a806aa43",
}
SUPERSEDED_MARKER_BYTES = b"""{
  "benchmark_id": "forge-cpp-formal-timeout-calibration",
  "document_type": "formal_provider_canary_attempt",
  "error_class": "RunnerError",
  "manifest_sha256": "aeb1e66b85da53dbbe91c33059825d092143a4c0fa0b3045c327524767c9b10b",
  "schema_version": "formal-provider-canary-attempt-1.0.0",
  "status": "failed",
  "updated_at": "2026-08-13T16:32:31.076123+00:00"
}
"""


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


protocol = _load_module("forge_formal_timeout_canary_amendment_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_formal_timeout_canary_amendment_runner_test", RUNNER_PATH)


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_is_deterministic_schema_valid_and_single_variable() -> None:
    manifest = load_manifest()

    assert protocol.validate_manifest(manifest) == manifest
    assert protocol.generate_manifest() == manifest
    assert manifest["schema_version"] == "formal-collection-4.6.0-timeout-canary-amendment"
    assert manifest["authorization"]["issue_url"].endswith("/issues/119")
    assert manifest["authorization"]["new_canary"] == {
        "maximum_attempts": 1,
        "anonymous_models_endpoint_preflight": "forbidden",
        "authenticated_provider_request_required": True,
        "success_required_before_first_ledger": True,
    }
    assert manifest["authorization"]["collection_constraints"]["authorized_schedule_orders"] == [1, 2]
    assert {(profile["request_timeout_seconds"], profile["max_retries"]) for profile in manifest["model_profiles"].values()} == {(300, 0)}

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(manifest, schema)


def test_parent_calibration_files_remain_byte_identical() -> None:
    for relative_path, expected_git_blob in PARENT_FILES.items():
        payload = (REPO_ROOT / relative_path).read_bytes()
        header = f"blob {len(payload)}\0".encode()
        assert hashlib.sha1(header + payload).hexdigest() == expected_git_blob


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["authorization"]["new_canary"].update(maximum_attempts=2),
        lambda value: value["authorization"]["new_canary"].update(anonymous_models_endpoint_preflight="required"),
        lambda value: value["authorization"]["superseded_canary_terminal"].update(status="passed"),
        lambda value: value["model_profiles"]["richlab-gpt-5.5"].update(request_timeout_seconds=120),
        lambda value: value["authorization"]["collection_constraints"].update(authorized_schedule_orders=[1]),
    ],
)
def test_manifest_rejects_canary_timeout_or_scope_drift(mutation) -> None:
    manifest = copy.deepcopy(load_manifest())
    mutation(manifest)

    with pytest.raises(protocol.BenchmarkError):
        protocol.validate_manifest(manifest)


def test_superseded_terminal_requires_exact_marker_and_empty_layer(
    tmp_path: Path,
) -> None:
    manifest = load_manifest()
    frozen = manifest["authorization"]["superseded_canary_terminal"]
    marker_path = tmp_path / frozen["marker_relative_path"]
    marker_path.parent.mkdir(parents=True)
    assert hashlib.sha256(SUPERSEDED_MARKER_BYTES).hexdigest() == frozen["marker_sha256"]
    marker_path.write_bytes(SUPERSEDED_MARKER_BYTES)

    result = runner._verify_superseded_canary_terminal(manifest, output_dir=tmp_path)

    assert result == {
        "status": "failed",
        "provider_report_count": 0,
        "formal_ledger_count": 0,
    }
    (tmp_path / "unexpected.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(runner.RunnerError, match="evidence layer changed"):
        runner._verify_superseded_canary_terminal(manifest, output_dir=tmp_path)


def test_canary_skips_anonymous_endpoint_preflight_and_restores_hook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = load_manifest()
    monkeypatch.setattr(
        runner,
        "_verify_superseded_canary_terminal",
        lambda *args, **kwargs: {"status": "failed"},
    )
    original = runner._base_runner.collect_preflight
    captured: dict[str, object] = {}

    def collect(*args, **kwargs):
        captured["patched"] = runner._base_runner.collect_preflight is not original
        result = runner._base_runner.collect_preflight("manifest", check_endpoint=True)
        captured["result"] = result
        return {"passed": True}

    monkeypatch.setattr(
        runner,
        "_original_collect_preflight",
        lambda *args, **kwargs: kwargs["check_endpoint"],
    )
    monkeypatch.setattr(runner, "_original_collect_provider_canary", collect)

    assert runner.collect_provider_canary(manifest, manifest_path=MANIFEST_PATH, output_dir=tmp_path)["passed"] is True
    assert captured == {"patched": True, "result": False}
    assert runner._base_runner.collect_preflight is original


def test_create_attempt_and_batch_force_endpoint_check_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = load_manifest()
    monkeypatch.setattr(
        runner,
        "_verify_superseded_canary_terminal",
        lambda *args, **kwargs: {"status": "failed"},
    )
    captured: list[bool] = []
    monkeypatch.setattr(
        runner,
        "_original_create_attempt",
        lambda _manifest, **kwargs: captured.append(kwargs["check_endpoint"]) or "ledger",
    )

    assert (
        runner.create_attempt(
            manifest,
            case_id="cppitertools",
            condition_id="richlab-gpt-5.5",
            repetition=1,
            output_dir=tmp_path,
        )
        == "ledger"
    )
    assert captured == [False]

    batch: dict[str, object] = {}
    monkeypatch.setattr(
        runner,
        "_original_run_timeout_calibration_batch",
        lambda *args, **kwargs: batch.update(kwargs) or {"status": "timeout_calibration_complete"},
    )
    result = runner.run_timeout_canary_amendment_batch(
        manifest,
        manifest_path=MANIFEST_PATH,
        output_dir=tmp_path,
        max_attempts=2,
    )
    assert result["status"] == "timeout_calibration_complete"
    assert batch["check_endpoint"] is False
