"""Issue #214 R3 Make jobs lifecycle 静态合同。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _load_gate():
    module_name = "forge_opaque_provenance_r3_make_lifecycle_gate_contract"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS_DIR / "forge_opaque_provenance_r3_make_lifecycle_gate.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))
    return module


gate = _load_gate()


def test_r3_make_lifecycle_contract_accepts_both_jobs_profiles() -> None:
    result = gate.validate_gate_contract()

    assert result["schema_version"] == gate.SCHEMA_VERSION
    assert [item["profile"]["profile_id"] for item in result["profiles"]] == ["jobs-omitted", "jobs-1"]
    assert all(item["parent"]["status"] == "unproven" for item in result["profiles"])
    assert all(item["treatment"]["status"] == "proven" for item in result["profiles"])
    assert all(item["treatment"]["proof_mode"] == "direct_make" for item in result["profiles"])
    assert all(item["parent_history_prefix_preserved"] is True for item in result["profiles"])
    assert result["provider_calls"] == 0
    assert result["credential_read"] is False
    assert result["formal_attempts"] == 0
    assert result["model_tokens"] == 0
    assert result["evidence_writes"] == 0


@pytest.mark.parametrize(
    ("profile_id", "command"),
    (("jobs-omitted", "make libhoedown.a"), ("jobs-1", "make -j1 libhoedown.a")),
)
def test_docker_adapter_exposes_only_the_selected_build_profile(profile_id: str, command: str) -> None:
    adapter = gate.build_docker_adapter(profile_id)
    assert adapter.TREATMENT_BUILD_COMMAND == command
    assert adapter.TREATMENT_STAGE_COMMAND == "cp libhoedown.a /artifacts/libhoedown.a"
    assert adapter.build_repair_packet() == gate.lifecycle.build_repair_packet()


def test_unknown_jobs_profile_is_rejected() -> None:
    with pytest.raises(gate.R3MakeLifecycleGateError, match="未知 R3 Make jobs profile"):
        gate.build_docker_adapter("jobs-unbounded")
