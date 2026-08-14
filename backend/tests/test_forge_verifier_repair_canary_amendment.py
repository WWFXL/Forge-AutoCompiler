from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "scripts" / "forge_verifier_repair_canary_amendment_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts" / "forge_verifier_repair_canary_amendment_runner.py"
REPORT_PATH = REPO_ROOT / "scripts" / "forge_verifier_repair_canary_amendment_report.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-repair-pilot-canary-amendment.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-verifier-repair-pilot-canary-amendment-v1.schema.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_module("forge_verifier_repair_canary_amendment_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_verifier_repair_canary_amendment_runner_test", RUNNER_PATH)
report = _load_module("forge_verifier_repair_canary_amendment_report_test", REPORT_PATH)


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _write_json(path: Path, value: dict) -> bytes:
    raw = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def test_manifest_is_deterministic_schema_valid_and_preserves_study() -> None:
    manifest = _manifest()
    parent = protocol._parent_manifest()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert protocol.validate_manifest(manifest) == manifest
    assert protocol.generate_manifest() == manifest
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(manifest, schema)
    assert manifest["schema_version"] == "verifier-driven-repair-pilot-canary-amendment-1.0.0"
    assert manifest["authorization"]["issue_url"].endswith("/131")
    assert manifest["authorization"]["new_canary"] == {
        "maximum_attempts": 1,
        "authenticated_requests_per_provider": 1,
        "request_timeout_seconds": 300,
        "max_retries": 0,
        "success_required_before_first_ledger": True,
    }
    for key in ("model_profiles", "conditions", "collection_plan", "cases", "repair_packet", "fidelity_gate", "outcomes", "analysis_plan"):
        assert manifest[key] == parent[key]
    assert manifest["authorization"]["budget_confirmation"] == parent["authorization"]["budget_confirmation"]


def test_parent_identity_and_files_remain_frozen() -> None:
    parent = protocol._parent_manifest()
    assert protocol.parent_protocol.manifest_sha256(parent) == protocol.PARENT_CANONICAL_SHA256
    assert protocol.SUPERSEDED_CANARY_TERMINAL["marker_sha256"] == "1a2b7bc7547e30ef56b1340420e435bd44b2f56df5e025a90653f5f88a39bcd7"
    assert protocol.SUPERSEDED_CANARY_TERMINAL["provider_report_sha256"] == "a8cc041ba4213a9f35169e4c48273c4ba4911e84e467c7f55fd5143bff2283a5"


def test_superseded_canary_requires_exact_marker_report_and_zero_ledgers(tmp_path: Path) -> None:
    manifest = copy.deepcopy(_manifest())
    frozen = manifest["authorization"]["superseded_canary_terminal"]
    marker = {
        "benchmark_id": frozen["benchmark_id"],
        "manifest_sha256": frozen["manifest_sha256"],
        "status": "failed",
        "error_class": None,
    }
    provider_report = {
        "benchmark_id": frozen["benchmark_id"],
        "manifest_sha256": frozen["manifest_sha256"],
        "passed": False,
    }
    marker_raw = _write_json(tmp_path / frozen["marker_relative_path"], marker)
    report_path = tmp_path / frozen["provider_report_relative_path"]
    report_raw = _write_json(report_path, provider_report)
    frozen["marker_sha256"] = hashlib.sha256(marker_raw).hexdigest()
    frozen["provider_report_sha256"] = hashlib.sha256(report_raw).hexdigest()

    assert runner._verify_superseded_canary_terminal(manifest, output_dir=tmp_path) == {
        "status": "failed",
        "provider_report_count": 1,
        "formal_ledger_count": 0,
    }
    report_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(runner.RunnerError, match="report changed"):
        runner._verify_superseded_canary_terminal(manifest, output_dir=tmp_path)


def test_canary_verifies_superseded_layer_before_delegating(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest = _manifest()
    calls: list[str] = []
    monkeypatch.setattr(runner, "_verify_superseded_canary_terminal", lambda *_args, **_kwargs: calls.append("verify"))
    monkeypatch.setattr(runner, "_original_collect_provider_canary", lambda *_args, **_kwargs: calls.append("canary") or {"passed": True})

    assert runner.collect_provider_canary(manifest, manifest_path=MANIFEST_PATH, output_dir=tmp_path) == {"passed": True}
    assert calls == ["verify", "canary"]


def test_report_adapter_uses_amendment_identity() -> None:
    manifest = _manifest()
    assert report._parent.protocol.SCHEMA_VERSION == protocol.SCHEMA_VERSION
    assert report._parent.protocol.DEFAULT_MANIFEST == protocol.DEFAULT_MANIFEST
    assert report._parent.DEFAULT_EVIDENCE_DIR == Path(protocol.EVIDENCE_DIRECTORY)
    assert report._parent.load_manifest(MANIFEST_PATH) == manifest
