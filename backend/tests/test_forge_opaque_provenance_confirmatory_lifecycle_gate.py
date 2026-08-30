"""Issue #232 六 case confirmatory lifecycle adapter 的静态合同。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "forge_opaque_provenance_confirmatory_lifecycle_gate.py"


def _load_gate():
    scripts = str(REPO_ROOT / "scripts")
    sys.path.insert(0, scripts)
    try:
        spec = importlib.util.spec_from_file_location("forge_opaque_provenance_confirmatory_lifecycle_test", SCRIPT_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(scripts)


gate = _load_gate()


def test_six_case_adapters_are_derived_from_frozen_candidate() -> None:
    adapters = gate.build_case_adapters(REPO_ROOT)
    assert [adapter.case_id for adapter in adapters] == ["pupnp", "ada-url", "args", "gpac", "fio", "sql-parser-shared"]
    assert [adapter.build_system for adapter in adapters] == ["cmake", "cmake", "cmake", "make", "make", "make"]
    assert [adapter.artifact_type for adapter in adapters] == ["static_library", "static_library", "executable", "static_library", "executable", "shared_library"]
    assert all(adapter.parent_command.startswith("sh -c ") for adapter in adapters)
    assert all(adapter.treatment_stage_command == f"cp {adapter.stage_source} {adapter.stage_destination}" for adapter in adapters)


@pytest.mark.parametrize("case_id", gate.candidate.CASE_ORDER)
def test_parent_is_single_fault_and_direct_treatment_is_append_only(case_id: str) -> None:
    adapter = gate.build_case_adapter(case_id, REPO_ROOT)
    frozen = gate.build_frozen_identity(
        adapter,
        image_id="sha256:" + "7" * 64,
        physical_attempt_id=f"attempt-static-{case_id}",
        build_tree_sha256="8" * 64 if adapter.build_system == "cmake" else None,
        artifact_size=2048,
        artifact_sha256="9" * 64,
    )
    parent, parent_history = gate.evaluate_parent(adapter, frozen, parent_command_id="parent-wrapper")
    treatment, treatment_history = gate.evaluate_treatment(
        adapter,
        frozen,
        parent_command_id="parent-wrapper",
        treatment_build_command_id="treatment-build",
        treatment_stage_command_id="treatment-stage",
    )
    assert (parent.status, parent.classification, parent.reason) == ("unproven", "opaque_build_provenance", "opaque_wrapper")
    assert (treatment.status, treatment.proof_mode) == ("proven", adapter.expected_proof_mode)
    assert treatment_history[: len(parent_history)] == parent_history


def test_static_gate_closes_external_authorization_and_freezes_image_inputs() -> None:
    report = gate.validate_gate_contract(REPO_ROOT)
    assert len(report["cases"]) == 6
    assert report["candidate_manifest_sha256"] == gate.CANDIDATE_MANIFEST_SHA256
    assert report["candidate_manifest_file_sha256"] == gate.CANDIDATE_MANIFEST_FILE_SHA256
    assert report["compile_dockerfile_sha256"] == gate.COMPILE_DOCKERFILE_SHA256
    assert report["compile_image"] == "autocompiler:gcc13"
    assert report["provider_calls"] == 0
    assert report["credential_read"] is False
    assert report["checkpoint_created"] is False
    assert report["formal_attempts"] == 0
    assert report["model_tokens"] == 0
    assert report["formal_evidence_writes"] == 0


def test_unknown_case_and_invalid_build_tree_identity_fail_closed() -> None:
    with pytest.raises(gate.ConfirmatoryLifecycleGateError):
        gate.build_case_adapter("unknown", REPO_ROOT)
    make_adapter = gate.build_case_adapter("fio", REPO_ROOT)
    with pytest.raises(gate.ConfirmatoryLifecycleGateError):
        gate.build_frozen_identity(
            make_adapter,
            image_id="sha256:" + "1" * 64,
            physical_attempt_id="attempt-invalid-make-tree",
            build_tree_sha256="2" * 64,
            artifact_size=1,
            artifact_sha256="3" * 64,
        )


def test_cli_reports_static_zero_provider_contract(capsys: pytest.CaptureFixture[str]) -> None:
    assert gate.main(["validate"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert len(report["cases"]) == 6
    assert report["provider_calls"] == report["model_tokens"] == 0


def test_new_sources_do_not_contain_provider_or_credential_entrypoints() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    for forbidden in ("openai_ak", "deepseek_api_key", "api_key=", "chatopenai(", "execute-pair", "reachability"):
        assert forbidden not in source
