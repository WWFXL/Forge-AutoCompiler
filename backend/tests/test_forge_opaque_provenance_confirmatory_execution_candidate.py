"""Issue #235 confirmatory execution candidate 的零 provider 合同。"""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"


def _load(name: str, filename: str):
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS))


protocol = _load("forge_confirmatory_execution_candidate_test", "forge_opaque_provenance_confirmatory_execution_candidate_protocol.py")
gate = _load("forge_confirmatory_execution_composition_test", "forge_opaque_provenance_confirmatory_execution_composition_gate.py")


def test_candidate_preserves_parent_and_closes_authorization() -> None:
    manifest = protocol.generate_manifest(REPO_ROOT)
    assert protocol.validate_manifest(manifest, REPO_ROOT) == manifest
    delta = protocol.validate_allowed_delta(manifest, REPO_ROOT)
    assert delta["parent_manifest_sha256"] == protocol.PARENT_MANIFEST_SHA256
    assert delta["schedule_identity_sha256"] == "3f35dd8c245cb7e9db6069f63cf133c98fbfdf6813a11e3fa2306a5eb34c2134"
    assert delta["provider_status"] == "selected_not_authorized"
    assert delta["real_pair_runner_implemented"] is False
    assert all(value is False for key, value in manifest["authorization"].items() if key.endswith("_authorized") and key != "model_tokens_authorized")
    assert manifest["authorization"]["model_tokens_authorized"] == 0


def test_manifest_schema_and_generation_are_deterministic() -> None:
    manifest = json.loads(protocol.DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    schema = json.loads(protocol.DEFAULT_SCHEMA.read_text(encoding="utf-8"))
    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.schema_document(manifest)


def test_six_case_dispatch_accepts_only_frozen_direct_actions() -> None:
    dispatches = gate.build_all_dispatches(REPO_ROOT)
    assert [item.case_id for item in dispatches] == ["pupnp", "ada-url", "args", "gpac", "fio", "sql-parser-shared"]
    assert [item.policy_family for item in dispatches] == ["cmake_runtime_parity_v1"] * 3 + ["r3_make_runtime_parity_v1"] * 3
    assert all((item.build_action, item.stage_action) == ("repair_build", "artifact_stage") for item in dispatches)


def test_endpoint_censoring_continues_without_replacement() -> None:
    manifest = protocol.generate_manifest(REPO_ROOT)
    first, second = manifest["schedule"]["pairs"][:2]
    state = gate.next_batch_state(manifest, [{"pair_id": first["pair_id"], "terminal": "endpoint_censored", "recorded_tokens": 0}])
    assert state == {"status": "ready", "reason": None, "recorded_tokens": 0, "next_pair_id": second["pair_id"]}
    taxonomy = manifest["execution_candidate"]["terminal_taxonomy"]
    assert taxonomy["replacement_forbidden"] is True
    assert taxonomy["backfill_forbidden"] is True


@pytest.mark.parametrize("terminal", ["mechanism_invalid", "identity_invalid", "evidence_invalid", "cleanup_failed", "orphan_detected"])
def test_invalid_mechanism_or_cleanup_stops_batch(terminal: str) -> None:
    manifest = protocol.generate_manifest(REPO_ROOT)
    pair_id = manifest["schedule"]["pairs"][0]["pair_id"]
    state = gate.next_batch_state(manifest, [{"pair_id": pair_id, "terminal": terminal, "recorded_tokens": 100}])
    assert state == {"status": "stopped", "reason": terminal, "recorded_tokens": 100, "next_pair_id": None}


def test_token_ceiling_is_checked_before_next_pair() -> None:
    manifest = protocol.generate_manifest(REPO_ROOT)
    pair_id = manifest["schedule"]["pairs"][0]["pair_id"]
    ceiling = manifest["runtime_contract"]["batch_recorded_token_ceiling"]
    state = gate.next_batch_state(manifest, [{"pair_id": pair_id, "terminal": "valid", "recorded_tokens": ceiling}])
    assert state["status"] == "stopped"
    assert state["reason"] == "token_ceiling_reached"


def test_unrelated_parent_or_authorization_drift_fails_closed() -> None:
    manifest = protocol.generate_manifest(REPO_ROOT)
    for mutation in ("case", "schedule", "authorization"):
        drifted = copy.deepcopy(manifest)
        if mutation == "case":
            drifted["cases"][0]["direct_target"] = "wrong"
        elif mutation == "schedule":
            drifted["schedule"]["pairs"][0]["arm_order"].reverse()
        else:
            drifted["authorization"]["provider_calls_authorized"] = True
        with pytest.raises(protocol.ConfirmatoryExecutionCandidateError):
            protocol.validate_manifest(drifted, REPO_ROOT)


def test_full_fake_agent_composition_gate_has_no_external_effects() -> None:
    report = asyncio.run(gate.validate_composition_gate(REPO_ROOT))
    assert report["status"] == "passed"
    assert len(report["dispatches"]) == len(report["agent_construction"]) == 6
    assert all(item["model_calls"] == 1 and item["provider_calls"] == 0 for item in report["agent_construction"])
    assert report["provider_calls"] == report["formal_attempts"] == report["model_tokens"] == 0
    assert report["credential_read"] is False
    assert report["docker_executed"] is False
    assert report["checkpoint_created"] is False
    assert report["formal_evidence_writes"] == 0


def test_new_sources_do_not_expose_real_execution_or_credentials() -> None:
    sources = "\n".join((SCRIPTS / name).read_text(encoding="utf-8").lower() for name in ("forge_opaque_provenance_confirmatory_execution_candidate_protocol.py", "forge_opaque_provenance_confirmatory_execution_composition_gate.py"))
    for forbidden in ("openai_ak", "deepseek_api_key=", "api_key=", "execute_pair(", "execute_reachability("):
        assert forbidden not in sources
