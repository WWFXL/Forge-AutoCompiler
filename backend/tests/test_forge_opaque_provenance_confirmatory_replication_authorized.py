"""Issue #247 independent replication authorized amendment 的零 provider 测试。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
PROTOCOL_PATH = SCRIPTS / "forge_opaque_provenance_confirmatory_replication_authorized_protocol.py"
RUNNER_PATH = SCRIPTS / "forge_opaque_provenance_confirmatory_replication_authorized_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-confirmatory-replication-authorized.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-confirmatory-replication-authorized.schema.json"


def _load_module(name: str, path: Path):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_module("forge_confirmatory_replication_authorized_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_confirmatory_replication_authorized_runner_test", RUNNER_PATH)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_manifest_schema_and_runtime_identity_are_frozen() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)

    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.schema_document(manifest)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    protocol.verify_frozen_components(manifest, REPO_ROOT)
    assert protocol.canonical_sha256(manifest) == "784f33442a13df571f93acb97ba987950e11fffa97511fe5bf3f74c9bb75a3d1"


def test_authorized_delta_preserves_independent_replication_boundaries() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    delta = protocol.validate_allowed_delta(manifest, REPO_ROOT)
    execution = manifest["authorized_execution"]

    assert delta == {
        "status": "passed",
        "parent_manifest_sha256": "7b1817becba4ec57eb9726be0e1faaa5427af309dca7552634e3f6a3a1b5d938",
        "schedule_identity_sha256": "3f35dd8c245cb7e9db6069f63cf133c98fbfdf6813a11e3fa2306a5eb34c2134",
        "evidence_identity_sha256": "b136cc5669384176853f00b878dae207d89b7bce593cc8e5f1ff9ab06505b9bc",
        "verifier_relaxation": False,
        "historical_outcomes_imported": False,
        "v1_attempt_extended": False,
    }
    assert manifest["authorization"]["model_tokens_authorized"] == 2_940_000
    assert all(value is True for key, value in manifest["authorization"].items() if key.endswith("_authorized") and key != "model_tokens_authorized")
    assert execution["provider"] == {
        "status": "active_authorized",
        "id": "deepseek-v4-flash",
        "endpoint": "https://api.deepseek.com",
        "credential_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-v4-flash",
        "request_timeout_seconds": 300,
        "max_retries": 0,
        "fallback": "forbidden",
        "streaming": False,
    }
    assert execution["budget"]["batch_maximum_recorded_tokens"] == 2_940_000
    assert execution["relationship_to_v1"]["historical_outcomes_imported"] is False
    assert execution["relationship_to_v1"]["gpac_v1_attempt_resumed"] is False
    assert execution["analysis"]["model_ranking_performed"] is False


def test_runtime_validation_binds_repair_adapter_without_provider_work() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    result = runner.validate_runtime(manifest, REPO_ROOT)

    assert result == {
        "status": "valid",
        "manifest_sha256": "784f33442a13df571f93acb97ba987950e11fffa97511fe5bf3f74c9bb75a3d1",
        "evidence_identity_sha256": "b136cc5669384176853f00b878dae207d89b7bce593cc8e5f1ff9ab06505b9bc",
        "schedule_identity_sha256": "3f35dd8c245cb7e9db6069f63cf133c98fbfdf6813a11e3fa2306a5eb34c2134",
        "pair_executor_adapter": "scripts/forge_opaque_provenance_confirmatory_execution_repair_adapter.py",
        "pair_count": 12,
        "case_count": 6,
        "build_systems": ["cmake", "make"],
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
    }


def test_protocol_binding_restores_base_module_after_failure() -> None:
    original = runner.base.protocol

    with pytest.raises(RuntimeError, match="injected"):
        with runner._protocol_binding():
            assert runner.base.protocol is runner.protocol
            raise RuntimeError("injected")

    assert runner.base.protocol is original


def test_batch_forces_repair_executor_and_restores_protocol(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    original = runner.base.protocol
    captured: dict[str, object] = {}
    monkeypatch.setattr(runner, "validate_runtime", lambda *_args: {"status": "valid"})

    def fake_run_batch(_manifest, **kwargs):
        captured.update(kwargs)
        assert runner.base.protocol is runner.protocol
        return {"status": "completed"}

    monkeypatch.setattr(runner.base, "run_batch", fake_run_batch)
    result = runner.run_batch(manifest, output_dir=tmp_path, repo_root=REPO_ROOT)

    assert result == {"status": "completed"}
    assert captured == {
        "output_dir": tmp_path,
        "repo_root": REPO_ROOT,
        "pair_executor": runner.repair.execute_real_pair,
    }
    assert runner.base.protocol is original


def test_preflight_delegates_without_writing_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    output_dir = tmp_path / "absent-evidence"
    monkeypatch.setattr(runner, "validate_runtime", lambda *_args: {"status": "valid"})

    def fake_preflight(_manifest, **kwargs):
        assert runner.base.protocol is runner.protocol
        assert not output_dir.exists()
        return {"ready": True, "provider_calls": 0, "model_tokens": 0}

    monkeypatch.setattr(runner.base, "collect_preflight", fake_preflight)
    result = runner.collect_preflight(
        manifest,
        output_dir=output_dir,
        repo_root=tmp_path,
        require_empty=True,
    )

    assert result == {"ready": True, "provider_calls": 0, "model_tokens": 0}
    assert not output_dir.exists()


def test_schema_and_protocol_reject_authorization_drift() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    drifted = copy.deepcopy(manifest)
    drifted["authorized_execution"]["provider"]["max_retries"] = 1

    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(drifted)
    with pytest.raises(protocol.ProtocolError):
        protocol.validate_manifest(drifted, REPO_ROOT)


def test_runner_contains_no_checkpoint_copy_or_credential_value() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "pair_executor=repair.execute_real_pair" in source
    assert "base.run_batch(" in source
    for forbidden in (
        ".RealLifecycleCheckpointGate(",
        ".capture(",
        ".provision_arm(",
        "sk-",
        "api_key=",
        "os.environ[",
        "OPENAI_AK",
    ):
        assert forbidden not in source
