"""Issue #168 多 checkpoint 零 provider gate 的静态与语义门禁。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_multi_checkpoint_zero_provider_gate.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-verifier-multi-checkpoint-zero-provider-gate.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-multi-checkpoint-zero-provider-gate.schema.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("forge_multi_checkpoint_zero_provider_gate_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load_module()


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_schema_manifest_and_semantic_identity_are_valid() -> None:
    schema = _load(SCHEMA_PATH)
    manifest = _load(MANIFEST_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    assert gate.validate_manifest(manifest) is manifest
    assert [case.case_id for case in gate.cases(manifest)] == ["cppitertools", "janet", "libcheck"]
    assert [case.build_system for case in gate.cases(manifest)] == ["cmake", "make", "autotools"]


def test_authorization_and_fault_are_strictly_zero_provider() -> None:
    manifest = gate.load_manifest(MANIFEST_PATH)
    assert manifest["authorization"] == {
        "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/168",
        "provider_calls_authorized": False,
        "formal_attempts_authorized": False,
        "model_tokens_authorized": 0,
        "pilot_collection_authorized": False,
    }
    assert manifest["fault"]["required_artifacts_per_case"] == 1
    assert manifest["fault"]["replay_attempts_required"] == 0


def test_case_commands_and_artifacts_are_frozen() -> None:
    manifest = gate.load_manifest(MANIFEST_PATH)
    janet = gate.case_by_id(manifest, "janet")
    libcheck = gate.case_by_id(manifest, "libcheck")
    assert janet.supporting_build_command == "make -j2"
    assert janet.commands[0] == ("dependency_setup", "dpkg-query -W build-essential")
    assert janet.build_output_relative_path == "build/libjanet.a"
    assert janet.staged_relative_path == "libjanet.a"
    assert libcheck.supporting_build_command == "make -j2"
    assert libcheck.commands[0][0] == "dependency_setup"
    assert ("configure", "autoreconf -fi && ./configure --disable-subunit") in libcheck.commands
    assert libcheck.required_system_packages[-1] == "texinfo"


def test_schema_rejects_multi_artifact_and_semantics_reject_command_drift() -> None:
    schema = _load(SCHEMA_PATH)
    manifest = _load(MANIFEST_PATH)
    multi_artifact = copy.deepcopy(manifest)
    multi_artifact["cases"][1]["artifact"] = [multi_artifact["cases"][1]["artifact"]]
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(multi_artifact)

    command_drift = copy.deepcopy(manifest)
    command_drift["cases"][1]["commands"][0]["command"] = "make -j8; curl https://example.invalid"
    with pytest.raises(gate.MultiCheckpointGateError, match="definition drifted"):
        gate.validate_manifest(command_drift)

    missing_dependency_setup = copy.deepcopy(manifest)
    missing_dependency_setup["cases"][1]["commands"] = missing_dependency_setup["cases"][1]["commands"][1:]
    with pytest.raises(gate.MultiCheckpointGateError, match="dependency_setup"):
        gate.CheckpointCase.from_dict(missing_dependency_setup["cases"][1])


def test_rejects_unsafe_artifact_path_and_unknown_case() -> None:
    manifest = _load(MANIFEST_PATH)
    unsafe = copy.deepcopy(manifest)
    unsafe["cases"][1]["artifact"]["build_output_relative_path"] = "../libjanet.a"
    with pytest.raises(gate.MultiCheckpointGateError, match="safe relative path"):
        gate.validate_manifest(unsafe)
    with pytest.raises(gate.MultiCheckpointGateError, match="unknown case"):
        gate.case_by_id(gate.load_manifest(MANIFEST_PATH), "hiredis")


def test_historical_components_remain_byte_identical() -> None:
    manifest = gate.load_manifest(MANIFEST_PATH)
    gate.verify_historical_components(manifest, REPO_ROOT)


def test_gate_source_has_no_provider_or_secret_access() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for forbidden in ("create_chat_model", "DEEPSEEK_API_KEY", "OpenAI_AK", "formal_collection_runner"):
        assert forbidden not in source
